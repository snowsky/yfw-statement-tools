"""
Standalone FastAPI entry point for statement-tools.
"""
from shared.app import create_app

PLUGIN_PREFIX = "/api/v1/external/statement-tools"

app = create_app(
    api_prefix=PLUGIN_PREFIX,
    require_auth=True,
    include_connection_check=True,
)
