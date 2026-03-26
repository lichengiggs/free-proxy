from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_scripts.token_limit_store import load_token_limits, upsert_token_limit


class TokenLimitStoreTests(unittest.TestCase):
    def test_load_returns_empty_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'token-limits.json'
            self.assertEqual(load_token_limits(path), {})

    def test_upsert_persists_provider_model_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'token-limits.json'
            upsert_token_limit(
                'longcat',
                'LongCat-Flash-Lite',
                input_tokens_limit=65536,
                output_tokens_limit=4096,
                source='default_fallback',
                path=path,
                now_ts=123,
            )
            saved = load_token_limits(path)
            self.assertEqual(saved['longcat/LongCat-Flash-Lite']['input_tokens_limit'], 65536)
            self.assertEqual(saved['longcat/LongCat-Flash-Lite']['output_tokens_limit'], 4096)
            self.assertEqual(saved['longcat/LongCat-Flash-Lite']['updated_at'], 123)
