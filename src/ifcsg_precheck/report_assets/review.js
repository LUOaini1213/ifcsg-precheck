/* Standalone reports use no CDN, upload endpoint, persistent state or IFC processing. */
(() => {
  "use strict";
  const normalize = value => String(value ?? "").toLocaleLowerCase();
  function matches(record, filters) {
    return (!filters.agency || record.agency.split("; ").includes(filters.agency)) &&
      (!filters.severity || record.severity === filters.severity) &&
      (!filters.status || record.status === filters.status) &&
      normalize(record.guid).includes(normalize(filters.guid)) &&
      normalize(record.property + " " + record.detail).includes(normalize(filters.property));
  }
  function csvCell(value) {
    let text = String(value ?? "");
    // Keep source identities in JSON; spreadsheet review exports neutralize formulas.
    if (/^[\s]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  }
  function toCSV(records) {
    const keys = ["kind", "agency", "severity", "status", "guid", "property", "detail"];
    return [keys, ...records.map(record => keys.map(key => record[key]))]
      .map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
  }
  function download(document, URL, Blob, name, type, content) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const anchor = document.createElement("a");
    try { anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); }
    finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {matches, csvCell, toCSV, download};
    return;
  }
  const data = JSON.parse(document.getElementById("review-data").textContent);
  const controls = Object.fromEntries(["agency", "severity", "status", "guid", "property"]
    .map(key => [key, document.getElementById("filter-" + key)]));
  const rows = [...document.querySelectorAll("#review tr[data-kind]")];
  let visible = data.review_records;
  function apply() {
    const filters = Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, input.value]));
    visible = data.review_records.filter(record => matches(record, filters));
    const totals = {}, shown = {};
    rows.forEach((row, index) => {
      const record = data.review_records[index];
      row.hidden = !matches(record, filters);
      totals[record.kind] = (totals[record.kind] || 0) + 1;
      if (!row.hidden) shown[record.kind] = (shown[record.kind] || 0) + 1;
    });
    document.querySelectorAll("[data-count]").forEach(label => {
      const kind = label.dataset.count;
      label.textContent = `(${shown[kind] || 0} of ${totals[kind] || 0} shown)`;
    });
    document.getElementById("review-visible").textContent = `${visible.length} of ${rows.length} review records shown. Complete model counts are unchanged.`;
  }
  Object.values(controls).forEach(input => input.addEventListener("input", apply));
  const form = document.getElementById("review-filters");
  form.addEventListener("submit", event => event.preventDefault());
  form.addEventListener("reset", () => setTimeout(apply, 0));
  document.getElementById("download-json").addEventListener("click", () =>
    download(document, URL, Blob, "ifc-review-evidence.json", "application/json", JSON.stringify(data, null, 2)));
  document.getElementById("download-csv").addEventListener("click", () =>
    download(document, URL, Blob, "ifc-review-filtered.csv", "text/csv;charset=utf-8", toCSV(visible)));
  apply();
})();
