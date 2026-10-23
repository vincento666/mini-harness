# `fix-chat-screen-feedback` 的变异测试一轮（tasks 5.3）

基线 `a6c9a99`（`src/mini_harness/cli/main.py` 与 `6919bbd` 逐字节相同）。14 条变异，全部打在 `src/mini_harness/cli/main.py` 的单处，逐条施加 → 跑判据 → 按字节还原并比对。脚手架 `.tmp/mutation/run_mutants.py`（scratch，不进测试套件），原始输出 `.tmp/mutation/run.log` 与 `.tmp/mutation/full_pass.log`。

**结论：14 条全部被杀死，无存活、无 dud。** 本轮没有需要补的判据。

## 14 条变异与杀掉它们的判据

| # | 改法 | 变红的判据 |
| --- | --- | --- |
| M1 | 悬空冒号回来：`detail` 为空也打 `code: ` | `test_ctrl_c_in_a_serve_subprocess_exits_with_five_without_a_dangling_colon` |
| M2 | 不再要求 `code` 与 `reason` 不同 → 溢出那一行把停止理由打两遍 | `test_the_overflow_segment_note_carries_the_detail_once` |
| M3 | `ABORTED` 搬回「不打」那一半（塞进 `_SEGMENT_NOTE_SUPPRESSED`） | `test_ctrl_c_mid_segment_prints_the_aborted_note` |
| M4 | 空正文照打（去掉 `content.strip()` 那道闸） | `test_tool_only_turns_leave_no_blank_lines` |
| M5 | 提示符改用 `print`（自带换行） | 六条：`test_stdout_carries_only_model_reply_text_and_the_prompt`、`test_a_segments_summary_never_appears_on_stdout`、`test_the_prompt_does_not_carry_its_own_newline`、`test_tool_only_turns_leave_no_blank_lines`、`test_ctrl_c_mid_segment_prints_the_aborted_note`、`test_ctrl_c_at_the_prompt_ends_the_session_without_traceback` |
| M6 | 提示符打出去但不 `flush`（管道上屏幕上还没有它） | `test_ctrl_c_mid_segment_prints_the_aborted_note`、`test_ctrl_c_at_the_prompt_ends_the_session_without_traceback` |
| M7 | session id 打到 stdout | 五条，含 `test_chat_prints_the_session_id_on_stderr` 与三条 stdout 投影判据 |
| M8 | 溢出那一行丢掉日志里的 `detail`（换成空串） | `test_a_provider_failed_segment_says_so_on_stderr`、`test_the_overflow_segment_note_carries_the_detail_once` |
| M9 | 段收尾不带造成它的失败结果的 `code` | `test_a_provider_failed_segment_says_so_on_stderr`、`test_a_fence_denied_segment_says_so_on_stderr` |
| M10 | 连续溢出只记上一个理由、不记「这一句说过没有」 | `test_consecutive_overflows_say_the_session_cannot_come_down`（恰一次 → 两段各说一次） |
| M11 | 不查上一个段的收尾理由（任何溢出都说那一行） | `test_a_single_overflow_does_not_say_the_session_cannot_come_down` |
| M12 | 「降不下去」那一行打到 stdout | `test_consecutive_overflows_say_the_session_cannot_come_down`（stderr 上那一行消失） |
| M13 | 会话收尾不换 `_suppress_sigint`（收尾缝隙里没人接） | `test_ctrl_c_at_the_prompt_ends_the_session_without_traceback` |
| M14 | `_chat` 把旧 SIGINT 处理器换回去（design D7 说不要换的那一条） | 同上 |

M13 与 M14 各只被一条判据杀死，而那条判据正是本轮最难稳定的一条（1.6：提示符上取消不留 traceback）。这两条是本轮最值钱的：它们证明 2.7 的实现形状不是可有可无的——换处理器与收尾不换处理器都会让同一判据变红。

## 定向轮与全量轮差多少条（L-042 要的数）

14 条跑的是三条 CLI 判据文件（`tests/test_cli_chat.py`、`tests/test_cli_serve.py`、`tests/test_cli_run.py`）。三条代表性变异（M1、M3、M13）改跑**全量**对照：红数与定向轮**相同**（各 1 条，且是同一条判据），没有跨 seam 的额外红。本轮的差值是 **0 条**——本 change 的实现只动 `cli/main.py`，判据全在 seam ⑥ 的这三份文件里，定向轮的覆盖面与全量轮重合。

## 施加与还原的纪律

- 每条变异的锚点先数一遍（必须恰出现一次），施加后跑判据，然后**按字节还原并比对**。
- 第一版脚手架用 `read_text` / `write_text`：Windows 的文本模式把 LF 换成 CRLF，还原检查当场报「还原失败」，工作树里 `cli/main.py` 的行尾被整份改掉（`git diff` 只剩 CRLF 警告、内容一行没动）。改用 `read_bytes` / `write_bytes` 后重跑，14 条全部还原干净；`git status` 在变异轮前后一致。教训记进 `docs/lessons.md` 的 L-019。
- 判据跑的是 `python -m pytest`（不套 `coverage run`）：seam ⑥ 的子进程自己会写 partial，门禁那三步（`coverage erase` 起头）不受影响。

## 还原后的基线确认

四道门禁与 `openspec validate`：见 `openspec/changes/fix-chat-screen-feedback/tasks.md` 5.3 那一行记录的数字。
