# Design

## Context

见 `proposal.md` 的 Why。这里只记约束：

- 受保护头部由 `events/fold.py` 的 `protected_header` 拼出，第一条是模块常量 `SYSTEM_PROMPT`；`context/assembled` 落盘的是折叠结果，`replay` 靠**重算折叠**逐字段核对（`assembly_points` 给出每个装配点之前的日志前缀）。
- 头部里已经有一块是日志派生的：工具块。它的派生方式就是答案的形状——`_start_facts` 从该装配点之前的 `session/start` 读回 `tools` 与 `append_system_prompt`，注释写明理由：「注册表在回放时根本不存在」。
- `bash` 在哪个壳里跑，`tools/bash_tools.py` 已经知道（它按平台分支选 shell），但这份事实现在不出现在模型看到的任何东西里。
- 工具描述是常量，随 provider 请求发出去，但**不进** `context/assembled`——所以它能承载与平台无关的引导，承载不了平台事实。

## Goals / Non-Goals

**Goals:**

- 模型在第一条回复之前就知道自己在哪个操作系统、`bash` 用哪个 shell 执行。
- 它同时知道这个平台上列目录、搜内容、看文件该用什么命令，以及这些事有原生工具可做、不必用 shell 也不必写脚本。
- 这份事实**进日志**、**进折叠结果**、**可被 replay 逐字段复现**。
- 这条事实存在之前写下的每一份日志，折叠结果与 replay 结果都不变。

**Non-Goals:**

- 不加开关、不加配置键、不做平台探测（不检测机器上有没有 `ls`）。
- 不改 `bash` 的输出解码（`docs/adr/0002-deferred-refactors.md` 第 30 条 2026-10-22 已按 DSH 结案；2026-10-24 人再次确认保持 lossy UTF-8）。
- 不动窗口预算的触发线公式；头部变多是这件事的副作用，不是新判据。
- 描述里不放平台专用命令，也不按平台发不同工具让模型自己挑（ADR-0030）。
- 不把「让模型临时写脚本」当成等价能力。

## Decisions

**D1 平台事实走 `session/start` → fold 读回，不改 `SYSTEM_PROMPT` 常量。**
`context/assembled` 由折叠重算，常量一变，所有旧日志的每个装配点都会 `REPLAY_MISMATCH`，M5 立的那条逐点重放判据要跟着改。走 `session/start` 则与 `tools`、`append_system_prompt` 同一套路：新会话有那块，旧会话没有，折叠结果逐字节不变。被否掉的另一条是「只写进工具描述」——那条路让它不进折叠结果，屏幕上与日志里都看不见，等于把事实藏在 provider 请求里。

**D2 只记 `os` 与 `shell` 两个字段，不记代码页。**
代码页要么走 `ctypes.GetOEMCP`（新依赖、只在 Windows 有意义），要么 `locale.getpreferredencoding(False)`（Windows 上给的是 ANSI 码页，不等于 `cmd.exe` 实际用的 OEM 码页）。两条都可能记下一个**错的事实**，而错的运行时事实比没有更糟——它会写进每一轮上下文。解码不动，所以「命令输出按 UTF-8 解码、非法字节显示为替换字符」这句是**关于 harness 自己的说明**，不是平台事实，放在运行环境块里随块一起出现。

**D3 `shell` 这份事实由 `tools/bash_tools.py` 提供，CLI 只搬运。**
它已经按平台分支决定怎么起进程；让 CLI 自己再判一次平台，就有两处判断同一件事，早晚分叉。事实住在知道它的那一层，CLI 负责把它写进 `session/start`。

**D4 那块的位置在工具块之后、追加文本之前。**
既有判据钉着「折叠结果第一条仍是内置常量」与「追加文本出现在头部内」，把新块插到最前会撞前者，插到追加文本之后会让 `--append-system-prompt` 不再是头部最后一块。放在中间，两条既有判据都不用改措辞。

**D5 不记工作区根。**
`session/start` 已经有 `workspace`，工作区边界由围栏强制（不变量 E）。把路径再抄一份进头部不增加判据，只增加预算占用。

**D6 建议与事实同一块，且建议只由日志里的 `platform` 推出。**
UAT 里失败的不只是「不知道是 Windows」，而是知道之后的下一步；Gemini CLI 的做法就是按 `process.platform` 生成命令建议（`grep`/`tail`/`head` 在 win32 上换成 `type`/`findstr`/`Get-Content`）。但建议 MUST 由记下来的 `shell` 推出：如果折叠时读 `process.platform`，同一份日志在两台机器上重放会产出不同的头部，`REPLAY_MISMATCH`。被否掉的：只给事实不给建议（Claude Code 的形状，UAT 说明不够）；把建议写死在 `SYSTEM_PROMPT` 里（旧日志全部不一致）；建议单独成一块（同一份事实两个来源，位置也要重新论证）。

**D7 原生工具的引导放在描述里，平台相关的半句只放在头部。**
「列目录用 `glob`、搜内容用 `grep`、读文件用 `read`」是平台无关的，放在四个工具的描述里；一旦把 `dir` 写进描述，Linux 上就错了，而且平台事实会有第二个来源。被否掉的：把平台事实写进描述（不进折叠结果、日志里看不见）；按平台生成描述（描述在重放里没有记录，无法核对，且多一个平台判断点）。临时脚本也不列为等价手段（ADR-0030）——Python 版本在机器之间不一致，同版本在不同平台上的行为也未必一致。

**测试策略（seam 边界）。**
seam ②（工具注册与管线）：`bash` 暴露的 shell 形态与它实际起进程用的形态一致；四个描述里的引导在、且都不含平台专用字样。seam ④（日志追加与折叠）：`session/start` 多一个字段；折叠头部多一块、位置正确；同一份日志记 win32 与记 posix 各出各的建议；**没有该字段的旧日志折叠结果逐字节不变**。seam ⑥（CLI 黑盒）：三个入口都写、`replay` 对旧日志不出 `REPLAY_MISMATCH`、对新日志逐字段复现。不新增缝——装配与配置都在 ② 与 ⑥ 判（AGENTS.md）。

## Risks / Trade-offs

- [一批钉头部形状的测试与 fixture 会红] → 先跑全量看红在哪，逐条改**判据**；不许为了让 fixture 不变而把新块挪位置或改成可选。
- [建议文本读当前机器的平台，导致换机器重放不一致] → 判据用「日志里记 `nt` / `cmd.exe /c`、判据机器是什么平台都一样」来钉住；实现里只读 `platform` 字段，不读 `process.platform`。
- [头部变多让窗口更早触发，小窗口那一族的既有判据可能跟着动] → 触发线公式不动；若某条判据因头部变多而失效，改那条判据的窗口数值，并在提交信息里写明是判据跟着事实变多而调，不是放宽不变量 D。
- [真实端点那一半可能仍然看见试错正文] → 判据不写成「模型不再试错」（不可控），写成「模型收到的头部里有这两个事实与本平台建议」+ 人在 UAT 里观察屏幕上那段试错正文是否变短、以及它列目录时选 `glob` 还是 `bash ls`。
- [分支依赖] → 本分支建在 `change/fix-chat-screen-feedback` 之上（ADR-0024 / 0025 的收尾四项与 `-uat.md` 约定、以及 `events/fold.py` 与 `cli/main.py` 的当前形状都在那条分支上）。先合它、再合这个；顺序反了会在主干上留下「代码已合、主规格还停在上一个里程碑」的窗口。
- [ADR 编号跨分支会撞] → 本 change 占 0029 与 0030（本分支扫到最大号 0028）。别的分支已经各占：`fix-compaction-and-context-overflow` 与 `fix-post-compaction-budget-reading` 都是 0026、`add-key-driven-default-provider` 是 0027、本分支的上游 `fix-chat-screen-feedback` 是 0028。撞号由人在 merge 时裁。
