# mini-harness

个人实验版 agent harness 的 MVP。headless CLI 优先，架构决策照抄 DeepSeek Harness（DSH）的核心思想，用 OpenSpec 做规格（SDD）、用 TDD 做实现。

**当前状态与门禁实测**见 `docs/CURRENT.md`；**里程碑与完成判据**见 `docs/roadmap.md`。`openspec-verify-change` 未装，规格 ↔ 实现的一致性由 `code-review` 技能（Standards / Spec 两轴）代劳。

---

## 先读这三样，再动手

1. **`docs/handoff-2026-10-15.md`** —— 已锁定的**编号决策与运行时不变量**，这就是规格输入；**不要重新 grill**，除非出现新的设计分叉。它与后来的 ADR 分叉时**以 ADR 与 `docs/roadmap.md` 为准**，handoff 冻结不编辑。
2. **`docs/lessons.md`** —— 教训的收件箱与活跃区；Active Lessons 每次接手都读。
3. **`docs/CURRENT.md`** —— 当前进度、门禁实测、已知缺口。

**接手先核实时状态**：先 `git status --short` 与 `git log --oneline -3`。跟 `docs/CURRENT.md` 对不上时以仓库实况为准并报告偏差——不要相信上一段会话的叙事。

---

## 编码行为四规

1. **先想再写**：假设写出来；同一句话有多种读法时把读法摆出来让人裁决，不许默默选一种。
2. **最简实现**：不为单次使用的代码加抽象，不加没被要求过的可配置性，不为不可能的场景写错误处理。
3. **只改必须改的**：不顺手「改善」相邻代码，不重构没坏的东西，不删与本次改动无关的死代码；自己改动造成的孤儿 import 自己清。已识别的坏味道只记账进 `docs/adr/` 里的 ADR，到对应里程碑再动。
4. **把任务写成可验证的判据**：修 bug 先写能复现它的测试；每个里程碑有完成判据；收尾跑一轮变异测试（判据见下「流程」）。

---

## 命令

```bash
# 便宜的在前：格式 / 风格 / 类型最省，测试带覆盖率记账最贵
uv run ruff format --diff src tests
uv run ruff check src tests
uv run mypy --strict src
uv run coverage erase
uv run coverage run -m pytest -q
uv run coverage combine
uv run coverage report --fail-under=95 --show-missing   # 这三步不可拆，理由见下「覆盖率纪律」
```

---

## 门禁：有哪几道

一次提交算「完成」= **测试、覆盖率地板、`mypy --strict`、ruff** 四道全绿，通过信号都是**退出码 0**（覆盖率那道额外看 `TOTAL`）；规格结构、规格 ↔ 实现（`code-review` 两轴）、变异测试是里程碑收尾时跑的。地板数值与规则在 `pyproject.toml`。

**覆盖率纪律**：seam ⑥ 是真实子进程，每个子进程各写一份 partial，所以上面那三步不可拆。combine 只认内容不认新旧，旧 partial 混进这一轮是**看不见的**。要抬地板就补低覆盖处的判据，不要凑低价值测试。

**ruff 的例外只有两处**：中文全角标点与 `docs/tools/` 下的文档与图表构建脚本——门禁只跑 `src` 与 `tests`。

---

## 六条不可让步的运行时不变量

**A** 日志唯一真源，只追加不改写 · **B** 工具是能力契约，失败也是结果 · **C** 回合主循环显式 · **D** 窗口预算与 `CONTEXT_WINDOW_EXCEEDED` · **E** 围栏两条独立轴 + 工作区边界 + 写前必读 CAS · **F** 全程可观测

六条的全文在 OpenSpec 的 config 里，每个 `openspec` 命令都会自动读到它。**写任何代码前先读**；违反任何一条必须在 `docs/adr/` 留 ADR 并由人裁决，规格与测试不得自行放宽它们。

---

## 流程：每个里程碑一个 OpenSpec change

一个里程碑的顺序：**propose → 人审 proposal / specs / design / tasks → apply（按 tdd 技能，red → green 单切片，一次一个）→ `code-review` 两轴 → 变异测试一轮 + Learning Gate → 在 change 分支上 sync delta 进主规格 + 归档 → 代码与规格一次合入 main**。

分支纪律：每个 change 一个分支 `change/<id>`；**归档在分支上做**——sync 进主规格、移 `changeRoot`、`openspec validate --all --strict` 全绿，然后代码与规格一次合入 `main`。反过来（先合并再归档）会在主干上留下「代码已合、主规格还停在上一个里程碑」的窗口。**merge 与推 `main` 先征求人的批准、确认了才执行**；agent 可自行推 `change/<id>` 分支与归档提交。

**完成判据含一条人手验收**：拿它用真实工作区办一件真事（不是跑判据），观察记进 `docs/verification/<change-id>-manual.md`；不进 CI，也不替代门禁那四道。**依赖模型回复形状的功能，完成判据里还要有一次真实端点实测**（ADR-0022）：那一跑不进 CI，但不跑完这个 change 不算完成。

**提交粒度**：一个红绿循环一次提交，提交信息带 task 编号，让 `git log` 能对上 `tasks.md` 的复选框。**一个提交最多覆盖同一 seam 上相邻的 3 个 task**；超过就在提交信息里写明为什么打包（没有理由为了省时间打包）。

**测试只写在下面七个 seam 上**（tdd 技能要求先约定再写，不许水平切片）：
① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒（subprocess 跑真实命令） ⑦ 委派与目标（子日志与父日志的配对、目标轮次与 `blocked`）。组合层与扩展层**不新增缝**：装配、配置、技能与外部触发都在 ② 与 ⑥ 判。

**每个里程碑收尾跑一轮变异测试并记录**：改坏一处实现 → 跑全量测试 → 把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/<change-id>-mutation.md` → 还原并确认回到基线（**还原前先看 `git status`**，别把本轮未提交的改动一起回滚）。判据：每个变异都被至少一条测试杀死；存活的算覆盖缺口，补一条能杀死它的测试（先确认它在变异下红）。变异必须改变**可观察行为**，语义等价的改法是 dud mutant，不算。捕获一整个异常类族的代码，判据要用族里不显眼的那个成员。

**Learning Gate（变异测试之后、归档之前）**：扫本轮证据——红过的测试、存活的变异、返工过的规格、踩过的工具坑——可复用教训写进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`。**每个 change 的 `tasks.md` 末尾固定两项收尾任务：变异测试一轮、Learning Gate**（archive 时未勾会警告）。晋升进本文件的只能是一句话规则，且**一进一出**：同时删掉或压缩本文件一条旧内容。收件箱超过 15 条先消化再收；每里程碑归档后跑一次 `agents-md-slim`。

---

## 技术选型（已定，不要重新讨论）

Python **>= 3.12** · **uv** · `src/mini_harness/` 布局 · **mypy strict** · **pydantic v2** · **httpx** · **aiohttp**（M7 的 serve 服务端与 SSE） · **argparse** · **pytest + pytest-asyncio** · asyncio 单事件循环 · 包名 `mini_harness`，命令名 **`minihns`** · 密钥只走环境变量（默认 `DEEPSEEK_API_KEY`，`--api-key-env` 指定变量名）。

## MVP 分两阶段（ADR-0010）

**第一阶段**（M1 至 M9：内核 / 工件 / 组合 / 能力 / 模型的基础，围栏有雏形）**已完成**；进度看 `docs/CURRENT.md`。**第二阶段**（补全成**没有 web / Electron 外壳**的完整类 DSH 形态）：**M10 → M11 → M12 → M13 → M14 → M15**。**第三阶段**（加壳）等前两阶段做完再规划。每个里程碑做什么见 `docs/roadmap.md` 的表。**始终不做**：PTC 工具面塌缩、多模型路由与重试策略、独立工单与 triage 标签体系。

---

## 引用纪律

- DSH 的参考文档在本仓库 `docs/dsh-reference/`。**不要无差别先读**：只在照某个机制实现时去查对应章节或图的锚点（图集锚点形如 `#fig-<图名>`）。这些图只做过静态结构校验，**没有视觉复核**。
- 需要更细的出处时，只允许引 `S:\Develop\agent_harness\re\verified\dsh\` 与 `re\shell\`。**`re\full\` 是 8 字节偏移的损坏副本，永远不要引用**；不要 grep `rea/app-graph.json`（376 MB，分析时两次 OOM 被杀）。
- 写规格时把「DSH 这么做」与「mini 版故意简化」分开写，简化处必须在 `docs/adr/` 里写明代价（用 `domain-modeling` 技能写 ADR）。
- **ADR 的新增与读写一律照 `domain-modeling` 技能的 `ADR-FORMAT`**：`docs/adr/` 下顺序编号 `NNNN-slug.md`（编号扫现有最大号 +1，目录用到时才建），正文 1–3 句；三条判据（**难回退** / **无上下文会困惑** / **真实取舍**）同时成立才写；被重新审视的加 `Status` frontmatter，推翻就新开一份并在旧份标 `superseded`。**本文件不写死 ADR 编号**——欠账在哪份里看 `docs/CURRENT.md`。
