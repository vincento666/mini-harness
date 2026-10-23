> **前置**：本 change 的分支从 `fix-small-window-compaction-dead-zone` 的 tip 起，判据照它的压力预算（`W − O`）与那三个数的 `detail` 写。它的 UAT 那一半（7.2）没填完之前，本 change 不 apply、不归档。

## 1. 判据先写（seam ④：日志追加与折叠 / 预算读数）

- [ ] 1.1 压缩之前的回报不充当压缩之后的读数：一份前缀里有一条 `input_tokens` 很大的回合级 `model/response`、其后有一条 `compaction/summary`，装配点的读数是估算值而不是那条回报（先确认它在现状下红）
- [ ] 1.2 压缩之后新的回报重新参与校准：摘要之后再写一条更大的回合级回报，之后的装配点用它
- [ ] 1.3 既有的「同一份前缀两次读数相同」在新算法下照旧绿（不许改松）
- [ ] 1.4 既有的「被遮蔽的读数不参与校准」「摘要调用的读数不参与校准」两条照旧绿

## 2. 判据先写（seam ① 回合循环 / seam ⑥ CLI 黑盒）

- [ ] 2.1 seam ①：遮蔽掉的那段折出的消息估算大于摘要估算时，那条 `compaction/summary` 的 `tokens_after` 小于 `tokens_before`
- [ ] 2.2 seam ①：遮蔽之后读数落回触发线之下、该次装配照常写 `context/assembled` 与不带 `purpose` 的 `model/request`（这条是「每问必溢出」的根因判据）
- [ ] 2.3 seam ①：请求级压缩（provider 报出上下文超限）写出的那条 `compaction/summary` 同样把校准的界往前推
- [ ] 2.4 seam ⑥：真实子进程跑一次带 `usage.input_tokens` 的 fixture（形状照 `.tmp/uat-repro/fixture2.json`；补的是形状不是验收，ADR-0022），stderr 上 `[遮蔽] … tokens <前> 降至 <后>` 那一行满足 `后 < 前`
- [ ] 2.5 seam ⑥：以 `CONTEXT_WINDOW_EXCEEDED` 收尾的日志 `minihns replay` 退出码 0（新读数算法下重跑，不许出现 `REPLAY_MISMATCH`）

## 3. 实现

- [ ] 3.1 `context/budget.py` 的 `budget_reading`：校准那一路加 `seq` 界（该点之前最后一条 `compaction/summary` 的 `seq`；没有摘要记录时不设界）
- [ ] 3.2 确认 `loop/turn_loop.py` 的 `tokens_after` 不需要改（改了就是绕过了 3.1）
- [ ] 3.3 确认 `budget_reading` 仍是日志前缀的纯函数：不引入进程内缓存、不读该点之后的事件

## 4. 门禁与规格

- [ ] 4.1 四道门禁全绿（ruff format / ruff check / mypy --strict / coverage --fail-under=95）
- [ ] 4.2 `openspec validate --all --strict` 全绿

## 5. 两轴 review

- [ ] 5.1 Standards 轴：只动 `budget_reading` 一处；`turn_loop.py` 与 `context/projection` 不许顺手改
- [ ] 5.2 Spec 轴：delta 里每一条 scenario 对上一条判据，逐条核；对不上的记账

## 6. 收尾四项（ADR-0024 + ADR-0025）

- [ ] 6.1 真实端点验收：接上真实端点把本 change 的判据跑一遍——**这条缺陷只在真实端点上出现，这一半是本 change 的核心**；记录进 `docs/verification/fix-post-compaction-budget-reading-real-endpoint.md`
- [ ] 6.2 UAT 验收（人跑）：场次表在 `docs/verification/fix-post-compaction-budget-reading-uat.md`（propose 时已立骨架）。**那张表没填完本 change 不得归档、不得合入 `main`**
- [ ] 6.3 变异测试一轮：记录进 `docs/verification/fix-post-compaction-budget-reading-mutation.md`；变异要改的是「界」的可观察行为（例如把界挪到摘要之后一条记录、或干脆不设界），存活的补判据
- [ ] 6.4 Learning Gate：扫本轮证据写进 `docs/lessons.md` 收件箱；ADR-0029 落字（低估真实用量这条取舍）；归档后跑 `agents-md-slim`
