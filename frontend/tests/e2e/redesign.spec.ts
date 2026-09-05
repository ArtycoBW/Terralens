import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, polygon } from "./fixtures";

test("список статусов ограничен экраном и управляется клавиатурой", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/app/polygons");
  const select = page.getByRole("combobox", { name: "Статус анализа" });
  await select.focus();
  await page.keyboard.press("ArrowDown");
  const list = page.getByRole("listbox");
  await expect(list).toBeVisible();
  const box = await list.boundingBox();
  const viewport = page.viewportSize()!;
  expect(box!.height).toBeLessThanOrEqual(320.5);
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
  await page.keyboard.press("End");
  await expect(
    page.getByRole("option", { name: "Отменён", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(list).not.toBeVisible();
  await expect(select).toBeFocused();
  await expect(select).toContainText("Все статусы");
  await select.click();
  await page.getByRole("option", { name: "Завершён", exact: true }).click();
  await expect(page.getByRole("link", { name: /Тестовое поле/ })).toBeVisible();
  expect(await page.locator("main select").count()).toBe(0);
});

test("календарь выбирает дату клавиатурой и не принимает 31 февраля", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  const input = page.getByRole("textbox", {
    name: "Начало периода",
    exact: true,
  });
  await input.fill("2024-06-01");
  const opener = page.getByRole("button", {
    name: "Календарь: Начало периода",
    exact: true,
  });
  await opener.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(input).toHaveValue("2024-06-02");
  await expect(opener).toBeFocused();
  await input.fill("2024-02-31");
  await expect(input).toHaveAttribute("aria-invalid", "true");
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/analyses"))
      requests.push(request.url());
  });
  await page
    .getByRole("button", { name: /Запустить спутниковый анализ/ })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Допустимый период",
  );
  expect(requests).toEqual([]);
  await input.fill("2024-xx");
  await page
    .getByRole("button", { name: "Календарь: Конец периода", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("календарь внутри редактора закрывается раньше родительского диалога", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByRole("button", { name: "Редактировать поле" }).click();
  await page
    .getByRole("button", { name: "Добавить сезон", exact: true })
    .click();
  const calendar = page.getByRole("button", {
    name: "Календарь: Начало",
    exact: true,
  });
  await calendar.click();
  await expect(page.getByRole("dialog")).toHaveCount(2);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(calendar).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("ошибка удаления сохраняет подтверждение и допускает отмену", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/v1/polygons/${polygon.id}`, (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({
          status: 409,
          json: {
            error: {
              code: "version_conflict",
              message: "Версия поля изменилась",
            },
          },
        })
      : route.fallback(),
  );
  await page.goto(`/app/polygons/${polygon.id}`);
  const trigger = page.getByRole("button", {
    name: "Удалить поле",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Отмена", exact: true }),
  ).toBeFocused();
  await dialog
    .getByRole("button", { name: "Удалить поле", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Версия поля изменилась",
  );
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "Тестовое поле", exact: true }),
  ).toBeVisible();
});

test("Colonnade переключает единственную панель и её ссылку", async ({
  page,
}) => {
  await page.goto("/");
  const tabs = page.getByRole("tablist", { name: "Возможности", exact: true });
  await tabs.getByRole("tab", { name: "Территория", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(
    tabs.getByRole("tab", { name: "Контекст", exact: true }),
  ).toBeFocused();
  await expect(page.getByRole("tabpanel")).toHaveCount(1);
  await expect(page.getByRole("tabpanel").getByRole("link")).toHaveAttribute(
    "href",
    "/app/data-quality",
  );
  for (let i = 0; i < 9; i++) await page.keyboard.press("ArrowRight");
  await expect(
    tabs.getByRole("tab", { name: "Территория", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel").getByRole("heading")).toHaveText(
    "Начните с вашего поля",
  );
  await expect(page.locator("[data-terrain]")).not.toHaveAttribute(
    "data-ready",
    "true",
  );
  const poster = page.getByAltText(
    "Иллюстрация объёмного рельефа с линиями высоты",
  );
  await poster.scrollIntoViewIfNeeded();
  await expect(poster).toBeVisible();
  await expect
    .poll(() =>
      poster.evaluate((img) => (img as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
});

test("меню и первый экран помещаются в 320 пикселей", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/");
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toBeVisible();
  const lines = await heading.evaluate(
    (el) =>
      el.getBoundingClientRect().height /
      parseFloat(getComputedStyle(el).lineHeight),
  );
  expect(lines).toBeLessThan(2.1);
  const opener = page.getByRole("button", {
    name: "Открыть меню",
    exact: true,
  });
  await opener.click();
  await page
    .getByRole("navigation", { name: "Меню проекта" })
    .getByRole("link", { name: "Методология", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page).toHaveURL(/#method$/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("рельеф поддерживает вращение, масштаб, метки и потерю WebGL", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Исследовать в 3D", exact: true })
    .click();
  const canvas = page.locator("[data-terrain]");
  await expect(canvas).toHaveAttribute("data-ready", "true");
  const marker = page.getByRole("button", {
    name: "Метка: Гребень склона",
    exact: true,
  });
  await expect(marker).toBeVisible();
  const transform = () => marker.evaluate((el) => el.style.transform);
  const initial = await transform();
  await page
    .getByRole("button", { name: "Приблизить рельеф", exact: true })
    .click();
  await expect.poll(transform).not.toBe(initial);
  const zoomed = await transform();
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(transform).not.toBe(zoomed);
  await page.keyboard.press("Home");
  await expect.poll(transform).toBe(initial);
  await marker.focus();
  await expect(page.getByRole("tooltip")).toContainText("Гребень склона");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).not.toBeVisible();
  await canvas.evaluate((el) => {
    const c = el as HTMLCanvasElement;
    const gl = c.getContext("webgl2") || c.getContext("webgl");
    if (!gl) throw Error("No live WebGL context");
    gl.getExtension("WEBGL_lose_context")!.loseContext();
  });
  await expect(canvas).toHaveAttribute("data-ready", "false");
  await expect(marker).not.toBeVisible();
  await expect(
    page.getByAltText("Иллюстрация объёмного рельефа с линиями высоты"),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("галерея форматов переключается кнопками, клавиатурой и перетаскиванием", async ({
  page,
}) => {
  await page.goto("/");
  const stage = page.locator("[data-output-stage]");
  await stage.scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: "Следующий формат", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Показать GeoJSON", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await stage.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("button", { name: "Показать JSON", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Показать CSV", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Показать CSV", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const box = (await stage.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6 - 120, box.y + box.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
  await expect(
    page.getByRole("button", { name: "Показать CSV", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  expect(await stage.locator("[data-front=true]").count()).toBe(1);
  await expect(
    page.getByRole("link", { name: "К исследованиям", exact: true }),
  ).toHaveAttribute("href", "/app/polygons");
});

test("боковая навигация раскрывается и сохраняет доступ к разделам", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Рабочая карта", exact: true }),
  ).toBeVisible();
  if (page.viewportSize()!.width < 768) {
    const trigger = page.getByRole("button", {
      name: "Открыть навигацию",
      exact: true,
    });
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(result.violations).toEqual([]);
    await dialog.getByRole("link", { name: "Мои поля", exact: true }).click();
    await expect(dialog).not.toBeVisible();
  } else {
    const rail = page.locator("[data-sidebar]");
    await expect(rail).toHaveAttribute("data-open", "false");
    await rail.getByRole("link", { name: "Карта", exact: true }).focus();
    await expect(rail).toHaveAttribute("data-open", "true");
    await page
      .getByRole("button", { name: "Закрепить навигацию", exact: true })
      .click();
    await page.locator("main h1").click();
    await expect(rail).toHaveAttribute("data-open", "true");
    const mapWidth = await page
      .locator("[data-map-canvas]")
      .evaluate((e) => e.clientWidth);
    expect(mapWidth).toBeGreaterThan(500);
    await rail.getByRole("link", { name: "Мои поля", exact: true }).click();
  }
  await expect(page).toHaveURL(/\/app\/polygons$/);
  await expect(
    page.getByRole("heading", { name: "Мои поля", exact: true }),
  ).toBeVisible();
});
