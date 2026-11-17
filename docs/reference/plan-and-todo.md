# plan 与 todo：把计划与进度放进日志（M14c 底稿）

**定位**：M14c 的实现笔记，不是规格；已落成（`2026-11-16-m14c-personal-assistant-tools`）。规格见 `openspec/specs/assistant-tools/spec.md` 的「todos 投影」与 `plan` Requirement。

**一句话**：计划和待办都不写工作区文件；它们是日志事件，模型靠自己的工具调用历史看到，UI 与恢复靠投影重算。

## 1. 形状

| 事件 | 载荷 | 用途 |
|---|---|---|
| `plan/mode` | `{active: bool}` | 计划模式开关 |
| `approval/request` | `{purpose: "plan-review", plan: "..."}` | 计划正文与复核请求 |
| `todo/updated` | `{items: [{id, text, status}]}` | 整张待办表 |

`status` 只有 `pending` / `in_progress` / `completed`；缺省按 `pending` 落盘，避免下游读到缺字段。

## 2. 机制

**进入计划模式**：`/plan` 由壳写 `plan/mode {active: true}`；模型只读探索，`write` / `edit` / `bash` / `subagent` 在派发前被拒，结果词 `DENIED_BY_PLAN`，副作用不发生。

**提交计划**：`exit_plan_mode(plan)` 走审批复用路径，请求里带 `purpose=plan-review` 与正文；只有 `APPROVED` 才返回 `plan_exit=true`，回合循环随后写 `plan/mode {active: false}`。`DENIED` 与 `UNAVAILABLE` 保持 active，且工具结果文案区分「人拒绝」与「问不到人」。

**推进进度**：`todo(items)` 每次提交**整张表**；工具结果只回计数与一句确认，整表留在 tool call 参数里。回合循环把成功的调用落成 `todo/updated`，缺省字段在这里规范化。

**回显**：`todos` 投影单元按事件推进——`todo/updated` 整表替换，`segment/start` 清空，`segment/end` 保留；`GET /sessions/{id}/projections/todos` 给快照，SSE 在变化时推 `session/projection` 帧，增量 apply，不重算全量。

## 3. 决策与依据

| 决策 | 理由 | 记录 |
|---|---|---|
| 不写计划文件 | 文件与日志会形成两个真源；日志可回放、可审计 | M14c design D1 |
| 计划正文放 `approval/request` | 复核请求本身就是「计划被提交」的事实，不新增事件 | design D2 |
| 只有 `APPROVED` 翻转 | 把「计划通过」与「问不到人」分开，后者不能当成默许 | design D3 |
| todo 整表替换 | 删项与改状态都能表达；回放只取最后一张表 | design D4 |
| `segment/start` 清空投影 | DSH 的 `turn` 相当于 mini 的 `segment`；照搬 `turn/start` 会在多步中间抹掉表 | design D8 |
| 投影是纯函数 + 单元 | 快照与 CLI 共用一份规则；可丢弃、可重建 | design D7 |

## 4. 边界与已知缺口

- **没有读回工具**：模型靠 tool call 历史看表；上下文压缩后可能看不到，需靠模型主动重发或后续补读回；
- **计划正文不自动注入**：批准后不会作为独立消息塞进上下文，避免每轮 token 成本与前缀缓存破坏；
- **投影只服务 `todos`**：没有第二单元之前不建注册表发现机制；
- **`present` 的 headless 输出**仍是缺口，与本模块无关但同属 M14c 尾巴。

## 5. 出处

- `src/mini_harness/tools/assistant.py`：`todo`、`exit_plan_mode`、`present`；
- `src/mini_harness/tools/dispatch.py`：计划期四路拦截与审批复用；
- `src/mini_harness/events/projection.py`：`ProjectionUnit` 与 `todos`；
- `src/mini_harness/cli/host.py`：快照接口与 SSE 投影帧；
- `openspec/changes/archive/2026-11-16-m14c-personal-assistant-tools/`。
