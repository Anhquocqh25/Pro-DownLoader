const state = {
  info: null,
  mediaFormat: "video",
  job: null,
  fileBlob: null,
  fileUrl: "",
  installPrompt: null,
  pollTimer: null,
};

const byId = (id) => document.getElementById(id);
const elements = {
  connectionButton: byId("connectionButton"),
  connectionText: byId("connectionText"),
  installButton: byId("installButton"),
  installDialog: byId("installDialog"),
  settingsButton: byId("settingsButton"),
  settingsDialog: byId("settingsDialog"),
  apiKeyInput: byId("apiKeyInput"),
  saveSettingsButton: byId("saveSettingsButton"),
  urlInput: byId("urlInput"),
  urlError: byId("urlError"),
  pasteButton: byId("pasteButton"),
  fetchButton: byId("fetchButton"),
  mediaSection: byId("mediaSection"),
  thumbnail: byId("thumbnail"),
  thumbnailFallback: byId("thumbnailFallback"),
  duration: byId("duration"),
  mediaTitle: byId("mediaTitle"),
  mediaMeta: byId("mediaMeta"),
  mediaProvider: byId("mediaProvider"),
  formatSelect: byId("formatSelect"),
  cookieBrowser: byId("cookieBrowser"),
  maxQuality: byId("maxQuality"),
  proxyInput: byId("proxyInput"),
  douyinEngine: byId("douyinEngine"),
  impersonate: byId("impersonate"),
  subtitlesToggle: byId("subtitlesToggle"),
  subtitleLanguage: byId("subtitleLanguage"),
  metadataToggle: byId("metadataToggle"),
  thumbnailToggle: byId("thumbnailToggle"),
  downloadButton: byId("downloadButton"),
  jobSection: byId("jobSection"),
  jobLabel: byId("jobLabel"),
  jobPercent: byId("jobPercent"),
  jobState: byId("jobState"),
  jobProgress: byId("jobProgress"),
  jobError: byId("jobError"),
  completeSection: byId("completeSection"),
  fileName: byId("fileName"),
  videoPreview: byId("videoPreview"),
  audioPreview: byId("audioPreview"),
  playButton: byId("playButton"),
  saveButton: byId("saveButton"),
  shareButton: byId("shareButton"),
  historyList: byId("historyList"),
  refreshHistoryButton: byId("refreshHistoryButton"),
  toast: byId("toast"),
};

function apiKey() {
  return localStorage.getItem("proDownloaderApiKey") || "change-me";
}

function advancedOptions() {
  return {
    cookie_browser: elements.cookieBrowser.value,
    proxy: elements.proxyInput.value.trim(),
    max_quality: elements.maxQuality.value,
    subtitles: elements.subtitlesToggle.checked && !elements.subtitlesToggle.disabled,
    subtitle_languages: elements.subtitleLanguage.value || "all",
    metadata: elements.metadataToggle.checked && !elements.metadataToggle.disabled,
    thumbnail: elements.thumbnailToggle.checked && !elements.thumbnailToggle.disabled,
    douyin_engine: elements.douyinEngine.value,
    impersonate: elements.impersonate.value,
  };
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-API-Key", apiKey());
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response;
}

function setConnection(online, text) {
  elements.connectionButton.classList.toggle("is-online", online);
  elements.connectionButton.classList.toggle("is-offline", !online);
  elements.connectionText.textContent = text;
}

async function checkConnection() {
  setConnection(false, "Checking server");
  try {
    await api("/api/health");
    setConnection(true, "Server connected");
  } catch (error) {
    setConnection(false, error.message === "Invalid or missing API key" ? "API key required" : "Server unavailable");
  }
}

function setButtonLoading(button, loading, label) {
  button.disabled = loading;
  button.classList.toggle("is-loading", loading);
  const icon = button.querySelector("svg");
  const text = button.querySelector("span");
  if (icon) {
    icon.setAttribute("data-lucide", loading ? "loader-circle" : button === elements.fetchButton ? "scan-search" : "download");
  }
  if (text) {
    text.textContent = loading ? label : button === elements.fetchButton ? "Fetch" : "Download";
  }
  renderIcons();
}

function validateUrl(value) {
  const text = value.trim();
  if (!text) {
    return "Paste a video URL first.";
  }
  let parsed;
  try {
    parsed = new URL(text);
  } catch {
    return "Enter a complete URL starting with http:// or https://.";
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    return "URL must start with http:// or https://.";
  }
  const host = parsed.hostname.toLowerCase();
  const videoMatch = parsed.pathname.match(/\/video\/([^/?#]+)/);
  if ((host.includes("tiktok.com") || host.includes("tiktokv.com")) && videoMatch) {
    if (!/^\d{8,}$/.test(videoMatch[1])) {
      return "TikTok link looks incomplete. Paste the full video link again.";
    }
  }
  if (host.includes("douyin.com")) {
    const modalId = parsed.searchParams.get("modal_id");
    if (modalId !== null && !/^\d{16,}$/.test(modalId)) {
      return "Douyin link looks incomplete. Paste the full video link again.";
    }
    if (videoMatch && !/^\d{16,}$/.test(videoMatch[1])) {
      return "Douyin link looks incomplete. Paste the full video link again.";
    }
  }
  return "";
}

function showUrlError(message) {
  elements.urlError.textContent = message;
  elements.urlError.hidden = !message;
}

function clearCompletedFile() {
  if (state.fileUrl) {
    URL.revokeObjectURL(state.fileUrl);
  }
  state.fileBlob = null;
  state.fileUrl = "";
  elements.completeSection.hidden = true;
  elements.videoPreview.pause();
  elements.audioPreview.pause();
  elements.videoPreview.removeAttribute("src");
  elements.audioPreview.removeAttribute("src");
  elements.videoPreview.hidden = true;
  elements.audioPreview.hidden = true;
}

async function fetchMedia() {
  const url = elements.urlInput.value.trim();
  const validationError = validateUrl(url);
  showUrlError(validationError);
  if (validationError) {
    elements.mediaSection.hidden = true;
    return;
  }

  setButtonLoading(elements.fetchButton, true, "Fetching");
  elements.jobSection.hidden = true;
  clearCompletedFile();
  try {
    const response = await api("/api/fetch", {
      method: "POST",
      body: JSON.stringify({ url, options: advancedOptions() }),
    });
    state.info = await response.json();
    elements.urlInput.value = state.info.url;
    renderMedia();
    elements.mediaSection.hidden = false;
    elements.mediaSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    state.info = null;
    elements.mediaSection.hidden = true;
    showUrlError(error.message);
  } finally {
    setButtonLoading(elements.fetchButton, false, "");
  }
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "";
  }
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function compatibleFormats() {
  const formats = Array.isArray(state.info?.formats) ? state.info.formats : [];
  if (state.mediaFormat === "audio") {
    const audioFormats = formats.filter((format) => format.media_format === "audio");
    return audioFormats.length
      ? audioFormats
      : [{ id: "", label: "Best audio (MP3)", provider: "yt-dlp", media_format: "audio" }];
  }
  const videoFormats = formats.filter((format) => format.media_format !== "audio");
  return videoFormats.length
    ? videoFormats
    : [{ id: "", label: "Best available video", provider: "yt-dlp", media_format: "video" }];
}

function renderFormats() {
  const formats = compatibleFormats();
  elements.formatSelect.replaceChildren();
  for (const format of formats) {
    const option = document.createElement("option");
    option.value = format.id || "";
    option.textContent = `${format.provider ? `${format.provider} - ` : ""}${format.label || format.id || "Best"}`;
    elements.formatSelect.append(option);
  }
  renderProvider();
}

function selectedFormat() {
  return compatibleFormats().find((format) => (format.id || "") === elements.formatSelect.value) || compatibleFormats()[0];
}

function renderProvider() {
  const format = selectedFormat();
  elements.mediaProvider.textContent = format?.provider ? `Provider: ${format.provider}` : "";
}

function renderMedia() {
  const info = state.info;
  elements.mediaTitle.textContent = info.title || "Untitled video";
  elements.mediaMeta.textContent = [info.uploader, formatDuration(info.duration)].filter(Boolean).join(" · ");

  elements.thumbnail.hidden = !info.thumbnail;
  elements.thumbnailFallback.hidden = Boolean(info.thumbnail);
  if (info.thumbnail) {
    elements.thumbnail.src = info.thumbnail;
    elements.thumbnail.alt = info.title ? `Thumbnail for ${info.title}` : "Video thumbnail";
  } else {
    elements.thumbnail.removeAttribute("src");
    elements.thumbnail.alt = "";
  }

  const duration = formatDuration(info.duration);
  elements.duration.textContent = duration;
  elements.duration.hidden = !duration;

  const subtitleLanguages = Array.isArray(info.subtitle_languages) ? info.subtitle_languages : [];
  elements.subtitlesToggle.disabled = subtitleLanguages.length === 0;
  elements.subtitlesToggle.checked = false;
  elements.subtitleLanguage.disabled = true;
  elements.subtitleLanguage.replaceChildren(new Option("All languages", "all"));
  for (const language of subtitleLanguages) {
    elements.subtitleLanguage.append(new Option(language, language));
  }

  elements.metadataToggle.disabled = !info.supports_metadata;
  elements.metadataToggle.checked = false;
  elements.thumbnailToggle.disabled = !info.supports_thumbnail;
  elements.thumbnailToggle.checked = false;
  elements.douyinEngine.disabled = !new URL(info.url).hostname.toLowerCase().includes("douyin.com");
  if (elements.douyinEngine.disabled) {
    elements.douyinEngine.value = "Auto";
  }

  renderFormats();
  renderIcons();
}

function setMediaFormat(format) {
  state.mediaFormat = format;
  document.querySelectorAll("[data-media-format]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mediaFormat === format);
  });
  renderFormats();
  elements.playButton.querySelector("span").textContent = format === "audio" ? "Play audio" : "Play video";
}

async function startDownload() {
  if (!state.info) {
    return;
  }
  const format = selectedFormat();
  setButtonLoading(elements.downloadButton, true, "Starting");
  clearCompletedFile();
  elements.jobSection.hidden = false;
  elements.jobError.hidden = true;
  updateJob({ status: "queued", progress: 0 });

  try {
    const response = await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: state.info.url,
        media_format: state.mediaFormat,
        format_id: format?.id || null,
        title: state.info.title || "",
        provider: format?.provider || "",
        option: format?.label || format?.id || "",
        reuse_history: true,
        options: advancedOptions(),
      }),
    });
    const created = await response.json();
    await pollJob(created.job_id);
  } catch (error) {
    updateJob({ status: "error", progress: state.job?.progress || 0, error: error.message });
  } finally {
    setButtonLoading(elements.downloadButton, false, "");
  }
}

function updateJob(job) {
  state.job = { ...state.job, ...job };
  const progress = Math.max(0, Math.min(100, Number(state.job.progress) || 0));
  const statusLabels = {
    queued: "Queued",
    running: "Downloading",
    done: "Complete",
    error: "Error",
  };
  elements.jobPercent.textContent = `${progress}%`;
  elements.jobProgress.value = progress;
  elements.jobProgress.textContent = `${progress}%`;
  elements.jobState.textContent = statusLabels[state.job.status] || state.job.status || "Working";
  elements.jobLabel.textContent = state.job.status === "error" ? "Download failed" : "Downloading";
  elements.jobError.textContent = state.job.error || "";
  elements.jobError.hidden = !state.job.error;
}

async function pollJob(jobId) {
  while (true) {
    const response = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    const job = await response.json();
    updateJob(job);
    if (job.status === "done") {
      await loadCompletedFile(job);
      await loadHistory();
      return;
    }
    if (job.status === "error") {
      throw new Error(job.error || "Download failed.");
    }
    await new Promise((resolve) => {
      state.pollTimer = window.setTimeout(resolve, 1000);
    });
  }
}

async function loadCompletedFile(job) {
  const response = await api(job.file_url);
  state.fileBlob = await response.blob();
  state.fileUrl = URL.createObjectURL(state.fileBlob);
  elements.fileName.textContent = job.file_name || "Downloaded file";
  elements.completeSection.hidden = false;
  elements.playButton.querySelector("span").textContent = job.media_format === "audio" ? "Play audio" : "Play video";
  elements.completeSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function togglePreview() {
  if (!state.fileUrl || !state.job) {
    return;
  }
  const isAudio = state.job.media_format === "audio";
  const player = isAudio ? elements.audioPreview : elements.videoPreview;
  const other = isAudio ? elements.videoPreview : elements.audioPreview;
  other.pause();
  other.hidden = true;
  if (!player.src) {
    player.src = state.fileUrl;
  }
  player.hidden = false;
  player.play().catch(() => {});
}

function saveFile() {
  if (!state.fileUrl || !state.job) {
    return;
  }
  const link = document.createElement("a");
  link.href = state.fileUrl;
  link.download = state.job.file_name || (state.job.media_format === "audio" ? "download.mp3" : "download.mp4");
  document.body.append(link);
  link.click();
  link.remove();
}

async function shareFile() {
  if (!state.fileBlob || !state.job) {
    return;
  }
  const file = new File([state.fileBlob], state.job.file_name || "download", { type: state.fileBlob.type });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: state.job.title || state.job.file_name });
      return;
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
    }
  }
  saveFile();
  showToast("Sharing is unavailable here. The file was opened for saving instead.");
}

async function loadHistory() {
  try {
    const response = await api("/api/history");
    const history = await response.json();
    renderHistory(Array.isArray(history) ? history.slice(-8).reverse() : []);
  } catch {
    renderHistory([]);
  }
}

function renderHistory(history) {
  elements.historyList.replaceChildren();
  if (!history.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No downloads yet.";
    elements.historyList.append(empty);
    return;
  }

  for (const entry of history) {
    const item = document.createElement("article");
    item.className = "history-item";
    const title = document.createElement("strong");
    title.textContent = entry.title || entry.url || "Downloaded media";
    const meta = document.createElement("span");
    meta.textContent = [entry.media_format, entry.provider, entry.option].filter(Boolean).join(" · ");
    const time = document.createElement("time");
    time.dateTime = entry.downloaded_at || "";
    time.textContent = formatHistoryDate(entry.downloaded_at);
    item.append(title, meta, time);
    elements.historyList.append(item);
  }
}

function formatHistoryDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

async function pasteUrl() {
  showUrlError("");
  try {
    if (!navigator.clipboard?.readText) {
      throw new Error("Clipboard access needs HTTPS.");
    }
    const text = (await navigator.clipboard.readText()).trim();
    if (!text) {
      throw new Error("Clipboard is empty.");
    }
    elements.urlInput.value = text;
    await fetchMedia();
  } catch (error) {
    elements.urlInput.focus();
    showToast(`${error.message} Paste into the URL field, then Fetch will run automatically.`);
  }
}

function showSettings() {
  elements.apiKeyInput.value = apiKey();
  elements.settingsDialog.showModal();
}

async function saveSettings(event) {
  event.preventDefault();
  localStorage.setItem("proDownloaderApiKey", elements.apiKeyInput.value.trim());
  elements.settingsDialog.close();
  await checkConnection();
  await loadHistory();
}

async function installApp() {
  if (state.installPrompt) {
    state.installPrompt.prompt();
    await state.installPrompt.userChoice;
    state.installPrompt = null;
    return;
  }
  elements.installDialog.showModal();
}

let toastTimer;
function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4000);
}

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function bindEvents() {
  elements.connectionButton.addEventListener("click", showSettings);
  elements.settingsButton.addEventListener("click", showSettings);
  elements.saveSettingsButton.addEventListener("click", saveSettings);
  elements.installButton.addEventListener("click", installApp);
  elements.pasteButton.addEventListener("click", pasteUrl);
  elements.fetchButton.addEventListener("click", fetchMedia);
  elements.downloadButton.addEventListener("click", startDownload);
  elements.formatSelect.addEventListener("change", renderProvider);
  elements.subtitlesToggle.addEventListener("change", () => {
    elements.subtitleLanguage.disabled = !elements.subtitlesToggle.checked;
  });
  elements.playButton.addEventListener("click", togglePreview);
  elements.saveButton.addEventListener("click", saveFile);
  elements.shareButton.addEventListener("click", shareFile);
  elements.refreshHistoryButton.addEventListener("click", loadHistory);
  document.querySelectorAll("[data-media-format]").forEach((button) => {
    button.addEventListener("click", () => setMediaFormat(button.dataset.mediaFormat));
  });
  elements.urlInput.addEventListener("paste", () => {
    window.setTimeout(() => {
      if (!validateUrl(elements.urlInput.value)) {
        fetchMedia();
      }
    }, 50);
  });
  elements.thumbnail.addEventListener("error", () => {
    elements.thumbnail.hidden = true;
    elements.thumbnailFallback.hidden = false;
  });
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installPrompt = event;
  });
}

async function start() {
  bindEvents();
  renderIcons();
  await checkConnection();
  await loadHistory();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

start();
