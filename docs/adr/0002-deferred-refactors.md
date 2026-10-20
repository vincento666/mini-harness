# 记账：M1 至 M4 留下的坏味道与设计缺口，到对应里程碑再动

这一条不是待办清单的优先级排序，而是 code-review 修复轮（change `m1-event-log-and-turn-loop` 的 tasks 第 11 节）留下的**账**：审查里确认存在的重复与泄漏，M1 里改它们只会增加改动面、不会增加判据，因此只记账不动代码。任何一条到 M2 都可以按新证据改判——但改判要发生在 M2 的 change 里，不是顺手改。第 9 至 12 条来自 M2（change `m2-file-tools-and-fences`）的 `code-review` 两轴审查，第 13 至 17 条来自 M4（change `m4-real-provider`）的同一轮审查；处理方式同样是记账。M3（change `m3-bash-concurrency-timeout`）的收尾轮对第 1、8 至 17 条逐条改判，判词写在各条末尾：已处理 4 条（1、9、10、11），改判为长期形态 3 条（8、12、16），未处理推到 M5 2 条（14、15），未触发 1 条（17）。第 18 至 29 条来自 M3 的 `code-review` 两轴审查——Standards 轴确认存在但「改它不增加判据」的判断项，加两条规格 ↔ 实现的判断（第 28、29 条）——处理方式同样是记账：八条推到 M5，两条判为不动（25、27），两条按现状留着并写明何时才动（28、29）。第 30 条来自 M3 的人手验收（cmd.exe 的 GBK 输出碎成 U+FFFD），同样是记账。最后一节记提交纪律的三处措辞欠账：历史提交不改写，只把与 AGENTS.md 原文不符的地方更正在这里。它前面那节是 M8 审查轮（2026-10-20）的账：提交粒度三处超数没写打包理由、三个 docs 提交没有门禁行、派发段两条未定形状推到 M10，第 18 与 19 条改判。

## 1. `run_session` 的九个关键字参数就是 `session/start` 的 payload

`run_session(prompt, provider, provider_name, log, registry, workspace, max_turns, cancel, append_system_prompt)` 里除 `provider`/`log`/`registry` 外的那几个，与写进 `session/start.payload` 的字段几乎一一对应。测试里因此有 11 处把同一串参数重复写一遍。

- 现在不动的理由：参数形状就是 seam ① 的接口本身，M1 只有一个调用方（CLI）；抽 `SessionSettings` 会让「payload 里有什么」这条事实变成两层间接。
- M2 的处理：加文件工具时参数还会再长（工具白名单、预算），那时引入 `SessionSettings`（pydantic 模型），让它同时是 `run_session` 的入参和 `session/start.payload` 的来源，测试改用一个构造 helper。
- **部分处理（2026-10-17，M2 change `m2-file-tools-and-fences` 任务 3.2；M2 审查后更正）**：`loop/settings.py::SessionSettings` 落地，`run_session` 收 `settings=`，`session/start.payload` 由它生成；seam ① 与 seam ⑥ 的测试改用 `tests/tool_harness.py` 的 helper。但 seam ②③ 里仍有四处手搓 `SessionSettings(...)`（`test_fences._context`、`test_approval_gate._run`、`test_vocabulary_reachability._dispatch_with_gate`、`test_tool_registry`），因为 helper 不收 `registry` 与 `approval_gate`。剩下的这一半留到 M3：把 helper 扩成收 `registry` / `gate` 时才值得收，否则只是把一处构造搬到另一处。
- **已处理（2026-10-19，M3 任务 2.1 / 2.2 / 2.3）**：helper 收了 `registry` 与 `approval_gate`，四处手搓 `SessionSettings(...)` 改用 `tests/tool_harness.py::dispatch_context`；再把 seam ① 的 run 形状收成一份（`run_session_fixture`），连带收掉 `test_turn_loop.py` 的 12 处内联、它的 `_run_with_provider` / `_run_through` / `_settings`、`test_tool_dispatch.py::_run`、`test_vocabulary_reachability.py` 的两处内联。`SessionSettings(` 在 `tests/` 里 15 → 10 → 4 处，剩两处内联有结构性理由：SIGINT 黑盒与「日志变得不可写」那条都要在跑之前先把日志建出来并改它的权限，helper 插不进去。

## 2. `ToolDefinition` 与 `ToolSpec` 字段完全相同

`mini_harness/tools/registry.py::ToolDefinition` 与 `mini_harness/provider/contract.py::ToolSpec` 都是 `name: str` + `description: str`，`ToolRegistry.specs()` 逐字段搬运。

- 现在不动的理由：两个名字对应两个概念（注册表里的定义 / 送给模型的规格），M1 里合并会抹掉这条区分，而区分本身是设计意图。
- M2 的处理：文件工具落地时看它们是否开始分叉（参数 schema、权限标记）。分叉就保留两个并让 `specs()` 显式映射；不分叉就合并成一个类型并在两处复用。
- **已处理（2026-10-17，M2 任务 10.1）**：分叉了——`ToolDefinition` 多了 `args_model`、`mutates`、`run`，`ToolSpec` 仍然只有 `name` + `description`，`specs()` 显式映射。两个名字对应两个概念这条区分因此保留。

## 3. `main._replay` 摸的是事件层的内部形状

`_replay` 自己扫 `records` 找 `turn/start` 取 `turn_id`、按 `context/assembled` 的下标切前缀。这些是 events 层的知识，放在 CLI 层意味着 events 层改形状时 CLI 会跟着坏。

- 现在不动的理由：M1 只有 replay 一个消费者，且这段逻辑与它的判据（逐点相等）在同一个测试文件里最好读。
- M2 的处理：下沉成 events 层的 `assembly_points(records)`（返回 `(前缀, turn_id, 记录)`），CLI 只负责打印与退出码。
- **未处理（2026-10-18 的 M3 分流核实）**：上面那条「M2 的处理」没有执行——`cli/main.py::_replay` 仍自己扫 `records` 找 `turn/start`、按 `context/assembled` 的下标切前缀。这条账本记录与实况不符，已在此处更正而不是悄悄删掉。改判：第二个消费者是 M6 的 chat REPL 与 M7 的 serve SSE，**推到 M6**；M3 加 `bash` 不改 replay 的输入形状（工具名列表已在 `session/start.payload.tools`，`fold()` 从它派生），所以它不会变得更坏。

## 4. 三个测试文件各自有一份 `_cli` 黑盒 helper

`tests/test_cli_run.py`、`tests/test_cli_replay.py`、`tests/test_integration.py` 都定义了几乎相同的 `_cli(*args, cwd)`（`sys.executable -m mini_harness.cli.main`、UTF-8）。

- 现在不动的理由：seam ⑥ 的测试要能单独读懂「这是一次真实子进程调用」，共享 helper 会让每个文件少一行但多一次跳转。
- M2 的处理：若第四个 CLI 测试文件出现（三份变四份），把它们收进 `tests/cli_blackbox.py`，并把 `_run_once` 这类构造 helper 一起收进去。
- **已处理（2026-10-16，chore(test) 覆盖率记账）**：不是等第四个文件，而是记账本身逼出了共享——子进程要计入覆盖率，`coverage run --rcfile=<仓库根>/pyproject.toml -p` 与 `COVERAGE_FILE` 这两个坑必须在三处同时改，三份副本就成了三处必须同步的正确性。三份 `_cli` 已收进 `tests/cli_blackbox.py::_cli`（签名 `(*args, cwd, env=None)`，与原 `test_cli_run.py` 那份一致），三个测试文件只留 `from cli_blackbox import _cli`。`_run_once` / `_run_scenario` / `_log_files` 仍留在各自文件里：它们是本文件的构造细节，与记账无关。

## 5. `stop_reason`、`outcome`、`role` 是裸 `str`

词表写在 spec 里（五个 `stop_reason`、两个 `tool/result.outcome`、三种消息 `role`），代码里都是 `str`，mypy 挡不住词表外的值：`RunOutcome(stop_reason="OK")` 能通过类型检查。

- 现在不动的理由：词表本身在 M1 期间还在被 spec 改动（本轮就加了 `NOT_IMPLEMENTED`），锁成 `Literal` 会让每次词表改动多一处类型编辑；测试目前从日志断言词表，覆盖是够的。
- M2 的处理：词表稳定后改成 `Literal[...]` 或枚举，并让 `EventRecord.type` 的校验也走同一份词表常量。
- **已处理（2026-10-17，M2 任务 2.3 / 10.3 / 12.2）**：`StopReason`、`ToolOutcome`、`FenceCode`、`ApprovalDecision` 都是 `Literal`，词表常量与 `Literal` 同源（`STOP_REASONS = frozenset(get_args(StopReason))`），`EventRecord.type` 的校验走 `events/vocabulary.py`；后两份词表随围栏模块（任务组 4 与 5）落地。词表里「有取值跑不到」由 `tests/test_vocabulary_reachability.py` 挡（任务 14.1）。

## 6. `RunOutcome.failure_code` 与 `detail` 只被 CLI 读一次，`turns` 在生产里没人读

内核结果里的这三个字段，`failure_code`/`detail` 只在 `_run` 映射退出码时被读，`turns` 目前只有测试读。

- 现在不动的理由：它们是把「失败也是结果」写进日志之外的唯一载体；`turns` 是 `session/end.payload.turns` 的对应物，留着让内核结果与日志可对照。
- M2 的处理：加文件工具时若需要「失败发生在哪个工具」这类细节，扩 `RunOutcome` 而不是新加一个并列结果类型。
- **已按原计划走（2026-10-19，M3 收尾核实）**：M3 的派发段失败沿用同一个形状——批次里的内核失败带 `failure_code` 与 `detail`，`_kernel_failure` 把它映射成 `RunOutcome(stop_reason=…)`，没有新加并列结果类型。`turns` 仍只有测试读（`session/end.payload.turns` 的对应物）。

## 7. 设计缺口：replay 的折叠入参里工具描述取空

`_replay` 重算每个 `context/assembled` 时传 `tool_descriptions=()`：M1 注册表为空，所以这与实时装配一致。一旦 M2 注册了真实工具，头部里的「可用工具」块会依赖注册表，而注册表的名字只出现在该装配点**之后**的 `model/request` 里——前缀里没有这个事实，重放就会对合法日志报 `REPLAY_MISMATCH`。

- 现在不动的理由：M1 没有任何注册工具，这条差异不存在；把它做成「前缀可见的工具描述」要改 `session/start` 的 payload 字段表，属于扩词表级决定。
- M2 的处理：在 `session/start.payload`（或每个 `turn/start.payload`）里记下当时的工具名列表，让折叠入参全部可从日志前缀派生；`tests/test_cli_replay.py::test_replay_does_not_use_events_after_the_assembly_point` 已经是这条判据的守门测试，M2 只需把取空的这一行换成从前缀派生。
- **已处理（2026-10-17，M2 任务 3.2 与 11.1）**：工具名列表进 `session/start.payload.tools`，`fold()` 不再收 `append_system_prompt` / `tool_descriptions` 参数——单一真源是 `session/start`，回放侧与实时侧从同一份前缀派生。CLI 一接线就让三条 replay 判据立刻红（`REPLAY_MISMATCH: seq=2`），这条差异不是假设。

## 8. `provider` 层的两处 import 指向 `events.fold`

`provider/contract.py:11` 与 `provider/mock.py:13` 都 `from mini_harness.events.fold import Message`，因为 `generate` 的入参类型是 `Sequence[Message]`。依赖方向因此是 provider → events，而不是两份契约各自独立；分层图上看是一条反向箭头。

- 现在不动的理由：`Message` 目前只有折叠一个生产者，另立一个消息类型模块会让同一个类型有两个家；M1 的判据不依赖这条方向。
- M2 的处理：文件工具落地后看 `Message` 是否需要携带更多工具相关字段（`tool_calls` 与 `tool_call_id` 已经在）。需要就把 `Message` 抽成独立的类型模块，provider 与 events 都指向它；不需要就把这条方向记为长期形态并在此处改判。
- **改判为长期形态（2026-10-19，M3 收尾核实）**：M3 加 `bash` 与并发派发没有让 `Message` 多带一个字段——工具调用相关的两个字段 M1 就在。provider → events 这条反向箭头保留。

## 9. `approval/*` 这一对事件在问完人之后才落盘

`turn_loop` 先派发（含向人提问），再把 `approval/request` 与 `approval/response` 追加进日志。人已回答、而执行段抛异常或进程被杀时，日志里没有任何 `approval/*`——event-log 规格要求的「每条 `approval/request` 有且只有一条配对的 `approval/response`」在这种情况下不成立。

- 现在不动的理由：M2 的判据覆盖的是「问了就成对出现」与「没问就都不出现」（12.3 与 13.x），这条差异只在「问了之后进程死掉」的路径上存在，而 M2 没有能可靠杀死进程再检查日志的判据。
- M3 的处理：把 `approval/request` 在提问**之前**写、`approval/response` 在拿到结论后立刻写，代价是日志里可能出现「有 request 没有 response」的半对——那时要么加一条折叠侧的判据把它读成「未回答」，要么在词表里加一个 `UNANSWERED`。这是扩词表级决定，不在 M2 顺手做。
- **已处理（2026-10-19，M3 任务 5.6）**：`approval/request` 在提问之前落盘，写不进去就不问人。落地形状是 `dispatch_tool_call` 多一个可选入参 `on_approval_request`（落盘钩子，返回「写进去没有」），日志仍由回合循环写，不变量 A 没动。半对（有 request 没 response）只在 `ABORTED` 收尾的 session 里成立，**没有加 `UNANSWERED` 词表项**：改用折叠侧的容忍判据（`tests/test_context_fold.py::test_an_unanswered_approval_request_leaves_the_fold_unchanged`）钉住「半对不影响折叠结果」。

## 10. 取消信号只在回合边界被看到

`cancel.is_set()` 只出现在回合边界（`turn_loop` 的 281 / 293 / 307 三处，行号在 2026-10-18 的 M3 分流里更正过；原来写的 267 / 279 / 293 是 M2 时的位置），派发一批 `tool_calls` 的循环里没有检查。实测：第一个调用置位 cancel 后，同一批里的第二个 `write` 仍被派发。规格 turn-loop 那条「当运行期间收到取消信号时…」读起来像随时生效。

- 现在不动的理由：M2 的取消判据覆盖的是 `generate` 期间与回合边界；「一批工具中途取消」需要决定剩下几个算不算执行过、要不要写 `tool/cancelled`（这个词在 M2 词表之外，见 ADR-0003 第 3 条）。
- M3 的处理：决定「取消发生在派发段时剩下未执行的调用怎么写」——要么加 `tool/cancelled` 词表项，要么在 `turn/end.payload` 里记下「未执行的 `tool_call_id` 列表」。两者都是扩词表，与第 3 条同源。
- **已处理（2026-10-19，M3 任务 1.1 / 5.2 / 5.3）**：选 `tool/cancelled`。派发段两处查取消（拿到独占权之后、`begin` 之前），已经开始的被打断并塌成 `TOOL_CANCELLED`，每条 `TOOL_TIMEOUT` / `TOOL_CANCELLED` 配一条 `tool/cancelled`；判据「取消之后没有『有 `tool/call` 没 `tool/result`』的记录」钉住剩下的那几个不写 `tool/call`。`turn/end.payload` 不记未执行列表——那条形状没有判据需要它。
- **被取代（2026-10-20，ADR-0011）**：M3 那套「取消掀翻整个会话」的形状整体重做——取消改成回合级协作式事件，派发前被取消与派发后被取消是两个结果词，被中断的回合由闭合记录收尾，会话是否终止由入口决定。落点 M8。这一条从「已处理」改判为「被取代」，M8 之后本条作废。

## 11. `error/fence` 里被拒的路径只在自由文本 `detail` 里

payload 是 `turn_id` / `tool_call_id` / `code` / `detail`。规格要求「被拒的路径或工具名」可断言，实现把它塞进自由文本，且形态不统一：`OUTSIDE_WORKSPACE` 放解析后的键，`SANDBOX_DENIES_WRITE` 放未解析的 `raw_path`。判据只能断言 `code`，断言不了路径。

- 现在不动的理由：M2 的判据断言的是 `code` 与退出码；把路径做成结构化字段要定「放原始写法还是解析后键」，而这两者对模型的可读性不同（原始写法更接近模型自己写的路径，解析后键更接近围栏真正拒绝的东西）。
- M3 的处理：加 `path` 与 `raw_path` 两个字段（或一个 `target` 对象），并让 `detail` 只面向人。改的是 `error/fence` 的 payload 字段表，属于扩词表级决定。
- **已处理（2026-10-19，M3 任务 1.5）**：加 `path`（解析后的键）与 `raw_path`（模型的原始写法）两个字段，`detail` 只面向人。判据：越界写那条断言两者各有取值，`read-only` 下的 `bash` 那条断言两者都是 `null`——工具没有路径时不假造一个。

## 12. seam ②③ 的测试里各留一份桩与常量

`DONE` 与 `_DONE`、`_ApprovingGate` 两份、`_Gate` 两份、`_StubArgs` / `_WriteArgs` 两份桩，根因与第 1 条同源：`tests/tool_harness.py` 的 helper 不收 `registry` 与 `approval_gate`。

- 现在不动的理由：seam ②③ 的判据要能单独读懂「这个门只批准一次」「这个工具只记录被调用过」，把桩收进共享模块会让每条判据多一次跳转。
- M3 的处理：与第 1 条剩下的那一半一起做——helper 收 `registry` / `gate` 之后，桩才有唯一的家。
- **部分处理并改判为长期形态（2026-10-19，M3 任务 2.1 / 2.2 与收尾轮）**：根因消除了——helper 收 `registry` 与 `approval_gate`，四处手搓 `SessionSettings(...)` 与 `_DONE` 都改用 `tests/tool_harness.py`。桩本身按原理由留在各文件：`_Gate` 两份、`_WriteArgs`、`_StubArgs` 各判一件事（「这个门只批准一次」「这个工具只记录被调用过」），收进共享模块会让每条判据多一次跳转、少一处能单独读懂的形状。改判：这不是欠账，是 seam ②③ 的长期形态。

## 13. `generate` 里重试前后两段是同形的

`provider/openai_compat.py::generate` 把「发一次 → 是失败结果就返回 → 状态码可重试就记一条」在第一次与第二次请求前后各写一遍，`_retryable` 因此被调两次。

- 现在不动的理由：规格钉死「只重试一次」。把两段收成一个循环要么加一个没人要求的 `max_attempts` 参数（编码四规第 2 条），要么把「只重试一次」这条规格事实藏进循环边界——两者都让规格 ↔ 代码的对应变难读。
- M3 的处理：只有当「重试策略要可配置」真的成为需求（它现在在 AGENTS.md 的「明确不做」清单里）才抽；否则这条就是长期形态，到 M3 在此处改判。
- **改判为长期形态（2026-10-19，M3 收尾核实）**：M3 没有让重试策略可配置（`bash` 的超时是工具入参，不是 provider 的重试策略），多模型路由与重试策略仍在「明确不做」清单里。两段同形保留。

## 14. `base_url` / `model` / `api_key_env` 三个 `str | None` 一路结伴

它们从 `cli/main.py` 进 `loop/settings.py::SessionSettings` 再进适配器，只对 openai 路径有意义；mock 路径上三条都是 `None`。

- 现在不动的理由：`SessionSettings` 是 `session/start.payload` 的唯一来源（第 1 条的处理结果），而 payload 的字段表是规格事实；把三条收成一个 `ProviderEndpoint | None` 会让 payload 多一层嵌套，改的是规格而不是代码。
- M3 / M5 的处理：出现第二个真实 provider，或 REPL 需要显示端点时，立一个端点类型并让 payload 由它派生。
- **未处理，推到 M5（2026-10-19 核实）**：M3 没有引入第二个真实 provider，也没有动 `session/start.payload` 的字段表（本轮动的 payload 是 `error/fence`，见第 11 条）。
- **改判到 M9（2026-10-20，ADR-0010 之后）**：不再推 M5——M5 是窗口预算与压缩，跟端点类型无关，再推一次就是第五次「未处理推到 M5」。M9 `m9-assembly-and-config-layering` 才是「provider 与端点由装配决定」那一处：配置文件层叠落地时立 `ProviderEndpoint`，payload 由它派生。

## 15. 「这是 openai 路径」这个判断在四处重复

`cli/main.py` 三处（选 provider、`--fixture` 互斥、payload 那三条填不填）加 `loop/turn_loop.py` 一处（`start_payload` 里加不加那三条）。

- 现在不动的理由：四处各自决定不同的事；抽一个 `is_openai` 布尔只是把判断搬个地方，不减少任何一处。
- M3 / M5 的处理：与第 14 条同源——`SessionSettings` 带一个可选端点对象之后，「是不是 openai」变成「端点在不在」，四处塌成一处。
- **未处理，推到 M5（2026-10-19 核实）**：四处判断仍在四处，M3 一条没动；与第 14 条同源，等端点类型出现一起收。
- **改判到 M9（2026-10-20，ADR-0010 之后）**：与第 14 条一起收在 M9——端点类型由装配引入之后，「是不是 openai」变成「端点在不在」，四处塌成一处。

## 16. seam ① 的测试里 provider 桩与 run helper 各两份

`tests/test_turn_loop.py` 里 `_openai_provider(bodies)`（386 行）与 `_scripted_provider(responses)`（486 行）都是「用 `httpx.MockTransport` 按顺序回放响应」；`_run_with_provider`（503 行）与本 change 新加的 `_run_through`（644 行）都是「建日志、跑一次、读回记录」。

- 现在不动的理由：两份桩分别服务不同的判据（一份喂 JSON 体、一份喂现成的 `httpx.Response` 用来塞 429/500），两份 helper 的差别在 workspace 与 settings 是否要分开——M4 的「两种 provider 同一场景」那条判据必须两个 session 用同一份 workspace。
- M3 的处理：与第 1 条剩下的那一半、第 12 条一起做：`tests/tool_harness.py` 的 helper 收 `registry` / `gate` / provider 时，桩与 run helper 才有唯一的家。
- **部分处理并改判（2026-10-19，M3 任务 2.3）**：run 形状收成一份——`run_session_fixture` 成为 seam ① 唯一的「建日志 + 建 `SessionSettings` + 调 `run_session`」，`run_fixture_session` 退成它的 fixture 薄壳，既有调用点一行没动。两份 provider 桩按原理由保留：`_openai_provider` 喂 JSON 体、`_scripted_provider` 喂现成的 `httpx.Response`（429 / 500 只能这样塞），M3 没有让它们分叉的新证据。改判：桩留在 seam ① 的测试文件里是长期形态。

## 17. 一次回合发了两次 HTTP，日志只有一条 `model/request`

429 重试的回合里日志形状是 `model/request` → `model/retry` → `model/response`：请求实际发了两次，日志说的是「一次请求 + 一次重试」。

- 现在不动的理由：`model/retry` 的存在就是为了让这条可读；写两条 `model/request` 会让「一个回合一次请求」这条形状变模糊，而且要改 event-log 的 payload 字段表（扩词表级决定）。
- M3 的处理：若流式或并发派发让「一个回合多次请求」成为真实形状，再决定 `model/request` 是否带 `attempt` 字段。
- **未触发（2026-10-19 核实）**：M3 的并发派发让「一个回合多个工具调用」成为真实形状，没有让「一个回合多次请求」成为真实形状——provider 仍是一回合一次 `generate`，重试那条形状没变。`model/request` 不带 `attempt` 字段这条保留。

## 18. `_dispatch_batch` 一个函数里装着派发段的五件事

`loop/turn_loop.py:138-350` 约 210 行，里面五个闭包：`begin`（176）、`ask_logged`（198）、`escaped`（223）、`one`（240）、`dispatch_one`（250），共用 `calls` / `started` / `finished` / `mutating` / `read_slots` / `outcomes` / `stop` 这批批次状态。取消、超时、围栏、approval 落盘、内核故障五件事都在同一个函数里改（Divergent Change）。

- 现在不动的理由：这些闭包共用的是**一批调用的状态**，抽成模块级函数要把这七份状态传来传去；seam ① 的判据全部从日志外部观察派发结果，抽与不抽对判据没有区别，M3 里抽只增加改动面。
- 处理时点：M5（chat REPL 需要把同一派发段跑在不同外壳里）或出现第二个派发者时。那时先抽的是批次状态（一个 `_Batch`），不是闭包本身。
- **改判到 M10（2026-10-20，ADR-0013 之后）**：本条自己写的触发条件有两处不对——chat REPL 是 **M6** 不是 M5；而 ADR-0013 已把「管线加段 + 派生信号 + `CommandRunner` 缝」定在 **M10**，那正是派发段要动的时候。所以 `_Batch` 与第 23 条（`denial_code: FenceCode`）一起在 M10 收，M6 只收第 3 与第 21 条。

## 19. `begin` 与 `ask_logged` 是同形的

两个闭包都是「`_append_all` 写一条 → 有 failure 就记进 `outcome.failure`、`stop.set()`、返回 `False`」（`turn_loop.py:176-196` 与 `198-221`）。

- 现在不动的理由：两者写的记录类型不同，失败之后的下一步也不同（`begin` 假 → 这一条不派发；`ask_logged` 假 → 不问人）。合并要加一个「失败之后怎么办」的参数，那是为两个调用方加的抽象（编码四规第 2 条）。
- 处理时点：出现第三个「先落盘再决定」的记录时再收（M5 的 REPL 若把 approval 换成异步审批就有第三个）。

## 20. 只读与会改动的派发链在 `dispatch_one` 里分两段写

`if index > 0: await started[index - 1].wait()` 与 `if mutating[index] or mutating[index - 1]: await finished[index - 1].wait()` 串在一起，读的人要自己拼出「只有一对相邻的只读调用允许同时在跑」。

- 现在不动的理由：这两条 `await` 就是那条规则的直译，而规则本身是 M3 实现期才发现的（design.md 的 D1 落地修正）。收成 `await chain(index)` 会把规则从代码里搬进一个名字，规格 turn-loop 那条 scenario 判的正是这两条 `await` 的可观察结果。
- 处理时点：M5 若并发形状变复杂（只读调用带自己的预算、或出现第三类工具）再抽。

## 21. `registry` / `context` / `approval_gate` / `on_approval_request` 四个入参一路结伴

`dispatch_tool_call(...)` 里后四个每次一起出现（`tools/dispatch.py:41-48`），是 data clump。

- 现在不动的理由：它们就是 seam ② 的接口本身，判据注入的正是这四个的不同组合；收成一个 `DispatchEnvironment` 会让「这条判据注入了哪个门」多一层跳转。
- 处理时点：M5 / M6（REPL 与 serve 各带一套门与上下文时）。

## 22. 三个名字与实际含义有距离

`_race_with_cancel` 也 race 内核异常（`turn_loop.py:107`）；`MAX_PARALLEL_TOOLS = 8` 实际只约束只读调用（会改动的永远串行，`turn_loop.py:44`）；`_bounded` 做的是「截断并留固定标记」，不是「限制」（`tools/bash_tools.py:23`）。

- 现在不动的理由：改名是纯搬运，判据不受影响；M3 的提交里混进与规格无关的改名会让 `git log` ↔ `tasks.md` 的对应变浑。
- 处理时点：M5 与第 18 条同一处代码动的时候一起改（`MAX_PARALLEL_TOOLS` → `MAX_PARALLEL_READS` 一类）。

## 23. `denial_code: str | None` 应该是 `FenceCode | None`

`_BatchOutcome.denial_code`（`turn_loop.py:103`）与 `run_session` 里的局部 `denial_code`（`turn_loop.py:390`）是 `str | None`，取值来自 `DispatchOutcome.fence_code`（`FenceCode`）。mypy 挡不住往这两处塞词表外的字符串。

- 现在不动的理由：终点 `RunOutcome.failure_code` 是 `str`（它对应日志里的字段），只锁中间量等于锁一半；M3 里锁它没有新判据。
- 处理时点：M5 与第 5 条（词表 `Literal`）同源一起收。
- **改判到 M10（2026-10-20，ADR-0013 之后）**：与第 18 条一起收在 M10——那一步给 `FenceCode` 加 `SANDBOX_UNAVAILABLE`，围栏码在派发段里流过的地方全都要重看一遍，锁中间量与加词表值是同一次改动。第 5 条（`stop_reason` / `outcome` / `role` 的 `Literal`）照旧在 M5 收，那里 `StopReason` 要加 `CONTEXT_WINDOW_EXCEEDED`。

## 24. `ApprovalAsked | None` 是一个「可以没有」的钩子

`dispatch_tool_call` 的 `on_approval_request` 可选（`tools/dispatch.py:46`）；不传时 `approval/request` 不落盘，也就是 D12 那条规格在这个调用方身上不成立。实现里唯一的调用方（回合循环）永远传。

- 现在不动的理由：可选是为了 seam ②③ 的判据能单独跑 `dispatch_tool_call`（不建日志也能判围栏与门）。改成必填会让那批判据都要造一份日志。
- 处理时点：M5。若「不传就少写一条记录」这个形状造成真 bug，再改成必填或换成显式的 NoOp。

## 25. `tests/tool_harness.py` 的 `workspace` / `session_dir` 两个旋钮

`run_session_fixture(..., workspace=None, session_dir=None)` 两个可选参数默认都是 `tmp_path`；只有少数判据用它们（两个档位对 `bash` 那条要两个 session 各一个目录，「日志变得不可写」那条要在跑之前先把日志建出来）。

- 现在不动的理由：用它们的判据都有结构性理由；少一个旋钮就要多一处手搓 `SessionSettings`，那正是第 1 条刚收掉的东西。
- 处理时点：不动。M5 若 session 目录成为一等概念，跟着那时一起改。

## 26. `tool_harness` 的两个 `wrap` 闭包逐字段重建 `ToolDefinition`

`timed_registry` 与 `serialized_registry` 里的 `wrap`（`tests/tool_harness.py:59` 与 `83`）都把 `ToolDefinition` 的五个字段抄一遍再换 `run`。

- 现在不动的理由：`dataclasses.replace(definition, run=...)` 一行能替，但 M3 里改它没有任何判据变化，只是测试内部形状。
- 处理时点：M5 顺手（与第 22 条一起）。

## 27. `bash_tools.py` 两处平台判断方向相反

`_terminate_tree` 里 `if sys.platform == "win32":`（`tools/bash_tools.py:41`，`taskkill /T /F /PID`）与启动处 `if sys.platform != "win32":`（`tools/bash_tools.py:61`，`start_new_session=True`）。

- 现在不动的理由：两处都必须是字面量比较，`mypy --strict` 才会剪掉另一侧的 `killpg` / `getpgid` / `SIGKILL`——抽成 helper 函数不剪（M3 实测过，见 `docs/lessons.md`）。两个方向相反是用途不同（终止 vs 启动参数），不是笔误。
- 处理时点：不动。这是平台分支的长期形态，代价写在 ADR-0009 与 design.md 的 D9（两端各拉低一半覆盖率）。

## 28. `dispatch.py:73-79`：approval 记录写不进日志时塌成 `TOOL_IO_FAILED`

规格没有这条，实现有：`on_approval_request` 报告写不进去时直接返回 `TOOL_IO_FAILED`，不去问人。这一行未覆盖（`docs/CURRENT.md` 的未覆盖清单里）。

- 判词：留着。它是 D12「`approval/request` 在提问之前落盘，写不进去就不问人」的另一半，`TOOL_IO_FAILED` 是既有词表里最贴近的取值，没有为它新造取值。规格侧的对应物是 event-log 那条「提问之前落盘」；「写不进去时得到哪个结果词」目前没有规格，也没有判据需要它。
- 处理时点：M5 之后若这条变成要判的行为，再在 event-log 的 delta 里写明结果词。

## 29. `registry.py:21-24`：`ToolArgs.approval_detail()` 只有 `bash` 覆写

基类默认给目标路径，六个工具里只有 `bash` 覆写它——一个只有一个实现的钩子。

- 判词：留着到 M5。它现在承担的是「问人的那句话拿什么当主语」这条区分：`bash` 没有目标路径，主语是命令；文件工具主语是路径。
- 处理时点：M5 之后若仍只有 `bash` 覆写，就把它塌成 dispatch 侧的一个函数（`question_for(definition, args)`）并删掉钩子。

## 30. `bash` 的输出按 UTF-8 解码，非 UTF-8 的控制台输出碎成替换字符

`tools/bash_tools.py:83` 的 `stdout.decode("utf-8", errors="replace") + stderr.decode(...)`。M3 人手验收实测到：cmd.exe 上 `ls` 不存在时写的是 GBK 字节，落进日志的是 **34 个 U+FFFD**（`docs/verification/m3-bash-concurrency-timeout-manual.md` 的「别扭与意外」第 2 条）。模型看到的是 `'ls' ??????ڲ???ⲿ???`。

- 判词：M3 不动。规格只保证「命令的输出是结果」，没有规定解码选型；`errors="replace"` 至少保证不抛异常。真正的修法要先决定拿什么当依据——Windows 侧的 OEM 代码页（`cp936`）、`locale.getpreferredencoding(False)`，还是先试 UTF-8 失败再回退——那是选型不是修补，选错会把一种乱码换成另一种。
- 处理时点：M5 或 M6，等 `bash` 的输出成为模型的主要输入面。届时先补一条 seam ③ 判据：一条命令在 Windows 上产出非 UTF-8 字节，断言 `tool/result` 的 content 是可读的中文而不是替换字符。

## 提交纪律：本轮审查查出的三处措辞欠账（不改写历史，只记账）

- `b7534fa`、`7608649`、`90bc02f` 三个 docs 提交的信息里没有门禁那一行。AGENTS.md 的原文是「一次提交算『完成』= 测试、覆盖率地板、`mypy --strict`、ruff 四道全绿」，没有区分代码提交与文档提交。从 10.1 起本轮每个提交的信息里都带门禁实测行；历史提交不改写。
- `788f3b7` 的信息里写「四道门禁跳过（AGENTS.md：门禁那四道是代码提交的门禁）」——括号里那句 AGENTS.md 没有。以仓库文本为准：四道是「一次提交算完成」的定义，规格结构、规格 ↔ 实现、变异测试才是里程碑收尾时跑的。
- `6704997` 的信息里自称「不是编号 task」。AGENTS.md 要求提交信息带 task 编号；那一轮实际做的是「4.1–4.3 落地时埋下的缺陷」的修复，缺的是打包理由而不是编号本身。之后超过 3 个 task 的提交都在信息里写明理由。

Considered options：现在就抽 `SessionSettings` 与 `Literal` 词表（否：M1 的判据已经全绿，改动只增加面不增加证据）；把 `_replay` 的扫描逻辑立刻下沉（否：只有一个消费者，等第二个消费者出现再抽）；M1 就把工具描述写进 `session/start`（否：M1 没有任何工具可写，写了也测不出差异）；M1 就把 `Message` 抽到独立类型模块（否：一个生产者两个消费者，抽出去只是把同一行 import 换个地方）；M2 就把 `approval/request` 改成提问前写（否：会留下「有 request 没 response」的半对，而 M2 词表里没有表达它的取值）；M2 就在派发循环里查取消（否：先要决定未执行的调用怎么写日志，那是扩词表级决定）。

## M8 审查轮：查出的欠账与改判（2026-10-20）

来自 change `m8-runtime-semantics-alignment` 的 `code-review` 两轴审查（固定点 `main`）。处理方式同样是记账；已动的三条写在最后。

- **提交粒度三处超数、没写打包理由**：`7953165`（3.1–3.4）、`39eed49`（2.3 加 4.1–4.5）、`7336791`（5.1–5.5）。AGENTS.md 的原文是「一个提交最多覆盖同一 seam 上相邻的 3 个 task；超过就在提交信息里写明为什么打包」——这三条都超过 3 个 task，信息里只有内容说明、没有打包理由。历史提交不改写。
- **三个 docs 提交没有门禁那一行**：`ddb634a`、`f4328b3`、`71264cf`。与上面「提交纪律」一节同一条规矩：四道门禁是「一次提交算完成」的定义，不分代码与文档。
- **围栏拒绝路径上未派发的调用连 `tool/call` 都不写**（Spec 轴第 2 条）。取消路径 M8 补了 scenario 与判据，围栏路径没有：`stop.is_set()` 在 `begin()` 之前返回，那批后面的调用不落任何记录。它与「每个 `tool/call` 都有配对的 `tool/result`」不冲突（没写调用就没有悬空），但这条形状在 delta 里没有落点，读规格的人要从代码里自己拼出来。处理时点：M10 与第 18 条一起动派发段时补 scenario 与判据。
- **`denial_code` 的裁决依据换成了落盘时序**（Spec 轴第 4 条的一半）。`settle` 里 `if outcome.denial_code is None: outcome.denial_code = ...` 取的是**第一个落盘的**拒绝；M8 之前批次按声明顺序落盘，「第一个」等于「声明里第一个」，M8 之后它等于完成顺序里的第一个。同一批里有两条不同围栏码时 `RunOutcome.failure_code` 取哪一条变成时序依赖，没有判据固定它。处理时点：M10 与第 23 条（`denial_code: FenceCode`）一起收——那一步同时锁类型与定顺序。
- **第 19 条的触发条件已经满足**：`settle`（`turn_loop.py:240`）是第三个「先落盘再决定」的形状——它把 `approval/response` / `tool/result` / `tool/cancelled` / `error/fence` 一次写完，失败就记 failure 并 `stop.set()`。三条同形、失败后的下一步各不相同（`begin` 假 → 这一条不派发；`ask_logged` 假 → 不问人；`settle` 假 → 这一条的结果没落盘）。M8 里合并它们只增加改动面、不增加判据，**改判到 M10 与第 18 条一起收**。
- **第 18 条的账本数字要更新**：`_dispatch_batch` 现在是 `turn_loop.py:138-380` 约 242 行、**八个**闭包（`begin` 176、`ask_logged` 198、`escaped` 223、`settle` 240、`not_dispatched` 303、`abandoned` 318、`one` 327、`dispatch_one` 337），不是「五个闭包、约 210 行」。M8 把落盘时机从批次末改到产出时，新增的 `settle` 与 `not_dispatched` 就是那件事的两半。第 20 条的形状也因此更明显：只读链与会改动链各有一份「拿到额度之后才决定要不要开始」。结论不变，仍在 M10 收。
- **已动的三条**：Spec 轴第 1 条是 delta 措辞写错、实现没错，`session/end` 归内核，措辞已改（REPL 与端点里会话继续归 M6 / M7）。第 3 条是 scenario 后半句没有落点，补了 seam ⑥ 判据 `test_a_log_that_ends_in_aborted_replays_without_a_derived_closer`。第 5 条是实现缺陷，已修（卡在只读并发额度上的调用塌成 `ABORTED_BEFORE_DISPATCH`，见 tasks 9.1）。
- **词表与文档同步**：GLOSSARY 的「闭合记录」自相矛盾（前半句说它让日志完整、后半句说它不落盘），改名成「闭合（closer）」并以读方为准；新开 ADR-0014 记下「闭合是读方派生」这条裁决，ADR-0011 与 ADR-0012 的 `status` 各加一句收窄说明。`events/fold.py` 的常量改名成与值一致的 `TOOL_OUTCOME_UNKNOWN`；测试里的字面量保留——「每个值可达」的判据要写出那个词本身，而 `events` 不 import `tools`（依赖方向是工具读事件），所以两处同名不是可以合并的重复。
