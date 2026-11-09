# Spec Delta

## MODIFIED Requirements

### Requirement: 会话列表与状态

`GET /sessions` SHALL 返回本进程持有的会话列表，每项含 `session_id`、`status`（`idle` / `running` / `ended`）、`workspace`、`created_at`、`last_seq`、`turns`、`parent_session_id` 与 `depth`；根会话的 `parent_session_id` SHALL 是 `null`、`depth` 是 `0`。`GET /sessions/{id}` SHALL 返回同一形状的一条；未知 id SHALL 是 `404`。列表 MUST NOT 返回密钥或 `Authorization` 内容。

由 `subagent` 创建的子会话 SHALL 在收尾时出现在列表里（`status` 为 `ended`、`parent_session_id` 是父会话、`depth` 是父的 `depth + 1`），`GET /sessions/{id}` SHALL 能查到它。父会话的 `GET /sessions/{id}/events` MUST NOT 转发子会话的事件。

#### Scenario: 列表能看见刚开的会话

- **WHEN** 创建两个会话后 `GET /sessions`
- **THEN** 返回两条，`status` 与 `last_seq` 与各自日志一致

#### Scenario: 子会话带父子字段

- **WHEN** 一个子代理完成（或被取消）之后 `GET /sessions`
- **THEN** 列表里有那条子会话，`parent_session_id` 是父会话 id、`depth` 是 `1`、`status` 是 `ended`

#### Scenario: 父流不转发子流

- **WHEN** 订阅父会话的事件流，同时它的子代理在跑
- **THEN** 流里只有父会话自己的记录，子会话的 `session_id` 与 `session/start` 一次都不出现
