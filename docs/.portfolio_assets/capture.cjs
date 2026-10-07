const { chromium } = require("C:/Users/shobh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
(async () => {
  const browser = await chromium.launch({ headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 920 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:8002/", { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.locator("#promptInput").waitFor({ state: "visible", timeout: 15000 });
    await page.waitForTimeout(700);
    await page.screenshot({ path: "docs/.portfolio_assets/welcome.jpg", type: "jpeg", quality: 90 });
    const investigate = page.getByRole("tab", { name: /Investigate claim/ });
    await investigate.click();
    await page.locator("#promptInput").fill("Does TP53 activation cause cell-cycle arrest in human cancer cells following DNA damage?");
    await page.locator("#sendButton").click();
    await page.getByRole("heading", { name: "Evidence assessment" }).waitFor({ state: "visible", timeout: 120000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: "docs/.portfolio_assets/investigation.jpg", type: "jpeg", quality: 90 });
    const cards = page.getByText(/EVIDENCE CARDS/).first();
    await cards.evaluate(el => el.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(300);
    await page.screenshot({ path: "docs/.portfolio_assets/evidence-cards.jpg", type: "jpeg", quality: 90 });
    console.log(JSON.stringify({ title: await page.title(), text: (await page.locator("#messageView").innerText()).slice(0, 500), screenshots: ["welcome.jpg", "investigation.jpg", "evidence-cards.jpg"] }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e.stack || e); process.exit(1); });

