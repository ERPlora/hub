# Inventario (`inventory`)

El **catálogo con su stock**: cada producto con su SKU, su precio, su coste, su categoría fiscal, su unidad de
medida, su foto y cuántas unidades quedan. El TPV vende de este catálogo y cada venta baja el stock sola; las
recepciones, los recuentos y las bajas dejan un movimiento que nunca se edita, así que cada saldo se explica.
Avisa cuando un artículo baja de su mínimo, importa y exporta el catálogo en CSV y vende al peso o por medida
sin redondear. Es la carta del restaurante y los productos de venta de la peluquería.

- **Estado**: completa (2026-10-31): los 33 flujos `INVENTORY-F01` … `F33` están `hecho`. INVENTORY-F12 (cargar
  la carta de una plantilla del sector) se cerró al cerrar la app: la plantilla la carga la plataforma desde
  Ajustes › Datos y copias, y Inventario la recibe por su alta en lote.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Catálogo** (F01–F08, F29): alta, edición, activar y desactivar, eliminar (el SKU y el EAN-13 quedan libres;
  los movimientos se conservan), los productos «Sin configurar» por falta de categoría fiscal, las categorías del
  TPV y la marca «Agotado» que pone y quita una persona.
- **Importar y exportar** (F09–F12): productos y categorías desde un CSV con ensayo previo, columnas adivinadas
  y la ventana de categorías fiscales; exportar el catálogo tal como se vuelve a importar; y la carta de una
  plantilla del sector (restaurante o peluquería), que salta los SKU que ya existen.
- **Stock** (F13–F20): recibir mercancía con su coste, contar, dar de baja con motivo, el historial de
  movimientos, el panel con stock bajo, el aviso al cruzar el mínimo, los ajustes (controlar stock, vender sin
  stock, umbral) y qué artículos llevan control de stock.
- **Con otras apps** (F21–F28): bajar el stock al cobrarse una venta (también los componentes de un menú o un
  pack), reponerlo al anularse o devolverse, la etiqueta del código de barras por Impresión, vender al peso o por
  medida, entregar el catálogo al TPV, a Cocina y a Menús, y el paso «Tu catálogo» del Inicio.
- **Foto del artículo** (F30–F33): elegirla de la librería de ERPlora o subir una propia (WebP de 512 × 512 en la
  carpeta del negocio), verla en el TPV y que viaje en las copias y plantillas.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:cube-outline`, categoría `catalog`, gratuita (`premium = False`) |
| Verticales | `restaurant`; la plantilla de peluquería la activa con sus productos de venta |
| `requires` | `["tax"]` |
| Usa de otras apps | las categorías fiscales de Impuestos; la moneda del negocio (`base.business.get`); la librería de imágenes y las fotos propias de la plataforma (`base.images`); por nombre y sin requisito, `printing.job.create` para la etiqueta |
| Quién la lee | Ventas (catálogo de venta y bajada de stock), Cocina, Menús y combos, Modificadores, Tarifas, Caja, Facturación, Clientes, Personal, Mesas, Impresión, Web, Automatizaciones y VeriFactu; la plataforma (plantillas, copias, Inicio) |
| Pantallas | `/inventory/dashboard`, `/inventory/products`, `/inventory/movements`, `/inventory/categories` y `/inventory/settings` |
| Inicio | el paso «Tu catálogo» (`inventory.stock.get_summary`, obligatorio) y cuatro paneles: stock bajo, valor del stock a coste, productos con stock y los de menos stock |
| Operaciones | 13 consultas (`queries.py`) y 21 acciones (`services.py`), todas con `ai=`; 31 rutas en `/api/inventory/…` |
| Eventos | 11, `inventory.product.{created,updated,deleted,categorized,uncategorized}`, `inventory.category.{created,updated,deleted}`, `inventory.stock.{changed,threshold_crossed}` e `inventory.config.updated` (`events.py`); reacciona a `sale.sale.completed`, `sale.sale.voided` y `sale.sale.refunded` |
| Migraciones | `0001_initial` … `0005_product_image` |
| Admin | Django admin en `hubs.erplora.com`, con todas las tablas editables para soporte: avisa, no impide (no pasa por las reglas de las operaciones); los ids y las fechas, solo lectura |

Las decisiones de diseño (el libro de movimientos que nunca se edita, la anulación y la devolución que reponen
una sola vez, el SKU que se libera al eliminar…) están en «Para quien lo mantiene» del WORKBOOK; las de la
migración, en la ronda de cierre de Inventario de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/inventory
pnpm test apps/inventory
CI=1 pnpm e2e tests/e2e/inventory-products.spec.ts tests/e2e/inventory-flows.spec.ts tests/e2e/inventory-stock.spec.ts
```

- `test_integration_tax.py`, `test_integration_printing.py`, `test_integration_home.py` y
  `test_integration_assistant.py` van contra las apps reales; `test_relay.py`, por el tick real del relay del
  outbox; `test_concurrency.py`, con hilos.
- Además de las tres de arriba: `inventory-import`, `inventory-photo`, `inventory-sold-out`, `inventory-employee`,
  `inventory-template` (la carta de la plantilla del restaurante, F12) y `fix-inventory-setup-hooks`.
- La carga de las plantillas la prueba también `base/tests/test_blueprint.py` (cada semilla entra entera en un
  negocio vacío).

## Qué queda fuera

- **hub#525** — Los importes de cuatro cifras salen sin separador de millares («1234,56 €»).
- **hub#526** — La tarjeta de confirmación del asistente no dice qué registro toca una escritura.
- Lo que no hace a propósito (almacenes, lotes, recetas, variantes, cobrar…): «Lo que NO hace, a propósito» del
  WORKBOOK.
- Las peticiones de [`UI-REQUESTS.md`](UI-REQUESTS.md).
