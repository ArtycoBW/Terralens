# Ascend — source template

This is the complete source for the **Ascend** project, distributed as a GetLayers template.
It's a Vite project —
the full project tree, minus installed dependencies and any local secrets.

## Run it as-is

```sh
npm install
npm run dev      # Vite prints a localhost URL
# production build: npm run build  (output in dist/)
```

> If the project needs environment variables (e.g. an API key), copy `.env.example` to
> `.env` (or `.env.local`) and fill it in — secrets are intentionally **not** included.

## Reuse it with your AI

Hand this whole folder to your AI coding assistant — Claude, Cursor, Copilot, v0 — and ask it
to adapt the parts you want into your own project, in any framework. The companion **prompt**
on the GetLayers listing rebuilds this same result as a single self-contained plain-HTML file;
this source bundle is the reference implementation behind it.
