# Spec Delta

## MODIFIED Requirements

### Requirement: 触发线由固定公式给出

系统 SHALL 用 `floor(min(W × threshold_ratio, W − O − headroom_tokens))` 给出压缩触发线（W 是 `window`、O 是 `reserve`）；`threshold_ratio` 与 `headroom_tokens` 来自有效配置，默认分别为 `0.8` 与 `65536`。该公式算出负数时触发线 SHALL 取 0——触发线对任意合法的 W、O 与参数都是全函数。取 0 只意味着每次装配都尝试一次压缩，不构成配置错误。触发线 MUST NOT 被用作溢出判据（见「溢出判据是压力预算，触发线只决定要不要压缩」）。

#### Scenario: 默认参数下的触发线是一个可断言的数
- **WHEN** `window` 为 128000、`reserve` 为 8192，两个压缩参数取默认值
- **THEN** 触发线为 54272（`W − O − 65536` 比 `W × 0.8` 小）

#### Scenario: 小窗口下每次装配都越线
- **WHEN** 一次 run 的 `--window` 为 70000、`--reserve` 为 100（触发线 4364，比默认保留预算 11200 还小）
- **THEN** 每一个需要装配的回合都进入压缩判定，且触发线本身是 4364 而不是负数

#### Scenario: 自定义比例与 headroom 改变触发线
- **WHEN** `window` 为 100000、`reserve` 为 1000、`compaction_threshold_ratio = 0.5`、`compaction_headroom_tokens = 1000`
- **THEN** 触发线为 50000（`W × 0.5` 比 `W − O − 1000` 小）

### Requirement: 遮蔽范围保留尾部且不拆散配对

系统 SHALL 在压缩时保留尾部：保留预算在 `compaction_retain_tokens > 0` 时 SHALL 是它，否则 SHALL 是 `floor(W × compaction_retain_ratio)`（W 是 `window`；ratio 默认 `0.16`）。遮蔽范围是从对话体第一条可遮蔽记录起的连续 seq 区间，其选择使未被遮蔽的记录估算不超过保留预算。`session/start` 与既有的 `compaction/summary` MUST NOT 进入遮蔽范围；切点 MUST NOT 落在一条 assistant 工具请求与它的 `tool/call` 或 `tool/result` 之间，此时整组一起遮蔽。没有可遮蔽内容时 SHALL 不产生遮蔽范围。

#### Scenario: 保留预算是窗口的 16%
- **WHEN** `window` 为 128000，`compaction_retain_ratio` 取默认值，`compaction_retain_tokens` 为 0
- **THEN** 保留预算为 20480

#### Scenario: retain_tokens 覆盖 ratio
- **WHEN** `window` 为 128000、`compaction_retain_ratio = 0.5`、`compaction_retain_tokens = 3000`
- **THEN** 保留预算为 3000，而不是 64000

#### Scenario: 自定义 ratio 缩小保留尾部
- **WHEN** `window` 为 100000、`compaction_retain_ratio = 0.10`、`compaction_retain_tokens = 0`
- **THEN** 保留预算为 10000；同样的日志在默认 0.16 下保留 16000

#### Scenario: 切点不拆散一组工具往返
- **WHEN** 尾部切点落在一组 assistant 工具请求与它的工具结果之间
- **THEN** 遮蔽范围的 `end` 在该组最后一条记录之后，整组一起被遮蔽

#### Scenario: 既有摘要不被遮蔽
- **WHEN** 一次压缩发生在已有 `compaction/summary` 之后
- **THEN** 遮蔽范围的 `start` 大于那条记录的 `seq`

#### Scenario: 没有可遮蔽内容时不产生范围
- **WHEN** 对话体里只剩一条本身就超预算的记录
- **THEN** 不产生遮蔽范围，也不写 `compaction/summary`

## ADDED Requirements

### Requirement: 压缩参数的取值域在 session 开始之前校验

系统 SHALL 在 session 开始之前校验四个压缩参数：`0 < compaction_threshold_ratio <= 1`、`0 < compaction_retain_ratio <= 1`、`compaction_headroom_tokens >= 0`、`compaction_retain_tokens >= 0`。非法值 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT`、且 MUST NOT 创建 session 日志；`window − reserve <= 0` 仍按原规则单独失败。

#### Scenario: ratio 越界是参数错误
- **WHEN** 配置文件写 `compaction_retain_ratio = 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 负的 headroom 是参数错误
- **WHEN** 配置文件写 `compaction_headroom_tokens = -1`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 合法边界值照常开始
- **WHEN** `compaction_threshold_ratio = 1`、`compaction_retain_ratio = 1`、`compaction_headroom_tokens = 0`、`compaction_retain_tokens = 0`，且压力预算为正
- **THEN** session 正常开始，`session/start` 记录这四个值
