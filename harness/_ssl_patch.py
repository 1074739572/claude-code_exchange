"""
SSL patch for Windows environments where huggingface.co CA is missing.

Patches huggingface_hub's HTTP client factory to create httpx.Client instances
with SSL certificate verification disabled. Required on some Windows machines
where the root CA for huggingface.co's certificate is not in the Windows
certificate store AND not covered by certifi either.

Usage:
    import harness._ssl_patch  # auto-applies at import time

Or call explicitly:
    from harness._ssl_patch import patch_hf_ssl
    patch_hf_ssl()

The patch is idempotent (safe to call multiple times).
"""

import os
import ssl
from typing import Optional

_APPLIED: bool = False


def patch_hf_ssl() -> None:
    """Replace huggingface_hub's HTTP client factory with SSL-verify-disabled clients.

    Uses the official ``huggingface_hub.utils._http.set_client_factory()`` API.
    This is the recommended approach; it correctly replaces the internals so that
    ``get_session()`` returns a client with the desired configuration.
    """
    global _APPLIED
    if _APPLIED:
        return

    try:
        import httpx
        from huggingface_hub.utils._http import set_client_factory

        def _make_client() -> httpx.Client:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return httpx.Client(
                verify=ctx,
                timeout=httpx.Timeout(300.0, connect=30.0, read=120.0),
                follow_redirects=True,
            )

        set_client_factory(_make_client)
        _APPLIED = True
    except ImportError:
        # huggingface_hub not installed — not needed
        pass
    except Exception as exc:
        import warnings

        warnings.warn(f"harness._ssl_patch: failed to apply SSL patch: {exc}")


# Auto-apply at import time
patch_hf_ssl()
