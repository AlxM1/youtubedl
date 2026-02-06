import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", str(BASE_DIR / "downloads")))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data.db'}")
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

COOKIES_FILE = os.environ.get("COOKIES_FILE", "")

SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be", "youtube-nocookie.com"],
    "twitter": ["twitter.com", "x.com"],
    "instagram": ["instagram.com"],
    "tiktok": ["tiktok.com"],
    "facebook": ["facebook.com", "fb.watch", "fb.com"],
}

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
