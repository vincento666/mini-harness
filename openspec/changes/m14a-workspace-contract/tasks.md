# Tasks

## 1. 发现与渲染（seam ①）

- [x] 1.1 `contracts.py`：读两个 scope、trim 去重、`Instructions from:` 分段、路径只写 `~` 与相对名
- [x] 1.2 预算：16 KiB 上限、先丢用户全局再截断项目、`Workspace instruction budget` 通知、单文件 1 MiB 上限
- [x] 1.3 转义 `</system-reminder>` 与空链（两份都没有时不产出消息）

## 2. 注入与刷新（seam ①④）

- [x] 2.1 首 turn 在 `context/assembled` 之前注入 `source: "workspace-instructions"` 的 `user/message`
- [x] 2.2 每 turn 观察：指纹未变不重发；变化追加完整替换；两份都没了追加 `Instructions removed:` 并退休
- [x] 2.3 payload 记 `digest` 与 `scopes`（`scope` / `path` / `digest` / `bytes` / `truncated`），正文不进 `session/start`

## 3. 回放与子会话（seam ④⑦）

- [x] 3.1 `replay` 逐点相等，且不重读磁盘
- [x] 3.2 子会话各自注入一份；父会话不受影响

## 4. CLI 黑盒（seam ⑥）

- [x] 4.1 跑 `minihns run`，日志里能看到契约消息与 `source`；文件缺失时没有该消息

## 5. 收尾

- [x] 5.1 真实端点：项目 `AGENTS.md` 的约定被模型读到并照做
- [ ] 5.2 UAT（人跑，场次见 `docs/verification/m14a-workspace-contract-uat.md`）
- [x] 5.3 变异测试一轮
- [x] 5.4 Learning Gate
