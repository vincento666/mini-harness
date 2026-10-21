# Tasks

每个任务是一个 red → green 单切片，标注它测哪个 seam。提交信息带任务编号。

## 1. 词表与折叠：三个新值

- [x] 1.1 词表加 `user/message`、`segment/start`、`segment/end`：已知类型判据 + 写进日志不被标 `unrecognized_type`。可达判据分两处落——run 侧的两个段记录由 2.3 落，chat 侧的三个值由 6.2 落。seam ④（`tests/test_event_vocabulary.py`）
- [x] 1.2 折叠把 `user/message` 折成 `role: user` 消息、按 `seq` 进对话体、头部之后第一条仍是它。seam ④（`tests/test_context_fold.py`）
- [x] 1.3 `segment/start` 与 `segment/end` 不产出上下文里的消息（加与不加它们，折叠结果相同）。seam ④（`tests/test_context_fold.py`）
- [x] 1.4 落在 `shadowed_range` 里的 `user/message` 不进对话体；遮蔽 `segment/*` 对折叠结果没有效果。seam ④（`tests/test_context_fold.py`）

## 2. 内核入口拆成「开始会话 / 跑一个段 / 结束会话」

- [ ] 2.1 先立回归判据：拆分之前后，一次性 run 的日志除新增的两条段边界外逐行相同、退出码不变。seam ⑥（`tests/test_cli_run.py`）
- [ ] 2.2 拆出 `start_session` / `run_turn_segment` / `end_session`，`run_session` 变成三者的组合；段调用不写 `session/end`。seam ①（`tests/test_turn_loop.py`）
- [ ] 2.3 段边界进日志：run 恰一个段，`segment/start` 在第一个 `turn/start` 之前、`segment/end` 在最后一个 `turn/end` 之后，payload 含 `segment_id`、`stop_reason`、`turns`。同步 `test_turn_loop.py` 里四处钉死序列的判据。seam ①（`tests/test_turn_loop.py`）
- [ ] 2.4 `segment_id` 与 `turn_id` 跨段连续（两段共 5 个回合是 `s1`/`s2` 与 `t1`…`t5`）；段用完 `max_turns` 不结束会话，下一条输入额度完整。seam ①（`tests/test_turn_loop.py`）
- [ ] 2.5 收 ADR-0002 第 21 条：会话环境收成一个冻结入参，段调用不再一路结伴（判据不变，只改注入形状）。seam ①②（`tests/test_turn_loop.py`、`tests/test_tool_dispatch.py`）

## 3. 溢出与取消的收尾边界

- [ ] 3.1 先红：溢出回合只写 `error/context` + `turn/end` + `segment/end`，`session/end` 由入口写（一次性 run 照写、退出码 4）。seam ①（`tests/test_context_budget.py`）
- [ ] 3.2 取消同形复核：段收尾不写 `session/end` 时，`run` 入口补写并映射退出码 5；段中取消写 `segment/end(ABORTED)`。seam ①⑥（`tests/test_turn_cancel.py`、`tests/test_cli_run.py`）
- [ ] 3.3 溢出收尾的日志照样逐点重放、退出码 0（既有守卫不退化）。seam ⑥（`tests/test_cli_replay.py`）

## 4. 预算的两条 DSH 校正

- [ ] 4.1 启动期校验：`window − reserve − 65536 ≤ 0` → 退出码 2、stderr 指出三个数、不建日志；`--window 70000 --reserve 4096` 照跑。seam ⑥（`tests/test_cli_run.py`）
- [ ] 4.2 既有 cli 判据里 `--window 4000 --reserve 500` 那条换成合法窗口（规格 scenario 同步）。seam ⑥（`tests/test_cli_run.py`）
- [ ] 4.3 请求级压缩：provider 报 `PROVIDER_CONTEXT_OVERFLOW` 且有可遮蔽内容 → 恰一条 `compaction/summary` + 重试一次 + 回合正常继续。seam ①（`tests/test_context_budget.py`）
- [ ] 4.4 无可遮蔽或重试仍失败 → 不写 `compaction/summary`、塌成溢出、没有 `error/model`。seam ①（`tests/test_context_budget.py`）

## 5. replay 的扫描逻辑下沉（ADR-0002 第 3 条）

- [ ] 5.1 事件层给出读方 API（装配点序列、按装配点切前缀），CLI 的 `_replay` 改用它、不再自己扫 `records` 与按下标切前缀。seam ④⑥（`tests/test_cli_replay.py`）
- [ ] 5.2 「replay 不用装配点之后的事件」那条守卫在新形状下仍然绿（不退化）。seam ⑥（`tests/test_cli_replay.py`）

## 6. `minihns chat`

- [ ] 6.1 子命令与参数表共用：同一份 flag、同一套层叠、`session/start.payload.entry` 为 `chat`、`prompt` 为空串。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.2 管道喂两行 → 一份日志、一条 `session/start`、两个段、两条 `user/message`、一条 `session/end(MODEL_COMPLETED)`、退出码 0。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.3 空 stdin 是合法会话：只有 `session/start` 与 `session/end`，没有 `segment/start` 与 `turn/start`。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.4 空白行不写记录、不开段。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.5 段用完 `max_turns` 回到提示符：`segment/end` 的 `stop_reason` 是 `MAX_TURNS`、`turns` 为上限值，下一条输入开 `s2` 并照样有完整额度。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.6 段级失败不退出进程：一条输入触发围栏拒绝 → `error/fence` 与 `segment/end(FENCE_DENIED)` 在盘上、会话继续、EOF 收尾退出码 0。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.7 段进行中 SIGINT：`error/abort` + `turn/end(ABORTED)` + `segment/end(ABORTED)`、没有 `session/end`、进程不退出（Linux runner 上跑，Windows 侧按 M3 的边界 skip）。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.8 提示符上 SIGINT 与 EOF 都是正常收尾：`session/end(MODEL_COMPLETED)`、退出码 0。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.9 stdout 只打模型回复正文与提示符，工具结果内容不出现在 stdout。seam ⑥（`tests/test_cli_chat.py`）
- [ ] 6.10 chat 溢出后会话继续：`error/context` + `turn/end` + `segment/end(CONTEXT_WINDOW_EXCEEDED)`、没有 `session/end`、下一条输入开新段。seam ⑥（`tests/test_cli_chat.py`）

## 7. 文档与决策

- [ ] 7.1 ADR-0019：溢出的入口边界（内核只写回合级收尾）+ 请求级压缩与一次重试 + 窗口预算不成立是启动期配置错误；写清「DSH 这么做」与「mini 版故意简化」的分界。
- [ ] 7.2 ADR-0020：REPL 的会话边界、词表三个新值、`entry` 字段、会话收尾复用 `MODEL_COMPLETED`、run 的 prompt 仍住在 `session/start` 这处不对称。
- [ ] 7.3 `GLOSSARY.md`：新增词条「回合段（segment）」，改掉「本项目没有 DSH 的 turn / step 双层」那句（本项目的一个回合 = DSH 的 step，一个段 = DSH 的 turn）。
- [ ] 7.4 ADR-0002 新记三条：DSH 的「压缩失败 warn 并继续回合」推到 M10 / M11；工具事件的终端投影归 M7 之后的事件流消费者；DSH 的 `next-step` 输入排队不做。并更正第 3、21 条为「M6 已处理」。
- [ ] 7.5 `docs/verification/m6-chat-repl-manual.md`：人手验收（真工作区、真模型跑一次 chat，至少两条输入、一次取消、一次段用完上限）。
- [ ] 7.6 更正 `docs/verification/m5-context-budget-compaction-manual.md`：「窗口 32768 → 退出码 4」被启动期校验取代，标注而不删。
- [ ] 7.7 `docs/CURRENT.md` 与 `docs/roadmap.md` 的状态行更新（M6 之后是 M7）。

## 8. 收尾

- [ ] 8.1 `code-review` 两轴（Standards / Spec，固定点 `main`），判断项记账不动代码。
- [ ] 8.2 变异测试一轮并记进 `docs/verification/m6-chat-repl-mutation.md`：每个变异都被至少一条测试杀死，存活的算覆盖缺口并补判据。
- [ ] 8.3 Learning Gate：扫本轮证据，可复用教训进 `docs/lessons.md` 收件箱；没有信号写 `NO-PROMOTE`（NO-PROMOTION）。
- [ ] 8.4 在 change 分支上 sync delta 进主规格、移 `changeRoot` 到 `openspec/changes/archive/`、`openspec validate --all --strict` 全绿。
- [ ] 8.5 门禁四道全绿后，**先征求人的批准**再 `--no-ff` 合入 `main` 并推远端、打 tag `m6`、删 change 分支。
