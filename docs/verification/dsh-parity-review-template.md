# DSH parity review 模板

**何时跑**：change 明确声称“对齐 DSH”、照抄 DSH 某个机制，或把 DSH 行为作为完成判据时。  
**何时不跑**：纯内部重构、纯存储/工具细节、文档整理，且没有 DSH 对照声明。

**时点**：`code-review` 之后、收尾四项/归档之前。若发现设计级偏差，回到 design/spec，而不是只改代码。

## 输入

- change 的 proposal / design / spec / tasks；
- `git diff <base>...HEAD`；
- DSH 出处：`docs/dsh-reference/` 对应章节，或
  `S:\Develop\agent_harness\re\verified\dsh\node_modules\@deepseek-ai/...` 的 README/代码。

## 输出

`docs/verification/<change-id>-dsh-review.md`

## 表

| 行为 | DSH | mini | 结论 | 记账 |
|---|---|---|---|---|
|  |  |  | aligned / simplified / deferred | 理由、ADR、触发条件 |

## 结论词

- **aligned**：行为一致，或差异只在传输/命名且不改变语义；
- **simplified**：有意简化；必须写理由，必要时 ADR；
- **deferred**：明确后做；必须写触发条件。

## 判据

- 每个出现在 spec/design 里的 DSH 对照点都有一行；
- 没有“看起来像对齐但未验证”的项；
- `simplified` 不藏代价，`deferred` 不写成“以后再说”；
- 发现的差异要么修，要么记账；不允许静默消失。

## 示例

| 行为 | DSH | mini | 结论 | 记账 |
|---|---|---|---|---|
| 子代理 spawn | 有 | 有 | aligned | — |
| 子代理 fork | 有 | 不做 | deferred | ADR-0035；触发条件：需要 KV cache 复用 |
| compact timed stream | 有 | 暂不做 | simplified | 只保留 blocks；ADR 待补 |
