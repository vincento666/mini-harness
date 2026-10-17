# Tasks

每个任务是一个 red → green 单切片：先写失败测试，再写最小实现，跑绿后提交一次。seam 编号：① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒。提交粒度照 AGENTS.md：一个红绿循环一次提交，一个提交最多覆盖同一 seam 上相邻 3 个 task。

## 1. fixture 仓库与测试 helper（无红）

- [ ] 1.1 建 `tests/fixtures/repo/`：5 个 `.md`（含可搜的共同词）+ 一个可跑的小 pytest 工程（含一个必然失败用例）；验证 `uv run pytest tests/fixtures/repo -q` 退出码非 0 且失败用例被收集（seam ③ 的内容源）
- [ ] 1.2 在 `tests/paths.py` 加 fixture 仓库路径常量与 `copy_repo_to(tmp_path)` helper；验证一条测试断言复制后的目录含那 5 个 `.md` 且原仓库字节不变（seam ③）
- [ ] 1.3 把 `--sandbox`（三档、默认 `workspace-write`）与 `--yes` 加进 `build_parser`，非法档位以退出码 2 + `INVALID_ARGUMENT` 且无 session 日志；验证黑盒两条测试红→绿（seam ⑥）

## 2. 事件词表与类型常量（seam ④）

- [ ] 2.1 红：断言 `approval/request` 与 `approval/response` 在词表内且可被写出，`tool/cancelled` 与 `model/retry` 在词表外被拒；绿后验证（seam ④）
- [ ] 2.2 红：断言 `error/fence` 是合法类型且 payload 含 `turn_id`、`code`、被拒路径或工具名；绿后验证（seam ④）
- [ ] 2.3 红：断言 `outcome` / `stop_reason` / `error/fence.code` / `approval/response.decision` 四个词表常量与 `Literal` 类型别名同源，且词表外的值过不了 `EventRecord` 校验；绿后验证 `uv run mypy --strict src` 退出码 0（seam ④，ADR-0002 第 5 条）

## 3. SessionSettings 与 session/start 新字段（seam ①④⑥）

- [ ] 3.1 红：断言 `session/start.payload` 含 `sandbox`、`approval`、`tools`（五个工具名），且 payload 里没有 `schema_version`；绿后验证（seam ④⑥）
- [ ] 3.2 红：断言 `run_session` 收 `SessionSettings` 且 `session/start.payload` 由它派生（同一事实只写一遍）；绿后验证既有 seam ① 测试在新签名下全绿（seam ①，ADR-0002 第 1 条）
- [ ] 3.3 红：断言 `--sandbox read-only` 与 `--yes` 分别落到 payload 的 `sandbox` 与 `approval`（`ask` / `auto`）；绿后验证（seam ⑥④）

## 4. 围栏判定：规范化、边界、档位（seam ②）

- [ ] 4.1 红：断言路径键规范化（解析 junction/符号链接、Windows 大小写折叠），且同一文件两种写法得到同一键；绿后验证（seam ②）
- [ ] 4.2 红：断言 `write`/`edit` 目标解析后在工作区之外时判定为拒绝（`OUTSIDE_WORKSPACE`），且 `read`/`glob`/`grep` 不受边界约束；绿后验证（seam ②）
- [ ] 4.3 红：断言 `read-only` 档位拒绝 `write`/`edit`（`SANDBOX_DENIES_WRITE`）而放行读类工具；绿后验证（seam ②）
- [ ] 4.4 红：断言 `danger-full-access` 解除工作区边界但不放宽写前必读与 CAS；绿后验证（seam ②）
- [ ] 4.5 红：断言两轴独立——`danger-full-access` 仍默认问人、`--yes` 不使 `read-only` 的写变允许；绿后验证（seam ②）

## 5. approval 门（seam ②①）

- [ ] 5.1 红：注入返回 `APPROVED` 的假 approval 门，断言 `write`/`edit` 各产生一对 `approval/request` + `approval/response`（`decision: APPROVED`）且随后 `outcome: OK`；绿后验证（seam ②④）
- [ ] 5.2 红：断言 `read`/`glob`/`grep` 在任何档位下都不产生 `approval/*` 记录；绿后验证（seam ②④）
- [ ] 5.3 红：注入返回 `DENIED` 的门，断言 `outcome: DENIED_BY_APPROVAL` 与 `error/fence`（`APPROVAL_DENIED`）；绿后验证（seam ②④）
- [ ] 5.4 红：断言 stdin 非 tty 且未 `--yes` 时结论是 `UNAVAILABLE`（不挂起、不默认批准），`--yes` 时不产生任何 `approval/*` 记录；绿后验证（seam ②⑥）
- [ ] 5.5 红：断言 `approval/response.decision` 三个取值各有判据（批准 / 拒绝 / 不可问人）；绿后验证（seam ②④）

## 6. 文件工具契约：read（seam ③）

- [ ] 6.1 红：直接调 `read` 执行入口，断言 3 行文件整读返回 `1: `、`2: `、`3: ` 前缀；绿后验证（seam ③）
- [ ] 6.2 红：断言 `offset=2, limit=1` 只返回第 2 行且行号为 2；`offset` 或 `limit` 为 0 时是 `TOOL_ARGS_INVALID`；绿后验证（seam ③）
- [ ] 6.3 红：断言 `PATH_NOT_FOUND`、`IS_A_DIRECTORY`、`NOT_UTF8_TEXT` 三种失败都是结果且文件字节不变；绿后验证（seam ③）
- [ ] 6.4 红：断言 `read` 缺 `file_path` 时是 `TOOL_ARGS_INVALID` 且没有任何文件被触碰；绿后验证（seam ③）

## 7. 文件工具契约：write 与写前必读（seam ③）

- [ ] 7.1 红：断言目标不存在时 `write` 直接创建并返回 `OK`（含必要时创建父目录）；绿后验证（seam ③）
- [ ] 7.2 红：断言已存在文件在未 `read` 过时是 `WRITE_WITHOUT_READ` 且字节不变；绿后验证（seam ③）
- [ ] 7.3 红：断言同一派发上下文里先 `read`（`OK`）再 `write` 成功，且失败的 `read`（`PATH_NOT_FOUND`）不算读过；绿后验证（seam ③）
- [ ] 7.4 红：断言「已读过」判定跨 session 不继承（session B 直接 `write` session A 读过的文件是 `WRITE_WITHOUT_READ`），且同一日志前缀重算两次判定相同；绿后验证（seam ③④）

## 8. 文件工具契约：edit 与 CAS（seam ③）

- [ ] 8.1 红：断言 `old_string` 唯一匹配时替换成功且只替换这一处；绿后验证（seam ③）
- [ ] 8.2 红：断言 `old_string` 出现 0 次是 `EDIT_TARGET_NOT_FOUND`、出现多次且 `replace_all` 为假是 `EDIT_TARGET_AMBIGUOUS`，两者文件内容都不变；`replace_all` 为真时全部替换；绿后验证（seam ③）
- [ ] 8.3 红：断言读过之后文件被外部改动再 `edit` 是 `STALE_EDIT` 且不被改写；未 `read` 直接 `edit` 是 `WRITE_WITHOUT_READ`；绿后验证（seam ③）

## 9. 文件工具契约：glob 与 grep（seam ③）

- [ ] 9.1 红：断言 `glob` 对 fixture 仓库的 `**/*.md` 返回那 5 个相对路径、按修改时间从新到旧、不含目录、上限 100；无匹配是 `OK` 且说明没有匹配；绿后验证（seam ③）
- [ ] 9.2 红：断言 `grep` 返回 `文件:行号: 行内容` 形式的命中、上限 250、无匹配是 `OK`；绿后验证（seam ③）
- [ ] 9.3 红：断言非法正则是 `TOOL_ARGS_INVALID` 且内容含解析错误；绿后验证（seam ③）

## 10. 注册表接线与三段派发（seam ②③⑤⑥）

- [ ] 10.1 红：断言注册表非空且恰含五个工具，`ToolDefinition` 带参数校验模型与「会不会改动」标记，`ToolSpec` 仍是 `name` + `description`（`specs()` 显式映射）；绿后验证（seam ②，ADR-0002 第 2 条）
- [ ] 10.2 红：断言三段顺序——参数校验失败时不做围栏判定也不执行、围栏拒绝时不执行；绿后验证（seam ②）
- [ ] 10.3 红：断言 `NOT_IMPLEMENTED` 从词表移除且任何场景都不出现；未注册工具名仍是 `UNKNOWN_TOOL`；绿后验证（seam ②）
- [ ] 10.4 把既有 M1 场景断言搬家（design D9）：`tool_then_done` 与 `tool_then_exhaust` 的 `read a.md` 断言改为 `PATH_NOT_FOUND`，新增 `unknown_tool/turns.json` 场景守 `UNKNOWN_TOOL`；验证三条既有测试红→绿且 fixture 文件本身未被改（seam ⑤②⑥）

## 11. 折叠头部与 replay（seam ④⑥）

- [ ] 11.1 红：断言折叠头部的工具块取自 `session/start.payload.tools` 而非进程内注册表，且对同一前缀重算两次头部相同；绿后验证（seam ④）
- [ ] 11.2 红：断言 `minihns replay` 对注册了工具、含 `approval/*` 与 `error/fence` 的合法日志逐点重算相等、退出码 0；绿后验证既有「装配点之后的事件被篡改时 replay 仍通过」的测试仍绿（seam ⑥④，ADR-0002 第 7 条）
- [ ] 11.3 红：断言 replay 过程中没有任何 Provider 调用且工作区里没有任何文件被创建或修改；绿后验证（seam ⑥⑤③）

## 12. 围栏拒绝的终止序列（seam ①⑥）

- [ ] 12.1 红：断言围栏拒绝时事件顺序为 `tool/call` → 配对的 `tool/result` → `error/fence` → `turn/end`（`FENCE_DENIED`）→ `session/end`，且同回合剩余调用不被派发；绿后验证（seam ①④）
- [ ] 12.2 红：断言 `stop_reason` 词表含 `FENCE_DENIED` 且映射到退出码 3；绿后验证既有「每个停止原因都在退出码映射表里」的测试仍绿（seam ⑥①）
- [ ] 12.3 红：断言 M2 全部场景（含围栏拒绝与取消）都不写 `tool/cancelled`、也不写 `model/retry`；绿后验证（seam ①④）

## 13. CLI 黑盒集成（seam ⑥）

- [ ] 13.1 红：`--yes` 下跑一个「对 fixture 仓库的 5 个 `.md` 各 `read` + `edit`」的 mock 场景，断言退出码 0、5 个文件内容都被改、日志里没有任何 `approval/*`；绿后验证（seam ⑥③②）
- [ ] 13.2 红：断言越界写（目标在工作区之外）以退出码 3 结束、stderr 含被拒路径、日志里有 `error/fence`（`OUTSIDE_WORKSPACE`）；绿后验证（seam ⑥②）
- [ ] 13.3 红：断言 stdin 非 tty 且未 `--yes` 的写场景以退出码 3 结束、stderr 含 `APPROVAL_UNAVAILABLE`；绿后验证（seam ⑥②）
- [ ] 13.4 红：断言 `--sandbox read-only --yes` 的写场景以退出码 3 结束（`--yes` 不放宽档位）；绿后验证（seam ⑥②）
- [ ] 13.5 红：断言 M2 全部成功与失败场景没有任何 run 以 4 退出，且退出码非 2 的失败都有 `error/*` 事件；绿后验证（seam ⑥）
- [ ] 13.6 红：断言带 `--events jsonl` 时 stdout 与日志逐行相等（含 `approval/*` 与 `error/fence` 的 run）；绿后验证（seam ⑥④）
- [ ] 13.7 手动 smoke：在真实 tty 里跑一次会提问的 run，记录 `y` 与 `n` 两种回答的实际行为到 `docs/verification/m2-file-tools-and-fences-approval-smoke.md`；验证该文件存在且记录了两次退出码

## 14. 词表可达性与文档（seam ⑥④）

- [ ] 14.1 红：断言 `tool/result.outcome` 的 12 个取值、`error/fence.code` 的 4 个取值、`approval/response.decision` 的 3 个取值、`turn/end.stop_reason` 的 6 个取值每个都至少被一条测试断言到；绿后验证（seam ②④⑥，Active Lesson 1）
- [ ] 14.2 新开 `docs/adr/0003-m2-fence-simplifications.md`：照 `domain-modeling` 的 ADR-FORMAT 写「无 OS 级强制」「无 approval 提权通道」「管线塌成三段」「两轴不预设」四条简化与代价；验证文件存在且引用本 change（无红）
- [ ] 14.3 更新 `docs/CURRENT.md`（门禁实测与已知缺口）与 `docs/roadmap.md` 的 M2 行；验证两份文件里的 M2 判据与本 change 的 specs 一致（无红）

## 15. 收尾门禁

- [ ] 15.1 变异测试一轮：改坏围栏判定、CAS 判定、词表校验、`FENCE_DENIED` 映射、已读集合派生各一处，跑全量测试，把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/m2-file-tools-and-fences-mutation.md`；还原前先看 `git status`，还原后确认全绿与 `uv run mypy --strict src` 干净。判据：每个变异都被至少一条测试杀死，存活的补一条能杀死它的测试
- [ ] 15.2 Learning Gate：扫本轮证据（红过的测试、存活的变异、返工过的规格、踩过的工具坑），可复用教训写进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`；验证 `docs/lessons.md` 已更新或明确写了 `NO-PROMOTION`

## Workflow follow-up

- 人工审阅 proposal / specs / design / tasks 后再进入 apply（`/openspec-apply-change`），分支 `change/m2-file-tools-and-fences`。
- 实现完成后用 `code-review` 技能做 Standards / Spec 两轴审查（`openspec-verify-change` 未装）。
- 审查通过后合入 `main`，再 `openspec-archive-change` 把六份 delta 同步进 `openspec/specs/`，并跑一次 `agents-md-slim`。
