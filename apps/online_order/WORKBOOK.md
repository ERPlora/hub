# Workbook — Pedidos online (app)
Prefijo: ONLINE_ORDER
Alcance MVP: restaurante (no viene en ninguna plantilla; entra en la tienda cuando el cliente pueda pedir)
Estado de la app: en construcción — hoy, el código de cada mesa, su regeneración, la hoja de QR, la carta que abre el QR de cada mesa y el pedido que el cliente envía desde ella, que queda pendiente; falta que el personal lo acepte o lo rechace

> Manual de usuario y especificación de la app `online_order`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor y
> páginas).

## Para qué sirve y para quién

Pedidos online deja que el cliente sentado a la mesa pida él mismo desde su móvil: escanea el QR de su mesa, ve la
carta y pide, y el pedido llega a la cuenta de la mesa y a cocina. El pago no cambia: se cobra en el TPV como
siempre.

### En detalle

- **Cada mesa tiene su propio QR**, con un código que nadie puede adivinar. El QR se imprime una vez y se deja en la
  mesa; no caduca ni cambia solo.
- **Regenerar el QR** de una mesa le da un código nuevo: el QR impreso deja de valer en ese momento y hay que imprimir
  el nuevo. Sirve cuando alguien se ha llevado una foto del QR y pide desde fuera, o cuando el papel se ha perdido.
- **El cliente pide sin cuenta ni app instalada**: abre la página de su mesa con la cámara del móvil, ve la carta
  (fotos, descripción, alérgenos, suplementos y menús) y manda su pedido.
- **Solo se pide con el negocio abierto**, según el horario de Horarios.
- **Si la mesa ya tiene la cuenta abierta**, el pedido entra en ella y va a cocina. Si no, el primer pedido espera a
  que un empleado lo acepte o lo rechace desde el centro de avisos, salvo que el negocio apague «Aceptar el primer
  pedido de cada mesa».
- La cuenta se cobra en el TPV como cualquier otra.

### Quién la usa y qué hace cada uno

- El **propietario**, el **administrador** y el **responsable** ven el código de cada mesa y lo regeneran.
- El **empleado** no ve los códigos de las mesas.
- El **asistente** (por voz o por texto, con la sesión de quien habla) hace lo mismo: «¿qué mesas tienen ya su código
  QR para pedir?», «regenera el código QR de la mesa 4 de la terraza». Antes de regenerar pide confirmar con su
  tarjeta, que nombra la mesa por su número y su zona, como la nombra el plano de sala.

## Referencia adoptada

**Odoo, Square, Toast, Lightspeed, Qamarero, Last.app, SumUp y GloriaFood** (tabla y enlaces en «Decisiones de
mercado»): un QR fijo por mesa con un identificador imposible de adivinar, pedir solo con el negocio abierto y que un
empleado acepte el primer pedido de una mesa sin cuenta abierta (el «open table» de Qamarero, la aceptación manual de
Lightspeed y Toast). Nadie rota el QR impreso por tiempo ni usa la ubicación del móvil, que pide permiso y falla en
interiores; volver a generar el QR de una mesa es la salida cuando uno ya no se quiere que valga.

## Antes de empezar

1. Pedidos online enciende con ella **Mesas** (y, por Mesas, **Ventas** y **Clientes**) e **Inventario**, y no se
   pueden apagar mientras esté encendida. Con **Suplementos** y **Menús** encendidas, la carta enseña también los
   suplementos de cada plato y los menús.
2. En **Mesas**, da de alta las zonas y las mesas del local: cada mesa tiene su QR.
3. Cada mesa recibe su código la primera vez que se genera su QR; desde entonces el mismo código vale hasta que se
   regenera.
4. En **Inventario**, la carta de la mesa enseña los productos a la venta que tienen encendido «Mostrar en la carta»,
   como la carta de la Página web, con su foto, su descripción, sus alérgenos y su categoría.

## Pantallas

El menú **Pedidos online** tiene una pestaña: **Códigos QR**. Solo la ven quienes pueden ver los QR de las mesas
(el propietario, el administrador y el responsable); los botones para generar y regenerar, solo quienes pueden
regenerarlos. La **Página de la mesa** no está en el menú: es la que abre el QR de cada mesa en el móvil del cliente,
sin cuenta ni sesión.

### Códigos QR
Aquí tienes todas las mesas del local, en el orden del plano de sala, cada una con la dirección que abre su QR y
cuándo se generó. Desde aquí imprimes la hoja con el QR de cada mesa para recortarlo y dejarlo en ella, imprimes el de
una sola mesa y, si un QR ya no debe valer, lo regeneras.

#### Detalle
Menú **Pedidos online → Códigos QR**. Lista: Mesa, Zona («Sin zona» si no tiene), Dirección y Generado («Sin QR
todavía» en una mesa sin código), en vista tabla o tarjetas. Arriba, **Imprimir hoja**: abre el diálogo de impresión
del aparato con una tarjeta por mesa con QR, tres por fila, cada una con «Escanea para pedir», el QR, «Mesa 4» y su
zona, y su borde discontinuo para recortarla; en la app instalada va a su pantalla de imprimir. Por fila, **Imprimir
QR** (solo esa mesa) y **Regenerar QR**, que pide confirmación («¿Regenerar el QR de la mesa 4 (Terraza)?»), o
**Generar QR** en una mesa que aún no tiene. Si hay mesas sin QR, un aviso dice cuántas no salen en la hoja, con
**Generar los QR que faltan**. El QR se dibuja en el propio aparato: la hoja no pide nada a internet.

### Página de la mesa
La que ve el cliente en su móvil al escanear el QR de su mesa: la carta del negocio, con la mesa en la que está
arriba. Desde aquí arma su pedido y lo envía al local.

#### Detalle
Dirección `/p/<negocio>/order/<código>`, sin sesión, en el idioma del móvil (español o inglés). Arriba, el nombre del
negocio y «Mesa 4 · Terraza» (sin zona, solo «Mesa 4»). Debajo, **Menús** primero, con el precio cerrado de cada menú y
sus platos («Primeros · Segundos · Bebida»), y después cada categoría de Inventario en su orden, con sus platos
ordenados por nombre: la foto (si la tiene), el nombre, la descripción, «Alérgenos: Gluten, Leche» y el precio. Los
platos sin categoría van al final, en «Otros platos». Tocar un plato abre su ficha con la foto en grande, lo mismo de la
fila y cada grupo de suplementos con cuántos se eligen («Opcional · hasta 2», «Elige 1») y cada opción con sus
alérgenos y lo que suma («+0,50 €»); tocar un menú abre sus platos, curso a curso, del mismo modo. En la ficha se marca
lo que se quiere de cada grupo (en uno de un solo elegido, marcar otro cambia el elegido; uno lleno deja esperando los
demás; lo que se puede repetir lleva uno menos y uno más con su cuenta), cuántos y una nota para cocina; **Añadir · 8,00 €**
lo pone en el pedido, y espera mientras un grupo no tiene lo que pide. Abajo, **Ver pedido (3) · 25,50 €** abre el
pedido: cada línea con lo que lleva, su nota y su importe, uno menos y uno más (uno menos en una línea de uno la quita) y
el total; **Enviar pedido** lo manda al local. Enviado, la página dice «Pedido enviado: el local lo confirmará
enseguida.». Los importes son los de la carta; el local vuelve a ponerles precio al recibir el pedido.

## Estados de cada pantalla

| Pantalla | Cargando | Vacío | Error |
|---|---|---|---|
| Códigos QR | La lista en carga; **Imprimir hoja**, apagado hasta tener todas las mesas | «Aún no hay mesas», con **Ir a Mesas** a quien puede añadirlas | El de la lista con «Reintentar»; el de generar o regenerar, en un aviso efímero con su motivo; «No se ha podido imprimir la hoja.» |
| Página de la mesa | «Cargando la carta…»; en la ficha de un plato, «Cargando sus suplementos…»; mientras se envía, **Enviar pedido** espera | «Aún no hay platos en la carta», con «Pregunta al personal qué puedes pedir.»; el pedido sin nada, «Tu pedido está vacío» con «Añade platos de la carta.» | «No se ha podido cargar la carta.» con «Reintentar»; en la ficha, «No se han podido cargar sus suplementos.» con «Reintentar»; un QR que ya no vale, «Este QR ya no está activo» con «Pide ayuda al personal.», sin nada del negocio; un pedido rechazado, su motivo en el pedido, que se queda para enviarlo otra vez; sin conexión, «Sin conexión. Compruébala y vuelve a enviar el pedido.» |

«Reconectando…» mientras se recupera la conexión en vivo (lo pintado se queda).

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ONLINE_ORDER-F01 | Generar o regenerar el QR de una mesa | hecho |
| ONLINE_ORDER-F02 | Ver e imprimir la hoja de QR de las mesas | hecho |
| ONLINE_ORDER-F03 | El cliente abre la carta desde el QR de su mesa | hecho |
| ONLINE_ORDER-F04 | El cliente pide desde su mesa | hecho |
| ONLINE_ORDER-F05 | Aceptar o rechazar el primer pedido de una mesa | no hecho |
| ONLINE_ORDER-F06 | El cliente ve si su pedido se ha aceptado | no hecho |
| ONLINE_ORDER-F07 | Configurar los pedidos desde la mesa | no hecho |
| ONLINE_ORDER-F08 | La cuenta dice que el pedido es online | no hecho |

### ONLINE_ORDER-F01 Generar o regenerar el QR de una mesa
Estado: hecho
Actor: propietario, administrador o responsable; el asistente, con la sesión de quien habla
Pantalla: Códigos QR
Pasos:
1. Elige la mesa en **Códigos QR** o, hablando con el asistente, por su número y, si el número se repite, por
   su zona («la 4 de la terraza»).
2. Pulsa **Regenerar QR**: la confirmación nombra la mesa y avisa de que el QR impreso deja de valer en ese momento.
   El asistente enseña lo mismo en su tarjeta.
3. Al confirmar, la mesa recibe un código nuevo: el anterior deja de abrir la página de la mesa en ese momento, y un
   aviso pide imprimir el nuevo (**Imprimir QR**, ONLINE_ORDER-F02).
4. Una mesa que aún no tiene código recibe el primero con **Generar QR**, sin confirmación, porque no hay nada impreso
   que deje de valer; **Generar los QR que faltan** se lo da, una tras otra, a todas las que aún no tienen.
Entra: la mesa, de Mesas.
Sale: el código nuevo de la mesa, la dirección de su página y cuándo se generó; el aviso de que se ha regenerado.
Si falla: no cambia nada en esa mesa, y el aviso dice el motivo. La mesa no existe o está borrada («Esa mesa no existe
en este negocio.»); el número se repite en varias zonas y no se dice cuál (Mesas pide la zona); quien lo pide no puede
cambiar los QR de las mesas («No tienes permiso»; en pantalla no le salen los botones). **Generar los QR que faltan** se
para en la primera mesa que falla: las anteriores ya tienen su QR.
Implicados: TABLE-F02, TABLE-F04

### ONLINE_ORDER-F02 Ver e imprimir la hoja de QR de las mesas
Estado: hecho
Actor: propietario, administrador o responsable; el asistente, con la sesión de quien habla, da la lista
Pantalla: Códigos QR
Pasos:
1. Abre **Pedidos online → Códigos QR**: cada mesa con su número, su zona y, si ya tiene código, la dirección de
   su página y cuándo se generó. Las mesas salen en el orden del plano de sala (la 2 antes que la 10).
2. Pulsa **Imprimir hoja**: el diálogo de impresión del aparato trae un QR por mesa con su número y su zona, para
   recortar y dejar en cada mesa. Las mesas que aún no tienen QR no salen, y la pantalla dice cuántas son.
3. Para una sola mesa (la del QR regenerado), **Imprimir QR** en su fila trae solo la suya.
Entra: las mesas y sus zonas, de Mesas.
Sale: nada; solo se lee y se imprime.
Si falla: sin mesas dadas de alta, «Aún no hay mesas», con **Ir a Mesas**; si el aparato no imprime, «No se ha podido
imprimir la hoja.»; quien no puede ver los QR de las mesas no ve la pestaña («No tienes permiso» por la API).
Implicados: TABLE-F02, WEBSITE-F09

### ONLINE_ORDER-F03 El cliente abre la carta desde el QR de su mesa
Estado: hecho
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. Escanea el QR de su mesa con la cámara del móvil y se abre la página de la mesa, con el nombre del negocio y su
   mesa con la zona («Mesa 4 · Terraza»).
2. Ve la carta completa: los menús y los productos a la venta que se muestran en la carta, por categoría, con su foto,
   su descripción, sus alérgenos y su precio. Lo agotado no sale, ni lo que el negocio no muestra en la carta.
3. Toca un plato y ve sus suplementos, cuántos se eligen de cada grupo y lo que suma cada uno; toca un menú y ve sus
   platos, curso a curso, con sus alérgenos.
Entra: la carta (Inventario y, si están encendidas, Suplementos y Menús) y la mesa (Mesas).
Sale: nada; solo se lee. La página no enseña costes, existencias, impuestos ni nada del personal.
Si falla: un QR que ya no vale (regenerado, o de una mesa borrada) enseña «Este QR ya no está activo» con «Pide ayuda
al personal.», y nada del negocio; sin platos a la venta, «Aún no hay platos en la carta»; si la carta no carga, «No se
ha podido cargar la carta.» con «Reintentar».
Implicados: ONLINE_ORDER-F01, INVENTORY-F36, COMBO-F14

### ONLINE_ORDER-F04 El cliente pide desde su mesa
Estado: hecho
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. En la carta de su mesa, toca un plato o un menú, marca sus suplementos o los platos de cada curso, elige cuántos,
   escribe si quiere una nota para cocina y pulsa **Añadir**.
2. Pulsa **Ver pedido**: revisa cada línea y el total, cambia cuántos o quita alguna.
3. Pulsa **Enviar pedido**: el pedido queda guardado en el local como pendiente, y la página dice «Pedido enviado: el
   local lo confirmará enseguida.». Lo que pasa después lo dice ONLINE_ORDER-F05.
Entra: la carta (Inventario y, si están encendidas, Suplementos y Menús) y la mesa (Mesas).
Sale: el pedido pendiente de la mesa, cada plato con sus suplementos y cada menú con sus platos al precio de la carta, y
su aviso.
Si falla: no se guarda nada y el pedido se queda en el móvil para enviarlo otra vez. Un plato o un menú que ya no está
en la carta (agotado, oculto o quitado mientras pedía: «Esto ya no está en la carta: quítalo de tu pedido y vuelve a
enviarlo.»); un grupo de suplementos o un curso del menú sin lo que pide, o un plato del menú agotado (el motivo de
Suplementos o de Menús); demasiados pedidos seguidos desde la misma mesa o en el negocio («Demasiados pedidos seguidos.
Inténtalo dentro de unos minutos o pide ayuda al personal.»); un QR que ya no vale («Este QR ya no está activo»); sin
conexión («Sin conexión. Compruébala y vuelve a enviar el pedido.»).
Implicados: ONLINE_ORDER-F03, ONLINE_ORDER-F05

### ONLINE_ORDER-F05 Aceptar o rechazar el primer pedido de una mesa
Estado: no hecho — falta el pedido pendiente y su aviso
Actor: empleado, responsable, administrador o propietario
Pantalla: Centro de avisos → Pedidos por aceptar
Pasos:
1. Si la mesa ya tiene la cuenta abierta, el pedido entra en ella sin esperar y se manda a cocina con todo lo que la
   cuenta tenía sin mandar, también lo que el camarero había apuntado en el TPV.
2. Si no la tiene, el centro de avisos enseña «Pedidos por aceptar» con cada pedido pendiente: la mesa, lo que pide y
   cuándo.
3. Pulsa **Aceptar**: se abre la cuenta de la mesa, entran las líneas y se mandan a cocina; o pulsa **Rechazar** y
   el cliente lo ve en su página.
4. Cobrada o anulada la cuenta, el siguiente pedido de esa mesa vuelve a esperar.
Entra: el pedido pendiente.
Sale: la cuenta de la mesa con sus líneas y la comanda, o el pedido rechazado.
Si falla: otro empleado ya lo ha decidido («Este pedido ya está decidido.»).
Implicados: ONLINE_ORDER-F04, TABLE-F10, TABLE-F18, SALE-F20, KITCHEN-F05

### ONLINE_ORDER-F06 El cliente ve si su pedido se ha aceptado
Estado: no hecho — falta el pedido
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. Tras pedir, la página de la mesa enseña su pedido como pendiente, aceptado o rechazado.
2. Se actualiza sola cuando un empleado lo decide.
Entra: el pedido.
Sale: nada; solo se lee.
Si falla: un QR que ya no vale deja de enseñar el pedido.
Implicados: ONLINE_ORDER-F05

### ONLINE_ORDER-F07 Configurar los pedidos desde la mesa
Estado: no hecho — faltan los ajustes y pedir solo con el negocio abierto
Actor: propietario o administrador
Pantalla: Ajustes
Pasos:
1. Enciende o apaga «Aceptar el primer pedido de cada mesa» (encendido de fábrica). Apagado, todo pedido entra solo
   y abre la cuenta de la mesa si no la hay.
2. Pulsa **Guardar**.
3. Fuera del horario de Horarios, la página de la mesa sigue enseñando la carta, pero dice que ahora no se aceptan
   pedidos y no deja enviarlos.
Entra: los ajustes de la app y el horario del negocio (Horarios), que dicen si hoy se aceptan pedidos.
Sale: los ajustes guardados.
Si falla: sin horario del negocio, los ajustes avisan de que no se aceptarán pedidos hasta configurarlo.
Implicados: SCHEDULE-F02

### ONLINE_ORDER-F08 La cuenta dice que el pedido es online
Estado: no hecho — faltan el origen y el canal en la cuenta de Ventas
Actor: camarero o cocina
Pantalla: ninguna propia (se ve en la cuenta de Ventas y en la comanda de Cocina)
Pasos:
1. Una cuenta abierta por un pedido desde la mesa lleva el origen «Pedido online».
2. Su comanda sale en cocina como un pedido para comer en el local.
Entra: el pedido del cliente.
Sale: la cuenta de Ventas con su origen y su canal.
Si falla: no aplica; lo pone el propio pedido.
Implicados: SALE-F19, KITCHEN-F05

## Servicios: lo que entra y lo que sale

Todo se puede pedir por la pantalla, la API y el asistente (por voz o por texto, con la sesión de quien habla), con
las mismas reglas y permisos. Una mesa se nombra por su id o como la dice una persona: su número y, si se repite, su
zona.

### Lo que ofrece: consultas

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las mesas en el orden del plano de sala, cada una con su zona y, si ya lo tiene, su código, la dirección de su página y cuándo se generó, en páginas (hasta 100) | ver los QR de las mesas (+ ver mesas) | F02 | `online_order.qr_code.list` |
| La carta de la mesa de un código: el nombre del negocio, el número y la zona de la mesa, los platos a la venta que se muestran en la carta por categoría y los menús con sus platos | cualquiera con el QR de la mesa, sin sesión | F03 | `online_order.public.menu` |
| Los grupos de suplementos de un plato de esa carta, con sus opciones | cualquiera con el QR de la mesa, sin sesión | F03 | `online_order.public.options` |

Las dos de la carta y el envío del pedido son de la página de la mesa: las llama su móvil por la puerta pública del Hub,
con el código en el cuerpo de la llamada, y no son herramientas del asistente.

### Lo que ofrece: acciones

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Da a una mesa un código nuevo; el anterior deja de valer al momento | regenerar los QR de las mesas (+ ver mesas) | F01 | `online_order.qr_code.regenerate` |
| Guarda como pendiente el pedido de la mesa de un código: cada plato con sus suplementos y cada menú con sus platos, al precio de la carta | cualquiera con el QR de la mesa, sin sesión | F04 | `online_order.public.send` |

Regenerar es de **riesgo alto** para el asistente: el QR impreso deja de valer y no se puede volver atrás, así que su
tarjeta pide la confirmación antes de hacerlo.

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `online_order.qr_code.regenerated` | Se genera o se regenera el código de una mesa | La mesa (`table_id`); nunca el código |
| `online_order.order.sent` | Llega el pedido de una mesa | El pedido (`order_id`), la mesa (`table_id`) y su total (`total`) |

### A qué reacciona

A ningún aviso de otra app.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver los QR de las mesas | sí | sí | sí | no | `online_order.view_qr_code` |
| Regenerar los QR de las mesas | sí | sí | sí | no | `online_order.change_qr_code` |
| Abrir la página de pedidos de una mesa | sí | sí | no | no | `online_order.public` |

Las mesas las lee Mesas con el permiso de quien pregunta: hace falta el de esta app **y** el de ver mesas. El cliente
que abre la página de su mesa no tiene cuenta: la página la sirve la puerta pública con `online_order.public` y nada
más.

## Para quien lo mantiene

- **`requires = ["table", "inventory"]`**: llama a las lecturas de Mesas (`table.table.list` y `table.table.get`) y a
  las de la carta de Inventario (`inventory.product.list_for_sale`, `inventory.category.list` e
  `inventory.product_category.list`) por su nombre. Suplementos (`modifier.group.for_target`) y Menús
  (`combo.combo.for_sale`) se leen solo si están encendidas en el negocio (`base.apps_on.active_apps`): sin ellas, la
  carta va sin suplementos ni menús. Las apps que necesitará el pedido (Ventas, Clientes y Horarios) entran en
  `requires` en el mismo cambio que empiece a llamarlas.
- Modelo (UUIDv7, sin `hub_id`): `TableCode`, una fila por mesa con código: el id de la mesa de Mesas (`table_id`,
  único, sin clave ajena, como `order_id` de Mesas hacia Ventas), el código (`secrets.token_urlsafe(16)`, guardado tal
  cual porque la hoja se vuelve a imprimir, único) y cuándo se generó. Regenerar escribe con un solo `INSERT … ON
  CONFLICT (table_id) DO UPDATE`: dos regeneraciones a la vez de una mesa sin código no chocan, gana la última.
- La dirección de la página de una mesa es `/p/<negocio>/order/<código>` sobre la dirección pública del negocio
  (`base.qr.public_url`, la misma que usa Página web para su QR). La sirve la puerta pública de `base`
  (`base/public_door.py`), porque la app declara `public_pages = {"order": "online_order.public"}`: el HTML es el mismo
  valga o no el código, y sus llamadas van por `POST /p/<negocio>/api/<operación>` con el código en el cuerpo, nunca en
  la dirección. La puerta solo corre las tres operaciones cuyo permiso es `online_order.public`.
- Las dos lecturas de la carta leen las otras apps con `menu_reader(ctx)` (`queries.py`): el contexto del visitante más
  `MENU_READS`, los permisos de ver mesas, productos, categorías, suplementos y menús, y ninguno que escriba. Su salida
  es propia (`schemas.py`): nunca el coste, el SKU, la categoría de impuesto, las existencias ni el nombre de cocina que
  dan las lecturas del TPV. Un código que no es de ninguna mesa, el viejo de una regenerada o el de una mesa borrada
  dan el mismo 404 `online_order.qr_not_active`, sin nada del negocio.
- La carta se agrupa por categoría con la misma pieza que la carta de Página web, `base/catalog_groups.py` (cada fila de
  una lista de otra app, página a página, y los productos bajo sus categorías en su orden). Los platos se leen ya
  filtrados por «Mostrar en la carta» (`show_on_website=True`), como en Página web, con el mismo tope de 200: los que
  el negocio no muestra no ocupan sitio. Los alérgenos de los platos de un menú los da `combo.combo.for_sale` con cada
  elección, también los de un plato que no se muestra suelto en la carta. Los suplementos de un plato se leen al
  abrirlo, como hace el TPV, y solo de un plato de la carta (`online_order.not_on_menu` si no lo es).
- Modelos del pedido (UUIDv7, sin `hub_id`): `Order`, el pedido de una mesa (`table_id`, como `TableCode`), su estado
  (`pending`, `accepted` o `rejected`; hoy solo se guardan pendientes) y su total; y `OrderLine`, cada línea: un plato
  (`product_id`) o un menú (`combo_id`), nunca los dos, con su nombre, cuántos, su precio por unidad, su nota y lo que
  lleva (`picks`: cada suplemento, o cada plato del menú con su curso, por su id y con lo que suma).
- `online_order.public.send` lee las otras apps con `order_caller(ctx)` (`services.py`): el contexto del visitante más
  `ORDER_READS`, los permisos de ver mesas, productos, suplementos y menús, y ninguno que escriba. El cliente solo manda
  ids: el precio de cada plato es el de `inventory.product.list_for_sale` (con «Mostrar en la carta»), Suplementos valora
  y comprueba los suplementos con `modifier.selection.resolve` y Menús los cursos y sus suplementos con
  `combo.combo.resolve`. Lo que no está en la carta da el 409 `online_order.not_on_menu` con la línea (`lines.<n>`).
- El envío bloquea la fila del código de la mesa hasta el COMMIT: una regeneración a la vez espera al pedido, y con
  una que llegó antes el código viejo ya no abre nada, así que nunca se guarda un pedido de un QR que ya no vale.
- Límite de envíos con `base.throttle.allow`, como las lecturas públicas de Página web: 10 pedidos por mesa y 120 en el
  negocio cada 10 minutos, con el 429 `base.rate_limited`. Por mesa y no por móvil, porque los móviles que usan el wifi
  del local comparten una sola dirección.
- Las fotos de los productos y las de los menús se sirven sin sesión (`public_media` de Inventario y de Menús), porque
  las enseña esta página.
- Las mesas borradas en Mesas no salen en la lista; su fila de `TableCode` se queda y no abre nada, porque la página
  de la mesa comprobará que la mesa sigue existiendo.
- El aviso `online_order.qr_code.regenerated` no lleva el código: los avisos llegan a Automatizaciones y al
  registro, y el código abre la página de la mesa.
- La pantalla lee todas las mesas de una vez, en ventanas de 100 (`base/frontend/lib/live-all-rows.ts`), porque la
  hoja las imprime todas. El QR se dibuja en el navegador con `qrcode` (como el QR de la factura del tique) desde la
  dirección que da `online_order.qr_code.list`, así que no hace falta otra lectura; la hoja se imprime con
  `base/frontend/lib/print.ts`, que en la app instalada la manda a su pantalla de imprimir. «Generar los QR que
  faltan» llama a `online_order.qr_code.regenerate` una vez por mesa, en orden.

## Lo que queda fuera

- **Encargar para recoger** y **a domicilio** (con la dirección, las zonas de reparto, el pedido mínimo y los gastos
  de envío) son las dos entregas siguientes de esta app, después del pedido desde la mesa.
- **Pagar desde el móvil**: el pago sigue en el TPV.
- La verificación del teléfono por SMS, la rotación automática del QR y su caducidad por tiempo.
- La carta solo para mirar, con un QR para todo el local, es la de la Página web del negocio.

## Decisiones de mercado (2026-11-25)

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Odoo | QR fijo por mesa; solo con la sesión de caja abierta; entra solo a cocina; se paga en caja | https://www.odoo.com/documentation/17.0/applications/sales/point_of_sale/self_order.html |
| Square | QR fijo por mesa; la barrera es el cobro o una retención de tarjeta | https://squareup.com/help/us/en/article/8690-set-up-open-tabs-for-your-online-selling-profile |
| Toast | QR fijo por mesa; cuentas abiertas; domicilio con aprobación manual opcional | https://support.toasttab.com/en/article/Setting-Up-Toast-Mobile-Order-and-Pay |
| Lightspeed | QR por mesa; aceptación automática o manual en el TPV | https://resto-support.lightspeedhq.com/hc/articles/4411463548443 |
| Qamarero | Mesa abierta por defecto; opción de aceptar el primer pedido de cada mesa | https://intercom.help/qamarero-9e4c4f5026e3/es/articles/9711683-open-table-acepta-cada-primer-pedido-desde-el-qr |
| Last.app | QR por mesa; solo dentro del horario; QR aparte para llevar | https://desk.last.app/portal/en/kb/articles/lastqr-configuration |
| SumUp | Se paga al pedir; sin cuenta abierta | https://www.sumup.com/es-es/pedir-y-pagar/ |
| GloriaFood | Aceptar o rechazar cada pedido | https://gloriafood.com/order-taking-app-for-restaurants |

La ubicación del móvil se descarta: su precisión depende del dispositivo y del entorno y exige permiso
(https://developer.mozilla.org/en-US/docs/Web/API/GeolocationCoordinates/accuracy).
