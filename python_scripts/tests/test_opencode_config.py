from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.opencode_config import configure_opencode_provider, detect_opencode_config


class OpencodeConfigTests(unittest.TestCase):
    def test_configure_creates_provider_with_auto_and_coding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get('OPENCODE_TEST_DIR')
            os.environ['OPENCODE_TEST_DIR'] = tmp
            try:
                result = configure_opencode_provider(port=8765)
                self.assertTrue(result['success'])
                self.assertIsNone(result['backup'])

                status = detect_opencode_config()
                self.assertTrue(status['exists'])
                self.assertTrue(status['isValid'])

                content = status.get('content') or {}
                provider = content.get('provider', {}).get('free_proxy', {})
                self.assertEqual(provider.get('name'), 'free_proxy')
                self.assertEqual(provider.get('options', {}).get('baseURL'), 'http://localhost:8765/v1')
                models = provider.get('models', {})
                self.assertEqual(sorted(models.keys()), ['auto', 'coding'])
            finally:
                if old is None:
                    os.environ.pop('OPENCODE_TEST_DIR', None)
                else:
                    os.environ['OPENCODE_TEST_DIR'] = old

    def test_configure_preserves_existing_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get('OPENCODE_TEST_DIR')
            os.environ['OPENCODE_TEST_DIR'] = tmp
            try:
                root = Path(tmp)
                config_path = root / 'opencode.json'
                root.mkdir(parents=True, exist_ok=True)
                config_path.write_text(
                    json.dumps(
                        {
                            'provider': {
                                'other': {
                                    'name': 'other',
                                    'options': {'baseURL': 'http://example.com'},
                                    'models': {'fast': {'name': 'fast'}},
                                }
                            },
                            'instructions': ['~/.config/opencode/rules/global-guidelines.md'],
                        }
                    ),
                    encoding='utf-8',
                )

                result = configure_opencode_provider(port=8765)
                self.assertTrue(result['success'])
                self.assertTrue(result['backup'])

                final = json.loads(config_path.read_text(encoding='utf-8'))
                self.assertIn('other', final.get('provider', {}))
                self.assertIn('free_proxy', final.get('provider', {}))
                self.assertIn('instructions', final)
            finally:
                if old is None:
                    os.environ.pop('OPENCODE_TEST_DIR', None)
                else:
                    os.environ['OPENCODE_TEST_DIR'] = old
