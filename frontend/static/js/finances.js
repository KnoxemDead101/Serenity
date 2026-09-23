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

const SECTIONS = [
  { path: "bills", noun: "Bill", form: "bill-form", body: "bills-body", message: "bill-message",
    columns: (r) => [makeCell(r.name), makeCell(formatDate(r.due_date)), makeCell(r.frequency), makeCell(r.category || "—"), makeCell(formatMoney(r.amount), "num")],
     read: (f) => ({name:f.elements.name.value, amount:f.elements.amount.value, due_date:f.elements.due_date.value, frequency:f.elements.frequency.value, category:f.elements.category.value, notes:f.elements.notes.value}),
     fill: (f,r) => { f.elements.name.value=r.name; f.elements.amount.value=r.amount; f.elements.due_date.value=r.due_date || ""; f.elements.frequency.value=r.frequency; f.elements.category.value=r.category || ""; f.elements.notes.value=r.notes || ""; }},
  { path: "debts", noun: "Debt", form: "debt-form", body: "debts-body", message: "debt-message",
    columns: (r) => [makeCell(r.name), makeCell(r.debt_type), makeCell(formatDate(r.due_date)), makeCell(`${r.interest_rate}%`, "num"), makeCell(formatMoney(r.minimum_payment), "num"), makeCell(formatMoney(r.balance), "num")],
     read: (f) => ({name:f.elements.name.value, debt_type:f.elements.debt_type.value, balance:f.elements.balance.value, interest_rate:f.elements.interest_rate.value, minimum_payment:f.elements.minimum_payment.value, due_date:f.elements.due_date.value || null, notes:f.elements.notes.value}),
     fill: (f,r) => { f.elements.name.value=r.name; f.elements.debt_type.value=r.debt_type; f.elements.balance.value=r.balance; f.elements.interest_rate.value=r.interest_rate; f.elements.minimum_payment.value=r.minimum_payment; f.elements.due_date.value=r.due_date || ""; f.elements.notes.value=r.notes || ""; }},
  { path: "investments", noun: "Investment", form: "investment-form", body: "investments-body", message: "investment-message",
    columns: (r) => [makeCell(r.name), makeCell(r.ticker || "—"), makeCell(r.quantity, "num"), makeCell(formatMoney(r.cost_basis), "num"), makeCell(formatMoney(r.current_value), "num")],
     read: (f) => ({name:f.elements.name.value, ticker:f.elements.ticker.value, quantity:f.elements.quantity.value || "0", cost_basis:f.elements.cost_basis.value, current_value:f.elements.current_value.value, notes:f.elements.notes.value}),
     fill: (f,r) => { f.elements.name.value=r.name; f.elements.ticker.value=r.ticker || ""; f.elements.quantity.value=r.quantity; f.elements.cost_basis.value=r.cost_basis; f.elements.current_value.value=r.current_value; f.elements.notes.value=r.notes || ""; }},
];

function setUpSection(section) {
  const form = document.getElementById(section.form), body = document.getElementById(section.body);
  const message = document.getElementById(section.message), submit = form.querySelector('button[type="submit"]');
  const cancel = form.querySelector("[data-cancel]"), addLabel = submit.textContent;
  let records = [], editingId = null;
  function reset() { editingId = null; form.reset(); submit.textContent = addLabel; cancel.hidden = true; }
  async function load() {
    records = await apiGet(`${financeApi}/${section.path}`); body.replaceChildren();
    if (!records.length) { const row=document.createElement("tr"), cell=makeCell("No records yet.", "muted"); cell.colSpan=form.closest("section").querySelectorAll("th").length; row.appendChild(cell); body.appendChild(row); return; }
    for (const record of records) {
      const row=document.createElement("tr"); if (!record.active) row.className="inactive";
      const cells=section.columns(record);
      if (!record.active) { const badge=document.createElement("span"); badge.className="badge"; badge.textContent="Inactive"; cells[0].append(" ",badge); }
      row.append(...cells, makeActionsCell(makeRowButton("Edit","edit",record.id), record.active ? makeRowButton("Deactivate","deactivate",record.id,"secondary") : makeRowButton("Reactivate","reactivate",record.id,"secondary")));
      body.appendChild(row);
    }
  }
  form.addEventListener("submit", async (event) => { event.preventDefault(); try { if (editingId === null) { await apiPost(`${financeApi}/${section.path}`, section.read(form)); showMessage(message, `${section.noun} added.`, false); } else { await apiPut(`${financeApi}/${section.path}/${editingId}`, section.read(form)); showMessage(message, `${section.noun} saved.`, false); } reset(); await load(); } catch (error) { showMessage(message,error.message,true); }});
  cancel.addEventListener("click", reset);
  body.addEventListener("click", async (event) => { const button=event.target.closest("button[data-action]"); if(!button)return; const record=records.find((r)=>r.id===Number(button.dataset.id)); if(!record)return; if(button.dataset.action==="edit"){editingId=record.id; section.fill(form,record); submit.textContent=`Save ${section.noun.toLowerCase()}`; cancel.hidden=false; form.elements.name.focus(); return;} if(button.dataset.action==="deactivate" && !window.confirm(`Deactivate "${record.name}"? It stays in your history but stops counting toward totals.`))return; try { await apiPost(`${financeApi}/${section.path}/${record.id}/${button.dataset.action}`); showMessage(message,`${section.noun} ${button.dataset.action==="deactivate"?"deactivated":"reactivated"}.`,false); await load(); } catch(error){showMessage(message,error.message,true);} });
  return {load};
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

const sections = SECTIONS.map(setUpSection);
loadFinanceOptions()
  .then(() => Promise.all(sections.map((section) => section.load())))
  .catch((error) => showMessage(document.getElementById("bill-message"), error.message, true));