## ADDED Requirements

### Requirement: 窗口预算不成立的配置在 session 开始之前失败
当有效的 `window − reserve − 65536 ≤ 0` 时（触发线为 0，任何非空上下文都越线且压缩救不动），系统 SHALL 在 session 开始之前以退出码 2 结束，stderr 含 `INVALID_ARGUMENT` 并指出 `window`、`reserve` 与那个 65536 的余量三个数，且 MUST NOT 创建任何 session 日志。照 DSH：窗口减去预留与 headroom 之后没有剩余压力预算时，这是配置解析期的错误（`TargetPressureConfigError`，`dsh-compaction-basic/lib/index.js:130-131`），不是运行期才发现的溢出。

#### Scenario: 窗口太小是参数错误
- **WHEN** 执行 `minihns run -p "x" --window 32768 --reserve 4096`
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT` 与三个数，且没有创建任何 session 日志

#### Scenario: 触发线为正的最小窗口照跑
- **WHEN** 执行 `minihns run -p "x" --window 70000 --reserve 4096`
- **THEN** 会话开始，`session/start` 的 payload 里 `window` 为 70000、`reserve` 为 4096

## MODIFIED Requirements

### Requirement: 触发线由固定公式给出
系统 SHALL 用 `floor(min(W × 0.8, W − O − 65536))` 给出压缩触发线（W 是 `window`、O 是 `reserve`）；65536 是实现常量，MUST NOT 有命令行开关。该公式算出负数时触发线 SHALL 取 0——触发线对任意合法的 W 与 O 都是全函数。`W − O − 65536 ≤ 0` 的窗口组合进不了会话（接替见「窗口预算不成立的配置在 session 开始之前失败」），所以 CLI 路径上取 0 这一支走不到。

#### Scenario: 默认参数下的触发线是一个可断言的数
- **WHEN** `window` 为 128000、`reserve` 为 8192
- **THEN** 触发线为 54272（`W − O − 65536` 比 `W × 0.8` 小）

#### Scenario: 小窗口下每次装配都越线
- **WHEN** 一次 run 的 `--window` 为 70000、`--reserve` 为 100（触发线 4364，比保留预算 11200 还小）
- **THEN** 每一个需要装配的回合都进入压缩判定，且触发线本身是 4364 而不是负数

### Requirement: 越线时压缩发生在装配之内
当一次装配的预算读数超过触发线时，系统 SHALL 在写出该点的 `context/assembled` 之前完成一次压缩：生成摘要、写一条 `compaction/summary`、再按新的日志前缀重新折叠。**同一次装配之内** MUST NOT 压缩多于一次；未越线的装配 MUST NOT 写 `compaction/summary`。provider 报出上下文超限触发的**请求级压缩**是另一次尝试，上限 1 次（见「provider 报出的上下文超限塌成同一个溢出结果」与 ADR-0019），不受「一次装配最多一次」约束。

#### Scenario: 压缩记录在装配记录之前
- **WHEN** 某回合的装配越线并完成了压缩
- **THEN** 该回合的日志里 `compaction/summary` 出现在该点的 `context/assembled` 之前

#### Scenario: 未越线就没有压缩记录
- **WHEN** 跑完一次预算充裕的 run
- **THEN** 日志里没有任何 `compaction/summary` 记录

#### Scenario: 一次装配只尝试一次
- **WHEN** 一次装配压缩之后预算读数仍超过触发线
- **THEN** 系统不在同一装配里尝试第二次压缩，而是产出溢出结果

### Requirement: 压缩救不了时是 CONTEXT_WINDOW_EXCEEDED 结果
当一次装配压缩之后预算读数仍超过触发线时，系统 SHALL 写一条 `error/context`（payload 含 `turn_id`、`code: CONTEXT_WINDOW_EXCEEDED`、`detail`）与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`），结束**该回合**；`session/end` 与退出码由入口决定——一次性 `minihns run` 写 `session/end` 并以退出码 4 结束，`minihns chat` 不写 `session/end` 且会话继续。MUST NOT 抛出未捕获异常，也 MUST NOT 为这个溢出结果调用回合模型——带 `purpose: compaction` 的摘要调用除外。

#### Scenario: 溢出的回合不产出该回合自己的模型调用
- **WHEN** 一次装配以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该回合没有 `context/assembled`、没有不带 `purpose: compaction` 的 `model/request`、没有 `tool/call`

#### Scenario: 单条消息本身就超线
- **WHEN** 对话体里没有任何可遮蔽的内容，而预算读数已超过触发线
- **THEN** 日志以 `error/context` 与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）收尾；一次性 run 还写 `session/end` 且退出码为 4

#### Scenario: 溢出收尾的日志可被重放
- **WHEN** 对一次以 `CONTEXT_WINDOW_EXCEEDED` 收尾的 run 的日志执行 `minihns replay`
- **THEN** 每条 `context/assembled` 都与其前缀的重算结果逐字段相等，replay 以退出码 0 结束；溢出发生在第一次装配之前时，日志里没有装配点，replay 照样以退出码 0 结束并说明这一点

### Requirement: provider 报出的上下文超限塌成同一个溢出结果
当 Provider 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果时，系统 SHALL 先做一次**请求级压缩**：有可遮蔽的内容就生成摘要、写一条 `compaction/summary`、按新的日志前缀重新折叠并重试该请求一次（上限 1 次，照 DSH 的 `maxOverflowRetries` 默认 1）。压缩无可遮蔽、重试次数已用完、或重试仍报同一失败时，系统 SHALL 产出与估算兜底同一个溢出结果：写 `error/context`（`code: CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`），`session/end` 与退出码由入口决定。此时 MUST NOT 写 `error/model`。

#### Scenario: 真实超限不走 provider 失败那条路
- **WHEN** 某回合的模型调用得到 `PROVIDER_CONTEXT_OVERFLOW` 的失败结果且没有可遮蔽的内容
- **THEN** 该回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED`，日志里没有 `error/model`，也没有 `compaction/summary`

#### Scenario: 两条触发路径产出同一个停止理由
- **WHEN** 一次 run 由估算兜底溢出、另一次由 provider 报出溢出
- **THEN** 两份日志的 `turn/end` 的 `stop_reason` 相同，一次性 run 的退出码都是 4

#### Scenario: 请求级压缩救回一次
- **WHEN** 某回合的模型调用得到 `PROVIDER_CONTEXT_OVERFLOW`，而对话体里有可遮蔽的较早往返
- **THEN** 日志里恰有一条 `compaction/summary`，该请求被重试一次，该回合以正常的 `model/response` 继续而不是以溢出收尾
