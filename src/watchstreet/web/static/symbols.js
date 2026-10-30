/* Symbol autocomplete backed by /api/search. */
(function () {
  const input = document.querySelector('input[name="symbol"]');
  const list = document.getElementById("symbols");
  if (!input || !list) return;
  const DEBOUNCE_MS = 250, MIN_CHARS = 2;
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < MIN_CHARS) return;
    timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const matches = await res.json();
        list.innerHTML = "";
        matches.forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m.symbol; opt.label = `${m.name} (${m.exchange})`;
          list.appendChild(opt);
        });
      } catch { /* autocomplete is optional */ }
    }, DEBOUNCE_MS);
  });
})();
