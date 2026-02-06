# Video Downloader

A private, self-hosted web platform for downloading video content from YouTube, X/Twitter, Instagram, TikTok, and Facebook. Built with FastAPI + yt-dlp.

## Features

- **Multi-platform** — YouTube, X/Twitter, Instagram, TikTok, Facebook (and 3,000+ other sites via yt-dlp)
- **Format selector** — Browse all available formats (resolution, codec, bitrate, file size) and pick exactly what you want
- **Quick picks** — One-click "Best Quality MP4" and "Audio Only" presets
- **Download queue** — Concurrent downloads with live progress tracking
- **Download history** — SQLite-backed history with metadata, thumbnails, and file management
- **File serving** — Download completed files directly from the web UI
- **Docker ready** — Single command deployment
- **Private** — No tracking, no accounts, runs entirely on your machine

## Quick Start

### Option 1: Docker (recommended)

```bash
docker compose up -d
```

Open [http://localhost:8000](http://localhost:8000).

### Option 2: Run locally

```bash
# Prerequisites: Python 3.10+, FFmpeg
pip install -r requirements.txt
python app.py
```

Open [http://localhost:8000](http://localhost:8000).

## Usage

1. **Paste** a video URL from any supported platform
2. **Click Fetch** — the app extracts video info and lists all available formats
3. **Pick a format** from the dropdown (or use a quick-pick button)
4. **Click Download** — the video downloads in the background
5. **Save** completed downloads to your machine from the downloads list

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DOWNLOAD_DIR` | `./downloads` | Where files are stored |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Parallel download limit |
| `PORT` | `8000` | Web server port |
| `HOST` | `0.0.0.0` | Bind address |
| `COOKIES_FILE` | (empty) | Path to `cookies.txt` for authenticated content |
| `DATABASE_URL` | `sqlite+aiosqlite:///data.db` | Database connection string |

### Cookie Authentication

Some content requires authentication (private Instagram posts, age-restricted YouTube videos, etc.). Export your browser cookies to a `cookies.txt` file and set the `COOKIES_FILE` environment variable:

```bash
COOKIES_FILE=./cookies.txt python app.py
```

## Architecture

```
app.py              — FastAPI application, API endpoints, static file serving
downloader.py       — yt-dlp integration, format extraction, download manager
database.py         — SQLAlchemy async models and session management
config.py           — Configuration from environment variables
static/
  index.html        — Single-page web UI
  style.css         — Dark theme styles
  app.js            — Frontend logic (fetch, format selector, queue, polling)
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/extract` | Extract video info and available formats |
| `POST` | `/api/download` | Start a download with selected format |
| `GET` | `/api/downloads` | List all downloads with status/progress |
| `GET` | `/api/downloads/:id/progress` | Live progress for an active download |
| `GET` | `/api/downloads/:id/file` | Serve a completed file |
| `DELETE` | `/api/downloads/:id` | Cancel/delete a download and its file |

## Platform Notes

| Platform | Notes |
|---|---|
| YouTube | May need a JS runtime (Deno/Node) alongside `yt-dlp-ejs` for some operations |
| X/Twitter | Direct tweet URLs work; some content may need auth cookies |
| Instagram | Public posts/reels work; private content needs login cookies |
| TikTok | Standard URLs work; watermark-free downloads available |
| Facebook | Public video URLs work; private content needs login cookies |

## Tech Stack

- **Backend:** Python, FastAPI, yt-dlp, SQLAlchemy (async), aiosqlite
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Storage:** SQLite + local filesystem
- **Containerization:** Docker
