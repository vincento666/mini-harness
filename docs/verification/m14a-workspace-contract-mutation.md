# m14a-workspace-contract 变异测试

**日期**：2026-11-13。做法：改坏一处 → 跑定向判据 → 还原 → `git status` 复查。定向文件 `tests/test_contracts.py`（14 条）。

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | 顺序反了 | `_candidates` 返回「项目 → 用户全局」 | 被杀：`test_two_contracts_render_global_then_project` |
| M2 | 不按内容去重 | 去重条件换成 `if False` | 被杀：`test_identical_content_renders_only_the_global_one` |
| M3 | 不转义框架字符 | `_escape` 原样返回 | 被杀：`test_the_framework_tag_in_content_is_escaped` |
| M4 | 超预算不截断 | 去掉 `_truncate` 调用 | 被杀：`test_over_budget_drops_the_global_segment_before_truncating` |
| M5 | 指纹不含正文 | `_render_digest` 的 `text` 置空 | **存活（等价）**：每层 digest 仍能发现内容变化 |
| M5b | 指纹不含每层 digest/字节 | scopes 只留 `[scope, path]` | **存活（等价）**：正文仍在指纹里 |
| M5c | 指纹只剩路径 | 两个信号都去掉 | 被杀：`test_a_changed_contract_appends_a_replacement` |
| M6 | 不注入契约 | 去掉 `_maybe_emit_contracts` 调用 | 被杀：`test_the_contract_is_injected_before_the_first_assembled` |
| M7 | 文件消失不退休 | 移除分支直接 `return None` | 被杀：`test_removing_both_files_appends_a_removal_notice` |

**基线**：还原后 `tests/test_contracts.py` 14 passed，工作区干净。

## 两条存活变异怎么算

M5 与 M5b 各自只去掉指纹的一路信号，另一路仍然能发现变化，所以行为等价——按 `AGENTS.md` 的判据是 dud mutant，不算覆盖缺口。M5c 把两路都去掉后被杀死，证明「指纹确实在跟着内容变」。

## 已知偶发

`tests/test_subagent.py::test_two_subagents_run_in_parallel` 在并行负载下偶发（实测 0.586 vs 阈值 0.55，单跑通过）；与本 change 的两次文件 stat 无关，但记在这里。

## Learning Gate

**NO-PROMOTION**：本轮唯一可复用信号是「指纹有两路独立信号时，单路变异会存活；要判它是否空转，得把两路都去掉（M5c）」——这条已经写进上面的「两条存活变异怎么算」，属于变异判读的细节，不够格占 AGENTS.md 的一句话额度。`docs/lessons.md` 收件箱已 31 条，先消化再收。
