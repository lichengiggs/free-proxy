#!/usr/bin/env python3
"""Smoke ``free-proxy/auto`` against the provider keys already in ``.env``.

This is a night-review and explicit Acceptance check. It is not part of unittest.
"""

from __future__ import annotations

import json
import signal
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python_scripts.service import ProxyService


class _SmokeTimeout(Exception):
    """The live smoke exceeded its overall deadline."""


def _alarm(_signum: int, _frame: object) -> None:
    raise _SmokeTimeout()


def _nonstream_text(body: bytes | None) -> str:
    if not body:
        return ''
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return ''
    if not isinstance(parsed, dict):
        return ''
    choices = parsed.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ''
    message = choices[0].get('message')
    if not isinstance(message, dict):
        return ''
    content = message.get('content')
    if isinstance(content, str) and content.strip():
        return content.strip()
    reasoning = message.get('reasoning_content')
    if isinstance(reasoning, str):
        return reasoning.strip()
    return ''


def _stream_text(chunks: object) -> tuple[str, bool]:
    parts: list[str] = []
    saw_done = False
    if chunks is None:
        return '', False
    for chunk in chunks:
        if isinstance(chunk, str):
            raw = chunk.encode('utf-8')
        elif isinstance(chunk, (bytes, bytearray)):
            raw = bytes(chunk)
        else:
            continue
        if b'data:[DONE]' in raw.replace(b' ', b''):
            saw_done = True
        for line in raw.splitlines():
            if not line.startswith(b'data:'):
                continue
            data = line[5:].strip()
            if data == b'[DONE]':
                saw_done = True
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            choices = payload.get('choices')
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                continue
            delta = choices[0].get('delta')
            if not isinstance(delta, dict):
                continue
            text = delta.get('content') or delta.get('reasoning_content') or ''
            if isinstance(text, str):
                parts.append(text)
    return ''.join(parts).strip(), saw_done


def _fail(reason: str) -> int:
    print(f'live provider: fail {reason[:240]}')
    return 1


def main() -> int:
    """Call the public auto alias once without streaming and once with streaming.

    Args:
        None.

    Returns:
        0 when no provider key is configured, or both calls return text and the
        streaming call includes ``data: [DONE]``. Returns 1 when a call fails.
        The line ``live provider: ok`` is printed only on success.

    Raises:
        This function does not raise. Timeouts and provider errors are printed
        and returned as 1.
    """
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(90)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = ProxyService(
                health_path=root / 'health.json',
                preferred_model_path=root / 'preferred.json',
                token_limit_path=root / 'limits.json',
                request_timeout_seconds=20,
            )
            if not service.available_providers():
                print('live provider: skipped no key')
                return 0
            relay = service.openai_relay()
            base = {
                'model': 'free-proxy/auto',
                'messages': [{'role': 'user', 'content': 'Reply with the single word pong.'}],
                'max_tokens': 16,
            }
            plain = relay.handle_chat(relay.normalize(dict(base)))
            if plain.status != 200 or not _nonstream_text(plain.body):
                return _fail(f'non-stream status {plain.status}')
            streamed = relay.handle_chat(relay.normalize({**base, 'stream': True}))
            if streamed.status != 200 or streamed.stream_chunks is None:
                return _fail(f'stream status {streamed.status}')
            text, saw_done = _stream_text(streamed.stream_chunks)
            if not text or not saw_done:
                return _fail('stream ended without text and data: [DONE]')
    except _SmokeTimeout:
        return _fail('timeout')
    except Exception as exc:
        return _fail(f'{type(exc).__name__}')
    finally:
        signal.alarm(0)
    print('live provider: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
