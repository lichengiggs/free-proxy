from __future__ import annotations

import json
import os
import unittest

from python_scripts.client import ProviderClient
from python_scripts.config import get_provider_spec, get_provider_specs


class MatrixTransport:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': f'{self.provider_name}-model'}]}).encode()
        if self.provider_name == 'gemini':
            return 200, {}, json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class ProviderMatrixTests(unittest.TestCase):
    def test_every_provider_has_spec_and_smoke_flow(self) -> None:
        for spec in get_provider_specs():
            with self.subTest(provider=spec.name):
                os.environ[spec.api_key_env] = 'test-key'
                client = ProviderClient(spec=get_provider_spec(spec.name), api_key='test-key', transport=MatrixTransport(spec.name))
                models = client.list_models()
                self.assertTrue(models)
                self.assertEqual(client.chat(models[0], 'ok'), 'ok')
