# Loop Lessons

教训的**收件箱与活跃区**。机制照 `universal-work-loop` 的 Learning Gate：每次里程碑收尾或 `code-review` 之后扫一遍证据，把可复用的信号写进这里；**AGENTS.md 只接收晋升后的压缩规则，且每次晋升必须同时删掉或压缩 AGENTS.md 里的一条旧内容（一进一出）**。

`Status`：`inbox`（待消化）| `active`（每次进入本项目工作都读）| `promoted`（已写进 AGENTS.md）| `rejected`。

## Active Lessons

现在只有这五条会常驻；其余留在收件箱。

1. **词表类规格必须配「每个值都可达」的测试**。M1 的 `turn/end.stop_reason` 从成功路径倒推，漏了 `TOOL_CALLS`；`ABORTED` 写了却不可达，直到实现才暴露。
2. **写新 Requirement 时成对检查它跟已有 Requirement 是否互斥**。「每个非零退出都有 `error/*` 事件」与「重放不追加事件」各自正确、合起来不可满足，最后靠 ADR-0001 开一个显式例外收场。
3. **测试写下即绿就是危险信号**。M1 有约 24 个切片没有红。判据不是测试数量，是变异测试：两轮共 18 个变异、16 个被杀，存活的 `G` 与 `P` 各换回一条判据（`P` 证明当时没有任何 CLI 测试守 `LOG_WRITE_FAILED`）。
4. **接手前先核实时状态，不要相信上一段的叙事**。M1 期间 `git checkout --` 误回滚了未提交的改动，导致一次 `ImportError`。跑 `git status --short` 与 `git log --oneline -3` 再动手。
5. **文本文件绝不经 PowerShell 往返，读也要显式 `-Encoding UTF8`**。`Set-Content` 毁 UTF-8（真毁过一次测试文件），`Out-File -Encoding utf8` 带 BOM，`>` 产生 UTF-16LE；不带 `-Encoding UTF8` 的 `Get-Content` 连行数都会数错（见 L-013），还会把中文注释行与紧随其后的代码行粘成一行（见 L-022）。改文件用编辑工具；要读命令的 stderr 就 `2> 文件` 再读。

## Candidate Inbox

2026-11-16 归并：29 条原文移到 `docs/lessons-archive.md`，这里按类合并成 9 条。合并时保留了原始编号，便于回查。

### L-074
- Seen: 6（不同日期：2026-10-16/21/22/23/24/25）
- Promotion: 已晋升（2026-11-16 → AGENTS.md「编码行为四规」第 4 条）
- Date: 2026-11-16
- Context: 归并自 L-005 / L-036 / L-041 / L-048 / L-055（`fix-small-window-compaction-dead-zone`）/ L-056（同 change 的 delta）
- Observation: 判据写成「字段存在」「顺序正确」「常见形状能过」时，坏法只要换一格就活下来：自指断言把待判值写在两侧（L-036）、只断言三条字段在不在（L-041）、只覆盖入口常见的形状（L-048）、判据落在实现之后就没见过红（L-055）、场景有一半在装配缝上不可达（L-056）
- Evidence: `docs/lessons-archive.md` 对应条目；M9 变异 5、M6 三条存活变异、`fix-small-window-compaction-dead-zone` 的 4.1 与 2.3
- Next use: 每条 Scenario 先列「坏法清单」再写断言；断言里不得出现待判值自身；红绿循环记一行「红的样子」，没红就写原因
- Status: promoted

### L-075
- Seen: 2（不同日期：2026-10-23/29）
- Date: 2026-11-16
- Context: 归并自 L-059 / L-060 / L-066
- Observation: 判据会绿在「本机恰好没有那个环境变量」上（L-059）；撤掉一条检查后 mock 判据会真向公网发请求（L-060）；用「一整行 50000 字符」构造大结果时，工具的单行上限先把结果截到 2000 字符，fixture 想造的语义已经不在了（L-066）
- Evidence: `docs/lessons-archive.md` 对应条目；`test_a_bare_run_with_the_key_present_defaults_to_openai` 的 argv
- Next use: 判据开头显式构造环境（清掉真实变量再写假值）；fixture 用真实端点产物；造大结果前先确认工具自身的上限不会先截断
- Status: inbox

### L-076
- Seen: 1（不同日期：2026-11-05）
- Date: 2026-11-16
- Context: 归并自 L-070
- Observation: 用 `session + 首尾 seq + 条数` 做缓存 key，会让不同日志、不同内容在相同 seq 形状下碰撞，测试拿到上一份 messages；日志 append-only 不等于「任意同 seq 形状都同内容」
- Evidence: `docs/lessons-archive.md` L-070
- Next use: 按日志派生的缓存，key 带内容指纹，或把缓存绑定到确有版本的对象
- Status: inbox

### L-077
- Promotion: ready（≥3 个不同日期）
- Seen: 3（不同日期：2026-10-21/23/27）
- Date: 2026-11-16
- Context: 归并自 L-045 / L-047 / L-058 / L-063
- Observation: 带「每次」的 Requirement 只按正常回合核过，漏掉摘要调用与压缩后重试两条路径（L-047）；tasks 里写的失败码与规格不符（L-045）；扩充词表时，把旧词当反例的判据「还绿」不等于「还判那件事」（L-058）；两轴审查给出的改法会破坏 `FENCE_DENIED` / `CONTEXT_WINDOW_EXCEEDED` 的语义（L-063）
- Evidence: `docs/lessons-archive.md` 对应条目；`context-projection` 的「每次模型调用前记录 context/assembled」
- Next use: 全称量词要列全部调用路径；词表扩充逐处核对反例；审查建议先对照规格再决定接受或拒绝，拒绝要写理由
- Status: inbox

### L-078
- Promotion: ready（≥3 个不同日期）
- Seen: 3（不同日期：2026-10-17/23/25）
- Date: 2026-11-16
- Context: 归并自 L-019 / L-057（`add-platform-facts...` 那条 PowerShell 经验）
- Observation: 把 `async def test_...:` 整行（含结尾换行）当 `old_string` 会把下一行粘上来、语法当场坏掉；`git checkout -- <file>` 会连本轮未提交的改动一起回滚（L-019）；PowerShell 5.1 的 `Set-Content -Encoding utf8` 会写 BOM，`tasks.md` 首行因此带 BOM（L-057）
- Evidence: `docs/lessons-archive.md` 对应条目
- Next use: 编辑走编辑工具、不走 shell 往返；`old_string` 不带尾随换行；回滚前先看 `git status`
- Status: inbox

### L-079
- Promotion: ready（≥3 个不同日期）
- Seen: 4（不同日期：2026-10-23/25/11-13/11-18）
- Date: 2026-11-18
- Context: 归并自 L-072 / L-056（`add-platform-facts...` 的 mypy 窄化）；11-18 复发于「诊断覆盖率异常时反复手跑 report」
- Observation: `coverage report` 会消费并删除全部 `.coverage.*` partial，combine 之前跑过一次 report，下一轮 combine 的输入就少一批（L-072）；**为看单个文件而重跑 report 同样成立**——它按「当时存在的 partial」合并，前一次已把上一批吃掉，于是读数一路走低（11-18 实测：209 份 partial，一次 report 得 95%，随后归零）；mypy 的平台窄化只认 `sys.platform == "win32"` 这种字面量，抽成常量后窄化失效（L-056）
- Evidence: `docs/lessons-archive.md` 对应条目；2026-11-13 的四次整轮实测；2026-11-18 的 209 → 0 实测（`docs/CURRENT.md`）
- Next use: 覆盖率异常先数 partial 份数；平台判断保留字面量写法
- Status: inbox

### L-080
- Promotion: ready（≥3 个不同日期）
- Seen: 4（不同日期：2026-10-22/23/24/28）
- Date: 2026-11-16
- Context: 归并自 L-052 / L-054 / L-055（`fix-chat-screen-feedback` 的真实端点那条）/ L-064
- Observation: 真实端点暴露的缺陷，mock 全绿也抓不到，形状差在「段数与每段的输入数」（L-052）、「端口是否还开着与时序」（L-054）、「收尾缝隙只有几毫秒」（L-055）、「顺序对但延迟到整段结束才发」（L-064）
- Evidence: `docs/lessons-archive.md` 对应条目
- Next use: 真实端点场次至少覆盖「多段、每段多输入、连续操作」三种形状；流式判据要断言时间维度，不只顺序
- Status: inbox

### L-081
- Seen: 2（不同日期：2026-10-21/11-06）
- Date: 2026-11-16
- Context: 归并自 L-039 / L-071
- Observation: 实现里同时存在两条同义路径时，变异删掉一条、判据仍全绿，说明那条是死路径（L-071）；反过来，绿着写出来的守卫判据可以是有价值的，它的价值在变异轮兑现（L-039）
- Evidence: `docs/lessons-archive.md` 对应条目；M12 的取消桥
- Next use: 变异存活先判「是否等价机制/冗余路径」，再决定补判据还是删实现；绿着写的守卫要在提交信息里标注
- Status: inbox

### L-082
- Seen: 1（不同日期：2026-10-27）
- Date: 2026-11-16
- Context: 归并自 L-062
- Observation: `Future[bool]` 表达不了第三种结论 `UNAVAILABLE`；取消时把 pending future 置成 `False`，门只能回 `DENIED`，日志于是把「没人回答」写成「人拒绝了」
- Evidence: `docs/lessons-archive.md` L-062
- Next use: 语义有三态时不要用 bool 建模；取消/关停要能区分「拒绝」与「问不到人」
- Status: inbox

### L-083
- Seen: 1（2026-11-16）
- Date: 2026-11-16
- Context: 流程文档改动推送后，CI 连续三次红
- Observation: 本地只跑了 `ruff check` 与针对改动文件的 `ruff format <file>`，没跑全树的 `ruff format --diff`；CI 的 format 步骤抓到 5 个文件不合格。门禁是四道，少跑一道就等于把 CI 当成第一道
- Evidence: `gh run view 43802086482 --log-failed`；修复提交紧随其后
- Next use: 每次提交前按 AGENTS.md 的四道顺序跑，`ruff format --diff` 在最前
- Status: inbox

### L-084
- Seen: 1（2026-11-17）
- Date: 2026-11-17
- Context: M14c 两轴复核，子代理指出判据只断言实现内部字段
- Observation: 判据要断言「日志里的事件」或「外部可观察行为」，不要断言 `plan_exit`、私有 helper 返回值这类内部字段；否则改坏真实写入路径测试仍然全绿
- Evidence: 复核第二轮 5/6/7/8 条；已补 `_dispatch_batch` 日志级判据
- Next use: 新判据先问「删掉实现里哪一行，它会红」
- Status: inbox

### L-085
- Seen: 1（2026-11-18）
- Promotion: 已晋升（2026-11-18 → `AGENTS.md`「引用纪律」第 3 条，人裁本次直接进顶层）
- Date: 2026-11-18
- Context: M13 propose，`todos` 清空条件被改成「goal 段保留」，理由写进 design D8 与 spec；人问「是否违背 DSH」后查出 DSH 无条件清空
- Observation: 新增机制会**扩展既有名词的外延**（goal 轮次也是一种「段」/DSH 的 turn），既有规格里的全称量词（「`segment/start` 一律清空」）因此自动落到新机制上。写规格时我把注意力放在新机制本身，没重扫既有规则里以「每次 / 一律 / 无条件」开头的句子。更值得记的是：我读过 `tool-todo` 的 README（明写 `turn/start` 清空），仍判断错——丢的是「goal 轮次也是 turn」这一步推理，不是资料
- Evidence: `packages/todo/tool-todo/src/index.ts:120-131`（无条件 `turn/start → null`，无 goal 分支）；`docs/subsystems/goal.md:119`（"admitted user-message turn"）；本轮撤回提交 `2f62b8f`
- Next use: 写新机制前先列「会被它波及的既有全称量词」清单，逐条去**一手实现的赋值点**确认（那一行代码，不是文档摘要）；六问第 4 问的「会动现有规格」要按「旧规则的外延变了」来答，不只按「新增了事件/字段」来答
- Status: promoted

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）
- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- **Seen ≥3 个不同日期才晋升**（照 yetone 的做法）；每次只晋升一条，守一进一出。未达阈值的留在收件箱。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
