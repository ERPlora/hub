# Propinas (`tip`)

La propina que el cliente deja al pagar, con tarjeta o en efectivo, guardada aparte de la venta con **de quién es**.
La propina no es una venta: no lleva IVA, no cambia el tique y no llega a la AEAT. La de efectivo entra en el cajón y
la caja la enseña en su propia línea.

- **Estado**: parcial, fuera de la tienda y de las plantillas hasta que tenga sus pantallas. Hoy una propina se anota, se ajusta y se anula por la API y el asistente, y sale aparte en la
  caja (TIP-F01, F03 a F06 en `parcial`); faltan las pantallas, el paso del cobro, el informe, «Mis propinas» y el
  reparto.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta «Para quien
  lo mantiene»). Lo que se cambie de la app se cambia antes allí.

## Qué hace hoy

- **Ajustes** (F01): pedir propina al cobrar (apagado de fábrica), la sugerencia marcada, «Otra cantidad» y tres
  sugerencias por forma de pago de Ventas, en porcentaje o en importe (3 %, 5 % y 10 % de fábrica).
- **Anotar** (F03 a F05): una propina sobre su venta, por su id o su número, con su forma de pago, para quien atendió
  la venta salvo que se diga otra persona del equipo; o al bote, en efectivo, sin venta ni persona. La misma clave del
  intento del cobro la anota una sola vez.
- **La caja**: cada propina se apunta en la sesión abierta (`cash_register.movement.add` con `app="tip"`). Con
  «Activar caja» encendido y la caja cerrada, la de efectivo se rechaza; con la caja apagada se guarda solo aquí.
- **Ajustar y anular** (F06): con su motivo; la diferencia entra o sale de la sesión abierta y una cerrada no se toca.
  Anular una venta o devolverla entera anula su propina sola.
- **La lista y una propina**: las más nuevas primero, con búsqueda por venta o persona y filtros; una propina se lee
  por su id o por el número de su venta (la activa). Un empleado ve solo las suyas.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:wallet-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales y tienda | ninguna vertical y fuera de la tienda (`listed = False`) hasta que tenga sus pantallas: entonces, `hair_salon` y `restaurant` |
| `requires` | `sale` (la venta y su forma de pago), `cash_register` (el cajón) y `staff` (de quién es) |
| Operaciones | 3 consultas (`queries.py`) y 6 acciones (`services/`), todas con `ai=`; 7 rutas en `/api/tip/…` (sin ruta: `tip.sale.void` y `tip.sale.refund`, las reacciones a Ventas) |
| Eventos | 4, `tip.settings.updated` y `tip.tip.{added,adjusted,voided}` (`events.py`); reacciona a `sale.sale.voided` y `sale.sale.refunded` |
| Tarea programada | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin de propinas y ajustes en `hubs.erplora.com` |

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/tip
```
