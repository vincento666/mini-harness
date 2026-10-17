# Loop Lessons

教训的**收件箱与活跃区**。机制照 `universal-work-loop` 的 Learning Gate：每次里程碑收尾或 `code-review` 之后扫一遍证据，把可复用的信号写进这里；**AGENTS.md 只接收晋升后的压缩规则，且每次晋升必须同时删掉或压缩 AGENTS.md 里的一条旧内容（一进一出）**。

`Status`：`inbox`（待消化）| `active`（每次进入本项目工作都读）| `promoted`（已写进 AGENTS.md）| `rejected`。

## Active Lessons

现在只有这五条会常驻；其余留在收件箱。

1. **词表类规格必须配「每个值都可达」的测试**。M1 的 `turn/end.stop_reason` 从成功路径倒推，漏了 `TOOL_CALLS`；`ABORTED` 写了却不可达，直到实现才暴露。
2. **写新 Requirement 时成对检查它跟已有 Requirement 是否互斥**。「每个非零退出都有 `error/*` 事件」与「重放不追加事件」各自正确、合起来不可满足，最后靠 ADR-0001 开一个显式例外收场。
3. **测试写下即绿就是危险信号**。M1 有约 24 个切片没有红。判据不是测试数量，是变异测试：15 个变异 14 个被杀，存活的 `P` 证明当时没有任何 CLI 测试守 `LOG_WRITE_FAILED`。
4. **接手前先核实时状态，不要相信上一段的叙事**。M1 期间 `git checkout --` 误回滚了未提交的改动，导致一次 `ImportError`。跑 `git status --short` 与 `git log --oneline -3` 再动手。
5. **文本文件绝不经 PowerShell 往返，读也要显式 `-Encoding UTF8`**。`Set-Content` 毁 UTF-8（真毁过一次测试文件），`Out-File -Encoding utf8` 带 BOM，`>` 产生 UTF-16LE；不带 `-Encoding UTF8` 的 `Get-Content` 连行数都会数错（见 L-013）。改文件用编辑工具；要读命令的 stderr 就 `2> 文件` 再读。

## Candidate Inbox

条目格式：

```text
Date / Context / Observation / Evidence / Next use / Promotion candidate / Status
```

### L-001
- Date: 2026-10-15
- Context: M1 `tasks.md` 1.2「验证工具链可用」
- Observation: 把「0 个测试时 pytest 退出码 0」写成了任务，pytest 实际返回 5，任务不可能成立
- Evidence: 规格返工提交 `73069a6` 前后；tasks 1.2 措辞改写
- Next use: 写「验证类」任务时先跑一次真实命令拿退出码，再写判据
- Promotion candidate: AGENTS.md（已并入 Active 1 的同类）
- Status: merged into L-014

### L-002
- Date: 2026-10-15
- Context: 事件词表与停止原因的规格
- Observation: 从「成功跑完」倒推词表，漏掉「回合结束但会话继续」这一整类状态
- Evidence: 新增第五个值 `TOOL_CALLS`（提交 `73069a6`）
- Next use: M2 写工具事件词表时先穷举「回合结束 / 会话结束 / 失败」三态
- Promotion candidate: solution document（M2 design.md）
- Status: closed（M2 的 14.1 已把「每个取值都可达」做成判据）

### L-003
- Date: 2026-10-15
- Context: cli 规格的两条 Requirement
- Observation: 各自正确、合起来不可满足；`openspec validate --strict` 只查结构，查不出这种矛盾
- Evidence: ADR-0001 里 `error/replay` 只走 stderr 的显式例外
- Next use: 每写一条新 Requirement，列出它可能撞上哪条已有的，写进 design.md
- Promotion candidate: AGENTS.md（Active 2）
- Status: active

### L-004
- Date: 2026-10-16
- Context: 变异测试第 10、11 轮
- Observation: 变异必须改变**可观察行为**，否则是 dud mutant（`elif not x:` → `elif False:` 语义等价，41 个测试全绿）；重命名内部函数导致 5 个 collection error，属于无效变异
- Evidence: `docs/verification/m1-mutation.md` 的方法论注记
- Next use: 变异前先想「哪条断言会因此变红」，想不出就别做
- Promotion candidate: AGENTS.md 流程节（变异段）
- Status: promoted

### L-005
- Date: 2026-10-16
- Context: 第 11 轮变异 `P`
- Observation: 删掉 `_run` 的内核失败映射分支后仍 exit 1（KeyError 兜底），59 个测试全绿 —— 存活原因是**没有 CLI 黑盒测试覆盖 `LOG_WRITE_FAILED`**，而规格里它有两条 Scenario
- Evidence: `docs/verification/m1-mutation.md`；补测试提交 `1a7c912`（抽出 `exit_code_for`）
- Next use: 规格里每条失败路径 Scenario 都要能指到一条测试；指不到就是缺口
- Promotion candidate: verifier/eval
- Status: inbox

### L-006
- Date: 2026-10-16
- Context: 手动黑盒跑 M1 CLI
- Observation: 两个缺陷 `code-review` 两个轴都没发现：带 UTF-8 BOM 的 fixture 读不了（`FIXTURE_INVALID: Unexpected UTF-8 BOM`）、日志不可写时的退出码路径无覆盖
- Evidence: 修提交 `6ad6256`；黑盒九发的结果记录
- Next use: 里程碑收尾除了自动门禁，手动跑一遍真实命令（含畸形输入）
- Promotion candidate: AGENTS.md 流程节
- Status: inbox

### L-007
- Date: 2026-10-16
- Context: 子进程覆盖率记账
- Observation: seam ⑥ 的 CLI 测试跑在子进程里，默认不计覆盖率；要记账必须 `coverage run -p` + `COVERAGE_FILE` 指回仓库根 + 显式 `--rcfile`（测试的 `cwd` 是 tmp_path）
- Evidence: 提交 `0a9745e`；`cli/main.py` 36% → 96%
- Next use: 任何「黑盒 + 记账」需求直接照这套
- Promotion candidate: solution document
- Status: inbox

### L-008
- Date: 2026-10-16
- Context: 覆盖率门禁本身
- Observation: `coverage combine` 只认文件内容不认新旧，上一轮残留的 partial 会被混进这一轮，且**看不出来**（连跑两轮不 erase，第二轮仍报 96%）
- Evidence: 提交 `f0e063b`（AGENTS.md 加 `coverage erase` 为第 0 步）
- Next use: 任何「合并式」记账都先清场再测
- Promotion candidate: AGENTS.md（已并入覆盖率段）
- Status: active

### L-009
- Date: 2026-10-16
- Context: `uv add --dev ruff pytest-cov`
- Observation: uv 缓存（C:）与仓库（S:）跨文件系统，hardlink 建不了 → 退化成复制，一条命令跑了约 17 分钟
- Evidence: 实现会话的回报；缓存随后搬到 `S:\AppData\uv\cache`
- Next use: 跨盘项目设 `UV_LINK_MODE=copy` 或让缓存与仓库同盘
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: merged into L-012

### L-010
- Date: 2026-10-16
- Context: 提交粒度
- Observation: 「一个红绿循环一次提交」在实现中被打包成 4 个多任务提交，最狠的一个打包 14 个任务，出问题不好二分
- Evidence: `8320f1e`（tasks 7.1–9.4）
- Next use: 规则已收紧（AGENTS.md 流程节）：一个提交最多覆盖同一 seam 相邻 3 个 task
- Promotion candidate: AGENTS.md（已写）
- Status: promoted

### L-011
- Date: 2026-10-16
- Context: 规格与实现的偏差记录方式
- Observation: 简化不写 ADR 就会被后人当缺陷修掉；ADR 只在「难回退 + 无上下文会困惑 + 真实取舍」三条同时成立时才写
- Evidence: `docs/adr/0001`、`docs/adr/0002`
- Next use: 沿用 `domain-modeling` 的 ADR-FORMAT
- Promotion candidate: 已在 AGENTS.md 引用纪律
- Status: promoted

### L-012
- Date: 2026-10-17
- Context: 把 uv 缓存从 C: 搬到 S:
- Observation: 同盘时 uv 用 hardlink 把缓存文件接进 venv，**字节是共享的**；搬走缓存只回收「没有被任何 venv 引用」的那部分。实测搬走 5.338 GB 只让 C: 多出 0.4 GB，因为其中约 4.91 GB 与三个 uv 建的 venv 共享（`.unsloth` 4.11 / hermes-agent 0.61 / uv tools 0.19）
- Evidence: `fsutil hardlink list …\cryptography\hazmat\bindings\_rust.pyd` 列出三个 venv 路径；robocopy 日志 `5.338 g copied / 0 failed`；三个 `pyvenv.cfg` 都写着 `uv = 0.12.5`
- Next use: 估算「搬缓存能腾出多少」之前先数谁在共享它；跨盘搬缓存会让总占用上升
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: inbox

### L-013
- Date: 2026-10-17
- Context: 复核「AGENTS.md 压缩了多少」
- Observation: PowerShell 5.1 的 `Get-Content` 不带 `-Encoding UTF8` 时按 ANSI 解码 UTF-8 中文，**行数会数错、控制台全是乱码**：同一份文件报 99 个 LF / 8062 字符，真实是 138 行 / 6892 字符。我据此向用户报了「135 → 100 行」的错误结论
- Evidence: `Get-Content -Raw` 99 LF vs `Get-Content -Raw -Encoding UTF8` 138 LF；`git cat-file -s` 11,815 B；`git diff --stat 8298373 060c067 -- AGENTS.md` = +27 / −19
- Next use: 行数与字数统计一律 `-Encoding UTF8`，或用 `git cat-file -s` 的字节数；跨工具核对以 git 与文件读取工具为准
- Promotion candidate: 已并入 Active Lessons 第 5 条
- Status: active

### L-014
- Date: 2026-10-17
- Context: 复核 AGENTS.md 命令段
- Observation: 我写进 AGENTS.md 的判据「`ruff format --diff` 空输出 = 干净」是凭印象写的。实测干净时它**退出码 0 且往 stderr 打 `27 files already formatted`**，不是空输出。同一文件里还抓到过一处过时的「全量测试 9 秒」
- Evidence: `uv run ruff format --diff src tests` → exit 0 + stderr「27 files already formatted」
- Next use: 写进 AGENTS.md 的每一条判据都要当场跑一次并记下真实输出；判据优先写成「退出码」而不是「输出长什么样」
- Promotion candidate: 无需进 AGENTS.md（判据本身已改对）
- Status: inbox

### L-015
- Date: 2026-10-17
- Context: 决定坏味道账本与 ADR 编号规则
- Observation: 技能已有官方格式时我另立规矩：发明了「ADR 一个里程碑一份」「命名 `NNNN-<milestone>-<slug>.md`」「允许原地更新」，被用户纠正。`ADR-FORMAT.md` 里只有：顺序编号 `NNNN-slug.md`、编号扫现有最大号 +1、目录用到时才建、正文 1–3 句、三条判据同时成立才写、可选 `Status` 与 `superseded by ADR-NNNN`
- Evidence: `C:\Users\vincento\.agents\skills\domain-modeling\ADR-FORMAT.md` 第 3、5、15、21、27、29-37 行
- Next use: 用任何技能之前先读它的 SKILL/FORMAT 文件并按官方规则写；要偏离就在 ADR 里写明偏离与理由，不要在 AGENTS.md 里另立一套
- Promotion candidate: AGENTS.md 引用纪律已改为「照 ADR-FORMAT」；教训本身留本文件
- Status: inbox

### L-016
- Date: 2026-10-17
- Context: M2 收尾变异轮（tasks 15.1）
- Observation: 三种「看起来在变异」其实全绿的改法，都不是变异：① 删掉 `path_key` 里的 `os.path.normcase` —— 本机 `os.path.realpath` 走 `GetFinalPathNameByHandleW`，已经把**存在**的路径折叠成磁盘上的大小写，语义等价；② 把围栏的档位段与边界段互换 —— 两段各自带互斥的 `context.sandbox` 前置条件，不可能同时命中，顺序不可观察；③ 把 `judge_fence` 调用挪到参数校验之前、但 `DENIED` 的返回留在原位 —— 可观察顺序没变
- Evidence: `docs/verification/m2-file-tools-and-fences-mutation.md` 的 dud 一节（G / I / J′ 三行）；①的大小写实测记在同文档
- Next use: 做「顺序类」变异之前先确认那两段可能同时命中；否则先把前置条件一起去掉（那是另一条变异，本轮的 H）
- Promotion candidate: 无需进 AGENTS.md（L-004 已晋升的那句「变异必须改变可观察行为」已覆盖原则）
- Status: inbox

### L-017
- Date: 2026-10-17
- Context: M2 收尾变异轮，`reads_from_records` 连中两条存活（M、N）
- Observation: 同一个函数被改坏两次都全绿：「后来的成功读不覆盖先前的」与「一次 `write` 也算读过」。当时的判据只有「读过 / 没读过」两个端点，没有「读的顺序」和「什么算读过」这两个维度。补完两条后端点从 2 个变 4 个
- Evidence: 存活与补测记录 `a146f8c`；变异下的红：`assert ['OK', 'OK', ... 'STALE_EDIT'] == ['OK', 'OK', 'OK', 'OK']`、`assert ['OK', 'STALE_EDIT'] == ['OK', 'WRITE_WITHOUT_READ']`
- Next use: 一条规则有多个输入维度时，变异按维度逐个做；同一函数连续两条存活就是「只测了端点」的信号
- Promotion candidate: AGENTS.md 流程节的变异段（若要晋升就与「一次只改一处」那句合并，不新增句子）
- Status: inbox

### L-018
- Date: 2026-10-17
- Context: M2 13.7 的真实 tty approval smoke
- Observation: 本机 `subprocess.DEVNULL` 的 stdin 是 NUL 设备，`isatty()` 报 **True**，所以「没有人类可问」不能用 DEVNULL 表达，EOF 才是 `UNAVAILABLE` 的判据。ConPTY 路线在本机 `UpdateProcThreadAttribute` 恒返回 87；可用的路线是 `CREATE_NEW_CONSOLE` + `AttachConsole(child pid)` + `CONIN$` + `WriteConsoleInputW` 投 KEY_EVENT
- Evidence: `docs/verification/m2-file-tools-and-fences-approval-smoke.md` 与同目录 `-approval-smoke-harness.py`（`y` → 0、`n` → 3）；13.3 第一次红的记录
- Next use: M3 要真实 tty 的黑盒（Ctrl-C、交互式 approval）直接复用那份 harness，别再试 ConPTY
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: inbox

### L-019
- Date: 2026-10-17
- Context: M2 变异轮里补测试
- Observation: 编辑工具的两个坑各咬过一次：把 `async def test_...:` 整行（含结尾换行）当 `old_string` 会把下一行粘到 def 行上、语法当场坏掉；`git checkout -- <file>` 之后直接 edit 会报「file changed since it was read」，必须先重读那一小段
- Evidence: 本轮 `tests/test_tool_registry.py` 的 def 行被粘坏过一次；`dispatch.py` / `fences.py` / `file_tools.py` 各撞过一次「file changed since it was read」
- Next use: 锚点选正文里唯一的两行组合，不选 def 行；每次 `git checkout --` 之后先 read 再 edit
- Promotion candidate: 无需进 AGENTS.md（工具用法，不是项目规则）
- Status: inbox

### L-020
- Date: 2026-10-17
- Context: M2 12.3「不写 `tool/cancelled` / `model/retry`」
- Observation: 往 `closing_events` 里塞 `tool/cancelled` 并不会写出那个类型——`EventLog.append` 把词表外的类型塌成 `error/internal` 并在 payload 里记 `unrecognized_type`。只断言「日志里没有那个类型」会绿在错误的原因上
- Evidence: tasks 12.3 的变异记录；`docs/verification/m2-file-tools-and-fences-mutation.md` 方法论注 3
- Next use: 断言「某事件类型不该出现」时同时断言 `payload["unrecognized_type"]` 里没有那个词
- Promotion candidate: 无需进 AGENTS.md（本仓 `EventLog` 的具体行为，规格与测试已自证）
- Status: inbox

### M2 收尾轮的消化记录（2026-10-17，tasks 15.2）

收新条目之前先消化：L-001 并入 L-014（同一件事——判据要当场跑一次并记下真实输出）、L-009 并入 L-012（同一件事——uv 缓存与跨盘）、L-002 关闭（M2 的 14.1 已经把「词表每个取值都可达」做成判据）。收件箱从 9 条变成 6 条旧 + 5 条新 = 11 条，仍在 15 条以内。

**AGENTS.md 本轮不晋升**：M2 的可复用信号要么已被 Active Lessons 覆盖（第 3 条「测试写下即绿就是危险信号」、第 4 条「接手前先核实时状态」），要么是环境事实或工具用法（L-018 / L-019 / L-020），没有值得占 AGENTS.md 额度的一句话新规则。

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）

- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
