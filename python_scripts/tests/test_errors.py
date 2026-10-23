from __future__ import annotations

import unittest

from python_scripts.errors import classify_error, remediation_suggestion


class ErrorTests(unittest.TestCase):
    def test_classify_error_by_text_without_status(self) -> None:
        self.assertEqual(classify_error(0, 'invalid api key').category, 'auth')
        self.assertEqual(classify_error(0, 'quota exceeded').category, 'quota')
        self.assertEqual(classify_error(0, 'model not found').category, 'model_not_found')
        self.assertEqual(classify_error(400, 'maximum context length is 8192 tokens').category, 'token_limit')
        self.assertEqual(classify_error(400, 'maxOutputTokens too large').category, 'token_limit')

    def test_quota_phrases_outrank_bare_429(self) -> None:
        self.assertEqual(classify_error(429, 'credits are depleted').category, 'quota')
        self.assertEqual(classify_error(429, 'credit balance is too low').category, 'quota')
        self.assertEqual(classify_error(429, 'spend limit reached').category, 'quota')
        self.assertEqual(classify_error(429, 'insufficient_quota').category, 'quota')
        self.assertEqual(classify_error(429, 'spending cap reached').category, 'quota')
        self.assertEqual(classify_error(429, 'slow down').category, 'rate_limit')

    def test_remediation_suggestion_returns_actionable_text(self) -> None:
        self.assertIn('API Key', remediation_suggestion('auth', 'groq'))
        self.assertIn('额度', remediation_suggestion('quota', 'openrouter'))
        self.assertIn('模型', remediation_suggestion('model_not_found', 'sambanova'))
