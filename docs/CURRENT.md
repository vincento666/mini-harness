# 当前状态

**更新：2026-10-27**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` = **`46ce2d2`**（merge `change/h2-streaming-and-event-echo`），tag `m1`–`m9` 都在；H1 / H2 分支已删除。
- **H1 已合入并归档**：40/40 task；归档在 `openspec/changes/archive/2026-10-27-h1-host-session-api`。主规格新建 `host-api`，`cli` / `fences` delta 已 sync。GLOSSARY / roadmap / stage-map 的 K/R/S 分层口径已 cherry-pick（`9af5d3d`、`ad60a9d`）。
- **H2 已合入并归档**：全部 task 勾完；真实端点 S1–S4、人跑 UAT S1–S5、变异四条、Learning Gate 全过。归档在 `openspec/changes/archive/2026-10-28-h2-streaming-and-event-echo`；主规格 `provider` / `host-api` 已 sync。
- **P0 诊断完成**：`docs/verification/p0-budget-reading-diagnostic-2026-10-27.md`。当前 main 的 W1 四次遮蔽均下降、W2 未触发溢出；**不按旧 20 个 task 原样 apply**，需重新确认是否还有可复现症状。
- **唯一未实现的修复分支**：`change/fix-post-compaction-budget-reading`（20 个 task 全未勾，只有 proposal / design / spec / tasks；不实现、不归档）。
- 已合并但分支还没删的：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。
- `openspec validate --all --strict`：**13 份主规格、0 个活动 change，0 失败**（2026-10-28 H2 归档后实测）。
- 门禁（H2 合并到 `main` 后实测）：`522 passed / 8 skipped`、`TOTAL 2696 语句 / 138 未覆盖 / 95%`；ruff / mypy 全绿。

## 下一步

1. **M10**：立 `m10-tool-pipeline-and-concurrency`，第一个切片是**压缩参数可配置**（`threshold/headroom/retain_ratio/retain_tokens`，默认行为不变、进 `session/start`、replay 取回），再做六段管线、并发与结果剪枝。
2. **P0**：`fix-post-compaction-budget-reading` 先不 apply——诊断（W1/W2）没有复现「遮蔽后 tokens 后 > 前」；要么补一次能稳定触发溢出的真实端点样本再决定是否修，要么把它降级为未复现的历史缺陷并记账。
3. **M10 / M11 / M12 / M13 / M14 / M14a / M14b / M14c / M15a / MEM1**：按 `docs/roadmap.md` 的顺序；M10 的第一个切片是**压缩参数可配置**（`threshold/headroom/retain_ratio/retain_tokens`，默认行为不变、进 `session/start`、replay 取回），再做六段管线、并发与结果剪枝。M14 含 CLI 与 host 的斜杠命令、技能清单注入与正文按需加载；M14a–c 是 M14 之后的三小步（工作区契约 / 上下文经济与计量 / 个人助理 UX 工具）；M15a 是无人值守壳的硬前置；MEM1 是最小记忆。

## 开放缺口（按严重度）

- **P0 预算读数未复现**：`budget_reading` 仍无「摘要之后」的 seq 界，代码路径在；但 2026-10-27 的 W1/W2 真实端点诊断没有复现「遮蔽后 tokens 后 > 前」，W2 也没触发溢出。先不按旧 20 task apply；要么补稳定复现样本，要么降级为未复现的历史缺陷。诊断见 `docs/verification/p0-budget-reading-diagnostic-2026-10-27.md`。
- **UI 服务端 allowlist / 投影暂缓**：H2 保持日志逐行镜像 + 客户端过滤；公网/多客户端/事件词表变大时再按 ADR-0002 的最小 MVP 判，现在不实现。
- **`SESSION_BUSY` 的状态码自相矛盾（H1 spec）**：错误表写 409，`/messages` 队满的场景与 task 4.3 写 429；实现按 429 归档，spec 表仍写 409，留到 H2 或后续 spec 修正时裁决。
- **H2 已归档**：`h2-streaming-and-event-echo` 全部 task 勾完；真实端点 S1–S4、UAT S1–S5（人跑）、变异四条、Learning Gate 都过。归档在 `openspec/changes/archive/2026-10-28-h2-streaming-and-event-echo`；主规格 `provider` / `host-api` 已 sync。分支 `change/h2-streaming-and-event-echo`（tip `ed07c8d`）**尚未合入 `main`**。
- **没有 resume / 格式迁移 / session index**：M11。
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

