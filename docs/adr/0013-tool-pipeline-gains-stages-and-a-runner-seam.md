---
status: accepted
partially_supersedes: ADR-0003
---

# 工具管线加段到与 DSH 同形；「怎么跑一条命令」立成一条缝

ADR-0003 第 3 条把管线定成三段、工具体不接信号，代价是超时与取消只能从外面掀（走查第三节）。裁决：**以 DSH 为真理转向**——管线加段：校验 → 围栏与审批 → **单调守卫（判定一旦作出不可翻案）** → 执行（换入派生信号，结束时恢复调用方信号）→ **执行后观察与替换** → **内容收尾（截断与归一化由工具定义自己负责）**。同时把「怎么跑一条命令」从工具体里抽成一条缝：现有 win32 与 posix 两个实现是这条缝上的两个 adapter，OS 级拦截将来是**第三个 adapter**，不动工具体。排在 M10。

Considered options：保持三段（否：工具体无法协作式停止，长命令只能被杀，与 ADR-0011 的协作式取消直接矛盾）；现在就写 OS adapter（否：M15 之前没有判据环境，本机也没有可用的 Linux）。

Consequences：ADR-0002 第 18 条（抽 `_Batch`）与第 23 条（`denial_code` 换成词表类型）在 M10 一并收；`FenceCode` 加「沙箱不可用」，runner 不可用即拒绝、fail-closed；ADR-0003 其余各条（不做 OS 级强制、approval 不提权、两轴不预设、EOF → `APPROVAL_UNAVAILABLE`、CAS 只比读到的窗口）仍然有效。
