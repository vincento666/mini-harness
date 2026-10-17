#!/usr/bin/env python3
"""UML / ER / 状态机 SVG 生成器：按软件行业主流画法输出 Blueprint 风格的图。

支持的记号：
  sequence   生命线（虚线）、激活条、同步/返回/自消息、alt 与 loop 组合框
  class      三栏类框、关联、泛化（空心三角）、实现（虚线空心三角）、依赖（虚线开箭头）、
             组合（实心菱形）、聚合（空心菱形）、多重性与角色名
  er         实体框（名称栏 + 属性栏，PK/FK 标记）、鸦爪连线（1 与 N 端）、可选圈
  state      圆角状态框、初始实心圆、终止靶心、转移标签 guard / effect
  component  组件框 + 提供接口圆（lollipop）+ 需求接口半圆 + 装配连线
  card       公式卡片（设计决策留档，不当成已实现）

输出带 data-graph-role / data-node-id / data-edge-id / data-owner 属性，
可直接过 fireworks-tech-graph 的 check（几何、越界、碰撞、箭头记号）。
"""

from __future__ import annotations

import html
from typing import Any

BG = "#0a1628"
GRID = "#112240"
PANEL = "#0d1f3c"
STROKE = "#00b4d8"
INK = "#caf0f8"
SUB = "#90e0ef"
MUTED = "#48cae4"
ACCENT = "#00b4d8"
WARN = "#f77f00"
OK = "#06d6a0"
FONT = "'Courier New','Lucida Console','Microsoft YaHei','SimHei',monospace"

FLOW_COLORS = {
    "control": "#00b4d8",
    "read": "#48cae4",
    "write": "#90e0ef",
    "data": "#caf0f8",
    "async": "#f77f00",
    "feedback": "#06d6a0",
    "neutral": "#48cae4",
}


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def tw(text: str, size: float) -> float:
    """粗略文本宽度：CJK 按全宽，拉丁按 0.6 倍。"""
    total = 0.0
    for ch in str(text):
        total += size if ord(ch) > 0x2E80 else size * 0.6
    return total


def _defs() -> str:
    return f"""  <defs>
    <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="{GRID}" stroke-width="0.5" opacity="0.6"/>
    </pattern>
    <marker id="uArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{ACCENT}"/>
    </marker>
    <marker id="uArrowOpen" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="{ACCENT}" stroke-width="1.4"/>
    </marker>
    <marker id="uTriHollow" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="12" markerHeight="12" orient="auto-start-reverse">
      <path d="M 0 14 L 14 7 L 0 0 z" fill="{BG}" stroke="{ACCENT}" stroke-width="1.2"/>
    </marker>
    <marker id="uTriFilled" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="12" markerHeight="12" orient="auto-start-reverse">
      <path d="M 0 14 L 14 7 L 0 0 z" fill="{ACCENT}"/>
    </marker>
    <marker id="uDiamondFilled" viewBox="0 0 16 12" refX="15" refY="6" markerWidth="14" markerHeight="12" orient="auto-start-reverse">
      <path d="M 0 6 L 8 0 L 16 6 L 8 12 z" fill="{ACCENT}"/>
    </marker>
    <marker id="uDiamondHollow" viewBox="0 0 16 12" refX="15" refY="6" markerWidth="14" markerHeight="12" orient="auto-start-reverse">
      <path d="M 0 6 L 8 0 L 16 6 L 8 12 z" fill="{BG}" stroke="{ACCENT}" stroke-width="1.2"/>
    </marker>
    <marker id="uCrowFoot" viewBox="0 0 16 16" refX="15" refY="8" markerWidth="14" markerHeight="14" orient="auto-start-reverse">
      <path d="M 15 8 L 1 1 M 15 8 L 1 15 M 15 8 L 1 8" fill="none" stroke="{ACCENT}" stroke-width="1.3"/>
    </marker>
    <marker id="uCrowOne" viewBox="0 0 12 16" refX="11" refY="8" markerWidth="10" markerHeight="12" orient="auto-start-reverse">
      <path d="M 11 1 L 11 15 M 5 8 L 11 8" fill="none" stroke="{ACCENT}" stroke-width="1.3"/>
    </marker>
    <marker id="uCrowZeroOne" viewBox="0 0 16 16" refX="15" refY="8" markerWidth="14" markerHeight="14" orient="auto-start-reverse">
      <path d="M 4 8 m -4 0 a 4 4 0 1 0 8 0 a 4 4 0 1 0 -8 0 M 15 8 L 8 2 M 15 8 L 8 14" fill="none" stroke="{ACCENT}" stroke-width="1.3"/>
    </marker>
  </defs>"""


def _skeleton(fig: dict[str, Any]) -> tuple[list[str], int, int]:
    w = int(fig.get("width", 1200))
    h = int(fig.get("height", 760))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="{FONT}" data-generator="mini-harness-uml" data-schema-version="1" '
        f'data-style-id="3" data-visual-theme="Blueprint" data-diagram-type="{esc(fig["uml_kind"])}" '
        f'data-quality-profile="standard" data-graph-bounds="0,0,{w},{h}">',
        _defs(),
        f'  <rect x="0" y="0" width="{w}" height="{h}" fill="{BG}" data-graph-role="background"/>',
        f'  <rect x="0" y="0" width="{w}" height="{h}" fill="url(#grid)" opacity="0.55" data-graph-role="decoration"/>',
        f'  <text x="40" y="46" font-size="17" fill="{INK}" letter-spacing="0.05em">{esc(fig["title"])}</text>',
        f'  <text x="40" y="68" font-size="11" fill="{SUB}">{esc(fig.get("subtitle", ""))}</text>',
        f'  <text x="{w - 40}" y="46" font-size="10" fill="{MUTED}" text-anchor="end" letter-spacing="0.08em">'
        f"{esc(fig.get('meta_center', ''))}</text>",
    ]
    return parts, w, h


def _title_block(parts: list[str], w: int, h: int, fig: dict[str, Any]) -> None:
    bx, by, bw, bh = w - 250, h - 74, 210, 54
    parts.append(
        f'  <g data-graph-role="decoration">'
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{PANEL}" stroke="{STROKE}" stroke-width="1"/>'
        f'<text x="{bx + 10}" y="{by + 18}" font-size="9" fill="{MUTED}" letter-spacing="0.08em">MINI-HARNESS / '
        f"{esc(fig.get('sheet', 'M1'))}</text>"
        f'<text x="{bx + 10}" y="{by + 33}" font-size="9" fill="{SUB}">SHEET {esc(fig.get("id", ""))}</text>'
        f'<text x="{bx + 10}" y="{by + 46}" font-size="9" fill="{SUB}">画法：UML 2.5 / IE 鸦爪 / C4</text>'
        f"</g>"
    )


def _footer(parts: list[str], w: int, h: int, fig: dict[str, Any]) -> None:
    footer = fig.get("footer", "")
    if footer:
        parts.append(
            f'  <text x="40" y="{h - 24}" font-size="10" fill="{MUTED}">{esc(footer)}</text>'
        )


def _node_box(
    parts: list[str],
    node_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    sublabel: str = "",
    type_label: str = "",
    *,
    fill: str = PANEL,
    stroke: str = STROKE,
    dashed: bool = False,
) -> None:
    dash = ' stroke-dasharray="6,3"' if dashed else ""
    parts.append(
        f'  <g data-graph-role="node" data-node-id="{esc(node_id)}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{dash} data-node-id="{esc(node_id)}"/>'
        f'<text x="{x + w / 2}" y="{y + 20}" font-size="12.5" fill="{INK}" text-anchor="middle">{esc(label)}</text>'
    )
    if sublabel:
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 36}" font-size="10" fill="{SUB}" text-anchor="middle">{esc(sublabel)}</text>'
        )
    if type_label:
        parts.append(
            f'<text x="{x + 8}" y="{y + h - 8}" font-size="9" fill="{MUTED}" letter-spacing="0.06em">{esc(type_label)}</text>'
        )
    parts.append("</g>")


def _label(
    parts: list[str],
    owner: str,
    x: float,
    y: float,
    text: str,
    size: float = 10.5,
    color: str = SUB,
    anchor: str = "middle",
) -> None:
    parts.append(
        f'  <text data-graph-role="label" data-owner="{esc(owner)}" x="{x}" y="{y}" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}">{esc(text)}</text>'
    )


def _edge(
    parts: list[str],
    edge_id: str,
    points: list[tuple[float, float]],
    source: str,
    target: str,
    flow: str = "control",
    *,
    dashed: bool = False,
    marker: str = "uArrow",
    marker_start: str = "",
) -> None:
    path = " ".join(f"{'M' if i == 0 else 'L'} {px:g} {py:g}" for i, (px, py) in enumerate(points))
    dash = ' stroke-dasharray="6,3"' if dashed else ""
    start = f' marker-start="url(#{marker_start})"' if marker_start else ""
    parts.append(
        f'  <path data-graph-role="edge" data-edge-id="{esc(edge_id)}" data-source="{esc(source)}" '
        f'data-target="{esc(target)}" data-edge-kind="flow" data-flow="{esc(flow)}" '
        f'd="{path}" fill="none" stroke="{FLOW_COLORS.get(flow, ACCENT)}" stroke-width="1.6"'
        f'{dash}{start} marker-end="url(#{marker})"/>'
    )


# ------------------------------------------------------------------ sequence


def _sequence(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    actors = spec["actors"]
    top = float(spec.get("top", 120))
    bottom = float(spec.get("bottom", h - 110))
    left = float(spec.get("left", 90))
    span = w - 2 * left
    step = span / max(1, len(actors) - 1)
    xs: dict[str, float] = {}
    for index, actor in enumerate(actors):
        cx = left + index * step
        xs[actor["id"]] = cx
        box_w = float(actor.get("width", 150))
        _node_box(
            parts,
            actor["id"],
            cx - box_w / 2,
            top - 46,
            box_w,
            34,
            actor["label"],
            actor.get("sublabel", ""),
            actor.get("type_label", ""),
            dashed=bool(actor.get("dashed")),
        )
        _node_box(
            parts,
            f"{actor['id']}-tail",
            cx - box_w / 2,
            bottom,
            box_w,
            34,
            actor["label"],
        )
        parts.append(
            f'  <line x1="{cx}" y1="{top - 12}" x2="{cx}" y2="{bottom}" stroke="{MUTED}" '
            f'stroke-width="1" stroke-dasharray="5,4" data-graph-role="decoration"/>'
        )

    y = top + 10
    row_h = float(spec.get("row_h", 46))
    ys: list[float] = []
    for message in spec["messages"]:
        ys.append(y)
        y += row_h + (12 if message.get("kind") == "self" else 0)

    for frame in spec.get("frames", []):
        i0, i1 = frame["msg_range"]
        cover = [xs[a] for a in frame["covers"]]
        x0 = min(cover) - float(frame.get("pad", 62))
        x1 = max(cover) + float(frame.get("pad", 62))
        y0 = ys[i0] - 26.0
        y1 = ys[i1] + 22.0
        tag = frame["label"]
        tag_w = tw(tag, 10.0) + 26.0
        parts.append(
            f'  <g data-graph-role="decoration">'
            f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" '
            f'stroke="{MUTED}" stroke-width="1" stroke-dasharray="7,4"/>'
            f'<path d="M {x0} {y0} L {x0 + tag_w} {y0} L {x0 + tag_w} {y0 + 14} L {x0 + tag_w - 9} {y0 + 20} '
            f'L {x0} {y0 + 20} z" fill="{ACCENT}" opacity="0.28" stroke="{MUTED}" stroke-width="1"/>'
            f'<text x="{x0 + 8}" y="{y0 + 14}" font-size="10" fill="{INK}">{esc(tag)}</text>'
        )
        if frame.get("divider_after") is not None:
            dy = ys[frame["divider_after"]] - 13.0
            parts.append(
                f'<line x1="{x0}" y1="{dy}" x2="{x1}" y2="{dy}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="7,4"/>'
            )
            if frame.get("else_label"):
                parts.append(
                    f'<path d="M {x0} {dy} L {x0 + tw(frame["else_label"], 10.0) + 26} {dy} '
                    f"L {x0 + tw(frame['else_label'], 10.0) + 26} {dy + 14} "
                    f'L {x0 + tw(frame["else_label"], 10.0) + 17} {dy + 20} L {x0} {dy + 20} z" '
                    f'fill="{ACCENT}" opacity="0.28" stroke="{MUTED}" stroke-width="1"/>'
                    f'<text x="{x0 + 8}" y="{dy + 14}" font-size="10" fill="{INK}">{esc(frame["else_label"])}</text>'
                )
        parts.append("</g>")

    for index, message in enumerate(spec["messages"]):
        y = ys[index]
        mid = message["id"]
        x_from, x_to = xs[message["from"]], xs[message["to"]]
        kind = message.get("kind", "sync")
        if kind == "self":
            _edge(
                parts,
                mid,
                [(x_from, y), (x_from + 44, y), (x_from + 44, y + 40), (x_from, y + 40)],
                message["from"],
                message["from"],
                message.get("flow", "write"),
                marker="uArrow",
            )
            _label(parts, mid, x_from + 52, y - 6, message["label"], anchor="start")
            continue
        dashed = kind in {"ret", "async"}
        marker = "uArrowOpen" if kind == "ret" else "uArrow"
        flow = message.get("flow", "feedback" if kind == "ret" else "control")
        _edge(
            parts,
            mid,
            [(x_from, y), (x_to, y)],
            message["from"],
            message["to"],
            flow,
            dashed=dashed,
            marker=marker,
        )
        _label(parts, mid, (x_from + x_to) / 2, y - 8, message["label"])
        if message.get("activate"):
            bar_w = float(message.get("bar", 10))
            bar_h = float(message.get("bar_h", 34))
            parts.append(
                f'  <rect x="{x_to - bar_w / 2}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{ACCENT}" '
                f'opacity="0.35" stroke="{ACCENT}" stroke-width="1" data-graph-role="decoration"/>'
            )
    fig["_seq_bottom"] = y


# ------------------------------------------------------------------ class


def _class_box(parts: list[str], cls: dict[str, Any]) -> None:
    x, y, w = float(cls["x"]), float(cls["y"]), float(cls["width"])
    name_h = 26.0
    attrs = cls.get("attrs", [])
    methods = cls.get("methods", [])
    attr_h = 20.0 + 16.0 * len(attrs) if attrs else 0.0
    meth_h = 20.0 + 16.0 * len(methods) if methods else 0.0
    h = float(cls.get("height", name_h + attr_h + meth_h))
    stereotype = cls.get("stereotype")
    parts.append(
        f'  <g data-graph-role="node" data-node-id="{esc(cls["id"])}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{PANEL}" stroke="{STROKE}" stroke-width="1.4" data-node-id="{esc(cls["id"])}"/>'
    )
    if stereotype:
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 13}" font-size="9.5" fill="{MUTED}" text-anchor="middle">{esc(stereotype)}</text>'
        )
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 24}" font-size="12.5" fill="{INK}" text-anchor="middle">{esc(cls["name"])}</text>'
        )
    else:
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 18}" font-size="12.5" fill="{INK}" text-anchor="middle">{esc(cls["name"])}</text>'
        )
    cursor = y + name_h
    if attrs:
        parts.append(
            f'<line x1="{x}" y1="{cursor}" x2="{x + w}" y2="{cursor}" stroke="{STROKE}" stroke-width="1" opacity="0.7"/>'
        )
        cursor += 16
        for attr in attrs:
            parts.append(
                f'<text x="{x + 10}" y="{cursor}" font-size="10.5" fill="{SUB}">{esc(attr)}</text>'
            )
            cursor += 16
    if methods:
        parts.append(
            f'<line x1="{x}" y1="{cursor - 6}" x2="{x + w}" y2="{cursor - 6}" stroke="{STROKE}" stroke-width="1" opacity="0.7"/>'
        )
        cursor += 6
        for method in methods:
            parts.append(
                f'<text x="{x + 10}" y="{cursor}" font-size="10.5" fill="{SUB}">{esc(method)}</text>'
            )
            cursor += 16
    if cls.get("note"):
        parts.append(
            f'<text x="{x + 8}" y="{y + h - 8}" font-size="9" fill="{MUTED}" letter-spacing="0.06em">{esc(cls["note"])}</text>'
        )
    parts.append("</g>")
    cls["_bounds"] = (x, y, x + w, y + h)


def _class(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    for cls in spec["classes"]:
        _class_box(parts, cls)
    bounds = {cls["id"]: cls["_bounds"] for cls in spec["classes"]}
    styles = {
        "association": {"marker": "", "marker_start": "", "dashed": False},
        "navigable": {"marker": "uArrowOpen", "marker_start": "", "dashed": False},
        "generalization": {"marker": "uTriHollow", "marker_start": "", "dashed": False},
        "realization": {"marker": "uTriHollow", "marker_start": "", "dashed": True},
        "dependency": {"marker": "uArrowOpen", "marker_start": "", "dashed": True},
        "composition": {"marker": "", "marker_start": "uDiamondFilled", "dashed": False},
        "aggregation": {"marker": "", "marker_start": "uDiamondHollow", "dashed": False},
    }
    for rel in spec["relations"]:
        style = styles[rel["type"]]
        points = rel["points"]
        _edge(
            parts,
            rel["id"],
            points,
            rel["from"],
            rel["to"],
            rel.get("flow", "control"),
            dashed=style["dashed"],
            marker=style["marker"],
            marker_start=style["marker_start"],
        )
        label_at = rel.get("label_at") or points[len(points) // 2]
        if rel.get("label"):
            _label(parts, rel["id"], label_at[0], label_at[1] - 8, rel["label"])
        if rel.get("from_mult"):
            _label(
                parts,
                rel["id"],
                points[0][0] + 10,
                points[0][1] + 16,
                rel["from_mult"],
                9.5,
                MUTED,
                "start",
            )
        if rel.get("to_mult"):
            _label(
                parts,
                rel["id"],
                points[-1][0] - 10,
                points[-1][1] + 16,
                rel["to_mult"],
                9.5,
                MUTED,
                "end",
            )
        _ = bounds


# ------------------------------------------------------------------ er


def _er(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    for ent in spec["entities"]:
        x, y, bw = float(ent["x"]), float(ent["y"]), float(ent["width"])
        rows = ent.get("attrs", [])
        hname = 28.0
        bh = float(ent.get("height", hname + 18.0 * len(rows) + 8))
        parts.append(
            f'  <g data-graph-role="node" data-node-id="{esc(ent["id"])}">'
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="2" fill="{PANEL}" stroke="{STROKE}" stroke-width="1.4" data-node-id="{esc(ent["id"])}"/>'
            f'<rect x="{x}" y="{y}" width="{bw}" height="{hname}" fill="{ACCENT}" opacity="0.18" data-node-id="{esc(ent["id"])}"/>'
            f'<text x="{x + bw / 2}" y="{y + 19}" font-size="12.5" fill="{INK}" text-anchor="middle">{esc(ent["name"])}</text>'
        )
        cursor = y + hname + 14
        for attr in rows:
            key = attr.get("key", "")
            badge = {"PK": OK, "FK": WARN}.get(key, "")
            if key:
                parts.append(
                    f'<rect x="{x + 8}" y="{cursor - 10}" width="22" height="13" rx="2" fill="{badge}" opacity="0.22" '
                    f'stroke="{badge}" stroke-width="0.8"/>'
                    f'<text x="{x + 19}" y="{cursor}" font-size="8.5" fill="{badge}" text-anchor="middle">{esc(key)}</text>'
                )
            parts.append(
                f'<text x="{x + 36}" y="{cursor}" font-size="10.5" fill="{SUB}">{esc(attr["name"])}</text>'
            )
            if attr.get("note"):
                parts.append(
                    f'<text x="{x + bw - 8}" y="{cursor}" font-size="9" fill="{MUTED}" text-anchor="end">{esc(attr["note"])}</text>'
                )
            cursor += 18
        parts.append("</g>")
    ends = {"one": "uCrowOne", "many": "uCrowFoot", "zero-or-one": "uCrowZeroOne", "none": ""}
    for rel in spec["relations"]:
        _edge(
            parts,
            rel["id"],
            rel["points"],
            rel["from"],
            rel["to"],
            rel.get("flow", "data"),
            marker=ends.get(rel.get("to_card", "one"), "uCrowOne"),
            marker_start=ends.get(rel.get("from_card", "one"), ""),
        )
        mid = rel.get("label_at") or rel["points"][len(rel["points"]) // 2]
        if rel.get("label"):
            _label(parts, rel["id"], mid[0], mid[1] - 10, rel["label"], 10, SUB)


# ------------------------------------------------------------------ state machine


def _state(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    for state in spec["states"]:
        sid = state["id"]
        if state.get("kind") == "initial":
            cx, cy = float(state["x"]), float(state["y"])
            parts.append(
                f'  <g data-graph-role="node" data-node-id="{esc(sid)}">'
                f'<circle cx="{cx}" cy="{cy}" r="9" fill="{ACCENT}" data-node-id="{esc(sid)}"/></g>'
            )
            continue
        if state.get("kind") == "final":
            cx, cy = float(state["x"]), float(state["y"])
            parts.append(
                f'  <g data-graph-role="node" data-node-id="{esc(sid)}">'
                f'<circle cx="{cx}" cy="{cy}" r="12" fill="none" stroke="{ACCENT}" stroke-width="2" data-node-id="{esc(sid)}"/>'
                f'<circle cx="{cx}" cy="{cy}" r="6" fill="{ACCENT}" data-node-id="{esc(sid)}"/></g>'
            )
            continue
        x, y, bw, bh = (
            float(state["x"]),
            float(state["y"]),
            float(state["width"]),
            float(state["height"]),
        )
        parts.append(
            f'  <g data-graph-role="node" data-node-id="{esc(sid)}">'
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="{bh / 2}" fill="{PANEL}" stroke="{STROKE}" stroke-width="1.4" data-node-id="{esc(sid)}"/>'
            f'<text x="{x + bw / 2}" y="{y + 21}" font-size="12" fill="{INK}" text-anchor="middle">{esc(state["name"])}</text>'
        )
        if state.get("activity"):
            parts.append(
                f'<text x="{x + bw / 2}" y="{y + 36}" font-size="9.5" fill="{SUB}" text-anchor="middle">{esc(state["activity"])}</text>'
            )
        parts.append("</g>")
    for trans in spec["transitions"]:
        _edge(
            parts,
            trans["id"],
            trans["points"],
            trans["from"],
            trans["to"],
            trans.get("flow", "control"),
            dashed=bool(trans.get("dashed")),
        )
        mid = trans.get("label_at") or trans["points"][len(trans["points"]) // 2]
        if trans.get("trigger"):
            _label(parts, trans["id"], mid[0], mid[1] - 10, trans["trigger"], 10, INK)
        if trans.get("guard"):
            _label(parts, trans["id"], mid[0], mid[1] + 14, trans["guard"], 9.5, MUTED)


# ------------------------------------------------------------------ component


def _component(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    for comp in spec["components"]:
        x, y, cw, ch = (
            float(comp["x"]),
            float(comp["y"]),
            float(comp["width"]),
            float(comp["height"]),
        )
        tab = 16.0
        parts.append(
            f'  <g data-graph-role="node" data-node-id="{esc(comp["id"])}">'
            f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="2" fill="{PANEL}" stroke="{STROKE}" stroke-width="1.4" data-node-id="{esc(comp["id"])}"/>'
            f'<rect x="{x}" y="{y}" width="26" height="{tab}" fill="{ACCENT}" opacity="0.25" stroke="{STROKE}" stroke-width="1" data-node-id="{esc(comp["id"])}"/>'
            f'<line x1="{x + 26}" y1="{y}" x2="{x + 26}" y2="{y + tab}" stroke="{STROKE}" stroke-width="1"/>'
            f'<text x="{x + cw / 2}" y="{y + 34}" font-size="12" fill="{INK}" text-anchor="middle">{esc(comp["name"])}</text>'
        )
        for line in comp.get("lines", []):
            parts.append(
                f'<text x="{x + cw / 2}" y="{y + 52}" font-size="9.5" fill="{SUB}" text-anchor="middle">{esc(line)}</text>'
            )
        parts.append("</g>")
    for iface in spec.get("interfaces", []):
        cx, cy = float(iface["x"]), float(iface["y"])
        if iface.get("kind") == "provided":
            parts.append(
                f'  <g data-graph-role="decoration">'
                f'<circle cx="{cx}" cy="{cy}" r="7" fill="none" stroke="{OK}" stroke-width="1.6"/>'
                f'<line x1="{cx}" y1="{cy + 7}" x2="{cx}" y2="{cy + 18}" stroke="{OK}" stroke-width="1.4"/></g>'
            )
        else:
            parts.append(
                f'  <g data-graph-role="decoration">'
                f'<path d="M {cx - 8} {cy - 6} A 9 9 0 0 1 {cx + 8} {cy - 6}" fill="none" stroke="{WARN}" stroke-width="1.6"/>'
                f'<line x1="{cx}" y1="{cy - 6}" x2="{cx}" y2="{cy + 10}" stroke="{WARN}" stroke-width="1.4"/></g>'
            )
        if iface.get("label"):
            _label(parts, iface["id"], cx, cy - 16, iface["label"], 9.5, MUTED)
    for link in spec.get("links", []):
        _edge(
            parts,
            link["id"],
            link["points"],
            link["from"],
            link["to"],
            link.get("flow", "control"),
            dashed=True,
        )
        mid = link.get("label_at") or link["points"][len(link["points"]) // 2]
        if link.get("label"):
            _label(parts, link["id"], mid[0], mid[1] - 8, link["label"], 9.5, SUB)


# ------------------------------------------------------------------ formula card


def _card(fig: dict[str, Any], parts: list[str], w: int, h: int) -> None:
    spec = fig["spec"]
    for card in spec["cards"]:
        x, y, cw, ch = (
            float(card["x"]),
            float(card["y"]),
            float(card["width"]),
            float(card["height"]),
        )
        accent = {"warn": WARN, "ok": OK, "info": ACCENT}.get(card.get("tone", "info"), ACCENT)
        parts.append(
            f'  <g data-graph-role="node" data-node-id="{esc(card["id"])}">'
            f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="2" fill="{PANEL}" stroke="{accent}" stroke-width="1.4" stroke-dasharray="6,3" data-node-id="{esc(card["id"])}"/>'
            f'<text x="{x + 14}" y="{y + 22}" font-size="11.5" fill="{INK}" letter-spacing="0.05em">{esc(card["title"])}</text>'
        )
        cursor = y + 42
        for line in card.get("lines", []):
            parts.append(
                f'<text x="{x + 14}" y="{cursor}" font-size="10.5" fill="{SUB}">{esc(line)}</text>'
            )
            cursor += 18
        parts.append(
            f'<text x="{x + 14}" y="{y + ch - 12}" font-size="9" fill="{accent}" letter-spacing="0.06em">{esc(card.get("status", ""))}</text>'
        )
        parts.append("</g>")
    for note in spec.get("notes", []):
        _label(
            parts, note["id"], float(note["x"]), float(note["y"]), note["text"], 10, MUTED, "start"
        )


BUILDERS = {
    "sequence": _sequence,
    "class": _class,
    "er": _er,
    "state": _state,
    "component": _component,
    "card": _card,
}


def emit(fig: dict[str, Any]) -> str:
    kind = fig["uml_kind"]
    if kind not in BUILDERS:
        raise ValueError(f"未知 UML 类型：{kind}")
    parts, w, h = _skeleton(fig)
    BUILDERS[kind](fig, parts, w, h)
    for index, item in enumerate(fig.get("legend", [])):
        lx = 40 + index * 190
        ly = h - 66
        color = FLOW_COLORS.get(item["flow"], ACCENT)
        parts.append(
            f'  <g data-graph-role="decoration"><line x1="{lx}" y1="{ly}" x2="{lx + 34}" y2="{ly}" '
            f'stroke="{color}" stroke-width="1.6"{' stroke-dasharray="6,3"' if item.get("dashed") else ""} '
            f'marker-end="url(#uArrow)"/>'
            f'<text x="{lx + 42}" y="{ly + 4}" font-size="9.5" fill="{MUTED}">{esc(item["label"])}</text></g>'
        )
    _title_block(parts, w, h, fig)
    _footer(parts, w, h, fig)
    parts.append("</svg>")
    return "\n".join(parts)
