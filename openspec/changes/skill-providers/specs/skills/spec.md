# Spec Delta

## MODIFIED Requirements

### Requirement: preset 作用域技能层

配置 SHALL 接受 `[subagent.presets.<id>.skills]`：`kind`（目前只接受 `filesystem`）与 `dirs`（字符串数组）。子会话的技能视图 SHALL 是「全局 provider 层」加「preset 的 provider 层」：**近层同名技能直接胜出**（MUST NOT 再看 rank）；同一层内按 provider 的 rank 与注册顺序裁决。根会话 MUST NOT 有 preset 层。目录不存在 SHALL 视为空层，MUST NOT 让会话启动失败。

命令面（`/skills`、`/<技能名>`、host 命令清单）SHALL 与模型目录读**同一份注册表快照**，MUST NOT 再读装配期的 `settings.skills`。

#### Scenario: preset 层覆盖同名技能

- **WHEN** 全局有一个 `tdd`，preset 的 `dirs` 里也有一个 `tdd`
- **THEN** 子会话看到 preset 那份；父会话仍是全局那份

#### Scenario: preset 层独有的技能

- **WHEN** 一个技能只在 preset 的 `dirs` 里
- **THEN** 子会话的清单与命令面有它，父会话没有

#### Scenario: 近层低 rank 仍胜

- **WHEN** preset 层的同名技能 rank 比全局层大
- **THEN** 仍然是 preset 层胜出

#### Scenario: 不存在的目录是空层

- **WHEN** `dirs` 指向一个不存在的目录
- **THEN** 子会话照常启动，没有该层的技能，`skills_incomplete` 不出现

#### Scenario: 命令面与模型目录同源

- **WHEN** 会话进行中新增一个技能
- **THEN** 模型目录与 `/skills` 都在下一次观察时看到它
