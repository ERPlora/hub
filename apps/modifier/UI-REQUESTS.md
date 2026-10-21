# Peticiones de UI de la app `modifier`

Lo que las páginas de Suplementos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Al cerrar la app (2026-10-21)**, contra `ERPlora/ui` `origin/main` `9962696` (el puntero del Hub va en
`f62af6b`): no ha llegado nada de lo de abajo. Ninguno rompe un flujo (todos tienen su sustituto, dicho en cada
punto), así que pasan a «Fuera por ahora» (`## 6` de `MIGRATION.md`) con las claves `modifier:ui-icons` y
`modifier:ui-sheet-sections`; los componentes compartidos son los mismos que ya esperan allí por Menús
(`combo:ui-money-reader`, `combo:ui-live-server-table`). Quien los suba a `ui` los borra de aquí y cambia el
sustituto en la misma PR del puntero.

## Iconos (registrarlos en `packages/ui/src/shell/icons.ts`, `ION_ICONS`)

- `ion:options-outline` — icono del módulo y de su entrada de menú (`apps.py` `icon` y `navigation`), el
  del producto actual (`options-outline`). Hoy: `lucide:sliders-horizontal`, el mismo dibujo (dos
  deslizadores) en Lucide, ya registrado; `ion:layers-outline` no, porque ya es el de Menús (`combo`).
  Al registrarlo, cambiar a la vez `apps.py`, `tests/test_apps.py`, el icono de las tarjetas y del vacío
  de `frontend/pages/GroupsPage.vue`, y correr `pnpm gen:app-icons`.

## Hoja con secciones

- **Qué**: una hoja (`ion-modal`) con título, «Cerrar» y varias secciones, cada una con su lista, sus
  estados (cargando, vacío, error) y su «Cargar más». Servicios tiene la suya (`SheetModal`, una sola
  lista) y Suplementos la suya (`GroupSheet`, opciones y «Se aplica a»). **Hoy**: cada app la monta con
  `ion-modal` y los componentes de `@erplora/ui` (`InlineFeedback`, `StatusPill`, `ConfirmDialog`).

## Componentes compartidos

- **Lector de importes con signo** (`lib/money.ts` + `components/MoneyInput.vue`, con su botón ±): el mismo de
  Servicios, Inventario y Menús. Cada app lleva hoy su copia porque una app no importa el código de otra;
  debería vivir en `@erplora/ui/components` como `MoneyInput` con la prop `signed`. Al llegar, se borra la copia.
- **`useLiveList` / `useServerTable` / `useT`** (`frontend/composables/`): copias de las de Impuestos, como en el
  resto de apps; mismo destino (`@erplora/ui/sdk`). `useSheetList` (las listas de la hoja, de 20 en 20) va con la
  hoja con secciones de arriba.
