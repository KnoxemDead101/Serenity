/* System page: fetches and displays health evidence only. No calculations. */
(function () {
  const $ = (id) => document.getElementById(id);
  const titles = {
    NORMAL: "Normal (limited observation)",
    READ_ONLY: "Read-only",
    UNAVAILABLE: "Unavailable",
  };
  let loadToken = 0;
  let sessionEnded = false;

  function text(id, value) { $(id).textContent = value; }

  function clearEvidence() {
    $("system-checks").replaceChildren();
    $("system-meta").hidden = true;
    $("system-checks-panel").hidden = true;
    $("system-migration-panel").hidden = true;
    $("data-health-panel").hidden = true;
    clearHistory();
    if (window.SerenityVerification) window.SerenityVerification.clear();
    $("data-health-readings").replaceChildren();
    ["data-health-message", "data-health-checked"].forEach((id) => text(id, ""));
    ["system-writes", "system-checked", "system-version",
      "system-migration-status", "system-migration-message",
      "system-migration-expected", "system-migration-observed"].forEach((id) => text(id, ""));
  }

  // History is supplementary evidence: it never replaces valid current health.
  let healthHistory = null;
  function clearHistory() {
    healthHistory = null;
    $("system-history").replaceChildren();
    text("system-history-note", "");
    $("system-history-panel").hidden = true;
  }

  const HIST_ENUMS = {
    kind: ["BASELINE", "TRANSITION"],
    state: ["NORMAL", "READ_ONLY", "UNAVAILABLE"],
    database: ["AVAILABLE", "UNAVAILABLE"],
    schema: ["AVAILABLE", "UNAVAILABLE"],
    write_safety: ["AVAILABLE", "READ_ONLY", "UNAVAILABLE"],
    migration: ["CURRENT", "BEHIND", "UNVERIFIED"],
  };
  function validHistory(h) {
    if (!h || typeof h !== "object" || !["AVAILABLE", "UNAVAILABLE"].includes(h.status) ||
        h.retention_days !== 90 || h.max_entries !== 200 || !Array.isArray(h.entries) ||
        h.entries.length > 200) return false;
    if (h.status === "UNAVAILABLE" && h.entries.length !== 0) return false;
    return h.entries.every((e) => e && typeof e === "object" &&
      typeof e.checked_at === "string" && Number.isFinite(Date.parse(e.checked_at)) &&
      Object.keys(HIST_ENUMS).every((k) => HIST_ENUMS[k].includes(e[k])));
  }
  // Health may omit history (older fixtures); an invalid value is ignored, not fatal.
  function readHealthHistory(d) {
    const h = d && d.history;
    if (h && typeof h === "object" && ["AVAILABLE", "UNAVAILABLE"].includes(h.status) &&
        typeof h.recorded === "boolean") return { status: h.status, recorded: h.recorded };
    return null;
  }

  function renderHistory(h) {
    const list = $("system-history");
    list.replaceChildren();
    let note;
    if (h.status === "UNAVAILABLE") {
      note = "Status history could not be read. This is not the same as having no history.";
    } else if (h.entries.length === 0) {
      note = "No status history has been recorded yet.";
    } else {
      note = h.entries.length + " observation" + (h.entries.length === 1 ? "" : "s") + " shown, newest first.";
    }
    if (healthHistory && healthHistory.status === "UNAVAILABLE") {
      note += " The latest check could not be saved to history.";
    }
    text("system-history-note", note);
    h.entries.forEach((e) => {
      const li = document.createElement("li");
      li.dataset.kind = e.kind;
      const head = document.createElement("div");
      head.className = "sys-check-head";
      const time = document.createElement("time");
      time.dateTime = e.checked_at;
      time.textContent = new Date(e.checked_at).toLocaleString() + " (" + e.checked_at + ")";
      const kind = document.createElement("span");
      kind.className = "sys-check-key";
      kind.textContent = e.kind === "BASELINE" ? "Baseline" : "Changed";
      head.append(time, kind);
      const row = document.createElement("div");
      row.className = "sys-hist-statuses";
      [["state", "State"], ["database", "Database"], ["schema", "Schema"],
        ["write_safety", "Write safety"], ["migration", "Migration"]].forEach(([k, label]) => {
        const s = document.createElement("span");
        s.append(label + ": ", pill(e[k]));
        row.append(s);
      });
      li.append(head, row);
      list.append(li);
    });
    $("system-history-panel").hidden = false;
  }

  async function loadHistory(token) {
    if (sessionEnded || sessionRecoveryActive || !$("system-history")) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/serenity-api/system/history", {
        cache: "no-store", credentials: "same-origin", signal: controller.signal,
      });
      ensureSessionActive();
      if (token !== loadToken) return;
      if (response.status === 401) { sessionEnded = true; clearEvidence(); showSessionRecovery(); return; }
      if (accountIsInactive(response)) { sessionEnded = true; clearEvidence(); showSessionRecovery("inactive"); return; }
      if (!response.ok) throw new Error("status");
      const data = await response.json();
      ensureSessionActive();
      if (token !== loadToken || sessionEnded) return;
      if (!validHistory(data)) throw new Error("shape");
      renderHistory(data);
    } catch {
      if (token === loadToken && !sessionEnded && $("system-history")) {
        clearHistory();
        text("system-history-note", "Status history could not be loaded. Current health above is unaffected. Use Refresh to try again.");
        $("system-history-panel").hidden = false;
      }
    } finally {
      clearTimeout(timer);
    }
  }

  function pill(value) {
    const span = document.createElement("span");
    span.className = "sys-pill";
    span.dataset.v = String(value);
    span.textContent = String(value).replace(/_/g, " ");
    return span;
  }

  function showUnavailable(note) {
    clearEvidence();
    $("system-status").dataset.state = "UNAVAILABLE";
    text("sys-state-title", "Unavailable");
    text("system-message", "Serenity's state could not be read, so nothing is shown as healthy. Your records have not been judged empty or lost; their state is unknown.");
    text("system-refresh-note", note || "");
  }

  const DH_KEYS = ["accounts", "bills", "debts", "investments", "income"];
  const DH_STATUS = ["MISSING", "MANUAL", "PARTIAL", "STALE", "INCONSISTENT", "UNAVAILABLE"];
  const DH_DOMAINS = {
    accounts: ["ACTUAL", "/accounts"], bills: ["PLANNED", "/finances"],
    debts: ["ACTUAL", "/finances"], investments: ["MIXED", "/finances"],
    income: ["PLANNED", "/income"],
  };
  function validHealth(h) {
    const isText = (v) => typeof v === "string" && v.length > 0;
    if (!h || typeof h !== "object" || !isText(h.message) || !isText(h.checked_at) ||
        !Number.isFinite(Date.parse(h.checked_at)) || !Array.isArray(h.readings) ||
        h.readings.length !== DH_KEYS.length) return false;
    if (!DH_KEYS.every((k) => h.readings.filter((r) => r && r.key === k).length === 1)) return false;
    return h.readings.every((r) => {
      if (!r || !isText(r.label) || !DH_STATUS.includes(r.status) ||
          r.basis !== DH_DOMAINS[r.key][0] || r.source !== DH_DOMAINS[r.key][1]) return false;
      const unreadable = r.status === "UNAVAILABLE" || r.status === "INCONSISTENT";
      if (unreadable) { if (r.record_count !== null) return false; }
      else if (!Number.isSafeInteger(r.record_count) || r.record_count < 0 ||
        (r.status === "MISSING") !== (r.record_count === 0)) return false;
      if (!Array.isArray(r.findings) || r.findings.length === 0 || !r.findings.every((f) =>
        f && isText(f.code) && isText(f.message) && [...DH_STATUS, "UNKNOWN"].includes(f.status))) return false;
      if (unreadable || r.status === "MISSING") return r.findings.every((f) => f.status === r.status);
      if (!r.findings.every((f) => ["MANUAL", "PARTIAL", "STALE", "UNKNOWN"].includes(f.status))) return false;
      // Match the server's evidence labels, never recompute financial values.
      const expected = r.findings.some((f) => f.status === "PARTIAL") ? "PARTIAL"
        : r.findings.some((f) => f.status === "STALE") ? "STALE"
        : r.findings.some((f) => f.status === "UNKNOWN") ? "PARTIAL" : "MANUAL";
      return r.status === expected;
    });
  }

  function renderHealth(h) {
    text("data-health-message", h.message);
    const when = new Date(h.checked_at);
    const t = $("data-health-checked");
    t.textContent = when.toLocaleString() + " (" + h.checked_at + ")";
    t.dateTime = h.checked_at;
    const list = $("data-health-readings");
    list.replaceChildren();
    h.readings.forEach((r) => {
      const li = document.createElement("li");
      li.dataset.domain = r.key;
      li.dataset.status = r.status;
      const head = document.createElement("div");
      head.className = "sys-check-head";
      const name = document.createElement("strong");
      name.textContent = r.label;
      const basis = document.createElement("span");
      basis.className = "sys-check-key";
      basis.textContent = "Basis: " + r.basis.toLowerCase();
      head.append(name, pill(r.status), basis);
      const count = document.createElement("p");
      count.className = "dh-count";
      count.textContent = r.record_count === null ? "Count: Unknown"
        : "Count: " + r.record_count + " recorded" + (r.record_count === 0 ? " (not a confirmed real-world zero)" : "");
      const ul = document.createElement("ul");
      ul.className = "dh-findings";
      r.findings.forEach((f) => {
        const fi = document.createElement("li");
        fi.dataset.code = f.code;
        fi.append(pill(f.status), " ", f.message);
        ul.append(fi);
      });
      const a = document.createElement("a");
      a.href = r.source;
      a.className = "dh-source";
      a.textContent = "Review in " + r.source;
      li.append(head, count, ul, a);
      list.append(li);
    });
    $("data-health-panel").hidden = false;
  }

  function validEvidence(d) {
    const states = ["NORMAL", "READ_ONLY", "UNAVAILABLE"];
    const statuses = ["AVAILABLE", "READ_ONLY", "UNAVAILABLE", "UNVERIFIED", "MANUAL"];
    const keys = ["database", "schema", "write_safety", "authentication", "backups", "market_data"];
    const isText = (value) => typeof value === "string" && value.length > 0;
    if (!d || !states.includes(d.state) ||
        typeof d.writes_enabled !== "boolean" ||
        d.writes_enabled !== (d.state === "NORMAL") ||
        !isText(d.message) || !isText(d.application_version) ||
        !isText(d.checked_at) || !Number.isFinite(Date.parse(d.checked_at)) ||
        !Array.isArray(d.checks) || d.checks.length !== keys.length) return false;
    if (!keys.every((key) => d.checks.filter((c) => c && c.key === key).length === 1) ||
        !d.checks.every((c) => statuses.includes(c.status) && isText(c.label) && isText(c.message))) return false;
    if (!validHealth(d.data_health)) return false;
    const m = d.migration;
    return m && ["CURRENT", "BEHIND", "UNVERIFIED"].includes(m.status) &&
      isText(m.message) &&
      (m.expected_revision === null || isText(m.expected_revision)) &&
      (m.observed_revision === null || isText(m.observed_revision));
  }

  function render(d) {
    const state = ["NORMAL", "READ_ONLY", "UNAVAILABLE"].includes(d.state) ? d.state : "UNAVAILABLE";
    $("system-status").dataset.state = state;
    text("sys-state-title", titles[state]);
    text("system-message", String(d.message ?? ""));
    text("system-writes", d.writes_enabled === true ? "Enabled" : "Paused");
    const when = new Date(d.checked_at);
    const t = $("system-checked");
    t.textContent = isNaN(when) ? String(d.checked_at ?? "") : when.toLocaleString() + " (" + d.checked_at + ")";
    if (!isNaN(when)) t.dateTime = d.checked_at;
    text("system-version", String(d.application_version ?? ""));
    $("system-meta").hidden = false;

    const list = $("system-checks");
    list.replaceChildren();
    (Array.isArray(d.checks) ? d.checks : []).forEach((c) => {
      const li = document.createElement("li");
      li.dataset.status = String(c.status);
      li.dataset.key = String(c.key);
      const head = document.createElement("div");
      head.className = "sys-check-head";
      const name = document.createElement("strong");
      name.textContent = String(c.label);
      const key = document.createElement("span");
      key.className = "sys-check-key";
      key.textContent = String(c.key);
      head.append(name, pill(c.status), key);
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = String(c.message ?? "");
      li.append(head, p);
      list.append(li);
    });
    $("system-checks-panel").hidden = false;

    const m = d.migration || {};
    const ms = $("system-migration-status");
    ms.replaceChildren(pill(m.status));
    text("system-migration-message", String(m.message ?? ""));
    text("system-migration-expected", m.expected_revision == null ? "Not observed (unknown)" : String(m.expected_revision));
    text("system-migration-observed", m.observed_revision == null ? "Not observed (unknown)" : String(m.observed_revision));
    $("system-migration-panel").hidden = false;
    renderHealth(d.data_health);
  }

  async function load() {
    if (sessionEnded || sessionRecoveryActive || !$("system-status")) return;
    const token = ++loadToken;
    const btn = $("system-refresh");
    btn.disabled = true;
    // Drop any previous result first so a failed refresh can never show stale success.
    clearEvidence();
    $("system-status").dataset.state = "loading";
    $("system-status").setAttribute("aria-busy", "true");
    text("sys-state-title", "Checking…");
    text("system-message", "Asking the server for its current state.");
    text("system-refresh-note", "");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/serenity-api/system/health", {
        cache: "no-store", credentials: "same-origin", signal: controller.signal,
      });
      ensureSessionActive();
      if (token !== loadToken) return;
      if (response.status === 401) { sessionEnded = true; clearEvidence(); showSessionRecovery(); return; }
      if (accountIsInactive(response)) { sessionEnded = true; clearEvidence(); showSessionRecovery("inactive"); return; }
      if (!response.ok) throw new Error("status");
      const data = await response.json();
      ensureSessionActive();
      if (token !== loadToken || sessionEnded) return;
      if (!validEvidence(data)) throw new Error("shape");
      render(data);
      healthHistory = readHealthHistory(data);
      // Independent request: its failure must not replace the valid health above.
      await loadHistory(token);
      // Also independent: owner verification review never alters health above.
      if (window.SerenityVerification && token === loadToken && !sessionEnded) {
        await window.SerenityVerification.load(() => token === loadToken && !sessionEnded && !sessionRecoveryActive);
      }
    } catch {
      if (token === loadToken && !sessionEnded && $("system-status")) showUnavailable("The health check failed. Use Refresh to try again.");
    } finally {
      clearTimeout(timer);
      if (token === loadToken && $("system-refresh")) {
        btn.disabled = false;
        $("system-status").removeAttribute("aria-busy");
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("system-refresh").addEventListener("click", load);
    document.addEventListener("serenity-verification-changed", load);
    load();
  });
})();
