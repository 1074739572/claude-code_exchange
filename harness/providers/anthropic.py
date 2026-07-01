"""Anthropic SDK client factory per provider."""

from __future__ import annotations

import threading

from anthropic import Anthropic

from harness.providers.config import ProviderConfig, resolve_api_key

_lock = threading.Lock()
_clients: dict[str, Anthropic] = {}


def get_anthropic_client(provider: ProviderConfig) -> Anthropic:
    with _lock:
        cached = _clients.get(provider.id)
        if cached is not None:
            return cached
        api_key = resolve_api_key(provider)
        if not api_key:
            envs = provider.api_key_env
            if provider.api_key_fallback_env:
                envs += f" or {provider.api_key_fallback_env}"
            raise RuntimeError(
                f"Missing API key for provider '{provider.label}'. "
                f"Set {envs} in .env"
            )
        client = Anthropic(api_key=api_key, base_url=provider.base_url)
        _clients[provider.id] = client
        return client
