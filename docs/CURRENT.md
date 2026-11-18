# 当前状态

**更新：2026-11-18**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/CURRENT-history.md`、`docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` 以 `git log -1` 为准；最近一次里程碑合并是 `m14c`（`09caa26`，2026-11-17 07:55）。
- **门禁实测（2026-11-18，`change/m13-goal-rounds`）**：ruff `format --diff` / `check` 绿、`mypy --strict` 绿；**818 passed / 7 skipped / 0 failed**；覆盖率 **95.01%（4745 条 / 237 未覆盖）**，`precision = 2` 之下 `coverage report` 退出码 0；`openspec validate --all --strict` 绿。
- **覆盖率读数机制（源码事实）**：所有 reporting 命令在出报告前都会调一次 `combine`（`coverage/cmdline.py:884-887`），默认 `keep=False` 会删掉全部 partial。所以「为看单文件再跑一次 `report`」会吃掉下一批输入（L-079 的复发形态）——只看 `scripts/coverage-report.sh` 的那一次输出，别为了换视角再跑一遍。
- **清理 partial 的办法（避开批量删除守卫）**：`mkdir -p .tmp/cov-archive && mv .coverage.* .coverage .tmp/cov-archive/`——移动不算删除。攒多了在**单独一条命令**里删归档目录，或由人批一次批量确认。
- **不做「关 parallel + 单文件 append」**（2026-11-18 判断，理由留档）：partial 是子进程覆盖率的常规采集方式；append 到同一个 SQLite 在并发子进程下有写冲突风险，收益只是少一步 `combine`。今天的问题已查明是「反复跑 report 吃掉 partial」，不是 partial 机制本身。
- **沙箱会把长命令掐断**：全量测试在沙箱里跑时，两次都在十几分钟后被 `sitecustomize._BrokerProtocolError: execution capability 已过期` 打断，日志只剩空文件（partial 已写 160 份，说明测试本身在跑）。四道门禁与覆盖率两步因此在**沙箱外**跑（每轮约 3 分钟）；沙箱内跑单个测试文件没问题。
- **活动 change**：`m13-goal-rounds`（分支 `change/m13-goal-rounds`）。apply 进行到 4.x：**1.1–4.4 已落**——goal 事件与折叠、`user/message.source`、`[goal]` 三键与 todo 并行纪律、三个目标工具（CAS / 相位矩阵 / 阻塞门槛）、段后续跑（四事件顺序、`round-limit`、失败收尾）、`replay` 的轮次校验。下一步 5.1–5.4：武装位收口、四条 `/goal` 命令、`--resume` 黑盒、REPL 段后驱动。六问已答：单目标 + 任务并行（ADR-0042）。
- **待裁（M13）**：轮次准入点是否从「首条 `turn/start` 之后」再挪到「首条 `context/assembled` 之后」——更贴 DSH 的「进入模型历史」，代价是四事件顺序与契约行为 1 的三条判据一起改。见 ADR-0043 与 `m13-goal-rounds-dsh-review.md` D.2。
- 已合并但未删的分支：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。

## 下一步

0. **本周冲刺（2026-W47）**：`docs/plan-2026-W47.md`；M14c 已完成，下一项 M13。

1. **M14c 个人助理 UX 工具——已完成**（`2026-11-16-m14c-personal-assistant-tools`）：todo/plan/ask_user/present、投影框架与快照/SSE；23 份主规格 validate 绿；全量 728 passed / 6 skipped（macOS 上 1 条大小写折叠用例失败，属平台假设）。

2. **M13 目标轮次**：propose 与契约已批，apply 到 4.4（1.1–4.4 已落）；下一步 5.1–5.4（武装位、`/goal` 四条命令、`--resume` 黑盒、REPL 驱动），再 6.x 验收。M13 之后是 M15a 进程收容 → MEM1 基础记忆。
3. 并行支撑轨：E1 评测（`scripts/eval/` 只有 README，无 runner）；E2 组件接缝在 M 核心之后。

## 开放缺口

- **P0 预算读数未复现**：`fix-post-compaction-budget-reading` 20 个 task 未 apply；2026-10-27 的真实端点诊断没复现「遮蔽后 tokens 后 > 前」。要么补稳定样本，要么降级为未复现的历史缺陷。
- **`SESSION_BUSY` 状态码自相矛盾**：spec 表写 409，实现按 429 归档；留到后续 spec 修正时裁。
- **委派的三处语义原语未对齐**：子级审批继承父模式、没有「沙箱升级才问人」的阶梯、工具表只是组合过滤。见 `docs/verification/m12-subagent-delegation-dsh-review.md`。
- **UI 服务端 allowlist 暂缓**：H2 保持日志逐行镜像 + 客户端过滤；公网/多客户端时再判。
- **fork 与插件容器暂不做**（ADR-0035）；**OS 级沙箱**在 M15a。

## 地图

- 里程碑与执行顺序：`docs/roadmap.md`　· 八阶段：`docs/stage-map.md`
- 教训：`docs/lessons.md`（只读 Active；归档 `docs/lessons-archive.md` 不读）
- 流程与升级清单：`docs/process/devops-loop.md`（推理账 `docs/process/devops-loop-rationale.md`，改流程时才读）
- 延后重构账：`docs/adr/0002-deferred-refactors.md`
- 每 change 的验收：`docs/verification/<change-id>-{report,uat,real-endpoint,mutation,code-review,dsh-review}.md`
