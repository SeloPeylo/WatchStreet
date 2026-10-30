/* World map: equirectangular projection of the vendored Natural Earth topojson. No libraries. */
(function () {
  const host = document.getElementById("map");
  if (!host) return;
  const NS = "http://www.w3.org/2000/svg";
  const W = 1000, H = 500, MIN_ZOOM = 1, MAX_ZOOM = 12, ZOOM_STEP = 1.15;
  const KIND_COLORS = { mine: "#e8a26b", facility: "#c08df0", port: "#6bd0e8" };
  const CAT_COLORS = { hazard: "#f0616d", geopolitics: "#f0b429", commodity: "#3ecf8e", macro: "#4f9cf9", regulatory: "#c08df0", supply: "#e8a26b", company: "#8b98b0" };
  const el = (n, a, p) => { const e = document.createElementNS(NS, n); Object.entries(a || {}).forEach(([k, v]) => e.setAttribute(k, v)); if (p) p.appendChild(e); return e; };
  const proj = (lon, lat) => [((lon + 180) / 360) * W, ((90 - lat) / 180) * H];

  function decode(topo) {
    const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate;
    const arcs = topo.arcs.map((arc) => { let x = 0, y = 0; return arc.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty]; }); });
    // Rings that cross the antimeridian are unwrapped (lon may exceed +-180) and drawn again shifted by 360.
    const unwrap = (pts) => { const out = [pts[0].slice()]; for (let i = 1; i < pts.length; i++) { let lo = pts[i][0]; const prev = out[i - 1][0];
      while (lo - prev > 180) lo -= 360; while (prev - lo > 180) lo += 360; out.push([lo, pts[i][1]]); } return out; };
    const ring = (ids) => { const pts = []; ids.forEach((i) => { const a = i >= 0 ? arcs[i] : arcs[~i].slice().reverse(); pts.push(...(pts.length ? a.slice(1) : a)); }); return unwrap(pts); };
    const path = (pts, shift) => "M" + pts.map(([lo, la]) => proj(lo + shift, la).map((v) => v.toFixed(1)).join(",")).join("L") + "Z";
    const draw = (pts) => { const lons = pts.map((p) => p[0]); const shifts = [0]; if (Math.max(...lons) > 180) shifts.push(-360); if (Math.min(...lons) < -180) shifts.push(360); return shifts.map((sh) => path(pts, sh)).join(""); };
    return topo.objects.countries.geometries.map((g) => {
      const polys = g.type === "MultiPolygon" ? g.arcs : [g.arcs];
      const d = polys.map((poly) => poly.map((r) => draw(ring(r))).join("")).join("");
      return { name: g.properties.name, d };
    });
  }

  function show(title, rows) {
    const d = document.getElementById("detail"); d.replaceChildren();
    const h = document.createElement("h2"); h.textContent = title; d.appendChild(h);
    rows.forEach(([label, value, href]) => {
      const p = document.createElement("p"); const b = document.createElement("strong"); b.textContent = label + ": "; p.appendChild(b);
      if (href) { const a = document.createElement("a"); a.href = href; a.rel = "noopener noreferrer"; a.target = "_blank"; a.textContent = value; p.appendChild(a); } else p.appendChild(document.createTextNode(value));
      d.appendChild(p);
    });
  }

  async function init() {
    let topo, data;
    try {
      [topo, data] = await Promise.all([fetch(host.dataset.geo).then((r) => r.json()), fetch(host.dataset.url).then((r) => { if (!r.ok) throw new Error(r.statusText); return r.json(); })]);
    } catch (err) { host.textContent = "Karte konnte nicht geladen werden: " + err.message; return; }
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid meet" }, host);
    const layers = { exposure: el("g", {}, svg), assets: el("g", {}, svg), intel: el("g", {}, svg) };
    const max = Math.max(0.0001, ...Object.values(data.exposure).map((e) => e.share));
    decode(topo).forEach((c) => {
      const ex = data.exposure[c.name];
      const p = el("path", { d: c.d, fill: ex ? "#4f9cf9" : "#1c2638", "fill-opacity": ex ? 0.25 + 0.7 * (ex.share / max) : 1, stroke: "#27344b", "stroke-width": 0.4 }, layers.exposure);
      p.addEventListener("click", () => show(c.name, ex ? [["Portfolio-Exposure", (ex.share * 100).toFixed(1) + " %"]].concat(ex.reasons.map((r) => [r.stock, `${r.via} (${(r.share * 100).toFixed(1)} %)`])) : [["Exposure", "keine bekannte"]]));
    });
    data.assets.forEach((a) => { const [x, y] = proj(a.lon, a.lat);
      const c = el("circle", { cx: x, cy: y, r: 4.5, fill: KIND_COLORS[a.kind] || "#e8a26b", stroke: "#0b1220", "stroke-width": 1.2, style: "cursor:pointer" }, layers.assets);
      c.addEventListener("click", (e) => { e.stopPropagation(); show(a.name, [["Art", a.kind], ["Aktie", a.stock || "–"], ["Land", a.country || "–"], ["Koordinaten", `${a.lat.toFixed(2)}, ${a.lon.toFixed(2)}`]]); }); });
    data.intel.forEach((i) => { const [x, y] = proj(i.lon, i.lat);
      el("circle", { cx: x, cy: y, r: 9 + i.severity, fill: CAT_COLORS[i.category] || "#888", "fill-opacity": 0.18, stroke: CAT_COLORS[i.category] || "#888", "stroke-width": 0.8 }, layers.intel);
      const c = el("circle", { cx: x, cy: y, r: 2 + i.severity * 0.7, fill: CAT_COLORS[i.category] || "#888", style: "cursor:pointer" }, layers.intel);
      c.addEventListener("click", (e) => { e.stopPropagation(); show(i.headline, [["Thema", i.category], ["Schwere", String(i.severity)], ["Betrifft", i.stocks.join(", ") || "–"], ["Warum relevant", i.why || "–"], ["Quelle", "öffnen ↗", i.url]]); }); });

    document.querySelectorAll("#layers input[data-layer]").forEach((cb) => cb.addEventListener("change", () => { layers[cb.dataset.layer].style.display = cb.checked ? "" : "none"; }));
    let vb = { x: 0, y: 0, w: W, h: H };
    const apply = () => svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    document.getElementById("reset").addEventListener("click", () => { vb = { x: 0, y: 0, w: W, h: H }; apply(); });
    svg.addEventListener("wheel", (e) => { e.preventDefault(); const f = e.deltaY < 0 ? 1 / ZOOM_STEP : ZOOM_STEP, nw = Math.min(W / MIN_ZOOM, Math.max(W / MAX_ZOOM, vb.w * f)), k = nw / vb.w, r = svg.getBoundingClientRect();
      const mx = vb.x + ((e.clientX - r.left) / r.width) * vb.w, my = vb.y + ((e.clientY - r.top) / r.height) * vb.h; vb = { x: mx - (mx - vb.x) * k, y: my - (my - vb.y) * k, w: nw, h: vb.h * k }; apply(); }, { passive: false });
    let drag = null;
    svg.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, vb: { ...vb } }; });
    window.addEventListener("mouseup", () => { drag = null; });
    window.addEventListener("mousemove", (e) => { if (!drag) return; const r = svg.getBoundingClientRect(); vb.x = drag.vb.x - ((e.clientX - drag.x) / r.width) * vb.w; vb.y = drag.vb.y - ((e.clientY - drag.y) / r.height) * vb.h; apply(); });
  }
  init();
})();
