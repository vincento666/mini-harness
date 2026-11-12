---
status: proposed
---

# M14 的三处简化：技能清单进头部、`skill` 是内置工具、preset 只作用于子会话

DSH 的技能清单是第一个 `agent/pre-step` 注入的 user 角色 `<system-reminder>`，之后每步比对 digest、变了就追加一条完整替换；mini 的这条简化**已由 `skill-catalog-live` 消除**：目录改为 user 消息、每 turn 指纹替换、不完整重试、清空退休、压缩后重建。DSH 的 `skill` 是消费方插件（`dsh-tool-skill`），可见性由分层作用域与 `ToolRestriction` 裁剪；mini 没有插件容器（ADR-0035），把它注册成内置工具，用 `tools` 白名单做全有或全无的裁剪。DSH 的 `agentPreset` 是会话级 preset，根与会话都跑在某个 preset 下；mini 的 `[subagent]` preset 只作用于子会话、persona 是单个字符串，根会话的人设留到「根也要 preset」时再做。

技能调用也是简化：DSH 把 `/name` 当**用户消息里的空白分隔 token**（可在句中），pre-step 监听器把正文注入当步、不落命令事件；mini 把它做成 **chat 行首的 `/<技能名> [指令]` 命令**，展开成一条 `user/message` 并落 `command/run`/`command/done`。DSH 还有 `disable-model-invocation` / `user-invocable` 两个策略位；mini 把所有发现到的技能都当「模型可调 + 用户可调」。

Considered options：清单改成 user 角色 reminder + 每步 digest 替换——否，M14 要动注入与 fold 的装配时机，收益只是会话中途可见，先记账；`skill` 做成插件——否，插件容器不在 MVP（ADR-0035）；preset 提到会话级——否，根会话的预设会牵动 `session/start` 契约与所有壳，超出本 change 的量级。

Consequences：技能清单是 `session/start` 的一部分（指纹与回放都稳定，但不能热更新）；`skill` 工具对所有会话可见（除非 `tools` 白名单排除）；子会话能有人设、根不能。触发条件：需要会话中途增删技能即时可见（watcher + digest 替换）；需要根会话也按 preset 配人设/工具；`user-invocable` / `disable-model-invocation` 策略位由 `skill-invocation-policy`（M14 之后、M14a 之前）补；句中 `/技能名` 由 `skill-inline-mention`（M14c 之后）补。
