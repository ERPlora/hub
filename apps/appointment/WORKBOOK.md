# Workbook — Citas (app)
Prefijo: APPOINTMENT
Alcance MVP: peluquería
Estado de la app: hecha (servidor y páginas); lo que queda fuera está en «Lo que queda fuera»

> Manual de usuario y especificación de la app `appointment`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Citas del producto actual
> (`modules-workspace/modules/appointments`, `origin/main` `73ab682`, v1.1.151) y de sus
> `workflow/*.md`. Los números de flujo se conservan (`APPOINTMENTS-Fnn` → `APPOINTMENT-Fnn`). Lo que
> cambia frente al producto actual lo dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Citas es **la agenda de un negocio que trabaja con cita previa** (peluquería, estética, barbería).
Cada cita une una clienta de **Clientes**, uno o varios servicios de **Servicios** (corte + color) y
un profesional de **Personal** a una hora, sin pisar el horario del negocio (**Horarios**), el turno ni
las ausencias del profesional ni otra cita suya, y guarda todo lo que le pasa desde que se reserva
hasta que se atiende, se cobra o se anula.

Quién la usa:

- El **empleado** ve **su propia agenda**: reserva citas para sí, las confirma, las empieza, las
  termina, las mueve, las anula y las cobra. Las citas de los compañeros no las ve.
- El **responsable** ve y gestiona la agenda de todo el equipo, y bloquea tiempo.
- El **propietario** y el **administrador**: además borran citas y cambian los ajustes de reserva.
- La **clienta** reserva, mueve y cancela sola cuando el negocio lo permite (por WhatsApp o por la
  reserva online, a través de la API), siempre con las reglas de antelación del negocio.
- El **asistente** (por voz o por texto, con la sesión de quien habla) hace todo lo anterior:
  «mañana a las 10 con Ana para corte a Lucía», «mueve la cita de Lucía al jueves», «cancela la de
  las 12».

## Referencia adoptada

- **Fresha, Vagaro, Mangomint, Square Appointments, Booksy y Phorest**: agenda del día por
  profesional, arrastrar la cita a otra hora o a otro profesional, vista de semana, varios servicios
  en una cita, estados reservada → confirmada → en curso → completada / cancelada / no presentada,
  cobro de la cita en el TPV sin volver a teclearla y política de cancelación que ata a la clienta,
  no al negocio.
- **Google Calendar / RFC 5545**: editar una serie «solo esta cita» o «esta y las siguientes», nunca
  todas, y la serie conserva su hora de pared al cambiar la hora oficial.
- **Mindbody/Booker**: el mostrador puede apuntar una cita que ya ha empezado.
- Decisiones del producto actual que mandan aquí: el horario del negocio solo vive en Horarios, el
  cobro lo hace el TPV (Citas solo anota con qué venta se cobró), el reloj es siempre el del negocio y
  las series se editan con corte.

## Antes de empezar

1. Citas enciende con ella **Clientes**, **Servicios**, **Personal** y **Horarios**, y no se pueden
   apagar mientras Citas esté encendida.
2. En **Servicios**, da de alta los servicios reservables con su precio y su duración, y asigna a cada
   uno los profesionales que lo hacen. Un servicio sin nadie asignado lo puede hacer todo el equipo
   reservable (la regla es de Citas).
3. En **Personal**, da de alta a los profesionales y márcalos **Reservables**. Si quieres que la agenda
   respete su turno, crea su horario semanal; sin horario, solo sus ausencias aprobadas impiden
   reservarle.
4. En **Horarios**, confirma la semana del negocio y pon los festivos. Un día sin ninguna regla de
   horario (ni semana ni excepción) deja reservar a cualquier hora.
5. La agenda pinta siempre el **reloj del negocio** (en la fase 1, Europe/Madrid), nunca el del
   dispositivo: si el dispositivo está en otra zona, un aviso lo dice.
6. Revisa los **Ajustes** de Citas (antelaciones, solapes, cancelación de la clienta, ventana del
   calendario).
7. Para cobrar desde la agenda hace falta **Venta** encendida y poder vender en ella.

## Pantallas

Citas se abre desde el menú **Citas** y tiene dos pestañas: **Agenda** y **Ajustes** (esta solo para
quien puede cambiarlos). Lo que una persona no puede hacer sale en gris o no aparece, y la app lo
rechaza aunque lo intente por la API o por el asistente.

### Agenda
Una barra con el día (‹ fecha › y **Hoy**, y el botón del calendario para saltar a una fecha),
**Filtrar por estado**, el aviso **N por confirmar** cuando hay reservas de clientas pendientes, y el
conmutador **Lista · Por profesional · Periódicas** (en el móvil, solo iconos). En **Por profesional**,
además, **Día · Semana**.

- **Lista**: columnas Hora, Nº, Cliente, Servicio, Profesional y Estado, buscador «Buscar nº, cliente
  o servicio…» y, por fila, **Cobrar, Editar, Confirmar, Iniciar, Completar, No-show, Cancelar,
  Historial y Borrar**. La que no aplica al estado de la cita sale en gris, no se esconde; **Cobrar**
  sale en gris si la cita ya está cobrada y se llama **Ir a la cuenta** mientras su cuenta sigue abierta
  en el TPV (entonces No-show, Cancelar y Borrar salen en gris).
- **Por profesional · Día**: una fila por profesional reservable y una fila «Sin asignar» si hay
  citas sin profesional; las horas del calendario van en horizontal y lo que el negocio tiene cerrado
  o bloqueado sale sombreado (lo cerrado, según Horarios; ahí no se puede tocar para reservar). Un profesional que ya no admite citas (no reservable, inactivo, de baja)
  conserva su fila, detrás de los reservables, los días en que aún tiene citas, y encima de la rejilla
  un aviso «Ana ya no admite citas nuevas: sus citas del día siguen en su fila para que puedas
  pasárselas a otra persona del equipo.». Tocar un hueco abre el alta con ese profesional y esa hora;
  tocar una cita abre su ficha; arrastrar una cita la mueve a otra hora o a otra fila (con el ratón,
  al soltar; en una pantalla táctil, manteniéndola pulsada antes de arrastrar).
- **Por profesional · Semana**: una fila por profesional y una columna por día de la semana, con las
  citas de cada día en orden. Tocar una cita abre su ficha; arrastrarla a otro día u otra fila la
  mueve conservando la hora.
- **Periódicas**: ver la pantalla [Periódicas](#periódicas).
- Botón **Añadir cita** → **Nueva cita**: Cliente (buscador «Busca por nombre o teléfono»; si no está,
  **+ Nuevo cliente** la crea con nombre y teléfono sin salir), Servicios (uno o varios, en orden),
  Profesional (solo los que hacen todos esos servicios), Día, Hora (con las **Horas libres** como
  botones), Min. (la suma de las duraciones, cambiable), Notas para la clienta y Notas internas. Min.
  y el **Total** salen con la duración y el precio propios del profesional elegido para cada servicio
  (Servicios, «Quién lo hace»), o los del catálogo si no tiene; es lo que la cita reserva.
  Avisos: «Esta cita empieza en el pasado…» y el profesional que no hace un servicio.
- **Editar** → **Editar la cita**: Día, Hora, Min., Servicios, Profesional, las notas y **Guardar
  cambios**; debajo, el historial. La clienta no se cambia.
- Diálogos: **Cita solapada** (**Reservar igual** / **Elegir otra hora**), **Editar cita periódica**
  (**Solo esta cita** / **Esta y todas las siguientes**), **Cancelar la cita** (motivo opcional) y
  **Borrar la cita** (confirmación).

### Periódicas
Tercer segmento de la Agenda. Tabla: Cliente, Servicio, Profesional, Repetición (por ejemplo «Cada
semana · lunes · 11:00»), Empieza, Termina («Sin fin», «Tras {n} citas» o la fecha) y **Activa**
(interruptor). Por fila: **Editar serie**, **Reservar citas** y **Borrar** (pide confirmación). El
botón de añadir abre **Nueva cita periódica** (Cliente, Servicios, Profesional, Repetición, Día de la
semana, Empieza el, Hora, Min., «Termina el (opcional)», «Número de citas (opcional)») con **Crear
cita periódica**; editar abre **Editar cita periódica** con «Desde» y **Guardar de esta cita en
adelante**. Tras reservar o guardar sale «{booked} citas reservadas · {skipped} no se han podido
reservar:» con cada fecha y su motivo, y si quedan fechas, «Las fechas desde el {date} aún no están
reservadas: pulsa «Reservar citas» en la serie para reservarlas.».

### Ficha de la cita
Al tocar una cita: número, estado, clienta, servicios con su precio, profesional, hora, notas, si está
cobrada y su **Historial**: cada cambio con su hora en el reloj del negocio, quién lo hizo («Lo pidió
la clienta» cuando fue ella) y qué cambió.

### Ajustes de Citas
Pestaña **Ajustes** (solo para quien puede cambiarlos): «Duración por defecto (minutos)», «Antelación
mínima para reservar (minutos)» (solo para las reservas de la clienta), «Reservar como máximo con esta
antelación (días)» (0 = sin límite), «Permitir citas solapadas», «Permitir que la clienta cancele su
cita», «Antelación mínima para cancelar (horas)», «El calendario empieza a las (hora)», «El calendario
termina a las (hora)», «Intervalo entre huecos (minutos)» y «Confirmar automáticamente las citas que
reserva la clienta»; botón **Guardar**.

### Historial de visitas (en la ficha de Clientes)
Bloque al final de la ficha de una clienta en **Clientes**, aportado por Citas: sus 10 últimas citas,
la más reciente primero, con servicios, profesional, estado y notas (la interna primero).

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado; bajo Servicios y Profesional, «Cargando servicios…» / «Cargando profesionales…». |
| Vacío | «Sin citas para este día.», «Todavía no hay citas periódicas.»; sin profesionales reservables, «Aún no hay profesionales reservables.»; en el alta, «Todavía no hay servicios reservables. Dalos de alta en Servicios.». |
| Error | El aviso de la tabla o de la rejilla con «Reintentar». Un rechazo de un formulario sale dentro del formulario, cada motivo bajo su campo, sin perder lo tecleado; un conflicto (409) sale encima del botón y en un aviso. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |
| Otra zona horaria | «Este dispositivo está en otra zona horaria. La agenda muestra siempre el reloj del negocio: {zona}.» |

Fechas, horas e importes salen con el formato del idioma de quien mira y en el reloj del negocio.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| APPOINTMENT-F01 | Reservar una cita desde la agenda | hecho |
| APPOINTMENT-F02 | Ver qué horas quedan libres | hecho |
| APPOINTMENT-F03 | Confirmar una cita pendiente | hecho |
| APPOINTMENT-F04 | Mover una cita o cambiarle el profesional o los servicios | hecho |
| APPOINTMENT-F05 | Cancelar una cita desde la agenda | hecho |
| APPOINTMENT-F06 | La clienta cancela o mueve su propia cita | hecho (API y asistente; la conversación de WhatsApp es de su app) |
| APPOINTMENT-F07 | Empezar el servicio | hecho |
| APPOINTMENT-F08 | Completar la cita | hecho |
| APPOINTMENT-F09 | Marcar que la clienta no se presentó | hecho |
| APPOINTMENT-F10 | Ver el historial de una cita | hecho |
| APPOINTMENT-F11 | Borrar una cita | hecho |
| APPOINTMENT-F12 | Crear una cita periódica | hecho |
| APPOINTMENT-F13 | Reservar las citas de una serie | hecho |
| APPOINTMENT-F14 | Editar una serie de esta cita en adelante | hecho |
| APPOINTMENT-F15 | Pausar, reactivar o borrar una serie | hecho |
| APPOINTMENT-F16 | Bloquear tiempo en la agenda | hecho (asistente y API; la rejilla lo pinta) |
| APPOINTMENT-F17 | Cobrar la cita en el TPV | hecho (Citas abre la cuenta; ver «Contrato con Ventas») |
| APPOINTMENT-F18 | Cita que reserva la clienta (WhatsApp, reserva online) | hecho (API y asistente) |
| APPOINTMENT-F19 | Ajustar las reglas de reserva | hecho |
| APPOINTMENT-F20 | Ver las citas de una clienta en su ficha | hecho |
| APPOINTMENT-F21 | Reservar varias citas de golpe (bono o curso) | hecho (asistente y API) |
| APPOINTMENT-F22 | Cambiar las notas o el contacto de una cita | hecho |
| APPOINTMENT-F23 | Unir las citas al fusionar dos fichas de clienta | hecho |
| APPOINTMENT-F24 | Vaciar los datos de una clienta al borrarla | hecho |
| APPOINTMENT-F25 | Un profesional se da de baja con citas futuras | hecho |
| APPOINTMENT-F26 | Un servicio se archiva con series que lo usan | hecho |
| APPOINTMENT-F27 | Ver la agenda de la semana | hecho |

### APPOINTMENT-F01 Reservar una cita desde la agenda
Estado: hecho
Actor: empleado (para sí), responsable, asistente
Pantalla: Agenda
Pasos:
1. Pulsa **Añadir cita**, o en «Por profesional» toca un hueco libre (rellena profesional y hora).
2. Elige la clienta (se busca por nombre, teléfono o email; si no está, **+ Nuevo cliente** la crea con
   nombre y teléfono), uno o varios servicios y el profesional. Con servicios elegidos solo salen los
   profesionales **Activos y Reservables que los hacen todos**; si un servicio no tiene a nadie
   asignado, para ese servicio vale todo el equipo reservable. «Min.» se rellena con la suma de las
   duraciones (la propia del profesional si la tiene, si no la del catálogo).
3. Escribe el día y toca una de las **Horas libres** (o escribe otra hora).
4. Pulsa **Añadir cita**. Si el negocio permite solapes y esa hora choca con otra cita del
   profesional, responde a «Cita solapada».
5. La cita aparece como **Confirmada** con su número `APT-AAAAMMDD-NNNN`.
Entra: la ficha de la clienta (Clientes), los servicios con su precio y duración (Servicios), el
profesional y quién hace qué (Personal y Servicios), el horario del negocio (Horarios) y el turno y las
ausencias del profesional (Personal).
Sale: la cita con el nombre, el teléfono y el email de la clienta y el nombre, precio y duración de
cada servicio **congelados** (cambiar el catálogo después no cambia la cita), su línea «Reservada» en
el historial y el aviso de cita creada (`appointment.appointment.created`).
Si falla: el motivo sale dentro del panel, sin perder lo tecleado: fuera del horario del negocio, el
profesional no trabaja a esa hora, franja bloqueada, el profesional ya tiene una cita
(`appointment.slot_taken`), demasiado lejos, la clienta, el servicio o el profesional no existen o no
se pueden reservar. Desde el mostrador ni la antelación mínima ni una hora ya pasada rechazan (la
hora pasada solo avisa antes de guardar). Dos personas que reservan a la vez el mismo hueco del mismo
profesional: entra una y la otra recibe el rechazo.

### APPOINTMENT-F02 Ver qué horas quedan libres
Estado: hecho
Actor: empleado, asistente, clienta
Pantalla: Agenda (alta y edición)
Pasos:
1. Con servicios, profesional y día elegidos aparecen las **Horas libres** como botones.
2. Las horas candidatas salen cada «Intervalo entre huecos» dentro de la ventana del calendario
   («empieza a las», «termina a las»). Solo sale la que cabe entera: dentro del horario del negocio
   (Horarios: el tramo de ese día o la madrugada del anterior), dentro del turno del profesional y fuera
   de sus ausencias (Personal), sin bloqueo y sin otra cita suya; con los solapes permitidos, una hora
   ocupada también sale. La cita puede terminar justo a la hora de cierre.
3. Desde el mostrador salen también las horas dentro de la antelación mínima (marcadas), nunca las ya
   pasadas; a la clienta, solo las que respetan la antelación mínima.
4. Sin profesional (el asistente: «¿qué horas hay mañana para corte?»), cada hora dice qué
   profesionales la tienen libre.
5. Al preguntar si una hora concreta se puede reservar, se contesta por qué no; con qué citas choca se
   dice solo a quien puede ver esa agenda (a un empleado, de un compañero, solo «ya tiene una cita»).
Entra: el horario del negocio, el turno y las ausencias, los bloqueos, las citas y los ajustes.
Sale: la lista de horas; no guarda nada.
Si falla: «No se han podido cargar las horas libres» con **Reintentar**; se puede escribir una hora y
la reserva se juzga al guardar. Sin horas: «No quedan horas libres ese día…».

### APPOINTMENT-F03 Confirmar una cita pendiente
Estado: hecho
Actor: empleado (las suyas), responsable, asistente
Pantalla: Agenda
Pasos:
1. Entra desde el aviso **N por confirmar** o busca la cita **Pendiente**.
2. Pulsa **Confirmar** en su fila.
3. La cita pasa a **Confirmada** y el historial dice «Confirmada».
Entra: una cita pendiente (la que reservó la clienta con la confirmación automática apagada).
Sale: la cita confirmada, su línea de historial y el aviso `appointment.appointment.confirmed`.
Si falla: «Esta cita ya no se puede confirmar: ya no está pendiente.»; no se escribe nada.

### APPOINTMENT-F04 Mover una cita o cambiarle el profesional o los servicios
Estado: hecho
Actor: empleado (las suyas), responsable, asistente
Pantalla: Agenda
Pasos:
1. Pulsa **Editar** (o toca la cita en «Por profesional»): se abre «Editar la cita».
2. Cambia Día, Hora, Min., Servicios o Profesional y pulsa **Guardar cambios**. Si la cita es de una
   serie, elige **Solo esta cita** o **Esta y todas las siguientes** (APPOINTMENT-F14).
3. Atajo: en «Por profesional» arrástrala a otra hora, otro día u otra fila. Arrastrando no se lleva a
   una hora ya pasada (eso, desde el panel).
4. La cita conserva su número y el historial dice «Cambio de hora», «Cambio de profesional» o «Cambio
   de servicio».
Entra: una cita **Pendiente** o **Confirmada**.
Sale: la cita movida (servicios nuevos traen su nombre y precio del catálogo y su duración, la propia
del profesional si la tiene; un profesional nuevo conserva el precio y la duración), su historial y el
aviso `appointment.appointment.rescheduled`.
Si falla: el motivo en el panel y en un aviso; un bloque arrastrado vuelve a su sitio. Una cita en
curso, completada, cancelada o no presentada no se mueve (**Editar** sale en gris).

### APPOINTMENT-F05 Cancelar una cita desde la agenda
Estado: hecho
Actor: empleado (las suyas), responsable, asistente
Pantalla: Agenda
Pasos:
1. Pulsa **Cancelar** en una cita pendiente, confirmada o no presentada.
2. «Cancelar la cita de Lucía (martes 14, 10:00)?» con el motivo opcional; pulsa **Cancelar la cita**.
3. La cita pasa a **Cancelada** (el hueco queda libre) y el historial dice «Cancelada», quién y el
   motivo.
Sale: el aviso `appointment.appointment.cancelled`.
Si falla: «Esta cita ya no se puede cancelar en su estado actual.» (en curso, completada o ya
cancelada); con su cuenta abierta en el TPV, «Esta cita tiene una cuenta abierta en el TPV: cóbrala o
anúlala allí primero.» (`appointment.check_open`).

### APPOINTMENT-F06 La clienta cancela o mueve su propia cita
Estado: hecho (API y asistente)
Actor: clienta (a través de WhatsApp o la reserva online)
Pantalla: ninguna
Pasos:
1. La automatización pide cancelar o mover **en nombre de la clienta**, diciendo quién es.
2. La cita tiene que ser suya; si no lo es, se contesta igual que si no existiera (no se deja
   averiguar qué citas hay).
3. Para cancelar se aplica la política: «Permitir que la clienta cancele su cita» y «Antelación mínima
   para cancelar».
4. Para mover se aplican la antelación mínima y las mismas reglas que una reserva de la clienta.
5. En el historial queda «Lo pidió la clienta» con el motivo, y también quién del equipo lo anotó.
6. Hacerlo en nombre de la clienta no da más permisos: quien lo anota solo cambia las citas que ya
   podía cambiar (un empleado, las suyas, y no se las pasa a un compañero).
Si falla: `appointment.customer_cancellation_disabled`, `appointment.cancellation_notice_required`,
`appointment.too_soon`, `appointment.appointment_not_found` o `permission_denied`.

### APPOINTMENT-F07 Empezar el servicio
Estado: hecho
Actor: empleado (las suyas), responsable
Pantalla: Agenda
Pasos:
1. Cuando llega la clienta, pulsa **Iniciar** en su cita pendiente o confirmada.
2. La cita pasa a **En curso** y el historial dice «Servicio iniciado».
Sale: el aviso `appointment.appointment.started`.
Si falla: «Esta cita no se puede iniciar en su estado actual.»

### APPOINTMENT-F08 Completar la cita
Estado: hecho
Actor: empleado (las suyas), responsable
Pantalla: Agenda
Pasos:
1. Al terminar, pulsa **Completar** en la cita en curso (o confirmada).
2. La cita pasa a **Completada**. Cobrarla también la completa (APPOINTMENT-F17).
Sale: el aviso `appointment.appointment.completed`.
Si falla: «Esta cita no se puede completar en su estado actual.»

### APPOINTMENT-F09 Marcar que la clienta no se presentó
Estado: hecho
Actor: empleado (las suyas), responsable
Pantalla: Agenda
Pasos:
1. Pasada la hora de la cita, pulsa **No-show** en una cita pendiente o confirmada.
2. La cita pasa a **No-show**, el hueco se libera y el historial dice «No se presentó».
Sale: el aviso `appointment.appointment.marked_no_show`.
Si falla: antes de su hora, «Todavía no es la hora de esta cita: no se puede marcar como no
presentada.»; en otro estado, «Esta cita no se puede marcar como no presentada en su estado actual.»;
con su cuenta abierta en el TPV, `appointment.check_open`.

### APPOINTMENT-F10 Ver el historial de una cita
Estado: hecho
Actor: empleado (las suyas), responsable
Pantalla: Agenda
Pasos:
1. Pulsa **Historial** en la fila (en cualquier estado) o abre la ficha de la cita.
2. Cada cambio con su hora en el reloj del negocio, quién lo hizo («Lo pidió la clienta» si fue ella) y
   qué cambió (de qué profesional o servicio a cuál, y la nueva hora).
Si falla: «No se pudo cargar el historial de la cita.»

### APPOINTMENT-F11 Borrar una cita
Estado: hecho
Actor: propietario, administrador
Pantalla: Agenda
Pasos:
1. Pulsa **Borrar** y confirma «¿Borrar la cita APT-…? En el día a día es mejor Cancelar, que conserva
   el registro.».
2. La cita desaparece de la agenda (queda archivada, no destruida).
Entra: una cita pendiente, confirmada, cancelada o no presentada que no esté cobrada.
Sale: el aviso `appointment.appointment.deleted`.
Si falla: «Esta cita no se puede borrar: está en curso, completada o cobrada.»; con su cuenta abierta
en el TPV, `appointment.check_open`.

### APPOINTMENT-F12 Crear una cita periódica
Estado: hecho
Actor: empleado (para sí), responsable, asistente
Pantalla: Periódicas
Pasos:
1. En **Periódicas**, pulsa añadir: «Nueva cita periódica».
2. Elige la clienta, los servicios, el profesional (solo los que los hacen), la repetición (cada día,
   cada semana, cada dos semanas o cada mes), el día de la semana si aplica, el día de inicio, la hora,
   los minutos y, si quieres, «Termina el» o «Número de citas».
3. Pulsa **Crear cita periódica**: se crea la serie y se reservan sus citas de la ventana
   (APPOINTMENT-F13).
Sale: la serie activa, sus citas y el aviso `appointment.recurring.created`.
Si falla: el motivo en el panel; si la serie se creó y alguna fecha no cupo, se listan con su motivo.

### APPOINTMENT-F13 Reservar las citas de una serie
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Periódicas
Pasos:
1. Pulsa **Reservar citas** en la fila de la serie.
2. Se reservan las fechas de la ventana (de hoy a la antelación máxima; con 0, 90 días) que aún no
   estaban dadas, como mucho 50 por vuelta; la pantalla sigue sola con la siguiente vuelta.
3. Una fecha que no cabe (cerrado, el profesional no trabaja, bloqueo, otra cita, pasado, demasiado
   pronto) se salta y se lista con su motivo; las demás se reservan. Una fecha que se canceló a mano no
   se vuelve a reservar.
4. Si la serie aún no tiene ninguna fecha en la ventana: «Aún no hay nada que reservar: la próxima fecha
   de esta serie, el {fecha}, queda más lejos que la antelación máxima».
Si falla: una serie pausada pide reactivarla (`appointment.recurring_inactive`); una sin fechas, «Esta
cita periódica ya no tiene fechas que reservar.» (`appointment.recurring_ended`).

### APPOINTMENT-F14 Editar una serie de esta cita en adelante
Estado: hecho
Actor: empleado (las suyas), responsable, asistente
Pantalla: Periódicas, Agenda
Pasos:
1. Pulsa **Editar serie**, o mueve en la Agenda una cita de la serie y elige **Esta y todas las
   siguientes**.
2. Cambia la hora, los minutos, la repetición, el día de la semana, el profesional o los servicios; el
   panel dice desde qué fecha se aplica, cuántas citas alcanza y cuántas no se tocarán por estar
   cobradas.
3. Pulsa **Guardar de esta cita en adelante**.
4. Lo anterior a hoy, lo cancelado, lo en curso, lo completado y lo cobrado no se toca. Las citas que
   siguen cayendo en la pauta se mueven; las que ya no caen se cancelan; las que no caben se quedan como
   estaban y se listan; las fechas nuevas se reservan solas (si la serie está activa: editar una serie
   pausada la deja pausada; la que se pausó porque su profesional se dio de baja vuelve a reservar al
   darle otro). Una cita cancelada por no caer ya en la pauta deja libre su fecha: si la pauta vuelve,
   se reserva otra vez. Lo que tiene su cuenta abierta en el TPV tampoco se toca.
Sale: la serie partida en dos (la vieja termina el día antes) o, si el cambio empieza en su primera
fecha, la misma serie editada; el aviso `appointment.recurring.updated`.
Si falla: «Termina el» antes de la fecha del cambio o del inicio de la serie, 422 en ese campo («El
final no puede ser anterior al inicio.»).

### APPOINTMENT-F15 Pausar, reactivar o borrar una serie
Estado: hecho
Actor: empleado (las suyas), responsable
Pantalla: Periódicas
Pasos:
1. Apaga el interruptor **Activa** para que deje de reservar; enciéndelo para reactivarla.
2. **Borrar** pide confirmar «¿Borrar las citas periódicas de {nombre}?»; las citas ya reservadas se
   conservan.
Sale: `appointment.recurring.updated` o `appointment.recurring.deleted`.

### APPOINTMENT-F16 Bloquear tiempo en la agenda
Estado: hecho (asistente y API; la rejilla lo pinta)
Actor: responsable, asistente
Pantalla: Agenda (lo pinta)
Pasos:
1. Pide al asistente un bloqueo con título, inicio y fin, tipo (festivo, vacaciones, descanso,
   mantenimiento u otro), si es de día entero y, si es de un profesional, cuál.
2. Desde ese momento nadie puede reservar en esa franja; sin profesional, bloquea todo el negocio. Un
   bloqueo de día entero cubre esos días enteros, en la reserva y en las horas libres.
Sale: `appointment.blocked_time.created` / `appointment.blocked_time.deleted`.

### APPOINTMENT-F17 Cobrar la cita en el TPV
Estado: hecho
Actor: responsable, empleado (sus propias citas), con permiso de vender en Venta
Pantalla: Agenda
Pasos:
1. Pulsa **Cobrar** en la fila de la cita.
2. Citas abre en el TPV una cuenta enlazada a la cita, titulada «{clienta} · {nº de cita}», con una
   línea **de servicio** por cada servicio de la cita (como si se tocara en «Servicios» del TPV,
   SALE-F38), con el profesional que lo hizo y **al precio con que se reservó** (el propio de la
   profesional incluido), aunque el catálogo haya cambiado desde entonces, y lleva a **Venta** con esa
   cuenta en pantalla (`/sale/pos?order=<cuenta>`).
3. En el TPV se añaden productos o descuentos, un servicio se
   puede pagar con un **bono** de la clienta (SALE-F27) y se cobra como cualquier venta.
4. Una cita tiene **una sola cuenta**: mientras sigue abierta, el botón se llama **Ir a la cuenta** y
   vuelve a ella (nunca abre otra, aunque se pulse a la vez en dos dispositivos); si se anula la cuenta
   en el TPV, **Cobrar** abre una nueva. Con la cuenta abierta, la cita no se cancela, ni se marca como
   no presentada, ni se borra: primero se cobra o se anula la cuenta (decisión de mercado).
5. Al cobrarla, la cita queda **cobrada** y, si no lo estaba, **Completada**; **Cobrar** sale en gris.
   Si la venta se anula, la cita deja de estar cobrada y **Cobrar** vuelve a estar activo.
Entra: una cita pendiente, confirmada, en curso o completada que no esté cobrada.
Sale: la cuenta abierta en Venta (`sale.order.opened`) y aquí `appointment.appointment.check_opened`; al
cobrar, el aviso de Venta `sale.sale.created_from_appointment` y aquí `appointment.appointment.charged`;
al anular la cuenta, `sale.order.voided` y aquí `appointment.appointment.check_closed`.
Si falla: una cita cancelada o no presentada no se cobra (`appointment.cannot_charge`); ya cobrada,
también si el TPV la acaba de cobrar y el aviso aún no ha llegado (`appointment.already_charged`); un
servicio sin
categoría fiscal (`appointment.service_needs_tax_setup`); Venta apagada (`appointment.sale_unavailable`);
un servicio que ya no se ofrece o un precio que no es el de la cita, la frase de Venta
(`sale.service_not_available`, `sale.booked_price_mismatch`); sin permiso de vender, el de Venta.

### APPOINTMENT-F18 Cita que reserva la clienta
Estado: hecho (API y asistente)
Actor: clienta (WhatsApp, reserva online)
Pasos:
1. La automatización ofrece las horas libres (APPOINTMENT-F02) y reserva con origen «WhatsApp» u
   «Online».
2. Con **Confirmar automáticamente las citas que reserva la clienta** encendido (de fábrica), nace
   **Confirmada**; apagado, nace **Pendiente** y suma en **N por confirmar**. Si un servicio de la cita
   tiene **Requiere confirmación** (Servicios), nace **Pendiente** aunque esté encendido.
3. Siempre con la antelación mínima, nunca en el pasado ni encima de otra cita del profesional.

### APPOINTMENT-F19 Ajustar las reglas de reserva
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Cambia los ajustes y pulsa **Guardar**: «Ajustes guardados.» Se guarda solo lo que cambia.
Sale: `appointment.settings.updated`.
Si falla: «Revisa los campos marcados y vuelve a guardar.»; «El calendario termina antes de empezar.»

### APPOINTMENT-F20 Ver las citas de una clienta en su ficha
Estado: hecho
Actor: quien ve la agenda
Pantalla: Historial de visitas (ficha de Clientes)
Pasos:
1. Abre la ficha en **Clientes**: el bloque **Historial de visitas** enseña sus 10 últimas citas.
Si falla: «No se pudo cargar el historial de visitas.» · vacío: «Este cliente aún no tiene citas.»

### APPOINTMENT-F21 Reservar varias citas de golpe (bono o curso)
Estado: hecho (asistente y API)
Pasos:
1. Pide al asistente varias citas para la misma clienta, servicios y profesional (hasta 50).
2. Se reservan todas o ninguna: si una no cabe, se dice cuál y por qué.

### APPOINTMENT-F22 Cambiar las notas o el contacto de una cita
Estado: hecho
Pantalla: Agenda (Editar) y asistente
Pasos:
1. En «Editar la cita» cambia las notas, o pide al asistente corregir el teléfono o el email.
2. Solo cambia lo que se envía. El teléfono se guarda en formato internacional (`+34600111222`); uno que
   no es un número válido se rechaza (`appointment.phone_invalid`) y no se guarda nada.
Sale: `appointment.appointment.updated` (sin línea de historial si solo cambian notas o contacto).

### APPOINTMENT-F23 Unir las citas al fusionar dos fichas de clienta
Estado: hecho
Actor: sistema
Pasos:
1. En **Clientes** se fusionan dos fichas (`customer.customer.merged`).
2. Todas las citas y series de la absorbida pasan a la que se queda; los nombres guardados en cada cita
   no cambian. Repetirlo no cambia nada más.

### APPOINTMENT-F24 Vaciar los datos de una clienta al borrarla
Estado: hecho
Actor: sistema
Pasos:
1. En **Clientes** se borran los datos personales de una ficha (`customer.customer.erased`).
2. Sus citas (en cualquier estado, también las borradas) se quedan sin nombre, teléfono, email, notas y
   motivo de cancelación; sus series sin nombre, y pausadas; su historial sin nombres ni motivos.
3. Donde estaba el nombre, la agenda dice «Cliente borrado». Se quedan la cita, su número, los
   servicios, el precio, el profesional, la hora, el estado y la venta.

### APPOINTMENT-F25 Un profesional se da de baja con citas futuras
Estado: hecho
Actor: sistema
Pasos:
1. En **Personal** se da de baja a alguien (`staff.member.terminated`).
2. Sus citas futuras pendientes o confirmadas pasan al carril **Sin asignar**, con «Profesional dado de
   baja: pendiente de reasignar» en su historial, y la agenda avisa «{n} citas sin profesional:
   asígnalas»; se reasignan editándolas o arrastrándolas a otra fila. Sus series se pausan.
3. Desactivar a alguien o marcarlo no reservable no toca sus citas: siguen en su fila con el aviso
   «… ya no admite citas nuevas».

### APPOINTMENT-F26 Un servicio se archiva con citas o series que lo usan
Estado: hecho
Actor: sistema
Pasos:
1. En **Servicios** se archiva un servicio (`service.service.archived`).
2. Nada se cancela ni se cambia (el mercado: Fresha, Phorest, TimeTap): las citas ya reservadas lo
   conservan (nombre, precio y duración congelados) y se pueden cobrar; ya no se ofrece para reservar.
3. Una serie que lo usa salta sus fechas nuevas con el motivo «Un servicio de esta serie ya no se puede
   reservar.» (`service_unavailable`) hasta que se edita con otro servicio.
4. Antes de archivar, Servicios puede preguntar cuántas citas próximas lo usan
   (`appointment.appointment.count_active_for_service`).

### APPOINTMENT-F27 Ver la agenda de la semana
Estado: hecho
Pantalla: Agenda (Por profesional · Semana)
Pasos:
1. En «Por profesional», pulsa **Semana**: una columna por día, de lunes a domingo, y una fila por
   profesional; ‹ › avanza de semana en semana.

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y los mismos permisos. Una cita se nombra por su id o por su
número (`APT-…`); una clienta, por su id, su nombre, su teléfono o su email; un servicio y un
profesional, por su id o su nombre; una hora, como fecha y hora de pared del negocio («2026-10-15
10:00»). Si un nombre vale para varios, se dice cuáles y se pide que elija.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las citas de un rango de días, por profesional, estado, clienta o búsqueda, en páginas (hasta 100) | ver citas (todas o las suyas) | F01–F11, F27 | `appointment.appointment.list` |
| Una cita completa | ver citas | F04, F10 | `appointment.appointment.get` |
| El historial de una cita | ver citas | F10 | `appointment.appointment.history` |
| Las últimas citas de una clienta, con notas | ver citas | F20 | `appointment.appointment.list_for_customer` |
| Cuántas citas próximas usan un servicio | ver citas | F26 | `appointment.appointment.count_active_for_service` |
| Cuántas reservas de clientas esperan confirmación | ver citas | F03, F18 | `appointment.appointment.count_to_confirm` |
| Las filas de la agenda (profesionales reservables y los que conservan citas) | ver citas | F01, F04, F25, F27 | `appointment.agenda.lanes` |
| Las horas libres de un día | ver disponibilidad | F02, F18 | `appointment.availability.slots` |
| Si una hora concreta se puede reservar y por qué no | ver disponibilidad | F02 | `appointment.availability.check` |
| Los bloqueos de un rango | ver disponibilidad | F16 | `appointment.blocked_time.list` |
| Las series, con búsqueda y filtros | ver citas | F12–F15 | `appointment.recurring.list` |
| Una serie con lo que alcanza un cambio desde una fecha | ver citas | F14 | `appointment.recurring.get` |
| Los ajustes | ver citas | F19 | `appointment.settings.get` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Reserva una cita | reservar (o reservarse) | F01, F18 | `appointment.appointment.create` |
| Reserva hasta 50 citas, todas o ninguna | reservar | F21 | `appointment.appointment.bulk_create` |
| Mueve una cita, le cambia profesional o servicios | cambiar citas (o las suyas) | F04, F06 | `appointment.appointment.reschedule` |
| Cambia notas, contacto (y, si se envía, la hora) | cambiar citas | F22 | `appointment.appointment.update` |
| Confirma / inicia / completa | cambiar citas | F03, F07, F08 | `appointment.appointment.confirm`, `.start`, `.complete` |
| Marca no presentada | cambiar citas | F09 | `appointment.appointment.mark_no_show` |
| Cancela (también en nombre de la clienta) | cambiar citas | F05, F06 | `appointment.appointment.cancel` |
| Borra una cita / varias | borrar citas | F11 | `appointment.appointment.delete`, `.bulk_delete` |
| Abre la cuenta de la cita en el TPV | cambiar citas + vender | F17 | `appointment.appointment.charge` |
| Crea / quita un bloqueo | gestionar bloqueos | F16 | `appointment.blocked_time.create`, `.delete` |
| Crea una serie y reserva su ventana | reservar | F12, F13 | `appointment.recurring.create` |
| Reserva las fechas de una serie | reservar | F13 | `appointment.recurring.materialize` |
| Edita una serie desde una fecha | cambiar citas | F14 | `appointment.recurring.update` |
| Pausa / reactiva / borra una serie | cambiar citas | F15 | `appointment.recurring.deactivate`, `.activate`, `.delete` |
| Guarda los ajustes (solo lo enviado) | ajustes | F19 | `appointment.settings.update` |

Cancelar, marcar no presentada, cobrar y borrar son de **riesgo alto** para el asistente: pide
confirmación antes de hacerlas.

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `appointment.appointment.created` | Reserva (una por cita del lote y de la serie) | La cita, su número, la clienta, el profesional y su hora |
| `appointment.appointment.confirmed`, `.started`, `.completed`, `.marked_no_show`, `.cancelled`, `.deleted` | Cada cambio de estado | La cita |
| `appointment.appointment.rescheduled` | Mover (hora, profesional o servicios) | La cita, la hora y el profesional nuevos |
| `appointment.appointment.updated` | Cambiar notas o contacto | La cita |
| `appointment.appointment.charged` / `.uncharged` | Venta cobrada / anulada | La cita y la venta |
| `appointment.appointment.check_opened` / `.check_closed` | **Cobrar** abre su cuenta / la cuenta se anula en el TPV | La cita y la cuenta |
| `appointment.appointment.unassigned` | Baja de su profesional | La cita |
| `appointment.appointment.reassigned` | Fusión de fichas | La ficha que queda y la absorbida |
| `appointment.blocked_time.created`, `.deleted` | Bloqueos | El bloqueo |
| `appointment.recurring.created`, `.updated`, `.deleted` | Series | La serie |
| `appointment.settings.updated` | Guardar ajustes con algún cambio | Nada |

Los avisos llevan identificadores, nunca notas ni motivos (pueden llevar datos de salud).

### A qué reacciona

| Aviso de otra app | Qué hace Citas | Flujos |
|---|---|---|
| `customer.customer.merged` (Clientes) | Pasa citas y series de la ficha absorbida a la que queda | F23 |
| `customer.customer.erased` (Clientes) | Vacía los datos de la clienta en citas, series e historial | F24 |
| `staff.member.terminated` (Personal) | Sus citas futuras pasan a «Sin asignar»; sus series se pausan | F25 |
| `sale.sale.created_from_appointment` (Venta) | Anota la venta en la cita y la completa (409 si la cita está cancelada, no presentada o borrada, o cobrada con otra venta) | F17 |
| `sale.sale.voided` (Venta) | Quita la marca de cobrada a la cita de esa venta y su cuenta | F17 |
| `sale.order.voided` (Venta) | Suelta la cuenta anulada: **Cobrar** abre una nueva | F17 |

### Contrato con Ventas

Venta no es requisito de Citas: Citas usa su operación `sale.order.open` por nombre, con la sesión de
quien cobra (su permiso de vender), y reacciona a sus avisos. La cuenta lleva `appointment_id`, el
título «{clienta} · {nº}» y una línea de servicio por servicio (`service_lines`, SALE-F38:
`service_id`, `staff_id` = el profesional y `booked_price` = el precio reservado, que Venta comprueba
contra `appointment.appointment.get`: `services[].service_id` y `services[].price`), para que un bono de
la clienta pueda pagarla (`sale.order.apply_voucher`, SALE-F27); nunca líneas de precio abierto. Cobrar la cuenta emite
`sale.sale.created_from_appointment` con `sale_id` y `appointment_id`; anular la venta, `sale.sale.voided`
con `sale_id`; anular la cuenta abierta, `sale.order.voided` con `order_id`. La cita guarda su cuenta
(`order_id`) mientras está abierta: volver a cobrar la consulta con `sale.order.get` y, si sigue abierta,
la devuelve sin abrir otra (Venta, por su parte, devuelve la cuenta abierta de una cita con
`already = true`).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver toda la agenda | sí | sí | sí | no | `appointment.view_appointment` |
| Ver su propia agenda | sí | sí | sí | sí | `appointment.view_own_appointment` |
| Reservar para cualquiera | sí | sí | sí | no | `appointment.add_appointment` |
| Reservarse citas | sí | sí | sí | sí | `appointment.add_own_appointment` |
| Cambiar cualquier cita (estados, mover, cancelar, cobrar, series) | sí | sí | sí | no | `appointment.change_appointment` |
| Cambiar sus propias citas | sí | sí | sí | sí | `appointment.change_own_appointment` |
| Borrar citas | sí | sí | no | no | `appointment.delete_appointment` |
| Ver disponibilidad y bloqueos | sí | sí | sí | sí | `appointment.view_schedule` |
| Bloquear tiempo | sí | sí | sí | no | `appointment.manage_schedule` |
| Ajustes | sí | sí | no | no | `appointment.manage_settings` |

«Sus propias» citas son las de la ficha de Personal vinculada a su cuenta; un empleado sin ficha
vinculada ve la agenda vacía con el aviso «Tu cuenta no está vinculada a ninguna ficha de Personal.».

## Para quien lo mantiene

- Anatomía completa (copia de `apps/tax` y `apps/service`): `apps.py`, `models.py`, `migrations/`,
  `schemas.py`, `engine.py` (reglas sin ORM: disponibilidad, horas libres y recurrencias), `queries.py`,
  `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `test_integration_{customer,service,staff,schedule,sale}.py`
  (con las apps reales, sin dobles) y `test_concurrency.py` (hilos).
- **`requires = ["customer", "service", "staff", "schedule"]`** (choca con el ejemplo del README y de la
  skill `erplora-apps`, que no incluye `schedule`: Citas lee el horario del negocio en cada reserva).
  `Appointment.customer` → `customer.Customer`; `Appointment.staff` y `Recurring.staff` →
  `staff.Member`; `AppointmentService.service` y `RecurringService.service` → `service.Service`. Los
  nombres se resuelven con `find_customer`, `find_service` y `resolve_member` de esas apps. La venta es
  un identificador opaco (`sale_id`): Venta no es requisito.
- **Disponibilidad = Horarios ∩ Personal ∩ citas**: `queries.py` lee `schedule.hours.for_range` y
  `staff.availability.for_member` (sus operaciones, con un contexto de lectura que añade `schedule.view`
  y `staff.view` a quien reserva: reservar no exige permisos de esas apps), los bloqueos y las citas, y
  `engine.py` decide. Orden de los motivos (el primero gana): `invalid_start`, `in_past`, `too_soon`,
  `too_far`, `outside_schedule`, `outside_staff_hours`, `blocked`, `overlap`. `in_past` y `too_soon` solo
  para la clienta y las series; el mostrador los salta. Un día con `source = none` en Horarios no
  restringe (como el producto actual); un día sin horario de Personal solo restringe por ausencias.
- **Solapes con bloqueo**: reservar, mover y editar bloquean antes la ficha del profesional
  (`resolve_member(lock=True)`, por id en orden fijo cuando son dos), así que dos reservas del mismo
  profesional a la vez se esperan y la segunda ve la primera (`tests/test_concurrency.py`). Con los
  solapes permitidos, el mostrador tiene que confirmar (`confirm_overlap`, 409
  `appointment.overlap_needs_confirmation` con las citas que pisa); la clienta nunca solapa.
- **Numeración** `APT-AAAAMMDD-NNNN` por día de creación del negocio, con `Counter` (una fila por día)
  bloqueada en la transacción de la reserva; nunca secuencias.
- **Reloj**: los instantes se guardan con zona (UTC) y salen en la del negocio; una hora sin zona que
  llega es de pared del negocio, y una que no existe por el cambio de hora se rechaza
  (`appointment.invalid_local_time`). Fase 1: la zona es `settings.TIME_ZONE` (Europe/Madrid), como en
  Horarios y Personal.
- **Recurrencias** con `python-dateutil` (`rrule`; mantenida, decenas de colaboradores, desde 2003):
  diaria, semanal, quincenal y mensual (mismo día del mes, el último en un mes corto), con fin por fecha
  o por número de citas contado desde el inicio de la serie.
- Modelos (UUIDv7, sin `hub_id`): `Settings` (una fila), `Counter`, `Appointment`,
  `AppointmentService` (líneas congeladas), `History`, `BlockedTime`, `Recurring` y
  `RecurringService`. Borrar una cita o una serie es lógico (`deleted_at`).
- Las reacciones (`events.py`) las ejecuta el relay del outbox en la fase 2; aquí están probadas con los
  avisos reales de cada app.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/pages/AgendaPage.vue` (Lista, Por profesional día/semana, Periódicas) y
  `SettingsPage.vue`; `frontend/customer-card/VisitHistory.vue` es el bloque de la ficha de Clientes.
- La rejilla del día y el tablero de la semana son componentes propios (`DayGrid.vue`,
  `WeekBoard.vue`) mientras `@erplora/ui` no tenga el `Scheduler` (port de `ok-scheduler`, pedido en
  `UI-REQUESTS.md`).
- El cliente se elige con `CustomerSearch` de Clientes (por su ruta pública).
- Datos solo por `useLive`/`useCommand`; listas en ventanas de 100 (`useLiveWindows`).

## Lo que queda fuera

- **Recordatorios** («Enviar recordatorios»): el producto actual guardaba el ajuste sin enviar nada; aquí
  no se porta un ajuste que no hace nada. Los mensajes son de la app de WhatsApp y de las
  automatizaciones.
- **Pantalla de bloqueos**: se crean por el asistente o la API y la rejilla los pinta (como el producto
  actual, que no tenía pantalla).
- **Reserva online pública, depósitos o cargo por no presentarse, lista de espera, salas o equipos,
  reservas de grupo y calendario externo**: fuera del MVP, como en el producto actual.

## Lo que NO hace, a propósito

- No guarda el horario del negocio (Horarios) ni el turno del profesional (Personal).
- No cobra ni arma ventas: abre la cuenta en Venta y anota que se cobró.
- No envía mensajes ni recordatorios.
- No cambia todas las citas de una serie: solo **Solo esta cita** o **Esta y todas las siguientes**.
- No retiene un hueco mientras alguien decide.

## Cambios frente al producto actual

- **Varios servicios en una cita** (corte + color), cada uno con su precio y duración congelados (antes,
  uno por cita; lo pedía B-04).
- **Vista de semana** por profesional (antes, fuera del MVP).
- **El empleado ve y gestiona su propia agenda**; el responsable, la de todos (antes el empleado veía
  todas y solo reservaba).
- **Las citas del mostrador nacen Confirmadas**; Iniciar acepta también una pendiente.
- **Cobrar completa la cita** y una cita cobrada no se mueve, no se cancela ni se borra; anular la venta
  le quita la marca de cobrada. Una cita cancelada o no presentada no se cobra.
- **No-show solo pasada la hora** de la cita.
- **Cancelar pide confirmación y deja escribir el motivo; Borrar pide confirmación** y ya no «responde
  bien sin borrar» una cita en curso o completada: la rechaza.
- **La clienta que pide sobre una cita ajena** recibe el mismo «no existe» que sobre una inexistente.
- **Baja de un profesional**: sus citas futuras pasan a «Sin asignar» y sus series se pausan (antes, Citas
  no escuchaba a Personal). Archivar un servicio no cambia ninguna cita (decisión de mercado).
- **Un bloqueo de día entero** se juzga igual en la reserva y en las horas libres.
- **Los ajustes de fábrica son uno solo** (antes cada pieza tenía los suyos).
- Retirados: el ajuste de recordatorios; `set_auto_confirm_online` (lo hace `settings.update`, que
  guarda solo lo enviado); `availability.day_opening` (es `schedule.hours.for_range` de Horarios); la
  tarea `phones_to_e164` (el teléfono llega ya normalizado de Clientes y toda escritura lo normaliza);
  las lecturas internas `own_slots`, `own_rules`, `conflicting`, `upcoming_for_staff*`,
  `blocked_times.overlapping/upcoming`, `recurring.occurrences` (eran el reparto entre SQL y el handler
  WASM); la tabla apartada de retenciones de hueco.

## Decisiones de mercado (2026-10-14)

Las dudas abiertas del módulo viejo («Dudas abiertas» de su `WORKFLOW.md`) y las del porte, resueltas con
la skill `market-decision` (al menos 8 referencias cada una; (F) página leída, (S) solo el extracto del
buscador).

| Duda | Gana | Referencias |
|---|---|---|
| ¿La cita del mostrador nace pendiente o reservada? | **Reservada en firme** (aquí, «Confirmada»); «Pendiente» solo para la reserva de la clienta que el negocio revisa | Fresha (F) fresha.com/help-center/knowledge-base/calendar/600-update-appointment-statuses · Square (F) developer.squareup.com/docs/bookings-api/use-webhooks · Vagaro (S) support.vagaro.com/hc/en-us/articles/28544779074971 · Mindbody (S) support.mindbodyonline.com/s/article/203258883 · Mangomint (F) mangomint.com/learn/automated-messages-appointment-booked · Timely (S) help.gettimely.com/hc/en-gb/articles/38566344340759 · Booksy (S) support.booksy.com/hc/en-us/articles/16463923827986 · Odoo (F) odoo.com/documentation/saas-19.1/es/applications/productivity/appointments.html |
| ¿Cobrar deja la cita completada? | **Sí**, y completada es final: para deshacerlo se anula la venta | Fresha (F) …/calendar/29-complete-appointments · Mindbody (S) support.mindbodyonline.com/s/article/218291727 · Vagaro (S) support.vagaro.com/hc/en-us/articles/360000550993 · Timely (S) help.gettimely.com/hc/en-gb/articles/27815030886551 · Phorest (S) phorest.helpjuice.com/333939 · Square (F, sin estado completada: queja en su comunidad) community.squareup.com/t5/Appointments-Bookings/Appointment-Status/m-p/821279 · MyTime (S) help.mytime.com/support/solutions/articles/31000175188 · Mangomint (F) mangomint.com/learn/calendar-color-key-icons |
| ¿Se cobra una cita cancelada o no presentada? | **No** (solo una tasa, fuera del MVP); una cobrada no se cancela ni se marca no-show sin anular la venta | Fresha (F) …/payments/617-charge-no-show-and-cancellation-fees · Square (S) squareup.com/help/au/article/5493 · Vagaro (S) support.vagaro.com/hc/en-us/articles/360003362734 · Mindbody (S) support.mindbodyonline.com/s/article/No-Shows-Overview-FAQs · Mangomint (F) mangomint.com/learn/how-can-i-enforce-my-cancellation-policy · Phorest (F) support.phorest.com/hc/en-us/articles/360021236480 · Timely (S) help.gettimely.com/hc/en-gb/articles/38728984673175 · MyTime (F) help.mytime.com/support/solutions/articles/31000174867 |
| ¿No-show antes de la hora? | **No**: solo pasada la hora | Fresha (F) …/617 · Mindbody (S) No-Shows-Overview-FAQs · MyTime (F) …/31000174867 · Zoho Bookings (S) help.zoho.com/portal/en/kb/bookings/view-bookings/articles/status-14-3-2023 · Phorest (S) phorest.helpjuice.com/44083 · Booksy (S) biz.booksy.com/blog/how-booksy-reviews-work · Mangomint (F) mangomint.com/learn/cancel-or-delete-an-appointment · Timely (S) help.gettimely.com/hc/en-gb/articles/1500002256522 |
| Baja de un profesional con citas futuras | El mercado **impide la baja** hasta reasignarlas o cancelarlas (Fresha, Square, Phorest, Mindbody, Timely, Shortcuts, Vagaro, SimplyBook, Microsoft Bookings); como la baja es de Personal, Citas las pasa a «Sin asignar» con aviso y pide a Personal el bloqueo (`UI-REQUESTS.md`) | Fresha (F) …/team/113-archive-and-suspend-team-members-from-your-workspace · Square (F) squareup.com/help/us/en/article/5350 · Phorest (F) support.phorest.com/hc/en-us/articles/360017831220 · Shortcuts (F) shortcuts.help/en/aire/remove-an-employee · Microsoft Bookings (F) uvm.edu/it/kb/article/msbookings-shared-pages · Timely (S) help.gettimely.com/hc/en-gb/articles/33946740720151 · Vagaro (S) support.vagaro.com/hc/en-us/articles/204981784 · Mindbody (S) support.mindbodyonline.com/s/article/Removing-Former-Employees |
| Archivar un servicio con citas o series | **Nada en cascada**: lo reservado lo conserva y se cobra; deja de ofrecerse | Fresha (F) …/catalog/77-archive-and-delete-items-in-your-service-menu · Phorest (F) support.phorest.com/hc/en-us/articles/360017513980 · Acuity (S) help.acuityscheduling.com/hc/en-us/articles/16676922487949 · Booksy (S) · Microsoft Bookings (S) · Square (S) community.squareup.com/t5/Appointments-Bookings/Archive-Services/td-p/807764 · TimeTap (S) support.timetap.com/hc/en-us/articles/24826811849879 · Healthie (S) help.gethealthie.com/article/1115-delete-an-appointment-type |
| ¿Cancelar pide motivo y confirmación? | **Confirmación con motivo opcional** | Fresha (F) …/calendar/545-manage-cancellation-reasons · Timely (S) …/27782511092759 · Phorest (S) support.phorest.com/hc/en-us/articles/360016486739 · Mangomint (F) …/cancel-or-delete-an-appointment · Vagaro (S) support.vagaro.com/hc/en-us/articles/360009686934 |
| Solape con otra cita del profesional | En el mostrador **avisa y deja «Reservar igual»** (ajuste encendido de fábrica; apagado, bloqueo); la reserva de la clienta **nunca** solapa | Fresha (S) fresha.com/for-business/features/scheduling · Vagaro (S) support.vagaro.com/hc/en-us/articles/204347690 · Mangomint (S) mangomint.com/learn/faq-calendar-and-appointments · Timely (S) help.gettimely.com/hc/en-gb/articles/360060705974 · Mindbody (S) Repeating-Appointments |
| ¿Se cancela, se marca no presentada o se borra una cita con su cuenta abierta (sin cobrar) en el TPV? ¿Y volver a pulsar Cobrar? | **Se rechaza** hasta cobrar o anular la cuenta en el TPV (8 de 11: cancelar no toca la caja a escondidas); volver a cobrar **va a la misma cuenta** | Timely (F) help.gettimely.com/hc/en-gb/articles/1500002197102 · Jane (F) jane.app/guide/cancel-or-delete-an-appointment-from-the-schedule · Mangomint (F) mangomint.com/learn/discard-an-existing-checkout/ y mangomint.com/learn/save-a-checkout-for-later/ · Fresha (F) fresha.com/help-center/knowledge-base/calendar/600-update-appointment-statuses · Vagaro (F) support.vagaro.com/hc/en-us/articles/360013133794 · Zenoti (F) help.zenoti.com/en/appointments/daily-tasks/faq-and-troubleshooting.html · ezyVet (S) docs.ezyvet.com (appointments troubleshooting) · Toast (F) doc.toasttab.com/doc/platformguide/adminVoidingOrders.html · Square (F, no deja una cita en dos tickets) community.squareup.com/t5/Appointments-Bookings/Can-t-save-appointments-to-open-ticket-now/m-p/752438 · en contra: Odoo y Rendezvous anulan solos un borrador que solo lleva esa cita |

Los recordatorios («Enviar recordatorios») no se portan: un ajuste visible que no hace nada es lo que
la regla «nada a medias ni simulado» prohíbe.

