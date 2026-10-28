# Tarifas (`pricing`)

Otros precios para los productos y servicios del negocio y sus descuentos automáticos: tarifas por grupo de
clientes, con fechas y tramos por cantidad (una puede ser la general, para todos), reglas de descuento por
línea y la consulta que dice qué precio toca a una línea, de qué tarifa sale, qué regla le quita cuánto y
cuánto queda.

- **Estado**: completa (2026-10-21): los 14 flujos, `PRICING-F01` … `F14`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Las tarifas** (F01–F05): ver, buscar y filtrar tras el embudo (abre en «Activas»), crear con código único
  sin distinguir mayúsculas, divisa ISO 4217 de dos decimales (la del negocio, la de su país, si no se dice),
  base fiscal (según el negocio, con o sin impuesto), grupo de clientes y fechas; editar solo lo enviado;
  elegir la general (una sola, sin grupo y en la divisa del negocio) y desactivar o reactivar (nunca la general).
- **Los precios** (F06–F08): el detalle de la tarifa con sus precios, el de ficha de Inventario al lado;
  poner el precio de un producto o de un servicio desde una cantidad mínima en la unidad del producto
  (repetirlo da precios por volumen), cambiarlo y quitarlo. En una tarifa desactivada solo se quitan.
- **Las reglas de descuento** (F09–F12): porcentaje, importe por unidad, «compra X, llévate Y» y por tramos,
  sobre todo, todos los productos, todos los servicios, una categoría, un producto o un servicio, con grupo,
  cantidad mínima, fechas y prioridad; editar, desactivar y reactivar.
- **El precio de una línea** (F13): entre las tarifas vigentes de la base fiscal de la venta que valen para
  ese cliente gana el precio más bajo (sin ninguna, el de ficha) y, encima, un solo descuento automático, el
  mejor para el cliente, con las cantidades contadas en la unidad del precio. Es una consulta: no escribe ni
  avisa. **Ventas aún no la llama** (el TPV cobra el precio de ficha; ver «Contrato con Ventas»).
- **Lo que borran o cambian otras apps** (F14): un producto, una categoría o un grupo borrados y el nombre
  nuevo de un servicio llegan por el relay del outbox, una sola vez por aviso.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:pricetag` (el del módulo viejo), categoría `catalog`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` (entra en sus plantillas) |
| `requires` | `["inventory", "customer"]`: los precios y las reglas apuntan a productos y categorías de Inventario por clave ajena; el grupo de clientes es un UUID, sin clave ajena (Clientes borra grupos de verdad) |
| Usa de otras apps | Inventario: `Product`, `ProductCategory`, `UNIT_SPECS`, `fits_unit`, `increment_of`, `find_product`, `find_category` y `held` (retiene lo que una escritura nombra); Clientes: `CustomerGroup`, `find_group` y `find_customer`; Servicios (sin requerirla): `service.service.get` por nombre. Las pantallas llaman a `inventory.product.list`, `inventory.category.list`, `customer.group.list` y `service.service.list` |
| La usan | Ninguna app la llama por nombre (Ventas aún no: «Contrato con Ventas»). Automatizaciones puede arrancar con sus avisos y usar sus acciones que no son de riesgo alto (FLOW-F11, FLOW-F21), como con cualquier app |
| Pantallas | `/pricing/lists` (las dos tablas: tarifas y reglas) y `/pricing/lists/:id` (el detalle de la tarifa con sus precios); altas y ediciones en `FormModal` |
| Operaciones | 5 consultas (`queries.py`) y 16 acciones (`services.py`), todas con `ai=`; 17 rutas en `/api/pricing/…` (las 4 reacciones `pricing.catalog.*`, solo de la plataforma, no tienen ruta) |
| En vivo | `pricing.price_list.list`, `.get`, `pricing.price_item.list` y `pricing.rule.list` (`live.py`) |
| Eventos | 12, `pricing.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `inventory.product.deleted`, `inventory.category.deleted`, `customer.group.deleted` y `service.service.updated`, por el relay del outbox |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin con CRUD sobre tarifas, precios y reglas en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (qué tarifa gana, un solo descuento por línea, las cantidades en la unidad del
precio, la marca de la general, lo que una escritura retiene) están en «Referencia adoptada» y en «Para
quien lo mantiene» del WORKBOOK; las de la migración, en la ronda 2026-10-21 (CLOSE-PRICING) de
`PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/pricing
pnpm test apps/pricing
pnpm e2e tests/e2e/pricing-flows.spec.ts tests/e2e/pricing-lists.spec.ts tests/e2e/pricing-business-currency.spec.ts
```

- `tests/test_integration_inventory.py`, `test_integration_customer.py` y `test_integration_service.py` van
  contra las apps reales; `test_relay.py`, las cuatro reacciones entregadas por el tick real del relay del
  outbox, una sola vez y con dos negocios; `test_concurrency.py`, en hilos (la general elegida a la vez, el
  código repetido, el borrado de lo que una escritura nombra y el del detalle que se lee).
- `pricing-flows.spec.ts` recorre PRICING-F01 a F12 en 390, 834 y 1440; `pricing-lists.spec.ts`, de la
  tarifa al precio de una línea (PRICING-F13); `pricing-business-currency.spec.ts`, el negocio en Polonia
  (tarifas y precios en eslotis) y de vuelta en España. `tests/test_business_currency.py`: la divisa del
  negocio en el precio de una línea, la tarifa general y una tarifa nueva, con dos negocios y el hub de ERPlora.

## Qué queda fuera

- Descuentos por importe del tique, horarios (happy hour), conversión de divisas o de bases fiscales, reglas
  por categoría de servicio y borrar tarifas o reglas: «Lo que NO hace, a propósito» del WORKBOOK.
- Que Ventas pida el precio a Tarifas: es de Ventas («Contrato con Ventas» del WORKBOOK).
- El panel lateral del `DataTable` de [`UI-REQUESTS.md`](UI-REQUESTS.md).
