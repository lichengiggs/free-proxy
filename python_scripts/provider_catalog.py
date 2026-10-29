from __future__ import annotations

import os
import re
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
    account_id_env: str | None = None


_ACCOUNT_ID_RE = re.compile(r'^[0-9a-fA-F]{32}$')
CLOUDFLARE_PAID_MODEL_IDS = frozenset({
    '@cf/moonshotai/kimi-k2.6',
    '@cf/moonshotai/kimi-k2.7-code',
    '@cf/zai-org/glm-5.2',
    '@cf/zai-org/glm-5.3',
    '@cf/zai-org/glm-5.3-flash',
    '@cf/deepseek-ai/deepseek-v4-flash-0731',
    '@cf/deepseek-ai/deepseek-v4.1-flash-1017',
    '@cf/deepseek-ai/deepseek-v4-pro-0813',
})


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
        model_hints=('llama-3.1-8b-instant',),
    ),
    ProviderMeta(
        'gemini',
        'https://generativelanguage.googleapis.com/v1beta',
        'GEMINI_API_KEY',
        'gemini',
        model_hints=('gemini-3.1-flash-lite-preview',),
    ),
    ProviderMeta(
        'mistral',
        'https://api.mistral.ai/v1',
        'MISTRAL_API_KEY',
        'openai',
        model_hints=('mistral-large-latest',),
    ),
    ProviderMeta(
        'nvidia',
        'https://integrate.api.nvidia.com/v1',
        'NVIDIA_API_KEY',
        'openai',
        model_hints=('meta/llama-3.1-70b-instruct',),
    ),
    ProviderMeta(
        'cloudflare',
        'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1',
        'CLOUDFLARE_API_KEY',
        'openai',
        model_hints=('@cf/meta/llama-3.1-8b-instruct',),
        account_id_env='CLOUDFLARE_ACCOUNT_ID',
    ),
    ProviderMeta(
        'amd',
        'https://developer.amd.com.cn/radeon/api/v1',
        'AMD_API_KEY',
        'openai',
        model_hints=('DeepSeek-V4-Flash',),
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


def is_valid_account_id(value: str) -> bool:
    """Return whether ``value`` is a 32-character hexadecimal account id.

    Args:
        value: Raw account id. Empty text, spaces, ``/``, and ``..`` are invalid.
        The check does not rewrite case.

    Returns:
        True when ``value`` matches ``^[0-9a-fA-F]{32}$``.

    Raises:
        None.
    """
    return _ACCOUNT_ID_RE.fullmatch(value) is not None


def _provider_with_account_id(provider: ProviderMeta) -> ProviderMeta:
    if not provider.account_id_env or '{account_id}' not in provider.base_url:
        return provider
    account_id = os.environ.get(provider.account_id_env, '')
    if not is_valid_account_id(account_id):
        return provider
    return replace(provider, base_url=provider.base_url.replace('{account_id}', account_id, 1))


def get_provider(name: str) -> ProviderMeta:
    """Return provider metadata, optionally pointed at the contract-test upstream.

    Args:
        name: Catalog provider name.

    Returns:
        The catalog record. When ``FREE_PROXY_TEST_UPSTREAM`` is a loopback HTTP
        URL, ``base_url`` is that URL and no account id is inserted. For
        Cloudflare, a valid ``CLOUDFLARE_ACCOUNT_ID`` replaces ``{account_id}``
        in the catalog template without changing case. A missing or invalid
        account id keeps the template, name, and hint.

    Raises:
        KeyError: ``name`` is not in the catalog.
        ProviderError: The test upstream variable is set to a non-loopback URL.
    """
    provider = PROVIDER_MAP.get(name)
    if provider is None:
        raise KeyError(f'unknown provider: {name}')
    override = test_upstream_base_url()
    if override is not None:
        return replace(provider, base_url=override)
    return _provider_with_account_id(provider)


def list_providers(names: Iterable[str] | None = None) -> list[ProviderMeta]:
    if names is None:
        return list(PROVIDERS)
    wanted = set(names)
    return [provider for provider in PROVIDERS if provider.name in wanted]


def configured_provider_names(env: dict[str, str] | None = None) -> list[str]:
    """Return catalog providers that have the credentials this process can use.

    Args:
        env: Optional environment mapping. Defaults to ``os.environ``.

    Returns:
        Provider names in catalog order. Cloudflare is included only when its
        API token and a 32-character hexadecimal account id are both present.

    Raises:
        None.
    """
    source = os.environ if env is None else env
    names: list[str] = []
    for provider in PROVIDERS:
        if not str(source.get(provider.api_key_env, '')).strip():
            continue
        if provider.account_id_env and not is_valid_account_id(str(source.get(provider.account_id_env, ''))):
            continue
        names.append(provider.name)
    return names


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
