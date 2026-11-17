#!/usr/bin/env bash
# 提交前快检：格式 / 风格 / 类型；全量测试留给 CI。
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff format --diff src tests
uv run ruff check src tests
uv run mypy --strict src
