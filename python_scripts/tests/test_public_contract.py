"""Public behavior locked by the agent pipeline.

The pipeline refuses a merge when this file differs from the base branch.
Change it in a human commit when the public behavior itself changes.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO

import httpx
from fastapi.testclient import TestClient

from python_scripts.provider_catalog import PROVIDERS, get_provider
from python_scripts.provider_errors import ProviderError
from python_scripts.service import ProxyService
from python_scripts.server_fastapi import app

ROOT = Path(__file__).resolve().parents[2]
_SUCCESS_SSE = (
    b'data: {"choices":[{"index":0,"delta":{"content":"hello-contract"}}]}\n\n'
    b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
    b'data: [DONE]\n\n'
)


class _RecordingTransport:
    def __init__(self, *, fail_first_stream: bool = False, break_first_stream: bool = False) -> None:
        self.fail_first_stream = fail_first_stream
        self.break_first_stream = break_first_stream
        self.probe_max_tokens: list[int] = []
        self.chat_max_tokens: list[int] = []
        self.stream_calls = 0
        self.chunks_pulled = 0

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.split('?', 1)[0].endswith('/models'):
            return 200, {'Content-Type': 'application/json'}, json.dumps({'data': [{'id': 'listed-model'}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        model = str(payload.get('model', ''))
        self.probe_max_tokens.append(int(payload.get('max_tokens', 0) or 0))
        if model == 'missing-model':
            return 401, {'Content-Type': 'application/json'}, json.dumps({'error': {'message': 'invalid api key'}}).encode()
        return 200, {'Content-Type': 'application/json'}, json.dumps({'choices': [{'message': {'content': 'probe-ok'}}]}).encode()

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, timeout
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.chat_max_tokens.append(int(payload.get('max_tokens', 0) or 0))
        self.stream_calls += 1
        if self.fail_first_stream and self.stream_calls == 1:
            return 429, {'Content-Type': 'application/json'}, iter([b'{"error":{"message":"rate limit"}}'])
        if self.break_first_stream and self.stream_calls == 1:
            def broken() -> object:
                self.chunks_pulled += 1
                yield _SUCCESS_SSE.split(b'data: [DONE]')[0]
                self.chunks_pulled += 1
                raise RuntimeError('upstream closed after the first chunk')

            return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, broken()
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([_SUCCESS_SSE])


class _ContractCase(unittest.TestCase):
    def setUp(self) -> None:
        self.env_keys = [provider.api_key_env for provider in PROVIDERS]
        self.env_keys.extend(['FREE_PROXY_TEST_UPSTREAM', 'FREE_PROXY_TEST_STATE_DIR'])
        self.old_env = {key: os.environ.get(key) for key in self.env_keys}
        for key in self.env_keys:
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        import python_scripts.server_fastapi as server

        self._server = server
        self._old_service = server._service
        self.transport = _RecordingTransport()
        self._install()

    def tearDown(self) -> None:
        self._server._service = self._old_service
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _install(self, transport: _RecordingTransport | None = None) -> ProxyService:
        dotenv = Path(self.tmp.name) / 'blank.env'
        dotenv.write_text('', encoding='utf-8')
        service = ProxyService(
            transport=transport or self.transport,
            dotenv_path=dotenv,
            health_path=Path(self.tmp.name) / 'health.json',
            preferred_model_path=Path(self.tmp.name) / 'preferred.json',
            token_limit_path=Path(self.tmp.name) / 'limits.json',
        )
        self._server._service = service
        return service

    def _enable(self, *names: str) -> None:
        for name in names:
            os.environ[get_provider(name).api_key_env] = f'test-{name}-key'


class PublicContractTests(_ContractCase):
    def test_public_models_lists_auto(self) -> None:
        response = TestClient(app).get('/v1/models')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'object': 'list', 'data': [{'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'}]},
        )

    def test_public_aliases_return_openai_json_and_sse(self) -> None:
        self._enable('groq')
        client = TestClient(app)
        for model in ('auto', 'free-proxy/auto', 'free_proxy/auto'):
            with self.subTest(model=model):
                response = client.post(
                    '/v1/chat/completions',
                    json={'model': model, 'messages': [{'role': 'user', 'content': 'hello'}]},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn('application/json', response.headers.get('content-type', ''))
                body = response.json()
                self.assertEqual(body['object'], 'chat.completion')
                self.assertEqual(body['choices'][0]['message']['content'], 'hello-contract')
                self.assertEqual(body['choices'][0]['finish_reason'], 'stop')

        streamed = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )
        self.assertEqual(streamed.status_code, 200)
        self.assertIn('text/event-stream', streamed.headers.get('content-type', ''))
        self.assertIn('hello-contract', streamed.text)
        self.assertIn('data: [DONE]', streamed.text)
        self.assertLess(streamed.text.index('hello-contract'), streamed.text.index('data: [DONE]'))

    def test_public_coding_alias_is_deprecated(self) -> None:
        client = TestClient(app)
        for model in ('coding', 'free-proxy/coding', 'free_proxy/coding'):
            with self.subTest(model=model):
                response = client.post(
                    '/v1/chat/completions',
                    json={'model': model, 'messages': [{'role': 'user', 'content': 'hello'}]},
                )
                self.assertEqual(response.status_code, 400)
                error = response.json()['error']
                self.assertEqual(error['code'], 'model_deprecated')
                self.assertIn('free-proxy/auto', error['message'])

    def test_public_rejects_unknown_model_and_empty_messages(self) -> None:
        client = TestClient(app)
        unknown = client.post('/v1/chat/completions', json={'model': 'gpt-4', 'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()['error']['message'], "model must be 'free-proxy/auto'")
        empty = client.post('/v1/chat/completions', json={'model': 'free-proxy/auto', 'messages': []})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.json()['error']['message'], 'messages must not be empty')

    def test_public_probe_budget_stays_smaller_than_chat(self) -> None:
        self._enable('groq')
        client = TestClient(app)
        probe = client.post('/providers/groq/probe', json={'model': 'llama-3.1-8b-instant'})
        self.assertEqual(probe.status_code, 200)
        self.assertEqual(probe.json()['content'], 'probe-ok')
        chat = client.post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(self.transport.probe_max_tokens, [32])
        self.assertGreaterEqual(self.transport.chat_max_tokens[0], 256)
        self.assertGreater(self.transport.chat_max_tokens[0], self.transport.probe_max_tokens[0])

    def test_public_fallback_tries_next_provider(self) -> None:
        self._enable('openrouter', 'groq')
        self.transport.fail_first_stream = True
        response = TestClient(app).post(
            '/v1/chat/completions',
            json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['choices'][0]['message']['content'], 'hello-contract')
        self.assertGreaterEqual(self.transport.stream_calls, 2)

    def test_public_stream_does_not_switch_after_first_chunk(self) -> None:
        self._enable('openrouter', 'groq')
        self.transport.break_first_stream = True
        with self.assertRaises(RuntimeError) as caught:
            TestClient(app).post(
                '/v1/chat/completions',
                json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
            )
        self.assertIn('upstream closed', str(caught.exception))
        self.assertGreaterEqual(self.transport.chunks_pulled, 1)
        self.assertEqual(self.transport.stream_calls, 1)

    def test_console_journey_probe_chat_and_diagnostics(self) -> None:
        self._enable('groq')
        client = TestClient(app)
        page = client.get('/')
        self.assertEqual(page.status_code, 200)
        for label in ('diagnosticsBox', '探测模型', '动作:', 'Provider:', 'Model:', '错误:', '分类:', 'HTTP:', '建议:'):
            self.assertIn(label, page.text)

        probe = client.post('/providers/groq/probe', json={'model': 'llama-3.1-8b-instant'})
        self.assertEqual(probe.status_code, 200)
        probed = probe.json()
        self.assertTrue(probed['ok'])
        self.assertEqual(probed['provider'], 'groq')
        self.assertEqual(probed['model'], 'llama-3.1-8b-instant')
        self.assertEqual(probed['content'], 'probe-ok')

        failed = client.post('/providers/groq/probe', json={'model': 'missing-model'})
        self.assertEqual(failed.status_code, 400)
        failure = failed.json()
        self.assertFalse(failure['ok'])
        self.assertEqual(failure['provider'], 'groq')
        self.assertEqual(failure['model'], 'missing-model')
        self.assertEqual(failure['category'], 'auth')
        self.assertEqual(failure['status'], 401)
        self.assertTrue(failure['error'])
        self.assertTrue(failure['suggestion'])

        streamed = client.post(
            '/chat/completions',
            json={'provider': 'groq', 'model': 'llama-3.1-8b-instant', 'prompt': 'hello', 'stream': True},
        )
        self.assertEqual(streamed.status_code, 200)
        self.assertIn('text/event-stream', streamed.headers.get('content-type', ''))
        self.assertIn('hello-contract', streamed.text)
        self.assertIn('data: [DONE]', streamed.text)

    def test_public_test_upstream_stays_on_loopback(self) -> None:
        os.environ['FREE_PROXY_TEST_UPSTREAM'] = 'https://example.com/v1'
        with self.assertRaises(ProviderError):
            get_provider('groq')
        os.environ['FREE_PROXY_TEST_UPSTREAM'] = 'http://example.com:9'
        with self.assertRaises(ProviderError):
            get_provider('groq')
        os.environ.pop('FREE_PROXY_TEST_UPSTREAM', None)
        self.assertNotIn('127.0.0.1', get_provider('groq').base_url)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split('?', 1)[0]
        if not path.endswith('/models'):
            self.send_error(404)
            return
        body = json.dumps({'data': [{'id': 'llama-3.1-8b-instant'}]}).encode()
        self._write(200, 'application/json', body)

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', '0') or '0')
        self.rfile.read(length)
        path = self.path.split('?', 1)[0]
        if not path.endswith('/chat/completions'):
            self.send_error(404)
            return
        body = (
            b'data: {"choices":[{"index":0,"delta":{"content":"pong"}}]}\n\n'
            b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n'
        )
        self._write(200, 'text/event-stream; charset=utf-8', body)

    def _write(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args


class ProcessStreamContractTests(unittest.TestCase):
    def test_process_stream_reaches_done(self) -> None:
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), _UpstreamHandler)
        upstream_port = int(upstream.server_address[1])
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        state = tempfile.TemporaryDirectory()
        Path(state.name, '.env').write_text('GROQ_API_KEY=test-contract-key\n', encoding='utf-8')
        port = _free_port()
        stderr = tempfile.TemporaryFile()
        env = os.environ.copy()
        for provider in PROVIDERS:
            env.pop(provider.api_key_env, None)
        for key in ('ALL_PROXY', 'all_proxy'):
            env.pop(key, None)
        env.update(
            {
                'FREE_PROXY_TEST_UPSTREAM': f'http://127.0.0.1:{upstream_port}',
                'FREE_PROXY_TEST_STATE_DIR': state.name,
                'http_proxy': 'http://127.0.0.1:9',
                'https_proxy': 'http://127.0.0.1:9',
                'HTTP_PROXY': 'http://127.0.0.1:9',
                'HTTPS_PROXY': 'http://127.0.0.1:9',
                'NO_PROXY': '127.0.0.1,localhost',
                'no_proxy': '127.0.0.1,localhost',
                'PYTHONUNBUFFERED': '1',
            }
        )
        proc = subprocess.Popen(
            [sys.executable, '-m', 'python_scripts.cli', 'serve', '--port', str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
        old_proxy = {key: os.environ.get(key) for key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy')}
        try:
            self._wait_until_ready(proc, port, stderr)
            for key in ('ALL_PROXY', 'all_proxy'):
                os.environ.pop(key, None)
            os.environ.update(
                {
                    'http_proxy': 'http://127.0.0.1:9',
                    'https_proxy': 'http://127.0.0.1:9',
                    'HTTP_PROXY': 'http://127.0.0.1:9',
                    'HTTPS_PROXY': 'http://127.0.0.1:9',
                    'NO_PROXY': '127.0.0.1,localhost',
                    'no_proxy': '127.0.0.1,localhost',
                }
            )
            with httpx.Client(trust_env=True, timeout=20) as client:
                with client.stream(
                    'POST',
                    f'http://127.0.0.1:{port}/v1/chat/completions',
                    json={'model': 'free-proxy/auto', 'messages': [{'role': 'user', 'content': 'ping'}], 'stream': True},
                ) as response:
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        chunks.extend(chunk)
                    status = response.status_code
            self.assertEqual(status, 200)
            self.assertIn(b'pong', chunks)
            self.assertIn(b'data: [DONE]', chunks)
            self.assertLess(chunks.index(b'pong'), chunks.index(b'data: [DONE]'))
            self.assertIsNone(proc.poll())
        finally:
            for key, value in old_proxy.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)
            stderr.close()
            state.cleanup()

    def _wait_until_ready(self, proc: subprocess.Popen[bytes], port: int, stderr: BinaryIO) -> None:
        deadline = time.time() + 30
        last_error = ''
        while time.time() < deadline:
            if proc.poll() is not None:
                stderr.seek(0)
                raise AssertionError(f'serve exited {proc.returncode}: {stderr.read().decode("utf-8", errors="ignore")}')
            try:
                response = httpx.get(f'http://127.0.0.1:{port}/health', timeout=0.5, trust_env=False)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                time.sleep(0.2)
                continue
            if response.status_code == 200:
                return
            last_error = f'status {response.status_code}'
            time.sleep(0.2)
        stderr.seek(0)
        detail = stderr.read().decode('utf-8', errors='ignore')
        raise AssertionError(f'serve did not become ready: {last_error}\n{detail}')
