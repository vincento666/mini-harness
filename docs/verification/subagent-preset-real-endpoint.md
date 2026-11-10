# subagent-preset 真实端点验收

**日期**：2026-11-10。`--provider deepseek`，模型 `deepseek-chat`。

## S1 · 配了 preset：子工具表由 preset 决定

工作区 `mini.config.toml`：

```toml
[subagent]
preset = "reader"

[subagent.presets.reader]
tools = ["read", "glob"]
```

`minihns run -p "派一个 subagent 读 inbox.md 并总结成一句话" --yes`

| 观察 | 事实 |
|---|---|
| 父 `session/start.tools` | `read / write / edit / glob / grep / bash / subagent`（父自己的表不变） |
| 子 `session/start` | `entry=subagent`、`preset=reader`、`tools=read / glob` |
| 子做了什么 | 只用 `read` 读了 inbox.md，父拿到一句话总结 |

## S2 · 没配 preset：子继承父的整张表

删掉 `mini.config.toml`，同一句任务换成 second.md。

| 观察 | 事实 |
|---|---|
| 子 `session/start` | `entry=subagent`、没有 `preset` 字段、`tools` 与父的七个名字完全一致 |
| 派发 | 照常工作（没有因为缺 preset 失效） |

## 结论

**通过**：preset 决定子会话的工具表、无 preset 时继承父组合、父子都照常收尾。运行期没有读磁盘配置——子日志里的 `preset` 与 `tools` 就是装配期编译出来的事实。
