# Tasks

## 0. 前置

- [ ] 0.1 子代理复核验证契约（plan 切片五项检查），GAPS 先改契约

## 1. todo（seam ②④⑥）

- [x] 1.1 `todo` 工具：add / update / complete，整表写 `todo/updated`
- [x] 1.2 `fold` 取最后一张表；`replay` 相等
- [x] 1.3 `/todo` 命令：只打印，不写事件

## 2. plan（seam ①②④⑥）

- [x] 2.1 `plan/mode {active}` 事件 + `fold_plan_mode`；`--resume` 恢复
- [x] 2.2 `/plan` 与 `/plan off`；host 命令列表同步
- [x] 2.3 dispatch 拦截 `write` / `edit` / `bash` / `subagent` → `DENIED_BY_PLAN`（副作用前）
- [x] 2.4 `exit_plan_mode(plan)`：复用 approval，带 `purpose: "plan-review"` 与正文；仅批准置 false
- [x] 2.5 拒绝 / 不可用保持 active，结果说明原因
- [ ] 2.6 `/plan off` 写事件并退出
- [ ] 2.7 回放含 `plan/mode` 的日志逐点相等

## 3. ask_user（seam ①②④）

- [x] 3.1 `question/asked` / `question/answered` 事件与配对折叠
- [x] 3.2 超时 → `QUESTION_UNAVAILABLE`，不伪造答案（tty 门已接；非 tty 立即不可用）
- [x] 3.3 host 的问答门（挂起 future + 事件推送）

## 4. present（seam ②④）

- [x] 4.1 路径校验（工作区内且存在）→ `present/artifact`
- [x] 4.2 越界 / 不存在 → `PRESENT_INVALID_PATH`

## 6. 投影（2026-11-16 人裁：完整框架）

- [ ] 6.1 `ProjectionUnit` 协议 + `project(records, name)` 纯函数 + 单测
- [ ] 6.2 `todos` 单元：todo/updated 整表、segment/start 清空、segment/end 保留
- [ ] 6.3 host 快照接口 `GET /sessions/{id}/projections/todos`
- [ ] 6.4 SSE `session/projection` 帧（name / state_version / value）
- [ ] 6.5 CLI `/todo` 与快照共用同一个 project 函数

## 5. 收尾

- [ ] 5.1 真实端点：多步任务用到 `todo` 与 `plan`，批准后继续写
- [ ] 5.2 UAT（关键场次人跑：计划期拦截、批准后恢复）
- [ ] 5.3 变异测试一轮
- [ ] 5.4 Learning Gate
- [ ] 5.5 两轴 review（子代理）+ 对齐复核
