function renderSummaryCards(summary) {
    const el = document.getElementById('summary-cards');
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
        <div class="summary-card">
            <div class="label">Transactions</div>
            <div class="value">${summary.txn_count}</div>
        </div>
        <div class="summary-card">
            <div class="label">Avg Expense</div>
            <div class="value">${fmtMoney(summary.avg_expense)}</div>
        </div>
        <div class="summary-card">
            <div class="label">Biggest Expense</div>
            <div class="value">${fmtMoney(summary.biggest_expense_amount)}</div>
            <div class="sub-value">${summary.biggest_expense_description || '—'}</div>
        </div>
    `;
}

function renderCategoryPieChart(breakdown) {
    destroyChart('categoryPie');
    const ctx = document.getElementById('categoryPieChart');
    registerChart('categoryPie', new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: breakdown.map(r => r.category),
            datasets: [{
                data: breakdown.map(r => r.total),
                backgroundColor: breakdown.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
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

function renderCategoryTable(breakdown) {
    const tbody = document.querySelector('#category-table tbody');
    tbody.innerHTML = breakdown.map((r, i) => `
        <tr>
            <td><span class="category-swatch" style="background:${CHART_COLORS[i % CHART_COLORS.length]}"></span></td>
            <td>${r.category}</td>
            <td class="numeric">${fmtMoney(r.total)}</td>
        </tr>
    `).join('') || '<tr><td colspan="3">No expenses for this month</td></tr>';
}

function renderDailySpendChart(daily) {
    destroyChart('dailySpend');
    const ctx = document.getElementById('dailySpendChart');
    registerChart('dailySpend', new Chart(ctx, {
        type: 'bar',
        data: {
            labels: daily.map(r => new Date(r.date).getDate()),
            datasets: [{
                label: 'Spend',
                data: daily.map(r => r.total),
                backgroundColor: '#4f8ef7',
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { title: { display: true, text: 'Day of month' } } },
        },
    }));
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
        `<option value="${m}" ${m === selected ? 'selected' : ''}>${formatPeriodLabel(m)}</option>`
    ).join('');
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

    populateMonthSelect(data.available_months, data.selected_month);
    renderSummaryCards(data.month_summary);
    renderCategoryPieChart(data.category_breakdown);
    renderCategoryTable(data.category_breakdown);
    renderDailySpendChart(data.daily_spend);
    renderTopMerchants(data.top_merchants);
}

document.addEventListener('DOMContentLoaded', () => {
    loadMonthly();

    document.getElementById('month-select').addEventListener('change', (e) => {
        loadMonthly(e.target.value);
    });
});