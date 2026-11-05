function monthLabel(period, opts = { month: 'short', year: 'numeric' }) {
    const [y, m] = period.split('-').map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString(undefined, opts);
}

// Occasional categories (Settings, default Travel): spending that isn't part of a
// normal month. Shown apart from the regular expenses; OCCASIONAL is null when none.
let OCCASIONAL = null;

function setupOccasional(data) {
    const names = data.occasional_categories || [];
    OCCASIONAL = names.length ? {
        names,
        label: names.join(' & '),
        color: categoryColor(names[0]),
    } : null;
}

/**
 * One row of cards: each shows the total for the period and, underneath, the
 * average per month over the complete months (the month in progress is left
 * out: its expenses aren't all in yet). `avg` is null when there's no
 * complete month, and then only the totals show.
 */
function renderOverviewSummaryCards(summary, avg) {
    const el = document.getElementById('overview-summary-cards');
    const note = document.getElementById('summary-note');
    if (!summary) {
        el.innerHTML = '<div class="summary-card"><div class="label">No data</div><div class="value">—</div></div>';
        note.textContent = '';
        return;
    }
    const perMonth = (value, isRate = false) => !avg ? '' : `
        <div class="per-month">
            <span class="per-month-label">${isRate ? 'Complete months' : 'Per month'}</span>
            <span class="per-month-value">${isRate ? `${value.toFixed(1)}%` : fmtMoney(value)}</span>
        </div>`;
    const card = (cls, label, value, avgValue, sub = '', isRate = false, style = '') => `
        <div class="summary-card ${cls}" ${style ? `style="${style}"` : ''}>
            <div class="label">${label}</div>
            <div class="value">${value}</div>
            ${sub ? `<div class="sub-value" title="${esc(sub.replace(/<[^>]+>/g, ''))}">${sub}</div>` : ''}
            ${perMonth(avgValue, isRate)}
        </div>`;

    const trips = OCCASIONAL ? esc(OCCASIONAL.label) : '';
    const cards = [card('income', 'Income', fmtMoney(summary.income), avg?.income)];
    if (OCCASIONAL) {
        cards.push(
            card('expenses', 'Regular Expenses', fmtMoney(-summary.regular_expenses), avg && -avg.regular_expenses,
                 `Without ${trips.toLowerCase()}`),
            card('occasional', trips, fmtMoney(-summary.occasional), avg && -avg.occasional,
                 'Apart from regular', false, `--occasional-colour:${OCCASIONAL.color}`));
    } else {
        cards.push(card('expenses', 'Expenses', fmtMoney(-summary.expenses), avg && -avg.expenses,
                        'Net of refunds &amp; repayments'));
    }
    cards.push(
        card('invested', 'Invested', fmtMoney(summary.invested), avg?.invested),
        card('net', 'Net Saved', fmtMoney(summary.net), avg?.net,
             OCCASIONAL ? `${fmtMoney(summary.net_regular)} before ${trips.toLowerCase()}` : 'Income − expenses'),
        card('rate', 'Savings Rate', `${summary.savings_rate.toFixed(1)}%`, avg?.savings_rate,
             OCCASIONAL ? `${summary.savings_rate_regular.toFixed(1)}% before ${trips.toLowerCase()}` : '', true));
    el.innerHTML = cards.join('');

    if (!avg) {
        note.textContent = '';
        return;
    }
    const range = avg.from === avg.to ? monthLabel(avg.from) : `${monthLabel(avg.from)} – ${monthLabel(avg.to)}`;
    let text = `Per month: average of ${avg.months} complete month${avg.months === 1 ? '' : 's'} (${range}).`;
    if (avg.left_out.length) {
        const months = avg.left_out.map(p => monthLabel(p, { month: 'long', year: 'numeric' })).join(', ');
        text += ` ${months} isn't over yet, so it's left out.`;
    }
    note.textContent = text;
}

function renderOverviewIncomeExpensesChart(trend) {
    destroyChart('overviewIncomeExpenses');
    const ctx = document.getElementById('overviewIncomeExpensesChart');
    const bar = (label, data, color, stack) => ({ label, data, backgroundColor: color, borderRadius: 6, stack });
    // Regular expenses and occasional spending (trips) stack into one expenses bar.
    const datasets = [bar('Income', trend.map(r => r.income), '#16a34a', 'income')];
    if (OCCASIONAL) {
        datasets.push(
            bar('Regular expenses', trend.map(r => -r.regular_expenses), '#dc2626', 'spent'),
            bar(OCCASIONAL.label, trend.map(r => -r.occasional), OCCASIONAL.color, 'spent'));
    } else {
        datasets.push(bar('Expenses', trend.map(r => -r.expenses), '#dc2626', 'spent'));
    }
    datasets.push(bar('Invested', trend.map(r => r.invested), '#7c3aed', 'invested'));

    registerChart('overviewIncomeExpenses', new Chart(ctx, {
        type: 'bar',
        data: { labels: trend.map(r => formatPeriodLabel(r.period)), datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: c => `${c.dataset.label}: ${fmtMoney(c.parsed.y)}`,
                        footer: items => (OCCASIONAL
                            ? `All expenses: ${fmtMoney(-trend[items[0].dataIndex].expenses)}` : ''),
                    },
                },
            },
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
        },
    }));
}

// The line shows what happened; for a year still in progress, this says where it's heading.
function renderProjectionNote(projection) {
    const el = document.getElementById('projection-note');
    el.hidden = !projection;
    if (!projection) return;
    const p = projection;
    const beforeTrips = OCCASIONAL ? ` (${p.savings_rate_regular.toFixed(1)}% before ${esc(OCCASIONAL.label.toLowerCase())})` : '';
    const income = p.income_from_last_year ? "last year's income" : "last year's income where known";
    el.innerHTML = `<strong>Projected for ${esc(p.year)}: ${p.savings_rate.toFixed(1)}%${beforeTrips}, saving ${esc(fmtMoney(p.net))}.</strong>
        Estimate: the months left use ${income} and this year's average spending.`;
}

function renderOverviewSavingsRateChart(trend, projection, selectedYear) {
    destroyChart('overviewSavingsRate');
    const ctx = document.getElementById('overviewSavingsRateChart');
    // All Time has one point per year: this year's point is the year so far, and the
    // projection continues the line to a point of its own. A year's months can't
    // continue into a yearly rate, so there it's a level line across the chart.
    const extendLine = !!projection && selectedYear === 'all';
    const rows = extendLine ? [...trend, projection] : trend;
    const last = rows.length - 1;
    const labels = trend.map(r => formatPeriodLabel(r.period));
    if (extendLine) {
        labels[labels.length - 1] = `${projection.year} so far`;
        labels.push(`${projection.year} projected`);
    }
    const isProjected = i => extendLine && i === last;
    // Positions in time when projecting: a year's tick is that year's end, so the
    // year so far sits as close to its end as today really is.
    const projectedYear = extendLine ? Number(projection.year) : null;
    const xPosition = i => {
        if (isProjected(i)) return projectedYear;
        if (i === last - 1) {
            const start = new Date(projectedYear, 0, 1);
            const end = new Date(projectedYear + 1, 0, 1);
            return projectedYear - 1 + (Date.now() - start) / (end - start);
        }
        return Number(rows[i].period);
    };
    const points = pick => rows.map((r, i) => (extendLine ? { x: xPosition(i), y: pick(r) } : pick(r)));
    const datasets = [{
        label: 'Savings rate',
        savedKey: 'net',
        data: points(r => r.savings_rate),
        segment: extendLine ? {
            borderDash: c => (c.p1DataIndex === last ? [6, 4] : undefined),
            backgroundColor: c => (c.p1DataIndex === last ? 'transparent' : undefined),
        } : undefined,
        // Neutral slate: a rate, not a category (violet means Investments elsewhere).
        borderColor: '#475569',
        backgroundColor: 'rgba(71,85,105,0.12)',
        fill: 'origin',
        cubicInterpolationMode: 'monotone',  // smooth, but never overshoots the data
        borderWidth: 2,
        pointBackgroundColor: rows.map((_, i) => (isProjected(i) ? '#fff' : '#475569')),
        pointBorderColor: '#475569',
        pointRadius: 4,
    }];
    if (OCCASIONAL) {
        // What a normal month would have saved: the gap to the solid line is what trips cost.
        datasets.push({
            label: `Before ${OCCASIONAL.label.toLowerCase()}`,
            savedKey: 'net_regular',
            data: points(r => r.savings_rate_regular),
            borderColor: OCCASIONAL.color,
            backgroundColor: OCCASIONAL.color,
            borderDash: [6, 4],
            borderWidth: 2,
            fill: false,
            cubicInterpolationMode: 'monotone',
            pointRadius: 3,
        });
    }
    if (projection && !extendLine) {
        datasets.push({
            label: `Projected for ${projection.year}`,
            data: trend.map(() => projection.savings_rate),
            isProjection: true,
            borderColor: '#0f172a',
            borderDash: [3, 4],
            borderWidth: 1.5,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 0,
        });
    }
    registerChart('overviewSavingsRate', new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: datasets.length > 1, position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: c => {
                            if (c.dataset.isProjection) {
                                return `${c.dataset.label}: ${c.parsed.y.toFixed(1)}% · saved ${fmtMoney(projection.net)}`;
                            }
                            const amount = rows[c.dataIndex][c.dataset.savedKey];
                            return `${c.dataset.label}: ${c.parsed.y.toFixed(1)}% · saved ${fmtMoney(amount)}`;
                        },
                        title: items => labels[items[0].dataIndex],
                        footer: items => {
                            const i = items[0].dataIndex;
                            return `${isProjected(i) ? 'Estimated income' : 'Income'}: ${fmtMoney(rows[i].income)}`;
                        },
                    },
                },
            },
            scales: {
                ...(extendLine ? {
                    x: {
                        type: 'linear',
                        min: Number(rows[0].period) - 0.2,
                        max: projectedYear + 0.2,
                        afterBuildTicks: axis => {
                            axis.ticks = rows.filter((_, i) => i !== last - 1).map((_, i) => ({ value: Number(rows[0].period) + i }));
                        },
                        ticks: { callback: v => String(v) },
                    },
                } : {}),
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

// ---------- Occasional spending (trips) on its own ----------

function renderOccasionalSection(data) {
    const section = document.getElementById('occasional-section');
    section.hidden = !OCCASIONAL;
    if (!OCCASIONAL) return;

    const s = data.summary;
    const avg = data.monthly_average;
    const trend = data.income_expenses_trend;
    const name = OCCASIONAL.label.toLowerCase();
    document.getElementById('occasional-title').textContent = OCCASIONAL.label;

    const spent = -s.occasional;
    const allExpenses = -s.expenses;
    const ratePoints = s.savings_rate_regular - s.savings_rate;
    const periodWord = data.selected_year === 'all' ? 'year' : 'month';
    const periodsWith = trend.filter(r => -r.occasional > 0.5).length;
    const stat = (title, value, help = '') => `
        <div class="occ-stat"><div class="occ-stat-name">${esc(title)}</div>
            <div class="occ-stat-value">${esc(value)}</div>${help ? `<div class="occ-stat-help">${esc(help)}</div>` : ''}</div>`;
    document.getElementById('occasional-stats').innerHTML = [
        stat('Spent', fmtMoney(spent), `${allExpenses > 0 ? Math.round(spent / allExpenses * 100) : 0}% of all expenses`),
        avg ? stat('Per month', fmtMoney(-avg.occasional), 'Average of complete months') : '',
        stat('Cost to your savings rate', `${ratePoints > 0 ? '−' : ''}${Math.abs(ratePoints).toFixed(1)} pts`,
             `${s.savings_rate_regular.toFixed(1)}% without, ${s.savings_rate.toFixed(1)}% with`),
        stat(`${periodWord === 'year' ? 'Years' : 'Months'} with ${name}`, `${periodsWith} of ${trend.length}`),
    ].join('');

    destroyChart('occasionalChart');
    registerChart('occasionalChart', new Chart(document.getElementById('occasionalChart'), {
        type: 'bar',
        data: {
            labels: trend.map(r => formatPeriodLabel(r.period)),
            datasets: [{
                label: OCCASIONAL.label,
                data: trend.map(r => -r.occasional),
                // A bar below zero: more came back (e.g. friends paying their share) than was spent.
                backgroundColor: trend.map(r => (-r.occasional < 0 ? '#86efac' : OCCASIONAL.color)),
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: c => (c.parsed.y < 0 ? `Money back: ${fmtMoney(-c.parsed.y)}` : `Spent: ${fmtMoney(c.parsed.y)}`),
                        afterLabel: c => {
                            const r = trend[c.dataIndex];
                            return -r.expenses > 0 && -r.occasional > 0
                                ? `${Math.round(-r.occasional / -r.expenses * 100)}% of that ${periodWord}'s expenses` : '';
                        },
                        footer: () => (periodWord === 'month' ? 'Click to open it in Monthly' : ''),
                    },
                },
            },
            onClick: (_e, items) => {
                const period = items.length ? trend[items[0].index].period : null;
                if (period && /^\d{4}-\d{2}$/.test(period)) {
                    location.href = `/monthly?month=${period}&category=${encodeURIComponent(OCCASIONAL.names[0])}`;
                }
            },
            scales: { y: { beginAtZero: true } },
        },
    }));

    const lines = data.occasional_lines;
    document.getElementById('occasional-lines').innerHTML = lines.length ? lines.map(l => {
        const p = new URLSearchParams({ search: l.description || '', date_from: l.paid_on, date_to: l.paid_on });
        const day = new Date(`${l.paid_on}T00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
        return `<li><span class="occ-date">${esc(day)}</span>
            <a href="/transactions?${p}" title="${esc(l.description)}">${esc(l.description)}</a>
            <span class="occ-amount">${fmtMoney(l.spent)}</span></li>`;
    }).join('') : `<li class="small-muted">No ${esc(name)} spending in this period.</li>`;
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
    setupOccasional(data);
    renderOverviewSummaryCards(data.summary, data.monthly_average);
    renderOverviewIncomeExpensesChart(data.income_expenses_trend);
    renderOverviewSavingsRateChart(data.savings_rate_trend, data.year_end_projection, data.selected_year);
    renderProjectionNote(data.year_end_projection);
    renderOccasionalSection(data);
    renderCategoryHeatmap(data.category_heatmap);
}

document.addEventListener('DOMContentLoaded', () => {
    loadOverview('all');

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadOverview(e.target.value);
    });
});