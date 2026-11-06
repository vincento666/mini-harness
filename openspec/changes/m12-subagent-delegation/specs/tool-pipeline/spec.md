# Spec Delta

## MODIFIED Requirements

### Requirement: 工具并发类别与 barrier

`ToolDefinition` SHALL 声明 `ConcurrencyClass`：`parallel`（只读/无副作用）或 `exclusive`（会改动/需独占）。同一时刻在跑的 `parallel` SHALL ≤ 8；`exclusive` SHALL ≤ 1，并且是 barrier：它之前声明的调用先完成，之后声明的调用等它完成。`tool/call` SHALL 按声明顺序落盘，`tool/result` SHALL 按完成顺序落盘。

`subagent` SHALL 是 `parallel` 类别：同一批声明的多个子代理 SHALL 并发执行，父会话只收它们各自的最终结果。额度耗尽（`ACTIVATION_LIMIT_REACHED`）与深度超限（`DEPTH_EXCEEDED`）SHALL 是 `tool/result` 的结果词，MUST NOT 抛出异常打断父回合。

#### Scenario: 并行只读批次真并发

- **WHEN** 同一批声明 4 个 `parallel` 调用，每个阻塞 0.1 s
- **THEN** 批次 wall-clock 明显小于串行 0.4 s，且同时最多 8 个在跑

#### Scenario: 改动调用是 barrier

- **WHEN** 同一批是 `read → write → read`
- **THEN** 第一个 `read` 在 `write` 开始前完成，第三个 `read` 在 `write` 完成后开始

#### Scenario: 结果按完成顺序

- **WHEN** 两个 `parallel` 调用完成顺序与声明顺序相反
- **THEN** 两条 `tool/result` 按完成顺序落盘，`tool/call` 仍按声明顺序

#### Scenario: 同批两个子代理并发

- **WHEN** 同一批声明两个 `subagent`，两个子任务的模型回合各阻塞一段
- **THEN** 两段阻塞重叠，父日志有两条 `tool/result`，按完成顺序落盘

#### Scenario: 额度用尽仍是结果

- **WHEN** 父会话的活跃子代理已经到了 `maxActiveSubagents`
- **THEN** 该次调用的结果是 `ACTIVATION_LIMIT_REACHED`，父回合继续
