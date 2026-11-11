# M14 真实端点验收

**日期**：2026-11-11。`--provider deepseek`，模型 `deepseek-chat`。

## 场景

工作区 `/tmp/m14-real` 里放一个项目技能 `.minihns/skills/tdd/SKILL.md`，正文要求：

> 回答必须以「【TDD】」开头，并且严格按顺序列出三步：1. 先写一条会失败的测试。2. 再写最小实现让它变绿。3. 每次只做一个切片。

任务：`先用 skill 工具加载 tdd 技能，然后按它的要求说明你会怎么改一个函数`。

## 观察

| 事件 | 事实 |
|---|---|
| `tool/call` | `skill {"name": "tdd"}` |
| `tool/result` | `<skill_content name="tdd">` + `<skill_resources>`（技能文件路径）+ `<skill_instructions>`（正文） |
| 最终 `model/response` | 以「【TDD】」开头，并严格列出那三步 |

## 结论

**通过**：模型能发现清单之外的技能、用 `skill` 工具按需取正文、按正文的约束回答；正文来自日志里的 `tool/result`（回放不依赖磁盘当前内容）。
