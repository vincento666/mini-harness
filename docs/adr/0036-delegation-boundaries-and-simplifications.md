---
status: proposed
---

# 委派只做 spawn；额度按父会话计；子级档位只能收窄

M12 的委派只做 `spawn`（`fork` 见 ADR-0035）；`maxActiveSubagents` 按父会话计、不设全局池；`subagent.sandbox` 只能收窄不能放宽（放宽会绕过宿主的 `--allow-danger-full-access` 许可）；子会话的模型/内核失败以 `TOOL_IO_FAILED` 回到父，不读成「成功但没有正文」。

Considered options：设全局子代理池——否，单进程上界 4×8=32，先不引入第二套配额；允许子级放宽档位——否，那是提权通道；把子会话失败也当 `OK`——否，违反不变量 B；子级工具作用域当权限边界——否，`tools` 只是上下文经济选项，父的围栏档位仍是唯一约束。

Consequences：`ACTIVATION_LIMIT_REACHED` 在当前并发上限（8）下只有预置计数能触发，真实触发要等 M13 的目标轮次或并发上限变化；结果形状只给最终文本，产物清单与 `subagent/delivery-unavailable` 这类投递词留到壳。
