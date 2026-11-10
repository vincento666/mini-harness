# subagent-preset UAT

**状态**：**agent 代跑**（用户明确指示，2026-11-10）。这是对 ADR-0025「人坐在终端前」那半的流程偏离：四场全部是 non-tty 的 CLI 运行，观察由 agent 记录；合并前由用户确认接受这笔偏离。

## 跑前准备

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
rm -rf /tmp/preset-uat && mkdir -p /tmp/preset-uat
printf '目标：把这条写进 note.md\n' > /tmp/preset-uat/inbox.md
printf '第二份材料\n' > /tmp/preset-uat/second.md

cat > /tmp/preset-uat/mini.config.toml <<'TOML'
[subagent]
preset = "reader"
allowed_presets = ["reader", "writer"]

[subagent.presets.reader]
tools = ["read", "glob"]

[subagent.presets.writer]
tools = ["read", "write", "edit"]
TOML
```

## 场次

### S1 · 模型在部署白的名单里选 preset

```bash
uv run minihns run --provider deepseek --workspace /tmp/preset-uat --session-dir /tmp/preset-uat/s1 \
  -p "用 subagent 读 inbox.md 并总结；如果只需要读，就用 reader" --yes
```

看：子 `session/start` 的 `preset` 是 `reader` 或 `writer`（模型只能选这两个），`tools` 与该 preset 一致；子日志里没有第三个 preset。

### S2 · 不配 preset：继承父组合

把 `mini.config.toml` 挪走再跑一次（或换一个没有配置的工作区）：

```bash
mv /tmp/preset-uat/mini.config.toml /tmp/preset-uat/mini.config.toml.bak
uv run minihns run --provider deepseek --workspace /tmp/preset-uat --session-dir /tmp/preset-uat/s2 \
  -p "派一个 subagent 读 second.md 并总结" --yes
```

看：子 `session/start` 没有 `preset`，`tools` 与父的整张表一致；派发照常。

### S3 · 配错 preset：装配期就失败

```bash
cat > /tmp/preset-uat/mini.config.toml <<'TOML'
[subagent]
preset = "ghost"
TOML
uv run minihns run --provider deepseek --workspace /tmp/preset-uat --session-dir /tmp/preset-uat/s3 \
  -p "派一个 subagent 读 inbox.md" --yes
```

看：退出码 2，stderr 含 `INVALID_ARGUMENT` 与 `ghost`，`/tmp/preset-uat/s3` 下**没有**日志文件。

### S4 · 能力 ≠ 授权

恢复配置，把子会话的沙箱压到 read-only，让 `writer` 去写：

```bash
svn=$(cat /tmp/preset-uat/mini.config.toml.bak 2>/dev/null || true)
cp /tmp/preset-uat/mini.config.toml.bak /tmp/preset-uat/mini.config.toml 2>/dev/null
uv run minihns run --provider deepseek --workspace /tmp/preset-uat --session-dir /tmp/preset-uat/s4 \
  -p "用 writer preset 派一个 subagent 把 inbox.md 写进 note.md" --sandbox read-only
```

看：子会话的工具表里有 `write`（preset 给的），但写调用是 `DENIED_BY_FENCE`（档位拒绝）——工具面与授权是两件事。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | 白名单选 preset | 只能是 reader/writer | 父七件套；子 `preset=reader`、`tools=read/glob`（模型选了 reader） | 通过 | |
| S2 | 无 preset | 继承父表、派发照常 | 子没有 `preset` 字段、`tools` 与父的七件套一致；派发成功 | 通过 | |
| S3 | 配错 preset | 退出码 2、无日志 | 退出码 **2**，`INVALID_ARGUMENT: [subagent] preset ghost 不在 presets 里`，`s3/` 目录不存在 | 通过 | |
| S4 | read-only 下的写 | `DENIED_BY_FENCE` | 父第一次带 `sandbox=workspace-write` 被 `TOOL_ARGS_INVALID`（不能比父宽）；第二次不带 sandbox → 子 `preset=writer`、`tools=read/write/edit`，它的 `write` 是 `DENIED_BY_FENCE`（`SANDBOX_DENIES_WRITE`），`note.md` 没被创建 | 通过 | 模型先试了放宽档位、被拒后才收窄——正常，但读日志的人要知道这条 |

**至少一条「用起来别扭」**：S4 里模型先尝试给子会话放宽沙箱（`workspace-write`），被 `TOOL_ARGS_INVALID` 拒了才改回不带 sandbox；「只能收窄」这条约束是运行时才知道的，工具描述里没有明说。

**结论**：通过（S1–S4；agent 代跑，用户确认接受流程偏离）。
