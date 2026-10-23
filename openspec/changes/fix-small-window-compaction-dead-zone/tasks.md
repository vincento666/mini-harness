# Tasks

## 1. 压力预算这一处事实（seam ④ 的预算模块）

- [ ] 1.1 红：写判据——`pressure_budget(window, reserve)` 对三组参数给出可断言的数：128000 / 8192 → 119808、70000 / 100 → 69900、100000 / 100 → 99900；且它与 `trigger_line`、`retain_line` 是三个不同的数（70000 / 100 下分别是 69900 / 4364 / 11200）。跑 `uv run pytest -q` 确认它红。
- [ ] 1.2 绿：在 `context/budget.py` 提供 `pressure_budget`，与 `trigger_line` / `retain_line` 同一模块、同一份常量表，并从 `context/__init__.py` 导出；1.1 变绿且 `uv run mypy --strict src` 无新错。

## 2. 溢出判据换轨（seam ①）

- [ ] 2.1 红：写死区判据——`window 70000 / reserve 100`，一份 fixture 让某回合的预算读数落在 `(4364, 11200]` 且对话体无可遮蔽内容 → 断言该回合有 `context/assembled` 与不带 `purpose` 的 `model/request`、日志里没有 `error/context`、没有 `compaction/summary`。确认它红（今天这条以退出码 4 收尾）。
- [ ] 2.2 绿：`turn_loop.py` 的溢出判定改用 `pressure_budget`（触发线只留「要不要压缩」那一处），2.1 变绿；既有的压缩、遮蔽、`compaction/summary` 形状判据全部仍绿。
- [ ] 2.3 红：写「压缩之后仍超压力预算」的判据——假 provider 写出一条摘要，重折叠后读数仍超过压力预算 → 断言 `error/context`（`CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`，且 `detail` 里同时出现预算读数、压力预算、触发线三个数。确认它红（今天这条分支不可达）。
- [ ] 2.4 绿：实现两种 `detail` 措辞（「压缩之后」与「无可遮蔽」）各带三个数，2.3 变绿；`uv run pytest -q` 全绿。

## 3. 摘要请求发不出去不再直接溢出（seam ①）

- [ ] 3.1 红：写判据——遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过压力预算 → 断言日志里没有带 `purpose: compaction` 的 `model/request`、没有 `error/model`，且当预算读数本身不超过压力预算时该回合照常写 `context/assembled`。确认它红（今天这条路无条件通向 `error/context`）。
- [ ] 3.2 绿：把「发不出摘要调用」与「溢出」解耦，3.1 变绿；既有的「一段都装不下时不发请求」与「摘要调用失败沿用 provider 失败结果」两组判据仍绿。

## 4. 黑盒：小窗口能对话，真窗口仍溢出（seam ⑥）

- [ ] 4.1 红：真实子进程跑 `minihns run --window 70000 --reserve 100` 带 2.1 那份 fixture → 断言退出码不是 4、日志里有 `context/assembled`。确认它红。
- [ ] 4.2 红：同一 fixture 配 `--window 60000 --reserve 100`（压力预算 59900 小于读数）→ 断言退出码 4、日志里有 `error/context` 且 `detail` 含三个数。确认它红。
- [ ] 4.3 绿：4.1 与 4.2 变绿；既有的「溢出映射到退出码 4」黑盒判据仍绿（它的构造方式若依赖触发线，如实改判据对象并写明）。

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
