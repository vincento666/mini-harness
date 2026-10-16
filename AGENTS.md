# mini-harness

个人实验版 agent harness 的 MVP。headless CLI 优先，架构决策照抄 DeepSeek Harness（DSH）的核心思想，用 OpenSpec 做规格（SDD）、用 TDD 做实现。

**当前状态**：**M1 完成并已归档** —— 62 个测试全绿、`uv run mypy --strict src` 干净（17 个源文件）、`uv run ruff check src tests` 干净（覆盖率实测 76% / 地板 75），change `m1-event-log-and-turn-loop` 已合入 `main`（merge commit `141e28c`）并归档到 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`。五份主规格已同步进 `openspec/specs/`：`cli`、`context-projection`、`event-log`、`provider`、`turn-loop`，共 33 个 Requirement / 53 个 Scenario，`openspec validate --specs` 全过。延后的重构与已知缺口见 `docs/adr/0002-deferred-refactors.md` 和 `docs/verification/m1-mutation.md` 的「剩余已知缺口」。下一个里程碑是 **M2**，等用户发话再 `/openspec-propose m2-file-tools-and-fences`。

已装的 OpenSpec 工作流（core profile，delivery=skills）：`openspec-propose`、`openspec-explore`、`openspec-apply-change`、`openspec-update-change`、`openspec-sync-specs`、`openspec-archive-change`。`openspec-verify-change` **未装**——它要 `openspec config profile` 交互勾选；在它可用之前，规格与实现的一致性用 `code-review` 技能（Standards / Spec 两轴）代劳。

---

## 先读这三样，再动手

1. **`docs/handoff-2026-10-15.md`** —— 已锁定的 **38 条编号决策 + 6 条不变量**，这就是规格输入。**不要重新 grill**，除非实现过程中出现新的设计分叉。
2. **`docs/dsh-reference/DSH运行时设计说明.html`** —— 入门三节（什么是 harness / 通用十格流水线 / 上下文压缩）+ 8 章 + 8 张算法卡，每节配图折叠内嵌。
3. **`docs/dsh-reference/DSH运行时设计图集.html`** —— 75 张图，锚点形如 `#fig-<图名>`；要照某个机制实现时，先把那张图的锚点读出来。

---

## 编码行为四规

摘要在此，**全文见 `docs/reference/karpathy-claude-md.md`**（来源 <https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md>，逐字留存）。与上面的「先读这三样」或下面的六条不变量冲突时，**以本文件与 `openspec/specs/` 为准**。

1. **先想再写**：假设写出来；同一句话有多种读法时把读法摆出来让人裁决，不许默默选一种。
2. **最简实现**：不为单次使用的代码加抽象，不加没被要求过的可配置性，不为不可能的场景写错误处理。M1 里 `dispatch` 那个 `OK` 占位就是这条要抓的东西。
3. **只改必须改的**：不顺手「改善」相邻代码，不重构没坏的东西，不删与本次改动无关的死代码；自己改动造成的孤儿 import 自己清。已识别的坏味道只记账进 `docs/adr/0002-deferred-refactors.md`，到对应里程碑再动。
4. **把任务写成可验证的判据**：修 bug 先写能复现它的测试；每个里程碑有完成判据；收尾跑一轮变异测试，判据是「每个变异都被至少一条测试杀死」。

---

## 命令

```bash
uv sync                       # 装依赖（含 dev）
uv run pytest                 # 全部测试（含覆盖率地板）
uv run pytest -k <表达式>     # 单个红绿循环
uv run mypy --strict src      # 类型检查
uv run ruff check src tests   # 风格门禁
uv run ruff format --diff src tests   # 看还有没有没格式化的（空输出 = 干净）
uv run minihns run -p "任务" --provider mock --fixture <turns.json> --workspace <dir> --events jsonl
uv run minihns replay <session-id>
uv run minihns chat           # M6 之后
uv run minihns serve --http   # M7 之后
```

---

## 门禁：有哪几道、各自由谁规定

一次提交算「完成」= 前四道在命令行上全绿；后三道是里程碑收尾时跑的。

| 门禁 | 跑什么 | 规定它的东西 |
|---|---|---|
| 测试 | `uv run pytest` | pytest + pytest-asyncio；测试只写在六个 seam 上，当前 62 个 |
| 覆盖率地板 | 同上（`addopts` 里 `--cov=mini_harness --cov-report=term-missing`） | `pyproject.toml` 的 `[tool.coverage.report] fail_under = 75`，实测 76% |
| 类型 | `uv run mypy --strict src` | `[tool.mypy] strict = true`，17 个源文件 |
| 风格 | `uv run ruff check src tests` | `[tool.ruff]` + `[tool.ruff.lint] select = ["E","F","I","UP","B","SIM","C4","RUF"]`，`line-length = 100` |
| 规格结构 | `openspec validate --specs` | OpenSpec（主 specs 的 Requirement / Scenario 形状） |
| 规格 ↔ 实现 | `code-review` 技能，Standards 与 Spec 两轴 | 本文件流程节（`openspec-verify-change` 未装，由它代劳） |
| 变异测试 | 每个里程碑收尾一轮 | 本文件流程节；记录进 `docs/verification/<change-id>-mutation.md` |

**覆盖率地板为什么只有 75**：seam ⑥ 的 CLI 测试是 subprocess 黑盒，跑在子进程里，不计进这次进程内的覆盖率，`cli/main.py` 因此只有 36%。要抬地板先解决「子进程也记账」，不要靠补低价值测试凑数。

**ruff 唯一的例外**：`allowed-confusables = ["：", "，", "；", "（", "）"]`。本项目的 docstring / 注释 / 面向用户的字符串一律用中文全角标点，RUF001/RUF002/RUF003 把这几个字符当成「可疑的 ASCII 近似字符」报警，与这条成文规范冲突；其中 `SYSTEM_PROMPT` 与 `未注册的工具：read` 是规格里的字面量，改标点就是改行为。全仓没有一处 `# noqa`。

---

## 六条不可让步的运行时不变量

| | 不变量 | 大白话 |
|---|---|---|
| A | 事件日志是唯一真源，只追加不改写；当前上下文由折叠派生 | 账本只往后记，「现在算数的内容」是算出来的 |
| B | 工具是能力契约，定义与执行分离；**失败也是结果** | 工具挂了返回 `UNKNOWN_TOOL`/`TOOL_TIMEOUT`/`ABORTED`，不抛异常打断回合 |
| C | 回合主循环显式：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止 | 循环是明写的，不是藏在回调里 |
| D | 上下文有窗口预算与显式溢出错误 `CONTEXT_WINDOW_EXCEEDED` | 桌子多大、什么时候收、收不动了就明说 |
| E | 能力受围栏约束：工作区边界 + 写前必读 CAS + 「能干什么」与「要不要问人」两条独立轴 | 权限开关和问不问人是两回事 |
| F | 全程可观测：CLI 输出可重放的 JSONL 事件流 | 每次运行都能重放得到同一结果 |

---

## 流程：每个里程碑一个 OpenSpec change

```
/openspec-propose <change-id>   → 人工审阅 proposal / specs / design / tasks
/openspec-apply-change          → 按 tdd 技能实现：red → green 单切片，一次一个
/openspec-verify-change         → 校验实现与规格一致
/code-review                    → Standards 与 Spec 两轴
/openspec-archive-change        → 归档进 openspec/changes/archive/
```

分支纪律：每个 change 一个分支 `change/<id>`，完成后合入 `main` 并做 archive 提交。

**提交粒度**：一个红绿循环一次提交，提交信息带 task 编号，让 `git log` 能对上 `tasks.md` 的复选框。**一个提交最多覆盖同一 seam 上相邻的 3 个 task**；超过就在提交信息里写明为什么打包（例如同一个 seam 上的连续小步无法单独变红）。反例是 M1 的 `8320f1e`，它打包了 tasks 7.1–9.4 共 14 个任务，出问题不好二分。全量 `pytest` 只要 9 秒，没有理由为了省时间打包。

**测试只写在下面六个 seam 上**（tdd 技能要求先约定再写，不许水平切片）：
① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒（subprocess 跑真实命令）

**每个里程碑收尾跑一轮变异测试并记录**：改坏一处实现 → 跑全量测试 → 把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/<change-id>-mutation.md` → `git checkout --` 还原并确认回到基线。判据：每个变异都被至少一条测试杀死；存活的算覆盖缺口，补一条能杀死它的测试（先确认它在变异下红）。做法与判据见 `docs/verification/m1-mutation.md`。

---

## 里程碑

| | change | 内容 | 完成判据 |
|---|---|---|---|
| M1 | `m1-event-log-and-turn-loop` | JSONL 只追加 + 折叠 + 回合循环 + mock Provider + `minihns run` + `minihns replay` | mock 场景跑通；replay 与实时折叠一致 |
| M2 | `m2-file-tools-and-fences` | `read`/`write`/`edit`(CAS)/`glob`/`grep` + 工作区边界 + 写前必读 + 两轴 | 批量改文件成功；越界写被拒并写事件、退出码 3 |
| M3 | `m3-bash-concurrency-timeout` | `bash` + 只读并发（max 8）+ 超时与取消事件 | 一轮内并发读 ≥2；超时写 `tool/cancelled` 且回合继续 |
| M4 | `m4-real-provider-deepseek` | OpenAI 兼容适配器 + `parallel_tool_calls` + 429/5xx 重试一次 | 真实调用 smoke 通过；mock 与真实同一接口 |
| M5 | `m5-context-budget-compaction` | 窗口预算 + 触发线公式 + 剪枝 + 摘要 + 遮蔽 + 标记对 | 小 W 下触发压缩；原文事件仍在日志里 |
| M6 | `m6-chat-repl` | `minihns chat` REPL，复用同一内核入口 | REPL 续跑同一会话内核 |
| M7 | `m7-serve-http-sse` | `minihns serve --http` 输出 SSE 事件流 | 事件流与 JSONL 日志内容一致 |

---

## 技术选型（已定，不要重新讨论）

Python **>= 3.12** · **uv** · `src/mini_harness/` 布局 · **mypy strict** · **pydantic v2** · **argparse** · **pytest + pytest-asyncio** · asyncio 单事件循环 · 包名 `mini_harness`，命令名 **`minihns`** · 密钥只走 `DEEPSEEK_API_KEY` 环境变量。

## MVP 明确不做

插件容器与热更新、子代理委派与目标状态机、OS 级沙箱（Windows ACL / job object / landlock）、投影缓存与 `--resume`、PTC 工具面塌缩、多模型路由与重试策略、web / Electron 外壳实现、独立工单与 triage 标签体系。

---

## 引用纪律

- DSH 的事实只引 `docs/dsh-reference/` 里的四份文档与 `DSH逆向分析报告.md`。
- 需要更细的出处时，只允许引 `S:\Develop\agent_harness\re\verified\dsh\` 与 `re\shell\`。**`re\full\` 是 8 字节偏移的损坏副本，永远不要引用**；不要 grep `rea/app-graph.json`。
- 写规格时把「DSH 这么做」与「mini 版故意简化」分开写，简化处必须在 `docs/adr/` 里写明代价（用 `domain-modeling` 技能写 ADR）。
- 四份参考 HTML 的图只做过静态结构校验，**没有视觉复核**。
