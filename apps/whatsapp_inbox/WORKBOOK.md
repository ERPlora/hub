# Workbook — Bandeja de WhatsApp (app)
Prefijo: WHATSAPP_INBOX
Alcance MVP: transversal
Estado de la app: hecha en el Hub (servidor y páginas). Lo que entra de erplora.com y lo que sale hacia
él está declarado y probado en el Hub, pero espera la otra mitad del contrato: las puertas
`/internal/whatsapp/*` que monta `base` y las que sirve el SaaS («Contrato con el SaaS»); hasta
entonces F03, F08, F27, F28 y F32–F34 no funcionan de punta a punta.

> Manual de usuario y especificación de la app `whatsapp_inbox`. Se escribe **antes** que el código:
> no se programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en
> verde (servidor y páginas). Parte del `WORKFLOW.md` del módulo Bandeja de WhatsApp del producto
> actual (`modules-workspace/modules/whatsapp_inbox`, `origin/main` `5ea1588`, v2.1.113) y de la app
> `whatsapp_inbox` del SaaS actual (`saas`, `origin/develop`). Los números de flujo se conservan
> (otras apps los citan); los nuevos empiezan en F32.

## Para qué sirve y para quién

La Bandeja de WhatsApp pone dentro del Hub el WhatsApp del negocio: cada cliente que escribe al
número del negocio tiene **una conversación**, con todos sus mensajes, y el equipo la lee y **contesta
desde el Hub**, sin coger el móvil. Reconoce a la persona por su número y une la conversación a su
ficha de Clientes; deja **asignar** cada conversación a alguien del equipo, marcarla **abierta,
pendiente o cerrada** y dejar **notas internas** que el cliente nunca ve. Pasadas 24 horas desde el
último mensaje del cliente, WhatsApp solo deja escribir con una **plantilla aprobada por Meta**: la
bandeja lo sabe y ofrece las plantillas del negocio.

Sirve igual a la peluquería (la clienta que pide hora) y al restaurante (el comensal que pregunta por
una mesa): lo que cambia es lo que se contesta, no cómo.

Quién la usa:

- El **propietario** y el **administrador**: todo, también ver el estado del número y las plantillas
  (Ajustes) y borrar los datos de un número.
- El **responsable**: lee, contesta, asigna a cualquiera, cambia el estado y deja notas.
- El **empleado**: lee, contesta, se asigna a sí mismo, cambia el estado y deja notas.
- Del otro lado, el **cliente** solo usa su WhatsApp.

El dueño puede seguir contestando desde la app WhatsApp Business de su móvil: lo que escribe allí
aparece en la conversación como mensaje del negocio (coexistencia de Meta).

## Referencia adoptada

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Square Messages | Bandeja en el panel y en el TPV: se elige la conversación y se contesta; pide consentimiento antes de escribir primero a un móvil | https://squareup.com/help/us/en/article/8415-reply-to-customers-with-square-messages |
| Shopify Inbox | Conversaciones abiertas/cerradas, se cierran y reabren a mano; se asignan solo a quien tiene permiso de chat | https://help.shopify.com/en/manual/inbox/conversations |
| Fresha (Client Connect) | Bandeja de clientes: contestar, abierta/cerrada, sin leer y notas internas para el equipo | https://www.fresha.com/help-center/knowledge-base/messaging/102320-manage-client-messages-in-client-connect |
| Vagaro Connect | Mensajes de ida y vuelta con clientes desde el panel | https://www.vagaro.com/en-au/pro/updates/vagaro-connect |
| Odoo (WhatsApp) | Contesta libre dentro de 24 h del último mensaje del cliente; después, solo plantilla aprobada | https://odoo.com/pt_BR/forum/ajuda-1/v183-how-can-i-send-a-whatsapp-message-to-my-customer-after-24-hours-285255 |
| Zendesk | Abierta / pendiente (esperando al cliente) / resuelta; cuando el cliente contesta, vuelve a abierta | https://www.eesel.ai/blog/zendesk-ticket-status-lifecycle |
| Intercom | Notas internas en la conversación que no cambian su estado; abrir, posponer, cerrar | https://community.intercom.com/inbox-9/snoozed-conversations-reopen-when-adding-a-note-8095 |
| Front | Comentarios internos en línea con la conversación, solo para el equipo | https://www.getmacha.com/blog/front-comments-and-mentions-explained |
| Meta (WhatsApp Business Platform) | Ventana de 24 h desde el último mensaje del cliente; fuera, solo plantillas | https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages |
| SleekFlow / Chakra (bandejas de WhatsApp) | Opt-in obligatorio antes de escribir; «me la quedo» con aviso de choque entre agentes | https://help.sleekflow.io/whatsapp/whatsapp-message-opt-in · https://chakrahq.com/article/whatsapp-shared-inbox-for-customer-support-teams/ |

**Gana:** una bandeja desde la que se contesta (Square, Shopify, Fresha, Vagaro, Odoo), con tres
estados (abierta, pendiente, cerrada) donde un mensaje nuevo del cliente reabre la conversación
(Zendesk), asignación a quien puede leer la bandeja con «Asignármela» que no pisa a otro (Shopify,
Chakra), notas internas en el hilo (Fresha, Intercom, Front) y la regla de Meta de las 24 horas
hecha cumplir en el servidor.
**Por qué las demás no:** contestar solo desde el móvil (el producto actual) obliga a coger el
teléfono y deja la bandeja en solo lectura; dos estados (Shopify) no distinguen «espero al cliente»
de «está hecho»; asignar tecleando un identificador (el producto actual) no lo usa nadie.

## Antes de empezar

1. Activar **Clientes**: la bandeja no se enciende sin ella (une cada conversación a su ficha).
2. Conectar el número de WhatsApp Business del negocio **en erplora.com** (la cuenta de WhatsApp,
   el webhook de Meta y las plantillas viven allí). En el Hub, **Bandeja de WhatsApp → Ajustes** dice
   si el número está conectado y lleva a erplora.com para conectarlo.
3. Crear las plantillas en WhatsApp Manager o en erplora.com y esperar a que Meta las apruebe:
   aparecen solas en **Ajustes → Plantillas de Meta**.
4. Escribir al número desde otro móvil y comprobar que la conversación aparece en la bandeja.

## Pantallas

### Bandeja de entrada
Menú **Bandeja de WhatsApp → Bandeja de entrada** (título «Bandeja de WhatsApp»). La ven todos los
roles. Tabla con **Contacto** (el nombre de la ficha, o el de WhatsApp, o el número), **Teléfono**,
**Estado** (Abierta, Pendiente, Cerrada), **Asignada a**, **Sin leer** y **Último mensaje** (hora si es
de hoy, «Ayer», o la fecha, en el reloj del negocio); buscador «Filtrar contacto o teléfono…»; filtros
**Estado**, **Asignada a** (A mí, Sin asignar) y **Sin leer**; 50 por página; primero la actividad
más reciente. Acción de fila **Abrir** (o tocar la fila): la conversación se abre en un panel encima
de la lista, que se queda debajo.

El panel enseña: el contacto, su número y su estado; la ficha de Clientes unida (con enlace) o
**Unir a una ficha** / **Crear ficha**; **Asignada a** con el selector del equipo y **Asignármela**;
los botones de estado **Abierta / Pendiente / Cerrada**; el hilo, del mensaje más antiguo al más
reciente (los del cliente a la izquierda, los del negocio a la derecha con su estado —Enviando…,
Enviado, Entregado, Leído, No entregado, o No enviado con **Reintentar**—, las notas internas en amarillo con su autor); **Ver anteriores** si
hay más; y debajo el cuadro para escribir con dos pestañas: **Responder** (texto, **Enviar**, y
**Plantilla**) y **Nota interna** (**Añadir nota**). Con la ventana de 24 horas cerrada, el cuadro de
texto lo dice («Han pasado más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja
escribirle con una plantilla aprobada.») y solo queda **Plantilla**. Solo el propietario y el
administrador ven **Borrar datos de este número**.

Avisos encima de la lista: «Reconectando…» mientras vuelve la conexión en vivo; el número sin
conectar («WhatsApp no está conectado. Conecta el número del negocio en erplora.com para recibir y
enviar mensajes.», con **Ir a erplora.com** para quien puede configurar); los mensajes del plan
gastados este mes («Has usado todos los mensajes de WhatsApp de tu plan este mes. Los mensajes siguen
llegando aquí, pero no se pueden enviar hasta el mes que viene o hasta que mejores el plan.»).
Vacía: «Sin conversaciones.»; con búsqueda o filtro: «Sin resultados»; cargando: indicador; error de
lista: el motivo con **Reintentar**; error del panel: el motivo que da el Hub o «No se pudo cargar la
conversación».

### Ajustes
Menú **Bandeja de WhatsApp → Ajustes** (título «Ajustes del canal»), solo propietario y
administrador. Tres bloques: **Tu número** («Conectado» con el número y el nombre del negocio, «Sin
conectar» o «Hay que reconectar», y **Gestionar en erplora.com**); **Este mes** (los mensajes
enviados frente a los del plan, o «Sin límite»); y **Plantillas de Meta**: tabla con **Nombre**,
**Idioma**, **Categoría** (Utilidad, Marketing, Autenticación), **Estado en Meta** (Aprobada, En
revisión, Rechazada, Pausada, Desactivada, Borrada en WhatsApp Manager) y **Texto**, con buscador
«Buscar plantilla…» y el motivo de Meta en las rechazadas. Vacía: «Sin plantillas.» con «Las
plantillas se crean en WhatsApp Manager o en erplora.com y aparecen aquí cuando Meta las revisa.».

## Estados de cada pantalla

| Pantalla | Cargando | Vacía | Error | Sin permiso / app apagada |
|---|---|---|---|---|
| Bandeja | indicador en la tabla; el panel, «Cargando…» | «Sin conversaciones.» / «Sin resultados» | el motivo + **Reintentar**; el panel, su motivo | «No tienes permiso» / «Esta app no está activa en este negocio» en lugar de la lista |
| Panel de la conversación | «Cargando…» | «Todavía no hay mensajes.» | «No se pudo cargar la conversación» | — |
| Ajustes | indicador | «Sin plantillas.» | el motivo + **Reintentar** | igual que la bandeja |

## Flujos

| ID | Flujo | Estado | Vertical |
|---|---|---|---|
| WHATSAPP_INBOX-F01 | Conectar el número de WhatsApp del negocio | movido a erplora.com (el Hub enseña el estado) | comun |
| WHATSAPP_INBOX-F02 | Desconectar o volver a conectar el número | movido a erplora.com (el Hub enseña «Hay que reconectar») | comun |
| WHATSAPP_INBOX-F03 | Recibir un mensaje en la bandeja | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F04 | Reconocer a la clienta por su número | hecho | comun |
| WHATSAPP_INBOX-F05 | Leer una conversación | hecho | comun |
| WHATSAPP_INBOX-F06 | Ver una foto, una nota de voz o un documento | parcial (se abre en una pestaña; sin vista previa en el hilo) | comun |
| WHATSAPP_INBOX-F07 | Asignar una conversación a alguien del equipo | hecho | comun |
| WHATSAPP_INBOX-F08 | Contestar desde la app de WhatsApp Business del móvil | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F09 | Ver quién espera respuesta | hecho (filtro y recuento; la campana del Hub no existe aún) | comun |
| WHATSAPP_INBOX-F10 | Borrar los datos de un número sin ficha | hecho | comun |
| WHATSAPP_INBOX-F11 | Borrar los datos de una clienta desde su ficha | hecho | comun |
| WHATSAPP_INBOX-F12 | Unir dos fichas de la misma clienta | hecho | comun |
| WHATSAPP_INBOX-F13 | Ver el consumo del mes y llegar al tope | hecho | comun |
| WHATSAPP_INBOX-F14–F26 | Respuestas automáticas que reservan cita o mesa | fuera de esta app (ver «Lo que NO hace») | — |
| WHATSAPP_INBOX-F27 | Ver las plantillas y lo que dice Meta de cada una | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F28 | Traer las plantillas creadas en WhatsApp Manager | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F29–F31 | Crear, editar y borrar una plantilla | movido a erplora.com | comun |
| WHATSAPP_INBOX-F32 | Contestar desde la bandeja | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F33 | Enviar una plantilla | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F34 | Saber si un mensaje llegó y se leyó | declarado; esperan las puertas de base/SaaS | comun |
| WHATSAPP_INBOX-F35 | Cambiar el estado de una conversación | hecho | comun |
| WHATSAPP_INBOX-F36 | Dejar una nota interna | hecho | comun |
| WHATSAPP_INBOX-F37 | Unir la conversación a una ficha o crear la ficha | hecho | comun |

### WHATSAPP_INBOX-F01 Conectar el número de WhatsApp del negocio
Estado: movido a erplora.com
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Abrir **Bandeja de WhatsApp → Ajustes**: **Tu número** dice «Sin conectar».
2. Pulsar **Gestionar en erplora.com**: en el panel del negocio de erplora.com se conecta el número
   (Facebook, QR de la app WhatsApp Business).
3. Al volver, **Tu número** dice «Conectado» con el número, sin recargar.
Entra: el estado del número que erplora.com manda al Hub.
Sale: nada en el Hub; el número conectado vive en erplora.com.
Si falla: lo dice erplora.com; el Hub sigue diciendo «Sin conectar».

### WHATSAPP_INBOX-F02 Desconectar o volver a conectar el número
Estado: movido a erplora.com
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Si WhatsApp retiró el permiso, **Tu número** dice «Hay que reconectar» y la bandeja avisa de que
   no se puede enviar.
2. **Gestionar en erplora.com** lleva a reconectar o desconectar.
Sale: las conversaciones guardadas no se tocan.

### WHATSAPP_INBOX-F03 Recibir un mensaje en la bandeja
Estado: declarado; esperan las puertas de base/SaaS
Actor: cliente, sistema
Pantalla: Bandeja de entrada
Pasos:
1. La clienta escribe al número del negocio.
2. En pocos segundos su conversación sale arriba en la bandeja con **Sin leer** sumado y la hora en
   **Último mensaje**; si la bandeja o su conversación están abiertas, se refrescan solas.
3. Un mensaje que llega dos veces aparece una sola vez y suma una sola vez.
4. Los mensajes del historial que trae la conexión aparecen con la hora en que se dijeron y no suman
   en **Sin leer**; si uno llegó vacío (foto del historial anunciada antes de tiempo) y después llega
   completo, se completa en su sitio.
5. Si la conversación estaba pendiente o cerrada, vuelve a **Abierta**.
6. Con los mensajes del plan gastados, el mensaje llega igual: el tope solo limita lo que se envía.
Entra: cada mensaje que erplora.com recibe de Meta para este negocio.
Sale: una conversación por número y el mensaje guardado; aviso `whatsapp_inbox.message.received`.
Si falla: si el Hub no contesta, erplora.com guarda el mensaje y lo vuelve a entregar.

### WHATSAPP_INBOX-F04 Reconocer a la clienta por su número
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando escribe alguien cuyo número está en **una** ficha de Clientes, su conversación queda unida a
   esa ficha.
2. Cuando se crea o se corrige una ficha con el número de alguien que ya había escrito, su
   conversación se une a ella.
3. El número se compara como número (formato internacional): `600 111 222`, `+34 600 111 222` y
   `0034600111222` son la misma persona en un negocio de España; los mismos dígitos con el prefijo de
   otro país son otra persona.
Entra: el número de la conversación y las fichas con ese número.
Sale: la conversación sabe de qué ficha es. Solo rellena un vínculo vacío: el que puso una persona se
respeta. Una ficha eliminada cuenta como vacío: su conversación queda sin ficha y otra ficha viva del
mismo número la reclama.
Si falla: si dos fichas tienen el mismo número, no se une a ninguna y el mensaje sigue guardado.

### WHATSAPP_INBOX-F05 Leer una conversación
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Buscar por contacto o teléfono (el teléfono escrito de cualquier forma, también una parte:
   `600 111` encuentra `+34600111222`) o filtrar por estado, asignación o sin leer. El asistente la
   nombra como se dice: «Ana Lopez», «ana lópez» o «Zoé 🌸» llevan a la misma conversación si solo una
   coincide.
2. Pulsar **Abrir** en la fila (o tocar la fila).
3. El hilo aparece encima de la lista, del más antiguo al más reciente; un mensaje sin texto ni
   adjunto enseña su tipo en el idioma de quien lo lee («Ubicación», «Respuesta de botón»…), y una
   reacción (👍) aparece sobre el mensaje al que responde, sin sumar en **Sin leer**.
4. Al abrirla, **Sin leer** vuelve a «—»; un mensaje que llega con el hilo abierto también queda leído.
5. **Cerrar** vuelve a la lista.
Sale: **Sin leer** a cero en esa conversación; nada más cambia.
Si falla: el motivo dentro del panel; la lista sigue disponible.

### WHATSAPP_INBOX-F06 Ver una foto, una nota de voz o un documento
Estado: parcial — el adjunto se abre en una pestaña nueva servida por erplora.com; el hilo no enseña
la foto ni reproduce el audio (falta permitir el origen de erplora.com en la política de seguridad del
Hub)
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Un mensaje con adjunto enseña su tipo (Foto, Nota de voz, Vídeo, Documento, Sticker), el nombre del
   archivo y su texto.
2. Pulsar **Abrir el adjunto**: se abre en una pestaña nueva (solo adjuntos de erplora.com por https).
Si falla: si erplora.com ya no lo guarda, la pestaña lo dice.

### WHATSAPP_INBOX-F07 Asignar una conversación a alguien del equipo
Estado: hecho
Actor: empleado (a sí mismo), responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Abrir la conversación (F05).
2. Pulsar **Asignármela**, o elegir a alguien del equipo en **Asignada a** (solo responsable,
   administrador y propietario), o **Quitar asignación**.
3. La lista y el panel enseñan la asignación, en todas las pantallas abiertas.
Sale: la conversación queda asignada; aviso `whatsapp_inbox.conversation.assigned`.
Si falla: quien no puede asignar a otros (el empleado) nunca quita una conversación a otra persona:
«Esta conversación ya la lleva {nombre}.», también si se la asignaron un instante antes; tampoco puede
asignarla a otro («Solo puedes asignarte conversaciones a ti»). El responsable sí reasigna, y su
**Asignármela** tampoco pisa a nadie.

### WHATSAPP_INBOX-F08 Contestar desde la app de WhatsApp Business del móvil
Estado: declarado; esperan las puertas de base/SaaS
Actor: propietario
Pantalla: Bandeja de entrada
Pasos:
1. Contestar como siempre desde la app WhatsApp Business del móvil.
2. La respuesta aparece en el hilo como mensaje del negocio, marcada «Desde el móvil».
3. No suma en **Sin leer**.

### WHATSAPP_INBOX-F09 Ver quién espera respuesta
Estado: hecho (filtro y recuento; la campana del Hub llegará con la barra superior)
Actor: todos
Pantalla: Bandeja de entrada
Pasos:
1. Filtrar **Estado: Abierta** y **Sin leer**: quedan las conversaciones cuyo último mensaje es del
   cliente.
2. El recuento de conversaciones esperando respuesta está disponible para la campana del Hub
   (`whatsapp_inbox.conversation.summary`).

### WHATSAPP_INBOX-F10 Borrar los datos de un número sin ficha
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de entrada
Pasos:
1. Abrir la conversación de la persona que pide borrar sus datos.
2. Pulsar **Borrar datos de este número**; leer «¿Borrar los datos de este número?» con el número y el
   aviso de que no se puede deshacer; pulsar **Borrar datos** (o **Cancelar**).
3. El panel se cierra, la conversación sale de la lista y aparece «Se han borrado los datos de este
   número.».
Sale: número, nombre, textos, adjuntos y notas vaciados en el Hub al momento; conversación cerrada y
borrada. Si vuelve a escribir, empieza una conversación nueva. Aviso
`whatsapp_inbox.conversation.erased` con el identificador (nunca el número). Después del guardado, el Hub
pide a erplora.com que olvide ese número y sus mensajes (adjuntos incluidos, que viven allí); hasta que
lo confirma, el número se guarda aparte solo para pedírselo (`erase_status = pending`).
Si falla: «No se pudieron borrar los datos de este número» (o el motivo). Si erplora.com no confirma,
se le vuelve a pedir: al pulsarlo otra vez y cada 5 minutos desde el worker (fase 2); pulsarlo dos veces
no borra nada más.

### WHATSAPP_INBOX-F11 Borrar los datos de una clienta desde su ficha
Estado: hecho
Actor: sistema
Pasos:
1. En Clientes se borran los datos de una ficha.
2. Todas las conversaciones unidas a esa ficha quedan vaciadas y cerradas como en F10.
Entra: el aviso `customer.customer.erased`.
Si falla: el aviso se reintenta; repetirlo no cambia nada.

### WHATSAPP_INBOX-F12 Unir dos fichas de la misma clienta
Estado: hecho
Actor: sistema
Pasos:
1. En Clientes se une una ficha duplicada a otra.
2. Las conversaciones de la ficha absorbida pasan a la que queda, sin tocar nada más.
Entra: el aviso `customer.customer.merged`. Repetirlo no cambia nada.

### WHATSAPP_INBOX-F13 Ver el consumo del mes y llegar al tope
Estado: hecho
Actor: todos (aviso), propietario y administrador (Ajustes)
Pantalla: Bandeja de entrada, Ajustes
Pasos:
1. **Ajustes → Este mes** enseña los mensajes enviados este mes frente a los del plan; los dos
   números los pone erplora.com.
2. En el tope, la bandeja lo avisa encima de la lista y **Enviar** lo explica en vez de enviar.
3. Lo que escriben los clientes se sigue guardando.
4. Al cambiar de mes (en el reloj del negocio) el aviso se va aunque erplora.com aún no haya hablado.
Si falla: si erplora.com rechaza un envío por el tope, el mensaje no sale y se dice por qué.

### WHATSAPP_INBOX-F27 Ver las plantillas y lo que dice Meta de cada una
Estado: declarado; esperan las puertas de base/SaaS
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. **Ajustes → Plantillas de Meta** lista las plantillas con su estado en Meta; una rechazada enseña
   «Motivo de Meta: …».
2. Cuando Meta cambia el veredicto, la tabla cambia sola.
Entra: la lista que erplora.com manda al Hub cada vez que cambia.
Sale: nada; una plantilla que Meta ya no lista queda «Borrada en WhatsApp Manager» y no se puede enviar.

### WHATSAPP_INBOX-F28 Traer las plantillas creadas en WhatsApp Manager
Estado: declarado; esperan las puertas de base/SaaS
Actor: sistema
Pasos: las que el negocio crea en WhatsApp Manager aparecen en la lista en cuanto erplora.com las
manda, con su texto, sus variables y su estado.

### WHATSAPP_INBOX-F32 Contestar desde la bandeja
Estado: declarado; esperan las puertas de base/SaaS
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Abrir la conversación (F05), pestaña **Responder**.
2. Escribir y pulsar **Enviar** (o Ctrl+Intro).
3. El mensaje aparece en el hilo, a la derecha, «Enviando…»; **Sin leer** queda a cero. En cuanto
   erplora.com lo acepta pasa a «Enviado».
Entra: el texto (hasta 4096 caracteres) y una clave del mensaje (la pantalla y el asistente la generan;
la misma al reintentar).
Sale: el mensaje guardado en cola y, tras el guardado, entregado a erplora.com; avisos
`whatsapp_inbox.message.sent` y, al contestar erplora.com, `whatsapp_inbox.message.status_changed`.
Si no se puede ni guardar, el cuadro conserva el texto con el motivo:
- han pasado más de 24 horas desde el último mensaje del cliente: «Han pasado más de 24 horas…»;
- el número no está conectado («WhatsApp no está conectado…»), el mes está gastado o el Hub no llega a
  erplora.com: el cuadro lo dice antes de escribir.
Si erplora.com lo rechaza (número bloqueado, tope del mes…): la burbuja dice «No entregado» y su motivo.
Si erplora.com no contesta o no confirma: la burbuja dice «No enviado» con **Reintentar**, que lo entrega
otra vez con la misma clave: nunca sale dos veces.

### WHATSAPP_INBOX-F33 Enviar una plantilla
Estado: declarado; esperan las puertas de base/SaaS
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En **Responder**, pulsar **Plantilla**: se abre «Enviar una plantilla» con las plantillas
   **aprobadas** (nombre, idioma, categoría y texto).
2. Elegir una y rellenar sus variables (`{{1}}`, `{{2}}`…); la vista previa enseña el texto final.
3. Pulsar **Enviar**: el mensaje aparece en el hilo como en F32.
También por el asistente o la API a un número que aún no ha escrito («envía la plantilla de
recordatorio a +34 600 111 222»): se crea su conversación.
Si falla: una plantilla de **Marketing** solo se envía a una clienta con ficha y con el consentimiento
de marketing por WhatsApp dado en Clientes («Esta clienta no ha dado su consentimiento para recibir
publicidad por WhatsApp.»); una plantilla no aprobada o borrada no se puede elegir; faltan variables:
«Rellena todas las variables de la plantilla.»; el resto, como en F32.

### WHATSAPP_INBOX-F34 Saber si un mensaje llegó y se leyó
Estado: declarado; esperan las puertas de base/SaaS
Actor: todos
Pantalla: Bandeja de entrada
Pasos:
1. Cada mensaje enviado lleva su estado: **Enviando…**, **Enviado**, **Entregado**, **Leído**, **No
   entregado** (con el motivo de Meta o de erplora.com) o **No enviado** (con **Reintentar**).
2. Cambia solo, sin recargar, cuando erplora.com lo cuenta.
Sale: el estado solo avanza (un «Entregado» que llega tarde no deshace un «Leído»); un estado que llega
antes que la respuesta de erplora.com se casa con el mensaje por su clave y no se pierde.

### WHATSAPP_INBOX-F35 Cambiar el estado de una conversación
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel, pulsar **Abierta**, **Pendiente** (esperando al cliente) o **Cerrada** (resuelta).
2. La lista lo enseña al momento en todas las pantallas.
3. Si el cliente vuelve a escribir, la conversación vuelve a **Abierta** sola.
Sale: aviso `whatsapp_inbox.conversation.status_changed`.

### WHATSAPP_INBOX-F36 Dejar una nota interna
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel, pestaña **Nota interna**: escribir y pulsar **Añadir nota**.
2. La nota sale en el hilo, en amarillo, con su autor y su hora; el cliente nunca la ve.
3. Quien la escribió, el responsable, el administrador y el propietario pueden **Borrarla**.
Sale: aviso `whatsapp_inbox.note.added` / `whatsapp_inbox.note.deleted`.

### WHATSAPP_INBOX-F37 Unir la conversación a una ficha o crear la ficha
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel sin ficha, **Unir a una ficha** busca en Clientes por nombre, teléfono o email; elegir
   una la une.
2. O **Crear ficha**: crea en Clientes una ficha con el nombre de WhatsApp (o el número) y el número,
   con origen «WhatsApp», y la une.
3. Con ficha, **Ver ficha** lleva a ella y **Desunir** la quita.
Sale: aviso `whatsapp_inbox.conversation.customer_linked`.
Si falla: los motivos de Clientes (por ejemplo, un número que no es válido).

## Servicios: lo que entra y lo que sale

### Lo que ofrece: consultas (leen, no cambian nada)

| Operación | Qué devuelve |
|---|---|
| `whatsapp_inbox.conversation.list` | Conversaciones, con búsqueda por contacto o teléfono y filtros de estado, asignación, sin leer y ficha |
| `whatsapp_inbox.conversation.detail` | Una conversación (por id, número o nombre) con su ficha, su asignación y si la ventana de 24 h está abierta |
| `whatsapp_inbox.conversation.by_phone` | La conversación de un número exacto (formato internacional), o ninguna: para avisar desde otra app |
| `whatsapp_inbox.conversation.summary` | Abiertas, sin leer y esperando respuesta, y si el tope del mes está gastado |
| `whatsapp_inbox.message.list` | Los mensajes de una conversación, del más reciente al más antiguo |
| `whatsapp_inbox.note.list` | Las notas internas de una conversación |
| `whatsapp_inbox.template.list` | Las plantillas (por defecto, solo las aprobadas) |
| `whatsapp_inbox.channel.get` | El estado del número y el consumo del mes |
| `whatsapp_inbox.agent.list` | Las personas del negocio a las que se puede asignar una conversación |

### Lo que ofrece: acciones (cambian datos)

| Operación | Qué hace |
|---|---|
| `whatsapp_inbox.message.send` | Guarda y entrega un texto (dentro de 24 h) o una plantilla aprobada, a una conversación o a un número; pide una clave por mensaje |
| `whatsapp_inbox.message.retry` | Vuelve a entregar un mensaje que no salió, con la misma clave |
| `whatsapp_inbox.conversation.mark_read` | Deja **Sin leer** a cero |
| `whatsapp_inbox.conversation.assign` | Asigna o desasigna; «Asignármela» no pisa a otro |
| `whatsapp_inbox.conversation.set_status` | Abierta, pendiente o cerrada |
| `whatsapp_inbox.conversation.link_customer` | Une a una ficha, crea la ficha o desune |
| `whatsapp_inbox.conversation.erase` | Borra los datos de un número (irreversible) |
| `whatsapp_inbox.note.add` / `whatsapp_inbox.note.delete` | Notas internas |

Del sistema (sin ruta pública; solo erplora.com por `/internal`, las entregas, el worker y las
reacciones): `whatsapp_inbox.message.receive`, `whatsapp_inbox.message.update_status`,
`whatsapp_inbox.channel.sync`; las entregas (`whatsapp_inbox.message.claim_delivery`,
`whatsapp_inbox.message.record_delivery`, `whatsapp_inbox.conversation.claim_erasure`,
`whatsapp_inbox.conversation.record_erasure`); la tarea del worker `whatsapp_inbox.delivery.resume`; y
las reacciones a Clientes (`whatsapp_inbox.conversation.claim_for_customer`,
`whatsapp_inbox.conversation.move_customer`, `whatsapp_inbox.conversation.release_customer`,
`whatsapp_inbox.conversation.erase_for_customer`).

### Lo que avisa

`whatsapp_inbox.message.received`, `whatsapp_inbox.message.sent`,
`whatsapp_inbox.message.status_changed`, `whatsapp_inbox.conversation.read`,
`whatsapp_inbox.conversation.assigned`, `whatsapp_inbox.conversation.status_changed`,
`whatsapp_inbox.conversation.customer_linked`, `whatsapp_inbox.conversation.erased`,
`whatsapp_inbox.note.added`, `whatsapp_inbox.note.deleted`, `whatsapp_inbox.channel.synced`. Llevan
identificadores, nunca un número ni un texto.

### A qué reacciona y lo que necesita de otras apps

- **Clientes** (obligatoria): `customer.customer.created` y `customer.customer.updated` unen las
  conversaciones sin ficha de ese número (F04); `customer.customer.merged` las pasa a la ficha que
  queda (F12); `customer.customer.deleted` las deja sin ficha y otra ficha viva del número las reclama;
`customer.customer.erased` las borra (F11). Lee las fichas por número y el
  consentimiento de marketing por WhatsApp; crea fichas solo con `customer.customer.create`.

### Quién la usa

- **Citas** y **Reservas** (cuando avisen por WhatsApp): `conversation.by_phone` para encontrar la
  conversación y `message.send` con una plantilla de Utilidad para el aviso o el recordatorio.
- El **asistente**: todas las operaciones, con referencias humanas («responde a Ana», «asigna la
  conversación de +34 600 111 222 a Luis», «envía la plantilla recordatorio a +34…»).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado |
|---|---|---|---|---|
| `whatsapp_inbox.view` (leer, marcar leída) | sí | sí | sí | sí |
| `whatsapp_inbox.reply` (enviar, reintentar, notas, estado, ficha, asignarse una libre) | sí | sí | sí | sí |
| `whatsapp_inbox.assign` (asignar a otro, quitársela a otro, borrar notas ajenas) | sí | sí | sí | no |
| `whatsapp_inbox.configure` (Ajustes) | sí | sí | no | no |
| `whatsapp_inbox.erase` (borrar datos de un número) | sí | sí | no | no |

Las operaciones del sistema piden `whatsapp_inbox.receive`, que ningún rol tiene.

## Lo que NO hace, a propósito

- **No guarda credenciales de Meta**: la cuenta de WhatsApp Business, el webhook y el token viven en
  erplora.com.
- **No crea, edita ni borra plantillas** (F29–F31): se hacen en WhatsApp Manager o en erplora.com,
  que es quien habla con Meta; el Hub guarda una copia para elegirlas y enviarlas.
- **No contesta sola ni reserva** (F14–F26): las respuestas automáticas eran recetas del módulo de
  Automatizaciones y del asistente, que no se portan con esta app; vuelven con ellos.
- **No hace campañas** ni envíos masivos.
- No sincroniza grupos ni listas de difusión (límite de la coexistencia de Meta).

## Para quien lo mantiene

### Modelo

- `Channel` (una fila): estado del número (`not_connected`, `connected`, `reconnect_needed`), número
  y nombre, tope y consumo del mes (`monthly_limit`, `monthly_usage`, `usage_month` `AAAA-MM`) y la
  `version` de la última foto de erplora.com (una igual o más vieja se ignora). **Fase 1 sin tenencia:**
  es una sola fila compartida por todos los hubs (como todas las tablas de la fase 1); en la fase 2 vive
  en la BD de cada hub.
- `Conversation`: número E.164 (`phone`, único entre las no borradas), nombre de WhatsApp y su forma
  para buscar (`contact_search`: sin mayúsculas, tildes, emojis ni espacios de más), ficha
  (`customer`, FK a `customer.Customer`; una ficha eliminada cuenta como ninguna), asignada
  (`assigned_to`, FK al usuario), estado, sin leer, último mensaje (hora, extracto, tipo, dirección),
  último mensaje del cliente (`last_inbound_at`: la ventana de 24 h), `erased_at`, y el borrado en
  erplora.com (`erase_status`: vacío, `pending`, `done`; `erase_phone`: el número que erplora.com tiene
  que olvidar, solo hasta que lo confirma).
- `Message`: dirección (`inbound`, `outbound`), origen (`customer`, `phone_app`, `hub`), procedencia
  (`live`, `history`), tipo de Meta, texto, adjunto por URL de erplora.com (`media_url`, solo https y de
  su origen; tipo MIME, nombre, pie), estado (`received`; los del Hub: `queued` → `sending` → `sent` →
  `delivered` → `read`, o `failed`) con el código y el motivo del último intento o de Meta,
  `wa_message_id` (único; vacío mientras no ha salido), `client_message_id` (la clave del envío, única,
  obligatoria), plantilla usada y sus variables, quién lo envió, hora en que se dijo y objeto de Meta
  (`payload`). Una reacción es un mensaje de tipo `reaction` cuyo `reply_to` es el mensaje al que
  responde: no suma en «Sin leer» ni pasa a último mensaje.
- `Note`: texto, autor y hora.
- `Template`: nombre + idioma (únicos), categoría, estado en Meta, cabecera, cuerpo, pie, número de
  variables, motivo de rechazo.

Mensajes recibidos y enviados: el admin los enseña en **solo lectura** (son lo que llevó WhatsApp; se
corrigen borrando los datos de la conversación, nunca editando), con borrado para el staff.

### Reglas que no se rompen

- **Nada espera a erplora.com dentro de una transacción.** `message.send` valida y guarda el mensaje
  `queued` con su clave en una transacción corta (con su evento) y lo entrega **después del COMMIT**
  (`transaction.on_commit`): `message.claim_delivery` lo toma con `SKIP LOCKED` y lo pone `sending`
  (transacción corta), la llamada HTTP a erplora.com va sin transacción ni bloqueo, y
  `message.record_delivery` guarda la respuesta en otra transacción corta. Lo mismo al borrar
  (`conversation.claim_erasure` → HTTP → `conversation.record_erasure`). Un erplora.com lento nunca
  bloquea la conversación (`receive`, `mark_read`, `assign`) ni, con el plan Gratis, el hub.
- **Fase 1** entrega al terminar la petición (el `on_commit` corre en ella); **fase 2**: el trabajo
  diferido entra con `use_hub(hub)` explícito (corre fuera de la petición que eligió el hub) y la tarea
  del worker `whatsapp_inbox.delivery.resume` (`*/5 * * * *`, `catch_up: collapse`, declarada en
  `apps.py`) retoma con `SKIP LOCKED`, de 50 en 50, los mensajes `queued`/`sending` y los borrados
  `pending` con más de 2 minutos.
- **Un mensaje nunca es «enviado» sin el id de Meta.** Respuestas de erplora.com: 200 con
  `wa_message_id` → `sent`; 409 → `failed` con su motivo (`whatsapp.cap_reached` se guarda como
  `whatsapp_inbox.cap_reached`, cualquier otro como `whatsapp_inbox.send_refused`); conexión fallida o un
  4xx que no es 409 → no ha salido (`sending`, `whatsapp_inbox.saas_unreachable`); 5xx, tiempo de lectura
  agotado o 200 sin id → no se sabe (`sending`, `whatsapp_inbox.send_unknown`). Los dos últimos se
  reintentan **con la misma clave** («No enviado · Reintentar», `message.retry`): erplora.com nunca envía
  dos veces la misma clave.
- **La clave es obligatoria y una por mensaje** (`client_message_id`): la pantalla la guarda hasta que el
  Hub acepta el mensaje (aunque se retoque el texto) y el asistente genera una por intención. La misma
  clave dos veces, también a la vez, es un solo mensaje y una sola entrega (restricción única; el
  segundo recibe la fila del primero).
- La ventana de 24 h se cuenta desde el último mensaje **del cliente** (`last_inbound_at`), en el
  servidor; fuera de ella, `message.send` con texto da 409 `whatsapp_inbox.window_closed`. Sin
  `SAAS_INTERNAL_URL`, sin número conectado o con el mes gastado no se guarda nada (409
  `whatsapp_inbox.saas_unconfigured`, `whatsapp_inbox.channel_not_connected`,
  `whatsapp_inbox.cap_reached`).
- Una plantilla `MARKETING` exige la ficha viva de la conversación o, si no hay conversación, la única
  ficha viva de ese número, con el consentimiento `marketing` por `whatsapp` en vigor (el último hecho
  de Clientes); 409 `whatsapp_inbox.marketing_consent_missing`.
- Cada `wa_message_id`, una fila; el mismo mensaje entregado dos veces a la vez, una fila y un solo
  «Sin leer» (bloqueo de la conversación + restricción única). Una conversación por número entre las no
  borradas (restricción única parcial).
- Sin `whatsapp_inbox.assign` nadie quita una conversación a otra persona: si la lleva otro, 409
  `whatsapp_inbox.already_assigned`, pida «asignármela» o «quitar asignación»; solo se asigna a sí mismo.
  Con el permiso, «Asignármela» (`only_if_unassigned`) tampoco la quita.
- El estado de un mensaje solo avanza: `queued`/`sending` < `sent` < `delivered` < `read`; `failed`
  sustituye a todo menos a `read`. Un estado que llega antes que la respuesta de erplora.com se casa
  por la clave y el `sent` posterior no lo hace retroceder.
- Las referencias por voz o texto («Ana Lopez», «zoe») se comparan sin mayúsculas, tildes, emojis ni
  espacios de más, contra el nombre de WhatsApp y el de la ficha viva; solo valen si señalan
  exactamente una conversación (si no, 409 `whatsapp_inbox.conversation_ambiguous`).
- Un número que llega de erplora.com tiene que ser internacional (`+?[1-9]` y 7–15 cifras) o es un 422;
  el número del negocio, E.164 o vacío.
- Zona horaria de la fase 1: `Europe/Madrid` (el mes del tope y las horas de la bandeja).

### Retención (RGPD)

Las conversaciones se guardan mientras el negocio usa la app. Se borran: a mano (F10), al borrar la
ficha en Clientes (F11) y con la base de datos del negocio cuando se da de baja. Borrar vacía en el Hub,
al momento, el número, el nombre, los textos, los adjuntos, las variables de plantilla, el objeto de Meta
y las notas; y pide a erplora.com que olvide el número y los mensajes (los adjuntos viven allí). Quedan
el identificador de cada mensaje (para no volver a crearlo si erplora.com lo entregara otra vez), las
fechas y, solo hasta que erplora.com confirma, el número a olvidar (`erase_phone`). No hay purga
automática por antigüedad en la fase 1: si se decide un plazo, será un ajuste con su tarea.

### Contrato con el SaaS

**Firma** de toda llamada, en los dos sentidos (la de todo `/internal`, `base.auth.sign`): cabeceras
`X-Erplora-Timestamp` (segundos Unix) y `X-Erplora-Signature` = HMAC-SHA256 en hexadecimal de
`f"{timestamp}.{cuerpo}"` con `INTERNAL_SHARED_SECRET`; quien recibe rechaza (401) una firma mala o una
marca de tiempo a más de 300 s. Cuerpo JSON UTF-8. `hub` = el slug del negocio en la fase 1 (el
`Hub.id` en la fase 2). Ejemplo de cabeceras:

```http
POST /internal/whatsapp/inbound HTTP/1.1
Content-Type: application/json
X-Erplora-Timestamp: 1760518800
X-Erplora-Signature: 5f0c…e91a   # hex(HMAC_SHA256(secret, "1760518800." + cuerpo))
```

**Cuatro puertas que monta `base`** (erplora.com → Hub; cada una ejecuta una operación de sistema):

1. `POST /internal/whatsapp/inbound` → `whatsapp_inbox.message.receive`. Un mensaje del cliente o el eco
   de lo que el dueño escribió en el móvil, en vivo o del historial:

   ```json
   {"hub": "a", "wa_message_id": "wamid.HBgL…", "from": "34600111222", "contact_name": "Ana",
    "direction": "inbound", "source": "live", "type": "image", "text": "",
    "media": {"url": "https://erplora.com/whatsapp/media/7f3c…", "mime_type": "image/jpeg",
              "filename": "", "caption": "Mi pelo"},
    "reply_to": "", "sent_at": "2026-10-15T10:00:00Z", "payload": {"…": "objeto de Meta"}}
   ```

   `from`: el número internacional del cliente, con o sin `+`. `direction`: `inbound` (cliente) u
   `outbound` (eco del móvil; `from` sigue siendo el cliente). `source`: `live` o `history`.
   `media.url`: del origen de erplora.com y por https; el navegador la abre con la sesión del negocio.
   Una reacción llega con `type: "reaction"`, el emoji en `text` y el mensaje que responde en
   `reply_to`. Respuesta 200 `{"id", "conversation_id", "created"}`; repetir el mismo `wa_message_id`
   es 200 con `created: false` (o completa un `media_placeholder` del historial). 422 con el sobre de
   errores si el cuerpo no vale (no reintentar); 404 `app_inactive` si la app no está activa en ese
   negocio, 5xx o sin respuesta: erplora.com guarda el mensaje y reintenta con espera creciente.
2. `POST /internal/whatsapp/status` → `whatsapp_inbox.message.update_status`:

   ```json
   {"hub": "a", "wa_message_id": "wamid.HBgM…", "client_message_id": "0199e7c2-…",
    "status": "failed", "error": {"code": "131047", "message": "Re-engagement message"},
    "status_at": "2026-10-15T10:00:05Z"}
   ```

   `status`: `sent`, `delivered`, `read` o `failed`. **`client_message_id` es la clave con la que el Hub
   envió el mensaje (su `Idempotency-Key`)**: erplora.com la manda siempre, porque un estado puede llegar
   antes que su respuesta al envío y solo la clave lo casa. Respuesta 200
   `{"updated": true|false, "status": "…"}`; un mensaje desconocido es 200 con `updated: false`.
3. `PUT /internal/whatsapp/channel` → `whatsapp_inbox.channel.sync`, cada vez que cambia el número, el
   consumo o una plantilla:

   ```json
   {"hub": "a", "version": 42, "status": "connected", "phone_number": "+34910000000",
    "display_name": "Peluquería Ana", "monthly_limit": 150, "monthly_usage": 12, "usage_month": "2026-10",
    "templates": [{"name": "recordatorio", "language": "es", "category": "UTILITY", "status": "APPROVED",
                   "header": "", "body": "Hola {{1}}, te esperamos el {{2}}.", "footer": "",
                   "variables": 2, "rejected_reason": "", "meta_id": "1234567890"}]}
   ```

   → 200 `{"applied": true|false, "version": 42}`. `templates: null` deja las plantillas como están;
   una lista las sustituye (las que faltan quedan `DELETED`). Una `version` igual o menor que la
   guardada no se aplica.
4. La clave `whatsapp` de la **foto de estado** (`PUT /internal/hubs/{id}/state`): el mismo cuerpo que la
   puerta 3 (sin `hub`), con la `version` de la foto; `base` se la pasa a `whatsapp_inbox.channel.sync`.

**Tres puertas que sirve el SaaS** (el Hub → erplora.com; `apps/whatsapp_inbox/gateway.py`, `httpx`, 5 s
para conectar y 15 s para leer; siempre después del COMMIT, nunca dentro de una transacción):

5. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/send`, con `Idempotency-Key: <client_message_id>`:

   ```json
   {"hub": "a", "to": "+34600111222", "type": "text", "text": "Sí, mañana a las 10"}
   {"hub": "a", "to": "+34600111222", "type": "template",
    "template": {"name": "recordatorio", "language": "es", "variables": ["Ana", "viernes"]}}
   ```

   Respuestas: 200 `{"wa_message_id": "wamid…"}` (aceptado por Meta); 409
   `{"error": {"code": "whatsapp.cap_reached" | "whatsapp.not_connected" | "whatsapp.window_closed" |
   "whatsapp.template_not_approved" | "whatsapp.recipient_blocked", "message": "…"}}` = no ha salido;
   un 4xx que no es 409 = no ha salido; 5xx o sin respuesta = no se sabe. erplora.com **nunca envía dos
   veces la misma clave** (devuelve el `wa_message_id` que ya tenía) y **reserva el cupo del mes de forma
   atómica al aceptar**: dos envíos simultáneos no pueden pasar ambos el tope.
6. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/erase`:

   ```json
   {"hub": "a", "phone": "+34600111222", "wa_message_ids": ["wamid.HBgL…", "wamid.HBgM…"]}
   ```

   erplora.com borra lo que guarda de ese número para ese negocio (mensajes aparcados, adjuntos, el
   cliente en sus colas) y contesta 200 `{"erased": true}`. Cualquier otra respuesta deja el borrado
   `pending` y el Hub lo vuelve a pedir.
7. El **envío de estados** de la puerta 2 es obligación del SaaS: cada estado de Meta de un mensaje del
   Hub, con su `wa_message_id` y su `client_message_id`, hasta 200.

### Contrato con `base`

- Montar las puertas 1–3 en `/internal/whatsapp/` (no publicadas en el ALB), comprobar la firma y la
  marca de tiempo, resolver el negocio por `hub` (fase 1: `Scope("host", hub)`; fase 2: `use_hub`),
  comprobar que la app está activa (si no, 404 `app_inactive`) y ejecutar la operación con
  `system_context(scope)`, devolviendo su salida o el sobre de errores con su estado HTTP (422 para un
  cuerpo que no vale).
- Al recibir la foto de estado con la clave `whatsapp` (puerta 4), pasarla a `whatsapp_inbox.channel.sync`.
- En la fase 2: el relay del outbox entrega `customer.customer.created/updated/merged/deleted/erased` a
  `apps.whatsapp_inbox.events.react`; el worker ejecuta la tarea `resume_deliveries` de `apps.py` en
  cada hub (`hub_due`), y el trabajo diferido de esta app entra con `use_hub(hub)`.
- La campana de la barra superior puede leer `whatsapp_inbox.conversation.summary` (`awaiting_reply`).
- Para ver fotos y audio dentro del hilo (F06 completo), la CSP del Hub tiene que permitir el origen de
  erplora.com en `img-src` y `media-src` (`config/settings.py`, como ya hace con `form-action`).

### Contradicciones escritas, sin resolver

- `PLAN-SAAS.md` (fila de `assistant`, `speech`, `whatsapp_inbox`, `notify` ≈l.45; ≈l.758; ≈l.875) y
  `PLAN-HUB.md` (≈l.71 y ≈l.461) dicen que WhatsApp **sale del SaaS** y que el Hub llama a Meta
  directamente. Esta app sigue el encargo del 2026-10-15: la cuenta de WhatsApp Business, el webhook de
  Meta y las plantillas siguen en el SaaS, y el Hub habla con él por `/internal`. Falta la ronda nueva que
  lo decida en los planes.
- Fase 1 sin tenencia: `Channel` es una sola fila compartida por todos los hubs, y las conversaciones de
  `a` y `b` comparten tablas (solo los avisos vivos van por hub), como en todas las apps de la fase 1.

### Cambios frente al producto actual

| Producto actual | Aquí | Motivo |
|---|---|---|
| El Hub **sondea** a erplora.com (`/api/v1/hub/device/whatsapp/inbox`, `statuses`) | erplora.com **empuja** al Hub por `/internal` | Contrato SaaS ↔ Hub (el SaaS empuja tras el commit; PLAN-SAAS §2) |
| La bandeja no contesta («Desde esta pantalla no se contesta») | Se contesta desde el Hub (F32, F33) | Mercado (ver «Referencia adoptada») |
| Estados `active`/`closed`, solo el borrado cierra | Abierta / pendiente / cerrada, a mano; un mensaje nuevo reabre | Mercado (Zendesk, Fresha, Shopify) |
| Asignar tecleando el identificador, solo el administrador | Selector del equipo + «Asignármela»; el responsable asigna | Mercado (Shopify, Chakra); el producto actual lo marcaba «parcial» |
| Sin notas | Notas internas (F36) | Mercado (Fresha, Intercom, Front) |
| «Necesita atención» lo ponían las recetas | Filtro **Sin leer** + recuento `awaiting_reply` | Sin recetas no hay quien la ponga |
| Fotos y audio dentro del hilo, descargados por una puerta del Hub | Enlace al adjunto en erplora.com | La CSP del Hub no deja pintar archivos de otro origen (ver «Contrato con `base`») |
| Plantillas: crear, editar, borrar desde el Hub | Solo lectura de la copia; se gestionan en erplora.com | Las plantillas son de la cuenta de WhatsApp Business, que vive en erplora.com |
| Repaso cada 15 min de conversaciones sin ficha | Se une al recibir y al guardar la ficha | No hay conversaciones anteriores a la app nueva que repasar |
| Recetas de cita y mesa (F14–F26) | Fuera | Dependen de Automatizaciones y del asistente, no portados |
| `templates.list` y ajustes solo para el administrador | Elegir plantilla para enviar: quien contesta; Ajustes: propietario y administrador | Quien contesta necesita las plantillas |
