# host-stream-hardening — 变异记录

**日期**：2026-11-27。**口径**：逐条注入、跑判据测试、`git checkout --` 回滚。实现先提交再变异——第一轮变异时实现还没提交，`git checkout --` 把它连同变异一起冲掉了，白查了一场「回滚后判据怎么还是红的」；这个流程教训写进了提交信息与 tasks 3.3。回滚后复核：`snapshot or corrupt` 判据全绿。

---

## M1：serve 读日志失败直接断流，不发 `stream/end`

**注入**（`src/mini_harness/cli/serve.py::_events` 的 `LogReadFailure` 分支）：删掉 `stream_end_frame(...)` 的 write，直接 `return response`。

**跑**：`uv run pytest tests/test_cli_serve.py -k corrupt`

**结果**：**被杀死**（1 failed）——进程内判据 `test_a_corrupt_log_line_ends_the_stream_with_stream_end` 收不到那帧，`frames == []` vs 期望恰一条 `stream/end`。

## M2：snapshot 的 messages 混进一条控制面记录

**注入**（`src/mini_harness/cli/host.py` 的 `_snapshot_frame` payload）：`messages` 末尾追加 `{"role": "system", "content": "M2 变异：混进控制面记录"}`。

**跑**：`uv run pytest tests/test_cli_host.py -k snapshot_messages`

**结果**：**被杀死**（1 failed）——`test_snapshot_messages_are_the_model_context_not_the_control_plane` 的「snapshot == 同前缀 `fold`」逐字段断言不等。

## 结论

- 「唯一实现缺口」两侧（host.py 在 merge 时已补、serve.py 本 change 补）现在各有一条黑盒判据，两条变异分别被各自侧的判据杀死。
- M2 顺带验证了追认条款不是空话：snapshot 多一条记录都会被「与 fold 逐字段相等」抓出来。
