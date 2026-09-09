
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

function fmtMoney(n) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n || 0);
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
