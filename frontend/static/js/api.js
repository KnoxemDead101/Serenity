/*
 * Shared helpers for talking to the Serenity backend.
 *
 * RULE: JavaScript in Serenity only fetches and displays data.
 * All financial calculations happen in Python (services/).
 */

// Send a GET request and return the parsed JSON.
async function apiGet(url) {
  const response = await fetch(url);
  return handleResponse(response);
}

// Send a POST request with a JSON body and return the parsed JSON.
async function apiPost(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

async function apiPut(url, body) {
  const response = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

async function apiDelete(url) {
  const response = await fetch(url, { method: "DELETE" });
  return handleResponse(response);
}

// If the server reports an error, turn it into a readable message.
async function handleResponse(response) {
  const data = await response.json().catch(() => null);
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
