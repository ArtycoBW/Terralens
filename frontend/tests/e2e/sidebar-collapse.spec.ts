import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.use({ contextOptions: { reducedMotion: "no-preference" } });

test("сворачивание sidebar не оставляет подписи поверх страницы", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "На телефоне используется отдельная панель Sheet");
  await mockApi(page);
  await page.goto("/app/compare");
  const rail = page.locator("[data-sidebar]");
  const heading = page.getByRole("heading", {
    name: "Сравнение полей и сезонов",
  });
  await heading.hover();
  await expect(rail).toHaveAttribute("data-open", "false");
  for (let cycle = 0; cycle < 2; cycle++) {
    for (const name of ["Мои поля", "Сравнение", "Качество данных", "Модели"]) {
      await rail.getByRole("link", { name, exact: true }).hover();
      await expect(rail).toHaveAttribute("data-open", "true");
      // Exercise the delayed tooltip callbacks, including while labels are expanded.
      await page.waitForTimeout(300);
    }
    await heading.hover();
    await expect(rail).toHaveAttribute("data-open", "false");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await expect(page.locator('[data-slot="tooltip-content"]')).toHaveCount(0);
  }
  await rail.getByRole("link", { name: "Мои поля", exact: true }).focus();
  await expect(rail).toHaveAttribute("data-open", "true");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/polygons$/);
  await page.getByRole("heading", { name: "Мои поля", exact: true }).click();
  await expect(rail).toHaveAttribute("data-open", "false");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});
