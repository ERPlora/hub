# Mesas (`table`)

El plano del restaurante o del bar: las zonas del local, sus mesas colocadas en un plano vivo con su aforo y
su forma, y las cuentas de Ventas sentadas en cada mesa. Dice en el momento qué mesa está libre, ocupada,
reservada o fuera de servicio, cuántos comensales hay, desde cuándo y quién los atiende.

- **Estado**: completa (2026-10-21): los 32 flujos, `TABLE-F01` … `F32`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Dibujar la sala** (F01–F08): zonas con color y orden, mesas que nacen en el primer hueco libre (también
  muchas de golpe por el asistente o la API), arrastrar y soltar en el plano (también con el teclado), número
  único por zona por cualquier puerta, mesas bloqueadas o desactivadas fuera del servicio y los ajustes de
  sala (preguntar los comensales al sentar, avisos ámbar y rojo).
- **El servicio** (F09–F17, F32): el plano vivo de cada zona; sentar a un grupo abre su cuenta en Ventas con
  el título «Mesa N»; volver a la mesa y cobrarla en el TPV; traer a una mesa una cuenta ya abierta («Elegir
  mesa» del TPV, que monta Ventas); aparcar, corregir comensales, transferir, fusionar y dividir, con las dos
  partes (Mesas y Ventas) en la misma operación; el cliente de la mesa.
- **Lo que viene de Ventas** (F18–F21): cobrar entera la cuenta libera la mesa, anular un cobro baja el
  «Cobrado», eliminar la cuenta libera la mesa; cerrar a mano solo una mesa cuya cuenta está vacía.
- **El historial** (F22–F24): Sesiones con las cuentas abiertas, cerradas y todas, su detalle, borrar una
  terminada y volver a sentar una aparcada.
- **Reservas** (F25–F31): retener la mesa de una reserva confirmada (Reservada desde una hora antes), moverla
  o soltarla cuando cambia, gastarla al sentar (desde Reservas, solo la de esa reserva), caducar las vencidas,
  retener a mano por el asistente o la API y olvidar el nombre de una clienta borrada.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:grid-outline` (el viejo, `ion:restaurant-outline`, espera en `UI-REQUESTS.md`), categoría `restaurant`, gratuita (`premium = False`) |
| Verticales | `restaurant` (entra en su plantilla) |
| `requires` | `["sale", "customer"]`; Ventas no requiere Mesas: solo sabe de títulos |
| Usa de otras apps | Ventas: `sale.order.open`, `.set_label`, `.split`, `.merge` y `.void`, en la misma transacción, y lee `Order`, `OrderLine` y `Sale`. Clientes: `customer.order.link`, su `OrderLink` y `find_customer`. Reservas no es un requisito: es ella la que llama a Mesas (`table.hold.*`, `table.session.open` con `reservation_id`) |
| Pantallas | `/table/floor-plan`, `/table/zones`, `/table/tables`, `/table/sessions`, `/table/settings`; «Elegir mesa» del TPV la monta Ventas (SALE-F19) |
| Operaciones | 12 consultas (`queries.py`) y 26 acciones (`services.py`), todas con `ai=`; 33 rutas en `/api/table/…` (las 5 de la plataforma no tienen ruta). Cada id que toma una acción lleva la marca `refers` de la lectura que lo nombra en la tarjeta del asistente (`base.E009`) |
| Eventos | 18, `table.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `sale.order.completed`/`voided` (`table.session.close_by_order`) y a `customer.customer.erased` (`table.hold.forget_customer`), por el relay del outbox |
| Tarea programada | `expire_table_holds` → `table.hold.expire`, `0 * * * *`, `collapse` (la corre el worker) |
| Inicio | El paso «Tus mesas» (`setup`: `table.floor.status`, hecho con una mesa en uso, orden 100, recomendado, para quien crea mesas, lleva a `/table/tables`); sin paneles ni campana, como el módulo viejo |
| Migraciones | `0001_initial`, `0002_session_table_by_status` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (el estado de la mesa se calcula al leer, las retenciones, la concurrencia, lo que
se lee de Ventas, la zona horaria de la fase 1) están en «Para quien lo mantiene» del WORKBOOK; las de la
migración, en las rondas 2026-10-21 (APP-TABLE y CLOSE-TABLE) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/table apps/sale/tests/test_integration_table.py \
  apps/reservation/tests/test_integration_table.py
pnpm test apps/table apps/sale/frontend/components/pos
pnpm e2e tests/e2e/table-flows.spec.ts tests/e2e/table-floor.spec.ts tests/e2e/sale-table.spec.ts tests/e2e/fix-table-setup-hooks.spec.ts
```

- `tests/test_integration_sale.py` va contra Ventas y Clientes reales; `test_integration_relay.py`, contra
  Reservas, Clientes y Ventas reales por el tick del relay del outbox; `test_concurrency.py`, con dos
  camareros a la vez en hilos. Reservas → Mesas, sin dobles, también en
  `apps/reservation/tests/test_integration_table.py`.
- `table-flows.spec.ts` recorre los flujos con pantalla en 390, 834 y 1440.

## Qué queda fuera

- El estado «por limpiar», juntar mesas físicas con el aforo sumado, elegir o cambiar el camarero de una
  cuenta y los planos por turno: «Lo que NO hace, a propósito» del WORKBOOK.
- Los dos iconos de [`UI-REQUESTS.md`](UI-REQUESTS.md).
