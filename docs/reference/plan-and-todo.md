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

### 2.1 计划模式的状态机

```
              /plan                  exit_plan_mode(plan)
   普通 ───────────────▶ 计划中 ───────────────────▶ 待审批
    ▲                     │                            │
    │                     │ write/edit/bash/subagent    │ APPROVED
    │                     │ → DENIED_BY_PLAN            ▼
    └─────────────────────┴────────────────────────── 普通
                          DENIED / UNAVAILABLE
                          → 保持计划中
```

### 2.2 从事件到投影

```
日志（唯一真源）
  todo/updated ──┐
  segment/start ─┼─▶ project(records, "todos") ──▶ {name, state_version, value}
  segment/end ───┘                                      │
                                                        ├─▶ CLI /todo
                                                        ├─▶ GET /projections/todos
                                                        └─▶ SSE session/projection
```

### 2.3 三条路径

**进入计划模式**：`/plan` 由壳写 `plan/mode {active: true}`；模型只读探索，`write` / `edit` / `bash` / `subagent` 在派发前被拒，结果词 `DENIED_BY_PLAN`，副作用不发生。

**提交计划**：`exit_plan_mode(plan)` 走审批复用路径，请求里带 `purpose=plan-review` 与正文；只有 `APPROVED` 才返回 `plan_exit=true`，回合循环随后写 `plan/mode {active: false}`。`DENIED` 与 `UNAVAILABLE` 保持 active，且工具结果文案区分「人拒绝」与「问不到人」。

**推进进度**：`todo(items)` 每次提交**整张表**；工具结果只回计数与一句确认，整表留在 tool call 参数里。回合循环把成功的调用落成 `todo/updated`，缺省字段在这里规范化。

**读回**：`get_todos()` 无入参，读 `todos` 投影（与 `/todo`、快照接口同值），不写事件。它补的是「被遮蔽后看不见表」：整表只活在工具历史里，剪枝或压缩一挡就没了。段首清空之后读回为空——段作用域，不跨段继承。

**读回的边界**：跨轮重交**不经过**读回——模型从自己的历史里看见上一轮 `todo` 的入参，直接重交；历史完整时是零次额外调用。段首之后投影为空，所以「先读回旧表、再重交」在当前工具下不成立。这不是缺口：DSH 的 `turn/start` 同样把投影归 `null`（`todo_index.ts:130`），表是**本轮的常备计划**，不是跨轮状态（design D8）。

**回显**：`todos` 投影单元按事件推进——`todo/updated` 整表替换，`segment/start` 清空，`segment/end` 保留；`GET /sessions/{id}/projections/todos` 给快照，SSE 在变化时推 `session/projection` 帧，增量 apply，不重算全量。

### 2.4 与段、轮的关系

| 词 | 在 mini 里 | 在 DSH 里 | 表的边界 |
|---|---|---|---|
| 回合 | 一次模型往返 | step | 不变 |
| 段 | 一条输入展开的那串回合 | turn | `segment/start` 清空 |
| 轮 | 一次目标驱动的段 | goal round（就是一次 admitted user-message turn） | 同段，清空 |

所以 goal 轮次与普通对话在表上没有区别：**每轮开头都是空表**。跨轮连续性不靠表——靠目标、工作区与（可能被压缩的）历史；表是「这一轮的常备计划」。详见 `docs/verification/m13-goal-rounds-dsh-review.md` D.7.2。

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

### 4.1 DSH 已实现、mini 未实现

- **计划提示注入**：DSH 在每个模型请求里带 `plan:policy` 段；mini 不注入，模型靠工具历史与命令结果理解计划状态。
- **待决选择与步边界**：DSH 的 `plan/mode` 是 turn-enclosed 事件，用户选择先 pending，等下一个 pre-step 追加；mini 在命令执行时立即写日志，没有 pending 状态。
- **todo 的部署配置**：DSH 要求 `allowParallelInProgress` 必填，并校验空内容、重复内容与多余字段；mini 没有这两个开关与校验。
- **todo 的结果形状**：两边给模型看的都是计数文本。DSH 的结构化输出是 `{todos, counts}`，但模型可见的是 `render` 出来的那一句计数（`todo_index.ts:159-182`），整表只留在调用入参与 `todo/write` 事件里；mini 同形（`已更新待办：…`）。
- **事件与条目形状**：DSH 是 `todo/write`、条目 `{content, status}`；mini 是 `todo/updated`、条目 `{id, text, status}`。

### 4.2 DSH 也未实现或明确不强制

- **计划模式本身是软引导**：DSH 的 plan mode 只注入提示，不阻止写操作；真正的限制由 sandbox 与 approval 各自执行。mini 选择在派发前硬拦四类工具，这是**比 DSH 更强的偏离**（ADR-0041）。
- **todo 的顺序与新鲜度**：DSH 把「保持列表最新」交给工具描述与模型，没有运行时强制。

### 4.3 mini 独有的简化代价

- 投影在 `segment/start` 清空，而日志仍保留最后一张表：新段里 `/todo` 为空，DSH 的 last-write-wins 不会这样；
- ~~没有读回工具，压缩后模型可能看不到表~~（M13 task 4.5 补 `get_todos`：读投影、不落事件、段首为空）；
- 计划正文不自动注入；
- 投影只服务 `todos`，没有第二单元。

## 5. 出处

- `src/mini_harness/tools/assistant.py`：`todo`、`exit_plan_mode`、`present`；
- `src/mini_harness/tools/dispatch.py`：计划期四路拦截与审批复用；
- `src/mini_harness/events/projection.py`：`ProjectionUnit` 与 `todos`；
- `src/mini_harness/cli/host.py`：快照接口与 SSE 投影帧；
- `openspec/changes/archive/2026-11-16-m14c-personal-assistant-tools/`；
- DSH `packages/plan/`、`packages/todo/tool-todo/`、`docs/subsystems/plan.md`，commit `47f9438`。
