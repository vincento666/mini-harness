# 里程碑

每个里程碑 = 一个 OpenSpec change（流程见 AGENTS.md 的流程节）。**完成判据是验收口径**，不是内容描述；收尾门禁全绿且判据可复现，才算完成。

**执行顺序（ADR-0005 的换序 + ADR-0010 的两阶段）：第一阶段 M1 → M2 → M4 → M3 → M8 → M5 → M9 → M6 → M7；第二阶段 M10 → M11 → M12 → M13 → M14 → M15；第三阶段（加壳）待规划。** 编号是决策编号、不是执行顺序；下表按执行顺序排，M6（`m6-chat-repl`）与 M7（`m7-serve-http-sse`）都已合入 `main`（merge commit `d77e8ad` 与 **`34982d1`**）、归档在 `openspec/changes/archive/2026-10-22-m6-chat-repl/` 与 `…/2026-10-22-m7-serve-http-sse/`、tag `m6` 与 `m7`，**第一阶段（M1 至 M9）到此做完，下一个里程碑是第二阶段的 M10**。

| | change | 内容 | 完成判据 |
|---|---|---|---|
| M1 ✅ | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `minihns run` + `minihns replay` | mock 场景跑通；replay 与实时折叠一致 |
| M2 ✅ | `m2-file-tools-and-fences` | `read`/`write`/`edit`(CAS)/`glob`/`grep` + 工作区边界 + 写前必读 + 两轴 | 批量改文件成功（fixture 仓库一轮 10 次 read+edit 全 `OK`）；越界写被拒并写 `error/fence`、退出码 3；真实 tty 的 `y` / `n` 两次 smoke 分别是 0 与 3。**判据全部复现，收尾门禁跑完（变异 19 条 + 审查后抽查 4 条、Learning Gate 收 5 条、`code-review` 两轴修掉两条最重的发现）；已合入 `main`、归档为 `2026-10-18-m2-file-tools-and-fences`、tag `m2`** |
| M4 ✅ | `m4-real-provider`（原名 `m4-real-provider-deepseek`，因先跑本地端点而改名） | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | **两个端点各一次真实 smoke 跑通**：本地 `http://127.0.0.1:8300/v1`（Strata server，模型 `qwen3.8-flash-next-iq3_xxs`）先跑通，DeepSeek 官方端点收尾；mock 与真实同一接口；`ToolSpec` 带上参数 schema（ADR-0005 第 4 条那条阻塞项已在 tasks 2.1–2.3 解决）；真实 smoke 不进 CI。**判据全部复现，收尾门禁跑完（变异 18 条：17 条首轮被杀、存活的 E2 补三条判据后被杀；Learning Gate 晋升 1 条进 Active、收件箱收 3 条并消化 7 条；`code-review` 两轴 16 条发现里修 5 条、记账 11 条）；已合入 `main`、归档为 `2026-10-18-m4-real-provider`、tag `m4`** |
| M3 ✅ | `m3-bash-concurrency-timeout` | `bash` + 只读并发（max 8）+ 超时与取消事件 + **平台适配层（路径规范化 / tty / 进程树与信号）+ CI 矩阵（Windows + Linux）** | 一轮内并发读 ≥2；超时写 `tool/cancelled` 且回合继续；同一套判据在 Windows 与 Linux 各跑一遍全绿，门禁由 CI 跑。**判据全部复现，收尾门禁跑完（变异 12 条：10 条首轮被杀、T1 与 O1 存活后各补一条判据、C2 判定 dud；Learning Gate 收 4 条、关闭 1 条、AGENTS.md 不晋升；`code-review` 两轴七条全修、记账 12 条）；人手验收三个 session 跑完（真事 / 30.07 s 超时 / 7.51 s Ctrl-C）；CI 两端各跑四道、两端 `TOTAL` 都是 1136/50/96%，`main` 首绿 `39254753712`；已合入 `main`、归档为 `2026-10-19-m3-bash-concurrency-timeout`、tag `m3`** |
| M8 ✅ | `m8-runtime-semantics-alignment` | **三处转向里的两处**（ADR-0011 / ADR-0012）：取消改成回合级协作式事件（派发前被取消与派发后被取消两个结果词、被中断的回合由闭合记录收尾）；工具结果在产生时立刻落盘 + `TOOL_OUTCOME_UNKNOWN` | 硬杀一轮后重读该日志：每条未配对的调用都有闭合记录、replay 仍逐点相等；派发前取消与派发后取消各得到自己的结果词、都不掀翻回合；一次性 run 仍以退出码 5 结束。**判据全部复现，「闭合记录」这条措辞由 ADR-0014 更正为读方派生（日志里那样一条记录不存在）。收尾门禁跑完（变异 8 条：7 条首轮被杀、D 存活后补判据被杀；修复轮另补变异 I 被杀；Learning Gate 收 5 条、关闭 2 条、AGENTS.md 不晋升；`code-review` 两轴里 Spec 轴五条修 2 条、改措辞 1 条、记账 2 条，Standards 轴七条全记账进 ADR-0002）；人手验收六个 session 跑完（含取消落在并发批次中途的真事）；已合入 `main`、归档为 `2026-10-20-m8-runtime-semantics-alignment`、tag `m8`** |
| M5 ✅ | `m5-context-budget-compaction` | 窗口预算 + 触发线公式 + 剪枝 + 摘要 + 遮蔽 + 标记对 + `CONTEXT_WINDOW_EXCEEDED` 的 stop reason + 退出码 4 变可达 + `Usage` 进预算 + 收 ADR-0002 第 5 条（`stop_reason` / `outcome` / `role` 换成词表 `Literal`） | 小 W 下触发压缩；原文事件仍在日志里；压缩仍不够时以退出码 4 结束且日志里有对应 `error/*`。**判据全部复现，收尾门禁跑完；已合入 `main`（merge commit `2a77cfd`）、归档为 `2026-10-21-m5-context-budget-compaction`、tag `m5`**。**「压缩仍不够」这一半 2026-10-23 才第一次以字面形状可达**：change `fix-small-window-compaction-dead-zone` 把溢出判据换成压力预算之后，「可遮蔽的那一段本身就装不下」在 seam ① 与真端点上各跑到一次（ADR-0026） |
| M9 ✅ | `m9-assembly-and-config-layering` | 组合层：`mini.config.toml` + 层叠「内置默认 → 配置文件 → CLI flag」+ 工具表从装配来（替掉硬编码的 5 + 1）+ 必需项缺失当场失败 + 收 ADR-0002 第 14、15 条（立 `ProviderEndpoint`，「是不是 openai」四处塌成一处） | 同一 CLI 在两份配置下 `session/start.payload` 不同；缺必需项退出码 2 且**没有日志文件**。**判据全部复现，收尾门禁跑完；已合入 `main`（merge commit `5fb7675`）、归档为 `2026-10-21-m9-assembly-and-config-layering`、tag `m9`；6.5 的模型层那一半等人跑** |
| M6 ✅ | `m6-chat-repl` | `minihns chat` REPL，复用同一内核入口 + 扩词表 `user/message`（折叠里第二条人话目前没有生产者：`fold` 只从 `session/start.payload.prompt` 取一条）+ 顺带收 ADR-0002 第 3、21 条 | REPL 续跑同一会话内核；取消一个回合后会话继续。**判据全部复现，收尾门禁跑完（变异 13 条全杀：9 条首轮被杀、1 条 dud、1 条特殊形状、3 条存活后补 4 条判据被杀；Learning Gate 合并 2 条、新收 2 条、AGENTS.md 不晋升；`code-review` 两轴两条裁决落地、记账进 ADR-0002 第 51、52 条）；人手验收三个 session 跑完（真事 / 溢出 / 围栏 + replay）；六份 delta 已 sync 进主规格（新建能力 `chat-repl`）、归档为 `2026-10-22-m6-chat-repl`；已合入 `main`（merge commit `d77e8ad`）、tag `m6`；模型层那一半人手验收等人跑** |
| M7 ✅ | `m7-serve-http-sse` | `minihns serve --http` 输出 SSE 事件流 + 断线续读（客户端带最后 `seq`，从该点续读） | 事件流与 JSONL 日志内容一致；从任意 `seq` 续读仍一致。**实现、agent 侧人手验收（含模型层）、`code-review` 两轴、变异一轮与 Learning Gate 完成（组 1 至 9 加 10.1 至 10.3）**：帧是 `id` = `seq` / `event` = 类型 / `data` = 整行记录 JSON，游标就是 `seq`（`Last-Event-ID` 或 `?from=`，`0` 合法、负数与非整数 400）；`--host` / `--port` 是 CLI-only（ADR-0021）；会话收尾即进程退出（0 / 1 / 3 / 4 / 5 都在 seam ⑥ 判过）；`entry` 词表加 `serve`；收 ADR-0002 第 40、50 条；**15 个变异全部被杀死、没有存活**。Learning Gate 新收 L-049 / L-050、合并 L-040、AGENTS.md 不晋升。**收尾完成（tasks 36/36）**：四份 delta 已 sync 进主规格（新建能力 `event-stream`，主规格从 11 个能力变 12 个）、在分支上归档为 `2026-10-22-m7-serve-http-sse`、已合入 `main`（merge commit `34982d1`）、tag `m7`、10.4 `agents-md-slim` 已跑。**还等人的**：9.1 的 Ctrl-C 那一半与四条 Windows 上 skip 的 SIGINT 子进程判据（Linux runner）。模型层那一半 2026-10-22 晚跑完（用户作用域的 `DEEPSEEK_API_KEY` 显式注入 + `https://api.deepseek.com/v1`），M6 的模型层非 tty 那一半同时跑完，查出两条新形状记进 ADR-0002 第 62 与 63 条 |
| M10 | `m10-tool-pipeline-stages-and-runner-seam` | 管线加段（单调守卫 / 执行换入派生信号并在结束时恢复调用方信号 / 执行后观察与替换 / 内容收尾由工具定义负责）+ `CommandRunner` 缝（win32 与 posix 两个 adapter）+ `SANDBOX_UNAVAILABLE`（ADR-0013）+ 收 ADR-0002 第 18、23 条（抽 `_Batch`；`denial_code: FenceCode`） | 注入「runner 不可用」的桩 → `error/fence(code: SANDBOX_UNAVAILABLE)` + 退出码 3；两个既有 adapter 的判据不变；工具体收到信号后自己停 |
| M11 | `m11-projection-cache-and-resume` | 投影分流三态（进上下文 / 被遮蔽 / 只在日志）+ 折叠缓存「日志领先、缓存跟随」+ 崩溃后的读方修复 + `--resume` + `schema_version` 相邻迁移 | 被遮蔽的消息不出现在折叠结果里；硬杀后的日志被 resume 补出闭合；resume 后 replay 仍逐点相等 |
| M12 | `m12-subagent-delegation` | 委派层第一半：`subagent` 工具、独立子日志、父日志只有 `tool/call` + `tool/result`；子会话继承档位与边界、**不继承 approval 放行**；`maxDepth` 单调下限 | **seam ⑦**：子代理写自己的日志；子代理问人得到 `APPROVAL_UNAVAILABLE`；深度超限是结果词不是异常 |
| M13 | `m13-goal-rounds` | 委派层第二半：持久 goal 对象 + 轮次续跑 + 轮次上限 + `blocked` 需同一阻碍持续三轮 | **seam ⑦**：小上限下自动续跑 N 轮；同一阻碍持续三轮落 `blocked`、两轮不落 |
| M14 | `m14-skills-and-triggers` | 扩展层最小版：`SKILL.md` 目录发现 + `skill` 工具（正文按需加载）+ 外部触发塌成一条可重放的会话事件 | 仓库内一个 skill 被列出并加载；一条外部触发在日志里是一条事件、replay 仍相等 |
| M15 | `m15-os-enforcement` | 围栏增厚：Windows 侧从 job object + `KILL_ON_JOB_CLOSE` 起步、再 ACL；Linux 侧 landlock / bwrap（本机没有可用的 Linux） | 一条命令试图写工作区外的文件时被 OS 拒；OS adapter 坐在 M10 那条缝上、工具体不改 |

**每个里程碑的完成判据有三半，三半都通过才算验收**（ADR-0024 加严 + ADR-0025 加第三半，都是 2026-10-23）：mock 那一半是四道门禁，mock 桩只负责单元测试与冒烟；**真实那一半是接上真实端点把这一行的完成判据跑一遍并通过**；**UAT 那一半是人坐在终端前拿它办一件真事**，观察表 `docs/verification/<change-id>-uat.md` 没填完不得归档、不得合入 `main`。已归档的 **M5 / M6 / M7 按这条重新验收**（2026-10-23）：三份记录 `docs/verification/m5-context-budget-compaction-reacceptance.md`、`m6-chat-repl-reacceptance.md`、`m7-serve-http-sse-reacceptance.md`——M5 与 M7 全过，M6 除「取消一个回合后会话继续」（要终端前的 Ctrl-C）外全过；M5 那一跑同时证明「压缩仍不够」只能以「无可遮蔽」出现，这一条后来由 change `fix-small-window-compaction-dead-zone` 修掉（ADR-0026）。**这三条里程碑的 UAT 那一半在 `docs/verification/m5-m6-m7-uat.md`（六场），等人跑。**

**每个里程碑的完成判据里都含一条人手验收**（ADR-0005）：用真实工作区干一件真事——不是跑判据，是拿它办一件事——把观察记进 `docs/verification/<change-id>-manual.md`。它不进 CI。**2026-10-23 起它是第五道门禁**（ADR-0025）：观察表在 `docs/verification/<change-id>-uat.md`，那张表没填完这个 change 不得归档、不得合入 `main`，tty 场次 agent 不得代跑；它记的仍是「用起来是什么样」和「哪儿别扭」。M1 与 M2 的这条补在 `docs/verification/m1-m2-manual-smoke.md`。

**决策 33 预告的 `scripts/acceptance.py` 已被这条替代**（2026-10-19 更正）：仓库里没有 `scripts/` 目录、也没有那个脚本。验收口径换成了上面这条人手验收（ADR-0005 追加的裁决），逐里程碑的实测在 `docs/verification/`。读 `docs/handoff-2026-10-15.md` 时会读到旧口径，以本节为准。

## 尚未实现的命令

第一阶段的命令都已实现并在 `main` 上：`minihns run` / `replay`（M1）、`minihns chat`（M6，merge `d77e8ad`）、`minihns serve --http`（M7，merge `34982d1`）。第二阶段的命令要等对应里程碑立 change，不在此列。

## 跨平台与 CI 排在哪儿（2026-10-17 裁决）

跨平台对齐**并入 M3**，不单开里程碑：M3 的 `bash`、超时与取消撞的是硬平台差异（Windows 没有 POSIX 进程组，进程树 kill 走 job object 或 `taskkill /T`；PTY 与信号语义不同），判据本身就要在两端各跑一遍。CI 矩阵与它同期落地——没有 CI，「两端都跑绿」这句话无法被机器验证，跨平台会退化成手动 smoke。

代价：M2 与 M3 期间的实现按 Windows 语义写（路径大小写、junction、tty、SIGINT），到 M3 才在 Linux 上验证并补齐。「其他端」的接缝只在 M7 的 SSE 事件流上；web / Electron 外壳属**第三阶段**（ADR-0010），M15 才把 OS 级拦截补上。

**2026-10-18 追加裁决（ADR-0005）**：M4 换到 M3 之前，于是「两端各跑绿」与 CI 矩阵整体后移一个里程碑，Windows 绑定点的欠账多攒一个里程碑（M4 的 HTTP 与 JSON 本身跨平台，路径 / tty / SIGINT 那三处照旧欠着）。CI 不持 API key：门禁那道必须离线可跑，所以 CI 只跑 mock 判据，真实 Provider 的 smoke 归人手验收。

## 与 DSH 的对齐走查（2026-10-19 走查，2026-10-20 裁决）

`docs/dsh-alignment.md` 记着 main（tag `m3`）与 DSH 运行时设计的逐支柱对照、三处真走岔、未落地与错位的四分类。走查的排期提案已于 2026-10-20 裁决成立，本表已按裁决重排：

- **ADR-0010**：MVP 分两阶段（第一阶段五层基础 + 围栏雏形，第二阶段补全成没有外壳的完整类 DSH 形态，第三阶段加壳待规划）；测试缝从六条扩到七条，新增 ⑦ 委派与目标。
- **ADR-0011 / 0012 / 0013**：三处走岔**按 DSH 为真理转向**——取消是回合级协作式事件（取代 ADR-0007）、工具结果在产生时立刻落盘 + 闭合记录（推翻 M3 design 的 D3）、管线加段并把「怎么跑一条命令」立成一条缝（部分取代 ADR-0003 第 3 条）。
- **`GLOSSARY.md`**：三条术语对齐落档——mini 的回合 ≡ DSH 的 step、mini 的会话开始记录 ≡ DSH 的 config header、事件流输出 ≡ 日志的逐行镜像。此后不再为「形状像不像 DSH」付钱。
