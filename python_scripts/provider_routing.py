from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from .provider_catalog import CLOUDFLARE_PAID_MODEL_IDS, get_provider_model_hints


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


def _cooldown_deadline(entry: dict[str, object]) -> int | None:
    value = entry.get('cooldown_until')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def cooldown_active(entry: dict[str, object], now_ts: int, current_key_hash: str | None = None) -> bool:
    deadline = _cooldown_deadline(entry)
    if deadline is None or deadline <= now_ts:
        return False
    if entry.get('category') == 'auth':
        stored_hash = entry.get('key_hash')
        current_hash = (current_key_hash or '').strip()
        if isinstance(stored_hash, str) and stored_hash and current_hash and stored_hash != current_hash:
            return False
    return True


def provider_cooldown_active(health: HealthState, provider: str, now_ts: int, current_key_hash: str | None = None) -> bool:
    prefix = f'{provider}/'
    for key, entry in health.items():
        if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(entry, dict):
            continue
        if entry.get('scope') != 'provider':
            continue
        if cooldown_active(entry, now_ts, current_key_hash):
            return True
    return False


def candidate_in_cooldown(health: HealthState, provider: str, model: str, now_ts: int, current_key_hash: str | None = None) -> bool:
    if provider_cooldown_active(health, provider, now_ts, current_key_hash):
        return True
    entry = health.get(f'{provider}/{model}')
    if isinstance(entry, dict) and cooldown_active(entry, now_ts, current_key_hash):
        return True
    return False


_SAMBANOVA_LIST_PRIORITY: tuple[str, ...] = (
    'gpt-oss-120b',
    'DeepSeek-V3.1',
    'Meta-Llama-3.3-70B-Instruct',
)
_GEMINI_REJECTED_TOKENS = frozenset({'pro', 'argon'})


def _model_id_tokens(model_id: str) -> set[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in model_id.lower():
        if char.isalnum():
            current.append(char)
            continue
        if current:
            tokens.append(''.join(current))
            current = []
    if current:
        tokens.append(''.join(current))
    return set(tokens)


def _checked_at(entry: dict[str, object]) -> int | None:
    value = entry.get('checked_at')
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _latest_successful_model(
    health: HealthState,
    provider: str,
    now_ts: int,
    current_key_hash: str | None,
) -> str | None:
    prefix = f'{provider}/'
    best_at: int | None = None
    best_model: str | None = None
    for key, entry in health.items():
        if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(entry, dict):
            continue
        if entry.get('ok') is not True:
            continue
        checked_at = _checked_at(entry)
        if checked_at is None:
            continue
        model_id = key[len(prefix):]
        if not model_id:
            continue
        if provider == 'cloudflare' and model_id in CLOUDFLARE_PAID_MODEL_IDS:
            continue
        if candidate_in_cooldown(health, provider, model_id, now_ts, current_key_hash):
            continue
        if best_at is None or checked_at >= best_at:
            best_at = checked_at
            best_model = model_id
    return best_model


def _clean_model_ids(models: list[str]) -> list[str]:
    cleaned: list[str] = []
    for model in models:
        if not isinstance(model, str):
            continue
        text = model.strip()
        if text:
            cleaned.append(text)
    return cleaned


def _select_openrouter(models: list[str]) -> str | None:
    if 'openrouter/free' in models:
        return 'openrouter/free'
    return models[0] if models else None


def _select_gemini(models: list[str]) -> str | None:
    eligible = [model for model in models if _GEMINI_REJECTED_TOKENS.isdisjoint(_model_id_tokens(model))]
    for model in eligible:
        if 'flash-lite' in model.lower():
            return model
    for model in eligible:
        if 'flash' in model.lower():
            return model
    return eligible[0] if eligible else None


def _select_groq(models: list[str]) -> str | None:
    for model in models:
        if model.startswith('openai/gpt-oss-') or model.startswith('qwen/'):
            return model
    return None


def _select_sambanova(models: list[str]) -> str | None:
    for model_id in _SAMBANOVA_LIST_PRIORITY:
        if model_id in models:
            return model_id
    return models[0] if models else None


def _select_cloudflare(models: list[str]) -> str | None:
    for model in models:
        if model not in CLOUDFLARE_PAID_MODEL_IDS:
            return model
    return None


def select_listed_model(provider: str, models: list[str]) -> str | None:
    """Pick one refreshed auto candidate from an already filtered model list.

    Args:
        provider: Catalog provider name.
        models: Model ids after the adapter's existing ``/models`` filter.

    Returns:
        The model to insert after a remembered success, or None when this list
        should not contribute a candidate. Cloudflare skips the paid model ids
        and returns None when every remaining id is paid, so the caller uses
        the single hint.

    Raises:
        None.
    """
    cleaned = _clean_model_ids(models)
    if provider == 'openrouter':
        return _select_openrouter(cleaned)
    if provider == 'gemini':
        return _select_gemini(cleaned)
    if provider == 'groq':
        return _select_groq(cleaned)
    if provider == 'sambanova':
        return _select_sambanova(cleaned)
    if provider == 'cloudflare':
        return _select_cloudflare(cleaned)
    return cleaned[0] if cleaned else None


def _refreshed_model(provider: str, listed_models: dict[str, list[str] | None] | None) -> str | None:
    if listed_models is None or provider not in listed_models:
        return None
    models = listed_models[provider]
    if not models:
        return None
    return select_listed_model(provider, models)


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
    if alias != 'auto':
        return []

    snapshot = health or {}
    timestamp = int(time.time()) if now_ts is None else now_ts
    return [
        (item.provider, item.model)
        for item in build_auto_candidates(
            requested_model=None,
            configured=configured,
            health=snapshot,
            now_ts=timestamp,
            ttl_seconds=ttl_seconds,
        )
    ]


def build_auto_candidates(
    *,
    requested_model: str | None,
    configured: list[str],
    health: HealthState,
    now_ts: int,
    ttl_seconds: int,
    key_hashes: dict[str, str] | None = None,
    listed_models: dict[str, list[str] | None] | None = None,
) -> list[CandidateTarget]:
    """Build the ``free-proxy/auto`` candidate list for one request.

    Args:
        requested_model: Optional ``provider/model`` preference. It stays first.
        configured: Configured provider names, in catalog order.
        health: Local health records. Entries for providers outside ``configured`` are ignored.
        now_ts: Current timestamp used for cooldown checks.
        ttl_seconds: Kept for callers. Remembered successes stay eligible after this TTL;
            cooldown is read from ``cooldown_until``.
        key_hashes: Current API-key hashes, used to lift auth cooldowns.
        listed_models: Per-provider ``list_models()`` results from this request.
            ``None`` as the map, a missing provider, ``None`` as the value, or an empty
            list means the list failed or had no qualified model, so the single hint is used.
            A provider already in ``rate_limit``, ``quota``, or ``auth`` cooldown is skipped
            entirely, including when this map contains models for it.

    Returns:
        Candidates in attempt order. Each configured provider contributes its latest
        uncooled success, then one refreshed model when that model differs, otherwise
        its single hint. Cloudflare never contributes one of the paid model ids.

    Raises:
        KeyError: A configured provider is missing from the catalog when its hint is needed.
    """
    del ttl_seconds
    ordered: list[CandidateTarget] = []
    seen: set[tuple[str, str]] = set()
    hashes = key_hashes or {}

    def push(provider: str, model: str, source: CandidateSource) -> None:
        if provider == 'cloudflare' and model in CLOUDFLARE_PAID_MODEL_IDS:
            return
        key = (provider, model)
        if provider not in configured or key in seen:
            return
        if candidate_in_cooldown(health, provider, model, now_ts, hashes.get(provider)):
            return
        seen.add(key)
        ordered.append(CandidateTarget(provider, model, source, len(ordered)))

    if requested_model and '/' in requested_model:
        provider_name, model_id = requested_model.split('/', 1)
        push(provider_name, model_id, 'user_requested')

    for provider_name in configured:
        key_hash = hashes.get(provider_name)
        if provider_cooldown_active(health, provider_name, now_ts, key_hash):
            continue
        success = _latest_successful_model(health, provider_name, now_ts, key_hash)
        if success:
            push(provider_name, success, 'health_boosted')
        refreshed = _refreshed_model(provider_name, listed_models)
        if refreshed:
            push(provider_name, refreshed, 'provider_default')
            continue
        hints = get_provider_model_hints(provider_name)
        if hints:
            push(provider_name, hints[0], 'provider_default')

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
