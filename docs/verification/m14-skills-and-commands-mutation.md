# M14 变异测试

**日期**：2026-11-11。每个变异改源码、跑指定判据、记录红，再 `git checkout` 还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 发现结果不排序 | `discover_skills` 直接返回 dict 插入序（rank 序），不按名字排序 | `test_four_roots_are_discovered_in_rank_order` | 红：插入序是 zeta/mid/alpha，期望 alpha/mid/zeta |
| M2 | 正文不截断 | `read_skill_body` 直接 `return body`，去掉 32 KiB 上限与截断提示 | `test_body_is_capped` | 红：正文没有「已截断」也没有变短 |
| M3 | persona 不进头部 | `protected_header` 删掉 `if persona: parts.append(persona)` | `test_the_child_header_carries_the_preset_persona` | 红：子头部没有那段人设 |

**基线**：还原后 `tests/test_skills.py` + `tests/test_subagent.py` 36 passed（全量 612 passed）。

**关于 M1 的前置修正**：原判据里三个技能的名字碰巧与 rank 同序（project/shared/user），「不排序」也能过；先把名字改成 zeta/mid/alpha，让名字序与 rank 序相反，M1 才有杀死力。

## Learning Gate

**NO-PROMOTION**：`docs/lessons.md` 的收件箱已 71 条（纪律要求超过 15 条先消化，本轮不动它）。本轮的两条可复用信号已固化在别处：

- **覆盖率 partial 会跨轮污染**：中断过的覆盖率跑在仓库根留下旧 `.coverage.*`，`coverage erase` 不一定清干净；混进下一轮会得到假低值（本轮先看到 82%，`rm -f .coverage .coverage*` 重跑才是 95%）。这条写在这里，等收件箱消化时再决定是否晋升。
- **命令是 UI 动作，不是消息**：DSH 的命令不创建模型消息、不开段；mini 照此实现。写进 ADR-0038 与 DSH parity review。
