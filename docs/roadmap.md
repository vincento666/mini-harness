# 里程碑

每个里程碑 = 一个 OpenSpec change（流程见 AGENTS.md 的流程节）。**完成判据是验收口径**，不是内容描述；收尾门禁全绿且判据可复现，才算完成。

**执行顺序（2026-10-18 裁决，ADR-0005）：M1 → M2 → M4 → M3 → M5 → M6 → M7。** 编号是决策编号、不是执行顺序；下表按执行顺序排，所以下一个未完成的里程碑是 M3。

| | change | 内容 | 完成判据 |
|---|---|---|---|
| M1 ✅ | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `minihns run` + `minihns replay` | mock 场景跑通；replay 与实时折叠一致 |
| M2 ✅ | `m2-file-tools-and-fences` | `read`/`write`/`edit`(CAS)/`glob`/`grep` + 工作区边界 + 写前必读 + 两轴 | 批量改文件成功（fixture 仓库一轮 10 次 read+edit 全 `OK`）；越界写被拒并写 `error/fence`、退出码 3；真实 tty 的 `y` / `n` 两次 smoke 分别是 0 与 3。**判据全部复现，收尾门禁跑完（变异 19 条 + 审查后抽查 4 条、Learning Gate 收 5 条、`code-review` 两轴修掉两条最重的发现）；已合入 `main`、归档为 `2026-10-18-m2-file-tools-and-fences`、tag `m2`** |
| M4 ✅ | `m4-real-provider`（原名 `m4-real-provider-deepseek`，因先跑本地端点而改名） | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | **两个端点各一次真实 smoke 跑通**：本地 `http://127.0.0.1:8300/v1`（Strata server，模型 `qwen3.8-flash-next-iq3_xxs`）先跑通，DeepSeek 官方端点收尾；mock 与真实同一接口；`ToolSpec` 带上参数 schema（ADR-0005 第 4 条那条阻塞项已在 tasks 2.1–2.3 解决）；真实 smoke 不进 CI。**判据全部复现，收尾门禁跑完（变异 18 条：17 条首轮被杀、存活的 E2 补三条判据后被杀；Learning Gate 晋升 1 条进 Active、收件箱收 3 条并消化 7 条；`code-review` 两轴 16 条发现里修 5 条、记账 11 条）；已合入 `main`、归档为 `2026-10-18-m4-real-provider`、tag `m4`** |
| M3 ⬅ 下一个 | `m3-bash-concurrency-timeout` | `bash` + 只读并发（max 8）+ 超时与取消事件 + **平台适配层（路径规范化 / tty / 进程树与信号）+ CI 矩阵（Windows + Linux）** | 一轮内并发读 ≥2；超时写 `tool/cancelled` 且回合继续；同一套判据在 Windows 与 Linux 各跑一遍全绿，门禁由 CI 跑 |
| M5 | `m5-context-budget-compaction` | 窗口预算 + 触发线公式 + 剪枝 + 摘要 + 遮蔽 + 标记对 | 小 W 下触发压缩；原文事件仍在日志里 |
| M6 | `m6-chat-repl` | `minihns chat` REPL，复用同一内核入口 | REPL 续跑同一会话内核 |
| M7 | `m7-serve-http-sse` | `minihns serve --http` 输出 SSE 事件流 | 事件流与 JSONL 日志内容一致 |

**每个里程碑的完成判据里都含一条人手验收**（ADR-0005）：用真实工作区干一件真事——不是跑判据，是拿它办一件事——把观察记进 `docs/verification/<change-id>-manual.md`。它不进 CI、不替代上面任何一条判据；它记的是「用起来是什么样」和「哪儿别扭」。M1 与 M2 的这条补在 `docs/verification/m1-m2-manual-smoke.md`。

## 尚未实现的命令

```bash
uv run minihns chat           # M6 之后
uv run minihns serve --http   # M7 之后
```

## 跨平台与 CI 排在哪儿（2026-10-17 裁决）

跨平台对齐**并入 M3**，不单开里程碑：M3 的 `bash`、超时与取消撞的是硬平台差异（Windows 没有 POSIX 进程组，进程树 kill 走 job object 或 `taskkill /T`；PTY 与信号语义不同），判据本身就要在两端各跑一遍。CI 矩阵与它同期落地——没有 CI，「两端都跑绿」这句话无法被机器验证，跨平台会退化成手动 smoke。

代价：M2 与 M3 期间的实现按 Windows 语义写（路径大小写、junction、tty、SIGINT），到 M3 才在 Linux 上验证并补齐。MVP 不做 web / Electron 外壳实现（见 AGENTS.md），「其他端」的接缝只在 M7 的 SSE 事件流上，外壳本身属 MVP 之外。

**2026-10-18 追加裁决（ADR-0005）**：M4 换到 M3 之前，于是「两端各跑绿」与 CI 矩阵整体后移一个里程碑，Windows 绑定点的欠账多攒一个里程碑（M4 的 HTTP 与 JSON 本身跨平台，路径 / tty / SIGINT 那三处照旧欠着）。CI 不持 API key：门禁那道必须离线可跑，所以 CI 只跑 mock 判据，真实 Provider 的 smoke 归人手验收。
