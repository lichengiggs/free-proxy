from __future__ import annotations

import json
import unittest

from python_scripts.protocol_converter import gemini_json_to_openai_chat, gemini_sse_to_openai_chat, iter_gemini_sse_as_openai_chunks


class ProtocolConverterTests(unittest.TestCase):
    def test_gemini_json_to_openai_chat(self) -> None:
        payload = {
            'candidates': [
                {
                    'content': {
                        'parts': [{'text': 'hello from gemini'}],
                    }
                }
            ]
        }
        body = gemini_json_to_openai_chat('gemini', 'gemini-3.1-flash-lite-preview', payload)
        parsed = json.loads(body.decode('utf-8'))
        self.assertEqual(parsed['model'], 'gemini/gemini-3.1-flash-lite-preview')
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello from gemini')

    def test_gemini_sse_appends_fragments_and_maps_finish_reason(self) -> None:
        events = [
            _gemini_sse_event('hel'),
            _gemini_sse_event('lo', 'STOP'),
        ]
        chunks = list(iter_gemini_sse_as_openai_chunks(events, provider='gemini', model='gemini-2.0-flash'))
        parsed = [_parse_sse_chunk(chunk) for chunk in chunks]

        self.assertEqual(
            [
                (item['choices'][0]['delta'].get('content'), item['choices'][0]['finish_reason'])
                for item in parsed
                if item != '[DONE]'
            ],
            [('hel', None), ('lo', None), (None, 'stop')],
        )
        self.assertEqual(parsed[-1], '[DONE]')
        self.assertEqual(parsed[0]['object'], 'chat.completion.chunk')
        self.assertEqual(parsed[0]['model'], 'gemini/gemini-2.0-flash')

        body = gemini_sse_to_openai_chat(events, provider='gemini', model='gemini-2.0-flash')
        chat = json.loads(body.decode('utf-8'))
        self.assertEqual(chat['object'], 'chat.completion')
        self.assertEqual(chat['model'], 'gemini/gemini-2.0-flash')
        self.assertEqual(chat['choices'][0]['message']['role'], 'assistant')
        self.assertEqual(chat['choices'][0]['message']['content'], 'hello')
        self.assertEqual(chat['choices'][0]['finish_reason'], 'stop')

    def test_gemini_sse_keeps_spacing_and_lowercases_finish_reason(self) -> None:
        split = _gemini_sse_event('hel')
        events = [split[:8], split[8:], _gemini_sse_event(' lo', 'MAX_TOKENS')]
        chunks = list(iter_gemini_sse_as_openai_chunks(events, provider='gemini', model='m'))
        parsed = [_parse_sse_chunk(chunk) for chunk in chunks]
        self.assertEqual(parsed[0]['choices'][0]['delta']['content'], 'hel')
        self.assertEqual(parsed[1]['choices'][0]['delta']['content'], ' lo')
        self.assertEqual(parsed[2]['choices'][0]['finish_reason'], 'max_tokens')
        self.assertEqual(parsed[2]['choices'][0]['delta'], {})
        body = gemini_sse_to_openai_chat(
            [_gemini_sse_event('hel'), _gemini_sse_event(' lo', 'MAX_TOKENS')],
            provider='gemini',
            model='m',
        )
        self.assertEqual(json.loads(body.decode('utf-8'))['choices'][0]['message']['content'], 'hel lo')


def _gemini_sse_event(text: str, finish_reason: str | None = None) -> bytes:
    candidate: dict[str, object] = {'content': {'role': 'model', 'parts': [{'text': text}]}}
    if finish_reason is not None:
        candidate['finishReason'] = finish_reason
    payload = json.dumps({'candidates': [candidate]}, ensure_ascii=False, separators=(',', ':'))
    return f'data: {payload}\n\n'.encode('utf-8')


def _parse_sse_chunk(chunk: bytes) -> object:
    text = chunk.decode('utf-8')
    data = text.removeprefix('data: ').strip()
    if data == '[DONE]':
        return '[DONE]'
    return json.loads(data)
