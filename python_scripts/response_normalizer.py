from __future__ import annotations

from collections.abc import Iterable
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RelayResponse:
    status: int
    headers: dict[str, str]
    body: bytes | None
    stream_chunks: object | None


def sanitize_model_text(text: str) -> str:
    return text


def _sse_json_line(payload: dict[str, object] | str) -> bytes:
    if isinstance(payload, str):
        return f'data: {payload}\n\n'.encode('utf-8')
    return f'data: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'.encode('utf-8')


def _stream_text_delta(_provider: str, choice: object) -> dict[str, object]:
    if not isinstance(choice, dict):
        return {}
    message = choice.get('message')
    if isinstance(message, dict):
        tool_calls = message.get('tool_calls')
        if isinstance(tool_calls, list) and tool_calls:
            return {'tool_calls': tool_calls}
        content = message.get('content')
        if isinstance(content, str) and content:
            return {'role': str(message.get('role') or 'assistant'), 'content': sanitize_model_text(content)}
        reasoning = message.get('reasoning_content')
        if isinstance(reasoning, str) and reasoning:
            return {'role': str(message.get('role') or 'assistant'), 'reasoning_content': sanitize_model_text(reasoning)}
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get('text')
                    if isinstance(text, str) and text:
                        chunks.append(sanitize_model_text(text))
            merged = ''.join(chunks)
            if merged:
                return {'role': str(message.get('role') or 'assistant'), 'content': merged}
    text = choice.get('text')
    if isinstance(text, str) and text:
        return {'role': 'assistant', 'content': sanitize_model_text(text)}
    return {}


def _normalized_assistant_message(_provider: str, parsed: object) -> tuple[str | None, list[dict[str, object]] | None, str]:
    if not isinstance(parsed, dict):
        return None, None, 'stop'
    choices = parsed.get('choices')
    if not isinstance(choices, list) or not choices:
        return None, None, 'stop'
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None, None, 'stop'
    finish_reason = 'stop'
    raw_finish_reason = first_choice.get('finish_reason')
    if isinstance(raw_finish_reason, str) and raw_finish_reason:
        finish_reason = raw_finish_reason
    message = first_choice.get('message')
    if isinstance(message, dict):
        tool_calls = message.get('tool_calls')
        if isinstance(tool_calls, list) and tool_calls:
            return None, [item for item in tool_calls if isinstance(item, dict)], 'tool_calls'
        content = message.get('content')
        if isinstance(content, str) and content.strip():
            return sanitize_model_text(content.strip()), None, finish_reason
        reasoning = message.get('reasoning_content')
        if isinstance(reasoning, str) and reasoning.strip():
            return sanitize_model_text(reasoning.strip()), None, finish_reason
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get('text')
                    if isinstance(text, str) and text.strip():
                        chunks.append(sanitize_model_text(text.strip()))
            merged = '\n'.join(chunks).strip()
            if merged:
                return merged, None, finish_reason
    text = first_choice.get('text')
    if isinstance(text, str) and text.strip():
        return sanitize_model_text(text.strip()), None, finish_reason
    return None, None, finish_reason


def _assistant_message_payload(
    *,
    provider: str,
    model: str,
    content: str | None,
    tool_calls: list[dict[str, object]] | None,
    finish_reason: str | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {'role': 'assistant'}
    if tool_calls:
        message['tool_calls'] = tool_calls
        message['content'] = None
    else:
        message['content'] = content or ''
    resolved_finish_reason = 'tool_calls' if tool_calls else (finish_reason or 'stop')
    return {
        'id': f'chatcmpl-{int(time.time())}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': f'{provider}/{model}',
        'choices': [{'index': 0, 'message': message, 'finish_reason': resolved_finish_reason}],
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
    }


def wrap_openai_body_as_sse(*, provider: str, fallback_model: str, body: bytes) -> Iterable[bytes]:
    parsed = json.loads(body.decode('utf-8'))
    if not isinstance(parsed, dict):
        return [_sse_json_line('[DONE]')]
    choices = parsed.get('choices')
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    chunk_id = str(parsed.get('id', f'chatcmpl-{int(time.time())}'))
    created_raw = parsed.get('created')
    created = created_raw if isinstance(created_raw, int) else int(time.time())
    actual_model = str(parsed.get('model') or fallback_model)
    delta = _stream_text_delta(provider, first_choice)
    chunks: list[bytes] = []
    if delta:
        normalized_delta = dict(delta)
        if 'tool_calls' in normalized_delta:
            tool_calls = normalized_delta['tool_calls']
            if isinstance(tool_calls, list):
                normalized_delta['tool_calls'] = tool_calls
        chunks.append(
            _sse_json_line(
                {
                    'id': chunk_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': actual_model,
                    'choices': [{'index': 0, 'delta': normalized_delta, 'finish_reason': None if 'tool_calls' not in normalized_delta else 'tool_calls'}],
                }
            )
        )
    _, tool_calls, finish_reason = _normalized_assistant_message(provider, parsed)
    chunks.append(
        _sse_json_line(
            {
                'id': chunk_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': actual_model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}],
            }
        )
    )
    chunks.append(_sse_json_line('[DONE]'))
    return chunks


def normalize_json_success(*, provider: str, model: str, content: str) -> RelayResponse:
    body = json.dumps(_assistant_message_payload(provider=provider, model=model, content=content, tool_calls=None), ensure_ascii=False).encode('utf-8')
    return RelayResponse(200, {'Content-Type': 'application/json; charset=utf-8'}, body, None)


def normalize_sse_success(*, provider: str, model: str, body: bytes) -> RelayResponse:
    return RelayResponse(
        200,
        {'Content-Type': 'text/event-stream; charset=utf-8'},
        None,
        wrap_openai_body_as_sse(provider=provider, fallback_model=f'{provider}/{model}', body=body),
    )


def normalize_provider_response(*, provider: str, model: str, body: bytes, stream: bool) -> RelayResponse:
    parsed = json.loads(body.decode('utf-8'))
    content, tool_calls, _finish_reason = _normalized_assistant_message(provider, parsed)
    assistant_body = _assistant_message_payload(provider=provider, model=model, content=content, tool_calls=tool_calls)
    encoded = json.dumps(assistant_body, ensure_ascii=False).encode('utf-8')
    if stream:
        return RelayResponse(
            200,
            {'Content-Type': 'text/event-stream; charset=utf-8'},
            None,
            wrap_openai_body_as_sse(provider=provider, fallback_model=f'{provider}/{model}', body=body),
        )
    return RelayResponse(200, {'Content-Type': 'application/json; charset=utf-8'}, encoded, None)


def _sse_event_separator(pending: bytearray) -> tuple[int, int] | None:
    line_feed = pending.find(b'\n\n')
    carriage_return = pending.find(b'\r\n\r\n')
    if line_feed < 0 and carriage_return < 0:
        return None
    if carriage_return < 0 or (line_feed >= 0 and line_feed < carriage_return):
        return line_feed, 2
    return carriage_return, 4


def _sse_data_payload(raw_event: bytes) -> str | None:
    data_lines: list[str] = []
    for line in raw_event.splitlines():
        if not line.startswith(b'data:'):
            continue
        value = line[5:]
        if value.startswith(b' '):
            value = value[1:]
        data_lines.append(value.decode('utf-8', errors='ignore'))
    if not data_lines:
        return None
    return '\n'.join(data_lines)


def _iter_sse_data_payloads(chunks: Iterable[object]) -> Iterable[str]:
    pending = bytearray()
    for chunk in chunks:
        if isinstance(chunk, memoryview):
            chunk = chunk.tobytes()
        if isinstance(chunk, (bytes, bytearray)) and chunk:
            pending.extend(chunk)
        while True:
            separator = _sse_event_separator(pending)
            if separator is None:
                break
            index, length = separator
            raw_event = bytes(pending[:index])
            del pending[: index + length]
            payload = _sse_data_payload(raw_event)
            if payload is not None:
                yield payload
    if pending:
        payload = _sse_data_payload(bytes(pending))
        if payload is not None:
            yield payload


def _append_delta_text(delta: object, key: str, parts: list[str]) -> None:
    if not isinstance(delta, dict):
        return
    value = delta.get(key)
    if isinstance(value, str) and value:
        parts.append(value)


def synthesize_openai_json_from_sse(chunks: Iterable[bytes], *, provider: str, model: str) -> bytes:
    """把上游 OpenAI SSE 收成一份 chat completion JSON。

    Args:
        chunks: 按到达顺序的 SSE 分片。
        provider: 写入模型名的 provider。
        model: 写入模型名的模型 id。

    Returns:
        UTF-8 JSON。正文是 `choices[0].delta.content` 的顺序拼接；
        拼接结果为空时改用 `delta.reasoning_content`。`finish_reason`
        是最后一个非空值，没有则为 `stop`。

    Raises:
        Exception: 读取分片时抛出的错误会原样传出。
    """
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    for payload in _iter_sse_data_payloads(chunks):
        if payload.strip() == '[DONE]':
            break
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        choices = parsed.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        choice = choices[0]
        raw_finish_reason = choice.get('finish_reason')
        if isinstance(raw_finish_reason, str) and raw_finish_reason:
            finish_reason = raw_finish_reason
        _append_delta_text(choice.get('delta'), 'content', content_parts)
        _append_delta_text(choice.get('delta'), 'reasoning_content', reasoning_parts)
    content = ''.join(content_parts)
    if not content:
        content = ''.join(reasoning_parts)
    assistant_body = _assistant_message_payload(
        provider=provider,
        model=model,
        content=sanitize_model_text(content),
        tool_calls=None,
        finish_reason=finish_reason,
    )
    return json.dumps(assistant_body, ensure_ascii=False).encode('utf-8')
