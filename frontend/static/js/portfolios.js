/* Organization only: this page never interprets account balances or values investments. */
const PORTFOLIOS_URL = "/serenity-api/portfolios";
const CONTAINERS_URL = "/serenity-api/investment-accounts";
const portfolioForm = document.getElementById("portfolio-form");
const containerForm = document.getElementById("container-form");
const portfolioBody = document.getElementById("portfolios-body");
const containerBody = document.getElementById("containers-body");
const portfolioMessage = document.getElementById("portfolio-message");
const containerMessage = document.getElementById("container-message");
const containerHint = document.getElementById("container-hint");
const portfolioSubmit = document.getElementById("portfolio-submit");
const containerSubmit = document.getElementById("container-submit");
const portfolioCancel = document.getElementById("portfolio-cancel");
const containerCancel = document.getElementById("container-cancel");
let portfolios = [];
let containers = [];
let accounts = [];
let investments = [];
let portfolioEditId = null;
let containerEditId = null;
let busy = false;
let loadGeneration = 0;

// Shared session recovery removes all form fields from main. Discard the page's
// in-memory copies too, and invalidate outstanding reads before they can repaint.
const main = document.querySelector("main");
new MutationObserver(() => {
  if (!sessionRecoveryActive) return;
  loadGeneration += 1;
  portfolios = [];
  containers = [];
  accounts = [];
  investments = [];
  portfolioEditId = null;
  containerEditId = null;
}).observe(main, { childList: true });

function message(target, text, isError = false) {
  if (!sessionRecoveryActive) showMessage(target, text, isError);
}

function resetPortfolio() {
  portfolioEditId = null;
  portfolioForm.reset();
  portfolioSubmit.textContent = "Add portfolio";
  portfolioCancel.hidden = true;
}

function resetContainer() {
  containerEditId = null;
  containerForm.reset();
  containerForm.hidden = true;
  containerSubmit.textContent = "Add container";
  containerCancel.hidden = true;
  choosePortfolioOptions();
  chooseAccountOptions();
}

function addOption(select, id, label) {
  const option = document.createElement("option");
  option.value = String(id);
  option.textContent = label;
  select.appendChild(option);
}

function choosePortfolioOptions() {
  const select = containerForm.elements.portfolio_id;
  const selected = select.value;
  select.replaceChildren();
  addOption(select, "", "Choose an active portfolio");
  for (const record of portfolios) {
    if (record.active || (containerEditId !== null &&
        String(record.id) === String(containers.find((item) => item.id === containerEditId)?.portfolio_id))) {
      addOption(select, record.id, record.active ? record.name : `${record.name} (archived; select an active portfolio)`);
      if (!record.active) select.lastChild.disabled = true;
    }
  }
  select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  select.disabled = !portfolios.some((item) => item.active);
}

function chooseAccountOptions() {
  const select = containerForm.elements.account_id;
  const selected = select.value;
  select.replaceChildren();
  addOption(select, "", "Choose an unlinked active Account");
  const edited = containers.find((item) => item.id === containerEditId);
  for (const account of accounts) {
    if ((account.active && !containers.some((item) => item.account_id === account.id)) ||
        edited?.account_id === account.id) {
      addOption(select, account.id, account.active ? account.name : `${account.name} (inactive)`);
    }
  }
  if (edited && !accounts.some((item) => item.id === edited.account_id)) {
    addOption(select, edited.account_id, `Account #${edited.account_id} (unavailable)`);
  }
  select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  select.disabled = containerEditId !== null ||
    !accounts.some((item) => item.active && !containers.some((container) => container.account_id === item.id));
}

function labelledCell(name, active) {
  const cell = makeCell(name);
  if (!active) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "Archived";
    cell.append(" ", badge);
  }
  return cell;
}

function render() {
  if (sessionRecoveryActive) return;
  portfolioBody.replaceChildren();
  containerBody.replaceChildren();
  const holdingsBody = document.getElementById("portfolio-holdings-body");
  holdingsBody.replaceChildren();
  document.getElementById("legacy-links").hidden = !containers.length;
  if (!portfolios.length) {
    const row = document.createElement("tr");
    const cell = makeCell("No portfolios yet. Create a portfolio to organize investments.", "muted");
    cell.colSpan = 3;
    row.append(cell);
    portfolioBody.append(row);
  }
  for (const record of portfolios) {
    const row = document.createElement("tr");
    if (!record.active) row.className = "inactive";
    row.append(
      labelledCell(record.name, record.active), makeCell(record.notes || "—"),
      makeActionsCell(
        makeRowButton("Edit", "edit", record.id),
        makeRowButton(record.active ? "Archive" : "Reactivate",
          record.active ? "deactivate" : "reactivate", record.id, "secondary"),
      ),
    );
    portfolioBody.append(row);
  }
  let shown = 0;
  for (const portfolio of portfolios) {
    for (const investment of investments.filter((item) => item.portfolio_id === portfolio.id ||
      (item.portfolio_id == null && containers.some((c) =>
        c.id === item.investment_account_id && c.portfolio_id === portfolio.id)))) {
      const row = document.createElement("tr");
      const link = document.createElement("a");
      link.href = "/finances";
      link.textContent = investment.name;
      const name = document.createElement("td");
      name.append(link);
      row.append(makeCell(portfolio.name), name, makeCell(investment.quantity),
        makeCell(formatMoney(investment.current_value)),
        makeCell(investment.review_pending ? "Pending review — not counted" :
          investment.active ? "Existing investment" : "Inactive"));
      holdingsBody.append(row);
      shown += 1;
    }
  }
  if (!shown) {
    const row = document.createElement("tr");
    const cell = makeCell("No investments assigned yet. Add one on Finances.", "muted");
    cell.colSpan = 5;
    row.append(cell);
    holdingsBody.append(row);
  }
  if (!containers.length) {
    const row = document.createElement("tr");
    const cell = makeCell("No investment containers yet. Create a portfolio and an existing Account first.", "muted");
    cell.colSpan = 5;
    row.append(cell);
    containerBody.append(row);
  }
  for (const record of containers) {
    const row = document.createElement("tr");
    if (!record.active) row.className = "inactive";
    const portfolio = portfolios.find((item) => item.id === record.portfolio_id);
    const account = accounts.find((item) => item.id === record.account_id);
    row.append(
      labelledCell(record.name, record.active),
      labelledCell(portfolio?.name || `Portfolio #${record.portfolio_id} (unavailable)`, portfolio?.active),
      labelledCell(account?.name || `Account #${record.account_id} (unavailable)`, account?.active),
      makeCell(record.notes || "—"),
      makeActionsCell(
        makeRowButton("Edit", "edit", record.id),
        makeRowButton(record.active ? "Archive" : "Reactivate",
          record.active ? "deactivate" : "reactivate", record.id, "secondary"),
      ),
    );
    containerBody.append(row);
  }
  choosePortfolioOptions();
  chooseAccountOptions();
  const freeAccounts = accounts.filter((account) =>
    account.active && !containers.some((item) => item.account_id === account.id));
  containerHint.textContent = !portfolios.some((item) => item.active)
    ? "Create or reactivate a portfolio before adding a container."
    : !freeAccounts.length
      ? "An unlinked active Account is needed for a new container. Create one on the Accounts page; archived links still reserve Accounts."
      : "Select an unlinked active Account. A link alone does not confirm its cash balance.";
}

async function reload() {
  const generation = ++loadGeneration;
  const [newPortfolios, newContainers, newAccounts, newInvestments] = await Promise.all([
    apiGet(PORTFOLIOS_URL), apiGet(CONTAINERS_URL), apiGet("/serenity-api/accounts"),
    apiGet("/serenity-api/investments"),
  ]);
  if (sessionRecoveryActive || generation !== loadGeneration) return;
  portfolios = newPortfolios;
  containers = newContainers;
  accounts = newAccounts;
  investments = newInvestments;
  render();
}

function editPortfolio(record) {
  portfolioEditId = record.id;
  portfolioForm.elements.name.value = record.name;
  portfolioForm.elements.notes.value = record.notes || "";
  portfolioSubmit.textContent = "Save portfolio";
  portfolioCancel.hidden = false;
  portfolioMessage.hidden = true;
  portfolioForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function editContainer(record) {
  containerEditId = record.id;
  containerForm.hidden = false;
  choosePortfolioOptions();
  chooseAccountOptions();
  containerForm.elements.name.value = record.name;
  containerForm.elements.notes.value = record.notes || "";
  containerForm.elements.portfolio_id.value = String(record.portfolio_id);
  containerForm.elements.account_id.value = String(record.account_id);
  containerSubmit.textContent = "Save container";
  containerCancel.hidden = false;
  containerMessage.hidden = true;
  containerForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

portfolioCancel.addEventListener("click", () => {
  if (busy) return;
  resetPortfolio();
  portfolioMessage.hidden = true;
});
containerCancel.addEventListener("click", () => {
  if (busy) return;
  resetContainer();
  containerMessage.hidden = true;
});

portfolioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || sessionRecoveryActive) return;
  busy = true;
  portfolioSubmit.disabled = true;
  const id = portfolioEditId;
  const payload = {
    name: portfolioForm.elements.name.value.trim(),
    notes: portfolioForm.elements.notes.value.trim() || null,
  };
  try {
    await (id === null ? apiPost(PORTFOLIOS_URL, payload) :
      apiPut(`${PORTFOLIOS_URL}/${id}`, payload));
    if (sessionRecoveryActive) return;
    resetPortfolio();
    await reload();
    message(portfolioMessage, id === null ? "Portfolio added." : "Portfolio saved.");
  } catch (error) {
    message(portfolioMessage, error.message, true);
  } finally {
    busy = false;
    portfolioSubmit.disabled = false;
  }
});

containerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || sessionRecoveryActive) return;
  busy = true;
  containerSubmit.disabled = true;
  const id = containerEditId;
  const existing = containers.find((item) => item.id === id);
  const payload = {
    name: containerForm.elements.name.value.trim(),
    portfolio_id: Number(containerForm.elements.portfolio_id.value),
    account_id: id === null ? Number(containerForm.elements.account_id.value) : existing.account_id,
    notes: containerForm.elements.notes.value.trim() || null,
  };
  try {
    await (id === null ? apiPost(CONTAINERS_URL, payload) :
      apiPut(`${CONTAINERS_URL}/${id}`, payload));
    if (sessionRecoveryActive) return;
    resetContainer();
    await reload();
    message(containerMessage, id === null ? "Container added." : "Container saved. Regrouping did not move money.");
  } catch (error) {
    message(containerMessage, error.message, true);
  } finally {
    busy = false;
    containerSubmit.disabled = false;
  }
});

async function onRowAction(event, body, records, url, target) {
  const button = event.target.closest("button[data-action]");
  if (!button || !body.contains(button) || busy || sessionRecoveryActive) return;
  const record = records.find((item) => item.id === Number(button.dataset.id));
  if (!record) return;
  if (button.dataset.action === "edit") {
    if (body === portfolioBody) editPortfolio(record);
    else editContainer(record);
    return;
  }
  const action = button.dataset.action;
  if (!["deactivate", "reactivate"].includes(action)) return;
  if (action === "deactivate" && !window.confirm(
    `Archive "${record.name}"? This only changes its organization status; no balance or investment is removed.`
  )) return;
  busy = true;
  button.disabled = true;
  try {
    await apiPost(`${url}/${record.id}/${action}`);
    if (sessionRecoveryActive) return;
    // An edit in progress may contain unsaved changes: do not discard it.
    await reload();
    message(target, action === "deactivate" ? `${record.name} archived.` : `${record.name} reactivated.`);
  } catch (error) {
    message(target, error.message, true);
  } finally {
    busy = false;
    button.disabled = false;
  }
}

portfolioBody.addEventListener("click", (event) =>
  onRowAction(event, portfolioBody, portfolios, PORTFOLIOS_URL, portfolioMessage));
containerBody.addEventListener("click", (event) =>
  onRowAction(event, containerBody, containers, CONTAINERS_URL, containerMessage));

reload().catch((error) => {
  if (sessionRecoveryActive) return;
  portfolioBody.replaceChildren();
  containerBody.replaceChildren();
  message(portfolioMessage, `Could not load portfolios: ${error.message}`, true);
  message(containerMessage, `Could not load investment containers: ${error.message}`, true);
});