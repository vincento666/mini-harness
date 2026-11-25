# UAT：restore-chat-streaming

**状态**：**全部待人跑/待人确认**（场次 2、5 有 agent 代跑记录，但按 ADR-0025 未经人确认不算通过）；场次 1、3、4 无记录。
**归属**：场次 1、3、4 是 tty 手感，按 ADR-0025 由人跑；agent 只准备场次与观察表。场次 2、5 不需要 tty，代跑已如实标注。

## 场次

| # | 命令 | 观察什么 | 通过判据 | 结果 |
|---|---|---|---|---|
| 1 | `minihns chat`（不传 flag），提一个需要长回答的问题 | 正文是否在生成时逐段出现；`[answer]` 是否只出现一次 | 不传 flag 就能看到增量；一个轮次内 `[answer]` 恰一次；轮末没有整段重复 | **待人跑** |
| 2 | `minihns chat --no-stream`，同一个问题 | 是否回到「安静到轮末、一次出现」 | 轮中没有正文输出；轮末整段出现一次；stderr 无 `[answer]` | **待人确认**（agent 代跑记录：stdout 是 `> 这是完整回复\n> `，stderr 只有会话 id；管道形态，非 tty） |
| 3 | `minihns chat`，让模型创建一个多轮目标并自动续跑 | 每轮正文是否各自成行；`[轮] n/cap` 是否在该轮正文前；提示符是否只在最后出现一次 | 两轮以上的正文不粘连；每条 `[轮]` 在对应正文之前；提示符一条输入只一次 | **待人跑**（自动化判据 `test_goal_rounds_each_get_their_own_line` 已覆盖分行与顺序，tty 合流手感仍需人看） |
| 4 | `minihns chat`，等正文出现几个字后按 Ctrl-C | 已显示的前缀是否保留；是否补打整段；是否回到提示符 | 前缀保留并换行；不出现最终整段；`[轮] 收尾 ABORTED` 可见；进程不退出 | **待人跑**（这是本 change 最关键的手感场次） |
| 5 | `printf '你好\n' \| minihns chat` | stdin 非 tty 时是否照常开轮与收尾 | 有增量输出；EOF 后退出码 0；日志有 `session/end` | **待人确认**（agent 代跑记录：会话 `2eb3ff10712142b8acaa152e1fe26cff`，退出码 0，stdout 有正文、stderr 有 `[answer] `） |

## 观察记录

- 终端：（待填：iTerm2 / Terminal.app）
- 端点：OpenRouter `qwen/qwen3.8-27b`，经 `--proxy http://127.0.0.1:7897`
- 时间：
- 场次 1 实际：
- 场次 2 实际：2026-11-25 代跑（mock fixture，管道）。`> 这是完整回复\n> `，无 `[answer]`。
- 场次 3 实际：
- 场次 4 实际：
- 场次 5 实际：2026-11-25 代跑（真实端点）。见 `restore-chat-streaming-real-endpoint.md` 场次 1。

## 已知偏离

- 场次 2、5 由 agent 代跑（2026-11-25），它们不需要 tty；场次 1、3、4 未代跑，等人在真终端里跑。
- 场次 5 用的是真实端点那一场（管道喂一行），不是单独再造一个 mock 场次——两者的判据相同，避免重复请求。

## 跑之前的准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
uv run minihns chat --provider openrouter --proxy http://127.0.0.1:7897 --max-steps 4
```

场次 4 的提示词建议：「分三轮讲一个故事，每轮一段，写完一段就停」。看到正文滚出来几个字后按 Ctrl-C。
