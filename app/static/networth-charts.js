// Net Worth Analytics: tiles, stacked liquid/illiquid trend, allocations, investments.

const LIQUID = '#0ea5e9';      // same as the Net Worth page
const ILLIQUID = '#a7770a';
const INVESTED = '#7602c3';    // the Investments category colour
const UNCLASSIFIED = '#9ca3af';

// Asset categories are user-defined, so they get the dataviz skill's validated
// 8-hue palette by their position in Net Worth Config (stable unless reordered).
const ASSET_PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];

const nwFmt = (n, d = 0) => new Intl.NumberFormat(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);
const nwChf = (n, d = 0) => `CHF ${nwFmt(Number(n) || 0, d)}`;
const nwSigned = (n, d = 0) => `${n >= 0 ? '+' : '−'}${nwFmt(Math.abs(n), d)}`;

function nwDate(iso, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
    const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, opts);
}

const axisMoney = {
    ticks: { callback: v => v === 0 ? 'CHF 0' : `CHF ${nwFmt(v / 1000)}k` },
    grid: { color: 'rgba(148,163,184,0.2)' },
};
const moneyTooltip = c => `${c.dataset.label}: ${nwChf(c.parsed.y)}`;

// A real time axis (snapshots are irregular: an 18-month gap must look like one).
// Linear scale over timestamps, so no date adapter library is needed.
const toTime = iso => { const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d).getTime(); };
const timeAxis = points => {
    const xs = points.map(p => p.x);
    const pad = Math.max((Math.max(...xs) - Math.min(...xs)) * 0.02, 86400000);
    return {
        type: 'linear',
        min: Math.min(...xs) - pad,
        max: Math.max(...xs) + pad,
        grid: { display: false },
        // Ticks on the 1st of the month, every 1/2/3/6/12 months so at most ~7 show.
        afterBuildTicks: axis => { axis.ticks = monthTicks(axis.min, axis.max); },
        ticks: {
            autoSkip: false,
            callback: v => new Date(v).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
        },
    };
};

function monthTicks(min, max) {
    const start = new Date(min), end = new Date(max);
    const months = (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth();
    const step = [1, 2, 3, 6, 12].find(s => months / s <= 7) || 12;
    const d = new Date(start.getFullYear(), start.getMonth() + 1, 1);
    while (d.getMonth() % step !== 0) d.setMonth(d.getMonth() + 1);   // align to Jan/Apr/Jul… for readable steps
    const ticks = [];
    for (; d.getTime() <= max; d.setMonth(d.getMonth() + step)) ticks.push({ value: d.getTime() });
    return ticks;
}
const timeTitle = items => items.length ? new Date(items[0].parsed.x).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';

function emptyChart(canvasId, message) {
    const box = document.getElementById(canvasId).parentElement;
    box.innerHTML = `<div class="empty-chart">${esc(message)}</div>`;
}

// ---------- tiles ----------

function renderTiles(trend, investments) {
    const last = trend[trend.length - 1];
    const first = trend[0];
    const tiles = [];
    if (last) {
        const total = Number(last.total_networth_chf);
        const growth = total - Number(first.total_networth_chf);
        const growthPct = Number(first.total_networth_chf) ? growth / Number(first.total_networth_chf) * 100 : 0;
        const liquidShare = total ? Number(last.total_liquid_chf) / total * 100 : 0;
        tiles.push(`
            <div class="summary-card total">
                <div class="label">Net worth</div>
                <div class="value big">${nwChf(total)}</div>
                <div class="sub-value">as of ${esc(nwDate(last.snapshot_date))}</div>
            </div>
            <div class="summary-card net">
                <div class="label">Growth</div>
                <div class="value"><span class="change ${growth >= 0 ? 'up' : 'down'}">${nwSigned(growth)}</span></div>
                <div class="sub-value">${nwSigned(growthPct, 1)}% since ${esc(nwDate(first.snapshot_date))} (${trend.length} snapshots)</div>
            </div>
            <div class="summary-card liquid">
                <div class="label">Liquid share</div>
                <div class="value">${nwFmt(liquidShare)}%</div>
                <div class="sub-value">${nwChf(last.total_liquid_chf)} usable now</div>
                <div class="share-bar"><span style="width:${liquidShare}%; background:${LIQUID}"></span><span style="width:${100 - liquidShare}%; background:${ILLIQUID}"></span></div>
            </div>`);
    } else {
        tiles.push(`<div class="summary-card total"><div class="label">Net worth</div><div class="value big">—</div>
            <div class="sub-value">Record snapshots on the Net Worth page to see your trend.</div></div>`);
    }
    const inv = investments[investments.length - 1];
    if (inv) {
        const prev = investments[investments.length - 2];
        const change = prev ? inv.total_chf - prev.total_chf : null;
        tiles.push(`
            <div class="summary-card invested">
                <div class="label">Investments</div>
                <div class="value">${nwChf(inv.total_chf)}</div>
                <div class="sub-value">as of ${esc(nwDate(inv.date))}${change != null ? ` · <span class="change ${change >= 0 ? 'up' : 'down'}">${nwSigned(change)}</span> since ${esc(nwDate(prev.date))}` : ''}</div>
            </div>`);
    }
    document.getElementById('tiles').innerHTML = tiles.join('');
}

// ---------- charts ----------

function renderNetWorthChart(trend) {
    destroyChart('netWorth');
    if (!trend.length) return emptyChart('netWorthChart', 'No snapshots yet.');
    const area = (label, key, color) => ({
        label,
        data: trend.map(r => ({ x: toTime(r.snapshot_date), y: Number(r[key]) })),
        borderColor: color,
        backgroundColor: color + '55',
        borderWidth: 2,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: color,
        cubicInterpolationMode: 'monotone',
    });
    registerChart('netWorth', new Chart(document.getElementById('netWorthChart'), {
        type: 'line',
        data: {
            datasets: [area('Liquid', 'total_liquid_chf', LIQUID), area('Illiquid', 'total_illiquid_chf', ILLIQUID)],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        title: timeTitle,
                        label: moneyTooltip,
                        footer: items => `Net worth: ${nwChf(items.reduce((s, i) => s + i.parsed.y, 0))}`,
                    },
                },
            },
            scales: {
                y: { ...axisMoney, stacked: true, beginAtZero: true },
                x: timeAxis(trend.map(r => ({ x: toTime(r.snapshot_date) }))),
            },
        },
    }));
}

function renderInvestmentChart(points) {
    destroyChart('investments');
    if (!points.length) return emptyChart('investmentChart', 'No investment accounts with values yet.');
    registerChart('investments', new Chart(document.getElementById('investmentChart'), {
        type: 'line',
        data: {
            datasets: [{
                label: 'Investments',
                data: points.map(p => ({ x: toTime(p.date), y: Number(p.total_chf) })),
                borderColor: INVESTED,
                backgroundColor: INVESTED + '22',
                borderWidth: 2,
                fill: 'origin',
                pointRadius: 4,
                pointBackgroundColor: INVESTED,
                cubicInterpolationMode: 'monotone',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { title: timeTitle, label: moneyTooltip } } },
            scales: { y: { ...axisMoney, beginAtZero: true }, x: timeAxis(points.map(p => ({ x: toTime(p.date) }))) },
        },
    }));
}

function assetColor(name, categories) {
    const i = categories.findIndex(c => c.value === name);
    return i === -1 ? UNCLASSIFIED : ASSET_PALETTE[i % ASSET_PALETTE.length];
}

function shareRows(rows, nameKey, colorOf) {
    const total = rows.reduce((s, r) => s + Number(r.total_chf), 0);
    return rows.map(r => {
        const share = total ? Number(r.total_chf) / total * 100 : 0;
        const color = colorOf(r[nameKey]);
        return `
            <tr>
                <td><span class="swatch" style="background:${color}"></span>${esc(r[nameKey])}</td>
                <td class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${share}%; background:${color}"></div></div></td>
                <td class="num">${nwFmt(share, 1)}%</td>
                <td class="num">${nwChf(r.total_chf)}</td>
            </tr>`;
    }).join('');
}

function renderAllocation(allocation, categories) {
    destroyChart('allocation');
    const table = document.getElementById('allocationTable');
    if (!allocation.length) {
        table.innerHTML = '<tr><td class="empty-state">No account values yet.</td></tr>';
        return emptyChart('allocationChart', '—');
    }
    const colors = allocation.map(r => assetColor(r.asset_category, categories));
    registerChart('allocation', new Chart(document.getElementById('allocationChart'), {
        type: 'doughnut',
        data: {
            labels: allocation.map(r => r.asset_category),
            datasets: [{ data: allocation.map(r => Number(r.total_chf)), backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${nwChf(c.parsed)}` } } },
        },
    }));
    table.innerHTML = shareRows(allocation, 'asset_category', name => assetColor(name, categories));
}

function renderInstitutions(rows) {
    document.getElementById('institutionTable').innerHTML =
        shareRows(rows, 'institution', () => '#4f8ef7') || '<tr><td class="empty-state">No account values yet.</td></tr>';
}

async function loadNetWorthCharts() {
    const [res, lookups] = await Promise.all([
        fetch('/api/analytics/networth-charts'),
        fetch('/api/networth/lookups').then(r => r.json()),
    ]);
    if (!res.ok) {
        console.error('Failed to load net worth charts');
        return;
    }
    const data = await res.json();
    const categories = lookups.asset_categories || [];   // already in Config order
    renderTiles(data.networth_trend, data.investment_trend);
    renderNetWorthChart(data.networth_trend);
    renderAllocation(data.asset_allocation, categories);
    renderInstitutions(data.institution_allocation);
    renderInvestmentChart(data.investment_trend);
}

document.addEventListener('DOMContentLoaded', loadNetWorthCharts);
