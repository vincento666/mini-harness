"""fixture 仓库的小 pytest 工程：一条绿、一条必然失败。

必然失败那条是哨兵：主测试运行必须排除这份目录（见 `pyproject.toml` 的 `norecursedirs`）。
它一旦被收进主套件，主套件立刻变红。
"""

from calc import add


def test_add_is_correct() -> None:
    assert add(2, 3) == 5


def test_sentinel_always_fails() -> None:
    # 故意失败：这份目录只该被显式调用（`pytest tests/fixtures/repo`），不该被主套件收集。
    assert add(2, 3) == 999
