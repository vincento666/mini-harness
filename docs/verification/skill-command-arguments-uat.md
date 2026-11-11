# skill-command-arguments UAT

**状态**：**agent 代跑**（用户明确指示「继续修补」后由 agent 验证，2026-11-11）；合并前由用户确认。

## 场次与观察

| 场次 | 动作 | 实际观察 | 结论 |
|---|---|---|---|
| S1 | chat `/tdd 帮我改一个函数` | 模型回复以「【TDD】」开头、列出三步；日志一条 `command/run`、一条 `user/message`（正文 + 指令）、一条 `segment/start` | 通过 |
| S2 | chat `/tdd`（不带指令） | 屏幕打印正文；日志一条 `command/run`，**没有** `user/message`、没有 `segment/start` | 通过 |
| S3 | host `POST {name:"tdd", arguments:"帮我改一个函数"}` | 202 `{"queued": false, "segment_id": "s1", "cursor": 2}`；日志一条 `user/message` + 一条段 | 通过 |

**一条「用起来别扭」**：`/skill <名字>` 不接受指令，带指令必须写成 `/<技能名> 指令`——两个入口看起来很像，但只有一个能带指令；文档里要显眼地说清楚。

**结论**：通过（agent 代跑）。
