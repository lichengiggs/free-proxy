from __future__ import annotations

import os
import unittest

from python_scripts.provider_catalog import PROVIDERS, configured_provider_names, get_provider, list_providers


class ProviderCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop('GEMINI_API_KEY', None)
        os.environ.pop('OFOX_API_KEY', None)

    def test_get_provider_returns_catalog_item(self) -> None:
        provider = get_provider('openrouter')
        self.assertEqual(provider.name, 'openrouter')
        self.assertEqual(provider.api_key_env, 'OPENROUTER_API_KEY')

    def test_get_provider_returns_ofox_catalog_item(self) -> None:
        provider = get_provider('ofox')
        self.assertEqual(provider.name, 'ofox')
        self.assertEqual(provider.base_url, 'https://api.ofox.ai/v1')
        self.assertEqual(provider.api_key_env, 'OFOX_API_KEY')

    def test_get_provider_returns_amd_catalog_item(self) -> None:
        provider = get_provider('amd')
        self.assertEqual(provider.name, 'amd')
        self.assertEqual(provider.base_url, 'https://developer.amd.com.cn/radeon/api/v1')
        self.assertEqual(provider.api_key_env, 'AMD_API_KEY')
        self.assertEqual(provider.format, 'openai')
        self.assertEqual(provider.model_hints, ('DeepSeek-V4-Flash', 'MiniCPM5-2B'))
        self.assertEqual(PROVIDERS[-1].name, 'amd')

    def test_amd_api_key_configures_amd(self) -> None:
        self.assertEqual(configured_provider_names({'AMD_API_KEY': 'test-key'}), ['amd'])
        self.assertNotIn('amd', configured_provider_names({}))
        self.assertNotIn('amd', configured_provider_names({'AMD_TOKEN': 'test-key'}))

    def test_list_providers_keeps_declared_order(self) -> None:
        names = [item.name for item in list_providers()]
        self.assertEqual(names, [item.name for item in PROVIDERS])

    def test_configured_provider_names_reads_env_from_catalog(self) -> None:
        names = configured_provider_names({'GEMINI_API_KEY': 'y', 'OFOX_API_KEY': 'z', 'LONGCAT_API_KEY': 'x'})
        self.assertEqual(names, ['ofox', 'gemini'])
        self.assertNotIn('longcat', names)

    def test_longcat_api_key_does_not_configure_any_provider(self) -> None:
        names = configured_provider_names({'LONGCAT_API_KEY': 'x'})
        self.assertEqual(names, [])

    def test_get_provider_treats_longcat_as_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_provider('longcat')
        self.assertTrue(all(provider.name != 'longcat' for provider in PROVIDERS))
        self.assertTrue(all('api.longcat.chat' not in provider.base_url for provider in PROVIDERS))

    def test_all_providers_have_required_fields(self) -> None:
        for p in PROVIDERS:
            self.assertTrue(p.name, f'{p} missing name')
            self.assertTrue(p.base_url, f'{p} missing base_url')
            self.assertTrue(p.api_key_env, f'{p} missing api_key_env')
            self.assertTrue(p.model_hints, f'{p} missing model_hints')

    def test_model_hints_returns_list(self) -> None:
        from python_scripts.provider_catalog import get_provider_model_hints
        hints = get_provider_model_hints('groq')
        self.assertEqual(hints, ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile'])
