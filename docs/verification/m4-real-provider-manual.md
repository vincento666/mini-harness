# M4 真实端点人手验收（task 7.1 / 7.2）

分支 `change/m4-real-provider`，提交 `5f907fd` 之后的工作树。不进 CI。

## 前提

- 本地端点 `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`（DSH 自己用的那个端点：单流 FIFO、无视觉）。密钥走 `--api-key-env MINIHNS_STRATA_KEY`，值不落进任何记录。
- 工作区 `.tmp/m4-manual/`（gitignored）：`inbox.md` 5 条 TODO、`notes/week-41.md` 2 条 TODO、`README.md` 说明。里面的 TODO 是本仓库真实存在的欠账（见 `docs/CURRENT.md` 与 ADR-0004）。
- 任务：把两个文件里的 TODO 合并成一份 `TODO.md`，按文件顺序编号、保留原措辞，不许改动源文件。
- 因为 8300 是单流 FIFO 且本次验收与 DSH 自己共用它，prompt 短、`--max-turns 6`、一次只跑一个 session。

## 7.1 本地 8300：成功

```
uv run python -m mini_harness.cli.main run \
  -p "把 inbox.md 和 notes/week-41.md 里所有 TODO 条目合并成一份 TODO.md：按文件顺序编号，保留原措辞，每条一行；不要改动 inbox.md 与 notes/week-41.md。" \
  --provider openai --base-url http://127.0.0.1:8300/v1 \
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY \
  --workspace .tmp/m4-manual --session-dir .tmp/m4-manual/sessions \
  --max-turns 6 --yes
```

- session id `bd7dd019bb2a42cea1d0e11d564d9dc2`，退出码 **0**，墙钟 **14.9 s**，日志 24 KB / 37 条记录。
- 产出 `.tmp/m4-manual/TODO.md`：7 条，顺序与源文件一致、措辞未改；`inbox.md` 与 `notes/week-41.md` 没有被改动（日志里对它们只有 `read`）。

逐回合（`model/response` 的 `finish_reason` / 调用数 / usage）：

| 回合 | finish_reason | 工具调用 | in / out tokens |
| --- | --- | --- | --- |
| t1 | `tool_calls` | `read` ×2（同一回合两个调用） | 900 / 73 |
| t2 | `tool_calls` | `glob` ×1 | 1191 / 39 |
| t3 | `tool_calls` | `write` ×1 | 1243 / 235 |
| t4 | `tool_calls` | `read` ×1（写完回读校验） | 1475 / 66 |
| t5 | `stop` | — | 1702 / 384 |

合计 7308 tokens。`turn/end` 的 `stop_reason` 前四回合是 `TOOL_CALLS`、末回合 `MODEL_COMPLETED`，`session/end` 是 `MODEL_COMPLETED`。

日志里 `tool_calls` 的真实形状（seam ③ 的派发侧直接吃它）：

```json
{"turn_id":"t1","tool_call_id":"call_9276140a5fc3423a80a14467","name":"read","arguments":{"file_path":"inbox.md"}}
```

- 一轮两个调用确实落地成两条 `tool/call` + 两条 `tool/result`（task 4.1 的判据在真实端点上复现）。
- `arguments` 是解析过的对象，不是字符串；字段名与 `read` 的参数模型一致（`file_path`），说明工具面的 JSON Schema 被端点遵守。
- 密钥：整份日志里 `MINIHNS_STRATA_KEY` 的值 **0 次命中**，变量名 `MINIHNS_STRATA_KEY` 1 次命中（`session/start.payload.api_key_env`）。
- 日志里的 `usage` 是 `{"input_tokens":…,"output_tokens":…}`——mini 自己的 `Usage` 拼写；端点回的是 `prompt_tokens`/`completion_tokens`（实测 `/v1/chat/completions` 的原始响应），适配器负责这次翻译。

### 哪儿别扭（真实观察）

1. **模型不叙述**：四个 `tool_calls` 回合的 `content` 都是空串。日志里看不见「它打算干什么」，只能从 `tool/call` 反推意图。对可观测性（不变量 F）不算缺口——事实都在——但人读日志时会缺一层。
2. **t2 的 `glob` 是多余的**：两个文件都读完了，它又 glob 一遍（大概是确认 `TODO.md` 不存在）。多花一个回合、1191 个输入 tokens。
3. **上下文单调增长**：900 → 1702 输入 tokens，五个回合翻了近一倍。M3 的窗口预算（不变量 D）会被真实端点顶到，不是理论问题。
4. **`--yes` 是必须的**：不给 `--yes` 时写类工具落在 approval 门上，stdin 非 tty → `UNAVAILABLE` → 拒绝、退出码 3。人手验收第一次就跑的是 `--yes`，非 `--yes` 的路径只有 seam ② 的黑盒测试覆盖。
5. **端点没有 `--max-turns` 之外的刹车**：t5 的 384 输出 tokens 是一段人读不着的总结，`--yes` 模式下它照样进日志、照样计费。

## 7.2 DeepSeek：未达成（账户余额）

同一条任务、同一份工作区副本（`.tmp/m4-manual-ds/`），只换端点与密钥变量：

```
uv run python -m mini_harness.cli.main run -p "…" \
  --provider openai --model deepseek-chat --api-key-env DEEPSEEK_API_KEY \
  --workspace .tmp/m4-manual-ds --session-dir .tmp/m4-manual-ds/sessions \
  --max-turns 6 --yes
```

- session id `8edd79c3d12b4416a89c645bd8502b2b`，退出码 **1**，墙钟 **0.94 s**。
- 唯一一条模型记录：`error/model code=PROVIDER_HTTP_STATUS detail=HTTP 402`，`turn/end` 与 `session/end` 都是 `PROVIDER_ERROR`；`model/retry` **0 条**（402 是 4xx，按规格不重试）。
- 402 说明密钥被接受（不是 401），DeepSeek 侧回的是「余额不足」。工作区没有被改动。
- 这条判据要求「两个端点各一次**成功**的真实会话」，**没有达成**：`tasks.md` 的 7.2 保持未勾，`docs/CURRENT.md` 记为 M4 的未收尾项。两个端点的差异对比（参数 schema 遵守、一轮几个调用、耗时、`finish_reason` 用词）等 key 有余额再补。

## 顺带钉住的环境事实（task 6.x 期间踩到）

- 本机 `NO_PROXY=localhost,127.0.0.1,::1,[::1]`。httpx 默认 `trust_env=True` 会在构造客户端时抛 `httpx.InvalidURL: Invalid port: ':1]'`——它不是 `httpx.HTTPError` 的子类，会绕过 provider 的失败捕获、直接给一个未捕获 traceback。实测三种情形：默认 → `InvalidURL`；`trust_env=False` → 正常发请求；删掉 `NO_PROXY` → 正常发请求。
- 裁决：适配器 `trust_env=False`，不继承 `HTTP_PROXY` / `NO_PROXY` / netrc。代价：处在公司代理之后的用户无法经代理访问远端端点（记进 ADR-0006）。
- 本机 `HTTP_PROXY=http://127.0.0.1:7897` 存在，但 `trust_env=False` 下直连 `api.deepseek.com` 拿到了真实的 402 响应——直连这条路是通的。
