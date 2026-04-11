"""
YFW client factory.

Sidecar mode (YFW_INTERNAL_MODE=true): use InternalYFWClient, which calls
core services directly via Python imports — no HTTP round-trip needed.

Default / standalone mode: use YFWClient, which forwards files to a YFW
instance over HTTP. In sidecar deployments this uses X-Internal-Secret;
in standalone deployments it uses X-API-Key.
"""
from __future__ import annotations

import os


def get_yfw_client(yfw_url: str = "", api_key: str = "", secret_key: str = "", user_email: str = ""):
    """
    Return a YFW client.
    Prioritizes YFWClient (HTTP) which uses internal_secret for sidecar trust.
    Only falls back to InternalYFWClient if internal modules are explicitly available.
    """
    # 1. Check if we should use direct Python calls (True Plugin mode)
    if os.getenv("YFW_INTERNAL_MODE") == "true":
        try:
            from services.internal_client import InternalYFWClient
            import core.models.database  # check for module
            return InternalYFWClient()
        except ImportError:
            pass

    # 2. Default: Use YFWClient (HTTP)
    # This works for both standalone (X-API-Key) and sidecar (X-Internal-Secret).
    from services.yfw_client import YFWClient
    return YFWClient(yfw_url=yfw_url, api_key=api_key, secret_key=secret_key, user_email=user_email)
