import type { Point, Anomaly } from "./api";
export const chartBase = {
  backgroundColor: "transparent",
  textStyle: {
    color: "#a6a69a",
    fontFamily: "Golos Text Variable, sans-serif",
  },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#25271e",
    borderColor: "#5d6054",
    textStyle: { color: "#f4f3e8" },
  },
  legend: { textStyle: { color: "#a6a69a" }, top: 0 },
  grid: { left: 48, right: 30, top: 65, bottom: 65 },
  dataZoom: [
    { type: "inside" },
    {
      type: "slider",
      height: 18,
      bottom: 15,
      borderColor: "#404139",
      textStyle: { color: "#a6a69a" },
    },
  ],
  aria: {
    enabled: true,
    label: {
      description:
        "Временной ряд. Наблюдения и оценки различаются, пропуски сохранены. Точные значения доступны в таблице ниже.",
    },
  },
  yAxis: {
    type: "value",
    splitLine: { lineStyle: { color: "#35382c" } },
    axisLabel: { color: "#a6a69a" },
  },
  xAxis: {
    type: "category",
    boundaryGap: false,
    axisLabel: { color: "#a6a69a" },
    axisLine: { lineStyle: { color: "#404139" } },
  },
};
export function ndviOption(
  points: Point[],
  anomalies: Anomaly[],
  range?: [string, string],
) {
  const dates = points.map((p) => p.date);
  const values = (f: (p: Point) => number | null) => points.map((p) => f(p));
  return {
    ...chartBase,
    dataZoom: [
      { type: "inside", startValue: range?.[0], endValue: range?.[1] },
      {
        type: "slider",
        height: 18,
        bottom: 15,
        startValue: range?.[0],
        endValue: range?.[1],
      },
    ],
    xAxis: { ...chartBase.xAxis, data: dates },
    yAxis: { ...chartBase.yAxis, name: "NDVI", scale: true },
    series: [
      {
        name: "Восстановленный NDVI",
        type: "line",
        data: values((p) => p.reconstructed),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: "#d5e78b", width: 2, type: "dashed" },
        itemStyle: { color: "#d5e78b" },
        markArea: {
          silent: true,
          data: anomalies.map((a) => [
            {
              xAxis: a.start_date,
              itemStyle: {
                color: a.severity === "critical" ? "#fb718523" : "#fbbf2419",
              },
            },
            { xAxis: a.end_date },
          ]),
        },
      },
      {
        name: "Наблюдения после QA",
        type: "scatter",
        data: values((p) => p.clean_primary),
        symbolSize: 6,
        itemStyle: { color: "#d5e78b" },
      },
      {
        name: "Исходный NDVI",
        type: "scatter",
        data: values((p) => p.observed_primary),
        symbolSize: 4,
        itemStyle: { color: "#deddd0" },
      },
      {
        name: "Сезонная норма",
        type: "line",
        data: values((p) => p.climatology_mean),
        showSymbol: false,
        lineStyle: { color: "#a6a69a", type: "dotted" },
        itemStyle: { color: "#a6a69a" },
      },
      {
        name: "Нижняя граница нормы (±σ)",
        type: "line",
        data: values((p) =>
          p.climatology_mean != null && p.climatology_std != null
            ? p.climatology_mean - p.climatology_std
            : null,
        ),
        showSymbol: false,
        lineStyle: { color: "#73849c", width: 1, type: "dotted" },
      },
      {
        name: "Верхняя граница нормы (±σ)",
        type: "line",
        data: values((p) =>
          p.climatology_mean != null && p.climatology_std != null
            ? p.climatology_mean + p.climatology_std
            : null,
        ),
        showSymbol: false,
        lineStyle: { color: "#73849c", width: 1, type: "dotted" },
      },
      {
        name: "Нижняя граница прогноза",
        type: "line",
        data: values((p) => p.prediction_interval.lower),
        showSymbol: false,
        lineStyle: { color: "#7faaff", width: 1 },
      },
      {
        name: "Верхняя граница прогноза",
        type: "line",
        data: values((p) => p.prediction_interval.upper),
        showSymbol: false,
        lineStyle: { color: "#7faaff", width: 1 },
      },
      {
        name: "Основание интервала",
        type: "line",
        stack: "prediction-band",
        stackStrategy: "all",
        data: values((p) =>
          p.prediction_interval.lower != null &&
          p.prediction_interval.upper != null
            ? p.prediction_interval.lower
            : null,
        ),
        showSymbol: false,
        connectNulls: false,
        silent: true,
        lineStyle: { opacity: 0 },
        tooltip: { show: false },
      },
      {
        name: "Интервал прогноза",
        type: "line",
        stack: "prediction-band",
        stackStrategy: "all",
        data: values((p) =>
          p.prediction_interval.lower != null &&
          p.prediction_interval.upper != null
            ? p.prediction_interval.upper - p.prediction_interval.lower
            : null,
        ),
        showSymbol: false,
        connectNulls: false,
        silent: true,
        lineStyle: { opacity: 0 },
        areaStyle: { color: "#7faaff", opacity: 0.15 },
        itemStyle: { color: "#7faaff" },
        tooltip: { show: false },
      },
    ],
    legend: {
      ...chartBase.legend,
      data: [
        "Восстановленный NDVI",
        "Наблюдения после QA",
        "Исходный NDVI",
        "Сезонная норма",
        "Нижняя граница нормы (±σ)",
        "Верхняя граница нормы (±σ)",
        "Нижняя граница прогноза",
        "Верхняя граница прогноза",
        "Интервал прогноза",
      ],
      selected: {
        "Исходный NDVI": false,
        "Нижняя граница нормы (±σ)": false,
        "Верхняя граница нормы (±σ)": false,
        "Нижняя граница прогноза": false,
        "Верхняя граница прогноза": false,
      },
      type: "scroll",
    },
  };
}
