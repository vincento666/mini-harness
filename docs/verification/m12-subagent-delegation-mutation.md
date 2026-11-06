# M12 变异测试

**日期**：2026-11-06。每个变异改源码、跑指定判据、记录红，再用 `git checkout` 还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 深度检查失效 | `if depth > MAX_DEPTH` → `if depth > MAX_DEPTH + 99` | `test_depth_exceeded_is_a_result` | 红：子代理真的派出了孙代理，结果不是 `DEPTH_EXCEEDED` |
| M2 | 容量检查失效 | `if delegation.active >= delegation.max_active` → `+ 99` | `test_activation_limit_is_a_result` | 红：第 9 个没有被拒，反倒建出了子会话 |
| M3 | 父取消不传给子会话 | 删掉 `except CancelledError: child_cancel.set()` | `test_parent_cancel_cancels_the_child` | 红：子会话跑到慢命令自己结束（5.08 s），`session/end` 不是 `ABORTED` |
| S1 | 取消桥（存活） | 删掉 `_forward_cancel` 与它的 `create_task` | 全部判据仍绿 | **存活**：父取消本来就以 `CancelledError` 到达执行器，桥是第二条同义路径 |

**S1 的处理**：存活变异不是补一条测试，而是删掉冗余实现——`subagent` 不再订阅父的取消事件，取消传播只剩执行器里那一行；`DispatchContext.cancel` 随之删除（提交 `7372e05`）。补测试只会把死路径变成「有测试守着的死路径」。

**结论**：3 个有效变异全部被杀死；1 个存活变异定位到冗余实现并删除，还原后回到基线（`tests/test_subagent.py` 10 passed）。
