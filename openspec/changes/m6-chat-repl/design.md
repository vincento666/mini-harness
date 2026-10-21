# Design

## 边界：REPL 是入口，不是内核的一部分

内核（`loop/`）不知道 REPL 存在。M5 之前 `run_session` 一个函数干完三件事：写 `session/start`、跑 `max_turns` 个回合、写 `session/end`。REPL 需要的是「开始一个会话 / 跑一个回合段 / 结束一个会话」三件事各自可调用，于是内核入口拆成三段（ADR-0011 的边界由此真正落地）：

- **D1** `start_session(...)` 写 `session/start`；`run_turn_segment(env, first_turn_index)` 跑**一个段**（段内上限是有效 `max_turns`）并返回 `RunOutcome`，MUST NOT 写 `session/end`；`end_session(log, stop_reason)` 写 `session/end`。一次性 `run` = 开始 + 一个段 + 结束，日志字节与 M5 之前逐行相同（回归判据守着）。
- **D2** 顺带收 ADR-0002 第 21 条：`provider` / `log` / `registry` / `settings` / `approval_gate` / `cancel` 收成一个冻结的**会话环境**入参，段调用不再一路结伴。第 3 条（`_replay` 摸事件层内部形状）由 D7 收。
- **D3** `turn_id` 跨段连续：段起始编号由入口给（`first_turn_index`），内核不数段、不数输入。REPL 每跑完一段就把偏移推进到该段实际跑掉的回合数。

## 输入即记录

- **D4** CLI 的读循环读一行 → 非空就写一条 `user/message`（payload `turn_id` = 该段第一个回合、`content` 原文）→ 开一段。空白行不写记录、不开段。`entry` 为 `chat` 的会话里 `session/start.payload.prompt` 是空串：一个会话的人话只有一个家（ADR-0020）。词表加 `user/message` 是扩词表级决定，落在 `events/vocabulary.py` 与 event-log 主规格。
- **D5** 折叠里 `role: user` 消息有两个来源（`session/start.payload.prompt` 与 `user/message`），按 `seq` 顺序进对话体、可进遮蔽范围。run 的日志形状不变。

## 取消与溢出的收尾边界

- **D6** 两级取消：每个段一个 `asyncio.Event`。段进行中收到 SIGINT → 置位该段的 cancel，内核按既有回合级形状收尾（`error/abort` + `turn/end(ABORTED)`），入口不写 `session/end`、回到提示符。没有段在跑时收到 SIGINT（含 stdin 读行里的 `KeyboardInterrupt`）→ 结束读循环 → `session/end(MODEL_COMPLETED)`、退出码 0。EOF 同一条路。
- **D7** 溢出与取消同形（ADR-0019）：内核只写 `error/context` + `turn/end(CONTEXT_WINDOW_EXCEEDED)`，`session/end` 与退出码归入口。`run` 塌成退出码 4，`chat` 回到提示符。
- **D8** 照 DSH 的两条校正：① `window − reserve − 65536 ≤ 0` 是**配置错误**，在 CLI 参数校验里以退出码 2 失败并指出三个数（DSH 在配置解析期抛 `TargetPressureConfigError`）；② provider 报 `PROVIDER_CONTEXT_OVERFLOW` 时先做一次请求级压缩、有可遮蔽的内容就重试该请求一次（上限 1，照 DSH `maxOverflowRetries` 默认 1），救不动才塌成溢出。**不做**的那条：DSH 在压缩调用自己抛错时 `continuing the turn`（`dsh-compaction-basic/lib/index.js:849`），mini 版仍沿用 M5 落下的「摘要调用失败 = provider 失败结果」，记进 ADR-0002 推到 M10 / M11。

## stdout

- **D9** stdout 只打印每条 `model/response` 的 `content` 原文与一行固定提示符。工具事件的终端投影（Claude Code 那种进度行）是日志的另一种投影，归 M7 之后的事件流消费者，不在 M6（记 ADR-0002）。

## 测试策略（只在既有七个缝上写）

| Seam | 落点 | 判据形状 |
| --- | --- | --- |
| ① 回合循环 | `tests/test_turn_loop.py`、`tests/test_context_budget.py` | 段边界与 `turn_id` 偏移；溢出与取消只写回合级收尾；请求级压缩 + 一次重试；无可遮蔽时不写 `compaction/summary` |
| ④ 日志追加与折叠 | `tests/test_event_vocabulary.py`、`tests/test_vocabulary_reachability.py`、`tests/test_context_fold.py`、`tests/test_cli_replay.py` | `user/message` 可达且折成 `user` 消息；遮蔽里的输入不进表层；replay 的扫描逻辑住在事件层 |
| ⑥ CLI 黑盒 | `tests/test_cli_run.py`、新增 `tests/test_cli_chat.py` | 管道喂行 → 一份日志两条输入；空 stdin；段用完 `max_turns` 回到提示符；段级失败不退出；stdout 只打模型回复正文；启动期窗口校验退出码 2；SIGINT 两级（Linux 上跑，Windows 侧沿用 M3 的边界：真实控制台 Ctrl-C 无判据） |

seam ②③⑤⑦ 不动：工具契约、文件工具、provider 接口、委派都不因 REPL 改变形状（provider 的 `PROVIDER_CONTEXT_OVERFLOW` 取值 M5 已有）。

## 已知风险与边界

- **Windows 的 Ctrl-C**：M3 已定「Windows 真实控制台 Ctrl-C 不在判据范围内」。chat 的 SIGINT 判据在 Linux runner 上跑；Windows 侧靠 EOF（管道喂行）判据 + 人手验收。
- **stdin 与审批门共用**：审批门在段内读一行、读循环在段外读一行，不同时发生；若一条输入正等待审批，取消走既有回合级形状。
- **`entry` 字段**：payload 加一个键，现有判据没有「键集合恰好等于」的断言，成本是新增断言而不是改旧断言。
- **M5 的 manual 文档**：「窗口 32768 → 退出码 4」那条观察被 D8① 取代，收尾时在文档里标注而不是删掉。
