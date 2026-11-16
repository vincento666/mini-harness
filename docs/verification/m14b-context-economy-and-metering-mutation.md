# m14b-context-economy-and-metering 变异测试

**日期**：2026-11-16。做法：改坏一处 → 跑定向判据 → 还原 → `git status` 复查。

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | 阈值少一 | `<= PRUNE_CHARS` 改成 `<` | 被杀：`test_the_threshold_is_inclusive`（8192 恰好不该剪） |
| M2 | 头部预算改小 | `HEAD_CHARS 4096 → 1024` | 被杀：`test_head_and_tail_budgets_are_exact` |
| M3 | 尾部预算改小 | `TAIL_CHARS 1024 → 512` | 被杀：同上 |
| M4 | spill 不落盘 | 去掉 `target.write_text` | 被杀：`test_a_long_result_is_pruned_and_spilled`（文件与 digest 对不上） |
| M5 | payload 不写 pruned | `result_payload.update` 改成 `pass` | 被杀：`test_the_payload_carries_pruned_metadata` |
| M6 | 同回合先者胜 | `per_turn[turn_id] = usage` 改成 `setdefault` | 被杀：`test_the_last_response_of_a_turn_wins` |
| M7 | 忽略缓存命中 | `input_tokens = prompt` | 被杀：`test_stream_usage_carries_deepseek_cache_buckets` |
| M8 | 缺价目表当成 0 元 | `return None` 改成 `return Pricing()` | 被杀：`test_pricing_is_none_without_a_table` |

**结果**：8 个变异全部被杀，无覆盖缺口。还原后定向判据全绿、工作区干净。

## Learning Gate

**NO-PROMOTION**。本轮有两个可复用信号，但都已在代码或规格里自证，不够格占 AGENTS.md 的一句话额度：

1. **通用层要先看既有面的预算契约**：剪枝初版套到 `read` 上，把 `test_file_read` 的两条判据弄红——`read` 有自己的 capped window + `offset` 续读约定（M10 判据写明「没有 spill」）。既有测试直接抓住了这个回归，说明「不改相邻代码」的边界由判据守着，不靠记性。
2. **四桶必须不重叠**：adapter 的 `input_tokens` 改成「未缓存」后，metering 里原来的「减去 cache」就变成双重扣减。这条语义已写进 `Usage` 的 docstring 与 design，并被 `test_stream_usage_*` 与 `test_four_buckets_are_summed` 两边钉住。

`docs/lessons.md` 收件箱已 31 条，超过 15 条的自律线；下次收尾先归并，再考虑把第 1 条晋升。
