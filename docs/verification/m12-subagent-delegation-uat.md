# M12 subagent UAT

**状态**：S1–S5 已由人跑（2026-11-09）。S5 第二轮暴露并修复了一个真缺陷（Ctrl-C 延迟 30 s），修复后第三轮通过。

## 跑前准备

```bash
mkdir -p /tmp/m12-uat && cd /tmp/m12-uat
printf '目标：把这条写进 note.md\n' > inbox.md
printf '第二份材料\n' > second.md
export DEEPSEEK_API_KEY=...        # 真端点；密钥只走环境变量
```

会话日志落在 `./sessions/`。父与子的日志是两个文件，父文件名就是 `minihns` 打出来的会话 id。

## 场次

### S1 · 一次委派（只读任务）

```bash
minihns run --provider deepseek -p "用 subagent 让子会话读 inbox.md 并总结成一句话" --yes
```

看：父回答里有子会话的总结；父日志只有一条 `subagent` 的 `tool/call` + 一条 `tool/result`，子日志（另一个文件）里才有子会话的 `model/*` 与工具过程。

### S2 · 并行

```bash
minihns run --provider deepseek -p "同一轮里派两个 subagent：一个读 inbox.md，一个读 second.md，各自总结" --yes
```

看：两条结果几乎同时回来（体感明显快于先后做）；父日志两条 `tool/result`。模型不一定把它们放在同一批——放不到同一批时记「别扭」，不算不通过。

### S3 · 深度

```bash
minihns run --provider deepseek -p "派一个 subagent，让它自己再派一个 subagent 去读 inbox.md" --yes
```

看：子会话那层的 `subagent` 结果是 `DEPTH_EXCEEDED`，父回合照常结束。

**容量一半不可观察**：工具并发上限与 `maxActiveSubagents` 都是 8，同一批 9 个 `subagent` 时第 9 个会排队、等前 8 个之一完成再跑，撞不到额度（design D8）。`ACTIVATION_LIMIT_REACHED` 由判据（预置计数）覆盖，不在 UAT 里造。

### S4 · 子会话问人不可用

不设 `--yes`（ask 模式），让子代理去写文件：

```bash
minihns run --provider deepseek -p "派一个 subagent 把 inbox.md 的内容写进 note.md"
```

看：子会话的写请求得到 `UNAVAILABLE`（子日志里是 `DENIED_BY_APPROVAL` + `error/fence` 的 `APPROVAL_UNAVAILABLE`）；**父日志里那一条 `subagent` 的 `tool/result` 也是 `DENIED_BY_APPROVAL`**（内容带围栏码与子会话最后的文本）。父会话自己接着写时会照常问你——批准了它就是父写的，不是子会话写的。

### S5 · 取消

```bash
uv run minihns chat --provider deepseek --workspace /tmp/m12-uat --session-dir /tmp/m12-uat/s5 --yes
> 派一个 subagent 跑一条 30 秒的慢命令（sleep 30），等它跑完再回来
```

**子代理真的跑起来之后**按 Ctrl-C（看 `[tool] subagent` 那一行之后、结果回来之前）。

看：父回到提示符、退出码仍是 0；子日志最后是 `session/end(ABORTED)`；没有残留的 `sleep` 进程。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | 单次委派 | 父只拿结果 | 父先 `glob` 再 `subagent`；子会话 `entry=subagent` / `depth=1` / `delegated=True`，只做了一次 `read`；父拿到一句话总结（`bd4f8a7e…`） | 通过 | |
| S2 | 并行 | 真并发 | 同一批两条 `subagent`；两个子会话各读一个文件；两条结果按完成顺序回来（`second.md` 先于 `inbox.md`）（`0beb6fb0…`） | 通过 | 结果顺序与声明顺序不同，读日志时要习惯 |
| S3 | 深度 | `DEPTH_EXCEEDED` | 子会话里那次 `subagent` 是 `DEPTH_EXCEEDED`，子会话把这句限制写进最终回复，父回合照常继续（`6a6dd24d…`） | 通过 | |
| S4 | 子审批 | `APPROVAL_UNAVAILABLE` | 子会话的 `bash` 与 `write` 都被拒（`APPROVAL_UNAVAILABLE`），父那两条 `tool/result` 都是 `DENIED_BY_APPROVAL`；父随后**自己** `write`，走人工批准后写成 `note.md`（`1ec75393…`） | 通过 | 子会话被拒两次后，父才换自己上；「我让子代理做，最后还是我批」的体感 |
| S5 | 父取消 | 子 `ABORTED`、无孤儿 | 第一轮子会话只做了一次 `read` 就收尾，Ctrl-C 没落在运行中（`837270e1…`）；第二轮 Ctrl-C 后 bash 跑满 **30.04 s** 才 `TOOL_CANCELLED`（缺陷，已修）；第三轮修复后：`^C` 当场 `TOOL_CANCELLED`，子会话 `session/end(ABORTED)`（`2f91e783…` / 子 `cbe8d7ed…`），上一轮 `pgrep -fl sleep` 为空 | 通过（修复后） | Ctrl-C 延迟是缺陷，不是体感 |

**至少一条「用起来别扭」**：S4 里子会话被拒两次后父才换自己上——「我让子代理做，最后还是我批」；S2 两条结果按完成顺序回来，与声明顺序不同，读日志时要习惯。

**结论**：通过（S1–S5；S5 的 Ctrl-C 延迟作为缺陷修复后复验）。

## 发现并修复的缺陷（S5 第二轮）

**症状**：Ctrl-C 之后 `[tool] subagent -> TOOL_CANCELLED` 要等约 30 秒才出现（正好是子会话 `bash` 的 `sleep 30`）。

**根因**：chat 的 SIGINT 处理器直接调 `signals.active.set()`。`Event.set()` 只把回调排进 `_ready`，**不写循环的自管道**；事件循环此时睡在 selector 里（等 bash 的管道），于是要等管道有动静才醒——bash 退出时才处理取消。

**实验**（同机、同循环，信号由线程在 1 s 时发出，循环正 await 一个 4 s 的子进程）：

| 处理器写法 | 事件被观察到的时刻 |
|---|---|
| `Event.set()` 直调 | 4.01 s（子进程结束） |
| `loop.call_soon_threadsafe(event.set)` | 1.01 s |

**修复**：`_ChatSignals` 带循环句柄，处理器改走 `loop.call_soon_threadsafe(signals.active.set)`；与 `_await_session`（run/serve）和 host 的 `_stop_handler` 同一条规矩。回归用例：`test_the_chat_handler_wakes_the_loop_instead_of_only_queueing`（锁住「必须调度、不直接置位」），CLI 黑盒的 `test_sigint_mid_segment_cancels_the_segment_not_the_session` 从「全量里时红时绿」变为稳定通过。

