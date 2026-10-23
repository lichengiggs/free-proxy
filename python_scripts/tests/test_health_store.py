from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_scripts import health_store


class HealthStoreTests(unittest.TestCase):
    def test_load_health_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing-health.json'
            self.assertEqual(health_store.load_health(path), {})

    def test_upsert_health_persists_provider_model_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model-health.json'
            health_store.upsert_health('openrouter', 'm1', True, path=path, now_ts=100)
            health_store.upsert_health('openrouter', 'm2', False, reason='rate_limit', path=path, now_ts=101)

            data = health_store.load_health(path)
            self.assertEqual(data['openrouter/m1']['ok'], True)
            self.assertEqual(data['openrouter/m1']['checked_at'], 100)
            self.assertEqual(data['openrouter/m2']['ok'], False)
            self.assertEqual(data['openrouter/m2']['reason'], 'rate_limit')

    def test_upsert_health_stores_cooldown_without_api_key_and_clears_it_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model-health.json'
            secret = 'test-live-secret'
            digest = health_store.hash_api_key(secret)
            self.assertNotEqual(digest, secret)
            self.assertNotIn(secret, digest)
            self.assertEqual(health_store.hash_api_key(''), '')

            health_store.upsert_health(
                'groq',
                'llama-3.1-8b-instant',
                False,
                reason='auth',
                path=path,
                now_ts=10,
                category='auth',
                cooldown_until=99,
                scope='provider',
                key_hash=digest,
            )
            raw = path.read_text(encoding='utf-8')
            self.assertNotIn(secret, raw)
            data = health_store.load_health(path)
            entry = data['groq/llama-3.1-8b-instant']
            self.assertEqual(entry['category'], 'auth')
            self.assertEqual(entry['scope'], 'provider')
            self.assertEqual(entry['cooldown_until'], 99)
            self.assertEqual(entry['key_hash'], digest)

            health_store.upsert_health('groq', 'llama-3.1-8b-instant', True, path=path, now_ts=11)
            cleared = health_store.load_health(path)['groq/llama-3.1-8b-instant']
            self.assertNotIn('cooldown_until', cleared)
            self.assertNotIn('scope', cleared)
            self.assertNotIn('key_hash', cleared)
            self.assertNotIn('category', cleared)
