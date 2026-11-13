# 工作区契约（M14a）的 DSH 一手调研

**日期**：2026-11-13。**来源**：`@deepseek-ai/dsh-agent-instructions` 的官方 README 与插件目录，对应提交 `47f943859bef60e4160492346772ded9b24f765a`（`packages/context/agent-instructions`）：

- 插件目录（中文全文）：<http://dsh.pub/zh/plugins/agent-instructions>
- 上游 README：<https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a/packages/context/agent-instructions>

本文只记录**该来源明确写出**的行为；没有写到的，标「未记载」，不替它补。

## 1. 形状：不是头部，是持久的 user 消息

DSH 把工作区指令作为**持久历史里的 user 角色消息**注入，用 `<system-reminder>` 框住。基线模板（原文）：

```md
<system-reminder>
The following workspace instructions may be relevant to your work. Use them as guidance when applicable. More specific instructions take precedence over broader ones. They do not override system, developer, or direct user instructions.

Instructions from: ~/.dsh/AGENTS.md

<user-global-instructions>

Instructions from: AGENTS.md

<project-instructions>
</system-reminder>
```

后续发现的新 scope 用「带来源的 user/message」：

```md
<system-reminder>
Additional instructions from: packages/app/AGENTS.md

These instructions apply to work under `packages/app`. Use them as guidance when relevant; more specific instructions take precedence. They do not override system, developer, or direct user instructions.

<nested-instructions>
</system-reminder>
```

变更是 `Updated instructions from: <path>`；消失或成为同目录重复项是 `Instructions removed: <path>` 加一句「之前加载的内容不再适用」。

**与 mini 的关系**：roadmap 写的是「注入受保护头部」，但 DSH 的做法是**持久 user 消息**。mini 已有同形状的先例——技能目录（`user/message` + `source: "skill-catalog"` + 指纹替换）。若照 DSH，M14a 不需要动 `context-projection` 的头部派生，也不需要把契约正文塞进 `session/start.payload`。

## 2. 机制

- **注入时点**：每个实时会话第一次符合条件的 `agent/pre-step` 组合基线，折入最终批次、紧随已领取的直接提示词之后；被拒绝或为空的批次把基线留在 inbox。
- **顺序**：先 `$DSH_HOME/AGENTS.md`（用户全局），再 `/AGENTS.md`（共享根），再项目链——从项目根到 `cwd` 的每一层，先基础候选（`AGENTS.md`、`CLAUDE.md`），再本地 overlay（`AGENTS.local.md`、`CLAUDE.local.md`），由宽到具体。
- **去重**：同一目录内，去除首尾空白后字节相同的候选只渲染最早那个（`CLAUDE.md` 复制 `AGENTS.md` 就只出现一次）。
- **刷新**：没有 watcher；成功的**第一方** `read` / `write` / `edit` 触及更深目录后，下一次请求带上新适用的文件。`bash` 里的 `cd` **不触发**（每次 bash 是新 shell，解析 shell 语法不可靠）。恢复会话时对账可见基线；压缩遮蔽后由下一次 pre-step 或 touch 重新加入。
- **状态**：模型可见文本里没有隐藏标记；每个事件带类型化来源 `agent-instructions`，含 `{ action, scope, path, digest? }`，基线另有 `baseline: true` 与 `baselineIdentity`（由发现、优先级、项目根、预算配置派生）。
- **未变不重发**：路径与 SHA-1 内容 digest 都没变就不重复注入；移除是 tombstone，文件再出现会重新加载。

## 3. 语义

- **预算**：`maxBytes` 必填，**用户全局链与项目链分别计算**，各不超过 `maxBytes`；一条消息同时装两条链时最多 2×。
- **丢弃顺序**：先丢整份**更宽泛**的文件，再**截断最具体**的那份；渲染后字节数绝不超过预算。
- **可见提示**：会发一条 `Workspace instruction budget ...` 通知，**指名被省略与被截断的路径**。
- **空链**：不产生任何 token。
- **单文件上限**：`maxSourceBytes` 默认 1 MiB，在渲染前限制每个源文件。
- **转义**：内容、路径、scope、预算元数据里的字面 `</system-reminder>` 会被转义，仓库控制的文本不能关掉框架。
- **安全边界（DSH 自己列的）**：候选文件最后一段是 symlink 时会跟随到目标，可能把树外内容当工作区指令加载；加载不受信任仓库时要靠文件系统策略或 OS 沙箱限制。

## 4. mini 的映射

| 维度 | DSH（一手资料） | mini 现状 | 建议 |
|---|---|---|---|
| 注入位置 | 持久 user 消息（`<system-reminder>` 框） | 头部由 `session/start` 前缀派生；技能目录已是持久 user 消息 | **照 DSH**：`user/message` + `source: "workspace-instructions"` |
| scope 集合 | 用户全局 + 共享根 + 项目根到 cwd 的逐层链 + 本地 overlay | 无 | **最小**：用户全局（`$MINIHNS_HOME/AGENTS.md`）+ 项目根 `AGENTS.md`；不做逐层链与 overlay |
| 重发 | 路径 + SHA-1 未变不重发 | 目录用指纹（name+desc+source+complete） | 用 `(path, digest)` 判定；变更发 `Updated`，消失发 `Removed` |
| 预算 | 每链 `maxBytes`，先丢宽泛再截断具体，notice 指名路径 | 目录有 `CATALOG_BUDGET` | 单链预算 16 KiB（可配），notice 照抄「指名路径」 |
| 记录 | 类型化来源 `{action, scope, path, digest}` + `baselineIdentity` | `session/start` + 消息 payload | 消息 payload 带 `scope` / `path` / `digest` / `truncated` |
| 回放 | 指令是历史内容，从日志重建 | `replay` 逐点校验 | 天然满足：消息在日志里，不依赖磁盘 |
| 与记忆分开 | DSH 没有 MEMORY.md 概念 | MEM1 用 `MEMORY.md` | 契约 `source` 与记忆 `source` 分开，互不覆盖 |

## 5. 需要裁决的三个分叉

1. **注入位置**：照 DSH 用持久 user 消息（推荐，且与技能目录同构），还是照 roadmap 原文塞进受保护头部。后者要求契约正文进 `session/start.payload` 才能回放，日志会变大。
2. **scope 深度**：只「用户全局 + 项目根」两步（推荐，mini 的 agent 不 `cd`，bash 是子进程），还是照 DSH 做逐层链与本地 overlay。
3. **文件名**：DSH 用户全局也叫 `AGENTS.md`；roadmap 写的是 `USER.md`。两者只能选一个作为用户级契约的文件名，另一个可作为别名或不做。

## 6. 对验收判据的影响

roadmap 的判据是「两份契约都在**头部**可见」。若采纳分叉 1 的推荐，判据要改成「两份契约都在**第一个 turn 的上下文**可见（一条 `source: "workspace-instructions"` 的 user 消息）」，并保留「超预算有 marker、`replay` 逐点相等、与 MEMORY.md 分开」三条。这条改动属于规格级偏差，必须由人裁决后才写进 proposal。
