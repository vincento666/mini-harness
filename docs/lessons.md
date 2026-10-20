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
- Status: inbox

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
- Status: inbox

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
- Status: inbox

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
- Status: inbox

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
- Status: inbox

### L-025
- Date: 2026-10-18
- Context: M4 7.1 / 7.2 两个端点跑同一条任务
- Observation: 同一条 prompt、同一份工作区形状：8300 五个回合、多一次没必要的 `glob`、四个 `tool_calls` 回合 `content` 全空；`deepseek-chat` 三个回合、会叙述、把每条的 `TODO ` 前缀去掉了还在末回合自己说明这处偏离。而日志形状、工具派发、退出码、一轮两个调用完全一致——**差异全在模型行为层，harness 层没有一处 provider 分支**。且「有没有照吩咐做」这一层 harness 看不见：日志只记录它做了什么
- Evidence: `docs/verification/m4-real-provider-manual.md` 的差异表与两个 session id
- Next use: M5 之后的人手验收记录固定分两栏：harness 层（必须一致，出现差异就是缺陷）与模型层（允许不同，只观察不修）
- Promotion candidate: AGENTS.md 完成判据那句（本轮不晋升，先看 M3 的验收是否也需要这个分栏）
- Status: inbox

### L-026
- Date: 2026-10-18
- Context: 用 PowerShell 把 DeepSeek 会话日志摘要成逐回合表
- Observation: `switch ($_.type)` 的分支里 `$_` 换成了 switch 的主语（那个类型字符串），于是 `$_.payload` 与 `$_.seq` 全空，输出 13 行全空白——症状与「日志里没有内容」完全同形，差点误报成产品缺陷
- Evidence: 第一次摘要 13 行全空；改成 `foreach ($r in $recs) { $p = $r.payload; switch ($r.type) { … } }` 后同一份日志 13 行全对
- Next use: 在 `switch` 里访问原对象一律先赋给命名变量；与 Active 5 同族——读取端把真相弄错，不是被读的东西坏了
- Promotion candidate: 无需进 AGENTS.md（工具用法，不是项目规则）
- Status: inbox

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
- Status: inbox（与 L-017 同族，M5 若再出现同类就合并）

### L-029
- Date: 2026-10-19
- Context: M3 变异轮 P1（Windows 的 `taskkill /T /F /PID` → `process.kill()`）
- Observation: 超时那半边红（后代继续往工作区写），取消那半边是**挂住**：后代握着 stdout/stderr 的管道句柄，`await process.wait()` 永不返回，整条 session 卡在执行段里，全量跑不结束。「取消塌成结果词」隐含一个前提——**执行段一定会返回**，而返回取决于管道句柄全部关闭，不只取决于那个进程死没死
- Evidence: `docs/verification/m3-bash-concurrency-timeout-mutation.md` 的 P1 行与「P1 的附带事实」一节；两次全量跑被手动终止
- Next use: 任何 `asyncio` 子进程 + PIPE 的代码，收尾都要问「谁还握着这两个管道」；只杀父进程不等于执行段会返回
- Promotion candidate: 无需进 AGENTS.md（本仓 `bash` 工具与 asyncio 的具体行为，已由 ADR-0009 与那两条判据承载）
- Status: inbox

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
- Status: inbox

### L-032
- Date: 2026-10-20
- Context: M8 变异轮 D（`fold()` 的 `pending` 从局部列表换成模块级 `_PENDING`，折叠结束不清）
- Observation: 全量 **232 passed / 0 failed**——「同一份日志折叠两次逐字段相等」这条判据抓不到进程内残留。原因是它只喂一份输入，而那份输入里未配对的调用后面还跟着一条会产出消息的事件，折叠在中途就把 pending 冲掉并 `clear()`：**残留唯一显形的路径（只能靠收尾清掉的那条）没有被喂进去**
- Evidence: `docs/verification/m8-runtime-semantics-alignment-mutation.md` 的 D 一节；补法是把同一条判据改成判两份形状（`_half_log_events()` 与 `[:-1]`），变异下 `assert ['tool','assistant'] == ['assistant','tool','assistant']`
- Next use: 判「无状态 / 确定性」时至少两份输入：状态在中途被清掉的那份，和只能靠收尾清掉的那份
- Promotion candidate: 测试设计规则，与 Active Lesson 3（写下即绿就是危险信号）同族；本轮不占额度
- Status: inbox

### L-033
- Date: 2026-10-20
- Context: M8 变异轮 G（内核替未配对的 `tool/call` 在日志里编一条 `tool/result(TOOL_OUTCOME_UNKNOWN)`）
- Observation: 施加变异前先补判据，因为这条约束在旧判据集里**没有可观察落点**：run 正常跑完的批次里不存在未配对的调用（取消路径下未派发的有配对结果，围栏与写日志失败的路径下 `tool/call` 根本没写），唯一在 run 里留下未配对调用的形状是执行段逃出来的异常，而既有判据只判它不被改名成 `TOOL_CANCELLED`。证据是变异下全量跑到第 208 条才红、**前 207 条全绿**
- Evidence: `docs/verification/m8-runtime-semantics-alignment-mutation.md` 的 G 一节；新判据 `test_an_escaped_exception_leaves_the_call_unpaired_and_fold_closes_it`（seam ①）
- Next use: 写「MUST NOT 产生 X」这类否定式约束时先问「哪个 run 形状会让它被违反」；指不到就把判据写在读方（折叠 / replay）而不是内核，或者补一个能跑出那个形状的场景
- Promotion candidate: 与 Active Lesson 1 / 3 同族（可达性、写下即绿）；本轮不占额度
- Status: inbox

### L-034
- Date: 2026-10-20
- Context: M8 tasks 6.1 写 seam ⑥ 的硬杀判据
- Observation: 硬杀判据有三条形状约束，缺一条就会变成不可靠或留孤儿：杀点**由日志定位**（轮询到那条挂着的调用的 `tool/call` 落盘才杀，它出现时命令一定在跑），断言**只挑与杀点无关的性质**（每行独立可解析、文件以换行结尾、落了的记录字段齐全），挂着的命令**自己会在有限时间后结束**（`for _ in range(100): time.sleep(0.1)`），否则硬杀之后它是永远不回的孤儿
- Evidence: `tests/test_cli_run.py` 的 `_hard_kill_a_run()`；变异 F（结果回到批次末缓冲）正是被这条判据杀死
- Next use: M15（OS 级拦截）与任何要判「进程被硬杀之后日志什么形状」的判据都照这三条写
- Promotion candidate: 无需进 AGENTS.md（判据写法，不是项目规则）
- Status: inbox

### L-035
- Date: 2026-10-20
- Context: M8 tasks 7.2 跑 `openspec validate --all --strict`
- Observation: `uv run openspec ...` 报 `error: Failed to spawn: openspec` / `Caused by: program not found`——`openspec` 是全局 CLI，不在本项目的 uv 依赖里。AGENTS.md 的命令块只列了四道门禁（都走 `uv run`），OpenSpec 那几条命令要直接跑全局命令
- Evidence: 本轮 tasks 7.2 的记录；`openspec validate --all --strict` 直接跑是 `Totals: 9 passed, 0 failed (9 items)`
- Next use: OpenSpec 系列命令不加 `uv run` 前缀
- Promotion candidate: 无需进 AGENTS.md（工具用法）
- Status: inbox

### M8 收尾轮的消化记录（2026-10-20，tasks 8.3）

先消化再收：L-027 关闭为 `rejected`（AGENTS.md 变异段本来就写着「跑全量测试」，本轮变异八条全部跑全量，没有新规则）；L-030 关闭为 `rejected`（在带装饰器的测试之间插函数的锚点纪律，本轮新增两条 seam ⑥ 测试时照做了，没有新信号）。L-028 与 L-005 / L-017 同族保持收件箱；本轮 L-032 与 L-033 是它们在读方与否定式约束上的同族证据。

**AGENTS.md 本轮不晋升**：一进一出的额度没有空闲，而本轮三条最值钱的信号里，「守卫判据可以红着穿过中间任务」与 Active Lesson 1 同族、「确定性判据要判到清理的那条路径」与 Active Lesson 3 同族、「否定式约束要先找到能违反它的 run 形状」是 L-005 那条已晋升规则的镜像面——三条都不够新到值得挤掉现有五条里的任何一条。

收件箱：15 条（L-005 / L-014 / L-017 / L-019 / L-021 / L-024 / L-025 / L-026 / L-028 / L-029 / L-031 / L-032 / L-033 / L-034 / L-035），到 15 条上限；下一个 change 收尾先消化再收。本轮关闭两条：L-027、L-030。

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）

- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
