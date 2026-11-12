# 技能、斜杠命令与渐进式披露（M14 底稿）

**定位**：M14 的设计底稿，不是规格；**已落成**（`2026-11-11-m14-skills-and-commands`），正文保留 DSH 事实与当时的取舍。DSH 的事实来自 `docs/dsh-reference/` 的图集 `e06-extension-axes` 与 `e08-skill-discovery-ranks`；mini 的取舍在本文写清。

## 1. DSH 的三条扩展轴

`e06` 把扩展分成三条轴，全部通过注册、不改内核：

| 轴 | 内容 | 关键机制 |
|---|---|---|
| 知识轴 | 技能发现 | **6 级优先级根**；`SKILL.md` 包或扁平 `.md`；**清单注入、正文按需加载** |
| 触发轴 | commands / schedule | commands 5 个方法；schedule 6 个方法 |
| 产物轴 | terminal | 交互终端 |

`e08` 的六级根（同名技能按高优先级覆盖）：

| 等级 | 根（DSH 的实际名字） |
|---|---|
| 100 | `project-dsh`：`<projectRoot>/.dsh/skills` |
| 200 | `project-agents`：`<projectRoot>/.agents/skills` |
| 300 | `custom`：`Config.customSkillDirs` |
| 400 | `user-dsh`：`<dshHome>/skills` |
| 500 | `user-agents`：`<agentsHome>/skills` |
| 600 | `bundled`：`Config.bundledSkillDir` |

项目根是最近的 `.git` 祖先（没有就用 cwd）；不做内置系统技能，打包技能走 bundled 根。名字是 kebab-case，目录式 `<name>/SKILL.md` 或扁平 `<name>.md`，不递归；有 watcher，会话中途可更新。注册表是**分层**的（host + 每个 scope 一层）：近一层的同名条目直接胜出，rank 只在同一层内裁决。

**渐进式披露**的具体含义：启动时只把技能的**清单**（名字、描述、排名/路径）注入上下文；正文留在磁盘，等模型或用户明确要时再读。这样技能再多也不撑爆头部。

## 2. mini 的映射（建议）

不照搬六级，先落 **4 级根**，把 DSH 的 100/200/500/600 对上，300/400 留空：

| rank | mini 根 | 说明 |
|---|---|---|
| 100 | `<workspace>/.minihns/skills/` | 项目内 |
| 200 | `<workspace>/.agents/skills/` | 项目共享（与现有 agents 技能目录兼容） |
| 400 | `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`） | 用户级（照 DSH 的 `user-dsh`） |
| 600 | `src/mini_harness/builtin_skills/` | 内置 |

300 / 500 本 change 不做。同名技能数字小者胜；发现结果按 `(rank, path)` 排序，保证确定性。每个技能是 `SKILL.md`（带 frontmatter：`name` / `description`）或一个扁平 `.md`；名字必须 kebab-case，不递归。

## 2b. 调用策略、完整性与作用域层（skill-invocation-policy）

- **策略位**：frontmatter 的 `disable-model-invocation` 与 `user-invocable`（缺省都允许；宽松布尔 `true/false`、`yes/no`、`on/off`、`1/0`；非法值丢弃整个技能）。模型面（payload/头部/`skill` 工具）只认模型可调，人机面（`/skills`、`/<技能名>`、`/skill`、host 命令清单）只认用户可调；两面都禁用的技能只留在 `settings.skills`。
- **完整性**：根目录 `iterdir` 失败 → `complete=false`，payload 记 `skills_incomplete`、头部警告；单文件坏掉只跳过；下一次装配重新发现。
- **preset 层（skill-providers 起）**：`[subagent.presets.<id>.skills]` 挂一层 filesystem provider（`kind = "filesystem"`、必填 `dirs`）；子会话 = 全局层 + 该层，**同名由近层胜出**（不再看 rank），层内按目录顺序；根会话只有全局层。目录不存在是空层。命令面与模型目录读同一份注册表快照，`skill` 工具的正文也由拥有这个名字的那一层提供（ADR-0040；ADR-0039 已被取代）。

## 3. 内核：清单注入 + 正文按需

**启动**：`session/start.payload.skills` 只放装配期清单（审计与命令面用）：

```json
[{"name": "tdd", "description": "test-first ...", "rank": 100, "path": "..."}]
```

模型目录是一条 **user 角色的 `<system-reminder>` 消息**（`source: skill-catalog`）：名字 + 转义后的描述，**不放正文**；描述截到 500 字符。每个 turn 装配前重新发现并比对指纹，变了追加完整替换；不完整发警告、下一步重试；清空追加空目录退休旧名字；压缩折掉后重建。受保护头部**不放**技能块。

**按需加载**：`skill` 工具（`{name}`）读正文并返回；正文作为 `tool/result` 进日志与上下文。`skill` 工具是普通工具，走 ② 的注册/围栏/结果词；不需要新增长期上下文机制。

**为什么正文必须进日志**：不变量 A——折叠只从日志前缀派生；如果正文只从磁盘读、不落日志，`replay` 会随技能文件变化而失配。所以「读技能」必须是一条可重放的 `tool/call` + `tool/result`。

## 4. 斜杠命令：CLI 与其它壳同一份

命令不是壳自己发明的语法，而是**内核命令面**的投影：

| 入口 | 命令 | 行为 |
|---|---|---|
| CLI `chat` | `/skills` | 列清单（名字、描述、rank），不开段 |
| CLI `chat` | `/skill <name>` | 打印正文，不开段；模型要用技能走 `skill` 工具 |
| CLI `chat` | `/<技能名>` | **执行**：正文 + 默认指令拼成 `user/message` 并开段；带指令则替换默认句 |
| CLI `chat` | `/skill <技能名>` | **查看**：打印正文、不开段 |
| CLI `chat` | `/<技能名> <指令>` | 技能正文 + 指令拼成一条 `user/message` 并开段；host 同义（202，忙时排队） |
| CLI `chat` | `/help` | 列可用命令（壳本地，不落日志） |
| host | `GET /commands` | 列清单（与 `/skills` 同源） |
| host | `POST /sessions/{id}/commands` | 执行 `{name, args}`，返回 200 + `{output, cursor}`，不开段 |
| UI | 同上 | 输入 `/` 弹出同一份清单，不另写一套 |

DSH 的技能调用是**消息里的 `/name` token**（空白分隔、可在句中）：pre-step 监听器把技能正文注入当步，不落命令事件；mini 把它做成 chat 行首的 `/<技能名> [指令]` 命令，展开成一条 `user/message` 并落两件套（见 ADR-0038）。

**命令调用落 `command/run` + `command/done` 两件套**（照 DSH）：前者在 handler 之前（`command_id` / `name` / `raw_input`），后者在结算之后（`command_id` / `ok` / `text?`）；只进日志、不进 transcript。语法/未知命令的 admission miss 不落日志。命令**不创建模型消息、不开启段**——这是人机直连的 UI 动作，不是往对话里塞话。

**不做什么**：壳自己绕过内核直接读技能文件；技能正文只存在于壳的内存；命令产生的事件不进日志；命令伪装成用户消息去开段。

## 5. M14 完成判据

- 一个项目技能与一个用户技能同时存在时，同名高 rank 胜出，低 rank 不出现在清单里。
- `session/start.payload.skills` 只有清单，没有正文；`skill` 工具加载后正文才进上下文。
- CLI `/skills` 与 host `GET /commands` 返回同一份清单；CLI `/skill x` 与 host `POST /commands` 得到同一份正文、同一份日志。
- `replay` 逐点相等；技能文件在会话中途被改，不影响已发生的日志重放。
- 一条外部触发在日志里是一条事件、`replay` 仍相等。

## 6. 开放问题

- 6 级根要不要全抄？先 4 级（100/200/400/600）；300/500 等真有自定义/agents 家目录时再加。
- 命令事件：已裁——`command/run` + `command/done` 两件套，命令不开段。
- 技能正文的预算：单个 `SKILL.md` 要不要设上限（例如 32 KiB）？先设，超了截断并提示用 `read` 读全文。
- 技能发现是否在 `session/start` 时快照？先快照到 payload；会话中途新增的技能下一会话才可见。
- `run --skill` 与 `/skill` 的语义是否要一致（都是「加载正文」）？先一致。
