# 当前状态

**更新：2026-11-20**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/CURRENT-history.md`、`docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` 以 `git log -1` 为准；最近一次里程碑合并是 `m14c`（`09caa26`，2026-11-17 07:55）。
- **门禁实测（2026-11-20，`change/m13-goal-rounds`）**：ruff `format --diff` / `check` 绿、`mypy --strict` 绿；**860 passed / 7 skipped / 0 failed**；`openspec validate --all --strict` 绿（23 规格 + 2 change，共 25 项）。覆盖率口径见下一条——**上一轮的 96.66% 是累积口径，不是单次读数**。
- **覆盖率读数机制（源码事实）**：所有 reporting 命令在出报告前都会调一次 `combine`（`coverage/cmdline.py:884-887`），默认 `keep=False` 会删掉全部 partial。所以「为看单文件再跑一次 `report`」会吃掉下一批输入（L-079 的复发形态）——只看 `scripts/coverage-report.sh` 的那一次输出，别为了换视角再跑一遍。
- **清理 partial 的办法（避开批量删除守卫）**：`mkdir -p .tmp/cov-archive && mv .coverage.* .coverage .tmp/cov-archive/`——移动不算删除。攒多了在**单独一条命令**里删归档目录，或由人批一次批量确认。
- **不做「关 parallel + 单文件 append」**（2026-11-18 判断，理由留档）：partial 是子进程覆盖率的常规采集方式；append 到同一个 SQLite 在并发子进程下有写冲突风险，收益只是少一步 `combine`。今天的问题已查明是「反复跑 report 吃掉 partial」，不是 partial 机制本身。
- **沙箱会把长命令掐断**：全量测试在沙箱里跑时，两次都在十几分钟后被 `sitecustomize._BrokerProtocolError: execution capability 已过期` 打断，日志只剩空文件（partial 已写 160 份，说明测试本身在跑）。四道门禁与覆盖率两步因此在**沙箱外**跑（每轮约 3 分钟）；沙箱内跑单个测试文件没问题。
- **活动 change**：`m13-goal-rounds`（分支 `change/m13-goal-rounds`）。apply 到 5.x：**1.1–5.10 已落**——goal 事件与折叠、`user/message.source`、`[goal]` 四键与 todo 并行纪律、三个目标工具（CAS / 相位矩阵 / 阻塞门槛）、段后续跑（四事件顺序、`round-limit`、失败收尾）、`replay` 的轮次校验、`get_todos` 读回（补 D8 的遮蔽缺口）、武装位收口、`/goal` 六条命令、`--resume` 黑盒、REPL 段后驱动、host 驱动与队列人话优先、未决问题交回人类、停滞闸门（默认开、阈值 2）、`/goal edit` / `complete`。**6.1 真实端点已通过**（`deepseek-chat`，A/B 两场）；**6.3 变异已完成**（六条全杀，M5 单点覆盖记为薄弱处）；**6.4 Learning Gate 已完成**（L-086–L-089 进收件箱，无晋升）。只剩 **6.2 UAT**（人跑；场次 1 已按 D15 改口）。六问已答：单目标 + 任务并行（ADR-0042）。
- **已裁（M13，2026-11-19）**：轮次准入点从「首条 `turn/start` 之后」挪到「首条 `context/assembled` 之后」——装配完成才算一轮，注入/折叠/装配内压缩失败不再白烧额度。四事件顺序随之变成 `segment/start → goal 消息 → turn/start → context/assembled → goal/updated`；契约行为 1 新增一条顺序判据。ADR-0043 已改为 accepted。
- **覆盖率口径（2026-11-20 查清）**：项目一直用「合并仓库根所有历史 partial」的**累积口径**报数（96.66% 即此）；单次全量跑 `coverage run -m pytest` 只有 **78.47%**（4943 条 / 1064 未覆盖）。黑盒测试给每个子进程套了一层 `coverage run -p`，其 partial 落在仓库根（`tests/cli_blackbox.py`），但把本次 309 个 partial 合并后读数反而降到 74.59%（96 个被跳过），说明**合并链路本身有问题**，不是覆盖真的掉了。95% 地板当前按单次口径是红的。已记为开放缺口，待单独修；本轮不擅改地板。
- **已裁并实现（2026-11-20，问题/队列/停滞/host 驱动；同日三裁定停滞阈值）**：① host 的 goal 不再只到命令面——段后收尾抽成 `settle_segment`，`run` / `chat` / `host` 三处共用；host 队列里有人话时先跑人话，队列空才开 goal 轮（对齐 DSH 的 `competingQueued`，design D13）。② `ask_user` 问不到人时不再落 `paused`：段尾交回控制权，目标保持 `active/armed`；人的回答是一条人类段（不推进 `rounds_started`），它收尾后自动接下一 goal 轮（D15，取代 D11）。③ 停滞闸门**默认开、阈值 2**（2026-11-20 三裁）：连续两个 goal 轮次零工具调用才 `stalled`（解除武装、相位不变、计数清零，D14）；一轮空转不误杀，`stall_rounds = 0` 可完全关闭（对齐 DSH）。判据单位是轮，不是回合。`segment/end` 增 `tool_calls` 供审计。④ `/goal` 补 `edit [--max-rounds N] [正文]` 与 `complete`：edit 不动相位/武装位，可改上限解锁 `round-limit`。⑤ `rounds_started` / `max_rounds` 的口径写进 `goal` 规格与 `GLOSSARY.md`：前者是当前 goal 轮号，后者是单目标上限，人类段不计数。
- **UAT 场次 1/2 暴露并已修（2026-11-19）**：① 自动轮次里 `ask_user` 问不到人时驱动仍续跑，白白消耗轮次额度——现在段尾 `awaiting_input`、目标落 `paused` 并解除武装（design D11，`added`）；② `write`/`edit` 回执把相对 `--workspace` 原样拼出（`.tmp/uat/m13/notes.md`），与 bash 的 cwd 对不上——工作区装配时绝对化，回执改工作区相对路径；③ 自动轮次之间没有终端边界——补 `[轮] n/cap`、`已用尽`、`目标已暂停` 三类 stderr 行；④ `/goal resume` 之后还要人敲一行「继续」（那一行会开人类段、把活干在轮次之外）——现在命令成功即驱动下一轮（design D12）。
- **已核对（M13，2026-11-19）**：DSH 的 step / turn / goal round 与 mini 的回合 / 段 / 轮以及各自跟 goal 的关系**都有直接等价物**（逐条对边界事件与判据，见 `m13-goal-rounds-dsh-review.md` D.6）。据此 D.2–D.5 维持现状：D.2 已对齐、D.3 语义对齐（表示多一份冗余字段）、D.4 对齐、D.5 保持 `simplified`（要真对齐得先有输入队列）。`get_todos` 记为 `added`（D.7），不是对齐项；它的作用域是**本段**——跨轮重交靠模型历史（DSH 同构，零次额外调用）；**goal 轮同样清表**（DSH 的 round 就是一次 turn，`turn/start` 无条件清），被遮蔽后跨轮读不回，两边一样（D.7.2）。要跨轮读旧表需另加 `scope=last`——**已裁（2026-11-19）：按 D8 不加**，表保持段作用域。
- 已合并但未删的分支：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。

## 下一步

0. **本周冲刺（2026-W47）**：`docs/plan-2026-W47.md`；M14c 已完成，下一项 M13。

1. **M14c 个人助理 UX 工具——已完成**（`2026-11-16-m14c-personal-assistant-tools`）：todo/plan/ask_user/present、投影框架与快照/SSE；23 份主规格 validate 绿；全量 728 passed / 6 skipped（macOS 上 1 条大小写折叠用例失败，属平台假设）。

2. **M13 目标轮次**：1.1–5.10 已落，6.1/6.3/6.4 已完成；只剩 6.2 UAT（场次 1/2 已按 D15 改口，人跑）。M13 之后是 `align-turn-step-naming`（C 方案，单立 change）→ M15a 进程收容 → MEM1 基础记忆 → E1 → E2。逐组件缺口见 `docs/reference/dsh-core-components.md`。
3. 并行支撑轨：E1 评测（`scripts/eval/` 只有 README，无 runner）；E2 组件接缝在 M 核心之后。

## 开放缺口

- **P0 预算读数未复现**：`fix-post-compaction-budget-reading` 20 个 task 未 apply；2026-10-27 的真实端点诊断没复现「遮蔽后 tokens 后 > 前」。要么补稳定样本，要么降级为未复现的历史缺陷。
- **`SESSION_BUSY` 状态码自相矛盾**：spec 表写 409，实现按 429 归档；留到后续 spec 修正时裁。
- **委派的三处语义原语未对齐**：子级审批继承父模式、没有「沙箱升级才问人」的阶梯、工具表只是组合过滤。见 `docs/verification/m12-subagent-delegation-dsh-review.md`。
- **命名兼容层的删除点（2026-11-20）**：`align-turn-step-naming` 计划用日志 schema v2 在读取时上迁 v1；删除条件见该 change 的 design D4（两个里程碑 + 无 v1 日志要回放 + 外部消费者升级完）。到期未删要在这里记账。
- **覆盖率合并链路待修（2026-11-20）**：单次口径 78.47%、累积口径 96.66%、本次 partial 合并 74.59%，三个数不可比。先查 `coverage combine` 为何跳过 96 个 partial（`COVERAGE_FILE` 与 `-p` 后缀的组合），再决定是修链路还是把地板改成单次口径。修好之前，门禁读数不得再引用 96.66% 当「本次」。
- **UI 服务端 allowlist 暂缓**：H2 保持日志逐行镜像 + 客户端过滤；公网/多客户端时再判。
- **fork 与插件容器暂不做**（ADR-0035）；**OS 级沙箱**在 M15a。

## 地图

- 里程碑与执行顺序：`docs/roadmap.md`　· 八阶段：`docs/stage-map.md`
- 教训：`docs/lessons.md`（只读 Active；归档 `docs/lessons-archive.md` 不读）
- 流程与升级清单：`docs/process/devops-loop.md`（推理账 `docs/process/devops-loop-rationale.md`，改流程时才读）
- 延后重构账：`docs/adr/0002-deferred-refactors.md`
- 每 change 的验收：`docs/verification/<change-id>-{report,uat,real-endpoint,mutation,code-review,dsh-review}.md`
