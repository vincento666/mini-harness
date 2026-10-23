# Tasks

## 1. 压力预算这一处事实（seam ④ 的预算模块）

- [x] 1.1 红：写判据——`pressure_budget(window, reserve)` 对三组参数给出可断言的数：128000 / 8192 → 119808、70000 / 100 → 69900、100000 / 100 → 99900；且它与 `trigger_line`、`retain_line` 是三个不同的数（70000 / 100 下分别是 69900 / 4364 / 11200）。跑 `uv run pytest -q` 确认它红。
- [x] 1.2 绿：在 `context/budget.py` 提供 `pressure_budget`，与 `trigger_line` / `retain_line` 同一模块、同一份常量表，并从 `context/__init__.py` 导出；1.1 变绿且 `uv run mypy --strict src` 无新错。**1.1 的红是 `ImportError: cannot import name 'pressure_budget'`（整个文件收集失败）**；判据里 `retain_line` 只吃一个参数（`retain_line(70000) == 11200`），写错成两个参数时它先红在 `TypeError`。

## 2. 溢出判据换轨（seam ①）

- [x] 2.1 红：写死区判据——`window 70000 / reserve 100`，一份 fixture 让某回合的预算读数落在 `(4364, 11200]` 且对话体无可遮蔽内容 → 断言该回合有 `context/assembled` 与不带 `purpose` 的 `model/request`、日志里没有 `error/context`、没有 `compaction/summary`。确认它红（今天这条以退出码 4 收尾）。**实测**：`tests/test_turn_compaction.py::test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow`，fixture 是让模型 `read` 一份 24000 字符的文件（约 6000 个 token），红在 `error/context` 的 `detail` 结尾是「已超过触发线 4364」。**先踩空一次**：原本用「模型回复本身 100000 字符」做 fixture，它不是无可遮蔽——那一组工具往返被整段遮蔽了，`compaction/summary` 照样写出来（`tokens_after: 25`）；无可遮蔽要的是**整段对话体都装得进保留尾部**，于是改读大文件。
- [x] 2.2 绿：`turn_loop.py` 的溢出判定改用 `pressure_budget`（触发线只留「要不要压缩」那一处），2.1 变绿；既有的压缩、遮蔽、`compaction/summary` 形状判据全部仍绿。**换轨必然打破既有溢出 fixture**：seam ① 三条（`test_overflow_when_nothing_can_be_shadowed` prompt 100000 → 300000 字符；`test_an_overflow_closes_the_segment_not_the_session` prompt「任务」→ 20000 个字符；`test_one_compaction_then_overflow_...` 摘要 100000 → 300000 字符），seam ⑥ 五条见 4.3。判据对象没变，变的构造数值。
- [ ] 2.3 红：写「压缩之后仍超压力预算」的判据——假 provider 写出一条摘要，重折叠后读数仍超过压力预算 → 断言 `error/context`（`CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`，且 `detail` 里同时出现预算读数、压力预算、触发线三个数。确认它红（今天这条分支不可达）。
- [ ] 2.4 绿：实现两种 `detail` 措辞（「压缩之后」与「无可遮蔽」）各带三个数，2.3 变绿；`uv run pytest -q` 全绿。

## 3. 摘要请求发不出去不再直接溢出（seam ①）

- [ ] 3.1 红：写判据——遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过压力预算 → 断言日志里没有带 `purpose: compaction` 的 `model/request`、没有 `error/model`，且当预算读数本身不超过压力预算时该回合照常写 `context/assembled`。确认它红（今天这条路无条件通向 `error/context`）。
- [ ] 3.2 绿：把「发不出摘要调用」与「溢出」解耦，3.1 变绿；既有的「一段都装不下时不发请求」与「摘要调用失败沿用 provider 失败结果」两组判据仍绿。

## 4. 黑盒：小窗口能对话，真窗口仍溢出（seam ⑥）

- [x] 4.1 红：真实子进程跑 `minihns run --window 70000 --reserve 100` 带 2.1 那份 fixture → 断言退出码不是 4、日志里有 `context/assembled`。确认它红。**实测**：`tests/test_cli_run.py::test_a_dead_zone_window_still_holds_a_conversation`，prompt 24000 个字符（约 6000 个 token，落在 `(4364, 11200]`）。它写在 2.2 之后，红不是当场踩出来的——把 `turn_loop.py` 那一处判据临时改回 `reading > line` 跑一次，它红在 `assert 4 == 0`，改回来它绿。
- [x] 4.2 红（**构造改了，原判据做不到**）：原写的是「同一 fixture 配 `--window 60000 --reserve 100`（压力预算 59900 小于读数）→ 退出码 4」。做不到有两处：Windows 的命令行上限 32767 字符，59900 个 token 要 24 万字符的上下文，`-p` 传不进去；且那种窗口在旧的启动校验下先以退出码 2 结束。改成 `--window 4000 --reserve 100`（压力预算 3900 个 token）配 20000 个字符的 prompt → 退出码 4、日志里有 `error/context`。判据对象不变。
- [x] 4.3 绿：既有的「溢出映射到退出码 4」黑盒判据逐条改构造方式并写明——`test_cli_run.py` 的 `_TIGHT_WINDOW` 66000 → 4000、`_OVERFLOW_PROMPT` 2000 → 20000 个字符（两条判据：退出码 4 与「溢出发生在第一次装配之前仍可重放」）；`test_cli_chat.py` 两条 `--window 66000` → `4000`、`--append-system-prompt` 2000 → 20000 个字符；`test_cli_serve.py` 的溢出那条同改；`test_cli_replay.py` 的溢出日志改由「摘要自己 300000 个字符」造出；`test_vocabulary_reachability.py` 两条：prompt 100000 → 300000 个字符、窗口 4000 那条加 20000 个字符的 prompt。
- [x] 4.4 红：`minihns run --window 4000 --reserve 100`（触发线 0、保留预算 640、压力预算 3900）→ 退出码 0 且 `session/start` 里 `window` 与 `reserve` 照原样。确认它红（今天退出码 2、连日志都不建）。
- [x] 4.5 绿：启动校验从 `W − O − 65536 ≤ 0` 换成 `W − O ≤ 0`（design D5 的 apply 时改），stderr 那句话只给 `window` 与 `reserve` 两个数；4.4 变绿；既有的两条「配置期就失败」判据改数值后仍咬得住（`--window 4096 --reserve 8192` 与 `--window 4000 --reserve 4000`），`test_cli_serve.py` 同形那条改 `--window 8192 --reserve 8192`。

## 5. 既有判据与规格的措辞对齐（seam ① 与 ⑥）

- [ ] 5.1 把 `tests/` 中断言「仍超过触发线」的溢出判据改判据对象为压力预算，逐条写明改了哪个数值；改完跑全量确认全绿，再用变异确认它们咬得住（不接受「改完就绿」）。
- [ ] 5.2 跑 `tests/test_vocabulary_reachability.py` 确认没有新增 `code` 或 `stop_reason`、每个既有值仍可达。
- [ ] 5.3 跑 `openspec validate --all --strict` 确认本 change 的两份 delta 结构合法（ADDED 1 条、MODIFIED 4 条，被改的每条保留全部既有 scenario 名）。

## 6. 真实端点验收（完成判据的第二半，ADR-0024）

- [ ] 6.1 本机 Strata（`http://127.0.0.1:8300/v1`、`qwen3.8-flash-next-iq3_xxs`）跑 `--window 70000 --reserve 100` 读 `.tmp/reacc/ws/big.md`：确认不再以退出码 4 结束、会话正常收尾，记下真实的预算读数与触发线。
- [ ] 6.2 同一端点跑一次真溢出（`--window 100000 --reserve 100` 读 `huge.md`）：确认退出码 4、`error/context` 的 `detail` 含三个数。
- [ ] 6.3 跑一次「压缩发生了但仍不够」：小窗口 + 长摘要，如实记录**撞没撞到**那条字面分支；撞不到就写明撞不到与原因。
- [ ] 6.4 观察记进 `docs/verification/fix-small-window-compaction-dead-zone-real-endpoint.md`。

## 7. UAT 验收（完成判据的第三半，ADR-0025，人跑）

- [ ] 7.1 手册骨架已立：`docs/verification/fix-small-window-compaction-dead-zone-uat.md`（三场：小窗口能对话 / 真溢出看得见那一行 / 压缩看得见）。
- [ ] 7.2 等人坐在终端前跑完那三场并填回观察表；**表没填完本 change 不得归档、不得合入 `main`**。

## 8. 变异测试一轮

- [ ] 8.1 五条变异跑全量并记进 `docs/verification/fix-small-window-compaction-dead-zone-mutation.md`：① 溢出判据改回触发线；② `pressure_budget` 写成 `window - reserve - 65536`；③ `detail` 去掉压力预算那个数；④ 「发不出摘要调用」重新直接通向溢出；⑤ 无可遮蔽时仍写 `compaction/summary`。每条必须被至少一条测试杀死，存活的补判据。

## 9. Learning Gate

- [ ] 9.1 扫本轮证据写进 `docs/lessons.md` 收件箱；**收件箱已到上限 15 条，先消化再收新条**。
- [ ] 9.2 关闭 `docs/adr/0002` 的「判据欠账」里小窗口死区那条，立 ADR-0026（溢出判据与压缩触发线是两件事），并在 `docs/roadmap.md` 的 M5 行补一句「压缩仍不够」第一次可达。
