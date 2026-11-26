# fix-case-insensitive-path-keys 变异测试记录（2026-11-26）

基线：全量 928 passed / 6 skipped；本 change 相关 seam ③④ 33 passed / 1 skipped。

| 变异 | 改法 | 结果 |
|---|---|---|
| M1 去掉规范化 | `_folded_existing_prefix` 开头直接 `return path` | **被杀死**——4 条全红：`test_a_differently_cased_path_folds_only_where_paths_fold`、`test_path_key_normalizes_case_only_when_the_filesystem_does`、`test_a_new_file_keeps_the_given_spelling_while_existing_parents_fold`、`test_the_same_file_written_two_ways_gets_one_path_key` |
| M2 去掉缓存 | 每次调用重新 `iterdir()`，不走 `_fold_cache` | **被杀死**——`test_a_second_path_key_for_the_same_directories_hits_the_cache` 红 |

还原后复核：seam ③④ 33 passed / 1 skipped，回到基线（还原前 `git status` 确认无未提交改动被卷入）。

无存活变异，无覆盖缺口。
