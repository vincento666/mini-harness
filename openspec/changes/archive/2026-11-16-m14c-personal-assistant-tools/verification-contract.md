# M14c 验证契约（切片 1：plan）

**日期**：2026-11-16（第二版，按子代理复核修正）。M14c 共四片（`todo` / `plan` / `ask_user` / `present`），本契约只覆盖 `plan`；其余三片在各自 apply 前补契约。

## 目标

模型在改动工作区前先交出一份计划；**人批准前，任何可能写工作区的路径都不可用**（含子会话）。

## 可观察行为

1. `/plan` 与 `/plan off` 都写 `plan/mode`；`--resume` 与 `replay` 从日志恢复。
2. 计划模式 active 时，`write` / `edit` / `bash` / `subagent` 在**产生任何副作用之前**被拒绝，结果词 `DENIED_BY_PLAN` 且以固定前缀 `计划模式：` 开头；工作区文件不变。
3. `exit_plan_mode(plan)` 触发 `approval/request`，payload 含 `purpose: "plan-review"` 与计划正文；**只有 `APPROVED`** 把 `plan/mode` 置 `false`。
4. `DENIED` 或 `UNAVAILABLE`（含人关闭复核）保持 active，并把原因作为工具结果返回。
5. 批准后 `write` / `edit` / `bash` 恢复，按原有围栏与审批策略执行。
6. 含计划事件的日志 `replay` 逐点相等。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 进入/退出 | seam ①：`/plan` 与 `/plan off` 各一条，断言 `plan/mode` 事件值；seam ④：`fold_plan_mode` 取最后值 |
| 2 副作用前拦截 | seam ②：`write` / `edit` / `bash` / `subagent` 各一条，断言结果以 `计划模式：` 开头且**目标文件未创建/未修改** |
| 3 精确批准 + 正文 | seam ①：断言 `approval/request.payload["purpose"] == "plan-review"` 且 `plan` 正文等于提交内容；`APPROVED` 后 `active=false` |
| 4 拒绝/不可用保持 | seam ①：`DENIED` 与 `UNAVAILABLE` 各一条，断言 `active` 仍为 true，且随后 `write` 仍被拒 |
| 5 批准后恢复 | seam ①：批准后 `write` 成功，文件内容正确 |
| 6 回放相等 | seam ④：含 `plan/mode` 的日志 `replay` 逐点相等 |

## 坏法清单（变异种子）

1. 拦截点漏掉 `subagent`，子会话继承工具表写文件。
2. 先执行副作用再返回 `DENIED_BY_PLAN`（文件已变）。
3. 拒绝被当成批准（答案语义塌陷）。
4. `plan/mode` 只存内存，恢复后丢失。
5. `bash` 被漏掉，只有 `write` / `edit` 被拦。
6. 计划正文没进 `approval/request`，日志里查不到。

## 不验什么

- 本切片之外的 `todo` / `ask_user` / `present`（同 change 的另外三片）；
- 完整 plan-mode 状态机（pending selection、投影、客户端表现）；
- 计划质量的自动评分；
- host 侧对计划正文的渲染。

## 待裁决

已裁：计划期一律拒绝（含 `bash` 与 `subagent` 子会话）；批准复用 approval gate；计划正文放复核请求。


---

## 切片 2：todo（2026-11-17 补）

**目标**：模型用整表更新推进多步任务，进度可从日志恢复与回显。

**可观察行为**：`todo(items)` 成功 → `todo/updated {items}`，缺省 `status` 规范为 `pending`；`/todo` 打印投影；`segment/start` 清空投影；`segment/end` 保留。

**判据**：工具计数与结果；事件形状（含缺省规范）；`/todo` 空表与非空；投影清空/保留；快照接口。**坏法**：省略 `status` 导致 `/todo` KeyError；整表未替换；投影不随 segment 清空；事件缺失。

## 切片 3：ask_user

**目标**：模型能问一个普通问题，答案进日志并回给模型；问不到人不伪造。

**可观察行为**：`question/asked` → 答案 → `question/answered`；无答案返回 `QUESTION_UNAVAILABLE`；日志写不进返回 `TOOL_IO_FAILED`。**判据**：事件顺序、答案回传、不可用、写失败。**坏法**：先返回答案再写日志；把关闭当成批准；日志失败仍返回答案。

## 切片 4：present

**目标**：把工作区内产物交给壳。

**可观察行为**：合法路径 → `present/artifact {path, title}`；越界/缺失 → `PRESENT_INVALID_PATH`。**判据**：工作区内文件、已存在的工作区外文件、缺失文件。**坏法**：只检查存在不检查越界；目录被当成产物；事件路径为绝对路径。
