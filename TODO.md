# TODO — Hub (backlog vivo)

> **Qué es esto:** lista de trabajo específica del **Hub** (runtime Rust + `apps/web` Vue3 + Ionic +
> OutfitKit). Se ordena por prioridad; el item **#1** es lo que atacamos ahora. El backlog amplio del
> núcleo sigue en [`BACKLOG.md`](BACKLOG.md); el backlog cross-component, en el [`roadmap/TODO.md`](../pm/roadmap/TODO.md).
>
> **Convenciones:** `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[H]` requiere al humano
> (core/decisión) · `[IA]` la IA puede acelerar (tests/docs/boilerplate). Toda decisión de
> arquitectura → su ADR en `architecture/00-overview/decision-log.md`.

---

## 1. Asistente persistente — panel lateral que vive en el shell 🎯 EN FOCO

> **Meta:** el Asistente deja de ser un *drawer* overlay que se cierra al navegar y pasa a ser un
> **panel independiente del shell** que, al activarse, **se mantiene abierto en todas las páginas**
> hasta que el usuario lo cierra. En **desktop** se queda fijo y visible **junto al drawer principal**
> (modo *push*: empuja el contenido, sin scrim, como un segundo panel / `ion-menu side="end"`). En
> **móvil** funciona como **overlay con backdrop** (igual que `ion-menu`/`ion-drawer` por defecto).
> Misma conducta y misma estética que en el Cloud (**paridad obligatoria** — ver
> [`saas/TODO.md` #1](../saas/TODO.md)).

**Estado hoy:** es un drawer overlay custom (slide-over `translateX`) con scrim:
- Componente → [apps/web/src/components/AssistantDrawer.vue](apps/web/src/components/AssistantDrawer.vue) (drawer propio en CSS, no usa `ok-drawer`).
- Montaje en el shell → [apps/web/src/App.vue:99](apps/web/src/App.vue#L99) (import en línea 117).
- Botón sparkles en la topbar → [apps/web/src/components/AppTopbar.vue:59-68](apps/web/src/components/AppTopbar.vue#L59-L68).
- Estado global `assistantOpen` / `toggleAssistant` / `closeAssistant` → [apps/web/src/lib/shell.ts:9-35](apps/web/src/lib/shell.ts#L9-L35) (ya persiste entre rutas por ser ref de módulo).
- Chat SSE intacto → [apps/web/src/lib/assistant.ts](apps/web/src/lib/assistant.ts) (`POST /api/assistant/chat/stream`).

**Tareas:**

- [x] [H] **Decisión de layout (preguntar, no decidir).** RESUELTO por el humano en el brief de la
  tarea: el panel queda `position:fixed; right:0; width:420px` y el **push** se logra cuando
  `html.assistant-open` (clase global que togglea AssistantDrawer), con scrim+overlay solo `<992px`.
  (No se usó segunda zona del split-pane ni `ion-menu side="end"`.) Breakpoint 992px (lg), paridad
  con el Cloud. **NOTA QA:** el push se hace encogiendo el `ion-split-pane` (`inset-inline-end:420px`),
  NO padeando `ion-app` — Ionic posiciona el split-pane `absolute; inset:0` y un hijo `inset:0` llena
  el padding-box, así que el padding del host NO lo encoge (el contenido quedaba tapado, no empujado).
- [x] [IA] **Refactor de [AssistantDrawer.vue](apps/web/src/components/AssistantDrawer.vue):** de
  overlay `translateX` a **panel persistente** que **empuja el contenido** en desktop (sin scrim, ancho
  fijo 420px) y **overlay + scrim** debajo del breakpoint. Chat SSE y footer intactos (solo layout).
- [x] [IA] **Persistir el estado abierto entre recargas:** `assistantOpen` respaldado en `localStorage`
  (clave `erplora.assistant.open`) desde [apps/web/src/lib/shell.ts](apps/web/src/lib/shell.ts):
  el ref se inicializa desde localStorage y un `watch` escribe en cada cambio.
- [x] [IA] **Verificación (directiva QA, 3 viewports):** `typecheck` + `build` VERDES y **QA visual con
  Playwright HECHA** (Hub local `pnpm dev` :5173 + runtime :8787, viewports 1280/800/390): desktop
  empuja real el contenido a 860 sin solape ni scrim; persiste al navegar (SPA→/billing) y al recargar
  (localStorage); tablet/móvil overlayan con scrim que cierra. **Se detectó y corrigió** que el push
  por `padding ion-app` no encogía el split-pane (ver nota arriba). Pendiente solo review/merge humano.

---

## Backlog (sin ordenar — mover arriba al priorizar)

> El backlog del núcleo (runtime/crates/módulos) sigue en [`BACKLOG.md`](BACKLOG.md).

- [ ] _(añadir aquí lo que vaya saliendo en el Hub)_

---

_Última actualización: 2026-06-21 — creada la lista del Hub; item #1 = asistente persistente._
