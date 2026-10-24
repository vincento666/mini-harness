# Tasks

## 1. 工具面那条事实（seam ②）

- [ ] 1.1 红：写一条 seam ② 的测试，断言 `bash` 工具面暴露它实际用来执行命令的 shell 形态，且该形态与它起进程时实际用的那条一致（本机是 `cmd.exe /c`）。先确认它在当前实现下红。绿：让 `tools/bash_tools.py` 提供这份事实，CLI 不自己判平台。门禁四道全绿。
- [ ] 1.2 红：写一条 seam ② 的测试，断言这份事实不是可配置性——工具注册表与配置层叠都不接受对它的覆盖。绿：确认它天然不可配置，或补上拒绝路径。门禁四道全绿。

## 2. `session/start` 记下平台事实（seam ⑥）

- [ ] 2.1 红：seam ⑥ 黑盒跑一次 `minihns run`，断言 `session/start` 的 payload 里 `platform` 含非空的 `os` 与 `shell`，且 `shell` 与该日志里 `bash` 实际执行用的形态一致。绿：CLI 把它写进 payload。
- [ ] 2.2 红：seam ⑥ 黑盒分别跑 `chat`（EOF 退出）与 `serve`，断言两份日志都有 `platform` 且两处的 `os` 与 `shell` 相同。绿：三个入口走同一条装配路。
- [ ] 2.3 红：seam ⑥ 断言 `platform` 不出现在命令行开关表与配置文件的合法键表里（`--help` 里没有它、配置文件里写它是既有那条「配置文件只接受这些键」的失败形状）。绿：确认没有为它开可配置性。

## 3. 折叠头部多一块（seam ④）

- [ ] 3.1 红：seam ④ 断言折叠结果的受保护头部里多一块运行环境，内容含 `os` 与 `shell`，位置在内置常量与工具块之后、`--append-system-prompt` 的追加文本之前；`header_fingerprint` 覆盖它。绿：`_start_facts` 读回、`protected_header` 拼这块。
- [ ] 3.2 红：seam ④ 断言「命令输出按 UTF-8 解码、非法字节显示为替换字符」那句说明随这块一起出现，且它是关于 harness 自己的说明、不是猜测出来的平台事实。绿：把它固定在那一块里。
- [ ] 3.3 红：seam ④ 逐点重放一份带 `platform` 的新日志，断言每个装配点与该记录逐字段相等。绿：确认派生只依赖该点之前的前缀。

## 4. 旧日志不受影响（seam ④ + ⑥）

- [ ] 4.1 红：seam ④ 折叠一份 `session/start` 没有 `platform` 的日志，断言头部只有内置常量、工具块与追加文本，`header_fingerprint` 与该记录里的一致，且没有为缺失事实填入猜测值。绿：缺失时不产出这块。
- [ ] 4.2 红：seam ⑥ 对一份既有 fixture 日志跑 `minihns replay`，断言每个装配点 `verified … OK`、退出码 0、没有 `REPLAY_MISMATCH`。绿：确认旧日志的字节与折叠结果都不变。

## 5. 既有判据对齐（seam ④ / ⑥）

- [ ] 5.1 跑全量测试，把因头部多一块而红的判据逐条改判据（不改实现来迁就 fixture）；提交信息里列出改了哪几条、为什么。门禁四道全绿。
- [ ] 5.2 复核小窗口那一族的判据（`--window 70000 --reserve 100` 那条路）：触发线公式不变，若某条判据因头部变多而失效，只改那条判据的窗口数值并写明理由。门禁四道全绿。

## 6. 收尾四项

- [ ] 6.1 真实端点验收（完成判据的第二半，ADR-0024）：接上真实端点跑一次 `chat`，断言模型收到的头部里有这两个事实（从 `context/assembled` 里读），观察记进 `docs/verification/add-platform-facts-to-protected-header-real-endpoint.md`。
- [ ] 6.2 UAT 验收（完成判据的第三半，ADR-0025，人跑）：按 `docs/verification/add-platform-facts-to-protected-header-uat.md` 的场次跑，观察表填完才算通过；那张表没填完不得归档、不得合入 `main`。
- [ ] 6.3 变异测试一轮：改坏一处实现（例如把这块的位置挪到追加文本之后、把缺失事实填成猜测值、把 `shell` 换成 CLI 自己判平台），跑全量，记进 `docs/verification/add-platform-facts-to-protected-header-mutation.md`，还原并确认回到基线（还原前先看 `git status`）。
- [ ] 6.4 Learning Gate：扫本轮证据，可复用教训写进 `docs/lessons.md` 收件箱，没有信号就写 `NO-PROMOTION`；把「保持 lossy UTF-8」这条裁决补进 `docs/adr/0002-deferred-refactors.md` 第 30 条；需要 ADR 的按 `domain-modeling` 的 ADR-FORMAT 新开一份（编号扫现有最大号 +1，注意跨分支撞号由人在 merge 时裁）。

## Workflow follow-up

- 两轴审查（`code-review`，Standards / Spec）自固定点起。
- 归档在分支上做：sync delta 进主规格、移 `changeRoot`、`openspec validate --all --strict` 全绿，然后跑一次 `agents-md-slim`。
- 合并顺序：先 `change/fix-chat-screen-feedback`，再本分支；merge 与推 `main` 先征求人的批准。
