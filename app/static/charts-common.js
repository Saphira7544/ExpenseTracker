
const CHART_COLORS = [
    '#4f8ef7', '#16a34a', '#f97316', '#7c3aed', '#ec4899',
    '#0ea5e9', '#eab308', '#14b8a6', '#ef4444', '#a855f7',
    '#22c55e', '#64748b'
];

const _chartRegistry = {};

function destroyChart(key) {
    if (_chartRegistry[key]) {
        _chartRegistry[key].destroy();
        delete _chartRegistry[key];
    }
}

function registerChart(key, chart) {
    _chartRegistry[key] = chart;
    return chart;
}

// Currency the analytics API returned values in (set from each response).
let DISPLAY_CURRENCY = 'CHF';

function fmtMoney(n) {
    return DISPLAY_CURRENCY + ' ' + new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n || 0);
}

/** Fill the currency toggle; changing it saves the preference and reloads the view. */
function setupCurrencySelect(data, onChange) {
    DISPLAY_CURRENCY = data.currency;
    const select = document.getElementById('currency-select');
    select.innerHTML = data.available_currencies
        .map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    select.value = data.currency;
    select.onchange = async () => {
        await fetch('/api/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_currency: select.value }),
        });
        onChange();
    };
}

/** Explain currency conversion, and warn when something couldn't be converted. */
function renderFxNotice(data) {
    const el = document.getElementById('fx-notice');
    const parts = [];
    if (data.converted_currencies.length) {
        parts.push(`${esc(data.converted_currencies.join(', '))} amounts converted to ${esc(data.currency)} ` +
                   `at the rate of each transaction's date (${esc(data.fx_source)}).`);
    }
    if (data.fx_missing.length) {
        parts.push(`<strong>No exchange rate available for ${esc(data.fx_missing.join(', '))};` +
                   ` those transactions are left out of the totals.</strong>`);
    }
    el.innerHTML = parts.join(' ');
    el.classList.toggle('fx-warning', data.fx_missing.length > 0);
    el.style.display = parts.length ? 'block' : 'none';
}

function fmtCHF(n) {
    return 'CHF ' + new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
}

/** Turns "2026-03" -> "Mar 2026", or "2026" -> "2026" (left as-is for all-time). */
function formatPeriodLabel(period) {
    if (/^\d{4}-\d{2}$/.test(period)) {
        const [y, m] = period.split('-');
        const date = new Date(Number(y), Number(m) - 1, 1);
        return date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
    }
    return period;
}

Chart.defaults.font.family = "-apple-system, 'Segoe UI', Roboto, sans-serif";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15,23,42,0.92)';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
