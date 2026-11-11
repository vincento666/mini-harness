# Tasks

## 1. 目录消息（seam ④）

- [ ] 1.1 目录渲染：`<available_skills>` 模板、描述截断、结尾「先加载再行动」
- [ ] 1.2 不完整目录：警告行 + `incomplete: true`；空且不完整也发
- [ ] 1.3 空目录退休：曾发过、现在为空且完整
- [ ] 1.4 指纹：模型可调 `(name, description)` + complete

## 2. 注入与刷新（seam ①）

- [ ] 2.1 `SkillCatalogState` + `refresh` 闭包；每 turn 装配前调用
- [ ] 2.2 首个 turn 注入、指纹不变不重复、变了追加替换
- [ ] 2.3 工具改技能文件后下一 turn 生效（每 turn 扫描）
- [ ] 2.4 压缩 shadowed_range 覆盖目录 seq → 重注入

## 3. 头部与子会话（seam ④⑦）

- [ ] 3.1 受保护头部移除技能块；`payload.skills` 保留为装配快照（审计/命令面）
- [ ] 3.2 子会话 refresh 含 preset 层；complete 取与

## 4. 收尾

- [ ] 4.1 真实端点：会话中途改技能文件，下一 turn 目录更新
- [ ] 4.2 UAT（人跑）
- [ ] 4.3 变异测试一轮
- [ ] 4.4 Learning Gate
- [ ] 4.5 对齐复核（十项）
