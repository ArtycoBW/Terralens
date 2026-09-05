import { test, expect } from "@playwright/test";
import { mockApi, run } from "./fixtures";

test.use({ contextOptions: { reducedMotion: "no-preference" } });

for (const [name, path, surface] of [
  ["карта", "/app", "[data-map-canvas] canvas"],
  ["график анализа", `/app/analyses/${run.id}`, 'main [role="img"] canvas'],
  ["список полей", "/app/polygons", 'main [role="combobox"]'],
]) {
  test(`навигация не вызывает мерцание: ${name}`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "На телефоне навигация открывается в Sheet");
    await mockApi(page);
    await page.goto(path);
    await expect(page.locator(surface).first()).toBeVisible();
    const rail = page.locator("[data-sidebar]");
    const outside = page.locator("main h1");
    await outside.hover();
    await expect
      .poll(async () => (await rail.boundingBox())!.width)
      .toBeCloseTo(76, 0);

    // Track every painted frame, not just the identical start/end positions.
    const monitor = await page.evaluateHandle((selector) => {
      const main = document.querySelector("main")!;
      const surface = document.querySelector(selector)!;
      const sidebar = document.querySelector("[data-sidebar]")!;
      const samples: {
        x: number;
        width: number;
        surfaceWidth: number;
        connected: boolean;
        sidebarWidth: number;
      }[] = [];
      let canvasResets = 0;
      const observer = new MutationObserver((changes) => {
        canvasResets += changes.length;
      });
      observer.observe(surface, {
        attributes: true,
        attributeFilter: ["width", "height"],
      });
      let frame = 0;
      const sample = () => {
        const rect = main.getBoundingClientRect();
        samples.push({
          x: rect.x,
          width: rect.width,
          surfaceWidth: surface.getBoundingClientRect().width,
          connected: surface.isConnected,
          sidebarWidth: sidebar.getBoundingClientRect().width,
        });
        frame = requestAnimationFrame(sample);
      };
      sample();
      return {
        stop: () => {
          cancelAnimationFrame(frame);
          observer.disconnect();
          return { samples, canvasResets };
        },
      };
    }, surface);

    for (let cycle = 0; cycle < 2; cycle++) {
      // Target the fixed icon rail, including when labels are clipped.
      await page.mouse.move(35, 130);
      await expect(rail).toHaveAttribute("data-open", "true");
      await expect
        .poll(async () => (await rail.boundingBox())!.width)
        .toBeCloseTo(248, 0);
      await outside.hover();
      await expect(rail).toHaveAttribute("data-open", "false");
      await expect
        .poll(async () => (await rail.boundingBox())!.width)
        .toBeCloseTo(76, 0);
    }
    const { samples, canvasResets } = await monitor.evaluate((value) =>
      value.stop(),
    );
    await monitor.dispose();
    expect(samples.length).toBeGreaterThan(10);
    expect(
      samples.some(
        (sample) => sample.sidebarWidth > 90 && sample.sidebarWidth < 230,
      ),
    ).toBe(true);
    expect(samples.every((sample) => sample.connected)).toBe(true);
    expect(
      Math.max(...samples.map((s) => s.x)) -
        Math.min(...samples.map((s) => s.x)),
    ).toBeLessThan(1);
    expect(
      Math.max(...samples.map((s) => s.width)) -
        Math.min(...samples.map((s) => s.width)),
    ).toBeLessThan(1);
    expect(
      Math.max(...samples.map((s) => s.surfaceWidth)) -
        Math.min(...samples.map((s) => s.surfaceWidth)),
    ).toBeLessThan(1);
    expect(canvasResets).toBe(0);

    const resizeMonitor = await page.evaluateHandle((selector) => {
      const surface = document.querySelector(selector)!;
      const widths: number[] = [];
      const observer = new ResizeObserver(([entry]) =>
        widths.push(entry.contentRect.width),
      );
      observer.observe(surface);
      return {
        stop: () => {
          observer.disconnect();
          return { widths, connected: surface.isConnected };
        },
      };
    }, surface);
    await rail.getByRole("button", { name: "Закрепить навигацию" }).click();
    await expect
      .poll(async () => (await page.locator("main").boundingBox())!.x)
      .toBeCloseTo(248, 0);
    await rail.getByRole("button", { name: "Свернуть навигацию" }).click();
    await expect
      .poll(async () => (await page.locator("main").boundingBox())!.x)
      .toBeCloseTo(76, 0);
    const resizes = await resizeMonitor.evaluate((value) => value.stop());
    await resizeMonitor.dispose();
    expect(resizes.connected).toBe(true);
    // Initial measurement plus at most one resize for each pin/unpin action.
    expect(resizes.widths.length).toBeLessThanOrEqual(3);
    expect(new Set(resizes.widths).size).toBe(2);
  });
}

test("навигация выдерживает быстрое наведение, закрепление и управление клавиатурой", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "На телефоне используется Sheet");
  await mockApi(page);
  await page.goto("/app/polygons");
  const rail = page.locator("[data-sidebar]");
  const search = page.getByRole("textbox", { name: "Поиск" });
  await search.fill("Тестовое");
  const before = await page.locator("main").boundingBox();
  await page.mouse.move(35, 130);
  await rail.getByRole("button", { name: "Закрепить навигацию" }).click();
  await search.hover();
  await expect(rail).toHaveAttribute("data-open", "true");
  await rail.getByRole("button", { name: "Свернуть навигацию" }).click();
  await expect(rail).toHaveAttribute("data-open", "false");
  await page.mouse.move(800, 130);
  for (let cycle = 0; cycle < 3; cycle++) {
    await page.mouse.move(35, 130);
    await page.waitForTimeout(100);
    await page.mouse.move(800, 130);
    await page.waitForTimeout(100);
  }
  // Release focus left on the pin control before checking hover-only dismissal.
  await search.focus();
  await expect
    .poll(async () => (await rail.boundingBox())!.width)
    .toBeCloseTo(76, 0);
  await expect(search).toHaveValue("Тестовое");
  expect(await page.locator("main").boundingBox()).toEqual(before);
  await rail.getByRole("link", { name: "Сравнение", exact: true }).focus();
  await expect(rail).toHaveAttribute("data-open", "true");
  await page.keyboard.press("Escape");
  await expect(rail).toHaveAttribute("data-open", "false");
  await expect
    .poll(async () => (await rail.boundingBox())!.width)
    .toBeCloseTo(76, 0);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});

test("режим уменьшенного движения раскрывает панель сразу", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "На телефоне используется Sheet");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockApi(page);
  await page.goto("/app/polygons");
  const rail = page.locator("[data-sidebar]");
  await expect(rail).toBeVisible();
  await page.mouse.move(35, 130);
  await expect(rail).toHaveAttribute("data-open", "true");
  const width = await rail.evaluate(
    (element) =>
      new Promise<number>((resolve) => {
        requestAnimationFrame(() =>
          requestAnimationFrame(() =>
            resolve(element.getBoundingClientRect().width),
          ),
        );
      }),
  );
  expect(width).toBe(248);
});

test("мобильная навигация закрывается после перехода и возвращает доступ к странице", async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, "Проверка мобильной панели");
  await mockApi(page);
  await page.goto("/app/polygons");
  await page.getByRole("button", { name: "Открыть навигацию" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await sheet.getByRole("link", { name: "Сравнение", exact: true }).click();
  await expect(sheet).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Сравнение полей и сезонов" }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Совмещение рядов" }).click();
  await expect(page.getByRole("listbox")).toBeVisible();
});
