import { test, expect } from "@playwright/test";
import { mockApi, polygon, run } from "./fixtures";
test("рисование контура мышью передаёт валидный GeoJSON в форму", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/app");
  await page
    .getByRole("button", { name: "Нарисовать контур", exact: true })
    .click();
  const box = await page.locator(".map-canvas").boundingBox();
  if (!box) throw new Error("Карта отсутствует");
  const corners = [
    [0.3, 0.45],
    [0.65, 0.45],
    [0.65, 0.65],
    [0.3, 0.65],
    [0.3, 0.45],
  ];
  for (const [x, y] of corners)
    await page.mouse.click(box.x + box.width * x, box.y + box.height * y, {
      delay: 100,
    });
  if (isMobile)
    await expect(
      page.getByRole("button", { name: "Показать карту" }),
    ).toBeVisible();
  const geometry = JSON.parse(
    await page.getByRole("textbox", { name: "Геометрия GeoJSON" }).inputValue(),
  );
  expect(geometry.type).toBe("Polygon");
  expect(geometry.coordinates[0]).toHaveLength(5);
  expect(geometry.coordinates[0][0]).toEqual(geometry.coordinates[0].at(-1));
});
test("недоступный WebGL оставляет рабочую альтернативу карты", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type.includes("webgl")) return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });
  await page.goto("/app");
  await expect(
    page.getByText("WebGL недоступен.", { exact: false }),
  ).toBeVisible();
  if (isMobile)
    await page.getByRole("button", { name: "Показать панель" }).click();
  await page.getByText("Контур GeoJSON / ввод без карты").click();
  await expect(
    page.getByRole("textbox", { name: "Геометрия GeoJSON" }),
  ).toBeVisible();
});
test("лендинг доступен без WebGL и без движения", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Состояние полей",
  );
  await expect(
    page.getByRole("link", { name: "Исследовать поле" }),
  ).toBeVisible();
  await expect(page.locator(".planet-canvas")).not.toHaveClass(/ready/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
test("пустое пространство и доступный ввод GeoJSON", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/app");
  if (isMobile)
    await page.getByRole("button", { name: "Показать панель" }).click();
  await expect(
    page.getByText("Пока нет полей.", { exact: false }),
  ).toBeVisible();
  await page.getByText("Контур GeoJSON / ввод без карты").click();
  await expect(
    page.getByRole("textbox", { name: "Геометрия GeoJSON" }),
  ).toBeVisible();
});
test("ошибка сети не превращается в пустые данные", async ({ page }) => {
  await mockApi(page, { error: 503 });
  await page.goto("/app/polygons");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Источник временно недоступен",
  );
  await expect(
    page.getByRole("button", { name: "Повторить", exact: true }),
  ).toBeVisible();
});
test("фильтр списка полей", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/polygons");
  await expect(page.getByRole("link", { name: /Тестовое поле/ })).toBeVisible();
  await page.getByPlaceholder("Название поля").fill("не существует");
  await expect(page.getByText("Нет полей по выбранным фильтрам")).toBeVisible();
});
test("название поля и сезоны редактируются в доступном диалоге", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByRole("button", { name: "Редактировать поле" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Название поля", exact: true })
    .fill("Новое название");
  await page
    .getByRole("button", { name: "Добавить сезон", exact: true })
    .click();
  await expect(page.getByLabel("Начало", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
test("не допускает анализ только погоды", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByLabel("Sentinel-2 · Earth Search").uncheck();
  await page.getByLabel("Landsat 8/9 · Planetary Computer").uncheck();
  await page
    .getByRole("button", { name: /Запустить спутниковый анализ/ })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Выберите спутниковый источник",
  );
});
test("отклоняет перевёрнутый период", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByLabel("Начало периода").fill("2024-07-01");
  await page.getByLabel("Конец периода").fill("2024-06-01");
  await page
    .getByRole("button", { name: /Запустить спутниковый анализ/ })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Допустимый период",
  );
});
test("показывает прогресс и отмену задачи", async ({ page }) => {
  await mockApi(page, { state: "running" });
  await page.goto(`/app/analyses/${run.id}`);
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", "0.3");
  await page.getByRole("button", { name: "Отменить задачу" }).click();
  await expect(
    page.getByText("Отмена запрошена", { exact: false }),
  ).toBeVisible();
});
test("показывает повтор при отказе источника", async ({ page }) => {
  await mockApi(page, { state: "failed" });
  await page.goto(`/app/analyses/${run.id}`);
  await expect(
    page.getByRole("button", { name: "Повторить задачу" }),
  ).toBeVisible();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Сбой источника",
  );
});
test("дневная таблица отличает ноль от отсутствия", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/analyses/${run.id}`);
  await expect(
    page.getByRole("cell", { name: "Наблюдение", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Недоступно", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Выбрать дату (клавиатура)").fill("2024-06-02");
  await expect(page.getByText("Все значения за 2024-06-02")).toBeVisible();
});
test("нет данных не обозначается нормальным состоянием", async ({ page }) => {
  await mockApi(page, { state: "no_data" });
  await page.goto(`/app/analyses/${run.id}`);
  await page.getByRole("tab", { name: /Аномалии/ }).click();
  await expect(
    page.getByText("Недостаточно данных для надёжного поиска аномалий"),
  ).toBeVisible();
});
test("критичность и уверенность различаются", async ({ page }) => {
  await mockApi(page, { anomaly: true });
  await page.goto(`/app/analyses/${run.id}`);
  await page.getByRole("tab", { name: /Аномалии/ }).click();
  await expect(
    page.getByRole("article").getByText("Критично", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Уверенность: Низкая")).toBeVisible();
  await page
    .getByRole("button", { name: "Показать период на графике" })
    .click();
  await expect(
    page.getByRole("tab", { name: "Динамика NDVI" }),
  ).toHaveAttribute("aria-selected", "true");
});
test("сравнение восстанавливается из URL", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/compare?runs=${run.id}&alignment=calendar`);
  await expect(page.getByRole("checkbox")).toBeChecked();
  await expect(page.getByRole("columnheader", { name: "Ряд 1" })).toBeVisible();
  await page.getByLabel("Совмещение рядов").selectOption("day_of_year");
  await expect(page).toHaveURL(/alignment=day_of_year/);
});
test("метрики не подменяют официальный score", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/models");
  await expect(
    page.getByText("Официальный результат организаторов пока не опубликован.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "0,08", exact: true }),
  ).toBeVisible();
});
test("benchmark остаётся анонимным", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/benchmark");
  await expect(
    page.getByText("AOI анонимизированы и не показаны на карте.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByLabel("Анонимный AOI")).toBeVisible();
});
test("основные экраны не переполняют мобильную ширину", async ({ page }) => {
  await mockApi(page);
  for (const path of [
    "/app/polygons",
    `/app/polygons/${polygon.id}`,
    `/app/analyses/${run.id}`,
    "/app/compare",
    "/app/data-quality",
    "/app/models",
    "/app/benchmark",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      path,
    ).toBe(true);
  }
});
test("конфликт версий не теряет введённое название", async ({ page }) => {
  await mockApi(page);
  await page.route(`**/api/v1/polygons/${polygon.id}`, async (route) =>
    route.request().method() === "PATCH"
      ? route.fulfill({
          status: 409,
          json: {
            error: {
              code: "version_conflict",
              message: "Версия контура изменилась",
              request_id: "conflict",
            },
          },
        })
      : route.fallback(),
  );
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByRole("button", { name: "Редактировать поле" }).click();
  await page
    .getByRole("textbox", { name: "Название поля", exact: true })
    .fill("Мой черновик");
  await page.getByRole("button", { name: "Сохранить изменения" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "Версия контура изменилась",
  );
  await expect(
    page.getByRole("textbox", { name: "Название поля", exact: true }),
  ).toHaveValue("Мой черновик");
});
test("черновик контура восстанавливается после перезагрузки", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/app");
  if (isMobile)
    await page.getByRole("button", { name: "Показать панель" }).click();
  await page
    .getByRole("textbox", { name: "Название", exact: true })
    .fill("Черновик поля");
  await page.getByText("Контур GeoJSON / ввод без карты").click();
  await page
    .getByRole("textbox", { name: "Геометрия GeoJSON" })
    .fill(JSON.stringify(polygon.geometry));
  await page.reload();
  if (isMobile)
    await page.getByRole("button", { name: "Показать панель" }).click();
  await expect(
    page.getByRole("textbox", { name: "Название", exact: true }),
  ).toHaveValue("Черновик поля");
  await expect(
    page.getByRole("textbox", { name: "Геометрия GeoJSON" }),
  ).toHaveValue(JSON.stringify(polygon.geometry));
});
test("редактор карты доступен в карточке поля", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/polygons/${polygon.id}`);
  await page.getByRole("button", { name: "Редактировать поле" }).click();
  await page
    .getByRole("button", { name: "Редактировать контур на карте" })
    .click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Изменить вершины" }),
  ).toBeEnabled();
});
test("истёкшая сессия скрывает приватный интерфейс", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/polygons");
  await expect(page.getByRole("link", { name: /Тестовое поле/ })).toBeVisible();
  await page.route(`**/api/v1/polygons/${polygon.id}`, (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: "session_expired", message: "Сессия истекла" } },
    }),
  );
  await page.getByRole("link", { name: /Тестовое поле/ }).click();
  await expect(
    page.getByRole("heading", { name: "Сессия истекла" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Основная навигация" }),
  ).not.toBeVisible();
});
