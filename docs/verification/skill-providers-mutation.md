# skill-providers 变异测试

**日期**：2026-11-12。每个变异改一处源码、跑指定判据、记录红，再从备份还原并用 `git status` 复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 近层不占地 | `snapshot` 先遍历全局层再遍历层 | `test_the_near_layer_wins_by_name_across_ranks` | 红：胜出的是全局那份（rank 100 而非 600） |
| M2 | 正文一律从全局层读 | `get` 里 `provider.get` 换成 `self._global.get` | `test_the_near_layer_wins_by_name_across_ranks`、`test_get_routes_to_the_provider_that_owns_the_skill` | 红：拿到全局正文 |
| M3 | 完整性位恒真 | `complete and view.complete` 换成 `complete and True` | `test_incomplete_layers_make_the_snapshot_incomplete` | 红：层不完整快照仍报完整 |
| M4 | 无注册表不回落 | `skills_view` 的 `else tuple(fallback)` 换成 `else ()` | `test_without_a_registry_the_command_face_uses_the_assembly_snapshot` | 首轮**存活**：原判据只覆盖 `skill` 工具自己那条回落，命令面这条没判据；补判据后红 |
| M5 | 工具绕开注册表 | `skill_content_body(skill, body)` 换成 `skill_content(skill)`（就地读文件） | `test_the_skill_tool_reads_the_body_through_the_registry` | 红：正文变成文件里的 |
| M6 | 未知 kind 放行 | `if kind not in SKILL_KINDS` 换成 `if False` | `test_a_skills_table_needs_a_known_kind_and_string_dirs` | 红：`kind = "remote"` 不再退出码 2 |
| M7 | 子会话不挂层 | `if directories and child_skill_registry is not None` 换成 `if False` | `test_a_preset_skill_layer_reaches_the_child_only` | 红：子会话目录没有 `extra`、`tdd` 仍是全局那份 |
| M8 | preset 层挂错对象 | spawn 时把层就地写进父注册表的 `_scopes` | `test_a_preset_skill_layer_reaches_the_child_only` | 首轮**存活**：原判据只看父 `session/start` 快照（spawn 前已写），看不到之后的变化；补「父目录只有一条、不含 `extra`」后红 |
| M9 | 命令面退回装配快照 | `skills = skills_view(...)` 换成 `prepared.settings.skills` | `test_the_chat_command_face_reads_the_live_registry` | 红：中途新建的技能 `/skills` 看不到 |

**基线**：还原后 `tests/test_skill_providers.py` + `tests/test_skills.py` 47 passed，`git status` 干净。

## Learning Gate

**NO-PROMOTION**：`docs/lessons.md` 共 71 条、其中 28 条仍在 `inbox`，先消化再收。本轮唯一新信号是「父会话的判据要落在 spawn **之后**的消息上，不能只看 `session/start`」，已写进 M8 的判据本身（父目录断言），不新增收件箱条目。
