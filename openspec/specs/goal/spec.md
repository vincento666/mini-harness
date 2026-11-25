# goal Specification

## Purpose
TBD - created by archiving change m13-goal-rounds. Update Purpose after archive.
## Requirements
### Requirement: 目标是会话里的单值状态

系统 SHALL 以 `goal/updated` 事件记录当前目标，载荷为 `{goal: <快照> | null}`；快照 MUST 含 `id`、`revision`、`objective`、`phase`、`max_rounds`、`rounds_started`，`phase` 取 `active` / `paused` / `blocked` / `complete` 之一，`blocked` 时 MUST 另含 `blocked_reason {code, message}`（两者非空），非 `blocked` 时 MUST NOT 带它。`null` SHALL 表示目标被清除。纯折叠 SHALL 取最后一条的载荷；`goal/updated` MUST NOT 改写历史事件。

同一会话 MUST 至多一个非 `complete` 的目标。

`revision` SHALL 只随**控制面动作**（`create`、`edit`、`pause`、`resume`、`complete`、`blocked`、`clear`）递增；轮次推进 MUST NOT 改 `revision`——否则模型在轮内拿到的引用会立刻过期。

#### Scenario: 创建后可读回同一份快照

- **WHEN** 人类在会话里提出一个目标，模型调用 `create_goal`
- **THEN** 日志恰新增一条 `goal/updated`，其 `goal.revision == 1`、`phase == "active"`、`rounds_started == 0`；`get_goal()` 返回同一份快照与 `armed == true`（创建即武装，照 DSH 的 `create`）

#### Scenario: 轮次推进不改 revision

- **WHEN** 一个目标跑满三轮，每轮都写 `goal/updated`
- **THEN** 三条 `goal/updated` 的 `revision` 全为 `1`，`rounds_started` 依次为 1、2、3

#### Scenario: 控制面动作递增 revision

- **WHEN** 对同一目标连续执行 `edit` 与 `pause`
- **THEN** 两条 `goal/updated` 的 `revision` 依次为 2 与 3

#### Scenario: 清除留下 null

- **WHEN** `/goal clear` 执行
- **THEN** 日志新增 `goal/updated {goal: null}`；`get_goal()` 返回 `null`；之前的历史快照仍在日志里

### Requirement: goal 工具及其权威

系统 SHALL 提供 `get_goal()`、`create_goal(objective, max_rounds?)`、`update_goal(goal_id, revision, action, objective?, max_rounds?, blocked_reason?)` 三个工具，`action` 取 `edit` / `pause` / `resume` / `complete` / `blocked`。所有工具结果 SHALL 是同一份紧凑 JSON：无目标时 `{"goal": null}`，否则含快照与 `armed`。

`create`、`edit`、`pause`、`resume` MUST 只在本段由人类来源的 `user/message` 开启时成立；`entry == "subagent"` 的会话 MUST NOT 具备该权威，返回 `GOAL_AUTHORITY_REQUIRED`。

`create` 在存在非 `complete` 目标时 MUST 返回 `GOAL_ALREADY_ACTIVE`；上一个目标已 `complete` 时 SHALL 允许创建**新**目标（新 `id`、`revision == 1`、`rounds_started == 0`）。

`update_goal` 的 `goal_id` 或 `revision` 与当前值不符时 MUST 返回 `GOAL_REF_STALE` 且不落事件。

`edit` SHALL 是部分替换：至少一个有效字段（`objective` 非空串、`max_rounds` 为正整数），空串与 `0` 视为省略；其它 `action` MUST 忽略这两个字段。`create_goal` 与 `edit` 的 `max_rounds` SHALL 以部署策略的 `max_rounds` 为**硬顶**：请求值大于它时按它落，MUST NOT 让模型用一个大数字绕开预算；要跑更多轮只能改部署配置。

`resume` SHALL：对 `active` 且未武装的目标置真；对 `blocked` 的目标置 `active`、清空 `blocked_reason`、置真；对 `paused` 的目标 MUST 返回 `GOAL_RESUME_BY_TOOL_DENIED`（该转换只由 `/goal resume` 完成）。

`complete` SHALL 把非 `complete` 目标置 `complete` 并解除武装；`blocked` SHALL 按「阻塞需要轮数门槛」Requirement 判定。

相位不允许该动作时 MUST 返回 `GOAL_INVALID_TRANSITION` 且不落事件：`pause` 只在 `active`，`complete` 只在非 `complete`，`blocked` 只在 `active`，`resume` 在 `complete` 或轮次已用尽时拒绝（`paused` 归人，见 `GOAL_RESUME_BY_TOOL_DENIED`）。

#### Scenario: 单目标约束

- **WHEN** 当前目标 `active`，模型再次调用 `create_goal`
- **THEN** 结果是 `GOAL_ALREADY_ACTIVE`，日志不新增 `goal/updated`

#### Scenario: complete 之后可另起一个目标

- **WHEN** 目标 A 已 `complete`，模型调用 `create_goal` 并给出新的 objective
- **THEN** 新快照的 `id` 与 A 不同、`revision == 1`、`rounds_started == 0`

#### Scenario: 旧 revision 被拒

- **WHEN** 目标已到 `revision == 3`，调用方仍提交 `revision == 2`
- **THEN** 结果是 `GOAL_REF_STALE`，`phase` 与 `rounds_started` 不变

#### Scenario: 子会话没有创建权

- **WHEN** 子会话（`entry == "subagent"`）里的模型调用 `create_goal`
- **THEN** 结果是 `GOAL_AUTHORITY_REQUIRED`，日志不新增 `goal/updated`

#### Scenario: 工具不能恢复已暂停的目标

- **WHEN** `phase == "paused"`，模型调用 `update_goal(action="resume")`
- **THEN** 结果是 `GOAL_RESUME_BY_TOOL_DENIED`，`phase` 仍为 `paused`，`armed` 仍为 `false`

#### Scenario: 撞上限之后能人工续跑

- **WHEN** 目标因轮次用尽落到 `blocked {code: "round-limit"}`，用户把 `max_rounds` 调大后输入 `/goal resume`
- **THEN** 新快照 `phase == "active"`、无 `blocked_reason`、`armed == true`，随后出现新的 goal 来源消息

#### Scenario: edit 是部分替换

- **WHEN** 当前 `objective` 为 P、`max_rounds` 为 3，调用 `edit` 只给 `max_rounds: 5`
- **THEN** 新快照 `objective` 仍为 P、`max_rounds == 5`、`phase` 不变

#### Scenario: 无目标时读取不报错

- **WHEN** 会话里从未创建目标，模型调用 `get_goal`
- **THEN** 结果是 `OK`，内容为 `{"goal": null}`

### Requirement: 轮次是 goal 来源的用户消息

`user/message` 的载荷 SHALL 含 `source`：`{kind: "user"}` 或 `{kind: "goal", goal_id, revision, round}`；缺该字段的旧日志 MUST 按 `{kind: "user"}` 读。

goal 来源消息的正文 SHALL 是一个 `<goal_round>` 块，至少含 `Objective: <JSON 引号的目标原文>` 与 `Round: <轮号>/<轮次上限>` 两行，以及一段终局约束：完成则调用 `update_goal` 标 `complete`、已达阻塞门槛则标 `blocked`、否则现在执行下一步具体动作；只复述计划而不调用工具会被视为停滞。正文 MUST NOT 为空。

goal 来源消息的 `round` MUST 等于写入时快照的 `rounds_started + 1`，`revision` MUST 等于写入时快照的 `revision`。`replay` MUST 在下列任一情形判日志不自洽：轮号非正、同一 `goal_id` 内轮号跳号、轮号超过该目标的 `max_rounds`、`revision` 与当前快照不符、`phase` 已停。校验 SHALL 按 `goal_id` 分组——不同目标各自从 1 起算，重复轮号合法。

#### Scenario: 轮号连续

- **WHEN** 一个上限为 3 的目标连跑三轮
- **THEN** 三条 goal 来源 `user/message` 的 `source.round` 依次为 1、2、3，`source.goal_id` 与 `goal/updated` 的 `id` 相同

#### Scenario: 正文带目标与轮号

- **WHEN** 目标是「修好失败的用例」、上限 3，跑第 2 轮
- **THEN** 该条 `user/message` 的 `content` 含 `Objective: "修好失败的用例"` 与 `Round: 2/3`，且不是空串

#### Scenario: 换目标后轮号重新从 1 起算

- **WHEN** 日志里目标 A 跑三轮后 `complete`，随后目标 B 跑一轮
- **THEN** `replay` 成功，B 的 `source.round == 1`

#### Scenario: 跳号被拒

- **WHEN** 回放一份把同一目标的第二条 goal 消息 `round` 写成 3 的日志
- **THEN** `replay` 以日志不自洽结束，退出码非零

#### Scenario: 旧日志缺 source 仍可读

- **WHEN** 回放一份 `user/message` 不带 `source` 的旧日志
- **THEN** `replay` 成功，该消息按人类来源计入

### Requirement: 轮次驱动与上限

段结束且 `turn/end.stop_reason` 不在 `{ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED, MAX_TURNS}` 之内时，系统 SHALL 检查当前目标：`phase == active`、`armed` 为真、`rounds_started < max_rounds` 三者同时成立才 SHALL 开新段，并按顺序写 `segment/start`、goal 来源的 `user/message`、该段首条 `turn/start`、该段首条 `context/assembled`、`goal/updated`（`rounds_started` 递增，`revision` 不变）。三者任一不成立 MUST NOT 开新段。

`rounds_started` 是**当前 goal 轮次的序号**：goal 消息被准入（`context/assembled` 落盘）之后它就是本轮的 n；人类段的 `user/message` MUST NOT 推进它。`max_rounds` 是**单个目标**的轮次上限，不是会话的段数上限。`max_rounds` 由 CLI 的 `minihns goal <id> edit --max-rounds` 或模型的 `update_goal edit` 改写；会话内的 `/goal edit` 只改正文。

goal 轮次以零个成功派发的工具调用收尾（模型只说话、没有动作）时，系统 SHALL 累加「连续空转轮数」；连续轮数达到 `[goal] stall_rounds` 时 SHALL 解除武装、MUST NOT 开下一段，`phase` MUST 保持不变（完成与否不是驱动能替模型判断的事实）。`stall_rounds` 缺省为 `2`：一轮可能只是「想清楚再答」，连续两轮才判死循环；配置 `0` 表示关闭该闸门（完全对齐 DSH，只由 `complete` / `blocked` / `max_rounds` 决定）。任何有工具调用的 goal 轮次把计数清零；人类段 MUST NOT 受这条约束，并把计数清零。判据单位是**轮**（一次准入），不是回合；一轮里只要有一个成功派发的工具调用就不算空转。

轮次额度 SHALL 在**首条 `context/assembled` 落盘之后**消耗：该轮真的装进了上下文才算数；该段在装配完成之前失败（provider 立刻失败、注入失败、折叠失败、装配内压缩失败）MUST NOT 计入 `rounds_started`——这是 DSH「进模型历史才计数」在 mini 的等价物。

`rounds_started` 已达 `max_rounds` 时，系统 SHALL 写 `goal/updated` 把 `phase` 置 `blocked`、`blocked_reason.code` 置 `round-limit`，并 MUST NOT 再起轮次。

写日志失败时 MUST NOT 静默重试：落 `error/*`、结束会话、以非零退出码收尾。

段以 `ABORTED` 收尾时，系统 SHALL 把 `phase` 置 `paused` 并解除武装；以其余四种失败收尾时 SHALL 只解除武装（`phase` 保持，等人 `/goal resume`）。

#### Scenario: 达标即续跑

- **WHEN** 段以 `MODEL_COMPLETED` 收尾，目标 `active`、已武装、`rounds_started == 1`、`max_rounds == 3`
- **THEN** 日志依次出现 `segment/start`（新 `segment_id`）、`source.round == 2` 的 `user/message`、`turn/start`、`context/assembled`、`rounds_started == 2` 的 `goal/updated`

#### Scenario: 一轮空转不误杀

- **WHEN** 一个 goal 轮次零工具调用，上一轮有工具调用（计数从 0 起），目标仍 `active`、已武装、还有额度
- **THEN** 驱动照常开下一段；`segment/end.tool_calls == 0` 只作审计

#### Scenario: 连续两轮空转按默认阈值停

- **WHEN** `[goal]` 没有 `stall_rounds`（缺省 2），连续两个 goal 轮次零工具调用
- **THEN** 第二个轮次之后不再开段、武装位解除、`phase` 仍 `active`、计数清零；下一次 `/goal resume` 从零重新计

#### Scenario: 关闭闸门就完全对齐 DSH

- **WHEN** `[goal] stall_rounds = 0`，goal 轮次连续空转
- **THEN** 驱动一路开到 `max_rounds`，最后落 `blocked{round-limit}`，不因空转提前停

#### Scenario: 上限不再开段

- **WHEN** `rounds_started == max_rounds` 且目标仍 `active`
- **THEN** 不出现新的 `segment/start`，出现一条 `goal/updated`：`phase == "blocked"`、`blocked_reason.code == "round-limit"`

#### Scenario: 早失败不消耗轮次

- **WHEN** 第 2 轮的段刚写完 goal 消息，provider 在 `turn/start` 之前失败
- **THEN** `rounds_started` 仍为 1（这一轮不算数），且不再自动续跑

#### Scenario: 取消把目标置暂停

- **WHEN** 第 2 轮进行中被取消，段以 `ABORTED` 收尾
- **THEN** 日志新增 `goal/updated`：`phase == "paused"`；`get_goal()` 的 `armed == false`

#### Scenario: 失败收尾解除武装

- **WHEN** 段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 不出现新的段、不出现 goal 来源消息；`get_goal()` 的 `armed == false`

#### Scenario: 写不进日志就停

- **WHEN** 续跑要写的 `goal/updated` 落盘失败
- **THEN** 不出现新的段，日志里留下 `error/*`，命令以非零码结束

### Requirement: 未回答的问题把控制权交回人类

一个段在收尾时若仍带着**没有答案的问题**（`ask_user` 返回 `QUESTION_UNAVAILABLE`，日志有 `question/asked` 且没有配对的 `question/answered`），驱动 MUST NOT 再开自动轮次，SHALL 回到入口等待人类输入；目标 MUST 保持 `active` 与武装，MUST NOT 落 `paused`。人类的下一段是一条 `{kind: "user"}` 消息，MUST NOT 计入 `rounds_started`；该段结束之后，驱动 SHALL 照常判定并开下一 goal 轮。已 `blocked` / `complete` / `paused` 的目标 MUST NOT 被这条改写。`rounds_started >= max_rounds` 时以额度用尽为准（先落 `blocked{round-limit}`）。未决问题是**段作用域**：每个段开头清空，MUST NOT 跨段继承。

#### Scenario: 轮次里问不到人就交回控制权

- **WHEN** 第 1 轮里 `ask_user` 返回 `QUESTION_UNAVAILABLE`，该段以 `MODEL_COMPLETED` 收尾
- **THEN** 日志没有第 2 段的 goal `user/message`；`phase` 仍为 `active`、`armed` 仍为真；`question/asked` 有一条且没有 `question/answered`

#### Scenario: 回答是人的一段，不是 goal 轮

- **WHEN** 上一场之后人输入答案
- **THEN** 该段写一条 `source.kind == "user"` 的 `user/message`；`rounds_started` 不变；该段以 `MODEL_COMPLETED` 收尾后，才出现 `source.round == 2` 的 goal 消息

#### Scenario: 段首清空

- **WHEN** 上一段留了未决问题，新的一段里没有再提问
- **THEN** 新段结尾不因上一段的问题而停止（标记已在 `segment/start` 清空）

### Requirement: 阻塞需要轮数门槛

`update_goal(action="blocked")` MUST 要求 `blocked_reason` 非空；`rounds_started` 小于 `blocked_after_consecutive_rounds` 时 MUST 返回 `GOAL_BLOCK_TOO_EARLY` 且不落事件。被接受时快照的 `blocked_reason.code` MUST 为 `model-reported`，`message` 为调用方给出的原文。

`create_goal` 显式给出的 `max_rounds` 小于门槛时 MUST NOT 拒绝创建：该目标只能走到 `round-limit`，`model-reported` 这条出口对它关闭——这是调用方的显式选择。部署级的 `[goal]` 组合不允许这样配，见 `config-layering` delta。

#### Scenario: 两轮就报阻塞被拒

- **WHEN** `rounds_started == 2`、门槛为 3，模型调用 `blocked`
- **THEN** 结果是 `GOAL_BLOCK_TOO_EARLY`，`phase` 仍为 `active`

#### Scenario: 三轮后可报阻塞

- **WHEN** `rounds_started == 3`，模型带 `blocked_reason` 调用 `blocked`
- **THEN** `phase == "blocked"`、`blocked_reason.code == "model-reported"`、`message` 与入参相同

#### Scenario: 相位不允许的动作被拒

- **WHEN** 目标 `phase == "blocked"`，模型调用 `update_goal(action="pause")`
- **THEN** 结果是 `GOAL_INVALID_TRANSITION`，`phase` 仍为 `blocked`，日志不新增 `goal/updated`

#### Scenario: 空原因被拒

- **WHEN** `blocked_reason` 为空串
- **THEN** 结果是 `TOOL_ARGS_INVALID`，`phase` 不变

### Requirement: 武装是进程内状态

`armed` MUST NOT 出现在任何事件载荷里，只活在会话运行期。会话启动、`--resume` 恢复、以及从日志重建会话之后，`armed` MUST 为假；只有 `/goal resume` 或 `update_goal(action="resume")` 能把它置真。`pause`、`complete`、`blocked`、达到轮次上限、以及以失败收尾的段 MUST 把它置假。

#### Scenario: 恢复后不自动跑

- **WHEN** 用 `--resume` 恢复一个 `active` 目标的会话
- **THEN** 第一次模型请求之前日志里没有新的 goal 来源消息，`get_goal()` 的 `armed` 为 `false`

#### Scenario: 恢复后人工续跑

- **WHEN** 恢复后用户输入 `/goal resume`
- **THEN** 下一条 `goal/updated` 的 `revision` 递增、`phase` 仍 `active`，`armed` 为 `true`，随后出现 goal 来源消息

### Requirement: 人类消息优先于自动轮次

同一会话里，段进行中投递的人类消息 SHALL 在该段收尾后**先**跑；只要待跑队列非空，入口 MUST NOT 先开 goal 轮次。人类段结束后，入口 SHALL 重新判定目标；队列里再有人话就继续先跑人话。`chat` 没有段中队列，提示符上的下一条输入同样先于自动轮次。

这条对齐 DSH 的 `competingQueued`：自动轮次给竞争输入让位。差别只在粒度——mini 在段（DSH 的 turn）边界让位，不在一个段内部的模型步之间插队。

#### Scenario: 队列里的人话先跑

- **WHEN** goal 轮次正在跑，人投递了一条消息；该轮次以 `MODEL_COMPLETED` 收尾
- **THEN** 下一条 `user/message` 的 `source.kind == "user"`、内容是那条投递；goal 轮次在它之后才继续

#### Scenario: 人话不推进轮号

- **WHEN** 第 1 轮之后夹了一段人类消息
- **THEN** 人类段的 `user/message` 不带 `source.round`；其后的 goal 消息 `source.round == 2`

#### Scenario: 请求的上限被部署上限截住

- **WHEN** 部署 `[goal] max_rounds = 32`，模型调用 `create_goal(max_rounds=100)`
- **THEN** 落盘快照的 `max_rounds == 32`；`minihns goal <id> edit --max-rounds 100` 同样落 32

