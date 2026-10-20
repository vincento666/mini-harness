# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-20（**M8 实现与四道门禁完成，收尾没跑**：分支 `change/m8-runtime-semantics-alignment`，tasks 1 至 7 组全勾、`openspec validate --all --strict` 9 过 0 失败；人手验收 8.1、变异轮 8.2、Learning Gate 8.3、`code-review`、归档都还没做。M3 的收尾记录留在下面）

## 进度

- **M1 / M2 / M3 / M4 完成并已归档**：分别在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`、`2026-10-18-m2-file-tools-and-fences/`、`2026-10-19-m3-bash-concurrency-timeout/`、`2026-10-18-m4-real-provider/`，tag `m1` / `m2` / `m3` / `m4`，merge commit `141e28c` / `d89a7c2` / `1d8e120` / **`d17e596`**（M3）。主规格现有 **8 个能力**，`openspec validate --all --strict` 8 过 0 失败（M3 后新增 `bash-tool` 6 条 Requirement；cli 7 / context-projection 8 / event-log 10 / fences 12 / file-tools 11 / provider 9 / turn-loop 13）。
- **M3 落地的东西**（change `m3-bash-concurrency-timeout`，分支 `change/m3-bash-concurrency-timeout`）：
  - `bash` 工具（`mutates=True`）：经平台 shell 执行、cwd 固定为工作区根、命令文本里的路径不解析（ADR-0008）；`timeout_seconds` 默认 30、上限 600，601 是 `TOOL_ARGS_INVALID` 且没有进程被启动；命令退出码非 0 仍是 `OK` 且 content 里有退出码；输出单一上限 16384 字节（stdout 与 stderr 合算）超限留固定标记 `[输出已截断]`；超时之后整棵进程树收掉（POSIX `start_new_session=True` + `killpg`，Windows `taskkill /T /F /PID`，ADR-0009）。
  - 派发段并发：同一回合的只读调用最多 8 个同时在跑，沾上「要改动」的排队串行；前缀每回合取样一次、整批共用；`tool/result` 按声明顺序落盘（第二个先完成也一样）。
  - 超时与取消落进词表：`ToolOutcome` 加 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`（16 值），新事件 `tool/cancelled`（payload 只有 `turn_id` 与 `tool_call_id`，不含命令输出）；超时塌成结果、回合继续，取消打断整个 session（`error/abort` + `turn/end(ABORTED)` + 退出码 5，ADR-0007）。模型请求超时 120 s 写进规格。
  - `approval/request` 改成提问之前落盘；写不进去就不问人。`error/fence` 的 payload 加 `path` 与 `raw_path`，`detail` 只面向人。
  - 测试 helper 收口：`tests/tool_harness.py` 的 `dispatch_call` / `dispatch_context` / `run_session_fixture` 收 `registry` 与 `approval_gate`，seam ① 的 run 形状收成一份。
  - CI：`.github/workflows/gates.yml` 落地，`windows-latest` + `ubuntu-latest` 两端各跑四道门禁、各判 95% 地板，不持任何 secret。
- **M3 的收尾门禁**：变异 12 条（10 条首轮被杀，T1 与 O1 存活并已各补一条判据，C2 判定 dud）→ `docs/verification/m3-bash-concurrency-timeout-mutation.md`；Learning Gate 收 L-027 至 L-030、关闭 L-018、补 L-019，**AGENTS.md 本轮不晋升** → `docs/lessons.md`。
- **M3 的收尾**：tasks 51/51 全勾（人手验收 8.1–8.2 于 2026-10-19 跑完，见下）。`code-review` 两轴已跑完：A 至 G 七条全修（10.1–10.7，其中 10.4 改的是规格、10.1 与 10.5 改的是实现），Standards 轴的判断项与两条规格 ↔ 实现的判断记账进 ADR-0002 第 18 至 29 条，提交纪律的三处措辞欠账记在同文件最后一节；人手验收跑出来的一条新缺口是第 30 条。delta 已合进 main specs（`697675c`），change 目录已移进 `openspec/changes/archive/2026-10-19-m3-bash-concurrency-timeout/`，merge 进 `main` 是 `d17e596`，tag `m3`。**`agents-md-slim` 已跑**：三处精简（coverage 三步的注释与「覆盖率纪律」重复、ruff 例外的规则名解释是 `pyproject.toml` 里读得到的、handoff 那句写死的「38 条」会随决策增加失真），没有结构性可删项，AGENTS.md 本轮同样没有晋升新规则。M3 到此结束。
- **M8 落地的东西**（change `m8-runtime-semantics-alignment`，分支 `change/m8-runtime-semantics-alignment`，ADR-0011 / 0012 / 0013 的语义转向）：
  - **取消不再掀翻批次**：取消置位之后没轮到派发的声明调用，各落一对记录——`tool/call` 加一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`，不配 `tool/cancelled`（「被打断」预设它开始过）。`ToolOutcome` 从 16 值变 18 值。
  - **`tool/result` 在产生时落盘**：落盘顺序从「声明顺序」改成「完成顺序」，批次末的缓冲整段删掉。turn-loop 主规格里「工具调用与结果按声明顺序落盘」那条 Requirement 已 REMOVED，换成「工具结果在产生时落盘」。
  - **闭合是读方派生**：`tool/call` 没有配对结果时，`events/fold.py` 派生一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息，排在它该在的位置（未配对的先闭合，再轮到它之后的那条消息）。不落盘、不新造事件类型、不自动重试；`TOOL_OUTCOME_UNKNOWN` 不在日志里。
  - 新增 seam ⑥ 硬杀黑盒两条：`test_a_hard_kill_leaves_no_half_written_line`（Windows `Popen.kill()`、Linux CI `SIGKILL`）与 `test_a_hard_killed_log_replays_without_appending`。
  - 中途门禁裁决（tasks 组 5 之前的已知红）：`test_every_tool_outcome_is_reachable` 从 2.1 红到 5.5，5.5 把观察源从 seam ② 扩到 seam ① 的取消批次与 seam ④ 的折叠之后转绿；每个中间提交都写明了「哪条判据红着、哪个 task 让它绿」。

## 门禁实测（Windows 本机）

| 门禁 | 实测 |
|---|---|
| 测试 | 232 passed / 2 skipped。skip 的两条：符号链接判据（本机不允许创建符号链接）、`test_sigint_in_a_real_subprocess_exits_with_five`（`skipif win32`，Linux 侧跑）。全量带覆盖率记账约 65 秒 |
| 覆盖率 | `coverage erase` → `coverage run -m pytest` → `coverage combine` → `coverage report --fail-under=95`：TOTAL **95%**（1162 语句 / 53 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `events/reader.py` 88% · `loop/turn_loop.py` 90% · `provider/openai_compat.py` 89% · `tools/bash_tools.py` 94% · `tools/file_tools.py` 96% · `tools/registry.py` 97% · `provider/mock.py` 98% · `tools/dispatch.py` 98% · `cli/main.py` 99% · 其余 100%（含 M8 改过的 `events/fold.py`） |
| 覆盖率（CI 两端，run #3 `81e268f`） | `coverage TOTAL (ubuntu-latest)` = **1136 语句 / 50 未覆盖 / 96%**；`coverage TOTAL (windows-latest)` = **1136 / 50 / 96%**。两端数字一模一样：D9 预期的「平台分支在两端各拉低一半」没有把总数拉开。本机那 50 行是哪 50 行已知（下一段）；Linux 端那 50 行的身份没读到——annotation 只带 `TOTAL` 行，要 `--show-missing` 才有清单 |
| 类型 | `mypy --strict` 干净，22 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（56 文件）；全仓没有一处 `# noqa` |
| CI | **`main` 首绿已跑**：merge commit `d17e596` 触发的 run [`39254753712`](https://github.com/vincento666/mini-harness/actions/runs/39254753712) 两个 job 都是 `completed / success`（`gates (ubuntu-latest)`、`gates (windows-latest)`）——`gates.yml` 现在在 `main` 上了，推 `main` 会触发 run。change 分支上的四次（`d681ec6` / `2b9e044` / `81e268f` / `d249979` / `298f582`）也都是 `completed / success`，ubuntu 约 57 s、windows 约 99 s。推送走本机代理：`GIT_SSH_COMMAND='ssh -o "ProxyCommand=C:/PROGRA~1/Git/mingw64/bin/connect.exe -H 127.0.0.1:7897 %h %p"'`。两端的 `TOTAL` 由 workflow 那一步写进步骤摘要与一条 annotation，但 run 日志与 annotation API 都要鉴权（实测 403 / 空列表），数字要人从 run 页面贴回来（已贴，见上一行）。GitHub 另有一条提示：`ubuntu-latest` 自 2026-10-19 起迁移到 Ubuntu 26（[runner-images #14748](https://github.com/actions/runner-images/issues/14748)），绿都在迁移当天 |

53 条未覆盖行里绝大多数是回合循环里「日志写不进去」的分支（`turn_loop.py` 的 158、193–195、218–220、294–296、310、347、356–357、361、371、424、428、438、463、491、533、545 与 `dispatch.py` 的 74：approval 记录写不进日志时塌成 `TOOL_IO_FAILED`）。这一类在 seam ④ 直接判日志层，不在 seam ① 造场景去撞它——刻意没有为它们写判据，每个相关提交的信息里都写明了这一点。剩下的是平台分支与响应解析的形状分支：`bash_tools.py` 的 53–54、63（Windows 与 POSIX 各一半）、`file_tools.py` 的 128、130、133、160–161、203、`reader.py` 的 28–29、34、`openai_compat.py` 的 13 条、`cli/main.py` 的 216、254、`registry.py` 的 23、`mock.py` 的 67。要抬地板就补 `events/reader.py`、`provider/openai_compat.py`（响应解析里那些「形状不对」的分支）的判据，不要凑低价值测试。

## 待办与已知缺口

- **M3 的人手验收跑完**（tasks 8.1–8.2，2026-10-19 20:08–20:11，人在真终端跑三个 session，观察记进 `docs/verification/m3-bash-concurrency-timeout-manual.md`）：真事 `c25136a7…` 52 条记录 / 31.92 s / 6 回合，三次 `bash` 提问都问到并得到 `APPROVED`，`counts.txt` 落在工作区根，t5 两条 `read` 是 `call c1`、`call c2`、`result c1`、`result c2`（两条结果同一毫秒）——10.4 的「可以交错」在真 run 里出现。超时 `4a2da4bf…` 实测 **30.07 s** 塌成 `TOOL_TIMEOUT` + `tool/cancelled`，之后三个回合继续，进程树收干净且是模型自己用 `tasklist` / `Get-CimInstance` 查出来的。Ctrl-C `30eae257…` 11 条记录 / 7.51 s，`TOOL_CANCELLED` → `tool/cancelled` → `error/abort(ABORTED)` → `session/end(ABORTED)`。两格没有终端侧直接证据：退出码 5 是从日志加映射表读出的，「同一回合里没开始的调用也各有一条结果」那一回合没撞到。不进 CI。
- **Windows 的 Ctrl-C 黑盒不在 M3**：seam ① 注入 cancel 判据、seam ⑥ Linux 真实 SIGINT 黑盒、两端都跑得动的 seam ⑥ `bash` 超时黑盒（`test_a_bash_timeout_in_the_cli_is_a_result_word_and_the_run_continues`，`timeout_seconds: 1` + 一条不会自己停的命令）都有；Windows 真实控制台 Ctrl-C 没有判据，缺口与边界记在 `docs/verification/m3-bash-concurrency-timeout-manual.md`。ConPTY 路线本机走不通（`UpdateProcThreadAttribute` 恒返回 87），可用的替代形状是 `WriteConsoleInput` 投递 KEY_EVENT（M2 的 approval smoke 用过）。
- **Linux 侧的判据在 CI 上跑绿了，本机仍没跑过**：符号链接键规范化、真实 SIGINT 黑盒、`tests/test_turn_cancel.py` 的 POSIX `killpg` 那一半——run #1 / #2 的 `ubuntu-latest` job 绿就是它们绿的证据（那两条在 Linux 上不被 skip，95% 地板也在那一端单独判过）。本机这一半依旧未验证；junction 那一半本机跑过（`test_a_junction_key_resolves_to_its_target_without_privileges`）。
- **硬杀会吞掉已经完成的结果**（**M8 已关闭**）：M3 的形状是 `tool/result` 缓冲到批次结束才落盘，SIGKILL 落在批次中间时已经跑完的那几条结果不在盘上，日志留下「有 `tool/call` 没 `tool/result`」的前缀。M8 按 DSH 转向（ADR-0012）：结果在产生时落盘、落盘顺序是完成顺序，那条前缀由折叠派生闭合而不写进日志。判据两条落在 seam ⑥——`test_a_hard_kill_leaves_no_half_written_line`（真子进程、杀点由日志定位、每行独立可解析、没有 `session/end`）与 `test_a_hard_killed_log_replays_without_appending`（那份日志照样逐点重放、字节不变）。
- **协作式取消只做了一半**（M8 的已知边界，M10 补完）：取消置位之后派发段不再派发新调用（未派发的落 `ABORTED_BEFORE_DISPATCH`）、正在执行的调用被 `CancelledError` 打断并塌成 `TOOL_CANCELLED`、`bash` 的执行段自己把进程树收掉——但**工具体不观察取消信号**，打断靠外层 asyncio 取消它，工具内部没有「看到信号就自己停下来」的入口。补完它要等 M10 的派生信号与执行段立成缝（ADR-0013）。
- **两端覆盖率各报各的，不合并**：95% 地板在两个 runner 上各自判。平台分支在两端各拉低一半是已知形状（D9）。M3 实测：两端 `TOTAL` 都是 1136 / 50 / 96%，数字相同。
- **`bash` 的输出按 UTF-8 解码，非 UTF-8 的控制台输出碎在日志里**：人手验收实测到，cmd.exe 上 `ls` 不存在时写的是 GBK 字节，`tools/bash_tools.py:83` 的 `errors="replace"` 把 content 变成 34 个 U+FFFD。没有判据（判它要在判据里造一条产出非 UTF-8 字节的命令并断言中文可读），记进 `docs/adr/0002-deferred-refactors.md` 第 30 条，处理时点 M5 或 M6。
- **M3 闭合的三条旧缺口**（原来在本文件的「已知缺口」里）：`approval/*` 晚落盘（ADR-0002 第 9 条）、取消只在回合边界被看到（第 10 条）、`error/fence` 的路径只在自由文本里（第 11 条）。三条都有判据与落地形状，见 `openspec/changes/m3-bash-concurrency-timeout/design.md` 的 D12 / D5 / D13。
- 延后的重构与记账：`docs/adr/0002-deferred-refactors.md`。M3 收尾轮逐条改判：**已处理** 第 1（含剩的那一半）、6、9、10、11 条；**改判为长期形态** 第 8、12、16 条；**未处理推到 M5** 第 14、15 条（要等第二个 provider 或 REPL）；**未触发** 第 17 条；第 3 条（`_replay` 的扫描逻辑下沉）推到 M6 的 chat REPL。第 2、4、5、7 条 M2 已处理。
- **对齐走查与账本更正（2026-10-19，docs-only）**：新增 `docs/dsh-alignment.md`——17 根支柱逐条对照、三处真走岔、未落地与错位的四分类、以及一份**待裁决**的排期提案（M5–M7 各补原判据没覆盖的那一半；M8–M13 把九层做齐，围栏层做薄但把执行段立成缝；M14 的 OS 级强制排在 MVP 之外）。顺手更正四处过期账本：ADR-0008 正文的 `raw_path=args.target_path() or ""`（实现早已改成传 `None` + `judge_fence` 显式分支）、ADR-0001 第 6 条与 cli 主规格的 `error/replay` 措辞（它不在事件词表、从不进日志；例外落在「每个非零退出都有 `error/*`」那一侧，cli 主规格的退出码 Requirement 因此补了第三种例外）、`docs/roadmap.md` 写明决策 33 的 `scripts/acceptance.py` 已被「每里程碑一条人手验收」替代、AGENTS.md 的 handoff 那条加了「以 ADR 与 roadmap 为准」的指路标记。另澄清一条：`PROVIDER_ABORTED` **不是**「有词表值没判据」——它有两条 seam ⑤ 判据、适配器会产出，缺的只是内核侧的调用路径，本文件上面那条措辞本来就准确。
- **两阶段 MVP 裁决（2026-10-20）**：走查的排期提案成立，落档 **ADR-0010**（MVP 分两阶段、第三阶段加壳待规划、测试缝从六条扩到七条，新增 ⑦ 委派与目标）、**ADR-0011**（取消是回合级协作式事件，会话终止由入口决定；ADR-0007 已标 superseded）、**ADR-0012**（结果在产生时立刻落盘 + 闭合记录，见上条）、**ADR-0013**（管线加段 + 派生信号 + 执行段立成缝；ADR-0003 第 3 条作废）。`docs/roadmap.md` 的里程碑表已重排：执行顺序 **M1 → M2 → M4 → M3 → M8 → M5 → M9 → M6 → M7**（第一阶段）→ **M10 → M11 → M12 → M13 → M14 → M15**（第二阶段），下一个未完成的里程碑是 **M8** `m8-runtime-semantics-alignment`。新增 `GLOSSARY.md`：mini 的回合 ≡ DSH 的 step、会话开始记录 ≡ config header、事件流输出 ≡ 日志逐行镜像。**下一个 change 要改的是已经绿过的判据**：turn-loop 的「按声明顺序落盘」与 M3 变异里守它的那条。
- 变异测试记录：`docs/verification/m1-mutation.md`（两轮 18 条：16 杀，G 与 P 各换回一条判据）、`docs/verification/m2-file-tools-and-fences-mutation.md`（收尾轮 20 条 + 审查后抽查 4 条）、`docs/verification/m4-real-provider-mutation.md`（18 条：17 杀，E2 补三条判据后被杀）、`docs/verification/m3-bash-concurrency-timeout-mutation.md`（12 条：10 杀，T1 与 O1 补判据后被杀，C2 是 dud）。
- 手测清单：`docs/verification/m1-m2-manual-smoke.md`（11 个 CLI 黑盒场景一键跑完、`mismatches=0`）。M4 的人手验收是另一形状：`docs/verification/m4-real-provider-manual.md`，两个真实端点各一次，外加一次 402 的失败路径证据。M3 沿用后者的形状。
- 已知缺口（M3 之后仍在）：
  - **围栏不是安全边界**：没有 OS 级强制（ADR-0003 第 1 条），防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。`bash` 只受档位轴约束（ADR-0008）：命令文本里的路径不解析，所以越界轴对 `bash` 不适用。
  - **适配器只认 OpenAI 兼容的拼写**：`openai_compat.py` 只认 `choices[].message.tool_calls` 与 `usage.prompt_tokens` / `completion_tokens`，不读流式 SSE（ADR-0006 第 1 条）。
  - **`PROVIDER_ABORTED` 有词表值与判据、没有生产路径**：取消走回合边界的 `error/abort`（退出码 5），`src` 里没有「取消置位后再调 `generate()`」的地方。
  - **`Usage` 只落进日志、不参与预算**：不变量 D 的窗口预算与 `CONTEXT_WINDOW_EXCEEDED` 还不存在——**M5 的活**（`docs/roadmap.md`）。
  - **CAS 只比「读到的窗口」**：窗口之外的改动不触发 `STALE_EDIT`；取舍与收紧办法记在 `docs/adr/0004-cas-compares-the-read-window.md`。
- ADR 现有十三份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`（记账，M3 改判见上）、`0003-m2-fence-simplifications.md`（**partially superseded by ADR-0013**：第 3 条作废，其余有效）、`0004-cas-compares-the-read-window.md`、`0005-m4-before-m3.md`（M4 换到 M3 之前）、`0006-m4-provider-simplifications.md`、`0007-ctrl-c-cancels-the-session.md`（**superseded by ADR-0011**）、`0008-bash-is-fenced-by-the-sandbox-level-only.md`、`0009-bash-runs-through-the-platform-shell.md`（进程树终止手段，与 fences 主规格「MUST NOT 依赖 job object」的区分）、`0010-two-phase-mvp-and-seventh-seam.md`、`0011-cancel-is-a-turn-level-cooperative-event.md`、`0012-tool-results-are-logged-as-they-happen.md`、`0013-tool-pipeline-gains-stages-and-a-runner-seam.md`。
- 门禁判据此前**只在 Windows 上跑绿过**；M3 把跨平台对齐与 CI 矩阵做成了工作流，但首绿要等人推送（`docs/roadmap.md` 的「跨平台与 CI 排在哪儿」；换序见 ADR-0005）。CI 不持 API key：门禁只跑 mock 判据，真实 Provider 的 smoke 归人手验收。平台绑定点：路径规范化（大小写 / junction / 符号链接）、tty 检测、SIGINT 与进程树终止。
