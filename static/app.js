// State
let currentVideoInfo = null;
let pollTimer = null;

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
    const resp = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "Failed to extract video info");
    }

    const data = await resp.json();
    currentVideoInfo = data;
    renderFormatSelector(data);
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
    sep.textContent = "── Specific Formats ──";
    select.appendChild(sep);
  }

  // Individual formats
  for (const f of info.formats || []) {
    const opt = document.createElement("option");
    opt.value = f.format_id;
    opt.dataset.note = f.note;

    let label = f.format_id + " | " + f.ext.toUpperCase();
    if (f.resolution) label += " | " + f.resolution;
    if (f.fps) label += " @ " + f.fps + "fps";
    label += " | " + f.media_type.replace("_", " ");
    if (f.note) label += " | " + f.note;
    if (f.filesize) label += " | ~" + formatBytes(f.filesize);
    if (f.tbr) label += " | " + f.tbr + " kbps";

    opt.textContent = label;
    select.appendChild(opt);
  }

  section.classList.remove("hidden");
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
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: currentVideoInfo.url,
        format_id: formatId,
        format_note: note,
      }),
    });

    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.detail || "Failed to start download");
    }

    // Clear input and format section
    document.getElementById("url-input").value = "";
    document.getElementById("format-section").classList.add("hidden");
    currentVideoInfo = null;

    // Refresh downloads and start polling
    refreshDownloads();
    startPolling();
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// --- Downloads list ---
async function refreshDownloads() {
  try {
    const resp = await fetch("/api/downloads");
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
        ? `<img class="dl-thumb" src="${escapeHtml(dl.thumbnail)}" alt="" />`
        : `<div class="dl-thumb"></div>`;

      const title = dl.title || dl.url;
      const statusClass = dl.status;
      const progress = dl.progress || 0;

      let metaParts = [];
      if (dl.platform) metaParts.push(`<span class="badge ${dl.platform}">${dl.platform}</span>`);
      if (dl.format_note) metaParts.push(dl.format_note);
      if (dl.filesize) metaParts.push(formatBytes(dl.filesize));
      if (dl.duration) metaParts.push(formatDuration(dl.duration));
      if (dl.speed) metaParts.push(formatBytes(dl.speed) + "/s");
      if (dl.eta) metaParts.push("ETA: " + dl.eta + "s");

      let progressHtml = "";
      if (dl.status === "downloading" || dl.status === "pending") {
        progressHtml = `
          <div class="dl-progress">
            <div class="dl-progress-bar" style="width: ${progress}%"></div>
          </div>`;
      }

      let actionsHtml = "";
      if (dl.status === "completed") {
        actionsHtml = `
          <button onclick="downloadFile(${dl.id})">Save</button>
          <button class="danger" onclick="deleteDl(${dl.id})">Delete</button>`;
      } else if (dl.status === "failed") {
        actionsHtml = `<button class="danger" onclick="deleteDl(${dl.id})">Remove</button>`;
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
          <span class="status ${statusClass}">${dl.status}</span>
          <div class="dl-actions">${actionsHtml}</div>
        </div>`;
    })
    .join("");
}

// --- Actions ---
function downloadFile(id) {
  window.open(`/api/downloads/${id}/file`, "_blank");
}

async function deleteDl(id) {
  try {
    await fetch(`/api/downloads/${id}`, { method: "DELETE" });
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
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- Init ---
refreshDownloads();
