# Tasks

## 1. 渲染与解析（seam ②）

- [x] 1.1 `skill_content(skill, instruction)` 返回 XML 三段 + 指令；`skill` 工具复用
- [x] 1.2 `direct_skill(name, skills)`：内置名优先，返回技能或 None

## 2. chat 壳（seam ⑥）

- [x] 2.1 `/<技能名> 指令` 写两件套事件、把正文 + 指令作为 `user/message` 开段
- [x] 2.2 `/<技能名>` 与 `/skill <名字>` 仍不开段

## 3. host 壳（seam ⑥）

- [x] 3.1 `POST {name:"<技能名>", arguments:"<指令>"}` 返回 202，写两件套并投递消息
- [x] 3.2 段进行中投递时 `queued=true`（与消息队列同一条）

## 4. 收尾四项

- [x] 4.1 真实端点：`/tdd 帮我改个函数` 后模型按技能正文回答
- [x] 4.2 UAT（人跑）
- [x] 4.3 变异测试一轮
- [x] 4.4 Learning Gate
