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

### 窄窗口那条：`458576ac17e24a77a7251e1db6020737`（5 条记录）

| 观察点 | 期望 | 实际 |
| --- | --- | --- |
| 退出码 | 0（正常办完）或 4（真装不下） | ✓ 4 |
| 触发线 | `32768 − 4096 − 65536` 为负 → 取 0 | ✓ 0（stderr 里写着） |
| 日志形状 | 装配之前就越线 → 没有 `context/assembled`、没有 `model/request` | ✓ `session/start` → `turn/start` → `error/context` → `turn/end` → `session/end` |
| 溢出收尾的 stderr 措辞 | 「无可遮蔽的内容…」，与「没压缩」一致 | ✓ `无可遮蔽的内容，预算读数 33 已超过触发线 0` |
| `minihns replay` | 不报不一致、退出码 0 | ✓ `no_context_assembled: 这份日志没有装配点` + `turn t1: CONTEXT_WINDOW_EXCEEDED`（M5 审查轮修掉的那条守卫在真日志上成立） |
| 摘要质量 | 不适用 | 不适用：这一跑没有任何压缩发生 |

「窗口 32768 装不下任何东西」不是这一跑的失败，是公式的结果：headroom 65536 比窗口本身还大，触发线取 0，任何非空上下文都越线。

> **M6 更正（2026-10-21，`m6-chat-repl` 任务 7.6）**：这一条观察照 M5 的实现成立，到 M6 不再成立。ADR-0019 把「`window − reserve − 65536 ≤ 0`」判成**启动期参数错误**（照 DSH：`pressureBudgetTokens <= 0` 在配置解析期抛 `TargetPressureConfigError`）。今天同一句命令的结果是退出码 **2**、stderr `INVALID_ARGUMENT: --window 32768 减去 --reserve 4096 与余量 65536 之后没有剩余压力预算`，**不建 session 日志**——也就没有上面那五条评价记录（`session/start` → `turn/start` → `error/context` → `turn/end` → `session/end`）。这一节保留不删：它是 M5 的实测记录，也是「触发线取 0 时任何非空上下文都越线」这条公式性质的出处。今天的等价跑法是把窗口抬到 `reserve + 65536` 之上，例如 `--window 73728 --reserve 4096`（触发线 4096）。

### 宽窗口那条：`f7fcaa2c4b764e13aa980227982f6d19`（39 条记录、五回合跑完）

| 观察点 | 期望 | 实际 |
| --- | --- | --- |
| 触发线 / 保留尾部 | 61440 / 20971 | ✓ 公式核对过 |
| 回合形状 | 工具往返正常配对、正常收尾 | ✓ t1 `read`（结果 58961 字符）→ t2 `bash` ×2 → t3 `glob` → t4 `read` ×2（13693 / 6339 字符）→ t5 收尾 3251 字；`session/end.stop_reason = MODEL_COMPLETED` |
| 日志里有没有 `compaction/summary` | 有则说明压缩救回一次 | **没有**。t5 那次装配的估算读数 19991、校准读数 33871（provider 回报的最大 `input_tokens`），离触发线 61440 还差 27569 |
| 溢出收尾 | 没发生 | ✓ 没有 `error/context` |
| 摘要质量 | 摘要是否说清了任务 / 已做了什么 / 下一步 | 不适用：没有摘要可看 |

**没触发压缩不是 bug**：这份真工作区上的对话总共约 79000 字符，离 61440 的触发线差得远。要看压缩真跑起来，窗口要窄到「触发线为正、且对话中途越线」。同一份工作区换这一条：

```powershell
uv run minihns run -p "读 notes/merged-notes.md，指出里面还没处理的欠账" `
  --provider openai --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs `
  --api-key-env MINIHNS_STRATA_KEY `
  --workspace .tmp/m5-manual/ws --session-dir .tmp/m5-manual/sessions --window 73728 --reserve 4096 --yes
```

触发线 `73728 − 4096 − 65536 = 4096`、保留尾部 `floor(73728 × 0.16) = 11796`。t1 装配读数 33 不越线；t1 那条 58961 字符的 `read` 结果进来之后，t2 的读数约 14771 > 4096 → 该出现 `compaction/summary`。要看的是：遮蔽范围有没有把 t1 那组往返整组带走（切点落在组内不拆散）、`tokens_before` / `tokens_after` 差多少、遮蔽之后表层还剩几条、以及压缩是否真把这次 run 救回退出码 0（救不回来就是退出码 4 且措辞换成「压缩之后…」）。

### 顺手量到的一条偏差（已记进 ADR-0016 的 Consequences）

t5 那次装配三个数：`ceil(字符数 / 4)` 估出 **19991**，harness 当时能用的校准读数是 **33871**（provider 回报的最大 `input_tokens`），provider 事后回报那次请求的真实 `input_tokens` 是 **44873**。估算比真实小 **2.24 倍**（正文是中文，一个汉字算 1 个字符、实际约 1 至 2 个 token）；校准把偏差收窄到 **1.32 倍**，但校准用的是**上一次请求**的数，天然滞后一回合。结论与 ADR-0016 一致：估算只管「要不要压缩」，真兜底是 provider 报 `context_length_exceeded` 那条路径。
