from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from python_scripts.server import ApiHandler


@dataclass
class FakeResult:
    ok: bool
    actual_model: str | None = None
    content: str | None = None
    error: str | None = None
    category: str | None = None
    status: int | None = None
    suggestion: str | None = None


@dataclass
class FakeRawResult:
    ok: bool
    status: int
    headers: dict[str, str]
    body: bytes
    error: str | None = None
    category: str | None = None
    suggestion: str | None = None


class FakeService:
    def __init__(self) -> None:
        self.saved_keys: list[tuple[str, str]] = []

    def provider_key_statuses(self):
        return {
            'openrouter': {'configured': True, 'masked': 'sk-o***1234', 'env': 'OPENROUTER_API_KEY'},
            'longcat': {'configured': False, 'masked': '', 'env': 'LONGCAT_API_KEY'},
        }

    def available_providers(self):
        return ['openrouter']

    def list_models(self, provider: str):
        return ['m1'] if provider == 'openrouter' else []

    def recommended_models(self, provider: str, requested_model: str | None = None):
        ordered = []
        if requested_model:
            ordered.append(requested_model)
        return ordered + ['m1', 'm2']

    def public_models(self):
        return [
            {'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'},
            {'id': 'free-proxy/coding', 'object': 'model', 'owned_by': 'free-proxy'},
        ]

    def resolve_alias_candidates(self, alias: str):
        if alias == 'coding':
            return [('openrouter', 'coding')]
        return [('openrouter', 'auto')]

    def verify_provider_key(self, provider: str):
        return {'ok': True, 'provider': provider, 'verified_model': 'm1'}

    def save_provider_key(self, provider: str, api_key: str):
        self.saved_keys.append((provider, api_key))
        return {'ok': True, 'provider': provider, 'masked': 'sk-o***1234'}

    def probe(self, provider: str, model: str):
        return FakeResult(provider == 'openrouter', actual_model=model, content='ok', error='fail', category='server', status=500, suggestion='retry')

    def chat(self, provider: str, model: str, prompt: str):
        if provider == 'openrouter':
            return FakeResult(ok=True, actual_model=model, content=f'echo:{prompt}')
        return FakeResult(ok=False, error='provider not available', category='auth', status=401, suggestion='set key')

    def chat_completions_raw(self, provider: str, model: str, payload: dict):
        if provider != 'openrouter':
            return FakeRawResult(ok=False, status=401, headers={}, body=b'', error='provider not available', category='auth', suggestion='set key')
        if payload.get('stream'):
            body = (
                'data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"echo:hello"},"index":0}]}\n\n'
                'data: [DONE]\n\n'
            ).encode('utf-8')
            return FakeRawResult(ok=True, status=200, headers={'Content-Type': 'text/event-stream; charset=utf-8'}, body=body)
        body = json.dumps(
            {
                'id': 'chatcmpl-test',
                'object': 'chat.completion',
                'model': f'{provider}/{model}',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'echo:hello'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
            }
        ).encode('utf-8')
        return FakeRawResult(ok=True, status=200, headers={'Content-Type': 'application/json; charset=utf-8'}, body=body)


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_service = ApiHandler.service
        self._old_openclaw_test_dir = os.environ.get('OPENCLAW_TEST_DIR')
        self._old_opencode_test_dir = os.environ.get('OPENCODE_TEST_DIR')
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['OPENCLAW_TEST_DIR'] = self.tmp.name
        ApiHandler.service = FakeService()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ApiHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        ApiHandler.service = self._old_service
        if self._old_openclaw_test_dir is None:
            os.environ.pop('OPENCLAW_TEST_DIR', None)
        else:
            os.environ['OPENCLAW_TEST_DIR'] = self._old_openclaw_test_dir
        if self._old_opencode_test_dir is None:
            os.environ.pop('OPENCODE_TEST_DIR', None)
        else:
            os.environ['OPENCODE_TEST_DIR'] = self._old_opencode_test_dir
        self.tmp.cleanup()

    def _request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = b''
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode('utf-8')
        conn.close()
        return resp.status, json.loads(data) if data else {}

    def _request_raw(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict[str, str], str]:
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = b''
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        data = resp.read().decode('utf-8')
        conn.close()
        return status, resp_headers, data

    def test_index_page_uses_new_validation_flow_and_updated_examples(self) -> None:
        status, headers, body = self._request_raw('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers.get('content-type', ''))
        self.assertIn('free-proxy 控制台', body)
        self.assertIn('3. 模型验证', body)
        self.assertIn('探测模型', body)
        self.assertIn('http://127.0.0.1:8765/v1', body)
        self.assertNotIn('按 TypeScript 版的交互方式重做', body)
        self.assertNotIn('查看模型', body)
        self.assertNotIn('聊天测试台', body)
        self.assertNotIn('诊断面板', body)
        self.assertNotIn('等待聊天结果', body)

    def test_health_route(self) -> None:
        status, body = self._request('GET', '/health')
        self.assertEqual(status, 200)
        self.assertEqual(body, {'ok': True})

    def test_provider_keys_status_route(self) -> None:
        status, body = self._request('GET', '/api/provider-keys')
        self.assertEqual(status, 200)
        self.assertTrue(body['openrouter']['configured'])

    def test_openai_models_route_returns_public_aliases(self) -> None:
        status, body = self._request('GET', '/v1/models')
        self.assertEqual(status, 200)
        self.assertEqual(body['object'], 'list')
        ids = [item['id'] for item in body['data']]
        self.assertIn('free-proxy/auto', ids)
        self.assertIn('free-proxy/coding', ids)

    def test_recommended_models_route_accepts_requested_model_query(self) -> None:
        status, body = self._request('GET', '/api/providers/openrouter/models/recommended?model=my-picked-model')
        self.assertEqual(status, 200)
        self.assertEqual(body['provider'], 'openrouter')
        self.assertEqual(body['items'][0], 'my-picked-model')

    def test_save_provider_key_requires_api_key(self) -> None:
        status, body = self._request('POST', '/api/provider-keys/openrouter', {'api_key': ''})
        self.assertEqual(status, 400)
        self.assertIn('missing api_key', body['error'])

    def test_openai_chat_completion_accepts_model_with_provider_prefix(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['object'], 'chat.completion')
        self.assertEqual(body['model'], 'openrouter/m1')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')
        self.assertEqual(body['choices'][0]['message']['role'], 'assistant')

    def test_openai_chat_completion_can_fallback_to_default_provider_when_provider_missing(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['model'], 'openrouter/m1')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')

    def test_openai_chat_completion_supports_auto_model_for_newbies(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['model'], 'openrouter/auto')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')

    def test_openai_chat_completion_supports_coding_alias_for_agents(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'model': 'free-proxy/coding', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body['model'], 'openrouter/coding')
        self.assertEqual(body['choices'][0]['message']['content'], 'echo:hello')

    def test_openai_chat_completion_stream_mode_returns_sse(self) -> None:
        status, headers, body = self._request_raw(
            'POST',
            '/v1/chat/completions',
            {'model': 'openrouter/m1', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(status, 200)
        self.assertIn('text/event-stream', headers.get('content-type', ''))
        self.assertIn('data: [DONE]', body)
        self.assertIn('chat.completion.chunk', body)

    def test_openai_chat_completion_returns_openai_style_error_when_model_missing(self) -> None:
        status, body = self._request(
            'POST',
            '/v1/chat/completions',
            {'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 400)
        self.assertIn('error', body)
        self.assertIn('missing model', body['error']['message'])

    def test_legacy_chat_completion_route_keeps_old_custom_shape(self) -> None:
        status, body = self._request(
            'POST',
            '/chat/completions',
            {'provider': 'openrouter', 'model': 'm1', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(body['actual_model'], 'm1')
        self.assertEqual(body['content'], 'echo:hello')

    def test_configure_openclaw_rejects_invalid_mode(self) -> None:
        status, body = self._request('POST', '/api/configure-openclaw', {'mode': 'invalid'})
        self.assertEqual(status, 400)
        self.assertFalse(body['success'])

    def test_configure_opencode_writes_free_proxy_provider(self) -> None:
        os.environ['OPENCODE_TEST_DIR'] = self.tmp.name
        status, body = self._request('POST', '/api/configure-opencode', {})
        self.assertEqual(status, 200)
        self.assertTrue(body['success'])

        content = json.loads(Path(self.tmp.name, 'opencode.json').read_text(encoding='utf-8'))
        provider = content['provider']['free-proxy']
        self.assertEqual(provider['options']['baseURL'], 'http://localhost:8765/v1')
        self.assertIn('coding', provider['models'])


if __name__ == '__main__':
    unittest.main()
