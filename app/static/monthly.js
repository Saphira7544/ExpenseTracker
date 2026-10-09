// Monthly view. Every chart is linked: click a category (pie slice or table
// row) or a day (daily bar) and the rest of the page focuses on it.
//
// The API sends every spending line of the month; the page aggregates them
// itself, so focusing is instant. Like most cross-filtering dashboards, a
// chart is filtered by the *other* selections and highlights its own: the pie
// still shows every category (the selected one stands out), but only for the
// selected day, and the daily chart shows the selected category on every day.

const state = {
    category: null,     // e.g. 'Housing'
    day: null,          // 'YYYY-MM-DD'
    order: 'biggest',   // transactions list: 'biggest' or 'date'
    showAll: false,
};
let monthData = null;
let currentMonth = null;        // 'YYYY-MM' being shown
let availableMonths = [];       // months that have data, newest first

const PIE_MAX_SLICES = 7;       // the rest are summed into "Everything else" (the table lists every category)
const EVERYTHING_ELSE = 'Everything else';
const EVERYTHING_ELSE_COLOR = '#d1d5db';
const MONEY_BACK_COLOR = '#86efac';
const LIST_LIMIT = 10;

// ---------- small helpers ----------

function fmtMoney2(n) {
    return DISPLAY_CURRENCY + ' ' + new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(n || 0);
}

function parseDay(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function fmtDay(iso, withWeekday = true) {
    return parseDay(iso).toLocaleDateString(undefined, withWeekday
        ? { weekday: 'short', day: 'numeric', month: 'short' }
        : { day: 'numeric', month: 'short' });
}

function fade(hex, alpha = '40') {
    return hex.length === 7 ? hex + alpha : hex;
}

/** Update a chart in place (it animates to the new values) or create it. */
function upsertChart(key, canvasId, config) {
    const chart = _chartRegistry[key];
    if (chart && chart.config.type === config.type) {
        chart.data = config.data;
        chart.options = config.options;
        chart.update();
        return;
    }
    destroyChart(key);
    registerChart(key, new Chart(document.getElementById(canvasId), config));
}

function sum(lines, pick = l => l.spent) {
    return lines.reduce((s, l) => s + pick(l), 0);
}

/** Lines matching the given filters (pass null to ignore a filter). */
function linesWhere({ category = null, day = null } = {}) {
    return monthData.lines.filter(l =>
        (category === null || l.category === category) && (day === null || l.date === day));
}

/** Net spent per category, biggest first. */
function breakdown(lines) {
    const totals = new Map();
    lines.forEach(l => totals.set(l.category, (totals.get(l.category) || 0) + l.spent));
    return [...totals].map(([category, total]) => ({ category, total }))
        .filter(r => Math.abs(r.total) >= 0.005)
        .sort((a, b) => b.total - a.total);
}

/** Average net spend per month in the 12 months before this one (0 for months without any). */
function usualFor(category) {
    const h = monthData.history;
    if (!h) return null;
    const before = h.months.slice(0, -1);
    const values = category ? (h.by_category[category] || {}) : h.total;
    return before.reduce((s, m) => s + (values[m] || 0), 0) / before.length;
}

function setFocus(changes) {
    Object.assign(state, changes, { showAll: false });
    render();
}

function toggleCategory(category) {
    setFocus({ category: state.category === category ? null : category });
}

function toggleDay(day) {
    setFocus({ day: state.day === day ? null : day });
}

// ---------- focus bar ----------

function renderFocusBar() {
    const el = document.getElementById('focus-bar');
    if (!state.category && !state.day) {
        el.className = 'focus-bar hint';
        el.innerHTML = '<i class="fa-solid fa-arrow-pointer"></i> Click a category or a day to focus every chart on it.';
        return;
    }
    const chips = [];
    if (state.category) {
        chips.push(`<button type="button" class="focus-chip" data-clear="category" title="Stop focusing on ${esc(state.category)}">
            <span class="category-swatch" style="background:${categoryColor(state.category)}"></span>${esc(state.category)}
            <i class="fa-solid fa-xmark" aria-hidden="true"></i><span class="visually-hidden">remove</span></button>`);
    }
    if (state.day) {
        chips.push(`<button type="button" class="focus-chip" data-clear="day" title="Show the whole month">
            <i class="fa-regular fa-calendar"></i>${esc(fmtDay(state.day))}
            <i class="fa-solid fa-xmark" aria-hidden="true"></i><span class="visually-hidden">remove</span></button>`);
    }
    el.className = 'focus-bar active';
    el.innerHTML = `<span class="focus-label">Focused on</span>${chips.join('')}
        <button type="button" class="focus-clear" data-clear="all">Clear <kbd>Esc</kbd></button>`;
}

// ---------- summary cards ----------

function renderSummaryCards() {
    const el = document.getElementById('summary-cards');
    const summary = monthData.month_summary;
    if (!summary) {
        el.innerHTML = '<div class="summary-card"><div class="label">No data</div><div class="value">—</div></div>';
        return;
    }
    if (!state.category && !state.day) {
        el.innerHTML = `
            <div class="summary-card income"><div class="label">Income</div><div class="value">${fmtMoney(summary.income)}</div></div>
            <div class="summary-card expenses"><div class="label">Expenses</div><div class="value">${fmtMoney(-summary.expenses)}</div>
                <div class="sub-value">Net of refunds &amp; repayments</div></div>
            <div class="summary-card invested"><div class="label">Invested</div><div class="value">${fmtMoney(summary.invested)}</div></div>
            <div class="summary-card net"><div class="label">Net Saved</div><div class="value">${fmtMoney(summary.net)}</div></div>
            <div class="summary-card rate"><div class="label">Savings Rate</div><div class="value">${summary.savings_rate.toFixed(1)}%</div></div>
            <div class="summary-card"><div class="label">Transactions</div><div class="value">${summary.txn_count}</div></div>
            <div class="summary-card"><div class="label">Biggest Expense</div><div class="value">${fmtMoney(summary.biggest_expense_amount)}</div>
                <div class="sub-value" title="${esc(summary.biggest_expense_description)}">${esc(summary.biggest_expense_description || '—')}</div></div>`;
        return;
    }

    // Focused: everything about the selected category and/or day.
    const lines = linesWhere({ category: state.category, day: state.day });
    const out = lines.filter(l => l.spent > 0);
    const moneyOut = sum(out);
    const moneyBack = -sum(lines.filter(l => l.spent < 0));
    const net = moneyOut - moneyBack;
    const biggest = out.reduce((b, l) => (!b || l.spent > b.spent ? l : b), null);
    const what = state.category || 'Spending';
    const when = state.day ? `on ${fmtDay(state.day)}` : 'this month';
    const colour = state.category ? categoryColor(state.category) : '#4f8ef7';

    const cards = [`
        <div class="summary-card focus-card" style="--focus-colour:${colour}">
            <div class="label">${esc(what)}, net</div><div class="value">${fmtMoney(net)}</div>
            <div class="sub-value">${esc(when)}</div></div>`,
        `<div class="summary-card"><div class="label">Money out</div><div class="value">${fmtMoney(moneyOut)}</div>
            <div class="sub-value">${out.length} expense${out.length === 1 ? '' : 's'}</div></div>`,
        `<div class="summary-card"><div class="label">Money back</div><div class="value money-back">${fmtMoney(moneyBack)}</div>
            <div class="sub-value">Refunds &amp; repayments</div></div>`];

    if (state.category) {
        const monthNet = sum(state.day ? linesWhere({ day: state.day }) : monthData.lines);
        if (monthNet > 0 && net > 0) {
            cards.push(`<div class="summary-card"><div class="label">Share of ${state.day ? 'the day' : 'the month'}</div>
                <div class="value">${Math.round(net / monthNet * 100)}%</div>
                <div class="sub-value">of ${fmtMoney(monthNet)} net spending</div></div>`);
        }
    }
    if (!state.day) {
        const usual = usualFor(state.category);
        if (usual !== null) {
            cards.push(`<div class="summary-card"><div class="label">Usual month</div><div class="value">${fmtMoney(usual)}</div>
                <div class="sub-value">${usualComparison(net, usual, true)}</div></div>`);
        }
    }
    if (biggest) {
        cards.push(`<div class="summary-card"><div class="label">Biggest</div><div class="value">${fmtMoney(biggest.spent)}</div>
            <div class="sub-value" title="${esc(biggest.description)}">${esc(fmtDay(biggest.date, false))} · ${esc(biggest.description)}</div></div>`);
    }
    el.innerHTML = cards.join('');
}

/** "▲ 35% more than usual" style text, coloured: more spending is red, less is green. */
function usualComparison(value, usual, long = false) {
    if (value < 0) return long ? '<span class="vs-down">More came back than was spent</span>' : '';
    if (Math.abs(usual) < 5) {
        return Math.abs(value) < 5 ? '' : `<span class="vs-new">${long ? 'Nothing usually' : 'new'}</span>`;
    }
    const pct = (value - usual) / Math.abs(usual) * 100;
    if (Math.abs(pct) < 10) return `<span class="vs-same">≈ ${long ? 'as usual' : 'usual'}</span>`;
    const more = pct > 0;
    const text = `${more ? '▲' : '▼'} ${Math.abs(Math.round(pct))}%${long ? (more ? ' more than usual' : ' less than usual') : ''}`;
    return `<span class="${more ? 'vs-up' : 'vs-down'}">${text}</span>`;
}

// ---------- pie ----------

function pieSlices(rows) {
    // A category can be net negative (more paid back than spent); a pie can't show that.
    // The selected category always gets its own slice, even if it's a small one.
    const positive = rows.filter(r => r.total > 0);
    let top = positive.slice(0, PIE_MAX_SLICES);
    const selected = positive.find(r => r.category === state.category);
    if (selected && !top.includes(selected)) top = top.concat([selected]);
    const rest = positive.filter(r => !top.includes(r));
    const restTotal = sum(rest, r => r.total);
    if (rest.length === 1) return top.concat(rest);
    return restTotal > 0 ? top.concat([{ category: EVERYTHING_ELSE, total: restTotal, inside: rest }]) : top;
}

// Writes the focused amount in the hole of the doughnut.
const centerText = {
    id: 'centerText',
    afterDraw(chart, _args, opts) {
        if (!opts.lines) return;
        const { ctx, chartArea } = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta.data.length) return;
        const { x, y } = meta.data[0];
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#0f172a';
        ctx.font = `700 ${Math.max(13, Math.min(20, chartArea.width / 16))}px ${Chart.defaults.font.family}`;
        ctx.fillText(opts.lines[0], x, y - 9);
        ctx.fillStyle = '#64748b';
        ctx.font = `500 12px ${Chart.defaults.font.family}`;
        ctx.fillText(opts.lines[1], x, y + 12);
        ctx.restore();
    },
};

function renderCategoryPie(rows) {
    const slices = pieSlices(rows);
    const colours = slices.map(r => {
        const c = r.category === EVERYTHING_ELSE ? EVERYTHING_ELSE_COLOR : categoryColor(r.category);
        return state.category && r.category !== state.category ? fade(c) : c;
    });
    const selected = rows.find(r => r.category === state.category);
    const centre = selected
        ? [fmtMoney(selected.total), state.category]
        : [fmtMoney(sum(rows.filter(r => r.total > 0), r => r.total)), state.day ? fmtDay(state.day) : 'spent'];

    upsertChart('categoryPie', 'categoryPieChart', {
        type: 'doughnut',
        data: {
            labels: slices.map(r => r.category),
            datasets: [{
                data: slices.map(r => r.total),
                backgroundColor: colours,
                borderWidth: 2,
                borderColor: '#fff',
                offset: slices.map(r => (r.category === state.category ? 14 : 0)),
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '58%',
            layout: { padding: 10 },
            onClick: (_e, items) => {
                if (!items.length) return;
                const cat = slices[items[0].index].category;
                if (cat !== EVERYTHING_ELSE) toggleCategory(cat);
            },
            onHover: (e, items) => {
                const cat = items.length ? slices[items[0].index].category : null;
                e.native.target.style.cursor = cat && cat !== EVERYTHING_ELSE ? 'pointer' : 'default';
            },
            plugins: {
                centerText: { lines: slices.length ? centre : null },
                legend: {
                    position: 'right',
                    onClick: (_e, item) => {
                        const cat = slices[item.index].category;
                        if (cat !== EVERYTHING_ELSE) toggleCategory(cat);
                    },
                },
                tooltip: {
                    callbacks: {
                        label: c => `${c.label}: ${fmtMoney(c.parsed)}`,
                        afterLabel: c => (slices[c.dataIndex].inside || [])
                            .map(r => `   ${r.category}: ${fmtMoney(r.total)}`),
                        footer: c => (slices[c[0].dataIndex].category === EVERYTHING_ELSE
                            ? 'Pick one in the table to focus on it' : 'Click to focus on it'),
                    },
                },
            },
        },
        plugins: [centerText],
    });
}

// ---------- category table ----------

function renderCategoryTable(rows) {
    const tbody = document.querySelector('#category-table tbody');
    const net = sum(rows, r => r.total);
    const showUsual = !state.day && monthData.history;
    document.querySelector('#category-table thead th:last-child').style.visibility = showUsual ? '' : 'hidden';

    tbody.innerHTML = rows.map(r => {
        const selected = r.category === state.category;
        const share = net > 0 && r.total > 0 ? `${Math.round(r.total / net * 100)}%` : '';
        const usual = showUsual ? usualFor(r.category) : null;
        const usualTitle = usual === null ? '' : `Usual month: ${fmtMoney(usual)} (average of the 12 months before)`;
        return `
        <tr class="${selected ? 'selected' : ''} ${state.category && !selected ? 'dimmed' : ''}"
            data-category="${esc(r.category)}" tabindex="0" role="button" aria-pressed="${selected}">
            <td><span class="category-swatch" style="background:${categoryColor(r.category)}"></span></td>
            <td>${esc(r.category)}</td>
            <td class="numeric ${r.total < 0 ? 'money-back' : ''}">${fmtMoney(r.total)}</td>
            <td class="numeric share">${share}</td>
            <td class="numeric" title="${esc(usualTitle)}">${usual === null ? '' : usualComparison(r.total, usual)}</td>
        </tr>`;
    }).join('') || `<tr><td colspan="5" class="small-muted">No expenses ${state.day ? 'on this day' : 'this month'}</td></tr>`;
}

// ---------- daily chart ----------

function renderDailyChart() {
    const [y, m] = currentMonth.split('-').map(Number);
    const daysInMonth = new Date(y, m, 0).getDate();
    const days = Array.from({ length: daysInMonth }, (_, i) =>
        `${currentMonth}-${String(i + 1).padStart(2, '0')}`);
    const index = new Map(days.map((d, i) => [d, i]));
    const zeros = () => days.map(() => 0);

    // Only the focused category, so its own scale shows which days were heavy.
    const out = zeros(), back = zeros();
    linesWhere({ category: state.category }).forEach(l => {
        const i = index.get(l.date);
        if (i === undefined) return;
        if (l.spent > 0) out[i] += l.spent;
        else back[i] += l.spent;
    });

    const mainColour = state.category ? categoryColor(state.category) : '#4f8ef7';
    const perDay = colour => days.map(d => (state.day && d !== state.day ? fade(colour, '55') : colour));
    const datasets = [{
        label: state.category || 'Spent',
        data: out,
        backgroundColor: perDay(mainColour),
        borderRadius: 3,
    }];
    if (back.some(v => v < 0)) {
        datasets.push({ label: 'Money back', data: back, backgroundColor: perDay(MONEY_BACK_COLOR), borderRadius: 3 });
    }
    document.getElementById('daily-title').textContent =
        state.category ? `Daily Spending on ${state.category}` : 'Daily Spending';

    upsertChart('dailySpend', 'dailySpendChart', {
        type: 'bar',
        data: { labels: days.map(d => Number(d.slice(8))), datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            onClick: (_e, items) => { if (items.length) toggleDay(days[items[0].index]); },
            onHover: (e, items) => { e.native.target.style.cursor = items.length ? 'pointer' : 'default'; },
            plugins: {
                legend: { display: datasets.length > 1, position: 'bottom' },
                tooltip: {
                    filter: c => c.parsed.y !== 0,
                    callbacks: {
                        title: c => fmtDay(days[c[0].dataIndex]),
                        label: c => `${c.dataset.label}: ${fmtMoney(Math.abs(c.parsed.y))}`,
                        footer: c => (days[c[0].dataIndex] === state.day ? 'Click to show the whole month' : 'Click to see this day'),
                    },
                },
            },
            scales: {
                x: { stacked: true, grid: { display: false }, title: { display: true, text: 'Day of month' } },
                y: { stacked: true, ticks: { callback: v => fmtMoney(v) },
                     grid: { color: c => (c.tick.value === 0 ? '#94a3b8' : 'rgba(148,163,184,0.2)') } },
            },
        },
    });
}

// ---------- last 13 months ----------

function renderHistoryChart() {
    const h = monthData.history;
    if (!h) {
        destroyChart('history');
        return;
    }
    const values = state.category ? (h.by_category[state.category] || {}) : h.total;
    const data = h.months.map(m => values[m] || 0);
    const colour = state.category ? categoryColor(state.category) : '#4f8ef7';
    const usual = usualFor(state.category);
    document.getElementById('history-title').textContent =
        state.category ? `${state.category}, Last 13 Months` : 'Last 13 Months';

    upsertChart('history', 'historyChart', {
        type: 'bar',
        data: {
            labels: h.months.map(m => formatPeriodLabel(m).replace(/ (\d{2})(\d{2})$/, " '$2")),
            datasets: [
                {
                    type: 'line',
                    label: 'Usual (12-month average)',
                    data: h.months.map(() => usual),
                    borderColor: '#64748b',
                    borderDash: [5, 4],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHitRadius: 0,
                },
                {
                    label: state.category || 'Net spending',
                    data,
                    backgroundColor: h.months.map(m => (m === currentMonth ? colour : fade(colour, '66'))),
                    borderRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (_e, items) => {
                const bar = items.find(i => i.datasetIndex === 1);
                if (!bar) return;
                const month = h.months[bar.index];
                if (month !== currentMonth && availableMonths.includes(month)) loadMonthly(month);
            },
            onHover: (e, items) => {
                const bar = items.find(i => i.datasetIndex === 1);
                e.native.target.style.cursor = bar && availableMonths.includes(h.months[bar.index]) ? 'pointer' : 'default';
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: c => formatPeriodLabel(h.months[c[0].dataIndex]),
                        label: c => `${c.dataset.label}: ${fmtMoney(c.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
                y: { beginAtZero: true, ticks: { callback: v => fmtMoney(v) } },
            },
        },
    });
}

// ---------- transactions list ----------

function transactionsLink(line) {
    const p = new URLSearchParams({ search: line.description || '', date_from: line.date, date_to: line.date });
    return `/transactions?${p}`;
}

function renderLines() {
    let lines = linesWhere({ category: state.category, day: state.day });
    if (state.order === 'biggest') {
        lines = lines.filter(l => l.spent > 0).sort((a, b) => b.spent - a.spent);
    }
    const total = lines.length;
    const shown = state.showAll ? lines : lines.slice(0, LIST_LIMIT);

    const subject = state.category || '';
    const when = state.day ? ` on ${fmtDay(state.day)}` : '';
    document.getElementById('lines-title').textContent = state.order === 'biggest'
        ? `${subject ? subject + ': ' : ''}Biggest Expenses${when}`
        : `${subject ? subject + ': ' : ''}All Transactions${when}`;

    document.querySelector('#lines-table tbody').innerHTML = shown.map(l => {
        const back = l.spent < 0;
        const original = l.currency !== DISPLAY_CURRENCY
            ? `<span class="original-amount">${esc(l.currency)} ${Math.abs(l.amount).toFixed(2)}</span>` : '';
        return `
        <tr class="${l.date === state.day ? 'on-day' : ''}">
            <td class="col-date"><button type="button" class="link-btn day-btn" data-day="${l.date}"
                title="Focus on this day">${esc(fmtDay(l.date))}</button></td>
            <td>
                <div class="line-desc" title="${esc(l.description)}">${esc(l.description || '—')}</div>
                ${l.note ? `<div class="line-note" title="${esc(l.note)}"><i class="fa-solid fa-scissors"></i> ${esc(l.note)}</div>` : ''}
            </td>
            <td><button type="button" class="link-btn cat-btn" data-category="${esc(l.category)}"
                title="Focus on ${esc(l.category)}">${categoryBadge(l.category)}</button></td>
            <td class="numeric ${back ? 'money-back' : ''}">${back ? '+' : ''}${fmtMoney2(Math.abs(l.spent))}${original}</td>
            <td class="col-open"><a class="icon-btn small" href="${esc(transactionsLink(l))}"
                title="Open in Transactions"><i class="fa-solid fa-arrow-up-right-from-square"></i></a></td>
        </tr>`;
    }).join('') || '<tr><td colspan="5" class="small-muted">Nothing here.</td></tr>';

    const footer = document.getElementById('lines-footer');
    footer.innerHTML = total > LIST_LIMIT
        ? `<span class="small-muted">Showing ${shown.length} of ${total}</span>
           <button type="button" class="link-btn" id="toggle-all">${state.showAll ? 'Show fewer' : `Show all ${total}`}</button>`
        : '';
}

// ---------- everything ----------

function render() {
    if (!monthData) return;
    const rows = breakdown(linesWhere({ day: state.day }));
    renderFocusBar();
    renderSummaryCards();
    renderCategoryPie(rows);
    renderCategoryTable(rows);
    renderDailyChart();
    renderHistoryChart();
    renderLines();

    const params = new URLSearchParams({ month: currentMonth });
    if (state.category) params.set('category', state.category);
    history.replaceState(null, '', `/monthly?${params}`);
}

// ---------- Year dropdown + January..December buttons ----------

const MONTH_NAMES = Array.from({ length: 12 }, (_, i) =>
    new Date(2000, i, 1).toLocaleDateString(undefined, { month: 'short' }));

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

async function loadMonthly(month) {
    const url = month
        ? `/api/analytics/monthly?month=${encodeURIComponent(month)}`
        : '/api/analytics/monthly';
    const res = await fetch(url);
    if (!res.ok) {
        console.error('Failed to load monthly dashboard');
        return;
    }
    const data = await res.json();

    setupCurrencySelect(data, () => loadMonthly(currentMonth));
    renderFxNotice(data);
    monthData = data;
    availableMonths = data.available_months;
    currentMonth = data.selected_month;
    // The category stays focused across months (handy for "how much on Housing each month?"); the day doesn't.
    state.day = null;
    state.showAll = false;
    if (!currentMonth) {
        renderSummaryCards();
        return;
    }
    renderMonthPicker();
    render();
}

document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(location.search);
    state.category = params.get('category') || null;
    loadMonthly(params.get('month'));

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadMonthly(monthForYear(e.target.value));
    });

    document.getElementById('month-buttons').addEventListener('click', (e) => {
        const btn = e.target.closest('.month-btn');
        if (btn && !btn.disabled && btn.dataset.month !== currentMonth) loadMonthly(btn.dataset.month);
    });

    document.getElementById('focus-bar').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-clear]');
        if (!btn) return;
        const what = btn.dataset.clear;
        setFocus(what === 'all' ? { category: null, day: null } : { [what]: null });
    });

    const table = document.querySelector('#category-table tbody');
    table.addEventListener('click', (e) => {
        const row = e.target.closest('tr[data-category]');
        if (row) toggleCategory(row.dataset.category);
    });
    table.addEventListener('keydown', (e) => {
        const row = e.target.closest('tr[data-category]');
        if (row && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            toggleCategory(row.dataset.category);
        }
    });

    document.querySelector('#lines-table tbody').addEventListener('click', (e) => {
        const cat = e.target.closest('.cat-btn');
        const day = e.target.closest('.day-btn');
        if (cat) setFocus({ category: cat.dataset.category });
        if (day) toggleDay(day.dataset.day);
    });

    document.getElementById('lines-footer').addEventListener('click', (e) => {
        if (e.target.closest('#toggle-all')) {
            state.showAll = !state.showAll;
            renderLines();
        }
    });

    document.querySelector('.segmented').addEventListener('click', (e) => {
        const btn = e.target.closest('.segment');
        if (!btn || btn.dataset.mode === state.order) return;
        state.order = btn.dataset.mode;
        state.showAll = false;
        document.querySelectorAll('.segment').forEach(b => {
            b.classList.toggle('selected', b === btn);
            b.setAttribute('aria-checked', String(b === btn));
        });
        renderLines();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && (state.category || state.day) && !document.querySelector('dialog[open]')) {
            setFocus({ category: null, day: null });
        }
    });
});
