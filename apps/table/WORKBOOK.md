# Workbook — Mesas (app)
Prefijo: TABLE
Alcance MVP: restaurante
Estado de la app: completa (2026-10-21)
Lo que no entra todavía: ver «Lo que queda fuera».

> Manual de usuario y especificación de la app `table`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas).

## Para qué sirve y para quién

Mesas es el plano de tu local y de sus zonas, como el salón, la terraza o la barra. De un vistazo ves
qué mesa está libre, ocupada o reservada y cuánto tiempo lleva sentado cada grupo. Tocas una mesa
libre para sentar a un grupo y una ocupada para abrir su cuenta, pedir más o cobrarla; manteniéndola
pulsada, pasas su cuenta a otra mesa, la juntas con otra o la divides.

### En detalle

Mesas es el **plano del restaurante o del bar**: las zonas del local (salón, terraza, barra), las
mesas de cada zona con su aforo, su forma y su sitio en el plano, y las **cuentas que hay sentadas en
cada mesa**. Dice, en vivo, qué mesa está libre, ocupada, reservada o fuera de servicio, cuántos
comensales hay, desde cuándo y quién la atiende, y sabe qué cuenta de Ventas está en qué mesa.

### Quién la usa y qué hace cada uno

- El **responsable** de sala dibuja el plano: crea zonas y mesas, las coloca arrastrándolas y cambia
  su aforo, su forma o su estado.
- El **administrador** y el **propietario**, además, borran mesas, zonas y cuentas del historial y
  cambian los ajustes de sala.
- El **empleado** (camarero, cajero) sienta a la gente, pasa una cuenta a otra mesa, junta o divide
  cuentas, corrige los comensales, quita la mesa a una cuenta y cierra una mesa a mano.

### Lo que no hace

Mesas no cobra (eso es Ventas: la mesa lleva al TPV con su cuenta), no apunta reservas (eso es
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
  la cuenta (Toast, Square, Lightspeed y Odoo).
- **Sentar en una mesa reservada está permitido y gasta la reserva; superar el aforo avisa pero no
  impide.**
- **La mesa reservada se pinta Reservada solo cerca de la hora de su reserva** (decisión de mercado).
  Antes de eso la mesa sigue Disponible y enseña la próxima reserva
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
  antes, la mesa sigue Disponible con «Ana · 21:00». **Por qué no desde que se confirma** (aunque sea
  dentro de una semana): bloquearía la mesa todo el servicio y un grupo sentado a mediodía «gastaría» la
  reserva de la noche.
- **Una mesa o una zona desactivada sale del servicio** (decisión de mercado): no se pinta en el
  plano de servicio ni se puede sentar; sigue en «Editar plano», en **Mesas** y en **Zonas**, como
  [Lightspeed — desactivar una mesa](https://k-series-support.lightspeedhq.com/hc/articles/1260804656729),
  [Toast — quitar una mesa del área de servicio](https://support.toasttab.com/article/Creating-Service-Areas-and-Table-Setup-1493049150430)
  y el estado Activa / Inactiva de los planos de [Poster](https://knowledge-base.joinposter.com/en/how-to-edit-a-table-layout-or-hide-the-floor-plan)
  y [MultiPOS](https://docs.devdiggers.com/multipos-point-of-sale-for-woocommerce/configuration/tables/).
- **La mesa cuya cuenta se ha impreso se marca «Cuenta pedida» hasta que se cobra** (decisión de mercado):
  al imprimir la cuenta para la mesa, la mesa cambia de color en el plano, como en
  [Lightspeed K-Series](https://k-series-support.lightspeedhq.com/hc/en-us/articles/360050328494-Understanding-the-Floor-Plan-screen),
  [SumUp POS Pro](https://help.sumup.com/en-GB/pos/articles/75000023480-table-plan-what-is-the-meaning-of-the-colours-associated-to-any-table-)
  e [iMPOS](https://knowledge.impos.com.au/hc/en-us/articles/210213528-Table-and-Meal-Status), y vuelve a su
  color al cobrarla, como en [Lightspeed L-Series](https://resto-support.lightspeedhq.com/hc/en-us/articles/226306187-Understanding-table-status).
  Ninguno de los consultados dice que la marca se quite al añadir líneas o al volver a imprimir.

## Antes de empezar

- Mesas necesita **Ventas** (la cuenta de cada mesa es una cuenta abierta de Ventas) y **Clientes**
  (el cliente de una mesa y el olvido de su nombre). Se encienden con ella y no se apagan mientras
  Mesas esté encendida.
- Las horas (apertura, cierre, reservas) son las del negocio, en su zona horaria.

Configuración inicial, paso a paso:

1. En **Mesas → Zonas** (o con el «+» del **Plano de sala**) crea las zonas del local (TABLE-F01).
2. En **Mesas → Plano de sala**, en «Editar plano», con el «+» añade las mesas de cada zona (TABLE-F02).
   Hasta que haya una mesa en uso, el Inicio te lo recuerda con «Tus mesas».
3. Arrástralas hasta que el plano se parezca a la sala y ajusta en cada una su aforo y su forma
   (TABLE-F03, TABLE-F04).
4. En **Mesas → Ajustes** (solo el administrador) decide si al sentar se preguntan los comensales y a
   partir de cuántos minutos una cuenta abierta se pone ámbar y roja (TABLE-F08).
5. En **Plano de sala**, «Servicio», toca una mesa libre y siéntala: se abre su cuenta en Ventas.

## Pantallas

El menú **Mesas** tiene cinco pestañas: **Plano de sala**, **Zonas**, **Mesas**, **Sesiones** y
**Ajustes**. **Zonas** y **Mesas** solo salen a quien puede cambiarlas, y **Ajustes**, a quien puede
cambiarlos; los botones que el perfil no puede usar no salen.

### Plano de sala
Aquí ves de un vistazo cómo está la sala: cada mesa en su sitio, con su color y, si está ocupada, el
tiempo que lleva el grupo sentado. En **Servicio** tocas una mesa libre para sentar a un grupo y una
ocupada para abrir su cuenta, pedir más o cobrarla; manteniendo pulsada una mesa, pasas la cuenta a otra
mesa, la juntas con otra o la divides. En **Editar plano** colocas las mesas arrastrándolas y añades zonas
y mesas.

El color de cada mesa dice cómo está:

- **Verde**, Disponible: está libre y se puede sentar.
- **Rellena del color principal** (azul de serie), Ocupada: hay un grupo sentado con su cuenta abierta.
- **Amarilla**, Reservada: su reserva empieza dentro de una hora o ya ha empezado.
- **Gris a rayas**, Bloqueada: está fuera de servicio y no se puede sentar.

#### Detalle
Menú **Mesas → Plano de sala**. Arriba, la tira de zonas (se desliza de lado en el móvil y se difumina
por el borde cuando hay más zonas), el conmutador **Servicio / Editar plano** (solo a quien puede dibujar
el plano) y, en «Editar plano», un «+» («Añadir zona o mesa») y un lápiz («Editar zona»). Cada pestaña
lleva un punto del color de su zona y el número de mesas ocupadas sobre las que están en servicio
(«7/12»). Debajo, una tarjeta resume la zona elegida: libres, ocupadas, reservadas y comensales.

En tableta y ordenador, el plano encuadra las mesas de la zona, de la primera a la última aunque estén lejos
de la esquina del plano, y ajusta solo su sitio y su tamaño para enseñarlas todas sin que dejen de leerse;
«Editar plano» lo enseña desde su esquina, para poder colocar una mesa en cualquier sitio. Si aun así no
cabe, se desplaza dentro de su recuadro, de lado y de arriba abajo,
con un fundido en cada borde que tenga mesas detrás; el fondo se arrastra con el ratón y, con el plano
seleccionado, las flechas del teclado lo desplazan. No hay botones de zoom. La cuadrícula solo sale en
«Editar plano». En el teléfono, «Servicio» enseña las mesas en tarjetas a dos columnas, cada una con el
dibujo de la mesa y sus sillas, el número, el estado y la hora; «Editar plano» sigue siendo el plano.

Cada mesa tiene su forma (redonda, cuadrada o rectangular) y sillas según su aforo; las sillas llenas son
los comensales sentados. Se dibujan doce sillas como mucho: con más aforo, las llenas se reparten en
proporción, y la cifra exacta siempre va escrita. Dentro de la mesa van su número en grande y un dato: el
tiempo que lleva ocupada («1:08»), la hora en una reservada o el estado en las demás. Debajo, el estado
escrito con su icono, los comensales («3/4 pax») o el aforo, y el nombre y la hora de la reserva
(«Ana · 21:00»; «Cliente borrado» si se borraron los datos de esa clienta). Quién atiende una mesa
ocupada se ve en su ventana.

El color de cada mesa dice su estado:

- **Verde**, Disponible: fondo verde suave y borde verde. Está libre y se puede sentar.
- **Rellena de color**, Ocupada: la mesa entera del color principal de la «Paleta de tema» (azul con la
  paleta ERPlora). Hay un grupo sentado con su cuenta abierta.
- **Amarilla**, Reservada: fondo amarillo suave y borde amarillo discontinuo. Su reserva empieza dentro de
  una hora o ya ha empezado.
- **Gris a rayas**, Bloqueada: está fuera de servicio y no se puede sentar hasta que se desbloquee.

En una mesa ocupada, el tiempo lleva además un arco que avanza. Al pasar los minutos de «Aviso ámbar
(minutos)» de los Ajustes, el tiempo y el arco se ponen ámbar, y al pasar los de «Aviso rojo (minutos)»,
rojos; la mesa no cambia de color. Los cambios de estado y de zona se animan con suavidad, salvo si el dispositivo pide menos
movimiento. Mientras carga, se ve la silueta del plano. El plano **es vivo**: cambia solo cuando alguien
sienta, cobra, mueve o edita una mesa. Tiene dos modos:

- **Servicio** (de entrada): no se arrastra. Tocar una mesa ocupada abre su cuenta en **Ventas → Vender**,
  lista para añadir platos o cobrarla; con dos cuentas en la mesa, se elige primero cuál («Cuenta 1»,
  «Cuenta 2»). Tocar una mesa libre, reservada o bloqueada, o mantener pulsada cualquier mesa (en el
  ordenador, clic derecho), abre su ventana **Mesa N**. Debajo, la ayuda «Toca una mesa para sentarla o
  abrir su cuenta · mantenla pulsada (o haz clic derecho) para transferir, fusionar y más.».
  - libre o reservada: la pregunta de comensales («Comensales en la mesa N · 4 pax», «−» y «+», atajos
    del 1 al 8 que sientan de un toque, el aviso «Supera el aforo de la mesa (4)» y «Sentar N»), y el
    cliente opcional («Asignar cliente»). Con el ajuste de comensales apagado, «Sentar» sienta con el
    aforo (o los comensales de la reserva).
  - ocupada: comensales, desde cuándo, quién atiende, el cliente de la cuenta (asignar o quitar) y
    las acciones **Transferir**, **Fusionar**, **Dividir cuenta**, **Comensales**, **Quitar mesa** y
    **Cerrar mesa**. Con dos cuentas en la mesa, se elige primero cuál («Cuenta 1», «Cuenta 2»).
  - bloqueada: «Mesa fuera de servicio: no se puede sentar hasta que se desbloquee.».
  - Transferir y Fusionar ponen el plano en modo destino: «Transferir N a…» / «Elige una mesa libre»
    (o «Fusionar N con…» / «Elige una mesa ocupada») y «Cancelar»; solo se pueden tocar las mesas que
    valen.
- **Editar plano**: se arrastra cada mesa a su sitio (también con el teclado: cada flecha la mueve un
  poco y, con Mayúsculas, cuatro veces más) y se guarda al soltar. Tocar una mesa abre **Editar mesa**
  (Número, Aforo, Ancho, Alto, Nombre (opcional), Forma, Estado (Disponible o Bloqueada), Zona, Activa;
  pie con «Borrar» y «Guardar»); el «+» abre **Añadir** (campo Zona y «Añadir zona»; campo «Número de
  mesa», que si se deja vacío «Se numera sola», y «Añadir mesa»); el lápiz abre **Editar zona** (Nombre, Descripción
  (opcional); «Borrar zona» y «Guardar»). Debajo, la ayuda «Arrastra para colocar · toca una mesa
  para editarla o borrarla. Los cambios se guardan al momento.». En «Editar plano» se ven también las
  mesas y zonas desactivadas, en gris.

Las ventanas tapan toda la pantalla en el móvil y van centradas en tableta y ordenador.

### Zonas
Aquí creas y ordenas las zonas del local, como la sala, la terraza o la barra, cada una con su color.
Las zonas son las pestañas que salen arriba en el **Plano de sala**, y aquí ves cuántas mesas tiene cada
una y cuántas están libres ahora. Con el «+» añades una zona y, desde su fila, cambias su nombre, su
color o su orden.

#### Detalle
Menú **Mesas → Zonas**. Tabla: Nombre (con su color), Mesas, Libres («libres / total»), Orden,
Estado (Activa, Inactiva); buscador «Buscar zona…», filtros por columna tras el embudo, vista tabla o
tarjetas. El «+» (solo a quien puede crear zonas) abre el panel con Nombre, Descripción, Color (Azul,
Cian, Morado, Verde, Ámbar, Rojo, Gris), Orden y «Añadir zona»; por fila «Editar» (el mismo panel con
el interruptor «Activa» y «Guardar cambios») y «Borrar» (solo el administrador), que pide confirmación
en «¿Borrar la zona?» y deja «Borrar zona» apagado si la zona tiene mesas.

### Mesas
Aquí tienes todas las mesas del local en una lista, con su número, su zona, su aforo y su estado. Sirve
para buscar una mesa, añadir mesas nuevas con el «+» o cambiar sus datos con **Editar** sin pasar por el
plano. Una mesa nueva aparece en el primer hueco libre de su zona; para llevarla a su sitio, usa
**Editar plano** en el **Plano de sala**.

#### Detalle
Menú **Mesas → Mesas**. Tabla en orden natural (la 2 antes que la 10): Número, Nombre, Zona, Aforo,
Estado; buscador «Buscar mesa…» (número y nombre), filtros por columna tras el embudo (zona, estado,
forma, aforo), vista tabla o tarjetas. El «+» abre el panel con Número, Aforo, Ancho, Alto, Zona y
«Añadir mesa». Por fila, «Editar» (Número, Nombre, Aforo, Ancho, Alto, Forma, Zona, Estado y Activa) y
«Borrar» (solo el administrador, con confirmación).

### Sesiones
Aquí ves las cuentas de la sala, las abiertas y las ya cerradas, con su mesa, quién atiende, los
comensales y el tiempo que llevan. Desde cada fila miras el **Detalle** de una cuenta, cierras una que se
quedó abierta o, con **Volver a sentar**, llevas a una mesa libre una cuenta que se quedó sin mesa.

#### Detalle
Menú **Mesas → Sesiones**: las cuentas de la sala. Pestañas «Abiertas», «Cerradas» y «Todas». Tabla:
Mesa («Sin mesa (aparcada)» si no tiene), Cobrado y Cierre (no salen en Abiertas), Zona, Camarero,
Comensales, Apertura, Tiempo, Estado (Abierta, Cerrada, Trasladada, Fusionada, Aparcada); el tiempo de
una cuenta abierta se pone ámbar y rojo según los Ajustes. Vista tabla o tarjetas: la tarjeta lleva de título la
mesa («Mesa 4»), el estado en su etiqueta y, debajo, cada otro dato con el icono de su columna delante, sin
repetir la mesa; la apertura y el cierre llevan cada uno el suyo, así que dos horas iguales no se confunden. Buscador «Buscar mesa…», filtros tras el
embudo por zona, camarero y estado. Por fila «Detalle» (ventana con zona, camarero, estado, comensales, apertura,
cierre, tiempo, cobrado y notas), en las abiertas «Cerrar sesión» (con confirmación), en las aparcadas
«Volver a sentar» (elige la mesa libre) y, en las terminadas, «Borrar» (solo el administrador). Las
horas van en la hora del negocio. Lo cobrado va en la moneda en que se cobró: la del negocio (la de su
país, con sus decimales), nunca en euros si el negocio cobra en otra.

### Ajustes
Aquí decides cómo trabaja la sala: si al sentar una mesa se preguntan los comensales y a los cuántos
minutos el tiempo de una mesa ocupada se pone ámbar y, después, rojo. Si no se preguntan, la mesa se
sienta con su aforo. Cambia lo que necesites y pulsa **Guardar**: vale para todo el negocio, en todos
los aparatos.

#### Detalle
Menú **Mesas → Ajustes**: «Preguntar los comensales al sentar una mesa», «Aviso ámbar (minutos)» y
«Aviso rojo (minutos)», y «Guardar». Solo la ve quien puede cambiarlos (de fábrica, el propietario y el
administrador).

## Estados de cada pantalla

| Pantalla | Cargando | Vacío | Error |
|---|---|---|---|
| Plano de sala | Esqueleto del plano | Sin zonas: «Crea una zona para empezar a colocar mesas.»; zona sin mesas: «Sin mesas en esta zona. Pulsa «Añadir mesa».» | Al cargar: aviso con «Reintentar»; al guardar, dentro de la ventana abierta (o encima del plano si no hay ninguna) |
| Zonas | La tabla en carga | «No hay zonas. Pulsa «+» para crear la primera (Salón, Terraza, Barra…).» | El de la tabla con «Reintentar»; el de guardar, dentro del panel |
| Mesas | La tabla en carga | «Sin mesas.» | El de la tabla con «Reintentar»; el de guardar, dentro del panel |
| Sesiones | La tabla en carga | «No hay sesiones. Sienta a un grupo desde el plano y aparecerá aquí.» | El de la tabla con «Reintentar»; el de cerrar, en su confirmación |
| Ajustes | «Cargando…» | — | Por campo (422) y encima del formulario |

En todas: «Reconectando…» mientras se recupera la conexión en vivo (lo pintado se queda), «Esta app
no está activa en este negocio» y «No tienes permiso».

## Cambios sin guardar en Android

En las ventanas de alta y edición de esta app, el botón atrás del móvil pregunta «¿Descartar los cambios?»
cuando hay algo escrito o elegido sin guardar: «Seguir editando» conserva lo tecleado y «Descartar cambios»
cierra la ventana sin guardarlo. Con la ventana como se abrió, atrás la cierra sin preguntar (BASE-F05).

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TABLE-F01 | Crear y ordenar las zonas del local | hecho |
| TABLE-F02 | Añadir mesas | hecho |
| TABLE-F03 | Colocar las mesas en el plano | hecho |
| TABLE-F04 | Editar o borrar una mesa | hecho |
| TABLE-F05 | Sacar una mesa del servicio (bloquearla) y devolverla | hecho |
| TABLE-F06 | Renombrar o borrar una zona | hecho |
| TABLE-F07 | Crear muchas mesas de golpe | hecho |
| TABLE-F08 | Ajustar la sala: comensales al sentar y avisos de tiempo | hecho |
| TABLE-F09 | Ver cómo está la sala | hecho |
| TABLE-F10 | Sentar a un grupo en una mesa libre o reservada | hecho |
| TABLE-F11 | Volver a una mesa ocupada para pedir más o cobrarla | hecho |
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
| TABLE-F25 | Retener la mesa de una reserva confirmada | hecho |
| TABLE-F26 | Mover o soltar la retención cuando cambia la reserva | hecho |
| TABLE-F27 | Soltar la mesa cuando la reserva se cancela o no se presenta | hecho |
| TABLE-F28 | Sentar al grupo de una reserva | hecho |
| TABLE-F29 | Caducar las retenciones vencidas | hecho |
| TABLE-F30 | Retener o soltar una mesa a mano | hecho |
| TABLE-F31 | Olvidar el nombre de un cliente cuyos datos se borran (RGPD) | hecho |
| TABLE-F32 | Poner o quitar el cliente de una mesa | hecho |
| TABLE-F33 | Ver cuánto lleva cada mesa | hecho |
| TABLE-F34 | Ver qué mesas han pedido la cuenta | hecho |

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
ese nombre.». El motivo de un campo sale debajo de él y se quita en cuanto se corrige ese campo. Un
empleado no ve el «+»; si lo pide por la API, se rechaza por permiso.
Implicados: TABLE-F06, TABLE-F09

### TABLE-F02 Añadir mesas
Estado: hecho
Actor: responsable, administrador
Pantalla: Inicio, Plano de sala (Editar plano), Mesas
Pasos:
1. En el **Inicio**, mientras no haya ninguna mesa en uso, «Termina de configurar tu negocio» trae
   «Tus mesas» («Añade las mesas de tu sala: sin ellas no hay comanda por mesa, ni dividir ni
   transferir.»), «Recomendado», a quien puede crear mesas. «Configurar» lleva a **Mesas → Mesas**
   (paso 6).
2. En **Plano de sala → Editar plano**, elige la zona y pulsa «+».
3. En «Número de mesa» escribe el número o nombre (S1, Terraza A) o déjalo vacío: «Se numera sola»
   con el primer número libre de esa zona.
4. Pulsa «Añadir mesa» (apagado mientras no haya ninguna zona).
5. La mesa aparece en la zona, en el primer hueco libre, cuadrada, para 4 y Disponible.
6. Otra forma: en **Mesas → Mesas**, «+» con Número, Aforo, Ancho y Alto (vacíos, «Estándar»: la mesa
   de siempre, 72 × 72) y Zona y «Añadir mesa»; también nace en el primer hueco libre de su zona, del
   tamaño que tenga.
Entra: número (o ninguno), y en la lista también aforo, ancho, alto y zona.
Sale: la mesa (avisa: `table.table.created`). Con una mesa en uso, «Elegir mesa» del TPV deja de decir
«Aún no hay mesas. Créalas en Mesas → Plano de sala.» (`table.floor.status`), y «Tus mesas» queda
«Hecho» en el Inicio sin recargar. Una mesa ocupada o bloqueada sigue contando; si se apagan o se borran
todas (TABLE-F04), el paso vuelve a pendiente solo. Una zona sin mesas no lo da por hecho.
Si falla: número repetido en la zona (sin distinguir mayúsculas ni espacios), se añada desde donde se
añada: «Ya hay una mesa con ese número en esta zona.». Zona borrada mientras tanto: «Esa zona no existe
en este negocio.». En la ventana de **Mesas**, el motivo de un campo sale debajo de él y se quita en
cuanto se corrige ese campo.
Implicados: TABLE-F03, TABLE-F04, TABLE-F07, BASE-F01

### TABLE-F03 Colocar las mesas en el plano
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano)
Pasos:
1. En **Plano de sala → Editar plano**, elige la zona.
2. Arrastra cada mesa a su sitio (el gesto lo coge solo la mesa; deslizar sobre el plano vacío lo
   desplaza). Con teclado: tabula hasta la mesa y muévela con las flechas, a pasos cortos; con
   Mayúsculas, a pasos cuatro veces más largos.
3. Al soltar se guarda al momento. La mesa no sale del borde del plano.
4. Al recargar, cada mesa sigue donde se dejó.
Entra: la posición nueva.
Sale: la posición de la mesa (avisa: `table.table.updated`).
Si falla: «No se pudo guardar la posición» encima del plano; la mesa vuelve a su sitio guardado.
Implicados: TABLE-F02, TABLE-F09

### TABLE-F04 Editar o borrar una mesa
Estado: hecho
Actor: responsable, administrador
Pantalla: Plano de sala (Editar plano), Mesas
Pasos:
1. En **Editar plano**, toca la mesa (o en **Mesas**, «Editar» en su fila): se abre «Editar mesa».
2. Cambia Número, Aforo, Ancho y Alto (el tamaño de su caja en el plano, de 24 a 10000; la mesa de
   siempre mide 72 × 72: una larga para ocho, 160 × 72), Nombre (opcional), Forma (Cuadrada, Redonda,
   Rectangular), Estado (Disponible o Bloqueada), Zona o Activa.
3. Pulsa «Guardar»: la ventana se cierra y el plano cambia solo (si cambió de zona, aparece en la otra
   pestaña en el mismo sitio; con otro tamaño, se pinta en su sitio con su caja nueva).
4. Para quitarla, pulsa «Borrar» (solo el administrador) y confírmalo: desaparece del plano y de la
   lista; su historia de cuentas se conserva.
Entra: la mesa elegida.
Sale: la mesa cambiada (avisa: `table.table.updated`) o borrada (avisa: `table.table.deleted`).
Si falla: dentro de la ventana: «El número de mesa es obligatorio», «Ya hay una mesa con ese número
en esta zona.», «Esa mesa no existe en este negocio.», un ancho o un alto fuera de 24 a 10000 («Debe
ser mayor o igual que 24.», «Debe ser menor o igual que 10000.») o con decimales («Introduce un número
entero.»), y entonces no se guarda nada; cada motivo bajo su campo hasta que se corrige ese campo;
borrar una mesa con cuenta abierta: «Esa mesa tiene una cuenta abierta. Ciérrala o trasládala antes de
borrar la mesa.».
Implicados: TABLE-F02, TABLE-F05, TABLE-F21

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
   Bloqueada. Una mesa Bloqueada no sale Reservada aunque tenga una reserva.
Entra: la mesa elegida.
Sale: el estado de la mesa (avisa: `table.table.updated`).
Si falla: los mismos avisos que al editar una mesa. Sentar en una mesa bloqueada, también desde el
asistente o la API, se rechaza con el mismo aviso de mesa fuera de servicio.
Implicados: TABLE-F04, TABLE-F10, TABLE-F25

### TABLE-F06 Renombrar o borrar una zona
Estado: hecho
Actor: responsable, administrador
Pantalla: Zonas, Plano de sala (Editar plano)
Pasos:
1. En **Mesas → Zonas**, «Editar»: cambia Nombre, Descripción, Color, Orden o «Activa» y pulsa
   «Guardar cambios». En el plano, el lápiz («Editar zona») cambia Nombre y Descripción.
2. Para borrarla (solo el administrador): «Borrar» abre «¿Borrar la zona?» con «N mesas en esta zona.
   Una zona con mesas no se puede borrar: mueve o borra antes sus mesas.» (con una sola, «1 mesa en esta
   zona. … muévela o bórrala antes.»); con mesas, «Borrar zona» sale apagado.
3. Sin mesas, «Borrar zona» la quita de la lista y del plano.
Entra: la zona elegida.
Sale: la zona cambiada (avisa: `table.zone.updated`) o borrada (avisa: `table.zone.deleted`).
Si falla: «Esta zona todavía tiene mesas. Muévelas a otra zona o bórralas antes.» o «Esa zona no
existe en este negocio.». El motivo de un campo sale debajo de él hasta que se corrige ese campo.
Implicados: TABLE-F01, TABLE-F04

### TABLE-F07 Crear muchas mesas de golpe
Estado: hecho
Actor: responsable, asistente
Pantalla: asistente y API
Pasos:
1. Pide al asistente «crea 12 mesas en la Terraza, de la T1 a la T12, para 4».
2. Se crean de una vez (de 1 a 100), numeradas con el prefijo y el número inicial que se digan (1 si
   no), con el aforo (4) y la forma (cuadrada) que se digan, en los primeros huecos libres de la zona.
Entra: zona (por id o por nombre), cuántas, prefijo, número inicial, aforo y forma.
Sale: las mesas (avisa: `table.table.created`).
Si falla: si la zona no existe, no se crea ninguna. Si algún número ya existe en la zona, no se crea
ninguna y se dice cuáles.
Implicados: TABLE-F02

### TABLE-F08 Ajustar la sala: comensales al sentar y avisos de tiempo
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En **Mesas → Ajustes**, marca o desmarca «Preguntar los comensales al sentar una mesa».
2. Pon «Aviso ámbar (minutos)» y «Aviso rojo (minutos)» (de 1 a 600; el rojo no puede ser menor que el
   ámbar).
3. Pulsa «Guardar».
   Lo que se cambia mientras se está guardando no se pierde: se queda en pantalla, por guardar.
4. Desmarcado, tocar una mesa libre la sienta con su aforo (con los comensales de la reserva si está
   Reservada). En **Sesiones**, el tiempo de una cuenta abierta se pone ámbar y rojo a partir de esos
   minutos. Mientras no se guarden, valen los de fábrica: se preguntan los comensales y los avisos
   saltan a los 60 y a los 90 minutos.
Entra: los tres valores.
Sale: los ajustes de sala (avisa: `table.settings.updated`).
Si falla: un valor fuera de rango sale en su campo. El aviso se quita en cuanto se cambia algo y el
motivo de un campo en cuanto se corrige ese campo; los dos vuelven si al guardar otra vez se rechaza.
Un aviso que no es de ningún campo se queda hasta que se vuelve a guardar.
Implicados: TABLE-F10, TABLE-F22

### TABLE-F09 Ver cómo está la sala
Estado: hecho
Actor: responsable, empleado
Pantalla: Plano de sala
Pasos:
1. Abre **Mesas → Plano de sala** y elige la zona: su contenido sale al momento, sin esperar a cargar.
   La pestaña indica cuántas mesas están ocupadas y la tarjeta resume libres, ocupadas, reservadas y
   comensales.
2. En tableta y ordenador el plano encuadra las mesas de la zona, de la primera a la última, y las ajusta
   al espacio; en el teléfono, «Servicio» las muestra en tarjetas a dos columnas. Cada mesa dice su estado
   escrito, con icono, forma, sillas y color: Disponible, Ocupada, Reservada o Bloqueada.
3. Una mesa ocupada enseña el tiempo («0:35») y los comensales («3/4 pax»); el tiempo avanza solo y, al
   pasar los avisos de los Ajustes, solo cambian de color el tiempo y su arco. Una mesa con reserva hoy dice
   el nombre y la hora. Quién la atiende se ve en su ventana: quien atiende su cuenta en Ventas (el chip
   «Atiende» del TPV) o, si nadie lo ha cambiado, quien la sentó, por su nombre o, si su cuenta no tiene,
   por lo que va antes de la @ de su correo, nunca el correo entero.
4. El plano cambia solo cuando alguien sienta, traslada, junta, divide, cobra o anula: no hay que salir y
   volver, y la ventana que tengas abierta (dividir, comensales, cerrar, «Editar mesa») sigue en el paso en
   que estabas, con lo que hayas escrito. Y con el reloj: una mesa pasa a Reservada una hora antes de su
   reserva y vuelve a Disponible cuando la reserva acaba, sin que nadie toque nada.
Entra: las mesas, sus cuentas abiertas, sus retenciones y el estado de sus cuentas en Ventas.
Sale: nada.
Si falla: un fallo al cargar sale con «Reintentar».
Implicados: TABLE-F10, TABLE-F25, TABLE-F29, TABLE-F33, TABLE-F34, SALE-F16, SALE-F19, BASE-F119

### TABLE-F10 Sentar a un grupo en una mesa libre o reservada
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Plano de sala (Servicio); asistente
Pasos:
1. En **Plano de sala → Servicio**, toca una mesa Disponible o Reservada. Se pregunta «Comensales en
   la mesa N», con el aforo (o los comensales de la reserva) ya puesto.
2. Toca un atajo del 1 al 8 (sienta de un toque) o ajusta con «−» y «+» y pulsa «Sentar N». Más que el
   aforo avisa «Supera el aforo de la mesa (4)» y deja sentar. Con el ajuste de comensales apagado,
   «Sentar» sienta con el aforo.
3. Si quieres, antes de sentar «Asignar cliente» le pone la ficha a la cuenta. En una Reservada, si no
   eliges ninguna, la cuenta lleva el cliente de la reserva.
4. La mesa pasa a Ocupada y en Ventas nace su cuenta abierta con el título «Mesa N» (la ve **Cuentas
   abiertas** del TPV). Quien sienta es el camarero de la cuenta: su nombre o, si su cuenta no tiene, lo que
   va antes de la @ de su correo, nunca el correo entero.
5. Con el asistente: «sienta a tres en la mesa 4» (con su zona si el número se repite).
Entra: la mesa y los comensales; en una Reservada, los comensales y el cliente de la reserva.
Sale: la cuenta de mesa abierta con sus comensales, la hora y el camarero (avisa:
`table.session.opened`); su cuenta en Ventas (avisa: `sale.order.opened`), con su cliente si lo hay
(avisa: `customer.order.linked`); las reservas retenidas en esa mesa que ya estaban Reservadas, gastadas
(TABLE-F28; desde Reservas, solo la de esa reserva).
Si falla: si otro dispositivo la acaba de ocupar, «Otro dispositivo acaba de ocupar esa mesa. Se ha
actualizado el plano.» y la mesa no se sienta. **Dos camareros que sientan la misma mesa a la vez
dejan una sola cuenta**: el segundo recibe ese mismo aviso. Una mesa bloqueada, desactivada o borrada
no se sienta. Sentar se hace en la sala, con el grupo delante: una automatización no puede hacerlo.
Implicados: TABLE-F08, TABLE-F28, TABLE-F32, SALE-F19, FLOW-F12, BASE-F119

### TABLE-F11 Volver a una mesa ocupada para pedir más o cobrarla
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En **Plano de sala → Servicio**, toca una mesa Ocupada: se abre su cuenta en **Ventas → Vender**, sin
   ventanas por medio; allí se añaden rondas y se cobra.
2. Con dos cuentas en la mesa (dividida), se elige primero la cuenta («Cuenta 1», «Cuenta 2») y se abre
   esa.
3. Los datos de la mesa (comensales, desde cuándo, camarero y cliente) y sus acciones (transferir,
   fusionar, dividir, corregir los comensales, quitar la mesa y cerrarla) están en su ventana, que se abre
   manteniendo pulsada la mesa (en el ordenador, con el clic derecho).
Entra: la mesa tocada y su cuenta abierta.
Sale: nada en Mesas.
Si falla: si la cuenta ya se cobró o anuló desde otro sitio, Ventas avisa al llegar «Esa cuenta ya no
está abierta (se cobró, se anuló o no existe): el TPV sigue como estaba.».
Implicados: TABLE-F13, TABLE-F14, TABLE-F15, TABLE-F16, TABLE-F17, TABLE-F18, TABLE-F21, TABLE-F32,
SALE-F19

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
en la mesa N.». Las mesas Ocupadas y Bloqueadas no se pueden tocar. Llevar una cuenta a una mesa se
hace con el grupo delante: una automatización no puede hacerlo.
Implicados: TABLE-F10, TABLE-F13, TABLE-F24, SALE-F19, FLOW-F12

### TABLE-F13 Quitar la mesa de una cuenta (aparcarla)
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio); también en Ventas → Vender, «Elegir mesa» → «Quitar de la mesa» (SALE-F19)
Pasos:
1. En el plano, mantén pulsada la mesa ocupada y, en su ventana, pulsa «Quitar mesa».
2. La mesa queda Disponible para otros; la cuenta de mesa pasa a «Aparcada», sin mesa, conservando
   comensales, camarero y hora; la cuenta sigue abierta en Ventas (**Cuentas abiertas**).
3. Para seguir con ella en una mesa, **Sesiones → Volver a sentar**.
Entra: la cuenta de mesa.
Sale: la cuenta aparcada (avisa: `table.session.parked`) y la mesa libre si no le queda otra cuenta. Si
luego Ventas la cobra entera o la anula, la cuenta de mesa queda «Cerrada» (sin mesa).
Si falla: «Esa cuenta no está abierta: no existe en este negocio, o ya se ha cerrado, trasladado,
fusionado o aparcado.».
Implicados: TABLE-F24, SALE-F19

### TABLE-F14 Corregir los comensales de una mesa ocupada
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Plano de sala (Servicio); asistente
Pasos:
1. En el plano, mantén pulsada la mesa ocupada y, en su ventana, pulsa «Comensales».
2. Sale la pregunta con los comensales actuales; cámbialos con un atajo o con «−» / «+» y «Guardar».
3. La mesa enseña los comensales nuevos. En una mesa dividida se corrige la cuenta elegida.
4. Con el asistente: «en la mesa 4 ahora son cinco»; en una mesa dividida, di cuál de sus cuentas.
Entra: la cuenta abierta de la mesa.
Sale: los comensales de la cuenta (avisa: `table.session.updated`).
Si falla: una cuenta ya cerrada, trasladada, fusionada o aparcada no se corrige: sale el mismo aviso
que al quitar la mesa («Esa cuenta no está abierta…»). Siempre queda al menos 1 comensal.
Implicados: TABLE-F10, TABLE-F13, TABLE-F17

### TABLE-F15 Pasar la cuenta a otra mesa (transferir)
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Plano de sala (Servicio); asistente
Pasos:
1. En el plano, mantén pulsada la mesa ocupada y, en su ventana, pulsa «Transferir».
2. El plano dice «Transferir N a…» y «Elige una mesa libre»: solo se pueden tocar las Disponibles y
   Reservadas. «Cancelar» lo deshace.
3. Toca la mesa de destino.
4. La cuenta es la misma, ahora en la mesa de destino, con sus comensales, su camarero, sus notas, su
   hora de llegada y su título nuevo en Ventas («Mesa M»); la de origen queda libre si no le queda otra
   cuenta, y la de destino, Ocupada (si estaba Reservada, su reserva se da por sentada).
5. Con el asistente: «pasa la mesa 4 a la 6».
Entra: la cuenta de origen y la mesa de destino.
Sale: la cuenta de origen «Trasladada» y una cuenta de mesa nueva en el destino con la misma cuenta
de Ventas (avisa: `table.session.transferred`).
Si falla: «Otro dispositivo acaba de ocupar esa mesa. Se ha actualizado el plano.» si el destino ya no
está libre; «Esa cuenta no está abierta…» si otro ya la movió.
Implicados: TABLE-F28, SALE-F25

### TABLE-F16 Juntar las cuentas de dos mesas ocupadas (fusionar)
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. En el plano, mantén pulsada la mesa que se va a juntar y, en su ventana, pulsa «Fusionar».
2. El plano dice «Fusionar N con…» y «Elige una mesa ocupada»: solo se pueden tocar las Ocupadas (la
   propia mesa solo si tiene otra cuenta: así se deshace una división).
3. Toca la mesa que se queda.
4. La mesa de origen queda libre si no le queda otra cuenta y su cuenta de mesa, «Fusionada». En
   Ventas, las líneas sin cobrar de la cuenta de origen pasan a la de la mesa que se queda y la vacía
   queda anulada, **en la misma operación**: o se junta todo, o no se junta nada. Lo que la cuenta de
   origen ya había cobrado sigue en su «Cobrado». El TPV que tenía la cuenta de origen en pantalla (en
   este dispositivo o en otro) pasa a la de la mesa que se queda y avisa «Esa cuenta se ha juntado con
   otra: la pantalla muestra la cuenta juntada.».
Entra: las dos cuentas.
Sale: una sola cuenta abierta en la mesa que se queda (avisa: `table.session.merged` y
`sale.order.merged`).
Si falla: «Esa mesa no tiene ninguna otra cuenta abierta con la que fusionar.» si el destino está libre
o es la misma mesa sin otra cuenta.
Implicados: TABLE-F17, SALE-F24

### TABLE-F17 Dividir la cuenta de una mesa
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Plano de sala (Servicio); asistente
Pasos:
1. En el plano, mantén pulsada la mesa ocupada y, en su ventana, pulsa «Dividir cuenta».
2. Marca las líneas que se van a la cuenta nueva (las de su cuenta en Ventas, cada una con su importe
   en la moneda del negocio) y pulsa «Dividir». Sin nada marcado, la nueva nace vacía.
3. Mesas abre una segunda cuenta en la misma mesa (1 comensal) y Ventas le pasa las líneas marcadas,
   en la misma operación. Cobrar una cierra solo esa: la mesa sigue Ocupada con la otra. Se puede
   dividir aunque la mesa esté bloqueada o desactivada: no se sienta a nadie nuevo.
4. Con el asistente: «divide la cuenta de la mesa 4, pagan por separado» (sin decir líneas, la nueva
   nace vacía).
Entra: la cuenta abierta de la mesa y las líneas que se mueven.
Sale: dos cuentas de mesa abiertas en la misma mesa, la nueva colgando de la original (avisa:
`table.session.split` y `sale.order.opened`).
Si falla: si otro dispositivo está cobrando esa cuenta, Ventas lo rechaza («La cuenta ha cambiado…»)
y no se divide nada. Dividir se hace en la mesa, con el grupo delante: una automatización no puede
hacerlo.
Implicados: TABLE-F16, TABLE-F18, SALE-F23, FLOW-F12

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
Implicados: TABLE-F17, TABLE-F22, SALE-F22

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
Implicados: TABLE-F22, SALE-F30

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
Implicados: TABLE-F21, SALE-F18

### TABLE-F21 Cerrar una mesa a mano
Estado: hecho
Actor: empleado, responsable
Pantalla: Sesiones, Plano de sala (Servicio)
Pasos:
1. En **Mesas → Sesiones → Abiertas**, «Cerrar sesión» (o «Cerrar mesa» en la ventana de la mesa, que se
   abre manteniéndola pulsada en el plano).
2. Confirma en «¿Cerrar la sesión?»: «Mesa N · N comensales. La mesa queda libre y la sesión pasa al
   histórico. Si su cuenta sigue abierta en Ventas, primero cóbrala, pásala a otra mesa o elimínala
   desde el TPV.» (con uno solo, «1 comensal»).
3. Si su cuenta de Ventas está vacía (nadie pidió nada), Mesas la anula y cierra la mesa: un grupo que
   se levanta sin pedir no necesita a un responsable.
4. Si su cuenta tiene algo pedido, no se cierra nada: se cobra, se pasa a otra mesa o se elimina en
   Ventas.
Entra: la cuenta de mesa abierta y el estado de su cuenta en Ventas.
Sale: la cuenta de mesa «Cerrada» con su hora (avisa: `table.session.closed`).
Si falla: «La cuenta de esta mesa sigue abierta en Ventas: cóbrala, pásala a otra mesa o elimínala
desde el TPV.»; «La cuenta de esta mesa ha cambiado. Recarga la lista e inténtalo de nuevo.» (otro
dispositivo le cambió la cuenta); «Esa cuenta no está abierta…» (ya la cerró otro).
Implicados: TABLE-F15, TABLE-F18, TABLE-F20

### TABLE-F22 Consultar las cuentas de la sala (abiertas y cerradas)
Estado: hecho
Actor: responsable, empleado
Pantalla: Sesiones
Pasos:
1. Abre **Mesas → Sesiones**: arranca en «Abiertas», las más recientes primero.
2. «Cerradas» enseña las cerradas con «Cobrado» (en la moneda en que se cobró: la del negocio) y
   «Cierre»; «Todas», también las trasladadas, fusionadas y aparcadas.
3. Filtra por zona, camarero o estado, o busca por número de mesa. El camarero sale por su nombre o, si su
   cuenta no tiene, por lo que va antes de la @ de su correo, también en las cuentas de antes, y no se le
   busca por su correo.
4. «Detalle» enseña zona, camarero, estado, comensales, apertura, cierre, tiempo, cobrado y notas.
Entra: las cuentas de mesa y lo cobrado en Ventas.
Sale: nada.
Si falla: si la lista no carga, sale un aviso con «Reintentar». Las devoluciones no restan del
«Cobrado».
Implicados: TABLE-F18, TABLE-F19, TABLE-F23, BASE-F119

### TABLE-F23 Borrar una cuenta cerrada del historial
Estado: hecho
Actor: administrador, asistente
Pantalla: Sesiones; asistente
Pasos:
1. En **Sesiones → Cerradas** (o **Todas**), «Borrar» en una cuenta terminada y confírmalo.
2. Desaparece de **Sesiones**; queda guardada como borrada y su recorrido por las mesas se conserva.
3. Con el asistente: «borra del historial la cuenta cerrada de la mesa 4»; busca él la cuenta y pide
   confirmación.
Entra: la cuenta de mesa.
Sale: la cuenta borrada (avisa: `table.session.deleted`).
Si falla: una cuenta abierta o aparcada no se borra: «Esa cuenta sigue abierta: ciérrala antes de
borrarla.».
Implicados: TABLE-F22

### TABLE-F24 Volver a sentar una cuenta aparcada
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Sesiones; también en Ventas → Vender, tocando una mesa en «Elegir mesa» con la cuenta en pantalla (SALE-F19)
Pasos:
1. En **Sesiones → Todas**, «Volver a sentar» en una cuenta aparcada y elige una mesa libre.
2. La cuenta de mesa vuelve a «Abierta» en esa mesa, con sus comensales, su camarero y su hora de
   apertura, y su cuenta de Ventas toma el título de la mesa; la mesa pasa a Ocupada y, si estaba
   Reservada, su reserva se da por sentada.
Entra: la cuenta aparcada y la mesa.
Sale: la cuenta de mesa sentada (avisa: `table.session.restored`).
Si falla: «Esa cuenta no está aparcada: no existe en este negocio, o ya está sentada en una mesa.»; la
mesa tiene que estar libre, como al sentar a un grupo, y salen los mismos avisos. Volver a sentar se
hace con el grupo delante: una automatización no puede hacerlo.
Implicados: TABLE-F10, TABLE-F13, TABLE-F28, SALE-F19, FLOW-F12

### TABLE-F25 Retener la mesa de una reserva confirmada
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en el Plano de sala)
Pasos:
1. En Reservas, una reserva con mesa pasa a Confirmada (o nace ya confirmada).
2. En esa misma operación, Mesas aparta esa mesa para la reserva desde su fecha y hora (del negocio) hasta que acaba su
   duración (120 minutos si no trae), con sus comensales, su nombre y su ficha de cliente. La noche del cambio de hora la
   duración es la real: una reserva de 90 minutos aparta la mesa 90 minutos, ni una hora más ni una menos. Una hora que se
   repite (las 02:30 de la noche de octubre) es la primera, aún en horario de verano; una que no existe (las 02:30 de la
   noche de marzo) pasa a las 03:30.
3. Desde 60 minutos antes de su hora la mesa sale Reservada; antes, Disponible con «Ana · 21:00».
4. Una mesa puede tener varias reservas retenidas; el plano enseña la más temprana de hoy.
Entra: de Reservas, la reserva con su mesa, fecha, hora, duración, comensales, nombre y ficha.
Sale: la retención (avisa: `table.table.held`). Si la confirmación llega dos veces, sigue habiendo una
sola retención.
Si falla: una mesa borrada, desactivada o fuera de servicio no se retiene, y Reservas no confirma la reserva
(se deshace todo).
Implicados: RESERVATION-F07, TABLE-F09, TABLE-F28

### TABLE-F26 Mover o soltar la retención cuando cambia la reserva
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en el Plano de sala)
Pasos:
1. En Reservas se cambia la mesa, la fecha, la hora, la duración, los comensales o el nombre de una
   reserva retenida.
2. En esa misma operación, Mesas mueve la retención a la mesa nueva y a la hora nueva, con la misma duración real (también
   la noche del cambio de hora); si a la reserva se le quita la mesa, suelta la retención.
Entra: de Reservas, la reserva cambiada.
Sale: la retención movida o soltada (avisa: `table.table.held` o `table.table.hold_released`).
Si falla: una mesa nueva borrada, desactivada o fuera de servicio no recibe la retención: Reservas no
guarda el cambio y la reserva sigue retenida en la vieja.
Implicados: RESERVATION-F08, TABLE-F25

### TABLE-F27 Soltar la mesa cuando la reserva se cancela o no se presenta
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en el Plano de sala)
Pasos:
1. En Reservas, una reserva se cancela, se marca como no presentada o se borra.
2. En esa misma operación, Mesas suelta su retención (sin el nombre): la mesa vuelve a Disponible si no tiene otra reserva ni
   gente sentada.
3. Una retención que ya se gastó (la gente se sentó) no se toca.
Entra: de Reservas, la reserva cancelada, no presentada o borrada.
Sale: la retención soltada (avisa: `table.table.hold_released`).
Si falla: si se pide dos veces, no cambia nada.
Implicados: RESERVATION-F09, RESERVATION-F10, RESERVATION-F20, TABLE-F25

### TABLE-F28 Sentar al grupo de una reserva
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. Llega el grupo de la reserva: la mesa está Reservada. Tócala; la pregunta de comensales viene con
   los de la reserva. Pulsa «Sentar N», como al sentar a cualquier grupo.
2. La mesa pasa a Ocupada, su cuenta lleva el cliente de la reserva (o el que se elija antes con
   «Asignar cliente»), igual que al sentarla desde Reservas, y la reserva se da por sentada: la mesa ya
   no vuelve a salir Reservada por ella. Pasar o dividir una cuenta a esa mesa, o volver a sentar allí
   una aparcada, también la da por sentada.
3. Sentar a otro grupo en esa mesa horas antes de la reserva (la mesa aún Disponible) **no** da por
   sentada la reserva de la noche.
4. Si se sienta desde Reservas («Sentar» en la reserva), solo cuenta esa reserva: con Ana a las 19:00 y
   Bea a las 21:00 en la mesa 5, sentar a Ana a las 20:10 deja viva la de Bea, y cuando Ana se va la mesa
   vuelve a salir Reservada para Bea. Si Reservas sienta a un grupo más de una hora antes de su reserva,
   la mesa no vuelve a salir Reservada para quien ya se sentó. Desde el plano no se sabe de qué reserva
   es el grupo, y se dan por sentadas todas las que ya tenían la mesa Reservada.
Entra: la mesa Reservada (y, desde Reservas, la reserva que se sienta, RESERVATION-F11).
Sale: la cuenta con el cliente de la reserva; las retenciones que la pintaban Reservada (desde Reservas,
solo la suya), gastadas y sin nombre; una retención que aún no pintaba la mesa, soltada al sentar desde
Reservas.
Si falla: los mismos avisos que al sentar a un grupo en una mesa libre o reservada.
Implicados: RESERVATION-F11, TABLE-F10, TABLE-F25

### TABLE-F29 Caducar las retenciones vencidas
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una retención cuya ventana ya pasó deja de pintar la mesa en el mismo momento (se compara con la
   hora real, con su zona).
2. Cada hora, Mesas las marca como caducadas y les borra el nombre.
Entra: la hora.
Sale: las retenciones caducadas, sin nombre (avisa: `table.table.hold_released` una vez por cada
retención caducada, con su mesa; nada si no caducó ninguna).
Si falla: se repite en el siguiente repaso; si el hub estuvo parado, hace uno solo al volver.
Implicados: TABLE-F09, TABLE-F25

### TABLE-F30 Retener o soltar una mesa a mano
Estado: hecho
Actor: responsable, empleado, asistente
Pantalla: asistente y API
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
Implicados: TABLE-F09, TABLE-F28

### TABLE-F31 Olvidar el nombre de un cliente cuyos datos se borran (RGPD)
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en el Plano de sala)
Pasos:
1. En **Clientes** se borran los datos personales de una ficha (también de las que se le unieron).
2. Al momento, todas las retenciones de mesa de esa clienta, vivas o terminadas, se quedan sin su nombre,
   y la cuenta de una mesa en la que está sentada deja de enseñarlo.
3. La mesa sigue apartada a su hora: donde estaba el nombre se lee «Cliente borrado · 21:00».
Entra: el aviso `customer.customer.erased` con el id de la ficha.
Sale: retenciones sin el nombre de la clienta (avisa: `table.table.held`, y el plano se repinta solo). No
suelta ninguna mesa.
Si falla: repetirlo no cambia nada; un aviso sin id no toca las retenciones sin ficha.
Implicados: CUSTOMER-F16, CUSTOMER-F13, RESERVATION-F22

### TABLE-F32 Poner o quitar el cliente de una mesa
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. Al sentar, o en la ventana de una mesa ocupada (mantenla pulsada en el plano), pulsa «Asignar
   cliente» y busca la ficha por nombre o teléfono (el buscador de Clientes, el mismo del TPV).
2. La cuenta de la mesa queda con esa ficha: Ventas la recupera al cobrar. «Quitar cliente» la suelta.
3. El asistente también puede sentar con cliente: «sienta a Ana García en la mesa 4, somos 3».
4. Si en Clientes se elimina la ficha, la cuenta deja de decir su nombre; si el personal de ERPlora la recupera
   desde la copia aparte, lo vuelve a decir al momento, también en el plano y la sala que estén abiertos.
Entra: la ficha, de Clientes.
Sale: el enlace cuenta ↔ cliente, que guarda Clientes (avisa: `customer.order.linked`).
Si falla: el motivo de Clientes; la mesa se sienta igual.
Implicados: CUSTOMER-F17, CUSTOMER-F19, CUSTOMER-F33, TABLE-F10

### TABLE-F33 Ver cuánto lleva cada mesa
Estado: hecho
Actor: empleado, responsable
Pantalla: Plano de sala (Servicio)
Pasos:
1. Abre **Mesas → Plano de sala**. Cada mesa Ocupada enseña en la etiqueta de debajo, debajo de sus
   comensales, el importe de su cuenta con la moneda del negocio (bajo «Ocupada · 3/4 pax», «42,50 €»), y
   «0,00 €» mientras no se ha pedido nada. Es el mismo importe que esa cuenta enseña en **Cuentas abiertas**
   de Ventas. El lector de pantalla lo dice con la mesa: «Cuenta 42,50 €».
2. Con varias cuentas en la mesa (dividida), enseña la suma de todas.
3. En el teléfono, la tarjeta de cada mesa ocupada lo enseña también, junto al tiempo.
4. Cuando el camarero añade o quita una línea en Ventas, cobra una parte de la cuenta (entonces enseña
   lo que falta por cobrar) o la junta, la divide o la pasa a otra mesa, el importe cambia solo en todos
   los dispositivos que tienen el plano abierto, sin salir y volver.
5. Las mesas Disponibles, Reservadas y Bloqueadas no enseñan importe.
Entra: el importe de cada cuenta abierta de la sala, de Ventas, leído de una vez para todo el plano.
Sale: nada.
Si falla: como el resto del plano, un fallo al cargar sale con «Reintentar».
Implicados: TABLE-F09, TABLE-F15, TABLE-F16, TABLE-F17, TABLE-F34, SALE-F17, SALE-F19, SALE-F22

### TABLE-F34 Ver qué mesas han pedido la cuenta
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Plano de sala (Servicio); asistente
Pasos:
1. En Ventas, con la cuenta de una mesa en pantalla, el camarero imprime la cuenta para llevarla a la mesa
   («Imprimir cuenta»), por la impresora de tiques o por el diálogo de impresión del dispositivo, o se la pide
   al asistente («imprime la cuenta de la mesa 4»).
2. En **Mesas → Plano de sala**, esa mesa pasa a **Cuenta pedida**: su estado escrito, con su icono, dice
   «Cuenta pedida» en lugar de «Ocupada», y la mesa se pinta de un color propio que no se confunde con los de
   los otros estados ni con el ámbar y el rojo del aviso de tiempo. Sigue enseñando el tiempo, los comensales
   y el importe, y en la tarjeta de la zona cuenta como ocupada. En el teléfono, su tarjeta lo dice igual.
3. Con varias cuentas en la mesa (dividida), basta con que se haya impreso la de una.
4. La marca es de la cuenta: si la cuenta pasa a otra mesa, va con ella. Volver a imprimirla, añadir líneas o
   cobrar solo una parte no la quita; se quita cuando esa cuenta se cierra: se cobra entera o se elimina.
5. El cambio sale solo en todos los dispositivos que tienen el plano abierto, sin salir y volver.
6. Por el asistente o la API, cada mesa del plano dice si su cuenta está pedida («¿qué mesas han pedido la
   cuenta?»).
Entra: de Ventas, qué cuentas abiertas de la sala tienen la cuenta impresa, leído de una vez para todo el plano.
Sale: nada en Mesas; Ventas apunta en la cuenta que se imprimió.
Si falla: si la impresión no llega a Ventas (sin conexión), el papel sale igual por el dispositivo y la mesa no
se marca hasta que se vuelva a imprimir; un fallo al cargar el plano sale con «Reintentar».
Implicados: TABLE-F09, TABLE-F15, TABLE-F17, TABLE-F18, TABLE-F20, TABLE-F33, SALE-F21

## Mesas: lo que entra y lo que sale

Todo se puede pedir por las pantallas, por el asistente (por voz o por texto, con la sesión de la
propia persona) y por la API, con las mismas reglas y los mismos permisos. Pensado para la voz: una
mesa se nombra por su id o por su número («mesa 4»), con la zona si el número se repite («la 4 de la
terraza»); una zona por su id o por su nombre; un cliente por su id, su nombre o su teléfono. Si un
nombre casa con varios, se rechaza diciendo cuáles (409 `*_ambiguous`).

Antes de cambiar nada, el asistente pide confirmación y dice por su nombre, nunca por un código, lo que
toca cada cambio: la mesa con su zona, como 5 (Terraza), porque el número se repite entre zonas; la zona;
la cuenta por dónde está (su mesa con su zona, o «Aparcada»); la cuenta de Ventas por su título; el
cliente por su ficha; la reserva por el nombre que pinta en la mesa, y cada línea que se mueve al dividir
por su nombre. Lo que la persona no puede ver (la cuenta de Ventas, sin permiso en Ventas) no sale.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las zonas con sus mesas y las libres, búsqueda, filtros, orden y páginas (hasta 100) | ver zonas | F01, F06 | `table.zone.list` |
| Una zona | ver zonas | F06 | `table.zone.get` |
| Las mesas con su estado vivo (comensales, desde cuándo, camarero, cliente, reserva), en orden natural, con búsqueda, filtros y páginas | ver mesas | F02, F09 | `table.table.list` |
| Una mesa con sus cuentas abiertas y su nombre con la zona, como 5 (Terraza) | ver mesas | F09–F17 | `table.table.get` |
| Las cuentas de la sala (abiertas, cerradas, todas), con cobrado, filtros y páginas | ver cuentas | F22 | `table.session.list` |
| Una cuenta de mesa y dónde está: su mesa con la zona, o «Aparcada» | ver cuentas | F21, F22 | `table.session.get` |
| Las cuentas de mesa de una cuenta de Ventas (para el TPV: la mesa de la cuenta en pantalla) | ver cuentas | F12, F13, F24 | `table.session.by_order` |
| Una línea de la cuenta de Ventas de una mesa, con su nombre y su cantidad, como las lista «Dividir cuenta» | ver cuentas | F17 | `table.session.line` |
| La retención que una reserva tiene en su mesa, mientras la retiene, con el nombre que pinta | ver mesas | F10, F28 | `table.hold.by_reservation` |
| Los camareros que han abierto cuentas (para el filtro) | ver cuentas | F22 | `table.waiter.list` |
| Si el plano está montado (mesas en uso y zonas), para «Elegir mesa» del TPV y el paso «Tus mesas» del Inicio | ver mesas | F02 | `table.floor.status` |
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
`table.hold.move_reservation` (los llama Reservas dentro de su operación) y `table.hold.forget_customer`
(reacción a Clientes).

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `table.zone.created`, `.updated`, `.deleted` | Crear, cambiar o borrar una zona | `id` |
| `table.table.created`, `.updated`, `.deleted` | Crear (también de golpe), cambiar, mover o borrar una mesa | `id` (`ids` de golpe) |
| `table.table.held`, `table.table.hold_released` | Retener o soltar una mesa (también al caducar) u olvidar el nombre de una clienta borrada | `table_id`, `source`, `source_ref` |
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

Las reacciones llegan en segundo plano, poco después, y repetirlas no cambia nada. Lo que dice Ventas se lee
además en cada lectura y en cada escritura: una cuenta de mesa cuya cuenta de Ventas está cobrada o anulada
se pinta y se trata como cerrada. Reservas no se escucha: llama a Mesas dentro de su propia operación (F25 a
F28), y sus avisos, recibidos después, repetirían una reserva tal como era (un «confirmada» viejo volvería a
retener la mesa de un grupo ya sentado).

Carga que esperan las reacciones (de cada aviso se lee solo esto; lo demás se ignora):

- `sale.order.completed`, `sale.order.voided`: `order_id`.
- `customer.customer.erased`: `id` (la ficha).

Lo que Reservas manda al llamar (los mismos nombres que sus avisos `status_changed` y `updated`):

- `table.hold.sync_reservation`: `id` (la reserva), `status` (`confirmed` retiene; `cancelled`, `no_show`
  o `deleted` sueltan), `table_id`, `date` y `time` (de pared, del negocio), `duration_minutes` (120 si no
  viene), `party_size`, `guest_name` y `customer_id`.
- `table.hold.move_reservation`: `id` y los campos que cambiaron; `table_id` enviado vacío (`null`) = la
  reserva se quedó sin mesa.

### Lo que necesita de otras apps

- **Ventas** (requisito): abre la cuenta de cada mesa (`sale.order.open`), le pone el título
  (`sale.order.set_label`), la divide (`sale.order.split`), la junta (`sale.order.merge`) y anula la
  cuenta vacía de una mesa que se cierra (`sale.order.void`), siempre llamando a sus operaciones con la
  sesión de quien está en la sala y en la misma transacción. Lee de sus modelos el estado de cada
  cuenta, sus líneas, quién la atiende y lo cobrado.
- **Clientes** (requisito): el cliente de la cuenta (`customer.order.link`, su modelo `OrderLink` para
  pintarlo) y la búsqueda por nombre o teléfono (`find_customer`).

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Ventas | «Elegir mesa» del TPV (SALE-F19): las mesas y su estado, sentar o volver a sentar la cuenta de pantalla, quitarle la mesa y seguir la mesa de una cuenta | `table.table.list`, `table.floor.status`, `table.session.open`, `table.session.restore`, `table.session.park`, `table.session.by_order` |
| Reservas | Retener, mover y soltar la mesa de una reserva y sentarla, dentro de su operación | `table.hold.sync_reservation`, `table.hold.move_reservation`, `table.hold.release`, `table.session.open` |
| Plataforma (Inicio) | El paso «Tus mesas» de «Termina de configurar tu negocio» (TABLE-F02) | `table.floor.status` |

Cocina no llama a Mesas: la comanda lleva el título de su cuenta, el que Mesas le pone en Ventas («Mesa 4»).
Reservas, además, repinta sus pantallas con los avisos de las mesas y las zonas (`table.table.created`,
`.updated`, `.deleted`, `table.zone.updated`, `.deleted`), y Automatizaciones oye todos los avisos de Mesas,
como los de cualquier app.

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

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).
Sentar, dividir y juntar piden además «Montar la cuenta» de
Ventas (`sale.add_sale`), que tienen todos los papeles menos la gestoría.

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas/`, `queries/`,
  `services/`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `tests/test_integration_sale.py` (Ventas y Clientes reales),
  `tests/test_integration_relay.py` (Reservas, Clientes y Ventas reales, por el bucle del worker con el
  relay del outbox) y `tests/test_concurrency.py` (dos camareros a la vez, con hilos). Reservas → Mesas, sin
  mocks, también en `apps/reservation/tests/test_integration_table.py`.
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
- **Quién sienta una mesa** (BASE-F119): la cuenta de mesa guarda su camarero (`waiter_name`) con `actor_label`
  (`services/writes.py`), que nombra con `actor_name` de `base.queries.people`, la misma pieza que Ventas y Cocina: el
  nombre de la cuenta o, sin él, lo que va antes de la @ de su correo, porque el correo de un compañero solo llega a
  quien ve el contacto del equipo. Las cuentas guardadas antes con un correo las limpió una vez la migración `0003`, en
  la base de datos de cada negocio: así el plano, el detalle, el filtro por camarero (su nombre, su búsqueda y su
  orden), lo vivo y el asistente leen el nombre sin tapar nada al leer.
- **El estado de una mesa no se guarda: se calcula al leer** — Ocupada si tiene una cuenta viva
  (abierta y con su cuenta de Ventas abierta, o sin cuenta de Ventas); si no, Bloqueada si lo está;
  si no, Reservada si tiene una retención viva que ya entró en su ventana (60 minutos antes de
  `held_from`, hasta `held_until`); si no, Disponible. Lo único que se guarda es `blocked`. Así no
  hay «liberar si no le queda otra cuenta» ni repaso que repinte, y una reserva vencida deja de pintar
  en el acto (el defecto de 1–2 horas de TABLES-F29 desaparece).
- **Sentar gasta las retenciones que ya pintan la mesa** (TABLE-F28): `table.session.open` con
  `reservation_id` (opcional; lo manda Reservas al sentar una reserva) gasta solo la retención de esa
  reserva (`source = "reservation"`, `source_ref` = su id) y toma de ella los comensales si no vienen y,
  en una cuenta nueva sin cliente elegido, su cliente (`Hold.customer_id`, con `customer.order.link`);
  sin él (el plano, el TPV), todas las que ya entraron en su ventana. Trasladar, dividir y volver a
  sentar no dicen reserva: gastan todas. Una reserva sentada más de una hora antes de su hora no gasta
  nada (su retención aún no pinta la mesa): Reservas la suelta tras sentarla, con `table.hold.release`
  en la misma operación (`apps/reservation/services.py`, el `seat` de RESERVATION-F11).
- **Relay del outbox** (`base/relay.py`, en el worker): entrega a `events.REACTIONS`
  lo de Ventas (`sale.order.completed`/`voided` → `table.session.close_by_order`) y lo de Clientes
  (`customer.customer.erased` → `table.hold.forget_customer`, que anota `table.table.held` por retención
  para repintar el plano). Además, las lecturas tratan como cerrada una cuenta de mesa abierta **o
  aparcada** cuya `sale.Order` está `completed` o `voided`, con la hora de cierre de la cuenta, y las
  escrituras, antes de nada, cierran esas cuentas (`settle`): el plano no espera al relay. Una cuenta que
  acaba aparcada se cierra sin mesa (restricción `table_session_table_by_status`).
- **Reservas no es una reacción**: la llamada dentro de la operación
  de Reservas es la única vía; sus avisos `reservation.reservation.status_changed` y `updated` no se
  escuchan, porque entregados después re-aplicarían una reserva vieja
  (`test_integration_relay.py::test_a_party_seated_long_before_its_time_is_not_held_again_by_a_late_confirmation`).
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
- **Hora del negocio**: `base.business.business_zone` (la zona del hub); las retenciones de Reservas
  traen fecha y hora de pared y se guardan con esa zona. «Hoy» en el plano es el día del negocio.
- **Asistente**: cada operación declara `ai` (descripción; `risk: "high"` en cerrar, trasladar,
  fusionar, borrar zonas, mesas y cuentas) y cada campo de `schemas/` su `description`. Ninguna
  descripción manda preguntar antes: la tarjeta es la confirmación, y el «Ask first.» que llevaban
  cerrar, pasar, juntar y borrar una cuenta hacía que el asistente preguntara en el chat sin sacarla
  (hub#1140; lo guarda `tests/test_guardrails_assistant.py` para todo el Hub).
- **En persona** (`ai.in_person`): sentar, volver a sentar, dividir y enlazar una
  cuenta (`table.session.open`, `.restore`, `.split` y `.link_order`). Automatizaciones no las ofrece ni
  las concede, y un paso que se hubiera colado se rechaza al correr (`flow.high_risk`, FLOW-F12): las
  cuatro abren o retitulan la cuenta en Ventas con la sesión de quien actúa (`sale.add_sale`), y un paso
  solo lleva el permiso de su operación, así que caían siempre con `permission_denied`. El asistente, con
  una persona delante, las hace sin pedir confirmación (`risk: normal`). Mesas sigue sin ampliar los
  permisos de nadie.
- **Los importes agrupan los millares** también con cuatro cifras («1.234,56 €»; `formatMoney` de
  `@erplora/ui/components`, con `useGrouping: 'always'`, porque el CLDR del español espera a cinco: hub#658).
- **La ayuda dentro del Hub** (`help` en `apps.py`) publica el primer apartado, cada `###` de «Pantallas» y, de
  cada flujo `hecho` en una pestaña, el título, los «Pasos» y el «Si falla»; `tests/test_help_workbooks.py`
  rechaza ahí código, incidencias, píxeles, ids de flujo y nombres de operación. Lo que esas partes no dicen y
  vigilan las pruebas:
  - El color de cada estado sale de `FloorPlan/floor-status.css` de `@erplora/ui` (Disponible y Reservada,
    los tonos `success` y `warning`; Ocupada, `--ep-primary-text`, que sigue la paleta; Bloqueada, el gris
    `medium`), y el del tiempo, de `durationTone` (`frontend/lib/format.ts`): la leyenda de «Plano de sala»
    dice lo mismo y cambia con ellos.
  - El teléfono es hasta 640 px de ancho (`useIsPhone`), el mismo corte que las listas de `@erplora/ui`.
  - Quien atiende una mesa va también en su nombre accesible (`accessible` de `frontend/lib/floor-view.ts`).
  - Mientras carga, el plano pinta `FloorSkeleton`; los avisos de vacío y de error conservan sus acciones.
  - En «Editar plano», una flecha mueve la mesa 8 px y, con Mayúsculas, 32 px (`KEY_STEP` y `keyDelta`).
  - Tocar una mesa ocupada (TABLE-F11) abre el TPV en `/sale/pos?order=<id>`; la ventana de la mesa sale
    del evento `contextmenu` (pulsación larga en una pantalla táctil, clic derecho o tecla de menú), que el
    plano y `FloorCard` de `@erplora/ui` reciben sin dejar salir el menú del navegador. Safari en iOS no lo
    lanza al mantener pulsado: el equipo de destino es la tableta Android con Chrome.
  - En las ventanas de zona y de mesa, el motivo de un campo se quita al corregir ese campo aunque otro campo
    diga lo mismo (hub#888).
  - En Ajustes, lo que se cambia mientras se guarda se queda por guardar (hub#914); el aviso y los motivos
    siguen las reglas de las ventanas de formulario, y un rechazo sin campo se queda hasta el siguiente
    intento (hub#854); en el móvil cabe entera en español y en inglés: la frase larga del interruptor parte en
    dos líneas y «Guardar» se ve completo al final (hub#866).
- **Administrador de Django con CRUD completo** (PLAN §17): zonas, mesas, cuentas de mesa,
  recorrido, retenciones y ajustes; ids y fechas en solo lectura. Lo que guarda no pasa por las
  operaciones ni deja aviso.
- **Tarea programada**: `expire_table_holds` (`table.hold.expire`, cada hora, en UTC, `collapse`): la
  corre el worker (`base/scheduler.py`), en cada negocio y con su ámbito (`base.hub_visits`).

### Lo que NO hace, a propósito

- No guarda lo que se ha pedido: líneas, importes y cocina son de Ventas y Cocina; el importe de cada
  mesa del plano (TABLE-F33) lo lee de Ventas.
- No impide sentar más comensales que el aforo: avisa.
- No toma reservas: eso es Reservas; Mesas solo aparta la mesa en el plano.
- No tiene asiento por comensal, cursos, estado «por limpiar» ni mesas físicas unidas con
  aforo sumado: no entran en el MVP.
- No guarda planos distintos por turno.
- No deja elegir ni cambiar el camarero de una cuenta: es quien la sienta.

### Lo que queda fuera

- Los 34 flujos están `hecho`. Lo que no entra a propósito está en «Lo que NO hace, a propósito».
- Los dos iconos de [`UI-REQUESTS.md`](UI-REQUESTS.md) (`ion:restaurant-outline` para la app y
  `ion:map-outline` para el Plano de sala) siguen sin registrarse en `@erplora/ui`; mientras, la app usa
  `ion:grid-outline` (también en el paso «Tus mesas» del Inicio) y el plano `ion:apps-outline`.
