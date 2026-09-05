import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, polygon } from "./fixtures";
test("основные экраны проходят проверку WCAG AA", async ({ page }) => {
  await mockApi(page);
  for (const path of [
    "/",
    "/app/polygons",
    `/app/analyses/${polygon.latest_run_id}`,
    "/app/models",
    "/app/compare",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      path === "/"
        ? "Состояние полей"
        : path === "/app/polygons"
          ? "Мои поля"
          : path.includes("/analyses/")
            ? "Тестовое поле"
            : path === "/app/models"
              ? "Модели"
              : "Сравнение",
    );
    if (path.includes("/analyses/"))
      await page.getByRole("tab", { name: "Динамика NDVI" }).waitFor();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations,
      JSON.stringify(
        result.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            summary: n.failureSummary,
          })),
        })),
        null,
        2,
      ),
    ).toEqual([]);
  }
});
test("лендинг работает без JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(baseURL!);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Состояние полей",
  );
  await expect(
    page.getByRole("link", { name: "Исследовать поле" }).first(),
  ).toHaveAttribute("href", "/app");
  await context.close();
});
test("выход доступен и отменяем на любом экране", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/polygons");
  await page
    .getByRole("button", { name: "Завершить сессию", exact: true })
    .filter({ visible: true })
    .click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(page.getByRole("alertdialog")).not.toBeVisible();
  await expect(page.getByRole("link", { name: /Тестовое поле/ })).toBeVisible();
});
