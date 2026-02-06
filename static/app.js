// State
let currentVideoInfo = null;
let pollTimer = null;
let apiKey = localStorage.getItem("apiKey") || "";
let deferredInstallPrompt = null;

// --- Service Worker Registration ---
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
}

// --- PWA Install Prompt ---
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  // Show install banner unless dismissed
  if (!localStorage.getItem("installDismissed")) {
    document.getElementById("install-banner").classList.remove("hidden");
  }
});

function installApp() {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  deferredInstallPrompt.userChoice.then((result) => {
    if (result.outcome === "accepted") {
      showToast("App installed!", "success");
    }
    deferredInstallPrompt = null;
    document.getElementById("install-banner").classList.add("hidden");
  });
}

function dismissInstall() {
  document.getElementById("install-banner").classList.add("hidden");
  localStorage.setItem("installDismissed", "1");
}

// Detect if running as installed PWA
window.addEventListener("appinstalled", () => {
  document.getElementById("install-banner").classList.add("hidden");
  deferredInstallPrompt = null;
});

// --- Toast Notifications ---
function showToast(message, type) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast" + (type ? " " + type : "");
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// --- API helper ---
async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const resp = await fetch(path, opts);
  if (resp.status === 401) {
    // Show settings panel for API key entry
    document.getElementById("settings-panel").classList.remove("hidden");
    document.getElementById("settings-apikey").focus();
    throw new Error("API key required. Enter it in Settings above.");
  }
  return resp;
}

// --- Settings ---
function toggleSettings() {
  const panel = document.getElementById("settings-panel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden")) {
    document.getElementById("settings-apikey").value = apiKey;
    checkHealth();
  }
}

function saveApiKey() {
  const input = document.getElementById("settings-apikey");
  apiKey = input.value.trim();
  localStorage.setItem("apiKey", apiKey);
  showToast("API key saved", "success");
  document.getElementById("settings-panel").classList.add("hidden");
  refreshDownloads();
}

async function checkHealth() {
  const el = document.getElementById("settings-health");
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    el.textContent = "Online - " + data.disk_free_mb + " MB free, " + data.active_downloads + " active";
    el.style.color = "#00b894";
  } catch (e) {
    el.textContent = "Offline or unreachable";
    el.style.color = "#e74c3c";
  }
}

// --- Clipboard Paste (mobile) ---
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      document.getElementById("url-input").value = text;
      showToast("Pasted from clipboard");
      // Auto-fetch if it looks like a URL
      if (text.startsWith("http://") || text.startsWith("https://")) {
        fetchFormats();
      }
    }
  } catch (e) {
    // Clipboard API denied — fallback to manual paste
    document.getElementById("url-input").focus();
    showToast("Tap and hold to paste", "error");
  }
}

// --- Share Target ---
// When opened via Android share, the URL comes as a query param
(function handleShareTarget() {
  const params = new URLSearchParams(window.location.search);
  const sharedUrl = params.get("url");
  if (sharedUrl) {
    document.getElementById("url-input").value = sharedUrl;
    // Clean the URL bar
    history.replaceState(null, "", "/");
    // Auto-fetch
    setTimeout(fetchFormats, 300);
  }
})();

// --- Fetch formats ---
async function fetchFormats() {
  const urlInput = document.getElementById("url-input");
  const url = urlInput.value.trim();
  if (!url) return;

  const fetchBtn = document.getElementById("fetch-btn");
  const spinner = document.getElementById("fetch-spinner");
  const errorEl = document.getElementById("fetch-error");
  const formatSection = document.getElementById("format-section");

  fetchBtn.disabled = true;
  spinner.classList.remove("hidden");
  errorEl.classList.add("hidden");
  formatSection.classList.add("hidden");

  try {
    const resp = await api("POST", "/api/extract", { url });

    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "Failed to extract video info");
    }

    const data = await resp.json();
    currentVideoInfo = data;
    renderFormatSelector(data);
    // Haptic feedback on success (if supported)
    if (navigator.vibrate) navigator.vibrate(50);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    fetchBtn.disabled = false;
    spinner.classList.add("hidden");
  }
}

// Handle Enter key on URL input
document.getElementById("url-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") fetchFormats();
});

// --- Render format selector ---
function renderFormatSelector(info) {
  const section = document.getElementById("format-section");
  const thumb = document.getElementById("preview-thumb");
  const title = document.getElementById("preview-title");
  const platform = document.getElementById("preview-platform");
  const duration = document.getElementById("preview-duration");
  const uploader = document.getElementById("preview-uploader");
  const select = document.getElementById("format-select");

  thumb.src = info.thumbnail || "";
  thumb.alt = info.title;
  title.textContent = info.title;
  platform.textContent = info.platform;
  platform.className = "badge " + info.platform;
  duration.textContent = info.duration ? formatDuration(info.duration) : "";
  uploader.textContent = info.uploader || "";

  // Build options
  select.innerHTML = "";

  // Best quality presets
  const bestOpt = document.createElement("option");
  bestOpt.value = "best";
  bestOpt.textContent = "Best Quality (auto-merge MP4)";
  bestOpt.dataset.note = "Best Quality";
  select.appendChild(bestOpt);

  const audioOpt = document.createElement("option");
  audioOpt.value = "best_audio";
  audioOpt.textContent = "Best Audio Only";
  audioOpt.dataset.note = "Audio Only";
  select.appendChild(audioOpt);

  // Separator
  if (info.formats && info.formats.length > 0) {
    const sep = document.createElement("option");
    sep.disabled = true;
    sep.textContent = "\u2500\u2500 Specific Formats \u2500\u2500";
    select.appendChild(sep);
  }

  // Individual formats
  for (const f of info.formats || []) {
    const opt = document.createElement("option");
    opt.value = f.format_id;
    opt.dataset.note = f.note;

    let label = f.ext.toUpperCase();
    if (f.resolution) label += " " + f.resolution;
    if (f.fps && f.fps > 30) label += " @" + f.fps;
    label += " " + f.media_type.replace("_", " ");
    if (f.note) label += " - " + f.note;
    if (f.filesize) label += " ~" + formatBytes(f.filesize);

    opt.textContent = label;
    select.appendChild(opt);
  }

  section.classList.remove("hidden");
  // Scroll format section into view on mobile
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// --- Quick pick ---
function quickPick(formatId) {
  const select = document.getElementById("format-select");
  select.value = formatId;
  startDownload();
}

// --- Start download ---
async function startDownload() {
  if (!currentVideoInfo) return;

  const select = document.getElementById("format-select");
  const formatId = select.value;
  const note = select.selectedOptions[0]?.dataset?.note || "";
  const btn = document.getElementById("download-btn");

  btn.disabled = true;

  try {
    const resp = await api("POST", "/api/download", {
      url: currentVideoInfo.url,
      format_id: formatId,
      format_note: note,
    });

    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "Failed to start download");
    }

    showToast("Download started!", "success");
    if (navigator.vibrate) navigator.vibrate([50, 30, 50]);

    // Clear input and format section
    document.getElementById("url-input").value = "";
    document.getElementById("format-section").classList.add("hidden");
    currentVideoInfo = null;

    // Refresh downloads and start polling
    refreshDownloads();
    startPolling();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// --- Downloads list ---
async function refreshDownloads() {
  try {
    const resp = await api("GET", "/api/downloads");
    const downloads = await resp.json();
    renderDownloads(downloads);

    // Auto-poll if there are active downloads
    const hasActive = downloads.some(
      (d) => d.status === "pending" || d.status === "downloading"
    );
    if (hasActive) {
      startPolling();
    } else {
      stopPolling();
    }
  } catch (err) {
    console.error("Failed to refresh downloads:", err);
  }
}

function renderDownloads(downloads) {
  const list = document.getElementById("downloads-list");

  if (downloads.length === 0) {
    list.innerHTML =
      '<p class="empty-state">No downloads yet. Paste a URL above to get started.</p>';
    return;
  }

  list.innerHTML = downloads
    .map((dl) => {
      const thumbHtml = dl.thumbnail
        ? `<img class="dl-thumb" src="${escapeHtml(dl.thumbnail)}" alt="" loading="lazy" />`
        : `<div class="dl-thumb"></div>`;

      const title = dl.title || dl.url;
      const statusClass = dl.status;
      const progress = dl.progress || 0;

      let metaParts = [];
      if (dl.platform)
        metaParts.push(
          `<span class="badge ${escapeHtml(dl.platform)}">${escapeHtml(dl.platform)}</span>`
        );
      if (dl.format_note) metaParts.push(escapeHtml(dl.format_note));
      if (dl.filesize) metaParts.push(formatBytes(dl.filesize));
      if (dl.duration) metaParts.push(formatDuration(dl.duration));
      if (dl.speed) metaParts.push(formatBytes(dl.speed) + "/s");
      if (dl.eta) metaParts.push("ETA " + dl.eta + "s");

      let progressHtml = "";
      if (dl.status === "downloading" || dl.status === "pending") {
        progressHtml = `
          <div class="dl-progress">
            <div class="dl-progress-bar" style="width: ${Math.min(progress, 100)}%"></div>
          </div>`;
      }

      let actionsHtml = "";
      if (dl.status === "completed") {
        const fileUrl = apiKey
          ? `/api/downloads/${dl.id}/file?api_key=${encodeURIComponent(apiKey)}`
          : `/api/downloads/${dl.id}/file`;
        actionsHtml = `
          <button onclick="window.open('${fileUrl}', '_blank')">Save</button>
          <button class="danger" onclick="deleteDl(${dl.id})">Delete</button>`;
      } else if (dl.status === "failed") {
        actionsHtml = `
          <button onclick="retryDl(${dl.id})">Retry</button>
          <button class="danger" onclick="deleteDl(${dl.id})">Remove</button>`;
      } else {
        actionsHtml = `<button class="danger" onclick="deleteDl(${dl.id})">Cancel</button>`;
      }

      return `
        <div class="dl-item">
          ${thumbHtml}
          <div class="dl-info">
            <div class="dl-title" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
            <div class="dl-meta">${metaParts.join(" &middot; ")}</div>
            ${progressHtml}
            ${dl.error ? `<div class="error-msg">${escapeHtml(dl.error)}</div>` : ""}
          </div>
          <span class="status ${escapeHtml(statusClass)}">${escapeHtml(dl.status)}</span>
          <div class="dl-actions">${actionsHtml}</div>
        </div>`;
    })
    .join("");
}

// --- Actions ---
async function retryDl(id) {
  try {
    const resp = await api("POST", `/api/downloads/${id}/retry`);
    if (!resp.ok) {
      const data = await resp.json();
      showToast("Retry failed: " + (data.detail || "Unknown error"), "error");
      return;
    }
    showToast("Retrying download...");
    refreshDownloads();
    startPolling();
  } catch (err) {
    console.error("Retry failed:", err);
  }
}

async function deleteDl(id) {
  try {
    await api("DELETE", `/api/downloads/${id}`);
    refreshDownloads();
  } catch (err) {
    console.error("Delete failed:", err);
  }
}

// --- Polling ---
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(refreshDownloads, 2000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// Pause polling when app is backgrounded, resume when foregrounded
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopPolling();
  } else {
    refreshDownloads();
  }
});

// --- Helpers ---
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + " " + sizes[i];
}

function formatDuration(seconds) {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${pad(m)}:${pad(s)}`;
  return `${m}:${pad(s)}`;
}

function pad(n) {
  return n.toString().padStart(2, "0");
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// --- Init ---
refreshDownloads();
