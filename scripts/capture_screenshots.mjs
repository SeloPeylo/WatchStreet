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
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

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
    await page.fill('input[name="quantity"]', "zehn");
    await page.fill('input[name="avg_price"]', "150");
    await page.click('button[type="submit"]');
    await page.waitForLoadState("networkidle");
  },
  full: false,
});
await shot("04-watchlist", "/watchlist");
await shot("05-stock-detail", "/stocks/1");
await shot("06-stock-chart-daily", "/stocks/1", {
  full: false,
  prepare: async () => {
    await page.click('button[data-interval="1d"]');
    await page.waitForTimeout(500);
    await page.hover("#chart svg", { position: { x: 500, y: 150 } });
  },
});
await shot("07-tickets", "/tickets");
await shot("08-ticket-detail", "/tickets/1");
await shot("09-system", "/system");
await browser.close();
