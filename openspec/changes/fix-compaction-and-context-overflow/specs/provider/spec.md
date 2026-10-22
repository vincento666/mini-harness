# Spec Delta

## ADDED Requirements

### Requirement: 失败结果带上提供方说的那句话
当一次模型请求得到 4xx 或 5xx 的回复时，失败结果的 `detail` SHALL 同时含状态码与响应正文的有界摘要：单行（换行压成空格）、整条至多 200 字符、取自响应 JSON 里错误对象的 `message`（取不到时取正文本身），正文为空或读不出时只有状态码。该摘要 SHALL 写进 `error/model` 的 payload，也 SHALL NOT 改变失败结果的 `code`。

#### Scenario: 正文里那句话进 detail
- **WHEN** 假端点返回 400 且响应 JSON 是 `{"error": {"type": "invalid_request_error", "message": "prompt leaves no room to answer"}}`
- **THEN** 失败结果的 `detail` 含 `HTTP 400` 与 `prompt leaves no room to answer`

#### Scenario: 正文不是 JSON 时取正文本身
- **WHEN** 假端点返回 502 且正文是一段以 `<` 开头的 HTML
- **THEN** 失败结果的 `detail` 含 `HTTP 502` 与该正文的开头，且不超过 200 字符

#### Scenario: 空正文不制造空话
- **WHEN** 假端点返回 400 且正文为空
- **THEN** 失败结果的 `detail` 就是 `HTTP 400`

## MODIFIED Requirements

### Requirement: 上下文超限的回复是溢出结果
当真实 provider 返回 4xx（429 除外，它走既有的重试）且响应 JSON 里的错误对象指向「提示词装不进上下文」时，系统 SHALL 产出 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果：MUST NOT 为它重试（它不是 429 也不是 5xx），MUST NOT 塌成 `PROVIDER_HTTP_STATUS`。指向它有两种形状：错误对象的 `code` 为 `context_length_exceeded`；或错误对象的 `message` 含固定短语表里的某一条（大小写不敏感）。两者都不指向时仍按既有的「状态码不可接受」路径走；重试耗尽的 5xx 也仍走那条路径。

#### Scenario: 上下文超限的 400 不重试
- **WHEN** 假端点对一次请求返回 400 且 `error.code` 为 `context_length_exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 413 报同一个 code 也塌成溢出
- **WHEN** 假端点返回 413 且 `error.code` 为 `context_length_exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 正文说装不下时也塌成溢出
- **WHEN** 假端点返回 400、错误对象没有 `code`，但 `message` 是 `prompt (222233 tokens) leaves no room to answer in the context (196608); requests are never truncated`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 其它 400 仍走既有路径
- **WHEN** 假端点返回 400 且 `error.code` 是别的值（例如 `invalid_request_error`）、`error.message` 不含固定短语表里的任何一条
- **THEN** `generate` 返回 `code: PROVIDER_HTTP_STATUS` 的失败结果
