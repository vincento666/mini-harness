# 记账：M1 与 M2 留下的坏味道与设计缺口，到对应里程碑再动

这一条不是待办清单的优先级排序，而是 code-review 修复轮（change `m1-event-log-and-turn-loop` 的 tasks 第 11 节）留下的**账**：审查里确认存在的重复与泄漏，M1 里改它们只会增加改动面、不会增加判据，因此只记账不动代码。任何一条到 M2 都可以按新证据改判——但改判要发生在 M2 的 change 里，不是顺手改。第 9 至 11 条来自 M2（change `m2-file-tools-and-fences`）的 `code-review` 两轴审查，处理方式同样是记账。

## 1. `run_session` 的九个关键字参数就是 `session/start` 的 payload

`run_session(prompt, provider, provider_name, log, registry, workspace, max_turns, cancel, append_system_prompt)` 里除 `provider`/`log`/`registry` 外的那几个，与写进 `session/start.payload` 的字段几乎一一对应。测试里因此有 11 处把同一串参数重复写一遍。

- 现在不动的理由：参数形状就是 seam ① 的接口本身，M1 只有一个调用方（CLI）；抽 `SessionSettings` 会让「payload 里有什么」这条事实变成两层间接。
- M2 的处理：加文件工具时参数还会再长（工具白名单、预算），那时引入 `SessionSettings`（pydantic 模型），让它同时是 `run_session` 的入参和 `session/start.payload` 的来源，测试改用一个构造 helper。
- **部分处理（2026-10-17，M2 change `m2-file-tools-and-fences` 任务 3.2；M2 审查后更正）**：`loop/settings.py::SessionSettings` 落地，`run_session` 收 `settings=`，`session/start.payload` 由它生成；seam ① 与 seam ⑥ 的测试改用 `tests/tool_harness.py` 的 helper。但 seam ②③ 里仍有四处手搓 `SessionSettings(...)`（`test_fences._context`、`test_approval_gate._run`、`test_vocabulary_reachability._dispatch_with_gate`、`test_tool_registry`），因为 helper 不收 `registry` 与 `approval_gate`。剩下的这一半留到 M3：把 helper 扩成收 `registry` / `gate` 时才值得收，否则只是把一处构造搬到另一处。

## 2. `ToolDefinition` 与 `ToolSpec` 字段完全相同

`mini_harness/tools/registry.py::ToolDefinition` 与 `mini_harness/provider/contract.py::ToolSpec` 都是 `name: str` + `description: str`，`ToolRegistry.specs()` 逐字段搬运。

- 现在不动的理由：两个名字对应两个概念（注册表里的定义 / 送给模型的规格），M1 里合并会抹掉这条区分，而区分本身是设计意图。
- M2 的处理：文件工具落地时看它们是否开始分叉（参数 schema、权限标记）。分叉就保留两个并让 `specs()` 显式映射；不分叉就合并成一个类型并在两处复用。
- **已处理（2026-10-17，M2 任务 10.1）**：分叉了——`ToolDefinition` 多了 `args_model`、`mutates`、`run`，`ToolSpec` 仍然只有 `name` + `description`，`specs()` 显式映射。两个名字对应两个概念这条区分因此保留。

## 3. `main._replay` 摸的是事件层的内部形状

`_replay` 自己扫 `records` 找 `turn/start` 取 `turn_id`、按 `context/assembled` 的下标切前缀。这些是 events 层的知识，放在 CLI 层意味着 events 层改形状时 CLI 会跟着坏。

- 现在不动的理由：M1 只有 replay 一个消费者，且这段逻辑与它的判据（逐点相等）在同一个测试文件里最好读。
- M2 的处理：下沉成 events 层的 `assembly_points(records)`（返回 `(前缀, turn_id, 记录)`），CLI 只负责打印与退出码。

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

## 7. 设计缺口：replay 的折叠入参里工具描述取空

`_replay` 重算每个 `context/assembled` 时传 `tool_descriptions=()`：M1 注册表为空，所以这与实时装配一致。一旦 M2 注册了真实工具，头部里的「可用工具」块会依赖注册表，而注册表的名字只出现在该装配点**之后**的 `model/request` 里——前缀里没有这个事实，重放就会对合法日志报 `REPLAY_MISMATCH`。

- 现在不动的理由：M1 没有任何注册工具，这条差异不存在；把它做成「前缀可见的工具描述」要改 `session/start` 的 payload 字段表，属于扩词表级决定。
- M2 的处理：在 `session/start.payload`（或每个 `turn/start.payload`）里记下当时的工具名列表，让折叠入参全部可从日志前缀派生；`tests/test_cli_replay.py::test_replay_does_not_use_events_after_the_assembly_point` 已经是这条判据的守门测试，M2 只需把取空的这一行换成从前缀派生。
- **已处理（2026-10-17，M2 任务 3.2 与 11.1）**：工具名列表进 `session/start.payload.tools`，`fold()` 不再收 `append_system_prompt` / `tool_descriptions` 参数——单一真源是 `session/start`，回放侧与实时侧从同一份前缀派生。CLI 一接线就让三条 replay 判据立刻红（`REPLAY_MISMATCH: seq=2`），这条差异不是假设。

## 8. `provider` 层的两处 import 指向 `events.fold`

`provider/contract.py:11` 与 `provider/mock.py:13` 都 `from mini_harness.events.fold import Message`，因为 `generate` 的入参类型是 `Sequence[Message]`。依赖方向因此是 provider → events，而不是两份契约各自独立；分层图上看是一条反向箭头。

- 现在不动的理由：`Message` 目前只有折叠一个生产者，另立一个消息类型模块会让同一个类型有两个家；M1 的判据不依赖这条方向。
- M2 的处理：文件工具落地后看 `Message` 是否需要携带更多工具相关字段（`tool_calls` 与 `tool_call_id` 已经在）。需要就把 `Message` 抽成独立的类型模块，provider 与 events 都指向它；不需要就把这条方向记为长期形态并在此处改判。

## 9. `approval/*` 这一对事件在问完人之后才落盘

`turn_loop` 先派发（含向人提问），再把 `approval/request` 与 `approval/response` 追加进日志。人已回答、而执行段抛异常或进程被杀时，日志里没有任何 `approval/*`——event-log 规格要求的「每条 `approval/request` 有且只有一条配对的 `approval/response`」在这种情况下不成立。

- 现在不动的理由：M2 的判据覆盖的是「问了就成对出现」与「没问就都不出现」（12.3 与 13.x），这条差异只在「问了之后进程死掉」的路径上存在，而 M2 没有能可靠杀死进程再检查日志的判据。
- M3 的处理：把 `approval/request` 在提问**之前**写、`approval/response` 在拿到结论后立刻写，代价是日志里可能出现「有 request 没有 response」的半对——那时要么加一条折叠侧的判据把它读成「未回答」，要么在词表里加一个 `UNANSWERED`。这是扩词表级决定，不在 M2 顺手做。

## 10. 取消信号只在回合边界被看到

`cancel.is_set()` 只出现在回合边界（`turn_loop` 的 267 / 279 / 293 三处），派发一批 `tool_calls` 的循环里没有检查。实测：第一个调用置位 cancel 后，同一批里的第二个 `write` 仍被派发。规格 turn-loop 那条「当运行期间收到取消信号时…」读起来像随时生效。

- 现在不动的理由：M2 的取消判据覆盖的是 `generate` 期间与回合边界；「一批工具中途取消」需要决定剩下几个算不算执行过、要不要写 `tool/cancelled`（这个词在 M2 词表之外，见 ADR-0003 第 3 条）。
- M3 的处理：决定「取消发生在派发段时剩下未执行的调用怎么写」——要么加 `tool/cancelled` 词表项，要么在 `turn/end.payload` 里记下「未执行的 `tool_call_id` 列表」。两者都是扩词表，与第 3 条同源。

## 11. `error/fence` 里被拒的路径只在自由文本 `detail` 里

payload 是 `turn_id` / `tool_call_id` / `code` / `detail`。规格要求「被拒的路径或工具名」可断言，实现把它塞进自由文本，且形态不统一：`OUTSIDE_WORKSPACE` 放解析后的键，`SANDBOX_DENIES_WRITE` 放未解析的 `raw_path`。判据只能断言 `code`，断言不了路径。

- 现在不动的理由：M2 的判据断言的是 `code` 与退出码；把路径做成结构化字段要定「放原始写法还是解析后键」，而这两者对模型的可读性不同（原始写法更接近模型自己写的路径，解析后键更接近围栏真正拒绝的东西）。
- M3 的处理：加 `path` 与 `raw_path` 两个字段（或一个 `target` 对象），并让 `detail` 只面向人。改的是 `error/fence` 的 payload 字段表，属于扩词表级决定。

## 12. seam ②③ 的测试里各留一份桩与常量

`DONE` 与 `_DONE`、`_ApprovingGate` 两份、`_Gate` 两份、`_StubArgs` / `_WriteArgs` 两份桩，根因与第 1 条同源：`tests/tool_harness.py` 的 helper 不收 `registry` 与 `approval_gate`。

- 现在不动的理由：seam ②③ 的判据要能单独读懂「这个门只批准一次」「这个工具只记录被调用过」，把桩收进共享模块会让每条判据多一次跳转。
- M3 的处理：与第 1 条剩下的那一半一起做——helper 收 `registry` / `gate` 之后，桩才有唯一的家。

Considered options：现在就抽 `SessionSettings` 与 `Literal` 词表（否：M1 的判据已经全绿，改动只增加面不增加证据）；把 `_replay` 的扫描逻辑立刻下沉（否：只有一个消费者，等第二个消费者出现再抽）；M1 就把工具描述写进 `session/start`（否：M1 没有任何工具可写，写了也测不出差异）；M1 就把 `Message` 抽到独立类型模块（否：一个生产者两个消费者，抽出去只是把同一行 import 换个地方）；M2 就把 `approval/request` 改成提问前写（否：会留下「有 request 没 response」的半对，而 M2 词表里没有表达它的取值）；M2 就在派发循环里查取消（否：先要决定未执行的调用怎么写日志，那是扩词表级决定）。
