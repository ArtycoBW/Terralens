# TerraLens frontend

Next.js App Router, TypeScript, Tailwind/shadcn, TanStack Query, MapLibre + Terra Draw, ECharts. Лендинг — адаптация Ascend с Three.js, GSAP и Lenis.

Из корня `docker compose up --build -d` запускает всё приложение на http://localhost:3001. Для разработки запустите backend/worker через Compose, затем из frontend:

```powershell
pnpm install --frozen-lockfile
pnpm dev --port 3001
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm test:e2e
```

API должен работать на `127.0.0.1:8000`. Next проксирует `/api/v1`; `API_INTERNAL_URL` задаёт адрес сервера в контейнере. Используйте один origin для приложения и API. Поддержаны localhost:3000 и localhost:3001; второй порт удобен, когда первый занят другим проектом.

Если frontend уже запущен через Compose, перед `pnpm dev --port 3001` выполните из корня `docker compose stop frontend`. Playwright локально использует установленный Chrome, в CI — Chromium. Для другого адреса задайте `E2E_BASE_URL`; сервер должен быть запущен до тестов. Воспроизводимый сквозной тест без API-моков: `node tests/live-flow.mjs` (создаёт гостевое пространство и поле, обращается к спутниковым сервисам, сохраняет результаты в artifacts/frontend-work/live-browser). Обычные E2E используют контрактные fixtures и не требуют внешних источников.

Типы генерируются из общего контракта: `pnpm api:generate`. TypeScript 5.9 закреплён из-за совместимости с openapi-typescript; ESLint 9 — с eslint-plugin-react. Three.js 0.143 сохранён для supplied Ascend, который использует WebGL1Renderer и прежний colour pipeline.


Этап 1: сессия и CSRF, навигация, карта, поиск регионов/OSM, рисование и ввод GeoJSON, сохранение полей. Проверки: production build, TypeScript, ESLint, 15 unit tests; Chrome — создание поля по реальному OSM-контуру Потсдама через Next proxy.

Этап 2: список/редактирование полей и сезонов, история, запуск/отмена/повтор анализа, ежедневные ряды/погода/аномалии, качество и provenance, экспорт CSV/GeoJSON/JSON, сравнение до четырёх анализов с URL, реестр моделей, анонимный benchmark. Проверки: build, typecheck, lint, 17 unit tests; из Chrome запущен реальный расчёт с тремя прошлыми сезонами. Данные benchmark обновляются `python scripts/build_frontend_benchmark.py` из корня репозитория.

