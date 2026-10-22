# M6 人手验收（`m6-chat-repl`）

**状态：agent 这一半跑完（2026-10-21 22:36–22:52，真 PowerShell 终端，四次 `chat` run 加一次 `replay`）；真模型那一半与 Linux 上的两条 Ctrl-C 判据待人跑（见最后一节）。**

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

agent 的子进程里没有密钥。端点与密钥沿用 M5 / M9 记下的那套。

```powershell
cd S:\Develop\mini-harness
$env:MINIHNS_STRATA_KEY = "<密钥>"

# 1) 交互式：tty 上敲两条输入，第二条之后按 Ctrl-C（提示符上）
uv run minihns chat --provider openai --base-url http://127.0.0.1:8300/v1 `
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY

# 2) 同一句里加 --yes（不问人），再跑一次，看工具调用那一段的屏幕输出顺序

# 3) 把窗口压小，看会话是否继续
uv run minihns chat --provider openai --base-url http://127.0.0.1:8300/v1 `
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY `
  --window 66000 --reserve 100 --append-system-prompt "（一段两千字左右的说明）" --yes
```

| 观察点 | 期望 | 实际 |
|---|---|---|
| 提示符上 Ctrl-C | 退出码 0、`session/end(MODEL_COMPLETED)`、没有 `segment/start` | 待填 |
| 段进行中 Ctrl-C（真模型正在调工具时） | `error/abort` + `turn/end(ABORTED)` + `segment/end(ABORTED)`、进程不退出、下一条输入开新段 | 待填 |
| 回复正文什么时候出现 | 整段跑完才出现（不是流式，ADR-0002 第 46 条） | 待填 |
| 真模型撞上下文超限 | `error/context` + `segment/end(CONTEXT_WINDOW_EXCEEDED)`、会话继续、没有 `error/model` | 待填 |
| 会改动的工具在 tty 上问人 | 问题出现在 stderr、回答读 stdin；答 `n` 之后 `approval/response` 与 `tool/result` 都在 | 待填 |

跑完把 session id 或日志文件名给我，我按这张表读。

### Linux 上的两条 Ctrl-C 判据

`tests/test_cli_chat.py` 的 `test_sigint_mid_segment_cancels_the_segment_not_the_session` 与 `test_sigint_at_the_prompt_ends_the_session_cleanly` 在 Windows 上 skip（沿用 M3 的边界：Windows 真实控制台 Ctrl-C 无判据）。机制本身由两条跨平台的过程内守卫钉（handler 置起段事件 / handler 抛 `KeyboardInterrupt`），可子进程那两条到收尾都没跑过。

```bash
cd /path/to/mini-harness && git checkout change/m6-chat-repl
uv run pytest tests/test_cli_chat.py -q -k sigint
```

判据：两条都过（不是 skip）。若哪条红，把它的完整输出贴回来。
