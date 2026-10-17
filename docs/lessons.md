# Loop Lessons

教训的**收件箱与活跃区**。机制照 `universal-work-loop` 的 Learning Gate：每次里程碑收尾或 `code-review` 之后扫一遍证据，把可复用的信号写进这里；**AGENTS.md 只接收晋升后的压缩规则，且每次晋升必须同时删掉或压缩 AGENTS.md 里的一条旧内容（一进一出）**。

`Status`：`inbox`（待消化）| `active`（每次进入本项目工作都读）| `promoted`（已写进 AGENTS.md）| `rejected`。

## Active Lessons

现在只有这五条会常驻；其余留在收件箱。

1. **词表类规格必须配「每个值都可达」的测试**。M1 的 `turn/end.stop_reason` 从成功路径倒推，漏了 `TOOL_CALLS`；`ABORTED` 写了却不可达，直到实现才暴露。
2. **写新 Requirement 时成对检查它跟已有 Requirement 是否互斥**。「每个非零退出都有 `error/*` 事件」与「重放不追加事件」各自正确、合起来不可满足，最后靠 ADR-0001 开一个显式例外收场。
3. **测试写下即绿就是危险信号**。M1 有约 24 个切片没有红。判据不是测试数量，是变异测试：15 个变异 14 个被杀，存活的 `P` 证明当时没有任何 CLI 测试守 `LOG_WRITE_FAILED`。
4. **接手前先核实时状态，不要相信上一段的叙事**。M1 期间 `git checkout --` 误回滚了未提交的改动，导致一次 `ImportError`。跑 `git status --short` 与 `git log --oneline -3` 再动手。
5. **文本文件绝不经 PowerShell 往返**。`Set-Content` 毁 UTF-8（真毁过一次测试文件），`Out-File -Encoding utf8` 带 BOM，`>` 产生 UTF-16LE。改文件用编辑工具；要读命令的 stderr 就 `2> 文件` 再读。

## Candidate Inbox

条目格式：

```text
Date / Context / Observation / Evidence / Next use / Promotion candidate / Status
```

### L-001
- Date: 2026-10-15
- Context: M1 `tasks.md` 1.2「验证工具链可用」
- Observation: 把「0 个测试时 pytest 退出码 0」写成了任务，pytest 实际返回 5，任务不可能成立
- Evidence: 规格返工提交 `73069a6` 前后；tasks 1.2 措辞改写
- Next use: 写「验证类」任务时先跑一次真实命令拿退出码，再写判据
- Promotion candidate: AGENTS.md（已并入 Active 1 的同类）
- Status: inbox

### L-002
- Date: 2026-10-15
- Context: 事件词表与停止原因的规格
- Observation: 从「成功跑完」倒推词表，漏掉「回合结束但会话继续」这一整类状态
- Evidence: 新增第五个值 `TOOL_CALLS`（提交 `73069a6`）
- Next use: M2 写工具事件词表时先穷举「回合结束 / 会话结束 / 失败」三态
- Promotion candidate: solution document（M2 design.md）
- Status: inbox

### L-003
- Date: 2026-10-15
- Context: cli 规格的两条 Requirement
- Observation: 各自正确、合起来不可满足；`openspec validate --strict` 只查结构，查不出这种矛盾
- Evidence: ADR-0001 里 `error/replay` 只走 stderr 的显式例外
- Next use: 每写一条新 Requirement，列出它可能撞上哪条已有的，写进 design.md
- Promotion candidate: AGENTS.md（Active 2）
- Status: active

### L-004
- Date: 2026-10-16
- Context: 变异测试第 10、11 轮
- Observation: 变异必须改变**可观察行为**，否则是 dud mutant（`elif not x:` → `elif False:` 语义等价，41 个测试全绿）；重命名内部函数导致 5 个 collection error，属于无效变异
- Evidence: `docs/verification/m1-mutation.md` 的方法论注记
- Next use: 变异前先想「哪条断言会因此变红」，想不出就别做
- Promotion candidate: AGENTS.md 流程节（变异段）
- Status: promoted

### L-005
- Date: 2026-10-16
- Context: 第 11 轮变异 `P`
- Observation: 删掉 `_run` 的内核失败映射分支后仍 exit 1（KeyError 兜底），59 个测试全绿 —— 存活原因是**没有 CLI 黑盒测试覆盖 `LOG_WRITE_FAILED`**，而规格里它有两条 Scenario
- Evidence: `docs/verification/m1-mutation.md`；补测试提交 `1a7c912`（抽出 `exit_code_for`）
- Next use: 规格里每条失败路径 Scenario 都要能指到一条测试；指不到就是缺口
- Promotion candidate: verifier/eval
- Status: inbox

### L-006
- Date: 2026-10-16
- Context: 手动黑盒跑 M1 CLI
- Observation: 两个缺陷 `code-review` 两个轴都没发现：带 UTF-8 BOM 的 fixture 读不了（`FIXTURE_INVALID: Unexpected UTF-8 BOM`）、日志不可写时的退出码路径无覆盖
- Evidence: 修提交 `6ad6256`；黑盒九发的结果记录
- Next use: 里程碑收尾除了自动门禁，手动跑一遍真实命令（含畸形输入）
- Promotion candidate: AGENTS.md 流程节
- Status: inbox

### L-007
- Date: 2026-10-16
- Context: 子进程覆盖率记账
- Observation: seam ⑥ 的 CLI 测试跑在子进程里，默认不计覆盖率；要记账必须 `coverage run -p` + `COVERAGE_FILE` 指回仓库根 + 显式 `--rcfile`（测试的 `cwd` 是 tmp_path）
- Evidence: 提交 `0a9745e`；`cli/main.py` 36% → 96%
- Next use: 任何「黑盒 + 记账」需求直接照这套
- Promotion candidate: solution document
- Status: inbox

### L-008
- Date: 2026-10-16
- Context: 覆盖率门禁本身
- Observation: `coverage combine` 只认文件内容不认新旧，上一轮残留的 partial 会被混进这一轮，且**看不出来**（连跑两轮不 erase，第二轮仍报 96%）
- Evidence: 提交 `f0e063b`（AGENTS.md 加 `coverage erase` 为第 0 步）
- Next use: 任何「合并式」记账都先清场再测
- Promotion candidate: AGENTS.md（已并入覆盖率段）
- Status: active

### L-009
- Date: 2026-10-16
- Context: `uv add --dev ruff pytest-cov`
- Observation: uv 缓存（C:）与仓库（S:）跨文件系统，hardlink 建不了 → 退化成复制，一条命令跑了约 17 分钟
- Evidence: 实现会话的回报；缓存随后搬到 `S:\AppData\uv\cache`
- Next use: 跨盘项目设 `UV_LINK_MODE=copy` 或让缓存与仓库同盘
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: inbox

### L-010
- Date: 2026-10-16
- Context: 提交粒度
- Observation: 「一个红绿循环一次提交」在实现中被打包成 4 个多任务提交，最狠的一个打包 14 个任务，出问题不好二分
- Evidence: `8320f1e`（tasks 7.1–9.4）
- Next use: 规则已收紧（AGENTS.md 流程节）：一个提交最多覆盖同一 seam 相邻 3 个 task
- Promotion candidate: AGENTS.md（已写）
- Status: promoted

### L-011
- Date: 2026-10-16
- Context: 规格与实现的偏差记录方式
- Observation: 简化不写 ADR 就会被后人当缺陷修掉；ADR 只在「难回退 + 无上下文会困惑 + 真实取舍」三条同时成立时才写
- Evidence: `docs/adr/0001`、`docs/adr/0002`
- Next use: 沿用 `domain-modeling` 的 ADR-FORMAT
- Promotion candidate: 已在 AGENTS.md 引用纪律
- Status: promoted

### L-012
- Date: 2026-10-17
- Context: 把 uv 缓存从 C: 搬到 S:
- Observation: 同盘时 uv 用 hardlink 把缓存文件接进 venv，**字节是共享的**；搬走缓存只回收「没有被任何 venv 引用」的那部分。实测搬走 5.338 GB 只让 C: 多出 0.4 GB，因为其中约 4.91 GB 与三个 uv 建的 venv 共享（`.unsloth` 4.11 / hermes-agent 0.61 / uv tools 0.19）
- Evidence: `fsutil hardlink list …\cryptography\hazmat\bindings\_rust.pyd` 列出三个 venv 路径；robocopy 日志 `5.338 g copied / 0 failed`；三个 `pyvenv.cfg` 都写着 `uv = 0.12.5`
- Next use: 估算「搬缓存能腾出多少」之前先数谁在共享它；跨盘搬缓存会让总占用上升
- Promotion candidate: 无需进 AGENTS.md（环境事实，非项目规则）
- Status: inbox

## 收敛纪律（防止本文件与 AGENTS.md 线性膨胀）

- 每个里程碑收尾扫一次，**允许输出 `NO-PROMOTION`**（没有可复用信号就不写条目）。
- 收件箱条目超过 **15 条**必须先消化再收新的：合并同类、把已被代码或规格自证的条目删掉。
- 晋升进 AGENTS.md 的唯一形态是**一句话规则**；细节留在本文件或 `docs/verification/`。
- 每次晋升同时删/压 AGENTS.md 的一条旧内容（一进一出）。
- 每个里程碑归档后跑一次 `agents-md-slim`；AGENTS.md 超过 **150 行**时跑一次 `agents-md-refactor` 做拆分。
