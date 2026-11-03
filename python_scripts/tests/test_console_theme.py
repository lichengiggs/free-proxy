from __future__ import annotations

import unittest
from pathlib import Path


class ConsoleThemeTests(unittest.TestCase):
    def test_console_page_background_is_neutral_light_gray(self) -> None:
        html = Path(__file__).resolve().parents[1].joinpath('web', 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('#f6f7f3', html)
        self.assertNotIn('#fbfcf8', html)
        self.assertIn('--bg: #f2f2f2;', html)
        body = html.split('body {', 1)[1].split('}', 1)[0]
        self.assertIn('linear-gradient(180deg, #f7f7f7 0%, var(--bg) 100%)', body)
        self.assertNotIn('#f6f7f3', body)
        self.assertNotIn('#fbfcf8', body)
        for preserved in (
            '--panel: #fffdfa;',
            '--panel-strong: #ffffff;',
            '--text: #182018;',
            '--muted: #667163;',
            '--line: #dde5d7;',
            '--primary: #1e6a52;',
            '--primary-strong: #174f3d;',
            '--accent: #d5843f;',
            '--danger: #b9483e;',
            '--success-bg: #e4f5ea;',
            '--error-bg: #fdeaea;',
            '--info-bg: #ebf3ff;',
        ):
            self.assertIn(preserved, html)
