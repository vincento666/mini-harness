# `fix-compaction-and-context-overflow` 的真实端点实测（task 5.4 与 5.5）

**状态：agent 这一半跑完（2026-10-22 23:25–23:32，本机 Strata 端点，两次 `minihns chat`）。这一半是完成判据，不是 CI：ADR-0022 写明「模型相关功能的完成判据含一次真实端点实测，CI 的 mock 判据不算验收」。** 剩下的 tty 那一半（真终端里的 Ctrl-C）仍待人跑，沿用 M3 / M6 的边界。

跑法：`minihns chat --provider openai`，端点 `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`，密钥走环境变量名 `MINIHNS_STRATA_KEY`（值不落任何文件）。工作区是 `.tmp/realchat/`（现场写的 `big.md`：600 行、每行 4 位行号加 90 个 ASCII 字符，共 58203 字符）。输入从管道喂进去（stdin 非 tty），stdout 与 stderr 各自重定向到文件后再读——PowerShell 把子进程的 stderr 包成 ErrorRecord 会把同一行显示两遍，这一层噪音不能当证据。

## 场景 A：小窗口里压缩根本不可能发生（session `608ef8e48b214e2892da23456da267dc`）

`--window 70000 --reserve 100`。两条输入：第一条要模型 `read big.md` 全文，第二条要它读前 30 行。退出码 0，日志 52 条。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 段失败在屏幕上看得见 | stderr 有一行 | ✓ `[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED` |
| 溢出塌成回合级收尾、会话继续 | `error/context` + `turn/end` + `segment/end`，之后还有第二个段 | ✓ seq 44 / 45 / 46，段 `s2`；`session/end` 是 `MODEL_COMPLETED` |
| 压缩有没有发生 | —— | **没有**。`error/context` 的 detail 是「无可遮蔽的内容，预算读数 4393 已超过触发线 4364」 |
| stdout 有没有回复 | 只有回复正文与提示符 | ✓ 三行 `> `，一个字的回复都没有 |

**这一条是「chat 对不了话」的第一种形状**：窗口 70000、保留 100 时触发线是 4364、保留线是 11200。预算读数刚过触发线（4393）时整份对话还不到保留线，`shadowed_range` 返回 `None`——压缩不可能发生，直接塌成溢出。而端点自己的窗口是 196608 token，4393 估算 token 的请求离窗口远得很。

## 场景 B：窗口调到真会压缩的量级（session `d31a7790e92c49fcb47d9a5dc8b25636`）

`--window 80000 --reserve 100`（触发线 14363、保留线 12800，触发线在保留线之上才可能压缩）。两条输入：第一条要模型把 `big.md` 分四次读完、每次只回一个「好」字；第二条要它一句话说明 `big.md` 是什么。退出码 0，日志 52 条。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 压缩真的发生、摘要真的来自真端点 | `model/request{purpose: compaction}` 后跟一条 `compaction/summary` | ✓ 两次：seq 11→13（回合 `t2`）、seq 30→32（回合 `t4`），都在段 `s1` |
| 遮蔽反馈在 stderr 看得见 | 一行含 `shadowed_range` 两端、`tokens_before`、`tokens_after` | ✓ 原文两行：`[遮蔽] 折掉 seq 1 至 8：tokens 15196 降至 74` 与 `[遮蔽] 折掉 seq 14 至 18：tokens 15364 降至 13239` |
| 遮蔽反馈不是 stdout、不是日志 | stdout 里没有、日志原文里没有 | ✓ stdout 只有 `> ` 与模型回复正文；日志里 `[遮蔽]` 一个字符都没有 |
| 摘要回复不打到 stdout | 带 `purpose` 的那次不投影 | ✓ stdout 里没有任何摘要正文 |
| 会话继续接受下一条输入 | 第二个段开出来 | ✓ 段 `s2` 存在（它的收尾见下） |
| 有没有无声死掉的段 | 没有 | **有**：段 `s2` 以 `FENCE_DENIED` 收尾（模型调 `bash`，stdin 非 tty → 审批 `UNAVAILABLE` → `error/fence{APPROVAL_UNAVAILABLE}`），屏幕上那一行没有——`FENCE_DENIED` 不在打那一行的三种理由里 |

**修好之前跑同一场景，遮蔽反馈那一行打了两遍**（同一条 `compaction/summary` 报两次）。mock 判据抓不到：那些判据每段只喂一条输入，第二次不报也看不出来。真端点这一跑把它暴露了，实现里补的是「只报 `through` 之后新写出的记录」，判据里补的是第二条输入。

## 估算与真端点的三个数（task 5.5）

同一份日志，每个回合的 `context/assembled` 按 `estimate_tokens` 算一遍，对 `model/response` 里 provider 回报的 `input_tokens`（压缩那次不算）：

| 回合 | 估算 | provider 回报 | 比值 | 正文字符数 |
|---|---|---|---|---|
| `t1` | 49 | 1031 | 21.04 | 195 |
| `t2` | 74 | 1086 | 14.68 | 295 |
| `t3` | 10227 | 13172 | 1.29 | 40795 |
| `t4` | 5278 | 7397 | 1.40 | 20859 |
| `t5` | 5284 | 7421 | 1.40 | 20880 |

**别扭在哪：**

1. **估算里没有一个字节的固定开销。** 正文 195 字符的请求 provider 报 1031 token——工具 schema 与 chat 模板那一份（约 980 token）估算里不存在。窗口越小、对话越短，这一项占比越大，而触发线恰恰是在对话短的时候先动。
2. **正文那一份估算是偏小的，但不是 M5 量到的那个倍数。** 这一跑正文部分是 1.29 至 1.40 倍（内容是重复 ASCII `abcdefghij`，tokenize 得比自然语言省）；M5 那次是 2.24 倍。倍数随内容变，所以「按倍数校准」这条路不成立，能成立的只有「把 provider 回报的 `input_tokens` 回灌成下一回合的读数」。
3. **小窗口里触发线在保留线之下，压缩不可能发生**（场景 A）。`trigger_line = min(W*4//5, W - reserve - 65536)` 与 `retain_line = W*16//100`：`W - reserve - 65536 < W*16/100` 时两者反号，`W=70000 / reserve=100` 就是这种窗口。这不是这次修的那四条之一，是这一跑新撞出来的。
4. **第二次压缩几乎不省**：`15364 → 13239`，省 14%。保留线 12800 逼着尾部几乎全留，能折掉的只剩头部那一小截——而头部恰恰是最旧、最该进摘要的内容（ADR-0002 第 65 条记的就是这个代价）。
5. 小观察：正文为空的回复也在 stdout 上打一个空行（`t2` / `t3` 是带工具调用的空正文）。不影响判据，记在这儿。

## 待人跑的那一半

真终端（tty）里的 `minihns chat`：提示符上 Ctrl-C、段进行中 Ctrl-C、审批问人。命令与 M6 那份末尾相同，加上这一跑的窗口参数：

```powershell
$env:MINIHNS_STRATA_KEY = [Environment]::GetEnvironmentVariable("MINIHNS_STRATA_KEY","User")
uv run minihns chat --provider openai --base-url http://127.0.0.1:8300/v1 `
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY `
  --window 80000 --reserve 100
```

要看的是：屏幕上 `[遮蔽] ...` 那一行出现在什么位置（是不是紧跟着就出现、有没有把回复挤开），以及段以 `FENCE_DENIED` 收尾时屏幕上到底有没有东西。
