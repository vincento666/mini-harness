# m13-goal-rounds 真实端点

**日期**：2026-11-19。`--provider deepseek`（`deepseek-chat`），`run` 入口，两个独立工作区（`.tmp/real/m13`、`.tmp/real/m13-cap`），`--yes`（workspace-write，不设审批）。两场都在十秒内跑完：A 9.1 秒 / 8 回合，B 10.1 秒 / 8 回合。

## 场景 A：两轮续跑后自己标完成

工作区只有 `data.txt`（三行：3 / 5 / 7）。一次 `run` 把节奏说清：

- 人类这一段只 `create_goal`（`max_rounds: 2`），不读不写；
- 目标第 1 轮只读 `data.txt` 并说明计划，不写、不标完成；
- 目标第 2 轮写 `sum.txt`、读回确认、`update_goal complete`。

### 观察

| 段 | 来源 | 回合 | 做了什么 | 该段的 goal 快照 |
|---|---|---|---|---|
| s1 | 人 | t1–t2 | `create_goal {objective: "把 data.txt 的三个数字相加写入 sum.txt", max_rounds: 2}`，随后停 | active · rev 1 · rounds 0 |
| s2 | goal 轮 1 | t3–t4 | `read data.txt`（拿到 3/5/7），说明「相加得 15，写 `15` + 换行」，未写文件 | active · rev 1 · rounds 1 |
| s3 | goal 轮 2 | t5–t8 | `write sum.txt` → `read sum.txt`（读回 `15`）→ `update_goal complete` | active · rev 1 · rounds 2 → complete · rev 2 |

- **产物**：`sum.txt` 内容为 `15\n`，与读回一致；
- **轮次不改 revision**：三条轮次快照的 `revision` 全是 `1`，只有 `complete` 那条是 `2`——真实日志里 CAS 引用跨轮仍有效；
- **`armed` 不在载荷里**：四条 `goal/updated` 的快照都没有这个键；
- **无人插话**：两轮之间没有读 stdin，也没有 `user/message`（除 goal 来源的两条）；
- 进程退出码 `0`，`session/end` 恰一条。

usage（同一会话，按回合）：

| 回合 | input | cache_read | output |
|---|---|---|---|
| t1 | 3024 | 0 | 75 |
| t2 | 235 | 2944 | 66 |
| t8 | 199 | 3584 | 76 |

`cache_read` 从 t2 起命中并逐轮增长（2944 → 3584）：轮次复用的是同一段前缀，不是每轮重建上下文。

## 场景 B：两轮用尽后落 `round-limit`

另一工作区（`data.txt`：2 / 4 / 6），同一节奏，但两轮都只读、不标完成，看上限如何收尾。

### 观察

| 段 | 来源 | 回合 | 收尾 |
|---|---|---|---|
| s1 | 人 | 4 | `create_goal {max_rounds: 2}` 后 MODEL_COMPLETED |
| s2 | goal 轮 1 | 2 | MODEL_COMPLETED，未标完成 |
| s3 | goal 轮 2 | 2 | MODEL_COMPLETED，未标完成 |

s3 之后：

```
goal/updated {phase: "blocked", revision: 2, rounds_started: 2,
              blocked_reason: {code: "round-limit", message: "轮次已用尽（2/2）"}}
```

- **没有 s4**：撞上限不再开段；
- 工作区里没有 `sum.txt`（演练确实只读）；
- 退出码 `0`，`session/end` 唯一；
- 轮次快照依旧是 `rev 1`（rounds 1 与 2），阻塞那条才是 `rev 2`。

## 结论

**通过**。判据里的两件核心行为在真实端点上成立：

1. 目标 active 且武装时，段结束不回到入口，直接起下一轮（A 两轮、B 两轮）；
2. 上限用尽写 `blocked{round-limit}` 并停下（B），完成时写 `complete` 并停下（A）；两种收尾都不再开段。

同时验证了「轮次不递增 revision」「`armed` 不落盘」两条不变量在真实日志上成立。

## 未覆盖（交给别的场次）

- `/goal` 命令面与取消后暂停：UAT 场次 2、4；
- `--resume` 后不自动跑：`tests/test_chat_goal_driver.py`（mock）＋ UAT 场次 4；
- 变异测试：6.3。
