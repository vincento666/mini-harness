# Design

## 边界：REPL 是入口，不是内核的一部分

内核（`loop/`）不知道 REPL 存在。M5 之前 `run_session` 一个函数干完三件事：写 `session/start`、跑 `max_turns` 个回合、写 `session/end`。REPL 需要的是「开始一个会话 / 跑一个段 / 结束一个会话」三件事各自可调用，于是内核入口拆成三段（ADR-0011 的边界由此真正落地）：

- **D1** `start_session(...)` 写 `session/start`；`run_turn_segment(env, first_turn_index)` 跑**一个段**（段内上限是有效 `max_turns`）并返回 `RunOutcome`，MUST NOT 写 `session/end`；`end_session(log, stop_reason)` 写 `session/end`。一次性 `run` = 开始 + 一个段 + 结束。日志形状由此多两条记录（段的边界，D3），其余逐行与 M5 之前相同。
- **D2** 顺带收 ADR-0002 第 21 条：`provider` / `log` / `registry` / `settings` / `approval_gate` 收成一个冻结的**会话环境**入参，段调用不再一路结伴。`cancel` 不在这里——D7 要「取消当前段、会话继续」，一个会话一份事件置起之后没有地方放回去，所以它是段的入参而不是会话的（实现时的改判，记进 ADR-0002 第 47 条）。第 3 条（`_replay` 摸事件层内部形状）由 D10 收。

## 段：M6 补上 DSH 缺的那一层边界

- **D3** 段的边界 durable（照 DSH 的 `turn` 边界）：段开始写 `segment/start`（payload `segment_id`），段结束写 `segment/end`（payload `segment_id`、该段最后一个回合的 `stop_reason`、该段实际跑掉的回合数 `turns`）。`segment_id` 与 `turn_id` 都在会话内连续编号，段起始编号由入口给（`first_turn_index`），内核不数段、不数输入。`segment/*` 与 `turn/*` 一样不产出上下文里的消息。DSH 那边：`turn = phase.turn + 1` 后 `session.append("turn/start", {turn})`（`dsh-agent-loop/lib/index.js:941-947`），编号单调且落日志；turn 之内 `while (true) { step = phase.step + 1; … }`（:951-957）。**本项目的「回合」仍是 DSH 的 `step`，本项目的「段」是 DSH 的 `turn`**——GLOSSARY 第 17-19 行那句「本项目没有 DSH 的 turn / step 双层」由此作废，M6 补上缺的那一层并新增词条「段（segment）」（收尾轮按裁决统一用「段」，提案与规划产物里旧的「回合段」是同一个东西，GLOSSARY 的 _Avoid_ 里写明）。
- **D4** `max_turns` 判的是**段**，会话级不设上限。DSH 的交互循环对 `turn` 与 `step` 都不设轮数上限——`dsh-agent-loop` 的全部数值配置只有 `maxParallelToolCalls`（默认 10，:1534）与每 agent 的 `maxTokens`（:1541）。DSH 唯一带轮数上限的地方是委派工具 `dsh-tool-ralph` 的 `maxRounds`（默认 256，用完返回 `{status: "budget-limited", roundsStarted}`），那对应本项目的 seam ⑦ / M15「目标轮次与 `blocked`」，**MUST NOT 与 `max_turns` 混名**。保留 `max_turns` 是 mini 的故意简化：headless 一次性 run 需要一个默认终止条件（`MAX_TURNS` 是已落地的 `stop_reason`，CI 判据靠它）。一次性 run 恰一个段，所以「一次 run 的上限」与「段内上限」在那里是同一个数——变掉的只是「一次会话只有一条输入」这个前提。

## 输入即记录

- **D5** CLI 的读循环读一行 → 非空就写一条 `user/message`（payload `segment_id` 与 `content` 原文）→ 开一段。空白行不写记录、不开段。`entry` 为 `chat` 的会话里 `session/start.payload.prompt` 是空串：一个会话的人话只有一个家（ADR-0020）。词表加 `user/message`、`segment/start`、`segment/end` 是扩词表级决定，落在 `events/vocabulary.py` 与 event-log 主规格。
- **D6** 折叠里 `role: user` 消息有两个来源（`session/start.payload.prompt` 与 `user/message`），按 `seq` 顺序进对话体、可进遮蔽范围。run 的 prompt 仍住在 `session/start` 里——这是 M1 落下的形状，M6 不动它，不对称记 ADR-0020。

## 取消与溢出的收尾边界

- **D7** 两级取消：每个段一个 `asyncio.Event`。段进行中收到 SIGINT → 置位该段的 cancel，内核按既有回合级形状收尾（`error/abort` + `turn/end(ABORTED)` + `segment/end(ABORTED)`），入口不写 `session/end`、回到提示符。没有段在跑时收到 SIGINT（含 stdin 读行里的 `KeyboardInterrupt`）→ 结束读循环 → `session/end(MODEL_COMPLETED)`、退出码 0。EOF 同一条路。词表里没有「人结束了会话」这个值，复用 `MODEL_COMPLETED` 表示正常收尾，代价写 ADR-0020。
- **D8** 溢出与取消同形（ADR-0019）：内核只写 `error/context` + `turn/end(CONTEXT_WINDOW_EXCEEDED)` + `segment/end`，`session/end` 与退出码归入口。`run` 塌成退出码 4，`chat` 回到提示符。
- **D9** 照 DSH 的两条预算校正：① `window − reserve − 65536 ≤ 0` 是**配置错误**，在 CLI 参数校验里以退出码 2 失败并指出三个数（DSH 在配置解析期抛 `TargetPressureConfigError`，`dsh-compaction-basic/lib/index.js:130-131`）；② provider 报 `PROVIDER_CONTEXT_OVERFLOW` 时先做一次请求级压缩、有可遮蔽的内容就重试该请求一次（上限 1，照 DSH `maxOverflowRetries` 默认 1，:861-887），救不动才塌成溢出。**不做**的那条：DSH 在压缩调用自己抛错时 `continuing the turn`（:849），mini 版仍沿用 M5 落下的「摘要调用失败 = provider 失败结果」，记进 ADR-0002 推到 M10 / M11。

## stdout

- **D10** 把 replay 的扫描逻辑下沉到事件层（ADR-0002 第 3 条）：事件层给出「装配点序列」与「按装配点切前缀」的读方 API，CLI 的 `_replay` 只用它。第二个消费者（chat 之后的 SSE）由此不必再扫一遍。
- **D11** stdout 只打印每条 `model/response` 的 `content` 原文与一行固定提示符。工具事件的终端投影（Claude Code 那种进度行）是日志的另一种投影，归 M7 之后的事件流消费者，不在 M6（记 ADR-0002）。

## 测试策略（只在既有七个缝上写）

| Seam | 落点 | 判据形状 |
| --- | --- | --- |
| ① 回合循环 | `tests/test_turn_loop.py`、`tests/test_context_budget.py`、`tests/test_turn_cancel.py` | 段的边界与 `segment_id` / `turn_id` 偏移；`segment/end` 的 `stop_reason` 与 `turns`；溢出与取消只写回合级收尾；请求级压缩 + 一次重试；无可遮蔽时不写 `compaction/summary` |
| ④ 日志追加与折叠 | `tests/test_event_vocabulary.py`、`tests/test_vocabulary_reachability.py`、`tests/test_context_fold.py`、`tests/test_cli_replay.py` | 三个新词表值可达；`user/message` 折成 `user` 消息、`segment/*` 不产出消息；遮蔽里的输入不进表层；replay 的扫描逻辑住在事件层 |
| ⑥ CLI 黑盒 | `tests/test_cli_run.py`、新增 `tests/test_cli_chat.py` | 管道喂行 → 一份日志两条输入两个段；空 stdin；段用完 `max_turns` 回到提示符且下一条输入额度完整；段级失败不退出；stdout 只打模型回复正文；启动期窗口校验退出码 2；SIGINT 两级（Linux 上跑，Windows 侧沿用 M3 的边界：真实控制台 Ctrl-C 无判据） |

seam ②③⑤⑦ 不动：工具契约、文件工具、provider 接口、委派都不因 REPL 改变形状（provider 的 `PROVIDER_CONTEXT_OVERFLOW` 取值 M5 已有）。钉死事件序列的既有判据共 6 处（`test_turn_loop.py` 四处、`test_event_log_append.py:70`、`test_event_vocabulary.py:36`），前四处因 run 也写段边界而改——这是 D3 的已计代价，不是回归。**收尾轮按实况更正（2026-10-21）**：受影响的是 **8 个测试文件、约 21 个测试函数、47 行新增断言**（逐文件的数字见 ADR-0020）；这张表列的 `test_event_log_append.py` 一行没改，`test_context_fold.py`、`test_turn_compaction.py`、`test_cli_run.py`、`test_turn_cancel.py`、`test_approval_gate.py`、`test_cli_replay.py` 不在表上。④ 那行的落点 `test_vocabulary_reachability.py` 本轮没动，三个新词表值的可达性判据实际落在 `test_event_vocabulary.py`（seam ④）与 `test_cli_run.py` / `test_cli_chat.py`（seam ⑥）；2.5 的 seam ② 落点 `test_tool_dispatch.py` 同样没动。

## 已知风险与边界

- **Windows 的 Ctrl-C**：M3 已定「Windows 真实控制台 Ctrl-C 不在判据范围内」。chat 的 SIGINT 判据在 Linux runner 上跑；Windows 侧靠 EOF（管道喂行）判据 + 人手验收。
- **stdin 与审批门共用**：审批门在段内读一行、读循环在段外读一行，不同时发生；若一条输入正等待审批，取消走既有回合级形状。DSH 另有 `next-step` 队列（跑中途注入输入），M6 不做输入排队，记 ADR-0002。
- **`entry` 字段**：payload 加一个键，现有判据没有「键集合恰好等于」的断言，成本是新增断言而不是改旧断言。
- **M5 的 manual 文档**：「窗口 32768 → 退出码 4」那条观察被 D9① 取代，收尾时在文档里标注而不是删掉。
