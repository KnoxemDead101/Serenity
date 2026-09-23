/*
 * Setup page: businesses and dependents. Both sections support add, edit,
 * deactivate and reactivate; validation remains on the server.
 */
const SETUP_SECTIONS = [
  { path: "businesses", noun: "Business", nameField: "name", form: "business-form", body: "businesses-body", message: "business-message" },
  { path: "dependents", noun: "Dependent", nameField: "display_name", form: "dependent-form", body: "dependents-body", message: "dependent-message" },
];

function setUpSetupSection(section) {
  const form = document.getElementById(section.form);
  const body = document.getElementById(section.body);
  const message = document.getElementById(section.message);
  const submit = form.querySelector('button[type="submit"]');
  const cancel = form.querySelector("[data-cancel]");
  const addLabel = submit.textContent;
  let records = [], editingId = null;
  const nameOf = (record) => record[section.nameField];
  function resetForm() { editingId = null; form.reset(); submit.textContent = addLabel; cancel.hidden = true; }
  function beginEdit(record) {
    editingId = record.id; form.elements[section.nameField].value = nameOf(record);
    form.elements.notes.value = record.notes || ""; submit.textContent = `Save ${section.noun.toLowerCase()}`;
    cancel.hidden = false; form.elements[section.nameField].focus();
  }
  async function load() {
    records = await apiGet(`/serenity-api/${section.path}`); body.replaceChildren();
    if (!records.length) { const row = document.createElement("tr"); const cell = makeCell("None yet.", "muted"); cell.colSpan = 3; row.appendChild(cell); body.appendChild(row); return; }
    for (const record of records) {
      const row = document.createElement("tr"); if (!record.active) row.className = "inactive";
      const nameCell = makeCell(nameOf(record));
      if (!record.active) { const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = "Inactive"; nameCell.append(" ", badge); }
      row.append(nameCell, makeCell(record.notes || "—"), makeActionsCell(
        makeRowButton("Edit", "edit", record.id),
        record.active ? makeRowButton("Deactivate", "deactivate", record.id, "secondary") : makeRowButton("Reactivate", "reactivate", record.id, "secondary")));
      body.appendChild(row);
    }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); const requestBody = { [section.nameField]: form.elements[section.nameField].value, notes: form.elements.notes.value };
    try {
      if (editingId === null) { await apiPost(`/serenity-api/${section.path}`, requestBody); showMessage(message, `${section.noun} added.`, false); }
      else { await apiPut(`/serenity-api/${section.path}/${editingId}`, requestBody); showMessage(message, `${section.noun} saved.`, false); }
      resetForm(); await load();
    } catch (error) { showMessage(message, error.message, true); }
  });
  cancel.addEventListener("click", resetForm);
  body.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]"); if (!button) return;
    const record = records.find((item) => item.id === Number(button.dataset.id)); if (!record) return;
    if (button.dataset.action === "edit") { beginEdit(record); return; }
    try { await apiPost(`/serenity-api/${section.path}/${record.id}/${button.dataset.action}`);
      showMessage(message, `${nameOf(record)} ${button.dataset.action === "deactivate" ? "deactivated" : "reactivated"}.`, false); await load();
    } catch (error) { showMessage(message, error.message, true); }
  });
  return { load };
}
Promise.all(SETUP_SECTIONS.map(setUpSetupSection).map((section) => section.load()))
  .catch((error) => showMessage(document.getElementById("business-message"), error.message, true));