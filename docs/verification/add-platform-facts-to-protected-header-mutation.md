# 变异测试一轮：`add-platform-facts-to-protected-header`（tasks 6.3）

**判据**：每个变异至少被一条判据杀死；存活的算覆盖缺口，补一条能杀死它的判据。变异必须改变可观察行为，语义等价的改法不算。

## 跑法

脚手架 `.tmp/mutation/run_platform_mutants.py`（一次性工具，不进仓库）：逐个把源码改成变异体 → 跑该变异点对应的**定向判据** → 用改前读到的原始**字节**写回 → 报表 → 最后 `git status --porcelain` 确认工作树只剩那四个未跟踪的 `docs/tools/` 文件。

定向跑是为了快：九个变异各跑一两个判据文件（`tests/test_context_fold.py` / `tests/test_cli_run.py -k platform` / `tests/test_tool_registry.py` / `tests/test_cli_replay.py`）。**定向之后跑了一次全量**确认回到基线：430 passed / 5 skipped / **1 failed**——那一条是已知的 Windows Ctrl-C 偶发（`test_ctrl_c_at_the_prompt_ends_the_session_without_traceback`，单独复跑 1 passed，`docs/lessons.md` 的 L-055 记的就是它），与本 change 无关。

## 九个变异

| # | 变异：把哪儿改坏 | 结果 | 杀它的判据 |
|---|---|---|---|
| M1 | 运行环境块挪到追加文本**之后**（位置错） | KILLED | `test_the_header_carries_a_runtime_environment_block` |
| M2 | `_start_facts` 的**兜底**分支（日志里根本没有 `session/start`）返回一个猜的平台 | KILLED | `test_fold_puts_the_system_prompt_first_and_keeps_the_body_in_order`、`test_header_cannot_be_replaced_by_conversation_content` |
| M3 | 建议改回读**折叠时所在机器**的 `sys.platform`，不看日志里的 `shell` | KILLED | `test_the_advice_follows_the_recorded_platform` |
| M4 | `fold` 读了 `platform` 却不把它传给头部 | KILLED | `test_the_header_carries_a_runtime_environment_block` 等三条 |
| M5 | 抹掉「命令输出按 UTF-8 解码」那句说明 | KILLED | `test_the_environment_block_says_how_command_output_is_decoded` |
| M6 | CLI 自己判平台、写死一个错的 `shell`（`"bash"`） | KILLED | `test_session_start_records_the_platform_facts`、`test_the_three_entries_record_the_same_platform_facts` |
| M7 | `glob` 的描述去掉「什么时候用我」那句 | KILLED | `test_the_native_file_tools_say_they_are_the_way_to_do_it` |
| M8 | 没有事实时也拼一块**空**的运行环境块 | KILLED | `test_a_log_without_the_platform_facts_keeps_the_old_header` 等三条 |
| M9 | `session/start` 里没有 `platform` 时**填一个猜测值** | KILLED | `test_a_log_without_the_platform_facts_keeps_the_old_header`、`test_replay_of_a_log_without_the_platform_facts_still_verifies` |

**9/9 被杀，0 存活，没有要补的判据。**

## 两条读变异时记下的事实

1. **M2 与 M9 是两个不同的口子。** 最初只写了 M2（兜底分支），它杀掉的是排序类判据——因为 `session/start` 存在时走的是另一条 return。真正危险的是「`session/start` 在、但里面没有 `platform`」这条最常走的路，那要 M9 才压到；它一压，正好是那两条「旧日志不变」的判据红。**同一处逻辑的多个 return 各是一个变异口，不能只改一个就以为覆盖了。**
2. **M3 能被杀，靠的是判据不看本机平台。** 判据在一台 Windows 机器上跑一份「记着 `posix`」的日志，如果实现读 `process.platform`，它就会吐出 Windows 建议——这条判据在哪个平台上跑都同样有效，正是 ADR-0029 那条「建议只由日志推出」的可测形态。

## 还原纪律

- 每个变异改的都是**一个**文件的字节；写回用的是改前读到的原始 `bytes`，不经过文本模式，不碰行尾（`docs/lessons.md` L-019 记的就是文本模式把 LF 换成 CRLF 那一课）。
- 全部跑完后 `git status --porcelain` 只剩四个未跟踪的 `docs/tools/` 文件——没有把本轮改动一起回滚。
