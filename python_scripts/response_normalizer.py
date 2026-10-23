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


def _assistant_message_payload(*, provider: str, model: str, content: str | None, tool_calls: list[dict[str, object]] | None) -> dict[str, object]:
    message: dict[str, object] = {'role': 'assistant'}
    if tool_calls:
        message['tool_calls'] = tool_calls
        message['content'] = None
    else:
        message['content'] = content or ''
    return {
        'id': f'chatcmpl-{int(time.time())}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': f'{provider}/{model}',
        'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if tool_calls else 'stop'}],
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
