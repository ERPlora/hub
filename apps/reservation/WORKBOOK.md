# Workbook — Reservas (app)
Prefijo: RESERVATION
Alcance MVP: restaurante
Estado de la app: hecha (servidor y páginas). De la reserva por WhatsApp, el aviso al confirmar (F19) ya sale; de
F17 y F18 está la parte de Reservas y la conversación es de la segunda parte de la Bandeja de WhatsApp. La liberación de pendientes
(F13) avisa al momento solo en un negocio hasta la fase 2: ver «Lo que queda fuera».

> Manual de usuario y especificación de la app `reservation`. Se escribe **antes** que el código: no
> se programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Reservas del producto actual
> (`modules-workspace/modules/reservations`, `origin/main` `952295e`, v3.0.50). Los números de flujo se
> conservan (`RESERVATIONS-Fnn` → `RESERVATION-Fnn`). Lo que cambia frente al producto actual lo dice
> «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Reservas es el **libro de reservas del restaurante o del bar**: decide cuándo y para cuántos se acepta
reservar (franjas horarias con un máximo de reservas y, si se quiere, de comensales, dentro del horario
del negocio; y días bloqueados), apunta cada reserva con su cliente y su mesa, la lleva de Pendiente a
Completada y guarda en una **lista de espera** a quien no cabe.

Quién la usa:

- El **empleado** que coge el teléfono o atiende la puerta (el anfitrión o el camarero) apunta,
  confirma, sienta, cambia y cancela reservas y lleva la lista de espera.
- El **responsable** de sala, además, crea las franjas, bloquea días y cambia las reglas.
- El **administrador** y el **propietario**, además, borran reservas para siempre.

Reservas no pinta el plano (eso es **Mesas**: aparta la mesa de cada reserva confirmada), no cobra (eso
es **Ventas**) y no es la agenda de citas de una peluquería (eso es **Citas**).

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó (OpenTable, Resy, SevenRooms, Toast
Tables, Square, Lightspeed, TouchBistro, Tablein, TablesReady, CoverManager, TheFork Manager, Odoo). Las
dudas abiertas del producto actual se resolvieron así; la investigación, con sus fuentes, está en
«Investigación de mercado», al final de este manual.

- **Libro por día y por servicio**, con los **cubiertos** del día y cuánto queda libre en la próxima
  franja; la franja agotada se ve **atenuada y marcada «Lleno»**, no se esconde (OpenTable, Resy).
- **Ciclo de la reserva**: pendiente → confirmada → sentada → completada, más cancelada y no
  presentada; no se vuelve atrás.
- **El anfitrión gestiona la reserva entera** (duda 1): el empleado de sala confirma, sienta, cambia,
  cancela y marca no presentados, y lleva la lista de espera; lo del responsable son las franjas, los
  bloqueos y las reglas.
- **El aforo de la franja se cuenta en reservas y, si se quiere, también en comensales** (duda 2): el
  máximo de reservas de siempre y un máximo de comensales opcional; la franja se cierra con el primero
  que se alcanza, como ResDiary, OpenTable y HostMe.
- **Sentar la reserva sienta la mesa** (duda 3): «Sentar» abre la cuenta de su mesa en Mesas y Ventas
  en el mismo paso. Una mesa ocupada se rechaza (hay que liberarla o pasar la reserva a otra mesa),
  salvo que ese mismo grupo ya se sentara en ella desde el plano: entonces solo se marca la reserva.
- **En la lista están todas las acciones** (duda 4): editar (también la mesa), confirmar, sentar,
  completar, cancelar con motivo, no presentado y borrar.
- **Una mesa no se reserva dos veces a la misma hora** (duda 5): al elegir mesa se ofrecen las libres
  a esa hora que caben al grupo; dos reservas a la vez sobre la misma mesa y hora dejan una. El
  mercado avisa y deja sobrevender la mesa al personal; aquí manda el encargo de Ioan (una sola
  reserva por mesa y hora), y queda señalado como contradicción. La asignación automática y juntar
  mesas no entran (ver «Lo que queda fuera»).
- **La lista de espera es para un día y una hora** (duda 6), hoy o más adelante, en el orden en que se
  apuntó; cuando hay sitio se convierte en reserva con un toque. El mercado separa la cola de la puerta
  (con espera estimada y SMS) de la lista para días llenos; sin mensajería, aquí es una lista para las
  dos cosas (ver «Lo que queda fuera»).
- **El teléfono es obligatorio de fábrica en la reserva** (duda 7), y siempre el mismo (el producto
  actual no lo pedía hasta que se guardaba cualquier ajuste); el correo, no. La lista de espera no pide
  nada más que el nombre: el teléfono solo sirve para llamar.
- **Las reglas de reserva son del cliente que reserva solo** (duda 8): comensales mínimos y máximos,
  antelación mínima, días máximos y la franja llena atan a las reservas por internet o por WhatsApp. El
  personal reserva desde ya (nunca una hora pasada), cualquier grupo y cualquier fecha, y una franja
  llena la puede llenar a sabiendas: el sistema avisa y pide «Reservar igualmente».
- **Mesa reservada desde una hora antes** (duda 8, decidida por Mesas, TABLE-F25): antes la mesa sigue
  libre y enseña «Ana · 21:00».

## Antes de empezar

- Reservas necesita **Mesas** (la mesa de cada reserva y su retención en el plano), **Clientes** (la
  ficha de cada cliente) y **Horarios** (el horario del negocio). Se encienden con ella y no se apagan
  mientras Reservas esté encendida. Mesas trae con ella **Ventas**.
- Las horas son las del negocio: en esta fase, **Europe/Madrid**. Una reserva guarda su día y su hora
  de pared («el jueves a las 21:00»), como se dicen por teléfono.
- **Franjas**: sin una franja para ese día de la semana no se puede reservar nada. Es la causa número
  uno de «no hay disponibilidad».
- **Horario del negocio**: una reserva tiene que empezar con el negocio abierto según Horarios: sus
  días especiales y cambios temporales siempre, y su semana habitual en cuanto el negocio la guarda o la
  confirma. La semana por defecto de Horarios (de lunes a viernes de 09:00 a 18:00), sin confirmar, no
  limita: si no, un restaurante que nunca abrió Horarios no podría reservar ninguna cena.
- **Reglas de fábrica**: la reserva dura 120 minutos, nace Pendiente, el teléfono es obligatorio, el
  correo no, y una pendiente se libera 15 minutos después de su hora. Para las reservas por internet o
  WhatsApp, además: grupos de 1 a 20, al menos 1 hora de antelación y hasta 30 días vista.

Configuración inicial, paso a paso:

1. En **Horarios**, pon el horario del negocio (si no lo tienes ya).
2. Abre **Reservas → Disponibilidad**, sección **Franjas horarias**, y crea las franjas de cada día
   de servicio (RESERVATION-F01).
3. En **Fechas bloqueadas**, añade los días o las horas en que no aceptas reservas (RESERVATION-F02).
4. Si quieres otras reglas, cámbialas en **Reservas → Ajustes** (RESERVATION-F03, F04).
5. En **Mesas**, dibuja la sala: las reservas se asignan a sus mesas.
6. Crea una reserva de prueba y comprueba en **Disponibilidad → Ocupación** que su franja baja en uno.

## Pantallas

El menú **Reservas** tiene tres entradas: **Reservas**, **Lista de espera** y **Disponibilidad**. Abajo,
las pestañas de las tres más **Ajustes** (esta, solo a quien puede cambiarlos). Los botones que el
perfil no puede usar no salen.

### Reservas
Menú **Reservas → Reservas**. Arriba, la **barra del día**: «Día anterior», la fecha, «Día siguiente» y
«Hoy» cuando se está en otro día; el día en letra; y tres cifras: **cubiertos** (personas que vienen,
sin canceladas ni no presentadas), **reservas** y **próxima franja** (la primera que no ha terminado,
con cuántas reservas quedan «libres» o «Lleno»; o «No queda servicio hoy», «Sin servicio este día»,
«Cerrado este día»). «Hoy» es el del reloj del negocio, no el del dispositivo.

Debajo, la tabla del día por hora: Fecha, Hora, Cliente, Teléfono, Pax, Mesa, Estado; buscador
«Buscar cliente, teléfono o correo…» que busca en **todo** el libro (resultados por día y hora);
filtros por hora, comensales, mesa y estado; vista tabla o tarjetas. Acción principal **«Nueva
reserva»** y, por fila, según su estado: «Confirmar», «Sentar», «Completar», «Cancelar», «No
presentado», «Editar» y «Borrar» (solo el administrador). Tocar una fila la abre para editarla.

Vacía: «No hay reservas este día», con explicación y «Nueva reserva». Buscando sin resultados:
«Ninguna reserva coincide con la búsqueda» y «Limpiar filtros». Cargando: «Cargando…» y las cifras en
gris. Error: el mensaje y «Reintentar»; un fallo de una acción de fila sale encima de la tabla y uno
del formulario, dentro del formulario.

**Formulario de reserva** («Nueva reserva» / «Editar reserva»): Cliente (el buscador de Clientes, por
nombre o teléfono, con «+ Nuevo cliente»), Nombre, Teléfono, Correo, Fecha, Hora, Comensales, Duración
(minutos), Mesa (las libres a esa hora, con su aforo y su zona; las que no caben al grupo, avisadas),
Origen (Teléfono, En el local), Notas del cliente y Notas internas.

### Lista de espera
Menú **Reservas → Lista de espera**. Tabla, en el orden en que se apuntaron (por día y hora
preferida): Fecha, Hora pref., Cliente, Teléfono, Pax, Contactado, Estado (En espera, Convertida);
buscador y filtros (fecha, contactado, convertida). Acción principal **«Añadir cliente»** (Cliente,
Nombre, Teléfono, Fecha, Hora, Pax, Notas → «Añadir a la lista de espera»); por fila «Contactado»,
«Convertir» y «Quitar». Vacía: «La lista de espera está vacía.». Cargando: «Cargando…». Error: el
mensaje de la tabla con «Reintentar».

### Disponibilidad
Menú **Reservas → Disponibilidad**. Tres secciones apiladas:
- **Ocupación**: una fecha (hoy por defecto) y, por cada franja de ese día, Franja, Reservadas, Máx,
  Comensales y Disponibles; la franja sin hueco se ve atenuada con la marca «Lleno», y la que cae
  fuera del horario del negocio, marcada «Fuera de horario». Encima, el horario del negocio de ese día
  y, si el día está bloqueado, su motivo. Se refresca sola cuando entra, cambia o se cancela una
  reserva. Vacía: «Sin servicio ese día (sin franjas).».
- **Franjas horarias**: Día, Desde, Hasta, Máx. reservas, Máx. comensales; «Añadir franja» (Día,
  Desde, Hasta, Máx. reservas, Máx. comensales → «Crear franja») y «Quitar» por fila. Vacía: «Sin
  franjas horarias.».
- **Fechas bloqueadas**: Fecha, Motivo, Horas (Todo el día, o desde–hasta); «Añadir fecha bloqueada»
  (Fecha, Motivo, Todo el día, Desde, Hasta → «Bloquear fecha») y «Quitar». Vacía: «Sin fechas
  bloqueadas.».
Cada sección pinta su propio «Cargando…» y su error con reintento.

### Ajustes
Pestaña **Ajustes** (solo quien puede cambiarlos). Comensales mínimos y máximos, antelación mínima
(horas, para internet y WhatsApp), días máximos de antelación, duración por defecto, confirmar solas
las reservas nuevas, teléfono obligatorio, correo obligatorio y minutos tras la hora para liberar una
pendiente. «Guardar».

## Estados de cada pantalla

| Pantalla | Cargando | Vacía | Error | Sin permiso | App apagada |
|---|---|---|---|---|---|
| Reservas | «Cargando…», cifras en gris | «No hay reservas este día» + «Nueva reserva» | mensaje + «Reintentar» | aviso en lugar de la tabla | aviso en lugar de la tabla |
| Lista de espera | «Cargando…» | «La lista de espera está vacía.» | mensaje + «Reintentar» | aviso | aviso |
| Disponibilidad | «Cargando…» por sección | un texto por sección | mensaje + «Reintentar» por sección | aviso | aviso |
| Ajustes | «Cargando…» | — | mensaje + «Reintentar» | aviso | aviso |

Mientras se recupera la conexión en vivo, «Reconectando…» encima, sin borrar lo pintado.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| RESERVATION-F01 | Crear y quitar franjas horarias | hecho |
| RESERVATION-F02 | Bloquear un día o unas horas | hecho |
| RESERVATION-F03 | Ajustar las reglas de reserva | hecho |
| RESERVATION-F04 | Elegir si las reservas se confirman solas | hecho |
| RESERVATION-F05 | Consultar cuánto queda libre en un día | hecho |
| RESERVATION-F06 | Tomar una reserva a mano (teléfono o mostrador) | hecho |
| RESERVATION-F07 | Confirmar una reserva | hecho |
| RESERVATION-F08 | Modificar una reserva (día, hora, comensales, mesa) | hecho |
| RESERVATION-F09 | Cancelar una reserva | hecho |
| RESERVATION-F10 | Marcar que no se presentaron | hecho |
| RESERVATION-F11 | Sentar a la reserva | hecho |
| RESERVATION-F12 | Completar la reserva | hecho |
| RESERVATION-F13 | Liberar las reservas pendientes que nadie confirmó | parcial |
| RESERVATION-F14 | Apuntar en la lista de espera | hecho |
| RESERVATION-F15 | Marcar contactado o quitar de la lista de espera | hecho |
| RESERVATION-F16 | Convertir una entrada de la lista de espera en reserva | hecho |
| RESERVATION-F17 | Reserva que llega por WhatsApp | parcial |
| RESERVATION-F18 | Cambiar o anular la reserva por WhatsApp | parcial |
| RESERVATION-F19 | Avisar por WhatsApp cuando el restaurante confirma | hecho |
| RESERVATION-F20 | Borrar una reserva | hecho |
| RESERVATION-F21 | Unir las reservas de dos fichas de cliente | hecho |
| RESERVATION-F22 | Borrar los datos personales de un cliente (RGPD) | hecho |
| RESERVATION-F23 | Elegir una mesa libre para la reserva | hecho |

### RESERVATION-F01 Crear y quitar franjas horarias
<!-- origen: fi:modules/reservations#command-reservations-timeslots-create-sql-transaccional fi:modules/reservations#command-reservations-timeslots-delete-sql-transaccional fi:modules/reservations#query-reservations-timeslots-list old:reservations/workflow/disponibilidad.md#reservations-f01 qa:modules/reservations/create-reservation wf:whatsapp-mesa#rec_wa_mesa-f04 -->
Estado: hecho
Actor: responsable
Pantalla: Disponibilidad → Franjas horarias
Pasos:
1. Pulsa «Añadir franja», elige el día de la semana, desde y hasta, el máximo de reservas y, si
   quieres, el máximo de comensales. «Crear franja».
2. Para quitarla, «Quitar» en su fila y confirma. Las reservas que ya tenía se quedan.
Entra: día, desde, hasta, máximo de reservas, máximo de comensales (opcional).
Sale: la franja (avisa: `reservation.time_slot.created`, `reservation.time_slot.deleted`).
Si falla: «Hasta» antes o igual que «Desde»: «La franja tiene que terminar después de empezar.»; una
franja que se pisa con otra del mismo día: «Esa franja se pisa con otra del mismo día (13:00–16:00).».
Implicados: RESERVATION-F05, RESERVATION-F06

### RESERVATION-F02 Bloquear un día o unas horas
<!-- origen: qa:modules/reservations/create-reservation wf:whatsapp-mesa#rec_wa_mesa-f04 fi:modules/reservations#command-reservations-blocked_dates-create-sql-transaccional fi:modules/reservations#command-reservations-blocked_dates-delete-sql-transaccional fi:modules/reservations#query-reservations-blocked_dates-list old:reservations/workflow/disponibilidad.md#reservations-f02 -->
Estado: hecho
Actor: responsable
Pantalla: Disponibilidad → Fechas bloqueadas
Pasos:
1. Pulsa «Añadir fecha bloqueada», escribe la fecha y el motivo (festivo, cierre, evento privado).
2. Deja «Todo el día» marcado o, para unas horas, quítalo y pon desde y hasta.
3. Ese día (o esas horas) no se aceptan reservas nuevas; las que ya había se quedan.
4. Para levantar el bloqueo, «Quitar» en su fila y confirma.
Entra: fecha, motivo, todo el día o desde–hasta.
Sale: el bloqueo (avisa: `reservation.blocked_date.created`, `reservation.blocked_date.deleted`).
Si falla: sin horas cuando no es todo el día, o «hasta» antes que «desde»: lo dice el campo; ese día
ya bloqueado a esa hora: «Esa fecha ya está bloqueada a esa hora.».
Implicados: RESERVATION-F05, RESERVATION-F06

### RESERVATION-F03 Ajustar las reglas de reserva
<!-- origen: qa:modules/reservations/create-reservation fi:modules/reservations#command-reservations-settings-upsert-sql-transaccional fi:modules/reservations#query-reservations-settings-get old:reservations/workflow/disponibilidad.md#reservations-f03 qa:verticals/restaurant/05-reservations -->
Estado: hecho
Actor: responsable
Pantalla: Ajustes
Pasos:
1. Cambia comensales mínimos y máximos, antelación, duración por defecto, teléfono o correo
   obligatorios y los minutos para liberar una pendiente. «Guardar».
2. Las reglas valen para las reservas nuevas y para los cambios; las ya hechas no se tocan.
Entra: las reglas.
Sale: las reglas guardadas (avisa: `reservation.settings.updated`).
Si falla: mínimo de comensales mayor que el máximo: lo dice el campo.
Implicados: RESERVATION-F06, RESERVATION-F13, RESERVATION-F17

### RESERVATION-F04 Elegir si las reservas se confirman solas
<!-- origen: fi:modules/reservations#command-reservations-settings-upsert-sql-transaccional old:reservations/workflow/disponibilidad.md#reservations-f04 wf:whatsapp-mesa#rec_wa_mesa-f06 -->
Estado: hecho
Actor: responsable
Pantalla: Ajustes
Pasos:
1. Marca «Confirmar solas las reservas nuevas» y guarda.
2. Desde entonces toda reserva nueva (a mano, desde la lista de espera, por internet o por WhatsApp)
   nace Confirmada y retiene su mesa.
Entra: el interruptor.
Sale: el ajuste (avisa: `reservation.settings.updated`).
Si falla: sin permiso para cambiar los ajustes, la pestaña no sale; un fallo al guardar se dice encima
del botón y el interruptor vuelve a como estaba.
Implicados: RESERVATION-F07, TABLE-F25

### RESERVATION-F05 Consultar cuánto queda libre en un día
<!-- origen: wf:whatsapp-mesa#rec_wa_mesa-f04 old:reservations/workflow/disponibilidad.md#reservations-f05 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Disponibilidad → Ocupación; Reservas (barra del día)
Pasos:
1. Elige la fecha (hoy por defecto).
2. Cada franja dice cuántas reservas lleva, su máximo, los comensales y las que quedan; la llena sale
   atenuada con «Lleno» y la que cae fuera del horario del negocio, con «Fuera de horario».
3. Se actualiza sola mientras entran, cambian o se cancelan reservas.
Entra: la fecha.
Sale: nada (consulta). Cuenta exactamente lo que cuenta la puerta del alta.
Si falla: sin franjas ese día: «Sin servicio ese día (sin franjas).»; un fallo al leer se dice en la
sección con «Reintentar».
Implicados: RESERVATION-F01, RESERVATION-F02, SCHEDULE-F02

### RESERVATION-F06 Tomar una reserva a mano (teléfono o mostrador)
<!-- origen: qa:verticals/restaurant/11-races-and-concurrency qa:modules/reservations/create-reservation qa:verticals/restaurant/05-reservations fi:modules/reservations#command-reservations-reservations-create-handler-wasm-create_reservation old:reservations/workflow/reservas.md#reservations-f06 wf:restaurante-dia#rec_restaurante-f04 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Reservas → «Nueva reserva»
Pasos:
1. Busca al cliente por nombre o teléfono; si no está, escribe su nombre y su teléfono (se crea su
   ficha en Clientes, o se usa la que ya tiene ese teléfono).
2. Pon la fecha, la hora, los comensales y, si quieres, la mesa (RESERVATION-F23), la duración, el
   origen y las notas. «Reservar».
3. La reserva nace Pendiente (o Confirmada, si se confirman solas: entonces retiene su mesa).
4. Por voz: «reserva para 4 mañana a las 21 a nombre de Ana, en la mesa 5».
Entra: cliente (o nombre y teléfono), fecha, hora, comensales, mesa, duración, origen, notas.
Sale: la reserva, ligada a la ficha del cliente (avisa: `reservation.reservation.created`).
Si falla: no se guarda nada y lo escrito se queda; el primer motivo que aplica, en este orden: un
teléfono que no es de su país (el motivo de Clientes, en el campo Teléfono, antes que nada más: nunca
después de «¿Reservar igualmente?»); sin teléfono (o sin correo) cuando son obligatorios: «Este negocio
pide un teléfono en cada reserva.»; una hora ya pasada: «Esa hora ya ha pasado.»; solo por internet o
WhatsApp, comensales fuera de los límites («Ese número de comensales está fuera de los límites del
negocio (1–20 comensales).»), menos antelación de la mínima («Hay que reservar con al menos 1 h de
antelación.») o más allá de los días máximos («Solo se reserva hasta 30 días vista.»); día bloqueado:
«Esa fecha está bloqueada (festivo o cierre): ese día no se aceptan reservas.»; negocio cerrado a esa
hora (Horarios): «A esa hora el negocio está cerrado.»; ninguna franja cubre esa hora: «No hay servicio
a esa hora: ninguna franja la cubre.»; franja llena: «Esa franja ya está completa para ese día.» (al
personal se le pregunta «¿Reservar igualmente?» y, si lo confirma, la reserva entra; por internet o
WhatsApp, nunca); mesa fuera de servicio: «Esa mesa no se puede reservar: está bloqueada o fuera de
servicio.»; mesa ya reservada a esa hora: «La mesa 5 ya tiene una reserva de 21:00 a 23:00.». Dos
reservas a la vez sobre el último hueco o sobre la misma mesa y hora: entra una y la otra recibe su
motivo (en la franja llena, el personal puede después reservar igualmente; en la mesa, nunca).
Implicados: CUSTOMER-F10, CUSTOMER-F11, SCHEDULE-F02, RESERVATION-F23, TABLE-F25

### RESERVATION-F07 Confirmar una reserva
<!-- origen: qa:verticals/restaurant/05-reservations wf:whatsapp-mesa#rec_wa_mesa-f06 wf:restaurante-dia#rec_restaurante-f04 fi:modules/reservations#command-reservations-reservations-set_status-handler-wasm-set_status old:reservations/workflow/reservas.md#reservations-f07 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Reservas (fila → «Confirmar»)
Pasos:
1. «Confirmar» en una reserva Pendiente.
2. Pasa a Confirmada y, si tiene mesa, Mesas la retiene: desde una hora antes la mesa sale Reservada
   en el plano con el nombre y la hora (TABLE-F25).
Entra: la reserva.
Sale: la reserva confirmada (avisa: `reservation.reservation.status_changed`).
Si falla: desde otro estado: «Esta reserva está confirmada: no se puede confirmar.»; con su mesa fuera
de servicio (bloqueada, desactivada, borrada o en una zona desactivada), que no se podría retener: «La
mesa 5 (Terraza) no se puede reservar: está bloqueada o fuera de servicio.», y sigue Pendiente.
Implicados: TABLE-F25, RESERVATION-F19

### RESERVATION-F08 Modificar una reserva (día, hora, comensales, mesa)
<!-- origen: qa:verticals/restaurant/05-reservations wf:restaurante-dia#rec_restaurante-f04 fi:modules/reservations#command-reservations-reservations-update-sql-transaccional old:reservations/workflow/reservas.md#reservations-f08 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Reservas (fila → «Editar», o tocar la fila)
Pasos:
1. Cambia el día, la hora, los comensales, la duración, la mesa (o quítala), el contacto o las notas.
   «Guardar».
2. El cambio pasa la misma puerta que el alta del personal (sin contar la propia reserva), aunque la
   reserva naciera por internet o por WhatsApp: el personal cambia cualquier grupo y llena una franja
   llena con «Reservar igualmente». Si estaba confirmada, Mesas mueve su retención a la mesa y la hora
   nuevas, o la suelta si se queda sin mesa (TABLE-F26).
3. Una reserva sentada, completada, cancelada o no presentada solo cambia sus notas.
Entra: los campos cambiados.
Sale: la reserva cambiada (avisa: `reservation.reservation.updated`).
Si falla: los motivos de RESERVATION-F06; en otro estado: «Esta reserva ya no se puede cambiar: solo sus
notas.».
Implicados: TABLE-F26, RESERVATION-F06, RESERVATION-F18

### RESERVATION-F09 Cancelar una reserva
<!-- origen: qa:verticals/restaurant/05-reservations wf:restaurante-dia#rec_restaurante-f04 fi:modules/reservations#command-reservations-reservations-set_status-handler-wasm-set_status old:reservations/workflow/reservas.md#reservations-f09 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Reservas (fila → «Cancelar»)
Pasos:
1. «Cancelar» en una reserva Pendiente o Confirmada; escribe el motivo si quieres y confirma.
2. Pasa a Cancelada, deja su hueco libre y Mesas suelta su mesa (TABLE-F27).
Entra: la reserva y el motivo.
Sale: la reserva cancelada (avisa: `reservation.reservation.status_changed`).
Si falla: desde otro estado: «Esta reserva está sentada: no se puede cancelar.».
Implicados: TABLE-F27, RESERVATION-F18

### RESERVATION-F10 Marcar que no se presentaron
<!-- origen: qa:verticals/restaurant/05-reservations wf:restaurante-dia#rec_restaurante-f04 fi:modules/reservations#command-reservations-reservations-set_status-handler-wasm-set_status old:reservations/workflow/reservas.md#reservations-f10 qa:modules/reservations/no-show-and-deposit wf:whatsapp-mesa#rec_wa_mesa-f10 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Reservas (fila → «No presentado»)
Pasos:
1. «No presentado» en una reserva Pendiente o Confirmada y confirma.
2. Pasa a No presentada, deja su hueco libre y Mesas suelta su mesa.
Entra: la reserva.
Sale: la reserva no presentada (avisa: `reservation.reservation.status_changed`).
Si falla: desde otro estado: «Esta reserva está sentada: no se puede marcar como no presentada.».
Implicados: TABLE-F27

### RESERVATION-F11 Sentar a la reserva
<!-- origen: fi:modules/reservations#command-reservations-reservations-set_status-handler-wasm-set_status wf:whatsapp-mesa#rec_wa_mesa-f10 old:reservations/workflow/reservas.md#reservations-f11 wf:restaurante-dia#rec_restaurante-f05 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Reservas (fila → «Sentar»)
Pasos:
1. Llega el grupo: «Sentar» en su reserva Pendiente o Confirmada.
2. Pasa a Sentada. Si tiene mesa, se sienta en Mesas con sus comensales y su cliente: se abre la
   cuenta de la mesa en Ventas y se gasta la retención de esta reserva, solo la suya (TABLE-F28): con
   Ana a las 19:00 y Bea a las 21:00 en la mesa 5, sentar a Ana a las 20:10 deja la mesa reservada para
   Bea, que vuelve a salir Reservada cuando Ana se va.
3. Si el grupo ya se sentó en esa mesa desde el plano (gastando la retención de esta reserva), solo se
   marca la reserva, con la cuenta de la mesa.
Entra: la reserva.
Sale: la reserva sentada y, si se pudo, la cuenta de la mesa (avisa:
`reservation.reservation.status_changed`; Mesas avisa `table.session.opened`).
Si falla: desde otro estado: «Esta reserva está completada: su estado ya no puede cambiar.»; la mesa
fuera de servicio: «La mesa 5 (Terraza) no se puede reservar: está bloqueada o fuera de servicio.»; la
mesa ocupada por otros (también por el grupo de otra reserva sentado antes, aunque al sentarlo desde el
plano se gastara la retención de esta): «La mesa 5 (Terraza) está ocupada ahora mismo: libérala, o pasa
la reserva a otra mesa antes de sentarla.»; si Mesas o Ventas rechazan sentar, su motivo. En todos, la
reserva no cambia.
Implicados: TABLE-F10, TABLE-F28

### RESERVATION-F12 Completar la reserva
<!-- origen: fi:modules/reservations#command-reservations-reservations-set_status-handler-wasm-set_status wf:whatsapp-mesa#rec_wa_mesa-f10 old:reservations/workflow/reservas.md#reservations-f12 wf:restaurante-dia#rec_restaurante-f13 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Reservas (fila → «Completar»)
Pasos:
1. El grupo se va: «Completar» en su reserva Sentada.
2. Pasa a Completada; su cuenta de mesa sigue su curso en Mesas y Ventas (se cobra o se cierra allí).
Entra: la reserva.
Sale: la reserva completada (avisa: `reservation.reservation.status_changed`).
Si falla: sin sentar antes: «Esta reserva está confirmada: no se puede completar sin sentarla antes.».
Implicados: RESERVATION-F11

### RESERVATION-F13 Liberar las reservas pendientes que nadie confirmó
<!-- origen: wf:whatsapp-mesa#rec_wa_mesa-f06 old:reservations/workflow/reservas.md#reservations-f13 -->
Estado: parcial — la liberación corre sola cada cuarto de hora y libera las pendientes de todos los
negocios, pero en esta fase avisa en un único negocio fijo: la pantalla de Reservas de los demás la ve
en su repaso de cinco minutos, no al momento (llega con el recorrido por negocio de la fase 2)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada cuarto de hora, las reservas que siguen Pendientes pasados los minutos de los ajustes (15) desde
   su hora se cancelan con el motivo «Sin confirmar» y dejan su hueco libre.
2. Las confirmadas, sentadas y las de otros días no se tocan.
Entra: la hora.
Sale: las reservas liberadas (avisa: `reservation.reservation.unconfirmed_released`, solo si liberó
alguna).
Si falla: una pasada que falla no cambia nada y la siguiente lo vuelve a intentar.
Implicados: RESERVATION-F03

### RESERVATION-F14 Apuntar en la lista de espera
<!-- origen: qa:verticals/restaurant/05-reservations fi:modules/reservations#command-reservations-waitlist-create-sql-transaccional fi:modules/reservations#query-reservations-waitlist-list old:reservations/workflow/lista-de-espera.md#reservations-f14 qa:modules/reservations/waitlist-and-walk-in wf:whatsapp-mesa#rec_wa_mesa-f05 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Lista de espera → «Añadir cliente»
Pasos:
1. Busca al cliente o escribe su nombre y, si quieres, su teléfono (con teléfono se liga a su ficha como
   una reserva), la fecha, la hora que prefiere, los comensales y las notas.
2. «Añadir a la lista de espera»: sale en la lista, en el orden en que se apuntó, En espera.
Entra: cliente (o nombre y teléfono), fecha, hora preferida, comensales, notas.
Sale: la entrada (avisa: `reservation.waitlist.created`).
Si falla: sin nombre ni cliente: lo dice el formulario; un teléfono que no es de su país: el motivo de
Clientes.
Implicados: RESERVATION-F16, CUSTOMER-F10

### RESERVATION-F15 Marcar contactado o quitar de la lista de espera
<!-- origen: qa:modules/reservations/waitlist-and-walk-in fi:modules/reservations#command-reservations-waitlist-delete-sql-transaccional fi:modules/reservations#command-reservations-waitlist-update-handler-wasm-waitlist_update old:reservations/workflow/lista-de-espera.md#reservations-f15 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Lista de espera (fila → «Contactado», «Quitar»)
Pasos:
1. «Contactado» cuando se le llama: la fila dice «Sí».
2. «Quitar» (y confirmar) cuando ya no espera: sale de la lista.
Entra: la entrada.
Sale: la entrada contactada o quitada (avisa: `reservation.waitlist.updated`,
`reservation.waitlist.deleted`).
Si falla: una entrada que ya no está: «Esa entrada de la lista de espera no existe en este negocio.».
Implicados: RESERVATION-F14

### RESERVATION-F16 Convertir una entrada de la lista de espera en reserva
<!-- origen: qa:verticals/restaurant/05-reservations qa:modules/reservations/waitlist-and-walk-in fi:modules/reservations#command-reservations-waitlist-update-handler-wasm-waitlist_update old:reservations/workflow/lista-de-espera.md#reservations-f16 -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Lista de espera (fila → «Convertir»)
Pasos:
1. Hay sitio: «Convertir». Se crea la reserva con los datos de la propia entrada (cliente, fecha, hora
   preferida, comensales, notas), con la duración por defecto, y la entrada queda Convertida.
2. La conversión comprueba que la hora no haya pasado, el día bloqueado, el horario del negocio y la
   franja con sitio: es el personal quien la hace, a menudo para ahora mismo (sin antelación, días
   máximos ni límites de comensales). Con la franja llena, se pregunta «¿Convertir igualmente?».
Entra: la entrada.
Sale: la reserva (origen «Lista de espera») y la entrada convertida (avisa:
`reservation.reservation.created`, `reservation.waitlist.converted`).
Si falla: hora pasada, franja llena o día bloqueado: su motivo, y nada cambia; ya convertida: «Esta
entrada ya se convirtió en reserva.».
Implicados: RESERVATION-F06, RESERVATION-F14

### RESERVATION-F17 Reserva que llega por WhatsApp
<!-- origen: wf:whatsapp-mesa#rec_wa_mesa-f03 qa:verticals/restaurant/05-reservations wf:whatsapp-mesa#rec_wa_mesa-f05 old:reservations/workflow/whatsapp-y-clientes.md#reservations-f17 qa:modules/reservations/whatsapp-reservation -->
Estado: parcial — Reservas ya acepta la reserva que el cliente hace por WhatsApp con sus reglas; falta
la conversación que la pide (preguntar comensales, ofrecer horas libres, contestar), que es la segunda
parte de la Bandeja de WhatsApp
Actor: cliente, asistente
Pantalla: ninguna
Pasos:
1. El cliente escribe al WhatsApp del restaurante («mesa para 4 el sábado a las 21»).
2. La reserva entra con las reglas del cliente que reserva solo (comensales, antelación, días máximos;
   una franja llena, nunca), ligada a la ficha que ya tiene ese teléfono o a una nueva de origen
   WhatsApp; con el nombre que dé en el mensaje y, si no da ninguno, a nombre de su teléfono. Sus
   peticiones van a las notas.
3. La reserva aparece en Reservas, Pendiente para que la confirme el personal (o Confirmada, si se
   confirman solas).
Entra: el mensaje, el teléfono y la ficha del cliente.
Sale: la reserva, de origen WhatsApp (avisa: `reservation.reservation.created`).
Si falla: los motivos de RESERVATION-F06 que atan al cliente, para contárselo y ofrecerle otra hora.
Implicados: CUSTOMER-F10, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F24

### RESERVATION-F18 Cambiar o anular la reserva por WhatsApp
<!-- origen: old:reservations/workflow/whatsapp-y-clientes.md#reservations-f18 wf:whatsapp-mesa#rec_wa_mesa-f08 -->
Estado: parcial — Reservas ya cambia o anula la reserva en nombre del cliente, comprobando que es suya;
falta que WhatsApp lo pida desde la conversación (segunda parte de la Bandeja de WhatsApp; en el
producto actual tampoco lo hacía)
Actor: cliente, asistente
Pantalla: ninguna
Pasos:
1. El cliente escribe «no vamos a poder ir» o «¿podemos ir a las nueve?».
2. Se comprueba que la reserva es de quien escribe (su ficha); si no, se rechaza sin contar nada de
   ella, ni siquiera si existe.
3. Se anula o se cambia con las reglas del cliente que reserva solo; la mesa, las notas internas y
   reservar igualmente siguen siendo cosa del restaurante.
4. La mesa retenida se suelta o se mueve, como al cambiar o cancelar a mano.
Entra: el mensaje y la ficha del cliente.
Sale: la reserva anulada o cambiada (avisa: `reservation.reservation.status_changed`,
`reservation.reservation.updated`).
Si falla: «Esa reserva es de otro comensal, así que no se puede gestionar en su nombre.»; «La mesa y
las notas internas las pone el restaurante: no se pueden cambiar desde la reserva del propio
cliente.»; o el motivo de la puerta (RESERVATION-F06).
Implicados: RESERVATION-F08, RESERVATION-F09, WHATSAPP_INBOX-F25

### RESERVATION-F19 Avisar por WhatsApp cuando el restaurante confirma
<!-- origen: old:reservations/workflow/whatsapp-y-clientes.md#reservations-f19 wf:whatsapp-mesa#rec_wa_mesa-f07 -->
Estado: hecho
Actor: responsable, cliente
Pantalla: Reservas
Pasos:
1. Con la automatización «Avisar por WhatsApp al cliente cuando se confirma su reserva» encendida en
   Automatizaciones (WHATSAPP_INBOX-F26), el personal pulsa «Confirmar» en una reserva Pendiente, o la reserva
   nace ya confirmada porque «Confirmar solas las reservas nuevas» está encendido.
2. La reserva da su día y su hora listos para decírselos al cliente («martes, 5 de marzo de 2030»,
   «21:30»), en su idioma y en el reloj del negocio, y sus comensales.
3. Si el teléfono de la reserva (el de su conversación, si llegó por WhatsApp; RESERVATION-F17) tiene
   conversación de WhatsApp con el negocio, el cliente recibe por ese mismo WhatsApp que su mesa está
   confirmada, con el día, la hora y los comensales.
Entra: la confirmación de la reserva y su teléfono.
Sale: el aviso de la confirmación (`reservation.reservation.status_changed`) y el mensaje al cliente, que se ve
en su conversación de la Bandeja de WhatsApp.
Si falla: sin teléfono o sin conversación de WhatsApp con ese número, no se manda nada y la reserva sigue
confirmada; el motivo queda en el historial de la automatización.
Implicados: RESERVATION-F07, RESERVATION-F17, WHATSAPP_INBOX-F26

### RESERVATION-F20 Borrar una reserva
<!-- origen: fi:modules/reservations#command-reservations-reservations-delete-sql-transaccional old:reservations/workflow/reservas.md#reservations-f20 -->
Estado: hecho
Actor: administrador, propietario
Pantalla: Reservas (fila → «Borrar»)
Pasos:
1. «Borrar» y confirma. Mejor cancelar: guarda el motivo.
2. La reserva desaparece del libro y Mesas suelta su mesa.
Entra: la reserva.
Sale: nada (avisa: `reservation.reservation.deleted` y `reservation.reservation.status_changed`
con el estado `deleted`).
Si falla: sin permiso para borrar, «Borrar» no sale; una reserva que ya no está: «Esa reserva no existe
en este negocio.».
Implicados: TABLE-F27

### RESERVATION-F21 Unir las reservas de dos fichas de cliente
<!-- origen: old:reservations/workflow/whatsapp-y-clientes.md#reservations-f21 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Clientes se unen dos fichas de la misma persona.
2. Sus reservas y sus entradas de espera pasan a la ficha que queda; el nombre con el que reservaron
   no cambia.
Entra: el aviso `customer.customer.merged` (`id` la que queda, `absorbed_id` la absorbida).
Sale: reservas y entradas re-apuntadas (avisa: `reservation.customer.reassigned`, solo si movió
alguna). Repetirlo no cambia nada.
Si falla: se reintenta solo; repetirlo no cambia nada.
Implicados: CUSTOMER-F13

### RESERVATION-F22 Borrar los datos personales de un cliente (RGPD)
<!-- origen: old:reservations/workflow/whatsapp-y-clientes.md#reservations-f22 -->
Estado: hecho
Actor: sistema
Pantalla: Reservas, Lista de espera
Pasos:
1. En Clientes se borran los datos personales de una ficha.
2. Sus reservas se quedan sin nombre, teléfono, correo, notas, notas internas ni motivo de
   cancelación, y sus entradas de espera sin nombre, teléfono, correo ni notas (también las quitadas).
   La pantalla dice «Cliente borrado».
3. Se conservan el día, la hora, los comensales, la mesa, el estado y el enlace a la ficha. El nombre
   también se borra de los avisos que sus reservas dejaron en el registro de avisos (`status_changed` y
   `updated` lo llevan). Mesas olvida el nombre de sus retenciones por su cuenta (TABLE-F31).
Entra: el aviso `customer.customer.erased` (`id` de la ficha).
Sale: reservas y entradas sin datos personales (avisa: `reservation.customer.erased`, solo si cambió
alguna). Repetirlo no cambia nada.
Si falla: se reintenta solo; repetirlo no cambia nada.
Implicados: CUSTOMER-F16, TABLE-F31

### RESERVATION-F23 Elegir una mesa libre para la reserva
<!-- origen: nuevo (el producto actual no elegía la mesa en el formulario: solo el asistente asignaba mesa) -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: formulario de reserva → Mesa
Pasos:
1. Con la fecha, la hora y los comensales puestos, el campo Mesa ofrece las mesas en servicio que
   están libres a esa hora (sin otra reserva viva que se pise), primero las que caben al grupo, con su
   aforo y su zona; las que se quedan pequeñas salen avisadas, y se pueden elegir igual.
2. Por voz: «en la mesa 5» o «en la 4 de la terraza».
Entra: fecha, hora, duración, comensales.
Sale: nada (consulta).
Si falla: sin mesas libres a esa hora, el campo no ofrece ninguna y la reserva se puede tomar sin mesa;
una mesa que se ocupa mientras tanto la rechaza la puerta (RESERVATION-F06).
Implicados: RESERVATION-F06, TABLE-F25

## Reservas: lo que entra y lo que sale

Todo se puede pedir por las pantallas, por el asistente (por voz o por texto, con la sesión de la
propia persona) y por la API, con las mismas reglas y los mismos permisos. Pensado para la voz: una
reserva se nombra por su id o por el nombre o el teléfono del cliente con su fecha («la reserva de Ana
de mañana»); una mesa por su id o por su número («mesa 5»), con la zona si el número se repite; un
cliente por su id, su nombre o su teléfono. Si una referencia casa con varias, se rechaza diciendo
cuáles (409 `*_ambiguous`). Cambiar y cancelar se pueden pedir además en nombre del propio cliente
(`on_behalf_of`, su ficha; hoy, desde WhatsApp): solo su reserva, con sus reglas de cliente y sin tocar la
mesa, las notas internas ni reservar igualmente (F18).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las reservas de unos días (o de todo el libro buscando), con filtros, orden y páginas (hasta 100) | ver reservas | F05–F12 | `reservation.reservation.list` |
| Una reserva | ver reservas | F08, F19 | `reservation.reservation.get` |
| Un día: cubiertos, reservas, bloqueos, horario del negocio y ocupación de cada franja | ver reservas | F05 | `reservation.availability.day` |
| Las mesas libres para una fecha, hora, duración y grupo | ver reservas | F23 | `reservation.availability.tables` |
| Las franjas horarias, con filtros y páginas | ver franjas | F01 | `reservation.time_slot.list` |
| Las fechas bloqueadas, con filtros y páginas | ver bloqueos | F02 | `reservation.blocked_date.list` |
| La lista de espera, en orden de llegada, con búsqueda, filtros y páginas | ver lista de espera | F14–F16 | `reservation.waitlist.list` |
| Las reglas (con la zona horaria del negocio) | ver ajustes | F03, F04 | `reservation.settings.get` |

Todas se pueden seguir en vivo.

Cada reserva que dan (la lista, una reserva y la que devuelve cada acción) trae, además de su fecha y su
hora, el día y la hora listos para decir en el idioma de quien la pide («martes, 5 de marzo de 2030» o
«Tuesday, March 5, 2030», y «21:30»): es lo que usa un mensaje que no sabe dar formato a una fecha. Son
los de la reserva tal como se apuntó, en el reloj del negocio, sin correrse por la zona horaria.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Apunta una reserva (`overbook` llena a sabiendas una franja llena, solo el personal) | apuntar reservas | F06 | `reservation.reservation.create` |
| Cambia una reserva | cambiar reservas | F08 | `reservation.reservation.update` |
| Confirma, sienta, completa, cancela o marca no presentada | cambiar reservas | F07, F09–F12 | `reservation.reservation.confirm`, `.seat`, `.complete`, `.cancel`, `.no_show` |
| Borra una reserva | borrar reservas | F20 | `reservation.reservation.delete` |
| Libera las pendientes vencidas | cambiar reservas | F13 | `reservation.reservation.release_unconfirmed` |
| Crea o quita una franja | cambiar franjas | F01 | `reservation.time_slot.create`, `.delete` |
| Bloquea o desbloquea una fecha | cambiar bloqueos | F02 | `reservation.blocked_date.create`, `.delete` |
| Apunta, marca contactada, convierte (también a sabiendas en una franja llena) o quita una entrada de espera | cambiar lista de espera | F14–F16 | `reservation.waitlist.create`, `.update`, `.convert`, `.delete` |
| Guarda las reglas | cambiar ajustes | F03, F04 | `reservation.settings.update` |

Solo para la plataforma (sin ruta en la API, como sistema): `reservation.customer.reassign` y
`reservation.customer.erase` (reacciones a Clientes).

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `reservation.reservation.created` | Alta (también desde la lista de espera) | `id`, `status`, `table_id`, `date`, `time`, `party_size` |
| `reservation.reservation.status_changed` | Confirmar, sentar, completar, cancelar, no presentado, borrar | `id`, `status` (`deleted` al borrar), `previous_status`, `table_id`, `date`, `time`, `duration_minutes`, `party_size`, `guest_name`, `customer_id` |
| `reservation.reservation.updated` | Cambiar | `id` y los campos que cambiaron (`table_id`, `date`, `time`, `duration_minutes`, `party_size`, `guest_name`); `table_id` vacío = sin mesa |
| `reservation.reservation.deleted` | Borrar | `id` |
| `reservation.reservation.unconfirmed_released` | Liberar pendientes | `count` |
| `reservation.time_slot.created`, `.deleted` | Franjas | `id` |
| `reservation.blocked_date.created`, `.deleted` | Bloqueos | `id`, `date` |
| `reservation.waitlist.created`, `.updated`, `.converted`, `.deleted` | Lista de espera | `id` (`reservation_id` al convertir) |
| `reservation.settings.updated` | Guardar las reglas | los campos cambiados |
| `reservation.customer.reassigned`, `reservation.customer.erased` | Reacciones a Clientes | `id` (y `absorbed_id`) |

`status_changed` y `updated` llevan además el nombre del cliente y su ficha (era la carga con la que
Mesas iba a pintar la retención); los demás, solo ids y números. Mesas ya no escucha estos avisos: la
retención la recibe por la llamada de Reservas en la misma transacción (TABLE-F25–F28).

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| `customer.customer.merged` | Clientes | Pasa sus reservas y entradas a la ficha que queda (F21) | `reservation.customer.reassign` |
| `customer.customer.erased` | Clientes | Borra sus datos personales de reservas y entradas (F22) | `reservation.customer.erase` |

### Lo que necesita de otras apps

- **Mesas** (requisito): la mesa de cada reserva (sus mesas, para elegirla y comprobar que está en
  servicio) y, en la misma transacción de cada cambio, la retención de su mesa:
  `table.hold.sync_reservation` (confirmar, cancelar, no presentada, borrar),
  `table.hold.move_reservation` (quitar la mesa de una confirmada) y `table.hold.release` (sentar
  pronto); sentar llama a `table.session.open` con la sesión de quien sienta.
- **Clientes** (requisito): la ficha del cliente (`find_customer`), buscarla por teléfono
  (`customer.customer.by_phone`) y crearla (`customer.customer.create`), con la sesión de quien reserva.
- **Horarios** (requisito): el horario del negocio de cada día (`schedule.hours.for_range`), leído en
  nombre de quien reserva aunque no tenga permiso en Horarios, y la forma de decir un día
  (`day_label`), la misma que usa Citas.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Mesas | Retener, mover y soltar la mesa de cada reserva | ninguno de Reservas: es Reservas quien llama a sus acciones de plataforma, en la misma transacción |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver reservas | sí | sí | sí | sí | `reservation.view_reservation` |
| Apuntar reservas | sí | sí | sí | sí | `reservation.add_reservation` |
| Cambiar reservas (y su estado) | sí | sí | sí | sí | `reservation.change_reservation` |
| Borrar reservas | sí | sí | no | no | `reservation.delete_reservation` |
| Ver franjas | sí | sí | sí | sí | `reservation.view_timeslot` |
| Crear y quitar franjas | sí | sí | sí | no | `reservation.change_timeslot` |
| Ver bloqueos | sí | sí | sí | sí | `reservation.view_blockeddate` |
| Bloquear y desbloquear fechas | sí | sí | sí | no | `reservation.change_blockeddate` |
| Ver la lista de espera | sí | sí | sí | sí | `reservation.view_waitlistentry` |
| Cambiar la lista de espera | sí | sí | sí | sí | `reservation.change_waitlistentry` |
| Ver ajustes | sí | sí | sí | sí | `reservation.view_settings` |
| Cambiar ajustes | sí | sí | sí | no | `reservation.manage_settings` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).
Sentar pide además «Sentar» de Mesas (`table.add_session`) y «Montar la cuenta» de Ventas
(`sale.add_sale`); apuntar con un cliente nuevo, «Gestionar clientes» de Clientes
(`customer.manage`): los cuatro papeles los tienen.

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `engine.py` (la puerta del
  alta sin base de datos), `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`,
  `locale/`, `frontend/` y un `tests/test_<fichero>.py` por fichero, más
  `tests/test_integration_table.py`, `tests/test_integration_customer.py`,
  `tests/test_integration_schedule.py` (las apps reales, sin dobles) y `tests/test_concurrency.py`
  (hilos y bloqueos de verdad). Por el bucle real del worker, `tests/test_relay.py` (F21, F22: el
  tick del relay con las operaciones de Clientes) y `tests/test_scheduled_release.py` (F13: el tick del
  scheduler). En el navegador, `tests/e2e/reservation-book.spec.ts` (oculto): reservar con mesa, confirmar
  y verla Reservada en el plano de Mesas, sentarla desde el libro (Ocupada, cuenta abierta en Ventas) y
  completarla; editar, cancelar con motivo, no presentado y borrar; confirmar solas; sentar a un grupo y
  ver la mesa Reservada para la reserva siguiente cuando se va; la lista de espera; Disponibilidad y
  Ajustes, en tres tamaños (capturas `APP-RESERVATION-<flujo>-{390,834,1440}`). Lo que falta de
  `@erplora/ui` y de Mesas está en `UI-REQUESTS.md`.
- **`requires = ["table", "customer", "schedule"]`**: la mesa es una clave ajena a `table.Table`; el
  cliente, a `customer.Customer` (`PROTECT`, como Citas); el horario se lee con la operación
  `schedule.hours.for_range`, con `schedule.view` añadido al contexto solo para esa lectura (como
  Citas).
- **Modelos**: `Settings` (una fila), `TimeSlot` (día de la semana, desde, hasta, máximo de reservas y
  de comensales; borrado lógico; sin solapes en el mismo día), `BlockedDate` (todo el día o
  desde–hasta; único por fecha y hora de inicio entre los vivos), `Reservation` (cliente, nombre,
  teléfono, correo, día y hora de pared, duración, comensales, mesa, estado, origen, notas, notas
  internas, hora de cada paso, motivo de cancelación, cuenta de mesa abierta al sentar; borrado
  lógico) y `WaitlistEntry` (cliente, contacto, día, hora preferida, comensales, notas, contactada y la
  reserva en la que se convirtió; borrado lógico). PK UUIDv7.
- **La puerta** (`engine.py`, pura): contacto → comensales → hora pasada / antelación → días máximos →
  día bloqueado → horario del negocio → franja que la cubre → franja con sitio (reservas y comensales)
  → mesa en servicio → mesa libre. La primera que rechaza gana. Comensales, antelación, días máximos y
  la franja llena solo atan a internet y WhatsApp; el personal llena una franja llena con
  `overbook=true`: la negativa (409 `reservation.no_capacity`) lo dice en `fields.overbook`, que es lo
  que leen la pantalla, la API y el asistente para ofrecer «Reservar igualmente». Un cambio que no mueve el día ni la hora no vuelve a mirar el
  reloj. Cuenta como el producto actual: las
  reservas no canceladas ni no presentadas de la franja (también sentadas y completadas); una mesa se
  pisa con las pendientes, confirmadas y sentadas.
- **Concurrencia**: toda escritura que reserva (alta, cambio, conversión) bloquea primero la fila de
  `Settings` (`select_for_update`): las reservas de un negocio van en fila, y la puerta se comprueba
  ya con el bloqueo puesto. Dos reservas a la vez sobre el último hueco o la misma mesa y hora dejan
  una (`tests/test_concurrency.py`, con la fila ya creada: crearla también pone en fila por su índice
  único y escondería si el bloqueo funciona; probado quitando el bloqueo, los tres casos fallan). Los
  cambios de estado bloquean su reserva.
- **Con Mesas, en la misma transacción** (la única vía): confirmar (o nacer confirmada),
  cancelar, no presentada y borrar llaman por nombre a `table.hold.sync_reservation`; cambiar una
  confirmada la llama con los datos nuevos (mueve la retención) o, si se queda sin mesa, a
  `table.hold.move_reservation` con `table_id` vacío; sentar llama a `table.session.open` con su
  `reservation_id` (con la sesión de quien sienta: abre la cuenta en Ventas y gasta solo la retención de
  esta reserva, si ya entró en su ventana) y suelta con `table.hold.release` la que aún no había entrado. Las acciones de plataforma
  de Mesas (`table.system`) se llaman con ese único permiso añadido al contexto de quien actúa. Si Mesas
  rechaza, se deshace todo. Los avisos `status_changed` y `updated` se siguen grabando, pero Mesas ya no
  reacciona a ellos (2026-10-21, APP-TABLE): entregados después por el relay, re-aplicaban la reserva tal
  como era (un «confirmada» viejo volvía a retener la mesa de un grupo ya sentado).
- **Sentar con la mesa ya ocupada** solo marca la reserva si su retención se gastó y ninguna otra reserva
  es dueña de la cuenta sentada (`table_session_id`): sentar desde el plano no dice de qué reserva es el
  grupo y Mesas gasta todas las retenciones de la mesa dentro de la hora, así que la retención gastada
  sola no prueba que sea este grupo.
- **RGPD en el registro de avisos**: la reacción a `customer.customer.erased` vacía también `guest_name`
  en los `status_changed` y `updated` de sus reservas (esos avisos llevan el nombre).
- **Clientes**: sin ficha elegida y con teléfono, se busca la ficha viva con ese número
  (`customer.customer.by_phone`; entre varias, la del mismo nombre sin mayúsculas ni acentos, si no la
  primera) y, si no hay, se crea (`customer.customer.create`, origen Teléfono, En el local, WhatsApp o
  Web), antes de la puerta: un teléfono que Clientes rechaza se dice primero. La reserva copia el
  nombre, el teléfono y el correo de la ficha elegida si no se escriben otros; con la ficha encontrada o
  creada por el teléfono, el teléfono queda como lo guarda Clientes (+34600111222).
- **Hora del negocio**: fase 1, `settings.TIME_ZONE` (Europe/Madrid). El día y la hora se guardan de
  pared; «ahora» es la hora del negocio.
- **Asistente**: cada operación declara `ai` (descripción; `risk: "high"` en cancelar, no presentado y
  todo borrado) y cada campo de `schemas.py` su `description`.
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17): ajustes, franjas, bloqueos,
  reservas y lista de espera; ids y fechas en solo lectura. Lo que guarda no pasa por las operaciones
  ni deja aviso.
- **Tarea programada**: `release_unconfirmed_reservations` (`reservation.reservation.release_unconfirmed`,
  cada 15 minutos, en UTC, `collapse`); la corre el worker (`base/scheduler.py`) como sistema en el ámbito
  fijo `WORKER_SCOPE_SLUG` de la fase 1: libera las pendientes de toda la BD compartida, pero su aviso vivo
  sale solo por ese ámbito (F13 `parcial` hasta el recorrido por `hub_due`).
- **Relay del outbox** (`base/relay.py`, en el worker desde el 2026-10-21): entrega `customer.customer.merged`
  y `customer.customer.erased` a `events.REACTIONS` (F21, F22), como sistema en el ámbito del hub que anotó
  el aviso; idempotentes.
- **Quién juzga un cambio** (F08, F18): `judged_as` pasa a la puerta el origen del personal (`phone`) en
  todo cambio del personal, aunque la reserva naciera por internet o WhatsApp (duda 8), y el de un cliente
  que reserva solo cuando llega `on_behalf_of`. Con `on_behalf_of`, `_named` rechaza con 409
  `reservation.customer_mismatch` toda reserva que no sea de esa ficha (también una inexistente o borrada,
  antes que su estado) y `update` rechaza la mesa, las notas internas y `overbook` con 409
  `reservation.staff_only_field` (el `customer_identity_refusal` y `STAFF_ONLY_UPDATE_FIELDS` del módulo
  viejo).

### Cambios frente al producto actual

1. **Horario del negocio**: una reserva tiene que empezar con el negocio abierto (Horarios); antes solo
   contaban las franjas.
2. **Mesa en pantalla**: el formulario elige la mesa entre las libres a esa hora (antes solo el
   asistente asignaba mesa) y **una mesa no se reserva dos veces a la misma hora** (antes no se
   comprobaba).
3. **Confirmar retiene la mesa también cuando la reserva nace confirmada** y cambiar la hora de una
   confirmada mueve la retención (antes solo al pulsar «Confirmar» y solo al cambiar la mesa).
4. **Sentar abre la cuenta de la mesa** en el mismo paso y la retención se gasta (antes eran dos
   acciones en dos apps).
5. **Editar, No presentado, Cancelar con motivo y Borrar tienen pantalla** (antes solo el asistente).
6. **El empleado confirma, sienta, cambia, cancela y lleva la lista de espera** (antes solo el
   responsable; duda 1).
7. **Máximo de comensales por franja**, opcional, además del de reservas (duda 2).
8. **Ajustes tiene pantalla** (antes solo el asistente) y el teléfono es obligatorio de fábrica y
   siempre (antes no lo era hasta guardar cualquier ajuste).
9. **La duración por defecto vale para toda reserva** (antes la reserva a mano duraba siempre 120
   minutos y solo la conversión la usaba).
10. **Las reglas de reserva (comensales, antelación, días máximos) son para internet y WhatsApp**; el
    personal reserva desde ya, nunca en una hora pasada (antes también frenaban al personal).
11. **Bloquear por horas tiene pantalla** (antes solo el día entero).
12. **Las franjas de un mismo día no se pisan** (antes podían solaparse y contar dos veces).
13. **Cada motivo de rechazo tiene su texto**, también al cambiar (antes el cambio daba un único «no se
    pudo»).
14. **La reserva guarda su origen** (Teléfono, En el local, Lista de espera, WhatsApp, Internet).
15. **La ficha del cliente la busca o la crea el servidor** (antes la pantalla), así también por el
    asistente y la API.
16. **Las fechas y horas se escriben con los campos del navegador**, como Citas (antes, texto en el
    orden del idioma).
17. **El personal puede llenar una franja llena a sabiendas**, tras un aviso (antes nunca; duda 8).
18. **La lista de espera no pide teléfono** (antes la pantalla lo exigía; duda 7).
19. **El personal cambia la reserva que el cliente hizo solo sin sus reglas** (comensales, antelación,
    días máximos; y con «Reservar igualmente» en una franja llena): antes el cambio se juzgaba con las
    reglas del origen de la reserva (duda 8).
20. **Sentar desde Reservas gasta solo la retención de esa reserva** (TABLE-F28): antes gastaba todas
    las de la mesa dentro de la hora, y la reserva siguiente de la misma mesa dejaba de verse Reservada.

### Lo que NO hace, a propósito

- No cobra depósitos, señales ni cargos por no presentarse.
- No envía correos, SMS ni recordatorios (los ajustes de correo del producto actual, que no enviaban
  nada, no se portan).
- No pinta ni ocupa el plano: eso es de Mesas.
- No es la agenda de citas por profesional (Citas) ni la reserva web.
- No sincroniza con calendarios externos.

### Lo que queda fuera

- **La conversación de WhatsApp** (F17, F18): pedir los comensales y ofrecer horas libres, y cambiar o
  anular desde el mensaje son de la segunda parte de la Bandeja de WhatsApp (`whatsapp_inbox` F24, F25, que
  esperan al asistente del Hub). Reservas ya tiene su parte: la reserva del cliente con sus reglas y la puerta
  «en nombre del cliente». El aviso al confirmar (F19) ya sale: lo manda la receta `reservation_confirmed` de
  `whatsapp_inbox` (WHATSAPP_INBOX-F26) con el `status_changed` confirmado y el día y la hora listos para el
  mensaje (`date_label`, `time_label`; `tests/test_queries.py`, `tests/test_services.py`;
  `apps/whatsapp_inbox/tests/test_relay_notify.py`).
- **Asignación automática de mesa y juntar mesas para un grupo grande**: una reserva tiene una mesa
  (la retención de Mesas es una por reserva); juntar mesas espera a que Mesas tenga mesas unidas
  (su duda 3).
- **El aviso al momento de la liberación de pendientes en cada negocio** (F13): en la fase 1 la tarea
  corre en un único ámbito fijo; llega con el recorrido por negocio de la fase 2.
- **Que sentar desde el plano marque la reserva** Sentada: Mesas gasta la retención, pero no sabe de la
  reserva; se marca en Reservas con «Sentar» (que entonces no abre otra cuenta).
- **La cola de la puerta con espera estimada y aviso por SMS** (duda 6): necesita mensajería; la lista de
  espera sirve hoy para la puerta y para otros días, sin avisos.
- **Franjas que cruzan la medianoche**: una franja termina el mismo día (hasta las 23:59).

### Dudas abiertas

Resueltas en esta versión (por mercado, «Referencia adoptada»): 1, 2, 3, 4, 5, 6, 7 y 8. Siguen fuera
del MVP: asignación automática y mesas unidas (5) y el aviso por WhatsApp (F19).

### Paridad con el producto actual

Operaciones (21 commands y 9 queries del `module.json`):

| Producto actual | Aquí | Motivo |
|---|---|---|
| `reservations.reservations.list` / `.get` | `reservation.reservation.list` / `.get` | — |
| `reservations.slots.count_for`, `reservations.day.summary`, `reservations.blocked_dates.on_date` | `reservation.availability.day` | Una sola lectura del día: ocupación, cifras y bloqueos, más el horario |
| `reservations.timeslots.list` | `reservation.time_slot.list` | — |
| `reservations.blocked_dates.list` | `reservation.blocked_date.list` | — |
| `reservations.waitlist.list` | `reservation.waitlist.list` | Orden de llegada estable |
| `reservations.settings.get` | `reservation.settings.get` | Con la zona horaria |
| — | `reservation.availability.tables` | Nueva: mesas libres (F23) |
| `reservations.reservations.create` (+ `_create_gated`) | `reservation.reservation.create` | La puerta en `engine.py` y la transacción |
| `reservations.reservations.update` (+ `_apply_update`) | `reservation.reservation.update` | Cada rechazo con su motivo |
| `reservations.reservations.set_status` (+ `_apply_status`) | `.confirm`, `.seat`, `.complete`, `.cancel`, `.no_show` | Una acción por paso: el asistente y su riesgo |
| `reservations.reservations.delete` | `reservation.reservation.delete` | — |
| `reservations.reservations.release_unconfirmed` | `reservation.reservation.release_unconfirmed` | — |
| `reservations.timeslots.create` / `.delete` | `reservation.time_slot.create` / `.delete` | Sin solapes |
| `reservations.blocked_dates.create` / `.delete` | `reservation.blocked_date.create` / `.delete` | — |
| `reservations.waitlist.create` / `.delete` | `reservation.waitlist.create` / `.delete` | — |
| `reservations.waitlist.update` (+ `_waitlist_update`, `_waitlist_promote`) | `reservation.waitlist.update` + `reservation.waitlist.convert` | Convertir es su propia acción |
| `reservations.settings.upsert`, `reservations.settings.set_auto_confirm` | `reservation.settings.update` | Guarda solo lo que se envía: cubre los dos |
| `reservations._on_customer_merged` / `_on_customer_anonymized` | `reservation.customer.reassign` / `.erase` | — |

Pantallas: Reservas (barra del día, tabla, alta, acciones), Lista de espera y Disponibilidad
(Ocupación, Franjas, Fechas bloqueadas), con las mismas columnas, textos, vacíos y errores; se añaden
Editar, No presentado, Cancelar con motivo, Borrar, la Mesa en el formulario, el máximo de comensales,
el bloqueo por horas y la pestaña Ajustes. Lo que no se porta: la tabla guardia `reservations__gate`
(la puerta es Python en la transacción), `time_slot_duration` (no lo usaba nada) y los ajustes de
correo y recordatorio (no enviaban nada).

## Investigación de mercado

Hecha el 2026-10-15 con la skill `market-decision` (ayudas públicas de cada producto; los foros de
Reddit y de Toast no devolvieron hilos útiles; la ayuda de SevenRooms es privada y la de OpenTable solo
se lee por sus fragmentos indexados). Un producto por fila, su fuente al lado.

### Duda 1 — ¿Quién gestiona la reserva en sala?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Toast Tables | El host cambia cualquier estado, edita y lleva la espera; configurar es del gerente | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |
| ResDiary | Usuario general gestiona reservas; supervisor y gerente se saltan reglas | https://help-resdiary.theaccessgroup.com/en/articles/12107884-create-or-edit-your-users |
| Zenchef | El miembro trabaja; las acciones de gerente piden su PIN | https://help.zenchef.com/hc/en-gb/articles/39168951890973-Staff-PIN-give-every-team-member-their-own-identity-on-a-shared-device |
| Resy | Cancelar no está protegido; se protegen turnos, bloqueos y plano | https://helpdesk.resy.com/en_us/user-permissions-r1zCWDmU_ |
| Eat App | Staff crea y edita; borrar y bloquear franjas son permisos aparte | https://restaurant.eatapp.co/knowledge/setting-up-permissions-and-preferences |
| Tablein | Staff entra en calendario, plano y lista; manager, todo | https://help.tablein.com/user-accounts |
| easyTable | User gestiona reservas; ajustes, el super user | https://help.easytable.com/?p=410 |
| Oracle Simphony | El personal crea, edita y cancela desde la lista | https://docs.oracle.com/en/industries/food-beverage/simphony/19.7/sipou/c_reservations_list.htm |

**Gana:** el personal de sala hace el día a día (alta, cambio, estados, cancelar, no presentado, lista
de espera); al gerente le quedan configuración y bloqueos; borrar, al administrador.

### Duda 2 — ¿El aforo de la franja en reservas o en comensales?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Toast Tables | Comensales cada 15 min | https://intercom.help/toast-central/en/articles/14187736-toast-tables-faq |
| OpenTable | Tope de comensales o de grupos | https://support.opentable.com/s/article/flow-controls?language=en_US |
| Resy | Comensales por intervalo | https://helpdesk.resy.com/en_us/how-to-setup-flexible-seating-to-maximize-covers-BkL3bvQLO |
| Eat App | Comensales por franja y total del turno | https://restaurant.eatapp.co/knowledge/how-to-add-a-new-shift |
| ResDiary | Reservas, comensales o ambos; cierra el primero | https://help-resdiary.theaccessgroup.com/en/articles/12082778-limit-your-covers-or-bookings-per-time-slot |
| HostMe | Comensales y reservas por franja | https://help.hostmeapp.com/en/articles/4473275-understand-cover-pacing |
| Zenchef | Stock de comensales por servicio | https://help.zenchef.com/hc/en-gb/articles/4402475918865-How-to-activate-Table-Inventory |
| Odoo | Capacidad por participantes | https://www.odoo.com/documentation/19.0/applications/productivity/appointments.html |

**Gana:** los dos límites, cerrando con el primero que se alcanza; aquí se conserva el de reservas del
producto actual y se añade el de comensales, opcional.

### Duda 3 — ¿Sentar la reserva sienta la mesa y abre la cuenta?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Toast Tables | Sentar abre el pedido; no deja sentar en una mesa ocupada | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |
| Lightspeed K-Series | Sentar abre el pedido; con un pedido abierto en la mesa, falla | https://k-series-support.lightspeedhq.com/hc/en-us/articles/38042219443483-Managing-reservations-at-the-POS |
| TheFork + Lightspeed | Llegado o sentado abre el pedido si la mesa está libre | https://k-series-support.lightspeedhq.com/hc/en-us/articles/26405089037467-Setting-up-TheFork-integration |
| Square + OpenTable | Sentar crea el ticket de la mesa | https://squareup.com/help/us/en/article/7878-opentable-and-square-for-restaurants |
| Zenchef + Lightspeed | Sentado en cualquiera de los dos; pagar termina la reserva | https://help.zenchef.com/hc/en-gb/articles/360016862217-Lightspeed-K-Series |
| Resy | Dos pasos emparejados por mesa y hora | https://helpdesk.resy.com/pos-integrations-HkUQN3s5u |
| Odoo PoS | Etapa de la reserva y abrir la mesa, por separado | https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/restaurant.html |
| TablesReady | Check-in y «Serve»; sin TPV | https://support.tablesready.com/article/155-how-to-use-table-management |

**Gana:** un gesto sienta la reserva, ocupa la mesa y abre la cuenta; una mesa ocupada se rechaza.

### Duda 4 — ¿Qué acciones hay en la lista del anfitrión?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Zenchef | Estado (confirmar, llegado, terminado, no-show, cancelar), mesa y editar | https://help.zenchef.com/hc/en-gb/articles/360016773958-How-to-configure-the-choice-of-actions-on-my-reservations |
| Toast Tables | Sentar, terminado, no-show, cancelar y editar | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |
| Resy | Cancelar o cambiar desde la fila | https://helpdesk.resy.com/en_us/how-to-cancel-or-change-a-reservation-SyPWGvX8_ |
| CoverManager | Estado, editar y asignar mesa desde la lista | https://apps.apple.com/es/app/covermanager/id1289393829 |
| Lightspeed | Asignar mesa, sentar y editar | https://k-series-support.lightspeedhq.com/hc/en-us/articles/38042219443483-Managing-reservations-at-the-POS |
| Oracle Simphony | Crear, editar y cancelar con motivo | https://docs.oracle.com/en/industries/food-beverage/simphony/19.7/sipou/t_reservations_cancel.htm |
| Odoo PoS | Etapas, editar y borrar | https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/restaurant.html |
| ResDiary | Asignar, mover o unir mesas desde la lista | https://help-resdiary.theaccessgroup.com/en/articles/12301575-manage-your-expected-arrival-list |

**Gana:** todo en la fila: estados, editar (con la mesa) y cancelar con motivo opcional.

### Duda 5 — ¿Dos reservas en la misma mesa? ¿Asignación automática?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| OpenTable | Asigna solo y solo usa mesas libres toda la estancia | https://support.opentable.com/s/article/Booking-Rules?language=en_US |
| Resy | Pre-asigna; un solape ofrece cambiar o sobrevender | https://helpdesk.resy.com/how-to-change-table-assignment-in-resyos-HJpGvQ8O |
| Toast Tables | Los solapes salen en rojo (aviso) | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |
| Zenchef | Asignación automática opcional, agrupaciones de mesas | https://help.zenchef.com/hc/en-gb/articles/4402475918865-How-to-activate-Table-Inventory |
| Eat App | Conflictos como error o aviso según el usuario | https://restaurant.eatapp.co/knowledge/setting-up-permissions-and-preferences |
| Odoo | Asignación automática y recursos enlazados | https://www.odoo.com/documentation/19.0/applications/productivity/appointments.html |
| ResDiary | Combinar varias mesas | https://help-resdiary.theaccessgroup.com/en/articles/12301575-manage-your-expected-arrival-list |
| Resmio | Solo ofrece las mesas libres por defecto | https://www.resmio.com/en/help/managing-reservations/ |

**Gana en el mercado:** asignación automática editable y aviso del solape al personal. **Aquí:** se
ofrecen las mesas libres (como Resmio) y el solape se rechaza siempre, por el encargo de Ioan («dos
reservas para la misma mesa y hora → una»): contradicción señalada. Asignación automática y mesas
unidas, fuera.

### Duda 6 — ¿Lista de espera de la puerta o para días llenos?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Resy | Cola de hoy y «Notify» para fechas futuras | https://helpdesk.resy.com/en_us/what-is-notify-and-how-does-it-work-BJrJzPQLu |
| OpenTable | Cola con SMS y «Notify me» | https://support.opentable.com/s/article/Direct-Messaging-Restaurant-FAQ?language=en_US |
| ResDiary | Lista del día y lista para franjas llenas | https://help-resdiary.theaccessgroup.com/en/articles/12304331-manage-your-waitlist |
| TheFork Manager | Lista de la puerta y lista virtual | https://www.theforkmanager.com/es/blog/lista-de-espera-restaurante-10-estrategias-clave-para-gestionarla-y-como-digitalizarla |
| CoverManager | Cola con posición y SMS; listas de reservas | https://www.covermanager.com/en/solution/virtual-waitlist |
| Toast Tables | Solo la cola de hoy | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |
| Zenchef | Solo para servicios futuros llenos | https://help.zenchef.com/hc/en-gb/articles/4404685613969-How-to-set-up-and-use-the-waiting-list |
| Tablein | Estados de espera y en cola | https://help.tablein.com/reservation-statuses |

**Gana en el mercado:** dos listas, con aviso por SMS. **Aquí:** una lista por día y hora, en orden de
llegada, sin avisos (no hay mensajería): la cola con espera estimada queda fuera.

### Duda 7 — ¿Teléfono y correo obligatorios?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Resy | Teléfono obligatorio, correo opcional | https://helpdesk.resy.com/how-to-book-a-reservation-in-resyos-app-rJxfGvXIu |
| Zenchef | Campos obligatorios configurables | https://help.zenchef.com/hc/en-gb/articles/360000079577-How-do-I-add-a-booking-to-my-booking-list |
| Resmio | El restaurante elige qué es obligatorio | https://www.resmio.com/en/help/managing-reservations/ |
| resOS | Teléfono, correo o ambos, por ajuste | https://resos.com/mailchimp-and-mandatory-fields/ |
| Square Appointments | El personal reserva con teléfono; en línea, correo y teléfono | https://community.squareup.com/t5/Appointments-Bookings/Email-required-for-appointment/m-p/670172 |
| Eat App | En línea, nombre, teléfono y correo | https://restaurant.eatapp.co/knowledge/creating-reservations |
| Oracle Simphony | Teléfono y correo opcionales | https://docs.oracle.com/en/industries/food-beverage/simphony/19.7/sipou/t_reservations_add.htm |
| Toast Tables | En la espera, nombre y teléfono opcionales | https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist |

**Gana:** reserva con nombre y teléfono (configurable), correo opcional; la espera, sin obligatorios.

### Duda 8 — ¿Las reglas de la reserva en línea atan al personal?

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Toast Tables | El tope es duro solo en línea; el host recibe un aviso | https://support.toasttab.com/en/article/Getting-Started-Toast-Waitlist |
| Resy | Las reservas de la casa pueden superar el ritmo | https://helpdesk.resy.com/en_us/how-to-setup-flexible-seating-to-maximize-covers-BkL3bvQLO |
| ResDiary | Supervisor y gerente se saltan el límite | https://help-resdiary.theaccessgroup.com/en/articles/12082778-limit-your-covers-or-bookings-per-time-slot |
| Zenchef | Antelación y cierre previo son de la reserva en línea | https://help.zenchef.com/hc/en-gb/articles/12503790929821-How-to-close-the-booking-availability-as-the-shift-approaches |
| HostMe | El host supera el límite con aviso | https://help.hostmeapp.com/en/articles/4473275-understand-cover-pacing |
| OpenTable | El personal puede sobrevender con aviso | https://support.opentable.com/s/article/Resolving-table-conflicts-using-timeline-in-GuestCenter?language=en_US |
| Eat App | Sobrevender y saltar bloqueos, por tipo de usuario | https://restaurant.eatapp.co/knowledge/setting-up-permissions-and-preferences |
| TableCheck | Nadie reserva una hora pasada: es un walk-in | https://support-restaurants.tablecheck.com/hc/en-us/articles/900000845246-Creating-a-Walk-In |

**Gana:** las reglas en línea solo atan a la reserva en línea; el personal las pasa con un aviso
visible; nunca una hora pasada.
