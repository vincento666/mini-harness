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

## 与 DSH 的形状对照

DSH 的 `/name` 是**用户消息里空白分隔的 token**（可在句中），pre-step 把正文注入当步、不落命令事件；mini 是 chat 行首命令、展开成 `user/message` 并落两件套。「技能名 + 自然语言」的表面形状一致，机制差异记在 ADR-0038。

## 结论

**通过**：命令 + 自然语言展开成一条含技能正文的用户消息，模型按正文约束回答；命令本身仍只落两件套。
