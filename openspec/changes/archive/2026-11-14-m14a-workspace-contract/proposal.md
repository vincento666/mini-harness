# Proposal

## Why

mini 现在对「这个工作区该怎么干活」一无所知：技能是能力，但项目的约定（先读哪份文档、提交怎么写、哪些命令不要跑）只写在仓库的 `AGENTS.md` 里，模型看不到。M14 把技能面做完了，M14a 补的是**契约面**：把项目级与用户级的 `AGENTS.md` 按预算注入上下文，只读、可回放、与记忆分开。

## What Changes

- 新增 `source: "workspace-instructions"` 的持久 `user/message`：首 turn 注入，按「用户全局 → 项目」顺序，用 `<system-reminder>` 框住。
- 发现：`$MINIHNS_HOME/AGENTS.md`（默认 `~/.mini-harness/AGENTS.md`）与 `<workspace>/AGENTS.md`；trim 后内容相同只渲染第一份；路径只写 `~/.mini-harness/AGENTS.md` 与 `AGENTS.md`，不写绝对路径。
- 预算：整条消息 16 KiB；超预算先整份丢用户全局、再截断项目那份，并发出可见 `Workspace instruction budget ...` 通知指名被省略/截断的路径；单文件读前上限 1 MiB。
- 刷新：每 turn 观察（与技能目录同节奏），`(path, digest, bytes, truncated)` 未变不重发；变了追加完整替换；两份都没了追加一条移除消息并退休。
- 与 MEM1 的 `MEMORY.md` 严格分开：source 不同、文件不同、互不覆盖。

## DSH 十项

一手来源：`@deepseek-ai/dsh-agent-instructions`（提交 `47f9438`，`packages/context/agent-instructions`）。详细核对见 `docs/reference/workspace-contract.md`。

**形状**：DSH 用持久 user 消息 + `<system-reminder>` 框，基线模板为 `Instructions from: <path>` 分段；mini 照此，但只做两个 scope。建议：aligned。

**机制**：DSH 在第一次 `agent/pre-step` 组合基线，之后由第一方 `read`/`write`/`edit` touch 驱动刷新，无 watcher。mini 没有插件 pre-step，用「每 turn 观察」代替；mini 的 bash 是子进程，也没有 `cd` 语义。建议：simplified（触发条件：出现真正的目录级 touch 语义）。

**语义**：DSH 每链 `maxBytes`、先丢宽泛再截断具体、notice 指名路径、空链不加 token、转义 `</system-reminder>`。mini 用单条消息一个预算，丢弃顺序照抄。建议：aligned（预算从「每链」收成「整条」是规模差异）。

**不变量**：契约是日志里的消息，fold 从日志前缀重建；不读磁盘、不改写文件；A「日志唯一真源」与 E「工作区边界」都满足。建议：aligned。

**面**：模型面看消息；人机面 `/contracts` 可后续加（本 change 不做）；日志面记 `source` 与 scope 元数据；宿主面暂不暴露。建议：simplified（`/contracts` 延后）。

**失败与降级**：文件不存在是空链，不报错；读失败（权限）按空链处理并在消息里标 `unavailable`；超预算不丢整条，只按顺序丢/截断。建议：aligned。

**组合与扩展**：DSH 支持逐层链与 `AGENTS.local.md` overlay；mini 只做两步。建议：simplified，触发条件：agent 能在会话内切换工作目录。

**资源与约束**：minii 的 16 KiB 远小于 DSH 的 64 KiB；单文件 1 MiB 上限照抄；每次观察只 stat + 读两份文件。建议：aligned。

**信任与授权**：只读；symlink 按 DSH 的告警处理——mini 的 `read` 已有工作区边界，但契约读取发生在装配期，需明确「只读文本、不执行」；不写绝对路径与密钥。建议：aligned（边界写在 design 的 Risks）。

**回放与确定性**：契约是消息，`replay` 逐点相等天然成立；指纹与 `(path, digest)` 都进 payload。建议：aligned。

## Capabilities

### New Capabilities

- `workspace-contract`：工作区契约的发现、渲染、注入、刷新与回放。

## Impact

- 代码：新增 `src/mini_harness/contracts.py`（发现、渲染、预算、指纹）；`loop/turn_loop.py` 注入与刷新；`skills.py` 不动。
- 测试：seam ①（注入与刷新）、④（payload 与回放）、⑥（CLI 黑盒一条）。
- 非目标：逐层链、`AGENTS.local.md` overlay、`USER.md`、`/contracts` 命令、记忆（MEM1）。
- 验收：两份契约在第一个 turn 的上下文可见；超预算有 marker；`replay` 逐点相等；与 `MEMORY.md` 分开。
