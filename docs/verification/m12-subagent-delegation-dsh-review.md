# M12 DSH parity review

**日期**：2026-11-06。对照点来自 `docs/reference/subagents.md` 与 `docs/dsh-reference/DSH运行时设计说明.html` 的委派章节。

| 行为 | DSH（公开仓库/文章） | mini | 结论 | 记账 |
|---|---|---|---|---|
| 子代理 spawn | 有（空对话起步，`startActivation({prompt})`） | 有（`subagent` 工具，`task` 必填、不 seed 父历史） | aligned | — |
| 子代理 fork | 有（截至最后一个 `turn/end` 的配平前缀） | 不做 | deferred | ADR-0035；触发条件：需要 KV cache 复用且宿主协议允许 fork 语义 |
| 深度 | `depth = 父 + 1`；`maxDepth` 默认 1，工具可显式指定 | 同左（常量 1），`DEPTH_EXCEEDED` 是结果词 | aligned | 工具级覆盖我们没做 |
| 容量 | `maxActiveSubagents` 默认 8，**按 subagent 树**计，根不占名额；耗尽 `ACTIVATION_LIMIT_REACHED`（浏览器消息 `subagent/delivery-unavailable`） | 每父会话 8 个活跃子代理；耗尽 `ACTIVATION_LIMIT_REACHED` | simplified | 深度 1 时「每树」与「每父」等价；没有 `subagent/delivery-unavailable`（无浏览器消息面）；工具并发上限也是 8，同一批 9 个撞不到额度（design D8） |
| 审批 | 进程内子 agent 被**钉定为 `never`**：每次 ask 在任何应答者之前解析为 rejected；把子级 ask 路由给父级**已延后**；`subagent-acp` 的子侧自动应答是后端自己的 | approval 模式随会话继承（`auto` 继承），门固定 `UNAVAILABLE`；父拿到的也是拒绝结果词 | simplified | 差异在「无人值守」放在哪一轴：DSH 的 Auto 预设是 **full-access 沙箱**（正常写入不触发 ask），mini 的 `auto` 是「全部自动批准」。mini 的 ask 模式对每次会改动都问人，字面钉 `never` 会让子代理连 full-access 下也写不了——要等价，得先有「沙箱升级才问人」的语义（ADR-0036 记账） |
| 子会话声明 | 受保护上下文带 `subagent:delegation`：权限启动时固定、需要审批的操作自动拒绝、**不要重试**、把限制写进回复给父级 | 同左（`DELEGATION_SCOPE_DECLARATION`，`session/start.payload.delegated`） | aligned | 文案是中文、措辞按 mini 的系统提示改写 |
| 子级工具作用域 | `scope.tools = 组合过滤`，**不是授权继承**；`agentPreset` 决定 persona 与工具 | 默认继承父工具表，`tools` 参数收窄；不是权限边界 | simplified | 没有 `agentPreset`（persona/技能归 M14）；`tools` 与 DSH 同形（组合而非授权） |
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

