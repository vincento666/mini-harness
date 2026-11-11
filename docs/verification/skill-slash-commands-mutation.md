# skill-slash-commands 变异测试

**日期**：2026-11-11。每个变异改源码、跑指定判据、记录红，再 `git checkout` 还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 直接技能名不解析 | `execute_command` 把 `direct` 恒置 `None` | `test_execute_command_supports_a_direct_skill_name`、`test_chat_runs_a_skill_directly` | 红：`/tdd` 变成未知命令 |
| M2 | 技能覆盖内置命令 | 把直接技能分支挪到 `skills` 分支之前 | `test_a_builtin_name_wins_over_a_skill` | 红：`/skills` 去加载了叫 `skills` 的技能 |
| M3 | 清单忽略会话技能 | `GET /commands?session_id=` 不取 `handle.settings.skills` | `test_host_commands_match_the_cli_and_do_not_open_a_segment` | 红：会话清单里没有 `tdd` |

**基线**：还原后 `tests/test_skills.py` + `tests/test_cli_commands.py` 20 passed。

## Learning Gate

**NO-PROMOTION**：收件箱仍 71 条（纪律：先消化）。本轮信号「命令名空间里内置优先、技能名是会话级发现」已写在 `skills` 规格的 Scenario 与 design D1/D3，不新增收件箱条目。
