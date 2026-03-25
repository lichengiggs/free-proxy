from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from python_scripts.config import load_dotenv


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_parses_key_value_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('OPENROUTER_API_KEY="abc"\n# comment\nPORT=8765\n', encoding='utf-8')
            values = load_dotenv(path)
            self.assertEqual(values['OPENROUTER_API_KEY'], 'abc')
            self.assertEqual(values['PORT'], '8765')

    def test_load_dotenv_missing_file(self) -> None:
        values = load_dotenv(Path('/no/such/file'))
        self.assertEqual(values, {})
