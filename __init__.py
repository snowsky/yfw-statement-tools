"""
YourFinanceWORKS plugin entry point for statement-tools.

When installed as a plugin (cloned into api/plugins/statement-tools/),
the YFW plugin loader calls register_plugin(app) to mount routes.
"""
from shared.routers import statements_router

PLUGIN_PREFIX = "/api/v1/statement-tools"


def register_plugin(app, mcp_registry=None, feature_gate=None):
    """Called by YourFinanceWORKS plugin loader at startup."""
    app.include_router(statements_router, prefix=PLUGIN_PREFIX, tags=["statement-tools"])

    return {
        "name": "statement-tools",
        "version": "1.0.0",
        "routes": [
            f"{PLUGIN_PREFIX}/statements/upload",
            f"{PLUGIN_PREFIX}/statements/download/{{token}}",
        ],
    }
