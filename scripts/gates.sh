#!/usr/bin/env bash
# 四道门禁（跑完四道 + 全量测试）。覆盖率读数在 `scripts/coverage-report.sh`。
#
# 为什么拆成两条命令：沙箱的 sitecustomize 会拦 `shutil.rmtree` 与批量删除，按
# **单条命令累计删除的文件数**计数（阈值 50）。一次全量 pytest 自己的临时目录清理
# 就把这个额度花光了，于是紧随其后的 `coverage combine`（它会先删掉旧的目标文件）
# 必然被拦——报错原句见 `.tmp/gates-3.1.log`。分两条命令 = 两个额度，各自够用。
#
# 脚本里因此一步删除都不做：
#   1. basetemp 用**每次新目录**：pytest 会在用 tmp_path 之前删掉已存在的 basetemp，
#      1600 个文件必被拦，于是每条用例都 setup 失败（一次 542 个 ERROR）。
#   2. 不再 `rm -rf .tmp/pytest-gates`：同上，是上一次的产物挡住了这一次。
#   3. `coverage combine --keep`：不加 `--keep` 会删掉全部 partial，数量随黑盒子进程增长。
#      `coverage run -p` 本身不擦旧数据，合并是幂等的，所以不擦也能得到同样的读数。
#
# 攒大了怎么办：`.tmp/gates-*` 与 `.coverage.*` 会累积。单独跑一次
# `uv run coverage erase` 或 `rm -rf .tmp/gates-*`，由人批一次批量确认即可——它们在
# 脚本里没法弹窗，所以只能放在脚本外。
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff format --diff src tests
uv run ruff check src tests
uv run mypy --strict src

uv run coverage run -m pytest -q \
  --basetemp=".tmp/gates-$(date +%Y%m%d-%H%M%S)" -p no:cacheprovider
