// Shared voice navigation and logout handlers
(function () {
    window.VoiceNav = {
        _inited: false,
        // Starts an always-on local SpeechRecognition on pages that don't have
        // assistant.js (signup, pin_reveal, etc.) so voice nav can still work.
        _startLocalRecognition() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) return;
            const r = new SR();
            r.continuous = true;
            r.interimResults = true;
            r.lang = 'en-US';
            r.onresult = (event) => {
                const result = event.results[event.results.length - 1];
                if (!result.isFinal) return;
                const transcript = result[0].transcript.trim();
                if (transcript) {
                    window.dispatchEvent(new CustomEvent('feed-update', {
                        detail: { text: '[User]: ' + transcript, time: '' }
                    }));
                }
            };
            r.onend = () => { try { r.start(); } catch (e) { } };
            try { r.start(); } catch (e) { }
        },
        init(page) {
            if (this._inited) return;
            this._inited = true;
            // On pages without assistant.js AND without their own recognition
            // (signup, pin_reveal), start our own so nav commands can be heard.
            // login.js runs its own recognition — skip it there to avoid conflicts.
            if (typeof sendChat === 'undefined' && page !== 'login') {
                this._startLocalRecognition();
            }
            window.addEventListener('feed-update', (e) => {
                const text = (e.detail && e.detail.text) ? e.detail.text : '';
                if (!/^\[user\]/i.test(text)) return;
                const spoken = text.replace(/^\[user\]:\s*/i, '').toLowerCase();

                // Cancel / back
                if (/\b(cancel|go back|return)\b/.test(spoken)) {
                    if (typeof handleCancel === 'function') handleCancel(new Event('click'));
                    return;
                }

                // Logout
                if (/\b(log ?out|sign out|sign ?me out|log ?me out|logout)\b/.test(spoken)) {
                    try {
                        // Prefer the POST voice-logout endpoint; fallback to GET /logout if unavailable
                        fetch('/voice-logout', { method: 'POST', headers: { 'Content-Type': 'application/json' } }).catch(() => {
                            try { fetch('/logout'); } catch (e) { }
                        });
                    } catch (e) { }
                    window.location.href = '/';
                    return;
                }

                // Generic navigation match
                const navMatch = spoken.match(/\b(go to|open|take me to|show me)\b\s*(the )?([a-z0-9 \-]+)\b/);
                if (navMatch) {
                    const target = navMatch[3].trim();
                    this.navigate(page, target);
                }
            });
        },

        navigate(page, target) {
            if (!target) return;
            const t = target.toLowerCase();

            // Page-specific handlers (prefer in-page functions when available)
            if (page === 'admin') {
                if (/\b(users?)\b/.test(t) && typeof showPanel === 'function') { showPanel('users', document.querySelectorAll('.nav-item')[1]); return; }
                if (/\b(activity|logs?)\b/.test(t) && typeof showPanel === 'function') { showPanel('activity', document.querySelectorAll('.nav-item')[2]); return; }
                if (/\b(api|usage)\b/.test(t) && typeof showPanel === 'function') { showPanel('api', document.querySelectorAll('.nav-item')[3]); return; }
                if (/\b(errors?)\b/.test(t) && typeof showPanel === 'function') { showPanel('errors', document.querySelectorAll('.nav-item')[4]); return; }
                if (/\b(status)\b/.test(t) && typeof showPanel === 'function') { showPanel('status', document.querySelectorAll('.nav-item')[0]); return; }
            }

            if (page === 'dashboard') {
                if (/\b(inbox|messages|mail)\b/.test(t) && typeof showPage === 'function') { showPage('inbox'); return; }
                if (/\b(tasks?)\b/.test(t) && typeof showPage === 'function') { showPage('tasks'); return; }
                if (/\b(dashboard|home)\b/.test(t) && typeof showPage === 'function') { showPage('dashboard'); return; }
            }

            if (page === 'signup') {
                if (/\b(login|sign in|home)\b/.test(t)) { window.location.href = '/'; return; }
                if (/\b(signup|sign up|create account)\b/.test(t)) { window.location.href = '/signup'; return; }
                if (/\b(pin|pin reveal|reveal)\b/.test(t)) { window.location.href = '/pin-reveal'; return; }
            }

            if (page === 'login') {
                if (/\b(sign ?up|create account|register)\b/.test(t)) { window.location.href = '/signup'; return; }
            }

            if (page === 'pin_reveal') {
                if (/\b(login|sign in)\b/.test(t)) { window.location.href = '/'; return; }
                if (/\b(dashboard)\b/.test(t)) { window.location.href = '/dashboard'; return; }
            }

            // Common fallbacks
            if (/\b(settings|profile)\b/.test(t)) { window.location.href = '/dashboard'; return; }
            if (/\b(admin)\b/.test(t)) { window.location.href = '/admin'; return; }

            // Final fallback: pathify the phrase
            try { window.location.href = '/' + t.replace(/\s+/g, '-'); } catch (e) { }
        }
    };
})();
