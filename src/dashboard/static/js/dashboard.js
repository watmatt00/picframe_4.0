/**
 * PicFrame 4.0 Dashboard JavaScript
 * Based on v3 dashboard functionality
 */

let sourcesInitialized = false;
let settingsInitialized = false;
let toolsInitialized = false;

document.addEventListener('DOMContentLoaded', () => {
    initTabSwitching();
    initAdvancedToggles();
    initStatusDashboard();
    initSettingsForm();
    initDeviceManagement();
    initSettingsLogViewer();
    initPhotoTools();
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

    // Initialize or refresh sources when tab is opened
    if (tabId === 'sources') {
        if (!sourcesInitialized) {
            initSourcesManager();
            sourcesInitialized = true;
        } else {
            loadSources();
        }
    }

    // Initialize tools tab on first open
    if (tabId === 'tools' && !toolsInitialized) {
        toolsInitialized = true;
        loadToolsSources();
    }
}

// =============================================================================
// ADVANCED TOGGLES
// =============================================================================

function initAdvancedToggles() {
    // Settings logs toggle
    const settingsLogsToggle = document.getElementById('settings-logs-toggle');
    const settingsLogsSection = document.getElementById('settings-logs-section');
    if (settingsLogsToggle && settingsLogsSection) {
        settingsLogsToggle.addEventListener('click', () => {
            settingsLogsSection.classList.toggle('visible');
            settingsLogsToggle.textContent = settingsLogsSection.classList.contains('visible')
                ? '▾ Hide'
                : '▸ Show';
            if (settingsLogsSection.classList.contains('visible')) {
                loadSettingsLogs();
            }
        });
    }

    // Mobile App Pairing card toggle
    const pairingToggle = document.getElementById('pairing-toggle');
    const pairingSection = document.getElementById('pairing-section');
    if (pairingToggle && pairingSection) {
        pairingToggle.addEventListener('click', () => {
            pairingSection.classList.toggle('visible');
            const isVisible = pairingSection.classList.contains('visible');
            pairingToggle.textContent = isVisible ? '▾ Hide' : '▸ Show';
            // Collapse the devices card when pairing section hides
            if (!isVisible) {
                const devicesCard = document.getElementById('devices-card');
                const toggleBtn = document.getElementById('btn-toggle-devices');
                if (devicesCard) devicesCard.style.display = 'none';
                if (toggleBtn) toggleBtn.textContent = 'Manage Devices';
            }
        });
    }

    // Frame Settings card toggle
    const settingsFormToggle = document.getElementById('settings-form-toggle');
    const settingsFormSection = document.getElementById('settings-form-section');
    if (settingsFormToggle && settingsFormSection) {
        settingsFormToggle.addEventListener('click', () => {
            settingsFormSection.classList.toggle('visible');
            settingsFormToggle.textContent = settingsFormSection.classList.contains('visible')
                ? '▾ Hide'
                : '▸ Show';
        });
    }

    // Updates card toggle
    const updatesToggle = document.getElementById('updates-toggle');
    const updatesSection = document.getElementById('updates-section');
    if (updatesToggle && updatesSection) {
        updatesToggle.addEventListener('click', () => {
            updatesSection.classList.toggle('visible');
            updatesToggle.textContent = updatesSection.classList.contains('visible')
                ? '▾ Hide'
                : '▸ Show';
        });
    }

    // Rename File card toggle
    const renameToggle = document.getElementById('rename-toggle');
    const renameSection = document.getElementById('rename-section');
    if (renameToggle && renameSection) {
        renameToggle.addEventListener('click', () => {
            renameSection.classList.toggle('visible');
            renameToggle.textContent = renameSection.classList.contains('visible') ? '▾ Hide' : '▸ Show';
        });
    }

    // Photo Backups card toggle
    const backupToggle = document.getElementById('backup-toggle');
    const backupSection = document.getElementById('backup-section');
    if (backupToggle && backupSection) {
        backupToggle.addEventListener('click', () => {
            backupSection.classList.toggle('visible');
            const isVisible = backupSection.classList.contains('visible');
            backupToggle.textContent = isVisible ? '▾ Hide' : '▸ Show';
            if (isVisible) {
                loadBackupList();
            }
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

    // Auto-refresh thumbnail in sync with frame rotation interval
    const thumbnailImg = document.getElementById("current-image-thumbnail");
    if (thumbnailImg) {
        const rotationSecs = parseInt(thumbnailImg.dataset.rotationInterval, 10) || 30;
        setInterval(() => {
            thumbnailImg.src = `/current-image?t=${new Date().getTime()}`;
        }, rotationSecs * 1000);
    }

    // Initial load only — use the refresh button for manual updates
    refreshStatus();
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
        label: document.getElementById('input-label'),
        btnSave: document.getElementById('btn-save-source'),
        sourcesTbody: document.getElementById('sources-tbody'),
        statusMessage: document.getElementById('status-message'),
        form: document.getElementById('add-source-form')
    };
}

function initSourcesEventListeners() {
    if (sourcesElements.form) {
        sourcesElements.form.addEventListener('submit', onFormSubmit);
    }
}

async function loadSourcesInitialData() {
    await loadSources();
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

    const name = sourcesElements.label.value.trim();
    if (!name) {
        showSourcesStatus('error', 'Display name is required');
        return;
    }

    sourcesElements.btnSave.disabled = true;
    sourcesElements.btnSave.textContent = 'Saving...';
    showSourcesStatus('info', 'Creating new source...');

    try {
        const response = await fetch('/api/sources/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        const data = await response.json();

        if (data.ok) {
            showSourcesStatus('success', `Source "${data.source_id}" created successfully!`);
            sourcesElements.form.reset();
            await loadSources();
        } else {
            showSourcesStatus('error', `Failed to create source: ${data.error}`);
        }
    } catch (err) {
        showSourcesStatus('error', `Error: ${err.message}`);
    } finally {
        sourcesElements.btnSave.disabled = false;
        sourcesElements.btnSave.textContent = 'Add Source';
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

// =============================================================================
// PAIRING
// =============================================================================

let pairingCountdownInterval = null;

async function generatePairingCode() {
    const errorEl = document.getElementById("pairing-error");
    if (errorEl) errorEl.style.display = "none";

    try {
        const resp = await fetch("/pairing/generate", { method: "POST" });
        const data = await resp.json();

        if (data.error) {
            if (errorEl) {
                errorEl.textContent = data.error;
                errorEl.style.display = "block";
            } else {
                alert("Failed to generate code: " + data.error);
            }
            return;
        }

        const resultDiv = document.getElementById("pairing-result");
        const qrImg = document.getElementById("pairing-qr");
        const codeEl = document.getElementById("pairing-code");
        const countdownEl = document.getElementById("pairing-countdown");

        if (qrImg) qrImg.src = data.qr_data_url;
        if (codeEl) codeEl.textContent = data.code;

        // Start countdown
        if (pairingCountdownInterval) clearInterval(pairingCountdownInterval);
        const expiresAt = new Date(data.expires_at);
        function updateCountdown() {
            const remaining = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
            if (countdownEl) countdownEl.textContent = remaining;
            if (remaining <= 0) {
                clearInterval(pairingCountdownInterval);
                if (resultDiv) resultDiv.style.display = "none";
            }
        }
        updateCountdown();
        pairingCountdownInterval = setInterval(updateCountdown, 1000);

        if (resultDiv) resultDiv.style.display = "block";
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = "Error generating pairing code: " + err.message;
            errorEl.style.display = "block";
        } else {
            alert("Error generating pairing code: " + err.message);
        }
    }
}

// =============================================================================
// DEVICE MANAGEMENT
// =============================================================================

let devicesLoaded = false;

function initDeviceManagement() {
    const toggleBtn = document.getElementById('btn-toggle-devices');
    const devicesCard = document.getElementById('devices-card');
    if (toggleBtn && devicesCard) {
        toggleBtn.addEventListener('click', () => {
            const isVisible = devicesCard.style.display !== 'none';
            devicesCard.style.display = isVisible ? 'none' : 'block';
            toggleBtn.textContent = isVisible ? 'Manage Devices' : 'Hide Devices';
            if (!isVisible) {
                loadDevices();
            }
        });
    }
}

async function loadDevices() {
    const tbody = document.getElementById('devices-tbody');
    const summary = document.getElementById('device-summary');
    if (!tbody) return;

    try {
        const response = await fetch('/api/devices');
        const data = await response.json();

        if (summary) {
            summary.textContent = data.device_count + ' device(s), ' + data.admin_count + ' admin(s)';
        }

        if (!data.devices || data.devices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; opacity: 0.6; padding: 2rem;">No devices paired. Use "Generate Pairing QR Code" above to pair a device.</td></tr>';
            return;
        }

        const canRevoke = data.admin_count > 1;

        const rows = data.devices.map(function(device) {
            const badgeClass = device.role === 'admin' ? 'badge-admin' : 'badge-user';
            const revokeDisabled = (!canRevoke && device.role === 'admin');
            const revokeBtn = revokeDisabled
                ? '<button class="btn-small btn-danger" disabled title="Cannot remove last admin">Revoke</button>'
                : '<button class="btn-small btn-danger" onclick="revokeDevice(\'' + escapeHtml(device.id) + '\', \'' + escapeHtml(device.name) + '\')">Revoke</button>';

            return '<tr>' +
                '<td>' + escapeHtml(device.name) + '</td>' +
                '<td><span class="badge ' + badgeClass + '">' + escapeHtml(device.role) + '</span></td>' +
                '<td>' + (device.paired_at || 'Unknown') + '</td>' +
                '<td>' + (device.last_seen || 'Never') + '</td>' +
                '<td>' + revokeBtn + '</td>' +
                '</tr>';
        }).join('');

        tbody.innerHTML = rows;
    } catch (err) {
        console.error('Failed to load devices:', err);
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #fca5a5; padding: 2rem;">Error loading devices: ' + escapeHtml(err.message) + '</td></tr>';
    }
}

async function revokeDevice(deviceId, deviceName) {
    if (!confirm('Revoke access for "' + deviceName + '"? This device will no longer be able to manage this frame.')) {
        return;
    }

    const statusEl = document.getElementById('devices-status-message');

    try {
        const response = await fetch('/devices/' + deviceId + '/revoke', { method: 'POST' });
        const data = await response.json();

        if (data.ok) {
            if (statusEl) {
                statusEl.className = 'status-message success';
                statusEl.textContent = 'Device "' + deviceName + '" revoked successfully.';
                statusEl.style.display = 'block';
                setTimeout(function() { statusEl.style.display = 'none'; }, 5000);
            }
            await loadDevices();
        } else {
            if (statusEl) {
                statusEl.className = 'status-message error';
                statusEl.textContent = data.error || 'Failed to revoke device';
                statusEl.style.display = 'block';
            }
        }
    } catch (err) {
        console.error('Failed to revoke device:', err);
        if (statusEl) {
            statusEl.className = 'status-message error';
            statusEl.textContent = 'Error: ' + err.message;
            statusEl.style.display = 'block';
        }
    }
}

// =============================================================================
// SETTINGS LOG VIEWER
// =============================================================================

let settingsAutoRefreshInterval = null;

async function loadSettingsLogs() {
    const logType = document.getElementById('settings-log-type');
    const logLines = document.getElementById('settings-log-lines');
    const content = document.getElementById('settings-log-content');
    if (!content) return;

    const type = logType ? logType.value : 'ops';
    const lines = logLines ? logLines.value : '100';

    try {
        const response = await fetch('/api/logs?log_type=' + type + '&lines=' + lines);
        const data = await response.json();

        if (data.logs && data.logs.length > 0) {
            content.textContent = data.logs.join('\n');
        } else {
            content.textContent = 'No log entries found.';
        }
    } catch (err) {
        content.textContent = 'Failed to load logs: ' + err.message;
    }
}

function initSettingsLogViewer() {
    const refreshBtn = document.getElementById('btn-refresh-logs');
    const logType = document.getElementById('settings-log-type');
    const logLines = document.getElementById('settings-log-lines');
    const autoRefresh = document.getElementById('settings-auto-refresh');

    if (refreshBtn) refreshBtn.addEventListener('click', loadSettingsLogs);
    if (logType) logType.addEventListener('change', loadSettingsLogs);
    if (logLines) logLines.addEventListener('change', loadSettingsLogs);

    if (autoRefresh) {
        autoRefresh.addEventListener('change', function() {
            if (autoRefresh.checked) {
                settingsAutoRefreshInterval = setInterval(loadSettingsLogs, 5000);
            } else {
                clearInterval(settingsAutoRefreshInterval);
                settingsAutoRefreshInterval = null;
            }
        });
    }
}

// =============================================================================
// UPDATES
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize day dropdown from saved frequency + day
    const freqEl = document.getElementById('update-frequency');
    const dayEl = document.getElementById('update-day');
    if (freqEl && dayEl) {
        const savedDay = parseInt(dayEl.dataset.savedDay || '1', 10);
        updateDayDropdown(freqEl.value, savedDay);
    }

    const scheduleForm = document.getElementById('update-schedule-form');
    if (scheduleForm) {
        scheduleForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveUpdateSchedule();
        });
    }
});

function updateDayDropdown(frequency, selectedDay) {
    const dayEl = document.getElementById('update-day');
    const labelEl = document.getElementById('update-day-label');
    const dayGroup = document.getElementById('update-day-group');
    if (!dayEl) return;

    if (selectedDay === undefined) {
        selectedDay = parseInt(dayEl.value, 10);
    }

    // Hide day picker for daily
    if (dayGroup) dayGroup.style.display = (frequency === 'daily') ? 'none' : '';

    dayEl.innerHTML = '';

    if (frequency === 'monthly') {
        if (labelEl) labelEl.textContent = 'Day of month';
        const ordinals = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th',
                          '11th','12th','13th','14th','15th','16th','17th','18th','19th','20th',
                          '21st','22nd','23rd','24th','25th','26th','27th','28th'];
        for (let i = 1; i <= 28; i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = ordinals[i - 1];
            if (i === selectedDay) opt.selected = true;
            dayEl.appendChild(opt);
        }
    } else if (frequency === 'weekly') {
        if (labelEl) labelEl.textContent = 'Day of week';
        const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
        for (let i = 0; i < 7; i++) {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = days[i];
            if (i === selectedDay) opt.selected = true;
            dayEl.appendChild(opt);
        }
    }
    // daily: day picker hidden, nothing to populate
}

function _setUpdateMsg(text, color) {
    const el = document.getElementById('update-message');
    if (el) { el.textContent = text; el.style.color = color || '#9ca3af'; }
}

async function checkForUpdates() {
    const btn = document.getElementById('btn-check-updates');
    const spinner = document.getElementById('btn-check-updates-spinner');
    const label = document.getElementById('btn-check-updates-label');
    const applyBtn = document.getElementById('btn-apply-update');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (label) label.textContent = 'Checking...';
    _setUpdateMsg('Contacting GitHub...', '#9ca3af');

    try {
        const resp = await fetch('/api/updates/check', { method: 'POST' });
        if (!resp.ok) throw new Error('Server error ' + resp.status);
        const data = await resp.json();

        // Update version display
        const localVersionEl = document.getElementById('update-local-version');
        const localHashEl = document.getElementById('update-local-commit');
        const remoteVersionEl = document.getElementById('update-remote-version');
        const remoteHashEl = document.getElementById('update-remote-commit');
        const statusEl = document.getElementById('update-status-text');
        const lastCheckedEl = document.getElementById('update-last-checked');

        if (localVersionEl && data.local_version) localVersionEl.textContent = data.local_version;
        if (localHashEl && data.local_commit) localHashEl.textContent = '(' + data.local_commit + ')';
        if (lastCheckedEl && data.checked_at) {
            try {
                const d = new Date(data.checked_at);
                lastCheckedEl.textContent = d.toLocaleDateString('en-US', {day:'numeric', month:'short', year:'numeric'}) +
                    ' at ' + d.toLocaleTimeString('en-US', {hour:'numeric', minute:'2-digit'});
            } catch (e) {
                lastCheckedEl.textContent = data.checked_at;
            }
        }

        if (data.error) {
            _setUpdateMsg('Check failed: ' + data.error, '#f87171');
            if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Check failed</span>';
            if (remoteVersionEl) remoteVersionEl.textContent = '—';
            if (remoteHashEl) remoteHashEl.textContent = '';
        } else if (data.up_to_date === true) {
            if (remoteVersionEl) remoteVersionEl.textContent = data.local_version || 'same';
            if (remoteHashEl) remoteHashEl.textContent = data.remote_commit ? '(' + data.remote_commit + ')' : '';
            if (statusEl) statusEl.innerHTML = '<span style="color:#34d399;">Up to date</span>';
            if (applyBtn) applyBtn.style.opacity = '0.5';
            _setUpdateMsg('', '');
        } else if (data.up_to_date === false) {
            if (remoteVersionEl) remoteVersionEl.textContent = data.remote_version || '—';
            if (remoteHashEl) remoteHashEl.textContent = data.remote_commit ? '(' + data.remote_commit + ')' : '';
            if (statusEl) statusEl.innerHTML = '<span style="color:#f59e0b;">Update available</span>';
            if (applyBtn) applyBtn.style.opacity = '1';
            _setUpdateMsg('Update available — click Apply Now to install.', '#f59e0b');
        } else {
            _setUpdateMsg('Could not determine update status.', '#f87171');
        }
    } catch (err) {
        _setUpdateMsg('Error: ' + err.message, '#f87171');
    } finally {
        if (btn) btn.disabled = false;
        if (spinner) spinner.style.display = 'none';
        if (label) label.textContent = 'Check Now';
    }
}

async function applyUpdate() {
    const btn = document.getElementById('btn-apply-update');
    const spinner = document.getElementById('btn-apply-update-spinner');
    const label = document.getElementById('btn-apply-update-label');

    if (!confirm('Apply update now? This runs git pull on the Pi. The API will need to be restarted to pick up changes.')) return;

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (label) label.textContent = 'Applying...';
    _setUpdateMsg('Running git pull...', '#9ca3af');

    try {
        const resp = await fetch('/api/updates/apply', { method: 'POST' });
        if (!resp.ok) throw new Error('Server error ' + resp.status);
        const data = await resp.json();

        if (data.ok) {
            _setUpdateMsg('Update applied! Restart API to activate.', '#34d399');
            const statusEl = document.getElementById('update-status-text');
            if (statusEl) statusEl.innerHTML = '<span style="color:#34d399;">Applied — restart required</span>';
        } else {
            _setUpdateMsg('Apply failed: ' + (data.error || 'unknown error'), '#f87171');
        }
    } catch (err) {
        _setUpdateMsg('Error: ' + err.message, '#f87171');
    } finally {
        if (btn) btn.disabled = false;
        if (spinner) spinner.style.display = 'none';
        if (label) label.textContent = 'Apply Now';
    }
}

async function saveUpdateSchedule() {
    const msgEl = document.getElementById('update-schedule-message');
    const btn = document.querySelector('#update-schedule-form button[type="submit"]');

    const autoCheck = document.getElementById('update-auto-check')?.checked ?? true;
    const autoApply = document.getElementById('update-auto-apply')?.checked ?? false;
    const frequency = document.getElementById('update-frequency')?.value || 'monthly';
    const day = parseInt(document.getElementById('update-day')?.value || '1', 10);
    // Strip seconds if browser returns HH:MM:SS from <input type="time">
    const rawTime = document.getElementById('update-check-time')?.value || '02:00';
    const checkTime = rawTime.length > 5 ? rawTime.substring(0, 5) : rawTime;

    if (!checkTime || !/^\d{2}:\d{2}$/.test(checkTime)) {
        if (msgEl) {
            msgEl.className = 'status-message error';
            msgEl.textContent = 'Please enter a valid time';
            msgEl.style.display = 'block';
        }
        return;
    }

    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

    try {
        const resp = await fetch('/api/updates/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_check: autoCheck, auto_apply: autoApply, frequency, day, check_time: checkTime })
        });
        if (!resp.ok) {
            throw new Error(`Server error ${resp.status} — the API may be restarting, try again`);
        }
        const data = await resp.json();

        if (data.ok) {
            if (msgEl) {
                msgEl.className = 'status-message success';
                msgEl.textContent = 'Schedule saved!';
                msgEl.style.display = 'block';
                setTimeout(() => { msgEl.style.display = 'none'; }, 4000);
            }
        } else {
            if (msgEl) {
                msgEl.className = 'status-message error';
                msgEl.textContent = 'Failed: ' + (data.error || 'unknown error');
                msgEl.style.display = 'block';
            }
        }
    } catch (err) {
        if (msgEl) {
            msgEl.className = 'status-message error';
            msgEl.textContent = err.message.includes('Failed to fetch')
                ? 'Could not reach the API — it may be restarting. Refresh the page and try again.'
                : 'Error: ' + err.message;
            msgEl.style.display = 'block';
        }
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Save Schedule'; }
    }
}

// =============================================================================
// PHOTO TOOLS TAB
// =============================================================================

function initPhotoTools() {
    // Source loading is triggered by switchTab('tools') — see switchTab().

    // Filename Cleaner
    const btnScanFn = document.getElementById('btn-scan-filenames');
    const btnApplyFn = document.getElementById('btn-apply-filenames');
    const btnApplyFnTop = document.getElementById('btn-apply-filenames-top');
    const chkAllFn = document.getElementById('filenames-check-all');
    if (btnScanFn) btnScanFn.addEventListener('click', runFilenameScan);
    if (btnApplyFn) btnApplyFn.addEventListener('click', runFilenameApply);
    if (btnApplyFnTop) btnApplyFnTop.addEventListener('click', runFilenameApply);
    if (chkAllFn) chkAllFn.addEventListener('change', function () {
        // Only toggle checkboxes in currently visible rows
        document.querySelectorAll('#filenames-tbody tr').forEach(tr => {
            if (tr.style.display !== 'none') {
                const cb = tr.querySelector('.filename-check');
                if (cb) cb.checked = this.checked;
            }
        });
        updateFilenameApplyBtn();
    });

    // Duplicate Finder
    const btnScanDup = document.getElementById('btn-scan-duplicates');
    const btnApplyDup = document.getElementById('btn-apply-duplicates');
    const btnApplyDupTop = document.getElementById('btn-apply-duplicates-top');
    if (btnScanDup) btnScanDup.addEventListener('click', runDupScan);
    if (btnApplyDup) btnApplyDup.addEventListener('click', runDupApply);
    if (btnApplyDupTop) btnApplyDupTop.addEventListener('click', runDupApply);

    // Video Manager
    const btnScanVid = document.getElementById('btn-scan-videos');
    const btnApplyVid = document.getElementById('btn-apply-videos');
    const btnApplyVidTop = document.getElementById('btn-apply-videos-top');
    const chkAllVid = document.getElementById('videos-check-all');
    if (btnScanVid) btnScanVid.addEventListener('click', runVideoScan);
    if (btnApplyVid) btnApplyVid.addEventListener('click', runVideoApply);
    if (btnApplyVidTop) btnApplyVidTop.addEventListener('click', runVideoApply);
    if (chkAllVid) chkAllVid.addEventListener('change', function () {
        document.querySelectorAll('.video-check').forEach(cb => cb.checked = this.checked);
        updateVideoApplyBtn();
    });

    // Close buttons
    const closeFn = document.getElementById('btn-close-filenames');
    const closeDup = document.getElementById('btn-close-duplicates');
    const closeVid = document.getElementById('btn-close-videos');
    if (closeFn) closeFn.addEventListener('click', () => {
        document.getElementById('filenames-result').style.display = 'none';
    });
    if (closeDup) closeDup.addEventListener('click', () => {
        document.getElementById('duplicates-result').style.display = 'none';
    });
    if (closeVid) closeVid.addEventListener('click', () => {
        document.getElementById('videos-result').style.display = 'none';
    });

    // Cancel buttons
    ['btn-cancel-filenames', 'btn-cancel-filenames-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => { if (_fnAbort) _fnAbort.abort(); });
    });
    ['btn-cancel-duplicates', 'btn-cancel-duplicates-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => { if (_dupAbort) _dupAbort.abort(); });
    });
    ['btn-cancel-videos', 'btn-cancel-videos-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => { if (_vidAbort) _vidAbort.abort(); });
    });

    // Rename File card
    const btnScanRename = document.getElementById('btn-scan-rename');
    const btnApplyRename = document.getElementById('btn-apply-rename');
    const btnApplyRenameTop = document.getElementById('btn-apply-rename-top');
    const btnCloseRename = document.getElementById('btn-close-rename');
    if (btnScanRename) btnScanRename.addEventListener('click', runRenameScan);
    if (btnApplyRename) btnApplyRename.addEventListener('click', runRenameApply);
    if (btnApplyRenameTop) btnApplyRenameTop.addEventListener('click', runRenameApply);
    if (btnCloseRename) btnCloseRename.addEventListener('click', () => {
        document.getElementById('rename-result').style.display = 'none';
    });

    // Photo Backups card
    const btnCreateBackup = document.getElementById('btn-create-backup');
    if (btnCreateBackup) btnCreateBackup.addEventListener('click', runCreateBackup);
}

async function loadToolsSources() {
    const sel = document.getElementById('tools-source-select');
    try {
        const data = await apiFetch('/api/sources');
        sel.innerHTML = '';
        (data.sources || []).forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = s.label + (s.active ? ' (active)' : '');
            if (s.active) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch (e) {
        sel.innerHTML = '<option value="">Error loading sources</option>';
    }
}

function toolsSourceId() {
    return document.getElementById('tools-source-select').value;
}

// =============================================================================
// PHOTO BACKUPS
// =============================================================================

async function loadBackupList() {
    const sourceId = toolsSourceId();
    const tbody = document.getElementById('backup-tbody');
    const table = document.getElementById('backup-table');
    const empty = document.getElementById('backup-list-empty');
    if (!sourceId || !tbody) return;
    tbody.innerHTML = '<tr><td colspan="4" style="color:#94a3b8;">Loading…</td></tr>';
    if (table) table.style.display = 'table';
    if (empty) empty.style.display = 'none';
    try {
        const data = await apiFetch(`/api/tools/backup/${sourceId}/list`);
        if (!data.ok) {
            tbody.innerHTML = `<tr><td colspan="4" style="color:#f87171;">${data.error || 'Error loading backups'}</td></tr>`;
            return;
        }
        const backups = data.backups || [];
        if (backups.length === 0) {
            if (table) table.style.display = 'none';
            if (empty) empty.style.display = 'block';
            return;
        }
        if (empty) empty.style.display = 'none';
        if (table) table.style.display = 'table';
        tbody.innerHTML = backups.map(b => {
            const created = new Date(b.created_at).toLocaleString();
            return `<tr>
                <td style="font-family:monospace;font-size:0.85rem;">${b.filename}</td>
                <td>${fmtBytes(b.size_bytes)}</td>
                <td>${created}</td>
                <td><button class="btn secondary" style="padding:0.25rem 0.6rem;font-size:0.8rem;"
                    onclick="runDeleteBackup('${b.filename.replace(/'/g, "\\'")}')">Delete</button></td>
            </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" style="color:#f87171;">Error: ${e.message}</td></tr>`;
    }
}

async function runCreateBackup() {
    const sourceId = toolsSourceId();
    if (!sourceId) { alert('Select a photo source first.'); return; }
    const btn = document.getElementById('btn-create-backup');
    const status = document.getElementById('backup-create-status');
    btn.disabled = true;
    btn.textContent = 'Creating…';
    status.textContent = 'This may take a minute for large libraries…';
    status.style.color = '#94a3b8';
    try {
        const data = await apiFetch(`/api/tools/backup/${sourceId}/create`, { method: 'POST' });
        if (data.ok) {
            status.textContent = `Backup created: ${data.filename} (${fmtBytes(data.size_bytes)})`;
            status.style.color = '#4ade80';
            await loadBackupList();
            // Auto-collapse after 2 seconds
            setTimeout(() => {
                const section = document.getElementById('backup-section');
                const toggle = document.getElementById('backup-toggle');
                if (section && section.classList.contains('visible')) {
                    section.classList.remove('visible');
                    if (toggle) toggle.textContent = '▸ Show';
                }
                status.textContent = '';
            }, 2000);
        } else {
            status.textContent = data.error || 'Backup failed';
            status.style.color = '#f87171';
        }
    } catch (e) {
        status.textContent = `Error: ${e.message}`;
        status.style.color = '#f87171';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Create Backup';
    }
}

async function runDeleteBackup(filename) {
    if (!confirm(`Delete backup "${filename}"? This cannot be undone.`)) return;
    const sourceId = toolsSourceId();
    try {
        const data = await apiFetch(`/api/tools/backup/${sourceId}/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename }),
        });
        if (data.ok) {
            await loadBackupList();
        } else {
            alert(data.error || 'Delete failed');
        }
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

function fmtEta(count, secPerItem = 3) {
    const secs = count * secPerItem;
    if (secs < 60) return `~${secs} sec`;
    const mins = Math.round(secs / 60);
    return `~${mins} min`;
}

function fmtBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

function reasonLabel(r) {
    return {
        google_id: 'Google ID',
        numbered_suffix: 'Numbered dup',
        ext_case: 'Ext case',
        long_name: 'Long name',
        spaces: 'Spaces',
        wrong_ext: 'Wrong ext',
    }[r] || r;
}

// ----- Filename Cleaner -----

async function runFilenameScan() {
    const src = toolsSourceId();
    if (!src) { alert('Select a source first'); return; }
    const btn = document.getElementById('btn-scan-filenames');
    btn.disabled = true; btn.textContent = 'Scanning…';
    document.getElementById('filenames-result').style.display = 'none';
    try {
        const data = await apiFetch(`/api/tools/${src}/scan/filenames`);
        if (!data.ok) throw new Error(data.error || 'Scan failed');
        renderFilenameResults(src, data);
    } catch (e) {
        alert('Filename scan failed: ' + e.message);
    } finally {
        btn.disabled = false; btn.textContent = 'Scan';
    }
}

// Active filter set — keys are reason codes or "needs_review"
let _fnActiveFilters = new Set();
let _fnCurrentSrc = '';
let _fnFixes = [];

// AbortControllers for cancelling in-progress apply jobs
let _fnAbort = null;
let _dupAbort = null;
let _vidAbort = null;

function renderFilenameResults(src, data) {
    _fnCurrentSrc = src;
    _fnFixes = data.fixes || [];
    _fnActiveFilters = new Set();  // reset to "All" on new scan

    const summary = document.getElementById('filenames-summary');
    const resultDiv = document.getElementById('filenames-result');

    const mtimeCount = _fnFixes.filter(f => f.needs_review).length;
    const mtimeNote = mtimeCount ? ` · ${mtimeCount} without EXIF date` : '';
    summary.textContent = _fnFixes.length === 0
        ? `✅ All ${data.total_files_scanned} files look clean — nothing to fix.`
        : `Found ${_fnFixes.length} file(s) with issues (scanned ${data.total_files_scanned} total)${mtimeNote}.`;

    const setActionVisibility = (visible) => {
        ['btn-apply-filenames', 'btn-apply-filenames-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.closest('.button-row').style.display = visible ? '' : 'none';
        });
    };

    if (_fnFixes.length === 0) {
        document.getElementById('filenames-table-wrap').style.display = 'none';
        document.getElementById('filenames-filter-bar').innerHTML = '';
        setActionVisibility(false);
        resultDiv.style.display = 'block';
        return;
    }

    _buildFilterBar();
    _renderFilenameRows();

    document.getElementById('filenames-table-wrap').style.display = '';
    setActionVisibility(true);
    resultDiv.style.display = 'block';
}

function _buildFilterBar() {
    const bar = document.getElementById('filenames-filter-bar');

    // Count per issue type
    const counts = {};
    let mtimeCount = 0;
    _fnFixes.forEach(f => {
        f.reasons.forEach(r => { counts[r] = (counts[r] || 0) + 1; });
        if (f.needs_review) mtimeCount++;
    });

    const filterTooltips = {
        all:            'Show all files with issues',
        google_id:      'Files with a Google Photos token appended — e.g. IMG_1592 {AByz57...}.HEIC',
        numbered_suffix:'Files with a duplicate-copy suffix — e.g. photo (1).jpg or 20230101(0).jpg',
        ext_case:       'Files with an uppercase extension — e.g. .JPG or .HEIC (will be lowercased)',
        long_name:      'Filename stem is over 20 characters — likely machine-generated; will be renamed to YYYYMMDD_HHMMSS',
        spaces:         'Filename contains spaces — will be replaced with underscores',
        wrong_ext:      'File bytes don\'t match declared extension — e.g. a JPEG file saved as .heic',
        needs_review:   'Proposed name uses file modification time (no EXIF date found) — review before applying',
    };

    const filters = [
        { key: 'all', label: `All (${_fnFixes.length})` },
        ...Object.entries(counts).map(([k, n]) => ({ key: k, label: `${reasonLabel(k)} (${n})` })),
        ...(mtimeCount ? [{ key: 'needs_review', label: `⚠️ mtime (${mtimeCount})` }] : []),
    ];

    bar.innerHTML = '';
    filters.forEach(({ key, label }) => {
        const btn = document.createElement('button');
        btn.className = 'btn secondary' + (key === 'all' ? ' active' : '');
        btn.style.cssText = 'padding:0.25rem 0.75rem;font-size:0.8rem;margin:0 0.25rem 0.25rem 0;';
        btn.textContent = label;
        btn.dataset.filter = key;
        btn.title = filterTooltips[key] || '';
        btn.addEventListener('click', () => _toggleFilter(key));
        bar.appendChild(btn);
    });
}

function _toggleFilter(key) {
    if (key === 'all') {
        _fnActiveFilters.clear();
    } else {
        _fnActiveFilters.has(key) ? _fnActiveFilters.delete(key) : _fnActiveFilters.add(key);
    }
    // Update button states
    document.querySelectorAll('#filenames-filter-bar button').forEach(btn => {
        const k = btn.dataset.filter;
        if (k === 'all') {
            btn.classList.toggle('active', _fnActiveFilters.size === 0);
        } else {
            btn.classList.toggle('active', _fnActiveFilters.has(k));
        }
    });
    _applyFilenameFilter();
    // Reset all checkboxes — you can only select what you can see
    document.querySelectorAll('.filename-check').forEach(cb => cb.checked = false);
    document.getElementById('filenames-check-all').checked = false;
    updateFilenameApplyBtn();
}

function _applyFilenameFilter() {
    document.querySelectorAll('#filenames-tbody tr').forEach(tr => {
        if (_fnActiveFilters.size === 0) {
            tr.style.display = '';
            return;
        }
        const reasons = JSON.parse(tr.dataset.reasons || '[]');
        const needsReview = tr.dataset.needsReview === 'true';
        const match = [..._fnActiveFilters].some(f =>
            f === 'needs_review' ? needsReview : reasons.includes(f)
        );
        tr.style.display = match ? '' : 'none';
    });
}

function _renderFilenameRows() {
    const tbody = document.getElementById('filenames-tbody');
    tbody.innerHTML = '';

    _fnFixes.forEach(fix => {
        const tr = document.createElement('tr');
        tr.dataset.reasons = JSON.stringify(fix.reasons);
        tr.dataset.needsReview = fix.needs_review ? 'true' : 'false';
        if (fix.needs_review) tr.style.background = 'rgba(120,53,15,0.15)';

        const reviewBadge = fix.needs_review
            ? ' <span class="status-chip" style="background:#78350f;color:#fde68a;">⚠️ mtime</span>'
            : '';

        const orientBadge = (fix.exif_orientation && fix.exif_orientation !== 1)
            ? ` <span class="status-chip" style="background:#4c1d95;color:#ede9fe;" title="EXIF orientation ${fix.exif_orientation} — photo needs rotation">↻ ${fix.exif_orientation}</span>`
            : '';

        const exifCell = fix.exif_date
            ? `<span style="font-size:0.75rem;color:#94a3b8;">${escHtml(fix.exif_date)}</span>${orientBadge}`
            : `<span style="font-size:0.75rem;color:#475569;">—</span>${orientBadge}`;

        const thumbUrl = `/api/thumbnail/${encodeURIComponent(_fnCurrentSrc)}?filename=${encodeURIComponent(fix.original)}`;

        tr.innerHTML = `
            <td style="width:72px;padding:4px;">
                <img src="${thumbUrl}" loading="lazy"
                     style="width:64px;height:64px;object-fit:cover;border-radius:4px;display:block;"
                     onerror="this.style.opacity='0.2';">
            </td>
            <td><input type="checkbox" class="filename-check"
                data-original="${escHtml(fix.original)}"
                data-reasons='${JSON.stringify(fix.reasons)}'></td>
            <td style="font-family:monospace;font-size:0.8rem;">${escHtml(fix.original)}</td>
            <td class="fn-proposed-cell" data-proposed="${escHtml(fix.proposed)}" style="padding:2px 6px;">
                <span class="fn-proposed-display"
                      style="font-family:monospace;font-size:0.8rem;color:#86efac;">${escHtml(fix.proposed)}</span>
            </td>
            <td>${exifCell}</td>
            <td>${fix.reasons.map(r => `<span class="status-chip">${reasonLabel(r)}</span>`).join(' ')}${reviewBadge}</td>
        `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll('.filename-check').forEach(cb => {
        cb.addEventListener('change', () => {
            const tr = cb.closest('tr');
            const cell = tr.querySelector('.fn-proposed-cell');
            if (cb.checked) {
                const current = cell.dataset.proposed;
                cell.innerHTML = `<input type="text" class="fn-proposed-input"
                    value="${escHtml(current)}"
                    style="font-family:monospace;font-size:0.8rem;color:#e2e8f0;background:#1e293b;border:1px solid #475569;border-radius:4px;padding:2px 6px;width:100%;box-sizing:border-box;">`;
            } else {
                const input = cell.querySelector('.fn-proposed-input');
                const val = (input ? input.value.trim() : '') || cell.dataset.proposed;
                cell.dataset.proposed = val;
                cell.innerHTML = `<span class="fn-proposed-display"
                    style="font-family:monospace;font-size:0.8rem;color:#86efac;">${escHtml(val)}</span>`;
            }
            updateFilenameApplyBtn();
        });
    });
    document.getElementById('filenames-check-all').checked = false;
    updateFilenameApplyBtn();
}

function updateFilenameApplyBtn() {
    const checked = document.querySelectorAll('.filename-check:checked').length;
    const label = checked > 0 ? `Apply ${checked} Rename(s)` : 'Apply Selected Renames';
    ['btn-apply-filenames', 'btn-apply-filenames-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) { btn.disabled = checked === 0; btn.textContent = label; }
    });
}

async function runFilenameApply() {
    const src = toolsSourceId();
    const checked = [...document.querySelectorAll('.filename-check:checked')];
    if (!checked.length) return;
    if (!confirm(`Rename ${checked.length} file(s)? Cloud files will be renamed first.\nEstimated time: ${fmtEta(checked.length)}`)) return;

    const fixes = checked.map(cb => {
        const tr = cb.closest('tr');
        const cell = tr.querySelector('.fn-proposed-cell');
        const input = cell?.querySelector('.fn-proposed-input');
        const proposed = (input ? input.value.trim() : '') || cell?.dataset.proposed || '';
        return { original: cb.dataset.original, proposed, reasons: JSON.parse(cb.dataset.reasons) };
    });

    const total = fixes.length;
    let succeeded = 0;
    const failures = [];

    const setStatus = (msg, color = '#94a3b8') => {
        ['filenames-apply-status', 'filenames-apply-status-top'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = msg; el.style.color = color; }
        });
    };
    const setBtn = (text) => {
        ['btn-apply-filenames', 'btn-apply-filenames-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) { btn.disabled = true; btn.textContent = text; }
        });
    };
    const showCancel = (visible) => {
        ['btn-cancel-filenames', 'btn-cancel-filenames-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.style.display = visible ? '' : 'none';
        });
    };

    _fnAbort = new AbortController();
    setBtn(`Renaming 0 of ${total}…`);
    showCancel(true);
    setStatus('');

    try {
        for (let i = 0; i < fixes.length; i++) {
            if (_fnAbort.signal.aborted) break;
            const fix = fixes[i];
            setBtn(`Renaming ${i + 1} of ${total}…`);
            setStatus(`${fix.original} → ${fix.proposed}`, '#fbbf24');
            try {
                const data = await apiFetch(`/api/tools/${src}/apply/filenames`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fixes: [fix] }),
                    signal: _fnAbort.signal,
                });
                if (data.succeeded?.length) succeeded++;
                else failures.push(...(data.failed?.length ? data.failed : [{ filename: fix.original, error: data.error || 'Unknown error' }]));
            } catch (e) {
                if (e.name === 'AbortError') break;
                failures.push({ filename: fix.original, error: e.message });
            }
        }
        const cancelled = _fnAbort.signal.aborted;
        setStatus(
            cancelled
                ? `⏹ Stopped after ${succeeded} rename(s)${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`
                : `✅ ${succeeded} of ${total} renamed${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`,
            cancelled || failures.length ? '#fbbf24' : '#86efac'
        );
        if (failures.length) console.warn('Rename failures:', failures);
        if (!cancelled) setTimeout(runFilenameScan, 800);
    } finally {
        showCancel(false);
        _fnAbort = null;
        updateFilenameApplyBtn();
    }
}

// ----- Duplicate Finder -----

async function runDupScan() {
    const src = toolsSourceId();
    if (!src) { alert('Select a source first'); return; }
    const btn = document.getElementById('btn-scan-duplicates');
    btn.disabled = true; btn.textContent = 'Scanning…';
    document.getElementById('duplicates-result').style.display = 'none';
    try {
        const data = await apiFetch(`/api/tools/${src}/scan/duplicates`);
        if (!data.ok) throw new Error(data.error || 'Scan failed');
        renderDupResults(src, data);
    } catch (e) {
        alert('Duplicate scan failed: ' + e.message);
    } finally {
        btn.disabled = false; btn.textContent = 'Scan';
    }
}

function renderDupResults(src, data) {
    const groups = data.groups || [];
    const summary = document.getElementById('duplicates-summary');
    const container = document.getElementById('duplicates-groups');
    const resultDiv = document.getElementById('duplicates-result');

    summary.textContent = groups.length === 0
        ? `✅ No exact duplicates found in ${data.total_files_scanned} files.`
        : `Found ${groups.length} duplicate group(s) — ${data.duplicate_count} file(s) can be removed.`;

    container.innerHTML = '';
    groups.forEach((group, idx) => {
        const div = document.createElement('div');
        div.style.cssText = 'border:1px solid #334155;border-radius:6px;padding:1rem;margin-bottom:1rem;';
        const rows = group.files.map(f => `
            <tr>
                <td>
                    <label style="display:flex;align-items:center;gap:0.5rem;">
                        <input type="radio" name="dup_keep_${idx}" class="dup-keep"
                            data-group="${idx}" value="${escHtml(f.filename)}"
                            ${f.filename === group.keep_suggestion ? 'checked' : ''}>
                        <span style="font-size:0.75rem;color:#22c55e;font-weight:600;">KEEP</span>
                    </label>
                </td>
                <td style="font-family:monospace;font-size:0.8rem;">${escHtml(f.filename)}</td>
                <td style="color:#94a3b8;">${fmtBytes(f.size_bytes)}</td>
            </tr>
        `).join('');
        div.innerHTML = `
            <div style="color:#94a3b8;font-size:0.8rem;margin-bottom:0.5rem;">
                Group ${idx + 1} · ${group.files.length} identical files · ${fmtBytes(group.files[0].size_bytes)} each
            </div>
            <table class="sources-table" style="margin:0;">
                <thead><tr><th>Keep?</th><th>Filename</th><th>Size</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
        container.appendChild(div);
    });

    document.querySelectorAll('.dup-keep').forEach(r =>
        r.addEventListener('change', updateDupApplyBtn)
    );
    updateDupApplyBtn();
    resultDiv.style.display = 'block';
}

function updateDupApplyBtn() {
    const groupNames = new Set(
        [...document.querySelectorAll('[name^="dup_keep_"]')].map(r => r.name)
    );
    let toDelete = 0;
    groupNames.forEach(name => {
        toDelete += document.querySelectorAll(`[name="${name}"]`).length - 1;
    });
    const label = toDelete > 0 ? `Delete ${toDelete} Duplicate(s)` : 'Delete Duplicates';
    ['btn-apply-duplicates', 'btn-apply-duplicates-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) { btn.disabled = groupNames.size === 0; btn.textContent = label; }
    });
}

async function runDupApply() {
    const src = toolsSourceId();
    const groupNames = new Set(
        [...document.querySelectorAll('[name^="dup_keep_"]')].map(r => r.name)
    );

    const toDelete = [];
    groupNames.forEach(name => {
        const radios = [...document.querySelectorAll(`[name="${name}"]`)];
        const kept = radios.find(r => r.checked)?.value;
        radios.forEach(r => { if (r.value !== kept) toDelete.push(r.value); });
    });

    if (!toDelete.length) return;
    if (!confirm(`Delete ${toDelete.length} duplicate file(s)? This cannot be undone.\nEstimated time: ${fmtEta(toDelete.length)}`)) return;

    const total = toDelete.length;
    let succeeded = 0;
    const failures = [];

    const setStatus = (msg, color = '#94a3b8') => {
        ['duplicates-apply-status', 'duplicates-apply-status-top'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = msg; el.style.color = color; }
        });
    };
    const setBtn = (text) => {
        ['btn-apply-duplicates', 'btn-apply-duplicates-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) { btn.disabled = true; btn.textContent = text; }
        });
    };
    const showCancel = (visible) => {
        ['btn-cancel-duplicates', 'btn-cancel-duplicates-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.style.display = visible ? '' : 'none';
        });
    };

    _dupAbort = new AbortController();
    setBtn(`Deleting 0 of ${total}…`);
    showCancel(true);
    setStatus('');

    try {
        for (let i = 0; i < toDelete.length; i++) {
            if (_dupAbort.signal.aborted) break;
            const filename = toDelete[i];
            setBtn(`Deleting ${i + 1} of ${total}…`);
            setStatus(filename, '#fbbf24');
            try {
                const data = await apiFetch(`/api/tools/${src}/apply/duplicates`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ to_delete: [filename] }),
                    signal: _dupAbort.signal,
                });
                if (data.succeeded?.length) succeeded++;
                else failures.push(...(data.failed?.length ? data.failed : [{ filename, error: data.error || 'Unknown error' }]));
            } catch (e) {
                if (e.name === 'AbortError') break;
                failures.push({ filename, error: e.message });
            }
        }
        const cancelled = _dupAbort.signal.aborted;
        setStatus(
            cancelled
                ? `⏹ Stopped after ${succeeded} deletion(s)${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`
                : `✅ ${succeeded} of ${total} deleted${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`,
            cancelled || failures.length ? '#fbbf24' : '#86efac'
        );
        if (failures.length) console.warn('Delete failures:', failures);
        if (!cancelled) setTimeout(runDupScan, 800);
    } finally {
        showCancel(false);
        _dupAbort = null;
        updateDupApplyBtn();
    }
}

// ----- Video Manager -----

async function runVideoScan() {
    const src = toolsSourceId();
    if (!src) { alert('Select a source first'); return; }
    const btn = document.getElementById('btn-scan-videos');
    btn.disabled = true; btn.textContent = 'Scanning…';
    document.getElementById('videos-result').style.display = 'none';
    try {
        const data = await apiFetch(`/api/tools/${src}/scan/videos`);
        if (!data.ok) throw new Error(data.error || 'Scan failed');
        renderVideoResults(src, data);
    } catch (e) {
        alert('Video scan failed: ' + e.message);
    } finally {
        btn.disabled = false; btn.textContent = 'Scan';
    }
}

function renderVideoResults(src, data) {
    const videos = data.videos || [];
    const summary = document.getElementById('videos-summary');
    const tbody = document.getElementById('videos-tbody');
    const resultDiv = document.getElementById('videos-result');

    summary.textContent = videos.length === 0
        ? '✅ No video files found in this source.'
        : `Found ${videos.length} video file(s) · ${fmtBytes(data.total_size_bytes)} total.`;

    tbody.innerHTML = '';
    videos.forEach(v => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input type="checkbox" class="video-check" value="${escHtml(v.filename)}" checked></td>
            <td style="font-family:monospace;font-size:0.8rem;">${escHtml(v.filename)}</td>
            <td style="color:#94a3b8;">${fmtBytes(v.size_bytes)}</td>
        `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll('.video-check').forEach(cb =>
        cb.addEventListener('change', updateVideoApplyBtn)
    );
    document.getElementById('videos-check-all').checked = videos.length > 0;
    updateVideoApplyBtn();
    resultDiv.style.display = 'block';
}

function updateVideoApplyBtn() {
    const checked = document.querySelectorAll('.video-check:checked').length;
    const label = checked > 0 ? `Delete ${checked} Video(s)` : 'Delete Selected Videos';
    ['btn-apply-videos', 'btn-apply-videos-top'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) { btn.disabled = checked === 0; btn.textContent = label; }
    });
}

async function runVideoApply() {
    const src = toolsSourceId();
    const toDelete = [...document.querySelectorAll('.video-check:checked')].map(cb => cb.value);
    if (!toDelete.length) return;
    if (!confirm(`Delete ${toDelete.length} video file(s)? This cannot be undone.\nEstimated time: ${fmtEta(toDelete.length)}`)) return;

    const total = toDelete.length;
    let succeeded = 0;
    const failures = [];

    const setStatus = (msg, color = '#94a3b8') => {
        ['videos-apply-status', 'videos-apply-status-top'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = msg; el.style.color = color; }
        });
    };
    const setBtn = (text) => {
        ['btn-apply-videos', 'btn-apply-videos-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) { btn.disabled = true; btn.textContent = text; }
        });
    };
    const showCancel = (visible) => {
        ['btn-cancel-videos', 'btn-cancel-videos-top'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.style.display = visible ? '' : 'none';
        });
    };

    _vidAbort = new AbortController();
    setBtn(`Deleting 0 of ${total}…`);
    showCancel(true);
    setStatus('');

    try {
        for (let i = 0; i < toDelete.length; i++) {
            if (_vidAbort.signal.aborted) break;
            const filename = toDelete[i];
            setBtn(`Deleting ${i + 1} of ${total}…`);
            setStatus(filename, '#fbbf24');
            try {
                const data = await apiFetch(`/api/tools/${src}/apply/videos`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ to_delete: [filename] }),
                    signal: _vidAbort.signal,
                });
                if (data.succeeded?.length) succeeded++;
                else failures.push(...(data.failed?.length ? data.failed : [{ filename, error: data.error || 'Unknown error' }]));
            } catch (e) {
                if (e.name === 'AbortError') break;
                failures.push({ filename, error: e.message });
            }
        }
        const cancelled = _vidAbort.signal.aborted;
        setStatus(
            cancelled
                ? `⏹ Stopped after ${succeeded} deletion(s)${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`
                : `✅ ${succeeded} of ${total} deleted${failures.length ? ` · ⚠️ ${failures.length} failed` : ''}`,
            cancelled || failures.length ? '#fbbf24' : '#86efac'
        );
        if (failures.length) console.warn('Video delete failures:', failures);
        if (!cancelled) setTimeout(runVideoScan, 800);
    } finally {
        showCancel(false);
        _vidAbort = null;
        updateVideoApplyBtn();
    }
}

// ----- Rename File (browser + batch) -----

async function runRenameScan() {
    const srcId = toolsSourceId();
    if (!srcId) { alert('Select a source first.'); return; }
    const btn = document.getElementById('btn-scan-rename');
    const scanStatus = document.getElementById('rename-scan-status');
    const resultEl = document.getElementById('rename-result');
    btn.disabled = true;
    btn.textContent = 'Scanning…';
    scanStatus.textContent = 'Reading files and EXIF data — may take a moment…';
    scanStatus.style.color = '#94a3b8';
    resultEl.style.display = 'none';
    try {
        const data = await apiFetch(`/api/tools/${srcId}/scan/files`);
        if (!data.ok) throw new Error(data.error || 'Scan failed');
        const files = data.files || [];
        document.getElementById('rename-summary').textContent =
            `${files.length} file${files.length === 1 ? '' : 's'} — edit the New Filename column, then Apply`;
        const tbody = document.getElementById('rename-tbody');
        tbody.innerHTML = '';
        files.forEach(f => {
            const tr = document.createElement('tr');
            const thumbSrc = `/api/thumbnail/${srcId}?filename=${encodeURIComponent(f.filename)}`;
            const exifCell = f.exif_date
                ? `<span style="font-size:0.8rem;">${escHtml(f.exif_date)}</span>`
                : `<span style="color:#64748b;font-size:0.8rem;">—</span>`;
            tr.innerHTML = `
                <td><img src="${thumbSrc}" style="width:64px;height:64px;object-fit:cover;border-radius:4px;"
                    loading="lazy" onerror="this.style.display='none'"></td>
                <td style="font-family:monospace;font-size:0.85rem;">${escHtml(f.filename)}</td>
                <td>${exifCell}</td>
                <td><input type="text" class="form-input rename-new-name"
                    data-original="${escHtml(f.filename)}"
                    value="${escHtml(f.filename)}"
                    style="width:100%;min-width:200px;font-family:monospace;font-size:0.85rem;"
                    spellcheck="false"></td>`;
            tbody.appendChild(tr);
        });
        tbody.querySelectorAll('.rename-new-name').forEach(inp => {
            inp.addEventListener('input', updateRenameApplyBtn);
        });
        scanStatus.textContent = '';
        resultEl.style.display = 'block';
        updateRenameApplyBtn();
    } catch (e) {
        scanStatus.textContent = '❌ ' + e.message;
        scanStatus.style.color = '#f87171';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan';
    }
}

function getRenameChanges() {
    const changes = [];
    document.querySelectorAll('#rename-tbody .rename-new-name').forEach(inp => {
        const original = inp.dataset.original;
        const proposed = inp.value.trim();
        if (proposed && proposed !== original) {
            changes.push({ original, proposed, reasons: [] });
        }
    });
    return changes;
}

function updateRenameApplyBtn() {
    const changed = getRenameChanges().length > 0;
    ['btn-apply-rename', 'btn-apply-rename-top'].forEach(id => {
        const b = document.getElementById(id);
        if (b) b.disabled = !changed;
    });
}

async function runRenameApply() {
    const srcId = toolsSourceId();
    const fixes = getRenameChanges();
    if (!fixes.length) return;
    const topBtn = document.getElementById('btn-apply-rename-top');
    const botBtn = document.getElementById('btn-apply-rename');
    const topStatus = document.getElementById('rename-apply-status-top');
    const botStatus = document.getElementById('rename-apply-status');
    [topBtn, botBtn].forEach(b => { if (b) b.disabled = true; });
    const msg = `Renaming ${fixes.length} file${fixes.length === 1 ? '' : 's'}…`;
    topStatus.textContent = botStatus.textContent = msg;
    topStatus.style.color = botStatus.style.color = '#94a3b8';
    try {
        const data = await apiFetch(`/api/tools/${srcId}/apply/filenames`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fixes }),
        });
        const succeeded = data.succeeded?.length ?? 0;
        const failed = data.failed?.length ?? 0;
        const result = failed
            ? `✅ ${succeeded} renamed, ❌ ${failed} failed`
            : `✅ ${succeeded} file${succeeded === 1 ? '' : 's'} renamed`;
        topStatus.textContent = botStatus.textContent = result;
        topStatus.style.color = botStatus.style.color = failed ? '#f87171' : '#4ade80';
        if (succeeded) await runRenameScan();
    } catch (e) {
        topStatus.textContent = botStatus.textContent = '❌ ' + e.message;
        topStatus.style.color = botStatus.style.color = '#f87171';
        [topBtn, botBtn].forEach(b => { if (b) b.disabled = false; });
    }
}

// Helper used throughout tools JS
function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function apiFetch(url, opts = {}) {
    const resp = await fetch(url, opts);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}
