# 变异测试一轮（`h1-host-session-api`）

**基线**：`492 passed / 8 skipped`，`TOTAL 2523 stmts / 126 missing = 95%`（提交 `9c1868c`；两轴审查后的修正已在内）。
**结果：五个变异全部被杀，没有存活的变异。**

跑法：`.tmp/mut_h1/run.py` 严格串行——应用一处字面替换 → `pytest -q -rf --tb=no` 跑全量 → 还原。五个变异都在已提交的 HEAD 之上跑；跑前 `git status --short` 里没有 `src/` 或 `tests/` 的未提交改动。

**还原的坑**：runner 用 `Path.write_text` 还原，Windows 上把 LF 写成了 CRLF，`git status` 因此仍显示 `M`（结果 JSON 的 `status_after` 是 `M src/...`）。还原后用 `git checkout -- src/mini_harness/cli/host.py src/mini_harness/session/host.py` 回到基线，并重跑 host 判据 `34 passed / 1 skipped`；之后 `git status --short` 只剩 `docs/tools/` 的既有未跟踪脚本。`status_after` 那几行是工具痕迹，不是变异存活。

| 变异 | 改法 | 红几条 | 判据在哪个 seam |
|---|---|---|---|
| M1 | 鉴权跳过：`_guard` 不再检查 Bearer token | 2 | ⑥ |
| M2 | 消息不排队：段进行中直接回 409 | 4 | ① 与 ⑥ |
| M3 | 审批默认批准：门登记 future 后立刻返回 `APPROVED` | 5 | ② 与 ⑥ |
| M4 | snapshot 的 `last_seq` 永远报 `-1` | 2 | ⑥ |
| M5 | DELETE 允许 running：撤掉 `close_session` 的段中检查 | 2 | ⑥ |

## M1（2 红）

- `tests/test_cli_host.py::test_every_host_error_uses_the_envelope`
- `tests/test_cli_host.py::test_host_rejects_missing_or_wrong_token`

鉴权跳过只打这两条：它们分别判「401 与错误信封」和「无 token / 错 token」。`test_every_host_error_uses_the_envelope` 同时覆盖 401/403/404/409/429，所以 M1 也让它红——这是同一条判据的两个半边，不是重复计数。

## M2（4 红）

- `tests/test_cli_host.py::test_a_full_queue_is_rejected`
- `tests/test_cli_host.py::test_the_host_completion_script`
- `tests/test_cli_host.py::test_cancel_ends_only_the_segment`
- `tests/test_cli_host.py::test_a_second_message_queues_and_runs_after_the_first`

「不排队」直接打掉 4.2 / 4.3 与两个跨段场景（取消后排队的那条、完成判据的第二句）。`test_the_host_completion_script` 与 `test_cancel_ends_only_the_segment` 的 `queued` 断言是队列行为的独立护栏。

## M3（5 红）

- `tests/test_cli_host.py::test_cancel_while_waiting_for_approval_is_unavailable`
- `tests/test_cli_host.py::test_the_host_completion_script`
- `tests/test_cli_host.py::test_host_denies_a_write_over_http`
- `tests/test_host_approval.py::test_an_expired_approval_is_unavailable`
- `tests/test_host_approval.py::test_the_host_gate_never_reads_stdin`

「门立刻批准」同时打掉拒绝、取消等待、超时与「不读 stdin」四条：这四条都在判「门不能自己给出结论」。seam ② 两条与 seam ⑥ 三条各占一半。

## M4（2 红）

- `tests/test_cli_host.py::test_snapshot_precedes_only_new_frames`
- `tests/test_cli_host.py::test_the_host_completion_script`

snapshot 的 `last_seq` 是「晚连从哪继续」的唯一锚点；7.3 与 10.1 都断它，别的判据不碰 snapshot 的这个字段。

## M5（2 红）

- `tests/test_cli_host.py::test_every_host_error_uses_the_envelope`
- `tests/test_cli_host.py::test_delete_closes_only_an_idle_session`

「DELETE 允许 running」只打这两条：5.3 判 409 与日志的最后一条，9.1 判 409 的信封。两条都在 seam ⑥。

## 覆盖缺口与 dud 判定

没有存活变异，也没有语义等价（dud）的变异。M1 的「跳过鉴权」改变了 401 的可观察行为；M2 改变了第二句的 `queued` 与段顺序；M3 把「等人」变成「默认批准」；M4 改了 snapshot 的 `last_seq`；M5 把 409 变成 200。五个都改变可观察行为，且各自至少一条判据当场红。
