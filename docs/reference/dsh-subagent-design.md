# DSH 的子代理：设计、机制与 mini 的对照

**定位**：一份系统笔记，回答「DSH 怎么设计子代理、为什么这么设计、mini 在哪一步对齐/简化」。它不是规格，规格在 `openspec/specs/subagent-delegation/`；mini 侧的落成形状与判据在 `docs/reference/subagents.md` 与 `docs/verification/m12-subagent-delegation-*`。本文把散在各处的调研、术语和推理串成一条可读的线。

**证据等级**（读的时候请区分）：

1. **一级**：DSH 公开仓库的 README / Agent Note（`github.com/deepseek-ai/deepseek-harness`，本文引用的固定 commit 是 `fcc0ad46`）。
2. **二级**：DSH 团队公开的 Super-agent 文章与第三方拆解（发布日期 2026-10-31 左右）。
3. **三级**：本仓库 `docs/dsh-reference/` 的逆向取证（较早快照，结构仍有效）。
4. **推断**：没有直接出处、由上面三类推出并标注「推断」的句子。

---

## 1. 从一个任务说起

你在一个会话里对模型说：「把这三份实验报告读一遍，写个综述。」

模型可以自己做，但它也可以**把其中一份派出去**：创建一个**子会话**，只给它一句自足的任务（「读 a.md，总结成三点」），让它在自己的上下文里跑完，只把**最终结论**带回来。父会话的上下文只增加一条结果，而不是子会话的整段过程。

这次「派出去」在 DSH 里叫**委派（delegation）**，被派出去的那一半叫**子代理（subagent）**。要把它设计对，必须回答五个问题：

1. **子会话从哪儿起步？** 空对话（`spawn`），还是抄父会话已完成的历史（`fork`）？
2. **子能看见什么、能碰什么？**（工具面、工作目录、沙箱）
3. **子要不要问人？** 谁能批准它？（审批）
4. **能派多少个、能派多深？**（容量、深度）
5. **结果怎么回来？** 父要等它、还是继续干别的？（交付与通知）

DSH 的整套设计就是这五个问题的答案，加上一条贯穿所有答案的原则：**日志是唯一真源，子会话有自己的日志，父只通过一对工具记录与它相连**。

---

## 2. 基础概念与术语

先立词，后面的推理才不飘。

| 术语 | 一句话解释 | 在本笔记里的位置 |
|---|---|---|
| **Session（会话）** | 一份只追加的事件日志（JSONL）加它的派生状态；「当前上下文」由折叠日志得到 | 一切单位的容器 |
| **Agent** | 跑在 Session 里的执行体；DSH 里一个 Agent 有自己的注册作用域、模型路由与会话 | 子代理 = 子 Agent |
| **Turn / 回合** | 一次「模型调用 + 它的工具派发」 | 循环单位 |
| **Tool（工具）** | 一项能力契约：名字、参数 schema、执行入口；失败也是结果 | 子代理能做什么 |
| **工具注册表 / 注册作用域** | 某个 Agent 当前能用的工具集合；**作用域**强调它按 Agent 构造，不是全局共享 | 组合过滤的落点 |
| **组合过滤（composition filter）** | 从「可用工具目录」里挑一个子集，**只决定能力，不决定授权** | preset 的机制 |
| **Preset（预设）** | 一套预打包的 Agent 配置：persona、工具（DSH 的 `agentPreset`） | 部署决定子代理的方法 |
| **Permission preset（权限预设）** | 把沙箱模式与审批策略捆在一起的选择器（如 workspace-write + ask） | 与 Agent preset 不是一回事 |
| **Sandbox mode（沙箱模式）** | `read-only` / `workspace-write` / `danger-full-access`；回答「能碰哪儿」 | 授权的一轴 |
| **Approval policy（审批策略）** | `ask` / `never`；回答「要不要问人」；`never` 是**确定性拒绝**，不是自动批准 | 授权的另一轴 |
| **Approval seam（审批缝）** | 一个服务：把「这个操作可以继续吗」路由给**拥有该 Agent 的通道**，并落审计对 | 谁能批准 |
| **Responder（应答者）** | 审批缝上的监听器：交互宿主、自动化客户端、测试脚本；没有应答者 → `unavailable` | 谁在答 |
| **allowed-once** | 只放行被问的那一次调用，授权不跨调用存活 | 审批结果词 |
| **Spawn / Fork** | 子会话的两种起步：空对话 / 父已完成轮次的前缀 | 起步方式 |
| **Activation（激活）** | 一次被管理的委派执行：启动、运行、结算、清理 | 生命周期单位 |
| **Completion notification（完成通知）** | 子级结束后发给父级的一条 user 角色消息，带最终答案 | 结果怎么回来 |
| **`delivery: parent / caller`** | 结果交给父（发通知）还是交给调用方（工作流等待 result） | 交付对象 |
| **`maxDepth`** | 递归深度上限，默认 1；深度 = 父 + 1 | 能派多深 |
| **`maxActiveSubagents`** | 每棵 subagent 树里在线 + 正在创建的子级上限，默认 8；根不占名额 | 能派多少 |
| **Agent 名称** | 根的 `lead`、子级 `agent-N`、完整路径 `reviewer/checker` | 身份与引用 |
| **结果词** | 失败也是结果：`ACTIVATION_LIMIT_REACHED`、`DEPTH_EXCEEDED`、`subagent/delivery-unavailable` 等 | 失败怎么表达 |
| **Super-agent** | Router（主会话派单）+ Worker（每任务一个会话）+ Thread（事件路由）+ Watchdog（独立巡检） | 委派的上一层拓扑 |

两条容易混的边界，先划清：

- **Agent preset ≠ Permission preset**：前者决定「这个 Agent 是什么样」（人设、工具），后者决定「它能干什么、要不要问人」（沙箱、审批）。DSH 把它们分成两个包。
- **工具 ≠ 权限**：工具面是能力组合；能不能用仍由沙箱、边界、审批判定。所以「子代理有了 bash」不等于「它被允许写文件」。

---

## 3. DSH 的三层结构

DSH 的委派不是一个函数，而是三个包各管一段：

```
┌──────────────────────────────────────────────────────────┐
│ 工具面  dsh-tool-subagent                                │
│   给模型的 `subagent` 工具：schema、参数、启动、返回名称   │
├──────────────────────────────────────────────────────────┤
│ 服务    dsh-subagent                                     │
│   提供方注册表 + 受管理 activation：容量、深度、结算、清理 │
├──────────────────────────────────────────────────────────┤
│ 后端    dsh-subagent-spawn-in-process / fork / acp / ... │
│   真正创建子 Agent：进程内、进程外、外部 CLI             │
└──────────────────────────────────────────────────────────┘
```

- **工具面**只做「模型能看到什么、调用时传什么」。它不拥有生命周期；调用后立刻返回子任务名称，工作交给运行时。
- **服务**是唯一的所有者：谁在跑、占多少额度、什么时候结算、失败怎么收尾。
- **后端**决定子 Agent 在哪跑：`spawn`（同进程、空对话）、`fork`（同进程、带父前缀）、`acp` / Codex / Claude Code（进程外，执行一次）。

同进程后端（`spawn` / `fork`）与外部后端的关键差别：前者有**本地子 Session**，可以接受后续消息、可以冷恢复；后者执行一次，不接受继续输入。

---

## 4. 一次 spawn 的完整生命周期

按 DSH 的公开 README 把一次 `subagent` 调用拆开（编号是叙述顺序，不是源码行号）：

1. **模型产出调用**：`subagent(task="…", agent_preset?=…)`。`task` 必须自足——spawn 不带父对话。
2. **工具校验**：`provider` 存在、参数合法、`agent_preset` 在白名单枚举内、深度不超过上限。启动失败返回**出错的工具结果**，不会留下已发布的子 Agent。
3. **服务预留**：子级身份与容量槽；超过 `maxActiveSubagents` 直接以 `ACTIVATION_LIMIT_REACHED` 拒绝（浏览器消息走 `subagent/delivery-unavailable`）。额度**不排队**——避免父等子、子又占着父的额度。
4. **解析 preset**：模型给的选择 → 配置的默认 → 父当前的 preset 代际。选中后**在启动时解析**；未知或加载失败 → 出错结果、不启动。
5. **构造子作用域**：按 preset 从工具目录组合出子 Agent 的注册作用域。**父的 Agent 局部工具限制不导入**。
6. **创建子 Agent**：同进程后端创建子 Session（新日志）、写 `session/start`（含父 id、深度、preset）；进程外后端起一次执行。
7. **返回名称**：工具结果只是 `started subagent <name>`。**结果不在这里**。
8. **父继续**：父可以在子运行期间做别的事，或结束本回合。
9. **子结算**：子跑完（或失败/被取消）→ 服务收集最终输出与停止原因 → 清理资源 → 归还容量。
10. **完成通知**：父仍在线时，子级最终答案作为一条 user 角色消息投递给父；父如果空闲，这条消息会起一次新的模型回合。
11. **审计与持久化**：子 `session/start`、父的工具记录、子日志都在；父的上下文里只有通知（最终答案），没有子的过程。

**一句话**：DSH 的委派是**异步**的——工具调用只负责「启动并拿到名字」，结果走通知。

---

## 5. 工具面：scope、preset 与组合过滤

这是这次讨论里最容易误解的一层，分开说。

### 5.1 「scope.tools」是什么

DSH 的伪代码里有一行 `scope.tools = 组合过滤(非授权继承)`。它描述的是**结果**：子 Agent 的注册作用域里最终有哪些工具。它不是模型传进来的参数。

### 5.2 谁决定 scope.tools 的内容

三种情况，按优先级：

1. **模型选了 preset**：preset 的工具表（部署写的）就是内容。模型只能选白名单里的 id，**不能挑单个工具**。
2. **配置了默认 preset**：用默认的那套。
3. **都没有**：子级「加入父方当前的 preset 代际」——继承父的组合。**派发照常，不会因为没有 preset 而失效。**

### 5.3 组合从哪里取

从**工具目录（catalog）**——宿主组合出来的可用工具全集。preset 的工具表是这张目录的一个子集，**不是父会话工具表的子集**。spawn README 的原话：

> 子级在继承或独立选择的 preset 之下拥有自身注册作用域，**不导入父方的 Agent 局部工具限制**。

这条不是细节：Super-agent 的设计里 Router **可以不带 bash**、Worker **有全工具**——如果做成「preset ∩ 父表」，这个形状就做不出来。

### 5.4 过滤在什么时候发生

在**构造子 Agent 的注册作用域时**，不是在调用工具时。表里没有的工具就是不存在，模型的 schema 也是从这张表派生的。所以它叫「组合」，不叫「授权」——授权在沙箱与审批那一层。

### 5.5 和 mini 的 M12 参数有什么不同

M12 的 mini 有一个 `subagent.tools`：**父模型**在调用里给一个工具名列表，子会话取它与父表的交集。它的**形状**和 `scope.tools` 很像（都是创建时的工具面），但**作者**不同：

| | M12 的 mini | DSH |
|---|---|---|
| 谁写工具集内容 | 父模型（`tools` 参数） | 部署（preset）或父的代际 |
| 模型能选什么 | 任意工具名子集 | 白名单里的 preset id |
| 父的局部限制是否导入 | 是（∩ 父表） | 否 |
| 是授权吗 | 不是 | 不是 |

ADR-0037 的结论：**把这个作者换回部署**——M14 用 preset + 白名单替代 `subagent.tools`，并删除该参数。理由不是「模型不可信」，而是「能力面的作者应该是部署；模型只在部署给的选项里选」。

---

## 6. 权限面：沙箱、审批缝与「子级钉 `never`」

### 6.1 两条独立的轴

- **沙箱模式**回答「能碰哪儿」：`read-only` / `workspace-write` / `danger-full-access`。
- **审批策略**回答「要不要问人」：`ask` / `never`。

DSH 把两条轴捆成 **permission preset**（例如 workspace-write + ask、danger-full-access + never），但执行时各自保留自己的值。

### 6.2 审批缝

`dsh-user-approval` 是一个服务，只做机制、不做策略：

- 请求带着**发起它的 Agent**、工具名、精确的调用 id、人类可读的原因。
- 路由原则是**归属**：请求必须到达**拥有这个 Agent 的通道**；无人拥有的 Agent **失败关闭**（`unavailable`）。
- 结果只有四种：`allowed-once` / `rejected` / `cancelled` / `unavailable`；模型只能看到由结果派生的普通工具结果。
- 成功的请求落一对**只进日志、不进 transcript** 的审计事件：`approval/asked` + `approval/decided`。
- `allow_always` 刻意**没有实现**：没有授权存储、作用域与撤销之前，只提供「一次」。
- `policy: never` 在**任何应答者之前**把 ask 解析为 `rejected`。

### 6.3 子代理的审批：钉死为 `never`

subagent README 的 FAQ：

> **subagent 的审批如何路由？** 不路由：委派会把每个进程内子 agent 钉定为 `'never'`……将子 agent 的 ask 路由到父控制器**已延后**。

也就是说：

- 子级**没有**问人的通道，任何需要审批的操作都被确定性拒绝。
- 父**不能代答**——那会变成「父是模型、父批准自己的孩子」的审批逃逸，而且没有申请者身份可审计。
- 「让子代理干活」的正路不是给它审批通道，而是**部署把沙箱放宽**（Auto 预设 = full-access + ask + auto-review 应答者；子级的 ask 仍被拒，但正常写入在沙箱层就不需要 ask）。
- 子级的运行时上下文会明确告诉模型：**权限在启动时固定、不要重试被拒绝的操作、把限制写进回复让父级处理**。

### 6.4 与 mini 的对照

mini M12 的做法：子会话继承 `approval` 模式，但审批门固定 `UNAVAILABLE`；拒绝以 `DENIED_BY_APPROVAL` / `DENIED_BY_FENCE` 回到父（父能分清「没做成」与「做成了」）；子级头部带一条中文的委派声明。差异在「无人值守放在哪一轴」：DSH 放在**沙箱宽度**，mini 放在**审批模式**——因为 mini 的 `ask` 是「每次会改动都问」，字面钉 `never` 会让子代理连 full-access 下也写不了。这条代价记在 ADR-0036，等 mini 有「沙箱升级才问人」的语义再收紧。

---

## 7. 容量、深度与身份

- **容量**：`maxActiveSubagents` 默认 8，**按 subagent 树**计（本地与外部后代共享），根不占名额；耗尽在启动/冷恢复时以 `ACTIVATION_LIMIT_REACHED` 拒绝。额度不排队。
- **深度**：`maxDepth` 默认 1，深度 = 父 + 1；工具级可以显式指定，`0` 禁止委派。
- **身份**：根叫 `lead`，子级 `agent-N`（或调用方指定的名字），完整路径如 `reviewer/checker`；重名、非法名在启动前拒绝。
- **恢复**：本地子级可继续、可冷恢复；恢复时按保存的 preset 重新组装，preset 缺失/损坏则拒绝恢复。

mini M12：深度 1、每父会话 8、用会话 id 代替名字、只有 spawn（fork 见 ADR-0035）。深度 1 时「每树 8」与「每父 8」等价。

---

## 8. 结果怎么回来

DSH 的交付有两种：

- **`delivery: parent`**（默认的委派工具）：子级结束后，向父发一条 **user 角色**的完成通知，带最终答案。父如果空闲，这条通知会起一次新的模型回合；父如果忙，它排在后面。父**收不到**子的 transcript、工具输出与推理过程。
- **`delivery: caller`**（工作流等程序调用方）：不发通知，调用方直接 `await result`。

工具调用的结果本身只是 `started subagent <name>`。这一点和 mini 不同：mini 的 `subagent` 工具**同步等待**子会话结束，把最终文本作为 `tool/result` 返回。两者信息边界相同（父只拿最终结果），但并发形状不同：DSH 的父可以在子运行期间继续干活，mini 的父回合要等。

这条差异记在 DSH review 的「完成通知」一行，触发条件是「父回合需要与子代理并行推进」（Super-agent 的 Router/Worker 形状）。

---

## 9. Super-agent：委派的上一层

公开事实（二级证据）：

- 文章《Exploring Super-agent Design》（2026-10-31），配一个研究原型 `deepseek-ai/dsh-superagent-prototype`（MIT、单 commit、README 自称 "not an official DeepSeek product"）。
- 形状：**Router**（常驻主会话；文章的设计里它**可以不带 bash**、用更轻的模型）派单；每个 Ticket 一个 **Worker** 会话（强模型、全工具）；**Thread** 让后续事件直连 Worker；**Watchdog** 是进程外的定时巡检。
- 权限：Router 与 Worker **都跑 `danger-full-access`**；Worker 的隔离不在审批、不在 OS，而在**工具边界**——读取用的 ticket id 在构造工具时由宿主写进闭包，越界的读取直接拒绝。Worker 的 shell 以操作员身份运行、不经审批。

**连续性**：Super-agent 没有发明新的权限通道，它复用的还是 session / preset / tool / approval 原语；「子 ask 路由给父」在核心仍是**延后**项，原型也没有做。真正新增的是拓扑（Router/Worker/Thread/Watchdog）与**工具边界分域**。

**对 mini 的含义**：M12 的 spawn 形状是底座；将来的「Worker」等价物是「会话 + preset + 收窄的工具表」，而不是给子代理加一条父代答通道。另外 `danger-full-access` 是那个原型的默认姿态，抄拓扑时不能顺手抄这条——mini 的默认是 workspace-write + ask。

---

## 10. mini 的对照：已实现、简化、暂缓

| 行为 | mini 现状 | 结论 |
|---|---|---|
| spawn | 有（`subagent`，不 seed 父历史） | aligned |
| fork | 不做 | deferred（ADR-0035） |
| 深度 | 常量 1，`DEPTH_EXCEEDED` | aligned（没有工具级覆盖） |
| 容量 | 每父会话 8，`ACTIVATION_LIMIT_REACHED` | simplified（深度 1 下与「每树」等价） |
| 审批 | 继承模式 + 门 `UNAVAILABLE` | simplified（见 6.4） |
| 工具面 | M12 是模型参数；M14 起 preset + 白名单 | simplified → aligned |
| 委派声明 | 受保护头部一条 | aligned |
| 并发 | 同批 `parallel` ≤ 8 | aligned |
| 取消 | 段取消 → 子 `ABORTED` | 可观察行为一致，没有 dispose/drain API |
| 结果 | 工具结果同步返回最终文本 | simplified（DSH 是异步通知） |
| 名字 / preset / 子级恢复 | 没有 | deferred（触发条件见 DSH review） |

三处「语义原语」的差距（沙箱=授权本体 vs 审批=升级；工具边界 vs 工具表；审批结果词与审计）各自带触发条件，记在 `docs/verification/m12-subagent-delegation-dsh-review.md` 的「语义原语的差距」。

---

## 11. 常见误解（这次讨论里纠正过的）

1. **「用 preset 可以让模型在白名单工具里挑」** —— 不行。白名单是 **preset id** 的列表，选择粒度是整套 preset；模型不能在 preset 内部挑工具。
2. **「没设 preset 时继承父表，再选个更小的子集」** —— 不行。没 preset 时继承父的**整张表**，没有「再选子集」的入口（`subagent.tools` 已删）。
3. **「父模型决定子代理注册什么工具」** —— 不是。preset 的内容由部署写；宿主装配把它编译成子 registry；父模型只选 preset id。
4. **「`scope.tools` 是模型传的参数」** —— 不是，它是结果。内容来自 preset 或父的代际。
5. **「`never` = 自动批准」** —— 反了。`never` 是**确定性拒绝**（每次 ask 在任何应答者之前解析为 `rejected`）。
6. **「工具面窄 = 权限小」** —— 两回事。工具是能力；权限由沙箱、边界、审批决定。子代理有 bash 但沙箱 read-only，照样会被围栏拒。
7. **「子代理的审批会转给父」** —— DSH 明确**延后**，核心不做；父代答是审批逃逸。

---

## 12. 出处清单

**DSH 公开仓库**（固定 commit `fcc0ad46`）：

- `packages/subagent/subagent/README.zh.md` —— 服务 seam、容量、命名、恢复、完成通知与**字面**的 `subagent:delegation` 声明。
- `packages/subagent/subagent-spawn-in-process/README.zh.md` —— 进程内后端、**不导入父方局部工具限制**。
- `packages/subagent/tool-subagent/README.zh.md` —— 工具 schema、`agentPreset` / `allowedAgentPresets`、`maxDepth`、模型选择。
- `.agents/notes/implemented/feature/2026-07-06-approval-seam.zh.md` —— 审批缝、结果词、审计对、`never`、子代理钉定。
- `packages/interaction/permission-presets/README.zh.md` —— 权限预设（沙箱 + 审批）。

**Super-agent**：

- 《Exploring Super-agent Design》（DeepSeek，2026-10-31，公众号文章）。
- `deepseek-ai/dsh-superagent-prototype`（研究原型；第三方拆解见 `neoneye/agent-memory-atlas` 的 `dsh-superagent` 页）。

**本仓库**：

- `docs/reference/subagents.md` —— mini 的落成形状与实现对照。
- `docs/verification/m12-subagent-delegation-dsh-review.md` —— 逐项 parity、语义原语差距与触发条件。
- `openspec/specs/subagent-delegation/spec.md` —— 主规格。
- `docs/adr/0035`、`0036`、`0037` —— fork 范围、M12 边界、preset 与 `tools` 的定案。
