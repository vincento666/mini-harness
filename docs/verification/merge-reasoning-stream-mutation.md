# merge-reasoning-stream — 变异记录

**日期**：2026-11-26。**口径**：按 `verification-contract.md` 的「变异（至少两条）」逐条注入、跑判据测试、看是否被杀死，然后 `git checkout --` 回滚。每次只改一处，判据测试用 `--basetemp` 新目录。

回滚后复核：`git status` 只剩文档改动，`tests/test_cli_chat.py tests/test_cli_host.py -k "reasoning or thinking"` → **2 passed**。

---

## M1：把 `reasoning/delta` 也写进日志

**注入**（`src/mini_harness/session/host.py::publish_reasoning`）：先广播 ephemeral 帧，再 `self.log.append("reasoning/delta", dict(frame))`，模拟「思考增量顺手落盘」。

**跑**：`uv run pytest tests/test_cli_host.py -k reasoning`

**结果**：**被杀死**（1 failed）。

```
tests/test_cli_host.py:818
>   assert "reasoning/delta" not in log.read_text(encoding="utf-8")
E   assert 'reasoning/delta' not in '{"schema_ve...alls": 0}}\n'
E     'reasoning/delta' is contained here:
E       d_type": "reasoning/delta", "step_id": "t1", "index": 0, "text": "想", "kind": "reasoning"}}
```

副作用值得记一笔：`EventLog.append` 对不认识的类型名会降级写 `error/internal` + `unrecognized_type`，所以这条变异在日志里以「错误事件」形态出现，判据仍按「日志里出现 reasoning delta」抓到——正是判据 3/4 要防的那件事。

## M2：把思考增量接进正文 sink

**注入**（`src/mini_harness/cli/main.py`）：`on_reasoning=renderer.reasoning` 改成 `lambda step_id, _index, text: renderer.text(step_id, text)`，即让思考走正文那条路。

第一次注入用了 `on_reasoning=renderer.text`（签名 `(step_id, text)` 与 `(step_id, index, text)` 不匹配），测试以 `TypeError` 崩掉。**崩溃不等于判据生效**，所以重做了一版签名对齐的变异——变异必须死在断言上，不能死在类型错误上。

**跑**：`uv run pytest tests/test_cli_chat.py -k "reasoning or thinking"`

**结果**：**被杀死**（1 failed，死在该判据自己的断言上）。

```
>   assert "[thinking] 先想" in result.stderr
E   AssertionError: assert '[thinking] 先想' in '会话 4d64d8e354cb4c4aa327c012e8066ad1\n[answer] '
E   stdout='> 先想\n> '
```

stdout 里出现 `先想`、stderr 没有 `[thinking]`——正文与思考混流的形状正是判据 3 要拒的。

## 结论

- 两条变异都被现有测试杀死，且 M2 是被**语义断言**杀死、不是被异常杀死。
- 这两条恰好也解释了 1.8 真端点发现的缺陷为什么长期看不见：mock 与单测都按 `reasoning_content` 造帧、都只断言「两条流分开」，没有一条测试质疑「换一种 wire 名还认不认」。补的那条场景（`specs/provider` delta + `test_openrouter_stream_reasoning_key_is_also_understood`）就是为这个缺口立的。
- 变异只覆盖「思考是否被落盘 / 是否混进正文」两处；blocks 顺序、interrupted 与 attempt 的互斥不在变异范围（由 1.8 真端点与既有 `test_reasoning_contract.py` 覆盖）。
