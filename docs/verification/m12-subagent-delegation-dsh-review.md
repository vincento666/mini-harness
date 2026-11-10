# M12 DSH parity review

**日期**：2026-11-06（2026-11-10 按公开仓库更新）。对照点来自 `docs/reference/subagents.md`、公开仓库的 `dsh-subagent` / `dsh-tool-subagent` / 审批缝 Agent Note，以及 `docs/dsh-reference/DSH运行时设计说明.html` 的委派章节。术语与机制的系统说明见 [`docs/reference/dsh-subagent-design.md`](../reference/dsh-subagent-design.md)。

| 行为 | DSH（公开仓库/文章） | mini | 结论 | 记账 |
|---|---|---|---|---|
| 子代理 spawn | 有（空对话起步，`startActivation({prompt})`） | 有（`subagent` 工具，`task` 必填、不 seed 父历史） | aligned | — |
| 子代理 fork | 有（截至最后一个 `turn/end` 的配平前缀） | 不做 | deferred | ADR-0035；触发条件：需要 KV cache 复用且宿主协议允许 fork 语义 |
| 深度 | `depth = 父 + 1`；`maxDepth` 默认 1，工具可显式指定 | 同左（常量 1），`DEPTH_EXCEEDED` 是结果词 | aligned | 工具级覆盖我们没做 |
| 容量 | `maxActiveSubagents` 默认 8，**按 subagent 树**计，根不占名额；耗尽 `ACTIVATION_LIMIT_REACHED`（浏览器消息 `subagent/delivery-unavailable`） | 每父会话 8 个活跃子代理；耗尽 `ACTIVATION_LIMIT_REACHED` | simplified | 深度 1 时「每树」与「每父」等价；没有 `subagent/delivery-unavailable`（无浏览器消息面）；工具并发上限也是 8，同一批 9 个撞不到额度（design D8） |
| 审批 | 进程内子 agent 被**钉定为 `never`**：每次 ask 在任何应答者之前解析为 rejected；把子级 ask 路由给父级**已延后**；`subagent-acp` 的子侧自动应答是后端自己的 | approval 模式随会话继承（`auto` 继承），门固定 `UNAVAILABLE`；父拿到的也是拒绝结果词 | simplified | 差异在「无人值守」放在哪一轴：DSH 的 Auto 预设是 **full-access 沙箱**（正常写入不触发 ask），mini 的 `auto` 是「全部自动批准」。mini 的 ask 模式对每次会改动都问人，字面钉 `never` 会让子代理连 full-access 下也写不了——要等价，得先有「沙箱升级才问人」的语义（ADR-0036 记账） |
| 子会话声明 | 受保护上下文带 `subagent:delegation`：权限启动时固定、需要审批的操作自动拒绝、**不要重试**、把限制写进回复给父级 | 同左（`DELEGATION_SCOPE_DECLARATION`，`session/start.payload.delegated`） | aligned | 文案是中文、措辞按 mini 的系统提示改写 |
| 子级工具作用域 | `scope.tools = 组合过滤`，**不是授权继承**；工具集来自宿主配置的 `agentPreset`（persona + 工具） | M12：默认继承父工具表 + `subagent.tools`（模型参数）收窄；**M14 起：部署 preset + 白名单，删除 `tools`**（ADR-0037） | aligned（2026-11-10 落成，`subagent-preset`） | preset 从内置目录组合、不导入父的局部限制；工具是能力，授权仍由围栏管 |
| 子级 agent 名称 | `agent-N`，根是 `lead`，路径形如 `reviewer/checker`；重名 `DUPLICATE_AGENT_NAME` | 用子会话 id，没有名字 | deferred | 触发条件：UI 要画任务树或需要人类可读的引用时 |
| 同批并发 | 工具批调度里只读调用并发 | `subagent` 标 `parallel`，同批真并发、结果按完成顺序落盘 | aligned | M10 的批调度 |
| 取消 | 调用方 signal 只取消未发布的工作；发布后 `dispose()` 取消并等待清理；宿主用 `drainDescendants([root])` | 父段取消 → 子会话按 `ABORTED` 收尾，已完成结果保留 | simplified | 我们只有「段取消」一种入口，没有 `dispose/drain` 生命周期 API；深度 1 下等价 |
| 审批结果词 | `allowed-once` / `rejected` / `cancelled` / `unavailable`，四者模型可区分 | `APPROVED` / `DENIED` / `UNAVAILABLE`；取消走回合取消（ADR-0007） | simplified | 没有 `allowed-once` 与 `cancelled` 的独立词；审计对是 `approval/request` + `approval/response` |
| 审计事件 | `approval/asked` + `approval/decided`（只进日志、不进 transcript） | `approval/request` + `approval/response`（同边界） | aligned | 只差命名 |
| 完成通知 | 用户角色消息：`Background subagent <name> finished…`，带最终文本；明确「父级不收到完整 transcript/tool output/reasoning」 | 子会话最终文本作为 `tool/result` 返回 | simplified | 信息边界相同（只有最终文本）；我们用工具结果而不是用户消息，父级上下文形状不同 |
| 结果形状 | 最终结果 + 结构化数据 + 停止原因；投递失败另有词 | 最终文本；模型/内核失败 `TOOL_IO_FAILED`；围栏拒绝 `DENIED_BY_APPROVAL`/`DENIED_BY_FENCE` | simplified | 不返回产物清单与结构化输出（ADR-0036） |


**判据**：每个 spec/design 里出现的 DSH 对照点都有一行；`simplified` 都写了代价，`deferred` 都写了触发条件。

## 与 Super-agent 架构的连续性（2026-11-07 补）

**公开事实**：Super-agent 是 DeepSeek 的一篇设计文章（《Exploring Super-agent Design》，2026-10-31），配一个**研究原型** `deepseek-ai/dsh-superagent-prototype`（MIT，单 commit，README 自称 "not an official DeepSeek product"）。它的形状是：常驻 Router 主会话（无 bash、轻模型）派单，每个 Ticket 一个 Worker 会话（强模型、全工具），Thread 决定后续消息直接进 Worker，另有一个进程外的 Watchdog。

**权限怎么分**：Router 与 Worker **都跑 `danger-full-access`**（`src/app/sessions.ts:152`）；Worker 的隔离不在审批或 OS，而在**工具边界**——读取用的 ticket id 在构造工具时由宿主编进闭包，不是工具参数（`src/app/runtime.ts:124`、`src/app/resources.ts:97-104`），越界的读取直接拒绝。Worker 的 shell 也以操作员身份运行、不经审批。

**连续性**：是。Super-agent 没有发明新的权限通道，它复用的是 DSH 已有的 session / preset / tool / approval 原语；「子级 ask 路由给父级」在核心仍是**延后**项，原型也没有做。真正变的是拓扑（Router/Worker/Thread/Watchdog）与**工具边界分域**，不是委派审批。

**对 mini 的含义**：M12 的 spawn 形状是底座；将来若做 Worker，等价物是「会话 + preset + 收窄的工具表」，而不是给子代理加一条父代答通道。另外 `danger-full-access` 在这个原型里是**默认姿态**——它和 mini 的「默认 workspace-write + ask」是两种安全基线，抄拓扑时不能顺手抄这条。

## 语义原语的差距（M12 之后）

结构（spawn / 深度 / 容量 / 父只拿结果 / 取消 / 并发）已经对齐。剩下的差距不在结构，在三个原语的**粒度**：

| 原语 | DSH | mini | 后果 | 什么时候对齐 |
|---|---|---|---|---|
| 沙箱与审批的关系 | 沙箱模式是**授权本身**（workspace-write 等），审批只处理**升级**（`sandbox_permissions`） | 沙箱回答「能碰哪儿」，审批回答「每次会改动都问不问」 | 子代理在 `ask` 下连 full-access 都写不了；DSH 的 `never` 钉定不能字面照搬 | 出现「同一次调用要超出会话档位的权限」的真实场景（bash 请求升级）时，立 fence 阶梯的 ADR |
| 工具边界 | 工具**按数据边界授权**：ticket id 在构造工具时绑进闭包，越界读取被拒 | 只有**组合过滤**（收窄工具表），没有数据边界 | 子会话里任何注册工具都能碰工作区内的任何文件 | 出现「一个会话只能看一个工单 / 仓库子集」的需求（Super-agent 的 worker）时 |
| 审批结果词与审计 | `allowed-once` / `rejected` / `cancelled` / `unavailable`，配 `approval/asked` + `approval/decided` | `APPROVED` / `DENIED` / `UNAVAILABLE`；取消走回合取消；配 `approval/request` + `approval/response` | 壳要做「允许一次 / 始终允许」或缺「取消」这个独立结论时对不上 | 宿主 UI 需要区分「取消」与「拒绝」，或需要 `allow_always` 的存储与撤销时 |

**结论**：下一轮对齐不该是再给 subagent 加特性，而是把「沙箱阶梯」与「工具边界」两个原语各自定下来（各一个 ADR / change）。M13（目标轮次）与 Super-agent 轨都依赖它们；M12 的 spawn 形状可以不动。

### 子代理工具的来源：DSH 的形状与对齐方案

**DSH 事实**（[tool-subagent README](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/subagent/tool-subagent/README.zh.md)）：

- 工具配置有两项：`agentPreset`（默认子级 preset）与 `allowedAgentPresets`（非空白名单）。
- 只有配了白名单，模型才在 schema 里多一个 `agent_preset` **枚举**；没有白名单时**模型不能覆盖**配置里的选择。
- 工具 schema 里**没有 `tools` / 任意工具名列表**：preset 的内容（persona、`toolFilter`）在 preset 注册表里，不在工具参数里。
- 选中的 preset 在启动子级时才解析；未知或加载不了的 preset 返回**出错的工具结果**，子级不启动。
- 子级组装规则：本地 spawn 在「继承或独立选择的 preset」之下拥有自己的注册作用域，不导入父级的 Agent 局部工具限制。

**mini 现状**：`subagent.tools` 是**父模型给的参数**（收窄父工具表），配置层另有会话级 `tools` 白名单；没有子级 preset。两者语义都是「组合过滤」，但来源不同（模型 vs 宿主）。

**结论：已定案，按 DSH 形状在 M14 落地，并删除 `subagent.tools`（ADR-0037）。** 方案（写在这里，避免下次重新推导）：

```toml
# mini.config.toml（草案；现在还没有这段）
[subagent]
preset = "reader"                    # 默认子级 preset
allowed_presets = ["reader", "writer"]  # 有它才给模型 agent_preset 枚举

[subagent.presets.reader]
tools = ["read", "glob", "grep"]

[subagent.presets.writer]
tools = ["read", "write", "edit"]
```

- 子工具表 = **preset 的 `tools` 从内置工具目录取**；**不导入父的局部工具限制**（否则 Router→Worker 形状做不出来）。工具是能力，授权仍由继承的档位/边界/审批管。**已落成**：`[subagent]` 配置、白名单枚举、preset 编译（`config/assembly.py`）与删除 `subagent.tools`。
- 有 `allowed_presets` 时工具 schema 暴露 `agent_preset` 枚举；无白名单时模型不能选。
- 未知 preset → `TOOL_ARGS_INVALID`（与现在的未知工具名同形），不建子会话。
- `subagent.tools` **删除**：无 preset 时子级继承父组合、派发不失效，模型侧裁剪不是必需品；preset + 白名单已经能表达同样的裁剪（ADR-0037）。

**排期**：与 M14 同批——preset 的工具部分先落，`persona` 字段由 M14 补；子级冷恢复落地时把 preset 写进 descriptor 还原（DSH 的 `restoring-child-composition`）。

**没有 preset 时的回落（DSH 原文）**：两个选择字段都省略时，工具**不要求 preset 服务**；子级缺省「加入父方当前的 preset 代际」——也就是继承父的组合，派发照常工作。配置了但解析失败是另一回事：未知或加载不了的 preset 返回出错的工具结果、子级不启动。所以「没配置」= 继承，「配错了」= 报错，两者不能混。

**折中方案（已废弃，保留作历史）**：曾考虑「preset 之上再 ∩ 模型给的 `tools`」；ADR-0037 已定案删除 `tools`，模型只剩「在白名单里选 preset」这一种选择，没有任意工具名的裁剪。

**复杂度记账**（为什么不在 M12 顺手做）：配置要从扁平变嵌套（`SETTINGS_FIELDS` / `layering` / 校验错误码）、工具 schema 要按配置动态生成枚举、要新增 preset 注册表与未知 id 的拒绝路径、冷恢复还要写 descriptor；约等于一个 M14 子切片，且现在没有 persona 可装，先做只会得到一个「只有工具」的半套 preset。

