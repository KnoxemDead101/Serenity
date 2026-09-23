/*
 * Dashboard page: asks the backend for calculated totals and shows them.
 */

function makeCard(label, value) {
  const card = document.createElement("div");
  card.className = "card";

  const labelEl = document.createElement("div");
  labelEl.className = "card-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("div");
  valueEl.className = "card-value";
  valueEl.textContent = value;

  card.append(labelEl, valueEl);
  return card;
}

async function loadDashboard() {
  const summary = await apiGet("/serenity-api/dashboard/summary");

  document.getElementById("total-balance").textContent = formatMoney(summary.total_balance);
  document.getElementById("account-count").textContent = summary.account_count;
  document.getElementById("monthly-bills").textContent = formatMoney(summary.monthly_bill_total);
  document.getElementById("debt-balance").textContent = formatMoney(summary.debt_balance);
  document.getElementById("investment-value").textContent = formatMoney(summary.investment_value);
  document.getElementById("net-worth").textContent = formatMoney(summary.net_worth);

  const container = document.getElementById("classification-cards");
  container.replaceChildren();
  for (const [classification, balance] of Object.entries(summary.balance_by_classification)) {
    container.appendChild(makeCard(classification, formatMoney(balance)));
  }
}

loadDashboard().catch((error) => {
  const errorEl = document.getElementById("error");
  errorEl.textContent = error.message;
  errorEl.hidden = false;
});
