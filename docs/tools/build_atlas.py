#!/usr/bin/env python3
"""生成里程碑图表集：把 repowiki/assets/svg 下的图表内联成一份离线 HTML 图集。

用法：
    uv run python docs/tools/build_atlas.py --milestone M1 --out docs/milestones/M1-架构图集.html

图集顺序固定为「先宏观架构与流程，再关键机制，再工程方法」；
每张图带图名、图种（解释图 / UML 记号图）与一段读法。
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

from diagram_defs import FIGURES

SVG_DIR = REPO / "repowiki" / "assets" / "svg"

GROUP_ORDER = ["宏观", "机制", "工程"]

GROUP_INTRO = {
    "宏观": (
        "先看整体：系统边界、容器、分层、模块依赖、一次运行的生命周期，以及类图、契约图、实体关系图、"
        "状态机与组件装配图。这一组回答「系统是怎么设计的、组件之间是什么关系」。"
    ),
    "机制": (
        "再看关键部分：回合循环五步、追加与折叠、确定性、事件词表、工具派发、Provider 契约、退出码映射、"
        "围栏两轴与窗口预算公式。这一组回答「每个关键决策落在哪段代码上、失败怎么走」。"
    ),
    "工程": (
        "最后看方法：测试接缝、里程碑变更闭环、收尾门禁、变异测试、覆盖率现状、仓库结构、教训复利与路线图。"
        "这一组回答「怎么保证它真的是这样」。"
    ),
}

# 每张图一段读法：先说这张图钉住了什么，再说看图的正确顺序。
NOTES = {
    "m1-01-system-context": (
        "系统上下文：边界只有一处——进程边界。人给意图，CLI 把意图变成事件，事件写进日志，"
        "模型与工作区都在边界另一侧被调用。看图顺序：先找 CLI 这个边界，再看它两侧各有什么。"
    ),
    "m1-02-container-view": (
        "容器视图：CLI、回合循环内核、日志层、Provider 契约、工具注册与派发。"
        "注意 Provider 与工具都是「契约 + 一个实现」，不是「一堆实现」。"
    ),
    "m1-03-layered": (
        "分层与围栏：上层单向依赖下层，围栏（工作区边界与写前必读）是贯穿所有层的第二根轴，"
        "它不属于任何一层，所以画成竖条而不是某一层。"
    ),
    "m1-04-package-deps": (
        "模块依赖：11 个真实模块的 import 方向。反向依赖有两条——provider/contract.py 与 provider/mock.py 各引一次 "
        "events/fold.py 的 Message，这条账记在 ADR-0002 第 8 条而不是当场修——先记账、后偿还，是刻意的顺序。"
    ),
    "m1-05-lifecycle": (
        "一次 run 的生命周期：从参数校验到退出码。主干只有一条线，失败分支不改变主干结构，"
        "只是让主干提前结束。看这张图要顺着序号读，不要跳。"
    ),
    "m1-11-process-files": (
        "进程与文件：三个进程（CLI、内核、被派发的工具）与两块存储（日志文件、工作区）。"
        "外部只有一处——日志文件，它是唯一事实。"
    ),
    "m1-12-use-case": (
        "用例图：M1 只承诺四件事（跑一次会话、写日志、回放、按退出码表态）。"
        "文件工具与围栏属于 M2，图上标灰，避免把路线图当现状。"
    ),
    "m1-07-state-session": (
        "会话状态机：状态名与事件词表一一对应，状态迁移的证据就是日志里那几条事件。"
        "取消是一条虚线支路，它不新增状态，只改变停止原因。"
    ),
    "m1-08-er-log": (
        "实体关系：只有一张持久「表」——事件；会话是它的分组，回合与消息是折叠出来的投影。"
        "投影不落盘是刻意的：落盘就要面对两份事实谁是真的这个问题。"
    ),
    "m1-09-class-core": (
        "核心类图：EventLog 追加产生 EventRecord，fold 读入事件产出 Message 与 AssembledContext。"
        "头部指纹只覆盖受保护头部，不覆盖正文，这一点在字段注释里。"
    ),
    "m1-09b-class-contracts": (
        "契约类图：Provider 协议的一个方法有两种返回——AssistantTurn 或 ProviderFailure。"
        "「失败也是结果」不是口号，它写在返回类型里。"
    ),
    "m1-10-component-contract": (
        "组件与接口装配：实心圆是提供接口，半圆弧是需求接口。CLI 不认识 mock，只认识 Provider 协议，"
        "所以换实现不需要改 CLI。"
    ),
    "m1-06-seq-run": (
        "run 会话时序图：六条生命线、激活条、loop 组合框覆盖整个回合循环、alt 框区分「有工具调用」与「无工具调用」。"
        "这张图是回合循环五步的消息级版本，对着 m1-13 看。"
    ),
    "m1-13-turn-loop-steps": (
        "回合循环五步：记账、装配上下文、调模型、派发工具、判定停止。每一步都写日志，"
        "停止判定把原因写进 turn/end，退出码只是它的一次映射。"
    ),
    "m1-14-append-fold": (
        "追加与折叠：日志只追加，任何当前状态都是对同一份日志的一次折叠。"
        "左边是事实，右边是视图，视图每次重算、不落盘。"
    ),
    "m1-15-determinism": (
        "折叠确定性：同一事件前缀必然折叠出同一上下文。这条性质是 replay 的全部依据，"
        "也是「日志是唯一事实」能被验证的地方。"
    ),
    "m1-16-event-vocabulary": (
        "事件词表：M1 只有 9 种具体事件类型加一个 error/ 命名空间。词表小是设计决策——"
        "每加一种事件，折叠规则与测试都要跟着长。"
    ),
    "m1-18-tool-dispatch": (
        "工具派发：M1 没有任何工具实现，但派发路径已经把两种结果写死——UNKNOWN_TOOL 与 NOT_IMPLEMENTED。"
        "先把失败的形状定下来，实现再填进来。"
    ),
    "m1-19-seq-cancel": (
        "取消时序：SIGINT 只置标志，检查点在回合边界。取消写两条事件、映射到退出码 5，"
        "它是一次可回放的结果，不是一次异常。"
    ),
    "m1-20-seq-replay": (
        "replay 时序：回放不重新调模型，只重新折叠同一份事件。因为调的是同一个 fold()，"
        "结果一致不是承诺而是结构。"
    ),
    "m1-21-exit-code": (
        "停止判定与退出码：五种 stop_reason 映射到四个退出码，词表外一律兜底为 1。"
        "3 与 4 保留但不可达，给 M2 的围栏与 M3 的超时留着位置。"
    ),
    "m1-22-provider-contract": (
        "Provider 契约与剧本实现：一个方法、两种返回、一个实现。换模型只换实现，"
        "内核与测试都不动，这是 Provider 接缝存在的理由。"
    ),
    "m1-23-dataflow": (
        "数据流：唯一入口是事件写入，唯一出口是从日志折叠出的上下文。"
        "闭环只有一条路，所以任何状态争议都能回到日志。"
    ),
    "m1-24-fence-matrix": (
        "围栏两轴：工作区边界与写前必读互相不解锁，审批也不解锁边界。"
        "M1 的实际状态是「未实现」，图上直接写出来，不含糊。"
    ),
    "m1-34-budget-formula": (
        "窗口预算公式：公式是 M5 的设计决策，M1 代码里没有任何预算常量，护栏是 --max-turns。"
        "触发线目前有两份候选记录（0.85 × A 与 floor(min(W × 0.8, W − O − 65536))），图上并列写出并注明以 M5 的 change 为准——"
        "把「想做的」和「做了的」写在同一张图上，路线图就不会被当成现状。"
    ),
    "m1-25-seam-map": (
        "六个测试接缝：接缝是测试边界，不是实现边界。接缝③（文件工具契约）在 M1 是空的，"
        "空接缝也是接缝——它标明 M2 要在哪里长测试。"
    ),
    "m1-26-change-lifecycle": (
        "一个里程碑 = 一个 OpenSpec change：从开分支到归档，归档之后规格才是事实。"
        "代码是证据，规格是判据。"
    ),
    "m1-27-gate-pipeline": (
        "收尾门禁流水线：八道门按固定顺序跑，任何一门红，里程碑就没完。"
        "顺序是刻意的：先擦覆盖率数据，再跑测试，再合并数据，最后才看报告。"
    ),
    "m1-28-mutation": (
        "变异测试：M1 注入 17 个变异，16 个被杀，1 个存活。存活的那个换回一处设计改进——"
        "把退出码映射从 CLI 里抽成可测函数。门禁不只测代码，也测门禁本身。"
    ),
    "m1-29-timeline": (
        "M1 的推进顺序：先契约与日志，再循环与 CLI，最后门禁与收尾。"
        "顺序的理由是依赖方向，不是工作量。"
    ),
    "m1-30-repo-layout": (
        "仓库结构：代码、决策文档、自研工具、wiki 资产四块各自独立。"
        "文档与工具进版本库，和代码同一套门禁之外单独管理。"
    ),
    "m1-31-lessons-loop": (
        "教训与复利：看见 → 实验判据 → 写教训 → 改规矩 → 下一个里程碑验证。"
        "教训编号是索引，不是日志流水账。"
    ),
    "m1-32-roadmap": (
        "路线图 M1 到 M7：每个里程碑一个 change，完成判据是可观测口径，不是「做完了」。"
        "M2 起才碰文件与围栏，M4 才接真实模型。"
    ),
    "m1-33-coverage": (
        "覆盖率现状：457 语句、20 未覆盖、TOTAL 95.62%，底线 95%。"
        "条形长度按比例画，竖线是门禁线，不随里程碑变化。"
    ),
}

CSS = """
:root{--bg:#0a1628;--panel:#0d1f3c;--line:#1f3a5f;--ink:#caf0f8;--sub:#90e0ef;--muted:#48cae4;
--core:#00b4d8;--data:#48cae4;--ok:#06d6a0;--warn:#f77f00;
--mono:'Courier New','Lucida Console','Microsoft YaHei','SimHei',monospace;
--sans:'Helvetica Neue',Helvetica,'PingFang SC','Microsoft YaHei',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.8}
.wrap{max-width:1240px;margin:0 auto;padding:28px 24px 80px}
header.top{border:1px solid var(--line);border-radius:10px;padding:22px 26px;background:var(--panel)}
h1{margin:0 0 6px;font-size:28px;letter-spacing:.01em}
.tagline{color:var(--sub);font-family:var(--mono);font-size:13px}
.toc{margin:22px 0 8px;border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:18px 22px}
.toc h2{margin:0 0 10px;font-size:15px;color:var(--core);font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase}
.toc ol{margin:0 0 14px;padding-left:22px;columns:2;column-gap:28px}
.toc li{font-size:13.5px;margin:3px 0;break-inside:avoid}
.toc a{color:var(--sub);text-decoration:none}
.toc a:hover{color:var(--core)}
section.group{margin:34px 0 10px}
section.group>h2{font-size:20px;color:var(--core);border-bottom:1px solid var(--line);padding-bottom:8px;margin:0 0 6px}
section.group>p{color:var(--sub);margin:6px 0 0}
.fig{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:18px 20px;margin:22px 0}
.fig h3{margin:0 0 2px;font-size:18px}
.fig .kind{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.fig .sub{color:var(--sub);font-size:14px;margin:4px 0 12px}
.fig-svg svg{width:100%;height:auto;display:block;border:1px solid #0a1a30;border-radius:6px;background:#08111f}
.fig .read{margin-top:12px;font-size:14px;color:var(--ink)}
.fig .read b{color:var(--core)}
.legend{border:1px dashed var(--line);border-radius:10px;padding:16px 20px;background:#0c1c34;font-size:13.5px;color:var(--sub)}
.legend code{font-family:var(--mono);background:#08111f;border:1px solid var(--line);border-radius:3px;padding:1px 5px}
footer{margin-top:36px;color:var(--muted);font-family:var(--mono);font-size:12px}
a.anchor{color:inherit;text-decoration:none}
"""


def load_svg(fig_id: str) -> str | None:
    path = SVG_DIR / f"{fig_id}.svg"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("<?xml"):
        text = text.split("?>", 1)[1]
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成里程碑离线图表集")
    parser.add_argument("--milestone", default="M1")
    parser.add_argument("--out", default="docs/milestones/M1-架构图集.html")
    args = parser.parse_args()

    prefix = f"{args.milestone.lower()}-"
    figures = [fig for fig in FIGURES if fig["id"].startswith(prefix)]
    if not figures:
        print(f"没有 {prefix} 前缀的图表")
        return 1

    by_group: dict[str, list[dict[str, object]]] = {name: [] for name in GROUP_ORDER}
    for fig in figures:
        by_group.setdefault(str(fig.get("group", "机制")), []).append(fig)

    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = [
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{args.milestone} 架构图集 · mini-harness</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        '<div class="wrap">\n'
        '<header class="top">'
        f"<h1>{args.milestone} 架构图集</h1>"
        '<div class="tagline">mini-harness · 一个 MVP 个人实验版 agent harness · '
        f"{len(figures)} 张图 · 生成于 {now}</div>"
        "<p>图集分三段：先宏观架构与流程（系统怎么设计、组件什么关系），"
        "再关键机制（每个决策落在哪段代码、失败怎么走），最后工程方法（怎么保证它真的是这样）。"
        "解释性图用同一套蓝图风格；时序图、类图、实体关系图、状态机、组件图按 UML 与 IE 鸦爪记号绘制。</p>"
        "</header>\n"
    ]

    toc: list[str] = ['<div class="toc">']
    for name in GROUP_ORDER:
        items = by_group.get(name) or []
        if not items:
            continue
        toc.append(f"<h2>{name}（{len(items)} 张）</h2><ol>")
        for fig in items:
            toc.append(f'<li><a href="#{fig["id"]}">{fig["title"]}</a></li>')
        toc.append("</ol>")
    toc.append("</div>\n")
    parts.extend(toc)

    parts.append(
        '<div class="legend"><b>看图约定</b>：实线箭头是控制流，虚线是外部或可选路径，'
        "细虚线框是容器或组合框。UML 记号：实心三角 = 泛化，空心三角 = 实现，"
        "实心菱形 = 组合，空心菱形 = 聚合，开箭头 = 依赖或导航，"
        "鸦爪 = 多端，单线 = 一端，实心圆 = 初始伪状态，同心圆 = 终止伪状态，"
        "实心圆加竖线 = 提供接口，半圆弧 = 需求接口。配色：<code>#00b4d8</code> 主干、"
        "<code>#06d6a0</code> 已实现、<code>#f77f00</code> 计划或未实现、"
        "<code>#48cae4</code> 数据与投影。</div>\n"
    )

    for name in GROUP_ORDER:
        items = by_group.get(name) or []
        if not items:
            continue
        parts.append(
            f'<section class="group"><h2>{name}</h2><p>{GROUP_INTRO[name]}</p></section>\n'
        )
        for fig in items:
            svg = load_svg(str(fig["id"]))
            if svg is None:
                parts.append(
                    f'<div class="fig"><h3>{fig["title"]}</h3><p>缺 SVG 源：{fig["id"]}</p></div>\n'
                )
                continue
            kind = "UML 记号图" if fig.get("kind") == "uml" else "解释图"
            note = NOTES.get(str(fig["id"]), "")
            parts.append(
                f'<div class="fig" id="{fig["id"]}">'
                f'<div class="kind">{kind} · {fig["id"]}</div>'
                f'<h3><a class="anchor" href="#{fig["id"]}">{fig["title"]}</a></h3>'
                f'<div class="sub">{fig.get("subtitle", "")}</div>'
                f'<div class="fig-svg">{svg}</div>'
                + (f'<div class="read"><b>读法</b>　{note}</div>' if note else "")
                + "</div>\n"
            )

    parts.append(
        f"<footer>图集由 docs/tools/build_atlas.py 生成 · SVG 源在 repowiki/assets/svg · {now}</footer>\n"
    )
    parts.append("</div>\n</body>\n</html>\n")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"{out} · {len(figures)} 张图 · {out.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
