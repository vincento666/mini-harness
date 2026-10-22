# M6 人手验收（`m6-chat-repl`）

**状态：agent 这一半跑完（2026-10-21 22:36–22:52，真 PowerShell 终端，四次 `chat` run 加一次 `replay`）；真模型那一半的**非 tty 部分**由 agent 于 2026-10-22 跑完（DeepSeek 官方端点，两次 run，见「真模型的 chat」）；剩下的 tty 部分（提示符上 Ctrl-C、段进行中 Ctrl-C、审批问人）与 Linux 上的两条 Ctrl-C 判据仍待人跑（见最后一节）。**

这一半用的是 mock provider——agent 的子进程里没有密钥，真模型那一半待人跑（下一节）。task 7.5 列的三件事里，「至少两条输入」跑到了（场景 A 两条、场景 B 与 C 各两条）；「一次取消」与「一次段用完上限」在 agent 这一半**没有真 run 证据**：取消在 Windows 上判不了（沿用 M3 的边界，见最后一节），`max_turns` 用完那条只有 seam ⑥ 的判据 `test_a_segment_that_uses_up_max_turns_returns_to_the_prompt` 钉着。这一半补的是判据没覆盖的那一面：真日志的形状、真工作区里的真文件、stdout 上到底出现什么。

跑法：真工作区就是仓库根 `S:\Develop\mini-harness`（真文件 `docs/CURRENT.md`、`GLOSSARY.md`），日志落在 `sessions/`（gitignored）。回放 fixture 是现场写的 `.tmp/m6-manual/fixture.json`（`read docs/CURRENT.md` → 停 → `read GLOSSARY.md` → 停）与 `.tmp/m6-manual/fixture2.json`（一次 `write` → 停）。输入从管道喂进去（stdin 非 tty）。任务是真事——「读这份仓库的文件并回答」，不是跑判据。

## 场景 A：两条输入加一行空白（session `ceb007576e834d74baf35025a2ed1ac4`）

输入三行：`读一下 docs/CURRENT.md，告诉我门禁四道是什么`、一行空白、`GLOSSARY 里「段」是怎么定义的`。退出码 0，日志 32 条记录。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 一个会话一份日志、一个 session id | 目录里只多一个文件 | ✓ 32 行都落在 `ceb007576e834d74baf35025a2ed1ac4.jsonl` |
| `session/start` 在第一条输入之前 | `entry: chat`、`prompt: ""` | ✓ seq 0 就是它，`entry` 是 `chat`、`prompt` 是空串 |
| 每条输入一条 `user/message` | 两条，内容原文 | ✓ seq 2 与 seq 17，`segment_id` 分别是 `s1` / `s2` |
| 每条输入一个段 | 两个段、段边界成对 | ✓ `segment/start` 在 seq 1 / 16，`segment/end` 在 seq 15 / 30，`stop_reason` 都是 `MODEL_COMPLETED`、`turns` 都是 2 |
| 空白行不写记录、不开段 | 日志里找不到它的痕迹 | ✓ seq 15 与 16 之间什么都没有 |
| `turn_id` 跨段连续 | 不是每段从 `t1` 重来 | ✓ `t1 t2 t3 t4` |
| `session/end` 只在收尾 | 恰一条、`MODEL_COMPLETED` | ✓ seq 31，`turns: 4` |
| stdout 只有模型回复正文与提示符 | 工具结果内容不出现 | ✓ 八行：`> `、两条回复、`> `、`> `、两条回复、`> `；`tool/result` 的内容一个字都没有 |

## 场景 B：溢出塌成段，会话继续（session `f7e2d322075a4200937e1926b0c2e488`）

`--window 66000 --reserve 100 --append-system-prompt`（2000 个汉字，估算 500 token，触发线 364）。输入两行。退出码 0，stdout 只有三行 `> `，日志 14 条。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 溢出只写回合级收尾 | `error/context` + `turn/end` + `segment/end` | ✓ 每段三条：`error/context{code: CONTEXT_WINDOW_EXCEEDED}`、`turn/end(CONTEXT_WINDOW_EXCEEDED)`、`segment/end(..., turns: 1)` |
| 会话继续 | 没有中途的 `session/end` | ✓ 全日志只有一条 `session/end`（seq 13，`MODEL_COMPLETED`、`turns: 2`），在 stdin 关闭之后 |
| 下一条输入开新段 | `s2` 照常开 | ✓ seq 7–12 |
| 不冒充 provider 失败 | 没有 `error/model` | ✓ 全日志没有 |
| 请求级压缩启动与否 | 有可遮蔽内容才启动 | ✓ **没启动**：没有 `model/request`、没有 `compaction/summary`，`shadowed_range` 返回 `None`（见「别扭」第 4 条） |

## 场景 C：围栏拒绝塌成段，会话继续（session `15f8f1bc45164ef1a3368a8ab501203b`）

`--sandbox read-only`，第一条输入要模型写文件。退出码 0，日志 21 条。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 失败是结果 | `tool/result` 与 `error/fence` 都在 | ✓ seq 8 是拒绝文本、seq 9 是 `error/fence{code: SANDBOX_DENIES_WRITE}` |
| 段级失败不退出进程 | 退出码 0、会话继续 | ✓ 退出码 0，`segment/end(s1, FENCE_DENIED, turns: 1)` 之后 `s2` 照常开、照常答 |
| 跨段共用一份上下文 | 第二段的上下文里有第一段的历史 | ✓ 见场景 D 的 `final_context` |

## 场景 D：`chat` 少哪两个 flag，`replay` 读得懂 chat 的日志

| 观察点 | 期望 | 实际 |
|---|---|---|
| `chat --events jsonl` | 参数错误、不建日志 | ✓ 退出码 2、stderr `INVALID_ARGUMENT: unrecognized arguments: --events jsonl` |
| `replay <session_id>` 读场景 C 那份日志 | 每个装配点逐点相等、退出码 0 | ✓ `verified seq=4: OK`、`verified seq=15: OK`、`turn t1: FENCE_DENIED`、`turn t2: MODEL_COMPLETED`、退出码 0 |
| 折叠出来的上下文里两条输入都在 | `role: user` 两条 | ✓ `写一个文件试试` 与 `第二条输入照常` 都在 `final_context.messages` 里 |

## 别扭在哪（六条）

1. **提示符的次数等于读行的次数，不等于段的次数。** 一行空白也打一次 `> `：打提示符 → 读到空白 → 不开段 → 再打提示符。场景 A 的 stdout 里那两条 `> ` 挨在一起就是这个。规格说的是「空白行不写记录、不开段」，实现照做；别扭在屏幕上看不出那一次读发生了什么。
2. **工具调用那一回合的回复正文也打出来。** 场景 C 的 stdout 上有「我写一个文件试试。」——它是一条不带 `purpose` 的 `model/response`，按规格就是回复正文。人看到的是模型在说它接下来要干什么，不是答案。要区分「说要做」与「做完了说」得给回复正文加分类，词表里没有。
3. **溢出那两场里 stdout 只有提示符。** 没有回复、stderr 是空的、退出码 0。人只知道「它没答」，不知道为什么；要看日志才知道每段都塌成 `CONTEXT_WINDOW_EXCEEDED`。这是「stdout 只打模型回复正文」的直接后果，不是漏了报错。
4. **一条输入的会话没有可遮蔽的内容，请求级压缩根本不启动。** `context/budget.py::shadowed_range` 的「最后一条记录总是留着」在这里生效：候选只有那一条 `user/message`，遮蔽集合为空 → 返回 `None` → 什么都不写 → 重新读数仍越线 → 溢出。于是长 `--append-system-prompt` 的 chat 是「会话活着但每段都溢出」：入口边界（ADR-0019）让它不死，可它也办不成事。
5. **PowerShell 5.1 往管道里塞 BOM，第一条输入带着 U+FEFF 进日志。** 用 `$OutputEncoding = [System.Text.Encoding]::UTF8` 喂行时，场景 B 的 seq 2 内容是 `﻿第一条输入`（开头一个零宽字符）。`[System.Text.Encoding]::UTF8` 是带 BOM 的那个 UTF-8。绕法：`$OutputEncoding = New-Object System.Text.UTF8Encoding $false`（场景 C 用的就是这个，日志干净）。mini 照原文写进 `user/message`，不剥——与 ADR-0018 里「配置文件带 BOM 被判成非法 TOML」是同一条编码边界的另一头：那一头剥不剥待人裁决，这一头照「内容原文」写。
6. **提示符在 stdout，审批问题在 stderr，而且非 tty 根本不问。** `tools/fences.py::StdinApprovalGate` 只在 `sys.stdin.isatty()` 时提问（问题写 stderr），非 tty 直接 `UNAVAILABLE`。管道喂行的验收里审批这一环整条看不见，退出码也不反映它。真 tty 的那一半待人跑（下一节）。

## 待人跑的那一半

### 真模型的 chat

原来这一节整段待人跑：agent 的子进程里没有密钥。2026-10-22 人把密钥放进**用户作用域**的 `DEEPSEEK_API_KEY`，于是**非 tty 的那一半由 agent 跑完**（下面两场），tty 的那一半仍待人跑。

两条现场事实决定了怎么跑：

- 用户作用域的环境变量不会自动进到 agent 的子进程——子进程继承的是 harness 进程的环境块。每次调用前显式取一次：`$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")`。
- 本机 Strata（`127.0.0.1:8300`）要的是它自己的 `MINIHNS_STRATA_KEY`，手上没有，所以端点换成官方 OpenAI 兼容端点 `https://api.deepseek.com/v1`，模型 `deepseek-flash`（窗口 1048576）。`provider/openai_compat.py` 的客户端是 `trust_env=False`，本机 `NO_PROXY` 里那个 `[::1]` 打不挂它（同一台机器上裸 httpx 客户端会被它打成 `InvalidURL: Invalid port: ':1]'`）。

#### 场 1：两条输入、真模型、真工具调用（session `19bf20d2d5ab45738f628491d4aab47c`）

退出码 0，日志 39 条记录。工作区 `.tmp/m6-model/ws`，里面一份 9 行的 `notes.md`。输入两行：「先读一下 notes.md，然后用一句话告诉我它有几行」、「再基于刚才读到的内容写一句话结论，不要再调用工具」。stdin 是管道（非 tty），带 `--yes`。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 回复正文什么时候出现 | 整段跑完才出现（不是流式，ADR-0002 第 46 条） | 每个**回合**跑完就出现，不是整段：s1 里 t1 的正文先打出，之后三次工具往返在屏幕上没有任何痕迹，t4 的正文最后打出。仍然不是逐字流式 |
| 工具结果不上 stdout | 只打模型回复正文 | ✓ 四次 `tool/result` 一次都没上 stdout |
| 真模型自己决定调工具 | `read` 之后可能还有别的 | ✓ 模型为了数行数自己调了两次 `bash`：`wc -l notes.md` 在 Windows 上不存在 → `tool/result outcome=OK`、正文开头「退出码 255\n'wc' is not recognized…」；下一回合换成一条 python 命令拿到 9。不变量 B 在真模型下成立：工具失败不打断回合 |
| 段边界与回合计数 | 两条输入两个段 | ✓ `segment/end` 的 `turns` 是 4 与 1，`session/end` 的 `turns` 是 5 |
| 模型答得对不对 | — | 「9 行」，并且主动指出文件第 7 行自称「全文共 12 行」与实际不符 |

两条判据没覆盖的形状，记进 ADR-0002 第 62 与 63 条：

- **只带 `tool_calls`、正文为空的那次 `model/response` 会在 stdout 上打出一个空行。** s1 有四次 `model/response`，屏幕上因此多出两个空行。规格说「stdout 只打印模型回复正文」，空正文也是正文，所以这不是违规，是没人决定过它该不该打。
- **管道喂行在末尾多一个换行**，于是多一次空输入与多一次提示符：两条输入打出四个 `> `。「空白输入不开段」那条判据钉的就是这一环。

#### 场 2：真模型撞上下文超限（session `ff7d94d71c2846d598e11eae873b2484`）

`--window 66000 --reserve 100`（触发线 364 个字符、保留线 10560）。第一条输入约 5000 字，第二条很短。退出码 0，日志 14 条记录。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 溢出写在哪 | `error/context` + `turn/end(CONTEXT_WINDOW_EXCEEDED)` + `segment/end(CONTEXT_WINDOW_EXCEEDED)` | ✓ seq 4 / 5 / 6，`code` 是 `CONTEXT_WINDOW_EXCEEDED` |
| 会话继续 | 回到提示符、没有 `error/model` | ✓ 段 s2 照开、整份日志没有 `error/model` |
| 短输入是否跑得动 | 跑得动，用来证明会话还在 | **跑不动**：s2 也在装配期溢出（seq 10）。超长的那条 `user/message` 住在保留尾部（10560 > 5000），无可遮蔽的内容，于是这个会话里之后每一段都溢出 |
| 屏幕上看得见吗 | — | **完全看不见**：stdout 只有四个 `> `，stderr 是空的，退出码 0。一个「一次模型请求都没成功过」的会话以 `session/end(MODEL_COMPLETED)` 收尾 |

#### 仍待人跑的那一半（tty）

| 观察点 | 期望 | 实际 |
|---|---|---|
| 提示符上 Ctrl-C | 退出码 0、`session/end(MODEL_COMPLETED)`、没有 `segment/start` | 待填（agent 的子进程不是 tty，Ctrl-C 送不进去） |
| 段进行中 Ctrl-C（真模型正在调工具时） | `error/abort` + `turn/end(ABORTED)` + `segment/end(ABORTED)`、进程不退出、下一条输入开新段 | 待填（同上） |
| 会改动的工具在 tty 上问人 | 问题出现在 stderr、回答读 stdin；答 `n` 之后 `approval/response` 与 `tool/result` 都在 | 待填（`StdinApprovalGate` 只在 `sys.stdin.isatty()` 时提问，非 tty 直接 `UNAVAILABLE`；上面两场用的都是 `--yes`） |

跑法（密钥从用户作用域显式取一次，端点用手上有的那个）：

```powershell
cd S:\Develop\mini-harness
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")

# 1) 交互式：tty 上敲两条输入，第二条之后按 Ctrl-C（提示符上）
uv run minihns chat --provider openai --base-url https://api.deepseek.com/v1 `
  --model deepseek-flash --api-key-env DEEPSEEK_API_KEY

# 2) 同一句里加 --yes（不问人），再跑一次，看工具调用那一段的屏幕输出顺序
#    这一条 agent 已跑过（场 1）；tty 上问人那一环仍待人看

# 3) 把窗口压小，看会话是否继续
uv run minihns chat --provider openai --base-url https://api.deepseek.com/v1 `
  --model deepseek-flash --api-key-env DEEPSEEK_API_KEY `
  --window 66000 --reserve 100 --append-system-prompt "（一段两千字左右的说明）" --yes
```

### Linux 上的两条 Ctrl-C 判据

`tests/test_cli_chat.py` 的 `test_sigint_mid_segment_cancels_the_segment_not_the_session` 与 `test_sigint_at_the_prompt_ends_the_session_cleanly` 在 Windows 上 skip（沿用 M3 的边界：Windows 真实控制台 Ctrl-C 无判据）。机制本身由两条跨平台的过程内守卫钉（handler 置起段事件 / handler 抛 `KeyboardInterrupt`），可子进程那两条到收尾都没跑过。

```bash
cd /path/to/mini-harness && git checkout change/m6-chat-repl
uv run pytest tests/test_cli_chat.py -q -k sigint
```

判据：两条都过（不是 skip）。若哪条红，把它的完整输出贴回来。
