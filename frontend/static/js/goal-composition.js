/* Goal composition: items, milestones and checkpoints under one goal.
 * Display and input only. Money stays as strings; "reached" comes from the API.
 * Nothing here is real spending or a financial total. */
const GC = (() => {
  const BASE = "/serenity-api/goals";
  const panel = document.getElementById("composition");
  const body = document.getElementById("composition-body");
  const msg = document.getElementById("composition-message");
  const title = document.getElementById("composition-title");
  let goalId = null, data = null, options = null;
  let showArchivedItems = false, busy = false, gen = 0;
  const editing = { items: null, milestones: null, checkpoints: null };
  // Unsaved form values per section, so failed writes or refreshes never lose typing.
  let drafts = {};

  const SECTIONS = {
    items: {
      heading: "Items", noun: "item",
      note: "Expected cost is a plan. Manual actual cost override is a provisional note you enter; it is not recorded spending.",
      fields: [
        { name: "name", label: "Name", max: 100, required: true },
        { name: "description", label: "Description (optional)", area: true, max: 1000 },
        { name: "expected_cost", label: "Expected cost, planning ($, optional)", money: true },
        { name: "manual_actual_cost_override", label: "Manual actual cost override, provisional ($, optional)", money: true },
        { name: "notes", label: "Notes (optional)", area: true, max: 1000 },
        { name: "sort_order", label: "Order", order: true },
      ],
    },
    milestones: {
      heading: "Milestones", noun: "milestone",
      note: "Completion date is set by the system when status becomes Completed.",
      fields: [
        { name: "title", label: "Title", max: 100, required: true },
        { name: "description", label: "Description (optional)", area: true, max: 1000 },
        { name: "target_date", label: "Target date (optional)", date: true },
        { name: "sort_order", label: "Order", order: true },
      ],
    },
    checkpoints: {
      heading: "Checkpoints", noun: "checkpoint",
      note: "Reached is worked out by the server from your manual progress. Unknown means there is no manual progress to compare.",
      fields: [
        { name: "amount", label: "Amount ($)", money: true, required: true },
        { name: "label", label: "Label (optional)", max: 100 },
        { name: "sort_order", label: "Order", order: true },
      ],
    },
  };

  const pretty = (v) => { const t = String(v).toLowerCase().replace(/_/g, " "); return t[0].toUpperCase() + t.slice(1); };
  const say = (text, err) => { if (!sessionRecoveryActive) showMessage(msg, text, err); };
  const moneyOrDash = (v) => (v == null ? "—" : formatMoney(v));

  // Reset private state if the session-recovery screen replaces the page.
  new MutationObserver(() => {
    if (!sessionRecoveryActive) return;
    gen += 1; goalId = null; data = null; options = null; drafts = {};
  }).observe(document.querySelector("main"), { childList: true });

  function close() {
    gen += 1; goalId = null; data = null; drafts = {};
    for (const k in editing) editing[k] = null;
    panel.hidden = true; body.replaceChildren();
  }

  async function load(scroll) {
    if (goalId === null) return;
    const g = ++gen, id = goalId;
    try {
      const [opts, d] = await Promise.all([
        options ? Promise.resolve(options) : apiGet(`${BASE}/composition/options`),
        apiGet(`${BASE}/${id}/composition?active_only=${!showArchivedItems}`),
      ]);
      if (sessionRecoveryActive || g !== gen) return;
      options = opts; data = d;
      render();
      if (scroll) { panel.hidden = false; panel.scrollIntoView({ behavior: "smooth", block: "start" }); panel.focus(); }
    } catch (error) {
      if (sessionRecoveryActive || g !== gen) return;
      if (/not found|404/i.test(error.message)) { close(); return; }
      panel.hidden = false;
      say(`Could not load composition: ${error.message}`, true);
    }
  }

  function field(spec, rec) {
    const wrap = document.createElement("label");
    wrap.textContent = spec.label + " ";
    const input = document.createElement(spec.area ? "textarea" : "input");
    input.name = spec.name;
    if (spec.area) input.rows = 2;
    else if (spec.money) { input.type = "text"; input.inputMode = "decimal"; input.autocomplete = "off"; input.placeholder = "e.g. 250.00"; }
    else if (spec.date) input.type = "date";
    else if (spec.order) { input.type = "number"; input.min = "0"; input.max = "2147483647"; input.step = "1"; input.placeholder = "0"; }
    else input.type = "text";
    if (spec.max) input.maxLength = spec.max;
    if (spec.required) input.required = true;
    const v = rec ? rec[spec.name] : null;
    input.value = v == null ? "" : String(v);
    wrap.append(input);
    return wrap;
  }

  function buildForm(kind, rec, readonly) {
    const s = SECTIONS[kind];
    const form = document.createElement("form");
    form.className = "wide-form form-grid";
    form.dataset.kind = kind;
    for (const spec of s.fields) form.append(field(spec, rec));
    const buttons = document.createElement("div");
    buttons.className = "form-buttons";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = rec ? `Save ${s.noun}` : `Add ${s.noun}`;
    buttons.append(submit);
    if (rec) {
      const cancel = makeRowButton("Cancel edit", "cancel", rec.id, "secondary");
      cancel.dataset.kind = kind;
      buttons.append(cancel);
    }
    form.append(buttons);
    if (readonly) for (const el of form.querySelectorAll("input,textarea,button")) el.disabled = true;
    return form;
  }

  function detailCell(kind, r) {
    const cell = document.createElement("td");
    const strong = document.createElement("strong");
    strong.textContent = r.name || r.title || (kind === "checkpoints" ? formatMoney(r.amount) : "");
    cell.append(strong);
    const lines = [];
    if (kind === "items") {
      lines.push(`Expected cost (planning): ${moneyOrDash(r.expected_cost)}`);
      lines.push(`Manual actual cost override (provisional): ${moneyOrDash(r.manual_actual_cost_override)}`);
    } else if (kind === "milestones") {
      lines.push(`Target date: ${r.target_date || "—"}`);
      lines.push(`Completed: ${r.completed_at ? new Date(r.completed_at).toLocaleString() : "—"}`);
    } else {
      lines.push(r.label ? `Label: ${r.label}` : "No label");
      lines.push(r.reached === true ? "Reached (per your manual progress)"
        : r.reached === false ? "Not reached yet" : "Reached: unknown (no manual progress)");
    }
    if (r.description) lines.push(r.description);
    if (r.notes) lines.push(`Notes: ${r.notes}`);
    for (const t of lines) {
      const small = document.createElement("small");
      small.className = "muted";
      small.textContent = t;
      cell.append(document.createElement("br"), small);
    }
    if (r.active === false) {
      const b = document.createElement("span");
      b.className = "badge"; b.textContent = "Archived";
      cell.append(" ", b);
    }
    return cell;
  }

  function section(kind, rows, readonly) {
    const s = SECTIONS[kind];
    const wrap = document.createElement("div");
    wrap.dataset.section = kind;
    const h = document.createElement("h3");
    h.textContent = s.heading;
    const note = document.createElement("p");
    note.className = "muted"; note.textContent = s.note;
    wrap.append(h, note);
    if (kind === "items") {
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.id = "composition-show-archived"; cb.checked = showArchivedItems;
      lab.append(cb, " Show archived items");
      wrap.append(lab);
    }
    const editRec = rows.find((r) => r.id === editing[kind]);
    wrap.append(buildForm(kind, editRec || null, readonly));
    const tw = document.createElement("div");
    tw.className = "table-wrap";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>Order</th><th>Details</th><th>Status</th><th>Actions</th></tr>";
    const tbody = document.createElement("tbody");
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = makeCell(`No ${s.heading.toLowerCase()} yet.`, "muted");
      td.colSpan = 4; tr.append(td); tbody.append(tr);
    }
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.dataset.recordId = String(r.id);
      if (r.active === false) tr.className = "inactive";
      const statusCell = document.createElement("td");
      if (kind === "checkpoints") statusCell.textContent = r.reached === true ? "Reached" : r.reached === false ? "Not reached" : "Unknown";
      else {
        const sel = document.createElement("select");
        sel.className = "composition-status";
        sel.dataset.kind = kind; sel.dataset.id = String(r.id);
        sel.setAttribute("aria-label", `Status for ${r.name || r.title}`);
        for (const v of options[kind === "items" ? "item_statuses" : "milestone_statuses"]) {
          const o = document.createElement("option");
          o.value = v; o.textContent = pretty(v); sel.append(o);
        }
        sel.value = r.status; sel.disabled = readonly;
        statusCell.append(sel);
      }
      const btns = [makeRowButton("Edit", "edit", r.id)];
      if (kind === "items") btns.push(makeRowButton(r.active ? "Archive" : "Reactivate", r.active ? "deactivate" : "reactivate", r.id, "secondary"));
      btns.push(makeRowButton("Delete", "delete", r.id, "secondary"));
      for (const b of btns) { b.dataset.kind = kind; if (readonly) b.disabled = true; }
      tr.append(makeCell(String(r.sort_order), "num"), detailCell(kind, r), statusCell, makeActionsCell(...btns));
      tbody.append(tr);
    }
    table.append(thead, tbody); tw.append(table); wrap.append(tw);
    return wrap;
  }

  function render() {
    if (sessionRecoveryActive || !data) return;
    const g = data.goal, readonly = g.active === false;
    title.textContent = `Composition: ${g.name}`;
    body.replaceChildren();
    const top = document.createElement("div");
    const bar = document.createElement("div");
    bar.className = "form-buttons";
    const closeBtn = makeRowButton("Close composition", "close", g.id, "secondary");
    bar.append(closeBtn);
    // Source navigation: Goal -> Projects filtered to this goal.
    const projectsLink = document.createElement("a");
    projectsLink.className = "button secondary goal-details-projects-link";
    projectsLink.href = `/projects?goal_id=${g.id}`;
    projectsLink.textContent = "View projects";
    bar.append(projectsLink);
    top.append(bar);
    if (readonly) {
      const p = document.createElement("p");
      p.className = "message error";
      p.textContent = "This goal is archived, so its composition is read only. Reactivate the goal from the goals table to make changes.";
      top.append(p);
    }
    body.append(top,
      section("items", data.items, readonly),
      section("milestones", data.milestones, readonly),
      section("checkpoints", data.checkpoints, readonly));
    for (const f of body.querySelectorAll("form[data-kind]")) {
      // Restore unsaved input (kept until a write succeeds or the user cancels).
      const d = drafts[f.dataset.kind];
      if (d && d.editId === editing[f.dataset.kind]) {
        for (const [n, v] of d.values) if (f.elements[n]) f.elements[n].value = v;
      }
    }
    panel.hidden = false;
  }

  const MONEY = /^\d+(\.\d{1,2})?$/;
  function payloadFrom(kind, form, rec) {
    const out = {};
    for (const spec of SECTIONS[kind].fields) {
      const raw = form.elements[spec.name].value.trim();
      if (spec.money) {
        if (raw && !MONEY.test(raw)) throw new Error("Enter amounts as plain dollars, such as 250 or 250.50.");
        out[spec.name] = raw || null;
      } else if (spec.order) {
        if (raw && !/^\d+$/.test(raw)) throw new Error("Order must be a whole number, 0 or more.");
        out[spec.name] = raw ? Number(raw) : (rec ? rec.sort_order : 0);
      } else out[spec.name] = raw || null;
    }
    return out;
  }

  async function write(fn, okText) {
    if (busy || sessionRecoveryActive) return false;
    const requestGoalId = goalId;
    busy = true;
    try {
      await fn();
      // A write belongs to the Goal where it started, even if Details for a
      // different Goal is opened while its request is in flight.
      if (sessionRecoveryActive || goalId !== requestGoalId) return false;
      busy = false;
      await load(false);
      if (sessionRecoveryActive || goalId !== requestGoalId) return false;
      say(okText, false);
      return true;
    } catch (error) {
      if (!sessionRecoveryActive && goalId === requestGoalId) say(error.message, true);
      return false;
    } finally { busy = false; }
  }

  body.addEventListener("input", (event) => {
    const form = event.target.closest("form[data-kind]");
    if (!form || sessionRecoveryActive) return;
    drafts[form.dataset.kind] = {
      editId: editing[form.dataset.kind],
      values: [...form.elements].filter((e) => e.name).map((e) => [e.name, e.value]),
    };
  });

  body.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target.closest("form[data-kind]");
    if (!form || busy || !data || data.goal.active === false) return;
    const kind = form.dataset.kind, s = SECTIONS[kind];
    const rec = data[kind].find((r) => r.id === editing[kind]) || null;
    let payload;
    try { payload = payloadFrom(kind, form, rec); } catch (e) { say(e.message, true); return; }
    const url = `${BASE}/${goalId}/${kind}`;
    const ok = await write(() => (rec ? apiPut(`${url}/${rec.id}`, payload) : apiPost(url, payload)),
      rec ? `${pretty(s.noun)} saved.` : `${pretty(s.noun)} added.`);
    if (ok) { editing[kind] = null; delete drafts[kind]; render(); }
    // On failure the form is untouched so nothing typed is lost.
  });

  body.addEventListener("click", async (event) => {
    const b = event.target.closest("button[data-action]");
    if (!b || busy || sessionRecoveryActive || !data) return;
    const action = b.dataset.action;
    if (action === "close") { close(); return; }
    const kind = b.dataset.kind;
    if (!kind || b.disabled) return;
    const rec = data[kind].find((r) => r.id === Number(b.dataset.id));
    if (!rec) return;
    const s = SECTIONS[kind], name = rec.name || rec.title || "this checkpoint";
    const url = `${BASE}/${goalId}/${kind}/${rec.id}`;
    if (action === "edit") { editing[kind] = rec.id; delete drafts[kind]; render(); return; }
    if (action === "cancel") { editing[kind] = null; delete drafts[kind]; render(); return; }
    if (action === "delete") {
      if (!window.confirm(`Permanently delete ${s.noun} "${name}"? This cannot be undone.`)) return;
      if (await write(() => apiDelete(url), `${pretty(s.noun)} deleted.`) && editing[kind] === rec.id) { editing[kind] = null; render(); }
    } else if (action === "deactivate" || action === "reactivate") {
      if (action === "deactivate" && !window.confirm(`Archive item "${name}"? Its status is not changed.`)) return;
      await write(() => apiPost(`${url}/${action}`), action === "deactivate" ? "Item archived." : "Item reactivated.");
    }
  });

  body.addEventListener("change", async (event) => {
    const t = event.target;
    if (t.id === "composition-show-archived") {
      showArchivedItems = t.checked;
      load(false);
      return;
    }
    if (!t.matches("select.composition-status") || busy) return;
    const kind = t.dataset.kind, id = Number(t.dataset.id);
    const ok = await write(() => apiPost(`${BASE}/${goalId}/${kind}/${id}/status`, { status: t.value }), "Status updated.");
    if (!ok && data) render();
  });

  return {
    open(id) { goalId = Number(id); drafts = {}; for (const k in editing) editing[k] = null; msg.hidden = true; load(true); },
    // Called after any top-level goal change; closes itself if the goal is gone.
    refresh() { if (goalId !== null && !busy) load(false); },
    closeIf(id) { if (goalId === Number(id)) close(); },
  };
})();
