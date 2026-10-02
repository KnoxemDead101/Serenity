/* Projects and Tasks (one script, two pages). Manual work tracking only:
 * not Goal Items, and no money or financial progress is read or calculated.
 * All user text is shown with textContent. */
const KIND = document.body.dataset.kind;
const IS_PROJECT = KIND === "projects";
const WORK_URL = `/serenity-api/${KIND}`;
const PARENT_URL = IS_PROJECT ? "/serenity-api/goals" : "/serenity-api/projects";
const PARENT_KEY = IS_PROJECT ? "goal_id" : "project_id";
const PARENT_NAME_KEY = IS_PROJECT ? "goal_name" : "project_name";
const DATE_KEY = IS_PROJECT ? "target_date" : "due_date";
const NOUN = IS_PROJECT ? "project" : "task";
const PARENT_NOUN = IS_PROJECT ? "goal" : "project";
const PARENT_PAGE = IS_PROJECT ? "/goals" : "/projects";

const form = document.getElementById("work-form");
const body = document.getElementById("work-body");
const msg = document.getElementById("work-message");
const submitBtn = document.getElementById("work-submit");
const cancelBtn = document.getElementById("work-cancel");
const showArchived = document.getElementById("work-show-archived");
const filterSel = document.getElementById("work-filter-parent");
const loadError = document.getElementById("work-load-error");
const detailsPanel = document.getElementById("work-details");
const detailsBody = document.getElementById("work-details-body");
let records = [], parents = [], options = null;
let editId = null, detailsId = null, busy = false, gen = 0;
const params = new URLSearchParams(window.location.search);

new MutationObserver(() => {
  if (!sessionRecoveryActive) return;
  gen += 1; records = []; editId = null; detailsId = null;
}).observe(document.querySelector("main"), { childList: true });

const say = (text, err = false) => { if (!sessionRecoveryActive) showMessage(msg, text, err); };
const pretty = (v) => { const t = String(v).toLowerCase().replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
const parentById = (id) => parents.find((p) => p.id === id);

// A task cannot change while its project is archived; archived records are read only.
function locked(r) {
  if (!r.active) return true;
  if (!IS_PROJECT && r.project_id != null) {
    const p = parentById(r.project_id);
    return !!p && p.active === false;
  }
  return false;
}
function lockReason(r) {
  if (!r.active) return `This ${NOUN} is archived. Reactivate it to make changes.`;
  return "Its project is archived. Restore the project to change this task.";
}

function fillSelect(select, values) {
  select.replaceChildren();
  for (const v of values) {
    const o = document.createElement("option");
    o.value = v; o.textContent = pretty(v); select.append(o);
  }
}

function fillParentSelects(currentId) {
  const none = `No ${PARENT_NOUN} (standalone)`;
  form.elements.parent_id.replaceChildren(new Option(none, ""));
  for (const p of parents) {
    // Archived parents cannot receive a new link; an existing link stays selectable.
    if (!p.active && p.id !== currentId) continue;
    form.elements.parent_id.append(new Option(p.name + (p.active ? "" : " (archived)"), String(p.id)));
  }
  const keep = filterSel.value;
  filterSel.replaceChildren(new Option(`All ${KIND}`, ""));
  for (const p of parents) filterSel.append(new Option(p.name + (p.active ? "" : " (archived)"), String(p.id)));
  filterSel.value = keep;
}

function resetForm() {
  editId = null;
  form.reset();
  fillParentSelects(null);
  form.elements.priority.value = "NORMAL";
  form.elements.status.value = "NOT_STARTED";
  form.elements.status.disabled = true;
  // Default a new record's parent to the active filter, when that parent can be linked.
  const f = parentById(Number(filterSel.value));
  form.elements.parent_id.value = f && f.active ? String(f.id) : "";
  document.getElementById("work-form-title").textContent = `Add ${NOUN}`;
  submitBtn.textContent = `Add ${NOUN}`;
  cancelBtn.hidden = true;
  document.getElementById("work-parent-hint").textContent = "";
}

function parentLink(r) {
  if (r[PARENT_KEY] == null) return null;
  const a = document.createElement("a");
  a.href = `${PARENT_PAGE}?${PARENT_KEY}=${r[PARENT_KEY]}`;
  a.textContent = r[PARENT_NAME_KEY] || `${pretty(PARENT_NOUN)} ${r[PARENT_KEY]}`;
  a.className = "work-parent-link";
  return a;
}

function statusSelect(r) {
  const sel = document.createElement("select");
  sel.className = "work-status-select";
  sel.dataset.id = String(r.id);
  sel.setAttribute("aria-label", `Status for ${r.name}`);
  fillSelect(sel, options.statuses);
  sel.value = r.status;
  if (locked(r)) { sel.disabled = true; sel.title = lockReason(r); }
  return sel;
}

function actionButtons(r, inDetails) {
  const out = [];
  if (!inDetails) out.push(makeRowButton("Details", "open", r.id, "secondary"));
  const lock = locked(r);
  const edit = makeRowButton("Edit", "edit", r.id);
  edit.disabled = lock;
  if (lock) edit.title = lockReason(r);
  out.push(edit);
  const arch = makeRowButton(r.active ? "Archive" : "Reactivate", r.active ? "deactivate" : "reactivate", r.id, "secondary");
  if (r.active && lock) { arch.disabled = true; arch.title = lockReason(r); }
  out.push(arch);
  return out;
}

function render() {
  if (sessionRecoveryActive) return;
  body.replaceChildren();
  if (!records.length) {
    const tr = document.createElement("tr");
    const td = makeCell(filterSel.value ? `No ${KIND} for this ${PARENT_NOUN} yet.`
      : showArchived.checked ? `No ${KIND} yet.` : `No active ${KIND} yet. Add one above.`, "muted");
    td.colSpan = 6; tr.append(td); body.append(tr);
    return;
  }
  for (const r of records) {
    const tr = document.createElement("tr");
    tr.dataset.recordId = String(r.id);
    if (!r.active) tr.className = "inactive";
    const nameCell = makeCell(r.name);
    if (!r.active) {
      const b = document.createElement("span");
      b.className = "badge"; b.textContent = "Archived";
      nameCell.append(" ", b);
    }
    if (r.description) {
      const d = document.createElement("small");
      d.className = "muted"; d.textContent = r.description;
      nameCell.append(document.createElement("br"), d);
    }
    const parentCell = document.createElement("td");
    const link = parentLink(r);
    if (link) parentCell.append(link); else { parentCell.textContent = "Standalone"; parentCell.className = "muted"; }
    const statusCell = document.createElement("td");
    statusCell.append(statusSelect(r));
    tr.append(nameCell, parentCell, makeCell(pretty(r.priority)), statusCell,
      makeCell(r[DATE_KEY] || "—"), makeActionsCell(...actionButtons(r, false)));
    body.append(tr);
  }
}

function showLoadError(text) {
  document.getElementById("work-load-error-text").textContent = text;
  loadError.hidden = false;
  body.replaceChildren();
}

async function reload() {
  const g = ++gen;
  const query = new URLSearchParams({ active_only: String(!showArchived.checked) });
  if (filterSel.value) query.set(PARENT_KEY, filterSel.value);
  const [opts, list, plist] = await Promise.all([
    options ? Promise.resolve(options) : apiGet(`${WORK_URL}/options`),
    apiGet(`${WORK_URL}?${query}`),
    apiGet(`${PARENT_URL}?active_only=false`),
  ]);
  if (sessionRecoveryActive || g !== gen) return;
  if (!options) {
    options = opts;
    fillSelect(form.elements.priority, opts.priorities);
    fillSelect(form.elements.status, opts.statuses);
    form.elements.priority.value = "NORMAL";
    form.elements.status.value = "NOT_STARTED";
  }
  parents = plist;
  records = list;
  loadError.hidden = true;
  const cur = editId === null ? null : (records.find((r) => r.id === editId) || {})[PARENT_KEY];
  const draft = form.elements.parent_id.value;
  fillParentSelects(cur ?? null);
  form.elements.parent_id.value = draft;
  render();
  if (detailsId !== null) await loadDetails(detailsId, false);
}

function loadAll(initial) {
  return reload().then(() => {
    if (initial) startDeepLink();
  }).catch((error) => {
    if (sessionRecoveryActive) return;
    showLoadError(`Could not load ${KIND}: ${error.message}`);
  });
}

function startEdit(r) {
  if (locked(r)) { say(lockReason(r), true); return; }
  editId = r.id;
  const e = form.elements;
  fillParentSelects(r[PARENT_KEY]);
  e.name.value = r.name;
  e.description.value = r.description || "";
  e.priority.value = r.priority;
  e.status.value = r.status;
  e.status.disabled = true;
  e.date.value = r[DATE_KEY] || "";
  e.parent_id.value = r[PARENT_KEY] == null ? "" : String(r[PARENT_KEY]);
  e.notes.value = r.notes || "";
  document.getElementById("work-form-title").textContent = `Edit ${NOUN}`;
  submitBtn.textContent = `Save ${NOUN}`;
  cancelBtn.hidden = false;
  const p = r[PARENT_KEY] == null ? null : parentById(r[PARENT_KEY]);
  document.getElementById("work-parent-hint").textContent =
    p && !p.active ? `The linked ${PARENT_NOUN} is archived. You can keep this link or choose another.` : "";
  msg.hidden = true;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  e.name.focus();
}

function detailRow(dl, term, value) {
  const dt = document.createElement("dt"); dt.textContent = term;
  const dd = document.createElement("dd");
  if (value instanceof Node) dd.append(value); else dd.textContent = value;
  dl.append(dt, dd);
}

function renderDetails(r) {
  detailsBody.replaceChildren();
  document.getElementById("work-details-title").textContent = `${pretty(NOUN)}: ${r.name}`;
  const top = document.createElement("div");
  top.className = "form-buttons";
  top.append(makeRowButton("Close details", "close", r.id, "secondary"));
  detailsBody.append(top);
  if (locked(r)) {
    const p = document.createElement("p");
    p.className = "message error"; p.textContent = lockReason(r);
    detailsBody.append(p);
  }
  const dl = document.createElement("dl");
  dl.className = "work-details-grid";
  detailRow(dl, "Status", pretty(r.status) + (r.active ? "" : " (archived)"));
  detailRow(dl, "Priority", pretty(r.priority));
  detailRow(dl, IS_PROJECT ? "Target date" : "Due date", r[DATE_KEY] || "—");
  detailRow(dl, IS_PROJECT ? "Source goal" : "Source project", parentLink(r) || "Standalone");
  detailRow(dl, "Description", r.description || "—");
  detailRow(dl, "Notes", r.notes || "—");
  detailRow(dl, "Completed", r.completed_at ? new Date(r.completed_at).toLocaleString() : "—");
  detailRow(dl, "Created", new Date(r.created_at).toLocaleString());
  detailRow(dl, "Updated", new Date(r.updated_at).toLocaleString());
  detailsBody.append(dl);
  const bar = document.createElement("div");
  bar.className = "form-buttons";
  const lab = document.createElement("label");
  lab.textContent = "Status ";
  const sel = statusSelect(r);
  sel.classList.add("work-details-status");
  lab.append(sel);
  bar.append(lab, ...actionButtons(r, true));
  if (IS_PROJECT) {
    const t = document.createElement("a");
    t.className = "button secondary work-tasks-link";
    t.href = `/tasks?project_id=${r.id}`;
    t.textContent = "View tasks";
    bar.append(t);
  }
  detailsBody.append(bar);
}

async function loadDetails(id, focus) {
  detailsId = id;
  try {
    const r = await apiGet(`${WORK_URL}/${id}`);
    if (sessionRecoveryActive || detailsId !== id) return;
    renderDetails(r);
    detailsPanel.hidden = false;
    if (focus) { detailsPanel.scrollIntoView({ behavior: "smooth", block: "start" }); detailsPanel.focus(); }
  } catch (error) {
    if (sessionRecoveryActive || detailsId !== id) return;
    detailsId = null;
    detailsPanel.hidden = true;
    say(`Could not open ${NOUN} details: ${error.message}`, true);
  }
}

function closeDetails() { detailsId = null; detailsPanel.hidden = true; detailsBody.replaceChildren(); }

// Deep links: /projects?project_id=N opens details; other filters are applied before the first load.
function startDeepLink() {
  const id = Number(params.get("project_id"));
  if (IS_PROJECT && Number.isInteger(id) && id > 0) {
    loadDetails(id, true);
  }
}

async function runAction(fn, okText, button) {
  if (busy || sessionRecoveryActive) return false;
  busy = true;
  if (button) button.disabled = true;
  try {
    await fn();
    if (sessionRecoveryActive) return false;
    try {
      await reload();
      say(okText);
    } catch (error) {
      // The mutation succeeded. Do not invite a duplicate create just because
      // refreshing the list failed after saving.
      showLoadError(`Could not refresh ${KIND}: ${error.message}`);
      say(`${okText} The list could not refresh. Use Retry to reload it.`, true);
    }
    return true;
  } catch (error) {
    say(error.message, true);
    return false;
  } finally {
    busy = false;
    if (button) button.disabled = false;
  }
}

async function changeStatus(select) {
  if (busy || sessionRecoveryActive) return;
  const id = Number(select.dataset.id);
  const r = records.find((x) => x.id === id) || { name: NOUN, status: select.value };
  select.disabled = true;
  const ok = await runAction(() => apiPost(`${WORK_URL}/${id}/status`, { status: select.value }),
    `${r.name} status updated.`, null);
  if (!ok) { select.value = r.status; }
  select.disabled = false;
}

async function handleAction(button) {
  const action = button.dataset.action;
  if (action === "close") { closeDetails(); return; }
  const id = Number(button.dataset.id);
  let r = records.find((x) => x.id === id);
  if (!r) { try { r = await apiGet(`${WORK_URL}/${id}`); } catch (e) { say(e.message, true); return; } }
  if (action === "open") { loadDetails(id, true); return; }
  if (action === "edit") { startEdit(r); return; }
  if (action === "deactivate" && !window.confirm(
    `Archive "${r.name}"? ${IS_PROJECT ? "Its tasks become read only until it is restored. " : ""}You can show archived ${KIND} and reactivate it later.`)) return;
  await runAction(() => apiPost(`${WORK_URL}/${id}/${action}`),
    action === "deactivate" ? `${r.name} archived.` : `${r.name} reactivated.`, button);
  if (action === "deactivate" && editId === id) resetForm();
}

function onClick(event) {
  const b = event.target.closest("button[data-action]");
  if (b && !b.disabled) handleAction(b);
}
function onChange(event) {
  const s = event.target.closest("select.work-status-select");
  if (s) changeStatus(s);
}
body.addEventListener("click", onClick);
detailsBody.addEventListener("click", onClick);
body.addEventListener("change", onChange);
detailsBody.addEventListener("change", onChange);

cancelBtn.addEventListener("click", () => { if (!busy) { resetForm(); msg.hidden = true; } });
document.getElementById("work-retry").addEventListener("click", () => loadAll(false));
showArchived.addEventListener("change", () => loadAll(false));
filterSel.addEventListener("change", () => {
  const url = new URL(window.location.href);
  if (filterSel.value) url.searchParams.set(PARENT_KEY, filterSel.value); else url.searchParams.delete(PARENT_KEY);
  window.history.replaceState(null, "", url);
  if (editId === null) {
    const f = parentById(Number(filterSel.value));
    form.elements.parent_id.value = f && f.active ? String(f.id) : "";
  }
  loadAll(false);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || sessionRecoveryActive) return;
  const e = form.elements;
  const payload = {
    name: e.name.value.trim(),
    description: e.description.value.trim() || null,
    notes: e.notes.value.trim() || null,
    priority: e.priority.value,
    [DATE_KEY]: e.date.value || null,
    [PARENT_KEY]: e.parent_id.value ? Number(e.parent_id.value) : null,
  };
  if (!payload.name) { say("Name is required.", true); return; }
  const id = editId;
  submitBtn.disabled = true;
  const ok = await runAction(() => (id === null ? apiPost(WORK_URL, payload) : apiPut(`${WORK_URL}/${id}`, payload)),
    id === null ? `${pretty(NOUN)} added.` : `${pretty(NOUN)} saved.`, null);
  submitBtn.disabled = false;
  if (ok) resetForm();
  // On failure the form keeps what was typed.
});

// Prefilter from the URL (?goal_id=N on projects, ?project_id=N on tasks).
// Parent options are filled once the first load returns, so apply it then.
const initialFilter = params.get(PARENT_KEY);
resetForm();
(async () => {
  await loadAll(true);
  if (initialFilter) {
    if (!/^\d+$/.test(initialFilter) || !parentById(Number(initialFilter))) {
      showLoadError(`The source ${PARENT_NOUN} could not be found in this workspace.`);
      return;
    }
    // Deep link to a project's own details uses project_id on the projects page,
    // which is not a filter there; only goal_id filters projects.
    filterSel.value = initialFilter;
    if (filterSel.value === initialFilter) {
      await loadAll(false);
      resetForm();
    }
  }
})();
