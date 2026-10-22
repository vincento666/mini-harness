---
status: accepted
---

# 模型相关功能的完成判据含一次真实端点实测

M4 之后每个里程碑的完成判据里都没有真实端点那一行：M4 写着「两个端点各一次真实 smoke 跑通」，M5（正是窗口预算与压缩那个里程碑）、M6（chat REPL）、M7（serve 事件流）的完成判据全是 mock 桩形状。成因是两条既有决定叠在一起——handoff 决策 6 把真实调用放在「测试默认用 mock、真实只在手动 smoke 里跑、密钥缺失就跳过」的位置，ADR-0005 又把它安放进「人手验收，不进 CI、不替代上面任何一条判据」的位置——合起来的效果是 **mock 桩绿等于里程碑完成**。本 ADR 裁定：**任何依赖模型回复形状的功能，完成判据里必须有一次真实端点实测（不进 CI，但不跑完这个里程碑不算完成）；CI 层的判据要用真实端点实际回过的产物做 fixture，不用手编的桩数据去猜形状。**

为什么现在才补：真实端点上的失败形状只有真实端点会给。这次实测到的是 400 加 `{"error": {"type": "invalid_request_error", "message": "prompt (222233 tokens) leaves no room to answer in the context (196608)"}}`——没有 `error.code`，而 provider 主规格与既有判据只认 `error.code == "context_length_exceeded"`。同样形状的东西 mock 造不出来。此前真实那一半不是没跑：M5 量到估算偏小 2.24 倍、M6 场 2 两段都溢出、M7 的 C 场小窗口溢出客户端挤不进去——三条观察都记进了 `docs/verification/`，**没有一条回灌成判据**。

Considered options：CI 里带密钥跑真实端点（否：CI 不持 API key 是既定选型，且真实端点抖动会让门禁不可信）；照旧只把真实那一半写进 manual（否：那正是这次漏洞的形状）；把真实会话整份搬进 fixture（否：太大且带真实内容，只裁字段形状与必要的短句）。

Consequences：决策 6 的「真实调用要隔离」仍然成立——**隔离的是 CI，不是验收**；`tests/fixtures/` 成为真实产物的存放处，每条写明来源 session id；「真实端点跑一次」从此是 `tasks.md` 里的复选框，不再是「等人跑」的那一半；后续里程碑的完成判据要照这条写。
