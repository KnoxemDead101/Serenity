/* Read-only reconciliation: only the Python API computes cents and proposed totals. */
const reconciliationApi = "/serenity-api/reconciliation";
const reconciliationSection = document.getElementById("reconciliation");
const reconciliationWorkspace = document.getElementById("reconciliation-workspace");
const reconciliationForm = document.getElementById("reconciliation-form");
const reconciliationReport = document.getElementById("reconciliation-report");
const reconciliationMessage = document.getElementById("reconciliation-message");
const reconciliationStatus = document.getElementById("reconciliation-status");
let reconciliationSources = [];
let reconciliationAccounts = [];
let reconciliationContainers = [];
let reconciliationInstruments = [];
let reconciliationSpecifications = [];
let reconciliationToken = null;
let reconciliationGeneration = 0;
let reconciliationBusy = false;

// api.js removes the whole main on session loss. Also drop owner data held in memory.
new MutationObserver(() => {
  if (!sessionRecoveryActive) return;
  reconciliationGeneration += 1;
  reconciliationSources = [];
  reconciliationAccounts = [];
  reconciliationContainers = [];
  reconciliationInstruments = [];
  reconciliationSpecifications = [];
  reconciliationToken = null;
}).observe(document.querySelector("main"), { childList: true });

function reconciliationField(labelText, control, hint) {
  const label = document.createElement("label");
  label.append(document.createTextNode(labelText), control);
  if (hint) {
    const small = document.createElement("small");
    small.className = "muted";
    small.textContent = hint;
    label.append(small);
  }
  return label;
}

function reconciliationSelect(name, choices) {
  const select = document.createElement("select");
  select.name = name;
  for (const [value, label] of choices) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = label;
    select.append(option);
  }
  return select;
}

function reconciliationInput(name, type = "text") {
  const input = document.createElement("input");
  input.name = name;
  input.type = type;
  return input;
}

function reconciliationCheck(name, text) {
  const input = reconciliationInput(name, "checkbox");
  return reconciliationField(text, input);
}

function reconciliationChoices(records, empty, label) {
  return [["", empty], ...records.map((record) => [record.id, label(record)])];
}

function renderReconciliationDraft() {
  const sourceHost = document.getElementById("reconciliation-sources");
  const accountHost = document.getElementById("reconciliation-accounts");
  sourceHost.replaceChildren();
  accountHost.replaceChildren();
  if (!reconciliationSources.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No existing Investments. A report can still show the current totals.";
    sourceHost.append(empty);
  }
  for (const source of reconciliationSources) {
    const group = document.createElement("fieldset");
    group.className = "reconciliation-group";
    group.dataset.sourceId = String(source.id);
    if (source.portfolio_id != null) group.dataset.portfolioId = String(source.portfolio_id);
    const legend = document.createElement("legend");
    legend.textContent = `${source.name} (#${source.id})${source.active ? "" : " — inactive"}${source.review_pending ? " — pending review, not counted" : ""}`;
    const summary = document.createElement("p");
    summary.className = "muted";
    summary.textContent = `Original: ${source.quantity} units; entered value ${formatMoney(source.current_value)}; entered basis ${formatMoney(source.cost_basis)}. Ticker ${source.ticker || "not recorded"} is not an identity match.`;
    const fields = document.createElement("div");
    fields.className = "reconciliation-fields";
    let accountChoice;
    if (source.portfolio_id != null) {
      const portfolio = portfolios.find((item) => item.id === source.portfolio_id);
      const notice = document.createElement("p");
      notice.textContent = `Portfolio: ${portfolio?.name || `#${source.portfolio_id}`}. Choose an Account only now, for balance review; it was not required at entry.`;
      fields.append(notice);
      accountChoice = reconciliationSelect("account_id", reconciliationChoices(
        reconciliationAccounts.filter((item) => item.active), "Unresolved — choose an Account to review",
        (item) => `${item.name} (#${item.id})`));
      accountChoice.addEventListener("change", () => {
        for (const member of document.querySelectorAll('#reconciliation-accounts [name="source_id"]')) {
          if (Number(member.value) === source.id)
            member.checked = member.closest("[data-account-id]")?.dataset.accountId === accountChoice.value;
        }
      });
    } else {
      accountChoice = reconciliationSelect("investment_account_id",
        reconciliationChoices(reconciliationContainers, "Unresolved — no existing account link",
          (r) => `${r.name} (#${r.id})${r.active ? "" : " — archived"}`));
      if (source.review_pending && source.investment_account_id != null)
        accountChoice.value = String(source.investment_account_id);
    }
    const instrument = reconciliationSelect("instrument_id",
      reconciliationChoices(reconciliationInstruments, "Unresolved — no instrument",
        (r) => `${r.symbol} · ${r.name} (#${r.id})${r.active ? "" : " — inactive"}`));
    const spec = reconciliationSelect("specification_id", [["", "Unresolved — no exact specification"]]);
    function updateSpecs() {
      const previous = spec.value;
      spec.replaceChildren();
      for (const [value, text] of [["", "Unresolved — no exact specification"],
        ...reconciliationSpecifications.filter((r) => String(r.instrumentId) === instrument.value)
          .map((r) => [r.specification_id, `${r.symbol} · version ${r.version} (spec #${r.specification_id}), ${r.asset_type}, ${r.currency}, tick ${r.tick_size}, point value ${r.point_value}`])]) {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = text;
        spec.append(option);
      }
      spec.value = [...spec.options].some((o) => o.value === previous) ? previous : "";
    }
    instrument.addEventListener("change", updateSpecs);
    fields.append(
      reconciliationField(source.portfolio_id != null ? "Account to review (not a portfolio requirement)" : "Existing account link", accountChoice),
      reconciliationField("Instrument (exact identity)", instrument),
      reconciliationField("Immutable specification (exact version)", spec),
      reconciliationCheck("identity_confirmed", "I checked that the original Investment is this exact instrument and specification."),
      reconciliationField("Beneficial ownership", reconciliationSelect("beneficial_ownership", [
        ["unknown", "Unknown — do not assume ownership"], ["personal", "Personally owned"],
        ["simulation", "Simulation / paper"], ["prop", "Prop account"], ["other", "Other"],
      ]), "A portfolio name does not establish beneficial ownership."),
      reconciliationField("Basis review", reconciliationSelect("basis_status", [
        ["unknown", "Unknown basis"], ["unverified", "Original entered basis — unverified"],
      ]), "Neither choice certifies tax basis."),
      reconciliationCheck("zero_basis_reviewed", "I reviewed the original zero basis, if any (not a verified tax basis)."),
      reconciliationField("Original value as-of date (optional)", reconciliationInput("valuation_as_of", "date"),
        "Leave blank if the original entered value is undated; a date does not refresh its price."),
      reconciliationField("Evidence for dated original value", reconciliationInput("valuation_evidence"),
        "Required if a date is entered; never a quote or conversion."),
    );
    fields.querySelector('[name="valuation_evidence"]').maxLength = 2000;
    group.append(legend, summary, fields);
    sourceHost.append(group);
  }
  for (const account of reconciliationAccounts) {
    const group = document.createElement("fieldset");
    group.className = "reconciliation-group";
    group.dataset.accountId = String(account.id);
    const legend = document.createElement("legend");
    legend.textContent = `${account.name} (#${account.id}) — live ledger ${formatMoney(account.current_balance)}${account.active ? "" : " — inactive"}`;
    const fields = document.createElement("div");
    fields.className = "reconciliation-fields";
    const meaning = reconciliationSelect("balance_meaning", [
      ["unknown", "Unknown — leave unresolved"], ["cash_only", "Cash only"],
      ["combined", "Combined cash and original investment values"],
    ]);
    const evidence = reconciliationInput("evidence");
    evidence.maxLength = 2000;
    const cash = reconciliationInput("cash_cents", "text");
    cash.inputMode = "numeric";
    cash.pattern = "-?[0-9]+";
    const included = document.createElement("div");
    included.className = "reconciliation-members";
    const memberHeading = document.createElement("p");
    memberHeading.textContent = "Complete set of original Investments mapped to this Account (cash-only balances do not include their values):";
    included.append(memberHeading);
    for (const source of reconciliationSources) {
      const check = reconciliationCheck("source_id", `${source.name} (#${source.id})`);
      check.querySelector("input").value = String(source.id);
      included.append(check);
    }
    fields.append(
      reconciliationField("Meaning of existing balance", meaning),
      reconciliationField("Statement or review evidence", evidence, "Explain what the existing ledger balance contains."),
      reconciliationField("Cash portion in integer cents (required for cash-only and combined)", cash,
        "For cash-only, enter the full ledger balance in cents. For combined, enter only its cash portion. For example, 200000 means $2,000.00. No arithmetic is done in this page."),
      included,
      reconciliationCheck("complete", "I attest this is the complete set of original Investments mapped to this Account, whether or not their values are included in its ledger balance."),
    );
    group.append(legend, fields);
    accountHost.append(group);
  }
}

function discardReconciliation() {
  reconciliationGeneration += 1;
  reconciliationToken = null;
  reconciliationSources = [];
  reconciliationAccounts = [];
  reconciliationContainers = [];
  reconciliationInstruments = [];
  reconciliationSpecifications = [];
  reconciliationForm.reset();
  document.getElementById("reconciliation-sources").replaceChildren();
  document.getElementById("reconciliation-accounts").replaceChildren();
  reconciliationReport.hidden = true;
  reconciliationWorkspace.hidden = true;
  reconciliationMessage.hidden = true;
  reconciliationStatus.textContent = "";
  document.getElementById("reconciliation-cancel").hidden = true;
  document.getElementById("reconciliation-start").hidden = false;
}

document.getElementById("reconciliation-cancel").addEventListener("click", discardReconciliation);
document.getElementById("reconciliation-start").addEventListener("click", async () => {
  if (reconciliationBusy || sessionRecoveryActive) return;
  const generation = ++reconciliationGeneration;
  reconciliationBusy = true;
  const start = document.getElementById("reconciliation-start");
  start.disabled = true;
  showMessage(reconciliationMessage, "Loading original records and exact specifications…", false);
  try {
    const [sources, accounts, containers, instruments] = await Promise.all([
      apiGet("/serenity-api/investments"), apiGet("/serenity-api/accounts"),
      apiGet("/serenity-api/investment-accounts"), apiGet("/serenity-api/instruments"),
    ]);
    const specifications = (await Promise.all(instruments.map(async (instrument) =>
      (await apiGet(`/serenity-api/instruments/${instrument.id}/specifications`))
        .map((spec) => ({ ...spec, instrumentId: instrument.id }))
    ))).flat();
    if (sessionRecoveryActive || generation !== reconciliationGeneration) return;
    reconciliationSources = sources;
    reconciliationAccounts = accounts;
    reconciliationContainers = containers;
    reconciliationInstruments = instruments;
    reconciliationSpecifications = specifications;
    renderReconciliationDraft();
    const requested = Number(new URLSearchParams(window.location.search).get("review"));
    if (Number.isSafeInteger(requested) && requested > 0 &&
        sources.some((source) => source.id === requested && source.review_pending)) {
      const chosen = sources.find((source) => source.id === requested);
      const container = containers.find((item) => item.id === chosen.investment_account_id);
      if (container) {
        const account = [...document.querySelectorAll("#reconciliation-accounts [data-account-id]")]
          .find((item) => Number(item.dataset.accountId) === container.account_id);
        const member = account && [...account.querySelectorAll('[name="source_id"]')]
          .find((item) => Number(item.value) === requested);
        if (member) member.checked = true;
      }
    }
    reconciliationWorkspace.hidden = false;
    if (requested > 0 && sources.some((source) => source.id === requested && source.review_pending))
      document.querySelector(`[data-source-id="${requested}"]`)?.scrollIntoView({behavior: "smooth", block: "center"});
    document.getElementById("reconciliation-cancel").hidden = false;
    start.hidden = true;
    reconciliationMessage.hidden = true;
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      showMessage(reconciliationMessage, `Could not load reconciliation: ${error.message}`, true);
  } finally {
    reconciliationBusy = false;
    start.disabled = false;
  }
});

if (new URLSearchParams(window.location.search).has("review"))
  document.getElementById("reconciliation-start").click();

function readReconciliationDraft() {
  const mappings = [...document.querySelectorAll("#reconciliation-sources [data-source-id]")].map((group) => {
    const value = (name) => group.querySelector(`[name="${name}"]`)?.value || "";
    return {
      source_id: Number(group.dataset.sourceId),
      portfolio_id: group.dataset.portfolioId ? Number(group.dataset.portfolioId) : null,
      account_id: value("account_id") ? Number(value("account_id")) : null,
      investment_account_id: value("investment_account_id") ? Number(value("investment_account_id")) : null,
      instrument_id: value("instrument_id") ? Number(value("instrument_id")) : null,
      specification_id: value("specification_id") ? Number(value("specification_id")) : null,
      identity_confirmed: group.querySelector('[name="identity_confirmed"]').checked,
      beneficial_ownership: value("beneficial_ownership"),
      basis_status: value("basis_status"),
      zero_basis_reviewed: group.querySelector('[name="zero_basis_reviewed"]').checked,
      valuation_as_of: value("valuation_as_of") || null,
      valuation_evidence: value("valuation_evidence").trim() || null,
    };
  });
  const accounts = [...document.querySelectorAll("#reconciliation-accounts [data-account-id]")].map((group) => {
    const value = (name) => group.querySelector(`[name="${name}"]`).value;
    const cents = value("cash_cents").trim();
    // Preserve exact integer cents as a JSON number; refuse unsafe or decimal input.
    if (cents && (!/^-?[0-9]+$/.test(cents) || !Number.isSafeInteger(Number(cents))))
      throw new Error(`Account #${group.dataset.accountId}: cash cents must be a safe whole integer.`);
    return {
      account_id: Number(group.dataset.accountId),
      balance_meaning: value("balance_meaning"),
      evidence: value("evidence").trim() || null,
      complete: group.querySelector('[name="complete"]').checked,
      source_ids: [...group.querySelectorAll('[name="source_id"]:checked')].map((check) => Number(check.value)),
      cash_cents: cents ? Number(cents) : null,
    };
  });
  return { mappings, accounts };
}

// Display cents exactly as returned by the backend, without JS financial arithmetic.
function reconciliationMoney(cents) {
  if (cents === null || cents === undefined) return "—";
  const raw = String(cents);
  if (!/^-?\d+$/.test(raw)) return `Invalid backend cents: ${raw}`;
  const negative = raw.startsWith("-");
  const digits = (negative ? raw.slice(1) : raw).padStart(3, "0");
  const whole = digits.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? "−" : ""}$${whole}.${digits.slice(-2)}`;
}

function reconciliationList(id, items) {
  const host = document.getElementById(id);
  host.replaceChildren();
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = typeof item === "string" ? item : JSON.stringify(item);
    host.append(li);
  }
  if (!host.childElementCount) {
    const li = document.createElement("li");
    li.textContent = "None reported.";
    host.append(li);
  }
}

function renderReconciliationReport(report) {
  const labels = [
    ["account_balance_cents", "Account balances"], ["legacy_investment_cents", "Original Investments"],
    ["holding_value_cents", "Preview holdings"], ["debt_balance_cents", "Debts"],
    ["net_worth_cents", "Net worth"],
  ];
  const totals = document.getElementById("reconciliation-totals");
  totals.replaceChildren();
  for (const [key, label] of labels) {
    const row = document.createElement("tr");
    row.append(makeCell(label), makeCell(reconciliationMoney(report.current?.[key]), "num"),
      makeCell(reconciliationMoney(report.proposed?.[key]), "num"));
    totals.append(row);
  }
  document.getElementById("reconciliation-captured").textContent =
    `Captured ${report.captured_at || "unknown time"} · report format ${report.format_version}. Snapshot only.`;
  document.getElementById("reconciliation-delta").textContent =
    `Backend-explained net worth delta (proposed versus current): ${reconciliationMoney(report.delta_cents)}.`;
  const outcomes = document.getElementById("reconciliation-outcomes");
  outcomes.replaceChildren();
  for (const item of report.sources || []) {
    const row = document.createElement("tr");
    row.append(
      makeCell(`${item.source?.name || "Investment"} (#${item.source?.id ?? item.source_id ?? "?"})`),
      makeCell(`${item.outcome || "unresolved"}; ${(item.warnings || []).join("; ") || "No warnings reported"}`),
      makeCell(`Original user-entered value; ${item.valuation?.as_of || "undated"}; ${item.valuation?.evidence || "no dated evidence"}; ${item.valuation?.warning || "Not a live quote."}`),
      makeCell(reconciliationMoney(item.current_value_cents), "num"),
      makeCell(reconciliationMoney(item.proposed_legacy_cents), "num"),
      makeCell(reconciliationMoney(item.proposed_holding_cents), "num"),
      makeCell(`${reconciliationMoney(item.basis_cents)} (${item.basis_status || "unknown"})`),
    );
    outcomes.append(row);
  }
  const accounts = document.getElementById("reconciliation-account-results");
  accounts.replaceChildren();
  for (const item of report.accounts || []) {
    const row = document.createElement("tr");
    row.append(makeCell(`${item.account?.name || item.name || "Account"} (#${item.account?.id ?? item.account_id ?? "?"})`),
      makeCell(reconciliationMoney(item.current_balance_cents), "num"),
      makeCell(reconciliationMoney(item.proposed_balance_cents), "num"),
      makeCell(reconciliationMoney(item.correction_cents), "num"),
      makeCell((item.warnings || []).join("; ") || "None reported"));
    accounts.append(row);
  }
  reconciliationList("reconciliation-explanations", (report.explanations || []).map((item) =>
    typeof item === "string" ? item :
      `Account #${item.account_id}: ${item.reason} Backend correction ${reconciliationMoney(item.delta_cents)}.`));
  reconciliationList("reconciliation-warnings", report.warnings);
  reconciliationStatus.textContent = "Snapshot not yet checked for freshness. Export checks again.";
  reconciliationReport.hidden = false;
}

reconciliationForm.addEventListener("input", () => {
  reconciliationGeneration += 1;
  reconciliationToken = null;
  reconciliationReport.hidden = true;
});
reconciliationForm.addEventListener("change", () => {
  reconciliationGeneration += 1;
  reconciliationToken = null;
  reconciliationReport.hidden = true;
});
reconciliationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (reconciliationBusy || sessionRecoveryActive) return;
  let draft;
  try {
    draft = readReconciliationDraft();
  } catch (error) {
    showMessage(reconciliationMessage, error.message, true);
    return;
  }
  const generation = ++reconciliationGeneration;
  reconciliationBusy = true;
  const button = document.getElementById("reconciliation-preview");
  button.disabled = true;
  reconciliationToken = null;
  reconciliationReport.hidden = true;
  try {
    const response = await apiPost(`${reconciliationApi}/preview`, draft);
    if (sessionRecoveryActive || generation !== reconciliationGeneration) return;
    reconciliationToken = response.report_token;
    renderReconciliationReport(response.report);
    showMessage(reconciliationMessage, "Read-only snapshot created. No live data changed.", false);
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      showMessage(reconciliationMessage, `Preview unavailable: ${error.message}`, true);
  } finally {
    reconciliationBusy = false;
    button.disabled = false;
  }
});

document.getElementById("reconciliation-verify").addEventListener("click", async () => {
  if (!reconciliationToken || reconciliationBusy || sessionRecoveryActive) return;
  const token = reconciliationToken;
  const generation = reconciliationGeneration;
  reconciliationBusy = true;
  try {
    const result = await apiPost(`${reconciliationApi}/verify`, { report_token: token });
    if (sessionRecoveryActive || generation !== reconciliationGeneration || token !== reconciliationToken) return;
    reconciliationStatus.textContent = result.stale
      ? "Stale: financial or reference records changed since capture. Discard and create a new preview; do not use this report."
      : "Signed snapshot verified against current records. It remains read-only and may become stale later.";
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      reconciliationStatus.textContent = `Could not verify report: ${error.message}`;
  } finally {
    reconciliationBusy = false;
  }
});

document.getElementById("reconciliation-export").addEventListener("click", async () => {
  if (!reconciliationToken || reconciliationBusy || sessionRecoveryActive) return;
  const token = reconciliationToken;
  const generation = reconciliationGeneration;
  reconciliationBusy = true;
  try {
    ensureSessionActive();
    const response = await fetch(`${reconciliationApi}/export`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_token: token }),
    });
    if (!response.ok) {
      // The shared handler detects revoked sessions and explains stale 409 responses.
      await handleResponse(response);
      return;
    }
    ensureSessionActive();
    const blob = await response.blob();
    if (sessionRecoveryActive || generation !== reconciliationGeneration || token !== reconciliationToken) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "serenity-reconciliation-signed.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    reconciliationStatus.textContent = "Signed JSON exported from the server. No live records changed.";
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      reconciliationStatus.textContent = `Export refused: ${error.message}. Refresh the preview if stale.`;
  } finally {
    reconciliationBusy = false;
  }
});