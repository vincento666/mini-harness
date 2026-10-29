# M10 压缩参数真实端点验收

**日期**：2026-10-29。**端点**：deepseek（真实 key，不进日志）。**入口**：`minihns chat`。

## 跑法

工作区 `.tmp/m10-compaction-real/ws`：

```toml
# mini.config.toml
compaction_retain_ratio = 0.05
```

```powershell
uv run minihns chat --workspace .tmp\m10-compaction-real\ws `
  --session-dir .tmp\m10-compaction-real\sessions `
  --provider deepseek --window 70000 --reserve 100 --max-turns 8 --sandbox workspace-write --yes
```

输入：`用 read 工具读取 big.md 并总结。`（`big.md` 151,203 字节，1200 行）

## 观察（session `e7c1140f2c7c4c089f23002bbe79632e`）

stderr：

```text
[遮蔽] 折掉 seq 1 至 8：tokens 39116 降至 198
```

`session/start.payload` 的有效值：

```json
{
  "window": 70000,
  "reserve": 100,
  "compaction_threshold_ratio": 0.8,
  "compaction_headroom_tokens": 65536,
  "compaction_retain_ratio": 0.05,
  "compaction_retain_tokens": 0
}
```

`compaction/summary`：`tokens_before=39116`、`tokens_after=198`、`shadowed_range={start:1,end:8}`。

## 结论

- 配置文件里的 `compaction_retain_ratio = 0.05` 生效并进入 payload；
- 真实端点确实按更小的保留比例触发了遮蔽，且 `tokens_after < tokens_before`；
- `minihns replay e7c1140f2c7c4c089f23002bbe79632e`：`verified seq=4: OK`、`verified seq=14: OK`，无 `REPLAY_MISMATCH`；
- 单次真实端点样本，不是统计保证。
