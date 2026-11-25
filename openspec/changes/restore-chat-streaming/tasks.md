# 任务：restore-chat-streaming

## 1 实现

- [ ] 1.1 先写红判据：不传 flag 即流式；`--no-stream` 逐点不变；两个 flag 互斥；首 delta 在阻塞桩放行前已到 stdout（`tests/test_cli_chat.py`）
- [ ] 1.2 `cli/main.py`：`_ChatStreamRenderer`（`text(step_id, text)`、每轮一次 `[answer] `、`finish_turn()` 收行——只在写过正文时换行）
- [ ] 1.3 `chat` 的互斥 flag `--stream` / `--no-stream`，`set_defaults(stream=True)`；更新 flag 表比对的既有测试（并上这两个）
- [ ] 1.4 `SessionEnv` 增加可选 `on_step_end(step_id)`；`turn_loop` 在该步 `model/response` 落盘后、下一步开始前调用；CLI 在钩子里回退打印「没流过非空 delta」的步
- [ ] 1.5 去重：渲染器维护「已输出」集合（流式步 + 回退步）；`_print_new_replies` 增加跳过集合；`printed` 游标按**非 `purpose`** 的 `model/response` 条数推进（与 resume 初始化同一口径）
- [ ] 1.6 按轮收尾：每次 `run_turn` 返回后调 `finish_turn()`；目标连续多轮各成一行，提示符不重复
- [ ] 1.7 取消分叉：provider 调用处记录 `streamed_any`；`turn_loop` 的 `_abort_turn` 判据加 `and streamed_any`，没流过则写完整 `model/response`
- [ ] 1.8 可控停顿桩：测试里加一个「发首 delta 后阻塞、放行后发剩余」的 provider，用于证明实时性与取消时机

## 2 判据

- [ ] 2.1 默认流式——fixture `deltas: ["你","好"]`，stdout 顺序出现且轮末不重复
- [ ] 2.2 实时性——阻塞桩：首 delta 在放行前已到 stdout，第二个尚未出现
- [ ] 2.3 `--no-stream` 与基线逐点相同（现有 chat 测试显式加 `--no-stream` 后仍绿）
- [ ] 2.4 去重三分支：有 delta、无 delta、同轮混合不倒序
- [ ] 2.5 `[answer] ` 每轮恰一次；空 delta 不触发
- [ ] 2.6 黑盒：目标两轮各一行、`[轮] 1/…` 与 `[轮] 2/…` 都在正文前、提示符一次
- [ ] 2.7 黑盒：管道喂行（stdin 非 tty）仍按行开轮，EOF 正常收尾
- [ ] 2.8 取消三分支：有 delta（pty 真 Ctrl-C）、无 delta（单测）、`--no-stream`（旧形状）
- [ ] 2.9 日志不变：成功一轮的事件类型序列与 `model/response` 键集合相同；`replay` 两者都退 0 且折叠消息逐点相等

## 3 收尾

- [ ] 3.1 全量门禁：ruff `format --diff` / `check`、`mypy --strict`、pytest 全量、`openspec validate --all --strict`
- [ ] 3.2 真实端点验收：OpenRouter `qwen/qwen3.8-27b` 跑一次流式 chat，记录首帧可见与拼接一致（`docs/verification/restore-chat-streaming-real-endpoint.md`）
- [ ] 3.3 UAT 验收：人跑；场次手册 `docs/verification/restore-chat-streaming-uat.md`（关键场次是 UX 手感，按 ADR-0025 不得由 agent 代跑）
- [ ] 3.4 变异测试一轮：记录 `docs/verification/restore-chat-streaming-mutation.md`，存活变异补测试
- [ ] 3.5 两轴 code review 与对照门禁（子代理，归档前）
- [ ] 3.6 Learning Gate：可复用教训写进 `docs/lessons.md` 收件箱，没有就写 `NO-PROMOTION`
- [ ] 3.7 文档：`docs/reference/h2-streaming-and-reasoning.md` 的 chat 段落按实现回写（含「思考流 deferred」的边界）；`docs/CURRENT.md` 活动 change 与门禁读数更新
