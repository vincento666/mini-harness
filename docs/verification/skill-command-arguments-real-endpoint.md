# skill-command-arguments 真实端点

**日期**：2026-11-11。`--provider deepseek`，chat 输入 `/tdd 帮我改一个函数`。

技能正文要求：回答必须以「【TDD】」开头，并严格列出三步。

## 观察

| 项 | 事实 |
|---|---|
| `command/run` | `name=tdd`，`raw_input=/tdd 帮我改一个函数` |
| `command/done` | `ok=true` |
| `user/message` | `<skill_content name="tdd">…</skill_content>` + 空行 + `帮我改一个函数` |
| `segment/start` | 一条 |
| 模型回复 | 以「【TDD】」开头，列出三步（红判据 → 最小实现 → 一次一个切片） |

## 结论

**通过**：命令 + 自然语言展开成一条含技能正文的用户消息，模型按正文约束回答；命令本身仍只落两件套。
