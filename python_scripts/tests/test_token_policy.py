from __future__ import annotations

import unittest

from python_scripts.token_policy import response_token_budget, trim_prompt


class TokenPolicyTests(unittest.TestCase):
    def test_trim_prompt_keeps_short_text(self) -> None:
        text = 'hello world'
        self.assertEqual(trim_prompt('github', text), text)

    def test_trim_prompt_truncates_long_text(self) -> None:
        text = 'a' * 7000
        trimmed = trim_prompt('github', text)
        self.assertNotEqual(trimmed, text)
        self.assertIn('...[内容已截断]...', trimmed)
        self.assertTrue(trimmed.startswith('a'))
        self.assertTrue(trimmed.endswith('a'))

    def test_response_token_budget_uses_updated_default(self) -> None:
        self.assertEqual(response_token_budget('unknown-provider'), 4096)
