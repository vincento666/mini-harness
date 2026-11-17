# AI coding 流程控制：从「靠自觉」到「靠边界」（M14c 后定稿）

**定位**：流程机制说明，不是规格。现行规则在 `docs/process/devops-loop.md` §0；本文只解释三层控制如何分工、为什么这样分、哪里仍然管不住。

**一句话**：能被脚本判定的，交给 git hook 与 CI；需要判断的，留给契约、两轴复核与人；两者之间用「停点」连接。

## 1. 三层控制的形状

| 层 | 触发 | 执行者 | 管什么 | 绕得过吗 |
|---|---|---|---|---|
| git hooks | commit / push | git | 格式、风格、类型 | `--no-verify` |
| harness hooks | 会话与工具调用 | agent 产品 | 启动装钩子、拦截主规格与 ADR 直写、拦截高危删除 | 换产品即失效 |
| CI | push / PR | 远端 runner | 全量测试、覆盖率、双平台 | 绕不过 |
| 脚本 | 人/agent 调用 | shell | 建 change、归档前校验、全量门禁 | 不调用就不跑 |

三层不是互相替代，而是**触发点不同**：git hook 在「改动进入版本库」时拦，harness hook 在「模型动手之前」拦，CI 在「代码离开本机」时兜底。

```
改动 ─▶ git commit ─▶ pre-commit（秒级：格式 / 风格 / 类型）
                    └▶ harness PreToolUse（写前：主规格 / ADR / 高危删除）
改动 ─▶ git push ───▶ CI（全量测试 + 覆盖率 + 双平台）
流程 ─▶ scripts ────▶ gates / new-change / check-change / bootstrap
```

## 2. 五个停点

默认动作是继续，只有五类情形弹窗：对齐（范围与分叉）、警告（不可逆/安全/成本）、复核（blocker 或两轴结论）、决策（merge、UAT 归属、改 AGENTS/ADR/流程）、事故（证据不足、连续失败、计划外需求）。

目标验证类弹窗必须带三样：一手证据、因果链、反方视角；只给结论的弹窗不算对齐。

## 3. 一个 change 的控制点

```
契约 ─▶ propose ─▶ apply（切片）─▶ 四道门禁 ─▶ 两轴复核
                                              │
                                              ▼
        merge ◀─ 归档 ◀─ UAT ◀─ 变异 ◀────────┘
```

1. **验证契约**：先写目标、可观察行为、判据、坏法清单、不验什么；人审后才 propose；
2. **切片实现**：按 tasks 顺序，判据先行；一个红绿循环一次提交；
3. **四道门禁**：格式、风格、类型、测试与覆盖率；`scripts/gates.sh` 一条命令跑完；
4. **两轴复核**：Standards（仓库约定）与 Spec（需求覆盖）分别由子代理审，结论要人接受；
5. **变异测试**：改坏实现，确认判据会红；存活变异补判据；
6. **关键 UAT**：人坐终端拿它办一件真事；agent 代跑需明确授权；
7. **归档与合并**：归档在 change 分支上做，merge 与推 `main` 是人闸。

## 4. 硬控制与软控制的边界

**能硬控制的**：格式、类型、测试、覆盖率、规格结构、change 产物齐全、分支名、危险删除、主规格直写。

**不能硬控制的**：契约是否覆盖真正的坏法、两轴结论是否成立、UAT 是否真的办成一件事、设计分叉的代价取舍。

把后者脚本化，只会把错误判断固化得更快；所以流程用「停点」而不是「更多检查」来处理它们。

## 5. 已知限制

- **git hook 要装**：`core.hooksPath` 不随克隆走，靠 `scripts/bootstrap.sh` 补；
- **harness hook 绑产品**：`.claude/settings.json` 只对读它的产品生效，换 harness 可能失效；
- **`--no-verify` 可绕**：最终仍要靠 CI；
- **技能不随仓库走**：`~/.workbuddy/skills` 是用户级，流程文档只能「建议调用」，不能当门禁；
- **Windows 差异**：hook 走 Git Bash，脚本按 POSIX 写，未用 bash 4+ 特性。

## 6. 一次实测

M14c 收尾：732 passed / 6 skipped、覆盖率 95%、变异 3/3、CI 双平台 success、关键 UAT 两场 PASS；两轴复核第一轮抓到 1 个 blocker（子会话继承工具表可绕过计划拦截）。这些数字是流程有效性的证据，不是流程本身。

## 7. 出处

- `docs/process/devops-loop.md`：§0 停点、§0.3 契约、§0.6 推进模式；
- `docs/process/devops-loop-rationale.md`：规则背后的推理账；
- `AGENTS.md`：门禁、三半完成判据、七个 seam；
- `.githooks/pre-commit`、`scripts/pre-commit.sh`、`scripts/gates.sh`、`scripts/bootstrap.sh`；
- `.claude/settings.json`、`scripts/harness_hooks.py`；
- `.github/workflows/`：CI 双平台。
