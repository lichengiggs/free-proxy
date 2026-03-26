from __future__ import annotations

import json
import time
from pathlib import Path


DEFAULT_TOKEN_LIMIT_PATH = Path('data/token-limits.json')

TokenLimitState = dict[str, dict[str, int | str]]


def load_token_limits(path: Path | None = None) -> TokenLimitState:
    target = path or DEFAULT_TOKEN_LIMIT_PATH
    if not target.exists():
        return {}
    raw = target.read_text(encoding='utf-8').strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}

    state: TokenLimitState = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized: dict[str, int | str] = {}
        for field, item in value.items():
            if field in {'input_tokens_limit', 'output_tokens_limit', 'updated_at'} and isinstance(item, int):
                normalized[field] = item
            elif field == 'source' and isinstance(item, str):
                normalized[field] = item
        if normalized:
            state[key] = normalized
    return state


def upsert_token_limit(
    provider: str,
    model: str,
    *,
    input_tokens_limit: int,
    output_tokens_limit: int,
    source: str,
    path: Path | None = None,
    now_ts: int | None = None,
) -> None:
    target = path or DEFAULT_TOKEN_LIMIT_PATH
    state = load_token_limits(target)
    state[f'{provider}/{model}'] = {
        'input_tokens_limit': int(input_tokens_limit),
        'output_tokens_limit': int(output_tokens_limit),
        'source': source,
        'updated_at': int(time.time()) if now_ts is None else int(now_ts),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
