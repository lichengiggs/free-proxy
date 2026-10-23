from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from copy import deepcopy
from pathlib import Path

from cachetools import TTLCache


DEFAULT_HEALTH_PATH = Path('data/model-health.json')
HealthState = dict[str, dict[str, object]]
_HEALTH_CACHE: TTLCache[str, HealthState] = TTLCache(maxsize=8, ttl=30)
_HEALTH_LOCK = threading.Lock()


def _clone_state(data: HealthState) -> HealthState:
    return deepcopy(data)


def load_health(path: Path | None = None) -> HealthState:
    target = path or DEFAULT_HEALTH_PATH
    cache_key = str(target)
    cached = _HEALTH_CACHE.get(cache_key)
    if cached is not None:
        return _clone_state(cached)
    if not target.exists():
        return {}
    raw = target.read_text(encoding='utf-8').strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict):
        normalized: HealthState = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, dict):
                normalized[key] = dict(value)
        _HEALTH_CACHE[cache_key] = _clone_state(normalized)
        return normalized
    return {}


def save_health(data: HealthState, path: Path | None = None) -> None:
    target = path or DEFAULT_HEALTH_PATH
    _HEALTH_CACHE[str(target)] = _clone_state(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _HEALTH_LOCK:
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(target))
        except Exception:
            os.unlink(tmp_path)
            raise


def hash_api_key(api_key: str) -> str:
    normalized = (api_key or '').strip()
    if not normalized:
        return ''
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def upsert_health(
    provider: str,
    model: str,
    ok: bool,
    reason: str | None = None,
    *,
    path: Path | None = None,
    now_ts: int | None = None,
    category: str | None = None,
    cooldown_until: int | None = None,
    scope: str | None = None,
    key_hash: str | None = None,
) -> None:
    state = load_health(path)
    key = f'{provider}/{model}'
    previous = state.get(key, {})
    previous_success = int(previous.get('success_streak', 0)) if isinstance(previous.get('success_streak', 0), int) else 0
    previous_failure = int(previous.get('failure_streak', 0)) if isinstance(previous.get('failure_streak', 0), int) else 0
    entry: dict[str, object] = {
        'ok': ok,
        'reason': reason,
        'checked_at': int(time.time()) if now_ts is None else int(now_ts),
        'success_streak': previous_success + 1 if ok else 0,
        'failure_streak': previous_failure + 1 if not ok else 0,
    }
    if not ok:
        if isinstance(category, str) and category:
            entry['category'] = category
        if scope in {'model', 'provider'}:
            entry['scope'] = scope
        if isinstance(cooldown_until, int) and not isinstance(cooldown_until, bool):
            entry['cooldown_until'] = cooldown_until
        if isinstance(key_hash, str) and key_hash:
            entry['key_hash'] = key_hash
    state[key] = entry
    save_health(state, path)
