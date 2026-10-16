# Tasks

每个任务是一个 red → green 单切片：先写失败测试，再写最小实现，跑绿后提交一次。seam 编号：① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒。

## 1. 工程骨架（无测试）

- [ ] 1.1 建 `pyproject.toml`（`requires-python >= 3.12`、`src/mini_harness/` 布局、`minihns` console script、pydantic v2）与 `uv sync`，验证 `uv run minihns --help` 退出码 0 且打印 usage
- [ ] 1.2 配 mypy strict 与 pytest + pytest-asyncio，验证 `uv run mypy --strict src` 与 `uv run pytest`（此时 0 个测试）都退出码 0
- [ ] 1.3 建 `tests/fixtures/scenarios/` 目录与一个最小 mock fixture（单条纯文本回复），验证该文件被 pytest 的 fixture 路径常量解析到

## 2. 事件日志追加（seam ④）

- [ ] 2.1 红：断言一次追加写产出的每行含六个信封字段且 `schema_version == 1`；绿后验证该测试通过（seam ④）
- [ ] 2.2 红：断言同一 session 内 `seq` 从 0 起严格递增 1；绿后验证（seam ④）
- [ ] 2.3 红：断言已写入字节是最终日志文件的严格前缀（只追加不改写）；绿后验证（seam ④）
- [ ] 2.4 红：断言 session 目录不存在时被创建、两次 run 得到两个不同 session id 与两个日志文件；绿后验证（seam ④）
- [ ] 2.5 红：断言词表外的类型不会被写出、无法归类的事实落成 `error/internal`；绿后验证（seam ④）
- [ ] 2.6 红：断言 session 目录不可写时返回 `LOG_WRITE_FAILED` 结果（退出码 1 的映射输入），不是未捕获异常；绿后验证（seam ④）

## 3. 折叠与受保护头部（seam ④）

- [ ] 3.1 红：对固定事件序列折叠两次，断言结果逐字段相同（纯函数）；绿后验证（seam ④）
- [ ] 3.2 红：断言折叠结果第一条是内置系统提示、其后按事件顺序保留对话体（含 assistant 与工具结果消息）；绿后验证（seam ④）
- [ ] 3.3 红：断言 fixture 回复文本与内置系统提示相同时头部不被顶替；`--append-system-prompt` 的文本被追加且常量仍在最前；绿后验证（seam ④）
- [ ] 3.4 红：断言 50 条对话事件全部被折入、没有截断也没有 `CONTEXT_WINDOW_EXCEEDED`；绿后验证（seam ④）
- [ ] 3.5 红：冷启动（只给日志文件）折叠结果等于运行当时最后一条 `context/assembled` 的 payload；绿后验证（seam ④）

## 4. Provider 契约与 mock（seam ⑤）

- [ ] 4.1 红：断言 mock Provider 只暴露 `generate(messages, tools, signal)` 并返回 `AssistantTurn{content, tool_calls, usage, finish_reason}`；绿后验证（seam ⑤）
- [ ] 4.2 红：断言 fixture 序列被逐条回放（第 i 次调用返回第 i 条）；绿后验证（seam ⑤）
- [ ] 4.3 红：断言 fixture 条目耗尽时产出 `PROVIDER_EXHAUSTED` 结果而不是异常；绿后验证（seam ⑤）
- [ ] 4.4 红：断言 Provider 返回缺字段时产出 `PROVIDER_SCHEMA_INVALID` 结果而不是异常；绿后验证（seam ⑤）

## 5. 回合主循环（seam ①）

- [ ] 5.1 红：单回合 happy path，断言事件类型序列恰为 `session/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`session/end`；绿后验证（seam ①）
- [ ] 5.2 红：两回合场景，断言每个 `turn/end` 都在下一个 `turn/start` 之前、3 个回合对应 3 个不同 `turn_id` 且每回合恰一条 `turn/start`/`turn/end`；绿后验证（seam ①）
- [ ] 5.3 红：断言 `tool_calls` 为空时 `stop_reason == MODEL_COMPLETED` 且不再有下一回合；绿后验证（seam ①）
- [ ] 5.4 红：断言回合数达到 `--max-turns`（默认 8）时最后回合 `stop_reason == MAX_TURNS` 且 run 结果为成功；绿后验证（seam ①）
- [ ] 5.5 红：断言注入取消信号后 `turn/end` 的 `stop_reason == ABORTED`、日志以 `session/end` 收尾、结果为取消（退出码 5 的映射输入）；绿后验证（seam ①）
- [ ] 5.6 红：断言 Provider 失败时 `stop_reason == PROVIDER_ERROR`、写 `error/model`、结果为失败（退出码 1 的映射输入）；绿后验证（seam ①⑤）
- [ ] 5.7 红：断言循环对 Provider 的全部调用都是 `generate` 且参数只有 messages/tools/signal；绿后验证（seam ①⑤）

## 6. 工具派发与空注册表（seam ②）

- [ ] 6.1 红：断言 fixture 声明的每个工具调用都产出配对的 `tool/call` 与 `tool/result`，`outcome == UNKNOWN_TOOL`，且该回合正常写 `turn/end`；绿后验证（seam ②①）
- [ ] 6.2 红：断言上一回合的 `tool/result` 出现在下一回合的 `context/assembled` 里；绿后验证（seam ②④）
- [ ] 6.3 红：断言 `session/start` payload 记录 `workspace`（绝对路径）、`provider`、`max_turns`、`append_system_prompt`、`schema_version`；绿后验证（seam ④⑥）

## 7. CLI：run（seam ⑥）

- [ ] 7.1 红：`minihns run` 缺 `-p` 与 `-p ""` 都退出码 2、stderr 含 `INVALID_ARGUMENT`、没有 session 日志；绿后验证（seam ⑥）
- [ ] 7.2 红：`--max-turns 0` 与 `--provider deepseek` 分别退出码 2 且 stderr 含 `INVALID_ARGUMENT` / `UNKNOWN_PROVIDER`；`--fixture` 指向非法 JSON 时退出码 2 且含 `FIXTURE_INVALID`；绿后验证（seam ⑥⑤）
- [ ] 7.3 红：happy path `minihns run -p "任务" --provider mock --fixture <f>` 退出码 0、stdout 含 session id、`sessions/<id>.jsonl` 存在；绿后验证（seam ⑥）
- [ ] 7.4 红：断言带 `--events jsonl` 时 stdout 的事件行数与日志行数相同且逐行解析后对象相等；绿后验证（seam ⑥④）
- [ ] 7.5 红：断言环境里存在 `DEEPSEEK_API_KEY` 时日志全文与 stdout 都不含其值；绿后验证（seam ⑥④）

## 8. CLI：replay（seam ⑥）

- [ ] 8.1 红：断言 `minihns replay <session-id>` 打印的最终上下文与日志里最后一条 `context/assembled` 一致，且过程中没有 Provider 调用；绿后验证（seam ⑥④⑤）
- [ ] 8.2 红：断言 replay 未知 session id 时退出码 2、stderr 含 `SESSION_NOT_FOUND` 与查找路径；绿后验证（seam ⑥）
- [ ] 8.3 红：断言连续两次 replay 后被重放日志的字节数与内容都不变；绿后验证（seam ⑥④）

## 9. 集成与退出码表（seam ⑥，跨多任务）

- [ ] 9.1 红：多回合 mock 场景（含一次工具调用与一次 fixture 耗尽）跑通，断言退出码分别为 0 与 1、日志含对应 `error/*`；绿后验证（seam ⑥①②⑤）
- [ ] 9.2 红：断言 M1 全部场景（成功与失败）没有任何 run 以 3 或 4 退出；绿后验证（seam ⑥）
- [ ] 9.3 跑 `uv run mypy --strict src` 与 `uv run pytest` 全绿，验证 M1 完成判据：mock 场景跑通、`replay` 输出与实时折叠一致
- [ ] 9.4 把「明文 JSONL、`schema_version` 从 1 起、M1 不施加窗口预算、退出码 3/4 保留」四条简化写进 `docs/adr/`，验证 ADR 文件存在且引用本 change

## Workflow follow-up

- 人工审阅 proposal / specs / design / tasks 后再进入 apply（`/openspec-apply-change`）。
- 实现完成后：`openspec-verify-change` 不可用期间用 `code-review` 技能做 Standards / Spec 两轴审查。
- 审查通过后合入 `main`，再 `openspec-archive-change` 把五份 delta 同步进 `openspec/specs/`。
