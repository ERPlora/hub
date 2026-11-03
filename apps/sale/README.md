# Ventas / TPV (`sale`)

La **caja registradora** del negocio: se monta la cuenta tocando artículos, se cobra en efectivo, con tarjeta o
repartido entre varios medios, y queda una **venta que ya no cambia**, con su número del día, su IVA línea a línea
y su tique o su factura. Sirve al restaurante (cuentas abiertas por mesa, comanda a cocina, precuenta, cobrar por
partes, dividir y juntar) y a la peluquería (cada servicio con su profesional, la cita cobrada sin volver a
teclearla y la línea pagada con un bono).

- **Estado**: completa (2026-10-31): los 38 flujos `SALE-F01` … `F38` están `hecho`. Del registro de la migración,
  el «86» del QA viejo (SALE-G05) queda cubierto por F07 con INVENTORY-F29 y la propina (SALE-G06) está
  `descartado` con su issue (hub#562; ver «Qué queda fuera»).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Vender y cobrar** (F01–F08): la rejilla del catálogo de Inventario (con lo agotado en gris) y el buscador; la
  hoja **Cobro** con efectivo y cambio, tarjeta u otro medio, cobro repartido, tique o factura con los datos del
  cliente, cliente obligatorio, el reintento que nunca cobra dos veces y el cierre de caja de Caja. Los límites de
  España (tique hasta 3.000 €, efectivo por debajo de 1.000 €) solo en un negocio de España.
- **Montar la cuenta** (F09–F18): precio libre por sección, venta por peso, suplementos, menús, notas, descuentos
  (los de por encima del máximo, con la aprobación de un responsable), invitaciones, quién atiende, aparcar y
  recuperar, y eliminar una cuenta.
- **Sala y cocina** (F19–F25): sentar la cuenta en una mesa, enviar la comanda por rondas (urgente con la llama),
  anular un plato enviado con motivo, precuenta, cobrar solo unas líneas; dividir, juntar y trasladar las hacen los
  botones de Mesas con las operaciones de Ventas.
- **Peluquería** (F26, F27, F32, F38): cobrar la cita al precio reservado, vender servicios al precio de la
  profesional, pagar una línea con un bono y devolver su sesión.
- **Historial y correcciones** (F28–F33): la lista de ventas con sus cifras y los paneles del Inicio, el documento
  con su QR fiscal y «Emitir ahora», anular una venta (rectificativa R5 de Facturación en la misma anulación),
  devolver toda, una parte o por otro medio, y unir las ventas de dos fichas.
- **Ajustes** (F34–F37): los del TPV, las secciones del precio libre, las notas rápidas y los medios de pago
  (Bizum o transferencia, por el asistente).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:cart-outline`, categoría `sales`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `["tax", "customer"]` |
| Usa de otras apps | por nombre y sin requisito: el catálogo de Inventario, los grupos de Suplementos, los menús de Menús y combos, los servicios, asignaciones y sesiones de bono de Servicios, el documento fiscal de Facturación, la sesión de Caja, las mesas de Mesas, la cita de Citas y el equipo de Personal; sin la app, su parte no aparece o se rechaza con su motivo |
| Quién la lee | Inventario y Clientes (avisos de venta cobrada, anulada y devuelta), Facturación (la requiere: venta, líneas y devoluciones), Caja (la requiere: las ventas de cada turno), Cocina (las comandas), Mesas y Citas (abren y mueven cuentas con sus operaciones) |
| Pantallas | `/sale/pos`, `/sale/sales`, `/sale/quick-notes`, `/sale/departments` y `/sale/settings` |
| Inicio | los paneles «Ventas hoy», «Tickets hoy», «Ventas últimos 7 días» y «Actividad reciente» |
| Operaciones | 19 consultas (`queries.py`) y 40 acciones (`services.py`), todas con `ai=`; 57 con ruta en `/api/sale/…` (`sale.customer.reassign` y `sale.sale.record_invoice` no tienen ruta: son las reacciones, solo el sistema) |
| Eventos | 22 propios (`sale.sale.*`, `sale.order.*`, `sale.payment_method.created`, `sale.settings.updated`, `sale.department.*` y `sale.quick_note.*`; `events.py`); reacciona a `customer.customer.merged` y a `invoice.invoice.issued` |
| Migraciones | `0001_initial` … `0013_order_merged_into` |
| Admin | Django admin en `hubs.erplora.com`: medios de pago, ajustes, secciones, notas rápidas y las cuentas abiertas con sus líneas editables; las ventas, sus líneas, sus cobros y el contador del día en solo lectura, sin alta ni borrado (de la venta, solo las notas) |

Las decisiones de diseño (la cuenta cobra al precio con que se pidió, la venta no cambia, el número del día con
`UPDATE … RETURNING`, la aprobación del responsable con su PIN, el reparto de las devoluciones por profesional…)
están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda de cierre de Ventas de
`PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/sale
pnpm test apps/sale
CI=1 pnpm e2e tests/e2e/sale-pos.spec.ts tests/e2e/sale-sales.spec.ts tests/e2e/sale-till-flows.spec.ts
```

- Los `test_integration_*.py` van contra las apps reales (Inventario, Clientes, Impuestos, Facturación, Caja,
  Servicios, Suplementos, Menús, Mesas, Citas, Personal, Impresión, el asistente y el Inicio);
  `test_concurrency.py`, el cobro y la numeración con hilos.
- 22 specs `tests/e2e/sale-*.spec.ts` (TPV, cobro, cocina, mesa, bono, documento pendiente, QR fiscal, agotado,
  hablar, aprobaciones, moneda del negocio…).
- Nunca hay red real de la AEAT: VeriFactu solo en el entorno de pruebas (working-rules §15).

## Qué queda fuera

- **hub#562** — El cobro del TPV no deja añadir propina (SALE-G06): cruza Ventas y Caja y la propina nunca entra
  en la base ni el IVA del tique; el producto la aplazó tras el MVP.
- **hub#558**, **hub#560** y **hub#561** — fallos vistos en la migración: dos pruebas del precio libre que fallan
  por tiempo con la máquina cargada, seis textos en español con las palabras de otra app y la tarjeta del asistente
  que no dice qué registro toca una escritura de Ventas.
- **hub#442** — el aviso de agotado se queda en el TPV tras volver a poner el artículo a la venta (en la cadena de
  arreglos de Ventas).
- Lo que no hace a propósito (mesas y clientes en la cuenta, numerar facturas, hablar con la AEAT, el datáfono o la
  báscula, comensal por línea, reabrir una venta cobrada…) y lo demás que queda fuera: «Lo que NO hace, a
  propósito» y «Lo que queda fuera» del WORKBOOK.
