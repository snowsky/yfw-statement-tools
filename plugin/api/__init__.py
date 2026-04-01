"""
Plugin entry points for YourFinanceWORKS deployment.

When running as a plugin inside the YFW app, statement processing
is handled directly via the internal service — no external API key needed.
"""
from shared.routers.statements import create_router

PLUGIN_PREFIX = "/api/v1/statement-tools"


def _make_internal_client_factory():
    """
    Return a factory that creates an InternalYFWClient.

    The internal client calls the core processing service directly
    instead of going through the external HTTP API (no API key needed).
    """
    def factory(request):
        from plugin.api._internal_client import InternalYFWClient

        db_factory = None
        try:
            from core.models.database import get_tenant_context
            from core.services.tenant_database_manager import tenant_db_manager

            tenant_id = get_tenant_context()
            if tenant_id:
                db_factory = tenant_db_manager.get_tenant_session(tenant_id)
        except Exception:
            pass
        return InternalYFWClient(db_session_factory=db_factory)

    return factory


def register_plugin(app, mcp_registry=None, feature_gate=None):
    """Called by the YourFinanceWORKS plugin loader at startup."""

    # Use session-based auth instead of API key
    try:
        from core.routers.auth import get_current_user
        auth_dep = get_current_user
    except ImportError:
        auth_dep = None

    # Use internal processing client (no API key needed)
    try:
        client_factory = _make_internal_client_factory()
    except Exception:
        client_factory = None

    app.include_router(
        create_router(
            api_prefix=PLUGIN_PREFIX,
            auth_dependency=auth_dep,
            client_factory=client_factory,
        ),
        prefix=PLUGIN_PREFIX,
        tags=["statement-tools"],
    )
    return {
        "name": "statement-tools",
        "version": "1.0.0",
        "routes": [
            f"{PLUGIN_PREFIX}/statements/upload",
            f"{PLUGIN_PREFIX}/statements/download/{{token}}",
            f"{PLUGIN_PREFIX}/batch/upload",
            f"{PLUGIN_PREFIX}/batch/jobs/{{job_id}}",
        ],
    }
