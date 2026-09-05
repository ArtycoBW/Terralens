"use client";
import { Button } from "@/components/ui/button";

import Link from "next/link";
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main
      id="main"
      className="mx-auto my-[15dvh] grid max-w-xl gap-5 px-6 [&_h1]:text-3xl"
    >
      <p className="mb-2 text-xs font-medium text-muted-foreground">
        TerraLens
      </p>
      <h1>Не удалось показать страницу</h1>
      <p>
        Повторите загрузку. Уже запущенный расчёт продолжает выполняться на
        сервере.
      </p>
      {error.digest && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          Код ошибки: {error.digest}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Button variant="ghost" className="mt-3 w-fit" onClick={retry}>
          Повторить
        </Button>
        <Link className="mt-3 w-fit" href="/app">
          Открыть карту
        </Link>
      </div>
    </main>
  );
}
