## ADDED Requirements

### Requirement: 一条输入开一个回合段，段的边界在日志里
系统 SHALL 把一条输入（一次性 run 的 prompt、REPL 的一条输入）展开成一个**回合段**，并把段的边界 durable 写进日志：段开始时写 `segment/start`（payload 含 `segment_id`），段结束时写 `segment/end`（payload 含 `segment_id`、该段最后一个回合的 `stop_reason`、该段实际跑掉的回合数 `turns`）。`segment_id` 在会话内连续编号（`s1`、`s2`…）且 MUST NOT 重复。一次性 `minihns run` 恰有一个段。`segment/*` MUST NOT 产出上下文里的消息。照 DSH：段的边界对应 DSH 的 `turn` 边界（`turn = phase.turn + 1` 后 `session.append("turn/start", {turn})`，编号单调且落日志），本项目的「回合」仍是 DSH 的 `step`（GLOSSARY）。

#### Scenario: 一次 run 恰一个段
- **WHEN** 一次 run 跑了一个回合就正常结束
- **THEN** 日志的类型序列是 `session/start`、`segment/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`segment/end`、`session/end`，`segment/end` 的 `stop_reason` 是 `MODEL_COMPLETED`、`turns` 为 1

#### Scenario: 段编号在会话内连续
- **WHEN** 一次 chat 跑两个段
- **THEN** 日志里恰有 `s1` 与 `s2` 各一条 `segment/start` 与一条 `segment/end`，没有第三个段编号

#### Scenario: 段级取消段的边界也写
- **WHEN** 一个段进行中收到取消信号
- **THEN** 日志里有 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `segment/end`（`stop_reason: ABORTED`），没有 `session/end`

### Requirement: 预算溢出是回合终止结果，会话是否继续由入口决定
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束**该回合**：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具。内核 MUST NOT 把「会话是否结束」写进回合语义——`session/end` 与退出码由入口决定：一次性 `minihns run` 据此结束 session 并以退出码 4 收尾，`minihns chat` 里会话 SHALL 回到提示符等下一条输入（ADR-0019）。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: REPL 里溢出之后会话继续
- **WHEN** 一次 chat 的某个段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该段有 `error/context`、`turn/end` 与 `segment/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）、没有 `session/end`，下一条输入开启新的段

## MODIFIED Requirements

### Requirement: 回合数上限由 --max-turns 决定
系统 SHALL 用 `--max-turns` 限制**一个回合段**的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。会话级 MUST NOT 设回合数上限：一次性 `minihns run` 恰一个段，`minihns chat` 里每条输入是一个段，段用完上限 MUST NOT 结束会话（见 `chat-repl`）。照 DSH：DSH 的交互循环对 `turn` 与 `step` 都不设轮数上限（`dsh-agent-loop` 的全部数值配置只有 `maxParallelToolCalls` 默认 10 与每 agent 的 `maxTokens`），带轮数上限的只有委派工具的 `maxRounds`（默认 256，用完返回 `budget-limited`）——那对应本项目的 seam ⑦ / M15 的「目标轮次与 `blocked`」，MUST NOT 与这里的 `max_turns` 混名。

#### Scenario: 非法 max-turns 不产生日志
- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 上限判的是段不是会话
- **WHEN** 一次 chat 的第一条输入用完 `max_turns = 2`
- **THEN** 该段的 `segment/end` 的 `stop_reason` 是 `MAX_TURNS`、`turns` 为 2，日志里没有 `session/end`，下一条输入开一个新的段并照样有 2 个回合的额度

## REMOVED Requirements

### Requirement: 预算溢出终止整个 session
**Reason**: 「终止整个 session」把入口策略写进了回合语义，与 ADR-0011 已确立的边界（内核 MUST NOT 决定会话是否结束）冲突；在 REPL 里它会让一次溢出杀掉整个会话，而 DSH 的溢出是请求级失败、会话不死（`dsh-compaction-basic/lib/index.js:861-887`）。
**Migration**: 由本 change 新增的「预算溢出是回合终止结果，会话是否继续由入口决定」接替；它的两条 scenario（「溢出回合没有 model/request」「取消在场时不为压缩调用模型」）原样搬进那条需求，一次性 run 的退出码 4 留在 `cli` 的「退出码只取自固定表」里。
