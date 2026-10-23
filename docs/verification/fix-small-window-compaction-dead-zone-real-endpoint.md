# 真实端点验收：`fix-small-window-compaction-dead-zone`

完成判据的第二半（ADR-0024）。端点是本机 Strata：`http://127.0.0.1:8300/v1`、模型
`qwen3.8-flash-next-iq3_xxs`、密钥走 `--api-key-env MINIHNS_STRATA_KEY`。工作区
`.tmp/reacc/ws`，日志在 `.tmp/reacc/sessions/`。跑的时间：2026-10-23。

## 6.1 死区窗口不再以退出码 4 结束

`minihns run -p "用 read 工具读 dead.md，然后只回一句「读完了」。" --window 70000 --reserve 100`
（`dead.md` 36000 个字符，一行）。会话 `00dfb231b9eb445e95d01be466d1d02a`。

| 量 | 值 |
| --- | --- |
| 触发线 | 4364 |
| 保留预算 | 11200 |
| 压力预算 | 69900 |
| 估算 token（折叠表层） | 9058 |
| 预算读数 | 27444（端点回报的 `input_tokens`） |
| 退出码 | 0 |

日志里 `compaction/summary` 零条、`error/context` 零条，`session/end` 的 `stop_reason` 是
`MODEL_COMPLETED`。读数 27444 超过触发线 4364、整段对话体都装得进保留尾部 11200 于是无可遮蔽——
这正是 M5 真实验收里 session `70fa85600d484109b2f266506ee24c42`（读数 5933）当时以退出码 4 收尾的那个形状。
**修完它跑完了。**

顺带一条硬事实：估算 9058 与端点回报 27444 差三倍。`CHARS_PER_TOKEN = 4` 对中文严重低估——
36000 个字符端点算成约 27000 个 token，实测约 **1.3 个字符一个 token**。预算读数取
`max(估算, 回报)`，所以真端点上主导的是回报那一半。

## 6.1 附：压缩在真端点上确实发生

同一端点读 `big.md`（245988 个字符、2000 行）。会话 `4ef8d41b84964be68c6da88b4c8fef47`，
`--window 70000 --reserve 100`，退出码 0。`compaction/summary` 一条：`shadowed_range` seq 1 至 7、
`tokens_before` 64276、`tokens_after` 106；摘要请求回报 `input_tokens` 101045。压缩之后照常装配、
照常调模型、正常收尾。

## 6.2 真溢出：退出码 4，`detail` 三个数

`minihns run -p "用 read 工具读 big.md …" --window 60000 --reserve 100`。会话
`bfe6d7ae75eb422fa370cf088b04c304`。

```
CONTEXT_WINDOW_EXCEEDED: 可遮蔽的那一段本身就装不下，预算读数 64276 超过压力预算 59900（触发线 0）
```

退出码 4；日志里 `error/context` 的 `payload.code` 是 `CONTEXT_WINDOW_EXCEEDED`，`detail` 三个数齐；
没有 `purpose: compaction` 的 `model/request`（那一段裁到只剩一组往返仍装不下，于是请求根本没发出去）。

**与计划不同的一处**：tasks 6.2 写的是 `--window 100000 --reserve 100` 读 `huge.md`。它撞不到溢出——
`read` 工具默认只回 2000 行，`huge.md` 有 3300 行，所以进上下文的只有约 246000 个字符
（估算 61500 个 token），比压力预算 99900 小得多。换成 `--window 60000` 才成立。

## 6.3 「压缩发生了但仍不够」：撞不到，原因写清楚

试过 `--window 4000 --reserve 100` 加 15400 个字符的 `--append-system-prompt` 读 `small4.md`
（会话 `474d8e4c59b64f8ea97304cdfc0fba73`）：

```
CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 8700 已超过压力预算 3900（触发线 0）
```

溢出发生在**第一次装配**，走的是「无可遮蔽」那条，不是「压缩之后」。两条算术原因：

1. 真端点回报的 `input_tokens` 主导读数。受保护的头部一大，第一次装配的读数（8700）就已经超过
   压力预算（3900），此时日志里除了受保护事件什么都没有，`shadowed_range` 给不出范围。
   要让第一次装配不溢出，头部必须小到回报值不超过压力预算；按实测 1.3 字符/token，
   这比按估算能塞进去的头部小得多。
2. 要撞「压缩之后」，摘要本身要超过压力预算的约八成（`0.84 × W`）。真模型写摘要恰恰是把它缩短，
   6.1 附那一条实测 `tokens_after` 106。真端点上这条字面分支走不到。

结论：这条分支由 mock 判据 `test_one_compaction_then_overflow_when_the_context_still_does_not_fit`
覆盖（300000 个字符的摘要），真端点这一半**撞不到**，不是漏跑。

## 附带发现：`minihns.exe` 那个入口在超长参数下崩

`minihns run --append-system-prompt <24000 个字符>` 与 `minihns run -p <24000 个字符>` 都以
`0xC0000005`（访问违例）结束，退出码 `-1073741819`，**没有任何输出、没有 `session/start`**。
16000 个字符正常。同一份参数换成 `.venv/Scripts/python.exe -m mini_harness.cli.main …` 一切正常
（干净地报 `INVALID_ARGUMENT`）。所以崩的是 venv 的 console-script 启动器，不是 mini-harness 的代码。

对 UAT 的影响：溢出场次不要用巨型 `-p`，改用「模型读一个大文件」把上下文撑大——
`docs/verification/fix-small-window-compaction-dead-zone-uat.md` 里的场次已经是这个形状。
