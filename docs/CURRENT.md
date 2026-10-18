# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-18（M4 已合入 `main` 并归档，tag `m4`；下一个里程碑是 M3）

## 进度

- **M1 完成并已归档**：change `m1-event-log-and-turn-loop` 已合入 `main`（merge commit `141e28c`），归档在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`，tag `m1`。
- **M2 完成并已归档**：change `m2-file-tools-and-fences` 已合入 `main`（merge commit `d89a7c2`），归档在 `openspec/changes/archive/2026-10-18-m2-file-tools-and-fences/`，tag `m2`。六份 delta 已同步进主规格：新增 29 条 Requirement、修改 9 条、移除 2 条；主规格现有 7 个能力（`openspec list --specs`：cli 6 / context-projection 8 / event-log 9 / fences 12 / file-tools 11 / provider 5 / turn-loop 9），`openspec validate --specs` 7 过 0 失败。
- **M2 的收尾门禁全跑完**：变异 20 条 + 审查后抽查 4 条、Learning Gate 收 L-016 至 L-020、`code-review` 两轴修掉两条最重的发现（tasks 第 16 节）、`agents-md-slim` 已跑（AGENTS.md 110 → 100 行）。
- M2 落地的东西：五个文件工具 `read` / `write` / `edit`（CAS）/ `glob` / `grep`；三段派发管线（校验 → 围栏 → 执行）；围栏判定（档位 → 工作区边界 → 要不要问人）；`approval/request` 与 `approval/response` 事件；`error/fence` 的四种 code；`FENCE_DENIED` → 退出码 3；`SessionSettings` 同时是 `run_session` 的入参与 `session/start.payload` 的来源。
- **M4 完成并已归档**：change `m4-real-provider` 已合入 `main`（merge commit `1d8e120`，分支上 11 个提交，`bad809d` 起），归档在 `openspec/changes/archive/2026-10-18-m4-real-provider/`，tag `m4`。四份 delta 已同步进主规格：新增 6 条 Requirement、修改 5 条、移除 1 条（被移除那条里「mock 路径 MUST NOT 发起网络请求」这条收窄后的约束落在「mock Provider 按 fixture 序列回复」的描述里）；主规格现有 7 个能力（`openspec list --specs`：cli 7 / context-projection 8 / event-log 9 / fences 12 / file-tools 11 / provider 9 / turn-loop 9），`openspec validate --specs` 7 过 0 失败。落地的东西：`ToolSpec` 带上从派发侧 pydantic 模型派生的参数 JSON Schema；`provider/openai_compat.py` 一个适配器（httpx、非流式、429/5xx 重试一次、请求体显式 `parallel_tool_calls: true`、超时与传输层失败塌成 `PROVIDER_TIMEOUT` / `PROVIDER_TRANSPORT`、取消信号已置位就不发请求也不发重试、`trust_env=False`）；重试事实由 `ProviderAttempt` 带回、由回合循环写成 `model/retry`（provider 不碰日志，不变量 A）；CLI 的 `--provider openai` 与 `--base-url` / `--model` / `--api-key-env`，密钥只走变量名。词表新增 `model/retry`，provider 失败 code 词表六值。变异 18 条：17 条首轮被杀，存活的 E2（把 `except httpx.HTTPError` 收窄成 `ConnectError`）补三条判据后被杀（`docs/verification/m4-real-provider-mutation.md`）。
- **M4 的 `code-review` 两轴跑完**（fixed point `main`）：Standards 5 条硬违反 + 5 条味道，Spec 11 条。人裁决「修四条硬的 + 补 `parallel_tool_calls`」→ tasks 第 9 节 9.1–9.5 已修（`--base-url` 形状校验、fixture 不得伪造 `model/retry`、三条 scenario 补判据、重试前再查取消、`parallel_tool_calls`）；其余记账：ADR-0006 补两条（决策 22 的指数退避没做、`AssistantTurn.attempts` 扩了决策 20 的形状），ADR-0002 补第 13 至 17 条（`generate` 两段同形、三条 `str | None` 结伴、「是 openai」四处判断、seam ① 桩两份、一次回合两次 HTTP 只有一条 `model/request`）。

## 门禁实测

| 门禁 | 实测 |
|---|---|
| 测试 | 176 passed / 1 skipped（skip 的是符号链接判据：本机不允许创建符号链接）；全量带覆盖率记账约 43 秒（seam ⑥ 的真实子进程比 M2 多） |
| 覆盖率 | `coverage erase` → `coverage run -m pytest` → `coverage combine`（合并 36 份 partial）后 TOTAL **96%**（950 语句 / 37 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `provider/openai_compat.py` 89% · `loop/turn_loop.py` 92% · `events/reader.py` 85% · `tools/file_tools.py` 96% · `tools/registry.py` 97% · `provider/mock.py` 98% · `cli/main.py` 99% · 其余 100% |
| 类型 | `mypy --strict` 干净，21 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（52 文件）；全仓没有一处 `# noqa` |

要再抬覆盖率地板，补 `events/reader.py`、`provider/openai_compat.py`（未覆盖的是响应解析里那些「形状不对」的分支）与 `loop/turn_loop.py` 的判据，不要凑低价值测试。

## 待办与已知缺口

- **M4 的人手验收跑通了两个端点**：本地 8300 session `bd7dd019bb2a42cea1d0e11d564d9dc2`（退出码 0、五个回合、7308 tokens、t1 一轮两个 `tool_calls`）；DeepSeek session `eead6d7e2d15424da0fa12127b53978d`（退出码 0、三个回合、3965 tokens、4.0 s）。DeepSeek 第一次跑撞到账户余额不足：HTTP 402 塌成 `error/model`（`PROVIDER_HTTP_STATUS`）、退出码 1、没有 `model/retry`——这条留在记录里，它是失败路径的真实证据。两个端点的差异表与「哪儿别扭」在 `docs/verification/m4-real-provider-manual.md`。
- **M3 开工前的欠账分流跑完**（2026-10-18，两份独立分流对照后合并）。**挡 M3 判据的九条**：① `tool/cancelled` 在词表外，且四处断言它在表外（`events/vocabulary.py`、event-log 与 turn-loop 主规格、`tests/test_event_vocabulary.py`、`test_turn_loop.py` 那条「M2 不写 tool/cancelled」）② 派发段里没有取消与超时的落点 ③ `except OSError` 挡不住 `asyncio.TimeoutError`（不是 `OSError` 子类）与 `CancelledError`（`BaseException`）——不变量 B 第一次有真实逃逸路径 ④ `ToolOutcome` 的 14 个取值里没有超时/取消 ⑤ bash 的 `target_path()` 是 `None`、`or ""` 让 `path_key` 塌成工作区根，边界轴对 bash 恒真 ⑥ 每个调用派发前重读全日志前缀，并发下「同一份前缀得到同一判定」不成立 ⑦ 覆盖率地板只剩 1 个点余量（96% 对 95%），而平台分支在两个 runner 上各拉低一半 ⑧ 符号链接判据在 Linux 不再 skip、围栏的大小写折叠在 Linux 会为假 ⑨ 没有 CI，`origin/main` 落后 52 个提交。**M3 里必须裁决的**：Ctrl-C 语义（决策 15「Ctrl-C 写 `tool/cancelled` 并继续回合」与决策 29 的退出码 5 及现行 turn-loop 规格冲突）、模型调用超时（实现 30 s 对决策 15 的 120 s）、bash 落在围栏哪条轴上、超时后进程树怎么收（fences 主规格字面禁止 job object，roadmap 却预告它）、`error/fence` 的 payload 字段表、bash 的执行形状（shell / cwd / 命令退出码非 0 算哪个结果词）、输出上限、CI 矩阵与覆盖率地板策略。**测试 helper 收口是判据①的前置而不是可选项**：`tests/tool_harness.py` 硬编码 `file_tool_definitions()` 与 `_ApprovingGate()`，写不出「只注册 bash 的注册表」那条 seam ③ 判据。
- **M3 的三条前置裁决定稿**（2026-10-18，人裁决）。① **Ctrl-C 取消整个 session**：被打断的那个调用写 `tool/cancelled`，随后 `error/abort` + `turn/end(ABORTED)` + 退出码 5；「继续回合」只属于超时。**决策 15 被部分推翻**——保留「Ctrl-C 写 `tool/cancelled`」，作废「并继续回合」；冻结的 handoff 不编辑，权威更正处是 `docs/adr/0007-ctrl-c-cancels-the-session.md`。② **模型调用超时改回 120 s 并把数值写进规格**：实现现在是 `provider/openai_compat.py` 的 30 s，决策 15 锁的是 120 s，M3 是「超时」这个概念的归属里程碑。③ **bash 只受围栏的档位轴约束**、cwd 固定为工作区根、命令文本里的路径不解析：`docs/adr/0008-bash-is-fenced-by-the-sandbox-level-only.md`。**仍未裁决**：超时后怎么终止进程树（fences 主规格字面禁止 job object，`docs/roadmap.md` 却预告它）、CI runner 与覆盖率地板策略、bash 的执行形状（用不用 shell、命令退出码非 0 算哪个结果词、输出上限）。
- **下一个里程碑是 M3**（`m3-bash-concurrency-timeout`：`bash` 工具、并发派发、超时、平台层与 CI 矩阵）。执行顺序 M1 → M2 → M4 → **M3** → M5 → M6 → M7，编号不变、顺序换了；理由与代价见 `docs/adr/0005-m4-before-m3.md`。M4 原来那个阻塞项（`ToolSpec` 缺参数 schema）已在 tasks 2.1–2.3 解决。CI 不持 API key，真实 Provider 的 smoke 走人手验收（`docs/roadmap.md`）。
- **`code-review` 两轴已跑**（fixed point `main` = `134ae69`，22 提交）。两条最重的发现已在 tasks 第 16 节修掉：执行段的文件 I/O 失败塌成 `TOOL_IO_FAILED`（此前 `FileExistsError` 逃出管线，违反不变量 B）、`glob` / `grep` 搜索根是文件时改报 `NOT_A_DIRECTORY`（此前是标签与语义相反的 `IS_A_DIRECTORY`）。词表因此 14 值。已合入 `main`（merge commit `d89a7c2`）并归档在 `openspec/changes/archive/2026-10-18-m2-file-tools-and-fences/`；`agents-md-slim` 也已跑（AGENTS.md 110 → 100 行）。
- 延后的重构与记账：`docs/adr/0002-deferred-refactors.md`。第 1、2、4、5、7 条已处理（M2 落了 `SessionSettings`、`ToolDefinition` 与 `ToolSpec` 分叉、`Literal` 词表、工具名列表进 `session/start`）；第 1 条只剩「seam ②③ 里四处手搓 `SessionSettings`」这一半，连同第 3、6、8 条、M2 审查新增的第 9 至 12 条（`approval/*` 晚落盘、取消只在回合边界被看到、`error/fence` 的路径只在自由文本 `detail` 里、seam ②③ 的桩各留一份）、以及 M4 审查新增的第 13 至 17 条（`generate` 重试前后两段同形、`base_url`/`model`/`api_key_env` 三个 `str | None` 结伴、「这是 openai」四处判断、seam ① 的 provider 桩与 run helper 各两份、一次回合两次 HTTP 只有一条 `model/request`）留给 M3（第 14、15 条要等第二个 provider 或 REPL，那是 M5 的形状）。ADR 现有六份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`、`0003-m2-fence-simplifications.md`（M2 围栏的简化与代价）、`0004-cas-compares-the-read-window.md`（CAS 比的是读到的窗口）、`0005-m4-before-m3.md`（M4 换到 M3 之前：理由、代价、被否掉的三个选项）、`0006-m4-provider-simplifications.md`（provider 层六处简化，与 `trust_env=False` 的起因和代价）。
- 变异测试记录：M1 的在 `docs/verification/m1-mutation.md`（两轮共 18 条：16 条被杀，存活的 G 与 P 各换回一条判据）；M2 的在 `docs/verification/m2-file-tools-and-fences-mutation.md`（收尾轮 20 条 A 至 S，含 J 的跟进 J′：15 条被既有测试杀死，G / I / J′ 是 dud mutant，M 与 N 存活并已各补一条判据；审查修复后又跑 4 条抽查 T / U / V / W，全被杀死。同文档注 6 记了一条事实：`ToolResult` 是 dataclass，词表外的值在运行期不会被挡，靠 `mypy --strict` 与可达性判据守）。
- 手测清单：`docs/verification/m1-m2-manual-smoke.md`。11 个 CLI 黑盒场景一键跑完（实测 `mismatches=0`：退出码 0/1/2/3 各有场景）、`replay` 两条、外加只有真终端能做的 approval 按键与 Ctrl-C 两条。M3 的手测沿用它的形状（场景表 + 一键脚本 + `mismatches=0`）。M4 的人手验收是另一形状：`docs/verification/m4-real-provider-manual.md`，不进 CI。
- 已知缺口：
  - **符号链接 / junction 的键规范化在本机没跑过**：`tests/test_fences.py::test_a_symlink_key_resolves_to_its_target` 因「不允许创建符号链接」skip。大小写折叠与 `..` 折叠那两半有判据，符号链接这一半没有。
  - **Ctrl-C 只在进程内测过**：Windows 上没有 CTRL_C_EVENT 黑盒，`ABORTED` → 退出码 5 的真实信号路径没有黑盒覆盖。
  - **approval 的真实 tty smoke 跑通了，但按键是投递的**：`docs/verification/m2-file-tools-and-fences-approval-smoke.md` 记了两次退出码（`y` → 0、`n` → 3）；按键来自 `WriteConsoleInput` 的 KEY_EVENT，不是人手敲的键盘。ConPTY 路线在本机 `UpdateProcThreadAttribute` 恒返回 87，走不通。
  - **围栏不是安全边界**：没有 OS 级强制（ADR-0003 第 1 条），它防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。
  - **适配器只认 OpenAI 兼容的拼写**：`ToolSpec.parameters` 现在带 JSON Schema（M4 补的），但 `openai_compat.py` 只认 `choices[].message.tool_calls` 与 `usage.prompt_tokens` / `completion_tokens` 这套形状，也不读流式 SSE。只发 Anthropic 拼写或只支持流式的端点要新写一个适配器（ADR-0006 第 1 条）。
  - **`PROVIDER_ABORTED` 有词表值与判据、没有生产路径**：`src` 里没有任何地方会在取消置位后再调 `generate()`——取消走的是回合边界的 `error/abort`（退出码 5）。seam ⑤ 那条「信号已置位就不发请求」守的是适配器这一侧的契约。
  - **`Usage` 只落进日志、不参与预算**：真实端点上五个回合的输入 tokens 从 900 涨到 1702（`docs/verification/m4-real-provider-manual.md`），而不变量 D 的窗口预算与 `CONTEXT_WINDOW_EXCEEDED` 还不存在——**M5 的活**（`docs/roadmap.md` 的 M5 行；2026-10-18 的 M3 分流核实这条曾被误写成「M3 的活」）。
  - **CAS 只比「读到的窗口」**：窗口之外的改动不触发 `STALE_EDIT`——实测 `read` 用 `offset=1 limit=1` 读过第 1 行后把第 3 行改掉，`edit` 仍 `OK` 并改写文件。这一半既没有判据、也没有测试钉住现状行为；取舍与收紧办法记在 `docs/adr/0004-cas-compares-the-read-window.md`。
  - **`approval/*` 这一对在问完人之后才落盘**：人已回答而执行段抛异常或进程被杀时，日志里没有这一对事件。ADR-0002 第 9 条。
  - **取消信号只在回合边界被看到**：同一批 `tool_calls` 里第一个调用置位 cancel 后，第二个 `write` 仍被派发（`turn_loop` 只在 267 / 279 / 293 三处查 `cancel.is_set()`）。ADR-0002 第 10 条。
  - **`error/fence` 里被拒的路径只在自由文本 `detail` 里**：判据只能断言 `code`；形态还不统一——`OUTSIDE_WORKSPACE` 放解析后的键，`SANDBOX_DENIES_WRITE` 放未解析的 `raw_path`。ADR-0002 第 11 条。
- 门禁判据目前**只在 Windows 上跑绿过**，仓库没有 CI。跨平台对齐（Linux/macOS）与 CI 矩阵已裁决并入 M3，不单开里程碑——见 `docs/roadmap.md` 的「跨平台与 CI 排在哪儿」；换序之后（ADR-0005）它整体后移一个里程碑，且 CI 不持 API key：门禁只跑 mock 判据，真实 Provider 的 smoke 归人手验收。M2 的 seam ⑥ 判据同样只在 Windows 验证；平台绑定点只有路径规范化（大小写 / junction）、tty 检测、SIGINT 三处，围栏本身不做 OS 级强制所以天生可移植。
