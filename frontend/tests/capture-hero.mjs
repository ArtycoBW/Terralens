import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const directory = "../artifacts/redesign/hero-story";
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const evidence = { errors: [], frames: [] };
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "no-preference",
  });
  page.on("pageerror", (error) => evidence.errors.push(error.message));
  await page.goto("http://localhost:3001/");
  await page.locator('[data-planet][data-hydrated="true"]').waitFor();
  await page.mouse.move(400, 150);
  await page
    .locator('[data-planet][data-ready="true"]')
    .waitFor({ timeout: 45000 });
  for (const [width, height] of [
    [1440, 1000],
    [1024, 900],
    [768, 1024],
    [390, 844],
    [390, 700],
  ]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(500);
    for (const progress of [0, 0.3, 0.59, 0.92]) {
      await page
        .locator("[data-hero]")
        .evaluate(
          (element, p) =>
            window.scrollTo(
              0,
              element.offsetTop +
                (element.offsetHeight -
                  element.querySelector("[data-hero-stage]").offsetHeight) *
                  p,
            ),
          progress,
        );
      await page.waitForTimeout(500);
      await page.screenshot({
        path: `${directory}/${width}-${height}-${progress}.png`,
      });
      evidence.frames.push(
        await page.evaluate(() => ({
          width: innerWidth,
          height: innerHeight,
          progress: document.querySelector("[data-hero]").dataset.progress,
          overflow: document.documentElement.scrollWidth > innerWidth,
          panels: [...document.querySelectorAll("[data-story-panel]")]
            .filter((el) => getComputedStyle(el).visibility !== "hidden")
            .map((el) => ({
              label: el.dataset.storyPanel,
              box: el.getBoundingClientRect().toJSON(),
              content: el.firstElementChild.getBoundingClientRect().toJSON(),
            })),
        })),
      );
    }
  }
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(evidence, null, 2),
  );
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await browser.close();
}
