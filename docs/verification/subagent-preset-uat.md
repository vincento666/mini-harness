# subagent-preset UAT

**状态**：等人跑（agent 不代跑 tty 场次，ADR-0025）。

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
| S1 | 白名单选 preset | 只能是 reader/writer | | | |
| S2 | 无 preset | 继承父表、派发照常 | | | |
| S3 | 配错 preset | 退出码 2、无日志 | | | |
| S4 | read-only 下的写 | `DENIED_BY_FENCE` | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过：
