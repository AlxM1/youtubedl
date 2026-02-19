# Changelog - YouTubeDL Service

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-02-19

### Added
- **Cortex Integration** - Task activity reporting to Cortex (http://cortex:3011)
  - Task lifecycle events (start, progress, complete, fail)
  - Periodic health check reporting
  - Auto-disable on connection failure to prevent log spam
- **Security Headers Middleware** - Added comprehensive security headers:
  - Content-Security-Policy
  - X-Content-Type-Options (nosniff)
  - X-Frame-Options (DENY)
  - X-XSS-Protection
  - Referrer-Policy
- **Format ID Validation** - Input validation to prevent injection attacks
- **Socket Timeouts** - 30-second timeout on all yt-dlp network operations
- **Rate Limiting on Downloads** - 20 requests per IP per minute (in addition to extraction limit)
- **Stale File Cleanup** - Partial downloads are now deleted on server restart
- **Configuration Documentation** - Added `.env.example` with all config options
- **CHANGELOG.md** - This file

### Changed
- **Rate Limiter** - Switched from unbounded dict to TTLCache to prevent memory leak
- **API Key Logging** - Query param API key usage now logs deprecation warning
- **Error Messages** - Sanitized to prevent internal info disclosure
- **Dependencies** - Added `httpx>=0.27.0` and `cachetools>=5.3.0`

### Fixed
- **Memory Leak** - Rate limiter dictionary growing indefinitely
- **Hanging Downloads** - Added socket timeout to prevent indefinite hangs
- **Disk Space Waste** - Partial files from failed downloads are now cleaned up
- **Security** - Multiple security hardening improvements (see Security Audit)

### Security
- Fixed potential command injection via format_id (now validated)
- Added comprehensive SSRF protection validation
- Improved path traversal protection logging
- Added security headers to all responses
- Rate limited all mutating endpoints

## [1.0.0] - Initial Release
- Multi-platform video downloader (YouTube, X/Twitter, Instagram, TikTok, Facebook)
- Format selector with quick-pick presets
- Download queue with live progress tracking
- SQLite-backed download history
- Docker containerization
- API key authentication
- Rate limiting on format extraction
- PWA support with service worker
