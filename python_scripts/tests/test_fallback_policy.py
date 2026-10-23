from __future__ import annotations

import unittest

from email.utils import formatdate

from python_scripts.fallback_policy import (
    QUOTA_COOLDOWN_SECONDS,
    RATE_LIMIT_DEFAULT_SECONDS,
    RATE_LIMIT_MAX_SECONDS,
    TRANSIENT_MODEL_COOLDOWN_SECONDS,
    UNKNOWN_COOLDOWN_SECONDS,
    FallbackContext,
    decide_next_action,
    parse_retry_after,
    plan_cooldown,
)


class RelayAttemptResult:
    def __init__(self, ok: bool, category: str | None) -> None:
        self.ok = ok
        self.category = category


class FallbackPolicyTests(unittest.TestCase):
    def test_rate_limit_moves_to_next_candidate_with_backoff(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=1)
        decision = decide_next_action(context, RelayAttemptResult(False, 'rate_limit'))
        self.assertEqual(decision.action, 'next_candidate')
        self.assertEqual(decision.sleep_seconds, 0.0)

    def test_token_limit_retries_same_provider_only_twice(self) -> None:
        context = FallbackContext(attempt_count=2, same_provider_attempts=2)
        decision = decide_next_action(context, RelayAttemptResult(False, 'token_limit'))
        self.assertEqual(decision.action, 'next_candidate')

    def test_auth_stops(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(False, 'auth'))
        self.assertEqual(decision.action, 'stop')

    def test_network_error_moves_to_next_candidate(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(False, 'network'))
        self.assertEqual(decision.action, 'next_candidate')

    def test_unknown_error_moves_to_next_candidate(self) -> None:
        # unknown（如上游返回 Unsupported parameter 400）不应终止整条链路，
        # 应视为当前 Provider 不兼容，跳到下一个候选。
        context = FallbackContext(attempt_count=1, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(False, 'unknown'))
        self.assertEqual(decision.action, 'next_candidate')

    def test_retry_same_provider_when_under_limit(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=1)
        decision = decide_next_action(context, RelayAttemptResult(False, 'token_limit'))
        self.assertEqual(decision.action, 'retry_same_provider')

    def test_stops_when_same_provider_attempts_exceeded(self) -> None:
        context = FallbackContext(attempt_count=3, same_provider_attempts=3)
        decision = decide_next_action(context, RelayAttemptResult(False, 'token_limit'))
        # same_provider_attempts=3 >= max_same_provider_attempts=2, so moves to next_candidate
        # But attempt_count=3 < max_total_attempts=5, so doesn't stop yet
        self.assertEqual(decision.action, 'next_candidate')

    def test_stops_when_total_attempts_exceeded(self) -> None:
        context = FallbackContext(attempt_count=6, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(False, 'rate_limit'))
        self.assertEqual(decision.action, 'stop')

    def test_success_returns_stop(self) -> None:
        context = FallbackContext(attempt_count=1, same_provider_attempts=0)
        decision = decide_next_action(context, RelayAttemptResult(True, None))
        self.assertEqual(decision.action, 'stop')

    def test_retry_after_accepts_seconds_and_http_dates_inside_fifteen_minutes(self) -> None:
        now = 1_700_000_000
        self.assertEqual(parse_retry_after('120', now), 120)
        self.assertEqual(parse_retry_after(str(RATE_LIMIT_MAX_SECONDS), now), RATE_LIMIT_MAX_SECONDS)
        self.assertIsNone(parse_retry_after('0', now))
        self.assertIsNone(parse_retry_after('-5', now))
        self.assertIsNone(parse_retry_after(str(RATE_LIMIT_MAX_SECONDS + 1), now))
        self.assertIsNone(parse_retry_after('not-a-date', now))
        header = formatdate(now + 30, usegmt=True)
        parsed = parse_retry_after(header, now)
        self.assertIsNotNone(parsed)
        self.assertGreaterEqual(parsed or 0, 29)
        self.assertLessEqual(parsed or 0, 30)

    def test_plan_cooldown_uses_category_scope_and_duration(self) -> None:
        now = 1_700_000_000
        rate_limit = plan_cooldown(category='rate_limit', now_ts=now, retry_after=None, ttl_seconds=600)
        assert rate_limit is not None
        self.assertEqual(rate_limit.scope, 'provider')
        self.assertEqual(rate_limit.cooldown_until, now + RATE_LIMIT_DEFAULT_SECONDS)

        hinted = plan_cooldown(category='rate_limit', now_ts=now, retry_after='90', ttl_seconds=600)
        assert hinted is not None
        self.assertEqual(hinted.cooldown_until, now + 90)

        too_long = plan_cooldown(category='rate_limit', now_ts=now, retry_after='1200', ttl_seconds=600)
        assert too_long is not None
        self.assertEqual(too_long.cooldown_until, now + RATE_LIMIT_DEFAULT_SECONDS)

        quota = plan_cooldown(category='quota', now_ts=now, ttl_seconds=600)
        assert quota is not None
        self.assertEqual((quota.scope, quota.cooldown_until), ('provider', now + QUOTA_COOLDOWN_SECONDS))

        auth = plan_cooldown(category='auth', now_ts=now, ttl_seconds=600)
        assert auth is not None
        self.assertEqual(auth.scope, 'provider')
        self.assertGreater(auth.cooldown_until, now + QUOTA_COOLDOWN_SECONDS)

        server = plan_cooldown(category='server', now_ts=now, ttl_seconds=600)
        network = plan_cooldown(category='network', now_ts=now, ttl_seconds=600)
        assert server is not None and network is not None
        self.assertEqual(server.scope, 'model')
        self.assertEqual(server.cooldown_until, now + TRANSIENT_MODEL_COOLDOWN_SECONDS)
        self.assertEqual(network.cooldown_until, server.cooldown_until)

        missing = plan_cooldown(category='model_not_found', now_ts=now, ttl_seconds=600)
        assert missing is not None
        self.assertEqual((missing.scope, missing.cooldown_until), ('model', now + 600))

        unknown = plan_cooldown(category='unknown', now_ts=now, ttl_seconds=600)
        assert unknown is not None
        self.assertEqual((unknown.scope, unknown.cooldown_until), ('model', now + UNKNOWN_COOLDOWN_SECONDS))

        self.assertIsNone(plan_cooldown(category='token_limit', now_ts=now, ttl_seconds=600))
