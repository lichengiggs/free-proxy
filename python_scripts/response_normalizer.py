from __future__ import annotations

import re
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


_LONGCAT_TOOL_CALL_MARKERS = ('<longcat_tool_call>', '<longcat_arg_key>', '<longcat_arg_value>')
_LONGCAT_ARG_PATTERN = re.compile(
    r'<longcat_arg_key>(?P<key>.*?)</longcat_arg_key>\s*<longcat_arg_value>(?P<value>.*?)</longcat_arg_value>',
    re.S,
)


def sanitize_model_text(text: str) -> str:
    if not text or not any(marker in text for marker in _LONGCAT_TOOL_CALL_MARKERS):
        return text

    prefix = text.split('<longcat_arg_key>', 1)[0].split('<longcat_tool_call>', 1)[0].strip()
    question_items: list[dict[str, str]] = []
    for match in _LONGCAT_ARG_PATTERN.finditer(text):
        raw_value = match.group('value').strip().rstrip(',')
        if raw_value and not raw_value.startswith('['):
            raw_value = f'[{raw_value}]'
        try:
            parsed = json.loads(raw_value) if raw_value else []
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            if not isinstance(item, dict):
                continue
            question = item.get('question')
            if not isinstance(question, str) or not question.strip():
                continue
            header = item.get('header')
            question_items.append(
                {
                    'header': header.strip() if isinstance(header, str) and header.strip() else '',
                    'question': question.strip(),
                }
            )

    if question_items:
        lines: list[str] = []
        if prefix:
            lines.append(prefix)
            lines.append('')
        for index, item in enumerate(question_items, start=1):
            if item['header']:
                lines.append(f'{index}. {item["header"]}：{item["question"]}')
            else:
                lines.append(f'{index}. {item["question"]}')
        return '\n'.join(lines).strip()

    cleaned = prefix or text
    return cleaned.replace('question\n', '').replace('question', '').strip()


def _sse_json_line(payload: dict[str, object] | str) -> bytes:
    if isinstance(payload, str):
        return f'data: {payload}\n\n'.encode('utf-8')
    return f'data: {json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}\n\n'.encode('utf-8')


def _stream_text_delta(choice: object) -> dict[str, str]:
    if not isinstance(choice, dict):
        return {}
    message = choice.get('message')
    if isinstance(message, dict):
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


def wrap_openai_body_as_sse(*, fallback_model: str, body: bytes) -> Iterable[bytes]:
    parsed = json.loads(body.decode('utf-8'))
    if not isinstance(parsed, dict):
        return [_sse_json_line('[DONE]')]
    choices = parsed.get('choices')
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    chunk_id = str(parsed.get('id', f'chatcmpl-{int(time.time())}'))
    created_raw = parsed.get('created')
    created = created_raw if isinstance(created_raw, int) else int(time.time())
    actual_model = str(parsed.get('model') or fallback_model)
    delta = _stream_text_delta(first_choice)
    chunks: list[bytes] = []
    if delta:
        chunks.append(
            _sse_json_line(
                {
                    'id': chunk_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': actual_model,
                    'choices': [{'index': 0, 'delta': {key: sanitize_model_text(value) for key, value in delta.items()}, 'finish_reason': None}],
                }
            )
        )
    finish_reason = 'stop'
    if isinstance(first_choice, dict):
        raw_finish_reason = first_choice.get('finish_reason')
        if isinstance(raw_finish_reason, str) and raw_finish_reason:
            finish_reason = raw_finish_reason
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
    now = int(time.time())
    body = json.dumps(
        {
            'id': f'chatcmpl-{now}',
            'object': 'chat.completion',
            'created': now,
            'model': f'{provider}/{model}',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
        },
        ensure_ascii=False,
    ).encode('utf-8')
    return RelayResponse(200, {'Content-Type': 'application/json; charset=utf-8'}, body, None)


def normalize_sse_success(*, provider: str, model: str, body: bytes) -> RelayResponse:
    return RelayResponse(
        200,
        {'Content-Type': 'text/event-stream; charset=utf-8'},
        None,
        wrap_openai_body_as_sse(fallback_model=f'{provider}/{model}', body=body),
    )
