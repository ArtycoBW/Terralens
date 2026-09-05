"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, label, terminalJob, type Job } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Status } from "./common";
export function JobProgress({
  id,
  onFinish,
  onRetry,
}: {
  id: string;
  onFinish?: () => void;
  onRetry?: (job: Job) => void;
}) {
  const client = useQueryClient();
  const job = useQuery({
    queryKey: ["job", id],
    queryFn: ({ signal }) => api<Job>(`jobs/${id}`, { signal }),
    refetchInterval: (q) =>
      q.state.data && terminalJob(q.state.data.state) ? false : 2000,
  });
  const mutate = useMutation({
    mutationFn: (action: string) =>
      api<Job>(`jobs/${id}/${action}`, { method: "POST", body: "{}" }),
    onSuccess: (j, action) => {
      client.invalidateQueries({ queryKey: ["job", id] });
      if (action === "retry") onRetry?.(j);
    },
  });
  useEffect(() => {
    if (job.data?.state && terminalJob(job.data.state)) {
      onFinish?.();
      client.invalidateQueries({ queryKey: ["run"] });
    }
  }, [job.data?.state, onFinish, client]);
  return (
    <div className="job-box">
      <ErrorNotice error={job.error || mutate.error} />
      {job.data && (
        <>
          <div className="actions">
            <Status value={job.data.state} />
            <span className="small">
              {label[job.data.stage] || job.data.stage}
            </span>
          </div>
          <progress
            aria-label="Прогресс задачи"
            max={1}
            value={job.data.progress ?? undefined}
          />
          <p className="micro muted" aria-live="polite">
            {job.data.progress == null
              ? "Ожидаем данные"
              : `${Math.round(job.data.progress * 100)}%`}{" "}
            · Попытка {job.data.attempt}
            {job.data.cancel_requested ? " · Отмена запрошена" : ""}
          </p>
          {job.data.error && (
            <p role="alert" className="small">
              {String(
                (job.data.error as { message?: string }).message ||
                  "Задача завершилась с ошибкой",
              )}
            </p>
          )}
          <div className="actions">
            {!terminalJob(job.data.state) && (
              <Button
                size="sm"
                variant="outline"
                disabled={mutate.isPending || job.data.cancel_requested}
                onClick={() => mutate.mutate("cancel")}
              >
                Отменить задачу
              </Button>
            )}
            {job.data.retryable && onRetry && (
              <Button
                size="sm"
                variant="outline"
                disabled={mutate.isPending}
                onClick={() => mutate.mutate("retry")}
              >
                Повторить задачу
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
