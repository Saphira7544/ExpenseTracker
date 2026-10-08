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
            <div class="sub-value" title="${esc(summary.biggest_expense_description)}">${esc(summary.biggest_expense_description || '—')}</div>
        </div>
    `;
}

const PIE_MAX_SLICES = 7;  // the rest fold into "Other" (the table below lists every category)

function pieSlices(breakdown) {
    // A category can be net negative (more paid back than spent); a pie can't show that.
    const positive = breakdown.filter(r => r.total > 0);
    const top = positive.filter(r => r.category !== 'Other').slice(0, PIE_MAX_SLICES);
    const rest = positive.filter(r => !top.includes(r)).reduce((sum, r) => sum + r.total, 0);
    return rest > 0 ? top.concat([{ category: 'Other', total: rest }]) : top;
}

function renderCategoryPieChart(breakdown) {
    breakdown = pieSlices(breakdown);
    destroyChart('categoryPie');
    const ctx = document.getElementById('categoryPieChart');
    registerChart('categoryPie', new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: breakdown.map(r => r.category),
            datasets: [{
                data: breakdown.map(r => r.total),
                backgroundColor: breakdown.map(r => categoryColor(r.category)),
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
    tbody.innerHTML = breakdown.map(r => `
        <tr>
            <td><span class="category-swatch" style="background:${categoryColor(r.category)}"></span></td>
            <td>${esc(r.category)}</td>
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
            <td>${esc(r.description ?? '—')}</td>
            <td>${r.occurrences}</td>
            <td class="numeric">${fmtMoney(r.total)}</td>
        </tr>
    `).join('') || '<tr><td colspan="3">No data for this month</td></tr>';
}

// ---------- Year dropdown + January..December buttons ----------

let currentMonth = null;        // 'YYYY-MM' being shown
let availableMonths = [];       // months that have data, newest first

const MONTH_NAMES = Array.from({ length: 12 }, (_, i) =>
    new Date(2000, i, 1).toLocaleDateString(undefined, { month: 'short' }));

function renderMonthPicker() {
    const [year, month] = currentMonth.split('-');
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
    availableMonths = data.available_months;
    currentMonth = data.selected_month;
    if (currentMonth) renderMonthPicker();
    renderSummaryCards(data.month_summary);
    renderCategoryPieChart(data.category_breakdown);
    renderCategoryTable(data.category_breakdown);
    renderDailySpendChart(data.daily_spend);
    renderTopMerchants(data.top_merchants);
}

document.addEventListener('DOMContentLoaded', () => {
    loadMonthly();

    document.getElementById('year-select').addEventListener('change', (e) => {
        loadMonthly(monthForYear(e.target.value));
    });

    document.getElementById('month-buttons').addEventListener('click', (e) => {
        const btn = e.target.closest('.month-btn');
        if (btn && !btn.disabled && btn.dataset.month !== currentMonth) loadMonthly(btn.dataset.month);
    });
});