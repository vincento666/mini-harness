# `m10-compaction-parameters` UAT（人跑）

**状态**：等人跑（ADR-0025：这张表没填完，本 change 不得归档、不得合入 `main`）。

**怎么算办一件真事**：不是跑判据，是在一个真实工作区里改 `mini.config.toml`，用 `minihns chat` 读大文件，观察 `[遮蔽]` 的保留量、`session/start` 的四个值，以及改小 retain 后压缩是否真的更激进。真实端点不是本 change 的硬要求（配置是本地行为），但 W1 的最后一次用真实 deepseek 最好。

## 跑之前

```powershell
$ws = ".tmp\m10-compaction-uat\ws"
New-Item -ItemType Directory -Force $ws | Out-Null
# 放一份 60 KB 左右的文本文件，例如 big.md
Set-Content "$ws\big.md" ("alpha beta gamma delta " * 4000) -Encoding UTF8
```

## W1 · 默认 vs 小 retain

1. 在 `$ws/mini.config.toml` 写：

```toml
window = 70000
reserve = 100
compaction_retain_ratio = 0.16
```

2. 跑：

```powershell
uv run minihns chat --workspace $ws --session-dir .tmp\m10-compaction-uat\s1 --window 70000 --reserve 100 --provider mock --fixture <fixture>
```

3. 再写 `compaction_retain_ratio = 0.05`，换 `--session-dir .tmp\m10-compaction-uat\s2` 重跑。
4. 对比两次 `[遮蔽] 折掉 seq …：tokens <前> 降至 <后>` 与 `compaction/summary.shadowed_range`。

**预期**：0.05 那次保留尾部更小、遮蔽范围更大；`session/start.payload.compaction_retain_ratio` 分别是 0.16 / 0.05。

## W2 · retain_tokens 覆盖 ratio

1. 配置写 `compaction_retain_ratio = 0.5`、`compaction_retain_tokens = 3000`。
2. 重跑同一个 fixture。
3. 看 `shadowed_range` 与 `tokens_after`。

**预期**：实际保留预算按 3000，不按 35000；payload 两个值都在。

## W3 · 非法值不建日志

```powershell
uv run minihns run -p "x" --provider mock --fixture <fixture> --workspace $ws
```

把配置改成 `compaction_retain_ratio = 0`，再跑一次。

**预期**：退出码 2，stderr 含 `INVALID_ARGUMENT`，`.tmp\m10-compaction-uat` 下没有新的 session 日志。

## W4 · replay 仍相等

```powershell
uv run minihns replay <session-id> --session-dir .tmp\m10-compaction-uat\s2
```

**预期**：退出码 0；没有 `REPLAY_MISMATCH`；旧日志（没有四个字段）也能 replay。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| W1 | 0.16 vs 0.05 | 遮蔽范围变大 / payload 对 | 0.16：`12171->10154` range 1-8；0.05：`6117->2079` range 1-15，第二次 `6115->4100` range 28-32；payload 分别为 0.16/0.05 | 通过 | 单份大文件只产生一条 read 结果，最后一条总被保留，比率看不出差别；要六份文件才看得到尾部落差 |
| W2 | retain_tokens=3000 | 覆盖 0.5 ratio | 0.5+3000：出现两次遮蔽（`6117->2079`、`6115->4100`），payload `0.5/3000`；对照组 0.5+0 不触发遮蔽 | 通过 | 无 |
| W3 | ratio=0 | 退出码 2 / 无日志 | `INVALID_ARGUMENT: compaction_retain_ratio 必须在 (0, 1] 内，收到 0.0`；退出码 2，`w3-sessions` 无 jsonl | 通过 | 无 |
| W4 | replay | 退出码 0 | session `16d04ac7...`：`verified seq=28/35/45: OK`，退出码 0 | 通过 | 无 |

**至少一条「用起来别扭」**：单份大文件只有一条 read 结果，保留尾部永远包含它，ratio 调小看不出差别；UAT 需要用多份文件/多条结果才能观察 retain 的效果。

**结论**：通过（agent 代跑，用户明确要求；W1 s3/s4、W2 s5 + s6 对照、W3 w3-sessions、W4 s4）。
