from __future__ import annotations

import json
import unittest

from python_scripts.client import ProviderClient
from python_scripts.config import get_provider_spec


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str], tuple[int, dict[str, str], bytes]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str] | None, bytes | None]] = []

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: int = 30):
        self.requests.append((method, url, headers, body))
        return self.responses[(method, url)]


class ClientTests(unittest.TestCase):
    def test_openai_list_models_and_chat(self) -> None:
        spec = get_provider_spec('openrouter')
        transport = FakeTransport({
            ('GET', 'https://openrouter.ai/api/v1/models'): (200, {}, json.dumps({'data': [{'id': 'a'}, {'id': 'b'}]}).encode()),
            ('POST', 'https://openrouter.ai/api/v1/chat/completions'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['a', 'b'])
        self.assertEqual(client.chat('a', 'ok'), 'ok')

    def test_github_uses_preview_version(self) -> None:
        spec = get_provider_spec('github')
        transport = FakeTransport({
            ('GET', 'https://models.github.ai/inference/models'): (404, {}, b'not found'),
            ('POST', 'https://models.github.ai/inference/chat/completions?api-version=2024-12-01-preview'): (200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gpt-4o-mini', 'gpt-4o', 'DeepSeek-V3-0324', 'Llama-3.3-70B-Instruct'])
        self.assertEqual(client.chat('gpt-4o-mini', 'ok'), 'ok')

    def test_cerebras_model_hint_fallback(self) -> None:
        spec = get_provider_spec('cerebras')
        transport = FakeTransport({
            ('GET', 'https://api.cerebras.ai/v1/models'): (403, {}, b'error code: 1010'),
            ('POST', 'https://api.cerebras.ai/v1/chat/completions'): (403, {}, b'error code: 1010'),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gpt-oss-120b', 'llama-3.1-8b'])
        with self.assertRaises(Exception):
            client.chat('llama-3.3-70b', 'ok')

    def test_gemini_normalizes_models_and_chat(self) -> None:
        spec = get_provider_spec('gemini')
        transport = FakeTransport({
            ('GET', 'https://generativelanguage.googleapis.com/v1beta/models'): (200, {}, json.dumps({'models': [{'id': 'models/gemini-2.0-flash'}]}).encode()),
            ('POST', 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'): (200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode()),
        })
        client = ProviderClient(spec=spec, api_key='x', transport=transport)
        self.assertEqual(client.list_models(), ['gemini-2.0-flash'])
        self.assertEqual(client.chat('models/gemini-2.0-flash', 'ok'), 'ok')
