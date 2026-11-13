# m14a-workspace-contract UAT

**状态**：等人跑（ADR-0025）。四场。

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | 项目根放一份 `AGENTS.md`，写一条可观察的约定（例如「回复开头先写 `收到`」），跑一次 `minihns run` | 模型按约定回复；日志里有 `source: "workspace-instructions"` 的消息 |
| S2 | 再在 `~/.mini-harness/AGENTS.md` 放一条不同的约定，跑一次 | 消息里先出现用户全局段、后出现项目段；两条约定都生效 |
| S3 | 把项目 `AGENTS.md` 写到超过 16 KiB | 消息不超过上限，含 `Workspace instruction budget:` 通知并指名被截断的路径；模型仍能读到前段 |
| S4 | 两个文件都不放，跑一次 | 日志里没有 `workspace-instructions` 消息，模型正常回答 |

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | | | |
| S2 | | | |
| S3 | | | |
| S4 | | | |

**结论**：通过 / 不通过：
