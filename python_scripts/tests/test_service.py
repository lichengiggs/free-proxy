from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_scripts.health_store import load_health
from python_scripts.provider_errors import ProviderError
from python_scripts.service import ProxyService, ResolvedOpenAIRequest


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.timeouts: list[int] = []
        self.stream_calls: list[int] = []

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, body
        self.stream_calls.append(timeout)
        return 200, {}, iter([b''])

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        self.calls.append((method, url))
        self.timeouts.append(timeout)
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'ok-model', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


def _gemini_sse_event(text: str, finish_reason: str | None = None) -> bytes:
    candidate: dict[str, object] = {'content': {'role': 'model', 'parts': [{'text': text}]}}
    if finish_reason is not None:
        candidate['finishReason'] = finish_reason
    payload = json.dumps({'candidates': [candidate]}, ensure_ascii=False, separators=(',', ':'))
    return f'data: {payload}\n\n'.encode('utf-8')


class GeminiTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.timeouts: list[int] = []
        self.stream_calls = 0

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, body, timeout
        self.stream_calls += 1
        raise AssertionError('gemini chat_text and probe must not use stream_request')

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        self.urls.append(url)
        self.timeouts.append(timeout)
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode('utf-8')
        return 200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'gemini-ok'}]}}]}).encode('utf-8')


class GeminiSseTransport:
    def __init__(self) -> None:
        self.request_calls = 0
        self.stream_urls: list[str] = []
        self.headers: dict[str, str] | None = None
        self.body: bytes | None = None

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body, timeout
        self.request_calls += 1
        raise AssertionError('gemini stream chat must not call request()')

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, timeout
        self.stream_urls.append(url)
        self.headers = headers
        self.body = body
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            _gemini_sse_event('hel'),
            _gemini_sse_event('lo', 'STOP'),
        ])


class FallbackTransport:
    def __init__(self) -> None:
        self.chat_models: list[str] = []
        self.last_prompt: str = ''
        self.max_tokens: list[int] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}, {'id': 'model-b', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()

        payload = json.loads((body or b'{}').decode('utf-8'))
        model = str(payload.get('model', ''))
        self.chat_models.append(model)
        self.last_prompt = str(payload.get('messages', [{}])[0].get('content', ''))
        self.max_tokens.append(int(payload.get('max_tokens', 0) or 0))

        if model == 'model-a':
            return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class StreamTransport(FallbackTransport):
    def __init__(self) -> None:
        super().__init__()
        self.stream_payloads: list[dict[str, object]] = []

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
        self.stream_payloads.append(payload)
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"content":"ok"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class VerifyTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body, timeout
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'v-model', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class AuthFailTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body, timeout
        return 401, {}, json.dumps({'error': {'message': 'invalid api key'}}).encode()


class ListOkChatFailTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-can-list', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        return 429, {}, json.dumps({'error': {'message': 'rate limit'}}).encode()


class SslVerifyFailTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, url, headers, body, timeout
        raise ProviderError('网络连接失败: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1002)')


class TokenLimitRetryTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.max_tokens: list[int] = []
        self.prompts: list[str] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.max_tokens.append(int(payload.get('max_tokens', 0) or 0))
        self.prompts.append(str(payload.get('messages', [{}])[0].get('content', '')))
        self.calls += 1
        if self.calls == 1:
            return 400, {}, json.dumps({'error': {'message': 'maximum context length is 8192 tokens'}}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class RawTransport:
    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, timeout
        if method == 'GET' and url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'model-a', 'pricing': {'prompt': '0', 'completion': '0'}}]}).encode()
        payload = json.loads((body or b'{}').decode('utf-8'))
        self.last_payload = payload
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({'model': payload.get('model'), 'ok': True}).encode()

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
        self.last_payload = payload
        event = json.dumps({'choices': [{'index': 0, 'delta': {'content': 'ok'}, 'finish_reason': 'stop'}]}, separators=(',', ':')).encode('utf-8')
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: ' + event + b'\n\n',
            b'data: [DONE]\n\n',
        ])


class ChunkedStreamTransport(RawTransport):
    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        del method, url, headers, timeout
        self.last_payload = json.loads((body or b'{}').decode('utf-8'))
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class StreamHttpTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str] | None, bytes | None, int]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append((method, url, headers, body, timeout))
        del timeout
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode('utf-8')

    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
            b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ])


class JsonFallbackStreamTransport(StreamHttpTransport):
    def stream_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 30,
    ) -> tuple[int, dict[str, str], object]:
        self.requests.append((method, url, headers, body, timeout))
        return 200, {'Content-Type': 'application/json; charset=utf-8'}, iter([
            json.dumps({
                'id': 'chatcmpl-stream-json',
                'object': 'chat.completion',
                'created': 2,
                'model': 'model-a',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'answer-json'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
            }).encode('utf-8')
        ])


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_keys = [
            'OPENROUTER_API_KEY',
            'LONGCAT_API_KEY',
            'GEMINI_API_KEY',
            'OFOX_API_KEY',
            'SAMBANOVA_API_KEY',
        ]
        self.old_values = {key: os.environ.get(key) for key in self.env_keys}
        os.environ['OPENROUTER_API_KEY'] = 'test'
        self.tmp = tempfile.TemporaryDirectory()
        self.health_path = Path(self.tmp.name) / 'default-health.json'
        self.token_limit_path = Path(self.tmp.name) / 'default-token-limits.json'

    def tearDown(self) -> None:
        for key, value in self.old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def make_service(
        self,
        transport: object,
        *,
        dotenv_path: Path | None = None,
        health_path: Path | None = None,
        token_limit_path: Path | None = None,
        request_timeout_seconds: int = 12,
    ) -> ProxyService:
        return ProxyService(
            transport=transport,
            dotenv_path=dotenv_path,
            health_path=self.health_path if health_path is None else health_path,
            token_limit_path=self.token_limit_path if token_limit_path is None else token_limit_path,
            request_timeout_seconds=request_timeout_seconds,
        )

    def test_probe_returns_ok(self) -> None:
        service = self.make_service(FakeTransport())
        result = service.probe('openrouter', 'ok-model')
        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'ok')
        self.assertEqual(result.actual_model, 'ok-model')

    def test_request_timeout_is_propagated_to_adapter_transport(self) -> None:
        transport = FakeTransport()
        service = self.make_service(transport, request_timeout_seconds=7)
        service.probe('openrouter', 'ok-model')
        self.assertTrue(any(value == 7 for value in transport.timeouts))
        self.assertEqual(transport.stream_calls, [])

    def test_chat_is_strict_for_explicit_model(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.chat('openrouter', 'model-a', prompt='x' * 20000)

            self.assertFalse(result.ok)
            self.assertEqual(result.model, 'model-a')
            self.assertEqual(result.status, 429)
            self.assertEqual(result.category, 'rate_limit')
            self.assertEqual(result.actual_model, None)
            self.assertEqual(transport.chat_models[0], 'model-a')
            self.assertIn('...[内容已截断]...', transport.last_prompt)
            self.assertEqual(transport.max_tokens[0], 512)

    def test_stream_chat_ignores_stream_and_wraps_prompt_into_messages_for_openai_payloads(self) -> None:
        transport = RawTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.forward_direct_chat('openrouter', 'model-a', {'model': 'model-a', 'prompt': 'hello', 'stream': True})

            self.assertTrue(result.ok)
            chunks = list(result.stream_chunks or [])
            self.assertEqual(chunks[-1], b'data: [DONE]\n\n')
            self.assertIn(b'"content":"ok"', chunks[0])
            self.assertEqual(transport.last_payload and transport.last_payload.get('stream'), True)
            self.assertEqual(transport.last_payload and transport.last_payload.get('messages'), [{'role': 'user', 'content': 'hello'}])

    def test_probe_keeps_small_output_budget_for_non_thinking_models(self) -> None:
        transport = FallbackTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(transport=transport, health_path=Path(tmp) / 'health.json')
            result = service.probe('openrouter', 'model-a')

            self.assertFalse(result.ok)
            self.assertEqual(transport.chat_models, ['model-a'])
            self.assertEqual(transport.max_tokens[0], 32)

    def test_provider_key_status_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(VerifyTransport(), dotenv_path=env_path)

            before = service.provider_key_statuses()
            self.assertFalse(before['openrouter']['configured'])
            self.assertFalse(before['groq']['configured'])
            self.assertNotIn('longcat', before)

            service.save_provider_key('openrouter', 'sk-example-123456')
            service.save_provider_key('groq', 'groq-example-123456')
            after = service.provider_key_statuses()
            self.assertTrue(after['openrouter']['configured'])
            self.assertIn('***', after['openrouter']['masked'])
            self.assertTrue(after['groq']['configured'])
            self.assertEqual(after['groq']['env'], 'GROQ_API_KEY')
            self.assertNotIn('longcat', after)

    def test_save_and_load_preferred_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preferred_path = Path(tmp) / 'preferred-model.json'
            service = ProxyService(
                transport=VerifyTransport(),
                health_path=self.health_path,
                preferred_model_path=preferred_path,
                token_limit_path=self.token_limit_path,
            )

            result = service.save_preferred_model('groq', 'llama-3.1-8b-instant')
            self.assertTrue(result['ok'])
            self.assertEqual(service.preferred_model(), 'groq/llama-3.1-8b-instant')

    def test_verify_provider_key_and_recommended_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(VerifyTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertTrue(verify['ok'])
            self.assertEqual(verify['provider'], 'openrouter')

            recommended = service.recommended_models('openrouter')
            self.assertTrue(len(recommended) >= 1)

    def test_ofox_recommended_models_fall_back_to_single_free_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(AuthFailTransport(), dotenv_path=env_path)
            service.save_provider_key('ofox', 'sk-of-example-123456')

            recommended = service.recommended_models('ofox')
            self.assertEqual(recommended, ['z-ai/glm-4.7-flash:free'])

    def test_verify_provider_key_returns_error_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(AuthFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'auth')

    def test_verify_provider_key_fails_when_model_list_ok_but_not_callable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(ListOkChatFailTransport(), dotenv_path=env_path)
            service.save_provider_key('openrouter', 'sk-example-123456')

            verify = service.verify_provider_key('openrouter')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'rate_limit')
            self.assertTrue(bool(verify.get('suggestion')))

    def test_verify_provider_key_classifies_ssl_certificate_failure_as_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / '.env'
            service = self.make_service(SslVerifyFailTransport(), dotenv_path=env_path)
            service.save_provider_key('groq', 'groq-example-123456')

            verify = service.verify_provider_key('groq')
            self.assertFalse(verify['ok'])
            self.assertEqual(verify['category'], 'network')
            self.assertIn('检查网络', verify['suggestion'])

    def test_public_models_exposes_auto_alias_only(self) -> None:
        service = self.make_service(FakeTransport())
        models = service.public_models()
        ids = [item['id'] for item in models]
        self.assertEqual(ids, ['free-proxy/auto'])

    def test_service_exposes_openai_relay_accessor(self) -> None:
        service = self.make_service(FakeTransport())
        relay = service.openai_relay()
        self.assertIsNotNone(relay)

    def test_relay_health_updater_persists_cooldown_without_api_key(self) -> None:
        previous = os.environ.get('GROQ_API_KEY')
        os.environ['GROQ_API_KEY'] = 'test-secret-value'
        try:
            service = self.make_service(FakeTransport())
            relay = service.openai_relay()
            digest = relay.key_hash_loader('groq')
            self.assertEqual(len(digest), 64)
            self.assertNotIn('test-secret-value', digest)
            relay.health_updater(
                'groq',
                'llama-3.1-8b-instant',
                False,
                'auth',
                category='auth',
                cooldown_until=123456,
                scope='provider',
                key_hash=digest,
            )
            saved = load_health(service.health_path)
            entry = saved['groq/llama-3.1-8b-instant']
            self.assertEqual(entry['cooldown_until'], 123456)
            self.assertEqual(entry['scope'], 'provider')
            self.assertEqual(entry['category'], 'auth')
            self.assertEqual(entry['key_hash'], digest)
            self.assertNotIn('test-secret-value', json.dumps(saved))
        finally:
            if previous is None:
                os.environ.pop('GROQ_API_KEY', None)
            else:
                os.environ['GROQ_API_KEY'] = previous

    def test_execute_openai_target_returns_raw_forward_result_for_openai_provider(self) -> None:
        transport = RawTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored'})
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, 'openrouter')
        self.assertEqual(result.model, 'model-a')
        self.assertEqual(result.status, 200)
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(result.headers.get('Content-Type'), 'application/json; charset=utf-8')
        self.assertIs(transport.last_payload.get('stream') if transport.last_payload else None, True)
        parsed = json.loads(result.body)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'ok')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'stop')

    def test_forward_direct_chat_strips_local_provider_field_before_upstream_request(self) -> None:
        transport = RawTransport()
        service = self.make_service(transport)

        result = service.forward_direct_chat(
            'openrouter',
            'model-a',
            {'provider': 'openrouter', 'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]},
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(transport.last_payload)
        self.assertNotIn('provider', transport.last_payload or {})
        self.assertEqual(transport.last_payload and transport.last_payload.get('model'), 'model-a')

    def test_forward_direct_chat_strips_duplicate_provider_prefix_from_model_before_upstream_request(self) -> None:
        transport = RawTransport()
        service = self.make_service(transport)

        result = service.forward_direct_chat(
            'openrouter',
            'openrouter/stepfun/step-3.5-flash:free',
            {
                'provider': 'openrouter',
                'model': 'openrouter/stepfun/step-3.5-flash:free',
                'messages': [{'role': 'user', 'content': 'hello'}],
            },
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(transport.last_payload)
        self.assertEqual(transport.last_payload and transport.last_payload.get('model'), 'stepfun/step-3.5-flash:free')

    def test_forward_direct_chat_persists_successful_model_health(self) -> None:
        transport = RawTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(
                transport=transport,
                health_path=Path(tmp) / 'health.json',
                token_limit_path=self.token_limit_path,
            )

            result = service.forward_direct_chat(
                'openrouter',
                'model-a',
                {'provider': 'openrouter', 'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]},
            )

            self.assertTrue(result.ok)
            health = load_health(Path(tmp) / 'health.json')
            self.assertEqual(health['openrouter/model-a']['ok'], True)

    def test_execute_openai_target_ignores_stream_flag_for_openai_provider(self) -> None:
        transport = ChunkedStreamTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        with patch('python_scripts.service.get_model_capabilities', return_value={'streaming': False}):
            result = service.execute_openai_target(target, {'model': 'ignored', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertEqual(
            list(result.stream_chunks or []),
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n',
                b'data: [DONE]\n\n',
            ],
        )
        self.assertIs(transport.last_payload.get('stream') if transport.last_payload else None, True)

    def test_execute_openai_target_synthesizes_json_when_client_does_not_stream(self) -> None:
        transport = ChunkedStreamTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': False, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        self.assertIsNone(result.stream_chunks)
        self.assertIs(transport.last_payload.get('stream') if transport.last_payload else None, True)
        parsed = json.loads(result.body)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'answer-1')
        self.assertNotIn('think-1', parsed['choices'][0]['message']['content'])

    def test_execute_openai_target_uses_reasoning_when_sse_content_is_empty(self) -> None:
        class ReasoningOnlyTransport(ChunkedStreamTransport):
            def stream_request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], object]:
                del method, url, headers, timeout
                self.last_payload = json.loads((body or b'{}').decode('utf-8'))
                return 200, {'Content-Type': 'text/event-stream; charset=utf-8'}, iter([
                    b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-1"}}]}\n\n',
                    b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-2"},"finish_reason":"length"}]}\n\n',
                    b'data: [DONE]\n\n',
                ])

        transport = ReasoningOnlyTransport()
        service = self.make_service(transport)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        result = service.execute_openai_target(target, {'model': 'ignored', 'stream': False, 'messages': [{'role': 'user', 'content': 'hello'}]})

        self.assertTrue(result.ok)
        parsed = json.loads(result.body)
        self.assertEqual(parsed['choices'][0]['message']['content'], 'think-1think-2')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'length')

    def test_gemini_probe_and_chat_text_stay_on_generate_content(self) -> None:
        os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
        transport = GeminiTransport()
        service = self.make_service(transport, request_timeout_seconds=7)
        self.assertEqual(service.provider_adapter('gemini').chat_text('models/gemini-2.0-flash', 'ok'), 'gemini-ok')
        result = service.probe('gemini', 'gemini-2.0-flash')

        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'gemini-ok')
        self.assertEqual(transport.stream_calls, 0)
        self.assertEqual(transport.timeouts, [7, 7])
        self.assertGreaterEqual(len(transport.urls), 2)
        for url in transport.urls:
            path = url.split('?', 1)[0]
            self.assertTrue(path.endswith(':generateContent'))
            self.assertFalse(path.endswith(':streamGenerateContent'))

    def test_forward_direct_chat_without_stream_keeps_gemini_on_generate_content(self) -> None:
        os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
        transport = GeminiTransport()
        service = self.make_service(transport)
        result = service.forward_direct_chat(
            'gemini',
            'gemini-2.0-flash',
            {'messages': [{'role': 'user', 'content': 'hello'}]},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'gemini-ok')
        self.assertIsNone(result.stream_chunks)
        self.assertEqual(transport.stream_calls, 0)
        self.assertTrue(any(url.split('?', 1)[0].endswith(':generateContent') for url in transport.urls))

    def test_forward_direct_chat_streams_gemini_sse(self) -> None:
        os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
        transport = GeminiSseTransport()
        service = self.make_service(transport)
        result = service.forward_direct_chat(
            'gemini',
            'gemini-2.0-flash',
            {'model': 'gemini-2.0-flash', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
        )

        self.assertTrue(result.ok)
        self.assertIsNone(result.content)
        self.assertEqual(transport.request_calls, 0)
        self.assertIn('text/event-stream', result.headers.get('Content-Type', ''))
        url = transport.stream_urls[0]
        path, _, query = url.partition('?')
        self.assertTrue(path.endswith('/models/gemini-2.0-flash:streamGenerateContent'))
        self.assertEqual(query, 'alt=sse')
        self.assertNotIn('test-gemini-key', url)
        self.assertEqual((transport.headers or {}).get('x-goog-api-key'), 'test-gemini-key')
        upstream = json.loads(transport.body or b'{}')
        self.assertEqual(upstream['contents'], [{'role': 'user', 'parts': [{'text': 'hello'}]}])
        self.assertEqual(upstream['generationConfig']['temperature'], 0)
        self.assertEqual(upstream['generationConfig']['maxOutputTokens'], 1024)
        self.assertNotIn('tools', upstream)
        text = b''.join(list(result.stream_chunks or [])).decode('utf-8')
        self.assertLess(text.index('"content":"hel"'), text.index('"content":"lo"'))
        self.assertLess(text.index('"content":"lo"'), text.index('"finish_reason":"stop"'))
        self.assertLess(text.index('"finish_reason":"stop"'), text.index('data: [DONE]'))

    def test_chat_retries_once_after_token_limit_and_persists_learned_limit(self) -> None:
        transport = TokenLimitRetryTransport()
        with tempfile.TemporaryDirectory() as tmp:
            service = ProxyService(
                transport=transport,
                health_path=Path(tmp) / 'health.json',
                token_limit_path=Path(tmp) / 'token-limits.json',
            )
            result = service.chat('openrouter', 'model-a', prompt='x' * 60000, max_output_tokens=4096)

            self.assertTrue(result.ok)
            self.assertEqual(transport.calls, 2)
            self.assertLess(transport.max_tokens[-1], transport.max_tokens[0])
            token_limits = json.loads((Path(tmp) / 'token-limits.json').read_text(encoding='utf-8'))
            self.assertEqual(token_limits['openrouter/model-a']['input_tokens_limit'], 8192)

    def test_provider_adapter_logs_upstream_request_and_response_safely(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []

        def debug_log(event: str, **fields: object) -> None:
            logs.append((event, fields))

        transport = RawTransport()
        service = ProxyService(transport=transport, debug_log=debug_log)
        target = ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None)
        service.execute_openai_target(target, {'model': 'model-a', 'messages': [{'role': 'user', 'content': 'hello'}]})

        events = [event for event, _ in logs]
        self.assertIn('upstream_request', events)
        self.assertIn('upstream_response', events)
        first = logs[0][1]
        self.assertEqual(first['auth_present'], True)
        self.assertEqual(first['auth_scheme'], 'Bearer')
        self.assertNotIn('Authorization', str(logs))
        self.assertNotIn('hello', str(logs))

    def test_execute_openai_target_logs_missing_provider_as_request_failure(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []

        def debug_log(event: str, **fields: object) -> None:
            logs.append((event, fields))

        class FailTransport(RawTransport):
            def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
                del method, headers, body, timeout
                return 403, {'cf-ray': 'ray-1'}, b'{"error":{"message":"error code: 1010"}}'

            def stream_request(
                self,
                method: str,
                url: str,
                headers: dict[str, str] | None = None,
                body: bytes | None = None,
                timeout: int = 30,
            ) -> tuple[int, dict[str, str], object]:
                del method, url, headers, body, timeout
                return 403, {'cf-ray': 'ray-1'}, iter([b'{"error":{"message":"error code: 1010"}}'])

        service = ProxyService(transport=FailTransport(), debug_log=debug_log)
        result = service.execute_openai_target(ResolvedOpenAIRequest(provider='openrouter', model='model-a', alias=None), {'model': 'model-a'})

        self.assertFalse(result.ok)
        self.assertTrue(any(event == 'request_failed' for event, _ in logs))
