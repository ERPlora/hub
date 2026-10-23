# Peticiones de UI de la app `sale`

Lo que las páginas de Ventas / TPV necesitan de `@erplora/ui` (o de la plataforma) y todavía no está.
Mientras tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:storefront` (relleno) — entrada de menú **Vender** (`apps.py`), el icono del producto actual.
  Hoy: `ion:storefront-outline`.
- `ion:chatbubble-ellipses-outline` — entrada de menú **Notas rápidas**. Hoy: `ion:chatbubbles-outline`.
- `ion:flame` y `ion:flame-outline` — la llama de urgencia junto a «Enviar comanda» en «Comanda actual»
  (SALE-F20, KITCHEN-F18), el icono del producto actual. Hoy: `ion:alert-circle` / `ion:alert-circle-outline`.
- `ion:trending-up-outline` — el panel **Ventas hoy** del Inicio (`apps.py`, `widgets`; SALE-F28), el icono
  del producto actual. Hoy: `ion:cash-outline` (el que el viejo ponía dentro del panel).
- `ion:bar-chart-outline` — el panel **Ventas últimos 7 días** del Inicio, el icono del producto actual. Hoy:
  `ion:calendar-outline`.

## Plataforma

- **Permiso por entrada de menú** (`Nav.permission`): el producto actual escondía «Notas rápidas»,
  «Departamentos» (aquí «Secciones») y «Ajustes» a quien no tiene `sale.manage_settings`. Hoy salen
  en el menú y la página se abre en solo lectura (o con el aviso «No tienes permiso…» en Ajustes).
- **Elevación por PIN del responsable** (`X-Elevation-Token`, `requires_elevation`): precio libre,
  descuento por encima del máximo, anular una cuenta o una línea enviada, anular y devolver ventas. Hoy
  el empleado ve «Lo tiene que hacer un responsable» y el servidor responde 403.

## Formato

- **Formateadores de dinero, porcentaje y cantidad** en `@erplora/ui/components/format` (hoy
  `frontend/lib/format.ts`, con `Intl.NumberFormat`; mismo pedido que `customer`).

## Back office

Lo que piden Notas rápidas, Secciones y Ajustes (`frontend/components/backoffice/`).

- `ion:save-outline` — botón **Guardar** de Ajustes, el icono del producto actual. Hoy: `lucide:save`
  (el mismo disquete, de otro juego).
- **Tabla de servidor viva** (`useServerTable`: búsqueda, orden, páginas y «Cargar más» en ventanas de
  100 como máximo, una suscripción por ventana) en `@erplora/ui`: hoy cada app lleva su copia (`tax`,
  `inventory`, `customer`, `sale`); la de `sale`, en `frontend/composables/useServerTable.ts`, recibe el
  tope de la búsqueda de cada lista (`maxSearch`).
- **Selector con búsqueda en el servidor** (campo + `ion-modal` + `ion-searchbar` + lista) en
  `@erplora/ui/components`, el mismo que pide `tax` (`SearchSelect`): hoy «IVA que cobra» es
  `components/backoffice/TaxCategoryPicker.vue`.

## Ventas

Lo que piden Ventas, el documento de venta, Anular y Devolver (`pages/SalesPage.vue`,
`frontend/components/sales/`, `frontend/components/document/`).

- `ion:print-outline` — botón de imprimir del documento y acción **Reimprimir** de la fila, los iconos
  del producto actual. Hoy: `ion:receipt-outline` en el documento y `ion:copy-outline` en «Reimprimir»
  (sale un DUPLICADO).
- `ion:return-down-back-outline` — acción **Devolver** de la fila. Hoy: `lucide:rotate-ccw` (la flecha
  de deshacer, de otro juego).
- **Código QR** (el `ok-qr` de antes) en `@erplora/ui/components`: el tique pintaba el QR promocional
  (`receipt_marketing_url`, con `receipt_marketing_text` encima). Hoy el tique no lo pinta: sin QR, el
  texto solo engañaría. Tampoco pinta la imagen del pie (`receipt_footer_image`).
- **Selector de cantidad** (el `ok-qty-stepper` de antes, − n +) en `@erplora/ui/components`: «Unidades
  que vuelven» de Devolver. Hoy: un `ion-input` numérico (1…lo que queda).
- **Tabla de servidor viva con filtros de la página**: la de `frontend/composables/useServerTable.ts` no
  admite filtros propios (periodo, estado, pago, total) ni reiniciar en la primera página al cambiarlos;
  Ventas lleva la suya en `components/sales/useServerTable.ts` + `useLiveList.ts` (ventanas de 100 como
  máximo). Se unen cuando llegue la de `@erplora/ui`.
- **Selector con búsqueda en el servidor**: «Devolver por» usa `components/sales/PaymentMethodPicker.vue`
  (busca en `sale.payment_method.list`, 20 por página). El filtro «Pago» de Ventas ya es el `lookup` del
  embudo de `DataTable`.
- **Impresora de red** (app Impresión): hoy el documento, «Reimprimir» y la cuenta del TPV se imprimen
  con el diálogo del navegador (`lib/print.ts`, `printPaper`).

## Cobro

Lo que pide la hoja **Cobro** (`frontend/components/checkout/`, `lib/checkout/methods.ts`).

- `ion:swap-horizontal-outline` — botón **Repartir el cobro** y forma de pago de tipo transferencia, los
  iconos del producto actual. Hoy: `ion:swap-vertical-outline`.
- `ion:ellipsis-horizontal-circle-outline` — forma de pago «otra» sin nombre conocido. Hoy:
  `ion:wallet-outline`.
- `ion:gift-outline` — forma de pago de regalo. Hoy: `ion:ticket-outline`, el de los vales.
- `ion:document-text-outline` — recuadro de los datos del cliente ya completo («Esta venta sale como
  factura completa»). Hoy: `ion:receipt-outline`.
- **Marca de Bizum** (el SVG de marca del producto actual) como icono horneado de `@erplora/ui`: nada de
  SVG sueltos. Hoy: `ion:phone-portrait-outline`.
- **Aviso de advertencia** (`toastWarning`) en `@erplora/ui/shell`: el toque en «Cobrar» bloqueado y en
  el efectivo por encima del límite usan `toast(mensaje, 'warning')`.

## POS

Lo que pide la pantalla **Vender** (`pages/PosPage.vue`, `frontend/components/pos/`).

- `ion:pause-circle-outline` — botón **Aparcar esta cuenta** de la cabecera. Hoy: `ion:time-outline`.
- `ion:gift-outline` / `ion:gift` — botón **Invitar / quitar invitación** de la línea. Hoy:
  `ion:sparkles-outline` (en verde cuando está invitada).
- `ion:chatbox-ellipses-outline` / `ion:chatbox-ellipses` — botón **Nota** de la línea y la nota bajo
  ella. Hoy: `ion:chatbubbles-outline` (en el color primario cuando hay nota).
- `ion:pricetag` (relleno) — descuento puesto en la línea o en la cuenta. Hoy: `ion:pricetag-outline` en
  el color de aviso.
- `ion:print-outline` — botón **Imprimir cuenta** del pie y la impresora de la precuenta. Hoy:
  `ion:receipt-outline`.
- `ion:expand-outline` / `ion:contract-outline` — **Pantalla completa** / **Salir de pantalla completa**
  del menú ⋮. Hoy: `ion:chevron-expand-outline` para los dos.
- `ion:remove-outline` — el «−» del selector de cantidad. Hoy el selector pinta los signos «−» y «+»
  como texto (con su nombre accesible).
- `ion:ellipse-outline` — el círculo vacío que marca una línea para cobrarla aparte. Hoy: un aro de CSS
  (marcada: `ion:checkmark-circle`).
- `ion:flame` — cabecera **Enviado** de las líneas que ya están en cocina. Hoy:
  `ion:checkmark-circle-outline`.
- **Selector de cantidad** (− n +) en `@erplora/ui/components`: hoy `components/pos/QtyStepper.vue`
  (el mismo pedido que Devolver).
- **Hoja del TPV** (`ion-modal` del alto de su contenido: tarjeta de 24rem en escritorio y hoja desde
  abajo en el móvil, con la cifra grande arriba y el pie fijo) en `@erplora/ui/components`: hoy
  `components/pos/PosSheet.vue`.
- **Teclado numérico** (1…9, separador decimal del idioma, 0 y borrar) en `@erplora/ui/components`:
  hoy `components/pos/PosNumpad.vue` (Cobro lleva el suyo, `PayKeypad`).
- **Lista viva en ventanas** (`useLiveWindows`: ventanas de 100 como máximo, una suscripción por
  ventana, «Cargar más») en `@erplora/ui`: hoy `composables/pos/useLiveWindows.ts`.
- **Escalón de la cantidad en la línea de la cuenta**: `OrderLineOut` no trae el incremento congelado
  de la unidad, así que el selector sube y baja de uno en uno y una cantidad que no encaja la rechaza el
  servidor («La cantidad no encaja con el escalón del producto»).
- **Catálogo de venta por categoría**: `inventory.product.list_for_sale` no filtra por categoría, así
  que la rejilla lee `inventory.product.list` (`is_active`, `category_id`, por nombre) y marca «Falta el
  IVA» con su `needs_tax_setup`.
