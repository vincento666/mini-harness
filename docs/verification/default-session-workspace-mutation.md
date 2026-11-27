# default-session-workspace — 变异记录

**状态**：全部被现有判据杀死（2026-11-27）。每个变异注入后只跑相关判据（`tests/test_default_workspace.py`），
回滚后复跑全绿。

| 变异 | 注入点 | 杀死它的判据 | 观察 |
|---|---|---|---|
| M1 默认目录拼接漏 `session_id` | `assembly.default_workspace` 返回 `home/workspaces` | `test_default_workspace_is_the_session_directory` | 期望 `<home>/workspaces/<sid>`，实际共享目录 |
| M2 发现根误锚会话工作区 | `assembly` 的 `discovery_workspace = workspace` | `test_discovery_root_stays_at_the_startup_directory` | 项目里 `.minihns/skills/demo` 的技能清单变空、`discovery_workspace` 断言不等 |
| M3 resume 静默落到默认目录 | `_resolve_workspace` 删掉「读日志」分支 | `test_resume_restores_an_explicit_workspace_from_the_log` | 首场用**显式不同**工作区，恢复后落回默认路径 |
| M4 显式 `--workspace` 被默认逻辑覆盖 | `_resolve_workspace` 删掉显式分支 | `test_explicit_workspace_keeps_the_old_semantics`（连带 `test_resume_prefers_the_explicit_workspace`） | 显式目录不生效 |
| M5 创建失败被吞（降级 cwd） | `mkdir` 的 `OSError` 分支返回 `Path.cwd()` | `test_creation_failure_is_an_argument_error_without_a_log` | 期望退出码 2 + `INVALID_ARGUMENT`，实际 0 |
| M6 工作区路径写上 stdout | `cli/main.py` 去掉 `file=sys.stderr` | `test_default_mode_keeps_products_out_of_the_startup_directory` | stdout 混进工作区路径 |

## 教训

- **M3 第一版存活**：首场用的是默认工作区，而默认路径恰好等于 `<MINIHNS_HOME>/workspaces/<sid>`，
  「不读日志、直接按 id 推默认路径」照样得到同一个目录。补一条首场用**显式不同**工作区的 resume 判据
  才把「读日志」这一步钉死。判据要能区分「真的读了」与「碰巧算对了」。
- **M2 第一次注入没生效**：`ruff format` 改写过目标块，脚本没加 `assert` 就静默 no-op，测试自然全绿。
  变异脚本必须断言目标文本存在。
- 变异回滚用 `git checkout --` 会冲掉未提交的实现（本 change 踩了一次，重放实现后改为**先提交再变异**）。
