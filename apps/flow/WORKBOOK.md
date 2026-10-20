# Workbook — Automatizaciones (app)
Prefijo: FLOW
Alcance MVP: transversal (peluquería y restaurante: reglas «cuando pase esto, haz aquello»)
Estado de la app: hecha (servidor, motor y páginas); el relay del outbox que entrega los avisos llega en la fase 2

> Manual de usuario y especificación de la app `flow`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Automatizaciones del producto actual
> (`modules-workspace/modules/flows`, `origin/main` `a555f56`, v0.1.86) y del motor que lo ejecutaba,
> que vivía en el núcleo del hub viejo. Aquí la app es las dos cosas: la pantalla **y** el motor. Hace
> lo mismo, se ve igual y conserva su funcionalidad salvo lo que dicen «Cambios frente al producto
> actual» y «Qué queda fuera», al final.

## Para qué sirve y para quién

Automatizaciones es donde el negocio deja escritas reglas que se cumplen solas: «cuando se cobre una
venta grande, apunta una nota en la ficha del cliente», «cada mañana a las 9, déjame la tarea de
repasar la agenda», «cuando alguien no venga a su cita, déjame la tarea de llamarle». Desde aquí se
elige una automatización hecha de la galería o se monta una desde cero, se le conceden los permisos
que necesita, se prueba sin efectos, se enciende, se ejecuta a mano si hace falta y se lee lo que hizo.

Una automatización es **una columna**: arriba, **cuándo arranca** (algo que pasa en el negocio, un
horario, una fecha o solo a mano); debajo, sus **pasos**, que se hacen en orden: **Hacer algo** (una
acción de otra app, por ejemplo crear una tarea), **Consultar algo** (leer un dato de otra app),
**Solo sigue si…** (una condición: si no se cumple, la automatización termina ahí sin error) y
**Esperar** (minutos, horas o días). Hoy arrancan solas las de horario y las de fecha; las que arrancan
cuando pasa algo en el negocio se ejecutan con **Ejecutar ahora** hasta que les llegue el aviso
(FLOW-F21).

Solo la usan el **propietario** y el **administrador**: una automatización actúa en nombre del negocio
sin nadie delante. El responsable y el empleado no la ven.

Cuando el Hub tenga su asistente (hoy no lo tiene: FLOW-F17), la usará por voz o por texto con la
sesión de quien habla: «crea un flujo que al completar una venta de más de 100 € me cree una tarea» (lo
deja como **borrador**, apagado, para que lo revises), «activa la automatización de bienvenida», «pausa
la de la caja», «¿qué automatizaciones tengo?», «ejecuta ahora la revisión semanal», «¿por qué falló la
de bienvenida?».

## Referencia adoptada

**Con qué permisos actúa una automatización y si se puede ejecutar a mano estando en pausa** (skill
`market-decision`, 2026-10-15).

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Salesforce Flow | Las automatizaciones que arrancan solas (por un registro) corren en **contexto de sistema**, sin mirar los permisos de quien las hizo | https://trailhead.salesforce.com/content/learn/modules/flow-implementation-2/grant-flow-permissions-and-context |
| HubSpot Workflows | Solo se inscribe a mano un registro si el flujo **está encendido**; apagado, no entra nada nuevo | https://knowledge.hubspot.com/workflows/manually-enroll-objects-into-workflows |
| HubSpot Workflows | Apagar para lo nuevo; lo que estaba esperando no ejecuta sus acciones | https://knowledge.hubspot.com/workflows/turn-off-workflows |
| Power Automate | Un flujo automático o programado corre con las conexiones **de su dueño**; si el dueño se va, hay que cambiarlo | https://learn.microsoft.com/power-automate/change-cloud-flow-owner |
| Power Automate (foro) | Al desactivar la cuenta del dueño, los flujos automáticos se rompieron; solo siguieron los manuales | https://powerusers.microsoft.com/t5/General-Power-Automate/Need-to-use-another-User-s-connections-on-a-Flow/m-p/1507107 |
| Power Automate | Un flujo en «Desactivado» no corre: hay que volver a activarlo | https://learn.microsoft.com/power-automate/fix-connection-failures |
| Zapier | Cada Zap usa las conexiones privadas de su dueño; el dueño tiene que tenerlas para encenderlo | https://help.zapier.com/hc/en-us/articles/8496326497037 |
| Zapier (foro de consultoría) | Un Zap hecho con la cuenta de quien se fue sigue corriendo con sus credenciales | https://alltomate.com/blogs/is-zapier-safe/ |
| Business Central | Las tareas en cola corren con la sesión de quien las dejó listas y necesitan sus permisos | https://learn.microsoft.com/en-us/dynamics365/release-plan/2023wave1/smb/dynamics365-business-central/delegated-admins-job-queue-entries-are-run-user |
| Odoo | Las acciones automáticas corren con acceso elevado (`sudo`); se recomienda no esconder con ello permisos que faltan | https://deploymonkey.com/blog/odoo-sudo-superuser-security |
| Producto actual (ERPlora) | «Una automatización actúa con sus propios permisos, nunca con los de quien la creó»; se conceden uno a uno; el hub rechaza ejecutar una en pausa | `modules/flows/WORKFLOW.md`, «Reglas que no se rompen» y FLOWS-F22 |

**Gana:** las herramientas **dentro del producto** (Salesforce, HubSpot, Odoo y el producto actual)
hacen correr la automatización **como el negocio**, no como la persona que la creó; las de
integración (Zapier, Power Automate, Business Central) usan la cuenta del dueño, y sus foros cuentan
lo que pasa cuando esa persona se va. Nuestro usuario es un negocio pequeño cuyo personal cambia, así
que la automatización actúa **como el negocio**, pero **solo con las acciones que el dueño le ha
autorizado una a una** (como el producto actual): sin permiso concedido, el paso se rechaza y el
historial lo dice. Y **ejecutar a mano exige que esté encendida** (HubSpot, Power Automate y el
producto actual): para ver qué haría estando apagada está **Probar**, que no ejecuta nada.
**Por qué las demás no:** con los permisos de quien la creó, la automatización deja de funcionar el
día que esa persona se va o cambia de rol, que es la queja repetida de los foros; con todos los
permisos del sistema y sin lista, una automatización mal escrita podría hacer cualquier cosa.

Del producto actual se conserva, ya contrastado allí contra Zapier, Make, Power Automate, Shopify
Flow, Odoo y Business Central (`qa-hub-flows`, ADR-0461): **una columna** de pasos de arriba abajo y
no un lienzo de nodos (en la tablet del mostrador una columna se usa con el dedo); **sin
bifurcaciones**: un «Solo sigue si…» que no se cumple termina la automatización (eso es funcionar, no
fallar), y dos desenlaces son dos automatizaciones; **empezar por una plantilla** de la galería; y lo
que escribe el asistente nace **borrador**.

## Antes de empezar

1. Solo el **propietario** o un **administrador** abren Automatizaciones (menú **Automatizaciones**).
2. Las automatizaciones usan **avisos y acciones de otras apps**: la galería y los desplegables solo
   ofrecen los de las apps activas en el negocio. Nueve de las diez tarjetas de la galería crean una
   **tarea**, así que necesitan la app **Tareas**; sin ella la galería las esconde y dice qué falta.
3. Los horarios se leen en la hora del negocio: en la fase 1, **Europe/Madrid**.

Configuración inicial, paso a paso:

1. Abre **Automatizaciones** (FLOW-F01).
2. En la galería, abre una tarjeta, lee qué hará y pulsa **Usar esta** (FLOW-F04).
3. En la pestaña **Permisos** pulsa **Autorizar todo lo que necesita** (FLOW-F12).
4. Abre **Probar** y revisa lo que haría con lo último que pasó en el negocio (FLOW-F13).
5. Enciende el interruptor y pulsa **Guardar** (FLOW-F14).
6. Cuando se dispare, revísala en **Historial** (FLOW-F16).

## Pantallas

### Automatizaciones
Menú **Automatizaciones**, una sola entrada. De arriba abajo:

- El botón **Nueva automatización**, arriba a la derecha.
- **Esperan tu respuesta** — solo si hay alguna pregunta que puedas contestar: cada tarjeta, de qué
  automatización viene, la pregunta y sus detalles, a quién se le hizo, qué pasa si nadie contesta y qué
  hace un no, **Añadir una nota (opcional)**, **Aprobar** y **No** (FLOW-F29). Un responsable o un empleado,
  que solo contestan, ven solo esto: «No hay nada esperando tu respuesta.» cuando no hay nada.
- **Propuestas por el asistente** — solo si hay borradores: «El asistente las escribió cuando le
  pediste una automatización. No hace nada hasta que la revises y la actives.», y por cada uno su
  nombre, la etiqueta «Borrador», **Revisar** y una × («Descartar») (FLOW-F18, FLOW-F19).
- **Tus automatizaciones** — solo si hay alguna. El buscador «Busca por nombre, por lo que la arranca o
  por lo que hace», los filtros **Ver** (encendidas, en pausa) y **Arranca con** (algo que pasa, un
  horario, una fecha, a mano), el orden (tocadas al final, nombre) y el recuento. Cada fila: casilla
  para elegirla, el nombre, cuándo arranca en palabras («Cuando se cobra una venta», «Todos los días a
  las 09:00», «Solo cuando pulses Ejecutar»), la última ejecución, la etiqueta «Activa» o «En pausa»,
  el interruptor, **Hacer una copia** y **Borrar**. Con varias elegidas, **Encenderlas** y **Ponerlas en
  pausa** (FLOW-F02, FLOW-F03).
- **La galería**, siempre debajo: «Elige una y pasa a ser tuya, apagada, para que la mires antes de que
  haga nada.», el botón **¿Cómo funciona esto?** y las tarjetas en «Cualquier negocio», «Peluquería y
  estética» y «Bares y restaurantes»; al final, la línea de lo que falta («Hay automatizaciones
  ocultas: necesitan la app …») (FLOW-F04).

### Editor de automatización
Se abre al tocar una fila, al pulsar **Nueva automatización**, al usar una tarjeta o al revisar un
borrador. Cabecera: ← (vuelve a la lista; si hay cambios sin guardar, pregunta antes), el nombre
(vacío: «Automatización sin nombre»), la etiqueta «Activa»/«En pausa», el interruptor, **Probar**,
**Ejecutar ahora** y **Guardar** («Guardando…»). Cuatro pestañas:

- **Pasos**: la tarjeta del disparador («Cuando pase esto…»), los pasos en columna, cada uno con su asa
  para arrastrar y × (las esperas y los «Solo sigue si…» son tiras estrechas; el resto, tarjetas que se
  despliegan al tocarlas; dentro, **Más opciones**: «Solo si…» y «Si falla, sigue», FLOW-F25), y los
  botones para añadir: **Hacer algo**, **Consultar algo**, **Solo sigue
  si…**, **Esperar**, **Llamar a otro sistema** (FLOW-F27) y **Preguntar antes a alguien** (FLOW-F28). Sin pasos: «Todavía no hay pasos. Añade lo primero que debe hacer esta
  automatización.»
- **Probar**: lo que haría con lo último que pasó, sin hacer nada (FLOW-F13).
- **Permisos**: «Una automatización se ejecuta con sus propios permisos, nunca con los tuyos. Nada de
  lo de abajo ocurre hasta que lo autorices.», las filas «Falta tu permiso» o «Autorizado» y
  **Autorizar todo lo que necesita** (FLOW-F12).
- **Historial**: las ejecuciones, las más recientes primero y las paradas por error arriba (FLOW-F16);
  una parada por un error en un paso lleva **Reanudar desde el paso que falló** (FLOW-F24).

### Guía
Botón **¿Cómo funciona esto?** de la galería. «Cómo funcionan las automatizaciones», con cinco
apartados: «Qué es una automatización», «Tu primera automatización, paso a paso», «Los permisos: por
qué hay que decir que sí», «Cómo saber si funcionó» y «Lo que todavía no puede hacer». **Volver a las
automatizaciones** regresa (FLOW-F08).

## Estados de cada pantalla

| Estado | Qué se ve |
|---|---|
| Cargando | La lista con su indicador; el editor, «Cargando…» |
| Vacío | Sin automatizaciones, solo la galería; sin pasos, «Todavía no hay pasos…»; sin ejecuciones, «Todavía no se ha ejecutado.» |
| Sin resultados | «Aquí no hay nada que encaje con eso.» y **Volver a verlas todas** |
| Error | El mensaje en rojo encima, con **Reintentar** en la lista; un fallo al guardar, encender, copiar o borrar dice qué no encaja y no cambia nada; si no se puede leer lo que pueden usar las automatizaciones (avisos y acciones), «No se ha podido leer lo que pueden usar aquí las automatizaciones.» con **Reintentar** |
| Reconectando | «Reconectando…» mientras vuelve el directo; lo pintado se queda |
| Sin permiso | «No tienes permiso» en lugar de la pantalla |
| App inactiva | «Esta app no está activa en este negocio» |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| FLOW-F01 | Entrar en Automatizaciones | hecho |
| FLOW-F02 | Ver, buscar y ordenar las automatizaciones | hecho |
| FLOW-F03 | Encender o pausar desde la lista, una o varias | hecho |
| FLOW-F04 | Crear una automatización desde una tarjeta de la galería | hecho |
| FLOW-F05 | Llegar a una tarjeta desde otro sitio | hecho |
| FLOW-F06 | Hacer una copia | hecho |
| FLOW-F07 | Borrar una automatización | hecho |
| FLOW-F08 | Leer la guía | hecho |
| FLOW-F09 | Crear una automatización desde cero | hecho |
| FLOW-F10 | Elegir cuándo arranca | hecho |
| FLOW-F11 | Añadir, ordenar y rellenar los pasos | hecho |
| FLOW-F12 | Conceder y retirar los permisos | hecho |
| FLOW-F13 | Probar sin que haga nada | hecho |
| FLOW-F14 | Guardar y encender desde el editor | hecho |
| FLOW-F15 | Ejecutar a mano | hecho |
| FLOW-F16 | Ver qué hizo y por qué falló | hecho |
| FLOW-F17 | Pedirle al asistente una automatización | parcial |
| FLOW-F18 | Revisar un borrador del asistente y crearlo | hecho |
| FLOW-F19 | Descartar un borrador del asistente | hecho |
| FLOW-F20 | Otra app pregunta si una automatización ya está montada | hecho |
| FLOW-F21 | Cuando pasa algo en el negocio, la automatización arranca | parcial |
| FLOW-F22 | Cuando llega la hora, la automatización arranca | hecho |
| FLOW-F23 | Cuando acaba una espera, la automatización sigue | hecho |
| FLOW-F24 | Reanudar una ejecución desde el paso que falló | hecho |
| FLOW-F25 | «Solo si…» y «Si falla, sigue» en cada paso | hecho |
| FLOW-F26 | Guardar secretos que no se pueden volver a leer | parcial |
| FLOW-F27 | Llamar a otro sistema | hecho |
| FLOW-F28 | Preguntar antes a alguien | hecho |
| FLOW-F29 | Contestar lo que pregunta una automatización | hecho |
| FLOW-F30 | Cerrar lo que nadie contestó a tiempo | hecho |
| FLOW-F31 | Mandar un mensaje a un cliente | parcial |
| FLOW-F32 | Poner una foto, un vídeo o un PDF en la cabecera de un WhatsApp | parcial |

### FLOW-F01 Entrar en Automatizaciones
<!-- origen: old:flows/workflow/lista-y-galeria.md#flows-f01 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. Abre **Automatizaciones** en el menú.
2. Salen los borradores del asistente (si hay), tus automatizaciones (si hay) y la galería.
Entra: la sesión.
Sale: nada guardado.
Si falla: sin permiso, «No tienes permiso»; con la app apagada, «Esta app no está activa en este
negocio»; cualquier otro fallo, en rojo con **Reintentar**. Lo ven el propietario y el administrador; el
resto del equipo no tiene la entrada en el menú.
Implicados: FLOW-F02, FLOW-F04, FLOW-F18

### FLOW-F02 Ver, buscar y ordenar las automatizaciones
<!-- origen: old-hub:HUB-F81 old:flows/workflow/lista-y-galeria.md#flows-f02 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. En **Tus automatizaciones** cada fila dice el nombre, cuándo arranca en palabras, cuándo se ejecutó
   por última vez y cómo acabó, y si está «Activa» o «En pausa».
2. Escribe en el buscador (nombre, el aviso que la arranca o las acciones que hace) o filtra por
   **Ver** y **Arranca con**; ordena por **Tocadas al final** o **Nombre**.
3. Sin resultados: «Aquí no hay nada que encaje con eso.» y **Volver a verlas todas**.
4. Toca una fila para abrirla en el editor.
Entra: las automatizaciones del negocio, en páginas de hasta 100.
Sale: nada guardado. La lista se actualiza sola cuando alguien cambia una o termina una ejecución.
Si falla: si no se puede leer la lista, el mensaje en rojo arriba con **Reintentar**; lo que ya estaba
pintado se queda.
Implicados: FLOW-F01, FLOW-F03, FLOW-F06, FLOW-F07

### FLOW-F03 Encender o pausar desde la lista, una o varias
<!-- origen: old-hub:HUB-F87 old:flows/workflow/lista-y-galeria.md#flows-f03 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. Mueve el interruptor de una fila: se guarda al momento y la etiqueta pasa a «Activa» o «En pausa».
2. Para varias: marca sus casillas y pulsa **Encenderlas** o **Ponerlas en pausa**.
3. Encender una a la que le faltan permisos avisa: «Encendida, pero aún no tiene los permisos que pide:
   no hará nada hasta que se los concedas en la pestaña Permisos.»
Entra: la automatización (por voz, por su nombre: «activa la automatización de bienvenida»).
Sale: encendida o en pausa (`flow.flow.enabled`, `flow.flow.paused`). Al pausarla deja de arrancar;
una ejecución que espera se cancela al despertar si sigue en pausa (si se vuelve a encender antes,
sigue). Un horario que se enciende cuenta desde ese momento: no recupera lo que pasó mientras estaba
en pausa.
Si falla: el mensaje en rojo arriba; la fila sigue como estaba.
Implicados: FLOW-F12, FLOW-F14, FLOW-F22, FLOW-F23

### FLOW-F04 Crear una automatización desde una tarjeta de la galería
<!-- origen: old:flows/workflow/lista-y-galeria.md#flows-f04 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. En la galería, toca una tarjeta: se despliega (una a la vez) con la frase de lo que hará, «Lo que
   decides tú» y «Lo que te va a pedir permiso para hacer», cada permiso con su explicación.
2. Si ya hay una automatización encendida que arranca con el mismo aviso, avisa: «Ojo: «…» ya se
   dispara con lo mismo.»
3. Pulsa **Usar esta** («Se crea en pausa. No pasa nada hasta que la enciendas.»).
4. Se abre el editor de la nueva, en pausa, en la pestaña **Permisos**. Sigue por FLOW-F12, FLOW-F13 y
   FLOW-F14.
5. Si el negocio ya la tiene, la tarjeta lleva «Activa», «En pausa» o «Sin terminar» (sin permisos) y
   el primer botón es **Verla**; **Usar esta** sigue disponible y crea una segunda. Una tarjeta de
   horario se reconoce por su horario y lo que hace, aunque se le haya cambiado el nombre.
Entra: las diez tarjetas: siete de «Cualquier negocio», dos de «Peluquería y estética» y una de «Bares
y restaurantes». Una tarjeta se esconde si falta una app de las que usa, y debajo de la galería se dice
cuál.
Sale: una automatización nueva, **en pausa y sin permisos**, con el nombre y los valores de la tarjeta
(esperar un día, 100,00 €, seis personas…).
Si falla: el mensaje en rojo dentro de la tarjeta; no se crea nada.
Implicados: FLOW-F05, FLOW-F08, FLOW-F12, FLOW-F13, FLOW-F14

Las diez tarjetas de la galería, con su sector, cuándo arrancan y qué hacen.

| Tarjeta | Sector | Arranca | Hace |
|---|---|---|---|
| Dar la bienvenida a un cliente nuevo | cualquiera | Se crea una ficha de cliente | Espera un día y deja la tarea de darle la bienvenida |
| Apuntar las ventas grandes en la ficha | cualquiera | Se cobra una venta | Solo si tiene cliente y pasa de 100,00 €: apunta una nota en su ficha |
| La lista de bienvenida de alguien nuevo en el equipo | cualquiera | Se da de alta a alguien en Personal | Deja la tarea de preparar su primer día |
| Revisar la caja al cerrarla | cualquiera | Se cierra una caja | Deja la tarea de revisar el cierre |
| Enterarte cuando Hacienda rechaza un registro | cualquiera | VeriFactu marca un registro como rechazado | Deja una tarea urgente |
| Repasar la semana el viernes | cualquiera | Los viernes a las 18:00 | Deja la tarea de repasar la semana |
| Revisar la agenda cada mañana | peluquería | Todos los días a las 09:00 | Deja la tarea de repasar la agenda |
| Llamar a quien no vino | peluquería | Una cita se marca como «no vino» | Deja una tarea urgente de llamarle |
| Preparar las mesas de grupos grandes | restaurante | Entra una reserva | Solo si son seis o más: deja la tarea de prepararla |
| Avisar de una venta grande | cualquiera | Se cobra una venta | Solo si pasa de 100,00 €: deja una tarea |

### FLOW-F05 Llegar a una tarjeta desde otro sitio
<!-- origen: old:flows/workflow/lista-y-galeria.md#flows-f07 -->
Estado: hecho (pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. Abre un atajo a una automatización de la galería (un enlace guardado o el que ofrezca otra app; hoy
   ninguna app del Hub lo ofrece todavía): se abre **Automatizaciones** con esa tarjeta desplegada y a
   la vista.
2. Si vuelve a tocar un atajo con la pantalla ya abierta, se despliega la tarjeta nueva.
3. Un atajo a una tarjeta que no existe o está escondida enseña la galería sin abrir nada.
Entra: la tarjeta que nombra el atajo.
Sale: nada guardado.
Si falla: lo mismo que FLOW-F01; una tarjeta que no se puede usar aquí no se abre.
Implicados: FLOW-F04, FLOW-F20

### FLOW-F06 Hacer una copia
<!-- origen: old:flows/workflow/lista-y-galeria.md#flows-f08 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. En la fila, pulsa **Hacer una copia**.
2. Sale «Copia de …» (o «Copia de … (2)») en la lista, en pausa, y el aviso «Copiada, y la copia está en
   pausa. No lleva ninguno de los permisos de la original: concédele lo que necesite antes de
   encenderla.».
Entra: la automatización que se copia (por voz, por su nombre).
Sale: una automatización nueva con los mismos pasos, en pausa, sin permisos y sin historial
(`flow.flow.created`).
Si falla: el mensaje en rojo arriba; no se crea nada.
Implicados: FLOW-F02, FLOW-F12

### FLOW-F07 Borrar una automatización
<!-- origen: old-hub:HUB-F88 old:flows/workflow/lista-y-galeria.md#flows-f09 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. En la fila, pulsa **Borrar**.
2. Confirma: «¿Borrar «…»? Esto no se puede deshacer.» con **Sí, bórrala** o **Déjala**.
Entra: la automatización que se borra (por voz, por su nombre, y siempre con la confirmación).
Sale: la automatización deja de arrancar al momento y sale de la lista; lo que esperaba se cancela al
momento; su historial se conserva (`flow.flow.deleted`).
Si falla: el mensaje en rojo arriba; la fila sigue.
Implicados: FLOW-F02, FLOW-F16, FLOW-F23

### FLOW-F08 Leer la guía
<!-- origen: old:flows/workflow/lista-y-galeria.md#flows-f10 -->
Estado: hecho (pantalla)
Actor: propietario, administrador
Pantalla: Guía
Pasos:
1. En la galería, pulsa **¿Cómo funciona esto?**.
2. Lee los cinco apartados. «Lo que todavía no puede hacer» empieza por «Arrancar sola cuando pasa algo
   en el negocio»: por ahora una automatización de «Pasa algo» solo se ejecuta con **Ejecutar ahora**.
3. **Volver a las automatizaciones** regresa.
Entra: nada; los textos van dentro de la app.
Sale: nada guardado.
Si falla: no lee nada del negocio; sin permiso, «No tienes permiso».
Implicados: FLOW-F04, FLOW-F21

### FLOW-F09 Crear una automatización desde cero
<!-- origen: old-hub:HUB-F80 old:flows/workflow/editor.md#flows-f12 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. En **Automatizaciones** pulsa **Nueva automatización**.
2. Se abre el editor vacío: «Automatización sin nombre», «En pausa», el disparador «Solo cuando pulses
   Ejecutar» y «Todavía no hay pasos…».
3. Escribe el nombre, elige cuándo arranca (FLOW-F10) y añade los pasos (FLOW-F11).
4. Pulsa **Guardar**: sale «Guardada.» y el editor sigue abierto sobre ella; ya se le pueden conceder
   permisos (FLOW-F12).
Entra: lo que escribe en el editor y lo que pueden usar las automatizaciones del negocio (avisos y
acciones de sus apps activas).
Sale: una automatización nueva, en pausa salvo que se haya encendido el interruptor antes de guardar, y
sin permisos (`flow.flow.created`). Sin nombre se guarda como «Automatización sin nombre».
Si falla: lo que no encaja, en rojo y junto al paso que lo tiene («Elige qué tiene que hacer este
paso.», «Este aviso no existe en tu negocio.», «Esa fecha y hora ya ha pasado.»…); no se guarda nada.
Implicados: FLOW-F10, FLOW-F11, FLOW-F12, FLOW-F14

### FLOW-F10 Elegir cuándo arranca
<!-- origen: old-hub:HUB-F108 old:flows/workflow/editor.md#flows-f13 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Toca la tarjeta «Cuando pase esto…» y elige:
   - **Pasa algo**: en «Elige qué pasa», los avisos de las apps activas del negocio, dichos en palabras
     («se cobra una venta», «se crea una ficha de cliente», «una cita se marca como no vino»…) y con
     buscador. Debajo, **Solo cuando…**: condiciones sobre los datos del aviso («el total es mayor que
     10000»); sin ellas arranca con cada aviso. Avisa: «Por ahora no arranca sola cuando pasa esto:
     ejecútala con «Ejecutar ahora». Un horario o una fecha sí arrancan solos.» (FLOW-F21).
   - **Según un horario**: «Cada cuánto» (todos los días, todas las semanas, todos los meses), el día de
     la semana o del mes si toca, y la hora, en la hora del negocio. Un día del mes que no existe (el 31
     en abril) se salta ese mes.
   - **Una vez, en una fecha y hora**.
   - **Solo a mano**: no arranca sola (FLOW-F15).
2. La tarjeta resume lo elegido («Cuando se cobra una venta», «Todos los viernes a las 18:00»…).
Entra: los avisos de las apps activas.
Sale: el disparador, al **Guardar**.
Si falla: un aviso que no existe en el negocio, un horario sin hora o una fecha pasada los rechaza el
servidor al guardar, junto al campo. La fecha solo se mira si cambia: una automatización «Una vez» que ya
se disparó se puede renombrar o pausar.
Implicados: FLOW-F21, FLOW-F22, FLOW-F15

### FLOW-F11 Añadir, ordenar y rellenar los pasos
<!-- origen: old-hub:HUB-F109 old-hub:HUB-F89 old-hub:HUB-F90 old-hub:HUB-F91 old:flows/workflow/editor.md#flows-f14 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Pulsa un botón de añadir; el paso sale al final, abierto. Arrastra el asa para cambiar el orden; ×
   lo quita.
2. Rellena su formulario:
   - **Hacer algo**: «Qué hacer» (una acción de las apps activas, elegida de una lista con buscador:
     «Crear una tarea», «Añadir una nota a un cliente»…) y «Con esta información»: un campo por cada
     dato que la acción pide (los obligatorios marcados) y **Añadir información** para los opcionales.
   - **Consultar algo**: «Qué consultar» (una consulta de las apps activas), sus datos y «Qué guardar»
     («La primera fila que encuentre, campo a campo» o «Solo cuántas hay»). Si no encuentra nada, la
     automatización sigue; para pararla, se añade después un «Solo sigue si…» sobre «Encontró algo».
   - **Solo sigue si…**: una o varias filas «Dato», «Es» («igual a», «distinto de», «uno de», «está
     presente», «contiene», «mayor que», «mayor o igual que», «menor que», «menor o igual que») y
     «Valor», con **Añadir una condición**. El «Valor» se escribe o, con **Insertar un dato**, es otro
     dato de la automatización (el total del aviso frente al mínimo que leyó una consulta), y entonces
     sale como pastilla con «Quitar este dato». Si no se cumplen todas, la automatización termina ahí
     sin error.
   - **Esperar**: «Cuánto» y la unidad (minutos, horas o días), contado desde el paso anterior; de un
     minuto a 30 días.
3. En cada valor, **Insertar un dato** abre «¿Qué dato?», con los datos del aviso y un ejemplo real del
   negocio al lado (el último aviso de ese tipo), y los datos que dejan los pasos anteriores; se elige,
   no se escribe. Un dato elegido se ve como una pastilla; el resto del valor es texto.
Entra: las acciones y consultas de las apps activas, el último aviso real de ese tipo y lo que dejan los
pasos anteriores. Los datos se nombran en el idioma de la pantalla («Número de venta», «Teléfono del
cliente»), nunca con su nombre interno.
Sale: los pasos, al **Guardar**. Cada acción o consulta que se nombra pasa a pedir su permiso (FLOW-F12).
Si falla: el servidor rechaza al guardar una acción o una consulta que no existe en el negocio, un dato
de un paso que no va antes, una condición vacía o una espera fuera de rango, junto al paso.
Implicados: FLOW-F12, FLOW-F13, FLOW-F16

### FLOW-F12 Conceder y retirar los permisos
<!-- origen: old-hub:HUB-F98 old:flows/workflow/editor.md#flows-f19 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Editor de automatización
Pasos:
1. Abre **Permisos** (se abre sola al crear desde la galería).
2. Lee la lista, sacada de los pasos **guardados**: cada acción y cada consulta, dichas en palabras. Lo
   que falta sale como «Falta tu permiso»; lo concedido, «Autorizado» con **Retirar**. Con cambios
   sin guardar avisa: «Guárdala primero: lo que autorices es lo guardado.».
3. Pulsa **Autorizar todo lo que necesita**: sale «Permisos actualizados.».
Entra: los pasos guardados y los permisos que tiene.
Sale: la lista completa de permisos de la automatización (`flow.flow.granted`). Antes del primer
guardado no hay nada que autorizar: la pestaña lo dice y pide guardar.
Si falla: si la lista nombra algo que no existe en el negocio, o algo que necesita a una persona delante
(anular, devolver, borrar datos, enviar a Hacienda…), se rechaza entera y se dice qué. Nadie concede lo
que no puede hacer él mismo: «No puedes permitir lo que tú no puedes hacer: «…».» (tampoco una
integración con su clave). Cada paso actúa solo con el permiso que se le concedió, nunca con todos los
de quien la montó.
Implicados: FLOW-F04, FLOW-F06, FLOW-F11, FLOW-F16

### FLOW-F13 Probar sin que haga nada
<!-- origen: old:flows/workflow/editor.md#flows-f20 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Pulsa **Probar** (cabecera) o la pestaña **Probar**.
2. Arriba: «Nada de esto es real. No se envía nada, no se cobra nada y no se apunta nada: esto es solo
   lo que HARÍA tu automatización.» y con qué datos prueba («Con lo que pasó de verdad la última vez
   que …») o «Esto no ha pasado en tu negocio últimamente…».
3. Paso a paso dice qué haría y con qué valores, y señala: si ni siquiera arrancaría por su «Solo
   cuando…», lo que saldría vacío, lo que la acción rechazaría («Se lo rechazarían: …»), una condición
   que la pararía («Se pararía aquí, y eso es la automatización funcionando»), lo que no se puede saber
   porque sale de un paso que no ha corrido, una espera y un paso sin permiso («Todavía no le has
   permitido …»).
Entra: lo que hay en el editor, aunque no esté guardado, y el último aviso real de ese tipo.
Sale: nada: no ejecuta, no guarda.
Si falla: lo que no encaja en el documento se dice junto al paso; sin permiso para leer los avisos
reales, «No tienes permiso».
Implicados: FLOW-F10, FLOW-F11, FLOW-F12, FLOW-F14

### FLOW-F14 Guardar y encender desde el editor
<!-- origen: old-hub:HUB-F80 old-hub:HUB-F86 old:flows/workflow/editor.md#flows-f21 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Mueve el interruptor de la cabecera: la etiqueta pasa a «Activa». Si le faltan permisos avisa como en
   FLOW-F03; si no se ha abierto **Probar**, «Todavía no la has probado…». No impide encenderla.
2. Pulsa **Guardar** («Guardando…» y después «Guardada.»): se guarda el documento y, si el interruptor
   cambió, después se enciende o se pausa.
Entra: lo que hay en el editor y sus cambios sin guardar.
Sale: la automatización guardada (`flow.flow.updated`; `flow.flow.enabled` o `flow.flow.paused` si
cambió el interruptor). Cambiar el disparador o los pasos sube su versión: lo que ya estaba en marcha
sigue con la versión con la que empezó.
Si falla: el mensaje en rojo, junto al paso que no encaja; no se guarda nada. Un fallo que el Hub no
explica (sin conexión) dice «No se ha podido hacer ahora. Vuelve a intentarlo en un momento.», nunca un
texto técnico; lo escrito sigue en el editor.
Implicados: FLOW-F03, FLOW-F12, FLOW-F13, FLOW-F15

### FLOW-F15 Ejecutar a mano
<!-- origen: old-hub:HUB-F85 old:flows/workflow/editor.md#flows-f22 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Editor de automatización
Pasos:
1. Con la automatización guardada y encendida, pulsa **Ejecutar ahora**.
2. Confirma: «¿Ejecutarla ahora? Hará de verdad lo que dicen sus pasos.» con **Sí, ejecútala** o
   **Cancelar**.
3. Sale «Ejecutada. Mírala en Historial.»; si se paró por un error, «Se ejecutó y se paró por un error:
   …» en rojo; si quedó esperando, «Se ejecutó y está esperando…».
Entra: la automatización (por voz: «ejecuta ahora la revisión semanal»).
Sale: una ejecución real, con todos sus efectos (`flow.run.started`, `flow.run.finished`). Sin datos de
un aviso, lo que lee del aviso sale vacío.
Si falla: en pausa, «Esta automatización está en pausa: enciéndela para ejecutarla.»; sin guardar,
el botón no sale; con cambios sin guardar está desactivado: «Guárdala primero: «Ejecutar ahora» ejecuta lo
guardado.».
Implicados: FLOW-F14, FLOW-F16, FLOW-F21

### FLOW-F16 Ver qué hizo y por qué falló
<!-- origen: old-hub:HUB-F102 old:flows/workflow/editor.md#flows-f23 -->
Estado: hecho
Actor: propietario, administrador, asistente
Pantalla: Editor de automatización
Pasos:
1. Abre la pestaña **Historial**: las ejecuciones, las más recientes primero, de 20 en 20 con **Ver
   más**; se actualiza sola.
2. Si alguna se paró por un error, arriba sale «Necesita a alguien» con «N ejecuciones se pararon por
   un problema».
3. Cada ejecución: su estado («Terminó bien», «Terminó: no se cumplía la condición», «Se paró por un
   error», «Esperando», «Cancelada»), el día y la hora, **Copiar la referencia** y ▾ para ver sus
   pasos en palabras («Hizo: Crear una tarea», «Encontró 3», «No encontró nada, y siguió», «Esperó 1
   hora», «Se paró aquí porque no se cumplió esto: Total mayor que 10000»).
4. Una parada por error dice qué pasó y qué hacer («Ha intentado hacer algo que no le has autorizado,
   así que ha parado. Abre Permisos y concédele lo que necesita.»); si el error es de la app que hizo la
   acción, sale su frase tal cual, con el texto técnico plegado.
Entra: las ejecuciones de esa automatización de los últimos 90 días, y todas las que siguen esperando.
Sale: nada. El historial guarda cada ejecución terminada **90 días** y después la olvida; una que
espera o está en marcha no se borra nunca. Lo que leyeron sus pasos (la ficha de un cliente) no se
guarda al terminar: solo los ids y los importes del aviso que la arrancó; una parada por un error lo
guarda 7 días, para poder reanudarla (FLOW-F24).
Si falla: si no se puede leer el historial, el mensaje en rojo con **Reintentar**; sin ejecuciones,
«Todavía no se ha ejecutado.».
Implicados: FLOW-F13, FLOW-F15, FLOW-F21, FLOW-F22, FLOW-F23

### FLOW-F17 Pedirle al asistente una automatización
<!-- origen: old:flows/workflow/bandejas-y-asistente.md#flows-f26 -->
Estado: parcial — el borrador, su forma y su bandeja están hechos y probados (FLOW-F18, FLOW-F19), pero el
Hub todavía no tiene asistente: hoy nadie puede pedirlo hablando ni escribiendo.
Actor: propietario, administrador, asistente
Pantalla: asistente
Pasos:
1. Pides al asistente algo que pase solo («crea un flujo que al completar una venta de más de 100 € me
   cree una tarea»).
2. El asistente escribe un **borrador**: nombre, cuándo arranca, de uno a ocho pasos de «hacer algo»,
   «solo sigue si» o «esperar», y las notas de lo que no supo decidir.
3. Te dice que lo ha dejado esperando en Automatizaciones y repite sus dudas.
Entra: lo que se pide, en palabras, y lo que pueden usar las automatizaciones del negocio.
Sale: un borrador pendiente (`flow.draft.proposed`). **No** crea ninguna automatización, no concede
permisos y no ejecuta nada.
Si falla: un borrador que no sigue la forma pedida, o con un paso que lee lo que no deja ningún paso
anterior, se rechaza antes de guardarlo.
Implicados: FLOW-F18, FLOW-F19

### FLOW-F18 Revisar un borrador del asistente y crearlo
<!-- origen: old:flows/workflow/bandejas-y-asistente.md#flows-f27 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. En **Propuestas por el asistente**, pulsa **Revisar**: se abre en el editor como una automatización
   que todavía no existe, con el recuadro «Esto es un borrador que escribió el asistente. Está apagado,
   no tiene permisos y no pasa nada hasta que lo actives tú.» y «Lo que el asistente no ha podido
   decidir».
2. Corrige y completa los pasos (FLOW-F10, FLOW-F11).
3. Pulsa **Guardar**: se crea la automatización (en pausa si no se ha tocado el interruptor) y el
   borrador sale de la bandeja como usado, **en la misma operación**: no se puede crear dos veces.
Entra: el borrador pendiente, tal como lo dejó el asistente, con sus notas.
Sale: una automatización nueva sin permisos y el borrador usado, con el enlace a ella
(`flow.flow.created`, `flow.draft.used`). Salir sin guardar deja el borrador en la bandeja.
Si falla: si no encaja (una acción que no existe aquí), el mensaje junto al paso y no se crea nada; un
borrador ya decidido, «Ese borrador ya se decidió.».
Implicados: FLOW-F17, FLOW-F19, FLOW-F12

### FLOW-F19 Descartar un borrador del asistente
<!-- origen: old:flows/workflow/bandejas-y-asistente.md#flows-f28 -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. En **Propuestas por el asistente**, pulsa × («Descartar») en el borrador que no quiere.
2. Sale «Descartado.» y el borrador desaparece de la bandeja; los demás siguen.
Entra: el borrador pendiente.
Sale: el borrador descartado (`flow.draft.dismissed`), que se conserva como registro.
Si falla: uno ya decidido no se puede volver a decidir: «Ese borrador ya se decidió.».
Implicados: FLOW-F17, FLOW-F18

### FLOW-F20 Otra app pregunta si una automatización ya está montada
<!-- origen: old:flows/workflow/bandejas-y-asistente.md#flows-f29 -->
Estado: hecho
Actor: otra app, asistente
Pantalla: ninguna
Pasos:
1. Una app que ofrece un atajo hacia Automatizaciones pregunta con un aviso y una acción.
2. Recibe tres números: cuántas automatizaciones arrancan con ese aviso y pueden hacer esa acción,
   cuántas de ellas están encendidas y cuántas escuchan ese aviso pero todavía no tienen ningún permiso
   (a medio montar).
Entra: el aviso y la acción por los que pregunta; pide el permiso de ver automatizaciones.
Sale: tres números; ningún nombre ni contenido. Hoy ninguna app la usa todavía; el asistente también
puede preguntarla.
Si falla: sin el permiso de ver automatizaciones, se rechaza.
Implicados: FLOW-F05

### FLOW-F21 Cuando pasa algo en el negocio, la automatización arranca
<!-- origen: old-hub:HUB-F110 old-hub:HUB-F82 -->
Estado: parcial — el motor está hecho y probado con avisos reales de Clientes, Ventas y Tareas, pero
el aviso de otra app le llega con el relay del outbox, que es de la plataforma (fase 2). Hasta
entonces una automatización que arranca con «Pasa algo» no se dispara sola en el negocio: se puede
ejecutar a mano (FLOW-F15) o montar con un horario (FLOW-F22).
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Otra app deja un aviso (por ejemplo, «se cobra una venta»).
2. Cada automatización **encendida** que arranca con ese aviso y cuyo «Solo cuando…» se cumple empieza
   una ejecución con los datos del aviso, y hace sus pasos en orden.
3. Si su «Solo cuando…» ya no se puede leer (porque se escribió a mano en la administración o con una
   versión anterior), no se queda callada: empieza una ejecución que se para con «Ya no se puede leer
   su «Solo cuando…»…», visible en Historial, y las demás automatizaciones de ese aviso siguen.
Entra: el aviso de otra app, con sus datos (ids, importes y estados; nunca nombres ni textos).
Sale: una ejecución (`flow.run.started`, `flow.run.finished` o `flow.run.parked` si espera). Un mismo
aviso entregado dos veces arranca **una sola** ejecución por automatización.
Si falla: cada paso que falla para la ejecución con su motivo, visible en Historial; los pasos
anteriores se quedan hechos. Una automatización que se dispararía a sí misma en cadena se para (ver
«Para quien lo mantiene»). Un «Solo sigue si…» que ya no se puede leer para la ejecución con «Ya no se
puede leer este «Solo sigue si…»…».
Implicados: FLOW-F10, FLOW-F11, FLOW-F15, FLOW-F16

### FLOW-F22 Cuando llega la hora, la automatización arranca
<!-- origen: old-hub:HUB-F229 old-hub:HUB-F83 old-hub:HUB-F84 -->
Estado: hecho
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Cada minuto, la plataforma mira las automatizaciones encendidas con horario o fecha.
2. Las que han llegado a su hora (en la hora del negocio) arrancan una vez y hacen sus pasos.
3. La siguiente hora del horario se cuenta desde ahora; una fecha arranca una sola vez.
Entra: los horarios y las fechas de las automatizaciones encendidas.
Sale: una ejecución (`flow.run.started`, `flow.run.finished`); la siguiente hora del horario. Si el
sistema estuvo parado y se perdieron varias horas, arranca **una vez** y sigue desde ahora. Una pasada
sin nada que hacer no deja ningún aviso.
Si falla: un paso que falla para esa ejecución con su motivo, visible en Historial; la siguiente hora
del horario sigue en pie.
Implicados: FLOW-F03, FLOW-F10, FLOW-F16

### FLOW-F23 Cuando acaba una espera, la automatización sigue
<!-- origen: old-hub:HUB-F92 -->
Estado: hecho
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Cada minuto, la plataforma mira las ejecuciones que esperaban («Esperar»).
2. Las que han terminado su espera siguen por el paso siguiente, con la versión de la automatización
   con la que empezaron.
Entra: las ejecuciones que esperan y la hora a la que despiertan.
Sale: la ejecución sigue (`flow.run.resumed`) y termina o vuelve a esperar. Una pasada sin nada que
hacer no deja ningún aviso.
Si falla: si la automatización está en pausa al despertar, la ejecución se cancela («Cancelada: la
automatización se puso en pausa mientras esperaba.»); si está borrada, también («Cancelada: la
automatización se borró.»).
Implicados: FLOW-F03, FLOW-F07, FLOW-F11, FLOW-F16

### FLOW-F24 Reanudar una ejecución desde el paso que falló
<!-- origen: old-hub:HUB-F103 gh:hub#952 -->
Estado: hecho
Actor: propietario, administrador, asistente
Pantalla: Editor de automatización
Pasos:
1. En **Historial**, una ejecución que se paró por un error en uno de sus pasos lleva **Reanudar desde el
   paso que falló**. Antes, arregla la causa: concede el permiso que faltaba, vuelve a encender la app o
   espera a que el otro sistema responda.
2. Pulsa el botón y confirma: «¿Reanudarla desde el paso que falló?» con **Sí, reanúdala** o **Cancelar**.
3. Sale «Reanudada: terminó bien.» (o «…está esperando»); si vuelve a fallar, «Se reanudó y volvió a
   pararse por un error: …» junto a la ejecución, que se puede reanudar otra vez. En sus pasos queda
   «Reanudada aquí, desde el paso que había fallado».
Entra: la ejecución parada por un error (por voz, por su referencia: «reanuda la de bienvenida que falló»).
Sale: la misma ejecución sigue en el paso que falló, sin repetir los que ya hicieron efecto y con los
pasos con los que empezó, aunque la automatización haya cambiado después (`flow.run.resumed`,
`flow.run.finished`). Una ejecución parada por un error guarda lo que dejaron sus pasos **7 días** para
poder reanudarse; después lo olvida y ya no se reanuda.
Si falla: con la automatización en pausa, «Esta automatización está en pausa: enciéndela para
ejecutarla.»; borrada, «Esa automatización no existe en este negocio.»; una que se paró antes de hacer
ningún paso (una cadena, un «Solo cuando…» ilegible), en algo que necesita a una persona delante o en una
llamada a una dirección privada o mal escrita (los mismos pasos volverían a fallar), «Esta ejecución no se
puede reanudar…: ejecútala de nuevo entera»; pasados 7 días, «…ya no se puede reanudar…»;
una ya reanudada, «Solo se puede reanudar una ejecución que se paró por un error…»: nunca se reanuda dos
veces. Ninguna se reanuda sola.
Implicados: FLOW-F12, FLOW-F15, FLOW-F16

### FLOW-F25 «Solo si…» y «Si falla, sigue» en cada paso
<!-- origen: old-hub:HUB-F97 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Abre un paso de **Hacer algo**, **Consultar algo** o **Esperar** y pulsa **Más opciones**.
2. Marca **Solo si…** y escribe sus condiciones, como en un «Solo sigue si…» («Total mayor que 10000»):
   «Si no se cumple, este paso se salta y la automatización sigue.».
3. En **Hacer algo** y **Consultar algo**, marca **Si falla, sigue con los pasos siguientes**: «El fallo queda
   escrito en este paso y los siguientes pueden mirar si falló.».
4. Cerrado, el paso lo dice debajo de su título («Solo si: Total mayor que 10000 · Si falla, sigue»). Un paso
   posterior puede mirar, con **Insertar un dato**, si ese paso «Se saltó» o «Falló» y su «Código del fallo».
5. Pulsa **Guardar**.
Entra: las condiciones y la casilla de cada paso.
Sale: el paso con sus opciones, al **Guardar**. Al ejecutarse, un paso cuyo «Solo si…» no se cumple no se
hace y el historial dice «Se saltó: no se cumplía su «Solo si…» (…)»; uno que falla con «Si falla, sigue»
deja «…: el motivo. Siguió con los pasos siguientes.» y la ejecución termina bien si el resto va bien.
**Probar** dice «Se saltaría: no se cumple su «Solo si…»». Sin opciones, un paso que falla para la
ejecución, como siempre.
Si falla: un «Solo si…» que lee un dato que no deja ningún paso anterior, con una comparación que no
existe, o un «Si falla» en una espera o en un «Solo sigue si…», no se guarda. Un «Solo si…» que ya no se
puede leer (escrito en crudo en la administración) para la ejecución con «Ya no se puede leer el «Solo
si…» de este paso…», y esa ejecución no se reanuda: hay que corregir el paso.
Implicados: FLOW-F11, FLOW-F13, FLOW-F16, FLOW-F24

### FLOW-F26 Guardar secretos que no se pueden volver a leer
<!-- origen: old-hub:HUB-F99 -->
Estado: parcial — en este servidor todavía no se pueden guardar secretos; llegará cuando se active su clave
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Abre un paso de **Llamar a otro sistema**. Debajo está **Secretos**: «Claves y contraseñas de otros
   sistemas. Insértalas por su nombre; una vez guardado, nadie puede volver a leer un valor, ni siquiera tú.».
2. Escribe un **Nombre** (en mayúsculas, como «STRIPE_KEY») y su **Valor**, que se escribe tapado, y pulsa
   **Guardar secreto**. Sale «STRIPE_KEY guardado. Su valor ya no se puede mostrar.» y los dos campos se
   vacían. Guardar otra vez el mismo nombre cambia su valor.
3. La lista enseña solo los nombres. Para usar uno, en un valor del paso pulsa **Insertar un dato** y elige
   «Secreto «STRIPE_KEY»» en **Secretos**.
4. Para borrarlo, pulsa su **×** y confirma «¿Borrar STRIPE_KEY?» con **Sí, borrarlo** o **Conservarlo**.
Entra: el nombre y el valor de cada secreto (por voz, por su nombre: «guarda la clave de Stripe»).
Sale: el secreto sellado con la clave del servidor (`flow.secret.saved`, `flow.secret.deleted`). Su valor
solo se abre en el momento de llamar y nunca sale: ni en la lista, ni en **Probar** (que enseña «••••»), ni
en el historial, ni en un fallo; lo que el otro sistema responda con el secreto dentro también sale tapado.
Si falla: un nombre con minúsculas al principio, cifras primero o símbolos: «Usa mayúsculas, cifras y _,
empezando por una letra (STRIPE_KEY).», y lo escrito se queda; sin la clave de cifrado del servidor, la caja
dice «Este servidor todavía no puede guardar secretos: le falta su clave de cifrado.» en cuanto se abre, en
lugar de los campos, y no deja guardar.
Guardar un paso que nombra un secreto que no existe: «No hay ningún secreto llamado «X».» junto al campo.
Una ejecución cuyo secreto se borró o ya no se puede abrir se para antes de llamar, con el motivo y qué hacer.
Un secreto solo se puede insertar en **Llamar a otro sistema**: en cualquier otro paso no se guarda.
Implicados: FLOW-F11, FLOW-F13, FLOW-F16, FLOW-F27

### FLOW-F27 Llamar a otro sistema
<!-- origen: old-hub:HUB-F94 old:flows/workflow/editor.md#flows-f16 gh:hub#2648 gh:hub#2659 gh:hub#2675 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. En **Pasos**, pulsa **Llamar a otro sistema**. Se abre su tarjeta.
2. Elige el **Método** y escribe la **Dirección** a mano, empezando por «https» y el nombre del servidor:
   «Este paso te pedirá permiso para llamar a» y ese nombre. Después del nombre se pueden insertar datos.
3. Añade las **Cabeceras** que pida el otro sistema (**Añadir una cabecera**: **Nombre** y **Valor**) y **Qué
   envía**. En cualquier valor, **Insertar un dato** ofrece lo que trajo el aviso, lo que dejaron los pasos
   anteriores, los **Secretos** (FLOW-F26) y la «Clave de no repetición» de esta llamada.
4. Ajusta los **Segundos de espera** (de 1 a 30) y, si quieres, **Más opciones** (FLOW-F25).
5. **Guardar** y, en **Permisos**, concede «Llamar a» ese servidor.
Entra: el método, la dirección, las cabeceras, el texto que envía y la espera.
Sale: al ejecutarse, la llamada sale cuando la ejecución ya está guardada, nunca dentro de ella; el historial
dice «Llamando a…» con el nombre del servidor y luego «Llamó a…: respondió 201», y los pasos siguientes
pueden leer su «Estado» y su «Texto» (hasta 1 MiB). Si el proceso se cae a mitad, la llamada se repite a los
5 minutos con la **misma** «Clave de no repetición», para que el otro sistema no la haga dos veces.
**Probar** dice «Llamaría a… con esto» con lo que enviaría y los secretos tapados, sin llamar.
Si falla: una dirección que no empieza por «https» y su servidor, con usuario o contraseña, o con datos
antes del nombre, no se guarda («Escribe la dirección a mano…»); tampoco las cabeceras que pone el sistema
(Host, Content-Length…). Al llamar: una dirección de una red privada, del propio servidor o de los datos
internos de la nube no se llama («…está dentro de una red privada, así que no se llamó.»); sin permiso, «…no
le has dejado hacer…»; si responde un error, no contesta a tiempo o no se puede llegar, la ejecución se para
con el motivo y qué hacer, y se puede reanudar (FLOW-F24) o seguir con «Si falla, sigue»; una dirección
privada no se reanuda: hay que cambiar el paso y ejecutarla de nuevo. Mientras el servidor no pueda guardar
secretos (FLOW-F26), una llamada que no usa ninguno se guarda, se prueba y sale igual; la que usa uno se
para antes de llamar («Este servidor no puede usar secretos…»). No sigue
redirecciones. Una ejecución cuya automatización se borra mientras llama se cancela.
Implicados: FLOW-F12, FLOW-F13, FLOW-F16, FLOW-F24, FLOW-F25, FLOW-F26

### FLOW-F28 Preguntar antes a alguien
<!-- origen: old-hub:HUB-F96 old:flows/workflow/editor.md#flows-f18 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. En **Pasos**, pulsa **Preguntar antes a alguien**. Se abre su tarjeta.
2. Escribe **La pregunta** y, si quieres, **Detalles (opcional)**, con datos insertados: se rellenan en el
   momento de preguntar.
3. En **Quién tiene que contestar** elige «Quien lleva el negocio» (de fábrica), «Un responsable» o «Un
   empleado»: «Los responsables la contestan en Automatizaciones, en «Esperan tu respuesta»; quien lleva el
   negocio también puede.».
4. Ajusta **Cuánto esperar la respuesta** (de 1 a 720 horas; de fábrica, 72).
5. En **Si dicen que no**, «Parar la automatización aquí» o «Seguir con los pasos siguientes»; en **Si nadie
   contesta a tiempo**, «Contarlo como un no», «Parar la automatización aquí» o «Seguir con los pasos
   siguientes». Con «Seguir», el aviso explica cómo poner después un «Solo sigue si…» sobre «Aprobada».
6. Pulsa **Guardar**. Este paso no pide permiso.
Entra: la pregunta, sus detalles, a quién, cuánto esperar y qué hacer con un no y con el silencio.
Sale: el paso. Al ejecutarse, la pregunta espera en «Esperan tu respuesta» (FLOW-F29) con su texto ya rellenado y
la ejecución se para ahí (`flow.question.asked`); el historial dice «Preguntó a los responsables; espera una
respuesta hasta el …». Cambiar después la automatización no cambia una pregunta ya hecha. **Probar** dice
«Preguntaría a … y esperaría hasta … horas» con la pregunta rellenada, sin preguntar.
Si falla: una pregunta vacía, o una espera de menos de una hora o de más de 30 días, no se guarda; una
pregunta que nombra un secreto tampoco.
Implicados: FLOW-F13, FLOW-F16, FLOW-F25, FLOW-F29, FLOW-F30

### FLOW-F29 Contestar lo que pregunta una automatización
<!-- origen: old:flows/workflow/bandejas-y-asistente.md#flows-f24 old-hub:HUB-F100 gh:hub#2502 gh:flows#166 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Automatizaciones
Pasos:
1. En **Automatizaciones**, **Esperan tu respuesta** enseña cada pregunta que puedes contestar, la que caduca
   antes primero: de qué automatización viene, la pregunta y sus detalles, «Preguntado a los responsables.
   Quien lleva el negocio también puede contestar.», qué pasa si nadie contesta («Si nadie contesta antes
   del …, cuenta como un no.») y qué hace un no.
2. Si quieres, escribe en **Añadir una nota (opcional)**.
3. Pulsa **Aprobar** o **No**. Sale «Aprobada: la automatización sigue.» o «Contestada que no.» y la tarjeta
   sale de la bandeja.
Entra: la decisión y la nota (por voz: «aprueba la devolución de Ana»), con quién contesta de su sesión.
Sale: la respuesta con quién, cuándo y la nota (`flow.question.answered`). Un sí sigue con los pasos
siguientes, que pueden leer «Aprobada», «Nota» y «Contestada por»; un no hace lo que dice el paso: para la
ejecución («Cancelada: Marta contestó que no a «…».») o sigue. El historial dice «Marta contestó que sí:
«…»». Quien lleva el negocio ve todas; un responsable, las de los responsables y los empleados; un
empleado, las de los empleados.
Si falla: la tarjeta se queda con el motivo: «Alguien ya contestó a esta. No se ha hecho nada dos veces.»
(dos personas a la vez: gana una sola), «Demasiado tarde: nadie la contestó a tiempo y se cerró. No se ha
hecho nada.», «Esta pregunta se le hizo a otra persona: tú no puedes contestarla.»; con la automatización
en pausa, un sí (o un no que sigue) se niega en tu idioma con «Esta automatización está en pausa:
enciéndela para ejecutarla.» y la pregunta espera; un no que para la ejecución sí se acepta. Borrar la
automatización cancela sus preguntas.
Implicados: FLOW-F16, FLOW-F28, FLOW-F30

### FLOW-F30 Cerrar lo que nadie contestó a tiempo
<!-- origen: old-hub:HUB-F101 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada minuto el Hub repasa las preguntas cuyo plazo ha vencido.
2. Las cierra como caducadas y hace lo que dice su paso: contarlo como un no (lo que haga un no), parar o
   seguir con los pasos siguientes.
Entra: las preguntas que esperan, con su plazo.
Sale: la pregunta caducada (`flow.question.expired`) y su ejecución cancelada («Cancelada: nadie contestó
«…» a tiempo.») o seguida, con «Caducado» para un «Solo sigue si…» posterior; el historial dice «Nadie contestó
a tiempo». Un segundo repaso no vuelve a cerrar nada.
Si falla: una pregunta vencida que aún no ha cerrado el repaso ya no se puede contestar; si la automatización
está en pausa y tocaba seguir, la ejecución se cancela («Cancelada: la automatización se puso en pausa
mientras esperaba.»). Si alguien contesta justo cuando la cierra el repaso, gana uno solo.
Implicados: FLOW-F16, FLOW-F28, FLOW-F29

### FLOW-F31 Mandar un mensaje a un cliente
<!-- origen: old-hub:HUB-F93 old:flows/workflow/editor.md#flows-f15 gh:whatsapp_inbox#273 -->
Estado: parcial — el Hub todavía no puede mandarle un mensaje a un cliente: la Bandeja de WhatsApp declara su envío (WHATSAPP_INBOX-F32, F33) pero espera la puerta del SaaS hacia Meta, y no hay correo saliente para clientes; el paso no se ofrece hasta que exista
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Abre una automatización y mira los botones para añadir de **Pasos**.
2. El paso **Enviar un mensaje** todavía no aparece entre ellos: una automatización aún no puede escribir a
   un cliente.
Entra: —
Sale: nada todavía. Cuando el envío exista, el paso mandará un WhatsApp (una plantilla aprobada) o un correo
a un cliente, respetando lo que el cliente haya aceptado recibir, con su permiso como cualquier acción.
Si falla: no aplica mientras el paso no se ofrezca.
Implicados: FLOW-F11, FLOW-F12

### FLOW-F32 Poner una foto, un vídeo o un PDF en la cabecera de un WhatsApp
<!-- origen: old-hub:HUB-F112 -->
Estado: parcial — depende de FLOW-F31 y además de un sitio donde guardar los archivos y de plantillas de WhatsApp con cabecera, que el Hub todavía no tiene
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Abre una automatización y mira los botones para añadir de **Pasos**.
2. Sin el paso **Enviar un mensaje** (FLOW-F31) no hay cabecera que rellenar.
Entra: —
Sale: nada todavía.
Si falla: no aplica mientras el paso no se ofrezca.
Implicados: FLOW-F31

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y los mismos permisos. Una automatización se nombra por su id o
por su nombre (o parte de él); si un nombre vale para varias, se dice cuáles (`flow.ambiguous_flow`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las automatizaciones, con búsqueda, filtros, orden y su última ejecución, en páginas de hasta 100 (en vivo) | ver | F02 | `flow.flow.list` |
| Una automatización, con los permisos que necesita y los que le faltan (en vivo) | ver | F09–F16 | `flow.flow.detail` |
| Las ejecuciones de una automatización, de 20 en 20, y cuántas fallaron (en vivo) | ver | F16 | `flow.run.list` |
| Los borradores pendientes del asistente (en vivo) | ver | F18, F19 | `flow.draft.list` |
| Los avisos y las acciones de las apps activas, con los datos que pide cada acción | ver | F10, F11 | `flow.catalog.read` |
| El último aviso real de un tipo, con sus datos | gestionar | F11, F13 | `flow.event.sample` |
| Lo que haría una automatización con el último aviso real, sin ejecutar nada | gestionar | F13 | `flow.flow.test` |
| Cuántas automatizaciones de un aviso pueden hacer una acción, cuántas encendidas y cuántas a medias | ver | F20 | `flow.flow.status` |
| Los nombres de los secretos del negocio, nunca su valor, y si el servidor puede guardarlos (en vivo) | gestionar | F26 | `flow.secret.list` |
| Las preguntas que espera contestar esta persona, las que caducan antes primero, hasta 100 (en vivo) | contestar | F29 | `flow.question.list` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea una automatización (de cero, de una tarjeta o de un borrador), en pausa y sin permisos | gestionar | F04, F09, F18 | `flow.flow.create` |
| Cambia el nombre, el disparador o los pasos (el interruptor es `set_enabled`) | gestionar | F10, F11, F14 | `flow.flow.update` |
| Enciende o pausa | gestionar | F03, F14 | `flow.flow.set_enabled` |
| Hace una copia en pausa y sin permisos | gestionar | F06 | `flow.flow.duplicate` |
| Borra (su historial se queda) | gestionar | F07 | `flow.flow.delete` |
| Fija la lista entera de acciones y consultas que puede hacer | gestionar | F12 | `flow.flow.grant` |
| La ejecuta ahora | gestionar | F15 | `flow.flow.run` |
| Deja un borrador del asistente | gestionar | F17 | `flow.draft.propose` |
| Descarta un borrador | gestionar | F19 | `flow.draft.dismiss` |
| Arranca las automatizaciones de un aviso | solo la plataforma | F21 | `flow.run.react` |
| Arranca las de horario o fecha que toca | solo la plataforma | F22 | `flow.schedule.fire_due` |
| Sigue las ejecuciones cuya espera terminó | solo la plataforma | F23 | `flow.run.resume_due` |
| Reanuda una ejecución parada por un error en el paso que falló | gestionar | F24 | `flow.run.retry` |
| Guarda (o cambia) un secreto, sellado | gestionar | F26 | `flow.secret.set` |
| Borra un secreto | gestionar | F26 | `flow.secret.delete` |
| Toma la llamada de una ejecución para hacerla | solo la plataforma | F27 | `flow.run.claim_call` |
| Apunta cómo acabó la llamada y sigue la ejecución | solo la plataforma | F27 | `flow.run.record_call` |
| Contesta sí o no, con una nota, a una pregunta de una automatización | contestar (su rol) | F29 | `flow.question.answer` |
| Cierra las preguntas que nadie contestó a tiempo | solo la plataforma | F30 | `flow.question.expire_due` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Automatización nueva | Crear o copiar | `id` | `flow.flow.created` |
| Automatización cambiada | Guardar nombre, disparador o pasos | `id`, `version` | `flow.flow.updated` |
| Encendida | Encenderla | `id` | `flow.flow.enabled` |
| En pausa | Pausarla | `id` | `flow.flow.paused` |
| Permisos cambiados | Conceder o retirar | `id` | `flow.flow.granted` |
| Borrada | Borrarla | `id` | `flow.flow.deleted` |
| Ejecución empezada | Arranca una ejecución | `id`, `flow_id` | `flow.run.started` |
| Ejecución en espera | Llega a un «Esperar» | `id`, `flow_id`, `resume_at` | `flow.run.parked` |
| Ejecución reanudada | Termina la espera o se reanuda desde el paso que falló | `id`, `flow_id` | `flow.run.resumed` |
| Ejecución terminada | Termina bien, por una condición, por un error o cancelada | `id`, `flow_id`, `status` | `flow.run.finished` |
| Borrador propuesto | El asistente deja un borrador | `id` | `flow.draft.proposed` |
| Borrador usado | Se crea la automatización desde él | `id`, `flow_id` | `flow.draft.used` |
| Borrador descartado | Se descarta | `id` | `flow.draft.dismissed` |
| Secreto guardado | Guardar o cambiar un secreto | `id` | `flow.secret.saved` |
| Secreto borrado | Borrarlo | `id` | `flow.secret.deleted` |
| Pregunta hecha | Una ejecución llega a «Preguntar antes a alguien» | `id`, `run_id`, `flow_id` | `flow.question.asked` |
| Pregunta contestada | Alguien contesta sí o no | `id`, `run_id` | `flow.question.answered` |
| Pregunta caducada | Nadie la contestó a tiempo | `id`, `run_id` | `flow.question.expired` |

Los avisos llevan ids, nunca nombres ni contenidos.

### A qué reacciona y lo que necesita de otras apps
- **A todos los avisos de las apps activas** (FLOW-F21), salvo los suyos: es la única app que escucha
  cualquier aviso. Hace las acciones y consultas de otras apps **por su nombre** (`task.task.create`),
  con sus reglas y sus mensajes, nunca tocando sus datos; por eso no necesita ninguna app
  (`requires` vacío): una automatización que nombra una app apagada falla con su motivo, visible.
- De la plataforma: la zona horaria del negocio (los horarios) y los avisos del outbox (el último de un
  tipo, para Probar y los ejemplos).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver las automatizaciones, sus ejecuciones y los borradores | sí | sí | no | no | `flow.view` |
| Crear, cambiar, encender, conceder, ejecutar, borrar; probar; decidir borradores; contestar lo que se pregunta a quien lleva el negocio | sí | sí | no | no | `flow.manage` |
| Ver «Esperan tu respuesta» y contestar lo que se pregunta a los empleados | sí | sí | sí | sí | `flow.answer` |
| Contestar lo que se pregunta a los responsables | sí | sí | sí | no | `flow.answer_manager` |

## Para quien lo mantiene

- **Anatomía**: `apps.py`, `models.py`, `document.py` (el documento de una automatización: rutas de
  datos, plantillas `{{…}}`, condiciones, horarios y permisos que pide; puro, sin base de datos),
  `schemas.py`, `queries.py`, `services.py` (con el motor), `events.py`, `live.py`, `api.py`, `admin.py`,
  `locale/`, `frontend/` y un `tests/test_<fichero>.py` por fichero, más
  `tests/test_integration_apps.py` (Clientes, Ventas y Tareas de verdad) y `tests/test_concurrency.py`.
- **Modelos**: `Flow` (nombre, encendida, disparador aplanado —`trigger_kind`, `trigger_event`,
  `trigger_filter`, `schedule`, `run_at`, `next_fire_at`—, `steps`, `grants`, `version`, `language`,
  `search_text`, borrado lógico `deleted_at`), `FlowRun` (versión y copia de los pasos con que empezó,
  `trigger_key` único por automatización, `input`, `status`, `step_index`, `log`, `outputs`, error,
  `resume_at`, `chain`), `Draft`, `Secret` (nombre único y valor sellado, FLOW-F26) y `Question` (FLOW-F28:
  ejecución y paso únicos, texto ya rellenado, `role`, `on_no`, `on_timeout`, `expires_at`, `status`, quién
  y cuándo contestó y la nota). UUIDv7, sin `hub_id`.
- **El documento**: `trigger` = `{kind: event, event, filter}` · `{kind: schedule, every: day|week|month,
  weekday 0–6 (lunes 0), day 1–31, time "HH:MM"}` · `{kind: at, at}` · `{kind: manual}`; `steps` = lista
  de `{id, kind: command|query|condition|delay|http, …}`; `http` = `{method, url, headers, body, timeout}`
  (FLOW-F27), cuyos textos pueden leer además `secret.<NOMBRE>` y `run.idempotency_key` (ningún otro paso). Un valor es un literal, una **ruta**
  (`input.total`, `steps.s1.id`: conserva el tipo) o un texto con `{{ruta}}` (siempre texto). Raíces:
  `input` (lo que trajo el aviso o la ejecución a mano) y `steps.<id>` de un paso anterior. Sin índices
  de lista. Condición: `{ruta: {eq|neq|in|exists|contains|gt|gte|lt|lte: valor}}`, todas a la vez; un
  dato que no está nunca cumple salvo `exists: false`. Todo paso salvo `condition` admite `run_if` (una
  condición: si no se cumple, se salta, queda `skipped` en el log y, en una acción o consulta,
  `steps.<id>.skipped`), y `command`/`query` admiten `on_error: continue` (el fallo queda en el log con
  `continued`, deja `steps.<id>.failed` y `error_code`/`error_message`, y la ejecución sigue). Sin ellos el
  paso se guarda como antes (`exclude_none`); un `run_if` ilegible para con `flow.run_if_unreadable`, que no
  se reanuda (FLOW-F25).
- **Catálogo sin inventar nombres**: los avisos son los `events.ALL` de las apps activas (todas declaran
  el suyo); las acciones y consultas, las operaciones registradas de las apps activas cuyo permiso
  declara su app (las de «solo la plataforma» quedan fuera) **y que no necesitan a una persona delante**:
  toda operación con `ai.risk == "high"` (anular, devolver, borrar, enviar a Hacienda, `go_live`…) queda
  fuera y se rechaza al guardar, al conceder y al ejecutar con el código `flow.high_risk` (revisión
  2026-10-15). En la fase 1 «activas» son las instaladas (como `base.session.me`); la fase 2 lo cambia por
  la foto del SaaS en `queries.active_apps`.
- **Con qué actúa**: el motor solo llama a las operaciones de la lista `grants`, que fija un propietario
  o administrador, que se valida entera contra el catálogo y que solo contiene lo que quien la concede
  puede hacer él mismo. Cada paso corre con el contexto `flow_run:<id>` (el actor queda en el outbox de
  lo que haga), **solo con el permiso de su propia operación y los de lectura de su app**
  (`<app>.view…`, para contestar con lo que hizo), nunca con todos: los controles internos de la
  operación siguen valiendo (el «no elevation» del motor viejo); en el idioma de quien la guardó.
- **Transacciones**: arrancar una ejecución es **una** operación (`flow.run.react`, `fire_due`,
  `resume_due`, `flow.flow.run`); cada paso es una operación anidada (un *savepoint*): un paso que falla
  no deja nada suyo y los anteriores se quedan. La ejecución, su historial y sus avisos se guardan en la
  misma transacción. Un error inesperado de un paso se registra (`flow.step_crashed`) y queda en el log.
- **Una sola ejecución por aviso**: se bloquea la fila de la automatización (`select_for_update`), se
  mira si ya hay ejecución con ese `trigger_key` (el id del aviso del outbox) y la restricción única
  `(flow, trigger_key)` lo respalda; dos entregas a la vez dan una ejecución.
- **Una automatización borrada mientras se busca** (2026-10-17): `resolve_flow` la lee **una** vez por su
  id, siempre entre las no borradas: bloqueada en las escrituras y con su última ejecución en el detalle.
  Un borrado confirmado a la vez (el «Borrar» del negocio o el del admin) da lo que se leyó o «no existe»
  (404), nunca un 500 ni un cambio, una copia o una ejecución sobre la ya borrada; buscada por su nombre y
  borrada entre el nombre y la lectura, «no existe». Lo prueban los casos de borrado a mitad de
  `tests/test_concurrency.py`.
- **Sin cadenas infinitas**: un aviso hecho por un paso lleva el actor `flow_run:<id>`; la ejecución que
  arranca hereda su cadena. Si la automatización ya está en la cadena (se dispararía a sí misma) o la
  cadena pasa de **8** automatizaciones (`MAX_CHAIN`), no se ejecuta ningún paso y queda una ejecución
  fallida con `flow.loop_stopped`, visible en Historial. **Límite**: la cadena solo sigue los avisos que
  graba el propio paso; si el aviso pasa antes por la reacción de otra app (que corre como el sistema),
  los avisos de esa reacción llevan `system` y la cadena empieza de nuevo. Heredarla pide que el relay del
  outbox (fase 2, en `base/`) ejecute cada reacción con el actor del aviso que entrega; no se hace desde
  esta app ni tocando `packages/`.
- **Lo que leyeron los pasos** (`outputs`: la ficha de un cliente…) solo se guarda mientras la ejecución
  puede seguir: esperando, o parada por un error durante `RESUME_DAYS` (7) para reanudarla (FLOW-F24);
  al terminar bien, por una condición o cancelada se vacía, y la poda de cada hora vacía la de un fallo de
  más de 7 días, así que un historial terminado no guarda copias de datos de otras apps. Lo que trajo el
  aviso (`input`) sí se queda con la ejecución.
- **Reanudar** (`flow.run.retry`, FLOW-F24): bloquea la automatización y después la ejecución (el mismo
  orden que toda escritura) y solo sigue si está `failed` en un paso (su última entrada del log es
  `failed` en `step_index`), guarda lo que dejó cada paso anterior que deja algo, tiene menos de 7 días y la
  automatización está encendida; nunca tras `flow.loop_stopped`, `flow.filter_unreadable`,
  `flow.condition_unreadable` ni `flow.high_risk`. Sigue con su `definition` (la versión con la que
  empezó) y deja en el log `resumed` con quién. Dos a la vez: la segunda espera el bloqueo y ve que ya no
  está `failed`.
- **Secretos** (`vault.py`, FLOW-F26): Fernet de `cryptography` con la clave `FLOW_SECRETS_KEY` del
  entorno (Secrets Manager en AWS; nunca en el código); sin ella, `flow.secret.list` dice `available: false`
  y guardar da `flow.secrets_key_missing`. El valor entra como `SecretStr` (un 422 nunca lo repite), solo se
  abre al hacer la llamada y se tapa (`vault.mask`) en todo lo que se guarda o se enseña de ella: log,
  errores, lo que respondió y **Probar**. Ni la API, ni `live.py`, ni el admin (solo ver el nombre y borrar)
  lo devuelven. En la fase 1, como toda tabla de `flow`, los secretos se comparten entre los negocios de
  la misma base de datos hasta la BD por hub de la fase 2.
- **Llamadas** (`http.py`, FLOW-F27): solo `https` con el nombre del servidor escrito a mano (es el permiso,
  `http:https://host`); el nombre se resuelve **una** vez, se rechaza toda dirección que no sea pública
  (privada, del propio equipo, de enlace local —metadatos de la nube—, multicast o reservada) y se conecta
  a esa misma IP con su nombre en TLS (sin cambio de DNS entre medias); sin redirecciones ni proxies del
  entorno, con tiempo total y como mucho 1 MiB de respuesta. El paso deja la ejecución en `calling`; la
  llamada sale tras el COMMIT (`dispatch_call`, sin transacción ni bloqueo alrededor):
  `flow.run.claim_call` la toma con un plazo de `CALL_LEASE_MINUTES` (5) en `resume_at` y
  `flow.run.record_call` apunta cómo acabó y sigue. Si el proceso se cae, `resume_due` la vuelve a lanzar
  al vencer el plazo con la misma `Idempotency-Key` (uuid5 de ejecución y paso). Los tests llaman a un
  servidor HTTPS local de verdad (`tests/local_https.py`), nunca a un `patch` del cliente.
- **Preguntas** (FLOW-F28 a F30): el paso `ask` deja una `Question` con su texto rellenado con `document.fill`
  y pone la ejecución en `asking` con `resume_at` = el plazo. Contestar (`flow.question.answer`) bloquea la
  automatización, después la ejecución y después la pregunta (el mismo orden que toda escritura) y solo
  decide una `pending` dentro de plazo de una ejecución `asking`; quién contesta lo dice su permiso
  (`ROLE_PERMISSION`: '' → `flow.manage`, `manager` → `flow.answer_manager`, `employee` → `flow.answer`, y
  `flow.manage` siempre). El rechazo de una automatización en pausa sale en el idioma de quien contesta
  (flows#166). `flow.question.expire_due` (cada minuto) toma las ejecuciones `asking` vencidas con `SKIP
  LOCKED` y luego su pregunta; nunca coge la automatización, así que no se cruza con quien contesta. Un paso
  posterior lee `steps.<id>.approved`, `.expired`, `.note` y `.answered_by`. Borrar la automatización cancela
  sus ejecuciones `asking` y sus preguntas. Este paso no pide permiso: no hace nada fuera de la app.
- **Retención** (hub#699, la del Hub viejo: 90 días fijos, sin ajuste por hub): la tarea programada
  `flow.run.prune` (cada hora, en el minuto 17) borra como mucho `PRUNE_BATCH` (500) ejecuciones
  terminadas (`succeeded`, `stopped`, `failed`, `cancelled`) cuya hora de fin —o de inicio, si no la
  tienen— pasa de `HISTORY_DAYS` (90), las más viejas primero, y deja en el log cuántas borró. Una
  ejecución que espera o está en marcha no caduca. No deja aviso: borrar historial no es un hecho del
  negocio, y la red de seguridad de 300 s de las consultas vivas pone la lista al día.
- **Horarios**: `python-dateutil` (`rrule`, ya dependencia del Hub), en la zona del negocio; `fire_due`
  barre con `SKIP LOCKED`, arranca una vez aunque se hayan perdido varias horas y avanza
  `next_fire_at` desde ahora en la misma transacción.
- **Reintentos**: declarados y no ejecutados en la fase 1. Una ejecución fallida no se reintenta sola;
  el relay del outbox (fase 2) reintentará la **entrega** de un aviso cuya reacción no llegó a
  confirmarse, y la idempotencia por `trigger_key` hace que un reintento no ejecute dos veces.
- **Fase 1**: el worker (`run_worker`) corre cada minuto las dos tareas programadas (`fire_due`,
  `resume_due`) como el sistema, en un único ámbito fijo (`WORKER_SCOPE_SLUG`); como en la fase 1 todos
  los hubs comparten tablas, ve todas las automatizaciones (FLOW-F22 y F23, probado pasando por
  `base.scheduler.run_due`). **No** hay relay del outbox: nada llama a `flow.run.react` fuera de los tests
  (FLOW-F21 parcial). El motor se prueba entregando a `events.react` (o `events.deliver`) avisos
  **reales** del outbox, hechos por las operaciones reales de otras apps. El relay debe entregar a
  `flow` **todos** los avisos (`REACTIONS = {"*": "flow.run.react"}`), con su id y su actor.
- **Lo que ya no se puede leer** (hub#1766): un «Solo cuando…» o un «Solo sigue si…» guardado con una
  forma que el motor no entiende (escrito en crudo desde el admin o por una versión anterior) nunca se
  evalúa como «no se cumple»: la ejecución se para con `flow.filter_unreadable` o
  `flow.condition_unreadable` y las demás automatizaciones del aviso siguen (`document.readable`).
- **Asistente**: toda operación declara `ai={"description"…}` (`risk` solo en las acciones; `high` al
  encender o pausar, conceder, ejecutar y borrar) y todo campo de entrada lleva `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre `Flow`, `FlowRun`, `Draft` y `Question`; de `Secret`, solo
  ver el nombre y borrar (un valor no se escribe ni se lee desde el admin). Una escritura cruda del admin no
  deja aviso.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/flow/automations` (lista, borradores y galería; `?template=` abre una
  tarjeta), `/flow/automations/new` (`?draft=` carga un borrador), `/flow/automations/:id` (`?tab=`) y
  `/flow/guide`.
- La lista es `DataTable` en servidor con `useLiveList`/`useServerTable`, casillas y acciones de fila;
  el editor es la columna del producto actual hecha en CSS propio (sin librería de lienzos: no hay
  nodos), con `ion-reorder-group` para ordenar con el dedo.
- Las palabras de avisos y acciones salen de `frontend/lib/phrasing.ts`: frases escritas a mano para
  las conocidas y compuestas (app + palabras) para las demás, en `en` y `es`.
- Los iconos son los registrados en la shell; los deseados esperan en `UI-REQUESTS.md`.

## Lo que NO hace, a propósito

- **No tiene bifurcaciones ni bucles**: una automatización es una columna; un «Solo sigue si…» que no
  se cumple la termina. Dos desenlaces son dos automatizaciones.
- **No es un lienzo de nodos**.
- **No cuenta hacia atrás desde una fecha del aviso** («el día antes de la cita»): una espera cuenta
  desde el paso anterior.
- **El asistente no enciende ni concede sin confirmarlo**: deja borradores, y encender, pausar, conceder,
  ejecutar y borrar son acciones `risk: "high"` que el asistente confirma con la persona antes.
- **No automatiza lo que necesita a una persona delante**: anular o devolver una venta, borrar los datos
  de un cliente, enviar o anular registros en Hacienda… no salen en la lista de acciones.
- **No ejecuta en pausa**: para eso está Probar.
- **No reintenta sola** una ejecución que falló: se reanuda a mano desde el paso que falló (FLOW-F24).

## Cambios frente al producto actual

- **El motor vive en la app**: antes era del núcleo del hub y la pantalla llamaba a su API; ahora
  guardar, encender, ejecutar y el historial son operaciones de esta app, con los mismos permisos por
  la pantalla, el asistente y la API.
- **Las acciones se eligen de una lista** (con buscador y en palabras), con los datos que pide cada
  una; antes se escribía el nombre técnico a mano y un nombre que no existía fallaba al ejecutarse.
  Ahora se rechaza al guardar.
- **Ejecutar ahora** existe (FLOW-F15; antes «no hecho»), solo con la automatización encendida.
- **Nada que necesite a una persona delante** (anular, devolver, borrar, enviar a Hacienda) se puede
  automatizar, y **cada paso actúa solo con el permiso de su acción** (y las lecturas de su app), como el
  «no elevation» del motor viejo; antes la lista de permisos admitía cualquier acción.
- **El filtro del disparador se ve y se edita** («Solo cuando…»; antes se conservaba sin verse).
- **Probar** valida también los datos contra la acción («Se lo rechazarían: …»).
- **Revisar un borrador y crearlo es una sola operación**: ya no se puede crear dos veces.
- **Volver con cambios sin guardar pregunta** antes de perderlos.
- **El historial pagina** de 20 en 20 con **Ver más** (antes, solo las 20 últimas) y la fila de la
  lista enseña la última ejecución.
- **Horarios**: todos los días, todas las semanas o todos los meses a una hora (antes, una línea cron;
  los horarios que la pantalla no sabía dibujar ya no existen).
- **Consultar algo** trae como mucho 100 filas (el tope de toda lista del Hub; antes 200).
- **Nombres**: `flow.*` en vez de `flows.*`; `flow.draft.propose`, `flow.draft.list`,
  `flow.draft.dismiss` (antes `flows.drafts.propose`, `.list` y `.resolve`), `flow.flow.status` (antes
  `flows.automations.status`); permisos `flow.view` y `flow.manage` (antes `flows.view_flow` y
  `flows.manage_flow`). Las rutas de datos empiezan por `input.` (antes también `event.` en el filtro).

### Paridad: acciones

| Producto actual | Aquí | Motivo si cambia |
|---|---|---|
| `flows.drafts.propose` | `flow.draft.propose` | — |
| `flows.drafts.resolve` (`used`) | dentro de `flow.flow.create` con `draft_id` | una sola operación: no se crea dos veces |
| `flows.drafts.resolve` (`dismissed`) | `flow.draft.dismiss` | — |
| `POST /api/hub/flows` | `flow.flow.create` | el motor es de la app |
| `PUT /api/hub/flows/{id}` | `flow.flow.update`, `flow.flow.set_enabled` | — |
| `DELETE /api/hub/flows/{id}` | `flow.flow.delete` | — |
| copia en la pantalla | `flow.flow.duplicate` | ahora también por el asistente y la API |
| `PUT /api/hub/flows/{id}/grants` | `flow.flow.grant` | permisos por acción o consulta; sin límites de campo (ver «Qué queda fuera») |
| `POST /api/hub/flows/{id}/run` | `flow.flow.run` | ahora con botón |
| motor del núcleo (eventos, cron, `at`, esperas) | `flow.run.react`, `flow.schedule.fire_due`, `flow.run.resume_due` | — |
| `…/flows/secrets` | `flow.secret.list`, `flow.secret.set`, `flow.secret.delete` | solo el nombre: el valor no se vuelve a leer nunca |
| paso `http` del motor | paso «Llamar a otro sistema» (`flow.run.claim_call`, `flow.run.record_call`) | la llamada sale tras guardar la ejecución, con su clave de no repetición |
| `…/approvals` (preguntas) | `flow.question.list`, `flow.question.answer`, `flow.question.expire_due` | el rol al que se pregunta sí decide quién contesta |
| `…/approvals` (propuestas del asistente), `…/events/dead*` | — | fuera (ver «Qué queda fuera») |

### Paridad: consultas

| Producto actual | Aquí | Motivo si cambia |
|---|---|---|
| `flows.drafts.list` | `flow.draft.list` | — |
| `flows.automations.status` | `flow.flow.status` | — |
| `GET /api/hub/flows` | `flow.flow.list` | pagina (≤ 100), busca y filtra en el servidor |
| `GET /api/hub/flows/{id}` | `flow.flow.detail` | — |
| `GET /api/hub/flows/{id}/runs` | `flow.run.list` | pagina |
| `GET /api/hub/events` | `flow.catalog.read` | también las acciones y consultas |
| `GET /api/hub/events/shape` | `flow.event.sample` | el último aviso real, no muestras por campo |
| «Probar» calculado en la pantalla | `flow.flow.test` | en el servidor, que valida contra la acción |

### Paridad: páginas

| Producto actual | Aquí | Motivo si cambia |
|---|---|---|
| Automatizaciones (lista, borradores, galería) | `/flow/automations` | la lista es la `DataTable` del Hub (mismos controles: buscador, filtros, orden, casillas, interruptor, copiar, borrar) |
| Editor (Pasos, Probar, Permisos, Historial) | `/flow/automations/:id` y `/new` | la misma columna; los pasos de mensaje y de asistente, fuera |
| Guía | `/flow/guide` | — |
| Bandeja «Esperan tu respuesta» | «Esperan tu respuesta», arriba de `/flow/automations` | solo preguntas: las propuestas del asistente llegan con él |
| Bandeja «Necesita tu atención» (eventos caídos) | — | fuera: es la administración del outbox, de la plataforma |

## Contradicciones señaladas (no resueltas aquí)

- **PLAN-HUB** deja los flows para «tarde» (tabla de rutas del hub y §8); la decisión de Ioan del
  2026-10-15 los porta ya: hace falta una ronda nueva en PLAN-HUB que lo diga.
- **El asistente como actor** de FLOW-F03, F12 y F15: es coherente con «no enciende ni concede sin
  confirmarlo» porque `create`/`update` ya no llevan el interruptor y `set_enabled`, `grant`, `run` y
  `delete` son `risk: "high"` (el asistente confirma antes).
- **`@operation` hoy no aplica la app activa** (fase 1): el catálogo de esta app filtra por las apps
  instaladas y el motor comprueba que la operación sigue en él al ejecutar; la comprobación de la
  plataforma llega con la fase 2.

## Qué queda fuera

- **Guardar secretos en los servidores de ERPlora** (FLOW-F26, parcial): la caja, el sellado y su uso en
  una llamada están hechos y probados, pero producción y pre todavía no tienen su clave de cifrado; hasta
  que se active, la caja lo dice al abrirse y las llamadas sin secretos funcionan igual.
- **Paso «Enviar un mensaje»** y la cabecera multimedia de un WhatsApp (FLOW-F31, FLOW-F32, parciales):
  dependen del envío de WhatsApp y de correo a clientes, que todavía no existe en el Hub ni en el SaaS.
- **Paso «Pedírselo al asistente»** y las propuestas del asistente en **Esperan tu respuesta**: dependen del
  asistente en el Hub (parte 3 de la migración de esta app).
- **«Necesita tu atención»** (eventos que no se entregaron): es la administración del outbox (PLAN-HUB
  bloque 7), de la plataforma, con el relay de la fase 2.
- **Recetas que traen otras apps** («Viene con …», restaurar la de fábrica) y la reparación de las de
  WhatsApp: ninguna app del Hub publica recetas todavía; la tarjeta «Contestar los WhatsApp» vuelve
  cuando la Bandeja de WhatsApp declare su aviso.
- **Límites en un permiso** («solo con este cliente»): se concede la acción entera.
- **Borrar al momento lo que leyó una ejecución que espera** cuando se borran los datos de un cliente
  (pm#637): una ejecución terminada no guarda nada de lo que leyeron sus pasos, pero una que espera
  conserva la ficha que leyó hasta que despierta (como mucho 30 días). Borrarla en el acto pide
  reaccionar al aviso del borrado, que llega con el relay del outbox (fase 2).
