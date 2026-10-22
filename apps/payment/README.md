# Pagos (`payment`)

El dinero que **sale** del negocio: lo que se paga a un proveedor, una transferencia o un reembolso que no
es de una venta. Cada pago lleva su referencia del día (`PAY-AAAAMMDD-NNNN`), sube por la escalera
Borrador → Aprobado → Enviado → Completado (o se cancela con su motivo) y guarda quién lo registró, quién
lo aprobó y cuándo pasó cada paso. Los métodos de pago son **desde dónde paga el negocio** (su cuenta, su
tarjeta de empresa, la caja), no las formas de cobro del TPV, que son de Ventas. No mueve dinero ni habla
con ningún banco.

- **Estado**: completa (2026-10-23): los 8 flujos, `PAYMENT-F01` … `F08`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Métodos** (F01, F08): crear, editar, desactivar y reactivar los métodos de pago (nombre único sin
  distinguir mayúsculas, tipo y cuenta); un método no se borra nunca y la cuenta sale tapada en las listas.
- **Pagos** (F02–F05): registrar un pago en borrador con su referencia del día (un reintento del mismo
  formulario no lo duplica), aprobarlo (permiso aparte), marcarlo como enviado y como completado, y
  cancelarlo con motivo mientras no esté terminado. Un paso fuera de orden se rechaza con su motivo y no
  avisa.
- **La lista** (F06): búsqueda por referencia, beneficiario o factura del proveedor, filtros de columna
  (fecha e importe por rango), orden y vista viva; un pago se lee entero por su referencia.
- **Los avisos** (F07): cada paso de un pago y cada cambio de un método deja su evento; Automatizaciones
  los ofrece como disparadores y corre una vez por aviso.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `lucide:send` (el `ion:send-outline` pedido espera en `UI-REQUESTS.md`), categoría `sales`, gratuita (`premium = False`) |
| Verticales | ninguna (`verticals = []`): no viene en ninguna plantilla; se enciende desde la tienda (`listed`) |
| `requires` | `[]`: no necesita ninguna app; las formas de cobro del TPV son de Ventas y aquí no se leen |
| Usa de otras apps | nada |
| Quién la lee | Automatizaciones: oye sus nueve avisos (FLOW-F21) y sus pasos pueden usar las consultas y las acciones sin riesgo alto (FLOW-F11: registrar un pago y crear, cambiar, desactivar o activar un método). Ninguna otra app |
| Pantallas | `/payment/payments` (Pagos) y `/payment/methods` (Métodos) |
| Operaciones | 4 consultas (`queries.py`) y 9 acciones (`services.py`), todas con `ai=` (`risk = "high"` en aprobar, enviar, completar y cancelar); 13 rutas en `/api/payment/…` |
| Eventos | 9, `payment.payment.{created,approved,sent,completed,cancelled}` y `payment.method.{created,updated,deactivated,activated}` (`events.py`); no reacciona a ninguno de otra app |
| Tarea programada | ninguna |
| Migraciones | `0001_initial`, `0002_payment_trail`, `0003_payment_idempotency_key` |
| Admin | Django admin con CRUD de métodos, pagos y contadores en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (Pagos no es Ventas, referencia con `UPDATE … RETURNING`, idempotencia del alta,
cuentas tapadas, rastro de la escalera) están en «Para quien lo mantiene» del WORKBOOK; las de la
migración, en la ronda 2026-10-23 (CLOSE-PAYMENT) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/payment
pnpm test apps/payment
CI=1 pnpm e2e tests/e2e/payment-flow.spec.ts
```

- `tests/test_integration_sale.py` va contra Ventas real (los dos catálogos no se mezclan); `test_relay.py`,
  por el tick real del relay del outbox hasta una automatización real de Automatizaciones, con dos hubs;
  `test_concurrency.py`, con hilos (referencias, aprobaciones, el mismo intento dos veces a la vez).
- `payment-flow.spec.ts` recorre los flujos con pantalla (F01–F06 y F08) en 390, 834 y 1440; F07 no tiene
  pantalla y su evidencia es `test_relay.py`.

## Qué queda fuera

- Lo que no hace a propósito (bancos, SEPA, conciliación, cobros de clientes, pagos parciales): «Lo que NO
  hace» del WORKBOOK.
- Los iconos y las piezas compartidas de [`UI-REQUESTS.md`](UI-REQUESTS.md).
