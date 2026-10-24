# Proposal

## Why

2026-10-24 的人手验收里，模型在 Windows 工作区上连 `ls` 都跑不通，靠试错才在屏幕上写出「这是一台 Windows shell（cmd）环境」。受保护头部里只有两句内置提示加一份工具名清单（`events/fold.py` 的 `SYSTEM_PROMPT`），**没有任何关于运行平台的事实**，而 `bash` 在 Windows 上走 `cmd.exe /c`（`tools/bash_tools.py`）。模型不知道自己在什么壳里，就多烧回合、屏幕上就多一段试错正文、日志里就多几条注定失败的 `tool/result`。

## What Changes

- `session/start` 的 payload 新增一个平台事实块：`os`（`os.name` 的原值）与 `shell`（`bash` 实际用来执行命令的形态——Windows 上是 `cmd.exe /c`，POSIX 上是 `/bin/sh -c`）。三个入口（`run` / `chat` / `serve`）都写。
- 受保护头部新增一块「运行环境」，内容取自该装配点之前的 `session/start`，位置在内置常量与工具块之后、`--append-system-prompt` 之前。
- 那一块里带一句固定说明：命令输出按 UTF-8 解码，不是合法 UTF-8 的字节显示为替换字符。于是已经发生的乱码从「模型以为工具坏了」变成「模型知道为什么」。
- 旧日志不受影响：`session/start` 里没有 `platform` 时头部不产出那一块，折叠结果与今天逐字节相同。这一条 MUST 有判据钉住（旧日志的 fixture 不动）。

**本 change 明确不做**：

- 不改 `bash` 的输出解码、不猜平台代码页。2026-10-24 人裁决保持 lossy UTF-8，与 `docs/adr/0002-deferred-refactors.md` 第 30 条 2026-10-22「按 DSH 结案」一致（DSH 自己就是 lossy UTF-8）。
- 不动 `SYSTEM_PROMPT` 那个内置常量。`context/assembled` 由 `fold` 重算，改常量会让**所有旧日志 replay 出 `REPLAY_MISMATCH`**；平台事实因此走 `session/start` → fold 读回那条路（与 `tools`、`append_system_prompt` 同一套路）。
- 不加命令行开关、不加配置文件键。平台事实是事实不是可配置性（编码行为四规 #2）。
- 不把平台事实塞进工具描述：那条路让它不进折叠结果、不进 `context/assembled`，屏幕上与日志里都看不见。
- 不做平台探测式的能力协商：不检测机器上有没有 `ls`，不装 shell 适配层。
- 不碰本轮 UAT 看见的第三条（Ctrl-C 落在「请求还没发出」那道缝里时屏幕上打的是 `[段] PROVIDER_ERROR：PROVIDER_ABORTED …`）。它留在「取消的落点」那一族等 M10。

## Capabilities

### Modified Capabilities

- `cli`：`session/start` 的 payload 新增 `platform`（`os` 与 `shell`），三个入口都写。
- `context-projection`：受保护头部新增一块由日志前缀派生的「运行环境」；没有该事实的旧日志头部逐字节不变。

## Impact

代码：`src/mini_harness/tools/bash_tools.py`（把它实际使用的 shell 形态变成一个可读的事实）、`src/mini_harness/cli/main.py`（写进 `session/start`）、`src/mini_harness/events/fold.py`（`_start_facts` 读回、`protected_header` 多一块）。

测试：seam ②（工具面那条事实与 `bash` 实际执行形态一致）、seam ④（`session/start` 的字段、折叠头部多一块、**旧日志折叠结果不变**）、seam ⑥（CLI 黑盒：模型收到的头部里有它、`replay` 逐字段复现）。

判据影响：新会话的 `header_fingerprint` 与 `context/assembled` 多一块，一批钉头部形状的测试要跟着改；旧日志的 fixture 与 `REPLAY_MISMATCH` 那条判据不动。窗口预算的估算多几十个字，触发线位置不变。

文档：`docs/adr/0002-deferred-refactors.md` 第 30 条补一行「2026-10-24 人再次确认保持 lossy UTF-8」；UAT 场次骨架 `docs/verification/add-platform-facts-to-protected-header-uat.md`（ADR-0025）。

依赖：本 change 的分支建在 `change/fix-chat-screen-feedback` 之上——ADR-0024 / 0025 的收尾四项与 `-uat.md` 约定、以及 `events/fold.py` 与 `cli/main.py` 的当前形状都只在那条分支上。先合它，再合这个。
