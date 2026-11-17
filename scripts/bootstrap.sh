#!/usr/bin/env bash
# 新机器/新克隆的一次性恢复：校验 uv，装 pre-commit hook，确认格式基线。
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null 2>&1 || {
  echo "缺 uv：先安装 https://docs.astral.sh/uv/ 再重跑" >&2
  exit 1
}
git rev-parse --git-dir >/dev/null 2>&1 || {
  echo "不在 git 仓库内" >&2
  exit 1
}

./scripts/install-hooks.sh
uv run ruff format --diff src tests >/dev/null
echo "bootstrap 完成：pre-commit 已启用，格式基线 OK"
