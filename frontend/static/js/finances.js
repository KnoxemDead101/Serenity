const financeApi = "/serenity-api";

function setMessage(element, text, isError = false) {
  element.textContent = text;
  element.className = isError ? "message error" : "message success";
  element.hidden = false;
}

function formatDate(dateString) {
  if (!dateString) return "—";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(
    new Date(`${dateString}T00:00:00`),
  );
}

function appendEmptyRow(body, columns, text = "No records yet.") {
  const row = document.createElement("tr");
  const cell = makeCell(text, "muted");
  cell.colSpan = columns;
  row.appendChild(cell);
  body.replaceChildren(row);
}

async function loadBills() {
  const bills = await apiGet(`${financeApi}/bills`);
  const body = document.getElementById("bills-body");
  body.replaceChildren();
  if (bills.length === 0) {
    appendEmptyRow(body, 5);
    return;
  }
  for (const bill of bills) {
    const row = document.createElement("tr");
    row.appendChild(makeCell(bill.name));
    row.appendChild(makeCell(formatDate(bill.due_date)));
    row.appendChild(makeCell(bill.frequency));
    row.appendChild(makeCell(bill.category || "—"));
    row.appendChild(makeCell(formatMoney(bill.amount), "num"));
    body.appendChild(row);
  }
}

async function loadDebts() {
  const debts = await apiGet(`${financeApi}/debts`);
  const body = document.getElementById("debts-body");
  body.replaceChildren();
  if (debts.length === 0) {
    appendEmptyRow(body, 6);
    return;
  }
  for (const debt of debts) {
    const row = document.createElement("tr");
    row.appendChild(makeCell(debt.name));
    row.appendChild(makeCell(debt.debt_type));
    row.appendChild(makeCell(formatDate(debt.due_date)));
    row.appendChild(makeCell(`${debt.interest_rate}%`, "num"));
    row.appendChild(makeCell(formatMoney(debt.minimum_payment), "num"));
    row.appendChild(makeCell(formatMoney(debt.balance), "num"));
    body.appendChild(row);
  }
}

async function loadInvestments() {
  const investments = await apiGet(`${financeApi}/investments`);
  const body = document.getElementById("investments-body");
  body.replaceChildren();
  if (investments.length === 0) {
    appendEmptyRow(body, 5);
    return;
  }
  for (const investment of investments) {
    const row = document.createElement("tr");
    row.appendChild(makeCell(investment.name));
    row.appendChild(makeCell(investment.ticker || "—"));
    row.appendChild(makeCell(investment.quantity, "num"));
    row.appendChild(makeCell(formatMoney(investment.cost_basis), "num"));
    row.appendChild(makeCell(formatMoney(investment.current_value), "num"));
    body.appendChild(row);
  }
}

async function loadFinanceOptions() {
  const options = await apiGet(`${financeApi}/finance/options`);
  const select = document.querySelector("#bill-form select[name=frequency]");
  for (const frequency of options.bill_frequencies) {
    const option = document.createElement("option");
    option.value = frequency;
    option.textContent = frequency;
    select.appendChild(option);
  }
  const debtTypeSelect = document.querySelector("#debt-form select[name=debt_type]");
  for (const debtType of options.debt_types) {
    const option = document.createElement("option");
    option.value = debtType;
    option.textContent = debtType;
    debtTypeSelect.appendChild(option);
  }
}

document.getElementById("bill-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("bill-message");
  try {
    await apiPost(`${financeApi}/bills`, {
      name: form.elements.name.value,
      amount: form.elements.amount.value,
      due_date: form.elements.due_date.value,
      frequency: form.elements.frequency.value,
      category: form.elements.category.value,
    });
    form.reset();
    setMessage(message, "Bill added.");
    await loadBills();
  } catch (error) {
    setMessage(message, error.message, true);
  }
});

document.getElementById("debt-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("debt-message");
  try {
    await apiPost(`${financeApi}/debts`, {
      name: form.elements.name.value,
      debt_type: form.elements.debt_type.value,
      balance: form.elements.balance.value,
      interest_rate: form.elements.interest_rate.value,
      minimum_payment: form.elements.minimum_payment.value,
      due_date: form.elements.due_date.value || null,
    });
    form.reset();
    setMessage(message, "Debt added.");
    await loadDebts();
  } catch (error) {
    setMessage(message, error.message, true);
  }
});

document.getElementById("investment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("investment-message");
  try {
    await apiPost(`${financeApi}/investments`, {
      name: form.elements.name.value,
      ticker: form.elements.ticker.value,
      quantity: form.elements.quantity.value || "0",
      cost_basis: form.elements.cost_basis.value,
      current_value: form.elements.current_value.value,
    });
    form.reset();
    setMessage(message, "Investment added.");
    await loadInvestments();
  } catch (error) {
    setMessage(message, error.message, true);
  }
});

Promise.all([loadFinanceOptions(), loadBills(), loadDebts(), loadInvestments()]).catch(
  (error) => {
    setMessage(document.getElementById("bill-message"), error.message, true);
  },
);