# m14a-workspace-contract 真实端点

**日期**：2026-11-13。`--provider deepseek`（`deepseek-chat`），工作区 `.tmp/real/m14a`，会话 `1c9421dc…`。

## 场景

项目根 `AGENTS.md` 写两条可观察的约定：

```md
- 回复的第一句必须以「收到」开头。
- 回答里必须提到这条约定来自 AGENTS.md。
```

任务：「报一下你现在的工作目录名，并按约定回复。」

## 观察

| 面 | 结果 |
|---|---|
| 日志里的契约消息 | `source: "workspace-instructions"`，`scopes` 为 `[("project", "AGENTS.md", 55, False)]` |
| 位置 | 消息在第 4 条（`turn/start` 之后、`context/assembled` 之前） |
| 模型回复 | 「**收到。**当前工作目录名是 `m14a`……这条约定来自本工作区的 AGENTS.md。」 |

## 结论

**通过**：契约在真实端点被读到，模型按约定执行，且日志里可审计到来源与字节数。没有观察到截断、转义或路径泄漏问题（本条契约 55 字节，远低于 16 KiB）。

UAT 四场（`docs/verification/m14a-workspace-contract-uat.md`）另跑。
