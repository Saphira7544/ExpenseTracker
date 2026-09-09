function getLatestValuationForAccount(accountId) {
    return dashboardData.valuations.find(v => v.account_id === accountId) || null;
}

/** Quantity or Price changed -> recompute Original Value, then cascade to CHF. */
function onQuantityOrPriceChange() {
    const quantity = parseFloat(document.getElementById('quickUpdateQuantity').value);
    const price = parseFloat(document.getElementById('quickUpdatePrice').value);
    if (!isNaN(quantity) && !isNaN(price)) {
        document.getElementById('quickUpdateOriginalValue').value = (quantity * price).toFixed(2);
    }
    recomputeChfFromOriginal();
    recomputePerformanceSummary();
}

/** Original Value changed directly by the user -> cascade to CHF only. */
function onOriginalValueChange() {
    recomputeChfFromOriginal();
    recomputePerformanceSummary();
}

/** FX rate changed -> cascade to CHF only. */
function onFxChange() {
    recomputeChfFromOriginal();
}

/** Avg. Purchase Price changed -> only affects the performance summary. */
function onAvgPriceChange() {
    recomputePerformanceSummary();
}

function recomputeChfFromOriginal() {
    const original = parseFloat(document.getElementById('quickUpdateOriginalValue').value);
    const fx = parseFloat(document.getElementById('quickUpdateFx').value);
    if (!isNaN(original) && !isNaN(fx)) {
        document.getElementById('quickUpdateValue').value = (original * fx).toFixed(2);
    }
}

/** Live Cost Basis / Unrealized P&L / Total Return %, for reference only — not saved directly. */
function recomputePerformanceSummary() {
    const quantity = parseFloat(document.getElementById('quickUpdateQuantity').value);
    const avgPrice = parseFloat(document.getElementById('quickUpdateAvgPrice').value);
    const originalValue = parseFloat(document.getElementById('quickUpdateOriginalValue').value);
    const summaryEl = document.getElementById('quickUpdatePerformanceSummary');

    if (isNaN(quantity) || isNaN(avgPrice) || isNaN(originalValue)) {
        summaryEl.textContent = '';
        return;
    }

    const costBasis = quantity * avgPrice;
    const unrealizedPnl = originalValue - costBasis;
    const totalReturnPct = costBasis !== 0 ? (unrealizedPnl / costBasis) * 100 : 0;
    const sign = unrealizedPnl >= 0 ? '+' : '';

    summaryEl.innerHTML = `
        Cost basis: ${costBasis.toFixed(2)}
        &nbsp;·&nbsp; Unrealized P&amp;L: ${sign}${unrealizedPnl.toFixed(2)}
        &nbsp;·&nbsp; Total return: ${sign}${totalReturnPct.toFixed(1)}%
    `;
}

function openQuickUpdateModal(accountId) {
    const account = dashboardData.accounts.find(a => a.id === accountId);
    if (!account) return;

    const latest = getLatestValuationForAccount(accountId);

    document.getElementById('quickUpdateAccountId').value = accountId;
    document.getElementById('quickUpdateAccountName').textContent = account.account_name;
    document.getElementById('quickUpdateCurrencyLabel').textContent = account.currency || '';
    document.getElementById('quickUpdateDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('quickUpdateNote').value = '';
    document.getElementById('quickUpdateError').textContent = '';
    document.getElementById('quickUpdatePerformanceSummary').textContent = '';

    document.getElementById('quickUpdateQuantity').value = latest?.quantity ?? '';
    document.getElementById('quickUpdateAvgPrice').value = latest?.avg_purchase_price ?? '';
    document.getElementById('quickUpdatePrice').value = latest?.current_price ?? '';
    document.getElementById('quickUpdateFx').value = latest?.exchange_rate_to_chf ?? 1;
    document.getElementById('quickUpdateOriginalValue').value = latest?.current_value_original ?? '';
    document.getElementById('quickUpdateRealizedPnl').value = latest?.realized_pnl ?? 0;
    document.getElementById('quickUpdateValue').value = '';

    const hint = document.getElementById('quickUpdateHint');
    if (latest) {
        const qtyPart = latest.quantity != null ? ` · qty ${latest.quantity}` : '';
        hint.textContent = `Last recorded: CHF ${Number(latest.current_value_chf).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} on ${latest.valuation_date}${qtyPart}`;
    } else {
        hint.textContent = 'No previous value on file yet — this will be the first entry.';
    }

    recomputePerformanceSummary();
    document.getElementById('quickUpdateModal').style.display = 'flex';
}

function closeQuickUpdateModal() {
    document.getElementById('quickUpdateModal').style.display = 'none';
}

async function saveQuickUpdate() {
    const accountId = Number(document.getElementById('quickUpdateAccountId').value);
    const date = document.getElementById('quickUpdateDate').value;
    const quantity = parseFloat(document.getElementById('quickUpdateQuantity').value);
    const avgPrice = parseFloat(document.getElementById('quickUpdateAvgPrice').value);
    const price = parseFloat(document.getElementById('quickUpdatePrice').value);
    const originalValue = parseFloat(document.getElementById('quickUpdateOriginalValue').value);
    const fx = parseFloat(document.getElementById('quickUpdateFx').value);
    const chfValue = parseFloat(document.getElementById('quickUpdateValue').value);
    const realizedPnl = parseFloat(document.getElementById('quickUpdateRealizedPnl').value);
    const note = document.getElementById('quickUpdateNote').value;
    const errorEl = document.getElementById('quickUpdateError');

    if (!date || isNaN(chfValue)) {
        errorEl.textContent = 'Please enter at least a date and a CHF value.';
        return;
    }
    errorEl.textContent = '';

    const res = await fetch('/api/networth/valuations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            account_id: accountId,
            valuation_date: date,
            quantity: isNaN(quantity) ? null : quantity,
            avg_purchase_price: isNaN(avgPrice) ? null : avgPrice,
            current_price: isNaN(price) ? null : price,
            current_value_original: isNaN(originalValue) ? null : originalValue,
            exchange_rate_to_chf: isNaN(fx) ? null : fx,
            current_value_chf: chfValue,
            realized_pnl: isNaN(realizedPnl) ? 0 : realizedPnl,
            source: 'manual',
            note: note || null,
        }),
    });

    if (res.ok) {
        closeQuickUpdateModal();
        loadDashboard();
    } else {
        const err = await res.json();
        errorEl.textContent = err.detail || 'Failed to save.';
    }
}

/** Enrich each account row with its latest known value + "as of" date. */
function renderAccountCurrentValues() {
    document.querySelectorAll('[data-current-value-for]').forEach(cell => {
        const accountId = Number(cell.dataset.currentValueFor);
        const latest = getLatestValuationForAccount(accountId);
        if (latest) {
            cell.innerHTML = `
                <strong>CHF ${Number(latest.current_value_chf).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
                <div class="small-muted">as of ${latest.valuation_date}</div>
            `;
        } else {
            cell.innerHTML = '<span class="small-muted">No value yet</span>';
        }
    });
}