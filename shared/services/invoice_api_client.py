import logging
import httpx
from typing import Any


logger = logging.getLogger(__name__)



class YFWClient:
    """Async client for YFW statement processing API."""

    def __init__(self, yfw_url: str, api_key: str):
        # Normalize URL: remove trailing slashes and redundant /api/v1
        base = yfw_url.rstrip("/")
        if base.endswith("/api/v1"):
            base = base[:-7].rstrip("/")
        self._base = base
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    async def process_statement(
        self,
        file_content: bytes,
        filename: str,
        content_type: str = "application/pdf",
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
                headers=self._headers(),
            )
            logger.info("YFW process status: %d", resp.status_code)

        if resp.status_code == 401:
            raise PermissionError("Invalid API key.")
        if resp.status_code == 402:
            raise PermissionError(
                "Statement processing is not enabled on your YFW license."
            )
        if resp.status_code == 403:
            raise PermissionError(
                "Your API key does not have document processing permission."
            )
        if resp.status_code == 429:
            raise RuntimeError("Rate limit exceeded. Please try again later.")
        if resp.status_code == 503:
            raise RuntimeError(
                "YFW AI processing service is unavailable. "
                "Please check Settings > AI Configuration."
            )
        if not resp.is_success:
            raise RuntimeError(f"YFW returned HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        return data.get("transactions", data if isinstance(data, list) else [])

    async def health_check(self) -> dict[str, Any]:
        """Ping the YFW statements health endpoint to validate connectivity."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self._base}/api/v1/external/statements/health"
            logger.info("Checking health at: %s", url)
            resp = await client.get(
                url,
                headers=self._headers(),
            )
            logger.info("Health check status: %d", resp.status_code)
        
        self._handle_error(resp)
        return resp.json()

    async def upload_batch(
        self,
        files: list[tuple[str, bytes, str]],
        document_type: str = "statement"
    ) -> dict[str, Any]:
        """
        Upload multiple files for asynchronous batch processing.
        
        Args:
            files: List of (filename, content, content_type) tuples
            document_type: The type of document to process (e.g., 'statement')
            
        Returns:
            Dictionary containing 'job_id' and initial status.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self._base}/api/v1/external-transactions/batch-processing/upload"
            logger.info("Uploading batch to YFW: %s", url)
            
            # Prepare multipart form data
            data = {"document_types": document_type}
            file_data = [
                ("files", (filename, content, content_type))
                for filename, content, content_type in files
            ]
            
            resp = await client.post(
                url,
                data=data,
                files=file_data,
                headers=self._headers(),
            )
            if not resp.is_success:
                logger.error("YFW batch upload error: %d - %s", resp.status_code, resp.text[:500])
            else:
                logger.info("YFW batch upload status: %d", resp.status_code)
        
        self._handle_error(resp)
        return resp.json()

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the current status and extracted data for a batch job."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self._base}/api/v1/external-transactions/batch-processing/jobs/{job_id}"
            logger.debug("Checking job status: %s", url)
            resp = await client.get(
                url,
                headers=self._headers(),
            )
        
        self._handle_error(resp)
        return resp.json()

    def _handle_error(self, resp: httpx.Response) -> None:
        """Centralized error handling for YFW API responses."""
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
