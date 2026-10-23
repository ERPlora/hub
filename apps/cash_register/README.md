# Caja (`cash_register`)

El efectivo del cajón por turnos: se abre una sesión con su fondo, los cobros, anulaciones y devoluciones
de Ventas aparecen solos, las entradas y salidas se apuntan a mano, se cuenta el cajón por billetes y
monedas y al cerrar quedan para siempre el esperado, el contado y la diferencia.

- **Estado**: completa (2026-10-21): los 17 flujos, `CASH_REGISTER-F01` … `F17`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Ajustes y cajones** (F01, F02): caja activada, fondo y recuento obligatorios, saldo negativo, arqueo
  ciego y cierre automático; los de fábrica valen sin guardar nunca. Cajones con nombre único, que se
  desactivan y nunca se borran.
- **El turno** (F03, F05, F06, F09): una sesión abierta por negocio, número `S-AAMMDD-NNNN` por día de
  negocio, entradas y salidas con concepto, arqueo por billetes y monedas y cierre con esperado, contado y
  diferencia congelados.
- **Lo que viene de Ventas** (F13, F14, F15, F17): cada cobro, anulación y devolución, por forma de pago,
  leído de Ventas al mirar; lo que no cae en ningún turno sale en «Cobros fuera de turno».
- **Reglas del cierre** (F04, F07, F08, F10): Ventas no cobra en efectivo con la caja cerrada; arqueo ciego
  por permiso; revisión del turno con cuentas abiertas, comandas sin servir e impresiones sin salir, que
  avisa y nunca impide; cierre solo al corte del día de una sesión olvidada.
- **Consultar e imprimir** (F11, F12, F16): detalle de la sesión con movimientos y arqueos, las cifras
  «Sesión actual» y «Descuadres recientes» encima de la tabla, e informe X o Z por la cola de recibos de
  Impresión (sin ella, por el navegador); los dos papeles, el del dispositivo y el del navegador, lo
  titulan X o Z.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:cash-outline`, categoría `sales`, gratuita (`premium = False`) |
| Verticales | `hair_salon`, `restaurant` (entra en sus plantillas) |
| `requires` | `["sale"]`; Ventas no requiere Caja (sería un ciclo): pregunta por nombre a `cash_register.session.current` |
| Usa de otras apps | Ventas, su requisito: lee `Sale`, `SalePayment`, `RefundPayment` y sus cuentas abiertas (`sale.order.list`). Sin requisito, por nombre: Cocina (`kitchen.ticket.board`) e Impresión (`printing.job.summary`; `printing.job.create` encola el informe) |
| Pantallas | `/cash_register/sessions`, `/cash_register/sessions/:id`, `/cash_register/settings` |
| Operaciones | 8 consultas (`queries.py`) y 9 acciones (`services.py`), todas con `ai=`; rutas en `/api/cash_register/…` |
| Eventos | 7, `cash_register.<entidad>.<hecho>` (`events.py`); sin `REACTIONS`: no escucha a nadie |
| Tarea programada | `auto_close_sessions` → `cash_register.session.auto_close`, `*/5 * * * *`, `collapse` (la corre el worker) |
| Migraciones | `0001_initial`; los índices que necesita de Ventas están en `sale/0005_cash_register_indexes` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (las líneas se leen y se copian al cerrar, el esperado, la concurrencia, la
numeración, el arqueo ciego, la zona horaria de la fase 1) están en «Para quien lo mantiene» del
WORKBOOK; las de la migración, en la ronda 2026-10-21 de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/cash_register apps/sale/tests/test_integration_cash_register.py
pnpm test apps/cash_register
pnpm e2e tests/e2e/cash-register-flows.spec.ts tests/e2e/cash-register-settings.spec.ts \
  tests/e2e/cash-register-shift.spec.ts tests/e2e/sale-cash-gate.spec.ts
```

- `tests/test_integration_sale.py` y `test_integration_printing.py` van contra Ventas e Impresión reales,
  sin dobles; `tests/test_concurrency.py`, con sesiones reales en hilos.
- `cash-register-flows.spec.ts` recorre los 17 flujos con pantalla en 390, 834 y 1440.

## Qué queda fuera

- Una sesión por cajón, el umbral de descuadre con aprobación y el «no-sale»: «Lo que NO hace, a
  propósito» del WORKBOOK.
- Los cinco componentes compartidos de [`UI-REQUESTS.md`](UI-REQUESTS.md).
