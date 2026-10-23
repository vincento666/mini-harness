# `fix-post-compaction-budget-reading` 的 UAT 验收手册（人跑）

**第五道门禁的执行手册**（ADR-0025）。不是跑判据：是你坐在终端前拿 `minihns chat` 读大文件、接着问问题，然后把「遮蔽之后读数到底降没降、溢出之后还问得动吗」填回来。**这张表没填完，本 change 不得归档、不得合入 `main`。**

**前置**：这两场要在 `fix-small-window-compaction-dead-zone` 落地之后跑——它把溢出判据换成压力预算（`W − O`），下面用的窗口参数照它才成立。准备（真实工作区 `$WS`、注入密钥变量、选模型层 `$EP`）照 `docs/verification/m5-m6-m7-uat.md` 的「准备」一节。

> **这一场必须用真实端点**：这条缺陷只在真实回报（`usage.input_tokens`）在场时出现。mock 桩的 `usage` 全 0，读数只剩估算，遮蔽当然砍得动——用 mock 跑这两场等于没跑。
> **退出码怎么读**：`cmd /c "uv run minihns … & echo %ERRORLEVEL%"`，别在 Ctrl-C 之后读 `$LASTEXITCODE`。

---

## W1 · 「降至」到底降没降

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-d\sessions @EP --window 70000 --reserve 100 --max-turns 8 --sandbox workspace-write --yes
```

让它读真实工作区里**最大的那份文本文件**，读完问一句总结，再读第二份，再问一句。

| 要观察的 | 你看到的 |
|---|---|
| `[遮蔽] 折掉 seq … 至 …：tokens <前> 降至 <后>`：后面那个数比前面小吗 | |
| 差值大概是多少（摘要的大小？还是别的） | |
| 同一次会话里第二、第三条遮蔽反馈的两个数，趋势是往下还是往上 | |
| 遮蔽之后还报不报 `[段] CONTEXT_WINDOW_EXCEEDED` | |
| 遮蔽之后问「刚才读了哪个文件」，答得上来吗 | |

---

## W2 · 溢出之后还问得动吗（对照上一轮的「每问必溢出」）

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-d\sessions2 @EP --window 70000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

连读三份大文件，每读一份都接着问一句；一直问到出现 `[段] CONTEXT_WINDOW_EXCEEDED`，然后**继续问三句**。

| 要观察的 | 你看到的 |
|---|---|
| 第一次溢出之后，接着问的那三句各是什么反应（有回复 / 又溢出） | |
| 三句里溢出了几次（上一轮是三句全溢出） | |
| 溢出之后 `[遮蔽]` 那一行还出现吗、两个数什么关系 | |
| 会话最后是怎么结束的（自己结束？你 Ctrl-C？）、退出码 | |
| 用这次的 session id 跑 `uv run minihns replay <id> --session-dir .tmp\uat-d\sessions2`：退出码、有没有 `REPLAY_MISMATCH` | |
| 换成更大的窗口（`--window 128000 --reserve 8192`）重跑一遍，结论一样吗 | |

---

## 跑完之后

把观察填进本文件，然后说一句「这个 change 的 UAT 跑完了」。我会按填回来的东西判 UAT 那一半；不符合的项照 ADR-0025 立成新的修复 change。

**还有一件想问你的**（这个 change 故意不做的那一半）：如果当时屏幕上有一行提前告诉你「当前表层快满了，要先压缩」，你会希望它长什么样、在什么时候出现？这一句是「精细的 token 预算管理」那条前瞻决策的输入，不是本 change 的判据。
