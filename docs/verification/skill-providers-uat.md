# skill-providers UAT

**状态**：等人跑（ADR-0025）。四场。

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | 配 `[subagent.presets.reader.skills] kind="filesystem"`、`dirs=["sk"]`，全局与层里各放一个 `tdd` | 子会话看到层里那份；父会话是全局那份 |
| S2 | 层里放一个全局没有的 `review` | 子会话的目录与 `/skills` 有它；父没有 |
| S3 | 会话中途新建技能后再 `/skills` | `/skills` 与模型目录都看到 |
| S4 | 把 `kind` 写成 `remote` | 退出码 2、`INVALID_ARGUMENT`、无日志 |

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | | | |
| S2 | | | |
| S3 | | | |
| S4 | | | |

**结论**：通过 / 不通过：
