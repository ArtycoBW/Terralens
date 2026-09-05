import { describe, it, expect } from "vitest";
import { parseGeometry, bounds, validPeriod } from "../../src/lib/geometry";
const polygon = {
  type: "Polygon",
  coordinates: [
    [
      [13, 52],
      [13.01, 52],
      [13.01, 52.01],
      [13, 52],
    ],
  ],
};
describe("Контур поля", () => {
  it("принимает GeoJSON Feature и сохраняет lon/lat", () => {
    const g = parseGeometry(
      JSON.stringify({ type: "Feature", geometry: polygon }),
    );
    expect(bounds(g)).toEqual([13, 52, 13.01, 52.01]);
  });
  it("отклоняет незамкнутый контур", () => {
    expect(() =>
      parseGeometry(
        JSON.stringify({
          type: "Polygon",
          coordinates: [
            [
              [13, 52],
              [14, 52],
              [14, 53],
              [13, 53],
            ],
          ],
        }),
      ),
    ).toThrow();
  });
  it("отклоняет широту за пределами WGS84", () => {
    expect(() =>
      parseGeometry(
        JSON.stringify({
          type: "Polygon",
          coordinates: [
            [
              [13, 152],
              [14, 52],
              [14, 53],
              [13, 152],
            ],
          ],
        }),
      ),
    ).toThrow();
  });
  it("соблюдает серверный лимит вершин", () =>
    expect(() => parseGeometry(JSON.stringify(polygon), 3)).toThrow(
      /Максимум/,
    ));
  it("отклоняет пустую геометрию", () =>
    expect(() =>
      parseGeometry('{"type":"Polygon","coordinates":[]}'),
    ).toThrow());
});
describe("Период анализа", () => {
  it("считает високосный год включительно", () =>
    expect(
      validPeriod("2024-01-01", "2024-12-31", "2017-01-01", "2025-01-01", 366),
    ).toBe(true));
  it.each([
    ["2024-06-02", "2024-06-01"],
    ["2016-01-01", "2016-01-02"],
    ["2026-01-01", "2026-02-01"],
    ["2023-01-01", "2024-12-31"],
    ["bad", "bad"],
  ])("отклоняет недопустимый период %s %s", (a, b) =>
    expect(validPeriod(a, b, "2017-01-01", "2025-01-01", 366)).toBe(false),
  );
});
