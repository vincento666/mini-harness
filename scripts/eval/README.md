# E1 评测与观测（支撑轨）

**定位**：配套能力，不是核心运行时。这里量的是「更快、更省、更稳」，不是「功能对不对」——功能对不对由七个 seam 的判据与「mock / 真实 / UAT」三半回答（ADR-0034）。**不进四道门禁、不作为归档条件、不进 CI。**

## 跑什么

三个最小任务（先能跑，再谈扩充）：

1. **单文件修完并跑测试**：工作区里一个 `calc.py` 带两个 TODO，让它改完并跑 `pytest`；判「测试通过」与「改了几个文件」。
2. **跨文件回答**：给三个文档，问一个需要综合的问题；判「答案里是否含关键事实」与「读了几次、多少 token」。
3. **小重构**：两个文件各改一处 + 一次 `bash` 跑测试；判「测试通过」与「工具调用数」。

任务定义放在 `tasks/`（每个任务一个目录：`prompt.md` + `workspace/` + `check.py`）。**不把任务写进 `tests/`**：它们不是门禁。

## 量什么

| 维度 | 指标 |
|---|---|
| 效果 | 任务成功率、期望文件是否改到、测试是否通过 |
| 效率 | 回合数、工具调用数、wall-clock、最大并发数、首 token 延迟（H2 后） |
| 上下文 | 输入/输出 token、峰值上下文、压缩次数、剪枝/截断省下的字节 |
| 安全 | 审批次数、拒绝次数、越界尝试是否被围栏拦下 |
| 一致性 | `minihns replay <id>` 是否退出 0、装配点是否逐点相等 |

## 两种模式

- **mock**：确定性、日常可跑；用 fixture provider，不看真实模型的质量。
- **真实**：按需、人跑、不进 CI；密钥只从环境变量读，报告里不写密钥。

## 产物

`docs/verification/eval/<date>/report.md` + `report.json`，模板：

```markdown
# Eval <date>
- commit:
- provider: mock | <name>
- task: <id>
- success: yes/no
- turns / tool_calls:
- input_tokens / output_tokens / peak_context:
- compaction_count / bytes_saved_by_pruning:
- wall_clock_s / max_concurrency:
- approvals / denials:
- replay: ok / mismatch
- 备注（别扭在哪、哪条指标不可比）:
```

## 不做什么

公开榜单、CI 门禁、按模型排名、自动调参、把评测结果当验收判据。
