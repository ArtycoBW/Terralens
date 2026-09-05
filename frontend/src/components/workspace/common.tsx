"use client";
import { ApiError, label } from "@/lib/api";
import { Button } from "@/components/ui/button";
export function ErrorNotice({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <p>{error.message}</p>
      {error instanceof ApiError && error.requestId && (
        <small>Код обращения: {error.requestId}</small>
      )}
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <span className="pill" data-state={value}>
      {label[value] || value}
    </span>
  );
}
export function JsonDetails({
  value,
  title = "Подробности",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <details className="json-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
