# m14a-workspace-contract 对齐复核

**日期**：2026-11-13。对齐对象：proposal / design / spec（2 条 Requirement、11 个 Scenario）/ tasks 验收 + DSH 十项。DSH 出处为官方一手资料（`deepseek-ai/deepseek-harness` 提交 `47f9438` 的 `packages/context/agent-instructions`），核对过程见 `docs/reference/workspace-contract.md`。

## 提案

| 对照点 | 实现 | 结论 |
|---|---|---|
| Why：模型看不到项目约定 | 每会话注入一条 `source: "workspace-instructions"` 的 user 消息 | aligned |
| What Changes：两个 scope、预算、刷新、与记忆分开 | 全部落地（`contracts.py` + `turn_loop.py`） | aligned |
| 非目标：逐层链 / overlay / `USER.md` / `/contracts` | 未做 | aligned |
| Impact：新增 `contracts.py`、改 `turn_loop.py`、不动 `skills.py` | 一致 | aligned |

## 设计

| 决策 | 实现 | 结论 |
|---|---|---|
| D1 形状与位置 | 持久 `user/message`，`<system-reminder>` 框；不进头部与 `session/start` | aligned |
| D2 两个 scope 与路径 | 用户全局 + 项目根；符号路径；trim 去重 | aligned（显示路径的已知简化见 code-review C2） |
| D3 预算 | 单条 16 KiB；先丢用户全局再截断项目；可见 notice | simplified：DSH 是每链一个 `maxBytes`（默认 64 KiB），mini 只有一个总预算；理由是 mini 只有一个消息装两条链 |
| D4 刷新 | 每 turn 观察 + 指纹；替换 / 移除 / 退休 | simplified：DSH 由第一方 `read`/`write`/`edit` touch 驱动；mini 没有 pre-step hook，沿用目录消息的「每 turn 观察」节奏 |
| D5 记录与回放 | payload 记 `digest` 与 `scopes`；正文只在消息里；replay 不读盘 | aligned |
| D6 子会话与边界 | 子会话各自一份；只读；读失败不启动失败 | aligned |

## 规格（11 个 Scenario）

| Scenario | 判据 | 结论 |
|---|---|---|
| 两份契约都在 | `test_two_contracts_render_global_then_project`、注入 e2e | aligned |
| 只有项目一份 | `test_only_the_project_contract_renders_one_segment` | aligned |
| 两份都没有 | `test_without_any_contract_nothing_is_rendered`、`test_without_files_no_contract_message` | aligned |
| 内容相同只渲染一份 | `test_identical_content_renders_only_the_global_one` | aligned |
| 超预算有可见通知 | `test_over_budget_drops_the_global_segment_before_truncating` | aligned |
| 框架字符被转义 | `test_the_framework_tag_in_content_is_escaped` | aligned |
| 未变不重发 | `test_an_unchanged_contract_is_not_repeated` | aligned |
| 变化追加完整替换 | `test_a_changed_contract_appends_a_replacement` | aligned |
| 文件消失后退休 | `test_removing_both_files_appends_a_removal_notice` | aligned |
| 回放逐点相等 | `test_replay_rebuilds_contract_messages_without_touching_disk` | aligned |
| 记忆不被混入 | `test_the_memory_file_is_not_mixed_in`、`test_the_contract_body_never_enters_session_start` | aligned |

## tasks 验收

1.1–4.1、5.1、5.3、5.4 完成；**5.2 UAT 未跑**（deferred，触发条件：人坐终端跑四场）。归档与合入排在 UAT 之后。

## DSH 十项

| # | 项 | 结论 | 记账 |
|---|---|---|---|
| 1 | 形状 | aligned | 持久 user 消息、`Instructions from:` 分段、`<system-reminder>` 框 |
| 2 | 机制 | simplified | 每 turn 观察代替 touch 驱动；没有 pre-step hook |
| 3 | 语义 | aligned | 丢宽泛再截断、notice 指名路径、空链不加 token、转义 |
| 4 | 不变量 | aligned | 契约是日志消息，fold 从前缀重建；不写文件 |
| 5 | 面 | simplified | 模型面与日志面有；`/contracts` 命令延后 |
| 6 | 失败与降级 | aligned | 缺失是空链、读失败不启动失败、超限按 unavailable |
| 7 | 组合与扩展 | simplified | 只做两步 scope，无逐层链与 overlay |
| 8 | 资源与约束 | aligned | 16 KiB < DSH 64 KiB；单文件 1 MiB |
| 9 | 信任与授权 | aligned | 只读；symlink 风险记账（code-review S4） |
| 10 | 回放与确定性 | aligned | `replay` 逐点相等且不读盘 |

## 结论

提案、设计、规格逐条兑现；十项里 7 aligned、3 simplified（机制、面、组合），都有理由与触发条件。唯一未完成项是 UAT 四场，归档前必须补。
