"""Improved harness: modular s20 comprehensive agent."""

# SSL patch MUST be imported before any huggingface_hub API calls.
# On some Windows environments, the root CA for huggingface.co is missing
# from both the system trust store and certifi, causing SSL handshake failures.
# This patch uses set_client_factory() to create httpx.Client instances with
# host checking disabled.
import harness._ssl_patch  # noqa: F401

from harness.loop import agent_loop
from harness.context import update_context

__all__ = ["agent_loop", "update_context"]
