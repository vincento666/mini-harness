#!/usr/bin/env bash
# 覆盖率读数：合并 partial 并出报告。**必须与 `scripts/gates.sh` 分开跑**——理由见那边
# 的注释（一次全量 pytest 就把删除额度花光，同一条命令里再删东西必被拦）。
set -euo pipefail
cd "$(dirname "$0")/.."

count=$(find . -maxdepth 1 -name '.coverage.*' | wc -l | tr -d ' ')
if [ "$count" -gt 0 ]; then
  uv run coverage combine --keep
else
  echo "警告：没有 .coverage.* partial，直接读上一次合并的结果（可能陈旧）" >&2
fi

uv run coverage report --fail-under=95 --show-missing
