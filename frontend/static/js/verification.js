/* Owner verification review: fetches, displays and saves owner evidence only.
   Amounts are server strings shown as-is. No financial calculations. */
(function () {
  const $ = (id) => document.getElementById(id);
  const KINDS = { account_balance: "Derived account balance", debt_balance: "Entered debt balance",
    legacy_valuation: "Entered legacy valuation", opening_valuation: "Original entered opening valuation" };
  const STATUSES = ["UNKNOWN", "VERIFIED", "STALE", "CHANGED", "INCONSISTENT"];
  const STATUS_TEXT = {
    UNKNOWN: "Unknown - never verified",
    VERIFIED: "Verified by you",
    STALE: "Stale - 30 or more UTC days old (decided by the server)",
    CHANGED: "Changed since you verified it",
    INCONSISTENT: "Inconsistent - the saved evidence does not fit this item",
  };
  let gen = 0;
  let controller = null;

  const present = () => !!$("system-verification-panel");
  const isText = (v) => typeof v === "string" && v.length > 0;
  const isTs = (v) => isText(v) && /(?:Z|\+00:00)$/.test(v) && Number.isFinite(Date.parse(v));
  const isDate = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) &&
    Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v;
  const isId = (v) => Number.isSafeInteger(v) && v > 0;
  const isKind = (v) => Object.prototype.hasOwnProperty.call(KINDS, v);

  function validEvidence(e, withKey) {
    return e && typeof e === "object" && isId(e.id) && isDate(e.as_of) &&
      typeof e.evidence === "string" && isTs(e.recorded_at) &&
      (!withKey || (isKind(e.kind) && isId(e.target_id)));
  }
  function validData(d) {
    return d && isTs(d.checked_at) && Array.isArray(d.targets) && Array.isArray(d.retained) &&
      d.targets.every((t) => t && isKind(t.kind) && isId(t.target_id) && isText(t.label) &&
        typeof t.amount === "string" && /^-?\d+\.\d{2}$/.test(t.amount) &&
        /^[0-9a-f]{64}$/.test(t.snapshot) && STATUSES.includes(t.status) &&
        (t.verification === null || validEvidence(t.verification, false)) &&
        (t.status === "UNKNOWN") === (t.verification === null) &&
        (t.status === "INCONSISTENT" || t.verification === null ||
          (t.verification.evidence.trim().length > 0 && t.verification.evidence.length <= 1000 &&
           t.verification.as_of <= d.checked_at.slice(0, 10) &&
           Date.parse(t.verification.recorded_at) <= Date.parse(d.checked_at)))) &&
      new Set(d.targets.map((t) => t.kind + ":" + t.target_id)).size === d.targets.length &&
      d.retained.every((r) => validEvidence(r, true));
  }

  function clear() {
    gen++;
    if (controller) controller.abort();
    controller = null;
    if (!present()) return;
    $("verification-targets").replaceChildren();
    $("verification-retained").replaceChildren();
    $("verification-retained").hidden = true;
    $("verification-retained-title").hidden = true;
    $("verification-message").textContent = "";
    $("verification-checked").textContent = "";
    $("system-verification-panel").hidden = true;
  }

  function el(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt !== undefined) n.textContent = txt;
    return n;
  }
  function pill(v) {
    const s = el("span", "sys-pill", v.replace(/_/g, " "));
    s.dataset.v = v;
    return s;
  }
  function evidenceBlock(e) {
    const box = el("div", "ver-evidence");
    box.append(el("p", "", "Checked as of: " + e.as_of),
      el("p", "", "Your evidence: " + e.evidence),
      el("p", "muted", "Recorded at " + e.recorded_at));
    return box;
  }

  async function request(fn, myGen, note) {
    // Returns true only when the result is still current and ok.
    try {
      await fn();
      if (myGen !== gen || !present()) return false;
      return true;
    } catch (err) {
      if (myGen !== gen || !present()) return false;
      note.textContent = err && err.message ? err.message : "The request failed.";
      return null;
    }
  }

  function targetItem(t) {
    const li = el("li");
    li.dataset.kind = t.kind;
    li.dataset.targetId = String(t.target_id);
    li.dataset.status = t.status;
    const head = el("div", "sys-check-head");
    head.append(el("strong", "", t.label), pill(t.status), el("span", "sys-check-key", KINDS[t.kind]));
    const amt = el("p", "ver-amount", "Amount shown: $" + t.amount);
    amt.dataset.role = "amount";
    const st = el("p", "muted", STATUS_TEXT[t.status]);
    li.append(head, amt, st);
    li.append(t.verification ? evidenceBlock(t.verification)
      : el("p", "muted", "No evidence saved. Unknown, never verified."));
    li.append(el("p", "muted ver-snapshot", "Snapshot: " + t.snapshot));

    const base = "ver-" + t.kind + "-" + t.target_id;
    const form = el("form", "ver-form");
    form.id = base + "-form";
    form.noValidate = false;
    const dl = el("label", "", "As-of date of the checked fact (UTC)");
    const date = document.createElement("input");
    date.type = "date"; date.required = true; date.id = base + "-date"; date.name = "as_of";
    dl.append(date);
    const el2 = el("label", "", "Evidence (required, up to 1000 characters)");
    const ev = document.createElement("textarea");
    ev.required = true; ev.maxLength = 1000; ev.rows = 3; ev.id = base + "-evidence"; ev.name = "evidence";
    el2.append(ev);
    const cl = el("label", "ver-confirm");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.required = true; cb.id = base + "-confirm";
    cl.append(cb, el("span", "", "I, the owner, have checked the displayed amount and snapshot above."));
    const note = el("span", "muted"); note.id = base + "-note"; note.setAttribute("role", "status");
    const buttons = el("div", "form-buttons");
    const save = el("button", "", t.verification ? "Replace evidence" : "Save evidence");
    save.type = "submit"; save.id = base + "-save";
    buttons.append(save);
    let del = null;
    if (t.verification) {
      del = el("button", "", "Delete evidence");
      del.type = "button"; del.id = base + "-delete";
      buttons.append(del);
    }
    buttons.append(note);
    form.append(dl, el2, cl, buttons);
    li.append(form);

    const lock = (on) => { save.disabled = on; if (del) del.disabled = on; };
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      note.textContent = "";
      const evidence = ev.value.trim();
      if (!date.value) { note.textContent = "Choose the date you checked."; return; }
      if (!evidence) { note.textContent = "Evidence is required."; return; }
      if (!cb.checked) { note.textContent = "Confirm that you checked the displayed snapshot."; return; }
      const myGen = gen;
      lock(true);
      note.textContent = "Saving...";
      const ok = await request(() => apiPut("/serenity-api/system/verifications/" + t.kind + "/" + t.target_id,
        { as_of: date.value, evidence, snapshot: t.snapshot }), myGen, note);
      if (ok === true) await reload(myGen, "Evidence saved for " + t.label + ".", true);
      else if (ok === null) {
        if (/changed|reload/i.test(note.textContent)) { await reload(myGen, "This item changed. Reloaded; check the new snapshot before saving."); }
        else lock(false);
      }
    });
    if (del) del.addEventListener("click", async () => {
      if (!window.confirm("Delete this saved evidence?")) return;
      note.textContent = "";
      const myGen = gen;
      lock(true);
      const ok = await request(() => apiDelete("/serenity-api/system/verifications/" + t.verification.id), myGen, note);
      if (ok === true) await reload(myGen, "Evidence deleted for " + t.label + ".", true);
      else if (ok === null) lock(false);
    });
    return li;
  }

  function retainedItem(r) {
    const li = el("li");
    li.dataset.id = String(r.id);
    const head = el("div", "sys-check-head");
    head.append(el("strong", "", KINDS[r.kind] + " #" + r.target_id), el("span", "sys-check-key", "source no longer current"));
    li.append(head, evidenceBlock(r));
    const note = el("span", "muted"); note.setAttribute("role", "status");
    const del = el("button", "", "Remove retained evidence");
    del.type = "button"; del.id = "ver-retained-" + r.id + "-delete";
    del.addEventListener("click", async () => {
      if (!window.confirm("Remove this retained evidence?")) return;
      const myGen = gen;
      del.disabled = true;
      const ok = await request(() => apiDelete("/serenity-api/system/verifications/" + r.id), myGen, note);
      if (ok === true) await reload(myGen, "Retained evidence removed.", true);
      else if (ok === null) del.disabled = false;
    });
    li.append(del, note);
    return li;
  }

  function render(d) {
    const tl = $("verification-targets");
    tl.replaceChildren();
    d.targets.forEach((t) => tl.append(targetItem(t)));
    const rl = $("verification-retained");
    rl.replaceChildren();
    d.retained.forEach((r) => rl.append(retainedItem(r)));
    rl.hidden = $("verification-retained-title").hidden = d.retained.length === 0;
    $("verification-checked").textContent = new Date(d.checked_at).toLocaleString() + " (" + d.checked_at + ")";
    $("verification-checked").dateTime = d.checked_at;
    $("verification-message").textContent = d.targets.length === 0
      ? "Nothing is available to review yet." : "";
    $("system-verification-panel").hidden = false;
  }

  function fail(msg) {
    clearList();
    $("verification-message").textContent = msg;
    $("system-verification-panel").hidden = false;
  }
  function clearList() {
    $("verification-targets").replaceChildren();
    $("verification-retained").replaceChildren();
    $("verification-retained").hidden = true;
    $("verification-retained-title").hidden = true;
    $("verification-checked").textContent = "";
  }

  // isCurrent lets system.js tie this request to its own load token.
  async function load(isCurrent) {
    if (!present() || typeof sessionRecoveryActive !== "undefined" && sessionRecoveryActive) return;
    const myGen = ++gen;
    if (controller) controller.abort();
    controller = new AbortController();
    const mine = controller;
    const timer = setTimeout(() => mine.abort(), 10000);
    const live = () => myGen === gen && present() && (!isCurrent || isCurrent());
    clearList();
    try {
      const response = await fetch("/serenity-api/system/verifications", {
        cache: "no-store", credentials: "same-origin", signal: mine.signal });
      if (!live()) return;
      if (response.status === 401) { clear(); showSessionRecovery(); return; }
      if (accountIsInactive(response)) { clear(); showSessionRecovery("inactive"); return; }
      if (!response.ok) throw new Error("status");
      const data = await response.json();
      if (!live()) return;
      if (!validData(data)) throw new Error("shape");
      render(data);
    } catch {
      if (live()) fail("Owner verification could not be loaded. No evidence is shown. Use Refresh to try again.");
    } finally {
      clearTimeout(timer);
    }
  }

  // After a save or delete, reload and then show the outcome only if still current.
  async function reload(myGen, message, updateHealth) {
    if (myGen !== gen || !present()) return;
    if (updateHealth) {
      // Reobserve both the redacted reminders and the private review controls.
      document.dispatchEvent(new Event("serenity-verification-changed"));
      return;
    }
    const expectedGen = gen + 1;
    await load();
    if (gen === expectedGen && present() && $("system-verification-panel") && !$("system-verification-panel").hidden) {
      const m = $("verification-message");
      if (m.textContent === "") m.textContent = message;
    }
  }

  window.SerenityVerification = { load, clear };
})();
