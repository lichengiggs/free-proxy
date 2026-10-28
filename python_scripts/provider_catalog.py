from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Iterable, Literal
from urllib.parse import urlsplit

from .provider_errors import ProviderError


FormatType = Literal['openai', 'gemini', 'anthropic']


@dataclass(frozen=True)
class ProviderMeta:
    name: str
    base_url: str
    api_key_env: str
    format: FormatType
    model_hints: tuple[str, ...] = field(default_factory=tuple)
    required_query: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    model_capabilities: dict[str, dict[str, object]] = field(default_factory=dict)


PROVIDERS: tuple[ProviderMeta, ...] = (
    ProviderMeta(
        'openrouter',
        'https://openrouter.ai/api/v1',
        'OPENROUTER_API_KEY',
        'openai',
        model_hints=('openrouter/auto:free',),
    ),
    ProviderMeta(
        'groq',
        'https://api.groq.com/openai/v1',
        'GROQ_API_KEY',
        'openai',
        model_hints=('llama-3.1-8b-instant', 'llama-3.3-70b-versatile'),
    ),
    ProviderMeta(
        'gemini',
        'https://generativelanguage.googleapis.com/v1beta',
        'GEMINI_API_KEY',
        'gemini',
        model_hints=('gemini-3.1-flash-lite-preview', 'gemini-2.0-flash'),
    ),
    ProviderMeta(
        'mistral',
        'https://api.mistral.ai/v1',
        'MISTRAL_API_KEY',
        'openai',
        model_hints=('mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest'),
    ),
    ProviderMeta(
        'nvidia',
        'https://integrate.api.nvidia.com/v1',
        'NVIDIA_API_KEY',
        'openai',
        model_hints=('meta/llama-3.1-70b-instruct',),
    ),
    ProviderMeta(
        'amd',
        'https://developer.amd.com.cn/radeon/api/v1',
        'AMD_API_KEY',
        'openai',
        model_hints=('DeepSeek-V4-Flash', 'MiniCPM5-2B'),
    ),
)

PROVIDER_MAP: dict[str, ProviderMeta] = {provider.name: provider for provider in PROVIDERS}


def test_upstream_base_url() -> str | None:
    """Return the loopback upstream override used by the contract process test.

    Args:
        None.

    Returns:
        ``FREE_PROXY_TEST_UPSTREAM`` without a trailing slash, or None when it is unset.

    Raises:
        ProviderError: The variable is set to a URL that is not ``http`` on
        ``127.0.0.1`` or ``localhost``.
    """
    raw = os.environ.get('FREE_PROXY_TEST_UPSTREAM', '').strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'http' or host not in {'127.0.0.1', 'localhost'} or parsed.username or parsed.password:
        raise ProviderError('FREE_PROXY_TEST_UPSTREAM must be http://127.0.0.1 or http://localhost')
    return raw.rstrip('/')


def get_provider(name: str) -> ProviderMeta:
    """Return provider metadata, optionally pointed at the contract-test upstream.

    Args:
        name: Catalog provider name.

    Returns:
        The catalog record. When ``FREE_PROXY_TEST_UPSTREAM`` is a loopback HTTP
        URL, ``base_url`` is that URL.

    Raises:
        KeyError: ``name`` is not in the catalog.
        ProviderError: The test upstream variable is set to a non-loopback URL.
    """
    provider = PROVIDER_MAP.get(name)
    if provider is None:
        raise KeyError(f'unknown provider: {name}')
    override = test_upstream_base_url()
    if override is None:
        return provider
    return replace(provider, base_url=override)


def list_providers(names: Iterable[str] | None = None) -> list[ProviderMeta]:
    if names is None:
        return list(PROVIDERS)
    wanted = set(names)
    return [provider for provider in PROVIDERS if provider.name in wanted]


def configured_provider_names(env: dict[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return [provider.name for provider in PROVIDERS if str(source.get(provider.api_key_env, '')).strip()]


def get_provider_model_hints(name: str) -> list[str]:
    return list(get_provider(name).model_hints)


def get_provider_required_query(name: str) -> dict[str, str]:
    return dict(get_provider(name).required_query)


def get_model_capabilities(name: str, model_id: str) -> dict[str, object]:
    provider = get_provider(name)
    model_key = model_id.strip()
    if model_key and model_key in provider.model_capabilities:
        return dict(provider.model_capabilities[model_key])
    return {}
