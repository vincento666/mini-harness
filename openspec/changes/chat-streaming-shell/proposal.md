# Proposal

## Why

`minihns chat` 现在不传 `on_delta` / `on_reasoning`，stdout 是日志投影：模型整段结束后才打印正文。它因此不能作为壳体验流式输出，也不能实时看到思考/正文分流；真正的流式只在 `host` SSE 路径。

本 change 把 `chat` 当作一个 shell：复用现有 `run_turn_segment` 的 delta sink 通路，给 chat 增加 `--stream` / `--no-stream`，不新造 provider 或内核流式路径。

## What Changes

- **`--stream` / `--no-stream`**：互斥；默认 `--no-stream`，保持现有阻塞输出逐点不变；`--stream` 打开 shell 的实时输出。
- **`--stream` 时**：
  - 正文 delta 实时写 stdout；
  - reasoning delta 实时写 stderr（`[thinking]` 前缀），stdout 仍只放正文；
  - 段结束时不再重复打印已经流出的正文；没有 delta 的回复仍走最终日志投影，避免空输出；
  - Ctrl-C 仍按现有段级取消收尾，已流出的部分不撤回。
- **复用现有通路**：chat 的 `SessionEnv` 注入 `on_delta` / `on_reasoning`，provider 仍走 `generate`；不复制 host SSE，不改内核事件形状。
- **非流式不变**：`--no-stream` / 不传 flag 的 stdout、日志、退出码与现在逐点相同。

## Capabilities

### New Capabilities

- `chat-streaming`：chat 的 shell 模式、`--stream/--no-stream`、实时正文/思考分流、去重与取消行为。

### Modified Capabilities

- `chat-repl`：stdout “只打印完整 model/response 正文”的约束增加 `--stream` 分支；非流式分支保持原样。

## Impact

- 代码：`cli/main.py`（chat flag 与渲染）、`loop/turn_loop.py`（已有 sink，无需新形状）、tests（CLI blackbox）。
- 测试：seam ⑥（chat 子进程），用 mock fixture 的 deltas/reasoning_deltas 判流式顺序与去重。
- 规格：新 capability + `chat-repl` delta。
- 验收：真实 reasoner 的 chat 流式；UAT；变异。

## Non-Goals

- 不做真正的终端折叠 UI（plain terminal 只能前缀/分行）；不做 host SSE 改动；不做 Web 壳。
- 不做多路并发模型流、不做逐 token 日志。
