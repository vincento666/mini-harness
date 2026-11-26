# Tasks

## 1. 路径键按文件系统行为规范化

- [ ] 1.1 seam ③④：`test_a_differently_cased_path_folds_only_where_paths_fold` 改成按实测行为分支（折叠的文件系统上 `OK / OK`，不折叠的上 `PATH_NOT_FOUND / WRITE_WITHOUT_READ`）
- [ ] 1.2 seam ③④：`test_path_key_normalizes_case_only_when_the_filesystem_does`——同一文件两种写法得到同一个键；大小写敏感目录里的两个文件得到两个键
- [ ] 1.3 seam ③④：新文件的父目录前缀被规范化、文件名保持原样（与「新文件不需要先读」共存）

## 2. 成本

- [ ] 2.1 seam ③④：同一目录的第二次 `path_key` 命中缓存（判据：第二次不重新列举目录）

## 3. 收尾四项

- [ ] 3.1 真实端点验收：一次真实 `run` 的读写走通（这次修复不产生新的模型交互，只验证端到端没坏）
- [ ] 3.2 UAT 验收（人跑）：macOS 上「读一种写法、改另一种写法」办成一件真事
- [ ] 3.3 变异测试一轮：至少一条变异（去掉规范化）被 1.1 杀死
- [ ] 3.4 Learning Gate
