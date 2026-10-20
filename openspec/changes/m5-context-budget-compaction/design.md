# Design

## Context

动机见 `proposal.md` 的 Why。这里只写现状与约束。

**装配的现状**（`loop/turn_loop.py:436-448`）：每个回合读全量日志 → `fold(events)` → 写 `context/assembled` → 写 `model/request` → `provider.generate(context.messages, ...)`。`fold` 是纯函数，不知道窗口、不知道预算、不遮蔽任何东西（`events/fold.py:104` 的 docstring 明写「不截断、不遮蔽、不摘要」）。

**已有的原料**：`Usage` 从 M4 起就在 `model/response.payload.usage` 里（`turn_loop.py:494`），`input_tokens` 取自 OpenAI 兼容的 `prompt_tokens`（`provider/openai_compat.py:172`）。`cli/main.py:44-51` 的 `STOP_REASONS_TO_EXIT_CODES` 里没有 4，`EXIT_CONTEXT_EXCEEDED` 这个常量还不存在。词表分两处：事件类型在 `events/vocabulary.py`，`StopReason` 在 `loop/turn_loop.py:26`。

**约束**：不变量 A（provider 不碰日志，一切落盘由内核做）、C（五步显式）、D（预算与显式溢出错误）。折叠一致性由前缀重算定义（`context-projection`）——任何压缩决策落进日志之后，`minihns replay` 的逐点重算 MUST 仍然成立。

## Goals / Non-Goals

**Goals**

- 让「这份上下文有多贵」成为日志里可断言的事实，让「贵到装不下」成为一个结果词。
- 压缩是**追加式的**：写一条替换记录，不改写、不删除、不重排任何既有记录。
- 读方（fold）与写方（回合循环）各自只知道自己那一半：fold 只 honor 遮蔽，回合循环只做预算判定与摘要调用。

**Non-Goals**

- 不做 token 计量的服务化、投影缓存、检查点（DSH 的 `dsh-token-meter` 是 replay-aware 服务，`storages/session_projcache` 是投影缓存；mini 每次装配现算，与既有 fold 同阶）。
- 不做压缩策略的可配置化：触发线公式、65536 headroom、16% 尾部保留都是实现常量（同「并发额度 8 不许有开关」那条规矩）。
- 不做单条工具结果的剪枝、spill、图片 offload、`/compact` 命令。

## Decisions

### D1 遮蔽是日志上的一条替换记录，不是 start/summary/end 标记对

`compaction/summary` 一条记录，payload 带 `shadowed_range: {start, end}`（含两端，取自同一 session 的 `seq`）。

DSH 的事实：`SurfaceOp = 'append' | {op:'replace', startSeq, endSeq}`，`compaction/summary` 与 `compaction/prune` 携带 `shadowedRange{start,end}` / `shadowedSeqs[]` / `shadowedTokenCount`（`docs/dsh-reference/DSH运行时架构剖析.html` 的「表层（surface）」一节）。handoff 决策 10 与 26 写的是 `compaction/start → summary → end` 标记对——人已裁决改成 DSH 形状。

为什么：mini 的 fold 是读方派生，fold 需要的全部信息（哪些记录不产出消息）在这一条记录里；`start` 与 `end` 两条对折叠没有信息量，只给以后的 REPL / SSE 看进度。考虑过的替代：`shadowed_seqs` 列表（DSH 也有）——一次遮蔽常覆盖上百条记录，payload 会长，取 range。代价：进度可观测性变弱，M6/M7 若要显示「正在压缩」得另找事实。→ **ADR-0015**。

### D2 摘要由模型生成，走同一个 `generate`

摘要请求的消息 = 受保护头部 + 被遮蔽那段折出来的消息 + 一条固定的 user 指令；`tools` 传空列表（摘要不需要工具）。那次调用照常落 `model/request` 与 `model/response`，payload 带 `purpose: "compaction"`；fold 对带这个标记的 `model/response` 不产出 assistant 消息。

为什么不落盘：不变量 F（全程可观测）与 A（provider 不碰日志、由内核落）。为什么不进表层：否则摘要文本在上下文里出现两次——一次是 `system` 摘要，一次是 assistant 回复。考虑过的替代：不落 `model/*`、把 usage 与重试塞进 `compaction/summary` 的 payload——省两条记录，代价是那次调用的重试与失败事实没有既有形状可挂。

mock provider 不需要新形状：摘要调用只是 fixture 序列里多一条条目，按发生顺序排即可。

### D3 预算读数 = max(估算, provider 回报过的最大值)

估算：逐条消息 `len(content) + len(tool_calls 的 JSON 文本)`，除以 4 向上取整，再逐条相加。校准：该前缀里 `purpose` 不是 `compaction` 的 `model/response.payload.usage.input_tokens` 的最大值。摘要那次调用的回报值不参与——它量的是被遮蔽的那一大段，压缩之后还拿它当读数，下一回合立刻又越线，于是每一回合都压缩一次，最后撞到兜底溢出。这条在 propose 之后由实现核对补进规格（`context-budget` 的「摘要调用的读数不参与校准」场景）。

`tool_calls` 必须算进去——上下文里最贵的常是模型请求的 `write` 参数，只算 `content` 会漏掉它。

这是 handoff 风险 3（「`len ÷ 4` 不是真 token 数，harness 不依据自己的估算做终止决策」）的落点：估算驱动**压缩**，provider 的真实超限报错驱动**兜底终止**；估算兜底只在「压缩后仍装不下」时出手。→ **ADR-0016**。

### D4 压缩范围与语法边界

可遮蔽范围 = 对话体里 `session/start` 之后、保留尾部之外的那些记录。尾部保留预算 = `floor(W × 0.16)`（DSH `DEFAULT_RETAIN_RATIO = .16`），从对话体末尾往前按**组**累计：一个 assistant 消息加它的工具结果组是一组，切点 MUST NOT 落在组内。

DSH 保护的是 node 0（受保护的 `system/message`），压缩范围从「第一个不是 system/message 的节点」开始（compaction-basic README:113）。mini 的受保护头部与用户 prompt 都从 `session/start` **一条记录**派生，覆盖它等于同时拆掉头部与任务本身——这是 mini 与 DSH 的一处形状差异，不是简化。摘要消息因此落在头部与用户 prompt 之后，对应 DSH 里紧跟 node 0 的那个位置。→ **ADR-0017**。

不拆散配对是硬要求：范围拆开一对 `tool/call` 与 `tool/result` 会让 fold 为那条调用派生 `TOOL_OUTCOME_UNKNOWN` 闭合，压缩反而把上下文弄得更怪。切点落在组内时**整组一起遮蔽**，而不是把整组拉进尾部——尾部是预算的目标，不是保证；把一条 25000 token 的 assistant 请求拉进 20480 的尾部等于这次压缩什么都没做。

既有的 `compaction/summary` 也不进范围：遮蔽它等于丢掉上一份摘要，而摘要链是压缩后仅存的长程记忆。

`shadowed_range` 返回 `None` 的唯一含义是「没有可遮蔽的内容」：候选为空，或遮蔽之后尾部为空。这时压缩帮不上忙，走溢出路径（`context-budget` 的「单条消息本身就超线」）。

### D5 一次装配最多压缩一次

不循环压缩。一次压缩后仍超线说明「保留尾部本身装不下」，那是溢出而不是压缩不够。考虑过的替代：反复压缩直到装不下——要多调模型、要重算摘要、判据翻倍，且 DSH 也没有这条。

### D6 取消在场时不压缩

`cancel.is_set()` 时跳过预算判定与摘要调用，直接走既有取消路径。为压缩再调一次模型违背 ADR-0011 的「取消优先到底」。

### D7 摘要调用失败沿用 `PROVIDER_ERROR`

不新造「压缩失败」结果词：既有形状（`error/model` + `stop_reason: PROVIDER_ERROR` + 退出码 1）够用，此时不写 `compaction/summary`。新造一个词表值没有新判据（不变量 B）。

### D8 provider 侧只认 `error.code == "context_length_exceeded"`

OpenAI 兼容端点的稳定字段。按 message 文本匹配会把一种误判换成另一种。代价：非兼容端点用别的 code 时塌回 `PROVIDER_HTTP_STATUS`（退出码 1），漏判可见但不静默——日志里那条 `error/model` 就是证据。

### D9 代码落在哪

新增一个模块 `src/mini_harness/context/budget.py`：估算、触发线、尾部保留与语法边界的选择（输入是记录序列与 W/O，输出是 `shadowed_range` 或 `None`）。`events/fold.py` 只加读方规则（honor 遮蔽、摘要进表层、`purpose` 标记跳过）。回合循环负责编排：判定 → 调模型 → 落 `compaction/summary` → 重新折叠 → 必要时溢出。

为什么不塞进 `fold.py`：fold 是纯读方，让它知道 W / O / 触发线等于把写方决策搬进读方，也让 seam ④ 的判据被迫带上预算参数。为什么不塞进 `turn_loop.py`：那里已经 562 行、`_dispatch_batch` 一个函数 242 行（ADR-0002 第 18 条），再塞一段只会加重那笔账。

## 测试策略（seam 边界）

| seam | 判据落点 | 判什么 |
| --- | --- | --- |
| ① 回合循环 | `tests/test_context_budget.py`（新） | 触发线数值；小 W 触发压缩且 `compaction/summary` 在 `context/assembled` 之前；一次装配只一次；兜底溢出 → `error/context` + `turn/end` + 退出码 4；取消在场不压缩；摘要失败沿用 `PROVIDER_ERROR`；溢出回合没有 `model/request` |
| ④ 日志追加与折叠 | `tests/test_context_fold.py`（扩） | 被遮蔽的记录不产出消息；不拆散配对；被遮蔽的调用不派生闭合；摘要 `system` 消息的位置与多条顺序；`purpose: compaction` 的回复不进表层；确定性；压缩过的日志逐点重放 |
| ⑤ Provider 接口 | `tests/test_provider_openai.py`（扩） | 400 + `context_length_exceeded` → `PROVIDER_CONTEXT_OVERFLOW` 且无 `model/retry`；其它 400 仍 `PROVIDER_HTTP_STATUS` |
| ⑥ CLI 黑盒 | `tests/test_cli_budget.py`（新） | `--window` / `--reserve` 进 payload；非法取值退出码 2 且不建日志；退出码 4 可达；压缩过的日志 `minihns replay` 逐点通过 |
| ② 工具注册与管线 | `tests/test_vocabulary_reachability.py`（扩） | 新事件类型与新 `StopReason` 值可达，词表外不写出 |

fixture：新增 `tests/fixtures/scenarios/compaction/turns.json`（小 W 下触发一次压缩的回复序列）。

## Risks / Trade-offs

- **[中文被 `len ÷ 4` 严重低估]** 中文一个字符常是 1 token 甚至更多，估算可能只有真实值的四分之一 → 压缩触发太晚。缓解：两条触发路径（D3 + D8），人手验收专门观察一次真实 run 里压缩有没有按时触发。
- **[默认参数下触发线是 54272，不是 102400]** `W − O − 65536` 比 `W × 0.8` 小，128000 窗口的 run 在约 42% 处就开始压缩。这是照抄 DSH 的 headroom 语义，不是笔误；写进 ADR-0016，免得下一个里程碑以为是 bug 去「修」。
- **[遮蔽让日志变长而不是变短]** 压缩后日志更长，`read_events` 每回合读全量。缓解：本轮不动它（M1 起的形状），把「每回合全量重读」记进 ADR-0002 作为到 M11 的账。
- **[覆盖率地板]** 新增的压缩段落在 `turn_loop.py`，那里已有 23 行未覆盖。缓解：判据按 seam 表写全再跑门禁；地板数值不许靠低价值测试凑。

## Open Questions

- 摘要指令那条 user 文本的具体措辞——常量内容，实现期定，不影响规格与任务拆分。
- 多次压缩的遮蔽范围是否允许重叠——按 D4 的「从上次切点之后继续」自然不重叠；真出现重叠再定，不预先写规则。
