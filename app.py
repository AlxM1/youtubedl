from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import downloader
from database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Video Downloader", lifespan=lifespan)


# --- Pydantic models ---

class ExtractRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    format_note: str = ""


class DownloadResponse(BaseModel):
    id: int
    url: str
    title: str
    platform: str
    format_id: str
    format_note: str
    filename: str
    filesize: float
    thumbnail: str
    duration: float
    status: str
    error: str
    progress: float
    created_at: str
    completed_at: str | None

    class Config:
        from_attributes = True


# --- API endpoints ---

@app.post("/api/extract")
async def extract_formats(req: ExtractRequest):
    """Extract video info and available formats from a URL."""
    if not req.url.strip():
        raise HTTPException(400, "URL is required")
    result = await downloader.extract_formats(req.url.strip())
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/download")
async def start_download(req: DownloadRequest):
    """Start downloading a video with the selected format."""
    if not req.url.strip():
        raise HTTPException(400, "URL is required")
    dl = await downloader.start_download(
        url=req.url.strip(),
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


@app.delete("/api/downloads/{dl_id}")
async def delete_download(dl_id: int):
    """Delete a download record and its file."""
    ok = await downloader.delete_download(dl_id)
    if not ok:
        raise HTTPException(404, "Download not found")
    return {"ok": True}


@app.get("/api/downloads/{dl_id}/file")
async def serve_file(dl_id: int):
    """Serve a completed download file."""
    downloads = await downloader.get_all_downloads(limit=1000)
    dl = next((d for d in downloads if d.id == dl_id), None)
    if not dl or dl.status != "completed":
        raise HTTPException(404, "File not available")
    p = Path(dl.filepath)
    if not p.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(p, filename=dl.filename, media_type="application/octet-stream")


# --- Serve frontend ---

STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, reload=True)
