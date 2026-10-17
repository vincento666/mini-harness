#!/usr/bin/env python3
"""Dump a factual inventory of the mini-harness source tree for docs generation.

Writes JSON to repowiki/assets/meta/inventory.json: every module with its
classes, fields, method signatures, module functions, constants, and the exact
line ranges each entry occupies (so wiki citations can be exact).

Usage:  uv run python docs/tools/inventory.py
"""

from __future__ import annotations

import ast
import contextlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "repowiki" / "assets" / "meta" / "inventory.json"


def ann(node: ast.AST) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def decorator_text(dec: ast.expr) -> str:
    try:
        return ast.unparse(dec)
    except Exception:
        return "?"


def args_text(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = fn.args
    parts: list[str] = []

    def one(arg: ast.arg, default=None) -> str:
        name = arg.arg
        ty = ann(arg.annotation)
        text = f"{name}: {ty}" if ty else name
        if default is not None:
            text += f"={ann(default)}"
        return text

    pos = a.posonlyargs + a.args
    defaults = list(a.defaults)
    pad = len(pos) - len(defaults)
    for idx, arg in enumerate(pos):
        default = None if idx < pad else defaults[idx - pad]
        parts.append(one(arg, default))
    if a.vararg:
        parts.append("*" + one(a.vararg))
    elif a.kwonlyargs:
        parts.append("*")
    for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=False):
        parts.append(one(arg, default) + "")
    if a.kwarg:
        parts.append("**" + one(a.kwarg))
    return ", ".join(parts)


def func_entry(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    return {
        "name": ("async " if isinstance(fn, ast.AsyncFunctionDef) else "") + fn.name,
        "signature": f"{fn.name}({args_text(fn)}) -> {ann(fn.returns)}",
        "decorators": [decorator_text(d) for d in fn.decorator_list],
        "start": fn.lineno,
        "end": getattr(fn, "end_lineno", fn.lineno),
        "doc": (ast.get_docstring(fn) or "").splitlines()[0] if ast.get_docstring(fn) else "",
    }


def class_entry(cls: ast.ClassDef) -> dict:
    fields: list[dict] = []
    methods: list[dict] = []
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.append(
                {
                    "name": node.target.id,
                    "type": ann(node.annotation),
                    "default": ann(node.value) if node.value is not None else None,
                    "line": node.lineno,
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(func_entry(node))
    return {
        "name": cls.name,
        "bases": [ann(b) for b in cls.bases],
        "decorators": [decorator_text(d) for d in cls.decorator_list],
        "start": cls.lineno,
        "end": getattr(cls, "end_lineno", cls.lineno),
        "fields": fields,
        "methods": methods,
        "doc": (ast.get_docstring(cls) or "").splitlines()[0] if ast.get_docstring(cls) else "",
    }


def module_entry(path: pathlib.Path) -> dict:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    classes: list[dict] = []
    functions: list[dict] = []
    constants: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(class_entry(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(func_entry(node))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    with contextlib.suppress(Exception):
                        constants.append(
                            {
                                "name": target.id,
                                "value": ast.unparse(node.value),
                                "line": node.lineno,
                            }
                        )
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(f"{node.module} ({', '.join(a.name for a in node.names)})")
        elif isinstance(node, ast.Import):
            imports.append(", ".join(a.name for a in node.names))
    return {
        "path": path.relative_to(REPO).as_posix(),
        "lines": len(src.splitlines()),
        "imports": sorted(set(imports)),
        "constants": constants,
        "classes": classes,
        "functions": functions,
    }


def main() -> int:
    roots = [REPO / "src" / "mini_harness", REPO / "tests"]
    modules = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            modules.append(module_entry(path))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"repo": REPO.name, "modules": modules}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"modules={len(modules)} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
