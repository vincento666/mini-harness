# Design

## Decisions

**D1 形状与位置。** 契约是一条持久的 `user/message`，payload 带 `source: "workspace-instructions"`，内容用 `<system-reminder>` 框住。它不进 `session/start`、不进受保护头部：头部仍由日志前缀派生，契约只作为历史内容存在。

**D2 两个 scope 与路径。** 用户全局读 `$MINIHNS_HOME/AGENTS.md`（未设时 `~/.mini-harness/AGENTS.md`），项目读 `<workspace>/AGENTS.md`。渲染顺序「用户全局 → 项目」；两份都用 `Instructions from: <path>` 起段，路径分别写 `~/.mini-harness/AGENTS.md` 与 `AGENTS.md`，MUST NOT 写绝对路径。两份 trim 后字节相同则只渲染用户全局那份。

**D3 预算与截断。** 整条消息上限 `CONTRACT_BUDGET = 16 * 1024` 字节。超预算时先整份丢用户全局那段，再截断项目那段；截断保留前 N 字节并追加一行可见通知：`Workspace instruction budget: omitted <paths>; truncated <path> to <bytes> bytes.`。渲染后字节数 MUST NOT 超过上限。单文件读前 `stat`，超过 1 MiB 按 `unavailable` 处理，不读。

**D4 刷新与退休。** 每 turn 观察一次（与技能目录同一节奏，不引入 watcher）。指纹取两段的 `(path, digest, bytes, truncated)` 列表。指纹未变 MUST NOT 重发；变了追加一条完整替换；两份都没了追加一条 `Instructions removed: <paths>` 并退休；曾发过、现在为空时不得让模型继续用旧内容。

**D5 记录与回放。** 消息 payload 记 `source`、`digest`、`scopes: [{scope, path, digest, bytes, truncated}]`；正文只在消息内容里，不进 `session/start`。`replay` 从日志折叠，MUST NOT 重读磁盘。

**D6 子会话与边界。** 子会话各自注入自己的契约消息（工作区相同，内容相同但各自一份），父会话不受影响；`MINIHNS_HOME` 随进程环境。契约只读：不执行、不写回、不跟随改写。读失败（权限、超限）按空链或 `unavailable` 处理，MUST NOT 让会话启动失败。

## Risks

- **每 turn 读两份文件**：本地文件成本可忽略；网络盘上可能拖慢一个 turn。触发条件：真实端点下 turn 延迟明显上升时改成「按 mtime 探测、变了才读」。
- **内容里的框架字符**：`</system-reminder>` 必须转义，否则仓库控制的文本能提前关掉框架。
- **截断后的半截指令**：notice 只说明截断，不保证语义完整；这是与 DSH 相同的取舍。
- **子会话重复注入**：每个子会话一份，token 成本乘以子会话数；可接受，因为契约短（16 KiB 上限）。
- **symlink**：契约读取发生在装配期，若 `AGENTS.md` 是指向树外的链接，会把树外内容当指令读入。DSH 明确记录了这个风险；mini 的处理是「只读文本、不执行」，并在 design 里留账，不额外加沙箱。

## 测试与 seam

- seam ①：首 turn 注入、两份/一份/零份、去重、预算与 notice、刷新与退休。
- seam ④：payload 字段与 `replay` 逐点相等。
- seam ⑥：一条 CLI 黑盒，跑 `minihns run` 后日志里能看到契约消息。
