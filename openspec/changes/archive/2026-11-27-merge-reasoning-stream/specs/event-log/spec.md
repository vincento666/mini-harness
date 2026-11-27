# Spec Delta

## ADDED Requirements

### Requirement: model/attempt 记录被重试掉的失败尝试

一次模型调用最终失败且此前已有重试或已交付前缀时，系统 SHALL 在 `error/model` 之前写一条 `model/attempt`：`step_id`、`status`（`error` / `aborted`）、`error_code`、`partial_blocks`（已交付前缀的块，无前缀为空数组）。`model/attempt` 是 log-only 诊断记录：MUST NOT 进入 `fold` 的模型历史、MUST NOT 被当作 assistant 消息重放给模型。

成功的一步 MUST NOT 写 `model/attempt`；用户取消且有已交付内容时写 `model/response`（`interrupted: true`）而不写 `model/attempt`，二者互斥。

#### Scenario: 失败带前缀先写 attempt

- **WHEN** provider 在已交付一段正文后报 `PROVIDER_SCHEMA_INVALID`
- **THEN** 日志有 `model/attempt`（status=error、partial_blocks 含那段正文），没有 `model/response`

#### Scenario: attempt 不进模型历史

- **WHEN** 会话后续继续，`fold` 重算模型上下文
- **THEN** messages 里没有来自 `model/attempt` 的条目
