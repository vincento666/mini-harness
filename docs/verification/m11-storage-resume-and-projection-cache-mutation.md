# M11 变异测试

**日期**：2026-11-05。每个变异改源码、跑指定判据、记录红，再用编辑还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 缓存 key 不含内容指纹 | key 最后一位改成空串 | `test_fold_cache_does_not_collide_on_same_seq_with_different_content` | 红：同 seq 不同内容拿到旧 messages |
| M2 | schema 接受任意跳版 | `N-1` 判断改成恒真 | `test_schema_skip_is_rejected_without_writing` | 红：version 2 被当成功 |
| M3 | 损坏缓存不检查类型 | `isinstance` 改成 `is not None` | `test_fold_cache_corruption_falls_back` | 红：`AttributeError` |

**结论**：3 个有效变异全部被杀死；还原后回到基线。
