function getLatestValuationForAccount(accountId) {
    // dashboardData.valuations is already sorted by valuation_date DESC
    // (see list_valuations() in app/services/networth.py), so the first
    // match for this account is the latest one.
    return dashboardData.valuations.find(v => v.account_id === accountId) || null;
}

function openQuickUpdateModal(accountId) {
    const account = dashboardData.accounts.find(a => a.id === accountId);
    if (!account) return;

    const latest = getLatestValuationForAccount(accountId);

    document.getElementById('quickUpdateAccountId').value = accountId;
    document.getElementById('quickUpdateAccountName').textContent = account.account_name;
    document.getElementById('quickUpdateDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('quickUpdateValue').value = '';
    document.getElementById('quickUpdateNote').value = '';

    const hint = document.getElementById('quickUpdateHint');
    if (latest) {
        hint.textContent = `Last recorded: CHF ${Number(latest.current_value_chf).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} on ${latest.valuation_date}`;
    } else {
        hint.textContent = 'No previous value on file yet — this will be the first entry.';
    }

    document.getElementById('quickUpdateModal').style.display = 'flex';
}

function closeQuickUpdateModal() {
    document.getElementById('quickUpdateModal').style.display = 'none';
}

async function saveQuickUpdate() {
    const accountId = Number(document.getElementById('quickUpdateAccountId').value);
    const date = document.getElementById('quickUpdateDate').value;
    const value = parseFloat(document.getElementById('quickUpdateValue').value);
    const note = document.getElementById('quickUpdateNote').value;
    const errorEl = document.getElementById('quickUpdateError');

    if (!date || isNaN(value)) {
        errorEl.textContent = 'Please enter a date and a value.';
        return;
    }
    errorEl.textContent = '';

    // This is a POST, not a PATCH — it always creates a brand-new
    // valuation row for today (or the date you pick), preserving history.
    const res = await fetch('/api/networth/valuations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            account_id: accountId,
            valuation_date: date,
            current_value_chf: value,
            source: 'manual',
            note: note || null,
        }),
    });

    if (res.ok) {
        closeQuickUpdateModal();
        loadDashboard(); // existing function in networth.html — refreshes tables + accounts
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