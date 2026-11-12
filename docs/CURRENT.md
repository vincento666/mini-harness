# 当前状态

**更新：2026-11-09**。以 `git status --short` 与 `git log --oneline -3` 为准；本文件只写「现在」，历史在 `docs/verification/` 与 `openspec/changes/archive/`。

## 现在

- `main` 以 `git log -1` 为准（最近 H2 合并提交 `46ce2d2`，之后是状态/计划文档），tag `m1`–`m9` 都在；H1 / H2 分支已删除。
- **H1 已合入并归档**：40/40 task；归档在 `openspec/changes/archive/2026-10-27-h1-host-session-api`。主规格新建 `host-api`，`cli` / `fences` delta 已 sync。GLOSSARY / roadmap / stage-map 的 K/R/S 分层口径已 cherry-pick（`9af5d3d`、`ad60a9d`）。
- **H2 已合入并归档**：全部 task 勾完；真实端点 S1–S4、人跑 UAT S1–S5、变异四条、Learning Gate 全过。归档在 `openspec/changes/archive/2026-10-28-h2-streaming-and-event-echo`；主规格 `provider` / `host-api` 已 sync。
- **M11 已合入并归档**：`m11-storage-resume-and-projection-cache` 23/23，`main` 合并 `c9c62ee`；EventLog 续写、chat/Host resume、schema 相邻迁移、Host session index、fold 缓存、投影三态、chat 工具事件行与 Host observer 已落成；主规格 4 个已 sync。归档在 `openspec/changes/archive/2026-11-05-m11-storage-resume-and-projection-cache`。
- **M12 已合入并归档**：合并 `4ff7226`；`m12-subagent-delegation` 18/18 task；`subagent` 工具（spawn）、独立子会话与子日志、深度/容量结果词、子会话审批不可用、同批真并发、父取消级联、Host 父子字段、委派声明都已落成；真实端点 S1–S4、人跑 UAT S1–S5、变异 3+1 条、DSH parity review 全过。归档在 `openspec/changes/archive/2026-11-09-m12-subagent-delegation`；主规格 `subagent-delegation` 新建，`host-api` / `tool-pipeline` 已 sync。UAT 期间发现并修复了 chat 的 SIGINT 唤醒缺陷（`2cb1234`）。子代理 preset 与 `subagent.tools` 的去留见 roadmap 的「子代理 preset 与工具来源」。
- **`subagent-preset` 已合入并归档**：合并 `b9bf3bd`；14/14 task；`[subagent]` preset / 白名单 / 编译进子 registry、删除 `subagent.tools`；真实端点、UAT（agent 代跑，用户指示）、变异、Learning 全过。归档在 `openspec/changes/archive/2026-11-10-subagent-preset`；主规格 `subagent-delegation` / `config-layering` 已 sync。
- **`skill-slash-commands`（M14 的补丁）已合入并归档**（合并 `4a9fe04`）：直接 `/技能名` 与 `/skill 技能名` 等价、host `GET /commands?session_id=` 列会话技能、`/help` 列技能命令；含渐进式披露与技能执行结果的端到端判据；UAT agent 代跑。
- **`skill-command-arguments`（M14 补丁的补丁）已合入并归档**（合并 `4a9fe04`）：`/<技能名> 指令` 把正文 + 指令展开成消息并开段，host 返回 202（忙时排队）；不含指令的 `/<技能名>` 仍只打印正文。含真实端点、变异 3 条、UAT（agent 代跑）、Learning。
- **`skill-invocation-policy` 已合入并归档**（合并 `78ddaba`）：策略位（模型/人机两面）、发现完整性（`skills_incomplete` + 头部警告）、preset 目录层（`skill_dirs` 同名覆盖）、`/<技能名>` 执行与 `/skill` 查看；真实端点、UAT（agent 代跑）、变异、对齐复核全过。
- **`skill-catalog-live` 已合入并归档**（合并 `9b0f8c1`）：目录改为持久 user 消息、每 turn 指纹替换、不完整重试/恢复、清空退休、压缩重建、子会话重放 preset 层；真实端点（加/删/权限失败三场）、UAT（agent 代跑）、变异 4 条、对齐复核全过。
- **`skill-providers`（任务完成，门禁红未归档）**：分支 `change/skill-providers`。1.1–4.4 与 5.1–5.6 全部完成（provider/注册表、装配与目录、命令面与 `skill` 工具、preset `skills` 表、真实端点两场、UAT 四场（agent 代跑）、变异 9 条、两轴审查、对齐复核、ADR-0035/0040）。两处曾待裁决的已裁：D7 保留裸 env 回落；摘要加 `Skill.source`（`session/start` 与目录消息都写层名，指纹随之含 `source`）。门禁：ruff / `mypy --strict` / `openspec validate --all --strict`（21 项）全绿；全量 663 passed / 6 skipped / 1 failed（macOS 大小写折叠，既知红）。**覆盖率门禁是红的**：整轮 `coverage run -m pytest` → `combine` → `report` 79%（3761 语句 / 793 未覆盖），手动合并全部 233 份 partial 仍是 79%（不是 `combine` 丢数据），而同文件单独跑 `skills.py` 是 96%——矛盾未解，归档前必须查清。流程欠账（两轴顺序、两处打包超数、提交信息缺门禁行、UAT 代跑）记在 ADR-0002 的「`skill-providers` 的流程欠账」。
- **P0 诊断完成**：`docs/verification/p0-budget-reading-diagnostic-2026-10-27.md`。当前 main 的 W1 四次遮蔽均下降、W2 未触发溢出；**不按旧 20 个 task 原样 apply**，需重新确认是否还有可复现症状。
- **唯一未实现的修复分支**：`change/fix-post-compaction-budget-reading`（20 个 task 全未勾，只有 proposal / design / spec / tasks；不实现、不归档）。
- 已合并但分支还没删的：`change/fix-small-window-compaction-dead-zone`、`change/add-key-driven-default-provider`、`change/fix-chat-screen-feedback`、`change/add-platform-facts-to-protected-header`、`change/fix-compaction-and-context-overflow`。
- `openspec validate --all --strict`：**19 份主规格、0 个活动 change，0 失败**（2026-11-09 M12 归档后实测）。
- 门禁（M12 委派）：`587 passed / 6 skipped / 1 failed`（macOS 上的大小写折叠用例，见 `change/fix-case-insensitive-path-keys` 的 proposal）、`TOTAL 3159 语句 / 151 未覆盖 / 95%`；ruff / mypy 全绿。

## 下一步

1. **M12 与 `subagent-preset` 已合入 `main`**（`4ff7226` / `b9bf3bd`）：归档与规格 sync 完成，`openspec validate` 19/19。**M14（技能 / 命令）已合入并归档（合并 `1b6e831`，18/18）；下一步 M14a 工作区契约 → M14b → M14c（plan）→ M13 目标**（2026-11-10 裁决：M14 与 plan 提前，goal 后置）。
2. **M10 已完成并合入**：第一切片 `m10-compaction-parameters` 合入 `aa48ae7`；余下 `m10-tool-pipeline-and-concurrency` 26/26 task，`main` 合并 `856d368`，归档在 `openspec/changes/archive/2026-10-29-m10-tool-pipeline-and-concurrency`。六段管线、并发类别/barrier、CommandRunner、read 50 KiB/2000 字符窗口（不 spill）、bash/搜索 spill 都已落成。
3. **思考模式与预算**：M10 之后、M11/M12 之前立 `reasoning-mode-and-budget`；durable `model/response` 用有序 content blocks（reasoning/text/tool-call）而不是单字段、实时 `reasoning/delta` ephemeral、reasoning tokens 属 output 不重复计；DSH 对照与暂缓项见 `docs/reference/reasoning-mode.md`。
4. **P0**：`fix-post-compaction-budget-reading` 先不 apply——诊断（W1/W2）没有复现「遮蔽后 tokens 后 > 前」；要么补一次能稳定触发溢出的真实端点样本再决定是否修，要么把它降级为未复现的历史缺陷并记账。
5. **M14a / M14b / M14c / M13 / M15a / MEM1**：按 `docs/roadmap.md` 的顺序（2026-11-10 起 M14 与 plan 在 goal 之前；M14 已归档）；M14 含 CLI 与 host 的斜杠命令、技能清单注入与正文按需加载；M14a–c 是 M14 之后的三小步（工作区契约 / 上下文经济与计量 / 个人助理 UX 工具）；M15a 是无人值守壳的硬前置；MEM1 是最小记忆。

## 开放缺口（按严重度）

- **P0 预算读数未复现**：`budget_reading` 仍无「摘要之后」的 seq 界，代码路径在；但 2026-10-27 的 W1/W2 真实端点诊断没有复现「遮蔽后 tokens 后 > 前」，W2 也没触发溢出。先不按旧 20 task apply；要么补稳定复现样本，要么降级为未复现的历史缺陷。诊断见 `docs/verification/p0-budget-reading-diagnostic-2026-10-27.md`。
- **UI 服务端 allowlist / 投影暂缓**：H2 保持日志逐行镜像 + 客户端过滤；公网/多客户端/事件词表变大时再按 ADR-0002 的最小 MVP 判，现在不实现。
- **`SESSION_BUSY` 的状态码自相矛盾（H1 spec）**：错误表写 409，`/messages` 队满的场景与 task 4.3 写 429；实现按 429 归档，spec 表仍写 409，留到 H2 或后续 spec 修正时裁决。
- **H2 已合入并归档**：全部 task 勾完；真实端点 S1–S4、UAT S1–S5（人跑）、变异四条、Learning Gate 全过。归档在 `openspec/changes/archive/2026-10-28-h2-streaming-and-event-echo`；主规格 `provider` / `host-api` 已 sync。
- **没有 resume / 格式迁移 / session index**：M11。
- **没有技能 / 斜杠命令 / 渐进披露**：M14；CLI 与 host 要同一份命令面。
- **没有工作区契约 / 结果剪枝计量 / 助理 UX 工具**：M14a / M14b / M14c；非核心，但缺了个人助理不像。
- **没有记忆**：MEM1（项目/用户 `MEMORY.md` + `memory` 工具）；MEM2 定时巩固在壳后。
- **委派的三处语义原语未对齐**：子级审批仍继承父的 `approval` 模式 + 门 `UNAVAILABLE`（DSH 把进程内子级钉成 `never`）；没有「沙箱升级才问人」的阶梯；工具表只是组合过滤、没有数据边界授权；子级 preset 与异步完成通知都写了触发条件；preset 与 `subagent.tools` 已定案（ADR-0037）并落成（`change/subagent-preset`：`[subagent]` preset + 白名单、删除 `tools`，待四项收尾），见 roadmap 的「子代理 preset 与工具来源」。见 `docs/verification/m12-subagent-delegation-dsh-review.md` 的「语义原语的差距」。
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
- M12 的子代理与并发底稿：`docs/reference/subagents.md`；DSH 侧的系统调研：[`docs/reference/dsh-subagent-design.md`](reference/dsh-subagent-design.md)
- 四层 / 段与回合 / 控制面说明：`docs/reference/runtime-layers-and-control-plane.md`
- E2 组件接缝规划：`docs/reference/e2-component-seams.md`
- G 轨服务化运行时：`docs/reference/g-track-service-runtime.md`
- DSH 逐支柱对照：`docs/dsh-alignment.md`（基线 `m3`，形状仍有效）
- 延后重构账：`docs/adr/0002-deferred-refactors.md`（末尾有 2026-10-26 的 M10 分流）
- 每 change 的验收：`docs/verification/<change-id>-{manual,real-endpoint,uat,mutation}.md`
- 本轮的决策：ADR-0031（宿主）、0032（流式 ephemeral）、0033（并发策略）、0034（评测支撑轨）、0035（fork / 插件容器范围）


