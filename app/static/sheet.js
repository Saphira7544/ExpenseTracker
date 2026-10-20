// Monthly Sheet: the month laid out like the old Excel budget sheet.
// Income, savings and totals at the top, then spending grouped into sections
// (Housing, Food, ...; SHEET_GROUPS in app/core/categories.py, plus the group
// picked for each of your own categories on the Categories page),
// then a summary. Every total is shown in the display currency and, smaller,
// in the other one, like the sheet's CHF and EUR columns.

let sheetData = null;
let currentMonth = null;
let availableMonths = [];

const LINES_PREVIEW = 5;   // transactions shown per group before "Show all"
const INVESTED_COLOR = '#7602c3';
const LEFT_OVER_COLOR = '#16a34a';

const MONTH_NAMES = Array.from({ length: 12 }, (_, i) =>
    new Date(2000, i, 1).toLocaleDateString(undefined, { month: 'short' }));

// ---------- formatting ----------

function fmt(n, currency = DISPLAY_CURRENCY) {
    return currency + ' ' + new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(n || 0);
}

function fmtPct(n, digits = 0) {
    return `${(n || 0).toFixed(digits)}%`;
}

/** An amount in the display currency with the other currency underneath. */
function both(main, alt, cls = '') {
    return `<span class="amount ${cls}"><span class="main">${fmt(main)}</span>` +
           `<span class="alt">${fmt(alt, sheetData.alt_currency)}</span></span>`;
}

function fmtDate(iso, opts = { day: 'numeric', month: 'short' }) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, opts);
}

function transactionsLink(line) {
    const p = new URLSearchParams({ search: line.description || '', date_from: line.date, date_to: line.date });
    return `/transactions?${p}`;
}

/** "Paid in CHF 295.25 · EUR 289.44": the amounts in their original currencies
 *  (left out when everything was in the display currency: it would repeat the total). */
function paidIn(byCurrency) {
    const entries = Object.entries(byCurrency);
    if (!entries.some(([c]) => c !== DISPLAY_CURRENCY)) return '';
    return `<div class="paid-in small-muted">Paid in ${entries.map(([c, v]) => esc(fmt(v, c))).join(' · ')}</div>`;
}

/** Positive = more than usual (red), negative = less (green); small differences are "as usual".
 *  Nothing when the month or the usual is net money back (e.g. Transfers full of repayments). */
function vsUsual(value, usual) {
    if (usual === null || usual === undefined || value < 0 || usual < -5) return '';
    const usualText = `usual ${fmt(usual)}`;
    if (Math.abs(usual) < 5) {
        return Math.abs(value) < 5 ? '' : `<span class="vs-new" title="${esc(usualText)}">new this month</span>`;
    }
    const pct = (value - usual) / Math.abs(usual) * 100;
    if (Math.abs(pct) < 10) return `<span class="vs-same" title="${esc(usualText)}">≈ as usual</span>`;
    const more = pct > 0;
    return `<span class="${more ? 'vs-up' : 'vs-down'}" title="${esc(usualText)}">` +
           `${more ? '▲' : '▼'} ${Math.abs(Math.round(pct))}% vs usual</span>`;
}

function lineRow(l) {
    const original = l.currency !== DISPLAY_CURRENCY
        ? `<span class="alt">${esc(fmt(l.amount, l.currency))}</span>` : '';
    return `<li class="${l.value < 0 ? 'money-back-line' : ''}">
        <span class="line-date">${esc(fmtDate(l.date))}</span>
        <a class="line-desc" href="${transactionsLink(l)}" title="${esc(l.description)}${l.note ? ' · ' + esc(l.note) : ''}">${esc(l.description)}</a>
        <span class="line-amount"><span class="main">${fmt(l.value)}</span>${original}</span>
    </li>`;
}

/** Biggest transactions, with a toggle for the rest. */
function lineList(lines, emptyText) {
    if (!lines.length) return `<p class="small-muted empty-note">${esc(emptyText)}</p>`;
    const rest = lines.length - LINES_PREVIEW;
    return `<ul class="line-list">${lines.map((l, i) =>
        lineRow(l).replace('<li', `<li${i >= LINES_PREVIEW ? ' hidden data-extra' : ''}`)).join('')}</ul>
        ${rest > 0 ? `<button type="button" class="link-btn show-more" aria-expanded="false"
            data-more="Show ${rest} more" data-less="Show fewer">Show ${rest} more</button>` : ''}`;
}

function categoryRows(categories) {
    return categories.map(c => `
        <tr>
            <td><span class="category-swatch" style="background:${categoryColor(c.category)}"></span> ${esc(c.category)}</td>
            <td class="numeric ${c.total < 0 ? 'money-back' : ''}">${fmt(c.total)}</td>
        </tr>`).join('');
}

// ---------- 1. Income, 2. Savings, Totals ----------

function renderIncome(income) {
    document.getElementById('income-block').innerHTML = `
        <h2 id="income-title"><i class="fa-solid fa-arrow-down"></i> 1. Income</h2>
        <div class="block-total income-colour">${both(income.total, income.total_alt)}</div>
        ${paidIn(income.by_currency)}
        <table class="category-mini">${categoryRows(income.categories)}</table>
        ${lineList(income.lines, 'No income this month')}`;
}

function renderSavings(savings) {
    document.getElementById('savings-block').innerHTML = `
        <h2 id="savings-title"><i class="fa-solid fa-piggy-bank"></i> 2. Savings &amp; Investments</h2>
        <div class="block-total invested-colour">${both(savings.total, savings.total_alt)}</div>
        ${paidIn(savings.by_currency)}
        ${lineList(savings.lines, 'Nothing invested this month')}`;
}

function renderTotals(t, rate) {
    const alt = sheetData.alt_currency;
    const row = (label, main, altValue, cls = '') => `
        <tr class="${cls}"><th scope="row">${label}</th>
            <td class="numeric">${fmt(main)}</td><td class="numeric alt-col">${fmt(altValue, alt)}</td></tr>`;
    const pct = t.remaining_pct === null ? '—' : fmtPct(t.remaining_pct, 2);
    const rateText = rate
        ? `1 ${esc(DISPLAY_CURRENCY)} = ${rate.rate.toFixed(4)} ${esc(alt)} · 1 ${esc(alt)} = ${(1 / rate.rate).toFixed(4)} ${esc(DISPLAY_CURRENCY)}
           <span title="${esc(sheetData.fx_source)}">(ECB, ${esc(fmtDate(rate.rate_date, { day: 'numeric', month: 'short', year: 'numeric' }))})</span>`
        : 'No exchange rate available';
    document.getElementById('totals-block').innerHTML = `
        <h2 id="totals-title"><i class="fa-solid fa-calculator"></i> Totals</h2>
        <div class="left-over-tile${t.left_over < 0 ? ' negative' : ''}">
            <div class="left-over-label"><i class="fa-solid fa-wallet"></i> Left in your accounts</div>
            ${both(t.left_over, t.left_over_alt)}
            <div class="left-over-help">${t.left_over < 0
                ? 'Spent and invested more than the income'
                : 'Income − expenses − invested'}</div>
        </div>
        <table class="totals-table">
            <thead><tr><th></th><th class="numeric">${esc(DISPLAY_CURRENCY)}</th><th class="numeric alt-col">${esc(alt)}</th></tr></thead>
            <tbody>
                ${row('Net income', t.income, t.income_alt)}
                ${row('Expenses', t.expenses, t.expenses_alt)}
                ${row('Remaining', t.remaining, t.remaining_alt, 'strong ' + (t.remaining < 0 ? 'negative' : ''))}
                <tr><th scope="row">Remaining, % of income</th><td class="numeric" colspan="2">${pct}</td></tr>
                ${row('Of which invested', t.invested, t.invested_alt)}
            </tbody>
        </table>
        <div class="rate-box"><i class="fa-solid fa-right-left"></i> ${rateText}</div>`;
}

// ---------- Where the income went ----------

function renderIncomeSplit(s) {
    const t = s.totals;
    const segments = s.groups.filter(g => g.total > 0.005)
        .map(g => ({ name: g.name, value: g.total, color: g.color }));
    if (t.invested > 0.005) segments.push({ name: 'Invested', value: t.invested, color: INVESTED_COLOR });
    if (t.left_over > 0.005) segments.push({ name: 'Left in your accounts', value: t.left_over, color: LEFT_OVER_COLOR, leftOver: true });

    const el = document.getElementById('income-split');
    const width = segments.reduce((sum, seg) => sum + seg.value, 0);
    if (width <= 0) {
        el.innerHTML = '<p class="small-muted">Nothing to show for this month.</p>';
        return;
    }
    const base = t.income > 0 ? t.income : null;   // percentages are "of income" when there is some
    const share = v => base ? fmtPct(v / base * 100) : fmtPct(v / width * 100);

    const bar = segments.map(seg => `
        <div class="split-seg${seg.leftOver ? ' left-over' : ''}" style="flex-grow:${seg.value}; background:${seg.color}"
             title="${esc(seg.name)}: ${esc(fmt(seg.value))} (${share(seg.value)}${base ? ' of income' : ''})"></div>`).join('');
    const legend = segments.map(seg => `
        <li><span class="category-swatch" style="background:${seg.color}"></span>
            <span class="legend-name">${esc(seg.name)}</span>
            <span class="legend-value">${fmt(seg.value)}</span>
            <span class="legend-share">${share(seg.value)}</span></li>`).join('');

    const notes = [];
    const back = s.groups.filter(g => g.total < -0.005);
    if (back.length) {
        notes.push(`More came back than was spent in ${esc(back.map(g => g.name).join(', '))} ` +
                   `(${fmt(-back.reduce((sum, g) => sum + g.total, 0))}), so they aren't in the bar.`);
    }
    if (!base) notes.push('No income this month: shares are of everything spent and invested.');
    else if (t.left_over < -0.005) {
        notes.push(`<strong>Spent and invested ${fmt(-t.left_over)} more than the month's income.</strong>`);
    }

    el.innerHTML = `
        <div class="split-bar" role="img" aria-label="How the month's income was used">${bar}</div>
        <ul class="split-legend">${legend}</ul>
        ${notes.map(n => `<p class="small-muted split-note">${n}</p>`).join('')}`;
}

// ---------- 3. Expenses, grouped ----------

function renderGroups(s) {
    const income = s.totals.income;
    document.getElementById('expenses-total').innerHTML =
        `${fmt(s.totals.expenses)} · ${fmt(s.totals.expenses_alt, sheetData.alt_currency)}`;

    document.getElementById('group-grid').innerHTML = s.groups.map(g => {
        const empty = !g.lines.length;
        const pctOfIncome = income > 0 && g.total > 0 ? g.total / income * 100 : 0;
        return `
        <article class="card group-card${empty ? ' empty' : ''}" style="--group-colour:${g.color}">
            <header class="group-header">
                <span class="group-icon"><i class="fa-solid ${esc(g.icon)}"></i></span>
                <div class="group-name">
                    <h3>${esc(g.name)}</h3>
                    <div class="small-muted group-members">${esc(g.member_categories.join(' · '))}</div>
                </div>
                ${both(g.total, g.total_alt, g.total < 0 ? 'money-back' : '')}
            </header>
            ${empty ? '<p class="small-muted empty-note">Nothing this month</p>' : `
            <div class="group-meter" title="${income > 0 ? `${fmtPct(pctOfIncome, 1)} of income` : ''}">
                <div style="width:${Math.min(pctOfIncome, 100)}%"></div>
            </div>
            <div class="group-stats small-muted">
                <span>${income > 0 && g.total > 0 ? `${fmtPct(pctOfIncome, 1)} of income` : ''}</span>
                ${vsUsual(g.total, g.usual)}
            </div>
            ${g.categories.length > 1 ? `<table class="category-mini">${categoryRows(g.categories)}</table>` : ''}
            ${paidIn(g.by_currency)}
            ${lineList(g.lines, '')}`}
        </article>`;
    }).join('');
}

// ---------- Summary ----------

function renderSummary(s) {
    const t = s.totals;
    const alt = sheetData.alt_currency;
    const share = v => (t.income > 0 ? fmtPct(v / t.income * 100, 1) : '');
    const row = (label, main, altValue, cls = '', swatch = '') => `
        <tr class="${cls}">
            <th scope="row">${swatch}${label}</th>
            <td class="numeric">${fmt(main)}</td>
            <td class="numeric alt-col">${fmt(altValue, alt)}</td>
            <td class="numeric share">${main > 0 ? share(main) : ''}</td>
        </tr>`;
    document.getElementById('summary-table').innerHTML = `
        <thead><tr><th></th><th class="numeric">Total ${esc(DISPLAY_CURRENCY)}</th>
            <th class="numeric alt-col">Total ${esc(alt)}</th><th class="numeric">% of income</th></tr></thead>
        <tbody>
            ${row('Remaining', t.remaining, t.remaining_alt, 'remaining-row')}
            ${s.groups.map(g => row(esc(g.name), g.total, g.total_alt, g.total < 0 ? 'money-back' : '',
                `<span class="category-swatch" style="background:${g.color}"></span> `)).join('')}
        </tbody>
        <tfoot>${row('Total expenses', t.expenses, t.expenses_alt)}</tfoot>`;
}

// ---------- page ----------

function render() {
    const s = sheetData.sheet;
    const title = fmtDate(`${currentMonth}-01`, { month: 'long', year: 'numeric' });
    document.getElementById('sheet-title').textContent = title;
    document.getElementById('sheet-last-date').textContent = s.last_date
        ? `Last day with data: ${fmtDate(s.last_date, { day: 'numeric', month: 'short', year: 'numeric' })}` : '';
    renderIncome(s.income);
    renderSavings(s.savings);
    renderTotals(s.totals, sheetData.rate);
    renderIncomeSplit(s);
    renderGroups(s);
    renderSummary(s);
    history.replaceState(null, '', `/sheet?month=${encodeURIComponent(currentMonth)}`);
}

function renderMonthPicker() {
    const [year] = currentMonth.split('-');
    const years = [...new Set(availableMonths.map(m => m.slice(0, 4)))];   // newest first

    const yearSelect = document.getElementById('year-select');
    yearSelect.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
    yearSelect.value = year;

    document.getElementById('month-buttons').innerHTML = MONTH_NAMES.map((name, i) => {
        const value = `${year}-${String(i + 1).padStart(2, '0')}`;
        const hasData = availableMonths.includes(value);
        const selected = value === currentMonth;
        return `<button type="button" role="radio" class="month-btn${selected ? ' selected' : ''}"
                    data-month="${value}" aria-checked="${selected}" ${hasData ? '' : 'disabled title="No transactions this month"'}>${esc(name)}</button>`;
    }).join('');
}

// Switching year keeps the same month when that year has data for it,
// otherwise jumps to the year's most recent month with data.
function monthForYear(year) {
    const sameMonth = `${year}-${currentMonth.slice(5)}`;
    if (availableMonths.includes(sameMonth)) return sameMonth;
    return availableMonths.find(m => m.startsWith(`${year}-`));
}

async function loadSheet(month) {
    const res = await fetch(month ? `/api/sheet?month=${encodeURIComponent(month)}` : '/api/sheet');
    if (!res.ok) {
        console.error('Failed to load the monthly sheet');
        return;
    }
    const data = await res.json();
    setupCurrencySelect(data, () => loadSheet(currentMonth));
    renderFxNotice(data);
    sheetData = data;
    availableMonths = data.available_months;
    currentMonth = data.selected_month;
    if (!currentMonth) {
        document.getElementById('sheet-title').textContent = 'No transactions yet';
        return;
    }
    renderMonthPicker();
    render();
}

document.addEventListener('DOMContentLoaded', () => {
    loadSheet(new URLSearchParams(location.search).get('month'));

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadSheet(monthForYear(e.target.value));
    });

    document.getElementById('month-buttons').addEventListener('click', (e) => {
        const btn = e.target.closest('.month-btn');
        if (btn && !btn.disabled && btn.dataset.month !== currentMonth) loadSheet(btn.dataset.month);
    });

    // "Show N more" under any transaction list.
    document.querySelector('.main-content').addEventListener('click', (e) => {
        const btn = e.target.closest('.show-more');
        if (!btn) return;
        const open = btn.getAttribute('aria-expanded') !== 'true';
        btn.previousElementSibling.querySelectorAll('[data-extra]').forEach(li => { li.hidden = !open; });
        btn.setAttribute('aria-expanded', open);
        btn.textContent = open ? btn.dataset.less : btn.dataset.more;
    });
});
