# Servicios (`service`)

El catálogo de lo que vende una peluquería o un centro de estética cuando no es un artículo: cada servicio
con su tarifa, su precio, su duración, su categoría y su categoría fiscal, y qué profesionales lo hacen, con
su duración y su precio propios. También guarda los bonos: paquetes de sesiones que una clienta paga una vez
y gasta en varias visitas, con su saldo, su caducidad, sus ajustes y cada sesión gastada.

- **Estado**: completa (2026-10-21): los 33 flujos, `SERVICE-F01` … `F33`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **El catálogo** (F01–F08, F11): dar de alta, editar, archivar y restaurar servicios (también muchos de
  golpe por el asistente o la API), tarifas de precio abierto («Desde», «Por hora», «Variable», «Gratis»),
  categorías en árbol con nombre único entre las vivas, y los ajustes que toma un servicio nuevo cuando no
  se dicen (duración, margen, reserva online y categoría fiscal).
- **Quién lo hace** (F31–F33): asignar profesionales de Personal a un servicio con sus minutos y su precio
  propios, marcar el servicio principal, apagar o quitar una asignación, y decir quién puede hacerlo (solo
  personas activas y reservables). Quien se da de baja en Personal sale de todos sus servicios.
- **Lo que leen otras apps** (F09, F10): la agenda de Citas, el TPV de Ventas, la página de Reservas online
  y Tarifas leen los servicios en oferta; un servicio sin categoría fiscal sale marcado y no se vende.
- **Los bonos** (F12–F21): crear, editar y eliminar bonos del catálogo; concederlos a una clienta con sus
  condiciones congeladas; ver quién los compró, sus movimientos y su saldo; anular uno sin usar, regalar o
  quitar sesiones y alargar la caducidad con motivo; gastar una sesión fuera del cobro.
- **El bono en el cobro** (F22–F27, con Ventas): pagar una línea con un bono (la sesión queda reservada un
  día), soltarla si la línea o la cuenta desaparecen, darla por gastada al cobrar y devolverla al devolver
  o anular la venta, todo en la misma transacción que la escritura de Ventas.
- **Las fichas de Clientes** (F28–F30): al unir dos fichas, los bonos pasan a la que queda; al eliminar o
  anonimizar una, sus bonos quedan «sin cliente» (y, al anonimizar, sin sus textos libres) y se rescatan
  desde «Bonos sin cliente».

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:briefcase-outline` (el del módulo viejo), categoría `catalog`, gratuita (`premium = False`) |
| Verticales | `hair_salon` (entra en su plantilla; la de restaurante no la trae) |
| `requires` | `["tax", "staff", "customer"]`: la categoría fiscal es de Impuestos, los profesionales de Personal y la titular de un bono, de Clientes |
| Usa de otras apps | Impuestos: `tax.TaxCategory` (claves ajenas, con la lectura retenida `FOR KEY SHARE`). Personal: `staff.Member` y `resolve_member`. Clientes: `customer.Customer`, `find_customer` y el bloqueo de la ficha. La venta y la cita de una sesión son identificadores opacos (`sale_id`, `appointment_id`): Ventas y Citas no son requisito |
| Quién la lee | Citas (`service.service.list_for_sale`, `service.assignment.eligible` y los modelos; la requiere), Ventas (`list_for_sale`, `get`, `assignment.list`, `grant.tender_options` y `service.session.*`, por nombre y sin requerirla), Reservas online (los modelos, los ajustes y `service.service.list`/`.update`; la requiere) y Tarifas (`service.service.list` y `.get`, sin requerirla) |
| Pantallas | `/service/services`, `/service/categories`, `/service/packages`, `/service/settings`; el hueco del bono en el cobro lo monta Ventas (SALE-F27) |
| Operaciones | 18 consultas (`queries.py`) y 27 acciones (`services.py`), todas con `ai=`; 37 rutas en `/api/service/…` (sin ruta: las 4 de la plataforma, con `service.system`, y las 4 `service.session.*` que Ventas corre dentro de sus escrituras) |
| Eventos | 25, `service.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `staff.member.terminated` (`service.assignment.release_member`), `customer.customer.merged` (`service.grant.reassign`) y `customer.customer.erased` (`service.grant.forget_customer`), por el relay del outbox |
| Tarea programada | `expire_session_holds` → `service.session.expire`, `0 * * * *`, `collapse` (la corre el worker) |
| Migraciones | `0001_initial`, `0002_redemption_states` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (saldo calculado al leer, estados de una sesión, concurrencia, árbol de
categorías, reacciones) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda
2026-10-21 (CLOSE-SERVICE) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/service apps/sale/tests/test_integration_service.py \
  apps/appointment/tests/test_integration_service.py apps/pricing/tests/test_integration_service.py
pnpm test apps/service apps/sale/frontend/components/checkout
pnpm e2e tests/e2e/service-flows.spec.ts tests/e2e/service-catalog.spec.ts tests/e2e/service-vouchers.spec.ts \
  tests/e2e/sale-voucher.spec.ts tests/e2e/fix-service-setup-hooks.spec.ts
```

- `tests/test_integration_tax.py`, `test_integration_staff.py`, `test_integration_customer.py` y
  `test_integration_sale.py` van contra las apps reales, sin dobles; `test_relay.py`, contra Clientes y
  Personal por el tick real del relay del outbox, con dos hubs; `test_concurrency.py`, con dos cajas a la
  vez en hilos.
- `service-flows.spec.ts` recorre los flujos con pantalla en 390, 834 y 1440; el bono en el cobro se ve en
  `sale-voucher.spec.ts`.
- `test_integration_home.py` lleva el paso «Tu catálogo de servicios» del Inicio por la consulta real de `base`
  (con dos hubs y con Servicios apagada); `fix-service-setup-hooks.spec.ts` lo recorre en 390, 834 y 1440.

## Qué queda fuera

- Vender un bono en el TPV (y, con ello, concederlo al cobrar y anularlo con su venta) e importar servicios
  desde un fichero: «Lo que queda fuera» del WORKBOOK.
- El panel lateral de [`UI-REQUESTS.md`](UI-REQUESTS.md).
