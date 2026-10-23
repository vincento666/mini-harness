## 1. 判据先写（seam ⑥：真实子进程，断言 stdout / stderr 的排版与内容）

- [x] 1.1 提示符不自带换行：管道喂一行、fixture 一条 `stop` 回复 → stdout 恰为 `> <正文>\n> `（先确认它在现状下红）
- [x] 1.2 只带工具调用的回合不留空行：fixture 三条只带 `tool_calls`（`content` 为空）加一条带正文 → 正文之前不出现连续空行
- [x] 1.3 段收尾那一行不重复同一个词、带非空 detail：让一次 chat 的段以 `CONTEXT_WINDOW_EXCEEDED` 收尾（fixture 带 `usage.input_tokens` 做校准，形状照 `.tmp/uat-repro/fixture2.json`；这是 mock 形状不是验收，ADR-0022）→ stderr 那一行含 `CONTEXT_WINDOW_EXCEEDED` 恰一次、含非空 detail
- [x] 1.4 既有的 provider 那一行照旧：`[段] PROVIDER_ERROR：PROVIDER_HTTP_STATUS` 那条判据在新组装规则下仍绿（不许为了新形状把它改松）
- [x] 1.5 取消的段打 `[段] ABORTED`：真 Ctrl-C（`CREATE_NEW_PROCESS_GROUP` + `CTRL_C_EVENT`，同步点是 stdout 上先出现 `> `）落在段进行中 → stderr 有那一行、stdout 没有、日志没有、会话继续接受下一条输入
  - 本机实测偏离 design D8：只带 `CREATE_NEW_PROCESS_GROUP` 时 `GenerateConsoleCtrlEvent` 静默无效；判据用 `CREATE_NEW_CONSOLE` + `FreeConsole` + `AttachConsole(pid)` + `GenerateConsoleCtrlEvent(CTRL_C_EVENT, pid)`，见 `tests/cli_blackbox.py`
- [x] 1.6 提示符上取消没有 traceback：真 Ctrl-C 落在没有段在跑时 → 退出码 0、stderr 里没有 `Traceback`、日志以 `session/end`（`MODEL_COMPLETED`）收尾
  - 本机实测：管道上的阻塞 `readline` 不被 Ctrl-C 打断（Windows 的 Ctrl-C 只在解释器回到字节码边界时才被消费），所以信号之后给 stdin 一个 EOF；缝隙只有几毫秒，一次送进缝隙的概率不够高，判据连着送到进程自己退出为止（4/4 红 → 5/5 绿）
- [x] 1.7 chat 在 stderr 给出 session id：那一行在 stderr、不在 stdout、不在日志；拿它跑 `minihns replay` 找得到这次会话
- [x] 1.8 连续两段溢出 → stderr 多出一行「降不下去」的说明，且每个会话恰一次；不连续（中间有一段正常收尾）时不多出
- [x] 1.9 非 0 退出那一行不带悬空冒号：`serve --http` 中途取消 → 退出码 5、stderr 那一行含 `ABORTED` 且不以冒号结尾

## 2. 实现（把上面那批判据逐个转绿，一次一个红绿循环）

- [x] 2.1 提示符改用 `sys.stdout.write` + `flush`（不再 `print`）
- [x] 2.2 `_print_new_replies` 跳过 `content.strip()` 为空的回复
- [x] 2.3 `_print_segment_note` 按 D3 组装：reason → 与 reason 不同的 code → 非空 detail
- [x] 2.4 `_SEGMENT_NOTE_SUPPRESSED` 只剩 `MODEL_COMPLETED`
- [x] 2.5 chat 启动时往 stderr 打印 session id 一行
- [x] 2.6 `_report_failure` 在 detail 为空时只打失败码、不带冒号
- [x] 2.7 会话收尾（含 `end_session` 与它的打印）移进 `except KeyboardInterrupt` 的覆盖范围
  - 本机实测的形状：收尾那一段换一个什么都不做的处理器（`_suppress_sigint`）再写 `session/end`；不置 `SIG_IGN`——Windows 上被忽略的 Ctrl-C 会在解释器里炸成 `OSError: Signal 2 ignored due to race condition`。`_chat` 不再把旧处理器换回去：换回去等于在退出前的缝隙里重新开一个没人接的洞
- [x] 2.8 连续溢出的说明：一个局部变量记住上一个段的 `stop_reason`，不进日志、不新增状态机
  - 「每个会话恰一次」还要第二个局部布尔（这一句说过没有）：只记上一个收尾理由的话，连续三段溢出会说两次

## 3. 门禁与规格

- [x] 3.1 四道门禁全绿（ruff format / ruff check / mypy --strict / coverage --fail-under=95）
  - 最后一次实现提交（`163c588`）上实测：417 passed / 5 skipped、`TOTAL 1951 93 95%`、ruff format / ruff check / mypy --strict 退出码都是 0
- [x] 3.2 `openspec validate --all --strict` 全绿（`chat-repl` 与 `cli` 的 delta 进主规格是在归档那一步，不在这里）
  - 实测：13 passed / 0 failed，含 `change/fix-chat-screen-feedback`

## 4. 两轴 review

- [x] 4.1 Standards 轴：`cli/main.py` 的改动是否只动了必须动的（内核 `loop/` 与 `context/` 不许动）
  - 内核 `loop/` 与 `context/` 没动，`src/` 里只有 `cli/main.py` 一处改动。查出一条打包超数：`a34c63e` 打 1.7 + 2.5 + 1.8 + 2.8，信息里的理由自证应拆——分支未推，当场拆成 `d2395c7` + `5bf86d3`。测试里的重复：溢出那套 fixture 两份，抽成 `_overflow_entries`。记账不动的两条：脚手架（`_cli_console_process` / `_send_ctrl_c` / `_LiveStreams`）早于它的使用者两个提交；挂起 fixture 在 chat 与 serve 两个测试文件各一份。细节记进 `docs/adr/0002-deferred-refactors.md` 的「`fix-chat-screen-feedback` 的两轴审查」一节
- [x] 4.2 Spec 轴：delta 里每一条 scenario 对上一条判据，逐条核；对不上的写进 `docs/adr/0002-deferred-refactors.md`
  - 补上六条判据缺口：serve 与 run 那两行各补「不在 stdout、不在日志」两半；run 溢出补「含日志里那句非空 detail」；1.3 补「那一行的整数含触发线 54272、且有一个整数越线」；围栏那条补「含 `error/fence` 里那个 code」；1.2 把第三条工具回合的 `content` 换成全空白；Linux-only 的 serve SIGINT 那条补「恰一行、不以冒号结尾、不在 stdout」（本机 skip）。两条没补的形状（`_chat` 不换回旧处理器、`[降不下去]` 前缀写死在判据里）记进同一节

## 5. 收尾四项（ADR-0024 + ADR-0025）

- [x] 5.1 真实端点验收：接上真实端点把本 change 的判据跑一遍，记录进 `docs/verification/fix-chat-screen-feedback-real-endpoint.md`
  - 9 条里 8 条通过。1.6 那一半：单次 Ctrl-C 三次都是退出码 0、无 traceback、`session/end` 恰一条；判据里「连送到进程退出为止」的 40 次连发把 Ctrl-C 压到解释器收尾之后，拿到 `0xC000013A`（日志完整、无 traceback）。两条后果要人裁决，记在同一份文档里
- [ ] 5.2 UAT 验收（人跑）：场次表在 `docs/verification/fix-chat-screen-feedback-uat.md`（propose 时已立骨架）。**那张表没填完本 change 不得归档、不得合入 `main`**
- [x] 5.3 变异测试一轮：记录进 `docs/verification/fix-chat-screen-feedback-mutation.md`；每个变异都要被杀死，存活的补一条判据
  - 14 条变异全部被杀死、无存活、无 dud，本轮没有需要补的判据。11 条跑三条 CLI 判据文件，M1 / M3 / M13 改跑全量对照，红数相同、差 0 条（AGENTS.md 变异段写的是「跑全量测试」，这一处照定向做、用三条全量补测量，记在同一份文档里）。第一版脚手架的文本模式读写把 `cli/main.py` 的行尾整份换成 CRLF、还原检查当场失败，改按字节读写后重跑；还原前后 `git status` 一致
- [ ] 5.4 Learning Gate：扫本轮证据写进 `docs/lessons.md` 收件箱；ADR-0028 落字（D4 那条规格反面集合的取舍）；归档后跑 `agents-md-slim`
