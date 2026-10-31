# Clientes (`customer`)

El fichero de personas y empresas del negocio y el dueño de su dato personal: la ficha con el contacto y los
datos fiscales, sus grupos, etiquetas y campos propios, sus notas y su actividad, su consentimiento de
publicidad por canal, sus datos de salud con permiso y lo que ha comprado. Es la app de la que más dependen
las demás: Ventas, Citas, Reservas, la Bandeja de WhatsApp y otras cinco la requieren.

- **Estado**: completa (2026-10-31): 31 de sus 32 flujos, `CUSTOMER-F01` … `F32`, están `hecho`;
  `CUSTOMER-F26` está `descartado` con su issue (hub#514).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Las fichas** (F01–F09, F27–F29, F31): dar de alta (solo el nombre es obligatorio), buscar sin
  acentos ni mayúsculas, filtrar y ordenar, editar con sus campos personalizados, eliminar conservando la
  historia, importar y exportar CSV; grupos, etiquetas y campos propios del negocio; las cuatro cifras de
  arriba de la lista, vivas.
- **La persona** (F10–F16, F32): el teléfono en E.164 con las reglas de libphonenumber, la búsqueda por
  número (también las cifras que da WhatsApp), el aviso de duplicado en el alta rápida, la fusión de dos
  fichas (cada app re-apunta lo suyo), el consentimiento por canal como libro de hechos, el borrado de datos
  personales (RGPD) y las alergias y la prueba de sensibilidad con el permiso expreso de la persona.
- **Con Ventas** (F17–F23): el buscador de cliente del TPV (`CustomerSearch`, también en la agenda de
  Citas, F25) con la copia fiscal, el enlace cliente ↔ pedido, y las compras, anulaciones y devoluciones
  que llegan por el relay del outbox y mueven las cifras y la etapa de la ficha.
- **Con las demás apps** (F24, F30): la ficha completa a quien la pide por su id y los bloques de otras
  apps al final de la ficha (hoy, el «Historial de visitas» de Citas).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:people-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | ninguna: se enciende sola |
| La requieren | Ventas, Facturación, Citas, Servicios, Tarifas, Reservas, Mesas, Reservas online y la Bandeja de WhatsApp |
| Pantallas | `/customer/customers` (lista y ficha, `/customer/customers/:id`), `/customer/groups`, `/customer/tags`, `/customer/fields`; `/customer/preview/customer-search` solo en el servidor de desarrollo |
| Operaciones | 16 consultas (`queries.py`) y 28 acciones (`services.py`), todas con `ai=`; las cuatro `customer.health.*`, con `ai=INTERNAL` y sin `expose_api` (los datos de salud no llegan al asistente ni a las API keys); 41 rutas en `/api/customer/…` (sin ruta: las tres `customer.purchase.*`, que solo corre el sistema) |
| Aprobaciones | 8 órdenes que un responsable aprueba con su PIN al empleado (`approvals`, BASE-F84): unir fichas, crear y cambiar grupos y etiquetas, y crear, cambiar y eliminar campos |
| Eventos | 28, `customer.<entidad>.<hecho>` (`events.py`), solo con identificadores; `REACTIONS` a `sale.sale.completed`, `.voided` y `.refunded` (`customer.purchase.record`, `.void`, `.refund`), por el relay del outbox |
| Bloques de la ficha | `apps/<id>/frontend/customer-card/<Bloque>.vue` de cada app encendida (hoy, `appointment`) |
| Migraciones | `0001_initial`, `0002_purchase_refunds`, `0003_health_record` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (teléfonos, búsqueda, estados de una ficha, consentimiento, compras, bloqueos y
bloques de otras apps) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda
2026-10-31d (CLOSE-CUSTOMER) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/customer apps/sale/tests/test_integration_customer.py \
  base/tests/test_relay.py
pnpm test apps/customer
pnpm e2e tests/e2e/customer-flows.spec.ts tests/e2e/customer-pages.spec.ts tests/e2e/customer-card.spec.ts \
  tests/e2e/customer-create-search.spec.ts tests/e2e/customer-search.spec.ts tests/e2e/customer-csv.spec.ts \
  tests/e2e/customer-country.spec.ts tests/e2e/customer-employee.spec.ts \
  tests/e2e/customer-business-currency.spec.ts
```

- `test_phones.py` es el contrato de la lectura E.164; `test_concurrency.py` cruza en hilos, con sesiones
  reales, las escrituras de la app con el «Eliminar» del admin del Hub; `test_business_currency.py` lleva la moneda del negocio con dos hubs.
- `test_phone_lookup_coherence.py`: la ficha que Clientes guarda por su teléfono la encuentra otra app con las
  mismas cifras, sea cual sea el país del negocio; `test_approvals.py`: lo que el empleado hace con el PIN de un
  responsable y lo que nunca se le pide.
- `apps/sale/tests/test_integration_customer.py` da a Clientes los avisos reales de Ventas, y
  `base/tests/test_relay.py` los lleva por el tick real del relay hasta la ficha.

## Qué queda fuera

- `CUSTOMER-F26` (hub#514), los importes sin separador de millares (hub#512), la tarjeta del asistente que
  no dice qué ficha toca (hub#513) y el país del negocio para un teléfono sin prefijo (hub#527, cruza las apps
  que buscan fichas por teléfono): «Lo que queda fuera» del WORKBOOK.
- Las peticiones de [`UI-REQUESTS.md`](UI-REQUESTS.md).
