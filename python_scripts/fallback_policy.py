from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Literal

FallbackAction = Literal['stop', 'retry_same_provider', 'next_candidate']
CooldownScope = Literal['model', 'provider']

RATE_LIMIT_DEFAULT_SECONDS = 60
RATE_LIMIT_MAX_SECONDS = 15 * 60
QUOTA_COOLDOWN_SECONDS = 6 * 60 * 60
TRANSIENT_MODEL_COOLDOWN_SECONDS = 30
UNKNOWN_COOLDOWN_SECONDS = 60
AUTH_COOLDOWN_SECONDS = 100 * 365 * 24 * 60 * 60


@dataclass(frozen=True)
class FallbackContext:
    attempt_count: int
    same_provider_attempts: int
    max_same_provider_attempts: int = 2
    max_total_attempts: int = 5
    backoff_multiplier: float = 1.5


@dataclass(frozen=True)
class FallbackDecision:
    action: FallbackAction
    sleep_seconds: float = 0.0


@dataclass(frozen=True)
class CooldownPlan:
    category: str
    scope: CooldownScope
    cooldown_until: int


def decide_next_action(context: FallbackContext, attempt) -> FallbackDecision:
    if attempt.ok:
        return FallbackDecision('stop')
    if context.attempt_count >= context.max_total_attempts:
        return FallbackDecision('stop')
    # auth 结束的是当前 provider。转发循环记下 provider 冷却后，继续其他 provider。
    if attempt.category == 'auth':
        return FallbackDecision('stop')
    if attempt.category == 'token_limit':
        if context.same_provider_attempts < context.max_same_provider_attempts:
            return FallbackDecision('retry_same_provider')
        return FallbackDecision('next_candidate')
    if attempt.category == 'rate_limit':
        return FallbackDecision('next_candidate', 0.0)
    if attempt.category in {'quota', 'model_not_found', 'network', 'server'}:
        return FallbackDecision('next_candidate')
    # 未知分类（如上游返回 Unsupported parameter 400）不应终止整条链路：
    # 视为当前 Provider 不兼容，跳到下一个候选。总尝试次数由 max_total_attempts 兜底。
    return FallbackDecision('next_candidate')


def parse_retry_after(value: str | None, now_ts: int) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    seconds = _retry_after_seconds(text, now_ts)
    if seconds is None or seconds <= 0 or seconds > RATE_LIMIT_MAX_SECONDS:
        return None
    return seconds


def plan_cooldown(*, category: str, now_ts: int, retry_after: str | None = None, ttl_seconds: int) -> CooldownPlan | None:
    if category == 'token_limit':
        return None
    if category == 'rate_limit':
        seconds = parse_retry_after(retry_after, now_ts)
        if seconds is None:
            seconds = RATE_LIMIT_DEFAULT_SECONDS
        return CooldownPlan(category, 'provider', int(now_ts) + seconds)
    if category == 'quota':
        return CooldownPlan(category, 'provider', int(now_ts) + QUOTA_COOLDOWN_SECONDS)
    if category == 'auth':
        return CooldownPlan(category, 'provider', int(now_ts) + AUTH_COOLDOWN_SECONDS)
    if category in {'server', 'network'}:
        return CooldownPlan(category, 'model', int(now_ts) + TRANSIENT_MODEL_COOLDOWN_SECONDS)
    if category == 'model_not_found':
        window = ttl_seconds if isinstance(ttl_seconds, int) and ttl_seconds > 0 else 0
        return CooldownPlan(category, 'model', int(now_ts) + window)
    if category == 'unknown':
        return CooldownPlan(category, 'model', int(now_ts) + UNKNOWN_COOLDOWN_SECONDS)
    return None


def _retry_after_seconds(text: str, now_ts: int) -> int | None:
    numeric = text.lstrip('-').replace('.', '', 1)
    if numeric.isdigit():
        try:
            return int(float(text))
        except ValueError:
            return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp()) - int(now_ts)
