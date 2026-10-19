# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-19（M3 的实现与收尾门禁跑完，`code-review` 两轴的修复轮 10.1–10.8 跑完，分支 `change/m3-bash-concurrency-timeout` 上 34 个提交；**推送与 CI 首绿已跑（两个 job 都绿），人手验收与归档还没跑**）

## 进度

- **M1 / M2 / M4 完成并已归档**：分别在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`、`2026-10-18-m2-file-tools-and-fences/`、`2026-10-18-m4-real-provider/`，tag `m1` / `m2` / `m4`，merge commit `141e28c` / `d89a7c2` / `1d8e120`。主规格现有 7 个能力，`openspec validate --specs` 7 过 0 失败（M2 后 cli 7 / context-projection 8 / event-log 9 / fences 12 / file-tools 11 / provider 9 / turn-loop 9）。
- **M3 实现跑完，收尾门禁跑完，未合并未归档**：change `m3-bash-concurrency-timeout`，分支 `change/m3-bash-concurrency-timeout`（`main` 之上 32 个提交）。落地的东西：
  - `bash` 工具（`mutates=True`）：经平台 shell 执行、cwd 固定为工作区根、命令文本里的路径不解析（ADR-0008）；`timeout_seconds` 默认 30、上限 600，601 是 `TOOL_ARGS_INVALID` 且没有进程被启动；命令退出码非 0 仍是 `OK` 且 content 里有退出码；输出单一上限 16384 字节（stdout 与 stderr 合算）超限留固定标记 `[输出已截断]`；超时之后整棵进程树收掉（POSIX `start_new_session=True` + `killpg`，Windows `taskkill /T /F /PID`，ADR-0009）。
  - 派发段并发：同一回合的只读调用最多 8 个同时在跑，沾上「要改动」的排队串行；前缀每回合取样一次、整批共用；`tool/result` 按声明顺序落盘（第二个先完成也一样）。
  - 超时与取消落进词表：`ToolOutcome` 加 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`（16 值），新事件 `tool/cancelled`（payload 只有 `turn_id` 与 `tool_call_id`，不含命令输出）；超时塌成结果、回合继续，取消打断整个 session（`error/abort` + `turn/end(ABORTED)` + 退出码 5，ADR-0007）。模型请求超时 120 s 写进规格。
  - `approval/request` 改成提问之前落盘；写不进去就不问人。`error/fence` 的 payload 加 `path` 与 `raw_path`，`detail` 只面向人。
  - 测试 helper 收口：`tests/tool_harness.py` 的 `dispatch_call` / `dispatch_context` / `run_session_fixture` 收 `registry` 与 `approval_gate`，seam ① 的 run 形状收成一份。
  - CI：`.github/workflows/gates.yml` 落地，`windows-latest` + `ubuntu-latest` 两端各跑四道门禁、各判 95% 地板，不持任何 secret。
- **M3 的收尾门禁**：变异 12 条（10 条首轮被杀，T1 与 O1 存活并已各补一条判据，C2 判定 dud）→ `docs/verification/m3-bash-concurrency-timeout-mutation.md`；Learning Gate 收 L-027 至 L-030、关闭 L-018、补 L-019，**AGENTS.md 本轮不晋升** → `docs/lessons.md`。
- **M3 还剩**：tasks 7.3（两端的 `TOTAL` 记进本文件的门禁表——数字要人从 run 页面贴回来，见下表 CI 那行）、8.1–8.2（人手验收，见下）、`openspec-sync-specs` → `/openspec-archive-change` → `agents-md-slim`。`code-review` 两轴已跑完：A 至 G 七条全修（10.1–10.7，其中 10.4 改的是规格、10.1 与 10.5 改的是实现），Standards 轴的判断项与两条规格 ↔ 实现的判断记账进 ADR-0002 第 18 至 29 条，提交纪律的三处措辞欠账记在同文件最后一节。

## 门禁实测（Windows 本机）

| 门禁 | 实测 |
|---|---|
| 测试 | 222 passed / 2 skipped。skip 的两条：符号链接判据（本机不允许创建符号链接）、`test_sigint_in_a_real_subprocess_exits_with_five`（`skipif win32`，Linux 侧跑）。全量带覆盖率记账约 58 秒 |
| 覆盖率 | `coverage erase` → `coverage run -m pytest` → `coverage combine` → `coverage report --fail-under=95`：TOTAL **96%**（1136 语句 / 50 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `events/reader.py` 85% · `provider/openai_compat.py` 89% · `loop/turn_loop.py` 91% · `tools/bash_tools.py` 94% · `tools/file_tools.py` 96% · `tools/registry.py` 97% · `provider/mock.py` 98% · `tools/dispatch.py` 98% · `cli/main.py` 99% · 其余 100% |
| 类型 | `mypy --strict` 干净，22 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（56 文件）；全仓没有一处 `# noqa` |
| CI | **首绿已跑**：run #1（`d681ec6`）与 run #2（`2b9e044`）都是 `completed / success`——`gates (ubuntu-latest)` 57 s、`gates (windows-latest)` 99 s。推送走本机代理：`GIT_SSH_COMMAND='ssh -o "ProxyCommand=C:/PROGRA~1/Git/mingw64/bin/connect.exe -H 127.0.0.1:7897 %h %p"'`。`main` 已快进 `134ae69..1ba0e2f`，但 **`main` 上没有 `gates.yml`**（它只在 change 分支上），所以推 `main` 不触发 run；`main` 的 CI 首绿要等 M3 合并。两端的 `TOTAL` 由 workflow 那一步写进步骤摘要与一条 annotation，但 run 日志与 annotation API 都要鉴权（实测 403 / 空列表），数字要人从 [run 页面](https://github.com/vincento666/mini-harness/actions/runs/39242198903) 贴回来 |

50 条未覆盖行里绝大多数是回合循环里「日志写不进去」的分支（`turn_loop.py` 的 157、193–195、218–220、263、274、281、286、340、400、404、414、439、467、509、521 与 `dispatch.py` 的 74：approval 记录写不进日志时塌成 `TOOL_IO_FAILED`）。这一类在 seam ④ 直接判日志层，不在 seam ① 造场景去撞它——刻意没有为它们写判据，每个相关提交的信息里都写明了这一点。剩下的是平台分支与响应解析的形状分支：`bash_tools.py` 的 53–54、63（Windows 与 POSIX 各一半）、`file_tools.py` 的 128、130、133、160–161、203、`reader.py` 的 25、28–29、34、`openai_compat.py` 的 13 条、`cli/main.py` 的 216、254、`registry.py` 的 23、`mock.py` 的 67。要抬地板就补 `events/reader.py`、`provider/openai_compat.py`（响应解析里那些「形状不对」的分支）的判据，不要凑低价值测试。

## 待办与已知缺口

- **M3 的人手验收待跑**（tasks 8.1–8.2）：清单已备好，等人在真终端跑。三个场景（真事 + 并发派发与落盘顺序 / 一条故意超时的命令 / 一次 Ctrl-C）、可粘贴的命令、要贴回来的东西都在 `docs/verification/m3-bash-concurrency-timeout-manual.md`；工作区 `.tmp/m3-manual/`（gitignored）已备好 `notes/a.md`、`notes/b.md`、`count_lines.py`、`slow.py`，`counts.txt` 与日志目录已清空。不进 CI。
- **Windows 的 Ctrl-C 黑盒不在 M3**：seam ① 注入 cancel 判据、seam ⑥ Linux 真实 SIGINT 黑盒、两端都跑得动的 seam ⑥ `bash` 超时黑盒（`test_a_bash_timeout_in_the_cli_is_a_result_word_and_the_run_continues`，`timeout_seconds: 1` + 一条不会自己停的命令）都有；Windows 真实控制台 Ctrl-C 没有判据，缺口与边界记在 `docs/verification/m3-bash-concurrency-timeout-manual.md`。ConPTY 路线本机走不通（`UpdateProcThreadAttribute` 恒返回 87），可用的替代形状是 `WriteConsoleInput` 投递 KEY_EVENT（M2 的 approval smoke 用过）。
- **Linux 侧的判据在 CI 上跑绿了，本机仍没跑过**：符号链接键规范化、真实 SIGINT 黑盒、`tests/test_turn_cancel.py` 的 POSIX `killpg` 那一半——run #1 / #2 的 `ubuntu-latest` job 绿就是它们绿的证据（那两条在 Linux 上不被 skip，95% 地板也在那一端单独判过）。本机这一半依旧未验证；junction 那一半本机跑过（`test_a_junction_key_resolves_to_its_target_without_privileges`）。
- **硬杀会吞掉已经完成的结果**：`tool/result` 缓冲到批次结束才落盘（design.md 的 D3），所以 SIGKILL 落在批次中间时，已经跑完的那几条结果不在盘上，日志留下「有 `tool/call` 没 `tool/result`」的前缀。取消路径不受影响——`TOOL_CANCELLED` 是合成出来的结果，每条 `tool/call` 都有配对。append-only 日志里「立刻落盘」与「按声明顺序」只能要一样，M3 要的是顺序。pi 的 issue #7053 是同一形状。这条没有判据（判它要在判据里可靠地硬杀子进程再读日志，seam ⑥ 本机做不到），记为已知缺口。
- **两端覆盖率各报各的，不合并**：95% 地板在两个 runner 上各自判。平台分支在两端各拉低一半是已知形状（D9）。
- **M3 闭合的三条旧缺口**（原来在本文件的「已知缺口」里）：`approval/*` 晚落盘（ADR-0002 第 9 条）、取消只在回合边界被看到（第 10 条）、`error/fence` 的路径只在自由文本里（第 11 条）。三条都有判据与落地形状，见 `openspec/changes/m3-bash-concurrency-timeout/design.md` 的 D12 / D5 / D13。
- 延后的重构与记账：`docs/adr/0002-deferred-refactors.md`。M3 收尾轮逐条改判：**已处理** 第 1（含剩的那一半）、6、9、10、11 条；**改判为长期形态** 第 8、12、16 条；**未处理推到 M5** 第 14、15 条（要等第二个 provider 或 REPL）；**未触发** 第 17 条；第 3 条（`_replay` 的扫描逻辑下沉）推到 M6 的 chat REPL。第 2、4、5、7 条 M2 已处理。
- 变异测试记录：`docs/verification/m1-mutation.md`（两轮 18 条：16 杀，G 与 P 各换回一条判据）、`docs/verification/m2-file-tools-and-fences-mutation.md`（收尾轮 20 条 + 审查后抽查 4 条）、`docs/verification/m4-real-provider-mutation.md`（18 条：17 杀，E2 补三条判据后被杀）、`docs/verification/m3-bash-concurrency-timeout-mutation.md`（12 条：10 杀，T1 与 O1 补判据后被杀，C2 是 dud）。
- 手测清单：`docs/verification/m1-m2-manual-smoke.md`（11 个 CLI 黑盒场景一键跑完、`mismatches=0`）。M4 的人手验收是另一形状：`docs/verification/m4-real-provider-manual.md`，两个真实端点各一次，外加一次 402 的失败路径证据。M3 沿用后者的形状。
- 已知缺口（M3 之后仍在）：
  - **围栏不是安全边界**：没有 OS 级强制（ADR-0003 第 1 条），防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。`bash` 只受档位轴约束（ADR-0008）：命令文本里的路径不解析，所以越界轴对 `bash` 不适用。
  - **适配器只认 OpenAI 兼容的拼写**：`openai_compat.py` 只认 `choices[].message.tool_calls` 与 `usage.prompt_tokens` / `completion_tokens`，不读流式 SSE（ADR-0006 第 1 条）。
  - **`PROVIDER_ABORTED` 有词表值与判据、没有生产路径**：取消走回合边界的 `error/abort`（退出码 5），`src` 里没有「取消置位后再调 `generate()`」的地方。
  - **`Usage` 只落进日志、不参与预算**：不变量 D 的窗口预算与 `CONTEXT_WINDOW_EXCEEDED` 还不存在——**M5 的活**（`docs/roadmap.md`）。
  - **CAS 只比「读到的窗口」**：窗口之外的改动不触发 `STALE_EDIT`；取舍与收紧办法记在 `docs/adr/0004-cas-compares-the-read-window.md`。
- ADR 现有九份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`（记账，M3 改判见上）、`0003-m2-fence-simplifications.md`、`0004-cas-compares-the-read-window.md`、`0005-m4-before-m3.md`（M4 换到 M3 之前）、`0006-m4-provider-simplifications.md`、`0007-ctrl-c-cancels-the-session.md`（决策 15 的部分推翻）、`0008-bash-is-fenced-by-the-sandbox-level-only.md`、`0009-bash-runs-through-the-platform-shell.md`（进程树终止手段，与 fences 主规格「MUST NOT 依赖 job object」的区分）。
- 门禁判据此前**只在 Windows 上跑绿过**；M3 把跨平台对齐与 CI 矩阵做成了工作流，但首绿要等人推送（`docs/roadmap.md` 的「跨平台与 CI 排在哪儿」；换序见 ADR-0005）。CI 不持 API key：门禁只跑 mock 判据，真实 Provider 的 smoke 归人手验收。平台绑定点：路径规范化（大小写 / junction / 符号链接）、tty 检测、SIGINT 与进程树终止。
