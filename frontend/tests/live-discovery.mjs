import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const base = process.env.E2E_BASE_URL || "http://localhost:3001";
const directory = "../artifacts/frontend-work/live-discovery";
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
const evidence = { base, started_at: new Date().toISOString(), errors: [] };
page.on("pageerror", (error) => evidence.errors.push(error.message));
try {
  await page.goto(`${base}/app`);
  await page.getByPlaceholder("Например, Potsdam").fill("Potsdam");
  await page.getByPlaceholder("DE", { exact: true }).fill("DE");
  const response = page.waitForResponse((r) =>
    r.url().includes("/api/v1/regions?"),
  );
  await page.getByRole("button", { name: "Найти регион", exact: true }).click();
  const regions = await (await response).json();
  evidence.regions = regions.items;
  if (!regions.items?.length) throw new Error("Поиск не вернул Potsdam");
  await page
    .getByRole("button", { name: regions.items[0].name, exact: true })
    .click();
  // Камера выставляет bbox после fitBounds, далее запуск — отдельное действие пользователя.
  await page.waitForTimeout(1000);
  const acceptedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/discoveries") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Найти контуры OSM на карте" })
    .click();
  const accepted = await (await acceptedResponse).json();
  evidence.discovery = accepted;
  if (!accepted.discovery_id) throw new Error(JSON.stringify(accepted));
  const candidatesResponse = await page.waitForResponse(
    (r) => r.url().includes(`/api/v1/discoveries/${accepted.discovery_id}?`),
    { timeout: 180000 },
  );
  const candidates = await candidatesResponse.json();
  evidence.candidate_count = candidates.items.length;
  if (!candidates.items.length)
    throw new Error("OSM не вернул контуров в этом viewport");
  await page
    .locator(".map-panel .result-list button")
    .filter({ hasText: /га/ })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "Название", exact: true })
    .fill("Потсдам · контур из поиска OSM");
  const savedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/polygons") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Сохранить поле", exact: true })
    .click();
  evidence.polygon = await (await savedResponse).json();
  if (evidence.polygon.source !== "osm")
    throw new Error("Не сохранено происхождение OSM");
  await page.getByRole("link", { name: "Открыть анализ" }).waitFor();
  await page.screenshot({ path: `${directory}/map.png`, fullPage: true });
  if (evidence.errors.length) throw new Error(evidence.errors.join("\n"));
  console.log(
    "PASS: real Nominatim → viewport → Overpass → candidate → saved OSM polygon",
    evidence.candidate_count,
  );
} catch (error) {
  evidence.failure = String(error);
  await page.screenshot({ path: `${directory}/failure.png`, fullPage: true });
  throw error;
} finally {
  evidence.finished_at = new Date().toISOString();
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(evidence, null, 2),
  );
  await browser.close();
}
