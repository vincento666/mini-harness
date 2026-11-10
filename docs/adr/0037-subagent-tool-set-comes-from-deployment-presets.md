---
status: proposed
---

# 子代理的工具集只由部署 preset 决定，`subagent.tools` 在 M14 删除

DSH 的 `agentPreset` / `allowedAgentPresets` 是部署侧配置：**没有 preset 时子级加入父的当前组合，派发不会失效**，模型只能在白名单里选 preset。mini 的 `subagent.tools`（父模型在工具调用里给的收窄列表）在 M12 是安全的（只能减、不能加），但它把「子能有什么」的来源交给了模型；M14 用 preset + 白名单替代它，并删除该参数。

Considered options：保留 `tools` 作为「preset 之上再减」——否，DSH 没有这一层，而部署已经能表达同样的裁剪，两套来源并存只会让「子能有什么」有两种解释；保留但只记账——否，同上；完全不配 preset 就禁用委派——否，DSH 的缺省是继承父组合，禁用是更差的产品行为。

Consequences：模型失去临场裁剪（要省上下文只能靠部署预设或选 preset）；工具 schema 里 `tools` 消失、`agent_preset` 成为白名单枚举；M12 的 spec 与测试要跟着改；「无 preset 时继承父组合」保证派发不会因为没配置而失效；`persona` 字段随 M14 补齐后，preset 与 DSH 的 `agentPreset` 同形。
