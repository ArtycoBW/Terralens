import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const base = process.env.E2E_BASE_URL || "http://localhost:3001";
const directory = "../artifacts/redesign/visual-smoke";
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "no-preference",
});
const evidence = { base, errors: [], cycles: [] };
page.on("pageerror", (e) => evidence.errors.push(e.message));
try {
  await page.goto(base);
  for (let cycle = 0; cycle < 3; cycle++) {
    await page.locator('[data-planet][data-hydrated="true"]').waitFor();
    await page.mouse.move(700 + cycle * 5, 200);
    await page
      .locator("[data-planet][data-ready=true]")
      .waitFor({ timeout: 30000 });
    await page.locator("[data-terrain]").scrollIntoViewIfNeeded();
    await page
      .locator("[data-terrain][data-ready=true]")
      .waitFor({ timeout: 30000 });
    await page
      .locator("header")
      .getByRole("link", { name: "Исследовать поле", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Рабочая карта", exact: true })
      .waitFor();
    if (await page.locator("[data-planet],[data-terrain]").count())
      throw Error("Landing canvas remained after navigation");
    const map = await page.locator("[data-map-canvas]").boundingBox();
    if (!map || map.height < 400) throw Error("Invalid map size");
    evidence.cycles.push({ cycle, landingCanvases: 0, mapHeight: map.height });
    await page
      .locator("[data-sidebar]")
      .getByRole("link", { name: "TerraLens", exact: true })
      .click();
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 700 ? 844 : 1000 });
    if (
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      )
    )
      throw Error(`Overflow ${width}`);
  }
  if (evidence.errors.length) throw Error(evidence.errors.join("\n"));
  evidence.passed = true;
  console.log(
    "PASS: three Earth/terrain/app transitions; five widths; no browser errors",
  );
} catch (error) {
  evidence.failure = String(error);
  throw error;
} finally {
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(evidence, null, 2),
  );
  await browser.close();
}
