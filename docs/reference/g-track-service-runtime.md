# G 轨：服务化运行时（多用户 / 客服 / 连接器）——规划口径

**状态**：规划口径，**不是 spec**。G 轨在 `personal-baseline-v1` 之后另开分支；不混进 M 轨。

**一句话**：把个人内核变成可接现有客服平台/多用户的**服务化运行时**；只做智能客服机器人的核心能力和基础接口，**不做**转人工、会话队列、质检、SLA 管理、PII 全治理。

---

## 1. 目标

- 多 worker、持久队列、共享 session store、可水平扩展。
- 接现有客服平台：入站消息 → 会话映射 → 机器人核心 → 出站回复；**转人工/队列/质检由平台负责**。
- 基础作业与调度：后台 job、cron/heartbeat/standing orders。
- 连接器：web/browser、MCP resources、业务 API（日历/邮件/文档/CRM）。
- 多租户隔离：tenant/user 的 session、memory、quota、数据边界。
- 运维：audit、metrics、health、backup；OTel/telemetry 可选、opt-in。
- 复用 E2 的组件/注册表；不 fork 内核。

---

## 2. 明确不做（记账，不再重开）

| 不做 | 原因 |
|---|---|
| **PTC 工具面塌缩** | AGENTS 已写“始终不做”；要 sandbox/JS guest/语言运行时，不是最小实现 |
| **model fallback / model routing** | AGENTS 已写“始终不做多模型路由与重试策略”；现有 429/5xx 重试一次保持现状 |
| **routing（model / agent routing）** | 平台负责渠道/客服路由；mini 只做 `conversation_id → session_id` 的映射，不做路由引擎 |
| **转人工 / 会话队列 / 质检** | 现有客服平台已提供；mini 只发 handoff 信号，不拥有队列与坐席 |
| **SLA 管理 / SLA 报表** | 平台所有；mini 只承诺延迟/超时契约 |
| **PII 全治理（consent / DSR / 留存门户）** | 平台所有；mini 只做“日志不泄 PII、最小脱敏、可删” |
| **plugin manager / HMR / 插件市场** | E2 只做会话级组件；HMR 不做 |
| **完整 workflowEngine / teams / workflow 图引擎** | 只做最小线性 workflow/team（用 plan + subagent），不做 PTC 图引擎 |
| **多租户计费 / 工单 / triage** | 不属于本项目 |

「不做」不等于「不存在」：平台已有的能力通过 **基础接口**接进来；mini 不复制它们。

---

## 3. G0–G6

| 层 | 内容 | 完成判据 |
|---|---|---|
| **G0 服务运行时** | 多 worker、持久队列、lease/affinity、共享 session store、背压/重试/幂等/优雅 drain | 两个 worker 能并行处理不同会话；worker 崩溃后 job 可重投；无重复回复 |
| **G1 Bot API / 平台适配** | 入站 webhook/HTTP/WS；出站回复/流式；`tenant_id`/`user_id`/`conversation_id` 映射；auth/HMAC；幂等键；handoff 信号；错误/超时契约 | 一个真实平台适配器端到端跑通；重复投递不重复回复；handoff 信号可被平台消费；错误里无 PII |
| **G2 Jobs / Schedule** | 持久 job、cron/interval/heartbeat、standing orders、重试/死信/取消 | 定时任务按时触发；失败重试到死信；取消可生效；job 状态可查 |
| **G3 Connectors** | 连接器注册表 + 适配器：web/browser、MCP resources、业务 API；auth/secret、rate limit、timeout、idempotency、audit | 注册一个 web 与一个业务连接器；超时/限流/重试是结果；凭据不进日志 |
| **G4 租户 / 记忆** | per-tenant/user session、memory、quota、数据边界、保留/删除 | 租户 A 读不到租户 B；memory 按用户隔离；删除可执行 |
| **G5 Ops** | audit、metrics、health、backup/migration；OTel/Prometheus 可选；telemetry opt-in | 每次工具调用/审批/回复有 audit；指标可查；默认不导出 telemetry |
| **G6 智能客服核心** | RAG/FAQ 知识检索、多轮上下文、工具调用、记忆、guardrails、置信度/兜底；**不含**队列/质检/转人工 | 一组真实 FAQ/业务问题答对率达标；低置信度触发 handoff 信号；引用可追溯 |

G6 可以跟 G1 并行；G2 在 G3 之前（连接器需要可靠 job）；G5 的 audit 与 G4 同期，不要等最后。

---

## 4. 客服接口契约（G1 的最小面）

**入站**（平台 → bot）：

```json
{
  "tenant_id": "t1",
  "user_id": "u1",
  "conversation_id": "c1",
  "message": "...",
  "metadata": {"channel": "web", "locale": "zh-CN"},
  "idempotency_key": "..."
}
```

**出站**（bot → 平台）：

```json
{
  "reply": "...",
  "citations": [{"title": "...", "url": "..."}],
  "confidence": 0.82,
  "handoff": {"needed": false, "reason": null},
  "trace_id": "..."
}
```

- 认证：Bearer / HMAC 二选一；密钥只从 secret store/env。
- 会话：`conversation_id` ↔ `session_id` 的映射与 TTL；同一会话串行，不同会话可并行。
- 幂等：同一 `idempotency_key` 不重复回复。
- 超时：bot 给自己设回复上限；超时返回 handoff/兜底，不把平台挂住。
- 流式：SSE 可选；平台不支持就整段返回。
- **不做**：转人工队列、坐席分配、质检评分、SLA 报表；这些由平台做。

---

## 5. SLA 与 PII：能不能不做？

### SLA

**SLA（Service Level Agreement）** 是服务等级承诺：响应时间、解决时间、可用性、并发、升级时限等。  
在“已有客服平台”的前提下：

- **SLA 管理/报表可以不做**：平台拥有 SLA，mini 只是后端 bot。
- **但延迟/超时/可用性契约不能不做**：bot 要给自己设 p95 首 token、最大回复时间、超时→handoff/兜底、限流/降级。否则平台会把超时算到你头上。
- 结论：**SLA 管理不做；延迟契约要做**。

### PII

**PII（Personally Identifiable Information）** 是能识别个人的信息：姓名、手机号、身份证、地址、邮箱、聊天内容里的敏感字段等。  
平台通常负责 consent、留存、DSR、合规；但 bot 仍然会**接触并可能记录**这些内容：

- 必须做：日志/trace 不写原始 PII 与密钥；错误信息不回显 PII；长期记忆默认不存 PII；提供删除/保留钩子。
- 可以交给平台：consent、DSR 门户、合规报表、留存策略的“制度”部分。
- 结论：**PII 全治理可以不做；PII 不泄漏/最小脱敏/可删除的基线不能不做**。内网测试可再放宽，生产客服不行。

---

## 6. 顺序

```text
personal-baseline-v1
→ E2 组件接缝（推荐，先有组件/归因）
→ G0 服务运行时
→ G1 Bot API / 平台适配
→ G2 Jobs / Schedule
→ G3 Connectors
→ G4 租户 / 记忆
→ G5 Ops（audit 与 G4 同期）
→ G6 智能客服核心（可与 G1 并行）
```

G 轨不阻塞 M 轨；M 轨也不为 G 轨提前做多租户/多 worker。两边共享内核与 E2 组件，不共享单用户假设。

---

## 7. 开放问题

- 现有客服平台的具体协议（webhook/WS/HTTP）与鉴权方式；先做一个 adapter，不做通用网关。
- `conversation_id` 的生命周期与 TTL；平台是否支持 resume。
- RAG/FAQ 的数据源与更新频率；G6 是否复用 MEM1/MEM2。
- audit 的保留期与访问控制；PII 脱敏规则由平台还是 mini 配置。
- G2 的 job 存储：SQLite 起步还是直接共享 DB；多 worker 的 lease 语义。
