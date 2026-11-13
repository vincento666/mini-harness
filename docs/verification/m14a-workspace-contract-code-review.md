# m14a-workspace-contract 代码审查（两轴）

**日期**：2026-11-13。范围：`change/m14a-workspace-contract` 的 7 个提交。两轴：Standards 与 Spec。

## Standards

| # | 发现 | 处置 |
|---|---|---|
| C1 | `load_contracts(workspace, environ)` 收 environ 只为了取 home，`turn_loop` 又把它拼回 `{"MINIHNS_HOME": ...}`，调用方来回转换 | **已修**：改成收 `home: Path`；`contract_home(environ)` 只留给 `SessionEnv` 的默认工厂。16 条判据复跑全绿 |
| C2 | 显示路径恒为 `~/.mini-harness/AGENTS.md`；`MINIHNS_HOME` 指到别处时标签与实际不符 | 记账：显示层优先不泄漏绝对路径；`MINIHNS_HOME` 是测试/高级开关，触发条件是它成为常规用法时再按真实目录渲染 |
| C3 | `_catalog_shadowed` 被契约复用，名字偏窄 | 记账：改名会牵动目录的调用点，属无关改动；语义是「这条消息是否被压缩遮蔽」，两个调用点一致 |
| C4 | 每 turn `stat` + 读两份文件 | 记账：本地可忽略；网络盘上若 turn 延迟明显，改「按 mtime 探测、变了才读」 |
| C5 | `render_removed` 直接拼接路径、未转义 | 接受：路径只来自两个固定显示名（`~/.mini-harness/AGENTS.md`、`AGENTS.md`），不含仓库可控文本 |

## Spec

| # | 对照点 | 结论 |
|---|---|---|
| S1 | 注入位置 | 按人裁决：持久 `user/message`（`source: "workspace-instructions"`），不是受保护头部；与 DSH 一手资料一致 |
| S2 | 两个 Requirement、11 个 Scenario | 每条都有判据：两份/一份/零份、去重、超预算、转义、未变、替换、移除、回放、记忆分开、正文不进 `session/start` |
| S3 | 预算语义 | 单条消息 16 KiB；DSH 是每链一个 `maxBytes`。规模差异，记 `simplified` |
| S4 | symlink | 无判据；与 DSH 同风险的已知项，design 的 Risks 已记 |

## 结论

无阻塞项：一处 API 别扭已修（C1），四处记账（C2–C4、S3/S4 的已知项）。
