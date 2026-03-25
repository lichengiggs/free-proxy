from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .client import ProviderClient, ProviderError, Transport
from .config import ProviderSpec, configured_provider_names, get_probe_model_candidates, get_provider_spec, hydrate_env


@dataclass
class ProbeResult:
    provider: str
    model: str
    ok: bool
    actual_model: str | None = None
    content: str | None = None
    error: str | None = None


class ProxyService:
    def __init__(self, *, transport: Transport | None = None) -> None:
        hydrate_env()
        self.transport = transport

    def available_providers(self) -> list[str]:
        return configured_provider_names()

    def provider_client(self, provider_name: str) -> ProviderClient:
        spec = get_provider_spec(provider_name)
        api_key = os.environ.get(spec.api_key_env, '').strip()
        if not api_key:
            raise ProviderError(f'{provider_name} 没有配置 API Key')
        return ProviderClient(spec=spec, api_key=api_key, transport=self.transport)

    def list_models(self, provider_name: str) -> list[str]:
        return self.provider_client(provider_name).list_models()

    def probe(self, provider_name: str, model_id: str) -> ProbeResult:
        client = self.provider_client(provider_name)
        last_error: str | None = None
        for candidate in get_probe_model_candidates(provider_name, model_id):
            try:
                content = client.chat(candidate, 'ok')
                return ProbeResult(provider=provider_name, model=model_id, ok=True, actual_model=candidate, content=content)
            except ProviderError as exc:
                last_error = str(exc)
        return ProbeResult(provider=provider_name, model=model_id, ok=False, error=last_error or '探测失败')

    def summary(self) -> dict[str, Any]:
        providers = []
        for provider_name in self.available_providers():
            try:
                models = self.list_models(provider_name)
                providers.append({'provider': provider_name, 'models': models})
            except ProviderError as exc:
                providers.append({'provider': provider_name, 'error': str(exc), 'models': []})
        return {'providers': providers}
