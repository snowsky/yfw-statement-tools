"""
YFW client factory.

Sidecar mode (YFW_SECRET_KEY is set): use InternalYFWClient, which calls
core services directly via Python imports — no HTTP round-trip needed.

Standalone mode: use YFWClient, which forwards files to a YFW instance
over HTTP using YFW_API_URL / YFW_API_KEY.
"""
from __future__ import annotations

import os


def get_yfw_client(yfw_url: str = "", api_key: str = "", secret_key: str = ""):
    if os.getenv("YFW_SECRET_KEY"):
        try:
            from services.internal_client import InternalYFWClient
            return InternalYFWClient()
        except ImportError:
            pass
    from services.yfw_client import YFWClient
    return YFWClient(yfw_url=yfw_url, api_key=api_key, secret_key=secret_key)
