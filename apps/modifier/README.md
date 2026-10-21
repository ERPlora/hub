# Suplementos (`modifier`)

El catálogo de las elecciones que acompañan a un plato: el punto de la carne, el extra de queso, el tamaño, «sin
cebolla». Se ordena en grupos (mínimo, máximo y si una opción se repite), cada opción con su suplemento (más, menos o
gratis), su opción por defecto y, si tributa distinto del plato, su categoría fiscal propia; un grupo se engancha a
productos o a categorías de Inventario y se comparte. Suplementos dice qué grupos lleva cada artículo y es la única
fuente del precio del suplemento; Ventas los pregunta en el TPV y los cobra, y Cocina los pinta en la comanda.

- **Estado**: completa (2026-10-21): los 9 flujos, `MODIFIER-F01` … `F09`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **El catálogo** (F01–F05): la tabla de grupos con buscador, orden y filtros (nombre, obligatorio u opcional);
  crear, cambiar y borrar un grupo (nombre único sin mirar mayúsculas, mínimo y máximo entre 0 y 50, repetición y
  orden); en la hoja del grupo, sus opciones (suplemento con signo, nombre de comanda, categoría fiscal propia,
  elegida por defecto; hasta 100 por grupo) y los productos o categorías a los que se aplica.
- **En el TPV** (F06–F07, con Ventas): al tocar un artículo, la hoja pregunta sus grupos y los de todas sus
  categorías, una vez cada uno, con su regla y las opciones por defecto marcadas; al añadir la línea, Suplementos
  comprueba y valora lo elegido con la sesión de quien vende (mínimo, máximo, repetición, que el plato no baje de
  cero y que un artículo a peso no lleve suplemento con precio) y Ventas lo congela. Una opción con otra categoría
  fiscal se cobra en su línea hija, por cada plato, y el IVA cuadra al céntimo.
- **En cocina** (F08): el nombre de comanda de cada opción, en el orden elegido, llega con la ronda y Cocina lo pinta
  en la tarjeta y en el papel; renombrar o borrar después no reescribe lo pedido.
- **Bajas** (F09, por el relay del outbox): un producto o una categoría borrados en Inventario sueltan sus grupos por
  la reacción a `inventory.product.deleted` e `inventory.category.deleted`; hasta entonces, ese enganche ya no se ve
  ni se pregunta.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `lucide:sliders-horizontal` (el viejo, `ion:options-outline`, espera en `UI-REQUESTS.md`), categoría `catalog`, gratuita (`premium = False`) |
| Verticales | `restaurant` (entra en su plantilla; la de peluquería no la lleva) |
| `requires` | `["inventory", "tax"]`: un enganche es FK a `inventory.Product` o `inventory.Category` (`CASCADE`), y la categoría fiscal propia, a `tax.TaxCategory` (`PROTECT`). No se engancha a servicios de Servicios |
| Quién la usa | Ventas la llama por nombre (`modifier.group.for_target` y `modifier.selection.resolve`) sin requerirla, solo con Suplementos encendida; Cocina no la llama: lee lo que Ventas congela en la línea |
| Pantallas | `/modifier/groups` (la tabla) y la hoja del grupo en un `ion-modal`, sin URL propia; la hoja del TPV es de Ventas |
| Operaciones | 6 consultas (`queries.py`) y 10 acciones (`services.py`), todas con `ai=`; 14 rutas en `/api/modifier/…` (`modifier.link.drop_product` y `drop_category`, las reacciones de sistema, no tienen ruta) |
| Eventos | 8, `modifier.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `inventory.product.deleted` y `inventory.category.deleted`, por el relay del outbox |
| Migraciones | `0001_initial` (depende de `inventory 0001` y `tax 0005`) |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (unicidad y reglas en la base de datos, la valoración como única puerta del precio, los
bloqueos y el contrato con Ventas y con Cocina) están en «Para quien lo mantiene» del WORKBOOK; las de la migración,
en la ronda 2026-10-21 (CLOSE-MODIFIER) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/modifier apps/sale/tests/test_integration_modifier.py \
  apps/kitchen/tests/test_integration_modifier.py
pnpm test apps/modifier
pnpm e2e tests/e2e/modifier-groups.spec.ts tests/e2e/modifier-till.spec.ts
```

- `tests/test_integration_sale.py` va contra Ventas real (lo que pregunta el TPV, descuento, repetido, plato a peso,
  IVA al céntimo y el empleado con su sesión); `test_integration_kitchen.py`, de Ventas a Cocina por un tick real del
  relay; `test_integration_inventory.py` y `test_integration_tax.py`, contra Inventario e Impuestos reales;
  `test_relay.py`, F09 por el tick real del worker y con dos negocios; `test_concurrency.py`, con escrituras a la
  vez en hilos.
- `modifier-groups.spec.ts` recorre la tabla y la hoja (F01–F05); `modifier-till.spec.ts`, el TPV, el cobro, la
  pantalla de cocina y el borrado en Inventario de verdad (F06–F09). Los dos, en 390, 834 y 1440.

## Qué queda fuera

- Variantes, stock o coste por opción, menús a precio cerrado y pintar la hoja del TPV o la comanda: «Lo que NO
  hace, a propósito» del WORKBOOK (lo pintan Ventas y Cocina).
- Suplementos de un servicio (peluquería), «agotado» por opción, activar o desactivar un grupo sin borrarlo y un
  precio de la opción distinto por producto: «Lo que queda fuera» del WORKBOOK.
- El icono y los componentes compartidos de [`UI-REQUESTS.md`](UI-REQUESTS.md).
