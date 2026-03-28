"""
Plugin entry points for YourFinanceWORKS deployment.
"""
from shared.routers.statements import create_router

PLUGIN_PREFIX = "/api/v1/statement-tools"


def register_plugin(app, mcp_registry=None, feature_gate=None):
    """Called by the YourFinanceWORKS plugin loader at startup."""
    app.include_router(
        create_router(api_prefix=PLUGIN_PREFIX, auth_dependency=None),
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
