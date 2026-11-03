# Tasks

## 1. EventLog 续写

- [ ] 1.1 seam ④：`test_open_reads_last_seq_and_appends_next`——最后 seq 7，新 append 是 8
- [ ] 1.2 seam ④：空日志从 0 开始

## 2. resume

- [ ] 2.1 seam ⑥：`test_chat_resume_appends_to_the_same_log`——不新建 session/start
- [ ] 2.2 seam ⑥：`test_resume_replay_is_pointwise_equal`
- [ ] 2.3 seam ⑥：`test_resume_closes_hard_kill_gap_without_rewriting`
- [ ] 2.4 seam ⑥：`test_host_resume_uses_existing_session`

## 3. schema 迁移

- [ ] 3.1 seam ④：`test_adjacent_schema_migration`
- [ ] 3.2 seam ④：`test_schema_skip_is_rejected_without_writing`

## 4. session index

- [ ] 4.1 seam ⑥：`test_host_lists_ended_sessions_after_restart`
- [ ] 4.2 seam ⑥：`test_host_index_does_not_expose_log_download`

## 5. fold 缓存与三态

- [ ] 5.1 seam ④：`test_fold_cache_follows_new_log_seq`
- [ ] 5.2 seam ④：`test_fold_cache_corruption_falls_back`
- [ ] 5.3 seam ④：`test_projection_marks_in_context_shadowed_log_only`
- [ ] 5.4 seam ④：`test_overlapping_shadow_ranges_merge`

## 6. 文档与 UAT

- [ ] 6.1 文档：存储/恢复/缓存底稿更新
- [ ] 6.2 UAT 骨架：`docs/verification/m11-storage-resume-and-projection-cache-uat.md`

## 7. 收尾四项

- [ ] 7.1 真实端点验收
- [ ] 7.2 UAT 验收（人跑）
- [ ] 7.3 变异测试一轮
- [ ] 7.4 Learning Gate
