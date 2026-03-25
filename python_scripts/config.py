from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DOTENV_PATH = ROOT_DIR / '.env'


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key_env: str
    format: str


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec('openrouter', 'https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', 'openai'),
    ProviderSpec('groq', 'https://api.groq.com/openai/v1', 'GROQ_API_KEY', 'openai'),
    ProviderSpec('opencode', 'https://opencode.ai/zen/v1', 'OPENCODE_API_KEY', 'openai'),
    ProviderSpec('gemini', 'https://generativelanguage.googleapis.com/v1beta', 'GEMINI_API_KEY', 'gemini'),
    ProviderSpec('github', 'https://models.github.ai/inference', 'GITHUB_MODELS_API_KEY', 'openai'),
    ProviderSpec('mistral', 'https://api.mistral.ai/v1', 'MISTRAL_API_KEY', 'openai'),
    ProviderSpec('cerebras', 'https://api.cerebras.ai/v1', 'CEREBRAS_API_KEY', 'openai'),
    ProviderSpec('sambanova', 'https://api.sambanova.ai/v1', 'SAMBANOVA_API_KEY', 'openai'),
)

PROVIDER_MODEL_HINTS: dict[str, list[str]] = {
    'github': ['gpt-4o-mini', 'gpt-4o', 'DeepSeek-V3-0324', 'Llama-3.3-70B-Instruct'],
    'cerebras': ['gpt-oss-120b', 'llama-3.1-8b'],
}

PROVIDER_REQUIRED_QUERY: dict[str, dict[str, str]] = {
    'github': {'api-version': '2024-12-01-preview'},
}


def load_dotenv(path: Path = DOTENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def hydrate_env(path: Path = DOTENV_PATH, *, overwrite: bool = False) -> dict[str, str]:
    values = load_dotenv(path)
    for key, value in values.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return values


def get_provider_specs() -> tuple[ProviderSpec, ...]:
    return PROVIDER_SPECS


def get_provider_spec(name: str) -> ProviderSpec:
    for spec in PROVIDER_SPECS:
        if spec.name == name:
            return spec
    raise KeyError(f'unknown provider: {name}')


def configured_provider_names(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    return [spec.name for spec in PROVIDER_SPECS if source.get(spec.api_key_env)]


def iter_provider_specs(names: Iterable[str] | None = None) -> list[ProviderSpec]:
    if names is None:
        return list(PROVIDER_SPECS)
    wanted = set(names)
    return [spec for spec in PROVIDER_SPECS if spec.name in wanted]


def get_provider_model_hints(name: str) -> list[str]:
    return PROVIDER_MODEL_HINTS.get(name, [])


def get_probe_model_candidates(name: str, requested_model: str | None = None) -> list[str]:
    candidates: list[str] = []
    if requested_model:
        candidates.append(requested_model)
    for model_id in get_provider_model_hints(name):
        if model_id not in candidates:
            candidates.append(model_id)
    return candidates


def get_provider_required_query(name: str) -> dict[str, str]:
    return PROVIDER_REQUIRED_QUERY.get(name, {})
