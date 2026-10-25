# Spec Delta

## ADDED Requirements

### Requirement: 文件工具的描述引导优先用它们
`glob`、`grep`、`read` 三个文件工具的描述 SHALL 各带一句「什么时候用我」的引导：要列文件用 `glob`（它只列文件，不含子目录）、要搜内容用 `grep`、要读文件用 `read`，并点明这些事不需要用 `bash` 跑 `ls` / `grep` / `cat`，也不需要临时写一段脚本。这些描述 MUST 与平台无关——`dir`、`findstr`、`Get-Content` 这类平台专用命令只出现在头部的运行环境块里（ADR-0029）。

#### Scenario: glob 的描述点明列文件
- **WHEN** 读一次 run 发给模型的工具表里 `glob` 的描述
- **THEN** 描述里含「列文件」这类指引（并说明它只列文件、不含子目录），点明不要用 `bash` 的 `ls`

#### Scenario: grep 的描述点明搜内容
- **WHEN** 读同一份工具表里 `grep` 的描述
- **THEN** 描述里含「搜内容」这类指引，并点明不要用 `bash` 的 `grep`

#### Scenario: read 的描述点明读文件
- **WHEN** 读同一份工具表里 `read` 的描述
- **THEN** 描述里含「读文件」这类指引，并点明不要用 `bash` 的 `cat` 或 `type`

#### Scenario: 描述不写平台专用命令
- **WHEN** 读这三个文件工具的描述
- **THEN** 它们都不含 `dir`、`findstr`、`Get-Content` 这类只在某一个平台上成立的字样
