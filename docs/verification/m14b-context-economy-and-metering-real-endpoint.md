# m14b-context-economy-and-metering 真实端点

**日期**：2026-11-16。`--provider deepseek`（`deepseek-chat`），工作区 `.tmp/real/m14b`，会话 `e5a9c4b9…`。价目表用测试值 `input = 1.0`、`output = 2.0`（只为验算金额，不是真实定价）。

## 场景

- 工作区有 `a.md`（一句说明）；
- 任务：「读一下 a.md，用一句话总结它说了什么。」

## 观察

| 回合 | 日志里的 `usage` |
|---|---|
| t1 | `input 156 / cache_read 1408 / output 38` |
| t2 | `input 227 / cache_read 1408 / output 89` |

`minihns usage e5a9c4b9… --config …` 的输出：

```json
{
  "turns": [
    {"turn_id": "t1", "input_uncached": 156, "cache_read": 1408, "cache_write": 0, "output": 38},
    {"turn_id": "t2", "input_uncached": 227, "cache_read": 1408, "cache_write": 0, "output": 89}
  ],
  "total": {"input_uncached": 383, "cache_read": 2816, "cache_write": 0, "output": 127},
  "cost": 0.000637
}
```

对账：

- 四桶与日志逐项相等（383 / 2816 / 0 / 127）；
- 成本 `(383×1 + 2816×0 + 127×2) / 1e6 = 0.000637`，与输出一致；
- 缓存命中确实是真实数字：DeepSeek 两回合都报 `1408`，说明适配器的 `prompt_cache_hit_tokens` 解析生效。

## 结论

**通过**。`cache_read` 在生产路径上非空，四桶不再是「结构就位、数值为 0」。

未覆盖：`cache_write`（DeepSeek 不报该字段，恒为 0）；截断/剪枝在本场没有触发（结果都很短）。
