# Spec Delta

## MODIFIED Requirements

### Requirement: 回合主循环按固定五步显式执行
系统 SHALL 对每个回合按固定顺序执行：写 `turn/start` → 折叠装配上下文（越线时先压缩并写 `compaction/summary`）并写 `context/assembled` → 调 Provider 并写 `model/request` 与 `model/response` → 派发工具调用并写 `tool/call` 与 `tool/result` → 写 `turn/end`。该顺序 MUST NOT 藏在回调或隐式钩子里；压缩 MUST NOT 成为第六步，它属于装配步之内。

#### Scenario: 两个回合的事件顺序可断言
- **WHEN** 一次 run 完成两个回合
- **THEN** 日志里事件类型按上述五步成组出现，且每个 `turn/end` 都在下一个 `turn/start` 之前

#### Scenario: 压缩不改变五步的顺序
- **WHEN** 某回合的装配触发了压缩
- **THEN** 该回合仍是 `turn/start` 开始、`turn/end` 收尾，`compaction/summary` 位于该回合的 `context/assembled` 之前

### Requirement: 停止判定写在 turn/end
系统 SHALL 在每条 `turn/end` 的 payload 里写 `stop_reason`，取值只允许 `MODEL_COMPLETED`、`TOOL_CALLS`、`MAX_TURNS`、`PROVIDER_ERROR`、`ABORTED`、`FENCE_DENIED`、`CONTEXT_WINDOW_EXCEEDED`。`TOOL_CALLS` 只用于「模型要求调工具、还要继续」的回合；`MODEL_COMPLETED` 只用于「模型不再要求继续」；`FENCE_DENIED` 只用于「本回合因围栏或审批拒绝而终止」；`CONTEXT_WINDOW_EXCEEDED` 只用于「本回合的上下文压缩之后仍然装不下」。`session/end` SHALL 记录整个 session 的最终 `stop_reason` 与回合总数。

#### Scenario: 模型不请求工具即停止
- **WHEN** Provider 返回的 `tool_calls` 为空
- **THEN** 该回合 `stop_reason` 为 `MODEL_COMPLETED`，且不再开始下一回合

#### Scenario: 模型要求调工具时回合以 TOOL_CALLS 收尾
- **WHEN** Provider 返回的 `tool_calls` 非空且回合数未达 `--max-turns`
- **THEN** 该回合 `stop_reason` 为 `TOOL_CALLS`，且紧接着开始下一回合

#### Scenario: 达到回合上限即停止
- **WHEN** 已完成的回合数达到 `--max-turns`
- **THEN** 最后一个回合的 `stop_reason` 为 `MAX_TURNS`（即使该回合也要求调工具），`session/end` 被写入，run 以退出码 0 结束

#### Scenario: 围栏拒绝的回合以 FENCE_DENIED 收尾
- **WHEN** 某回合派发工具时发生围栏或审批拒绝
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `FENCE_DENIED`，`session/end` 的最终 `stop_reason` 也是 `FENCE_DENIED`

#### Scenario: 预算溢出的回合以 CONTEXT_WINDOW_EXCEEDED 收尾
- **WHEN** 某回合的装配压缩之后预算读数仍超过触发线
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `CONTEXT_WINDOW_EXCEEDED`，`session/end` 的最终 `stop_reason` 也是它

## ADDED Requirements

### Requirement: 预算溢出终止整个 session
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束整个 session：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具，且 `session/end` MUST 被写出。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5
