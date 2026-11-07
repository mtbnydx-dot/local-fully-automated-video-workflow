(() => {
  "use strict";

  const view = document.querySelector('[data-view="download-center"]');
  if (!view) return;

  const refs = {
    tabCount: document.querySelector("#downloadCenterTabCount"),
    badge: document.querySelector("#downloadCenterBadge"),
    activeCount: document.querySelector("#downloadActiveCount"),
    pausedCount: document.querySelector("#downloadPausedCount"),
    installedCount: document.querySelector("#downloadInstalledCount"),
    resourceBreakdown: document.querySelector("#downloadResourceBreakdown"),
    partialCount: document.querySelector("#downloadPartialCount"),
    partialSize: document.querySelector("#downloadPartialSize"),
    resumeAll: document.querySelector("#downloadResumeAllButton"),
    modelSize: document.querySelector("#downloadModelSize"),
    sourceLabel: document.querySelector("#downloadSourceLabel"),
    sourceEndpoint: document.querySelector("#downloadSourceEndpoint"),
    root: document.querySelector("#downloadCenterRoot"),
    sourceSettings: document.querySelector("#downloadCenterSourceSettings"),
    openRoot: document.querySelector("#downloadCenterOpenRoot"),
    refresh: document.querySelector("#downloadCenterRefresh"),
    transferSummary: document.querySelector("#downloadTransferSummary"),
    transferFilters: document.querySelector("#downloadTransferFilters"),
    transferList: document.querySelector("#downloadTransferList"),
    resourceSummary: document.querySelector("#downloadResourceSummary"),
    resourceFilters: document.querySelector("#downloadResourceFilters"),
    resourceSearch: document.querySelector("#downloadResourceSearch"),
    resourceSort: document.querySelector("#downloadResourceSort"),
    resourceList: document.querySelector("#downloadResourceList"),
    resourcePrev: document.querySelector("#downloadResourcePrev"),
    resourceNext: document.querySelector("#downloadResourceNext"),
    resourcePageSummary: document.querySelector("#downloadResourcePageSummary"),
    status: document.querySelector("#downloadCenterStatus"),
  };

  const ACTIVE_STATUSES = new Set(["queued", "running", "pausing", "canceling"]);
  const RESUMABLE_STATUSES = new Set(["paused", "interrupted"]);
  const TERMINAL_STATUSES = new Set(["success", "failed", "error", "stopped", "lost", "canceled", "cancelled"]);
  const PAGE_SIZE = 20;
  const state = {
    data: null,
    loading: false,
    visible: false,
    timer: 0,
    transferFilter: "active",
    resourceFilter: "all",
    resourcePage: 1,
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function asNumber(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function formatBytes(value) {
    const bytes = Math.max(0, asNumber(value));
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    const amount = bytes / 1024 ** index;
    const digits = index >= 3 ? 2 : index === 2 ? 1 : 0;
    return `${amount.toFixed(digits)} ${units[index]}`;
  }

  function formatTime(value) {
    const timestamp = asNumber(value);
    if (!timestamp) return "时间未知";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp));
  }

  function formatEta(value) {
    let seconds = Math.max(0, Math.round(asNumber(value)));
    if (!seconds) return "";
    if (seconds < 60) return `约 ${seconds} 秒`;
    const minutes = Math.floor(seconds / 60);
    seconds %= 60;
    if (minutes < 60) return `约 ${minutes} 分 ${seconds} 秒`;
    const hours = Math.floor(minutes / 60);
    return `约 ${hours} 小时 ${minutes % 60} 分`;
  }

  function statusMeta(status) {
    const items = {
      queued: ["排队中", "active"],
      running: ["正在下载", "active"],
      pausing: ["正在暂停", "active"],
      paused: ["已暂停", "paused"],
      interrupted: ["可继续", "paused"],
      canceling: ["正在取消", "active"],
      canceled: ["已取消", "neutral"],
      cancelled: ["已取消", "neutral"],
      success: ["已完成", "success"],
      failed: ["失败", "failed"],
      error: ["失败", "failed"],
      lost: ["状态丢失", "failed"],
      stopped: ["已停止", "neutral"],
    };
    const [label, tone] = items[status] || [status || "未知", "neutral"];
    return { label, tone };
  }

  function resourceStatusMeta(resource) {
    const status = String(resource?.status || "");
    if (status === "downloading") return { label: "正在下载", tone: "active" };
    if (status === "paused") return { label: "断点已暂停", tone: "paused" };
    if (resource?.resource_type === "partial") return { label: "未完成断点", tone: "partial" };
    if (resource?.kind === "custom_node") return { label: "节点已安装", tone: "success" };
    return { label: "已下载", tone: "success" };
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : detail?.message || `请求失败 (${response.status})`;
      throw new Error(message);
    }
    return payload || {};
  }

  function setStatus(message = "", tone = "") {
    refs.status.textContent = message;
    refs.status.className = `download-center-status${tone ? ` ${tone}` : ""}${message ? " visible" : ""}`;
  }

  function transferIsLive(item) {
    const status = String(item?.status || "");
    return ACTIVE_STATUSES.has(status) || RESUMABLE_STATUSES.has(status);
  }

  function transferMatchesFilter(item) {
    if (state.transferFilter === "active") return transferIsLive(item);
    if (state.transferFilter === "history") return TERMINAL_STATUSES.has(String(item?.status || ""));
    return true;
  }

  function renderSummary() {
    const summary = state.data?.summary || {};
    const active = asNumber(summary.active_count);
    const paused = asNumber(summary.paused_count);
    const live = active + paused;
    refs.activeCount.textContent = String(active);
    refs.pausedCount.textContent = paused ? `${paused} 项已暂停或可继续` : "无暂停任务";
    refs.installedCount.textContent = String(asNumber(summary.installed_count));
    refs.resourceBreakdown.textContent = `模型 ${asNumber(summary.model_count)} · 节点 ${asNumber(summary.custom_node_count)}`;
    refs.partialCount.textContent = String(asNumber(summary.partial_count));
    refs.partialSize.textContent = formatBytes(summary.partial_bytes);
    refs.modelSize.textContent = formatBytes(summary.model_bytes);
    if (refs.resumeAll) {
      const resumables = resumablePartials();
      refs.resumeAll.classList.toggle("hidden", !resumables.length);
      if (resumables.length) refs.resumeAll.textContent = `一键续传全部（${resumables.length} 项）`;
    }

    if (active) {
      refs.badge.textContent = `${active} 项正在下载`;
      refs.badge.className = "active";
    } else if (paused) {
      refs.badge.textContent = `${paused} 项可继续`;
      refs.badge.className = "paused";
    } else {
      refs.badge.textContent = "当前空闲";
      refs.badge.className = "idle";
    }
    refs.tabCount.textContent = String(live);
    refs.tabCount.classList.toggle("hidden", !live);

    const source = state.data?.source || {};
    refs.sourceLabel.textContent = `${source.region_label || "自定义"}下载源`;
    refs.sourceEndpoint.textContent = source.hf_endpoint || "未配置 Hugging Face 下载源";
    refs.sourceEndpoint.title = source.hf_endpoint || "";
    const selectedRoot = state.data?.selected_root || {};
    refs.root.textContent = selectedRoot.models_path || selectedRoot.path || "未找到下载目录";
    refs.root.title = refs.root.textContent;
    refs.openRoot.disabled = !state.data?.open_supported || !selectedRoot.path;
  }

  function renderTransferFiles(files) {
    if (!files.length) return '<div class="download-detail-empty">该任务没有可单列的模型文件。</div>';
    return files
      .map((file) => {
        const expected = asNumber(file.expected_bytes);
        const downloaded = asNumber(file.downloaded_bytes);
        const percent = expected ? Math.min(100, downloaded / expected * 100) : asNumber(file.percent);
        return `
          <div class="download-file-row">
            <div>
              <strong>${escapeHtml(file.label || file.name || "资源")}</strong>
              <code title="${escapeHtml(file.path || "")}">${escapeHtml(file.path || "")}</code>
            </div>
            <span>${expected ? `${formatBytes(downloaded)} / ${formatBytes(expected)} · ${percent.toFixed(1)}%` : escapeHtml(file.status || "等待处理")}</span>
          </div>`;
      })
      .join("");
  }

  function renderTransferCard(item) {
    const progress = item.progress || {};
    const status = String(item.status || "");
    const meta = statusMeta(status);
    const total = asNumber(progress.total_bytes);
    const downloaded = asNumber(progress.downloaded_bytes);
    let percent = total ? downloaded / total * 100 : asNumber(progress.percent);
    if (status === "success") percent = 100;
    percent = Math.max(0, Math.min(100, percent));
    const speed = asNumber(progress.speed_mb_s);
    const eta = formatEta(progress.eta_seconds);
    const currentFile = progress.current_file || "";
    const files = Array.isArray(progress.files) ? progress.files : [];
    const indeterminate = !total && ACTIVE_STATUSES.has(status);
    const measurements = [];
    if (total) measurements.push(`${formatBytes(downloaded)} / ${formatBytes(total)}`);
    if (speed > 0 && ACTIVE_STATUSES.has(status)) measurements.push(`${speed.toFixed(2)} MB/s`);
    if (eta && ACTIVE_STATUSES.has(status)) measurements.push(eta);
    if (status === "paused" || status === "interrupted") measurements.push(".part 断点已保留");
    const actions = [];
    if (item.can_pause) actions.push(`<button class="secondary" type="button" data-download-action="pause">暂停</button>`);
    if (item.can_resume) actions.push(`<button class="primary" type="button" data-download-action="resume">继续下载</button>`);
    if (item.can_cancel) actions.push(`<button class="secondary danger" type="button" data-download-action="cancel">取消并保留断点</button>`);
    const log = Array.isArray(item.log_tail) ? item.log_tail.join("\n") : "";
    const error = item.error || item.failure_hint?.message || "";
    return `
      <article class="download-transfer-card ${meta.tone}" data-transfer-id="${escapeHtml(item.id)}">
        <div class="download-transfer-head">
          <div class="download-transfer-name">
            <span class="download-state-mark ${meta.tone}" aria-hidden="true"></span>
            <div>
              <strong>${escapeHtml(item.title || "下载任务")}</strong>
              <small>${escapeHtml(formatTime(item.created_at))}${item.base_dir ? ` · ${escapeHtml(item.base_dir)}` : ""}</small>
            </div>
          </div>
          <span class="download-status-badge ${meta.tone}">${escapeHtml(meta.label)}</span>
        </div>
        <div class="download-progress-copy">
          <strong>${percent.toFixed(1)}%</strong>
          <span>${escapeHtml(measurements.join(" · ") || (TERMINAL_STATUSES.has(status) ? "任务已结束" : "等待进度数据"))}</span>
        </div>
        <div class="download-progress-track ${indeterminate ? "indeterminate" : ""}" role="progressbar" aria-label="${escapeHtml(item.title || "下载任务")}进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent.toFixed(1)}">
          <div class="download-progress-value ${meta.tone}" style="width:${indeterminate ? "36" : percent.toFixed(1)}%"></div>
        </div>
        ${currentFile ? `<div class="download-current-file"><span>当前文件</span><strong>${escapeHtml(currentFile)}</strong></div>` : ""}
        ${error ? `<div class="download-transfer-error">${escapeHtml(error)}</div>` : ""}
        ${actions.length ? `<div class="download-transfer-actions">${actions.join("")}</div>` : ""}
        <details class="download-transfer-details">
          <summary>资源明细与最近日志</summary>
          <div class="download-file-list">${renderTransferFiles(files)}</div>
          ${log ? `<pre>${escapeHtml(log)}</pre>` : ""}
        </details>
      </article>`;
  }

  function renderTransfers() {
    const all = Array.isArray(state.data?.transfers) ? state.data.transfers : [];
    const visible = all.filter(transferMatchesFilter);
    const liveCount = all.filter(transferIsLive).length;
    refs.transferSummary.textContent = `${liveCount} 项可操作 · 共保留 ${all.length} 条记录`;
    refs.transferList.innerHTML = visible.length
      ? visible.map(renderTransferCard).join("")
      : '<div class="download-empty-state">当前筛选下没有下载任务。</div>';
  }

  function filteredResources() {
    const all = Array.isArray(state.data?.resources) ? [...state.data.resources] : [];
    const query = String(refs.resourceSearch.value || "").trim().toLocaleLowerCase("zh-CN");
    const filtered = all.filter((item) => {
      if (state.resourceFilter === "model" && item.resource_type !== "model") return false;
      if (state.resourceFilter === "custom_node" && item.kind !== "custom_node") return false;
      if (state.resourceFilter === "partial" && item.resource_type !== "partial") return false;
      if (!query) return true;
      return [item.label, item.name, item.path, item.relative_path, item.catalog_id, item.category]
        .some((value) => String(value || "").toLocaleLowerCase("zh-CN").includes(query));
    });
    const sort = refs.resourceSort.value;
    filtered.sort((left, right) => {
      if (sort === "name") return String(left.label || left.name || "").localeCompare(String(right.label || right.name || ""), "zh-CN");
      if (sort === "size") return asNumber(right.size_bytes) - asNumber(left.size_bytes);
      return asNumber(right.modified_at) - asNumber(left.modified_at);
    });
    return filtered;
  }

  function renderResourceRow(item) {
    const meta = resourceStatusMeta(item);
    const expected = asNumber(item.expected_bytes);
    const size = asNumber(item.size_bytes);
    const percent = expected ? Math.min(100, size / expected * 100) : asNumber(item.percent);
    const category = item.kind === "custom_node" ? "自定义节点" : item.category || "模型";
    const sizeLabel = item.kind === "custom_node" ? "本地目录" : formatBytes(size);
    const progress = item.resource_type === "partial"
      ? `
        <div class="download-resource-progress">
          <div class="download-progress-track" role="progressbar" aria-label="${escapeHtml(item.label)}下载进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent.toFixed(1)}">
            <div class="download-progress-value ${meta.tone}" style="width:${percent.toFixed(1)}%"></div>
          </div>
          <span>${expected ? `${percent.toFixed(1)}% · ${formatBytes(size)} / ${formatBytes(expected)}` : `${formatBytes(size)} 已保留`}</span>
        </div>`
      : "";
    const resumeAction = item.resource_type === "partial" && item.can_resume
      ? `<button class="primary" type="button" data-resume-partial="${escapeHtml(item.id || "")}">${escapeHtml(item.resume_label || "一键续传")}</button>`
      : "";
    const resumeNote = item.resource_type === "partial" && item.resume_note
      ? `<small class="download-resume-note">${escapeHtml(item.resume_note)}</small>`
      : "";
    return `
      <article class="download-resource-row ${meta.tone}">
        <div class="download-resource-main">
          <span class="download-state-mark ${meta.tone}" aria-hidden="true"></span>
          <div>
            <div class="download-resource-name">
              <strong>${escapeHtml(item.label || item.name || "资源")}</strong>
              <span>${item.managed ? "平台已登记" : "目录内资源"}</span>
            </div>
            <div class="download-resource-meta">${escapeHtml(meta.label)} · ${escapeHtml(category)} · ${escapeHtml(sizeLabel)} · ${escapeHtml(formatTime(item.modified_at))}</div>
            <code title="${escapeHtml(item.path || "")}">${escapeHtml(item.path || "")}</code>
            ${progress}
            ${resumeNote}
          </div>
        </div>
        <div class="download-resource-actions">
          ${resumeAction}
          <button class="secondary download-resource-open" type="button" data-open-path="${escapeHtml(item.open_path || item.path || "")}">打开目录</button>
        </div>
      </article>`;
  }

  function renderResources() {
    const all = Array.isArray(state.data?.resources) ? state.data.resources : [];
    const filtered = filteredResources();
    const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    state.resourcePage = Math.max(1, Math.min(pageCount, state.resourcePage));
    const start = (state.resourcePage - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);
    refs.resourceSummary.textContent = `扫描到 ${all.length} 项 · 当前筛选 ${filtered.length} 项`;
    refs.resourceList.innerHTML = pageItems.length
      ? pageItems.map(renderResourceRow).join("")
      : '<div class="download-empty-state">没有符合当前筛选的本地资源。</div>';
    refs.resourcePageSummary.textContent = `第 ${state.resourcePage} / ${pageCount} 页 · 共 ${filtered.length} 项 · 每页 ${PAGE_SIZE} 项`;
    refs.resourcePrev.disabled = state.resourcePage <= 1;
    refs.resourceNext.disabled = state.resourcePage >= pageCount;
  }

  function render() {
    if (!state.data) return;
    renderSummary();
    renderTransfers();
    renderResources();
  }

  function scheduleRefresh() {
    window.clearTimeout(state.timer);
    const active = asNumber(state.data?.summary?.active_count) > 0;
    const delay = state.visible ? (active ? 1500 : 5000) : 15000;
    state.timer = window.setTimeout(() => loadCenter({ quiet: true }), document.hidden ? Math.max(delay, 30000) : delay);
  }

  async function loadCenter({ force = false, quiet = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    if (!quiet) setStatus("正在同步下载任务与本地目录。", "pending");
    try {
      state.data = await requestJson(`/api/download-center${force ? "?refresh=true" : ""}`);
      render();
      if (!quiet) setStatus(`已于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} 更新。`, "success");
    } catch (error) {
      setStatus(`下载中心同步失败：${error.message}`, "failed");
      if (!state.data) {
        refs.transferList.innerHTML = `<div class="download-empty-state failed">${escapeHtml(error.message)}</div>`;
        refs.resourceList.innerHTML = `<div class="download-empty-state failed">${escapeHtml(error.message)}</div>`;
      }
    } finally {
      state.loading = false;
      scheduleRefresh();
    }
  }

  async function controlTransfer(jobId, action, button) {
    if (action === "cancel" && !window.confirm("取消这个下载任务？已下载的 .part 断点会保留。")) return;
    const card = button.closest(".download-transfer-card");
    card?.classList.add("busy");
    card?.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    const labels = { pause: "暂停", resume: "继续", cancel: "取消" };
    setStatus(`正在${labels[action] || "处理"}下载任务。`, "pending");
    try {
      await requestJson(`/api/install/${encodeURIComponent(jobId)}/${action}`, { method: "POST", body: "{}" });
      await loadCenter({ force: true, quiet: true });
      setStatus(`${labels[action] || "任务操作"}已提交。`, "success");
    } catch (error) {
      setStatus(`${labels[action] || "任务操作"}失败：${error.message}`, "failed");
    } finally {
      card?.classList.remove("busy");
    }
  }

  function resumablePartials() {
    const all = Array.isArray(state.data?.resources) ? state.data.resources : [];
    return all.filter((item) => item.resource_type === "partial" && item.can_resume && item.id);
  }

  async function resumeAllPartials() {
    const targets = resumablePartials();
    if (!targets.length || !refs.resumeAll) return;
    refs.resumeAll.disabled = true;
    let done = 0;
    const failures = [];
    // 逐个串行续传：安装任务后端互斥，并发提交会互相 409。
    for (const item of targets) {
      setStatus(`断点续传 ${done + failures.length + 1}/${targets.length}：${item.label || item.id}`, "pending");
      try {
        await requestJson("/api/download-center/resume", {
          method: "POST",
          body: JSON.stringify({ resource_id: item.id }),
        });
        done += 1;
      } catch (error) {
        failures.push(`${item.label || item.id}：${error.message}`);
      }
      await loadCenter({ force: true, quiet: true });
    }
    setStatus(
      failures.length
        ? `断点续传完成 ${done}/${targets.length}；失败：${failures.slice(0, 3).join("；")}`
        : `已提交 ${done} 项断点续传，进度见上方下载任务。`,
      failures.length ? "failed" : "success",
    );
    refs.resumeAll.disabled = false;
  }

  async function resumePartial(resourceId, button) {
    if (!resourceId) return;
    button.disabled = true;
    button.textContent = "正在续传";
    setStatus("正在建立断点续传任务；现有 .part 文件会原样保留。", "pending");
    try {
      const result = await requestJson("/api/download-center/resume", {
        method: "POST",
        body: JSON.stringify({ resource_id: resourceId }),
      });
      state.transferFilter = "active";
      refs.transferFilters.querySelectorAll("button").forEach((item) => {
        item.classList.toggle("active", item.dataset.transferFilter === "active");
      });
      await loadCenter({ force: true, quiet: true });
      const job = result.job || {};
      setStatus(
        job.completed
          ? "断点文件已经完整，校验与收尾已完成。"
          : result.mode === "job"
            ? "原下载任务已恢复，将从现有断点继续。"
            : "已创建单文件续传任务，将从现有断点继续。",
        "success",
      );
    } catch (error) {
      setStatus(`断点续传失败：${error.message}`, "failed");
      button.disabled = false;
      button.textContent = "一键续传";
    }
  }

  async function openPath(path) {
    if (!path) return;
    setStatus("正在打开系统目录。", "pending");
    try {
      const result = await requestJson("/api/download-center/open", {
        method: "POST",
        body: JSON.stringify({ path }),
      });
      setStatus(`已打开：${result.path || path}`, "success");
    } catch (error) {
      setStatus(`打开目录失败：${error.message}`, "failed");
    }
  }

  refs.transferFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-transfer-filter]");
    if (!button) return;
    state.transferFilter = button.dataset.transferFilter || "all";
    refs.transferFilters.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    renderTransfers();
  });

  refs.resourceFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-resource-filter]");
    if (!button) return;
    state.resourceFilter = button.dataset.resourceFilter || "all";
    state.resourcePage = 1;
    refs.resourceFilters.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    renderResources();
  });

  refs.transferList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-download-action]");
    if (!button) return;
    const card = button.closest("[data-transfer-id]");
    if (!card) return;
    void controlTransfer(card.dataset.transferId, button.dataset.downloadAction, button);
  });

  refs.resourceList.addEventListener("click", (event) => {
    const resumeButton = event.target.closest("[data-resume-partial]");
    if (resumeButton) {
      void resumePartial(resumeButton.dataset.resumePartial, resumeButton);
      return;
    }
    const button = event.target.closest("[data-open-path]");
    if (button) void openPath(button.dataset.openPath);
  });

  refs.resourceSearch.addEventListener("input", () => {
    state.resourcePage = 1;
    renderResources();
  });
  refs.resourceSort.addEventListener("change", () => {
    state.resourcePage = 1;
    renderResources();
  });
  refs.resourcePrev.addEventListener("click", () => {
    state.resourcePage = Math.max(1, state.resourcePage - 1);
    renderResources();
  });
  refs.resourceNext.addEventListener("click", () => {
    state.resourcePage += 1;
    renderResources();
  });
  refs.refresh.addEventListener("click", async () => {
    refs.refresh.disabled = true;
    refs.refresh.textContent = "刷新中";
    await loadCenter({ force: true });
    refs.refresh.disabled = false;
    refs.refresh.textContent = "刷新";
  });
  refs.openRoot.addEventListener("click", () => void openPath(state.data?.selected_root?.models_path || state.data?.selected_root?.path || ""));
  refs.resumeAll?.addEventListener("click", () => void resumeAllPartials());
  refs.sourceSettings.addEventListener("click", () => {
    document.querySelector('.view-tab[data-view="environment"]')?.click();
    window.setTimeout(() => document.querySelector("#openSourceConfigButton")?.click(), 120);
  });

  window.addEventListener("workspace:viewchange", (event) => {
    state.visible = event.detail?.view === "download-center";
    if (state.visible) void loadCenter({ quiet: Boolean(state.data) });
    else scheduleRefresh();
  });
  window.addEventListener("workspace:downloadchange", (event) => {
    state.transferFilter = "active";
    refs.transferFilters.querySelectorAll("button").forEach((item) => {
      item.classList.toggle("active", item.dataset.transferFilter === "active");
    });
    setStatus(event.detail?.message || "下载任务已更新。", "success");
    void loadCenter({ force: true, quiet: true });
  });
  document.addEventListener("visibilitychange", scheduleRefresh);
  window.addEventListener("beforeunload", () => window.clearTimeout(state.timer));

  state.visible = !view.classList.contains("hidden");
  void loadCenter({ quiet: true });
})();
