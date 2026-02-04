/**
 * PicFrame 4.0 Dashboard JavaScript
 * Based on v3 dashboard functionality
 */

let sourcesInitialized = false;
let settingsInitialized = false;

document.addEventListener('DOMContentLoaded', () => {
    initTabSwitching();
    initAdvancedToggles();
    initStatusDashboard();
    initSettingsForm();
});

// =============================================================================
// TAB SWITCHING
// =============================================================================

function initTabSwitching() {
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`tab-${tabId}`).classList.add('active');

    // Initialize sources manager on first load
    if (tabId === 'sources' && !sourcesInitialized) {
        initSourcesManager();
        sourcesInitialized = true;
    }
}

// =============================================================================
// ADVANCED TOGGLES
// =============================================================================

function initAdvancedToggles() {
    // Status advanced toggle
    const statusAdvancedToggle = document.getElementById('status-advanced-toggle');
    const statusAdvancedSection = document.getElementById('status-advanced-section');
    if (statusAdvancedToggle && statusAdvancedSection) {
        statusAdvancedToggle.addEventListener('click', () => {
            statusAdvancedSection.classList.toggle('visible');
            statusAdvancedToggle.textContent = statusAdvancedSection.classList.contains('visible')
                ? '▾ Hide technical details'
                : '▸ Show technical details';
        });
    }

    // Logs advanced toggle
    const logsAdvancedToggle = document.getElementById('logs-advanced-toggle');
    const logsAdvancedSection = document.getElementById('logs-advanced-section');
    if (logsAdvancedToggle && logsAdvancedSection) {
        logsAdvancedToggle.addEventListener('click', () => {
            logsAdvancedSection.classList.toggle('visible');
            logsAdvancedToggle.textContent = logsAdvancedSection.classList.contains('visible')
                ? '▾ Hide logs'
                : '▸ Show logs';
        });
    }

    // Sources table advanced toggle
    const sourcesTableToggle = document.getElementById('sources-table-advanced-toggle');
    const sourcesTable = document.getElementById('sources-table');
    if (sourcesTableToggle && sourcesTable) {
        sourcesTableToggle.addEventListener('click', () => {
            sourcesTable.classList.toggle('show-tech');
            sourcesTableToggle.textContent = sourcesTable.classList.contains('show-tech')
                ? '▾ Hide technical columns'
                : '▸ Show technical columns';
        });
    }
}

// =============================================================================
// STATUS DASHBOARD
// =============================================================================

function initStatusDashboard() {
    const bannerText = document.getElementById("banner-text");
    const bannerPill = document.getElementById("banner-pill");
    const bannerUpdated = document.getElementById("banner-updated");
    const topBanner = document.getElementById("top-banner");

    const overallTitle = document.getElementById("overall-title");
    const overallChip = document.getElementById("overall-chip");

    const trafficGreen = document.getElementById("traffic-green");
    const trafficAmber = document.getElementById("traffic-amber");
    const trafficRed = document.getElementById("traffic-red");

    const remoteCountEl = document.getElementById("remote-count");
    const localCountEl = document.getElementById("local-count");

    const webDot = document.getElementById("web-status-dot");
    const webText = document.getElementById("web-status-text");
    const pfDot = document.getElementById("pf-status-dot");
    const pfText = document.getElementById("pf-status-text");
    const currentRemoteEl = document.getElementById("current-remote");
    const storageIndicator = document.getElementById("storage-indicator");
    const storageText = document.getElementById("storage-text");

    const lastSyncEl = document.getElementById("last-sync");
    const lastRestartEl = document.getElementById("last-restart");
    const logTailEl = document.getElementById("log-tail");

    const btnRefresh = document.getElementById("btn-refresh");
    const btnSyncNow = document.getElementById("btn-sync-now");
    const btnSyncNowSpinner = document.getElementById("btn-sync-now-spinner");
    const btnSyncNowLabel = document.getElementById("btn-sync-now-label");
    const btnRestartPf = document.getElementById("btn-restart-pf");
    const btnRestartPfSpinner = document.getElementById("btn-restart-pf-spinner");
    const btnRestartPfLabel = document.getElementById("btn-restart-pf-label");
    const btnRestartApi = document.getElementById("btn-restart-api");
    const btnRestartApiSpinner = document.getElementById("btn-restart-api-spinner");
    const btnRestartApiLabel = document.getElementById("btn-restart-api-label");

    function setServiceDot(dotEl, textEl, status) {
        if (!dotEl || !textEl) return;
        const s = (status || "").toLowerCase();
        const up = s === "active" || s === "running";
        dotEl.classList.toggle("off", !up);
        textEl.textContent = up ? "RUNNING" : (status || "UNKNOWN").toUpperCase();
    }

    function setStorageDisplay(percent) {
        if (!storageIndicator) return;
        if (percent < 70) {
            storageIndicator.className = "storage-indicator ok";
        } else if (percent < 90) {
            storageIndicator.className = "storage-indicator warn";
        } else {
            storageIndicator.className = "storage-indicator error";
        }
    }

    function setTrafficLights(severity) {
        if (!trafficGreen || !trafficAmber || !trafficRed) return;
        const sev = (severity || "UNKNOWN").toUpperCase();
        trafficGreen.classList.add("off");
        trafficAmber.classList.add("off");
        trafficRed.classList.add("off");

        if (sev === "OK" || sev === "MATCH") {
            trafficGreen.classList.remove("off");
        } else if (sev === "WARN" || sev === "SYNCING") {
            trafficAmber.classList.remove("off");
        } else if (sev === "ERROR" || sev === "MISMATCH") {
            trafficRed.classList.remove("off");
        } else {
            trafficAmber.classList.remove("off");
        }
    }

    function setBannerForSeverity(severity) {
        if (!topBanner || !bannerPill) return;
        const sev = (severity || "UNKNOWN").toUpperCase();
        if (sev === "OK" || sev === "MATCH") {
            topBanner.style.background = "linear-gradient(90deg, #0b7a39, #059669)";
            bannerPill.textContent = "OK";
        } else if (sev === "WARN" || sev === "SYNCING") {
            topBanner.style.background = "linear-gradient(90deg, #92400e, #f97316)";
            bannerPill.textContent = "SYNCING";
        } else if (sev === "ERROR" || sev === "MISMATCH") {
            topBanner.style.background = "linear-gradient(90deg, #b91c1c, #ef4444)";
            bannerPill.textContent = "ERROR";
        } else {
            topBanner.style.background = "linear-gradient(90deg, #4b5563, #6b7280)";
            bannerPill.textContent = "UNKNOWN";
        }
    }

    async function refreshStatus() {
        if (btnRefresh) btnRefresh.disabled = true;
        try {
            const resp = await fetch("/dashboard/status");
            const data = await resp.json();

            const nowStr = new Date().toLocaleString();
            if (bannerUpdated) bannerUpdated.textContent = "Updated: " + nowStr;

            // Sync status
            const syncStatus = data.sync_status || "idle";
            const cloudCount = data.remote_count || 0;
            const localCount = data.local_count || 0;
            const countsMatch = cloudCount === localCount;

            const severity = syncStatus === "syncing" ? "SYNCING" :
                            syncStatus === "error" ? "ERROR" :
                            !countsMatch ? "WARN" :
                            syncStatus === "match" ? "OK" :
                            syncStatus === "idle" ? "OK" : "UNKNOWN";

            if (overallTitle) {
                overallTitle.textContent = syncStatus === "syncing" ? "Syncing photos..." :
                                           syncStatus === "error" ? "Sync error" :
                                           !countsMatch ? `Out of sync (${cloudCount} cloud / ${localCount} local)` :
                                           syncStatus === "match" ? "Photos in sync" :
                                           syncStatus === "idle" ? "Photos in sync" : "Checking status...";
            }
            if (overallChip) {
                overallChip.textContent = severity;
                overallChip.classList.remove("error", "warn");
                if (severity === "ERROR") overallChip.classList.add("error");
                else if (severity === "SYNCING") overallChip.classList.add("warn");
            }
            if (bannerText) bannerText.textContent = overallTitle ? overallTitle.textContent : "Photo sync status";

            setTrafficLights(severity);
            setBannerForSeverity(severity);

            // Counts
            if (remoteCountEl) remoteCountEl.textContent = data.remote_count || "--";
            if (localCountEl) localCountEl.textContent = data.local_count || "--";

            // Services
            const services = data.services || [];
            const pfService = services.find(s => s.name === "picframe" || s.name === "picframe.service");
            const apiService = services.find(s => s.name === "picframe-api" || s.name === "picframe-api.service");

            setServiceDot(pfDot, pfText, pfService?.active ? "active" : "inactive");
            setServiceDot(webDot, webText, "active"); // Dashboard is always running if we're here

            // Current source
            if (currentRemoteEl) currentRemoteEl.textContent = data.current_source || "--";

            // Storage
            if (storageText) storageText.textContent = `${data.storage_percent || 0}% (${data.storage_used || 0} / ${data.storage_total || 0} GB)`;
            setStorageDisplay(data.storage_percent || 0);

            // Last sync and restart
            if (lastSyncEl) lastSyncEl.textContent = data.last_sync || "--";
            if (lastRestartEl) lastRestartEl.textContent = data.last_restart || "--";

            // Logs
            if (logTailEl && data.logs) {
                logTailEl.textContent = data.logs.slice(0, 20).join("\n") || "(no log data)";
            }
        } catch (err) {
            console.error("Failed to refresh status", err);
            if (bannerText) bannerText.textContent = "Error fetching status";
            setBannerForSeverity("ERROR");
        } finally {
            if (btnRefresh) btnRefresh.disabled = false;
        }
    }

    async function syncNow() {
        if (!btnSyncNow) return;
        btnSyncNow.disabled = true;
        if (btnSyncNowSpinner) btnSyncNowSpinner.style.display = "inline-block";
        if (btnSyncNowLabel) btnSyncNowLabel.textContent = "Syncing...";

        try {
            const resp = await fetch("/sync", { method: "POST" });
            const data = await resp.json();
            if (data.error) {
                alert("Sync error: " + data.error);
            } else {
                alert("Sync started!");
                setTimeout(refreshStatus, 2000);
            }
        } catch (err) {
            console.error("Failed to sync", err);
            alert("Error syncing: " + err);
        } finally {
            btnSyncNow.disabled = false;
            if (btnSyncNowSpinner) btnSyncNowSpinner.style.display = "none";
            if (btnSyncNowLabel) btnSyncNowLabel.textContent = "🔄 Sync Now";
        }
    }

    async function restartPfService() {
        if (!btnRestartPf) return;
        if (!confirm("Restart the picture frame display?")) return;

        btnRestartPf.disabled = true;
        if (btnRestartPfSpinner) btnRestartPfSpinner.style.display = "inline-block";
        if (btnRestartPfLabel) btnRestartPfLabel.textContent = "Restarting...";

        try {
            const resp = await fetch("/services/picframe/restart", { method: "POST" });
            if (resp.ok) {
                alert("Picframe service restarted!");
                await refreshStatus();
            } else {
                const data = await resp.json();
                alert("Restart failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            console.error("Failed to restart picframe", err);
            alert("Error restarting: " + err);
        } finally {
            btnRestartPf.disabled = false;
            if (btnRestartPfSpinner) btnRestartPfSpinner.style.display = "none";
            if (btnRestartPfLabel) btnRestartPfLabel.textContent = "♻️ Restart Frame";
        }
    }

    async function restartApiService() {
        if (!btnRestartApi) return;
        if (!confirm("Restart the API service? The page will reload.")) return;

        btnRestartApi.disabled = true;
        if (btnRestartApiSpinner) btnRestartApiSpinner.style.display = "inline-block";
        if (btnRestartApiLabel) btnRestartApiLabel.textContent = "Restarting...";

        try {
            const resp = await fetch("/services/picframe-api/restart", { method: "POST" });
            if (resp.ok) {
                alert("API service restarting... Page will reload.");
                setTimeout(() => window.location.reload(), 3000);
            } else {
                const data = await resp.json();
                alert("Restart failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            console.error("Failed to restart API", err);
            alert("Error restarting: " + err);
        } finally {
            btnRestartApi.disabled = false;
            if (btnRestartApiSpinner) btnRestartApiSpinner.style.display = "none";
            if (btnRestartApiLabel) btnRestartApiLabel.textContent = "♻️ Restart API";
        }
    }

    // Button event listeners
    if (btnRefresh) btnRefresh.addEventListener("click", refreshStatus);
    if (btnSyncNow) btnSyncNow.addEventListener("click", syncNow);
    if (btnRestartPf) btnRestartPf.addEventListener("click", restartPfService);
    if (btnRestartApi) btnRestartApi.addEventListener("click", restartApiService);

    // Auto-refresh thumbnail
    const thumbnailImg = document.getElementById("current-image-thumbnail");
    if (thumbnailImg) {
        setInterval(() => {
            const timestamp = new Date().getTime();
            thumbnailImg.src = `/current-image?t=${timestamp}`;
        }, 30000);
    }

    // Initial load and auto-refresh
    refreshStatus();
    setInterval(refreshStatus, 15000);
}

// =============================================================================
// SOURCES MANAGER
// =============================================================================

const sourcesState = {
    currentRemote: '',
    currentPath: [],
    remotes: [],
    localDirs: [],
    sources: []
};

let sourcesElements = {};

function initSourcesManager() {
    initSourcesElements();
    initSourcesEventListeners();
    loadSourcesInitialData();
}

function initSourcesElements() {
    sourcesElements = {
        sourceId: document.getElementById('input-source-id'),
        label: document.getElementById('input-label'),
        remote: document.getElementById('input-remote'),
        remotePath: document.getElementById('input-remote-path'),
        localDir: document.getElementById('input-local-dir'),
        newDirName: document.getElementById('input-new-dir-name'),
        newDirContainer: document.getElementById('new-dir-input-container'),
        enabled: document.getElementById('input-enabled'),
        btnTest: document.getElementById('btn-test-connection'),
        btnSave: document.getElementById('btn-save-source'),
        sourcesTbody: document.getElementById('sources-tbody'),
        breadcrumb: document.getElementById('breadcrumb-path'),
        remoteDirList: document.getElementById('remote-dir-list'),
        statusMessage: document.getElementById('status-message'),
        form: document.getElementById('add-source-form')
    };
}

function initSourcesEventListeners() {
    if (sourcesElements.remote) {
        sourcesElements.remote.addEventListener('change', onRemoteChange);
    }
    if (sourcesElements.localDir) {
        sourcesElements.localDir.addEventListener('change', onLocalDirChange);
    }
    if (sourcesElements.form) {
        sourcesElements.form.addEventListener('submit', onFormSubmit);
    }
    if (sourcesElements.btnTest) {
        sourcesElements.btnTest.addEventListener('click', onTestConnection);
    }
}

async function loadSourcesInitialData() {
    await Promise.all([
        loadSources(),
        loadRcloneRemotes(),
        loadLocalDirs()
    ]);
}

async function loadSources() {
    try {
        const response = await fetch('/api/sources');
        const data = await response.json();
        sourcesState.sources = data.sources || [];
        renderSourcesTable();
    } catch (err) {
        console.error('Failed to load sources:', err);
        if (sourcesElements.sourcesTbody) {
            sourcesElements.sourcesTbody.innerHTML = `
                <tr>
                    <td colspan="6" class="loading-cell" style="color: #fca5a5;">
                        Error loading sources: ${escapeHtml(err.message)}
                    </td>
                </tr>
            `;
        }
    }
}

function renderSourcesTable() {
    if (!sourcesElements.sourcesTbody) return;

    if (sourcesState.sources.length === 0) {
        sourcesElements.sourcesTbody.innerHTML = `
            <tr>
                <td colspan="6" class="loading-cell">No sources configured yet</td>
            </tr>
        `;
        return;
    }

    const rows = sourcesState.sources.map(source => {
        const statusBadges = [];

        if (source.active) {
            statusBadges.push('<span class="source-status-badge active">Active</span>');
        } else if (source.enabled) {
            statusBadges.push('<span class="source-status-badge enabled">Ready</span>');
        } else {
            statusBadges.push('<span class="source-status-badge disabled">Disabled</span>');
        }

        const activateBtn = source.active
            ? ''
            : `<button class="btn-small" onclick="activateSource('${escapeHtml(source.path)}', '${escapeHtml(source.id)}')">Activate</button> `;

        return `
            <tr>
                <td class="tech-column"><strong>${escapeHtml(source.id)}</strong></td>
                <td>${escapeHtml(source.label)}</td>
                <td><code>${escapeHtml(source.remote || 'local')}</code></td>
                <td class="tech-column"><code>${escapeHtml(source.path)}</code></td>
                <td>${statusBadges.join(' ')}</td>
                <td class="tech-column" style="white-space: nowrap;">
                    ${activateBtn}<button class="btn-small btn-danger" onclick="deleteSource('${escapeHtml(source.id)}')">Delete</button>
                </td>
            </tr>
        `;
    }).join('');

    sourcesElements.sourcesTbody.innerHTML = rows;
}

async function loadRcloneRemotes() {
    try {
        const response = await fetch('/api/rclone/remotes');
        const data = await response.json();

        if (!data.ok) {
            throw new Error(data.error || 'Failed to load remotes');
        }

        sourcesState.remotes = data.remotes || [];
        renderRemoteDropdown();
    } catch (err) {
        console.error('Failed to load remotes:', err);
        if (sourcesElements.remote) {
            sourcesElements.remote.innerHTML = `<option value="">Error: ${escapeHtml(err.message)}</option>`;
        }
        showSourcesStatus('error', `Failed to load rclone remotes: ${err.message}`);
    }
}

function renderRemoteDropdown() {
    if (!sourcesElements.remote) return;

    if (sourcesState.remotes.length === 0) {
        sourcesElements.remote.innerHTML = `<option value="">No remotes configured</option>`;
        return;
    }

    const options = sourcesState.remotes.map(remote =>
        `<option value="${escapeHtml(remote)}">${escapeHtml(remote)}</option>`
    ).join('');

    sourcesElements.remote.innerHTML = `
        <option value="">Select a remote...</option>
        ${options}
    `;
}

async function loadLocalDirs() {
    try {
        const response = await fetch('/api/local/list-dirs');
        const data = await response.json();

        if (!data.ok) {
            throw new Error(data.error || 'Failed to load directories');
        }

        sourcesState.localDirs = data.dirs || [];
        sourcesState.picturesBasePath = data.base_path;
        renderLocalDirDropdown();
    } catch (err) {
        console.error('Failed to load local dirs:', err);
        if (sourcesElements.localDir) {
            sourcesElements.localDir.innerHTML = `<option value="">Error: ${escapeHtml(err.message)}</option>`;
        }
    }
}

function renderLocalDirDropdown() {
    if (!sourcesElements.localDir) return;

    if (sourcesState.localDirs.length === 0) {
        sourcesElements.localDir.innerHTML = `
            <option value="">No directories found</option>
            <option value="new">+ Create new directory</option>
        `;
        return;
    }

    const options = sourcesState.localDirs.map(dir =>
        `<option value="${escapeHtml(dir.path)}">${escapeHtml(dir.path)}</option>`
    ).join('');

    sourcesElements.localDir.innerHTML = `
        <option value="">Select a directory...</option>
        ${options}
        <option value="new">+ Create new directory</option>
    `;

    // Update the hint to show correct base path
    const hint = document.querySelector('#new-dir-input-container .form-hint');
    if (hint && sourcesState.picturesBasePath) {
        hint.textContent = `Will be created in ${sourcesState.picturesBasePath}/`;
    }
}

function onRemoteChange() {
    const selectedRemote = sourcesElements.remote.value;

    if (!selectedRemote) {
        sourcesState.currentRemote = '';
        sourcesState.currentPath = [];
        renderBreadcrumb();
        renderRemoteDirs([]);
        return;
    }

    sourcesState.currentRemote = selectedRemote;
    sourcesState.currentPath = [];
    renderBreadcrumb();
    loadRemoteDirs();
}

function onLocalDirChange() {
    const selectedValue = sourcesElements.localDir.value;

    if (selectedValue === 'new') {
        sourcesElements.newDirContainer.style.display = 'block';
        sourcesElements.newDirName.required = true;
        sourcesElements.newDirName.focus();
    } else {
        sourcesElements.newDirContainer.style.display = 'none';
        sourcesElements.newDirName.required = false;
        sourcesElements.newDirName.value = '';
    }
}

async function loadRemoteDirs() {
    if (!sourcesState.currentRemote) {
        renderRemoteDirs([]);
        return;
    }

    if (sourcesElements.remoteDirList) {
        sourcesElements.remoteDirList.innerHTML = `<div class="dir-item loading">Loading directories...</div>`;
    }

    try {
        const response = await fetch('/api/rclone/list-dirs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                remote: sourcesState.currentRemote,
                path: sourcesState.currentPath.join('/')
            })
        });

        const data = await response.json();

        if (!data.ok) {
            throw new Error(data.error || 'Failed to list directories');
        }

        renderRemoteDirs(data.dirs || []);
    } catch (err) {
        console.error('Failed to load remote dirs:', err);
        if (sourcesElements.remoteDirList) {
            sourcesElements.remoteDirList.innerHTML = `
                <div class="dir-item placeholder" style="color: #fca5a5;">
                    Error: ${escapeHtml(err.message)}
                </div>
            `;
        }
    }
}

function renderRemoteDirs(dirs) {
    if (!sourcesElements.remoteDirList) return;

    if (dirs.length === 0) {
        sourcesElements.remoteDirList.innerHTML = `<div class="dir-item placeholder">No directories found</div>`;
        return;
    }

    const items = dirs.map(dir => {
        const dirData = typeof dir === 'string' ? { name: dir, valid: true } : dir;
        const { name, valid, trimmed_name, reason } = dirData;

        if (!valid) {
            return `
                <div class="dir-item-blocked" title="${escapeHtml(reason)}">
                    <span class="dir-warning-icon">⚠️</span>
                    <span class="dir-name-blocked">${escapeHtml(name)}</span>
                    <span class="dir-warning-text">
                        Invalid name - rename to "${escapeHtml(trimmed_name)}"
                    </span>
                </div>
            `;
        } else {
            return `<div class="dir-item" data-dirname="${escapeHtml(name)}">${escapeHtml(name)}</div>`;
        }
    }).join('');

    sourcesElements.remoteDirList.innerHTML = items;

    sourcesElements.remoteDirList.querySelectorAll('.dir-item[data-dirname]').forEach(item => {
        item.addEventListener('click', () => {
            const dirname = item.getAttribute('data-dirname');
            navigateToDir(dirname);
        });
    });
}

function navigateToDir(dirname) {
    sourcesState.currentPath.push(dirname);
    renderBreadcrumb();
    loadRemoteDirs();
    updateRemotePathInput();
}

function navigateToLevel(level) {
    sourcesState.currentPath = sourcesState.currentPath.slice(0, level);
    renderBreadcrumb();
    loadRemoteDirs();
    updateRemotePathInput();
}

function renderBreadcrumb() {
    if (!sourcesElements.breadcrumb) return;

    if (!sourcesState.currentRemote) {
        sourcesElements.breadcrumb.innerHTML = `<span class="breadcrumb-item root">Select a remote first</span>`;
        return;
    }

    const parts = [`<span class="breadcrumb-item root" data-level="0">Root</span>`];

    sourcesState.currentPath.forEach((part, index) => {
        parts.push(`<span class="breadcrumb-item" data-level="${index + 1}">${escapeHtml(part)}</span>`);
    });

    sourcesElements.breadcrumb.innerHTML = parts.join('');

    sourcesElements.breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
        item.addEventListener('click', () => {
            const level = parseInt(item.getAttribute('data-level'));
            navigateToLevel(level);
        });
    });
}

function updateRemotePathInput() {
    if (sourcesElements.remotePath) {
        sourcesElements.remotePath.value = sourcesState.currentPath.join('/');
    }
}

async function onTestConnection() {
    const remote = sourcesElements.remote.value;
    const path = sourcesElements.remotePath.value;

    if (!remote) {
        showSourcesStatus('error', 'Please select a remote first');
        return;
    }

    const fullPath = path ? `${remote}${path}` : remote;

    sourcesElements.btnTest.disabled = true;
    sourcesElements.btnTest.textContent = 'Testing...';
    showSourcesStatus('info', 'Testing connection...');

    try {
        const response = await fetch('/api/config/test-remote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ remote: fullPath })
        });

        const data = await response.json();

        if (data.ok) {
            showSourcesStatus('success', `Connection successful! Found ${data.file_count} items.`);
        } else {
            showSourcesStatus('error', `Connection failed: ${data.error}`);
        }
    } catch (err) {
        showSourcesStatus('error', `Test failed: ${err.message}`);
    } finally {
        sourcesElements.btnTest.disabled = false;
        sourcesElements.btnTest.textContent = 'Test Connection';
    }
}

async function onFormSubmit(event) {
    event.preventDefault();

    // Handle new directory creation
    let localPath = sourcesElements.localDir.value;
    let createDirectory = false;

    if (localPath === 'new') {
        const newDirName = sourcesElements.newDirName.value.trim();
        if (!newDirName) {
            showSourcesStatus('error', 'Please enter a directory name');
            return;
        }

        if (!/^[a-zA-Z0-9_-]+$/.test(newDirName)) {
            showSourcesStatus('error', 'Directory name must contain only letters, numbers, hyphens, and underscores');
            return;
        }

        // Use the pictures base path from state (set by API)
        localPath = `${sourcesState.picturesBasePath}/${newDirName}`;
        createDirectory = true;
    }

    // Gather form data
    const formData = {
        source_id: sourcesElements.sourceId.value.trim(),
        label: sourcesElements.label.value.trim(),
        rclone_remote: buildFullRemotePath(),
        path: localPath,
        enabled: sourcesElements.enabled.checked,
        create_directory: createDirectory
    };

    // Validate
    if (!formData.source_id) {
        showSourcesStatus('error', 'Source ID is required');
        return;
    }

    if (!formData.label) {
        showSourcesStatus('error', 'Label is required');
        return;
    }

    if (!formData.rclone_remote) {
        showSourcesStatus('error', 'Please select a remote');
        return;
    }

    if (!formData.path) {
        showSourcesStatus('error', 'Please select or create a local directory');
        return;
    }

    // Show confirmation dialog
    const confirmMessage = `Please confirm the new photo source:\n\n` +
        `Name: ${formData.label}\n` +
        `Cloud Location: ${formData.rclone_remote}\n` +
        `Local Storage: ${formData.path}\n` +
        (createDirectory ? `\nA new directory will be created.\n` : '') +
        `\nDo you want to proceed?`;

    if (!confirm(confirmMessage)) {
        return;
    }

    // Disable submit button
    sourcesElements.btnSave.disabled = true;
    sourcesElements.btnSave.textContent = 'Saving...';
    showSourcesStatus('info', 'Creating new source...');

    try {
        const response = await fetch('/api/sources/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.ok) {
            showSourcesStatus('success', `Source "${formData.source_id}" created successfully!`);

            // Reset form
            sourcesElements.form.reset();
            sourcesState.currentPath = [];
            renderBreadcrumb();
            renderRemoteDirs([]);

            // Reload sources
            await loadSources();
        } else {
            showSourcesStatus('error', `Failed to create source: ${data.error}`);
        }
    } catch (err) {
        showSourcesStatus('error', `Error: ${err.message}`);
    } finally {
        sourcesElements.btnSave.disabled = false;
        sourcesElements.btnSave.textContent = 'Add Photo Source';
    }
}

function buildFullRemotePath() {
    const remote = sourcesElements.remote.value;
    const path = sourcesElements.remotePath.value;

    if (!remote) {
        return '';
    }

    return path ? `${remote}${path}` : remote;
}

function showSourcesStatus(type, message) {
    if (!sourcesElements.statusMessage) return;

    sourcesElements.statusMessage.className = `status-message ${type}`;
    sourcesElements.statusMessage.textContent = message;
    sourcesElements.statusMessage.style.display = 'block';

    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            sourcesElements.statusMessage.style.display = 'none';
        }, 5000);
    }
}

async function activateSource(targetPath, sourceId) {
    if (!confirm(`Switch to "${sourceId}"?\n\nThis will sync photos from the cloud and display them on your frame.`)) {
        return;
    }

    showSourcesStatus('info', `Activating "${sourceId}" and syncing photos...`);

    try {
        const response = await fetch('/api/frame-live', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_dir: targetPath })
        });

        const data = await response.json();

        if (data.ok) {
            if (data.sync_triggered) {
                showSourcesStatus('success', `"${sourceId}" activated and synced successfully!`);
            } else {
                showSourcesStatus('success', `"${sourceId}" activated successfully!`);
            }
            // Reload sources to update active status
            await loadSources();
        } else {
            showSourcesStatus('error', `Failed to activate: ${data.error}`);
        }
    } catch (err) {
        showSourcesStatus('error', `Error activating source: ${err.message}`);
    }
}

async function deleteSource(sourceId) {
    if (!confirm(`Are you sure you want to delete source "${sourceId}"?\n\nThis will remove it from the configuration but will NOT delete any files.`)) {
        return;
    }

    showSourcesStatus('info', `Deleting source "${sourceId}"...`);

    try {
        const response = await fetch('/api/sources/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_id: sourceId })
        });

        const data = await response.json();

        if (data.ok) {
            showSourcesStatus('success', `Source "${sourceId}" deleted successfully!`);
            await loadSources();
        } else {
            showSourcesStatus('error', `Failed to delete source: ${data.error}`);
        }
    } catch (err) {
        showSourcesStatus('error', `Error deleting source: ${err.message}`);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// SETTINGS FORM
// =============================================================================

function initSettingsForm() {
    const form = document.getElementById('settings-form');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const btn = document.getElementById('btn-save-settings');
        const statusEl = document.getElementById('settings-status-message');

        const settings = {
            frame_name: document.getElementById('settings-frame-name').value,
            rotation_interval: parseInt(document.getElementById('settings-rotation-interval').value),
            sync_interval: parseInt(document.getElementById('settings-sync-interval').value),
            log_level: document.getElementById('settings-log-level').value
        };

        btn.disabled = true;
        btn.textContent = 'Saving...';

        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            const data = await response.json();

            if (data.ok) {
                statusEl.className = 'status-message success';
                let message = 'Settings saved successfully!';
                if (data.restarted) {
                    message += ' Frame display restarted.';
                }
                statusEl.textContent = message;
                statusEl.style.display = 'block';
                // Update frame name in header if it changed
                const hostName = document.getElementById('host-name');
                if (hostName) hostName.textContent = settings.frame_name;
                setTimeout(() => { statusEl.style.display = 'none'; }, 5000);
            } else {
                statusEl.className = 'status-message error';
                statusEl.textContent = 'Failed to save settings: ' + (data.error || 'Unknown error');
                statusEl.style.display = 'block';
            }
        } catch (err) {
            statusEl.className = 'status-message error';
            statusEl.textContent = 'Error saving settings: ' + err.message;
            statusEl.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Save Settings';
        }
    });
}
