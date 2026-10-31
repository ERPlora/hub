# Peticiones de UI de la app `customer`

Lo que la app necesita de `@erplora/ui` y todavía no está. Mientras tanto usa lo más parecido, dentro de
`apps/customer/frontend/`; se cambia en cuanto llegue. Revisado al cerrar la app (CLOSE-CUSTOMER,
2026-10-31) contra `@erplora/ui` en `673e625`: lo que ya llegó ha salido de esta lista y lo que queda va
a `## 6` del registro de la migración con la clave `customer:ui-…` de cada punto. Ninguno rompe un flujo:
todos tienen su sustituto en uso.

## Ya en `@erplora/ui`, falta usarlo en la app

- **`formatMoney`** (`@erplora/ui/components/format`): la app sigue con su `lib/money.ts`, que no agrupa
  los millares; lo lleva hub#512.
- **`ion:pricetags`** y **`ion:cloud-upload-outline`** ya están registrados: la pestaña **Etiquetas**
  (`apps.py`, `Nav(id="tags")`, y `frontend/lib/tabs.ts`) sigue con `ion:list-outline` y **Importar CSV**
  (`components/CustomerImportButton.vue`) con `ion:file-tray-outline`. Propuesto como FIX al cerrar la app.

## Iconos

- `ion:git-merge-outline` (`customer:ui-icon-git-merge`) — botón **Fusionar con…** de la ficha
  (`pages/CustomerDetailPage.vue`); hoy va sin icono.

## Componentes

- **Panel lateral de alta/edición del `DataTable`** (`customer:ui-side-panel`; lo piden también `service`,
  `inventory`, `pricing` y `task`) — el `ok-data-table` del producto abría «Añadir» y «Editar» en su panel
  lateral (hoja completa en el móvil). API propuesta: ranura `create` + método
  `open('create' | 'edit', { title })` / `close()`. Uso: alta de cliente (`CustomerCreateModal.vue`) y
  grupos, etiquetas y campos (`GroupFormModal.vue`, `TagFormModal.vue`, `FieldFormModal.vue`); hoy van en
  `FormModal`.
- **`Kpi`** (`customer:ui-kpi`; la misma petición que `staff:ui-kpi-card`) — la tarjeta de cifra del
  producto (`ok-kpi`: etiqueta en versalitas sobre un valor grande, delta opcional). API propuesta: `label`,
  `value`, `delta?`, `trend?`, `icon?`. Uso: las cuatro cifras de la lista (`CustomerStats.vue`, que hoy la
  pinta con su propio CSS).
- **`useConfirm` con `testid`** (`customer:ui-confirm-testid`) — `ConfirmOptions` no acepta `testid`, así
  que un e2e no encuentra los botones del diálogo imperativo; la app usa `<ConfirmDialog>` directo
  (`CustomerDeleteDialog.vue`, `EntityDeleteDialog.vue`). Propuesta: `testid?: string` en `ConfirmOptions`.
- **`useI18n` exportado desde `@erplora/ui/shell`** (`customer:ui-i18n-shell`) — el Hub no depende de
  `vue-i18n`; la app lee `$t` y `$i18n` de las propiedades globales (`lib/useCustomerI18n.ts`).
- **Nombre de un buscador suelto** (`customer:ui-searchbar-name`; `useSearchbarName`, la misma petición que
  `sale`) — Ionic 8 anuncia el campo de todo `ion-searchbar` como «search text», en inglés; `@erplora/ui` ya
  trae `syncSearchbarInputName`, pero cada pantalla tiene que volver a llamarlo al cambiar el idioma o el
  texto de ayuda y al crearse de nuevo el buscador. Hoy ese `watch` lo lleva la app en
  `lib/useSearchbarName.ts` (el selector de cliente, `CustomerPicker.vue`, y la búsqueda de grupos y
  etiquetas de la ficha, `MembershipEditor.vue`).

## Formateadores (`@erplora/ui/components/format`)

- **`formatDay('YYYY-MM-DD', locale)`** (`customer:ui-format-day`) — un día sin hora ni zona (cumpleaños,
  aniversario); hoy `lib/dates.ts`.

## Librerías (las añade quien lleva `packages/ui`)

- **`libphonenumber-js`** (`customer:ui-libphonenumber`; MIT, `catamphetamine/libphonenumber-js`, releases
  mensuales, decenas de colaboradores, desde 2016) — formatear el teléfono por país al pintarlo y al
  escribirlo (`formatInternational`, `AsYouType`). Hoy `lib/phoneDisplay.ts` separa el prefijo por la tabla
  E.164 y agrupa de tres en tres; la validación sigue siendo del servidor (`phonenumbers`).
- **`papaparse`** (`customer:ui-papaparse`; MIT, `mholt/PapaParse`, mantenida, muchos colaboradores, desde
  2013) — leer el CSV de «Importar CSV» (comillas, separadores, codificaciones). Hoy `lib/csvImport.ts` lee
  RFC 4180 con `,`, `;` y tabulador.
