# TerraLens frontend

Next.js App Router, TypeScript, Tailwind/shadcn, TanStack Query, MapLibre + Terra Draw.

```powershell
pnpm install --frozen-lockfile
pnpm dev --port 3001
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

API должен работать на `127.0.0.1:8000`. Next проксирует `/api/v1`; `API_INTERNAL_URL` задаёт адрес сервера в контейнере. Используйте один origin для приложения и API. Поддержаны localhost:3000 и localhost:3001; второй порт удобен, когда первый занят другим проектом.

Типы генерируются из общего контракта: `pnpm api:generate`. TypeScript 5.9 закреплён из-за совместимости с openapi-typescript; ESLint 9 — с eslint-plugin-react. Three.js 0.143 сохранён для supplied Ascend, который использует WebGL1Renderer и прежний colour pipeline.


Этап 1: сессия и CSRF, навигация, карта, поиск регионов/OSM, рисование и ввод GeoJSON, сохранение полей. Проверки: production build, TypeScript, ESLint, 15 unit tests; Chrome — создание поля по реальному OSM-контуру Потсдама через Next proxy.
