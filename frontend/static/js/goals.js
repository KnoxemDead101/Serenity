/* Manual goal records only: no progress is linked, calculated, or derived here. */
const GOALS_URL = "/serenity-api/goals";
const goalForm = document.getElementById("goal-form");
const goalBody = document.getElementById("goals-body");
const goalMessage = document.getElementById("goal-message");
const goalSubmit = document.getElementById("goal-submit");
const goalCancel = document.getElementById("goal-cancel");
const showArchived = document.getElementById("goals-show-archived");
let goals = [];
let goalOptions = null;
let goalEditId = null;
let busy = false;
let loadGeneration = 0;

const main = document.querySelector("main");
new MutationObserver(() => {
  if (!sessionRecoveryActive) return;
  loadGeneration += 1;
  goals = [];
  goalEditId = null;
}).observe(main, { childList: true });

function message(target, text, isError = false) {
  if (!sessionRecoveryActive) showMessage(target, text, isError);
}

function label(value) {
  const text = String(value).toLowerCase().replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function fillSelect(select, values, defaultValue) {
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label(value);
    select.appendChild(option);
  }
  if (defaultValue && values.includes(defaultValue)) select.value = defaultValue;
}

function updateProgressInputState() {
  goalForm.elements.current_progress_amount.disabled =
    goalForm.elements.progress_source.value !== "MANUAL";
}

function applyDefaults() {
  const e = goalForm.elements;
  if (!goalOptions) return;
  e.priority.value = goalOptions.priorities.includes("NORMAL") ? "NORMAL" : e.priority.value;
  e.progress_source.value = goalOptions.progress_sources.includes("MANUAL") ? "MANUAL" : e.progress_source.value;
  e.status.value = goalOptions.statuses.includes("NOT_STARTED") ? "NOT_STARTED" : e.status.value;
  updateProgressInputState();
}

function resetGoal() {
  goalEditId = null;
  goalForm.reset();
  applyDefaults();
  goalForm.elements.status.disabled = true;
  document.getElementById("goal-title").textContent = "Add a goal";
  goalSubmit.textContent = "Add goal";
  goalCancel.hidden = true;
}

// Source navigation: Goal -> Projects filtered to this goal (work tracking, not Goal Items).
function makeProjectsLink(id) {
  const link = document.createElement("a");
  link.href = `/projects?goal_id=${id}`;
  link.className = "button secondary goal-projects-link";
  link.textContent = "Projects";
  return link;
}

function moneyText(value) {
  return value == null ? "—" : formatMoney(value);
}

function render() {
  if (sessionRecoveryActive) return;
  goalBody.replaceChildren();
  if (!goals.length) {
    const row = document.createElement("tr");
    const cell = makeCell(showArchived.checked ? "No goals yet." : "No active goals yet. Add one above.", "muted");
    cell.colSpan = 11;
    row.append(cell);
    goalBody.append(row);
    return;
  }
  for (const g of goals) {
    const row = document.createElement("tr");
    row.dataset.goalId = String(g.id);
    if (!g.active) row.className = "inactive";
    const nameCell = makeCell(g.name);
    if (!g.active) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Archived";
      nameCell.append(" ", badge);
    }
    if (g.description) {
      const d = document.createElement("small");
      d.className = "muted";
      d.textContent = g.description;
      nameCell.append(document.createElement("br"), d);
    }
    const statusSelect = document.createElement("select");
    statusSelect.className = "goal-status-select";
    statusSelect.setAttribute("aria-label", `Status for ${g.name}`);
    statusSelect.dataset.id = String(g.id);
    for (const s of goalOptions.statuses) {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = label(s);
      statusSelect.appendChild(o);
    }
    statusSelect.value = g.status;
    const statusCell = document.createElement("td");
    statusCell.append(statusSelect);
    if (g.completed_at) {
      const c = document.createElement("small");
      c.className = "muted";
      c.textContent = ` Completed ${new Date(g.completed_at).toLocaleDateString()}`;
      statusCell.append(c);
    }
    const tAmt = makeCell(moneyText(g.target_amount), "num");
    const pAmt = makeCell(moneyText(g.current_progress_amount), "num");
    const source = g.progress_source === "MANUAL" ? label(g.progress_source)
      : `${label(g.progress_source)} (reserved; not linked)`;
    row.append(
      nameCell, makeCell(label(g.goal_type)), makeCell(label(g.category)),
      makeCell(label(g.priority)), statusCell, makeCell(g.target_date || "—"),
      tAmt, pAmt, makeCell(source), makeCell(g.notes || "—"),
      makeActionsCell(
        makeRowButton("Details", "open", g.id, "secondary"),
        makeRowButton("Edit", "edit", g.id),
        makeRowButton(g.active ? "Archive" : "Reactivate", g.active ? "deactivate" : "reactivate", g.id, "secondary"),
        makeRowButton("Delete", "delete", g.id, "secondary"),
        makeProjectsLink(g.id),
      ),
    );
    goalBody.append(row);
  }
}

async function reload() {
  const generation = ++loadGeneration;
  const url = showArchived.checked ? `${GOALS_URL}?active_only=false` : GOALS_URL;
  const [opts, list] = await Promise.all([
    goalOptions ? Promise.resolve(goalOptions) : apiGet(`${GOALS_URL}/options`),
    apiGet(url),
  ]);
  if (sessionRecoveryActive || generation !== loadGeneration) return;
  if (!goalOptions) {
    goalOptions = opts;
    const e = goalForm.elements;
    fillSelect(e.goal_type, opts.goal_types);
    fillSelect(e.category, opts.categories);
    fillSelect(e.priority, opts.priorities, "NORMAL");
    fillSelect(e.status, opts.statuses, "NOT_STARTED");
    fillSelect(e.progress_source, opts.progress_sources, "MANUAL");
    updateProgressInputState();
  }
  goals = list;
  render();
  // Keep an open composition fresh after any save, status, archive or delete.
  GC.refresh();
}

function editGoal(g) {
  const e = goalForm.elements;
  goalEditId = g.id;
  e.name.value = g.name;
  e.description.value = g.description || "";
  e.goal_type.value = g.goal_type;
  e.category.value = g.category;
  e.priority.value = g.priority;
  e.status.value = g.status;
  e.status.disabled = true;
  e.target_date.value = g.target_date || "";
  e.target_amount.value = g.target_amount ?? "";
  e.current_progress_amount.value = g.current_progress_amount ?? "";
  e.progress_source.value = g.progress_source;
  updateProgressInputState();
  e.notes.value = g.notes || "";
  document.getElementById("goal-title").textContent = "Edit goal";
  goalSubmit.textContent = "Save goal";
  goalCancel.hidden = false;
  goalMessage.hidden = true;
  goalForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

goalCancel.addEventListener("click", () => {
  if (busy) return;
  resetGoal();
  goalMessage.hidden = true;
});

goalForm.elements.progress_source.addEventListener("change", updateProgressInputState);

showArchived.addEventListener("change", () => {
  reload().catch((error) => message(goalMessage, `Could not load goals: ${error.message}`, true));
});

goalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || sessionRecoveryActive) return;
  const e = goalForm.elements;
  const money = (v) => v.trim() || null;
  if (e.progress_source.value !== "MANUAL" && money(e.current_progress_amount.value) !== null) {
    message(goalMessage,
      "Current progress amount can only be set when progress source is MANUAL. Select Manual to edit or clear the amount.",
      true);
    return;
  }
  for (const value of [money(e.target_amount.value), money(e.current_progress_amount.value)]) {
    if (value !== null && !/^\d+(\.\d{1,2})?$/.test(value)) {
      message(goalMessage, "Enter amounts as plain dollars, such as 1250 or 1250.50.", true);
      return;
    }
  }
  busy = true;
  goalSubmit.disabled = true;
  const id = goalEditId;
  const payload = {
    name: e.name.value.trim(),
    description: e.description.value.trim() || null,
    goal_type: e.goal_type.value,
    category: e.category.value,
    priority: e.priority.value,
    target_date: e.target_date.value || null,
    target_amount: money(e.target_amount.value),
    current_progress_amount: money(e.current_progress_amount.value),
    progress_source: e.progress_source.value,
    notes: e.notes.value.trim() || null,
  };
  try {
    await (id === null ? apiPost(GOALS_URL, payload) : apiPut(`${GOALS_URL}/${id}`, payload));
    if (sessionRecoveryActive) return;
    resetGoal();
    await reload();
    message(goalMessage, id === null ? "Goal added." : "Goal saved.");
  } catch (error) {
    message(goalMessage, error.message, true);
  } finally {
    busy = false;
    goalSubmit.disabled = false;
  }
});

goalBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !goalBody.contains(button) || busy || sessionRecoveryActive) return;
  const record = goals.find((item) => item.id === Number(button.dataset.id));
  if (!record) return;
  const action = button.dataset.action;
  if (action === "edit") { editGoal(record); return; }
  if (action === "open") { GC.open(record.id); return; }
  if (!["deactivate", "reactivate", "delete"].includes(action)) return;
  if (action === "delete" && !window.confirm(
    `Permanently delete "${record.name}"? This cannot be undone.`)) return;
  if (action === "deactivate" && !window.confirm(
    `Archive "${record.name}"? You can show archived goals and reactivate it later.`)) return;
  busy = true;
  button.disabled = true;
  try {
    if (action === "delete") await apiDelete(`${GOALS_URL}/${record.id}`);
    else await apiPost(`${GOALS_URL}/${record.id}/${action}`);
    if (sessionRecoveryActive) return;
    if (action === "delete" && goalEditId === record.id) resetGoal();
    if (action === "delete") GC.closeIf(record.id);
    await reload();
    message(goalMessage, action === "delete" ? `${record.name} deleted.`
      : action === "deactivate" ? `${record.name} archived.` : `${record.name} reactivated.`);
  } catch (error) {
    message(goalMessage, error.message, true);
  } finally {
    busy = false;
    button.disabled = false;
  }
});

goalBody.addEventListener("change", async (event) => {
  const select = event.target.closest("select.goal-status-select");
  if (!select || busy || sessionRecoveryActive) return;
  const record = goals.find((item) => item.id === Number(select.dataset.id));
  if (!record) return;
  busy = true;
  select.disabled = true;
  try {
    await apiPost(`${GOALS_URL}/${record.id}/status`, { status: select.value });
    if (sessionRecoveryActive) return;
    await reload();
    message(goalMessage, `${record.name} status updated.`);
  } catch (error) {
    select.value = record.status;
    message(goalMessage, error.message, true);
  } finally {
    busy = false;
    select.disabled = false;
  }
});

reload().catch((error) => {
  if (sessionRecoveryActive) return;
  goalBody.replaceChildren();
  message(goalMessage, `Could not load goals: ${error.message}`, true);
});
// Deep link /goals?goal_id=N opens that goal's details (archived goals included).
const deepGoalId = Number(new URLSearchParams(window.location.search).get("goal_id"));
if (Number.isInteger(deepGoalId) && deepGoalId > 0) GC.open(deepGoalId);
