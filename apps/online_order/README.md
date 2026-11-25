# Pedidos online (`online_order`)

El cliente sentado a la mesa pide desde su móvil con el QR de la mesa, y el pedido llega a la cuenta de la mesa y a
cocina; el cobro sigue en el TPV.

- **Estado**: en construcción. Hoy, cada mesa tiene su código y se regenera por la API y con el asistente
  (`ONLINE_ORDER-F01` y `F02`, parciales); la hoja de QR, la carta pública y el pedido llegan después.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:qr-code-outline`, categoría `restaurant`, gratuita (`premium = False`), en la tienda |
| Verticales | ninguna: está en la tienda y no viene en ninguna plantilla |
| `requires` | `table` (con Mesas llegan Ventas y Clientes); lee las mesas con `table.table.list` y `table.table.get` |
| Permisos | `online_order.view_qr_code` y `online_order.change_qr_code` (propietario, administrador y responsable; el empleado, ninguno) |
| Pantallas | ninguna todavía |
| Operaciones | 1 consultas (`queries.py`: `qr_code.list`) y 1 acciones (`services.py`: `qr_code.regenerate`, `risk = "high"`), las dos con `ai=` y abiertas a las claves de API; 2 rutas en `/api/online_order/qr_codes…` |
| Eventos | 1, `online_order.qr_code.regenerated` (`events.py`), con el id de la mesa y nunca el código; no escucha a nadie |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin de solo lectura sobre los códigos en `hubs.erplora.com`: un código solo cambia regenerándolo |

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/online_order
```
