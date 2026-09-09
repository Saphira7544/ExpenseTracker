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
            <div class="value">${fmtMoney(Math.abs(summary.expenses))}</div>
            <div class="sub-value">Excludes investments</div>
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
                    data: trend.map(r => Math.abs(r.expenses)),
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
                borderColor: '#7c3aed',
                backgroundColor: 'rgba(124,58,237,0.15)',
                fill: true,
                tension: 0.35,
                pointBackgroundColor: '#7c3aed',
                pointRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
        },
    }));
}

function renderOverviewCategoryTrendChart(data) {
    destroyChart('overviewCategoryTrend');
    const ctx = document.getElementById('overviewCategoryTrendChart');
    const categories = Object.keys(data.series);
    registerChart('overviewCategoryTrend', new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.periods.map(formatPeriodLabel),
            datasets: categories.map((cat, i) => ({
                label: cat,
                data: data.periods.map(p => data.series[cat][p] || 0),
                borderColor: CHART_COLORS[i % CHART_COLORS.length],
                backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + '33',
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
    const url = year && year !== 'all'
        ? `/api/analytics/overview?year=${encodeURIComponent(year)}`
        : '/api/analytics/overview?year=all';
    const res = await fetch(url);
    if (!res.ok) {
        console.error('Failed to load overview dashboard');
        return;
    }
    const data = await res.json();

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