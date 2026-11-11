# Design

## Decisions

**D1 目录消息。** 目录写成 `user/message`，payload 为 `{content, source: "skill-catalog", incomplete: bool}`。内容模板照 DSH 的 `<system-reminder>`：`<available_skills>` 里每行 `` - `name`: description ``，结尾一句「目录只是摘要，先调用 `skill` 工具加载再行动」。不完整时在开头加一行警告；清空时内容明确「不要使用旧目录里的名字」。

**D2 指纹与状态。** `SkillCatalogState` 记住上次发出的指纹（模型可调 `(name, description)` 列表 + `complete`）与消息 seq。指纹变了或从未发过（且有模型可调技能或不完整）就追加一条替换。

**D3 注入点。** 每个 turn 的 `context/assembled` 之前调用 `refresh`（闭包：重新发现全局四根 + 子会话的 preset 层），必要时追加目录消息。第一个 turn 的目录消息落在段内第一条 `user/message` 之前（模型先看到目录，再看到任务）。工具改了技能文件后，下一 turn 就生效（每 turn 扫描，不需要 watcher）。

**D4 不完整与重试。** 每次观察都重新发现；不完整 → 发 `incomplete: true` 的目录（确认条目 + 警告）；下一次观察到完整 → 指纹变化（complete 参与指纹）→ 追加无警告的替换。不做 last-good：确认条目就是当前视图。

**D5 空目录退休。** 曾经发过目录、现在模型可调条目为空且完整 → 追加空目录消息（明确不要用旧名字）；从未发过且为空 → 什么都不发。

**D6 压缩后重建。** 若目录消息的 seq 落在某条 `compaction/summary` 的 `shadowed_range` 里，清空状态里的指纹，下一次装配重新注入。判据只看 shadowed_range，不新增事件。

**D7 命令面保持快照。** `/skills`、`/<技能名>`、host 命令面仍用 `settings.skills`（装配期快照）；与模型目录可能短暂不一致，记为 simplified（触发：命令面也需要实时视图时）。

**D8 子会话的刷新含 preset 层。** 子会话的 `refresh` 闭包重新发现全局四根，再按 preset 的 `skill_dirs` 合并；`complete` 取与。没有 refresh 的测试环境回落到 `settings.skills`。

## Risks

- **目录消息进历史会占 token**：替换是整套重发（DSH 同），技能多时成本线性；目录条目要截断描述。
- **每 turn 扫描四个根**：本地目录便宜，但网络盘会慢；先接受，watcher 仍不做。
- **文件夹测试**：现有判据大量断言头部有「可用技能」；要改成目录消息断言，避免漏改。
