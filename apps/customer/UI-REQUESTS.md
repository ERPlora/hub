# Peticiones de UI de la app `customer`

Lo que la app necesita de `@erplora/ui` y todavía no está. Mientras tanto usa lo más parecido, dentro de
`apps/customer/frontend/`; se cambia en cuanto llegue.

## Iconos

- `ion:pricetags` — pestaña **Etiquetas** del menú de Clientes (`apps/customer/apps.py`, `Nav(id="tags")`,
  y `frontend/lib/tabs.ts`); hoy usa `ion:list-outline`. Es el icono del producto actual.
- `ion:cloud-upload-outline` — botón **Importar CSV** de la lista (`components/CustomerImportButton.vue`);
  hoy usa `ion:file-tray-outline`.
- `ion:git-merge-outline` — botón **Fusionar con…** de la ficha (`pages/CustomerDetailPage.vue`); hoy va sin
  icono.

(`ion:layers-outline` y `ion:person-add-outline` ya están registrados y se usan.)

## Componentes

- **`SearchSelect`** — cerrada: llegó como `Combo` (`@erplora/ui/components`) y el «País» de la ficha lo usa
  (`components/CustomerForm.vue`); la copia propia `CountrySelect.vue` se ha borrado. Los «Grupos» y
  «Etiquetas» de la ficha (`components/MembershipEditor.vue`) no son un combo de un valor, sino casillas de
  selección múltiple con buscador en el servidor a partir de 100: se quedan así y no piden nada a `ui`.
- **Panel lateral de alta/edición del `DataTable`** — el `ok-data-table` del producto abría «Añadir» y
  «Editar» en su panel lateral (hoja completa en el móvil). API propuesta: ranura `create` + método
  `open('create' | 'edit', { title })` / `close()`. Uso: alta de cliente (`CustomerCreateModal.vue`) y
  grupos, etiquetas y campos (`GroupFormModal.vue`, `TagFormModal.vue`, `FieldFormModal.vue`); hoy van en
  `FormModal`.
- **`Kpi`** — la tarjeta de cifra del producto (`ok-kpi`: etiqueta en versalitas sobre un valor grande,
  delta opcional). API propuesta: `label`, `value`, `delta?`, `trend?`, `icon?`. Uso: las cuatro cifras de
  la lista (`CustomerStats.vue`, que hoy la pinta con su propio CSS).
- **`useConfirm` con `testid`** — `ConfirmOptions` no acepta `testid`, así que un e2e no encuentra los
  botones del diálogo imperativo; la app usa `<ConfirmDialog>` directo (`CustomerDeleteDialog.vue`,
  `EntityDeleteDialog.vue`). Propuesta: `testid?: string` en `ConfirmOptions`.
- **`useI18n` exportado desde `@erplora/ui/shell`** — el Hub no depende de `vue-i18n`; la app lee `$t` y
  `$i18n` de las propiedades globales (`lib/useCustomerI18n.ts`).

## Formateadores (`@erplora/ui/components/format`)

- **`formatMoney(cents, locale, currency)`** — hoy `lib/money.ts` (euros).
- **`formatDay('YYYY-MM-DD', locale)`** — un día sin hora ni zona (cumpleaños, aniversario); hoy
  `lib/dates.ts`.

## Librerías (las añade quien lleva `packages/ui`)

- **`libphonenumber-js`** (MIT; `catamphetamine/libphonenumber-js`, releases mensuales, decenas de
  colaboradores, desde 2016) — formatear el teléfono por país al pintarlo y al escribirlo
  (`formatInternational`, `AsYouType`). Hoy `lib/phoneDisplay.ts` separa el prefijo por la tabla E.164 y
  agrupa de tres en tres; la validación sigue siendo del servidor (`phonenumbers`).
- **`papaparse`** (MIT; `mholt/PapaParse`, mantenida, muchos colaboradores, desde 2013) — leer el CSV de
  «Importar CSV» (comillas, separadores, codificaciones). Hoy `lib/csvImport.ts` lee RFC 4180 con `,`, `;` y
  tabulador.
