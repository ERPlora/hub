# Workbook — Tarifas (app)
Prefijo: PRICING
Alcance MVP: transversal (peluquería y restaurante: precios por grupo de clientes y descuentos automáticos)
Estado de la app: completa (2026-10-21)

> Manual de usuario y especificación de la app `pricing`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Precios del producto actual
> (`modules-workspace/modules/pricing`, `origin/main` `cd6985c`, v1.1.32). Hace lo mismo, se ve igual
> (una entrada de menú, **Tarifas**, con las listas arriba y las reglas debajo) y conserva su
> funcionalidad salvo lo que dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Tarifas guarda **otros precios** para tus artículos y servicios y los **descuentos automáticos**:

- una **tarifa** (lista de precios) es un precio distinto del de la ficha para algunos artículos o
  servicios: «Mayoristas», «Socios VIP», «Temporada de verano». Se le puede dar un **grupo de
  clientes** (solo vale para quien está en ese grupo), unas **fechas** (solo vale entre ellas) y
  **tramos por cantidad** («a partir de 10 unidades, 0,80 €»). Una de ellas puede ser la **tarifa
  general**, la que vale para todo el mundo;
- una **regla de descuento** baja el importe de una línea sola: un porcentaje, un importe por unidad,
  «compra 2 y llévate 1» o un descuento por tramos de cantidad. Se limita a todo, a los productos, a los
  servicios, a una categoría, a un producto o a un servicio; y, si quieres, a un grupo de clientes, a
  una cantidad mínima y a unas fechas.

Tarifas **calcula el precio** de una línea: con el artículo o el servicio, el cliente, la cantidad y el
día, dice qué precio le toca, de qué tarifa sale, qué regla le quita cuánto y cuánto queda. Lo usan las
apps que venden (Ventas, cuando lo pida: ver «Contrato con Ventas»), el asistente («¿cuánto le cuesta
un corte a un cliente del grupo VIP?») y la API.

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** crean y cambian tarifas, precios y
  reglas, eligen la tarifa general y desactivan lo que ya no vale.
- El **empleado** ve las tarifas y las reglas y consulta precios.

## Referencia adoptada

**Qué tarifa gana, cuántos descuentos automáticos se suman y cuándo se fija el precio** (skill
`market-decision`, 2026-10-15). El producto actual elegía el precio más bajo entre todas las tarifas
activas (sin mirar fechas ni la tarifa por defecto), sumaba todas las reglas en cadena por prioridad
sobre el importe del tique, y nadie lo llamaba.

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Business Central | Listas por cliente, grupo de precios de cliente o todos, con fechas, cantidad mínima y divisa; gana el **mejor precio** (el más bajo) en la fecha; sin acuerdo, el precio de la ficha; se calcula al insertar la línea | https://learn.microsoft.com/en-us/dynamics365/business-central/sales-how-record-sales-price-discount-payment-agreements |
| Shopify | Catálogos B2B por empresa o mercado, precio fijo o % y tramos por volumen; gana el **precio más bajo**; los descuentos automáticos no se combinan: se aplica **el mejor para el cliente**; un descuento manual del TPV siempre se aplica | https://help.shopify.com/en/manual/b2b/catalogs · https://help.shopify.com/manual/discounts/discount-combinations · https://help.shopify.com/en/manual/sell-in-person/shopify-pos/discount-management/combining-discounts |
| Lightspeed X-Series | Libros de precios por grupo de clientes, tienda, fechas y unidades mín./máx. (tramos repitiendo el producto); el libro general es la base; entre promociones gana **la mejor para el cliente**; libro y promoción se apilan | https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534056400411-Running-sales-using-price-books · https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534113032859-Setting-up-multi-save-and-conditional-promotions |
| Odoo 18 | Tarifa en la ficha del cliente o la por defecto del TPV; reglas con fechas, cantidad mínima y ámbito (producto, categoría, todo); sin regla, el precio base; al cambiar de cliente o de cantidad se recalculan las líneas que no tienen precio manual | https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/pricing/pricelists.html <!-- código: https://github.com/odoo/odoo/blob/18.0/addons/product/models/product_pricelist_item.py --> |
| Square | El precio por cliente es un descuento automático ligado a un grupo de clientes; reglas por cantidad, 2x1, fechas y horas; **un solo descuento automático por artículo, el más favorable** | https://squareup.com/help/us/en/article/6603 · https://developer.squareup.com/blog/discounting-at-square/ |
| Toast | Precios por menú, horario o nivel; descuentos automáticos 2x1, volumen, fijo o %; **uno por artículo**; los manuales nunca se quitan al recalcular | https://doc.toasttab.com/doc/platformguide/adminAutoApplyDiscounts.html · https://doc.toasttab.com/doc/platformguide/adminToastPosPricingFeatures.html |
| WooCommerce | Cupones (%, fijo por carrito o por producto, gasto mínimo, categorías, caducidad) y Dynamic Pricing por rol, tramos por producto o categoría; en categorías gana el mayor descuento | https://woocommerce.com/document/coupon-management/ · https://woocommerce.com/document/woocommerce-dynamic-pricing/ |
| Holded | Tarifas extra por producto junto al precio principal, con una tarifa por defecto en la ficha del contacto | https://help.holded.com/en/articles/6865131 |
| Fresha | Descuento manual (fijo o %) por artículo o al total en el cobro; ofertas con duración en la reserva online | https://www.fresha.com/help-center/knowledge-base/sales/518-apply-a-discount-at-checkout |
| Foro de Square | Un 10 % automático se suma a un 35 % de empleado y el personal lo quita a mano: piden no acumular | https://community.squareup.com/t5/Square-for-Retail/Stacking-Discounts-MUST-GO/td-p/363325 |
| Foro de Shopify | Descuentos marcados como combinables no se combinan: «only the largest discounts apply» por artículo | https://community.shopify.com/t/why-arent-my-automatic-discount-codes-combining-at-checkout/227952 |
| Foro de Odoo | La tarifa del cliente no se aplica sola en el TPV y hay que elegirla a mano | https://www.odoo.com/forum/help-1/pos-and-customer-pricelist-131813 |

**Gana:**

1. **Una tarifa vale para un grupo de clientes o para todos** (la general), entre sus fechas, como en
   Business Central, Shopify y Lightspeed. Si varias tarifas tienen precio para la línea, gana **el más
   bajo** (el «mejor precio» de Business Central, Shopify y Lightspeed). Dentro de una tarifa, el tramo
   de cantidad mínima más alto que alcanza la línea. Sin precio en ninguna, **el de la ficha**.
2. **Un solo descuento automático por línea: el mejor para el cliente** (Square, Shopify, Toast,
   promociones de Lightspeed); a igual descuento, la regla de menor prioridad y después la de código
   menor. La regla se aplica sobre el precio de la tarifa (Lightspeed: libro y promoción se apilan).
3. **El precio se resuelve en el servidor al añadir la línea** y se congela en ella (Business Central,
   Toast). Solo se vuelve a pedir si cambian la cantidad o el cliente de la cuenta, y nunca sobre un
   precio puesto a mano (Odoo).
4. **Un descuento manual va encima** del precio ya resuelto y no se quita al recalcular (Shopify, Toast,
   Odoo). Lo decide y lo limita Ventas (`max_discount_percent`), no esta app.

**Por qué las demás no:** «la regla más específica gana» (Odoo) obliga a entender un orden que el dueño
no ve y en el foro se queja de que la tarifa del cliente no se aplica; sumar todas las reglas en cadena
(el producto actual, Square con la queja del foro) cobra de menos sin que nadie lo note; los descuentos
por importe del tique (gasto mínimo) necesitan el tique entero, que esta app no tiene: se quedan fuera
(«Lo que NO hace»).

**Las cantidades de una regla en un artículo que se vende al peso** (skill `market-decision`,
2026-10-15): un «0,50 € por unidad», un «compra 2, llévate 1», un tramo o un mínimo, ¿cuentan gramos,
kilos o líneas?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Odoo 18 | La cantidad mínima va en la unidad de medida del producto; la fidelización suma las cantidades en esa unidad y redondea hacia abajo las unidades gratis | Código fuente de Odoo 18: tarifas y fidelización <!-- código: https://github.com/odoo/odoo/blob/18.0/addons/product/models/product_pricelist_item.py · https://github.com/odoo/odoo/blob/18.0/addons/sale_loyalty/models/sale_order.py --> |
| Business Central | Precio y descuento de línea por unidad de medida y cantidad mínima en esa unidad | https://learn.microsoft.com/en-us/dynamics365/business-central/sales-how-record-sales-price-discount-payment-agreements |
| Dynamics 365 Commerce | Descuentos por cantidad y combinados con unidad de medida en cada línea; no convierte unidades | https://learn.microsoft.com/en-us/dynamics365/commerce/retail-discounts-overview |
| Square | Las reglas cuentan «artículos» enteros; con unidad de medida no dice cómo cuenta 0,25 lb | https://developer.squareup.com/reference/square/objects/CatalogProductSet |
| Lightspeed X-Series | Al peso, cantidad = peso; las promociones cuentan artículos sin decir qué hace con decimales | https://x-series-api.lightspeedhq.com/docs/promotions |
| Toast | Al peso, cantidad decimal; el 2x1 cuenta artículos y no menciona el peso | https://intercom.help/toast-central/en/articles/9307949-configure-items-priced-by-weight |
| Loyverse | Sin reglas por cantidad: a lo pesado solo le llega el porcentaje | https://help.loyverse.com/help/how-create-and-configure-discounts |
| Foro de Toast | El descuento en dólares solo cubre la primera libra; por debajo de 1 lb no hay descuento | https://community.toasttab.com/t5/restaurant-operations/discounting-of-weighed-items-under-a-lb/m-p/14871 |
| Foro de Reckon | Una promoción de 2 $/kg redondea el peso a unidades (0,5 kg sin descuento); piden que vaya «relative to the weight» | https://community.reckon.com/discussion/5944939/why-isnt-the-promotional-prices-applied-to-weighted-items-in-pos |

**Gana:** contar **en la unidad del precio** (kg en un café a 20 €/kg vendido en gramos), como Odoo,
Business Central y Dynamics 365 Commerce, con las unidades gratis redondeadas hacia abajo (Odoo).
**Por qué las demás no:** contar gramos regala el café (250 × 0,50 €) y cumple un mínimo de 3 con 3 g;
contar cada línea como una unidad es el fallo del que se quejan los foros; excluir lo pesado no lo hace
nadie a propósito y deja sin promociones a una charcutería.

## Antes de empezar

1. Tarifas necesita **Inventario** (los productos y sus categorías) y **Clientes** (los grupos): al
   encenderla se encienden las dos. **Servicios** no hace falta: si está, también se ponen precios a
   servicios y reglas para servicios.
2. Si una tarifa es para un grupo («VIP», «Mayoristas»), crea antes el grupo en **Clientes → Grupos**
   y mete en él a sus clientes.
3. Sin ninguna tarifa ni regla, todo se cobra al precio de la ficha: instalar Tarifas no cambia nada
   hasta que creas la primera.
4. «Hoy» y las fechas de las tarifas y las reglas son el día del negocio: en la fase 1, la zona horaria
   del Hub, **Europe/Madrid**. La divisa del negocio es el **euro**.

## Pantallas

Tarifas se abre desde el menú **Tarifas** (icono de etiquetas). Lo que una persona no puede hacer no
aparece, y la app lo rechaza aunque lo intente por la API o por el asistente.

### Tarifas
Dos tablas, una encima de otra, como en el producto actual.

**Listas de precios**: buscador «Buscar código o nombre…», columnas **Código** (con la etiqueta
**General** si es la tarifa general), **Nombre**, **Divisa**, **Grupo de clientes** («Todos» si es
la general, «—» si no tiene), **Impuesto** («Según el negocio», «Impuesto incluido», «Impuesto no
incluido»), **Vigencia** («Siempre», «Desde 1 jul 2026», «Hasta…» o las dos fechas), **Precios**
(cuántos tiene) y **Estado** (Activa o Inactiva). Se ordena por Código, Nombre, Divisa, Grupo e Impuesto
(por defecto, por nombre) y se filtra, con el embudo de la barra, por Código, Nombre y Divisa (por el
texto que contienen), Grupo de clientes, Impuesto y Estado (al abrir, **Activas** ya elegido;
**Inactivas**, o **Todos** para las dos); 50 por página, en lista o en tarjetas.

- **+** abre **Nueva tarifa**: **Código** y **Nombre** (obligatorios), **Divisa** (EUR), **Impuesto**
  (Según el negocio por defecto), **Grupo de clientes** (buscador; vacío = ninguno), **Desde** y
  **Hasta**, y **Tarifa general** (un interruptor; no se puede con grupo).
- Acciones de fila: **Abrir** (también pulsando la fila), **Editar**, **Hacer general** (en el menú «⋮»;
  solo en una activa, sin grupo, en euros y que no lo sea; pide confirmación), **Desactivar** (en el
  menú «⋮»; pide confirmación; no en la general) o **Activar** (en las inactivas). El empleado solo ve
  **Abrir**.

**Reglas de descuento**: buscador «Buscar código o nombre…», columnas **Código**, **Nombre**, **Tipo**
(Porcentaje, Importe por unidad, Compra X, llévate Y, Por tramos), **Valor** («10 %», «0,50 € por
unidad», «Compra 2, llévate 1», «3+: 10 % · 6+: 15 %»), **Se aplica a** («Todo», «Todos los
productos», «Todos los servicios», la categoría, el producto o el servicio, con «(borrado)» si
Inventario lo borró; con el grupo de clientes detrás si lo tiene, o «Grupo borrado»), **Vigencia**, **Prioridad** y **Estado**. Se ordena por Código, Nombre, Tipo y
Prioridad (Valor no se ordena ni se filtra: sus unidades son distintas); se filtra, con el embudo, por
Código, Nombre, Tipo, Se aplica a y Estado (como en las tarifas: **Activas** al abrir); 50 por página.

- **+** abre **Nueva regla de descuento** (PRICING-F10).
- Acciones de fila: **Editar** (también pulsando la fila), **Desactivar** (pide confirmación) o
  **Activar** (en las inactivas). El empleado no tiene acciones.

### Tarifa (detalle)
Se abre desde la fila y tiene **Volver**; su título es el nombre de la tarifa. Arriba, la tarifa:
**Código** con la etiqueta **General**, **Grupo de clientes** («Todos» en la general), **Divisa**,
**Impuesto**, **Vigencia** y **Estado**, y en la barra **Editar**, **Hacer general** y **Desactivar /
Activar** (lo que corresponda; con las mismas confirmaciones que en la tabla).

Debajo, **Precios**: buscador «Buscar producto o servicio…», columnas **Artículo** (nombre),
**Tipo** (Producto o Servicio), **SKU**, **Desde** (la cantidad mínima, con su unidad), **Precio** y
**Precio de ficha** (el de Inventario; «—» en un servicio). Los precios, en la divisa de la tarifa. Orden
por Artículo, Desde y Precio; filtro por Tipo, con el embudo; 50 por página.

- **+** abre **Nuevo precio**: **Tipo** (Producto o Servicio), el buscador del artículo (un producto por
  nombre o SKU; un servicio por nombre), **Desde la cantidad** (cantidad mínima, 1 por defecto) y
  **Precio**.
- Acciones de fila: **Editar** (precio y cantidad mínima; también pulsando la fila) y **Quitar** (pide
  confirmación).

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin listas de precios.», «Sin reglas de descuento.» o «Esta tarifa aún no tiene precios.»; con búsqueda o filtro, «Sin resultados». |
| Error | El aviso de la tabla con «Reintentar». El rechazo de un formulario sale dentro del formulario y debajo de su campo, sin perder lo tecleado; el de una confirmación, dentro de la confirmación. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |
| Tarifa que no existe | El detalle dice «Esta tarifa no existe» con **Volver**. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| PRICING-F01 | Ver las tarifas | hecho |
| PRICING-F02 | Crear una tarifa | hecho |
| PRICING-F03 | Editar una tarifa | hecho |
| PRICING-F04 | Elegir la tarifa general | hecho |
| PRICING-F05 | Desactivar o reactivar una tarifa | hecho |
| PRICING-F06 | Ver los precios de una tarifa | hecho |
| PRICING-F07 | Poner el precio de un producto o un servicio en una tarifa | hecho |
| PRICING-F08 | Cambiar o quitar un precio | hecho |
| PRICING-F09 | Ver las reglas de descuento | hecho |
| PRICING-F10 | Crear una regla de descuento | hecho |
| PRICING-F11 | Editar una regla | hecho |
| PRICING-F12 | Desactivar o reactivar una regla | hecho |
| PRICING-F13 | Consultar el precio de una línea | hecho |
| PRICING-F14 | Cuando se borra un producto, una categoría o un grupo, o cambia un servicio | hecho |

### PRICING-F01 Ver las tarifas
<!-- origen: fi:modules/pricing#navigation-lists-erp-pricing-lists fi:modules/pricing#permission-pricing-view_pricing-manage_pricing-apply_pricing fi:modules/pricing#query-pricing-price_lists-list-expose_api old:pricing/WORKFLOW.md#pricing-f01 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, empleado, asistente
Pantalla: Tarifas
Pasos:
1. Abre **Tarifas** en el menú: arriba, las listas de precios activas.
2. Busca por código o nombre, ordena o filtra (Estado **Inactivas** enseña las desactivadas).
Entra: las tarifas del negocio.
Sale: nada; la tabla se mantiene al día sola cuando alguien cambia una tarifa o un precio.
Si falla: el aviso de la tabla con «Reintentar».
Implicados: Clientes (el nombre del grupo)

### PRICING-F02 Crear una tarifa
<!-- origen: fi:modules/pricing#command-wasm-pricing-price_lists-create-create_price_list fi:modules/pricing#event-emitidos-price_list-created-price_item-added-rule-created-rule-deactivated old:pricing/WORKFLOW.md#pricing-f02 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas
Pasos:
1. Pulsa **+** en «Listas de precios»: se abre **Nueva tarifa**.
2. Escribe el **Código** (hasta 50 caracteres; único, sin distinguir mayúsculas: «VIP» y «vip» son el
   mismo) y el **Nombre** (hasta 200).
3. Si quieres: la **Divisa** (código ISO de tres letras con dos decimales: EUR, USD, GBP…), el
   **Impuesto** (Según el negocio, Impuesto incluido, Impuesto no incluido), el **Grupo de clientes**,
   **Desde** y **Hasta** (las dos incluidas), y **Tarifa general**.
4. Pulsa **Crear**: la tarifa sale en la tabla, activa y sin precios.
Entra: el formulario. El asistente nombra el grupo por su nombre.
Sale: la tarifa y el aviso `pricing.price_list.created`. Si se marca como general, la que lo era deja
de serlo en la misma operación: nunca hay dos.
Si falla: debajo de su campo y sin crear nada: «Ya existe una tarifa con ese código. Elige otro.»
(también si la que lo tiene está desactivada), una divisa que no existe o que no tiene dos decimales,
«Hasta» antes que «Desde», un grupo que no existe, «La tarifa general vale para todos: quítale el
grupo.» o «La tarifa general va en la divisa del negocio (EUR), la que cobra la caja.» (el interruptor se
apaga solo con un grupo o con otra divisa).
Implicados: Clientes

### PRICING-F03 Editar una tarifa
<!-- origen: nuevo (Business Central, Shopify, Lightspeed y Odoo editan, desactivan y reactivan tarifas, precios y reglas; el producto actual no: «Cambios frente al producto actual») -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas, Tarifa (detalle)
Pasos:
1. **Editar** en la fila o en el detalle: **Editar tarifa — {nombre}** con lo que tiene.
2. Cambia lo que quieras (código, nombre, divisa, impuesto, grupo, fechas) y pulsa **Guardar**.
Entra: solo lo cambiado. Quitar el grupo deja la tarifa sin grupo.
Sale: la tarifa y `pricing.price_list.updated` (sin cambios, nada).
Si falla: los mismos rechazos que al crear; a la general no se le puede poner grupo ni otra divisa. Si
Clientes borró su grupo, la columna y el formulario dicen «Grupo borrado» y la tarifa no vale para nadie
hasta que se le quite o se le elija otro.
Implicados: Clientes

### PRICING-F04 Elegir la tarifa general
<!-- origen: fi:modules/pricing#command-interno-pricing-_unset_default-pricing-_insert_price_list -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas, Tarifa (detalle)
Pasos:
1. **Hacer general** en una tarifa activa, sin grupo y en euros (en otra no se ofrece).
2. Confirma «{nombre} pasa a ser la tarifa general: valdrá para todos los clientes y la actual dejará de
   serlo.».
Entra: la tarifa. Por el asistente o la API también se puede **quitar** la marca (ninguna general).
Sale: la tarifa general nueva y `pricing.price_list.default_changed` (con la anterior). Si dos personas
eligen a la vez, queda una sola: la última.
Si falla: «Una tarifa desactivada no puede ser la general.», «La tarifa general vale para todos: quítale
el grupo.», «La tarifa general va en la divisa del negocio (EUR)…» y, si otras elecciones ganan la carrera
tres veces seguidas, «Otra persona está cambiando la tarifa general en este momento. Vuelve a intentarlo
en un instante.» (409 `pricing.default_busy`, nunca un error del servidor).
Implicados: ninguno

### PRICING-F05 Desactivar o reactivar una tarifa
<!-- origen: nuevo (Business Central, Shopify, Lightspeed y Odoo editan, desactivan y reactivan tarifas, precios y reglas; el producto actual no: «Cambios frente al producto actual») -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas, Tarifa (detalle)
Pasos:
1. **Desactivar** y confirma «{nombre} dejará de aplicarse a las ventas nuevas. Sus precios se
   guardan.».
2. Para volver a usarla, filtra por **Inactivas** y pulsa **Activar**.
Entra: la tarifa.
Sale: la tarifa y `pricing.price_list.deactivated` o `…activated`. Las ventas ya hechas no cambian.
Si falla: «Esta es la tarifa general: elige otra como general o quítale la marca antes de
desactivarla.», «Esa tarifa ya está desactivada.», «Esa tarifa ya está activa.».
Implicados: ninguno

### PRICING-F06 Ver los precios de una tarifa
<!-- origen: fi:modules/pricing#query-pricing-price_lists-get-expose_api fi:modules/pricing#query-pricing-price_lists-items-expose_api -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, empleado, asistente
Pantalla: Tarifa (detalle)
Pasos:
1. Pulsa una tarifa en la tabla: se abre su detalle.
2. Busca por nombre o SKU, filtra por Tipo u ordena.
Entra: los precios de la tarifa; de un producto, su nombre, SKU, unidad y precio de ficha de
Inventario, al día; de un servicio, su nombre.
Sale: nada. Por la API y el asistente, también los precios de un producto o un servicio en todas las
tarifas.
Si falla: «Esta tarifa no existe» con **Volver**.
Implicados: Inventario, Servicios

### PRICING-F07 Poner el precio de un producto o un servicio en una tarifa
<!-- origen: fi:modules/pricing#event-emitidos-price_list-created-price_item-added-rule-created-rule-deactivated fi:modules/pricing#command-pricing-price_lists-add_item old:pricing/WORKFLOW.md#pricing-f03 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifa (detalle)
Pasos:
1. **+** en «Precios»: **Nuevo precio**.
2. En **Tipo**, elige **Producto** (búscalo por nombre o SKU) o **Servicio** (búscalo por nombre).
3. **Desde la cantidad**: la cantidad mínima a partir de la que vale (1 por defecto; en la unidad del
   producto, «0,5» kg, y en su escalón). Para precios por volumen, repite el producto con otra cantidad
   mínima.
4. **Precio**: en euros, como lo escribe una persona («12,50»). Es el precio por la misma cantidad que el
   de la ficha (si la ficha dice «0,37 € por 100 ud», el de la tarifa también es por 100 ud).
5. Pulsa **Añadir**.
Entra: la tarifa (activa), el artículo y su precio. El asistente nombra la tarifa por su código o su
nombre y el artículo por su nombre o su SKU.
Sale: el precio y `pricing.price_item.added`.
Si falla: debajo de su campo y sin guardar nada: «Esa tarifa no está disponible: no existe en este
negocio o está desactivada.», «Ese artículo ya tiene precio en esta tarifa desde esa cantidad.», un
producto que no existe o está borrado, una cantidad que no encaja en la unidad del producto o que no es
mayor que 0, un precio negativo. Sin Servicios en el negocio: «Servicios no está activa en este
negocio.».
Implicados: Inventario, Servicios

### PRICING-F08 Cambiar o quitar un precio
<!-- origen: nuevo (Business Central, Shopify, Lightspeed y Odoo editan, desactivan y reactivan tarifas, precios y reglas; el producto actual no: «Cambios frente al producto actual») -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifa (detalle)
Pasos:
1. **Editar** en la fila: cambia **Precio** o **Desde la cantidad** y **Guardar**.
2. **Quitar** en la fila y confirma «Se quitará el precio de {artículo} desde {cantidad}. Se cobrará el de
   otra tarifa o el de la ficha.».
Entra: el precio, por su fila; el asistente, por la tarifa, el artículo y la cantidad mínima (1 si no la
dice).
Sale: `pricing.price_item.updated` o `pricing.price_item.removed`.
Si falla: «Ese artículo ya tiene precio en esta tarifa desde esa cantidad.», «Ese precio ya no
existe.». Los precios de una tarifa **desactivada** no se cambian (como no se añaden: «Esa tarifa no
está disponible…»): el detalle no ofrece **+** ni **Editar**, solo **Quitar**.
Implicados: ninguno

### PRICING-F09 Ver las reglas de descuento
<!-- origen: fi:modules/pricing#query-pricing-rules-list-expose_api old:pricing/WORKFLOW.md#pricing-f04 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, empleado, asistente
Pantalla: Tarifas
Pasos:
1. Baja hasta **Reglas de descuento**: las activas.
2. Busca, ordena o filtra (Estado **Inactivas** enseña las desactivadas).
Entra: las reglas del negocio; el nombre de la categoría, el producto o el grupo, al día.
Sale: nada.
Si falla: el aviso de la tabla con «Reintentar».
Implicados: Inventario, Clientes

### PRICING-F10 Crear una regla de descuento
<!-- origen: fi:modules/pricing#event-emitidos-price_list-created-price_item-added-rule-created-rule-deactivated fi:modules/pricing#command-pricing-rules-create old:pricing/WORKFLOW.md#pricing-f05 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas
Pasos:
1. **+** en «Reglas de descuento»: **Nueva regla de descuento**.
2. **Código** y **Nombre** (obligatorios; el código, único).
3. **Tipo** y su valor (las unidades son las del precio de cada artículo: kg en un café a 20 €/kg
   vendido en gramos; una unidad en lo que se vende por unidades y en los servicios):
   - **Porcentaje**: el % que se quita a la línea (hasta 100, dos decimales).
   - **Importe por unidad**: los euros que se quitan por cada unidad del precio vendida.
   - **Compra X, llévate Y**: «Compra» y «Gratis» (2 y 1 = cada 3 unidades, 1 gratis, hacia abajo).
   - **Por tramos**: hasta 10 tramos, cada uno con **Desde la cantidad** y **Porcentaje (%)** («Añadir
     tramo», «Quitar tramo»).
4. **Se aplica a**: Todo, Todos los productos, Todos los servicios, Una categoría, Un producto o Un
   servicio (con su buscador).
5. Si quieres: **Grupo de clientes** (solo para ellos; sin elegir, «Todos los clientes»), **Cantidad
   mínima**, **Desde**, **Hasta** y **Prioridad** (100 por defecto; a igual descuento, gana la de número
   menor).
6. **Crear**.
Entra: el formulario.
Sale: la regla activa y `pricing.rule.created`.
Si falla: debajo de su campo: «Ya existe una regla con ese código. Elige otro.», un valor que falta o
fuera de rango para su tipo, tramos repetidos o desordenados, una categoría, un producto o un servicio
que no existe, «Hasta» antes que «Desde».
Implicados: Inventario, Servicios, Clientes

### PRICING-F11 Editar una regla
<!-- origen: nuevo (Business Central, Shopify, Lightspeed y Odoo editan, desactivan y reactivan tarifas, precios y reglas; el producto actual no: «Cambios frente al producto actual») -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas
Pasos:
1. **Editar** en la fila: **Editar regla — {nombre}**.
2. Cambia lo que quieras y **Guardar**.
Entra: solo lo cambiado; el asistente nombra la regla por su código o su nombre.
Sale: la regla y `pricing.rule.updated` (sin cambios, nada).
Si falla: los mismos rechazos que al crear.
Implicados: Inventario, Servicios, Clientes

### PRICING-F12 Desactivar o reactivar una regla
<!-- origen: fi:modules/pricing#event-emitidos-price_list-created-price_item-added-rule-created-rule-deactivated fi:modules/pricing#command-pricing-rules-deactivate old:pricing/WORKFLOW.md#pricing-f06 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Tarifas
Pasos:
1. **Desactivar** y confirma «{nombre} dejará de aplicarse a las ventas nuevas.».
2. Para volver a usarla, filtra por **Inactivas** y pulsa **Activar**.
Entra: la regla.
Sale: `pricing.rule.deactivated` o `pricing.rule.activated`. Las ventas ya hechas no cambian.
Si falla: «Esa regla de descuento ya está desactivada.», «Esa regla de descuento ya está activa.» y, si
Clientes borró su grupo, «El grupo de clientes de esta regla ya no existe: elige otro grupo o quítaselo
antes de activarla.» (409 `pricing.rule_group_deleted`): sin grupo valdría para todos.
Implicados: Clientes

### PRICING-F13 Consultar el precio de una línea
<!-- origen: fi:modules/pricing#command-wasm-pricing-price_lists-get_price-get_price old:pricing/WORKFLOW.md#pricing-f07 -->
Estado: hecho (no tiene pantalla propia: lo pide quien vende o el asistente; Ventas aún no lo pide, ver «Contrato con Ventas»)
Actor: sistema (Ventas), asistente, empleado por la API
Pantalla: ninguna
Pasos:
1. Quien pregunta da el **producto** o el **servicio** (por id, nombre o SKU), y si quiere el
   **cliente**, la **cantidad** (1 por defecto), el **momento** (ahora por defecto) o una **tarifa**
   concreta.
2. Las tarifas candidatas son las activas, vigentes ese día, en euros y **de la base fiscal de la venta**
   (`tax_included`; con impuesto incluido si no lo dice, como en una caja) o que siguen al negocio, que
   valen para ese cliente: la general y las de sus grupos activos. Nunca se comparan precios de bases
   distintas (una general a 10,00 € con IVA no pierde contra una de empresa a 9,00 € sin IVA, 10,89 € con
   él). Con una tarifa concreta, solo esa (tiene que estar activa y vigente).
3. En cada candidata, el precio del tramo de cantidad mínima más alto que alcanza la cantidad. Gana
   **el precio más bajo**; sin ninguno, el de la ficha.
4. Las reglas candidatas son las activas, vigentes ese día, de ese artículo (por su alcance), sin grupo
   o de un grupo del cliente, y con la cantidad mínima alcanzada. Sus cantidades (importe por unidad,
   compra y gratis, tramos y mínimo) cuentan **en la unidad del precio**: en un café a 20 €/kg vendido
   en gramos, «0,50 € por unidad» es por kg, «compra 2, llévate 1» regala 1 kg de cada 3 kg (las unidades
   gratis se redondean hacia abajo) y un mínimo de 3 pide 3 kg. Se calcula el descuento de cada una
   sobre el importe de la línea y gana **el mayor** (a igual descuento, la de prioridad menor y después
   la de código menor). Solo una.
Entra: lo anterior; de Inventario, el producto (precio, unidad y escalón); de Servicios, el servicio
(por su consulta, con el permiso de quien pregunta); de Clientes, la ficha y sus grupos.
Sale: el precio de ficha, el precio de la línea y la tarifa de la que sale (o ninguna), si sus precios
llevan el impuesto, la divisa, el importe de la línea, el descuento y la regla que lo da, y el total.
No escribe nada ni avisa.
Si falla: un producto o un cliente que no existe (404), un nombre que vale para varios (409 con la
lista), una tarifa concreta que no existe, está desactivada o no está vigente ese día (409
`pricing.price_list_unavailable`), Servicios apagada (409 `pricing.services_unavailable`), una
cantidad que no es mayor que 0.
Implicados: Inventario, Servicios, Clientes, Ventas

### PRICING-F14 Cuando se borra un producto, una categoría o un grupo, o cambia un servicio
<!-- origen: nuevo (lo piden los borrados y cambios de Inventario, Clientes y Servicios sobre lo que señala una tarifa o una regla) -->
Estado: hecho (no tiene pantalla: lo hace la app sola, unos segundos después del cambio de la otra)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Inventario borra un producto (`inventory.product.deleted`): Tarifas quita sus precios de todas las
   tarifas y desactiva las reglas de ese producto.
2. Inventario borra una categoría (`inventory.category.deleted`): Tarifas desactiva sus reglas.
3. Clientes borra un grupo (`customer.group.deleted`): sus tarifas se quedan sin grupo y sus reglas se
   desactivan (nunca pasa a valer para todos un descuento de un grupo).
4. Servicios cambia un servicio (`service.service.updated`): Tarifas copia su nombre nuevo en sus
   precios y sus reglas.
Entra: el aviso.
Sale: `pricing.price_item.removed`, `pricing.rule.deactivated`, `pricing.price_list.updated` o
`pricing.price_item.updated` y `pricing.rule.updated`. Repetir el aviso no cambia nada.
Si falla: se reintenta solo, cada vez más espaciado (hasta una hora entre intentos), y tras ocho intentos se
da por perdido y queda anotado. Mientras tanto, un producto o una categoría borrados ya no salen en los precios
y un grupo borrado no vale para nadie (se mira al leer).
Implicados: Inventario, Clientes, Servicios

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien habla)
y la API, con las mismas reglas y los mismos permisos. Una tarifa se nombra por su id, su código o su
nombre («lista mayoristas»); una regla por su id, su código o su nombre; un producto por su id, su SKU
o su nombre; un servicio por su id o su nombre; un grupo por su id o su nombre («grupo VIP»); un cliente
por su id, su nombre, su teléfono o su correo. Si un nombre vale para varios, se dice cuáles
(`pricing.ambiguous_price_list`, `pricing.ambiguous_rule` o el de la app dueña).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio | En vivo |
|---|---|---|---|---|
| Las tarifas, con búsqueda, filtros y orden, en páginas de hasta 100 | ver | F01 | `pricing.price_list.list` | sí |
| Una tarifa | ver | F03, F06 | `pricing.price_list.get` | sí |
| Los precios de una tarifa, o los de un producto o un servicio en todas | ver | F06 | `pricing.price_item.list` | sí |
| Las reglas de descuento | ver | F09 | `pricing.rule.list` | sí |
| El precio de una línea (tarifa, regla, descuento y total) | ver | F13 | `pricing.price.resolve` | no |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea una tarifa | gestionar | F02 | `pricing.price_list.create` |
| Cambia una tarifa (solo lo enviado) | gestionar | F03 | `pricing.price_list.update` |
| Elige o quita la tarifa general | gestionar | F04 | `pricing.price_list.set_default` |
| Desactiva una tarifa | gestionar | F05 | `pricing.price_list.deactivate` |
| Reactiva una tarifa | gestionar | F05 | `pricing.price_list.activate` |
| Pone el precio de un producto o un servicio en una tarifa | gestionar | F07 | `pricing.price_item.add` |
| Cambia un precio | gestionar | F08 | `pricing.price_item.update` |
| Quita un precio | gestionar | F08 | `pricing.price_item.remove` |
| Crea una regla | gestionar | F10 | `pricing.rule.create` |
| Cambia una regla | gestionar | F11 | `pricing.rule.update` |
| Desactiva una regla | gestionar | F12 | `pricing.rule.deactivate` |
| Reactiva una regla | gestionar | F12 | `pricing.rule.activate` |
| Olvida un producto borrado | solo la plataforma | F14 | `pricing.catalog.forget_product` |
| Olvida una categoría borrada | solo la plataforma | F14 | `pricing.catalog.forget_category` |
| Olvida un grupo de clientes borrado | solo la plataforma | F14 | `pricing.catalog.forget_group` |
| Copia el nombre nuevo de un servicio | solo la plataforma | F14 | `pricing.catalog.refresh_service` |

Cuando el Hub tenga API keys (`erpk_live`), llegarán a las consultas, a crear y cambiar tarifas y a
poner, cambiar y quitar precios (para sincronizar precios desde otro sistema); elegir la general,
desactivar y las reglas, solo desde el Hub o el asistente.

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Tarifa nueva | Crear | `id`, `code`, `is_default` | `pricing.price_list.created` |
| Tarifa cambiada | Editar con algún cambio, o su grupo borrado | `id` | `pricing.price_list.updated` |
| Tarifa general cambiada | Elegirla o quitarla | `id`, `is_default`, `previous_id` | `pricing.price_list.default_changed` |
| Tarifa desactivada / reactivada | Desactivar / activar | `id` | `pricing.price_list.deactivated`, `…activated` |
| Precio puesto | Añadir | `id`, `price_list_id`, `product_id` o `service_id`, `min_quantity`, `price` | `pricing.price_item.added` |
| Precio cambiado | Editar, o el nombre nuevo de un servicio | `id` (o `service_id`) | `pricing.price_item.updated` |
| Precio quitado | Quitar, o el producto borrado | `id`, `price_list_id` | `pricing.price_item.removed` |
| Regla nueva | Crear | `id`, `code` | `pricing.rule.created` |
| Regla cambiada | Editar, o el nombre nuevo de un servicio | `id` | `pricing.rule.updated` |
| Regla desactivada / reactivada | Desactivar / activar, o su producto, categoría o grupo borrados | `id` | `pricing.rule.deactivated`, `…activated` |

Ninguna app los escucha salvo **Automatizaciones**, que puede arrancar una automatización con cualquiera
de ellos (FLOW-F21). Sus pasos también pueden consultar tarifas, precios, reglas y el precio de una
línea, y usar las acciones de Tarifas que no piden confirmación (FLOW-F11): crear o cambiar una tarifa,
poner o cambiar un precio y crear, cambiar o reactivar una regla.

### A qué reacciona y lo que necesita de otras apps
- **Inventario** (`requires`): los precios y las reglas apuntan a sus productos y categorías; Tarifas lee
  su nombre, SKU, unidad, escalón y precio de ficha. Reacciona a `inventory.product.deleted` y
  `inventory.category.deleted` (F14).
- **Clientes** (`requires`): una tarifa o una regla puede ser de un grupo; el precio de una línea lee los
  grupos activos del cliente (un grupo desactivado deja de dar sus precios y sus reglas). Si Clientes
  **borra** un grupo (`customer.group.deleted`), sus tarifas se quedan sin grupo y sus reglas se
  desactivan (F14); mientras tanto, un grupo que ya no existe no vale para nadie.
- **Servicios** (no es requisito): un precio o una regla de un servicio guarda su id y una copia de su
  nombre; el servicio se comprueba y su precio de ficha se lee con `service.service.get`, con la sesión
  de quien pide. Reacciona a `service.service.updated` (F14).
- De la plataforma: la zona horaria del negocio (el «hoy» de las fechas).

### Contrato con Ventas
Ventas **no** requiere Tarifas y Tarifas no toca Ventas. Lo que se pide a Ventas (no lo hace esta app):

1. En `sale.order.add_line` y `sale.order.add_service_line`, si Tarifas está activa, llamar **por
   nombre** (`call_app`, como hace con Facturación o Servicios) a `pricing.price.resolve` con el
   producto o el servicio, el cliente de la cuenta, la cantidad, el momento y **`tax_included` de la
   venta** (solo compiten las tarifas de esa base o que siguen al negocio); Tarifas apagada o ausente
   = el precio de la ficha, como hoy.
2. Congelar en la línea `unit_price` (el precio de la tarifa, en la misma unidad de precio que el de la
   ficha) y guardar `price_list_id`/`price_list_code` y el descuento automático (`discount`, en céntimos
   de esa línea, con `rule_id`/`rule_code`) aparte del descuento manual, para el tique.
3. Volver a pedirlo solo cuando cambien la cantidad de esa línea o el cliente de la cuenta, y nunca en
   una línea de precio libre, con `booked_price` de una cita o con un precio puesto a mano (Odoo).
4. El descuento manual de línea y el de la cuenta van **encima** (Shopify, Toast, Odoo), con el límite
   `max_discount_percent` de Ventas.
5. Las tarifas automáticas ya llegan de la base de la venta y en euros. Solo una tarifa pedida por su
   nombre puede venir en otra base o divisa: si `tax_included` de la respuesta no es `null` y no
   coincide con el de la venta, o la divisa no es la de la venta, no usar ese precio (409 propio de
   Ventas): Tarifas no convierte bases ni divisas.
6. En un servicio, el precio de la tarifa vale solo si el servicio es de precio fijo (los demás se
   teclean, como hoy) y por debajo de `booked_price` y del precio propio de la profesional, que siguen
   mandando.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver tarifas, precios y reglas, y consultar el precio de una línea | sí | sí | sí | sí | `pricing.view` |
| Crear, cambiar, elegir la general, desactivar y reactivar | sí | sí | sí | no | `pricing.manage` |

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `queries.py`,
  `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `tests/test_integration_*.py` con Inventario, Clientes y
  Servicios de verdad, `tests/test_concurrency.py` con hilos y `tests/test_relay.py` (PRICING-F14 de punta
  a punta: la operación real de la otra app, un tick real del worker y su relay, la reacción una sola vez y
  el hub B sin tocar al A). En Chrome, `tests/e2e/pricing-flows.spec.ts` (un test por flujo con pantalla,
  PRICING-F01 a F12, con sus capturas en tres tamaños) y `tests/e2e/pricing-lists.spec.ts` (de la tarifa al
  precio de una línea, PRICING-F13).
- **`requires = ["inventory", "customer"]`**: las claves ajenas a `inventory.Product` e
  `inventory.Category` las justifica leer el nombre, el SKU, la unidad y el precio al día; de Clientes se
  leen sus modelos (la ficha, sus grupos y el nombre de un grupo). **Servicios no es requisito**: un
  restaurante que enciende Tarifas no tiene por qué encender Servicios y Personal; el servicio es un
  UUID opaco con copia del nombre (precedente PLAN §20.5, el de Ventas).
- **El grupo es un UUID, no una clave ajena**: Clientes borra los grupos de verdad
  (`customer.group.delete`), y con una clave ajena su borrado leería las tablas de Tarifas, que en un
  hub sin Tarifas no existen (fase 2). Las variantes de base de datos de Django 6.1 (`DB_SET_NULL`) no
  sirven: `fields.E323` exige la misma variante en toda la cadena y los modelos de Inventario usan las
  de Python. Productos y categorías solo se borran de verdad desde el admin (Inventario los borra
  lógicamente): sus claves ajenas son `CASCADE`.
- Modelos: `PriceList` (código único sin distinguir mayúsculas, `tax_included` a tres valores,
  `customer_group_id`, fechas, `is_default`, `is_active`), `PriceItem` (tarifa, producto **o** servicio, `min_quantity`
  decimal de tres cifras como Inventario, precio en céntimos) y `DiscountRule` (tipo, valor por tipo,
  alcance, grupo, cantidad mínima, fechas, prioridad). UUIDv7, sin `hub_id`.
- **Una sola tarifa general**: índice único parcial (`is_default` verdadero) y restricción «la general
  no tiene grupo ni está inactiva». Elegirla baja la anterior y sube la nueva en un punto de guardado;
  si otra elección gana la carrera (el índice lo dice), se repite: queda la última.
- **Códigos únicos** con índice sobre `Lower(code)`; dos altas a la vez con el mismo código → una 409
  `pricing.duplicate_code`.
- **Lo que una escritura nombra lo retiene** (`held` de Inventario, `FOR KEY SHARE`, hasta el COMMIT):
  la categoría o el producto de una regla al crearla o editarla, el producto de un precio al ponerlo y el
  grupo de una tarifa o de una regla al crearlas, editarlas o activar la regla. Su borrado (el «Eliminar»
  de Inventario o de Clientes, o el del admin) espera a la escritura; uno que ya estaba en curso al leerla
  la deja como no encontrada, igual que una borrada antes (422 `invalid_field` en su campo; un precio,
  404; activar, 409 `pricing.rule_group_deleted`). Nunca el `IntegrityError` crudo ni una regla, un precio
  o una tarifa colgados de algo borrado (`tests/test_concurrency.py`).
- **Dinero en céntimos**, mitad hacia arriba, una vez por magnitud; el importe de la línea es
  `precio × (cantidad en la unidad del precio) ÷ price_quantity` con las fracciones exactas de
  `apps.inventory.models.UNIT_SPECS`, como Ventas. Divisa ISO 4217 de dos decimales (`pycountry` y
  `babel`, ya dependencias).
- El «hoy» es `timezone.localdate()` (fase 1: `TIME_ZONE` = Europe/Madrid); `pricing.price.resolve`
  toma `when` y los tests nunca leen el reloj real.
- Asistente: toda operación declara `ai={"description"…}` (`risk` solo en las acciones: `high` en
  elegir o quitar la general, desactivar o activar una tarifa, quitar un precio y desactivar una regla) y
  todo campo de entrada lleva `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre los tres modelos (ronda 12, PLAN §17); una
  escritura cruda del admin no deja aviso ni comprueba reglas, salvo los tramos de una regla, que lee
  como la API (`schemas.Tier`, hasta 10, cantidad creciente) porque el precio de una línea los lee así.
- La marca de la general la toma `_take_default_mark` en un punto de guardado; tras 3 carreras perdidas,
  409 `pricing.default_busy` (nunca el `IntegrityError` crudo).
- Cantidades de las reglas: `Article.measure` (la cantidad en `pricing_unit`, con las fracciones exactas
  de `UNIT_SPECS`); el importe de la línea usa además `price_quantity` (`Article.ratio`). Los tramos de
  una tarifa siguen en la unidad propia del producto, que la tabla pinta junto a la cantidad («500 g»).
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo.
- **Orden de las tablas** (`_ordering`, nota vigente del producto actual del 2026-09-28, hub#2355, como Ventas,
  Caja, Inventario y Tareas): la columna elegida y después el desempate, todo en la dirección de la lista y
  con los vacíos al final en las dos; `desc` es `asc` leído al revés, empates incluidos. Tarifas y reglas
  desempatan por código e `id`; los precios, por cantidad mínima e `id`. Lo fijan los tres
  `test_tied_*` de `tests/test_queries.py` (hasta CLOSE-PRICING desempataba siempre en ascendente).

## Contradicciones señaladas (no se resuelven aquí)

- **Fase 1 comparte las tablas entre hubs** (estado del repo, como `demo`): lo que se separa por ámbito
  son los avisos en vivo; la frontera de una BD por hub llega en la fase 2. Este WORKBOOK describe el
  comportamiento de un hub.
- **`@operation` hoy no lanza `AppInactive`**: con Servicios instalada pero apagada, `service.service.get`
  responde igual; `pricing.services_unavailable` solo salta si Servicios no está instalada
  (`UnknownOperation`). El «Servicios no está activa en este negocio» de PRICING-F07 depende de que la
  plataforma compruebe la app activa (fase 2).
- **Ventas no llama a Tarifas** (pricing#9 sigue abierto): ninguna app llama a `pricing.price.resolve`
  (`git grep` en `origin/main`); el `pricing` de Ventas es su propia valoración (`apps/sale/pricing.py`). El
  TPV cobra el precio de la ficha. PRICING-F13 es `hecho` como consulta (su test y `pricing-lists.spec.ts`);
  engancharla es de Ventas, con «Contrato con Ventas» como encargo.
- **API keys**: el Hub aún no las tiene (`config/api.py`: «API keys (`erpk_live`) come in phase 2»).
  `expose_api` marca lo que alcanzarán (`EXPOSED` en `tests/test_apps.py`).
- **«Asistente» en los flujos** (actor de casi todos y el ejemplo de voz): es la operación con `ai=` y su
  ruta de la API; el asistente del Hub aún no existe (la misma lectura de los cierres de Demo, Servicios,
  Menús y Tareas).
- **Fase 2 y las claves ajenas hacia Inventario** (`PriceItem.product`, `DiscountRule.product` y
  `DiscountRule.category` en `CASCADE`): con «tablas al activar», el borrado físico de un producto o de una
  categoría (el admin del Hub) en un hub donde Tarifas nunca se creó consultaría tablas que no existen. El
  grupo ya es un UUID por eso mismo; lo anotó el «Para PLAN-DB» de
  `docs/plans/2026-10-14-migracion-modulos.md` (Suplementos, Menús, Cocina y Tarifas) y PLAN-DB aún no lo
  recoge.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/pricing/lists` (las dos tablas, `ListsPage` con `PriceListsTable` y
  `RulesTable`) y `/pricing/lists/:id` (el detalle, `ListDetailPage`, con el id como prop).
- Las confirmaciones de la tarifa (hacer general, desactivar) viven en `ListConfirm`, que comparten la
  tabla y el detalle.
- Las tres tablas llevan sus filtros detrás del embudo (`filterable`, como la tabla del producto actual), y
  las de tarifas y reglas abren con «Activas» elegido: su opción vacía («Todos») pide todas.
- Listas en vivo con `useLiveList` (ventanas de 100 filas, cada una su suscripción) y `useServerTable`;
  escrituras con `useCommand`; formularios con `FormModal`, confirmaciones con `ConfirmDialog` y
  buscadores con `Combo` (productos y categorías de Inventario, servicios de Servicios, grupos de
  Clientes, por sus consultas).
- Importes con `MoneyInput` (lo que teclea una persona, en céntimos) y el formato del idioma (`Intl`),
  con los millares agrupados desde cuatro cifras también en español («1.234,56 €»; el CLDR espera a cinco:
  hub#1090), como Cobro en línea.
- Icono: `ion:pricetags-outline` (registrado); el `pricetag` del producto actual espera en
  `UI-REQUESTS.md`.

## Lo que NO hace, a propósito

- **No cambia lo que cobra Ventas** hasta que Ventas lo pida (ver «Contrato con Ventas»).
- **No hace descuentos por importe del tique** («gasta 50 € y llévate un 10 %»): necesita el tique
  entero; el descuento de la cuenta es de Ventas.
- **No hace horarios** (happy hour por días u horas): solo fechas.
- **No convierte divisas ni bases fiscales**: lo dice en la respuesta y decide quien vende.
- **No tiene reglas por categoría de servicio**: por servicio, por todos los servicios o por todo.
- **No borra tarifas ni reglas**: se desactivan y se reactivan (los precios sí se quitan).

## Cambios frente al producto actual

| Producto actual | Ahora | Por qué |
|---|---|---|
| Segmento de la tarifa (particular, empresa, mayorista, minorista), que nadie enviaba | **Grupo de clientes** de Clientes | Es lo que hacen Business Central, Lightspeed y Shopify; Clientes ya tiene grupos y el segmento nunca se enlazó |
| La tarifa por defecto no influía en nada | **Tarifa general**: vale para todos | Business Central «todos los clientes», Odoo «por defecto del TPV» |
| Gana el precio más bajo de todas las tarifas activas, sin fechas, comparando divisas sin convertir | El más bajo de las que valen para ese cliente, **vigentes** y en euros | Las fechas se guardaban y no se miraban; 90 USD «ganaban» a 100 EUR |
| Tramos con mínimo y máximo en millonésimas | **Cantidad mínima** decimal, en la unidad del producto; el tramo acaba donde empieza el siguiente | Business Central y Odoo; la cantidad es la de Inventario y Ventas |
| El artículo era un texto libre sin comprobar | **Producto de Inventario** o **servicio de Servicios**, comprobados | El precio de un artículo que no existe no lo cobraba nadie |
| Reglas en cadena por prioridad sobre el importe del tique, con mínimo y máximo de importe | **Una regla por línea, la mejor para el cliente**; prioridad como desempate; cantidad mínima | Square, Shopify, Toast y Lightspeed; las quejas de los foros |
| Alcance «categoría» que no filtraba nada | Todo, todos los productos, todos los servicios, categoría, producto o servicio, que **sí** filtran | |
| Por tramos sobre el importe; «compra X, llévate Y» con cantidad y precio en el texto de condiciones | Por tramos **de cantidad**; «compra X, llévate Y» con la cantidad de la línea, contada en la unidad del precio (kg en lo que se vende al peso) | Las condiciones eran JSON libre que nadie validaba; ver «Referencia adoptada» para el peso |
| Las bases fiscales mezcladas se rechazaban con un error genérico (`mixed_tax_basis`) | Solo compiten las tarifas de la base de la venta (`tax_included`) o que siguen al negocio | Nunca se comparan precios con y sin impuesto |
| `pricing.rules.calculate_discount` (descuento de un importe y su reparto por líneas y tipos) | Quitado: el descuento automático es por línea (`pricing.price.resolve`) | El reparto del descuento de la cuenta ya lo hace Ventas (`pricing.allocate`): no se duplica |
| `get_price` era una orden con rechazos genéricos | `pricing.price.resolve`, consulta, con sus códigos de error | |
| Sin editar ni desactivar tarifas, sin editar ni reactivar reglas, sin pantalla de precios ni alta de reglas | Editar y desactivar tarifas, editar y reactivar reglas, **detalle de la tarifa** con sus precios y **alta de reglas** en pantalla | Lo que hacen todos los productos de la tabla |
| Permisos `pricing.view_pricing`, `manage_pricing`, `apply_pricing` | `pricing.view` y `pricing.manage` | Todos los papeles que veían aplicaban |
| Servicios `pricing.price_lists.*`, `pricing.rules.*` | `pricing.price_list.*`, `pricing.price_item.*`, `pricing.rule.*`, `pricing.price.resolve` (en singular) | Convención de nombres; los avisos `pricing.price_list.created`, `pricing.price_item.added`, `pricing.rule.created` y `pricing.rule.deactivated` se conservan |
| Divisa libre de tres letras | Divisa ISO 4217 con dos decimales | Los importes se teclean y se leen con dos decimales |
| Alta en el panel lateral de la tabla | Alta y edición en un formulario (`FormModal`) | Ver `UI-REQUESTS.md` |
