import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ contextOptions: { reducedMotion: "no-preference" } });
// В CI SwiftShader считает полноразмерный кадр на CPU; захват PNG тоже ждёт GPU.
// Проверяем те же пиксели и ракурсы, предоставляя программному рендереру больше времени.
const frameTimeout = process.env.CI ? 45000 : 12000;

async function scrollStory(page: Page, progress: number) {
  // Программная постановка кадра следует после завершения реального wheel-события.
  await expect(page.locator("html")).not.toHaveClass(/lenis-smooth/);
  await page.locator("[data-hero]").evaluate((element, p) => {
    const stage = element.querySelector<HTMLElement>("[data-hero-stage]")!;
    window.scrollTo(
      0,
      (element as HTMLElement).offsetTop +
        ((element as HTMLElement).offsetHeight - stage.offsetHeight) * p,
    );
  }, progress);
  await expect
    .poll(async () =>
      Number(await page.locator("[data-hero]").getAttribute("data-progress")),
    )
    .toBeCloseTo(progress, 2);
}

async function oceanCenter(page: Page) {
  // Проверяем изображение, а не только прогресс/координаты Three.js.
  const png = await page.screenshot({ timeout: frameTimeout });
  return page.evaluate(async (base64) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(image, 0, 0);
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let count = 0,
      x = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (
        data[i + 2] > 45 &&
        data[i + 2] > data[i] * 1.4 &&
        data[i + 2] > data[i + 1] * 1.2
      ) {
        count++;
        x += (i / 4) % canvas.width;
      }
    }
    return { count, x: x / Math.max(1, count) / canvas.width };
  }, png.toString("base64"));
}

test("Земля и текст проходят весь hero и возвращаются при обратной прокрутке", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(process.env.CI ? 180000 : 90000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator("[data-hero]")).toHaveAttribute(
    "data-motion",
    "true",
  );
  await page.mouse.move(200, 150);
  await expect(page.locator("[data-planet]")).toHaveAttribute(
    "data-ready",
    "true",
    { timeout: 45000 },
  );
  await scrollStory(page, 0.3);
  const first = page.locator('[data-story-panel="Территория"]');
  await expect(first).toHaveCSS("opacity", "1");
  const stage = await page.locator("[data-hero-stage]").boundingBox();
  expect(stage!.y).toBeCloseTo(0, 0);
  expect((await page.locator("#features").boundingBox())!.y).toBeGreaterThan(
    page.viewportSize()!.height,
  );
  await expect
    .poll(async () => (await oceanCenter(page)).count, {
      timeout: frameTimeout,
    })
    .toBeGreaterThan(1000);
  const left = await oceanCenter(page);
  if (!isMobile) expect(left.x).toBeLessThan(0.42);
  await page.screenshot({ path: testInfo.outputPath("earth-left.png") });

  await scrollStory(page, 0.59);
  await expect(page.locator('[data-story-panel="Наблюдения"]')).toHaveCSS(
    "opacity",
    "1",
  );
  await expect(first).toHaveCSS("visibility", "hidden");
  await expect
    .poll(async () => (await oceanCenter(page)).x, { timeout: frameTimeout })
    .toBeGreaterThan(isMobile ? 0.46 : 0.58);
  await page.screenshot({ path: testInfo.outputPath("earth-right.png") });

  await scrollStory(page, 0.92);
  await expect(page.locator('[data-story-panel="Контекст"]')).toHaveCSS(
    "opacity",
    "1",
  );
  await scrollStory(page, 0.3);
  await expect(first).toHaveCSS("opacity", "1");
  await expect
    .poll(async () => Math.abs((await oceanCenter(page)).x - left.x), {
      timeout: frameTimeout,
    })
    .toBeLessThan(0.04);
  await scrollStory(page, 1);
  const featuresY = (await page.locator("#features").boundingBox())!.y;
  expect(Math.abs(featuresY - stage!.height)).toBeLessThan(3);
  await page.keyboard.press("PageDown");
  await expect
    .poll(
      async () => (await page.locator("[data-hero-stage]").boundingBox())!.y,
    )
    .toBeLessThan(-100);
  await page.locator("#features").scrollIntoViewIfNeeded();
  await expect(page.locator("#features").getByRole("tablist")).toBeInViewport();
  expect(errors).toEqual([]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect
    .poll(() =>
      page.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    )
    .toBe(true);
  await expect(page.locator("[data-planet]")).toHaveAttribute(
    "data-ready",
    "false",
  );
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(page.locator("[data-hero]")).toHaveAttribute(
    "data-motion",
    "true",
  );
  await scrollStory(page, 0.3);
  await expect(page.locator("[data-planet]")).toHaveAttribute(
    "data-ready",
    "true",
  );
  await expect
    .poll(async () => (await oceanCenter(page)).count, {
      timeout: frameTimeout,
    })
    .toBeGreaterThan(1000);
});

test("рассказ остаётся читаемым без анимации и без WebGL", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (
        type === "webgl" ||
        type === "webgl2" ||
        type === "experimental-webgl"
      )
        return null;
      return original.call(this, type, ...args);
    } as typeof original;
  });
  await page.goto("/");
  await expect(page.locator("[data-hero]")).toHaveAttribute(
    "data-motion",
    "true",
  );
  await page.mouse.move(200, 150);
  await scrollStory(page, 0.59);
  await expect(page.locator('[data-story-panel="Наблюдения"]')).toHaveCSS(
    "opacity",
    "1",
  );
  await expect(page.locator("[data-planet-poster]")).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-hero]")).not.toHaveAttribute("data-motion");
  for (const label of ["Территория", "Наблюдения", "Контекст"]) {
    const article = page.locator(`[data-story-panel="${label}"]`);
    await expect(article).toBeVisible();
    expect(
      await article.evaluate((element) => (element as HTMLElement).inert),
    ).toBe(false);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("без JavaScript все главы доступны по порядку", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto(baseURL || "http://localhost:3001/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const panels = page.locator("[data-story-panel]");
  expect(await panels.count()).toBe(4);
  const boxes = await panels.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    }),
  );
  for (let i = 1; i < boxes.length; i++)
    expect(boxes[i].top).toBeGreaterThanOrEqual(boxes[i - 1].bottom);
  await context.close();
});

test("колесо, якоря и изменение размера сохраняют навигацию и читаемость", async ({
  page,
  isMobile,
}) => {
  test.setTimeout(90000);
  await page.goto("/");
  await expect(page.locator("[data-hero]")).toHaveAttribute(
    "data-motion",
    "true",
  );
  if (!isMobile) {
    await page.mouse.move(700, 500);
    await page.mouse.wheel(0, 1100);
    await expect
      .poll(async () =>
        Number(await page.locator("[data-hero]").getAttribute("data-progress")),
      )
      .toBeGreaterThan(0.2);
    expect(
      (await page.locator("[data-hero-stage]").boundingBox())!.y,
    ).toBeCloseTo(0, 0);
  }
  for (const [width, height] of [
    [1440, 1000],
    [1024, 900],
    [768, 1024],
    [390, 844],
    [390, 700],
  ]) {
    await page.setViewportSize({ width, height });
    // ScrollTrigger пересчитывает длину закреплённой секции после resize.
    await page.waitForTimeout(250);
    await scrollStory(page, 0.59);
    const body = await page
      .locator('[data-story-panel="Наблюдения"] > div')
      .boundingBox();
    const link = await page
      .getByRole("link", { name: "К возможностям", exact: true })
      .boundingBox();
    expect(body!.x).toBeGreaterThanOrEqual(0);
    expect(body!.x + body!.width).toBeLessThanOrEqual(width);
    expect(body!.y).toBeGreaterThan(80);
    expect(body!.y + body!.height).toBeLessThan(link!.y - 8);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  const accessible = await new AxeBuilder({ page })
    .include("[data-hero]")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(accessible.violations).toEqual([]);
  await expect(
    page
      .getByRole("list", { name: "От контура к анализу" })
      .getByRole("heading"),
  ).toHaveCount(3);
  await page.getByRole("link", { name: "К возможностям", exact: true }).click();
  await expect(page.locator("#features").getByRole("tablist")).toBeInViewport();
  await page.goto("/#features");
  await expect(page.locator("#features").getByRole("tablist")).toBeInViewport();
  await page.setViewportSize({ width: 390, height: 600 });
  await expect(page.locator("[data-hero]")).not.toHaveAttribute("data-motion");
  await expect(page.locator('[data-story-panel="Наблюдения"]')).toHaveCSS(
    "position",
    "relative",
  );
});
