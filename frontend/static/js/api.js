/*
 * Shared helpers for talking to the Serenity backend.
 *
 * RULE: JavaScript in Serenity only fetches and displays data.
 * All financial calculations happen in Python (services/).
 */

let sessionRecoveryActive = false;

// This channel carries only a fixed event name, never account data or tokens.
// Browsers without BroadcastChannel still recheck when the tab is revisited.
try {
  const sessionChannel = new BroadcastChannel("serenity-session");
  sessionChannel.onmessage = (event) => {
    if (event.data === "signed-out") showSessionRecovery();
  };
} catch {
  // BroadcastChannel can be unavailable in restricted browser contexts.
}

let sessionCheckTimer;
let sessionCheckInFlight = false;
let lastSessionCheck = -Infinity;
const sessionCheckInterval = 15000;

function scheduleSessionCheck() {
  if (document.visibilityState !== "visible" || sessionRecoveryActive ||
      sessionCheckInFlight) return;
  clearTimeout(sessionCheckTimer);
  // Coalesce focus/visibility events and keep at least 15 seconds between
  // checks. A trailing check ensures a quick tab revisit is not lost.
  const delay = Math.max(250, sessionCheckInterval - (Date.now() - lastSessionCheck));
  sessionCheckTimer = setTimeout(recheckSession, delay);
}

async function recheckSession() {
  if (document.visibilityState !== "visible" || sessionRecoveryActive ||
      sessionCheckInFlight) return;
  sessionCheckInFlight = true;
  lastSessionCheck = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch("/serenity-api/auth/me", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (response.status === 401) showSessionRecovery();
  } catch {
    // An outage is not proof of revocation. No redirect or automatic retry;
    // a later tab revisit can check again.
  } finally {
    clearTimeout(timeout);
    sessionCheckInFlight = false;
  }
}

document.addEventListener("visibilitychange", scheduleSessionCheck);
window.addEventListener("focus", scheduleSessionCheck);
window.addEventListener("pageshow", (event) => {
  if (event.persisted) scheduleSessionCheck();
});

// Use only local paths for the return destination. In particular, //host and
// backslashes can be interpreted by browsers as an external navigation.
function safeReturnPath(value) {
  if (typeof value !== "string" || !value.startsWith("/") ||
      value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value)) {
    return "/";
  }
  try {
    const target = new URL(value, window.location.origin);
    if (target.origin !== window.location.origin ||
        target.pathname === "/sign-in" || target.pathname === "/sign-out") {
      return "/";
    }
    return target.pathname + target.search;
  } catch {
    return "/";
  }
}

function showSessionRecovery() {
  if (sessionRecoveryActive) return;
  sessionRecoveryActive = true;
  clearTimeout(sessionCheckTimer);
  const main = document.querySelector("main");
  if (!main) return;
  // Remove all previously rendered financial values AND unsaved form fields,
  // rather than simply hiding them where they could remain in the DOM.
  main.replaceChildren();
  const panel = document.createElement("section");
  panel.className = "panel session-recovery";
  panel.setAttribute("role", "alert");
  panel.setAttribute("aria-live", "assertive");
  const heading = document.createElement("h1");
  heading.tabIndex = -1;
  heading.textContent = "Your session has ended";
  const explanation = document.createElement("p");
  explanation.textContent = "Your financial information has been cleared from this page. Sign in again to continue. If sign-in is temporarily unavailable, try again later.";
  const actions = document.createElement("div");
  actions.className = "form-buttons";
  const signIn = document.createElement("a");
  signIn.className = "button";
  signIn.textContent = "Sign in again";
  signIn.href = "/sign-in?next=" + encodeURIComponent(
    safeReturnPath(window.location.pathname + window.location.search)
  );
  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "Retry session";
  const message = document.createElement("p");
  message.className = "muted";
  message.setAttribute("role", "status");
  retry.addEventListener("click", async () => {
    retry.disabled = true;
    message.textContent = "Checking your session…";
    try {
      // Only a deliberate click retries. Never reload on a failed check:
      // an unavailable Clerk backend must not cause a redirect loop.
      const response = await fetch("/serenity-api/auth/me");
      if (response.ok) {
        window.location.assign(safeReturnPath(
          window.location.pathname + window.location.search
        ));
        return;
      }
      message.textContent = "Your session is still unavailable. Sign in again or try later.";
    } catch {
      message.textContent = "Unable to check your session. Please try again later.";
    } finally {
      retry.disabled = false;
    }
  });
  actions.append(signIn, retry);
  panel.append(heading, explanation, actions, message);
  main.append(panel);
  heading.focus();
}

function ensureSessionActive() {
  if (sessionRecoveryActive) throw new Error("Your session has ended.");
}

// Send a GET request and return the parsed JSON.
async function apiGet(url) {
  ensureSessionActive();
  const response = await fetch(url);
  return handleResponse(response);
}

// Send a POST request with a JSON body and return the parsed JSON.
async function apiPost(url, body = {}) {
  ensureSessionActive();
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

async function apiPut(url, body) {
  ensureSessionActive();
  const response = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

async function apiDelete(url) {
  ensureSessionActive();
  const response = await fetch(url, { method: "DELETE" });
  return handleResponse(response);
}

// If the server reports an error, turn it into a readable message.
async function handleResponse(response) {
  if (response.status === 401) {
    showSessionRecovery();
    throw new Error("Your session has ended.");
  }
  ensureSessionActive();
  const data = await response.json().catch(() => null);
  // Sign-out may arrive while a response body is still being read.
  ensureSessionActive();
  if (response.ok) {
    return data;
  }
  throw new Error(describeError(data, response.status));
}

// FastAPI validation errors (HTTP 422) look like:
//   { "detail": [ { "loc": [...], "msg": "Value error, Name is required" } ] }
// Other errors look like: { "detail": "Account not found" }
function describeError(data, status) {
  if (data && Array.isArray(data.detail)) {
    return data.detail
      .map((problem) => problem.msg.replace(/^Value error, /, ""))
      .join(". ");
  }
  if (data && typeof data.detail === "string") {
    return data.detail;
  }
  return `Request failed (HTTP ${status})`;
}

// Display only: the API sends money as strings like "1234.50".
// Formatting it as "$1,234.50" is presentation, not calculation.
function formatMoney(amountString) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(Number(amountString));
}

// Build a table cell safely. Using textContent (not innerHTML) means
// text typed by the user can never be run as HTML/JavaScript.
function makeCell(text, className) {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) {
    cell.className = className;
  }
  return cell;
}

function makeRowButton(label, action, id, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.dataset.action = action;
  button.dataset.id = String(id);
  if (className) button.className = className;
  return button;
}

function makeActionsCell(...buttons) {
  const cell = document.createElement("td");
  const group = document.createElement("div");
  group.className = "row-actions";
  group.append(...buttons);
  cell.appendChild(group);
  return cell;
}

function showMessage(target, text, isError) {
  target.textContent = text;
  target.className = isError ? "message error" : "message success";
  target.hidden = false;
}

// The responsive navigation is progressively enhanced: desktop links work
// without JavaScript, while the phone menu is keyboard- and screen-reader-safe.
document.querySelectorAll(".nav-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    const header = button.closest(".topbar");
    const open = header.classList.toggle("nav-open");
    button.setAttribute("aria-expanded", String(open));
  });
  button.closest(".topbar").querySelectorAll(".site-nav a").forEach((link) => {
    link.addEventListener("click", () => {
      button.closest(".topbar").classList.remove("nav-open");
      button.setAttribute("aria-expanded", "false");
    });
  });
  button.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      button.closest(".topbar").classList.remove("nav-open");
      button.setAttribute("aria-expanded", "false");
    }
  });
});
