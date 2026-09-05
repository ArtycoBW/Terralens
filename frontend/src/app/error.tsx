"use client";
import Link from "next/link";
export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main id="main" className="connection">
      <p className="eyebrow">TerraLens</p>
      <h1>Не удалось показать страницу</h1>
      <p>
        Повторите загрузку. Уже запущенный расчёт продолжает выполняться на
        сервере.
      </p>
      {error.digest && (
        <p className="micro muted">Код ошибки: {error.digest}</p>
      )}
      <div className="actions">
        <button className="primary-link" onClick={retry}>
          Повторить
        </button>
        <Link className="primary-link" href="/app">
          Открыть карту
        </Link>
      </div>
    </main>
  );
}
