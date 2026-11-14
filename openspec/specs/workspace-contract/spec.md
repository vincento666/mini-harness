# workspace-contract Specification

## Purpose
TBD - created by archiving change m14a-workspace-contract. Update Purpose after archive.
## Requirements
### Requirement: 工作区契约的发现、渲染与注入

系统 SHALL 在每个会话的第一个 turn 的 `context/assembled` 之前注入一条持久 `user/message`，payload 带 `source: "workspace-instructions"`，内容用 `<system-reminder>` 框住，按「用户全局 → 项目」顺序分段，每段以 `Instructions from: <path>` 开头。

用户全局契约 SHALL 取自 `$MINIHNS_HOME/AGENTS.md`（未设时为 `~/.mini-harness/AGENTS.md`），项目契约 SHALL 取自 `<workspace>/AGENTS.md`。渲染出的路径 MUST 只写 `~/.mini-harness/AGENTS.md` 与 `AGENTS.md`，MUST NOT 写绝对路径。两份文件去除首尾空白后字节相同时 SHALL 只渲染用户全局那份。

契约总字节数 MUST NOT 超过 16 KiB。超预算时 SHALL 先整份省略用户全局段、再截断项目段，并 SHALL 在消息里写一行可见通知 `Workspace instruction budget: omitted <paths>; truncated <path> to <bytes> bytes.`，其中 MUST 指名被省略与被截断的路径。单个源文件超过 1 MiB SHALL 视为 `unavailable`，不读入。内容、路径与元数据里的字面 `</system-reminder>` SHALL 被转义，仓库控制的文本 MUST NOT 关闭框架。

两份文件都不存在时 MUST NOT 注入任何消息。读取失败 SHALL 按空段或 `unavailable` 处理，MUST NOT 让会话启动失败。

#### Scenario: 两份契约都在

- **WHEN** 用户全局与项目根各有一份 `AGENTS.md`
- **THEN** 第一个 turn 之前有一条 `source: "workspace-instructions"` 的 `user/message`，先出现 `Instructions from: ~/.mini-harness/AGENTS.md`、后出现 `Instructions from: AGENTS.md`，两段内容都在

#### Scenario: 只有项目一份

- **WHEN** 只有 `<workspace>/AGENTS.md` 存在
- **THEN** 消息里只有项目那一段，没有用户全局段

#### Scenario: 两份都没有

- **WHEN** 两个位置都没有 `AGENTS.md`
- **THEN** 日志里没有任何 `source: "workspace-instructions"` 的消息

#### Scenario: 内容相同只渲染一份

- **WHEN** 用户全局与项目根的两份文件去除首尾空白后字节相同
- **THEN** 消息里只出现用户全局那一段，项目段被折叠

#### Scenario: 超预算有可见通知

- **WHEN** 两份文件合计超过 16 KiB
- **THEN** 消息总字节不超过 16 KiB，且含 `Workspace instruction budget:` 一行，指名被省略与被截断的路径

#### Scenario: 框架字符被转义

- **WHEN** 契约正文里写了字面 `</system-reminder>`
- **THEN** 消息里该文本被转义，`<system-reminder>` 框架没有被提前关闭

### Requirement: 契约的刷新、退休与回放

系统 SHALL 在每个 turn 之前重新观察两份契约，并以 `(path, digest, bytes, truncated)` 列表计算指纹。一个 turn 的观察结果与上一次已发出的指纹相同时 MUST NOT 追加消息；不同时 SHALL 追加一条完整替换；两份都不存在时 SHALL 追加一条 `Instructions removed: <paths>` 并退休，让模型不再使用旧内容。

消息 payload SHALL 记 `source`、`digest` 与 `scopes`（每项含 `scope`、`path`、`digest`、`bytes`、`truncated`），MUST NOT 把契约正文写进 `session/start`。`minihns replay` SHALL 从日志前缀重建契约消息，MUST NOT 重读磁盘。

契约 SHALL 与 MEM1 的 `MEMORY.md` 分开：本能力 MUST NOT 读取 `MEMORY.md`，两者的消息 `source` 也不同。

#### Scenario: 未变不重发

- **WHEN** 连续两个 turn 之间两份契约没有变化
- **THEN** 第二个 turn 之前没有新的 `workspace-instructions` 消息

#### Scenario: 变化追加完整替换

- **WHEN** 项目根的 `AGENTS.md` 在两个 turn 之间被改写
- **THEN** 下一个 turn 之前追加一条完整替换消息，内容是新版本

#### Scenario: 文件消失后退休

- **WHEN** 两份契约文件都被删除
- **THEN** 下一个 turn 之前追加一条 `Instructions removed:` 消息，之后不再重复追加

#### Scenario: 回放逐点相等

- **WHEN** 对含契约消息的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 的消息序列与记录逐字段相等，且重算过程不读磁盘上的契约文件

#### Scenario: 记忆不被混入

- **WHEN** 用户目录里同时存在 `MEMORY.md` 与 `AGENTS.md`
- **THEN** 契约消息只含 `AGENTS.md` 的内容，`MEMORY.md` 不出现在这条消息里

