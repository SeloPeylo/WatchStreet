/* Shared UI behaviour: theme, menus, quick-jump palette, shortcuts, toasts, panel memory.
   Everything here is progressive enhancement; pages work without it. User data is only ever
   written with textContent. */
(function () {
  "use strict";
  const STORE_THEME = "ws.theme", STORE_PANELS = "ws.panels";
  const TOAST_MS = 5000, SEQUENCE_MS = 1200, PALETTE_MAX = 12;
  const FLASH_PARAM = "flash";
  const PAGES = [
    ["Übersicht", "/"], ["Holdings", "/holdings"], ["Watchlist", "/watchlist"], ["Intel", "/intel"],
    ["Quellen verwalten", "/intel/feeds"], ["Karte", "/map"], ["Netzwerk", "/graph"], ["Rohstoffe", "/commodities"],
    ["Tickets", "/tickets"], ["System", "/system"], ["Handbuch", "/manual"],
  ];
  const GOTO = { u: "/", h: "/holdings", w: "/watchlist", i: "/intel", t: "/tickets", k: "/map", n: "/graph", r: "/commodities" };

  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* storage may be blocked */ } },
  };
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const isTyping = (el) => el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

  /* ---- toasts ---- */
  function toast(text, kind) {
    const box = $("#toasts");
    if (!box) return;
    const node = document.createElement("div");
    node.className = "toast" + (kind ? " " + kind : "");
    node.textContent = text;
    const close = document.createElement("button");
    close.type = "button"; close.className = "link"; close.setAttribute("aria-label", "Meldung schließen"); close.textContent = "×";
    close.addEventListener("click", () => node.remove());
    node.appendChild(close);
    box.appendChild(node);
    setTimeout(() => node.remove(), TOAST_MS);
  }
  window.WS = { toast, store };

  /* Server-side flash messages become toasts and disappear from the address bar (reload-safe). */
  function handleFlash() {
    const inline = $("[data-flash]");
    if (inline) {
      toast(inline.textContent.trim());
      inline.remove();
    }
    const url = new URL(location.href);
    if (url.searchParams.has(FLASH_PARAM)) {
      url.searchParams.delete(FLASH_PARAM);
      try { history.replaceState(null, "", url.pathname + url.search + url.hash); } catch { /* ignore */ }
    }
    const err = $("#form-error");
    if (err) err.focus();
  }

  /* ---- theme ---- */
  function initTheme() {
    const btn = $("#theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const root = document.documentElement;
      const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
      const next = current === "light" ? "dark" : "light";
      root.dataset.theme = next;
      store.set(STORE_THEME, next);
      document.dispatchEvent(new CustomEvent("ws:theme"));
    });
  }

  /* ---- navigation: mobile toggle, dropdown groups ---- */
  function initNav() {
    const toggle = $("#nav-toggle"), nav = $("#site-nav");
    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const open = nav.classList.toggle("open");
        toggle.setAttribute("aria-expanded", String(open));
      });
    }
    const menus = $$("nav details.menu");
    menus.forEach((m) => m.addEventListener("toggle", () => {
      if (m.open) menus.forEach((o) => { if (o !== m) o.open = false; });
    }));
    document.addEventListener("click", (e) => { menus.forEach((m) => { if (!m.contains(e.target)) m.open = false; }); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") menus.forEach((m) => { if (m.open) { m.open = false; m.querySelector("summary").focus(); } });
    });
  }

  /* ---- quick-jump palette ---- */
  function initPalette() {
    const dlg = $("#palette"), input = $("#palette-input"), list = $("#palette-list");
    if (!dlg || !input || !list || typeof dlg.showModal !== "function") return;
    let entries = PAGES.map(([label, url]) => ({ label, url, hint: "Seite" })), loaded = false, shown = [], active = 0;

    async function loadStocks() {
      if (loaded) return;
      loaded = true;
      try {
        const res = await fetch("/api/stocks");
        const stocks = await res.json();
        const items = stocks.map((s) => ({ label: s.symbol + " – " + s.name, url: "/stocks/" + s.id, hint: "Aktie" }));
        entries = items.concat(entries);
        render();
      } catch { loaded = false; }
    }
    function render() {
      const q = input.value.trim().toLowerCase();
      shown = entries.filter((e) => !q || e.label.toLowerCase().includes(q)).slice(0, PALETTE_MAX);
      active = Math.min(active, Math.max(0, shown.length - 1));
      list.replaceChildren();
      shown.forEach((e, i) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option"); li.setAttribute("aria-selected", String(i === active));
        if (i === active) li.className = "on";
        const a = document.createElement("a");
        a.href = e.url; a.textContent = e.label;
        const hint = document.createElement("span");
        hint.className = "muted small"; hint.textContent = e.hint;
        li.append(a, hint);
        list.appendChild(li);
      });
      if (!shown.length) {
        const li = document.createElement("li");
        li.className = "muted"; li.textContent = "Keine Treffer.";
        list.appendChild(li);
      }
    }
    function open() { dlg.showModal(); input.value = ""; active = 0; render(); input.focus(); loadStocks(); }
    input.addEventListener("input", () => { active = 0; render(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(shown.length - 1, active + 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); render(); }
      else if (e.key === "Enter" && shown[active]) { e.preventDefault(); location.href = shown[active].url; }
    });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    $("#open-palette").addEventListener("click", open);
    window.WS.openPalette = open;
  }

  /* ---- keyboard shortcuts ---- */
  function initShortcuts() {
    const help = $("#help");
    let pending = null, timer = null;
    $("#open-help").addEventListener("click", () => help.showModal && help.showModal());
    document.addEventListener("keydown", (e) => {
      if (e.defaultPrevented || e.altKey) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); window.WS.openPalette && window.WS.openPalette(); return; }
      if (e.ctrlKey || e.metaKey || isTyping(e.target) || document.querySelector("dialog[open]")) return;
      if (e.key === "/") { e.preventDefault(); window.WS.openPalette && window.WS.openPalette(); }
      else if (e.key === "?") { e.preventDefault(); help.showModal && help.showModal(); }
      else if (pending && GOTO[e.key]) { location.href = GOTO[e.key]; }
      else if (e.key === "g") { pending = true; clearTimeout(timer); timer = setTimeout(() => { pending = null; }, SEQUENCE_MS); return; }
      pending = null;
    });
  }

  /* ---- forms: confirm destructive actions, guard against double submits ---- */
  function initForms() {
    document.addEventListener("submit", (e) => {
      const form = e.target;
      const message = form.dataset.confirm;
      if (message && !confirm(message)) { e.preventDefault(); return; }
      if (form.dataset.noLock !== undefined) return;
      const btn = form.querySelector('button:not([type="button"])');
      if (btn) setTimeout(() => { btn.disabled = true; btn.setAttribute("aria-busy", "true"); }, 0);
    });
    // Back/forward cache restores disabled buttons; re-enable them.
    window.addEventListener("pageshow", () => $$("button[aria-busy]").forEach((b) => { b.disabled = false; b.removeAttribute("aria-busy"); }));
    $$("[data-copy]").forEach((btn) => btn.addEventListener("click", async () => {
      const url = new URL(btn.dataset.copy || location.href, location.href).href;
      try { await navigator.clipboard.writeText(url); toast("Link kopiert."); } catch { toast("Kopieren nicht möglich.", "warn"); }
    }));
  }

  /* ---- collapsible panels: remember state, open on anchor navigation ---- */
  function initPanels() {
    const panels = $$("details.panel[id]");
    if (!panels.length) return;
    let saved = {};
    try { saved = JSON.parse(store.get(STORE_PANELS) || "{}"); } catch { saved = {}; }
    const key = (p) => location.pathname.startsWith("/stocks/") ? "stock:" + p.id : location.pathname + ":" + p.id;
    panels.forEach((p) => { if (key(p) in saved) p.open = saved[key(p)]; });
    const openTarget = () => {
      const id = decodeURIComponent(location.hash.slice(1));
      const target = id && document.getElementById(id);
      if (target && target.matches("details")) { target.open = true; target.scrollIntoView(); }
    };
    openTarget();
    window.addEventListener("hashchange", openTarget);
    panels.forEach((p) => p.addEventListener("toggle", () => {
      saved[key(p)] = p.open;
      store.set(STORE_PANELS, JSON.stringify(saved));
    }));
    $$('a[href^="#"]').forEach((a) => a.addEventListener("click", () => setTimeout(openTarget, 0)));
  }

  document.addEventListener("DOMContentLoaded", () => {
    handleFlash(); initTheme(); initNav(); initPalette(); initShortcuts(); initForms(); initPanels();
  });
})();
