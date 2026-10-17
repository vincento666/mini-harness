# fixture 仓库

这份目录是**只读 fixture**：测试把它复制到 tmp 工作区再跑，绝不原地改。

- 5 个 `.md` 供 `glob` 匹配（`**/*.md` 恰返回这 5 个相对路径）。
- 其中恰有 3 行含同一个待办标记词，供 `grep` 计数。
- `calc.py` 与 `test_calc.py` 是一个可跑的小 pytest 工程。

`test_calc.py` 里那条必然失败的用例是**哨兵**：它证明主测试运行不把这份目录收进去
（`pyproject.toml` 的 `norecursedirs`）。它一旦被收进主套件，主套件立刻变红。
