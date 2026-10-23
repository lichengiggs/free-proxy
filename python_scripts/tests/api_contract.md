# API Contract Baseline

## GET /v1/models

**Response**: `200 OK`
```json
{
  "object": "list",
  "data": [
    {"id": "free-proxy/auto", "object": "model", "owned_by": "free-proxy"}
  ]
}
```

## POST /v1/chat/completions (non-stream)

**Request**: `{"model": "free-proxy/auto", "messages": [{"role": "user", "content": "hello"}]}`

**Response**: `200 OK`, `Content-Type: application/json; charset=utf-8`
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "provider/model",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

## POST /v1/chat/completions (stream)

**Request**: `{"model": "free-proxy/auto", "messages": [...], "stream": true}`

**Response**: `200 OK`, `Content-Type: text/event-stream; charset=utf-8`
```
data: {"id":"...","object":"chat.completion.chunk","model":"...","choices":[{"index":0,"delta":{"content":"..."},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","model":"...","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Error Responses

**400 Bad Request** (missing or unsupported model):
```json
{"error": {"message": "model must be 'free-proxy/auto'", "type": "invalid_request_error", "param": null, "code": null}}
```

空 `model`，以及 `auto` / `free-proxy/auto` / `free_proxy/auto` 之外的模型，都走这条错误。

**400 Bad Request** (empty messages):
```json
{"error": {"message": "messages must not be empty", "type": "invalid_request_error", "param": null, "code": null}}
```

**400 Bad Request** (deprecated model):
```json
{"error": {"message": "model 'coding' is no longer supported. Use 'free-proxy/auto' instead.", "type": "invalid_request_error", "param": null, "code": "model_deprecated"}}
```

`coding` / `free-proxy/coding` / `free_proxy/coding` 都返回这条文案。

## POST /chat/completions (UI debug)

**Request**: `{"provider": "groq", "model": "llama-3.1-8b-instant", "messages": [...]}`

**Response (non-stream)**: `200 OK`
```json
{"ok": true, "provider": "groq", "model": "llama-3.1-8b-instant", "actual_model": "llama-3.1-8b-instant", "content": "..."}
```

**Response (`stream: true`)**:

- OpenAI 格式 provider（如 Groq、OpenRouter）：只有该模型的 `model_capabilities.streaming` 为 `true` 时才向上游开流并原样返回 SSE。当前 catalog 没有设置这个能力，所以 `"stream": true` 仍走非流式上游，响应是上游 JSON，`Content-Type: application/json`。这不是 `{ok, content}` 包装，也不是 SSE。
- 非 OpenAI 格式 provider（当前只有 Gemini）：忽略 `stream`。成功时返回 `{"ok": true, "provider": "...", "model": "...", "actual_model": "...", "content": "..."}`。
