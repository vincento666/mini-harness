# 与 DSH 的运行时对齐走查

基线：`main` = tag `m3`（`8093cf6`）。依据：DSH 侧取自 `docs/dsh-reference/`（设计说明 §3 十四层与 §5 五句横切、剖析 L0–L13、蓝图契约卡、逆向分析 §7–§10）；mini 侧取自 16 个实现模块、8 份主规格 76 条 Requirement、9 份 ADR、`docs/CURRENT.md` 的已知缺口。本文只走查**运行时形状与机制**，不重开任何已锁定的决策。

## 1. 结论三行

1. **机制流程上贴合**：日志即真相、折叠派生上下文、失败也是结果、两轴围栏 + CAS、显式回合循环、按码路由、密钥纪律、压缩公式——这八样都在，判据形状与 DSH 同源。
2. **架构形式上脱离很大**：DSH 的运行时形状（常驻宿主、投影分流、turn/step + inbox、六段管线与协作式 signal、OS 沙箱、恢复与格式迁移）在 mini 里缺席或更薄。
3. **脱离全部记账过**：九份 ADR + `docs/handoff-2026-10-15.md` §4.11 + `docs/CURRENT.md` 的已知缺口。这是**记账过的偏离，不是漂移**。但「记账」不等于「排期」——走查时缺席的支柱里只有压缩那一根有里程碑；2026-10-20 的裁决把记账变成排期（ADR-0010 到 ADR-0013，见第 5 节与第 7 节）。

## 2. 支柱对照表

DSH 的 17 根支柱（剖析 L0–L13 加内核五层）逐条对照。状态取值：**已在** / **部分** / **未落地**（规格写了、代码没有）/ **已排期**（ADR-0010 之后有里程碑）。下表是 2026-10-19 走查时的实况，「已排期」那一列的里程碑号是 2026-10-20 裁决补上的。

| # | DSH 支柱 | mini 现状 | 状态 |
|---|---|---|---|
| 1 | 会话日志追加、检查点、格式迁移 | 明文 JSONL、只追加、`seq` 单点分配、`schema_version` 从 1 起、无检查点、无迁移器 | 部分 |
| 2 | 事件折叠与投影分流 | 折叠是纯函数、`replay` 逐点重算相等；**没有投影分流**（只有一条「受保护头部 + 完整对话体」） | 部分 |
| 3 | 上下文窗口预算与压缩 | 公式照抄（决策 26 的 `floor(min(W × 0.8, W − O − 65 536))` 与尾部保留 16%），代码里没有任何预算常量、没有 `CONTEXT_WINDOW_EXCEEDED` | **未落地**（M5） |
| 4 | 回合主循环 | 五步显式循环、每回合恰一次模型调用；**没有 turn/step 双层** | 已在（形状更薄） |
| 5 | 工具注册与派发管线 | 三段：校验 → 围栏/approval → 执行；16 值结果词表 | 已在（DSH 是六段） |
| 6 | 沙箱与围栏 | 进程内两轴 + CAS + approval；**无 OS 级强制**（ADR-0003） | 已在（刻意薄；M10 立缝、M15 增厚） |
| 7 | 工具并发与取消 | `MAX_PARALLEL_TOOLS = 8`、只读并发 / 会改动串行、超时与取消塌成结果词 | 已在 |
| 8 | 委派与子代理 | 无 | **已排期**（M12） |
| 9 | 目标状态机 | 无 | **已排期**（M13） |
| 10 | 技能与知识注入 | 无 | **已排期**（M14） |
| 11 | 外部触发（排期 / webhook / hook / MCP） | 无 | **已排期**（M14） |
| 12 | Provider 接缝 | 单方法 Protocol + **两个 adapter**（mock、openai_compat）+ 按码路由 | 已在 |
| 13 | 装配与配置层叠 | argparse + `_await_session` 里硬编码工具表 | 部分（DSH 是 patch 层叠） |
| 14 | 工件与发布（manifest、完整性、版本） | wheel + `uv sync --frozen` + CI 矩阵；无 manifest、无完整性 | 部分 |
| 15 | 客户端协议与投影 `wire` | `--events jsonl` 逐行镜像日志 | 部分 |
| 16 | 可观测与遥测 | 全程事件日志 + `context/assembled` 指纹；无 OTel | 已在（更薄） |
| 17 | 失败关闭 | 非 tty 未 `--yes` → `APPROVAL_UNAVAILABLE` → 退出码 3；日志不可写即终止 | 已在 |

**到第一阶段结束（M7）**：已在 8 根（4、5、6、7、12、16、17 + M5 的 3），部分 5 根（1、2、13、14、15），未落地 0 根，已排期 4 根。DSH 的运行时形状仍然缺席——它由第二阶段补：M10 立缝与加段、M11 补投影分流 / 折叠缓存 / resume / 格式迁移、M12 与 M13 补委派与目标、M14 补技能与外部触发、M15 补 OS 级拦截。

## 3. 三处真走岔（不是简化，是选了相反的形状）

| 走岔 | 成文位置 | 裁决与落点 | 要对齐 DSH 需要什么 |
|---|---|---|---|
| **取消是会话终止，不是回合内事件**。DSH 协作式、静默、分派发前（`ABORTED_BEFORE_DISPATCH`）与派发后（把成功结果替换成 `ABORTED`），回合继续 | ADR-0007（决策 15 的部分推翻） | **已裁决转向**：ADR-0011（ADR-0007 已标 superseded）→ M8 | 加「派发前被取消」这一类结果词 + 被中断回合的闭合记录；会话终止交给入口 |
| **结果缓冲到批次结束才落盘**。DSH 检查点先于副作用、`resume` 时补 `interruptedTurnClosers`、崩溃留下的未匹配调用写 `TOOL_OUTCOME_UNKNOWN` 且不自动重试 | `m3` design.md 的 D3 + `docs/CURRENT.md` 已知缺口（**无判据**） | **已裁决转向**：ADR-0012（推翻 D3）→ M8 | 反过来选「立刻落盘」并给崩溃留 closer——三处里唯一带「缺口」标签的一处，现在有了判据 |
| **管线三段、工具体不接 signal**。DSH 六段 + guard 单调 + `execute` 换入派生信号、finally 恢复调用方信号 + `finalizeContent` + observe-only `tools/result`；每个工具体必须观察 `exec.signal` | ADR-0003（自己写了「加新段要改 `dispatch_tool_call` 函数体」） | **已裁决转向**：ADR-0013（ADR-0003 第 3 条作废）→ M10 | 加 guard / post-execute / finalizeContent 三段，并把派生信号交给工具体 |

三处原本都有人类裁决记录；2026-10-20 的裁决是**以 DSH 为真理把它们转向**，落档 ADR-0011 / 0012 / 0013。按 AGENTS.md，这类转向只能由人裁决，规格与测试不得自行放宽。

## 4. 未落地与错位

### A. 排期了的（ADR-0002 的处理时点）

第 3 条 `_replay` 下沉 → M6；第 14、15 条端点类型与四处「是不是 openai」判断 → M5；第 18 条抽 `_Batch`、第 19 条 `begin`/`ask_logged`、第 20 条派发链、第 21 条 data clump、第 22 条改名、第 23 条 `denial_code: FenceCode`、第 24 条 `ApprovalAsked` 钩子 → M5；第 25、26 条测试旋钮与 `wrap` → M5 顺手；第 29 条 `approval_detail` 钩子、第 30 条 bash 输出解码 → M5 或 M6。

**注意**：第 18 条自己写的处理时点是「M5（chat REPL 需要把同一派发段跑在不同外壳里）」——那个条件要到 M6 才成立。第 14、15 条已经写着「推到 M5」一次。**建议 M5 收尾轮逐条改判时把这批统一改判到 M6**，否则会变成第五次「未处理推到 M5」。

### B. 成文取舍、不打算对齐

围栏不是安全边界（ADR-0003）、CAS 只比读到的窗口（ADR-0004）、适配器只认 OpenAI 拼写且不读流式（ADR-0006）、`bash` 只受档位轴（ADR-0008）、经平台 shell 执行并按平台收进程树（ADR-0009）、Windows 真实 Ctrl-C 黑盒无判据、硬杀留半截前缀无判据。

### C. 账本自己过期了（本轮已更正）

| 条目 | 实况 | 本轮处理 |
|---|---|---|
| ADR-0008 正文写的 `raw_path=args.target_path() or ""` | 已不存在：`dispatch.py:61` 直接传 `None`，`judge_fence` 有显式 `raw_path is None` 分支 | 已在 ADR-0008 正文加「实现现状」一行 |
| handoff 决策 15「Ctrl-C 与超时都写 `tool/cancelled` 并继续回合」 | 与代码相反；ADR-0007 曾是权威更正，现已被 ADR-0011 取代（0007 已标 superseded）；handoff 冻结不编辑、自身没有指路标记 | 已在 AGENTS.md 的「先读这三样」处加指路标记，并随 ADR-0011 更新 |
| ADR-0001 第 6 条与 cli 主规格把 `error/replay` 写成事件类型 | 代码只往 stderr 打 `REPLAY_MISMATCH: …`；`error/replay` 不在 `ERROR_EVENT_TYPES`、从不进日志 | 已改 ADR-0001 第 6 条与 cli 主规格的措辞（改文档以匹配实现，不扩词表） |
| 决策 33 的 `scripts/acceptance.py` | 不存在（没有 `scripts/` 目录）。它被「每里程碑一条人手验收 + `docs/verification/<change-id>-manual.md`」替代（ADR-0005 追加的裁决），但没有任何文档写明这个替代 | 已在 `docs/roadmap.md` 写明这个替代 |
| `PROVIDER_ABORTED`「有词表值、没有生产路径」 | **不是缺陷**：它有两条 seam ⑤ 判据（`tests/test_provider_openai.py:230`、`:293`），适配器会产出（`provider/openai_compat.py:204`、`:234`）；缺的是内核侧调用路径，provider 主规格括号里自己写明「这条只在 provider 侧兜住」 | 不改代码；`docs/CURRENT.md` 的措辞已准确，本文记下这条澄清 |

### D. 代码有、主规格没写（11 条，未排期）

`InternalFailure` → `error/internal` → 词表外 stop reason → 退出码 1；`EventLog.append` 把词表外类型塌成 `error/internal` 并记 `unrecognized_type`；`approval/request` 写不进去塌成 `TOOL_IO_FAILED`（ADR-0002 第 28 条自认）；`ToolArgs.approval_detail()` 只有一个实现（第 29 条）；`judge_fence` 的 `raw_path is None` 分支与硬编码判定顺序（顺序本身就是行为）；`write_file` 自动 `mkdir(parents=True)`；`path_key` 的 `realpath` + nt 上 `normcase`；`grep` 没有扫描侧上限（只有输出 250 条）；`fold` 完全忽略 `tool/call`、`approval/*`、`turn/*`、`error/*`；`RunOutcome.turns` 生产里没人读；硬杀落在批次中间留下「有 `tool/call` 没 `tool/result`」的前缀。

## 5. 排期：九层齐备、围栏做薄（2026-10-20 已裁决，ADR-0010）

口径：**围栏层做薄但留增厚空间**（保留档位轴、边界轴、approval 轴、CAS、进程树收干净这五样最小能力，OS 级拦截推到 M15）；其余八层（工件、组合、内核、能力、数据、委派、模型、扩展）都基本实现。

**执行顺序**：第一阶段 M1 → M2 → M4 → M3（已完）→ **M8 三处转向里的两处** → M5 → **M9 组合层** → M6 → M7；第二阶段 **M10 → M11 → M12 → M13 → M14 → M15**；第三阶段（加壳）等前两阶段做完再规划。

两处排序不是随手排的：三处转向排在 M5 之前，因为 M5 的压缩与 replay 判据、M11 的 resume 都建在「日志前缀在任何时刻都是完整事实」之上；组合层提前进第一阶段、排在 M5 之后 M6 之前，因为 M6 的常驻外壳要读配置、工具表要从装配来，而不变量 D 是六条里唯一还没落地的，不该再往后推。

### 5.1 薄围栏的「增厚空间」具体是什么

不是留一句「以后加沙箱」，而是**把执行段立成一条缝**：现在「怎么跑一条命令」写在 `tools/bash_tools.py` 里，平台分支（`taskkill /T /F /PID` 与 `killpg`）混在工具体内。把它抽成 `CommandRunner` 接口，两个既有平台分支就是这条缝上的两个 adapter——按 codebase-design 的判据，**两个 adapter 才是真缝**。OS 级沙箱将来是**第三个 adapter** 坐在同一条缝上，不动工具体。

配套两件事，都是 fail-closed 的形状：`FenceCode` 加 `SANDBOX_UNAVAILABLE`（runner 不可用即拒绝，退出码 3）；runner 自身的失败约定码（DSH 的 `RUNNER_FAILURE_EXIT = 127` 与 `RUNNER_SIGNATURE` 是同一形状）。

### 5.2 合进 M5–M7 的三处

| 里程碑 | 合并内容 | 为什么合在这里 |
|---|---|---|
| **M5** `m5-context-budget-compaction` | ① 新增 `CONTEXT_WINDOW_EXCEEDED` 的 stop reason；② 退出码 4 从「保留、MUST NOT 被产生」变成可达（cli 主规格那句要改）；③ `Usage` 从「只落日志」变成触发线的输入 | 不变量 D 的另一半。M5 原判据（小 W 触发压缩、原文仍在日志）不覆盖溢出那一侧，而 `StopReason` 现在六个取值里没有它 |
| **M6** `m6-chat-repl` | ① 扩词表 `user/message`（折叠里第二条人话目前没有生产者：`fold` 只从 `session/start.payload.prompt` 取一条 user 消息）；② 顺带收 ADR-0002 第 3、18、21 条 | REPL 不扩词表就跑不起来。`user/message` + 回合边界领取，就是 DSH 的 inbox 的最小替身（不做 `spliced`/`inserted` 定位） |
| **M7** `m7-serve-http-sse` | 断线续读：客户端带最后 `seq`，从该点续读事件流 | DSH「日志是唯一 generation source」的最小版，判据现成（事件流与日志逐行一致 + 从任意 `seq` 续读仍一致） |

M5–M7 各自**不加新层**，只把「原判据没覆盖的那一半」补齐。

### 5.3 第二阶段（编号已按裁决重排）

| | change | 层 | 内容 | 完成判据 |
|---|---|---|---|---|
| **M8** | `m8-runtime-semantics-alignment` | 内核 + 数据 | 三处转向里的两处（ADR-0011 / ADR-0012）：取消改成回合级协作式事件（派发前 / 派发后两个结果词 + 被中断回合的闭合记录）；工具结果在产生时立刻落盘 + `TOOL_OUTCOME_UNKNOWN` | 硬杀一轮后重读日志：每条未配对的调用都有闭合记录、replay 仍逐点相等；两种取消各得到自己的结果词、都不掀翻回合 |
| **M9** | `m9-assembly-and-config-layering` | 组合 | `mini.config.toml`（决策 8 预告过）+ 层叠顺序「内置默认 → 配置文件 → CLI flag」；工具表从装配来（替掉硬编码的 5 + 1）；必需项缺失当场失败 | 同一 CLI 在两份配置下 `session/start.payload` 不同；缺必需项退出码 2 且**没有日志文件** |
| **M10** | `m10-tool-pipeline-stages-and-runner-seam` | 能力 + 围栏 | 管线加段（单调守卫 / 执行换入派生信号并恢复 / 执行后观察与替换 / 内容收尾）；执行段立成 `CommandRunner` 缝（win32 / posix 两个 adapter）；`FenceCode` 加 `SANDBOX_UNAVAILABLE`；runner 失败约定码。**不实现 OS 级强制** | 注入「runner 不可用」的桩 → `error/fence(code: SANDBOX_UNAVAILABLE)` + 退出码 3；两个既有 adapter 的判据不变；工具体收到信号后自己停 |
| **M11** | `m11-projection-cache-and-resume` | 数据 + 工件 | 投影分流三态（进上下文 / 被遮蔽 / 只在日志）；折叠缓存「日志领先、缓存跟随」；`--resume` 对既有日志继续追加；`schema_version` 相邻迁移 | 被遮蔽的消息不出现在折叠结果里；硬杀后的日志被 resume 补出闭合；`--resume` 后 replay 仍逐点相等 |
| **M12** | `m12-subagent-delegation` | 委派 | `subagent` 工具（spawn 形状）：独立子 session、独立日志、父日志只有 `tool/call` + `tool/result`；子 session 继承档位与边界、**不继承 approval 放行**；`maxDepth` 单调下限 | **seam ⑦**：子代理写自己的日志；子代理问人得到 `APPROVAL_UNAVAILABLE`；深度超限是结果词不是异常 |
| **M13** | `m13-goal-rounds` | 委派 | 持久 goal 对象 + 轮次续跑 + 轮次上限 + `blocked` 需同一阻碍持续三轮 | **seam ⑦**：小上限下自动续跑 N 轮；同一阻碍持续三轮落 `blocked`、两轮不落 |
| **M14** | `m14-skills-and-triggers` | 扩展 | `SKILL.md` 目录发现 + `skill` 工具（正文按需加载）；外部触发塌成一条可重放的会话事件 | 仓库内一个 skill 被列出并加载；一条外部触发在日志里是一条事件、replay 仍相等 |
| **M15** | `m15-os-enforcement` | 围栏增厚 | Windows 侧从 job object + `KILL_ON_JOB_CLOSE` 起步、再 ACL；Linux 侧 landlock / bwrap | 一条命令试图写工作区外的文件时被 OS 拒；OS adapter 坐在 M10 那条缝上、工具体不改 |

M15 排在第二阶段末尾：本机没有可用的 Linux，Windows 侧 ACL 是 DSH 里最重的一块（受限令牌 + ACL 改写 + 审计补偿），所以从 job object 起步而不是从 ACL 起步。M10 立了缝之后，M15 什么时候做都不影响其它层——这是「围栏做薄但留增厚空间」的全部含义。

### 5.4 用术语对齐代替实现（已落进 `GLOSSARY.md`）

| DSH 的形状 | mini 的处理 |
|---|---|
| turn / step 双层（一个 turn 可含多次模型调用） | **不做双层**。mini 的「一回合恰一次模型调用」是 turn-loop 主规格的成文事实。`GLOSSARY.md` 已写明 **mini 的回合 ≡ DSH 的 step** |
| config header 与「策略可在会话中途变」 | 一次性 run 没有中途变策略这回事。写明 **mini 的 `session/start` ≡ DSH 的 config header**，并记下 DSH 为什么拒绝把 `sandboxMode`/`approvalPolicy` 写进 header |
| 投影单元 + `wire` / host-only 区分 | 写明 **`--events jsonl` 与 M7 的 SSE ≡ 日志的逐行镜像**，mini 没有投影单元这一层 |

## 6. 这份排期的四笔代价（不写出来排期就是假的）

1. **词表扩张**：`user/message`、`session/resume`、`SANDBOX_UNAVAILABLE`、`TOOL_OUTCOME_UNKNOWN`、派发前 / 派发后两个取消结果词、闭合记录类型、`subagent/*`、`goal/*`、`skill/*`。粗算 M8–M14 新增 12–18 个词表值，每个都要配「每个值可达」的判据（Active Lesson 1 栽过两次）。
2. **seam 清单已扩到七条**：新增 ⑦ 委派与目标（子会话日志与父日志的配对、目标轮次与 `blocked`）。组合层与扩展层不新增缝，在 ② 与 ⑥ 判。AGENTS.md 的 seam 清单与「MVP 明确不做」那节都已按裁决改写。
3. **人手验收与 CI 的分工更紧**：委派与 goal 会放大真实模型调用，而 CI 不持 API key（ADR-0005），所以 M12 / M13 的判据必须全 mock，真实形状只能靠人手验收——这两个人手验收是整份排期里最贵的两项。
4. **三处转向要改已经绿过的判据**：turn-loop 主规格里「工具调用与结果按声明顺序落盘」要在 M8 改；并发只读工具的结果顺序变成**完成顺序**，判据要按集合而不是按序列断言；ADR-0002 第 10 条（取消只在回合边界被看到）从「已处理」变「被取代」。M3 的 12 条变异里有一条守的就是落盘顺序，它要跟着重写。

按已跑完的五个里程碑（M1、M2、M4、M3 加 M3 的 CI）的节奏粗估，M8–M14 七个新里程碑约等于再走一遍 M1–M3 的量，其中 M12 与 M13 因人手验收更重，M15 因需要本机没有的 Linux 环境而另算。

## 7. 裁决结果（2026-10-20）

1. **排期成立**：MVP 分两阶段、第三阶段（加壳）待规划；测试缝从六条扩到七条。落档为 **ADR-0010**，`docs/roadmap.md` 的里程碑表已重排（M8–M15 是新决策编号，执行顺序写在表头），AGENTS.md 的「MVP 明确不做」改成「MVP 分两阶段」。
2. **三处走岔按 DSH 为真理转向**：**ADR-0011**（取消是回合级协作式事件，会话是否终止由入口决定；取代 ADR-0007）、**ADR-0012**（结果在产生时立刻落盘 + 闭合记录 + `TOOL_OUTCOME_UNKNOWN`；推翻 M3 design 的 D3）、**ADR-0013**（管线加段 + 派生信号 + 执行段立成缝；部分取代 ADR-0003 第 3 条）。前两条落在 M8，第三条落在 M10。
3. **术语对齐三条落进 `GLOSSARY.md`**：此后不再为「形状像不像 DSH」付钱。

一处遗留：`docs/handoff-2026-10-15.md` 的决策 15 与决策 26 附近写的取消语义现在与 ADR-0011 相反。handoff 冻结不编辑，指路标记在 AGENTS.md 的「先读这三样」。
