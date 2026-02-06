# Video Downloader Platform — Research

## Goal

Build a private, self-hosted interface/platform to download video content from **YouTube**, **X (Twitter)**, **Instagram**, and **TikTok**, storing files locally.

---

## 1. Core Backend Engine: yt-dlp

**[yt-dlp](https://github.com/yt-dlp/yt-dlp)** is the de facto standard. Nearly every tool in this space uses it under the hood.

| Attribute | Detail |
|---|---|
| License | Unlicense |
| Language | Python |
| Supported sites | 3,000+ (YouTube, TikTok, Instagram, X/Twitter, Reddit, Vimeo, etc.) |
| Install | `pip install yt-dlp` |
| Python requirement | 3.10+ (CPython), 3.11+ (PyPy) |
| Key dependency | FFmpeg (for merging/converting), `yt-dlp-ejs` + a JS runtime (Deno/Node/Bun) for YouTube |

### Python API (embed in your own app)

```python
import yt_dlp

def download_video(url, output_dir="./downloads"):
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
```

Progress hooks, metadata extraction, playlist support, cookie-based auth, and format selection are all available programmatically.

---

## 2. Ready-Made Self-Hosted Web UIs

These are turnkey solutions you can deploy with Docker and use from a browser.

### 2a. MeTube (Recommended — simplest path)

| Attribute | Detail |
|---|---|
| Repo | [alexta69/metube](https://github.com/alexta69/metube) |
| Stars | ~10.4k |
| License | AGPL-3.0 |
| Stack | Python + yt-dlp + web UI |
| Deploy | Single Docker command |

```bash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads ghcr.io/alexta69/metube
```

**Features:**
- Paste a URL → pick quality → download. Supports all yt-dlp sites.
- Playlist support, concurrent download limits, custom output directories.
- Browser extensions for Chrome/Firefox (right-click → send to MeTube).
- Light/dark themes, per-user access control.
- Auto-updates yt-dlp nightly.

**Config env vars:** `DOWNLOAD_DIR`, `MAX_CONCURRENT_DOWNLOADS`, `OUTPUT_TEMPLATE`, `YTDL_OPTIONS` (JSON), `HTTPS`, etc.

### 2b. Cobalt

| Attribute | Detail |
|---|---|
| Repo | [imputnet/cobalt](https://github.com/imputnet/cobalt) |
| License | AGPL-3.0 |
| Stack | Node.js (pnpm monorepo) — API + frontend |
| Deploy | Docker |

**Features:**
- Zero tracking, no ads, no accounts. "Paste link, get file."
- Supports YouTube, Instagram, TikTok, X/Twitter, Reddit, SoundCloud, Vimeo, VK, Bilibili, Dailymotion.
- Has its own download engine (does **not** use yt-dlp) — acts as a streaming proxy.
- Self-hostable with Cloudflare Turnstile and API key auth.
- REST API for programmatic use.

**Caveat:** YouTube downloads can be unreliable at scale due to YouTube's aggressive anti-bot measures blocking cobalt's requests.

### 2c. yt-dlp-web-ui

| Attribute | Detail |
|---|---|
| Repo | [marcopiovanello/yt-dlp-web-ui](https://github.com/marcopiovanello/yt-dlp-web-ui) |
| Stack | Go backend + React frontend + yt-dlp |
| Deploy | Docker or binary |

Lightweight web UI with batch downloads, format selection, and progress tracking.

### 2d. YoutubeDL-Material

| Attribute | Detail |
|---|---|
| Repo | [Tzahi12345/YoutubeDL-Material](https://github.com/Tzahi12345/YoutubeDL-Material) |
| Stack | Node.js + Angular + yt-dlp |
| Deploy | Docker |

Full-featured: multi-user, subscriptions, file management, audio-only mode, sharing.

---

## 3. Desktop / CLI Alternatives

| Tool | Type | Notes |
|---|---|---|
| [VidBee](https://vidbee.org/) | Desktop (Electron) | MIT license, bundles yt-dlp + FFmpeg, RSS auto-download |
| [Social-Media-Downloader](https://github.com/nayandas69/Social-Media-Downloader) | Python CLI | Wraps yt-dlp, batch downloads |
| [gallery-dl](https://github.com/mikf/gallery-dl) | Python CLI | Specialized for image galleries but supports some video sites |

---

## 4. Comparison: Which Approach?

| Approach | Pros | Cons | Best for |
|---|---|---|---|
| **MeTube (Docker)** | Zero code, 1-command deploy, auto-updates | Limited customization beyond env vars | Quick personal setup |
| **Cobalt (Docker)** | Clean UI, own engine, privacy-first | YouTube can be flaky, Node.js stack | Non-YouTube-heavy use |
| **Custom app with yt-dlp Python API** | Full control, custom UI, metadata DB, scheduling | Must build & maintain yourself | Tailored requirements |
| **yt-dlp CLI directly** | Most flexible, scriptable | No web UI, CLI-only | Power users / scripting |

---

## 5. Architecture for a Custom Platform

If you want to build your own (maximum control), here's a recommended stack:

```
┌──────────────────────────────────────────────┐
│                  Frontend                     │
│         (React / Next.js / Vue)               │
│  - Paste URL, select quality/format           │
│  - View download queue & history              │
│  - Browse/play downloaded files               │
└──────────────┬───────────────────────────────┘
               │ REST API / WebSocket
┌──────────────▼───────────────────────────────┐
│               Backend (Python)                │
│  - FastAPI or Flask                           │
│  - yt-dlp as Python library                   │
│  - Celery / background workers for downloads  │
│  - SQLite/PostgreSQL for metadata & history   │
│  - FFmpeg for post-processing                 │
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│            Local Storage                      │
│  /downloads/{platform}/{date}/{filename}.mp4  │
└──────────────────────────────────────────────┘
```

### Key dependencies

```
pip install yt-dlp fastapi uvicorn celery sqlalchemy
apt install ffmpeg
# Also need: deno or nodejs (for yt-dlp YouTube support)
```

### Platform-specific notes

| Platform | yt-dlp support | Notes |
|---|---|---|
| **YouTube** | Excellent | Requires `yt-dlp-ejs` + JS runtime (Deno recommended). May need cookies for age-restricted content. |
| **X / Twitter** | Good | Works with direct tweet URLs. Some content needs auth cookies. |
| **Instagram** | Good | Public posts work. Private/stories need login cookies (`--cookies-from-browser` or `cookies.txt`). |
| **TikTok** | Good | Works with standard video URLs. Watermark-free downloads available. |

---

## 6. Recommendation

**For fastest time to value:** Deploy **MeTube** via Docker. One command, covers all 4 platforms, web UI included.

**For a custom platform with full control:** Build a Python backend using yt-dlp as a library, with FastAPI for the API layer and a simple frontend. This gives you:
- Custom metadata storage and search
- Scheduled/automated downloads
- Platform-specific handling and retry logic
- Integration with media servers (Plex, Jellyfin, etc.)

---

## 7. Legal Considerations

- yt-dlp and all listed tools are legal software.
- Downloading copyrighted content without permission may violate copyright law in your jurisdiction.
- These tools are intended for downloading content you have the right to access (your own uploads, Creative Commons content, public domain, etc.).

---

## Sources

- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
- [MeTube GitHub](https://github.com/alexta69/metube)
- [Cobalt GitHub](https://github.com/imputnet/cobalt)
- [yt-dlp-web-ui GitHub](https://github.com/marcopiovanello/yt-dlp-web-ui)
- [YoutubeDL-Material GitHub](https://github.com/Tzahi12345/YoutubeDL-Material)
- [VidBee](https://vidbee.org/)
- [yt-dlp Python integration guide](https://yt-dlp.eknerd.com/docs/embedding%20yt-dlp/using-yt-dlp-in-python-scripts/)
- [yt-dlp complete guide (2026)](https://www.rapidseedbox.com/blog/yt-dlp-complete-guide)
