# Demo (`demo`)

La app de referencia de la fase 1: elementos con nombre, estado y nota, cada uno con sus líneas. No
resuelve nada del negocio; enseña el patrón completo de una app del Hub (lista y ficha vivas, línea
optimista e idempotente, permisos por papel) y es la que se copia para escribir cualquier otra.

- **Estado**: completa (2026-10-21): los 6 flujos, `DEMO-F01` … `F06`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`**: ninguna abierta (sin `UI-REQUESTS.md`). La única que tuvo, la barra
  de la ficha plegada en «⋮» en el móvil, llegó con ERPlora/ui#13.
- **No es la demo pública.** Los negocios de demostración (`demo-<hex>`, los que pide el `/demo/` del
  SaaS) son de `base`: README del Hub, «Demo», y `tests/e2e/demo.spec.ts`. Comparten el nombre, nada más.

## Qué hace hoy

- **Lista** (F01, F05, F06): tabla del servidor con buscador por nombre, filtro de estado tras el
  embudo, 50 por página (10, 25, 50 o 100), tabla o tarjetas y, en el móvil, «Cargar más» hasta 100
  elementos y páginas a partir de ahí; encima, las cifras «Abiertos», «Hechos» y «Líneas» para quien
  gestiona.
- **Crear, editar y borrar** (F01, F02, F03): formularios con el error bajo cada campo; editar solo
  cambia lo enviado y, sin cambios, no avisa; borrar pide confirmación y se lleva las líneas.
- **Línea al instante** (F04): aparece antes de que conteste el servidor, se deshace si lo rechaza y
  repetirla con el mismo `client_line_id` no la duplica ni vuelve a avisar.
- **En vivo** (F05): lista, ficha y cifras se re-ejecutan en el servidor tras el COMMIT y llegan por
  `/api/live`; el aviso de `a` no llega a `b`.
- **Sin permiso** (F06): el empleado solo ve; la ficha deja de pintar el elemento si se borra en otro
  sitio o si le quitan el permiso con la pantalla abierta.
- **Ejemplo de los ganchos del Inicio** (BASE-F01, F06, F10; PLAN-HUB, ronda 2026-10-21): un paso de «Termina de
  configurar tu negocio» («Crea tu primer elemento»), un panel del tablero («Elementos abiertos») y un contador
  de la campana («Elementos de demo abiertos»), el modelo que copian los módulos. Como Demo no está en la tienda,
  `base` solo los enseña con `HOME_UNLISTED_HOOKS` (desarrollo, tests y e2e) o en un hub de demo; nunca a un cliente.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:flask-outline`, categoría `organization`, gratuita (`premium = False`), fuera de la tienda (`listed = False`) |
| Verticales | ninguna (no entra en ninguna plantilla) |
| `requires` | ninguno; no lee ni llama a otras apps |
| Permisos | `demo.view` (todos los papeles) y `demo.manage` (todos menos el empleado) |
| Pantallas | `/demo/items`, `/demo/items/new`, `/demo/items/:id`, `/demo/items/:id/edit` |
| Operaciones | 4 consultas (`queries.py`: `list`, `detail`, `stats` y `open_count`, la del contador de la campana) y 4 acciones (`services.py`: `create`, `update`, `delete`, `add_line`), todas con `ai=` (`risk = "high"` solo en `delete`); rutas en `/api/demo/items…`, sin parámetros en la ruta |
| Eventos | 4, `demo.item.<hecho>` (`events.py`); sin `REACTIONS`: no escucha a nadie |
| Ganchos del Inicio | `setup` (`first_item`), `widgets` (`open_items`, `kpi`) y `bell` (`open_items`) |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin con CRUD sobre elementos y líneas en `hubs.erplora.com` (PLAN §17–§18), por el ORM y sin aviso, como el de las demás apps |

Las decisiones de diseño (rutas sin parámetros, línea idempotente por `(elemento, client_line_id)` con
la fila bloqueada, errores y sus códigos, qué deja de pintar la ficha, papeles con prefijo `hub_`, ámbito
de la fase 1, el tope de 100 filas de la lista, `ai=` y el admin) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda
2026-10-21 (CLOSE-DEMO) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/demo
pnpm test apps/demo
pnpm e2e tests/e2e/demo-flows.spec.ts tests/e2e/two-tabs-live.spec.ts tests/e2e/optimistic-add-line.spec.ts \
  tests/e2e/two-orgs-isolated.spec.ts tests/e2e/reconnect.spec.ts tests/e2e/delete-item.spec.ts \
  tests/e2e/create-edit-pages.spec.ts tests/e2e/edit-keeps-text.spec.ts tests/e2e/list-filters-stats.spec.ts \
  tests/e2e/datatable.spec.ts tests/e2e/employee-permissions.spec.ts
```

- Un `tests/test_<fichero>.py` por fichero de la app; `test_services.py` incluye la concurrencia de
  `add_line` con dos sesiones reales.
- `demo-flows.spec.ts` recorre los 6 flujos en 390, 834 y 1440, con su captura `APP-DEMO-<flujo>-<ancho>`, y la
  lista con más de 100 elementos (el móvil pagina; tres «Cargar más» seguidos dentro de esos 100).

## Qué queda fuera

- Borrar o reordenar líneas, precios e impuestos, y separar los datos de `a` y `b` (llega con la
  tenencia de la fase 2): «Lo que NO hace, a propósito» del WORKBOOK.
- El asistente del Hub que llama a las operaciones por su `ai=` (fase 2): Demo ya las declara.
