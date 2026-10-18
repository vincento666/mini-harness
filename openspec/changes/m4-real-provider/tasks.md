# Tasks

## 1. 端点事实核查（先探再写判据）

- [ ] 1.1 确认本地端点事实：`GET http://127.0.0.1:8300/health`（免鉴权）拿到 `model` 与 `max_context`；用可用 key 发一条带 `tools` 的最小 `POST /v1/chat/completions`，确认响应里出现 `message.tool_calls` 与 `finish_reason: "tool_calls"`。把请求形状与真实响应样本记进 `docs/verification/m4-real-provider-endpoint-probe.md`。判据：文档存在，含一条真实响应原文与「产出 tool_calls」的结论行。
- [ ] 1.2 在同一文档里记下鉴权事实：config 里两个 key 的实测差异（第一个 401、第二个通），可用那个只设进环境变量（约定名 `MINIHNS_STRATA_KEY`），MUST NOT 写进任何仓库文件。判据：文档含两条结论行，且 `git grep` 在仓库里搜不到该 key 的任何片段。

## 2. 依赖与工具面 schema（seam ②）

- [ ] 2.1 `pyproject.toml` 加 `httpx` 依赖，`uv sync` 后 `uv run python -c "import httpx; print(httpx.__version__)"` 成功打印版本；同时把 `AGENTS.md` 技术选型那行补上 `httpx`。判据：命令退出码 0。
- [ ] 2.2 red：断言送进 provider 的工具面里每个工具都带参数 JSON Schema，且字段名与必填项与该工具派发侧参数模型的 JSON Schema 一致（seam ②）→ green：`ToolSpec` 加 `parameters`，注册表从 `args_model` 派生。判据：该测试先红后绿，且 `mypy --strict src` 干净。
- [ ] 2.3 确认既有 mock 路径不受影响：跑全量测试，既有 seam ⑤⑥ 判据全绿、没有一条被 2.2 改坏。判据：`uv run coverage run -m pytest -q` 退出码 0。

## 3. 适配器骨架与请求形状（seam ⑤）

- [ ] 3.1 red：用注入的假 HTTP 层断言请求形状——URL 是 `<base-url>/chat/completions`、请求体含 `model`、`messages`、`tools`（每个工具带 `parameters`）、密钥存在才带鉴权头、未设不带（seam ⑤）→ green：`provider/openai_compat.py` 的 `generate` 最小实现。判据：该测试先红后绿。
- [ ] 3.2 red：200 响应转成 `AssistantTurn`（`content`、`finish_reason`、`tool_calls`、`usage` 四个字段各断言）→ green。判据：该测试先红后绿。
- [ ] 3.3 red：200 但响应体缺 `choices` → `error/model`（`code: PROVIDER_SCHEMA_INVALID`）、`stop_reason: PROVIDER_ERROR`、退出码 1、没有未捕获异常（seam ⑤ + seam ①）→ green。判据：该测试先红后绿。

## 4. 一轮多调用（seam ①⑤）

- [ ] 4.1 red：假 HTTP 层返回含两个 `tool_calls` 的响应 → 该回合产生两条 `tool/call` 与两条 `tool/result`、`turn/end` 的 `stop_reason` 为 `TOOL_CALLS`（seam ①）→ green（确认内核这条路径真的可达）。判据：该测试先红后绿。

## 5. 重试、状态码与超时（seam ⑤①④）

- [ ] 5.1 red：第一次 429、第二次 200 → 日志恰好一条 `model/retry`（含 `turn_id`、`attempt`、`status`）、退出码 0（seam ⑤ + seam ①）→ green：重试一次，`ProviderFailure` 带回重试事实，回合循环写 `model/retry`（provider 不碰日志）。判据：该测试先红后绿。
- [ ] 5.2 red：两次都 500 → 一条 `model/retry` + 一条 `error/model`（`code: PROVIDER_HTTP_STATUS`）+ 退出码 1 → green。判据：该测试先红后绿。
- [ ] 5.3 red：400 → 没有 `model/retry`、`error/model` 的 `code` 为 `PROVIDER_HTTP_STATUS`、退出码 1 → green。判据：该测试先红后绿。
- [ ] 5.4 red：请求超时 → `error/model`（`code: PROVIDER_TIMEOUT`）、退出码 1、没有未捕获异常 → green。判据：该测试先红后绿。
- [ ] 5.5 red：取消信号已置位时 `generate` 不再发出新请求（假 HTTP 层计数为 0）→ green。判据：该测试先红后绿。
- [ ] 5.6 red：一条含 `model/retry` 的日志被 replay 时每条 `context/assembled` 仍与前缀重算逐字段相等（seam ④）→ green（折叠把 `model/retry` 当事实、不进上下文）。判据：该测试先红后绿。

## 6. CLI 的 provider 选择与密钥（seam ⑥）

- [ ] 6.1 red：`--provider claude` → 退出码 2、stderr 含 `UNKNOWN_PROVIDER`、没有 session 日志 → green。判据：该黑盒测试先红后绿。
- [ ] 6.2 red：`--provider openai --fixture <f>` → 退出码 2、stderr 含 `INVALID_ARGUMENT`、没有 session 日志 → green。判据：该黑盒测试先红后绿。
- [ ] 6.3 red：`--api-key-env` 指向未设的变量 → 请求被发出（不带鉴权头）、假 server 返回 401 → 退出码 1、`error/model`（`code: PROVIDER_HTTP_STATUS`）、没有 `model/retry`、退出码不是 2 → green。判据：该黑盒测试先红后绿，且不依赖 8300。
- [ ] 6.4 red：`--api-key-env` 指向已设的变量 → loopback 假 server 收到带密钥的请求，而 stdout、stderr 与该 session 的日志里都搜不到该值 → green。判据：该黑盒测试先红后绿。
- [ ] 6.5 red：`--provider openai` 的 `session/start` payload 含 `base_url`、`model`、`api_key_env`（变量名），且整份日志里没有密钥的值 → green。判据：该黑盒测试先红后绿。

## 7. 真实端点人手验收（不进 CI）

- [ ] 7.1 用本地端点 `http://127.0.0.1:8300/v1`（`--api-key-env MINIHNS_STRATA_KEY --model qwen3.8-flash-next-iq3_xxs`）拿真实工作区办一件真事（例如把某目录里的 `TODO` 全部改掉），把命令、退出码、日志里 `tool_calls` 的真实形状、耗时、以及「哪儿别扭」记进 `docs/verification/m4-real-provider-manual.md`。判据：文档含至少一次成功的真实会话（session id + 退出码 + 被真实改动的文件）。
- [ ] 7.2 设好 `DEEPSEEK_API_KEY` 后跑同一条命令打到 DeepSeek，在同一文档里记下两个端点的差异（参数 schema 是否被遵守、一轮几个调用、耗时、`finish_reason` 用词）。判据：文档含两个端点各一次真实会话；若 DeepSeek key 尚未拿到，本条保持未勾并在 `docs/CURRENT.md` 记为 M4 的未收尾项。

## 8. 集成检查与收尾

- [ ] 8.1 四道门禁全绿：`coverage erase` → `coverage run -m pytest` → `coverage combine` → `coverage report --fail-under=95`，加 `mypy --strict src`、`ruff check src tests`、`ruff format --diff src tests`。判据：四条命令退出码均为 0 且 `TOTAL` 不低于 95%。
- [ ] 8.2 跑一轮变异测试并记进 `docs/verification/m4-real-provider-mutation.md`（重点变异：重试次数、429 与 400/401 的分支、schema 派生、`model/retry` 的写入位置、密钥是否漏进 payload）。判据：每个变异都被至少一条测试杀死，存活的补一条能杀死它的测试。
- [ ] 8.3 Learning Gate：可复用教训写进 `docs/lessons.md` 收件箱，没有信号就写 `NO-PROMOTION`。判据：`docs/lessons.md` 有本轮条目或 `NO-PROMOTION`。
- [ ] 8.4 用 `domain-modeling` 的 ADR-FORMAT 写 `docs/adr/0006-*.md`：mini 版相对 DSH 的 Provider 简化（单适配器、非流式、只重试一次、无 usage 预算）与「本地 8300 先跑通、DeepSeek 收尾」的顺序，并写明代价；同步更新 `docs/CURRENT.md` 的 ADR 计数与已知缺口。判据：文件存在、`docs/CURRENT.md` 的 ADR 计数与它一致。

## Workflow follow-up

- 分支 `change/m4-real-provider`；`/code-review` 两轴（Standards / Spec）后合入 `main`。
- `/openspec-archive-change` 归档，tag `m4`，归档后跑一次 `agents-md-slim`。
- 归档前确认 `docs/roadmap.md` 的 M4 行完成判据逐条可复现（两个端点的真实 smoke、mock 与真实同一接口、`ToolSpec` 带 schema）；roadmap 那一行的 change 名与 `m4-real-provider` 同步。
