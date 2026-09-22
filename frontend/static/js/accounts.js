/*
 * Accounts page.
 *
 * Flow when you submit the form:
 *   form -> apiPost("/api/accounts") -> FastAPI validates -> service saves
 *   -> SQLite -> JSON response -> we reload the table.
 */

const form = document.getElementById("account-form");
const formMessage = document.getElementById("form-message");
const accountsBody = document.getElementById("accounts-body");

// Fill a <select> with options that come from the backend.
function fillSelect(select, values) {
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

async function loadOptions() {
  const options = await apiGet("/api/accounts/options");
  fillSelect(form.elements.account_type, options.account_types);
  fillSelect(form.elements.classification, options.classifications);
}

async function loadAccounts() {
  const accounts = await apiGet("/api/accounts");
  accountsBody.replaceChildren();

  if (accounts.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("No accounts yet. Add one above.", "muted");
    cell.colSpan = 5;
    row.appendChild(cell);
    accountsBody.appendChild(row);
    return;
  }

  for (const account of accounts) {
    const row = document.createElement("tr");
    row.appendChild(makeCell(account.name));
    row.appendChild(makeCell(account.account_type));
    row.appendChild(makeCell(account.classification));
    row.appendChild(makeCell(account.institution || "—"));
    row.appendChild(makeCell(formatMoney(account.current_balance), "num"));
    accountsBody.appendChild(row);
  }
}

function showMessage(text, isError) {
  formMessage.textContent = text;
  formMessage.className = isError ? "message error" : "message success";
  formMessage.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); // stop the browser from reloading the page

  // Read the form. Money is sent as a STRING so no precision is lost
  // turning it into a JavaScript number. Python reads it as a Decimal.
  const body = {
    name: form.elements.name.value,
    account_type: form.elements.account_type.value,
    classification: form.elements.classification.value,
    opening_balance: form.elements.opening_balance.value || "0",
    institution: form.elements.institution.value,
    notes: form.elements.notes.value,
  };

  try {
    const created = await apiPost("/api/accounts", body);
    showMessage(`Added "${created.name}".`, false);
    form.reset();
    await loadAccounts();
  } catch (error) {
    showMessage(error.message, true);
  }
});

// Run when the page loads.
loadOptions()
  .then(loadAccounts)
  .catch((error) => showMessage(error.message, true));
