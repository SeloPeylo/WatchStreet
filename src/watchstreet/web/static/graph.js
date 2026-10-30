/* Dependency graph: tiny force-directed layout, no libraries. Data is rendered via textContent only. */
(function () {
  const host = document.getElementById("graph");
  if (!host) return;
  const NS = "http://www.w3.org/2000/svg";
  const PAD_X = 90, PAD_Y = 50, MAX_FIT = 2.2;
  const W = 900, H = 560, ITER = 320, REPULSION = 5200, SPRING = 0.02, REST = 90, GRAVITY = 0.012, DAMPING = 0.82;
  const COLORS = { company: "#4f9cf9", supplier: "#f0b429", customer: "#3ecf8e", mine: "#e8a26b", facility: "#c08df0",
                   port: "#6bd0e8", country: "#8b98b0", commodity: "#f0616d" };
  const el = (n, a, p) => { const e = document.createElementNS(NS, n); Object.entries(a || {}).forEach(([k, v]) => e.setAttribute(k, v)); if (p) p.appendChild(e); return e; };

  const hiddenKinds = new Set(), nodeEls = [];
  let query = "";
  // Dim nodes that are filtered out by the legend (kind) or the search box.
  function refresh() {
    nodeEls.forEach(({ n, g }) => {
      const match = !query || n.name.toLowerCase().includes(query);
      g.style.opacity = hiddenKinds.has(n.kind) ? "0.08" : match ? "1" : "0.2";
      g.style.pointerEvents = hiddenKinds.has(n.kind) ? "none" : "";
    });
  }
  function legend() {
    const box = document.getElementById("legend");
    Object.entries(COLORS).forEach(([k, c]) => {
      const b = document.createElement("button"); b.type = "button"; b.setAttribute("aria-pressed", "true"); b.title = "Art ein-/ausblenden";
      const i = document.createElement("i"); i.style.background = c; b.append(i, k);
      b.addEventListener("click", () => {
        const off = !hiddenKinds.has(k); if (off) hiddenKinds.add(k); else hiddenKinds.delete(k);
        b.setAttribute("aria-pressed", String(!off)); refresh();
      });
      box.appendChild(b);
    });
    const search = document.getElementById("graph-search");
    if (search) search.addEventListener("input", () => { query = search.value.trim().toLowerCase(); refresh(); });
    const reset = document.getElementById("graph-reset");
    if (reset) reset.addEventListener("click", () => {
      hiddenKinds.clear(); query = ""; if (search) search.value = "";
      box.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", "true")); refresh();
    });
  }

  function show(title, rows) {
    const d = document.getElementById("detail"); d.replaceChildren();
    const h = document.createElement("h2"); h.textContent = title; d.appendChild(h);
    rows.forEach(([label, value, href]) => {
      const p = document.createElement("p"); const b = document.createElement("strong"); b.textContent = label + ": "; p.appendChild(b);
      if (href) { const a = document.createElement("a"); a.href = href; a.textContent = value; p.appendChild(a); } else p.appendChild(document.createTextNode(value));
      d.appendChild(p);
    });
  }

  function layout(nodes, edges) {
    nodes.forEach((n, i) => { const a = (2 * Math.PI * i) / nodes.length; n.x = W / 2 + 200 * Math.cos(a); n.y = H / 2 + 200 * Math.sin(a); n.vx = n.vy = 0; });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    for (let it = 0; it < ITER; it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j]; let dx = a.x - b.x, dy = a.y - b.y; const d2 = Math.max(dx * dx + dy * dy, 25), f = REPULSION / d2, d = Math.sqrt(d2);
        dx /= d; dy /= d; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
      }
      edges.forEach((e) => { const a = byId.get(e.source), b = byId.get(e.target); const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, f = SPRING * (d - REST);
        a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; });
      nodes.forEach((n) => { n.vx += (W / 2 - n.x) * GRAVITY; n.vy += (H / 2 - n.y) * GRAVITY; n.vx *= DAMPING; n.vy *= DAMPING;
        n.x = Math.min(W - 30, Math.max(30, n.x + n.vx)); n.y = Math.min(H - 20, Math.max(20, n.y + n.vy)); });
    }
    // Fit the layout to the canvas so small graphs are not tiny.
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const sx = (W - 2 * PAD_X) / Math.max(maxX - minX, 1), sy = (H - 2 * PAD_Y) / Math.max(maxY - minY, 1), k = Math.min(sx, sy, MAX_FIT);
    nodes.forEach((n) => { n.x = W / 2 + (n.x - (minX + maxX) / 2) * k; n.y = H / 2 + (n.y - (minY + maxY) / 2) * k; });
    return byId;
  }

  async function init() {
    legend();
    let data;
    try { const res = await fetch(host.dataset.url); if (!res.ok) throw new Error(res.statusText); data = await res.json(); }
    catch (err) { host.textContent = "Netzwerk konnte nicht geladen werden: " + err.message; return; }
    if (!data.nodes.length) { host.textContent = "Noch keine Beziehungen. Sie entstehen aus Einreichungen (Agent), Minen-Datenpunkten oder durch deine Einträge."; return; }
    const byId = layout(data.nodes, data.edges);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Abhängigkeitsnetzwerk mit ${data.nodes.length} Knoten` }, host);
    data.edges.forEach((e) => {
      const a = byId.get(e.source), b = byId.get(e.target); const verified = e.document_id || e.origin === "user";
      const line = el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: verified ? "#8b98b0" : "#4a566e", "stroke-width": 1 + 4 * (e.strength || 0.1), "stroke-dasharray": verified ? "" : "5 4", style: "cursor:pointer" }, svg);
      line.addEventListener("click", () => show(`${a.name} → ${b.name}`, [["Beziehung", e.kind], ["Anteil", e.strength == null ? "unbekannt" : Math.round(e.strength * 100) + " %"],
        ["Konfidenz", e.confidence], ["Herkunft", e.origin], ["Notiz", e.note || "–"], ["Beleg", e.quote ? "„" + e.quote + "“" : "kein Zitat"]].concat(e.document_id ? [["Dokument", "#" + e.document_id, "/documents/" + e.document_id]] : [])));
    });
    data.nodes.forEach((n) => {
      const g = el("g", { style: "cursor:pointer", tabindex: "0", role: "button", "aria-label": n.name + " (" + n.kind + ")" }, svg);
      nodeEls.push({ n, g });
      el("circle", { cx: n.x, cy: n.y, r: n.kind === "company" ? 13 : 9, fill: COLORS[n.kind] || "#888", stroke: "#0b1220", "stroke-width": 2 }, g);
      const t = el("text", { x: n.x, y: n.y - 15, "text-anchor": "middle", fill: "currentColor", "font-size": 11 }, g); t.textContent = n.name;
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); g.dispatchEvent(new Event("click")); } });
      g.addEventListener("click", () => show(n.name, [["Art", n.kind], ["Land", n.country || "–"], ["Ort", n.lat == null ? "nicht gesetzt" : `${n.lat.toFixed(2)}, ${n.lon.toFixed(2)}`]].concat(n.stock_id ? [["Aktie", "öffnen", "/stocks/" + n.stock_id]] : [])));
    });
  }
  init();
})();
