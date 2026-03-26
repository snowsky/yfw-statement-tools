"""
Compatibility shim — detects plugin mode (running inside YFW) vs standalone.

In plugin mode: imports get_db and get_current_user from the host YFW app.
In standalone mode: falls back to standalone/ local implementations.
"""
try:
    from core.models.database import get_db           # noqa: F401
    from core.routers.auth import get_current_user    # noqa: F401
    STANDALONE = False

except ImportError:
    from standalone.database import get_db            # noqa: F401
    from standalone.auth import get_current_user      # noqa: F401
    STANDALONE = True

__all__ = ["get_db", "get_current_user", "STANDALONE"]
