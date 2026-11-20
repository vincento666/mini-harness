# Design

## D1 单 goal，多任务并行（ADR-0042）

目标域只维护**一个**当前目标，与 DSH 的 `current goal` 一致：`create` 仅在「无目标」或「上一个已 `complete`」时成立，其余 phase 必须先 `clear` 或 `resume`。并行不发生在目标之间，而发生在目标内部的任务上：一次调用可以标多个 `in_progress`，各任务状态在同一张表里各自成立。

**取舍**：这条路放弃「两个目标同时 active、轮次交替」。代价是多目标并存的竞态与调度仍未验证，roadmap 的 `parallel-goal-scheduler` 因此扩为「多目标状态 + 调度」。理由与代价记在 ADR-0042。

## D2 `goal/updated` 是整值替换，不是操作日志

载荷 `{goal: <快照> | null}`，每次改动写一条完整快照；`null` 是清除墓碑。`revision` 只随**控制面动作**（create / edit / pause / resume / complete / blocked / clear）+1；**轮次推进不改 `revision`**——否则模型在轮内拿到的引用会立刻过期（DSH 的 `roundsStarted` 是派生值，本来就不产生变更）。`update_goal` 必须带上一读的 `(goal_id, revision)`。

**与 DSH 的差异**：DSH 的 `goal/change` 带 `operation` 与 `view`（含 `rounds_started`、`createdAt`、`updatedAt`），并把「清除」编码为 `operation: "clear"` 的墓碑。mini 用整值替换 + `null`，与既有的 `plan/mode`、`todo/updated` 同形，折叠只需「取最后一条」。

**代价**：丢掉操作语义，靠前后两条快照的差推断发生了什么；`replay` 仍相等，因为回放只认最后值。

## D3 轮次驱动：把「预约 → 准入」塌成「写日志即准入」

DSH 的形状（一手资料，`packages/goal/goal-round-driver/src/index.ts`，commit 见附录）：

1. 只在 `agent.status === 'idle'`、无竞争输入（`competingQueued`）、目标 `active` 且 `armed` 时驱动一次；
2. 先过持久化检查点 `await ctx.sessions.flush()`，`await` 之后**重查**目标 revision 与竞争输入（`readyAfterCheckpoint`）；
3. 预约 `roundsStarted + 1` 并 `followup()` 排队；只有**进了模型历史**的 goal 消息才 `roundsStarted++`；
4. `agent/pre-step` 前后各校验一次（`validReservation`）：预约仍持有、`phase` 仍 `active`、`armed` 仍真、`source.round === roundsStarted + 1`；失败则丢弃这一步、恢复其它被领取的消息、重新驱动；
5. 失败出口各有稳定码：排队失败 `queue-failed`，准入被下游拒绝 `prompt-rejected`，额度用尽 `round-limit`。

mini 没有 inbox、没有可插队的竞争输入、主循环是显式的（不变量 C），所以第 1–4 步塌成一步：**段结束后在同一个协程里顺序判定条件、写 `segment/start` + goal 来源的 `user/message` + 首条 `turn/start` + 首条 `context/assembled` + `goal/updated`（`rounds_started` 递增），再进下一段**。写日志成功即准入，因为 mini 的日志就是历史真源（不变量 A），不存在「排队后被别人抢先」的窗口。

**代价**：丢掉 DSH 的「人先插话就让人插队」语义（`competingQueued` 让自动轮次让位）。mini 里人要么等当前轮收敛，要么取消；取消即暂停，不自动重跑。

**这条塌缩带来三个必须写明的语义**（复核 B3/B4 指出）：

1. **额度在首条 `context/assembled` 之后消耗**（2026-11-19 人裁）：顺序是 `segment/start` → goal 消息 → `turn/start` → `context/assembled` → `goal/updated`。装配完成之前失败（provider 立刻失败、注入失败、折叠失败、装配内压缩失败）都不计轮次——这是 DSH「进模型历史才计数」在 mini 的等价物。代价是 `goal/updated` 离消息更远，回放校验要认这个位置；收益是「起了回合但没装进上下文」不再白烧额度。
2. **取消置暂停**：段以 `ABORTED` 收尾时 `phase → paused` 并解除武装；其余失败只解除武装，`phase` 留在 `active`，等人 `/goal resume`。
3. **blocked 必须能回 active**：`round-limit` 落的是 `blocked`，而驱动只推 `active`。若 `resume` 不认 `blocked`，目标就永久停摆。所以 `resume` 对 `blocked` 置 `active`、清 `blocked_reason`、置真；对 `paused` 仍拒绝（那是人的口子）。

**保留的**：失败出口的稳定码——额度用尽仍是 `round-limit`，用来区分「跑满了」与「模型自报阻塞」。

## D4 轮次是 goal 来源的 `user/message`，不新增轮次事件

`user/message` 增 `source`：缺省 `{kind: "user"}`；goal 轮次为 `{kind: "goal", goal_id, revision, round}`。`round` 必须等于 `rounds_started + 1`，`revision` 必须与 `goal/updated` 的当前值相同，否则回放判日志不自洽。

**理由**：DSH 的轮次就是一条带来源的 user 消息，重放据此校验「轮号非正、跳号、旧 revision、已停 phase、超额」。mini 照抄这一步，才能让「轮次」有日志归属，而不是内存计数。

**代价**：`user/message` 的形状变化波及折叠、投影与 CLI 回显；旧日志缺 `source` 必须按人读，不能当解析失败。

**消息只有一个来源**：驱动在段后判定通过时调 `run_turn_segment(goal_round=...)`，正文由 `render_goal_round` 生成；人没有写 `user/message` 的入口，模型也没有——所以「goal 轮次」不可能被伪造或手改。`rounds_started` 写成快照字段、准入点取首条 `context/assembled` 之后，理由与代价见 ADR-0043。

## D5 `armed` 是进程内的布尔，永不落盘

`goal/updated` 不带武装位；`armed` 只活在会话运行期。会话启动（含 `--resume`）一律 `armed = false`；**`create` 置真**（DSH 的 `create` 就是 `commitSnapshot(..., 'armed')`，见 `packages/goal/goal/src/index.ts:300-321`；不置真则目标永远不动）；`/goal resume` 与 `update_goal(resume)` 把它置真；`pause` / `complete` / `blocked` / 撞上限 / 以失败收尾的段把它置假。`--resume` 之后不自动续跑，是这一条的必然结果，也是行为 3 的判据。

**与 DSH 的差异**：DSH 的 `activation` 是 `armed | disarmed`，同样进程内、同样在 resume / fork / 卸载后失效。mini 用 `bool`，语义等价，少一个枚举值。

## D6 blocked 的门槛：轮数是硬的，语义是软的

`update_goal(action="blocked")` 要求 `blocked_reason` 非空，且 `rounds_started >= blocked_after_consecutive_rounds`（默认 3），否则 `GOAL_BLOCK_TOO_EARLY`。落盘时 `blocked_reason.code` 固定为 `model-reported`，原文进 `message`；驱动自己因额度用尽落的阻塞用 `round-limit`。

**与 DSH 的差异**：DSH 的一手表述是「同一个阻碍持续 N 轮」，运行时能证明的只有「经过了 N 个被接受的轮次」，语义等价性归模型判断（"the model judges whether the same condition actually persisted"）。mini 照抄这条分层，不假装能验证「同一」。

## D7 todo 并行的开关默认 `true`

`allow_parallel_in_progress` 默认 `true`；配置为 `false` 时，一次调用里第二个 `in_progress` 得 `TODO_PARALLEL_DISABLED`，整表不落盘。

**与 DSH 的差异**：DSH 的这个键**必填、无默认**，缺失时装配失败（"a composition that omits it fails at load"）。mini 的 `mini.config.toml` 有缺省传统，改必填会让既有配置文件全部失效；默认 `true` 与本 change 的目的（任务并行）一致。代价：少了一个显式的部署声明，靠文档与示例补。

## D8 `todos` 每段开头照清，含 goal 轮次（对齐 DSH）

一度试过「goal 段保留、人类段清空」，2026-11-18 撤回。DSH 的 `todos` 投影无条件在 `turn/start` 归 `null`（`packages/todo/tool-todo/src/index.ts:120-131`：`if (event.type === 'turn/start') return null`），214 行里没有一个 `goal` 分支；而 goal 轮次在 DSH 就是一次 turn（`docs/subsystems/goal.md:119` 称其为 "admitted user-message **turn**"）。所以 DSH 每轮也清空。

**为什么不保留那处「更顺手」的偏离**：`todo` 在 DSH 里是「本轮的常备计划」，不是跨轮状态；跨轮靠 goal 的 objective、模型自己的工具历史、以及每次整表重写。保留旧表能买到的只有「轮次开头、模型还没提交新表」这段空窗期的可见性——它不改变任何真源，却让同一串事件在两份实现里投影不同。判据因此改为「清空对所有段一致」，跨轮的任务连续性由模型每轮重交整表负责，不由投影负责。

**配套（task 4.5）**：清空的代价是段内一旦被遮蔽（单条结果剪枝 / 折叠 / 压缩），模型就看不见刚提交的表，只能凭记忆重写整表——而 `todo` 是整表替换，记错就改掉进度。补一个只读的 `get_todos`：读 `todos` 投影（与 `/todo`、快照接口同值），不落事件，段首为空。**跨轮仍靠重交**，它不改变 D8 的边界，只把「本段提交过什么」变成可重读的事实。DSH 没有这个工具；这是 mini 自己补的洞，不是对齐项。

## D9 CLI `/goal` 只做查看与三个动作

`/goal` 打印当前目标（id、phase、`rounds_started/max_rounds`、阻塞原因）；`/goal pause`、`/goal resume`、`/goal clear` 各写一条 `goal/updated`。创建不提供命令语法——人类说一句要做的事，模型用 `create_goal` 落；命令面不重复一套目标描述解析。

**权威**：`create` / `edit` / `pause` / `resume` 要求当前段由人类来源消息开启（`source.kind == "user"`）；子会话（`entry == "subagent"`）一律不具备该权威。`complete` / `blocked` 在 goal 轮次里也允许。

**与 DSH 的差异**：DSH 的 `resume` 对持久 `paused` 目标在工具层直接拒绝（`GOAL_TOOL_RESUME_PAUSED`），把该转换留给用户面。mini 照抄这个分界，但用户面是 `/goal resume`（不是 Web 控件）。

## D10 相位转换矩阵照 DSH，动词分人/模型两套

| 动作 | 允许的相位 | 落定相位 | 武装 | 谁能调 |
|---|---|---|---|---|
| `create` | 无目标，或上一个 `complete` | `active` | 真 | 人类段里的模型 |
| `edit` | 任意 | 不变 | 不变 | 人类段里的模型 |
| `pause` | `active` | `paused` | 假 | 人类段里的模型 / `/goal pause` |
| `resume` | `active`（未武装）、`blocked` | `active` | 真 | 人类段里的模型；`paused` 只认 `/goal resume` |
| `complete` | 非 `complete` | `complete` | 假 | 模型（含 goal 轮次） |
| `blocked` | `active` 且跑满门槛 | `blocked` | 假 | 模型（含 goal 轮次） |

**依据**（`packages/goal/goal/src/index.ts`）：`pause` 的 `transition(..., ['active'], 'paused', 'disarmed')`（356）；`resume` 的 `resumable = ['active','paused','blocked']` 加两条拒绝——已 `active` 且已武装（376）、`roundsStarted >= maxGoalRounds`（381）；`complete` 的 `['active','paused','blocked']`（388-402）；`block` 只认 `active`（406-425）。

**与 DSH 的两处差异**：① `resume` 对 `paused` 在工具层拒绝，交给 `/goal resume`（DSH 是 `GOAL_TOOL_RESUME_PAUSED`，同一分界）；② DSH 用 `GOAL_INVALID_TRANSITION` 表达「相位不允许」，mini 补了同名结果词——这是实现时发现的缺口，记在 proposal 的「提案扩展」。

## D11 未回答的问题不续跑：暂停而不是跳过（已被 D15 取代，2026-11-20）

`ask_user` 在自动轮次里通常问不到人（`QUESTION_UNAVAILABLE`）。原来的行为是：模型拿到「问题未决」，段照常以 `MODEL_COMPLETED` 收尾，驱动接着开下一轮——问题还悬着，额度却继续烧。2026-11-19 的 UAT 场次 1 撞上这个形状（两轮全用在「问一个没人能答的问题」上）。

- **判据**：段尾 `session.questions.pending` 非空就是「等人回答」。它在段首清空（与 `todos` 同一条边界），只有 `ask_user` 拿到答案时才清掉。
- **处置**：`next_round` 多一档 `awaiting_input`；入口落 `paused` 并解除武装，与 `ABORTED` 同一条收尾理由——自动化停在这里，人回答后 `/goal resume` 再放行。`blocked` / `complete` / `paused` 不改写。
- **优先级**：额度用尽优先。最后一轮里问了问题也先落 `blocked{round-limit}`——那是更硬的事实，避免「paused 却 resume 不了」。
- **不选「继续跑」**：模型会重复提问或自拟答案，两种都在替人做决定；也不选「把问题塞进下一轮提示」——DSH 的轮次提示只有 objective 与轮号，加一段问答会变成新的机制。
- **代价**：DSH 没有对应的可查证据（它的问题面不在本次抓取范围），这是 mini 自己补的一条收尾规则；`paused` 的表达也让人必须多敲一次 `/goal resume`，换来的是「不会在问题悬着时继续花钱」。

**REPL 可见性**：自动轮次开始前沿用 `_print_segment_note` 的同一通道打 `[轮] n/cap`，额度用尽与「等人回答」各打一行。既有 `chat-repl` 规则要求 `MODEL_COMPLETED` 不打印段级那行，所以这里另立一种行，不改那条规则。

## D12 `/goal resume` 之后立刻驱动，不等下一行

原来的 REPL 只在**段结束**判定续跑；`/goal resume` 之后没有任何段在跑，于是人得再敲一行「继续」——那一行会开一个**人类段**，模型在里面把活干了，轮次却没算进去（UAT 场次 2 里第二节就是这样写的，终端也没有 `[轮]` 标记）。这与 DSH 的「idle 即驱动」相去甚远。

- **现行为**：`/goal resume` 成功之后，REPL 立刻用 `_resume_round` 算出下一轮并进段循环；`[轮] n/cap` 紧跟命令回执。人不用再敲一行。
- **只认三种事实**：命令是 `resume`、`armed` 已为真、目标 `active` 且还有额度；任一不成立就回到提示符。
- **代价**：`/goal resume` 立刻开始花钱。这是人的显式命令，且回执与 `[轮]` 行都在动手之前打出来，可 Ctrl-C 取消。
- **不动 `run` / `serve`**：它们没有命令面，本来就在段尾驱动。

## D13 人类竞争输入优先：段边界让位，不做步内插队

DSH 的驱动条件里有一条 `!competingQueued`（`docs/dsh-reference/DSH运行时架构剖析.html` 图 7-1；`goal-round-driver` 的 `readyToDrive`）：只要有排队的人类消息，自动轮次就不开，让人先说话。mini 的 host 已经有这条队列——`submit_message` 在段进行中把消息放进深度 1 的 `deque`（`session/host.py`），段收尾后取队首。所以这不是「mini 还没有的功能」，而是「chat 没接、host 有队列但没有驱动」。

**对齐的形状**：段（DSH 的 turn）收尾后按「队列人话 → goal 轮次」排序；队列非空时 MUST NOT 先开 goal 轮。差别只在粒度：mini 不在一个段内部的模型步之间插队，DSH 的排队消息也要等当前 turn 收尾才成为下一条 user 消息，二者在 turn 边界上等价。

**chat 没有队列**：REPL 是同步 `readline`，段进行中人不拥有提示符；Ctrl-C 是唯一的中断手段。这不是语义缺失，是本地调试入口的形态；host 才是通用入口（2026-11-20 人裁）。

**host 原来没有驱动**：`_run_segment` 只跑一段就回 idle，`/goal resume` 之后什么也不会发生。这是实现分叉，不是设计取舍。现在段后收尾抽成 `settle_segment`，`run` / `chat` / `host` 三处共用；host 在队列为空且判定 `continue` 时自己开下一轮。

## D14 停滞熔断：goal 轮次零工具调用就停自动推进

「完成了还不会停」的现场是：模型在第 4 轮说「没有新内容可写」，没有调用 `update_goal`，段以 `MODEL_COMPLETED` 收尾，驱动照常开下一轮。根因不是驱动判错，而是**完成是模型声明的事实，驱动没有可读的证据**；唯一能观察到的反面证据是「这一轮什么也没做」。

- **判据**：一个 goal 轮次里成功派发的工具调用数为 0（`SegmentOutcome.tool_calls`，落进 `segment/end.tool_calls`）。取消、未派发、围栏拒绝都不算动作。
- **处置**：`next_round` 返回 `stalled`；入口解除武装、**不改相位**、不落 `goal/updated`，回到提示符/idle。人可以用 `/goal resume` 再给一轮，或用 `/goal complete` 结束。为什么不是 `paused`：`armed` 本来就是「要不要自动推进」的进程内开关（D5），`phase` 是目标本身的状态；「已完成但没声明」不该被写成「暂停」。
- **为什么不是自动标完成**：完成需要证据，驱动没有；替模型写 `complete` 会让 `replay` 里出现一条没人做过的声明。为什么不是自动 `blocked`：`blocked` 的语义是「同一阻碍持续到门槛」，空转不是阻碍。
- **提示词是第一道**：`<goal_round>` 的末行要求三选一（complete / blocked / 现在做一个具体动作），并明说「只复述计划、不调用任何工具会被视为停滞」。提示词挡不住的，由熔断兜底。
- **残余**：如果模型在一轮里读了文件、然后说「没有新内容」，`tool_calls > 0`，熔断不触发；这一轮仍会被计为有动作。要更强只能读工作区指纹或要求每轮一个 `todo` 更新——两者都会把「研究型轮次」误杀，暂不做。

**与主流 harness 的对照**：Codex / Claude Code 这类「一问一答」循环在模型不调工具时就停；DSH 的 goal 循环不看工具调用，只看 `complete` / `blocked` / 上限。mini 取两者之间：默认照 DSH 续跑，但把「零动作」当作停止信号。这是 `added`，不是对齐项。

## D15 问题交回人类；完成与轮次的控制面

DSH 的 `ask_user` 超时返回 `{pending: true, callId}`，并说明「用户仍可回答，答案会以 `answer_to_pending_question` 用户消息回来」（`docs/dsh-reference/DSH运行时架构剖析.html`「协作型工具的实现细节」）。这推翻了 D11 的「暂停 + `/goal resume`」：

- **未决问题**：段尾仍有 `session.questions.pending` 时，驱动 MUST NOT 开自动轮次，但目标保持 `active` 与武装；入口回到人手里（chat 提示符、host idle）。
- **回答是一条人类段**：`source.kind == "user"`，`rounds_started` 不推进。该段收尾后，驱动照常判定并开下一 goal 轮（`source.round == n+1`）。所以「人回答后算不算新开一个 goal 轮」的答案是：回答本身不算，回答之后的那一轮才算。
- **目标随时可 edit**：`edit` 只改 `objective` / `max_rounds`，`revision + 1`，相位与武装位都不动（DSH 的 invariant；`docs/dsh-reference/DSH运行时架构剖析.html`：「edit 不改 phase 也不改 activation」）。工具面仍要求人类段；命令面补 `/goal edit`，人不必借模型的手改目标。
- **完成与轮次不是完全不可控**：模型可以 `complete` / `blocked`；`max_rounds` 是硬上限，且**部署策略的 `max_rounds` 是硬顶**——`create_goal` 与 `edit` 的请求值大于它时按它落，模型不能用一个大数字绕开预算（2026-11-20 补）；`/goal edit --max-rounds` 在硬顶内随时改上限；`/goal complete` 给人一个直接收尾的口子；空转熔断（D14）在模型不声明时兜底。模型仍拥有「什么时候算完成」的判断权——这是 DSH 的分层，不假装 harness 能验证完成。

**代价**：`awaiting_input` 不再落 `paused`，日志里看不到「为什么停在这一轮」的持久记录；`segment/end` 只有 `stop_reason=MODEL_COMPLETED` 与 `tool_calls`，`question/asked` 没有配对 `question/answered` 是唯一线索。这是可接受的：问题本身在日志里，人能读。

## 风险

- `user/message` 形状变化波及折叠、投影、CLI 与既有 fixture；旧日志兼容要一条专门的判据。
- 「写日志即准入」意味着日志写失败等于没起轮次；失败必须落 `error/*` 并停，不许静默重试。
- 7 个新结果词每个都要有可达判据（Active Lesson 1 栽过两次）。
- 段边界与投影清空的先后顺序，是实现里唯一容易写反的地方（D8 末段）。

## 测试与 seam

- seam ①：段结束后按条件续跑、不满足条件不起段、额度用尽不起段；
- seam ②：三个 goal 工具、七个结果词、todo 并行拒绝；
- seam ④：`goal/updated` 折叠、`user/message.source` 兼容、`replay` 逐点相等；
- seam ⑥：`/goal`、`/goal pause`、`/goal resume`、`--resume` 后不自动续跑；
- seam ⑦：3 轮上限的轮号连续、第 4 轮不出现、`round-limit` 落盘。

## 附录：一手资料与 commit

- `docs/subsystems/goal.md`（`master`）：`GoalPhase`、`GoalRef`、`GoalSnapshot`、`GoalMessageSource`、"only these admitted `user/message` events advance `roundsStarted`. Replay rejects non-positive rounds, gaps, stale revisions, stopped phases, and cap overflow."
- `packages/goal/goal-round-driver/README.md`（`master`）："only goal rounds that reach model history consume the allowance, and exhaustion records a blocker"；"at the cap it records a blocker with the stable code `round-limit`"；"Mounting the driver over an existing agent never arms a goal, and after session resume or fork an active goal stays disarmed until an explicit human-authorized resume"。
- `packages/goal/goal-round-driver/src/index.ts`（`master`，484 行）：`readyToDrive` / `readyAfterCheckpoint` / `validReservation` / `agent/pre-step` 围栏 / `queue-failed` / `prompt-rejected`。
- `packages/goal/goal-round-driver/src/prompt.ts`（`master`）：`<goal_round>` 块的原文。
- `packages/goal/tool-goal/README.md`（`master`）："a blocked call is mechanically rejected until the configured number of consecutive rounds has passed — the model judges whether the same condition actually persisted"；`GOAL_TOOL_RESUME_PAUSED`。
- `packages/todo/tool-todo/README.md`（`master`）："`allowParallelInProgress` is required with no default: a composition that omits it fails at load"。
- 抓取日期 2026-11-17，`master`；本仓库 `docs/dsh-reference/` 的二手汇编未用于形状判断。
