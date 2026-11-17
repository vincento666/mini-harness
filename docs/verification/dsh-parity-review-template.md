# 对齐复核（alignment review）模板

**何时跑**：**每个 change 必做**，位置在 apply **之前**、与契约复核同一道（`docs/process/devops-loop.md` §0.4 第一道）。  
**对齐对象**：proposal 的 Why / What / Impact 与验收、design 的每条决策、spec 的每条 Requirement 与 Scenario、tasks 的完成判据；**有 DSH 对照的**，按 `docs/reference/dsh-alignment-checklist.md` 的十项逐条核对。

**调研与复核的分工**：调研在 propose 之前，产出「DSH 是什么 + 我们的建议」；复核在写代码之前，逐条核对「提案/规格/验收是否站得住」，把偏离标成建议。**简化与弱化是建议，由人裁决**，agent 不得自行把建议写成结论。

**时点**：propose 定稿之后、apply 之前。若发现设计级偏差，回到 design/spec 改，不进 apply；实现之后发现「设计声称 aligned、实现不是」，按缺陷修，不靠这份复核兜底。

## 输入

- change 的 proposal / design / spec / tasks / 验证契约（提案与验收标准是**第一对齐对象**）；
- DSH 出处：上游仓库的一手文件 URL + commit（README / `docs/subsystems/*.md` / 源码），或仓库内 `docs/reference/dsh-alignment-checklist.md` 指到的对应章节；`docs/dsh-reference/` 只当索引。

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
