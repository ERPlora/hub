# Cocina (`kitchen`)

La pantalla de cocina del restaurante: cada ronda que el camarero envía desde el TPV se convierte en una comanda,
que se reparte por estaciones (plancha, barra, postres…) en la pantalla y en papel. Cada estación marca sus platos
listos, el pase entrega lo terminado y queda un historial de lo que pasó. Cocina no cobra, no descuenta stock y no
sabe de mesas ni de clientes: pinta e imprime la etiqueta que le da la cuenta.

- **Estado**: completa (2026-10-21): 30 de sus 31 flujos, `KITCHEN-F01` … `F31`, están `hecho`, y `KITCHEN-F30`
  está `descartado` con su motivo (la comanda no guarda cliente).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Estaciones y enrutado** (F01–F04): estaciones con color, destino («Pantalla y papel», «Solo pantalla», «Solo
  papel») e impresora por función o por nombre; cada producto o categoría de Inventario va a su estación y lo que no
  tiene estación sale en «Sin estación». Eliminar una estación la retira y libera su nombre.
- **La ronda llega** (F05–F09): la que envía el TPV, o la que Ventas envía sola por el relay del outbox, abre una
  comanda con el número del día, la ronda, la etiqueta, el tipo, la prioridad y quien atiende la cuenta; los platos
  de un menú van cada uno a su estación bajo la cabecera del menú, con sus suplementos y su nota; sale en papel una
  vez por impresora y se puede reimprimir como copia.
- **La pantalla** (F10–F17): tarjetas con semáforo verde, ámbar y rojo desde el envío, por estación o «Todas» (el
  pase); marcar listo por plato, por menú o por tarjeta, recuperar, entregar, marcar urgente (con aviso en papel),
  «Resumen» de lo que queda por cocinar, sonido al entrar una comanda y pase en papel al quedar lista.
- **Desde el TPV de Ventas** (F18–F20): «Enviar comanda (N)» con la llama de urgencia, la hoja «Comandas de la
  cuenta» con el estado de cada ronda, viva, y «Marcar urgente» desde allí.
- **La lista y el historial** (F21–F26): Comandas con búsqueda, filtros y páginas; lanzar, marcar lista, recuperar,
  servir, cancelar (con el vale «ANULADA · <etiqueta>» si salió en papel) y reimprimir; crear una comanda a mano y borrarla por el
  asistente o la API; el «Historial de cocina» con quién, plato y motivo; y los ajustes de la pantalla.
- **Lo que hace Ventas** (F27–F29, F31): cobrar la cuenta entera sirve las rondas listas (y, con la cocina en papel,
  las que nadie va a marcar); eliminar o unir una cuenta cancela o mueve sus rondas; anular un plato enviado lo tacha
  en la pantalla y saca su vale; Caja pregunta al cerrar qué comandas siguen sin servir.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:ticket-outline` (el viejo, `ion:restaurant-outline`, espera en `UI-REQUESTS.md`), categoría `restaurant`, gratuita (`premium = False`) |
| Verticales | `restaurant` (entra en su plantilla) |
| `requires` | `["sale", "inventory"]`: la comanda es una ronda de una cuenta de Ventas (lee `OrderLine`, sin clave ajena) y el enrutado apunta a `inventory.Product` y `inventory.Category` con clave ajena. Impresión es opcional: `printing.job.create` por nombre |
| Quién la usa | Ventas, en la pantalla «Vender»: `kitchen.ticket.send` al enviar (`useTill.ts`) y la hoja de la cuenta con `kitchen.ticket.by_order`, `kitchen.settings.get` y `kitchen.ticket.set_rush` (`KitchenTickets.vue`). Caja, al cerrar: `kitchen.ticket.board` (`CloseSessionForm.vue`). Ninguna app llama a Cocina desde su servidor; Menús y Suplementos no la llaman: sus datos llegan en las líneas de Ventas |
| Usa de otras apps | Ventas: `sale.order.fire` (el envío) y sus modelos de cuenta y línea. Impresión: `printing.job.create` (documento `kitchen_order`). Inventario: `held` (retiene producto y categoría al enrutar) y, en las páginas, `inventory.product.list` e `inventory.category.list` |
| Pantallas | `/kitchen/display`, `/kitchen/tickets`, `/kitchen/stations`, `/kitchen/history`, `/kitchen/settings`; la pestaña «Comanda actual» y la hoja «Comandas de la cuenta» del TPV las monta Ventas |
| Operaciones | 9 consultas (`queries.py`) y 20 acciones (`services.py`), todas con `ai=`; 27 rutas en `/api/kitchen/…` (`kitchen.ticket.receive` y `kitchen.ticket.sync`, del sistema, no tienen ruta) |
| Eventos | 18, `kitchen.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `sale.order.fired` (`kitchen.ticket.receive`) y a `sale.order.completed`, `sale.order.voided` y `sale.order.line_voided` (`kitchen.ticket.sync`), por el relay del outbox |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial`, `0002_settings_row`, `0003_ticket_printed_at`, `0004_item_options_and_menu` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18); eliminar una estación entra en la misma fila que las escrituras de Cocina |

Las decisiones de diseño (asentar lo que hizo Ventas en cada lectura y escritura, el id de la comanda = el de su
primera línea, el número del día, el papel en un savepoint, la concurrencia) están en «Para quien lo mantiene» del
WORKBOOK; las de la migración, en la ronda 2026-10-21 (CLOSE-KITCHEN) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/kitchen apps/sale/tests/test_services_order.py
pnpm test apps/kitchen apps/sale/frontend/components/pos apps/cash_register/frontend/components/CloseSessionForm.test.ts
pnpm e2e tests/e2e/kitchen-*.spec.ts tests/e2e/printing-kitchen.spec.ts
```

- `test_integration_sale.py`, `test_integration_inventory.py`, `test_integration_combo.py` y
  `test_integration_modifier.py` van contra las apps reales; `test_concurrency.py`, con hilos contra Postgres (dos
  envíos de la misma cuenta, eliminar una estación mientras se escribe).
- Las e2e de Cocina recorren el TPV, la pantalla, la lista, las estaciones, el historial y los ajustes; las de Ventas
  borran con `cleanSales` (`tests/e2e/sale-helpers.ts`) las comandas de las cuentas que limpian.

## Qué queda fuera

- Cursos con retener y lanzar (kitchen#71), vaciar de golpe lo cobrado antes de pasar a papel (kitchen#158) y los
  alérgenos de punta a punta (pm#115): «Lo que queda fuera» del WORKBOOK.
- Lo que sigue pedido a Ventas: el aviso propio del cambio de título y dos índices parciales («Lo que pide a otras
  apps» del WORKBOOK).
- Los iconos, los composables compartidos y el selector de color de [`UI-REQUESTS.md`](UI-REQUESTS.md).
