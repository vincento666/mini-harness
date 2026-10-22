# 记账：各里程碑留下的坏味道与设计缺口，到对应里程碑再动

这一条不是待办清单的优先级排序，而是 code-review 修复轮（change `m1-event-log-and-turn-loop` 的 tasks 第 11 节）留下的**账**：审查里确认存在的重复与泄漏，M1 里改它们只会增加改动面、不会增加判据，因此只记账不动代码。任何一条到 M2 都可以按新证据改判——但改判要发生在 M2 的 change 里，不是顺手改。第 9 至 12 条来自 M2（change `m2-file-tools-and-fences`）的 `code-review` 两轴审查，第 13 至 17 条来自 M4（change `m4-real-provider`）的同一轮审查；处理方式同样是记账。M3（change `m3-bash-concurrency-timeout`）的收尾轮对第 1、8 至 17 条逐条改判，判词写在各条末尾：已处理 4 条（1、9、10、11），改判为长期形态 3 条（8、12、16），未处理推到 M5 2 条（14、15），未触发 1 条（17）。第 18 至 29 条来自 M3 的 `code-review` 两轴审查——Standards 轴确认存在但「改它不增加判据」的判断项，加两条规格 ↔ 实现的判断（第 28、29 条）——处理方式同样是记账：八条推到 M5，两条判为不动（25、27），两条按现状留着并写明何时才动（28、29）。第 30 条来自 M3 的人手验收（cmd.exe 的 GBK 输出碎成 U+FFFD），同样是记账。最后一节记提交纪律的三处措辞欠账：历史提交不改写，只把与 AGENTS.md 原文不符的地方更正在这里。它前面那节是 M8 审查轮（2026-10-20）的账：提交粒度三处超数没写打包理由、三个 docs 提交没有门禁行、派发段两条未定形状推到 M10，第 18 与 19 条改判。M5 收尾轮（2026-10-21）把写着「M5」的旧处理时点逐条核实改判：五条推到 M10（19、20、22、26、29，其中 29 的触发条件已成立）、四条推到 M6 / M7（21、24、28、30，其中 30 的条件已成立、解码选型要人裁决）、一条按「不动」结案（25）；另新记第 31 条（单条工具结果的剪枝 → M10）与第 32 条（每回合全量重读日志 → M11）。M9 审查轮（2026-10-21）先当场动三条规格 ↔ 实现的缺口（`--config` 指向目录、配置写错档位跳过工作区边界、file-tools 那条 scenario 缺判据），再新记第 38 至 45 条与提交纪律三处欠账。M6 收尾轮（2026-10-21）当场动三条（第 3 条的装配点下沉进事件层、第 42 条改名、第 45 条撤两个无人用的导出），把写着 M6 时点的旧账逐条核实：已处理 3 条（3、42、45），部分处理 1 条（41），未触发改判 6 条（21、24、28、30、38、40），记实况 2 条（32 被 chat 加重、39 多出一份 `SessionEnv`）；再新记第 46 至 50 条与判据欠账两条。M7 收尾轮（2026-10-22）当场收三条：第 40 条（`ConfigFailure.code` 收成 `Literal` 与词表常量）、第 50 条（`_prepare_or_fail` 返回 `_Prepared | _Failure`）、第 41 条剩下的那一半（取「收窄词条」，装配住在 CLI 层）；把写着 M7 时点的旧账逐条核实：未触发改判 3 条（21、38、39），各自的新的触发条件写在条末。第 30 条按 DSH 结案（DSH 自己就是 lossy UTF-8，mini 两条都照到了），新记第 53 条（输出溢出没有 spill 文件与 `lossy` 标记 → M10）与第 54 条（卡住的 SSE 读者拖慢进程退出 → M10）。M7 的人手验收（同日，`docs/verification/m7-serve-http-sse-manual.md`）再新记第 55 条（溢出那一场几乎没有可连接的窗口，溢出在事件流上长什么样没有判据 → M10）。M7 的 `code-review` 两轴（同日）当场补四条判据缺口——bash 的 lossy UTF-8、`entry` 与 `prompt` 在 seam ⑥、游标「开始送帧」那一半、`--http` 改成人裁决的「保留但可选」并补判据——并新记第 56 至 61 条与提交纪律、判据欠账两节。

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
- **已处理（2026-10-21，M6 任务 5.1 / 5.2）**：`events/fold.py::assembly_points(events)` 落地，返回 `AssemblyPoint(record, prefix, turn_id)`；`cli/main.py::_replay` 不再自己扫 `records` 找 `turn/start`、也不再按 `context/assembled` 的下标切前缀。判据落在 seam ④（`tests/test_context_fold.py`），seam ⑥ 的 replay 判据形状不变。chat 的「按段读回回复」读的是 `read_events` 加词表过滤，不是装配点——它要判的是「哪些 `model/response` 不带 `purpose`」，与装配点是两件事。

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
- **已处理（M9，2026-10-21）**：`loop/settings.py::ProviderEndpoint` 立起来（三条 `str`：`base_url` / `model` / `api_key_env`），`SessionSettings` 上那三条 `str | None` 换成 `endpoint: ProviderEndpoint | None`。payload 没有多一层嵌套——那三个字段仍平铺在 `session/start.payload` 上，只是改由 `if settings.endpoint is not None:` 派生，规格事实未变。取舍见 ADR-0018。

## 15. 「这是 openai 路径」这个判断在四处重复

`cli/main.py` 三处（选 provider、`--fixture` 互斥、payload 那三条填不填）加 `loop/turn_loop.py` 一处（`start_payload` 里加不加那三条）。

- 现在不动的理由：四处各自决定不同的事；抽一个 `is_openai` 布尔只是把判断搬个地方，不减少任何一处。
- M3 / M5 的处理：与第 14 条同源——`SessionSettings` 带一个可选端点对象之后，「是不是 openai」变成「端点在不在」，四处塌成一处。
- **未处理，推到 M5（2026-10-19 核实）**：四处判断仍在四处，M3 一条没动；与第 14 条同源，等端点类型出现一起收。
- **改判到 M9（2026-10-20，ADR-0010 之后）**：与第 14 条一起收在 M9——端点类型由装配引入之后，「是不是 openai」变成「端点在不在」，四处塌成一处。
- **已处理（M9，2026-10-21）**：`turn_loop` 那一处变成「端点在不在」（`if settings.endpoint is not None:`），`cli/main.py` 里「payload 那三条填不填」那一处随端点对象消失——端点在 openai 那一支里构造一次、传给设置一次。命令行剩的那一处 `if provider_name == "openai":` 判的是「选哪个 provider」与「`--fixture` 互斥」，与「payload 填不填」不是同一件事，留着。

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
- **条件成立（2026-10-21，M6 收尾轮）**：请求级压缩之后的那次重试让「一个回合多次请求」成为真实形状——一个回合可以有两条不带 `purpose` 的 `model/request`（`turn_loop.py:587`），还有一条带 `purpose: compaction` 的摘要调用。本轮按人的裁决处理了可读性那一半（ADR-0019：重试之前补一条 `context/assembled`，摘要调用不补、规格写明它的上下文是表层加一条固定指令），`model/request` 仍不带 `attempt`。要不要给 `attempt` 推到 **M10**，与第 51 条同一处收。

## 18. `_dispatch_batch` 一个函数里装着派发段的五件事

`loop/turn_loop.py:138-350` 约 210 行，里面五个闭包：`begin`（176）、`ask_logged`（198）、`escaped`（223）、`one`（240）、`dispatch_one`（250），共用 `calls` / `started` / `finished` / `mutating` / `read_slots` / `outcomes` / `stop` 这批批次状态。取消、超时、围栏、approval 落盘、内核故障五件事都在同一个函数里改（Divergent Change）。

- 现在不动的理由：这些闭包共用的是**一批调用的状态**，抽成模块级函数要把这七份状态传来传去；seam ① 的判据全部从日志外部观察派发结果，抽与不抽对判据没有区别，M3 里抽只增加改动面。
- 处理时点：M5（chat REPL 需要把同一派发段跑在不同外壳里）或出现第二个派发者时。那时先抽的是批次状态（一个 `_Batch`），不是闭包本身。
- **改判到 M10（2026-10-20，ADR-0013 之后）**：本条自己写的触发条件有两处不对——chat REPL 是 **M6** 不是 M5；而 ADR-0013 已把「管线加段 + 派生信号 + `CommandRunner` 缝」定在 **M10**，那正是派发段要动的时候。所以 `_Batch` 与第 23 条（`denial_code: FenceCode`）一起在 M10 收，M6 只收第 3 与第 21 条。

## 19. `begin` 与 `ask_logged` 是同形的

两个闭包都是「`_append_all` 写一条 → 有 failure 就记进 `outcome.failure`、`stop.set()`、返回 `False`」（`turn_loop.py:176-196` 与 `198-221`）。

- 现在不动的理由：两者写的记录类型不同，失败之后的下一步也不同（`begin` 假 → 这一条不派发；`ask_logged` 假 → 不问人）。合并要加一个「失败之后怎么办」的参数，那是为两个调用方加的抽象（编码四规第 2 条）。
- 处理时点：出现第三个「先落盘再决定」的记录时再收（M5 的 REPL 若把 approval 换成异步审批就有第三个）。
- **改判到 M10（2026-10-21，M5 收尾核实）**：M5 没有新增「先落盘再决定」的闭包——压缩那三条记录走既有的 `_append_all` 与 `_provider_error` / `_context_overflow` 形状。第三个形状是 M8 的 `settle`，M8 已把本条改判到 M10，结论不变。

## 20. 只读与会改动的派发链在 `dispatch_one` 里分两段写

`if index > 0: await started[index - 1].wait()` 与 `if mutating[index] or mutating[index - 1]: await finished[index - 1].wait()` 串在一起，读的人要自己拼出「只有一对相邻的只读调用允许同时在跑」。

- 现在不动的理由：这两条 `await` 就是那条规则的直译，而规则本身是 M3 实现期才发现的（design.md 的 D1 落地修正）。收成 `await chain(index)` 会把规则从代码里搬进一个名字，规格 turn-loop 那条 scenario 判的正是这两条 `await` 的可观察结果。
- 处理时点：M5 若并发形状变复杂（只读调用带自己的预算、或出现第三类工具）再抽。
- **改判到 M10（2026-10-21，M5 收尾核实）**：M5 动的是装配之前与装配之内（预算、遮蔽、摘要），派发段这两条 `await` 一条没动，并发形状没有变复杂。与第 18 条一起在 M10 收。

## 21. `registry` / `context` / `approval_gate` / `on_approval_request` 四个入参一路结伴

`dispatch_tool_call(...)` 里后四个每次一起出现（`tools/dispatch.py:41-48`），是 data clump。

- 现在不动的理由：它们就是 seam ② 的接口本身，判据注入的正是这四个的不同组合；收成一个 `DispatchEnvironment` 会让「这条判据注入了哪个门」多一层跳转。
- 处理时点：M5 / M6（REPL 与 serve 各带一套门与上下文时）。
- **改判到 M6 / M7（2026-10-21，M5 收尾核实）**：M5 没给 `dispatch_tool_call` 加入参，也没有第二个派发者。真正「各带一套门与上下文」的是 M6 的 chat REPL 与 M7 的 serve——照本条自己写的第二个读法走。
- **未触发，改判到 M7（2026-10-21，M6 收尾核实）**：M6 的 chat REPL 没有成为第二个派发者，`dispatch_tool_call` 的四个入参一个没变——chat 复用同一个内核环境（`loop/turn_loop.py::SessionEnv` 收 provider / log / registry / settings / approval_gate，门与上下文仍由内核带）。仍等 M7 的 serve 带出第二套。
- **同一结伴在别处又出现一遍（2026-10-21，M6 收尾轮 Standards 轴）**：`SessionEnv` 立起来之后，`_recover_overflowed_request`（`turn_loop.py:534`）仍把 `log` / `settings` / `provider` / `registry` / `cancel` 一个个传一遍，`run_session`（`:938`）的签名仍是六个入参、内部再拼成 `SessionEnv`，`tests/tool_harness.py:269` 又把 `env` 拆回六个入参喂它。本条的「已处理」只成立于 `dispatch_tool_call` 那一半。处理时点不变（**M7**），收的时候把这三处一起收。
- **未触发，改判到 M10（2026-10-22，M7 收尾核实）**：M7 的 serve 不是第二个派发者。它复用同一个内核环境——`run_session(..., entry=ENTRY_SERVE, ...)`，approval 门仍是 `STDIN_APPROVAL_GATE` 那个模块常量；`dispatch_tool_call` 的四个入参一个没变，`run_session` 仍是六个入参，`_recover_overflowed_request` 仍逐个传。serve 带出来的第二套是 **HTTP 侧**的（`cli/serve.py::ServeServer`：监听地址、日志路径、`session_finished` 信号），与派发侧的门与上下文不重叠。新的触发条件：M10 给派发段加东西（可插拔 approval 门、子会话各自的门）时收，收法仍是「三处一起收」。

## 22. 三个名字与实际含义有距离

`_race_with_cancel` 也 race 内核异常（`turn_loop.py:107`）；`MAX_PARALLEL_TOOLS = 8` 实际只约束只读调用（会改动的永远串行，`turn_loop.py:44`）；`_bounded` 做的是「截断并留固定标记」，不是「限制」（`tools/bash_tools.py:23`）。

- 现在不动的理由：改名是纯搬运，判据不受影响；M3 的提交里混进与规格无关的改名会让 `git log` ↔ `tasks.md` 的对应变浑。
- 处理时点：M5 与第 18 条同一处代码动的时候一起改（`MAX_PARALLEL_TOOLS` → `MAX_PARALLEL_READS` 一类）。
- **改判到 M10（2026-10-21，M5 收尾核实）**：M5 没动这三处代码，改名仍是纯搬运。与第 18 条一起，在 M10 动派发段时一起改。

## 23. `denial_code: str | None` 应该是 `FenceCode | None`

`_BatchOutcome.denial_code`（`turn_loop.py:103`）与 `run_session` 里的局部 `denial_code`（`turn_loop.py:390`）是 `str | None`，取值来自 `DispatchOutcome.fence_code`（`FenceCode`）。mypy 挡不住往这两处塞词表外的字符串。

- 现在不动的理由：终点 `RunOutcome.failure_code` 是 `str`（它对应日志里的字段），只锁中间量等于锁一半；M3 里锁它没有新判据。
- 处理时点：M5 与第 5 条（词表 `Literal`）同源一起收。
- **改判到 M10（2026-10-20，ADR-0013 之后）**：与第 18 条一起收在 M10——那一步给 `FenceCode` 加 `SANDBOX_UNAVAILABLE`，围栏码在派发段里流过的地方全都要重看一遍，锁中间量与加词表值是同一次改动。第 5 条（`stop_reason` / `outcome` / `role` 的 `Literal`）照旧在 M5 收，那里 `StopReason` 要加 `CONTEXT_WINDOW_EXCEEDED`。

## 24. `ApprovalAsked | None` 是一个「可以没有」的钩子

`dispatch_tool_call` 的 `on_approval_request` 可选（`tools/dispatch.py:46`）；不传时 `approval/request` 不落盘，也就是 D12 那条规格在这个调用方身上不成立。实现里唯一的调用方（回合循环）永远传。

- 现在不动的理由：可选是为了 seam ②③ 的判据能单独跑 `dispatch_tool_call`（不建日志也能判围栏与门）。改成必填会让那批判据都要造一份日志。
- 处理时点：M5。若「不传就少写一条记录」这个形状造成真 bug，再改成必填或换成显式的 NoOp。
- **未触发，改判到 M6（2026-10-21，M5 收尾核实）**：M5 没动 `on_approval_request`，它也没造成 bug；回合循环仍是唯一调用方。第二个调用方是 M6 的 chat REPL，那时再判必填还是显式 NoOp。
- **未触发，改判到 M7（2026-10-21，M6 收尾核实）**：M6 没有第二个调用方——chat 走的是同一个 `run_turn_segment`，`on_approval_request` 仍是内核传进来的那个。

## 25. `tests/tool_harness.py` 的 `workspace` / `session_dir` 两个旋钮

`run_session_fixture(..., workspace=None, session_dir=None)` 两个可选参数默认都是 `tmp_path`；只有少数判据用它们（两个档位对 `bash` 那条要两个 session 各一个目录，「日志变得不可写」那条要在跑之前先把日志建出来）。

- 现在不动的理由：用它们的判据都有结构性理由；少一个旋钮就要多一处手搓 `SessionSettings`，那正是第 1 条刚收掉的东西。
- 处理时点：不动。M5 若 session 目录成为一等概念，跟着那时一起改。
- **未触发，按「不动」结案（2026-10-21，M5 收尾核实）**：M5 加的是 `--window` / `--reserve` 两个旋钮，没有让 session 目录成为一等概念（`--session-dir` 早就是 CLI 参数）。用这两个旋钮的判据仍有结构性理由。

## 26. `tool_harness` 的两个 `wrap` 闭包逐字段重建 `ToolDefinition`

`timed_registry` 与 `serialized_registry` 里的 `wrap`（`tests/tool_harness.py:59` 与 `83`）都把 `ToolDefinition` 的五个字段抄一遍再换 `run`。

- 现在不动的理由：`dataclasses.replace(definition, run=...)` 一行能替，但 M3 里改它没有任何判据变化，只是测试内部形状。
- 处理时点：M5 顺手（与第 22 条一起）。
- **改判到 M10（2026-10-21，M5 收尾核实）**：「顺手」与编码四规第 3 条冲突，M5 照第 3 条没动它。与第 22 条一起在 M10 收。

## 27. `bash_tools.py` 两处平台判断方向相反

`_terminate_tree` 里 `if sys.platform == "win32":`（`tools/bash_tools.py:41`，`taskkill /T /F /PID`）与启动处 `if sys.platform != "win32":`（`tools/bash_tools.py:61`，`start_new_session=True`）。

- 现在不动的理由：两处都必须是字面量比较，`mypy --strict` 才会剪掉另一侧的 `killpg` / `getpgid` / `SIGKILL`——抽成 helper 函数不剪（M3 实测过，见 `docs/lessons.md`）。两个方向相反是用途不同（终止 vs 启动参数），不是笔误。
- 处理时点：不动。这是平台分支的长期形态，代价写在 ADR-0009 与 design.md 的 D9（两端各拉低一半覆盖率）。

## 28. `dispatch.py:73-79`：approval 记录写不进日志时塌成 `TOOL_IO_FAILED`

规格没有这条，实现有：`on_approval_request` 报告写不进去时直接返回 `TOOL_IO_FAILED`，不去问人。这一行未覆盖（`docs/CURRENT.md` 的未覆盖清单里）。

- 判词：留着。它是 D12「`approval/request` 在提问之前落盘，写不进去就不问人」的另一半，`TOOL_IO_FAILED` 是既有词表里最贴近的取值，没有为它新造取值。规格侧的对应物是 event-log 那条「提问之前落盘」；「写不进去时得到哪个结果词」目前没有规格，也没有判据需要它。
- 处理时点：M5 之后若这条变成要判的行为，再在 event-log 的 delta 里写明结果词。
- **未触发，改判到 M6 之后（2026-10-21，M5 收尾核实）**：M5 没让这条变成要判的行为——压缩与 approval 落盘没有交集。M6 的 REPL 把 approval 变成对话里的一问一答，那时才可能判它。
- **未触发，改判到 M7（2026-10-21，M6 收尾核实）**：M6 的 chat 没有把 approval 变成 stdout 上的一问一答。实况是 `tools/fences.py::StdinApprovalGate`：问题写 **stderr**、回答读 tty 上的 stdin，非 tty 直接 `UNAVAILABLE`。chat 的「stdout 只有模型回复正文与提示符」因此不受影响，这条仍未变成要判的行为。

## 29. `registry.py:21-24`：`ToolArgs.approval_detail()` 只有 `bash` 覆写

基类默认给目标路径，六个工具里只有 `bash` 覆写它——一个只有一个实现的钩子。

- 判词：留着到 M5。它现在承担的是「问人的那句话拿什么当主语」这条区分：`bash` 没有目标路径，主语是命令；文件工具主语是路径。
- 处理时点：M5 之后若仍只有 `bash` 覆写，就把它塌成 dispatch 侧的一个函数（`question_for(definition, args)`）并删掉钩子。
- **条件成立，改判到 M10（2026-10-21，M5 收尾核实）**：M5 之后六个工具里仍只有 `bash` 覆写它，触发条件成立。但 M5 的实现没有动 `dispatch.py`，此刻塌这个钩子只增加改动面、不增加判据（编码四规第 3 条）。M10 重做管线时与第 18 / 21 条一起收。

## 30. `bash` 的输出按 UTF-8 解码，非 UTF-8 的控制台输出碎成替换字符

`tools/bash_tools.py:83` 的 `stdout.decode("utf-8", errors="replace") + stderr.decode(...)`。M3 人手验收实测到：cmd.exe 上 `ls` 不存在时写的是 GBK 字节，落进日志的是 **34 个 U+FFFD**（`docs/verification/m3-bash-concurrency-timeout-manual.md` 的「别扭与意外」第 2 条）。模型看到的是 `'ls' ??????ڲ???ⲿ???`。

- 判词：M3 不动。规格只保证「命令的输出是结果」，没有规定解码选型；`errors="replace"` 至少保证不抛异常。真正的修法要先决定拿什么当依据——Windows 侧的 OEM 代码页（`cp936`）、`locale.getpreferredencoding(False)`，还是先试 UTF-8 失败再回退——那是选型不是修补，选错会把一种乱码换成另一种。
- 处理时点：M5 或 M6，等 `bash` 的输出成为模型的主要输入面。届时先补一条 seam ③ 判据：一条命令在 Windows 上产出非 UTF-8 字节，断言 `tool/result` 的 content 是可读的中文而不是替换字符。
- **条件成立，改判到 M6（2026-10-21，M5 收尾核实）**：M5 之后工具输出确实是模型的主要输入面——人手验收里那条 55118 字符的 `tool/result` 正是被遮蔽的东西，窗口预算量主要就是量它。但解码选型（OEM 代码页 / `locale.getpreferredencoding(False)` / 先试 UTF-8 失败再回退）是选型不是修补，**要人裁决**；M6 让工具输出直接进对话，在那之前定下来。判据形状照原文那条写。
- **未处理，改判到 M7（2026-10-21，M6 收尾核实）**：M6 让工具输出直接进对话（chat 的 stdout 不打印它，但它进上下文、进预算），条件更成立了，可解码选型仍**要人裁决**——三条读法各自的失败模式不同，agent 不许自己选。M7 的 serve 会把工具输出送到人的屏幕上，届时必须定。
- **按 DSH 结案（2026-10-22，M7 任务 8.2）**：不用裁决了——DSH 自己就是 lossy UTF-8。子进程输出走 `dsh-subprocess-local/lib/output.js:193` 与 `:232` 的 `Buffer.toString("utf8")`（Node 对非法字节产出 U+FFFD），文件读走 `dsh-fs-local/lib/index.js:333` 的 `new TextDecoder("utf-8", { fatal: true })`（非法字节是错误）。mini 两条都照到了：`tools/bash_tools.py` 对子进程输出用 `errors="replace"`，`tools/file_tools.py` 对文件读用 `read_text(encoding="utf-8")` 并把 `UnicodeDecodeError` 收成一条结果。cmd.exe 的 GBK 输出碎成 U+FFFD 因此不是 mini 的缺口，是这一层共同的形状。真正的差在溢出那一侧——新记第 53 条。

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

## M5 审查轮：两条新账（2026-10-21）

来自 change `m5-context-budget-compaction` 的实现期与收尾轮。同样是记账，不动代码。

### 31. 单条工具结果的剪枝没有做：M5 只遮蔽整段

M5 的压缩遮蔽的是**一段历史**。DSH 还做另一件事，mini 版没有：把**单条**过大的工具结果就地剪短（它的 pruner 是 `thresholdChars 8192` / `headChars 4096` / `tailChars 1024`，剪枝记录同样带 `shadowedRange`）。mini 版现在的形状是：一条 55118 字符的 `tool/result` 会整条留在表层，直到某次压缩把包含它的整段遮蔽掉——在那之前它每次都进上下文、每次都算进预算。

- 记账不动的理由：M5 的规格只要求「窗口预算 + 遮蔽 + 溢出」三件事；把剪枝塞进来会让「遮蔽范围」与「单条结果的内容」两件事混在同一条 delta 里，判据也要跨两层写。
- 处理时点：**M10**。ADR-0013 给管线加的「内容收尾（截断与归一化由工具定义自己负责）」正是它的落点。届时先补 seam ② 判据：一条超阈值的工具结果落进日志的是「头部 + 标记 + 尾部」，且折叠读到的与日志里写的一致。

### 32. 回合循环每回合全量重读日志，而压缩让日志变长

每次装配都 `read_events(log.path)` 读全量，再 `fold()` 全量折叠，`shadowed_range()` 与预算校准又各扫一遍。M5 之前日志长度只随回合数增长；M5 之后一次压缩多写三条记录（`model/request` / `model/response` / `compaction/summary`），而被遮蔽的记录仍在文件里、仍要在全量扫描里被跳过。

- 记账不动的理由：没有判据需要它变，且当前量级（一个会话几十条记录）测不出差别；先做增量读会把 replay 依赖的「任何前缀可重算」这条形状改松。
- 处理时点：**M11**（日志读取与投影层）。那时先看「增量读 + 已算过的遮蔽范围可复用」能不能立成一个读方接口，再决定全量重读是否只留作 replay 的实现。
- **M6 让它更重（2026-10-21，M6 收尾核实）**：chat 每跑完一段就 `read_events(log.path)` 全量读一次再打印新回复（`cli/main.py::_print_new_replies`），一次会话的全量读次数从「回合数」变成「回合数 + 段数」。没加判据、也没改实现，只是记实况：M11 那条读方接口现在要多回答一个问题——「回复正文的投影能不能也从同一个读方拿」。

## M5 两轴审查轮：已动的与四条新账（2026-10-21）

同一 change 的 `code-review` 两轴（固定点 `main`）。先记已动的三条，再记账。

- **溢出收尾的日志重放**：实现把「没有任何 `context/assembled`」判成 `REPLAY_MISMATCH` 退出码 1，而 delta 规格那条 scenario 写的是退出码 0。人裁决改实现——溢出与取消都能在第一次装配之前把回合收掉，那是合法日志，不是损坏日志；replay 现在打印一行「没有装配点」的说明、不打印最后一次装配的上下文，并以退出码 0 结束。那条守卫原本没有任何测试守着（全仓 grep 无判据），这也是它能悄悄存在到 M5 的原因。
- **provider 超限的判定范围**：规格写「状态码 400」，实现是「4xx 里看 `error.code`」。人裁决改规格措辞并补 413 的 scenario 与判据：线上的事实是那个 code。顺带核出一处审查报告没说准的地方——重试耗尽的 5xx 与 429 在实现里更早返回（`openai_compat.py:261`），带同一个 code 也**不会**塌成溢出；这条现在写进规格正文。
- **design D2 与测试策略表**：D2 原写「送被遮蔽那段」，实现送整份表层；表里 seam ⑥ 的落点是一份不存在的 `test_cli_budget.py`。两处都是措辞与实况分叉，已按实况更正，`tests/test_context_budget.py` 的 docstring 也不再自称 seam ①。

### 33. 「遮蔽范围」在代码里是一个 dict：M5 记账，M11 收

GLOSSARY 立了「遮蔽范围」这个词，代码里它是 `dict[str, int]`（`shadowed_range` 产出、`fold.shadowed_seqs` 又用 `isinstance` 把它解析一遍），`compaction/summary` 的 payload 也带同名键。基线里的 Primitive Obsession 与 Data Clumps 都指到这里：它值得一个小类型。

- 记账不动的理由：现在只有一个产出方和一个读方，改名与加类型要连 payload 形状、replay 的逐字段比对、以及 `test_context_budget.py` 的十几条断言一起动。
- 处理时点：**M11**（投影层）。届时遮蔽范围是投影层的输入，类型自然要立。

### 34. 「这条记录是不是摘要回复」在五处各判一遍

`purpose == PURPOSE_COMPACTION` 加上 `event.type` 的同一套判断出现在 `budget._record_chars`、`budget._produces_message`、`budget.budget_reading` 与 `fold._body_message`。基线里的 Repeated Switches 与 Duplicated Code。

- **第五处（2026-10-21，M6 任务 6.9）**：`cli/main.py::_print_new_replies` 判的是「这条 `model/response` 是不是给人的回复」，谓词换成了 `"purpose" in event.payload`——不是等于 `PURPOSE_COMPACTION`。词表里 `purpose` 目前只有 `compaction` 一个值，两种写法现在等价；一旦有第二个用途（M7 之后可能的进度摘要），这五处里有一处的语义会和另外四处分开。
- 记账不动的理由：四处都属于「读方怎么看待一条记录」，正确的收法是把这条谓词放到事件层（或投影层的一个读方接口），而 M5 只允许 fold 加读方规则、不允许动事件层的形状。
- 处理时点：**M11**。与第 33 条同一处收。

### 35. 预算模块在重建工具往返的配对，而那份知识住在折叠里

`budget._round_owner` 与 `_round_end` 从 payload 里重建 `tool_call_id → assistant 记录` 的配对，这件事 `fold.py` 已经会做（`_call_id_of` 与它的 pending 表）；且 `_round_end` 每次调用重建一份 `by_seq`，在 `shadowed_range` 的 while 循环里是 O(n²)。基线里的 Feature Envy。

- 记账不动的理由：判据只要求「切点不拆散一组工具往返」，没有一条判据需要这份配对来自折叠；当前量级（几十条记录）下 O(n²) 测不出差别。
- 处理时点：**M11**。若第 32 条的「增量读 + 可复用的遮蔽范围」立成接口，这份配对自然由那个接口提供。

### 36. `retain_line` 这个名字没说它是「保留尾部的预算额度」

基线里的 Mysterious Name，轻。函数返回的是保留预算（token 数），名字读起来像一条 seq 线。

- 记账不动的理由：改名要连 19 条判据、design D4、GLOSSARY 与 `docs/CURRENT.md` 一起动，M5 收尾轮不该为一条命名账跑这些。
- 处理时点：**M11**，与第 33 条一起顺手收。

### 37. provider 报 `PROVIDER_ABORTED` 时塌成 `PROVIDER_ERROR`：未决

`openai_compat.py:222` 与 `:250` 会在取消信号已置位时返回 `PROVIDER_ABORTED`；回合循环把任何 provider 失败都走 `error/model` + `PROVIDER_ERROR` + 退出码 1。而主规格与 M5 的 scenario 都说「内核置位取消时走的是 `error/abort` 与退出码 5」。当前没有生产路径会撞上它（回合循环在调 `generate` 之前就先看取消），所以 `docs/CURRENT.md` 记的是「有词表值与判据、没有生产路径」。

- 记账不动的理由：把它塌成 `ABORTED` 要决定「provider 自己报的取消」与「内核置位的取消」是不是同一件事，那是 M10 派生信号与执行段立缝时的裁决。
- 处理时点：**M10**（ADR-0013 的执行段）。

### 提交纪律的两处欠账（历史提交不改写，只记账）

- `251e093` 打包了 task 7.1–7.7，跨 seam ⑥ 与 ②，**没有写打包理由**——违 AGENTS.md「一个提交最多覆盖同一 seam 上相邻的 3 个 task；超过就写明理由」。当时能写的真实理由是「7.5 与 7.7 是把组 5 已经打通的形状钉成 seam ⑥ 与 ② 的判据，拆开会产出只有断言没有实现的提交」，但这句话当时没写进提交信息。
- `a91a2d2` 自述「组 2 的六条判据是一次写完再实现的」——违「一条判据先红、再绿，一次一个切片」。它当时已诚实写在提交信息里，且组 3 起恢复交替；记在这里是为了让下一轮不再靠自述补救。
- 本轮（组 9）新增的两条判据里，413 那条写出来就是绿的（实现早已如此），按纪律写明它不是红绿对、是把「已经成立」钉成判据。

## M9 两轴审查轮：已当场动的与八条新账（2026-10-21）

同一 change 的 `code-review` 两轴（固定点 `main` = `338319e`，12 个提交）。先记已动的四条，再记账。

- **`--config` 指向目录或读不动的路径**：`load_config` 原本只 catch `FileNotFoundError` 与 `tomllib.TOMLDecodeError`，指向目录走的是 `PermissionError` → traceback、退出码 1、没有 `INVALID_ARGUMENT`。违 cli delta「配置层失败都在 session 开始之前」与 config-layering「配置文件不是合法 TOML……退出码 2」。当场补 `except OSError` → `CONFIG_NOT_FOUND`（detail 指路径与原因），判据 `test_a_config_path_that_is_not_a_file_is_an_argument_error` 先红后绿。
- **配置写错档位跳过工作区边界那一支**：`fences.py` 按 `== "read-only"` / `== "workspace-write"` / `== "ask"` 判定，所以配置里 `sandbox = "banana"` 两条都不成立、边界那一支整个跳过，**等价 `danger-full-access`**；`approval = "yolo"` 落到不问人。比 ADR-0018 原先那句「写错档位会一路走到运行期」重，已按实况改写 ADR-0018 的 Consequences。当场在 CLI 加词表判据（退出码 2、`INVALID_ARGUMENT`），词表 `SANDBOX_LEVELS` / `APPROVAL_MODES` 立在 `loop/settings.py`，argparse 的 `--sandbox` 的 `choices` 改用它（原来命令行与设置层各写一遍）。判据 `test_a_fence_level_outside_the_vocabulary_is_an_argument_error` 先红（`sandbox` 那一例 `assert 0 == 2`）后绿。
- **file-tools delta 的 scenario「被白名单筛掉的文件工具不在工具表里」没有任何判据**：实现本来就对，判据缺一半（只有 turn-loop 的空白名单那条）。补 `test_a_builtin_tool_filtered_out_by_the_whitelist_is_unknown`（seam ①，写出来就是绿的：白名单 `["read"]` 加一次 `grep` 调用 → `UNKNOWN_TOOL`、两条 `turn/end`、`MODEL_COMPLETED`）。
- **design D1 的签名与实况分叉**：D1 写 `layer_settings(args, config) -> SessionSettings | ConfigFailure`，实现返回新立的 `EffectiveSettings` 且永不返回 `ConfigFailure`，下界与词表判断留在 `cli/main.py`。已在 design.md 的 D1 下补一段「实现时的改判」写明形状与理由，代价记在下面第 39 条。

### 38. 可配字段名四处平行列出：`add_argument` / `BUILTIN_DEFAULTS` / `SETTINGS_FIELDS` / `EffectiveSettings`

13 个字段名在四处各写一遍，加一个字段要改四处，漏哪处工具看不见——`layer_settings` 用 `getattr(args, name, None)` 与 `EffectiveSettings(**values)`（`dict[str, Any]`），mypy strict 全程不拦，「键名逐字相同」只写在注释里。基线里的 Shotgun Surgery 与 Primitive Obsession 指同一处。

- 记账不动的理由：正确的收法是一份字段表当唯一来源、argparse 与 dataclass 都由它生成；那要把 CLI 的参数表从声明式改成生成式，M9 的判据面不因此多一条。
- 处理时点：**M6**（REPL 要复用同一份设置面时最疼）。
- **未处理，改判到 M7（2026-10-21，M6 收尾核实）**：M6 把「参数表」收成一份（`cli/main.py::_add_shared_flags`，`run` 与 `chat` 都 `parents=[shared]`），chat 一个新 flag 也没加；可那四处平行列出的字段名一处没少——加一个可配字段仍要改四处，mypy 仍不拦。M7 的 serve 复用同一份参数表时再收。
- **未处理，改判到 M10（2026-10-22，M7 收尾核实）**：M7 的 serve 复用同一份参数表（`parents=[shared]`），新加的两个 flag `--host` / `--port` 是 CLI-only、不进配置文件（ADR-0021 D4），所以四处平行列出的字段名一处没多、也一处没少——加一个**可配**字段仍要改四处，mypy 仍不拦。新的触发条件：M10 往配置文件加新字段（可插拔 approval 门、spill 阈值）时收；收法不变——一份字段表当唯一来源，argparse 与 dataclass 都由它生成。

### 39. `EffectiveSettings` 与 `SessionSettings` 字段高度重叠

层叠产出一份、日志字段表要另一份，两份的字段几乎同名同型。基线里的 Data Clumps。

- 记账不动的理由：让层叠直接产出 `SessionSettings` 会把「日志字段表」与「三层取值」绑死（design D1 的改判理由）；合并要连 `session/start.payload` 的字段表一起动。
- 处理时点：**M6**，与第 38 条同一处收。
- **未处理，改判到 M10（2026-10-21，M6 收尾核实）**：M6 没合并它们，反而新立第三份——`loop/turn_loop.py::SessionEnv`（provider / log / registry / settings / approval_gate，会话内冻结）。字段重叠从两份变三份，但三份各自回答不同的问题（三层取值 / 日志字段表 / 会话内不变的能力集）。M10 动派发段时与第 18、21、23 条一起看。
- **第四份，且它 ≡ 第三份的前四个字段（2026-10-21，M6 收尾轮 Standards 轴）**：`cli/main.py::_Prepared`（provider / settings / log / registry）与 `SessionEnv` 只差 `approval_gate`；`_run` 与 `_chat_session` 拿到 `_Prepared` 之后立刻把它拆开、再拼成 `SessionEnv`。基线里的 Data Clumps 加 Middle Man。
  - 记账不动的理由：`_Prepared` 是「装配成功」这个事实的名字，`_prepare_or_fail` 靠它把 12 处失败分支收在一处；把它直接换成 `SessionEnv` 要让 CLI 层知道 `approval_gate` 从哪来（现在是 `STDIN_APPROVAL_GATE` 那个模块常量）。
  - 处理时点：**M10**，与本条上面那半一起收；M7 的 serve 会带来第五份候选（HTTP 请求带自己的门与上下文），那时再定收法。
- **第五份候选没有出现，改判到 M10（2026-10-22，M7 收尾核实）**：本条预言的那一份没出现。serve 的会话材料仍是 `_Prepared`（provider / settings / log / registry），`cli/serve.py::ServeServer` 带的是 HTTP 侧的三样（host / port、日志路径、`session_finished` 信号），与那四份字段不重叠；`_Failure`（M7 任务 7.2）是失败结果，不是第五份设置面。四份各自回答的问题不变（三层取值 / 日志字段表 / 会话内不变的能力集 / 装配成功）。新的触发条件：M10 给每个会话各自的 approval 门或 spill 阈值时，第五份才会出现。

### 40. `ConfigFailure.code` 是裸 `str`，没有 `Literal` 与词表常量

六个值各有可达性判据（`test_every_config_failure_code_is_reachable`），但没有类型。与第 5 条同族（`stop_reason` / `outcome` / `role`）。

- 记账不动的理由：加 `Literal` 要先决定「CLI 层的 `INVALID_ARGUMENT` / `UNKNOWN_PROVIDER` 与这六个是不是同一张词表」，而那张对外失败码表 M9 没有判它。
- 处理时点：**M6 / M7**（失败码表要对外稳定、REPL 与 serve 要复用那张表时）。
- **未处理（2026-10-21，M6 收尾核实）**：M6 让 chat 复用同一套失败码（`_prepare_or_fail` 与 `run` 走同一条 `_report_failure`），可那张表仍是散在 `cli/main.py` 里的字符串，`ConfigFailure.code` 仍是裸 `str`。M7 立 serve 时收。
- **已处理（2026-10-22，M7 任务 7.1）**：`config/load.py::ConfigCode = Literal[六个值]`、`CONFIG_CODES = frozenset(get_args(ConfigCode))`，`ConfigFailure.code` 是 `ConfigCode`；可达性判据从「硬编码六个」改成「跑出来的集合 == `CONFIG_CODES`」——往词表加一个取值而没人能跑到它，那条就红。本条当初那个前置问题按现状答：CLI 层的 `INVALID_ARGUMENT` / `UNKNOWN_PROVIDER` **没有**并进来，配置层那张表只管配置层。剩下的那一半（对外失败码表）仍是散在 `cli/main.py` 的字符串；新的触发条件：M10 要把失败码对外承诺（HTTP 侧回码、spill 阈值报错）时立那张表。

### 41. 「装配」这个词在 GLOSSARY 里是五步，在代码里只有一步住在 `config/`

`config/assembly.py` 只装工具表；发现 / 层叠 / 选 provider / 建设置四步住在 `cli/main.py::_run`，`_run` 因此因四个原因被编辑（基线里的 Divergent Change + Mysterious Name）。

- 记账不动的理由：M9 的判据全在 seam ② 与 ⑥，把 `_run` 的装配段抽出来不增加判据，只搬代码。
- 处理时点：**M6**——REPL 进来时要么把 `_run` 的装配段抽进 `config/`，要么把 GLOSSARY 那个词收窄成「工具表与设置的产出」，二者取一。
- **部分处理（2026-10-21，M6 任务 6.1）**：两个读法都没选，选的是第三个：装配段从 `_run` 抽成 `cli/main.py::_prepare_or_fail`，`run` 与 `chat` 共用它，`_run` 因此不再是「因四个原因被编辑」的那个函数。可装配仍住在 CLI 层，GLOSSARY 的「装配」仍是五步。剩下的那一半（抽进 `config/` 还是收窄词条）改判到 M7——serve 是第三个消费者，那时才有证据说它属于哪一层。
- **剩下的那一半在 M7 收，取「收窄词条」（2026-10-22，M7 任务 7.3）**：serve 是第三个消费者，证据够了。`_prepare_or_fail` 吃的是 `argparse.Namespace`，`config/layering.py::layer_settings` 直接读 CLI 参数与配置文件两份——把它抽进 `config/` 要让配置层认识 argparse，而配置层现在不认识。裁决：装配住在 CLI 层，`config/` 只装工具表与层叠；GLOSSARY 的「装配」补上这一句（五步不变，写明它住在哪、三个入口共用同一条）。Divergent Change 那一半已随 `_prepare_or_fail` 结案，Mysterious Name 随词条收窄结案。

### 42. `build_registry(names)` 的 `names` 没说它是白名单

基线里的 Mysterious Name，轻。

- 处理时点：**M6** 顺手改名 `whitelist`。
- **已处理（2026-10-21，M6 收尾）**：`config/assembly.py::build_registry(whitelist)`，docstring 同步。十个调用点全是位置参数，没有一处跟着改。

### 43. `_FakeEndpoint` 与 `ProviderEndpoint` 共用「端点」这个词

测试里那个是一个真在监听的服务端，实现里那个是端点的三条事实。GLOSSARY 的「端点」指的是后者。

- 处理时点：下次动 `tests/test_cli_provider.py` 时改名 `_FakeServer`。

### 44. seam ⑥ 的配置判据里的三处重复

`tests/test_cli_config.py` 19 条判据里同一串 `_cli(... --fixture HELLO_SCENARIO ...)` 出现 21 次、`INVALID_ARGUMENT` 12 次、「没有日志」19 次且两种拼法（`tmp_path.glob` 与 `(tmp_path / "sessions").glob`）；`_session_records` 在 `test_cli_config.py` 与 `test_cli_provider.py` 各一份、返回类型还不同。与第 4 条（三个测试文件各一份 `_cli`）同形。

- 记账不动的理由：黑盒判据的可读性靠每条把命令行与断言写全；收成 helper 会让「哪条判据判什么」变模糊。两种「无日志」拼法里只有 6.2 那条用全树快照，那是它要钉的形状。
- 处理时点：与第 4 条同一处收（测试面整理那一轮）。

### 45. `CONFIG_FILE_NAME` 与测试里硬写的 `"mini.config.toml"` 有两个家

`config/__init__.py` 导出的 `CONFIG_FILE_NAME` 与 `EffectiveSettings` 包外无人用，测试里 20 处硬写那个文件名（基线里的 Speculative Generality + Duplicated Code）。

- 记账不动的理由：测试硬写文件名是刻意的——它判的是「CLI 真去找这个名字」，从常量读就等于让判据跟着实现走。真正多余的是那两个包外无人用的导出。
- 处理时点：**M6**（有人用就用，没人用就从 `__all__` 撤掉）。
- **已处理（2026-10-21，M6 收尾）**：M6 没有成为使用者，两个包外无人用的导出（`CONFIG_FILE_NAME`、`EffectiveSettings`）从 `config/__init__.py` 的 import 与 `__all__` 撤掉；测试仍硬写文件名，判据仍跟着命令行走。

### M9 审查轮的提交纪律欠账（历史提交不改写，只记账）

- `22e8480`、`ada6446` 两个提交的信息里没有门禁那一行——与上面「提交纪律」那节和 M8 那节同一条规矩（四道是「一次提交算完成」的定义，不分代码与文档），本轮是第三次。
- `7b5e6c8` 的信息自述「门禁数字记在下一条提交里」——四道确实在那个提交之前跑过，但证据不对应该提交。
- 变异编号 1–9 跑的是受影响的三到四个测试文件，不是全量。编号 10–13 跑全量，其中层叠顺序、白名单被忽略、密钥判据、端点派生四条等于把 1–9 里的对应变异在全量下重跑了一遍；编号 2（配置层整个删掉）、8（工作区根那份不认）、9（未知名不判）三条没有全量复跑。AGENTS.md 的原文是「收尾跑一轮变异测试……跑全量测试」：收尾那轮合规，中途那九条是额外动作，记在这里以免下一轮把「定向轮」当成合规做法。

## M6 审查轮：已动的与七条新账（2026-10-21）

来自 change `m6-chat-repl` 的实现期与收尾轮。已动的三条记在上面第 3、42、45 条的「已处理」行里，这里记账。

### 46. chat 的 stdout 是「每段跑完读回日志再打印」的投影，不是流式

模型回复要等整段跑完才出现；段进行中人只看到上一个提示符之后的空白。工具事件（`tool/call` / `tool/result`）在 chat 的 stdout 上没有任何投影。

- 记账不动的理由：M6 的规格只判「stdout 上有什么」，不判「什么时候到」；做流式要先有进度投影的形状，那是 M7 的 serve SSE 顺带产出的东西。
- 处理时点：**M7 之后**（proposal 的「明确不做」里写明工具事件的终端投影归 M7 之后）。

### 47. 取消事件住在段，不在会话：design D2 与实现分叉

D2 把 `cancel` 列在冻结的会话环境成员里，实现把它做成 `run_turn_segment` 的段级入参——一个会话一份 `asyncio.Event` 做不到「取消当前段、会话继续」：置起之后没有地方把它放回去。design.md 的 D2 已按实况更正。

- 处理时点：**M10**（ADR-0011 / ADR-0013 的执行段给取消加派生信号时重新定它的归属）。

### 48. 审批的 stdin 读取与 REPL 的 stdin 读取是同一条流

`tools/fences.py::StdinApprovalGate._await_readline` 起一个 daemon 线程读 stdin；chat 的 REPL 在主线程阻塞 `sys.stdin.readline()`。平时不冲突——提问发生在段内，那时 REPL 不在读。可取消恰好落在「等人回答」那一刻时，`_race_with_cancel` 放弃那个 await，daemon 线程仍挂在 stdin 上：它和 REPL 之后谁先读到那一行，没有判据说它属于谁。

- 记账不动的理由：M6 的取消判据不含「取消落在等人回答期间」，要判它要先有协作式取消的完整形状。
- 处理时点：**M10**。

### 49. DSH 做了、mini 版没做的两件事

- **压缩失败继续这个 turn**：DSH 的 `agent/pre-step` 里压缩抛错只 `logger.warn(... continuing the turn)` 再 `next()`；mini 的压缩失败塌成溢出结果（ADR-0019）。处理时点：**M10 / M11**。
- **输入排队**：DSH 的 Agent 有 `next-turn` / `next-step` 两个队列，跑着的时候来的输入不丢；mini 的 chat 在段跑着时读不到新输入（stdin 的读发生在段之后）。处理时点：**M7 之后**——serve 把「跑着的时候来一条输入」变成真实形状时再看。

### 50. `_prepare_or_fail` 既打 stderr 又返回退出码，返回类型是 `_Prepared | int`

装配函数报告失败并交出退出码，调用方要 `isinstance(prepared, int)` 才知道走不走得通。与第 40 条同族（失败码表散在 CLI 层）。

- 记账不动的理由：抽它是为了让 `run` 与 `chat` 共用同一条装配路，12 处失败分支不写两遍；改成 `Prepared | Failure` 要先有那张对外失败码表。
- 处理时点：**M7**，与第 40 条同一处收。
- **已处理（2026-10-22，M7 任务 7.2）**：`_prepare_or_fail` 返回 `_Prepared | _Failure`，`_Failure` 带 `code` / `detail` / `exit_code`，函数自己不再打 stderr；`run` / `chat` / `serve` 三处 `isinstance(prepared, _Failure)` 之后各自 `_report_failure`。当初那句「要先有那张对外失败码表」按现状答：不需要——`_Failure` 装的是码本身，不要求码先收成词表（第 40 条只收了配置层那六个）。既有失败判据一条没改、不变绿（382 passed / 5 skipped，TOTAL 95%）。

### 51. `SegmentOutcome` 兼任会话级的失败结果

`end_session` 返回 `SegmentOutcome | None`（`turn_loop.py:930`），`run_session` 的三条失败路都靠 `_run_outcome`（`:149`）把它转成 `RunOutcome`；「这一段是不是失败了」靠 `segment.stop_reason not in STOP_REASONS` 判（`:963`）。`SegmentOutcome` 与 `RunOutcome` 只差一个 `session_id`。基线里的 Mysterious Name，也与第 6 条「扩 `RunOutcome` 而不是新加并列结果类型」相冲。

- 记账不动的理由：M6 需要「跑完一段」这个中间结果，那时会话还没结束、`RunOutcome` 还不成立；把两者收成一个带 `scope` 的结果类型要连着改 seam ① 与 seam ⑥ 的判据形状。
- 处理时点：**M10**，与第 17 条的 `attempt` 那一半同一处收。

### 52. `_compact_if_over_line` 的 `None` 有两种含义

它返回 `None` 只说「没失败」——「没有可遮蔽的内容」也返回 `None`。于是两处调用方（`turn_loop.py:572` 与 `:804`）都要回读全量日志、扫「这一回合有没有一条 `compaction/summary`」才知道到底压没压。基线里的 Primitive Obsession 加 Duplicated Code，并加重第 32 条的全量重读。

- 记账不动的理由：让它返回「压了 / 没压 / 失败」三态要新造一个结果类型；M6 里这两处判定各一行、判据都在（`test_overflow_when_nothing_can_be_shadowed` 与 `test_one_compaction_then_overflow_when_the_context_still_does_not_fit` 分别钉住两条措辞）。
- 处理时点：**M11**，与第 32 条同一处收。

### 53. 输出溢出时没有 spill 文件，也没有 `lossy` 标记

`tools/bash_tools.py::_bounded` 在 `OUTPUT_LIMIT_BYTES` 处切掉并留固定标记 `[输出已截断]`；被切掉的那一份不在任何地方，读的人不知道少了多少、也无从取回。DSH 的 collect 模式给每条流一个 `spill: { maxBytes }`（默认 64 MiB，`dsh-bash-local/lib/index.js:31`、`:108-110`），读侧带 `spillPath`（`:38`、`:291-292`），工具层把它拼进结果：`` `${output.text}\n[output truncated; full output: ${output.spillPath ?? "(unavailable)"}]` ``（`dsh-tool-bash/lib/index.js:137`）。

- 记账不动的理由：spill 要决定文件落在哪、活多久、谁有权读，那是围栏与生命周期的一件事，不是截断函数的一件事；M7 立的是事件流，与它无关。
- 处理时点：**M10**，与第 31 条（单条工具结果的剪枝）同一处收。

### 54. 一个卡住的 SSE 读者能把进程退出拖到 aiohttp 的 `shutdown_timeout`

`cli/serve.py::ServeServer.close` 是 `runner.cleanup()`；handler 在 `session_finished` 置位后返回，可 `response.write` 是 await 的——一个 TCP 窗口不动的客户端能让那条 handler 迟迟不返回，进程退出因此可能拖到 aiohttp 默认的 60 s。没测过，也没有判据。

- 记账不动的理由：M7 的判据是「客户端断开 / 慢 / 从不连接都不改变会话与日志」，三条都绿；「进程在多快之内退出」不是这一轮的判据。
- 处理时点：**M10**（serve 带回程时一起看），或下一次真用 serve 且真等过之后。

### 55. 溢出那一场几乎没有可连接的窗口，溢出在事件流上长什么样没有判据

`docs/verification/m7-serve-http-sse-manual.md` 场景 C：`--window 66000 --reserve 100` 加一条超线的提示，会话从第一条记录到最后一条只用了 9 ms（溢出发生在第一次装配，装配之前没有可遮蔽的内容）。三种客户端都没挤进去：从服务器起来之前就开始敲端口的（每 5 ms、每 20 ms 各试一轮）、把 fixture 写成 40 MB 好让装配慢一点的（装配确实在绑定之后，窗口拉长了也没连上）——这台机器上抢在监听之前发出的 SYN 会被黑洞到超时而不是当场被拒，一次尝试耗掉 0.5 s 至 10 s。于是 seam ⑥ 的溢出判据只钉住了进程侧的收尾（退出码 4、日志最后四条、stdout 只打 session id），**「溢出在事件流上长什么样」仓里一条判据都没有**。

- 记账不动的理由：M7 的溢出判据是「溢出在 serve 与在 run 是同一种收尾」，那条绿着；要钉住流上的形状，得有一条能在毫秒级窗口里稳定连上的子进程判据，本机做不到（窗口窄与 SYN 黑洞都是环境事实，不是实现事实）。
- 处理时点：**M10**（serve 带 snapshot 帧与回程时一起看：晚连的客户端该拿到什么，那时才有答案），或 Linux runner 上先跑一次真 Ctrl-C 时顺手补。

### 56. 「会话收尾 → 失败出口」那段在 `cli/main.py` 里写了三遍

`exit_code_for(outcome)` → `if outcome.stop_reason not in STOP_REASONS: return _report_failure(outcome.failure_code or outcome.stop_reason, ...)` → `if exit_code != EXIT_OK: ...` 这段在 `_run` 与 `_serve_session` 里共三处；prompt 必填那两行在 `_run` 与 `_serve` 里逐字重复。Standards 轴的 Duplicated Code。

- 记账不动的理由：三处都在 seam ⑥ 有判据、形状一致，可现在只有两个入口，抽出来只是少写两行、不增加判据。
- 处理时点：**M10**（serve 带回程 POST 端点时会出第三个入口，那时抽才有依据）。

### 57. `(code, detail)` 在四个失败类型里各带一份

`_Failure(code, detail, exit_code)`、`ConfigFailure(code, detail)`、`BindFailure(host, port, detail)`、`LogReadFailure(path, detail, code)`。第 40 条收的是「对外失败码表」那一半（`ConfigCode` 词表），四个类型本身没收。Standards 轴的 Data Clumps。

- 记账不动的理由：它们分属配置层、CLI、事件层三个模块，各自的判据在各自 seam 上绿；抽一个共享 `Failure` 会把三层的词表混进同一份。
- 处理时点：**M10**（失败要从 HTTP 回程端点返回时，才判得到「一份失败类型」够不够）。

### 58. `LogTail.read_new` 与 `read_events` 把「文件不在 → 空」与「OSError → 失败」各写一遍

解析段已经共享 `_records_from_lines`，失败段没有。另有一处小重复：「没有游标」的 `-1` 有两个家（`cli/serve.py::NO_CURSOR` 与 `events/reader.py::LogTail(after=-1)`）。Standards 轴的 Duplicated Code。

- 记账不动的理由：两处判据都在 seam ④ 绿；把 `-1` 收成一个常量只是改名，不增加判据。
- 处理时点：**M11**，与第 32 条（每回合全量重读日志）同一处收。

### 59. `LogTail` 这个名字撞 GLOSSARY 的「保留尾部」

它是带游标的增量读方，不是上下文窗口里那个 retained tail。Standards 轴的 Mysterious Name。

- 记账不动的理由：改名不增加判据，且 M7 刚立完它、判据里全是这个名字。
- 处理时点：**M11**，与第 32、58 条同一处收。

### 60. `ServeServer` 靠一句 `assert` 顶替构造收口

`cli/serve.py::_events` 里的 `assert self._log_path is not None`：`ServeServer` 因此带着两个半初始化字段（`_runner`、`_log_path`），`attach` 只是一行赋值转发；`python -O` 下这句 assert 会消失。

- 记账不动的理由：绑定先于开日志是 design D3 的要求，`ServeServer` 必须分两步出生；在 mypy strict 下 assert 是最省的说法。判断项，不是硬违规。
- 处理时点：**M10**（serve 带 snapshot 帧与回程时，这个对象的出生顺序要重新设计）。

### 61. 三条边界判据欠账：`0.0.0.0` 真绑定、`--port 65535` 上界、日志读不动时事件流悄悄结束

`--host` 只判了拒绝 `localhost`，`0.0.0.0` 真能绑定并给出事件流没有判据；`--port` 只判 0 与 65536，上界 65535 合法没有判；`cli/serve.py:119`（`LogTail` 返回 `LogReadFailure` → 事件流提前结束、会话不受影响）是 `serve.py` 唯一未覆盖的一行，没有判据。

- 记账不动的理由：前两条的失败模式是环境性的——本机有 Windows 保留端口段（1048–1623、50000–50059）与未测过的防火墙行为，本机实测过才写判据；第三条要在会话进行中把日志变得读不动，seam ④ 判 `LogTail` 自己返回失败已经绿，serve 侧那一半要等回程端点才有自然的判法。人裁决（M7 收尾轮）：记账。
- 处理时点：**M10**，或 Linux runner 上跑那四条 skip 的 SIGINT 判据时顺手补前两条。

### 62. 正文为空的 `model/response` 在 chat 的 stdout 上打出一个空行

`cli/main.py::_print_new_replies` 对每一次不带 `purpose` 的 `model/response` 都 `print(content)`；真模型下「只调工具、没有正文」的那次回复正文是空串，于是屏幕上多出一个空行。M6 模型层场 1 里四次 `model/response` 打出两个空行。

- 记账不动的理由：规格说「chat 的 stdout 只打印模型回复正文」，空正文也是正文，这不是违规，是没人决定过它该不该打。改法有两种（空正文不打 / 打一行占位），选哪种是产品判断。
- 处理时点：**M10**（serve 的流与 chat 的 stdout 一起看屏幕形状时定）。

### 63. 溢出在 REPL 屏幕上不可见，而且一次溢出之后每一段都溢出

M6 模型层场 2：`--window 66000 --reserve 100` 下第一条输入约 5000 字，两段都在装配期溢出。日志层完全正确（`error/context` + `turn/end` + `segment/end` 都是 `CONTEXT_WINDOW_EXCEEDED`、没有 `error/model`、会话继续），但 stdout 只有四个 `> `、stderr 是空的、退出码 0。超长的那条 `user/message` 住在保留尾部（10560 > 5000）无可遮蔽，于是这个会话里之后每一段都溢出，而「一次模型请求都没成功过」这件事在屏幕上和退出码上都不留痕迹。

- 记账不动的理由：溢出只到回合级、入口决定会话是 ADR-0019 定过的；「要不要在屏幕上说一句话」与「退出码要不要反映整段会话」是两条新的产品判断，本机有真 runbook 证据（`ff7d94d71c2846d598e11eae873b2484`）才记。
- 处理时点：**M10**（与第 55 条「溢出在事件流上的形状」一起判）。

### 64. 估算与真端点差多少取决于内容，而且估算里没有固定开销

`context/budget.py::estimate_tokens` 是「字符数除以 4 向上取整逐条相加」。真端点上的实测散得很：M5 那次校准出偏小 2.24 倍；`fix-compaction-and-context-overflow` 的探针那次，端点报 `prompt (222233 tokens)` 而我们的触发线是 54272，约 4 倍；同一 change 的 `minihns chat` 实测里正文部分是 1.29 至 1.40 倍（内容是重复 ASCII，tokenize 得省），而正文只有 195 字符的那次估算 49、provider 报 1031——**工具 schema 与 chat 模板那约 980 token 估算里根本没有**。窗口越小、对话越短，这一项占比越大，而触发线恰恰是在对话短的时候先动。

- 记账不动的理由：「按倍数校准」这条路被实测否掉了（倍数随内容变），剩下的两条改法各有代价——把 provider 回报的 `input_tokens` 回灌成下一回合的读数（M5 的校准只做了一半，且被遮蔽的读数与摘要调用的读数都要排除），或给估算加一项固定开销（那个数每个端点不同）。本机有真 runbook 证据（`docs/verification/fix-compaction-and-context-overflow-manual.md` 的比值表）才记。
- 处理时点：**M10**（与第 16 条「每回合全量重读日志」那笔预算账一起判）。

### 65. 摘要请求装不下时从区间头部丢弃，等于最旧的内容不进摘要

`turn_loop.py::_compact_if_over_line` 里 `while body and estimate_tokens(...) > summary_budget: body = body[1:]`——`body` 是本次要遮蔽的那一段折出的消息，按 seq 从旧到新；超「窗口减保留额」时从**头部**丢。于是被遮蔽的最旧内容既不进上下文也不进摘要，遮蔽范围照写 `{start, end}`，那一段就消失了。真端点那一次实测到它的近亲：第二次压缩 `15364 → 13239` 只省 14%，因为保留线逼着尾部几乎全留，能折掉的只剩头部那一小截。

- 记账不动的理由：改法要么改成「从尾部丢、保住最旧的」（与「保留近期尾部」这条既有规则正面冲突），要么「装不下就不压缩、直接溢出」（M5 起既有判据就是这么定的，`test_a_summary_request_that_cannot_be_made_to_fit_is_never_sent` 钉着）。两条都是产品判断，这次只把代价写清。
- 处理时点：**M10**（与第 63 条一起判；第 63 条与本条同源——都是「遮蔽范围怎么选」）。

### M6 的提交纪律欠账（不改写历史，只记账）

- **两个规划提交没有门禁那一行**：`cf1543d`、`0f49b39` 的信息里只有 `openspec validate m6-chat-repl --strict` 通过。与「提交纪律」一节同一条规矩：四道门禁是「一次提交算完成」的定义，不分代码与文档。
- **三个实现提交的门禁行记不全**：`62ccd00` 只记 ruff format / check / mypy（红绿循环里跑了测试，信息里没写测试数与覆盖率）；`0afa628` 只记覆盖率（72 → 77 未覆盖行）；`ce87b9a` 只记三次定点变异与「6 条判据全绿」。缺的是记录，不是没跑。历史提交不改写。
- **一处成本自估偏低**：`0f49b39` 写「钉死事件序列的 6 处既有判据里 4 处要改」，实测见 ADR-0020 的更正行。

### M6 的判据欠账（不改写历史，只记账）

- 组 6 的六条判据（6.4–6.10）都是**绿着到的**：读行循环在 6.1–6.3 那一次就写完了。违「一条判据先红、再绿，一次一个切片」。当场用定点变异确认它们不空转（每次「改坏一处 → 哪条变红 → 还原」记在对应提交信息里），记在这里以免下一轮把「守卫」当成红绿对。
- 6.7 与 6.8 到收尾都没跑过：`tasks.md` 写的是「Linux runner 上跑」，本机是 Windows，Ctrl-C 子进程黑盒沿用 M3 的边界。`ABORTED` 在 chat 路径上的可达性因此只有两条过程内守卫（handler 置事件 / handler 抛 `KeyboardInterrupt`），没有子进程判据。缺口记进 `docs/verification/m6-chat-repl-manual.md`。
- **收尾轮补的三条**：`test_the_request_level_retry_records_the_context_it_actually_sent`（seam ①，真红过——先红在 `assert 1 == 2`，实现补上快照之后绿）；`test_chats_flag_table_is_runs_flag_table_minus_two` 与 `test_a_chat_that_cannot_start_leaves_no_log`（seam ⑥，**绿着到的守卫**：实现早在 6.1–6.3 与 `_prepare_or_fail` 里就写对了，Spec 轴查出的是「判据缺失」而不是「实现缺失」）。后两条在收尾变异轮里各配一条定点变异确认不空转。

### M7 的提交纪律欠账（不改写历史，只记账）

- **两个规划提交没有门禁那一行**：`8a5cb14`、`414ccf4` 的信息里只有 `openspec validate m7-serve-http-sse --strict` 通过。与 M6 / M8 / M9 同一条规矩：四道门禁是「一次提交算完成」的定义，不分代码与文档。
- **一个红绿循环拆成了两个提交、门禁只跑一次**：`fd1986a` 声明 6.1–6.3 却带着 6.4 的 seam ⑥ 判据（那条 SIGINT 子进程判据），`3d85b11` 的信息自述门禁数字「与上一个提交同一份工作树」。`git log` 与 `tasks.md` 的 6.1–6.4 因此对不上。
- **一处打包没写理由**：`d5231b8` 打包 7.1–7.3，跨 seam ②（7.1 的可达性判据在 `tests/test_config_layering.py`）、⑥（7.2 的三处调用方）与 docs（7.3）。提交粒度那条只允许「同一 seam 上相邻 3 个 task」，跨 seam 打包要写理由，这条没写。
- **一处 seam 标注与实况分叉**：`tasks.md` 的 7.1 标 seam ⑥、判据实际落在 ②。已在收尾轮就地更正（历史提交不改写）。

### M7 的判据欠账（不改写历史，只记账）

- 组 4 与组 5 的六条判据（4.2 / 4.3 / 4.4 / 4.5 / 5.2）与组 6 的三条（6.1 / 6.2 / 6.3）都是**绿着到的守卫**：帧、游标与断开处理在各自组的第一次红绿里就写完了。当场用定点变异确认它们不空转（4.5 那条还查出一个只在 seam ⑥ 存活的变异，人裁决定位到 seam ④ 补判据）。
- **收尾轮补的四条**（Spec 轴查出的是判据缺失）：`test_non_utf8_output_collapses_into_replacement_characters`（seam ②③，bash delta 那条 Scenario 从 propose 起就没有判据）；`test_the_start_record_names_the_serve_entry_and_the_prompt_verbatim`（seam ⑥，`entry` 此前只有 seam ① 的进程内判据，把 CLI 的 `entry=ENTRY_SERVE` 改成 `ENTRY_RUN` 全仓不红——L-048 那条教训在 M7 复发）；`test_a_cursor_ahead_of_what_is_written_is_not_an_error` 加强成同时判「不报错」与「开始送帧」；`test_serve_without_the_http_flag_is_the_same_session`（seam ⑥，真红过——先红在 `assert 2 == 0`，`--http` 改成可选之后绿；人裁决定的是「保留 `--http` 但可选」，规格 flag 表与 delta 的 Scenario 同步补上）。
- **9.1 的 Ctrl-C 那一半等人跑**（Linux runner）；四条 SIGINT 子进程判据（run 一条、chat 两条、serve 一条）本机 skip，沿用 M3 的边界。9.2 的模型层那一半 2026-10-22 晚跑完（用户作用域的密钥显式注入后），观察在 `docs/verification/m7-serve-http-sse-manual.md` 最后一节；同一轮把 M6 的模型层非 tty 那一半一并跑完，查出的两条新形状记进上面的第 62 与 63 条。
