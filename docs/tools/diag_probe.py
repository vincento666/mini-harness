#!/usr/bin/env python3
"""Bisect why a fireworks IR fails to render: try dropping containers or arrows.

Usage: uv run --no-project python docs/tools/diag_probe.py <ir.json>
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys

SKILL_SCRIPTS = r"C:\Users\vincento\.agents\skills\fireworks-tech-graph\scripts"
sys.path.insert(0, SKILL_SCRIPTS)

_spec = importlib.util.spec_from_file_location("gft", SKILL_SCRIPTS + r"\generate-from-template.py")
gft = importlib.util.module_from_spec(_spec)
sys.modules["gft"] = gft
assert _spec.loader is not None
_spec.loader.exec_module(gft)


def attempt(data: dict, label: str) -> bool:
    try:
        svg, _report = gft.build_svg_with_report(
            str(data.get("template_type", "architecture")), data
        )
    except Exception as exc:
        print(f"  FAIL  {label}: {exc}")
        return False
    print(f"  OK    {label}  ({len(svg)} 字节)")
    return True


def main() -> int:
    arg = sys.argv[1]
    if arg.startswith("m1-"):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import diagram_defs

        fig = next(f for f in diagram_defs.FIGURES if f["id"] == arg)
        base = fig["ir"]
    else:
        base = json.loads(pathlib.Path(arg).read_text(encoding="utf-8"))

    print("完整 IR:")
    if attempt(base, "full"):
        return 0

    print("去掉 containers:")
    no_cont = copy.deepcopy(base)
    no_cont["containers"] = []
    attempt(no_cont, "no containers")

    print("逐个去掉某条边:")
    for arrow in base.get("arrows", []):
        variant = copy.deepcopy(base)
        variant["arrows"] = [a for a in variant["arrows"] if a.get("id") != arrow.get("id")]
        attempt(variant, f"drop {arrow.get('id')}")

    print("去掉 legend:")
    no_leg = copy.deepcopy(base)
    no_leg.pop("legend", None)
    attempt(no_leg, "no legend")

    print("去掉单个节点:")
    for node in base.get("nodes", []):
        variant = copy.deepcopy(base)
        variant["nodes"] = [n for n in variant["nodes"] if n.get("id") != node.get("id")]
        variant["arrows"] = [
            a
            for a in variant["arrows"]
            if a.get("source") != node.get("id") and a.get("target") != node.get("id")
        ]
        attempt(variant, f"drop node {node.get('id')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
