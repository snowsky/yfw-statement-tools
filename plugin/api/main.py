from shared.app import create_app

PLUGIN_PREFIX = "/api/v1/statement-tools"

app = create_app(
    api_prefix=PLUGIN_PREFIX,
    require_auth=False,
    include_connection_check=False,
    service_name="statement-tools-plugin",
)
