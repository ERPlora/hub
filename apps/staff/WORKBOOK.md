# Workbook — Personal (app)
Prefijo: STAFF
Alcance MVP: transversal (lo usa sobre todo la peluquería; el restaurante lee su directorio)
Estado de la app: hecha (servidor y páginas)

> Manual de usuario y especificación de la app `staff`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Personal del producto actual
> (`modules-workspace/modules/staff`, `origin/main` `ff1d857`). Hace lo mismo, se verá igual y conserva
> toda su funcionalidad salvo lo que dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Personal es la **plantilla del negocio como recurso de trabajo**: quién trabaja, qué rol de catálogo
tiene («estilista», «camarero»), en qué horario trabaja cada semana, cuándo falta, cuánto cobra por hora
y qué comisión lleva. Responde a «**quién trabaja y atiende**», no a «quién entra»:

- Las **cuentas de acceso**, su papel de permisos (propietario, administrador, responsable,
  empleado) y el PIN son de la plataforma, no de Personal. Personal no crea cuentas ni da permisos.
- La **ficha** de un profesional puede **colgar** de una cuenta del negocio («Usuario del Hub»), y
  esa unión es opcional en los dos sentidos: un profesional sin cuenta aparece solo en la agenda, y una
  cuenta sin ficha no atiende. Desactivar una cuenta no toca la ficha.
- El **rol de Personal** es una etiqueta de catálogo y **no concede permisos**: los da el papel de la
  cuenta.

Quién la usa:

- El **propietario** y el **administrador** lo hacen todo, también desactivar y dar de baja.
- El **responsable** da de alta y edita fichas, roles, horarios y ajustes, ve la tarifa, la comisión,
  las notas de RRHH y lo que ha ganado cada profesional en **Comisiones**, registra ausencias y las
  aprueba, rechaza o cancela.
- El **empleado** ve el directorio, los horarios y quién falta (nunca la tarifa ni el motivo de una
  ausencia ajena), ve su propia ficha y sus ausencias, **pide sus ausencias** y retira las que aún
  están pendientes.

Citas (cuando llegue) lee de aquí quién es reservable, su horario y sus ausencias aprobadas; el TPV
y la cocina leen el directorio para nombrar a quien atiende. Al cerrar el día, **Comisiones** da lo que
ha vendido y ganado cada profesional.

## Referencia adoptada

- **Salón (Fresha, Vagaro, Mangomint, Square Appointments)**: el profesional como recurso de la
  agenda con su horario semanal y sus ausencias, reservable o no, y su comisión.
- **Odoo Empleados y Dynamics 365 Business Central**: la baja guarda fecha y motivo en la ficha; el
  puesto de trabajo («Job Position») es una etiqueta que se crea, se renombra, se retira y no se
  repite.
- **Factorial, Personio, BambooHR, Deputy, Homebase y Square Team**: el empleado **pide** su
  ausencia y el responsable la aprueba o la rechaza; pendiente → aprobada o rechazada, pendiente o
  aprobada → cancelada; rechazada y cancelada no vuelven atrás. Media jornada de mañana y otra de
  tarde el mismo día son compatibles.
- **Qué horario manda un día** (Fresha «regular shifts» + excepciones): el horario con fechas gana
  al habitual, y un horario de un solo día es la forma de dar una excepción.

## Antes de empezar

1. Las cuentas de quien vaya a entrar al TPV se crean en el SaaS (miembros del negocio); solo hacen
   falta si quieres vincular su ficha.
2. En **Personal → Roles**, crea los roles de catálogo del negocio (STAFF-F04). Un rol no es un
   permiso.
3. En **Personal → Personal**, da de alta a cada profesional (STAFF-F01), márcalo **Reservable** si
   va a recibir citas y vincula su cuenta si la tiene (STAFF-F03). Para muchos a la vez, el asistente
   los da de alta de golpe (STAFF-F07).
4. En **Personal → Horarios**, crea el horario semanal de cada profesional (STAFF-F13). Sin horario,
   Citas no restringe por horario: solo una ausencia aprobada impide la reserva (STAFF-F16).
5. Las ausencias se piden o se registran en **Ausencias** (STAFF-F17, STAFF-F24) y solo cuentan
   para la agenda cuando están **Aprobadas** (STAFF-F18).
6. La zona horaria del negocio decide qué es «hoy» para «Ausentes hoy», para el bloqueo de
   Desactivar y para el último día de una baja.
7. Los **Ajustes de Personal** existen y se guardan (STAFF-F22), pero todavía ningún comportamiento
   los lee.

## Pantallas

Personal se abre desde el menú **Personal** y tiene cuatro pestañas: **Personal**, **Roles**,
**Ausencias** y **Horarios**, más **Comisiones** (para quien ve la compensación) y **Ajustes** (para
quien puede guardarlos). Lo que una persona no puede hacer no aparece, y la app lo rechaza aunque lo
intente por la API o por el asistente.

### Personal
Encima de la tabla, tres cifras: **Plantilla activa**, **Ausentes hoy** y **Ausencias pendientes**
(STAFF-F23). Debajo, la tabla con buscador «Buscar miembro…» (nombre, apellidos, email, teléfono, nº de empleado o rol),
columnas **Nombre, Rol, Email, Estado** y, solo para quien puede ver la compensación, **Tarifa/h**;
**Teléfono** existe pero sale oculto. Se ordena por cualquier columna y se filtra por Nombre,
Apellidos, Email, Teléfono, Rol, Estado (**Activo**, **De baja**, **Inactivo**), Reservable, fecha de
alta, color y usuario; 50 por página. Las fichas dadas de baja no salen.

El botón **+** abre **Nuevo**; una fila abre **Editar · {nombre}**. Formulario: **Nombre, Apellidos,
Email, Teléfono, Nº de empleado, Rol** («Sin rol»), **Usuario del Hub** («Sin acceso al Hub»),
**Estado** (solo al editar: Activo, Inactivo, De baja), **Reservable**, **Margen entre citas (min)**,
**Fecha de alta**, **Color**, **Especialidades**, **Bio** y, para quien puede ver la compensación,
**Tarifa por hora** y **Comisión (%)**. Acciones de fila para el propietario y el administrador:
**Desactivar** y **Dar de baja**, las dos con confirmación.

### Roles
Tabla con buscador «Buscar rol…» y columnas **Rol, Descripción, Miembros** (cuántas personas
**Activas** lo llevan). **+** abre **Nuevo** (**Nombre del rol, Descripción, Color**); una fila abre
**Editar**, donde además se **retira** el rol (deja de ofrecerse) o se vuelve a activar.

### Ausencias
Encima de la tabla, **Ausencias de hoy**: quién falta hoy, con el tipo y, si es solo una parte del día,
sus horas (STAFF-F20). Debajo, la tabla con buscador por nombre y columnas **Miembro, Tipo, Desde, Hasta, Estado**, con filtros por
miembro, tipo, estado y fechas. Acciones de fila: **Aprobar**, **Rechazar** y **Cancelar**, donde
valen. **+** abre el formulario: **Miembro** (solo para quien gestiona ausencias; el empleado la pide
para sí), **Tipo** (Vacaciones, Baja por enfermedad, Asuntos propios, Formación u Otros), **Desde,
Hasta, Día completo** (si se apaga, **Desde (hora)** y **Hasta (hora)**) y **Motivo**. El motivo y las
notas solo los ven quien tiene permiso y la propia persona.

### Horarios
Selector **Miembro** y la tabla de sus horarios: **Horario, Por defecto, Desde, Hasta, Activo,
Horas** (la semana resumida). Acciones de fila: **Editar**, **Activar / desactivar** y **Eliminar**
(con confirmación). **+** abre **Nuevo**: **Horario** (nombre; vacío, «Horario habitual»), **Vigente
desde, Vigente hasta, Por defecto** y una fila por día de la semana con **Inicio, Fin, Inicio
descanso, Fin descanso** (o «No trabaja»).

### Comisiones
Arriba, el periodo: «Hoy» (al entrar), «Ayer», «Esta semana» (desde el lunes), «Este mes» (desde el
día 1) o «Personalizado», que abre «Desde» y «Hasta» con los días que había en pantalla; al lado, los
días que cuenta. Debajo, dos cifras: **Vendido** y **Comisiones** del periodo. Después, la lista con
buscador «Buscar profesional…» y columnas **Nombre, Rol, Vendido, Comisión %** y **Comisión**: cada
persona que puede cobrar comisión (Activa o De baja), también sin ventas y con comisión 0, y quien vendió
en el periodo aunque ya no esté («Ya no trabaja aquí» o «Inactivo» junto al nombre). Se ordena por
nombre, rol, vendido o comisión. En el móvil, una tarjeta por persona. Se pone al día sola al cobrar, anular
o devolver una venta y al cambiar una ficha.

### Ajustes de Personal
«Inicio de jornada (HH:MM)», «Fin de jornada (HH:MM)», «Duración del descanso (minutos)»,
«Antelación mínima de reserva (horas)», «Horas máximas por día», «Umbral de horas extra
(horas/semana)», «Mostrar fotos del personal», «Mostrar biografía del personal», «Permitir elegir
profesional», «Avisar de nueva cita», «Avisar de cancelación» y **Guardar**. Mientras el negocio no
ha guardado nunca, salen los valores propuestos.

### Paneles del inicio
El Hub todavía no tiene un Inicio con paneles. Mientras tanto, los cinco paneles del producto actual
salen dentro de Personal: **Plantilla activa**, **Ausentes hoy** y **Ausencias pendientes** encima de
la tabla de Personal, **Ausencias de hoy** encima de la de Ausencias y **Empleados por rol** en la
columna «Miembros» de Roles (STAFF-F20 y STAFF-F23).

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado; cada cifra enseña «…». |
| Vacío | «Sin miembros del staff.», «Sin roles definidos.», «Sin solicitudes de ausencia.» o «Este miembro aún no tiene horarios.»; con búsqueda o filtro, «Sin resultados». «Ausencias de hoy» sin nadie: «Nadie falta hoy.». Comisiones sin nadie que pueda cobrarla: «Nadie del equipo puede cobrar comisión todavía.»; sin Ventas en el negocio, «Las comisiones salen de las ventas» y «Activa Ventas para ver lo que ha ganado cada profesional.», sin lista. |
| Error | El aviso de la tabla con «Reintentar»; en Ajustes, «No se pudieron cargar los ajustes» con «Reintentar» y sin formulario. Las cifras dicen «No se pudieron cargar las cifras» y «Ausencias de hoy», «No se pudo cargar quién falta hoy», y la tabla sigue funcionando. Un rechazo de un formulario sale dentro del formulario, sin perder lo tecleado; el de una acción de fila, encima de la tabla. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| STAFF-F01 | Dar de alta a un profesional | hecho |
| STAFF-F02 | Editar la ficha de un profesional | hecho |
| STAFF-F03 | Vincular la ficha con una cuenta del negocio | hecho |
| STAFF-F04 | Crear, editar y retirar un rol | hecho |
| STAFF-F05 | Desactivar a un profesional | hecho |
| STAFF-F06 | Dar de baja a un profesional | hecho |
| STAFF-F07 | Dar de alta a varios profesionales de golpe | hecho (asistente y API) |
| STAFF-F08 | Ver mi propia ficha y mis ausencias | hecho |
| STAFF-F09 | Dar el equipo a otras apps | hecho (sin pantalla) |
| STAFF-F13 | Crear el horario semanal de un profesional | hecho |
| STAFF-F14 | Editar un horario | hecho |
| STAFF-F15 | Activar, desactivar o eliminar un horario | hecho |
| STAFF-F16 | Saber cuándo puede trabajar un profesional | hecho (sin pantalla) |
| STAFF-F17 | Registrar una ausencia | hecho |
| STAFF-F18 | Aprobar o rechazar una ausencia | hecho |
| STAFF-F19 | Cancelar una ausencia | hecho |
| STAFF-F20 | Ver quién falta hoy | hecho |
| STAFF-F21 | Dar la tarifa y la comisión de cada profesional | hecho |
| STAFF-F22 | Cambiar los ajustes de Personal | hecho |
| STAFF-F23 | Ver las cifras de la plantilla y por rol | hecho |
| STAFF-F24 | Pedir mi propia ausencia | hecho |

Los servicios que hace cada profesional (STAFF-F10, F11 y F12 del producto actual) no están en esta
app: ver «Cambios frente al producto actual».

### STAFF-F01 Dar de alta a un profesional
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f03 old-hub:HUB_SHELL-F81 old-hub:HUB_SHELL-F82 fi:modules/staff#command-staff-members-create fi:modules/staff#permission-role_permissions fi:modules/staff#query-staff-members-list old-hub:HUB-F145 old:staff/workflow/ficha.md#staff-f01 qa:modules/staff/create-employee -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Personal
Pasos:
1. En **Personal**, pulsa **+**: se abre **Nuevo** (sin Estado: la persona nace **Activa**).
2. Escribe Nombre y Apellidos (obligatorios, hasta 100 caracteres). Si quieres, Email, Teléfono,
   Nº de empleado, Rol, Usuario del Hub (STAFF-F03), Fecha de alta, Color (#RRGGBB),
   Especialidades, Bio, Margen entre citas y, con permiso de compensación, Tarifa por hora y
   Comisión (%). **Reservable** viene encendido.
3. Pulsa Guardar: la persona sale en la tabla como **Activa**.
Entra: el formulario; los roles activos (STAFF-F04), por id o por su nombre. La tarifa se guarda en
céntimos enteros; la comisión es un porcentaje de 0 a 100 con dos decimales. Por la API o el
asistente también se pueden dar el estado inicial y las notas de RRHH.
Sale: la ficha; Personal avisa de que hay una ficha nueva (`staff.member.created`).
Si falla: debajo de cada campo y sin guardar nada: nombre o apellidos vacíos, un email que no lo es,
un color que no es #RRGGBB, una tarifa negativa, una comisión fuera de 0–100, «Ese rol no está
disponible: no existe en este negocio, o se ha eliminado o retirado.», «Ese usuario del Hub no tiene
acceso a este negocio.» o la cuenta ya vinculada a otra ficha (STAFF-F03). Quien no puede ver la
compensación no puede enviarla: «Se necesita el permiso…». Dos fichas con el mismo nombre, email o nº
de empleado se aceptan.
Implicados: ninguno

### STAFF-F02 Editar la ficha de un profesional
<!-- origen: fi:modules/staff#command-staff-members-update fi:modules/staff#query-staff-members-get old:staff/workflow/ficha.md#staff-f02 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Personal
Pasos:
1. Pulsa la fila: se abre **Editar · {nombre}** (el asistente la nombra por su nombre).
2. Cambia lo que haga falta. **Estado** ofrece Activo, Inactivo y De baja (la baja definitiva es
   STAFF-F06). «Sin rol» quita el rol, «Sin acceso al Hub» desvincula la cuenta, y la Fecha de alta
   se puede **borrar**.
3. Guarda: solo cambia lo enviado.
Entra: la ficha (y, con permiso, su tarifa, comisión y notas).
Sale: la ficha cambiada (`staff.member.updated`). Guardar sin cambiar nada no avisa. Poner Inactivo
aquí no apaga Reservable, como hoy; volver a Activo tampoco lo enciende.
Si falla: los mismos rechazos que al dar de alta; «Ese miembro del personal no existe en este
negocio.» si ya no está (también si se dio de baja); poner **Inactivo** con ausencias pendientes o
aprobadas sin terminar: «Ese miembro tiene ausencias pendientes o aprobadas que aún no han terminado.
Resuélvelas primero.».
Implicados: ninguno

### STAFF-F03 Vincular la ficha con una cuenta del negocio
<!-- origen: old-hub:HUB_SHELL-F80 old-hub:HUB_SHELL-F84 old-hub:HUB_SHELL-F85 old-hub:HUB_SHELL-F88 old-hub:HUB-F146 old-hub:HUB-F148 old-hub:HUB-F149 old-hub:HUB-F158 old:staff/workflow/ficha.md#staff-f03 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Personal
Pasos:
1. En el formulario, abre «Usuario del Hub»: salen «Sin acceso al Hub» y las cuentas con acceso a
   este negocio.
2. Elige la cuenta de esa persona, o «Sin acceso al Hub» para desvincular, y guarda.
Entra: las cuentas activas con acceso a este negocio, solo su identificador y su nombre
(`staff.account.list`; las lee quien puede dar de alta o editar fichas).
Sale: el vínculo. Con él, la persona ve su propia ficha (STAFF-F08) y pide sus ausencias (STAFF-F24).
No cambia ningún permiso ni la comisión: una venta cuenta para quien se eligió al cobrarla (STAFF-F21).
Dar de baja la ficha libera la cuenta.
Si falla: «Ese usuario del Hub ya está vinculado a {nombre}. Un usuario del Hub solo puede
pertenecer a un miembro del equipo: desvincúlalo allí primero o elige otro usuario.»
(`staff.user_already_linked`), también si dos personas lo vinculan a la vez; «Ese usuario del Hub no
tiene acceso a este negocio.».
Implicados: ninguno

### STAFF-F04 Crear, editar y retirar un rol
<!-- origen: fi:modules/staff#command-staff-roles-create fi:modules/staff#query-staff-roles-list old:staff/workflow/ficha.md#staff-f04 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Roles
Pasos:
1. En **Roles**, pulsa **+**, escribe el Nombre (obligatorio, hasta 100) y, si quieres, Descripción y
   Color, y guarda: el rol sale con 0 miembros y ya se puede elegir en una ficha.
2. Para cambiarlo, pulsa su fila, cambia el nombre, la descripción, el color o el orden, o apaga
   **Activo** para retirarlo, y guarda.
Entra: lo tecleado.
Sale: el rol (`staff.role.created` o `staff.role.updated`). Un rol retirado deja de ofrecerse en las
fichas; las que ya lo llevan lo conservan. «Miembros» cuenta solo personas **Activas**. Un rol no
concede permisos.
Si falla: «Ya existe un rol con ese nombre.» (sin distinguir mayúsculas, `staff.role_name_taken`);
«Ese rol no existe en este negocio.».
Implicados: ninguno

### STAFF-F05 Desactivar a un profesional
<!-- origen: fi:modules/staff#command-handler-wasm-staff-members-deactivate-deactivate_staff_member old:staff/workflow/ficha.md#staff-f05 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Personal
Pasos:
1. En la fila, pulsa **Desactivar** y confirma «¿Sacar a {nombre} de la agenda? Deja de ser
   reservable; no se borra nada.».
2. La fila pasa a **Inactivo** y deja de ser reservable.
Entra: la ficha y sus ausencias pendientes o aprobadas que no han terminado (con el «hoy» del
negocio).
Sale: estado Inactivo y Reservable apagado (`staff.member.deactivated`). No toca horarios, ausencias,
cuenta ni citas. Para volver: STAFF-F02.
Si falla: «Ese miembro tiene ausencias pendientes o aprobadas que aún no han terminado. Resuélvelas
primero.» (`staff.active_time_off`; se rechazan o se cancelan en STAFF-F18 y STAFF-F19); «Ese
miembro del personal ya está inactivo.»; «Ese miembro del personal no existe en este negocio.».
Implicados: ninguno

### STAFF-F06 Dar de baja a un profesional
<!-- origen: fi:modules/staff#command-staff-members-delete old:staff/workflow/ficha.md#staff-f06 qa:modules/staff/offboard-employee -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Personal
Pasos:
1. En la fila, pulsa **Dar de baja**: el diálogo pide «Último día (hoy si se deja vacío)» y «Motivo
   (opcional)», hasta 500 caracteres.
2. Confirma: la persona desaparece de la tabla y del directorio.
Entra: la fecha (vacía, hoy en el día del negocio) y el motivo.
Sale: la ficha **Dada de baja**, sin Reservable, con su fecha y su motivo, y su cuenta liberada
(`staff.member.terminated`; el aviso no lleva el motivo). Es definitiva: no se edita ni se reabre.
Sus horarios dejan de contar y sus ausencias dejan de salir en las listas y en las cifras. Se puede
dar de baja a quien está Inactivo o tiene ausencias.
Si falla: «Ese miembro del personal no existe en este negocio.» si ya estaba dado de baja.
Implicados: ninguno

### STAFF-F07 Dar de alta a varios profesionales de golpe
<!-- origen: fi:modules/staff#command-handler-wasm-staff-members-bulk_create-bulk_create_staff_members old:staff/workflow/ficha.md#staff-f07 -->
Estado: hecho (asistente y API)
Actor: asistente, API
Pantalla: asistente
Pasos:
1. Quien puede dar de alta pide al asistente que dé de alta a varias personas (hasta 100 de una vez)
   con su nombre y, si quiere, email, teléfono, rol, fecha de alta, tarifa, reservable, bio y
   especialidades.
2. Se crea una ficha **Activa** por cada fila válida.
3. La respuesta dice qué fichas se crearon y qué filas se omitieron con su motivo.
Entra: las filas del lote; los roles activos del negocio.
Sale: una ficha por fila válida y un aviso `staff.member.created` por cada una (ninguno si no entra
ninguna).
Si falla: una fila con el nombre en blanco, un email que no lo es, una fecha mal escrita, una tarifa
negativa o un rol que no es del negocio se omite con su motivo (`name_required`, `invalid_email`,
`invalid_hire_date`, `negative_hourly_rate`, `role_not_found`) y las demás entran. Más de 100 filas se
rechaza entero.
Implicados: ninguno

### STAFF-F08 Ver mi propia ficha y mis ausencias
<!-- origen: old:staff/workflow/ficha.md#staff-f08 -->
Estado: hecho (servidor y pantalla)
Actor: empleado (y cualquier persona con ficha vinculada), asistente
Pantalla: Personal (vista propia) y Ausencias
Pasos:
1. Una persona con su cuenta vinculada a su ficha (STAFF-F03) abre lo suyo.
2. Ve su ficha con **su propia** tarifa y comisión (sin las notas de RRHH), y sus ausencias con su
   motivo y sus notas.
Entra: la cuenta con la que entra (no se puede falsear).
Sale: nada cambia. Sin ficha vinculada, la respuesta viene vacía.
Si falla: sin ficha o sin ausencias, vacío.
Implicados: ninguno

### STAFF-F09 Dar el equipo a otras apps
<!-- origen: wf:whatsapp-cita#rec_wa_cita-f04 old-hub:HUB_SHELL-F72 fi:modules/staff#event-emit-staff-member-created-updated-deactivated-terminated-staff-role-created-staff-time_off-created-status_changed-staff-schedule-created-staff-settings-updated old:staff/workflow/ficha.md#staff-f09 -->
Estado: hecho (sin pantalla)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una app que necesita nombrar al equipo (el TPV en «Atiende», la cocina, Citas) pide el
   directorio, con su permiso de ver el equipo.
2. Recibe, por persona: nombre, email, teléfono, nº de empleado, rol, cuenta, estado, reservable,
   fecha de alta y color; **nunca** la tarifa ni la comisión. Hasta 100 por página; se filtra, entre
   otros, por usuario (para pasar de una cuenta a su ficha).
Entra: nada; es una lectura.
Sale: el directorio de fichas que no están dadas de baja (también las Inactivas y De baja).
Si falla: cada app lo trata a su manera.
Implicados: ninguno

### STAFF-F13 Crear el horario semanal de un profesional
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f03 qa:verticals/beauty/01-services-professionals-and-schedules fi:modules/staff#command-handler-wasm-staff-schedules-create-create_schedule fi:modules/staff#query-staff-schedules-list_for_member old:staff/workflow/disponibilidad.md#staff-f13 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Horarios
Pasos:
1. Elige a la persona y pulsa **+**: se abre **Nuevo** con una semana propuesta (lunes a viernes de
   09:00 a 18:00).
2. Pon el nombre (vacío, «Horario habitual»), la vigencia si solo vale en unas fechas, «Por defecto»
   si es el habitual y, día a día, Inicio, Fin y, si hay pausa, Inicio y Fin de descanso.
3. Pulsa **Crear horario**.
Entra: la persona (por id o por nombre) y la semana. Un día es un tramo con un descanso opcional.
Sale: el horario (`staff.schedule.created`). Si es «Por defecto», los demás de esa persona dejan de
serlo. **Qué horario manda un día**: de los activos y vigentes ese día gana el que **no** es «Por
defecto»; entre varios, el de «Vigente desde» más reciente y luego el más nuevo; si ninguno vale,
ese día no tiene horario y Citas no restringe por horario.
Si falla: debajo de cada campo: «Un horario necesita al menos un día de trabajo con horas.», «La
hora de inicio tiene que ser anterior a la de fin.», «El descanso necesita inicio y fin (o ninguno).»,
«El descanso debe caer dentro del intervalo de trabajo.», «Cada día de la semana solo puede aparecer
una vez.», «La vigencia del horario termina antes de empezar.»; «Ese miembro del personal no existe
en este negocio.». Un turno que cruza la medianoche no se admite.
Implicados: ninguno

### STAFF-F14 Editar un horario
<!-- origen: old:staff/workflow/disponibilidad.md#staff-f14 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Horarios
Pasos:
1. Pulsa la fila del horario: se abre **Editar · {nombre}** con su semana.
2. Cambia el nombre, la vigencia, «Por defecto» o los días; un día que desmarcas queda «No
   trabaja». Guarda: **se sustituye la semana entera**; lo demás que no envíes se queda como estaba y
   una fecha vacía quita esa vigencia.
Entra: el horario y su semana completa.
Sale: el horario cambiado (`staff.schedule.updated`), con la misma regla de «Por defecto» y de qué
horario manda que al crearlo.
Si falla: los mismos rechazos que al crear, o «Ese horario no existe en este negocio.».
Implicados: ninguno

### STAFF-F15 Activar, desactivar o eliminar un horario
<!-- origen: old:staff/workflow/disponibilidad.md#staff-f15 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Horarios
Pasos:
1. **Activar / desactivar** cambia al momento: un horario inactivo no manda ningún día.
2. **Eliminar** pide confirmar «¿Eliminar el horario «{nombre}»? Sus horas dejan de contar para la
   disponibilidad.» y lo borra con sus horas.
Entra: el horario.
Sale: `staff.schedule.updated` o `staff.schedule.deleted`. Eliminar el «Por defecto» no hace «Por
defecto» a otro.
Si falla: «Ese horario no existe en este negocio.».
Implicados: ninguno

### STAFF-F16 Saber cuándo puede trabajar un profesional
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f06 wf:whatsapp-cita#rec_wa_cita-f04 old:staff/workflow/disponibilidad.md#staff-f16 -->
Estado: hecho (sin pantalla)
Actor: sistema (Citas), asistente
Pantalla: ninguna
Pasos:
1. Quien reserva pregunta por una persona (por id o por nombre) y un rango de días (hasta 731; un
   solo día vale).
2. Personal elige, para cada día, el horario que manda (STAFF-F13) y lo parte por el descanso.
3. Contesta, por día: qué horario manda (ninguno = «sin horario»), sus tramos, las ausencias
   **aprobadas** que lo cubren (de día entero o con sus horas, sin el tipo ni el motivo) y lo que
   queda libre: los tramos menos esas ausencias.
Entra: la persona y las fechas, en días del negocio.
Sale: solo lectura. Una ausencia pendiente, rechazada o cancelada no cuenta.
Si falla: «Ese miembro del personal no existe en este negocio.» (también si se dio de baja); un rango
al revés o de más de 731 días se rechaza en el campo.
Implicados: ninguno

### STAFF-F17 Registrar una ausencia
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f03 fi:modules/staff#command-handler-wasm-staff-time_off-create-create_time_off fi:modules/staff#query-staff-time_off-list old:staff/workflow/ausencias.md#staff-f17 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Ausencias
Pasos:
1. En **Ausencias**, pulsa **+**, elige el Miembro, el Tipo (viene Vacaciones), Desde y Hasta,
   «Día completo» (o sus horas) y, si quieres, el Motivo.
2. Pulsa Guardar: la ausencia sale como **Pendiente**.
Entra: la persona (cualquier ficha no dada de baja, también una Inactiva; por id o por nombre) y la
ausencia, con motivo y notas opcionales. Con horas, valen las mismas cada día del rango.
Sale: la ausencia Pendiente (`staff.time_off.created`; el aviso no lleva el motivo). Todavía no
cambia la agenda: solo cuenta al aprobarla (STAFF-F18). No avisa a la persona.
Si falla: debajo de cada campo: «La fecha de fin no puede ser anterior a la de inicio.», «Una
ausencia de medio día necesita hora de inicio y de fin.», «La hora de inicio tiene que ser anterior a
la de fin.»; «Ese miembro ya tiene una ausencia pendiente o aprobada en esas fechas.»
(`staff.overlapping_time_off`): se solapan si comparten algún día y, cuando las dos son de horas,
también alguna hora (una de mañana y otra de tarde del mismo día **no** chocan); las rechazadas y
canceladas no cuentan. «Ese miembro del personal no existe en este negocio.».
Implicados: ninguno

### STAFF-F18 Aprobar o rechazar una ausencia
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f03 fi:modules/staff#command-staff-time_off-set_status old:staff/workflow/ausencias.md#staff-f18 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Ausencias
Pasos:
1. Localiza la ausencia **Pendiente** (el filtro de Estado ayuda).
2. Pulsa **Aprobar** o **Rechazar**: la fila pasa a **Aprobada** o **Rechazada**.
Entra: la ausencia y las otras aprobadas de la misma persona.
Sale: el estado nuevo y, al aprobar, quién aprobó y cuándo (`staff.time_off.approved` o
`staff.time_off.rejected`). **Aprobada** resta esas horas de la disponibilidad (STAFF-F16) y cuenta
en «Ausentes hoy»; Rechazada no cambia nada. No avisa a la persona ni mira sus citas.
Si falla: «Ese miembro ya tiene una ausencia aprobada en esas fechas.» (al aprobar); «Esa solicitud
de ausencia no puede pasar a ese estado desde el actual.» (`staff.invalid_transition`); «Esa
solicitud de ausencia no existe en este negocio.».
Implicados: ninguno

### STAFF-F19 Cancelar una ausencia
<!-- origen: old:staff/workflow/ausencias.md#staff-f19 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable; el empleado, solo la suya pendiente
Pantalla: Ausencias
Pasos:
1. En la fila de una ausencia **Pendiente** o **Aprobada**, pulsa **Cancelar** y confirma.
2. La fila pasa a **Cancelada**; si estaba aprobada, sus horas vuelven a estar disponibles.
Entra: la ausencia.
Sale: el estado Cancelada (`staff.time_off.cancelled`), que es final; conserva quién la aprobó.
Si falla: «Esa solicitud de ausencia no puede pasar a ese estado desde el actual.»; un empleado que
intenta cancelar una ajena o una suya que ya no está pendiente (también si se la aprueban mientras la
cancela): «Solo puedes cancelar tus propias solicitudes pendientes.».
Implicados: ninguno

### STAFF-F20 Ver quién falta hoy
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f05 qa:verticals/beauty/02-opening-and-daily-agenda fi:modules/staff#query-staff-time_off-today old:staff/workflow/ausencias.md#staff-f20 fi:modules/staff#widget-staff-time_off_today-timeline -->
Estado: hecho
Actor: todos
Pantalla: Ausencias y Personal
Pasos:
1. Abre **Ausencias**: encima de la tabla, «Ausencias de hoy» lista a quien tiene una ausencia
   **aprobada** que cubre hoy (en el día del negocio), de día entero primero y luego por nombre, con el
   tipo y, si es solo una parte del día, sus horas, y dice cuántas son.
2. En **Personal**, la cifra «Ausentes hoy» cuenta las personas distintas que faltan hoy.
3. Para el detalle, la tabla de **Ausencias** con sus filtros.
Entra: las ausencias aprobadas y las fichas.
Sale: solo lectura; sin el motivo. Cambia sola cuando se aprueba o se cancela una ausencia.
Si falla: sin ausencias, «Nadie falta hoy.»; si no se puede leer, «No se pudo cargar quién falta hoy»
en su sitio, y la tabla sigue funcionando.
Implicados: ninguno

### STAFF-F21 Dar la tarifa y la comisión de cada profesional
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f15 fi:modules/staff#query-staff-commissions-summary old:staff/workflow/pago-y-ajustes.md#staff-f21 qa:modules/staff/commission-per-professional qa:verticals/beauty/07-closing-per-professional -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Personal (columna Tarifa/h y formulario) y Comisiones
Pasos:
1. Quien puede ver la compensación ve la tarifa, la comisión y las notas de RRHH de cada ficha.
2. La **hoja de comisiones** da, por cada persona que puede cobrar comisión (Activa o De baja; no las
   Inactivas ni las dadas de baja), su ficha, su cuenta (vacía si no tiene), nombre, rol y comisión,
   también las de comisión 0.
3. Para saber lo que ha ganado cada profesional, abre **Personal → Comisiones**. Sale «Hoy»: lo que ha
   vendido cada persona en el día del negocio, con lo devuelto ya restado, su comisión y lo que le
   corresponde (vendido × comisión ÷ 100, redondeado al céntimo una sola vez por persona; medio céntimo
   sube). Arriba, el total vendido y el total de comisiones.
4. Para otro periodo, elige «Ayer», «Esta semana», «Este mes» o «Personalizado» y pon «Desde» y
   «Hasta».
5. Cuenta lo que se atribuyó a cada persona en Ventas: la línea que hizo ella o, si la línea no dice
   quién, la cuenta que atendió (en una venta de una cita, la profesional de la cita). Lo que se cobra
   sin elegir a nadie del equipo no cuenta para nadie.
Entra: la tarifa y la comisión de cada ficha y, de Ventas, lo vendido por cada profesional en el periodo
(ya resta lo devuelto: lo que vuelve, a quien lo vendió). Ventas es opcional.
Sale: solo lectura.
Si falla: sin permiso de compensación, «No tienes permiso»; sin Ventas, «Las comisiones salen de las ventas»; con «Hasta» antes que «Desde»,
«La fecha de fin no puede ser anterior a la de inicio.» bajo «Hasta»; con un solo día, «Un periodo
personalizado necesita su primer y su último día.»; con más de dos años, «Pide como mucho 731 días de
una vez.».
Implicados: SALE-F16, SALE-F28

### STAFF-F22 Cambiar los ajustes de Personal
<!-- origen: old-hub:HUB_SHELL-F43 old-hub:HUB_SHELL-F44 fi:modules/staff#command-staff-settings-update fi:modules/staff#query-staff-settings-get fi:modules/staff#settings-bloque old:staff/workflow/pago-y-ajustes.md#staff-f22 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pantalla: Ajustes de Personal
Pasos:
1. Abre **Ajustes**: salen los guardados o, si nunca se guardaron, los propuestos (jornada de 09:00 a
   18:00, descanso de 60 minutos, antelación de 1 hora, 12 horas máximas por día, umbral de 40 horas
   semanales y los cinco interruptores encendidos).
2. Cambia lo que quieras: jornada en HH:MM (un fin antes del inicio es un turno de noche),
   descanso de 0 a 480 minutos, antelación de 0 a 168 horas, de 1 a 24 horas por día, umbral de 1 a
   168 horas por semana, y los interruptores.
3. Pulsa **Guardar**.
Entra: lo enviado; lo demás se queda como estaba.
Sale: los ajustes del negocio (`staff.settings.updated`), con las horas siempre en HH:MM. Hoy ningún
comportamiento los lee (como en el producto actual).
Si falla: un valor fuera de su rango sale debajo de su campo y no se guarda nada. Si los ajustes no se
pueden leer, «No se pudieron cargar los ajustes» con «Reintentar», sin formulario: nunca se ofrecen
para guardar unos valores que no son los del negocio.
Implicados: ninguno

### STAFF-F23 Ver las cifras de la plantilla y por rol
<!-- origen: fi:modules/staff#query-staff-members-stats old:staff/workflow/pago-y-ajustes.md#staff-f23 fi:modules/staff#widget-staff-headcount-kpi fi:modules/staff#widget-staff-on_leave_today-stat fi:modules/staff#widget-staff-pending_time_off-kpi fi:modules/staff#widget-staff-by_role-bar-list -->
Estado: hecho
Actor: todos
Pantalla: Personal y Roles
Pasos:
1. Abre **Personal**: encima de la tabla salen tres cifras: «Plantilla activa» (cuántas personas
   están **Activas**), «Ausentes hoy» (personas distintas con una ausencia aprobada que cubre hoy) y
   «Ausencias pendientes» (cuántas solicitudes esperan respuesta). En el móvil van en una sola línea,
   para que la tabla se siga viendo debajo.
2. Las cifras cambian solas, sin recargar, cuando alguien da de alta, desactiva o da de baja una ficha
   o pide, aprueba, rechaza o cancela una ausencia.
3. «Miembros» de **Roles** da cuántas personas **Activas** lleva cada rol (el panel «Empleados por
   rol» del producto actual).
Entra: las fichas, los roles y las ausencias. Por el asistente o la API, las cifras dan además
cuántas fichas hay y cuántas están **De baja** e **Inactivas**.
Sale: solo lectura. Las fichas dadas de baja y sus ausencias no cuentan.
Si falla: sin datos, ceros; si no se pueden leer, «No se pudieron cargar las cifras» en su sitio, y la
tabla sigue funcionando. Mientras llegan, cada cifra enseña «…».
Implicados: ninguno

### STAFF-F24 Pedir mi propia ausencia
<!-- origen: gh:staff#3 -->
Estado: hecho (servidor y pantalla)
Actor: empleado (y cualquier persona con ficha vinculada), asistente
Pantalla: Ausencias
Pasos:
1. En **Ausencias**, pulsa **+**: el formulario no pide Miembro, la ausencia es tuya.
2. Elige el Tipo, las fechas, «Día completo» (o sus horas) y, si quieres, el Motivo, y guarda.
3. Sale como **Pendiente** hasta que un responsable la apruebe o la rechace (STAFF-F18); mientras
   esté pendiente puedes retirarla (STAFF-F19).
Entra: tu ficha, por tu cuenta vinculada (STAFF-F03).
Sale: la ausencia Pendiente, con el mismo aviso que STAFF-F17 (`staff.time_off.created`).
Si falla: los mismos rechazos que STAFF-F17; sin ficha vinculada: «Tu usuario no está vinculado a
ningún miembro del personal: pide a un responsable que lo vincule.» (`staff.no_member_record`).
Implicados: ninguno

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y los mismos permisos. Una persona se nombra por su id o por
su nombre; si el nombre vale para varias, se dice cuáles y se pide que elija
(`staff.ambiguous_member`).

### Lo que ofrece: consultas (leen, no cambian nada; todas menos las cuentas se pueden seguir en vivo)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| El directorio, con búsqueda, filtros y orden por cualquier columna, en páginas (hasta 100) | ver | F09 | `staff.member.list` |
| La ficha de una persona (sin compensación) | ver | F02 | `staff.member.detail` |
| Mi ficha, con mi tarifa y mi comisión | ver | F08 | `staff.member.mine` |
| Tarifa, comisión y notas de RRHH, con los filtros, el orden y las páginas del directorio (la columna Tarifa/h lee las mismas filas) | ver la compensación | F21 | `staff.member.compensation` |
| La hoja de comisiones: quien puede cobrar comisión, con su ficha, su cuenta y su comisión | ver la compensación | F21 | `staff.commission.summary` |
| Lo que ha ganado cada profesional en un periodo (hoy, ayer, esta semana, este mes o dos días): vendido con lo devuelto restado, comisión y totales; dice si el negocio no tiene Ventas | ver la compensación (y las cifras de Ventas) | F21 | `staff.commission.report` |
| Las cifras: fichas, activos, de baja, inactivos, ausentes hoy y solicitudes pendientes | ver | F23 | `staff.member.stats` |
| Los roles con sus miembros activos, con filtros y orden | ver | F04, F23 | `staff.role.list` |
| Los horarios de una persona con su semana | ver | F13–F15 | `staff.schedule.list` |
| Un horario con su semana | ver | F14 | `staff.schedule.detail` |
| La disponibilidad de una persona por días | ver | F16 | `staff.availability.for_member` |
| Las ausencias, sin motivo, con filtros y orden | ver ausencias | F17–F19 | `staff.time_off.list` |
| Una ausencia con su motivo, sus notas y quién la aprobó | ver el detalle de ausencias | F18 | `staff.time_off.detail` |
| Quién falta hoy | ver ausencias | F20 | `staff.time_off.today` |
| Mis ausencias, con su motivo y sus notas | ver ausencias | F08 | `staff.time_off.mine` |
| Los ajustes | ver | F22 | `staff.settings.get` |
| Las cuentas activas con acceso al negocio, para «Usuario del Hub» (id y nombre, con búsqueda o por usuario: la cuenta de una ficha que ya no tiene acceso no sale y la pantalla dice «Sin acceso a este negocio») | dar de alta o editar | F03 | `staff.account.list` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Da de alta una ficha | dar de alta | F01, F03 | `staff.member.create` |
| Da de alta hasta 100 fichas de golpe | dar de alta | F07 | `staff.member.bulk_create` |
| Cambia una ficha (solo lo enviado) | editar | F02, F03 | `staff.member.update` |
| Desactiva una ficha | desactivar y dar de baja | F05 | `staff.member.deactivate` |
| Da de baja una ficha, con fecha y motivo | desactivar y dar de baja | F06 | `staff.member.terminate` |
| Crea un rol | ajustes | F04 | `staff.role.create` |
| Cambia o retira un rol | ajustes | F04 | `staff.role.update` |
| Crea un horario con su semana | ajustes | F13 | `staff.schedule.create` |
| Cambia un horario y sustituye su semana | ajustes | F14 | `staff.schedule.update` |
| Activa o desactiva un horario | ajustes | F15 | `staff.schedule.set_active` |
| Elimina un horario | ajustes | F15 | `staff.schedule.delete` |
| Registra una ausencia de cualquiera | gestionar ausencias | F17 | `staff.time_off.create` |
| Pide una ausencia propia | pedir ausencias | F24 | `staff.time_off.request` |
| Aprueba una ausencia | gestionar ausencias | F18 | `staff.time_off.approve` |
| Rechaza una ausencia | gestionar ausencias | F18 | `staff.time_off.reject` |
| Cancela una ausencia (la propia pendiente, o cualquiera con gestionar ausencias) | pedir ausencias | F19 | `staff.time_off.cancel` |
| Guarda los ajustes (solo lo enviado) | ajustes | F22 | `staff.settings.update` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Ficha nueva | Alta (una por ficha en el alta de golpe) | Cuál (`id`) | `staff.member.created` |
| Ficha cambiada | Edición con algún cambio | Cuál (`id`) | `staff.member.updated` |
| Ficha desactivada | Desactivar | Cuál (`id`) | `staff.member.deactivated` |
| Ficha dada de baja | Dar de baja | Cuál (`id`), sin el motivo | `staff.member.terminated` |
| Rol nuevo | Crear un rol | Cuál (`id`) | `staff.role.created` |
| Rol cambiado | Editar o retirar un rol con algún cambio | Cuál (`id`) | `staff.role.updated` |
| Horario nuevo | Crear un horario | El horario (`id`) y la persona (`member_id`) | `staff.schedule.created` |
| Horario cambiado | Editarlo, o activarlo o desactivarlo con cambio | El horario y la persona | `staff.schedule.updated` |
| Horario eliminado | Eliminarlo | El horario y la persona | `staff.schedule.deleted` |
| Ausencia nueva | Registrarla o pedirla | La ausencia (`id`) y la persona (`member_id`), sin el motivo | `staff.time_off.created` |
| Ausencia aprobada | Aprobar | La ausencia y la persona | `staff.time_off.approved` |
| Ausencia rechazada | Rechazar | La ausencia y la persona | `staff.time_off.rejected` |
| Ausencia cancelada | Cancelar | La ausencia y la persona | `staff.time_off.cancelled` |
| Ajustes cambiados | Guardar con algún cambio (o el primer guardado) | Nada | `staff.settings.updated` |

### A qué reacciona y lo que necesita de otras apps
No reacciona a ningún aviso y no requiere ninguna app. Para **Comisiones** pide a **Ventas**, si el
negocio la tiene, lo vendido por cada profesional en el periodo, con lo devuelto ya restado
(`sale.sale.by_staff`, con el permiso de cifras de Ventas de quien mira), y se pone al día con sus avisos
de venta cobrada, anulada o devuelta (`sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded`).
Sin Ventas, Comisiones lo dice y no lista a nadie. De la plataforma usa las cuentas del negocio (para
vincular una ficha) y la zona horaria del negocio (para el «hoy»).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver el equipo, roles, horarios, disponibilidad, cifras y ajustes | sí | sí | sí | sí | `staff.view` |
| Ver tarifa, comisión y notas de RRHH | sí | sí | sí | no | `staff.view_compensation` |
| Dar de alta fichas | sí | sí | sí | no | `staff.add_member` |
| Editar fichas | sí | sí | sí | no | `staff.change_member` |
| Desactivar y dar de baja | sí | sí | no | no | `staff.delete_member` |
| Ver ausencias (sin motivo) | sí | sí | sí | sí | `staff.view_time_off` |
| Ver el motivo y las notas de cualquier ausencia | sí | sí | sí | no | `staff.view_time_off_detail` |
| Registrar ausencias de cualquiera, aprobarlas, rechazarlas y cancelarlas | sí | sí | sí | no | `staff.manage_time_off` |
| Roles, horarios y ajustes | sí | sí | sí | no | `staff.manage_settings` |
| Pedir ausencias propias y retirar las propias pendientes | sí | sí | sí | sí | `staff.request_time_off` |

El cajero del producto actual ya no existe como papel: lo que veía (el directorio) lo ve el empleado.

## Para quien lo mantiene

- Anatomía completa de una app (copia de `apps/demo`): `apps.py`, `models.py`, `schemas.py`,
  `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/` y un
  `tests/test_<fichero>.py` por fichero. Las páginas (`frontend/`) llegan en la fase siguiente;
  `UI-REQUESTS.md` lista lo que se pide a `@erplora/ui`.
- Modelos: `Role` (el rol de catálogo), `Member` (la ficha), `Schedule` y `ScheduleDay` (el horario y
  sus días, lunes = 0; un día que no está es libre), `TimeOff` (la ausencia) y `StaffSettings` (una
  sola fila, restricción `staff_settings_singleton`). UUIDv7, sin `hub_id`.
- La ficha cuelga del usuario de la plataforma con una FK a `settings.AUTH_USER_MODEL`
  (`SET_NULL`), como `base.Membership`; «con acceso a este negocio» es tener `Membership` en el
  ámbito (fase 1). La fase 2 (usuarios del hub en su BD) cambia esa FK y esa comprobación junto con
  `Membership`. Igual `TimeOff.approved_by`.
- **Una cuenta, una ficha viva**: restricción parcial `staff_member_user_unique` (sin las dadas de
  baja); el servicio lo comprueba antes para nombrar a quien la tiene y traduce la violación de la
  restricción (dos guardados a la vez) al mismo 409.
- **Un solo «Por defecto» por persona**: restricción parcial `staff_schedule_one_default`; el
  servicio desmarca los demás en la misma transacción.
- Dar de baja = estado `terminated`, que funciona como borrado lógico: ninguna consulta devuelve una
  ficha dada de baja, ni sus horarios ni sus ausencias.
- Las escrituras sobre una persona bloquean primero su fila (`select_for_update`): dos ausencias
  pedidas a la vez, dos aprobaciones que se solapan o una cancelación contra una aprobación esperan a la
  primera y deciden sobre lo que dejó. Aprobar, rechazar, cancelar y tocar un horario bloquean la ficha
  y luego la fila; una ficha dada de baja mientras tanto da «no existe». Hay tests con hilos de cada
  carrera.
- El «hoy» es `timezone.localdate()` (zona del negocio; en la fase 1, `TIME_ZONE`).
- Dinero en céntimos enteros (`hourly_rate`); la comisión es `Decimal(5, 2)` de 0 a 100. El importe
  de la comisión (`staff.commission.report`) es `vendido × comisión ÷ 100` en `Decimal`, redondeado a
  céntimos enteros con `ROUND_HALF_UP` una sola vez por persona, sobre lo que Ventas le atribuye
  (`total_revenue`, que ya resta lo devuelto). Una venta nombra a su profesional por el id de su ficha
  (UUID); la cuenta (`user_id`, un entero) nunca llega a una venta, así que no hay dos identidades que
  sumar.
- Los avisos solo llevan identificadores: nunca el motivo de una baja ni de una ausencia (datos
  personales, y la baja por enfermedad es un dato de salud).
- Asistente: toda operación declara `ai={"description", "risk"}` (`risk` solo en las acciones; `high`
  en editar una ficha, que puede cambiar la compensación, desactivar, dar de baja y eliminar un
  horario) y todo campo de entrada lleva `description`; las mismas descripciones salen en el OpenAPI.
- El admin de Django del Hub tiene **CRUD completo** sobre todos los modelos (ronda 12, PLAN §17),
  para el staff de la plataforma; una escritura cruda del admin no deja aviso.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo.
- La resta de intervalos de la disponibilidad está hecha a mano: la única librería de intervalos de
  tamaño razonable (`portion`) es un proyecto de una sola persona, y las que cumplen los criterios
  (`sympy`, `pandas`) son desproporcionadas para eso.

## Lo que queda fuera (páginas)

- **Alta en lote (STAFF-F07)**: es del asistente y de la API, como en el producto actual; no tiene
  pantalla. Importar el equipo desde un fichero CSV (staff de services#152 del producto actual) no
  existía y no se porta: el alta a mano o por el asistente cubre a un equipo de peluquería o de sala.
- **Los paneles en el Inicio**: cuando el Hub tenga un Inicio con paneles, las cifras y «Ausencias de
  hoy» podrán salir también allí; hoy salen dentro de Personal.
- **Fechas y horas en el orden del idioma del negocio** (staff#86, staff#87 del producto actual): los
  campos usan `ion-input type="date|time"` hasta que `@erplora/ui` tenga el suyo (`UI-REQUESTS.md`).

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/staff/members`, `/staff/roles`, `/staff/time-off`, `/staff/schedules`,
  `/staff/commissions` y `/staff/settings`; la barra de pestañas (`frontend/tabs.ts`) añade «Comisiones»
  solo a quien ve la compensación (`staff.view_compensation`) y «Ajustes» solo a quien puede guardarlos
  (`staff.manage_settings`), como la pestaña que generaba la shell vieja. El menú de `apps.py` no las
  lleva: una entrada de menú no puede depender de un permiso (`live.meta.Nav`).
- Comisiones (`frontend/pages/CommissionsPage.vue`) sigue `staff.commission.report`: el periodo lo
  resuelve el servidor en días del negocio, y «Personalizado» envía `date_from` y `date_to`. Su 422 sale
  bajo «Hasta». Solo se suscribe quien ve la compensación. La consulta pide `sale.sale.by_staff` por su
  nombre (`live.operations.get`): Ventas ausente o apagada da `sales_available: false`.
- Listas en vivo con `useLiveList` (ventanas de 100 filas como suscripciones aparte: el servidor no da
  más de 100) y `useServerTable` (orden `columna`/`-columna`); escrituras con `useCommand`.
- Un horario nuevo solo nace «Por defecto» si la persona no tiene ya uno: un segundo (el de verano)
  no le quita la marca al habitual sin que nadie lo pida.
- Ajustes envía solo los campos que la persona tocó y cambió; lo que otra persona guarde mientras
  tanto entra en los demás campos sin pisar lo tecleado.
- «Mi ficha» (STAFF-F08) es un botón de la barra de Personal para quien tiene ficha vinculada; «Mis
  ausencias» es el selector «Todas / Mis ausencias» de Ausencias (con el motivo).
- Los selectores de listas largas (miembro, rol, usuario del Hub) buscan en el servidor
  (`frontend/components/SearchSelect.vue`).
- Las cifras de Personal (`frontend/components/StaffFigures.vue`, `staff.member.stats`) y «Ausencias de
  hoy» (`frontend/components/AwayToday.vue`, `staff.time_off.today`) son los paneles del Inicio viejo
  (STAFF-G01…G05) dentro de la app, como las cifras de Clientes y «Fichados ahora» de Control horario;
  sus tarjetas rehacen el `ok-kpi` hasta que `@erplora/ui` tenga una (`UI-REQUESTS.md`).
- El formulario de la ficha retira la lectura de una apertura anterior: cerrarlo mientras carga no
  deja el siguiente en «Cargando…».

## Lo que NO hace, a propósito

- **No es el acceso**: no crea cuentas, no da permisos, no guarda PIN.
- **No ficha** (entradas, salidas, horas trabajadas, horas extra) ni calcula nóminas: Comisiones da lo
  ganado en un periodo, pero ni lo paga ni lo guarda.
- **No reserva** ni mira las citas: al desactivar, dar de baja o aprobar una ausencia, las citas ya
  reservadas siguen en la agenda (la agenda es de Citas).
- **No guarda el horario del negocio** (abrir, cerrar, festivos: es de Horarios).
- **No guarda saldos** de vacaciones ni días acumulados.
- **No avisa de duplicados** de nombre, email o nº de empleado.
- **No borra ni anonimiza** una ficha: la baja la conserva.

## Cambios frente al producto actual

- **Servicios que hace cada profesional** (STAFF-F10, F11 y F12: asignar, cambiar, quitar, servicio
  principal, duración y precio propios, y «quién puede hacer un servicio»): **no están en esta app**.
  Guardan el id de un servicio, y una app solo referencia las de su `requires`; `service` no existe
  todavía. En el mercado (Fresha, Square Appointments, Vagaro, Mangomint, Odoo Appointments) se
  asignan en el servicio: irán a la app Servicios (con `requires = ["staff"]`) o a Citas cuando se
  porten, con sus mismas reglas. Contradice «conservar toda la funcionalidad» mientras tanto; está
  señalado para decidirlo.
- **Las tres lecturas de disponibilidad por instante** (`day_at`, `days_ahead`, `team_day_at`)
  existían porque un comando viejo solo podía leer con parámetros literales; ahora Citas llama a
  `staff.availability.for_member` con el día que calcula ella, y la respuesta es la misma.
- **Aprobar, rechazar y cancelar** son tres acciones con su propio aviso (`staff.time_off.approved`,
  `…rejected`, `…cancelled`) en lugar de `staff.time_off.set_status` y `staff.time_off.status_changed`.
  **Cancelar** tiene botón (antes solo el asistente).
- **El empleado pide su ausencia** (STAFF-F24, nuevo) y retira la suya pendiente; antes solo la
  registraba el responsable.
- **Dos ausencias de horas** el mismo día ya no chocan si sus horas no se pisan.
- **Roles**: se editan, se ordenan y se retiran (antes solo se creaban) y no se repite un nombre. La
  lista da también los retirados (con su marca), para poder reactivarlos.
- **Inactivo desde la edición** mira ahora las ausencias vivas, como Desactivar.
- **La fecha de alta** se puede borrar al editar, y el **margen entre citas** se guarda también al dar
  de alta.
- **Alta en lote**: una fila con nombre en blanco, email o fecha mal escritos o tarifa negativa se
  omite con su motivo en vez de tumbar el lote; más de 100 filas se rechaza en vez de perder las
  sobrantes; no avisa de una ficha nueva si no entra ninguna.
- **Notas de RRHH**: se ven con la compensación (antes se escribían y nadie las leía).
- **Ajustes**: las horas salen siempre en HH:MM; se guarda solo lo enviado.
- **Foto** de la ficha y **orden** de la ficha: no se portan; ninguna pantalla ni comando los escribía.
- Las cifras ya no cuentan las ausencias pendientes de una ficha dada de baja.
- **Los paneles del Inicio** (Plantilla activa, Ausentes hoy, Ausencias pendientes, Ausencias de hoy y
  Empleados por rol) salen dentro de Personal mientras el Hub no tenga un Inicio con paneles.
- **Comisiones** (nuevo): el producto actual no tenía pantalla que cruzara lo vendido con la comisión
  (STAFF-F21 «parcial»); el cierre por profesional lo componía cada uno. Ahora Personal da lo ganado por
  cada profesional en un periodo, con lo devuelto restado a quien lo vendió, como el informe de comisiones
  de Fresha, Phorest o Zenoti; no va en el cierre de caja (ningún TPV del mercado la pone en el informe Z).
  Ya no hay dos identidades de una persona que sumar: una venta siempre nombra la ficha.
- Las listas paginan con hasta 100 por página.
