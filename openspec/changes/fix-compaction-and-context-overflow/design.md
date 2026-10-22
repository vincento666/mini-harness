# Design

## Context

见 `proposal.md` 的 Why——根因、实测的 400 正文、以及那次会话的日志形状都在那里。这里只补形状层面的现状与约束。

现状（`main` 上的实现）：

- 装配越线时 `_compact_within_assembly` 已经算出了遮蔽范围 `rng = shadowed_range(events, settings.window)`，`compaction/summary` 的 payload 里已经写着 `shadowed_range: {start, end}`；**但摘要调用发的是 `[*context.messages, SUMMARY_INSTRUCTION]`**——整份表层，与被遮蔽的那段一模一样大。
- 折叠层已有 `fold(events)`，且遮蔽语义（`shadowed_seqs`、`PROTECTED_EVENT_TYPES`）都在 `context/` 与 `events/` 里；「按一段 seq 区间折出对话」目前没有入口。
- 适配层的溢出识别只看 `error.code == "context_length_exceeded"`；失败正文在 `_post` 里被丢掉，`detail` 只剩 `HTTP <状态码>`。
- chat 的 stdout 是日志的投影（只打不带 `purpose` 的 `model/response` 正文）；段级收尾在屏幕上是无声的。

约束：不变量 A（日志唯一真源）、D（窗口预算与 `CONTEXT_WINDOW_EXCEEDED`）、F（全程可观测）；测试只写在七个 seam 上；`字符 ÷ 4` 的估算是照 DSH 的启发式，本 change 不动它。

## Goals / Non-Goals

**Goals:**

- 摘要调用携带的内容与它要压缩的那一段一致，且这份请求自己装得下——判据用现成的触发线，不新增参数。
- 真端点说「装不下」时走既有的溢出路径（请求级压缩 + 重试一次 → 不行就 `CONTEXT_WINDOW_EXCEEDED`），不是 `PROVIDER_HTTP_STATUS`。
- 失败时日志与屏幕上都说得出那句话。

**Non-Goals:**

- 不改 `estimate_tokens` / `_record_chars` 的估算口径；不引入精确 token 化。
- 不加工具输出修剪器、不给摘要请求加 `max_tokens`、不做分段多次摘要。
- 不动 `compaction/summary` 的 payload 形状（`shadowed_range` / `summary` / `tokens_before` / `tokens_after` 四个键照旧），因此不动 `schema_version`。
- 不动 `serve` 的事件流、不动 `run` 的退出码表。

## Decisions

**D1 摘要请求只回放被遮蔽的那一段（照 DSH）。** DSH 的 `dsh-compaction-basic` 明确「该调用回放系统消息 + **已遮蔽区域的消息** + 尾随摘要指令」，且「它无法缩减系统提示词、工具或会话前缀」。mini 之前发整份表层是偏离，按「DSH 为真」更正。做法：`context/` 提供一个按 seq 闭区间折出对话的入口（复用既有折叠与投影语义），`turn_loop` 只调它，把「系统消息 + 该区间折出的消息 + 摘要指令」交给 provider。备选：照旧发整份、只加 `max_tokens`——实测那种请求被端点拒（prompt 本身就超窗口），且 DSH 说清了为什么加输出上限救不了。

**D2 摘要请求的预算上限用触发线，装不下就从区间头部丢。** 现成的两条线里，触发线的语义正是「这份内容开始装不下了」，用它当上限不新增参数（备选：新增 `--summary-budget`，违反「不加没被要求的可配置性」）。丢弃顺序取「从头部丢、保住该段里较新的部分」：摘要的价值在最近的被遮蔽内容。备选：分段多次摘要——DSH 也没做，且会打破「一次装配最多一次压缩」。一条都装不下时**不发请求**，直接走 `CONTEXT_WINDOW_EXCEEDED`：发一个必被拒的请求只会把溢出伪装成 provider 失败。

**D3 溢出识别放宽成「`error.code` 命中 或 `message` 命中固定短语表」。** 短语表是一个词表常量（四个短语，大小写不敏感），落在适配层。备选 A：照旧只认 `error.code`——本机真端点实测不命中（它给的是 `type: invalid_request_error` 加一句 `leaves no room to answer in the context`）。备选 B：解析消息里的 token 数与窗口比较——依赖措辞里的数字，更脆。DSH 的口径是「分类由适配器维护」「其他提供方侧上下文失败不参与分类」，mini 照这个口径，代价（猜文本）落 ADR-0022。

**D4 `detail` 的形状是 `HTTP <状态码>：<有界摘要>`。** 单行、至多 200 字符、换行压成空格；优先取错误对象的 `message`，取不到取正文本身；正文空则只有状态码。备选：塞全正文——一次 502 的 HTML 能把日志撑爆，也违反「日志是给人读的事件流」。

**D5 chat 的可见性走 stderr，stdout 的投影规则不动。** 一行含段的停止理由与失败 `code`；`MODEL_COMPLETED` 与 `ABORTED` 不打。备选：往 stdout 打——stdout 是日志的投影，掺进非投影行会破坏「stdout 与日志不冲突」那条判据。`MAX_TURNS` 也打：那次人手验收里第一段用尽 8 个回合，屏幕上没有任何痕迹。

**D6 遮蔽反馈同样走 stderr，内容取自 `compaction/summary` 已有的四个键。** 压缩发生时人要在屏幕上看到「哪一段被遮蔽、释放了多少」——数据本来就在日志里（`shadowed_range` / `tokens_before` / `tokens_after`），缺的只是把它说给人听。不新增事件类型、不改 `compaction/summary` 的 payload。备选：往 stdout 打——同 D5 的理由；备选：不打、让人自己去读日志——人手验收实测到「看不见」就是这次的起因。

**D7 模型相关功能的判据分两层，真实端点那一层是完成判据。** 本 change 起效：① **CI 层**——seam ⑤ 与 ⑥ 的判据用**从真实端点会话里裁下来的记录**做 fixture（真实响应正文、真实 `compaction/summary` 的字段形状），不靠手写的桩数据编造形状；② **完成层**——一次真实端点的 `minihns chat` 实测（本机 Strata 端点），跑完并把 session id、压缩发生在第几回合、屏幕上那一行的原文记进 `docs/verification/`，**不跑完这个 change 不算完成**。CI 不持 API key 这条不变（handoff 决策 6 的原意是「真实调用不进 CI」，不是「真实调用不算验收」）；补的是「真实那一层跑不跑」以前没有任何判据守着这件事。备选：CI 里带 key 跑真实端点——被否，CI 不持密钥是既定选型；备选：照旧只把真实那一半写进 manual——被否，那正是这次漏洞的形状。ADR-0022 记这条。

**测试策略（seam 边界）。** seam ①：假 provider 记下收到的消息，断言除系统消息与末条指令外全部落在 `shadowed_range` 内、保留尾部不在其中；再断言「区间裁到最小仍装不下」时没有 `model/request(purpose: compaction)` 而是 `error/context`。seam ④：按 seq 区间折出对话的入口（含保护事件不参与）。seam ⑤：假端点四种形状——`error.code` 命中 / 只有 `message` 命中 / 都不命中 / 正文非 JSON——各自的 `code` 与 `detail`；其中「只有 `message` 命中」那一条用真实端点实际回过的正文。seam ⑥：真实子进程跑 `minihns chat`，断言 stderr 那一行、stdout 不含它、日志不含它；再断言压缩那一段的遮蔽反馈一行。真端点那一半是完成判据（D7 的第二层），跑一次、记进 `docs/verification/`。

## Risks / Trade-offs

- [短语表脆，提供方措辞一改就失效] → 只落在适配层、不污染回合层；不命中时行为与今天完全一致（`PROVIDER_HTTP_STATUS`）；代价与 DSH 的对照写进 ADR-0022，短语表本身有「每个值可达」判据。
- [估算与真端点差约 4 倍这件事本 change 不修] → 缓解是 D1 让摘要请求装得下、D3 让真端点的拒绝走溢出路径；缺口记进 `docs/adr/0002` 第 64 条，留给后续里程碑。
- [从头部丢弃等于最旧的内容完全不进摘要] → 记进 ADR-0002 作为欠账；DSH 的 `dsh-compaction-tool-result-pruner`（先修剪超大工具输出、可能完全省去摘要）是另一条路，留给 M11 之后。
- [stderr 那一行可能被当成日志的一部分] → 判据显式写「不在 stdout、不在日志」；`replay` 与 `serve` 的输出不受影响。
- [摘要求不再发整份表层，摘要质量可能下降] → 摘要本来就是给模型看的内部件，且 `compaction/summary` 仍写着 `shadowed_range` 与 `tokens_before/after`，可核对；人手验收里观察并记录。
- [从真实会话裁下来的 fixture 会过期、且带真实内容] → fixture 只留字段形状与必要的短句（真实的那句 400 正文、真实 `compaction/summary` 的四个键），不整段搬工具输出；每条 fixture 在文件里写明来源 session id，措辞变了就用新一次真实实测的产物替换。
