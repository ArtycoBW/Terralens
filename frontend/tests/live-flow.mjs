import { chromium } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const base = process.env.E2E_BASE_URL || "http://localhost:3001";
const directory = "../artifacts/frontend-work/live-browser";
await mkdir(directory, { recursive: true });
const fixture = JSON.parse(
  await readFile("../backend/tests/fixtures/seville.geojson", "utf8"),
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
});
const page = await context.newPage();
const evidence = {
  started_at: new Date().toISOString(),
  base,
  geometry_source: fixture.properties,
  errors: [],
  exports: [],
};
page.on("pageerror", (error) => evidence.errors.push(error.message));
try {
  await page.goto(`${base}/app`);
  await page
    .getByRole("textbox", { name: "Название", exact: true })
    .fill("Севилья · сквозная проверка");
  await page.getByText("Контур GeoJSON / ввод без карты").click();
  await page
    .getByRole("textbox", { name: "Геометрия GeoJSON" })
    .fill(JSON.stringify(fixture.geometry));
  await page
    .getByRole("button", { name: "Сохранить поле", exact: true })
    .click();
  await page.getByRole("link", { name: "Открыть анализ" }).click();
  await page.getByLabel("Начало периода").fill("2024-06-01");
  await page.getByLabel("Конец периода").fill("2024-06-10");
  await page.getByLabel("Предыдущих сезонов для нормы").selectOption("0");
  await page
    .getByRole("button", { name: /Запустить спутниковый анализ/ })
    .click();
  await page.waitForURL("**/app/analyses/**");
  evidence.run_id = new URL(page.url()).pathname.split("/").at(-1);
  console.log("Started live run", evidence.run_id);
  await page.reload();
  await page
    .getByRole("tab", { name: "Динамика NDVI" })
    .waitFor({ timeout: 240000 });
  const result = await page.request.get(
    `${base}/api/v1/analyses/${evidence.run_id}`,
  );
  if (!result.ok()) throw new Error(`Run HTTP ${result.status()}`);
  evidence.run = await result.json();
  const series = await (
    await page.request.get(
      `${base}/api/v1/analyses/${evidence.run_id}/series?limit=100`,
    )
  ).json();
  if (series.items.length !== 10)
    throw new Error(`Expected 10 daily points, got ${series.items.length}`);
  evidence.series = series.items;
  await page
    .getByRole("img", { name: /График временного ряда/ })
    .first()
    .locator("canvas")
    .waitFor();
  await page
    .getByRole("heading", { name: "Севилья · сквозная проверка", exact: true })
    .waitFor();
  await page.screenshot({
    path: `${directory}/analysis-desktop.png`,
    fullPage: true,
  });
  for (const format of ["csv", "geojson", "json"]) {
    await page.getByRole("tab", { name: "Экспорт", exact: true }).click();
    await page.getByLabel("Формат", { exact: true }).selectOption(format);
    const request = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/exports") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Подготовить экспорт" }).click();
    const accepted = await (await request).json();
    const link = page.locator(
      `a[href="/api/v1/exports/${accepted.export_id}/download"]`,
    );
    await link.waitFor({ timeout: 45000 });
    const downloadEvent = page.waitForEvent("download");
    await link.click();
    const download = await downloadEvent;
    const path = `${directory}/result.${format}`;
    await download.saveAs(path);
    const bytes = await readFile(path);
    const digest = createHash("sha256").update(bytes).digest("hex");
    const metadata = await (
      await page.request.get(`${base}/api/v1/exports/${accepted.export_id}`)
    ).json();
    if (digest !== metadata.hash)
      throw new Error(`Download checksum mismatch: ${format}`);
    const manifest = await page.request.get(`${base}${metadata.manifest_url}`);
    if (!manifest.ok()) throw new Error(`Manifest failed: ${format}`);
    await writeFile(
      `${directory}/manifest-${format}.json`,
      JSON.stringify(await manifest.json(), null, 2),
    );
    evidence.exports.push({
      format,
      id: accepted.export_id,
      bytes: bytes.length,
      sha256: digest,
    });
    console.log("Verified export", format, bytes.length);
  }
  await page.goto(
    `${base}/app/compare?runs=${evidence.run_id}&alignment=day_of_year`,
  );
  await page.getByRole("columnheader", { name: "Ряд 1" }).waitFor();
  await page.screenshot({
    path: `${directory}/comparison-desktop.png`,
    fullPage: true,
  });
  await page.goto(`${base}/app/polygons/${evidence.run.polygon_id}`);
  await page.getByRole("button", { name: "Редактировать поле" }).click();
  await page
    .getByRole("textbox", { name: "Название поля", exact: true })
    .fill("Севилья · проверка завершена");
  await page.getByRole("button", { name: "Сохранить изменения" }).click();
  await page
    .getByRole("heading", { name: "Севилья · проверка завершена", exact: true })
    .waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}/app/analyses/${evidence.run_id}`);
  await page.getByRole("tab", { name: "Динамика NDVI" }).waitFor();
  await page
    .getByRole("img", { name: /График временного ряда/ })
    .first()
    .locator("canvas")
    .waitFor();
  await page
    .getByRole("heading", { name: "Севилья · проверка завершена", exact: true })
    .waitFor();
  await page.screenshot({
    path: `${directory}/analysis-mobile.png`,
    fullPage: true,
  });
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
  )
    throw new Error("Mobile horizontal overflow");
  const foreign = await browser.newContext();
  const other = await foreign.request.post(`${base}/api/v1/session`, {
    headers: { Origin: base },
    data: {},
  });
  if (!other.ok()) throw new Error("Second session failed");
  const denied = await foreign.request.get(
    `${base}/api/v1/analyses/${evidence.run_id}`,
  );
  if (denied.status() !== 404)
    throw new Error(`Private run leaked: ${denied.status()}`);
  await foreign.close();
  evidence.isolation_status = denied.status();
  evidence.completed_at = new Date().toISOString();
  if (evidence.errors.length) throw new Error(evidence.errors.join("\n"));
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(evidence, null, 2),
  );
  console.log(
    "PASS: live browser flow, all exports, comparison, rename, mobile and isolation",
  );
} catch (error) {
  evidence.failure = String(error);
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(evidence, null, 2),
  );
  await page.screenshot({ path: `${directory}/failure.png`, fullPage: true });
  throw error;
} finally {
  await browser.close();
}
