# Tasks

## 1. 压力预算这一处事实（seam ④ 的预算模块）

- [x] 1.1 红：写判据——`pressure_budget(window, reserve)` 对三组参数给出可断言的数：128000 / 8192 → 119808、70000 / 100 → 69900、100000 / 100 → 99900；且它与 `trigger_line`、`retain_line` 是三个不同的数（70000 / 100 下分别是 69900 / 4364 / 11200）。跑 `uv run pytest -q` 确认它红。
- [x] 1.2 绿：在 `context/budget.py` 提供 `pressure_budget`，与 `trigger_line` / `retain_line` 同一模块、同一份常量表，并从 `context/__init__.py` 导出；1.1 变绿且 `uv run mypy --strict src` 无新错。**1.1 的红是 `ImportError: cannot import name 'pressure_budget'`（整个文件收集失败）**；判据里 `retain_line` 只吃一个参数（`retain_line(70000) == 11200`），写错成两个参数时它先红在 `TypeError`。

## 2. 溢出判据换轨（seam ①）

- [x] 2.1 红：写死区判据——`window 70000 / reserve 100`，一份 fixture 让某回合的预算读数落在 `(4364, 11200]` 且对话体无可遮蔽内容 → 断言该回合有 `context/assembled` 与不带 `purpose` 的 `model/request`、日志里没有 `error/context`、没有 `compaction/summary`。确认它红（今天这条以退出码 4 收尾）。**实测**：`tests/test_turn_compaction.py::test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow`，fixture 是让模型 `read` 一份 24000 字符的文件（约 6000 个 token），红在 `error/context` 的 `detail` 结尾是「已超过触发线 4364」。**先踩空一次**：原本用「模型回复本身 100000 字符」做 fixture，它不是无可遮蔽——那一组工具往返被整段遮蔽了，`compaction/summary` 照样写出来（`tokens_after: 25`）；无可遮蔽要的是**整段对话体都装得进保留尾部**，于是改读大文件。
- [x] 2.2 绿：`turn_loop.py` 的溢出判定改用 `pressure_budget`（触发线只留「要不要压缩」那一处），2.1 变绿；既有的压缩、遮蔽、`compaction/summary` 形状判据全部仍绿。**换轨必然打破既有溢出 fixture**：seam ① 三条（`test_overflow_when_nothing_can_be_shadowed` prompt 100000 → 300000 字符；`test_an_overflow_closes_the_segment_not_the_session` prompt「任务」→ 20000 个字符；`test_one_compaction_then_overflow_...` 摘要 100000 → 300000 字符），seam ⑥ 五条见 4.3。判据对象没变，变的构造数值。
- [x] 2.3 红：写「压缩之后仍超压力预算」的判据——假 provider 写出一条摘要，重折叠后读数仍超过压力预算 → 断言 `error/context`（`CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`，且 `detail` 里同时出现预算读数、压力预算、触发线三个数。确认它红（**立计划时这条分支不可达；2.2 落地之后它已经可达**，见本条实测）。**实测**：`test_one_compaction_then_overflow_when_the_context_still_does_not_fit` 用 300000 字符的摘要打到那条分支，所以真正踩红的是三个数那一半：两条溢出判据都红在缺「触发线 4364」——`无可遮蔽的内容，预算读数 75015 已超过压力预算 69900` 与 `压缩之后预算读数 75024 仍超过压力预算 69900`。
- [x] 2.4 绿：两种 `detail` 措辞各带三个数（读数、压力预算、触发线），2.3 变绿；`uv run pytest -q` 全绿。

## 3. 摘要请求发不出去不再直接溢出（seam ①）

- [x] 3.1 红：写判据——遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过压力预算 → 断言日志里没有带 `purpose: compaction` 的 `model/request`、没有 `error/model`、没有 `compaction/summary`，且溢出那一条按这一回合的实际事实说话。**判据只断可达的那一半**（「该回合照常装配」那一半不可达，原因见本条实测），不可达那一半在规格里写成「除非预算读数本身超过压力预算」。确认它红（今天这条路无条件通向 `error/context` 且措辞说「无可遮蔽」）。**实测**：`test_a_shadowed_range_too_big_to_trim_sends_no_summary_request`（窗口 20000 / 预留 100：压力预算 19900、保留预算 3200、触发线 0；一条 100000 字符约 25000 个 token 的工具结果）。红只在一处——「没有 `purpose: compaction` 的请求」「没有 `error/model`」「没有 `compaction/summary`」三条本来就绿：2.2 换轨之后「发不出摘要请求」已经不再无条件通向溢出。红的是措辞：日志写着「无可遮蔽的内容」，可这一回合**有**可遮蔽的那一段，只是裁到只剩一组往返仍装不下。**顺带查清一件事**：这条 scenario 里「该回合照常装配」那一半在装配缝上走不到——摘要请求的预算就是压力预算，而遮蔽段是对话体的子集，遮蔽段本身就超压力预算时读数必然也超。
- [x] 3.2 绿：措辞跟着日志里的事实走，三种分支各带三个数（真写过摘要 / 给不出遮蔽范围 / 给得出却本身就装不下）；既有的「一段都装不下时不发请求」与「摘要调用失败沿用 provider 失败结果」两组判据仍绿。

## 4. 黑盒：小窗口能对话，真窗口仍溢出（seam ⑥）

- [x] 4.1 红：真实子进程跑 `minihns run --window 70000 --reserve 100` 带 2.1 那份 fixture → 断言退出码不是 4、日志里有 `context/assembled`。确认它红。**实测**：`tests/test_cli_run.py::test_a_dead_zone_window_still_holds_a_conversation`，prompt 24000 个字符（约 6000 个 token，落在 `(4364, 11200]`）。它写在 2.2 之后，红不是当场踩出来的——把 `turn_loop.py` 那一处判据临时改回 `reading > line` 跑一次，它红在 `assert 4 == 0`，改回来它绿。
- [x] 4.2 红（**构造改了，原判据做不到**）：原写的是「同一 fixture 配 `--window 60000 --reserve 100`（压力预算 59900 小于读数）→ 退出码 4」。做不到有两处：Windows 的命令行上限 32767 字符，59900 个 token 要 24 万字符的上下文，`-p` 传不进去；且那种窗口在旧的启动校验下先以退出码 2 结束。改成 `--window 4000 --reserve 100`（压力预算 3900 个 token）配 20000 个字符的 prompt → 退出码 4、日志里有 `error/context`。判据对象不变。
- [x] 4.3 绿：既有的「溢出映射到退出码 4」黑盒判据逐条改构造方式并写明——`test_cli_run.py` 的 `_TIGHT_WINDOW` 66000 → 4000、`_OVERFLOW_PROMPT` 2000 → 20000 个字符（两条判据：退出码 4 与「溢出发生在第一次装配之前仍可重放」）；`test_cli_chat.py` 两条 `--window 66000` → `4000`、`--append-system-prompt` 2000 → 20000 个字符；`test_cli_serve.py` 的溢出那条同改；`test_cli_replay.py` 的溢出日志改由「摘要自己 300000 个字符」造出；`test_vocabulary_reachability.py` 两条：prompt 100000 → 300000 个字符、窗口 4000 那条加 20000 个字符的 prompt。
- [x] 4.4 红：`minihns run --window 4000 --reserve 100`（触发线 0、保留预算 640、压力预算 3900）→ 退出码 0 且 `session/start` 里 `window` 与 `reserve` 照原样。确认它红（今天退出码 2、连日志都不建）。
- [x] 4.5 绿：启动校验从 `W − O − 65536 ≤ 0` 换成 `W − O ≤ 0`（design D5 的 apply 时改），stderr 那句话只给 `window` 与 `reserve` 两个数；4.4 变绿；既有的两条「配置期就失败」判据改数值后仍咬得住（`--window 4096 --reserve 8192` 与 `--window 4000 --reserve 4000`），`test_cli_serve.py` 同形那条改 `--window 8192 --reserve 8192`。

## 5. 既有判据与规格的措辞对齐（seam ① 与 ⑥）

- [x] 5.1 把 `tests/` 中断言「仍超过触发线」的溢出判据改判据对象为压力预算，逐条写明改了哪个数值；改完跑全量确认全绿，再用变异确认它们咬得住（不接受「改完就绿」）。**改完的清单在 4.3 与 2.2**（seam ① 三条、seam ⑥ 五条），全量全绿（413 passed / 5 skipped）。「咬得住」由 8.1 的 M1 与 M2 确认：M1 杀掉两条 seam ⑥ 判据，M2 杀掉七条 seam ⑥ 判据（`test_cli_chat.py` 两条、`test_cli_run.py` 四条、`test_cli_serve.py` 一条）加 seam ① 四条加 `test_context_budget.py` 那条，共 12 红。
- [x] 5.2 跑 `tests/test_vocabulary_reachability.py` 确认没有新增 `code` 或 `stop_reason`、每个既有值仍可达。**实测**：两条判据都在全量里绿；本 change 没进任何新词。
- [x] 5.3 跑 `openspec validate --all --strict` 确认本 change 的两份 delta 结构合法。**实测**：13 项全绿（12 份主规格 + 本 change）。delta 实际是 ADDED 1 条、MODIFIED **5** 条（比计划多两条：启动校验那条与触发线公式那条，起因见 design D5 的 apply 时改）。

## 6. 真实端点验收（完成判据的第二半，ADR-0024）

- [x] 6.1 本机 Strata（`http://127.0.0.1:8300/v1`、`qwen3.8-flash-next-iq3_xxs`）跑 `--window 70000 --reserve 100` 读一个大文件：确认不再以退出码 4 结束、会话正常收尾，记下真实的预算读数与触发线。**实测**：会话 `00dfb231b9eb445e95d01be466d1d02a`，触发线 4364、保留预算 11200、压力预算 69900、估算 9058、读数 27444，退出码 0，零条 `compaction/summary`、零条 `error/context`。
- [x] 6.2 同一端点跑一次真溢出：确认退出码 4、`error/context` 的 `detail` 含三个数。**实测**：会话 `bfe6d7ae75eb422fa370cf088b04c304`，`--window 60000 --reserve 100`，退出码 4，`可遮蔽的那一段本身就装不下，预算读数 64276 超过压力预算 59900（触发线 0）`。**与计划不同**：计划写的 `--window 100000` 读 `huge.md` 撞不到溢出——`read` 默认只回 2000 行而 `huge.md` 有 3300 行，进上下文的只有约 61500 个估算 token，比压力预算 99900 小得多。
- [x] 6.3 跑一次「压缩发生了但仍不够」：小窗口 + 长摘要，如实记录**撞没撞到**那条字面分支；撞不到就写明撞不到与原因。**撞不到**（会话 `474d8e4c59b64f8ea97304cdfc0fba73` 在第一次装配就溢出，走「无可遮蔽」那条）。两条算术原因记进验收文档：真端点回报的 `input_tokens` 主导读数（中文实测约 1.3 字符/token，`CHARS_PER_TOKEN = 4` 低估三倍），以及摘要要超过压力预算的约八成才撞得到那条分支——真模型写摘要恰恰是把它缩短（实测 `tokens_after` 106）。
- [x] 6.4 观察记进 `docs/verification/fix-small-window-compaction-dead-zone-real-endpoint.md`。**顺带查出一件与代码无关的事**：venv 的 `minihns.exe` 启动器在 24000 个字符的参数下以 `0xC0000005` 崩、无输出无日志；同一参数走 `python.exe -m mini_harness.cli.main` 正常。溢出场次因此用「模型读一个大文件」而不是巨型 `-p`。

## 7. UAT 验收（完成判据的第三半，ADR-0025，人跑）

- [x] 7.1 手册骨架已立：`docs/verification/fix-small-window-compaction-dead-zone-uat.md`（三场：小窗口能对话 / 真溢出看得见那一行 / 压缩看得见）。**两轴之后重算过场次数值**：U2 的 `--window 40000 --reserve 100` 压力预算 39900、触发线 0，读 `huge.md`（`read` 只回 2000 行 ≈ 61,500 个估算 token）撞的是「可遮蔽的那一段本身就装不下」；U1 读 `big.md` 读数约 6 万、在压力预算 69900 之内。两场各写明期望的形状（不是判据，是让人知道看没看对）。
- [ ] 7.2 等人坐在终端前跑完那三场并填回观察表；**表没填完本 change 不得归档、不得合入 `main`**。

## 8. 变异测试一轮

- [x] 8.1 五条变异跑全量并记进 `docs/verification/fix-small-window-compaction-dead-zone-mutation.md`：① 溢出判据改回触发线；② `pressure_budget` 写成 `window - reserve - 65536`；③ `detail` 去掉压力预算那个数；④ 「发不出摘要调用」重新直接通向溢出；⑤ 无可遮蔽时仍写 `compaction/summary`。每条必须被至少一条测试杀死，存活的补判据。**实测**：五条串行跑完，M1 杀 4 红、M2 杀 12 红、M3 杀 3 红、M4 杀 2 红、M5 杀 6 红，**没有存活的变异**，每条还原后 `git status --short -- <file>` 为空。④ 的改法落成一个可观察的形状：`if not body:` 返回 `ProviderFailure(PROVIDER_CONTEXT_OVERFLOW)` 而不是 `None`，于是日志里冒出 `error/model`。

## 9. Learning Gate

- [x] 9.1 扫本轮证据写进 `docs/lessons.md` 收件箱；**收件箱已到上限 15 条，先消化再收新条**。**实测**：先消化——关闭两条（L-050 / L-043）、合并三组（L-041 → L-036、L-052 → L-048、L-037 → L-039，家族头写在被合并的那条上）、补证据六条（L-019 / L-039 / L-045 / L-047 / L-049 / L-054）；再收三条新的：L-055（判据晚于实现时用「临时改回旧实现 → 跑 → 确认红 → 还原 → 确认工作树干净」实证）、L-056（写场景先算每个断言在哪个 seam 可达，不可达那一半删掉或写成「除非」）、L-057（真端点窗口数值按 provider 回报倒推、按 `read` 的行数上限算；撑上下文用大文件不用巨型 `-p`——venv 的 `minihns.exe` 在 24000 字符参数下 `0xC0000005` 崩）。**消化完的收件箱 12 条**，上限之内。AGENTS.md 本轮不晋升（没有一句话规则比得上现有的「判据只断可达那一半」与「变异必须改变可观察行为」）。
- [x] 9.2 关闭 `docs/adr/0002` 的「判据欠账」里小窗口死区那条，立 ADR-0026（溢出判据与压缩触发线是两件事），并在 `docs/roadmap.md` 的 M5 行补一句「压缩仍不够」第一次可达。**实测**：`docs/adr/0026-overflow-is-the-pressure-budget-not-the-trigger-line.md`（三个被否掉的选项写在里面：删掉 65536、抬高窗口下限到 78138、保留旧校验只改判据）；ADR-0016 尾部加一句「本条的触发线公式被 ADR-0026 收窄」，公式本身不变；`docs/roadmap.md` 的 M5 行与完成判据那两条（三半 / UAT 是第五道门禁）都改了。

## 10. `code-review` 两轴之后的裁决（seam ① 与规格）

两轴跑在 `db61a20...HEAD`（七个提交）之上。Standards 轴三条硬违反、六条判断项；Spec 轴四条「勾与证据对不上」与两条规格缺口。逐条落在这里。

- [x] 10.1 红：provider 报出的那条溢出的 `detail` 也要给三个数——`test_a_provider_reported_overflow_detail_carries_the_three_numbers`（窗口 70000 / 预留 100，provider 自己报 `PROVIDER_CONTEXT_OVERFLOW`、无可遮蔽）。**当场踩红**：`assert "压力预算 69900" in 'provider 报出上下文超限且无可遮蔽的内容：HTTP 400 上下文超限'`。这是 Spec 轴查出的缺口：delta 那条 MODIFIED 写着 `detail` SHALL 含三个数，而两条触发路径共用 `_context_overflow`，只有估算那一侧给了。
- [x] 10.2 绿：`_budget_triple` 一处给出那三个数，`_retry_after_provider_overflow` 的两个出口都接上它。装配点那三种措辞不动——它的措辞由 delta 钉着、真端点验收文档引的是原文。
- [x] 10.3 「一处事实」补全（Spec 轴 (a)1 与 Standards 轴的 Duplicated Code）：`_compact_if_over_line` 的 `summary_budget` 改调 `pressure_budget`，`trigger_line` 内部那一处 `W - O` 也改调它。改完 `W - O` 在 `src/` 里只有 `pressure_budget` 一处字面。
- [x] 10.4 delta 补第 6 条 MODIFIED（Spec 轴 (a)2）：「摘要调用失败沿用 provider 失败结果」——主规格那句「摘要调用**没有发出**时不是 provider 失败：那条路通向 `CONTEXT_WINDOW_EXCEEDED`」与 scenario「没发出的摘要调用不产生 provider 失败」的 THEN 按 design D4 改；两条既有 scenario 名保留。不补这条，sync 之后主规格与本 delta 自相矛盾。
- [x] 10.5 delta 的 ADDED 措辞收窄（Spec 轴 (c)3）：「并只用它判定上下文溢出」改成「上下文装不装得下 SHALL 只问它」，并写明端点自己报出的超限是另一条触发路径（照 ADR-0019，由回报触发、不由压力预算判定）；MODIFIED「压缩救不了时…」补一句「两条触发路径共用同一串三个数」。delta 结构复核：ADDED 1 条、MODIFIED 6 条，`openspec validate --all --strict` 13/13。
- [x] 10.6 两轴改动之后重跑变异：M2（`pressure_budget` 写歪）现在还要打到 `summary_budget` 与 `_budget_triple`，M3（去掉压力预算那个数）的锚点从三处变成四处；M6 = 把 provider 出口那串三个数摘掉，10.1 那条判据在 10.2 之前红过就是它的实证。**实测**：M2 **28 红**（第一轮 12 红）、M3 **4 红**（第一轮 3 红，多杀的是新判据）、M6 **1 红**（正是新判据），**没有存活的变异**；每条还原后 `git status --short -- <file>` 为空，整轮跑完 `git status --short -- src tests` 为空。记录在 `docs/verification/fix-small-window-compaction-dead-zone-mutation.md` 的「第二轮」。M2 从 12 红涨到 28 红是「一处事实」成立的证据：`trigger_line` 与 `summary_budget` 改调 `pressure_budget` 之后，写歪一处就打歪触发线那两条判据与摘要请求预算那一族判据。
- [x] 10.7 记账进 `docs/adr/0002`：`cancel.is_set()` 时既不压缩也不判溢出（既有豁免，delta 未处理）；`_compact_if_over_line` 的 `None` 兼表「无可遮蔽」与「裁到最小仍装不下」，调用方只能重算 `shadowed_range` 分辨；`(window, reserve)` 在四处结伴（可能的 Data Clumps）；测试里 70000 / 100 与那三个数硬编码在五个文件。**实测**：四条连同「压缩之后」在真端点不可达、delta 那条 scenario 有一半不可达，都写进 `docs/adr/0002` 的「`fix-small-window-compaction-dead-zone` 的判据欠账」一节；处理时点分别标在 M10（取消信号那一格，与 ADR-0013 一起判）与 M11（预算模块的整理）。本轮不动它们（四规 #3）。
