# M5 人手验收：`m5-context-budget-compaction`

完成判据里的那一条：拿它办一件真事，不是跑判据。分两栏——

- **harness 层**：真工作区 + mock provider，agent 自己跑（不需要密钥）。判的是压缩、溢出、重放这三件事在真实 CLI 子进程里的形状。
- **模型层**：真工作区 + 真模型，**必须人类跑**（密钥只在人的 shell 里）。判的是压缩在真实对话里按时触发、溢出收尾长什么样。

## harness 层（agent 跑，2026-10-21）

工作区 `.tmp/m5-manual/ws`，里面是真文档：`CURRENT.md`、`roadmap.md`，以及
`notes/merged-notes.md` = `docs/dsh-alignment.md` + `docs/lessons.md` +
`docs/adr/0002-deferred-refactors.md` 三份真文档合并，55118 个字符。
任务是一句真话：「把 notes/merged-notes.md 读一遍并给出摘要」。

### Run A：窗口 68000 / 预留 100（触发线 2364、保留预算 10880）

`minihns run -p "…" --provider mock --fixture .tmp/m5-manual/turns.json --workspace .tmp/m5-manual/ws --session-dir .tmp/m5-manual/sessions --window 68000 --reserve 100 --yes`

- 退出码 **0**，session `aa9cb054041342758055eb163786ff41`，日志 17 条。
- 事件序列：`session/start, turn/start, context/assembled, model/request, model/response, tool/call, tool/result, turn/end, turn/start, model/request, model/response, compaction/summary, context/assembled, model/request, model/response, turn/end, session/end`。
- 压缩发生在 **t2 的 `context/assembled` 之前**：摘要调用 seq 9 / 摘要回复 seq 10 / `compaction/summary` seq 11，装配记录 seq 12。
- `compaction/summary` 的 payload：`shadowed_range {start: 1, end: 6}`、`tokens_before 14796`、`tokens_after 45`。被遮蔽的正是 t1 那一整组（含那条 55118 字符的 `tool/result`）。

### Run B：窗口 4000 / 预留 500（触发线 0）

同一条命令换窗口。

- 退出码 **4**，session `a3bee6b3794c44bf9effa780c35066f0`，日志只有 5 条：
  `session/start, turn/start, error/context, turn/end, session/end`——**没有 `model/request`**，溢出这一回合没调过模型。
- stderr：`CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 32 已超过触发线 0`。

### Run C：重放 Run A

`minihns replay aa9cb054041342758055eb163786ff41 --session-dir .tmp/m5-manual/sessions`

- 退出码 **0**，`verified seq=2: OK` 与 `verified seq=12: OK`（两条 `context/assembled` 都等于自己前缀的重算结果），无 `REPLAY_MISMATCH`。
- `final_context` 三条消息：`system` 96 字符、`user` 32 字符、`system` 50 字符（那条摘要）。55118 字符的工具结果不在表层。

### 这一栏里发现的一处缺陷

第一次跑 Run B 时 stderr 写的是「压缩之后预算读数 32 仍超过触发线 0」——可这一回合**没有发生压缩**（无可遮蔽内容）。措辞与事实不符。
已按 red → green 修掉：`tests/test_turn_compaction.py` 里那条原本写成 `detail == error.payload["detail"]` 的自反断言换成判前缀（「无可遮蔽的内容」/「压缩之后」），先红后绿；detail 由日志里有没有本回合的 `compaction/summary` 决定。

## 模型层（人类跑）

密钥只在人的 shell 里，agent 跑不了。runbook：

```powershell
cd S:\Develop\mini-harness
# 1) 真事：让真模型在这份真工作区里办一件事，窗口给足，看它正常跑完
$env:MINIHNS_STRATA_KEY = "<你的 key>"
uv run minihns run -p "读 notes/merged-notes.md，指出里面还没处理的欠账" `
  --provider openai --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs `
  --api-key-env MINIHNS_STRATA_KEY `
  --workspace .tmp/m5-manual/ws --session-dir .tmp/m5-manual/sessions --window 32768 --reserve 4096 --yes
# 记下 session id，下面要用
uv run minihns replay <session-id> --session-dir .tmp/m5-manual/sessions
```

观察点（跑完把结果写进这张表，或直接把日志文件名告诉我，我来读）：

| 观察点 | 期望 | 实际 |
| --- | --- | --- |
| 退出码 | 0（正常办完）或 4（真装不下） | 待填 |
| 日志里有没有 `compaction/summary` | 窗口 32768 时触发线 = `32768 - 4096 - 65536` 为负 → 取 0，**每次装配都进压缩判定**；第一次多半无可遮蔽 → 直接溢出 4 | 待填 |
| 溢出收尾的 stderr 措辞 | 「无可遮蔽的内容…」或「压缩之后…」，与是否真压缩一致 | 待填 |
| `minihns replay` | 退出码 0、每条 `context/assembled` 都 `OK` | 待填 |
| 摘要质量 | 摘要是否说清了任务 / 已做了什么 / 下一步 | 待填 |

再跑一条窗口宽一点的，看压缩真的救回一次：

```powershell
uv run minihns run -p "读 notes/merged-notes.md，指出里面还没处理的欠账" `
  --provider openai --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs `
  --api-key-env MINIHNS_STRATA_KEY `
  --workspace .tmp/m5-manual/ws --session-dir .tmp/m5-manual/sessions --window 131072 --reserve 4096 --yes
```

窗口 131072：触发线 `min(104857, 131072 - 4096 - 65536) = 61440`、保留预算 20971。
观察点：`compaction/summary` 的 `tokens_before` / `tokens_after` 差多少、`shadowed_range` 有没有把一整组工具往返一起遮蔽、摘要之后的表层还剩几条消息。
