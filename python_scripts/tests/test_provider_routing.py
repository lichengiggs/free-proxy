from __future__ import annotations

import unittest
from pathlib import Path
from pathlib import Path

from python_scripts.provider_routing import CandidateTarget, build_auto_candidates, choose_candidates, resolve_alias_candidates, resolve_model_request, select_listed_model


class ProviderRoutingTests(unittest.TestCase):
    def test_resolve_model_request_supports_public_aliases(self) -> None:
        target = resolve_model_request(
            model='free-proxy/auto',
            provider=None,
            configured=['gemini'],
            known_providers={'gemini', 'openrouter'},
        )
        self.assertEqual(target.alias, 'auto')
        self.assertIsNone(target.provider)

    def test_resolve_model_request_supports_provider_prefixed_model(self) -> None:
        target = resolve_model_request(
            model='openrouter/m1',
            provider=None,
            configured=['openrouter'],
            known_providers={'openrouter'},
        )
        self.assertEqual(target.provider, 'openrouter')
        self.assertEqual(target.model, 'm1')

    def test_resolve_alias_candidates_keeps_declared_priority(self) -> None:
        candidates = resolve_alias_candidates('auto', configured=['groq', 'gemini', 'openrouter'])
        self.assertEqual(candidates[0], ('groq', 'llama-3.1-8b-instant'))
        self.assertIn(('gemini', 'gemini-3.1-flash-lite-preview'), candidates)
        self.assertTrue(all(provider != 'longcat' for provider, _model in candidates))
        self.assertTrue(all(provider != 'github' for provider, _model in candidates))

    def test_auto_candidates_follow_configured_provider_order(self) -> None:
        target = resolve_model_request(
            model='free-proxy/auto',
            provider=None,
            configured=['groq', 'gemini', 'mistral'],
            known_providers={'groq', 'gemini', 'mistral'},
        )
        self.assertEqual(target.alias, 'auto')

        items = build_auto_candidates(
            requested_model=target.model,
            configured=['groq', 'gemini', 'mistral'],
            health={},
            now_ts=150,
            ttl_seconds=60,
        )

        pairs = [(item.provider, item.model) for item in items]
        self.assertEqual(
            pairs[:3],
            [
                ('groq', 'llama-3.1-8b-instant'),
                ('gemini', 'gemini-3.1-flash-lite-preview'),
                ('mistral', 'mistral-large-latest'),
            ],
        )
        self.assertTrue(all(provider != 'longcat' for provider, _model in pairs))
        self.assertTrue(all(provider != 'github' for provider, _model in pairs))
        self.assertTrue(all('models.github.ai' not in model for _provider, model in pairs))

    def test_longcat_prefixed_model_follows_unknown_provider_rule(self) -> None:
        target = resolve_model_request(
            model='longcat/LongCat-Flash-Lite',
            provider=None,
            configured=['groq', 'gemini'],
            known_providers={'groq', 'gemini', 'openrouter'},
        )
        self.assertEqual(target.provider, 'groq')
        self.assertEqual(target.model, 'longcat/LongCat-Flash-Lite')
        self.assertIsNone(target.alias)

        items = build_auto_candidates(
            requested_model='longcat/LongCat-Flash-Lite',
            configured=['groq', 'gemini'],
            health={'longcat/LongCat-Flash-Lite': {'ok': True, 'checked_at': 120}},
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertTrue(items)
        self.assertTrue(all(item.provider != 'longcat' for item in items))
        self.assertEqual(items[0].provider, 'groq')

    def test_github_prefixed_model_follows_unknown_provider_rule(self) -> None:
        target = resolve_model_request(
            model='github/gpt-4o',
            provider=None,
            configured=['groq', 'gemini'],
            known_providers={'groq', 'gemini', 'openrouter'},
        )
        self.assertEqual(target.provider, 'groq')
        self.assertEqual(target.model, 'github/gpt-4o')
        self.assertIsNone(target.alias)

        items = build_auto_candidates(
            requested_model='github/gpt-4o',
            configured=['groq', 'gemini'],
            health={'github/gpt-4o': {'ok': True, 'checked_at': 120}},
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertTrue(items)
        self.assertTrue(all(item.provider != 'github' for item in items))
        self.assertTrue(all('models.github.ai' not in item.model for item in items))
        self.assertEqual(items[0].provider, 'groq')

    def test_build_auto_candidates_prefers_requested_then_health_then_hints(self) -> None:
        health = {
            'mistral/mistral-large-latest': {'ok': True, 'checked_at': 120},
        }
        items = build_auto_candidates(
            requested_model='mistral/mistral-medium-latest',
            configured=['mistral', 'openrouter'],
            health=health,
            now_ts=150,
            ttl_seconds=60,
        )
        self.assertEqual(
            items[:3],
            [
                CandidateTarget('mistral', 'mistral-medium-latest', 'user_requested', 0),
                CandidateTarget('mistral', 'mistral-large-latest', 'health_boosted', 1),
                CandidateTarget('openrouter', 'openrouter/auto:free', 'provider_default', 2),
            ],
        )

    def test_choose_candidates_prefers_requested_then_healthy_then_hints(self) -> None:
        health = {
            'openrouter/model-ok': {'ok': True, 'checked_at': 100},
            'openrouter/model-old': {'ok': True, 'checked_at': 1},
            'openrouter/model-bad': {'ok': False, 'checked_at': 100},
        }
        candidates = choose_candidates(
            provider='openrouter',
            requested_model='requested-model',
            health=health,
            hints=['model-ok', 'hint-model'],
            now_ts=120,
            ttl_seconds=30,
        )
        self.assertEqual(candidates[0], 'requested-model')
        self.assertEqual(candidates[1], 'model-ok')
        self.assertIn('hint-model', candidates)
        self.assertNotIn('model-old', candidates)

    def test_build_auto_candidates_skips_models_inside_cooldown(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'model', 'category': 'server', 'cooldown_until': now + 30},
            'groq/llama-3.3-70b-versatile': {'scope': 'model', 'category': 'server', 'cooldown_until': now + 30},
        }
        items = build_auto_candidates(
            requested_model=None,
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
        )
        providers = {item.provider for item in items}
        self.assertNotIn('groq', providers)
        self.assertIn('gemini', providers)

    def test_build_auto_candidates_returns_model_when_cooldown_reaches_now(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'model', 'category': 'server', 'cooldown_until': now},
        }
        items = build_auto_candidates(
            requested_model=None,
            configured=['groq'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
        )
        self.assertIn('llama-3.1-8b-instant', [item.model for item in items])

    def test_provider_cooldown_removes_every_hint_from_one_record(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'provider', 'category': 'rate_limit', 'cooldown_until': now + 60},
        }
        items = build_auto_candidates(
            requested_model=None,
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
        )
        pairs = [(item.provider, item.model) for item in items]
        self.assertNotIn(('groq', 'llama-3.1-8b-instant'), pairs)
        self.assertNotIn(('groq', 'llama-3.3-70b-versatile'), pairs)
        self.assertIn(('gemini', 'gemini-3.1-flash-lite-preview'), pairs)

    def test_cooled_preferred_model_yields_to_another_provider(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'provider', 'category': 'quota', 'cooldown_until': now + 60},
        }
        items = build_auto_candidates(
            requested_model='groq/llama-3.1-8b-instant',
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
        )
        self.assertTrue(items)
        self.assertEqual(items[0].provider, 'gemini')
        self.assertTrue(all(item.provider != 'groq' for item in items))

    def test_build_auto_candidates_is_empty_when_every_candidate_is_cooling(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {'scope': 'provider', 'category': 'rate_limit', 'cooldown_until': now + 5},
            'gemini/gemini-3.1-flash-lite-preview': {'scope': 'provider', 'category': 'quota', 'cooldown_until': now + 5},
        }
        items = build_auto_candidates(
            requested_model='groq/llama-3.1-8b-instant',
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
        )
        self.assertEqual(items, [])

    def test_auth_cooldown_lifts_when_provider_key_hash_changes(self) -> None:
        now = 1_000
        health = {
            'groq/llama-3.1-8b-instant': {
                'scope': 'provider',
                'category': 'auth',
                'cooldown_until': now + 10**7,
                'key_hash': 'old-hash',
            },
        }
        blocked = build_auto_candidates(
            requested_model=None,
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
            key_hashes={'groq': 'old-hash'},
        )
        self.assertTrue(all(item.provider != 'groq' for item in blocked))
        released = build_auto_candidates(
            requested_model=None,
            configured=['groq', 'gemini'],
            health=health,
            now_ts=now,
            ttl_seconds=600,
            key_hashes={'groq': 'new-hash'},
        )
        self.assertEqual(released[0].provider, 'groq')

    def test_auto_places_remembered_model_before_a_different_refreshed_model(self) -> None:
        items = build_auto_candidates(
            requested_model=None,
            configured=['openrouter'],
            health={'openrouter/old:free': {'ok': True, 'checked_at': 100}},
            now_ts=150,
            ttl_seconds=600,
            listed_models={'openrouter': ['meta/llama:free', 'openrouter/free', 'qwen/qwen3:free']},
        )
        self.assertEqual(
            [(item.provider, item.model) for item in items],
            [('openrouter', 'old:free'), ('openrouter', 'openrouter/free')],
        )

    def test_auto_uses_only_the_provider_hint_when_the_model_list_fails(self) -> None:
        failed = build_auto_candidates(
            requested_model=None,
            configured=['groq'],
            health={},
            now_ts=150,
            ttl_seconds=600,
            listed_models={'groq': None},
        )
        empty = build_auto_candidates(
            requested_model=None,
            configured=['groq'],
            health={},
            now_ts=150,
            ttl_seconds=600,
            listed_models={'groq': []},
        )
        self.assertEqual([(item.provider, item.model) for item in failed], [('groq', 'llama-3.1-8b-instant')])
        self.assertEqual([(item.provider, item.model) for item in empty], [('groq', 'llama-3.1-8b-instant')])

    def test_auto_skips_a_provider_that_is_cooling_even_when_its_list_has_models(self) -> None:
        now = 1_000
        items = build_auto_candidates(
            requested_model=None,
            configured=['groq', 'gemini'],
            health={'groq/llama-3.1-8b-instant': {'ok': True, 'checked_at': now, 'scope': 'provider', 'category': 'rate_limit', 'cooldown_until': now + 60}},
            now_ts=now,
            ttl_seconds=600,
            listed_models={'groq': ['openai/gpt-oss-20b'], 'gemini': ['gemini-2.0-flash']},
        )
        self.assertTrue(all(item.provider != 'groq' for item in items))
        self.assertEqual([(item.provider, item.model) for item in items], [('gemini', 'gemini-2.0-flash')])

    def test_openrouter_refresh_prefers_openrouter_free(self) -> None:
        self.assertEqual(
            select_listed_model('openrouter', ['meta/llama:free', 'openrouter/free', 'qwen/qwen3:free']),
            'openrouter/free',
        )
        self.assertEqual(select_listed_model('openrouter', ['meta/llama:free']), 'meta/llama:free')

    def test_gemini_refresh_skips_pro_and_argon_and_prefers_flash_lite(self) -> None:
        picked = select_listed_model(
            'gemini',
            ['gemini-2.5-pro', 'gemini-3-argon', 'gemini-2.0-flash', 'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite-preview'],
        )
        self.assertEqual(picked, 'gemini-2.5-flash-lite')
        self.assertIsNone(select_listed_model('gemini', ['gemini-2.5-pro', 'gemini-3-argon']))
        self.assertEqual(
            select_listed_model('gemini', ['gemini-2.5-pro', 'gemini-3.1-flash-lite-preview']),
            'gemini-3.1-flash-lite-preview',
        )

    def test_groq_refresh_skips_models_outside_gpt_oss_and_qwen(self) -> None:
        self.assertIsNone(select_listed_model('groq', ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768']))
        self.assertEqual(
            select_listed_model('groq', ['llama-3.3-70b-versatile', 'qwen/qwen3-32b', 'openai/gpt-oss-20b']),
            'qwen/qwen3-32b',
        )

    def test_sambanova_refresh_uses_named_priority_then_the_first_model(self) -> None:
        self.assertEqual(
            select_listed_model('sambanova', ['other', 'Meta-Llama-3.3-70B-Instruct', 'gpt-oss-120b']),
            'gpt-oss-120b',
        )
        self.assertEqual(select_listed_model('sambanova', ['DeepSeek-V3.1', 'other']), 'DeepSeek-V3.1')
        self.assertEqual(select_listed_model('sambanova', ['first-model', 'second-model']), 'first-model')

    def test_auto_candidate_docs_describe_success_then_refresh_then_hint(self) -> None:
        root = Path(__file__).resolve().parents[2]
        agents = (root / 'AGENTS.md').read_text(encoding='utf-8')
        research = (root / 'docs' / 'research.md').read_text(encoding='utf-8')
        for text in (agents, research):
            self.assertIn('成功记录', text)
            self.assertIn('刷新', text)
            self.assertIn('hint', text)
