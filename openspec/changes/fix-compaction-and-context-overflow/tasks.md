# Tasks

## 1. 折叠层：按 seq 区间折出对话（seam ④）

- [ ] 1.1 红：写判据——给定一份日志与一个 seq 闭区间，折出的消息只含该区间内的对话记录；`session/start` 与既有 `compaction/summary` 不参与区间；区间外（含保留尾部）的记录一条都不出现。跑 `uv run pytest -q` 确认它红。
- [ ] 1.2 绿：在 `context/` 提供该入口（复用既有折叠与投影语义，不新增第二套折叠），1.1 变绿且 `uv run mypy --strict src` 无新错。

## 2. 摘要请求只装被遮蔽那一段（seam ①）

- [ ] 2.1 红：假 provider 记下收到的消息，断言除系统消息与末条摘要指令外，每条都落在本次 `compaction/summary.payload.shadowed_range` 之内、保留尾部不在其中。跑测试确认它红（今天发的是整份表层）。
- [ ] 2.2 绿：`_compact_within_assembly` 改用 1.2 的入口构造摘要调用，2.1 变绿；既有压缩相关判据（`compaction/summary` 的四个键、一次装配最多一次）全部仍绿。
- [ ] 2.3 红：写「区间裁到最小仍超过触发线」的判据——日志里没有带 `purpose: compaction` 的 `model/request`、没有 `error/model`，该回合有 `error/context`（`CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`（同一停止理由）。确认它红。
- [ ] 2.4 绿：实现「从区间头部逐条丢弃直到装得下、一条都装不下就不发请求」，2.3 变绿；`uv run pytest -q` 全绿。

## 3. 适配层的溢出识别与失败正文（seam ⑤）

- [ ] 3.1 红：假端点返回 400、错误对象没有 `code`、`message` 是那句 `prompt (222233 tokens) leaves no room to answer in the context (196608); requests are never truncated` → 断言 `code: PROVIDER_CONTEXT_OVERFLOW` 且没有 `model/retry`。确认它红。
- [ ] 3.2 绿：加短语表词表（`Literal` + `frozenset`，四个短语、大小写不敏感）并放宽识别，3.1 变绿；既有「`error.code` 命中」「413」「其它 400 仍走既有路径」三条判据不变绿。
- [ ] 3.3 绿：把短语表接进 `tests/test_vocabulary_reachability.py` 的「每个值可达」判据，跑该文件确认每个短语都有一条判据打到它。
- [ ] 3.4 红：写 `detail` 的三种形状判据——响应 JSON 有 `error.message`（detail 含状态码与那句话）、正文是 HTML（detail 含状态码与正文开头且 ≤200 字符）、正文为空（detail 就是 `HTTP 400`）。确认它们红。
- [ ] 3.5 绿：实现 `detail` 构造（单行、换行压成空格、至多 200 字符），3.4 变绿；`error/model` 的 payload 里 `detail` 与失败结果一致，`code` 不因摘要改变。

## 4. chat 里段级收尾看得见（seam ⑥）

- [ ] 4.1 红：真实子进程跑 `minihns chat`，让一段以 `error/model`（`PROVIDER_HTTP_STATUS`）收尾 → 断言 stderr 有一行含 `PROVIDER_ERROR` 与 `PROVIDER_HTTP_STATUS`、stdout 不含该行、日志里也没有这一行。确认它红。
- [ ] 4.2 绿：实现 stderr 那一行，4.1 变绿；`chat` 既有的 stdout 投影判据（工具结果不上 stdout、带 `purpose` 的摘要不上 stdout）全部仍绿。
- [ ] 4.3 红：写其余形状的判据——`CONTEXT_WINDOW_EXCEEDED` 段与 `MAX_TURNS` 段各打一行且会话继续接受下一条输入；`MODEL_COMPLETED` 段与被取消的段不打。确认它们红。
- [ ] 4.4 绿：补齐形状判定，4.3 变绿；`uv run pytest -q` 全绿。

## 5. 账与文档

- [ ] 5.1 立 `docs/adr/0022-*.md`（照 `domain-modeling` 的 ADR-FORMAT，正文 1–3 句）：记录「DSH 只回放被遮蔽区域、mini 之前发整份表层」的更正与「猜正文短语」的代价；确认 `docs/adr/` 编号连续、无 0022 重复。
- [ ] 5.2 在 `docs/adr/0002-deferred-refactors.md` 追加第 64 条（估算与真端点差约 4 倍，实测数字与探针结论）与第 65 条（从区间头部丢弃等于最旧内容不进摘要），并更新 `docs/CURRENT.md` 的已知缺口清单；确认第 62、63 条与本 change 的对应关系写明。
- [ ] 5.3 人手验收记进 `docs/verification/fix-compaction-and-context-overflow-manual.md`：用本机 Strata 端点把那次失败重演一遍（同一 `--window 128000`、`--max-turns 8`、`approval ask`），记录屏幕上看得见什么、段是否还无声死掉、以及 `error/model` 的 `detail` 里那句话长什么样。

## 6. 集成检查与收尾

- [ ] 6.1 跑门禁四道并确认退出码 0：`uv run ruff format --diff src tests`、`uv run ruff check src tests`、`uv run mypy --strict src`、`uv run coverage erase` + `uv run coverage run -m pytest -q` + `uv run coverage combine` + `uv run coverage report --fail-under=95 --show-missing`。
- [ ] 6.2 变异测试一轮并记进 `docs/verification/fix-compaction-and-context-overflow-mutation.md`：至少覆盖「摘要请求改回发整份表层」「短语表匹配改成大小写敏感」「detail 不截断」「stderr 那一行改打 stdout」四处，确认每个变异都被至少一条测试杀死，还原前先看 `git status`。
- [ ] 6.3 Learning Gate：扫本轮证据写进 `docs/lessons.md`；收件箱已在 15 条上限，先消化（晋升或合并）再收新条目；无可复用信号就写 `NO-PROMOTION`。

## Workflow follow-up

- 跑 `code-review` 两轴（Standards / Spec）核对实现与三条 delta 一致。
- 在 change 分支上 sync delta 进主规格（`context-budget`、`provider`、`chat-repl`）并归档，然后 `openspec validate --all --strict` 全绿。
- 征求人批准后再合入 `main` 并推；合并后跑一次 `agents-md-slim`。
