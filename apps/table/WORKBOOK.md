# Workbook — Mesas (app)
Prefijo: TABLE
Alcance MVP: restaurante
Estado de la app: hecha (servidor y páginas; la ventana «Elegir mesa» del TPV la monta Ventas, SALE-F19).
La entrega de los avisos de otras apps (relay del outbox, fase 2) queda fuera: ver «Lo que queda fuera».

> Manual de usuario y especificación de la app `table`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Mesas del producto actual
> (`modules-workspace/modules/tables`, `origin/main` `905eb76`, v2.2.64) y de sus `workflow/*.md`.
> Los números de flujo se conservan (`TABLES-Fnn` → `TABLE-Fnn`) porque otras apps los citan. Lo que
> cambia frente al producto actual lo dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Mesas es el **plano del restaurante o del bar**: las zonas del local (salón, terraza, barra), las
mesas de cada zona con su aforo, su forma y su sitio en el plano, y las **cuentas que hay sentadas en
cada mesa**. Dice, en vivo, qué mesa está libre, ocupada, reservada o fuera de servicio, cuántos
comensales hay, desde cuándo y quién la atiende, y sabe qué cuenta de Ventas está en qué mesa.

Quién la usa:

- El **responsable** de sala dibuja el plano: crea zonas y mesas, las coloca arrastrándolas y cambia
  su aforo, su forma o su estado.
- El **administrador** y el **propietario**, además, borran mesas, zonas y cuentas del historial y
  cambian los ajustes de sala.
- El **empleado** (camarero, cajero) sienta a la gente, pasa una cuenta a otra mesa, junta o divide
  cuentas, corrige los comensales, quita la mesa a una cuenta y cierra una mesa a mano.

Mesas no cobra (eso es Ventas: la mesa lleva al TPV con su cuenta), no apunta reservas (eso será
Reservas: Mesas solo aparta la mesa en el plano) y no es la pantalla de cocina.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó.

- **Zonas, mesas colocadas en un plano, comensales por mesa y ocupación a la vista**, con el tiempo
  que lleva una cuenta abierta en ámbar y en rojo:
  [Square — planos de sala](https://squareup.com/help/us/en/article/6427-building-your-floor-plan).
- **Varias cuentas en una mesa** (dividir); las líneas las reparte Ventas:
  [Lightspeed — dividir una cuenta](https://resto-support.lightspeedhq.com/hc/en-us/articles/226405708-Splitting-a-bill),
  [Square — dividir por artículo](https://squareup.com/help/gb/en/article/8421-new-order-and-pay-capabilities-with-square-for-restaurants).
- **Pedir los comensales al sentar, transferir y juntar cuentas, sacar una mesa del servicio** y la
  lista de cuentas cerradas con su importe (Toast y Lightspeed).
- **Una mesa con su cuenta abierta no se libera a mano**: se cobra, se pasa a otra mesa o se elimina
  la cuenta (Toast, Square, Lightspeed y Odoo; tables#124 del producto actual).
- **Sentar en una mesa reservada está permitido y gasta la reserva; superar el aforo avisa pero no
  impide.**
- **La mesa reservada se pinta Reservada solo cerca de la hora de su reserva** (decisión de mercado
  de la duda 1 del producto actual). Antes de eso la mesa sigue Disponible y enseña la próxima reserva
  con su hora. Así lo hacen:

  | Producto | Cómo lo resuelve | Fuente |
  |---|---|---|
  | Toast Tables | El plano del servicio enseña en cada mesa la hora de su próxima reserva | [support.toasttab.com](https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist?lang=en_US) |
  | TouchBistro Reservations | El estado de la mesa (reservada u ocupada) es el del tramo horario que se mira, de 15 en 15 min | [TouchBistro — lista y plano](https://cdn.touchbistro.com/help/articles/reservations-ipad-app-using-the-reservation-list-and-floorplan) |
  | Tablein | La mesa con la próxima reserva más allá de la duración de una reserva lleva una etiqueta «Next» y sigue libre | [help.tablein.com](https://help.tablein.com/floor-plan) |
  | TablesReady | La mesa cambia de color cuando la reserva asignada está próxima y el grupo no ha llegado | [support.tablesready.com](https://support.tablesready.com/article/155-how-to-use-table-management) |
  | Lightspeed K-Series | La reserva tiene estados (Programada, Sentada…) y se asigna a una mesa del plano | [k-series-support](https://k-series-support.lightspeedhq.com/hc/en-us/articles/37718296880411-Understanding-the-settings-for-reservation-integrations) |
  | Odoo (módulo de reservas de mesa) | El plano marca las mesas con reserva en la ventana del servicio actual y avisa antes de sentar a otro | [ecosire.com](https://ecosire.com/apps/odoo/pos-restaurant-table-reservation) |
  | Square for Restaurants | El estado de la mesa sigue al de la reserva de OpenTable integrada | [squareup.com](https://squareup.com/gb/en/point-of-sale/restaurants/features/table-management-system) |
  | Tabit | Desde la mesa se ven sus próximas reservas | [support-us.tabit.cloud](https://support-us.tabit.cloud/hc/en-us/article_attachments/4408025435794) |

  **Gana:** Reservada desde **60 minutos antes** de la hora de la reserva hasta que acaba su ventana;
  antes, la mesa sigue Disponible con «Ana · 21:00». **Por qué no lo de antes** (Reservada desde que
  se confirma, aunque sea dentro de una semana): bloqueaba la mesa todo el servicio y un grupo sentado
  a mediodía «gastaba» la reserva de la noche.
- **Una mesa o una zona desactivada sale del servicio** (decisión de la duda 7): no se pinta en el
  plano de servicio ni se puede sentar; sigue en «Editar plano», en **Mesas** y en **Zonas**, como
  [Lightspeed — desactivar una mesa](https://k-series-support.lightspeedhq.com/hc/articles/1260804656729),
  [Toast — quitar una mesa del área de servicio](https://support.toasttab.com/article/Creating-Service-Areas-and-Table-Setup-1493049150430)
  y el estado Activa / Inactiva de los planos de [Poster](https://knowledge-base.joinposter.com/en/how-to-edit-a-table-layout-or-hide-the-floor-plan)
  y [MultiPOS](https://docs.devdiggers.com/multipos-point-of-sale-for-woocommerce/configuration/tables/).

## Antes de empezar

- Mesas necesita **Ventas** (la cuenta de cada mesa es una cuenta abierta de Ventas) y **Clientes**
  (el cliente de una mesa y el olvido de su nombre). Se encienden con ella y no se apagan mientras
  Mesas esté encendida.
- Las horas (apertura, cierre, reservas) son las del negocio: en esta fase, **Europe/Madrid**.

Configuración inicial, paso a paso:

1. En **Mesas → Zonas** (o con el «+» del **Plano de sala**) crea las zonas del local (TABLE-F01).
2. En **Mesas → Plano de sala**, en «Editar plano», con el «+» añade las mesas de cada zona (TABLE-F02).
3. Arrástralas hasta que el plano se parezca a la sala y ajusta en cada una su aforo y su forma
   (TABLE-F03, TABLE-F04).
4. En **Mesas → Ajustes** (solo el administrador) decide si al sentar se preguntan los comensales y a
   partir de cuántos minutos una cuenta abierta se pone ámbar y roja (TABLE-F08).
5. En **Plano de sala**, «Servicio», toca una mesa libre y siéntala: se abre su cuenta en Ventas.

## Pantallas

El menú **Mesas** tiene cinco pestañas: **Plano de sala**, **Zonas**, **Mesas**, **Sesiones** y
**Ajustes** (esta solo a quien puede cambiarlos). Ninguna otra se esconde por permiso; los botones
que el perfil no puede usar no salen.

### Plano de sala
Menú **Mesas → Plano de sala**. Arriba, una sola fila: la tira de zonas (se desliza de lado en el
móvil y se difumina por el borde cuando hay más zonas), el conmutador **Servicio / Editar plano** (solo
a quien puede dibujar el plano) y, en «Editar plano», un «+» («Añadir zona o mesa») y un lápiz
(«Editar zona»). Debajo, el plano de la zona elegida, con las mesas a su tamaño real: si no cabe de
ancho (móvil, tableta) se desliza de lado y el borde con mesas detrás se difumina; si no cabe de alto,
crece y se baja la página.

Cada mesa es una baldosa con su número, su estado escrito con su icono y color (Disponible, Ocupada,
Reservada, Bloqueada), el aforo («4 pax») o, si está ocupada, los comensales y los minutos que llevan
(«3 pax · 35 min», que avanzan solos) y quién la atiende; si tiene una reserva hoy, el nombre y la
hora de la reserva («Cliente borrado» si se borraron los datos de esa clienta) en una línea: un nombre
que no cabe se recorta con «…» y la hora se ve siempre entera («Maximiliana F… · 20:00»); el nombre
completo va en el título de la mesa. Las mesas redondas se pintan redondas y la rectangular, más
ancha que alta. El plano **es vivo**: cambia solo cuando alguien sienta, cobra, mueve o edita una mesa.

- **Servicio** (de entrada): no se arrastra. Tocar una mesa abre su ventana **Mesa N**:
  - libre o reservada: la pregunta de comensales («Comensales en la mesa N · 4 pax», «−» y «+», atajos
    del 1 al 8 que sientan de un toque, el aviso «Supera el aforo de la mesa (4)» y «Sentar N»), y el
    cliente opcional («Asignar cliente»). Con el ajuste de comensales apagado, «Sentar» sienta con el
    aforo (o los comensales de la reserva).
  - ocupada: comensales, desde cuándo, quién atiende, el cliente de la cuenta (asignar o quitar) y
    las acciones **Cobrar** (lleva al TPV con la cuenta), **Transferir**, **Fusionar**, **Dividir
    cuenta**, **Comensales**, **Quitar mesa** y **Cerrar mesa**. Con dos cuentas en la mesa, se elige
    primero cuál («Cuenta 1», «Cuenta 2»).
  - bloqueada: «Mesa fuera de servicio: no se puede sentar hasta que se desbloquee.».
  - Transferir y Fusionar ponen el plano en modo destino: «Transferir N a…» / «Elige una mesa libre»
    (o «Fusionar N con…» / «Elige una mesa ocupada») y «Cancelar»; solo se pueden tocar las mesas que
    valen.
- **Editar plano**: se arrastra cada mesa a su sitio (también con el teclado: flechas, 8 px; con
  Mayúsculas, 32 px) y se guarda al soltar. Tocar una mesa abre **Editar mesa** (Número, Aforo,
  Nombre (opcional), Forma, Estado (Disponible o Bloqueada), Zona, Activa; pie con «Borrar» y
  «Guardar»); el «+» abre **Añadir** (campo Zona y «Añadir zona»; campo «Número de mesa», que si se
  deja vacío «Se numera sola», y «Añadir mesa»); el lápiz abre **Editar zona** (Nombre, Descripción
  (opcional); «Borrar zona» y «Guardar»). Debajo, la ayuda «Arrastra para colocar · clic en una mesa
  para editarla o borrarla. Los cambios se guardan al momento.». En «Editar plano» se ven también las
  mesas y zonas desactivadas, en gris.

Las ventanas tapan toda la pantalla en el móvil y van centradas en tableta y ordenador.

### Zonas
Menú **Mesas → Zonas**. Tabla: Nombre (con su color), Mesas, Libres («libres / total»), Orden,
Estado (Activa, Inactiva); buscador «Buscar zona…», filtros por columna, vista tabla o tarjetas. El «+»
(solo a quien puede crear zonas) abre el panel con Nombre, Descripción, Color (Azul, Cian, Morado,
Verde, Ámbar, Rojo, Gris), Orden y «Añadir zona»; por fila «Editar» (el mismo panel con el interruptor
«Activa» y «Guardar cambios») y «Borrar» (solo el administrador), que pide confirmación en «¿Borrar la
zona?» y deja «Borrar zona» apagado si la zona tiene mesas.

### Mesas
Menú **Mesas → Mesas**. Tabla en orden natural (la 2 antes que la 10): Número, Nombre, Zona, Aforo,
Estado; buscador «Buscar mesa…» (número y nombre), filtros por columna (zona, estado, forma, aforo),
vista tabla o tarjetas. El «+» abre el panel con Número, Aforo, Zona y «Añadir mesa». Por fila,
«Editar» (Número, Nombre, Aforo, Forma, Zona, Estado y Activa) y «Borrar» (solo el administrador, con
confirmación).

### Sesiones
Menú **Mesas → Sesiones**: las cuentas de la sala. Pestañas «Abiertas», «Cerradas» y «Todas». Tabla:
Mesa («Sin mesa (aparcada)» si no tiene), Cobrado y Cierre (no salen en Abiertas), Zona, Camarero,
Comensales, Apertura, Tiempo, Estado (Abierta, Cerrada, Trasladada, Fusionada, Aparcada); el tiempo de
una cuenta abierta se pone ámbar y rojo según los Ajustes. Buscador «Buscar mesa…», filtros por zona,
camarero y estado. Por fila «Detalle» (ventana con zona, camarero, estado, comensales, apertura,
cierre, tiempo, cobrado y notas), en las abiertas «Cerrar sesión» (con confirmación), en las aparcadas
«Volver a sentar» (elige la mesa libre) y, en las terminadas, «Borrar» (solo el administrador). Las
horas van en la hora del negocio.

### Ajustes
Menú **Mesas → Ajustes**: «Preguntar los comensales al sentar una mesa», «Aviso ámbar (minutos)» y
«Aviso rojo (minutos)», y «Guardar». Solo la ve quien puede cambiarlos (de fábrica, el propietario y el
administrador).

## Estados de cada pantalla

| Pantalla | Cargando | Vacío | Error |
|---|---|---|---|
| Plano de sala | «Cargando…» | Sin zonas: «Crea una zona para empezar a colocar mesas.»; zona sin mesas: «Sin mesas en esta zona. Pulsa «Añadir mesa».» | Al cargar: aviso con «Reintentar»; al guardar, dentro de la ventana abierta (o encima del plano si no hay ninguna) |
| Zonas | La tabla en carga | «No hay zonas. Pulsa «+» para crear la primera (Salón, Terraza, Barra…).» | El de la tabla con «Reintentar»; el de guardar, dentro del panel |
| Mesas | La tabla en carga | «Sin mesas.» | El de la tabla con «Reintentar»; el de guardar, dentro del panel |
| Sesiones | La tabla en carga | «No hay sesiones. Sienta a un grupo desde el plano y aparecerá aquí.» | El de la tabla con «Reintentar»; el de cerrar, en su confirmación |
| Ajustes | «Cargando…» | — | Por campo (422) y encima del formulario |

En todas: «Reconectando…» mientras se recupera la conexión en vivo (lo pintado se queda), «Esta app
no está activa en este negocio» y «No tienes permiso».

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TABLE-F01 | Crear y ordenar las zonas del local | hecho |
| TABLE-F02 | Añadir mesas | hecho |
| TABLE-F03 | Colocar las mesas en el plano | hecho |
| TABLE-F04 | Editar o borrar una mesa | hecho |
| TABLE-F05 | Sacar una mesa del servicio (bloquearla) y devolverla | hecho |
| TABLE-F06 | Renombrar o borrar una zona | hecho |
| TABLE-F07 | Crear muchas mesas de golpe | hecho (asistente y API) |
| TABLE-F08 | Ajustar la sala: comensales al sentar y avisos de tiempo | hecho |
| TABLE-F09 | Ver cómo está la sala | hecho |
| TABLE-F10 | Sentar a un grupo en una mesa libre o reservada | hecho |
| TABLE-F11 | Volver a una mesa ocupada y cobrarla | hecho |
| TABLE-F12 | Llevar a una mesa una cuenta que ya está abierta | hecho |
| TABLE-F13 | Quitar la mesa de una cuenta (aparcarla) | hecho |
| TABLE-F14 | Corregir los comensales de una mesa ocupada | hecho |
| TABLE-F15 | Pasar la cuenta a otra mesa (transferir) | hecho |
| TABLE-F16 | Juntar las cuentas de dos mesas ocupadas (fusionar) | hecho |
| TABLE-F17 | Dividir la cuenta de una mesa | hecho |
| TABLE-F18 | Liberar la mesa al cobrar la cuenta entera | hecho |
| TABLE-F19 | Anular un cobro de una mesa | hecho |
| TABLE-F20 | Eliminar en Ventas la cuenta abierta de una mesa | hecho |
| TABLE-F21 | Cerrar una mesa a mano | hecho |
| TABLE-F22 | Consultar las cuentas de la sala (abiertas y cerradas) | hecho |
| TABLE-F23 | Borrar una cuenta cerrada del historial | hecho |
| TABLE-F24 | Volver a sentar una cuenta aparcada | hecho |
| TABLE-F25 | Retener la mesa de una reserva confirmada | servidor hecho (espera a Reservas) |
| TABLE-F26 | Mover o soltar la retención cuando cambia la reserva | servidor hecho (espera a Reservas) |
| TABLE-F27 | Soltar la mesa cuando la reserva se cancela o no se presenta | servidor hecho (espera a Reservas) |
| TABLE-F28 | Gastar la retención al sentar a la reserva | hecho |
| TABLE-F29 | Caducar las retenciones vencidas | hecho |
| TABLE-F30 | Retener o soltar una mesa a mano | hecho (asistente y API) |
| TABLE-F31 | Olvidar el nombre de un cliente cuyos datos se borran (RGPD) | servidor hecho (entrega en la fase 2) |
| TABLE-F32 | Poner o quitar el cliente de una mesa | hecho |

### TABLE-F01 Crear y ordenar las zonas del local
Estado: hecho
Actor: responsable, administrador
Pantalla: Zonas
Pasos:
1. En **Mesas → Zonas** pulsa «+».
2. Escribe el Nombre (Salón, Terraza, Barra…), elige el Color y el Orden (viene puesto el siguiente).
3. Pulsa «Añadir zona».
4. La zona sale en la lista con 0 mesas y, en ese orden, como pestaña del **Plano de sala**. También se
   crea desde el «+» del plano en «Editar plano» (campo Zona y «Añadir zona»): se pone la última y
   queda elegida.
Entra: el nombre, la descripción, el color y el orden.
Sale: la zona (avisa: `table.zone.created`).
Si falla: sin nombre, el botón no se activa. Un nombre que ya tiene otra zona: «Ya hay una zona con
ese nombre.». Un empleado no ve el «+»; si lo pide por la API, se rechaza por permiso.

### TABLE-F02 Añadir mesas
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano), Mesas
Pasos:
1. En **Plano de sala → Editar plano**, elige la zona y pulsa «+».
2. En «Número de mesa» escribe el número o nombre (S1, Terraza A) o déjalo vacío: «Se numera sola»
   con el primer número libre de esa zona.
3. Pulsa «Añadir mesa» (apagado mientras no haya ninguna zona).
4. La mesa aparece en la zona, en el primer hueco libre, cuadrada, para 4 y Disponible.
5. Otra puerta: en **Mesas → Mesas**, «+» con Número, Aforo y Zona y «Añadir mesa»; también nace en el
   primer hueco libre de su zona.
Entra: número (o ninguno), y en la lista también aforo y zona.
Sale: la mesa (avisa: `table.table.created`). Con una mesa en uso, el paso «Tus mesas» de la puesta
en marcha queda hecho (`table.floor.status`).
Si falla: número repetido en la zona (sin distinguir mayúsculas ni espacios), por cualquier puerta:
«Ya hay una mesa con ese número en esta zona.». Zona borrada mientras tanto: «Esa zona no existe en
este negocio.».

### TABLE-F03 Colocar las mesas en el plano
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano)
Pasos:
1. En **Plano de sala → Editar plano**, elige la zona.
2. Arrastra cada mesa a su sitio (el gesto lo coge solo la mesa; deslizar sobre el plano vacío lo
   desplaza). Con teclado: tabula hasta la mesa y muévela con las flechas (8 px; con Mayúsculas, 32 px).
3. Al soltar se guarda al momento. La mesa no sale del borde del plano.
4. Al recargar, cada mesa sigue donde se dejó.
Entra: la posición nueva.
Sale: la posición de la mesa (avisa: `table.table.updated`).
Si falla: «No se pudo guardar la posición» encima del plano; la mesa vuelve a su sitio guardado.

### TABLE-F04 Editar o borrar una mesa
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano), Mesas
Pasos:
1. En **Editar plano**, toca la mesa (o en **Mesas**, «Editar» en su fila): se abre «Editar mesa».
2. Cambia Número, Aforo, Nombre (opcional), Forma (Cuadrada, Redonda, Rectangular), Estado
   (Disponible o Bloqueada), Zona o Activa.
3. Pulsa «Guardar»: la ventana se cierra y el plano cambia solo (si cambió de zona, aparece en la otra
   pestaña en el mismo sitio).
4. Para quitarla, pulsa «Borrar» (solo el administrador) y confírmalo: desaparece del plano y de la
   lista; su historia de cuentas se conserva.
Entra: la mesa elegida.
Sale: la mesa cambiada (avisa: `table.table.updated`) o borrada (avisa: `table.table.deleted`).
Si falla: dentro de la ventana: «El número de mesa es obligatorio», «Ya hay una mesa con ese número
en esta zona.», «Esa mesa no existe en este negocio.»; borrar una mesa con cuenta abierta: «Esa mesa
tiene una cuenta abierta. Ciérrala o trasládala antes de borrar la mesa.».

### TABLE-F05 Sacar una mesa del servicio (bloquearla) y devolverla
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano), Mesas
Pasos:
1. Abre «Editar mesa» y en «Estado» elige «Bloqueada»; pulsa «Guardar».
2. La mesa sale Bloqueada (gris) en el plano y no se puede sentar: «Mesa fuera de servicio: no se
   puede sentar hasta que se desbloquee.».
3. Para devolverla, pon «Disponible» y guarda.
4. Bloquear una mesa ocupada no toca su cuenta: sigue Ocupada hasta cobrarla y entonces queda
   Bloqueada. Una reserva no pinta Reservada una mesa Bloqueada.
Entra: la mesa elegida.
Sale: el estado de la mesa (avisa: `table.table.updated`).
Si falla: como en TABLE-F04. Sentar en una mesa bloqueada (asistente, API) se rechaza con el mismo
motivo.

### TABLE-F06 Renombrar o borrar una zona
Estado: hecho
Actor: responsable, administrador
Pantalla: Zonas, Plano de sala (Editar plano)
Pasos:
1. En **Mesas → Zonas**, «Editar»: cambia Nombre, Descripción, Color, Orden o «Activa» y pulsa
   «Guardar cambios». En el plano, el lápiz («Editar zona») cambia Nombre y Descripción.
2. Para borrarla (solo el administrador): «Borrar» abre «¿Borrar la zona?» con «N mesas en esta zona.
   Una zona con mesas no se puede borrar: mueve o borra antes sus mesas.»; con mesas, «Borrar zona»
   sale apagado.
3. Sin mesas, «Borrar zona» la quita de la lista y del plano.
Entra: la zona elegida.
Sale: la zona cambiada (avisa: `table.zone.updated`) o borrada (avisa: `table.zone.deleted`).
Si falla: «Esta zona todavía tiene mesas. Muévelas a otra zona o bórralas antes.» o «Esa zona no
existe en este negocio.».

### TABLE-F07 Crear muchas mesas de golpe
Estado: hecho (asistente y API; sin pantalla, como el producto actual)
Actor: responsable, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente «crea 12 mesas en la Terraza, de la T1 a la T12, para 4».
2. Se crean de una vez (de 1 a 100), numeradas con el prefijo y el número inicial que se digan (1 si
   no), con el aforo (4) y la forma (cuadrada) que se digan, en los primeros huecos libres de la zona.
Entra: zona (por id o por nombre), cuántas, prefijo, número inicial, aforo y forma.
Sale: las mesas (avisa: `table.table.created`).
Si falla: si la zona no existe, no se crea ninguna. Si algún número ya existe en la zona, no se crea
ninguna y se dice cuáles.

### TABLE-F08 Ajustar la sala: comensales al sentar y avisos de tiempo
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En **Mesas → Ajustes**, marca o desmarca «Preguntar los comensales al sentar una mesa».
2. Pon «Aviso ámbar (minutos)» y «Aviso rojo (minutos)» (de 1 a 600; el rojo no puede ser menor que el
   ámbar).
3. Pulsa «Guardar».
4. Desmarcado, tocar una mesa libre la sienta con su aforo (con los comensales de la reserva si está
   Reservada). En **Sesiones**, el tiempo de una cuenta abierta se pone ámbar y rojo a partir de esos
   minutos. Sin guardar nunca: se pregunta, 60 y 90 minutos.
Entra: los tres valores.
Sale: los ajustes de sala (avisa: `table.settings.updated`).
Si falla: un valor fuera de rango sale en su campo.

### TABLE-F09 Ver cómo está la sala
Estado: hecho
Actor: responsable, empleado
Pantalla: Plano de sala
Pasos:
1. Abre **Mesas → Plano de sala** y elige la zona. Se ven todas sus mesas en uso, a su tamaño real.
2. Cada mesa dice su estado escrito, con icono y color: Disponible, Ocupada, Reservada o Bloqueada.
3. Una mesa ocupada dice los comensales y los minutos que llevan («3 pax · 35 min») y quién la
   atiende; los minutos avanzan solos. Una mesa con reserva hoy dice el nombre y la hora.
4. El plano cambia solo cuando alguien sienta, traslada, junta, divide, cobra o anula: no hay que
   salir y volver. Y con el reloj: una mesa pasa a Reservada una hora antes de su reserva y vuelve a
   Disponible cuando la reserva acaba, sin que nadie toque nada.
Entra: las mesas, sus cuentas abiertas, sus retenciones y el estado de sus cuentas en Ventas.
Sale: nada.
Si falla: un fallo al cargar sale con «Reintentar».

### TABLE-F10 Sentar a un grupo en una mesa libre o reservada
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En **Plano de sala → Servicio**, toca una mesa Disponible o Reservada. Se pregunta «Comensales en
   la mesa N», con el aforo (o los comensales de la reserva) ya puesto.
2. Toca un atajo del 1 al 8 (sienta de un toque) o ajusta con «−» y «+» y pulsa «Sentar N». Más que el
   aforo avisa «Supera el aforo de la mesa (4)» y deja sentar. Con el ajuste de comensales apagado,
   «Sentar» sienta con el aforo.
3. Si quieres, antes de sentar «Asignar cliente» le pone la ficha a la cuenta (TABLE-F32).
4. La mesa pasa a Ocupada y en Ventas nace su cuenta abierta con el título «Mesa N» (la ve **Cuentas
   abiertas** del TPV). Quien sienta es el camarero de la cuenta.
Entra: la mesa y los comensales; en una Reservada, los comensales de la reserva.
Sale: la cuenta de mesa abierta con sus comensales, la hora y el camarero (avisa:
`table.session.opened`); su cuenta en Ventas (avisa: `sale.order.opened`); las reservas retenidas en
esa mesa que ya estaban Reservadas, gastadas (TABLE-F28).
Si falla: si otro dispositivo la acaba de ocupar, «Otro dispositivo acaba de ocupar esa mesa. Se ha
actualizado el plano.» y la mesa no se sienta. **Dos camareros que sientan la misma mesa a la vez
dejan una sola cuenta**: el segundo recibe ese mismo aviso. Una mesa bloqueada, desactivada o borrada
no se sienta.

### TABLE-F11 Volver a una mesa ocupada y cobrarla
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En **Plano de sala → Servicio**, toca una mesa Ocupada: se abre su ventana con comensales, desde
   cuándo, camarero y cliente.
2. **Cobrar** lleva a **Ventas → Vender** con esa cuenta en pantalla (`/sale/pos?order=<id>`); allí se
   añaden rondas y se cobra.
3. Con dos cuentas en la mesa (dividida), se elige primero la cuenta («Cuenta 1», «Cuenta 2»).
Entra: la mesa tocada y su cuenta abierta.
Sale: nada en Mesas.
Si falla: si la cuenta ya se cobró o anuló desde otro sitio, Ventas avisa al llegar «Esa cuenta ya no
está abierta (se cobró, se anuló o no existe): el TPV sigue como estaba.».

### TABLE-F12 Llevar a una mesa una cuenta que ya está abierta
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Ventas → Vender («Elegir mesa», SALE-F19); asistente
Pasos:
1. En **Ventas → Vender**, con una cuenta en pantalla (de barra, con sus rondas), toca el botón de mesa
   de la cabecera de la cuenta («Asignar mesa»; solo con Mesas activa y permiso de sentar): se abre
   «Elegir mesa», con un buscador y las mesas en servicio del color de su estado, sus plazas y, si la
   tienen, la reserva de hoy («Marta · 21:00»).
2. Toca una mesa Disponible o Reservada: la cuenta pasa a ser la de esa mesa, con todo lo que tenía, y
   toma el título «Mesa 4». No se preguntan los comensales: los de la reserva y, si no hay, las plazas
   de la mesa. Sin cuenta aún, Mesas abre una con el título de la mesa y el TPV la pone en pantalla
   (TABLE-F10).
3. La cabecera de la cuenta enseña su mesa («Mesa 4»), seguida en vivo. En la misma ventana, «Quitar de
   la mesa» la aparca (TABLE-F13), y una cuenta aparcada se vuelve a sentar tocando otra mesa
   (TABLE-F24).
4. Con el asistente: «pon la cuenta de Ana en la mesa 4».
Entra: la cuenta (abierta) y la mesa.
Sale: la cuenta de mesa abierta y enlazada a esa cuenta (avisa: `table.session.opened`).
Si falla: los de TABLE-F10, dentro de la ventana y con estas palabras; una cuenta ya cobrada o anulada:
«Esa cuenta ya no está abierta en Ventas.»; una cuenta que ya está en otra mesa: «Esa cuenta ya está
en la mesa N.». Las mesas Ocupadas y Bloqueadas no se pueden tocar.

### TABLE-F13 Quitar la mesa de una cuenta (aparcarla)
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio); también en Ventas → Vender, «Elegir mesa» → «Quitar de la mesa» (SALE-F19)
Pasos:
1. En la ventana de la mesa ocupada pulsa «Quitar mesa».
2. La mesa queda Disponible para otros; la cuenta de mesa pasa a «Aparcada», sin mesa, conservando
   comensales, camarero y hora; la cuenta sigue abierta en Ventas (**Cuentas abiertas**).
3. Para seguir con ella en una mesa, **Sesiones → Volver a sentar** (TABLE-F24).
Entra: la cuenta de mesa.
Sale: la cuenta aparcada (avisa: `table.session.parked`) y la mesa libre si no le queda otra cuenta. Si
luego Ventas la cobra entera o la anula, la cuenta de mesa queda «Cerrada» (sin mesa).
Si falla: «Esa cuenta no está abierta: no existe en este negocio, o ya se ha cerrado, trasladado,
fusionado o aparcado.».

### TABLE-F14 Corregir los comensales de una mesa ocupada
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En la ventana de la mesa ocupada pulsa «Comensales».
2. Sale la pregunta con los comensales actuales; cámbialos con un atajo o con «−» / «+» y «Guardar».
3. La mesa enseña los comensales nuevos. En una mesa dividida se corrige la cuenta elegida.
Entra: la cuenta abierta de la mesa.
Sale: los comensales de la cuenta (avisa: `table.session.updated`).
Si falla: una cuenta ya cerrada, trasladada, fusionada o aparcada no se corrige (mensaje de
TABLE-F13). Siempre al menos 1.

### TABLE-F15 Pasar la cuenta a otra mesa (transferir)
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En la ventana de la mesa ocupada pulsa «Transferir».
2. El plano dice «Transferir N a…» y «Elige una mesa libre»: solo se pueden tocar las Disponibles y
   Reservadas. «Cancelar» lo deshace.
3. Toca la mesa de destino.
4. La cuenta es la misma, ahora en la mesa de destino, con sus comensales, su camarero, sus notas, su
   hora de llegada y su título nuevo en Ventas («Mesa M»); la de origen queda libre si no le queda otra
   cuenta, y la de destino, Ocupada (si estaba Reservada, gasta la reserva).
Entra: la cuenta de origen y la mesa de destino.
Sale: la cuenta de origen «Trasladada» y una cuenta de mesa nueva en el destino con la misma cuenta
de Ventas (avisa: `table.session.transferred`).
Si falla: «Otro dispositivo acaba de ocupar esa mesa. Se ha actualizado el plano.» si el destino ya no
está libre; «Esa cuenta no está abierta…» si otro ya la movió.

### TABLE-F16 Juntar las cuentas de dos mesas ocupadas (fusionar)
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En la ventana de la mesa que se va a juntar pulsa «Fusionar».
2. El plano dice «Fusionar N con…» y «Elige una mesa ocupada»: solo se pueden tocar las Ocupadas (la
   propia mesa solo si tiene otra cuenta: así se deshace una división).
3. Toca la mesa que se queda.
4. La mesa de origen queda libre si no le queda otra cuenta y su cuenta de mesa, «Fusionada». En
   Ventas, las líneas sin cobrar de la cuenta de origen pasan a la de la mesa que se queda y la vacía
   queda anulada, **en la misma operación**: o se junta todo, o no se junta nada. Lo que la cuenta de
   origen ya había cobrado sigue en su «Cobrado».
Entra: las dos cuentas.
Sale: una sola cuenta abierta en la mesa que se queda (avisa: `table.session.merged` y
`sale.order.merged`).
Si falla: «Esa mesa no tiene ninguna cuenta abierta con la que fusionar.» si el destino está libre o
es la misma mesa.

### TABLE-F17 Dividir la cuenta de una mesa
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En la ventana de la mesa ocupada pulsa «Dividir cuenta».
2. Marca las líneas que se van a la cuenta nueva (las de su cuenta en Ventas) y pulsa «Dividir». Sin
   nada marcado, la nueva nace vacía.
3. Mesas abre una segunda cuenta en la misma mesa (1 comensal) y Ventas le pasa las líneas marcadas,
   en la misma operación. Cobrar una cierra solo esa: la mesa sigue Ocupada con la otra. Se puede
   dividir aunque la mesa esté bloqueada o desactivada: no se sienta a nadie nuevo.
Entra: la cuenta abierta de la mesa y las líneas que se mueven.
Sale: dos cuentas de mesa abiertas en la misma mesa, la nueva colgando de la original (avisa:
`table.session.split` y `sale.order.opened`).
Si falla: si otro dispositivo está cobrando esa cuenta, Ventas lo rechaza («La cuenta ha cambiado…»)
y no se divide nada.

### TABLE-F18 Liberar la mesa al cobrar la cuenta entera
Estado: hecho
Actor: sistema
Pantalla: Ventas: Cobro
Pasos:
1. En Ventas se cobra la cuenta de una mesa, entera o en partes.
2. Lo cobrado sale en «Cobrado» de **Sesiones**, también en cada cobro parcial.
3. Cobrada entera, la cuenta de mesa queda «Cerrada» y la mesa libre si no le queda otra cuenta
   abierta; en una mesa dividida la otra cuenta sigue sentada.
4. Con un cobro parcial la cuenta sigue abierta y la mesa, Ocupada.
Entra: de Ventas, el estado de la cuenta y sus ventas.
Sale: la cuenta de mesa «Cerrada» con la hora del cobro; la mesa libre. Una venta sin mesa (barra,
para llevar) no deja nada.
Si falla: nada que ver: el plano y Sesiones lo leen de Ventas en cada lectura.

### TABLE-F19 Anular un cobro de una mesa
Estado: hecho
Actor: sistema
Pantalla: Ventas: Ventas
Pasos:
1. En Ventas, un responsable anula una venta cobrada que era de una mesa.
2. Mesas deja de contarla en «Cobrado» (sale «—» si no queda ningún cobro vivo).
3. La cuenta de mesa y la mesa no cambian: anular una venta no reabre ni cierra la cuenta en Ventas.
Entra: de Ventas, la venta anulada.
Sale: nada nuevo; «Cobrado» baja.
Si falla: como TABLE-F18.

### TABLE-F20 Eliminar en Ventas la cuenta abierta de una mesa
Estado: hecho
Actor: responsable
Pantalla: Ventas: Cuentas abiertas
Pasos:
1. En **Ventas → Cuentas abiertas** se elimina la cuenta de una mesa.
2. La cuenta de mesa queda «Cerrada» y la mesa libre si no le queda otra cuenta.
Entra: de Ventas, la cuenta anulada.
Sale: la cuenta de mesa cerrada; la mesa libre.
Si falla: como TABLE-F18.

### TABLE-F21 Cerrar una mesa a mano
Estado: hecho
Actor: empleado, responsable
Pantalla: Sesiones, Plano de sala (Servicio)
Pasos:
1. En **Mesas → Sesiones → Abiertas**, «Cerrar sesión» (o «Cerrar mesa» en la ventana de la mesa).
2. Confirma en «¿Cerrar la sesión?»: «Mesa N · N comensales. La mesa queda libre y la sesión pasa al
   histórico. Si su cuenta sigue abierta en Ventas, primero cóbrala, pásala a otra mesa o elimínala
   desde el TPV.».
3. Si su cuenta de Ventas está vacía (nadie pidió nada), Mesas la anula y cierra la mesa: un grupo que
   se levanta sin pedir no necesita a un responsable.
4. Si su cuenta tiene algo pedido, no se cierra nada: se cobra (TABLE-F18), se pasa a otra mesa
   (TABLE-F15) o se elimina en Ventas (TABLE-F20).
Entra: la cuenta de mesa abierta y el estado de su cuenta en Ventas.
Sale: la cuenta de mesa «Cerrada» con su hora (avisa: `table.session.closed`).
Si falla: «La cuenta de esta mesa sigue abierta en Ventas: cóbrala, pásala a otra mesa o elimínala
desde el TPV.»; «La cuenta de esta mesa ha cambiado. Recarga la lista e inténtalo de nuevo.» (otro
dispositivo le cambió la cuenta); «Esa cuenta no está abierta…» (ya la cerró otro).

### TABLE-F22 Consultar las cuentas de la sala (abiertas y cerradas)
Estado: hecho
Actor: responsable, empleado
Pantalla: Sesiones
Pasos:
1. Abre **Mesas → Sesiones**: arranca en «Abiertas», las más recientes primero.
2. «Cerradas» enseña las cerradas con «Cobrado» y «Cierre»; «Todas», también las trasladadas,
   fusionadas y aparcadas.
3. Filtra por zona, camarero o estado, o busca por número de mesa.
4. «Detalle» enseña zona, camarero, estado, comensales, apertura, cierre, tiempo, cobrado y notas.
Entra: las cuentas de mesa y lo cobrado en Ventas.
Sale: nada.
Si falla: el error de la tabla con reintento. Las devoluciones no restan del «Cobrado».

### TABLE-F23 Borrar una cuenta cerrada del historial
Estado: hecho
Actor: administrador, asistente
Pantalla: Sesiones
Pasos:
1. En **Sesiones → Cerradas** (o **Todas**), «Borrar» en una cuenta terminada y confírmalo.
2. Desaparece de **Sesiones**; queda guardada como borrada y su recorrido por las mesas se conserva.
Entra: la cuenta de mesa.
Sale: la cuenta borrada (avisa: `table.session.deleted`).
Si falla: una cuenta abierta o aparcada no se borra: «Esa cuenta sigue abierta: ciérrala antes de
borrarla.».

### TABLE-F24 Volver a sentar una cuenta aparcada
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Sesiones; también en Ventas → Vender, tocando una mesa en «Elegir mesa» con la cuenta en pantalla (SALE-F19)
Pasos:
1. En **Sesiones → Todas**, «Volver a sentar» en una cuenta aparcada y elige una mesa libre.
2. La cuenta de mesa vuelve a «Abierta» en esa mesa, con sus comensales, su camarero y su hora de
   apertura, y su cuenta de Ventas toma el título de la mesa; la mesa pasa a Ocupada y, si estaba
   Reservada, gasta la reserva.
Entra: la cuenta aparcada y la mesa.
Sale: la cuenta de mesa sentada (avisa: `table.session.restored`).
Si falla: «Esa cuenta no está aparcada: no existe en este negocio, o ya está sentada en una mesa.»; la
mesa tiene que estar libre como al sentar (TABLE-F10).

### TABLE-F25 Retener la mesa de una reserva confirmada
Estado: servidor hecho — la reacción existe; la dispara Reservas cuando exista (fase 2)
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Reservas, una reserva con mesa pasa a Confirmada.
2. Mesas aparta esa mesa para la reserva desde su fecha y hora (del negocio) hasta que acaba su
   duración (120 minutos si no trae), con sus comensales, su nombre y su ficha de cliente.
3. Desde 60 minutos antes de su hora la mesa sale Reservada; antes, Disponible con «Ana · 21:00».
4. Una mesa puede tener varias reservas retenidas; el plano enseña la más temprana de hoy.
Entra: de Reservas, la reserva con su mesa, fecha, hora, duración, comensales, nombre y ficha.
Sale: la retención (avisa: `table.table.held`). Si la confirmación llega dos veces, sigue habiendo una
sola retención.
Si falla: una mesa borrada o desactivada no se retiene.

### TABLE-F26 Mover o soltar la retención cuando cambia la reserva
Estado: servidor hecho — espera a Reservas (fase 2)
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Reservas se cambia la mesa, la fecha, la hora, la duración, los comensales o el nombre de una
   reserva retenida.
2. Mesas mueve la retención a la mesa nueva y a la hora nueva; si a la reserva se le quita la mesa,
   suelta la retención.
Entra: de Reservas, la reserva cambiada.
Sale: la retención movida o soltada (avisa: `table.table.held` o `table.table.hold_released`).
Si falla: una mesa nueva borrada o desactivada no recibe la retención y la reserva sigue retenida en
la vieja.

### TABLE-F27 Soltar la mesa cuando la reserva se cancela o no se presenta
Estado: servidor hecho — espera a Reservas (fase 2)
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Reservas, una reserva se cancela, se marca como no presentada o se borra.
2. Mesas suelta su retención (sin el nombre): la mesa vuelve a Disponible si no tiene otra reserva ni
   gente sentada.
3. Una retención que ya se gastó (la gente se sentó) no se toca.
Entra: de Reservas, la reserva cancelada, no presentada o borrada.
Sale: la retención soltada (avisa: `table.table.hold_released`).
Si falla: si el aviso se repite, no cambia nada.

### TABLE-F28 Gastar la retención al sentar a la reserva
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. Llega el grupo de la reserva: la mesa está Reservada. Tócala; la pregunta de comensales viene con
   los de la reserva. Pulsa «Sentar N» (TABLE-F10).
2. La mesa pasa a Ocupada y su retención queda gastada. Trasladar o dividir una cuenta a esa mesa, o
   volver a sentar allí una aparcada, también la gasta.
3. Sentar a otro grupo en esa mesa horas antes de la reserva (la mesa aún Disponible) **no** gasta la
   reserva de la noche.
Entra: la mesa Reservada.
Sale: las retenciones que la pintaban Reservada, gastadas y sin nombre.
Si falla: los de TABLE-F10.

### TABLE-F29 Caducar las retenciones vencidas
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una retención cuya ventana ya pasó deja de pintar la mesa en el mismo momento (se compara con la
   hora real, con su zona).
2. Cada hora, Mesas las marca como caducadas y les borra el nombre.
Entra: la hora.
Sale: las retenciones caducadas, sin nombre (avisa: `table.table.hold_released`, solo si caducó
alguna).
Si falla: se repite en el siguiente repaso; si el hub estuvo parado, hace uno solo al volver.

### TABLE-F30 Retener o soltar una mesa a mano
Estado: hecho (asistente y API, como el producto actual)
Actor: responsable, empleado, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente apartar una mesa («guarda la 6 para Pedro de 21:00 a 23:00, 4 personas»).
2. Desde una hora antes la mesa sale Reservada, con el nombre y la hora; pedirlo otra vez con la misma
   referencia cambia la misma retención.
3. Para soltarla, pide soltarla con la misma referencia.
Entra: mesa, referencia, desde, hasta, comensales y nombre.
Sale: la retención (avisa: `table.table.held`) o su liberación, que borra el nombre (avisa:
`table.table.hold_released`).
Si falla: «Esa mesa no existe en este negocio.»; soltar una retención que ya no está: «Esa retención
ya no está: se soltó, ha vencido, o esa reserva nunca llegó a retener una mesa.».

### TABLE-F31 Olvidar el nombre de un cliente cuyos datos se borran (RGPD)
Estado: servidor hecho — la reacción existe; la entrega el relay del outbox (fase 2)
Actor: sistema
Pantalla: Plano de sala
Pasos:
1. En **Clientes** se borran los datos personales de una ficha.
2. Todas las retenciones de mesa de esa clienta, vivas o terminadas, se quedan sin su nombre.
3. La mesa sigue apartada a su hora: donde estaba el nombre se lee «Cliente borrado · 21:00».
Entra: el aviso `customer.customer.erased` con el id de la ficha.
Sale: retenciones sin el nombre de la clienta. No suelta ninguna mesa.
Si falla: repetirlo no cambia nada; un aviso sin id no toca las retenciones sin ficha.

### TABLE-F32 Poner o quitar el cliente de una mesa
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. Al sentar, o en la ventana de una mesa ocupada, pulsa «Asignar cliente» y busca la ficha por
   nombre o teléfono (el buscador de Clientes, el mismo del TPV).
2. La cuenta de la mesa queda con esa ficha: Ventas la recupera al cobrar. «Quitar cliente» la suelta.
3. El asistente también puede sentar con cliente: «sienta a Ana García en la mesa 4, somos 3».
Entra: la ficha, de Clientes.
Sale: el enlace cuenta ↔ cliente, que guarda Clientes (avisa: `customer.order.linked`).
Si falla: el motivo de Clientes; la mesa se sienta igual.

## Mesas: lo que entra y lo que sale

Todo se puede pedir por las pantallas, por el asistente (por voz o por texto, con la sesión de la
propia persona) y por la API, con las mismas reglas y los mismos permisos. Pensado para la voz: una
mesa se nombra por su id o por su número («mesa 4»), con la zona si el número se repite («la 4 de la
terraza»); una zona por su id o por su nombre; un cliente por su id, su nombre o su teléfono. Si un
nombre casa con varios, se rechaza diciendo cuáles (409 `*_ambiguous`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las zonas con sus mesas y las libres, búsqueda, filtros, orden y páginas (hasta 100) | ver zonas | F01, F06 | `table.zone.list` |
| Una zona | ver zonas | F06 | `table.zone.get` |
| Las mesas con su estado vivo (comensales, desde cuándo, camarero, cliente, reserva), en orden natural, con búsqueda, filtros y páginas | ver mesas | F02, F09 | `table.table.list` |
| Una mesa con sus cuentas abiertas | ver mesas | F09–F17 | `table.table.get` |
| Las cuentas de la sala (abiertas, cerradas, todas), con cobrado, filtros y páginas | ver cuentas | F22 | `table.session.list` |
| Una cuenta de mesa | ver cuentas | F21, F22 | `table.session.get` |
| Las cuentas de mesa de una cuenta de Ventas (para Cocina y Ventas) | ver cuentas | F18 | `table.session.by_order` |
| Los camareros que han abierto cuentas (para el filtro) | ver cuentas | F22 | `table.waiter.list` |
| Si el plano está montado (mesas en uso) | ver mesas | F02 | `table.floor.status` |
| Los ajustes de sala | ver ajustes | F08 | `table.settings.get` |

Las zonas, las mesas, las cuentas, los camareros, el estado del plano y los ajustes se pueden seguir
en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea, cambia y borra zonas | crear / cambiar / borrar zonas | F01, F06 | `table.zone.create`, `.update`, `.delete` |
| Crea una mesa, muchas de golpe, la cambia, la mueve o la borra | crear / cambiar / borrar mesas | F02–F07 | `table.table.create`, `.bulk_create`, `.update`, `.move`, `.delete` |
| Sienta un grupo en una mesa (con una cuenta nueva o una ya abierta, y su cliente) | abrir cuentas | F10, F12, F32 | `table.session.open` |
| Cierra a mano una cuenta de mesa | cambiar cuentas | F21 | `table.session.close` |
| Pasa una cuenta a otra mesa | trasladar cuentas | F15 | `table.session.transfer` |
| Junta la cuenta de una mesa con la de otra | trasladar cuentas | F16 | `table.session.merge` |
| Divide la cuenta de una mesa | cambiar cuentas | F17 | `table.session.split` |
| Corrige los comensales | cambiar cuentas | F14 | `table.session.set_guests` |
| Quita la mesa a una cuenta (aparcar) y la vuelve a sentar | cambiar cuentas | F13, F24 | `table.session.park`, `.restore` |
| Enlaza una cuenta de Ventas a la cuenta de una mesa | abrir cuentas | F12 | `table.session.link_order` |
| Borra una cuenta terminada del historial | borrar cuentas | F23 | `table.session.delete` |
| Retiene o suelta una mesa a mano | cambiar cuentas | F30 | `table.hold.place`, `.release` |
| Guarda los ajustes de sala | ajustes | F08 | `table.settings.update` |

Solo para la plataforma (sin ruta en la API, como sistema): `table.session.close_by_order` (reacción
a Ventas), `table.hold.expire` (tarea programada), `table.hold.sync_reservation` y
`table.hold.move_reservation` (reacciones a Reservas) y `table.hold.forget_customer` (reacción a
Clientes).

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `table.zone.created`, `.updated`, `.deleted` | Crear, cambiar o borrar una zona | `id` |
| `table.table.created`, `.updated`, `.deleted` | Crear (también de golpe), cambiar, mover o borrar una mesa | `id` (`ids` de golpe) |
| `table.table.held`, `table.table.hold_released` | Retener o soltar una mesa (también al caducar) | `table_id`, `source`, `source_ref` |
| `table.session.opened` | Sentar | `id`, `table_id`, `order_id`, `guests_count` |
| `table.session.closed` | Cerrar a mano o por Ventas | `id`, `table_id`, `order_id` |
| `table.session.transferred` | Transferir | `id` (la nueva), `from_id`, `from_table_id`, `table_id`, `order_id` |
| `table.session.merged` | Fusionar | `id`, `into_id`, `table_id`, `order_id` |
| `table.session.split` | Dividir | `id` (la nueva), `from_id`, `table_id`, `order_id` |
| `table.session.updated` | Comensales o cuenta enlazada | `id` |
| `table.session.parked`, `table.session.restored` | Aparcar, volver a sentar | `id`, `table_id` |
| `table.session.deleted` | Borrar del historial | `id` |
| `table.settings.updated` | Guardar los ajustes | los campos cambiados |

Ningún aviso lleva nombres ni notas libres: solo ids y números.

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| `sale.order.completed` | Ventas | Cierra las cuentas de mesa de esa cuenta (F18) | `table.session.close_by_order` |
| `sale.order.voided` | Ventas | Cierra las cuentas de mesa de esa cuenta (F20) | `table.session.close_by_order` |
| `customer.customer.erased` | Clientes | Borra el nombre de sus retenciones (F31) | `table.hold.forget_customer` |
| `reservation.reservation.status_changed` | Reservas (cuando exista) | Retiene, suelta o gasta (F25, F27) | `table.hold.sync_reservation` |
| `reservation.reservation.updated` | Reservas (cuando exista) | Mueve o suelta la retención (F26) | `table.hold.move_reservation` |

Mientras no hay relay (fase 1), lo que dice Ventas se lee además en cada lectura y en cada escritura:
una cuenta de mesa cuya cuenta de Ventas está cobrada o anulada se pinta y se trata como cerrada.

Carga que esperan las reacciones (de cada aviso se lee solo esto; lo demás se ignora):

- `sale.order.completed`, `sale.order.voided`: `order_id`.
- `customer.customer.erased`: `id` (la ficha).
- `reservation.reservation.status_changed`: `id` (la reserva), `status` (`confirmed` retiene;
  `cancelled`, `no_show` o `deleted` sueltan), `table_id`, `date` y `time` (de pared, del negocio),
  `duration_minutes` (120 si no viene), `party_size`, `guest_name` y `customer_id`.
- `reservation.reservation.updated`: `id` y los campos que cambiaron, con los mismos nombres; `table_id`
  enviado vacío (`null`) = la reserva se quedó sin mesa.

### Lo que necesita de otras apps

- **Ventas** (requisito): abre la cuenta de cada mesa (`sale.order.open`), le pone el título
  (`sale.order.set_label`), la divide (`sale.order.split`), la junta (`sale.order.merge`) y anula la
  cuenta vacía de una mesa que se cierra (`sale.order.void`), siempre llamando a sus operaciones con la
  sesión de quien está en la sala y en la misma transacción. Lee de sus modelos el estado de cada
  cuenta, sus líneas y lo cobrado.
- **Clientes** (requisito): el cliente de la cuenta (`customer.order.link`, su modelo `OrderLink` para
  pintarlo) y la búsqueda por nombre o teléfono (`find_customer`).

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Ventas | «Elegir mesa» del TPV (SALE-F19): las mesas y su estado, sentar o volver a sentar la cuenta de pantalla, quitarle la mesa y seguir la mesa de una cuenta | `table.table.list`, `table.floor.status`, `table.session.open`, `table.session.restore`, `table.session.park`, `table.session.by_order` |
| Cocina | La mesa de una comanda | `table.session.by_order` |
| Reservas | Retener la mesa de una reserva | sus avisos |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver zonas | sí | sí | sí | sí | `table.view_zone` |
| Crear zonas | sí | sí | sí | no | `table.add_zone` |
| Cambiar zonas | sí | sí | sí | no | `table.change_zone` |
| Borrar zonas | sí | sí | no | no | `table.delete_zone` |
| Ver mesas | sí | sí | sí | sí | `table.view_table` |
| Crear mesas | sí | sí | sí | no | `table.add_table` |
| Cambiar y mover mesas | sí | sí | sí | no | `table.change_table` |
| Borrar mesas | sí | sí | no | no | `table.delete_table` |
| Ver cuentas de mesa | sí | sí | sí | sí | `table.view_session` |
| Sentar (abrir cuentas) | sí | sí | sí | sí | `table.add_session` |
| Cambiar cuentas (cerrar, dividir, comensales, aparcar, retener) | sí | sí | sí | sí | `table.change_session` |
| Trasladar y fusionar cuentas | sí | sí | sí | sí | `table.transfer_session` |
| Borrar cuentas del historial | sí | sí | no | no | `table.delete_session` |
| Ver ajustes | sí | sí | sí | sí | `table.view_settings` |
| Cambiar ajustes | sí | sí | no | no | `table.manage_settings` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado. Sentar, dividir y juntar piden además «Montar la cuenta» de
Ventas (`sale.add_sale`), que tienen los cuatro papeles.

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `queries.py`,
  `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `tests/test_integration_sale.py` (Ventas y Clientes reales)
  y `tests/test_concurrency.py` (dos camareros a la vez, con hilos).
- **`requires = ["sale", "customer"]`**: la cuenta de cada mesa es una `sale.Order` (guardada como
  `order_id`, UUID sin clave ajena, como Citas), y su estado, sus líneas y sus ventas se leen de los
  modelos de Ventas; el cliente de la cuenta se lee de `customer.OrderLink`. **Ventas no requiere
  Mesas**: no sabe nada de mesas, solo de títulos.
- **Modelos**: `Zone`, `Table` (número único por zona sin distinguir mayúsculas ni espacios entre las
  no borradas, también sin zona: `nulls_distinct=False`), `TableSession` (la cuenta de mesa:
  `open` → `closed` | `transferred` | `merged` | `parked`; aparcada ⇔ sin mesa; una cuenta de Ventas
  en una sola cuenta de mesa abierta o aparcada, por restricción única), `SessionMove` (el recorrido de
  cada cuenta por las mesas: un tramo vivo por cuenta, con el motivo de inicio y el de fin), `Hold` (la
  retención: única por `(source, source_ref)`, con `held_from` y `held_until` con zona) y
  `TableSettings` (una fila). Borrados lógicos (`is_deleted`) en zonas, mesas y cuentas.
- **El estado de una mesa no se guarda: se calcula al leer** — Ocupada si tiene una cuenta viva
  (abierta y con su cuenta de Ventas abierta, o sin cuenta de Ventas); si no, Bloqueada si lo está;
  si no, Reservada si tiene una retención viva que ya entró en su ventana (60 minutos antes de
  `held_from`, hasta `held_until`); si no, Disponible. Lo único que se guarda es `blocked`. Así no
  hay «liberar si no le queda otra cuenta» ni repaso que repinte, y una reserva vencida deja de pintar
  en el acto (el defecto de 1–2 horas de TABLES-F29 desaparece).
- **Sin relay en la fase 1** (como Caja): lo que hace Ventas (cobrar, anular la cuenta) no llega por
  aviso. Las lecturas tratan como cerrada una cuenta de mesa abierta **o aparcada** cuya `sale.Order`
  está `completed` o `voided`, con la hora de cierre de la cuenta; las escrituras, antes de nada,
  cierran esas cuentas (`settle`). `events.REACTIONS` hace lo mismo cuando llegue el relay. Una cuenta
  que acaba aparcada se cierra sin mesa (restricción `table_session_table_by_status`).
- **El paso del tiempo** (una reserva que entra en su ventana o acaba) no tiene aviso: el plano pinta el
  estado por el reloj (cada 30 s) y, cuando lo cambia, vuelve a pedir el plano al servidor.
- **Concurrencia**: sentar, trasladar, volver a sentar y dividir bloquean la fila de la mesa
  (`select_for_update`) antes de comprobar que sigue libre; dos camareros sobre la misma mesa van en
  fila y el segundo recibe `table.table_not_available`. Fusionar bloquea las dos mesas en orden de id
  (sin interbloqueos). Cerrar, comensales, aparcar y borrar bloquean la cuenta de mesa. Traer una
  cuenta de Ventas a una mesa bloquea antes esa cuenta (dos mesas a la vez: la segunda recibe
  `table.order_elsewhere`); dos zonas con el mismo nombre a la vez dan 409 `table.zone_name_taken`, y
  dos primeros guardados de los ajustes a la vez acaban los dos en la única fila. Nunca un 500.
- **Cliente al sentar** (TABLE-F32): si Clientes no puede poner la ficha (no existe, varias casan, sin
  permiso), la mesa se sienta igual y la respuesta lleva `customer_id` vacío; la ventana lo dice.
- **Fusionar** conserva en la cuenta de mesa fusionada su cuenta de Ventas (anulada) cuando las dos
  tenían una: lo que ya había cobrado sigue en su «Cobrado».
- **Con Ventas, en la misma transacción**: sentar abre la cuenta de Ventas (`sale.order.open`, título
  «Mesa N» en el idioma de quien sienta) o retitula la que se trae; trasladar y volver a sentar
  retitulan; fusionar llama a `sale.order.merge`; dividir a `sale.order.split`. Si Ventas rechaza, se
  deshace todo. Ventas inactiva o ausente → 409 `table.sale_unavailable`.
- **Cerrar a mano una mesa cuya cuenta de Ventas está vacía** (sin líneas ni cobros) la anula con
  `sale.order.void` con la sesión de quien cierra: Ventas deja anular una cuenta vacía a quien monta
  cuentas (`sale.add_sale`), sin `sale.void_sale`. Mesas nunca amplía los permisos de nadie.
- **Hora del negocio**: fase 1, `settings.TIME_ZONE` (Europe/Madrid); las retenciones de Reservas
  traen fecha y hora de pared y se guardan con esa zona. «Hoy» en el plano es el día del negocio.
- **Asistente**: cada operación declara `ai` (descripción; `risk: "high"` en cerrar, trasladar,
  fusionar, borrar zonas, mesas y cuentas) y cada campo de `schemas.py` su `description`.
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17): zonas, mesas, cuentas de mesa,
  recorrido, retenciones y ajustes; ids y fechas en solo lectura. Lo que guarda no pasa por las
  operaciones ni deja aviso.
- **Tarea programada**: `expire_table_holds` (`table.hold.expire`, cada hora, en UTC, `collapse`); hecho — la
  corre el worker (`base/scheduler.py`, 2026-10-15; en la fase 1, sobre un solo hub).

### Cambios frente al producto actual

1. **Se sienta también desde el plano de sala** (modo Servicio), además de desde «Elegir mesa» del TPV,
   y sentar abre ya la cuenta de Ventas con el título de la mesa (antes se sentaba solo desde el TPV y
   la cuenta nacía con el primer artículo).
2. **El plano es vivo** (antes no cambiaba al sentar ni al cobrar).
3. **Juntar y dividir hacen las dos partes en una sola operación** (antes Mesas juntaba o dividía y
   luego el TPV movía las líneas; si fallaba, quedaban desparejadas).
4. **El estado de la mesa se calcula** y el campo «Estado» de «Editar mesa» solo ofrece Disponible o
   Bloqueada (antes dejaba poner Ocupada o Reservada a mano sin ninguna cuenta).
5. **Reservada solo desde una hora antes** de la reserva, y sentar antes no la gasta (duda 1, por
   mercado); la retención vence a su hora exacta (antes 1–2 horas tarde, TABLES-F29).
6. **Mesas y zonas desactivadas salen del servicio** (duda 7, por mercado).
7. **El número de mesa es único en su zona por cualquier puerta** (duda 6; antes solo lo comprobaba el
   plano) y el nombre de zona, también.
8. **Dos camareros a la vez sobre la misma mesa dejan una sola cuenta** (antes podían entrar las dos).
9. **Eliminar la cuenta en Ventas libera la mesa** (TABLES-F20, antes no hecho).
10. **Cerrar una mesa con su cuenta vacía la cierra** sin pedir a un responsable que anule la cuenta.
11. **Volver a sentar una cuenta aparcada tiene pantalla** (Sesiones) y comprueba que la mesa está
    libre (antes aceptaba una mesa ocupada, bloqueada, borrada o de otro negocio).
12. **Borrar una cuenta del historial tiene pantalla** (Sesiones, solo el administrador).
13. **Con dos cuentas en una mesa, se elige cuál** al cobrar, transferir, fusionar o corregir (antes se
    cogía una sin elegir).
14. **Una zona con mesas (activas o no) no se borra** (antes las desactivadas se quedaban sin zona).
15. **El rojo no puede ser menor que el ámbar** en los ajustes.
16. **Lo cobrado se lee de Ventas** en vez de apuntarlo en un libro propio: mismo resultado, sin
    avisos que perder.
17. **El camarero se copia al sentar** (su nombre, como Caja guarda quién abre), en vez de buscarlo en
    la lista de personas cada vez que se pinta.
18. **El cliente de la mesa** (TABLE-F32) es nuevo: el producto actual solo lo ponía desde el TPV.
19. **El repaso de retenciones** corre cada hora y solo avisa si caducó alguna (antes cada 15 minutos
    y avisaba siempre).
20. **Una cuenta trasladada conserva su hora de llegada** (antes el traslado ponía el reloj a cero).
21. **La lista Mesas edita y borra por fila** (antes solo se editaba y borraba en el plano) y borrar
    una mesa pide confirmación (antes no la pedía).
22. **Una división se deshace fusionando** las dos cuentas de la misma mesa (antes no se podía).
23. **Una cuenta aparcada que Ventas cobra o anula se cierra** (antes se quedaba «Aparcada» para
    siempre).
24. **Fusionar no pierde lo cobrado** por la cuenta de origen antes de juntarla.

### Lo que NO hace, a propósito

- No sabe qué se ha pedido: líneas, importes y cocina son de Ventas y Cocina.
- No impide sentar más comensales que el aforo: avisa.
- No toma reservas: eso es Reservas; Mesas solo aparta la mesa en el plano.
- No tiene asiento por comensal, cursos, estado «por limpiar» (duda 2) ni mesas físicas unidas con
  aforo sumado (duda 3): no entran en el MVP, como en el producto actual.
- No guarda planos distintos por turno.
- No deja elegir ni cambiar el camarero de una cuenta (duda 8): es quien la sienta.

### Lo que queda fuera

- **La entrega de los avisos de otras apps** (relay del outbox, fase 2): las reacciones están
  declaradas y probadas; mientras, Mesas lee el estado de Ventas en cada lectura y escritura.
- **Reservas**: la app no existe todavía; las reacciones de TABLE-F25 a F27 esperan sus avisos con
  la carga documentada arriba.

### Dudas abiertas

Resueltas en esta versión: 1 (por mercado, «Referencia adoptada»), 5 (Volver a sentar y elegir la
cuenta de una mesa dividida tienen pantalla; deshacer una división se hace fusionando), 6, 7 (por
mercado). Siguen fuera del MVP: 2 («por limpiar»), 3 (mesas unidas) y 8 (cambiar el camarero).
