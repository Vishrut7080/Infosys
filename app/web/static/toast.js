// ─────────────────────────────────────────────────────────────
//  toast.js  —  VoiceMail AI
//  Global Toast.show(message, type, duration) utility.
//  Types: 'info' | 'success' | 'warning' | 'error'
// ─────────────────────────────────────────────────────────────

const Toast = (() => {
    let container = null;

    const ICONS = {
        success: '✓',
        error: '✕',
        warning: '!',
        info: 'i',
    };

    function ensureContainer() {
        if (!container || !document.body.contains(container)) {
            container = document.createElement('div');
            container.id = 'toast-container';
            // Respect page preference for bottom placement if requested by pages like login
            try {
                if (document && document.body && document.body.dataset && document.body.dataset.toastPosition === 'bottom') {
                    container.classList.add('position-bottom');
                }
            } catch (e) { }
            document.body.appendChild(container);
        } else {
            // If container exists but page requests bottom placement, ensure class is present
            try {
                if (document && document.body && document.body.dataset && document.body.dataset.toastPosition === 'bottom') {
                    container.classList.add('position-bottom');
                }
            } catch (e) { }
        }
        return container;
    }

    function dismiss(el) {
        if (!el || el.classList.contains('toast-out')) return;
        el.classList.add('toast-out');
        // Remove after animation; fallback timeout guards reduced-motion / no-animation cases
        el.addEventListener('animationend', () => el.remove(), { once: true });
        setTimeout(() => { if (el.parentNode) el.remove(); }, 350);
    }

    /**
     * @param {string} message  - Display text
     * @param {'info'|'success'|'warning'|'error'} type
     * @param {number} duration - Auto-dismiss delay in ms (default 3500)
     * @param {object} options  - Extra options like { link: { url: '', text: '' } }
     */
    function show(message, type = 'info', duration = 3500, options = {}) {
        const c = ensureContainer();

        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.style.setProperty('--toast-duration', `${duration}ms`);

        const icon = document.createElement('span');
        icon.className = 'toast-icon';
        icon.textContent = ICONS[type] ?? 'i';

        const msg = document.createElement('span');
        msg.className = 'toast-msg';
        msg.textContent = message;

        if (options.link) {
            const a = document.createElement('a');
            a.href = options.link.url;
            a.textContent = options.link.text || 'View';
            a.className = 'toast-link';
            a.style.marginLeft = '8px';
            a.style.color = 'inherit';
            a.style.textDecoration = 'underline';
            a.style.fontWeight = '600';
            a.onclick = (e) => e.stopPropagation();
            msg.appendChild(a);
        }

        const progress = document.createElement('div');
        progress.className = 'toast-progress';

        el.appendChild(icon);
        el.appendChild(msg);
        el.appendChild(progress);
        c.appendChild(el);

        const timer = setTimeout(() => dismiss(el), duration);
        el.addEventListener('click', () => { clearTimeout(timer); dismiss(el); });

        return el;
    }

    return { show, dismiss };
})();
