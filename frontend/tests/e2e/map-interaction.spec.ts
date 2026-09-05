import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.use({ contextOptions: { reducedMotion: "no-preference" } });

test("первая вершина действительно отображается поверх карты", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/app");
  await page
    .getByRole("button", { name: "Нарисовать контур", exact: true })
    .click();
  const map = await page.locator("[data-map-canvas]").boundingBox();
  if (!map) throw new Error("Карта отсутствует");
  const x = map.x + map.width * 0.4,
    y = map.y + map.height * 0.6;
  if (isMobile) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y, { delay: 60 });
  // Проверяем пиксели canvas: валидный GeoJSON сам по себе не доказывает отрисовку.
  await expect
    .poll(async () => {
      const png = await page.screenshot({
        clip: { x: x - 10, y: y - 10, width: 20, height: 20 },
      });
      return page.evaluate(async (base64) => {
        const img = new Image();
        img.src = `data:image/png;base64,${base64}`;
        await img.decode();
        const canvas = document.createElement("canvas");
        canvas.width = img.width;
        canvas.height = img.height;
        const context = canvas.getContext("2d")!;
        context.drawImage(img, 0, 0);
        const { data } = context.getImageData(
          0,
          0,
          canvas.width,
          canvas.height,
        );
        let count = 0;
        for (let i = 0; i < data.length; i += 4) {
          if (
            data[i] > 220 &&
            data[i + 1] > 230 &&
            data[i + 2] > 90 &&
            data[i + 2] < 140
          )
            count++;
        }
        return count;
      }, png.toString("base64"));
    })
    .toBeGreaterThan(20);
});

test("подсказка не мешает поставить и замкнуть контур мышью или касанием", async ({
  page,
  isMobile,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/app");
  await page
    .getByRole("button", { name: "Нарисовать контур", exact: true })
    .click();
  const map = await page.locator("[data-map-canvas]").boundingBox();
  const hint = await page
    .getByText("Добавляйте вершины кликом.", { exact: false })
    .boundingBox();
  if (!map || !hint) throw new Error("Карта и подсказка должны быть видимы");
  // Начать поверх подсказки: она не должна перехватывать ввод карты.
  const first = [hint.x + hint.width / 2, hint.y + hint.height / 2];
  const points = [
    first,
    [map.x + map.width * 0.8, map.y + map.height * 0.7],
    [map.x + map.width * 0.2, map.y + map.height * 0.7],
    first,
  ];
  for (const [x, y] of points) {
    if (isMobile) await page.touchscreen.tap(x, y);
    else await page.mouse.click(x, y, { delay: 60 });
  }
  await expect(
    page.getByRole("tab", { name: "Создать", exact: true }),
  ).toHaveAttribute("data-state", "active");
  const geometry = JSON.parse(
    await page.getByRole("textbox", { name: "Геометрия GeoJSON" }).inputValue(),
  );
  expect(geometry.type).toBe("Polygon");
  expect(geometry.coordinates[0]).toHaveLength(4);
  expect(geometry.coordinates[0][0]).toEqual(geometry.coordinates[0].at(-1));
});
