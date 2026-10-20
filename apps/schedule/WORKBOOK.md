# Workbook — Horarios (app)
Prefijo: SCHEDULE
Alcance MVP: peluquería y restaurante (la agenda de Citas lo lee para no reservar con el negocio cerrado)
Estado de la app: hecha (servidor y páginas); el paso «Confirma tu horario» de la puesta en marcha espera
a que el Hub tenga lista de puesta en marcha (ver «Lo que queda fuera»)

> Manual de usuario y especificación de la app `schedule`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Horarios del producto actual
> (`modules-workspace/modules/schedules`, `origin/main` `57d3f3f`, v2.0.48). Hace lo mismo, se verá
> igual y conserva toda su funcionalidad salvo lo que dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Horarios dice **cuándo está abierto el negocio**:

- la **semana habitual**: por cada día, cerrado, abierto 24 horas o uno o varios tramos (turno partido,
  o un tramo que pasa de medianoche, como 22:00–02:00);
- los **días especiales**: un festivo cerrado o un día con otro horario, que puede repetirse cada año
  (Navidad);
- los **cambios temporales**: unas fechas seguidas con otro horario o cerradas (vacaciones, horario de
  verano, obras).

Es el horario **del negocio**. No es el turno de cada profesional ni sus ausencias (eso es de
**Personal**), ni las horas que se pueden reservar (eso lo decide **Citas** cruzando las dos cosas).

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** fijan la semana, añaden, corrigen y borran
  días especiales y cambios temporales, y cambian los ajustes.
- El **empleado** solo lo ve.

Citas lo lee para ofrecer horas libres y rechazar una reserva con el negocio cerrado; el asistente
contesta con él «¿estáis abiertos el sábado a las seis?».

## Referencia adoptada

**Qué es de Horarios y qué de Personal** (skill `market-decision`, 2026-10-14). Todos los productos de
la tabla guardan dos cosas distintas: el horario del local (lo que ve el cliente y lo que cierra el
negocio un festivo) y el turno de cada profesional (cuándo se le puede reservar). La agenda reserva
dentro del turno del profesional y, con el local cerrado (festivo, vacaciones), no ofrece nada.

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Fresha | Horario de apertura del local aparte de los turnos del equipo; se reserva dentro del turno; al cambiar el horario se ofrece llevarlo a los turnos | https://www.fresha.com/help-center/knowledge-base/workspace-settings/588-update-your-business-opening-hours · https://www.fresha.com/help-center/knowledge-base/calendar/252-schedule-and-update-team-shifts |
| Square Appointments | «Business hours» del local y «Staff hours» por persona, independientes; se reserva por las del profesional | https://community.squareup.com/t5/Payments-Troubleshooting/How-can-I-adjust-my-Square-Appointments-open-hours/m-p/144439 |
| Vagaro | Horario del negocio fijo en el perfil, aparte del horario de cada empleado | https://www.vagaro.com/pro/updates/business-hours |
| Google Business Profile | Horario semanal con varios tramos por día, «abierto 24 horas» y horario especial por fecha (festivos, cierres) | https://support.google.com/business/answer/6303076?hl=en |
| Odoo | Horario de trabajo de la empresa con sus festivos («Public holidays») que heredan los empleados; cada empleado, su horario | https://www.odoo.com/documentation/19.0/applications/hr/time_off/public_holidays.html |
| Business Central | Calendario base con días no laborables, también recurrentes cada año, asignado a la empresa o al almacén | https://learn.microsoft.com/bg-bg/dynamics365/business-central/across-how-to-assign-base-calendars |
| Toast | Horario del restaurante y sus servicios (desayuno, comida, cena) por días de la semana, sin huecos ni solapes | https://support.toasttab.com/article/Setup-Restaurant-Hours-and-Services |
| Shopify | No tiene horario de tienda en el TPV; el foro se queja de que la recogida en tienda ignora el cierre del fin de semana | https://community.shopify.com/t/feedback-bug-pickup-from-store-availability-does-not-account-for-store-hours-or-weekend-closures/553038 |

**Gana:** dos horarios en dos apps. Horarios guarda el del negocio (semana, días especiales, cambios
temporales); Personal, el de cada profesional y sus ausencias. Citas reserva solo si la cita cabe
**entera** en un tramo abierto del negocio **y** en la disponibilidad del profesional. Es lo que hacen
todos los de salón y los ERP, y el caso de Shopify enseña lo que pasa si falta el horario del local.
**Por qué las demás no:** que el horario del negocio sea la unión de los turnos (una opción de Vagaro)
deja sin forma de cerrar un festivo; meter el turno del profesional en Horarios duplica lo que Personal
ya hace.

Por eso, de lo que el encargo pedía mirar, **todo lo «por persona» queda cubierto por Personal**:
horario semanal de cada profesional (STAFF-F13 a F15), sus ausencias (STAFF-F17 a F20, F24) y su
disponibilidad (`staff.availability.for_member`, STAFF-F16). El módulo viejo de Horarios tampoco lo
tenía. Horarios no conoce a nadie del equipo y no depende de Personal.

Del producto actual se conservan (su contraste de mercado ya estaba hecho y registrado en su código):

- **Google Business Profile**: varios tramos por día, «abierto 24 horas» como 00:00–00:00 y horario
  especial por fecha.
- **Square, Fresha y Google Business Profile**: siete filas fijas; un día se edita, nunca se «añade».
- **Odoo, Google Calendar, Microsoft Bookings, Business Central y Lightspeed Reservations**: la semana
  por defecto, de lunes a viernes de 09:00 a 18:00 sin pausa y el fin de semana cerrado.
- Sin regla para un día, el negocio **no** se da por abierto (código `no_hours`).

Y se decide aquí (mismo contraste):

- **Un tramo pertenece al día en que abre** (Google Business Profile): un 22:00–02:00 del sábado sigue
  abierto el domingo a la 01:00, venga de la semana, de un día especial o de un cambio temporal, aunque
  el domingo sea un día cerrado.
- **Un día especial y un cambio temporal se corrigen** (Google, Fresha, Square los editan); ya no hay
  que borrarlos y crearlos otra vez.

## Antes de empezar

1. Activa **Horarios** (viene con la peluquería y el restaurante). Ya tiene una semana por defecto
   (SCHEDULE-F12): de lunes a viernes de 09:00 a 18:00, sábado y domingo cerrados.
2. La zona horaria del negocio es la del Hub (SCHEDULE-F09): con ese reloj se lee todo el horario. En la
   fase 1 es la de Madrid.
3. En **Horarios → Horario**, pulsa **Sí, este es mi horario** si la semana por defecto es la tuya
   (SCHEDULE-F03), o edita los días que cambian (SCHEDULE-F02).
4. En **Días especiales**, añade los festivos y cierres (SCHEDULE-F04) y, para varios días seguidos, un
   cambio temporal (SCHEDULE-F05).
5. Si quieres que la semana empiece en domingo, cámbialo en **Ajustes** (SCHEDULE-F08).

## Pantallas

Horarios se abre desde el menú **Horarios** y tiene tres pestañas: **Horario**, **Días especiales** y
**Ajustes**. Lo que una persona no puede hacer no aparece, y la app lo rechaza aunque lo intente por la
API o por el asistente.

### Horario
Tabla de **siete filas fijas**, una por día de la semana, con las columnas **Día**, **Horario** y
**Estado**; no hay botón de añadir: un día se edita. **Horario** dice, por ejemplo, «10:00–14:00 ·
17:00–20:00», «Abierto 24 horas», «Cerrado» o «Sin definir»; **Estado** dice «Abierto», «Cerrado» o «—»
(sin definir); encima, **Columnas** y el cambio entre tabla y tarjetas. Las horas salen en el reloj del
idioma (24 horas en español, AM/PM en inglés). La acción
de fila **Editar** (o tocar la fila) abre «Editar horario — {día}» con: **Día**, **Cerrado**, **Abierto
24 horas**, una línea por tramo (**Abre**, **Cierra** y **Quitar tramo**), **+ Añadir tramo**, la pista
«Jornada partida: una línea por tramo (10:00–14:00 y 17:00–20:00). Un cierre anterior a la apertura pasa
de medianoche (22:00–02:00).» y **Guardar día**. Mientras nadie haya guardado ni confirmado la semana,
encima de la tabla sale el aviso amarillo «Este es un horario por defecto que hemos puesto por ti.
Comprueba que coincide con el de tu negocio: las reservas fuera de él se rechazan.» con el botón **Sí,
este es mi horario** (el botón, solo para quien puede cambiar el horario; el empleado ve el aviso). En
móvil la tabla se pinta como tarjetas.

### Días especiales
Dos tablas, una debajo de otra, cada una con su título.

- **Días especiales**: columnas **Fecha**, **Nombre**, **Estado** («Cerrado» o sus horas, tramo a tramo)
  y **Anual** («Sí»/«No»); buscador «Buscar día especial…», filtros por fecha (desde–hasta), nombre,
  estado y anual, orden por columna y 50 por página. **+** abre **Nuevo día especial**: **Fecha**,
  **Nombre** («Nombre (p. ej. Navidad)»), **Estado** («Cerrado» o «Abierto (con horario)»; empieza en
  Cerrado), el mismo editor de tramos, **Se repite cada año**, **Notas** y **Añadir día**. Acciones de
  fila: **Editar** (o tocar la fila; el mismo formulario con **Guardar**) y **Eliminar**.
- **Cambios temporales**: columnas **Desde**, **Hasta**, **Motivo** y **Estado**; buscador «Buscar cambio
  temporal…», filtros por fechas, motivo y estado, y los mismos controles. **+** abre **Nuevo cambio
  temporal**: **Desde**, **Hasta**, **Motivo**, **Estado**, el editor de tramos y **Añadir cambio
  temporal**. Acciones de fila: **Editar** y **Eliminar**.
- Eliminar pide confirmar: «Eliminar» · «Se eliminará «{nombre}». No se puede deshacer.» con
  **Cancelar** y **Eliminar**.

### Ajustes
Arriba, solo lectura, **Zona horaria del negocio** con su nombre (por ejemplo, Europe/Madrid) y la nota
«Es la del Hub y el único reloj con el que se lee el horario.». Debajo, **Semana empieza** (Lunes o
Domingo) y **Guardar**, que confirma con «Guardado». Quien no puede cambiar los ajustes ve el valor sin
poder cambiarlo y sin **Guardar**.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado; la semana no se pinta hasta tener también los ajustes (si no, se ordenaría mal). |
| Vacío | «Sin días especiales.» o «Sin cambios temporales.»; con búsqueda o filtro, «Sin resultados». La semana siempre tiene siete filas. |
| Error | El aviso de la tabla con «Reintentar». Un rechazo de un formulario sale dentro del formulario, sin perder lo tecleado; el de una acción de fila (eliminar, confirmar la semana, guardar los ajustes), encima de la tabla o del formulario. Con los ajustes sin leer no se enseña **Semana empieza**, para no guardar un valor que no se ha leído. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| SCHEDULE-F01 | Ver el horario de la semana | hecho |
| SCHEDULE-F02 | Fijar el horario de un día | hecho |
| SCHEDULE-F03 | Confirmar la semana por defecto | hecho |
| SCHEDULE-F04 | Añadir un día especial | hecho |
| SCHEDULE-F05 | Añadir un cambio temporal | hecho |
| SCHEDULE-F06 | Borrar un día especial o un cambio temporal | hecho |
| SCHEDULE-F07 | Cargar varios días especiales de golpe | hecho (asistente y API, como el producto actual) |
| SCHEDULE-F08 | Elegir con qué día empieza la semana | hecho |
| SCHEDULE-F09 | Ver la zona horaria con la que se lee el horario | hecho |
| SCHEDULE-F10 | Preguntar si el negocio está abierto en un momento | hecho (asistente y API, como el producto actual) |
| SCHEDULE-F11 | Dar el horario de unos días a Citas | hecho (lo leen Citas y Reservas) |
| SCHEDULE-F12 | Partir de una semana por defecto al activar | hecho (al crear las tablas) |
| SCHEDULE-F13 | Corregir un día especial o un cambio temporal | hecho |

### SCHEDULE-F01 Ver el horario de la semana
<!-- origen: fi:modules/schedules#query-schedules-business_hours-list old:schedules/WORKFLOW.md#schedules-f01 -->
Estado: hecho (servidor y pantalla)
Actor: todos
Pantalla: Horario
Pasos:
1. Abre **Horarios**; la pestaña **Horario** muestra los siete días.
2. Lee de cada día sus tramos, «Abierto 24 horas», «Cerrado» o «Sin definir».
3. Si la semana empieza en domingo (SCHEDULE-F08), la tabla abre por el domingo; solo cambia el orden.
Entra: la semana del negocio y el ajuste «Semana empieza».
Sale: nada; solo lectura.
Si falla: la tabla dice «No se ha podido cargar el horario.» con **Reintentar**; hasta tener la semana y
los ajustes no se pinta ni una fila, para no enseñar siete «Sin definir» que parecerían un negocio sin
horario.
Implicados: ninguno

### SCHEDULE-F02 Fijar el horario de un día
<!-- origen: qa:modules/schedules/schedule-and-availability-per-professional qa:verticals/beauty/01-services-professionals-and-schedules fi:modules/schedules#command-schedules-business_hours-set-handler-wasm-set_business_hours old:schedules/WORKFLOW.md#schedules-f02 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Horario
Pasos:
1. En **Horario**, pulsa **Editar** en el día (o toca la fila): se abre «Editar horario — {día}». El
   selector **Día** cambia de día sin cerrar.
2. Elige una de tres cosas: **Cerrado**; **Abierto 24 horas**; o una línea por tramo con su apertura y
   su cierre (10:00–14:00 y 17:00–20:00 para un turno partido; 22:00–02:00 pasa de medianoche).
3. Pulsa **Guardar día**: el formulario se cierra y la fila enseña el resumen nuevo.
Entra: el día (lunes a domingo; el asistente también entiende «el lunes») y sus tramos, hasta 12. El
orden da igual: se guardan ordenados. 00:00–00:00 es «abierto 24 horas»; cualquier otro tramo con la
misma apertura y cierre no vale.
Sale: los tramos del día, que **sustituyen** a los anteriores (no se acumulan), y el aviso
`schedule.week.updated`. La semana queda confirmada (SCHEDULE-F03): quien guarda un día ya la ha visto.
Si falla: debajo de los tramos y sin guardar nada: «Un día abierto necesita al menos un tramo horario.»,
«Un tramo no puede empezar y acabar a la misma hora; 00:00–00:00 es abierto 24 horas.», «Dos tramos se
solapan (o uno cruza la medianoche sobre otro); ajusta las horas para que no se pisen.», «Como mucho 12
tramos por día.». Una línea a medias no se envía: «Indica la hora de apertura y cierre, o márcalo como
cerrado».
Implicados: Citas (lee el horario en la reserva siguiente)

### SCHEDULE-F03 Confirmar la semana por defecto
<!-- origen: old-hub:HUB_SHELL-F31 old:schedules/WORKFLOW.md#schedules-f03 wf:peluqueria-dia#rec_peluqueria-f02 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Horario
Pasos:
1. Con el aviso amarillo «Este es un horario por defecto…» a la vista, comprueba que los días son los de
   tu negocio.
2. Pulsa **Sí, este es mi horario**; el botón se desactiva mientras trabaja.
3. El aviso desaparece.
Entra: la semana que ya está guardada; no se manda ninguna hora, así que nadie confirma un horario que no
se le ha enseñado.
Sale: la semana marcada como confirmada, sin cambiar ni una hora, y un aviso `schedule.week.updated`.
Confirmar dos veces no cambia nada ni avisa.
Si falla: arriba de la tabla: «No hay horario semanal que confirmar.» si no hay ningún día guardado (no
se llega desde la pantalla: el aviso solo sale cuando hay semana).
Implicados: ninguno

### SCHEDULE-F04 Añadir un día especial
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f02 fi:modules/schedules#command-schedules-special_days-create-handler-wasm-create_special_day fi:modules/schedules#query-schedules-special_days-list old:schedules/WORKFLOW.md#schedules-f04 qa:modules/schedules/absences-and-holidays -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Días especiales
Pasos:
1. En **Días especiales**, pulsa **+** (Nuevo día especial).
2. Escribe la **Fecha** y el **Nombre** (los dos obligatorios).
3. Deja **Cerrado** (lo que viene) o elige «Abierto (con horario)» y escribe uno o más tramos, igual que
   en SCHEDULE-F02.
4. Marca **Se repite cada año** si cae el mismo día y mes todos los años (Navidad); si quieres, **Notas**.
5. Pulsa **Añadir día**: el formulario se cierra y el día aparece en la lista.
Entra: fecha (real: el 31 de febrero no vale), nombre (hasta 200), cerrado o tramos, anual y notas (hasta
1000).
Sale: el día especial (`schedule.special_day.created`). Gana a todo lo demás ese día (SCHEDULE-F10,
F11). Un día anual vale **todos los años**, también los anteriores a su fecha; el del 29 de febrero solo
existe los años bisiestos.
Si falla: «Ya existe un día especial en esa fecha.» bajo la fecha (409 `schedule.special_day_exists`,
también si dos personas la crean a la vez); los rechazos de tramos de SCHEDULE-F02; un nombre vacío o de
solo espacios, bajo el nombre. Una fecha que tuvo un día especial borrado se puede volver a usar.
Implicados: Citas

### SCHEDULE-F05 Añadir un cambio temporal
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f02 qa:modules/schedules/absences-and-holidays fi:modules/schedules#command-schedules-overrides-create-handler-wasm-create_override fi:modules/schedules#query-schedules-overrides-list old:schedules/WORKFLOW.md#schedules-f05 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Días especiales
Pasos:
1. En la tabla «Cambios temporales», pulsa **+** (Nuevo cambio temporal).
2. Escribe **Desde**, **Hasta** y **Motivo** (los tres obligatorios).
3. Deja **Cerrado** (vacaciones del negocio) o elige «Abierto (con horario)» y escribe los tramos que
   valen esas fechas (horario de verano).
4. Pulsa **Añadir cambio temporal**.
Entra: las dos fechas (ambas incluidas), el motivo (hasta 200) y cerrado o tramos: el cambio vale todos
los días del rango con las mismas horas.
Sale: el cambio temporal (`schedule.override.created`). Gana a la semana, pero pierde contra un día
especial de esa fecha (no se avisa de que lo pisa: la precedencia lo resuelve).
Si falla: «La fecha de fin no puede ser anterior a la de inicio.» bajo Hasta; «Esas fechas se solapan con
el cambio temporal «{motivo}» ({desde}–{hasta}).» bajo Desde (409 `schedule.override_overlaps`): dos
cambios no cubren el mismo día, para que la respuesta no dependa de cuál se lea primero; los rechazos de
tramos de SCHEDULE-F02.
Implicados: Citas

### SCHEDULE-F06 Borrar un día especial o un cambio temporal
<!-- origen: fi:modules/schedules#command-schedules-overrides-delete-sql-transaccional fi:modules/schedules#command-schedules-special_days-delete-sql-transaccional old:schedules/WORKFLOW.md#schedules-f06 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Días especiales
Pasos:
1. En la fila, pulsa **Eliminar**.
2. En «Se eliminará «{nombre}». No se puede deshacer.» pulsa **Eliminar** (o **Cancelar**).
3. La fila desaparece; vuelve a regir la semana (o el cambio temporal) en esas fechas.
Entra: el día especial o el cambio temporal, por id o por su nombre o motivo (el asistente: «borra el
festivo de Navidad»).
Sale: la fila y sus tramos borrados en la misma operación (`schedule.special_day.deleted`,
`schedule.override.deleted`). Su fecha queda libre.
Si falla: «Ese día especial no existe en este negocio.» o «Ese cambio temporal no existe en este
negocio.» (404), sin avisar de nada; un nombre que vale para varios: «Hay varios con ese nombre: elige
uno.» con los candidatos.
Implicados: Citas

### SCHEDULE-F07 Cargar varios días especiales de golpe
<!-- origen: fi:modules/schedules#command-schedules-bulk_create_special_days-handler-wasm-bulk_create_special_days old:schedules/WORKFLOW.md#schedules-f07 -->
Estado: hecho (asistente y API, como el producto actual)
Actor: asistente, API
Pantalla: asistente
Pasos:
1. Pide al asistente que cargue una lista de festivos con su fecha y su nombre (hasta 366).
2. Cada uno es cerrado salvo que diga `is_closed: false` con sus tramos; puede marcarse anual.
3. La respuesta dice qué días se crearon y cuáles no, con su motivo.
Entra: la lista. Cada día lleva fecha y nombre y, si abre, sus tramos con las reglas de SCHEDULE-F02.
Sale: un día especial y un aviso `schedule.special_day.created` por cada día válido (ninguno si no entra
ninguno).
Si falla: un día con la fecha ya ocupada o repetida dentro de la lista (`already_exists`), o abierto sin
tramos o con tramos que no valen (`invalid_hours`), se salta con su motivo y los demás entran. Una lista
vacía, de más de 366 días, o con un día sin fecha real o sin nombre, se rechaza entera (422) antes de
crear nada.
Implicados: ninguno

### SCHEDULE-F08 Elegir con qué día empieza la semana
<!-- origen: fi:modules/schedules#command-schedules-settings-save-sql-transaccional fi:modules/schedules#query-schedules-settings-get old:schedules/WORKFLOW.md#schedules-f08 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Ajustes
Pasos:
1. En **Ajustes**, elige en **Semana empieza** Lunes o Domingo.
2. Pulsa **Guardar**.
3. La tabla de **Horario** abre por el día elegido.
Entra: el día de inicio (la pantalla ofrece lunes o domingo; el servidor acepta de 1, lunes, a 7,
domingo, y la tabla gira con cualquiera).
Sale: el ajuste (`schedule.settings.updated`, solo si cambia). Solo mueve el orden de las filas: no
cambia ninguna hora ni lo que contesta SCHEDULE-F10.
Si falla: un valor fuera de 1–7 sale debajo del campo y no se guarda nada.
Implicados: ninguno

### SCHEDULE-F09 Ver la zona horaria con la que se lee el horario
<!-- origen: old-hub:HUB_SHELL-F157 wf:peluqueria-dia#rec_peluqueria-f02 old:schedules/WORKFLOW.md#schedules-f09 -->
Estado: hecho (servidor y pantalla)
Actor: todos
Pantalla: Ajustes
Pasos:
1. Abre **Ajustes**; arriba aparece «Zona horaria del negocio» con su nombre (Europe/Madrid).
2. Lee la nota «Es la del Hub y el único reloj con el que se lee el horario.»: con ese reloj se leen la
   semana, los días especiales, los cambios temporales y lo que contesta SCHEDULE-F10.
Entra: la zona del Hub.
Sale: nada; solo lectura. Horarios no guarda zona propia: las horas son de pared (las 10:00 son las 10:00
antes y después del cambio de hora, sin tocar nada).
Si falla: nada que fallar; la zona siempre la da el servidor.
Implicados: ninguno

### SCHEDULE-F10 Preguntar si el negocio está abierto en un momento
<!-- origen: fi:modules/schedules#command-schedules-is_open-handler-wasm-is_open-solo-lectura old:schedules/WORKFLOW.md#schedules-f10 -->
Estado: hecho (asistente y API, como el producto actual)
Actor: asistente, API
Pantalla: ninguna
Pasos:
1. Se pregunta por un momento: con zona (`2026-08-18T08:00:00Z`) se pasa al reloj del negocio; sin zona
   (`2026-08-18T10:00`, «mañana a las diez» que el asistente escribe así) se lee tal cual; sin nada,
   contesta para ahora.
2. Contesta: abierto o cerrado, la regla que decidió, la zona usada, el día y la hora locales y un código
   estable del motivo.
Entra: solo el momento; el horario lo lee el servidor de este negocio, nunca lo manda quien pregunta.
Sale: nada guardado. `is_open`, `code` (`exception_closed`, `exception_hours`, `open_interval`,
`closed_today`, `overnight_open`, `outside_hours` o `no_hours`), `source` (`special_day`, `override`,
`weekly` o `none`), `rule_id`, los tramos que lo explican, `timezone`, `today`, `current_time` y, si lo
hay, `reason` (el nombre del día especial o el motivo del cambio que ganó). Orden: día especial de la
fecha exacta, día especial anual del mismo día y mes, cambio temporal que cubre la fecha, semana, nada.
Se está abierto desde la apertura y se deja de estar justo al cierre (a las 18:00 en punto ya está
cerrado). La madrugada de un tramo que pasó de medianoche la víspera cuenta como abierta
(`overnight_open`), venga de la regla que venga. Un día sin regla contesta `no_hours`: no está abierto.
Si falla: un momento que no es una fecha y hora reales: «Esa fecha y hora no son válidas.» (422 bajo
`when`).
Implicados: ninguno

### SCHEDULE-F11 Dar el horario de unos días a Citas
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f06 old:schedules/WORKFLOW.md#schedules-f11 -->
Estado: hecho (lo leen Citas y Reservas)
Actor: sistema (Citas y Reservas), asistente
Pantalla: ninguna
Pasos:
1. Citas (o Reservas) pide el horario de un rango de días (hasta 366; un solo día vale).
2. Horarios elige para cada día la regla que manda (la misma precedencia que SCHEDULE-F10) y lo
   contesta.
3. Citas reserva solo si la cita cabe **entera** en un tramo abierto (el de ese día o la cola de
   medianoche de la víspera) y en la disponibilidad del profesional que da Personal
   (`staff.availability.for_member`, STAFF-F16).
Entra: las fechas, en días del negocio.
Sale: solo lectura (contrato en «Para quien lo mantiene»). El final de la cita puede coincidir con el
cierre.
Si falla: un rango al revés o de más de 366 días se rechaza en el campo.
Implicados: Citas, Reservas

### SCHEDULE-F12 Partir de una semana por defecto al activar
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f02 old-hub:HUB-F22 old:schedules/WORKFLOW.md#schedules-f12 -->
Estado: hecho (al crear las tablas)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al crear las tablas de Horarios en un negocio, se planta de lunes a viernes de 09:00 a 18:00 y sábado
   y domingo cerrados.
2. La semana sale como **sin confirmar**: el aviso amarillo de Horario (SCHEDULE-F03).
Entra: nada de la persona; la semana es la del mercado, no la del negocio.
Sale: siete días. Solo una vez: una actualización nunca devuelve días que el negocio cambió.
Si falla: no hay pantalla; si no hubiera semana, Citas vería `no_hours`.
Implicados: ninguno

### SCHEDULE-F13 Corregir un día especial o un cambio temporal
<!-- origen: old:schedules/WORKFLOW.md#schedules-f04 old:schedules/WORKFLOW.md#schedules-f05 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Días especiales
Pasos:
1. Pulsa la fila (o **Editar**): se abre el formulario con lo guardado.
2. Cambia la fecha, el nombre o el motivo, el estado, los tramos, «Se repite cada año» o las notas.
3. Pulsa **Guardar**.
Entra: el día especial o el cambio temporal (por id o por nombre) y lo enviado; lo que no se envía se
queda como estaba, y si se envían los tramos se **sustituyen** todos.
Sale: el día o el cambio corregido (`schedule.special_day.updated`, `schedule.override.updated`).
Guardar sin cambiar nada no avisa.
Si falla: los mismos rechazos que al crearlo (la fecha de otro día especial, el rango de otro cambio).
Implicados: Citas

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien habla) y
la API, con las mismas reglas y los mismos permisos. Un día de la semana se nombra por su número (0 =
lunes) o por su nombre («lunes», «monday»); un día especial, por su id o su nombre; un cambio temporal,
por su id o su motivo. Si un nombre vale para varios, se dice cuáles y se pide que elija
(`schedule.ambiguous_reference`).

### Lo que ofrece: consultas (leen, no cambian nada; todas se pueden seguir en vivo)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| La semana: los siete días en el orden de «Semana empieza», cada uno cerrado, sin definir o con sus tramos, y si está confirmada | ver | F01, F03 | `schedule.week.get` |
| Los días especiales con sus tramos, con búsqueda, filtros, orden y páginas (hasta 100) | ver | F04, F06, F13 | `schedule.special_day.list` |
| Los cambios temporales con sus tramos, con búsqueda, filtros, orden y páginas (hasta 100) | ver | F05, F06, F13 | `schedule.override.list` |
| Los ajustes y la zona horaria del negocio | ver | F08, F09 | `schedule.settings.get` |
| ¿Está abierto en un momento? | ver | F10 | `schedule.business.is_open` |
| El horario de cada día de un rango | ver | F11 | `schedule.hours.for_range` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Fija los tramos de un día de la semana | cambiar el horario | F02 | `schedule.week.set_day` |
| Confirma la semana guardada | cambiar el horario | F03 | `schedule.week.confirm` |
| Crea un día especial | añadir | F04 | `schedule.special_day.create` |
| Crea hasta 366 días especiales de golpe | añadir | F07 | `schedule.special_day.bulk_create` |
| Corrige un día especial | cambiar el horario | F13 | `schedule.special_day.update` |
| Borra un día especial | borrar | F06 | `schedule.special_day.delete` |
| Crea un cambio temporal | añadir | F05 | `schedule.override.create` |
| Corrige un cambio temporal | cambiar el horario | F13 | `schedule.override.update` |
| Borra un cambio temporal | borrar | F06 | `schedule.override.delete` |
| Guarda los ajustes (solo lo enviado) | ajustes | F08 | `schedule.settings.update` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Semana cambiada | Guardar un día; confirmar la semana | El día (`weekday`) o nada al confirmar | `schedule.week.updated` |
| Día especial nuevo | Crearlo (uno por día en la carga de golpe) | Cuál (`id`) y su fecha | `schedule.special_day.created` |
| Día especial corregido | Corregirlo con algún cambio | Cuál (`id`) y su fecha | `schedule.special_day.updated` |
| Día especial borrado | Borrarlo | Cuál (`id`) | `schedule.special_day.deleted` |
| Cambio temporal nuevo | Crearlo | Cuál (`id`) y sus fechas | `schedule.override.created` |
| Cambio temporal corregido | Corregirlo con algún cambio | Cuál (`id`) y sus fechas | `schedule.override.updated` |
| Cambio temporal borrado | Borrarlo | Cuál (`id`) | `schedule.override.deleted` |
| Ajustes cambiados | Guardarlos con algún cambio | Nada | `schedule.settings.updated` |

Los avisos no llevan el nombre de un día especial ni el motivo de un cambio: son texto libre donde el
negocio puede escribir nombres de personas.

### A qué reacciona y lo que necesita de otras apps
Nada: Horarios no depende de ninguna app (`requires = []`) ni escucha avisos. De la plataforma usa la
zona horaria del negocio.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver la semana, los días especiales, los cambios, los ajustes y si está abierto | sí | sí | sí | sí | `schedule.view` |
| Añadir días especiales y cambios temporales | sí | sí | sí | no | `schedule.add` |
| Fijar la semana, confirmarla y corregir días especiales y cambios | sí | sí | sí | no | `schedule.change` |
| Borrar días especiales y cambios temporales | sí | sí | sí | no | `schedule.delete` |
| Cambiar los ajustes | sí | sí | sí | no | `schedule.manage_settings` |

## Para quien lo mantiene

- Anatomía completa de una app: `apps.py`, `models.py`, `engine.py` (las reglas, sin base de datos),
  `schemas.py`, `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/` y un
  `tests/test_<fichero>.py` por fichero; las páginas en `frontend/`. `UI-REQUESTS.md` lista lo que se pide
  a `@erplora/ui`.
- Modelos (UUIDv7, sin `hub_id`): `WeekDay` (un día de la semana, lunes = 0, cerrado o no; un día sin
  fila está «sin definir») con sus `WeekDayInterval`; `SpecialDay` (fecha única) con sus
  `SpecialDayInterval`; `Override` (rango de fechas) con sus `OverrideInterval`; `ScheduleSettings` (una
  sola fila: «Semana empieza» y si la semana está confirmada). Un tramo es `open_time`–`close_time` con
  `position`; `close_time` ≤ `open_time` pasa de medianoche y 00:00–00:00 es 24 horas.
- **Borrado de verdad**, no lógico: un día especial borrado libera su fecha (la restricción única cuenta
  solo lo que existe).
- Las reglas viven en `engine.py` (validar y ordenar tramos, precedencia, ¿abierto?, tramos de un día),
  sin ORM: las usan `queries.py` y `services.py`, y Citas puede llamar a `schedule.hours.for_range`.
- **Dos cambios temporales no se pisan**: las escrituras de cambios temporales bloquean antes la fila de
  ajustes (`select_for_update`), así que dos altas a la vez se esperan y la segunda ve la primera. Un día
  especial repetido lo para la restricción única, traducida al mismo 409.
- **Zona horaria**: el Hub todavía no guarda la del negocio. En la fase 1 es `settings.TIME_ZONE`
  (Europe/Madrid), la de `timezone.get_current_timezone()`, como «hoy» en Personal e Impuestos. Las horas
  son de pared; un instante con zona se convierte con `zoneinfo` (cambio de hora incluido). Cuando el Hub
  guarde la zona del negocio, `schedule.settings.get` y el motor la leerán de ahí.
- **Librerías**: ninguna nueva. La zona y el cambio de hora son `zoneinfo` y `datetime` de la biblioteca
  estándar (Python 3.14 lee RFC 3339 con `datetime.fromisoformat`). No hay calendario de festivos
  precargado (el módulo viejo tampoco lo tenía), así que `holidays` no hace falta.
- **Contrato para Citas** (`schedule.hours.for_range`, `date_from`, `date_to`, hasta 366 días): por día,
  `date`, `source` (`special_day`, `override`, `weekly` o `none`), `rule_id`, `name` (nombre del día
  especial o motivo del cambio, si lo hay), `is_closed`, `intervals` (los tramos tal como se guardaron,
  `open_time`/`close_time`) y `spans` (los mismos como fecha y hora de pared del negocio, `start` y `end`
  sin zona; `end` es del día siguiente si el tramo pasa de medianoche y 00:00–00:00 va de 00:00 a 00:00
  del día siguiente); y arriba `timezone`. Una cita de `start` a `end` cabe si existe un `span` (de su día
  o de la víspera) con `span.start ≤ start` y `end ≤ span.end`. Citas lo cruza con
  `staff.availability.for_member` (Personal) y decide qué hace con `source = none` (el producto actual
  dejaba reservar cuando no había ninguna fila semanal). El aviso de cualquier cambio de Horarios
  re-ejecuta la consulta en vivo.
- **«¿Abierto?» sin `when` depende del reloj**: es «ahora» en el momento de ejecutarse. Seguida en vivo,
  se re-ejecuta con un aviso de Horarios o en la pasada de seguridad de cada 300 s, así que puede llegar
  hasta 5 minutos tarde a una apertura o un cierre. Hoy ninguna pantalla la enseña (la usan el asistente
  y la API, que preguntan una vez). La pantalla que enseñe «abierto ahora» se suscribe con un `when`
  explícito (el minuto actual) y lo cambia cada minuto; nunca la versión sin `when`.
- **Fechas acotadas**: «¿abierto?» y el horario de un rango solo contestan entre 1900 y 2200 (422 «Elige
  una fecha entre 1900 y 2200.»); en los extremos del calendario de Python (año 1, año 9999) un día más
  o una hora de desfase desbordan.
- **La carga de golpe** salta un día con más de 12 tramos (`invalid_hours`) o cuya fecha ocupa otra
  persona a la vez (`already_exists`) y sigue con el resto; solo rechaza entera la lista vacía, de más
  de 366 días, con un día sin fecha real o sin nombre, o con más de 100 tramos en un día.
- Asistente: toda operación declara `ai={"description", "risk"}` (`risk` solo en las acciones; `high` en
  borrar un día especial o un cambio temporal, que no se deshace) y todo campo de entrada lleva
  `description`; las mismas descripciones salen en el OpenAPI.
- El admin de Django del Hub tiene **CRUD completo** sobre todos los modelos (ronda 12, PLAN §17), con
  los tramos como líneas de su día; ids y fechas de auditoría, de solo lectura. Una escritura cruda del
  admin no deja aviso.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo.
- La semana por defecto la planta la migración `0002_default_week` (con su vuelta atrás, que solo quita
  la semana si sigue sin confirmar).

## Lo que queda fuera

- **El paso «Confirma tu horario» de la puesta en marcha**: el Hub aún no tiene lista de puesta en
  marcha. `schedule.week.get` ya dice si la semana está confirmada (`confirmed`).
- **La semana de la peluquería** que plantaba el catálogo de arranque del producto actual (lunes a
  viernes 09:30–20:00 con descanso de 14:00 a 16:00, sábado 09:30–14:00): es de los catálogos de
  arranque, que no están portados.
- **Calendario de festivos del país precargado**: el producto actual no lo tenía; cada día especial lo
  escribe el negocio o el asistente (SCHEDULE-F07).
- **Fechas y horas en el orden del idioma del Hub** escritas a mano (`dd/mm/aaaa`, «2:30 pm», «1430»): los
  campos usan `ion-input type="date|time"` hasta que `@erplora/ui` tenga los suyos (`UI-REQUESTS.md`).
- **«Abrir ajustes del hub»** desde Ajustes: el Hub aún no tiene ajustes de zona horaria a los que ir.
- **El asistente (chat y voz) y las llaves de API del negocio** son de la plataforma, que aún no los tiene:
  Horarios ya declara cada operación para el asistente, con su descripción, y abre a las llaves la semana,
  las listas, «¿abierto?» y el horario de un rango; mientras tanto, SCHEDULE-F07 y SCHEDULE-F10 se piden
  por la API con la sesión.
- **El icono de estrella** de la pestaña **Días especiales** (el del producto actual): `@erplora/ui` aún no lo
  tiene y se usa el de calendario (`UI-REQUESTS.md`).

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/schedule/hours`, `/schedule/special-days` y `/schedule/settings`; la barra de
  pestañas (`frontend/tabs.ts`) lleva las tres, como el `navigation` de `apps.py`.
- Horario lee `schedule.week.get` (la semana ya plegada y girada por el servidor) y edita con
  `schedule.week.set_day`; Días especiales, `schedule.special_day.list` y `schedule.override.list` con
  `useLiveList` (ventanas de 100) y `useServerTable`; las escrituras, con `useCommand`.
- Un mismo editor de tramos (`frontend/components/IntervalsEditor.vue`) en los tres formularios.
- Las horas se pintan con `Intl` en el reloj del idioma (`frontend/lib/format.ts`); las fechas, en UTC
  para que nunca se muevan un día.

## Lo que NO hace, a propósito

- No guarda turnos de profesionales ni ausencias (Personal) ni decide las horas reservables (Citas).
- No cierra la caja ni impide vender fuera de horario: solo Citas lo lee.
- No avisa a nadie de que el negocio abre o cierra, ni cierra nada solo.
- No tiene zona horaria propia ni duración de hueco: la zona es del Hub y la duración, del servicio.
- No tiene varias plantillas de horario ni horario por sede: un Hub es un negocio.

## Cambios frente al producto actual

- **Un día especial y un cambio temporal se corrigen** (SCHEDULE-F13), y **su borrado es de verdad**: la
  fecha queda libre, así que ya no falla crear otro en la misma fecha ni el lote da por creado un día
  que no se crea (eran los «parcial» de SCHEDULES-F04, F06 y F07).
- **Un tramo pertenece al día en que abre**, venga de la regla que venga: el 22:00–02:00 de un día
  especial o de un cambio temporal sigue abierto pasada la medianoche (antes solo hasta las 24:00), y la
  madrugada del día siguiente cuenta aunque ese día tenga su propio día especial. Antes la cola de la
  víspera salía de la semana aunque la víspera la cerrara un festivo.
- **La carga de golpe** acepta tramos como el alta de uno (antes solo un par apertura–cierre sin pasar
  de medianoche) y un día con horas sin `is_closed: false` es cerrado, como al crear uno; una lista con un
  día sin nombre se rechaza entera, como antes, y ahora también con un día sin fecha real (antes se saltaba
  solo ese día): la lista se corrige de una vez, antes de crear nada.
- **¿Abierto?** es una consulta (antes una orden con lecturas precargadas) y su `source` de la semana se
  llama `weekly` (antes `business_hours`). El código `on_break` desaparece: era el descanso antiguo de una
  fila de antes de los tramos, que aquí no existe; tampoco el par apertura–cierre de reserva de las
  excepciones sin tramos.
- **«Semana confirmada»** es una marca de los ajustes, que pone quien guarda un día o confirma, en vez de
  mirar quién firmó cada fila; confirmar no reescribe la semana.
- **Ajustes**: el aviso solo sale si algo cambia (antes siempre); la tabla gira con cualquier día de
  inicio, no solo lunes o domingo; la zona horaria se enseña sin el botón «Abrir ajustes del hub»;
  **Guardar** dice «Guardado» (antes no decía nada), y el empleado ve los ajustes sin poder guardarlos
  (antes el Hub le pedía el PIN de un responsable).
- **Los rechazos de datos** (horas, tramos, fechas, nombre vacío) salen bajo su campo (422); los choques
  con otro dato (fecha ocupada, cambios que se pisan) son 409 con su código y también bajo su campo.
- **Días especiales** se ordenan por fecha por defecto (antes por nombre), y **cambios temporales** por
  fecha de inicio (antes por alta).
- Las listas paginan con hasta 100 por página.
- Los permisos se llaman `schedule.view`, `schedule.add`, `schedule.change`, `schedule.delete` y
  `schedule.manage_settings` (antes `schedules.view_schedule`…), y las operaciones,
  `schedule.<entidad>.<acción>` (tabla de equivalencias en el informe del porte).
