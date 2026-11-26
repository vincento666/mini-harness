# merge-reasoning-stream 真实端点验收

**日期**：2026-11-26。**端点**：OpenRouter `https://openrouter.ai/api/v1`，模型 `qwen/qwen3.8-27b`（密钥读进程环境 `OPENROUTER_API_KEY`，不进日志）。这是 `docs/reference/verification-endpoint.md` 指定的功能验证端点，不是 deepseek。

**判据**：`model/response.blocks` 保序（reasoning 在前、text 在后）、SSE 上 `reasoning/delta` 与 `model/delta` 是两条流、`usage.reasoning_tokens` 是 `output_tokens` 的子集不重复计。

---

## 0. 入场前发现的一个缺陷（已修）

原来流式解析只认 `delta.reasoning_content`（DeepSeek 系字段名），非流式路径却认 `reasoning_content` 或 `reasoning`。OpenRouter 归一发的是 `delta.reasoning`，于是**同一场会话在流式下思考全丢、非流式却正常**——换端点就哑了。

修法：流式按与非流式同口径取 `delta.get("reasoning_content") or delta.get("reasoning")`（`src/mini_harness/provider/openai_compat.py`），并补 `tests/test_provider_openai.py::test_openrouter_stream_reasoning_key_is_also_understood`，同时在 `specs/provider` delta 里加一条场景锁住。若不修，下文两场都记不到 reasoning 块。

## 1. 场次 A：`chat` 管道（`.tmp/uat-reasoning2`，session `246d03dce97743c29caa78059bd70cf4`）

```bash
printf '用三句话说明为什么天空是蓝色的。\n' | minihns chat \
  --provider openrouter --model qwen/qwen3.8-27b \
  --workspace .tmp/uat-reasoning2 --session-dir .tmp/uat-reasoning2/sessions --max-steps 2
```

退出码 0。stderr 一行 `会话 246d03dce97743c29caa78059bd70cf4`，接着 `[thinking] ` 打头的一次思考整段（198 字符，英文推理），正文开始处 stderr 出 `[answer] `；正文 151 字符落在 stdout，未与思考混流。思考与正文各出现一次，没有重复打印。

日志（`model/response`，`step_id=t1`）：

- `blocks`：`["reasoning", "text"]`，顺序即 provider 给出顺序。
- `usage`：`input_tokens=3360`、`output_tokens=140`、`reasoning_tokens=45`；45 ⊂ 140，未重复计。
- `content` 是正文（去掉 reasoning 后的投影），`reasoning` 全文只在 blocks 里。

## 2. 场次 B：`host` + SSE（`.tmp/uat-reasoning3`，session `8d262fd67f9740d5869dd300117aa8c4`）

`minihns host --http --provider openrouter --model qwen/qwen3.8-27b --sandbox read-only --yes`，`POST /sessions` 后先订阅 `GET /sessions/{id}/events`，再 `POST /sessions/{id}/messages`。帧序列（按到达顺序截取事件名）：

```
session/start, turn/start, user/message, step/start, context/assembled, model/request,
reasoning/delta × 36, model/delta × 45, model/response, step/end, turn/end
```

- `reasoning/delta` 36 条、`model/delta` 45 条，**全部 reasoning 都在任何 `model/delta` 之前**，没有一条思考混进正文流。
- 首条 reasoning 帧：`{"step_id": "t1", "index": 0, "text": "The", "kind": "reasoning"}`；首条正文帧：`{"step_id": "t1", "index": 0, "text": "\n\n潮汐主要由"}`。两条流各有独立 `index`、都按 `step_id` 归属。
- 该会话日志里**不含** `reasoning/delta`，也不含 `model/delta`：ephemeral 帧真的没落盘，durable 真相只有 `model/response`。
- 该会话 `model/response`：`blocks=["reasoning","text"]`，`usage={input_tokens:43, cache_read_tokens:3456, output_tokens:219, reasoning_tokens:143}`；143 ⊂ 219。

`minihns usage` 两侧读数与 payload 一致、没有翻倍：

| session | 入口 | steps | input_uncached | cache_read | output |
|---|---|---|---|---|---|
| `246d03dc…` | chat | 1 (`t1`) | 3360 | 0 | 140 |
| `8d262fd6…` | host | 1 (`t1`) | 43 | 3456 | 219 |

（`output` 就是 payload 的 `output_tokens`，reasoning 已含在内，不是另加一份。）

## 3. 结论与边界

- 真实 reasoner 上四条判据全部成立：blocks 保序、两条流分离、usage 不重复计、ephemeral 不落日志。
- 单次两场样本，只覆盖「单步、思考→正文」形状；「同一 response 内 reasoning → tool-call → reasoning → text」的长形状这次没构造出来，不冒充统计保证。
- 流式解析对 `reasoning` 字段的兼容是本次真端点暴露的缺陷，已连带修掉并加测试；不修则本场验收根本不可能通过。
- tty 手感（`[thinking]` 恰一次、实时刷新、不进 stdout 的观感）不在本场判据内，留给 1.9 人跑（ADR-0025）。
