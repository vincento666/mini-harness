# skill-catalog-live 真实端点

**日期**：2026-11-12。`--provider deepseek`，三个独立工作区。

## S1/S2 · 首轮注入与会话中途加技能

工作区先放 `tdd`。任务：让模型用 bash 创建 `.minihns/skills/review/SKILL.md`，然后问它有哪些技能。

| 目录消息 | 内容 |
|---|---|
| seq 3 | `tdd` |
| seq 11 | `tdd` + `review` |

模型先调 `bash` 建文件，下一 turn 目录替换并含 `review`。

## S3 · 清空退休

任务：让模型用 bash 删除 `.minihns/skills` 下所有内容。

| 目录消息 | 内容 |
|---|---|
| seq 3 | 含 `tdd` |
| seq 11 | 「本会话当前没有可用技能。不要使用之前目录里的技能名。」 |

## S4 · 不完整

任务：让模型用 bash 把 `.minihns/skills` 权限改成 000。

| 目录消息 | 内容 |
|---|---|
| seq 3 | 含 `tdd`，`incomplete=false` |
| seq 13 | 「这次发现一个技能都没确认到…」，`incomplete=true` |

## 结论

**通过**：目录是消息、每 turn 重算；加、删、读不了三种变化都在下一 turn 反映，且带正确的 `incomplete` 元数据。
