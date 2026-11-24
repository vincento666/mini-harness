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

### L-086
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: M13 复核 D.3：`rounds_started` 既写成快照字段，又能从日志的 goal 消息数出来；初稿把这条记成 `simplified`，人问「mini 是不是没有等价语义」
- Observation: 同一事实的两份写法里，只要**后一份能由日志重建**，语义就是对齐的，差的是表示（冗余/索引）；记成 `simplified` 会让读者把「冗余」读成「偏离」。记账要分两栏：`aligned（语义）/ simplified（表示）`
- Evidence: `docs/verification/m13-goal-rounds-dsh-review.md` D.3 与 `replay` 的 `goal_round_defect`
- Next use: 每个对齐项先问「丢掉这个字段/机制，语义能不能从日志或工作区重建」；能，就写语义对齐 + 表示差异，并写出冗余的收益与代价
- Status: inbox

### L-087
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: `docs/reference/plan-and-todo.md` 4.1 原写「DSH 返回 `{todos, counts}` 并有 native renderer」；本轮读 `todo_index.ts` 才发现模型可见的是 `render` 出来的计数文本，整表只在入参与事件里
- Observation: 跨项目对齐的转述会带着上一轮的误解一起传下去；文档写得越像结论，后人越不会回源。写「X 返回 Y」之前先看 Y 怎么到模型/用户手里，不能停在类型定义
- Evidence: `packages/todo/tool-todo/src/index.ts:159-182`（`output.schema` 之后是 `render` 只打 counts）；本轮更正 4.1
- Next use: 引用外部行为时标源文件行号；类型与「模型看到的内容」分开写
- Status: inbox

### L-088
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: 新增 `get_todos` 时只写了「段首清空」，没写「跨轮读到什么」；人追问「跨轮重交是不是只多一次工具调用」后才补出 D.7.1/D.7.2
- Observation: 读回类工具的价值与局限都在**作用域**上。只说「段首为空」不够，设计时就要回答「同段 / 跨段 / 被遮蔽」三种情形各返回什么、模型该怎么用
- Evidence: 复核文档 D.7.1（三种情形）与 D.7.2（goal 轮同样是 turn，跨轮两边都不保表）
- Next use: 新增读工具先画一张「作用域 × 状态」表，至少测一条边界（段首为空）
- Status: inbox

### L-089
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: `/goal` 最初先 `execute_command` 再写 `command/run`，回放时 `goal/updated` 早于「谁让它变的」
- Observation: 命令面的事件顺序是因果，不是装饰。已知命令应先落 `command/run` 再执行；「未知命令」用白名单（`RESERVED`）预检，不靠执行返回 `None` 来判——否则要么因果倒置，要么留一条不可达分支
- Evidence: `cli/main.py::_run_chat_command`、`session/host.py::run_command`；`command/run` 先于 `/goal` 的 `goal/updated`
- Next use: 命令 handler 有副作用时，先写 `command/run`；命令白名单与 handler 表同源，别让 handler 的返回值兼任「存在性检查」
- Status: inbox

### L-090
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: M13 的 UAT 场次 1：模型在自动轮次里调 `ask_user`，返回 `QUESTION_UNAVAILABLE`，驱动仍开了下一轮——问题没人答，额度照烧
- Observation: 自动循环的「还能不能继续」判据里，**未决的人工输入**必须是一条停止理由。工具返回「问不到人」不是普通错误：它表示这一轮在等一个只有人能给的东西；把它当成普通工具结果继续跑，等于用轮次额度买同一个问题
- Evidence: `loop/goal_driver.py` 的 `awaiting_input`；`docs/verification/m13-goal-rounds-dsh-review.md` D.8.1
- Next use: 任何自动续跑／重试循环，先列「哪些结果意味着必须等人」，再写「否则继续」；`ask_user`、审批、凭证缺失都在这一类
- Status: inbox

### L-091
- Seen: 1（2026-11-19）
- Date: 2026-11-19
- Context: 同一场 UAT：`--workspace .tmp/uat/m13` 是相对路径，`write` 回执写 `.tmp/uat/m13/notes.md`，而 `bash` 的 cwd 是工作区根，模型 `tail` 不到自己刚写的文件
- Observation: 工具回执里的路径必须是**模型能直接拿去用**的那条。同一个工作区在两处用两种写法（相对启动目录 vs 相对工作区），模型只会得到「写了却找不到」的假矛盾，浪费一整轮自查
- Evidence: `tools/file_tools.py` 的 `_relative_to` 回执；`session/assembly.py` 的 `abspath` 绝对化
- Next use: 新增工具回执先问「这条路径从 bash 的 cwd 看得到吗」；工作区在装配时绝对化，展示用工作区相对路径
- Status: inbox

### L-092
- Seen: 1（2026-11-20）
- Date: 2026-11-20
- Context: 讨论「mini 还没有段中人类消息队列」时，实际查代码发现 host 早就有 `submit_message` 的深度 1 队列；缺的是 host 的轮次驱动，不是队列本身
- Observation: 把「某个能力没有」当成结论之前先按**入口**查一遍：同一个语义可能已经在 host 存在、只在 chat 缺；也可能三处入口各有一份实现。功能缺口与入口分叉是两类问题，修法不同
- Evidence: `session/host.py::submit_message`（队列）与 `_run_segment`（原来只跑一段）；2026-11-20 抽 `settle_segment` 后三处共用
- Next use: 听到「mini 没有 X」时，先列 `run` / `chat` / `host` / `subagent` 四个入口，逐个查；先判分叉再判缺失
- Status: inbox

### L-093
- Seen: 1（2026-11-20）
- Date: 2026-11-20
- Context: 目标「完成了却不停」——模型说「没有新内容可写」，没调 `update_goal complete`，驱动照常开下一轮
- Observation: 完成是模型声明的事实，harness 验证不了；能观测的反面证据只有「这一轮什么也没做」。自动循环的停止判据应包含一条**零动作熔断**，而不是替模型宣布完成或阻塞
- Evidence: `loop/goal_driver.py` 的 `stalled`；`segment/end.tool_calls`；design D14
- Next use: 设计自动续跑时，先问「完成信号由谁给、给不出时最小可观测证据是什么」；不要用「没有新内容」这类自然语言当判据
- Status: inbox

### L-094
- Seen: 1（2026-11-20）
- Date: 2026-11-20
- Context: 原 D11 把「问不到人」处理成 `paused` + 解除武装，人回答后还要 `/goal resume`；DSH 的一手行为是答案以用户消息回来，目标继续
- Observation: 「暂停」和「等人」是两种状态：暂停是人做的决定，等人是流程中的一个等待点。把等人写成暂停，会把系统的等待成本转嫁给用户（多敲一次命令），也会让日志把「等着」记成「人叫停」
- Evidence: DSH `ask_user` 的 `{pending: true}` 与 `answer_to_pending_question`；design D15；host 里回答是 human turn
- Next use: 任何「等外部输入」的状态，先问它是否应该改变持久相位；默认保持原相位 + 交回控制权，只有人的显式动作才改相位
- Status: inbox

### L-095
- Seen: 1（2026-11-20）
- Date: 2026-11-20
- Context: 计划把 `segment → turn`、`turn → step` 全量改名；两遍直接替换会互相覆盖（第一遍产生的 `turn` 会被第二遍改成 `step`）
- Observation: 交换型改名必须用占位符分步落位；日志改名则应把兼容放在**读取侧的上迁**，不重写旧文件——原始证据保留，内部只有一种形状
- Evidence: `openspec/changes/align-turn-step-naming/design.md` D1/D2；`events/record.py` 的 `migrate_schema` 是现成落点
- Next use: 遇到 A→B、B→C 的链式改名，先写占位符顺序再动手；schema 变更优先读取时上迁，写入只写新形状
- Status: inbox

### L-096
- Seen: 1（2026-11-20）
- Date: 2026-11-20
- Context: 为「完成了却不停」加了「goal 轮次零工具调用即停」的熔断，阈值 1；同日经过「默认关（对齐 DSH）」与「默认开、阈值 2」两次修正才定下来
- Observation: 自动循环的停止判据有两个参数，不能只拍一个：**开关**（默认开还是关）与**阈值**（几轮才算）。阈值 1 会把「想清楚再答」的研究型轮次误杀；默认关又会放过真正的死循环。可行的默认是「开 + 连续两轮」：一轮留给人味，两轮判死循环，`0` 留作关闭
- Evidence: `GoalPolicy.stall_rounds = 2`；Claude Code 的 `/goal` stall detection 是「连续几轮不用工具」且保留 goal；Codex 的 token 预算命中只注入 wrap-up 不硬杀
- Next use: 给自动循环加停止判据时，把「开关」与「阈值」分开定；默认取中间值（2–3），不要取 1，也不要取「永不」
- Status: inbox

### L-097
- Seen: 1（2026-11-24）
- Date: 2026-11-24
- Context: `align-turn-step-naming` 的 3.5 把 `SYSTEM_PROMPT` 里的「在回合里」改成「每一步」，金样本 `replay` 立刻在 seq=3 报 `REPLAY_MISMATCH`
- Observation: 改名要按文本的去向分类：人可见文案（stderr、`--help`、HTTP detail）改了只影响观感；模型可见文本（系统提示词、工具 description、工具结果）改了就是行为变化——它进 `context/assembled`，逐点比对立刻红。金样本在这里不是「老日志兼容」的摆设，是「改动有没有越界」的探针
- Evidence: 改 `SYSTEM_PROMPT` 后 `minihns replay v1-goal-tools` exit 1（`error/replay seq=3`），回退后 exit 0（2026-11-24 两次实跑）；design D5 的「改词只到人可见文案」
- Next use: 任何改名或改措辞的 change，先给每条文本标去向（日志 / 上下文 / 终端 / HTTP）；进上下文的文本不在改名范围，要动就单独立项并重跑真实端点
- Status: inbox

### L-098
- Seen: 1（2026-11-24）
- Date: 2026-11-24
- Context: `align-turn-step-naming` 的变异测试里，把 host 重启扫描的 `turn/start` 改成 `step/start`，全量 45 条 host 测试全绿
- Observation: 同一个语义有两份实现时（活句柄自增 vs 从日志重建），只给其中一份写判据，另一份的错会静默通过。变异测试是发现这种「影子实现」最便宜的手段——它不看你写了多少测试，只看你改坏的那一处有没有人管
- Evidence: `_begin_turn` 的自增有 `test_the_session_view_counts_turns_not_steps`；`_scan_session_index` 的重建当时没有任何判据；补 `test_a_restarted_list_rebuilds_turns_from_turn_starts` 后变异被杀死（`docs/verification/align-turn-step-naming-mutation.md` 第 3 条）
- Next use: 写「从持久事实重建视图」的功能时，给「运行中」与「重启后」两条路径各写一条判据；收尾变异优先挑第二条路径改
- Status: inbox

### L-099
- Seen: 1（2026-11-24）
- Date: 2026-11-24
- Context: `align-turn-step-naming` 的真实端点场次 2，`minihns usage` 输出 `{"turns": [{turn_id t1}, {turn_id t2}]}`，而这份会话只跑了**一轮**两步
- Observation: 改名的漏网不是「旧字符串没换干净」那种显眼错，而是**单位错位**：数据是步的，键还是轮的，于是输出自相矛盾。mock 全绿抓不到它，因为判据只断言数值、没断言「键与数据是同一层」；只有把真实产物当数据读一遍才会撞上。凡输出里同时出现「层级名 + 列表」，就该有一条形状判据钉住两者的层数（一轮两步 → 列表两项且键叫 `step_id`）
- Evidence: `cli/main.py` 的 usage payload 原为 `turns[]` + `turn_id`；`host.py` 的 `model/delta` 帧原把步 id 装进 `turn_id`。修后判据 `test_the_usage_command_prints_steps_and_total`（顶层键集合）、`test_the_event_stream_mixes_durable_and_delta_frames`（帧键集合 + 与同一步 `model/response` 对齐）；把帧键改回 `turn_id` 变异即红
- Next use: 任何「改名 / 迁移」收尾，先跑一次真实端点把每个输出**当外部数据读**，再检查每个 JSON 的键与值的层级是否一致；这比通读一遍代码便宜
- Status: inbox

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）
- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- **Seen ≥3 个不同日期才晋升**（照 yetone 的做法）；每次只晋升一条，守一进一出。未达阈值的留在收件箱。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
