from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from python_scripts.fallback_policy import QUOTA_COOLDOWN_SECONDS
from python_scripts.openai_relay import OpenAIRelay
from python_scripts.provider_errors import ProviderError
from python_scripts.request_normalizer import ChatRequest
from python_scripts.token_policy import response_token_budget


def _gemini_sse_event(text: str, finish_reason: str | None = None) -> bytes:
    candidate: dict[str, object] = {'content': {'role': 'model', 'parts': [{'text': text}]}}
    if finish_reason is not None:
        candidate['finishReason'] = finish_reason
    payload = json.dumps({'candidates': [candidate]}, ensure_ascii=False, separators=(',', ':'))
    return f'data: {payload}\n\n'.encode('utf-8')


def _gemini_chat_request(stream: bool) -> ChatRequest:
    return ChatRequest(
        'free-proxy/auto',
        'gemini/gemini-2.0-flash',
        [{'role': 'user', 'content': 'hi'}],
        stream,
        None,
        None,
        {
            'model': 'free-proxy/auto',
            'requested_model': 'gemini/gemini-2.0-flash',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': stream,
        },
    )


def _parse_sse_chunk(chunk: bytes) -> object:
    data = chunk.decode('utf-8').removeprefix('data: ').strip()
    if data == '[DONE]':
        return '[DONE]'
    return json.loads(data)


class FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def forward_chat(self, payload: dict[str, object]):
        self.calls += 1
        if self.calls == 1:
            return type('AdapterResponse', (), {'status': 429, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"rate limit"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
        return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()


class OpenAIRelayTests(unittest.TestCase):
    def test_relay_falls_back_to_second_candidate(self) -> None:
        adapter = FakeAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertIsNotNone(response.body)

    def test_relay_uses_provider_listed_model_after_static_default_fails(self) -> None:
        class ProviderAwareAdapter:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []
                self.list_calls: list[str] = []

            def forward_chat(self, payload: dict[str, object]):
                self.payloads.append(payload)
                model = str(payload.get('model', ''))
                if model == 'openrouter/auto:free':
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"server error"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-listed"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

            def list_models(self) -> list[str]:
                self.list_calls.append('called')
                return ['qwen/qwen3.6-plus-preview:free']

        adapter = ProviderAwareAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertEqual(adapter.payloads[0]['model'], 'openrouter/auto:free')
        self.assertEqual(adapter.payloads[1]['model'], 'qwen/qwen3.6-plus-preview:free')

    def test_relay_loads_listed_models_lazily_after_provider_failure(self) -> None:
        class LazyAdapter:
            def __init__(self, provider: str, tracker: dict[str, list[str]]) -> None:
                self.provider = provider
                self.tracker = tracker

            def forward_chat(self, payload: dict[str, object]):
                self.tracker['payloads'].append(f'{self.provider}:{payload.get("model")}')
                if self.provider == 'openrouter' and payload.get('model') == 'openrouter/auto:free':
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"server error"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-listed"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

            def list_models(self) -> list[str]:
                self.tracker['lists'].append(self.provider)
                if self.provider == 'openrouter':
                    return ['qwen/qwen3.6-plus-preview:free']
                return ['llama-3.1-8b-instant']

        tracker = {'payloads': [], 'lists': []}
        checked_at = int(time.time())
        relay = OpenAIRelay(
            adapter_factory=lambda provider: LazyAdapter(provider, tracker),
            health_loader=lambda: {'openrouter/openrouter/auto:free': {'ok': True, 'checked_at': checked_at}},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        self.assertEqual(tracker['lists'], ['openrouter'])
        self.assertEqual(
            tracker['payloads'][:2],
            ['openrouter:openrouter/auto:free', 'openrouter:qwen/qwen3.6-plus-preview:free'],
        )

    def test_relay_returns_json_when_stream_is_not_requested(self) -> None:
        class StreamingAdapter:
            def forward_chat(self, payload: dict[str, object]):
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

            def list_models(self) -> list[str]:
                return ['qwen/qwen3.6-plus-preview:free']

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StreamingAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        self.assertIsNone(response.stream_chunks)
        self.assertIsNotNone(response.body)
        self.assertEqual(response.headers['Content-Type'], 'application/json; charset=utf-8')

    def test_relay_wraps_success_as_sse_when_client_requests_stream(self) -> None:
        class JsonAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"groq/llama-3.1-8b-instant","choices":[{"index":0,"message":{"role":"assistant","content":"ok-stream"},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: JsonAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        self.assertEqual(response.headers['Content-Type'], 'text/event-stream; charset=utf-8')
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'chat.completion.chunk', chunks[0])
        self.assertIn(b'ok-stream', chunks[0])
        self.assertEqual(chunks[-1], b'data: [DONE]\n\n')

    def test_relay_wraps_json_response_as_sse_when_client_requests_stream(self) -> None:
        """Verify that when client requests stream=True, relay wraps JSON response as SSE."""
        class JsonAdapter:
            def forward_chat(self, payload: dict[str, object]):
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"groq/llama-3.1-8b-instant","choices":[{"index":0,"message":{"role":"assistant","content":"ok-non-stream"},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: JsonAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'ok-non-stream', chunks[0])

    def test_relay_trims_prompt_and_caps_output_budget_for_long_requests(self) -> None:
        class BudgetAwareAdapter:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []

            def forward_chat(self, payload: dict[str, object]):
                self.payloads.append(payload)
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        adapter = BudgetAwareAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        long_text = 'x' * 45096
        request = ChatRequest(
            'free-proxy/auto',
            None,
            [{'role': 'system', 'content': long_text}, {'role': 'user', 'content': long_text}],
            True,
            32000,
            0,
            {'model': 'auto', 'messages': [{'role': 'system', 'content': long_text}, {'role': 'user', 'content': long_text}], 'stream': True, 'max_tokens': 32000, 'temperature': 0},
        )

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(len(adapter.payloads), 1)
        payload = adapter.payloads[0]
        self.assertEqual([message['role'] for message in payload['messages']], ['system', 'user'])
        self.assertLess(len(str(payload['messages'][0]['content'])), len(long_text))
        self.assertLess(len(str(payload['messages'][1]['content'])), len(long_text))
        self.assertEqual(payload['max_tokens'], response_token_budget('openrouter'))
        self.assertIs(payload['stream'], True)

    def test_relay_drops_old_history_when_context_exceeds_provider_budget(self) -> None:
        class BudgetAwareAdapter:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []

            def forward_chat(self, payload: dict[str, object]):
                self.payloads.append(payload)
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        adapter = BudgetAwareAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        messages = [{'role': 'system', 'content': 's' * 1000}]
        for index in range(1, 12):
            messages.append({'role': 'user', 'content': f'u{index}:' + ('x' * 3000)})
            messages.append({'role': 'assistant', 'content': f'a{index}:' + ('y' * 3000)})
        request = ChatRequest('free-proxy/auto', None, messages, True, None, None, {'model': 'auto', 'messages': messages, 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        payload = adapter.payloads[0]
        self.assertLess(len(payload['messages']), len(messages))
        self.assertEqual(payload['messages'][0]['role'], 'system')
        self.assertEqual(payload['messages'][-1]['role'], 'assistant')
        self.assertIn('a11:', str(payload['messages'][-1]['content']))

    def test_relay_keeps_configured_order_for_interactive_clients(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        for client_hint in ('opencode', 'openclaw'):
            calls.clear()
            relay = OpenAIRelay(
                adapter_factory=lambda provider: OrderedAdapter(provider),
                health_loader=lambda: {
                    'openrouter/openrouter/auto:free': {'ok': True, 'checked_at': int(time.time()), 'success_streak': 9, 'failure_streak': 0},
                    'groq/llama-3.1-8b-instant': {'ok': True, 'checked_at': int(time.time()), 'success_streak': 1, 'failure_streak': 0},
                },
                preferred_model_loader=lambda: 'longcat/LongCat-Flash-Chat',
                health_ttl_seconds=60,
                configured_providers_loader=lambda: ['openrouter', 'groq'],
            )
            request = ChatRequest(
                'free-proxy/auto',
                'longcat/LongCat-Flash-Lite',
                [{'role': 'user', 'content': 'hi'}],
                True,
                None,
                None,
                {
                    'model': 'auto',
                    'requested_model': 'longcat/LongCat-Flash-Lite',
                    'messages': [{'role': 'user', 'content': 'hi'}],
                    'stream': True,
                    'client_hint': client_hint,
                },
            )

            response = relay.handle_chat(request)

            self.assertEqual(response.status, 200, client_hint)
            self.assertEqual(calls[0], ('openrouter', 'openrouter/auto:free'))
            self.assertTrue(all(provider != 'longcat' for provider, _model in calls))
            self.assertTrue(all('api.longcat.chat' not in model for _provider, model in calls))

        calls.clear()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {},
            preferred_model_loader=lambda: 'longcat/LongCat-Flash-Chat',
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        saved_preference = ChatRequest(
            'free-proxy/auto',
            None,
            [{'role': 'user', 'content': 'hi'}],
            True,
            None,
            None,
            {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True, 'client_hint': 'openclaw'},
        )
        response = relay.handle_chat(saved_preference)
        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('groq', 'llama-3.1-8b-instant'))
        self.assertTrue(all(provider != 'longcat' for provider, _model in calls))

    def test_relay_prefers_saved_frontend_model_before_health_rankings(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"content":"ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {
                'groq/llama-3.1-8b-instant': {'ok': True, 'checked_at': int(time.time()), 'success_streak': 9, 'failure_streak': 0},
            },
            preferred_model_loader=lambda: 'groq/llama-3.3-70b-versatile',
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('groq', 'llama-3.3-70b-versatile'))

    def test_relay_records_health_on_success_and_failure(self) -> None:
        events: list[tuple[str, str, bool, str | None]] = []

        class HealthAdapter:
            def __init__(self) -> None:
                self.calls = 0

            def forward_chat(self, payload: dict[str, object]):
                self.calls += 1
                if self.calls == 1:
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"server error"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        adapter = HealthAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_updater=lambda provider, model, ok, reason=None, **_fields: events.append((provider, model, ok, reason)),
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0][:3], ('groq', 'llama-3.1-8b-instant', False))
        self.assertEqual(events[-1][:3], ('groq', 'llama-3.3-70b-versatile', True))

    def test_relay_attempts_candidates_in_priority_order(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                if self.provider == 'groq':
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"server error"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq', 'gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('groq', 'llama-3.1-8b-instant'))
        self.assertTrue(any(provider == 'gemini' for provider, _ in calls))

    def test_payload_for_candidate_strips_non_openai_fields(self) -> None:
        relay = OpenAIRelay(
            adapter_factory=lambda provider: FakeAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter'],
        )
        request = ChatRequest(
            'free-proxy/auto',
            'nvidia/z-ai/glm-5.2',
            [{'role': 'user', 'content': 'hi'}],
            True,
            1024,
            0.7,
            {
                'model': 'free-proxy/auto',
                'messages': [{'role': 'user', 'content': 'hi'}],
                'stream': True,
                'system': 'You are a helpful assistant.',
                'client_hint': 'openclaw',
                'requested_model': 'nvidia/z-ai/glm-5.2',
                'temperature': 0.7,
                'max_tokens': 1024,
            },
        )
        payload = relay._payload_for_candidate('nvidia', 'z-ai/glm-5.2', request)
        self.assertNotIn('client_hint', payload)
        self.assertNotIn('system', payload)
        self.assertNotIn('requested_model', payload)
        self.assertEqual(payload['model'], 'z-ai/glm-5.2')
        self.assertIs(payload['stream'], True)
        self.assertEqual(payload['max_tokens'], 1024)
        self.assertEqual(payload['messages'][0]['role'], 'system')
        self.assertEqual(payload['messages'][0]['content'], 'You are a helpful assistant.')
        self.assertEqual(payload['temperature'], 0.7)

    def test_relay_cleans_payload_and_falls_back_after_unsupported_parameter(self) -> None:
        payloads: list[dict[str, object]] = []

        class StrictAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                payloads.append(payload)
                if self.provider == 'nvidia':
                    return type('AdapterResponse', (), {'status': 400, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"message":"Validation: Unsupported parameter(s): client_hint","type":"Bad Request","code":400}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StrictAdapter(provider),
            health_loader=lambda: {},
            health_updater=None,
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['nvidia', 'openrouter'],
        )
        request = ChatRequest(
            'free-proxy/auto',
            'nvidia/z-ai/glm-5.2',
            [{'role': 'user', 'content': 'hi'}],
            False,
            None,
            None,
            {
                'model': 'free-proxy/auto',
                'messages': [{'role': 'user', 'content': 'hi'}],
                'client_hint': 'openclaw',
                'system': 'You are a helpful assistant.',
            },
        )
        response = relay.handle_chat(request)
        self.assertEqual(response.status, 200)
        # nvidia 的 payload 必须已清洗：无 client_hint / 顶层 system
        self.assertNotIn('client_hint', payloads[0])
        self.assertNotIn('system', payloads[0])
        # 400 (unknown) 后应继续尝试 openrouter，而不是整体 stop
        self.assertEqual(payloads[-1]['model'], 'openrouter/auto:free')

    def test_relay_uses_reasoning_content_when_content_is_missing(self) -> None:
        class ReasoningOnlyAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"choices":[{"message":{"role":"assistant","reasoning_content":"think-ok"}}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: ReasoningOnlyAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertIsNotNone(response.body)
        self.assertIn(b'think-ok', response.body or b'')

    def test_relay_falls_back_when_adapter_raises_provider_error(self) -> None:
        calls: list[str] = []

        class TimeoutAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append('gemini')
                raise ProviderError('网络连接失败: The read operation timed out')

        class SuccessAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append('github')
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-fallback"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: TimeoutAdapter() if provider == 'gemini' else SuccessAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[:2], ['gemini', 'gemini'])
        self.assertIn('github', calls)
        self.assertIn(b'ok-fallback', response.body or b'')

    def test_relay_prefers_health_boosted_candidate_over_configured_order(self) -> None:
        calls: list[tuple[str, str]] = []

        class OrderedAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                if self.provider == 'groq':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok-groq"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 402, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"error":{"message":"insufficient credits"}}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: OrderedAdapter(provider),
            health_loader=lambda: {'groq/llama-3.1-8b-instant': {'ok': True, 'checked_at': int(time.time()), 'success_streak': 4, 'failure_streak': 0}},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['openrouter', 'groq', 'gemini', 'github'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})

        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('groq', 'llama-3.1-8b-instant'))
        self.assertIsNone(response.body)
        self.assertIsNotNone(response.stream_chunks)
        chunks = list(response.stream_chunks or [])
        self.assertIn(b'ok-groq', chunks[0])

    def test_relay_forces_stream_false_upstream_even_when_client_requests_stream(self) -> None:
        """OpenAI providers stream upstream when the client asks for SSE."""
        stream_values: list[bool] = []

        class StreamCheckAdapter:
            def forward_chat(self, payload: dict[str, object]):
                stream_values.append(bool(payload.get('stream')))
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"ok"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StreamCheckAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})
        relay.handle_chat(request)
        self.assertEqual(stream_values, [True])

    def test_payload_for_candidate_streams_gemini_without_changing_openai_assignment(self) -> None:
        relay = OpenAIRelay(
            adapter_factory=lambda provider: FakeAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq', 'gemini'],
        )
        request = ChatRequest(
            'free-proxy/auto',
            None,
            [{'role': 'user', 'content': 'hi'}],
            False,
            None,
            None,
            {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': False},
        )
        openai_payload = relay._payload_for_candidate('groq', 'llama-3.1-8b-instant', request)
        gemini_payload = relay._payload_for_candidate('gemini', 'gemini-2.0-flash', request)
        self.assertIs(openai_payload['stream'], True)
        self.assertIs(gemini_payload['stream'], True)

    def test_relay_maps_gemini_sse_when_client_streams(self) -> None:
        calls: list[tuple[str, str, object]] = []
        consumed = {'n': 0}
        hel = _gemini_sse_event('hel')
        lo = _gemini_sse_event('lo', 'STOP')

        def events():
            consumed['n'] += 1
            yield hel
            consumed['n'] += 1
            yield lo

        class Adapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                calls.append((self.provider, str(payload.get('model', '')), payload.get('stream')))
                if self.provider == 'gemini':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'text/event-stream'}, 'body': None, 'stream': events(), 'content_type': 'text/event-stream'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json'}, 'body': b'{"choices":[{"message":{"content":"from-github"}}]}', 'stream': None, 'content_type': 'application/json'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: Adapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['gemini', 'github'],
        )
        response = relay.handle_chat(_gemini_chat_request(stream=True))

        self.assertEqual(response.status, 200)
        self.assertEqual(calls, [('gemini', 'gemini-2.0-flash', True)])
        self.assertEqual(consumed['n'], 0)
        self.assertIsNone(response.body)
        self.assertIn('text/event-stream', response.headers.get('Content-Type', ''))
        parsed = [_parse_sse_chunk(chunk) for chunk in list(response.stream_chunks or [])]
        self.assertEqual(consumed['n'], 2)
        self.assertEqual(calls, [('gemini', 'gemini-2.0-flash', True)])
        self.assertEqual(
            [
                (item['choices'][0]['delta'].get('content'), item['choices'][0]['finish_reason'])
                for item in parsed
                if item != '[DONE]'
            ],
            [('hel', None), ('lo', None), (None, 'stop')],
        )
        self.assertEqual(parsed[-1], '[DONE]')

    def test_relay_collects_gemini_sse_into_json_when_client_does_not_stream(self) -> None:
        calls: list[str] = []

        class Adapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                calls.append(self.provider)
                self.stream_flag = payload.get('stream')
                if self.provider == 'gemini':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {}, 'body': None, 'stream': iter([_gemini_sse_event('hel'), _gemini_sse_event('lo', 'STOP')]), 'content_type': 'text/event-stream'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {}, 'body': b'{"choices":[{"message":{"content":"from-github"}}]}', 'stream': None, 'content_type': 'application/json'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: Adapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['gemini', 'github'],
        )
        response = relay.handle_chat(_gemini_chat_request(stream=False))

        self.assertEqual(calls, ['gemini'])
        self.assertIsNone(response.stream_chunks)
        self.assertIn('application/json', response.headers.get('Content-Type', ''))
        parsed = json.loads(response.body or b'{}')
        self.assertEqual(parsed['object'], 'chat.completion')
        self.assertEqual(parsed['model'], 'gemini/gemini-2.0-flash')
        self.assertEqual(parsed['choices'][0]['message']['role'], 'assistant')
        self.assertEqual(parsed['choices'][0]['message']['content'], 'hello')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'stop')

    def test_relay_falls_back_when_gemini_http_500_sse_is_not_success(self) -> None:
        calls: list[str] = []

        class Adapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append(self.provider)
                if self.provider == 'gemini':
                    return type('AdapterResponse', (), {'status': 500, 'headers': {'Content-Type': 'text/event-stream'}, 'body': None, 'stream': iter([b'data: {"error":{"message":"gemini-broke"}}\n\n']), 'content_type': 'text/event-stream'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json'}, 'body': b'{"choices":[{"message":{"content":"from-github"}}]}', 'stream': None, 'content_type': 'application/json'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: Adapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['gemini', 'github'],
        )
        response = relay.handle_chat(_gemini_chat_request(stream=True))

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], 'gemini')
        self.assertIn('github', calls)
        joined = b''.join(list(response.stream_chunks or []))
        self.assertIn(b'from-github', joined)
        self.assertNotIn(b'gemini-broke', joined)

    def test_relay_passes_upstream_sse_through_and_does_not_call_next_provider(self) -> None:
        calls: list[tuple[str, str]] = []
        consumed = {'n': 0}
        reasoning = b'data: {"choices":[{"delta":{"reasoning_content":"think-1"},"index":0}]}\n\n'
        content = b'data: {"choices":[{"delta":{"content":"answer-1"},"index":0}]}\n\n'
        done = b'data: [DONE]\n\n'

        def events():
            consumed['n'] += 1
            yield reasoning
            consumed['n'] += 1
            yield content
            consumed['n'] += 1
            yield done

        stream_flags: list[object] = []

        class StreamingAdapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                calls.append((self.provider, str(payload.get('model', ''))))
                stream_flags.append(payload.get('stream'))
                if self.provider == 'groq':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'text/event-stream; charset=utf-8'}, 'body': None, 'stream': events(), 'content_type': 'text/event-stream; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"next"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StreamingAdapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq', 'openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls, [('groq', 'llama-3.1-8b-instant')])
        self.assertEqual(stream_flags, [True])
        self.assertEqual(consumed['n'], 0)
        self.assertIsNone(response.body)
        self.assertEqual(list(response.stream_chunks or []), [reasoning, content, done])
        self.assertEqual(consumed['n'], 3)

    def test_relay_synthesizes_json_from_upstream_sse_when_client_does_not_stream(self) -> None:
        calls: list[str] = []

        class StreamingAdapter:
            def forward_chat(self, payload: dict[str, object]):
                calls.append(str(payload.get('stream')))
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'text/event-stream; charset=utf-8'},
                        'body': None,
                        'stream': iter([
                            b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-1"}}]}\n\n',
                            b'data: {"choices":[{"index":0,"delta":{"content":"answer-1"},"finish_reason":"stop"}]}\n\n',
                            b'data: [DONE]\n\n',
                        ]),
                        'content_type': 'text/event-stream; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: StreamingAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls, ['True'])
        self.assertIsNone(response.stream_chunks)
        parsed = json.loads(response.body or b'{}')
        self.assertEqual(parsed['choices'][0]['message']['content'], 'answer-1')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'stop')

    def test_relay_synthesizes_reasoning_when_sse_content_is_empty(self) -> None:
        class ReasoningAdapter:
            def forward_chat(self, payload: dict[str, object]):
                del payload
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'text/event-stream; charset=utf-8'},
                        'body': None,
                        'stream': iter([
                            b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-1"}}]}\n\n',
                            b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"think-2"},"finish_reason":"length"}]}\n\n',
                            b'data: [DONE]\n\n',
                        ]),
                        'content_type': 'text/event-stream; charset=utf-8',
                    },
                )()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: ReasoningAdapter(),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)
        parsed = json.loads(response.body or b'{}')
        self.assertEqual(parsed['choices'][0]['message']['content'], 'think-1think-2')
        self.assertEqual(parsed['choices'][0]['finish_reason'], 'length')

    def test_relay_falls_back_when_first_openai_provider_returns_http_500(self) -> None:
        calls: list[str] = []

        class Adapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                del payload
                calls.append(self.provider)
                if self.provider == 'groq':
                    return type(
                        'AdapterResponse',
                        (),
                        {
                            'status': 500,
                            'headers': {'Content-Type': 'application/json; charset=utf-8'},
                            'body': None,
                            'stream': iter([b'{"error":{"message":"server error"}}']),
                            'content_type': 'application/json; charset=utf-8',
                        },
                    )()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"from-openrouter"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: Adapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq', 'openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], 'groq')
        self.assertIn('openrouter', calls)
        chunks = b''.join(list(response.stream_chunks or []))
        self.assertIn(b'from-openrouter', chunks)

    def test_relay_falls_back_when_sse_read_fails_before_handoff(self) -> None:
        calls: list[tuple[str, str]] = []

        def broken():
            yield b'data: {"choices":[{"index":0,"delta":{"content":"partial"}}]}\n\n'
            raise ProviderError('The read operation timed out')

        class Adapter:
            def __init__(self, provider: str) -> None:
                self.provider = provider

            def forward_chat(self, payload: dict[str, object]):
                model = str(payload.get('model', ''))
                calls.append((self.provider, model))
                if self.provider == 'groq' and model == 'llama-3.1-8b-instant':
                    return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'text/event-stream; charset=utf-8'}, 'body': None, 'stream': broken(), 'content_type': 'text/event-stream; charset=utf-8'})()
                return type('AdapterResponse', (), {'status': 200, 'headers': {'Content-Type': 'application/json; charset=utf-8'}, 'body': b'{"choices":[{"message":{"content":"from-next"}}]}', 'stream': None, 'content_type': 'application/json; charset=utf-8'})()

        relay = OpenAIRelay(
            adapter_factory=lambda provider: Adapter(provider),
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq', 'openrouter'],
        )
        request = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        response = relay.handle_chat(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(calls[0], ('groq', 'llama-3.1-8b-instant'))
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn(b'from-next', response.body or b'')
        self.assertNotIn(b'partial', response.body or b'')

    def test_relay_keeps_json_sse_wrap_when_adapter_has_no_stream(self) -> None:
        class JsonAdapter:
            def forward_chat(self, payload: dict[str, object]):
                self.stream_flag = payload.get('stream')
                return type(
                    'AdapterResponse',
                    (),
                    {
                        'status': 200,
                        'headers': {'Content-Type': 'application/json; charset=utf-8'},
                        'body': b'{"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"groq/llama","choices":[{"index":0,"message":{"role":"assistant","content":"json-body"},"finish_reason":"stop"}]}',
                        'stream': None,
                        'content_type': 'application/json; charset=utf-8',
                    },
                )()

        adapter = JsonAdapter()
        relay = OpenAIRelay(
            adapter_factory=lambda provider: adapter,
            health_loader=lambda: {},
            health_ttl_seconds=60,
            configured_providers_loader=lambda: ['groq'],
        )
        streaming = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], True, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True})
        streamed = relay.handle_chat(streaming)
        self.assertIs(adapter.stream_flag, True)
        self.assertIsNone(streamed.body)
        streamed_chunks = b''.join(list(streamed.stream_chunks or []))
        self.assertIn(b'json-body', streamed_chunks)
        self.assertIn(b'data: [DONE]', streamed_chunks)

        plain = ChatRequest('free-proxy/auto', None, [{'role': 'user', 'content': 'hi'}], False, None, None, {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]})
        json_response = relay.handle_chat(plain)
        self.assertIsNone(json_response.stream_chunks)
        self.assertIn(b'json-body', json_response.body or b'')


class _Clock:
    def __init__(self, now: int) -> None:
        self.now = now

    def time(self) -> float:
        return float(self.now)


class _MemoryHealth:
    def __init__(self, initial: dict[str, dict[str, object]] | None = None) -> None:
        self.data = {key: dict(value) for key, value in (initial or {}).items()}

    def load(self) -> dict[str, dict[str, object]]:
        return {key: dict(value) for key, value in self.data.items()}

    def update(self, provider: str, model: str, ok: bool, reason: str | None = None, **fields: object) -> None:
        entry: dict[str, object] = {'ok': ok, 'reason': reason}
        for name in ('category', 'scope', 'cooldown_until', 'key_hash'):
            value = fields.get(name)
            if value is not None:
                entry[name] = value
        self.data[f'{provider}/{model}'] = entry


def _chat_request() -> ChatRequest:
    return ChatRequest(
        'free-proxy/auto',
        None,
        [{'role': 'user', 'content': 'hi'}],
        False,
        None,
        None,
        {'model': 'auto', 'messages': [{'role': 'user', 'content': 'hi'}]},
    )


def _adapter_response(status: int, body: bytes, headers: dict[str, str] | None = None):
    return type(
        'AdapterResponse',
        (),
        {
            'status': status,
            'headers': headers or {'Content-Type': 'application/json; charset=utf-8'},
            'body': body,
            'stream': None,
            'content_type': 'application/json; charset=utf-8',
        },
    )()


def _error_response(status: int, message: str, headers: dict[str, str] | None = None):
    return _adapter_response(status, json.dumps({'error': {'message': message}}).encode('utf-8'), headers)


def _ok_response(content: str = 'ok'):
    return _adapter_response(200, json.dumps({'choices': [{'message': {'content': content}}]}).encode('utf-8'))


class CooldownRelayTests(unittest.TestCase):
    def _relay(self, factory, providers: list[str], health: dict[str, dict[str, object]] | None = None, hashes: dict[str, str] | None = None):
        memory = _MemoryHealth(health)
        key_hashes = dict(hashes or {})
        relay = OpenAIRelay(
            adapter_factory=factory,
            health_loader=memory.load,
            health_updater=memory.update,
            health_ttl_seconds=600,
            configured_providers_loader=lambda: list(providers),
            key_hash_loader=lambda provider: key_hashes.get(provider, ''),
        )
        return relay, memory, key_hashes

    def test_rate_limit_skips_provider_for_this_request_and_the_next_one(self) -> None:
        calls: list[tuple[str, str]] = []
        lists: list[str] = []
        gemini_ok = {'ok': True}

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    model = str(payload.get('model', ''))
                    calls.append((provider, model))
                    if provider == 'groq':
                        return _error_response(429, 'rate limit')
                    if gemini_ok['ok']:
                        return _ok_response('from-gemini')
                    return _error_response(500, 'server error')

                def list_models(self) -> list[str]:
                    lists.append(provider)
                    return []

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq', 'gemini'])
        clock = _Clock(1_700_000_000)
        with patch('python_scripts.openai_relay.time.sleep') as slept, patch('python_scripts.openai_relay.time.time', clock.time):
            response = relay.handle_chat(_chat_request())
            self.assertEqual(response.status, 200)
            self.assertEqual(
                calls,
                [
                    ('groq', 'llama-3.1-8b-instant'),
                    ('gemini', 'gemini-3.1-flash-lite-preview'),
                ],
            )
            self.assertEqual(lists, [])
            slept.assert_not_called()

            relay.handle_chat(_chat_request())
            self.assertEqual([item for item in calls if item[0] == 'groq'], [('groq', 'llama-3.1-8b-instant')])

            gemini_ok['ok'] = False
            clock.now += 59
            relay.handle_chat(_chat_request())
            self.assertEqual([item for item in calls if item[0] == 'groq'], [('groq', 'llama-3.1-8b-instant')])

            clock.now += 1
            relay.handle_chat(_chat_request())
            self.assertEqual([item for item in calls if item[0] == 'groq'], [('groq', 'llama-3.1-8b-instant'), ('groq', 'llama-3.1-8b-instant')])
            self.assertNotIn('groq', lists)

    def test_retry_after_controls_rate_limit_cooldown(self) -> None:
        calls: list[tuple[str, str]] = []
        lists: list[str] = []
        gemini_ok = {'ok': True}

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    model = str(payload.get('model', ''))
                    calls.append((provider, model))
                    if provider == 'groq':
                        return _error_response(429, 'rate limit', {'Retry-After': '120', 'Content-Type': 'application/json'})
                    if gemini_ok['ok']:
                        return _ok_response()
                    return _error_response(500, 'server error')

                def list_models(self) -> list[str]:
                    lists.append(provider)
                    return []

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq', 'gemini'])
        clock = _Clock(1_700_000_000)

        def groq_calls() -> list[tuple[str, str]]:
            return [item for item in calls if item[0] == 'groq']

        with patch('python_scripts.openai_relay.time.time', clock.time):
            relay.handle_chat(_chat_request())
            self.assertEqual(groq_calls(), [('groq', 'llama-3.1-8b-instant')])
            gemini_ok['ok'] = False
            clock.now += 90
            relay.handle_chat(_chat_request())
            self.assertEqual(groq_calls(), [('groq', 'llama-3.1-8b-instant')])
            clock.now += 30
            relay.handle_chat(_chat_request())
            self.assertEqual(groq_calls(), [('groq', 'llama-3.1-8b-instant'), ('groq', 'llama-3.1-8b-instant')])
            self.assertNotIn('groq', lists)

    def test_quota_cooldown_lasts_six_hours(self) -> None:
        calls: list[str] = []
        lists: list[str] = []
        gemini_ok = {'ok': True}

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    calls.append(provider)
                    if provider == 'groq':
                        return _error_response(429, 'credits are depleted')
                    if gemini_ok['ok']:
                        return _ok_response()
                    return _error_response(500, 'server error')

                def list_models(self) -> list[str]:
                    lists.append(provider)
                    return []

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq', 'gemini'])
        clock = _Clock(1_700_000_000)
        with patch('python_scripts.openai_relay.time.time', clock.time):
            relay.handle_chat(_chat_request())
            self.assertEqual(calls.count('groq'), 1)
            clock.now += 61
            relay.handle_chat(_chat_request())
            self.assertEqual(calls.count('groq'), 1)
            gemini_ok['ok'] = False
            clock.now = 1_700_000_000 + QUOTA_COOLDOWN_SECONDS - 1
            relay.handle_chat(_chat_request())
            self.assertEqual(calls.count('groq'), 1)
            clock.now += 1
            relay.handle_chat(_chat_request())
            self.assertEqual(calls.count('groq'), 2)
            self.assertNotIn('groq', lists)

    def test_auth_cooldown_follows_key_hash(self) -> None:
        calls: list[str] = []
        gemini_ok = {'ok': True}

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    del payload
                    calls.append(provider)
                    if provider == 'groq':
                        return _error_response(401, 'invalid api key')
                    if gemini_ok['ok']:
                        return _ok_response()
                    return _error_response(500, 'server error')

            return Adapter()

        relay, _memory, hashes = self._relay(factory, ['groq', 'gemini'], hashes={'groq': 'hash-a'})
        relay.handle_chat(_chat_request())
        self.assertEqual(calls.count('groq'), 1)
        self.assertIn('gemini', calls)
        relay.handle_chat(_chat_request())
        self.assertEqual(calls.count('groq'), 1)
        gemini_ok['ok'] = False
        relay.handle_chat(_chat_request())
        self.assertEqual(calls.count('groq'), 1)
        hashes['groq'] = 'hash-b'
        relay.handle_chat(_chat_request())
        self.assertEqual(calls.count('groq'), 2)

    def test_server_error_skips_only_the_failed_model(self) -> None:
        calls: list[tuple[str, str]] = []

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    model = str(payload.get('model', ''))
                    calls.append((provider, model))
                    if (provider, model) == ('groq', 'llama-3.1-8b-instant'):
                        return _error_response(500, 'server error')
                    return _ok_response('other-model')

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq'])
        response = relay.handle_chat(_chat_request())
        self.assertEqual(response.status, 200)
        self.assertEqual(
            calls[:2],
            [
                ('groq', 'llama-3.1-8b-instant'),
                ('groq', 'llama-3.3-70b-versatile'),
            ],
        )

    def test_all_cooled_candidates_return_502_without_upstream_calls(self) -> None:
        calls: list[str] = []
        now = 1_700_000_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'provider', 'category': 'quota', 'cooldown_until': now + 10},
            'gemini/gemini-3.1-flash-lite-preview': {'scope': 'provider', 'category': 'quota', 'cooldown_until': now + 10},
        }

        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    del payload
                    calls.append(provider)
                    return _ok_response()

                def list_models(self) -> list[str]:
                    calls.append(f'list:{provider}')
                    return ['extra-model']

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq', 'gemini'], health=health)
        clock = _Clock(now)
        with patch('python_scripts.openai_relay.time.time', clock.time):
            response = relay.handle_chat(_chat_request())
        self.assertEqual(calls, [])
        self.assertEqual(response.status, 502)
        payload = json.loads((response.body or b'{}').decode('utf-8'))
        self.assertEqual(payload['error']['message'], 'all candidates failed')
        self.assertEqual(payload['error']['code'], '502')

    def test_success_body_does_not_add_fallback_fields(self) -> None:
        def factory(provider: str):
            class Adapter:
                def forward_chat(self, payload: dict[str, object]):
                    del payload
                    return _ok_response('plain-ok')

            return Adapter()

        relay, _memory, _hashes = self._relay(factory, ['groq'])
        with patch('python_scripts.openai_relay.time.sleep') as slept:
            response = relay.handle_chat(_chat_request())
            slept.assert_not_called()
        body = json.loads((response.body or b'{}').decode('utf-8'))
        self.assertEqual(set(body), {'id', 'object', 'created', 'model', 'choices', 'usage'})
        self.assertEqual(body['choices'][0]['message']['content'], 'plain-ok')
        self.assertNotIn(b'fallback', response.body or b'')
