# M4 端点探测（tasks 1.1 / 1.2）

日期 2026-10-18。目的：在写任何适配器判据之前，确认目标端点**真的产出 `tool_calls`**，并把鉴权事实钉下来。结论先行：**产出**，M4 可以开工。

## 端点是什么

`http://127.0.0.1:8300/v1`，进程是 `S:\Develop\AIGC\Strata\Strata\serve\server.py --engine strata --config strata-iq3_xxs-nov-p1.json --port 8300`。它不是 llama.cpp，是 Strata 自己的 server；`GET /health` 免鉴权：

```json
{"status":"ok","max_context":196608,"model":"qwen3.8-flash-next-iq3_xxs","images":false,"api_key":true,"loaded":true,"service":"strata"}
```

`serve/server.py` 的文件头写明它支持 `POST /v1/chat/completions`（OpenAI，流式与非流式）、`POST /v1/messages`（Anthropic）、`/v1/responses`，并且「One sequence at a time behind a FIFO」——**单流**，一次只跑一条序列。

## 探测请求（可复现）

```powershell
$k = ((cmd /c "reg query HKCU\Environment /v MINIHNS_STRATA_KEY") | Select-String 'REG_SZ') -split '\s+' | Select-Object -Last 1
Invoke-RestMethod -Uri 'http://127.0.0.1:8300/v1/chat/completions' -Method Post `
  -ContentType 'application/json; charset=utf-8' -Headers @{Authorization="Bearer $k"} -Body $body
```

`$body` 的形状（一个工具、一个必填参数）：

```json
{"model":"qwen3.8-flash-next-iq3_xxs",
 "messages":[{"role":"user","content":"北京现在天气怎么样？请调用 get_weather 工具查询，city 填 Beijing。"}],
 "tools":[{"type":"function","function":{"name":"get_weather","description":"查询指定城市当前天气",
   "parameters":{"type":"object","properties":{"city":{"type":"string","description":"城市名"}},"required":["city"]}}}],
 "max_tokens":200,"temperature":0}
```

## 真实响应（实测样本）

```
id             chatcmpl-e175c518412b461c8f9b7507
elapsed        2289 ms
finish_reason  tool_calls
message.content       空串（长度 0）
message.tool_calls    1 条：
  id=call_2d52eed146984735bd67b3ce  type=function
  function.name=get_weather
  function.arguments={"city":"Beijing"}          ← 合法 JSON，且符合上面那份 parameters
usage          prompt_tokens 321 / completion_tokens 67 / total_tokens 388
```

**结论 1：该端点产出 `message.tool_calls`，`finish_reason` 是 `tool_calls`，`arguments` 是符合参数 schema 的 JSON 字符串。** 适配器照 OpenAI 的形状解析就够了，不需要为它写特殊的解析分支。

**结论 2：`content` 与 `tool_calls` 可以互斥**——这一轮 `content` 是空串。回合循环不能假设「有 tool_calls 就一定有正文」。

**结论 3：`usage` 字段齐全**（含 `prompt_tokens_details.cached_tokens`），适配器可以直接转进 `AssistantTurn.usage`。

## 鉴权事实（tasks 1.2）

- `/v1/*` 要密钥；`/health`、`/props` 一类免鉴权。
- 端点的 config 文件里 `api_key` 字段是**两个逗号分隔的 key**：第一个已失效（用它请求 `/v1/models` 返回 **401**），第二个可用，`Authorization: Bearer` 与 `x-api-key` 两种形式都通。
- 可用那个 key 已设进用户环境变量 `MINIHNS_STRATA_KEY`；`DEEPSEEK_API_KEY` 也已设，且**两者是不同的值**（脚本比对过，没有打印值）。
- 密钥只从 `--api-key-env` 指定的环境变量读。mini-harness MUST NOT 读端点自己的 config 文件取 key，MUST NOT 把 key 写进仓库、日志、`session/start` 的 payload 或命令行。
- 验证仓库干净：`git grep -n "<key 片段>" -- .` 退出码 1（搜不到）。

## 对本机跑真实 smoke 的约束

- **单流 FIFO**：一次只跑一条序列。跑 `minihns run --provider openai` 时，这条请求与跑在同一 server 上的其它会话（包括跑这个项目的 agent 自己）排队。真实 smoke 的 prompt 要短、`--max-turns` 显式给小值、一次只跑一个 session。
- **窗口 196608**：M5 的预算判据不会在这个端点上自然触发，M5 要用小 W 测。
- 上面那条最小请求的 `prompt_tokens` 是 321（工具 schema 与 chat template 的固定开销），不是 prompt 本身的字数——M5 估预算时别把这条当噪声忽略。
