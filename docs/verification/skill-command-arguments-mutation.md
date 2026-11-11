# skill-command-arguments 变异测试

**日期**：2026-11-11。每个变异改源码、跑指定判据、记录红，再从 `/tmp` 备份还原（本轮不用 `git checkout`，避免把未提交的改动一起回滚）。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 展开时不带指令 | `skill_content` 恒返回 XML，不拼 `instruction` | `test_chat_skill_command_with_an_instruction_opens_a_segment` | 红：`user/message` 里没有指令 |
| M2 | chat 不展开 | `if skill is not None and arguments.strip()` 恒假 | 同上 | 红：没有 `user/message`、没有新段 |
| M3 | host 不走 202 | 202 分支恒假，落回 `run_command` 的 200 | `test_a_skill_command_with_instruction_queues_while_running` | 红：返回 200 而不是 202 |

**基线**：还原后 `tests/test_skills.py` + `tests/test_cli_commands.py` 23 passed。

## Learning Gate

**NO-PROMOTION**：收件箱 71 条（先消化）。本轮信号「命令 + 参数要么展开成消息、要么是 handler 错误，不能静默丢参数」已写进 design D1 与规格 Scenario，不新增收件箱条目。
