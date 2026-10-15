# Peticiones de UI de la app `modifier`

Lo que las páginas de Suplementos necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo
más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

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
