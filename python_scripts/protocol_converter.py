from __future__ import annotations

import json
import time
from collections.abc import Iterable


def _extract_gemini_text(payload: dict[str, object]) -> str:
    candidates = payload.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        return ''
    first = candidates[0]
    if not isinstance(first, dict):
        return ''
    content = first.get('content')
    if not isinstance(content, dict):
        return ''
    parts = content.get('parts')
    if not isinstance(parts, list):
        return ''
    chunks: list[str] = []
    for item in parts:
        if isinstance(item, dict):
            text = item.get('text')
            if isinstance(text, str):
                chunks.append(text)
    return ''.join(chunks)


def gemini_json_to_openai_chat(provider: str, model: str, payload: dict[str, object]) -> bytes:
    now = int(time.time())
    return json.dumps(
        {
            'id': f'chatcmpl-{now}',
            'object': 'chat.completion',
            'created': now,
            'model': f'{provider}/{model}',
            'choices': [
                {
                    'index': 0,
                    'message': {'role': 'assistant', 'content': _extract_gemini_text(payload)},
                    'finish_reason': 'stop',
                }
            ],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
        },
        ensure_ascii=False,
    ).encode('utf-8')


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


def _iter_gemini_events(chunks: Iterable[bytes]) -> Iterable[dict[str, object]]:
    for payload in _iter_sse_data_payloads(chunks):
        if payload.strip() == '[DONE]':
            break
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            yield parsed


def _gemini_candidate(payload: dict[str, object]) -> dict[str, object] | None:
    candidates = payload.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if not isinstance(first, dict):
        return None
    return first


def _gemini_part_texts(candidate: dict[str, object]) -> list[str]:
    content = candidate.get('content')
    if not isinstance(content, dict):
        return []
    parts = content.get('parts')
    if not isinstance(parts, list):
        return []
    texts: list[str] = []
    for item in parts:
        if not isinstance(item, dict):
            continue
        text = item.get('text')
        if isinstance(text, str) and text:
            texts.append(text)
    return texts


def _gemini_finish_reason(candidate: dict[str, object]) -> str | None:
    raw = candidate.get('finishReason')
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().lower()
    return normalized or None


def _openai_sse_chunk(
    *,
    chunk_id: str,
    created: int,
    model_name: str,
    delta: dict[str, object],
    finish_reason: str | None,
) -> bytes:
    payload = {
        'id': chunk_id,
        'object': 'chat.completion.chunk',
        'created': created,
        'model': model_name,
        'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish_reason}],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return f'data: {encoded}\n\n'.encode('utf-8')


def iter_gemini_sse_as_openai_chunks(
    chunks: Iterable[bytes],
    *,
    provider: str,
    model: str,
) -> Iterable[bytes]:
    """把 Gemini `streamGenerateContent` SSE 映射成 OpenAI chat chunks。

    Args:
        chunks: 上游 SSE 字节。没有 `data: [DONE]`，读到迭代器结束。
        provider: 写入 chunk `model` 的 provider 名。
        model: 写入 chunk `model` 的模型 id。

    Returns:
        OpenAI `chat.completion.chunk` SSE。每个文本片段一个 `delta.content`，
        `finishReason` 另起一块小写 `finish_reason`，最后补 `data: [DONE]`。

    Raises:
        Exception: 读取 `chunks` 时抛出的错误会原样传出。
    """
    created = int(time.time())
    chunk_id = f'chatcmpl-{created}'
    model_name = f'{provider}/{model}'
    for event in _iter_gemini_events(chunks):
        candidate = _gemini_candidate(event)
        if candidate is None:
            continue
        for text in _gemini_part_texts(candidate):
            yield _openai_sse_chunk(
                chunk_id=chunk_id,
                created=created,
                model_name=model_name,
                delta={'content': text},
                finish_reason=None,
            )
        finish_reason = _gemini_finish_reason(candidate)
        if finish_reason is not None:
            yield _openai_sse_chunk(
                chunk_id=chunk_id,
                created=created,
                model_name=model_name,
                delta={},
                finish_reason=finish_reason,
            )
    yield b'data: [DONE]\n\n'


def gemini_sse_to_openai_chat(chunks: Iterable[bytes], *, provider: str, model: str) -> bytes:
    """把 Gemini SSE 片段收成一份 OpenAI chat completion JSON。

    Args:
        chunks: 上游 SSE 字节。按到达顺序拼接，后一个事件不覆盖前面的正文。
        provider: 写入 `model` 的 provider 名。
        model: 写入 `model` 的模型 id。

    Returns:
        与 `gemini_json_to_openai_chat()` 相同形状的 UTF-8 JSON。
        `choices[0].message.content` 是全部文本片段的拼接。

    Raises:
        Exception: 读取 `chunks` 时抛出的错误会原样传出。
    """
    texts: list[str] = []
    for event in _iter_gemini_events(chunks):
        candidate = _gemini_candidate(event)
        if candidate is None:
            continue
        texts.extend(_gemini_part_texts(candidate))
    merged = ''.join(texts)
    return gemini_json_to_openai_chat(
        provider,
        model,
        {'candidates': [{'content': {'parts': [{'text': merged}]}}]},
    )
