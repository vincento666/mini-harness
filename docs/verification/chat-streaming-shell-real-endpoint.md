# Chat streaming shell 真实端点验收

**日期**：2026-11-03。**端点**：DeepSeek `deepseek-reasoner`（真实 key，不进日志）。
**session**：`94676c8839824dc4962e49c87aa506a3`。

## 命令

```powershell
"用一句话解释 1+1，并说明你的思考过程。" |
  uv run minihns chat --stream --workspace .tmp\chat-stream-uat\ws `
    --provider deepseek --model deepseek-reasoner --max-turns 2 --sandbox workspace-write --yes
```

## 观察

- stderr 先出现 `[thinking] ...`，是 reasoning 文本；
- stdout 随后出现最终正文；
- 正文只出现一次，没有再打印整段日志投影；
- 会话 id 在 stderr：`94676c...`；
- 配置 `reasoning_effort = "high"`。

## 结论

`--stream` 的正文/思考分流与去重在真实 reasoner 上成立。取消场次需要 tty 交互，留 UAT。
