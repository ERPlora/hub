# ⚠️ DEPRECADO — reemplazado por `@erplora/module-toolkit`

Este paquete (`@erplora/module-cli`: `erplora module build|validate`) funcionaba cuando los módulos
vivían **dentro** del pnpm workspace de `hub/` (resolvía `lit`/`@erplora/*` por symlinks del
workspace). Tras mover el source de los módulos a repos independientes
(`ERPlora/modules-workspace/modules/<id>/`, 2026-06-07/08), sus scripts (`build:inventory`,
`build:all`) **ya no resuelven** (apuntan a `hub/modules`, vacío).

**Usa el toolkit nuevo:** [`ERPlora/module-toolkit`](../../../module-toolkit/) — `@erplora/module-toolkit`.
Es un repo propio (fuera del workspace), estilo Ionic CLI:

```sh
erplora startproject <n>   # workspace de dev (Ionic + OutfitKit por defecto)
erplora g module <id>      # scaffolding de un módulo
erplora dev <id>           # preview con datos mock, CSP-safe
erplora build <id>         # → dist/<id>.esm.js (mismo contrato que aquí)
erplora validate|pack|sign|publish <id>
```

El nuevo `build` resuelve/deduplica `lit` + `@erplora/*` vía un resolve-plugin del toolkit
(funciona con módulos standalone fuera de cualquier workspace). El contrato de salida
(`dist/<id>.esm.js`, bundle auto-contenido CSP-safe sin import-map) es **idéntico**, así que
`module-loader`/`sync-modules` no cambian.

> Se deja como histórico. Borrarlo es decisión del humano (afecta a los scripts `build:*` del
> `package.json` raíz de `hub/`, también obsoletos: el Hub ya no compila módulos, solo copia sus
> `dist/` con `apps/web/sync-modules.mjs`).
