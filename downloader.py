import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from sqlalchemy import select

import config
from database import Download, async_session

# Active downloads: download_id -> task
_active: dict[int, asyncio.Task] = {}
_progress: dict[int, dict] = {}
_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)


def detect_platform(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    hostname = hostname.removeprefix("www.").removeprefix("m.")
    for platform, domains in config.SUPPORTED_PLATFORMS.items():
        if any(hostname == d or hostname.endswith("." + d) for d in domains):
            return platform
    return "other"


def _base_ytdlp_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
    }
    if config.COOKIES_FILE:
        opts["cookiefile"] = config.COOKIES_FILE
    return opts


async def extract_formats(url: str) -> dict:
    """Extract video info and available formats without downloading."""
    opts = {
        **_base_ytdlp_opts(),
        "skip_download": True,
    }

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract_info, url, opts)
    if not info:
        return {"error": "Could not extract video information"}

    platform = detect_platform(url)
    formats = _parse_formats(info.get("formats", []))

    return {
        "url": url,
        "title": info.get("title", "Unknown"),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "platform": platform,
        "uploader": info.get("uploader", ""),
        "formats": formats,
    }


def _extract_info(url: str, opts: dict) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def _parse_formats(raw_formats: list[dict]) -> list[dict]:
    """Deduplicate and present clean format choices."""
    seen = set()
    formats = []

    for f in raw_formats:
        fid = f.get("format_id", "")
        ext = f.get("ext", "")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        has_video = vcodec != "none" and vcodec is not None
        has_audio = acodec != "none" and acodec is not None

        if not has_video and not has_audio:
            continue

        height = f.get("height") or 0
        width = f.get("width") or 0
        fps = f.get("fps") or 0
        tbr = f.get("tbr") or 0
        filesize = f.get("filesize") or f.get("filesize_approx") or 0

        if has_video:
            label = f"{height}p" if height else "video"
            if fps and fps > 30:
                label += f"{fps}"
            media_type = "video+audio" if has_audio else "video_only"
        else:
            label = "audio"
            media_type = "audio_only"

        note = f.get("format_note", label)
        key = (fid, ext)
        if key in seen:
            continue
        seen.add(key)

        formats.append({
            "format_id": fid,
            "ext": ext,
            "resolution": f"{width}x{height}" if width and height else "",
            "fps": fps,
            "filesize": filesize,
            "tbr": round(tbr, 1) if tbr else None,
            "has_video": has_video,
            "has_audio": has_audio,
            "media_type": media_type,
            "note": note,
        })

    # Sort: video+audio first, then by height descending
    def sort_key(f):
        order = {"video+audio": 0, "video_only": 1, "audio_only": 2}
        h = 0
        if f["resolution"]:
            parts = f["resolution"].split("x")
            if len(parts) == 2 and parts[1].isdigit():
                h = int(parts[1])
        return (order.get(f["media_type"], 3), -h, -(f["tbr"] or 0))

    formats.sort(key=sort_key)
    return formats


async def start_download(url: str, format_id: str, format_note: str = "") -> Download:
    """Create a download record and start the download in the background."""
    platform = detect_platform(url)

    async with async_session() as session:
        dl = Download(
            url=url,
            platform=platform,
            format_id=format_id,
            format_note=format_note,
            status="pending",
        )
        session.add(dl)
        await session.commit()
        await session.refresh(dl)
        dl_id = dl.id

    task = asyncio.create_task(_run_download(dl_id, url, format_id))
    _active[dl_id] = task
    return dl


async def _run_download(dl_id: int, url: str, format_id: str):
    """Execute the actual download with progress tracking."""
    await _update_status(dl_id, "downloading")

    async with _semaphore:
        loop = asyncio.get_event_loop()
        try:
            filepath = await loop.run_in_executor(
                None, _download_sync, dl_id, url, format_id
            )
            p = Path(filepath)
            filesize = p.stat().st_size if p.exists() else 0

            async with async_session() as session:
                dl = await session.get(Download, dl_id)
                dl.status = "completed"
                dl.filepath = str(filepath)
                dl.filename = p.name
                dl.filesize = filesize
                dl.progress = 100
                dl.completed_at = datetime.now(timezone.utc)
                await session.commit()
        except Exception as e:
            async with async_session() as session:
                dl = await session.get(Download, dl_id)
                dl.status = "failed"
                dl.error = str(e)
                await session.commit()
        finally:
            _active.pop(dl_id, None)
            _progress.pop(dl_id, None)


def _download_sync(dl_id: int, url: str, format_id: str) -> str:
    """Blocking download — runs in a thread executor."""
    final_filepath = None

    def progress_hook(d):
        nonlocal final_filepath
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total > 0 else 0
            _progress[dl_id] = {
                "progress": round(pct, 1),
                "speed": d.get("speed", 0),
                "eta": d.get("eta", 0),
                "downloaded": downloaded,
                "total": total,
            }
        elif d["status"] == "finished":
            final_filepath = d.get("filename", "")
            _progress[dl_id] = {"progress": 100, "speed": 0, "eta": 0}

    # Build format spec
    if format_id == "best":
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    elif format_id == "best_audio":
        fmt = "bestaudio/best"
    else:
        # Specific format id — try merging with best audio if video-only
        fmt = f"{format_id}+bestaudio/{format_id}/best"

    opts = {
        **_base_ytdlp_opts(),
        "format": fmt,
        "outtmpl": str(config.DOWNLOAD_DIR / "%(title)s [%(id)s].%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [],
    }

    # Extract info first to populate the record
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info:
            _update_info_sync(dl_id, info)
        ydl.download([url])

    if final_filepath:
        return final_filepath
    # Fallback: use the prepared filename
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return ydl.prepare_filename(info)


def _update_info_sync(dl_id: int, info: dict):
    """Update download record with extracted info (sync, called from thread)."""
    import asyncio as _aio

    async def _do():
        async with async_session() as session:
            dl = await session.get(Download, dl_id)
            if dl:
                dl.title = info.get("title", "")[:500]
                dl.thumbnail = info.get("thumbnail", "")
                dl.duration = info.get("duration", 0) or 0
                await session.commit()

    # Run in a new event loop since we're in a thread
    loop = _aio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    finally:
        loop.close()


async def _update_status(dl_id: int, status: str):
    async with async_session() as session:
        dl = await session.get(Download, dl_id)
        if dl:
            dl.status = status
            await session.commit()


def get_progress(dl_id: int) -> dict:
    return _progress.get(dl_id, {})


async def get_all_downloads(limit: int = 50) -> list[Download]:
    async with async_session() as session:
        result = await session.execute(
            select(Download).order_by(Download.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def delete_download(dl_id: int) -> bool:
    async with async_session() as session:
        dl = await session.get(Download, dl_id)
        if not dl:
            return False
        # Cancel active download
        task = _active.pop(dl_id, None)
        if task:
            task.cancel()
        # Delete file
        if dl.filepath:
            p = Path(dl.filepath)
            if p.exists():
                p.unlink()
        await session.delete(dl)
        await session.commit()
        return True
