import type { Page } from "@playwright/test";
export const polygon = {
  id: "11111111-1111-4111-8111-111111111111",
  workspace_id: "workspace",
  region_id: null,
  name: "Тестовое поле",
  current_version: 1,
  geometry: {
    type: "MultiPolygon",
    coordinates: [
      [
        [
          [13, 52],
          [13.01, 52],
          [13.01, 52.01],
          [13, 52],
        ],
      ],
    ],
  },
  geometry_hash: "test",
  area_ha: 12.5,
  source: "user",
  source_ref: "",
  crop_type: null,
  crop_seasons: [],
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  latest_run_id: "22222222-2222-4222-8222-222222222222",
};
export const run = {
  id: polygon.latest_run_id,
  polygon_id: polygon.id,
  polygon_version: 1,
  mode: "retrospective",
  period: { from: "2024-06-01", to: "2024-06-03" },
  state: "completed",
  job_id: "33333333-3333-4333-8333-333333333333",
  model_version: "test-model",
  config_version: "v1",
  created_at: "2026-09-01T00:00:00Z",
  completed_at: "2026-09-01T00:01:00Z",
  snapshots: [],
  warnings: [],
  summary: {
    observed_days: 1,
    total_days: 3,
    observed_coverage_ratio: 1 / 3,
    reconstructed_days: 1,
    unavailable_days: 1,
    longest_gap_days: 2,
    anomaly_period_count: 0,
    overall_status: "insufficient_data",
    summary_rule: "test",
    latest_estimate: { date: "2024-06-02", value: 0.5, origin: "interpolated" },
  },
  result_version: "test",
};
export const points = [0, 0.5, null].map((value, i) => ({
  date: `2024-06-0${i + 1}`,
  observed_primary: i === 0 ? 0 : null,
  clean_primary: i === 0 ? 0 : null,
  reconstructed: value,
  origin: i === 0 ? "observed" : i === 1 ? "interpolated" : "unavailable",
  source_sensor: i === 0 ? "sentinel2" : null,
  sensors: { sentinel2: i === 0 ? 0 : null, landsat: null, modis: null },
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
  support_count: 1,
  gap_days: 2,
  quality_flags: [],
  reference_years: 0,
}));
export const pageOf = (items: unknown[]) => ({
  items,
  next_cursor: null,
  total: items.length,
});
export async function mockApi(
  page: Page,
  options: {
    state?: string;
    empty?: boolean;
    error?: number;
    anomaly?: boolean;
  } = {},
) {
  let cancelled = false;
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace("/api/v1/", "");
    const method = route.request().method();
    if (path.endsWith("/cancel")) cancelled = true;
    let data: unknown;
    const changed = { ...run, state: options.state || run.state };
    if (path === "session")
      data = {
        workspace_id: "workspace",
        role: "guest",
        expires_at: "2026-09-12T00:00:00Z",
        csrf_token: "test-csrf",
      };
    else if (options.error)
      return route.fulfill({
        status: options.error,
        json: {
          error: {
            code: "provider_unavailable",
            message: "Источник временно недоступен",
            request_id: "test-request",
            retryable: true,
          },
        },
      });
    else if (path === "capabilities")
      data = {
        limits: {
          max_polygons: 20,
          max_vertices: 5000,
          max_polygon_area_ha: 10000,
          max_period_days: 366,
          max_discovery_area_km2: 2500,
        },
        supported_period: { from: "2017-01-01", to: "2026-08-31" },
        active_model: "test-model",
        providers: [],
        feature_flags: { export: true, comparison: true },
        retention: { workspace_days: 7, export_days: 7 },
      };
    else if (path === "polygons")
      data =
        method === "POST" ? polygon : pageOf(options.empty ? [] : [polygon]);
    else if (path === `polygons/${polygon.id}`) data = polygon;
    else if (path.endsWith("/analyses")) data = pageOf([changed]);
    else if (path === `analyses/${run.id}`) data = changed;
    else if (path.endsWith("/series"))
      data = {
        ...pageOf(options.state === "no_data" ? [] : points),
        actual_resolution: "daily",
      };
    else if (path.endsWith("/anomalies"))
      data = pageOf(
        options.anomaly
          ? [
              {
                id: "event",
                run_id: run.id,
                start_date: "2024-06-01",
                end_date: "2024-06-02",
                peak_date: "2024-06-02",
                severity: "critical",
                confidence: "low",
                event_kind: "single_observation_alert",
                min_z: -4,
                integrated_deficit: 0.3,
                observed_evidence_count: 1,
                reconstructed_fraction: 0.5,
                quality_flags: [],
                causes: [],
                explanation: {
                  summary: "Снижение подтверждено одним наблюдением",
                  recommended_checks: ["Проверить историю уборки"],
                },
                review_status: "unreviewed",
              },
            ]
          : [],
      );
    else if (path.endsWith("/quality"))
      data = {
        summary: run.summary,
        exclusions: { clouds: 2 },
        warnings: [],
        model: { id: "test-model" },
        reference: { years: 0 },
        observed_days_definition: "Только пригодные наблюдения после QA",
      };
    else if (path.startsWith("jobs/"))
      data = {
        id: run.job_id,
        kind: "analysis",
        state:
          options.state === "failed"
            ? "failed"
            : method === "POST"
              ? "cancelled"
              : "running",
        stage: "fetching_satellite",
        progress: 0.3,
        attempt: 1,
        created_at: run.created_at,
        started_at: run.created_at,
        finished_at: null,
        cancel_requested: cancelled,
        retryable: options.state === "failed",
        error:
          options.state === "failed" ? { message: "Сбой источника" } : null,
        result: { type: "analysis", id: run.id },
        parent_job_id: null,
      };
    else if (path === "regions") data = pageOf([]);
    else if (path === "comparisons")
      data = {
        alignment: "calendar",
        alignment_rule: "Общая календарная ось",
        axis: points.map((p) => p.date),
        aligned_series: [
          {
            run_id: run.id,
            points: points.map((p) => ({ ...p, alignment_key: p.date })),
          },
        ],
        items: [{ run: changed, series_url: "" }],
        warnings: [],
      };
    else if (path === "models")
      data = pageOf([
        {
          id: "test-model",
          active: true,
          artifact_hash: "hash",
          created_at: run.created_at,
          supported_modes: ["retrospective"],
          metrics: { development: { rmse: 0.08, mae: 0.06, n: 100 } },
        },
      ]);
    else data = {};
    await route.fulfill({ json: data });
  });
}
