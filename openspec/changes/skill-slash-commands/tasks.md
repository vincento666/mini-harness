# Tasks

## 1. 解析与清单（seam ②）

- [x] 1.1 `execute_command` 支持直接技能名，返回与 `skill <name>` 相同的正文
- [x] 1.2 内置命令与技能同名时内置胜出；带多余参数是 handler 错误
- [x] 1.3 `command_catalog(skills)` 返回内置命令 + 技能命令（去重）

## 2. chat 壳（seam ⑥）

- [x] 2.1 `/<技能名>` 打印正文，落两件套，不开段
- [x] 2.2 `/help` 列出内置命令与当前会话的技能命令

## 3. host 壳（seam ⑥）

- [x] 3.1 `GET /commands?session_id=` 追加该会话的技能命令
- [x] 3.2 `POST /sessions/{id}/commands {name:"<技能名>"}` 与 `/<技能名>` 同一份正文

## 4. 端到端判据（seam ⑥）

- [x] 4.1 渐进式披露：第一轮上下文无正文；`skill` 调用后正文作为工具结果进来
- [x] 4.2 技能执行结果：模型按正文约束回答
- [ ] 4.3 收尾四项（真实端点 / UAT / 变异 / Learning）
