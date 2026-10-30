/* Sortable and filterable tables.
   table[data-sortable]            -> headers with data-sort="num|text" become sort buttons
   cell data-v="..."               -> raw sort value (otherwise the cell text)
   input[data-filter-for="#id"]    -> live text filter over the table body rows */
(function () {
  "use strict";
  const collator = new Intl.Collator("de", { numeric: true, sensitivity: "base" });
  const cellValue = (row, idx, kind) => {
    const cell = row.cells[idx];
    const raw = cell ? (cell.dataset.v !== undefined ? cell.dataset.v : cell.textContent.trim()) : "";
    if (kind === "num") { const n = parseFloat(raw); return Number.isNaN(n) ? null : n; }
    return raw;
  };

  function makeSortable(table) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    table.querySelectorAll("th[data-sort]").forEach((th) => {
      const idx = th.cellIndex, kind = th.dataset.sort;
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = "sort"; btn.textContent = th.textContent;
      th.textContent = ""; th.appendChild(btn);
      th.setAttribute("aria-sort", "none");
      btn.addEventListener("click", () => {
        const dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
        table.querySelectorAll("th[aria-sort]").forEach((o) => o.setAttribute("aria-sort", "none"));
        th.setAttribute("aria-sort", dir);
        const rows = Array.from(tbody.rows).filter((r) => r.cells.length > 1);
        const sign = dir === "ascending" ? 1 : -1;
        rows.sort((a, b) => {
          const x = cellValue(a, idx, kind), y = cellValue(b, idx, kind);
          if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1; // missing values last
          return sign * (kind === "num" ? x - y : collator.compare(x, y));
        });
        rows.forEach((r) => tbody.appendChild(r));
      });
    });
  }

  function makeFilter(input) {
    const table = document.querySelector(input.dataset.filterFor);
    if (!table || !table.tBodies[0]) return;
    const status = document.createElement("span");
    status.className = "muted small"; status.setAttribute("aria-live", "polite");
    input.insertAdjacentElement("beforebegin", status);
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0, total = 0;
      Array.from(table.tBodies[0].rows).forEach((row) => {
        if (row.cells.length < 2) return;
        total += 1;
        const match = !q || row.textContent.toLowerCase().includes(q);
        row.hidden = !match;
        if (match) shown += 1;
      });
      status.textContent = q ? `${shown} von ${total}` : "";
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("table[data-sortable]").forEach(makeSortable);
    document.querySelectorAll("input[data-filter-for]").forEach(makeFilter);
  });
})();
