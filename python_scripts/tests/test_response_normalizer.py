from __future__ import annotations

import json
import unittest

from python_scripts.response_normalizer import normalize_json_success, normalize_provider_response, synthesize_openai_json_from_sse


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

    def test_synthesize_prefers_content_over_reasoning_and_keeps_last_finish_reason(self) -> None:
        raw = synthesize_openai_json_from_sse(
            [
                b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-1"},"finish_reason":"length"}]}\n\n',
                b'data: {"choi',
                b'ces":[{"index":0,"delta":{"content":"answer-1"},"finish_reason":"stop"}]}\n\n',
                b'data: not-json\n\n',
                b'data: [DONE]\n\n',
            ],
            provider='groq',
            model='llama',
        )
        parsed = json.loads(raw)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'answer-1')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'stop')
        self.assertNotIn('think-1', parsed['choices'][0]['message']['content'])

    def test_synthesize_concatenates_reasoning_when_content_is_empty(self) -> None:
        raw = synthesize_openai_json_from_sse(
            [
                b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-1"}}]}\n\n',
                b'data: {"choices":[{"index":0,"delta":{"content":""},"finish_reason":null}]}\n\n',
                b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-2"},"finish_reason":"length"}]}\n\n',
                b'data: [DONE]\n\n',
            ],
            provider='amd',
            model='Qwen3.8-27B',
        )
        parsed = json.loads(raw)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'think-1think-2')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'length')
