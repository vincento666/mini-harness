# context-budget Delta

## ADDED Requirements

### Requirement: 溢出判据是压力预算，触发线只决定要不要压缩
系统 SHALL 把「窗口减保留额」（`W − O`）作为压力预算，并只用它判定上下文溢出：一次装配的预算读数不超过压力预算时 MUST NOT 产出 `CONTEXT_WINDOW_EXCEEDED`，即使它超过触发线、即使本次没有可遮蔽的内容。触发线 SHALL 只决定「这次装配要不要尝试压缩」，MUST NOT 被用作溢出判据。触发线小于保留预算（`floor(W × 0.16)`）的窗口组合 SHALL 可跑。

#### Scenario: 死区窗口里装得下的读数不判溢出
- **WHEN** `--window` 为 70000、`--reserve` 为 100（触发线 4364、保留预算 11200、压力预算 69900），一次装配的预算读数为 5933 且没有可遮蔽的内容
- **THEN** 该回合照常写 `context/assembled` 与不带 `purpose` 的 `model/request`，日志里没有 `error/context`，一次性 run 不以退出码 4 结束

#### Scenario: 压缩之后仍超压力预算才溢出
- **WHEN** 一次装配越线、写出了一条 `compaction/summary`，按新日志前缀重折叠后的读数仍超过压力预算
- **THEN** 该回合以 `error/context`（`code: CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`（同一停止理由）收尾，`detail` 含预算读数、压力预算与触发线三个数

#### Scenario: 触发线小于保留预算不是配置错误
- **WHEN** 执行 `minihns run -p "x" --window 70000 --reserve 100`
- **THEN** 退出码不是 2，session 日志被创建（`W − O − 65536 = 4364 > 0`，「窗口预算不成立的配置」那条不适用）

## MODIFIED Requirements

### Requirement: 越线时压缩发生在装配之内
当一次装配的预算读数超过触发线时，系统 SHALL 在写出该点的 `context/assembled` 之前完成一次压缩：生成摘要、写一条 `compaction/summary`、再按新的日志前缀重新折叠。**同一次装配之内** MUST NOT 压缩多于一次；未越线的装配 MUST NOT 写 `compaction/summary`。provider 报出上下文超限触发的**请求级压缩**是另一次尝试，上限 1 次（见「provider 报出的上下文超限塌成同一个溢出结果」与 ADR-0019），不受「一次装配最多一次」约束。越线只触发压缩尝试；是否溢出由压力预算判（见「溢出判据是压力预算，触发线只决定要不要压缩」）。

#### Scenario: 压缩记录在装配记录之前
- **WHEN** 某回合的装配越线并完成了压缩
- **THEN** 该回合的日志里 `compaction/summary` 出现在该点的 `context/assembled` 之前

#### Scenario: 未越线就没有压缩记录
- **WHEN** 跑完一次预算充裕的 run
- **THEN** 日志里没有任何 `compaction/summary` 记录

#### Scenario: 一次装配只尝试一次
- **WHEN** 一次装配压缩之后预算读数仍超过触发线
- **THEN** 系统不在同一装配里尝试第二次压缩；该回合是否溢出由压力预算判

### Requirement: 压缩救不了时是 CONTEXT_WINDOW_EXCEEDED 结果
当一次装配的预算读数超过**压力预算**（`W − O`）时，系统 SHALL 写一条 `error/context`（payload 含 `turn_id`、`code: CONTEXT_WINDOW_EXCEEDED`、`detail`）与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`），结束**该回合**；`session/end` 与退出码由入口决定——一次性 `minihns run` 写 `session/end` 并以退出码 4 结束，`minihns chat` 不写 `session/end` 且会话继续。`detail` SHALL 含预算读数、压力预算与触发线三个数，并按这一回合的实际事实区分三种措辞：真写过摘要说「压缩之后」；`shadowed_range` 给不出范围说「无可遮蔽的内容」；给得出范围却裁到只剩一组往返仍装不下说「可遮蔽的那一段本身就装不下」。MUST NOT 抛出未捕获异常，也 MUST NOT 为这个溢出结果调用回合模型——带 `purpose: compaction` 的摘要调用除外。

#### Scenario: 溢出的回合不产出该回合自己的模型调用
- **WHEN** 一次装配以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该回合没有 `context/assembled`、没有不带 `purpose: compaction` 的 `model/request`、没有 `tool/call`

#### Scenario: 单条消息本身就超线
- **WHEN** 对话体里没有任何可遮蔽的内容，而预算读数已超过压力预算
- **THEN** 日志以 `error/context` 与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）收尾；一次性 run 还写 `session/end` 且退出码为 4

#### Scenario: 溢出收尾的日志可被重放
- **WHEN** 对一次以 `CONTEXT_WINDOW_EXCEEDED` 收尾的 run 的日志执行 `minihns replay`
- **THEN** 每条 `context/assembled` 都与其前缀的重算结果逐字段相等，replay 以退出码 0 结束；溢出发生在第一次装配之前时，日志里没有装配点，replay 照样以退出码 0 结束并说明这一点

### Requirement: 摘要请求只装本次要遮蔽的那一段
生成摘要的那次模型调用 SHALL 只携带三类消息：折叠派生的系统消息、本次遮蔽范围（`shadowed_range` 给出的 seq 闭区间）折出的消息、以及作为最后一条的摘要指令。该调用 MUST NOT 携带落在遮蔽范围之外的对话消息，也 MUST NOT 携带保留尾部。该调用携带的全部消息按既有的估算 SHALL NOT 超过压力预算：超过时系统 SHALL 从该范围的头部按工具往返整对丢弃直到装得下——带调用的那条 assistant 与回答它的 tool 消息 MUST NOT 被拆散。一条都装不下时 SHALL NOT 发出该调用；发不出该调用本身 MUST NOT 直接构成溢出结果，该回合是否溢出由压力预算判。

#### Scenario: 保留尾部不进摘要请求
- **WHEN** 一次装配越线并发出了摘要调用
- **THEN** 该调用收到的消息里，除系统消息与最后一条摘要指令外，每一条都来自本次 `compaction/summary.payload.shadowed_range` 之内；保留尾部的那段消息不在其中

#### Scenario: 摘要请求本身不越线
- **WHEN** 一次装配越线并发出了摘要调用
- **THEN** 该调用携带的全部消息按既有的估算不超过压力预算

#### Scenario: 裁剪不拆散工具往返
- **WHEN** 遮蔽范围折出的消息超过压力预算，裁剪从该范围头部丢掉一组工具往返
- **THEN** 该调用收到的消息里每一条 tool 消息之前都有一条带对应 `tool_call_id` 的 assistant 请求

#### Scenario: 一段都装不下时不发请求
- **WHEN** 遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过压力预算
- **THEN** 日志里没有带 `purpose: compaction` 的 `model/request`，也没有 `error/model`；该回合照常装配，除非预算读数本身超过压力预算

### Requirement: 窗口预算不成立的配置在 session 开始之前失败
当有效的 `window − reserve ≤ 0` 时（压力预算非正，没有任何上下文装得下），系统 SHALL 在 session 开始之前以退出码 2 结束，stderr 含 `INVALID_ARGUMENT` 并指出 `window` 与 `reserve` 两个数，且 MUST NOT 创建任何 session 日志。照 DSH：窗口减去预留之后没有压力预算时，这是配置解析期的错误（`TargetPressureConfigError`，`dsh-compaction-basic/lib/index.js:130-131`），不是运行期才发现的溢出。触发线为 0（`W − O − 65536 ≤ 0`）MUST NOT 构成配置错误——它只意味着每次装配都尝试一次压缩，装得下的读数照常跑完。

#### Scenario: 窗口太小是参数错误
- **WHEN** 执行 `minihns run -p "x" --window 4096 --reserve 8192`
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT` 与那两个数，且没有创建任何 session 日志

#### Scenario: 触发线为正的最小窗口照跑
- **WHEN** 执行 `minihns run -p "x" --window 70000 --reserve 4096`
- **THEN** 会话开始，`session/start` 的 payload 里 `window` 为 70000、`reserve` 为 4096

#### Scenario: 触发线为 0 的窗口照跑
- **WHEN** 执行 `minihns run -p "x" --window 4000 --reserve 100`（触发线 0、保留预算 640、压力预算 3900）
- **THEN** 退出码不是 2，session 日志被创建，`session/start` 的 payload 里 `window` 为 4000、`reserve` 为 100

### Requirement: 触发线由固定公式给出
系统 SHALL 用 `floor(min(W × 0.8, W − O − 65536))` 给出压缩触发线（W 是 `window`、O 是 `reserve`）；65536 是实现常量，MUST NOT 有命令行开关。该公式算出负数时触发线 SHALL 取 0——触发线对任意合法的 W 与 O 都是全函数。取 0 这一支在 CLI 路径上走得到：它只意味着每次装配都尝试一次压缩，不构成配置错误（配置错误只由「窗口预算不成立的配置在 session 开始之前失败」那条判定）。触发线 MUST NOT 被用作溢出判据（见「溢出判据是压力预算，触发线只决定要不要压缩」）。

#### Scenario: 默认参数下的触发线是一个可断言的数
- **WHEN** `window` 为 128000、`reserve` 为 8192
- **THEN** 触发线为 54272（`W − O − 65536` 比 `W × 0.8` 小）

#### Scenario: 小窗口下每次装配都越线
- **WHEN** 一次 run 的 `--window` 为 70000、`--reserve` 为 100（触发线 4364，比保留预算 11200 还小）
- **THEN** 每一个需要装配的回合都进入压缩判定，且触发线本身是 4364 而不是负数
