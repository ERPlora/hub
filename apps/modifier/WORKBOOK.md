# Workbook — Suplementos (app)
Prefijo: MODIFIER
Alcance MVP: restaurante
Estado de la app: completa (2026-10-21)

> Manual de usuario y especificación de la app `modifier`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Modificadores del producto actual
> (`modules-workspace/modules/modifiers`, `origin/main` `eb43c64`, v0.1.14) y de lo que el TPV viejo
> hacía con los suplementos (`modules/sales`, `origin/main` `c6cf4af`: `modifier_chain`,
> `modifier_child_line`, `paper-modifiers`). Los números de flujo se conservan
> (`MODIFIERS-Fnn` → `MODIFIER-Fnn`) porque Ventas y Cocina los citan.

## Para qué sirve y para quién

Suplementos es el catálogo de las elecciones que acompañan a un plato: el «punto de la carne», el
«extra de queso», el tamaño, «sin cebolla». Se ordena en **grupos**:

- cada grupo dice **cuántas opciones hay que elegir**: un mínimo (1 o más lo hace **obligatorio**) y un
  máximo (0 es sin techo), y si **una misma opción se puede repetir** («doble de queso»);
- cada **opción** lleva su **suplemento de precio**: más, menos o gratis; puede salir **elegida por
  defecto** y, si tributa a otro IVA que el plato (un refresco dentro de un menú), su **categoría
  fiscal propia**;
- un grupo se **engancha a productos o a categorías** de Inventario, y **se comparte**: el mismo grupo
  «Salsas» sirve a todas las hamburguesas y a toda la categoría «Carnes».

Es **Ventas** quien pregunta los grupos en el TPV, cobra el suplemento y lo manda a cocina: esta app
guarda el catálogo, dice qué grupos lleva cada artículo y es **la única fuente del precio** del
suplemento: lo que mande el navegador no cuenta.

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** crean, cambian y borran grupos y
  opciones, y los enganchan o sueltan.
- El **empleado** (camarero, cajero) consulta los grupos; quien lo vive cada día es él, en el TPV.

No es una variante de producto (una opción no lleva stock ni coste y no descuenta existencias) ni un
menú a precio cerrado (eso es Menús).

## Referencia adoptada

Contrastada con el barrido de mercado del módulo actual (20/08/2026) y con la ronda de este porte
(15/10/2026, skill `market-decision`); se adopta esto, no más:

- **Square** (modificadores): el grupo es un objeto propio y reutilizable, con mínimo y máximo de
  selecciones; una opción puede venir **preseleccionada**; se asigna a muchos artículos.
- **Toast** (grupos de modificadores): nombre de cocina distinto del comercial; el suplemento puede ser
  recargo o descuento; opciones **por defecto**; un pedido al que le falta un grupo obligatorio no se
  envía.
- **Clover** (grupos): no hay casilla «obligatorio»: obligatorio es «mínimo 1 o más».
- **Lightspeed Restaurant**: el grupo se cuelga de un artículo **o de una categoría**; un modificador no
  es una variante y no mueve stock; permite cantidades de la misma opción.
- **LS Central** (infocodes): el suplemento con otro tipo de IVA es su propia línea de venta.
- **Revo XEF** y **Ágora** (TPV de hostelería en España): grupos de «modificadores»/«suplementos» con
  mínimo, máximo y opción por defecto, editados en la misma ficha del grupo con sus artículos.
- **Loyverse** y **Odoo PdV**: las opciones y los artículos a los que se aplican se editan en pantalla,
  no por otra vía; el precio extra lo pone el catálogo.

## Antes de empezar

- Suplementos necesita **Inventario** (los productos y categorías a los que se engancha un grupo) e
  **Impuestos** (la categoría fiscal propia de una opción). Encender Suplementos enciende las dos.
- Sin **Ventas** nadie pregunta los grupos en el TPV; sin **Cocina** la comanda no los lleva. Las dos
  hablan con Suplementos por sus servicios, nunca por sus tablas.
- Los suplementos van en **euros con céntimos** en pantalla y en **céntimos enteros** por la API; pueden
  ser negativos (un descuento) o cero (gratis).

Configuración inicial, paso a paso:

1. Abre **Suplementos** y pulsa «Nuevo grupo»: nombre, y si hace falta nombre en la comanda, mínimo,
   máximo y si se repite (MODIFIER-F02).
2. Abre el grupo (toca su fila) y añade sus opciones con su suplemento (MODIFIER-F04).
3. En la misma hoja, en «Se aplica a», engánchalo a los productos o categorías que lo llevan
   (MODIFIER-F05).
4. En el TPV, toca uno de esos artículos: sale la hoja con el grupo, su regla y el precio de cada opción
   (MODIFIER-F06).

## Pantallas

### Suplementos
Menú **Suplementos** (una sola entrada). Arriba, el título «Suplementos». Debajo, la tabla de grupos
con el buscador «Buscar…» (busca por nombre y por nombre de comanda): **Nombre** (se ordena y se
filtra), **En la comanda** (el nombre de cocina; vacío, el comercial), **Elección** (se ordena por el
mínimo y se filtra por Obligatorio u Opcional), **Opciones** (cuántas tiene), **Se aplica a** (a
cuántos productos y categorías) y **Orden**; las tres últimas también se ordenan. La columna Elección
dice la regla: «Opcional» u «Obligatorio (mín. N)», con « · máx. N» si hay techo y « · se repite» si
una opción puede repetirse. Por orden y nombre; páginas de 50.

Quien puede gestionar ve **«Nuevo grupo»** y, en cada fila, **Editar** y **Borrar**. Tocar una fila abre
la hoja del grupo, a todos.

### Hoja del grupo
Título «Grupo — {nombre}» y su regla. Dos apartados:

- **Opciones**: cada una con su nombre, su nombre de comanda (si es otro), su suplemento («+1,00 €»,
  «−0,50 €» o «Gratis»), su categoría fiscal propia si la tiene y la marca «Por defecto». Quien gestiona
  ve «Añadir opción» y, en cada una, Editar y Borrar. Vacío: «Este grupo todavía no tiene opciones.».
  Si tiene menos opciones de las que pide el mínimo (y no se repiten), un aviso lo dice: el TPV no
  podría completarlo.
- **Se aplica a**: cada producto («Producto · Hamburguesa (HAM-01)») o categoría («Categoría ·
  Carnes») al que está enganchado; quien gestiona ve «Añadir producto o categoría» y, en cada uno,
  «Dejar de aplicar». Vacío: «Este grupo todavía no se aplica a nada: no saldrá en el TPV.».

De 20 en 20, con «Cargar más».

### Formularios
- **Grupo** («Nuevo grupo» / «Editando grupo — {nombre}»): Nombre, «Nombre en la comanda», «Mínimo (1 o
  más = obligatorio)», «Máximo (0 = sin techo)», «Se puede repetir una opción» y Orden.
- **Opción** («Nueva opción» / «Editando opción — {nombre}»): Nombre, «Nombre en la comanda»,
  «Suplemento (€)» (negativo descuenta; vacío o 0, gratis), «Categoría fiscal propia» (se busca;
  vacía = la del plato), Orden y «Elegida por defecto».
- **Enganchar** («Aplicar «{grupo}» a…»): Producto o Categoría, y el buscador de cada uno.
- **Borrar** grupo u opción y **Dejar de aplicar**: piden confirmación diciendo qué se va con ello.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Todavía no hay grupos de suplementos.» (o «Sin resultados» con búsqueda o filtro), con «Nuevo grupo» si puede crear; en la hoja, los vacíos de cada apartado. |
| Error | El aviso de la tabla con «Reintentar»; un rechazo de un formulario sale dentro de él, junto a su campo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva (`app_inactive`) | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| MODIFIER-F01 | Consultar y buscar los grupos | hecho |
| MODIFIER-F02 | Crear un grupo | hecho |
| MODIFIER-F03 | Cambiar o borrar un grupo | hecho |
| MODIFIER-F04 | Añadir, cambiar o quitar las opciones de un grupo | hecho |
| MODIFIER-F05 | Enganchar un grupo a productos o categorías, y soltarlo | hecho |
| MODIFIER-F06 | Elegir las opciones al vender un artículo | hecho |
| MODIFIER-F07 | Cobrar el suplemento: precio y IVA | hecho |
| MODIFIER-F08 | Que el suplemento salga en la comanda de cocina | hecho |
| MODIFIER-F09 | Soltar los grupos de un producto o una categoría que se borra | hecho |

### MODIFIER-F01 Consultar y buscar los grupos
<!-- origen: old:modifiers/WORKFLOW.md#modifiers-f01 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Suplementos
Pasos:
1. Abre **Suplementos**.
2. Lee la tabla: nombre, nombre de comanda, regla de elección, cuántas opciones, a cuántos productos y
   categorías se aplica y orden.
3. Para encontrar uno, escribe en «Buscar…» (nombre o nombre de comanda), ordena por una columna o
   filtra por nombre o por si es obligatorio u opcional.
Entra: los grupos del negocio.
Sale: nada; solo lee.
Si falla: el aviso de la tabla con «Reintentar»; sin grupos, «Todavía no hay grupos de suplementos.».
Implicados: ninguno

### MODIFIER-F02 Crear un grupo
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 old:modifiers/WORKFLOW.md#modifiers-f02 qa:modules/modifiers/required-modifiers-and-price -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Suplementos
Pasos:
1. Pulsa «Nuevo grupo».
2. Escribe el Nombre (obligatorio, único en el negocio sin mirar mayúsculas: «Salsas» y «salsas» son
   el mismo grupo).
3. Si la comanda debe decir otra cosa, escribe «Nombre en la comanda»; vacío, cocina lee el nombre.
4. Pon el Mínimo (1 o más lo hace obligatorio; 0, opcional), el Máximo (0 es sin techo; si no es 0, no
   puede ser menor que el mínimo), si una opción se puede repetir y el Orden en que sale en el TPV.
5. Pulsa «Crear»: el formulario se cierra y el grupo sale en la tabla. Todavía no sale en el TPV:
   faltan sus opciones (F04) y dónde se aplica (F05).
Entra: lo que escribe la persona.
Sale: el grupo (avisa: grupo creado). No crea opciones ni enganches.
Si falla: un nombre vacío o de más de 255 caracteres, un mínimo o máximo fuera de 0–50 o un máximo por
debajo del mínimo salen debajo de su campo; un nombre que ya tiene otro grupo, «Ya hay un grupo con ese
nombre.» debajo del Nombre. Lo escrito se queda.
Implicados: ninguno

### MODIFIER-F03 Cambiar o borrar un grupo
<!-- origen: old:modifiers/WORKFLOW.md#modifiers-f03 -->
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Suplementos
Pasos:
1. En la fila del grupo pulsa **Editar**, cambia lo que haga falta y pulsa «Guardar». Lo que no se toca
   se queda como estaba.
2. Para borrarlo, pulsa **Borrar**: la confirmación dice cuántas opciones y cuántos enganches se van
   con él. Confirma.
Entra: el grupo (por su id o su nombre) y los campos nuevos.
Sale: el grupo cambiado (avisa: grupo cambiado) o borrado con sus opciones y sus enganches, en una sola
operación (avisa: grupo borrado). Lo ya pedido o vendido no cambia: Ventas congela el suplemento en la
línea.
Si falla: los mismos rechazos que al crear; bajar el máximo por debajo de las opciones que ya salen por
defecto, «Este grupo tiene más opciones por defecto que su máximo.». Un grupo que no existe, «Este
grupo no existe.».
Implicados: SALE-F11

### MODIFIER-F04 Añadir, cambiar o quitar las opciones de un grupo
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 qa:modules/modifiers/required-modifiers-and-price old:modifiers/WORKFLOW.md#modifiers-f04 -->
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Suplementos (hoja del grupo)
Pasos:
1. Abre el grupo y, en Opciones, pulsa «Añadir opción».
2. Escribe el Nombre (único dentro del grupo) y, si hace falta, el nombre de comanda.
3. Escribe el Suplemento en euros: positivo cobra de más, negativo descuenta, vacío o 0 es gratis.
4. Solo si la opción tributa distinto del plato, elige su categoría fiscal propia; vacía, hereda la del
   plato.
5. Marca «Elegida por defecto» si el TPV debe traerla ya marcada. En un grupo de máximo 1, marcar otra
   desmarca la anterior; con otro máximo, no puede haber más opciones por defecto que el máximo.
6. Pulsa «Crear». Para cambiarla, **Editar**; para quitarla, **Borrar** (pide confirmación).
Entra: el grupo, nombre, nombre de comanda, suplemento, categoría fiscal propia, orden y si es por
defecto.
Sale: la opción (avisa: opción creada, cambiada o borrada). Borrarla la retira del catálogo: lo ya
pedido conserva su copia congelada, también en la comanda.
Si falla: un nombre vacío o repetido en el grupo, un suplemento que no es un importe, una categoría
fiscal que no existe en Impuestos o más opciones por defecto que el máximo salen junto a su campo. Una
opción con categoría fiscal propia se cobra en una línea aparte, que no puede valer cero ni menos: «Una
opción con su propia categoría fiscal se cobra en una línea aparte: su suplemento tiene que ser mayor
que cero.». Un grupo admite hasta 100 opciones.
Implicados: SALE-F11

### MODIFIER-F05 Enganchar un grupo a productos o categorías, y soltarlo
<!-- origen: wf:restaurante-dia#rec_restaurante-f03 qa:modules/modifiers/required-modifiers-and-price old:modifiers/WORKFLOW.md#modifiers-f05 -->
Estado: hecho
Actor: propietario, administrador, responsable, asistente
Pantalla: Suplementos (hoja del grupo)
Pasos:
1. Abre el grupo y, en «Se aplica a», pulsa «Añadir producto o categoría».
2. Elige Producto o Categoría y búscalo por su nombre (o el SKU, en un producto).
3. Pulsa «Aplicar». El mismo grupo puede colgar de muchos productos y categorías, y un producto puede
   llevar varios grupos: salen en el TPV por su Orden y su nombre.
4. Para quitarlo, pulsa **Dejar de aplicar** en esa fila (pide confirmación); después puede volver a
   engancharse.
Entra: el grupo y el producto o la categoría, de Inventario (por su id, o por su nombre o SKU).
Sale: el enganche (avisa: enganche hecho o soltado). En el TPV, el artículo pregunta sus grupos y los
de **todas** sus categorías, cada grupo una sola vez.
Si falla: un producto o una categoría que no existe o está borrado, «Este producto no existe en este
hub.» o «Esta categoría ya no existe.»; un enganche que ya existe, «Este grupo ya se aplica ahí.».
Implicados: INVENTORY-F01, INVENTORY-F06

### MODIFIER-F06 Elegir las opciones al vender un artículo
<!-- origen: qa:verticals/restaurant/03-menu-and-prices wf:restaurante-dia#rec_restaurante-f06 wf:restaurante-dia#rec_restaurante-f17 qa:modules/modifiers/required-modifiers-and-price old:modifiers/WORKFLOW.md#modifiers-f06 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Ventas: Vender
Pasos:
1. En el TPV, toca un artículo que tiene grupos (suyos o de cualquiera de sus categorías): se abre una
   hoja con su nombre. Sin grupos, el artículo entra directo.
2. Cada grupo dice su regla: «Elige N» si pide justo N, «Elige de N a M» si pide un mínimo y deja llegar a
   un techo, «Elige al menos N» si pide un mínimo sin techo, «Hasta N» si solo tiene techo, «Opcional» si
   no; cada opción lleva su suplemento con su signo si no es cero («+1,00 €») y las opciones por defecto ya
   salen marcadas.
3. Toca las opciones: en un grupo de una sola, tocar otra la cambia y tocar la misma la quita; en un grupo
   que se repite, cada opción va en su renglón, con su nombre entero, y cada toque suma uno al contador
   («× 2») que «−» resta; al llegar al techo, el siguiente toque avisa de que el grupo está completo.
4. Mientras un grupo obligatorio no esté completo, el botón dice «Elige una opción para continuar» y
   tocarlo señala ese grupo. Con todo elegido, dice «Añadir · <precio>» con los suplementos ya sumados.
5. Pulsa «Añadir»: la línea entra con las opciones en el orden en que se tocaron y su precio.
Entra: los grupos y opciones de este artículo (servicio «grupos de un producto»).
Sale: la línea con las opciones elegidas; del TPV solo viajan las opciones, nunca su precio.
Si falla: un grupo sin opciones no se pregunta. Un grupo enganchado al producto y a su categoría sale
una sola vez. Si no se pueden leer los grupos, «No se han podido leer los suplementos de este producto.
Inténtalo de nuevo.» y no entra nada.
Implicados: SALE-F11

### MODIFIER-F07 Cobrar el suplemento: precio y IVA
<!-- origen: wf:restaurante-dia#rec_restaurante-f11 old-hub:HUB_PERIPHERALS-F09 qa:modules/modifiers/required-modifiers-and-price old-hub:HUB_PERIPHERALS-F11 old:modifiers/WORKFLOW.md#modifiers-f07 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al añadir la línea (a una cuenta o a una venta directa), Ventas pide a Suplementos que **compruebe y
   valore** las opciones elegidas para ese artículo, con la sesión de quien vende.
2. Suplementos comprueba que cada opción es de un grupo de ese artículo, que cada grupo tiene entre su
   mínimo y su máximo y que nada se repite donde no se puede; devuelve cada opción con su precio de
   catálogo, sus nombres y su categoría fiscal.
3. Una opción sin categoría fiscal propia, o con la del plato, se suma al precio de la línea; una con
   otra categoría se cobra en una línea propia, hija de la del plato, con su tipo.
4. Ventas congela esa copia en la línea: cambiar o borrar la opción después no cambia lo que paga esa
   mesa.
5. Al cobrar, el tique nombra las opciones bajo el plato y cada opción con otra categoría fiscal sale como
   línea propia («+ Refresco»), por cada plato, con su base y su cuota: lo que dice la cuenta es lo que paga
   la tarjeta.
Entra: el artículo y las opciones elegidas, en orden.
Sale: las opciones con su precio, el total que se suma a la línea y cuáles van en línea propia; una opción
elegida dos veces cuenta dos; ninguna mueve stock.
Si falla: una opción que no es de ese artículo, «Esta opción no se ofrece con este producto.»; un grupo
por debajo de su mínimo, «Elige al menos N en «Grupo».»; por encima de su máximo, «Elige como mucho N en
«Grupo».»; una opción repetida donde no se puede, ««Opción» no se puede repetir.»; unos descuentos que
dejarían el plato por debajo de cero, «Estas opciones dejan el precio de «Plato» por debajo de cero.»; una
opción con suplemento en un artículo que se vende a peso o por medida, ««Artículo» se vende a peso o por
medida: no admite una opción con suplemento.». La línea no entra.
Implicados: SALE-F11

### MODIFIER-F08 Que el suplemento salga en la comanda de cocina
<!-- origen: old-hub:HUB_PERIPHERALS-F10 wf:restaurante-dia#rec_restaurante-f07 old-hub:HUB_SHELL-F78 old-hub:HUB_SHELL-F72 qa:modules/modifiers/required-modifiers-and-price old:modifiers/WORKFLOW.md#modifiers-f08 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al valorar las opciones (F07), Suplementos da también el **texto de cocina**: el nombre de comanda
   de cada opción (o el nombre, si no tiene), en el orden elegido, separados por «, ».
2. Ventas lo congela en la línea y lo manda con la comanda; Cocina lo pinta debajo del plato, en la
   pantalla de cocina («+QUESO, -CEBOLLA») y en el papel, una opción por renglón.
3. Renombrar o borrar la opción, o su grupo, después de pedirla no cambia lo que ya tiene cocina.
Entra: las opciones elegidas.
Sale: el texto de cocina («+QUESO, -CEBOLLA»).
Si falla: nada que no sea F07: si la valoración falla, la línea no entra.
Implicados: KITCHEN-F07, SALE-F20

### MODIFIER-F09 Soltar los grupos de un producto o una categoría que se borra
<!-- origen: nuevo (lo pide MODIFIER-F05: un enganche apunta a un producto o una categoría de Inventario, y esos se borran) -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien borra un producto o una categoría en Inventario.
2. A los pocos segundos, Suplementos suelta los grupos que colgaban de él (avisa: enganche soltado, uno
   por grupo); los demás enganches del grupo se quedan.
Entra: el aviso de Inventario (producto borrado, categoría borrada).
Sale: los enganches soltados. Mientras el aviso llega, un enganche a algo borrado ya no se ve en la hoja del
grupo ni se pregunta en el TPV.
Si falla: repetir el aviso no cambia nada; el borrado de un negocio nunca suelta los enganches de otro.
Implicados: INVENTORY-F04, INVENTORY-F07

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia
persona) y la API, con las mismas reglas y los mismos permisos. Pensado para la voz: un grupo se nombra
por su id o su nombre («grupo Salsas»), una opción por su id o su nombre y su grupo («opción Sin cebolla
de Extras»), un producto por su id, su SKU o su nombre y una categoría por su id o su nombre. Si un
nombre casa con varios, se rechaza diciendo cuáles (409 `*_ambiguous`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los grupos, con búsqueda, filtros (nombre, obligatorio), orden y páginas (hasta 100) | ver | F01 | `modifier.group.list` |
| Un grupo por su id o su nombre | ver | F03 | `modifier.group.get` |
| Las opciones, de un grupo o todas, con búsqueda y páginas | ver | F04, F07 | `modifier.option.list` |
| Los enganches, de un grupo, de un producto o de una categoría, con páginas | ver | F05 | `modifier.link.list` |
| Los grupos con sus opciones de un producto (los suyos y los de todas sus categorías, una vez cada uno) | ver | F06 | `modifier.group.for_target` |
| La comprobación y valoración de unas opciones elegidas para un producto: precio, nombres, categoría fiscal, total a sumar y texto de cocina | ver | F07, F08 | `modifier.selection.resolve` |

Los grupos, un grupo, las opciones, los enganches y los grupos de un producto se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea un grupo | gestionar | F02 | `modifier.group.create` |
| Cambia un grupo (lo que no se manda se queda) | gestionar | F03 | `modifier.group.update` |
| Borra un grupo con sus opciones y enganches | gestionar | F03 | `modifier.group.delete` |
| Añade una opción a un grupo | gestionar | F04 | `modifier.option.create` |
| Cambia una opción (lo que no se manda se queda) | gestionar | F04 | `modifier.option.update` |
| Borra una opción | gestionar | F04 | `modifier.option.delete` |
| Engancha un grupo a un producto o una categoría | gestionar | F05 | `modifier.link.attach` |
| Suelta un grupo de un producto o una categoría | gestionar | F05 | `modifier.link.detach` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Grupo creado, cambiado o borrado | F02, F03 | El grupo (`id`, `name`) | `modifier.group.created`, `.updated`, `.deleted` |
| Opción creada, cambiada o borrada | F04 | La opción, su grupo, su nombre y su suplemento | `modifier.option.created`, `.updated`, `.deleted` |
| Enganche hecho o soltado | F05, F09 | El grupo y el producto o la categoría | `modifier.link.attached`, `.detached` |

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Producto borrado (`inventory.product.deleted`) | Inventario | Suelta los grupos de ese producto (F09) | `modifier.link.drop_product` |
| Categoría borrada (`inventory.category.deleted`) | Inventario | Suelta los grupos de esa categoría (F09) | `modifier.link.drop_category` |

### Lo que necesita de otras apps

- **Inventario** (requisito): sus productos y categorías, a los que apunta cada enganche, y las
  categorías de cada producto, para saber qué grupos lleva en el TPV.
- **Impuestos** (requisito): la categoría fiscal propia de una opción.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Ventas | Pregunta los grupos de un artículo en el TPV y comprueba y valora lo elegido al añadir la línea (SALE-F11; «Contrato con Ventas») | `modifier.group.for_target`, `modifier.selection.resolve` |
| Cocina | No lee Suplementos: recibe de Ventas las opciones congeladas de cada línea (KITCHEN-F07; «Contrato con Cocina») | — |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver grupos, opciones y enganches; pedir los grupos de un producto y valorar una elección | sí | sí | sí | sí | `modifier.view` |
| Crear, cambiar y borrar grupos y opciones; enganchar y soltar | sí | sí | sí | no | `modifier.manage` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado.

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py` (`ModifierGroup`, `ModifierOption`, `ModifierLink`),
  `migrations/`, `schemas.py`, `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`,
  `admin.py`, `locale/`, `frontend/` y un `tests/test_<fichero>.py` por fichero, más
  `tests/test_integration_inventory.py`, `tests/test_integration_tax.py`, `tests/test_integration_sale.py`
  (F06 y F07 contra Ventas: descuento, repetido, a peso e IVA al céntimo) y
  `tests/test_integration_kitchen.py` (F08, Ventas → relay → Cocina) con las apps reales,
  `tests/test_relay.py` (F09 por un tick real del relay del worker, con dos negocios) y
  `tests/test_concurrency.py` con dos sesiones de verdad.
- **`requires = ["inventory", "tax"]`**. `ModifierLink.product` y `ModifierLink.category` son claves
  ajenas a `inventory.Product` y `inventory.Category` (exactamente una de las dos, `CheckConstraint`);
  `ModifierOption.tax_category` es clave ajena a `tax.TaxCategory` (`PROTECT`: Impuestos no borra
  categorías). Los productos y categorías se buscan con `find_product`/`find_category` de Inventario
  (su `requires`), que ya excluyen lo borrado y dicen 409 `inventory.*_ambiguous` con los candidatos.
- **Unicidad en la base de datos**: nombre del grupo sin mirar mayúsculas (`Lower(name)`), nombre de la
  opción dentro de su grupo, y un enganche por grupo y producto o grupo y categoría. Las operaciones
  comprueban antes y, si dos escrituras chocan a la vez, la segunda recibe el mismo 409 (captura del
  `IntegrityError` en un savepoint; test con hilos y sesiones reales).
- **Reglas del grupo, también en la base de datos**: mínimo y máximo entre 0 y 50 y máximo 0 o mayor o
  igual que el mínimo (`CheckConstraint`). Las opciones por defecto: en un grupo de máximo 1, marcar
  una desmarca la otra (en la misma transacción, con la fila del grupo bloqueada); con otro máximo, no
  más que el máximo (409 `modifier.too_many_defaults`). Bajar el máximo por debajo de las que ya hay
  por defecto, el mismo 409.
- **Valoración (`modifier.selection.resolve`)**: la única puerta del precio. Para un producto vivo,
  sus grupos son los suyos y los de todas sus categorías vivas, sin repetir; un grupo sin opciones no
  se pregunta ni se exige. Comprueba pertenencia (409 `modifier.option_not_offered`), mínimo
  (`modifier.choice_below_min`), máximo (`modifier.choice_above_max`) y repetición
  (`modifier.option_repeated`), con el campo `option_ids`. `own_line` = la opción tiene categoría fiscal
  y no es la del producto; `folded_delta` = la suma de las que no van en línea propia; `own_lines` = una
  por opción en línea propia, con su cantidad por unidad del plato. Rechaza también un plato que quedaría
  por debajo de cero (`modifier.price_below_zero`) y cualquier suplemento en un artículo que no se vende
  por unidad (`modifier.priced_by_measure`). Hasta 100 elecciones por llamada.
- **`modifier.group.for_target` no pagina** a propósito: es la respuesta de un solo artículo, en una
  llamada (sin N+1 por grupo), acotada por las 100 opciones como mucho de cada grupo (409
  `modifier.group_full`). El resto de listas pagina (hasta 100); los empates de la columna se desempatan por
  nombre y por `id` en la dirección de la lista: en descendente es la ascendente leída al revés, empates
  incluidos (`_ordered`, nota vigente del 2026-09-28, hub#2355). El catálogo entero de opciones por
  `sort_order` va antes por el orden y el nombre de sus grupos, en los dos sentidos. Lo fijan los
  `test_tied_*` de `tests/test_queries.py`, con las filas creadas fuera de orden.
- **Dinero**: céntimos enteros con signo, entre −99.999.999 y 99.999.999. Una opción con categoría
  fiscal propia tiene que valer más de cero (422 en `price_delta`): su línea propia no puede valer cero
  ni menos. Lo comprueba la operación antes y la base de datos después
  (`modifier_option_own_line_positive`, que `_save` convierte en el mismo 422). En pantalla, el campo del
  suplemento lleva un botón ± porque el teclado decimal de un móvil no tiene el signo menos.
- **Bloqueos**: crear o cambiar una opción y enganchar un grupo bloquean antes la fila del grupo; borrar
  el grupo a la vez espera, o es esperado y entonces se dice (404), nunca un enganche a un grupo borrado
  que rompe el COMMIT (test con hilos). Lo que la escritura nombra de otra app (el producto o la
  categoría de un enganche, la categoría fiscal propia de una opción) queda retenido hasta su COMMIT con
  `held()` de Inventario (`FOR KEY SHARE`): su borrado a la vez, el «Borrar» del negocio o el del admin
  del Hub, espera; uno que ya estaba en curso se ve acabado y se dice como uno borrado antes (404 del
  producto o la categoría, 422 en `tax_category_key`), nunca un enganche a algo borrado ni un
  `IntegrityError` en el COMMIT (500).
- **Borrar es borrar**: un grupo arrastra sus opciones y enganches por `CASCADE`; Ventas guarda su
  copia congelada. Un producto o categoría de Inventario se borra lógicamente y el relay del outbox del
  worker (`base/relay.py`, cada tick) entrega su aviso a `events.REACTIONS` (F09); mientras llega, los
  enganches a lo borrado se excluyen de toda lectura (`LIVE_LINK`).
- **Reacciones** (`events.REACTIONS`): `inventory.product.deleted` → `modifier.link.drop_product`,
  `inventory.category.deleted` → `modifier.link.drop_category`; como sistema (`modifier.system`, que
  ningún papel tiene), sin ruta, idempotentes.
- **Asistente**: cada operación declara `ai` (descripción; en las escrituras, `risk`: `high` al borrar
  un grupo o una opción) y cada campo de `schemas.py` su `description`. `expose_api` en las seis
  consultas.
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17), solo en `hubs.erplora.com` y para
  el staff: lo que guarda no pasa por las operaciones ni deja aviso, y no aplica sus reglas propias (las
  opciones por defecto dentro del máximo, las 100 opciones por grupo); la base de datos sí le rechaza
  nombres repetidos, un máximo por debajo del mínimo, una opción con IVA propio que no vale más de cero y
  enganches vacíos, dobles o repetidos.
- **Señalado, sin resolver aquí**:
  - `apps/modifier/tests/test_events.py` (`test_the_reaction_runs_as_the_system_scope_given`) da por bueno que la
    reacción de un ámbito B borre los enganches que creó A: es el estado de la fase 1, con las tablas
    compartidas y sin tenencia. En la fase 2, cada hub en su base de datos, la reacción solo verá los
    suyos y el test tendrá que decirlo.
  - Las claves ajenas `CASCADE` de `ModifierLink` hacia `inventory.Product` y `inventory.Category`
    chocarán en la fase 2 con «tablas al activar» (PLAN §15): las tablas de Suplementos solo existen en
    un hub que las encendió, e Inventario es su `requires`, así que se crean después; pero un borrado
    físico de un producto desde el admin cruzaría a una tabla de otra app. Señalado para PLAN-DB.

- **Páginas** (`frontend/`): `pages/GroupsPage.vue` (la tabla, `useLiveList` en ventanas de hasta 100),
  `components/GroupSheet.vue` (la hoja: `modifier.group.get` vivo y dos `useSheetList` de 20 en 20),
  `GroupFormModal`, `OptionFormModal` (con `MoneyInput` con signo y el `Combo` de Impuestos),
  `LinkFormModal` (Producto o Categoría, `Combo` sobre las listas de Inventario), `PageNotices`; las
  búsquedas de los `Combo` llaman a las operaciones de Inventario e Impuestos (`lib/pickers.ts`), nunca
  a sus modelos. Icono: `lucide:sliders-horizontal` (el `options-outline` de antes, pedido en
  `UI-REQUESTS.md`). Pruebas: Vitest por fichero, `tests/e2e/modifier-groups.spec.ts` (F01 a F05) contra
  Inventario e Impuestos reales y `tests/e2e/modifier-till.spec.ts` (F06 a F09) contra Inventario,
  Impuestos, Ventas y Cocina reales, con el relay del outbox corrido como lo corre cada tick.

### Paridad con la pantalla del producto actual

| Producto actual (`erp-modifiers-groups`) | Aquí | Motivo si cambia |
|---|---|---|
| Título «Modificadores» y menú de una entrada | «Suplementos», una entrada | El nombre que ya usa Ventas |
| Formulario de alta encima de la tabla (Nombre, Nombre en la comanda, Mínimo, Máximo, «Añadir») | «Nuevo grupo» abre el formulario con esos campos, más «Se puede repetir» y Orden | El patrón de la plataforma (`DataTable` + `FormModal`, como Impuestos y Servicios); el alta pedía repetir y orden por el asistente |
| «Guardando…» y botón desactivado sin nombre | El botón Crear con su espera y desactivado sin nombre | — |
| Fallo del alta bajo el formulario | Dentro del formulario, junto a su campo | — |
| Columnas Nombre (orden y filtro), En la comanda (o el nombre), Elección (orden), Orden (orden) | Las mismas, más Opciones y «Se aplica a»; Elección se filtra por obligatorio u opcional | Las cuentas dicen si el grupo saldrá en el TPV |
| Elección «Opcional» / «Obligatorio (mín. N)» « · máx. N» | Igual, más « · se repite» | Repetir ahora funciona |
| Buscador «Buscar…» (nombre y nombre de comanda), páginas de 50 | Igual | — |
| Vacío «Todavía no hay grupos de modificadores.», «Cargando…», error con reintento | «Todavía no hay grupos de suplementos.», «Cargando…», error de la tabla con «Reintentar» | El nombre |
| El formulario sale también al empleado (el servidor pide PIN) | El alta, editar y borrar solo salen a quien gestiona | Lo que no se puede hacer no aparece (regla de las demás apps) |
| Opciones, enganches, editar y borrar: solo asistente o API | En la hoja del grupo, además del asistente y la API | MODIFIER-F03 a F05 en pantalla |

### Contrato con Ventas

Lo que Ventas hace con Suplementos (SALE-F11, hecho; Suplementos no toca `apps/sale`).
Ventas **no requiere** Suplementos: llama a sus servicios por nombre (`call_app`), con la sesión de
quien vende, y sin Suplementos activo una línea con opciones se rechaza con su propio código
(`sale.modifier_unavailable`) y una sin opciones entra como siempre. El TPV solo pregunta los grupos con
Suplementos encendida y el permiso de verla (hub#1121); el empleado lo tiene, y cobra con su propia sesión
(hub#1219, `tests/test_integration_sale.py`).

1. **La hoja del TPV** (MODIFIER-F06): al tocar un artículo, `modifier.group.for_target` con
   `product_id`. Sin grupos, la línea entra directa. Con grupos, la hoja: regla por grupo («Elige N» con
   mínimo = máximo, «Elige de N a M» con mínimo ≥ 1 y un techo mayor, «Elige al menos N» con mínimo ≥ 1 sin
   techo, «Hasta N» opcional con techo, «Opcional»; `ruleOf` de `apps/sale/frontend/lib/modifierChoice.ts`,
   hub#143), opciones con su suplemento si no es 0, `is_default` ya marcadas, en los grupos con
   `allow_repeat` una opción por renglón con su contador y su «−», y «Añadir» desactivado («Elige una opción
   para continuar») mientras un grupo esté fuera de su mínimo y máximo.
2. **Añadir la línea** (`sale.order.add_line` y las líneas de `sale.sale.complete` y `sale.order.open`):
   un campo nuevo `option_ids` (lista de UUID en el orden de elección, hasta 100). En la misma
   transacción, `modifier.selection.resolve` con `product_id` y `option_ids`; sus 409 llegan a quien
   vende tal cual (con `fields.option_ids`). **Se llama SIEMPRE** que Suplementos esté activo, también
   con `option_ids` vacío: es lo que rechaza una línea sin un grupo obligatorio cuando llega por la API
   o el asistente, que no pasan por la hoja (probado: vacío y grupo obligatorio → 409
   `modifier.choice_below_min`).
3. **Congelar en la línea** la respuesta: por cada `picks[]`, `option_id`, `group_id`, `group_name`,
   `name`, `kitchen_name`, `price_delta`, `tax_category_key` y `own_line`, en el orden recibido; las
   `own_lines` y el `kitchen_text`. El precio unitario de la línea suma `folded_delta`. Lo que mande el navegador como
   precio del suplemento se ignora. Una cuenta abierta cobra lo congelado, aunque la opción cambie o se
   borre después.
4. **Al cobrar**, cada elemento de `own_lines` sale como línea hija de la del plato, con su
   `price_delta` como precio unitario y la categoría fiscal de la opción (sin producto ni stock); su
   cantidad es `quantity` (por unidad del plato) **por la cantidad de la línea del plato**: dos
   hamburguesas con un refresco cada una son una hija de 2; la misma opción elegida dos veces es una sola
   hija con `quantity` 2, no dos hijas. Siempre vale más de cero: Suplementos lo impide al guardar la
   opción, también en la base de datos.
   Decisión (`market-decision`): Square, Toast, Lightspeed, Clover y Revo multiplican el modificador por
   la cantidad del artículo y agrupan las repeticiones de una opción en una cantidad; ninguno factura un
   modificador por línea con independencia de cuántos platos lleva.
5. **El dinero que Suplementos ya garantiza** y Ventas no tiene que volver a comprobar:
   - `folded_delta` nunca deja el plato por debajo de cero: `price + folded_delta < 0` es 409
     `modifier.price_below_zero` (un «Sin carne −5,00 €» sobre un plato de 3,00 € no entra; a 0 sí, un
     plato gratis es un precio). Así `unit_price` nunca es negativo (es un entero positivo en Ventas y
     una línea negativa no cabe en un tique de VeriFactu).
   - Un artículo que no se vende por unidad (unidad o unidad de precio distinta de `ud`, o
     `price_quantity` distinto de 1: el jamón por kilo, los tornillos a 0,37 € el ciento) no admite
     ninguna opción con suplemento, ni sumada ni en línea propia: 409 `modifier.priced_by_measure`.
     Ventas valora esas líneas por su cantidad (`price_ratio`), y +1,00 € sobre 0,350 kg cobraría
     0,35 €. Las opciones gratis («loncheado») sí entran.
6. **El tique** (Impresión, `items[].modifiers`): los nombres comerciales (`name`) de la línea, sin
   importe, porque el suplemento ya está dentro del precio de la línea.
7. **La comanda** (`sale.order.fired`): cada línea lleva su `kitchen_text` congelado como
   `modifiers` (ver «Contrato con Cocina»).
8. **Dividir y juntar cuentas** mueven la línea con su copia congelada; no se vuelve a valorar.

Casos cubiertos, del TPV viejo (`modifier_chain`, `modifier_child_line`): la hamburguesa con queso cobra
8,00 + 1,00 € y no 8,00 € (sales#148); lo que vale la cuenta y lo que cobra la caja son el mismo número; la
opción con otro IVA sale en línea hija y base + cuota cuadran en las dos; una opción sin categoría propia
sigue siendo una sola línea (`apps/sale/tests/test_integration_modifier.py`); el descuento, el repetido, el
plato a peso y el IVA de cada suplemento al céntimo, tres platos con queso y refresco: 27,15 € al 10 %
(base 24,68 €, cuota 2,47 €) y 6,15 € al 21 % (base 5,08 €, cuota 1,07 €)
(`apps/modifier/tests/test_integration_sale.py`).

### Contrato con Cocina

Cocina **no lee** Suplementos (KITCHEN-F07, hecho). Ventas congela en cada línea lo que Suplementos dio
al valorar —cada opción con su `kitchen_name` (el nombre de comanda, o el nombre si no hay), en el orden
elegido, y el `kitchen_text` («+QUESO, -CEBOLLA»)— y lo manda con la ronda (`sale.order.fired`); el relay
del worker la entrega a Cocina (`kitchen.ticket.receive`), que guarda en el plato la lista de nombres de
comanda y la pinta debajo del nombre: en la pantalla separada por «, » y en el papel una por renglón
(hub#1156, hub#1138). Renombrar o borrar la opción, o su grupo, después de pedirla no cambia lo que lee
cocina (`tests/test_integration_kitchen.py`).

### Cambios frente al producto actual

1. **Pantalla completa**: opciones, enganches, edición y borrado se hacen en la pantalla (la hoja del
   grupo), además de por el asistente y la API; antes solo el alta del grupo tenía pantalla.
2. **Cambiar no reescribe lo que no se manda**: antes, un cambio sin un campo lo devolvía a su valor de
   fábrica (mínimo 0, suplemento 0…).
3. **El servidor hace cumplir las reglas** (mínimo, máximo, repetición y que la opción sea de un grupo
   del artículo) al valorar, y la valoración es la puerta del precio. Antes solo la hoja del TPV las
   miraba y la API dejaba pasar cualquier cosa.
4. **Un grupo enganchado al producto y a su categoría sale una vez**, y cuentan **todas** las categorías
   del artículo, no solo la primera.
5. **Se puede repetir** funciona (antes el campo existía y nadie lo leía) y hay **opción por defecto**.
6. **Máximo por debajo del mínimo** se rechaza; nombres de grupo únicos en el negocio y de opción
   únicos en su grupo; una opción con categoría fiscal propia tiene que valer más de cero (antes fallaba
   al cobrar).
7. **Cambiar, borrar o soltar algo que no existe** responde 404 y no avisa (antes respondía bien y
   avisaba igual).
8. **Los enganches apuntan a productos y categorías de Inventario** con clave ajena (antes, una
   referencia opaca que aceptaba cualquier texto), y se sueltan solos al borrarse lo enganchado.
9. **Nombre**: «Suplementos» en español, el que ya usaba Ventas («Ponle precio en Suplementos»); en
   inglés, «Modifiers». El permiso del empleado sigue siendo solo de consulta, y el botón de alta solo
   sale a quien puede crear.
10. **El catálogo completo de opciones** (`modifiers.options.all`, sin paginar) se sustituye por
    `modifier.selection.resolve`, que valora solo lo elegido; la lista de opciones pagina como todas.
11. **Paginación de la hoja**: de 20 en 20 con «Cargar más».

### Lo que NO hace, a propósito

- No tiene variantes de producto ni stock ni coste por opción (descontar ingredientes es otra cosa).
- No hace menús a precio cerrado: eso es Menús.
- No cobra ni factura por sí misma: Ventas pone el dinero.
- No pinta la hoja del TPV ni la comanda: son de Ventas y Cocina.

### Lo que queda fuera

- **Suplementos de un servicio** (peluquería: «+ tratamiento de keratina»): pide enganchar a servicios
  de la app Servicios, que hoy no es requisito; la vertical de esta app es el restaurante.
- **«Agotado» por opción y activar o desactivar un grupo sin borrarlo** (Square): hoy se retira
  borrando la opción o soltando el enganche.
- **Precio de la opción distinto por producto** (Toast «size-based pricing»).
