#!/usr/bin/env bash
# 归档前校验：契约、任务、UAT、变异、规格结构。任一缺失即非零退出。
# 用法：scripts/check-change.sh <change-id>
set -euo pipefail
cd "$(dirname "$0")/.."

id="${1:?用法: scripts/check-change.sh <change-id>}"
dir="openspec/changes/$id"
fail=0

check_file() {
  if [ ! -s "$1" ]; then
    echo "缺：$1" >&2
    fail=1
  fi
}

check_file "$dir/verification-contract.md"
check_file "docs/verification/$id-uat.md"
check_file "docs/verification/$id-mutation.md"

if grep -q '^- \[ \]' "$dir/tasks.md" 2>/dev/null; then
  echo "tasks 还有未勾项：" >&2
  grep -n '^- \[ \]' "$dir/tasks.md" >&2
  fail=1
fi

uv run openspec validate "$id" --strict || fail=1

if [ "$fail" -ne 0 ]; then
  echo "归档检查未通过" >&2
  exit 1
fi
echo "归档检查通过：$id"
