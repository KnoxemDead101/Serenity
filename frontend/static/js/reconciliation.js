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

let reconciliationPriorAccounts = [];
let reconciliationToken = null;
let reconciliationGeneration = 0;
let reconciliationBusy = false;

let reconciliationReportData = null;
let conversionApprovalId = null;
let conversionEvidenceId = null;
let conversionReportDigest = null;
let conversionExecutionKey = null;

new MutationObserver(() => {
  if (!sessionRecoveryActive) return;
  reconciliationGeneration += 1;
  reconciliationSources = [];
  reconciliationAccounts = [];
  reconciliationContainers = [];
  reconciliationInstruments = [];
  reconciliationSpecifications = [];
  reconciliationPriorAccounts = [];
  reconciliationToken = null;
  reconciliationReportData = null;
  conversionApprovalId = null;
  conversionEvidenceId = null;
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

function reconciliationSourceIsConverted(source) {
  return Boolean(source.converted || source.is_converted || source.source_read_only ||
    source.read_only || source.has_conversion || source.opening_position_id ||
    source.conversion_approval_id || source.valuation_representation === "opening" ||
    ["converted", "executed"].includes(source.conversion_status) ||
    source.conversion?.state === "executed");
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
    const priorAccount = reconciliationPriorAccounts.find((account) =>
      (account.source_ids || []).includes(source.id));
    const converted = reconciliationSourceIsConverted(source) || Boolean(priorAccount);
    const legend = document.createElement("legend");
    legend.textContent = `${source.name} (#${source.id})${source.active ? "" : " — inactive"}${converted ? " — conversion retained, read-only original" : source.review_pending ? " — pending review, not counted" : ""}`;
    const summary = document.createElement("p");
    summary.className = "muted";
    summary.textContent = `Original: ${source.quantity} units; entered value ${formatMoney(source.current_value)}; entered basis ${formatMoney(source.cost_basis)}. Ticker ${source.ticker || "not recorded"} is not an identity match.`;
    if (priorAccount || converted) {
      group.dataset.conversionHistory = "true";
      const retained = document.createElement("p");
      retained.className = "muted";
      retained.textContent = priorAccount
        ? `Retained conversion source in Account #${priorAccount.account_id}. This source cannot be converted again. Include it in that Account's complete source declaration; its prior opening and cash correction references are reviewed below.`
        : "The backend marks this as a conversion-retained original. It is read-only and cannot be converted again; prior Account/opening/cash evidence is unavailable in this review context.";
      group.append(legend, summary, retained);
      sourceHost.append(group);
      continue;
    }
    const fields = document.createElement("div");
    fields.className = "reconciliation-fields";
    let accountChoice;
    let conversionTargetChoice = null;
    if (source.portfolio_id != null) {
      const portfolio = portfolios.find((item) => Number(item.id) === Number(source.portfolio_id));
      const notice = document.createElement("p");
      notice.textContent = `Portfolio: ${portfolio?.name || `#${source.portfolio_id}`}. Choose an Account only now, for balance review; it was not required at entry.`;
      fields.append(notice);
      accountChoice = reconciliationSelect("account_id", reconciliationChoices(
        reconciliationAccounts.filter((item) => item.active), "Unresolved — choose an Account to review",
        (item) => `${item.name} (#${item.id})`));
      const preselectedContainer = reconciliationContainers.find((item) =>
        String(item.id) === String(source.investment_account_id));
      if (source.account_id != null) accountChoice.value = String(source.account_id);
      else if (preselectedContainer) accountChoice.value = String(preselectedContainer.account_id);
      const portfolioLinks = reconciliationContainers.filter((container) =>
        Number(container.portfolio_id) === Number(source.portfolio_id));
      conversionTargetChoice = reconciliationSelect("conversion_target_id", [
        ["", "No conversion target selected — preview only"],
      ]);
      function updateConversionTargets() {
        const previous = conversionTargetChoice.value;
        const accountId = accountChoice.value;
        conversionTargetChoice.replaceChildren(new Option(
          "No conversion target selected — preview only", "",
        ));
        for (const container of portfolioLinks.filter((item) =>
          String(item.account_id) === accountId)) {
          conversionTargetChoice.add(new Option(
            `${container.name} (#${container.id})${container.active ? "" : " — archived"}`,
            String(container.id),
          ));
        }
        conversionTargetChoice.value = [...conversionTargetChoice.options]
          .some((option) => option.value === previous) ? previous : "";
        conversionTargetChoice.disabled = !accountId ||
          ![...conversionTargetChoice.options].some((option) => option.value);
      }
      accountChoice.addEventListener("change", () => {
        for (const member of document.querySelectorAll('#reconciliation-accounts [name="source_id"]')) {
          if (Number(member.value) === source.id)
            member.checked = member.closest("[data-account-id]")?.dataset.accountId === accountChoice.value;
        }
        updateConversionTargets();
      });
      updateConversionTargets();
      if (preselectedContainer && [...conversionTargetChoice.options].some((option) =>
        option.value === String(preselectedContainer.id)))
        conversionTargetChoice.value = String(preselectedContainer.id);
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
      ...(conversionTargetChoice ? [reconciliationField(
        "Optional conversion target — required for execution only",
        conversionTargetChoice,
        "Choose only an existing InvestmentAccount link for this same portfolio and Account. Read-only previews do not require one; execution never creates a link silently.",
      )] : []),
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
    const priorAccount = reconciliationPriorAccounts.find((row) => row.account_id === account.id);
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
    if (priorAccount) {
      const history = document.createElement("p");
      history.className = "muted";
      history.textContent = `Prior opening IDs: ${priorAccount.opening_position_ids.join(", ") || "none"}; cash entry IDs: ${priorAccount.cash_entry_ids.join(", ") || "none"}; prior net cash correction ${reconciliationMoney(priorAccount.previous_correction_cents)}. Previously converted holdings are already counted separately, never subtracted from cash again. For combined balances, the cash reconciliation covers only newly mapped legacy values. A reversed prior source blocks this account group.`;
      fields.append(history, reconciliationCheck("prior_conversion_complete",
        "I reviewed every prior opening and cash entry listed above, included every prior source in this Account's complete source set, and confirm its current ledger excludes the already converted securities."));
    }
    group.append(legend, fields);
    accountHost.append(group);
  }
}

function discardReconciliation() {
  reconciliationGeneration += 1;
  reconciliationToken = null;
  reconciliationReportData = null;
  conversionApprovalId = null;
  conversionEvidenceId = null;
  conversionReportDigest = null;
  reconciliationSources = [];
  reconciliationAccounts = [];
  reconciliationContainers = [];
  reconciliationInstruments = [];
  reconciliationSpecifications = [];
  reconciliationPriorAccounts = [];
  reconciliationForm.reset();
  document.getElementById("reconciliation-sources").replaceChildren();
  document.getElementById("reconciliation-accounts").replaceChildren();
  reconciliationReport.hidden = true;
  reconciliationWorkspace.hidden = true;
  reconciliationMessage.hidden = true;
  reconciliationStatus.textContent = "";
  document.getElementById("conversion-approval").hidden = true;
  document.getElementById("conversion-execution").hidden = true;
  document.getElementById("conversion-evidence").hidden = true;
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
    const [sources, accounts, containers, instruments, prior] = await Promise.all([
      apiGet("/serenity-api/investments"), apiGet("/serenity-api/accounts"),
      apiGet("/serenity-api/investment-accounts"), apiGet("/serenity-api/instruments"),
      apiGet("/serenity-api/conversions/review-context"),
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
    reconciliationPriorAccounts = prior.accounts || [];
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
    if (Number.isSafeInteger(requested) && requested > 0 &&
        sources.some((source) => source.id === requested && source.review_pending))
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

function collectReconciliationDraft(requestMode = "read-only") {
  const mappings = [...document.querySelectorAll("#reconciliation-sources [data-source-id]:not([data-conversion-history])")].map((group) => {
    const value = (name) => group.querySelector(`[name="${name}"]`)?.value || "";
    const portfolioId = group.dataset.portfolioId ? Number(group.dataset.portfolioId) : null;
    const accountId = value("account_id") ? Number(value("account_id")) : null;
    const targetId = value("conversion_target_id") ? Number(value("conversion_target_id")) : null;
    const mapping = {
      source_id: Number(group.dataset.sourceId),
      portfolio_id: portfolioId,
      account_id: accountId,
      instrument_id: value("instrument_id") ? Number(value("instrument_id")) : null,
      specification_id: value("specification_id") ? Number(value("specification_id")) : null,
      identity_confirmed: group.querySelector('[name="identity_confirmed"]').checked,
      beneficial_ownership: value("beneficial_ownership"),
      basis_status: value("basis_status"),
      zero_basis_reviewed: group.querySelector('[name="zero_basis_reviewed"]').checked,
      valuation_as_of: value("valuation_as_of") || null,
      valuation_evidence: value("valuation_evidence").trim() || null,
    };
    if (portfolioId === null) {
      mapping.investment_account_id = value("investment_account_id")
        ? Number(value("investment_account_id")) : null;
    } else if (requestMode === "execution") {
      const target = reconciliationContainers.find((container) =>
        Number(container.id) === targetId);
      if (!accountId || !target ||
          Number(target.portfolio_id) !== portfolioId ||
          Number(target.account_id) !== accountId) {
        throw new Error(`Investment #${mapping.source_id}: execution preview requires an existing InvestmentAccount link for its selected portfolio and Account.`);
      }
      mapping.investment_account_id = targetId;
    }
    return mapping;
  });
  const accounts = [...document.querySelectorAll("#reconciliation-accounts [data-account-id]")].map((group) => {
    const value = (name) => group.querySelector(`[name="${name}"]`).value;
    const cents = value("cash_cents").trim();
    const priorAccount = reconciliationPriorAccounts.find((row) =>
      row.account_id === Number(group.dataset.accountId));
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
      prior_conversion_complete: group.querySelector('[name="prior_conversion_complete"]')?.checked || false,
      prior_opening_position_ids: priorAccount?.opening_position_ids || [],
      prior_cash_entry_ids: priorAccount?.cash_entry_ids || [],
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
  reconciliationReportData = report;
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
  renderConversionApprovalChoices(report);
}

function conversionDigest(report) {
  return conversionReportDigest || report?.report_sha256 || report?.report_digest ||
    report?.digest || report?.sha256 || null;
}

function conversionAccountId(report, mapping) {
  const directId = Number(mapping?.account_id);
  if (Number.isSafeInteger(directId) && directId > 0) return directId;
  const containerId = Number(mapping?.investment_account_id);
  const container = (report?.dependencies?.investment_accounts || []).find((item) =>
    Number(item.id) === containerId);
  const accountId = Number(container?.account_id);
  return Number.isSafeInteger(accountId) && accountId > 0 ? accountId : null;
}

function showConversionError(target, action, error) {
  const detail = error?.message || String(error);
  showMessage(target, `${action} refused: ${detail}. If this is stale or conflicts with dependent activity, stop and obtain a fresh report or separately approved corrective plan.`, true);
}

function cancelConversionApproval() {
  document.getElementById("conversion-approval-confirm").checked = false;
  document.getElementById("conversion-backup-reference").value = "";
  document.getElementById("conversion-backup-cutoff").value = "";
  document.getElementById("conversion-rollback-deadline").value = "";
  document.querySelectorAll('#conversion-record-confirmations input[type="checkbox"]').forEach((input) => {
    input.checked = false;
  });
  document.getElementById("conversion-approval-message").hidden = true;
}

async function refreshConversionEvidence(id) {
  ensureSessionActive();
  const response = await fetch(`/serenity-api/conversions/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  const evidence = await handleResponse(response);
  if (sessionRecoveryActive || String(id) !== String(conversionEvidenceId)) return;
  renderConversionEvidence(evidence);
}

function appendEvidenceField(host, label, value) {
  const row = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = `${label}: `;
  row.append(strong, document.createTextNode(
    value === null || value === undefined || value === "" ? "—" :
      typeof value === "string" ? value : JSON.stringify(value)
  ));
  host.append(row);
}

async function createReconciliationPreview(executable, button) {
  if (reconciliationBusy || sessionRecoveryActive) return;
  let draft;
  try {
    draft = collectReconciliationDraft(executable ? "execution" : "read-only");
  } catch (error) {
    showMessage(reconciliationMessage, error.message, true);
    return;
  }
  const generation = ++reconciliationGeneration;
  reconciliationBusy = true;
  button.disabled = true;
  reconciliationToken = null;
  conversionReportDigest = null;
  reconciliationReport.hidden = true;
  try {
    const endpoint = executable ? "execution-preview" : "preview";
    const response = await apiPost(`${reconciliationApi}/${endpoint}`, draft);
    if (sessionRecoveryActive || generation !== reconciliationGeneration) return;
    reconciliationToken = response.report_token;
    if (executable && response.report?.format_version === 2 && response.report?.executable === true) {
      conversionReportDigest = await reportSha256FromToken(response.report_token);
    }
    if (sessionRecoveryActive || generation !== reconciliationGeneration) return;
    renderReconciliationReport(response.report);
    showMessage(reconciliationMessage,
      executable
        ? "Execution-capable report created for review. No live data changed; approval and execution remain separate owner actions."
        : "Read-only snapshot created. No live data changed.",
      false);
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      showMessage(reconciliationMessage, `${executable ? "Execution preview" : "Preview"} unavailable: ${error.message}`, true);
  } finally {
    reconciliationBusy = false;
    button.disabled = false;
  }
}

function newConversionIdempotencyKey() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  if (typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
  }
  // This key binds retries; it is not an authorization secret. Older/insecure
  // test and embedded contexts may expose no Web Crypto APIs.
  return `conversion-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function renderConversionEvidence(evidence) {
  const host = document.getElementById("conversion-evidence-details");
  host.replaceChildren();
  const approval = evidence.approval || evidence;
  const events = evidence.events || [];
  const event = events.length ? events[events.length - 1] :
    (evidence.execution_event || evidence.event || evidence.execution || {});
  appendEvidenceField(host, "Approval ID", approval.id ?? conversionEvidenceId);
  appendEvidenceField(host, "Report SHA-256", approval.report_sha256 || approval.report_digest || approval.digest);
  appendEvidenceField(host, "Report / algorithm version",
    [approval.report_format_version || approval.format_version,
      approval.algorithm_version].filter(Boolean).join(" / "));
  appendEvidenceField(host, "State", approval.state);
  appendEvidenceField(host, "Approved by / at",
    [approval.approved_by || approval.actor, approval.approved_at].filter(Boolean).join(" · "));
  appendEvidenceField(host, "Preview cutoff / source fingerprint",
    [approval.preview_cutoff || approval.cutoff, approval.source_fingerprint].filter(Boolean).join(" · "));
  appendEvidenceField(host, "Rollback deadline", approval.rollback_deadline);
  appendEvidenceField(host, "Backup evidence reference", approval.backup_evidence_reference || approval.backup_evidence_ref);
  appendEvidenceField(host, "Latest event / kind", `${event.event_id ?? event.id ?? "—"} / ${event.event_kind || "—"}`);
  appendEvidenceField(host, "Executed / reversed at", approval.executed_at || approval.reversed_at);
  appendEvidenceField(host, "Before totals", event.before_totals || event.before || evidence.before_totals);
  appendEvidenceField(host, "After totals", event.after_totals || event.after || evidence.after_totals);
  appendEvidenceField(host, "Linked IDs", event.linked_ids || evidence.linked_ids);
  appendEvidenceField(host, "Cash correction entries", evidence.cash_entries || evidence.cash_reconciliation_entries);
  appendEvidenceField(host, "Eligibility / opening positions", evidence.eligibility || evidence.opening_positions);
  appendEvidenceField(host, "Warnings / reversal blockers", evidence.warnings || evidence.reversal_blockers);
  appendEvidenceField(host, "Conversion event history",
    events.map((row) => ({
      event_id: row.event_id, event_kind: row.event_kind, before_totals: row.before_totals,
      after_totals: row.after_totals, linked_ids: row.linked_ids, reason: row.reason,
    })));
  if (approval.report || evidence.report) {
    const reportHeading = document.createElement("h5");
    reportHeading.textContent = "Immutable owner-private approved report";
    const report = document.createElement("pre");
    report.className = "evidence-record";
    report.textContent = JSON.stringify(approval.report || evidence.report, null, 2);
    host.append(reportHeading, report);
  }
  const sources = evidence.sources || evidence.opening_positions || [];
  if (Array.isArray(sources) && sources.length) {
    const heading = document.createElement("h5");
    heading.textContent = "Converted source records — retained, read-only snapshots";
    host.append(heading);
    for (const source of sources) {
      const detail = document.createElement("pre");
      detail.className = "evidence-record";
      detail.textContent = JSON.stringify(source.source_snapshot || source.snapshot || source, null, 2);
      host.append(detail);
    }
  }
  const reversed = approval.state === "reversed" || events.some((row) => row.event_kind === "reversed");
  const executed = approval.state === "executed" || event.id || event.event_id;
  document.getElementById("conversion-reverse").disabled = !executed || Boolean(reversed);
  document.getElementById("conversion-reversal-confirm").checked = false;
  document.getElementById("conversion-reversal-reason").value = "";
}

function selectedConversionPayload() {
  const sourceIds = [...document.querySelectorAll('#conversion-record-confirmations [name="approved_source_id"]:checked')]
    .map((check) => Number(check.value));
  const selectedAccounts = [...document.querySelectorAll('#conversion-record-confirmations [name="approved_account_id"]:checked')];
  if (!sourceIds.length) throw new Error("Select at least one exact eligible source record, or cancel with no changes.");
  const requiredSourceIds = (reconciliationReportData.sources || [])
    .filter((item) => item.outcome === "eligible")
    .map((item) => Number(item.source?.id ?? item.source_id)).sort((a,b) => a-b);
  if (sourceIds.slice().sort((a,b) => a-b).join(",") !== requiredSourceIds.join(","))
    throw new Error("The server requires approval of the exact complete eligible source set. Confirm every eligible source record; do not select a subset.");
  const requiredAccountIds = [...new Set((reconciliationReportData.sources || [])
    .filter((item) => item.outcome === "eligible")
    .map((item) => conversionAccountId(reconciliationReportData, item.mapping))
    .filter((id) => id !== null))].sort((a,b) => a-b);
  const selectedAccountIds = selectedAccounts.map((check) => Number(check.value)).sort((a,b) => a-b);
  if (!requiredAccountIds.length ||
      selectedAccountIds.join(",") !== requiredAccountIds.join(","))
    throw new Error("Confirm the exact correction, including zero-cent corrections, for every account affected by the selected source set.");
  const accountCorrections = {};
  for (const check of selectedAccounts) {
    const accountId = Number(check.value);
    const result = (reconciliationReportData.accounts || []).find((item) =>
      Number(item.account?.id ?? item.account_id) === accountId);
    const cents = result?.correction_cents;
    if (!Number.isSafeInteger(cents)) {
      throw new Error(`Account #${accountId}: exact correction is unavailable as a safe integer cents value. Approval is blocked.`);
    }
    accountCorrections[String(accountId)] = cents;
  }
  return { sourceIds, accountCorrections };
}

function renderConversionApprovalChoices(report) {
  const approval = document.getElementById("conversion-approval");
  const host = document.getElementById("conversion-record-confirmations");
  const readiness = document.getElementById("conversion-readiness");
  host.replaceChildren();
  document.getElementById("conversion-approval-confirm").checked = false;
  document.getElementById("conversion-backup-reference").value = "";
  document.getElementById("conversion-backup-cutoff").value = "";
  document.getElementById("conversion-rollback-deadline").value = "";
  document.getElementById("conversion-approval-message").hidden = true;
  document.getElementById("conversion-execution").hidden = true;
  document.getElementById("conversion-evidence").hidden = true;
  conversionApprovalId = null;
  conversionEvidenceId = null;
  conversionExecutionKey = null;
  conversionReportDigest = conversionDigest(report);
  if (!conversionIsExecutable(report)) {
    approval.hidden = false;
    readiness.textContent = "Approval disabled: this is a read-only report format or the execution report digest is unavailable. Create a supported execution-capable report; a signed format-1 preview cannot be approved or executed.";
    document.getElementById("conversion-approve").disabled = true;
    return;
  }
  readiness.textContent = `Execution-capable report digest: ${conversionReportDigest}. Select each exact record and correction you are approving. Approval will store this report only and will not execute.`;
  document.getElementById("conversion-approve").disabled = false;
  const sources = (report.sources || []).filter((item) =>
    item.outcome === "eligible" && item.source?.active !== false &&
    item.mapping?.beneficial_ownership === "personal" &&
    (item.source?.id ?? item.source_id) !== null &&
    (item.source?.id ?? item.source_id) !== undefined);
  const sourceHeading = document.createElement("h5");
  sourceHeading.textContent = "Exact eligible personal source records";
  host.append(sourceHeading);
  if (!sources.length) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "No source is explicitly eligible and personally owned in this report.";
    host.append(note);
  }
  for (const item of sources) {
    const source = item.source || {};
    const name = `${source.name || "Investment"} (#${source.id ?? item.source_id ?? "?"})`;
    const detail = `Original ${reconciliationMoney(item.current_value_cents)}; proposed holding ${reconciliationMoney(item.proposed_holding_cents)}; basis ${reconciliationMoney(item.basis_cents)} (${item.basis_status || "unknown"}); warnings: ${(item.warnings || []).join("; ") || "none reported"}`;
    host.append(conversionCheckLabel(`${name} — ${detail}`, "approved_source_id",
      source.id ?? item.source_id));
  }
  const affectedAccountIds = new Set(sources.map((item) =>
    conversionAccountId(report, item.mapping)).filter((id) => id !== null));
  const accounts = (report.accounts || []).filter((item) =>
    affectedAccountIds.has(Number(item.account?.id ?? item.account_id)));
  const accountHeading = document.createElement("h5");
  accountHeading.textContent = "Exact account correction amounts";
  host.append(accountHeading);
  if (!accounts.length || accounts.length !== affectedAccountIds.size) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "The execution report does not contain every account affected by eligible source records. Approval is unavailable until this is resolved.";
    host.append(note);
  }
  for (const item of accounts) {
    const account = item.account || {};
    const id = account.id ?? item.account_id;
    const cents = item.correction_cents;
    const text = `${account.name || item.name || "Account"} (#${id}) — exact correction ${reconciliationMoney(cents)}; current ${reconciliationMoney(item.current_balance_cents)}, proposed ${reconciliationMoney(item.proposed_balance_cents)}; warnings: ${(item.warnings || []).join("; ") || "none reported"}`;
    host.append(conversionCheckLabel(text, "approved_account_id", id));
  }
  approval.hidden = false;
}

function conversionApiPost(url, body) {
  ensureSessionActive();
  return fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handleResponse);
}

function conversionCheckLabel(text, name, value) {
  const label = document.createElement("label");
  label.className = "conversion-choice";
  const check = document.createElement("input");
  check.type = "checkbox";
  check.name = name;
  check.value = String(value);
  label.append(check, document.createTextNode(text));
  return label;
}

async function reportSha256FromToken(token) {
  const encoded = token.split(".")[0];
  const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/").padEnd(
    Math.ceil(encoded.length / 4) * 4, "="
  );
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (window.crypto?.subtle) {
    const hash = await window.crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(hash)].map((value) => value.toString(16).padStart(2, "0")).join("");
  }
  return sha256Fallback(bytes);
}

function conversionIsExecutable(report) {
  const version = Number(report?.execution_format_version || report?.format_version || 0);
  return report?.executable === true && version === 2 && Boolean(conversionDigest(report));
}

function sha256Fallback(bytes) {
  const constants = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
  ];
  const state = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const bitLength = bytes.length * 8;
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000));
  view.setUint32(paddedLength - 4, bitLength >>> 0);
  const words = new Uint32Array(64);
  const rotate = (value, amount) => (value >>> amount) | (value << (32 - amount));
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1)
      words[index] = view.getUint32(offset + index * 4);
    for (let index = 16; index < 64; index += 1) {
      const a = words[index - 15], b = words[index - 2];
      const s0 = rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3);
      const s1 = rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10);
      words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,h] = state;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + sum1 + choice + constants[index] + words[index]) >>> 0;
      const sum0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sum0 + majority) >>> 0;
      [h,g,f,e,d,c,b,a] = [g,f,e,(d + temp1) >>> 0,c,b,a,(temp1 + temp2) >>> 0];
    }
    state[0]=(state[0]+a)>>>0; state[1]=(state[1]+b)>>>0;
    state[2]=(state[2]+c)>>>0; state[3]=(state[3]+d)>>>0;
    state[4]=(state[4]+e)>>>0; state[5]=(state[5]+f)>>>0;
    state[6]=(state[6]+g)>>>0; state[7]=(state[7]+h)>>>0;
  }
  return state.map((value) => value.toString(16).padStart(8, "0")).join("");
}

function invalidateReconciliationReport() {
  reconciliationGeneration += 1;
  reconciliationToken = null;
  reconciliationReportData = null;
  conversionReportDigest = null;
  document.getElementById("conversion-approval").hidden = true;
  document.getElementById("conversion-execution").hidden = true;
  document.getElementById("conversion-evidence").hidden = true;
  reconciliationReport.hidden = true;
}

reconciliationForm.addEventListener("input", invalidateReconciliationReport);
reconciliationForm.addEventListener("change", invalidateReconciliationReport);

reconciliationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  createReconciliationPreview(false, document.getElementById("reconciliation-preview"));
});

document.getElementById("reconciliation-execution-preview").addEventListener("click", () =>
  createReconciliationPreview(true, document.getElementById("reconciliation-execution-preview"))
);

document.getElementById("reconciliation-verify").addEventListener("click", async () => {
  if (!reconciliationToken || reconciliationBusy || sessionRecoveryActive) return;
  const token = reconciliationToken;
  const generation = reconciliationGeneration;
  reconciliationBusy = true;
  try {
    const result = await conversionApiPost(`${reconciliationApi}/verify`, { report_token: token });
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
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_token: token }),
    });
    if (!response.ok) {
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

document.getElementById("conversion-cancel-approval").addEventListener("click", cancelConversionApproval);

document.getElementById("conversion-approve").addEventListener("click", async () => {
  const button = document.getElementById("conversion-approve");
  const message = document.getElementById("conversion-approval-message");
  if (reconciliationBusy || sessionRecoveryActive || !reconciliationToken ||
      !reconciliationReportData || !conversionIsExecutable(reconciliationReportData)) return;
  let selection;
  let backupCutoff;
  let rollbackDeadline;
  const backupReference = document.getElementById("conversion-backup-reference").value.trim();
  const cutoffInput = document.getElementById("conversion-backup-cutoff").value;
  const deadlineInput = document.getElementById("conversion-rollback-deadline").value;
  try {
    selection = selectedConversionPayload();
    if (!document.getElementById("conversion-approval-confirm").checked)
      throw new Error("Explicit owner approval confirmation is required.");
    if (!backupReference) throw new Error("A private backup evidence reference is required.");
    if (!cutoffInput || !Number.isFinite(Date.parse(cutoffInput)))
      throw new Error("Enter the observed backup evidence cutoff.");
    if (!deadlineInput || !Number.isFinite(Date.parse(deadlineInput)))
      throw new Error("Enter a valid approved rollback deadline.");
    backupCutoff = new Date(cutoffInput).toISOString();
    rollbackDeadline = new Date(deadlineInput).toISOString();
  } catch (error) {
    showMessage(message, error.message, true);
    return;
  }
  const token = reconciliationToken;
  const generation = reconciliationGeneration;
  reconciliationBusy = true;
  button.disabled = true;
  try {
    const verification = await conversionApiPost(`${reconciliationApi}/verify`, { report_token: token });
    if (sessionRecoveryActive || generation !== reconciliationGeneration || token !== reconciliationToken) return;
    if (verification.stale || verification.valid !== true) {
      reconciliationStatus.textContent = "Stale or unverified: discard this report and create a fresh preview. No approval was stored.";
      document.getElementById("conversion-approval").hidden = true;
      return;
    }
    const response = await conversionApiPost("/serenity-api/conversions/approvals", {
      report_token: token,
      report_sha256: conversionReportDigest,
      selected_source_ids: selection.sourceIds,
      account_corrections_cents: selection.accountCorrections,
      backup_evidence_reference: backupReference,
      backup_cutoff: backupCutoff,
      rollback_deadline: rollbackDeadline,
      confirm_approval: true,
    });
    if (sessionRecoveryActive || generation !== reconciliationGeneration || token !== reconciliationToken) return;
    conversionApprovalId = response.approval_id ?? response.id;
    if (conversionApprovalId === null || conversionApprovalId === undefined)
      throw new Error("The server response did not include an approval ID. Do not assume an approval exists; refresh and inspect owner evidence.");
    conversionExecutionKey = newConversionIdempotencyKey();
    document.getElementById("conversion-approval-summary").textContent =
      `Approval ${conversionApprovalId} · SHA-256 ${response.report_sha256} · state ${response.state || "approved"}. This stores approval only; no conversion has executed.`;
    document.getElementById("conversion-execution-id").value = "";
    document.getElementById("conversion-execution-confirm").checked = false;
    document.getElementById("conversion-execution").hidden = false;
    conversionEvidenceId = conversionApprovalId;
    document.getElementById("conversion-evidence").hidden = false;
    cancelConversionApproval();
    showMessage(message, `Approval ${conversionApprovalId} stored. No conversion was executed. Execution requires a separate confirmation below.`, false);
    await refreshConversionEvidence(conversionEvidenceId).catch((error) => {
      showConversionError(document.getElementById("conversion-evidence-message"), "Evidence load", error);
    });
  } catch (error) {
    if (!sessionRecoveryActive && generation === reconciliationGeneration)
      showConversionError(message, "Approval", error);
  } finally {
    reconciliationBusy = false;
    button.disabled = false;
  }
});
document.getElementById("conversion-execution-cancel").addEventListener("click", () => {
  document.getElementById("conversion-execution-confirm").checked = false;
  document.getElementById("conversion-execution-id").value = "";
  document.getElementById("conversion-execution-message").hidden = true;
});

document.getElementById("conversion-execute").addEventListener("click", async () => {
  const button = document.getElementById("conversion-execute");
  const message = document.getElementById("conversion-execution-message");
  const typedId = document.getElementById("conversion-execution-id").value.trim();
  if (reconciliationBusy || sessionRecoveryActive || !conversionApprovalId) return;
  if (!document.getElementById("conversion-execution-confirm").checked ||
      typedId !== String(conversionApprovalId)) {
    showMessage(message, "Execution requires the separate confirmation checkbox and the exact approval ID.", true);
    return;
  }
  reconciliationBusy = true;
  button.disabled = true;
  try {
    const result = await conversionApiPost(
      `/serenity-api/conversions/${encodeURIComponent(conversionApprovalId)}/execute`,
      { idempotency_key: conversionExecutionKey, confirm_execute: true },
    );
    if (sessionRecoveryActive) return;
    document.getElementById("conversion-execution").hidden = true;
    document.getElementById("conversion-execution-confirm").checked = false;
    conversionEvidenceId = conversionApprovalId;
    document.getElementById("conversion-evidence").hidden = false;
    showMessage(message, "Server reported execution committed. Refreshing owner-private evidence and before/after proof…", false);
    try {
      await refreshConversionEvidence(conversionEvidenceId);
    } catch (error) {
      renderConversionEvidence({ approval: { id: conversionApprovalId, state: "executed" }, execution_event: result });
      showConversionError(document.getElementById("conversion-evidence-message"), "Evidence refresh", error);
    }
  } catch (error) {
    if (!sessionRecoveryActive) showConversionError(message, "Execution", error);
  } finally {
    reconciliationBusy = false;
    button.disabled = false;
  }
});

document.getElementById("conversion-refresh-evidence").addEventListener("click", async () => {
  const message = document.getElementById("conversion-evidence-message");
  if (!conversionEvidenceId || reconciliationBusy || sessionRecoveryActive) return;
  reconciliationBusy = true;
  try {
    await refreshConversionEvidence(conversionEvidenceId);
    showMessage(message, "Owner-private evidence refreshed from the server.", false);
  } catch (error) {
    if (!sessionRecoveryActive) showConversionError(message, "Evidence refresh", error);
  } finally {
    reconciliationBusy = false;
  }
});

document.getElementById("conversion-export-evidence").addEventListener("click", async () => {
  const message = document.getElementById("conversion-evidence-message");
  if (!conversionEvidenceId || reconciliationBusy || sessionRecoveryActive) return;
  const id = conversionEvidenceId;
  reconciliationBusy = true;
  try {
    ensureSessionActive();
    const response = await fetch(`/serenity-api/conversions/${encodeURIComponent(id)}/evidence`, {
      cache: "no-store",
    });
    if (!response.ok) {
      await handleResponse(response);
      return;
    }
    ensureSessionActive();
    const blob = await response.blob();
    if (sessionRecoveryActive || id !== conversionEvidenceId) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `serenity-conversion-${id}-evidence.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    showMessage(message, "Owner-private conversion evidence exported. This download does not execute or reverse a conversion.", false);
  } catch (error) {
    if (!sessionRecoveryActive) showConversionError(message, "Evidence export", error);
  } finally {
    reconciliationBusy = false;
  }
});

document.getElementById("conversion-reverse").addEventListener("click", async () => {
  const button = document.getElementById("conversion-reverse");
  const message = document.getElementById("conversion-evidence-message");
  const reason = document.getElementById("conversion-reversal-reason").value.trim();
  if (reconciliationBusy || sessionRecoveryActive || !conversionEvidenceId) return;
  if (!document.getElementById("conversion-reversal-confirm").checked || !reason) {
    showMessage(message, "A separate reversal confirmation and a specific reason are required.", true);
    return;
  }
  if (!window.confirm("Request a safe, owner-scoped reversal? The server must refuse if the deadline passed or any dependent activity exists.")) return;
  reconciliationBusy = true;
  button.disabled = true;
  try {
    const result = await conversionApiPost(
      `/serenity-api/conversions/${encodeURIComponent(conversionEvidenceId)}/reverse`,
      { confirm_reverse: true, reason },
    );
    if (sessionRecoveryActive) return;
    document.getElementById("conversion-reversal-confirm").checked = false;
    showMessage(message, result.event_kind === "reversed" || result.state === "reversed" || result.reversal
      ? "Server returned reversal evidence. The original source and conversion history remain retained."
      : "Reversal request processed; refresh evidence to inspect the server's committed state.", false);
    await refreshConversionEvidence(conversionEvidenceId);
  } catch (error) {
    if (!sessionRecoveryActive) showConversionError(message, "Safe reversal", error);
  } finally {
    reconciliationBusy = false;
    button.disabled = false;
  }
});
