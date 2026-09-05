"use client";
import { SelectControl, SelectOption } from "@/components/ui/select-control";

import { Label } from "@/components/ui/label";

import { useRef, useState, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type Schema } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { JobProgress } from "@/components/workspace/job-progress";
import { ErrorNotice } from "@/components/workspace/common";
export function Exports({ runId }: { runId: string }) {
  const [format, setFormat] = useState("csv"),
    [result, setResult] = useState<Schema["ExportAccepted"] | null>(null);
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(`terralens-export:${runId}`);
      if (saved) {
        const value = JSON.parse(saved);
        if (
          typeof value.export_id === "string" &&
          typeof value.job_id === "string"
        )
          queueMicrotask(() => setResult(value));
      }
    } catch {}
  }, [runId]);
  const key = useRef<{ format: string; id: string } | null>(null);
  const start = useMutation({
    mutationFn: () => {
      if (key.current?.format !== format)
        key.current = { format, id: crypto.randomUUID() };
      return api<Schema["ExportAccepted"]>("exports", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, format }),
        idempotencyKey: key.current.id,
      });
    },
    onSuccess: (r) => {
      setResult(r);
      try {
        sessionStorage.setItem(`terralens-export:${runId}`, JSON.stringify(r));
      } catch {}
      key.current = null;
    },
  });
  const exported = useQuery({
    queryKey: ["export", result?.export_id],
    queryFn: () =>
      api<Schema["ExportResponse"]>(`exports/${result!.export_id}`),
    enabled: !!result,
    refetchInterval: (q) =>
      q.state.data &&
      ["completed", "failed", "expired", "cancelled"].includes(
        q.state.data.status,
      )
        ? false
        : 2000,
  });
  return (
    <div className="grid min-w-0 gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
          Формат
          <SelectControl
            aria-label="Формат"
            value={format}
            onValueChange={(value) => setFormat(value)}
          >
            <SelectOption value="csv">CSV · временной ряд</SelectOption>
            <SelectOption value="geojson">GeoJSON · контур и итог</SelectOption>
            <SelectOption value="json">JSON · полный результат</SelectOption>
          </SelectControl>
        </Label>
        <Button
          variant="outline"
          disabled={start.isPending}
          onClick={() => start.mutate()}
        >
          Подготовить экспорт
        </Button>
      </div>
      <ErrorNotice error={start.error || exported.error} />
      {result && (
        <JobProgress
          id={result.job_id}
          onRetry={(j) => {
            const next = { ...result, job_id: j.id };
            setResult(next);
            try {
              sessionStorage.setItem(
                `terralens-export:${runId}`,
                JSON.stringify(next),
              );
            } catch {}
          }}
        />
      )}
      <div className="flex flex-wrap items-end gap-3">
        {exported.data?.download_url && (
          <Button asChild>
            <a href={exported.data.download_url} download>
              Скачать {exported.data.filename}
            </a>
          </Button>
        )}
        {exported.data?.manifest_url && (
          <Button asChild variant="outline">
            <a
              href={exported.data.manifest_url}
              target="_blank"
              rel="noreferrer"
            >
              Манифест и SHA-256 ↗
            </a>
          </Button>
        )}
      </div>
      {exported.data && (
        <p className="text-xs leading-relaxed text-muted-foreground break-all">
          Ссылка действует до{" "}
          {new Date(exported.data.expires_at).toLocaleString("ru-RU")} ·
          SHA-256: {exported.data.hash || "готовится"}
        </p>
      )}
      {exported.data?.status === "expired" && (
        <p>Экспорт истёк. Подготовьте файл заново.</p>
      )}
    </div>
  );
}
