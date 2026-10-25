# UAT 手册：`add-platform-facts-to-protected-header`

**这是 propose 阶段立的骨架**（ADR-0025）。场次由人跑，观察表由人填；**那张表没填完这个 change 不得归档、不得合入 `main`**。tty 场次 agent 不得代跑——agent 只能核对日志与 `context/assembled` 那一半。

跑之前先取密钥（本机实测可用的那条）：

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
```

> **路径坑（2026-10-25 人踩过）**：`chat` 与 `run` 不带 `--session-dir` 时，日志落在**当前工作目录下的 `sessions/`**，不是 `.tmp\uat-c\sessions`。所以拿那一行的 id 去 `replay <id> --session-dir .tmp\uat-c\sessions` 会得到 `SESSION_NOT_FOUND`——不是日志没写，是找错了目录。要么 replay 时不带 `--session-dir`（默认就是 `./sessions`），要么跑命令时也带上同一个 `--session-dir`。

## U1 拿它办一件真事（Windows 工作区）

```powershell
uv run minihns chat --workspace <一个真实工作区> --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --max-turns 8
```

进去打：`看看这个目录里有什么，然后读其中一个文件的前二十行`。

| 要观察的 | 你看到的 |
|---|---|
| 屏幕上还有没有那段试错正文（「`ls` 似乎不可用」「这是一台 Windows shell（cmd）环境」） | **没有**。一次都没出现；它没跑过 `ls`（日志核对：13 次工具调用里没有 `ls`） |
| 它第一次用哪个工具问「目录里有什么」：`glob` 还是 `bash` 里的 `ls` / `dir` | **`glob`**，参数 `{"pattern": "*"}`（日志核对：第一个 `tool/call` 就是它） |
| 它有没有临时写一段脚本去做本该由 `glob` / `grep` / `read` 干的活 | 没有写脚本文件；但为了拿文件大小，它连跑了几条临时的 shell / PowerShell 单行命令（`dir`、`for %f … find /c /v ""`、`certutil -encodehex`、`powershell -Command …`）。它自己承认这「等于把被禁的等价命令又请了回来」 |
| 它有没有在第一次失败之后就换到 `dir` / `Get-ChildItem` 这类形态 | 不适用——`ls` 从没被用过，第一次 `bash` 就是 `dir`（成功）。倒是 `for %f in (…)` 那条因为 `%f` 没展开而失败，它没有重试同一形态，改去查代码页 |
| 这一场烧了几个回合（对比 2026-10-24 那一场的回合数） | 13 个回合（日志核对：`session/end` turns=13；中途有一段的收尾理由是 `MAX_TURNS`，之后继续到正常收尾） |
| 启动时 stderr 上那一行 session id | `会话 b245f717bf6344869d964d975e6fc39b`（日志在 `S:\Develop\mini-harness\sessions\`） |

**真事是什么**：在 `S:\Develop\mini-harness\.tmp\reacc\ws` 这个真实工作区里问「目录里有什么、读一个文件的前二十行」，并顺手判断各文件大小与行数。

## U1b 直接问它「这个平台的命令怎么用」

同一场里打：`你打算怎么列这个目录里的文件？为什么用这个工具？`

| 要观察的 | 你看到的 |
|---|---|
| 它有没有引用头部里那句本平台的命令建议（提到 `dir` 或 `findstr`） | 引用了，而且更细：它说「`bash` 走 `cmd.exe /c`」，并指出 `dir` 的输出里目录中文名与表头是乱码（OEM 代码页与 harness 的 UTF-8 解码不一致） |
| 它有没有说「列目录该用 `glob`」这类原生工具的话 | **逐字引用了工具描述**：「系统给我的工具说明里明确规定：列目录用 `glob`，不要用 `bash` 里的 `ls` 或 `dir` 这类等价命令，也不该临时写脚本」 |
| 它有没有把 `ls` 当成可用命令 | 没有 |
| 额外（它自己指出的） | 它说上一轮「用 `glob` 列了目录、又用 `bash dir` 补文件大小」破坏了自己的约定，并提出「应该让工具返回值本身承担字节数」——**这是头部那句「列目录用 dir」与工具描述那句「列目录用 glob」在同一次装配里竞争的直接证据** |

## U2 乱码仍然会发生——看它怎么对待

同一场里打：`用 bash 跑 dir，然后把输出里你看不懂的地方告诉我`。

| 要观察的 | 你看到的 |
|---|---|
| 输出里有没有 U+FFFD（替换字符） | 有。`chcp` 的输出是 `�����ҳ: 936`（只有 `936` 能读）；之前的 `dir` 输出里 `S �еľ��� S`、`���ļ�` 也都是替换字符 |
| 它有没有把乱码当成「工具坏了」去重试 | 没有。它把乱码当**编码问题**处理：`chcp` 查代码页 → `certutil -encodehex` 抓原始字节 → PowerShell 按 936 解码验证 → 最后给出结论「代码页是 936（GBK）」 |
| 它有没有引用那句说明（命令输出按 UTF-8 解码）来解释 | 有，而且是逐字的意思：「`cmd.exe` 的 OEM 代码页和 harness 的 UTF-8 解码不一致」 |
| 它最后有没有把能读出来的部分读给你 | 有：从乱码里读出 `936`，并用 `Write-Host $e.GetString($b)` 按 GBK 解码验证了一遍 |
| 代价 | 这一场把回合烧到了 `MAX_TURNS`（日志核对：那一段的收尾理由是 `MAX_TURNS`）——**说明「查清楚乱码」很贵，而一句说明只能让它知道方向、不能让它免费收尾** |

## U3 旧日志照旧可重放

拿一条**这条事实存在之前**的 session id（例如 `b861ceee88ad48be904ac3c9233d5e47`）跑：

```powershell
uv run minihns replay b861ceee88ad48be904ac3c9233d5e47 --session-dir .tmp\uat-c\sessions
```

| 要观察的 | 你看到的 |
|---|---|
| 每个装配点是不是 `verified … OK` | 是，6 条（`verified seq=4/13/22/31/40/51: OK`）——**我替你跑的**（2026-10-25，只读日志，不代跑 tty 场次） |
| 有没有 `REPLAY_MISMATCH` | 没有 |
| 退出码 | 0 |
| 顺带（新日志也核了） | `b245f717…` 13 个装配点、`7d71754f…` 与 `d329a3e6…` 各 1 个，全部 `verified seq=…: OK`、退出码 0——带 `platform` 的新日志逐点重放同样一致 |

## U4 追加文本仍然排在最后

```powershell
uv run minihns run -p "说一句话" --append-system-prompt "回答只用中文" --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY
```

然后从那份日志的第一条 `context/assembled` 里读头部（agent 可以代读这一半）。

| 要观察的 | 你看到的 |
|---|---|
| 头部第一条是不是内置系统提示 | 是（两场 `7d71754f…` 与 `d329a3e6…` 都是） |
| 运行环境块在工具块之后、追加文本之前吗 | 是。末两段逐字是：运行环境那一块 → 空行 → `回答只用中文`（日志核对） |
| 追加文本还在头部最后吗 | 在，仍是最后一段 |
| 回答是不是只用中文 | 是：`今天也值得认真对待。` / `今天想先听你聊聊最近在忙什么，再决定我们一起做哪件事。`（日志里两条 `model/response`） |

## 2026-10-25 这一轮：填到哪一格

五场都跑了（U1 / U1b / U2 是同一场 `b245f717…`；U3 是旧的 `b861ceee…` 加三条新日志；U4 是 `7d71754f…` 与 `d329a3e6…`）。**表按「人观察 + 日志核对」两半填完**，没有空格子。

三条值得记下来的观察：

1. **描述里那句引导真的被模型引用了**——U1b 里它逐字复述「列目录用 `glob`」，并且第一次就用了 `glob`。ADR-0030 的引导是可观察的。
2. **头部那句「列目录用 dir」与描述那句「列目录用 glob」会竞争**——它先用 `glob`、再用 `bash dir` 补大小，然后自己指出这是「把被禁的等价命令又请了回来」。这不是失败，是同一件事有两处说法。**要不要把头部那句改成「列目录用 `glob`；真要跑 shell 命令时这个平台用 `dir`」**，见 `docs/verification/add-platform-facts-to-protected-header-real-endpoint.md` 的三条判读。
3. **乱码能解释、但很贵**——模型完全按设计的方向理解了乱码（代码页 936，不是工具坏了），代价是那一场烧到 `MAX_TURNS`。要把「查清乱码」变便宜，得在工具结果里给出可读的形状，不是在头部再加一句话。

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「这个 change 的 UAT 跑完了」。我会按填回来的东西判 UAT 那一半；不符合的项照 ADR-0025 立成新的修复 change。
