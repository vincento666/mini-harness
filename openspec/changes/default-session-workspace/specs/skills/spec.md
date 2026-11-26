# Spec Delta: skills

## MODIFIED Requirements

### Requirement: 技能发现按四级根与优先级

系统 SHALL 从四个根发现技能：项目内 `<发现根>/.minihns/skills/`（rank 100）、项目共享 `<发现根>/.agents/skills/`（rank 200）、用户级 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`，rank 400）、内置 `src/mini_harness/builtin_skills/`（rank 600）。发现根是显式 `--workspace` 解析后的目录，未给 `--workspace` 时是当前目录（启动目录）；它 MUST NOT 锚默认的会话专属工作区。300（自定义目录）与 500（agents 家目录）不在本 change。

一个技能 SHALL 是 `<dir>/SKILL.md` 或扁平的 `<name>.md`，MUST NOT 递归发现子目录；名字 SHALL 匹配 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）。frontmatter SHALL 提供非空的 `name` 与 `description`，并 MAY 提供 `disable-model-invocation` 与 `user-invocable` 两个策略键（缺省都为允许）。策略键的取值 SHALL 接受大小写不敏感的 `true/false`、`yes/no`、`on/off`、`1/0`；其它拼写或非布尔值 SHALL 丢弃整个技能，MUST NOT 静默放行任何一面。名字不合规、frontmatter 缺失、描述为空或单个文件读不出的条目 SHALL 跳过，MUST NOT 让会话启动失败；**根目录本身扫不动**（`iterdir` 失败）SHALL 把这次发现标记为不完整（见「发现完整性」），MUST NOT 静默当作「没有技能」。描述进清单前 SHALL 截到 500 字符。同名技能 SHALL 只保留一个，rank 数字小者胜出；发现结果 SHALL 按名字排序，保证确定性。

#### Scenario: 四级根各有一个技能

- **WHEN** 四个根里各放一个不同名的技能
- **THEN** 清单按 rank 100 → 200 → 400 → 600 排列

#### Scenario: 未给 --workspace 时项目技能仍被发现

- **WHEN** 启动目录的 `.minihns/skills/` 放一个技能，不传 `--workspace` 启动会话
- **THEN** 该技能出现在清单里（rank 100）；会话专属工作区下的同名目录不被扫描

#### Scenario: 同名技能高优先级胜出

- **WHEN** 项目内与用户级各有一个 `tdd` 技能
- **THEN** 清单里只有一个 `tdd`，来自项目内（rank 100）

#### Scenario: 名字不合规的条目被跳过

- **WHEN** 某个根里有一个名字带大写的 `Bad_Name.md`
- **THEN** 它不出现在清单里，会话照常开始

#### Scenario: 缺 description 或无 frontmatter 的条目被跳过

- **WHEN** 某个根里有一个没有 frontmatter 的 `flat.md`
- **THEN** 它不是技能，不出现在任何出口

#### Scenario: 非法策略值丢弃整个技能

- **WHEN** 某个技能写 `disable-model-invocation: maybe`
- **THEN** 整个技能被跳过，而不是按默认值放行
