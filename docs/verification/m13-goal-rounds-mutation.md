# m13-goal-rounds 变异测试

**日期**：2026-11-19。macOS，Python 3.13.3，pytest 9.1.1。逐条手工变异 → 跑对应判据 → `git checkout --` 还原；六条全部被杀，工作区事后与提交一致。

## 变异清单

| # | 变异 | 位置 | 判据命令 | 结果 |
|---|---|---|---|---|
| M1 | 轮次多记一：`rounds_started = round_number + 1` | `goals.advance_round` | `pytest tests/test_goal_rounds.py` | **杀掉**：4 条（三轮顺序、完成后不再开段、取消、provider 失败） |
| M2 | 驱动不看武装位：去掉 `next_round` 里的 `or not armed` | `loop/goal_driver.next_round` | `pytest tests/test_goal_rounds.py tests/test_chat_goal_driver.py` | **杀掉**：2 条（纯函数判据、`--resume` 不自动续跑） |
| M3 | `pause` / `complete` / `blocked` 不解除武装 | `tools/goal._update_goal` | `pytest tests/test_goal_update.py` | **杀掉**：3 条（暂停、完成、阻塞各一） |
| M4 | REPL 判定永假：`armed=False` | `cli/main.py` 的段后驱动 | `pytest tests/test_chat_goal_driver.py` | **杀掉**：2 条（两轮续跑、`/goal resume` 后续跑） |
| M5 | 每个回合都扣轮次：去掉 `offset == 0` | `loop/turn_loop.py` 的计数点 | `pytest tests/test_goal_rounds.py tests/test_goal_replay.py` | **杀掉**：2 条（专用判据 `test_a_round_with_two_turns_deducts_only_once` + `test_a_completed_goal_no_longer_opens_segments`） |
| M6 | 段首不清待办表：删掉 `segment/start → []` | `events/projection.py` | `pytest tests/test_todo_read_back.py tests/test_goal_projection.py` | **杀掉**：4 条（新段读回为空、goal 轮同样清、旧日志同样清） |

## 观察

- **M1 与 M4 各被 4 / 2 条判据抓住**，说明「轮次只由准入推进」和「REPL 只在武装时续跑」不是单点断言撑着的。
- ~~M5 只被一条用例杀死~~（2026-11-19 补）：新增 `test_a_round_with_two_turns_deducts_only_once`——两轮各两回合（先 `todo` 再收尾）、从不标完成，断言每个轮次段（`segment/end` 之前）恰有一条 `goal/updated` 且 `rounds_started` 等于轮号。复验 M5 时它给出 `[1, 1] != [1]`（同一轮写了两次同样的额度），与既有那条用例一起成为两条独立判据。
  - 已尝试补一条「每个轮次段恰一条 `goal/updated`」的断言，但 `complete` 也会写 `goal/updated`，按事件条数数会把正常收尾误判成多扣，遂撤回。
  - 要真正钉死「一轮一扣」，需要一个「轮次段两回合且不完成」的专用夹具，断言最终 `rounds_started` 仍为 1；这条留作后续补强（不阻塞本 change）。
- **M6** 是 `get_todos` 与投影的生命周期判据；四条用例分布在新读回与 goal 投影两处，说明这条语义没有只靠一条测试。

## 残余风险

- ~~M5 的单点覆盖~~（已由专用判据补上，见上）。
- 未做变异的部分：真实端点的缓存/计量、`--resume` 的日志重建路径；这两处靠 6.1 与 UAT 场次 4 覆盖。
