import { isIsoDate } from "./dates";
import { z } from "zod";
const position = z.tuple([
  z.number().min(-180).max(180),
  z.number().min(-90).max(90),
]);
const ring = z
  .array(position)
  .min(4)
  .refine(
    (p) => p[0][0] === p[p.length - 1][0] && p[0][1] === p[p.length - 1][1],
    "Контур должен быть замкнут",
  );
export const geometrySchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("Polygon"), coordinates: z.array(ring).min(1) }),
  z.object({
    type: z.literal("MultiPolygon"),
    coordinates: z.array(z.array(ring).min(1)).min(1),
  }),
]);
export type FieldGeometry = z.infer<typeof geometrySchema>;
export function parseGeometry(text: string, maxVertices = 5000): FieldGeometry {
  const input = JSON.parse(text);
  const result = geometrySchema.parse(
    input.type === "Feature" ? input.geometry : input,
  );
  const points =
    result.type === "Polygon"
      ? result.coordinates.flat()
      : result.coordinates.flat(2);
  if (points.length > maxVertices)
    throw new Error(`Максимум ${maxVertices} вершин`);
  return result;
}
export function bounds(
  geometry: FieldGeometry,
): [number, number, number, number] {
  const p =
    geometry.type === "Polygon"
      ? geometry.coordinates.flat()
      : geometry.coordinates.flat(2);
  return [
    Math.min(...p.map((v) => v[0])),
    Math.min(...p.map((v) => v[1])),
    Math.max(...p.map((v) => v[0])),
    Math.max(...p.map((v) => v[1])),
  ];
}
export function validPeriod(
  from: string,
  to: string,
  minimum: string,
  maximum: string,
  maxDays: number,
) {
  if (!isIsoDate(from) || !isIsoDate(to)) return false;
  const days = (Date.parse(to) - Date.parse(from)) / 86400000 + 1;
  return (
    Number.isFinite(days) &&
    days >= 1 &&
    days <= maxDays &&
    from >= minimum &&
    to <= maximum
  );
}
