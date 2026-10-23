# Loop Lessons

教训的**收件箱与活跃区**。机制照 `universal-work-loop` 的 Learning Gate：每次里程碑收尾或 `code-review` 之后扫一遍证据，把可复用的信号写进这里；**AGENTS.md 只接收晋升后的压缩规则，且每次晋升必须同时删掉或压缩 AGENTS.md 里的一条旧内容（一进一出）**。

`Status`：`inbox`（待消化）| `active`（每次进入本项目工作都读）| `promoted`（已写进 AGENTS.md）| `rejected`。

## Active Lessons

现在只有这五条会常驻；其余留在收件箱。

1. **词表类规格必须配「每个值都可达」的测试**。M1 的 `turn/end.stop_reason` 从成功路径倒推，漏了 `TOOL_CALLS`；`ABORTED` 写了却不可达，直到实现才暴露。
2. **写新 Requirement 时成对检查它跟已有 Requirement 是否互斥**。「每个非零退出都有 `error/*` 事件」与「重放不追加事件」各自正确、合起来不可满足，最后靠 ADR-0001 开一个显式例外收场。
3. **测试写下即绿就是危险信号**。M1 有约 24 个切片没有红。判据不是测试数量，是变异测试：两轮共 18 个变异、16 个被杀，存活的 `G` 与 `P` 各换回一条判据（`P` 证明当时没有任何 CLI 测试守 `LOG_WRITE_FAILED`）。
4. **接手前先核实时状态，不要相信上一段的叙事**。M1 期间 `git checkout --` 误回滚了未提交的改动，导致一次 `ImportError`。跑 `git status --short` 与 `git log --oneline -3` 再动手。
5. **文本文件绝不经 PowerShell 往返，读也要显式 `-Encoding UTF8`**。`Set-Content` 毁 UTF-8（真毁过一次测试文件），`Out-File -Encoding utf8` 带 BOM，`>` 产生 UTF-16LE；不带 `-Encoding UTF8` 的 `Get-Content` 连行数都会数错（见 L-013），还会把中文注释行与紧随其后的代码行粘成一行（见 L-022）。改文件用编辑工具；要读命令的 stderr 就 `2> 文件` 再读。

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
- Next use: 规格里每条失败路径 Scenario 都要能指到一条测试；指不到就是缺口。同族的两条已并进来：L-017（一条规则有多个输入维度时按维度逐个变异）、L-028（规格里写死的数值与边界）
- Promotion candidate: verifier/eval
- Status: inbox（家族头：L-005 失败路径 / L-017 维度 / L-028 数值与边界 / L-038 单位与边界。M6 的三条存活变异全在这一族里：窗口校验 `<= 0` 的「恰为 0」那一格、`session/end.turns` 的「减不减一都一样」、stdout 的 `purpose` 过滤「这个入口里从没发生过压缩」。见 `docs/verification/m6-chat-repl-mutation.md`）

### L-006
- Date: 2026-10-16
- Context: 手动黑盒跑 M1 CLI
- Observation: 两个缺陷 `code-review` 两个轴都没发现：带 UTF-8 BOM 的 fixture 读不了（`FIXTURE_INVALID: Unexpected UTF-8 BOM`）、日志不可写时的退出码路径无覆盖
- Evidence: 修提交 `6ad6256`；黑盒九发的结果记录
- Next use: 里程碑收尾除了自动门禁，手动跑一遍真实命令（含畸形输入）
- Promotion candidate: AGENTS.md 流程节
- Status: closed（AGENTS.md 流程节已把「人手验收」写成每个里程碑的固定完成判据，M4 的 `docs/verification/m4-real-provider-manual.md` 是它的产物）

### L-007
- Date: 2026-10-16
- Context: 子进程覆盖率记账
- Observation: seam ⑥ 的 CLI 测试跑在子进程里，默认不计覆盖率；要记账必须 `coverage run -p` + `COVERAGE_FILE` 指回仓库根 + 显式 `--rcfile`（测试的 `cwd` 是 tmp_path）
- Evidence: 提交 `0a9745e`；`cli/main.py` 36% → 96%
- Next use: 任何「黑盒 + 记账」需求直接照这套
- Promotion candidate: solution document
- Status: closed（AGENTS.md 命令段与覆盖率纪律段已把这套三步走写死，M2/M4 每轮门禁都在跑）

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
- Status: closed（环境事实已处置：缓存在 S: 与仓库同盘，本项目不再涉及）

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
- Status: closed（2026-10-20 M5 开工前消化：AGENTS.md 命令段的判据已按实测写死成「退出码」，M4 之后每轮门禁都在跑，没有待办）

### L-015
- Date: 2026-10-17
- Context: 决定坏味道账本与 ADR 编号规则
- Observation: 技能已有官方格式时我另立规矩：发明了「ADR 一个里程碑一份」「命名 `NNNN-<milestone>-<slug>.md`」「允许原地更新」，被用户纠正。`ADR-FORMAT.md` 里只有：顺序编号 `NNNN-slug.md`、编号扫现有最大号 +1、目录用到时才建、正文 1–3 句、三条判据同时成立才写、可选 `Status` 与 `superseded by ADR-NNNN`
- Evidence: `C:\Users\vincento\.agents\skills\domain-modeling\ADR-FORMAT.md` 第 3、5、15、21、27、29-37 行
- Next use: 用任何技能之前先读它的 SKILL/FORMAT 文件并按官方规则写；要偏离就在 ADR 里写明偏离与理由，不要在 AGENTS.md 里另立一套
- Promotion candidate: AGENTS.md 引用纪律已改为「照 ADR-FORMAT」；教训本身留本文件
- Status: closed（AGENTS.md 引用纪律已写死照 ADR-FORMAT；M4 的 ADR-0006 按它写）

### L-016
- Date: 2026-10-17
- Context: M2 收尾变异轮（tasks 15.1）
- Observation: 三种「看起来在变异」其实全绿的改法，都不是变异：① 删掉 `path_key` 里的 `os.path.normcase` —— 本机 `os.path.realpath` 走 `GetFinalPathNameByHandleW`，已经把**存在**的路径折叠成磁盘上的大小写，语义等价；② 把围栏的档位段与边界段互换 —— 两段各自带互斥的 `context.sandbox` 前置条件，不可能同时命中，顺序不可观察；③ 把 `judge_fence` 调用挪到参数校验之前、但 `DENIED` 的返回留在原位 —— 可观察顺序没变
- Evidence: `docs/verification/m2-file-tools-and-fences-mutation.md` 的 dud 一节（G / I / J′ 三行）；①的大小写实测记在同文档
- Next use: 做「顺序类」变异之前先确认那两段可能同时命中；否则先把前置条件一起去掉（那是另一条变异，本轮的 H）
- Promotion candidate: 无需进 AGENTS.md（L-004 已晋升的那句「变异必须改变可观察行为」已覆盖原则）
- Status: merged into L-004

### L-017
- Date: 2026-10-17
- Context: M2 收尾变异轮，`reads_from_records` 连中两条存活（M、N）
- Observation: 同一个函数被改坏两次都全绿：「后来的成功读不覆盖先前的」与「一次 `write` 也算读过」。当时的判据只有「读过 / 没读过」两个端点，没有「读的顺序」和「什么算读过」这两个维度。补完两条后端点从 2 个变 4 个
- Evidence: 存活与补测记录 `a146f8c`；变异下的红：`assert ['OK', 'OK', ... 'STALE_EDIT'] == ['OK', 'OK', 'OK', 'OK']`、`assert ['OK', 'STALE_EDIT'] == ['OK', 'WRITE_WITHOUT_READ']`
- Next use: 一条规则有多个输入维度时，变异按维度逐个做；同一函数连续两条存活就是「只测了端点」的信号
- Promotion candidate: AGENTS.md 流程节的变异段（若要晋升就与「一次只改一处」那句合并，不新增句子）
- Status: merged into L-005（2026-10-20 M5 开工前消化：同一件事——规格里的事实要有判据钉住，这条是它的「输入维度」版）

### L-018
- Date: 2026-10-17
- Context: M2 13.7 的真实 tty approval smoke
- Observation: 本机 `subprocess.DEVNULL` 的 stdin 是 NUL 设备，`isatty()` 报 **True**，所以「没有人类可问」不能用 DEVNULL 表达，EOF 才是 `UNAVAILABLE` 的判据。ConPTY 路线在本机 `UpdateProcThreadAttribute` 恒返回 87；可用的路线是 `CREATE_NEW_CONSOLE` + `AttachConsole(child pid)` + `CONIN$` + `WriteConsoleInputW` 投 KEY_EVENT
- Evidence: `docs/verification/m2-file-tools-and-fences-approval-smoke.md` 与同目录 `-approval-smoke-harness.py`（`y` → 0、`n` → 3）；13.3 第一次红的记录
- Next use: M3 要真实 tty 的黑盒（Ctrl-C、交互式 approval）直接复用那份 harness，别再试 ConPTY
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: closed（M3 裁决 Windows 真实 Ctrl-C 黑盒不在该 change 范围，缺口记进 `docs/verification/m3-bash-concurrency-timeout-manual.md`；harness 本身仍可用）

### L-019
- Date: 2026-10-17
- Context: M2 变异轮里补测试
- Observation: 编辑工具的两个坑各咬过一次：把 `async def test_...:` 整行（含结尾换行）当 `old_string` 会把下一行粘到 def 行上、语法当场坏掉；`git checkout -- <file>` 之后直接 edit 会报「file changed since it was read」，必须先重读那一小段
- Evidence: 本轮 `tests/test_tool_registry.py` 的 def 行被粘坏过一次；`dispatch.py` / `fences.py` / `file_tools.py` 各撞过一次「file changed since it was read」；M3 变异轮每次 `git checkout --` 之后重读，三次先 edit 后报错
- Next use: 锚点选正文里唯一的两行组合，不选 def 行；每次 `git checkout --` 之后先 read 再 edit
- Promotion candidate: 无需进 AGENTS.md（工具用法，不是项目规则）
- Status: inbox（家族头：L-019 重读与 def 行 / L-044 追加锚点。M6 又踩两次：一次 `ruff format` 之后 edit 报「file changed since it was read」，一次把 `old_string` 与 `new_string` 写反、报「old_string was not found」。2026-10-24 又踩一次反向错误，并补上这一族的新格：**改源文件的脚手架一律按字节读写**——变异轮用 `read_text` / `write_text` 改 `src/mini_harness/cli/main.py`，Windows 的文本模式把 LF 换成 CRLF，还原检查当场报「还原失败」，工作树里那一整份文件的行尾都被改（`git diff` 只剩 CRLF 警告、内容一行没动）；改成 `read_bytes` / `write_bytes` 并在还原后比对字节才干净）

### L-020
- Date: 2026-10-17
- Context: M2 12.3「不写 `tool/cancelled` / `model/retry`」
- Observation: 往 `closing_events` 里塞 `tool/cancelled` 并不会写出那个类型——`EventLog.append` 把词表外的类型塌成 `error/internal` 并在 payload 里记 `unrecognized_type`。只断言「日志里没有那个类型」会绿在错误的原因上
- Evidence: tasks 12.3 的变异记录；`docs/verification/m2-file-tools-and-fences-mutation.md` 方法论注 3
- Next use: 断言「某事件类型不该出现」时同时断言 `payload["unrecognized_type"]` 里没有那个词
- Promotion candidate: 无需进 AGENTS.md（本仓 `EventLog` 的具体行为，规格与测试已自证）
- Status: closed（`EventLog` 的词表外塌缩有判据钉着，M4 的 `model/retry` 进词表时也复用了同一条断言形状）

### L-021
- Date: 2026-10-18
- Context: 写 M1–M2 的 CLI 手测清单（`docs/verification/m1-m2-manual-smoke.md`）
- Observation: 手测脚手架有三条硬要求，缺一条就得到假结果：① **每个场景一个干净工作区**——上一轮把 `TODO: one` 改成 `DONE: one`，下一轮的 `old_string` 就变成 `EDIT_TARGET_NOT_FOUND`，看起来像 CAS 坏了；② **带工具调用的 fixture 必须有收尾回合**——只有一条 `finish_reason: tool_calls` 的条目会让下一跳 `generate` 撞上 `PROVIDER_EXHAUSTED`，本该 0 的场景报 1；③ **判据写成「退出码 + 日志里的词」两列并当场对照**，只写「应该成功」的清单会在第一次跑时就分不清是谁的错
- Evidence: 同一份脚手架三次返工：共用工作区时 `stale-edit` 报 `EDIT_TARGET_NOT_FOUND, EDIT_TARGET_NOT_FOUND`；缺收尾回合时 `io-failure` 报 exit 1；修完 11 个场景 `mismatches=0`
- Next use: M3 的手测清单直接沿用这份的形状（场景表 + 一键脚本 + `mismatches=0`），别新写一套
- Promotion candidate: 无需进 AGENTS.md（写验证文档的做法，细节已在 `docs/verification/`）
- Status: closed（2026-10-20 M5 开工前消化：那三条已在 `docs/verification/m1-m2-manual-smoke.md` 与 M8 的 `-manual.md` 里成型，M5 的 8.1 直接照现有形状写，不需要这条常驻）

### L-022
- Date: 2026-10-18
- Context: 从 markdown 里抠出代码块逐字执行，用来证明文档里的脚本真能跑
- Observation: 不带 `-Encoding utf8` 的 `Get-Content` 按本机 ANSI 代码页解码 UTF-8 中文，**行尾字节会被并入前一个多字节字符**——中文注释行与紧随其后的代码行粘成一行，脚本当场语法错误。症状看起来像「文档里的脚本是坏的」，实际是读取端的解码问题
- Evidence: 第一次抽取报「位置 行:13 字符:1 意外的标记 `}`」；加 `-Encoding utf8` 后同一份脚本 11 个场景全对
- Next use: 任何「读文件内容再执行/计数」的 PowerShell 都显式 `-Encoding utf8`（Active 5 的加强版：不只是行数数错，还会粘行）
- Promotion candidate: 已并入 Active 5 的证据，不占 AGENTS.md 额度
- Status: merged into Active 5

### M2 收尾轮的消化记录（2026-10-17，tasks 15.2）

收新条目之前先消化：L-001 并入 L-014（同一件事——判据要当场跑一次并记下真实输出）、L-009 并入 L-012（同一件事——uv 缓存与跨盘）、L-002 关闭（M2 的 14.1 已经把「词表每个取值都可达」做成判据）。收件箱从 9 条变成 6 条旧 + 5 条新 = 11 条，仍在 15 条以内。

**AGENTS.md 本轮不晋升**：M2 的可复用信号要么已被 Active Lessons 覆盖（第 3 条「测试写下即绿就是危险信号」、第 4 条「接手前先核实时状态」），要么是环境事实或工具用法（L-018 / L-019 / L-020），没有值得占 AGENTS.md 额度的一句话新规则。

### L-023
- Date: 2026-10-18
- Context: M4 收尾变异轮 E2（`except httpx.HTTPError` → `except httpx.ConnectError`）
- Observation: 变异存活。补的第一条判据用 `ConnectError` 也杀不死它——**最常见的失败恰好还在收窄后的捕获里**；真正杀死它的是同族里不显眼的 `ReadError`。同一时刻规格里 `PROVIDER_TRANSPORT` 有 Scenario，却没有任何判据经过那条捕获（覆盖率印证：`openai_compat.py` 的 85–86 行未覆盖）
- Evidence: `docs/verification/m4-real-provider-mutation.md` 的 E2 行与「存活的那一条」节；补测提交 `e1e951a`；`openai_compat.py` 87% → 89%
- Next use: 任何 `except <基类>` 的代码，判据至少覆盖族里两个成员，其中一个不是最显眼的那个
- Promotion candidate: AGENTS.md 流程节的变异段（本轮晋升，一进一出换掉「做法与判据见 `docs/verification/` 下的记录」）
- Status: promoted

### L-024
- Date: 2026-10-18
- Context: M4 6.x，CLI 子进程打本地 `http://127.0.0.1:8300/v1`
- Observation: httpx 默认 `trust_env=True` 会解析本机 `NO_PROXY=localhost,127.0.0.1,::1,[::1]` 并抛 `httpx.InvalidURL: Invalid port: ':1]'`；它不是 `httpx.HTTPError` 的子类，于是绕过适配器对传输层失败的捕获，直接给用户一个未捕获 traceback（违反不变量 B 与 F）。症状是「端点明明活着，请求却炸在客户端构造时」，第一反应会去查端点
- Evidence: `.tmp/dbg_proxy.py` 三情形实测（默认 → InvalidURL；`trust_env=False` → 正常；删掉 `NO_PROXY` → 正常）；provider delta 新增「适配器不继承代理环境变量」；ADR-0006 第 2 条记代价
- Next use: 接任何第三方网络库先问「它默认读哪些环境变量与配置文件」，并把「哪些异常类不在你的捕获族里」当成捕获契约的一部分检查
- Promotion candidate: 无需进 AGENTS.md（已由 ADR-0006 与那条 Requirement 承载）
- Status: closed（2026-10-20 M5 开工前消化：`trust_env` 那条已由 ADR-0006 与「适配器不继承代理环境变量」承载；M5 只改这个适配器的失败分类，不接新库）

### L-025
- Date: 2026-10-18
- Context: M4 7.1 / 7.2 两个端点跑同一条任务
- Observation: 同一条 prompt、同一份工作区形状：8300 五个回合、多一次没必要的 `glob`、四个 `tool_calls` 回合 `content` 全空；`deepseek-chat` 三个回合、会叙述、把每条的 `TODO ` 前缀去掉了还在末回合自己说明这处偏离。而日志形状、工具派发、退出码、一轮两个调用完全一致——**差异全在模型行为层，harness 层没有一处 provider 分支**。且「有没有照吩咐做」这一层 harness 看不见：日志只记录它做了什么
- Evidence: `docs/verification/m4-real-provider-manual.md` 的差异表与两个 session id
- Next use: M5 之后的人手验收记录固定分两栏：harness 层（必须一致，出现差异就是缺陷）与模型层（允许不同，只观察不修）
- Promotion candidate: AGENTS.md 完成判据那句（本轮不晋升，先看 M3 的验收是否也需要这个分栏）
- Status: closed（2026-10-22 `fix-compaction-and-context-overflow` 收尾消化已关闭：两栏记录——harness 层必须一致、模型层只观察——已在三份 manual 成型，真实那一半由 agent 跑完并已成为完成判据，不再是「等人跑」的那一半。Status 行当时没跟着改，2026-10-24 补齐）

### L-026
- Date: 2026-10-18
- Context: 用 PowerShell 把 DeepSeek 会话日志摘要成逐回合表
- Observation: `switch ($_.type)` 的分支里 `$_` 换成了 switch 的主语（那个类型字符串），于是 `$_.payload` 与 `$_.seq` 全空，输出 13 行全空白——症状与「日志里没有内容」完全同形，差点误报成产品缺陷
- Evidence: 第一次摘要 13 行全空；改成 `foreach ($r in $recs) { $p = $r.payload; switch ($r.type) { … } }` 后同一份日志 13 行全对
- Next use: 在 `switch` 里访问原对象一律先赋给命名变量；与 Active 5 同族——读取端把真相弄错，不是被读的东西坏了
- Promotion candidate: 无需进 AGENTS.md（工具用法，不是项目规则）
- Status: merged into Active 5（2026-10-20 M5 开工前消化：与 L-022 同法并入，Active 5 已写「读也要显式 `-Encoding UTF8`」）

### M4 收尾轮的消化记录（2026-10-18，tasks 8.3）

先消化再收新条目：关闭 L-006（人手验收已是 AGENTS.md 的固定完成判据）、L-007（覆盖率三步走已写死在命令段）、L-012（环境事实已处置）、L-015（引用纪律已写死照 ADR-FORMAT）、L-020（`EventLog` 词表外塌缩有判据自证）；合并 L-016 → L-004、L-022 → Active 5。收件箱从 13 条降到 6 条（L-005 / L-014 / L-017 / L-018 / L-019 / L-021），收进 L-023 至 L-026 后是 10 条，仍在 15 条以内。

**AGENTS.md 本轮晋升一条**：L-023 的「捕获一整个异常类族的代码，判据要用族里不显眼的那个成员」进流程节的变异段；换掉的那条是变异段末尾的「做法与判据见 `docs/verification/` 下的记录」（同一句里已经写了记录去哪儿）。另有一处**事实修正**不算晋升：技术选型段的密钥那句改成「只走环境变量（默认 `DEEPSEEK_API_KEY`，`--api-key-env` 指定变量名）」——`--api-key-env` 是 M4 新加的 CLI 参数。

### L-027
- Date: 2026-10-19
- Context: M3 收尾变异轮 X1（`except OSError` 排在 `except TimeoutError` 之前）
- Observation: 定向跑 `tests/test_bash_tool.py tests/test_turn_cancel.py` 15 条全绿，看着像存活；跑全量才红。原因是 `bash` 自己把超时塌成结果词，dispatch 那条捕获只有 seam ② 的桩判据（`test_vocabulary_reachability.py`）经过——**判据在另一个 seam 上，定向跑看不见它**
- Evidence: `docs/verification/m3-bash-concurrency-timeout-mutation.md` 的「工具坑」一节；X1 行（全量杀 2 条）
- Next use: 变异一律跑全量；定向跑只用来定位哪条红。AGENTS.md 变异段本来就写着「跑全量测试」，这条是执行纪律，不是新规则
- Promotion candidate: 无需晋升（AGENTS.md 已写「跑全量测试」，本轮是没照自己写的做）
- Status: rejected（2026-10-20 M8 收尾消化：AGENTS.md 变异段本来就写着，M8 八条变异全部跑全量，没有新规则）

### L-028
- Date: 2026-10-19
- Context: M3 变异轮 T1（`DEFAULT_TIMEOUT_SECONDS = 30` → 45）与 O1（`<=` → `<`）
- Observation: 两条存活，形状不同但同源：规格里写死的**数值**没有判据钉着。T1 是默认值（上限有 `timeout_seconds: 601` 钉，默认值没人钉）；O1 是边界（已有判据只判「超限会被截」，等于上限被截它抓不到）。补完两条后端点从 2 个变 4 个：等于上限、多一字节、默认值、省略入参时实际拿到的值
- Evidence: 变异下的红：`assert 45 == 30`、`assert 16401 == 16384`（16384 + 17 字节的标记）；补测提交 `e4b03ea`
- Next use: 规格里出现数值（默认值、上限、超时、预算）就问一句「哪条判据会因为改这个数而红」；指不到就是缺口。与 L-017 同族：一条规则有多个输入维度时按维度逐个变异
- Promotion candidate: 与 L-005 同族（「规格里每条失败路径 Scenario 都要能指到一条测试」的数值版）；本轮不占 AGENTS.md 额度
- Status: merged into L-005（2026-10-20 M5 开工前消化：同一件事的「数值与边界」版。M5 的触发线 54272、尾部保留 16%、8192 预留都是规格里写死的数值，判据照 L-005 这一族写）

### L-029
- Date: 2026-10-19
- Context: M3 变异轮 P1（Windows 的 `taskkill /T /F /PID` → `process.kill()`）
- Observation: 超时那半边红（后代继续往工作区写），取消那半边是**挂住**：后代握着 stdout/stderr 的管道句柄，`await process.wait()` 永不返回，整条 session 卡在执行段里，全量跑不结束。「取消塌成结果词」隐含一个前提——**执行段一定会返回**，而返回取决于管道句柄全部关闭，不只取决于那个进程死没死
- Evidence: `docs/verification/m3-bash-concurrency-timeout-mutation.md` 的 P1 行与「P1 的附带事实」一节；两次全量跑被手动终止
- Next use: 任何 `asyncio` 子进程 + PIPE 的代码，收尾都要问「谁还握着这两个管道」；只杀父进程不等于执行段会返回
- Promotion candidate: 无需进 AGENTS.md（本仓 `bash` 工具与 asyncio 的具体行为，已由 ADR-0009 与那两条判据承载）
- Status: closed（2026-10-20 M5 开工前消化：已由 ADR-0009 与两条判据承载；「谁还握着管道」到 M10 补协作式取消时再查那份 ADR，不常驻收件箱）

### L-030
- Date: 2026-10-19
- Context: M3 6.4 往 `tests/test_cli_run.py` 插新测试
- Observation: 把新函数插在 `@pytest.mark.skipif(...)` 与它装饰的 `def` 之间，装饰器就挂到了新测试上：Linux-only 的 SIGINT 黑盒失去 skip、新写的 Windows 判据反而被 skip。两边都表现为「跑过了」——一条 deselected、一条 skipped，全量仍然绿
- Evidence: `-rs` 的 skip 摘要指向 `tests\test_cli_run.py:307`（新测试的 def 行）；修法是装饰器紧贴它装饰的那个 `def`
- Next use: 在带装饰器的测试之间插函数，锚点选装饰器**之前**那两行；新加 skip 类测试后跑一次 `-rs` 看 skip 落在谁身上
- Promotion candidate: 无需进 AGENTS.md（工具用法，不是项目规则）
- Status: rejected（2026-10-20 M8 收尾消化：本轮往 `tests/test_cli_run.py` 插两条 seam ⑥ 测试时照这条锚点纪律做了，没有新信号）

### M3 收尾轮的消化记录（2026-10-19，tasks 9.2）

先消化再收新条目：关闭 L-018（M3 裁决 Windows 真实 Ctrl-C 黑盒不在本 change 范围，缺口记进 `docs/verification/m3-bash-concurrency-timeout-manual.md`；那份 ConPTY 之外的 harness 仍然可用，但「M3 要用它」这条 next use 作废）；L-019 补一条同型证据（本轮 `git checkout --` 之后 edit 又报「file changed since it was read」三次，先 read 再 edit 才成）；L-005 与 L-017 保持收件箱，L-028 是它们的数值/边界版同族证据。

**AGENTS.md 本轮不晋升**：本轮最值钱的三条信号里，「变异必须跑全量」AGENTS.md 变异段本来就写着（L-027 是执行纪律，不是新规则）；「规格里的数值要有判据钉住」与 L-005 / L-017 同族，晋升要占一进一出的额度而额度现在没有空闲；「dud 判定」的 `started` 链那条（`_append_all` 是同步函数，所以「等前一个开始」不可观察）已被 L-004 晋升的那句「变异必须改变可观察行为」覆盖。

收件箱：12 条（L-005 / L-014 / L-017 / L-019 / L-021 / L-024 / L-025 / L-026 / L-027 / L-028 / L-029 / L-030），仍在 15 条以内。

### L-031
- Date: 2026-10-20
- Context: M8 tasks 2.1 → 5.5（`test_every_tool_outcome_is_reachable` 从词表加值那一刻起就红，要等 seam ① 的取消批次与 seam ④ 的折叠都落地才可能绿）
- Observation: 词表守卫判据的红是**结构性**的，不是实现写错了。硬按「一次一个红绿循环」走就会逼出一个假绿（先给 seam ② 造一个假生产者）。裁决是让它红着穿过四个任务组，代价是每个中间提交都必须自己说清楚：哪条判据红着、哪个 task 让它绿
- Evidence: `openspec/changes/m8-runtime-semantics-alignment/design.md` 的 D6 与 Migration Plan 第 5 步；提交 `ff0937a` / `7953165` / `39eed49` 的信息里各有一段写明这条红；5.5 的提交 `7336791` 让它转绿
- Next use: 守卫判据预计要跨任务组才转绿时，先把它写成裁决记进 design，再在每个中间提交的信息里复述「哪条红 / 谁让它绿」；不要为了门禁当场造一个假生产者
- Promotion candidate: 与 Active Lesson 1 同族（词表可达性）；本轮不占 AGENTS.md 额度
- Status: closed（2026-10-21 M5 收尾轮的消化记录已关闭它——它的预测兑现了：词表守卫确实红着穿过 1 到 5 组，每个中间提交都写明了谁让它绿。Status 行当时没跟着改，2026-10-24 补齐）

### L-032
- Date: 2026-10-20
- Context: M8 变异轮 D（`fold()` 的 `pending` 从局部列表换成模块级 `_PENDING`，折叠结束不清）
- Observation: 全量 **232 passed / 0 failed**——「同一份日志折叠两次逐字段相等」这条判据抓不到进程内残留。原因是它只喂一份输入，而那份输入里未配对的调用后面还跟着一条会产出消息的事件，折叠在中途就把 pending 冲掉并 `clear()`：**残留唯一显形的路径（只能靠收尾清掉的那条）没有被喂进去**
- Evidence: `docs/verification/m8-runtime-semantics-alignment-mutation.md` 的 D 一节；补法是把同一条判据改成判两份形状（`_half_log_events()` 与 `[:-1]`），变异下 `assert ['tool','assistant'] == ['assistant','tool','assistant']`
- Next use: 判「无状态 / 确定性」时至少两份输入：状态在中途被清掉的那份，和只能靠收尾清掉的那份
- Promotion candidate: 测试设计规则，与 Active Lesson 3（写下即绿就是危险信号）同族；本轮不占额度
- Status: closed（2026-10-21 M5 收尾轮的消化记录已关闭它：4.7 的确定性判据确实喂了两份输入，代码就是它的形状。Status 行当时没跟着改，2026-10-24 补齐）

### L-033
- Date: 2026-10-20
- Context: M8 变异轮 G（内核替未配对的 `tool/call` 在日志里编一条 `tool/result(TOOL_OUTCOME_UNKNOWN)`）
- Observation: 施加变异前先补判据，因为这条约束在旧判据集里**没有可观察落点**：run 正常跑完的批次里不存在未配对的调用（取消路径下未派发的有配对结果，围栏与写日志失败的路径下 `tool/call` 根本没写），唯一在 run 里留下未配对调用的形状是执行段逃出来的异常，而既有判据只判它不被改名成 `TOOL_CANCELLED`。证据是变异下全量跑到第 208 条才红、**前 207 条全绿**
- Evidence: `docs/verification/m8-runtime-semantics-alignment-mutation.md` 的 G 一节；新判据 `test_an_escaped_exception_leaves_the_call_unpaired_and_fold_closes_it`（seam ①）
- Next use: 写「MUST NOT 产生 X」这类否定式约束时先问「哪个 run 形状会让它被违反」；指不到就把判据写在读方（折叠 / replay）而不是内核，或者补一个能跑出那个形状的场景
- Promotion candidate: 与 Active Lesson 1 / 3 同族（可达性、写下即绿）；本轮不占额度
- Status: closed（2026-10-21 M5 收尾轮的消化记录已关闭它：M5 的三条否定式约束都先找到了能违反它的 run 形状。Status 行当时没跟着改，2026-10-24 补齐）

### L-034
- Date: 2026-10-20
- Context: M8 tasks 6.1 写 seam ⑥ 的硬杀判据
- Observation: 硬杀判据有三条形状约束，缺一条就会变成不可靠或留孤儿：杀点**由日志定位**（轮询到那条挂着的调用的 `tool/call` 落盘才杀，它出现时命令一定在跑），断言**只挑与杀点无关的性质**（每行独立可解析、文件以换行结尾、落了的记录字段齐全），挂着的命令**自己会在有限时间后结束**（`for _ in range(100): time.sleep(0.1)`），否则硬杀之后它是永远不回的孤儿
- Evidence: `tests/test_cli_run.py` 的 `_hard_kill_a_run()`；变异 F（结果回到批次末缓冲）正是被这条判据杀死
- Next use: M15（OS 级拦截）与任何要判「进程被硬杀之后日志什么形状」的判据都照这三条写
- Promotion candidate: 无需进 AGENTS.md（判据写法，不是项目规则）
- Status: closed（2026-10-20 M5 开工前消化：那三条形状约束已在 `tests/test_cli_run.py` 的 `_hard_kill_a_run()` 里成型，M15 直接照代码写，不需要这条常驻）

### L-035
- Date: 2026-10-20
- Context: M8 tasks 7.2 跑 `openspec validate --all --strict`
- Observation: `uv run openspec ...` 报 `error: Failed to spawn: openspec` / `Caused by: program not found`——`openspec` 是全局 CLI，不在本项目的 uv 依赖里。AGENTS.md 的命令块只列了四道门禁（都走 `uv run`），OpenSpec 那几条命令要直接跑全局命令
- Evidence: 本轮 tasks 7.2 的记录；`openspec validate --all --strict` 直接跑是 `Totals: 9 passed, 0 failed (9 items)`
- Next use: OpenSpec 系列命令不加 `uv run` 前缀
- Promotion candidate: 无需进 AGENTS.md（工具用法）
- Status: closed（2026-10-20 M5 开工前消化：M8 之后每轮都直接跑全局 `openspec`，M5 的 propose 轮再次确认没有再踩；AGENTS.md 命令段只列四道门禁，不占额度）

### M8 收尾轮的消化记录（2026-10-20，tasks 8.3）

先消化再收：L-027 关闭为 `rejected`（AGENTS.md 变异段本来就写着「跑全量测试」，本轮变异八条全部跑全量，没有新规则）；L-030 关闭为 `rejected`（在带装饰器的测试之间插函数的锚点纪律，本轮新增两条 seam ⑥ 测试时照做了，没有新信号）。L-028 与 L-005 / L-017 同族保持收件箱；本轮 L-032 与 L-033 是它们在读方与否定式约束上的同族证据。

**AGENTS.md 本轮不晋升**：一进一出的额度没有空闲，而本轮三条最值钱的信号里，「守卫判据可以红着穿过中间任务」与 Active Lesson 1 同族、「确定性判据要判到清理的那条路径」与 Active Lesson 3 同族、「否定式约束要先找到能违反它的 run 形状」是 L-005 那条已晋升规则的镜像面——三条都不够新到值得挤掉现有五条里的任何一条。

收件箱：15 条（L-005 / L-014 / L-017 / L-019 / L-021 / L-024 / L-025 / L-026 / L-028 / L-029 / L-031 / L-032 / L-033 / L-034 / L-035），到 15 条上限；下一个 change 收尾先消化再收。本轮关闭两条：L-027、L-030。

### M5 开工前的收件箱消化（2026-10-21，apply 之前）

收件箱 15 条已到上限，按收敛纪律先消化再收。本轮不是里程碑收尾：只消化，不收新条目。

**合并三条**：L-017 与 L-028 并入 L-005——同一件事的三个面（失败路径 / 输入维度 / 数值与边界），L-005 做家族头；L-026 并入 Active Lesson 5（与 L-022 同法）。

**关闭六条**（已被代码、规格或 ADR 自证）：L-014（AGENTS.md 命令段的判据已按实测写成退出码）、L-021（手测脚手架的三条形状已在 `docs/verification/` 成型）、L-024（ADR-0006 与「适配器不继承代理环境变量」承载）、L-029（ADR-0009 与两条判据承载，M10 补协作式取消时再查）、L-034（`tests/test_cli_run.py` 的 `_hard_kill_a_run()` 就是它的代码形状）、L-035（全局 `openspec` 已成习惯，M5 的 propose 轮确认）。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：一进一出的额度没有空闲，而本轮没有新信号。L-025 的「人手验收记录分 harness 层与模型层两栏」要等 M5 的 8.1 真跑过一次真实模型再决定——凭 M4 一次观察就晋升，正是 Active Lesson 3 警告的那种「写下即绿」。

留存的 6 条对 M5 直接有用，实现时照它们做：

- **L-005（家族头）**：触发线 54272、尾部保留 16%、`reserve` 8192、`--window` 默认 128000 都是规格里写死的数值，每条都要指到一条「改这个数就红」的判据。
- **L-019**：变异轮每次 `git checkout --` 之后先 read 再 edit。
- **L-025**：8.1 的验收记录分两栏（harness 层必须一致，模型层只观察不修）。
- **L-031**：1.1 的词表守卫判据预计红着穿过 1 到 5 组（`CONTEXT_WINDOW_EXCEEDED` 要等 5.5 才可达），每个中间提交写明哪条红、谁让它绿。
- **L-032**：4.7 的确定性判据至少喂两份输入，其中一份的遮蔽只能靠收尾那条记录清掉。
- **L-033**：M5 有一批否定式约束（「MUST NOT 写 `compaction/summary`」「MUST NOT 覆盖 `session/start`」「MUST NOT 拆散配对」），先找出能违反它的那个 run 形状再写判据。

收件箱：6 条（L-005 / L-019 / L-025 / L-031 / L-032 / L-033），额度回到 9 条空闲。

### L-036
- Date: 2026-10-21
- Context: M5 组 5 写 `test_overflow_when_nothing_can_be_shadowed` 里 `error/context` 的 detail 断言，8.1 人手验收时暴露
- Observation: 那条断言写成 `assert error.payload == {"turn_id": "t1", "code": ..., "detail": error.payload["detail"]}`——待判的值同时写在两侧，恒真。人手验收读 stderr 时才看见真正的缺陷：没有发生压缩的回合，stderr 写的是「压缩之后预算读数 …」
- Evidence: 换成两条判前缀的断言（「无可遮蔽的内容」/「压缩之后」），先红后绿；`docs/verification/m5-context-budget-compaction-manual.md` 的「这一栏里发现的一处缺陷」
- Next use: 断言的一侧必须是常量或另一个来源的值；user-visible 文案的判据判「措辞与日志事实一致」
- Promotion candidate: 是四规 #4「把任务写成可验证的判据」的收紧，本轮不占额度
- Status: closed（2026-10-24 `fix-chat-screen-feedback` 收尾消化：那条纪律已是 seam ⑥ 写判据的默认形状——本轮补强的四条判据都从日志记录里取值再判屏幕上的那一行（1.3 取 `error/context` 的 `detail`、围栏那条取 `error/fence` 的 `code`、1.8 判 `[降不下去]` 不在日志里、serve 那条比对 `splitlines()`），没有再出现「待判的值写在两侧」。承载它的是判据本身，不需要常驻收件箱）

### L-037
- Date: 2026-10-21
- Context: M5 变异轮准备阶段读到 `shadowed_range` 的尾部累加器
- Observation: 把一处实现改对（`total = _record_chars(last)` → `total = _tokens(_record_chars(last))`）之后跑全量测试**283 条全绿**——没有任何判据注意到这个差别。这与 L-033 那条「变异下前 207 条全绿」是同一个信号的另一面：不只变异存活是缺口，**修复不引起任何红也是缺口**
- Evidence: `docs/verification/m5-context-budget-compaction-mutation.md` 的「一处存活的变异变成一处真 bug」；补的判据放回变异下确认它红，再还原
- Next use: 任何时候「修完 bug 全量全绿」都当覆盖缺口处理，补一条能区分对错的判据并确认它在旧实现下红
- Promotion candidate: 与 AGENTS.md 变异段「存活的算覆盖缺口」同族，本轮不占额度
- Status: inbox

### L-038
- Date: 2026-10-21
- Context: 同 L-037，`context/budget.py` 里 `_record_chars` 与 `_tokens` 的交界处
- Observation: 同一个累加器里混字符与 token，mypy strict 抓不到（两边都是 `int`），测试也抓不到（结果只是「遮蔽得多了一点」）。名字带单位是唯一防线，混用点必须有判据钉住
- Evidence: `src/mini_harness/context/budget.py` 的 `total = _tokens(_record_chars(candidates[-1]))`；判据 `test_the_tail_budget_is_counted_in_tokens_not_characters`（窗口 9375 → 保留预算 1500 token，尾部 4000 字符 + 100 字符 = 1025 token 装得下 → 无可遮蔽）
- Next use: 任何「按 token 计」的预算代码都让单位出现在名字里，并在边界值上写判据
- Promotion candidate: 与 L-005 家族（数值与边界）同族
- Status: merged into L-005（2026-10-22 M6 收尾消化：M6 没再动 `budget.py` 的字符 / token 交界，那条判据 `test_the_tail_budget_is_counted_in_tokens_not_characters` 仍在门禁里钉着；剩下的「边界值上写判据」就是 L-005 这一族）

### L-039
- Date: 2026-10-21
- Context: M5 组 6 / 组 7 里那批「写出来就是绿的」守卫判据（400 的另两种形状、发生过压缩的日志逐点重放、新事件类型的词表可达）
- Observation: 变异 6（任何 400 都算上下文超限）被三条测试杀死，其中两条正是那批绿着写出来的守卫——它们的价值到变异轮才兑现。与 L-031（守卫红着穿过中间任务）是同一件事的两面：红着写与绿着写都算数，前提是在提交信息里如实标注它不是红绿对
- Evidence: `docs/verification/m5-context-budget-compaction-mutation.md` 变异 6；`test_a_400_with_any_other_error_code_is_still_an_http_status_result`、`test_a_400_with_an_unreadable_body_is_still_an_http_status_result`
- Next use: 既有行为的守卫照写，提交信息里写明「这条写出来就是绿的，它是防下一步把分类改宽的守卫」
- Promotion candidate: 与 L-031 同族，本轮不占额度
- Status: inbox

### L-040
- Date: 2026-10-21
- Context: M5 task 8.1 搭人手验收的工作区
- Observation: harness 的 pwsh 子进程里，命令行上写中文路径会被编码掉：`Get-Content -Raw -Encoding UTF8 "docs\DSH逆向分析报告.md"` 报「找不到路径」，而同一个文件用 `Get-ChildItem docs -Filter 'DSH*.md'` 或内置 read / glob 工具都正常
- Evidence: 本轮搭 `.tmp/m5-manual/ws` 时的第一次尝试
- Next use: 命令行上不写非 ASCII 路径；要读非 ASCII 文件名就走内置工具或 ASCII 通配符
- Promotion candidate: 工具用法，无需进 AGENTS.md
- Status: merged into L-049（2026-10-22 M7 收尾消化：同一族——命令行与环境层的工具坑。M7 在同一族里又踩三处，合成一条 L-049；「命令行上不写非 ASCII 路径」这一格由 L-049 的 Next use 承载）

### M5 收尾轮的消化记录（2026-10-21，tasks 8.3）

**关闭三条**：L-031（它的预测兑现了——词表守卫确实红着穿过 1 到 5 组，每个中间提交都写明了谁让它绿，M5 的提交信息就是承载）、L-032（4.7 的确定性判据确实喂了两份输入，代码就是它的形状）、L-033（M5 的三条否定式约束都先找到了能违反它的 run 形状：溢出回合没有 `model/request`、遮蔽范围不覆盖 `session/start`、切点落组内时整组一起遮蔽）。

**留存三条**：L-005（家族头，M5 的数值判据都挂在它下面）、L-019（本轮变异轮又踩到「file changed since it was read」，规则仍然在起作用）、L-025（两栏记录已成型，但模型层那一半要等人类跑完才能判断它是否值得晋升）。

**新收五条**：L-036 到 L-040。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：本轮最值钱的三条（L-036 断言两侧不能同源、L-037 修复不引起红也是缺口、L-039 绿着写出来的守卫照写）都是四规 #4 与变异段现有句子的收紧，不是新规则；一进一出的额度要留给真正独立的内容。

收件箱：8 条（L-005 / L-019 / L-025 / L-036 / L-037 / L-038 / L-039 / L-040），额度空闲 7 条。

### L-041
- Date: 2026-10-21
- Context: M9 变异轮，编号 5「payload 里的 `model` 取 provider 名」
- Observation: 存在性断言与值断言是两种判据。`test_the_endpoint_fields_are_in_the_payload` 只断言三条字段在不在，「值取错了」这一类坏法它杀不掉（该变异下它存活）；同族里判值的两条把它补上了。只写前者等于把「取错值」这一整类坏法放行
- Evidence: `docs/verification/m9-assembly-and-config-layering-mutation.md` 变异 5（三条红、4.2 存活）；`test_openai_run_records_base_url_model_and_the_key_variable_name` 判值
- Next use: 写「字段在不在」的判据时同时问一句「值错了这条还红吗」；不红就补判值的断言，或确认同族已有判值的判据
- Promotion candidate: 与 L-036（断言两侧不能同源）同族
- Status: inbox（家族头：L-041 判值不判在 / L-053 投影规则的另一半。2026-10-24 收 L-053 进来）

### L-042
- Date: 2026-10-21
- Context: M9 变异轮，同一个变异（白名单被忽略）先跑定向、后跑全量
- Observation: 定向轮杀七条、全量轮杀九条，多出来的两条在别的 seam（① 的「白名单空表时工具调用是 UNKNOWN_TOOL」、④ 的「无工具折叠与 replay 相符」）。跨 seam 的判据在定向轮里看不见——「收尾跑全量」的收益是可测量的，不是仪式
- Evidence: 同上文档变异 3（定向）与变异 11（全量）
- Next use: 中途的定向轮只用来确认「这条判据不是空的」，里程碑收尾必须全量重跑一遍并记下差多少条
- Promotion candidate: AGENTS.md 变异段本来就写着「跑全量测试」，本轮不占额度
- Status: rejected（2026-10-22 `fix-compaction-and-context-overflow` 收尾消化已关闭为 rejected：AGENTS.md 变异段本来就写着。Status 行当时没跟着改，2026-10-24 补齐；本轮变异轮照 L-027 / L-042 这条改跑全量，见「本轮没照自己写的做」那条）

### L-043
- Date: 2026-10-21
- Context: M9 人手验收第一次写 `mini.config.toml`
- Observation: PowerShell 5.1 的 `Set-Content -Encoding UTF8` 写出的 UTF-8 带 BOM，`tomllib` 不吃，报错是「Invalid statement (at line 1, column 1)」——把人指向语法而不是编码。Windows 上记事本与 PowerShell 5.1 的默认 UTF-8 都带 BOM，所以「手写一份配置」这条路第一次是断的
- Evidence: `docs/verification/m9-assembly-and-config-layering-manual.md` 别扭第 1 条；`docs/adr/0018-config-is-three-layer-override.md` 的 Consequences
- Next use: 读用户会手写的文本输入（配置、导入文件）时，先确认它实际会遇到的编码方言；报错文案要指认编码而不是只抄解析器的话
- Promotion candidate: 与 L-011 家族（错误消息要指认原因）同族
- Status: inbox

### L-044
- Date: 2026-10-21
- Context: M9 组 5 与组 6 往测试文件尾部追加判据时
- Observation: `edit` 的 `old_string` 以「下一条语句的开头那行」作结尾、`new_string` 里没把它补回，就把那条语句的正文粘到了上一条之后（语法错误或直接少一个 `def`）。M9 内踩到三次，两次要靠重读区间补回 `def` 行。追加式编辑的正确锚点是「上一条的结尾」，不是「下一条的开头」
- Evidence: 本轮 `tests/test_cli_provider.py` 与 `tests/test_turn_loop.py` 的两次返工（`test_a_dead_endpoint_collapses_into_a_transport_result` 的正文一度孤儿化）
- Next use: 用 `edit` 插入内容时，锚点选上一段的末行；若必须以下一段作锚，就把那一行原样写进 `new_string`
- Promotion candidate: 工具用法，无需进 AGENTS.md
- Status: merged into L-019（2026-10-22 M6 收尾消化：同一件事——`edit` 的锚点纪律。M6 往 `tests/test_cli_chat.py` 与 `tests/test_cli_run.py` 插判据时照「上一条末行作锚、必要时把下一行原样写回」做了，没再踩；本轮另记一次反向错误进 L-019）

### L-045
- Date: 2026-10-21
- Context: M9 task 6.3 与 6.5 的前置条件
- Observation: 两处计划里的事实与规格 / 环境不符：tasks.md 写了第七个失败码 `MISSING_API_KEY`，规格定的是 stderr 含 `INVALID_ARGUMENT`（密钥判据是 CLI 层参数错误，不是 `ConfigFailure` 的一员）；人手验收要造「密钥设为空串」，PowerShell 5.1 里 `$env:X = ""` 是**删除**变量，那个形状在 shell 里造不出来。判据的前置条件要在写判据之前核实，不是写完再发现
- Evidence: `openspec/changes/m9-assembly-and-config-layering/tasks.md` 6.3 的改判行；manual 文档「设为空串那一半在 PowerShell 5.1 里造不出来」
- Next use: 计划里的枚举值先对齐规格再写判据；人手验收造不出来的形状，写明由哪条门禁判据代劳
- Promotion candidate: 与 L-004 家族（先确认它真的会坏 / 真的能造）同族
- Status: inbox（2026-10-24 补一条本轮证据：tasks 5.1 的前置条件写错一处——以为 `--window 3000 --reserve 100` 会跑出溢出，实际 `--window` 必须大于 `--reserve + 65536`，否则在 session 开始之前就是退出码 2（`INVALID_ARGUMENT: … 没有剩余压力预算`），scratch 那两条溢出判据因此「跑崩」成「日志里没有日志」。改成 `--window 70000 --reserve 100`（触发线 4364）加一条把预算读数推到 5027 的系统提示才可达。判据的前置条件在写之前先跑一次真实命令）

### L-046
- Date: 2026-10-21
- Context: M9 的 6.5 模型层那一半，人跑的第一场
- Observation: runbook 只写「工作区根一份配置」，没写这份配置该装什么、也没写跑下一场之前要把它换掉。于是场景 E 留下的 `tools = ["read", "web_search"]` 还在工作区根，模型层的第一场 run 在发出任何请求之前就以退出码 2 失败。跨 run 生效的工件（配置文件、fixture、工作区目录）在 runbook 里要逐场写明内容与场间重置方式，否则下一场撞的是上一场的失败
- Evidence: `docs/verification/m9-assembly-and-config-layering-manual.md`「第一次尝试的实际结果」与「别扭在哪」第 5 条
- Next use: 写多场手动验收的 runbook 时，每场给出工件内容与场间重置命令
- Promotion candidate: 与 L-045 同族（前置条件先核实）
- Status: closed（2026-10-22 `fix-compaction-and-context-overflow` 收尾消化已关闭：多场手动验收逐场写工件内容与场间重置的形状已在 M6 / M7 与那一轮的 manual 成型。Status 行当时没跟着改，2026-10-24 补齐。本轮的 UAT 手册照它写：三场各给一条可粘贴命令、`--session-dir` 与 `--window` 的具体数值、以及「窗口那一栏」那条前置条件）

### M9 收尾轮的消化记录（2026-10-21，tasks 7.2）

**关闭零条**：本轮没有自证的旧条目——L-036 / L-037 / L-038 是 M5 新收的，M9 没跑到它们的路径上；L-025（两栏记录）仍等人类跑完模型层那一半。

**留存八条**：L-005（家族头）、L-019（本轮又踩「file changed since it was read」两次，规则仍在起作用）、L-025（等人类）、L-036 / L-037 / L-038 / L-039 / L-040（M9 的 6.1–6.3 与 6.5 都按它们行事：6.1 的断言两侧不同源、变异 12 的失败输出照 L-037 记、配置文件的单位与编码按 L-038 / L-043 处理）。

**新收五条**：L-041 到 L-045。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：本轮最值钱的三条（L-041 存在性 vs 值、L-042 定向轮覆盖面、L-045 前置条件先核实）都是四规 #4 与变异段现有句子的收紧，不是新规则；L-043 与 L-044 分别是产品事实与工具用法，去处是 ADR 与本文件。

收件箱：13 条（L-005 / L-019 / L-025 / L-036 / L-037 / L-038 / L-039 / L-040 / L-041 / L-042 / L-043 / L-044 / L-045），额度空闲 2 条。

**归档后补记（2026-10-21，M9 的 6.5 模型层第一次尝试）**：新收一条 L-046（runbook 没写明跨 run 生效的工件与场间重置），收件箱 **14 条**、空闲 1 条；AGENTS.md 不晋升——这条的去处是 `docs/verification/` 的 runbook 写法，不是全局规则。

### L-047
- Date: 2026-10-21
- Context: M6 收尾 8.1 的 Spec 轴，主规格 context-projection 的「每次模型调用前记录 `context/assembled`」
- Observation: 带全称量词的 Requirement 只按「正常回合」那一条路径核对过，就漏掉两条不写快照的调用：带 `purpose` 的摘要调用（M5 起就没有快照）与请求级压缩之后的重试（M6 新加）。M5 的审查轴同样没抓到。核对的正确单位是**实现里那个动作的调用点清单**，不是规格里的 scenario 清单
- Evidence: `turn_loop.py` 里 `provider.generate` 三处调用，核对时逐点看「前面有没有快照」；补的 MODIFIED Requirement 与判据在提交 `013e469`，取舍记进 `docs/adr/0019-overflow-closes-the-turn-and-the-entry-decides-the-session.md` 的裁决段
- Next use: 写或审「每次 X 之前都写 Y」「所有 A 都 B」这类 Requirement 时，先 grep 出实现里那个动作的全部调用点，逐点问「这条路径写了吗」；没写的路径要么补写，要么在规格里写明它是「不写的那一个」
- Promotion candidate: 与 Active Lesson 2 不同族，是「规格 ↔ 实现怎么核对」的方法；本轮不占 AGENTS.md 额度
- Status: inbox

### L-048
- Date: 2026-10-22
- Context: M6 变异轮三条存活变异（stdout 的 `purpose` 过滤 / `session/end.turns` / 窗口校验 `<= 0`）
- Observation: 三条存活同形：既有判据覆盖的是**这个入口常见的形状**，缺口在「这个入口里从没发生过的那件事」与「边界那一格」。chat 的判据里从来没有一次真压缩，所以「摘要那条不打」在 seam ⑥ 上没人守；`turn_index - 1` 减不减所有断言都一样；三个测试窗口（32768 / 4096、70000 / 4096、66000 / 100）都不落在 0 上
- Evidence: `docs/verification/m6-chat-repl-mutation.md` 的变异 3 / 5 / 8 与「补的判据」一节（四条新判据，每条在变异下先确认红）
- Next use: 新入口（M7 的 `serve`、M10 的委派）落地后，把 run 与 chat 各自钉住的事件形状——压缩、溢出、取消、启动期失败——在新入口里各补一条判据；边界判据要含「恰为 0」与「恰为上限」
- Promotion candidate: 与 L-005 家族（数值与边界）同族，本轮不占额度
- Status: inbox

### M6 收尾轮的消化记录（2026-10-22，tasks 8.3）

**合并两条**：L-044 并入 L-019（同一件事——`edit` 的锚点纪律）、L-038 并入 L-005（「边界值上写判据」就是数值与边界那一族）。

**留存十二条**：L-005（家族头，M6 三条存活变异挂在它下面）、L-019（本轮又踩两次）、L-025（模型层那一半仍等人类跑完 runbook）、L-036（M6 两条 user-visible 文案判据都判前缀常量）、L-037（M6 没有「修完不引起红」的事件）、L-039（本轮两条 chat 守卫按它如实标注为守卫）、L-040（M6 的手动脚手架全程 ASCII 路径，没再踩）、L-041（M6 补的 `entry` 判据正是判值的断言）、L-042（本轮 12 个变异全部跑全量，没有定向轮）、L-043（配置文件的 BOM 仍未裁决，与 ADR-0018 的 Consequences 一起待办）、L-045（M6 的 tasks 6.3 一类前置条件都先对齐规格再写判据）、L-046（M6 的 manual 文档照它逐场写工件内容与场间重置）。

**Active Lesson 1 补一条证据**（不占收件箱额度）：M6 新增的 `session/start.payload.entry` 有两个取值，实现之后只有 `chat` 那一半有判据——变异「不写 `entry`」只让 chat 那条变红，`run` 那一半到变异轮才补上。「每个值可达」在新增的 payload 字段上同样成立，且**两个入口各要一条**。

**新收两条**：L-047、L-048。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：一进一出的额度只剩 1 条空闲，而本轮三条候选（L-047 全称量词按调用点核对、L-048 新入口要重跑旧入口的事件形状、`entry` 两个值各一条判据）分别是 Active Lesson 1 / 2 与 L-005 家族的收紧，不是独立的新规则。

**提交纪律的欠账记进 ADR-0002，不在这里立规则**：`cf1543d` / `0f49b39` 没有门禁行，`62ccd00` / `0afa628` / `ce87b9a` 只记了四道里的一到两道。AGENTS.md「一次提交算完成 = 四道全绿」本来就写着，本轮是没照自己写的做，属执行纪律不是新规则。

收件箱：14 条（L-005 / L-019 / L-025 / L-036 / L-037 / L-039 / L-040 / L-041 / L-042 / L-043 / L-045 / L-046 / L-047 / L-048），空闲 1 条。

### L-049
- Date: 2026-10-22
- Context: M7 组 9 人手验收的脚手架（`.tmp/m7_serve_demo.py` 驱动三个 `minihns serve` 子进程）与 seam ⑥ 那 23 条 httpx 判据
- Observation: 三处都不是代码缺陷，是本机环境，且每一处都先伪装成缺陷。① 驱动脚本起的孙进程继承 pwsh 的管道句柄时，外层 `… | Out-String` 永远等不到 EOF，第一次跑法在 240 s 超时里卡死；把孙进程的 stdout / stderr 重定向到文件、只把驱动自己的输出送进管道，才通。② 本机有 `HTTP_PROXY=http://127.0.0.1:7897` 与 `NO_PROXY=localhost,127.0.0.1,::1,[::1]`（大小写各一份，重复键连 `Get-ChildItem env:` 都报「已添加了具有相同键的项」），httpx 默认 `trust_env=True`，把 `[::1]` 当 host:port 解析，当场 `InvalidURL: Invalid port: ':1]'`——一整轮判据红在与 serve 无关的地方。③ 对一个还没开始监听的 loopback 端口发起 TCP connect，本机不是立刻被拒而是黑洞到超时：把 fixture 从 16 KB 放宽到 40 MB（会话日志全程 9 ms）都没救回「溢出那一场连上客户端」。④（2026-10-22 收尾轮补）密钥的作用域：人在自己的终端里 `$env:DEEPSEEK_API_KEY = …` 只影响那一个会话，agent 的子进程继承的是 harness 进程的环境块，`Process` 作用域里没有它——「agent 的子进程没有密钥」这句话因此把 M6 与 M7 的模型层 runbook 各压了一个里程碑。值在 `User` 作用域里时，每次调用前显式取一次 `$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")` 就进得去
- Evidence: `.tmp/m7-manual/report.txt` 第 3 场记为「无客户端」；`docs/verification/m7-serve-http-sse-manual.md` 别扭第 1 与第 3 条、模型层那一节；`tests/test_cli_serve.py` 的 `_read_stream` 与 `_get` 里的 `trust_env=False`；缺口记进 `docs/adr/0002-deferred-refactors.md` 第 55 条。④ 的实测：`User` 作用域有值、`Process` 作用域没有，注入后 `https://api.deepseek.com/v1/models` 返回 200，M6 两场与 M7 一场模型层 runbook 跑通
- Next use: seam ⑥ 的 HTTP 客户端一律 `trust_env=False`；人手验收的驱动脚本把子进程输出重定向到文件、不接管道；写「会话进行中能连上」这类判据之前先在本机测一次 connect 行为，测出来是黑洞就不要写这条判据，改记缺口；跑模型层 runbook 之前先探密钥作用域与端点（`/v1/models` 只打状态码与模型 id），别照旧 runbook 里那个手上没有密钥的端点写
- Promotion candidate: 工具与环境事实，去处是 runbook 写法与 ADR，不是全局规则
- Status: inbox（收 L-040 进来：同一族，M7 又踩三处。2026-10-24 本轮再补三格，每一格都先伪装成产品缺陷：① `… | Out-String` 与 Python 把 stdout 重定向到文件时的块缓冲，都会把 scratch 脚本的进度憋到进程结束才出现，第一次以为脚本挂死；② 一边开着读流线程、一边 `Popen.communicate()`，两者抢同一根管道，stderr 被吃掉一半——`[段] ABORTED` 因此「看不见」，第一次把它当成实现没打；③ 提示符不再自带换行之后，任何 `readline()` 式同步永远等不到行尾（真实端点验收的第一版在 R5 上死锁 20 分钟，子进程 0 CPU 挂着）。干净形状：子进程输出重定向到文件、只有一根读流、同步一律用轮询而不是等行）

### L-050
- Date: 2026-10-22
- Context: M7 组 2 实现 `ServeServer.bind()`，task 2.5「端口被占」那条判据
- Observation: aiohttp 3.14 要求 `runner.setup()` 先于构造 `TCPSite`，顺序写错第一次跑就 `RuntimeError: Call runner.setup() before making a site`（`BaseSite.__init__` 在 `runner.server is None` 时抛）。2.5 的红不是断言不符而是 exit 1。这类错误在正常路径上看不见：绑定成功、会话跑完、事件流正常，只有失败路径才经过 `runner.cleanup()` 那一段。2.1 到 2.4 的实现照正常路径写完，一路绿到 2.5 才暴露
- Evidence: 提交 `b862ed2` 的提交信息（「2.5 的红不是断言不符而是 exit 1」）；`src/mini_harness/cli/serve.py` 的 `bind()` 把 `runner.setup()` 与 `site.start()` 一起包进 `try / except OSError`；判据 `test_an_occupied_port_fails_before_the_session_starts`
- Next use: 引入新库或新外部依赖时先写「它失败时怎样」的判据（端口被占、连接被拒、文件读不动），再写正常路径；失败路径没有判据，构造顺序与清理顺序的错误就一路绿到线上
- Promotion candidate: 与四规 #4「修 bug 先写能复现它的测试」同族，本轮不占 AGENTS.md 额度
- Status: closed（2026-10-24 `fix-chat-screen-feedback` 收尾消化：`bind()` 的构造与清理顺序已由 `src/mini_harness/cli/serve.py` 的实现与 `test_an_occupied_port_fails_before_the_session_starts` 承载；本 change 没引入新外部依赖，也没有新的失败路径缺口。规则本身是四规 #4，不占额度）

### M7 收尾轮的消化记录（2026-10-22，tasks 10.3）

**合并一条**：L-040 并入 L-049（同一件事——命令行与环境层的工具坑；M7 在同一族里踩到三处，比 M5 那一处更值钱）。

**留存十三条**：L-005（家族头；M7 的 `--port` 上界与 `--host` 词表判据挂在它下面，变异 7 与 11 正是「改这个数就红」）、L-019（变异轮全程用 `edit` 还原、每次先 read 再 edit，没再踩也没省）、L-025（M7 的 manual 照它分 harness 层与「待人跑的那一半」，模型层仍等人类跑完 9.2）、L-036（10.1 加强的那条「游标超前」判据两侧不同源：一侧是 SSE 帧的 `id`，一侧是 `read_events` 读出的日志 `seq`）、L-037（M7 没有「修完不引起红」的事件；`9c226ee` 删的是不可达分支，全绿是应有结果）、L-039（M7 有八条绿着到的守卫，全部在提交信息里如实标注，变异 5 / 6 / 15 兑现了其中三条的价值）、L-041（M7 的 `entry` 与 `prompt` 判据是判值的断言，不是判存在的）、L-042（本轮 15 个变异里 14 个跑全量、1 个定点，定点那条在 mutation 文档里写明只跑 `tests/test_cli_serve.py` 与其代价）、L-043（配置文件的 BOM 仍未裁决，与 ADR-0018 的 Consequences 一起待办）、L-045（M7 的 4.4 与 10.1 两处「规格 ↔ 实现分叉」都是先对齐规格再改判据：游标允许 0、`--http` 保留但可选）、L-046（M7 第 2 场第一次跑红在 `log_records()` 断言「只有一份日志」——上一场的 stale log 没清；runbook 从此写明场间 `Remove-Item -Recurse -Force` 那一行）、L-047（M7 的 `tasks.md` 写「sync 六份 delta 主规格」，这个 change 实际只有四份 delta：`cli` / `turn-loop` / `bash-tool` / `event-stream`——全称量词与计数都要按工件清单核对）、L-048（**第二次复发**：`entry` 在 M7 只有 seam ① 的判据，变异 8 把 `ENTRY_SERVE` 换成 `ENTRY_RUN` 时 21 条 serve 判据一条都不红，10.1 才补上 seam ⑥ 那两条）。

**Active Lesson 1 补一条证据**（不占收件箱额度）：`SessionEntry` 加了第三个值 `serve`，seam ① 的「每个值可达」判据当场就写（1.2），但「这个值在 CLI 黑盒里长什么样」到 10.1 才补上——词表加一个值，seam ① 与 seam ⑥ 各欠一条判据，不是只欠一条。

**新收两条**：L-049、L-050。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：本轮三条候选都不是独立的新规则——L-050 是四规 #4 在「新外部依赖」上的收紧，L-049 是工具与环境事实（去处是 runbook 与 ADR-0002 第 55 条），L-048 是 Active Lesson 1 与 L-005 家族的收紧。**但 L-048 已复发两次**（M6 变异 10、M7 变异 8），若 M10 的委派入口再复发一次，它就是这个额度该给的那一条：规则草案「新入口的判据必须落在新入口自己的 seam 上，进程内直调不算」。

**提交纪律的欠账记进 ADR-0002，不在这里立规则**：规划提交 `8a5cb14` / `414ccf4` 没有门禁行；`fd1986a` 声明 6.1–6.3 却带着 6.4 的判据，紧随的 `3d85b11` 自述「与上一个提交同一份工作树」——一个红绿循环拆成两个提交、门禁只跑一次；`d5231b8` 跨 seam ② 与 ⑥ 加文档打包且没写理由。都在 `docs/adr/0002-deferred-refactors.md` 的「M7 的提交纪律欠账」一节。

收件箱：15 条（L-005 / L-019 / L-025 / L-036 / L-037 / L-039 / L-041 / L-042 / L-043 / L-045 / L-046 / L-047 / L-048 / L-049 / L-050），**到 15 条上限**：M10 收尾先消化再收新条目。

### L-051
- Date: 2026-10-22
- Context: `fix-compaction-and-context-overflow` 的 propose 与 task 5.4（真端点跑 `minihns chat`）
- Observation: 模型相关功能的失败形状只有真实端点会给，而 M5 之后每个里程碑的完成判据里都没有那一行。实测到的 400 是 `{"error": {"type": "invalid_request_error", "message": "prompt (222233 tokens) leaves no room to answer in the context (196608); requests are never truncated"}}`——**没有 `error.code`**，而 provider 主规格与那 400 条 mock 判据只认 `error.code == "context_length_exceeded"`。此前不是没跑过真实那一半：M5 量到估算偏小 2.24 倍、M6 场 2 两段都溢出、M7 的 C 场小窗口溢出客户端挤不进去——三条观察都记进了 `docs/verification/`，**没有一条回灌成判据**
- Evidence: `tests/fixtures/real_endpoint/context_overflow_400.json`（来源 session `92c155ba16fb4a4aa7bcbf931d5ba098`）与 `compaction_summary.json`（session `d31a7790e92c49fcb47d9a5dc8b25636`）；`docs/adr/0022-model-features-need-a-real-endpoint-gate.md`；`docs/verification/fix-compaction-and-context-overflow-manual.md`
- Next use: 依赖模型回复形状的里程碑，`tasks.md` 里要有一条「真实端点跑一次」的复选框（不进 CI，但不跑完这个 change 不算完成）；CI 层的判据读真实产物 fixture，不用手编桩数据猜形状
- Promotion candidate: AGENTS.md 完成判据那句（本轮晋升）
- Status: promoted

### L-052
- Date: 2026-10-22
- Context: 同一 change 的 task 5.2 与 5.4
- Observation: 「同一压缩记录在屏幕上报两遍」这个缺陷，400 条 mock 判据全绿抓不到，真端点那一跑第一次撞出来。形状差在**段数与每段的输入数**：那些 seam ⑥ 判据每段只喂一条输入、只有一段，而「每段重读整份日志、没卡游标」这种坏法只在「多段且某段有多条输入」时才显形
- Evidence: 修前那条判据红在 `assert 0 == 1`；变异「去掉 `event.seq <= through` 这条线」下红在 `assert 2 == 1`（`docs/verification/fix-compaction-and-context-overflow-mutation.md` 第 6 行）；真 run 的 stderr 里那一行原文出现两遍，记在 manual
- Next use: REPL 类入口（chat、M10 的委派）的 seam ⑥ 判据至少两条输入、跨两个段；任何「每段都重读全量状态」的实现，判据要能区分「重读」与「重报」
- Promotion candidate: 与 L-048 同族（入口常见的形状 ≠ 入口里从没发生过的那件事），本轮不占额度
- Status: inbox（2026-10-24 补一条本轮证据，方向相反但同源：**判据的形状比人做的事更狠**。1.6 那条判据为了撞进几毫秒的缝隙「一次 Ctrl-C 之后连送到进程退出为止」（40 次），mock 那一半 5/5 全绿；真实端点那一跑按同样形状 3/3 拿到 `0xC000013A`，而「人按一次 Ctrl-C」的形状 3/3 是退出码 0。连发越过了「会话收尾」这条边界、跑到解释器收尾里去了。真实那一半不只是补模型形状，也量出 mock 判据的形状偏离人的动作多远）

### L-053
- Date: 2026-10-23
- Context: 同一 change 的 `code-review` Spec 轴与 task 8.4
- Observation: chat-repl 的 delta 从 propose 起就写着「遮蔽反馈不是日志的投影」，可判据只断言「这一行不在 stdout、不在日志」。投影规则的另一半——**同一份日志的 `minihns replay` 输出不因它改变**——没有任何判据；实现那一半本来就是对的，缺口只在判据侧，所以四道门禁全绿也查不出来
- Evidence: 补的判据 `test_a_chat_that_compacted_replays_the_same_log_unchanged`（seam ⑥：真跑一次 chat 让 `[遮蔽]` 出现在 stderr，再对同一份日志跑 `minihns replay`，判退出码 0、stdout 与 stderr 里没有那一行、没有 `REPLAY_MISMATCH`）；Spec 轴的报告写明那条场景没有判据
- Next use: 写「某一行只出现在屏幕上」这类判据时，把「日志的重放方与折叠方看不见它」一起写成断言；投影规则的两半都要有判据
- Promotion candidate: 与 L-041 同族（判据要判值对不对，不是判有没有一行），本轮不占额度
- Status: merged into L-041（2026-10-24 `fix-chat-screen-feedback` 收尾消化：同一件事——「有一行」与「重放方看不见它」都是「判据只判了一半」。本轮的两条 chat 判据把两半一起判（1.7 判 id 不在任何一条记录的 payload 里、1.8 判那句说明不在 stdout 也不在日志），没有新形状）

### `fix-compaction-and-context-overflow` 收尾轮的消化记录（2026-10-22，tasks 6.4 与 7.3）

**关闭三条**：L-042 关闭为 `rejected`（与 L-027 同一理由——AGENTS.md 变异段本来就写着「跑全量测试」；本轮 6 个变异里 2 条跑全量、4 条定点，差多少条已在 mutation 文档写明）；L-046 关闭（「多场手动验收逐场写工件内容与场间重置」的形状已在 M6 / M7 与本轮的 manual 里成型，本轮照它写 `.tmp/realchat/` 那一份）；L-025 关闭（两栏记录——harness 层必须一致、模型层只观察——已在三份 manual 成型，AGENTS.md 完成判据那句承载；它「等人类跑完模型层那一半」的前提也变了：本轮真实端点那一半由 agent 跑完、并且从此是完成判据，不再是等人跑的那一半）。

**留存十二条，各补一条本轮证据**：L-005（本轮两个写死的数值都有「改它就红」的判据：`summary_budget = window - reserve` 与 `_DETAIL_MAX_CHARS = 200`，变异 3 红在 `assert 1119 <= 200`）、L-019（又踩两次：一次 `old_string matched 4 times`——两条 chat 判据共用同一段 fixture 块；一次 `ruff format` 之后 edit 报 not found）、L-036（chat 遮蔽判据的 needle 四个数取自日志读出的那条记录，不是把常量抄进断言两侧）、L-037（「修完重复报两遍」之后全量全绿——正是它警告的那种缺口，补强判据后在变异下确认红）、L-039（4.2 的实现一次覆盖了三种收尾理由，4.3 的三条判据绿着到；tasks.md 与提交信息里如实写明红是怎么临时收窄 `_SEGMENT_NOTE_REASONS` 验出来的）、L-041（遮蔽判据判的是那四个值对不对，不是「stderr 里有没有一行」）、L-043（配置文件的 BOM 仍未裁决）、L-045（5.3 的字面措辞在实现里做不到——chat 判据读不到 fixture，改判成 seam ① 读 fixture，写明在 tasks.md 与提交信息里，没有含糊过去）、L-047（delta 写「三种收尾理由都看得见」，按实现里那个理由集合核对才发现真 run 撞出的第四种 `FENCE_DENIED` 不在其中）、L-048（本轮第一次让 chat 在 seam ⑥ 上真发生一次压缩，正是 M6 变异 10 那个缺口）、L-049（新实例：PowerShell 把子进程 stderr 包成 ErrorRecords、同一行显示两遍，第一次读真 run 时把它当成实现缺陷；干净流要 `cmd /c "… < in > out 2> err"`）、L-050（本轮没有新外部依赖，没有新证据）。

**AGENTS.md 本轮晋升一条**：L-051 的「依赖模型回复形状的功能，完成判据里要有一次真实端点实测」进流程节的完成判据那句。一进一出换掉的是 ruff 例外那句里的括号（「本项目的 docstring / 注释 / 用户可见字符串一律用中文全角标点」——仓库实况已经在这么做，「例外只有两处」那条规则本身留着）。

**本轮的提交纪律有欠账**（这一句 2026-10-23 更正过，原来写的是「没有欠账」）：`14a7b48` 与 `1bc5e94` 两个规划提交只有 `openspec validate` 那一行；`34dd4e8` 与 `c7df1d1` 完全没有门禁行，后者是实现提交；`e5ad72f` 打包 7.1–7.2 与 6.4 + 7.3 跨三个 seam 且没写打包理由；变异轮（7.2）与 Learning Gate（7.3）跑在 `code-review` 两轴之前。逐条记在 `docs/adr/0002` 的「`fix-compaction-and-context-overflow` 的提交纪律与流程欠账」一节。红绿循环本身没有违例：两处打包（5.1–5.2 与 5.3–5.5）按「同一 seam 相邻至多 3 个 task」拆开，跨 seam 那一处的理由写在提交信息里。

收件箱：13 条（L-005 / L-019 / L-036 / L-037 / L-039 / L-041 / L-043 / L-045 / L-047 / L-048 / L-049 / L-050 / L-052），空闲 2 条；L-051 已晋升、不占额度。

### `fix-compaction-and-context-overflow` 两轴之后的消化记录（2026-10-23，tasks 8.1–8.9）

**四条裁决都落成了判据**：8.1 的 `FENCE_DENIED` 段（seam ⑥，真红过——`assert len(notes) == 1` 实得 0 行）；8.2 的孤儿 `tool` 消息（seam ①，真红过——摘要请求里的角色序列是 `system / tool / assistant / tool / user`，那条 `tool` 没有请求它的 `assistant`）；8.3 的 500 与 429（seam ⑤，**绿着到的**：`openai_compat.py` 里重试耗尽那条早退本来就挡住了 5xx 与 429，`status >= 400` 那一处从来没有可达的 5xx——当场用一处变异确认它们不空转，两条都红在 `assert 'PROVIDER_CONTEXT_OVERFLOW' == 'PROVIDER_HTTP_STATUS'`）；8.4 的 chat 日志逐点重放（seam ⑥，补的是 propose 起就缺的那半条判据）。

**第二轮变异（tasks 8.7）跑全量**：十条变异全部被杀死、无存活、无 dud，基线 **408 passed / 5 skipped**。两条新判据各自杀掉打它的那条变异（8 号「把 `FENCE_DENIED` 也压掉」只红在 `test_a_fence_denied_segment_says_so_on_stderr`；9 号「裁剪改回逐条丢」只红在 `test_the_summary_trim_drops_whole_round_trips`）。上一轮定点跑的六条这一轮全部改跑全量——代价就是违「两轴在变异之前」的那笔账。

**新收一条**：L-053（屏幕上那一行的判据要连重放方一起判：「不在 stdout、不在日志」只判了投影规则的一半）。
**补证据五条**：L-047（本轮人裁决定把 delta 那句改成**反面集合**——「不以 `MODEL_COMPLETED` / `ABORTED` 收尾就打」；正面清单每加一种收尾理由就漏一种，`FENCE_DENIED` 就是这么漏的）；L-039（8.3 那两条绿着到，靠变异确认不空转，与 M6 / M7 那两节「绿着到的守卫」同一形状）；L-037（两轴查出的判据缺口全部补在实现之后，必须在变异下重跑一遍才算数——这就是 tasks 8.7 存在的原因）；L-048（本轮第二次让 chat 在 seam ⑥ 上真发生压缩，并第一次把那份日志交给 `minihns replay` 判）；L-052（8.4 那条判据只喂一条输入：它判的是「重放看不见」，不是「跨段重报」，所以不违这条）。
**更正一句**：上面那条「本轮的提交纪律没有欠账」写错了，五条欠账记进 `docs/adr/0002` 的本 change 两节；实质违例是变异轮与 Learning Gate 跑在两轴之前。

**AGENTS.md 本轮不晋升**：L-053 与 L-041 同族（判据要判对不对，不是判有没有），L-047 的反面集合那条要等它在下个 change 里真的省下一次漏判才值得占额度。

收件箱：14 条（L-005 / L-019 / L-036 / L-037 / L-039 / L-041 / L-043 / L-045 / L-047 / L-048 / L-049 / L-050 / L-052 / L-053），空闲 1 条。

### 判据加严与 M5 / M6 / M7 重新验收的消化记录（2026-10-23，ADR-0024）

**人裁决的原话**：「决策 21『mock 优先』，和 ADR-0005 里『mock 桩绿等于里程碑完成』的读法，合出来的效果就是：mock 桩数据通过 = 判据通过，真实那一半是可选动作。一定修正，钉死 mock+真实数据都要测试通过才算验收通过作为硬判据，mock 只是方便进行小单元测试和冒烟，整体验收测试还是需要真实数据。还有 M5-M6-M7 要重新验收」。落档 **ADR-0024**，AGENTS.md 完成判据那句重写为「两半」，`openspec/config.yaml` 的 `rules.tasks` 加一条「末尾固定三项收尾」，ADR-0022 末尾加指路标记。**这一笔不是 lesson 晋升**：它由人裁决驱动、加严的是既有那句规则，一进一出没有动用；本轮为容纳新增内容压缩了 AGENTS.md 两处（流程节的「变异测试一轮 + Learning Gate」改成「收尾三项（见下 Learning Gate）」，ADR-0022 那句压成 12 字），**95 行 / 4824 字 → 95 行 / 4795 字**。

**重新验收跑完三份**（`docs/verification/m5-context-budget-compaction-reacceptance.md`、`m6-chat-repl-reacceptance.md`、`m7-serve-http-sse-reacceptance.md`）：M5 四条判据全过、M7 两条全过、M6 除「Ctrl-C 取消一个回合」（等人）外全过。真实端点是本机 Strata（`http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`，`n_ctx` 196608），密钥逐条命令从用户作用域注入。

**这一跑查出的硬事实（比"通过"更值钱的部分）**：**「压缩发生了但仍然不够」这条分支在当前预算形状下不可达。** 三次溢出（session `70fa85600d484109b2f266506ee24c42` 读数 5933 / 触发线 4364、session `8de532bbf9d045d58ca3cf56cd55c7ad` 一次 `read` 得 424,641 字符 ≈ 106,161 估算 token / 触发线 34364，另加 2026-10-22 那次 4393）全部走「无可遮蔽」。机制在 `context/budget.py` 第 200 至 211 行：保留尾部从最后一条候选起算，`_round_end` 把切点推到整组工具往返之后，落点越过最后一条候选就返回 `None`。算术上一样：一次压缩成功后的表层不超过「头部 + 摘要 + `retain_line`」，`retain_line = 0.16 W`、预算 `W - reserve`，前者要超过后者需 `reserve > 0.84 W`，而那时 `trigger_line = max(0, W - reserve - 65536) = 0`，压缩不会开始。**M5 的完成判据写着「压缩仍不够」，它从来没有、也暂时不可能以字面形状被跑到**——这条判据的真实形状就是小窗口死区的落点，已作为那个 change 的第一条证据。判据的字面措辞与可达形状对不上，是判据侧的欠账，不是实现的。

**新收一条**：L-054（真实端点验收要故意把会话做长，否则「断线续读」这类判据是空跑）。
**补证据两条**：L-049（新实例：`uv run minihns serve … 1>… 2>…` 两次都让 pwsh 作业报 `[exit code: 1]`，而会话日志是 `MODEL_COMPLETED` 收尾、SSE 帧完整；换成 `cmd /c "… 1>… 2>…"` 同一会话报 **0**——判 CLI 退出码不能读 pwsh 包装层那一位）；L-048（第三次让 chat / serve 在 seam ⑥ 上真发生压缩与真事件流，第一次把它用于**重新验收已归档的里程碑**而不是新 change）。

**AGENTS.md 本轮不晋升 lesson**（理由见上：改的是人裁决加严的那句，不是新 lesson）。

**同日第二条裁决（ADR-0025）**：「UAT 验收应该成为门禁之一」。人手验收从 ADR-0005 的「另有一条…它不替代任何一条判据」升成**第五道门禁**，完成判据成三半；通过信号是 `docs/verification/<change-id>-uat.md` 的观察表填完，没填完不得归档、不得合入 `main`，tty 场次 agent 不得代跑；UAT 场次骨架在 propose 阶段立，让人与实现同步跑。**这一笔的教训形状**：一条规则写成「另有一条」就会被执行成可选动作——M5 / M6 / M7 的实现、门禁、真实端点判据全绿，而「等人跑」那一半里装着只有人能判的东西（Ctrl-C 取消一个回合、提示符退出、屏幕上那一行），拖了三条里程碑没落地。**规则要有通过信号与阻塞后果，否则它不是门禁。**

收件箱：15 条（L-005 / L-019 / L-036 / L-037 / L-039 / L-041 / L-043 / L-045 / L-047 / L-048 / L-049 / L-050 / L-052 / L-053 / L-054），空闲 0 条——**已到上限，下个 change 收新条之前先消化**。

### L-054
- Date: 2026-10-23
- Context: M7 `m7-serve-http-sse` 真实端点重新验收，断线续读那两条判据
- Observation: 第一次 serve 会话 8 秒内跑完（模型把「三次 read」合成一次调用），第二个客户端连上去时端口已关（`WinError 10061`），「读到 seq n 断开再带 `Last-Event-ID: n` 重连」这条判据在真实端点上**空跑**——不是失败，是根本没被执行到。把会话做长之后（一次 `read` 取 `big.md` 全 2,000 行，`tool/result` 259,136 字符，把第二个回合的模型调用拉长到几十秒）四条连接都在会话内完成，续读与 `?from` 覆盖都读到
- Evidence: `.tmp/reacc/m7_client2.py` 与 `.tmp/reacc/m7_client3.py` 两次对照：前者第一次 `second=0 frames` 报 10061，后者 `full=[0..15] cut=[0..6] resume=[7..15] override=[3..15]`、比对脚本 `problems=0`
- Next use: 真实端点验收里凡是要「在会话进行中」做的事（断线重连、中途读日志、并发连接），先估会话时长并把会话故意做长；会话太短造成的空跑要在记录里写明是空跑，不能记成通过
- Promotion candidate: 与「判据要能真的被执行到」同族（L-037 / L-039 那一族：绿着到不等于判据跑过），本轮不占 AGENTS.md 额度
- Status: inbox（2026-10-24 补一条本轮证据：真实端点验收的 R5 与 R9 都照它把会话做长——R5 用「不带 `--yes` 的批准请求」把段停在派发之前，R9 用 `--max-turns 1` 让会话自己收尾，两条都在会话进行中读到 `session/end`；R9 第一次跑成空跑，原因正是会话太短、Ctrl-C 落在它已经结束之后）

### L-055
- Date: 2026-10-24
- Context: `fix-chat-screen-feedback` 的 task 5.1 真实端点验收，判据 1.6（提示符上 Ctrl-C 不留 traceback）那一半
- Observation: **判据的形状比人做的事更狠，而只有真实那一半量得出来。** 1.6 在 seam ⑥ 的形状是「一次 Ctrl-C，之后连着送到进程自己退出为止」（收尾缝隙只有几毫秒，单次信号撞不稳）：mock 那一半 5/5 全绿、退出码 0。真实端点按同样形状跑 3/3 拿到 `0xC000013A`（STATUS_CONTROL_C_EXIT），而「人按一次 Ctrl-C、之后照常 EOF」的形状 3/3 是退出码 0。两种形状下日志都是 `session/start` → `session/end`、都没有 traceback、`session/end` 都是 `MODEL_COMPLETED`——差别只在最后那几毫秒里有没有 Python 层的 SIGINT 处理器在场（CPython 在解释器收尾中把 SIGINT 换回默认处置）。连发撞毫秒级缝隙会越过「会话收尾」这条边界，把解释器的边界算成产品的失败
- Evidence: `.tmp/real-endpoint/probe_r6.py` 的对照（burst=0 → 退出码 `[0, 0, 0]`；burst=40 → `[3221225786, 3221225786, 3221225786]`）与 `docs/verification/fix-chat-screen-feedback-real-endpoint.md` 的「R6 那一半」一节；判据本身 `test_ctrl_c_at_the_prompt_ends_the_session_without_traceback`
- Next use: 要撞毫秒级缝隙的判据优先用可注入的同步点（收尾那段里放一个可等待的事件）而不是连发信号；这类判据跑真实端点时把「单次」与「连发」两种形状都跑一遍、分开记，并写明哪一种对应人的动作
- Promotion candidate: 与 L-052 同族（判据的形状与人的动作之间的距离），本轮不占 AGENTS.md 额度
- Status: inbox

### `fix-chat-screen-feedback` 收尾轮的消化记录（2026-10-24，tasks 5.4）

**先消化再收**（上一轮写明「已到上限」）。关闭三条：L-036（断言两侧不同源已是 seam ⑥ 写判据的默认形状，本轮补强的判据都从日志记录里取值再判屏幕上那一行）、L-050（`bind()` 的构造与清理顺序由实现与 `test_an_occupied_port_fails_before_the_session_starts` 承载，本 change 没有新外部依赖）、L-053 并入 L-041（「有一行」与「重放方看不见它」是同一件事——判据只判了一半；L-041 作家族头）。**另补齐六条 Status 行**：L-025 / L-031 / L-032 / L-033 / L-042 / L-046 早在 2026-10-21 与 2026-10-22 的消化记录里就关闭了，条目自己的 Status 行没跟着改；本轮核对全表（54 条条目 / 54 行 Status）后补齐，收件箱的真实数字因此比上一轮记的 15 条少。

**新收一条**：L-055（判据的形状比人做的事更狠：连发 40 次 Ctrl-C 撞进毫秒级缝隙，真实那一跑 3/3 拿到 `0xC000013A`，而单次 Ctrl-C 3/3 是退出码 0）。

**补证据五条**：L-019（变异脚手架用 `read_text` / `write_text` 改源文件，Windows 文本模式把 LF 换成 CRLF，还原检查当场报「还原失败」——改按字节读写才干净）、L-045（tasks 5.1 的前置条件写错：`--window 3000` 在 session 开始之前就是退出码 2，`--window` 必须大于 `--reserve + 65536`）、L-049（三格脚手架坑，每一格都先伪装成产品缺陷：`Out-String` 与块缓冲把进度憋到进程结束、读流线程与 `communicate()` 抢同一根管道吃掉 stderr、提示符不带换行之后 `readline()` 永远等不到行尾）、L-052（本轮的方向相反但同源：mock 判据的形状比人的动作更狠）、L-054（R5 / R9 都靠把会话做长才撞进「会话进行中」，R9 第一次是空跑）。

**AGENTS.md 本轮不晋升（NO-PROMOTION）**：本轮三条候选都不是独立的新规则——L-055 与 L-052 同族（形状之间的距离），L-019 的「按字节读写源文件」与 L-049 的三格都是工具与环境事实（去处是 `docs/verification/` 与本文件的家族头，不是全局规则），变异轮「定向 14 条 + 三条跑全量、差 0 条」的测量正是 L-042 关闭时说的「AGENTS.md 变异段本来就写着」。一进一出的额度没有动用。

**本轮的流程记账两条**（如实写，不改写历史）：① 变异轮 14 条里 11 条只跑三条 CLI 判据文件，AGENTS.md 变异段写的是「跑全量测试」；三条代表性变异（M1 / M3 / M13）改跑全量对照，红数与定向轮相同、差 **0 条**，测量记进 `docs/verification/fix-chat-screen-feedback-mutation.md`。② `backup-before-split`（`cfe0a1f`）与 `7d8845d` 的逐行差异不止「重新打包」：一行重复的注释、`_overflow_entries` 的提取、一条 docstring 措辞——split 顺带收了 fixture 重复，这件事 `docs/adr/0002` 第 630–631 行已经记着，本轮核对后确认无误；备份分支留着不删，等人裁决。

**本轮没照自己写的做的一处**：5.2 的 UAT 手册立起来了、三场命令与观察表都在，但**表是空的**——那一半要人跑。按 ADR-0025，这张表没填完本 change 不得归档、不得合入 `main`；A（`30bb7cf`）、B（`96abe4a`）、D（`5910a5c`）三条也卡在同一张表上。

收件箱：13 条（L-005 / L-019 / L-037 / L-039 / L-041 / L-043 / L-045 / L-047 / L-048 / L-049 / L-052 / L-054 / L-055），空闲 2 条。

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）
- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
