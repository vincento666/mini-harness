# fix-case-insensitive-path-keys — UAT 场次手册

**状态**：**已过**（2026-11-27 人跑，场次 1）。mock 与真实端点两半已完成（见 `tasks.md` 3.1、3.3 与 `fix-case-insensitive-path-keys-mutation.md`），UAT 这一半由人执行；**这张表没填完不得归档**（ADR-0025）。

## 跑之前的准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
```

前置知识：修复后 `path_key` 把已存在的前缀规范成磁盘上的写法——macOS APFS（默认大小写不敏感）上，`notes/plan.md` 与 `Notes/Plan.MD` 是同一个键；写法大小写不同不再误判 `WRITE_WITHOUT_READ`。新文件名不存在，保持调用给的写法（「新文件不需要先读」不变）。

## 场次表

| # | 怎么跑 | 看什么 | 通过判据 | 状态 |
|---|---|---|---|---|
| 1 | 在真终端用 `minihns chat`（加 `--workspace .tmp/uat-cas1 --provider openrouter --proxy http://127.0.0.1:7897 --max-steps 5 --yes`），提示词见下 | 读一种写法、改另一种写法能否办成一件真事 | 模型只用一种写法读过、换写法 edit 成功 `OK`，产物内容正确；**没有** `WRITE_WITHOUT_READ` / `STALE_EDIT` 误报；`[tool]` 行为与产物用 `ls`/`cat` 交叉核对 | **已过** |

**场次 1 提示词**（先把下面的准备命令跑掉，再造出文件）：

```bash
mkdir -p .tmp/uat-cas1/Reports && printf '季度收入三万。\n季度支出两万。\n结余一万。\n' > .tmp/uat-cas1/Reports/Summary.md
```

```
读取 reports/summary.md，把第一行替换成「季度收入三万五。」，然后告诉我文件现在完整的内容。
```

（工作区里文件是 `Reports/Summary.md`，提示词故意用小写 `reports/summary.md`——修复前这条会判 `WRITE_WITHOUT_READ`。）

## 观察记录（2026-11-27，人跑，会话 `0e4b8ede2e5440bbad8244d32fae2d45`）

- 模型只用小写 `reports/summary.md` 一种写法：`read` → `OK`（读到 `Reports/Summary.md` 三行内容），`edit` → `OK: 替换了 1 处`——修复前这条会判 `WRITE_WITHOUT_READ`。
- 全日志 0 命中 `WRITE_WITHOUT_READ` / `STALE_EDIT`（逐条 grep 核对）。
- 回答内容正确（第一行「季度收入三万五。」）；`cat` 交叉核对一致。
- 附加观察：`glob **/*` 返回磁盘真实写法 `Reports/Summary.md`——同一键（大小写不敏感）上规范到磁盘写法的旁证。
