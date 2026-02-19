# Video Downloader

A private, self-hosted web platform for downloading video content from YouTube, X/Twitter, Instagram, TikTok, and Facebook. Built with FastAPI + yt-dlp.

## Features

- **Multi-platform** — YouTube, X/Twitter, Instagram, TikTok, Facebook (and 3,000+ other sites via yt-dlp)
- **Format selector** — Browse all available formats (resolution, codec, bitrate, file size) and pick exactly what you want
- **Quick picks** — One-click "Best Quality MP4" and "Audio Only" presets
- **Download queue** — Concurrent downloads with live progress tracking
- **Retry failed downloads** — One-click retry from the UI
- **Download history** — SQLite-backed history with metadata, thumbnails, and file management
- **File serving** — Download completed files directly from the web UI
- **Docker ready** — Single command deployment with health checks
- **Private & secure** — API key auth, URL validation, rate limiting, path traversal protection, non-root container

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
| `API_KEY` | (empty) | API key for authentication. Empty = no auth (local-only use) |
| `EXTRACT_RATE_LIMIT` | `10` | Max format-extract requests per IP per minute |
| `MIN_FREE_DISK_MB` | `500` | Minimum free disk space (MB) before refusing downloads |
| `COOKIES_FILE` | (empty) | Path to `cookies.txt` for authenticated content |
| `DATABASE_URL` | `sqlite+aiosqlite:///data.db` | Database connection string |
| `CORTEX_URL` | `http://cortex:3011` | Cortex task reporting endpoint (auto-disabled if unreachable) |
| `CORTEX_TIMEOUT` | `5` | Cortex request timeout in seconds |

### Authentication

Set the `API_KEY` environment variable to protect your instance. Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The frontend will prompt for the key on first use and store it in localStorage. All API requests require the key via `X-API-Key` header or `?api_key=` query param. Static assets and the root page are always accessible.

### Cookie Authentication

Some content requires platform authentication (private Instagram posts, age-restricted YouTube videos, etc.). Export your browser cookies to a `cookies.txt` file and set the `COOKIES_FILE` environment variable:

```bash
COOKIES_FILE=./cookies.txt python app.py
```

## Security

- **API key authentication** — optional but strongly recommended for any non-localhost deployment
- **URL validation** — only HTTP/HTTPS URLs accepted; local/private IPs blocked (SSRF protection)
- **Rate limiting** — per-IP rate limiting on format extraction (10/min) and downloads (20/min)
- **Path traversal protection** — file downloads validated against the download directory
- **Format ID validation** — prevents command injection via format string attacks
- **Socket timeouts** — 30-second timeout prevents hanging on slow/malicious sites
- **Security headers** — CSP, X-Frame-Options, X-Content-Type-Options, etc.
- **Non-root container** — Docker runs as `appuser`, not root
- **Disk space guard** — refuses new downloads when disk is nearly full
- **Stale recovery** — downloads stuck mid-progress are marked as failed and partial files cleaned up on server restart
- **Memory-safe rate limiting** — uses TTL cache to prevent memory leaks

## Cortex Integration

The service reports task activity to Cortex (if available) for centralized monitoring:

- **Task lifecycle** — start, progress, completion, failure events
- **Health checks** — periodic health status reports
- **Download progress** — real-time progress updates (throttled to avoid spam)

Cortex integration is **non-blocking** and auto-disables if the endpoint is unreachable. Configure via:

```bash
CORTEX_URL=http://cortex:3011
CORTEX_TIMEOUT=5
```

## Architecture

```
app.py              — FastAPI application, API endpoints, auth, rate limiting, static serving
downloader.py       — yt-dlp integration, format extraction, download manager, retry logic
database.py         — SQLAlchemy async models and session management
config.py           — Configuration from environment variables
cortex_client.py    — Cortex task reporting integration
static/
  index.html        — Single-page web UI
  style.css         — Dark theme styles
  app.js            — Frontend logic (auth, format selector, queue, polling, retry)
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/extract` | Extract video info and available formats (rate limited) |
| `POST` | `/api/download` | Start a download with selected format (disk space checked) |
| `GET` | `/api/downloads` | List all downloads with status/progress |
| `GET` | `/api/downloads/:id/progress` | Live progress for an active download |
| `POST` | `/api/downloads/:id/retry` | Retry a failed download |
| `GET` | `/api/downloads/:id/file` | Serve a completed file |
| `DELETE` | `/api/downloads/:id` | Cancel/delete a download and its file |
| `GET` | `/api/health` | Health check (disk space, active downloads) |

## Platform Notes

| Platform | Notes |
|---|---|
| YouTube | May need a JS runtime (Deno/Node) alongside `yt-dlp-ejs` for some operations |
| X/Twitter | Direct tweet URLs work; some content may need auth cookies |
| Instagram | Public posts/reels work; private content needs login cookies |
| TikTok | Standard URLs work; watermark-free downloads available |
| Facebook | Public video URLs work; private content needs login cookies |

## Production Deployment

For exposing beyond localhost:

1. **Set `API_KEY`** — generate and set a strong key
2. **Use a reverse proxy** — put nginx/Caddy in front for HTTPS termination
3. **Bind to localhost** — set `HOST=127.0.0.1` and let the reverse proxy handle external traffic
4. **Monitor health** — poll `/api/health` or rely on Docker's built-in HEALTHCHECK

Example nginx config:

```nginx
server {
    listen 443 ssl;
    server_name dl.example.com;

    ssl_certificate     /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 0;
    }
}
```

## Tech Stack

- **Backend:** Python, FastAPI, yt-dlp, SQLAlchemy (async), aiosqlite
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Storage:** SQLite + local filesystem
- **Containerization:** Docker with health checks
