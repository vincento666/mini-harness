# M1 的刻意简化：明文 JSONL、版本从 1 起、不施加窗口预算、保留退出码 3/4、prompt 搭 `session/start`

M1（change `m1-event-log-and-turn-loop`）只验证「事件日志 + 显式回合循环 + 冷启动折叠」这条主干，因此刻意偏离几条显而易见的做法，免得主干被过早复杂化。后来的人看到下面的现象时，不要当成缺陷去「修」。

1. **session 日志是明文 JSONL。** 不压缩、不加密、不签名：每行一条事件、UTF-8、只追加。日志既是调试产物也是重放输入，明文让人和 `minihns replay` 都能直接读它；压缩与加密等到日志形状稳定之后再考虑。
2. **`schema_version` 从 1 起。** 每条事件的信封都带版本号，但 M1 只有版本 1，也没有迁移器。目的是让「版本从第一条日志起就存在」成为事实，而不是等到需要升级时才补。
3. **M1 不施加上下文窗口预算。** 折叠是全量的：受保护头部 + 按事件顺序的完整对话体，不截断、不摘要、不遮蔽，因此也不会产生上下文预算溢出。窗口预算属于后续里程碑；过早引入会让「折叠两次结果相同」这条不变量无法被测试固定。
4. **退出码 3 与 4 是保留码。** 完整表是 0 成功、1 模型或内部错误、2 参数错误、3 围栏拒绝或审批被拒、4 上下文预算溢出、5 用户取消。M1 既没有围栏也没有预算机制，所以 3 与 4 不会被产生；`tests/test_integration.py::test_no_m1_scenario_exits_with_the_reserved_codes` 把这一点锁住。

5. **用户 prompt 记在 `session/start.payload.prompt`，折叠时是对话体的第一条 `user` 消息。** M1 的事件词表里没有专门的 prompt 事件类型，用户输入原文因此搭 `session/start` 的 payload 进日志、再由折叠送进上下文。替代方案是新增 `prompt/submitted` 事件类型——M1 否掉（扩词表没有额外收益）；M2 之后若要多轮输入或 REPL 常驻，要走一次 openspec 变更再引入该类型。
6. **`replay` 逐点重算并断言相等，不打印「全量折叠的最终上下文」。** 最后一回合产生的对话体必然让全量折叠与最后一次装配不相等，所以「折叠等于实时装配」只在每个 `context/assembled` 的前缀上才是可断言的事实；不一致时产出 `error/replay`（`REPLAY_MISMATCH`）走 stderr、退出码 1，被重放的日志不被改写。

Considered options：二进制或压缩日志（否：M1 的判据是可重放与可读）；不带版本号（否：后续升级需要版本事实从第一条日志起就在）；M1 就做窗口截断（否：截断策略本身还没设计，先做会锁死折叠语义）；prompt 独立成事件类型（否于 M1：见第 5 条）；replay 只比对最后一条 `context/assembled`（否：在任何真实 run 上都不可满足）。

覆盖的 change：`openspec/changes/m1-event-log-and-turn-loop/`（proposal、design、specs、tasks）。
