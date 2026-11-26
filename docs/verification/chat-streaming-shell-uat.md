# Chat streaming shell UAT

**状态**：等人跑。

**怎么算办一件真事**：在真实终端里用 `minihns chat --stream` 问一个需要思考的问题，观察正文是否逐字出现、思考是否走 stderr、取消后是否保留已显示前缀；再用 `--no-stream` 确认旧行为。

## 跑之前

- 真实 reasoner；`DEEPSEEK_API_KEY`。
- 工作区 `.tmp/chat-stream-uat/ws`，配置 `reasoning_effort = "high"`。
- 终端能区分 stdout / stderr（或重定向到两个文件）。

## C1 · 流式正文

```powershell
uv run minihns chat --stream --workspace .tmp\chat-stream-uat\ws `
  --provider deepseek --model deepseek-reasoner --max-turns 2 --sandbox workspace-write --yes
```

输入：`用三句话解释 1+1。`

**预期**：正文逐字出现在 stdout；提示符只出现一次；段结束后没有整段重复。

## C2 · 思考走 stderr

同一命令，stderr 重定向到文件。

**预期**：stderr 有 `[thinking] ...`；stdout 不含思考文本。

## C3 · 取消

在正文流到一半按 Ctrl-C。

**预期**：已显示前缀保留；不追加最终整段；stderr 有 ABORTED 状态行；回到提示符。

## C4 · 非流式不变

```powershell
uv run minihns chat --no-stream ...
```

**预期**：仍是整段一次性输出，日志/退出码与今天一致。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| C1 | `--stream` | 正文逐字、不重复 | 真实 session `94676c...`：正文一次，未重复整段；默认 `--stream` 已生效；session `383ba483...` 看到 `[answer]` 开始标志 | 通过（agent） | 无 |
| C2 | 思考分流 | 只在 stderr | session `94676c...`：stderr `[thinking] ...`，stdout 无思考文本；`[answer]` 结束 thinking 行 | 通过（agent） | 无 |
| C3 | 流式中取消 | 保留前缀 | 人在 tty 输入「输出1000字散文」，正文流到「那时」按 Ctrl-C：保留该前缀，未追加最终整段，stderr `[段] ABORTED`，回到提示符 | 通过（人跑） | 无 |
| C4 | `--no-stream` | 旧行为不变 | 真实 session `f09b8b42...`：整段 `> 4。` 一次输出 | 通过（agent） | 无 |

**至少一条「用起来别扭」**：C3 必须人在终端按 Ctrl-C；脚本只能验证非取消路径。

**结论**：C1–C4 全部通过；C3 由人在 tty 跑，输出保留了已显示前缀并写 `[段] ABORTED`。
