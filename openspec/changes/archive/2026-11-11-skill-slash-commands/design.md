# Design

## Decisions

**D1 名字空间：内置命令优先。** `skills`、`skill`、`help` 是保留名；技能名与它们撞车时内置胜出（技能仍可用 `/skill <名字>` 调到）。发现结果里同名技能已按 rank 去重，这里只处理「技能 vs 内置」。

**D2 解析在共用层。** `execute_command` 先查内置命令，再查技能名；`/<name>` 与 `/skill <name>` 走同一条正文读取与同一对 `command/run` + `command/done`。`/<name>` 带多余参数是 handler 错误（`ok=false`），照常落两件套。

**D3 清单按会话。** 技能是会话级的（装配期按 workspace 发现），所以 host 的 `GET /commands` 不带会话时只列内置命令；带 `?session_id=` 时追加该会话的技能命令。chat 的 `/help` 天然有会话，直接列两者。

**D4 披露效果用日志判。** 端到端判据不比对 token：`session/start.payload.skills` 与第一条 `context/assembled` 都不含正文；`skill` 调用之后的 `context/assembled` 里正文作为工具消息出现。这是不变量 A 的可观察形状。
