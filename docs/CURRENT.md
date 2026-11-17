# 当前状态

**更新：2026-11-17**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/CURRENT-history.md`、`docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` 以 `git log -1` 为准；最近一次里程碑合并是 `m14c`（`09caa26`，2026-11-17 07:55）。
- **门禁实测（`m14b` 收尾，2026-11-16）**：ruff / `mypy --strict` 绿；**701 passed / 6 skipped / 1 failed**（`test_file_edit.py` 的 macOS 大小写折叠，既知红）；覆盖率 **95%（4070 / 206）**；`openspec validate --all --strict` **22/22**。`m14c` 收尾的读数是 728 passed（见「下一步」），两次读数未复核一致性。
- **无活动 change**。`m14b-context-economy-and-metering` 已归档（`2026-11-16-m14b-context-economy-and-metering`）并合入；主规格 `tool-pipeline` +2 条、新建 `usage-metering` 3 条。
- 已合并但未删的分支：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。

## 下一步

0. **本周冲刺（2026-W47）**：`docs/plan-2026-W47.md`；M14c 已完成，下一项 M13。

1. **M14c 个人助理 UX 工具——已完成**（`2026-11-16-m14c-personal-assistant-tools`）：todo/plan/ask_user/present、投影框架与快照/SSE；23 份主规格 validate 绿；全量 728 passed / 6 skipped（macOS 上 1 条大小写折叠用例失败，属平台假设）。

2. **M13 目标轮次**：按 `docs/process/devops-loop.md` §2 先做阶段进入六问，再按官方一手资料调研 DSH，然后 propose；plan 在 goal 之前（2026-11-10 裁决）。M13 之后是 M15a 进程收容 → MEM1 基础记忆。
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
