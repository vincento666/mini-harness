# 对齐复核（alignment review）模板

**何时跑**：**每个 change 必做**——它是 code review 的一步，不是 DSH 专项。  
**对齐对象**：proposal 的 Why / What / Impact 与验收、design 的每条决策、spec 的每条 Requirement 与 Scenario、tasks 的完成判据；**有 DSH 对照的**，按 `docs/reference/dsh-alignment-checklist.md` 的十项逐条核对。

**调研与复核的分工**：调研在 propose 之前，产出「DSH 是什么 + 我们的建议」；复核在实现之后，逐条核对「实现是否兑现了提案/规格/验收」，并给建议标状态。**简化与弱化是建议，由人裁决**，agent 不得自行把建议写成结论。

**时点**：`code-review` 两轴之后、收尾四项/归档之前。若发现设计级偏差，回到 design/spec 而不是只改代码；若发现「设计声称 aligned、实现不是」，先标红再修。

## 输入

- change 的 proposal / design / spec / tasks（提案与验收标准是**第一对齐对象**）；
- `git diff <base>...HEAD`；
- DSH 出处：`docs/dsh-reference/` 对应章节，或
  `S:\Develop\agent_harness\re\verified\dsh\node_modules\@deepseek-ai/...` 的 README/代码。

## 输出

`docs/verification/<change-id>-dsh-review.md`

## 表

| 类别 | 对照点（提案/设计/规格/验收/DSH） | 提案或 DSH 说什么 | 实现是什么 | 结论 | 记账 |
|---|---|---|---|---|---|
| 提案 / 设计 / 规格 / 验收 / DSH |  |  |  | aligned / simplified / deferred | 理由、ADR、触发条件 |

## 结论词

- **aligned**：行为一致，或差异只在传输/命名且不改变语义；
- **simplified**：有意简化；必须写理由，必要时 ADR；
- **deferred**：明确后做；必须写触发条件。

## 判据

- 每条 Requirement / Scenario / 验收判据都有一行，MUST NOT 只挑 DSH 行；
- 每个出现在 spec/design 里的 DSH 对照点都有一行；
- 没有“看起来像对齐但未验证”的项；
- `simplified` 不藏代价，`deferred` 不写成“以后再说”；两者的**裁决人是人**；
- 发现的差异要么修，要么由人确认后记账；不允许静默消失。

## 示例

| 行为 | DSH | mini | 结论 | 记账 |
|---|---|---|---|---|
| 子代理 spawn | 有 | 有 | aligned | — |
| 子代理 fork | 有 | 不做 | deferred | ADR-0035；触发条件：需要 KV cache 复用 |
| compact timed stream | 有 | 暂不做 | simplified | 只保留 blocks；ADR 待补 |
