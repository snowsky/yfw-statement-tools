import logging
import httpx
from typing import Any, Optional


logger = logging.getLogger(__name__)


class YFWClient:
    """Async HTTP client for YFW statement processing API."""

    def __init__(
        self,
        yfw_url: str,
        api_key: str,
        secret_key: str = "",
        user_email: str = "",
        plugin_id: str = "statement-tools",
        visitor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        per_tenant_user_id: Optional[int] = None,
    ):
        # Normalize URL: remove trailing slashes and redundant /api/v1
        base = yfw_url.rstrip("/")
        if base.endswith("/api/v1"):
            base = base[:-7].rstrip("/")
        self._base = base
        self._api_key = api_key
        self._secret_key = secret_key
        self._user_email = user_email
        self._plugin_id = plugin_id
        # Stored so every method call carries the correct tenant/visitor context
        # without needing per-call parameters.
        self._visitor_id = visitor_id
        self._tenant_id = tenant_id
        self._per_tenant_user_id = per_tenant_user_id

    def _headers(self, visitor_id: Optional[str] = None, tenant_id: Optional[str] = None) -> dict[str, str]:
        # Per-call params override instance defaults
        effective_visitor = visitor_id or self._visitor_id
        effective_tenant = tenant_id or self._tenant_id

        headers = {}
        # Prioritize secret key (Sidecar mode) over API key (Standalone mode)
        if self._secret_key:
            headers["X-Internal-Secret"] = self._secret_key
            headers["X-Plugin-Id"] = self._plugin_id
            if effective_visitor:
                headers["X-Public-Visitor-Id"] = effective_visitor
                if effective_tenant:
                    headers["X-Public-Tenant-Id"] = effective_tenant
            elif effective_tenant:
                headers["X-Plugin-Tenant-Id"] = effective_tenant
            # Always forward the authenticated user's email so the main app can
            # resolve their tenant even from JWTs that predate the tenant_id claim
            if self._user_email:
                headers["X-Plugin-User-Email"] = self._user_email
            # Forward per-tenant user ID so YFW can use it directly without a
            # costly cross-DB email scan (avoids MasterUser.id != TenantUser.id confusion)
            if self._per_tenant_user_id is not None:
                headers["X-Plugin-User-Id"] = str(self._per_tenant_user_id)
        elif self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    async def process_statement(
        self,
        file_content: bytes,
        filename: str,
        content_type: str = "application/pdf",
        visitor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Send a single file to YFW for AI-powered parsing.

        Returns a list of transaction dicts with keys:
          date, description, amount, transaction_type, category, balance
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self._base}/api/v1/external/statements/process"
            logger.info("Forwarding to YFW: %s", url)
            resp = await client.post(
                url,
                params={"format": "json"},
                files={"file": (filename, file_content, content_type)},
                headers=self._headers(visitor_id=visitor_id, tenant_id=tenant_id),
            )
            logger.info("YFW process status: %d", resp.status_code)

        self._handle_error(resp)
        data = resp.json()
        return data.get("transactions", data if isinstance(data, list) else [])

    async def health_check(self) -> dict[str, Any]:
        """Ping the YFW statements health endpoint to validate connectivity."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self._base}/api/v1/external/statements/health"
            resp = await client.get(url, headers=self._headers())

        self._handle_error(resp)
        return resp.json()

    async def upload_batch(
        self,
        files: list[tuple[str, bytes, str]],
        document_type: str = "statement",
        visitor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Upload multiple files for asynchronous batch processing."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self._base}/api/v1/external-transactions/batch-processing/upload"
            logger.info("Uploading batch to YFW: %s", url)
            data = {"document_types": document_type}
            file_data = [
                ("files", (filename, content, content_type))
                for filename, content, content_type in files
            ]
            resp = await client.post(
                url,
                data=data,
                files=file_data,
                headers=self._headers(visitor_id=visitor_id, tenant_id=tenant_id),
            )

        self._handle_error(resp)
        return resp.json()

    async def list_jobs(self, limit: int = 50) -> dict[str, Any]:
        """List batch jobs for the current authenticated user."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self._base}/api/v1/external-transactions/batch-processing/jobs"
            resp = await client.get(url, params={"limit": limit}, headers=self._headers())

        self._handle_error(resp)
        return resp.json()

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the current status and extracted data for a batch job."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self._base}/api/v1/external-transactions/batch-processing/jobs/{job_id}"
            resp = await client.get(url, headers=self._headers())

        self._handle_error(resp)
        return resp.json()

    def _handle_error(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        if resp.status_code == 401:
            raise PermissionError("Invalid API key.")
        if resp.status_code == 402:
            raise PermissionError(
                "Statement processing is not enabled on your YFW license."
            )
        if resp.status_code == 403:
            raise PermissionError(
                "Your API key does not have document or batch processing permission."
            )
        if resp.status_code == 429:
            raise RuntimeError("Rate limit exceeded. Please try again later.")
        if resp.status_code == 503:
            raise RuntimeError(
                "YFW AI processing service is unavailable. "
                "Please check Settings > AI Configuration."
            )
        raise RuntimeError(f"YFW returned HTTP {resp.status_code}: {resp.text[:200]}")
