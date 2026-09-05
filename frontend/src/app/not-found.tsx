import Link from "next/link";
export default function NotFound() {
  return (
    <main
      id="main"
      className="mx-auto my-[15dvh] grid max-w-xl gap-5 px-6 [&_h1]:text-3xl"
    >
      <p className="mb-2 text-xs font-medium text-muted-foreground">
        TerraLens · 404
      </p>
      <h1>Страница не найдена</h1>
      <p>Проверьте адрес или вернитесь в рабочее пространство.</p>
      <Link className="mt-3 w-fit" href="/app">
        Открыть карту
      </Link>
    </main>
  );
}
