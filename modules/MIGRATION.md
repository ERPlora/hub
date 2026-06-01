# Migración de módulos legacy → hub-next

Fuente legacy: `../old_modules/m_*` (Python/hotframe, renombrado de `modules/` el 2026-05-31).
Destino: `modules/*` (declarativo `module.json` + SQL por dialecto + WASM Tier 2 opcional + WC Stencil).
Regla: **90% de la lógica en Rust** (runtime = autoridad); WASM solo para batch/line-items/fiscal.

## Lote POS — COMPLETO ✅

| Módulo | Ver | Tablas | Queries | Commands | Handler WASM (Tier 2) | E2E |
|--------|-----|--------|---------|----------|------------------------|-----|
| inventory | 1.0.14 | 5 | 5 | 13 | bulk_create, receive_stock, decrease_on_sale | 6/6 |
| customers | 2.2.10 | 9 | 7 | 23 | bulk_create, set_groups, set_tags | 6/6 |
| sales (kernel POS) | 2.4.9 | 7 | 5 | 6 | complete_sale (IVA/líneas/nº atómico) | 6/6 |
| invoice | 1.0.6 | 3 | 4 | 8 | create_invoice, create_from_sale | 5/5 |
| cash_register | 1.2.6 | 5 | 5 | 8 | add_count, record_sale | 5/5 |

**Cadena de eventos verificada (E2E real)**: una venta emite `sale.completed` con las líneas →
- `inventory.decrease_on_sale` (WASM) expande N líneas en N bajas de stock (salta servicios)
- `customers.record_purchase` sube stats + transición de lifecycle
- `invoice.create_from_sale` (WASM) auto-crea factura F2 TICKET con las líneas
- `cash_register.record_sale` (WASM) añade movimiento de caja a la sesión abierta

> **No hay módulo `pos` con datos**: el TPV es una vista de `sales` (m_pos.HAS_MODELS=False).

## Pendiente (resto del catálogo ~95 módulos)

Siguientes candidatos naturales (deps de POS o alta frecuencia): products(*ya en inventory*),
taxes, payments, orders, tables, kitchen. Cada uno se porta con el mismo patrón.

## Cosas que NO migran tal cual
- **Tier 1 (PDF/Excel/barcode)**: export CSV/Excel, barcode SVG → capacidades host del runtime (pendiente).
- **Middleware** (p.ej. cash_register protege la URL del POS): se reimplementa como guard del shell.
- **routes.py / templates Jinja**: reemplazados por WC Stencil + SDK.
