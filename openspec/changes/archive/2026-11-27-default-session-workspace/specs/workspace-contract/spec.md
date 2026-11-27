# Spec Delta: workspace-contract

## MODIFIED Requirements

### Requirement: 工作区契约的发现、渲染与注入

系统 SHALL 在每个会话的第一个 turn 的 `context/assembled` 之前注入一条持久 `user/message`，payload 带 `source: "workspace-instructions"`，内容用 `<system-reminder>` 框住，按「用户全局 → 项目」顺序分段，每段以 `Instructions from: <path>` 开头。

用户全局契约 SHALL 取自 `$MINIHNS_HOME/AGENTS.md`（未设时为 `~/.mini-harness/AGENTS.md`）；项目契约 SHALL 取自**发现根**的 `AGENTS.md`——发现根是显式 `--workspace` 解析后的目录，未给 `--workspace` 时是当前目录（启动目录），MUST NOT 锚默认的会话专属工作区。渲染出的路径 MUST 只写 `~/.mini-harness/AGENTS.md` 与 `AGENTS.md`，MUST NOT 写绝对路径。两份文件去除首尾空白后字节相同时 SHALL 只渲染用户全局那份。

契约总字节数 MUST NOT 超过 16 KiB。超预算时 SHALL 先整份省略用户全局段、再截断项目段，并 SHALL 在消息里写一行可见通知 `Workspace instruction budget: omitted <paths>; truncated <path> to <bytes> bytes.`，其中 MUST 指名被省略与被截断的路径。单个源文件超过 1 MiB SHALL 视为 `unavailable`，不读入。内容、路径与元数据里的字面 `</system-reminder>` SHALL 被转义，仓库控制的文本 MUST NOT 关闭框架。

两份文件都不存在时 MUST NOT 注入任何消息。读取失败 SHALL 按空段或 `unavailable` 处理，MUST NOT 让会话启动失败。

#### Scenario: 两份契约都在

- **WHEN** 用户全局与启动目录各有一份 `AGENTS.md`
- **THEN** 第一个 turn 之前有一条 `source: "workspace-instructions"` 的 `user/message`，先出现 `Instructions from: ~/.mini-harness/AGENTS.md`、后出现 `Instructions from: AGENTS.md`，两段内容都在

#### Scenario: 未给 --workspace 时项目契约仍被发现

- **WHEN** 启动目录有一份 `AGENTS.md`，不传 `--workspace` 启动会话
- **THEN** 项目段照常注入；会话专属工作区下的 `AGENTS.md`（若有）不被读取

#### Scenario: 只有项目一份

- **WHEN** 只有发现根的 `AGENTS.md` 存在
- **THEN** 消息里只有项目那一段，没有用户全局段

#### Scenario: 两份都没有

- **WHEN** 两个位置都没有 `AGENTS.md`
- **THEN** 日志里没有任何 `source: "workspace-instructions"` 的消息

#### Scenario: 内容相同只渲染一份

- **WHEN** 用户全局与发现根的两份文件去除首尾空白后字节相同
- **THEN** 消息里只出现用户全局那一段，项目段被折叠

#### Scenario: 超预算有可见通知

- **WHEN** 两份文件合计超过 16 KiB
- **THEN** 消息总字节不超过 16 KiB，且含 `Workspace instruction budget:` 一行，指名被省略与被截断的路径

#### Scenario: 框架字符被转义

- **WHEN** 契约正文里写了字面 `</system-reminder>`
- **THEN** 该文本被转义，`<system-reminder>` 框架没有被提前关闭
