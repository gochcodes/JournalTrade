/**
 * Journal Trade - wspólna logika interfejsu
 */

const MONTHS_PL = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
    'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];
const DAYS_PL = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Ndz'];

/* ==================== FORMATOWANIE ==================== */
const JT = {
    fmt(v, digits = 2) {
        const n = Number(v) || 0;
        return n.toLocaleString('pl-PL', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    },
    fmtPL(v) {
        const n = Number(v) || 0;
        return (n > 0 ? '+' : '') + JT.fmt(n);
    },
    plClass(v) {
        const n = Number(v) || 0;
        return n > 0 ? 'positive' : (n < 0 ? 'negative' : 'neutral');
    },
    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    },
    localISO(d) {
        const z = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
    },
    fmtDate(iso) {
        if (!iso) return '—';
        const [y, m, d] = iso.split('-');
        return `${d}.${m}.${y}`;
    },
    tradesWord(n) {
        if (n === 1) return 'trade';
        const l = n % 10, h = n % 100;
        if (l >= 2 && l <= 4 && (h < 12 || h > 14)) return 'trade’y';
        return 'trade’ów';
    },

    /* ---------- Animowany licznik ---------- */
    countUp(el, target, { duration = 1000, decimals = 2, prefixSign = false, suffix = '' } = {}) {
        if (!el) return;
        const end = Number(target) || 0;
        const start = performance.now();
        const step = now => {
            const p = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - p, 3);
            const val = end * eased;
            const sign = prefixSign && val > 0 ? '+' : '';
            el.textContent = sign + JT.fmt(val, decimals) + suffix;
            if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    },

    /* ---------- Toasty ---------- */
    toast(message, type = 'info', timeout = 4000) {
        let c = document.querySelector('.toast-container');
        if (!c) {
            c = document.createElement('div');
            c.className = 'toast-container';
            document.body.appendChild(c);
        }
        const icons = { success: '✅', error: '⛔', info: 'ℹ️' };
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.innerHTML = `<span>${icons[type] || ''}</span><span>${JT.esc(message)}</span>`;
        const remove = () => {
            if (t.classList.contains('removing')) return;
            t.classList.add('removing');
            setTimeout(() => t.remove(), 300);
        };
        t.addEventListener('click', remove);
        c.appendChild(t);
        setTimeout(remove, timeout);
    },

    /* ---------- Wspólne opcje Chart.js ---------- */
    chartDefaults() {
        if (!window.Chart) return;
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
        Chart.defaults.borderColor = 'rgba(30, 41, 59, 0.8)';
        Chart.defaults.animation.duration = 1200;
        Chart.defaults.animation.easing = 'easeOutQuart';
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
        Chart.defaults.plugins.tooltip.backgroundColor = '#1a1f35';
        Chart.defaults.plugins.tooltip.borderColor = '#334155';
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.padding = 12;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
    },

    gradient(ctx, color) {
        const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.clientHeight || 300);
        g.addColorStop(0, color.replace('1)', '0.35)'));
        g.addColorStop(1, color.replace('1)', '0)'));
        return g;
    },
};

/* ==================== SIDEBAR ==================== */
function initSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const toggle = document.getElementById('sidebar-toggle');
    const overlay = document.querySelector('.sidebar-overlay');
    const mobileBtn = document.querySelector('.mobile-menu-btn');

    if (localStorage.getItem('jt-sidebar') === 'collapsed') sidebar.classList.add('collapsed');

    toggle?.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('jt-sidebar', sidebar.classList.contains('collapsed') ? 'collapsed' : 'open');
        setTimeout(() => window.dispatchEvent(new Event('resize')), 360);
    });
    mobileBtn?.addEventListener('click', () => {
        sidebar.classList.add('mobile-open');
        overlay?.classList.add('active');
    });
    overlay?.addEventListener('click', () => {
        sidebar.classList.remove('mobile-open');
        overlay.classList.remove('active');
    });
}

/* ==================== PŁYNNE PRZEJŚCIA STRON ==================== */
function initPageTransitions() {
    document.addEventListener('click', e => {
        const a = e.target.closest('a[href]');
        if (!a || a.target === '_blank' || a.hasAttribute('download') || e.ctrlKey || e.metaKey) return;
        const href = a.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript') || href.includes('/api/')) return;
        if (a.origin !== location.origin) return;
        e.preventDefault();
        const page = document.querySelector('.page-container');
        if (page) {
            page.style.transition = 'opacity .18s ease, transform .18s ease';
            page.style.opacity = '0';
            page.style.transform = 'translateY(8px)';
        }
        setTimeout(() => { location.href = href; }, 170);
    });
    // przy powrocie "wstecz" z bfcache
    window.addEventListener('pageshow', ev => {
        if (ev.persisted) {
            const page = document.querySelector('.page-container');
            if (page) { page.style.opacity = '1'; page.style.transform = 'none'; }
        }
    });
}

/* ==================== MODAL ZDJĘĆ ==================== */
function openImageModal(src) {
    const modal = document.getElementById('image-modal');
    if (!modal) return;
    modal.querySelector('img').src = src;
    modal.classList.add('active');
}
function closeImageModal() {
    document.getElementById('image-modal')?.classList.remove('active');
}

/* ==================== POTWIERDZENIE USUNIĘCIA ==================== */
let deleteFormToSubmit = null;
function confirmDelete(formId) {
    deleteFormToSubmit = document.getElementById(formId);
    document.getElementById('confirm-dialog')?.classList.add('active');
}
function cancelDelete() {
    deleteFormToSubmit = null;
    document.getElementById('confirm-dialog')?.classList.remove('active');
}
function executeDelete() {
    if (deleteFormToSubmit) deleteFormToSubmit.submit();
}

/* ==================== PODGLĄD PLIKU ==================== */
function previewFile(input) {
    const preview = document.getElementById('file-preview');
    if (!preview || !input.files || !input.files[0]) return;
    const reader = new FileReader();
    reader.onload = e => {
        preview.innerHTML = `<img src="${e.target.result}" alt="Podgląd" style="animation: scaleIn .3s ease">`;
    };
    reader.readAsDataURL(input.files[0]);
}

/* Wklejanie screena ze schowka (Ctrl+V) na formularzu */
function initPasteScreenshot() {
    const input = document.querySelector('input[name="screenshot"]');
    if (!input) return;
    document.addEventListener('paste', e => {
        const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith('image/'));
        if (!item) return;
        const file = item.getAsFile();
        const dt = new DataTransfer();
        dt.items.add(new File([file], `screenshot_${Date.now()}.png`, { type: file.type }));
        input.files = dt.files;
        previewFile(input);
        JT.toast('Wklejono screenshot ze schowka', 'success', 2500);
    });
}

/* ==================== TAGI ==================== */
function initTagsInput() {
    const wrap = document.querySelector('.tags-input-wrapper');
    if (!wrap) return;
    const hidden = document.getElementById('tagi');
    const input = wrap.querySelector('input');
    const sugBox = document.querySelector('.tag-suggestions');
    const all = JSON.parse(wrap.dataset.all || '[]');
    let tags = (hidden.value || '').split(',').map(t => t.trim()).filter(Boolean);

    const render = () => {
        wrap.querySelectorAll('.tag').forEach(t => t.remove());
        tags.forEach((t, i) => {
            const el = document.createElement('span');
            el.className = 'tag';
            el.innerHTML = `${JT.esc(t)} <span class="tag-remove" data-i="${i}">✕</span>`;
            wrap.insertBefore(el, input);
        });
        hidden.value = tags.join(', ');
    };
    const add = v => {
        v = v.trim().replace(/,/g, '');
        if (v && !tags.some(t => t.toLowerCase() === v.toLowerCase())) tags.push(v);
        input.value = '';
        sugBox?.classList.remove('active');
        render();
    };
    const showSug = () => {
        if (!sugBox) return;
        const q = input.value.trim().toLowerCase();
        const list = all.filter(t => !tags.includes(t) && (!q || t.toLowerCase().includes(q))).slice(0, 8);
        sugBox.innerHTML = list.map(t => `<div class="tag-suggestion">${JT.esc(t)}</div>`).join('');
        sugBox.classList.toggle('active', list.length > 0 && document.activeElement === input);
    };

    wrap.addEventListener('click', e => {
        if (e.target.classList.contains('tag-remove')) {
            tags.splice(Number(e.target.dataset.i), 1);
            render();
        }
        input.focus();
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(input.value); }
        else if (e.key === 'Backspace' && !input.value && tags.length) { tags.pop(); render(); }
    });
    input.addEventListener('input', showSug);
    input.addEventListener('focus', showSug);
    input.addEventListener('blur', () => setTimeout(() => {
        if (input.value.trim()) add(input.value);
        sugBox?.classList.remove('active');
    }, 150));
    sugBox?.addEventListener('mousedown', e => {
        const s = e.target.closest('.tag-suggestion');
        if (s) { e.preventDefault(); add(s.textContent); }
    });
    wrap.closest('form')?.addEventListener('submit', () => { if (input.value.trim()) add(input.value); });
    render();
}

/* ==================== AUTO-OBLICZANIE P/L ==================== */
function initPLCalc() {
    const btn = document.getElementById('calc-pl-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const entry = parseFloat(document.getElementById('entry_price').value);
        const exit = parseFloat(document.getElementById('exit_price').value);
        const size = parseFloat(document.getElementById('wielkosc_pozycji').value);
        const mult = parseFloat(document.getElementById('pl_multiplier')?.value) || 1;
        const dir = document.getElementById('kierunek').value;
        if ([entry, exit, size].some(isNaN)) {
            JT.toast('Uzupełnij Entry, Exit i wielkość pozycji', 'error');
            return;
        }
        const pl = (dir === 'LONG' ? exit - entry : entry - exit) * size * mult;
        const field = document.getElementById('profit_loss');
        field.value = pl.toFixed(2);
        field.classList.remove('flash-field');
        void field.offsetWidth;
        field.classList.add('flash-field');
    });
}

/* ==================== KALENDARZ ==================== */
let calYear, calMonth;

function initCalendar() {
    const grid = document.getElementById('calendar-grid');
    if (!grid) return;
    calYear = parseInt(grid.dataset.year, 10);
    calMonth = parseInt(grid.dataset.month, 10);
    renderCalendar(0);
    document.addEventListener('keydown', e => {
        if (e.target.matches('input, textarea, select')) return;
        if (e.key === 'ArrowLeft') changeMonth(-1);
        if (e.key === 'ArrowRight') changeMonth(1);
    });
}

function changeMonth(delta) {
    calMonth += delta;
    if (calMonth < 1) { calMonth = 12; calYear--; }
    if (calMonth > 12) { calMonth = 1; calYear++; }
    renderCalendar(delta);
}

function goToday() {
    const t = new Date();
    const delta = (t.getFullYear() * 12 + t.getMonth() + 1) - (calYear * 12 + calMonth);
    calYear = t.getFullYear();
    calMonth = t.getMonth() + 1;
    renderCalendar(Math.sign(delta));
}

async function renderCalendar(direction) {
    const grid = document.getElementById('calendar-grid');
    const title = document.getElementById('calendar-title');
    title.textContent = `${MONTHS_PL[calMonth - 1]} ${calYear}`;

    const url = new URL(location);
    url.searchParams.set('year', calYear);
    url.searchParams.set('month', calMonth);
    history.replaceState({}, '', url);

    // animacja wyjścia
    if (direction) {
        grid.style.transition = 'opacity .15s ease, transform .15s ease';
        grid.style.opacity = '0';
        grid.style.transform = `translateX(${direction > 0 ? -30 : 30}px)`;
        await new Promise(r => setTimeout(r, 150));
    }

    const [data, stats] = await Promise.all([
        fetch(`/api/calendar/${calYear}/${calMonth}`).then(r => r.json()).catch(() => ({})),
        fetch(`/api/stats/${calYear}/${calMonth}`).then(r => r.json()).catch(() => null),
    ]);

    grid.innerHTML = '';
    DAYS_PL.forEach(d => {
        const h = document.createElement('div');
        h.className = 'calendar-day-header';
        h.textContent = d;
        grid.appendChild(h);
    });

    let startDay = new Date(calYear, calMonth - 1, 1).getDay() - 1;
    if (startDay < 0) startDay = 6;
    const daysInMonth = new Date(calYear, calMonth, 0).getDate();
    const todayStr = JT.localISO(new Date());

    for (let i = 0; i < startDay; i++) {
        const e = document.createElement('div');
        e.className = 'calendar-day empty';
        grid.appendChild(e);
    }

    // tygodniowe sumy
    const weekly = {};
    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${calYear}-${String(calMonth).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const info = data[dateStr];
        const cell = document.createElement('div');
        cell.className = 'calendar-day cal-anim';
        cell.style.animationDelay = `${(startDay + d) * 12}ms`;
        if (dateStr === todayStr) cell.classList.add('today');
        const dow = new Date(calYear, calMonth - 1, d).getDay();
        if (dow === 0 || dow === 6) cell.classList.add('weekend');

        let html = `<div class="day-number">${d}</div>`;
        if (info) {
            const pl = info.total_pl;
            cell.classList.add(pl > 0 ? 'day-profit' : (pl < 0 ? 'day-loss' : 'day-even'));
            html += `<div class="day-trades">${info.trade_count} ${JT.tradesWord(info.trade_count)}</div>
                     <div class="day-pl ${pl > 0 ? 'profit' : (pl < 0 ? 'loss' : 'zero')}">${JT.fmtPL(pl)}</div>`;
            const wk = Math.floor((startDay + d - 1) / 7);
            weekly[wk] = (weekly[wk] || 0) + pl;
        } else {
            html += `<div class="day-add">＋</div>`;
        }
        cell.innerHTML = html;
        cell.title = info ? 'Zobacz szczegóły dnia' : 'Dodaj trade w tym dniu';
        cell.addEventListener('click', () => {
            location.href = info ? `/dzien/${dateStr}` : `/dodaj?date=${dateStr}`;
        });
        grid.appendChild(cell);
    }

    // wejście
    grid.style.transition = 'none';
    grid.style.transform = `translateX(${direction > 0 ? 30 : (direction < 0 ? -30 : 0)}px)`;
    void grid.offsetWidth;
    grid.style.transition = 'opacity .3s ease, transform .3s ease';
    grid.style.opacity = '1';
    grid.style.transform = 'translateX(0)';

    // podsumowanie tygodni
    const wbox = document.getElementById('weekly-summary');
    if (wbox) {
        const keys = Object.keys(weekly);
        wbox.innerHTML = keys.length ? keys.map(k => `
            <div class="week-item">
                <span class="week-label">Tydzień ${Number(k) + 1}</span>
                <span class="${JT.plClass(weekly[k])}">${JT.fmtPL(weekly[k])}</span>
            </div>`).join('') : '<p class="muted-text">Brak transakcji w tym miesiącu.</p>';
    }

    if (stats) {
        JT.countUp(document.getElementById('stat-total-trades'), stats.total_trades, { decimals: 0 });
        const plEl = document.getElementById('stat-total-pl');
        plEl.className = 'stat-value ' + JT.plClass(stats.total_pl);
        JT.countUp(plEl, stats.total_pl, { prefixSign: true });
        JT.countUp(document.getElementById('stat-winning'), stats.winning_trades, { decimals: 0 });
        JT.countUp(document.getElementById('stat-losing'), stats.losing_trades, { decimals: 0 });
        JT.countUp(document.getElementById('stat-winrate'), stats.winrate, { decimals: 1, suffix: '%' });
        const avgEl = document.getElementById('stat-avg-pl');
        avgEl.className = 'stat-value ' + JT.plClass(stats.avg_pl);
        JT.countUp(avgEl, stats.avg_pl, { prefixSign: true });
    }
}

/* ==================== RIPPLE NA PRZYCISKACH ==================== */
function initRipple() {
    document.addEventListener('pointerdown', e => {
        const btn = e.target.closest('.btn, .nav-item');
        if (!btn) return;
        const r = btn.getBoundingClientRect();
        const s = document.createElement('span');
        s.className = 'ripple';
        const size = Math.max(r.width, r.height);
        s.style.width = s.style.height = size + 'px';
        s.style.left = (e.clientX - r.left - size / 2) + 'px';
        s.style.top = (e.clientY - r.top - size / 2) + 'px';
        btn.appendChild(s);
        setTimeout(() => s.remove(), 600);
    });
}

/* ==================== POJAWIANIE SIĘ PRZY SCROLLU ==================== */
function initReveal() {
    const els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) { els.forEach(e => e.classList.add('visible')); return; }
    const io = new IntersectionObserver(entries => {
        entries.forEach(en => {
            if (en.isIntersecting) { en.target.classList.add('visible'); io.unobserve(en.target); }
        });
    }, { threshold: 0.08 });
    els.forEach(e => io.observe(e));
}

/* ==================== START ==================== */
document.addEventListener('DOMContentLoaded', () => {
    JT.chartDefaults();
    initSidebar();
    initPageTransitions();
    initRipple();
    initReveal();
    initTagsInput();
    initPLCalc();
    initPasteScreenshot();
    initCalendar();

    // Flash -> toasty
    document.querySelectorAll('[data-flash]').forEach(el => {
        JT.toast(el.dataset.flash, el.dataset.category || 'info');
        el.remove();
    });

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') { closeImageModal(); cancelDelete(); }
    });
});
