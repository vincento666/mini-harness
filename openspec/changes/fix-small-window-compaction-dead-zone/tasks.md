# Tasks

## 1. 压力预算这一处事实（seam ④ 的预算模块）

- [x] 1.1 红：写判据——`pressure_budget(window, reserve)` 对三组参数给出可断言的数：128000 / 8192 → 119808、70000 / 100 → 69900、100000 / 100 → 99900；且它与 `trigger_line`、`retain_line` 是三个不同的数（70000 / 100 下分别是 69900 / 4364 / 11200）。跑 `uv run pytest -q` 确认它红。
- [x] 1.2 绿：在 `context/budget.py` 提供 `pressure_budget`，与 `trigger_line` / `retain_line` 同一模块、同一份常量表，并从 `context/__init__.py` 导出；1.1 变绿且 `uv run mypy --strict src` 无新错。**1.1 的红是 `ImportError: cannot import name 'pressure_budget'`（整个文件收集失败）**；判据里 `retain_line` 只吃一个参数（`retain_line(70000) == 11200`），写错成两个参数时它先红在 `TypeError`。

## 2. 溢出判据换轨（seam ①）

- [x] 2.1 红：写死区判据——`window 70000 / reserve 100`，一份 fixture 让某回合的预算读数落在 `(4364, 11200]` 且对话体无可遮蔽内容 → 断言该回合有 `context/assembled` 与不带 `purpose` 的 `model/request`、日志里没有 `error/context`、没有 `compaction/summary`。确认它红（今天这条以退出码 4 收尾）。**实测**：`tests/test_turn_compaction.py::test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow`，fixture 是让模型 `read` 一份 24000 字符的文件（约 6000 个 token），红在 `error/context` 的 `detail` 结尾是「已超过触发线 4364」。**先踩空一次**：原本用「模型回复本身 100000 字符」做 fixture，它不是无可遮蔽——那一组工具往返被整段遮蔽了，`compaction/summary` 照样写出来（`tokens_after: 25`）；无可遮蔽要的是**整段对话体都装得进保留尾部**，于是改读大文件。
- [x] 2.2 绿：`turn_loop.py` 的溢出判定改用 `pressure_budget`（触发线只留「要不要压缩」那一处），2.1 变绿；既有的压缩、遮蔽、`compaction/summary` 形状判据全部仍绿。**换轨必然打破既有溢出 fixture**：seam ① 三条（`test_overflow_when_nothing_can_be_shadowed` prompt 100000 → 300000 字符；`test_an_overflow_closes_the_segment_not_the_session` prompt「任务」→ 20000 个字符；`test_one_compaction_then_overflow_...` 摘要 100000 → 300000 字符），seam ⑥ 五条见 4.3。判据对象没变，变的构造数值。
- [x] 2.3 红：写「压缩之后仍超压力预算」的判据——假 provider 写出一条摘要，重折叠后读数仍超过压力预算 → 断言 `error/context`（`CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`，且 `detail` 里同时出现预算读数、压力预算、触发线三个数。确认它红（今天这条分支不可达）。**实测**：2.2 落地之后这条分支已经可达（`test_one_compaction_then_overflow_when_the_context_still_does_not_fit` 用 300000 字符的摘要打到它），所以真正踩红的是三个数那一半：两条溢出判据都红在缺「触发线 4364」——`无可遮蔽的内容，预算读数 75015 已超过压力预算 69900` 与 `压缩之后预算读数 75024 仍超过压力预算 69900`。
- [x] 2.4 绿：两种 `detail` 措辞各带三个数（读数、压力预算、触发线），2.3 变绿；`uv run pytest -q` 全绿。

## 3. 摘要请求发不出去不再直接溢出（seam ①）

- [x] 3.1 红：写判据——遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过压力预算 → 断言日志里没有带 `purpose: compaction` 的 `model/request`、没有 `error/model`，且当预算读数本身不超过压力预算时该回合照常写 `context/assembled`。确认它红（今天这条路无条件通向 `error/context`）。**实测**：`test_a_shadowed_range_too_big_to_trim_sends_no_summary_request`（窗口 20000 / 预留 100：压力预算 19900、保留预算 3200、触发线 0；一条 100000 字符约 25000 个 token 的工具结果）。红只在一处——「没有 `purpose: compaction` 的请求」「没有 `error/model`」「没有 `compaction/summary`」三条本来就绿：2.2 换轨之后「发不出摘要请求」已经不再无条件通向溢出。红的是措辞：日志写着「无可遮蔽的内容」，可这一回合**有**可遮蔽的那一段，只是裁到只剩一组往返仍装不下。**顺带查清一件事**：这条 scenario 里「该回合照常装配」那一半在装配缝上走不到——摘要请求的预算就是压力预算，而遮蔽段是对话体的子集，遮蔽段本身就超压力预算时读数必然也超。判据只断言可达的那一半，规格里「除非预算读数本身超过压力预算」正是这一条。
- [x] 3.2 绿：措辞跟着日志里的事实走，三种分支各带三个数（真写过摘要 / 给不出遮蔽范围 / 给得出却本身就装不下）；既有的「一段都装不下时不发请求」与「摘要调用失败沿用 provider 失败结果」两组判据仍绿。

## 4. 黑盒：小窗口能对话，真窗口仍溢出（seam ⑥）

- [x] 4.1 红：真实子进程跑 `minihns run --window 70000 --reserve 100` 带 2.1 那份 fixture → 断言退出码不是 4、日志里有 `context/assembled`。确认它红。**实测**：`tests/test_cli_run.py::test_a_dead_zone_window_still_holds_a_conversation`，prompt 24000 个字符（约 6000 个 token，落在 `(4364, 11200]`）。它写在 2.2 之后，红不是当场踩出来的——把 `turn_loop.py` 那一处判据临时改回 `reading > line` 跑一次，它红在 `assert 4 == 0`，改回来它绿。
- [x] 4.2 红（**构造改了，原判据做不到**）：原写的是「同一 fixture 配 `--window 60000 --reserve 100`（压力预算 59900 小于读数）→ 退出码 4」。做不到有两处：Windows 的命令行上限 32767 字符，59900 个 token 要 24 万字符的上下文，`-p` 传不进去；且那种窗口在旧的启动校验下先以退出码 2 结束。改成 `--window 4000 --reserve 100`（压力预算 3900 个 token）配 20000 个字符的 prompt → 退出码 4、日志里有 `error/context`。判据对象不变。
- [x] 4.3 绿：既有的「溢出映射到退出码 4」黑盒判据逐条改构造方式并写明——`test_cli_run.py` 的 `_TIGHT_WINDOW` 66000 → 4000、`_OVERFLOW_PROMPT` 2000 → 20000 个字符（两条判据：退出码 4 与「溢出发生在第一次装配之前仍可重放」）；`test_cli_chat.py` 两条 `--window 66000` → `4000`、`--append-system-prompt` 2000 → 20000 个字符；`test_cli_serve.py` 的溢出那条同改；`test_cli_replay.py` 的溢出日志改由「摘要自己 300000 个字符」造出；`test_vocabulary_reachability.py` 两条：prompt 100000 → 300000 个字符、窗口 4000 那条加 20000 个字符的 prompt。
- [x] 4.4 红：`minihns run --window 4000 --reserve 100`（触发线 0、保留预算 640、压力预算 3900）→ 退出码 0 且 `session/start` 里 `window` 与 `reserve` 照原样。确认它红（今天退出码 2、连日志都不建）。
- [x] 4.5 绿：启动校验从 `W − O − 65536 ≤ 0` 换成 `W − O ≤ 0`（design D5 的 apply 时改），stderr 那句话只给 `window` 与 `reserve` 两个数；4.4 变绿；既有的两条「配置期就失败」判据改数值后仍咬得住（`--window 4096 --reserve 8192` 与 `--window 4000 --reserve 4000`），`test_cli_serve.py` 同形那条改 `--window 8192 --reserve 8192`。

## 5. 既有判据与规格的措辞对齐（seam ① 与 ⑥）

- [x] 5.1 把 `tests/` 中断言「仍超过触发线」的溢出判据改判据对象为压力预算，逐条写明改了哪个数值；改完跑全量确认全绿，再用变异确认它们咬得住（不接受「改完就绿」）。**改完的清单在 4.3 与 2.2**（seam ① 三条、seam ⑥ 五条），全量全绿（413 passed / 5 skipped）。「咬得住」由 8.1 的 M1 与 M2 确认：M1 杀掉两条 seam ⑥ 判据，M2 杀掉六条 seam ⑥ 判据加 seam ① 四条加 `test_context_budget.py` 那条。
- [x] 5.2 跑 `tests/test_vocabulary_reachability.py` 确认没有新增 `code` 或 `stop_reason`、每个既有值仍可达。**实测**：两条判据都在全量里绿；本 change 没进任何新词。
- [x] 5.3 跑 `openspec validate --all --strict` 确认本 change 的两份 delta 结构合法。**实测**：13 项全绿（12 份主规格 + 本 change）。delta 实际是 ADDED 1 条、MODIFIED **5** 条（比计划多两条：启动校验那条与触发线公式那条，起因见 design D5 的 apply 时改）。

## 6. 真实端点验收（完成判据的第二半，ADR-0024）

- [x] 6.1 本机 Strata（`http://127.0.0.1:8300/v1`、`qwen3.8-flash-next-iq3_xxs`）跑 `--window 70000 --reserve 100` 读一个大文件：确认不再以退出码 4 结束、会话正常收尾，记下真实的预算读数与触发线。**实测**：会话 `00dfb231b9eb445e95d01be466d1d02a`，触发线 4364、保留预算 11200、压力预算 69900、估算 9058、读数 27444，退出码 0，零条 `compaction/summary`、零条 `error/context`。
- [x] 6.2 同一端点跑一次真溢出：确认退出码 4、`error/context` 的 `detail` 含三个数。**实测**：会话 `bfe6d7ae75eb422fa370cf088b04c304`，`--window 60000 --reserve 100`，退出码 4，`可遮蔽的那一段本身就装不下，预算读数 64276 超过压力预算 59900（触发线 0）`。**与计划不同**：计划写的 `--window 100000` 读 `huge.md` 撞不到溢出——`read` 默认只回 2000 行而 `huge.md` 有 3300 行，进上下文的只有约 61500 个估算 token，比压力预算 99900 小得多。
- [x] 6.3 跑一次「压缩发生了但仍不够」：小窗口 + 长摘要，如实记录**撞没撞到**那条字面分支；撞不到就写明撞不到与原因。**撞不到**（会话 `474d8e4c59b64f8ea97304cdfc0fba73` 在第一次装配就溢出，走「无可遮蔽」那条）。两条算术原因记进验收文档：真端点回报的 `input_tokens` 主导读数（中文实测约 1.3 字符/token，`CHARS_PER_TOKEN = 4` 低估三倍），以及摘要要超过压力预算的约八成才撞得到那条分支——真模型写摘要恰恰是把它缩短（实测 `tokens_after` 106）。
- [x] 6.4 观察记进 `docs/verification/fix-small-window-compaction-dead-zone-real-endpoint.md`。**顺带查出一件与代码无关的事**：venv 的 `minihns.exe` 启动器在 24000 个字符的参数下以 `0xC0000005` 崩、无输出无日志；同一参数走 `python.exe -m mini_harness.cli.main` 正常。溢出场次因此用「模型读一个大文件」而不是巨型 `-p`。

## 7. UAT 验收（完成判据的第三半，ADR-0025，人跑）

- [ ] 7.1 手册骨架已立：`docs/verification/fix-small-window-compaction-dead-zone-uat.md`（三场：小窗口能对话 / 真溢出看得见那一行 / 压缩看得见）。
- [ ] 7.2 等人坐在终端前跑完那三场并填回观察表；**表没填完本 change 不得归档、不得合入 `main`**。

## 8. 变异测试一轮

- [x] 8.1 五条变异跑全量并记进 `docs/verification/fix-small-window-compaction-dead-zone-mutation.md`：① 溢出判据改回触发线；② `pressure_budget` 写成 `window - reserve - 65536`；③ `detail` 去掉压力预算那个数；④ 「发不出摘要调用」重新直接通向溢出；⑤ 无可遮蔽时仍写 `compaction/summary`。每条必须被至少一条测试杀死，存活的补判据。**实测**：五条串行跑完，M1 杀 4 红、M2 杀 12 红、M3 杀 3 红、M4 杀 2 红、M5 杀 6 红，**没有存活的变异**，每条还原后 `git status --short -- <file>` 为空。④ 的改法落成一个可观察的形状：`if not body:` 返回 `ProviderFailure(PROVIDER_CONTEXT_OVERFLOW)` 而不是 `None`，于是日志里冒出 `error/model`。

## 9. Learning Gate

- [ ] 9.1 扫本轮证据写进 `docs/lessons.md` 收件箱；**收件箱已到上限 15 条，先消化再收新条**。
- [ ] 9.2 关闭 `docs/adr/0002` 的「判据欠账」里小窗口死区那条，立 ADR-0026（溢出判据与压缩触发线是两件事），并在 `docs/roadmap.md` 的 M5 行补一句「压缩仍不够」第一次可达。
