# Tasks

## 1. 配置字段与类型

- [x] 1.1 seam ⑥：红判据 `test_compaction_ratio_accepts_float_and_int`——配置文件写 `compaction_retain_ratio = 0.10` 能读，写 `1` 也能读并归一成 float；实现 `SETTINGS_FIELDS` 的四个键与类型
- [x] 1.2 seam ⑥：红判据 `test_compaction_bool_is_not_a_number`——`compaction_retain_tokens = true` 是 `CONFIG_INVALID_VALUE`，不创建日志；实现 bool 拒绝
- [x] 1.3 seam ⑥：守卫——旧配置（没有四个键）逐点沿用默认，未知键仍报错

## 2. 预算函数参数化

- [x] 2.1 seam ④：红判据 `test_trigger_line_accepts_custom_ratio_and_headroom`——`(100000, 1000, ratio=.5, headroom=1000) == 50000`；实现 `trigger_line` 关键字参数
- [x] 2.2 seam ④：红判据 `test_retain_line_prefers_tokens_and_falls_back_to_ratio`——`retain_tokens=3000` 覆盖 ratio；`0` 时用 ratio
- [x] 2.3 seam ④：守卫——默认参数下既有 `trigger_line` / `retain_line` 判据逐点不变

## 3. 设置与 payload

- [x] 3.1 seam ①：红判据 `test_compaction_settings_reach_session_start_payload`——`SessionSettings` 四个字段进 payload，数值类型正确
- [x] 3.2 seam ⑥：红判据 `test_compaction_config_reaches_payload`——配置文件写四键，`minihns run` 的 `session/start` payload 与配置一致

## 4. 取值域与压缩行为

- [x] 4.1 seam ①：红判据 `test_compaction_ratio_out_of_range_fails_before_session`——`0` / `1.1` 退出码 2、无日志、含 `INVALID_ARGUMENT`
- [x] 4.2 seam ①：红判据 `test_compaction_negative_tokens_fails_before_session`——负数 headroom/retain_tokens 退出码 2、无日志
- [x] 4.3 seam ①：红判据 `test_shadowed_range_follows_retain_tokens`——同一日志下 `retain_tokens` 变小，遮蔽范围变大；`retain_tokens` 太大时无范围
- [x] 4.4 seam ④：守卫——旧日志 replay 仍逐点相等；缺四个字段不报错

## 5. 文档与 UAT

- [x] 5.1 文档：在 `docs/reference/tool-concurrency-and-context-economy.md` 与 `mini.config.toml` 示例里写清四个键与默认值
- [x] 5.2 UAT 骨架：`docs/verification/m10-compaction-parameters-uat.md`（propose 时立；人跑）

## 6. 收尾四项

- [x] 6.1 真实端点验收：真实 deepseek 下用一组自定义参数跑一次，记录 `[遮蔽] tokens 前/后` 与 `session/start` 四值，写进 `docs/verification/m10-compaction-parameters-real-endpoint.md`
- [x] 6.2 UAT 验收（人跑）：按 `docs/verification/m10-compaction-parameters-uat.md` 填观察表
- [x] 6.3 变异测试一轮：改坏「tokens 不覆盖 ratio」「ratio 边界放过 0」「payload 不记录」各一处，记进 `docs/verification/m10-compaction-parameters-mutation.md`
- [x] 6.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；M10 余下工具管线/并发另立 `m10-tool-pipeline-and-concurrency`。
