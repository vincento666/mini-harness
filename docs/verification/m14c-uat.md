# M14c 关键 UAT 记录

**日期**：2026-11-17
**授权**：人明确授权 agent 代跑关键场次（原规则要求人坐终端）。
**环境**：本机 macOS，`minihns host --http`，mock provider，`approval=auto`，`--allow-auto-approval`。

## 场次 1：计划期拦截

- 步骤：建会话 → `POST /commands {"name":"plan"}` → 发消息触发 `write a.txt`。
- 期望：`tool/result` 为 `DENIED_BY_PLAN`，`a.txt` 不存在。
- 结果：**PASS**（日志含 `DENIED_BY_PLAN`；`a.txt` 未创建）。

## 场次 2：退出计划后恢复

- 步骤：`POST /commands {"name":"plan","arguments":"off"}` → 再发消息触发 `write b.txt`。
- 期望：`tool/result` 为 `OK`，`b.txt` 内容为 `B\n`。
- 结果：**PASS**。

## 证据

- 会话日志：`.tmp/uat/sessions/<session_id>.jsonl`（本地，不入库）；
- 关键事件：`plan/mode {active:true}` → `tool/result DENIED_BY_PLAN` → `plan/mode {active:false}` → `tool/result OK`；
- 产物：`.tmp/uat/ws/b.txt` = `B\n`。

## 残余风险

- 批准路径（`exit_plan_mode` + `APPROVED`）未在 UAT 里走真实审批，只在单测与批次判据覆盖；
- UAT 使用 mock provider，不是真实端点；真实端点的计划行为待下一轮补。
