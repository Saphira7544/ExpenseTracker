function renderOverviewSummaryCards(summary) {
    const el = document.getElementById('overview-summary-cards');
    if (!summary) {
        el.innerHTML = '<div class="summary-card"><div class="label">No data</div><div class="value">—</div></div>';
        return;
    }
    el.innerHTML = `
        <div class="summary-card income">
            <div class="label">Income</div>
            <div class="value">${fmtMoney(summary.income)}</div>
        </div>
        <div class="summary-card expenses">
            <div class="label">Expenses</div>
            <div class="value">${fmtMoney(-summary.expenses)}</div>
            <div class="sub-value">Net of refunds &amp; repayments</div>
        </div>
        <div class="summary-card invested">
            <div class="label">Invested</div>
            <div class="value">${fmtMoney(summary.invested)}</div>
        </div>
        <div class="summary-card net">
            <div class="label">Net Saved</div>
            <div class="value">${fmtMoney(summary.net)}</div>
        </div>
        <div class="summary-card rate">
            <div class="label">Savings Rate</div>
            <div class="value">${summary.savings_rate.toFixed(1)}%</div>
        </div>
    `;
}

function renderOverviewIncomeExpensesChart(trend) {
    destroyChart('overviewIncomeExpenses');
    const ctx = document.getElementById('overviewIncomeExpensesChart');
    registerChart('overviewIncomeExpenses', new Chart(ctx, {
        type: 'bar',
        data: {
            labels: trend.map(r => formatPeriodLabel(r.period)),
            datasets: [
                {
                    label: 'Income',
                    data: trend.map(r => r.income),
                    backgroundColor: '#16a34a',
                    borderRadius: 6,
                },
                {
                    label: 'Expenses',
                    data: trend.map(r => -r.expenses),
                    backgroundColor: '#dc2626',
                    borderRadius: 6,
                },
                {
                    label: 'Invested',
                    data: trend.map(r => r.invested),
                    backgroundColor: '#7c3aed',
                    borderRadius: 6,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true } },
        },
    }));
}

function renderOverviewSavingsRateChart(trend) {
    destroyChart('overviewSavingsRate');
    const ctx = document.getElementById('overviewSavingsRateChart');
    registerChart('overviewSavingsRate', new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(r => formatPeriodLabel(r.period)),
            datasets: [{
                label: 'Savings rate (%)',
                data: trend.map(r => r.savings_rate),
                // Neutral slate: a rate, not a category (violet means Investments elsewhere).
                borderColor: '#475569',
                backgroundColor: 'rgba(71,85,105,0.12)',
                fill: 'origin',
                cubicInterpolationMode: 'monotone',  // smooth, but never overshoots the data
                borderWidth: 2,
                pointBackgroundColor: '#475569',
                pointRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => `Savings rate: ${c.parsed.y.toFixed(1)}%` } },
            },
            scales: {
                // Start at 0 so the line's height is proportional to the rate
                // (a 30% vs 42% month shouldn't look like a collapse). Negative
                // months still extend below 0.
                y: {
                    beginAtZero: true,
                    suggestedMax: 50,
                    ticks: { callback: v => `${v}%` },
                    grid: { color: c => c.tick.value === 0 ? '#94a3b8' : 'rgba(148,163,184,0.2)' },
                },
            },
        },
    }));
}

// ---------- Category x month heatmap ----------

const MONTH_LABEL = new Intl.DateTimeFormat(undefined, { month: 'short' });

function compactMoney(v) {
    const a = Math.abs(v);
    const text = a >= 10000 ? `${Math.round(a / 1000)}k`
        : a >= 1000 ? `${(a / 1000).toFixed(1)}k`
        : `${Math.round(a)}`;
    return v < 0 ? `−${text}` : text;
}

function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// One cell, shaded with the row's colour as strongly as this month compares
// with the row's biggest month. Money back (negative) gets green text, no fill.
function heatCell(value, rowMax, rgb, month, category) {
    const label = `${category || 'All categories'} · ${formatPeriodLabel(month)}`;
    if (!value || Math.abs(value) < 0.5) {
        return `<td class="hm-cell hm-empty" title="${esc(label)}: nothing">·</td>`;
    }
    const href = category
        ? `/monthly?month=${month}&category=${encodeURIComponent(category)}`
        : `/monthly?month=${month}`;
    const title = `${label}: ${value < 0 ? 'got back ' : ''}${fmtMoney(Math.abs(value))} (open in Monthly)`;
    if (value < 0) {
        return `<td class="hm-cell hm-back"><a href="${href}" title="${esc(title)}">${compactMoney(value)}</a></td>`;
    }
    const alpha = 0.10 + 0.80 * (rowMax > 0 ? value / rowMax : 0);
    const text = alpha > 0.55 ? '#fff' : '#0f172a';
    return `<td class="hm-cell" style="background:rgba(${rgb.join(',')},${alpha.toFixed(2)});color:${text}">` +
           `<a href="${href}" title="${esc(title)}">${compactMoney(value)}</a></td>`;
}

function renderCategoryHeatmap(data) {
    const table = document.getElementById('categoryHeatmap');
    if (!data.periods.length) {
        table.innerHTML = '<tr><td class="small-muted">No spending yet.</td></tr>';
        return;
    }
    const months = data.periods;
    const head = months.map((m, i) => {
        const [y, mm] = m.split('-').map(Number);
        const name = MONTH_LABEL.format(new Date(y, mm - 1, 1));
        const year = i === 0 || mm === 1 ? `<span class="hm-year">${y}</span>` : '<span class="hm-year">&nbsp;</span>';
        return `<th class="hm-month" scope="col">${esc(name)}${year}</th>`;
    }).join('');

    const row = (category, values, total, average, colour) => {
        const positives = Object.values(values).filter(v => v > 0);
        const rowMax = positives.length ? Math.max(...positives) : 0;
        const rgb = hexToRgb(colour);
        const name = category
            ? `<th scope="row" class="hm-name"><span class="category-swatch" style="background:${colour}"></span>${esc(category)}</th>`
            : '<th scope="row" class="hm-name">All categories</th>';
        const classes = [category ? '' : 'hm-total', total < 0 ? 'hm-net-back' : ''].join(' ').trim();
        return `<tr class="${classes}">${name}` +
            months.map(m => heatCell(values[m] || 0, rowMax, rgb, m, category)).join('') +
            `<td class="hm-num">${fmtMoney(average)}</td><td class="hm-num"><strong>${fmtMoney(total)}</strong></td></tr>`;
    };

    const grand = Object.values(data.total).reduce((s, v) => s + v, 0);
    table.innerHTML =
        `<thead><tr><th class="hm-name" scope="col">Category</th>${head}` +
        '<th class="hm-num" scope="col">Avg / month</th><th class="hm-num" scope="col">Total</th></tr></thead>' +
        '<tbody>' +
        row(null, data.total, grand, grand / months.length, '#475569') +
        data.rows.map(r => row(r.category, r.values, r.total, r.average, categoryColor(r.category))).join('') +
        '</tbody>';

    // Show the most recent months first.
    const wrap = document.getElementById('categoryHeatmapWrap');
    wrap.scrollLeft = wrap.scrollWidth;
}

function populateYearSelect(years, selected) {
    const select = document.getElementById('year-select');
    const options = ['<option value="all">All Time</option>']
        .concat(years.map(y => `<option value="${y}">${y}</option>`));
    select.innerHTML = options.join('');
    select.value = selected;
}

async function loadOverview(year) {
    const res = await fetch(`/api/analytics/overview?year=${encodeURIComponent(year || 'all')}`);
    if (!res.ok) {
        console.error('Failed to load overview dashboard');
        return;
    }
    const data = await res.json();

    setupCurrencySelect(data, () => loadOverview(document.getElementById('year-select').value));
    renderFxNotice(data);
    populateYearSelect(data.available_years, data.selected_year);
    renderOverviewSummaryCards(data.summary);
    renderOverviewIncomeExpensesChart(data.income_expenses_trend);
    renderOverviewSavingsRateChart(data.savings_rate_trend);
    renderCategoryHeatmap(data.category_heatmap);
}

document.addEventListener('DOMContentLoaded', () => {
    loadOverview('all');

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadOverview(e.target.value);
    });
});