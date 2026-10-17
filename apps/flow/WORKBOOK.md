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
**Esperar** (minutos, horas o días).

Solo la usan el **propietario** y el **administrador**: una automatización actúa en nombre del negocio
sin nadie delante. El responsable y el empleado no la ven.

El asistente la usa por voz o por texto con la sesión de quien habla: «crea un flujo que al completar
una venta de más de 100 € me cree una tarea» (lo deja como **borrador**, apagado, para que lo revises),
«activa la automatización de bienvenida», «pausa la de la caja», «¿qué automatizaciones tengo?»,
«ejecuta ahora la revisión semanal», «¿por qué falló la de bienvenida?».

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
  despliegan al tocarlas), y los botones para añadir: **Hacer algo**, **Consultar algo**, **Solo sigue
  si…** y **Esperar**. Sin pasos: «Todavía no hay pasos. Añade lo primero que debe hacer esta
  automatización.»
- **Probar**: lo que haría con lo último que pasó, sin hacer nada (FLOW-F13).
- **Permisos**: «Una automatización se ejecuta con sus propios permisos, nunca con los tuyos. Nada de
  lo de abajo ocurre hasta que lo autorices.», las filas «Pendiente de tu permiso» o «Autorizado» y
  **Autorizar todo lo que necesita** (FLOW-F12).
- **Historial**: las ejecuciones, las más recientes primero y las paradas por error arriba (FLOW-F16).

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
| FLOW-F17 | Pedirle al asistente una automatización | hecho |
| FLOW-F18 | Revisar un borrador del asistente y crearlo | hecho |
| FLOW-F19 | Descartar un borrador del asistente | hecho |
| FLOW-F20 | Otra app pregunta si una automatización ya está montada | hecho |
| FLOW-F21 | Cuando pasa algo en el negocio, la automatización arranca | hecho — el motor está; la entrega del aviso la hace el relay del outbox (fase 2) |
| FLOW-F22 | Cuando llega la hora, la automatización arranca | hecho — la tarea programada está declarada; la corre el worker (fase 2) |
| FLOW-F23 | Cuando acaba una espera, la automatización sigue | hecho — la tarea programada está declarada; la corre el worker (fase 2) |

### FLOW-F01 Entrar en Automatizaciones
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. Abre **Automatizaciones** en el menú.
2. Salen los borradores del asistente (si hay), tus automatizaciones (si hay) y la galería.
Entra: la sesión.
Sale: nada guardado.
Si falla: sin permiso, «No tienes permiso»; con la app apagada, «Esta app no está activa en este
negocio»; cualquier otro fallo, en rojo con **Reintentar**.

### FLOW-F02 Ver, buscar y ordenar las automatizaciones
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

### FLOW-F03 Encender o pausar desde la lista, una o varias
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

### FLOW-F04 Crear una automatización desde una tarjeta de la galería
Estado: hecho (pantalla; crea por `flow.flow.create`)
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
   el primer botón es **Verla**; **Usar esta** sigue disponible y crea una segunda.
Entra: las diez tarjetas: siete de «Cualquier negocio», dos de «Peluquería y estética» y una de «Bares
y restaurantes». Una tarjeta se esconde si falta una app de las que usa, y debajo de la galería se dice
cuál.
Sale: una automatización nueva, **en pausa y sin permisos**, con el nombre y los valores de la tarjeta
(esperar un día, 100,00 €, seis personas…).
Si falla: el mensaje en rojo dentro de la tarjeta; no se crea nada.

Las tarjetas:

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
Estado: hecho (pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. Un enlace a `/flow/automations?template=<tarjeta>` abre esa tarjeta de la galería y la trae a la
   vista.
2. Un enlace a una tarjeta que no existe o está escondida enseña la galería sin abrir nada.
Sale: nada guardado.

### FLOW-F06 Hacer una copia
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. En la fila, pulsa **Hacer una copia**.
2. Sale «Copia de …» (o «Copia de … (2)») en la lista, en pausa, y el aviso «Copiada, y la copia está en
   pausa. No lleva ninguno de los permisos de la original: concédele lo que necesite antes de
   encenderla.».
Sale: una automatización nueva con los mismos pasos, en pausa, sin permisos y sin historial
(`flow.flow.created`).
Si falla: el mensaje en rojo arriba; no se crea nada.

### FLOW-F07 Borrar una automatización
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Automatizaciones
Pasos:
1. En la fila, pulsa **Borrar**.
2. Confirma: «¿Borrar «…»? Esto no se puede deshacer.» con **Sí, bórrala** o **Déjala**.
Sale: la automatización deja de arrancar al momento y sale de la lista; lo que esperaba se cancela al
momento; su historial se conserva (`flow.flow.deleted`).
Si falla: el mensaje en rojo arriba; la fila sigue.

### FLOW-F08 Leer la guía
Estado: hecho (pantalla)
Actor: propietario, administrador
Pantalla: Guía
Pasos:
1. En la galería, pulsa **¿Cómo funciona esto?**.
2. Lee los cinco apartados; **Volver a las automatizaciones** regresa.
Entra: nada; los textos van dentro de la app.

### FLOW-F09 Crear una automatización desde cero
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
Sale: una automatización nueva, en pausa salvo que se haya encendido el interruptor antes de guardar, y
sin permisos (`flow.flow.created`). Sin nombre se guarda como «Automatización sin nombre».
Si falla: lo que no encaja, en rojo y junto al paso que lo tiene («Elige qué tiene que hacer este
paso.», «Este aviso no existe en tu negocio.», «Esa fecha y hora ya ha pasado.»…); no se guarda nada.

### FLOW-F10 Elegir cuándo arranca
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Toca la tarjeta «Cuando pase esto…» y elige:
   - **Pasa algo**: en «Elige qué pasa», los avisos de las apps activas del negocio, dichos en palabras
     («se cobra una venta», «se crea una ficha de cliente», «una cita se marca como no vino»…) y con
     buscador. Debajo, **Solo cuando…**: condiciones sobre los datos del aviso («el total es mayor que
     10000»); sin ellas arranca con cada aviso.
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

### FLOW-F11 Añadir, ordenar y rellenar los pasos
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
     «Valor», con **Añadir una condición**. Si no se cumplen todas, la automatización termina ahí sin
     error.
   - **Esperar**: «Cuánto» y la unidad (minutos, horas o días), contado desde el paso anterior; de un
     minuto a 30 días.
3. En cada valor, **Insertar un dato** abre «¿Qué dato?», con los datos del aviso y un ejemplo real del
   negocio al lado (el último aviso de ese tipo), y los datos que dejan los pasos anteriores; se elige,
   no se escribe. Un dato elegido se ve como una pastilla; el resto del valor es texto.
Sale: los pasos, al **Guardar**. Cada acción o consulta que se nombra pasa a pedir su permiso (FLOW-F12).
Si falla: el servidor rechaza al guardar una acción o una consulta que no existe en el negocio, un dato
de un paso que no va antes, una condición vacía o una espera fuera de rango, junto al paso.

### FLOW-F12 Conceder y retirar los permisos
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente
Pantalla: Editor de automatización
Pasos:
1. Abre **Permisos** (se abre sola al crear desde la galería).
2. Lee la lista, sacada de los pasos **guardados**: cada acción y cada consulta, dichas en palabras. Lo
   que falta sale como «Pendiente de tu permiso»; lo concedido, «Autorizado» con **Retirar**. Con cambios
   sin guardar avisa: «Guárdala primero: lo que autorices es lo guardado.».
3. Pulsa **Autorizar todo lo que necesita**: sale «Permisos actualizados.».
Entra: los pasos guardados y los permisos que tiene.
Sale: la lista completa de permisos de la automatización (`flow.flow.granted`). Antes del primer
guardado no hay nada que autorizar: la pestaña lo dice y pide guardar.
Si falla: si la lista nombra algo que no existe en el negocio, o algo que necesita a una persona delante
(anular, devolver, borrar datos, enviar a Hacienda…: `flow.high_risk`), se rechaza entera y se dice qué.
Nadie concede lo que no puede hacer él mismo: «No puedes permitir lo que tú no puedes hacer: «…».»
(también una API key con `flow:write`).

### FLOW-F13 Probar sin que haga nada
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

### FLOW-F14 Guardar y encender desde el editor
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Editor de automatización
Pasos:
1. Mueve el interruptor de la cabecera: la etiqueta pasa a «Activa». Si le faltan permisos avisa como en
   FLOW-F03; si no se ha abierto **Probar**, «Todavía no la has probado…». No impide encenderla.
2. Pulsa **Guardar** («Guardando…» y después «Guardada.»): se guarda el documento y, si el interruptor
   cambió, después se enciende o se pausa (`flow.flow.set_enabled`, la única puerta del interruptor).
Sale: la automatización guardada (`flow.flow.updated`; `flow.flow.enabled` o `flow.flow.paused` si
cambió el interruptor). Cambiar el disparador o los pasos sube su versión: lo que ya estaba en marcha
sigue con la versión con la que empezó.
Si falla: el mensaje en rojo, junto al paso que no encaja; no se guarda nada.

### FLOW-F15 Ejecutar a mano
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

### FLOW-F16 Ver qué hizo y por qué falló
Estado: hecho (servidor y pantalla)
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
Entra: las ejecuciones de esa automatización.
Sale: nada.

### FLOW-F17 Pedirle al asistente una automatización
Estado: hecho (servidor)
Actor: propietario, administrador, asistente
Pantalla: asistente
Pasos:
1. Pides al asistente algo que pase solo («crea un flujo que al completar una venta de más de 100 € me
   cree una tarea»).
2. El asistente escribe un **borrador**: nombre, cuándo arranca, de uno a ocho pasos de «hacer algo»,
   «solo sigue si» o «esperar», y las notas de lo que no supo decidir.
3. Te dice que lo ha dejado esperando en Automatizaciones y repite sus dudas.
Sale: un borrador pendiente (`flow.draft.proposed`). **No** crea ninguna automatización, no concede
permisos y no ejecuta nada.
Si falla: un borrador que no sigue la forma pedida, o con un paso que lee lo que no deja ningún paso
anterior, se rechaza antes de guardarlo.

### FLOW-F18 Revisar un borrador del asistente y crearlo
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
Sale: una automatización nueva sin permisos y el borrador usado, con el enlace a ella
(`flow.flow.created`, `flow.draft.used`). Salir sin guardar deja el borrador en la bandeja.
Si falla: si no encaja (una acción que no existe aquí), el mensaje junto al paso y no se crea nada; un
borrador ya decidido, «Ese borrador ya se decidió.».

### FLOW-F19 Descartar un borrador del asistente
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador
Pantalla: Automatizaciones
Pasos:
1. En **Propuestas por el asistente**, pulsa × («Descartar»).
Sale: el borrador descartado (`flow.draft.dismissed`), que se conserva como registro.
Si falla: uno ya decidido no se puede volver a decidir: «Ese borrador ya se decidió.».

### FLOW-F20 Otra app pregunta si una automatización ya está montada
Estado: hecho (servidor)
Actor: otra app, asistente
Pantalla: ninguna
Pasos:
1. Una app que ofrece un atajo hacia Automatizaciones pregunta con un aviso y una acción.
2. Recibe tres números: cuántas automatizaciones arrancan con ese aviso y pueden hacer esa acción,
   cuántas de ellas están encendidas y cuántas escuchan ese aviso pero todavía no tienen ningún permiso
   (a medio montar).
Sale: tres números; ningún nombre ni contenido.

### FLOW-F21 Cuando pasa algo en el negocio, la automatización arranca
Estado: hecho — el motor está y se prueba con avisos reales; la entrega la hace el relay del outbox
(fase 2)
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Otra app deja un aviso (por ejemplo, «se cobra una venta»).
2. Cada automatización **encendida** que arranca con ese aviso y cuyo «Solo cuando…» se cumple empieza
   una ejecución con los datos del aviso, y hace sus pasos en orden.
Sale: una ejecución (`flow.run.started`, `flow.run.finished` o `flow.run.parked` si espera). Un mismo
aviso entregado dos veces arranca **una sola** ejecución por automatización.
Si falla: cada paso que falla para la ejecución con su motivo, visible en Historial; los pasos
anteriores se quedan hechos. Una automatización que se dispararía a sí misma en cadena se para (ver
«Para quien lo mantiene»).

### FLOW-F22 Cuando llega la hora, la automatización arranca
Estado: hecho — la tarea programada `fire_due` está declarada y probada; la corre el worker (fase 2)
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Cada minuto, las automatizaciones encendidas con horario o fecha cuya hora ha llegado arrancan una
   vez.
Sale: una ejecución; la siguiente hora del horario (una fecha, una sola vez). Si el sistema estuvo
parado y se perdieron varias horas, arranca **una vez** y sigue desde ahora.

### FLOW-F23 Cuando acaba una espera, la automatización sigue
Estado: hecho — la tarea programada `resume_due` está declarada y probada; la corre el worker (fase 2)
Actor: la plataforma
Pantalla: ninguna (se ve en Historial)
Pasos:
1. Cada minuto, las ejecuciones que esperaban y cuya espera ha terminado siguen por el paso siguiente.
Sale: la ejecución sigue (`flow.run.resumed`) con la versión de la automatización con la que empezó.
Si la automatización está en pausa o borrada, se cancela.

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
| Ejecución reanudada | Termina la espera | `id`, `flow_id` | `flow.run.resumed` |
| Ejecución terminada | Termina bien, por una condición, por un error o cancelada | `id`, `flow_id`, `status` | `flow.run.finished` |
| Borrador propuesto | El asistente deja un borrador | `id` | `flow.draft.proposed` |
| Borrador usado | Se crea la automatización desde él | `id`, `flow_id` | `flow.draft.used` |
| Borrador descartado | Se descarta | `id` | `flow.draft.dismissed` |

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
| Crear, cambiar, encender, conceder, ejecutar, borrar; probar; decidir borradores | sí | sí | no | no | `flow.manage` |

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
  `resume_at`, `chain`) y `Draft`. UUIDv7, sin `hub_id`.
- **El documento**: `trigger` = `{kind: event, event, filter}` · `{kind: schedule, every: day|week|month,
  weekday 0–6 (lunes 0), day 1–31, time "HH:MM"}` · `{kind: at, at}` · `{kind: manual}`; `steps` = lista
  de `{id, kind: command|query|condition|delay, …}`. Un valor es un literal, una **ruta**
  (`input.total`, `steps.s1.id`: conserva el tipo) o un texto con `{{ruta}}` (siempre texto). Raíces:
  `input` (lo que trajo el aviso o la ejecución a mano) y `steps.<id>` de un paso anterior. Sin índices
  de lista. Condición: `{ruta: {eq|neq|in|exists|contains|gt|gte|lt|lte: valor}}`, todas a la vez; un
  dato que no está nunca cumple salvo `exists: false`.
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
  puede seguir (esperando); al terminar se vacía, así que un historial terminado no guarda copias de
  datos de otras apps. Lo que trajo el aviso (`input`) sí se queda con la ejecución.
- **Horarios**: `python-dateutil` (`rrule`, ya dependencia del Hub), en la zona del negocio; `fire_due`
  barre con `SKIP LOCKED`, arranca una vez aunque se hayan perdido varias horas y avanza
  `next_fire_at` desde ahora en la misma transacción.
- **Reintentos**: declarados y no ejecutados en la fase 1. Una ejecución fallida no se reintenta sola;
  el relay del outbox (fase 2) reintentará la **entrega** de un aviso cuya reacción no llegó a
  confirmarse, y la idempotencia por `trigger_key` hace que un reintento no ejecute dos veces.
- **Fase 1**: sin relay del outbox ni worker que corra tareas programadas. El motor se prueba entregando
  a `events.react` (o `events.deliver`) avisos **reales** del outbox, hechos por las operaciones reales de
  otras apps, y llamando a `fire_due` y `resume_due` con el reloj fijado en el test. El relay debe
  entregar a `flow` **todos** los avisos (`REACTIONS = {"*": "flow.run.react"}`), con su id y su actor.
- **Asistente**: toda operación declara `ai={"description"…}` (`risk` solo en las acciones; `high` al
  encender o pausar, conceder, ejecutar y borrar) y todo campo de entrada lleva `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre los tres modelos; una escritura cruda del admin
  no deja aviso.

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
- **No reintenta sola** una ejecución que falló.

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
| `…/flows/secrets`, `…/approvals`, `…/events/dead*` | — | fuera (ver «Qué queda fuera») |

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
| Editor (Pasos, Probar, Permisos, Historial) | `/flow/automations/:id` y `/new` | la misma columna; los pasos de mensaje, otro sistema, asistente y pregunta, fuera |
| Guía | `/flow/guide` | — |
| Bandeja «Pendiente de ti» | — | fuera |
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

- **Pasos «Enviar un mensaje», «Llamar a otro sistema» (con sus secretos), «Pedírselo al asistente» y
  «Preguntar antes a alguien»**, con la bandeja **Pendiente de ti**: dependen del envío de WhatsApp y
  correo, de guardar secretos cifrados, del asistente en el Hub y de una bandeja de preguntas por rol,
  que no existen todavía en el Hub. Volverán como pasos nuevos de esta misma columna.
- **«Necesita tu atención»** (eventos que no se entregaron): es la administración del outbox (PLAN-HUB
  bloque 7), de la plataforma, con el relay de la fase 2.
- **Recetas que traen otras apps** («Viene con …», restaurar la de fábrica) y la reparación de las de
  WhatsApp: ninguna app del Hub publica recetas todavía; la tarjeta «Contestar los WhatsApp» vuelve
  cuando la Bandeja de WhatsApp declare su aviso.
- **Límites en un permiso** («solo con este cliente»): se concede la acción entera.
- **Reintentar una ejecución fallida** desde el paso que falló.
- **Ocultar datos personales** en los ejemplos de Probar y del selector de datos: se ven tal cual
  llegaron en el aviso, solo para el propietario y el administrador.
