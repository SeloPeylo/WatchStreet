/* Dependency-free candlestick chart rendered as SVG. */
(function () {
  const host = document.getElementById("chart");
  if (!host) return;
  const NS = "http://www.w3.org/2000/svg";
  const W = 900, H = 360, PAD = { l: 8, r: 64, t: 10, b: 24 };
  const VOLUME_SHARE = 0.18;
  const UP = "#3ecf8e", DOWN = "#f0616d", GRID = "#27344b", TXT = "#8b98b0";
  const Y_TICKS = 5, X_TICKS = 6, BODY_RATIO = 0.7, MIN_BODY = 1;

  const el = (name, attrs, parent) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (parent) parent.appendChild(node);
    return node;
  };
  const fmtPrice = (v) => v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtTime = (t, interval) => {
    const d = new Date(t * 1000);
    return interval === "1h"
      ? d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });
  };

  function draw(candles, interval) {
    host.innerHTML = "";
    if (!candles.length) { host.textContent = "Keine Kursdaten verfügbar."; return; }
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }, host);
    const lo = Math.min(...candles.map((c) => c.l)), hi = Math.max(...candles.map((c) => c.h));
    const maxVol = Math.max(...candles.map((c) => c.v)) || 1;
    const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
    const priceH = plotH * (1 - VOLUME_SHARE);
    const y = (p) => PAD.t + priceH - ((p - lo) / (hi - lo || 1)) * priceH;
    const step = plotW / candles.length, bodyW = Math.max(1, step * BODY_RATIO);
    const x = (i) => PAD.l + step * i + step / 2;

    for (let i = 0; i <= Y_TICKS; i++) {
      const p = lo + ((hi - lo) * i) / Y_TICKS;
      el("line", { x1: PAD.l, x2: W - PAD.r, y1: y(p), y2: y(p), stroke: GRID, "stroke-width": 1 }, svg);
      const label = el("text", { x: W - PAD.r + 6, y: y(p) + 4, fill: TXT, "font-size": 11 }, svg);
      label.textContent = fmtPrice(p);
    }
    for (let i = 0; i < X_TICKS; i++) {
      const idx = Math.round(((candles.length - 1) * i) / (X_TICKS - 1));
      const anchor = i === 0 ? "start" : i === X_TICKS - 1 ? "end" : "middle";
      const label = el("text", { x: x(idx), y: H - 6, fill: TXT, "font-size": 11, "text-anchor": anchor }, svg);
      label.textContent = fmtTime(candles[idx].t, interval);
    }
    candles.forEach((c, i) => {
      const color = c.c >= c.o ? UP : DOWN;
      el("line", { x1: x(i), x2: x(i), y1: y(c.h), y2: y(c.l), stroke: color, "stroke-width": 1 }, svg);
      const top = y(Math.max(c.o, c.c));
      el("rect", { x: x(i) - bodyW / 2, y: top, width: bodyW, height: Math.max(MIN_BODY, y(Math.min(c.o, c.c)) - top), fill: color }, svg);
      const vh = (c.v / maxVol) * plotH * VOLUME_SHARE;
      el("rect", { x: x(i) - bodyW / 2, y: PAD.t + plotH - vh, width: bodyW, height: vh, fill: color, opacity: 0.35 }, svg);
    });

    const tip = document.createElement("div");
    tip.className = "tip"; tip.hidden = true; host.appendChild(tip);
    svg.addEventListener("mousemove", (ev) => {
      const box = svg.getBoundingClientRect();
      const px = ((ev.clientX - box.left) / box.width) * W;
      const i = Math.min(candles.length - 1, Math.max(0, Math.floor((px - PAD.l) / step)));
      const c = candles[i];
      tip.hidden = false;
      tip.style.left = Math.min(ev.clientX - box.left + 12, box.width - 190) + "px";
      tip.style.top = "8px";
      tip.textContent = `${fmtTime(c.t, interval)}  O ${fmtPrice(c.o)}  H ${fmtPrice(c.h)}  L ${fmtPrice(c.l)}  C ${fmtPrice(c.c)}`;
    });
    svg.addEventListener("mouseleave", () => { tip.hidden = true; });
  }

  async function load(interval) {
    host.textContent = "Lade Kursdaten …";
    try {
      const res = await fetch(`${host.dataset.url}?interval=${interval}`);
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      draw(await res.json(), interval);
    } catch (err) { host.textContent = `Kursdaten nicht verfügbar: ${err.message}`; }
  }

  document.querySelectorAll("#intervals button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#intervals button").forEach((b) => b.classList.toggle("active", b === btn));
      load(btn.dataset.interval);
    });
  });
  load(host.dataset.interval);
})();
