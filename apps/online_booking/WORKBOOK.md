# Workbook — Reservas online (app)
Prefijo: ONLINE_BOOKING
Alcance MVP: peluquería
Estado de la app: completa (2026-10-21)

> Manual de usuario y especificación de la app `online_booking`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor y
> páginas). Parte del `WORKFLOW.md` del módulo Reservas online del producto actual
> (`modules-workspace/modules/online_booking`, `origin/main` `3000878`, v1.1.23). Los números de flujo se
> conservan (`ONLINE_BOOKING-Fnn`). Lo que cambia frente al producto actual lo dice «Cambios frente al
> producto actual», al final.

## Para qué sirve y para quién

Reservas online es **la puerta por la que una clienta pide cita sola, desde fuera, sin llamar**: elige el
servicio, el profesional (o «sin preferencia»), el día y una hora libre, deja su nombre y su teléfono, y la
cita entra **en la agenda de Citas**, como cualquier otra, con el origen «Reserva online». Si el negocio
confirma a mano, nace **Pendiente** y espera en la **bandeja de Reservas**; si confirma solo, nace
**Confirmada**. La clienta recibe un número de cita y un enlace personal con el que ve su reserva y la
cancela dentro de la política del negocio.

Quién la usa:

- La **clienta**, en la página de reservas del negocio (sin cuenta ni contraseña).
- El **empleado** ve en la bandeja las reservas online de **su propia agenda**.
- El **responsable** ve todas las reservas online y las confirma, completa, marca como no presentadas o
  cancela.
- El **propietario** y el **administrador**: además las borran y configuran la página de reservas.
- El **asistente** (por voz o por texto, con la sesión de quien habla) hace lo mismo: «confirma la reserva
  de Ana de mañana», «¿qué reservas online hay pendientes?», «cancela la reserva APT-20261016-0003».

## Referencia adoptada

**Fresha, Treatwell, Booksy, Square Appointments, Vagaro, Mindbody, Odoo Appointments y SimplyBook.me**
(tabla y enlaces en «Decisiones de mercado»): la reserva online **es una cita de la agenda** desde el primer
momento (ocupa el hueco), con un ajuste de confirmación automática o manual; la página pide nombre y móvil;
la clienta gestiona su reserva con el enlace de la confirmación, y cancelar desde ahí respeta la antelación
del negocio.

## Antes de empezar

1. Reservas online enciende con ella **Citas**, **Clientes**, **Servicios** y **Personal** (y, por Citas,
   **Horarios**), y no se pueden apagar mientras esté encendida.
2. En **Servicios**, deja marcada **Reserva online** en los servicios que la clienta puede reservar (también
   desde los Ajustes de esta app). Un servicio archivado o que no se puede reservar en la agenda no sale.
3. En **Personal** y **Horarios**, lo mismo que pide la agenda: profesionales reservables, su horario y el
   del negocio. La página ofrece solo las horas que la agenda daría a la clienta.
4. Abre **Reservas online → Ajustes**, enciende **Página pública activada** y pulsa **Guardar**. Mientras
   está apagada, la página dice que el negocio no acepta reservas online.
5. Todas las horas son las del **reloj del negocio** (en la fase 1, Europe/Madrid).

## Pantallas

Reservas online se abre desde el menú **Reservas online** y tiene dos pestañas: **Reservas** y **Ajustes**
(esta, solo para quien puede cambiarlos). Lo que una persona no puede hacer sale en gris o no aparece, y la
app lo rechaza aunque lo intente por la API o por el asistente.

### Reservas (bandeja)
Tabla de 50 filas por página con buscador («Buscar nº, cliente, teléfono, servicio…») y filtros por columna
detrás del botón de filtros de la barra, como en el producto actual: Nº, Cliente, Servicio, Profesional, Fecha
(un día) y Estado. Columnas: **Nº** (`APT-…`), **Cliente** (con su
teléfono), **Servicio**, **Profesional**, **Fecha**, **Hora**, **Estado** y **Reservada** (cuándo la pidió).
Las más recientes primero; se ordena por columna. Lista o tarjetas.

Por fila: **Confirmar**, **Completar**, **No-show**, **Cancelar** y **Borrar** (Borrar solo para quien puede
borrar). La que no aplica al estado sale en gris, no se esconde. **Cancelar** pide confirmación con un motivo
opcional; **Borrar** pide confirmación. Vacía: «Aún no hay reservas online.» (con filtros: «Ninguna reserva
coincide con la búsqueda.»). Se refresca sola cuando cambia una cita online en la agenda.

### Ajustes
Título «Configuración de la página de reservas». Tres bloques y un botón **Guardar**:

- **Página pública**: «Página pública activada», «Título de la página», «Mensaje de bienvenida», «Color
  primario» (`#RRGGBB`), «URL del logo», «Email obligatorio», «Reservas próximas por móvil» (1 a 50),
  «Permitir elegir profesional», «Permitir notas», «Mensaje de confirmación» y «Política de cancelación»
  (el texto que lee la clienta).
- **Reglas de reserva** (son las de Citas, compartidas con WhatsApp): «Antelación mínima para reservar
  (minutos)», «Reservar como máximo con esta antelación (días)» (0 = sin límite), «Intervalo entre huecos
  (minutos)», «Confirmar automáticamente las reservas de la clienta», «Permitir que la clienta cancele su
  cita» y «Antelación mínima para cancelar (horas)».
- **Servicios reservables online**: los servicios en oferta, cada uno con un interruptor con su nombre
  (encendido, se reserva online; se guarda al tocarlo, en Servicios); el que no se puede reservar en la
  agenda lo dice («No se puede reservar en la agenda»).

Al guardar: «Configuración guardada.»; un rechazo sale debajo de su campo («No se pudo guardar»).

### Vista previa de la reserva (solo en desarrollo)
Página `/online_booking/preview`, solo en el servidor de desarrollo: hace el recorrido de la página pública
(servicio → profesional → día y hora → datos → reservar → ver y cancelar con el enlace) con las mismas
operaciones que llamará la página pública de `base`. No forma parte de la versión de producción.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» en la tabla; «Cargando la configuración…» en Ajustes. |
| Vacío | «Aún no hay reservas online.»; con filtros, «Ninguna reserva coincide con la búsqueda.»; en Ajustes sin servicios, «Todavía no hay servicios. Dalos de alta en Servicios.». |
| Error | El aviso de la tabla con «Reintentar»; el rechazo de una acción de fila, en su confirmación o encima de la tabla; un rechazo de Ajustes, debajo de su campo, sin perder lo tecleado. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

Fechas y horas salen en el reloj del negocio y con el formato del idioma de quien mira.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ONLINE_BOOKING-F01 | La clienta reserva desde la página de reservas | hecho (operaciones y vista previa; la página pública es de `base`) |
| ONLINE_BOOKING-F02 | Confirmar una reserva | hecho |
| ONLINE_BOOKING-F03 | Completar una reserva | hecho |
| ONLINE_BOOKING-F04 | Marcar que no se presentó | hecho |
| ONLINE_BOOKING-F05 | Cancelar una reserva | hecho |
| ONLINE_BOOKING-F06 | Borrar una reserva | hecho |
| ONLINE_BOOKING-F07 | Configurar la página de reservas | hecho |
| ONLINE_BOOKING-F08 | Ver y buscar las reservas | hecho |
| ONLINE_BOOKING-F09 | Seguir a la clienta cuando se fusionan dos fichas | hecho (lo hace Citas; la bandeja lo refleja) |
| ONLINE_BOOKING-F10 | La clienta ve su reserva con su enlace | hecho (operación; la página es de `base`) |
| ONLINE_BOOKING-F11 | La clienta cancela su reserva con su enlace | hecho (operación; la página es de `base`) |
| ONLINE_BOOKING-F12 | Borrar los datos de una clienta (RGPD) | hecho |

### ONLINE_BOOKING-F01 La clienta reserva desde la página de reservas
<!-- origen: fi:modules/online_booking#command-online_booking-bookings-create-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f01 -->
Estado: hecho (operaciones y vista previa; la página pública es de `base`)
Actor: clienta (sin sesión)
Pantalla: página pública de reservas (`base`); en desarrollo, la vista previa
Pasos:
1. Abre la página del negocio: título, mensaje de bienvenida, logo y color de los Ajustes.
2. Elige uno o varios servicios (hasta 5) de los **reservables online**, con su precio y su duración si
   Servicios los enseña («Mostrar precios», «Mostrar duración»).
3. Si el negocio lo permite, elige profesional entre los que hacen todos esos servicios, o «Sin
   preferencia».
4. Elige el día: salen las **horas libres** que la agenda daría a la clienta (horario del negocio, turno y
   ausencias del profesional, bloqueos y otras citas; nunca dentro de la antelación mínima, más allá de la
   máxima, en el pasado ni encima de otra cita).
5. Escribe su nombre, su **móvil** (obligatorio), su email (si el negocio lo pide) y, si se permite, una nota.
6. Pulsa **Reservar**: la cita entra en la agenda con el origen «Reserva online», **Confirmada** o
   **Pendiente** según «Confirmar automáticamente las reservas de la clienta» (y siempre Pendiente si un
   servicio tiene «Requiere confirmación» en Servicios), y la clienta ve su número de cita (`APT-…`), el
   mensaje de confirmación y su **enlace personal**.
Entra: los servicios reservables online (Servicios), los profesionales que los hacen (Servicios y Personal),
las horas libres y las reglas de reserva (Citas), las fichas de Clientes.
Sale: la cita (`appointment.appointment.created` y, si nace confirmada, `appointment.appointment.confirmed`),
la ficha de la clienta **enlazada por su teléfono** o creada si no existe (`customer.customer.created`, con
origen «web»), y el aviso `online_booking.booking.created`. Si la ficha no tiene email, el que escribió
queda como contacto de la cita (la ficha no se toca). Con «Sin preferencia», la cita es del primer
profesional (por orden de nombre) que tiene libre esa hora. Nada de lo que responde la página dice el nombre
de la ficha de ese móvil. Quien abra la vista previa desde dentro (propietario o administrador) reserva con
las mismas reglas que la clienta: nunca con las excepciones del mostrador.
Si falla: no se escribe nada. La página apagada («Este negocio no acepta reservas online ahora mismo.»); un
servicio que no se reserva online; elegir profesional cuando el negocio no lo permite; la hora ya no está
libre o no cumple las reglas (el motivo de Citas); el móvil que no es un número válido; falta el email
obligatorio; una nota cuando el negocio no las admite; **límites anti-abuso**: más de 5 reservas en una hora
desde el mismo dispositivo («…Inténtalo más tarde o llama al negocio.») o más de 100 en una hora en el
negocio («…Inténtalo dentro de unos minutos.»), o más
reservas online próximas con el mismo móvil de las que permiten los Ajustes (3 de fábrica: «Este móvil ya
tiene reservas próximas…», sin decir cuántas). Dos clientas que reservan a la vez la misma hora del mismo
profesional: entra una y la otra recibe «Esa hora ya no está libre».
Implicados: APPOINTMENT-F02, APPOINTMENT-F18, APPOINTMENT-F19, CUSTOMER-F10, CUSTOMER-F11, SERVICE-F10

### ONLINE_BOOKING-F02 Confirmar una reserva
<!-- origen: fi:modules/online_booking#command-online_booking-bookings-confirm-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f02 qa:modules/online_booking/online-booking -->
Estado: hecho
Actor: responsable, propietario, administrador, asistente
Pantalla: Reservas
Pasos:
1. En una reserva **Pendiente**, pulsa **Confirmar** (o di «confirma la reserva de Ana de mañana»).
2. La cita pasa a **Confirmada** en la agenda y su historial dice «Confirmada».
Entra: una reserva online pendiente (la página con la confirmación automática apagada, o un servicio que
requiere confirmación).
Sale: `appointment.appointment.confirmed`.
Si falla: «Esta cita ya no se puede confirmar: ya no está pendiente.»; si el nombre vale para varias
reservas, se dicen cuáles y se pide el número.
Implicados: APPOINTMENT-F03

### ONLINE_BOOKING-F03 Completar una reserva
<!-- origen: fi:modules/online_booking#command-online_booking-bookings-complete-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f03 -->
Estado: hecho
Actor: responsable, propietario, administrador, asistente
Pantalla: Reservas
Pasos:
1. En una reserva **Confirmada** o **En curso**, pulsa **Completar**.
2. La cita pasa a **Completada**. No cobra: el cobro es el de la agenda en el TPV.
Entra: una reserva online confirmada o en curso.
Sale: `appointment.appointment.completed`.
Si falla: «Esta cita no se puede completar en su estado actual.»
Implicados: APPOINTMENT-F08, APPOINTMENT-F17

### ONLINE_BOOKING-F04 Marcar que no se presentó
<!-- origen: fi:modules/online_booking#command-online_booking-bookings-no_show-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f04 -->
Estado: hecho
Actor: responsable, propietario, administrador, asistente
Pantalla: Reservas
Pasos:
1. Pasada la hora de la reserva, en una **Pendiente** o **Confirmada**, pulsa **No-show**.
2. La cita pasa a **No-show** y el hueco queda libre.
Entra: una reserva online pendiente o confirmada cuya hora ya pasó.
Sale: `appointment.appointment.marked_no_show`.
Si falla: antes de su hora, «Todavía no es la hora de esta cita…»; en otro estado, «Esta cita no se puede
marcar como no presentada en su estado actual.»
Implicados: APPOINTMENT-F09

### ONLINE_BOOKING-F05 Cancelar una reserva
<!-- origen: qa:modules/online_booking/online-booking fi:modules/online_booking#command-online_booking-bookings-cancel-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f05 -->
Estado: hecho
Actor: responsable, propietario, administrador, asistente
Pantalla: Reservas
Pasos:
1. Pulsa **Cancelar** en una reserva pendiente, confirmada o no presentada.
2. «¿Cancelar la reserva de Lucía (martes 14, 10:00)?» con el motivo opcional; pulsa **Cancelar la reserva**.
3. La cita pasa a **Cancelada**, el hueco queda libre y el historial guarda quién y el motivo.
Entra: una reserva online pendiente, confirmada o no presentada, sin cobrar.
Sale: `appointment.appointment.cancelled`. Rechazar una reserva pendiente es cancelarla (el mercado: el
«rechazar» de una solicitud libera el hueco igual).
Si falla: «Esta cita ya no se puede cancelar en su estado actual.»; dentro del diálogo.
Implicados: APPOINTMENT-F05

### ONLINE_BOOKING-F06 Borrar una reserva
<!-- origen: fi:modules/online_booking#command-online_booking-bookings-delete-sql-transaccional old:online_booking/WORKFLOW.md#online_booking-f06 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Reservas
Pasos:
1. Pulsa **Borrar** y confirma «¿Borrar la reserva APT-…? Es mejor cancelarla, que conserva su historial.».
2. La reserva desaparece de la bandeja y de la agenda (borrado lógico: el dato no se pierde).
Entra: una reserva online que no está en curso, completada ni cobrada.
Sale: `appointment.appointment.deleted`.
Si falla: una cita en curso, completada o cobrada no se borra («Esta cita no se puede borrar…»).
Implicados: APPOINTMENT-F11

### ONLINE_BOOKING-F07 Configurar la página de reservas
<!-- origen: fi:modules/online_booking#command-online_booking-settings-upsert-sql-transaccional fi:modules/online_booking#query-online_booking-settings-get old:online_booking/WORKFLOW.md#online_booking-f07 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Cambia los campos de **Página pública** y de **Reglas de reserva** y pulsa **Guardar**: «Configuración
   guardada.». Se guarda solo lo que cambia, todo junto o nada.
2. En **Servicios reservables online**, toca el interruptor de un servicio: se guarda al momento en
   Servicios.
Entra: los ajustes guardados (o los de fábrica: página apagada, email no obligatorio, 3 reservas próximas por
móvil, elegir profesional y notas permitidos) y las reglas de Citas.
Sale: `online_booking.settings.updated` (si cambia algo de la página) y `appointment.settings.updated` (si
cambia una regla); el interruptor de un servicio, `service.service.updated`.
Si falla: un color que no es `#RRGGBB`, una URL que no es `http(s)://…`, un número fuera de rango o un texto
demasiado largo, debajo de su campo; no se guarda nada.
Implicados: APPOINTMENT-F19, SERVICE-F02

### ONLINE_BOOKING-F08 Ver y buscar las reservas
<!-- origen: qa:modules/online_booking/online-booking fi:modules/online_booking#navigation-ui-bookings fi:modules/online_booking#query-online_booking-bookings-get fi:modules/online_booking#query-online_booking-bookings-list old:online_booking/WORKFLOW.md#online_booking-f08 -->
Estado: hecho
Actor: empleado (las de su agenda), responsable, propietario, administrador, asistente
Pantalla: Reservas
Pasos:
1. Abre **Reservas**: las citas con origen «Reserva online», las más recientes primero.
2. Busca por número, nombre, teléfono, email, servicio o profesional; filtra por columna desde el botón de
   filtros de la barra; ordena. Un nombre largo acaba en «…» dentro de su columna.
3. Una reserva concreta la da el asistente o la API por su número, o por la clienta y el día.
Entra: las citas de Citas con origen «Reserva online» que la persona puede ver.
Sale: nada se escribe. La fila no abre nada por sí sola: lo que se hace con una reserva son sus acciones.
Si falla: «No se pudieron cargar las reservas» con **Reintentar**.
Implicados: APPOINTMENT-F27

### ONLINE_BOOKING-F09 Seguir a la clienta cuando se fusionan dos fichas
<!-- origen: old:online_booking/WORKFLOW.md#online_booking-f09 -->
Estado: hecho (lo hace Citas; la bandeja lo refleja)
Actor: sistema
Pantalla: ninguna (se ve en Reservas)
Pasos:
1. En **Clientes** se fusionan dos fichas.
2. Citas pasa las citas de la absorbida a la que queda (APPOINTMENT-F23); la bandeja enseña la reserva con
   la ficha que queda y el nombre que la clienta escribió al reservar. Esta app no guarda la ficha de la
   clienta: nada más que hacer, y su enlace sigue funcionando.
Entra: el aviso de Clientes con la ficha que queda y la absorbida, que entrega el relay del worker.
Sale: nada propio (el aviso de Citas, `appointment.appointment.reassigned`).
Si falla: Citas no se queda a medias y el relay lo reintenta solo.
Implicados: APPOINTMENT-F23, CUSTOMER-F13

### ONLINE_BOOKING-F10 La clienta ve su reserva con su enlace
<!-- origen: nuevo (el enlace personal de la confirmación, como Square, Treatwell, SimplyBook.me y Acuity) -->
Estado: hecho (operación; la página es de `base`)
Actor: clienta (sin sesión)
Pantalla: la página de su reserva (`base`); en desarrollo, la vista previa
Pasos:
1. Abre el enlace de su confirmación.
2. Ve el número, el estado, el día y la hora, los servicios, el profesional, la política de cancelación y si
   todavía puede cancelar y hasta cuándo. Nunca el nombre de la ficha: quien tenga el enlace no averigua
   a quién pertenece un móvil.
Entra: el enlace que recibió al reservar; las reglas de cancelación de Citas.
Sale: nada se escribe. El enlace sigue valiendo aunque el negocio apague la página.
Si falla: un enlace que no existe, revocado o de una reserva borrada: «Esa reserva no existe o su enlace ya
no es válido.».
Implicados: APPOINTMENT-F06

### ONLINE_BOOKING-F11 La clienta cancela su reserva con su enlace
<!-- origen: nuevo (cancelar desde el enlace de la confirmación dentro de la política del negocio, como Square, Treatwell, SimplyBook.me y Acuity) -->
Estado: hecho (operación; la página es de `base`)
Actor: clienta (sin sesión)
Pantalla: la página de su reserva (`base`); en desarrollo, la vista previa
Pasos:
1. Desde su enlace pulsa **Cancelar la reserva** (motivo opcional).
2. Se aplica la política de Citas: «Permitir que la clienta cancele su cita» y «Antelación mínima para
   cancelar». La cita queda **Cancelada**, con «Lo pidió la clienta» en su historial. La política vale
   igual cuando el equipo prueba el enlace desde la vista previa.
Entra: el enlace de una reserva pendiente o confirmada, sin cobrar.
Sale: `appointment.appointment.cancelled`.
Si falla: «La cancelación online no está disponible. Ponte en contacto con el negocio.»; «Esta cita solo se
puede cancelar online con N horas de antelación…»; una ya cancelada o completada, el motivo de Citas.
Implicados: APPOINTMENT-F06, APPOINTMENT-F19

### ONLINE_BOOKING-F12 Borrar los datos de una clienta (RGPD)
<!-- origen: old-hub:HUB-F250 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en Reservas)
Pasos:
1. En **Clientes** se borran los datos personales de una ficha.
2. Citas vacía sus citas (APPOINTMENT-F24); esta app **revoca sus enlaces** (dejan de funcionar) y olvida el
   rastro del dispositivo con el que reservó. Repetirlo no cambia nada más.
Entra: el aviso de Clientes con la ficha borrada, que entrega el relay del worker.
Sale: nada propio: la reserva queda sin nombre en la bandeja y su enlace ya no abre nada.
Si falla: el relay reintenta la reacción sola; no se queda a medias.
Implicados: APPOINTMENT-F24, CUSTOMER-F16

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien habla) y la
API, con las mismas reglas y permisos. Una reserva se nombra por su id, su número (`APT-…`) o **como lo dice
una persona**: la clienta (nombre, teléfono o email) y el día («la de Ana de mañana»); sin día, su próxima
reserva online. Si vale para varias, se dicen cuáles y se pide el número.

### Lo que ofrece: consultas

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las reservas online, con búsqueda, filtros y orden, en páginas (hasta 100) | ver reservas | F08 | `online_booking.booking.list` |
| Una reserva | ver reservas | F08 | `online_booking.booking.get` |
| La configuración de la página y las reglas de reserva | ver reservas | F07 | `online_booking.settings.get` |
| Página, servicios, horas libres y reserva por enlace (públicas) | `online_booking.public` | F01, F10 | `online_booking.public.page`, `.services`, `.slots`, `.booking` |

### Lo que ofrece: acciones

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Confirma | confirmar reservas (+ cambiar citas) | F02 | `online_booking.booking.confirm` |
| Completa | cambiar reservas (+ cambiar citas) | F03 | `online_booking.booking.complete` |
| Marca no presentada | cambiar reservas (+ cambiar citas) | F04 | `online_booking.booking.no_show` |
| Cancela, con motivo | cambiar reservas (+ cambiar citas) | F05 | `online_booking.booking.cancel` |
| Borra | borrar reservas (+ borrar citas) | F06 | `online_booking.booking.delete` |
| Guarda la configuración (y las reglas de Citas) | ajustes (+ ajustes de Citas para las reglas) | F07 | `online_booking.settings.update` |
| Reserva y cancela desde la página (públicas) | `online_booking.public` | F01, F11 | `online_booking.public.book`, `.cancel` |

No-show, cancelar y borrar son de **riesgo alto** para el asistente: pide confirmación antes. Las acciones de
la bandeja las hace Citas con el permiso de quien actúa: hace falta el de esta app **y** el de Citas.

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `online_booking.booking.created` | Una clienta reserva desde la página | La cita (`appointment_id`), su número, la clienta y la hora; nunca notas |
| `online_booking.settings.updated` | Guardar la configuración con algún cambio de la página | Nada |

El resto de hechos (confirmada, cancelada, completada, no presentada, borrada) son los avisos de Citas.

### A qué reacciona

| Aviso de otra app | Qué hace | Flujos |
|---|---|---|
| `customer.customer.erased` (Clientes) | Revoca los enlaces de las reservas de esa ficha y olvida la huella del dispositivo | F12 |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver reservas (las de su agenda, si solo ve la suya en Citas) | sí | sí | sí | sí | `online_booking.view_booking` |
| Cambiar reservas (completar, no-show, cancelar) | sí | sí | sí | no | `online_booking.change_booking` |
| Confirmar reservas | sí | sí | sí | no | `online_booking.confirm_booking` |
| Borrar reservas | sí | sí | no | no | `online_booking.delete_booking` |
| Configurar la página | sí | sí | no | no | `online_booking.manage_settings` |
| Probar la página pública (vista previa) | sí | sí | no | no | `online_booking.public` |

## Para quien lo mantiene

- **Decisión de diseño** (ver «Decisiones de mercado»): Reservas online **no guarda reservas propias**. Una
  reserva online es una cita de Citas con `source = "online"`; esta app es la configuración de la página, la
  bandeja sobre esas citas, las operaciones públicas y el enlace de la clienta. Nada duplicado: estados,
  numeración, horas libres, antelaciones, confirmación automática y política de cancelación son de Citas;
  qué servicio se reserva online, de Servicios (`Service.allow_online_booking`); la ficha, de Clientes.
- **`requires = ["appointment", "customer", "service", "staff"]`**: lee las citas, busca y crea fichas, lee
  el catálogo y los profesionales de un servicio (`appointment.queries.bookable_members`, que devuelve
  fichas de Personal). Escribe en ellas solo por sus operaciones: `appointment.appointment.create`,
  `.confirm`, `.complete`, `.mark_no_show`, `.cancel`, `.delete`, `.update` (solo el email que tecleó la
  clienta como contacto de la cita, si su ficha no tiene), `appointment.settings.update`,
  `appointment.availability.slots` y `customer.customer.create`. El interruptor de un servicio en Ajustes
  lo guarda la página con `service.service.update`, con el permiso de quien lo toca.
- Modelos (UUIDv7, sin `hub_id`): `Settings` (una fila; sin ella, los de fábrica) y `Booking` (una por cita
  reservada desde la página: la cita, el hash del enlace y la huella del visitante).
- **Operaciones públicas**: permiso `online_booking.public` (contrato arriba). Para lo que piden a otras
  apps usan `delegated(ctx)`: el mismo contexto con los permisos justos de Citas, Clientes, Servicios,
  Horarios y Personal (como `appointment.queries.reader`), y como actor «online booking» cuando no hay
  persona. La reserva va con `source = "online"`: Citas aplica la antelación, la ventana y que la clienta
  nunca solapa, y decide Pendiente o Confirmada.
- **Ficha por teléfono**: el móvil se normaliza a E.164 (`apps.customer.phones`); entre las fichas vivas con
  ese número gana la de nombre igual (sin acentos ni mayúsculas) y, si no, la primera por nombre; sin
  ninguna, se crea con `customer.customer.create` (origen `website`). La página nunca cambia una ficha que
  ya existe.
- **«Sin preferencia»**: se prueba con cada profesional que hace los servicios, por orden de nombre, cada
  intento en su punto de guardado; gana el primero que Citas acepta. Si ninguno, el motivo común o «Esa hora
  ya no está libre» (`online_booking.time_taken`).
- **Concurrencia**: `public.book` bloquea primero la fila de `Settings` (`page_settings(lock=True)`): las
  reservas públicas del hub van una tras otra, así que los límites por dispositivo, por negocio y por móvil
  y la ficha de un móvil nuevo se deciden sobre lo que escribió la anterior (sin fichas duplicadas). Además,
  Citas bloquea la ficha del profesional antes de juzgar el hueco (`tests/test_concurrency.py`, con hilos).
- **Límites**: 5 por visitante y hora y 100 por negocio y hora (429; constantes de `services.py`), y las
  próximas por móvil de los Ajustes (409; 3 de fábrica); se cuentan sobre `Booking` y las citas, en la
  transacción de la reserva.
- **Reloj**: el de Citas (`apps.appointment.queries.now`, `business_zone`); los tests lo fijan.
- Las reacciones (`events.py`) las entrega el relay del outbox del worker (`base/relay.py`, ya en la fase 1);
  `tests/test_relay.py` las prueba de punta a punta con el bucle real del worker y el aviso real de Clientes.
  Sus dos avisos no los escucha ninguna app salvo Automatizaciones, que se apunta a todos (`"*"` en
  `apps/flow/events.py`); lo que hace con ellos es de FLOW-F21, que sigue `parcial`.

### Contrato con la página pública (para `base`)

La página sin sesión (`/p/<slug>/book`, plantillas de Django en el dominio de la web pública, pendiente del
bloque de la web pública) **no es de esta app**: la sirve `base`. Esta app le da las operaciones:

| Qué | Operación | Entrada → salida |
|---|---|---|
| Textos y reglas de la página | `online_booking.public.page` | nada → título, bienvenida, color, logo, email obligatorio, elegir profesional, notas, política de cancelación, antelaciones, si la clienta puede cancelar, zona horaria |
| Servicios reservables online | `online_booking.public.services` | búsqueda, página (≤ 100) → servicios con categoría, precio y duración (o `null` si Servicios no los enseña) y sus profesionales (vacío si no se elige) |
| Horas libres | `online_booking.public.slots` | servicios, día, profesional opcional → horas (con los profesionales libres si se elige) |
| Reservar | `online_booking.public.book` | servicios, profesional opcional, hora de pared, nombre, móvil, email, nota → número, estado, hora, servicios, profesional, mensaje y **`token`** (se enseña una vez) |
| Ver la reserva | `online_booking.public.booking` | `token` → número, estado, hora, servicios, profesional, si puede cancelar y hasta cuándo (nunca el nombre de la ficha) |
| Cancelar | `online_booking.public.cancel` | `token`, motivo → la reserva cancelada |

Cómo las expone la plataforma (fase 2, bloque 7 «puerta pública `/p/`»):

- **Contexto**: `base` llama a la operación en el propio proceso, sin ruta ninja anónima, con
  `OperationContext(scope=<hub del Host>, actor=None, permissions={"online_booking.public"}, request=<la
  petición>)`. Nada sale del cuerpo de la petición: el hub lo da el Host y el visitante, la petición.
- **Permiso**: `online_booking.public` no lo tiene ningún rol salvo propietario y administrador (para la
  vista previa); el empleado y el responsable no. La operación pública se apoya, para lo que pide a Citas,
  Clientes y Servicios, en un contexto delegado con solo lo que necesita (reservar, ver horas, crear o
  buscar la ficha, cancelar), nunca en el de un rol.
- **Visitante**: los límites por dispositivo se cuentan con una huella del visitante (HMAC con la
  `SECRET_KEY` de la última IP de `X-Forwarded-For`, la que añade el ALB, o de `REMOTE_ADDR` sin proxy). La
  IP no se guarda.
- **Antispam de la página**: el campo trampa (honeypot) y la espera mínima de envío son de la plantilla de
  `base`; los límites de esta app no dependen de ellos.
- **Enlace personal**: `token` de 43 caracteres (`secrets.token_urlsafe(32)`); se guarda solo su hash
  (SHA-256). `base` lo pone en la URL de la confirmación (`/p/<slug>/book/<token>`), nunca en un log, y al
  llamar a `public.booking`/`public.cancel` lo pasa en el cuerpo o en una cabecera, no en una query string.
  Las rutas de sesión de esta app (`/api/online_booking/public/booking?token=…`, solo dueño y administrador,
  para la vista previa) lo llevan en la query: aceptado, porque no son la puerta pública.
- **Enlace con la página apagada**: ver y cancelar con el enlace siguen funcionando aunque el negocio apague
  la página (la reserva sigue siendo de la clienta); reservar, no.
- **Errores**: el sobre único `{"error": {"code", "message", "fields"?}}` en el idioma del visitante; 404
  `online_booking.page_disabled` y `online_booking.booking_not_found`, 409 con el código de Citas o de esta
  app, 422 por campo y 429 `online_booking.too_many_bookings` / `online_booking.busy`.
- **Privacidad**: el aviso de privacidad y el texto legal del formulario son de la plantilla de `base`.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/pages/BookingsPage.vue` (bandeja), `SettingsPage.vue` y `PreviewPage.vue` (solo en desarrollo).
- Los estados permitidos y el reloj se leen de `apps/appointment/frontend/lib/states.ts` y `clock.ts`: las
  mismas reglas que la agenda, sin copiarlas.
- Datos solo por `useLive`/`useCommand` (la vista previa, por el cliente de la API: lo público no se sigue en
  vivo); listas en ventanas de 100.

## Lo que queda fuera

- **La página pública sin sesión** (`/p/<slug>/book`): es de `base` (bloque de la web pública); aquí está su
  contrato y la vista previa.
- **Verificar el móvil con un código (SMS o WhatsApp)**: falta un canal de envío; hasta entonces, cualquiera
  que sepa un teléfono puede reservar a su nombre (la cita sale con el nombre de esa ficha). Los límites
  frenan el abuso, no la suplantación.
- **Bloquear a una clienta** para que no reserve online (Fresha, Timely): el bloqueo es una marca de la ficha
  y le toca a Clientes; la confirmación manual es hoy la válvula.
- **Elección de profesional obligatoria** (el tercer modo de Timely) y el reparto por turnos o la
  reasignación dinámica de Fresha: hoy, elegir o «sin preferencia» (el primero libre por orden de nombre), o
  que asigne el negocio.
- **Mover la reserva desde el enlace**: Citas ya lo permite en nombre de la clienta
  (`appointment.appointment.reschedule`); la página lo ofrecerá con su bloque.
- **Avisos a la clienta** (confirmación, recordatorio, cancelación por email o WhatsApp), **depósito o cargo
  por no presentarse**, **lista de espera** y **calendario externo**: fuera del MVP, como en el producto actual.
- **Margen entre citas** (el «Buffer entre reservas» del producto actual, que nadie leía): los márgenes
  antes y después de cada servicio son de Servicios y Citas aún no los aplica.

## Contradicciones señaladas (no resueltas aquí)

- **Dónde vive la página pública**: el encargo y este documento la ponen en `/p/<slug>/book` del host del hub;
  `CLAUDE.md` («Frontend y admin») dice «Web/carta pública por hub (pendiente): plantillas en un dominio
  aparte». Lo decide el bloque de la web pública; el contrato de operaciones vale para los dos.
- **Tablas compartidas en la fase 1**: sin tenencia todavía, la fila única de `Settings` (y `Booking`) la
  comparten todos los ámbitos de la plataforma; es el estado de la fase 1, no del módulo: en la fase 2 cada
  hub la tiene en su BD.

Las dos siguen escritas, sin elegir, en la ronda 2026-10-21 (CLOSE-ONLINE_BOOKING) de `PLAN-HUB.md`.

## Lo que NO hace, a propósito

- No guarda reservas ni estados propios: la reserva es la cita.
- No reserva para la clienta desde dentro: eso es «Añadir cita» de la agenda (APPOINTMENT-F01).
- No retiene un hueco mientras la clienta decide.
- No cambia una ficha de Clientes que ya existe desde la página.

## Cambios frente al producto actual

| Producto actual | Ahora | Motivo |
|---|---|---|
| Libro de reservas propio (`BK-00001`, estados propios) | La reserva es una cita de Citas (`APT-…`) | El mercado: la reserva online ocupa el hueco en la agenda desde el primer momento; sin doble reserva |
| F01 «Tomar una reserva a mano» (texto libre) | La clienta reserva sola desde la página; desde dentro se reserva en la agenda | Lo de dentro ya es «Añadir cita» de Citas; dos formularios para lo mismo es un camino de más |
| Sin comprobar el hueco | Las horas libres y la reserva las juzga Citas | No existía; era la principal carencia del producto actual |
| `bookings.create/confirm/cancel/complete/no_show/delete` | `booking.confirm/cancel/complete/no_show/delete` (sobre la cita) y `public.book` | Mismas acciones; el alta la hace la clienta |
| No-show en cualquier momento | Solo pasada la hora | Regla de Citas (decisión de mercado de Citas) |
| El empleado veía todas las reservas | Ve las de su agenda | Regla de Citas: el empleado ve su propia agenda |
| `settings_missing` (sin fila no se reserva) | Interruptor «Página pública activada» | Lo mismo, dicho claro; los ajustes salen con valores de fábrica |
| Antelación mínima (horas) / máxima (días) / «Duración de slot» propias | Las de Citas: minutos, días e «Intervalo entre huecos» | Una sola regla para la agenda, WhatsApp y la página |
| «Teléfono obligatorio» | El móvil siempre es obligatorio | Es como se reconoce a la clienta (Clientes) y lo que pide todo el mercado |
| «Email obligatorio» encendido de fábrica | Apagado de fábrica | En las herramientas de salón el email es opcional (Square, Timely, Mangomint) |
| Sin límite de reservas por persona | «Reservas próximas por móvil» (3 de fábrica) y límites por dispositivo y negocio | Antiabuso del mercado (SimplyBook.me, Cal.com, Calendly) |
| «Buffer entre reservas» | No se porta | Nadie lo leía; el margen es de cada servicio (Servicios) |
| `_on_customer_merged` | Lo hace Citas (APPOINTMENT-F23) | Esta app no guarda la ficha |
| No escuchaba el borrado RGPD | Revoca los enlaces y olvida la huella | RGPD |
| Avisos `online_booking.booking.confirmed/cancelled/…` | Los de Citas | El hecho ocurre en la cita |

## Paridad con el producto actual

### Órdenes y consultas (`module.json`: 9 órdenes, 3 consultas)

| Producto actual | Ahora | Nota |
|---|---|---|
| `online_booking.bookings.create` (+ `_booking_create`) | `online_booking.public.book` (la clienta) · `appointment.appointment.create` (el equipo, en la agenda) | Comprueba el hueco; ficha por móvil |
| `online_booking.bookings.confirm` | `online_booking.booking.confirm` → `appointment.appointment.confirm` | Por número o por clienta y día |
| `online_booking.bookings.cancel` | `online_booking.booking.cancel` (con motivo) → `appointment.appointment.cancel` | Riesgo alto para el asistente |
| `online_booking.bookings.complete` | `online_booking.booking.complete` → `appointment.appointment.complete` | |
| `online_booking.bookings.no_show` | `online_booking.booking.no_show` → `appointment.appointment.mark_no_show` | Solo pasada la hora; riesgo alto |
| `online_booking.bookings.delete` | `online_booking.booking.delete` → `appointment.appointment.delete` | Borrado lógico; riesgo alto |
| `online_booking.settings.upsert` | `online_booking.settings.update` (+ `appointment.settings.update` para las reglas) | Solo lo enviado, todo o nada |
| `online_booking._on_customer_merged` | `appointment.customer.reassign` (Citas) | Esta app no guarda la ficha |
| `online_booking.bookings.list` | `online_booking.booking.list` | Búsqueda, filtros por columna, orden, ≤ 100 |
| `online_booking.bookings.get` | `online_booking.booking.get` | Por id, número o clienta y día |
| `online_booking.settings.get` | `online_booking.settings.get` | Con las reglas de Citas |
| — | `online_booking.public.page`, `.services`, `.slots`, `.booking`, `.cancel`; `online_booking.customer.erase` | Nuevas: la página pública y el RGPD |

### Pantallas (`ui/`: `erp-online-booking-list`, `erp-online-booking-settings`)

| Producto actual | Ahora | Nota |
|---|---|---|
| Reservas: tabla de 50 con buscador, filtros Ref/Cliente/Servicio/Personal/Fecha/Hora/Estado y acciones Confirmar/Completar/No-show/Cancelar/Borrar | `BookingsPage.vue`: lo mismo (Fecha de un día; la Hora se busca en la tabla), columna «Reservada», teléfono bajo el nombre, acciones en gris por estado, diálogo de cancelar con motivo y confirmación de borrar | Sin «Hora» como filtro propio: el filtro de día y el orden por fecha bastan (la columna sigue) |
| El «+» con el panel de alta (Cliente, Servicio, Personal, Fecha, Hora, Min.) | No está: la reserva del equipo es «Añadir cita» de la agenda | Ver «Cambios frente al producto actual» |
| Ajustes: los 15 campos y «Guardar» / «Configuración guardada.» | `SettingsPage.vue`: los campos de la página, las reglas de Citas y los servicios online; mismos textos | Sin «Duración de slot» ni «Buffer» propios (reglas de Citas / márgenes de Servicios) ni «Teléfono obligatorio» (siempre) |
| — | `PreviewPage.vue` (solo desarrollo) | El recorrido de la página pública |

## Decisiones de mercado (2026-10-15)

Las dudas del porte, resueltas con la skill `market-decision` (al menos 8 referencias cada una; (F) página
leída, (S) solo el extracto del buscador).

| Duda | Gana | Referencias |
|---|---|---|
| ¿La reserva online es una cita de la agenda (que ocupa el hueco) o una solicitud aparte que se convierte al aceptarla? | **Una cita de la agenda desde el primer momento**, Pendiente si el negocio confirma a mano, Confirmada si no (ajuste, automática de fábrica); la bandeja lista las pendientes; rechazar = cancelar (libera el hueco). Una solicitud aparte duplica la lógica de huecos y abre la doble reserva | Square (F) squareup.com/help/us/en/article/8444-accept-or-decline-appointments · Odoo (F) odoo.com/documentation/18.0/applications/productivity/appointments.html · SimplyBook.me (F) help.simplybook.me/wiki/Approve_Bookings_custom_feature · Cal.com (F) cal.com/docs/how-to-guides/how-to-set-up-requires-confirmation · Wix Bookings (S) support.wix.com/en/article/wix-bookings-requiring-approval-for-appointments · Vagaro (F) vagaro.com/learn/the-quickstart-guide-to-vagaro · MyTime (S) help.mytime.com/support/solutions/articles/31000175045 · Booksy (F) biz.booksy.com/blog/don-t-overpay-for-your-booking-system · foro: Calendly (F) community.calendly.com/how-do-i-40/approve-bookings-5906, Square (F) community.squareup.com/t5/Questions-How-To/Is-there-a-way-to-make-it-so-that-I-have-to-accept-an/m-p/123405 |
| ¿Qué pide el formulario y cómo se reconoce a la clienta? | **Nombre y móvil obligatorios, email opcional** (ajuste); la ficha se reconoce por el **móvil en E.164**, se enlaza o se crea, y la página nunca cambia una ficha que existe; sin código SMS en la v1 | Fresha (F) fresha.com/help-center/knowledge-base/online-presence/102398-learn-how-clients-book-appointments-online · Square (S) community.squareup.com/t5/Questions-How-To/Appointments-Client-Code-needed-to-book-online/m-p/130880 · Mangomint (F) mangomint.com/learn/online-booking-from-the-clients-perspective · Timely (S) help.gettimely.com/article/827-client-login-faq · Acuity (F) acuityscheduling.com/learn/how-clients-book-with-acuity · Microsoft Bookings (F) learn.microsoft.com/en-us/microsoft-365/bookings/define-service-offerings · Google Calendar (F) support.google.com/calendar/answer/10729749 · SimplyBook.me (S) tech-support.simplybook.me/t/719-cant-book-using-new-simplybook-account-client-phone-value-is-wrong/725 · foro: Square, fichas duplicadas (S) community.squareup.com/t5/Appointments-Bookings/Customer-Profile-Duplication/td-p/829070 |
| ¿Qué antiabuso lleva la página pública? | **Límite de reservas próximas por móvil (ajuste), límite por dispositivo y hora, límite por negocio y hora, y la confirmación manual como válvula**; campo trampa en la plantilla. Sin reCAPTCHA (choca con la CSP, nada por CDN) ni SMS por reserva (coste). Bloquear clienta, a Clientes | SimplyBook.me (F) help.simplybook.me/wiki/Anti-Fraud/Spam_Protection_Custom_Feature · Cal.com (F) cal.com/help/event-types/booker-active-booking-limit · Fresha (F) fresha.com/help-center/knowledge-base/clients/346-block-clients-from-booking · Timely (S) help.gettimely.com/hc/en-gb/articles/4410438923031-How-to-block-a-client · Calendly (F) calendly.com/help/abuse-prevention · Google Calendar (F) support.google.com/calendar/answer/11902347 · Square (F) squareup.com/help/us/en/article/5351-manage-your-square-appointments-account-settings · Vagaro (F) vagaro.com/pro/updates/limit-customer-booking · Microsoft Bookings (F) learn.microsoft.com/en-us/microsoft-365/bookings/define-service-offerings |
| ¿Cómo gestiona su reserva la clienta sin cuenta? | **Enlace secreto en la confirmación** que enseña la cita y la cancela; el corte en horas lo aplica el servidor y, pasado, «contacta con el negocio» | Square (F) community.squareup.com/t5/Using-Square/How-do-clients-cancel-their-own-appointments/m-p/21338 y squareup.com/gb/en/appointments/features/cancellation-policy · Treatwell (F) treatwell.es/en/info/booking-terms-and-conditions · SimplyBook.me (F) help.simplybook.me/wiki/Cancellation_Policy_custom_feature · Acuity (F) acuityscheduling.com/learn/how-clients-book-with-acuity · Odoo (F) odoo.com/documentation/19.0/applications/productivity/appointments.html · Microsoft Bookings (F) learn.microsoft.com/en-us/microsoft-365/bookings/set-scheduling-policies · Fresha (S) fresha.com/help-center/knowledge-base/calendar/102184-manage-online-bookings-settings · Calendly (F, sin corte: queja en su foro) calendly.com/help/how-to-add-a-cancellation-policy |
| «Sin preferencia» de profesional | **Estándar**; se asigna al **primer profesional libre por un orden fijo del equipo** (determinista, se puede probar); el negocio puede ocultar la elección | Fresha (F) fresha.com/help-center/knowledge-base/calendar/102178-set-up-new-appointment-assignment · Square (F) squareup.com/help/us/en/article/5351-manage-your-square-appointments-account-settings · Mangomint (F) mangomint.com/learn/adjusting-staff-selection-options-in-online-booking · SimplyBook.me (F) help.simplybook.me/wiki/Any_Employee_Selector_custom_feature · Timely (S) help.gettimely.com/hc/en-gb/articles/1500002268342 · Acuity (S) help.acuityscheduling.com/hc/articles/16676903042829 · Microsoft Bookings (F) learn.microsoft.com/en-us/microsoft-365/bookings/define-service-offerings · Odoo (F) odoo.com/documentation/18.0/applications/productivity/appointments.html · Calendly (S) help.calendly.com/hc/en-us/articles/4402432846999 |
| ¿Dónde viven antelaciones, intervalo y confirmación automática? | **En los ajustes de reserva online del negocio, un solo bloque**, que solo ata al canal de la clienta (la agenda interna no). Aquí son las reglas de Citas (que ya solo atan a la clienta y valen también para WhatsApp) y se editan desde los Ajustes de esta app | Square (F) squareup.com/help/us/en/article/5351-manage-your-square-appointments-account-settings · Fresha (S) fresha.com/help-center/knowledge-base/calendar/102184-manage-online-bookings-settings · Phorest (S) phorest.helpjuice.com/305579-your-checklist-for-going-live-with-online-bookings-gb · Vagaro (F) vagaro.com/learn/the-quickstart-guide-to-vagaro · Timely (S) help.gettimely.com/hc/en-gb/articles/33525019868183 · Microsoft Bookings (F) learn.microsoft.com/en-us/microsoft-365/bookings/set-scheduling-policies · Odoo (F) odoo.com/documentation/19.0/applications/productivity/appointments.html · Google Calendar (F) support.google.com/calendar/answer/10729749 · Calendly (S) help.calendly.com/hc/en-us/articles/1500004754122 |

La duda abierta del módulo viejo («si debe seguir instalable mientras no exista la página pública, o
retirarse o fusionarse con Citas») queda resuelta por la primera fila: la reserva es una cita y esta app es
su puerta pública y su bandeja; no hay nada que fusionar.
