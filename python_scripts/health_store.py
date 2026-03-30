from __future__ import annotations

import json
import time
from pathlib import Path


DEFAULT_HEALTH_PATH = Path('data/model-health.json')
HealthState = dict[str, dict[str, object]]


def load_health(path: Path | None = None) -> HealthState:
    target = path or DEFAULT_HEALTH_PATH
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
                normalized[key] = value
        return normalized
    return {}


def save_health(data: HealthState, path: Path | None = None) -> None:
    target = path or DEFAULT_HEALTH_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def upsert_health(
    provider: str,
    model: str,
    ok: bool,
    reason: str | None = None,
    *,
    path: Path | None = None,
    now_ts: int | None = None,
) -> None:
    state = load_health(path)
    key = f'{provider}/{model}'
    state[key] = {
        'ok': ok,
        'reason': reason,
        'checked_at': int(time.time()) if now_ts is None else int(now_ts),
    }
    save_health(state, path)
