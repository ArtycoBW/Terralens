import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="connection">
      <p className="eyebrow">TerraLens · 404</p>
      <h1>Страница не найдена</h1>
      <p>Проверьте адрес или вернитесь в рабочее пространство.</p>
      <Link className="primary-link" href="/app">
        Открыть карту
      </Link>
    </main>
  );
}
