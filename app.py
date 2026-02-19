import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import config
import downloader
from cortex_client import get_cortex, shutdown_cortex
from database import Download, async_session, init_db

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


# --- Rate limiter (TTL cache, per-IP) ---
# Each IP gets a list of timestamps; cache entries expire after 60s
_rate_cache: TTLCache = TTLCache(maxsize=10000, ttl=60)


def _check_rate_limit(ip: str, limit: int = config.EXTRACT_RATE_LIMIT) -> bool:
    """Return True if the request is within the rate limit."""
    now = time.time()
    window = 60.0
    
    if ip not in _rate_cache:
        _rate_cache[ip] = []
    
    bucket = _rate_cache[ip]
    # Prune old entries within the current bucket
    bucket = [t for t in bucket if now - t < window]
    _rate_cache[ip] = bucket
    
    if len(bucket) >= limit:
        return False
    
    bucket.append(now)
    _rate_cache[ip] = bucket
    return True


# --- Startup / Shutdown ---
async def _recover_stale_downloads():
    """Mark any downloads stuck in 'pending' or 'downloading' as failed on startup.
    Also clean up partial files to free disk space.
    """
    from sqlalchemy import select, or_

    async with async_session() as session:
        result = await session.execute(
            select(Download).where(
                or_(Download.status == "pending", Download.status == "downloading")
            )
        )
        stale = list(result.scalars().all())
        for dl in stale:
            dl.status = "failed"
            dl.error = "Server restarted while download was in progress"
            logger.warning("Recovered stale download id=%d url=%s", dl.id, dl.url)
            
            # Clean up partial files
            if dl.filepath:
                p = Path(dl.filepath)
                if p.exists():
                    try:
                        p.unlink()
                        logger.info("Deleted partial file: %s", p)
                    except OSError as e:
                        logger.warning("Could not delete partial file %s: %s", p, e)
        
        if stale:
            await session.commit()
            logger.info("Recovered %d stale downloads", len(stale))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _recover_stale_downloads()
    logger.info("Server started on %s:%s", config.HOST, config.PORT)
    
    # Report startup to Cortex
    cortex = get_cortex()
    await cortex.health_check(status="ok", details={"event": "startup"})
    
    yield
    
    logger.info("Server shutting down")
    # Report shutdown to Cortex
    await cortex.health_check(status="shutting_down", details={"event": "shutdown"})
    await shutdown_cortex()


app = FastAPI(title="Video Downloader", lifespan=lifespan)


# --- Security headers middleware ---
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Content Security Policy - restrict inline scripts and styles
    # Note: Relaxed for PWA functionality, can be tightened further
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests;"
    )
    
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # XSS protection (legacy, but doesn't hurt)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    return response


# --- Auth middleware ---
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth for static files and the root page
    path = request.url.path
    public_paths = ("/", "/sw.js", "/api/health")
    if not config.API_KEY or path in public_paths or path.startswith("/static"):
        return await call_next(request)

    # Check header first (preferred), fall back to query param (deprecated)
    key = request.headers.get("X-API-Key")
    if not key:
        key = request.query_params.get("api_key")
        if key:
            # Log deprecation warning for query param usage
            logger.warning(
                "API key via query param is deprecated (from %s). Use X-API-Key header.",
                request.client.host if request.client else "unknown"
            )
    
    if key != config.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


# --- Pydantic models ---

def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname looks like a private/local IP address."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local
    except ValueError:
        # Not an IP address — check hostname strings
        return hostname in ("localhost",)


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("Invalid URL: no hostname")
    # Block local/private addresses
    hostname = parsed.hostname.lower()
    if _is_private_ip(hostname):
        raise ValueError("Local/private URLs are not allowed")
    return url


class ExtractRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        return _validate_url(v)


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    format_note: str = ""

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        return _validate_url(v)


# --- API endpoints ---

@app.post("/api/extract")
async def extract_formats(req: ExtractRequest, request: Request):
    """Extract video info and available formats from a URL."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "Rate limit exceeded. Try again in a minute.")

    logger.info("Extracting formats: %s (from %s)", req.url, client_ip)
    result = await downloader.extract_formats(req.url)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/download")
async def start_download(req: DownloadRequest, request: Request):
    """Start downloading a video with the selected format."""
    # Rate limit downloads too (more lenient than extract)
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"download:{client_ip}", limit=20):
        raise HTTPException(429, "Too many downloads. Try again in a minute.")
    
    # Check disk space
    disk = shutil.disk_usage(config.DOWNLOAD_DIR)
    if disk.free < config.MIN_FREE_DISK_BYTES:
        free_mb = disk.free // (1024 * 1024)
        raise HTTPException(
            507, f"Insufficient disk space ({free_mb}MB free). Clear old downloads first."
        )

    logger.info("Starting download: %s [format=%s] (from %s)", req.url, req.format_id, client_ip)
    dl = await downloader.start_download(
        url=req.url,
        format_id=req.format_id,
        format_note=req.format_note,
    )
    return {"id": dl.id, "status": dl.status}


@app.get("/api/downloads")
async def list_downloads():
    """List all downloads with their current status."""
    downloads = await downloader.get_all_downloads()
    results = []
    for dl in downloads:
        d = {
            "id": dl.id,
            "url": dl.url,
            "title": dl.title,
            "platform": dl.platform,
            "format_id": dl.format_id,
            "format_note": dl.format_note,
            "filename": dl.filename,
            "filesize": dl.filesize,
            "thumbnail": dl.thumbnail,
            "duration": dl.duration,
            "status": dl.status,
            "error": dl.error,
            "progress": dl.progress,
            "created_at": dl.created_at.isoformat() if dl.created_at else "",
            "completed_at": dl.completed_at.isoformat() if dl.completed_at else None,
        }
        # Merge live progress if actively downloading
        live = downloader.get_progress(dl.id)
        if live:
            d["progress"] = live.get("progress", dl.progress)
            d["speed"] = live.get("speed", 0)
            d["eta"] = live.get("eta", 0)
        results.append(d)
    return results


@app.get("/api/downloads/{dl_id}/progress")
async def get_progress(dl_id: int):
    """Get live progress for an active download."""
    live = downloader.get_progress(dl_id)
    if live:
        return live
    return {"progress": 0, "speed": 0, "eta": 0}


@app.post("/api/downloads/{dl_id}/retry")
async def retry_download(dl_id: int):
    """Retry a failed download."""
    dl = await downloader.retry_download(dl_id)
    if not dl:
        raise HTTPException(404, "Download not found or not in a retryable state")
    logger.info("Retrying download id=%d", dl_id)
    return {"id": dl.id, "status": dl.status}


@app.delete("/api/downloads/{dl_id}")
async def delete_download(dl_id: int):
    """Delete a download record and its file."""
    ok = await downloader.delete_download(dl_id)
    if not ok:
        raise HTTPException(404, "Download not found")
    logger.info("Deleted download id=%d", dl_id)
    return {"ok": True}


@app.get("/api/downloads/{dl_id}/file")
async def serve_file(dl_id: int):
    """Serve a completed download file."""
    dl = await downloader.get_download_by_id(dl_id)
    if not dl or dl.status != "completed":
        raise HTTPException(404, "File not available")
    p = Path(dl.filepath)
    # Path traversal protection: ensure the file is inside DOWNLOAD_DIR
    try:
        p.resolve().relative_to(config.DOWNLOAD_DIR.resolve())
    except ValueError:
        logger.warning("Path traversal attempt blocked: %s", dl.filepath)
        raise HTTPException(403, "Access denied")
    if not p.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(p, filename=dl.filename, media_type="application/octet-stream")


@app.get("/api/health")
async def health_check():
    """Health check for monitoring and Docker HEALTHCHECK."""
    disk = shutil.disk_usage(config.DOWNLOAD_DIR)
    health_data = {
        "status": "ok",
        "disk_free_mb": disk.free // (1024 * 1024),
        "disk_total_mb": disk.total // (1024 * 1024),
        "active_downloads": len(downloader._active),
    }
    
    # Report health to Cortex (fire and forget, don't block)
    cortex = get_cortex()
    asyncio.create_task(cortex.health_check(status="ok", details=health_data))
    
    return health_data


# --- Serve frontend ---

STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/sw.js")
async def service_worker():
    """Serve service worker from root scope (required for PWA)."""
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        access_log=True,
    )
