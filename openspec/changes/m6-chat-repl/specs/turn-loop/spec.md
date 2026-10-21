## ADDED Requirements

### Requirement: 预算溢出是回合终止结果，会话是否继续由入口决定
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束**该回合**：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具。内核 MUST NOT 把「会话是否结束」写进回合语义——`session/end` 与退出码由入口决定：一次性 `minihns run` 据此结束 session 并以退出码 4 收尾，`minihns chat` 里会话 SHALL 回到提示符等下一条输入（ADR-0019）。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: REPL 里溢出之后会话继续
- **WHEN** 一次 chat 的某个回合段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该段有 `error/context` 与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）、没有 `session/end`，下一条输入开启新的回合段

## MODIFIED Requirements

### Requirement: 回合内事件携带 turn_id
系统 SHALL 在 `turn/start`、`context/assembled`、`model/request`、`model/response`、`user/message`、`tool/call`、`tool/result`、`turn/end` 的 payload 里写入 `turn_id`；同一回合内 `turn_id` 相同，跨回合 MUST NOT 重复。

#### Scenario: turn_id 与回合序号一一对应
- **WHEN** 一次 run 跑了 3 个回合
- **THEN** 日志里恰有 3 个不同的 `turn_id`，每个 `turn_id` 恰对应一条 `turn/start` 与一条 `turn/end`

### Requirement: 回合数上限由 --max-turns 决定
系统 SHALL 用 `--max-turns` 限制**一个回合段**的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。一次性 `minihns run` 里一次运行恰一个段；`minihns chat` 里每条输入是一个段，段用完上限 MUST NOT 结束会话（见 `chat-repl`）。

#### Scenario: 非法 max-turns 不产生日志
- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

## REMOVED Requirements

### Requirement: 预算溢出终止整个 session
**Reason**: 「终止整个 session」把入口策略写进了回合语义，与 ADR-0011 已确立的边界（内核 MUST NOT 决定会话是否结束）冲突；在 REPL 里它会让一次溢出杀掉整个会话，而 DSH 的溢出是请求级失败、会话不死（`dsh-compaction-basic/lib/index.js:861-887`）。
**Migration**: 由本 change 新增的「预算溢出是回合终止结果，会话是否继续由入口决定」接替；它的两条 scenario（「溢出回合没有 model/request」「取消在场时不为压缩调用模型」）原样搬进那条需求，一次性 run 的退出码 4 留在 `cli` 的「退出码只取自固定表」里。
