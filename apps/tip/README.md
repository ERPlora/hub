# Propinas (`tip`)

La propina que el cliente deja al pagar, con tarjeta o en efectivo, guardada aparte de la venta con **de quién es**.
La propina no es una venta: no lleva IVA, no cambia el tique y no llega a la AEAT. La de efectivo entra en el cajón y
la caja la enseña en su propia línea.

- **Estado**: parcial, en la tienda y en las plantillas de restaurante y peluquería. La hoja Cobro propone la propina y
  la anota con su venta en un cobro de una sola forma de pago; la pantalla **Propinas** anota, ajusta, anula y echa al
  bote, y **Ajustes** guarda las sugerencias; el **Informe** da las propinas por persona y por turno y cada empleado ve
  las suyas en **Mis propinas** (TIP-F01, F03, F05, F06, F13 y F14 hechos); faltan la propina de cada cobro al
  repartir, «Quédese el cambio» y el reparto.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta «Para quien
  lo mantiene»). Lo que se cambie de la app se cambia antes allí.

## Qué hace hoy

- **El paso del cobro** (F02): la fila «Propina» de la hoja Cobro de Ventas (`frontend/components/TipStep.vue`, que
  Ventas monta por su nombre porque `apps.py` lo declara en `checkout`): «Sin propina», las tres sugerencias de la forma
  de pago con su importe (`tip.suggestion.get`, sobre el total antes de descuentos) y «Otra cantidad». Cobrada la
  venta, la anota con ella (`tip.tip.add`) con la clave del intento del cobro y la posición de su cobro.
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
- **El informe** (F13, `tip.report.get`): las propinas activas de un periodo, con tarjeta, en efectivo y de otras
  formas, por persona (las sin asignar y las del bote, al final) o por jornada fichada en Control horario, que se lee
  por su nombre (`attendance.record.list`) si está activo; las anotadas fuera de toda jornada, en una línea aparte.
- **Mis propinas** (F14, `tip.report.mine`): las de la ficha de Personal de quien pregunta, de hoy y de la semana
  (desde el lunes); sin ficha, 409 `tip.member_not_linked`.
- **Las pantallas** (`frontend/`): **Propinas** (`pages/TipsPage.vue`: el periodo, la tabla o las tarjetas, «Anotar
  propina», «Ajustar» y «Anular»), **Informe** (`pages/ReportPage.vue`: el periodo, por persona o por turno, las cifras
  y «Exportar» en CSV) y **Ajustes** (`pages/SettingsPage.vue`), en el menú de quien gestiona (`tip.manage`; los
  cambios de los ajustes, solo con `tip.manage_settings`), y **Mis propinas** (`pages/MyTipsPage.vue`), en el de
  quien ve propinas (`tip.view_tip`).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:wallet-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales y tienda | `hair_salon` y `restaurant`, en la tienda |
| `requires` | `sale` (la venta y su forma de pago), `cash_register` (el cajón) y `staff` (de quién es) |
| Operaciones | 6 consultas (`queries.py`) y 6 acciones (`services/`), todas con `ai=`; 10 rutas en `/api/tip/…` (sin ruta: `tip.sale.void` y `tip.sale.refund`, las reacciones a Ventas) |
| Paso del cobro | `checkout = [CheckoutStep(key="tip", component="TipStep", permission="tip.add_tip")]` |
| Eventos | 4, `tip.settings.updated` y `tip.tip.{added,adjusted,voided}` (`events.py`); reacciona a `sale.sale.voided` y `sale.sale.refunded` |
| Tarea programada | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin de propinas y ajustes en `hubs.erplora.com` |

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/tip
```
