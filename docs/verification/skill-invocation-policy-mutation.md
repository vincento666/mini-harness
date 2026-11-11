# skill-invocation-policy 变异测试

**日期**：2026-11-11。每个变异改源码、跑指定判据、记录红，再从 `/tmp` 备份还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | `disable-model-invocation` 语义反转 | `model_invocable = model_disabled` | `test_default_policy_is_both_true` | 红：默认技能变成模型不可调 |
| M2 | 命令面不过滤 | `command_catalog` / `direct_skill` / `/skills` 都不看 `user_invocable` | `test_commands_only_see_user_invocable` | 红：`model-only` 出现在命令清单 |
| M3 | preset 层不覆盖 | 合并时 `skill.name in by_name` 就跳过 | `test_merge_skill_layer_overrides_and_adds` | 红：preset 层的同名 `tdd` 没覆盖全局 |

**基线**：还原后 `tests/test_skills.py` + `tests/test_subagent_presets.py` 42 passed。

## Learning Gate

**NO-PROMOTION**：`docs/lessons.md` 收件箱仍 71 条（先消化）。本轮信号「策略位要按语义反转检查默认值」「层合并的顺序要单独判」已写进判据与 ADR-0039，不新增收件箱条目。
