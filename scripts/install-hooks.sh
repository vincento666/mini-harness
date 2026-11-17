#!/usr/bin/env bash
# 一次性安装：让 git 使用仓库内的 .githooks。
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x .githooks/pre-commit scripts/pre-commit.sh
git config core.hooksPath .githooks
echo "已启用 .githooks（pre-commit 跑格式/风格/类型）"
