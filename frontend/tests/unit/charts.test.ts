import { describe, it, expect } from "vitest";
import { ndviOption } from "../../src/lib/charts";
import type { Point } from "../../src/lib/api";
const point = (date: string, value: number | null): Point => ({
  date,
  reconstructed: value,
  clean_primary: null,
  observed_primary: null,
  origin: value == null ? "unavailable" : "interpolated",
  source_sensor: null,
  sensors: { sentinel2: null, landsat: null, modis: null },
  climatology_mean: null,
  climatology_std: null,
  zscore: null,
  prediction_interval: {
    lower: null,
    upper: null,
    level: null,
    method: "not_calibrated",
  },
  weather: { temperature_c: null, precipitation_mm: null, provider: null },
  support_count: 0,
  gap_days: 10,
  quality_flags: [],
  reference_years: 0,
});
describe("Scientific chart", () => {
  it("строит полосу интервала с отрицательной границей и сохраняет пропуски", () => {
    const p = point("2024-06-01", 0);
    p.prediction_interval = {
      lower: -0.2,
      upper: 0.3,
      level: 0.9,
      method: "test",
    };
    const series = ndviOption([p, point("2024-06-02", null)], []).series;
    expect(series.find((s) => s.name === "Основание интервала")?.data).toEqual([
      -0.2,
      null,
    ]);
    expect(series.find((s) => s.name === "Интервал прогноза")?.data).toEqual([
      0.5,
      null,
    ]);
    expect(
      series.find((s) => s.name === "Интервал прогноза")?.stackStrategy,
    ).toBe("all");
  });
  it("сохраняет нулевой NDVI и пропуск раздельно", () => {
    const option = ndviOption(
      [point("2024-06-01", 0), point("2024-06-02", null)],
      [],
    );
    expect(option.series[0].data).toEqual([0, null]);
    expect(option.series[0].connectNulls).toBe(false);
  });
  it("не изобретает интервалы и сезонную норму", () => {
    const option = ndviOption([point("2024-06-01", 0.4)], []);
    expect(option.series[3].data).toEqual([null]);
    expect(option.series[6].data).toEqual([null]);
  });
});
