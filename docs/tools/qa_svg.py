"""SVG 视觉质检：连线完整性、文字重叠、文字溢出、字号下限、配色与对比度。

用法：`uv run --no-project python docs/tools/qa_svg.py [--only 图id前缀] [--json]`

判据全部来自 SVG 几何与颜色，不依赖肉眼：
- 连线端点必须落在自己节点的边界上（断线、悬空头尾会被抓）。
- 连线不得穿过非端点节点的内部（线从图形中间穿过去会被抓）。
- 文字框不得与别的节点图形、别的文字、或一条连线相交。
- 文字框必须落在自己的节点里（溢出超过 4px 报警）。
- 文字色与其脚下图形填充色的对比度必须 >= 3.0（低于 3.0 就是「看不见」）。
- 图形填充色必须来自本图自己声明的配色（style 块 / 背景 / 连线色），否则算跑错主题。
- 箭头标签的文字框必须被它的底色矩形包住。
- 字号不得小于 10.5。
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SVG_DIR = REPO / "repowiki" / "assets" / "svg"
OUT = REPO / "repowiki" / "assets" / "meta" / "qa-report.json"

MIN_FONT = 10.5
MIN_CONTRAST = 3.0
OVERLAP_TOL = 1.5
SPILL_TOL = 4.0
ENDPOINT_TOL = 7.0

# 两套主题的合法配色。跑错主题的填充与描边（例如深色蓝图里出现近白的数据库柱体）会被抓。
THEME_ALLOW: dict[str, set[str]] = {
    "fireworks-tech-graph": {
        "#082f49",
        "#0b3b5e",
        "#67e8f9",
        "#0ea5e9",
        "#22d3ee",
        "#38bdf8",
        "#fde047",
        "#c084fc",
        "#fb7185",
        "#bae6fd",
        "#e0f2fe",
        "#7dd3fc",
        "#cbd5e1",
        "#94a3b8",
        "#0f172a",
    },
    "mini-harness-uml": {
        "#0a1628",
        "#0d1f3c",
        "#112240",
        "#00b4d8",
        "#48cae4",
        "#90e0ef",
        "#caf0f8",
        "#06d6a0",
        "#f77f00",
    },
}

Box = tuple[float, float, float, float]


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    text = value.strip()
    if not text.startswith("#"):
        return None
    body = text[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) != 6:
        return None
    try:
        return (int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16))
    except ValueError:
        return None


def luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def text_width(text: str, size: float) -> float:
    """等宽字体下的宽度估算：CJK 1.02em，ASCII 0.62em，空格 0.30em。"""
    total = 0.0
    for ch in text:
        code = ord(ch)
        if code >= 0x2E80 or code in {0xFF01, 0xFF0C}:
            total += 1.02
        elif ch == " ":
            total += 0.30
        else:
            total += 0.62
    return total * size


def text_box(el: ET.Element, text: str, size: float) -> Box:
    x = float(el.get("x", "0"))
    y = float(el.get("y", "0"))
    width = text_width(text, size)
    anchor = (el.get("text-anchor") or "start").lower()
    if anchor == "middle":
        left, right = x - width / 2.0, x + width / 2.0
    elif anchor == "end":
        left, right = x - width, x
    else:
        left, right = x, x + width
    return (left, y - 0.85 * size, right, y + 0.28 * size)


def boxes_overlap(a: Box, b: Box, tol: float = 0.0) -> bool:
    return not (a[2] <= b[0] + tol or b[2] <= a[0] + tol or a[3] <= b[1] + tol or b[3] <= a[1] + tol)


def box_area(a: Box) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def overlap_area(a: Box, b: Box) -> float:
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def segment_hits_box(p0: tuple[float, float], p1: tuple[float, float], box: Box, pad: float = 0.0) -> bool:
    """Liang-Barsky：线段与矩形是否有内部交点。"""
    left, top, right, bottom = (box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad)
    if right <= left or bottom <= top:
        return False
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for delta, origin, bound_low, bound_high in (
        (-dx, p0[0], left, right),
        (dx, p0[0], left, right),
        (-dy, p0[1], top, bottom),
        (dy, p0[1], top, bottom),
    ):
        if abs(delta) < 1e-9:
            if origin < bound_low or origin > bound_high:
                return False
            continue
        ta = (bound_low - origin) / delta
        tb = (bound_high - origin) / delta
        if delta < 0:
            ta, tb = tb, ta
        t0 = max(t0, ta)
        t1 = min(t1, tb)
        if t0 > t1:
            return False
    return True


def parse_path_points(d: str) -> list[tuple[float, float]]:
    """只认 M/L/H/V 组成的折线（本项目所有连线都是），命令字母后可带空格，大小写都吃。"""
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    for command, numbers in re.findall(r"([MLHVmlhv])\s*((?:[-\d.]+[ ,]*)+)", d):
        values = [float(v) for v in re.split(r"[ ,]+", numbers.strip()) if v]
        if not values:
            continue
        relative = command.islower()
        kind = command.upper()
        if kind == "M":
            x, y = values[0], values[1]
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)
            # M 之后多余的坐标对按隐式 L 处理
            for i in range(2, len(values) - 1, 2):
                x, y = values[i], values[i + 1]
                current = (current[0] + x, current[1] + y) if relative else (x, y)
                points.append(current)
        elif kind == "L":
            for i in range(0, len(values) - 1, 2):
                x, y = values[i], values[i + 1]
                current = (current[0] + x, current[1] + y) if relative else (x, y)
                points.append(current)
        elif kind == "H":
            for value in values:
                current = (current[0] + value, current[1]) if relative else (value, current[1])
                points.append(current)
        elif kind == "V":
            for value in values:
                current = (current[0], current[1] + value) if relative else (current[0], value)
                points.append(current)
    return points


def class_fills(style_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for selector, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", style_text):
        match = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6})", body)
        if match:
            out[selector] = match.group(1)
    return out


def declared_colors(root: ET.Element) -> set[str]:
    """本图自己声明的配色：style 块里的 fill、背景矩形、连线描边、marker 填充。"""
    colors: set[str] = set()
    for el in root.iter():
        tag = strip_ns(el.tag)
        if tag == "style":
            colors.update(v.lower() for v in class_fills(el.text or "").values())
        for attr in ("fill", "stroke"):
            value = el.get(attr)
            if value and parse_color(value):
                colors.add(value.lower())
    return colors


def shape_bounds(el: ET.Element) -> Box | None:
    tag = strip_ns(el.tag)
    try:
        if tag == "rect":
            x, y = float(el.get("x", "0")), float(el.get("y", "0"))
            return (x, y, x + float(el.get("width", "0")), y + float(el.get("height", "0")))
        if tag == "circle":
            cx, cy, r = float(el.get("cx", "0")), float(el.get("cy", "0")), float(el.get("r", "0"))
            return (cx - r, cy - r, cx + r, cy + r)
        if tag == "ellipse":
            cx, cy = float(el.get("cx", "0")), float(el.get("cy", "0"))
            rx, ry = float(el.get("rx", "0")), float(el.get("ry", "0"))
            return (cx - rx, cy - ry, cx + rx, cy + ry)
    except ValueError:
        return None
    return None


def parse_bounds_attr(value: str | None) -> Box | None:
    if not value:
        return None
    parts = [float(p) for p in value.split(",") if p.strip()]
    if len(parts) != 4:
        return None
    return (parts[0], parts[1], parts[2], parts[3])


def union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def first_class(el: ET.Element) -> str:
    classes = (el.get("class") or "").split()
    return classes[0] if classes else ""


def load_svg(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    width = float(root.get("width", "0"))
    height = float(root.get("height", "0"))

    fills: dict[str, str] = {}
    style_text = ""
    for el in root.iter():
        if strip_ns(el.tag) == "style":
            style_text = el.text or ""
    fills.update(class_fills(style_text))

    background = "#000000"
    for el in root.iter():
        if strip_ns(el.tag) == "rect" and el.get("data-graph-role") == "background":
            background = el.get("fill", background)
            break

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    markers = {el.get("id") for el in root.iter() if strip_ns(el.tag) == "marker"}

    def walk(el: ET.Element, node: dict[str, Any] | None) -> None:
        tag = strip_ns(el.tag)
        current = node
        if tag == "g" and el.get("data-graph-role") == "node":
            shapes = [shape_bounds(child) for child in el if shape_bounds(child)]
            shapes = [s for s in shapes if s]
            bounds = parse_bounds_attr(el.get("data-graph-bounds")) or union(shapes)
            fills_under = [
                child.get("fill")
                for child in el
                if shape_bounds(child) and parse_color(child.get("fill"))
            ]
            current = {
                "id": el.get("data-node-id") or el.get("id") or f"node-{len(nodes)}",
                "kind": el.get("data-semantic-role") or "",
                "bounds": bounds,
                "shapes": shapes,
                "fills": [f for f in fills_under if f],
                "strokes": [
                    child.get("stroke")
                    for child in el
                    if shape_bounds(child) and parse_color(child.get("stroke"))
                ],
            }
            nodes.append(current)
        if tag in {"path", "line", "polyline"} and (
            el.get("data-graph-role") == "edge" or el.get("data-source") or el.get("marker-end")
        ):
            if tag == "line":
                points = [
                    (float(el.get("x1", "0")), float(el.get("y1", "0"))),
                    (float(el.get("x2", "0")), float(el.get("y2", "0"))),
                ]
            else:
                points = parse_path_points(el.get("d", ""))
            if len(points) >= 2:
                edges.append(
                    {
                        "id": el.get("data-edge-id") or el.get("id") or f"edge-{len(edges)}",
                        "source": el.get("data-source"),
                        "target": el.get("data-target"),
                        "points": points,
                        "marker_end": el.get("marker-end"),
                        "marker_start": el.get("marker-start"),
                        "flow": el.get("data-flow") or "",
                    }
                )
            return
        if tag == "text":
            raw = "".join(el.itertext())
            size = float(el.get("font-size") or fills_font(first_class(el), style_text) or 12)
            fill = el.get("fill") or fills.get(first_class(el), "")
            texts.append(
                {
                    "id": raw[:40],
                    "text": raw,
                    "role": el.get("data-text-role") or el.get("class") or "",
                    "size": size,
                    "fill": fill,
                    "box": text_box(el, raw, size),
                    "node": current["id"] if current else None,
                }
            )
            return
        for child in list(el):
            walk(child, current)

    walk(root, None)
    return {
        "root": root,
        "width": width,
        "height": height,
        "background": background,
        "generator": root.get("data-generator", ""),
        "nodes": nodes,
        "edges": edges,
        "texts": texts,
        "markers": markers,
        "palette": declared_colors(root),
    }


def fills_font(class_name: str, style_text: str) -> float | None:
    for selector, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", style_text):
        if selector == (class_name or "").split()[0]:
            match = re.search(r"font-size:\s*([\d.]+)", body)
            if match:
                return float(match.group(1))
    return None


def check_figure(path: Path) -> dict[str, Any]:
    data = load_svg(path)
    issues: list[dict[str, Any]] = []

    def add(kind: str, detail: str, *, severity: str = "high") -> None:
        issues.append({"kind": kind, "severity": severity, "detail": detail})

    node_by_id = {n["id"]: n for n in data["nodes"] if n["bounds"]}
    bg = parse_color(data["background"]) or (0, 0, 0)

    # 1. 连线端点必须贴在自己节点边界上
    for edge in data["edges"]:
        for role in ("source", "target"):
            node_id = edge.get(role)
            if not node_id:
                continue
            node = node_by_id.get(node_id)
            if node is None:
                add("断线", f"{edge['id']} 的 {role} 指向不存在的节点 {node_id}")
                continue
            point = edge["points"][0] if role == "source" else edge["points"][-1]
            left, top, right, bottom = node["bounds"]
            near = (
                abs(point[0] - left) <= ENDPOINT_TOL
                or abs(point[0] - right) <= ENDPOINT_TOL
                or abs(point[1] - top) <= ENDPOINT_TOL
                or abs(point[1] - bottom) <= ENDPOINT_TOL
            )
            inside = left + ENDPOINT_TOL < point[0] < right - ENDPOINT_TOL and top + ENDPOINT_TOL < point[1] < bottom - ENDPOINT_TOL
            if not near or inside:
                add("断线", f"{edge['id']} 的 {role} 端点 ({point[0]:.0f}, {point[1]:.0f}) 没有贴在 {node_id} 的边界上")

    # 2. 连线不得穿过非端点节点
    for edge in data["edges"]:
        for node in data["nodes"]:
            if not node["bounds"] or node["id"] in {edge.get("source"), edge.get("target")}:
                continue
            for p0, p1 in zip(edge["points"], edge["points"][1:]):
                if segment_hits_box(p0, p1, node["bounds"], pad=1.0):
                    add("线穿图形", f"{edge['id']} 穿过 {node['id']} 内部")
                    break

    # 3. 文字与别的节点图形、别的文字、别的连线相交
    for text in data["texts"]:
        for node in data["nodes"]:
            if not node["bounds"] or node["id"] == text["node"]:
                continue
            if overlap_area(text["box"], node["bounds"]) > 40.0:
                add("文字压在图形上", f"「{text['text']}」与节点 {node['id']} 重叠", severity="medium")
                break
    for i, first in enumerate(data["texts"]):
        for second in data["texts"][i + 1 :]:
            if first["node"] == second["node"] and first["node"] is not None:
                continue
            shared = overlap_area(first["box"], second["box"])
            smaller = min(box_area(first["box"]), box_area(second["box"]))
            if smaller > 0 and shared / smaller > 0.25:
                add("文字互相重叠", f"「{first['text']}」与「{second['text']}」重叠 {shared:.0f}px²")
    for text in data["texts"]:
        for edge in data["edges"]:
            hit = any(segment_hits_box(p0, p1, text["box"], pad=0.5) for p0, p1 in zip(edge["points"], edge["points"][1:]))
            if hit:
                add("线穿文字", f"连线 {edge['id']} 从「{text['text']}」中间穿过")
                break

    # 4. 文字溢出自己的节点
    for text in data["texts"]:
        node = node_by_id.get(text["node"] or "")
        if node is None:
            continue
        left, top, right, bottom = node["bounds"]
        box = text["box"]
        spill = max(box[0] - left, right - box[2], box[1] - top, bottom - box[3])
        if -spill > SPILL_TOL:
            add("文字溢出", f"「{text['text']}」在 {node['id']} 里溢出 {-spill:.0f}px", severity="medium")

    # 5. 对比度：文字色 vs 脚下填充色；填充色 vs 画布
    for text in data["texts"]:
        fill = parse_color(text["fill"])
        if fill is None:
            continue
        if text["fill"].lower() not in THEME_ALLOW.get(data["generator"], data["palette"]):
            add("配色跑题", f"文字「{text['text']}」的颜色 {text['fill']} 不在主题配色表里", severity="medium")
        node = node_by_id.get(text["node"] or "")
        under = None
        if node and node["fills"]:
            under = parse_color(node["fills"][0])
        base = under or bg
        ratio = contrast(fill, base)
        if ratio < MIN_CONTRAST:
            add(
                "文字对比度不足",
                f"「{text['text']}」{text['fill']} 对 {('#%02x%02x%02x' % base) if under else '画布'} 只有 {ratio:.2f}",
            )
    allowed = THEME_ALLOW.get(data["generator"], data["palette"])
    for node in data["nodes"]:
        for fill in node["fills"]:
            color = parse_color(fill)
            if color is None:
                continue
            if fill.lower() not in allowed:
                add("配色跑题", f"{node['id']} 的填充 {fill} 不在 {data['generator']} 主题的配色表里")
        for stroke in node["strokes"]:
            if stroke and stroke.lower() not in allowed:
                add("配色跑题", f"{node['id']} 的描边 {stroke} 不在 {data['generator']} 主题的配色表里", severity="medium")

    # 6. 字号下限
    for text in data["texts"]:
        if text["size"] < MIN_FONT:
            add("字号过小", f"「{text['text']}」字号 {text['size']}", severity="medium")

    # 7. 箭头记号必须存在
    for edge in data["edges"]:
        for attr in ("marker_end", "marker_start"):
            value = edge.get(attr)
            if not value:
                continue
            match = re.search(r"#([^)]+)", value)
            if match and match.group(1) not in data["markers"]:
                add("箭头记号缺失", f"{edge['id']} 引用了未定义的记号 {value}")

    # 8. 画布越界
    for node in data["nodes"]:
        if not node["bounds"]:
            continue
        left, top, right, bottom = node["bounds"]
        if left < 0 or top < 0 or right > data["width"] + 1 or bottom > data["height"] + 1:
            add("图形越出画布", f"{node['id']} 的边界 {node['bounds']} 超出 {data['width']}x{data['height']}")
    for text in data["texts"]:
        left, top, right, bottom = text["box"]
        if left < -1 or top < -1 or right > data["width"] + 1 or bottom > data["height"] + 1:
            add("文字越出画布", f"「{text['text']}」超出画布", severity="medium")

    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["kind"]] = counts.get(issue["kind"], 0) + 1
    return {
        "id": path.stem,
        "generator": data["generator"],
        "nodes": len(data["nodes"]),
        "edges": len(data["edges"]),
        "texts": len(data["texts"]),
        "high": sum(1 for i in issues if i["severity"] == "high"),
        "medium": sum(1 for i in issues if i["severity"] == "medium"),
        "counts": counts,
        "issues": issues,
    }


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    only = ""
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    paths = sorted(p for p in SVG_DIR.glob("*.svg") if not only or p.stem.startswith(only))
    if not paths:
        print(f"没有图可查：{SVG_DIR}")
        return 1

    results = [check_figure(p) for p in paths]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    bad = 0
    for result in results:
        if not result["issues"]:
            continue
        bad += 1
        print(f"✗ {result['id']}  高 {result['high']} 中 {result['medium']}  {result['counts']}")
        for issue in result["issues"][:12]:
            print(f"    [{issue['severity']}] {issue['kind']}：{issue['detail']}")
        if len(result["issues"]) > 12:
            print(f"    …另 {len(result['issues']) - 12} 条见 {OUT}")
    print(f"\n共 {len(results)} 图，有问题 {bad} 图 -> {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
