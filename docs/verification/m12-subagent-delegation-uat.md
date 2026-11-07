# M12 subagent UAT

**状态**：等人跑（agent 不代跑 tty 场次，ADR-0025）。

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

看：子会话的写请求得到 `UNAVAILABLE`（子日志里是 `DENIED_BY_APPROVAL` + `error/fence` 的 `APPROVAL_UNAVAILABLE`）；**父日志里那一条 `subagent` 的 `tool/result` 也是 `DENIED_BY_APPROVAL`**（内容带围栏码与子会话最后的文本），`note.md` 没有被写出来。父会话自己的写请求仍会像以前一样问你。

### S5 · 取消

```bash
minihns chat --provider deepseek --yes
> 派一个 subagent 跑一条 30 秒的慢命令
```

子代理跑起来之后按 Ctrl-C。

看：父回到提示符、退出码仍是 0；子日志最后是 `session/end(ABORTED)`；没有残留的 `sleep` 进程。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | 单次委派 | 父只拿结果 | | | |
| S2 | 并行 | 真并发 | | | |
| S3 | 深度 | `DEPTH_EXCEEDED` | | | |
| S4 | 子审批 | `APPROVAL_UNAVAILABLE` | | | |
| S5 | 父取消 | 子 `ABORTED`、无孤儿 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过：
