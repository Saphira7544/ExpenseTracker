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

function renderOverviewCategoryTrendChart(data) {
    destroyChart('overviewCategoryTrend');
    const ctx = document.getElementById('overviewCategoryTrendChart');
    // "Other" (everything outside the top categories) is drawn last, in grey.
    const categories = Object.keys(data.series).sort((a, b) => (a === 'Other') - (b === 'Other'));
    registerChart('overviewCategoryTrend', new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.periods.map(formatPeriodLabel),
            datasets: categories.map(cat => ({
                label: cat,
                data: data.periods.map(p => data.series[cat][p] || 0),
                borderColor: categoryColor(cat),
                backgroundColor: categoryColor(cat) + '33',
                fill: true,
                tension: 0.3,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { stacked: true, beginAtZero: true }, x: { stacked: true } },
        },
    }));
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
    renderOverviewCategoryTrendChart(data.spending_by_category_trend);
}

document.addEventListener('DOMContentLoaded', () => {
    loadOverview('all');

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadOverview(e.target.value);
    });
});