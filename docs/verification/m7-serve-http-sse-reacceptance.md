# M7 `m7-serve-http-sse` 真实端点重新验收（2026-10-23）

按 ADR-0024 重跑：mock 那一半是门禁四道（本轮 408 条通过 / 5 条跳过），这一份是**真实那一半**。端点与密钥同 `m5-context-budget-compaction-reacceptance.md`。客户端是 `.tmp/reacc/m7_client3.py`（httpx，`trust_env=False`，按 SSE 帧切 `id` / `event` / `data`），比对脚本 `.tmp/reacc/m7_compare.py`。

## 判据逐条

| 判据（`docs/roadmap.md` 的 M7 行） | 结果 | 实测 |
| --- | --- | --- |
| 事件流与 JSONL 日志内容一致 | **通过** | session `50688e79053e46fea73c6045fd5a6797`（`serve --http`，`--window 150000 --reserve 100`，16 条记录，`session/end` = `MODEL_COMPLETED`，`turns: 2`）：`GET /events` 一条连接读到 **16 帧**，`seq` 序列 `[0..15]` 与日志的 `seq` 序列逐位相同；每帧 `id` = 记录 `seq`、`event` = 记录 `type`、`data` 与日志整行**逐字符相同**；比对脚本 `problems=0`。另一次 serve 会话 `2a1b761ce46f4d3b9c7c3a35b72f49a8`（16 条记录）同样 16 帧、`[0..15]` |
| 从任意 `seq` 续读仍一致 | **通过** | 同一次会话：第一条连接读到 `seq` 6 后主动断开，带 `Last-Event-ID: 6` 重连读到 `[7..15]` 共 9 帧；`cut + resume = [0..15]` 与日志完全一致，续读起点是 `cut + 1` |
| `?from` 覆盖 `Last-Event-ID` | **通过** | 第三条连接带 `Last-Event-ID: 9` 且 `?from=2`：帧从 `seq` 3 开始（`[3..15]`），即 `from` 生效、`Last-Event-ID` 被覆盖 |
| 事件流不新增 HTTP 层事实、会话收尾即进程退出 | **通过** | 帧里没有日志外的记录；`cmd /c` 包装下 `minihns serve` 退出码 0 |

## 这一跑查出来的东西

**pwsh 直接重定向 stderr 会让外层报 exit 1，而 CLI 自己没问题。** 两次 `uv run minihns serve … 1>… 2>…` 的会话都是 `MODEL_COMPLETED` 收尾、SSE 帧完整，但 pwsh 作业报 `[exit code: 1]`——stderr 上那行「serve 监听 http://127.0.0.1:8321」被包成 `NativeCommandError`。换成 `cmd /c "… 1>… 2>…"` 后同一会话报 **0**。判 CLI 退出码时别信 pwsh 包装层的那一位。

**会话太短会让「断线续读」测不到。** 第一次尝试里会话 8 秒内跑完（模型把三次 `read` 合成一次），第二个客户端连上去时端口已经关了（`WinError 10061`）。用一次大 `read`（`big.md` 全 2,000 行，`tool/result` 259,136 字符）把第二个回合的模型调用拉长，四条连接才都在会话内完成。真实端点验收要**故意把会话做长**，否则续读类判据是空跑。

## 待人跑的那一半

9.1 的 Ctrl-C（服务端进程中断后日志不出现半条记录）与四条 Windows skip 的 SIGINT 子进程判据。
