# Design

## Context

`chat` 现在用 `SessionEnv` 不传 sink，`_print_new_responses` 在段结束后从日志投影正文。`run_turn_segment` 已经支持 `on_delta` / `on_reasoning`；host 已经用它们做 SSE。本 change 只把 chat 接到同一组 sink，不复制流式实现。

## Goals / Non-Goals

**Goals:** `--stream/--no-stream`；实时正文 stdout、实时 reasoning stderr；去重；无 delta 回退；取消不撤回。

**Non-Goals:** 终端折叠 UI、host SSE 改动、Web 壳、逐 token 日志、多模型并发流。

## Decisions

**D1 flag 是 `--stream` / `--no-stream` 互斥，默认 `--no-stream`。** 这样现有 chat 行为、测试、脚本逐点不变；`--stream` 是显式 shell 体验。argparse 用 `add_mutually_exclusive_group`，`dest="stream"`，默认 `False`。

**D2 chat 只注入 sink，不新造流式路径。** `SessionEnv(on_delta=..., on_reasoning=...)`；正文 sink 直接写 stdout 并 flush；reasoning sink 写 stderr `[thinking] ` 前缀，首次写行头，片段连续。provider 仍走既有 `generate`；`stream=True` 由 provider 自己决定。

**D3 去重按 turn_id。** 正文 sink 收到非空片段时把 `turn_id` 记进 `streamed_turns`；`_print_new_responses` 跳过 `turn_id` 在集合里的 `model/response`，避免整段重复。没有片段进的 turn 仍走投影（回退）。

**D4 取消与失败沿用段级形状。** Ctrl-C 仍由现有信号处理器置 cancel；流式只负责已写出的 stdout，不撤回；interrupted/attempt 由内核落账，chat 的状态行照旧。

**D5 reasoning 不进 stdout。** stderr 的 `[thinking]` 行是 shell 的可见提示，不是 durable 正文；`--no-stream` 时 reasoning 不显示（与今天一致）。stdout 仍只放正文，保持 `chat-repl` 的投影约束。

**D6 段结束后只补一次换行。** 流式正文允许没有换行；段结束时若 stdout 当前行非空，补一个 `\n`，让下一条提示符不粘在正文尾部。提示符仍只打印一次。

## Risks / Trade-offs

- **重复/漏打** → `streamed_turns` 只由非空正文 delta 置位；无 delta 回退。
- **reasoning 与正文交错** → 两个 sink 分别写 stdout/stderr；终端可能交错显示，这是 plain terminal 的限制，不做折叠。
- **provider 不流式** → `--stream` 仍可跑；没有 delta 时回退到完整投影。
- **取消时半行** → 保留已输出内容，补状态行；不补最终正文。
- **日志仍只有 durable** → sink 不碰日志；测试检查无 delta 记录。

## Migration Plan

1. flag 与 chat sink 注入。
2. stdout/stderr renderer + `streamed_turns` 去重。
3. 无 delta 回退、取消收尾。
4. CLI blackbox 测试、真实端点、UAT、变异、Learning。
