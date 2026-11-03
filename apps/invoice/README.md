# Facturación (`invoice`)

Convierte cada venta cobrada en un **documento fiscal numerado** y lo guarda para siempre: el tique (factura
simplificada, F2) de cada cobro, la factura completa (F1) cuando el cliente da su NIF, la factura completa que
sustituye a un tique (F3) y la rectificativa (R1–R5) de cada devolución, anulación o corrección. Es el eslabón
entre Ventas y VeriFactu en la cadena fiscal española: aquí nace el número de serie que luego viaja a la AEAT.
Sirve igual al restaurante y a la peluquería.

- **Estado**: completa (2026-10-31): 20 de los 23 flujos `INVOICE-F01` … `F23` están `hecho`; F04, F22 y F23,
  `descartado` con su motivo y su issue (hub#500, hub#501 y hub#502; ver «Qué queda fuera»).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Emitir al cobrar** (F01, F02, F06): Ventas pide el tique o la factura completa dentro del mismo cobro; si no
  se puede (sin emisor, sin permiso, importes que no cuadran), cobra igual y el documento queda «pendiente», con
  reintentos del hub y «Emitir ahora». Una factura por venta, nunca dos números.
- **Emitir a mano y sustituir** (F03, F05): la factura manual con el impuesto del territorio fiscal del negocio
  (IVA, IGIC o IPSI) y la F3 que sustituye a un tique desde su ficha.
- **Rectificar** (F07–F10): la rectificativa de una anulación (R5 del tique entero), de una devolución entera o
  por diferencias de una parcial (una línea por clave fiscal), y la rectificación a mano (R1–R4) desde la ventana
  o el asistente, con vista previa y confirmación.
- **Numerar** (F11–F15): series por código y año (`TICKET`, `FACT`, `RECT`) que nacen solas, con prefijo, formato
  y siguiente número que se bloquean con el primer documento; numeración con `UPDATE … RETURNING` en la misma
  transacción, sin huecos, y el paso «Tu numeración de facturas» del Inicio.
- **Consultar, imprimir y cobrar** (F16–F20): lista paginada viva con búsqueda y filtros, ficha con el
  «Justificante VeriFactu», A4 por la impresora del sistema o el diálogo del navegador (nunca sin su QR), «Marcar
  pagada» y la factura vigente de una venta para otras apps.
- **El emisor** (F21): la identidad fiscal del negocio, obligatoria para emitir; el paso «Los datos de tu negocio»
  del Inicio y la franja «Todavía no puedes facturar» hasta que está.
- **Hub de plataforma** (F23, parte de Facturación): `invoice.invoice.issue_platform` y sus consultas emiten las
  facturas de ERPlora que manda el SaaS por `/internal/platform/invoices`; el alta de ese hub con su BD propia
  queda fuera (hub#502).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:receipt-outline` (el del módulo actual, `document-text-outline`, está pedido en `UI-REQUESTS.md`), categoría `sales`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `["tax", "sale", "customer"]` |
| Usa de otras apps | la venta, sus líneas, devoluciones y anulación (filas de Ventas) y `sale.sale.record_invoice`; la regla fiscal congelada y `resolve_tax`/`tax_kind_of` de Impuestos; la ficha del cliente de Clientes; la moneda del negocio (`base.business.get`); por nombre y sin requisito, `printing.job.create` y `verifactu.record.by_invoice` |
| Quién la lee | VeriFactu (el aviso `invoice.invoice.issued` y la factura; `invoice.invoice.create` para su factura de prueba), Ventas (emite dentro de su cobro, anulación y devolución), Ventas e Impresión (`invoice.issuer.get`), la plataforma (los dos pasos del Inicio) |
| Pantallas | `/invoice/invoices` (y la ficha `/invoice/invoices/<id>`), `/invoice/series` y `/invoice/issuer` |
| Inicio | los pasos «Los datos de tu negocio» (`invoice.issuer.get`, `required=True`) y «Tu numeración de facturas» (`invoice.numbering.status`, recomendado) |
| Operaciones | 17 consultas (`queries.py`) y 13 acciones (`services.py`), todas con `ai=`; 25 con ruta en `/api/invoice/…` (`invoice.issuer.sync` y las cuatro del hub de plataforma no tienen ruta: solo el sistema) |
| Eventos | 6, `invoice.invoice.{issued,rectified,paid}`, `invoice.series.{created,updated}` e `invoice.issuer.updated` (`events.py`); reacciona a `sale.sale.completed`, `sale.sale.refunded` y `sale.sale.voided` |
| Migraciones | `0001_initial` … `0006_customer_id_type_choices` |
| Admin | Django admin en `hubs.erplora.com`: series y emisor editables; facturas y líneas en solo lectura, sin alta ni borrado (solo las notas) |

Las decisiones de diseño (el número se gasta al cobrar, el libro de números es la propia factura, la factura de
una venta se construye leyendo la venta, la rectificativa por diferencias…) están en «Para quien lo mantiene» del
WORKBOOK; las de la migración, en la ronda de cierre de Facturación de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/invoice
pnpm test apps/invoice
CI=1 pnpm e2e tests/e2e/invoice-sale.spec.ts tests/e2e/invoice-manual.spec.ts tests/e2e/invoice-series.spec.ts
```

- `test_integration_sale.py`, `test_integration_customer.py`, `test_integration_verifactu.py` y
  `test_integration_printing.py` van contra las apps reales; `test_relay.py`, por el tick real del relay del
  outbox; la numeración y «una por venta», con hilos.
- Además de las tres de arriba: `invoice-pending`, `invoice-assistant`, `invoice-locale-es`,
  `invoice-manual-tax-region`, `fix-invoice-setup-hooks` y `sale-invoice-chain`.
- Nunca hay red real de la AEAT: VeriFactu solo en el entorno de pruebas (working-rules §15).

## Qué queda fuera

- **hub#500** — El cliente no puede pedir él mismo la factura completa de su tique (INVOICE-F04).
- **hub#501** — El emisor de Facturación no se rellena con los datos fiscales de la cuenta de ERPlora (INVOICE-F22);
  choca con «Dos identidades» de PLAN-SAAS (los datos fiscales del negocio viven en el Hub): contradicción señalada,
  sin elegir.
- **hub#502** — ERPlora todavía no puede emitir sus propias facturas desde su hub de plataforma (INVOICE-F23).
- Lo que no hace a propósito (enviar a la AEAT, cobrar, presupuestos, vencimientos, el libro registro para la
  gestoría…): «Lo que NO hace, a propósito» del WORKBOOK.
- Los iconos y las piezas compartidas de [`UI-REQUESTS.md`](UI-REQUESTS.md).
