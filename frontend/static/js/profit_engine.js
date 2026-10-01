/* This page collects instrument facts and displays Python-calculated estimates only. */
const INSTRUMENT_URL = "/serenity-api/instruments";
const CALCULATE_URL = "/serenity-api/profit-engine/calculate";
const instrumentForm = document.getElementById("instrument-form");
const instrumentSubmit = document.getElementById("instrument-submit");
const instrumentCancel = document.getElementById("instrument-cancel");
const instrumentMessage = document.getElementById("instrument-message");
const instrumentBody = document.getElementById("instruments-body");
const versionsPanel = document.getElementById("versions-panel");
const versionsBody = document.getElementById("versions-body");
const versionsTitle = document.getElementById("versions-title");
const versionsMessage = document.getElementById("versions-message");
const calculatorForm = document.getElementById("calculator-form");
const calculatorSubmit = document.getElementById("calculator-submit");
const calculatorMessage = document.getElementById("calculator-message");
const calculatorResults = document.getElementById("calculator-results");
let instruments = [];
let editingId = null;
let viewingVersionsId = null;
let lifecyclePending = false;
let calculatorGeneration = 0;

function showProfitMessage(target, text, isError) {
  if (!sessionRecoveryActive) showMessage(target, text, isError);
}

function resetInstrumentForm() {
  editingId = null;
  instrumentForm.reset();
  instrumentForm.elements.symbol.disabled = false;
  instrumentSubmit.textContent = "Add instrument";
  instrumentCancel.hidden = true;
  updatePointValueField();
}

function updatePointValueField() {
  const shares = instrumentForm.elements.asset_type.value !== "FUTURE";
  const pointValue = instrumentForm.elements.point_value;
  if (shares) pointValue.value = "1";
  pointValue.readOnly = shares;
  document.getElementById("point-value-hint").textContent = shares
    ? "For shares this is always 1."
    : "Verify futures point value and tick size with your exchange or broker.";
}

function readInstrumentForm() {
  const fields = instrumentForm.elements;
  return {
    symbol: fields.symbol.value.trim(),
    name: fields.name.value.trim(),
    asset_type: fields.asset_type.value,
    exchange: fields.exchange.value.trim() || null,
    currency: "USD",
    tick_size: fields.tick_size.value,
    point_value: fields.point_value.value,
  };
}

function startInstrumentEdit(record) {
  editingId = record.id;
  for (const name of ["symbol", "name", "asset_type", "tick_size", "point_value"]) {
    instrumentForm.elements[name].value = record[name];
  }
  instrumentForm.elements.exchange.value = record.exchange || "";
  instrumentForm.elements.symbol.disabled = true;
  updatePointValueField();
  instrumentSubmit.textContent = "Save new version";
  instrumentCancel.hidden = false;
  instrumentMessage.hidden = true;
  instrumentForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function selectInstrumentChoices() {
  const select = calculatorForm.elements.specification_id;
  const previous = select.value;
  select.replaceChildren();
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Choose an active instrument";
  select.appendChild(blank);
  for (const record of instruments.filter((item) => item.active)) {
    const option = document.createElement("option");
    option.value = record.specification_id;
    option.textContent = `${record.symbol} · ${record.name} (v${record.version}, ${record.asset_type})`;
    select.appendChild(option);
  }
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  } else {
    select.value = "";
    calculatorGeneration += 1;
    clearResults();
  }
}

function renderInstruments(records) {
  if (sessionRecoveryActive) return;
  instruments = records;
  instrumentBody.replaceChildren();
  if (!records.length) {
    const row = document.createElement("tr");
    const cell = makeCell("No instruments yet. Add one to try the calculator.", "muted");
    cell.colSpan = 8;
    row.appendChild(cell);
    instrumentBody.appendChild(row);
  }
  for (const record of records) {
    const row = document.createElement("tr");
    if (!record.active) row.className = "inactive";
    const symbol = makeCell(record.symbol);
    if (!record.active) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Archived";
      symbol.append(" ", badge);
    }
    const lifecycle = record.active
      ? makeRowButton("Archive", "deactivate", record.id, "secondary")
      : makeRowButton("Reactivate", "reactivate", record.id, "secondary");
    row.append(
      symbol, makeCell(record.name), makeCell(record.asset_type),
      makeCell(record.exchange || "—"), makeCell(record.tick_size, "num"),
      makeCell(record.point_value, "num"), makeCell(`v${record.version}`),
      makeActionsCell(
        makeRowButton("Edit", "edit", record.id),
        makeRowButton("Versions", "versions", record.id, "secondary"),
        lifecycle,
      ),
    );
    instrumentBody.appendChild(row);
  }
  selectInstrumentChoices();
}

async function loadInstruments() {
  const records = await apiGet(INSTRUMENT_URL);
  renderInstruments(records);
}

function renderVersions(record, versions) {
  if (sessionRecoveryActive || viewingVersionsId !== record.id) return;
  versionsTitle.textContent = `Specification versions · ${record.symbol}`;
  versionsPanel.hidden = false;
  versionsBody.replaceChildren();
  for (const version of versions) {
    const row = document.createElement("tr");
    row.append(
      makeCell(`v${version.version}`),
      makeCell(version.symbol), makeCell(version.name),
      makeCell(version.asset_type), makeCell(version.exchange || "—"),
      makeCell(version.tick_size, "num"), makeCell(version.point_value, "num"),
    );
    versionsBody.appendChild(row);
  }
  if (!versions.length) showProfitMessage(versionsMessage, "No versions found.", true);
  else versionsMessage.hidden = true;
}

async function loadVersions(record) {
  viewingVersionsId = record.id;
  try {
    const versions = await apiGet(`${INSTRUMENT_URL}/${record.id}/specifications`);
    renderVersions(record, versions);
  } catch (error) {
    showProfitMessage(versionsMessage, error.message, true);
    if (!sessionRecoveryActive) versionsPanel.hidden = false;
  }
}

// Formatting string values is presentation only; no financial arithmetic is done here.
function displayDecimal(value) {
  if (value === null || value === undefined) return "—";
  return String(value);
}

function displayDollars(value) {
  if (value === null || value === undefined) return "—";
  const text = String(value);
  const negative = text.startsWith("-");
  const [whole, fraction = ""] = (negative ? text.slice(1) : text).split(".");
  return `${negative ? "-" : ""}$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;
}

function displayPair(points, ticks, dollars) {
  if (points === null || points === undefined) return "—";
  return `${displayDecimal(points)} points / ${displayDecimal(ticks)} ticks / ${displayDollars(dollars)}`;
}

function setResult(name, text) {
  document.getElementById(`result-${name}`).textContent = text;
}

function clearResults() {
  calculatorResults.hidden = true;
  for (const cell of calculatorResults.querySelectorAll("td[id^=result-]")) {
    cell.textContent = "";
  }
}

function renderCalculation(result) {
  if (sessionRecoveryActive) return;
  for (const name of ["price_difference", "points", "ticks", "planned_rr", "realized_r"]) {
    setResult(name, displayDecimal(result[name]));
  }
  for (const name of ["gross_pnl", "fees", "net_pnl"]) {
    setResult(name, displayDollars(result[name]));
  }
  setResult("risk", displayPair(result.risk_points, result.risk_ticks, result.risk_dollars));
  setResult("reward", displayPair(result.reward_points, result.reward_ticks, result.reward_dollars));
  calculatorResults.hidden = false;
}

instrumentForm.elements.asset_type.addEventListener("change", updatePointValueField);
instrumentCancel.addEventListener("click", () => {
  resetInstrumentForm();
  instrumentMessage.hidden = true;
});
instrumentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (instrumentSubmit.disabled) return;
  instrumentSubmit.disabled = true;
  const payload = readInstrumentForm();
  const savedId = editingId;
  try {
    const saved = savedId === null
      ? await apiPost(INSTRUMENT_URL, payload)
      : await apiPut(`${INSTRUMENT_URL}/${savedId}`, payload);
    if (sessionRecoveryActive) return;
    resetInstrumentForm();
    await loadInstruments();
    if (savedId !== null && calculatorForm.elements.specification_id.value === "") {
      calculatorForm.elements.specification_id.value = String(saved.specification_id);
    }
    if (viewingVersionsId === saved.id) await loadVersions(saved);
    showProfitMessage(instrumentMessage, savedId === null
      ? `Instrument ${saved.symbol} added.`
      : `New specification version saved for ${saved.symbol}.`, false);
  } catch (error) {
    showProfitMessage(instrumentMessage, error.message, true);
  } finally {
    instrumentSubmit.disabled = false;
  }
});

instrumentBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !instrumentBody.contains(button) || lifecyclePending) return;
  const record = instruments.find((item) => item.id === Number(button.dataset.id));
  if (!record) return;
  if (button.dataset.action === "edit") {
    startInstrumentEdit(record);
    return;
  }
  if (button.dataset.action === "versions") {
    await loadVersions(record);
    return;
  }
  if (button.dataset.action !== "deactivate" && button.dataset.action !== "reactivate") return;
  if (button.dataset.action === "deactivate" &&
      !window.confirm(`Archive "${record.symbol}"? It will no longer be available for new calculations. Its specification history is retained and it can be reactivated.`)) return;
  lifecyclePending = true;
  button.disabled = true;
  try {
    await apiPost(`${INSTRUMENT_URL}/${record.id}/${button.dataset.action}`);
    if (sessionRecoveryActive) return;
    if (editingId === record.id) resetInstrumentForm();
    await loadInstruments();
    calculatorGeneration += 1;
    clearResults();
    showProfitMessage(instrumentMessage, button.dataset.action === "deactivate"
      ? `${record.symbol} archived.` : `${record.symbol} reactivated.`, false);
  } catch (error) {
    showProfitMessage(instrumentMessage, error.message, true);
  } finally {
    lifecyclePending = false;
    button.disabled = false;
  }
});

function invalidateCalculation() {
  calculatorGeneration += 1;
  clearResults();
}
calculatorForm.addEventListener("input", invalidateCalculation);
calculatorForm.addEventListener("change", invalidateCalculation);
calculatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (calculatorSubmit.disabled) return;
  calculatorSubmit.disabled = true;
  clearResults();
  calculatorMessage.hidden = true;
  const generation = ++calculatorGeneration;
  const fields = calculatorForm.elements;
  const payload = {
    specification_id: Number(fields.specification_id.value),
    direction: fields.direction.value,
    quantity: fields.quantity.value,
    entry_price: fields.entry_price.value,
    exit_price: fields.exit_price.value || null,
    stop_price: fields.stop_price.value || null,
    target_price: fields.target_price.value || null,
    fees: fields.fees.value,
  };
  try {
    const result = await apiPost(CALCULATE_URL, payload);
    if (generation === calculatorGeneration) renderCalculation(result);
  } catch (error) {
    if (generation === calculatorGeneration) {
      showProfitMessage(calculatorMessage, error.message, true);
    }
  } finally {
    calculatorSubmit.disabled = false;
  }
});

updatePointValueField();
loadInstruments().catch((error) => {
  if (!sessionRecoveryActive) {
    instrumentBody.replaceChildren();
    const row = document.createElement("tr");
    const cell = makeCell("Could not load instruments.", "muted");
    cell.colSpan = 8;
    row.appendChild(cell);
    instrumentBody.appendChild(row);
  }
  showProfitMessage(instrumentMessage, error.message, true);
});