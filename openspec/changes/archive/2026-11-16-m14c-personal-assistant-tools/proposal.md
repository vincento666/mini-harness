# Proposal

## Why

个人助理缺四件最基本的交互：结构化待办、改动前的计划、向人提问、把产物交出去。没有它们，多步任务只能靠长文本，模型想确认一件事只能借审批通道，产物生成后也没有"交付"这个动作。

## What Changes

- **`todo`**：会话级待办，整表替换写 `todo/updated`；CLI `/todo` 打印当前表。
- **`plan`**：`plan/mode`（active）日志事件 + `/plan` 进入、`/plan off` 退出；`exit_plan_mode(plan)` 经审批复核，只有批准才退出。计划期 `write`/`edit`/`bash` 一律拒绝（`DENIED_BY_PLAN`）。
- **`ask_user`**：普通提问（不是审批），问题与答案分别落 `question/asked` / `question/answered`，答案作为工具结果回给模型。
- **`present`**：把工作区内的产物交给壳，落 `present/artifact`（相对路径 + 标题）；CLI 打印可打开提示，host 后续渲染。
- CLI 与 host 共用同一命令面：`/todo`、`/plan`、`/plan off`。

## Capabilities

### New

- `assistant-tools`：四个工具与两个命令的事件、语义与判据。

### Modified

- `tool-pipeline`：计划期写类工具的拦截与 `DENIED_BY_PLAN`。
- `cli` / `host-api`：命令面新增 `/todo`、`/plan`。

## Impact

- 事件词表 +5：`plan/mode`、`todo/updated`、`question/asked`、`question/answered`、`present/artifact`。
- 工具注册表 +4；CLI 命令 +2。
- 折叠：`plan/mode` 取最后值；todo 取最后整表；question 取配对；present 不进模型上下文。

## 非目标

- 完整 plan-mode 状态机（pending selection、投影、客户端表现）——只做 active 布尔与精确批准。
- 多计划管理、跨会话计划库、富文本编辑器。
- host 侧真正渲染产物（本 change 只落事件与路径）。

## 验收

四片各自的契约判据全绿；`replay` 逐点相等；CLI 黑盒覆盖 `/todo` 与 `/plan`；真实端点一次多步任务用到 `todo` 与 `plan`。
