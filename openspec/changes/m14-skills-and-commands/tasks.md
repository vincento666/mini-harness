# Tasks

## 1. 发现与清单（seam ②④）

- [ ] 1.1 seam ②：`test_four_roots_are_discovered_in_rank_order`——四级根各放一个技能，清单按 `(rank, path)` 排序
- [ ] 1.2 seam ②④：`test_the_higher_priority_root_wins_a_duplicate_name`——同名技能只出现一次、高优先级胜出
- [ ] 1.3 seam ④：`test_the_header_carries_only_the_manifest`——`session/start.payload.skills` 有清单无正文；头部有名字与描述、没有正文
- [ ] 1.4 seam ④：`test_the_manifest_is_truncated_over_budget`——超过字符预算时截断并留 marker

## 2. skill 工具（seam ②）

- [ ] 2.1 seam ②：`test_the_skill_tool_loads_the_body`——`{name}` 返回正文，结果是一条 `tool/result`
- [ ] 2.2 seam ②：`test_an_unknown_skill_is_an_argument_error`——未知名字是 `TOOL_ARGS_INVALID`
- [ ] 2.3 seam ②：`test_the_skill_body_is_capped`——超过 32 KiB 截断并提示用 `read`

## 3. 命令面（seam ⑥）

- [ ] 3.1 seam ⑥：`test_chat_lists_skills`——`/skills` 打印清单并写 `command/run` + `command/done`，不开段
- [ ] 3.2 seam ⑥：`test_chat_loads_a_skill`——`/skill x` 打印正文、落两件套事件，不写 `user/message`、不开段
- [ ] 3.3 seam ⑥：`test_host_commands_match_the_cli`——`GET /commands` 与 `/skills` 同一份清单；`POST /commands` 与 `/skill` 同一份正文、同一条事件
- [ ] 3.4 seam ⑥：`test_an_unknown_command_is_rejected`——未知命令 400 / 本地提示，不落日志

## 4. preset persona（seam ②⑦）

- [ ] 4.1 seam ②：`test_persona_is_accepted_in_a_preset`——`persona` 是合法键，未知键仍然报错
- [ ] 4.2 seam ⑦：`test_the_child_header_carries_the_preset_persona`——子 `session/start.payload.preset_persona` 与头部都有人设；没有 persona 时不出现

## 5. 收尾四项

- [ ] 5.1 真实端点验收：一个项目技能被 `/skill` 加载后模型按正文回答
- [ ] 5.2 UAT 验收（人跑）：斜杠命令与 host 命令面各办一件真事
- [ ] 5.3 变异测试一轮：至少三条（顺序不排序、正文不落日志、persona 不注入）被杀
- [ ] 5.4 Learning Gate
- [ ] 5.5 DSH parity review：技能发现/清单注入/按需加载/命令面/preset persona 五项逐条对比，写 `docs/verification/m14-skills-and-commands-dsh-review.md`
