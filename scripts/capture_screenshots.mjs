// Plays the copper research walk-through against a running demo instance and stores the
// screenshots used by docs/user-manual.md. It fails loudly if a step does not work, so it
// doubles as an end-to-end acceptance test.
//   make demo   (in another shell)   then   node scripts/capture_screenshots.mjs
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const OUT = path.resolve("docs/screenshots");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 900 }, deviceScaleFactor: 2 });
// The acceptance run must not depend on outside tile servers: use the built-in background.
const offlineMap = () => localStorage.setItem("basemap", "plain");
await page.addInitScript(offlineMap);
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
page.on("pageerror", (e) => problems.push(String(e)));

let index = 0;
const shot = async (name) => {
  await page.waitForTimeout(700); // let the map finish drawing
  index += 1;
  await page.screenshot({ path: path.join(OUT, `${String(index).padStart(2, "0")}_${name}.png`) });
};
const panel = page.getByTestId("asset-panel");
const openAsset = async (name) => {
  await page.getByPlaceholder("Suche").fill(name.slice(5, 16));
  await page.locator(".search li button", { hasText: name }).click();
  await panel.getByRole("heading", { name }).waitFor();
};

await page.goto(BASE);
await page.getByTestId("overview").waitFor();
await page.locator(".map canvas").waitFor();
await shot("explorer");

// 1 open the thesis, 2 discover a producing copper mine
await page.getByTestId("overview").getByRole("button", { name: /Kupfernachfrage/ }).click();
await shot("these_auf_karte");
await page.getByTestId("overview").getByRole("button", { name: "Demo Mina Altiplano" }).click();
await panel.waitFor();
await shot("charakterkarte");
await panel.locator('tr[data-metric="aisc"]').click();
await page.getByTestId("derivation").getByText("All-in sustaining costs").first().waitFor();
await shot("herleitung");
await page.getByTestId("derivation").getByRole("button", { name: "Schliessen" }).click();

// 3 switch to the company perspective without leaving the map
await panel.getByRole("button", { name: "Demo Andes Copper Corp" }).click();
const company = page.getByTestId("company-panel");
await company.getByTestId("checklist").waitFor();
await shot("unternehmen_hervorgehoben");
await company.getByRole("button", { name: "Demo Mina Altiplano" }).click();
await panel.waitFor();
await page.getByRole("button", { name: "Hervorhebung aufheben" }).click();
await panel.getByRole("button", { name: "+ Zur Auswahl" }).click();

// 4 mark the neighbouring exploration project, 5 note a research question
await openAsset("Demo Projekt Vecino");
await panel.getByRole("button", { name: "+ Zur Auswahl" }).click();
await panel.getByTestId("add-question").click();
await page.getByRole("status").getByText("Frage vorgemerkt").waitFor();
await shot("projekt_und_frage");
await page.getByTestId("compare-button").click();
await page.getByTestId("compare").waitFor();
await shot("vergleich");
await page.getByTestId("compare").getByRole("button", { name: "Schliessen" }).click();

// 6 review the backlog and start deliberately
await page.getByRole("button", { name: "Research", exact: true }).click();
await page.getByTestId("backlog").waitFor();
await shot("backlog");
const takeover = page.locator("[data-proposal]", { hasText: "Übernahmeziel" }).filter({ hasText: "von dir" });
await takeover.getByRole("button", { name: "Starten" }).click();

// 7 keep exploring meanwhile: a mine with unknown cost
await page.getByRole("button", { name: "Explorer", exact: true }).click();
await openAsset("Demo Mina Laguna Clara");
await shot("kosten_unbekannt");
const proposal = panel.locator(".cardlist > div", { hasText: "AISC" }).first();
await proposal.getByRole("button", { name: "Starten" }).click();

// 8 the sourced result appears at the object
await panel.locator('tr[data-metric="aisc"]', { hasText: "2,31" }).waitFor({ timeout: 30000 });
await shot("ergebnis_am_objekt");
await panel.locator('tr[data-metric="aisc"]').click();
await page.getByTestId("derivation").getByText("US$2.31 per lb").waitFor();
await shot("ergebnis_mit_zitat");
await page.getByTestId("derivation").getByRole("button", { name: "Schliessen" }).click();

// scenario and reference date
await page.goto(`${BASE}/?c=copper&color=margin&sc=copper:3.2`);
await page.getByTestId("banner").waitFor();
await shot("szenario");
await page.goto(`${BASE}/?c=copper&a=1&asof=2015-01-01`);
await page.getByTestId("asset-panel").getByText("Studienwerte").waitFor();
await shot("stichtag");
await page.goto(`${BASE}/?color=knowledge`);
await page.getByTestId("legend").getByText("Vertieft untersucht").waitFor();
await shot("wissensstatus");

// 9 what changed since the last visit, and the result of the question
await page.goto(`${BASE}/research`);
await page.getByTestId("tickets").getByRole("button", { name: /Übernahmeziel/ }).first().click();
await page.getByTestId("ticket-result").waitFor();
await shot("rechercheergebnis");
await page.getByTestId("ticket-result").getByRole("button", { name: "Schliessen" }).click();
await shot("lagebericht");

await page.getByRole("button", { name: "Portfolio", exact: true }).click();
await page.getByTestId("holdings").getByPlaceholder("Symbol").fill("DACC");
await page.getByPlaceholder("Stück").fill("100");
await page.getByPlaceholder("Ø Kaufpreis").fill("42");
await page.getByTestId("holding-thesis").selectOption({ index: 1 });
await page.getByPlaceholder("Warum kaufst du?").fill("Tiefkosten-Produzent mit Hebel auf Kupfer");
await page.getByPlaceholder("Ausstiegsbedingung").fill("Verkauf, wenn AISC über 2,60 USD/lb steigt");
await page.getByTestId("holdings").getByRole("button", { name: "Hinzufügen" }).click();
await page.getByTestId("holdings").getByText("DACC", { exact: true }).waitFor();
await page.getByTestId("journal").getByRole("cell", { name: "Kauf", exact: true }).waitFor();
await shot("portfolio");
await page.getByRole("button", { name: "Quellen", exact: true }).click();
await page.getByTestId("sources").getByText("Demo-Jahresbericht").first().waitFor();
await shot("quellen");
await page.getByRole("button", { name: "System", exact: true }).click();
await page.getByTestId("system").waitFor();
await shot("system");

// the junior: short runway, dilution, open checklist items
await page.getByRole("button", { name: "Explorer", exact: true }).click();
await page.getByPlaceholder("Suche").fill("Junior");
await page.locator(".search li button", { hasText: "Demo Junior Explorers" }).click();
await company.getByText("Reichweite ab heute").waitFor();
await shot("junior_unternehmen");

// import an analysis: visible at once, marked unverified, then confirmed by the user
await page.getByRole("button", { name: "Quellen", exact: true }).click();
const importer = page.getByTestId("import");
await importer.getByRole("button", { name: "Beispiel einsetzen" }).click();
await importer.getByTestId("import-run").click();
await importer.getByTestId("import-report").getByText("1 neue").waitFor();
await importer.getByTestId("unverified").getByText("Mina Ejemplo").first().waitFor();
await shot("analyse_import");
await page.getByRole("button", { name: "Explorer", exact: true }).click();
await page.getByPlaceholder("Suche").fill("Ejemplo");
await page.locator(".search li button", { hasText: "Mina Ejemplo" }).click();
await panel.getByText("ungeprüft").first().waitFor();
await shot("ungeprueft_am_objekt");
await panel.locator("[data-metric=aisc]").click();
page.once("dialog", (dialog) => dialog.accept("Im Geschäftsbericht 2025 des Betreibers nachgelesen"));
await page.getByTestId("derivation").getByRole("button", { name: "Selbst bestätigen" }).click();
await page.getByRole("status").getByText("Als eigene Annahme übernommen").waitFor();
await page.getByTestId("derivation").getByText("eigene Annahme, keine Primärquelle").waitFor();
await page.getByTestId("derivation").getByRole("button", { name: "Schliessen" }).click();

// sift all companies on one page
await page.getByRole("button", { name: "Unternehmen", exact: true }).click();
await page.getByTestId("companies").getByText("Demo Junior Explorers Ltd").waitFor();
await shot("unternehmen_sichten");

// the agent backend is chosen at runtime
await page.getByRole("button", { name: "System", exact: true }).click();
await page.getByTestId("agent").getByTestId("agent-runner").selectOption("openai");
await shot("agent_einstellung");

// macro: net liquidity is charted, a price can be shown in gold with the split below it
await page.getByRole("button", { name: "Makro", exact: true }).click();
await page.getByTestId("chart-note").getByText("Bilanzsumme der Fed − Konto des Finanzministeriums − Reverse Repo").waitFor();
await page.getByTestId("tile-copper").click();
await page.getByTestId("denominator").selectOption("gold");
await page.getByTestId("chart-note").getByText("Keine Kaufkraftbereinigung").waitFor();
await page.getByTestId("split").getByText("1 Jahr").waitFor();
await page.screenshot({ path: path.join(OUT, "29_makro_nenner.png") });

// the new commodities are in the bar; the theme switch goes automatic -> light -> dark and is kept
await page.getByTestId("commodities").getByText("Erdgas").waitFor();
await page.getByTestId("tile-LUMBER_GOLD").waitFor();
await page.getByTestId("theme").click();
await page.getByTestId("theme").click();
if ((await page.locator("html").getAttribute("data-theme")) !== "dark") throw new Error("dark theme not applied");
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "30_dunkel.png") });
await page.getByTestId("theme").click(); // back to automatic

// charts: every price in every yardstick, the lever chain adds up, a lens is saved, the regime map
await page.getByRole("button", { name: "Charts", exact: true }).click();
await page.getByTestId("ladder-slope").getByText("Empfindlichkeit").waitFor();
await page.getByTestId("ladder-deeper").click();
await page.getByTestId("ladder-dependents").getByText("Demo Andes Copper Corp").waitFor();
await page.getByTestId("ladder-deeper").click();
await page.getByTestId("ladder-trail").getByText("Dollar-Index").waitFor();
await page.getByTestId("ladder-space").check();
await page.screenshot({ path: path.join(OUT, "35_treiberleiter.png") });
await page.getByTestId("tab-matrix").click();
await page.getByTestId("cell-S:DACC-gold").click();
await page.getByTestId("matrix-detail").getByText("in Gold").waitFor();
await page.screenshot({ path: path.join(OUT, "31_massstab_matrix.png") });
await page.getByTestId("matrix").getByRole("button", { name: "Demo Andes Copper Corp (DACC)" }).click();
await page.getByTestId("chain").getByText("Unternehmen, gemessen in Kupfer").first().waitFor();
if ((await page.getByTestId("chain-link").count()) !== 3) throw new Error("lever chain needs three links");
await page.screenshot({ path: path.join(OUT, "32_hebelkette.png") });
await page.getByTestId("tab-lens").click();
await page.getByTestId("lens-unit").getByText("oz").waitFor();
const expected = problems.length;
await page.getByTestId("lens-input").fill("$objekt + DFII10");
await page.getByTestId("lens-run").click();
await page.getByTestId("lens-error").getByText("Einheiten passen nicht").waitFor();
problems.splice(expected); // the refused formula is answered with 400 on purpose
await page.getByTestId("lens-input").fill("ma($objekt / copper, 4)");
await page.getByTestId("lens-run").click();
await page.getByTestId("lens-unit").getByText("lb").waitFor();
await page.getByTestId("lens-name").fill("in Kupfer, geglättet");
await page.getByTestId("lens-save").click();
await page.getByTestId("saved-in Kupfer, geglättet").waitFor();
await page.screenshot({ path: path.join(OUT, "33_linse.png") });
await page.getByTestId("tab-regime").click();
await page.getByTestId("regime").locator("svg.regime").waitFor();
await page.getByTestId("regime-read").getByText("Heute").waitFor();
await page.screenshot({ path: path.join(OUT, "34_regimekarte.png") });

// a phone: the panel sits below the map, nothing is cut off to the right
const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await phone.addInitScript(offlineMap);
await phone.goto(`${BASE}/companies`);
await phone.getByTestId("companies").getByText("Demo Junior Explorers Ltd").waitFor();
const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
if (overflow > 2) problems.push(`Phone layout scrolls sideways by ${overflow}px`);
await phone.screenshot({ path: path.join(OUT, "25_handy.png") });
await phone.close();

await browser.close();
if (problems.length) {
  console.error("Browser errors:\n" + problems.join("\n"));
  process.exit(1);
}
console.log(`${index} screenshots written to ${OUT}`);
