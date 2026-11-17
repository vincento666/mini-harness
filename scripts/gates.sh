#!/usr/bin/env bash
# 四道门禁 + 覆盖率三步，一条命令跑完；便宜的在前。
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff format --diff src tests
uv run ruff check src tests
uv run mypy --strict src

rm -rf .tmp/pytest-gates
uv run coverage erase
uv run coverage run -m pytest -q --basetemp=.tmp/pytest-gates -p no:cacheprovider
uv run coverage combine
uv run coverage report --fail-under=95 --show-missing
