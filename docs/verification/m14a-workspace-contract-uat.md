# m14a-workspace-contract UAT

**状态**：agent 代跑（用户指示，2026-11-14）。四场。环境 `--provider deepseek`（`deepseek-chat`），工作区 `.tmp/uat/m14a-s1`–`s4`，用户级目录用 `MINIHNS_HOME=.tmp/uat/m14a-home`。

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | 项目根放一份 `AGENTS.md`，写一条可观察的约定（例如「回复开头先写 `收到`」），跑一次 `minihns run` | 模型按约定回复；日志里有 `source: "workspace-instructions"` 的消息 |
| S2 | 再在 `~/.mini-harness/AGENTS.md` 放一条不同的约定，跑一次 | 消息里先出现用户全局段、后出现项目段；两条约定都生效 |
| S3 | 把项目 `AGENTS.md` 写到超过 16 KiB | 消息不超过上限，含 `Workspace instruction budget:` 通知并指名被截断的路径；模型仍能读到前段 |
| S4 | 两个文件都不放，跑一次 | 日志里没有 `workspace-instructions` 消息，模型正常回答 |

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | 契约消息 1 条、364 字节，`scopes` 为 `[(AGENTS.md, 24, False)]`；回复首句「收到，工作目录名是 `m14a-s1`」 | 通过 | 无 |
| S2 | 契约消息 1 条、463 字节，`scopes` 顺序为 `~/.mini-harness/AGENTS.md` → `AGENTS.md`；回复是「[G] … [P]」，两条约定都生效 | 通过 | 显示路径恒为 `~/.mini-harness/AGENTS.md`，而本场实际用的是 `MINIHNS_HOME` 指到别处——标签与真实位置不符（code-review C2 已记账） |
| S3 | 源文件 112817 字节；契约消息恰好 **16384** 字节，`scopes` 为 `[(AGENTS.md, 7097, True)]`，通知是 `Workspace instruction budget: truncated AGENTS.md to 16013 bytes.`；模型读到了前 172 条 | 通过 | 通知里的 16013 是**正文**字节数，容易读成整条消息的大小；措辞可以更明确（例如 `body truncated to …`） |
| S4 | 契约消息 0 条；回复「你好。有什么我可以帮你的吗？」 | 通过 | 无 |

**结论**：通过。

## 附：人跑时可留意

- S3 的截断点落在半句话上（第 173 条被切断），模型仍能理解前段；如果真实项目的约定把关键规则放在文件末尾，截断会把它们丢掉——这是预算方案本身的取舍，不是缺陷。
- S2 的用户级路径显示与实际 `MINIHNS_HOME` 不一致，人跑时如果设置了自定义 home 会看到同样的标签。
