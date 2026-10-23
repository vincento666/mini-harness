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

进去之后：让它读 `big.md`（247,988 字符），然后接着问两句关于它的内容。

| 要观察的 | 你看到的 |
|---|---|
| 读完大文件之后会话还在（没有 `[段] CONTEXT_WINDOW_EXCEEDED`） | |
| 你接着问的第二句它答得上来 | |
| 屏幕上有没有 `[遮蔽]` 那一行、出现几次 | |
| 退出码（提示符上 Ctrl-C 后） | `$LASTEXITCODE` = |

## U2 · 真溢出仍然看得见那一行

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat2\sessions @EP --window 40000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读 `huge.md`（409,248 字符）。

| 要观察的 | 你看到的 |
|---|---|
| stderr 那一行 `[段] CONTEXT_WINDOW_EXCEEDED` | |
| 紧跟的那句 `detail` 里**三个数都在**（读数 / 压力预算 / 触发线） | |
| 会话不崩，你还能接着问一句 | |
| 退出后 `minihns replay <session id> --session-dir .tmp\uat2\sessions` 退出码 | |

## U3 · 压缩发生了但仍不够（这条分支第一次可达）

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat2\sessions @EP --window 70000 --reserve 100 --max-turns 12 --sandbox workspace-write --yes
```

让它连读三份大文件（`big.md` 两次不同区段 + `huge.md` 一段），逼压缩发生多次。

| 要观察的 | 你看到的 |
|---|---|
| `[遮蔽]` 那一行出现几次、每行的 tokens 前后 | |
| 有没有出现「压缩之后预算读数 … 仍超过压力预算」 | |
| 撞到了 / 没撞到（**如实写，没撞到也是结论**） | |

## 填完之后

在对话里说一句「这个 change 的 UAT 跑完了」，我按填回来的东西判第三半，并把不符合的项立成修复 change。
