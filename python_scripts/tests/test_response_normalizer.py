from __future__ import annotations

import json
import unittest

from python_scripts.response_normalizer import normalize_json_success, normalize_provider_response


class ResponseNormalizerTests(unittest.TestCase):
    def test_keeps_json_success_as_openai_json(self) -> None:
        response = normalize_json_success(provider='openrouter', model='m1', content='hello')
        parsed = json.loads(response.body.decode('utf-8'))
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello')

    def test_sse_termination_contains_done(self) -> None:
        from python_scripts.response_normalizer import wrap_openai_body_as_sse
        body = json.dumps({
            'choices': [{'message': {'content': 'hi', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        chunks = list(wrap_openai_body_as_sse(provider='groq', fallback_model='groq/llama-3.1-8b-instant', body=body))
        last = chunks[-1]
        self.assertIn(b'[DONE]', last)

    def test_sse_chunks_are_valid_json_lines(self) -> None:
        from python_scripts.response_normalizer import wrap_openai_body_as_sse
        body = json.dumps({
            'id': 'test-123',
            'model': 'groq/llama-3.1-8b-instant',
            'choices': [{'message': {'content': 'hello', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        chunks = list(wrap_openai_body_as_sse(provider='groq', fallback_model='groq/llama-3.1-8b-instant', body=body))
        for chunk in chunks:
            line = chunk.decode('utf-8').strip()
            self.assertTrue(line.startswith('data: '))
            payload = line[6:]
            if payload != '[DONE]':
                json.loads(payload)

    def test_normalize_provider_response_stream_false(self) -> None:
        body = json.dumps({
            'choices': [{'message': {'content': 'ok', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        resp = normalize_provider_response(provider='groq', model='llama-3.1-8b-instant', body=body, stream=False)
        self.assertEqual(resp.status, 200)
        self.assertIn(b'application/json', resp.headers.get('Content-Type', '').encode())
        parsed = json.loads(resp.body)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'ok')

    def test_normalize_provider_response_stream_true(self) -> None:
        body = json.dumps({
            'choices': [{'message': {'content': 'ok', 'role': 'assistant'}, 'finish_reason': 'stop'}]
        }).encode()
        resp = normalize_provider_response(provider='groq', model='llama-3.1-8b-instant', body=body, stream=True)
        self.assertEqual(resp.status, 200)
        self.assertIn(b'text/event-stream', resp.headers.get('Content-Type', '').encode())
        self.assertIsNotNone(resp.stream_chunks)
