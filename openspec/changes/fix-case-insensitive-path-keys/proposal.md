# Proposal

## Why

写前必读与 CAS 用「解析后的路径字符串」当键（`fences.path_key`）。这个键只在 `os.name == "nt"` 时折大小写，于是**大小写不敏感但不是 Windows 的文件系统**（macOS 的 APFS 默认就是）会把同一个文件记成两个键：先 `read` `notes/plan.md`、再 `edit` `Notes/Plan.MD` 会被判 `WRITE_WITHOUT_READ`，而这两个写法打开的是同一个文件。M12 在 macOS 上实测复现（`573 passed / 2 failed` 里的那条）。

## What Changes

- **路径键按文件系统行为折大小写，而不是按操作系统名字猜**：`path_key` 把**已存在的前缀**规范成磁盘上的写法（目录列举 + `casefold` 比对），新建部分保持调用给的写法。
- Windows 的 `normcase` 行为不变。
- 判据改成「按这份文件系统的实测行为分支」，而不是 `os.name == "nt"`；CI 的 Windows 与 Linux 各跑一支，macOS 本机跑折叠那一支。

## Capabilities

### Modified Capabilities

- `file-tools`：写前必读与 CAS 的「同一路径」由路径键的文件身份决定，而不是字符串逐字相等。

## Impact

- 代码：`tools/fences.py`（`path_key` 的规范化与每目录缓存）。
- 测试：seam ③④（同一文件的不同写法、大小写敏感文件系统上的两支）。
- 非目标：绕过符号链接的判定（`realpath` 已经处理）、大小写敏感文件系统上的行为改变。
- 风险：每次 `path_key` 多一次「深度 × 目录项」的规范化；用每目录缓存兜住，目录内容变化时条目只增不减（新增文件不影响已有映射）。
