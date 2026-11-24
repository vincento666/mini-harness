# 分层直接落地清单（复核确认版）

**日期**：2026-11-18 17:10　**性质**：对 `docs/analysis-poteto-gap-2026-11-18.md`（下称「差距分析」）的复核确认与分层落地收口，一次性分析件，不进读量清单　**方法**：全部条目先对仓库实况核验后才写入；核验口径以 `git log` / 脚本内容 / 自动化运行记录为准（AGENTS.md「接手先核实时状态」）。

**资料来源**：差距分析所列七份文档，加本轮新增核验对象：`scripts/gates.sh`、`scripts/coverage-report.sh`、`.workbuddy/memory/automations/` 两个自动化运行记录、`openspec/changes/m13-goal-rounds/tasks.md`、`git log`（HEAD `651d4cc`）。

**分区规则**：「底座」行为可验证事实；「落地内容与方法」为建议（含方法步骤），按三类标注——**①零规则改动·当下可做**、**②需人裁一处规则**、**③roadmap 既定·走正常 change 流程**；最终取舍由人裁决。

---

## 0. 本轮复核发现的三处实况变化（先于清单，影响上一轮结论）

1. **上一轮 P0-1（修覆盖率合并接线）已被仓库实况替代，不成立**。`docs/CURRENT.md`（2026-11-18 更新）记载：「combine 不求并集」的结论**已撤回**——错在读数方法（为了看单文件反复手跑 `coverage report`，而 reporting 命令出报告前会 `combine` 且默认 `keep=False` 删掉全部 partial，见 `coverage/cmdline.py:884-887`），不在 partial 机制；且「关 parallel + 单文件 append」**明确不做**（并发子进程对同一 SQLite 数据文件有写冲突风险，收益只是少一步 combine）。修复方案是 `precision = 2` + `coverage-report.sh` 加 `--keep-combined` + 补 15 条真实分支判据，实测 **95.03%（4612 / 229）**，门禁绿。
2. **上一轮 P0-2（启动 L0 每日观察）已上线**。`.workbuddy/memory/automations/` 下两个自动化均有运行记录：「研发流程自检（L1 只读）」（2026-11-16、11-17 两次）与「只读巡检（L0/L1）」（2026-11-18 11:46）。后者已产出调度雏形信号（如「计划要求 11-18 当日完成 M13……进度与计划口径有落差」）。
3. **M13 已在 apply 中段**，不再是「等人审 proposal」。`tasks.md` 9/19 已勾（0.1 契约复核、1.1–1.2、2.1–2.2、3.1–3.4），第 4 组（轮次驱动）进行中（工作区有未跟踪的 `tests/test_goal_rounds.py`）。**偏差报告**（按 AGENTS.md「以仓库实况为准并报告偏差」）：`docs/CURRENT.md` 的「活动 change」行仍写「等人审 proposal 与契约、提交 `03c7dce`」，实况 HEAD 为 `651d4cc`、9/19 已勾；`docs/process/devops-loop.md` §6 写「日程要人确认后才建」，实况两条自动化已运行三天。两处均为文档滞后，本报告不代改，留人裁。

**由此更新的风险基数**：覆盖率地板余量仅 **0.03pp**（95.03% vs 95）——任何新增代码都可能踩线，夜间批与并行会把「补判据」变成常态负担，这取代覆盖率机制本身成为新的约束点。

---

## 1. 层级划分口径

按「离落地动作的距离」分六层。层级之间是包含关系不是并列关系：A/B 是底座，C/D 是放大器，E 是产品化（把文中的 Bot 军团做成本项目能跑的能力），F 是放行（文中第五阶信任的落点）。

---

## 2. 层级 A：门禁与验证层（Verification is all you need）

**底座（事实）**：四道门禁 + 三半完成判据 + 变异测试 + 契约双重复核已制度化（AGENTS.md「流程」节、ADR-0024/0025）；`gates.sh` / `coverage-report.sh` 分工明确（沙箱删除额度所致，脚本内零删除）；覆盖率纪律「只跑 coverage-report.sh、不为看单文件再跑第二次」已入 CURRENT。

**直接落地**：

| 项 | 类别 | 方法 | 判据 | 风险 |
|---|---|---|---|---|
| A1 夜间验收批脚本 | ① | 新增 `scripts/night-verify.sh`：`git worktree add .tmp/verify-<id> change/<id>` → 在 worktree 内跑 `gates.sh` + `coverage-report.sh` → 产物落 `docs/verification/<id>-night-<date>.log`；清理 partial 走既有办法（`mv .coverage.* .tmp/cov-archive/`，移动不算删除） | 对 `change/m13-goal-rounds` 跑通，报告含四道退出码与 TOTAL；主工作区 `git status` 不被污染 | worktree 里 uv 环境重建成本；覆盖率 0.03pp 余量使「夜间批转红」频次可能偏高，报告须把「差几个百分点」写清楚，避免误读 |
| A2 验证执行独立化 | ② | 三半中 mock/真实两半的**执行**改由独立上下文子代理完成（WorkBuddy 只读子代理，非 mini 自己的 `subagent`——devops-loop §4 禁止被测对象当裁判）；输入=分支名+契约路径+两条命令，输出=PASS/FAIL+原始日志摘录 | 抽样一次：验证会话数字与独立复跑一致；验证会话零写入 | 与 §4「子代理只读」冲突，需人裁精化为「禁写文件、可跑门禁命令」；token 成本约翻倍 |

---

## 3. 层级 B：流程与纪律层（让正确做法=最容易的做法）

**底座（事实）**：切片纪律（判据先行、红绿循环、一提交≤3 task）、六类升级触发、五类停点、四段弹窗格式、`new-change.sh` / `check-change.sh` / pre-commit hook 已脚本化；「机械步骤一律脚本化」写入 §0.6 第 7 条。

**直接落地**：

| 项 | 类别 | 方法 | 判据 | 风险 |
|---|---|---|---|---|
| B1 四类 change 的 Playbook 模板 | ① | 在 `docs/verification/templates/` 放四份验证契约骨架（bugfix / 新工具 / 规格修正 / 性能），各带 3–5 条坏法清单种子；propose 时按类套用。属新增模板文件，不动 `docs/process/`（净增约束只限该目录） | 下一个新 change 的契约复核 GAPS 轮数下降（现上限两轮） | 模板僵化（为模板而写）；模板只准删不准堆 |
| B2 Learning Gate 机器化分流 | ② | Learning Gate 扫描时先问「这条教训能否转成机器强制？」处置顺序：ruff 规则 → `harness_hooks.py` / CI 检查 → 测试反例 fixture；不可机器化才进 `docs/lessons.md`。机器化门槛：Seen ≥2 | 下一个 change 的 Learning Gate 产出含「机器化落点或不可机器化理由」；同类错误被回归拦住 | 改 AGENTS.md 流程段，按 §1.1 第 3 类人裁；「一进一出」抵扣净增 |
| B3 lessons 收件箱消化 | ① | inbox 现 11 条、消化率约 8%（L1 自检记录），按既有收敛纪律做一次归并（合并同类→原文移 lessons-archive→归档后跑 `agents-md-slim`） | inbox ≤ 9 条；合并后条目保留原始编号可回查 | 归并把证据链压没——合并时保留 Evidence 行 |

---

## 4. 层级 C：调度与外环层（双循环 / 幕僚长）

**底座（事实）**：L0（只读巡检）与 L1（研发流程自检）两条自动化已上线且有连续三天运行记录，覆盖 §6 必报指标（未勾 task、CI 结论、分支落后数、文档行数、inbox 条数等）；L0 已产出计划落差类信号。

**直接落地**：

| 项 | 类别 | 方法 | 判据 | 风险 |
|---|---|---|---|---|
| C1 扩展 L0 采集面 | ① | 在既有 L0 自动化 prompt 里加两项：① 扫 `docs/CURRENT.md` 开放缺口与 `docs/lessons.md` 收件箱，产出「候选任务简报」（只分类不 propose，守 §6「分诊不是 propose」）；② 对照当周 `docs/plan-*.md` 报「今天该推进哪一项、昨天欠了什么」（W47 计划「每日节奏」本就如此要求） | 简报连续 5 个工作日零误报；空时只输出一行「无新事项；下一里程碑：X」 | 采集噪声稀释注意力；严禁越界自动 propose |
| C2 夜间批调度 | ① | 把 A1 脚本挂到一条夜间定时任务上，只对「已 apply 完、待收尾验收」的 change 跑；白天人只读报告 | 每个工作日上午有一份夜间报告；报告含 PASS/FAIL 与差距数字 | 任务描述须自包含（分支名、命令、产物路径写进 prompt）；不得连带 merge |
| C3 devops-loop §6 文档滞后修正 | ② | 一行改动：把「日程要人确认后才建」改为「L0/L1 已建，见 `.workbuddy/memory/automations/`」 | 文档与实况一致 | 流程文档净增 ≤0，需人裁或以删代改（压缩同节旧句抵扣） |

---

## 5. 层级 D：知识与共享上下文层（Feature Map / 园丁）

**底座（事实）**：真源结构清楚（AGENTS.md 读量纪律、specs 为规格真源、GLOSSARY 词表）；园丁机制的「教训→文本规则」通路（lessons + 一进一出）已在跑；M14a 工作区契约 / M14c plan 已完成；MEM1 在 roadmap。

**直接落地**：

| 项 | 类别 | 方法 | 判据 | 风险 |
|---|---|---|---|---|
| D1 Feature Map 派生页 | ① | 只读脚本从 `openspec/specs/` + `GLOSSARY.md` 生成一页「现况清单」（命令面、事件词表、结果词表、七个 seam、开放缺口），归档 change 后重新生成；派生文件禁手改（`check-change.sh` 加一条漂移检查） | 派生页逐项可追溯到 spec 条目；手改会被 check-change 拒绝 | 双真源风险只允许「派生」化解；该页不进「先读这三样」，只在装配/接手场景读 |
| D2 园丁机器化 | ② | 即 B2，同项不重复计 | — | — |

---

## 6. 层级 E：产品机制层（Bot 军团的运行底座，走正常 change 流程）

**底座（事实）**：委派（M12）、subagent preset + persona（persona 已在 `src/` 落地，本轮 grep 确认）、技能/命令（M14）、todo/plan/ask_user/present（M14c）、goal 轮次（M13 进行中 9/19）；无人值守入口条件已写死（H1/H2/M11/M14/MEM1/M15a 全完成才允许 `approval: auto`）。

**直接落地（③类：每项就是一个正常 change，无需改任何流程规则）**：

| 项 | 对应文中的效果 | 当前状态 | 方法要点 |
|---|---|---|---|
| E1 M13 目标轮次收尾 | 长任务不靠人反复续跑（夜间批量异步的产品前提） | apply 中段，余 4.x/5.x/6.x 共 10 task | 按 tasks.md 顺序续推；收尾四项（真实端点/UAT/变异/Learning Gate）不可省 |
| E2 M15a 进程收容 | 无人值守安全边界 | 未开始 | M13 后立即；坐在 M10 `CommandRunner` 缝上 |
| E3 MEM1 基础记忆 | Feature Map 的产品化（跨会话共享上下文） | 未开始 | 项目/用户 `MEMORY.md` + `memory` 工具 + `memory/loaded` 事件 |
| E4 E1 评测 runner | 「客观证据」的量化层（成功率/回合数/token/并发） | `scripts/eval/` 仅 README | 最小三任务 + held-out 基线 + report.json |
| E5 E2 组件接缝的 `Verifier` / `SubagentPolicy` | 校验 Bot 与角色隔离的产品化 | 未开始（E2 排 M 核心后） | 会话间可替换 + 默认组合行为不变 |
| E6 角色 Prompt 库 | 文中四角色 System Prompt 大包 | persona 基座已具备 | 把「契约复核者/对照门禁复核者/验证执行者/需求翻译」四份角色契约写成仓库内 preset/skill（开发流程用 WorkBuddy 子代理调用；产品侧即 preset 消费者） |

E6 的独立判据：四个角色各复现跑一次历史 change，输出格式稳定、验证者与复核者零写入。风险：`devops-loop.md` §4 边界——流程复核必须用编码 harness 的子代理，不得用被测 mini 的 `subagent` 既当运动员又当裁判。

---

## 7. 层级 F：吞吐与放行层（文中第五阶信任的落点，以②类为主）

| 项 | 类别 | 方法 | 判据 | 风险 |
|---|---|---|---|---|
| F1 有限并行 change | ①试点②常规化 | 试点：两个互不依赖 change（如 E4 E1-runner 与 E3 MEM1）各在 `change/<id>` 分支 + 独立 worktree 推进，夜间批分别验收，合并顺序人排。分支纪律本身不禁止并行，但主 agent 上下文与 CI 资源翻倍，常规化前建议人裁 | 两个 change 门禁互不污染；spec sync 冲突在归档时一次解 | 同一 spec 被两 change 改动会撞 sync；覆盖率 0.03pp 余量使并行补判据成本高；**硬前置 = A1 夜间批就绪** |
| F2 分级放行（低风险自动合并） | ② | 仅当「不触碰 A–F 不变量、不含安全面/规格语义变更、四道绿、对照门禁 PASS、变异全杀」时自动合入；其余保留人批。保守替代：不自动合并，改「人每日一次批量批准清单」（零规则改动） | 连续 10 个低风险 change 自动合入零回滚；任何回滚 case 回写为新的高风险分类条件 | **与 devops-loop §8「全自动 merge」明文禁止冲突**，采纳必须人裁 + 开 ADR（`docs/adr/` 下一号 0043）+ revert playbook；分类错误的代价是坏提交进 main |
| F3 夜间真实端点 | ② | 夜间批默认只跑 mock 门禁；真实端点需人单次授权 + 预算上限（六类升级第 3 类「成本显著上升」） | 每次授权有预算记录；超支自动停 | 费用与密钥暴露面；真实端点不进 CI（既有纪律） |

---

## 8. 汇总：按「能不能今天动手」排

**①零规则改动·今天可动手（6 项）**：A1 夜间验收批脚本 · B1 Playbook 模板 · B3 lessons 归并 · C1 扩展 L0 采集面 · C2 夜间批调度挂载 · D1 Feature Map 派生页。

**②需人裁一处规则（5 项，各自独立裁决）**：A2 验证执行独立化（精化「只读」）· B2 Learning Gate 机器化分流（改 AGENTS.md 流程段）· C3 devops-loop §6 滞后修正 · F2 分级放行（改 §8 + ADR-0043；或选保守替代）· F3 夜间真实端点授权。

**③roadmap 既定·走正常 change（6 项）**：E1–E6（M13 收尾 → M15a → MEM1 → E1 runner → E2 组件 → 角色 Prompt 库）。

**建议的启动顺序**：A1 → C2（当晚即有夜间报告）→ B3 + D1（消化与派生，半天内）→ C1（改 L0 prompt）→ E1（M13 收尾本来就该继续）→ 其余按人裁结果穿插。

---

## 9. 事实与推测分区声明

- **可验证事实**：第 0 节全部（git log、CURRENT.md 更新、自动化运行记录、tasks.md 勾选数、脚本内容、覆盖率实测数字均可当场复核）；各层「底座」行；第 8 节的分类依据（分类标准是既定文档的条款有无）。
- **建议与推测**：各表「方法」「判据」「风险」列、第 8 节启动顺序。文中效果（一人调度、夜间批量、自动放行）的达成度判断属推测——本清单只回答「什么能直接落地」，不承诺吞吐数字。
- 已删除内容：对文中体系复制成功率的任何估计；对 E 系列完成日期的承诺（W47 计划已明示「不砍判据、时间不够顺延」）。

---

## 引用文献（MLA）

老王，Jack.《一个人顶20人工程师团队：SpaceX女工程师的50+ Bot军团，月交付1000个PR的完整方法论》.《光复之路》，2026年11月5日，mp.weixin.qq.com/s/a62TEnabKjcKzcecSAq5WQ.

mini-harness.《AGENTS.md》《docs/CURRENT.md》《docs/process/devops-loop.md》《docs/roadmap.md》《docs/lessons.md》《docs/plan-2026-W47.md》. 仓库文档，2026年11月版本.

mini-harness.《scripts/gates.sh》《scripts/coverage-report.sh》. 仓库脚本，2026年11月18日版本.

mini-harness.《.workbuddy/memory/automations/》运行记录（研发流程自检 L1；只读巡检 L0/L1）. 2026年11月16–18日.

mini-harness.《openspec/changes/m13-goal-rounds/tasks.md》. 2026年11月18日版本.
