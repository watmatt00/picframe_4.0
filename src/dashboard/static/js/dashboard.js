/**
 * PicFrame 4.0 Dashboard JavaScript
 */

// Update current time in footer
function updateTime() {
    const el = document.getElementById('current-time');
    if (el) {
        el.textContent = new Date().toLocaleString();
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    updateTime();
    setInterval(updateTime, 1000);
});

// API helper
async function api(endpoint, options = {}) {
    const response = await fetch(endpoint, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
