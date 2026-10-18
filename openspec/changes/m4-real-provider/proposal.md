# Proposal

## Why

M1–M2 的全部判据都由 mock fixture 驱动，Provider 契约从来没有被真实模型检验过：`ToolSpec` 只有 `name` 与 `description`，模型看不到参数形状；`finish_reason` 只是记录，分支实际看 `tool_calls` 有没有；一轮多调用从未被真实产生过。ADR-0005 把 M4 提到 M3 之前，就是为了让这些抽象在撞进 `bash`、超时与平台差异之前先被真实模型压一遍。

## What Changes

- 新增 **OpenAI 兼容适配器**（`--provider openai`）：`POST <base-url>/chat/completions`，非流式，一次请求拿完整回复。HTTP 客户端用 **httpx**（人已裁决，`pyproject.toml` 多一个运行时依赖）。
- **`ToolSpec` 带上参数 JSON Schema**（ADR-0005 第 4 条的阻塞项）：schema 由注册表里每个工具的 pydantic `args_model` 派生，MUST NOT 手搓第二份。
- **解析 `message.tool_calls` 数组**：一轮内多个工具调用被真实产生并派发（内核已支持一批多个调用，M4 让真实模型真的产生它）。
- **429 与 5xx 重试一次**：只重试一次、只对 429 与 5xx；重试后仍失败塌成 `ProviderFailure` → `error/model` + `stop_reason: PROVIDER_ERROR` + 退出码 1。4xx（429 之外，含 401）不重试。
- **超时与取消**：请求超时塌成失败结果；取消信号已置位时 MUST NOT 再发新请求。
- **`model/retry` 事件落地**（词表已预留、M2 明确不写）：重试是会话事实，不落日志就违反不变量 A/F。
- **CLI 参数扩展**：`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、**`--api-key-env`（默认 `DEEPSEEK_API_KEY`）**。密钥只从指定环境变量读，MUST NOT 出现在命令行、日志或 `session/start` 里。`--provider mock` 仍是默认，既有 mock 判据不变。
- **两个真实端点都要跑通**（人已裁决）：先本地 `http://127.0.0.1:8300/v1`（Strata server，模型 `qwen3.8-flash-next-iq3_xxs`，`max_context 196608`，无视觉，`parallel: 1` 单流 FIFO；服务端原生发 `tool_calls` 与 `finish_reason: "tool_calls"`；**要鉴权**），再 DeepSeek 官方端点收尾。本机事实：该 server 的 config 里两个 key，第一个已失效（401），第二个可用——key 只走环境变量，MUST NOT 进仓库。

**本里程碑明确不做**：流式响应解析；多模型路由与可配置重试策略；`tool_choice` 与强制工具调用；窗口预算与压缩（M5）；`bash`、并发派发、进程超时与平台层（M3）；`--resume` 与投影缓存（MVP 不做清单）；真实 Provider 进 CI（CI 不持 API key，真实 smoke 走人手验收）；token 计费与 usage 预算；读取端点自己的 config 文件取 key。

## Capabilities

### New Capabilities

无。模型层的行为归已有的 `provider` 能力，不新开近义能力。

### Modified Capabilities

- `provider`: 新增 OpenAI 兼容适配器的行为判据（请求形状、`tool_calls` 解析、重试一次、超时、401 不重试、失败塌成 `ProviderFailure`）与「工具面带参数 JSON Schema 且由 `args_model` 派生」；替换「M1 只内置 mock Provider」这条。
- `cli`: `--provider` 取值从只有 `mock` 扩到 `mock` 与 `openai`，新增 `--base-url` / `--model` / `--api-key-env`；密钥只从环境变量读且不进日志。
- `turn-loop`: `error/model` 的 `code` 词表新增 `PROVIDER_HTTP_STATUS` 与 `PROVIDER_TIMEOUT`。
- `event-log`: 词表里 `model/retry` 从「M2 MUST NOT 被写出」改为 M4 可达（一次重试一条记录）。

## Impact

- 依赖：`pyproject.toml` 加 `httpx`；`AGENTS.md` 的「技术选型（已定）」一行需加 `httpx`（人已裁决，尚未写进文件）。
- 代码：`src/mini_harness/provider/` 新增适配器模块；`provider/contract.py::ToolSpec` 加 `parameters` 字段；`tools/registry.py` 派生 schema；`cli/main.py` 的「只 mock」硬门改成 provider 选择。
- 测试：seam ⑤ 用注入的假 HTTP 层驱动全部适配器判据，门禁与 CI 不跑网络、不需要 key；seam ⑥ 覆盖 provider 选择与参数校验。真实端点跑通是**人手验收**，记进 `docs/verification/m4-real-provider-manual.md`。
- 待落 ADR：mini 版相对 DSH 的简化（单适配器、非流式、只重试一次、无 usage 预算）与「本地端点先跑通、DeepSeek 收尾」这条顺序。
- 已知约束：8300 是**单流 FIFO**（一次一条序列），真实 smoke 与跑在它上面的其它会话会互相排队；它的窗口是 196608，M5 的预算判据不能靠它自然触发。
