# Workbook — Control horario (app)
Prefijo: ATTENDANCE
Alcance MVP: transversal (lo necesitan la peluquería y el restaurante: todo negocio con empleados)
Estado de la app: hecha (servidor y páginas); el panel de Inicio y el modo del dispositivo esperan a la
plataforma (ver «Lo que queda fuera»)

> Manual de usuario y especificación de la app `attendance`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Control horario del producto actual
> (`modules-workspace/modules/attendance`, `origin/main` `944a7b1`). Hace lo mismo, se ve igual y
> conserva toda su funcionalidad salvo lo que dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Es el **registro de jornada** del negocio. Cada persona del equipo ficha la entrada al llegar y la
salida al irse, con sus pausas en medio, con un toque y sin elegir nada: quien ficha es la persona de
la sesión, por la ficha de Personal vinculada a su cuenta. El responsable ve las jornadas de todo el
equipo, corrige las que están mal (siempre con un motivo, que queda en el historial) y saca el mes en
CSV para la gestoría o la Inspección de Trabajo.

En España todo negocio con empleados tiene que registrar el inicio y el fin de cada jornada,
guardarlo cuatro años y tenerlo a disposición del trabajador, de sus representantes y de la
Inspección (art. 34.9 del Estatuto de los Trabajadores, Real Decreto-ley 8/2019). Por eso:

- **Ninguna jornada se borra**, y una jornada solo cambia con una **corrección con motivo**, que deja
  una fila nueva en su historial que tampoco se borra ni se edita.
- **El trabajador ve sus propias jornadas** y quién las corrigió, cuándo y por qué.

Quién la usa:

- El **empleado** ficha la entrada, la salida y sus pausas, ve sus jornadas, su historial de
  correcciones y los ajustes (sin poder cambiarlos), y exporta sus jornadas en CSV.
- El **responsable**, el **administrador** y el **propietario** además ven las jornadas de todo el
  equipo y quién está dentro ahora, corrigen jornadas con motivo, fichan la entrada o la salida de
  otra persona (por el asistente o la API: «ficha la salida de Ana») y cambian los ajustes.

## Referencia adoptada

- **Odoo Asistencias, Square Team, Toast y Lightspeed**: una jornada es una entrada y una salida de una
  persona, con pausas dentro; una sola jornada abierta por persona.
- **Toast y Square**: el encargado edita una jornada con rastro (antes, después, quién y por qué).
- **Square, Factorial y Homebase**: el radio del lugar de trabajo se exige solo a los dispositivos
  personales; el TPV del mostrador nunca pide la ubicación, y la salida nunca se bloquea.
- **Homebase y Deputy**: el encargado puede fichar la entrada o la salida de alguien de su equipo, y
  queda quién lo hizo.
- El fichaje no calcula nóminas ni horas extra: eso, en el mercado, es otro producto.

## Antes de empezar

1. La app **Personal** encendida: el fichaje es de una **ficha de Personal** (Control horario la
   necesita y la enciende con ella).
2. Cada persona que vaya a fichar tiene su ficha en **Personal** **vinculada a su cuenta** («Usuario
   del Hub», STAFF-F03). Una cuenta sin ficha vinculada ve «Tu usuario no está vinculado a ninguna
   ficha de Personal» y no puede fichar.
3. Si se quiere exigir que el móvil esté en el local, un responsable lo activa en **Ajustes** y fija
   la ubicación del local (ATTENDANCE-F04). Por defecto no se pide ninguna ubicación.

## Pantallas

### Fichar
Se llega desde el menú de la app, «Fichar». Arriba, «Hola, <nombre>» y «Son las <hora>»; en el centro,
el estado («No has fichado la entrada», «Dentro desde las 09:00», «En pausa desde las 13:00»), el
tiempo que lleva desde la entrada, que corre solo, y el botón grande del momento: «Fichar entrada», o
«Empezar pausa» / «Terminar pausa» y «Fichar salida». A la derecha (debajo en el móvil), «Hoy»
(Trabajado y Pausas, que corren solos) y «Últimas jornadas» (las diez últimas, con su estado: «En
curso», «Cerrada», «Por revisar»). La puede abrir cualquier persona del equipo.

### Registros
Se llega desde el menú de la app, «Registros». Una tabla de las jornadas del mes elegido: Fecha,
Persona, Entrada, Salida, Pausas (min), Trabajado, Estado y Ubicación, con las acciones «Corregir» e
«Historial» en cada fila; en el móvil, tarjetas. Un empleado ve solo las suyas (sin columna Persona,
con «Historial»); el responsable ve las de todo el equipo con los filtros «Persona» (con buscador),
«Mes» y «Estado», y encima de la tabla «Fichados ahora»: cuántas personas tienen la jornada abierta y
quiénes, desde qué hora y si están en pausa. Arriba, «Exportar CSV».

### Ajustes
La pestaña «Ajustes» de la app. «Pedir la ubicación al fichar desde un dispositivo personal», «Radio
permitido», «Ubicación del lugar de trabajo» (Latitud, Longitud y «Usar mi ubicación actual») y
«Marcar a revisar tras (horas)». Solo un responsable o un administrador puede guardar; los demás la ven
en solo lectura con «Solo un responsable o un administrador puede cambiar estos ajustes.».

## Estados de cada pantalla

| Pantalla | Cargando | Vacía | Error |
|---|---|---|---|
| Fichar | «Cargando…» | «Todavía no hay jornadas» en Últimas jornadas; sin ficha vinculada, «Tu usuario no está vinculado a ninguna ficha de Personal» | «No se ha podido cargar el control horario…» y «Reintentar» |
| Registros | «Cargando jornadas…» | «No hay jornadas en este mes» (o «Nada coincide con los filtros») | «No se han podido cargar las jornadas.» y «Reintentar» |
| Historial | «Cargando historial…» | «Esta jornada no se ha corregido nunca.» | «No se ha podido cargar el historial.» |
| Ajustes | indicador de carga | — | el aviso y «Reintentar» |

En las tres páginas: «Reconectando…» mientras el directo se recupera (lo pintado se queda), «Esta app
no está activa en este negocio» si se apaga y «No tienes permiso» si el papel no llega.

## Flujos

| Flujo | Qué | Vertical | Estado |
|---|---|---|---|
| ATTENDANCE-F01 | Fichar la entrada al llegar y la salida al irse | común | hecho |
| ATTENDANCE-F02 | Hacer una pausa sin salir de la jornada | común | hecho |
| ATTENDANCE-F03 | Fichar desde el móvil cuando el negocio pide la ubicación | común | parcial: el modo del dispositivo es de la plataforma (fase 2) |
| ATTENDANCE-F04 | Ajustar la ubicación del local y cuándo se revisa una jornada olvidada | común | hecho |
| ATTENDANCE-F05 | Marcar para revisar una jornada que nadie cerró | común | hecho |
| ATTENDANCE-F06 | Ver mis jornadas del mes y quién las corrigió | común | hecho |
| ATTENDANCE-F07 | Ver las jornadas de todo el equipo | común | hecho |
| ATTENDANCE-F08 | Corregir una jornada mal fichada, con su motivo | común | hecho |
| ATTENDANCE-F09 | Ver quién cambió una jornada, cuándo y por qué | común | hecho |
| ATTENDANCE-F10 | Sacar el mes en CSV para la gestoría o la Inspección | común | hecho |
| ATTENDANCE-F11 | Ver quién está fichado ahora | común | hecho (en Registros; el panel de Inicio espera al Hub) |
| ATTENDANCE-F12 | Fichar la entrada o la salida de otra persona | común | hecho (asistente y API) |
| ATTENDANCE-F13 | Cerrar la jornada abierta de quien se da de baja | común | hecho |

### ATTENDANCE-F01 Fichar la entrada al llegar y la salida al irse
Actor: propietario, administrador, responsable, empleado
Pantalla: Fichar
Pasos:
1. Abre Control horario → «Fichar». Ve «No has fichado la entrada» y el botón «Fichar entrada».
2. Pulsa «Fichar entrada». Ve «Entrada fichada a las 09:00.», «Dentro desde las 09:00» y el tiempo que
   lleva desde la entrada, que corre solo.
3. Al acabar, pulsa «Fichar salida». Ve «Salida fichada a las 17:00.» y vuelve el botón «Fichar
   entrada».
4. En «Hoy» sale el tiempo trabajado y en «Últimas jornadas» la jornada, «Cerrada».
5. Una jornada que cruza la medianoche (de 22:00 a 06:00) es una sola y cuenta entera en el día en que
   empezó (el día del negocio, no el del dispositivo).
Entra: la persona de la sesión y su ficha de Personal.
Sale: la jornada guardada con la hora del servidor, abierta al entrar y cerrada al salir; los avisos
de entrada y de salida; «Fichados ahora» sube y baja.
Si falla: fichar la entrada con una jornada ya abierta se rechaza con «Ya tienes una jornada abierta:
ficha la salida antes de volver a entrar.» y la pantalla enseña la jornada abierta (dos toques a la
vez dejan una sola jornada); sin ficha vinculada, «Tu usuario no está vinculado a ninguna ficha de
Personal: pide a un responsable que la vincule en Personal.»; con la ficha inactiva o de baja temporal,
«Esa ficha de Personal no está activa (inactiva o de baja temporal): no puede fichar la entrada.» (la
salida sí se ficha); sin conexión, el error y «Reintentar».

### ATTENDANCE-F02 Hacer una pausa sin salir de la jornada
Actor: propietario, administrador, responsable, empleado
Pantalla: Fichar
Pasos:
1. Con la jornada abierta, pulsa «Empezar pausa». Ve «Pausa iniciada a las 13:00.» y «En pausa desde
   las 13:00»; el botón pasa a «Terminar pausa».
2. A la vuelta, pulsa «Terminar pausa». Ve «Pausa terminada a las 13:30.».
3. Puede hacer tantas pausas como quiera, una detrás de otra.
4. Si pulsa «Fichar salida» en plena pausa, la pausa se termina en ese mismo momento.
5. En «Hoy», «Pausas» suma el tiempo de pausa y «Trabajado» ya lo descuenta.
Entra: la jornada abierta de la persona (ATTENDANCE-F01).
Sale: cada pausa guardada dentro de su jornada; los avisos de pausa empezada y terminada.
Si falla: sin jornada abierta, «No hay ninguna jornada abierta: ficha la entrada primero.»; con una
pausa ya en curso, «Ya hay una pausa en curso.»; terminar una pausa que no existe, «No hay ninguna
pausa en curso que terminar.»; en una jornada olvidada (ATTENDANCE-F05), «Esta jornada lleva abierta más
de 12 horas y está por revisar…».

### ATTENDANCE-F03 Fichar desde el móvil cuando el negocio pide la ubicación
Estado: parcial — saber si un dispositivo es el TPV compartido o el móvil de alguien es de la
plataforma, que lo traerá con el PIN y el dispositivo de confianza (fase 2), y nunca lo dice la petición
(ni la pantalla, ni el asistente, ni la API). Hasta entonces todo dispositivo ficha como el compartido,
no se pide ninguna ubicación y Ajustes deja «Pedir la ubicación…» desactivado diciendo por qué. Lo que
sigue está hecho y probado en el servidor y en la pantalla, a la espera de ese dato.
Actor: propietario, administrador, responsable, empleado
Pantalla: Fichar
Pasos:
1. El negocio tiene activado «Pedir la ubicación al fichar desde un dispositivo personal»
   (ATTENDANCE-F04) y la persona usa su propio móvil o portátil.
2. Pulsa «Fichar entrada». Ve «Obteniendo tu ubicación…»; la primera vez el móvil pide permiso.
3. Dentro del radio, ficha como siempre y la jornada guarda la posición, la precisión y la distancia
   al local, que **calcula el Hub** (no se fía de la que diga el dispositivo).
4. Fuera del radio no ficha y lo dice: «Estás a 850 m del lugar de trabajo, fuera de los 100 m
   permitidos. Acércate para fichar o ficha en el mostrador.».
5. La salida nunca se bloquea: se guarda la posición si se puede y, si no, se ficha igual.
6. En el TPV del mostrador nunca se pide la ubicación, aunque el ajuste esté activado.
Entra: los ajustes de ubicación (ATTENDANCE-F04) y el modo del dispositivo.
Sale: la jornada con la distancia, la precisión y si estaba dentro del radio, solo en el momento de
fichar; las coordenadas exactas, solo cuando el negocio pide la ubicación y el dispositivo es personal
(nunca se guardan si nadie las pidió). Se conservan lo que la jornada: cuatro años. En Registros, la
columna «Ubicación» enseña dentro o fuera.
Si falla: con el permiso denegado, «El acceso a la ubicación está denegado…»; sin la ubicación del
local fijada, «Aún no se ha fijado la ubicación del lugar de trabajo…»; sin posición, «Hace falta tu
ubicación para fichar desde este dispositivo…»; si el GPS tarda más de 15 segundos, «Obtener tu
posición ha tardado demasiado. Vuelve a intentarlo.». En todos los casos no se ficha y se puede fichar
en el mostrador.

### ATTENDANCE-F04 Ajustar la ubicación del local y cuándo se revisa una jornada olvidada
Actor: propietario, administrador, responsable
Pantalla: Ajustes
Pasos:
1. Abre Control horario → «Ajustes».
2. Activa «Pedir la ubicación al fichar desde un dispositivo personal» (desactivado, con su motivo,
   mientras el Hub no distinga los dispositivos: ATTENDANCE-F03) y elige el «Radio permitido»: 50, 100,
   250, 500 o 1000 m.
3. Desde el propio local, pulsa «Usar mi ubicación actual»: se rellenan la latitud y la longitud y ve
   la precisión leída. También puede escribirlas a mano.
4. En «Marcar a revisar tras (horas)» pone de 1 a 24 horas (12 si no lo toca).
5. Pulsa «Guardar» y ve «Ajustes guardados.». Solo se envía lo que cambió.
Entra: nada de otras apps; sin ajustes guardados se ven los valores por defecto.
Sale: los ajustes que leen Fichar (ATTENDANCE-F03) y la revisión de jornadas (ATTENDANCE-F05); el
aviso de ajustes cambiados.
Si falla: una latitud o longitud fuera de rango, solo una de las dos o unas horas que no son un entero
de 1 a 24 se señalan en su campo; con la ubicación pedida y el local sin fijar, avisa «Fija la
ubicación del lugar de trabajo o nadie podrá fichar desde un dispositivo personal.»; quien no es
responsable ve los ajustes en solo lectura.

### ATTENDANCE-F05 Marcar para revisar una jornada que nadie cerró
Actor: sistema
Pantalla: ninguna (la insignia «Por revisar» sale en Fichar y en Registros)
Pasos:
1. Una jornada abierta más horas de las fijadas en Ajustes (12 por defecto) es una jornada olvidada: la
   persona olvidó fichar la salida. Desde ese momento se ve «Por revisar» en todas partes (Fichar,
   Registros, el CSV), sin tiempo trabajado, y no cuenta como «Fichados ahora». La tarea programada
   (cada 15 minutos, en el worker) la marca en la base de datos; el Hub la marca también cuando esa
   persona vuelve a fichar la entrada.
2. No se inventa ninguna hora de salida: ni «Fichar salida» ni las pausas la cierran (responde «Esta
   jornada lleva abierta más de 12 horas y está por revisar: la corrige un responsable. Ficha la entrada
   para empezar una jornada nueva.»); la pone un responsable con una corrección (ATTENDANCE-F08).
3. La persona puede volver a fichar la entrada sin esperar a esa corrección: Fichar le ofrece «Fichar
   entrada».
Entra: las horas de ATTENDANCE-F04.
Sale: la jornada en estado «Por revisar»; el aviso de jornada marcada (solo de las que se marcan).
Si falla: si la tarea no corre, la jornada se ve igual «Por revisar» y se marca cuando la persona
vuelve a fichar.

### ATTENDANCE-F06 Ver mis jornadas del mes y quién las corrigió
Actor: empleado (y cualquiera, para las suyas)
Pantalla: Registros
Pasos:
1. Abre Control horario → «Registros»: ve sus jornadas del mes en curso, sin elegir persona.
2. En «Mes» puede elegir cualquiera de los últimos cuatro años.
3. La jornada abierta sale con «En curso» y el tiempo trabajado hasta ahora; la que falta por cerrar,
   «Por revisar».
4. Una jornada corregida sale con las horas nuevas; «Historial» enseña quién la corrigió, cuándo, el
   antes y el después y el motivo.
Entra: sus jornadas y sus pausas.
Sale: nada; solo lee.
Si falla: «No se han podido cargar las jornadas.» y «Reintentar».

### ATTENDANCE-F07 Ver las jornadas de todo el equipo
Actor: propietario, administrador, responsable
Pantalla: Registros
Pasos:
1. Abre Control horario → «Registros»: ve las jornadas del mes de todo el equipo, con el nombre de
   cada persona (también de quien ya se dio de baja: sus jornadas se guardan cuatro años).
2. Filtra por «Persona» (busca por nombre), «Mes» y «Estado» («Abierta», «Cerrada», «Por revisar»),
   y ordena por fecha, entrada, salida, persona o estado.
3. En «Ubicación» ve si la entrada y la salida se ficharon dentro del radio del local, o «Sin
   ubicación registrada».
Entra: las jornadas y pausas de todos; los nombres, de las fichas de Personal.
Sale: nada; solo lee.
Si falla: «No se han podido cargar las jornadas.» y «Reintentar».

### ATTENDANCE-F08 Corregir una jornada mal fichada, con su motivo
Actor: propietario, administrador, responsable
Pantalla: Registros
Pasos:
1. En «Registros», en la jornada mal fichada, pulsa «Corregir».
2. En «Corregir jornada» ve la entrada y la salida en la hora del negocio. Cambia la que está mal;
   dejar «Salida (vacía = sigue abierta)» vacía reabre la jornada.
3. Escribe el «Motivo» (obligatorio, al menos 3 caracteres) y pulsa «Guardar corrección».
4. Ve «Jornada corregida.»; la fila enseña las horas nuevas y el tiempo trabajado recalculado.
5. Una jornada «Por revisar» se cierra así: se le pone la salida y queda «Cerrada». Una pausa que
   seguía en curso se termina en la nueva salida.
Entra: la jornada (ATTENDANCE-F07).
Sale: la jornada con las horas nuevas y una entrada nueva en su historial (ATTENDANCE-F09), que nunca
se borra; el aviso de jornada corregida; «Fichados ahora» se actualiza.
Si falla: «La salida tiene que ser posterior a la entrada.» bajo la salida; «Estas horas se solapan con
otra jornada de esta persona.» (tocarse no es solaparse: una jornada puede empezar en el instante en
que acabó la anterior); «Esa persona ya tiene otra jornada abierta: no se puede reabrir esta.»; una
hora futura, «La hora no puede ser futura.»; sin motivo, «Escribe un motivo de al menos 3 caracteres.».
Una corrección rechazada no cambia nada ni deja rastro. «Corregir» solo aparece a quien puede
corregir.

### ATTENDANCE-F09 Ver quién cambió una jornada, cuándo y por qué
Actor: propietario, administrador, responsable; el empleado, de las suyas
Pantalla: Registros
Pasos:
1. En «Registros», en una jornada, pulsa «Historial».
2. En «Historial de correcciones» ve cada cambio, del más reciente al más antiguo: quién (o «Sistema»),
   cuándo, «Antes» → «Después» y el «Motivo».
3. Si nadie la ha corregido, ve «Esta jornada no se ha corregido nunca.».
Entra: las correcciones de ATTENDANCE-F08 y ATTENDANCE-F13.
Sale: nada; el historial no se puede editar ni borrar.
Si falla: «No se ha podido cargar el historial.».

### ATTENDANCE-F10 Sacar el mes en CSV para la gestoría o la Inspección
Actor: todos (el empleado, solo sus jornadas)
Pantalla: Registros
Pasos:
1. En «Registros», elige el mes (y, si es responsable, la persona y el estado).
2. Pulsa «Exportar CSV»; mientras tanto ve «Exportando…».
3. Se descarga `attendance-2026-10.csv` con una línea por jornada del filtro, todas, no solo las que
   caben en la pantalla: fecha, persona, entrada, salida, minutos de pausa, minutos trabajados, estado y
   si la entrada y la salida fueron dentro del radio.
4. El fichero se abre con los acentos bien en una hoja de cálculo.
Entra: las jornadas del filtro (ATTENDANCE-F06, ATTENDANCE-F07).
Sale: el fichero descargado en el dispositivo; nada se guarda en el Hub.
Si falla: un mes sin jornadas descarga solo la cabecera y avisa «No hay jornadas con este filtro: el
fichero solo lleva la cabecera.»; si la descarga falla, «No se ha podido exportar el CSV. Inténtalo de
nuevo.».

### ATTENDANCE-F11 Ver quién está fichado ahora
Actor: propietario, administrador, responsable
Pantalla: Registros («Fichados ahora»)
Pasos:
1. Abre «Registros». Encima de la tabla, «Fichados ahora» dice cuántas personas tienen la jornada
   abierta y quiénes, desde qué hora y si están en pausa.
2. Cambia solo en cuanto alguien ficha la entrada o la salida, empieza o termina una pausa, o se
   corrige una jornada.
3. Una jornada «Por revisar» (o ya olvidada) no cuenta: nadie sabe si esa persona sigue dentro. Una
   ficha dada de baja tampoco.
Entra: las jornadas abiertas (ATTENDANCE-F01, ATTENDANCE-F08).
Sale: nada; solo lee.
Si falla: el aviso de error en su lugar, sin tapar la tabla.

### ATTENDANCE-F12 Fichar la entrada o la salida de otra persona
Actor: propietario, administrador, responsable
Pantalla: ninguna (asistente y API)
Pasos:
1. El responsable le dice al asistente «ficha la entrada de Ana» o «ficha la salida de Ana» (o llama a
   la API con la persona por su id o su nombre).
2. El Hub ficha a Ana con la hora del servidor, como si lo hiciera ella, y guarda quién lo hizo.
Entra: la ficha de Personal de esa persona.
Sale: lo mismo que ATTENDANCE-F01 y ATTENDANCE-F02.
Si falla: un empleado no puede fichar a otra persona («Solo puedes fichar tu propia entrada y
salida.»); si el nombre vale para
varias, se dice cuáles y se pide que elija; si no existe, «Esa persona no existe en Personal.».

### ATTENDANCE-F13 Cerrar la jornada abierta de quien se da de baja
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un responsable da de baja a una persona en Personal (STAFF-F06) mientras tiene la jornada abierta.
2. Control horario cierra esa jornada en ese momento (y su pausa en curso) con una corrección del
   «Sistema» cuyo motivo es «Jornada cerrada al dar de baja a la persona en Personal.».
Entra: el aviso de Personal `staff.member.terminated`.
Sale: la jornada cerrada, con su entrada en el historial; el aviso de jornada corregida.
Si falla: si la persona no tenía jornada abierta, no se hace nada (y una segunda entrega del aviso
tampoco).
Nota: la reacción está hecha y probada contra Personal real (`tests/test_integration_staff.py`); la
entrega automática del aviso es el relay del outbox, que llega con el worker de la fase 2, como las
reacciones de `inventory`, `customer` o `sale`.

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien habla)
y la API, con las mismas reglas y los mismos permisos. Una persona se nombra por su id o por su nombre
(«ficha la salida de Ana»); «mi jornada de hoy» es `attendance.record.current`. Las horas viajan en ISO
8601 con zona; las duraciones, en segundos.

### Lo que ofrece: consultas (leen, no cambian nada; todas menos la exportación se siguen en vivo)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Mi jornada de hoy: mi ficha, si estoy dentro o en pausa y desde cuándo, lo trabajado y las pausas de hoy y mis diez últimas jornadas | fichar | F01, F02 | `attendance.record.current` |
| Las jornadas, con búsqueda por persona, filtros (persona, mías, estado, fechas) y orden, en páginas (hasta 100); el empleado, solo las suyas | fichar | F06, F07 | `attendance.record.list` |
| Una jornada con sus pausas y la posición al fichar (la de otro, solo con ver el equipo) | fichar | F07 | `attendance.record.detail` |
| El CSV de las jornadas del filtro (el empleado, solo las suyas) | fichar | F10 | `attendance.record.export` |
| El historial de correcciones de una jornada (o de todas), del más reciente al más antiguo; el empleado, de las suyas | fichar | F09 | `attendance.correction.list` |
| Quién está fichado ahora (cuántos y quiénes), con búsqueda | ver el equipo | F11 | `attendance.presence.list` |
| Las personas que se pueden filtrar (fichas de Personal, también las dadas de baja con jornadas), con búsqueda | ver el equipo | F07 | `attendance.person.list` |
| Los ajustes | fichar | F03, F04 | `attendance.settings.get` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Ficha la entrada (la mía, u otra persona con «fichar a otros») | fichar | F01, F03, F12 | `attendance.record.clock_in` |
| Ficha la salida (y termina la pausa en curso) | fichar | F01, F12 | `attendance.record.clock_out` |
| Empieza una pausa | fichar | F02, F12 | `attendance.break.start` |
| Termina la pausa en curso | fichar | F02, F12 | `attendance.break.end` |
| Corrige una jornada con motivo (riesgo alto) | corregir | F08 | `attendance.record.correct` |
| Guarda los ajustes (solo lo enviado) | ajustes | F04 | `attendance.settings.update` |
| Marca para revisar las jornadas olvidadas (tarea programada, sistema) | sistema | F05 | `attendance.record.review_stale` |
| Cierra la jornada abierta de una persona dada de baja (reacción, sistema) | sistema | F13 | `attendance.record.close_for_terminated` |

No hay acción de borrar una jornada, a propósito: la ley pide conservarlas cuatro años.

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Entrada fichada | Fichar la entrada | La jornada (`id`) y la persona (`member_id`) | `attendance.record.clocked_in` |
| Salida fichada | Fichar la salida | La jornada y la persona | `attendance.record.clocked_out` |
| Pausa empezada | Empezar una pausa | La pausa (`id`), la jornada (`record_id`) y la persona | `attendance.break.started` |
| Pausa terminada | Terminar una pausa (también al fichar la salida en pausa) | La pausa, la jornada y la persona | `attendance.break.ended` |
| Jornada corregida | Una corrección, del responsable o del sistema | La jornada, la persona y la corrección (`correction_id`) | `attendance.record.corrected` |
| Jornada marcada para revisar | Solo las que la revisión marca | La jornada y la persona | `attendance.record.flagged` |
| Ajustes cambiados | Guardar con algún cambio | Nada | `attendance.settings.updated` |

Los avisos nunca llevan la posición ni el motivo de una corrección (datos personales).

### A qué reacciona y lo que necesita de otras apps

- **Personal** (`requires = ["staff"]`): la jornada es de una ficha de Personal (`staff.Member`), y la
  persona de la sesión se encuentra por la ficha vinculada a su cuenta. Lee los nombres de las fichas
  (también las dadas de baja) para la tabla, el CSV y el filtro.
- `staff.member.terminated` → `attendance.record.close_for_terminated` (ATTENDANCE-F13).
- `staff.member.updated` y `staff.member.terminated` vuelven a pintar las listas (el nombre o el
  estado de una persona).
- De la plataforma: la sesión y la zona horaria del negocio (fase 1: `Europe/Madrid`).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Fichar, ver lo mío, mi historial, los ajustes y exportar lo mío | sí | sí | sí | sí | `attendance.clock` |
| Ver las jornadas de todo el equipo y quién está dentro | sí | sí | sí | no | `attendance.view_all` |
| Corregir jornadas | sí | sí | sí | no | `attendance.correct` |
| Fichar la entrada, la salida o las pausas de otra persona | sí | sí | sí | no | `attendance.clock_others` |
| Cambiar los ajustes | sí | sí | sí | no | `attendance.manage_settings` |

## Para quien lo mantiene

- Anatomía completa de una app (copia de `apps/demo`): `apps.py`, `models.py`, `schemas.py`,
  `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y
  un `tests/test_<fichero>.py` por fichero, más `test_integration_staff.py` (contra Personal real, sin
  dobles) y `test_concurrency.py` (hilos).
- Modelos: `Record` (la jornada), `Break` (la pausa), `Correction` (el rastro, solo se inserta) y
  `AttendanceSettings` (una fila, restricción `attendance_settings_singleton`). UUIDv7, sin `hub_id`.
  `Record.member` es una FK a `staff.Member` con `PROTECT`: una ficha con jornadas no se puede borrar
  (la baja de Personal es lógica). `Record.work_date` es el día del negocio de la entrada: se fija al
  fichar y al corregir, y es lo que filtran el mes y el CSV.
- **Una sola jornada abierta por persona**: índice único parcial `attendance_record_one_open`; **una
  sola pausa en curso por jornada**: `attendance_break_one_running`. Cada acción sobre las jornadas de
  una persona bloquea antes su ficha (`select_for_update(no_key=True)`, que no frena a Personal): dos
  «Fichar entrada» a la vez esperan uno al otro y el segundo ve la jornada abierta (409); si aun así
  llegara a chocar el índice, se traduce al mismo 409. Hay tests con hilos.
- Coherencia en la base de datos: abierta o por revisar ⇒ sin salida; cerrada ⇒ con salida; la salida
  después de la entrada; la pausa termina después de empezar.
- La distancia al local la calcula el servidor con `geopy` (`geodesic`, WGS-84) a partir de la
  posición que manda el dispositivo; el dispositivo nunca dice si está dentro ni si es personal: eso
  sale de `services.device_source(ctx)`, que en la fase 1 dice «compartido» y en la fase 2 leerá el
  dispositivo de confianza de la sesión. Las coordenadas se guardan solo si el negocio pide la ubicación
  y el dispositivo es personal; si no, solo distancia, dentro/fuera y precisión (la migración 0002 borró
  las de las jornadas del dispositivo compartido).
- **Jornada olvidada** (`queries.is_stale`): abierta y con más horas que las de Ajustes. Se lee como
  «Por revisar» al momento (estado efectivo, sin tiempo trabajado y con su pausa parada), aunque la
  tarea aún no la haya marcado; `clock_out` y las pausas la rechazan con 409
  `attendance.day_needs_review`, y `clock_in` la marca.
- Una corrección guarda `is_system` y el nombre de quien la hizo (`created_by_name`): si su usuario se
  borra, sigue siendo suya y no del «Sistema».
- `close_for_terminated` solo actúa sobre una ficha dada de baja.
- El «hoy» y el día de una jornada son los del negocio: `timezone.localdate()` (fase 1, `TIME_ZONE` =
  `Europe/Madrid`). Las horas se guardan en UTC (`timestamptz`).
- Las duraciones se calculan en el servidor en segundos «a fecha de» (`as_of`); la pantalla las hace
  correr sola a partir de ahí, sin preguntar cada segundo. Una jornada «Por revisar» sin salida no tiene
  tiempo trabajado (vacío): contar «hasta ahora» sumaría días que nadie trabajó.
- La revisión de jornadas olvidadas es la tarea programada `review_stale` (`*/15 * * * *`, `collapse`,
  en UTC, la corre el worker de la fase 2 como sistema) y la aplica también `clock_in` a la persona que
  ficha, para no depender del worker.
- Asistente: toda operación declara `ai={"description", "risk"}` (`risk` solo en las acciones; `high`
  en corregir) y todo campo de entrada lleva `description`.
- **Admin de Django** (ronda 12, PLAN §17): ajustes con CRUD completo; jornadas, pausas y correcciones
  en **solo lectura** (salvo la nota interna de la jornada), sin alta ni borrado: una hora solo cambia
  con `attendance.record.correct`, que deja rastro. Contradice el «CRUD completo sobre todas sus
  tablas» del admin; lo impone el art. 34.9 ET, como en `invoice` lo impone el RD 1619/2012.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`; lo que sí se
  separa son los avisos en vivo. El PIN y el dispositivo de confianza (quién ficha en un TPV compartido
  y si un dispositivo es personal) son de `base`, en la fase 2.

## Lo que queda fuera

- **Panel «Fichados ahora» en el Inicio** (ATTENDANCE-F11): el Hub aún no tiene paneles en el Inicio;
  la consulta (`attendance.presence.list`) ya está, se sigue en vivo y se ve en Registros.
- **Modo del dispositivo** (ATTENDANCE-F03): es de la plataforma (fase 2). Hasta entonces todo
  dispositivo ficha como el compartido y «Pedir la ubicación…» queda desactivado en Ajustes.
- **Suprimir las jornadas pasados los cuatro años** (y con ellas su posición): se conservan; la
  supresión automática no está (como attendance#7 del producto actual).
- **Iconos propios** (café, play, ubicación, huella): pedidos en `UI-REQUESTS.md`; mientras, iconos
  registrados equivalentes.
- **Entrega automática de los avisos de otras apps** (ATTENDANCE-F13) y **tarea programada**
  (ATTENDANCE-F05): las corre el worker de la fase 2 (relay del outbox y tareas por hub). La reacción y la
  operación están hechas y probadas; mientras tanto, la revisión se aplica al volver a fichar.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/attendance/clock`, `/attendance/records` y `/attendance/settings`; la barra
  de pestañas (`frontend/tabs.ts`) son las tres, «Ajustes» para todos (en solo lectura para quien no
  puede guardar), como en el producto actual.
- Fichar se suscribe a `attendance.record.current` y `attendance.settings.get`; el reloj, el tiempo
  desde la entrada y los totales de hoy corren con un temporizador de un segundo sobre el `as_of` del
  servidor.
- Registros: `useLiveList` + `useServerTable` (ventanas de hasta 100 filas, orden `columna`/`-columna`),
  la persona con `Combo` (busca en `attendance.person.list`), el mes y el estado como filtros; las
  escrituras con `useCommand`.
- Ajustes envía solo los campos que la persona tocó y cambió.

## Paridad con el producto actual (para quien lo mantiene)

### Operaciones

| Producto actual | Ahora | Nota |
|---|---|---|
| `attendance.clock_in` | `attendance.record.clock_in` | Persona opcional (F12); la distancia la mide el Hub |
| `attendance.clock_out` (+ `break_end`) | `attendance.record.clock_out` | Termina la pausa en curso |
| `attendance.break_start` / `break_end` | `attendance.break.start` / `attendance.break.end` | |
| `attendance.records.correct` | `attendance.record.correct` | Riesgo alto; motivos de rechazo separados |
| `attendance.settings.update` | `attendance.settings.update` | Solo lo enviado |
| `attendance._auto_review_stale` | `attendance.record.review_stale` | Avisa de cada jornada marcada |
| `attendance.settings.get` | `attendance.settings.get` | |
| `attendance.records.mine_open` + `records.mine` + `breaks.mine` (Fichar) | `attendance.record.current` | Una sola consulta viva |
| `attendance.records.mine` + `records.list` | `attendance.record.list` | El servidor limita al empleado |
| `attendance.records.get` + `breaks.list` | `attendance.record.detail` | Con sus pausas |
| `attendance.corrections.list` | `attendance.correction.list` | También para el empleado, de lo suyo |
| `attendance.presence.count` | `attendance.presence.list` | Cuántos y quiénes |
| `hub.users.list` (nombres del filtro) | `attendance.person.list` | Fichas de Personal, también las dadas de baja con jornadas |
| CSV en la pantalla (`csv.ts`) | `attendance.record.export` | En el servidor, misma cabecera |
| — | `attendance.record.close_for_terminated` | Nuevo (F13) |

### Pantallas

| Producto actual | Ahora |
|---|---|
| `erp-attendance-clock` | `frontend/pages/ClockPage.vue` (`/attendance/clock`) |
| `erp-attendance-records` (tabla, «Corregir», «Historial», «Exportar CSV») | `frontend/pages/RecordsPage.vue` (`/attendance/records`), `components/CorrectionModal.vue`, `components/HistoryModal.vue` |
| `erp-attendance-settings` | `frontend/pages/SettingsPage.vue` (`/attendance/settings`) |
| Widget «Fichados ahora» del Inicio | `components/PresenceCard.vue`, encima de Registros |
| `ui/lib/geo.ts`, `device-mode.ts`, `duration.ts`, `records/zone.ts`, `minutes.ts`, `csv.ts`, `overlap.ts` | `lib/geo.ts`, `lib/device.ts`, `lib/time.ts`; los minutos, el CSV y el solape, en el servidor |

### Casos de las baterías

| Batería vieja | Dónde está ahora |
|---|---|
| `clock_cycle.hub.test.py` (día completo, rechazos, ajustes y radio, rastro, solape, presencia, permisos del empleado) | `tests/test_services.py`, `tests/test_queries.py`, `tests/test_api.py` |
| `data.pg.test.py` (dos entradas, ámbito, radio, corrección, revisión sin usuario, salida que cierra la pausa, día del negocio, solapes de attendance#12, ajustes) | `tests/test_services.py`, `tests/test_queries.py`, `tests/test_models.py`, `tests/test_concurrency.py` |
| `contract`, `manifest.contract`, `permissions.contract` | `tests/test_apps.py`, `tests/test_api.py`, `tests/test_live.py`, `tests/test_events.py` |
| Vitest de `ui/` (botones según el estado, hoy en la zona del negocio, radio, CSV, minutos, zona, solape, historial, ajustes, testids) | `frontend/**/*.test.ts` (Vitest) y `tests/e2e/attendance-clock.spec.ts` |

## Lo que NO hace, a propósito

- No calcula nóminas, horas extra ni horas contra contrato.
- No gestiona turnos ni cuadrantes: el horario de cada persona es de Personal, el del negocio de
  Horarios.
- No sigue la posición durante la jornada: solo al fichar (criterio de la AEPD).
- No cierra sola una jornada olvidada ni inventa su salida (salvo la baja en Personal, que la cierra
  con rastro del sistema).
- No borra jornadas.

## Cambios frente al producto actual

- **Quién ficha**: antes, el usuario del hub; ahora, su **ficha de Personal** (la app requiere
  `staff`). Una cuenta sin ficha vinculada no puede fichar y lo dice.
- **Operaciones con tres partes**: `attendance.clock_in` → `attendance.record.clock_in`,
  `attendance.clock_out` → `attendance.record.clock_out`, `attendance.break_start/end` →
  `attendance.break.start/end`, `attendance.records.correct` → `attendance.record.correct`,
  `attendance._auto_review_stale` → `attendance.record.review_stale`. Los avisos igual:
  `attendance.clocked_in/out` → `attendance.record.clocked_in/out`.
- **Lecturas juntadas**: `records.mine_open` + `records.mine` + `breaks.mine` (lo que pinta Fichar) son
  `attendance.record.current`; `records.mine` y `records.list` son `attendance.record.list` (el
  servidor limita al empleado a lo suyo); `records.get` + `breaks.*` son `attendance.record.detail`;
  `presence.count` es `attendance.presence.list` (cuántos y quiénes).
- **Rechazos con su motivo**: el único `attendance.clock_in_rejected` y el único
  `attendance.record_not_found` de antes se separan en `attendance.already_clocked_in`,
  `attendance.outside_radius`, `attendance.location_required`, `attendance.workplace_not_set`,
  `attendance.overlap`, `attendance.second_open_day`… y la salida antes de la entrada es un 422 en su
  campo.
- **La distancia la calcula el Hub**, no el dispositivo (antes se fiaba de `distance_m` y
  `within_radius` del cliente).
- **El CSV lo hace el servidor** (`attendance.record.export`), con la misma cabecera, y no se pide
  página a página.
- **El empleado ve el historial de sus jornadas** (attendance#8 del producto actual, cerrada aquí).
- **Las jornadas olvidadas se marcan también al volver a fichar** y la marca avisa
  (`attendance.record.flagged`), solo de las que marca (attendance#13 y #15).
- **«Fichados ahora»** dice también quiénes y se ve en Registros.
- **Fichar a otra persona** (ATTENDANCE-F12) y **cerrar la jornada al dar de baja** (ATTENDANCE-F13),
  nuevos.
- **Ajustes**: se guarda solo lo cambiado, no la foto entera.
- **El dispositivo no se declara**: `clock_in` ya no acepta `source`; lo decide el Hub.
- **Coordenadas solo si se piden**: antes se guardaban siempre que el dispositivo las mandaba.
- **Una jornada olvidada no se cierra con «Fichar salida»** ni cuenta «hasta ahora»: antes se cerraba
  como una jornada de 20 horas.
- **Una corrección no puede poner horas futuras** (antes se aceptaban).
- **Una ficha inactiva o de baja temporal no ficha la entrada** (la salida sí).
- Las listas paginan con hasta 100 por página.
