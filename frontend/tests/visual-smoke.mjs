import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const base = process.env.E2E_BASE_URL || "http://localhost:3001";
const directory = "../artifacts/frontend-work/visual-smoke";
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "no-preference",
});
const evidence = { base, errors: [], cycles: [] };
page.on("pageerror", (error) => evidence.errors.push(error.message));
try {
  await page.goto(base);
  for (let cycle = 0; cycle < 3; cycle++) {
    await page.locator(".planet-canvas.ready").waitFor({ timeout: 30000 });
    if (cycle === 0)
      await page.screenshot({ path: `${directory}/landing-desktop.png` });
    await page.getByRole("link", { name: "Исследовать поле" }).click();
    await page
      .getByRole("button", { name: "Нарисовать контур", exact: true })
      .waitFor();
    if (await page.locator(".planet-canvas").count())
      throw new Error("Планета осталась после перехода в приложение");
    const map = await page.locator(".map-canvas").boundingBox();
    if (!map || map.height < 400) throw new Error("Неверный размер карты");
    evidence.cycles.push({
      cycle,
      planet_canvases: 0,
      workspace_canvases: await page.locator("canvas").count(),
      map_height: map.height,
    });
    await page.locator(".sidebar .brand").click();
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 700 ? 844 : 1000 });
    if (
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      )
    )
      throw new Error(`Landing overflow ${width}`);
    if (width === 390)
      await page.screenshot({
        path: `${directory}/landing-mobile.png`,
        fullPage: true,
      });
  }
  if (evidence.errors.length) throw new Error(evidence.errors.join("\n"));
  evidence.passed = true;
  console.log(
    "PASS: three landing/app transitions, WebGL scene, reduced motion, four viewport widths",
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
