# Spec Delta

## MODIFIED Requirements

### Requirement: write 覆盖已存在文件前必须先读过
系统 SHALL 让 `write` 按 `file_path` 写入给定 `content`（UTF-8、覆盖式、必要时创建父目录）。目标文件已存在时，该派发点之前 MUST 已有对该路径且 `outcome` 为 `OK` 的 `read`，否则 SHALL 产出 `outcome: WRITE_WITHOUT_READ` 的 `tool/result` 且该文件字节不变。目标不存在时 SHALL 直接创建。

「对该路径」SHALL 按路径键判定：路径键 SHALL 把已存在的成分规范化成磁盘上的写法，因此大小写不敏感的文件系统上 `notes/plan.md` 与 `Notes/Plan.MD` 是同一个键；大小写敏感的文件系统上它们是两个键。

#### Scenario: 读过之后覆盖成功
- **WHEN** 同一 session 里先 `read` 某文件再 `write` 它
- **THEN** 结果是 `OK`，且文件内容等于给定的 `content`

#### Scenario: 没读过就覆盖被拒
- **WHEN** 本 session 没有 `read` 过某已存在文件就直接 `write` 它
- **THEN** 结果是 `WRITE_WITHOUT_READ`，该文件字节不变

#### Scenario: 换一种写法也是同一个文件
- **WHEN** 文件系统折叠大小写，先 `read` `notes/plan.md` 再 `write` `Notes/Plan.MD`
- **THEN** 结果是 `OK`（两者打开的是同一个文件）

#### Scenario: 不折叠时是另一个文件
- **WHEN** 文件系统区分大小写，先 `read` `notes/plan.md` 再 `write` `Notes/Plan.MD`
- **THEN** 结果是 `PATH_NOT_FOUND`（读不到）与 `WRITE_WITHOUT_READ`（没读过就写），两者都不是同一个文件

#### Scenario: 新文件不需要先读
- **WHEN** `write` 的目标在派发点之前不存在
- **THEN** 结果是 `OK` 且文件被创建

#### Scenario: 目标是目录是 IS_A_DIRECTORY
- **WHEN** `write` 的 `file_path` 指向一个目录
- **THEN** 结果是 `IS_A_DIRECTORY`，该目录的内容不变

### Requirement: edit 是字面替换且受 CAS 约束
系统 SHALL 让 `edit` 在已 `read` 过的文件里做字面替换：`old_string` MUST 恰好出现一次，除非 `replace_all` 为真。`edit` MUST 要求该派发点之前有对该路径 `outcome` 为 `OK` 的 `read`，且替换时的文件内容 MUST 与该次 `read` 返回的内容一致。「对该路径」与 `write` 同一条路径键规则。

#### Scenario: 唯一匹配替换成功
- **WHEN** 读过某文件后 `edit` 它，`old_string` 在文件里恰出现一次
- **THEN** 结果是 `OK`，该字面串被 `new_string` 替换且只替换这一处

#### Scenario: 目标不存在与多处匹配是两个不同的结果
- **WHEN** `old_string` 在文件里出现 0 次，或出现多次而 `replace_all` 为假
- **THEN** 结果分别是 `EDIT_TARGET_NOT_FOUND` 与 `EDIT_TARGET_AMBIGUOUS`，文件内容不变

#### Scenario: 原文与读到时不一致是 STALE_EDIT
- **WHEN** 读过某文件后该文件在 session 之外被改动，再对它 `edit`
- **THEN** 结果是 `STALE_EDIT`，文件不被改写

#### Scenario: 没读过就 edit 被拒
- **WHEN** 本 session 没有 `read` 过某文件就直接 `edit` 它
- **THEN** 结果是 `WRITE_WITHOUT_READ`
