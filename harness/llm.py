"""Central LLM calls with provider routing and API visibility."""

from __future__ import annotations

from harness.models import get_model_profile
from harness.providers.router import create_provider_message
from harness.ui.renderer import renderer


def _format_llm_tag(profile) -> str:
    tag = f"{profile.provider}/{profile.api_model}"
    if profile.thinking:
        tag += "+thinking"
    if profile.api_model != profile.id:
        tag = f"{profile.id}→{tag}"
    return tag


def create_message(
    *,
    messages: list,
    max_tokens: int,
    system: str | None = None,
    tools: list | None = None,
    model_id: str | None = None,
):
    profile = get_model_profile(model_id)

    with renderer.llm_busy(_format_llm_tag(profile)):
        response = create_provider_message(
            profile=profile,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
        )

    reported = getattr(response, "model", None)
    if reported and reported != profile.api_model:
        renderer.warn(
            f"API backend used '{reported}' (requested '{profile.api_model}')"
        )
    return response
