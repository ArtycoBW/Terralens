"use client";
export function readableMessage(value: unknown) {
  if (typeof value === "string") return value;
  if (
    value &&
    typeof value === "object" &&
    "message" in value &&
    typeof value.message === "string"
  )
    return value.message;
  return JSON.stringify(value);
}
export function Explanation({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return null;
  const data = value as Record<string, unknown>;
  return (
    <div className="explanation">
      <p className="text-sm leading-relaxed mt-3">
        {typeof data.summary === "string" ? data.summary : ""}
      </p>
      {[
        ["observations", "Что подтверждает сигнал"],
        ["possible_causes", "Возможные объяснения"],
        ["recommended_checks", "Что проверить"],
        ["limitations", "Ограничения"],
      ].map(
        ([key, title]) =>
          Array.isArray(data[key]) && (
            <div className="mt-3" key={key}>
              <h4 className="text-xs leading-relaxed uppercase text-primary">
                {title}
              </h4>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
                {(data[key] as unknown[])
                  .filter((v) => typeof v === "string")
                  .map((v, i) => (
                    <li key={i}>{String(v)}</li>
                  ))}
              </ul>
            </div>
          ),
      )}
    </div>
  );
}
