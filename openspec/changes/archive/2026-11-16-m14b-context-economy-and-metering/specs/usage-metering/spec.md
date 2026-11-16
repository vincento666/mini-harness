## ADDED Requirements

### Requirement: 回合与会话的 token 四桶计量

系统 SHALL 从日志里每个 `model/response` 的 `usage` 聚合四个互不重叠的 bucket：`input_uncached`、`cache_read`、`cache_write`、`output`。`reasoning` 是 `output` 的细分，MUST NOT 再加一次。缺 `usage` 的回合 SHALL 跳过，MUST NOT 用估算值代替。

会话总量 SHALL 是各回合的求和；同一 `(turn, step)` 的最终 assistant 消息用量 SHALL 替换该样本，MUST NOT 重复计数。

#### Scenario: 四桶求和

- **WHEN** 两个回合分别报告 `input 100 / cache_read 20 / output 30` 与 `input 50 / output 10`
- **THEN** 会话总量是 `input_uncached 150 / cache_read 20 / cache_write 0 / output 40`

#### Scenario: reasoning 不加两次

- **WHEN** 某回合 `output` 为 30、其中 `reasoning` 为 12
- **THEN** 总量只加 30，不是 42

#### Scenario: 缺 usage 的回合跳过

- **WHEN** 某回合的 `model/response` 没有 `usage`
- **THEN** 该回合不出现在 `turns[]` 里，也不影响总量

### Requirement: 配置驱动的成本估算

系统 SHALL 从配置 `[pricing.<model>]` 读四类单价（每百万 token），并把金额算成 `Σ(bucket × 单价) / 1_000_000`。配置缺失或缺字段时金额 SHALL 为 `null`，MUST NOT 用内置价目表或猜测值。

#### Scenario: 有价目表出金额

- **WHEN** `[pricing.deepseek-chat]` 给出 `input = 0.27`、`output = 1.10`
- **THEN** `cost` 是按四桶与单价算出的数

#### Scenario: 缺价目表出 null

- **WHEN** 配置里没有对应模型的价格
- **THEN** `cost` 是 `null`，报告显示 `n/a`

### Requirement: `minihns usage` 的输出

系统 SHALL 提供 `minihns usage <session-id>`，输出 JSON：`turns[]`（每回合的四桶）、`total`（四桶之和）、`cost`（可为 `null`）。命令 MUST NOT 修改日志。

#### Scenario: 输出可被 E1 消费

- **WHEN** 对一个含两回合用量的会话跑 `minihns usage`
- **THEN** stdout 是合法 JSON，含 `turns`、`total`、`cost` 三个键
