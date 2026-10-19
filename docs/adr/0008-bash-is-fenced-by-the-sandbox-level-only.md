# bash 只受围栏的档位轴约束，边界轴对它恒真

围栏的边界轴判的是「这个路径在工作区内吗」，而 `bash` 没有目标路径：`ToolArgs.target_path()` 返回 `None`。当时 `dispatch_tool_call` 里的 `raw_path=args.target_path() or ""` 让 `path_key(workspace, "")` 塌成工作区根本身（实测 `Path("")` → `WindowsPath(".")`）。裁决：**接受这个形状**——`bash` 只受档位轴约束（`read-only` 拒；`workspace-write` 与 `danger-full-access` 放行），子进程 cwd 固定为工作区根，命令文本里的路径不解析。

**实现现状（2026-10-19 更正）**：`or ""` 那一半已经不存在——`tools/dispatch.py` 直接把 `None` 传进 `judge_fence`，`judge_fence` 有显式的 `raw_path is None` 分支（无路径可判 → 档位轴已放行，`ask` 档位下落到 approval 段）。裁决本身不变，变的只是实现形状。

Considered options：解析命令文本里的路径、让 bash 也走边界轴——否，那要写一个 shell 解析器，且两个平台的 shell 语义不同；bash 在任何档位都一律需要 approval——否，tty 不可用时 bash 就永远不可用，而 CI 与脚本化正是 tty 不可用的场景。

代价：不变量 E 的「工作区边界」对 bash 只约束 cwd，不约束命令实际写到哪儿——`workspace-write` 与 `danger-full-access` 对 bash **没有任何可观察差别**。这条区分要写进 fences 主规格的措辞（现在那几条按工具名只点名 `read`/`write`/`edit`/`glob`/`grep`），不能留给读者推断。超时之后怎么终止进程树是另一个裁决：fences 主规格字面禁止 job object，`docs/roadmap.md` 却预告它，到 M3 里再立一份。
