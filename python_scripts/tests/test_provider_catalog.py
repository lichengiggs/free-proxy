from __future__ import annotations

import os
import unittest
from pathlib import Path

from python_scripts.provider_catalog import PROVIDERS, configured_provider_names, get_provider, list_providers


class ProviderCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop('GEMINI_API_KEY', None)

    def test_get_provider_returns_catalog_item(self) -> None:
        provider = get_provider('openrouter')
        self.assertEqual(provider.name, 'openrouter')
        self.assertEqual(provider.api_key_env, 'OPENROUTER_API_KEY')

    def test_get_provider_treats_ofox_as_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_provider('ofox')
        self.assertTrue(all(provider.name != 'ofox' for provider in PROVIDERS))
        self.assertTrue(all('api.ofox.ai' not in provider.base_url for provider in PROVIDERS))
        self.assertTrue(all(provider.api_key_env != 'OFOX_API_KEY' for provider in PROVIDERS))
        self.assertTrue(all('z-ai/glm-4.7-flash:free' not in provider.model_hints for provider in PROVIDERS))

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
        names = configured_provider_names({
            'GEMINI_API_KEY': 'y',
            'GROQ_API_KEY': 'z',
            'OFOX_API_KEY': 'leftover',
            'LONGCAT_API_KEY': 'x',
            'GITHUB_MODELS_API_KEY': 'g',
            'SAMBANOVA_API_KEY': 'sn',
        })
        self.assertEqual(names, ['groq', 'gemini'])
        self.assertNotIn('ofox', names)
        self.assertNotIn('longcat', names)
        self.assertNotIn('github', names)
        self.assertNotIn('sambanova', names)

    def test_ofox_api_key_does_not_configure_any_provider(self) -> None:
        names = configured_provider_names({'OFOX_API_KEY': 'z'})
        self.assertEqual(names, [])

    def test_longcat_api_key_does_not_configure_any_provider(self) -> None:
        names = configured_provider_names({'LONGCAT_API_KEY': 'x'})
        self.assertEqual(names, [])

    def test_get_provider_treats_longcat_as_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_provider('longcat')
        self.assertTrue(all(provider.name != 'longcat' for provider in PROVIDERS))
        self.assertTrue(all('api.longcat.chat' not in provider.base_url for provider in PROVIDERS))

    def test_sambanova_api_key_does_not_configure_any_provider(self) -> None:
        names = configured_provider_names({'SAMBANOVA_API_KEY': 'sn'})
        self.assertEqual(names, [])

    def test_get_provider_treats_sambanova_as_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_provider('sambanova')
        self.assertTrue(all(provider.name != 'sambanova' for provider in PROVIDERS))
        self.assertTrue(all(provider.base_url != 'https://api.sambanova.ai/v1' for provider in PROVIDERS))
        self.assertTrue(all('api.sambanova.ai' not in provider.base_url for provider in PROVIDERS))
        self.assertTrue(all(provider.api_key_env != 'SAMBANOVA_API_KEY' for provider in PROVIDERS))
        for hint in ('DeepSeek-V3.1-Terminus', 'Qwen3-235B', 'Meta-Llama-3.1-8B-Instruct'):
            self.assertTrue(all(hint not in provider.model_hints for provider in PROVIDERS))

    def test_console_no_longer_shows_sambanova_card(self) -> None:
        html = Path(__file__).resolve().parents[1].joinpath('web', 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('SambaNova', html)
        self.assertNotIn('SAMBANOVA_API_KEY', html)
        self.assertNotIn("id: 'sambanova'", html)
        self.assertNotIn('api.sambanova.ai', html)
        self.assertNotIn('cloud.sambanova.ai', html)

    def test_auto_candidates_exclude_sambanova_when_another_provider_is_configured(self) -> None:
        from python_scripts.provider_routing import build_auto_candidates, resolve_alias_candidates, resolve_model_request

        configured = configured_provider_names({
            'GROQ_API_KEY': 'groq-key',
            'SAMBANOVA_API_KEY': 'leftover',
        })
        self.assertEqual(configured, ['groq'])
        known = {provider.name for provider in PROVIDERS}
        target = resolve_model_request(
            model='free-proxy/auto',
            provider=None,
            configured=configured,
            known_providers=known,
        )
        self.assertEqual(target.alias, 'auto')

        candidates = resolve_alias_candidates('auto', configured=configured)
        self.assertTrue(candidates)
        self.assertTrue(all(provider != 'sambanova' for provider, _model in candidates))
        for provider_name, _model in candidates:
            self.assertNotIn('api.sambanova.ai', get_provider(provider_name).base_url)

        items = build_auto_candidates(
            requested_model=None,
            configured=configured,
            health={'sambanova/DeepSeek-V3.1-Terminus': {'ok': True, 'checked_at': 120}},
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertTrue(items)
        self.assertTrue(all(item.provider != 'sambanova' for item in items))
        for item in items:
            self.assertNotIn('api.sambanova.ai', get_provider(item.provider).base_url)

        explicit = resolve_model_request(
            model='sambanova/DeepSeek-V3.1-Terminus',
            provider=None,
            configured=configured,
            known_providers=known,
        )
        self.assertEqual(explicit.provider, 'groq')
        self.assertEqual(explicit.model, 'sambanova/DeepSeek-V3.1-Terminus')
        self.assertIsNone(explicit.alias)
        self.assertNotIn('api.sambanova.ai', get_provider(explicit.provider).base_url)

        routed = build_auto_candidates(
            requested_model='sambanova/DeepSeek-V3.1-Terminus',
            configured=configured,
            health={'sambanova/DeepSeek-V3.1-Terminus': {'ok': True, 'checked_at': 120}},
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertTrue(routed)
        self.assertEqual(routed[0].provider, 'groq')
        self.assertTrue(all(item.provider != 'sambanova' for item in routed))
        for item in routed:
            self.assertNotIn('api.sambanova.ai', get_provider(item.provider).base_url)

    def test_github_models_key_does_not_configure_any_provider(self) -> None:
        names = configured_provider_names({'GITHUB_MODELS_API_KEY': 'x'})
        self.assertEqual(names, [])

    def test_get_provider_treats_github_as_unknown(self) -> None:
        with self.assertRaises(KeyError):
            get_provider('github')
        self.assertTrue(all(provider.name != 'github' for provider in PROVIDERS))
        self.assertTrue(all('models.github.ai' not in provider.base_url for provider in PROVIDERS))
        self.assertTrue(all(provider.api_key_env != 'GITHUB_MODELS_API_KEY' for provider in PROVIDERS))

    def test_console_no_longer_shows_github_models_card(self) -> None:
        html = Path(__file__).resolve().parents[1].joinpath('web', 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('GitHub Models', html)
        self.assertNotIn('GITHUB_MODELS_API_KEY', html)
        self.assertNotIn("id: 'github'", html)

    def test_console_no_longer_shows_ofox_card(self) -> None:
        html = Path(__file__).resolve().parents[1].joinpath('web', 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('Ofox', html)
        self.assertNotIn('OFOX_API_KEY', html)
        self.assertNotIn("id: 'ofox'", html)
        self.assertNotIn('api.ofox.ai', html)
        self.assertNotIn('ofox.ai', html)

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
