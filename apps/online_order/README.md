# Pedidos online (`online_order`)

El cliente sentado a la mesa pide desde su móvil con el QR de la mesa, y el pedido llega a la cuenta de la mesa y a
cocina; el cobro sigue en el TPV.

- **Estado**: en construcción. Hoy, cada mesa tiene su código, se genera y se regenera en pantalla, por la API y con
  el asistente, la hoja de QR se imprime y el QR de cada mesa abre su carta en el móvil del cliente (`ONLINE_ORDER-F01`,
  `F02` y `F03`, hechos); el pedido llega después.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:qr-code-outline`, categoría `restaurant`, gratuita (`premium = False`), fuera de la tienda (`listed = False`) hasta que el cliente pueda pedir: un QR impreso no puede abrir una página que aún no existe |
| Verticales | ninguna: no viene en ninguna plantilla; el negocio la enciende cuando quiere que sus clientes pidan solos |
| `requires` | `table` (con Mesas llegan Ventas y Clientes) e `inventory`; lee las mesas con `table.table.list` y `table.table.get`, y la carta con las lecturas de Inventario y, si están encendidas, de Suplementos y Menús |
| Permisos | `online_order.view_qr_code` y `online_order.change_qr_code` (propietario, administrador y responsable; el empleado, ninguno); `online_order.public`, el de la página de la mesa, que la puerta pública da a quien la abre sin sesión |
| Pantallas | **Códigos QR** (`/online_order/qr-codes`, `frontend/pages/QrCodesPage.vue`): la lista, la hoja que se imprime (`frontend/components/QrSheet.vue`, con el QR dibujado en el navegador) y generar o regenerar por mesa. **Página de la mesa** (`/p/<negocio>/order/<código>`, `frontend/pages/TableMenuPage.vue` y `frontend/components/TableMenu.vue`), sin sesión: la carta con la mesa y su zona, y el pedido que se arma en ella (`DishSheet.vue`, `ChoicePicker.vue` y `BasketSheet.vue`) y se envía |
| Operaciones | 3 consultas (`queries.py`: `qr_code.list`, con `ai=` y abierta a las claves de API; `public.menu` y `public.options`, las de la página de la mesa, solo por la puerta pública y sin `ai=`) y 2 acciones (`services.py`: `qr_code.regenerate`, `risk = "high"`, con `ai=` y abierta a las claves de API; `public.send`, el pedido que envía la página de la mesa, solo por la puerta pública y sin `ai=`); 2 rutas en `/api/online_order/qr_codes…` |
| Eventos | 2 (`events.py`): `online_order.qr_code.regenerated`, con el id de la mesa y nunca el código, y `online_order.order.sent`, con el pedido, la mesa y su total; no escucha a nadie |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` (los códigos de las mesas) y `0002_order` (los pedidos y sus líneas) |
| Admin | Django admin de solo lectura sobre los códigos en `hubs.erplora.com`: un código solo cambia regenerándolo |

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/online_order
```
