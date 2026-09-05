import {Suspense} from "react";
import {Comparison} from "@/components/analysis/comparison";
export default function Page(){return <Suspense fallback={<div className="page-pad">Загружаем сравнение…</div>}><Comparison/></Suspense>}
