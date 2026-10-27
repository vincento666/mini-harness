# 当前状态

**更新：2026-10-27**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` = **`9b3a5bf`**（merge `add-key-driven-default-provider`），tag `m1`–`m9` 都在。
- **H1 已归档**：`change/h1-host-session-api` 40/40 task；归档提交 `be57f40`，归档在 `openspec/changes/archive/2026-10-27-h1-host-session-api`。主规格新建 `host-api`，`cli` / `fences` delta 已 sync；**合并到 `main` 仍待人批**。GLOSSARY / roadmap / stage-map 的 K/R/S 分层口径已 cherry-pick（`9af5d3d`、`ad60a9d`）。
- **唯一未合并的修复分支**：`change/fix-post-compaction-budget-reading`（从 `fix-small-window-compaction-dead-zone` 的 tip 起，20 个 task 全未勾，只有 proposal / design / spec / tasks）。
- 已合并但分支还没删的：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。
- `openspec validate --all --strict`：**13 份主规格、0 个活动 change，0 失败**（2026-10-27 归档后实测）。
- 门禁（源码基线 `9c1868c`；归档前重跑）：`492 passed / 8 skipped`、`TOTAL 2523 语句 / 126 未覆盖 / 95%`；ruff / mypy 全绿。全量首跑遇到一次 Windows Ctrl-C 已知 flake（同一用例在 main 上也复现过），重跑绿。变异五条全部被杀（`docs/verification/h1-host-session-api-mutation.md`）。真实端点（deepseek）已跑通（`docs/verification/h1-host-session-api-real-endpoint.md`）。

## 下一步

1. **合 H1（人批）**：`change/h1-host-session-api` 已归档、四道门禁/真实端点/UAT/变异/Learning Gate 都过；`main` 仍是 `9b3a5bf`。批准后把代码与规格一次合入 `main`，再删 H1 分支和 `docs-krs-glossary` worktree/branch。
2. **P0**：合 `fix-post-compaction-budget-reading`。前置是 `docs/verification/fix-post-compaction-budget-reading-uat.md` 的观察表填完（ADR-0025），并补一场「溢出一次之后，下一句正常问题能跑完」。它的 proposal 预留 ADR-0029，已与 `main` 的 0027–0030 冲突；合并时顺延到 0036（0031–0035 归本轮的宿主 / 流式 / 并发 / 评测 / 范围决策）。
3. **H2**：H1 合入 `main` 之后立刻立 `h2-streaming-and-event-echo`，再做 M10。
4. **M10 / M11 / M12 / M14 / M14a / M14b / M14c / M15a / MEM1**：按 `docs/roadmap.md` 的顺序；M14 含 CLI 与 host 的斜杠命令、技能清单注入与正文按需加载；M14a–c 是 M14 之后的三小步（工作区契约 / 上下文经济与计量 / 个人助理 UX 工具）；M15a 是无人值守壳的硬前置；MEM1 是最小记忆。

## 开放缺口（按严重度）

- **压缩后读数降不下来**：`budget_reading` 的校准被保留尾部里最新那条 `usage` 钉住，真端点上「一次溢出后每段都溢出」。修复分支未合（见上）。
- **H1 合并待人批**：归档、门禁、真实端点、UAT（agent 代跑经用户确认）、变异与 Learning Gate 都已完成；`main` 仍停在 `9b3a5bf`。
- **`SESSION_BUSY` 的状态码自相矛盾（H1 spec）**：错误表写 409，`/messages` 队满的场景与 task 4.3 写 429；实现按 429，等归档前由人裁决是否收窄错误表（本 change 不改已审 spec）。
- **没有 resume / 格式迁移 / session index**：M11。
- **没有流式**：provider 非流式；H2（已定为 H1 之后的下一项）。
- **没有技能 / 斜杠命令 / 渐进披露**：M14；CLI 与 host 要同一份命令面。
- **没有工作区契约 / 结果剪枝计量 / 助理 UX 工具**：M14a / M14b / M14c；非核心，但缺了个人助理不像。
- **没有记忆**：MEM1（项目/用户 `MEMORY.md` + `memory` 工具）；MEM2 定时巩固在壳后。
- **没有子代理并发**：M12；`maxActiveSubagents = 8`、`maxDepth = 1`、同批 `subagent` 真并发。
- **没有 OS 级沙箱**：M15a 进程收容是无人值守壳的硬前置；M15b 文件写拒绝可壳后。
- **fork 与插件容器**：暂不做，见 ADR-0035；图上两项与 roadmap 的差异已写明。
- **文档漂移已修**：`CURRENT` 的重复段、过期的“未归档”、ADR 计数 23 → 实际 30、门禁数字并列，都在 2026-10-26 这一轮清掉；`roadmap` 的重复判据段也已合并。

## 地图

- 里程碑与执行顺序：`docs/roadmap.md`
- 八阶段对照：`docs/stage-map.md`
- 评测骨架：`scripts/eval/README.md`（支撑轨，不进完成判据）
- M10 的并发 / 上下文底稿：`docs/reference/tool-concurrency-and-context-economy.md`
- H2 的流式 / 事件回显底稿：`docs/reference/host-streaming.md`
- H1 的安全威胁模型：`docs/reference/host-security-threat-model.md`
- M14 的技能 / 斜杠命令底稿：`docs/reference/skills-and-commands.md`
- MEM1 / MEM2 的记忆底稿：`docs/reference/memory.md`
- M12 的子代理与并发底稿：`docs/reference/subagents.md`
- 四层 / 段与回合 / 控制面说明：`docs/reference/runtime-layers-and-control-plane.md`
- E2 组件接缝规划：`docs/reference/e2-component-seams.md`
- G 轨服务化运行时：`docs/reference/g-track-service-runtime.md`
- DSH 逐支柱对照：`docs/dsh-alignment.md`（基线 `m3`，形状仍有效）
- 延后重构账：`docs/adr/0002-deferred-refactors.md`（末尾有 2026-10-26 的 M10 分流）
- 每 change 的验收：`docs/verification/<change-id>-{manual,real-endpoint,uat,mutation}.md`
- 本轮的决策：ADR-0031（宿主）、0032（流式 ephemeral）、0033（并发策略）、0034（评测支撑轨）、0035（fork / 插件容器范围）
