# skill-catalog-live 变异测试

**日期**：2026-11-12。每个变异改源码、跑指定判据、记录红，再从 `/tmp` 备份还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 不比对指纹 | `state.last_digest == digest` 恒假，每 turn 都发 | `test_the_catalog_message_is_injected_once_and_not_repeated` | 红：重复注入 |
| M2 | 只发首次 | 有 `last_digest` 就直接返回 | `test_a_changed_catalog_appends_a_replacement` | 红：新技能不出现 |
| M3 | 不看压缩遮蔽 | `shadowed` 恒假 | `test_a_shadowed_catalog_is_reinjected` | 红：折叠后不重建 |
| M4 | 子会话刷新丢 preset 层 | `child_refresh` 直接返回全局 | `test_a_preset_skill_layer_reaches_the_child_only` | 红：子会话目录没有 preset 技能 |

**基线**：还原后 `tests/test_skill_catalog.py` + `tests/test_skills.py` 43 passed。

## Learning Gate

**NO-PROMOTION**：`docs/lessons.md` 收件箱仍 71 条（先消化）。本轮信号「目录是消息、指纹要含完整性、子会话刷新要重放作用域层」已写进判据与设计，不新增收件箱条目。
