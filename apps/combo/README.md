# Menús y combos (`combo`)

Los artículos compuestos que se venden a precio cerrado: el menú del día, el menú infantil o el «bocadillo +
bebida» para llevar. Cada menú tiene platos (Primero, Segundo, Bebida…) con su mínimo y su máximo, y cada plato
ofrece elecciones, que son productos de Inventario con su suplemento. Menús dice lo que vale cada línea y cómo se
factura; Ventas la cobra, Inventario baja el stock de cada plato y Cocina recibe cada plato en su estación.

- **Estado**: completa (2026-10-21): los 13 flujos, `COMBO-F01` … `F13`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Montar los menús** (F01–F06): la lista con buscador, orden y filtros; el menú con su precio cerrado, su
  nombre de cocina, cómo se vende («en el local», una línea a su tipo de IVA, o «para llevar», repartido por
  plato) y si está a la venta; el constructor con sus platos (mínimo, máximo y repetición) y sus elecciones
  (una a una, varias de golpe o una categoría entera de Inventario), reordenables arrastrando o con subir y
  bajar, y un aviso que dice si el menú ya sale en el TPV o qué le falta.
- **Venderlos** (F07–F09, con Ventas): la hoja del TPV con todos los platos a la vez; el precio cerrado más
  cada suplemento (también el repetido y el negativo); una cuenta abierta cobra lo que se pidió aunque el menú
  suba de precio, se agote un plato o se retire; el IVA en una línea «en el local» o repartido por plato al
  céntimo «para llevar», con la cerveza o el vino del local al 21 % (`TAKEAWAY_CATEGORY`).
- **Lo que pasa después** (F10–F11, por el relay del outbox): Inventario baja el stock de cada plato elegido,
  nunca del menú, y lo repone al anular o devolver; Cocina pinta cada plato en su estación bajo el nombre de
  cocina del menú, en pantalla y en papel.
- **Agotados y bajas** (F12–F13): marcar una elección agotada (o que lo esté su producto en Inventario) la
  quita del TPV sin tocar el menú; un producto desactivado se marca y no se ofrece, y uno eliminado sale solo
  de todos los menús por la reacción a `inventory.product.deleted`.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:layers-outline` (el viejo, `ion:restaurant-outline`, espera en `UI-REQUESTS.md`), categoría `catalog`, gratuita (`premium = False`) |
| Verticales | `restaurant` (entra en su plantilla) |
| `requires` | `["inventory", "tax"]`: las elecciones son FK a `inventory.Product` y el menú «en el local», a `tax.TaxCategory`. No admite servicios de Servicios (los packs de peluquería son sus bonos) |
| Quién la usa | Ventas la llama por nombre (`combo.combo.resolve`, y la hoja del TPV lee `combo.combo.for_sale` en vivo) sin requerirla; Cocina e Inventario no la llaman: leen los componentes que Ventas pone en sus avisos |
| Pantallas | `/combo/menus` (lista) y `/combo/menus/:id` (constructor); la hoja del TPV es de Ventas |
| Operaciones | 4 consultas (`queries.py`) y 13 acciones (`services.py`), todas con `ai=`; 16 rutas en `/api/combo/…` (`combo.option.drop_product`, de la plataforma, no tiene ruta) |
| Eventos | 11, `combo.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `inventory.product.deleted` (`combo.option.drop_product`), por el relay del outbox |
| Migraciones | `0001_initial` (depende de `inventory 0001` y `tax 0005`) |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (concurrencia, cuándo sale un menú en el TPV, el reparto al céntimo, el riesgo de cada
operación para el asistente) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda
2026-10-21 (CLOSE-COMBO) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/combo apps/sale/tests/test_integration_combo.py \
  apps/kitchen/tests/test_integration_combo.py
pnpm test apps/combo apps/sale/frontend/components/pos
pnpm e2e tests/e2e/combo-menus.spec.ts tests/e2e/combo-till.spec.ts
```

- `tests/test_integration_sale.py` va contra Ventas real (precio, rechazos, cuenta abierta y reparto al
  céntimo); `test_integration_inventory.py` y `test_integration_tax.py`, contra Inventario e Impuestos reales;
  `test_relay.py`, por el tick real del worker (stock por plato, comanda por plato, producto eliminado y dos
  hubs); `test_concurrency.py`, con escrituras a la vez en hilos.
- `combo-menus.spec.ts` recorre la lista y el constructor (F01–F06, F12, F13) y una venta del menú
  (F07–F09); `combo-till.spec.ts`, el TPV, Cocina e Inventario de verdad (F07–F11). Los dos, en 390, 834 y
  1440.

## Qué queda fuera

- Horario del menú, elección por defecto y modificadores dentro de un plato, servicios de Servicios como
  elección y pintar en el constructor el reparto en euros de un menú «para llevar»: «Lo que NO hace, a
  propósito» del WORKBOOK.
- Marcar una cuenta «para llevar» en el TPV: es de Ventas; hasta entonces manda el ajuste del menú
  («Contradicciones señaladas» del WORKBOOK).
- Los iconos y los componentes compartidos de [`UI-REQUESTS.md`](UI-REQUESTS.md).
