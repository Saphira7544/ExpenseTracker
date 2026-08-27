

// app/static/analytics.js
// NEW FILE — add this at: app/static/analytics.js
//
// Fetches /api/analytics/dashboard and renders all charts with Chart.js.
// Re-fetches (only the month-dependent parts change) whenever the month dropdown changes.

const COLORS = [
    '#4f8ef7', '#16a34a', '#f97316', '#7c3aed', '#ec4899',
    '#0ea5e9', '#eab308', '#14b8a6', '#ef4444', '#a855f7',
    '#22c55e', '#64748b'
];

let charts = {};

function fmtMoney(n) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n || 0);
}

function destroyChart(key) {
    if (charts[key]) {
        charts[key].destroy();
        delete charts[key];
    }
}

function renderSummaryCards(summary) {
    const el = document.getElementById('summary-cards');
    if (!summary) {
        el.innerHTML = '<div class="summary-card"><div class="label">No data</div><div class="value">—</div></div>';
        return;
    }
    const rate = summary.income > 0 ? ((summary.net / summary.income) * 100).toFixed(1) : '0.0';
    el.innerHTML = `
        <div class="summary-card income">
            <div class="label">Income</div>
            <div class="value">${fmtMoney(summary.income)}</div>
        </div>
        <div class="summary-card expenses">
            <div class="label">Expenses</div>
            <div class="value">${fmtMoney(Math.abs(summary.expenses))}</div>
        </div>
        <div class="summary-card net">
            <div class="label">Net Saved</div>
            <div class="value">${fmtMoney(summary.net)}</div>
        </div>
        <div class="summary-card rate">
            <div class="label">Savings Rate</div>
            <div class="value">${rate}%</div>
        </div>
        <div class="summary-card">
            <div class="label">Transactions</div>
            <div class="value">${summary.txn_count}</div>
        </div>
    `;
}

function renderIncomeExpensesChart(trend) {
    destroyChart('incomeExpenses');
    const ctx = document.getElementById('incomeExpensesChart');
    charts.incomeExpenses = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: trend.map(r => r.month),
            datasets: [
                {
                    label: 'Income',
                    data: trend.map(r => r.income),
                    backgroundColor: '#16a34a',
                    borderRadius: 4,
                },
                {
                    label: 'Expenses',
                    data: trend.map(r => Math.abs(r.expenses)),
                    backgroundColor: '#dc2626',
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true } },
        },
    });
}

function renderSavingsRateChart(trend) {
    destroyChart('savingsRate');
    const ctx = document.getElementById('savingsRateChart');
    charts.savingsRate = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(r => r.month),
            datasets: [{
                label: 'Savings rate (%)',
                data: trend.map(r => r.savings_rate),
                borderColor: '#7c3aed',
                backgroundColor: 'rgba(124,58,237,0.15)',
                fill: true,
                tension: 0.3,
                pointBackgroundColor: '#7c3aed',
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
        },
    });
}

function renderCategoryPieChart(breakdown) {
    destroyChart('categoryPie');
    const ctx = document.getElementById('categoryPieChart');
    charts.categoryPie = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: breakdown.map(r => r.category),
            datasets: [{
                data: breakdown.map(r => r.total),
                backgroundColor: breakdown.map((_, i) => COLORS[i % COLORS.length]),
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'right' } },
        },
    });
}

function renderCategoryTrendChart(data) {
    destroyChart('categoryTrend');
    const ctx = document.getElementById('categoryTrendChart');
    const categories = Object.keys(data.series);
    charts.categoryTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.months,
            datasets: categories.map((cat, i) => ({
                label: cat,
                data: data.months.map(m => data.series[cat][m] || 0),
                borderColor: COLORS[i % COLORS.length],
                backgroundColor: COLORS[i % COLORS.length] + '33',
                fill: true,
                tension: 0.3,
            })),
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { stacked: true, beginAtZero: true }, x: { stacked: true } },
        },
    });
}

function renderNetWorthChart(trend) {
    destroyChart('netWorth');
    const ctx = document.getElementById('netWorthChart');
    charts.netWorth = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(r => r.snapshot_date),
            datasets: [
                {
                    label: 'Total Net Worth (CHF)',
                    data: trend.map(r => r.total_networth_chf),
                    borderColor: '#4f8ef7',
                    backgroundColor: 'rgba(79,142,247,0.15)',
                    fill: true,
                    tension: 0.3,
                },
                {
                    label: 'Liquid (CHF)',
                    data: trend.map(r => r.total_liquid_chf),
                    borderColor: '#16a34a',
                    fill: false,
                    tension: 0.3,
                },
                {
                    label: 'Illiquid (CHF)',
                    data: trend.map(r => r.total_illiquid_chf),
                    borderColor: '#f97316',
                    fill: false,
                    tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'bottom' } },
        },
    });
}

function renderInvestmentTrendChart(trend) {
    destroyChart('investmentTrend');
    const ctx = document.getElementById('investmentTrendChart');
    charts.investmentTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(r => r.date),
            datasets: [{
                label: 'Investment value (CHF)',
                data: trend.map(r => r.total_chf),
                borderColor: '#0ea5a4',
                backgroundColor: 'rgba(14,165,164,0.15)',
                fill: true,
                tension: 0.3,
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
        },
    });
}

function renderAssetAllocationChart(allocation) {
    destroyChart('assetAllocation');
    const ctx = document.getElementById('assetAllocationChart');
    charts.assetAllocation = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: allocation.map(r => r.asset_category),
            datasets: [{
                data: allocation.map(r => r.total_chf),
                backgroundColor: allocation.map((_, i) => COLORS[i % COLORS.length]),
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'right' } },
        },
    });
}

function renderLiquiditySplitChart(split) {
    destroyChart('liquiditySplit');
    const ctx = document.getElementById('liquiditySplitChart');
    charts.liquiditySplit = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: split.map(r => r.liquidity_status),
            datasets: [{
                data: split.map(r => r.total_chf),
                backgroundColor: ['#16a34a', '#f97316', '#64748b', '#4f8ef7'],
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'right' } },
        },
    });
}

function renderTopMerchants(rows) {
    const tbody = document.querySelector('#top-merchants-table tbody');
    tbody.innerHTML = rows.map(r => `
        <tr>
            <td>${r.description ?? '—'}</td>
            <td>${r.occurrences}</td>
            <td class="numeric">${fmtMoney(r.total)}</td>
        </tr>
    `).join('') || '<tr><td colspan="3">No data for this month</td></tr>';
}

function populateMonthSelect(months, selected) {
    const select = document.getElementById('month-select');
    select.innerHTML = months.map(m =>
        `<option value="${m}" ${m === selected ? 'selected' : ''}>${m}</option>`
    ).join('');
}

async function loadDashboard(month) {
    const url = month
        ? `/api/analytics/dashboard?month=${encodeURIComponent(month)}`
        : '/api/analytics/dashboard';
    const res = await fetch(url);
    if (!res.ok) {
        console.error('Failed to load analytics dashboard');
        return;
    }
    const data = await res.json();

    populateMonthSelect(data.available_months, data.selected_month);
    renderSummaryCards(data.month_summary);
    renderIncomeExpensesChart(data.income_expenses_trend);
    renderSavingsRateChart(data.savings_rate_trend);
    renderCategoryPieChart(data.category_breakdown);
    renderCategoryTrendChart(data.spending_by_category_trend);
    renderNetWorthChart(data.networth_trend);
    renderInvestmentTrendChart(data.investment_trend);
    renderAssetAllocationChart(data.asset_allocation);
    renderLiquiditySplitChart(data.liquidity_split);
    renderTopMerchants(data.top_merchants);
}

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();

    document.getElementById('month-select').addEventListener('change', (e) => {
        loadDashboard(e.target.value);
    });
});
