/* Live ticket status: polls /api/tickets/status for open tickets shown on the page, updates the
   badges in place and reloads the page (once) when a ticket finishes inside a [data-live-reload]
   region, so briefings, scores and counters appear without manual refreshing. */
(function () {
  "use strict";
  const POLL_MS = 3000, POLL_HIDDEN_MS = 15000, RELOAD_DELAY_MS = 800, MAX_ERRORS = 5;
  const OPEN = new Set(["queued", "running"]);
  const LABELS = { queued: "wartend", running: "läuft", done: "erledigt", failed: "fehlgeschlagen", cancelled: "abgebrochen" };
  const badges = () => Array.from(document.querySelectorAll(".badge[data-ticket-id]"));
  const reloadRegion = document.querySelector("[data-live-reload]");
  let errors = 0;

  function apply(badge, status) {
    badge.dataset.status = status;
    badge.className = "badge st-" + status;
    badge.textContent = LABELS[status] || status;
  }

  async function tick() {
    const open = badges().filter((b) => OPEN.has(b.dataset.status));
    if (!open.length) return;
    const ids = Array.from(new Set(open.map((b) => b.dataset.ticketId)));
    try {
      const res = await fetch("/api/tickets/status?ids=" + ids.join(","));
      if (!res.ok) throw new Error(String(res.status));
      const rows = await res.json();
      errors = 0;
      let finished = false;
      rows.forEach((row) => {
        badges().filter((b) => b.dataset.ticketId === String(row.id) && b.dataset.status !== row.status).forEach((b) => {
          apply(b, row.status);
          if (!OPEN.has(row.status)) {
            finished = true;
            if (window.WS) window.WS.toast(`Ticket #${row.id}: ${LABELS[row.status] || row.status}`, row.status === "failed" ? "warn" : "");
          }
        });
      });
      if (finished && reloadRegion) { setTimeout(() => location.reload(), RELOAD_DELAY_MS); return; }
    } catch {
      errors += 1;
      if (errors >= MAX_ERRORS) return; // give up quietly; the page still works without live updates
    }
    schedule();
  }

  function schedule() { setTimeout(tick, document.hidden ? POLL_HIDDEN_MS : POLL_MS); }

  document.addEventListener("DOMContentLoaded", () => {
    if (badges().some((b) => OPEN.has(b.dataset.status))) schedule();
  });
})();
