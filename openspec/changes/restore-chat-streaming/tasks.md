# 任务：restore-chat-streaming

## 1 实现

- [ ] 1.1 先写红判据：不传 flag 即流式；`--no-stream` 逐点不变；两个 flag 互斥；首 delta 在管道上可读（`tests/test_cli_chat.py`）
- [ ] 1.2 `cli/main.py`：`_ChatStreamRenderer`（`text(step_id, text)`、每轮一次 `[answer] `、`finish_turn()` 只在写过正文时换行）
- [ ] 1.3 `chat` 的互斥 flag `--stream` / `--no-stream`，`set_defaults(stream=True)`；更新 flag 表比对的既有测试（并上这两个）
- [ ] 1.4 `SessionEnv` 增加可选 `on_step_end(step_id, content)`；`turn_loop` 在 `step/end` 落盘后、下一步 `step/start` 前调用（最后一步在 `break` 前也调用），`content` 取该步非 `purpose` 的 `model/response.content`；钩子异常转 `error/*`，不留半截边界
- [ ] 1.5 CLI 钩子：`content.strip()` 非空且该步没流过非空 delta → 打印并记入已输出集合；`--no-stream` 与 `host` 不装钩子
- [ ] 1.6 去重：`_print_new_replies` 跳过已输出集合（流式步 + 回退步）；`printed` 游标按**非 `purpose`** 的条数推进，并把 `--resume` 的初始化（`main.py:687`）改成同一口径
- [ ] 1.7 按轮收尾：每次 `run_turn` 返回后调 `finish_turn()`；目标连续多轮各成一行，提示符不重复
- [ ] 1.8 取消分叉：在 `provider.generate` 返回后、写 response 前记 `streamed_any`（只算非空 text，每次 generate 前重置，含压缩重试）；真 → `_abort_turn`，假 → 写完整 `model/response`
- [ ] 1.9 可控停顿桩：测试里加「发首 delta 后阻塞、放行后发剩余」的 provider；管道读，不用 `capsys`

## 2 判据

- [ ] 2.1 默认流式——fixture `deltas: ["你","好"]`，stdout 顺序出现且轮末不重复
- [ ] 2.2 实时性——管道桩：首 delta 在放行前可读，第二个尚不可读；另有「写但不 flush」变异要能红
- [ ] 2.3 `--no-stream` 与基线逐点相同（现有 chat 测试显式加 `--no-stream` 后仍绿）
- [ ] 2.4 去重三分支：有 delta、无 delta、同轮混合不倒序；无 delta 的步整轮 exact-once
- [ ] 2.5 `[answer] ` 每轮恰一次；空 delta 不触发；空白 `content` 不出空行
- [ ] 2.6 compaction：摘要不进 stdout；同轮回退只取真正回复
- [ ] 2.7 黑盒：目标两轮各一行、`[轮]` 在正文前（pty 合流）、提示符一次
- [ ] 2.8 黑盒：管道喂行（stdin 非 tty）仍按行开轮，EOF 正常收尾
- [ ] 2.9 取消四分：流式中途（sink barrier）、已落盘工具窗口、无 delta 已落盘、`--no-stream` 旧形状
- [ ] 2.10 pty：`0x03` 能被投递为 SIGINT 并回到提示符（不承担「半句时刻」）
- [ ] 2.11 日志不变：成功一轮的事件类型序列与 `model/response` 键集合相同；`replay` 两者都退 0 且折叠消息逐点相等
- [ ] 2.12 `--resume` + compaction：首条新回复打印一次

## 3 收尾

- [ ] 3.1 全量门禁：ruff `format --diff` / `check`、`mypy --strict`、pytest 全量、`openspec validate --all --strict`
- [ ] 3.2 真实端点验收：OpenRouter `qwen/qwen3.8-27b` 跑一次流式 chat，记录首帧可见与拼接一致（`docs/verification/restore-chat-streaming-real-endpoint.md`）
- [ ] 3.3 UAT 验收：人跑；场次手册 `docs/verification/restore-chat-streaming-uat.md`（关键场次是 UX 手感，按 ADR-0025 不得由 agent 代跑）
- [ ] 3.4 变异测试一轮：记录 `docs/verification/restore-chat-streaming-mutation.md`，存活变异补测试
- [ ] 3.5 两轴 code review 与对照门禁（子代理，归档前）
- [ ] 3.6 Learning Gate：可复用教训写进 `docs/lessons.md` 收件箱，没有就写 `NO-PROMOTION`
- [ ] 3.7 文档：`docs/reference/h2-streaming-and-reasoning.md` 的 chat 段落按实现回写（含「思考流 deferred」的边界）；`docs/CURRENT.md` 活动 change 与门禁读数更新
