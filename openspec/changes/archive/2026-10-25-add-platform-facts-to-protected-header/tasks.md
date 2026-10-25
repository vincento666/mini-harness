# Tasks

## 1. 工具面那条事实（seam ②）

- [x] 1.1 红：写一条 seam ② 的测试，断言 `bash` 工具面暴露它实际用来执行命令的 shell 形态，且该形态与它起进程时实际用的那条一致（本机是 `cmd.exe /c`）。先确认它在当前实现下红。绿：让 `tools/bash_tools.py` 提供这份事实，CLI 不自己判平台。门禁四道全绿。
- [x] 1.2 红：写一条 seam ② 的测试，断言这份事实不是可配置性——工具注册表与配置层叠都不接受对它的覆盖。绿：确认它天然不可配置，或补上拒绝路径。门禁四道全绿。
- [x] 1.3 红：seam ② 断言 `glob` / `grep` / `read` 三个描述各带一句「什么时候用我」的引导（列目录 / 搜内容 / 读文件），并点明别用 `bash` 的等价命令、也别临时写脚本。绿：改三个描述。门禁四道全绿。
- [x] 1.4 红：seam ② 断言 `bash` 的描述把列目录与搜内容指给 `glob` 与 `grep`，且四个描述**都不含** `dir` / `findstr` / `Get-Content` 这类平台专用字样（ADR-0030）。绿：改 `bash` 描述。门禁四道全绿。

## 2. `session/start` 记下平台事实（seam ⑥）

- [x] 2.1 红：seam ⑥ 黑盒跑一次 `minihns run`，断言 `session/start` 的 payload 里 `platform` 含非空的 `os` 与 `shell`，且 `shell` 与该日志里 `bash` 实际执行用的形态一致。绿：CLI 把它写进 payload。
- [x] 2.2 红：seam ⑥ 黑盒分别跑 `chat`（EOF 退出）与 `serve`，断言两份日志都有 `platform` 且两处的 `os` 与 `shell` 相同。绿：三个入口走同一条装配路。
- [x] 2.3 红：seam ⑥ 断言 `platform` 不出现在命令行开关表与配置文件的合法键表里（`--help` 里没有它、配置文件里写它是既有那条「配置文件只接受这些键」的失败形状）。绿：确认没有为它开可配置性。

## 3. 折叠头部多一块（seam ④）

- [x] 3.1 红：seam ④ 断言折叠结果的受保护头部里多一块运行环境，内容含 `os` 与 `shell`，位置在内置常量与工具块之后、`--append-system-prompt` 的追加文本之前；`header_fingerprint` 覆盖它。绿：`_start_facts` 读回、`protected_header` 拼这块。
- [x] 3.2 红：seam ④ 断言「命令输出按 UTF-8 解码、非法字节显示为替换字符」那句说明随这块一起出现，且它是关于 harness 自己的说明、不是猜测出来的平台事实。绿：把它固定在那一块里。
- [x] 3.3 红：seam ④ 逐点重放一份带 `platform` 的新日志，断言每个装配点与该记录逐字段相等。绿：确认派生只依赖该点之前的前缀。
- [x] 3.4 红：seam ④ 同一份会话骨架分别记 `os: nt` + `shell: cmd.exe /c` 与记 `os: posix` + `shell: /bin/sh -c`，断言前者点出 `dir` / `findstr` / `Get-Content`、后者点出 `ls -R` / `grep` / `tail`，且各自不把对方的命令说成可用；判据跑在哪个平台上都一样（ADR-0029）。绿：建议由 `platform` 推出，不读 `process.platform`。
- [x] 3.5 红（2026-10-25 UAT 之后加的一条）：seam ④ 断言那块建议里 `glob` 的位置在 `dir`（记 posix 时是 `ls -R`）之前——原生工具排在 shell 命令之前，同一件事不能两处说法。绿：改两句建议的措辞，事实与建议的推出方向不变。门禁四道全绿。

## 4. 旧日志不受影响（seam ④ + ⑥）

- [x] 4.1 红：seam ④ 折叠一份 `session/start` 没有 `platform` 的日志，断言头部只有内置常量、工具块与追加文本，`header_fingerprint` 与该记录里的一致，且没有为缺失事实填入猜测值。绿：缺失时不产出这块。
- [x] 4.2 红：seam ⑥ 对一份既有 fixture 日志跑 `minihns replay`，断言每个装配点 `verified … OK`、退出码 0、没有 `REPLAY_MISMATCH`。绿：确认旧日志的字节与折叠结果都不变。

## 5. 既有判据对齐（seam ④ / ⑥）

- [x] 5.1 跑全量测试，把因头部多一块而红的判据逐条改判据（不改实现来迁就 fixture）；提交信息里列出改了哪几条、为什么。门禁四道全绿。
  - 实况：一条都没红。既有会话骨架（`tool_harness.build_session_env` 与各处 `SessionSettings`）走的是「没有 platform 就是没有这份事实」，头部因此与改动前逐字节相同——这既是设计（旧日志不变），也意味着头部那一块的形状只在 seam ⑥ 的黑盒与新建的 seam ④ 判据里被钉住。全量 431 passed / 5 skipped，TOTAL 1971 93 95%。
- [x] 5.2 复核小窗口那一族的判据（`--window 70000 --reserve 100` 那条路）：触发线公式不变，若某条判据因头部变多而失效，只改那条判据的窗口数值并写明理由。门禁四道全绿。
  - 实况：触发线公式没动，小窗口那一族全绿，一条都没改。头部那块大约两百来字节，对 `--window 70000 --reserve 100` 那种触发线 4364 的场合可以忽略；预算判据走的也是没有 platform 的骨架，所以量到的还是改动前的形状。

## 6. 收尾四项

- [x] 6.1 真实端点验收（完成判据的第二半，ADR-0024）：接上真实端点跑一次 `chat`，断言模型收到的头部里有这两个事实（从 `context/assembled` 里读），观察记进 `docs/verification/add-platform-facts-to-protected-header-real-endpoint.md`。
  - 实况：会话 `4d05e370b49247e596c566a3abc917ec`，头部三块齐（内置常量 → 工具块 → 运行环境块），模型第一次调用就 `bash {"command": "dir"}`，一次成功、没有试错正文；它没选 `glob`，头部建议与工具描述在同一次装配里竞争——记进那篇文档的「三条判读」，留给人裁。
  - 第二轮（3.5 改完建议之后，2026-10-25 晚）：会话 `8a1d826fb0be42a89df3878ce1785ab0`，同 prompt 同工作区，**turns=2**、只有两条 `glob`（`*` 与 `**/*`）、一次 `bash` 都没有。从 13 回合（还烧出一次 `MAX_TURNS`）降到 2 回合——那是「先原生工具、后平台 shell 命令」那句措辞的可观察效果。
- [x] 6.2 UAT 验收（完成判据的第三半，ADR-0025，人跑）：按 `docs/verification/add-platform-facts-to-protected-header-uat.md` 的场次跑，观察表填完才算通过；那张表没填完不得归档、不得合入 `main`。
  - 实况（2026-10-25，人跑 + agent 核对日志，人确认通过）：五场跑完、表填满——U1/U1b/U2 同一场 `b245f717…`（第一次就用 `glob`、13 回合、无 `ls`；U1b 里它逐字复述了工具描述那句引导）、U3 旧日志 `b861ceee…` 6 个装配点全 OK 且新日志三条也全 OK、U4 两场 `7d71754f…` / `d329a3e6…` 头部顺序正确且回答是中文。UAT 抓到的两处竞争（头部那句与描述那句）已按 3.5 改掉。
- [x] 6.3 变异测试一轮：改坏一处实现（例如把这块的位置挪到追加文本之后、把缺失事实填成猜测值、把 `shell` 换成 CLI 自己判平台、把建议改回读 `process.platform`），跑全量，记进 `docs/verification/add-platform-facts-to-protected-header-mutation.md`，还原并确认回到基线（还原前先看 `git status`）。
  - 实况：9 个变异 **9/9 被杀、0 存活**，定向跑（脚手架 `.tmp/mutation/run_platform_mutants.py`，字节级还原）；还原后跑了一次全量确认回到基线：430 passed / 5 skipped / 1 failed，那 1 条是 L-055 的已知 Windows Ctrl-C 偶发（单独复跑 1 passed）。记下两条读变异的事实：同一处逻辑的多个 return 各是一个变异口（M2 只压到兜底分支，M9 才压到「`session/start` 在但没有 `platform`」那条常走的路）；M3 能被杀靠的是判据不看本机平台。**两轴审查之后补测了 M3 与 M9 的全量**：红数与定向完全相同（各 2 条），差 0——AGENTS.md 要的「跑全量」在这一轮用两条代表补齐了。
- [x] 6.4 Learning Gate：扫本轮证据，可复用教训写进 `docs/lessons.md` 收件箱，没有信号就写 `NO-PROMOTION`；ADR-0029（平台事实与本平台建议）与 ADR-0030（原生工具优先、不拿脚本兜底）已在 propose 这一轮落字，收尾时核对它们是否还成立、必要时加 `Status`；把「保持 lossy UTF-8」这条裁决补进 `docs/adr/0002-deferred-refactors.md` 第 30 条。
  - 实况：新收 L-056（mypy 的平台窄化只认 `sys.platform` 字面量）与 L-057（这台机器的 PowerShell 5.1 写 UTF-8 带 BOM）；给 L-055 与 L-019 补了证据；**NO-PROMOTION**（两条都不是新的全局规则，额度没动）。ADR-0029 / 0030 仍然成立、没加 `Status`；ADR-0002 第 30 条补了一行「结案不动，补的是让模型知道为什么」。收件箱 15 条，到上限。

## Workflow follow-up

- 两轴审查（`code-review`，Standards / Spec）自固定点起。
- 归档在分支上做：sync delta 进主规格、移 `changeRoot`、`openspec validate --all --strict` 全绿，然后跑一次 `agents-md-slim`。
- 合并顺序：先 `change/fix-chat-screen-feedback`，再本分支；merge 与推 `main` 先征求人的批准。
