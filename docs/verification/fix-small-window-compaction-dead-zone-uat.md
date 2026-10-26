# `fix-small-window-compaction-dead-zone` 的 UAT 手册（人跑）

第五道门禁（ADR-0025）。三场，每场一段可粘贴的命令 + 一张观察表。**这张表没填完，本 change 不得归档、不得合入 `main`。**

准备（一次）：

```powershell
cd S:\Develop\mini-harness
$WS = "S:\Develop\mini-harness\.tmp\reacc\ws"      # 换成你自己的真实工作区更好
$env:MINIHNS_STRATA_KEY = [Environment]::GetEnvironmentVariable("MINIHNS_STRATA_KEY","User")
$EP = @("--provider","openai","--base-url","http://127.0.0.1:8300/v1","--model","qwen3.8-flash-next-iq3_xxs","--api-key-env","MINIHNS_STRATA_KEY")
```

## U1 · 小窗口里能对话（这一场就是修复本身）

修复前：`--window 70000 --reserve 100` 读一份大文件，第一次装配就死在 4364 token，退出码 4。修复后：应该能接着对话。

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat2\sessions @EP --window 70000 --reserve 100 --max-turns 10 --sandbox workspace-write --yes
```

进去之后：让它读 `big.md`（245,988 字符 / 2000 行，`read` 一次全回）。

期望的形状（不是判据，只是让你知道看没看对）：压力预算 69900、触发线 4364、保留预算 11200；读完之后预算读数约 6 万，**在压力预算之内**，所以会话不该死；读数越触发线且那一段装不进保留尾部，所以 `[遮蔽]` 那一行**该出现**。

| 要观察的 | 你看到的 |
|---|---|
| 读完大文件之后会话还在（没有 `[段] CONTEXT_WINDOW_EXCEEDED`） | **是**，会话还在（session `270cd4fe9d014266b18f22fcfa17019a`） |
| 你接着问的第二句它答得上来 | **答上来了**：「`big.md` 是 2000 行、CRLF 换行、首行带 BOM 的合成清单…」。第一问那一段在 10 个回合用完时收尾是 `MAX_TURNS`（模型一直在自查，不是溢出） |
| 屏幕上有没有 `[遮蔽]` 那一行、出现几次 | **两次**：`[遮蔽] 折掉 seq 1 至 45：tokens 17950 降至 329`、`[遮蔽] 折掉 seq 51 至 61：tokens 47975 降至 542` |
| 退出码（提示符上 Ctrl-C 后） | 这一跑用管道 EOF 收尾，退出码 **0**（没有 tty Ctrl-C 那一半） |

## U2 · 真溢出仍然看得见那一行

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat2\sessions @EP --window 40000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读 `huge.md`（405,949 字符 / 3300 行；`read` 默认只回 2000 行，进上下文的是约 246,000 个字符 ≈ 61,500 个估算 token）。

期望的形状：压力预算 39900、触发线 0；那一段工具往返本身就装不进压力预算，所以**不发摘要请求**，屏幕上那句 `detail` 该以「可遮蔽的那一段本身就装不下」开头、三个数都在。

| 要观察的 | 你看到的 |
|---|---|
| stderr 那一行 `[段] CONTEXT_WINDOW_EXCEEDED` | 有，但屏幕上那一行是 `[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED`——**只重复了失败码，没带 detail**（这条分支早于 `fix-chat-screen-feedback` 那版段收尾措辞） |
| 紧跟的那句 `detail` 里**三个数都在**（读数 / 压力预算 / 触发线） | 屏幕上看不到；**日志里两个数段落都在**：`error/context` 的 detail 是「可遮蔽的那一段本身就装不下，预算读数 63400 超过压力预算 39900（触发线 0）」（两段各一条，第二段读数 63403） |
| 那句 `detail` 的开头是哪一种措辞 | 「可遮蔽的那一段本身就装不下」——正是小窗口下预期的那一种 |
| 会话不崩，你还能接着问一句 | 会话没崩、退出码 0；但第二段同样溢出（`huge` 的读还压在上下文里），所以第二问没有得到回答——**如实记成「接着问得到的是又一次溢出，不是答案」** |
| 退出后 `minihns replay <session id> --session-dir .tmp\uat2\sessions` 退出码 | **0**，1 个装配点 `verified seq=4: OK`，没有 `REPLAY_MISMATCH` |

## U3 · 压缩发生了但仍不够（这条分支第一次可达）

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat2\sessions @EP --window 70000 --reserve 100 --max-turns 12 --sandbox workspace-write --yes
```

让它连读三份大文件（`big.md` 两次不同区段 + `huge.md` 一段），逼压缩发生多次。

| 要观察的 | 你看到的 |
|---|---|
| `[遮蔽]` 那一行出现几次、每行的 tokens 前后 | 日志里 **2 条 `compaction/summary`**：`shadowed 1–10` / 51509 → 192，`shadowed 16–118` / 17090 → 511（stderr 上只截到第二条，第一条在第一段里） |
| 有没有出现「压缩之后预算读数 … 仍超过压力预算」 | **没有**。这一跑没有 `error/*`，也就没有那条措辞 |
| 撞到了 / 没撞到（**如实写，没撞到也是结论**） | **没撞到**：第一次问答在 s1 正常收尾（`MODEL_COMPLETED`），第二问在 s2 烧完 12 个回合（`MAX_TURNS`），两段都没有溢出。会话 `5ed742e1bc96420d9a6c5460fa65f5ee`，退出码 **0**，`replay` 23 个装配点全 `verified`、无 `REPLAY_MISMATCH` |

## 2026-10-26 这一轮：用 DeepSeek 端点代跑（人授权「用 deepseek 的端点测试是一样的，帮我测了吧」）

三场都跑了，**端点换成 `https://api.deepseek.com/v1` + `deepseek-flash`**（手册原写的是本机 studio 的 `127.0.0.1:8300`，那一跑端口没有在监听）。三场都用管道喂 stdin、读到 EOF 收尾，所以「提示符上 Ctrl-C 的退出码」这一格没有；其余各格按上面三张表填。日志在 `.tmp\uat2\sessions`。

会话与结论：

| 场 | 会话 | 结果 | 退出码 | replay |
|---|---|---|---|---|
| U1 | `270cd4fe9d014266b18f22fcfa17019a` | 读 `big.md` 之后**会话还在**、第二问答得上来；`[遮蔽]` 两次 | 0 | 11 个装配点全 OK |
| U2 | `006a036085e045cc8669f4d0ef79ad65` | 真溢出：`detail` 三个数都在日志里；第二段又溢出 | 0 | 1 个装配点 OK |
| U3 | `5ed742e1bc96420d9a6c5460fa65f5ee` | 压缩两次、没有溢出；第二问烧完 12 回合 | 0 | 23 个装配点全 OK |

三条要留意的观察（都不改本 change 的代码）：

1. **修复本身成立**：`--window 70000 --reserve 100` 下读 248 KB 的 `big.md`，两段都活下来、第二句也答上了。这就是本 change 要修的那个死区。
2. **屏幕上那一行在这条分支上不含 `detail`**：U2 印的是 `[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED`（失败码重复），三个数只进了日志。原因是这条分支早于 `fix-chat-screen-feedback` 那版段收尾措辞。**rebase 到当前 `main` 之后已复跑确认**（2026-10-26，会话 `9d5f36ffc174477391732384c7b8f2a7`）：那一行现在是 `[段] CONTEXT_WINDOW_EXCEEDED：可遮蔽的那一段本身就装不下，预算读数 63411 超过压力预算 39900（触发线 0）`——三个数都在屏幕上，这一格转成通过。
3. **U3 的「压缩之后仍超过压力预算」这一种措辞没有可达**：三次跑里压缩之后都降到了几百 token，没有一条落到「仍超过压力预算」。如实记成「没撞到」——这不是判据失败，是这一组窗口 / 文件组合下那条路没被走到。

## 填完之后

在对话里说一句「这个 change 的 UAT 跑完了」，我按填回来的东西判第三半，并把不符合的项立成修复 change。
