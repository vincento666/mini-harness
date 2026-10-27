# 记忆：DSH 对照与 MEM1 / MEM2 的最小设计

**定位**：规划底稿，不是规格。MEM1 开工前由人审；对外行为以 change 的 delta spec 为准。

## 1. DSH 是什么形状

DSH 的参考文档里**没有独立的 memory 子系统**。它的「会话记忆」是：

- `session` / `resume`：会话日志与恢复；
- `CLAUDE.md` 类**约定文件**：项目/用户级的事实与偏好，启动时读入；
- `compaction`：长会话的摘要与遮蔽。

`docs/dsh-reference/DSH运行时设计说明.html` 的「会话记忆」一行写的就是这三样。DSH 的扩展轴（`e06`）有 skills / commands / schedule / terminal，但**没有 memory 轴**；所以「定时总结记忆」不是 DSH 的既有实现，是 mini 如果要做的扩展。

## 2. mini 的约束

- 不变量 A：日志唯一真源，折叠从日志前缀派生。记忆如果进受保护头部，**它必须在日志里有一条可重放的记录**，否则 `replay` 会随记忆文件变化而失配。
- 记忆文件可能在工作区外（用户级），不能靠 `write`/`edit` 的围栏；要一个专用的 `memory` 工具与边界。
- 记忆写入是持久副作用，和 `write` 一样要 CAS、审批（`ask` 档位）与边界。
- 预算：记忆不能无限长；加载时要有 token 预算与截断 marker。

## 3. MEM1 基础记忆（最小）

**两个 scope**：

| scope | 位置 | 优先级 |
|---|---|---|
| 项目 | `<workspace>/MEMORY.md` | 高 |
| 用户 | `$MINIHNS_HOME/MEMORY.md`（默认 `~/.mini-harness/`） | 低 |

**组件形状**：MEM1 直接实现 E2 的 `MemoryStore` 接口（`load` / `write` / `search` 可选），由 `SessionComponents.memory` 注入；`turn_loop` 不碰文件路径。这样 E2 不用二次抽取，R1/R2 可以在不改内核的情况下换记忆策略。

**启动加载**：`session/start` 之后、第一次 `context/assembled` 之前，写一条 `memory/loaded`：

```json
{"scope": "project", "path": "...", "hash": "sha256:...", "content": "...", "truncated": false}
```

`content` 是加载进头部的正文；超预算时截断并置 `truncated: true`。`replay` 用这条记录重建头部，**不读当前文件**。两个 scope 各一条，按项目 → 用户的顺序进头部。

**`memory` 工具**：`read` / `append` / `replace`，参数带 `scope` 与 `content`（或 `old_string` / `new_string`）；写是 `mutates=True`，走 CAS、边界与 approval；写成功后日志里是普通的 `tool/call` + `tool/result`，必要时再写一条 `memory/written`（或只靠 tool 结果，MEM1 design 定）。

**短记忆**：当前 session 的日志 + 压缩摘要；不另造「短期记忆文件」。

**完成判据**：会话 A 写的事实，会话 B 启动后能在受保护头部看到；`replay` 逐点相等；超预算有 marker；`memory` 写被 CAS / 边界 / 审批约束。

**不做**：向量库、embedding 检索、每轮自动抽取、跨用户记忆、静默写入。

## 4. MEM2 定时巩固（壳后）

**手动命令先跑稳**：`memory consolidate`（host 命令或 CLI 子命令）读「上次巩固以来」的会话日志，调模型生成摘要（`model/request` 带 `purpose: memory`），写 `memory/summary` 并把结论并进 `MEMORY.md`；一次巩固是普通会话，可重放。

**定时器住在 host**：一个 interval 触发器，不是内核 cron；默认关闭，显式开启；关掉时零副作用。DSH 的 `schedule` 扩展轴有 6 个方法，mini 只做「按 interval 触发一次巩固」，不做完整调度器。

**完成判据**：手动跑一次把两个会话的结论并进长期记忆；同一份日志重放得到同一条 `memory/summary`；关掉时零副作用。

**不做**：每轮自动总结、跨用户、向量检索、内核内置 cron。

## 5. 与斜杠命令的关系

MEM1 的壳面命令（M14 之后）：

- `/memory`：看当前加载了哪些 scope、各自多少 token、最近一次写入；
- `/remember <text>`：写入项目 memory（走 `memory` 工具，日志有记录）；
- `/forget <text>`：从 memory 删除/替换（同样走工具与审批）。

这些命令**不绕过内核**：它们调用同一个 `memory` 工具，CLI 与 host 走同一份命令面（见 `skills-and-commands.md`）。

## 6. 开放问题

- `memory/loaded` 的 content 要不要完整落盘？太长时落 hash + 截断内容，`replay` 用同一条记录，不再读文件。
- 项目 memory 与用户 memory 同名事实冲突时谁赢？先按「项目 > 用户」，在 MEM1 design 写死。
- `memory` 写要不要默认审批？先按 `ask` 档位要审批；无人值守时只能 `auto`，但要有 M15a。
- 记忆是否进压缩的遮蔽范围？MEM1 先不遮蔽（头部受保护），预算超了截断；M11 的投影三态再议。
