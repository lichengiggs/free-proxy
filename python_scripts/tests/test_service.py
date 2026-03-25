from __future__ import annotations

import json
import os
import unittest

from python_scripts.service import ProxyService


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, headers=None, body=None, timeout: int = 30):
        self.calls.append((method, url))
        if url.endswith('/models'):
            return 200, {}, json.dumps({'data': [{'id': 'ok-model'}]}).encode()
        return 200, {}, json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get('OPENROUTER_API_KEY')
        os.environ['OPENROUTER_API_KEY'] = 'test'

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop('OPENROUTER_API_KEY', None)
        else:
            os.environ['OPENROUTER_API_KEY'] = self._old

    def test_probe_returns_ok(self) -> None:
        service = ProxyService(transport=FakeTransport())
        result = service.probe('openrouter', 'ok-model')
        self.assertTrue(result.ok)
        self.assertEqual(result.content, 'ok')
        self.assertEqual(result.actual_model, 'ok-model')
