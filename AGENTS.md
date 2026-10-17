# mini-harness

个人实验版 agent harness 的 MVP。headless CLI 优先，架构决策照抄 DeepSeek Harness（DSH）的核心思想，用 OpenSpec 做规格（SDD）、用 TDD 做实现。

**当前状态与门禁实测**见 `docs/CURRENT.md`；**里程碑与完成判据**见 `docs/roadmap.md`。`openspec-verify-change` 未装，规格 ↔ 实现的一致性由 `code-review` 技能（Standards / Spec 两轴）代劳。

---

## 先读这四样，再动手

1. **`docs/handoff-2026-10-15.md`** —— 已锁定的 **38 条编号决策 + 6 条不变量**，这就是规格输入。**不要重新 grill**，除非实现过程中出现新的设计分叉。
2. **`docs/dsh-reference/DSH运行时设计说明.html`** 与 **`docs/dsh-reference/DSH运行时设计图集.html`** —— DSH 运行时机制的参考。要照某个机制实现，先读对应章节、或把对应图的锚点读出来（图集锚点形如 `#fig-<图名>`）。
3. **`docs/lessons.md`** —— 教训的收件箱与活跃区；Active Lessons 每次接手都读。
4. **`docs/CURRENT.md`** —— 当前进度、门禁实测、已知缺口。

**接手先核实时状态**：先 `git status --short` 与 `git log --oneline -3`。跟 `docs/CURRENT.md` 对不上时以仓库实况为准并报告偏差——不要相信上一段会话的叙事。

---

## 编码行为四规

摘要在此，**全文见 `docs/reference/karpathy-claude-md.md`**（来源 <https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md>，逐字留存）。与上面的「先读这四样」或下面的六条不变量冲突时，**以本文件与 `openspec/specs/` 为准**。

1. **先想再写**：假设写出来；同一句话有多种读法时把读法摆出来让人裁决，不许默默选一种。
2. **最简实现**：不为单次使用的代码加抽象，不加没被要求过的可配置性，不为不可能的场景写错误处理。
3. **只改必须改的**：不顺手「改善」相邻代码，不重构没坏的东西，不删与本次改动无关的死代码；自己改动造成的孤儿 import 自己清。已识别的坏味道只记账进 `docs/adr/0002-deferred-refactors.md`，到对应里程碑再动。
4. **把任务写成可验证的判据**：修 bug 先写能复现它的测试；每个里程碑有完成判据；收尾跑一轮变异测试，判据是「每个变异都被至少一条测试杀死」。

---

## 命令

```bash
uv run coverage erase         # 先清空旧 partial，再开始记账
uv run coverage run -m pytest -q        # 跑测试并记账：主进程 + seam ⑥ 的每个子进程各写一份 partial
uv run coverage combine                 # 把仓库根里的 partial 合并进 .coverage
uv run coverage report --fail-under=95 --show-missing   # 覆盖率地板
uv run mypy --strict src      # 类型检查
uv run ruff check src tests   # 风格门禁
uv run ruff format --diff src tests   # 干净 = 退出码 0 且没有 diff 块（它会往 stderr 打「N files already formatted」）
uv run minihns run -p "任务" --provider mock --fixture <turns.json> --workspace <dir> --events jsonl
uv run minihns replay <session-id>
```

---

## 门禁：有哪几道、各自由谁规定

一次提交算「完成」= 前四道全绿；后三道是里程碑收尾时跑的。命令见上面的命令段。每道的通过信号都是**退出码 0**（覆盖率那道额外看 `TOTAL` 行不低于地板）。

| 门禁 | 规定它的东西 |
|---|---|
| 测试 | pytest + pytest-asyncio；测试只写在六个预先约定的 seam 上 |
| 覆盖率地板 | `pyproject.toml` 的 `[tool.coverage.report] fail_under`；报告不在 pytest 的 `addopts` 里出 |
| 类型 | `[tool.mypy] strict = true` |
| 风格 | `[tool.ruff]` 与 `[tool.ruff.lint]`，具体规则在 `pyproject.toml` |
| 规格结构 | OpenSpec 的 Requirement / Scenario 形状 |
| 规格 ↔ 实现 | 本文件流程节（`code-review` 两轴） |
| 变异测试 | 本文件流程节；记录进 `docs/verification/<change-id>-mutation.md` |

**覆盖率纪律**：seam ⑥ 的 CLI 测试是真实子进程，记账分两段（主进程 + 每个子进程一份 partial，`coverage combine` 合并去重）。**先 `coverage erase` 再跑**：combine 只认内容不认新旧，旧 partial 混进这一轮是**看不见的**。记账是**无条件**的，全量测试因此 15 秒——换来的是「不会因为忘了加开关而悄悄不记账」。要抬地板就补低覆盖处的判据，不要凑低价值测试。

**ruff 唯一的例外**：`allowed-confusables` 放行中文全角标点 `：，；（）`。本项目的 docstring / 注释 / 面向用户的字符串一律用中文全角标点，RUF001/RUF002/RUF003 会把它们当成「可疑的 ASCII 近似字符」报警，与这条成文规范冲突；其中部分是规格里的字面量，改标点就是改行为。全仓没有一处 `# noqa`。

---

## 六条不可让步的运行时不变量

**A** 日志唯一真源，只追加不改写 · **B** 工具是能力契约，失败也是结果 · **C** 回合主循环显式 · **D** 窗口预算与 `CONTEXT_WINDOW_EXCEEDED` · **E** 围栏两条独立轴 + 工作区边界 + 写前必读 CAS · **F** 全程可观测

全文见 `openspec/config.yaml` 的 `context`（每个 OpenSpec 命令都会自动读到它）与 `docs/handoff-2026-10-15.md` §4.2。**写任何代码前先读**；违反任何一条必须在 `docs/adr/` 留 ADR 并由人裁决，规格与测试不得自行放宽它们。

---

## 流程：每个里程碑一个 OpenSpec change

```
/openspec-propose <change-id>   → 人工审阅 proposal / specs / design / tasks
/openspec-apply-change          → 按 tdd 技能实现：red → green 单切片，一次一个
/code-review                    → Standards 与 Spec 两轴（`openspec-verify-change` 未装，规格 ↔ 实现由它代劳）
收尾门禁                        → 变异测试一轮 + Learning Gate
/openspec-archive-change        → 归档进 openspec/changes/archive/
```

分支纪律：每个 change 一个分支 `change/<id>`，完成后合入 `main` 并做 archive 提交。

**提交粒度**：一个红绿循环一次提交，提交信息带 task 编号，让 `git log` 能对上 `tasks.md` 的复选框。**一个提交最多覆盖同一 seam 上相邻的 3 个 task**；超过就在提交信息里写明为什么打包（例如同一个 seam 上的连续小步无法单独变红）。全量测试带覆盖率记账只要 15 秒，没有理由为了省时间打包。

**测试只写在下面六个 seam 上**（tdd 技能要求先约定再写，不许水平切片）：
① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒（subprocess 跑真实命令）

**每个里程碑收尾跑一轮变异测试并记录**：改坏一处实现 → 跑全量测试 → 把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/<change-id>-mutation.md` → 还原并确认回到基线（**还原前先看 `git status`**，别把本轮未提交的改动一起回滚）。判据：每个变异都被至少一条测试杀死；存活的算覆盖缺口，补一条能杀死它的测试（先确认它在变异下红）。变异必须改变**可观察行为**，语义等价的改法是 dud mutant，不算。做法与判据见 `docs/verification/m1-mutation.md`。

**Learning Gate（变异测试之后、归档之前）**：扫本轮证据——红过的测试、存活的变异、返工过的规格、踩过的工具坑——可复用教训写进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`。**每个 change 的 `tasks.md` 末尾固定两项收尾任务：变异测试一轮、Learning Gate**（archive 时未勾会警告）。晋升进本文件的只能是一句话规则，且**一进一出**：同时删掉或压缩本文件一条旧内容。收件箱超过 15 条先消化再收；每里程碑归档后跑一次 `agents-md-slim`。

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
