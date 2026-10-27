# 技能、斜杠命令与渐进式披露（M14 底稿）

**定位**：M14 开工前的设计底稿，不是规格。DSH 的事实来自 `docs/dsh-reference/` 的图集 `e06-extension-axes` 与 `e08-skill-discovery-ranks`；mini 的取舍在本文写清。

## 1. DSH 的三条扩展轴

`e06` 把扩展分成三条轴，全部通过注册、不改内核：

| 轴 | 内容 | 关键机制 |
|---|---|---|
| 知识轴 | 技能发现 | **6 级优先级根**；`SKILL.md` 包或扁平 `.md`；**清单注入、正文按需加载** |
| 触发轴 | commands / schedule | commands 5 个方法；schedule 6 个方法 |
| 产物轴 | terminal | 交互终端 |

`e08` 的六级根（同名技能按高优先级覆盖）：

| 等级 | 根 |
|---|---|
| 100 | 项目内 |
| 200 | 项目共享 |
| 300 | 自定义 |
| 400 | 宿主 |
| 500 | 通用代理家目录 |
| 600 | 内置 |

**渐进式披露**的具体含义：启动时只把技能的**清单**（名字、描述、排名/路径）注入上下文；正文留在磁盘，等模型或用户明确要时再读。这样技能再多也不撑爆头部。

## 2. mini 的映射（建议）

不照搬六级，先落 **4 级根**，把 DSH 的 100/200/500/600 对上，300/400 留空：

| rank | mini 根 | 说明 |
|---|---|---|
| 100 | `<workspace>/.minihns/skills/` | 项目内 |
| 200 | `<workspace>/.agents/skills/` | 项目共享（与现有 agents 技能目录兼容） |
| 500 | `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`） | 用户级 |
| 600 | `src/mini_harness/skills/` | 内置 |

同名技能高 rank 覆盖低 rank；发现结果按 rank 升序、同 rank 按路径排序，保证确定性。每个技能是 `SKILL.md`（带 frontmatter：`name` / `description`）或一个扁平 `.md`。

## 3. 内核：清单注入 + 正文按需

**启动**：`session/start.payload.skills` 只放清单：

```json
[{"name": "tdd", "description": "test-first ...", "rank": 100, "path": "..."}]
```

受保护头部只放紧凑一行（名字 + 一句描述），**不放正文**。技能很多时按 rank 截断，截断处留 marker。

**按需加载**：`skill` 工具（`{name}`）读正文并返回；正文作为 `tool/result` 进日志与上下文。`skill` 工具是普通工具，走 ② 的注册/围栏/结果词；不需要新增长期上下文机制。

**为什么正文必须进日志**：不变量 A——折叠只从日志前缀派生；如果正文只从磁盘读、不落日志，`replay` 会随技能文件变化而失配。所以「读技能」必须是一条可重放的 `tool/call` + `tool/result`。

## 4. 斜杠命令：CLI 与其它壳同一份

命令不是壳自己发明的语法，而是**内核命令面**的投影：

| 入口 | 命令 | 行为 |
|---|---|---|
| CLI `chat` | `/skills` | 列清单（名字、描述、rank） |
| CLI `chat` | `/skill <name>` | 加载正文；日志写 `skill` 工具的 call/result（或用 `command/invoked` + `skill/loaded`，M14 design 定） |
| CLI `chat` | `/help` | 列可用命令 |
| CLI `run` | `--skill <name>` | 一次性运行前加载（可选） |
| host | `GET /commands` | 列清单（与 `/skills` 同源） |
| host | `POST /sessions/{id}/commands` | 执行 `{name, args}`；返回结果与游标 |
| UI | 同上 | 输入 `/` 弹出同一份清单，不另写一套 |

**命令调用要落一条可重放的事件**：候选是新增 `command/invoked`（payload：`name` / `args` / `ok`），或复用 `user/message` 的结构化 `command` 字段。M14 design 二选一；无论选哪个，`replay` 必须能重建「这条命令发生过、结果是什么」。

**不做什么**：壳自己绕过内核直接读技能文件；技能正文只存在于壳的内存；命令产生的事件不进日志。

## 5. M14 完成判据

- 一个项目技能与一个用户技能同时存在时，同名高 rank 胜出，低 rank 不出现在清单里。
- `session/start.payload.skills` 只有清单，没有正文；`skill` 工具加载后正文才进上下文。
- CLI `/skills` 与 host `GET /commands` 返回同一份清单；CLI `/skill x` 与 host `POST /commands` 得到同一份正文、同一份日志。
- `replay` 逐点相等；技能文件在会话中途被改，不影响已发生的日志重放。
- 一条外部触发在日志里是一条事件、`replay` 仍相等。

## 6. 开放问题

- 6 级根要不要全抄？先 4 级；300/400 等真有宿主/自定义根时再加。
- 命令事件用 `command/invoked` 还是 `user/message.command`？前者干净、后者少一个词表值；M14 design 裁。
- 技能正文的预算：单个 `SKILL.md` 要不要设上限（例如 32 KiB）？先设，超了截断并提示用 `read` 读全文。
- 技能发现是否在 `session/start` 时快照？先快照到 payload；会话中途新增的技能下一会话才可见。
- `run --skill` 与 `/skill` 的语义是否要一致（都是「加载正文」）？先一致。
