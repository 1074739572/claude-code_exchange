"""Thread-safe runtime model selection backed by config/models.json."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from harness.providers.config import get_provider, provider_key_status, resolve_api_key

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MODELS_CONFIG_PATH = PACKAGE_ROOT / "config" / "models.json"

_lock = threading.Lock()
_current_model: str = ""
_catalog: list[dict] = []
_default_model: str = ""


@dataclass(frozen=True)
class ModelProfile:
    """Resolved model sent to the API (id may differ from api_model)."""

    id: str
    label: str
    provider: str
    api_model: str
    thinking: bool = False


def _load_catalog() -> tuple[str, list[dict]]:
    if not MODELS_CONFIG_PATH.exists():
        fallback = os.getenv("MODEL_ID", "deepseek-v4-flash")
        return fallback, [
            {
                "id": fallback,
                "label": fallback,
                "provider": "deepseek",
                "api_model": fallback,
            }
        ]

    data = json.loads(MODELS_CONFIG_PATH.read_text(encoding="utf-8"))
    default = data.get("default") or os.getenv("MODEL_ID", "deepseek-v4-flash")
    models = []
    for entry in data.get("models", []):
        model_id = entry.get("id")
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "label": entry.get("label", model_id),
                "provider": entry.get("provider", "deepseek"),
                "api_model": entry.get("api_model", model_id),
                "thinking": bool(entry.get("thinking")),
            }
        )
    if not models:
        models = [
            {
                "id": default,
                "label": default,
                "provider": "deepseek",
                "api_model": default,
            }
        ]
    return default, models


def _profile_from_entry(entry: dict) -> ModelProfile:
    return ModelProfile(
        id=entry["id"],
        label=entry["label"],
        provider=entry.get("provider", "deepseek"),
        api_model=entry.get("api_model", entry["id"]),
        thinking=bool(entry.get("thinking")),
    )


def initialize_model(override: str | None = None) -> str:
    """Resolve initial model from CLI override, .env MODEL_ID, or config default."""
    global _current_model, _catalog, _default_model

    config_default, catalog = _load_catalog()
    env_model = os.getenv("MODEL_ID")
    initial = override or env_model or config_default

    with _lock:
        _catalog = catalog
        _default_model = config_default
        known_ids = {entry["id"] for entry in _catalog}
        if initial not in known_ids:
            _catalog = list(_catalog) + [
                {
                    "id": initial,
                    "label": f"{initial} (custom)",
                    "provider": "deepseek",
                    "api_model": initial,
                    "thinking": False,
                }
            ]
        if override is not None:
            _current_model = override
        elif not _current_model:
            _current_model = initial
        return _current_model


def get_model() -> str:
    with _lock:
        if not _current_model:
            return initialize_model()
        return _current_model


def get_model_profile(model_id: str | None = None) -> ModelProfile:
    with _lock:
        if not _catalog:
            initialize_model()
        mid = model_id or _current_model or _default_model
        for entry in _catalog:
            if entry["id"] == mid:
                return _profile_from_entry(entry)
        return ModelProfile(
            id=mid,
            label=mid,
            provider="deepseek",
            api_model=mid,
        )


def _provider_label(provider_id: str) -> str:
    try:
        return get_provider(provider_id).label
    except KeyError:
        return provider_id


def set_model(model_id: str) -> str:
    global _current_model
    model_id = model_id.strip()
    if not model_id:
        return "Usage: /model <id>   or   /model list"

    with _lock:
        known_ids = {entry["id"] for entry in _catalog}
        if model_id not in known_ids:
            options = ", ".join(sorted(known_ids))
            return f"Unknown model '{model_id}'. Available: {options}"
        profile = _profile_from_entry(next(e for e in _catalog if e["id"] == model_id))
        provider = get_provider(profile.provider)
        if not resolve_api_key(provider):
            envs = provider.api_key_env
            if provider.api_key_fallback_env:
                envs += f" or {provider.api_key_fallback_env}"
            return (
                f"Cannot switch to {model_id}: missing API key for {provider.label}. "
                f"Set {envs} in .env"
            )
        _current_model = model_id
        api_note = ""
        if profile.api_model != profile.id:
            api_note = f" → API: {profile.api_model}"
        if profile.thinking:
            api_note += " (thinking on)"
        return (
            f"Switched to {model_id} ({profile.label}) "
            f"[{_provider_label(profile.provider)}]{api_note}"
        )


def list_models() -> list[dict]:
    with _lock:
        if not _catalog:
            initialize_model()
        return list(_catalog)


def model_label(model_id: str | None = None) -> str:
    return get_model_profile(model_id).label


def format_model_status() -> str:
    profile = get_model_profile()
    provider_name = _provider_label(profile.provider)
    api = profile.api_model
    extra = f" [{provider_name}]"
    if api != profile.id:
        extra += f" → API: {api}"
    if profile.thinking:
        extra += " (thinking)"
    return f"Model: {profile.id}{extra}  —  /model to switch"


def format_model_list() -> str:
    current = get_model()
    key_status = provider_key_status()
    lines = [
        "Available models:",
        f"(Keys are read from {PACKAGE_ROOT / '.env'}, not .env.example)",
    ]

    by_provider: dict[str, list[dict]] = {}
    for entry in list_models():
        by_provider.setdefault(entry.get("provider", "deepseek"), []).append(entry)

    for provider_id, entries in by_provider.items():
        provider_label = _provider_label(provider_id)
        configured = key_status.get(provider_id, False)
        status = "key ok" if configured else "key missing"
        lines.append(f"\n[{provider_label}] ({status})")
        for entry in entries:
            marker = " *" if entry["id"] == current else "  "
            suffix = entry["label"]
            api = entry.get("api_model", entry["id"])
            if api != entry["id"] or entry.get("thinking"):
                bits = [f"api={api}"]
                if entry.get("thinking"):
                    bits.append("thinking")
                suffix += f" [{', '.join(bits)}]"
            lines.append(f"{marker} {entry['id']:<28} {suffix}")

    lines.append("")
    lines.append("Switch with: /model <id>")
    lines.append(f"API keys: edit {PACKAGE_ROOT / '.env'}")
    return "\n".join(lines)


def handle_model_command(query: str) -> str:
    parts = query.strip().split(maxsplit=1)
    if len(parts) == 1 or parts[1].lower() == "list":
        return format_model_list()
    return set_model(parts[1])
