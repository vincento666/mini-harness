# Proposal

## Why

`skill-invocation-policy` 把目录放在**受保护头部**、`session/start` 时定死：会话中途新增/删除/改描述都不会反映，不完整发现只警告一次。DSH 的目录是**持久的 user 角色消息**，每个 step 比对指纹、变了就追加完整替换；不完整时发布「确认条目 + 警告」，下一步重试。这是 ADR-0038 第一条简化的正面消除。

## DSH 对齐（十项里与本次相关的项）

**形状**：目录是一条 `user` 角色消息，payload 带来源（`skill-catalog`）与 `incomplete: true` 元数据；内容只含模型可调技能的 `name` + 截断后的 `description`，不含正文、路径、来源。

**机制**：第一个 `agent/pre-step` 注入初始目录（仅当 `skill` 工具可见且有模型可调技能或发现不完整）；之后每个 step 对「模型可调条目 + 完整性」算指纹，变了就追加一条完整替换；清空时追加空目录并明确「不要用旧名字」；不完整观察不缓存、下一步重试；完整后警告消失。压缩把历史目录消息折掉后，下一次完整快照重新建立。

**语义**：不完整时**确认条目 + 警告**（操作性读法，不保留严格 last-good）；目录只用于路由，正文仍由 `skill` 工具按需加载。

## 与 mini 现状的差异（本 change 要消除的）

| 面 | mini 现状 | DSH | 本 change |
|---|---|---|---|
| 目录位置 | 受保护头部 | user 角色消息 | 改为日志里的 `user/message`（`source: "skill-catalog"`） |
| 更新 | 装配期一次 | 每个 step 指纹替换 | 每个 turn 装配前重扫 + 指纹 |
| 不完整 | 只警告一次 | 每次观察都带警告、重试 | 每次装配重新观察 |
| 清空 | 头部消失 | 显式空目录退休旧名字 | 追加空目录消息 |
| 压缩 | 无 | 目录被折掉后重建 | 检测 shadowed 范围并重注入 |

## Capabilities

### Modified Capabilities

- `skills`：目录从「启动头部清单」改为「持久 user 消息 + 指纹替换 + 不完整重试 + 空目录退休」。

## Impact

- 代码：`skills.py`（目录渲染/指纹）、`loop/turn_loop.py`（每 turn 注入点与状态）、`events/fold.py`（头部移除技能块）、`session/assembly.py`（刷新闭包）、`tools/subagent.py`（子会话的刷新闭包含 preset 层）。
- 测试：seam ①④⑥⑦；头部判据改成目录消息判据。
- 非目标：命令面（`/skills`）仍用装配期快照（记 simplified）；watcher 仍不做（每 turn 扫描代替）。
