# Tasks

每个任务是一个 red → green 单切片：先写失败测试，再写最小实现，跑绿后提交一次。seam 编号：① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒。

## 1. 工程骨架（无测试）

- [x] 1.1 建 `pyproject.toml`（`requires-python >= 3.12`、`src/mini_harness/` 布局、`minihns` console script、pydantic v2）与 `uv sync`，验证 `uv run minihns --help` 退出码 0 且打印 usage
- [x] 1.2 配 mypy strict 与 pytest + pytest-asyncio，验证 `uv run mypy --strict src` 退出码 0；此时 `uv run pytest` 因没有任何测试返回 pytest 的 no-tests 码 5，退出码 0 从 2.1 起才成立
- [x] 1.3 建 `tests/fixtures/scenarios/` 目录与一个最小 mock fixture（单条纯文本回复），验证该文件被 pytest 的 fixture 路径常量解析到

## 2. 事件日志追加（seam ④）

- [x] 2.1 红：断言一次追加写产出的每行含六个信封字段且 `schema_version == 1`；绿后验证该测试通过（seam ④）
- [x] 2.2 红：断言同一 session 内 `seq` 从 0 起严格递增 1；绿后验证（seam ④）
- [x] 2.3 红：断言已写入字节是最终日志文件的严格前缀（只追加不改写）；绿后验证（seam ④）
- [x] 2.4 红：断言 session 目录不存在时被创建、两次 run 得到两个不同 session id 与两个日志文件；绿后验证（seam ④）
- [x] 2.5 红：断言词表外的类型不会被写出、无法归类的事实落成 `error/internal`；绿后验证（seam ④）
- [x] 2.6 红：断言 session 目录不可写时返回 `LOG_WRITE_FAILED` 结果（退出码 1 的映射输入），不是未捕获异常；绿后验证（seam ④）

## 3. 折叠与受保护头部（seam ④）

- [x] 3.1 红：对固定事件序列折叠两次，断言结果逐字段相同（纯函数）；绿后验证（seam ④）
- [x] 3.2 红：断言折叠结果第一条是内置系统提示、其后按事件顺序保留对话体（含 assistant 与工具结果消息）；绿后验证（seam ④）
- [x] 3.3 红：断言 fixture 回复文本与内置系统提示相同时头部不被顶替；`--append-system-prompt` 的文本被追加且常量仍在最前；绿后验证（seam ④）
- [x] 3.4 红：断言 50 条对话事件全部被折入、没有截断也没有 `CONTEXT_WINDOW_EXCEEDED`；绿后验证（seam ④）
- [x] 3.5 红：冷启动（只给日志文件）逐点重算——每条 `context/assembled` 都等于其之前前缀的折叠结果；绿后验证（seam ④）

## 4. Provider 契约与 mock（seam ⑤）

- [x] 4.1 红：断言 mock Provider 只暴露 `generate(messages, tools, signal)` 并返回 `AssistantTurn{content, tool_calls, usage, finish_reason}`；绿后验证（seam ⑤）
- [x] 4.2 红：断言 fixture 序列被逐条回放（第 i 次调用返回第 i 条）；绿后验证（seam ⑤）
- [x] 4.3 红：断言 fixture 条目耗尽时产出 `PROVIDER_EXHAUSTED` 结果而不是异常；绿后验证（seam ⑤）
- [x] 4.4 红：断言 Provider 返回缺字段时产出 `PROVIDER_SCHEMA_INVALID` 结果而不是异常；绿后验证（seam ⑤）

## 5. 回合主循环（seam ①）

- [x] 5.1 红：单回合 happy path，断言事件类型序列恰为 `session/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`session/end`；绿后验证（seam ①）
- [x] 5.2 红：两回合场景，断言每个 `turn/end` 都在下一个 `turn/start` 之前、3 个回合对应 3 个不同 `turn_id` 且每回合恰一条 `turn/start`/`turn/end`；绿后验证（seam ①）
- [x] 5.3 红：断言 `tool_calls` 为空时 `stop_reason == MODEL_COMPLETED` 且不再有下一回合；绿后验证（seam ①）
- [x] 5.4 红：断言回合数达到 `--max-turns`（默认 8）时最后回合 `stop_reason == MAX_TURNS` 且 run 结果为成功；绿后验证（seam ①）
- [x] 5.5 红：断言注入取消信号后 `turn/end` 的 `stop_reason == ABORTED`、日志以 `session/end` 收尾、结果为取消（退出码 5 的映射输入）；绿后验证（seam ①）
- [x] 5.6 红：断言 Provider 失败时 `stop_reason == PROVIDER_ERROR`、写 `error/model`、结果为失败（退出码 1 的映射输入）；绿后验证（seam ①⑤）
- [x] 5.7 红：断言循环对 Provider 的全部调用都是 `generate` 且参数只有 messages/tools/signal；绿后验证（seam ①⑤）

## 6. 工具派发与空注册表（seam ②）

- [x] 6.1 红：断言 fixture 声明的每个工具调用都产出配对的 `tool/call` 与 `tool/result`，`outcome == UNKNOWN_TOOL`，且该回合正常写 `turn/end`；绿后验证（seam ②①）
- [x] 6.2 红：断言上一回合的 `tool/result` 出现在下一回合的 `context/assembled` 里；绿后验证（seam ②④）
- [x] 6.3 红：断言 `session/start` payload 记录 `workspace`（绝对路径）、`provider`、`max_turns`、`append_system_prompt`、`prompt`，且 payload 里没有 `schema_version`；绿后验证（seam ④⑥）

## 7. CLI：run（seam ⑥）

- [x] 7.1 红：`minihns run` 缺 `-p` 与 `-p ""` 都退出码 2、stderr 含 `INVALID_ARGUMENT`、没有 session 日志；绿后验证（seam ⑥）
- [x] 7.2 红：`--max-turns 0` 与 `--provider deepseek` 分别退出码 2 且 stderr 含 `INVALID_ARGUMENT` / `UNKNOWN_PROVIDER`；`--fixture` 指向非法 JSON 时退出码 2 且含 `FIXTURE_INVALID`；绿后验证（seam ⑥⑤）
- [x] 7.3 红：happy path `minihns run -p "任务" --provider mock --fixture <f>` 退出码 0、stdout 含 session id、`sessions/<id>.jsonl` 存在；绿后验证（seam ⑥）
- [x] 7.4 红：断言带 `--events jsonl` 时 stdout 的事件行数与日志行数相同且逐行解析后对象相等；绿后验证（seam ⑥④）
- [x] 7.5 红：断言环境里存在 `DEEPSEEK_API_KEY` 时日志全文与 stdout 都不含其值；绿后验证（seam ⑥④）

## 8. CLI：replay（seam ⑥）

- [x] 8.1 红：断言 `minihns replay <session-id>` 对每条 `context/assembled` 逐点重算都相等、退出码 0，且过程中没有 Provider 调用；绿后验证（seam ⑥④⑤）
- [x] 8.2 红：断言 replay 未知 session id 时退出码 2、stderr 含 `SESSION_NOT_FOUND` 与查找路径；绿后验证（seam ⑥）
- [x] 8.3 红：断言连续两次 replay 后被重放日志的字节数与内容都不变；绿后验证（seam ⑥④）

## 9. 集成与退出码表（seam ⑥，跨多任务）

- [x] 9.1 红：多回合 mock 场景（含一次工具调用与一次 fixture 耗尽）跑通，断言退出码分别为 0 与 1、日志含对应 `error/*`；绿后验证（seam ⑥①②⑤）
- [x] 9.2 红：断言 M1 全部场景（成功与失败）没有任何 run 以 3 或 4 退出；绿后验证（seam ⑥）
- [x] 9.3 跑 `uv run mypy --strict src` 与 `uv run pytest` 全绿，验证 M1 完成判据：mock 场景跑通、`replay` 输出与实时折叠一致
- [x] 9.4 把「明文 JSONL、`schema_version` 从 1 起、M1 不施加窗口预算、退出码 3/4 保留」四条简化写进 `docs/adr/`，验证 ADR 文件存在且引用本 change

## 10. 规格修订轮（用户裁决后的新增可观察行为）

- [x] 10.1 红：断言 `tool_calls` 非空且未达回合上限的回合 `turn/end.stop_reason == TOOL_CALLS`，且 `MODEL_COMPLETED` 只出现在模型不再要求继续的回合；绿后验证（seam ①）
- [x] 10.2 红：断言 `minihns replay` 对每条 `context/assembled` 逐点重算相等；当某条被人为篡改时 replay 产出 `error/replay`（`code: REPLAY_MISMATCH`）且退出码 1、被重放的日志不被改写；绿后验证（seam ⑥④）
- [x] 10.3 红：断言 `session/start` payload 含 `prompt` 原文且不含 `schema_version`，且折叠里用户 prompt 是头部后第一条 `user` 消息；绿后验证（seam ④⑥）
- [x] 10.4 覆盖性切片（无红，不是 red→green）：断言 `--provider mock` 缺 `--fixture` 时退出码 2、stderr 含 `INVALID_ARGUMENT`、没有 session 日志（行为在 7.x 已实现）（seam ⑥）
- [x] 10.5 变异测试收尾：跑一轮有效变异并记进 `docs/verification/m1-mutation.md`，`git checkout --` 还原后确认全绿与 `uv run mypy --strict src` 干净，并在 `AGENTS.md` 写下「每个里程碑收尾跑一轮变异测试并记录」

## 11. code-review 修复轮（两轴审查 + 用户裁决后的必修项）

- [x] 11.1 红：断言每条 `context/assembled` 的 payload 含 `turn_id` 且等于所属回合；绿后验证（seam ①④）
- [x] 11.2 红：日志文件在 session 中途变得不可写时 `EventLog.append` 返回 `LogWriteFailure`（`LOG_WRITE_FAILED`）而不是抛异常，回合以失败结果结束、CLI 退出码 1；绿后验证（seam ④①⑥）
- [x] 11.3 红：fixture 条目形状不合法（`[{"foo":1}]`）时退出码 2、stderr 含 `FIXTURE_INVALID`、session 日志数量不变；绿后验证（seam ⑤⑥）
- [x] 11.4 红：断言停止原因词表里每个值都在 CLI 的退出码映射表里，且 `TOOL_CALLS` 映射到 0；绿后验证（seam ⑥）
- [x] 11.5 红：日志里有坏行时 `read_events` 返回 `LogReadFailure`（`LOG_UNREADABLE`）而不是抛异常，`minihns replay` 以退出码 1 结束；绿后验证（seam ④⑥）
- [x] 11.6 红：带 UTF-8 BOM 的 fixture 能跑通（退出码 0）；绿后验证（seam ⑤⑥）
- [x] 11.7 红：装配点之后的事件被篡改时 replay 仍然通过（折叠入参只从该点之前的事件派生）；绿后验证（seam ⑥④）
- [x] 11.8 红：取消被置位时写 `error/abort` 事件、`turn/end.stop_reason == ABORTED`、SIGINT 处理器把取消置位、CLI 映射到退出码 5；绿后验证（seam ①⑥）
- [x] 11.9 红：已注册工具在 M1 的派发结果是 `NOT_IMPLEMENTED` 而不是 `OK`；绿后验证（seam ②）
- [x] 11.10 把「replay 的失败只走 stderr 与退出码 1」这条例外写进 cli spec 正文与 `docs/adr/0001`（规格内部矛盾消解，无红）
- [x] 11.11 新开 `docs/adr/0002-deferred-refactors.md`：把审查记下的坏味道记账，写明 M2 一并处理；不动代码（无红）
- [x] 11.12 一致性收尾：proposal 的 Impact 与实现落点一致（`events/fold.py`）；`tests/test_fixture_paths.py` 的断言并进 seam ⑥ 后删除该文件；10.4 标注为覆盖性切片
- [ ] 11.13 变异测试一轮并追加进 `docs/verification/m1-mutation.md` 第 11 节：去掉 `append` 的 OSError 捕获、把 fixture 形状校验挪到 `EventLog.start` 之后、去掉 `context/assembled` 的 `turn_id`、`utf-8-sig` 改回 `utf-8`、replay 的入参派生改回读后一条事件；存活变异补测试杀死

## Workflow follow-up

- 人工审阅 proposal / specs / design / tasks 后再进入 apply（`/openspec-apply-change`）。
- 实现完成后：`openspec-verify-change` 不可用期间用 `code-review` 技能做 Standards / Spec 两轴审查。
- 审查通过后合入 `main`，再 `openspec-archive-change` 把五份 delta 同步进 `openspec/specs/`。
