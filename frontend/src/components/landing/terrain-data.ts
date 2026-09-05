export const TERRAIN_MARKERS = [
  {
    id: "ridge",
    x: -1.7,
    z: -1,
    title: "Гребень склона",
    text: "Открытые склоны могут быстрее терять влагу. Погодный ряд помогает проверить этот контекст.",
  },
  {
    id: "valley",
    x: 0.8,
    z: 1.2,
    title: "Понижение рельефа",
    text: "В понижениях может накапливаться вода. Изменения растительности стоит сопоставить с осадками.",
  },
  {
    id: "field",
    x: 2.5,
    z: -1.6,
    title: "Открытый участок",
    text: "Однородный контур удобен для сравнения наблюдений за разные периоды сезона.",
  },
] as const;
export type TerrainController = {
  dispose: () => void;
  reset: () => void;
  zoom: (factor: number) => void;
  rotate: (horizontal: number, vertical?: number) => void;
};
