# Impresión (`printing`)

Las impresoras del negocio y su cola de impresión: cada impresora con su nombre, su conexión (red, USB,
Bluetooth o la impresora del sistema), su ancho de papel y su función (recibo, cocina, barra o etiqueta); los
dispositivos dados de alta que sacan el papel; y la cola, que dice si el papel sale y deja reintentar o cancelar
lo atascado. No compone documentos ni habla con la impresora: Ventas, Facturación, Caja, Inventario y Cocina le
mandan el documento ya compuesto, y la app de ERPlora del dispositivo lo imprime.

- **Estado**: completa (2026-10-31): 19 de sus 20 flujos, `PRINTING-F01` … `F20`, están `hecho`;
  `PRINTING-F02` está `descartado` con su issue (app#17).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones** a `@erplora/ui` y a la app nativa que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Las impresoras** (F02–F05, F19): darlas de alta por su dirección, buscarlas desde la app del dispositivo,
  darles su función, probarlas con una hoja de prueba y ver su estado («Lista», «Esperando», «Con errores»,
  «Inactiva») con su último error.
- **Los dispositivos que imprimen** (F18): se dan de alta desde el propio dispositivo con las impresoras a las
  que llega; con la app de ERPlora abierta recogen sus trabajos por `/ws/print`, los imprimen y los confirman,
  con 5 intentos y un plazo de 90 s por entrega. Su presencia (cada 30 s) alimenta la campana.
- **La cola** (F01, F14, F20): las tarjetas por función en Impresoras, la tabla completa en Cola con filtros,
  «Reintentar» y «Cancelar» con motivo, el paso «Configura la impresora» del Inicio, la fila «Nadie está
  imprimiendo «…»» de la campana y la limpieza de lo terminado a los 30 días.
- **Lo que piden las demás apps** (F07–F13, F17): el tique al cobrar con sus copias y el cajón si entró
  efectivo, la reimpresión como «DUPLICADO», la cuenta de la mesa, la comanda de cada estación y su
  reimpresión, la etiqueta del código de barras, el informe X/Z y la página A4 de una factura.
- **Los ajustes** (F06, F15) y **el asistente** (F16): tique al cobrar, cajón, copias e impresora de cada
  función; todo se pide también por voz o texto, con la tarjeta de confirmación nombrando impresora,
  dispositivo y trabajo.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `lucide:receipt` (a la espera de `ion:print-outline`, `UI-REQUESTS.md`), categoría `organization`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | ninguna: se enciende sola |
| La usan | Ventas, Facturación, Caja, Inventario y Cocina (llaman a `printing.job.create` por su nombre; ninguna la requiere: sin Impresión, el papel sale por el diálogo del dispositivo); `base` con `/ws/print`, el Inicio y la campana |
| Pantallas | `/printing/printers`, `/printing/devices`, `/printing/jobs`, `/printing/settings`; `PrintHost.vue` (`/printing/print-host`, `meta.background`) corre de fondo en el dispositivo dado de alta |
| Operaciones | 11 consultas (`queries.py`) y 15 acciones (`services.py`), todas con `ai=`; `printing.device.get`, `printing.device.seen` y `printing.job.prune` con `ai=INTERNAL` (las dos primeras, del canal del dispositivo; la última, del sistema); 23 rutas en `/api/printing/…` |
| Hooks del Inicio | `setup` «Configura la impresora» y `bell` «Nadie está imprimiendo «…»» por función, con `printing.device.coverage`; `bell_refresh_every` de 30 s y `print_presence = "printing.device.seen"` |
| Eventos | 13, `printing.<entidad>.<hecho>` (`events.py`), solo con identificadores; no reacciona a ninguno |
| Migraciones | `0001_initial`, `0002_print_device`, `0003_printdevice_last_seen_at`, `0004_printjob_document_type_labels` |
| Admin | Django admin de ajustes, impresoras, trabajos y dispositivos en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (el documento de cada función, el protocolo de `/ws/print`, la presencia, el
cliente del canal en el dispositivo y la tarjeta del asistente) están en «Para quien lo mantiene» del
WORKBOOK; las de la migración, en la ronda de CLOSE-PRINTING de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/printing apps/sale/tests/test_integration_printing.py \
  apps/cash_register/tests/test_integration_printing.py apps/inventory/tests/test_integration_printing.py
pnpm test apps/printing
pnpm e2e tests/e2e/printing-printers.spec.ts tests/e2e/printing-devices.spec.ts tests/e2e/printing-queue.spec.ts \
  tests/e2e/printing-sale.spec.ts tests/e2e/printing-kitchen.spec.ts tests/e2e/printing-assistant.spec.ts \
  tests/e2e/printing-locale-es.spec.ts tests/e2e/printing-ws-client.spec.ts tests/e2e/ws-print.spec.ts
```

- `test_services.py` lleva la máquina de la cola (5 entregas, 90 s, confirmación tardía del mismo
  dispositivo, reintento y cancelación); `test_concurrency.py`, las carreras: dos dispositivos a la vez se llevan
  trabajos distintos, la misma clave a la vez es un trabajo y dos confirmaciones a la vez confirman una;
  `test_presence.py` prueba la presencia por el socket de verdad, con un empleado.
- `test_integration_*.py` dan a Impresión las peticiones reales de Ventas, Cocina, Inventario, el Inicio y el
  asistente; `test_documents.py` es el contrato del documento de cada función.
- `printing-ws-client.spec.ts` y `ws-print.spec.ts` llevan el cliente del dispositivo contra el `/ws/print`
  real.

## Qué queda fuera

- `PRINTING-F02` en una red sin salida a internet (app#17), el ancho del papel en la app del dispositivo y el
  icono `ion:print-outline`: «Lo que queda fuera» del WORKBOOK y [`UI-REQUESTS.md`](UI-REQUESTS.md).
- Relacionada, de otras apps: en la app Android no se abre el diálogo del dispositivo que usan Ventas, Caja y
  Facturación sin impresora de tiques (hub#455).
