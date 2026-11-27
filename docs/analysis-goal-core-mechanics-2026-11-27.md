# goal 功能：核心机制与关键决策（2026-11-27 现状笔记）

**定位**：这份笔记回答「goal 今天到底怎么运转」，面向接手者与评审。它不是规格（规格在
`openspec/specs/goal/spec.md`），也不是 M13 的过程记录（那份在 `docs/reference/goal-rounds.md`）。
两者的区别：规格写「必须怎样」，这篇写「为什么这样、语义边界在哪、代码落在哪」。

**适用范围**：`main@4b08386` 之后（`merge/reasoning` 已合入）；政策版本 **v3**。

---

## 0. 一句话与四层结构

**一句话**：目标只活在日志的 `goal/updated` 里；`goals.py` 管「什么转移合法」，`goal_driver.py`
管「该不该再开一轮」，`turn_loop.py` 管「跑」，`settle_turn` 是三者唯一的接线处。

```
cli/main.py (chat) ─┐
session/host.py ────┼→ settle_turn ─┬→ goal_driver.next_round   只判，不写
loop/turn_loop.py ──┘  （turn_loop） ├→ goals.fold_goal          读状态
   run_session_env                   └→ goals.exhaust/abort/pause 算新状态
                                            ↓
                                   EventLog.append("goal/updated")  唯一写点
```

---

## 1. 名词：先拆清楚，再谈机制

### 1.1 四个时间词

| 层 | 名字 | 边界事件 | 数什么 | 日常类比 |
|---|---|---|---|---|
| 会话 | session | `session/start` / `session/end` | 一整个日志 | 一次「上班」 |
| 轮 | turn | `turn/start` / `turn/end` | 一条输入展开的那串步 | 一件事从头做到交差 |
| 步 | step | `step/start` / `step/end` | 一次模型往返 + 这批工具 | 打一个电话、查一次资料 |
| 目标轮 | goal round | 没有独立事件，数 `source.round` | goal 消息被准入的次数 | 同一件事的第 N 天 |

**关键语义**：目标轮**不是**第四层嵌套，而是「轮」的一种。goal 来源的轮就是目标轮，人类来源的
轮不是。所以「goal 轮恰是一次目标轮」成立；`rounds_started` 数的是这种轮，人类轮不计数。

### 1.2 三个容易混的「计数」

| 名字 | 数什么 | 什么时候加 | 会不会落盘 |
|---|---|---|---|
| `revision` | 目标定义的**版本号** | 控制面动作（create/edit/pause/resume/complete/blocked/clear）各 +1 | 落盘（快照里） |
| `rounds_started` | 已准入的**目标轮数** | 每轮首条 `context/assembled` 落盘后 +1 | 落盘 |
| `armed` | 要不要**自动推进** | 建/恢复 → 真；暂停/完成/阻塞/额度用尽/失败/停滞 → 假 | **不落盘** |

**为什么 `armed` 不落盘**：落盘会让 `--resume` 之后意外自动跑。它是入口的进程内开关，不是目标
的状态；目标的状态是「它是什么」，武装位是「现在要不要自动开下一轮」。

**为什么轮次推进不递增 `revision`**：模型在轮内拿着 `goal_id@revision` 调 `update_goal`；如果每轮
都 +1，第一轮的引用在第二轮就过期，`update_goal` 会莫名失败。DSH 的 `roundsStarted` 同样是派生值。

---

## 2. 事件与状态形状

### 2.1 事件

| 事件 | 载荷要点 | 谁写 | 语义 |
|---|---|---|---|
| `goal/updated` | `{goal: 快照}` 或 `{goal: null}` | 工具 / 命令 / 驱动 | 目标的**唯一**事实；整值快照，不是增量 |
| `user/message` | `{content, source}`；goal 来源带 `{kind:"goal", goal_id, revision, round}` | 轮入口 | 区分人话与自动轮；轮号在 `source.round` |
| `turn/end` | `{turn_id, stop_reason, steps, tool_calls}` | `turn_loop` | `tool_calls` 是停滞闸门的判据 |
| `question/asked` / `question/answered` | `{question_id, ...}` | `ask_user` | 未决问题只有「问了没答」这一条线索 |

`goal/updated` 的 `{"goal": null}` 是**显式清除**，折叠时不能被跳过；旧日志缺 `source` 的
`user/message` 一律按人类来源读（兼容规则）。

### 2.2 持久快照（`GoalSnapshot`）

| 字段 | 含义 | 约束 |
|---|---|---|
| `id` / `revision` | 身份与定义版本 | 正整数；CAS 用 |
| `objective` | 目标正文 | 非空 |
| `phase` | `active` / `paused` / `blocked` / `complete` | 四值 |
| `max_rounds` | 单目标轮次上限 | ≥1；部署值是硬顶 |
| `rounds_started` | 已准入轮数 | ≥0 |
| `blocked_reason` | `{code, message}` | 仅 `blocked` 时存在，两者非空 |

形状约束在 `GoalSnapshot` 上由 pydantic 强制：`blocked` 必带原因、非 `blocked` 不许带。这条
不是装饰——`_next()` 每次改动都用 `model_validate` 重跑一遍，防止某条路径写出自相矛盾的快照。

### 2.3 进程内状态（`GoalRuntime`）

```python
@dataclass
class GoalRuntime:
    armed: bool = False      # 要不要自动推进
    idle_rounds: int = 0     # 连续多少个 goal 轮次零工具调用
```

`idle_rounds` 的维护规则：goal 轮 `tool_calls == 0` → +1，有动作 → 清零；人类轮一律清零。
只有 `stall_rounds > 0` 时它才参与判定。

---

## 3. 状态机：谁能把 phase 推到哪

### 3.1 phase 转移

| 起点 | 动作 | 终点 | 谁有权 | 附带效果 |
|---|---|---|---|---|
| （无） | `create` | `active` | 模型（人类轮内） | `revision=1`、`rounds_started=0`、武装 |
| `active` | `pause` | `paused` | 模型（人类轮内）/ `/goal pause` | 解武装 |
| `paused` | `resume` | `active` | **只** `/goal resume`（人） | 解 `blocked_reason`、武装 |
| `active`（未武装） | `resume`（工具） | `active` | 模型（人类轮内） | 重新武装（`/goal resume` 之外的合法路径） |
| `paused` | `resume`（工具） | 拒绝 | 模型 | `GOAL_RESUME_BY_TOOL_DENIED`：暂停只能由人恢复 |
| `active` | `complete` | `complete` | 模型 / 人 | 解武装 |
| `active` | `blocked` | `blocked{model-reported}` | 模型（须跑满门槛轮数） | 解武装 |
| `active` | 额度用尽 | `blocked{round-limit}` | **系统**（驱动） | 解武装 |
| `active` | 取消（`ABORTED`） | `paused` | 系统（收尾） | 解武装 |
| 任意非 complete | `clear` | （无目标） | 人（`/goal clear` / CLI） | 解武装 |
| `complete` | `resume` | 拒绝 | 任何人 | `GOAL_INVALID_TRANSITION` |

一张图：

```
        create                 pause                resume(/goal, 人)
  ∅ ──────────▶ active ──────────────▶ paused ──────────────▶ active
                  │  ▲                    │
     complete     │  └──── resume(工具) 拒 ┘
                  ▼
              complete
                  │  blocked(模型,≥门槛) / round-limit(系统)
                  ▼
              blocked ─── resume(/goal 或工具) ──▶ active（清 blocked_reason）
```

### 3.2 武装位（armed）转移

| 事件 | armed |
|---|---|
| 启动 / `--resume` / 从日志重建 | **假** |
| `create_goal` | 真 |
| `/goal resume`、`update_goal(resume)` | 真 |
| `pause` / `complete` / `blocked` / `clear` | 假 |
| 额度用尽（round-limit） | 假 |
| 失败收尾（四类） | 假 |
| 停滞闸门触发 | 假（相位不动） |

### 3.3 单目标约束

同一会话至多一个**非 `complete`** 的目标。已有未完成目标时 `create_goal` 返回
`GOAL_ALREADY_ACTIVE`；上一个已完成则允许建新目标（新 `id`、`revision=1`、`rounds_started=0`）。
多任务并行靠 todo 里多个 `in_progress`（ADR-0042），不靠多个目标。

### 3.4 CAS：为什么写目标要带 `id@revision`

`update_goal` 必须带 `goal_id` + `revision`，与当前快照不符返回 `GOAL_REF_STALE` 且不落事件。
语义是「拿旧目标改新状态」要被拒：模型可能在一轮里先读到目标、又经过一次人的 edit，然后拿旧引用
调用 complete——CAS 把这次写入挡掉，而不是把人的修改覆盖掉。

`revision` 只随控制面动作递增；`advance_round` 只改 `rounds_started`。这是两套计数能共存的前提。

---

## 4. 政策面：目标行为是怎么「告诉模型」的

政策面有三层，职责不同，不能互相替代：

| 层 | 载体 | 内容 | 是否可被覆盖 |
|---|---|---|---|
| 系统政策段 | `session/start.goal_policy` → 受保护头部 | 「什么时候建目标、建完就停、每轮推进一块」 | **不可**（`append_system_prompt` 只能追加，不能改） |
| 工具描述 | `create_goal` / `update_goal` 的 description | 使用条件、分轮边界、完成必须调工具 | 否（代码里固定） |
| 每轮正文 | `<goal_round>` 块 | `Objective`、`Round: n/cap`、终局三选一 | 否（每轮由驱动生成） |

### 4.1 版本号与不可变性

`GOAL_POLICY_VERSION = "v3"`，`GOAL_POLICY_VERSIONS` 里 v1/v2/v3 原文**全部保留**：

- `session/start.goal_policy` 记录当轮用的版本；
- `context/assembled` 的 system 消息按这个版本**重算**——`replay` 与实时装配必须得到同一份文本；
- 改旧版本文本 = 历史会话重放出的上下文与日志不一致，所以只能新增版本。

这是「政策也是日志事实」的具体形态：政策不是配置，是**可审计的输入**。

### 4.2 v3 的核心语义（2026-11-26 一句话任务 UX）

v3 在 v2 基础上加了一段触发规则，关键在于**触发条件写「任务性质」而不是「工作量估计」**：

> 若你有 `create_goal` 工具且手上的任务要写文件、改代码、跑命令验证或查多处资料——哪怕人只给了
> 一句话，也别等人吩咐流程：第一步就建目标……建目标的那一轮只做计划……正式内容从目标轮 1 开始。

第一版写的是「需要多步或多轮」，结果模型自评「一轮能干完」就不建目标，两场真实任务都失败。
改成按任务性质（要写文件 / 改代码 / 跑命令 / 查多处）后，三场一句话提示词全部按预期建目标。
**教训**：给模型的触发条件要可观察（任务类型），不要依赖它的自我工作量估计。

v3 同时保留 v2 的停滞闸门表述与 v1 的「人输入开的轮不推进目标轮次」。

### 4.3 为什么政策要进受保护头部

模型在长会话里会被压缩、被注入、被用户提示词干扰；如果政策只是「第一次 system 消息里的
一段话」，压缩后可能丢。受保护头部由 `context/assembled` 每步重算、按 `session/start` 的事实
重建，压缩只能遮蔽普通消息，动不了它。这也是「人裁：政策面不能靠用户提示词」的落点。

---

## 5. 驱动：一轮结束后要不要再开一轮

### 5.1 五选一

`next_round(...)` 是纯函数，输入六样，输出五选一：`stop` / `continue` / `exhausted` /
`awaiting_input` / `stalled`。判定顺序**先硬后软**：

| 顺序 | 条件 | 结论 | 处置 |
|---|---|---|---|
| 1 | 无目标 / 非 `active` / 未武装 | `stop` | 不开轮 |
| 2 | `stop_reason ∈ {ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED}` | `stop` | 解武装；`ABORTED` 另置 `paused`，其余相位不动 |
| 2.5 | `stop_reason == MAX_STEPS` | 继续判 3–6 | **轮边界，不是失败**：写满本轮步数只结束这一轮 |
| 3 | `rounds_started >= max_rounds` | `exhausted` | 写 `blocked{round-limit}`，解武装 |
| 4 | 轮尾有未决问题 | `awaiting_input` | 不开轮，保持 `active/armed`，交回控制权 |
| 5 | `stall_rounds > 0` 且是 goal 轮且 `idle_rounds >= stall_rounds` | `stalled` | 解武装、相位不动、计数清零 |
| 6 | 其余 | `continue` | 开下一轮，`rounds_started + 1` |

**顺序本身就是语义**：额度用尽比未决问题更硬（最后一轮里问了问题也先落 blocker）；问题比空转更硬
（先告诉人「等你回答」，而不是判死循环）。

### 5.2 `MAX_STEPS` 为什么不算失败

`MAX_STEPS` 只表示「这一轮把步数用完了」，模型和工具都可能完全正常。如果把它当失败，长任务会在
第一轮就被截断——2026-11-25 人裁（`goal-round-pacing`）把 `MAX_STEPS` 移出「不续跑」集合。
它仍在 `turn/end.stop_reason` 里如实记录，只是驱动不据此停。

### 5.3 停滞闸门（D14）

- 阈值 `[goal] stall_rounds`，缺省 **2**；`0` 关闭（完全对齐 DSH）。
- 判据单位是**轮**，不是步：一轮里只要有一个成功派发的工具调用就不算空转。
- 处置只解武装、不改相位、不落事件：「空转」不该被写成「人叫停」。
- 阈值取 1 会误杀「读文件后判断没新内容」的研究型轮次；取 3 以上白烧额度。
- 残余风险：模型每轮读一个文件再说「没有新内容」时 `tool_calls > 0`，闸门不触发。更强判据
  （工作区指纹、每轮必须更新 todo）会误杀研究型轮次，不做。

### 5.4 失败收尾的语义

| 收尾 | 相位 | 武装 | 理由 |
|---|---|---|---|
| `ABORTED`（人取消） | `active` → `paused` | 假 | 人叫停 = 暂停，不是失败 |
| `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` | 保持 `active` | 假 | 上游抖动不该替人决定目标作废，`/goal resume` 即可 |

写日志失败时不静默重试：落 `error/*`、结束会话、非零退出码。

---

## 6. 多轮推进：一轮是怎么被「准入」的

### 6.1 goal 轮的轮首顺序（ADR-0043）

```
turn/start
  → goal 来源 user/message（正文是 <goal_round> 块）
  → 首条 step/start
  → 首条 context/assembled
  → goal/updated（rounds_started 递增，revision 不变）
  → model/request
```

**为什么额度记在 `context/assembled` 之后**：这一轮真的装进了上下文才算数。装配之前失败（预算超线、
注入失败、折叠失败、装配内压缩失败）不消耗轮次——这是 DSH「进模型历史才计数」在 mini 的等价物。
`step/start` 与 goal 消息已经落盘的失败轮次，`rounds_started` 保持原值，日志里能看到「有人试过但没算数」。

### 6.2 三个入口共用一份收尾

`run_session_env`（run/serve/subagent）、chat 的 REPL 循环、host 的回合协程，三处都调
`settle_turn`，避免「host 只有命令面、没有驱动」这类分叉（2026-11-20 人裁）。差别只在入口怎么处理
五种决策：

| 决策 | run/serve | chat | host |
|---|---|---|---|
| `continue` | 立即开下一轮（同一协程） | 不打印提示符，直接开下一轮 | 协程内继续，事件流实时推 |
| `stop` | 收会话 | 回提示符 | 回 idle，等消息 |
| `exhausted` | 收会话 | 打印「已用尽」后回提示符 | 落 blocker，事件流可见 |
| `awaiting_input` | 收会话（目标保持 active） | 提示「回答后自动继续」，回提示符 | 回 idle，等下一条消息 |
| `stalled` | 收会话 | 打印「已停止自动推进」，回提示符 | 解武装，回 idle |

### 6.3 人话优先（D13）

host 的 `submit_message` 在轮进行中把消息放进**深度 1** 的队列；轮收尾后先跑队首人话，队列空才开
goal 轮。人类轮 `goal_round=False`：不推进 `rounds_started`、不改 `phase`、不改 `revision`、清零
`idle_rounds`。粒度是**轮边界**，不做步之间插队——对齐 DSH 的 `competingQueued`。

chat 没有轮中队列（同步 `readline`），提示符上的下一条输入同样先于自动轮次。这是本地入口的形态，
不是语义缺失。

### 6.4 提问与「回答算不算新轮」（D15，取代 D11）

- 轮内答上（tty / host 的 HTTP 等待窗口内）：同一轮继续，不新开轮。
- 答不上（`QUESTION_UNAVAILABLE`）：轮尾驱动给 `awaiting_input`，**目标保持 `active/armed`**，
  回到提示符 / idle。
- 人的回答是一条**人类轮**，不推进轮号；这轮收尾后驱动照常判定，下一 goal 轮是 `round + 1`。
- 未决问题是**轮作用域**：轮首清空，不跨轮继承。

结论一句话：**回答本身不算新开一个目标轮，回答之后的那一轮才算。**

### 6.5 `/goal resume` 即驱（D12）

命令把武装位从假翻到真之后，chat 与 host **立刻开下一轮**，不等客户端再发一条。判定收在
`next_goal_round(env)`；如果目标已经 active 且已武装，`/goal resume` 只回一句「无需 resume」，
不能再起一轮——否则问题未决时敲习惯性命令会白烧额度。

---

## 7. 人类轮 vs 目标轮：语义差异与屏幕表达

### 7.1 语义差异表

| 维度 | 人类轮 | 目标轮 |
|---|---|---|
| `user/message.source` | `{kind:"user"}` | `{kind:"goal", goal_id, revision, round}` |
| `rounds_started` | 不动 | +1（准入后） |
| `revision` | 不动 | 不动 |
| `phase` | 不动 | 不动（除非模型在本轮 complete/blocked） |
| 工具权威 | 可 create/edit/pause/resume | 只能 complete/blocked；create/edit/pause/resume 被拒 |
| `idle_rounds` | 清零 | 零工具调用 +1，否则清零 |
| 屏幕标记 | 无 `[轮] n/cap` | 开轮前打 `[轮] n/cap` |
| todos | 轮首清空 | 轮首清空（同一规则） |

### 7.2 打印规则（chat）

打印分两类，走 stderr，不进日志：

**A. 轮号横幅（只给自动轮）**

- 开每一轮自动轮之前：`[轮] n/cap`（n = `source.round`，cap = `max_rounds`）。
- 人类轮**不打**——人手里有提示符，知道自己刚发了什么；自动轮人没按回车，需要一行说明「这是第几轮」。

**B. 轮收尾行（所有轮，除 `MODEL_COMPLETED`）**

- `[轮] 收尾 <stop_reason>：<code> <detail>`，例如 `[轮] 收尾 ABORTED`；
- 四种驱动结论各有专句：
  - `[轮] 已用尽 n/cap：目标置为 blocked（round-limit）`
  - `[轮] 本轮有一个没答完的问题：目标保持 active；直接回答，回答后自动继续`
  - `[轮] 本轮没有工具调用：已停止自动推进（/goal resume 继续，/goal complete 结束）`
  - `stop` 无专句，直接回提示符。

**C. 提示符**

- 只有「回到等待状态」时才打 `> `：人类轮结束、`stop`/`exhausted`/`awaiting_input`/`stalled` 之后；
- 自动轮之间**不打**提示符——打了会让屏幕看起来像在等人输入。

### 7.3 屏幕上的一个完整片段（语义示例）

```
> 把测试修到全绿                     ← 人类轮（无 [轮] 横幅）
[thinking] ……
[answer] ……
[轮] 1/8                            ← 第 1 个目标轮（模型建了目标并结束本轮后自动开）
[tool] read …
[轮] 2/8                            ← 第 2 个目标轮
[轮] 已用尽 2/8：目标置为 blocked（round-limit）
>                                   ← 回提示符
```

注意 `[轮] 1/8` 出现在**建目标那一轮之后**：create 发生在人类轮里，人类轮本身不计入 `rounds_started`。

---

## 8. 工具面的权威与拒绝码

| 动作 | 人类轮 | 目标轮 | 子会话 |
|---|---|---|---|
| `get_goal` | 可 | 可 | 可 |
| `create_goal` | 可 | `GOAL_AUTHORITY_REQUIRED` | `GOAL_AUTHORITY_REQUIRED` |
| `update_goal edit/pause/resume` | 可 | `GOAL_AUTHORITY_REQUIRED` | `GOAL_AUTHORITY_REQUIRED` |
| `update_goal complete/blocked` | 可 | 可 | 不受人类轮约束，但子会话通常没有目标，实际返回 `GOAL_REF_STALE` |

拒绝码一览：`GOAL_AUTHORITY_REQUIRED`、`GOAL_ALREADY_ACTIVE`、`GOAL_REF_STALE`、
`GOAL_INVALID_TRANSITION`、`GOAL_BLOCK_TOO_EARLY`、`GOAL_RESUME_BY_TOOL_DENIED`、
`GOAL_NOT_FOUND`（CLI）。

**为什么 create/edit/pause/resume 要人类轮**：这四个动作改变「要做什么」或「要不要继续」，属于人的
决策；让模型在自动轮里改目标会出现「自己给自己换题」。`complete`/`blocked` 是模型对「做完没有 /
做不动了」的判断，必须由它自己声明——harness 没有可读证据。

---

## 9. 预算、阻塞与完成

### 9.1 三种停止来源

| 来源 | 强度 | 表现 |
|---|---|---|
| 模型 `complete` | 声明 | `phase=complete`，解武装 |
| 系统 `round-limit` | 硬 | `rounds_started >= max_rounds` → `blocked{round-limit}` |
| 模型 `blocked` | 半硬（有门槛） | 需跑满 `blocked_after_consecutive_rounds`（缺省 3） |
| 人 `/goal pause|complete|clear` | 硬 | 直接落快照 / null |

### 9.2 上限是硬顶

`create_goal` / `edit` 请求的 `max_rounds` 超过部署值（缺省 32）时按部署值落；人类 CLI
`minihns goal <id> edit --max-rounds` 同样被截。要真正跑更多轮只能改部署配置。
`create_goal` 显式给出小于门槛的上限**不拒绝**：该目标只能走到 `round-limit`，`model-reported`
出口对它关闭——这是调用方的显式选择。

### 9.3 `blocked_after_consecutive_rounds` 名不副实

字段名说「连续」，实现与规格数的是 `rounds_started` **总轮数**（至少跑满 N 轮才允许报阻塞），
不是「同一阻碍连续 N 轮」。要按阻碍内容判重得再加一份状态，现在没做——这是已知缺口，写在这里
避免下一个人按名字误解。

### 9.4 完成不可验证

完成是「工作区里的目标是否达成」的事实，harness 没有可读证据。能加的是**反面证据**：一轮里一个
成功派发的工具调用都没有，说明这一轮没推进——这就是停滞闸门。所以「问题解决了但目标还是 active」
是结构性正常，不是 bug：模型没调 `update_goal complete`。

---

## 10. 命令面分工

| 位置 | 命令 | 语义 |
|---|---|---|
| chat 提示符 / host `POST /commands` | `/goal` | 查看快照、武装位、阻塞原因 |
| 同上 | `/goal pause` / `resume` / `complete` / `clear` | 无参数动词；带参数报用法 |
| 同上 | `/goal edit <正文>`、`/goal <正文>` | 只换 objective，`revision+1`，相位与武装位不动 |
| CLI（离线） | `minihns goal <id> show|edit|clear` | `edit` 可带 `--max-rounds`；**不做** pause/resume/complete |

**分工理由**：`--flag` 是脚本接口，提示符是自然语言界面（2026-11-23 人裁）。运行期控制
（pause/resume/complete）离线写会产生「没人按过」的动作，只留在会话内；上限编辑带 flag，归 CLI。

---

## 11. 重放与自洽校验

`replay` 不信任日志，会检查 goal 轮次的自洽（`goal_round_defect`）：

- 轮号为正、同一 `goal_id` 内不跳号、不超 `max_rounds`；
- `revision` 与当前快照一致；
- `phase` 已停（`paused`/`blocked`/`complete`）之后不再出现轮次消息；
- 每条快照的 `rounds_started` 等于此前已出现的轮次条数。

校验按 `goal_id` 分组——换目标后轮号重新从 1 起算，重复轮号合法。任何一条不满足，`replay` 以
日志不自洽结束、退出码非零。这保证「目标状态」不是某次运行的内存残留，而是可从日志重建的事实。

---

## 12. 与主流 harness 的对照

| 系统 | 完成判据 | 空转处理 | 预算 |
|---|---|---|---|
| DSH | 模型 `complete` / `blocked` / `max_rounds` | 无 | 轮次硬上限 |
| Claude Code `/goal` | 每轮由独立小模型判 `met / not yet met / impossible` | 连续几轮不用工具才停，保留 goal | 条件里可写「跑满 20 轮就停」 |
| Codex goal mode | 结构化 `update_goal`（pursuing/paused/achieved/unmet/budget_limited） | Ralph loop 的 Review 阶段 | token 预算建议性 |
| mini | 模型声明 + 硬上限 + 停滞闸门 + 人的命令 | 连续 2 轮零动作 → 解武装 | `max_rounds` 硬顶（缺省 32） |

三家都没有「保证语义完成」；最终闸门在 harness（轮次 / 预算 / 阻塞次数），完成声明在模型。

---

## 13. 关键决策表

| 决策 | 结论 | 理由 | 记录 |
|---|---|---|---|
| 轮次准入点 | 首条 `context/assembled` 之后 | 装配成功才算一轮，失败不白烧额度 | ADR-0043 |
| 单目标 | 同时只有一个未完成目标 | 对齐 DSH；并行靠 todo | ADR-0042 |
| 人话优先 | 队列非空不开 goal 轮 | 对齐 `competingQueued`；粒度是轮边界 | design D13 |
| 问不到人 | 保持 `active/armed`，交回控制权 | 「等人」不是「暂停」；回答是人类轮 | design D15（取代 D11） |
| resume 即驱 | 命令成功立刻开下一轮 | 否则人要再敲一行，那行会开人类轮 | design D12 |
| 停滞闸门 | 缺省开、阈值 2；`0` 关闭 | 1 轮误杀研究型轮次，3 轮白烧额度 | design D14 |
| 命令面 flag | 会话内无 flag，上限编辑归 CLI | flag 是脚本接口，提示符是自然语言界面 | 2026-11-23 人裁 |
| 上限硬顶 | 请求超过部署值按部署值落 | 模型不能拿大数字绕开预算 | design D15 |
| 政策版本化 | v1/v2/v3 原文冻结，按 `session/start` 重算 | 政策是日志事实，重放必须一致 | `goal-ux-one-line` |
| v3 触发条件 | 按**任务性质**（写文件/改代码/跑命令/查资料） | 按「多步多轮」会让模型自评「一轮够」而不建目标 | `goal-ux-one-line` 真端点 |

---

## 14. 边界与已知缺口

- **完成不可验证**：只有模型声明；停滞闸门只抓「零动作」，抓不到「读了文件但没推进」。
- **`fold_goal` 全量重读**：每轮 O(n)，长会话累计 O(n²)。要优化可加「最后一条 goal 事件的 seq
  索引」或从文件尾倒读，不能改成内存缓存优先（多写入点的一致性问题）。
- **chat 没有轮中队列**：同步 `readline`；host 才是通用入口。
- **host 队列深度 1**：轮进行中只能再排一条，第三条被拒。
- **未决问题没有持久记录**：不落 `paused`，日志里只有 `question/asked` 没有配对的
  `question/answered`；人能读，审计要自己配对。
- **目标表不跨轮**：`todos` 在轮首清空，goal 轮同样清（DSH 的 round 就是一次 turn）；跨轮靠模型
  历史与目标，不靠表。
- **`blocked_after_consecutive_rounds` 名不副实**：见 §9.3。
- **edit 的两个坑**：正在跑的轮不变（`GoalRound` 快照已冻结）；`--max-rounds` 调到 ≤ 已用轮数时
  下一轮直接 `exhausted`；轮内拿旧 `revision` 调 `complete` 会被 CAS 拒。

---

## 15. 出处

- 代码：`src/mini_harness/goals.py`、`loop/goal_driver.py`、`loop/turn_loop.py`（`run_turn` /
  `settle_turn` / `next_goal_round` / `close_failed_round`）、`tools/goal.py`、`commands.py`、
  `cli/main.py`（轮循环与打印）、`session/host.py`（队列与驱动）
- 政策：`events/fold.py` 的 `GOAL_POLICY_VERSIONS`
- 规格：`openspec/specs/goal/spec.md`（9 条 Requirement）
- 过程笔记：`docs/reference/goal-rounds.md`（M13 实现笔记，含 D1–D15 细节）
- 验收：`docs/verification/goal-ux-one-line-*.md`、`docs/verification/m13-goal-rounds-*.md`
- ADR：`docs/adr/0042`、`docs/adr/0043`
