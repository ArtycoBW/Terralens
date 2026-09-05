import { Suspense } from "react";
import { Comparison } from "@/components/analysis/comparison";
export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
          Загружаем сравнение…
        </div>
      }
    >
      <Comparison />
    </Suspense>
  );
}
