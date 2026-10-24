# `fix-chat-screen-feedback` 的真实端点验收（tasks 5.1）

跑法：真实 DeepSeek 端点（`--provider openai --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY`，密钥走用户作用域的环境变量），子进程是裸的 `python -m mini_harness.cli.main`（不套 coverage，不污染门禁那三份 partial）。脚本 `.tmp/real-endpoint/acceptance.py`（scratch，不进测试套件），原始记录 `.tmp/real-endpoint/run.log` 与 `report.json`。

跑的时间：2026-10-24 01:30–01:50（Asia/Shanghai）。基线提交 `6919bbd`。

## 结果：9 条里 8 条通过，1 条按「人按一次 Ctrl-C」的形状通过、按连发的形状暴露出解释器边界

| 判据 | 结果 | 屏幕上实际看到的 |
| --- | --- | --- |
| 1.1 提示符不自带换行 | 通过 | stdout 是 `> 你好！很高兴见到你，有什么我可以帮忙的吗？\n> `——正文紧跟提示符，最后悬着一个 `> `，没有连续空行 |
| 1.2 只带工具调用的回合不留空行 | 通过 | 真实端点自己决定读 `note.md`（日志里有 `tool/call`），stdout 是 `> 第一行是苹果。\n> `，正文之前没有空行 |
| 1.3 溢出那一行不重复 reason、带非空 detail | 通过 | `[段] CONTEXT_WINDOW_EXCEEDED：无可遮蔽的内容，预算读数 5027 已超过触发线 4364`——`CONTEXT_WINDOW_EXCEEDED` 在那一行里出现一次，detail 与日志里 `error/context` 的那句逐字相同，两个数都在（触发线按 `max(W*0.8, W-reserve-65536)` 是 4364） |
| 1.4 provider 那一行照旧 | 通过 | `[段] PROVIDER_ERROR：PROVIDER_HTTP_STATUS HTTP 400：The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-nonexistent-model. (request_id: …)`——新的组装规则没有把既有那条改松 |
| 1.5 取消的段在屏幕上有一行 | 通过 | 段进行中（`model/request` 已落盘、正文还在流）发真 Ctrl-C → stderr 上 `[段] ABORTED`，stdout 上没有，日志里 `error/abort` → `turn/end` → `segment/end`，退出码 0 |
| 1.6 提示符上取消没有 traceback | 见下「R6 那一半」 | 单次 Ctrl-C：退出码 0、无 `Traceback`、`session/end` 恰一条（3/3） |
| 1.7 chat 在 stderr 给出 session id | 通过 | stderr 上 `会话 710587fea3494e459715ef3ae87841cc` 恰一行、不在 stdout、日志里没有一条记录为它而存在；拿它跑 `minihns replay` 退出码 0 |
| 1.8 连续两段溢出多出一行说明、恰一次 | 通过 | 三段连续溢出（`--window 70000 --reserve 100` 加一条把预算读数推到 5027 的系统提示）→ `[降不下去] 连续两段溢出：这份会话已经降不下去，退出并新开一个会话是可选动作。` 只出现一次，不在 stdout、不在日志 |
| 1.9 非 0 退出那一行不带悬空冒号 | 通过 | `serve --http` 中途 Ctrl-C → stderr 恰一行 `ABORTED`（尾巴上没有冒号）、stdout 只有 session id、退出码 5、无 `Traceback` |

## R6 那一半：连发的 Ctrl-C 压在进程收尾之后

判据 1.6 在 seam ⑥ 里的形状是「一次 Ctrl-C，之后连着送到进程自己退出为止」（缝隙只有几毫秒，一次送进去的概率不够高）。真实端点那一跑按这个形状拿到的是：

- 退出码 `3221225786`（`0xC000013A`，Windows 的 STATUS_CONTROL_C_EXIT），3/3 复现；
- 日志仍是 `session/start` → `session/end` 两条、`session/end` 的 `stop_reason` 是 `MODEL_COMPLETED`，stderr 里没有 `Traceback`。

单独跑一个探针（`.tmp/real-endpoint/probe_r6.py`）把变量只留「连发几次」：

| 形状 | 退出码（三次） | 日志 | traceback |
| --- | --- | --- | --- |
| 一次 Ctrl-C，然后 stdin EOF | `0, 0, 0` | `session/start` → `session/end` | 无 |
| 一次 Ctrl-C 之后连发 40 次 | `0xC000013A` ×3 | `session/start` → `session/end` | 无 |

读法：会话本身收尾干净——`session/end` 在盘上、没有 traceback。`0xC000013A` 出现在**收尾之后**：`finish()` 已经跑完、`_chat` 已经返回，CPython 在解释器收尾（`_PySignal_Fini`）里把 SIGINT 换回默认处置，那之后落进来的 Ctrl-C 没有 Python 层的处理器可接，进程按控制台默认的方式结束。这不是本 change 的处理器链漏了什么：缝隙里（`finish()` 之内）装的是 `_suppress_sigint`，那一段的 Ctrl-C 被吞掉、没有 traceback。

两条后果的**裁决**（2026-10-24 人认可，落字进 `docs/adr/0002-deferred-refactors.md` 的「真实端点那一半的两条裁决」一节；本 change 不改代码、不改判据）：

1. **判据的形状按 seam 拆开，处理时点 M10**。认可「判据比人做的事更狠」这个读法：毫秒级缝隙那一半改到 seam ①（进程内）判——`signals.active` 已经是「当前活跃段的可等待事件」（`cli/main.py` 每段开局 `cancel = asyncio.Event()`、`signals.active = cancel`），进程内判据 `set()` 它、await 段结束、再断收尾形状（`session/end` 恰一条、无 traceback、退出码），一个信号都不用发；seam ⑥ 只留人的形状：一次 Ctrl-C、退出码 0、无 traceback。附带的好处按可测量那四条记：确定性（这条判据本轮 3/5 才绿）、跨平台（不再一半是 Windows 专属配方、一半是 `skipif`）、判据与人的动作对齐、以及「先找可观察锚点再动手」变成可复用形状（M10 的父子取消传播与 M15 的硬杀判据直接复用）。代价也写明：在 seam ⑥ 上造锚点必然要往生产代码里加只有测试会用的钩子，撞四规 #2，要 ADR——所以规则候选是「撞时序缝隙先找可观察锚点，找不到就把判据挪到能判它的那个 seam」，按一进一出不占 AGENTS.md 额度，等 M10 真的省下一次漏判再说。
2. **不让进程在收尾之后硬退出（`os._exit`），按现状结案**。不硬退出没有资源代价：provider 每次请求一个 `async with httpx.AsyncClient(...)`（`provider/openai_compat.py`），在 `finish()` 之前早就关完；日志每条记录自己 `open("a")` → 写 → 关（`events/writer.py`），`session/end` 在 `finish()` 返回前已在盘上；chat 里没有非守护线程、没有常驻连接。唯一可观察后果就是那几毫秒里再来信号 → `0xC000013A`。硬退出的代价是它跳过 stdout / stderr 的缓冲刷新：stdout 是管道时 `print()` 块缓冲，最后几条模型回复可能丢——这个产品的全部就是屏幕上那一行加日志，为连发那种形状冒这个险不划算。

## 与 mock 门禁的关系

mock 那一半（四道门禁）跑过：417 passed / 5 skipped、`TOTAL 1951 93 95%`。这一节补的是真实那一半：上面 9 条判据的**形状**在真实端点下成立，包括真实 HTTP 400、真实溢出读数、真实流式回复中途取消。UAT 那一半（人坐在终端前办一件真事）还没跑，手册在 `docs/verification/fix-chat-screen-feedback-uat.md`。
