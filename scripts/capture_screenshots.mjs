// Captures the screenshots used by docs/user-manual.md from a running instance.
// Usage: BASE_URL=http://localhost:8000 node scripts/capture_screenshots.mjs
// The instance should run with demo data (make demo) so the documentation is reproducible.
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

// createRequire so a globally installed Playwright (NODE_PATH) is found too.
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const OUT = new URL("../docs/screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "dark" });

async function shot(name, path, { full = true, prepare } = {}) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  if (prepare) await prepare();
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: full });
  console.log("saved", name);
}

await shot("01-dashboard", "/");
await shot("02-holdings", "/holdings");
await shot("03-holdings-error", "/holdings", {
  prepare: async () => {
    await page.fill('input[name="symbol"]', "AAPL");
    await page.fill('input[name="quantity"]', "10");
    await page.fill('input[name="avg_price"]', "150");
    await page.click('button[type="submit"]');
    await page.waitForLoadState("networkidle");
  },
  full: false,
});
await shot("04-watchlist", "/watchlist");
// Quick-jump palette (key "/") and the confirmation toast shown after an action.
await shot("21-palette", "/", {
  full: false,
  prepare: async () => {
    await page.keyboard.press("/");
    await page.keyboard.type("n");
    await page.waitForSelector("#palette-list li a");
  },
});
await shot("22-toast", "/holdings?flash=holding_added", { full: false, prepare: () => page.waitForSelector(".toast") });
await shot("23-shortcuts", "/", {
  full: false,
  prepare: async () => {
    await page.keyboard.press("?");
    await page.waitForSelector("dialog#help[open]");
  },
});
// Resolve stock ids by symbol from the holdings page.
await page.goto(`${BASE}/holdings`, { waitUntil: "networkidle" });
const ids = await page.$$eval('a[href^="/stocks/"] strong', (els) =>
  Object.fromEntries(els.map((e) => [e.textContent.trim(), e.parentElement.getAttribute("href")])));

await shot("05-stock-tech", ids["AAPL"]);
await shot("06-stock-chart-daily", ids["AAPL"], {
  full: false,
  prepare: async () => {
    await page.click('button[data-interval="1d"]');
    await page.waitForTimeout(500);
    await page.hover("#chart svg", { position: { x: 500, y: 150 } });
  },
});
await shot("10-stock-mining", ids["NEM"]);
await shot("11-mining-valuation", ids["NEM"], {
  full: false,
  prepare: async () => {
    await page.locator("#valuation").scrollIntoViewIfNeeded();
  },
});
await shot("12-mining-evidence", ids["NEM"], {
  full: false,
  prepare: async () => {
    await page.locator("#evidence").scrollIntoViewIfNeeded();
  },
});
await shot("13-stock-oil", ids["XOM"]);
await shot("14-intel", "/intel", { full: false });
await shot("15-intel-primary", "/intel?primary=1&category=hazard", { full: false });
await shot("16-map", "/map", {
  full: false,
  prepare: async () => {
    await page.waitForSelector("#map svg path");
    await page.locator("#map circle").first().click();
  },
});
await shot("17-graph", `/graph?stock=${ids["NEM"].split("/").pop()}`, {
  full: false,
  prepare: async () => {
    await page.waitForSelector("#graph svg circle");
    await page.locator("#graph svg g").nth(2).click();
  },
});
await shot("18-commodities", "/commodities");
let filing = null;
for (let id = 1; id < 80 && !filing; id++) {
  const res = await page.request.get(`${BASE}/documents/${id}`);
  if (res.ok() && (await res.text()).includes("Item 2. Properties")) filing = id;
}
await shot("19-document", `/documents/${filing}`);
await shot("20-feeds", "/intel/feeds", { full: false });
await shot("07-tickets", "/tickets");
await shot("24-holdings-sorted", "/holdings", {
  full: false,
  prepare: async () => {
    await page.click("#holdings-table th:nth-child(8) button");
    await page.click("#holdings-table th:nth-child(8) button");
  },
});
const light = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
await light.goto(`${BASE}${ids["NEM"]}`, { waitUntil: "networkidle" });
await light.screenshot({ path: `${OUT}25-light-theme.png`, fullPage: false });
const phone = await browser.newPage({ viewport: { width: 390, height: 800 }, colorScheme: "dark" });
await phone.goto(`${BASE}/`, { waitUntil: "networkidle" });
await phone.click("#nav-toggle");
await phone.screenshot({ path: `${OUT}26-mobile-menu.png`, fullPage: false });
await phone.goto(`${BASE}${ids["AAPL"]}`, { waitUntil: "networkidle" });
await phone.screenshot({ path: `${OUT}27-mobile-stock.png`, fullPage: false });
await shot("08-ticket-detail", "/tickets/1");
await shot("09-system", "/system");
await browser.close();
