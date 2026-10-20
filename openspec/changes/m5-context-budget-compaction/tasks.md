# Tasks

红绿纪律：一条判据先红、再绿，一次一个切片。下面每一组内部就是实现顺序；组与组之间不许水平切片（不许「先把所有测试写完再实现」）。

## 1. 词表与退出码先行（seam ②）

- [x] 1.1 红：`tests/test_event_vocabulary.py` 断言 `compaction/summary` 与 `error/context` 在事件词表内；`tests/test_vocabulary_reachability.py` 断言 `CONTEXT_WINDOW_EXCEEDED` 在 `STOP_REASONS` 里
- [x] 1.2 绿：`events/vocabulary.py` 加两个事件类型；`loop/turn_loop.py` 的 `StopReason` 加 `CONTEXT_WINDOW_EXCEEDED`（收 ADR-0002 第 5 条的剩余部分）
- [x] 1.3 红：`cli/main.py` 的 `STOP_REASONS_TO_EXIT_CODES` 缺 4 —— 断言 `exit_code_for` 对新值返回 4
- [x] 1.4 绿：加 `EXIT_CONTEXT_EXCEEDED = 4` 与映射

## 2. 预算读数与触发线（seam ①）

- [x] 2.1 红：触发线公式——默认参数（128000 / 8192）下是 54272；`W − O − 65536` 为负时是 0 而不是负数
- [x] 2.2 绿：新建 `src/mini_harness/context/budget.py`，`trigger_line(window, reserve)`
- [x] 2.3 红：估算 token——`content` 与 `tool_calls` 的 JSON 文本都算，逐条除以 4 向上取整再相加
- [x] 2.4 绿：`estimate_tokens(messages)`
- [x] 2.5 红：预算读数 = max(估算, 该前缀里 `model/response.usage.input_tokens` 的最大值)；`purpose` 为 `compaction` 的那次回复不参与校准；没有回报时等于估算；同一份前缀两次读数相同
- [x] 2.6 绿：`budget_reading(events, messages)`

## 3. 遮蔽范围与语法边界（seam ①）

- [ ] 3.1 红：尾部保留预算 `floor(W × 0.16)`；切点落在「assistant 消息 + 它的工具结果组」之外；范围不覆盖 `session/start`
- [ ] 3.2 绿：`shadowed_range(events, window)` 返回 `{start, end}` 或 `None`
- [ ] 3.3 红：保留尾部本身已超预算（无可遮蔽内容）时返回 `None`
- [ ] 3.4 绿：补那条分支

## 4. 折叠的读方规则（seam ④）

- [ ] 4.1 红：被 `shadowed_range` 覆盖的记录不产出消息；被遮蔽的 `tool/call` 不派生 `TOOL_OUTCOME_UNKNOWN` 闭合
- [ ] 4.2 绿：`events/fold.py` honor 遮蔽
- [ ] 4.3 红：摘要作为受保护头部之后的 `system` 消息；多条摘要按 `seq` 排列；不落盘
- [ ] 4.4 绿
- [ ] 4.5 红：`purpose` 为 `compaction` 的 `model/response` 不产出 assistant 消息；没有该标记的照常产出
- [ ] 4.6 绿
- [ ] 4.7 红：压缩过的折叠仍是确定性纯函数；同一份日志逐点重算与每条 `context/assembled` 逐字段相等
- [ ] 4.8 绿

## 5. 回合循环的压缩段（seam ①）

- [ ] 5.1 红：装配越线 → 调模型生成摘要 → 写一条 `compaction/summary`（在该点 `context/assembled` 之前，payload 五个字段齐全）→ 按新前缀重新折叠
- [ ] 5.2 绿：`turn_loop.py` 的装配步内加压缩段（`_compact_if_over_line`）
- [ ] 5.3 红：未越线的 run 里没有任何 `compaction/summary`；一次装配最多一次压缩
- [ ] 5.4 绿
- [ ] 5.5 红：压缩后读数仍超线 → `error/context` + `turn/end`（`CONTEXT_WINDOW_EXCEEDED`）+ `session/end`，该回合没有 `model/request` 与 `tool/call`
- [ ] 5.6 绿
- [ ] 5.7 红：取消信号已置位时不生成摘要、不写 `compaction/summary`、不写 `error/context`，收尾仍是 `ABORTED`
- [ ] 5.8 绿
- [ ] 5.9 红：摘要调用失败 → `error/model` + `PROVIDER_ERROR` + 退出码 1，且没有 `compaction/summary`
- [ ] 5.10 绿
- [ ] 5.11 红：provider 返回 `PROVIDER_CONTEXT_OVERFLOW` → 同一个溢出结果（`error/context`、退出码 4、没有 `error/model`）
- [ ] 5.12 绿

## 6. provider 侧的超限识别（seam ⑤）

- [ ] 6.1 红：假端点返回 400 且 `error.code` 为 `context_length_exceeded` → `code: PROVIDER_CONTEXT_OVERFLOW`，且没有任何 `model/retry`
- [ ] 6.2 绿：`provider/openai_compat.py` 的失败分类
- [ ] 6.3 红：400 且 `error.code` 是别的值 → 仍 `PROVIDER_HTTP_STATUS`
- [ ] 6.4 绿

## 7. CLI 参数、fixture 与黑盒（seam ⑥ 与 ②）

- [ ] 7.1 红：`--window 4000 --reserve 500` 进 `session/start` payload；`--window 0` 退出码 2、stderr 含 `INVALID_ARGUMENT`、不建日志
- [ ] 7.2 绿：`loop/settings.py` 加 `window` / `reserve`，`cli/main.py` 加两个参数与校验
- [ ] 7.3 红：小 `--window` 的黑盒 run 以退出码 4 收尾且日志里有 `error/context`
- [ ] 7.4 绿
- [ ] 7.5 红：发生过压缩的 session 日志 `minihns replay` 逐点通过（退出码 0、无 `REPLAY_MISMATCH`）
- [ ] 7.6 绿
- [ ] 7.7 新增 fixture 场景 `tests/fixtures/scenarios/compaction/turns.json`；`tests/test_vocabulary_reachability.py` 扩到新事件类型与新 `StopReason` 值

## 8. 收尾

- [ ] 8.1 人手验收：真工作区 + 真模型办一件真事，观察压缩有没有按时触发、溢出收尾长什么样，记进 `docs/verification/m5-context-budget-compaction-manual.md`（人手跑，agent 出 runbook 并读日志）
- [ ] 8.2 变异测试一轮：改坏触发线 / 尾部保留 / 语法边界 / 遮蔽 honor / 溢出判定各一处，记进 `docs/verification/m5-context-budget-compaction-mutation.md`，还原前先看 `git status`
- [ ] 8.3 Learning Gate：扫本轮证据写进 `docs/lessons.md`；**收件箱已到 15 条上限，先消化再收**
- [ ] 8.4 四道门禁按新顺序跑一遍（格式 → 风格 → 类型 → 测试与覆盖率）+ `openspec validate --all --strict`
- [ ] 8.5 ADR 落档：0015（遮蔽是一条替换记录）、0016（预算读数两个来源、两条溢出触发路径）、0017（压缩范围不覆盖 `session/start`、摘要调用带 `purpose` 标记且不进表层）；ADR-0002 追加「单条工具结果的剪枝记账到 M10」与「每回合全量重读日志」，并把指向 M5 的旧指针按 M5 的实际范围改判（那些「处理时点：M5」写于 M5 还是 REPL 的旧分期）
- [ ] 8.6 核对 `GLOSSARY.md` 的「遮蔽（shadowing）」条目并按 M5 的实际语义更正，补「触发线」「保留尾部」两个词；跑 `agents-md-slim`

`code-review` 两轴在 apply 之后跑；修出的问题回到本文件加第 9 组，编号写进提交信息。
