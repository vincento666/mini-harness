# 记账：M1 留下的六处坏味道与一处设计缺口，M2 加文件工具时一并处理

这一条不是待办清单的优先级排序，而是 code-review 修复轮（change `m1-event-log-and-turn-loop` 的 tasks 第 11 节）留下的**账**：审查里确认存在的重复与泄漏，M1 里改它们只会增加改动面、不会增加判据，因此只记账不动代码。任何一条到 M2 都可以按新证据改判——但改判要发生在 M2 的 change 里，不是顺手改。

## 1. `run_session` 的九个关键字参数就是 `session/start` 的 payload

`run_session(prompt, provider, provider_name, log, registry, workspace, max_turns, cancel, append_system_prompt)` 里除 `provider`/`log`/`registry` 外的那几个，与写进 `session/start.payload` 的字段几乎一一对应。测试里因此有 11 处把同一串参数重复写一遍。

- 现在不动的理由：参数形状就是 seam ① 的接口本身，M1 只有一个调用方（CLI）；抽 `SessionSettings` 会让「payload 里有什么」这条事实变成两层间接。
- M2 的处理：加文件工具时参数还会再长（工具白名单、预算），那时引入 `SessionSettings`（pydantic 模型），让它同时是 `run_session` 的入参和 `session/start.payload` 的来源，测试改用一个构造 helper。

## 2. `ToolDefinition` 与 `ToolSpec` 字段完全相同

`mini_harness/tools/registry.py::ToolDefinition` 与 `mini_harness/provider/contract.py::ToolSpec` 都是 `name: str` + `description: str`，`ToolRegistry.specs()` 逐字段搬运。

- 现在不动的理由：两个名字对应两个概念（注册表里的定义 / 送给模型的规格），M1 里合并会抹掉这条区分，而区分本身是设计意图。
- M2 的处理：文件工具落地时看它们是否开始分叉（参数 schema、权限标记）。分叉就保留两个并让 `specs()` 显式映射；不分叉就合并成一个类型并在两处复用。

## 3. `main._replay` 摸的是事件层的内部形状

`_replay` 自己扫 `records` 找 `turn/start` 取 `turn_id`、按 `context/assembled` 的下标切前缀。这些是 events 层的知识，放在 CLI 层意味着 events 层改形状时 CLI 会跟着坏。

- 现在不动的理由：M1 只有 replay 一个消费者，且这段逻辑与它的判据（逐点相等）在同一个测试文件里最好读。
- M2 的处理：下沉成 events 层的 `assembly_points(records)`（返回 `(前缀, turn_id, 记录)`），CLI 只负责打印与退出码。

## 4. 三个测试文件各自有一份 `_cli` 黑盒 helper

`tests/test_cli_run.py`、`tests/test_cli_replay.py`、`tests/test_integration.py` 都定义了几乎相同的 `_cli(*args, cwd)`（`sys.executable -m mini_harness.cli.main`、UTF-8）。

- 现在不动的理由：seam ⑥ 的测试要能单独读懂「这是一次真实子进程调用」，共享 helper 会让每个文件少一行但多一次跳转。
- M2 的处理：若第四个 CLI 测试文件出现（三份变四份），把它们收进 `tests/cli_blackbox.py`，并把 `_run_once` 这类构造 helper 一起收进去。

## 5. `stop_reason`、`outcome`、`role` 是裸 `str`

词表写在 spec 里（五个 `stop_reason`、两个 `tool/result.outcome`、三种消息 `role`），代码里都是 `str`，mypy 挡不住词表外的值：`RunOutcome(stop_reason="OK")` 能通过类型检查。

- 现在不动的理由：词表本身在 M1 期间还在被 spec 改动（本轮就加了 `NOT_IMPLEMENTED`），锁成 `Literal` 会让每次词表改动多一处类型编辑；测试目前从日志断言词表，覆盖是够的。
- M2 的处理：词表稳定后改成 `Literal[...]` 或枚举，并让 `EventRecord.type` 的校验也走同一份词表常量。

## 6. `RunOutcome.failure_code` 与 `detail` 只被 CLI 读一次，`turns` 在生产里没人读

内核结果里的这三个字段，`failure_code`/`detail` 只在 `_run` 映射退出码时被读，`turns` 目前只有测试读。

- 现在不动的理由：它们是把「失败也是结果」写进日志之外的唯一载体；`turns` 是 `session/end.payload.turns` 的对应物，留着让内核结果与日志可对照。
- M2 的处理：加文件工具时若需要「失败发生在哪个工具」这类细节，扩 `RunOutcome` 而不是新加一个并列结果类型。

## 7. 设计缺口：replay 的折叠入参里工具描述取空

`_replay` 重算每个 `context/assembled` 时传 `tool_descriptions=()`：M1 注册表为空，所以这与实时装配一致。一旦 M2 注册了真实工具，头部里的「可用工具」块会依赖注册表，而注册表的名字只出现在该装配点**之后**的 `model/request` 里——前缀里没有这个事实，重放就会对合法日志报 `REPLAY_MISMATCH`。

- 现在不动的理由：M1 没有任何注册工具，这条差异不存在；把它做成「前缀可见的工具描述」要改 `session/start` 的 payload 字段表，属于扩词表级决定。
- M2 的处理：在 `session/start.payload`（或每个 `turn/start.payload`）里记下当时的工具名列表，让折叠入参全部可从日志前缀派生；`tests/test_cli_replay.py::test_replay_does_not_use_events_after_the_assembly_point` 已经是这条判据的守门测试，M2 只需把取空的这一行换成从前缀派生。

Considered options：现在就抽 `SessionSettings` 与 `Literal` 词表（否：M1 的判据已经全绿，改动只增加面不增加证据）；把 `_replay` 的扫描逻辑立刻下沉（否：只有一个消费者，等第二个消费者出现再抽）；M1 就把工具描述写进 `session/start`（否：M1 没有任何工具可写，写了也测不出差异）。
