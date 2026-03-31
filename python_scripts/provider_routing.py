from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from .provider_catalog import get_provider_model_hints


AliasName = Literal['auto']
CandidateSource = Literal['user_requested', 'health_boosted', 'provider_default', 'static_fallback_order']
HealthState = dict[str, dict[str, object]]

PUBLIC_MODEL_ALIASES: tuple[dict[str, str], ...] = (
    {'id': 'free-proxy/auto', 'object': 'model', 'owned_by': 'free-proxy'},
)


@dataclass(frozen=True)
class ResolvedModelRequest:
    provider: str | None
    model: str
    alias: AliasName | None


@dataclass(frozen=True)
class CandidateTarget:
    provider: str
    model: str
    source: CandidateSource
    rank: int


def _health_score(entry: dict[str, object], now_ts: int, ttl_seconds: int) -> int:
    checked_at_value = entry.get('checked_at')
    if not isinstance(checked_at_value, int):
        return 0
    age = max(0, now_ts - checked_at_value)
    if age > ttl_seconds:
        return 0

    success_streak = entry.get('success_streak')
    failure_streak = entry.get('failure_streak')
    score = 0
    if entry.get('ok') is True:
        score += 1000
        if isinstance(success_streak, int):
            score += success_streak * 50
        score -= age
    else:
        score -= 1000
        if isinstance(failure_streak, int):
            score -= failure_streak * 50
        score -= age
    return score


def resolve_model_request(
    *,
    model: str,
    provider: str | None,
    configured: list[str],
    known_providers: set[str],
) -> ResolvedModelRequest:
    normalized_provider = (provider or '').strip() or None
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError('missing model')

    if normalized_provider is not None:
        return ResolvedModelRequest(provider=normalized_provider, model=normalized_model, alias=None)

    if normalized_model in {'auto', 'free-proxy/auto', 'free_proxy/auto'}:
        return ResolvedModelRequest(provider=None, model='auto', alias='auto')
    if '/' in normalized_model:
        maybe_provider, maybe_model = normalized_model.split('/', 1)
        if maybe_provider in known_providers and maybe_model:
            return ResolvedModelRequest(provider=maybe_provider, model=maybe_model, alias=None)

    if configured:
        return ResolvedModelRequest(provider=configured[0], model=normalized_model, alias=None)

    raise ValueError('no configured providers found, please save at least one API key first')


def resolve_alias_candidates(
    alias: AliasName,
    configured: list[str],
    *,
    health: HealthState | None = None,
    now_ts: int | None = None,
    ttl_seconds: int = 600,
) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    if alias != 'auto':
        return ordered

    snapshot = health or {}
    timestamp = int(time.time()) if now_ts is None else now_ts

    ranked: list[tuple[int, int, str, str]] = []
    for provider_rank, provider_name in enumerate(configured):
        hints = get_provider_model_hints(provider_name)
        for model_id in hints:
            score = 0
            entry = snapshot.get(f'{provider_name}/{model_id}')
            if isinstance(entry, dict):
                score = _health_score(entry, timestamp, ttl_seconds)
            ranked.append((score, -provider_rank, provider_name, model_id))

    for _, _, provider_name, model_id in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True):
        pair = (provider_name, model_id)
        if pair not in ordered:
            ordered.append(pair)
    return ordered


def build_auto_candidates(*, requested_model: str | None, configured: list[str], health: HealthState, now_ts: int, ttl_seconds: int) -> list[CandidateTarget]:
    ordered: list[CandidateTarget] = []
    seen: set[tuple[str, str]] = set()

    def push(provider: str, model: str, source: CandidateSource) -> None:
        key = (provider, model)
        if provider not in configured or key in seen:
            return
        seen.add(key)
        ordered.append(CandidateTarget(provider, model, source, len(ordered)))

    if requested_model and '/' in requested_model:
        provider_name, model_id = requested_model.split('/', 1)
        push(provider_name, model_id, 'user_requested')

    ranked: list[tuple[int, int, str, str]] = []
    for provider_rank, provider_name in enumerate(configured):
        hints = get_provider_model_hints(provider_name)
        for model_id in hints:
            entry = health.get(f'{provider_name}/{model_id}')
            score = _health_score(entry, now_ts, ttl_seconds) if isinstance(entry, dict) else 0
            ranked.append((score, -provider_rank, provider_name, model_id))

    for _, _, provider_name, model_id in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True):
        push(provider_name, model_id, 'health_boosted' if isinstance(health.get(f'{provider_name}/{model_id}'), dict) else 'provider_default')

    return ordered


def choose_candidates(
    *,
    provider: str,
    requested_model: str | None,
    health: HealthState,
    hints: list[str],
    now_ts: int,
    ttl_seconds: int,
) -> list[str]:
    ordered: list[str] = []
    if requested_model:
        ordered.append(requested_model)

    healthy_models: list[tuple[int, str]] = []
    for key, value in health.items():
        if not key.startswith(f'{provider}/'):
            continue
        ok_value = value.get('ok')
        checked_at_value = value.get('checked_at')
        if ok_value is not True or not isinstance(checked_at_value, int):
            continue
        if now_ts - checked_at_value > ttl_seconds:
            continue
        model_id = key.split('/', 1)[1]
        healthy_models.append((checked_at_value, model_id))

    for _, model_id in sorted(healthy_models, key=lambda item: item[0], reverse=True):
        if model_id not in ordered:
            ordered.append(model_id)

    for hint in hints:
        if hint not in ordered:
            ordered.append(hint)

    return ordered
