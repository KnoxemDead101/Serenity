/*
 * Accounts page: accounts, transactions and their correction history.
 *
 * Flow when you submit a form:
 *   form -> apiPost(...) -> FastAPI validates -> service saves
 *   -> database -> JSON response -> we reload the tables.
 *
 * RULE: this file only reads forms and displays data. Balances and totals
 * are calculated in Python (services/).
 */

const form = document.getElementById("account-form");
const formMessage = document.getElementById("form-message");
const accountsBody = document.getElementById("accounts-body");
const transactionForm = document.getElementById("transaction-form");
const transactionMessage = document.getElementById("transaction-message");
const transactionsBody = document.getElementById("transactions-body");
const correctionsBody = document.getElementById("corrections-body");
const transactionCancel = document.getElementById("transaction-cancel");
const transactionSubmit = transactionForm.querySelector('button[type="submit"]');
const categorySuggestions = document.getElementById("category-suggestions");
const DEFAULT_TRANSACTION_TYPE = "Expense";
let editingTransactionId = null;
let loadedTransactions = [];

// Fill a <select> with options that come from the backend.
// `keepFirst` keeps an existing first option such as "Same as account".
function fillSelect(select, values, keepFirst = false) {
  const first = keepFirst ? select.options[0] : null;
  select.replaceChildren();
  if (first) select.appendChild(first);
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

async function loadOptions() {
  const [accountOptions, transactionOptions] = await Promise.all([
    apiGet("/serenity-api/accounts/options"),
    apiGet("/serenity-api/transactions/options"),
  ]);
  fillSelect(form.elements.account_type, accountOptions.account_types);
  fillSelect(form.elements.classification, accountOptions.classifications);
  fillSelect(transactionForm.elements.transaction_type, transactionOptions.transaction_types);
  fillSelect(transactionForm.elements.classification, transactionOptions.classifications, true);
  categorySuggestions.replaceChildren();
  for (const category of transactionOptions.categories) {
    const option = document.createElement("option");
    option.value = category;
    categorySuggestions.appendChild(option);
  }
  if (editingTransactionId === null) resetTransactionForm();
}

async function loadAccounts() {
  const accounts = await apiGet("/serenity-api/accounts");
  accountsBody.replaceChildren();
  const accountSelect = transactionForm.elements.account_id;
  const selectedAccount = accountSelect.value;
  accountSelect.replaceChildren();
  for (const account of accounts) {
    const option = document.createElement("option");
    option.value = String(account.id);
    option.textContent = `${account.name} (${formatMoney(account.current_balance)})`;
    accountSelect.appendChild(option);
  }
  if (accounts.some((account) => String(account.id) === selectedAccount)) {
    accountSelect.value = selectedAccount;
  }
  transactionSubmit.disabled = accounts.length === 0;

  if (accounts.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("No accounts yet. Add one above.", "muted");
    cell.colSpan = 5;
    row.appendChild(cell);
    accountsBody.appendChild(row);
    renderTransactions([]);
    renderCorrections([]);
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
  await Promise.all([loadTransactions(), loadCorrections()]);
}

function correctionSummary(snapshot) {
  if (!snapshot) return "Removed from active history";
  return [
    snapshot.date,
    snapshot.transaction_type,
    formatMoney(snapshot.amount),
    snapshot.description,
    snapshot.merchant ? `@ ${snapshot.merchant}` : "",
    snapshot.category ? `(${snapshot.category})` : "",
  ].filter(Boolean).join(" · ");
}

function renderCorrections(corrections) {
  correctionsBody.replaceChildren();
  if (corrections.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("No corrections yet for this account.", "muted");
    cell.colSpan = 4;
    row.appendChild(cell);
    correctionsBody.appendChild(row);
    return;
  }
  for (const correction of corrections) {
    const row = document.createElement("tr");
    const timestamp = correction.changed_at;
    const utcTimestamp = /(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp)
      ? timestamp
      : `${timestamp}Z`;
    row.appendChild(makeCell(new Date(utcTimestamp).toLocaleString()));
    row.appendChild(makeCell(correction.action));
    row.appendChild(makeCell(correctionSummary(correction.before)));
    row.appendChild(makeCell(correctionSummary(correction.after)));
    correctionsBody.appendChild(row);
  }
}

async function loadCorrections() {
  const accountId = transactionForm.elements.account_id.value;
  if (!accountId) {
    renderCorrections([]);
    return;
  }
  const corrections = await apiGet(`/serenity-api/accounts/${accountId}/transaction-corrections`);
  if (accountId === transactionForm.elements.account_id.value) renderCorrections(corrections);
}

function renderTransactions(transactions) {
  loadedTransactions = transactions;
  transactionsBody.replaceChildren();
  if (transactions.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("No transactions yet for this account.", "muted");
    cell.colSpan = 8;
    row.appendChild(cell);
    transactionsBody.appendChild(row);
    return;
  }
  for (const transaction of transactions) {
    const row = document.createElement("tr");
    row.appendChild(makeCell(transaction.date));
    row.appendChild(makeCell(transaction.transaction_type));
    row.appendChild(makeCell(transaction.description));
    row.appendChild(makeCell(transaction.merchant || "—"));
    row.appendChild(makeCell(transaction.classification));
    const category = [transaction.category, transaction.subcategory].filter(Boolean).join(" › ");
    row.appendChild(makeCell(category || "—"));
    // Display only: the sign mirrors the type the server already stored.
    row.appendChild(makeCell(
      `${transaction.transaction_type === "Expense" ? "−" : "+"}${formatMoney(transaction.amount)}`,
      "num"
    ));
    const actions = document.createElement("td");
    const actionGroup = document.createElement("div");
    actionGroup.className = "row-actions";
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.textContent = "Edit";
    editButton.dataset.action = "edit";
    editButton.dataset.transactionId = String(transaction.id);
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.textContent = "Delete";
    deleteButton.className = "danger";
    deleteButton.dataset.action = "delete";
    deleteButton.dataset.transactionId = String(transaction.id);
    actionGroup.append(editButton, deleteButton);
    actions.appendChild(actionGroup);
    row.appendChild(actions);
    transactionsBody.appendChild(row);
  }
}

function todayDateValue() {
  const today = new Date();
  return [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getDate()).padStart(2, "0"),
  ].join("-");
}

// Text fields that are simply copied between the form and a transaction.
const TEXT_FIELDS = ["description", "merchant", "location", "category", "subcategory"];

function resetTransactionForm() {
  editingTransactionId = null;
  transactionForm.elements.date.value = todayDateValue();
  transactionForm.elements.transaction_type.value = DEFAULT_TRANSACTION_TYPE;
  transactionForm.elements.amount.value = "";
  transactionForm.elements.classification.value = "";
  for (const field of TEXT_FIELDS) transactionForm.elements[field].value = "";
  transactionSubmit.textContent = "Record transaction";
  transactionCancel.hidden = true;
}

function beginTransactionEdit(transaction) {
  editingTransactionId = transaction.id;
  transactionForm.elements.date.value = transaction.date;
  transactionForm.elements.transaction_type.value = transaction.transaction_type;
  transactionForm.elements.amount.value = transaction.amount;
  transactionForm.elements.classification.value = transaction.classification;
  for (const field of TEXT_FIELDS) {
    transactionForm.elements[field].value = transaction[field] || "";
  }
  transactionSubmit.textContent = "Save changes";
  transactionCancel.hidden = false;
  transactionForm.elements.date.focus();
}

async function loadTransactions() {
  const accountId = transactionForm.elements.account_id.value;
  if (!accountId) {
    renderTransactions([]);
    return;
  }
  const transactions = await apiGet(`/serenity-api/accounts/${accountId}/transactions`);
  if (accountId === transactionForm.elements.account_id.value) renderTransactions(transactions);
}

function showMessage(target, text, isError) {
  target.textContent = text;
  target.className = isError ? "message error" : "message success";
  target.hidden = false;
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
    const created = await apiPost("/serenity-api/accounts", body);
    showMessage(formMessage, `Added "${created.name}".`, false);
    form.reset();
    await loadAccounts();
  } catch (error) {
    showMessage(formMessage, error.message, true);
  }
});

resetTransactionForm();
transactionForm.elements.account_id.addEventListener("change", () => {
  resetTransactionForm();
  renderTransactions([]);
  renderCorrections([]);
  Promise.all([loadTransactions(), loadCorrections()])
    .catch((error) => showMessage(transactionMessage, error.message, true));
});
transactionCancel.addEventListener("click", resetTransactionForm);
transactionsBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const transactionId = Number(button.dataset.transactionId);
  const transaction = loadedTransactions.find((item) => item.id === transactionId);
  if (!transaction) return;
  if (button.dataset.action === "edit") {
    beginTransactionEdit(transaction);
    return;
  }
  if (!window.confirm(`Delete "${transaction.description}"? It will be kept in the correction history.`)) return;
  const accountId = transactionForm.elements.account_id.value;
  try {
    await apiDelete(`/serenity-api/accounts/${accountId}/transactions/${transactionId}`);
    if (editingTransactionId === transactionId) resetTransactionForm();
    showMessage(transactionMessage, "Transaction deleted.", false);
    await loadAccounts();
  } catch (error) {
    showMessage(transactionMessage, error.message, true);
  }
});
transactionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const accountId = transactionForm.elements.account_id.value;
  const body = {
    date: transactionForm.elements.date.value,
    transaction_type: transactionForm.elements.transaction_type.value,
    amount: transactionForm.elements.amount.value,
    // Empty means "use the account's classification" (decided by the server).
    classification: transactionForm.elements.classification.value || null,
  };
  for (const field of TEXT_FIELDS) body[field] = transactionForm.elements[field].value;
  try {
    if (editingTransactionId === null) {
      await apiPost(`/serenity-api/accounts/${accountId}/transactions`, body);
      showMessage(transactionMessage, "Transaction recorded.", false);
    } else {
      await apiPut(
        `/serenity-api/accounts/${accountId}/transactions/${editingTransactionId}`,
        body
      );
      showMessage(transactionMessage, "Transaction updated.", false);
    }
    resetTransactionForm();
    await loadAccounts();
  } catch (error) {
    showMessage(transactionMessage, error.message, true);
  }
});

// Run when the page loads.
loadOptions()
  .then(loadAccounts)
  .catch((error) => showMessage(formMessage, error.message, true));
