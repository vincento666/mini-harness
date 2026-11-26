# Spec Delta: chat-repl

## ADDED Requirements

### Requirement: 提示符只在回到等待状态时出现

`minihns chat` 的提示符 SHALL 出现在两种时刻：会话开始后第一次等待输入、以及处理完一条非空输入（一轮或一条命令）之后。空白输入 MUST NOT 紧接着再出现一条提示符。提示符 MUST NOT 进事件日志，stdout 上模型回复正文的投影规则 MUST NOT 因本条改变。

#### Scenario: 粘贴末尾的空行不多出提示符

- **WHEN** 人向提示符提交一条带尾随空行的粘贴（等价于非空输入后紧跟一条空白输入）
- **THEN** stdout 上该次交互之后恰有一条提示符，没有第二条紧挨着出现

#### Scenario: 故意按回车后输入照常提交

- **WHEN** 人在提示符上只提交空白内容，然后在光标所在空行输入一句话
- **THEN** 这句话照常作为一条输入处理（写 `user/message`、开一轮），日志规则与投影规则不变

#### Scenario: 命令之后提示符照常回来

- **WHEN** 人输入 `/skills` 后再提交一条空白输入
- **THEN** `/skills` 的清单照常打印，之后提示符恰出现一次，空白没有再追加一条
