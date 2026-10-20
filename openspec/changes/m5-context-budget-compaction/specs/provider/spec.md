# Spec Delta

## ADDED Requirements

### Requirement: 上下文超限的回复是溢出结果
当真实 provider 返回状态码 400 且响应 JSON 里 `error.code` 为 `context_length_exceeded` 时，系统 SHALL 产出 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果：MUST NOT 重试（它不是 429 也不是 5xx），MUST NOT 塌成 `PROVIDER_HTTP_STATUS`。状态码 400 而 `error.code` 不是它时，仍按既有的「状态码不可接受」路径走。

#### Scenario: 上下文超限的 400 不重试
- **WHEN** 假端点对一次请求返回 400 且 `error.code` 为 `context_length_exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 其它 400 仍走既有路径
- **WHEN** 假端点返回 400 且 `error.code` 是别的值（例如 `invalid_request_error`）
- **THEN** `generate` 返回 `code: PROVIDER_HTTP_STATUS` 的失败结果
