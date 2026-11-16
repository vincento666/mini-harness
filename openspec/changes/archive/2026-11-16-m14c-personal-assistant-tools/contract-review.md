# 契约复核记录（plan 切片）

**日期**：2026-11-16。子代理（只读、独立上下文），两轮。按 §0.4：GAPS 先改契约，同一契约最多两轮。

## 第一轮：GAPS（8 条）

| # | 严重度 | 缺口 |
|---|---|---|
| A | blocker | `subagent` 标记为无副作用，但子会话继承工具表，可绕过计划模式写文件 |
| B | major | 没有断言 `approval/request` 带 `purpose: "plan-review"` 与计划正文 |
| C | major | 只断言结果词，没断言「副作用前拦截、文件未变」 |
| D | major | `/plan off` 没有场景与判据 |
| E | major | `UNAVAILABLE` / 人关闭复核被当成批准 |
| F | minor | `replay` 相等没有场景 |
| G | minor | 「提示可读」不可证伪 |
| H | minor | `foldPlanMode` / `Approve` 与实现命名不一致；change 名与 roadmap 不一致 |

处置：契约第二版改四路拦截（加 `subagent`）、固定前缀 `计划模式：`、补 payload/正文断言、补 `/plan off`、`UNAVAILABLE`、`replay` 三个场景；change 更名为 `m14c-personal-assistant-tools`；spec/design/tasks 同步。

## 第二轮：PASS

逐条核对 A–H 均为 CLOSED，无遗留影响正确性或既定需求的项。

**结论**：契约通过，可进入 apply。该 blocker 是这套机制第一次运行就抓到的真实绕过路径，已写进坏法清单与 design D2。
