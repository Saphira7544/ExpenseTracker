// Net Worth page: headline tiles, accounts / value history / snapshots tabs, and their dialogs.

const $ = id => document.getElementById(id);
let data = null;               // /api/networth/dashboard
let latestByAccount = new Map();

const STALE_DAYS = 62;

// ---------- formatting ----------

const fmt = (n, digits = 2) =>
  new Intl.NumberFormat(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
const chf = (n, digits = 2) => `CHF ${fmt(Number(n) || 0, digits)}`;
const signed = (n, digits = 0) => `${n >= 0 ? "+" : "−"}${fmt(Math.abs(n), digits)}`;

function formatDate(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function todayLocal() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function daysSince(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return Math.floor((Date.now() - new Date(y, m - 1, d)) / 86400000);
}

function liquidityKind(name) {
  const n = (name || "").toLowerCase();
  if (n.includes("illiquid")) return "illiquid";
  if (n.includes("liquid")) return "liquid";
  return "neutral";
}

const liquidityPill = name => name ? `<span class="pill ${liquidityKind(name)}">${esc(name)}</span>` : '<span class="muted-cell">—</span>';

async function apiError(res) {
  const body = await res.json().catch(() => ({}));
  if (Array.isArray(body.detail)) return body.detail.map(d => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join("; ");
  return body.detail || `Request failed (${res.status})`;
}

// ---------- loading ----------

async function load() {
  data = await (await fetch("/api/networth/dashboard")).json();
  latestByAccount = new Map();
  for (const v of data.valuations) {            // newest first
    if (!latestByAccount.has(v.account_id)) latestByAccount.set(v.account_id, v);
  }
  renderTiles();
  renderAccounts();
  renderHistoryFilter();
  renderHistory();
  renderSnapshots();
}

// ---------- tiles ----------

function liveTotals() {
  let liquid = 0, illiquid = 0;
  for (const a of data.accounts) {
    const v = latestByAccount.get(a.id);
    if (!a.is_active || !v) continue;
    if (liquidityKind(a.liquidity_status) === "liquid") liquid += Number(v.current_value_chf);
    else illiquid += Number(v.current_value_chf);
  }
  return { liquid, illiquid, total: liquid + illiquid };
}

function renderTiles() {
  const s = data.snapshots[0];
  const prev = data.snapshots[1];
  const live = liveTotals();
  const tiles = [];

  if (s) {
    const total = Number(s.total_networth_chf);
    const change = prev ? total - Number(prev.total_networth_chf) : null;
    const pct = prev && Number(prev.total_networth_chf) ? change / Number(prev.total_networth_chf) * 100 : null;
    const liquidShare = total ? Number(s.total_liquid_chf) / total * 100 : 0;
    tiles.push(`
      <div class="summary-card total">
        <div class="label">Net worth</div>
        <div class="value big">${chf(total, 0)}</div>
        <div class="sub-value">as of ${esc(formatDate(s.snapshot_date))}
          ${change != null ? `<br><span class="change ${change >= 0 ? "up" : "down"}">${signed(change)} (${signed(pct, 1)}%)</span> since ${esc(formatDate(prev.snapshot_date))}` : ""}
        </div>
      </div>
      <div class="summary-card liquid">
        <div class="label">Liquid</div>
        <div class="value">${chf(s.total_liquid_chf, 0)}</div>
        <div class="sub-value">${fmt(liquidShare, 0)}% of net worth</div>
        <div class="share-bar"><span style="width:${liquidShare}%; background:var(--liquid)"></span><span style="width:${100 - liquidShare}%; background:var(--illiquid)"></span></div>
      </div>
      <div class="summary-card illiquid">
        <div class="label">Illiquid</div>
        <div class="value">${chf(s.total_illiquid_chf, 0)}</div>
        <div class="sub-value">${fmt(100 - liquidShare, 0)}% of net worth · pensions, locked savings</div>
      </div>`);
  } else {
    tiles.push(`
      <div class="summary-card total">
        <div class="label">Net worth</div>
        <div class="value big">—</div>
        <div class="sub-value">No snapshot yet: record one to start your trend.</div>
      </div>`);
  }

  const diff = s ? live.total - Number(s.total_networth_chf) : live.total;
  const inSync = s && Math.abs(diff) < 1;
  tiles.push(`
    <div class="summary-card live">
      <div class="label">From latest values</div>
      <div class="value">${chf(live.total, 0)}</div>
      <div class="sub-value">${inSync
        ? "Matches your last snapshot."
        : s ? `<span class="change ${diff >= 0 ? "up" : "down"}">${signed(diff)}</span> not in a snapshot yet.`
            : "Sum of each active account's latest value."}</div>
      ${inSync ? "" : '<div class="tile-action"><button class="secondary" data-action="snapshot">Record snapshot</button></div>'}
    </div>`);

  $("tiles").innerHTML = tiles.join("");
}

$("tiles").addEventListener("click", e => {
  if (e.target.closest('[data-action="snapshot"]')) openSnapshotDialog();
});

// ---------- accounts tab ----------

function renderAccounts() {
  const showInactive = $("showInactive").checked;
  const accounts = data.accounts.filter(a => showInactive || a.is_active);
  $("countAccounts").textContent = data.accounts.filter(a => a.is_active).length;

  const groups = new Map();
  for (const a of accounts) {
    const key = a.institution || "No institution";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }
  const value = a => Number(latestByAccount.get(a.id)?.current_value_chf || 0);
  const grandTotal = accounts.filter(a => a.is_active).reduce((s, a) => s + value(a), 0);
  const ordered = [...groups.entries()]
    .map(([name, list]) => ({ name, list: list.sort((x, y) => value(y) - value(x)), total: list.filter(a => a.is_active).reduce((s, a) => s + value(a), 0) }))
    .sort((x, y) => (x.name === "No institution") - (y.name === "No institution") || y.total - x.total);

  $("accountsBody").innerHTML = ordered.map(g => `
    <tr class="group-row">
      <td colspan="4">${esc(g.name)}<span class="muted">${g.list.length} account${g.list.length === 1 ? "" : "s"}</span></td>
      <td class="num">${chf(g.total, 0)}<span class="as-of">${grandTotal ? fmt(g.total / grandTotal * 100, 0) : 0}% of total</span></td>
      <td></td>
    </tr>
    ${g.list.map(accountRow).join("")}`).join("")
    || `<tr><td colspan="6" class="empty-state">No accounts yet. Add your first one with <strong>Add account</strong>.</td></tr>`;
}

// Inside an institution group, "Interactive Brokers - CSPX" reads as just "CSPX".
function shortName(a) {
  const inst = (a.institution || "").trim();
  if (!inst) return a.account_name;
  const escaped = inst.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rest = a.account_name.replace(new RegExp(`^${escaped}\\s*[-–:]\\s*`, "i"), "").trim();
  return rest || a.account_name;
}

function accountRow(a) {
  const v = latestByAccount.get(a.id);
  const name = shortName(a);
  const showTicker = a.ticker_symbol && a.ticker_symbol.toLowerCase() !== name.toLowerCase();
  const age = v ? daysSince(v.valuation_date) : null;
  const valueCell = v
    ? `<strong>${chf(v.current_value_chf)}</strong>
       <span class="as-of ${age > STALE_DAYS ? "stale" : ""}">${age > STALE_DAYS ? '<i class="fa-solid fa-clock"></i> ' : ""}as of ${esc(formatDate(v.valuation_date))}</span>`
    : '<span class="muted-cell">No value yet</span>';
  return `
    <tr class="${a.is_active ? "" : "inactive"}">
      <td><span class="account-name" title="${esc(a.account_name)}">${esc(name)}</span>${showTicker ? `<span class="ticker">${esc(a.ticker_symbol)}</span>` : ""}
          ${a.currency ? `<span class="as-of">${esc(a.currency)}${a.is_active ? "" : " · inactive"}</span>` : ""}</td>
      <td>${esc(a.asset_category) || '<span class="muted-cell">—</span>'}</td>
      <td>${esc(a.account_type) || '<span class="muted-cell">—</span>'}</td>
      <td>${liquidityPill(a.liquidity_status)}</td>
      <td class="num">${valueCell}</td>
      <td class="col-actions"><div class="actions">
        <button class="icon-btn small" data-action="value" data-id="${a.id}" title="Record new value"><i class="fa-solid fa-arrow-trend-up"></i></button>
        <button class="icon-btn small" data-action="edit" data-id="${a.id}" title="Edit account"><i class="fa-solid fa-pen"></i></button>
        <button class="icon-btn small danger" data-action="delete" data-id="${a.id}" title="Delete account"><i class="fa-solid fa-trash"></i></button>
      </div></td>
    </tr>`;
}

$("showInactive").onchange = renderAccounts;

$("accountsBody").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const account = data.accounts.find(a => a.id === Number(btn.dataset.id));
  if (btn.dataset.action === "value") openValueDialog({ account });
  if (btn.dataset.action === "edit") openAccountDialog(account);
  if (btn.dataset.action === "delete") {
    const n = data.valuations.filter(v => v.account_id === account.id).length;
    if (!confirm(`Delete "${account.account_name}"${n ? ` and its ${n} recorded value${n === 1 ? "" : "s"}` : ""}? This can't be undone.\n\nTip: to keep its history, edit it and untick "Active" instead.`)) return;
    const res = await fetch(`/api/networth/accounts/${account.id}`, { method: "DELETE" });
    if (!res.ok) return alert(await apiError(res));
    load();
  }
});

// ---------- value history tab ----------

function renderHistoryFilter() {
  const sel = $("historyAccountFilter");
  const current = sel.value;
  sel.innerHTML = `<option value="">All accounts</option>` +
    [...data.accounts].sort((a, b) => a.account_name.localeCompare(b.account_name))
      .map(a => `<option value="${a.id}">${esc(a.account_name)}</option>`).join("");
  sel.value = current;
}

function renderHistory() {
  const filter = Number($("historyAccountFilter").value) || null;
  const rows = data.valuations.filter(v => !filter || v.account_id === filter);
  $("countHistory").textContent = data.valuations.length;

  $("historyBody").innerHTML = rows.map(v => {
    const cost = v.quantity != null && v.avg_purchase_price != null ? v.quantity * v.avg_purchase_price : null;
    const unrealized = cost != null && v.current_value_original != null ? v.current_value_original - cost : null;
    const pct = cost ? unrealized / cost * 100 : null;
    const ccy = v.currency || "";
    return `
      <tr>
        <td class="nowrap">${esc(formatDate(v.valuation_date))}</td>
        <td><span class="account-name">${esc(v.account_name)}</span>
            ${v.quantity != null ? `<span class="as-of">${fmt(v.quantity, 4).replace(/\.?0+$/, "")} units${v.current_price != null ? ` × ${fmt(v.current_price)}` : ""}</span>` : ""}</td>
        <td class="num">${v.current_value_original != null ? `${esc(ccy)} ${fmt(v.current_value_original)}` : '<span class="muted-cell">—</span>'}
            ${v.exchange_rate_to_chf != null && ccy !== "CHF" ? `<span class="as-of">rate ${fmt(v.exchange_rate_to_chf, 4)}</span>` : ""}</td>
        <td class="num"><strong>${chf(v.current_value_chf)}</strong></td>
        <td class="num">${unrealized != null
            ? `<span class="change ${unrealized >= 0 ? "up" : "down"}">${signed(pct, 1)}%</span><span class="perf">${signed(unrealized, 2)} ${esc(ccy)} on ${fmt(cost)}</span>`
            : '<span class="muted-cell">—</span>'}</td>
        <td class="num">${Number(v.realized_pnl) ? `<span class="change ${v.realized_pnl >= 0 ? "up" : "down"}">${signed(Number(v.realized_pnl), 2)}</span>` : '<span class="muted-cell">—</span>'}</td>
        <td>${esc(v.note) || '<span class="muted-cell">—</span>'}</td>
        <td class="col-actions"><div class="actions">
          <button class="icon-btn small" data-action="edit" data-id="${v.id}" title="Edit value"><i class="fa-solid fa-pen"></i></button>
          <button class="icon-btn small danger" data-action="delete" data-id="${v.id}" title="Delete value"><i class="fa-solid fa-trash"></i></button>
        </div></td>
      </tr>`;
  }).join("") || `<tr><td colspan="8" class="empty-state">No values recorded yet.</td></tr>`;
}

$("historyAccountFilter").onchange = renderHistory;

$("historyBody").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const v = data.valuations.find(x => x.id === Number(btn.dataset.id));
  if (btn.dataset.action === "edit") openValueDialog({ valuation: v });
  if (btn.dataset.action === "delete") {
    if (!confirm(`Delete the ${formatDate(v.valuation_date)} value of "${v.account_name}" (${chf(v.current_value_chf)})?`)) return;
    const res = await fetch(`/api/networth/valuations/${v.id}`, { method: "DELETE" });
    if (!res.ok) return alert(await apiError(res));
    load();
  }
});

// ---------- snapshots tab ----------

function renderSnapshots() {
  $("countSnapshots").textContent = data.snapshots.length;
  $("snapshotsBody").innerHTML = data.snapshots.map(s => `
    <tr>
      <td class="nowrap">${esc(formatDate(s.snapshot_date))}</td>
      <td class="num"><strong>${chf(s.total_networth_chf, 0)}</strong></td>
      <td class="num">${chf(s.total_liquid_chf, 0)}</td>
      <td class="num">${chf(s.total_illiquid_chf, 0)}</td>
      <td class="num">${s.mom_change_chf == null ? '<span class="muted-cell">first</span>'
        : `<span class="change ${s.mom_change_chf >= 0 ? "up" : "down"}">${signed(Number(s.mom_change_chf))}</span><span class="perf">${signed(Number(s.mom_change_pct), 1)}%</span>`}</td>
      <td>${esc(s.notes) || '<span class="muted-cell">—</span>'}</td>
      <td class="col-actions"><div class="actions">
        <button class="icon-btn small" data-action="edit" data-id="${s.id}" title="Edit snapshot"><i class="fa-solid fa-pen"></i></button>
        <button class="icon-btn small danger" data-action="delete" data-id="${s.id}" title="Delete snapshot"><i class="fa-solid fa-trash"></i></button>
      </div></td>
    </tr>`).join("") || `<tr><td colspan="7" class="empty-state">No snapshots yet. Use <strong>Record snapshot</strong> once your values are up to date.</td></tr>`;
}

$("snapshotsBody").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const s = data.snapshots.find(x => x.id === Number(btn.dataset.id));
  if (btn.dataset.action === "edit") openSnapshotDialog(s);
  if (btn.dataset.action === "delete") {
    if (!confirm(`Delete the ${formatDate(s.snapshot_date)} snapshot (${chf(s.total_networth_chf, 0)})?`)) return;
    const res = await fetch(`/api/networth/snapshots/${s.id}`, { method: "DELETE" });
    if (!res.ok) return alert(await apiError(res));
    load();
  }
});

// ---------- tabs ----------

function showTab(name) {
  document.querySelectorAll(".nw-tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".nw-panel").forEach(p => p.classList.toggle("active", p.id === `panel-${name}`));
  history.replaceState(null, "", `#${name}`);
}
document.querySelectorAll(".nw-tab").forEach(t => t.onclick = () => showTab(t.dataset.tab));

// ---------- dialogs (shared open/close) ----------

function openModal(id) { $(id).style.display = "flex"; }
function closeModal(id) { $(id).style.display = "none"; }
document.querySelectorAll(".modal-overlay").forEach(overlay => {
  overlay.addEventListener("mousedown", e => { if (e.target === overlay) closeModal(overlay.id); });
  overlay.querySelectorAll("[data-close]").forEach(b => b.onclick = () => closeModal(overlay.id));
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".modal-overlay").forEach(o => { if (o.style.display === "flex") closeModal(o.id); });
});

function lookupOptions(items, selectedId, placeholder) {
  // Inactive values stay selectable only for an account that already uses them.
  return `<option value="">${placeholder}</option>` + items
    .filter(x => x.is_active || x.id === selectedId)
    .map(x => `<option value="${x.id}" ${x.id === selectedId ? "selected" : ""}>${esc(x.value)}${x.is_active ? "" : " (inactive)"}</option>`).join("");
}

// ---------- account dialog ----------

let editingAccountId = null;

function openAccountDialog(account = null) {
  editingAccountId = account ? account.id : null;
  const L = data.lookups;
  $("accountTitle").textContent = account ? "Edit account" : "Add account";
  $("accountError").textContent = "";
  $("accName").classList.remove("invalid");
  $("accName").value = account?.account_name || "";
  $("accTicker").value = account?.ticker_symbol || "";
  $("accInstitution").innerHTML = lookupOptions(L.institutions, account?.institution_id ?? null, "— Institution —");
  $("accCategory").innerHTML = lookupOptions(L.asset_categories, account?.asset_category_id ?? null, "— Category —");
  $("accType").innerHTML = lookupOptions(L.account_types, account?.account_type_id ?? null, "— Type —");
  $("accCurrency").innerHTML = lookupOptions(L.currencies, account?.currency_id ?? null, "— Currency —");
  $("accLiquidity").innerHTML = lookupOptions(L.liquidity_statuses, account?.liquidity_status_id ?? null, "— Liquidity —");
  $("accActive").checked = account ? account.is_active : true;
  openModal("accountModal");
  $("accName").focus();
}

$("accountForm").onsubmit = async e => {
  e.preventDefault();
  const name = $("accName").value.trim();
  if (!name) {
    $("accName").classList.add("invalid");
    $("accountError").textContent = "Give the account a name.";
    return;
  }
  const payload = {
    account_name: name,
    ticker_symbol: $("accTicker").value.trim() || null,
    institution_id: Number($("accInstitution").value) || null,
    asset_category_id: Number($("accCategory").value) || null,
    account_type_id: Number($("accType").value) || null,
    currency_id: Number($("accCurrency").value) || null,
    liquidity_status_id: Number($("accLiquidity").value) || null,
    is_active: $("accActive").checked,
  };
  const res = await fetch(editingAccountId ? `/api/networth/accounts/${editingAccountId}` : "/api/networth/accounts", {
    method: editingAccountId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) { $("accountError").textContent = await apiError(res); return; }
  closeModal("accountModal");
  load();
};

$("addAccountBtn").onclick = () => openAccountDialog();

// ---------- value dialog ----------

let editingValuationId = null;
const num = id => { const v = parseFloat($(id).value); return isNaN(v) ? null : v; };

function accountCurrency(accountId) {
  return data.accounts.find(a => a.id === accountId)?.currency || "";
}

function onAccountChanged() {
  const ccy = accountCurrency(Number($("valAccount").value));
  $("valCurrencyLabel").textContent = ccy || "account currency";
  const isChf = ccy === "CHF";
  $("valFxFetch").style.display = ccy && !isChf ? "" : "none";
  if (isChf) { $("valFx").value = 1; recomputeChf(); }
}

function recomputeOriginal() {
  const q = num("valQuantity"), p = num("valPrice");
  if (q != null && p != null) $("valOriginal").value = (q * p).toFixed(2);
  recomputeChf();
}

function recomputeChf() {
  const orig = num("valOriginal"), fx = num("valFx");
  if (orig != null && fx != null) $("valChf").value = (orig * fx).toFixed(2);
  recomputeSummary();
}

function recomputeSummary() {
  const q = num("valQuantity"), avg = num("valAvgPrice"), orig = num("valOriginal");
  const el = $("valSummary");
  if (q == null || avg == null || orig == null) { el.textContent = ""; return; }
  const cost = q * avg, pnl = orig - cost, pct = cost ? pnl / cost * 100 : 0;
  const ccy = accountCurrency(Number($("valAccount").value));
  el.innerHTML = `Cost basis ${fmt(cost)} ${esc(ccy)} · Unrealised P&amp;L <span class="change ${pnl >= 0 ? "up" : "down"}">${signed(pnl, 2)}</span> · Return <span class="change ${pnl >= 0 ? "up" : "down"}">${signed(pct, 1)}%</span>`;
}

["valQuantity", "valPrice"].forEach(id => $(id).addEventListener("input", recomputeOriginal));
["valOriginal", "valFx"].forEach(id => $(id).addEventListener("input", recomputeChf));
$("valAvgPrice").addEventListener("input", recomputeSummary);
$("valAccount").addEventListener("change", onAccountChanged);

$("valFxFetch").onclick = async () => {
  const ccy = accountCurrency(Number($("valAccount").value));
  const day = $("valDate").value || todayLocal();
  const res = await fetch(`/api/fx/rate?from_currency=${encodeURIComponent(ccy)}&to_currency=CHF&on=${day}`);
  if (!res.ok) { $("valueError").textContent = await apiError(res); return; }
  const r = await res.json();
  $("valFx").value = r.rate;
  $("valFx").title = `ECB reference rate of ${r.rate_date}`;
  $("valueError").textContent = "";
  recomputeChf();
};

function openValueDialog({ account = null, valuation = null } = {}) {
  editingValuationId = valuation ? valuation.id : null;
  const accountId = valuation ? valuation.account_id : account?.id;
  const previous = valuation || (accountId ? latestByAccount.get(accountId) : null);

  $("valueTitle").textContent = valuation ? "Edit value" : "Record value";
  $("valueForm").reset();
  $("valueForm").querySelectorAll(".invalid").forEach(x => x.classList.remove("invalid"));
  $("valueError").textContent = "";
  $("valAccount").innerHTML = `<option value="">— Account —</option>` +
    data.accounts.filter(a => a.is_active || a.id === accountId)
      .map(a => `<option value="${a.id}">${esc(a.account_name)}</option>`).join("");
  $("valAccount").value = accountId || "";

  $("valDate").value = valuation ? String(valuation.valuation_date).slice(0, 10) : todayLocal();
  // Holdings and rate carry over from the last value; the value itself is new.
  $("valQuantity").value = previous?.quantity ?? "";
  $("valPrice").value = previous?.current_price ?? "";
  $("valAvgPrice").value = previous?.avg_purchase_price ?? "";
  $("valFx").value = previous?.exchange_rate_to_chf ?? "";
  $("valRealized").value = previous?.realized_pnl ?? "";
  $("valOriginal").value = valuation ? (valuation.current_value_original ?? "") : "";
  $("valChf").value = valuation ? valuation.current_value_chf : "";
  $("valNote").value = valuation?.note || "";

  const latest = accountId ? latestByAccount.get(accountId) : null;
  $("valueHint").textContent = valuation
    ? `Recorded on ${formatDate(valuation.valuation_date)}.`
    : latest ? `Last value: ${chf(latest.current_value_chf)} on ${formatDate(latest.valuation_date)}. Holdings and rate are pre-filled from it.`
             : "First value for this account.";
  onAccountChanged();
  recomputeSummary();
  openModal("valueModal");
  (accountId ? $(previous?.quantity != null ? "valPrice" : "valOriginal") : $("valAccount")).focus();
}

$("valueForm").onsubmit = async e => {
  e.preventDefault();
  const missing = [];
  if (!$("valAccount").value) missing.push("valAccount");
  if (!$("valDate").value) missing.push("valDate");
  if (num("valChf") == null) missing.push("valChf");
  $("valueForm").querySelectorAll(".invalid").forEach(x => x.classList.remove("invalid"));
  if (missing.length) {
    missing.forEach(id => $(id).classList.add("invalid"));
    $("valueError").textContent = "Fill in the account, date and value in CHF.";
    return;
  }
  const payload = {
    account_id: Number($("valAccount").value),
    valuation_date: $("valDate").value,
    quantity: num("valQuantity"),
    avg_purchase_price: num("valAvgPrice"),
    current_price: num("valPrice"),
    current_value_original: num("valOriginal"),
    exchange_rate_to_chf: num("valFx"),
    current_value_chf: num("valChf"),
    realized_pnl: num("valRealized") ?? 0,
    source: "manual",
    note: $("valNote").value.trim() || null,
  };
  const res = await fetch(editingValuationId ? `/api/networth/valuations/${editingValuationId}` : "/api/networth/valuations", {
    method: editingValuationId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) { $("valueError").textContent = await apiError(res); return; }
  closeModal("valueModal");
  load();
};

// ---------- snapshot dialog ----------

let editingSnapshotId = null;

function recomputeSnapshotTotal() {
  const l = num("snapLiquid"), i = num("snapIlliquid");
  $("snapTotal").value = l != null && i != null ? (l + i).toFixed(2) : "";
}
["snapLiquid", "snapIlliquid"].forEach(id => $(id).addEventListener("input", recomputeSnapshotTotal));

async function openSnapshotDialog(snapshot = null) {
  editingSnapshotId = snapshot ? snapshot.id : null;
  $("snapshotTitle").textContent = snapshot ? "Edit snapshot" : "Record snapshot";
  $("snapshotError").textContent = "";
  $("snapshotForm").reset();
  if (snapshot) {
    $("snapDate").value = String(snapshot.snapshot_date).slice(0, 10);
    $("snapLiquid").value = snapshot.total_liquid_chf;
    $("snapIlliquid").value = snapshot.total_illiquid_chf;
    $("snapNotes").value = snapshot.notes || "";
    $("snapshotHint").textContent = "The change vs the previous snapshot is recalculated when you save.";
  } else {
    const res = await fetch("/api/networth/compute-snapshot", { method: "POST" });
    const t = res.ok ? await res.json() : { total_liquid_chf: 0, total_illiquid_chf: 0 };
    $("snapDate").value = todayLocal();
    $("snapLiquid").value = Number(t.total_liquid_chf).toFixed(2);
    $("snapIlliquid").value = Number(t.total_illiquid_chf).toFixed(2);
    const stale = data.accounts.filter(a => a.is_active && latestByAccount.has(a.id)
      && daysSince(latestByAccount.get(a.id).valuation_date) > STALE_DAYS).length;
    $("snapshotHint").textContent = "Totals come from the latest value of each account." +
      (stale ? ` ${stale} account${stale === 1 ? " hasn't" : "s haven't"} been updated in over 2 months.` : "");
  }
  recomputeSnapshotTotal();
  openModal("snapshotModal");
  $("snapDate").focus();
}

$("snapshotForm").onsubmit = async e => {
  e.preventDefault();
  const liquid = num("snapLiquid"), illiquid = num("snapIlliquid");
  if (!$("snapDate").value || liquid == null || illiquid == null) {
    $("snapshotError").textContent = "Fill in the date and both totals.";
    return;
  }
  const payload = {
    snapshot_date: $("snapDate").value,
    total_liquid_chf: liquid,
    total_illiquid_chf: illiquid,
    total_networth_chf: liquid + illiquid,
    notes: $("snapNotes").value.trim() || null,
  };
  const res = await fetch(editingSnapshotId ? `/api/networth/snapshots/${editingSnapshotId}` : "/api/networth/snapshots", {
    method: editingSnapshotId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) { $("snapshotError").textContent = await apiError(res); return; }
  closeModal("snapshotModal");
  load();
};

$("recordSnapshotBtn").onclick = () => openSnapshotDialog();

// ---------- start ----------

showTab(["accounts", "history", "snapshots"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "accounts");
load();
