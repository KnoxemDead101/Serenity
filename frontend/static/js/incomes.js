/* Income profile data entry and display. Calculations stay server-side. */
const INCOME_URL = "/serenity-api/income-profiles";
const incomeForm = document.getElementById("income-form");
const incomeSubmit = document.getElementById("income-submit");
const incomeCancel = document.getElementById("income-cancel");
const incomeMessage = document.getElementById("income-message");
const incomeFormTitle = document.getElementById("income-form-title");
const incomesBody = document.getElementById("incomes-body");
const pageError = document.getElementById("error");
const TYPE_FIELD_NAMES = [
  "hourly_rate", "expected_hours_per_week", "standard_hours_per_week",
  "annual_salary", "amount_per_period",
];
let editingId = null;
let profilesById = {};

function fillSelect(select, options, blankLabel) {
  select.replaceChildren();
  if (blankLabel) {
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = blankLabel;
    select.appendChild(blank);
  }
  for (const value of options) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

function showFieldsForType() {
  const type = incomeForm.elements.income_type.value;
  for (const label of incomeForm.querySelectorAll("[data-types]")) {
    const applies = label.dataset.types.split(" ").includes(type);
    label.hidden = !applies;
    for (const input of label.querySelectorAll("input")) input.disabled = !applies;
  }
  const variable = type === "Variable";
  document.getElementById("amount-label").textContent = variable
    ? "Typical amount ($, optional, never projected)" : "Amount per paycheck ($)";
  incomeForm.elements.amount_per_period.required = !variable &&
    ["Recurring", "Other"].includes(type);
  incomeForm.elements.hourly_rate.required = type === "Hourly";
  incomeForm.elements.expected_hours_per_week.required = type === "Hourly";
  incomeForm.elements.annual_salary.required = type === "Salary";
  incomeForm.elements.pay_frequency.required = !variable;
}

function readForm() {
  const body = {};
  for (const element of incomeForm.elements) {
    if (element.name && !element.disabled) body[element.name] = element.value;
  }
  for (const name of TYPE_FIELD_NAMES) if (!body[name]) body[name] = null;
  if (!body.expected_net_per_period) body.expected_net_per_period = null;
  if (!body.pay_frequency) body.pay_frequency = null;
  return body;
}

function setDefaultChoices() {
  incomeForm.elements.income_type.value = "Hourly";
  incomeForm.elements.pay_frequency.value = "Biweekly";
  incomeForm.elements.classification.value = "Personal";
}

function resetForm() {
  editingId = null;
  incomeForm.reset();
  setDefaultChoices();
  incomeFormTitle.textContent = "Add an income profile";
  incomeSubmit.textContent = "Add income profile";
  incomeCancel.hidden = true;
  showFieldsForType();
}

function startEdit(profile) {
  editingId = profile.id;
  incomeForm.elements.name.value = profile.name;
  incomeForm.elements.income_type.value = profile.income_type;
  incomeForm.elements.classification.value = profile.classification;
  incomeForm.elements.pay_frequency.value = profile.pay_frequency || "";
  for (const name of [...TYPE_FIELD_NAMES, "expected_net_per_period"]) {
    incomeForm.elements[name].value = profile[name] ?? "";
  }
  incomeForm.elements.notes.value = profile.notes || "";
  showFieldsForType();
  incomeFormTitle.textContent = `Edit "${profile.name}"`;
  incomeSubmit.textContent = "Save income profile";
  incomeCancel.hidden = false;
  incomeMessage.hidden = true;
  incomeForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function moneyOrDash(value) {
  return value === null || value === undefined ? "—" : formatMoney(value);
}

function renderProfiles(profiles) {
  profilesById = Object.fromEntries(profiles.map((profile) => [profile.id, profile]));
  incomesBody.replaceChildren();
  if (!profiles.length) {
    const row = document.createElement("tr");
    const cell = makeCell("No income profiles yet.", "muted");
    cell.colSpan = 8;
    row.appendChild(cell);
    incomesBody.appendChild(row);
    return;
  }
  for (const profile of profiles) {
    const calc = profile.calculated;
    const row = document.createElement("tr");
    if (!profile.active) row.className = "inactive";
    const name = makeCell(profile.name);
    if (!profile.active) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Inactive";
      name.append(" ", badge);
    }
    const type = makeCell(profile.income_type);
    if (!calc.projected) {
      const badge = document.createElement("span");
      badge.className = "badge warning";
      badge.textContent = "Not projected";
      type.append(" ", badge);
    }
    const lifecycle = profile.active
      ? makeRowButton("Deactivate", "deactivate", profile.id, "secondary")
      : makeRowButton("Reactivate", "reactivate", profile.id, "secondary");
    row.append(
      name, type, makeCell(profile.pay_frequency || "—"),
      makeCell(moneyOrDash(calc.gross_per_period), "num"),
      makeCell(moneyOrDash(calc.gross_monthly), "num"),
      makeCell(moneyOrDash(calc.gross_annual), "num"),
      makeCell(moneyOrDash(calc.net_monthly), "num"),
      makeActionsCell(makeRowButton("Edit", "edit", profile.id), lifecycle),
    );
    incomesBody.appendChild(row);
  }
}

function renderSummary(summary) {
  document.getElementById("gross-monthly").textContent = formatMoney(summary.gross_monthly);
  document.getElementById("gross-annual").textContent = formatMoney(summary.gross_annual);
  document.getElementById("net-monthly").textContent = moneyOrDash(summary.net_monthly);
  document.getElementById("active-count").textContent = summary.active_count;
  const notes = [];
  if (summary.variable_count) notes.push(
    `${summary.variable_count} variable profile(s) are not included in the totals.`
  );
  if (summary.net_is_partial) notes.push(
    `Take-home covers only the ${summary.net_profile_count} profile(s) with a take-home amount.`
  );
  const note = document.getElementById("summary-note");
  note.textContent = notes.join(" ");
  note.hidden = !notes.length;
}

async function refresh() {
  try {
    const [profiles, summary] = await Promise.all([
      apiGet(INCOME_URL), apiGet(`${INCOME_URL}/summary`),
    ]);
    renderProfiles(profiles);
    renderSummary(summary);
    pageError.hidden = true;
  } catch (error) {
    pageError.textContent = error.message;
    pageError.hidden = false;
  }
}

incomeForm.elements.income_type.addEventListener("change", showFieldsForType);
incomeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  incomeSubmit.disabled = true;
  try {
    const body = readForm();
    if (editingId === null) {
      await apiPost(INCOME_URL, body);
      showMessage(incomeMessage, `Added "${body.name.trim()}".`, false);
    } else {
      await apiPut(`${INCOME_URL}/${editingId}`, body);
      showMessage(incomeMessage, `Saved "${body.name.trim()}".`, false);
    }
    resetForm();
    await refresh();
  } catch (error) {
    showMessage(incomeMessage, error.message, true);
  } finally {
    incomeSubmit.disabled = false;
  }
});
incomeCancel.addEventListener("click", () => {
  resetForm();
  incomeMessage.hidden = true;
});
incomesBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const profile = profilesById[id];
  if (button.dataset.action === "edit") {
    startEdit(profile);
    return;
  }
  if (button.dataset.action === "deactivate" &&
      !window.confirm(`Deactivate "${profile.name}"? It stays in your history but leaves the totals.`)) return;
  try {
    await apiPost(`${INCOME_URL}/${id}/${button.dataset.action}`);
    showMessage(incomeMessage, `Income profile ${button.dataset.action}d.`, false);
    await refresh();
  } catch (error) {
    showMessage(incomeMessage, error.message, true);
  }
});

async function init() {
  try {
    const options = await apiGet(`${INCOME_URL}/options`);
    fillSelect(incomeForm.elements.income_type, options.income_types);
    fillSelect(incomeForm.elements.pay_frequency, options.pay_frequencies, "Not set");
    fillSelect(incomeForm.elements.classification, options.classifications);
    setDefaultChoices();
    showFieldsForType();
  } catch (error) {
    pageError.textContent = error.message;
    pageError.hidden = false;
  }
  await refresh();
}
init();