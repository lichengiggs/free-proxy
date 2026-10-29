from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from pathlib import Path

from python_scripts.provider_catalog import CLOUDFLARE_PAID_MODEL_IDS, PROVIDERS, configured_provider_names, get_provider, list_providers


@contextmanager
def _env(updates: dict[str, str | None]):
    old = {key: os.environ.get(key) for key in updates}
    for key, value in updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


_CF_ACCOUNT = '0123456789abcDEF0123456789abcDEF'
_CF_ENV_CLEAR = {
    'CLOUDFLARE_API_KEY': None,
    'CLOUDFLARE_ACCOUNT_ID': None,
    'FREE_PROXY_TEST_UPSTREAM': None,
}


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
        self.assertEqual(provider.model_hints, ('DeepSeek-V4-Flash',))
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
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints, ['llama-3.1-8b-instant'])

    def test_each_provider_model_hints_keeps_only_the_first_entry(self) -> None:
        expected = {
            'openrouter': ('openrouter/auto:free',),
            'groq': ('llama-3.1-8b-instant',),
            'gemini': ('gemini-3.1-flash-lite-preview',),
            'mistral': ('mistral-large-latest',),
            'nvidia': ('meta/llama-3.1-70b-instruct',),
            'cloudflare': ('@cf/meta/llama-3.1-8b-instruct',),
            'amd': ('DeepSeek-V4-Flash',),
        }
        self.assertEqual({item.name: item.model_hints for item in PROVIDERS}, expected)
        for item in PROVIDERS:
            self.assertEqual(len(item.model_hints), 1)

    def test_cloudflare_stays_unconfigured_until_token_and_account_id_are_both_valid(self) -> None:
        self.assertNotIn('cloudflare', configured_provider_names({'CLOUDFLARE_API_KEY': 'cf-token-example-1234'}))
        self.assertNotIn('cloudflare', configured_provider_names({'CLOUDFLARE_ACCOUNT_ID': _CF_ACCOUNT}))
        self.assertNotIn('cloudflare', configured_provider_names({
            'CLOUDFLARE_API_KEY': 'cf-token-example-1234',
            'CLOUDFLARE_ACCOUNT_ID': 'not-a-valid-account',
        }))
        self.assertNotIn('cloudflare', configured_provider_names({
            'CLOUDFLARE_API_KEY': '   ',
            'CLOUDFLARE_ACCOUNT_ID': _CF_ACCOUNT,
        }))
        self.assertEqual(
            configured_provider_names({
                'CLOUDFLARE_API_KEY': 'cf-token-example-1234',
                'CLOUDFLARE_ACCOUNT_ID': _CF_ACCOUNT,
            }),
            ['cloudflare'],
        )

    def test_cloudflare_base_url_inserts_account_id_without_changing_case(self) -> None:
        with _env({**_CF_ENV_CLEAR, 'CLOUDFLARE_API_KEY': 'cf-token-example-1234', 'CLOUDFLARE_ACCOUNT_ID': _CF_ACCOUNT}):
            catalog = next(item for item in PROVIDERS if item.name == 'cloudflare')
            self.assertEqual(catalog.base_url, 'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1')
            self.assertEqual(catalog.api_key_env, 'CLOUDFLARE_API_KEY')
            self.assertEqual(catalog.account_id_env, 'CLOUDFLARE_ACCOUNT_ID')
            self.assertEqual([item.name for item in PROVIDERS][-2:], ['cloudflare', 'amd'])
            provider = get_provider('cloudflare')
            self.assertEqual(provider.name, 'cloudflare')
            self.assertEqual(provider.model_hints, ('@cf/meta/llama-3.1-8b-instruct',))
            self.assertEqual(
                provider.base_url,
                f'https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/v1',
            )
            self.assertNotIn('{account_id}', provider.base_url)
            self.assertEqual(catalog.base_url, 'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1')
            self.assertEqual(
                CLOUDFLARE_PAID_MODEL_IDS,
                frozenset({
                    '@cf/moonshotai/kimi-k2.6',
                    '@cf/moonshotai/kimi-k2.7-code',
                    '@cf/zai-org/glm-5.2',
                    '@cf/zai-org/glm-5.3',
                    '@cf/zai-org/glm-5.3-flash',
                    '@cf/deepseek-ai/deepseek-v4-flash-0731',
                    '@cf/deepseek-ai/deepseek-v4.1-flash-1017',
                    '@cf/deepseek-ai/deepseek-v4-pro-0813',
                }),
            )

    def test_invalid_cloudflare_account_id_keeps_name_and_hint(self) -> None:
        invalid_ids = ['', 'a' * 31, 'a' * 33, 'g' * 32, 'abcd/ef0123456789abcdef0123456789', '..' + 'ab' * 15, '0123456789abcdef 123456789abcdef']
        for account_id in invalid_ids:
            with self.subTest(account_id=account_id):
                with _env({**_CF_ENV_CLEAR, 'CLOUDFLARE_API_KEY': 'cf-token-example-1234', 'CLOUDFLARE_ACCOUNT_ID': account_id}):
                    provider = get_provider('cloudflare')
                    self.assertEqual(provider.name, 'cloudflare')
                    self.assertEqual(provider.model_hints, ('@cf/meta/llama-3.1-8b-instruct',))
                    self.assertEqual(provider.base_url, 'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1')
                    if account_id:
                        self.assertNotIn(account_id, provider.base_url)

    def test_cloudflare_test_upstream_does_not_insert_account_id(self) -> None:
        with _env({
            **_CF_ENV_CLEAR,
            'FREE_PROXY_TEST_UPSTREAM': 'http://127.0.0.1:9',
            'CLOUDFLARE_API_KEY': 'cf-token-example-1234',
            'CLOUDFLARE_ACCOUNT_ID': _CF_ACCOUNT,
        }):
            provider = get_provider('cloudflare')
            self.assertEqual(provider.base_url, 'http://127.0.0.1:9')
            self.assertNotIn(_CF_ACCOUNT, provider.base_url)
            self.assertNotIn('api.cloudflare.com', provider.base_url)
            self.assertEqual(provider.model_hints, ('@cf/meta/llama-3.1-8b-instruct',))
            self.assertNotIn('cloudflare', configured_provider_names({'CLOUDFLARE_API_KEY': 'cf-token-example-1234'}))

    def test_readme_and_changelog_say_cloudflare_needs_token_and_account_id(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for name in ('README.md', 'README_EN.md'):
            text = (root / name).read_text(encoding='utf-8')
            self.assertIn('Cloudflare Workers AI', text)
            self.assertIn('@cf/meta/llama-3.1-8b-instruct', text)
            self.assertIn('API Token', text)
            self.assertIn('Account ID', text)
            self.assertIn('10,000', text)
            self.assertIn('00:00 UTC', text)
            self.assertIn('http://127.0.0.1:8765/v1', text)
        changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
        self.assertIn('Cloudflare Workers AI 需要 API Token 和 Account ID', changelog)
        research = (root / 'docs' / 'research.md').read_text(encoding='utf-8')
        self.assertIn('CLOUDFLARE_ACCOUNT_ID', research)
        self.assertIn('合法 Account ID', research)
