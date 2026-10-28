# Workbook — Inventario (app)
Prefijo: INVENTORY
Alcance MVP: transversal
Estado de la app: en uso; parcial F12 (espera al núcleo)

> Manual de usuario y especificación de la app `inventory`. Se escribe **antes** que el código: no
> se programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en
> verde. Parte del `WORKFLOW.md` del módulo Inventario del producto actual (`modules-workspace`,
> `origin/main` `272e57f`, 08/10/2026). La app hace lo mismo y se ve igual; corrige los fallos que
> ese documento tenía anotados (lista en [Cambios frente al producto actual](#cambios-frente-al-producto-actual))
> y deja en [Dudas abiertas](#dudas-abiertas) lo que el producto todavía no ha decidido.

## Para qué sirve y para quién

Inventario es el catálogo de lo que se vende con existencias: cada producto con su nombre, su SKU,
su precio, su coste, su categoría fiscal, su unidad de medida y cuántas unidades quedan.

- En el **restaurante** es **la carta**: los platos y las bebidas que el TPV enseña agrupados por
  categoría y que Cocina envía a su estación.
- En la **peluquería** son **los productos de venta** (champú, cera, tinte de reventa). Los
  servicios de la peluquería no viven aquí: viven en Servicios.

Cada cambio de stock (stock inicial, recepción, venta, anulación, recuento, baja) deja un
**movimiento** que no se puede editar ni borrar, y el saldo de cada producto se explica por ellos.

Quién la usa:

- El **administrador** y el **responsable** dan de alta y cambian productos y categorías, importan
  y exportan el catálogo, reciben mercancía, cuentan stock y guardan los ajustes.
- El **empleado** y el **cajero** solo consultan productos, categorías y movimientos.

Las ventas no se hacen aquí: el stock baja solo cuando Ventas cobra. Inventario **no es
obligatorio para vender**: sin él, el TPV cobra servicios y líneas a precio libre.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó. De la referencia del restaurante se
adopta la carta por categorías, el control de stock por artículo y el recuento con motivo
([Lightspeed — Practice run checklist](https://resto-support.lightspeedhq.com/hc/en-us/article_attachments/360044738513))
y el «agotado» del artículo
([Square — disponibilidad](https://squareup.com/help/us/en/article/8495-beta-item-availability)),
pero no la cantidad restante en el TPV, que aquí no existe. Además:

- **Agotado («86») aparte de activo**: el artículo sigue en la carta con su interruptor encendido, el
  TPV deja de ofrecerlo y vuelve con un toque cuando hay otra vez: Square «Sold out», Toast «86»,
  Lightspeed «Unavailable», TouchBistro y Revel. Lo pone y lo quita una persona; ninguno lo quita solo
  al recibir mercancía.
- **La cifra de una categoría cuenta lo que se ve, agotados incluidos**: el TPV enseña lo agotado en
  gris y sin poder pedirlo ([Square](https://squareup.com/help/us/en/article/8430),
  [Toast](https://support.toasttab.com/en/article/86-an-Item),
  [Lightspeed](https://o-series-support.lightspeedhq.com/hc/articles/31329314792987),
  [SumUp](https://help.sumup.com/en-US/articles/WcT1PpyBZHREhzgn7Wstl)), y donde hay cifras siguen a lo
  que se enseña: WooCommerce solo deja fuera lo agotado de su cifra cuando lo oculta
  ([wc_recount_after_stock_change](https://wp-kama.com/plugin/woocommerce/function/_wc_term_recount)),
  y la queja de los foros es siempre una cifra que no cuadra con lo que se ve ([GeneratePress](https://generatepress.com/forums/topic/product-count-wrong-on-category-view/),
  [WoodMart](https://xtemos.com/forums/topic/out-of-stock-query-and-products-issue/),
  [Shopify](https://community.shopify.com/t/some-products-only-visible-when-customising-collection-page-not-front-end/373545)).

- **Control de stock por artículo, con un valor por defecto del negocio**: Square «Track stock»,
  Odoo «Track Inventory», Business Central, Shopify «Track quantity», WooCommerce «Manage stock?».
- **Importar con mapeo de columnas, ensayo e informe antes de crear nada**: el «Test import» de
  Odoo, el mapeo con columnas obligatorias de WooCommerce y Lightspeed, y el resumen de Shopify.
- **Borrar una categoría desvincula sus artículos; no los borra ni lo impide**: Shopify,
  WooCommerce, Square, Lightspeed, Toast y Vagaro.
- **Un menú o un pack mueve el stock de sus componentes, nunca el suyo**: el kit de Odoo, Shopify
  Bundles, WooCommerce Product Bundles y Square.
- **Libro de movimientos que no se edita y recuento absoluto con motivo**; **cantidades exactas
  con un escalón por unidad** (fracciones exactas, como SAP).
- **La categoría fiscal se elige por su tipo** («Producto — general · 21 %»), como Square,
  Lightspeed, Odoo y Holded.
- **La unidad de un producto con stock no se cambia**: Odoo lo impide en cuanto el producto tiene
  movimientos; aquí basta con que su stock sea cero.

## Antes de empezar

- **Impuestos** es imprescindible: cada producto apunta a una categoría fiscal suya. Para activar
  Inventario hace falta Impuestos, y no se puede desactivar Impuestos mientras Inventario esté
  activo. De fábrica, Impuestos trae las categorías de España.
- **Ventas** no depende de Inventario. Con las dos activas, el TPV vende desde este catálogo y la
  venta baja el stock (INVENTORY-F21). **Cocina** sí necesita Inventario: decide qué va a cada
  estación por producto y por categoría.
- **Impresión**, solo para la etiqueta del código de barras: una impresora con la función
  «Etiqueta» (INVENTORY-F25).
- Al activar Inventario, el negocio recibe las unidades de medida (unidad, kilo, gramo, tonelada,
  litro, mililitro, minuto y hora), y la lista «Termina de configurar tu negocio» pide el primer
  producto (INVENTORY-F28).

Configuración inicial, paso a paso:

1. En **Inventario → Ajustes** decide «Controlar stock» y «Permitir vender sin stock»
   (INVENTORY-F19). Lee antes lo que hace de verdad cada uno.
2. Carga la carta o el catálogo: con la plantilla de tu sector (INVENTORY-F12), con un CSV
   (INVENTORY-F09) o a mano (INVENTORY-F01).
3. Crea las categorías que agrupan la carta en el TPV (INVENTORY-F06) y asígnalas
   (INVENTORY-F08).
4. Comprueba que ningún producto sale «Sin configurar» (INVENTORY-F05).
5. Da el stock de partida con «Contar stock» (INVENTORY-F14) o con el «Stock inicial» del alta: los
   dos dejan su movimiento.
6. Haz una venta de prueba y comprueba en **Movimientos** que el stock bajó (INVENTORY-F21).

## Pantallas

Inventario se abre desde el menú **Inventario** y tiene cinco pestañas: **Panel**, **Productos**,
**Movimientos**, **Categorías** y **Ajustes**. Todas se ven con solo poder ver productos, salvo
Ajustes (abajo); lo que una persona no puede hacer no aparece en pantalla, y además la app lo
rechaza aunque alguien lo intente por otra puerta (el asistente o la API).

### Panel
Cifras de arriba: «Productos seguidos», «En stock», «Agotados», «Stock bajo» y «Valor de
existencias» («a coste»). Las cuatro primeras llevan a Productos. Si hay artículos con control de
stock sin coste, la nota «N producto(s) sin coste registrado: el valor mostrado es parcial».
Debajo, la tabla «Productos con stock bajo» (Nombre, SKU, Stock, Umbral), 5 por página.
Vacía: «Sin productos en stock bajo.». Cargando: «Cargando…». Error: «No se pudieron cargar las
métricas del inventario.» y el aviso de la tabla con «Reintentar».

### Productos
Tabla con Nombre, SKU, Precio, Stock («—» en un artículo sin control de stock) y Estado: un
interruptor activo/inactivo, «Sí»/«No» para quien no puede cambiar productos, o la marca «Sin
configurar · Falta la categoría fiscal»; a su lado, la insignia roja «Agotado» si el artículo está
agotado. Buscador «Buscar producto…» por nombre o SKU; orden por columna; filtros por nombre, SKU,
precio desde/hasta, stock desde/hasta y estado («Sí», «No», «Sin configurar», «Agotado»); 50 por
página; vista de tabla o de tarjetas.

Botones de la tabla: **+** (dar de alta), importar CSV y exportar CSV, cada uno solo para quien
tiene ese permiso. Por fila: «Detalles», «Recibir stock» y «Contar stock» (con permiso de stock y
solo en productos físicos), «Dar de baja stock» (además, solo en artículos con control de stock),
«Editar», «Marcar agotado» o, si ya lo está, «Volver a poner a la venta» (en el menú «⋮», para quien
puede cambiar productos) y «Eliminar». Tocar la fila abre la ficha.

El **+** y «Editar» abren el panel lateral del formulario: Nombre, SKU (bloqueado al editar: «El
SKU es la identidad del producto: no se edita»), Precio, «Coste (<moneda>)», «Stock inicial» (solo al
crear), «Umbral stock bajo», «EAN-13», «Descripción», «Tipo» («Físico» o «Servicio», solo al
crear), la casilla «Controlar stock de este artículo» con su nota, «Unidad de medida», «Categoría
fiscal» («Elige una categoría fiscal») y «Categorías» (si hay alguna), y «Guardar» / «Guardar
cambios» («Guardando…»).

Vacía: «Sin productos». Cargando: «Cargando…». Error: el aviso de la tabla con «Reintentar». Un
rechazo del formulario sale dentro del panel; el de una acción de fila, encima de la tabla.

### Ficha del producto
Ventana con el nombre del producto: SKU, Precio, Stock y Estado («Sí · Agotado» si está agotado); el
código de barras del SKU en una placa blanca con el SKU debajo; «Imprimir código de barras» y, con
permiso de stock y en un producto físico, «Recibir stock» y «Contar stock», y «Dar de baja stock» si
el artículo controla su stock; con permiso para cambiar productos, «Marcar agotado» o «Volver a poner
a la venta». Un fallo al imprimir o al marcar sale dentro de la ventana.

### Recepción
Ventana «Recepción — <producto>»: «Stock actual», «Cantidad recibida», «Coste unitario (<moneda>)» y
«Registrar recepción». Un rechazo sale dentro de la ventana.

### Recuento
Ventana «Recuento — <producto>»: «Stock actual», «Diferencia» (en cuanto hay cifra), «Stock
contado», «Motivo (obligatorio)» y «Aplicar recuento», con la nota de lo que falta («Escribe el
stock contado para continuar.» / «Hace falta un motivo para aplicar el recuento.»). Un rechazo
sale dentro de la ventana.

### Baja
Ventana «Baja — <producto>»: «Stock actual», «Cantidad que se da de baja», «Motivo: merma, rotura,
consumo propio… (obligatorio)» y «Dar de baja», con la nota de lo que falta. Un rechazo sale dentro
de la ventana.

### Importar productos
Tres ventanas seguidas:

1. «Revisa la importación»: un desplegable por columna del fichero («No importar» o el campo;
   Nombre y SKU llevan asterisco), «Primeras {n} filas de {total}», el resumen «{ready} fila(s)
   listas · {failed} con problemas» con hasta 10 motivos, e «Importar {n} producto(s)» y
   «Cancelar».
2. Si hace falta, «Categorías fiscales del CSV»: un bloque por texto fiscal no reconocido (o
   «Filas sin categoría fiscal») con «Elegir» / «Crear» / «Omitir», y «Confirmar e importar».
3. Mientras crea, encima de la tabla: «Importando {done}/{total}…» con «Parar». Al final,
   «Resultado de la importación»: «Filas», «Creadas», «Omitidas (ya existían)», «Fallidas», una
   línea por fila fallida («Línea N · SKU — motivo») y «Copiar informe».

### Movimientos
Tabla de solo lectura: Fecha, Nombre, SKU, Tipo («Inicial», «Recepción», «Venta», «Anulación»,
«Recuento», «Descuento», «Devolución»), Cantidad (con signo), Saldo, Motivo y Referencia (en una venta, el número
de su tique, su factura o la propia venta). Buscador por producto, SKU, referencia o número de
tique; filtros por Tipo y por Referencia; más recientes primero; 50 por página.

Vacía: «Todavía no hay movimientos. Aparecen al usar Recibir stock o Contar stock en un producto de
Productos, y con cada venta.». Sin coincidencias: «Ningún movimiento coincide con la búsqueda o los
filtros. Una venta se encuentra por el número de su tique, factura o venta.». Error: el aviso de la
tabla con «Reintentar».

### Categorías
Tabla con Nombre, Slug y Productos (cuántos activos tiene, agotados incluidos: la misma cifra que la
tira de categorías del TPV, que también los enseña); buscador «Buscar categoría…»; 25 por página; importar y
exportar CSV. El **+** y la fila (o «Editar») abren el panel: Nombre, «Slug
(opcional)», «Tipo de IVA / Impuesto» («— (por defecto)» o una categoría fiscal), «Cancelar
edición» y «Guardar» / «Guardar cambios». «Eliminar» abre «Eliminar categoría» con lo que va a
pasar y «Eliminar y desvincular» / «Cancelar». Vacía: «Sin categorías.». Cargando: «Cargando…».

### Ajustes
Cabecera «Inventario» con «Permitir vender sin stock», «Umbral de stock bajo» (con su explicación)
y «Controlar stock», y «Guardar». La ve y la guarda quien puede gestionar los ajustes del
inventario: de fábrica, el administrador y el responsable. Al empleado y al cajero no se les enseña
la pestaña; si escriben su dirección, ven «Esta página no existe». Cargando: «Cargando ajustes…».
Error: «No se pudieron cargar los ajustes.» con «Reintentar», nunca los valores de fábrica como si
fueran los del negocio.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (en Ajustes, «Cargando ajustes…») mientras llega el primer resultado. |
| Vacío | Productos: «Sin productos»; Movimientos: «Todavía no hay movimientos. Aparecen al usar Recibir stock o Contar stock en un producto de Productos, y con cada venta.»; Categorías: «Sin categorías.»; Panel: «Sin productos en stock bajo.». Con búsqueda o filtros sin resultado, la tabla dice que nada coincide. |
| Error | Panel: «No se pudieron cargar las métricas del inventario.»; Ajustes: «No se pudieron cargar los ajustes.»; las tablas, su aviso con «Reintentar». Un rechazo de una acción sale en su ventana, junto a su campo, o encima de la tabla. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva | «Esta app no está activa en este negocio» en lugar de las cifras y de la tabla. |
| Sin permiso | No aparece lo que no puede hacer (ni **+**, ni importar o exportar, ni las acciones de stock, ni el interruptor: «Sí»/«No»); Ajustes no sale y su dirección dice «Esta página no existe»; si pierde el permiso con Ajustes abierto, los campos se bloquean con «No tienes permiso para cambiar estos ajustes. Pídeselo a un administrador si lo necesitas.». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| | **Catálogo** | |
| INVENTORY-F01 | Dar de alta un producto | hecho |
| INVENTORY-F02 | Editar un producto | hecho |
| INVENTORY-F03 | Activar y desactivar un producto | hecho |
| INVENTORY-F04 | Eliminar un producto | hecho |
| INVENTORY-F05 | Revisar los productos que no se pueden vender por falta de IVA | hecho |
| INVENTORY-F06 | Crear y editar una categoría | hecho |
| INVENTORY-F07 | Eliminar una categoría | hecho |
| INVENTORY-F08 | Agrupar productos en categorías para el TPV | hecho |
| INVENTORY-F29 | Marcar un artículo como agotado | hecho |
| | **Importar y exportar** | |
| INVENTORY-F09 | Importar productos desde un CSV | hecho |
| INVENTORY-F10 | Importar categorías desde un CSV | hecho |
| INVENTORY-F11 | Exportar el catálogo a CSV | hecho |
| INVENTORY-F12 | Cargar la carta de una plantilla del sector | parcial — la parte de Inventario está (el alta en lote con su stock y sus categorías, que salta los SKU que ya existen); falta cargar la plantilla del sector, que es del núcleo y el Hub todavía no tiene |
| | **Stock** | |
| INVENTORY-F13 | Recibir mercancía | hecho |
| INVENTORY-F14 | Contar el stock de un producto | hecho |
| INVENTORY-F15 | Dar de baja stock sin venta (merma, rotura, consumo propio) | hecho |
| INVENTORY-F16 | Consultar el historial de movimientos | hecho |
| INVENTORY-F17 | Ver el panel y los productos con stock bajo | hecho |
| INVENTORY-F18 | Avisar cuando un artículo cruza su mínimo | hecho |
| INVENTORY-F19 | Ajustar el inventario | hecho |
| INVENTORY-F20 | Decidir qué artículos llevan control de stock | hecho |
| | **Con otras apps** | |
| INVENTORY-F21 | Bajar el stock al cobrarse una venta | hecho |
| INVENTORY-F22 | Bajar el stock de los componentes de un menú o un pack | hecho |
| INVENTORY-F23 | Reponer el stock al anularse una venta | hecho |
| INVENTORY-F24 | Reponer el stock de una devolución | hecho |
| INVENTORY-F25 | Imprimir la etiqueta del código de barras | hecho |
| INVENTORY-F26 | Vender al peso o por medida: unidades y escalón | hecho |
| INVENTORY-F27 | Entregar el catálogo al TPV, a Cocina y a Menús | hecho |
| INVENTORY-F28 | Completar el primer paso «Tu catálogo» | hecho |

Todos los flujos son comunes a los dos verticales (restaurante y peluquería).

### INVENTORY-F01 Dar de alta un producto
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 qa:verticals/restaurant/03-menu-and-prices fi:modules/inventory#command-inventory-products-create old:inventory/workflow/catalogo.md#inventory-f01 qa:modules/inventory/create-product-with-vat wf:peluqueria-dia#rec_peluqueria-f04 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En **Productos**, pulsa **+**: se abre el panel del formulario.
2. Escribe Nombre, SKU y Precio. El precio admite «2,20», «1.234,56» o lo que se pegue de la
   pantalla; al salir del campo se reescribe en el formato del negocio. Son opcionales «Coste
   (<moneda>)» (la del negocio: «Coste (PLN)» en Polonia), «Stock inicial», «Umbral stock bajo» (vacío = 10), «EAN-13» y «Descripción».
3. Elige «Tipo» («Físico» o «Servicio»), la «Unidad de medida» («Unidad (ud)» de entrada) y la
   «Categoría fiscal». Cada categoría fiscal dice su tipo («Producto — general · 21 %», «… ·
   exento») y no hay ninguna elegida de antemano.
4. En un producto físico, la casilla «Controlar stock de este artículo» sale marcada o no según el
   ajuste del negocio, con la nota «Sigue el ajuste del hub». Tocarla fija la decisión para este
   artículo (INVENTORY-F20).
5. Si hay categorías, busca en «Categorías» las que agrupan el producto en el TPV y elígelas una a
   una: cada una sale debajo del campo, con su botón para quitarla.
6. Pulsa «Guardar» («Guardando…»). El panel se cierra y el producto sale en la tabla con Estado
   «Sí».
Entra: las categorías fiscales y su tipo, de Impuestos; las unidades de medida y las categorías de
producto, de Inventario.
Sale: el producto, activo y enlazado a las categorías marcadas, en un solo paso: o se guarda
entero o no se guarda nada. Si se dio stock inicial, queda en **Movimientos** como «Inicial».
Inventario avisa a las demás apps de que hay un producto nuevo: Ventas lo ofrece en la rejilla del
TPV y el paso «Tu catálogo» de la puesta en marcha queda hecho (INVENTORY-F28).
Si falla: «Guardar» está apagado mientras falten Nombre, SKU o categoría fiscal. Sin categorías
fiscales sale «Todavía no hay categorías fiscales. Créalas en Impuestos: un producto no se puede
vender sin saber cómo tributa.». Un importe ilegible: «Esto no es un importe. Escribe una cifra,
por ejemplo 12,50.» o «Este importe se puede leer de dos maneras…». Una cantidad que no encaja en
la unidad: «La cantidad no respeta el incremento permitido para esta unidad». Un SKU que ya tiene
otro producto vivo: «Ese SKU ya existe en el catálogo»; un EAN-13 repetido: «Ese EAN-13 ya lo tiene
otro producto del catálogo». Una categoría fiscal que ya no está en Impuestos se rechaza, también si
llega por el asistente o la API. Todo rechazo sale dentro del panel y no se guarda nada.
Implicados: SALE-F01, TAX-F01, TAX-F19

### INVENTORY-F02 Editar un producto
<!-- origen: fi:modules/inventory#command-inventory-products-update fi:modules/inventory#query-inventory-products-get old:inventory/workflow/catalogo.md#inventory-f02 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En **Productos**, pulsa «Editar» en la fila (o toca la marca «Sin configurar»): se abre el panel
   «Editando producto — <nombre>» con los datos actuales.
2. Cambia lo que haga falta. El SKU está bloqueado («El SKU es la identidad del producto: no se
   edita»). El stock no se edita aquí: se recibe (INVENTORY-F13) o se cuenta (INVENTORY-F14). El
   «Tipo» y el «Stock inicial» no salen.
3. Pulsa «Guardar cambios». «Cancelar edición» o cerrar el panel lo deja como estaba.
4. La fila enseña los datos nuevos.
Entra: el producto tal como está guardado; las categorías fiscales, de Impuestos; las unidades y
las categorías de producto.
Sale: el producto cambiado, con sus categorías, en un solo paso. Inventario avisa del cambio y de
cada categoría añadida o quitada. El precio nuevo vale para lo que se añada a una cuenta desde
ahora: una cuenta abierta conserva el precio de cuando se pidió (lo decide Ventas).
Si falla: los mismos rechazos que el alta (INVENTORY-F01), dentro del panel, y no se guarda nada.
Vaciar la categoría fiscal no se puede: «Elige la categoría fiscal: sin ella el producto no se
puede vender.». La unidad de un producto con stock no se cambia: «No se puede cambiar la unidad de
un producto con stock. Cuenta su stock a cero y cámbiala después.».
Implicados: SALE-F01, TAX-F01, TAX-F19

### INVENTORY-F03 Activar y desactivar un producto
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 old:inventory/workflow/catalogo.md#inventory-f03 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En **Productos**, toca el interruptor de la columna Estado de la fila.
2. Apagado, el producto pasa a «No»; encendido, a «Sí». Un producto «Sin configurar» no tiene
   interruptor hasta que tenga categoría fiscal (INVENTORY-F05).
Entra: el producto.
Sale: el producto activo o inactivo; Inventario avisa del cambio. Inactivo, deja de salir en el TPV
y en el catálogo de venta, en las cifras del Panel, en la lista de stock bajo y en el número de
productos de cada categoría. Sigue en Productos y en sus movimientos.
Si falla: el motivo sale encima de la tabla («No se pudo actualizar el producto» o el que dé la
app). Sin permiso de cambio se ve «Sí»/«No» sin interruptor.
Implicados: SALE-F01

### INVENTORY-F04 Eliminar un producto
<!-- origen: fi:modules/inventory#command-inventory-products-delete old:inventory/workflow/catalogo.md#inventory-f04 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En **Productos**, pulsa «Eliminar» en la fila.
2. La ventana «Eliminar producto» dice «<nombre> (<SKU>) — se eliminará del catálogo (borrado
   lógico; sus movimientos de stock se conservan)».
3. Pulsa «Eliminar» (o «Cancelar»). La fila desaparece.
Entra: el producto elegido.
Sale: el producto queda eliminado e inactivo, fuera de todas las listas y del TPV. Su SKU y su
EAN-13 quedan libres para otro producto. Sus movimientos siguen en **Movimientos** con su nombre.
Inventario avisa de que el producto ya no está. No mira si tiene stock ni si está en una cuenta
abierta: Ventas rechaza al cobrar la línea de un producto que ya no está en el catálogo.
Si falla: «No se pudo eliminar el producto» (o el motivo) encima de la tabla.
Implicados: SALE-F01

### INVENTORY-F05 Revisar los productos que no se pueden vender por falta de IVA
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 qa:modules/inventory/create-product-with-vat old:inventory/workflow/catalogo.md#inventory-f05 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En el TPV, el aviso «N artículos no se pueden vender: les falta configurar el IVA.» trae
   «Revisar el catálogo» (solo para quien puede cambiar productos): abre **Productos** filtrado
   por «Sin configurar». También se llega filtrando Estado → «Sin configurar».
2. Cada fila lleva la marca «Sin configurar · Falta la categoría fiscal»: tocarla abre el
   formulario de edición.
3. Elige la «Categoría fiscal» y pulsa «Guardar cambios». El producto pasa a «Sí».
Entra: los productos cuya categoría fiscal ya no está en Impuestos. No se les inventa ninguna.
Sale: el producto con su categoría fiscal; Inventario avisa del cambio y el TPV deja de marcarlo
«Falta el IVA».
Si falla: los rechazos del formulario (INVENTORY-F02).
Implicados: SALE-F01, TAX-F01

### INVENTORY-F06 Crear y editar una categoría
<!-- origen: fi:modules/inventory#command-inventory-categories-create-update fi:modules/inventory#query-inventory-categories-list old:inventory/workflow/catalogo.md#inventory-f06 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Categorías
Pasos:
1. En **Categorías**, pulsa **+** (o toca una fila para editarla: «Editando categoría —
   <nombre>»).
2. Escribe el Nombre. Si dejas vacío «Slug (opcional)», se rellena solo con el nombre en
   minúsculas y con guiones. Al editar, dejarlo vacío conserva el que tenía; por el asistente o la
   API, un slug vacío se rehace con el nombre (nunca queda una categoría sin slug). Elige, si
   quieres, «Tipo de IVA / Impuesto» («— (por defecto)» lo deja vacío).
3. Pulsa «Guardar» o «Guardar cambios». La categoría sale en la tabla con su número de productos.
Entra: las categorías fiscales y su tipo, de Impuestos.
Sale: la categoría guardada. Editarla desde la pantalla no toca lo que la pantalla no enseña: la
descripción, el icono, el color y el orden que se pusieron por el asistente o la API se conservan.
Ventas la lee para la tira de categorías del TPV, y Cocina para elegir qué envía a cada estación.
Una categoría no se desactiva: se crea, se edita o se elimina.
Si falla: «Guardar» está apagado sin Nombre. Un rechazo sale dentro del panel («No se pudo
guardar la categoría» o el motivo).
Implicados: KITCHEN-F04, SALE-F01, TAX-F01

### INVENTORY-F07 Eliminar una categoría
<!-- origen: fi:modules/inventory#command-inventory-categories-delete old:inventory/workflow/catalogo.md#inventory-f07 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Categorías
Pasos:
1. En **Categorías**, pulsa «Eliminar» en la fila.
2. La ventana «Eliminar categoría» dice «<nombre> — N producto(s) quedarán sin esta categoría (se
   desvinculan; los productos no se borran)». N cuenta los productos activos.
3. Pulsa «Eliminar y desvincular» (o «Cancelar»).
Entra: la categoría elegida.
Sale: la categoría queda eliminada y todos sus productos, activos o no, desvinculados en el mismo
paso; los productos siguen. El TPV deja de agruparlos bajo ella.
Si falla: «No se pudo eliminar la categoría» (o el motivo) encima de la tabla.
Implicados: KITCHEN-F04, SALE-F01

### INVENTORY-F08 Agrupar productos en categorías para el TPV
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 fi:modules/inventory#query-inventory-product_categories old:inventory/workflow/catalogo.md#inventory-f08 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. Crea antes la categoría (INVENTORY-F06).
2. En el formulario del producto (alta o edición), busca en «Categorías» y elige una o varias: cada
   una sale debajo del campo, con su botón para quitarla, y ya no se ofrece de nuevo. El campo solo
   sale si hay alguna categoría.
3. Guarda. En **Categorías**, la columna Productos sube; en el TPV, el artículo sale bajo esa
   categoría.
Entra: las categorías del negocio.
Sale: el enlace entre producto y categoría, guardado junto con el producto; Inventario avisa de
cada categoría añadida o quitada. Un producto puede estar en varias. Ventas filtra la rejilla del
TPV con estos enlaces (solo de productos activos) y Cocina los usa para su reparto. El TPV ordena
productos y categorías por nombre.
Si falla: los rechazos del formulario; si algo falla no se guarda ni el producto ni sus
categorías. Un producto sin categoría se vende igual: sale en «Todos».
Implicados: KITCHEN-F04, SALE-F01

### INVENTORY-F09 Importar productos desde un CSV
<!-- origen: qa:modules/inventory/create-product-with-vat fi:modules/inventory#command-inventory-_insert_product-_receive_line-_restock_on_void fi:modules/inventory#command-inventory-products-bulk_create-handler-wasm-bulk_create old:inventory/workflow/importar-y-exportar.md#inventory-f09 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Importar productos
Pasos:
1. En **Productos**, pulsa el botón de importar CSV de la tabla y elige el fichero (con cabecera en
   la primera línea; separado por comas o por punto y coma, como lo guarda Excel en español). No se
   crea nada todavía.
2. En «Revisa la importación», cada columna trae su campo adivinado por la cabecera, en español o
   inglés y con o sin tildes («Nombre», «Código», «Precio», «IVA»…). Cámbialo o pon «No importar».
   Se pueden importar Nombre, SKU, Precio, Coste, Stock, Umbral, EAN-13, Descripción, Unidad y
   Categoría fiscal; Nombre y SKU son obligatorias.
3. Mira las «Primeras {n} filas de {total}» y el ensayo de todo el fichero: «{ready} fila(s) listas
   · {failed} con problemas», con la línea y el motivo de las diez primeras.
4. Pulsa «Importar {n} producto(s)» (o «Cancelar», que no deja rastro).
5. Si algún texto fiscal no se reconoce, o hay filas sin columna fiscal («Filas sin categoría
   fiscal»), sale «Categorías fiscales del CSV». Para cada uno: «Elegir» una categoría, «Crear» una
   (Clave y Nombre) u «Omitir». Pulsa «Confirmar e importar». Lo que se elige para un texto se guarda
   en Impuestos y la próxima importación ya lo reconoce; lo de «Filas sin categoría fiscal» no se
   guarda y se pregunta cada vez.
6. Mientras crea, encima de la tabla se lee «Importando {done}/{total}…» con «Parar».
7. Al acabar, «Resultado de la importación»: «Filas», «Creadas», «Omitidas (ya existían)»,
   «Fallidas», una línea por fallo y «Copiar informe».
Entra: el fichero; las categorías fiscales, sus nombres (también los traducidos) y los textos
aprendidos, de Impuestos; las unidades.
Sale: un producto activo y «Físico» por fila lista, que sigue el control de stock del negocio y no
lleva categorías de TPV; Inventario avisa de cada producto nuevo. El stock que trae cada fila queda
en **Movimientos** como «Inicial». En Impuestos, los textos aprendidos y las categorías creadas
desde la ventana fiscal. Una fila con un SKU que ya tiene un producto vivo se cuenta como omitida y
ese producto no se toca, digan lo que digan sus otras celdas (así el propio export se vuelve a importar
sin fallos, también con un stock negativo); un SKU de un producto eliminado crea uno nuevo.
Si falla: motivos de fila: «Faltan nombre o SKU», «Precio no numérico» (también para el coste),
«Precio o coste demasiado alto», «SKU duplicado en el fichero», «Cantidad no numérica», «Cantidad
demasiado grande», «La cantidad no respeta el incremento permitido para esta unidad», «Unidad de
medida no reconocida», «Un texto es más largo de lo que admite su columna», «Ese EAN-13 ya lo tiene
otro producto del catálogo» y «Falta la categoría fiscal» o «Categoría fiscal no reconocida». Si Impuestos no puede guardar un texto aprendido o una categoría
creada, se dice en el informe y sus filas quedan como fallidas con ese motivo. «Cancelar» en la
ventana fiscal no importa nada. «Parar» deja lo ya creado y el informe dice «La importación se
paró a medias. Lo que ya se había creado está contado abajo; el resto del fichero se quedó como
estaba.».
Implicados: TAX-F02, TAX-F14, TAX-F15

### INVENTORY-F10 Importar categorías desde un CSV
<!-- origen: old:inventory/workflow/importar-y-exportar.md#inventory-f10 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Categorías
Pasos:
1. En **Categorías**, pulsa el botón de importar CSV de la tabla y elige el fichero (separado por
   comas o por punto y coma).
2. Se reconocen las columnas Nombre (obligatoria), Slug y Categoría fiscal por su cabecera, en
   español o inglés («Nombre»/«name», «IVA»/«tax»…).
3. Se crea una categoría por fila con nombre; el slug, si no viene, se saca del nombre.
4. Al acabar, «Resultado de la importación»: «Filas», «Creadas», «Omitidas (ya existían)»,
   «Fallidas», una línea por fallo y «Copiar informe». La tabla se recarga.
Entra: el fichero; las categorías fiscales y los textos aprendidos, de Impuestos.
Sale: las categorías creadas. Una fila con el nombre de una categoría que ya existe se omite, así
que repetir el fichero no duplica nada.
Si falla: cada fila que no entra sale en el informe con su motivo: «Falta el nombre» o «Categoría
fiscal no reconocida: <texto>».
Implicados: TAX-F15

### INVENTORY-F11 Exportar el catálogo a CSV
<!-- origen: old:inventory/workflow/importar-y-exportar.md#inventory-f11 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En **Productos** (con la búsqueda y los filtros que quieras), pulsa el botón de exportar CSV de
   la tabla.
2. Se descarga `inventario-productos.csv` con **todos** los productos que cumplen la búsqueda y los
   filtros, no solo la página que se ve.
3. En **Categorías**, el mismo botón descarga `inventario-categorias.csv` (Nombre, Slug y número de
   productos).
Entra: los productos o las categorías que cumplen la búsqueda y los filtros.
Sale: el fichero, con las mismas cabeceras que reconoce la importación (Nombre, SKU, Precio, Coste,
Stock, Umbral, EAN-13, Descripción, Unidad, Categoría fiscal, Activo) y las cifras como se leen en
pantalla (2,20 €, 3 unidades), de modo que se puede volver a importar sin cambiar nada. No guarda
ni avisa nada.
Si falla: sin productos, el fichero lleva solo la cabecera. Sin permiso de exportar, el botón no
sale y la app no lo entrega por ninguna otra puerta. Un texto que una hoja de cálculo ejecutaría como
fórmula (empieza por =, +, -, @…) sale con un apóstrofo delante, que la importación quita.
Implicados: ninguno

### INVENTORY-F12 Cargar la carta de una plantilla del sector
<!-- origen: old-hub:HUB_SHELL-F26 old-hub:HUB-F235 old:inventory/workflow/importar-y-exportar.md#inventory-f12 wf:alta#rec_alta-f08 -->
Estado: parcial — la parte de Inventario está (el alta en lote con su stock y sus categorías, que salta los SKU que ya existen); falta cargar la plantilla del sector, que es del núcleo y el Hub todavía no tiene
Actor: administrador
Pantalla: Ajustes del negocio: plantillas
Pasos:
1. En los ajustes del negocio, el administrador elige la plantilla de su sector.
2. El negocio activa las apps que falten y aplica los datos de la plantilla; Inventario recibe sus
   productos, sus categorías y sus enlaces.
3. Comprueba en **Productos** que están y que ninguno sale «Sin configurar» (INVENTORY-F05).
Entra: la plantilla.
Sale: los productos, con su categoría fiscal, su stock (que queda en **Movimientos** como
«Inicial») y su umbral, y las categorías de la plantilla. Si se vuelve a aplicar sobre un catálogo
con los mismos SKU, esos productos se saltan: no cambian ni su precio ni su stock.
Si falla: cada app aplica su parte por separado; si la de Inventario falla, sale en el informe de
la plantilla y el resto se aplica.
Implicados: ninguno

### INVENTORY-F13 Recibir mercancía
<!-- origen: fi:modules/inventory#command-inventory-_insert_product-_receive_line-_restock_on_void fi:modules/inventory#command-inventory-stock-receive-handler-wasm-receive_stock old:inventory/workflow/stock.md#inventory-f13 qa:modules/inventory/waste-and-adjustment -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Recepción
Pasos:
1. En **Productos**, pulsa «Recibir stock» en la fila o en la ficha del producto.
2. En «Recepción — <producto>» se ve el «Stock actual». Escribe la «Cantidad recibida» y, si
   quieres, el «Coste unitario (<moneda>)».
3. Pulsa «Registrar recepción». La ventana se cierra y la fila enseña el stock nuevo.
4. En **Movimientos** sale una línea «Recepción» con la cantidad en positivo y el saldo.
Entra: el producto y el escalón de su unidad. Por el asistente o la API, una recepción puede llevar
varios productos y el número del albarán.
Sale: el stock sube y queda el movimiento «Recepción» con cantidad, saldo, coste y, si lo hay, el
albarán. Si se escribió coste, pasa a ser el coste del producto. Se aplica aunque el artículo no
lleve control de stock. Si un artículo con control sube por encima de su umbral, avisa del cruce
(INVENTORY-F18). Inventario avisa de que el stock cambió.
Si falla: «Registrar recepción» está apagado sin cantidad. «La cantidad no respeta el incremento
permitido para esta unidad», un coste ilegible («Esto no es un importe…») o «No se pudo registrar
la recepción» salen dentro de la ventana. Un servicio no se recibe: no tiene el botón, y por el
asistente o la API se rechaza con «Un servicio no lleva stock.». Una recepción con una línea sin
producto, con un producto que no existe o con cantidad cero se rechaza entera, diciendo qué línea
falla: no entra ninguna.
Implicados: ninguno

### INVENTORY-F14 Contar el stock de un producto
<!-- origen: qa:modules/inventory/waste-and-adjustment fi:modules/inventory#command-inventory-stock-adjust old:inventory/workflow/stock.md#inventory-f14 qa:verticals/restaurant/08-incidents-voids-and-refunds -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Recuento
Pasos:
1. En **Productos**, pulsa «Contar stock» en la fila o en la ficha.
2. En «Recuento — <producto>», escribe en «Stock contado» lo que hay de verdad (el total, no la
   diferencia): si el sistema dice 5 y cuentas 7, escribe 7. Aparece «Diferencia» (+2).
3. Escribe el «Motivo (obligatorio)».
4. Pulsa «Aplicar recuento». La fila enseña el saldo contado; en **Movimientos** sale «Recuento» con
   la diferencia y el motivo.
Entra: el producto y su saldo.
Sale: el saldo pasa a ser lo contado y queda el movimiento «Recuento» con la diferencia (si no hay
diferencia, no se apunta nada). Inventario avisa de que el stock cambió. Se aplica aunque el
artículo no lleve control de stock. Si cruza el umbral de un artículo con control, en cualquier
sentido, avisa del cruce (INVENTORY-F18).
Si falla: «Aplicar recuento» está apagado y dice qué falta: «Escribe el stock contado para
continuar.» o «Hace falta un motivo para aplicar el recuento.». Una cantidad negativa o que no
encaja en la unidad: «La cantidad no respeta el incremento permitido para esta unidad». Un motivo de
menos de 3 letras: «El motivo necesita al menos 3 letras.». Un servicio no se cuenta: no tiene el
botón, y por el asistente o la API se rechaza con «Un servicio no lleva stock.». Todo sale dentro
de la ventana; si no, «No se pudo aplicar el recuento».
Implicados: ninguno

### INVENTORY-F15 Dar de baja stock sin venta (merma, rotura, consumo propio)
<!-- origen: qa:modules/inventory/waste-and-adjustment qa:verticals/restaurant/08-incidents-voids-and-refunds fi:modules/inventory#command-inventory-stock-decrease old:inventory/workflow/stock.md#inventory-f15 -->
Estado: hecho
Actor: administrador, responsable (pantalla); asistente
Pantalla: ficha y tabla de Productos (ventana «Baja»); asistente
Pasos:
1. En **Productos**, pulsa «Dar de baja stock» en la fila (menú ⋮) o en la ficha del producto: solo
   sale en productos físicos con control de stock y con permiso de mover stock.
2. En «Baja — <producto>» escribe la cantidad y el motivo (merma, rotura, consumo propio…) y pulsa
   «Dar de baja». Por el asistente: «da de baja 2 botellas de vino tinto por rotura»; enseña la
   tarjeta de confirmación con el producto, la cantidad y el motivo.
3. En **Movimientos** sale «Descuento» con la cantidad en negativo y el motivo.
Entra: el producto, la cantidad (en el escalón de su unidad) y el motivo. También se puede pedir
por la API.
Sale: el stock baja y queda el movimiento «Descuento»; Inventario avisa de que el stock cambió y,
si cruza el umbral, del cruce (INVENTORY-F18). Lo pueden pedir el responsable y el administrador.
Si falla: si no hay bastante y «Permitir vender sin stock» está apagado, «No hay stock suficiente
para completar la operación.». Un producto que no existe: «Este producto no existe en este hub.».
Una cantidad fuera del escalón: «Esa cantidad no encaja en la unidad del producto…» (no se
redondea). Un servicio se rechaza con «Un servicio no lleva stock.», y un artículo sin control de
stock con «Este artículo no controla su stock: no hay nada que dar de baja.» (409
`inventory.stock_not_tracked`): ni éxito en silencio ni movimiento. Todo sale dentro de la ventana.
Implicados: ninguno

### INVENTORY-F16 Consultar el historial de movimientos
<!-- origen: old:inventory/workflow/stock.md#inventory-f16 -->
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Movimientos
Pasos:
1. Abre **Inventario → Movimientos**: los más recientes primero.
2. Busca por producto, SKU o referencia, o escribe el número de un tique, una factura o una venta:
   salen esa venta y, si se anuló, su anulación.
3. Filtra por Tipo o por Referencia; ordena por Fecha, Cantidad o Saldo.
4. En una venta, la Referencia es el número de su tique o factura (o, sin Facturación, el número de
   la venta). En tableta, tocar una referencia cortada la despliega.
Entra: el libro de movimientos; el número de cada venta y el de su tique o factura, que Inventario
apunta de Ventas cuando la venta baja el stock, solo para pintarlos y buscarlos.
Sale: nada: es solo lectura y ningún movimiento se edita ni se borra. Cada movimiento guarda
también quién lo hizo, aunque esta pantalla no lo enseña.
Si falla: una venta cuyo número Inventario no llegó a apuntar deja vacía la celda Referencia. Un tique
que Facturación numera más tarde (por ejemplo, sin los datos del negocio al cobrar) se lee y se busca
por el número de la venta. Error de carga: el aviso de la tabla con «Reintentar».
Implicados: INVOICE-F20, SALE-F28

### INVENTORY-F17 Ver el panel y los productos con stock bajo
<!-- origen: fi:modules/inventory#query-inventory-products-low_stock fi:modules/inventory#query-inventory-products-stats fi:modules/inventory#widget-inventory-low_stock_count-kpi-inventory-value-kpi-inventory-in_stock-stat-inventory-low_stock_products-bar-list old:inventory/workflow/stock.md#inventory-f17 -->
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Panel
Pasos:
1. Abre **Inventario → Panel**: «Productos seguidos», «En stock», «Agotados» (saldo 0 o menos),
   «Stock bajo» (saldo igual o menor que su umbral) y «Valor de existencias» a coste. Tocar una de
   las cuatro primeras lleva a **Productos**.
2. Debajo, «Productos con stock bajo», del que menos tiene al que más, con su umbral.
3. En el **Inicio**, los paneles de Inventario: «Productos con stock bajo» (la cifra de «Stock
   bajo»), «Valor de existencias (a coste)» y «Productos con menos stock» (los cinco que menos
   tienen, el primero el que menos) salen de serie; «Productos en stock» se añade con ⋮
   («Personalizar panel»), donde van agrupados bajo «Inventario». El valor sale en la moneda del
   negocio.
Entra: los productos activos, físicos y con control de stock. El valor es la suma de coste por
saldo de los que tienen saldo positivo; un saldo negativo no resta.
Sale: nada.
Si falla: «No se pudieron cargar las métricas del inventario.» y el aviso de la tabla con
«Reintentar»; en el Inicio, un panel que no se puede leer dice «No disponible». El panel y los
paneles del Inicio se refrescan solos con cualquier movimiento de stock (venta, anulación,
recepción, recuento, baja), con cualquier alta, cambio o eliminación de un producto y al guardar los
ajustes. Los paneles del Inicio los ve quien puede ver los productos.
Implicados: ninguno

### INVENTORY-F18 Avisar cuando un artículo cruza su mínimo
<!-- origen: old:inventory/workflow/stock.md#inventory-f18 qa:modules/inventory/stock-deduction-on-sale -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una venta, una baja o un recuento lleva un artículo con control de stock de estar por encima de
   su umbral a estar en él o por debajo: Inventario avisa del cruce «por debajo».
2. Mientras siga por debajo, no se repite. Cuando una recepción, un recuento o una anulación lo sube
   otra vez por encima, avisa de «recuperado», y eso rearma el siguiente.
3. Si el mismo artículo va en varias líneas de una venta (suelto y dentro de un menú), se decide
   una vez sobre el total.
4. Para que alguien se entere, el responsable monta en **Flujos** una automatización que arranque
   con este aviso (por ejemplo, avisar para reponer), como con cualquier otro aviso del negocio
   (FLOW-F21).
Entra: el saldo de antes y el de después del movimiento, y el umbral del producto.
Sale: el aviso con el producto (SKU y nombre), la cantidad de antes y la de después, el umbral, el
tipo de movimiento y la venta o el albarán.
Si falla: solo se avisa de lo que de verdad se movió: una venta que no bajó el stock (INVENTORY-F21)
no avisa. Dos movimientos a la vez sobre el mismo producto se aplican uno detrás de otro, así que el
aviso ni se pierde ni sale dos veces. Si el movimiento no llega a guardarse, tampoco sale el aviso.
Implicados: FLOW-F21

### INVENTORY-F19 Ajustar el inventario
<!-- origen: fi:modules/inventory#command-inventory-settings-update fi:modules/inventory#query-inventory-settings-get old:inventory/workflow/stock.md#inventory-f19 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Ajustes
Pasos:
1. Abre **Inventario → Ajustes**. La ven y la guardan el administrador y el responsable, igual
   desde la pestaña que por el asistente.
2. «Controlar stock» (de fábrica, encendido): es lo que hacen los artículos que no han decidido por
   sí mismos (INVENTORY-F20).
3. «Permitir vender sin stock» (de fábrica, apagado): encendido, una venta baja el stock aunque
   quede en negativo; apagado, si una venta pide más de lo que queda, ese artículo no baja nada (la
   venta se cobra igual) y una baja sin venta se rechaza.
4. «Umbral de stock bajo» (de fábrica, 10, en unidades enteras): el umbral con el que nace un
   producto creado sin el suyo (solo pasa por el asistente o la API: el formulario y el CSV siempre
   mandan uno). Cambiarlo no toca los productos que ya existen.
5. Pulsa «Guardar»: «Ajustes guardados.».
Entra: los ajustes guardados del negocio (uno por negocio); si nunca se guardaron, valen los de
fábrica.
Sale: los ajustes, que se aplican desde el siguiente movimiento. Solo avisan a las pantallas abiertas
(el Panel y las listas se refrescan); ninguna otra app reacciona.
Si falla: «No se pudieron guardar los ajustes.». Si con la pestaña abierta entra otra persona sin
el permiso (relevo de turno), los campos se bloquean, desaparece «Guardar» y sale «No tienes
permiso para cambiar estos ajustes. Pídeselo a un administrador si lo necesitas.».
Implicados: SALE-F01

### INVENTORY-F20 Decidir qué artículos llevan control de stock
<!-- origen: old:inventory/workflow/stock.md#inventory-f20 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En el formulario de un producto físico, mira «Controlar stock de este artículo»: marcada o no
   según lo que vale hoy para él; debajo, «Sigue el ajuste del hub» mientras no se toque.
2. Desmárcala para que sea solo de catálogo («Solo catálogo: las ventas no mueven su stock») o
   márcala para que lleve stock aunque el negocio no lo haga.
3. Guarda. En **Productos**, la columna Stock de un artículo sin control enseña «—».
Entra: el ajuste «Controlar stock» del negocio, para enseñar lo que vale antes de decidir.
Sale: la decisión del artículo; Inventario avisa del cambio. Vale la del artículo; si no tiene, la
del negocio; si el negocio nunca guardó ajustes, sí. Un servicio nunca lleva control. Sin control,
la venta no lo mueve, no sale en stock bajo ni en las cifras del Panel y no cruza su mínimo; recibir
y contar sí lo mueven.
Si falla: los rechazos del formulario (INVENTORY-F01). Una vez decidido, el artículo no vuelve a
«Sigue el ajuste del hub».
Implicados: SALE-F01

### INVENTORY-F21 Bajar el stock al cobrarse una venta
<!-- origen: qa:verticals/beauty/05-sale-upsell-and-payment wf:peluqueria-dia#rec_peluqueria-f09 qa:verticals/restaurant/03-menu-and-prices wf:restaurante-dia#rec_restaurante-f11 qa:verticals/restaurant/08-incidents-voids-and-refunds fi:modules/inventory#command-inventory-stock-decrease qa:modules/inventory/stock-deduction-on-sale fi:modules/inventory#command-inventory-stock-decrease_on_sale-handler-wasm-decrease_on_sale fi:modules/inventory#event-listen-sale-completed-inventory-stock-decrease_on_sale old-hub:HUB-F51 old:inventory/workflow/con-otros-modulos.md#inventory-f21 wf:restaurante-dia#rec_restaurante-f17 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Ventas cobra un tique y avisa de la venta cobrada (SALE-F01). En Inventario no se hace nada a
   mano.
2. Por cada línea con un artículo del catálogo, Inventario baja la cantidad vendida, también si la
   línea va invitada. No mueven nada una línea de servicio, una de precio libre, un suplemento ni un
   artículo sin control de stock.
3. Si el mismo artículo va en varias líneas, cada una deja su movimiento.
4. Se comprueba en **Movimientos**: una línea «Venta» por línea del tique, con su número como
   referencia, y el saldo que quedó.
Entra: la venta cobrada, de Ventas: cada línea con su artículo, su cantidad (exacta, ya comprobada
contra el escalón al cobrar), si es servicio y, si es un menú, sus componentes (INVENTORY-F22).
Sale: el stock baja y queda el movimiento «Venta» con la venta como referencia, en el mismo paso.
Con «Permitir vender sin stock» encendido, el saldo puede quedar en negativo; apagado, un artículo
que no alcanza no baja nada. Inventario avisa de que el stock cambió y, si cruza el mínimo, del
cruce (INVENTORY-F18). Si ninguna línea mueve stock, deja anotado que esa venta no movió nada, para
que su anulación no reponga nada.
Si falla: la venta ya está cobrada. Si Inventario no puede aplicarla en ese momento, se reintenta
sola y, si sigue fallando, queda en la lista de avisos fallidos del negocio para reintentarla a
mano. Dos ventas a la vez sobre la última unidad: con el ajuste apagado, la segunda no baja nada;
encendido, queda en negativo.
Implicados: SALE-F01, SALE-F11, SALE-F15

### INVENTORY-F22 Bajar el stock de los componentes de un menú o un pack
<!-- origen: wf:restaurante-dia#rec_restaurante-f11 old:inventory/workflow/con-otros-modulos.md#inventory-f22 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Ventas cobra un menú (o un pack) con las elecciones del cliente (SALE-F12).
2. Inventario baja cada componente elegido con la cantidad de la línea: tres menús, tres raciones de
   cada plato. El menú no tiene stock y nunca sale en **Movimientos**.
3. Un componente que es un servicio (lo normal en un pack de peluquería) o que no lleva control de
   stock no mueve nada, y no es un error.
4. Si un artículo va suelto y dentro de un menú en el mismo tique, el cruce de mínimo se decide una
   vez sobre el total.
Entra: los componentes de la línea, que Ventas fija del menú de Menús al cobrar.
Sale: un movimiento «Venta» por componente; la anulación los repone igual (INVENTORY-F23).
Si falla: como INVENTORY-F21.
Implicados: COMBO-F10, SALE-F12

### INVENTORY-F23 Reponer el stock al anularse una venta
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:restaurante-dia#rec_restaurante-f15 fi:modules/inventory#command-inventory-_insert_product-_receive_line-_restock_on_void qa:verticals/restaurant/08-incidents-voids-and-refunds qa:modules/inventory/stock-deduction-on-sale fi:modules/inventory#event-listen-sale-voided-inventory-_restock_on_void old:inventory/workflow/con-otros-modulos.md#inventory-f23 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El responsable anula una venta en Ventas (SALE-F30).
2. Inventario devuelve a cada artículo exactamente lo que esa venta le quitó, según su propio libro
   de movimientos: los menús, por sus componentes, y nada de lo que no llegó a bajar (sin control de
   stock, sin saldo, servicios).
3. En **Movimientos** sale una línea «Anulación» por artículo, con la misma referencia que la venta.
Entra: la venta anulada, de Ventas (solo cuál es).
Sale: el stock sube y queda el movimiento «Anulación». Devuelve lo que salió aunque el artículo haya
dejado de controlar stock entre medias. Inventario avisa de que el stock cambió y, si un artículo
vuelve por encima de su umbral, de «recuperado» (INVENTORY-F18).
Si falla: la anulación repone una sola vez, aunque el aviso llegue dos veces. El resultado es el
mismo llegue antes la venta o la anulación: si la anulación llega primero, la venta que llegue
después ya no baja nada. Un artículo eliminado después de la venta no recupera nada.
Implicados: SALE-F30

### INVENTORY-F24 Reponer el stock de una devolución
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:restaurante-dia#rec_restaurante-f15 qa:verticals/restaurant/08-incidents-voids-and-refunds qa:modules/inventory/stock-deduction-on-sale old:inventory/workflow/con-otros-modulos.md#inventory-f24 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El responsable devuelve una venta en Ventas (SALE-F31) y marca qué líneas y cuántas unidades
   vuelven (como el «devolver al stock» de Square y Toast).
2. Inventario repone esas unidades a cada artículo, una sola vez por devolución.
3. En **Movimientos** sale una línea «Devolución» por artículo, con la venta como referencia y el
   motivo de la devolución.
Entra: la devolución, de Ventas: su venta, su identificador, su motivo y las líneas que vuelven
(producto y cantidad). Una devolución solo de dinero no trae líneas.
Sale: el stock sube y queda el movimiento «Devolución»; Inventario avisa de que el stock cambió y, si
un artículo vuelve por encima de su umbral, de «recuperado» (INVENTORY-F18). Nunca repone más de lo
que la venta bajó y las devoluciones anteriores no repusieron (lo dice el libro), así que no vuelve
nada que la venta no bajó: un servicio, una línea de precio libre, un artículo que no alcanzaba o
sin control de stock. Un artículo que dejó de controlar su stock se deja como está. Una anulación
posterior repone solo lo que aún falta.
Si falla: la misma devolución entregada dos veces repone una vez. La devolución de una venta anulada
(o que Inventario no llegó a ver) no repone nada. Una línea de menú no repone sus componentes: el
aviso de la devolución no los trae; si vuelven a la estantería, se cuentan (INVENTORY-F14).
Implicados: SALE-F31

### INVENTORY-F25 Imprimir la etiqueta del código de barras
<!-- origen: old-hub:HUB_PERIPHERALS-F12 old:inventory/workflow/con-otros-modulos.md#inventory-f25 -->
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Ficha del producto
Pasos:
1. Abre la ficha del producto (toca la fila o «Detalles»): se ve el código de barras de su SKU en una
   placa blanca, con el SKU debajo, que se lee también con el tema oscuro.
2. Pulsa «Imprimir código de barras».
3. La etiqueta (nombre, código de barras y precio) va a la cola de Impresión, a la impresora con la
   función «Etiqueta», y la ficha dice «La etiqueta ha ido a la impresora «<nombre>».». La saca el
   equipo que recoge los trabajos de esa impresora (PRINTING-F12). Cada pulsación saca una etiqueta.
4. Si ninguna impresora tiene la función «Etiqueta», la etiqueta espera en la cola y la ficha lo
   dice: «La etiqueta espera en la cola de impresión: ninguna impresora tiene la función «Etiqueta».
   Asígnasela a una en Impresión.».
Entra: el SKU, el nombre y el precio del producto; la impresora con la función «Etiqueta», de
Impresión. También se pide por el asistente («imprime la etiqueta del champú») o por la API.
Sale: un trabajo de etiqueta en la cola de Impresión, con el precio en la moneda del negocio.
Si falla: quien no llega a la cola de impresión (Impresión no está activa, o no puede imprimir) ve el
diálogo de imprimir del navegador con el código, el SKU y el nombre, sin precio. Un SKU con letras que
un código de barras no lleva (tildes, eñes) no se dibuja ni se imprime: «Este SKU no se puede pasar a
código de barras: usa letras sin tilde, números y signos.». Cualquier otro rechazo sale dentro de la
ficha: «No se pudo imprimir la etiqueta del código de barras: <motivo>».
Implicados: PRINTING-F04, PRINTING-F12

### INVENTORY-F26 Vender al peso o por medida: unidades y escalón
<!-- origen: qa:verticals/restaurant/03-menu-and-prices old:inventory/workflow/con-otros-modulos.md#inventory-f26 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos
Pasos:
1. En el formulario del producto, elige la «Unidad de medida»: «Unidad (ud)», «Kilogramo (kg)»,
   «Gramo (g)», «Tonelada (t)», «Litro (l)», «Mililitro (ml)», «Minuto (min)» u «Hora (h)».
2. Cada una tiene su escalón: el gramo dentro del kilo, el mililitro dentro del litro, el kilo
   dentro de la tonelada, el cuarto de hora en la hora y la unidad entera en las demás.
3. El stock inicial, el umbral, la recepción, el recuento y la baja solo admiten cantidades de ese
   escalón.
4. En el TPV el artículo se vende tecleando la cantidad (0,532 kg) y la venta baja esa cantidad
   exacta, sin redondear (SALE-F10).
Entra: las unidades del negocio, que llegan al activar Inventario.
Sale: el producto con su unidad. Ventas la lee para la línea; el precio es por 1 de la unidad.
Por el asistente o la API, el precio se puede referir a otra cantidad (por 100 g, o por kilo con
el stock en gramos).
Si falla: «La cantidad no respeta el incremento permitido para esta unidad» en pantalla; «Esa
cantidad no encaja en la unidad del producto…» por el asistente o la API. La unidad de un producto
con stock no se cambia (INVENTORY-F02).
Implicados: SALE-F10

### INVENTORY-F27 Entregar el catálogo al TPV, a Cocina y a Menús
<!-- origen: qa:verticals/restaurant/03-menu-and-prices wf:restaurante-dia#rec_restaurante-f06 fi:modules/inventory#query-inventory-products-list old:inventory/workflow/con-otros-modulos.md#inventory-f27 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al abrir el TPV, Ventas pide a Inventario los productos activos (los agotados, para enseñarlos en
   gris), las categorías, qué categorías tiene cada producto y las unidades. Al cobrar, pide el
   catálogo de venta entero: precio, coste, categoría fiscal, unidad y si cada artículo lleva control
   de stock.
2. Cocina pide los productos y las categorías para elegir qué envía a cada estación.
3. Menús pide los productos que se pueden poner como componente: los activos, también los agotados
   hoy (un menú se monta con ellos); al vender, no ofrece una elección cuyo producto está agotado.
4. Sin Inventario activo, el TPV lo dice en la rejilla («… no está instalada, así que no hay rejilla
   de productos. Puedes cobrar servicios y ventas a precio libre; …») y vende servicios y precio
   libre.
Entra: nada: lo piden las demás apps (ver [Servicios](#servicios-lo-que-entra-y-lo-que-sale)).
Sale: las lecturas. En el catálogo de venta solo salen los productos a la venta: activos, no agotados
(INVENTORY-F29) y no eliminados; el mapa de categorías lleva los activos. La rejilla y el buscador del
TPV enseñan también lo agotado, en gris con «Agotado», y las cifras de su tira («Todos» y cada
categoría) cuentan lo que enseña la rejilla: los activos, agotados incluidos. No lo dejan pedir: tocarlo no añade nada y dice «… está agotado.», y una línea nueva de un agotado que llega
por el asistente o la API se rechaza sin escribir nada (SALE-F07). Un artículo que se marca agotado
con el TPV abierto pasa a gris al momento, sin recargar, y vuelve igual; el menú que no se puede
completar sin ese artículo sale del TPV (COMBO-F12). El catálogo de venta no lleva stock: el TPV no
enseña ni comprueba cuántas unidades quedan.
Si falla: lo decide quien pide. Ventas rechaza una línea de catálogo si no puede leer el catálogo de
venta y avisa en el TPV si Inventario está activo y no contesta; Cocina se queda sin opciones de
reparto.
Implicados: COMBO-F06, KITCHEN-F04, SALE-F01, INVENTORY-F29

### INVENTORY-F28 Completar el primer paso «Tu catálogo»
<!-- origen: old-hub:HUB_SHELL-F27 old-hub:HUB_SHELL-F31 old:inventory/workflow/con-otros-modulos.md#inventory-f28 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Inicio: Termina de configurar tu negocio
Pasos:
1. En la lista «Termina de configurar tu negocio» sale el paso obligatorio «Tu catálogo» («Añade al
   menos un producto para que haya algo que vender.»), marcado «Importante».
2. «Configurar» lleva a **Inventario → Productos**.
3. En cuanto hay un producto activo (físico o de tipo servicio), el paso sale hecho, sin recargar.
Entra: el número de productos activos.
Sale: el paso hecho o pendiente. Lo ve quien puede dar de alta productos.
Si falla: si se desactivan o eliminan todos los productos, el paso vuelve a pendiente, también sin
recargar.
Implicados: ninguno

### INVENTORY-F29 Marcar un artículo como agotado
<!-- origen: qa:modules/sales/sold-out-item-86 -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Productos; Ficha del producto
Pasos:
1. Se acaba un plato o un artículo a media jornada: en **Inventario → Productos**, búscalo y, en el
   menú «⋮» de su fila, toca «Marcar agotado». También desde su ficha, con «Marcar agotado», o
   diciéndoselo al asistente («las croquetas se han acabado»).
2. La fila enseña la insignia «Agotado» junto a su interruptor, que sigue encendido: el artículo no
   se desactiva ni pierde nada. El TPV deja de venderlo al momento: en la rejilla y en el buscador sale
   en gris con «Agotado» y no se puede pedir, también en los TPV que ya estaban abiertos, y en los
   menús sale «Agotado en Inventario»: el menú que solo se completaba con él deja de ofrecerse.
3. Para ver todo lo agotado, filtra Estado por «Agotado».
4. Cuando vuelve a haber, toca «Volver a poner a la venta» en el menú «⋮» o en la ficha: la insignia
   desaparece y el TPV lo vuelve a vender.
Entra: el artículo (por la pantalla, o por su SKU o su nombre desde el asistente o la API) y si está
agotado o vuelve a la venta.
Sale: el artículo marcado o desmarcado; Inventario avisa del cambio (`inventory.product.updated`).
Marcarlo dos veces no cambia nada. Desactivarlo, activarlo o editarlo no le quita la marca. Un
artículo agotado sigue contando en su categoría, porque el TPV lo sigue enseñando en gris
(INVENTORY-F27), y no sale en el catálogo de venta.
Si falla: el motivo sale encima de la tabla o dentro de la ficha («No se pudo cambiar si el producto
está agotado» o el que dé la app). Quien no puede cambiar productos ve la insignia, pero no las
acciones. Un artículo que ya no existe da «Este producto no existe en este hub».
Implicados: SALE-F01, INVENTORY-F27, COMBO-F12

## Qué comparten los verticales

El restaurante usa Inventario para la carta y la peluquería para los productos de venta, con las
mismas pantallas, los mismos ajustes y la misma reacción a la venta. No hay ningún ajuste por
vertical: tocar una pieza de esta tabla afecta a los dos negocios.

| Pieza compartida | Flujos que la usan |
|---|---|
| El formulario del producto (mismo panel para alta y edición; categoría fiscal obligatoria, sin opción por defecto) | F01, F02, F05, F08, F20, F26 |
| El selector de categoría fiscal con nombre y tipo («· 21 %», «exento»), leído de Impuestos | F01, F02, F06, F09 |
| El control de stock que vale para un artículo: el suyo, o el del negocio si no lo fijó; un servicio nunca | F17, F18, F19, F20, F21, F22 |
| La regla de bajar stock: saldo y movimiento en el mismo paso; con «Permitir vender sin stock» apagado, no baja si no alcanza | F15, F21, F22 |
| El libro de movimientos (no se edita; el saldo se explica por él; la anulación devuelve lo que él dice) | F01, F09, F12, F13, F14, F15, F16, F21, F22, F23 |
| El umbral de stock bajo de cada producto y el aviso de cruce | F13, F14, F15, F17, F18, F21, F23 |
| La unidad de medida y su escalón | F01, F02, F09, F13, F14, F15, F26 |
| El catálogo de venta que leen Ventas, Cocina y Menús (solo productos activos y no eliminados) | F03, F04, F08, F27 |
| Los textos fiscales aprendidos en Impuestos al importar | F09, F10 |

## Servicios: lo que entra y lo que sale

Todo lo que Inventario hace se puede pedir por tres puertas, siempre con las mismas reglas y los
mismos permisos: sus **pantallas**, el **asistente** y la **API**. Esta sección es la lista
completa. Las consultas se ejecutan sin preguntar; las acciones, desde el asistente, piden antes la
tarjeta de confirmación («un clic» o «escribe para confirmar», según el riesgo).

Por el asistente (también por voz) y por la API, un producto se nombra por su SKU o por su nombre, y una
categoría por su nombre, además de por su identificador: «da de baja 2 botellas de vino tinto» basta. Si
el nombre casa con varios, Inventario no elige: dice cuáles son y pregunta cuál. Toda lista se puede
buscar y va por páginas de hasta 100.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los productos con su stock y si están agotados, con búsqueda, filtros (nombre, SKU, precio, stock, estado, agotado) y páginas; «a la venta» da lo que ofrece el TPV | ver productos | F03, F05, F27, F29 | `inventory.product.list` |
| La ficha completa de un producto (por su id, su SKU o su nombre) | ver productos | F02, F25 | `inventory.product.get` |
| El catálogo de venta entero: productos a la venta (activos y no agotados) con precio, coste, categoría fiscal, unidad y si llevan control de stock | ver productos | F27 | `inventory.product.list_for_sale` |
| Los productos en su umbral o por debajo, del que menos tiene al que más | ver productos | F17 | `inventory.product.list_low_stock` |
| Qué categorías tiene cada producto activo | ver productos | F08, F27 | `inventory.product_category.list` |
| Las categorías, con cuántos productos activos tiene cada una (agotados incluidos, lo que enseña el TPV) | ver categorías | F06, F27 | `inventory.category.list` |
| El libro de movimientos: fecha, producto, tipo, cantidad, saldo, motivo, referencia y quién lo hizo | ver stock | F16 | `inventory.movement.list` |
| Las cifras del panel: productos seguidos, en stock, agotados, en stock bajo, valor a coste y número de productos activos | ver productos | F17, F28 | `inventory.stock.get_summary` |
| Las unidades de medida con su escalón | ver productos | F26 | `inventory.unit.list` |
| Los ajustes del inventario | gestionar ajustes | F19 | `inventory.config.get` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Confirmación en el asistente | Flujos | Servicio |
|---|---|---|---|---|
| Da de alta un producto, con sus categorías y su stock inicial | dar de alta productos | un clic | F01, F20, F26 | `inventory.product.create` |
| Da de alta muchos productos de una vez y dice qué fila entró, cuál se omitió y cuál falló | importar productos | un clic | F09 | `inventory.product.bulk_create` |
| Cambia un producto: datos, activo o inactivo, control de stock y categorías | cambiar productos | un clic | F02, F03, F05, F08, F20 | `inventory.product.update` |
| Elimina un producto | eliminar productos | escribir para confirmar | F04 | `inventory.product.delete` |
| Marca un producto como agotado o lo vuelve a poner a la venta | cambiar productos | un clic | F29 | `inventory.product.set_sold_out` |
| Añade un producto a una categoría | cambiar productos | un clic | F08 | `inventory.product_category.add` |
| Quita un producto de una categoría | cambiar productos | un clic | F08 | `inventory.product_category.remove` |
| Crea una categoría | crear categorías | un clic | F06 | `inventory.category.create` |
| Crea muchas categorías de una vez, con informe por fila | crear categorías | un clic | F10 | `inventory.category.bulk_create` |
| Cambia una categoría | cambiar categorías | un clic | F06 | `inventory.category.update` |
| Elimina una categoría y desvincula sus productos | eliminar categorías | escribir para confirmar | F07 | `inventory.category.delete` |
| Exporta productos o categorías a CSV | exportar productos | un clic | F11 | `inventory.product.export`, `inventory.category.export` |
| Registra una recepción de mercancía (uno o varios productos, coste y albarán) | mover stock | un clic | F13 | `inventory.stock.receive` |
| Aplica un recuento: el saldo pasa a ser lo contado, con motivo | mover stock | un clic | F14 | `inventory.stock.count` |
| Da de baja una cantidad sin venta (merma, rotura, consumo propio), con motivo | mover stock | un clic | F15 | `inventory.stock.write_off` |
| Manda a imprimir la etiqueta del código de barras | ver productos | un clic | F25 | `inventory.product.print_label` |
| Guarda los ajustes | gestionar ajustes | un clic | F19 | `inventory.config.update` |

### Lo que avisa (para las apps que quieran reaccionar)

| Aviso | Cuándo | Qué lleva | Quién lo usa | Servicio |
|---|---|---|---|---|
| Producto nuevo | Alta por pantalla, importación, plantilla, asistente o API | El producto y sus categorías | Flujos; paneles del Inicio | `inventory.product.created` |
| Producto cambiado | Cambio, activar o desactivar, marcar agotado o volver a la venta | El producto como queda, también si está agotado | Flujos; paneles del Inicio; el TPV, Cocina y Menús | `inventory.product.updated` |
| Producto eliminado | Eliminar | Cuál era (SKU y nombre) | Flujos; paneles del Inicio | `inventory.product.deleted` |
| Producto añadido a una categoría | Alta, cambio o enlace suelto | Producto y categoría | Flujos | `inventory.product.categorized` |
| Producto quitado de una categoría | Cambio, enlace suelto o categoría eliminada | Producto y categoría | Flujos | `inventory.product.uncategorized` |
| Stock cambiado | Cualquier movimiento: inicial, recepción, recuento, baja, venta, anulación | Producto, cantidad, saldo y tipo de movimiento | Panel y paneles del Inicio | `inventory.stock.changed` |
| Cruce del mínimo | Un artículo con control cruza su umbral, hacia abajo o «recuperado» | Producto (SKU y nombre), cantidad antes y después, umbral, tipo de movimiento, venta o albarán | Flujos (avisar para reponer) | `inventory.stock.threshold_crossed` |
| Categoría nueva, cambiada o eliminada | Crear, cambiar o eliminar una categoría | Cuál (id y nombre) | Las pantallas abiertas | `inventory.category.created`, `.updated`, `.deleted` |
| Ajustes cambiados | Guardar los ajustes con algún cambio | Nada | El Panel y las listas abiertas | `inventory.config.updated` |

Los avisos llevan solo lo que dice la columna «Qué lleva»: ni la identidad fiscal del negocio ni
datos de quien lo provocó.

### A qué reacciona (avisos de otras apps)

| Aviso de | Qué hace Inventario | Flujos | Servicio que escucha |
|---|---|---|---|
| Ventas: venta cobrada | Baja el stock de cada línea y de los componentes de los menús | F21, F22 | `sale.sale.completed` |
| Ventas: venta anulada | Repone exactamente lo que esa venta bajó | F23 | `sale.sale.voided` |
| Ventas: venta devuelta | Repone las unidades de las líneas que vuelven, una vez por devolución | F24 | `sale.sale.refunded` |

### Lo que necesita de otras apps

| De | Para qué | Flujos | Servicio |
|---|---|---|---|
| Impuestos | Las categorías fiscales con su tipo, para el selector (también para nombrar la elegida cuando no está entre las primeras) y para importar productos | F01, F02, F06, F09 | `tax.category.list` |
| Impuestos | Comprobar al guardar o importar que la categoría fiscal elegida existe y sigue activa, y saber qué productos no la tienen (lectura directa: es una app requerida) | F01, F02, F05, F06, F09, F10 | modelo `tax.TaxCategory` |
| Impuestos | Reconocer el texto de la columna fiscal de un CSV: la clave, el nombre en cualquier idioma o un texto aprendido | F09, F10 | `tax.alias.resolve` |
| Impuestos | Crear una categoría fiscal o aprender un texto desde la importación | F09 | `tax.category.create`, `tax.alias.create` |
| Ventas | El número del tique o la factura de una venta, para la Referencia de un movimiento | F16 | `sale.sale.get` |
| Impresión | Mandar la etiqueta a la impresora con la función «Etiqueta» | F25 | `printing.job.create` |
| Plataforma | La moneda del negocio (la de su país; en el hub propio de ERPlora, la del país de su emisor), para escribir los precios y costes del CSV, leerlos al importar y ponerla en la etiqueta | F09, F11, F25 | `base.business.get` |

Inventario no usa nada más de otras apps: el número de una venta le llega en su aviso, y el de su tique o
factura se lo da Ventas, no Facturación.

### Quién puede qué

| Permiso | Administrador | Responsable | Empleado | Cajero | Servicio |
|---|---|---|---|---|---|
| Ver productos | sí | sí | sí | sí | `inventory.view_product` |
| Ver categorías | sí | sí | sí | sí | `inventory.view_category` |
| Ver stock y movimientos | sí | sí | sí | sí | `inventory.view_stock` |
| Dar de alta productos | sí | sí | no | no | `inventory.add_product` |
| Cambiar productos | sí | sí | no | no | `inventory.change_product` |
| Eliminar productos | sí | sí | no | no | `inventory.delete_product` |
| Crear categorías | sí | sí | no | no | `inventory.add_category` |
| Cambiar categorías | sí | sí | no | no | `inventory.change_category` |
| Eliminar categorías | sí | sí | no | no | `inventory.delete_category` |
| Importar productos | sí | sí | no | no | `inventory.import_product` |
| Exportar productos | sí | sí | no | no | `inventory.export_product` |
| Mover stock (recibir, contar, dar de baja) | sí | sí | no | no | `inventory.adjust_stock` |
| Gestionar ajustes | sí | sí | no | no | `inventory.manage_settings` |

Son los permisos de fábrica de cada perfil; el administrador los puede cambiar en Roles. El
administrador lo puede todo. La app los comprueba en todas las puertas (pantalla, asistente y
API), no solo en la pantalla.

## Para quien lo mantiene
Lo que sigue es para quien cambia la app; quien la usa puede parar aquí.

## El servidor (fase de servidor, 2026-10-14)

- **Anatomía**: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/` y un `tests/test_<fichero>.py` por fichero.
  Las páginas (`frontend/`) son las del módulo viejo: Panel, Productos, Movimientos, Categorías y Ajustes.
- **31 operaciones** (12 consultas y 19 acciones), todas con `ai` (descripción y, en las acciones,
  riesgo: `high` para eliminar e importar) y con `expose_api` salvo las tres reacciones a Ventas. Las
  rutas no llevan parámetros: el producto o la categoría viajan en la entrada.
- **Requiere `tax`**: producto y categoría tienen FK a `tax.TaxCategory` (`PROTECT`, sin acceso inverso).
  «Sin configurar» (`needs_tax_setup`) = sin categoría fiscal o con una que Impuestos desactivó. Toda
  puerta rechaza una clave inexistente o inactiva. La importación de categorías lee el texto fiscal con
  `tax.alias.resolve` (clave, nombre en cualquier idioma o alias aprendido).
- **Cantidades**: `Decimal` exacto con tres decimales (el escalón más fino, el gramo en el kilo). Las
  ocho unidades son un registro en código (`models.UNIT_SPECS`: tipo, factor como fracción exacta y
  escalón), no una tabla: el negocio nunca crea unidades. Una cantidad fuera del escalón es 409
  `inventory.off_grid_quantity` con su campo; nunca se redondea. Dinero en céntimos enteros.
- **Campos de importe** (precio, coste, coste unitario; F01, F02, F13): se escriben y se leen con los decimales de
  la moneda del negocio (`useBusinessMoney`, los del servidor, nunca los del navegador). Si el panel se abre antes de
  que `base.business.get` conteste, el precio y el coste que la persona no ha tocado se reescriben desde lo guardado
  en cuanto llega la moneda (o cambia), y con ellos lo que el editar compara para mandar solo lo cambiado; lo ya
  escrito se queda tal cual y se lee en esa moneda al guardar (si no se puede, lo dice el campo), y salir del campo
  no lo reformatea mientras la moneda no se sabe.
- **Referencias de persona**: `find_product` busca por SKU (sin mayúsculas), luego por nombre exacto y
  luego por el único nombre que lo contiene; varios → 409 `inventory.product_ambiguous` con los
  candidatos. Igual `find_category` por nombre o slug.
- **Libro de movimientos**: `_move` escribe saldo y movimiento juntos con la fila del producto
  bloqueada; varios productos se bloquean por orden de id. El cruce del mínimo se decide una vez por
  operación sobre el total (también suelto + dentro de un menú).
- **Inicio** (ronda PLAN-HUB 2026-10-21): `setup` y `widgets` de `apps.py`, los del `module.json` viejo (sin
  `bell`). El paso `inventory.catalog` lee `active_products` de `inventory.stock.get_summary` (orden 30,
  `required`, permiso `inventory.add_product`, `events.PRODUCT_EVENTS`); los cuatro paneles leen
  `inventory.stock.get_summary` y `inventory.product.list_low_stock` (`limit` 5) con permiso
  `inventory.view_product` y `events.FIGURE_EVENTS`, las mismas que re-ejecutan el Panel (`live.py`). Ningún
  panel fija moneda ni idioma (gh:inventory#123) ni categoría (gh:inventory#126); un KPI no repite su nombre en
  `options.label` (gh:hub#1105).
- **Ventas**: `events.REACTIONS` lleva `sale.sale.completed` → `inventory.stock.apply_sale`,
  `sale.sale.voided` → `inventory.stock.restore_sale` y `sale.sale.refunded` →
  `inventory.stock.restore_refund`; `events.react` los ejecuta como sistema, cada uno en su transacción.
  La nota por devolución (`RefundStock`, única por `refund_id`) hace que cada una reponga una vez; lo
  que repone sale del libro (venta menos devoluciones anteriores), y la anulación descuenta lo ya
  devuelto. Los tests usan el evento real de Ventas, importando `apps.sale` solo en los tests. Su permiso, `inventory.system`, no lo tiene ningún rol. La nota por venta
  (`SaleStock`: `moved`, `unmoved`, `voided`) hace que la venta baje una vez, que la anulación reponga
  una vez lo que dice el libro y que una anulación que llega antes deje la venta sin efecto. Los entrega
  el relay del outbox del worker (`base/relay.py`, desde hub#105): `tests/test_relay.py` cobra, anula y
  devuelve con las operaciones reales de Ventas (y Menús) y pasa un tick real del worker. La forma del evento de Ventas (`sale_id`, `items[]` con `product_id`, `quantity`,
  `is_service` y `components[]`) la fija el WORKBOOK de Ventas.
- **Importar**: el servidor es la autoridad: recibe las celdas como texto ya mapeadas a nuestros
  campos, lee importes y cantidades en formato español o inglés (con los dos separadores manda el de
  la derecha; con solo comas, la coma es el decimal) y devuelve el informe por fila; `dry_run` es el
  ensayo. Hasta 100 filas por llamada: el cliente parte el fichero (y con ello «Parar») y detecta los
  SKU repetidos entre trozos. La adivinanza de cabeceras y la ventana fiscal son de la página.
- **Exportar**: CSV con los formatos CLDR del idioma de la petición (librería `babel`), `;` donde la
  coma es el decimal (Excel en español) y BOM UTF-8. Los importes van en la moneda del negocio y con sus
  decimales; exportar, importar y la etiqueta (F25) la preguntan a `base.operations.business_currency` como toda
  app que cobra (BASE-F50), sin copia propia: la de su país que contesta `base.business.get`, leída como la
  plataforma (una API key solo lleva el permiso de la operación), y en el hub propio de ERPlora, sin negocio en
  erplora.com (fase 1, sin fila de registro: `create_platform_hub`), la del país de su emisor
  (`PLATFORM_ISSUER_COUNTRY`), como Ventas y Tarifas (`tests/test_business_currency.py`);
  la importación acepta su código y su símbolo alrededor de la cifra («PLN12.50», «12,50 zł»), no los de otra.
- **Agotado (INVENTORY-F29, 2026-10-21)**: `Product.is_sold_out` con `db_default=False` (la 0003 solo
  añade la columna: un proceso con el código anterior sigue insertando). «A la venta» = activo y no
  agotado (`queries.ON_SALE`): es lo que da el filtro `is_active` de `inventory.product.list` (`false` da
  el resto, inactivos o agotados) y `list_for_sale`; la cifra de cada categoría cuenta los activos,
  agotados incluidos (lo que enseña el TPV, FIX-INVENTORY-SOLD-OUT-GREYED-IN-POS); `include_sold_out=true`
  hace que `is_active` sea solo el interruptor (la rejilla, el buscador y el «Todos» del TPV, que enseñan
  lo agotado en gris (SALE-F07), y los selectores de Menús, que configuran y no venden); `status=sold_out` filtra la marca y la fila lleva `is_sold_out`. Menús lee
  `Product.is_sold_out` directamente (`requires`): estado `product_sold_out` y 409 `combo.option_sold_out`. `inventory.product.set_sold_out`
  (permiso de cambiar productos) reutiliza `inventory.product.updated`, con `is_sold_out` en la carga:
  el TPV, Cocina y Menús re-ejecutan sus consultas sin tocar `live.py`. La ficha (`inventory.product.get`)
  sigue dando el artículo, marcado: es lo que lee Ventas al congelar una línea.
- **Referencia de una venta (INVENTORY-F16, 2026-10-21)**: la nota por venta (`SaleStock`) guarda
  `sale_number` (del aviso `sale.sale.completed`) y `document_number` (el `invoice_number` que da
  `sale.sale.get`, leído como sistema al bajar el stock; vacío si Ventas no lo sabe). `inventory.movement.list`
  devuelve `reference_label` (tique o factura, si no el número de la venta, para venta, anulación y
  devolución; la propia referencia para el resto) y su búsqueda y su filtro de Referencia encuentran una
  venta por cualquiera de los dos números. Migración `0004` solo añade columnas con `db_default` (expand).
- **Etiqueta (INVENTORY-F25, 2026-10-21)**: `inventory.product.print_label` (permiso de ver productos) pide
  a Impresión `printing.job.create` por su nombre (sin `requires`): un `barcode_label` con `product_name`,
  `barcode` (el SKU) y `price` en unidades de la moneda del negocio (`currency`, con la que Impresión le pone
  los decimales; en el hub propio de ERPlora, la del país de su emisor, como al exportar). Sin la cola
  (Impresión no instalada, apagada o sin `printing.print`) responde 409 `inventory.label_queue_unavailable` y la
  ficha imprime desde el navegador; un SKU fuera del ASCII imprimible, 409 `inventory.sku_not_barcode`. La placa
  dibuja el Code 128 con JsBarcode (renderizador a objeto: las barras las pinta Vue, sin HTML) y la impresión del
  navegador es una hoja solo para papel (`@media print`), hecha con el DOM.
- **Avisos añadidos** a la lista del producto: `inventory.category.*` e `inventory.config.updated`, solo
  para refrescar las consultas vivas.
- **Administrador de Django**: CRUD completo de todas las tablas para soporte (ronda 12, PLAN §17), el
  libro incluido: es un segundo camino de escritura que avisa y no impide; ids y fechas automáticas se
  ven pero no se editan. Las pantallas, el asistente y la API siguen sin editar el libro.
- **Pruebas que bloquean**: dos ventas de la última unidad, la misma venta dos veces, una venta y su
  anulación, y dos bajas del saldo entero, a la vez y en dos hilos (`test_services.py`). Con Impuestos
  real, sin dobles (`test_integration_tax.py`): categoría de fábrica y su tipo calculado, categoría
  desactivada rechazada por toda puerta, y textos fiscales leídos por sus alias.
- **Categorías**: nacen con el icono `ion:cube-outline` y el color `#3880ff`, como en el módulo viejo.
- **Roles**: el `cashier` viejo no existe; lo que tenía (ver productos, categorías y stock) es del
  empleado (`hub_employee`).
- **Del módulo viejo se queda fuera, a propósito**: almacenes (`inventory_location`) y variantes
  (`inventory_product_variant`), que este WORKBOOK excluye; la foto del producto y la imagen de la
  categoría (duda 6); el SKU autogenerado `PROD-NNN` de su alta en lote (aquí el SKU es obligatorio,
  INVENTORY-F09); desactivar una categoría (cambio 5); `inventory.products.unit_of` y
  `inventory.products.stock_levels`, que eran lecturas internas de los handlers (aquí la unidad sale en
  la ficha y en `inventory.unit.list`, y el saldo se lee dentro de la transacción).

## Cambios frente al producto actual

La app hace lo mismo que el módulo Inventario actual y se ve igual, salvo estos arreglos de fallos
que su `WORKFLOW.md` tenía anotados. Cada uno se puede vetar antes de construir su flujo.

1. **La app comprueba en todas las puertas lo que antes solo comprobaba la pantalla**: que la
   categoría fiscal existe en Impuestos (F01, F02), el escalón de la unidad en la recepción y el
   recuento (F13, F14), los permisos de importar y de exportar (F09, F11) y que un servicio no se
   recibe ni se cuenta (F13, F14).
2. **El stock inicial deja movimiento «Inicial»**, venga del alta, de un CSV o de una plantilla
   (F01, F09, F12, F16). Antes el saldo no se explicaba por el libro.
3. **El producto y sus categorías se guardan juntos**: o todo o nada (F02, F08). Antes las
   categorías se guardaban después, una a una.
4. **La unidad de un producto con stock no se cambia** (F02, F26). Antes 3 unidades pasaban a ser
   3 kg sin convertir.
5. **Editar una categoría no borra lo que la pantalla no enseña** (descripción, icono, color, orden),
   y **las categorías no se desactivan**: antes una categoría desactivada por la API desaparecía sin
   forma de volver (F06).
6. **Importar productos**: acepta coma o punto y coma (el CSV de Excel en español); el texto fiscal
   se compara también con el nombre traducido; si Impuestos no puede guardar un texto o una
   categoría, se dice en el informe (F09).
7. **Importar categorías** da el mismo informe que la de productos, omite las que ya existen por
   nombre y no deja categorías sin tipo en silencio (F10).
8. **Exportar** baja todo el catálogo filtrado, con las cifras como se leen, todos los campos y las
   cabeceras que la importación reconoce (F11). Antes bajaba solo la página, con cifras internas.
9. **Todo movimiento avisa de stock cambiado**, así el Panel y los paneles del Inicio se refrescan
   también tras una venta, una anulación o una recepción (F17, F21, F23).
10. **El aviso de cruce de mínimo es exacto**: solo con lo que de verdad se movió, también al anular,
    y ni se pierde ni se duplica con dos movimientos a la vez (F18, F21, F23).
11. **La anulación repone bien llegue antes o después que la venta** (F23). Antes, si la venta se
    reintentaba después de la anulación, el stock quedaba bajado por una venta anulada.
12. **Todas las consultas y acciones están en la API y en el asistente** (F13, F15). Antes recibir y
    dar de baja no estaban en la API pública.
13. **Dar de baja stock pide el permiso de mover stock**, no el de cambiar productos (F15).
14. **Una recepción con una línea mala se rechaza entera** diciendo qué línea falla (F13). Antes esa
    línea no movía nada y no se avisaba.
15. **Un SKU o un EAN-13 repetido se dice siempre con su mensaje** (F01). Antes dependía del texto
    del error de la base de datos.
16. **Cada pulsación de «Imprimir código de barras» saca una etiqueta**, y si ninguna impresora
    tiene la función «Etiqueta» se dice (F25). Antes, por la cola, cada producto sacaba su etiqueta
    una sola vez en toda su vida y sin aviso. Es lo que hacen Square y Shopify POS (imprimir
    etiquetas bajo demanda).
17. **Los avisos solo llevan los datos del flujo** (sección «Lo que avisa»). Antes copiaban también
    la identidad fiscal del negocio y quién lanzó la acción.

## Cobertura contra la referencia

| Elemento de la referencia | Qué hará la app | Flujo |
|---|---|---|
| Ficha con nombre, SKU, precio, coste, categoría fiscal, código de barras y unidad | sí | F01, F02 |
| Foto del artículo en la ficha | no: duda 6 | F01 |
| Precio por una cantidad distinta de la unidad (por 100 g, por kg con stock en g) | parcial: solo por el asistente o la API (duda 12) | F01, F26 |
| Categoría fiscal obligatoria y existente al guardar | sí | F01, F02 |
| Activar y desactivar sin borrar | sí | F03 |
| Borrado que conserva el historial y libera el código | sí | F04 |
| Categorías con orden, color e icono para la carta | parcial: se guardan por el asistente o la API; el TPV ordena por nombre (duda 6) | F06, F08 |
| Borrar una categoría desvincula | sí | F07 |
| Importar CSV con mapeo, ensayo e informe | sí | F09, F10 |
| CSV con punto y coma (el de Excel en español) | sí | F09, F10 |
| Actualizar precios de productos existentes por CSV | no: un SKU que ya existe se omite (duda 9) | F09 |
| Exportar el catálogo entero | sí | F11 |
| Control de stock por artículo con valor por defecto del negocio | sí | F20 |
| Recepción de mercancía con coste | parcial: en pantalla, un producto cada vez y sin albarán (duda 10) | F13 |
| Recuento absoluto con motivo | sí | F14 |
| Merma, rotura o consumo propio con motivo | sí: ventana «Baja» en la fila y la ficha, el asistente y la API | F15 |
| Historial de movimientos con quién y cuándo | parcial: se guarda quién, la pantalla no lo enseña ni filtra por fecha o producto (duda 11) | F16 |
| Alerta de stock bajo | parcial: panel, paneles del Inicio y aviso para Flujos, sin notificación (duda 13) | F17, F18 |
| No vender lo que no hay, o vender en negativo, según el ajuste | parcial: el TPV no lo impide; apagado, la venta no baja nada (duda 1) | F19, F21 |
| Agotado («86»): el TPV lo enseña en gris y no lo vende | sí: «Marcar agotado» en Productos y en la ficha, el asistente y la API | F29, F27 |
| Cantidad restante en el TPV («quedan 3») | no, a propósito por ahora | F27 |
| La venta baja el stock, una sola vez | sí | F21 |
| Menú o pack baja sus componentes | sí | F22 |
| La anulación repone exactamente lo que salió | sí | F23 |
| La devolución repone el stock | sí: las unidades de las líneas que vuelven, una vez | F24 |
| Etiqueta de código de barras con nombre y precio | sí | F25 |
| Lectura del código de barras en el TPV | no: la etiqueta lleva el SKU y el TPV no busca por EAN-13 (duda 7) | F25, F27 |
| Venta al peso con báscula | no: falta leer la báscula | F26 |
| Varios almacenes y traspasos | no, a propósito (futura app de almacenes) | — |
| Recetas o escandallos que bajan ingredientes | no, a propósito (fuera del MVP) | — |
| Variantes (talla, tamaño) con stock propio | no, a propósito por ahora | — |

## Datos: de quién es cada dato

- **Propios**: los productos (con su unidad, su umbral, su control de stock y su categoría fiscal,
  guardada como referencia a Impuestos), las categorías de producto y sus enlaces con los
  productos, el libro de movimientos, las unidades de medida, los ajustes (uno por negocio) y la
  marca de «venta ya repuesta» o «venta sin movimientos», y la de «devolución ya repuesta».
- **Lee de otros**: las categorías fiscales, sus tipos y los textos aprendidos, de Impuestos; al
  importar también crea en Impuestos categorías y textos aprendidos, siempre por sus servicios. En
  Movimientos, el número de la venta (Ventas) y el de su tique o factura (Facturación), solo para
  pintarlo. De Ventas recibe la venta cobrada (líneas, cantidades, componentes) y la venta anulada
  (cuál es).
- **Lo leen otros**, siempre por los servicios de la sección anterior: Ventas (catálogo de venta,
  rejilla, categorías, enlaces y unidades), Cocina (productos y categorías para su reparto), Menús
  (los productos que pueden ser componente) y el núcleo (las cifras de los paneles del Inicio y el
  primer paso de la puesta en marcha). Ninguna app toca sus datos directamente.
- **Datos personales**: no guarda clientes. Sí guarda quién creó y quién cambió cada producto y
  cada categoría, quién hizo cada movimiento, y textos libres que pueden llevar un nombre: el
  **motivo** de recuentos y bajas y la **descripción** de productos y categorías. La referencia de
  un movimiento de venta es la venta. Al eliminar un negocio se borra todo lo suyo.

## Reglas que no se rompen

Las hace cumplir la app por cualquier puerta (pantalla, asistente, API).

- **Aislamiento**: nada de un negocio se ve ni se toca desde otro; un producto solo se enlaza con
  una categoría del mismo negocio.
- **SKU y EAN-13 únicos entre los productos vivos** del negocio; un producto eliminado libera los
  dos.
- **Un producto no se guarda sin una categoría fiscal que exista en Impuestos**, al crear, editar o
  importar.
- **Dinero**: precio y coste en céntimos, enteros y nunca negativos.
- **Cantidades exactas**, sin redondear, siempre en el escalón de su unidad (como mucho, un gramo
  dentro del kilo).
- **El stock no se edita en la ficha**: solo lo mueven el stock inicial, la recepción, el recuento,
  la baja, la venta y la anulación. El SKU tampoco se edita. La unidad no se cambia con stock.
- **Recuento**: valor absoluto, nunca negativo, con un motivo de 3 a 500 caracteres.
- **El libro no se edita ni se borra.** Cada cambio de saldo y su movimiento se escriben en el
  mismo paso: no hay movimiento sin cambio de saldo ni cambio de saldo sin movimiento.
- **Sin «Permitir vender sin stock», el saldo nunca queda en negativo** por una venta o una baja: si
  no alcanza, no baja nada (y la baja se rechaza).
- **Un servicio no tiene stock**: no se recibe, no se cuenta y no baja. Un artículo sin control de
  stock no baja por una venta.
- **La anulación repone una sola vez y solo lo que salió**, leído del propio libro, llegue antes o
  después que la venta. **Una devolución repone una sola vez y nunca más de lo que su venta bajó**
  menos lo ya devuelto.
- **Permisos**: los de «Quién puede qué», en todas las puertas.
- **Borrado lógico**: un producto o una categoría eliminados no desaparecen de la base de datos y
  sus movimientos se conservan.

## Lo que NO hace, a propósito

- No gestiona almacenes, ubicaciones, traspasos, lotes, caducidades ni valoración FIFO o media: es
  de una futura app de almacenes. El coste de una recepción sustituye el del producto.
- No hace recetas ni escandallos: un plato no baja sus ingredientes; un suplemento nunca mueve
  stock.
- No calcula impuestos: solo guarda la categoría fiscal (eso es Impuestos).
- No pone el precio de una venta ni cobra: lo hace Ventas con el precio de este catálogo.
- No vende servicios con agenda: los servicios de la peluquería viven en Servicios.
- No gestiona variantes (talla, tamaño).
- No crea unidades de medida: usa las ocho de fábrica.
- No cambia el tipo de un producto (físico o servicio) después de crearlo.
- No imprime por sí misma: entrega la etiqueta a Impresión.
- No enseña en el TPV cuántas unidades quedan, ni marca un artículo agotado sola cuando su stock llega
  a cero, ni lo vuelve a poner a la venta al recibir mercancía: la marca «Agotado» la pone y la quita
  una persona (F29).

## Dudas abiertas

Se resuelven mirando cómo lo hace el mercado (skill `market-decision`) **antes** de escribir el
código del flujo; mientras tanto, el flujo hace lo que dice arriba.

1. Con «Permitir vender sin stock» apagado (el de fábrica), una venta que supera el saldo se cobra y
   el stock no baja nada, sin aviso (F21). ¿Debe el TPV avisar o impedir la venta, o la venta debe
   bajar a negativo igualmente y el ajuste solo gobernar el aviso?
2. ~~¿Debe la devolución de una venta reponer stock, con una casilla «devolver al stock» por línea
   como Square y Toast (F24, SALE-F31)?~~ Resuelta (2026-10-14): sí; Ventas dice qué líneas y cuántas
   unidades vuelven y Inventario las repone (F24).
3. ~~¿Hace falta una pantalla de baja con motivo (merma, rotura, consumo propio) o basta el recuento
   (F15)?~~ Resuelta (2026-10-14): sí, la ventana «Baja» en la fila y la ficha de Productos, como
   Square (ajustes con motivo «dañado», «perdido»), Odoo («Desechar»), Shopify y Lightspeed.
4. El «Tipo de IVA / Impuesto» de una categoría no lo usa nadie (F06): ¿se quita, o los productos de
   la categoría deben heredarlo?
5. El «Umbral de stock bajo» de Ajustes solo lo hereda un producto creado por el asistente o la API
   sin umbral (F19): ¿debe el formulario dejar el campo vacío para heredarlo, y debe un cambio del
   ajuste alcanzar a los productos que lo heredaron?
6. ¿Entran en el MVP la foto del artículo en la ficha y el orden, el color y el icono de las
   categorías en el TPV (F01, F06, F08)?
7. ¿Debe la etiqueta llevar el EAN-13 cuando lo hay, y el TPV buscar por código de barras (F25,
   F27)?
8. ¿Debe un artículo poder volver a «Sigue el ajuste del hub» después de haber decidido (F20)?
9. ¿Debe la importación actualizar el precio y los datos de un SKU que ya existe, como Shopify, en
   vez de omitirlo (F09)?
10. ¿Hace falta en pantalla la recepción de un albarán con varios productos y su número (F13)?
11. ¿Debe Movimientos enseñar quién hizo cada movimiento y filtrar por fecha y por producto (F16)?
    Cambia el aspecto de la pantalla.
12. ¿Debe el formulario dejar referir el precio a otra cantidad (por 100 g, por kilo con el stock en
    gramos) (F01, F26)?
13. ¿Debe haber una notificación visible de stock bajo, además del aviso para Flujos (F18)?
