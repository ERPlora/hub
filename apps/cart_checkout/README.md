# Carrito y pago (`cart_checkout`)

Una libreta interna de carritos y pedidos: carritos de una persona (email y nombre) o de una visita anónima
(código de sesión), con sus líneas y totales, que se convierten en pedidos con número del día y un estado
que una persona marca (Iniciado, Pagado o Fallido, Completado). **No es el TPV y nada de lo que hace es
fiscal**: no cobra, no habla con ninguna pasarela y no crea venta, factura, registro VeriFactu, movimiento de
caja ni de stock. Para cobrar está Ventas.

- **Estado**: completa (2026-10-21): los 14 flujos, `CART_CHECKOUT-F01` … `F14`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Carritos** (F01, F05, F06): alta con sesión (única entre los no borrados), email, nombre, moneda (la
  del negocio si no se dice) y caducidad; abandonar uno activo y borrarlo (lógico: sus pedidos siguen y la
  sesión queda libre).
- **Líneas, por el asistente o la API** (F02, F03, F04): añadir, cambiar la cantidad (0 la quita), quitar y
  vaciar; producto y precio son texto y números libres, cantidades con tres decimales y totales redondeados
  al céntimo (la mitad hacia arriba), con topes de 1 000 000 unidades y 99 999 999 999,99 €.
- **Caducidad** (F07): un carrito vencido se lee como Expirado en el acto, y la tarea de cada 15 minutos lo
  guarda.
- **Pedidos** (F08–F11): iniciar desde un carrito activo con número `OS-AAAAMMDD-NNNN` sin huecos por día del
  negocio y el total congelado; marcar pagado, fallido (con motivo) o completado (convierte el carrito).
- **Consultar** (F12): las pantallas Carritos y Pedidos, con búsqueda, filtros por columna tras el embudo de la
  barra (el Total lee lo que se pega y avisa de lo ambiguo), orden, lista o tarjetas y 50 filas; líneas y
  detalle de un pedido, por el asistente o la API.
- **Avisos** (F13): trece eventos al outbox en la transacción del cambio; solo los escucha Automatizaciones
  (FLOW-F21).
- **Datos personales** (F14): borrar los de un cliente por su email exacto (asistente, API o acción del
  admin), en carritos (también borrados) y pedidos; quedan número, importes, estados y fechas.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `lucide:shopping-bag`, categoría `sales`, gratuita (`premium = False`), `listed = True` (en la Tienda; ver la contradicción con ADR-0380 en el WORKBOOK) |
| Verticales | ninguna (`verticals = []`): no entra en ninguna plantilla, se enciende desde la Tienda |
| `requires` | ninguno (`[]`): sin FK a Inventario ni a Clientes; nadie la requiere |
| Usa de otras apps | nada: no lee ni llama a ninguna |
| Pantallas | `/cart_checkout/carts`, `/cart_checkout/orders` (pestañas de `frontend/tabs.ts`) |
| Operaciones | 6 consultas (`queries.py`) y 13 acciones (`services.py`), todas con `ai=` (`risk = "high"` en borrar un carrito, marcar pagado, fallar y borrar los datos de un cliente); rutas en `/api/cart_checkout/…` |
| Eventos | 13, `cart_checkout.<entidad>.<hecho>` (`events.py`); sin `REACTIONS`: no escucha a nadie |
| Consultas vivas | las 6 consultas, re-ejecutadas tras el COMMIT de sus eventos (`live.py`) |
| Tarea programada | `expire_overdue_carts` → `cart_checkout.cart.cleanup_expired`, `*/15 * * * *`, `collapse` (la corre el worker; en la fase 1, sobre su ámbito fijo) |
| Permisos | `view_cart` (todos, también el empleado), `manage_cart` y `checkout` (responsable, administrador y propietario) |
| Migraciones | `0001_initial`, `0002_order_email_erasable` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) y la acción «Borrar los datos personales de sus clientes», que es la operación `cart_checkout.customer.erase` |

Las decisiones de diseño (libreta interna fuera de las plantillas, borrado lógico, caducidad leída,
numeración sin huecos, bloqueos de fila, referencias humanas para el asistente, topes) están en «Para quien
lo mantiene» del WORKBOOK; las de la migración, en la ronda 2026-10-21 (CLOSE-CART_CHECKOUT) de
`PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/cart_checkout
pnpm test apps/cart_checkout
pnpm e2e tests/e2e/cart-checkout-flows.spec.ts tests/e2e/cart-checkout-api.spec.ts \
  tests/e2e/cart-checkout-employee.spec.ts
```

- `tests/test_concurrency.py` va con hilos y sesiones reales (el primer pedido del día, dos personas sobre
  la misma fila); `tests/test_scheduled_expiry.py` corre la tarea por `base.scheduler` sin esperar al reloj.
- `cart-checkout-flows.spec.ts` recorre las pantallas en 390, 834 y 1440; `cart-checkout-api.spec.ts`, los
  flujos sin pantalla por la API real del Hub; `cart-checkout-employee.spec.ts`, el empleado que solo mira.

## Qué queda fuera

- El aviso al instante de un carrito que vence solo (F07): en la fase 1 la tarea corre sobre el ámbito del
  worker; llega con la tenencia de la fase 2.
- Los iconos propios y las piezas compartidas de [`UI-REQUESTS.md`](UI-REQUESTS.md).
- Tienda, pasarela, venta, factura, impuestos, envío, stock y enlace con Clientes: «Lo que NO hace, a
  propósito» del WORKBOOK. El canal online hacia Ventas (cart_checkout#12) sigue aplazado.
