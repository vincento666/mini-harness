#!/usr/bin/env python3
"""Build every M1 diagram: render the fireworks IRs, emit the UML SVGs, validate all.

Outputs:
  repowiki/assets/svg/<id>.svg          校验通过的图（wiki 与图集共用的唯一真源）
  repowiki/assets/meta/diagram-report.json  每张图的校验结果

Usage: uv run --no-project python docs/tools/build_diagrams.py [--only <id-prefix>]
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SVG_DIR = REPO / "repowiki" / "assets" / "svg"
REPORT = REPO / "repowiki" / "assets" / "meta" / "diagram-report.json"
SKILL_SCRIPTS = r"C:\Users\vincento\.agents\skills\fireworks-tech-graph\scripts"
FIREWORKS_PY = pathlib.Path(SKILL_SCRIPTS) / "fireworks.py"

sys.path.insert(0, SKILL_SCRIPTS)
sys.path.insert(0, str(REPO / "docs" / "tools"))

_spec = importlib.util.spec_from_file_location("gft", SKILL_SCRIPTS + r"\generate-from-template.py")
gft = importlib.util.module_from_spec(_spec)
sys.modules["gft"] = gft
assert _spec.loader is not None
_spec.loader.exec_module(gft)

import diagram_defs
import uml_svg


def check_svg(path: pathlib.Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(FIREWORKS_PY), "check", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"ok": False, "raw": (proc.stdout or proc.stderr)[:400]}
    return data


def main() -> int:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    SVG_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    failures = 0

    for fig in diagram_defs.FIGURES:
        fid = fig["id"]
        if only and not fid.startswith(only):
            continue
        target = SVG_DIR / f"{fid}.svg"
        entry = {"id": fid, "title": fig["title"], "kind": fig["kind"], "group": fig["group"]}
        try:
            if fig["kind"] == "ir":
                svg, _report = gft.build_svg_with_report(fig["template"], fig["ir"])
            else:
                svg = uml_svg.emit(fig)
            target.write_text(svg, encoding="utf-8")
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = f"生成失败: {exc}"
            results.append(entry)
            failures += 1
            print(f"BUILD FAIL {fid}: {exc}")
            continue

        verdict = check_svg(target)
        entry["ok"] = bool(verdict.get("ok"))
        entry["bytes"] = target.stat().st_size
        if not entry["ok"]:
            entry["check"] = verdict
            failures += 1
            bad = {k: v for k, v in (verdict.get("checks") or {}).items() if not v.get("ok")}
            print(f"CHECK FAIL {fid}: {json.dumps(bad, ensure_ascii=False)[:600]}")
        else:
            print(f"ok {fid}  {entry['bytes']} 字节")
        results.append(entry)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n共 {len(results)} 张，失败 {failures} 张 -> {REPORT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
