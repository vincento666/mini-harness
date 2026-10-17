# 里程碑

每个里程碑 = 一个 OpenSpec change（流程见 AGENTS.md 的流程节）。**完成判据是验收口径**，不是内容描述；收尾门禁全绿且判据可复现，才算完成。

| | change | 内容 | 完成判据 |
|---|---|---|---|
| M1 ✅ | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `minihns run` + `minihns replay` | mock 场景跑通；replay 与实时折叠一致 |
| M2 | `m2-file-tools-and-fences` | `read`/`write`/`edit`(CAS)/`glob`/`grep` + 工作区边界 + 写前必读 + 两轴 | 批量改文件成功；越界写被拒并写事件、退出码 3 |
| M3 | `m3-bash-concurrency-timeout` | `bash` + 只读并发（max 8）+ 超时与取消事件 | 一轮内并发读 ≥2；超时写 `tool/cancelled` 且回合继续 |
| M4 | `m4-real-provider-deepseek` | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | 真实调用 smoke 通过；mock 与真实同一接口 |
| M5 | `m5-context-budget-compaction` | 窗口预算 + 触发线公式 + 剪枝 + 摘要 + 遮蔽 + 标记对 | 小 W 下触发压缩；原文事件仍在日志里 |
| M6 | `m6-chat-repl` | `minihns chat` REPL，复用同一内核入口 | REPL 续跑同一会话内核 |
| M7 | `m7-serve-http-sse` | `minihns serve --http` 输出 SSE 事件流 | 事件流与 JSONL 日志内容一致 |

## 尚未实现的命令

```bash
uv run minihns chat           # M6 之后
uv run minihns serve --http   # M7 之后
```
