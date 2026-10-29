# Impuestos (`tax`)

Qué impuesto lleva cada cosa que se vende: las categorías fiscales a las que apuntan productos, servicios,
secciones, menús y opciones de suplemento; las reglas que fijan el tipo de cada categoría por país, región y
fechas (IVA, IGIC o IPSI; sujeta, exenta, no sujeta o con inversión del sujeto pasivo; recargo de
equivalencia como componente); los alias que reconoce el importador de Inventario, y el territorio fiscal del
negocio. Ventas y Facturación calculan con ella cada línea; no fija precios ni habla con la AEAT.

- **Estado**: completa (2026-10-22): de sus 19 flujos, 17 están `hecho` y `TAX-F09` y `TAX-F10`,
  `descartado` con su motivo (ninguna puerta deja nacer la regla incoherente o solapada que reparaban).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Categorías y alias** (F01, F02, F13–F15): 11 categorías y 18 alias de fábrica, más las propias; el nombre
  de una de fábrica sale en el idioma de quien mira; un texto de fuera se reconoce por clave, nombre o alias.
- **Reglas** (F03–F08, F12): alta de una o hasta 100 de golpe (todo o nada), componentes de un nivel,
  calificación y causa de exención; un tipo se cambia con fecha de fin y regla nueva, nunca editando; dos
  reglas activas del mismo país, región y categoría nunca están vigentes el mismo día, tampoco si se guardan a
  la vez.
- **Territorio fiscal** (F11): todo el país, Canarias, Ceuta o Melilla en Impuestos → Ajustes; en esos
  territorios solo vale la regla del territorio, nunca el IVA nacional, y lo que no tiene regla se declara con
  el impuesto del territorio.
- **Cálculo y entrega** (F16–F19): el catálogo de España sembrado al crear las tablas, el aviso «Tus impuestos»
  (y su paso en «Termina de configurar tu negocio» del Inicio) y un único cálculo (`resolve_tax`/`calculate_tax`) que usan Ventas y Facturación dentro de su operación.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:calculator-outline`, categoría `sales`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` (entra en sus plantillas) |
| `requires` | `[]`: no depende de ninguna app ni reacciona a sus avisos |
| Usa de otras apps | nada; de la plataforma, la zona horaria (`timezone.localdate()`, en la fase 1 `settings.TIME_ZONE`) y `pycountry` para países y regiones |
| La usan | Inventario, Servicios, Ventas, Facturación, Menús y combos y Suplementos (todas la requieren); todas menos Facturación enlazan `TaxCategory` (`PROTECT`) y eligen la categoría con `tax.category.list`; de `queries.py`, Ventas importa `calculate_tax`, `current_rates`, `business_jurisdiction`, `business_tax_kind`, `business_today` y `category_by_reference`, Facturación `resolve_tax`, `resolve_category_text`, `tax_kind_of`, `business_tax_kind`, `round_half_up` y `split_amount` (y lee por id la regla que congeló cada línea, `TaxRule.objects.in_bulk`), Suplementos `resolve_category_text` y Servicios `held_categories`; Ventas y Facturación re-ejecutan sus consultas vivas con `RULE_EVENTS`; las pantallas de Ventas y Facturación leen `tax.settings.get` con `useTaxKind()`/`useTaxName()`; Inventario, además, `tax.alias.resolve`, `tax.alias.create` y `tax.category.create` al importar |
| Pantallas | `/tax/categories`, `/tax/rules`, `/tax/aliases` y `/tax/settings` |
| Operaciones | 10 consultas (`queries.py`) y 8 acciones (`services.py`), todas con `ai=`; 18 rutas en `/api/tax/…`; 7 consultas y acciones abiertas a las API keys (`expose_api`) |
| Eventos | 7, `tax.<entidad>.<hecho>` (`events.py`); `RULE_EVENTS` (las cuatro de reglas y el cambio de territorio) recalculan la caja de Ventas y el tipo general de Facturación; no reacciona a ninguno |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` a `0006_tax_settings`: `0002` siembra el catálogo de fábrica (con vuelta atrás), `0005` añade `retail.alcohol` sin reescribir ningún tipo y `0006` crea el territorio fiscal |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18); el territorio fiscal, por `tax.settings.update`, sin segunda fila ni borrado |

Las decisiones de diseño (la resolución única, el redondeo, el solape con bloqueo, la clave natural de la raíz,
la jurisdicción y el impuesto del territorio) están en «Para quien lo mantiene» del WORKBOOK; las de la
migración, en las rondas 2026-10-17 de `PLAN-HUB.md` §4 y en la ronda 2026-10-22 (CLOSE-TAX) de su §0 (raíz de
erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/tax
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/sale/tests/test_integration_tax.py apps/inventory/tests/test_integration_tax.py apps/service/tests/test_integration_tax.py apps/modifier/tests/test_integration_tax.py apps/invoice/tests/test_integration_sale.py
pnpm test apps/tax
pnpm e2e tests/e2e/tax-flows.spec.ts tests/e2e/tax-categories.spec.ts tests/e2e/tax-rules.spec.ts tests/e2e/tax-employee.spec.ts tests/e2e/tax-region-sale.spec.ts tests/e2e/tax-region-no-national-fallback.spec.ts \
  tests/e2e/fix-tax-setup-hooks.spec.ts
```

- `test_queries.py` prueba la resolución y el cálculo (región frente a país, territorios con impuesto propio,
  redondeo, reglas ilegibles) y el guardarraíl `test_only_tax_resolves_a_rule` (ninguna otra app busca reglas
  por su cuenta, hub#295); `test_services.py`, el solape con dos sesiones reales; `test_migrations.py`, el
  catálogo de fábrica y que sembrar dos veces no duplica nada; `test_admin.py`, que el territorio solo se
  guarda por su operación.
- Lo que leen las demás apps se prueba contra Impuestos real en sus `test_integration_tax.py` y en
  `apps/invoice/tests/test_integration_sale.py` y `test_integration_verifactu.py` (el `Impuesto` 01, 02 o 03
  del registro sellado).
- `tax-flows.spec.ts` recorre un test por flujo, en 390, 834 y 1440 los que tienen pantalla.
- `test_integration_home.py` lleva el paso «Tus impuestos» del Inicio por la consulta real de `base` (con dos
  hubs y con Impuestos apagada); `fix-tax-setup-hooks.spec.ts` lo recorre en 390, 834 y 1440.

## Qué queda fuera

- Que el aviso y el paso «Tus impuestos» miren el país y el territorio del negocio (hoy cuenta reglas de cualquiera), el
  país del negocio llegado del SaaS (fase 2) y «hoy» en la zona del negocio: «Lo que queda fuera» del WORKBOOK.
- `useServerTable`/`useLiveList` y los formateadores de porcentaje y fecha en `@erplora/ui`:
  [`UI-REQUESTS.md`](UI-REQUESTS.md).
