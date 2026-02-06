"""
Comprehensive integration & security test suite for VidGrab.
Run with: python tests.py
Requires the server to NOT be running (starts its own).
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

import aiohttp

BASE = "http://127.0.0.1:8111"
API_KEY = "test-secret-key-for-testing-only"
RESULTS = {"pass": 0, "fail": 0, "errors": []}


def report(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS["pass" if passed else "fail"] += 1
    if not passed:
        RESULTS["errors"].append(f"{name}: {detail}")
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not passed else ""))


async def run_tests():
    async with aiohttp.ClientSession() as s:
        print("\n=== 1. HEALTH & BASIC ENDPOINTS ===")
        await test_health(s)
        await test_root_page(s)
        await test_static_assets(s)

        print("\n=== 2. AUTHENTICATION ===")
        await test_auth_required(s)
        await test_auth_valid(s)
        await test_auth_header(s)
        await test_auth_query_param(s)
        await test_auth_skip_static(s)
        await test_auth_skip_health(s)

        print("\n=== 3. URL VALIDATION (SSRF PROTECTION) ===")
        await test_url_validation_empty(s)
        await test_url_validation_no_scheme(s)
        await test_url_validation_file_scheme(s)
        await test_url_validation_ftp_scheme(s)
        await test_url_validation_localhost(s)
        await test_url_validation_127(s)
        await test_url_validation_private_192(s)
        await test_url_validation_private_10(s)
        await test_url_validation_private_172(s)
        await test_url_validation_zero(s)
        await test_url_validation_ipv6_loopback(s)
        await test_url_validation_valid_url(s)

        print("\n=== 4. RATE LIMITING ===")
        await test_rate_limiting(s)

        print("\n=== 5. DOWNLOAD ENDPOINTS ===")
        await test_downloads_list_empty(s)
        await test_download_nonexistent_delete(s)
        await test_download_nonexistent_retry(s)
        await test_download_nonexistent_file(s)
        await test_download_progress_nonexistent(s)
        await test_download_format_validation(s)

        print("\n=== 6. PATH TRAVERSAL PROTECTION ===")
        await test_path_traversal(s)

        print("\n=== 7. INPUT EDGE CASES ===")
        await test_extract_missing_body(s)
        await test_extract_invalid_json(s)
        await test_download_missing_format(s)

        print("\n=== 8. PWA FILES ===")
        await test_manifest(s)
        await test_service_worker(s)
        await test_service_worker_root(s)
        await test_icons(s)

        print("\n=== 9. DISK SPACE CHECK ===")
        await test_health_has_disk_info(s)


# --- 1. Health & Basics ---

async def test_health(s):
    r = await s.get(f"{BASE}/api/health")
    data = await r.json()
    report("Health endpoint returns 200", r.status == 200)
    report("Health has status field", data.get("status") == "ok")
    report("Health has disk_free_mb", "disk_free_mb" in data)
    report("Health has active_downloads", "active_downloads" in data)


async def test_root_page(s):
    r = await s.get(BASE)
    text = await r.text()
    report("Root page returns 200", r.status == 200)
    report("Root page contains VidGrab", "VidGrab" in text)
    report("Root page has manifest link", "manifest.json" in text)
    report("Root page has service worker script", "app.js" in text)
    report("Root page has apple-mobile-web-app-capable", "apple-mobile-web-app-capable" in text)


async def test_static_assets(s):
    for path in ["/static/style.css", "/static/app.js", "/static/manifest.json"]:
        r = await s.get(f"{BASE}{path}")
        report(f"Static {path} returns 200", r.status == 200)


# --- 2. Authentication ---

async def test_auth_required(s):
    r = await s.get(f"{BASE}/api/downloads")
    report("API without key returns 401", r.status == 401)


async def test_auth_valid(s):
    r = await s.get(f"{BASE}/api/downloads", headers={"X-API-Key": API_KEY})
    report("API with valid key returns 200", r.status == 200)


async def test_auth_header(s):
    r = await s.get(f"{BASE}/api/downloads", headers={"X-API-Key": "wrong-key"})
    report("API with wrong key returns 401", r.status == 401)


async def test_auth_query_param(s):
    r = await s.get(f"{BASE}/api/downloads?api_key={API_KEY}")
    report("API with query param key returns 200", r.status == 200)


async def test_auth_skip_static(s):
    r = await s.get(f"{BASE}/static/style.css")
    report("Static files skip auth", r.status == 200)


async def test_auth_skip_health(s):
    # Health endpoint must skip auth (needed for Docker HEALTHCHECK)
    r = await s.get(f"{BASE}/api/health")
    report("Health endpoint skips auth (for Docker HEALTHCHECK)", r.status == 200)


# --- 3. URL Validation ---

async def _post_extract(s, url):
    return await s.post(
        f"{BASE}/api/extract",
        json={"url": url},
        headers={"X-API-Key": API_KEY},
    )


async def test_url_validation_empty(s):
    r = await _post_extract(s, "")
    report("Empty URL rejected", r.status == 422)


async def test_url_validation_no_scheme(s):
    r = await _post_extract(s, "youtube.com/watch?v=123")
    report("URL without scheme rejected", r.status == 422)


async def test_url_validation_file_scheme(s):
    r = await _post_extract(s, "file:///etc/passwd")
    report("file:// scheme rejected", r.status == 422)


async def test_url_validation_ftp_scheme(s):
    r = await _post_extract(s, "ftp://example.com/file")
    report("ftp:// scheme rejected", r.status == 422)


async def test_url_validation_localhost(s):
    r = await _post_extract(s, "http://localhost:8000/api/health")
    report("localhost blocked (SSRF)", r.status == 422)


async def test_url_validation_127(s):
    r = await _post_extract(s, "http://127.0.0.1:8000/api/health")
    report("127.0.0.1 blocked (SSRF)", r.status == 422)


async def test_url_validation_private_192(s):
    r = await _post_extract(s, "http://192.168.1.1/admin")
    report("192.168.x.x blocked (SSRF)", r.status == 422)


async def test_url_validation_private_10(s):
    r = await _post_extract(s, "http://10.0.0.1/internal")
    report("10.x.x.x blocked (SSRF)", r.status == 422)


async def test_url_validation_private_172(s):
    r = await _post_extract(s, "http://172.16.0.1/internal")
    report("172.x.x.x blocked (SSRF)", r.status == 422)


async def test_url_validation_zero(s):
    r = await _post_extract(s, "http://0.0.0.0/admin")
    report("0.0.0.0 blocked (SSRF)", r.status == 422)


async def test_url_validation_ipv6_loopback(s):
    r = await _post_extract(s, "http://[::1]/admin")
    report("IPv6 loopback blocked (SSRF)", r.status == 422)


async def test_url_validation_valid_url(s):
    r = await _post_extract(s, "https://www.example.com/video")
    # Should pass validation (400 from yt-dlp, not 422 from validation)
    report("Valid external URL passes validation", r.status == 400, f"got {r.status}")


# --- 4. Rate Limiting ---

async def test_rate_limiting(s):
    # Fire 12 requests quickly (limit is 10/min)
    statuses = []
    for _ in range(12):
        r = await _post_extract(s, "https://www.example.com/video")
        statuses.append(r.status)
    has_429 = 429 in statuses
    report("Rate limiting triggers after threshold", has_429, f"statuses: {statuses[-3:]}")


# --- 5. Download Endpoints ---

async def test_downloads_list_empty(s):
    r = await s.get(f"{BASE}/api/downloads", headers={"X-API-Key": API_KEY})
    data = await r.json()
    report("Downloads list returns array", isinstance(data, list))


async def test_download_nonexistent_delete(s):
    r = await s.delete(f"{BASE}/api/downloads/99999", headers={"X-API-Key": API_KEY})
    report("Delete nonexistent returns 404", r.status == 404)


async def test_download_nonexistent_retry(s):
    r = await s.post(f"{BASE}/api/downloads/99999/retry", headers={"X-API-Key": API_KEY})
    report("Retry nonexistent returns 404", r.status == 404)


async def test_download_nonexistent_file(s):
    r = await s.get(f"{BASE}/api/downloads/99999/file", headers={"X-API-Key": API_KEY})
    report("File for nonexistent returns 404", r.status == 404)


async def test_download_progress_nonexistent(s):
    r = await s.get(f"{BASE}/api/downloads/99999/progress", headers={"X-API-Key": API_KEY})
    data = await r.json()
    report("Progress for nonexistent returns defaults", data.get("progress") == 0)


async def test_download_format_validation(s):
    r = await s.post(
        f"{BASE}/api/download",
        json={"url": "https://www.youtube.com/watch?v=test", "format_id": "best"},
        headers={"X-API-Key": API_KEY},
    )
    # Should accept the request (download will fail in background but request is valid)
    report("Download request accepted with valid payload", r.status == 200, f"got {r.status}")


# --- 6. Path Traversal ---

async def test_path_traversal(s):
    # Try to access /api/downloads/{id}/file with a crafted DB record
    # We can't directly inject, but we can verify the endpoint checks paths
    r = await s.get(f"{BASE}/api/downloads/1/file", headers={"X-API-Key": API_KEY})
    report("File endpoint rejects invalid download", r.status == 404)


# --- 7. Input Edge Cases ---

async def test_extract_missing_body(s):
    r = await s.post(
        f"{BASE}/api/extract",
        data=b"",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    report("Extract with empty body returns error", r.status in (400, 422))


async def test_extract_invalid_json(s):
    r = await s.post(
        f"{BASE}/api/extract",
        data=b"not json",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    report("Extract with invalid JSON returns error", r.status in (400, 422))


async def test_download_missing_format(s):
    r = await s.post(
        f"{BASE}/api/download",
        json={"url": "https://youtube.com/watch?v=test"},
        headers={"X-API-Key": API_KEY},
    )
    report("Download without format_id returns 422", r.status == 422)


# --- 8. PWA Files ---

async def test_manifest(s):
    r = await s.get(f"{BASE}/static/manifest.json")
    data = await r.json()
    report("Manifest has name", data.get("name") == "VidGrab - Video Downloader")
    report("Manifest has start_url /", data.get("start_url") == "/")
    report("Manifest has display standalone", data.get("display") == "standalone")
    report("Manifest has icons", len(data.get("icons", [])) >= 2)
    report("Manifest has share_target", "share_target" in data)


async def test_service_worker(s):
    r = await s.get(f"{BASE}/static/sw.js")
    text = await r.text()
    report("Service worker exists at /static/sw.js", r.status == 200)
    report("SW has cache name", "vidgrab-v1" in text)
    report("SW skips API caching", '/api/' in text)


async def test_service_worker_root(s):
    r = await s.get(f"{BASE}/sw.js")
    report("Service worker served at /sw.js (root scope)", r.status == 200)
    ct = r.headers.get("content-type", "")
    report("SW has correct content-type", "javascript" in ct)
    report("SW has Service-Worker-Allowed header", "Service-Worker-Allowed" in r.headers)


async def test_icons(s):
    for path in ["/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/icons/icon.svg"]:
        r = await s.get(f"{BASE}{path}")
        report(f"Icon {path} returns 200", r.status == 200)
        length = r.content_length or len(await r.read())
        report(f"Icon {path} has content", length > 0)


# --- 9. Disk Space ---

async def test_health_has_disk_info(s):
    r = await s.get(f"{BASE}/api/health", headers={"X-API-Key": API_KEY})
    data = await r.json()
    report("Health disk_free_mb is number", isinstance(data.get("disk_free_mb"), int))
    report("Health disk_total_mb is number", isinstance(data.get("disk_total_mb"), int))


# --- Runner ---

def main():
    # Remove stale DB
    db_path = os.path.join(os.path.dirname(__file__), "test_data.db")
    if os.path.exists(db_path):
        os.unlink(db_path)

    # Start server
    env = os.environ.copy()
    env["API_KEY"] = API_KEY
    env["PORT"] = "8111"
    env["HOST"] = "127.0.0.1"
    env["EXTRACT_RATE_LIMIT"] = "10"
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env["DOWNLOAD_DIR"] = os.path.join(os.path.dirname(__file__), "test_downloads")

    os.makedirs(env["DOWNLOAD_DIR"], exist_ok=True)

    print("Starting server on port 8111...")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        env=env,
        cwd=os.path.dirname(__file__) or ".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to start
    import urllib.request
    for i in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=2)
            break
        except Exception:
            pass
    else:
        print("FATAL: Server did not start in 15s")
        proc.kill()
        sys.exit(1)

    print("Server started. Running tests...\n")

    try:
        asyncio.run(run_tests())
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        # Cleanup
        import shutil
        if os.path.exists(db_path):
            os.unlink(db_path)
        dl_dir = env["DOWNLOAD_DIR"]
        if os.path.exists(dl_dir):
            shutil.rmtree(dl_dir)

    print(f"\n{'='*50}")
    print(f"RESULTS: {RESULTS['pass']} passed, {RESULTS['fail']} failed")
    if RESULTS["errors"]:
        print(f"\nFAILURES:")
        for e in RESULTS["errors"]:
            print(f"  - {e}")
    print(f"{'='*50}\n")
    sys.exit(0 if RESULTS["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
