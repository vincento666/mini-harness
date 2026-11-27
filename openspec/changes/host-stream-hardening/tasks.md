# Tasks

## 1. stream/end 实现（唯一代码缺口）

- [x] 1.1 同左。host.py 侧随 merge-reasoning-stream 合并时补入（`test_a_broken_log_sends_stream_end_on_reconnect`）；serve.py 侧本 change 补入（进程内直测 `test_a_corrupt_log_line_ends_the_stream_with_stream_end`——坏行进真会话会把下一次装配一并带走，是既有「坏行终止会话」语义，不能当传输层判据）。帧编码器 `stream_end_frame` 与 `sse_frame` 同住 serve.py，消掉 host↔serve 循环导入
- [x] 1.2 同左。实现在 host.py 已有（merge 时补入），判据在 `test_cli_host.py`（`session_ended` 帧断言）

## 2. 规格追认（无代码）

- [x] 2.1 同左。`test_snapshot_messages_are_the_model_context_not_the_control_plane`：带工具调用的会话里 snapshot.messages 与同前缀 `fold` 逐字段相等、角色 ⊆ system/user/assistant/tool
- [x] 2.2 同左。判据已存在（`test_no_log_download_route`），本 change 追认

## 3. 收尾四项

- [x] 3.1 同左。会话 `19c0c50f…`（OpenRouter `qwen/qwen3.8-27b`），帧序正常，durable 重放 0 命中 stream/end / reasoning/delta / model/delta；见 `docs/verification/host-stream-hardening-real-endpoint.md`
- [ ] 3.2 UAT 验收（人跑）：手册已立 `docs/verification/host-stream-hardening-uat.md`（远端壳视角三场：正常收尾 / DELETE 的 session_ended / 坏行的 LOG_UNREADABLE）
- [x] 3.3 变异测试一轮：M1（serve 读失败不发帧）与 M2（snapshot 混进控制面记录）各被对应判据杀死；见 `docs/verification/host-stream-hardening-mutation.md`。流程教训：先提交再变异——第一轮回滚用 `git checkout --` 把未提交的实现一并冲掉了
- [x] 3.4 Learning Gate：**NO-PROMOTION**——本 change 是防御性收口，实现与判据无新的可复用信号；「先提交再变异」并入 merge-reasoning-stream 场次的既有教训（变异必须死在断言上）同族，不单独立条
