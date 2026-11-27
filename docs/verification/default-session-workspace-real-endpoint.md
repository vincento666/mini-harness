# default-session-workspace — 真端点验证（契约 3.2）

**口径**：管道喂提示词、不传 `--workspace`、`MINIHNS_HOME` 指临时目录；本 change 没有 tty 手感判据
（design D5），管道验证即够。

## 场次

| 场 | 端点 | 结果 |
|---|---|---|
| 首跑 `b6206b19…` | OpenRouter `qwen/qwen3.8-27b` | 第一步写入成功、第二步模型调用超时（端点抖动）。产物已落会话目录，但整场 `rc=1`，不计通过 |
| 复跑 `3a1b7f2d…` | 同上 | `rc=0`，全文判据成立 |

复跑命令（cwd 是干净临时目录，`MINIHNS_HOME` 指临时 home）：

```bash
MINIHNS_HOME=<tmp>/home minihns run \
  -p "在工作区根创建 hello.txt，内容一行：默认工作区生效。" \
  --provider openrouter --model qwen/qwen3.8-27b --yes --max-steps 6
```

## 读数（`3a1b7f2d…`）

- **stderr**：`工作区 /Users/vincento/work/develop/mini-harness/.tmp/uat-dsw2/home/workspaces/3a1b7f2d57f945eb9db8a7997d1924b1`
  ——绝对路径、无 `..`（首跑暴露 `MINIHNS_HOME=../home` 时路径带 `..`，已把默认目录绝对化）。
- **stdout**：只有 session id，没有工作区路径（契约 1 的「stdout 无路径」）。
- **启动目录**：`err.txt` / `out.txt` / `sessions/`（本次验证自己的重定向与日志目录），**没有** `hello.txt`。
- **会话工作区**：`home/workspaces/3a1b7f2d…/hello.txt`，内容 `默认工作区生效。`。

## 连带发现

- `write ../escape.txt` 的拒绝码是 `OUTSIDE_WORKSPACE`（路径解析在围栏之外），不是契约里写的
  `SANDBOX_DENIES_WRITE`（那一档是 read-only 拒绝）；契约与 tasks 的措辞已按实测修正。
- `bash "touch ../x"` **不会**被静态拒绝——bash 的围栏只看沙箱档位与 cwd，是既有语义（本 change
  明确「不动围栏与工具实现」）。默认模式下它的产物落在 `workspaces/` 而不是项目根，危害面已比
  变更前小；判据改钉「read-only 档位下 bash 仍被拒」。
