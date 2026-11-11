# skill-invocation-policy 真实端点

**日期**：2026-11-11。`--provider deepseek`，chat 依次：`/user-only`、让模型调 `skill(user-only)`、让模型调 `skill(both)`。

## 观察

| 动作 | 事实 |
|---|---|
| `/user-only` | 打印「回答以【USER】开头。」；不开段 |
| `session/start.payload.skills` | 只有 `both`（user-only 不进模型清单） |
| 模型 `skill(user-only)` | `TOOL_ARGS_INVALID`：`技能 user-only 不可由模型调用` |
| 模型 `skill(both)` | `OK`，返回 `<skill_content name="both">`；回复以「【BOTH】」开头 |

## 结论

**通过**：`disable-model-invocation: on` 的技能只出现在人机命令面、模型工具拒绝并给出与「未知」不同的文本；默认技能两面都可用。
