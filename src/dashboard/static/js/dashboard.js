/**
 * PicFrame 4.0 Dashboard JavaScript
 * Based on v3 dashboard functionality
 */

document.addEventListener('DOMContentLoaded', () => {
    initTabSwitching();
    initAdvancedToggles();
    initStatusDashboard();
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
            const severity = syncStatus === "syncing" ? "SYNCING" :
                            syncStatus === "match" ? "OK" :
                            syncStatus === "error" ? "ERROR" : "UNKNOWN";

            if (overallTitle) {
                overallTitle.textContent = syncStatus === "syncing" ? "Syncing photos..." :
                                           syncStatus === "match" ? "Photos in sync" :
                                           syncStatus === "error" ? "Sync error" : "Checking status...";
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
