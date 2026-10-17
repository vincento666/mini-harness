# 里程碑

每个里程碑 = 一个 OpenSpec change（流程见 AGENTS.md 的流程节）。**完成判据是验收口径**，不是内容描述；收尾门禁全绿且判据可复现，才算完成。

| | change | 内容 | 完成判据 |
|---|---|---|---|
| M1 ✅ | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `minihns run` + `minihns replay` | mock 场景跑通；replay 与实时折叠一致 |
| M2 ✅ | `m2-file-tools-and-fences` | `read`/`write`/`edit`(CAS)/`glob`/`grep` + 工作区边界 + 写前必读 + 两轴 | 批量改文件成功（fixture 仓库一轮 10 次 read+edit 全 `OK`）；越界写被拒并写 `error/fence`、退出码 3；真实 tty 的 `y` / `n` 两次 smoke 分别是 0 与 3。**判据全部复现，收尾门禁跑完（变异 19 条 + 审查后抽查 4 条、Learning Gate 收 5 条、`code-review` 两轴修掉两条最重的发现）；已合入 `main`、归档为 `2026-10-18-m2-file-tools-and-fences`、tag `m2`** |
| M3 | `m3-bash-concurrency-timeout` | `bash` + 只读并发（max 8）+ 超时与取消事件 + **平台适配层（路径规范化 / tty / 进程树与信号）+ CI 矩阵（Windows + Linux）** | 一轮内并发读 ≥2；超时写 `tool/cancelled` 且回合继续；同一套判据在 Windows 与 Linux 各跑一遍全绿，门禁由 CI 跑 |
| M4 | `m4-real-provider-deepseek` | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | 真实调用 smoke 通过；mock 与真实同一接口 |
| M5 | `m5-context-budget-compaction` | 窗口预算 + 触发线公式 + 剪枝 + 摘要 + 遮蔽 + 标记对 | 小 W 下触发压缩；原文事件仍在日志里 |
| M6 | `m6-chat-repl` | `minihns chat` REPL，复用同一内核入口 | REPL 续跑同一会话内核 |
| M7 | `m7-serve-http-sse` | `minihns serve --http` 输出 SSE 事件流 | 事件流与 JSONL 日志内容一致 |

## 尚未实现的命令

```bash
uv run minihns chat           # M6 之后
uv run minihns serve --http   # M7 之后
```

## 跨平台与 CI 排在哪儿（2026-10-17 裁决）

跨平台对齐**并入 M3**，不单开里程碑：M3 的 `bash`、超时与取消撞的是硬平台差异（Windows 没有 POSIX 进程组，进程树 kill 走 job object 或 `taskkill /T`；PTY 与信号语义不同），判据本身就要在两端各跑一遍。CI 矩阵与它同期落地——没有 CI，「两端都跑绿」这句话无法被机器验证，跨平台会退化成手动 smoke。

代价：M2 与 M3 期间的实现按 Windows 语义写（路径大小写、junction、tty、SIGINT），到 M3 才在 Linux 上验证并补齐。MVP 不做 web / Electron 外壳实现（见 AGENTS.md），「其他端」的接缝只在 M7 的 SSE 事件流上，外壳本身属 MVP 之外。
