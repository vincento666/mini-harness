# Design

## D1 计划状态只记日志

`plan/mode` = `{active: boolean}`，整值替换、只追加。`fold_plan_mode(events)` 返回最后一条的值，缺省 `false`。`--resume` 与 `replay` 都从日志取，不做内存单例。

## D2 拦截在 dispatch，不在提示词

计划模式 active 时，`write` / `edit` / `bash` 在派发前被拒，结果词 `DENIED_BY_PLAN`，内容说明「先提交计划并获批准」。`exit_plan_mode` 不受拦截。批准后 active=false，恢复原有围栏与审批策略。

**取舍**：bash 的只读命令也会被拒（用户已裁决「计划期全部拒绝」）。理由是 bash 可用重定向写文件，放行等于没拦。`subagent` 一并拦：它标记为无副作用，但子会话继承父的工具表，不拦就是一条绕过路径（子代理复核时发现）。

## D3 批准复用 approval gate

`exit_plan_mode(plan)` 触发一次 `approval/request`，payload 增加 `purpose: "plan-review"` 与 `plan` 正文（这是计划正文唯一的持久化位置）。只有 `APPROVED` 把 `plan/mode` 置 false；`DENIED` / `UNAVAILABLE` 保持 active，并把原因作为工具结果返回。人关闭复核按 `UNAVAILABLE` 处理，模型被明确告知「仍在计划模式」。

## D4 todo 是整表替换

`todo/updated {items: [{id, text, status}]}`，`status ∈ pending|in_progress|completed`。工具 `todo` 支持 add / update / complete；每次写整表（与 DSH 的 todo 同形），折叠取最后一张表。`/todo` 只打印，不改表。

## D5 ask_user 不是审批

`ask_user(question, options?)` 落 `question/asked`，人的回答落 `question/answered`，答案作为工具结果返回。与 approval 的区别：没有「批准/拒绝」语义，不改变任何状态；超时或问不到人返回 `QUESTION_UNAVAILABLE`，不伪造答案。

## D6 present 只交路径与标题

`present(path, title)` 校验路径在工作区内且存在，落 `present/artifact {path, title}`；CLI 打印「产物：<path>」，host 以后消费该事件渲染。越界或不存在返回 `PRESENT_INVALID_PATH`。

## 风险

- 事件词表 +5，fold 与 replay 要各自加分支；
- 计划期 bash 全拒可能挡住只读排查（已裁决接受）；
- host 命令面与 CLI 共用解析，避免两套 `/plan` 语义。

## 测试与 seam

- seam ①：plan 进入/退出、批准后恢复、拒绝保持；
- seam ②：`DENIED_BY_PLAN`、`todo` 整表、`present` 越界、`ask_user` 超时；
- seam ④：五个新事件的 fold 与 replay 相等；
- seam ⑥：`/todo`、`/plan`、`/plan off` 黑盒各一条。
