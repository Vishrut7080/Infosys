// ── Language Manager ─────────────────────────────────────────
// Handles EN/HI switching across all pages.
// Persists choice in localStorage.
// Responds to voice commands via /api/feed polling.
// ─────────────────────────────────────────────────────────────

const LangManager = {
    current: localStorage.getItem('va_lang') || 'en',

    toggle() {
        this.current = this.current === 'en' ? 'hi' : 'en';
        localStorage.setItem('va_lang', this.current);
        this.applyToPage();
        document.dispatchEvent(new CustomEvent('langChanged', { detail: { lang: this.current } }));
    },

    set(lang) {
        if (this.current === lang) return;
        this.current = lang;
        localStorage.setItem('va_lang', lang);
        this.applyToPage();
        document.dispatchEvent(new CustomEvent('langChanged', { detail: { lang } }));
    },

    isHindi() { return this.current === 'hi'; },

    // Translate an array of strings via Flask /translate endpoint
    async translate(texts) {
        if (this.current === 'en') return texts;
        try {
            const res = await fetch('/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ texts, target: 'hi' })
            });
            const data = await res.json();
            return data.translated || texts;
        } catch (e) { return texts; }
    },

    // Apply translations to all data-en/data-hi elements and update button label
    applyToPage() {
        // Update toggle button label
        const btn = document.getElementById('langToggleBtn');
        if (btn) btn.textContent = this.current === 'en' ? '🇮🇳 हिंदी' : '🇬🇧 English';

        // Static text elements
        document.querySelectorAll('[data-en]').forEach(el => {
            if (this.current === 'hi' && el.dataset.hi) {
                el.textContent = el.dataset.hi;
            } else if (el.dataset.en) {
                el.textContent = el.dataset.en;
            }
        });

        // Input placeholders
        document.querySelectorAll('[data-placeholder-en]').forEach(el => {
            if (this.current === 'hi' && el.dataset.placeholderHi) {
                el.placeholder = el.dataset.placeholderHi;
            } else if (el.dataset.placeholderEn) {
                el.placeholder = el.dataset.placeholderEn;
            }
        });
    }
};

// Apply on page load
document.addEventListener('DOMContentLoaded', () => {
    LangManager.applyToPage();
});

// ── Voice command listener ────────────────────────────────────
// Polls /api/feed every 2s. If "hindi mode" or "english mode"
// detected, switches language automatically.
let _langFeedIndex = 0;
setInterval(async () => {
    try {
        const res = await fetch(`/api/feed?since=${_langFeedIndex}`);
        const data = await res.json();
        if (data.entries && data.entries.length > 0) {
            _langFeedIndex = data.next_index;
            const last = data.entries[data.entries.length - 1];
            if (!last) return;
            const text = last.text.toLowerCase();
            if (text.includes('hindi mode') || text.includes('हिंदी मोड')) {
                LangManager.set('hi');
            } else if (text.includes('english mode') || text.includes('switch to english')) {
                LangManager.set('en');
            }
        }
    } catch (e) { }
}, 2000);