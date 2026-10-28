from __future__ import annotations

import unittest

from python_scripts.provider_routing import CandidateTarget, build_auto_candidates, choose_candidates, resolve_alias_candidates, resolve_model_request


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
                ('groq', 'llama-3.3-70b-versatile'),
                ('gemini', 'gemini-3.1-flash-lite-preview'),
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
                CandidateTarget('mistral', 'mistral-small-latest', 'provider_default', 2),
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
