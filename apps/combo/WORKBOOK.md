# Workbook — Menús y combos (app)
Prefijo: COMBO
Alcance MVP: restaurante
Estado de la app: hecha (servidor y páginas); lo que pinta o manda Ventas lo dice cada flujo

> Manual de usuario y especificación de la app `combo`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Menús y combos del producto actual
> (`modules-workspace/modules/combos`, `origin/main` `0fd6e5d`, v0.1.18) y de lo que Ventas e
> Inventario hacían con los menús (sus tests `combo_fire`, `combo_split`, `order_combo`,
> `order_menu_checkout`, `combo_stock` y `combo_components_stock`). Hace lo mismo, se ve igual y
> conserva su funcionalidad salvo lo que dice «Cambios frente al producto actual», al final. Los
> números de flujo se conservan (`COMBOS-Fnn` → `COMBO-Fnn`) porque otras apps los citan.

## Para qué sirve y para quién

Menús y combos guarda los artículos compuestos que se venden a **precio cerrado**: el menú del día
(«primero + segundo + postre + bebida por 13,50 €»), el menú infantil o el «bocadillo + bebida» para
llevar. Cada menú tiene **platos** (Primero, Segundo, Bebida…), cada uno con cuántas elecciones pide
como mínimo y como máximo, y cada plato ofrece **elecciones**: productos reales del catálogo de
Inventario, con un **suplemento** si sustituir cuesta más (o menos).

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** montan los menús: precio, cómo se
  vende, platos, elecciones, suplementos, orden y qué está agotado hoy.
- El **empleado** los consulta, y en el TPV los vende (la hoja del TPV es de Ventas).
- El **asistente**, por voz o por texto y con la sesión de quien habla: «crea el menú del día a 13,50
  para tomar en el local», «añade al menú del día un plato Primeros», «pon las lentejas en Primeros»,
  «la merluza lleva 2 euros de suplemento», «hoy no hay flan».

Este módulo guarda el menú y dice lo que vale y cómo se factura; **Ventas** lo ofrece en el TPV y lo
cobra, **Inventario** baja el stock de cada plato y **Cocina** recibe cada plato en su estación. No es
un descuento ni una variante, ni los extras de un plato (eso es Suplementos).

## Referencia adoptada

El barrido de mercado del producto actual (`architecture/modules/combos.md`, 24/08/2026: 10
referencias y sus foros) sigue vigente y se adopta, no más:

- [Square — combos](https://squareup.com/help/us/en/article/8558-create-and-sell-combos): el combo es
  un artículo del catálogo, con «elecciones requeridas» por grupo y un cargo por opción; un artículo
  agotado no se ofrece.
- [Lightspeed K-Series — combos](https://k-series-support.lightspeedhq.com/hc/en-us/articles/1260804656529-About-combos):
  grupos con cuántos artículos hay que elegir, a precio fijo; se añaden varios artículos de golpe.
- [Odoo — combos](https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/combos.html):
  precio extra por opción y el precio cerrado repartido en una línea por componente, en proporción a
  su precio de catálogo ([foro: cómo calcula el reparto](https://www.odoo.com/forum/help-1/how-does-odoo-calculate-the-price-split-on-combo-products-on-pos-250869)).
- Shopify Bundles, WooCommerce Product Bundles, NetSuite (kit), Holded (pack): el stock lo mueven
  los componentes, nunca el menú.
- Toast y Clover lo hacen como un descuento, y por eso **no** se siguen: un descuento no se manda a
  cocina, no se desglosa ni mueve stock.
- Ley del IVA: **art. 91.Uno.2.2º** (el menú servido en el local es una prestación única de
  restauración al 10 %, la bebida incluida, también la alcohólica) y **art. 79.Dos** (el pack de
  bienes a precio único reparte la base en proporción al valor de mercado de cada bien, que HMRC
  concreta como el precio de venta individual: [VATVAL03800](https://www.gov.uk/hmrc-internal-manuals/vat-valuation/vatval03800)).
- Confirmar antes de borrar (Square, Odoo, Shopify): un menú, un plato o una elección se quitan con
  una pregunta antes.

## Antes de empezar

- Menús necesita **Inventario** (sus elecciones son productos del catálogo) e **Impuestos** (el tipo
  de IVA de un menú «en el local»). Al activar Menús se activan los dos.
- Solo un producto que se vende y se cobra **por unidades** puede ser una elección (un menú lleva «una
  ración», no «un kilo» ni «el precio de 100»); los buscadores solo ofrecen esos. Un producto desactivado
  o eliminado en Inventario no se puede añadir.
- El precio cerrado y los suplementos son importes en euros, escritos con coma o punto.

Configuración inicial, paso a paso:

1. Abre **Menús** y pulsa **+** (COMBO-F02): nombre, precio cerrado, cómo se vende y, si es «en el
   local», el tipo de IVA.
2. Toca el menú para abrir su **constructor** y añade sus platos con el mínimo y el máximo de cada uno
   (COMBO-F05).
3. En cada plato, añade las elecciones, con su suplemento si lo hay (COMBO-F06).
4. Mira el aviso de arriba del constructor: dice si el menú ya sale en el TPV o qué le falta.

## Pantallas

### Menús
Menú **Menús**. Tabla de menús con el buscador «Buscar un menú…» (busca por nombre y por nombre de
cocina), vista de tabla o de tarjetas y columnas: Nombre (se ordena y se filtra), «Precio cerrado» (se
ordena), «Cómo se vende» («En el local» o «Para llevar»; se ordena y se filtra), «A la venta» (Sí o No;
se ordena y se filtra) y Orden (se ordena). Páginas de 50, por orden y nombre. Con permiso de gestión
hay botón **+** y, por fila, «Editar datos» y «Retirar»; sin él, solo se ve la lista. Tocar una fila
abre el constructor.

El formulario de alta y de edición (título «Menú nuevo» o «Menú · {nombre}») lleva: Nombre, «Nombre
de cocina» («Déjalo vacío y la comanda usa el nombre comercial.»), «Precio cerrado» («Lo que paga el
cliente por el menú entero, elija lo que elija.»), «¿Cómo se vende?» («Se consume en el local
(servicio de restauración)» o «Se vende como producto / para llevar», con la explicación de las dos
siempre a la vista y la elegida resaltada), «Tipo de IVA» (solo si es «en el local»), «Orden en la
lista de menús» y la casilla «A la venta» (marcada de partida), con «Guardar» y «Cancelar».

### Constructor del menú
Se abre al tocar un menú (`/combo/menus/<id>`). Arriba, la flecha atrás («Todos los menús»), el nombre
y el precio del menú, y un aviso con lo que hará ese menú en el tique: «Este menú se factura como un
único servicio: una sola línea a su tipo de IVA, tributen como tributen sus componentes.» o «Este menú
se factura como entrega de bienes: su precio se repartirá entre los componentes que añadas, una línea
por cada uno.». Debajo, si el menú todavía no sale en el TPV, otro aviso dice por qué («Todavía no
sale en el TPV: …»).

Después, la sección «Platos» («Un plato es un paso de ESTE menú: Primero, Segundo, Postre, Bebida. Su
orden es el orden en que se pregunta.») y una tarjeta por plato, en orden: nombre, su regla
(«Obligatorio · elige 1 · hasta 1 · sin repetir») y, con permiso de gestión, el asa de arrastre,
«Subir», «Bajar», «Editar datos» y «Retirar». Dentro, «Elecciones»: una fila por producto con su
suplemento, una marca «Agotado» si no está disponible hoy y, si el producto ya no se puede vender, «Desactivado en Inventario», «Ya no está en el
catálogo», «No se vende por unidades en Inventario» o, en un menú «para llevar», «Sin tipo de IVA para
llevar»; por fila, el asa, subir, bajar, «Agotado / Disponible», editar y quitar. Debajo, el buscador
«Busca un producto…», «Suplemento», «Añadir elección» y «Añadir varios» (ventana con buscador y
casillas: «Añadir N seleccionados»; lo que ya está en el plato sale marcado «Ya está en este plato»).
Al final, el formulario «Añadir un plato» (Nombre del plato, «Elecciones mínimas», «Elecciones
máximas», la casilla «Se puede elegir la misma opción más de una vez» y «Guardar»), que pasa a
«Plato · {nombre}» al editar uno.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» en el hueco de la tabla; «Cargando los platos…» en el constructor. |
| Vacío | «Aún no hay menús. Crea el primero con el botón +.»; con búsqueda o filtro, «Sin resultados». En el constructor, «Aún no hay platos. Añade el primero: un menú sin platos no tiene nada que elegir.» y, en un plato, «Aún no hay elecciones: nadie puede resolver este plato.». |
| Error | El aviso de la tabla con «Reintentar»; «No se han podido cargar los platos de este menú.» en el constructor. El rechazo de un formulario sale dentro del formulario, sin perder lo tecleado; el de una elección, dentro de su plato. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| Ya no existe | Si el menú se retira mientras su constructor está abierto (aquí o en otro dispositivo), el constructor se vacía y dice «Este menú ya no existe» («Se ha retirado, quizá desde otro dispositivo.»), con «Todos los menús» para volver. |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| COMBO-F01 | Consultar y buscar los menús | hecho |
| COMBO-F02 | Crear un menú a precio cerrado | hecho |
| COMBO-F03 | Cambiar los datos de un menú, ponerlo o quitarlo de la venta | hecho |
| COMBO-F04 | Retirar un menú | hecho |
| COMBO-F05 | Montar los platos de un menú | hecho |
| COMBO-F06 | Elegir los productos de cada plato y su suplemento | hecho |
| COMBO-F07 | Elegir un menú al vender | servidor hecho; la hoja del TPV es de Ventas (pedido a Ventas) |
| COMBO-F08 | Cobrar el menú: precio cerrado y suplementos | servidor hecho; lo llama Ventas al cobrar (pedido a Ventas) |
| COMBO-F09 | Repartir el IVA de un menú | servidor hecho; lo aplica Ventas en sus líneas (pedido a Ventas) |
| COMBO-F10 | Bajar el stock de cada plato al cobrar | contrato probado con Inventario real; el aviso lo manda Ventas (pedido a Ventas) |
| COMBO-F11 | Mandar el menú a cocina | contrato hecho; la comanda la arma Ventas y la pinta Cocina (pedido a Ventas y a Cocina) |
| COMBO-F12 | Marcar una elección como agotada | hecho |
| COMBO-F13 | Cuando un producto deja el catálogo | parcial — quitar solas de todos los menús las elecciones de un producto eliminado llega con el reparto de avisos entre apps (fase 2); hasta entonces se quedan marcadas, no se ofrecen ni se cobran y se quitan a mano |

### COMBO-F01 Consultar y buscar los menús
Estado: hecho
Actor: propietario, administrador, responsable, empleado, asistente
Pantalla: Menús
Pasos:
1. Abre **Menús**.
2. Lee la tabla: nombre, precio cerrado, cómo se vende, si está a la venta y orden.
3. Para encontrar uno, escribe en «Buscar un menú…», ordena por una columna o filtra por nombre, por
   cómo se vende o por «A la venta».
4. Toca una fila para abrir su constructor.
Entra: los menús del negocio (permiso de consulta).
Sale: nada; solo lee.
Si falla: el error de carga sale en la tabla con «Reintentar»; sin menús, «Aún no hay menús. Crea el
primero con el botón +.».
Implicados: ninguno

### COMBO-F02 Crear un menú a precio cerrado
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Menús
Pasos:
1. En Menús, pulsa **+**.
2. Escribe el Nombre; si la comanda debe decir otra cosa, el «Nombre de cocina».
3. Escribe el «Precio cerrado»: lo que paga el cliente por el menú entero. Vacío es 0.
4. Elige «¿Cómo se vende?»: «Se consume en el local» factura UNA línea al tipo del menú, la bebida
   incluida (el menú del día); «Se vende como producto / para llevar»: si todas las elecciones tributan
   igual, UNA línea a ese tipo; si no, UNA línea por plato, cada una a su tipo, con el precio repartido
   (COMBO-F09).
5. Si es «en el local», elige el «Tipo de IVA» del menú entero (en un restaurante, «Restaurante —
   comida», al 10 %).
6. Deja marcada «A la venta» si ya se puede vender y pulsa «Guardar».
7. El formulario se cierra y el menú aparece en la lista. Todavía no sale en el TPV: le faltan los
   platos y las elecciones (COMBO-F05, F06).
Entra: nombre, nombre de cocina, precio, forma de venta, tipo de IVA, orden y «A la venta»; las
categorías de IVA las lee de Impuestos.
Sale: el menú (avisa: menú nuevo).
Si falla: junto al campo: «El menú necesita un nombre.», «Un menú que se consume en el local
necesita su propio tipo de IVA: sin él no se puede facturar.», «El precio de un menú no puede ser
negativo. Para abaratar una opción, ponle un suplemento negativo.», «Esto no es un importe. Escribe
una cifra, por ejemplo 12,50.» y el de las dos lecturas posibles de un importe («1.250»), que cita lo
escrito. Un tipo de IVA que no existe en Impuestos: «Ese tipo de IVA no existe en Impuestos.». Sin
permiso de gestión no hay botón +.
Implicados: TAX-F01

### COMBO-F03 Cambiar los datos de un menú, ponerlo o quitarlo de la venta
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Menús
Pasos:
1. En la fila del menú, pulsa «Editar datos».
2. Cambia lo que haga falta: nombre, precio, forma de venta, tipo de IVA, orden o «A la venta».
3. Pulsa «Guardar». La lista muestra el cambio al momento.
4. Un menú con «A la venta» desmarcada sigue en la lista, pero el TPV deja de ofrecerlo.
Entra: los mismos campos que el alta; solo cambia lo que se envía (por el asistente o la API, lo que no
se nombra se queda como estaba).
Sale: el menú cambiado (avisa: menú cambiado). Lo ya cobrado no cambia: cada línea de venta lleva su
copia del menú. En una cuenta abierta, Ventas conserva el importe pedido; la forma de venta, el tipo de
IVA y si el menú sigue a la venta se leen al cobrar (COMBO-F08).
Si falla: los mismos avisos que el alta. Pasar a «en el local» sin tipo de IVA se rechaza.
Implicados: SALE-F12

### COMBO-F04 Retirar un menú
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Menús
Pasos:
1. En la fila del menú, pulsa «Retirar».
2. Confirma en «¿Retirar este menú?» («{nombre}» deja de estar a la venta, junto con sus platos y sus
   elecciones. Los tiques ya emitidos se siguen leyendo.).
3. El menú desaparece de la lista, con sus platos y sus elecciones, y el TPV deja de ofrecerlo. Quien
   lo tenga abierto en su constructor ve «Este menú ya no existe».
Entra: el menú elegido (por id o por nombre).
Sale: el menú, sus platos y sus elecciones borrados en una sola operación (avisa: menú retirado, con
su nombre). Los tiques emitidos llevan su copia y se siguen leyendo.
Si falla: «No se ha podido retirar el menú.» en el diálogo; un menú que ya no existe, «Ese menú no
existe en este negocio.». Una cuenta abierta que lo llevaba se rechaza al cobrar (COMBO-F08).
Implicados: SALE-F12

### COMBO-F05 Montar los platos de un menú
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Constructor del menú
Pasos:
1. Abre el menú (toca su fila) y baja a «Añadir un plato».
2. Escribe el «Nombre del plato» (Primeros, Segundos, Postre, Bebida), las «Elecciones mínimas» (1 o
   más hace el plato obligatorio; 0, opcional) y las «Elecciones máximas» (0 es sin límite). De partida
   salen 1 y 1.
3. Marca «Se puede elegir la misma opción más de una vez» solo si hace falta (dos cafés en el mismo
   menú).
4. Pulsa «Guardar»: el plato entra el último, que es el último que se pregunta.
5. Para cambiar el orden, arrastra el asa o usa «Subir» y «Bajar»: el orden nuevo se guarda entero de
   una vez. «Editar datos» abre el plato en el formulario y conserva su sitio. «Retirar» lo quita con
   sus elecciones, tras confirmarlo.
Entra: nombre, mínimo, máximo y repetición.
Sale: el plato (avisa: plato nuevo, cambiado, reordenado o retirado).
Si falla: junto al campo: «El plato necesita un nombre.», «El máximo ({max}) queda por debajo del
mínimo ({min}): nadie podría satisfacer nunca este plato.» y «Ese menú ya tiene un plato «{nombre}».».
Un mínimo o un máximo por encima de 50 se rechaza, igual que más de 20 platos en un menú («Un menú
admite como mucho 20 platos.»). Si el servidor rechaza, el formulario lo dice y no pierde lo escrito.
Implicados: ninguno

### COMBO-F06 Elegir los productos de cada plato y su suplemento
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Constructor del menú
Pasos:
1. En la tarjeta del plato, escribe en «Busca un producto…» y elige el producto del catálogo de
   Inventario (busca por nombre y por SKU).
2. Escribe el «Suplemento» si sustituir cuesta más (o menos, con signo negativo) que el precio
   cerrado; vacío es sin suplemento.
3. Pulsa «Añadir elección»: entra la última. Para varios de golpe, «Añadir varios»: marca las casillas
   y pulsa «Añadir N seleccionados» (todos entran sin suplemento y en el orden en que se marcaron).
4. Para cambiar el producto o el suplemento de una elección, pulsa su lápiz: el formulario dice
   «Editando «{producto}». Conserva su posición en el plato.». Con el asa, subir o bajar se reordena;
   la papelera la quita, tras confirmarlo.
Entra: los productos de Inventario (los activos, que se venden por unidades).
Sale: la elección (avisa: elección nueva, cambiada, reordenada o quitada). El suplemento se suma al
precio cerrado, nunca al precio del producto.
Si falla: «Elige antes un producto del catálogo.», «Este plato ya ofrece ese producto. Para que se
pueda elegir dos veces, activa «se puede elegir la misma opción más de una vez».», ««{producto}» está
desactivado en Inventario: actívalo antes de ponerlo en un menú.», «Solo un producto que se vende por
unidades puede ser una elección de menú.», «Un plato admite como mucho 40 elecciones.» y los avisos de
importe. «Añadir varios» sin nada marcado: «Marca al menos un producto.». Si el catálogo no carga,
el buscador lo dice con «Reintentar».
Implicados: INVENTORY-F27

### COMBO-F07 Elegir un menú al vender
Estado: servidor hecho; la hoja del TPV es de Ventas (pedido a Ventas, SALE-F12)
Actor: empleado, responsable
Pantalla: Ventas: Vender
Pasos:
1. En el TPV, en «Todos», los menús salen primero con la etiqueta «Menú». Toca uno: se abre una hoja
   con todos sus platos a la vez.
2. Cada plato muestra su contador (0/1) y sus elecciones disponibles, con el suplemento con su signo
   si no es cero. En un plato de una sola elección, tocar otra la cambia; en uno de varias, tocar de
   más no añade.
3. Mientras falte algo, el botón dice el motivo («Elige {n} en {plato}»); cuando cada plato
   obligatorio está completo, el botón suma el total en vivo. Pulsa añadir.
Entra: los menús a la venta que se pueden completar, con sus platos y sus elecciones disponibles
(`combo.combo.for_sale`).
Sale: la línea del menú con lo elegido. El precio que ve el TPV es una vista previa: el que vale lo
calcula este módulo al cobrar (COMBO-F08).
Si falla: un menú no sale en el TPV si no está a la venta, si no tiene ningún plato con elecciones o
si un plato obligatorio no tiene bastantes elecciones disponibles (agotadas, desactivadas o
eliminadas en Inventario). Un plato opcional sin elecciones disponibles no sale en la hoja.
Implicados: SALE-F12, MODIFIER-F06

### COMBO-F08 Cobrar el menú: precio cerrado y suplementos
Estado: servidor hecho; lo llama Ventas al pedir y al cobrar (pedido a Ventas, SALE-F12)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Ventas manda a Menús el menú, las elecciones de la línea y cómo se vende esa línea (el canal de su
   pedido: en el local, para llevar o a domicilio; sin canal vale el ajuste del menú)
   (`combo.combo.resolve`).
2. Menús comprueba cada plato (mínimo, máximo, repetición), que cada elección siga en el menú y siga
   siendo una ración (se vende por unidades) y, en un pedido nuevo, que esté disponible, con su producto
   activo, y que el menú siga a la venta.
3. El importe es el precio cerrado más un suplemento por cada elección (también la repetida). En una
   cuenta abierta, Ventas manda el importe que tenía al pedirlo: Menús reparte ese y **no vuelve a
   pedir disponibilidad** (el último flan servido y marcado «Agotado» no impide cobrar la mesa), solo
   los platos, las raciones y los datos fiscales.
4. Devuelve la línea del menú: nombre, nombre de cocina, importe, forma de venta y sus componentes, en
   el orden de los platos y de la elección.
Entra: el menú (por id o por nombre) y las elecciones (por id, o por el nombre o el SKU del producto,
con el plato si hace falta), con cuántas de cada una.
Sale: la línea del menú con sus componentes y su reparto fiscal (COMBO-F09). No guarda nada.
Si falla: la venta no se guarda y Menús dice por qué: «Ese menú no existe en este negocio.» (`combo.combo_missing`: un
404 es también «la app no está activa»), «Ese menú ya no está a la venta.», «Elige algo del menú antes de añadirlo.», «Al menú le falta elegir en «{plato}»: elige
{min}.», «El plato «{plato}» admite como mucho {max}.», «El plato «{plato}» no admite elegir dos veces
lo mismo.», ««{producto}» no es una elección de este menú.», ««{producto}» está agotado.», ««{producto}»
ya no se puede vender: está desactivado o eliminado en Inventario.», ««{producto}» ya no se vende por
unidades en Inventario, así que no se puede cobrar como elección de menú.» y «El importe del menú no puede
quedar en negativo.».
Implicados: SALE-F12

### COMBO-F09 Repartir el IVA de un menú
Estado: servidor hecho; lo aplica Ventas en sus líneas (pedido a Ventas, SALE-F12)
Actor: sistema
Pantalla: ninguna
Pasos:
1. «En el local»: el menú sale en UNA línea, con el importe y el tipo de IVA del menú, aunque una
   bebida de dentro tenga otro tipo en el catálogo (art. 91.Uno.2.2º LIVA: la bebida, también la
   alcohólica, es accesoria del servicio de restauración).
2. «Para llevar» (el ajuste del menú, o un pedido para llevar o a domicilio aunque el menú sea «en el
   local»): cada plato va a la categoría de su producto, salvo lo que en el local es servicio y para
   llevar es venta de bienes: `restaurant.alcohol` (la cerveza o el vino del restaurante, 10 % en la
   mesa) va a `retail.alcohol` (21 %, art. 90 LIVA). Es un mapa explícito con solo ese par de fábrica de
   Impuestos; una categoría propia del negocio va como está. Si todos van a la misma categoría: UNA línea
   con el importe y esa categoría.
3. «Para llevar» con categorías distintas: UNA línea por plato elegido, cada una con su categoría y el
   importe repartido en proporción al precio de catálogo de cada producto (art. 79.Dos
   LIVA), con el céntimo sobrante al resto mayor (a igualdad, al plato elegido antes); la suma es
   exactamente el importe. Ejemplo: 6,00 € sobre un bocadillo de 4,50 € (10 %) y una cerveza de 2,00 €
   (21 %): 4,15 € + 1,85 €.
4. No hay línea «padre» con dinero.
Entra: forma de venta, tipo de IVA del menú y elecciones; precio de catálogo y categoría fiscal de cada
producto, de Inventario.
Sale: el reparto, con la categoría fiscal de cada línea; Ventas calcula base y cuota con Impuestos.
Un menú «para llevar» sin tipo de IVA propio que se toma en el local va por plato a las categorías de
sus productos (las del local).
Si falla: «En el local» sin tipo de IVA no se puede guardar (COMBO-F02). Para llevar, un plato cuya
categoría no tiene equivalente activo en Impuestos: ««{producto}» se factura en {categoría}, que no
tiene equivalente para llevar en Impuestos, así que este menú no se puede vender para llevar.»
(`combo.tax_category_takeaway`); en un menú «para llevar» ese plato no se ofrece y el constructor lo
marca «Sin tipo de IVA para llevar». «Para llevar» con un producto sin categoría fiscal: ««{producto}» no tiene categoría fiscal en Inventario, así que este menú no se
puede cobrar.» (y no se ofrece). Partido con todos los productos a 0 € en el catálogo: «Los productos de
este menú no tienen precio de catálogo, así que no se puede repartir su IVA.»; si todas las elecciones
ofrecidas de un menú «para llevar» valen 0 € y van a categorías distintas, el menú no sale en el TPV.
Implicados: SALE-F12, TAX-F05

### COMBO-F10 Bajar el stock de cada plato al cobrar
Estado: contrato probado con Inventario real; el aviso de venta lo manda Ventas (pedido a Ventas)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al cobrar, Ventas pone en el aviso de venta cobrada, en la línea del menú, cada producto elegido con
   su cantidad (la de la línea ya multiplicada: tres menús, tres raciones de cada plato).
2. Inventario baja el stock de cada producto elegido, nunca el del menú, y solo de los que controlan
   existencias; un producto de tipo servicio no mueve nada.
3. Si se anula la venta, Inventario devuelve lo que salió de su libro de movimientos.
4. Si se devuelve, Inventario repone lo que le lleguen como líneas devueltas (INVENTORY-F24): Ventas
   manda los componentes del menú × los menús devueltos, una línea por producto.
Entra: los componentes que da COMBO-F08 (producto, cantidad, si es servicio).
Sale: movimientos de stock por producto (Inventario); nada de este módulo.
Si falla: como INVENTORY-F21. Probado con Inventario real (`restore_refund` repone los platos que le
llegan como líneas).
Implicados: INVENTORY-F22, INVENTORY-F23, SALE-F12

### COMBO-F11 Mandar el menú a cocina
Estado: contrato hecho; la comanda la arma Ventas y la pinta Cocina (pedido a Ventas y a Cocina)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El camarero añade un menú a la cuenta de la mesa y manda la cuenta a cocina.
2. Ventas manda la línea del menú con su nombre, su nombre de cocina y los platos elegidos, cada uno
   con su producto, su categoría y su cantidad (lo que dio COMBO-F08 al pedir).
3. Cocina pone cada plato en la estación de su producto (o de su categoría), bajo el nombre de cocina
   del menú (KITCHEN-F06).
Entra: la línea del menú de la cuenta abierta.
Sale: nada de este módulo.
Si falla: lo decide Ventas (pedido: no mandar a cocina un menú con un plato obligatorio sin elegir).
Implicados: KITCHEN-F06, SALE-F20

### COMBO-F12 Marcar una elección como agotada
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Constructor del menú
Pasos:
1. En la fila de la elección, pulsa «Agotado» (o di «hoy no hay flan en el menú del día»).
2. La fila se marca «Agotado» y el TPV deja de ofrecerla; el resto del menú se sigue vendiendo.
3. Cuando vuelva a haber, pulsa «Disponible».
Entra: la elección.
Sale: la elección cambiada (avisa: elección cambiada).
Si falla: si al agotarla un plato obligatorio se queda sin bastantes elecciones, el menú deja de salir
en el TPV y el aviso del constructor lo dice.
Implicados: COMBO-F07

### COMBO-F13 Cuando un producto deja el catálogo
<!-- origen: old:combos/WORKFLOW.md#combos-f06 old:combos/WORKFLOW.md#combos-f09 -->
Estado: parcial — quitar solas de todos los menús las elecciones de un producto eliminado llega con el reparto de avisos entre apps (fase 2); hasta entonces se quedan marcadas, no se ofrecen ni se cobran y se quitan a mano
Actor: sistema, propietario, administrador, responsable, asistente
Pantalla: Constructor del menú
Pasos:
1. Alguien desactiva un producto en Inventario: sus elecciones siguen en los menús, marcadas
   «Desactivado en Inventario», y el TPV no las ofrece hasta que se reactive.
2. Alguien elimina un producto en Inventario: sus elecciones siguen en los menús, marcadas «Ya no está
   en el catálogo», y el TPV no las ofrece ni se pueden cobrar (es definitivo: un producto eliminado no
   vuelve).
3. En el constructor del menú, quita cada una con su papelera, como cualquier otra elección (COMBO-F06).
Entra: el producto desactivado o eliminado en Inventario.
Sale: las elecciones marcadas y, al quitarlas, fuera del menú (avisa: elección quitada).
Si falla: si un plato obligatorio se queda sin bastantes elecciones que ofrecer, el menú deja de salir
en el TPV y el aviso del constructor dice por qué.
Implicados: INVENTORY-F04, COMBO-F06

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y permisos. Un menú se nombra por su id o por su nombre; un plato
por su id o por su nombre dentro del menú; un producto por su id, su SKU o su nombre. Si un nombre vale
para varios, se dice cuáles y se pide que elija (`combo.combo_ambiguous`, `combo.group_ambiguous`,
`combo.option_ambiguous`, `inventory.product_ambiguous`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los menús, con búsqueda, filtros y orden, en páginas de hasta 100 (en vivo) | ver | F01 | `combo.combo.list` |
| Un menú con sus platos y sus elecciones, si sale en el TPV y por qué no (en vivo) | ver | F05, F06, F12 | `combo.combo.get` |
| El catálogo de menús del TPV: los que se pueden vender, con sus platos y sus elecciones disponibles (en vivo) | ver | F07 | `combo.combo.for_sale` |
| La línea de un menú con lo elegido: importe, componentes y reparto fiscal | ver | F08, F09, F10, F11 | `combo.combo.resolve` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea un menú | gestionar | F02 | `combo.combo.create` |
| Cambia un menú (solo lo enviado) | gestionar | F03 | `combo.combo.update` |
| Retira un menú con sus platos y elecciones | gestionar | F04 | `combo.combo.delete` |
| Añade un plato (al final) | gestionar | F05 | `combo.group.create` |
| Cambia un plato (solo lo enviado) | gestionar | F05 | `combo.group.update` |
| Retira un plato con sus elecciones | gestionar | F05 | `combo.group.delete` |
| Ordena los platos de un menú, todos a la vez | gestionar | F05 | `combo.group.reorder` |
| Añade una elección (al final) | gestionar | F06 | `combo.option.create` |
| Añade varias elecciones de golpe | gestionar | F06 | `combo.option.bulk_create` |
| Cambia una elección: producto, suplemento o disponible (solo lo enviado) | gestionar | F06, F12 | `combo.option.update` |
| Quita una elección | gestionar | F06 | `combo.option.delete` |
| Ordena las elecciones de un plato, todas a la vez | gestionar | F06 | `combo.option.reorder` |
| Quita las elecciones de un producto eliminado | solo la plataforma | F13 | `combo.option.drop_product` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Menú nuevo | Crear un menú | `id`, `name` | `combo.combo.created` |
| Menú cambiado | Guardar con algún cambio | `id`, `name` | `combo.combo.updated` |
| Menú retirado | Retirar | `id`, `name` | `combo.combo.deleted` |
| Plato nuevo, cambiado o retirado | Crear, guardar con cambios o retirar un plato | `id`, `combo_id` | `combo.group.created`, `.updated`, `.deleted` |
| Platos reordenados | Cambiar el orden | `combo_id` | `combo.group.reordered` |
| Elección nueva, cambiada o quitada | Añadir (una o varias), guardar con cambios, agotar o quitar; quitar por producto eliminado lleva `reason: "product_deleted"` | `id`, `group_id`, `combo_id`, `product_id` | `combo.option.created`, `.updated`, `.deleted` |
| Elecciones reordenadas | Cambiar el orden | `group_id`, `combo_id` | `combo.option.reordered` |

### A qué reacciona

| Aviso de | Qué hace Menús | Flujos | Servicio que escucha |
|---|---|---|---|
| Inventario: producto eliminado | Quita sus elecciones de todos los menús (cuando llegue el reparto de avisos entre apps, fase 2; hasta entonces se quitan a mano) | F13 | `inventory.product.deleted` → `combo.option.drop_product` |

Además, los cambios de producto de Inventario (`inventory.product.updated`, `.deleted`) vuelven a
leer en vivo el constructor y el catálogo del TPV: el nombre, el precio y si está activo son de
Inventario.

### Lo que necesita de otras apps

| De | Para qué | Flujos | Servicio |
|---|---|---|---|
| Inventario (`requires`) | Los productos que pueden ser elección, con su nombre, SKU, precio, categoría fiscal y si están activos (lectura directa: es una app requerida) | F06, F07, F08, F09 | modelo `inventory.Product`; el buscador de la pantalla usa `inventory.product.list` |
| Impuestos (`requires`) | Las categorías fiscales del selector y la del menú «en el local» | F02, F03, F09 | modelo `tax.TaxCategory`; el selector usa `tax.category.list` |

### Contrato con Ventas

Ventas no requiere Menús: lo llama por el nombre de la operación (`call_app`), con la sesión de quien
vende, y si Menús no está activo el TPV no ofrece menús.

- **Catálogo del TPV**: `useLive('combo.combo.for_sale', {limit: 50})`. Cada fila: `id`, `name`,
  `kitchen_name`, `price` (céntimos), `supply_kind`, `sort_order` y `groups[]` (`id`, `name`,
  `min_choices`, `max_choices` —0 sin límite—, `allow_repeat`, `options[]` con `id`, `product_id`,
  `product_name`, `sku`, `price_delta`). Solo menús a la venta que se pueden completar y elecciones
  disponibles.
- **Al pedir y al cobrar**: `combo.combo.resolve` con `{id | combo, choices: [{option_id |
  product (+ group), quantity}], amount?, channel?}`; `channel` es el de su pedido (`dine_in`,
  `takeaway`, `delivery`) y decide «en el local» o «para llevar» (sin él, el ajuste del menú). Devuelve `combo_id`, `name`, `kitchen_name`,
  `supply_kind`, `price`, `supplements`, `amount`, `split` y `tax_category_key` (la de la línea única,
  o `null` si se parte) y `components[]` en orden: `option_id`, `group_id`, `group_name`,
  `product_id`, `product_name`, `sku`, `category_id`, `is_service`, `quantity` (por menú),
  `price_delta`, `catalog_price`, `tax_category_key` y `amount` (su parte, solo si `split`).
- **Qué hace Ventas con eso** (pedido a Ventas, SALE-F12): congelar la respuesta en la línea al pedir
  (en una cuenta abierta, guardar `amount`); al cobrar, volver a llamar con ese `amount` y materializar
  UNA línea (`split = false`, a `tax_category_key`) o UNA línea por componente (`split = true`, cada una
  a su `tax_category_key` y por su `amount`), hermanas y sin línea padre con dinero; mandar siempre el
  `channel` del pedido; multiplicar las cantidades por la de la línea; propagar los 409 de Menús tal
  cual; no mandar a cocina un menú con un plato obligatorio sin elegir; en una devolución, mandar los
  componentes × la cantidad devuelta como líneas de `sale.sale.refunded`.

### Contrato con Inventario

- En el aviso `sale.sale.completed`, la línea del menú lleva `components[]` con `product_id`,
  `quantity` (la de la línea ya multiplicada) e `is_service` de cada componente de COMBO-F08, y no
  mueve stock por sí misma (INVENTORY-F22; ya implementado en `inventory.stock.apply_sale`). Probado con
  Inventario real.
- La devolución: INVENTORY-F24 ya repone las líneas que le llegan en `sale.sale.refunded`
  (`inventory.stock.restore_refund`, `lines` de producto y cantidad). Ventas manda los componentes del
  menú × los menús devueltos como esas líneas (pedido a Ventas); probado con Inventario real.

### Contrato con Cocina

- Cocina no lee Menús. Recibe de Ventas, en `sale.order.fired`, la línea del menú con `name`,
  `kitchen_name` y sus componentes (`product_id`, `product_name`, `category_id`, `quantity`), y pone
  cada plato en su estación bajo el nombre de cocina del menú (KITCHEN-F06, pedido a Ventas por
  Cocina).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver los menús, el catálogo del TPV y calcular una línea de menú | sí | sí | sí | sí | `combo.view` |
| Crear, cambiar, ordenar y retirar menús, platos y elecciones | sí | sí | sí | no | `combo.manage` |

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `queries.py`,
  `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `test_integration_inventory.py`,
  `test_integration_tax.py` y `test_concurrency.py`.
- `requires = ["inventory", "tax"]`: `ChoiceOption.product` es FK a `inventory.Product` (`CASCADE`;
  Inventario borra lógicamente, así que la quitará la reacción de F13 cuando el relay del outbox la
  entregue, fase 2; hasta entonces, la papelera del constructor) y
  `Combo.tax_category` FK a `tax.TaxCategory` (`PROTECT`; Impuestos nunca borra una categoría). La
  migración depende de `inventory 0001` y `tax 0005`.
- Modelos: `Combo` (precio en céntimos ≥ 0; `supply_kind` `service` | `goods`; restricción: `service`
  ⇒ categoría fiscal), `ChoiceGroup` (`min_choices`, `max_choices` con 0 = sin límite y restricción
  `max = 0 o max ≥ min`, ambos ≤ 50; nombre único por menú, sin distinguir mayúsculas) y `ChoiceOption`
  (`price_delta` con signo, `is_available`; producto único por plato). UUIDv7, sin `hub_id`. Borrado
  físico en cascada: las ventas llevan su copia.
- **Orden**: un plato o una elección nuevos entran los últimos (`max + 1`); `reorder` recibe la lista
  entera de ids y la guarda en una transacción (rechaza una lista que no sea exactamente la del menú o
  el plato: `combo.reorder_mismatch`).
- **Concurrencia**: crear o cambiar un plato bloquea su menú; crear, cambiar o reordenar una elección
  bloquea su plato; retirar un menú bloquea el menú y sus platos (`select_for_update`). Así dos escrituras
  a la vez del mismo nombre o del mismo producto dan una y un 409 (`combo.group_exists`,
  `combo.option_exists`), los topes (20 platos, 40 elecciones) no se rebasan y retirar un menú mientras se
  le añade una elección no deja nada colgado. Las restricciones únicas de la base son la última red: un
  `IntegrityError` se convierte en su 409 dentro de un savepoint, nunca un 500. Crear o cambiar una
  elección retiene su producto, y crear o cambiar un menú su categoría fiscal, hasta el COMMIT (`held` de
  Inventario, `FOR KEY SHARE`): un borrado a la vez (el «Eliminar» de Inventario o el del admin del Hub)
  espera a la escritura, y uno ya en curso se lee terminado, como uno borrado antes (422 `invalid_field` en
  el campo que lo nombra), nunca un 500 ni un menú que ofrece un producto borrado. Probado con hilos.
- **Sale en el TPV** (`for_sale`, y el aviso del constructor): a la venta ∧ al menos una elección
  ofrecida ∧ cada plato obligatorio con elecciones ofrecidas suficientes (`min`, o una si se puede
  repetir) ∧ (partido) algún precio de catálogo que pesar. Ofrecida = disponible ∧ producto activo,
  no eliminado y por unidades ∧ (menú «para llevar») con categoría para llevar.
- **Reparto** (`queries.split_amount`): proporcional al `precio de catálogo × cantidad`, resto mayor,
  empate al primero; partir solo si `goods` y hay más de una categoría fiscal. Sin redondeos de más:
  enteros en céntimos.
- Asistente: toda operación declara `ai={"description"…}` (`risk` en las acciones; `high` al retirar
  un menú, un plato o una elección, y al cambiar un menú, porque puede cambiar cómo se factura: el riesgo
  es por operación, no por campo) y todo campo de entrada lleva `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre los tres modelos (ronda 12, PLAN §17); una
  escritura cruda del admin no deja aviso.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo.
- En el navegador: `tests/e2e/combo-menus.spec.ts` (oculto, con Inventario e Impuestos de verdad), que
  borra lo suyo (`E2E Combo …`, `E2E-CMB-…`) antes y después.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/combo/menus` (lista) y `/combo/menus/:id` (constructor). Una sola entrada de
  menú, sin pestañas, como el producto actual.
- Lista en vivo con `useLiveList` + `useServerTable` (orden `sort` + `dir`), filtros de columna de
  `DataTable`; el constructor sigue `combo.combo.get` en vivo; escrituras con `useCommand`.
- Formularios: `FormModal` para el menú; el plato y la elección se editan dentro del constructor, como
  el producto actual. Confirmaciones con `ConfirmDialog`. Buscador de producto con `Combo`
  (`inventory.product.list`, activos), de categoría fiscal con `Combo` (`tax.category.list`).
- Reordenar: `ion-reorder-group` (asa) y los botones subir/bajar, que acaban en la misma operación
  (`reorder`). WCAG 2.5.7: todo lo que se arrastra se puede hacer sin arrastrar.
- Los importes se leen con `lib/money.ts` (coma o punto, el «1.250» ambiguo se pregunta, el suplemento
  admite signo).
- Iconos registrados en la shell; los del producto actual (`restaurant-outline`,
  `reorder-three-outline`, `arrow-up-outline`) esperan en `UI-REQUESTS.md`.

## Lo que NO hace, a propósito

- **No cobra, no factura ni calcula cuotas**: lo hace Ventas con lo que lee de aquí.
- **No tiene stock propio**: el menú no se cuenta; se cuentan sus productos.
- **No tiene horario** (menú solo a mediodía): se pone y se quita de la venta a mano.
- **No tiene elección por defecto** ni modificadores dentro de un plato (eso es Suplementos, desde el
  TPV).
- **No admite servicios de la app Servicios** como elección: los packs de peluquería son los bonos y
  paquetes de Servicios (SERVICE-F12).
- **No manda nada a cocina** por sí mismo.

## Cambios frente al producto actual

- **Las elecciones son productos de Inventario por clave ajena** (`requires = ["inventory", "tax"]`),
  no una referencia opaca a producto o servicio: el nombre, el SKU y el precio se leen siempre, sin el
  «Artículo {ref} (ya no está en el catálogo)» falso del producto actual cuando el artículo no estaba
  en la página del buscador. Los servicios de la app Servicios dejan de poder ser elección (ver «Lo que
  NO hace»); un producto de tipo servicio de Inventario sí.
- **Solo productos activos y que se venden por unidades** al añadir (antes, cualquier id).
- **Agotado** (COMBO-F12) es nuevo: antes había que quitar la elección y volver a ponerla.
- **Producto eliminado** (COMBO-F13): la elección se marca «Ya no está en el catálogo» y el TPV no la
  ofrece ni la cobra; antes quedaba colgando. Que se quite sola de todos los menús llega con el relay
  del outbox (fase 2): la reacción ya está escrita y probada entregando el aviso real.
- **Un plato obligatorio sin elecciones bloquea el menú en el TPV**: antes no llegaba a Ventas y el
  menú se vendía sin él. El constructor dice por qué un menú no sale en el TPV.
- **Cambiar solo lo enviado**: editar un plato ya no lo manda al primer puesto ni pone mínimo y máximo
  en 1; cambiar un menú por el asistente ya no lo vuelve a poner a la venta; cambiar una elección ya no
  pone el suplemento a 0.
- **Ordenar es una sola operación** con la lista entera (antes, plato a plato y sin transacción común).
- **Confirmar antes de retirar** un menú, un plato o una elección (antes, al instante).
- **Nombre de plato único en su menú** («Ese menú ya tiene un plato «Primeros».»): con dos «Primeros»
  ni el TPV ni el asistente sabrían cuál es.
- **Topes**: 20 platos por menú y 40 elecciones por plato, para que el menú quepa en una lectura en
  vivo (256 KB).
- **El reparto fiscal lo calcula Menús** (`combo.combo.resolve`), no Ventas: Menús ya lee el precio y
  la categoría de cada producto. Un producto sin categoría fiscal se nombra en el aviso (antes mandaba
  a arreglarlo en Combos).
- **La línea del menú la calcula una sola operación** (`resolve`) en vez de leer `combos.options.all`
  entero: lo que antes era `combos.combos.all` + `combos.options.all` (sin paginar) es
  `combo.combo.for_sale` (paginado, hasta 50 menús por página) + `combo.combo.resolve`.
  `combos.groups.list` y `combos.options.list` desaparecen: `combo.combo.get` da el menú con sus platos
  y elecciones en una sola lectura en vivo.
- **Nombres**: `combo.*` en vez de `combos.*`; `combo.group.*` y `combo.option.*` en vez de
  `combos.groups.*` y `combos.options.*`; avisos `combo.group.*` y `combo.option.*` en vez de
  `combos.choice_group.*` y `combos.choice_option.*`; permisos `combo.view` y `combo.manage` en vez de
  `combos.view_combo` y `combos.manage_combo`.
- **Añadir varios** es una sola operación (`bulk_create`, todo o nada); antes, una por elección.
- Precios en céntimos, como el resto de la plataforma.

## Contradicciones señaladas

- El encargo dice «en hostelería el menú se factura al 10 % salvo bebidas alcohólicas». Eso vale
  **para llevar** (`retail.alcohol`, 21 %, art. 90 LIVA). **En el local** la bebida alcohólica del menú
  también va al 10 %: es accesoria del servicio de restauración (art. 91.Uno.2.2º LIVA), como dice la
  categoría `restaurant.alcohol` de Impuestos. Por eso «en el local» es una línea y «para llevar» se
  parte por categoría.
- SALE-F12 dice «al cobrar el menú se reparte en tantas líneas como tipos de IVA tenga». Solo es así
  «para llevar»; «en el local» es una línea (COMBO-F09). Pedido a Ventas que lo corrija al portar
  SALE-F12.
- «Para llevar» se decidía en dos sitios: por menú en Menús y por `channel` del pedido en Ventas. Queda
  unificado: manda el `channel` que Ventas pasa a `resolve`; el ajuste del menú es solo el valor por
  defecto.
- Una bebida refrescante con azúcar añadido va al 21 % para llevar y al 10 % en el local, pero Impuestos
  no tiene una categoría de fábrica que lo distinga (`restaurant.drink` va igual en los dos): no se mapea.
  Si hace falta, Impuestos tendrá que crear la pareja y añadirse aquí a `TAKEAWAY_CATEGORY`.
- `useServerTable`, `useLiveList`, `useT` y el lector de importes (`MoneyInput`, con signo) están
  copiados en cada app; ya pedido en `UI-REQUESTS.md` que suban a `@erplora/ui`.
