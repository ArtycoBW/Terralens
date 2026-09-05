export const HERO_CHAPTERS = [
  {
    label: "Территория",
    title: "Каждое поле — в своём контуре.",
    body: "Найдите участок на карте, нарисуйте границу или загрузите GeoJSON. История наблюдений будет собрана для выбранной территории.",
    detail: "Карта · OpenStreetMap · GeoJSON",
    side: "right",
    enter: [0.16, 0.23],
    exit: [0.37, 0.45],
  },
  {
    label: "Наблюдения",
    title: "Сезон становится видимым.",
    body: "Проследите, как менялась растительность. Спутниковые наблюдения и восстановленные значения NDVI показаны отдельно — вместе с пробелами в данных.",
    detail: "Sentinel-2 · Landsat · NDVI",
    side: "left",
    enter: [0.46, 0.53],
    exit: [0.66, 0.74],
  },
  {
    label: "Контекст",
    title: "У каждого изменения есть контекст.",
    body: "Сопоставьте динамику с погодой и качеством снимков. Проверьте источники, прежде чем делать вывод о состоянии поля.",
    detail: "Погода · Качество данных · Источники",
    side: "right",
    enter: [0.76, 0.83],
    exit: [1.1, 1.2],
  },
] as const;

export type HeroSceneState = { progress: number; active: boolean };

export function ramp(value: number, from: number, to: number) {
  const t = Math.max(0, Math.min(1, (value - from) / (to - from)));
  return t * t * (3 - 2 * t);
}

// Остановки дают время прочитать текст; между ними Земля пересекает экран.
const FRAMES = [
  { at: 0, side: 0, focus: 0, turn: 0 },
  { at: 0.06, side: 0, focus: 0, turn: 0 },
  { at: 0.23, side: -1, focus: 1, turn: 0.85 },
  { at: 0.36, side: -1, focus: 1, turn: 0.85 },
  { at: 0.53, side: 1, focus: 1, turn: 2.8 },
  { at: 0.65, side: 1, focus: 1, turn: 2.8 },
  { at: 0.83, side: -1, focus: 1, turn: 4.8 },
  { at: 1, side: -1, focus: 1, turn: 4.8 },
];

export function heroPlanetFrame(
  progress: number,
  width: number,
  height: number,
) {
  const end = FRAMES.findIndex((frame) => frame.at >= progress);
  const b = FRAMES[end < 0 ? FRAMES.length - 1 : end];
  const a = FRAMES[Math.max(0, end < 0 ? FRAMES.length - 2 : end - 1)];
  const t = a === b ? 0 : ramp(progress, a.at, b.at);
  const mix = (start: number, finish: number) => start + (finish - start) * t;
  const focus = mix(a.focus, b.focus);
  const side = mix(a.side, b.side);
  // Размеры видимой плоскости при камере Ascend: FOV 40°, z = 8.
  const viewHeight = 16 * Math.tan(Math.PI / 9);
  const viewWidth = (viewHeight * width) / Math.max(1, height);
  const narrow = width < 768;
  const radius = Math.min(
    viewWidth * (narrow ? 0.31 : 0.18),
    viewHeight * (narrow ? 0.17 : 0.29),
  );
  return {
    x: side * viewWidth * (narrow ? 0.06 : 0.25),
    y: -4.5 + ((narrow ? viewHeight * 0.19 : -0.1) + 4.5) * focus,
    scale: 2.15 + (radius / 1.95 - 2.15) * focus,
    turn: mix(a.turn, b.turn),
  };
}
