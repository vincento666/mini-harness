# Tasks

## 1. 依赖与内核的第三个入口

- [x] 1.1 前置（无新判据）：`uv add aiohttp` 与 `uv add --dev` 需要的部分；AGENTS.md 技术选型行加 aiohttp；门禁四道仍全绿
- [x] 1.2 seam ①：`SessionEntry` 加 `serve` 与 `ENTRY_SERVE` 常量——判据是「`entry: "serve"` 的会话跑完恰一个段、`session/end` 在盘上、`session/start.payload.entry` 是 `serve`」

## 2. serve 的参数表与「失败在会话开始之前」（seam ⑥）

- [x] 2.1 seam ⑥：`serve` 子命令存在且 `-p/--prompt` 必填非空——缺 prompt 是退出码 2、stderr 含 `INVALID_ARGUMENT`、没有新日志文件
- [x] 2.2 seam ⑥：`--port` 词表 1 至 65535——`--port 0` 与 `--port 65536` 各一条判据，都是 2 且没有日志
- [x] 2.3 seam ⑥：`--host` 只接受 `127.0.0.1` / `0.0.0.0`——其它取值是 2 且没有日志
- [x] 2.4 seam ⑥：`serve` 不接受 `--events`——给了就是 2 且没有日志
- [x] 2.5 seam ⑥：绑定先于开日志——端口被占时退出码 2、stderr 含 `INVALID_ARGUMENT` 与该端口、session 目录里没有新日志文件、没有发出任何模型请求
- [x] 2.6 seam ⑥：serve 的窗口预算失败与 run 同形——使触发线为 0 的 `--window` / `--reserve` 是 2 且没有日志

## 3. 事件流的形状（seam ⑥）

- [x] 3.1 seam ⑥：`GET /events` 一帧对应一条记录——帧数等于日志行数，`id` 与 `event` 等于该记录的 `seq` 与类型，`data` 解析后与日志那一行逐字段相等
- [x] 3.2 seam ⑥：事件流里没有日志里没有的事实——每个 `event` 值在词表内，且日志里没有由连接或请求产生的记录
- [x] 3.3 seam ⑥：`GET /` 是 404 且不是事件流，会话照常跑到自己的收尾
- [x] 3.4 seam ⑥：stdout 只打 session id 一行；监听地址打在 stderr

## 4. 续读游标（seam ⑥）

- [x] 4.1 seam ⑥：带 `Last-Event-ID: n` 重连——第一帧 `id` 是 n+1，整个会话的记录在两次连接里合计恰好出现一次
- [x] 4.2 seam ⑥：`?from=2` 与 `Last-Event-ID: 5` 同时在场——第一帧 `id` 是 3
- [x] 4.3 seam ⑥：游标指向还没写出的 `seq`——不报错、不返回 400，后续记录写出时开始送帧
- [x] 4.4 seam ⑥：游标是负数或非整数（`abc`、`-1`、`1x`）——该请求 400，会话不受影响、日志完整；`0` 是合法游标，第一帧 `id` 是 1
- [x] 4.5 seam ⑥ + ④：tail 入口的残行兜底——⑥ 判「追加写与读并发时帧数仍等于日志行数」（超大记录），④ 判「最后一行没有换行符时不消费残行、补完之后读得到」。判据落在 ④ 是因为 ⑥ 撞不上正在写的一半行：把换行纪律改坏的变异在 ⑥ 存活（实测三次 + 全量）

## 5. 断开与多客户端（seam ⑥）

- [x] 5.1 seam ⑥：客户端读到中途断开且不再重连——日志记录集合与不断开的同形会话相同（含 `session/end`），且没有因断开产生的记录
- [x] 5.2 seam ⑥：两个客户端同时读同一条流、其中一个先断开——另一个从自己的位置读到底，帧集合与单客户端相同

## 6. serve 的会话收尾就是进程退出（seam ① 与 ⑥）

- [x] 6.1 seam ⑥：预算溢出在 serve 里就是进程退出——`error/context`、`turn/end`、`segment/end`、`session/end` 都在盘上，退出码 4
- [x] 6.2 seam ⑥：provider 失败在 serve 里就是进程退出——`error/model` 与 `session/end` 在盘上，退出码 1
- [x] 6.3 seam ⑥：围栏拒绝在 serve 里就是进程退出——`error/fence` 与 `session/end` 在盘上，退出码 3
- [x] 6.4 seam ① + ⑥：取消在 serve 里就是进程退出——seam ① 用进程内 cancel 判 `session/end` 的 `ABORTED`；seam ⑥ 的 SIGINT 子进程判据在 Windows 上 skip、Linux runner 上跑

## 7. 收账：装配路与失败码表（第 40 与 50 条）

- [x] 7.1 seam ②：`ConfigFailure.code` 收成 `Literal` 与词表常量——既有配置失败判据全绿、`mypy --strict` 通过，并补一条「每个失败码可达」的判据（落点 `tests/test_config_layering.py`，不是 ⑥：这一条判的是配置层那个模块自己，本组标签是 ⑥  inherited）
- [x] 7.2 seam ⑥：`_prepare_or_fail` 返回 `Prepared | Failure`——`run` / `chat` / `serve` 三处调用方不再 `isinstance(..., int)`；既有失败判据不变绿
- [x] 7.3 docs：ADR-0002 第 21、38、39、41 条逐条改判（serve 复用同一个 `SessionEnv` 与同一份参数表，没有带出第二套门与上下文），写明新的触发条件

## 8. ADR 与文档

- [x] 8.1 新开 ADR-0021：serve 用 aiohttp 与 SSE，只照 DSH 的 `session/follow` 里 durable 事件那一半（`$events` 的 waterfall 与 assistant-stream 逐字帧都不做）；写明「将来加 snapshot 帧与一条回程 POST 端点——DSH 的 `$events/result` 是 unary HTTP RPC，不换 SSE 也不改 `seq` 游标」，含「host / port 是 CLI-only flag」的窄化与代价
- [x] 8.2 ADR-0002 第 30 条按 DSH 结案（lossy UTF-8，证据 `dsh-subprocess-local/lib/output.js:193`、`:232` 对照 `dsh-fs-local/lib/index.js:333`）；新开第 53 条：溢出时没有 spill 文件与 `lossy` 标记（DSH 的 `dsh-bash-local/lib/index.js:108-154`、`dsh-tool-bash/lib/index.js:137`），处理时点 M10
- [x] 8.3 GLOSSARY 补「事件流」「帧」「游标」三个词，并写明「游标就是日志的 `seq`」
- [x] 8.4 docs/CURRENT.md 与 docs/roadmap.md 的 M7 行与门禁实测

## 9. 人手验收（不进 CI）

- [x] 9.1 三个 session 跑完并记进 `docs/verification/m7-serve-http-sse-manual.md`：一次真事（serve 跑一个带工具调用的会话，客户端读到底 + 中途断开再带游标重连续读）、一次溢出（小窗口）、一次取消（Ctrl-C）。**Ctrl-C 那一半待人跑**（Windows 上给真实子进程送 Ctrl-C 这条路从 M3 起就没通过，seam ⑥ 那条 `test_sigint_in_a_serve_subprocess_exits_with_five` 在本机是 skip）；跑法写在文档最后一节。溢出那一场客户端挤不进去（窗口只有 9 ms），缺口记进 ADR-0002 第 55 条
- [ ] 9.2 模型层那一半写成人手 runbook（真实 provider + 真实模型下的事件流），等人跑

## 10. 收尾门禁

- [x] 10.1 `code-review` 两轴（Standards / Spec），裁决落地。Standards 轴：五条硬违规全在提交纪律与文档措辞（记进 ADR-0002 的 M7 两节欠账），代码未违 A–F、判据都在七个 seam 上、无凑数测试；六条判断项记进第 56 至 60 条。Spec 轴：形状核对通过（帧 / 游标 / 绑定先后 / 退出码 / 不写 HTTP 事实），查出四条判据缺口，当场补齐——bash 的 lossy UTF-8（seam ②③）、`entry` 与 `prompt` 在 seam ⑥、游标「开始送帧」那一半、`--http`（人裁决定「保留但可选」，delta 的 flag 表与 Scenario 同步补上）。另更正 7.1 的 seam 标注（⑥ → ②）与本文件末尾的「六份 delta」（实为四份）
- [x] 10.2 变异测试一轮，记进 `docs/verification/m7-serve-http-sse-mutation.md`；存活的算覆盖缺口并补判据。15 个变异全部被杀死、没有存活，因此没有新补判据；三处「没有可放的变异」（`serve.py:119` 的 `LogReadFailure` 出口、`0.0.0.0` 真绑定与 65535 上界、慢读者）已在 ADR-0002 第 61 与 54 条
- [ ] 10.3 Learning Gate：扫本轮证据写进 `docs/lessons.md` 收件箱（无可复用信号就写 NO-PROMOTION）
- [ ] 10.4 归档之后跑 `agents-md-slim`

## Workflow follow-up

- 在 change 分支上 sync 四份 delta 进主规格：新建 `openspec/specs/event-stream/spec.md`（含 Purpose），改 `cli` / `turn-loop` / `bash-tool` 三份主规格
- `openspec archive m7-serve-http-sse` 在分支上做，然后 `openspec validate --all --strict` 全绿（12 份主规格）
- 先征求人的批准、确认了才 `git merge --no-ff` 进 `main`、推 `main`、打 tag `m7`、删 `change/m7-serve-http-sse`
