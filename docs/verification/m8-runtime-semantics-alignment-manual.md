# M8 人手验收（`m8-runtime-semantics-alignment`）

**状态：跑完（2026-10-20 15:23–18:07，人在真 PowerShell 终端，六个 session）。** 第一轮里 M8 最想看的那个形状（取消落在批次中途、后面的调用没派发）没出现，第二轮重跑出现了：`cb15c24e14c34c6dbd3d449f23bc31ec`。

跑法：真终端 Windows PowerShell，仓库根 `S:\Develop\mini-harness`，端点 `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`，密钥走 `--api-key-env MINIHNS_STRATA_KEY`。工作区 `.tmp/m8-manual/`（gitignored），日志 `.tmp/m8-manual/sessions/`。取证脚本 `.tmp/m8-manual-inspect.py` 与 `.tmp/m8-manual-order.py`（`.tmp` 不入库，脚本内容在本文件末尾复述）。

## 场景 A：一次回合八条 `read`（session `e0f7c940f4bf4fd79a6c0f276b01610c`）

35 条记录，墙钟 11.70 s，两个回合，退出码 **3**。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 同一回合八条 `read` | 八条一次性声明 | ✓ seq 5–12，`ts` 全在 `07:23:00.748`–`.749` |
| `tool/call` 顺序 | 声明顺序 | ✓ `big, a, b, c, tiny, big, a, c` |
| `tool/result` 顺序 | 完成顺序，不要求声明顺序 | **这次看不出区别**：八条 read 都在 1 毫秒内完成（`.750`–`.751`），完成顺序恰好等于声明顺序。只读调用太快，这个形状要重跑才能显形（见 A′） |
| 交错形状 | 每个 id 自己的 `tool/call` → `tool/result` 相对顺序成立 | ✓ 八条 CALL 全在前、八条 RESULT 在后，每个 id 的相对顺序成立 |
| 八条都有配对结果 | 没有缺结果的 `tool/call` | ✓ 未配对 0 条。其中 4 条 `PATH_NOT_FOUND`——**工作区准备的锅**：`notes/a.md` `b.md` `c.md` 当时没建成（我用 PowerShell 建文件时 `Set-Content -Encoding utf8NoBOM` 在 5.1 上不存在，三条没写出来）。已补 |
| `TOOL_OUTCOME_UNKNOWN` | 日志里 0 次 | ✓ 0 次 |
| 并发上限 | 同一回合最多 8 个只读调用 | 未测到：这次恰好八条，没有第九条 |
| 退出码 | 期望 0 | **3**：模型在 t2 改用 `glob` + `bash`（`ls -la notes/ … wc -l notes/*`），bash 停在终端前提问，人按了回车 → `DENIED_BY_APPROVAL` → `error/fence APPROVAL_DENIED` → `turn/end FENCE_DENIED` → `session/end FENCE_DENIED` → 退出码 3 |

**清单外但值得记的一条**：那次围栏拒绝没有掀翻已经跑完的东西——t1 八条 read 的结果一条不少，被拒的那条自己有一条 `DENIED_BY_APPROVAL` 结果加一条 `error/fence`。这就是不变量 B（失败也是结果）与「围栏不吞已完成批次」在真 run 里的样子。

## 场景 B：真 Ctrl-C（session `b1f784d520214c2c96eab6f3ecfa2282`）

13 条记录，墙钟 15.41 s，一个回合。第一次尝试是 `325d962d951f4965b6a137707a14f97a`（56 条，墙钟 83.21 s，`MODEL_COMPLETED`）。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 提问 | 一条 bash 提问，答 `y` 之后进程才起 | ✓ `允许 bash 改动 python sleep.py，输入 y 或 n：`（写 stderr）。第一次尝试里模型连问三次 bash，三次都答 `y`，三条 bash 结果都是 `OK` |
| 被打断的那条 | `TOOL_CANCELLED` 紧跟 `tool/cancelled` | ✓ seq 8 `tool/result TOOL_CANCELLED` → seq 9 `tool/cancelled`，同一个 `tool_call_id` |
| 排在它后面的调用 | 各一对 `tool/call` + `tool/result(ABORTED_BEFORE_DISPATCH)`，没有 `tool/cancelled` | **没出现**：那个回合只声明了一条调用（模型习惯一个回合一条 bash），取消没有落在批次中途。这是 A′/B′ 要重跑的原因 |
| 收尾 | `error/abort` → `turn/end ABORTED` → `session/end ABORTED` | ✓ seq 10 / 11 / 12 正是这个顺序 |
| 退出码 | 5 | 未记录（stderr 是 `ABORTED:`，`echo "exit=$LASTEXITCODE"` 那一步当时没跑） |
| 进程树 | `sleep.py` 的 python 进程不活着 | 未单独查；`tool/result` 已落说明执行段返回了（M3 记过：后代握着管道句柄时它不会返回） |
| Ctrl-C 之前已落盘的记录 | 不是等批次结束才出现 | ✓ seq 5 `tool/call` 在提问之前就在盘上（`approval/request` 是 seq 6） |

**Windows 真控制台的 Ctrl-C 实测生效** ✓。M3 记的边界是「往子进程发 `CTRL_C_EVENT` 那条黑盒在 Windows 走不通」，那是**测试装置**走不通；人手在真终端按 Ctrl-C 这条路是通的，本轮第一次跑通。

## 场景 C：读那份半截日志（同一 session）

`b1f784d520214c2c96eab6f3ecfa2282.jsonl` 4227 字节。

| 观察点 | 期望 | 实际 |
|---|---|---|
| replay 退出码 | 0 | ✓ `exit=0` |
| 逐点重放 | 每个 `context/assembled` 一条 `verified seq=N: OK`，无 `REPLAY_MISMATCH` | ✓ `verified seq=2: OK`（这份日志只有一条 `context/assembled`），`turn t1: ABORTED` |
| 日志没被追加 | 前后字节数相同 | ✓ 4227 → 4227 |
| `final_context` 里的闭合 | 未配对的调用各有一条 `TOOL_OUTCOME_UNKNOWN` 消息 | **观察点写错了，两处**：① `replay` 打的是**最后记录的那一条** `context/assembled`，也就是回合开始时的上下文（system + user 两条消息），它不是「整份日志重折叠的结果」，本来就不会含闭合；② 这份日志里未配对的 `tool/call` 是 0 条——M8 之后真 run 里内核保证每条声明过的调用都有配对结果（包括没派发的），所以闭合派生只在**半截日志**（硬杀）的读方路径上出现，归 seam ④ 与 seam ⑥ 判，人手验收看不到它 |

## 第二轮重跑

### B′：取消落在批次中途（session `cb15c24e14c34c6dbd3d449f23bc31ec`）——M8 的新语义在真 run 里现形

23 条记录，墙钟 16.81 s，一个回合，**退出码 5**。同一个回合声明六条：`bash python sleep.py`（`timeout_seconds: 60`）加五条 `read`。答 `y` 之后在 `sleep.py` 挂着时按一次 Ctrl-C。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 被打断的那条 | `TOOL_CANCELLED` 紧跟 `tool/cancelled` | ✓ seq 5 `tool/call` → seq 8 `tool/result TOOL_CANCELLED`（`10:06:05.487`）→ seq 9 `tool/cancelled`，同一个 id |
| 排在它后面的五条 | 各一对 `tool/call` + `tool/result(ABORTED_BEFORE_DISPATCH)` | ✓ seq 10–19：五对**紧挨着**落盘，`ts` 全是 `10:06:05.488`，结果词全是 `ABORTED_BEFORE_DISPATCH` |
| 它们没有 `tool/cancelled` | 日志里 `tool/cancelled` 只有一条 | ✓ 只有一条，配的是 bash 那个 id |
| 它们真的没跑 | 没有一条真的读到内容 | ✓ 五条结果都在「取消在派发之前置位」那一句上 |
| 落盘顺序是完成顺序 | 不是声明顺序 | ✓ 声明顺序是 `bash, a, b, c, tiny, big`；落盘是 bash 的结果先（`.487`），五条的 `tool/call` 与结果全在它之后（`.488`）——排在后面的调用连「开始」都是取消之后才补的记录 |
| 收尾 | `error/abort` → `turn/end ABORTED` → `session/end ABORTED` | ✓ seq 20 / 21 / 22 |
| 退出码 | 5 | ✓ `exit=5` |
| 未配对的 `tool/call` | 0 条 | ✓ 0 条；`TOOL_OUTCOME_UNKNOWN` 在日志里 0 次 |

**对照组**（同一份提示、没按 Ctrl-C，session `f4a255521a5a4e9abcdc6cef224f454f`，26 条，墙钟 30.23 s，`MODEL_COMPLETED`，退出码 0）：bash 的结果落在 `10:06:44.937`，五条 `read` 的 `tool/call` 落在 `.938`–`.939`——**它们一直等到那条会改动的调用结束才开始**（不变量 E 的串行规则）。同一批六条调用，一次被取消在半路、一次跑完，两份日志的差别只有「五条的结果词是什么」。

### A′：八条 `read` 里放一条 1.9 MB 的（session `97dec3cd131d4f789c328367c3e7cc14`）

41 条记录，四个回合，退出码 0。八条 `read` 一次性声明 ✓（seq 5–12，`ts` 全在 `08:25:34.416`–`.417`），八条结果落在 `.424`–`.425`。

| 观察点 | 期望 | 实际 |
|---|---|---|
| `tool/call` 顺序 | 声明顺序 | ✓ `huge, tiny, a, b, c, tiny, a, big` |
| `tool/result` 顺序 | 完成顺序 | **仍然与声明顺序重合**：`huge.md` 那条 8 毫秒完成（`.416` → `.424`），七条小文件紧随其后（`.424`–`.425`）。八条只读调用并发跑（上限 8），先派发的先完成，所以看不出「后声明的先完成」 |
| 都有配对结果 | 0 条未配对 | ✓ 0 条，八条全 `OK` |

**这条形状在真 run 里抓不到，记为边界**：只读调用之间的耗时差是毫秒级，而派发顺序就是声明顺序，所以「完成顺序 ≠ 声明顺序」需要人为造一个慢的只读调用。它由 seam ① 的 `test_the_faster_result_is_on_disk_before_the_slower_one_finishes`（造一条先完成的调用）与 `test_results_land_in_completion_order_when_the_second_finishes_first` 判，人手验收不判。

**顺带看见的**：`read` 的窗口契约在真 run 里的样子——`huge.md` 20000 行只返回前 2000 行，模型于是又开了三个回合分别读 `offset: 2001`、`2011`、`4011`。

## 已知边界（跑之前就写着的）

- **协作式取消只做了一半**（M8 的已知边界，M10 补完）：Ctrl-C 之后 `sleep.py` 停下来靠的是外层 asyncio 取消那条调用加 `bash` 执行段收进程树——工具体不观察取消信号。
- **硬杀的形状不在人手验收里**：`tool/call` 已落、`tool/result` 没落、进程被硬收掉——那个形状由 seam ⑥ 的 `test_a_hard_kill_leaves_no_half_written_line` 与 `test_a_hard_killed_log_replays_without_appending` 判。
- **会话续跑不在 M8**：半截日志能被折叠配平，但 `minihns` 没有从它续跑的入口（M6 / M7）。

## 取证命令

```
$log = Get-ChildItem .tmp/m8-manual/sessions/*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $log -Encoding UTF8 | ForEach-Object { $e = $_ | ConvertFrom-Json; '{0,18}  {1}  {2}' -f $e.type, $e.payload.tool_call_id, $e.payload.outcome }
```

按批次看声明顺序与落盘顺序（含 `ts` 到毫秒）：`.tmp/m8-manual-order.py`，跑 `uv run python .tmp/m8-manual-order.py`。
