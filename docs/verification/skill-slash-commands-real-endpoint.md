# skill-slash-commands 真实端点检查

**日期**：2026-11-11。`--provider deepseek`，chat 输入 `/tdd` 与 `/help`。

## 观察

| 输入 | 输出 | 日志 |
|---|---|---|
| `/tdd` | 打印技能正文（「第一条：先写红判据。」） | `command/run name=tdd` + `command/done ok=true` |
| `/help` | `命令：/skills / /skill / /tdd` | 不落日志 |

## 结论

**通过**：直接技能命令走的是与 `/skill tdd` 同一条读取路径；`/help` 按当前会话的技能清单列出 `/tdd`；两条都不开段、不写 `user/message`。
