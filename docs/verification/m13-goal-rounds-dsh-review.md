# M13 契约与对齐复核

**日期**：2026-11-18。位置按新流程（§0.4 第一道）：apply 之前。复核者是与撰写者不共享上下文的子代理；输入是 change 文件 + DSH 一手文件，不含实现叙事。

**结论**：第一轮 `GAPS`——4 blocker、13 major。本文记复核结论与处置；处置状态除 `aligned` 外都要人裁。

## A. 十项对齐

| 项 | DSH（一手） | mini（change 位置） | 结论 | 记账 |
|---|---|---|---|---|
| 1 形状 | `GoalSnapshot{id,revision,objective,phase,blockedReason?,maxGoalRounds}`，`roundsStarted` 是 `GoalView` 的派生值（`docs/subsystems/goal.md:44-70`）；`goal/change` 带 `operation` 与墓碑 | 快照把 `rounds_started` 写进载荷、`goal/updated{goal\|null}` | simplified | design D2 + ADR-0043；本轮修：轮次推进不再递增 `revision`；4.4 补 replay 交叉校验（`goal_round_defect`） |
| 2 机制 | 空闲 → `flush` 检查点 → 预约 → `followup` → `pre-step` 前后两次围栏（`driver_index.ts:106-221,372-452`） | 段后同协程判定 + 写三事件 | simplified | D3；丢 `competingQueued` 让位 |
| 3 语义 | `create` 可替换 `complete`；`resume` 接受已停目标（含 blocked）并清旧 blocker，且要有轮次余量（`goal README:68`） | 原稿只写 paused 拒绝、active 武装，blocked 无出口 | **blocker，本轮修** | 补 `blocked → active` 且清 `blocked_reason` |
| 4 不变量 | `roundsStarted` 只由进入模型历史的 goal 消息推进；activation 永不落盘 | 首条 `context/assembled` 之后推进（2026-11-19 起）；`armed` 同样不落盘 | simplified | ADR-0043；计数点已贴住「进上下文」 |
| 5 面 | 模型面 = `<goal_round>`（objective + `Round: n/cap` + 指令，`prompt.ts:12-26`）+ `tool:goal` 政策段 | 无正文形状要求、无政策文本 | **blocker，本轮修正文；政策段记 deferred** | 正文补 Requirement；政策段触发条件：出现「模型反复试错才知门槛」的真实记录 |
| 6 失败 | `queue-failed` / `prompt-rejected` / `round-limit`；异常失败需人工 resume；`agent/error` 即 disarm | 只有 `round-limit`；失败收尾不续跑但未 disarm | simplified | 本轮把「失败收尾即 disarm」补进 Requirement 与判据 |
| 7 组合 | cap 属 goal、门槛属 tool-goal、并行属 todo 包，分属三处 | 全收进 `[goal]` 一段 | simplified | D7；代价：部署面分成三段变一段，语义归属变粗 |
| 8 资源 | cap 默认 256，只计 admitted rounds，不是资源预算 | 32 / 3 / true | simplified | 已记；`MAX_TURNS` 与轮次额度的关系见 major |
| 9 信任 | 精确 live agent + open turn；subagent 无权威，普通 fork 有 | 本段人类来源开机 + `entry=="subagent"` 拒绝 | aligned（等价，但 mini 无 live-agent 概念） | 复核者注：`entry` 判定与 DSH 的「运行时根 agent」不是同一层 |
| 10 回放 | 严格 fold 拒 malformed、revision 不连续、非法 phase 转换；损坏态 `GOAL_STATE_CORRUPT` | 只抄轮次五类 | simplified | 本轮补「按 `goal_id` 维度判跳号」；损坏态 deferred |

## B. 内部一致性缺口与处置

### Blocker（本轮已修）

| # | 缺口 | 处置 |
|---|---|---|
| B1 | 契约目标句仍写「在轮次之间各自保留」，与行为 4（每段清空）互斥 | 目标句改为「同一段里多个任务并存」，与 D8 一致 |
| B2 | goal 轮次消息**正文形状**无 Requirement；主规格 `context-projection` 只认「run prompt」与「REPL user/message」两个 user 来源 | 补 Requirement：正文是 `<goal_round>` 块，含 `Objective:` 与 `Round: n/cap`；补判据断言正文含 objective 与轮号；补 `context-projection` delta |
| B3 | `blocked` 无恢复路径：`round-limit` 落 blocked，driver 只推 `active`，resume 不认 blocked → 目标永久停摆 | `resume` 接受 `blocked`，置 `active` 并清 `blocked_reason`；补判据 |
| B4 | 额度在写 `goal/updated` 时即 +1，与 DSH 的「进历史才计数」不同；早失败的白烧无判据 | 改为对齐：计数点移到该段首条 `turn/start` 之后，早失败不计轮次；判据相应改写 |

### Major（本轮修）

- 门槛 3 与 `max_rounds = 3` 冲突 → 阻塞门槛的判据改用 `max_rounds = 5` 的夹具。
- 写日志失败无判据 → 补一条：日志不可写时不起段、不写 `goal/updated`、以非零退出。
- 「取消即暂停」无 Requirement → 补：`ABORTED` 收尾把 `phase` 置 `paused`、`armed` 置假。
- `create` 替换 `complete` 无正向判据 → 补一条：complete 后能再 create，且轮号从 1 重启。
- 替换后轮号重启会被跳号校验误杀 → 校验按 `goal_id` 维度分组。
- `edit` 语义空白 → 补：部分替换、至少一个有效字段、空串/0 视为省略。
- 每轮递增 `revision` 使轮内 ref 立即 stale → 轮次推进**不**改 `revision`；只有控制面动作递增。
- `MAX_TURNS` 不在不续跑集合 → 加入集合（与 DSH 的 max-tokens 停止同向）。

### Major / Minor（记账，待人裁）

- **模型面政策段**（`tool:goal` 的系统提示）：mini 没有；`GOAL_BLOCK_TOO_EARLY` 只能靠试错。`deferred`，触发条件：真实使用里出现「模型反复试错才知门槛」的记录。
- **激活事件**（`goal/activation-changed`）与宿主 `goal` 投影：本 change 不做（非目标已列），结论 `deferred`，触发条件：壳需要实时显示武装状态。
- **损坏态 `GOAL_STATE_CORRUPT`**：mini 用 `replay` 非零退出代替专名；`simplified`，代价是错误分类粒度更粗。
- **`clear` 是否置假 `armed`**：mini 无观察后果（clear 后无目标），`aligned` by construction；不单列 Requirement。
- **门槛 > `max_rounds` 的配置组合**：不予校验，行为是「只能等 `round-limit`」；`simplified`，代价写在 config delta。
- **`fork` 后武装**：mini 无 fork（ADR-0035），`deferred`。
- **`queue-failed` / `prompt-rejected` 两个 DSH 出口**：mini 无排队与 pre-step 链，`deferred`，无对应实现面。

## C. 复核者的总评

> 判据能在「模型实际收到什么」和「轮次何时消耗额度」这两处全绿而实现是错的，且 `round-limit` 之后没有回到 active 的路径。

三条都指向同一件事：我把「状态机走通」当成够了，没检查「走完之后还能不能回来」。B3 是其中最贵的——一个只能进不能出的状态机。

## D. 2026-11-18 追加：术语与轮次机制的记账

人问「同一个词在两边指什么、跨段的 goal 消息从哪来」之后补记。前三行是**术语映射**，后三行是**本轮实现里与 DSH 不同形的机制**。

### D.1 术语映射（aligned）

| mini | DSH | 关系 | 落点 |
|---|---|---|---|
| 段 segment | turn | 一个段恰是一个 turn：一条输入展开的那串回合 | `GLOSSARY.md`「段」；`turn-loop` 主规格 220 行原句 |
| 轮 round（goal 轮次） | goal round | 一轮恰是一个段；DSH 里那一轮也是一次 admitted user-message turn（`goal.md:119`） | `GLOSSARY.md`「轮」（本次新增） |
| 回合 turn | step | 一次模型往返 | `GLOSSARY.md`「回合」 |

因此「goal 跨段」= 「goal 跨 turn（DSH 义）」= 多轮，不是偏离；被 M13 改掉的是**入口的段数不变量**（`run` 以前恰一个段），见 `turn-loop` delta。同一次扫查还改掉两处旧全称量词：`turn-loop` 的「一次性 run 恰一个段」与 `event-stream` 的「一个会话恰一个段」。

### D.2 准入点：首条 `context/assembled` 之后（2026-11-19 已裁，aligned）

- DSH：消息**进了这一轮**才计数；被拒的预约不消耗轮号（`goal-round-driver/README.md:71`）。
- mini：写 goal 消息 → `turn/start` → `context/assembled` → `goal/updated`。装配完成之前失败（注入、折叠、装配内压缩、provider 立刻失败）不扣轮次。
- 2026-11-19 人裁：原来停在 `turn/start`，留了一个 `turn/start → context/assembled` 的白烧窗口；现已挪到 `context/assembled` 之后，四事件顺序与契约行为 1 的判据同步改。
- 残余窗口：「装配成功、`model/request` 立刻失败」仍会扣一轮——这与 DSH 一致（消息已进历史），不再收紧。

### D.3 计数来源：写成字段 + replay 交叉校验（语义 aligned / 表示 simplified）

- DSH：`roundsStarted` 是 `GoalView` 的派生值——从日志里数 goal 消息就能得出，不存在写错的可能。
- mini：同一个语义值写在快照里（`rounds_started`），**并且**能从日志数出来；`replay` 校验「每条快照的 `rounds_started` 等于此前该目标的轮次消息条数」（`goals.goal_round_defect`，4.4）。所以两边**语义等价**，差别只在表示：mini 多存了一份冗余。
- 收益：`get_goal` 能回自足快照，驱动不必每轮重扫全日志（O(1) 读 vs O(n) 数）。
- 代价：同一事实两份写法必须同步；改任何一边都会让 `replay` 判红——这是刻意的 redundancy，不是「语义没对齐」。

### D.4 goal 消息的唯一来源（aligned）

- 只有驱动能造它：`run_session_env` 判定后调 `run_turn_segment(goal_round=GoalRound(...))`（`turn_loop.py:1498`），正文由 `render_goal_round` 生成（`turn_loop.py:988`），来源固定为 `{kind: "goal", goal_id, revision, round}`。
- 人不能编辑它、模型不能伪造它（模型没有写 `user/message` 的工具）；DSH 同款——驱动排队一条带 goal message source 的 `<goal_round>` 提示（`driver README:71`）。
- REPL 的驱动入口（task 5.4）已接上，来源仍是这一条路径：`chat` 在段尾判定通过后调同一个 `run_turn_segment(goal_round=...)`。

### D.5 决策位置（simplified，已在项 2 记）

段后同协程判定，不是独立 consumer：省掉预约、`flush` 检查点与 `pre-step` 围栏；代价是丢 `competingQueued` 让位（人只能等这一段收敛或取消）。REPL 侧也已在 5.4 接上同一套判定（`chat` 段尾判定通过就不打印提示符，直接起下一轮）。

### D.6 等价物核对：turn / step / round 与 goal（2026-11-19，逐条对代码）

人要求「先确认 turn、step、round 之间的关系以及它们跟 goal 的对应关系在 mini 都有等价物，其余维持现状」。逐条核对的是**边界事件与判据**，不是名词：

| DSH | mini | 边界（写在哪） | 判据 |
|---|---|---|---|
| `step`（一次模型往返） | 回合 | `turn/start`（`turn_loop.py:1187`）→ `turn/end`（`1352`）；段内上限 `max_turns` | `test_two_segments_number_segments_and_turns_continuously`：两段共 5 个回合，编号连续 |
| `turn`（一次输入驱动的整跑） | 段 | `segment/start`（`995`）→ `segment/end`（`1021`）；一个段恰好包住 1..n 个回合 | 同上：`segment/end` 的 `turns` 与段内 `turn/start` 条数相等 |
| `goal round`（一次被准入的 user-message turn） | 轮 | 一轮 = 一个段；段首写 goal 来源 `user/message`（`source.round` 来自 `GoalRound`） | `test_three_rounds_run_in_order_and_stop_at_the_cap`：3 轮 → `s1`（人）+ `s2`/`s3`/`s4`，每轮段前六类固定 |
| goal 与轮的关系 | 同 | 轮属于目标：`source.goal_id` + `source.revision`；上限 `max_rounds`；计数 `rounds_started`；相位在 `goal/updated` | `replay` 的 `goal_round_defect`（4.4）+ 契约行为 1、2 的各条 |

DSH 侧的原句（`packages/goal/goal-round-driver/README.md` 与 `docs/subsystems/goal.md`）：**“Each round gives the model another turn toward the objective”**（`driver README:12`）——round 与 turn 是同一个对象；**“the `agent/pre-step` listener … before its step enters”**（`72`）——一个 round/turn 里有多个 step，每个 step 进模型之前过围栏；**“each admitted user-message turn”**（`goal.md:119`）——轮只由被准入的 user-message turn 推进。

结论：**四层都有直接等价物**，且关系同形——一个 goal 由多轮组成，一轮是一个段、段内多个回合；轮不拆、不并、不并发（`next_round` 与开段在同一个协程里顺序发生，`turn_loop.py:1473-1504`）。

**唯一不严格同形的一处**（早已记在 D.4 与 turn-loop 的设计里）：DSH 的 turn 总有一条 admitted `user/message`；mini 的 `run` 起手段把「人话」放在 `session/start`（design D6 的不对称）。这是**输入记录的存放位置**不同，不是段/回合边界不同——`run` 之后续跑的每一轮都照 D.4 那条路径写 goal 消息。

据此，D.2–D.5 的处置**维持现状**：D.2 已对齐（`context/assembled` 之后计数）、D.3 语义对齐（表示多一份冗余字段）、D.4 对齐、D.5 保持 `simplified`（要真对齐得先有输入队列，见项 2 的四件套）。

### D.7 `get_todos`：mini 补的一个洞（added，不是对齐项）

DSH 只有写表工具（`packages/todo/tool-todo/`），没有读回。mini 加 `get_todos` 的原因不是对齐，而是 D8 的代价：`todos` 每段开头清空、整表只活在工具历史里，被剪枝或压缩遮住之后模型只能凭记忆重写——而 `todo` 是整表替换，记错就改掉进度。

- 读的是 `todos` 投影，所以与 `/todo`、`GET /projections/todos` 同值；段首之后为空，不跨段继承（跨轮仍靠模型重交，D8 的边界不动）。
- 只读：不写 `todo/updated`、不问人、计划模式放行；`DispatchContext.todos` 由批首前缀折好传入（与 `goal` 同一条规则）。
- 代价：工具面多一个名字；同批里读不到本批前一条 `todo` 的结果（批首前缀只取样一次，与 `reads`、`goal` 一致）。

#### D.7.1 读回的边界：跨轮重交不经过它（2026-11-19 人问）

人问「跨轮重交整表本身就依赖读回上一段的表，所以只是多一次工具调用吧」。答案分两半：

- **跨轮、历史完整：零次额外调用。** 模型重交的是它自己上一轮 `todo` 调用的入参，历史里看得见，不需要读回；`get_todos` 在段首给的是空表（投影在 `segment/start` 清空），所以「先读回旧表再重交」这条路**当前不成立**。
- **DSH 同构，不是 mini 的缺口。** `todo_write` 的模型可见文本也只有计数（`render`，`todo_index.ts:159-182`），整表只留在调用入参与 `todo/write` 事件里；`turn/start` 之后投影归 `null`（`todo_index.ts:130`）。所以 DSH 跨轮同样靠模型重写，被遮蔽之后同样无路可读——它的表也是「本轮常备计划」，不是跨轮状态。
- **若要跨轮读旧表**，得加一个非投影的读法（例如 `get_todos(scope="last")` 读最后一条 `todo/updated`），代价是引入 DSH 没有的跨轮表语义，且模型容易把旧表当本段当前表。**2026-11-19 人裁：按 D8，不加**——表保持段作用域，跨轮不读旧表。

顺带更正一处旧记录：`docs/reference/plan-and-todo.md` 4.1 原写「DSH 返回 `{todos, counts}` 并有 native renderer」——结构化输出确实是这个形状，但模型读到的是 `render` 的计数文本，与 mini 同形；已改。

#### D.7.2 跨轮（含 goal 轮次）不保表：两边都靠历史与工作区（2026-11-19）

人追问三件：跨轮指普通 turn 还是 goal turn；DSH 具体怎么跨段保表；被遮蔽是否就读不回来。

- **两种轮是同一个边界。** DSH 的 goal round 就是一次 admitted user-message turn（`goal.md:119`）；`todos` 投影只认两个分支——`todo/write` 与 `turn/start`（`todo_index.ts:130`），**没有 goal 分支**。所以普通 turn 与 goal 轮都在开头清空，没有「goal 段保留表」这回事；mini 的 `segment/start` 同构（`events/projection.py`）。
- **DSH 不跨段保表。** 能查的载体都查了：包里没有读回工具（`tool-todo` 只有 `todo_write`）；工具结果的模型可见文本只有计数（`render`，`todo_index.ts:159-182`）；goal 轮提示只有 objective / round / 指令（`packages/goal/goal-round-driver/src/prompt.ts`）；系统提示的 section 排序里没有 todo（逆向报告 §5.3，`tool-todo` 只是工具分组）。`turn/start` 之后运行时状态是 `null`，唯一载体是模型自己的历史。
- **连续性靠三样，不是表。** 目标与轮号每轮注入；工作区、工具结果与持久状态由轮次提示明确要求「inspect them instead of assuming earlier narration is still current」；压缩摘要带叙述。表是「本轮常备计划」，条目刻意最小（无 id、整表替换，`docs/subsystems/todo.md`）。
- **被遮蔽就是读不回来。** 两边一样：DSH 没有读回面，mini 的 `get_todos` 只覆盖本段。要让跨轮读回成立，得加一个非投影的读法（`todos_last` 投影 + `get_todos(scope="last")`，标注「最近一次提交，可能来自更早的段」）——这是 DSH 没有的机制，**2026-11-19 人裁：不加，按 D8 保持段作用域**。

#### D.7.3 「工作区与持久状态」在 DSH 的具体形式（2026-11-19）

轮次提示那句 “Treat the current workspace, tool results, and durable session state as authoritative; inspect them instead of assuming earlier narration is still current” 指三层，按寿命排序：

| 说法 | 形式 | 模型怎么看到 | 寿命 |
|---|---|---|---|
| current workspace | cwd 下的文件树（源码、产物、构建输出、git 状态）；`tool-fs` / `tool-bash` 操作的对象 | `read` / `grep` / `glob` / `bash` | 跨会话；进度的唯一真源 |
| tool results | 本会话已发生的工具调用与输出，装配进上下文 | 直接在上下文里 | 跟上下文；会被剪枝 / 压缩遮蔽 |
| durable session state | 会话日志 + 从它折出的投影（`goal/change`、`todo/write`、`plan/mode`、压缩摘要） | `get_goal` 读目标（`goal.md:178`：goal service「backed exclusively by the owning session log」）；plan 段由提示注入；todo 没有读面 | 跨 resume / replay，但不保证在上下文里 |

- **AGENTS.md 不是状态，是指令**：它由 `agent-instructions` 段进提示（逆向报告 §5.2：`maxBytes: 65536`，读 `$DSH_HOME/AGENTS.md`），内容不随工作进展变化，也不该用来记进度。文档与产物属于第一层。
- **没有「会话快照」这个东西**：日志是 durable 的，每次请求的上下文是装配出来的视图（transient）。`goal/change` 的 payload 是「完整快照」，但那是**单个对象的整值替换**，不是会话快照；mini 的 `context/assembled` 同理。
- 所以「持久状态」里模型能读的只有目标（`get_goal`）与 plan 模式（提示注入）；**todo 表不在其中**——它是每轮清空的常备计划（D.7.2）。

### D.8 UAT 场次 1/2 暴露的两处实现问题（2026-11-19）

人跑场次 1 时模型在轮次里调 `ask_user`，得到 `QUESTION_UNAVAILABLE` 之后驱动仍开了下一轮——问题悬着，额度继续烧。同一场还暴露出工具回执的路径与 bash 的 cwd 对不上。

#### D.8.1 未回答的问题不续跑（added，不是对齐项）

- **原行为**：`ask_user` 返回「问不到人」，段照常以 `MODEL_COMPLETED` 收尾，`next_round` 只看快照、武装位与 `stop_reason`，于是开了下一轮。
- **现行为**：`session.questions.pending` 在段尾非空时，`next_round` 给 `awaiting_input`；入口落 `paused` 并解除武装，与 `ABORTED` 同一条收尾理由。段首清空；额度用尽优先。
- **为什么不是「继续跑」**：模型会重复提问或自拟答案，两种都在替人做决定。
- **对齐状态**：DSH 的问题面不在本次抓取范围（`/tmp/dsh-goal` 只有 goal/todo 子系统），所以这条记 `added`，不声称与 DSH 同形；形状上它只是把「段尾不能继续」多列一种理由，与 `ABORTED` 并列。

#### D.8.2 回执路径与工作区同一条（缺陷修复）

- **原行为**：`--workspace .tmp/uat/m13` 是相对路径，`resolve_target` 直接拼接，`write` 回执写 `.tmp/uat/m13/notes.md`；而 `bash` 的 cwd 是工作区根，模型 `tail .tmp/uat/m13/notes.md` 当场失败（场次 2 记录）。
- **现行为**：装配时把工作区绝对化（`os.path.abspath`，不解析符号链接），`write` / `edit` 的回执改用工作区相对路径（与 `glob` / `grep` 一致）：`写了 notes.md（… 个字符）`。
- **顺带**：`[段]` 那行只在非 `MODEL_COMPLETED` 时打印（`chat-repl` 的既有规则），所以自动轮次之间人看不到任何边界；补 `[轮] n/cap`、`已用尽 n/cap`、`目标已暂停` 三类行，写在 REPL 层，不进日志。

#### D.8.3 resume 之后立刻驱动（2026-11-19，更贴 DSH 的 idle）

- **原行为**：`/goal resume` 只放武装位；REPL 只在段尾判定，所以人还得敲一行「继续」。那一行开的是**人类段**——模型在里面写了第二节，轮次计数却没动（场次 2 的 `[轮] 3/4` 直接跳过了这活）。
- **现行为**：命令成功后立刻算下一轮并进段循环，`[轮] n/cap` 紧跟回执（design D12）。
- **对齐状态**：DSH 在 whole-agent idle 时驱动；命令返回就是 idle，所以这条是向 DSH 靠，而不是新增偏离。mini 仍缺 inbox 与 `pre-step` 围栏（D.5 的 `simplified` 不变）。
