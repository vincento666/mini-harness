# mini-harness

个人实验版 agent harness 的 MVP。headless CLI 优先，架构决策照抄 DeepSeek Harness（DSH）的核心思想，用 OpenSpec 做规格（SDD）、用 TDD 做实现。

**当前状态**：**M0 已完成** —— 工作区已建、DSH 参考材料已拷入、OpenSpec 1.14.2 已装并 `init --tools dsh`（技能在 `.dsh/skills/`）、首次提交 `0b27bdb`。**M1 尚未开始，一行实现代码都没有。**

已装的 OpenSpec 工作流（core profile，delivery=skills）：`openspec-propose`、`openspec-explore`、`openspec-apply-change`、`openspec-update-change`、`openspec-sync-specs`、`openspec-archive-change`。`openspec-verify-change` **未装**——它要 `openspec config profile` 交互勾选；在它可用之前，规格与实现的一致性用 `code-review` 技能（Standards / Spec 两轴）代劳。

---

## 先读这三样，再动手

1. **`docs/handoff-2026-10-15.md`** —— 已锁定的 **38 条编号决策 + 6 条不变量**，这就是规格输入。**不要重新 grill**，除非实现过程中出现新的设计分叉。
2. **`docs/dsh-reference/DSH运行时设计说明.html`** —— 入门三节（什么是 harness / 通用十格流水线 / 上下文压缩）+ 8 章 + 8 张算法卡，每节配图折叠内嵌。
3. **`docs/dsh-reference/DSH运行时设计图集.html`** —— 75 张图，锚点形如 `#fig-<图名>`；要照某个机制实现时，先把那张图的锚点读出来。

---

## 命令

```bash
uv sync                       # 装依赖（含 dev）
uv run pytest                 # 全部测试
uv run pytest -k <表达式>     # 单个红绿循环
uv run mypy --strict src      # 类型检查
uv run minihns run -p "任务" --workspace <dir> --events jsonl
uv run minihns replay <session-id>
uv run minihns chat           # M6 之后
uv run minihns serve --http   # M7 之后
```

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

分支纪律：每个 change 一个分支 `change/<id>`，完成后合入 `main` 并做 archive 提交。提交粒度 = 一个红绿循环一次。

**测试只写在下面六个 seam 上**（tdd 技能要求先约定再写，不许水平切片）：
① 回合循环 ② 工具注册与管线 ③ 文件工具契约 ④ 日志追加与折叠 ⑤ Provider 接口 ⑥ CLI 黑盒（subprocess 跑真实命令）

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
