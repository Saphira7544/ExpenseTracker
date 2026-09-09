function renderNetWorthTrendChart(trend) {
    destroyChart('netWorthTrend');
    const ctx = document.getElementById('netWorthTrendChart');
    if (!ctx) return;
    registerChart('netWorthTrend', new Chart(ctx, {
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
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
        },
    }));
}

function renderInvestmentTrendChart(trend) {
    destroyChart('investmentTrend');
    const ctx = document.getElementById('investmentTrendChart');
    if (!ctx) return;
    registerChart('investmentTrend', new Chart(ctx, {
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
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
        },
    }));
}

function renderAssetAllocationChart(allocation) {
    destroyChart('assetAllocation');
    const ctx = document.getElementById('assetAllocationChart');
    if (!ctx) return;
    registerChart('assetAllocation', new Chart(ctx, {
        type: 'pie',
        data: {
            labels: allocation.map(r => r.asset_category),
            datasets: [{
                data: allocation.map(r => r.total_chf),
                backgroundColor: allocation.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                borderWidth: 2,
                borderColor: '#fff',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right' } },
        },
    }));
}

function renderLiquiditySplitChart(split) {
    destroyChart('liquiditySplit');
    const ctx = document.getElementById('liquiditySplitChart');
    if (!ctx) return;
    registerChart('liquiditySplit', new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: split.map(r => r.liquidity_status),
            datasets: [{
                data: split.map(r => r.total_chf),
                backgroundColor: ['#16a34a', '#f97316', '#64748b', '#4f8ef7'],
                borderWidth: 2,
                borderColor: '#fff',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right' } },
        },
    }));
}

async function loadNetWorthCharts() {
    const res = await fetch('/api/analytics/networth-charts');
    if (!res.ok) {
        console.error('Failed to load net worth charts');
        return;
    }
    const data = await res.json();
    renderNetWorthTrendChart(data.networth_trend);
    renderInvestmentTrendChart(data.investment_trend);
    renderAssetAllocationChart(data.asset_allocation);
    renderLiquiditySplitChart(data.liquidity_split);
}

document.addEventListener('DOMContentLoaded', loadNetWorthCharts);