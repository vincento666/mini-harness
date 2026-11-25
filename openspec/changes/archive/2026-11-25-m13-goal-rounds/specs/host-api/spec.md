# Spec Delta: host-api

## MODIFIED Requirements

### Requirement: 消息开一个段，段进行中排队

`POST /sessions/{id}/messages` SHALL 在会话空闲时开一个段、写 `user/message` 并返回 `202`；段进行中再发 SHALL 进入深度为 1 的队列并返回 `202` 与 `queued: true`；队列已满 SHALL 返回 `429`；空消息 SHALL 返回 `400`。同一会话同一时刻 MUST NOT 有两个段在跑。

段收尾后，只要队列非空，SHALL 先开会话队列里的下一条人类消息；队列为空且目标 `active`、已武装、还有轮次额度时，SHALL 自动开下一 goal 轮。也就是说 host 与 `chat` / `run` 共用同一套段后收尾（见 `turn-loop` 的「段后收尾只有一份实现」）；host MUST NOT 只执行 `/goal` 命令而不驱动轮次。

#### Scenario: 第二句在段进行中排队

- **WHEN** 第一句已经让段跑起来，立刻再 POST 一句
- **THEN** 第二次返回 202 且 `queued` 为 true，第一段收尾后第二句自动开下一个段，日志里两条 `user/message` 的先后与请求一致

#### Scenario: 队列已满

- **WHEN** 已有一段在跑、队列里已有一句，再 POST 第三句
- **THEN** 第三次返回 429

#### Scenario: host 自动续跑目标轮次

- **WHEN** 人类段里的模型调用 `create_goal` 建了一个上限为 2 的目标，该人类段正常收尾
- **THEN** 不需要再来一条 `POST /messages`：日志里出现 goal 来源的 `user/message` 与新的段，跑满两轮后落 `blocked{round-limit}`

#### Scenario: 人话先于自动轮次

- **WHEN** 一个 goal 轮次正在跑，客户端 POST 了一条人类消息；该轮次正常收尾
- **THEN** 队列里的消息先开人类段；它收尾之后才出现下一 goal 轮

#### Scenario: 回答未决问题

- **WHEN** 一个 goal 轮次因 `ask_user` 超时以未决问题收尾
- **THEN** 会话回到 `idle`、目标仍 `active`；下一次 POST 的消息开一个人类段，收尾后自动接下一 goal 轮，`rounds_started` 不因人类段推进

#### Scenario: 命令面 resume 立刻驱动

- **WHEN** 会话空闲、目标 `paused`，客户端 POST `/commands` 执行 `/goal resume`
- **THEN** 响应 `ok` 为真后立刻出现 `segment/start` 与 `source.round == rounds_started + 1` 的 goal 消息，不需要再 POST `/messages`
