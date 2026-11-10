# Tasks

## 1. 配置与装配（seam ②）

- [x] 1.1 seam ②：`test_subagent_config_is_validated`——`[subagent]` 的未知键、`preset` 指向不存在的 id、`allowed_presets` 里有不存在的 id、`allowed_presets` 不含默认 preset、preset 里的未知工具名、重复/空 id，都是 `INVALID_ARGUMENT` 且不产生日志
- [x] 1.2 seam ②：`test_presets_are_carried_into_the_registry`——配置的 preset 表进到装配后的工具定义，`session/start.payload.tools` 不受影响

## 2. 工具与子会话（seam ⑦）

- [x] 2.1 seam ⑦：`test_no_preset_means_the_parent_composition`——没配 `[subagent]` 时子会话继承父工具表，派发照常
- [x] 2.2 seam ⑦：`test_a_preset_decides_the_child_tools`——默认 preset 生效，子会话里 preset 之外的工具是 `UNKNOWN_TOOL`；preset 给出父会话没有的工具时子会话有它，但沙箱仍会拒（能力≠授权）
- [x] 2.3 seam ⑦：`test_the_whitelist_exposes_an_enum`——有 `allowed_presets` 时工具 schema 的 `agent_preset` 恰是白名单；没有白名单时字段不出现
- [x] 2.4 seam ⑦：`test_an_unknown_preset_is_a_result`——默认 preset 指向不存在的 id 时是 `TOOL_ARGS_INVALID`，不建子会话
- [x] 2.5 seam ⑦：`test_the_tools_argument_is_gone`——`subagent` 的 schema 里没有 `tools`，传了也不生效（被 pydantic 拒）
- [x] 2.6 seam ⑦：`test_the_child_records_its_preset`——子 `session/start.payload.preset` 是选中的 id

## 3. 文档与兼容

- [x] 3.1 文档：`docs/reference/subagents.md` 的「工具来源」改成已落成的形状；DSH review 的对应行从 `simplified` 改 `aligned`
- [x] 3.2 破坏性变更：M12 的 spec/测试里所有 `subagent.tools` 的用法删掉（含 `test_the_tools_argument_restricts_the_child_registry`）

## 4. 收尾四项

- [ ] 4.1 真实端点验收：一个 preset 子代理 + 一个无 preset 子代理各跑一次
- [ ] 4.2 UAT 验收（人跑）：配 `[subagent]` 后模型只能在白名单里选，且没配 preset 时子代理照常工作
- [ ] 4.3 变异测试一轮：至少两条（把 preset 改成从父表取、去掉「无 preset 继承」）被杀
- [ ] 4.4 Learning Gate
