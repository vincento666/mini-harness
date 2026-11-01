# Reasoning 模式真实端点验收

**日期**：2026-11-01。**端点**：DeepSeek `deepseek-reasoner`（真实 key，不进日志）。

## 场景

工作区 `.tmp/reasoning-real/ws`，`mini.config.toml`：

```toml
reasoning_effort = "high"
```

`minihns chat --provider deepseek --model deepseek-reasoner --reasoning_effort` 由配置给出。

## 观察

### session `e782b7be07624b39842612e599305031`

- `model/response.blocks`：`reasoning` → `text`
- usage：`input_tokens=1182`、`output_tokens=266`、`reasoning_tokens=143`
- reasoning block 有完整思考文本，text 是最终回答。

### session `e8a286592ff3442582c66acce5599dd3`（带工具）

- t1：`blocks=tool-call`，`reasoning_tokens=0`
- t2：`blocks=reasoning,text`，`output_tokens=104`、`reasoning_tokens=54`
- 最终回答正确列出 `alpha` / `beta`。

## 结论

- 真实 reasoner 的 `reasoning_content` 进入 reasoning block，正文进入 text block。
- `reasoning_tokens` 是 `output_tokens` 的子集，payload 里可读。
- 工具回合与思考回合都能落成 blocks；不写每个 delta。
- 未触发“reasoning → tool-call → reasoning → text 在同一 response” 的长样本；这是单次真实端点样本的边界，不冒充统计保证。
