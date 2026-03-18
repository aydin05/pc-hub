/* === Toast Notifications === */
const Toast = {
    container: null,
    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },
    show(message, type = 'info', duration = 4000) {
        this.init();
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = {
            success: '&#10003;',
            error: '&#10007;',
            warning: '&#9888;',
            info: '&#8505;'
        };
        toast.innerHTML = `<span>${icons[type] || ''}</span><span>${message}</span>`;
        toast.addEventListener('click', () => toast.remove());
        this.container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 6000); },
    warning(msg) { this.show(msg, 'warning'); },
    info(msg) { this.show(msg, 'info'); }
};

/* === Modal === */
const Modal = {
    show(title, body, onConfirm, confirmText = 'Confirm', confirmClass = 'btn-danger') {
        const existing = document.querySelector('.modal-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal">
                <div class="modal-title">${title}</div>
                <div class="modal-body">${body}</div>
                <div class="modal-actions">
                    <button class="btn btn-outline modal-cancel">Cancel</button>
                    <button class="btn ${confirmClass} modal-confirm">${confirmText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('active'));

        overlay.querySelector('.modal-cancel').addEventListener('click', () => {
            overlay.classList.remove('active');
            setTimeout(() => overlay.remove(), 200);
        });

        overlay.querySelector('.modal-confirm').addEventListener('click', () => {
            overlay.classList.remove('active');
            setTimeout(() => overlay.remove(), 200);
            if (onConfirm) onConfirm();
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('active');
                setTimeout(() => overlay.remove(), 200);
            }
        });
    }
};

/* === API Helper === */
async function api(url, options = {}) {
    const defaults = {
        headers: { 'Content-Type': 'application/json' },
    };
    if (options.body && typeof options.body === 'object') {
        options.body = JSON.stringify(options.body);
    }
    const response = await fetch(url, { ...defaults, ...options });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data;
}

/* === SSE Helper === */
function streamSSE(url, { onMessage, onDone, onError }) {
    const source = new EventSource(url);
    source.onmessage = (event) => {
        const data = event.data;
        if (data.includes('[DONE]') || data.includes('"type":"done"') || data.includes("'type':'done'")) {
            if (onDone) onDone(data);
            source.close();
            return;
        }
        if (onMessage) onMessage(data);
    };
    source.onerror = () => {
        source.close();
        if (onError) onError();
    };
    return source;
}

/* === Terminal Output Helper === */
function appendTerminal(terminalEl, line) {
    if (!terminalEl) return;
    let cls = '';
    if (line.includes('[ERROR]') || line.includes('[FAIL]')) cls = 'line-error';
    else if (line.includes('[SUCCESS]') || line.includes('[DONE]')) cls = 'line-success';
    else if (line.includes('[INFO]') || line.includes('[RESTARTING]')) cls = 'line-info';

    if (cls) {
        terminalEl.innerHTML += `<span class="${cls}">${escapeHtml(line)}</span>\n`;
    } else {
        terminalEl.textContent += line + '\n';
    }
    terminalEl.scrollTop = terminalEl.scrollHeight;
}

/* === Utility === */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function $(selector) { return document.querySelector(selector); }
function $$(selector) { return document.querySelectorAll(selector); }

/* === Sidebar === */
document.addEventListener('DOMContentLoaded', () => {
    const hamburger = document.querySelector('.hamburger');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');

    if (hamburger) {
        hamburger.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('active');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
        });
    }

    // Highlight active nav link
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href !== '/dashboard' && path.startsWith(href))) {
            link.classList.add('active');
        }
    });
});

/* === Sidebar Quick Actions === */
function sidebarRestartChrome() {
    Modal.show('Restart Chrome',
        'Are you sure you want to <strong>restart Chrome</strong>?',
        () => {
            api('/kiosk/api/restart', { method: 'POST' }).then(() => {
                Toast.success('Chrome is restarting...');
            }).catch(err => Toast.error(err.message));
        },
        'Restart', 'btn-warning'
    );
}

function sidebarReboot() {
    Modal.show('Reboot Kiosk',
        'Are you sure you want to <strong>reboot</strong> the kiosk? All active sessions will be terminated.',
        () => {
            api('/system/api/reboot', { method: 'POST', body: { confirm: true } }).then(() => {
                Toast.info('Kiosk is rebooting...');
            }).catch(err => Toast.error(err.message));
        },
        'Reboot', 'btn-warning'
    );
}

function sidebarShutdown() {
    Modal.show('Shutdown Kiosk',
        'Are you sure you want to <strong>shut down</strong> the kiosk? This will power off the machine.',
        () => {
            api('/system/api/shutdown', { method: 'POST', body: { confirm: true } }).then(() => {
                Toast.info('Kiosk is shutting down...');
            }).catch(err => Toast.error(err.message));
        },
        'Shutdown', 'btn-danger'
    );
}

/* === Cursor / Touchscreen Mode Shortcuts (W = cursor, Q = touchscreen) === */
document.addEventListener('keydown', function(e) {
    const tag = document.activeElement.tagName;
    const isTyping = (tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement.isContentEditable);

    if (e.key === 'w' || e.key === 'W') {
        if (isTyping) return;
        e.preventDefault();
        fetch('/kiosk/api/cursor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show: true })
        }).catch(() => {});
        Toast.success('Cursor Mode — cursor visible');
        return;
    }
    if (e.key === 'q' || e.key === 'Q') {
        if (isTyping) return;
        e.preventDefault();
        fetch('/kiosk/api/cursor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show: false })
        }).catch(() => {});
        Toast.info('Touchscreen Mode — cursor hidden');
        return;
    }
});

/* === Live Clock === */
function startClock(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    function update() {
        el.textContent = new Date().toLocaleString();
    }
    update();
    setInterval(update, 1000);
}
