# Design

## Context

M12/subagent-preset 之后，子代理的工具面已经由部署 preset 决定；还差「知识面」（技能）与「preset 的人设」。DSH 的机制是清单注入 + 正文按需加载 + 一份命令面，正文必须进日志（不变量 A）。

## Decisions

**D1 四级根，数字小者优先。** 100 `<workspace>/.minihns/skills/`、200 `<workspace>/.agents/skills/`、500 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`）、600 内置 `src/mini_harness/skills/`。300/400 留空（等真有自定义/宿主根再加）。同名按 rank 小者胜；发现顺序按 `(rank, path)`，保证 `session/start` 与清单稳定。

**D2 技能文件。** 一个技能是 `<dir>/SKILL.md` 或扁平的 `<name>.md`。可选的 frontmatter 只认 `name:` 与 `description:` 两个键（按 `key: value` 解析，不引入 YAML 依赖）；缺失时名字回退到目录名/文件名，描述为空。没有名字的条目跳过，不让一个坏文件拖垮会话。

**D3 启动快照。** 发现发生在装配期；`session/start.payload.skills` 只放清单 `{name, description, rank, path}`。受保护头部放紧凑清单（名字 + 一句描述），字符预算（默认 2000），超了截断并留 `（还有 N 个技能未列出）`；正文绝不进头部。会话中途新增/修改技能不影响本会话的清单——下一会话才可见。

**D4 `skill` 工具。** 参数 `{name}`；读正文并返回（单次上限 32 KiB，超了截断并提示用 `read` 读全文）。未知名字是 `TOOL_ARGS_INVALID`。正文在调用时读盘，但**结果落 `tool/result`**，所以 `replay` 只认日志：技能文件在会话中途被改，不影响已发生的重放。

**D5 命令面是内核的投影。** 命令只有两个：`skills`（列清单）与 `skill <name>`（加载正文）。CLI `chat` 的 `/skills`、`/skill x`、`/help`；host 的 `GET /commands` 与 `POST /sessions/{id}/commands`。两边共用同一个 `CommandSurface`，返回同一份清单/正文。

**D6 命令落 `command/invoked`。** payload `{name, arguments, ok}`，只进日志、不进 transcript（与 `approval/*` 同一边界）。`/skills` 只写这一条、不开段；`/skill x` 成功时再写一条 `user/message`（内容是渲染后的技能正文）并开启一个段，失败时 `ok=false` 且不开段。`/help` 是壳本地的帮助，不落日志。

**D7 persona 进子会话头部。** `[subagent.presets.<id>].persona`（可选字符串）在装配期编译进 preset；spawn 时写子 `session/start.payload.preset_persona`，`fold` 把它作为受保护头部的一段（排在委派声明之后、追加文本之前）。没有 preset 或没有 persona 时什么都不写。

**D8 回放不读磁盘。** 清单、技能正文、persona、命令事件全在日志里；`replay` 只折叠日志。这是不变量 A 的直接推论，也是「正文必须落 `tool/result`」的原因。

## Risks

- **发现顺序不稳定**会让 `session/start` 与头部指纹抖动：顺序必须由 `(rank, path)` 决定，不能靠 `glob` 的返回顺序。
- **技能正文很大**：`skill` 的 32 KiB 上限与 `read` 的窗口是两条路；超限时给的是截断 + 提示，不是静默丢弃。
- **命令与消息的队列语义**：`skill` 在段进行中要像消息一样排队（不并发写日志）；`skills` 只读清单，不排队。
- **词表扩张**：`command/invoked` 要进 `test_vocabulary_reachability` 的判据，否则「词表里多了一个跑不到的值」。
