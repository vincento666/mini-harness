# 里程碑、宿主轨与评测轨

每个里程碑 = 一个 OpenSpec change（propose → 人审 → apply → `code-review` 两轴 → 四项收尾 → sync/archive → 合入 `main`）。**完成判据有三半**：mock 四道门禁 / 真实端点跑判据 / UAT 人跑；三半都过才算验收（ADR-0024、ADR-0025）。下表每行的「完成判据」是验收口径，不是内容描述。

**执行顺序（2026-10-26 修订）**

- **P0（不入里程碑）**：合 `fix-post-compaction-budget-reading`——UAT 表填完才合（ADR-0025）。
- **第二阶段**：**H1 宿主会话 API** → **H2 流式与事件回显**（2026-10-26 人裁决：优先于 M10）→ **M10 工具管线 / 并发 / 上下文经济** → **M11 存储与恢复** → **M12 委派** → **M13 目标** → **M14 技能 / 斜杠命令 / 渐进式披露** → **M14a 工作区契约** → **M14b 上下文经济与计量** → **M14c 个人助理 UX 工具** → **M15a 进程收容** → **MEM1 基础记忆**。
- **支撑轨**：**E1 评测与观测**（并行，不阻塞里程碑）；**E2 组件接缝**（M 核心完成后、R3/G 之前；**不是壳前置**）。
- **服务化分支（G 轨）**：`personal-baseline-v1` 之后；G0 → G6；不属于 M 轨，也不是加壳。
- **第三阶段（加壳）**：在 H1 / H2 / M11 / M14 / MEM1 / M15a 完成、宿主协议冻结之后规划；无人值守入口条件见下。
- **壳后**：**M15b 文件写拒绝**、**MEM2 定时巩固**、M13 目标轮次可后置。

H1 / H2 是新增的宿主轨，不占用 M10–M15 的决策编号；M 编号仍是决策编号、不是执行顺序。**H2 固定优先于 M10**，不再互换：流式是壳的第一体验，先做。

**分层术语**：K（内核层）/ R（运行时层）/ S（外壳）见 `GLOSSARY.md`；M 轨不按 DSH 的 L0–L13 编号，层号只说明职责（L3 = K；L2、L4–L10 = R；L1 = Artifact；L0、L11–L13 = Meta）。

## 已完成（M1–M9）

| ID | change | 落地 | 证据 |
|---|---|---|---|
| M1 ✅ | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `run` / `replay` | tag `m1`；[proposal](openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/proposal.md) |
| M2 ✅ | `m2-file-tools-and-fences` | 五个文件工具 + 工作区边界 + 写前必读 CAS + 两轴围栏 | tag `m2`；[proposal](openspec/changes/archive/2026-10-18-m2-file-tools-and-fences/proposal.md) |
| M4 ✅ | `m4-real-provider` | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | tag `m4`；[proposal](openspec/changes/archive/2026-10-18-m4-real-provider/proposal.md) |
| M3 ✅ | `m3-bash-concurrency-timeout` | `bash` + 只读并发 + 超时/取消 + 平台适配层 + CI 矩阵 | tag `m3`；[proposal](openspec/changes/archive/2026-10-19-m3-bash-concurrency-timeout/proposal.md) |
| M8 ✅ | `m8-runtime-semantics-alignment` | 回合级取消 + 结果在产生时落盘 + 读方闭合 | tag `m8`；[proposal](openspec/changes/archive/2026-10-20-m8-runtime-semantics-alignment/proposal.md) |
| M5 ✅ | `m5-context-budget-compaction` | 窗口预算 + 触发线 + 摘要 + 遮蔽 + 溢出结果 | tag `m5`；[proposal](openspec/changes/archive/2026-10-21-m5-context-budget-compaction/proposal.md) |
| M9 ✅ | `m9-assembly-and-config-layering` | `mini.config.toml` + 三层层叠 + 工具表从装配来 + `ProviderEndpoint` | tag `m9`；[proposal](openspec/changes/archive/2026-10-21-m9-assembly-and-config-layering/proposal.md) |
| M6 ✅ | `m6-chat-repl` | `minihns chat` + 段边界 + 两级取消 | tag `m6`；[proposal](openspec/changes/archive/2026-10-22-m6-chat-repl/proposal.md) |
| M7 ✅ | `m7-serve-http-sse` | `minihns serve --http` + SSE + `seq` 断线续读 | tag `m7`；[proposal](openspec/changes/archive/2026-10-22-m7-serve-http-sse/proposal.md) |

### 2026-10-23 至 2026-10-26 的修复轮

| change | 结果 | 状态 |
|---|---|---|
| `fix-compaction-and-context-overflow` | 摘要请求只装被遮蔽那一段；溢出短语表；工具往返整对丢弃 | 已归档 [2026-10-23](openspec/changes/archive/2026-10-23-fix-compaction-and-context-overflow/proposal.md) |
| `fix-chat-screen-feedback` | 屏幕反馈八条；UAT 升第五道门禁（ADR-0025） | 已归档 [2026-10-25](openspec/changes/archive/2026-10-25-fix-chat-screen-feedback/proposal.md) |
| `add-platform-facts-to-protected-header` | 平台事实与平台建议进受保护头部（ADR-0029 / 0030） | 已归档 [2026-10-25](openspec/changes/archive/2026-10-25-add-platform-facts-to-protected-header/proposal.md) |
| `fix-small-window-compaction-dead-zone` | 溢出判据换成压力预算 `W − O`（ADR-0026） | 已归档 [2026-10-26](openspec/changes/archive/2026-10-26-fix-small-window-compaction-dead-zone/proposal.md) |
| `add-key-driven-default-provider` | provider 名字是端点预设名（ADR-0027） | 已归档 [2026-10-26](openspec/changes/archive/2026-10-26-add-key-driven-default-provider/proposal.md) |
| `fix-post-compaction-budget-reading` | 遮蔽之后的读数不再被遮蔽之前那条 `usage` 钉住 | **进行中**：分支 `change/fix-post-compaction-budget-reading`，20 个 task 未勾，UAT 未跑 |

## 第二阶段（待办）

### H1 宿主会话 API（宿主轨）

- **change**：`h1-host-session-api`
- **状态**：✅ **2026-10-27 已归档**（`openspec/changes/archive/2026-10-27-h1-host-session-api`）：40/40 task；四道门禁 `492 passed / 8 skipped`、覆盖率 95%；真实 deepseek 端点、UAT（agent 代跑经用户确认）、变异五条全杀、Learning Gate 完成。主规格新建 `host-api`，`cli` / `fences` delta 已 sync；**合并到 `main` 仍待人批**。
- **层**：宿主（组合层的运行时那一半）
- **内容**：新增 `minihns host --http`——常驻、多会话、服务比会话活得久。装配从 `cli/main.py::_prepare_or_fail` 抽成 `session/assembly.py::assemble(...)`；端点 `POST /sessions`、`POST /sessions/{id}/messages`、`POST /sessions/{id}/cancel`、`POST /sessions/{id}/approvals/{tool_call_id}`、`GET /sessions`、`GET /sessions/{id}`、`DELETE /sessions/{id}`、`GET /sessions/{id}/events`（`snapshot` 帧 + `seq` 游标）；Bearer token 鉴权；session id 校验；会话上限；可插拔 approval 门（stdin 不再是唯一实现）；事件回显。
- **完成判据**：一个黑盒 HTTP 客户端开会话 → 发两句话（第二句在段进行中排队，202）→ 批准一次写 → 取消一回合 → 带游标重连，帧与日志逐字段相等；无 token 401；`../` 之类的 session id 是 400；超过会话上限是 429；`session/start.entry` 是 `host`；`serve` 的 one-shot 行为不变。
- **依赖**：M7、M9。不依赖 M10。
- **明确不做**：WebSocket mux、多租户、TLS 终止、公网暴露、UI 实现、浏览器 `EventSource` 的 query token（H1 用 header + `fetch` 流；一次性 ticket 归壳阶段）。

### H2 流式与事件回显（宿主轨）

- **change**：`h2-streaming-and-event-echo`
- **状态**：✅ **2026-10-28 已合入并归档**（`openspec/changes/archive/2026-10-28-h2-streaming-and-event-echo`）：真实端点 S1–S4、UAT S1–S5（人跑）、变异四条、Learning Gate 全过；主规格 `provider` / `host-api` 已 sync；`main` 合并提交 `46ce2d2`。
- **层**：模型 + 宿主
- **内容**：provider 走 `stream: true`（OpenAI 兼容 SSE）；`model/delta` 是**宿主流上的 ephemeral 帧**，不落日志；最终 `model/response` 仍是唯一 durable 真相；只有首 delta 之前才允许重试；流式 `tool_calls` 的拼装；mock 也能发 delta；`GET /events` 的 snapshot、断线续读与协议版本。设计底稿在 `docs/reference/host-streaming.md`。
- **完成判据**：首帧在 1 s 内（真端点）；拼接 delta 等于最终 `content`；工具调用流式拼装正确；断线重连从 durable `seq` 续读、最终回复不重复；`replay` 与不流式逐点相等；真实端点一次。
- **依赖**：H1；ADR-0006 修订。
- **明确不做**：多模型路由、逐字帧落日志、WebSocket、服务端事件 allowlist / UI 投影（先按日志镜像 + 客户端过滤；触发条件与最小 MVP 记在 ADR-0002「UI 事件 allowlist / 服务端投影（暂缓）」）。

### M10 工具管线 / 并发 / 上下文经济

- **change**：`m10-tool-pipeline-and-concurrency`
- **层**：能力 + 围栏 + 性能
- **内容**：**第一个切片：压缩参数可配置**——`compaction_threshold_ratio` / `compaction_headroom_tokens` / `compaction_retain_ratio` / `compaction_retain_tokens`（对应 DSH `dsh-compaction-basic` 的 `thresholdRatio` / `headroomTokens` / `retainRatio` / `retainTokens`；默认值保持现状，有效值进 `session/start`、replay 取回）。然后六段管线（`pre-execute → guard → execute → post-execute → finalizeContent → tools/result`）；`CommandRunner` 缝（win32 / posix 两个 adapter）；`FenceCode.SANDBOX_UNAVAILABLE`；工具并发类别（`parallel` / `exclusive`）+ 上限 + mutation barrier；结果在产生时落盘；单条结果的输出预算与 spill 文件；`read` 的字节上限（行数已有）、`grep` / `glob` 的字节上限；前缀复用。并发与上下文的设计底稿在 `docs/reference/tool-concurrency-and-context-economy.md`。
- **完成判据**：压缩参数可配且默认行为不变、`session/start` 记录、replay 用记录值逐点相等；注入「runner 不可用」的桩 → `error/fence(code: SANDBOX_UNAVAILABLE)` + 退出码 3；并行只读批次的 wall-clock 小于串行基线（E1 记录）；同一时刻在跑 ≤ 8；改动调用两侧的 barrier 成立；一条超大 `read` / `bash` 结果被截断、带固定 marker + spill，折叠读到的一致；工具体观察派生信号后自己停；真实端点一次。
- **依赖**：M3、M8。H1 可选。
- **明确不做**：OS 级沙箱（M15）、每工具可配并发数、跨会话结果缓存、PTC 工具面塌缩。

### M11 存储、恢复与投影缓存

- **change**：`m11-storage-resume-and-projection-cache`
- **层**：数据 + 工件
- **内容**：`EventLog.open` 读最后 `seq`；`--resume`；`schema_version` 相邻迁移；session index（重启后 `GET /sessions` 能列已结束会话）；折叠缓存（日志领先、缓存跟随）；投影三态（进上下文 / 被遮蔽 / 只在日志）；多次压缩的遮蔽范围重叠规则；硬杀后的读方修复。
- **完成判据**：resume 后续写 `seq` 正确、`replay` 逐点相等；硬杀日志被 resume 补出闭合；旧 schema 迁移；缓存失效正确；`GET /sessions` 重启后能列已结束会话。
- **依赖**：M5、M8、H1。
- **明确不做**：fork（ADR-0035：暂不做）、跨进程共享缓存。

### M12 委派（子代理）

- **change**：`m12-subagent-delegation`
- **层**：委派
- **内容**：`subagent` 工具（spawn 形状，fork 暂不做，ADR-0035）；独立子 session、独立日志；父日志只有 `tool/call` + `tool/result`；子 session 继承档位与边界、**不继承 approval 放行**（子会话问人一律 `UNAVAILABLE`）；`maxDepth` 默认 1（深度 = 父 + 1，写进子 `session/start`）；**每个父会话 `maxActiveSubagents` 默认 8**；容量耗尽与深度超限都是结果词（`ACTIVATION_LIMIT_REACHED` / `DEPTH_EXCEEDED`），不是异常。底稿在 `docs/reference/subagents.md`。
- **并发（强调）**：`subagent` 工具是 `parallel` 类别——同一批声明多个 `subagent` 时并发跑，结果按完成顺序落盘；父上下文只装子任务的最终结果，不装子会话的过程；子会话内部仍受每会话 8 个工具并发与自己的 `max_turns` 约束；host 的 `GET /sessions` 要能看出父子关系（M12 加字段）。
- **完成判据**：**seam ⑦**——子代理写自己的日志；子代理问人得到 `APPROVAL_UNAVAILABLE`；深度超限与容量耗尽都是结果词；同一批两个 `subagent` 真并发（wall-clock 小于串行）；父日志里只有两条 `tool/result`，没有子会话的 `model/*`。
- **依赖**：M10；H1 可选（子代理在 CLI 里也能跑）。M12 已在 M11 之后、M14 之前；流式已定优先，不再压过 H2。

### M13 目标轮次

- **change**：`m13-goal-rounds`
- **层**：委派
- **内容**：持久 goal 对象 + 轮次续跑 + 轮次上限 + `blocked` 需同一阻碍持续三轮。
- **完成判据**：**seam ⑦**——小上限下自动续跑 N 轮；同一阻碍持续三轮落 `blocked`、两轮不落。
- **依赖**：M12。可与 M12 合并执行，编号保留两个决策。

### M14 技能、斜杠命令与渐进式披露

- **change**：`m14-skills-and-commands`
- **层**：扩展
- **内容**：`SKILL.md` 目录发现（照 DSH 的六级优先级根：项目 / 项目共享 / 自定义 / 宿主 / 通用代理家目录 / 内置，同名高优先）；**清单注入 + 正文按需加载**——`session/start.payload.skills` 只放 `{name, description, rank, path}`，受保护头部只放紧凑清单，正文由 `skill` 工具按需读；**同一份命令面**给 CLI 与其它壳：CLI `chat` 的 `/skills`、`/skill <name>`，host 的 `GET /commands` 与 `POST /sessions/{id}/commands`；命令调用必须落一条可重放的事件（`command/invoked` 或 `user/message` 的结构化命令，M14 design 定）；外部触发塌成一条可重放的会话事件。底稿在 `docs/reference/skills-and-commands.md`。
- **完成判据**：仓库内一个 skill 被列出并加载；同一 skill 在两级根里只出现一次且高优先胜出；正文不在 `session/start` 的清单里、只在按需加载后才进上下文；CLI 与 host 对同一 `/skill` 得到同一份正文与同一条日志；一条外部触发在日志里是一条事件、`replay` 仍相等。
- **明确不做**：插件容器与热更新（ADR-0035）、MCP、hooks 的完整 allowlist、shell 自己发明一套绕过内核的命令。

### M14 之后的三小步（M14a–c，非核心、个人助理向）

三小步各自一个 change；**M14a 先做**（`ContextPolicy` 的契约/头部要它），M14b / M14c 可按壳的需求调序。它们都不是接壳硬前置，但缺了个人助理会明显“不像”。

- **M14a 工作区契约（`m14a-workspace-contract`）**：项目 `AGENTS.md` + 用户 `USER.md`（可选 persona/SOUL）按字节预算注入受保护头部；记录 scope / hash / 截断，不写绝对路径与密钥；**只读加载，不自动写**。判据：两份契约都在头部可见、超预算有 marker、`replay` 逐点相等；与 MEM1 的 `MEMORY.md` 分开（契约 vs 记忆）。
- **M14b 上下文经济与计量（`m14b-context-economy-and-metering`）**：单条结果剪枝（头/尾 + 阈值）、spill 的读回与回收、每会话/每回合 token 计量与成本估算、E1 报告里的上下文/成本列；M10 的“输出预算 + spill”是底座，M14b 是收尾。判据：超大结果被剪短且 spill 可读回、token 计量与 provider usage 对得上、E1 能出报告。
- **M14c 个人助理 UX 工具（`m14c-personal-assistant-tools`）**：`todo` / `plan`、`ask_user`（普通提问，不只是审批）、`present`（把产物交给壳）；CLI 的 `/todo` / `/plan` 与 host 的同一命令面。判据：多步任务会用 todo、`ask_user` 的答案作为结果进日志、`present` 产出一个可打开的产物、`replay` 相等。
- **明确不做**：自动写 workspace 契约、向量库记忆、完整 plan-mode 状态机、HMR/插件市场。

### M15 围栏增厚（M15a / M15b）

- **change**：`m15a-process-containment` / `m15b-os-write-denial`（可拆成两个 change，M15 编号保留）
- **层**：围栏增厚
- **M15a 进程收容（便宜，壳前）**：Windows job object + `KILL_ON_JOB_CLOSE`；POSIX 进程组 / 父死子收；服务退出时整棵进程树收干净；坐在 M10 的 `CommandRunner` 缝上。完成判据：host 被硬杀时子进程不残留；`bash` 超时/取消后进程树为空。
- **M15b 文件写拒绝（贵，可壳后）**：Windows ACL / Linux landlock / bwrap；一条命令试图写工作区外的文件时被 OS 拒；adapter 仍坐在 M10 那条缝上、工具体不改。
- **依赖**：M10。M15a 是**无人值守壳的硬前置**；M15b 在引入不可信 skills/MCP 或绑非 loopback 时必须提前。威胁模型在 `docs/reference/host-security-threat-model.md`。

### MEM1 基础记忆（最小）

- **change**：`mem1-basic-memory`
- **层**：扩展 / 数据
- **参照**：DSH 没有独立的 memory 子系统；它的「会话记忆」是 session / resume + `CLAUDE.md` 类约定文件 + 压缩摘要（`docs/dsh-reference/DSH运行时设计说明.html` 的「会话记忆」一行）。mini 照这个形状，不造向量库。
- **内容**：项目 `MEMORY.md`（工作区根）+ 用户 `$MINIHNS_HOME/MEMORY.md`；启动时按「项目 > 用户」加载，受 token 预算；写一条 `memory/loaded`（scope / path / hash / 截断后的 content），让 `replay` 能复现；`memory` 工具（read / append / replace，带 CAS 与边界）；memory 写是 mutating，`ask` 档位要审批。短期记忆就是当前 session 日志 + 压缩，不另造一套。底稿在 `docs/reference/memory.md`。
- **完成判据**：会话 A 写的事实，会话 B 启动后能在受保护头部看到；`replay` 逐点相等；超预算有截断 marker；`memory` 写被 CAS / 边界 / 审批约束。
- **明确不做**：向量库 / embedding 检索、每轮自动抽取、跨用户记忆、静默写入。

### MEM2 定时巩固（壳后）

- **change**：`mem2-memory-consolidation`
- **层**：宿主 / 扩展
- **内容**：host / CLI 的 `memory consolidate` 命令：读上次巩固以来的会话日志，调模型生成摘要（`purpose: memory`），写 `memory/summary` 与 `MEMORY.md`；**默认关闭**、需显式开启；定时器住在 host，不住内核；一次巩固是普通会话，可重放。
- **完成判据**：手动跑一次把两个会话的结论并进长期记忆；同一份日志重放得到同一条 `memory/summary`；关掉时零副作用。
- **明确不做**：每轮自动总结、跨用户、向量检索、内核内置 cron。

**记忆的顺序**：MEM1 在壳前（壳要用户/项目记忆）；MEM2 在壳后（先把「手动巩固」跑稳，再谈定时）。「定时总结」不是 DSH 的既有实现，是 mini 的扩展，别把它写成「照抄 DSH」。

## 第三阶段入口条件（无人值守）

壳要跑无人值守任务时，**不能只靠 `approval: ask`**；入口条件写死：

- **必需**：H1（宿主）、H2（流式）、M11（resume）、M14（技能/命令）、MEM1（记忆）、**M15a（进程收容）** 全部完成。
- **策略**：`approval: auto` 必须服务器启动时显式给 `--allow-auto-approval`；sandbox 只允许 `read-only` / `workspace-write`；**无人值守 MUST NOT 使用 `danger-full-access`**；每个任务给 `max_turns` / 窗口 / 时间的上限；host 退出时取消并收干净所有段与子进程。
- **审计**：所有 `tool/call` / `tool/result` / 审批 / `session/end` 都在日志里；无人值守会话要能事后 replay。
- **建议**：引入不可信 skills / MCP / 外部工具，或 host 绑非 loopback 时，把 **M15b（文件写拒绝）** 也提前到壳前。

## E1 评测与观测（支撑轨）

**定位**：配套能力，不是核心运行时，**不进四道门禁、不阻塞里程碑、不作为归档条件**。它回答的是「这一版是不是更快、更省、更稳」，不是「功能对不对」（功能对不对由 seam 判据与三半完成判据回答）。

- **落点**：`scripts/eval/`（runner + 任务集 + 报告），不新增测试缝；判据仍住在七个 seam。
- **任务集（最小三件）**：① 单文件 TODO 修完并跑测试；② 读多文件后回答一个跨文件问题；③ 一次小重构（多文件 edit + 一次 `bash` 测试）。
- **指标**：任务成功率、回合数、工具调用数、输入/输出 token、峰值上下文、压缩次数、剪枝/截断省下的字节、wall-clock、最大并发数、审批次数、首 token 延迟（H2 之后）、`replay` 是否逐点相等。
- **两种模式**：mock（确定性、进日常）；真实端点（按需，人跑，不进 CI）。
- **产物**：`docs/verification/eval/<date>/report.md` + `report.json`；模板在 `scripts/eval/README.md`。
- **明确不做**：公开榜单、CI 门禁、按模型排名、自动调参。

## 安全基线（H1 起生效）

- **绑定**：默认 `127.0.0.1`；`0.0.0.0` 必须显式给 `--host`，且 token 仍然必需。公网暴露不是目标。
- **鉴权**：所有写端点与 `GET /sessions*` / `GET /sessions/{id}/events` 都要 `Authorization: Bearer <token>`；token 从 `MINIHNS_HOST_TOKEN` 读（最小 32 字符），缺失退出码 2、不建日志。`GET /health` 可以免鉴权，只回协议版本与会话数。
- **来源**：浏览器同源或 `Origin: null`（Electron `file://`）放行；其它 `Origin` 403。`EventSource` 不能带 header，H1 的 UI 用 `fetch` 流；一次性 ticket 归壳阶段。
- **会话身份**：`session_id` 只接受 `^[0-9a-f]{32}$`；日志路径由 id 派生，不接受客户端给路径。
- **审批**：写操作默认 `ask`；`auto` 只能在服务器启动时显式配置；审批超时（默认 300 s）塌成 `APPROVAL_UNAVAILABLE`；子代理不继承放行。
- **密钥**：只从环境变量读；日志只记变量名；错误 detail 不回显 key；`session/start` 不写密钥值。
- **围栏**：工作区边界 + 写前必读 CAS 继续生效；`danger-full-access` 需要服务器启动时显式允许；OS 级强制在 M15。
- **资源**：同时在跑的会话上限（默认 4）；单会话同时在跑的工具 ≤ 8；慢 SSE 读者不阻塞内核；服务退出时取消所有段并写 `session/end`。

## E2 组件接缝（Component Seams）

**定位**：支撑轨 / 架构，不是新功能；M 轨核心之后、R3（模块级 harness 进化）与 G 轨（多用户/客服）之前。**不是接壳前置**。

- **目标**：把核心能力抽成可寻址、可版本化、可在**会话之间**替换的组件；支持架构优化、生产 A/B/回滚、以及模块级 RSI 的组件变异与归因。
- **首批组件**：`Provider`、`ApprovalGate`、`ToolPolicy`、`ContextPolicy`、`CompactionPolicy`、`FailurePolicy`、`MemoryStore`、`SkillCatalog`/`CommandRegistry`、`SubagentPolicy`、`Verifier`、`CommandRunner`。其中 **`MemoryStore` 在 MEM1 里直接按组件接口生出来**（greenfield，不做二次抽取），因为 R1/R2 都要换记忆策略。
- **边界**：**不做 HMR**、不做插件市场、不做远程代码加载、不做多租户/多 worker、不做通用 DI/事件总线、不重写 `turn_loop.py`、不改内核语义；日志只多 `session/start.payload.components`。
- **离线热插拔**：会话边界换组件版本（进程可继续、运行中会话不变）；不是运行中会话内替换。
- **验收**：默认组合行为不变；测试里换 fake `ContextPolicy`/`CompactionPolicy` 不改 `turn_loop.py`；同版本 replay 逐点相等、跨版本显式；E1 能做 A/B 与归因；组件异常不崩 host。
- **进入条件**：H1/H2/M10/M11/M14/**M14a**/MEM1 完成、E1 有 held-out 基线；M12/M13/M14b/M14c 可选。
- **明确不做**：E2 本身不做 RSI 实验；R1–R4 是消费者。
- 规划口径：[docs/reference/e2-component-seams.md](docs/reference/e2-component-seams.md)。OpenSpec change 等 M 核心完成后再 propose。

## G 轨（服务化，个人基线之后）

**定位**：多用户 / 客服 / 连接器的服务化运行时；**只做智能客服机器人的核心能力 + 基础接口**。转人工、会话队列、质检、SLA 管理、PII 全治理由**现有客服平台**负责，mini 不复制。

- **G0 服务运行时**：多 worker、持久队列、lease/affinity、共享 session store、背压/重试/幂等/优雅 drain。
- **G1 Bot API / 平台适配**：入站/出站、`tenant_id`/`user_id`/`conversation_id` 映射、鉴权、幂等、handoff 信号、超时契约；不做 routing 引擎。
- **G2 Jobs / Schedule**：持久 job、cron/interval/heartbeat、standing orders、重试/死信/取消。
- **G3 Connectors**：连接器注册表 + web/browser、MCP resources、业务 API 适配器。
- **G4 租户 / 记忆**：per-tenant/user session、memory、quota、数据边界、保留/删除。
- **G5 Ops**：audit、metrics、health、backup；OTel/Prometheus 可选、telemetry opt-in。
- **G6 智能客服核心**：RAG/FAQ、多轮、工具、记忆、guardrails、置信度/兜底；不含队列/质检/转人工。
- **不做账（记着，不排期）**：PTC 工具面塌缩、model fallback、model/agent routing、转人工/队列/质检、SLA 管理、PII 全治理、plugin manager/HMR、完整 workflowEngine/teams。
- **SLA / PII 的最小面**：SLA 管理不做，但延迟/超时/降级契约要做；PII 全治理不做，但日志不泄 PII、最小脱敏、可删除要做。
- 口径：[docs/reference/g-track-service-runtime.md](docs/reference/g-track-service-runtime.md)。

## 沙箱与子代理：现在讨论什么，什么时候做

两者都**不是 H1 的实现范围**；H1 的四份工件已审，spec 不再改。现在要定的是**威胁模型、预留缝与触发条件**，不是把 M15/M12 塞进 H1。

| | 现在必须定 | 不必现在做 | 提前的触发条件 |
|---|---|---|---|
| 沙箱 | H1 的威胁模型：host 写端点 + token + loopback；薄围栏不是安全边界；`danger-full-access` / `auto` 的显式允许 | ACL / landlock / 跨平台沙箱测试 | ① host 绑非 loopback；② 壳跑无人值守/长任务；③ 引入不可信 skills/MCP/外部工具；④ 多人使用 |
| 子代理 | H1 的会话注册表、每会话 gate/queue 能容纳子会话；M12 的 `parent_session_id` / `depth` / `maxActiveSubagents` | `subagent` 工具、子日志、目标轮次 | ① 主用例是并行研究/长任务；② 上下文成本是瓶颈；③ UI 要任务树 |

**沙箱的层次**（从便宜到贵）：

1. 路径边界 + CAS + 审批（现在就有；防「模型不小心」，不防恶意进程，ADR-0003）。
2. 进程收容（Windows job object + `KILL_ON_JOB_CLOSE`、POSIX 进程组；防孤儿进程，便宜）。
3. OS 文件写拒绝（Windows ACL / Linux landlock / bwrap；防恶意写入，贵，M15）。
4. 网络隔离（不在 MVP；host 只绑 loopback 是它的替身）。

结论：**H1 的 loopback + token + 逐次审批 + 路径边界足够个人本地壳 v1**；如果要跑无人值守或不可信内容，把「进程收容」在壳前做掉，把「OS 文件写拒绝」提前到壳之前或与壳同期。M15 可拆成 **M15a 进程收容 / M15b 文件写拒绝**。威胁模型的底稿在 `docs/reference/host-security-threat-model.md`。

**子代理的预留缝**：H1 的 `SessionHandle` 已经是「一个会话一个 env / gate / queue / cancel」，注册表是 `dict[session_id, SessionHandle]`；M12 只需要在 `session/start.payload` 加 `parent_session_id` 与 `depth`、给子会话一个 `entry=subagent`、把子会话计入会话上限、并让子会话的 approval 门返回 `UNAVAILABLE`。H1 不预写这些字段（会改已审的 spec），只保证注册表不是单例、gate/queue 不假设「一个进程一个会话」。

结论：**不需要在 H1 实现子代理；M12 在 M11 之后、M14 之前即可**。流式已定优先（H2），不再把 M12 压到 H2 之前；但要把「同批 `subagent` 真并发」写进 M12 的判据。

## 性能与上下文经济

**延迟**（并发）与**上下文**（token）是两件事，分开量、分开优化。

- **并发**：只读/网络类工具 `parallel`，会改动/独占类 `exclusive`；`exclusive` 是 barrier——它之前的调用先完成、它之后的调用等它完成；只读最多 8 个同时在跑；结果按完成顺序落盘。当前取舍是「保守但正确」，要在 E1 里量并行度与 wall-clock，再决定要不要更细的调度。
- **上下文**：单条工具结果的输出预算（`read` 的行数已有、补字节上限、`bash` 的 16 KB、`grep`/`glob` 的字节上限）+ spill 文件；压缩（整段遮蔽）与单条剪枝（M10）分开；折叠缓存与投影三态在 M11；`estimate_tokens` 的 `/4` 偏差是成文取舍（ADR-0016），不靠它做终止决策。
- **不去做**：跨会话结果缓存、推测执行、PTC 工具面塌缩、按内容自动调 tokenizer（要选型，不是修补）。

## DSH 对齐（宿主与流式）

- **durable / ephemeral 分开**：DSH 的 `session/follow` 是「opening snapshot + gap-free durable 帧 + 可选 cursorless assistant-stream 帧」；mini 的 `GET /events` 照 durable 那一半（`seq` 游标、帧与日志逐字段相等），H2 的 `model/delta` 照 assistant-stream 的 ephemeral 那一半（不落日志、断线不补）。
- **事件回显**：DSH 的 `$events` 是另一条 27 条 allowlist 的流；mini 不复制 allowlist，UI 的「事件回显」就是日志的逐行镜像——同一条事实不制造第二个真源。
- **回程**：DSH 的 `$events/result` 是 unary HTTP RPC；mini 的 H1 写端点也是 unary POST，SSE 与 `seq` 游标都不换（ADR-0021、ADR-0031）。
- **技能与命令**：DSH 的扩展三轴（skills / commands / schedule）与六级技能根（100 项目 → 600 内置）照；mini 先落 4 级根，清单注入、正文按需（`docs/reference/skills-and-commands.md`）。**记忆**：DSH 没有独立 memory 子系统，mini 照「约定文件 + session/resume + 压缩」，定时巩固是 mini 的扩展（`docs/reference/memory.md`）。
- **取舍**：DSH 的 WebSocket multiplex 不做；多模型路由不做；PTC 不做。逐条对照见 `docs/stage-map.md` 与 `docs/dsh-alignment.md`。

## 完成判据（只写一次）

**mock 那一半**是四道门禁（测试 / 覆盖率地板 / `mypy --strict` / ruff），通过信号是退出码 0（覆盖率额外看 `TOTAL`）；**真实那一半**是接上真实端点把本里程碑的完成判据跑一遍并通过，不进 CI、不替代门禁；**UAT 那一半**是人坐在终端前拿它办一件真事，场次与观察表在 `docs/verification/<change-id>-uat.md`，**那张表没填完这个 change 不得归档、不得合入 `main`**，tty 场次 agent 不得代跑。三半都过才算验收（ADR-0024、ADR-0025）。

## 命令现状

- 已实现：`minihns run` / `replay`（M1）、`chat`（M6）、`serve --http`（M7）。
- H1 新增：`minihns host --http`（常驻多会话；与 `serve` 的 one-shot 语义分开）。
- M11 新增：`minihns run --resume <id>` / `chat --resume <id>`。
- M14 新增：`chat` 里的 `/skills` / `/skill <name>` / `/help`；host 的 `GET /commands` 与 `POST /sessions/{id}/commands`。
- MEM2 新增：`memory consolidate`（默认关闭）。
- E1：`scripts/eval/run.py`（不是 `minihns` 子命令，避免把评测塞进产品命令面）。

## 跨平台与 CI

跨平台对齐已在 M3 并入：路径规范化、tty、SIGINT、进程树终止与 CI 矩阵（Windows + Linux）。H1/H2/M10 的判据要在两端各跑一遍；真实端点与 E1 的真实模式不进 CI（CI 不持密钥）。Windows 上四条 SIGINT 子进程判据继续 skip，Linux runner 上跑。

## 引用

- 八阶段对照：`docs/stage-map.md`（图上的 8 个阶段 × 状态 × 里程碑 × 证据）。
- DSH 逐支柱对照：`docs/dsh-alignment.md`（历史基线 `m3`，形状仍有效）。
- 延后重构账：`docs/adr/0002-deferred-refactors.md`；2026-10-26 的分流见该文件末尾。
- 当前进度：`docs/CURRENT.md`（只写「现在」，不写历史）。
