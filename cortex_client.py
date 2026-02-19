"""Cortex task reporting client for YouTubeDL service."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("cortex")

SERVICE_NAME = "youtubedl"


class CortexClient:
    """Simple async client for reporting task activity to Cortex."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None, api_key: str | None = None):
        # Import config here to avoid circular imports
        import config
        
        if base_url is None:
            base_url = config.CORTEX_URL
        if timeout is None:
            timeout = config.CORTEX_TIMEOUT
        if api_key is None:
            api_key = config.CORTEX_API_KEY
        
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)
        self._enabled = True

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def _post(self, endpoint: str, data: dict[str, Any]) -> bool:
        """Send a POST request to Cortex. Returns True on success, False on failure."""
        if not self._enabled:
            return False

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = await self._client.post(url, json=data)
            if resp.status_code >= 400:
                logger.warning(
                    "Cortex request failed: %s %s -> %d",
                    endpoint,
                    data,
                    resp.status_code,
                )
                return False
            return True
        except httpx.RequestError as e:
            # Network error — disable future requests to avoid log spam
            logger.warning("Cortex unreachable (%s), disabling reporting: %s", url, e)
            self._enabled = False
            return False
        except Exception as e:
            logger.exception("Unexpected error reporting to Cortex: %s", e)
            return False

    async def task_started(
        self,
        task_id: str,
        task_type: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Report that a task has started."""
        data = {
            "service": SERVICE_NAME,
            "task_id": task_id,
            "task_type": task_type,
            "description": description,
            "status": "started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        return await self._post("/api/tasks/start", data)

    async def task_progress(
        self,
        task_id: str,
        progress: float,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Report task progress (0-100)."""
        data = {
            "service": SERVICE_NAME,
            "task_id": task_id,
            "progress": round(progress, 2),
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        return await self._post("/api/tasks/progress", data)

    async def task_completed(
        self,
        task_id: str,
        result: str = "success",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Report that a task has completed."""
        data = {
            "service": SERVICE_NAME,
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        return await self._post("/api/tasks/complete", data)

    async def task_failed(
        self,
        task_id: str,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Report that a task has failed."""
        data = {
            "service": SERVICE_NAME,
            "task_id": task_id,
            "status": "failed",
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        return await self._post("/api/tasks/fail", data)

    async def health_check(
        self, status: str = "ok", details: dict[str, Any] | None = None
    ) -> bool:
        """Report service health status."""
        data = {
            "service": SERVICE_NAME,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }
        return await self._post("/api/health", data)


# Global instance
_cortex: CortexClient | None = None


def get_cortex() -> CortexClient:
    """Get the global Cortex client instance."""
    global _cortex
    if _cortex is None:
        _cortex = CortexClient()
    return _cortex


async def shutdown_cortex():
    """Close the global Cortex client."""
    global _cortex
    if _cortex:
        await _cortex.close()
        _cortex = None
