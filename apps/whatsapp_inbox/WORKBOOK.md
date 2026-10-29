# Workbook — Bandeja de WhatsApp (app)
Prefijo: WHATSAPP_INBOX
Alcance MVP: transversal
Estado de la app: hecha en el Hub (servidor y páginas), también las plantillas, que se crean, editan y
borran desde el Hub, y el número, que se conecta, se vuelve a conectar y se desconecta desde Ajustes. erplora.com
tiene su mitad desde saas#63 (2026-10-21) y los flujos que cruzan con él están probados de punta a punta contra
el erplora.com real con un número de pruebas (solo Meta se simula): recibir, el eco del móvil, los estados,
la opción tocada, contestar, enviar una plantilla, editarla y borrarla, olvidar un número, conectar el número,
llegar al tope del mes (F13) y la lista de plantillas que erplora.com trae de Meta (F27, F28). Queda en parcial
la cabecera con archivo (F29). Los avisos de la cita y de la mesa confirmadas (F23, F26) ya salen por WhatsApp; las
respuestas automáticas que reservan cita o mesa por WhatsApp (F14–F22, F24, F25) están escritas y esperan al asistente
del Hub.

> Manual de usuario y especificación de la app `whatsapp_inbox`. Se escribe **antes** que el código:
> no se programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en
> verde (servidor y páginas). Parte del `WORKFLOW.md` del módulo Bandeja de WhatsApp del producto
> actual (`modules-workspace/modules/whatsapp_inbox`, `origin/main` `5ea1588`, v2.1.113) y de la app
> `whatsapp_inbox` del SaaS actual (`saas`, `origin/develop`). Los números de flujo se conservan
> (otras apps los citan); los nuevos empiezan en F32. F14–F26 (respuestas automáticas y reservas por
> WhatsApp) vienen de `workflow/respuestas-automaticas.md` del mismo módulo.

## Para qué sirve y para quién

La Bandeja de WhatsApp pone dentro del Hub el WhatsApp del negocio: cada cliente que escribe al
número del negocio tiene **una conversación**, con todos sus mensajes, y el equipo la lee y **contesta
desde el Hub**, sin coger el móvil. Reconoce a la persona por su número y une la conversación a su
ficha de Clientes; deja **asignar** cada conversación a alguien del equipo, marcarla **abierta,
pendiente o cerrada** y dejar **notas internas** que el cliente nunca ve. Pasadas 24 horas desde el
último mensaje del cliente, WhatsApp solo deja escribir con una **plantilla aprobada por Meta**: la
bandeja lo sabe y ofrece las plantillas del negocio, que se crean, editan y borran en sus Ajustes.

Sirve igual a la peluquería (la clienta que pide hora) y al restaurante (el comensal que pregunta por
una mesa): lo que cambia es lo que se contesta, no cómo.

Quién la usa:

- El **propietario** y el **administrador**: todo, también ver el estado del número, gestionar las
  plantillas (Ajustes) y borrar los datos de un número.
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
| Odoo (WhatsApp) | Contesta libre dentro de 24 h del último mensaje del cliente; después, solo plantilla aprobada. Las plantillas se escriben en Odoo y se mandan a Meta con «Submit for Approval» | https://odoo.com/pt_BR/forum/ajuda-1/v183-how-can-i-send-a-whatsapp-message-to-my-customer-after-24-hours-285255 |
| Zendesk | Abierta / pendiente (esperando al cliente) / resuelta; cuando el cliente contesta, vuelve a abierta | https://www.eesel.ai/blog/zendesk-ticket-status-lifecycle |
| Intercom | Notas internas en la conversación que no cambian su estado; abrir, posponer, cerrar | https://community.intercom.com/inbox-9/snoozed-conversations-reopen-when-adding-a-note-8095 |
| Front | Comentarios internos en línea con la conversación, solo para el equipo | https://www.getmacha.com/blog/front-comments-and-mentions-explained |
| Meta (WhatsApp Business Platform) | Ventana de 24 h desde el último mensaje del cliente; fuera, solo plantillas | https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages |
| SleekFlow / Chakra (bandejas de WhatsApp) | Opt-in obligatorio antes de escribir; «me la quedo» con aviso de choque entre agentes | https://help.sleekflow.io/whatsapp/whatsapp-message-opt-in · https://chakrahq.com/article/whatsapp-shared-inbox-for-customer-support-teams/ |
| WATI, Respond.io, Twilio, Gupshup, AiSensy, Interakt, Zoko (plantillas) | Crear, editar y borrar la plantilla en su propio panel, con ejemplos de las variables, y ver el veredicto de Meta en la lista | https://support.wati.io/en/articles/11463217-how-to-create-a-whatsapp-template-message |

**Gana:** una bandeja desde la que se contesta (Square, Shopify, Fresha, Vagaro, Odoo), con tres
estados (abierta, pendiente, cerrada) donde un mensaje nuevo del cliente reabre la conversación
(Zendesk), asignación a quien puede leer la bandeja con «Asignármela» que no pisa a otro (Shopify,
Chakra), notas internas en el hilo (Fresha, Intercom, Front), la regla de Meta de las 24 horas
hecha cumplir en el servidor y las plantillas gestionadas en la propia app (Odoo, WATI, Respond.io y el
producto actual).
**Por qué las demás no:** contestar solo desde el móvil (el producto actual) obliga a coger el
teléfono y deja la bandeja en solo lectura; dos estados (Shopify) no distinguen «espero al cliente»
de «está hecho»; asignar tecleando un identificador (el producto actual) no lo usa nadie; mandar a
WhatsApp Manager a crear las plantillas saca al dueño de la app para lo que hace a diario.

## Antes de empezar

1. Activar **Clientes**: la bandeja no se enciende sin ella (une cada conversación a su ficha).
2. Conectar el número de WhatsApp Business del negocio en **Bandeja de WhatsApp → Ajustes → Conectar
   WhatsApp**: se abre la ventana de Meta, se entra con Facebook y se elige el número (la cuenta de
   WhatsApp y el enlace con Meta los guarda erplora.com).
3. Crear las plantillas en **Ajustes → Plantillas de Meta → Añadir plantilla** (o en WhatsApp Manager) y
   esperar a que Meta las apruebe: las de WhatsApp Manager aparecen solas en la misma lista.
4. Escribir al número desde otro móvil y comprobar que la conversación aparece en la bandeja.

## Pantallas

### Bandeja de entrada
Menú **Bandeja de WhatsApp → Bandeja de entrada** (título «Bandeja de WhatsApp»). La ven todos los
roles. Tabla con **Contacto** (el nombre de la ficha, o el de WhatsApp, o el número), **Teléfono**,
**Estado** (Abierta, Pendiente, Cerrada), **Asignada a**, **Sin leer** y **Último mensaje** (hora si es
de hoy, «Ayer», o la fecha, en el reloj del negocio); buscador «Filtrar contacto o teléfono…»; filtros
**Estado**, **Asignada a** (A mí, Sin asignar) y **Sin leer** detrás de **Filtros**, junto al buscador (en
el móvil se abren en una hoja sobre la lista) y con **Aplicar**; 50 por página; primero la actividad
más reciente. Acción de fila **Abrir** (o tocar la fila): la conversación se abre en un panel encima
de la lista, que se queda debajo.

El panel enseña: el contacto, su número y su estado; la ficha de Clientes unida (con enlace) o
**Unir a una ficha** / **Crear ficha**; **Asignada a** con el selector del equipo y **Asignármela**;
los botones de estado **Abierta / Pendiente / Cerrada**; el hilo, del mensaje más antiguo al más
reciente (los del cliente a la izquierda, los del negocio a la derecha con su estado —Enviando…,
Enviado, Entregado, Leído, No entregado, o No enviado con **Reintentar**—, las fotos y las notas de voz dentro
de su bocadillo, los vídeos y documentos con **Abrir el adjunto**, las notas internas en amarillo con su autor); **Ver anteriores** si
hay más; y debajo el cuadro para escribir con dos pestañas: **Responder** (texto, **Enviar**, y
**Plantilla**) y **Nota interna** (**Añadir nota**). Con la ventana de 24 horas cerrada, el cuadro de
texto lo dice («Han pasado más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja
escribirle con una plantilla aprobada.») y solo queda **Plantilla**. Solo el propietario y el
administrador ven **Borrar datos de este número**.

Avisos encima de la lista: «Reconectando…» mientras vuelve la conexión en vivo; el número sin
conectar («WhatsApp no está conectado. Conecta el número del negocio en Ajustes para recibir y enviar
mensajes.») o por reconectar («WhatsApp pide volver a conectar el número en Ajustes: hasta entonces no se
puede enviar nada.»), los dos con **Ir a Ajustes** para quien puede configurar; los mensajes del plan
gastados este mes («Has usado todos los mensajes de WhatsApp de tu plan este mes. Los mensajes siguen
llegando aquí, pero no se pueden enviar hasta el mes que viene o hasta que mejores el plan.») o un plan que
no incluye ninguno («Tu plan no incluye mensajes de WhatsApp. Los mensajes siguen llegando aquí, pero no se
puede enviar nada hasta que mejores el plan.»), los dos con **Mejorar el plan** para quien puede configurar.
Vacía: «Sin conversaciones.», a la vista bajo el buscador también en el móvil; con búsqueda o filtro:
«Sin resultados»; cargando: indicador; error de lista: el motivo con **Reintentar**; error del panel: el
motivo que da el Hub o «No se pudo cargar la conversación»; una foto o una nota de voz que no carga: «No se ha
podido cargar la imagen.» o «No se ha podido cargar la nota de voz.», con **Abrir el adjunto**.

### Ajustes
Menú **Bandeja de WhatsApp → Ajustes** (título «Ajustes del canal»), solo propietario y
administrador. Tres bloques: **Tu número** («Conectado» con el número y el nombre del negocio, «Sin
conectar» o «Hay que reconectar»; sin conectar o por reconectar, «Comprobando con erplora.com…» y luego
**Conectar WhatsApp** o **Volver a conectar**, o el motivo por el que todavía no se puede; conectado o por
reconectar, **Desconectar**, que pregunta antes); **Este mes** (los mensajes
enviados frente a los del plan, y en el tope «Has usado todos los mensajes de tu plan este mes.»; si el plan
no incluye ninguno, «Tu plan no incluye mensajes de WhatsApp.»; antes de que erplora.com hable, «erplora.com
todavía no ha informado de los mensajes de este mes.»; en el tope, **Mejorar el plan**, que abre los planes
de erplora.com); y **Plantillas de Meta**: tabla con **Nombre**,
**Idioma**, **Categoría** (Utilidad, Marketing, Autenticación), **Estado en Meta** (Sin enviar a Meta,
Aprobada, En revisión, Rechazada, Pausada por Meta, Desactivada por Meta, Borrada en WhatsApp Manager;
debajo, cuando toca, «Enviándose a Meta…», «No aceptada: …», «Cambios sin enviar: …» o «Borrándose en
Meta») y **Texto**, con buscador «Buscar plantilla…», el motivo de Meta en las rechazadas y el botón
**Añadir plantilla**. Acciones de fila: **Editar** (o tocar la fila; solo las que el Hub sabe escribir),
**Volver a enviar a Meta** (la que no llegó o no se aceptó) y **Borrar**. Vacía: «Sin plantillas.» con
«Crea una con «Añadir plantilla»: Meta la revisa. Las que se hacen en WhatsApp Manager también salen
aquí.».

### Plantilla (hoja)
Se abre con **Añadir plantilla** («Nueva plantilla») o **Editar** («Editar plantilla — nombre»), encima
de Ajustes. Campos: **Nombre** («Minúsculas, números y guiones bajos. No se puede cambiar después.»),
**Idioma** y **Categoría** (Utilidad o Marketing), **Cabecera (opcional)**, **Texto** («Donde va una
variable, escribe su número entre dobles llaves, empezando por el 1.»), un **Ejemplo de la variable n**
por cada variable («Meta revisa la plantilla con estos ejemplos.»), **Pie (opcional)** y **Botones**
(**Añadir botón**: Respuesta rápida, Enlace o Llamada, con su texto y su dirección o su número;
**Quitar botón**). Botón final **Enviar a revisión de Meta** (nueva) o **Guardar y enviar a Meta**
(editar). Al editar una aprobada avisa: «Hasta que Meta apruebe los cambios, se sigue enviando la
aprobada.»; la categoría de una que Meta no ha rechazado no se puede tocar («Meta solo deja cambiar la
categoría de una plantilla que ha rechazado.»).

## Estados de cada pantalla

| Pantalla | Cargando | Vacía | Error | Sin permiso / app apagada |
|---|---|---|---|---|
| Bandeja | indicador en la tabla; el panel, «Cargando…» | «Sin conversaciones.» / «Sin resultados» | el motivo + **Reintentar**; el panel, su motivo | «No tienes permiso» / «Esta app no está activa en este negocio» en lugar de la lista |
| Panel de la conversación | «Cargando…» | «Todavía no hay mensajes.» | «No se pudo cargar la conversación» | — |
| Ajustes | indicador | «Sin plantillas.» | el motivo + **Reintentar** | igual que la bandeja |
| Plantilla (hoja) | el botón final ocupado mientras guarda | — | el motivo debajo de su campo, o arriba el que da el Hub | solo propietario y administrador la abren |

## Flujos

| ID | Flujo | Estado | Vertical |
|---|---|---|---|
| WHATSAPP_INBOX-F01 | Conectar el número de WhatsApp del negocio | hecho | comun |
| WHATSAPP_INBOX-F02 | Desconectar o volver a conectar el número | hecho | comun |
| WHATSAPP_INBOX-F03 | Recibir un mensaje en la bandeja | hecho | comun |
| WHATSAPP_INBOX-F04 | Reconocer a la clienta por su número | hecho | comun |
| WHATSAPP_INBOX-F05 | Leer una conversación | hecho | comun |
| WHATSAPP_INBOX-F06 | Ver una foto, una nota de voz o un documento | hecho | comun |
| WHATSAPP_INBOX-F07 | Asignar una conversación a alguien del equipo | hecho | comun |
| WHATSAPP_INBOX-F08 | Contestar desde la app de WhatsApp Business del móvil | hecho | comun |
| WHATSAPP_INBOX-F09 | Ver quién espera respuesta | hecho | comun |
| WHATSAPP_INBOX-F10 | Borrar los datos de un número sin ficha | hecho | comun |
| WHATSAPP_INBOX-F11 | Borrar los datos de una clienta desde su ficha | hecho | comun |
| WHATSAPP_INBOX-F12 | Unir dos fichas de la misma clienta | hecho | comun |
| WHATSAPP_INBOX-F13 | Ver el consumo del mes y llegar al tope | hecho | comun |
| WHATSAPP_INBOX-F14 | Activar «Reservar citas» | parcial — la tarjeta todavía no aparece: la respuesta automática que reserva necesita el asistente, que aún no está en el Hub (sin él nadie lee lo que escribe la clienta) | peluqueria |
| WHATSAPP_INBOX-F15 | Activar «Reservar mesa» | parcial — la tarjeta todavía no aparece: la respuesta automática que reserva necesita el asistente, que aún no está en el Hub (sin él nadie lee lo que escribe el cliente) | restaurante |
| WHATSAPP_INBOX-F16 | Decidir si las reservas por WhatsApp se confirman solas | parcial — el interruptor va en la tarjeta de F14 o F15, que todavía no aparece; mientras, la misma decisión se toma en Citas («Ajustar las reglas de reserva») y en Reservas («Elegir si las reservas se confirman solas») | comun |
| WHATSAPP_INBOX-F17 | Desactivar una respuesta automática | parcial — sin las tarjetas de F14 y F15, que todavía no aparecen, no hay respuesta automática que desactivar | comun |
| WHATSAPP_INBOX-F18 | Actualizar una respuesta automática a su versión mejorada | parcial — sin las tarjetas de F14 y F15, que todavía no aparecen, no hay respuesta automática que actualizar | comun |
| WHATSAPP_INBOX-F19 | Elegir el hueco escribiendo en vez de tocando | parcial — los huecos los ofrece la respuesta automática de F21 o F24, que necesita el asistente, que aún no está en el Hub | comun |
| WHATSAPP_INBOX-F20 | Cuando el asistente no puede contestar | parcial — la disculpa y la marca las pone la respuesta automática de F21 o F24, que necesita el asistente, que aún no está en el Hub; hoy el mensaje espera en la bandeja como sin leer (F09) | comun |
| WHATSAPP_INBOX-F21 | La clienta pide cita por WhatsApp | parcial — el asistente, que lee el mensaje, busca el hueco y redacta la respuesta, todavía no está en el Hub; hoy el mensaje se contesta a mano desde la bandeja | peluqueria |
| WHATSAPP_INBOX-F22 | La clienta anula o mueve su cita por WhatsApp | parcial — el asistente, que entiende qué pide y busca su cita, todavía no está en el Hub; hoy se anula o se mueve a mano desde la Agenda | peluqueria |
| WHATSAPP_INBOX-F23 | La clienta recibe el aviso cuando el salón confirma | hecho | peluqueria |
| WHATSAPP_INBOX-F24 | El cliente pide mesa por WhatsApp | parcial — el asistente, que lee el mensaje, busca sitio y redacta la respuesta, todavía no está en el Hub; hoy la reserva se toma a mano en Reservas | restaurante |
| WHATSAPP_INBOX-F25 | El cliente anula o cambia su mesa por WhatsApp | parcial — el asistente, que entiende qué pide y busca su reserva, todavía no está en el Hub; hoy se cambia o se anula a mano en Reservas | restaurante |
| WHATSAPP_INBOX-F26 | El cliente recibe el aviso cuando el restaurante confirma | hecho | restaurante |
| WHATSAPP_INBOX-F27 | Ver las plantillas y lo que dice Meta de cada una | hecho | comun |
| WHATSAPP_INBOX-F28 | Traer las plantillas creadas en WhatsApp Manager | hecho | comun |
| WHATSAPP_INBOX-F29 | Crear una plantilla y mandarla a revisión | parcial — la cabecera con foto, vídeo o documento no se ofrece (el Hub no guarda archivos: se hace en WhatsApp Manager) | comun |
| WHATSAPP_INBOX-F30 | Editar una plantilla | hecho | comun |
| WHATSAPP_INBOX-F31 | Borrar una plantilla | hecho | comun |
| WHATSAPP_INBOX-F32 | Contestar desde la bandeja | hecho | comun |
| WHATSAPP_INBOX-F33 | Enviar una plantilla | hecho | comun |
| WHATSAPP_INBOX-F34 | Saber si un mensaje llegó y se leyó | hecho | comun |
| WHATSAPP_INBOX-F35 | Cambiar el estado de una conversación | hecho | comun |
| WHATSAPP_INBOX-F36 | Dejar una nota interna | hecho | comun |
| WHATSAPP_INBOX-F37 | Unir la conversación a una ficha o crear la ficha | hecho | comun |
| WHATSAPP_INBOX-F38 | Saber a qué pregunta contesta lo que toca la clienta | hecho | comun |

### WHATSAPP_INBOX-F01 Conectar el número de WhatsApp del negocio
<!-- origen: old-hub:HUB_SHELL-F37 old-hub:HUB_SHELL-F170 old-saas:SAAS_WHATSAPP_INBOX-F02 fi:modules/whatsapp_inbox#query-whatsapp_inbox-settings-get old-hub:HUB-F260 old-hub:HUB-F261 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f01 wf:whatsapp-cita#rec_wa_cita-f01 wf:whatsapp-mesa#rec_wa_mesa-f01 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Abrir **Bandeja de WhatsApp → Ajustes**: **Tu número** dice «Sin conectar» y, tras «Comprobando con
   erplora.com…», ofrece **Conectar WhatsApp**.
2. Pulsar **Conectar WhatsApp**: se abre la ventana de Meta («Termina en la ventana de Meta…»); se entra
   con Facebook y se elige o se añade el número del negocio. Si ya se usa en la app WhatsApp Business del
   móvil, se escanea el código con ese móvil y se sigue usando WhatsApp en él como siempre.
3. Al terminar en la ventana, **Tu número** dice «Conectando…» y enseguida «Conectado» con el número y el
   nombre del negocio, sin recargar. Si el número venía de la app del móvil, avisa de que sus contactos y
   chats llegan a la bandeja en unos minutos.
Entra: lo que la ventana de Meta devuelve (un código de un solo uso, la cuenta de WhatsApp Business, el
número elegido y el portfolio) y la respuesta de erplora.com.
Sale: el número conectado de este negocio, sin tocar el de ningún otro; aviso
`whatsapp_inbox.channel.connected`.
Si falla: si erplora.com no contesta, **Tu número** lo dice con **Reintentar**; si WhatsApp todavía no está
disponible en ERPlora, lo dice y no ofrece conectar. Si el navegador no deja abrir la ventana, pide permitir
las ventanas emergentes; si la ventana se cierra antes de terminar o Meta no termina, no se conecta nada y
se dice por qué. Si Meta rechaza el código (caduca a los 30 segundos), el número elegido no está en la
cuenta o la cuenta tiene varios y no se eligió ninguno, se dice y no se conecta nada; una demo no puede
conectar ningún número. Si erplora.com no confirma, en un momento **Tu número** dice si quedó conectado.
Implicados: erplora.com (la cuenta de WhatsApp Business del negocio), Meta

### WHATSAPP_INBOX-F02 Desconectar o volver a conectar el número
<!-- origen: old-hub:HUB_SHELL-F171 old-hub:HUB_SHELL-F172 old-saas:SAAS_WHATSAPP_INBOX-F03 old-saas:SAAS_WHATSAPP_INBOX-F04 old-hub:HUB-F262 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f02 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes, Bandeja de entrada
Pasos:
1. Si WhatsApp retiró el permiso, **Tu número** dice «Hay que reconectar» y la bandeja avisa de que no se
   puede enviar, con **Ir a Ajustes** para quien puede configurar.
2. **Volver a conectar** abre la ventana de Meta, como al conectar (F01).
3. **Desconectar** pregunta antes («¿Desconectar el número de WhatsApp?»: deja de recibir y enviar hasta que
   se vuelva a conectar; las conversaciones guardadas no se tocan). Al confirmar, **Tu número** dice «Sin
   conectar» y «WhatsApp desconectado.».
4. Con el número de vuelta, los avisos se van solos, sin recargar.
Entra: el estado del número que erplora.com manda al Hub y su respuesta al desconectar.
Sale: las conversaciones guardadas no se tocan; aviso `whatsapp_inbox.channel.disconnected`.
Si falla: si erplora.com no contesta o no confirma, el diálogo lo dice y el número sigue como estaba (en un
momento **Tu número** dice cómo quedó); si erplora.com no tenía ningún número conectado para este negocio,
lo dice y **Tu número** queda «Sin conectar». Mientras siga «Hay que reconectar», **Enviar** dice por qué no
sale («Hay que reconectar el número en Ajustes para enviar.») y un mensaje que no se entregó por eso dice
«Hay que reconectar» con **Volver a conectar**; lo guardado se sigue leyendo.
Implicados: erplora.com

### WHATSAPP_INBOX-F03 Recibir un mensaje en la bandeja
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F07 old-saas:SAAS_WHATSAPP_INBOX-F10 fi:modules/whatsapp_inbox#command-sql-multi-stmt-whatsapp_inbox-messages-ingest old-hub:HUB-F263 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f03 wf:whatsapp-cita#rec_wa_cita-f02 wf:whatsapp-mesa#rec_wa_mesa-f02 -->
Estado: hecho
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
Si falla: si el Hub no contesta, erplora.com guarda el mensaje y lo vuelve a entregar; un número que no
es un número no se guarda.
Implicados: erplora.com, Clientes (reconoce a la clienta, F04)

### WHATSAPP_INBOX-F04 Reconocer a la clienta por su número
<!-- origen: wf:whatsapp-cita#rec_wa_cita-f03 wf:whatsapp-mesa#rec_wa_mesa-f03 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f04 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando escribe alguien cuyo número está en **una** ficha de Clientes, su conversación queda unida a
   esa ficha.
2. Cuando se crea o se corrige una ficha con el número de alguien que ya había escrito, su
   conversación se une a ella.
3. El número se compara como número: escrito con espacios, con el prefijo del país o con «00» delante
   es la misma persona en un negocio de España, y un número extranjero que conserva su cero (un fijo de
   Italia) también; los mismos dígitos con el prefijo de otro país son otra persona.
Entra: el número de la conversación y las fichas con ese número.
Sale: la conversación sabe de qué ficha es. Solo rellena un vínculo vacío: el que puso una persona se
respeta. Una ficha eliminada cuenta como vacío: su conversación queda sin ficha y otra ficha viva del
mismo número la reclama.
Si falla: si dos fichas tienen el mismo número, no se une a ninguna y el mensaje sigue guardado.
Implicados: Clientes

### WHATSAPP_INBOX-F05 Leer una conversación
<!-- origen: fi:modules/whatsapp_inbox#query-whatsapp_inbox-conversations-get fi:modules/whatsapp_inbox#query-whatsapp_inbox-conversations-list fi:modules/whatsapp_inbox#query-whatsapp_inbox-messages-list old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f05 -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Buscar por contacto o teléfono (el teléfono escrito de cualquier forma, también solo una parte) o,
   en **Filtros**, filtrar por estado, asignación o sin leer. El asistente la nombra como se dice: «Ana Lopez», «ana
   lópez» o «Zoé 🌸» llevan a la misma conversación si solo una coincide.
2. Pulsar **Abrir** en la fila (o tocar la fila).
3. El hilo aparece encima de la lista, del más antiguo al más reciente; un mensaje sin texto ni
   adjunto enseña su tipo en el idioma de quien lo lee («Ubicación», «Respuesta de botón»…), y una
   reacción (👍) aparece sobre el mensaje al que responde, sin sumar en **Sin leer**.
4. Al abrirla, **Sin leer** vuelve a «—»; un mensaje que llega con el hilo abierto también queda leído.
5. **Cerrar** vuelve a la lista.
Entra: la búsqueda, los filtros y la conversación elegida.
Sale: **Sin leer** a cero en esa conversación; nada más cambia.
Si falla: el motivo dentro del panel; la lista sigue disponible. Mientras la lista carga, la tabla lo
dice (nunca «0 conversaciones»).
Implicados: Clientes (el nombre de la ficha)

### WHATSAPP_INBOX-F06 Ver una foto, una nota de voz o un documento
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F15 old-hub:HUB-F267 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f06 -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Un mensaje con adjunto enseña su tipo (Foto, Nota de voz, Vídeo, Documento, Sticker), el nombre del
   archivo y su texto.
2. Una foto o un sticker se ven dentro de su bocadillo, sin salirse de él; tocarlos los abre a tamaño
   completo en una pestaña nueva.
3. Una nota de voz se escucha con su reproductor, en el mismo bocadillo.
4. Un vídeo o un documento: pulsar **Abrir el adjunto** lo abre en una pestaña nueva.
5. Solo se enseñan y se abren adjuntos de erplora.com, por https.
Entra: el adjunto que guarda erplora.com: su enlace, su tipo, su nombre y su pie.
Sale: nada cambia en el Hub.
Si falla: si erplora.com no entrega la foto o la nota de voz (también cuando el navegador no tiene la
sesión de erplora.com de quien entró en el dispositivo: erplora.com solo las sirve a quien la tiene), el
bocadillo dice «No se ha podido cargar la imagen.» o «No se ha podido cargar la nota de voz.» y deja **Abrir
el adjunto**; si erplora.com ya no lo guarda, la pestaña lo dice.
Implicados: erplora.com (guarda los adjuntos)

### WHATSAPP_INBOX-F07 Asignar una conversación a alguien del equipo
<!-- origen: fi:modules/whatsapp_inbox#command-sql-declarativo-whatsapp_inbox-conversations-assign old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f07 -->
Estado: hecho
Actor: empleado (a sí mismo), responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. Abrir la conversación (F05).
2. Pulsar **Asignármela**, o elegir a alguien del equipo en **Asignada a** (solo responsable,
   administrador y propietario), o **Quitar asignación**.
3. La lista y el panel enseñan la asignación, en todas las pantallas abiertas.
Entra: a quién: a mí, a una persona del equipo o a nadie.
Sale: la conversación queda asignada; aviso `whatsapp_inbox.conversation.assigned`.
Si falla: quien no puede asignar a otros (el empleado) nunca quita una conversación a otra persona:
«Esta conversación ya la lleva {nombre}.», también si se la asignaron un instante antes; tampoco puede
asignarla a otro («Solo puedes asignarte conversaciones a ti»). El responsable sí reasigna, y su
**Asignármela** tampoco pisa a nadie.
Implicados: el equipo del negocio (las personas con acceso a la bandeja)

### WHATSAPP_INBOX-F08 Contestar desde la app de WhatsApp Business del móvil
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F08 old-hub:HUB-F264 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f08 -->
Estado: hecho
Actor: propietario
Pantalla: Bandeja de entrada
Pasos:
1. Contestar como siempre desde la app WhatsApp Business del móvil.
2. La respuesta aparece en el hilo como mensaje del negocio, marcada «Desde el móvil».
3. No suma en **Sin leer**.
Entra: el eco de lo que el dueño escribe en el móvil, que manda erplora.com.
Sale: el mensaje guardado en su conversación; aviso `whatsapp_inbox.message.received`.
Si falla: si no llega, el hilo no lo enseña; el móvil lo sigue teniendo.
Implicados: erplora.com, la app WhatsApp Business del móvil

### WHATSAPP_INBOX-F09 Ver quién espera respuesta
<!-- origen: old-hub:HUB_SHELL-F61 old-hub:HUB_SHELL-F64 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f09 wf:whatsapp-cita#rec_wa_cita-f09 wf:whatsapp-mesa#rec_wa_mesa-f09 -->
Estado: hecho
Actor: todos
Pantalla: Bandeja de entrada
Pasos:
1. En **Filtros**, elegir **Estado: Abierta** y **Sin leer** y pulsar **Aplicar**: quedan las
   conversaciones cuyo último mensaje es del cliente.
2. La campana del Hub cuenta **Clientes de WhatsApp esperando respuesta** y lleva a la **Bandeja de entrada**.
   Baja sola en cuanto alguien contesta (desde el Hub o desde el móvil), la deja pendiente o la cierra, y no sale
   cuando no espera nadie.
3. En la app instalada, cada mensaje de un cliente que se queda sin contestar avisa con una notificación del
   sistema, con su nombre y lo que escribió; al tocarla se abre esa conversación en la **Bandeja de entrada**.
4. Al ordenar por cualquier columna, las filas sin ese dato van al final, en los dos sentidos.
Entra: los filtros y el orden; los mensajes de los clientes.
Sale: la lista filtrada y los recuentos (`whatsapp_inbox.conversation.summary`,
`whatsapp_inbox.conversation.count_awaiting_reply`) y los avisos (`whatsapp_inbox.conversation.notices`); nada cambia.
Si falla: el motivo con **Reintentar**.
Implicados: la campana de la barra superior, los avisos de la app instalada

### WHATSAPP_INBOX-F10 Borrar los datos de un número sin ficha
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F21 old-hub:HUB-F251 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f10 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Bandeja de entrada
Pasos:
1. Abrir la conversación de la persona que pide borrar sus datos.
2. Pulsar **Borrar datos de este número**; leer «¿Borrar los datos de este número?» con el número y el
   aviso de que no se puede deshacer; pulsar **Borrar datos** (o **Cancelar**).
3. El panel se cierra, la conversación sale de la lista y aparece «Se han borrado los datos de este
   número.».
Entra: la conversación y la confirmación.
Sale: número, nombre, textos, adjuntos y notas vaciados en el Hub al momento; conversación cerrada y
borrada. Si vuelve a escribir, empieza una conversación nueva. Aviso
`whatsapp_inbox.conversation.erased` con el identificador (ningún aviso de la app lleva el número, el
nombre ni lo que se dijo, así que el historial interno no guarda nada suyo). Después del guardado, el
Hub pide a erplora.com que olvide ese número y sus mensajes (adjuntos incluidos, que viven allí); hasta
que lo confirma, el número se guarda aparte solo para pedírselo.
Si falla: «No se pudieron borrar los datos de este número» (o el motivo). Si erplora.com no confirma,
se le vuelve a pedir, siempre para el negocio que lo borró: al pulsarlo otra vez (desde el negocio que sea) y
cada 5 minutos; pulsarlo dos veces no borra nada más.
Implicados: erplora.com

### WHATSAPP_INBOX-F11 Borrar los datos de una clienta desde su ficha
<!-- origen: old-hub:HUB-F250 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f11 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (se borra desde la ficha, en Clientes)
Pasos:
1. En Clientes se borran los datos de una ficha.
2. Todas las conversaciones unidas a esa ficha quedan vaciadas y cerradas como en F10.
Entra: el aviso `customer.customer.erased`.
Sale: las conversaciones vaciadas y cerradas; aviso `whatsapp_inbox.conversation.erased` por cada una.
Si falla: el aviso se reintenta; repetirlo no cambia nada.
Implicados: Clientes, erplora.com

### WHATSAPP_INBOX-F12 Unir dos fichas de la misma clienta
<!-- origen: old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f12 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (se une desde Clientes)
Pasos:
1. En Clientes se une una ficha duplicada a otra.
2. Las conversaciones de la ficha absorbida pasan a la que queda, sin tocar nada más.
Entra: el aviso `customer.customer.merged`.
Sale: las conversaciones, en la ficha que queda.
Si falla: el aviso se reintenta; repetirlo no cambia nada.
Implicados: Clientes

### WHATSAPP_INBOX-F13 Ver el consumo del mes y llegar al tope
<!-- origen: old-hub:HUB_SHELL-F47 old-saas:SAAS_WHATSAPP_INBOX-F13 old-saas:SAAS_WHATSAPP_INBOX-F14 old-hub:HUB-F272 old:whatsapp_inbox/workflow/canal-y-bandeja.md#whatsapp_inbox-f13 -->
Estado: hecho
Actor: todos (aviso), propietario y administrador (Ajustes)
Pantalla: Bandeja de entrada, Ajustes
Pasos:
1. **Ajustes → Este mes** enseña los mensajes enviados este mes frente a los del plan; los dos
   números los pone erplora.com. Si el plan no incluye mensajes de WhatsApp, lo dice («Tu plan no incluye
   mensajes de WhatsApp.»), nunca que no tiene límite; en el tope, «Has usado todos los mensajes de tu plan este
   mes.»; antes de que erplora.com hable, «erplora.com todavía no ha informado de los mensajes de este mes.».
2. En el tope (con un plan que no incluye ninguno, desde el primer mensaje), la bandeja lo avisa encima de
   la lista y **Enviar** lo explica en vez de enviar («Tu plan no incluye mensajes de WhatsApp: no se puede
   enviar nada.» cuando el plan no incluye ninguno); quien puede configurar ve **Mejorar el plan**, que abre
   los planes de erplora.com.
3. Lo que escriben los clientes se sigue guardando.
4. Al cambiar de mes (en el reloj del negocio) el aviso se va aunque erplora.com aún no haya hablado; si el
   plan no incluye mensajes, sigue.
Entra: el consumo y el tope del mes que manda erplora.com (0: el plan no incluye ninguno).
Sale: el aviso en la bandeja; nada se guarda.
Si falla: si erplora.com rechaza un envío por el tope (las cifras del Hub iban por detrás), el mensaje no
llega a Meta ni se cuenta, queda «No entregado» y lo dice con «Los mensajes de WhatsApp de tu plan de este mes
están gastados: no se puede enviar nada hasta el mes que viene.», nunca como motivo de Meta; si pide ir más
despacio, no es el tope: el mensaje queda «No enviado» con **Reintentar**.
Implicados: erplora.com

### WHATSAPP_INBOX-F14 Activar «Reservar citas»
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f14 -->
Estado: parcial — la tarjeta todavía no aparece: la respuesta automática que reserva necesita el asistente,
que aún no está en el Hub (sin él nadie lee lo que escribe la clienta); su aviso de cita confirmada ya se
enciende desde Automatizaciones (F23)
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes → ¿Para qué lo usas?**, la tarjeta **Reservar citas** explica qué hace.
2. Pulsa **Activar**: sale «WhatsApp contestará solo: lee tu agenda, ofrece los huecos libres, reserva,
   mueve o anula la cita de la clienta que escribe.» con **Activar** y **Ahora no**. Si «Reservar mesa» está
   encendida, debajo dice «Solo una respuesta automática puede contestar en tu número: al activar esta se
   apaga «Reservar mesa».».
3. Pulsa **Activar**: primero se apaga «Reservar mesa» si estaba encendida, y después la tarjeta pasa a
   «Activa» con **Desactivar** y dice «Listo. Escríbete desde otro móvil: “quiero cita mañana”.».
4. Aparece el interruptor de confirmación (F16).
5. Si las dos llegan a estar encendidas desde Automatizaciones, cada tarjeta encendida avisa: «“Reservar
   mesa” también está encendida: cada mensaje recibe dos respuestas automáticas. Desactiva la que no uses.»
   (o nombrando «Reservar citas»); desactivar una (F17) quita el aviso.
Entra: que Citas, Clientes, Servicios, Personal y Automatizaciones estén activas en el negocio, y el
asistente.
Sale: hoy, nada. Cuando exista, las automatizaciones «WhatsApp → cita reservada» y «Cita confirmada →
WhatsApp» quedan encendidas (la primera vez, con exactamente los permisos que piden) y «WhatsApp → mesa
reservada», en pausa: una sola respuesta automática contesta en el número. Salen en Automatizaciones, en
**Viene con «Bandeja de WhatsApp»**, y ponerlas en pausa allí deja esta tarjeta apagada.
Si falla: la tarjeta dice el motivo, pone en pausa lo que llegó a encender y vuelve a encender la respuesta
que había apagado, para que el número nunca se quede sin contestar; sin permiso, «Solo un dueño o un
administrador puede activarlo.»; si falta una app que pide, la tarjeta dice «“Reservar citas” necesita la
aplicación …» con **Ver aplicaciones**; sin Citas, la tarjeta no aparece.
Implicados: APPOINTMENT-F18, APPOINTMENT-F19, CUSTOMER-F26, FLOW-F31, FLOW-F33, FLOW-F34, FLOW-F35,
WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F23

### WHATSAPP_INBOX-F15 Activar «Reservar mesa»
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f15 -->
Estado: parcial — la tarjeta todavía no aparece: la respuesta automática que reserva necesita el asistente,
que aún no está en el Hub (sin él nadie lee lo que escribe el cliente)
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes → ¿Para qué lo usas?**, la tarjeta **Reservar mesa** explica qué hace.
2. Pulsa **Activar**: sale «WhatsApp contestará solo: mira las mesas libres, reserva la mesa de quien
   escribe y le contesta. ¿Lo activas?» con **Activar** y **Ahora no**. Si «Reservar citas» está encendida,
   debajo dice «Solo una respuesta automática puede contestar en tu número: al activar esta se apaga
   «Reservar citas».».
3. Pulsa **Activar**: primero se apagan «Reservar citas» y su aviso de cita confirmada si estaban
   encendidos, y después la tarjeta pasa a «Activa» con **Desactivar** y dice «Listo. Escríbete desde otro
   móvil: “quiero mesa para dos mañana”.».
4. Aparece el interruptor de confirmación (F16).
5. Con las dos encendidas desde Automatizaciones, el mismo aviso que en F14, nombrando «Reservar citas».
Entra: que Reservas, Clientes y Automatizaciones estén activas en el negocio, y el asistente.
Sale: hoy, nada. Cuando exista, la automatización «WhatsApp → mesa reservada» encendida con exactamente sus
permisos y las de la cita en pausa, como en F14; sale en Automatizaciones, en **Viene con «Bandeja de
WhatsApp»**, y ponerla en pausa allí deja esta tarjeta apagada.
Si falla: igual que F14, nombrando Reservas o Clientes; la respuesta de citas que se apagó vuelve a
encenderse.
Implicados: RESERVATION-F17, FLOW-F33, FLOW-F34, FLOW-F35, WHATSAPP_INBOX-F24

### WHATSAPP_INBOX-F16 Decidir si las reservas por WhatsApp se confirman solas
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f16 -->
Estado: parcial — el interruptor va en la tarjeta de F14 o F15, que todavía no aparece; mientras, la misma
decisión se toma en Citas («Ajustar las reglas de reserva») y en Reservas («Elegir si las reservas se
confirman solas»)
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Con la tarjeta en «Activa», elige en su interruptor **Las citas se confirman solas** (o **Las reservas se
   confirman solas**) o **Las reviso yo antes**.
2. Con «Las reviso yo antes» sale dónde esperan: «Cada cita nueva te espera en la Agenda con “Confirmar”.»
   o «Cada reserva nueva te espera en Reservas con “Confirmar”.».
3. El cambio se guarda al momento en Citas o en Reservas, no en esta app.
4. El interruptor no abarca lo mismo en los dos negocios: en Citas decide solo las citas que reserva la
   propia clienta; en Reservas decide toda reserva nueva, también la que se toma a mano.
Entra: cómo confirma hoy la app que lleva la agenda. Sin cambiarlo, Citas confirma sola y Reservas revisa.
Sale: hoy, nada desde aquí. Cuando exista, la regla cambiada en Citas o en Reservas; la respuesta
automática la lee antes de cada reserva y elige la frase que manda. En la peluquería, con «Las citas se
confirman solas», la cita nace confirmada y eso dispara también el aviso de F23.
Si falla: «No se pudo guardar cómo se confirman las citas.» (o «las reservas») «Inténtalo otra vez.», y el
interruptor vuelve a como estaba.
Implicados: APPOINTMENT-F18, APPOINTMENT-F19, RESERVATION-F04, WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15

### WHATSAPP_INBOX-F17 Desactivar una respuesta automática
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f17 -->
Estado: parcial — sin las tarjetas de F14 y F15, que todavía no aparecen, no hay respuesta automática que
desactivar
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. En la tarjeta «Activa», pulsa **Desactivar**.
2. La tarjeta pasa a «Desactivada» con **Activar**; WhatsApp deja de contestar solo.
Entra: la tarjeta elegida.
Sale: hoy, nada. Cuando exista, se ponen en pausa primero los avisos que la acompañan y la respuesta
automática la última, para que nunca quede una respuesta encendida detrás de una tarjeta apagada. Desactivar
es poner en pausa, nunca borrar: en Automatizaciones sigue en su lista como «En pausa», con sus permisos y
su historial, y ponerla en pausa desde allí deja esta tarjeta apagada igual.
Si falla: la tarjeta dice el motivo y se vuelve a pintar con lo que de verdad sigue encendido.
Implicados: FLOW-F34, WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15

### WHATSAPP_INBOX-F18 Actualizar una respuesta automática a su versión mejorada
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f18 -->
Estado: parcial — sin las tarjetas de F14 y F15, que todavía no aparecen, no hay respuesta automática que
actualizar
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. Si la app trae una versión mejor que la que se encendió, la tarjeta dice «Hay una versión mejorada de
   esta respuesta automática.» con **Actualizar**.
2. Pulsa **Actualizar**: sale que la nueva sustituye a la actual, también los cambios hechos a mano, y que
   seguirá encendida o en pausa como esté.
3. Confirma con **Actualizar**: «Hecho: esta respuesta automática ya funciona con la última versión.».
Entra: qué automatizaciones de la tarjeta tienen una versión nueva.
Sale: hoy, nada. Cuando exista, solo esas automatizaciones vuelven a la versión que trae la app hoy,
conservando su encendido y su historial: es lo mismo que «Restaurar la de fábrica» en Automatizaciones.
Si falla: «Esta respuesta automática ya no existe aquí: vuelve a activarla.» o «No se pudo actualizar.
Inténtalo otra vez.»; el aviso sigue solo para lo que no se actualizó.
Implicados: FLOW-F35, WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15

### WHATSAPP_INBOX-F19 Elegir el hueco escribiendo en vez de tocando
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f19 -->
Estado: parcial — los huecos los ofrece la respuesta automática de F21 o F24, que necesita el asistente, que aún
no está en el Hub
Actor: cliente
Pantalla: WhatsApp: chat del cliente
Pasos:
1. La respuesta automática le ofrece una lista de horas (botón **Ver huecos** en la cita; horas en la mesa).
2. Ella puede tocar una opción, o escribir `el 2`, `la segunda` o `12:30`.
3. Si lo escrito señala una sola de las opciones ofrecidas en las últimas 24 horas, se comprueba que sigue
   libre y se reserva como si la hubiera tocado; si no está claro, se le vuelve a ofrecer.
Entra: la última lista ofrecida a ese número (solo 24 horas).
Sale: hoy, nada. Cuando exista, la reserva (F21 o F24); la lista se olvida en cuanto reserva, anula o mueve.
Si falla: si no se puede guardar la lista, recibe su respuesta igual y la próxima vez se le vuelve a
ofrecer.
Implicados: APPOINTMENT-F02, RESERVATION-F05, WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F24, WHATSAPP_INBOX-F38

### WHATSAPP_INBOX-F20 Cuando el asistente no puede contestar
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f20 -->
Estado: parcial — la disculpa y la marca las pone la respuesta automática de F21 o F24, que necesita el
asistente, que aún no está en el Hub; hoy el mensaje espera en la bandeja como sin leer (F09)
Actor: sistema
Pantalla: WhatsApp: chat del cliente
Pasos:
1. Si el asistente falla o no dice nada, el cliente recibe un texto fijo: en la cita «Perdona, ahora mismo
   no puedo mirar la agenda. Alguien del equipo te contestará por aquí en cuanto pueda.»; en la mesa, igual
   con «las reservas».
2. Su conversación queda marcada «Necesita atención» y sale en **Ver quién espera respuesta** (F09).
3. No se le manda nada más en ese turno.
4. La marca se pone solo en ese caso y cuando la respuesta automática no contesta porque se gastaron los
   mensajes del plan del mes (F13); cuando es el propio asistente quien contesta que alguien del negocio le
   responderá, la conversación no se marca.
Entra: lo que contestó el asistente en ese turno.
Sale: hoy, nada. Cuando exista, una disculpa y la marca de atención.
Si falla: si la marca no se puede poner, la disculpa sale igual y el mensaje sigue sin leer en la bandeja.
Implicados: WHATSAPP_INBOX-F09, WHATSAPP_INBOX-F13, WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F24

### WHATSAPP_INBOX-F21 La clienta pide cita por WhatsApp
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f21 -->
Estado: parcial — el asistente, que lee el mensaje, busca el hueco y redacta la respuesta, todavía no está
en el Hub; hoy el mensaje se contesta a mano desde la bandeja
Actor: cliente
Pantalla: WhatsApp: chat del cliente
Pasos:
1. La clienta escribe, por ejemplo, `¿Tenéis hueco mañana por la tarde para un corte?`.
2. Recibe al momento un acuse fijo: «¡Gracias por escribirnos! Miro la agenda y te contesto ahora mismo.».
3. Si no tiene ficha, se le crea una con origen WhatsApp.
4. Si su mensaje fija servicio, día y hora y está libre, se reserva con la profesional que trabaja a esa
   hora; si no, recibe los huecos libres de verdad para tocar o escribir (F19). El asistente nunca elige la
   hora por ella.
5. Recibe la respuesta: que la cita está reservada (día, hora y profesional) si el salón confirma solo, o
   que se la ha apuntado y el salón se la confirma, según F16. La cita está en la Agenda.
Entra: el mensaje escrito o la opción tocada (no el historial, ni las respuestas del dueño, ni fotos sin
texto).
Sale: hoy, nada. Cuando exista, ficha nueva si hacía falta (Clientes), conversación unida a la ficha, cita
confirmada o pendiente (Citas, `appointment.appointment.created`) y respuesta por WhatsApp. Los servicios y
su duración salen del catálogo de Servicios; las horas libres, de Citas.
Si falla: F20; sin hueco, se le dice por qué y se le ofrecen otros. Con los mensajes del plan del mes
gastados no recibe nada (ni acuse, ni respuesta, ni cita) y su mensaje queda en la bandeja con «Necesita
atención» (F13).
Implicados: APPOINTMENT-F02, APPOINTMENT-F18, CUSTOMER-F10, CUSTOMER-F26, WHATSAPP_INBOX-F16,
WHATSAPP_INBOX-F19, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F22 La clienta anula o mueve su cita por WhatsApp
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f22 -->
Estado: parcial — el asistente, que entiende qué pide y busca su cita, todavía no está en el Hub; hoy se anula o se mueve a mano desde la Agenda
Actor: cliente
Pantalla: WhatsApp: chat del cliente
Pasos:
1. La clienta escribe `no puedo ir` o `¿me la cambias al jueves?`.
2. Se busca su cita por su número; con dos próximas, se le pregunta cuál.
3. Anular: se anula con las reglas del salón (si se permite y con qué antelación); fuera de plazo se le dice
   y la cita sigue.
4. Mover: se le ofrecen huecos y se mueve la misma cita, con la misma profesional y el mismo servicio.
5. Recibe la respuesta con lo que ha pasado.
Entra: el mensaje y las citas de esa clienta.
Sale: hoy, nada. Cuando exista, la cita anulada o movida en Citas como si la anulara o moviera ella misma
(`appointment.appointment.cancelled`, `appointment.appointment.rescheduled`); nunca la de otra persona.
Si falla: F20; si Citas lo rechaza, se le explica. Con los mensajes del plan del mes gastados no se anula ni
se mueve nada, no recibe respuesta y la conversación queda con «Necesita atención» (F13).
Implicados: APPOINTMENT-F04, APPOINTMENT-F06, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F23 La clienta recibe el aviso cuando el salón confirma
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f23 -->
Estado: hecho
Actor: propietario, responsable, cliente
Pantalla: Automatizaciones; WhatsApp: chat del cliente
Pasos:
1. En Automatizaciones, debajo de la galería, en **Viene con «Bandeja de WhatsApp»**, enciende «Avisar por
   WhatsApp a la clienta cuando se confirma su cita» (FLOW-F33). Para avisar pasadas las 24 horas, crea en
   **Ajustes** la plantilla de Utilidad `appointment_confirmed` con cuatro datos (el día, la hora, el servicio
   y el profesional) y espera a que Meta la apruebe (F29).
2. Con «Las reviso yo antes», la encargada pulsa **Confirmar** en la Agenda.
3. Si la clienta tiene conversación de WhatsApp con el negocio, recibe «¡Confirmada! Te esperamos el {día} a
   las {hora} para tu {servicio} con {profesional}.», con el día y la hora en el idioma y el reloj del
   negocio.
4. La conversación se busca con el teléfono de la ficha de la clienta, y solo vale el número internacional
   exacto de una conversación de este negocio: un teléfono incompleto no avisa a nadie, y el aviso nunca sale
   a la conversación de otra persona.
5. Fuera de las 24 horas desde el último mensaje de la clienta, el aviso sale con la plantilla de Utilidad
   aprobada, porque WhatsApp no deja mandar texto libre.
6. El aviso sale con cualquier confirmación de una cita con conversación, también la de una cita que nace ya
   confirmada porque «Las citas se confirman solas» está encendido (F16).
Entra: la cita confirmada (Citas), la ficha de la clienta (Clientes) y la conversación cuyo número es
exactamente el de su ficha.
Sale: un WhatsApp a la clienta, que se ve en su conversación de la bandeja (`whatsapp_inbox.message.sent`);
el mismo aviso nunca sale dos veces.
Si falla: el motivo queda en el historial de la automatización y nada se ve en la Agenda. Sin teléfono en la
ficha o sin conversación con ese número, la automatización se para en su paso, sin error; fuera de las 24
horas sin la plantilla aprobada, con el número sin conectar o con los mensajes del mes gastados, se para con
el motivo. Lo que Meta rechace después se ve en la conversación («No entregado»).
Implicados: APPOINTMENT-F03, APPOINTMENT-F18, CUSTOMER-F11, FLOW-F31, FLOW-F33, WHATSAPP_INBOX-F14,
WHATSAPP_INBOX-F29, WHATSAPP_INBOX-F33

### WHATSAPP_INBOX-F24 El cliente pide mesa por WhatsApp
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f24 -->
Estado: parcial — el asistente, que lee el mensaje, busca sitio y redacta la respuesta, todavía no está en
el Hub; hoy la reserva se toma a mano en Reservas
Actor: cliente
Pantalla: WhatsApp: chat del cliente
Pasos:
1. El cliente escribe, por ejemplo, `Mesa para 4 el sábado a las 21`.
2. Recibe al momento un acuse fijo: «¡Gracias por escribirnos! Miro el libro de reservas y te contesto
   ahora mismo.».
3. Se mira si ese día cierra, los turnos y las plazas libres; la hora y cuántos son los dice el cliente,
   nunca el asistente.
4. Si hay sitio, se reserva; si no, se le ofrecen horas para tocar o escribir (F19), o se le apunta en la
   lista de espera.
5. Recibe la respuesta: que la mesa está reservada, o que se la ha apuntado y el restaurante se la
   confirma, según F16.
Entra: el mensaje escrito o la opción tocada, y la ficha de su teléfono si ya la tiene.
Sale: hoy, nada. Cuando exista, reserva confirmada o pendiente, o entrada en la lista de espera (Reservas,
`reservation.reservation.created`), con su teléfono y el nombre que dé en el mensaje (si no da ninguno, su
teléfono hace de nombre), ligada a su ficha o, si su teléfono no tiene, a una nueva de origen WhatsApp
(Clientes), y respuesta por WhatsApp.
Si falla: F20; sin plazas o con demasiados comensales, se le explica. Con los mensajes del plan del mes
gastados no recibe nada (ni acuse, ni respuesta, ni reserva) y su mensaje queda en la bandeja con
«Necesita atención» (F13).
Implicados: RESERVATION-F05, RESERVATION-F14, RESERVATION-F17, CUSTOMER-F10, WHATSAPP_INBOX-F16,
WHATSAPP_INBOX-F19, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F25 El cliente anula o cambia su mesa por WhatsApp
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f25 -->
Estado: parcial — el asistente, que entiende qué pide y busca su reserva, todavía no está en el Hub; hoy se cambia o se anula a mano en Reservas
Actor: cliente
Pantalla: WhatsApp: chat del cliente
Pasos:
1. El cliente escribe `no podemos ir` o `¿podemos pasarla a las 22?`.
2. Se busca su reserva por su número; con dos próximas, se le pregunta cuál.
3. Se anula o se cambia con las reglas del restaurante y se le contesta con lo que ha pasado.
Entra: el mensaje y las reservas de ese cliente.
Sale: hoy, nada. Cuando exista, la reserva anulada o cambiada en Reservas
(`reservation.reservation.status_changed`, `reservation.reservation.updated`); nunca la de otra persona.
Si falla: F20; si Reservas lo rechaza, se le explica.
Implicados: RESERVATION-F09, RESERVATION-F18, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F26 El cliente recibe el aviso cuando el restaurante confirma
<!-- origen: old:whatsapp_inbox/workflow/respuestas-automaticas.md#whatsapp_inbox-f26 -->
Estado: hecho
Actor: propietario, responsable, cliente
Pantalla: Automatizaciones; Reservas; WhatsApp: chat del cliente
Pasos:
1. En Automatizaciones, debajo de la galería, en **Viene con «Bandeja de WhatsApp»**, enciende «Avisar por
   WhatsApp al cliente cuando se confirma su reserva» (FLOW-F33). Para avisar pasadas las 24 horas, crea en
   **Ajustes** la plantilla de Utilidad `reservation_confirmed` con tres datos (el día, la hora y los
   comensales) y espera a que Meta la apruebe (F29).
2. Con «Confirmar solas las reservas nuevas» apagado, el encargado pulsa «Confirmar» en la reserva Pendiente,
   en Reservas.
3. Si el cliente tiene conversación de WhatsApp con el negocio, recibe «¡Confirmada! Te esperamos el {día} a
   las {hora}, mesa para {comensales}.», con el día y la hora en el idioma y el reloj del negocio.
4. La conversación se busca con el teléfono de la reserva (el de su conversación, si la reserva llegó por
   WhatsApp), y solo vale el número internacional exacto de una conversación de este negocio: un teléfono
   incompleto no avisa a nadie, y el aviso nunca sale a la conversación de otra persona.
5. Fuera de las 24 horas desde el último mensaje del cliente, el aviso sale con la plantilla de Utilidad
   aprobada, porque WhatsApp no deja mandar texto libre.
6. El aviso sale con cualquier confirmación de una reserva con conversación, también la de una reserva que
   nace ya confirmada porque «Confirmar solas las reservas nuevas» está encendido. Sentarla, completarla,
   cancelarla o marcar que no se presentó no avisan.
Entra: la reserva confirmada (Reservas) y la conversación cuyo número es exactamente el de la reserva.
Sale: un WhatsApp al cliente, que se ve en su conversación de la bandeja (`whatsapp_inbox.message.sent`);
el mismo aviso nunca sale dos veces.
Si falla: el motivo queda en el historial de la automatización y nada se ve en Reservas. Sin teléfono en la
reserva o sin conversación con ese número, la automatización se para en su paso, sin error; fuera de las 24
horas sin la plantilla aprobada, con el número sin conectar o con los mensajes del mes gastados, se para con
el motivo. Lo que Meta rechace después se ve en la conversación («No entregado»). Un negocio sin Reservas no
ve esta automatización.
Implicados: RESERVATION-F07, RESERVATION-F19, FLOW-F31, FLOW-F33, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F29,
WHATSAPP_INBOX-F33

### WHATSAPP_INBOX-F27 Ver las plantillas y lo que dice Meta de cada una
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F16 fi:modules/whatsapp_inbox#query-whatsapp_inbox-templates-list old-hub:HUB-F268 old:whatsapp_inbox/workflow/plantillas.md#whatsapp_inbox-f27 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. **Ajustes → Plantillas de Meta** lista las plantillas con su estado en Meta; una rechazada enseña
   «Motivo de Meta: …».
2. Cuando Meta cambia el veredicto, la tabla cambia sola.
Entra: la lista que erplora.com manda al Hub cada vez que cambia.
Sale: nada; una plantilla que Meta ya no lista queda «Borrada en WhatsApp Manager» y no se puede enviar.
Si falla: si la tabla no carga, el motivo con **Reintentar**; si erplora.com no manda la lista, se queda
la última que mandó.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F28 Traer las plantillas creadas en WhatsApp Manager
<!-- origen: old:whatsapp_inbox/workflow/plantillas.md#whatsapp_inbox-f28 -->
Estado: hecho
Actor: sistema
Pantalla: Ajustes
Pasos:
1. El negocio crea una plantilla en WhatsApp Manager.
2. Aparece en **Ajustes → Plantillas de Meta** en cuanto erplora.com la manda, con su texto, sus
   variables, sus botones y su estado.
3. Las que el Hub no sabe rellenar al enviar (cabecera con foto, vídeo, documento o una variable;
   variables con nombre en vez de número; códigos de verificación) se ven con su estado y «No se puede
   enviar ni editar aquí: se gestiona en WhatsApp Manager.», pero no se ofrecen para enviar ni se editan
   aquí; sí se pueden borrar.
Entra: la lista de plantillas que erplora.com trae de Meta.
Sale: cada plantilla guardada como la tiene Meta.
Si falla: nunca pisa una plantilla del Hub que todavía va hacia Meta ni trae de vuelta una borrada aquí.
Implicados: erplora.com, WhatsApp Manager

### WHATSAPP_INBOX-F29 Crear una plantilla y mandarla a revisión
<!-- origen: old:whatsapp_inbox/workflow/plantillas.md#whatsapp_inbox-f29 -->
Estado: parcial — la cabecera con foto, vídeo o documento no se ofrece (el Hub no guarda archivos: se
hace en WhatsApp Manager)
Actor: propietario, administrador
Pantalla: Ajustes, Plantilla (hoja)
Pasos:
1. En **Ajustes → Plantillas de Meta**, pulsar **Añadir plantilla**.
2. Escribir el nombre, elegir idioma y categoría (Utilidad o Marketing) y escribir el texto con `{{1}}`,
   `{{2}}`… donde van las variables, con un ejemplo de cada una; si se quiere, cabecera, pie y botones
   (respuestas rápidas juntas, hasta dos enlaces y una llamada; diez como mucho).
3. Pulsar **Enviar a revisión de Meta**: la plantilla sale en la lista «Sin enviar a Meta» con
   «Enviándose a Meta…» y pasa a «En revisión» en cuanto Meta la recibe.
4. Cuando Meta decide, pasa sola a «Aprobada» (ya se puede enviar, F33) o a «Rechazada» con su motivo.
Entra: nombre, idioma, categoría, cabecera, texto, ejemplos, pie, botones y una clave del guardado (la
misma al reintentar).
Sale: la plantilla guardada y, tras el guardado, entregada a erplora.com para que la registre en Meta;
aviso `whatsapp_inbox.template.created`.
Si falla: lo que Meta no aceptaría se dice debajo de su campo (un nombre con mayúsculas o espacios,
variables sin numerar en orden o con nombre, una variable sin ejemplo, una variable en la cabecera o
el pie, más de 60 caracteres en la cabecera o el pie, botones mezclados o de más); el mismo nombre en el
mismo idioma: «Ya hay una plantilla «…» en ese idioma.». Si Meta no la acepta o pide esperar, la lista
dice «No aceptada: …» con el motivo de Meta («Meta no ha contestado. Inténtalo de nuevo en unos
minutos.» cuando Meta no contesta: nunca culpa a ERPlora) y se corrige con **Editar** o se repite con
**Volver a enviar a Meta**. Si erplora.com no contesta, la lista lo dice y **Volver a enviar a Meta** la
entrega otra vez con la misma clave (también sola, cada 5 minutos): nunca se registra dos veces. Con
el mes gastado se puede crear igual.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F30 Editar una plantilla
<!-- origen: old:whatsapp_inbox/workflow/plantillas.md#whatsapp_inbox-f30 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes, Plantilla (hoja)
Pasos:
1. En **Ajustes → Plantillas de Meta**, pulsar **Editar** en la fila (o tocarla).
2. Cambiar el texto, los ejemplos, la cabecera, el pie o los botones (la categoría, solo si Meta la
   rechazó; el nombre y el idioma no cambian) y pulsar **Guardar y enviar a Meta**.
3. Una plantilla aprobada se sigue enviando tal como Meta la aprobó mientras el cambio va de camino
   («Hasta que Meta apruebe los cambios, se sigue enviando la aprobada.»); en cuanto Meta lo recibe, pasa
   a «En revisión» con el texto nuevo.
Entra: el cambio y una clave del guardado (la misma al reintentar).
Sale: el cambio guardado aparte hasta que Meta lo recibe, para que su veredicto nunca caiga sobre un
texto cambiado después; aviso `whatsapp_inbox.template.updated`.
Si falla: una plantilla en revisión no se cambia («Meta está revisando esta plantilla: espera a su
veredicto para cambiarla.»), ni una que va de camino («Esta plantilla se está enviando a Meta: espera
un momento.»); la que tiene algo que el Hub no sabe escribir, o está desactivada o borrada en WhatsApp
Manager, se cambia allí («Esta plantilla se cambia en WhatsApp Manager: el Hub no puede cambiarla.»);
la categoría de una aprobada: «Meta solo deja cambiar la categoría de una plantilla que ha rechazado.».
Si el cambio no llega a Meta, la fila dice «Cambios sin enviar: …» con **Volver a enviar a Meta**; lo
demás, como en F29.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F31 Borrar una plantilla
<!-- origen: old:whatsapp_inbox/workflow/plantillas.md#whatsapp_inbox-f31 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes → Plantillas de Meta**, pulsar **Borrar** en la fila.
2. Leer «¿Borrar esta plantilla?» con su nombre y su idioma y el aviso «Una plantilla aprobada tarda
   días en volver a aprobarse.»; pulsar **Borrar plantilla** (o **Cancelar**).
3. Ya no se puede enviar. Sale de la lista en cuanto Meta confirma; mientras tanto la fila dice
   «Borrándose en Meta».
Entra: la plantilla.
Sale: la plantilla borrada aquí y, tras el guardado, el borrado de esa plantilla en ese idioma pedido a
erplora.com (una que Meta nunca tuvo se borra sin preguntar); aviso `whatsapp_inbox.template.deleted`.
Si falla: si Meta ya no la tenía, cuenta como borrada; si erplora.com o Meta no contestan, la fila dice
«Borrándose en Meta» con el motivo y **Volver a enviar a Meta** lo pide otra vez. La lista que manda
Meta nunca la trae de vuelta, aunque la siga listando hasta borrarla; una nueva con el mismo nombre sí
se puede crear.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F32 Contestar desde la bandeja
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F12 old-hub:HUB-F266 -->
Estado: hecho
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
Si falla: si no se puede ni guardar, el cuadro conserva el texto con el motivo: han pasado más de 24
horas desde el último mensaje del cliente («Han pasado más de 24 horas…»), o el número no está
conectado, el mes está gastado o el Hub no llega a erplora.com (el cuadro lo dice antes de escribir).
Si erplora.com lo rechaza (número bloqueado, tope del mes…), la burbuja dice «No entregado» y su motivo.
Si erplora.com no contesta, no confirma o pide ir más despacio, la burbuja dice «No enviado» con
**Reintentar**, que lo entrega otra vez con la misma clave: nunca sale dos veces. Sale siempre por el número
del negocio que lo envió, aunque lo reintente otro desde la bandeja compartida de la fase 1.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F33 Enviar una plantilla
<!-- origen: old-hub:HUB-F266 -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En **Responder**, pulsar **Plantilla**: se abre «Enviar una plantilla» con las plantillas
   **aprobadas** que el Hub sabe rellenar (nombre, idioma, categoría y texto).
2. Elegir una y rellenar sus variables (`{{1}}`, `{{2}}`…); la vista previa enseña el texto final.
3. Pulsar **Enviar**: el mensaje aparece en el hilo como en F32.
También por el asistente o la API a un número que aún no ha escrito («envía la plantilla de
recordatorio a este número»): se crea su conversación. Una automatización no usa este envío sino uno más
estrecho, que nunca crea una conversación: solo escribe a la que ya existe con el número internacional exacto
(FLOW-F31, F23). Un número escrito a mano es del país del negocio
salvo que lleve su prefijo.
Entra: la plantilla (nombre e idioma), sus variables, una clave del mensaje y la conversación o el
número.
Sale: el mensaje guardado y entregado como en F32; aviso `whatsapp_inbox.message.sent`.
Si falla: una plantilla de **Marketing** solo se envía a una clienta con ficha y con el consentimiento
de marketing por WhatsApp dado en Clientes («Esta clienta no ha dado su consentimiento para recibir
publicidad por WhatsApp.»); una plantilla no aprobada, borrada o que el Hub no sabe rellenar no se
puede elegir; faltan variables: «Rellena todas las variables de la plantilla.»; un número incompleto:
«Esto no es un número de teléfono.» y no se guarda nada; el resto, como en F32.
Implicados: Clientes (el consentimiento de marketing), erplora.com, Meta

### WHATSAPP_INBOX-F34 Saber si un mensaje llegó y se leyó
<!-- origen: old-saas:SAAS_WHATSAPP_INBOX-F09 -->
Estado: hecho
Actor: todos
Pantalla: Bandeja de entrada
Pasos:
1. Cada mensaje enviado lleva su estado: **Enviando…**, **Enviado**, **Entregado**, **Leído**, **No
   entregado** (con el motivo de Meta o de erplora.com) o **No enviado** (con **Reintentar**). Si no se
   entregó porque WhatsApp retiró el permiso del número, dice «Hay que reconectar» con **Volver a conectar**,
   que lleva a **Tu número** en **Ajustes** (solo quien puede configurar; sin **Reintentar**, que volvería a
   fallar); con el número de vuelta, el mensaje queda con «El permiso de WhatsApp para tu número había
   caducado.».
2. Cambia solo, sin recargar, cuando erplora.com lo cuenta.
Entra: cada estado que erplora.com recibe de Meta para un mensaje del Hub.
Sale: el estado solo avanza (un «Entregado» que llega tarde no deshace un «Leído»); un estado que llega
antes que la respuesta de erplora.com se casa con el mensaje por su clave y no se pierde; aviso
`whatsapp_inbox.message.status_changed`.
Si falla: un estado de un mensaje que el Hub no conoce se ignora sin error.
Implicados: erplora.com, Meta

### WHATSAPP_INBOX-F35 Cambiar el estado de una conversación
<!-- origen: nuevo (Zendesk, Fresha y Shopify Inbox: abierta, pendiente y cerrada; ver «Referencia adoptada») -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel, pulsar **Abierta**, **Pendiente** (esperando al cliente) o **Cerrada** (resuelta).
2. La lista lo enseña al momento en todas las pantallas.
3. Si el cliente vuelve a escribir, la conversación vuelve a **Abierta** sola.
Entra: el estado elegido.
Sale: aviso `whatsapp_inbox.conversation.status_changed`.
Si falla: el motivo dentro del panel; el estado no cambia.
Implicados: ninguna otra app

### WHATSAPP_INBOX-F36 Dejar una nota interna
<!-- origen: nuevo (Fresha, Intercom y Front: notas internas en el hilo; ver «Referencia adoptada») -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel, pestaña **Nota interna**: escribir y pulsar **Añadir nota**.
2. La nota sale en el hilo, en amarillo, con su autor y su hora; el cliente nunca la ve.
3. Quien la escribió, el responsable, el administrador y el propietario pueden **Borrarla**.
Entra: el texto de la nota.
Sale: aviso `whatsapp_inbox.note.added` / `whatsapp_inbox.note.deleted`.
Si falla: el motivo en el panel; el empleado no borra la nota de otra persona.
Implicados: ninguna otra app

### WHATSAPP_INBOX-F37 Unir la conversación a una ficha o crear la ficha
<!-- origen: nuevo (Square, Fresha y Shopify Inbox: la conversación lleva a la ficha del cliente; ver «Referencia adoptada») -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario
Pantalla: Bandeja de entrada
Pasos:
1. En el panel sin ficha, **Unir a una ficha** busca en Clientes por nombre, teléfono o email; elegir
   una la une.
2. O **Crear ficha**: crea en Clientes una ficha con el nombre de WhatsApp (o el número) y el número,
   con origen «WhatsApp», y la une.
3. Con ficha, **Ver ficha** lleva a ella y **Desunir** la quita.
Entra: la ficha elegida, o nada para crearla.
Sale: aviso `whatsapp_inbox.conversation.customer_linked`.
Si falla: los motivos de Clientes (por ejemplo, un número que no es válido).
Implicados: Clientes

### WHATSAPP_INBOX-F38 Saber a qué pregunta contesta lo que toca la clienta
<!-- origen: old-hub:HUB-F265 -->
Estado: hecho
Actor: cliente, sistema
Pantalla: Bandeja de entrada
Pasos:
1. El negocio envía una plantilla con respuestas rápidas («Sí», «No») o un mensaje con botones.
2. La clienta toca una opción: en el hilo sale con el texto de la opción, como respuesta de botón.
3. La app que espera esa respuesta (un recordatorio de cita) sabe a cuál de sus mensajes contesta,
   aunque haya dos preguntas abiertas.
Entra: la opción tocada (su identificador y su texto) y el mensaje al que contesta, que manda
erplora.com o que el Hub lee de lo que mandó Meta.
Sale: la opción guardada con el mensaje; aviso `whatsapp_inbox.message.received` con el mensaje del Hub
al que contesta y la opción, vacíos (nunca ausentes) cuando no contesta a nada que enviara este Hub.
Si falla: si contesta a un mensaje que no envió este Hub (o cita uno suyo propio), el aviso no apunta a
ninguno.
Implicados: erplora.com; Citas y Reservas, cuando avisen por WhatsApp

## Servicios: lo que entra y lo que sale

### Lo que ofrece: consultas (leen, no cambian nada)

| Operación | Qué devuelve |
|---|---|
| `whatsapp_inbox.conversation.list` | Conversaciones, con búsqueda por contacto o teléfono y filtros de estado, asignación, sin leer y ficha |
| `whatsapp_inbox.conversation.detail` | Una conversación (por id, número o nombre) con su ficha, su asignación y si la ventana de 24 h está abierta |
| `whatsapp_inbox.conversation.by_phone` | La conversación de un número exacto (formato internacional), o ninguna: para avisar desde otra app |
| `whatsapp_inbox.conversation.summary` | Abiertas, sin leer y esperando respuesta, y si el tope del mes está gastado |
| `whatsapp_inbox.conversation.count_awaiting_reply` | Cuántos clientes esperan respuesta (abiertas con el último mensaje del cliente): lo cuenta la campana |
| `whatsapp_inbox.conversation.notices` | Los clientes que esperan respuesta, del más reciente al más antiguo, con quién, lo último que escribió y cuándo: los avisos del dispositivo |
| `whatsapp_inbox.message.list` | Los mensajes de una conversación, del más reciente al más antiguo |
| `whatsapp_inbox.note.list` | Las notas internas de una conversación |
| `whatsapp_inbox.template.list` | Las plantillas (filtros de estado, categoría, idioma, nombre y si se pueden enviar), con su camino a Meta |
| `whatsapp_inbox.channel.get` | El estado del número y el consumo del mes |
| `whatsapp_inbox.agent.list` | Las personas del negocio a las que se puede asignar una conversación |

### Lo que ofrece: acciones (cambian datos)

| Operación | Qué hace |
|---|---|
| `whatsapp_inbox.message.send` | Guarda y entrega un texto (dentro de 24 h) o una plantilla aprobada, a una conversación o a un número; pide una clave por mensaje |
| `whatsapp_inbox.message.retry` | Vuelve a entregar un mensaje que no salió, con la misma clave |
| `whatsapp_inbox.message.notify` | El envío que puede tener una automatización (FLOW-F31): solo a la conversación viva del número internacional exacto, nunca una nueva; texto dentro de 24 h y la plantilla aprobada fuera; mismo camino de salida que `message.send` |
| `whatsapp_inbox.conversation.mark_read` | Deja **Sin leer** a cero |
| `whatsapp_inbox.conversation.assign` | Asigna o desasigna; «Asignármela» no pisa a otro |
| `whatsapp_inbox.conversation.set_status` | Abierta, pendiente o cerrada |
| `whatsapp_inbox.conversation.link_customer` | Une a una ficha, crea la ficha o desune |
| `whatsapp_inbox.conversation.erase` | Borra los datos de un número (irreversible) |
| `whatsapp_inbox.note.add` / `whatsapp_inbox.note.delete` | Notas internas |
| `whatsapp_inbox.template.create` | Crea una plantilla y la entrega a erplora.com para Meta; pide una clave por guardado |
| `whatsapp_inbox.template.update` | Cambia una plantilla; la aprobada sigue enviándose hasta que Meta recibe el cambio |
| `whatsapp_inbox.template.retry` | Vuelve a entregar la plantilla (o su borrado) que no llegó a Meta; un rechazo va con clave nueva |
| `whatsapp_inbox.template.delete` | Borra una plantilla aquí y en Meta (irreversible) |
| `whatsapp_inbox.channel.prepare` | Pregunta a erplora.com con qué abrir la ventana de Meta y dice si se puede abrir ya (no guarda nada; es acción porque espera a erplora.com fuera de toda transacción) |
| `whatsapp_inbox.channel.connect` | Conecta el número que eligió la ventana de Meta, con su código de un solo uso tal cual llegó |
| `whatsapp_inbox.channel.disconnect` | Desconecta el número del negocio; las conversaciones se quedan |

Del sistema (sin ruta pública; solo erplora.com por `/internal`, las entregas, el worker y las
reacciones): `whatsapp_inbox.message.receive`, `whatsapp_inbox.message.update_status`,
`whatsapp_inbox.channel.sync`; las entregas (`whatsapp_inbox.message.claim_delivery`,
`whatsapp_inbox.message.record_delivery`, `whatsapp_inbox.conversation.claim_erasure`,
`whatsapp_inbox.conversation.record_erasure`, `whatsapp_inbox.template.claim_submit`,
`whatsapp_inbox.template.record_submit`, `whatsapp_inbox.template.claim_delete`,
`whatsapp_inbox.template.record_delete`); la tarea del worker `whatsapp_inbox.delivery.resume`; y
las reacciones a Clientes (`whatsapp_inbox.conversation.claim_for_customer`,
`whatsapp_inbox.conversation.move_customer`, `whatsapp_inbox.conversation.release_customer`,
`whatsapp_inbox.conversation.erase_for_customer`).

### Lo que avisa

`whatsapp_inbox.message.received` (con el mensaje del Hub al que contesta y la opción tocada, F38),
`whatsapp_inbox.message.sent`, `whatsapp_inbox.message.status_changed`, `whatsapp_inbox.conversation.read`,
`whatsapp_inbox.conversation.assigned`, `whatsapp_inbox.conversation.status_changed`,
`whatsapp_inbox.conversation.customer_linked`, `whatsapp_inbox.conversation.erased`,
`whatsapp_inbox.note.added`, `whatsapp_inbox.note.deleted`, `whatsapp_inbox.channel.synced`,
`whatsapp_inbox.channel.connected`, `whatsapp_inbox.channel.disconnected`, `whatsapp_inbox.template.created`, `whatsapp_inbox.template.updated`, `whatsapp_inbox.template.deleted`.
Llevan identificadores, nunca un número, un nombre ni un texto de la conversación.

### A qué reacciona y lo que necesita de otras apps

- **Clientes** (obligatoria): `customer.customer.created` y `customer.customer.updated` unen las
  conversaciones sin ficha de ese número (F04); `customer.customer.merged` las pasa a la ficha que
  queda (F12); `customer.customer.deleted` las deja sin ficha y otra ficha viva del número las reclama;
  `customer.customer.erased` las borra (F11). Lee las fichas por número y el consentimiento de
  marketing por WhatsApp; crea fichas solo con `customer.customer.create`.

### Quién la usa

- **Automatizaciones**: la receta de esta app «Avisar por WhatsApp a la clienta cuando se confirma su cita»
  (F23) lee la ficha, busca la conversación con `conversation.by_phone` y avisa con `message.notify`; las
  automatizaciones del negocio usan el mismo `message.notify` (FLOW-F31). Para saber qué contestó la clienta,
  el aviso `message.received` (F38).
- El **asistente**: todas las operaciones, con referencias humanas («responde a Ana», «asigna la
  conversación de Ana a Luis», «envía la plantilla recordatorio al número que te dicto», «crea una
  plantilla de recordatorio»).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado |
|---|---|---|---|---|
| `whatsapp_inbox.view` (leer, marcar leída) | sí | sí | sí | sí |
| `whatsapp_inbox.reply` (enviar, avisar a un número exacto, reintentar, notas, estado, ficha, asignarse una libre) | sí | sí | sí | sí |
| `whatsapp_inbox.assign` (asignar a otro, quitársela a otro, borrar notas ajenas) | sí | sí | sí | no |
| `whatsapp_inbox.configure` (Ajustes; conectar, volver a conectar y desconectar el número; crear, editar, reenviar y borrar plantillas) | sí | sí | no | no |
| `whatsapp_inbox.erase` (borrar datos de un número) | sí | sí | no | no |

Las operaciones del sistema piden `whatsapp_inbox.receive`, que ningún rol tiene.

## Para quien lo mantiene

### Modelo

- `Channel` (una fila por negocio): estado del número (`not_connected`, `connected`, `reconnect_needed`),
  número y nombre, tope y consumo del mes (`monthly_limit`, `monthly_usage`, `usage_month` `AAAA-MM`; 0 = el
  plan no incluye ninguno, nunca sin límite, y antes de la primera foto, `synced_at` vacío, no se supone
  tope: `Channel.cap_reached`) y la
  `version` de la última foto de erplora.com **de ese negocio** (una igual o más vieja se ignora). **Fase 1
  sin tenencia:** las tablas son compartidas, así que la fila lleva el negocio en `host` (la primera etiqueta
  de su host, como `base.Membership`; única) y cada operación lee y escribe solo la del `Scope` de su
  contexto: la foto de `b` nunca pisa el número de `a` (desde la migración `0005`, reversible). En la fase
  2 vive una sola en la BD de cada hub. Solo la escribe lo que dice erplora.com: su foto y su respuesta al
  conectar o desconectar desde Ajustes.
- `Conversation`: número E.164 (`phone`, único entre las no borradas), nombre de WhatsApp y su forma
  para buscar (`contact_search`: sin mayúsculas, tildes, emojis ni espacios de más), ficha
  (`customer`, FK a `customer.Customer`; una ficha eliminada cuenta como ninguna), asignada
  (`assigned_to`, FK al usuario), estado, sin leer, último mensaje (hora, extracto, tipo, dirección),
  último mensaje del cliente (`last_inbound_at`: la ventana de 24 h), `erased_at`, y el borrado en
  erplora.com (`erase_status`: vacío, `pending`, `done`; `erase_phone`: el número que erplora.com tiene
  que olvidar, solo hasta que lo confirma; `erase_host`: el negocio que lo borró, desde la migración `0007`).
- `Message`: dirección (`inbound`, `outbound`), origen (`customer`, `phone_app`, `hub`), procedencia
  (`live`, `history`), tipo de Meta, texto, adjunto por URL de erplora.com (`media_url`, solo https y de
  su origen; tipo MIME, nombre, pie), estado (`received`; los del Hub: `queued` → `sending` → `sent` →
  `delivered` → `read`, o `failed`) con el código del último intento o de Meta (`error_code`) y, solo en un
  rechazo que el Hub no nombra, el motivo tal como llegó (`error_message`; ver «Un motivo se dice…»),
  `wa_message_id` (único; vacío mientras no ha salido), `client_message_id` (la clave del envío, única,
  obligatoria), el negocio que lo envió desde el Hub (`host`, fase 1, desde la migración `0007`; vacío en lo que
  llega), plantilla usada y sus variables, quién lo envió, hora en que se dijo, objeto de Meta
  (`payload`), `reply_to` (el `wa_message_id` al que contesta o reacciona) y `reply_id` (la opción
  tocada: el identificador que el negocio puso en el botón, F38). Una reacción es un mensaje de tipo
  `reaction` cuyo `reply_to` es el mensaje al que responde: no suma en «Sin leer» ni pasa a último
  mensaje.
- `Note`: texto, autor y hora.
- `Template` (de cada negocio): el negocio en `host` (fase 1, como `Channel`; desde la migración `0006`,
  reversible: las copias de antes quedan sin negocio, solo en el admin, y la foto de cada negocio trae de Meta
  las suyas), nombre + idioma (únicos por negocio entre las no borradas), categoría, estado en Meta (`DRAFT` mientras
  Meta nunca la tuvo, `APPROVED`, `PENDING`, `REJECTED`, `PAUSED`, `DISABLED`, `DELETED`), cabecera
  (`header_format`: vacío, `TEXT` o un archivo o lugar hecho en WhatsApp Manager; `header`), cuerpo,
  ejemplos (`body_examples`), pie, botones, número de variables, motivo de rechazo, `meta_id`,
  `synced_at`; el cambio que espera llegar a Meta (`draft`); la entrega a erplora.com (`submit_state`:
  vacío, `queued`, `sending`, `failed`; `submit_key`, la clave del guardado, única; `submit_error_code` y,
  solo en un rechazo de Meta que el Hub no nombra, su motivo tal como llegó en `submit_error`; `submit_at`); el borrado (`deleted_at`, que conserva la fila, y `delete_state`:
  `pending` hasta que Meta lo confirma, `done`); y `supported` (si el Hub la escribe y la sabe rellenar:
  ni código de verificación, ni cabecera con archivo o con variable, ni variables con nombre, solo
  respuestas rápidas, enlaces fijos y llamadas).

Mensajes recibidos y enviados: el admin los enseña en **solo lectura** (son lo que llevó WhatsApp; se
corrigen borrando los datos de la conversación, nunca editando), con borrado para el staff.

### Reglas que no se rompen

- **Nada espera a erplora.com dentro de una transacción.** `message.send` valida y guarda el mensaje
  `queued` con su clave en una transacción corta (con su evento) y lo entrega **después del COMMIT**
  (`transaction.on_commit`): `message.claim_delivery` lo toma con `SKIP LOCKED` y lo pone `sending`
  (transacción corta), la llamada HTTP a erplora.com va sin transacción ni bloqueo, y
  `message.record_delivery` guarda la respuesta en otra transacción corta. Lo mismo al borrar
  (`conversation.claim_erasure` → HTTP → `conversation.record_erasure`) y con las plantillas
  (`template.claim_submit` → HTTP → `template.record_submit`; `template.claim_delete` → HTTP →
  `template.record_delete`). Un erplora.com lento nunca bloquea la conversación (`receive`, `mark_read`,
  `assign`) ni, con el plan Gratis, el hub. `channel.prepare`, `channel.connect` y `channel.disconnect`
  son acciones aunque `prepare` no guarde nada (una consulta abre su transacción `READ ONLY` antes de su
  primera línea): las tres preguntan a erplora.com **antes** de leer o escribir nada, y solo después
  `connect` y `disconnect` guardan su respuesta en la fila del negocio, en una transacción corta con su
  evento. La foto que erplora.com empuja entretanto dice lo mismo con una versión mayor, y la siguiente
  sigue ganando.
- **Fase 1** entrega al terminar la petición (el `on_commit` corre en ella); **fase 2**: el trabajo
  diferido entra con `use_hub(hub)` explícito (corre fuera de la petición que eligió el hub). La tarea
  del worker `whatsapp_inbox.delivery.resume` (`*/5 * * * *`, `catch_up: collapse`, declarada en
  `apps.py`) retoma con `SKIP LOCKED`, de 50 en 50, los mensajes `queued`/`sending`, las plantillas
  `queued`/`sending` y los borrados `pending` (de números y de plantillas) con más de 2 minutos. En la
  fase 1 el worker la corre con un solo ámbito fijo (`WORKER_SCOPE_SLUG`, `base/scheduler.py`): retoma lo de
  todos los negocios, y cada mensaje, plantilla o borrado se entrega a erplora.com como el de su negocio
  (`Message.host`, `Template.host`, `Conversation.erase_host`), con su contenido; un mensaje o un borrado de
  número anterior a la migración `0007`, sin negocio guardado, sale con el ámbito del worker, como hasta
  entonces. En la fase 2 corre en la BD de cada hub. «Reintentar» (`message.retry`) y volver a borrar un
  número ya borrado (`conversation.erase` por su id) entregan igual, con el negocio de la fila y no con el de
  quien lo pide desde la bandeja compartida; sin negocio guardado (anterior a `0007`), con el de quien lo pide.
- **Un mensaje nunca es «enviado» sin el id de Meta.** Respuestas de erplora.com: 200 con
  `wa_message_id` → `sent`; 409 → `failed` con su motivo (`whatsapp.cap_reached` se guarda como
  `whatsapp_inbox.cap_reached`; `whatsapp.reconnect_needed`, el 190 de Meta, como
  `whatsapp_inbox.reconnect_needed` con el texto del Hub (`RECONNECT_NEEDED`), nunca el de Meta, y la burbuja
  lo dice como **Tu número** mientras el canal siga `reconnect_needed`; cualquier otro como
  `whatsapp_inbox.send_refused`, con el motivo de Meta); conexión fallida o un
  4xx que no es 409 (también un 429: ir más despacio no es el tope) → no ha salido (`sending`,
  `whatsapp_inbox.saas_unreachable`); 5xx, tiempo de lectura agotado o 200 sin id → no se sabe
  (`sending`, `whatsapp_inbox.send_unknown`). Los dos últimos se reintentan **con la misma clave** («No
  enviado · Reintentar», `message.retry`): erplora.com nunca envía dos veces la misma clave. Un error de
  `httpx` que no es `HTTPError` (una URL que no entiende, una cabecera que no puede codificar) cuenta como
  «no ha salido», nunca como excepción.
- **Una plantilla nunca se registra dos veces.** Cada guardado lleva su `submit_key` (la pantalla genera
  una por guardado; el asistente, una por intención); el mismo guardado repetido es la misma fila y la
  misma entrega. 200 `{meta_id, status}` → la plantilla (o su `draft`) pasa a lo que Meta dice; 409 →
  `failed` con el motivo de Meta (`whatsapp.meta_unreachable`, `whatsapp.meta_rate_limited`,
  `whatsapp.not_connected` y `whatsapp.reconnect_needed` se dicen con palabras del Hub, sin culpar a ERPlora);
  sin respuesta →
  `sending`, y `template.retry` la entrega con la misma clave; un `failed` reintentado va con clave nueva
  (la misma daría el mismo rechazo).
- **Un motivo se dice en el idioma de quien lo lee, nunca en el de quien lo escribió.** La fila de un mensaje o
  de una plantilla guarda el código del Hub (`error_code`, `submit_error_code`) y, solo en un rechazo que el Hub
  no nombra (`whatsapp_inbox.send_refused`, `whatsapp_inbox.template_refused`), las palabras de Meta o de
  erplora.com tal como llegaron (`error_message`, `submit_error`). Las palabras del Hub para sus códigos
  (`cap_reached`, `reconnect_needed`, `saas_unreachable`, `send_unknown`, `conversation_erased`,
  `meta_unreachable`, `meta_rate_limited`, `channel_not_connected`; con `saas_unreachable` y `send_unknown`,
  las del borrado mientras la plantilla se está borrando) se ponen al leer (`message.list`, `template.list` y
  las respuestas de sus escrituras), en el idioma de quien mira. Así el reintento del worker, que escribe en
  inglés, no cambia el idioma de lo que ve la persona, y una fila de antes, con el texto ya guardado, se lee
  igual por su código.
- **La lista de Meta nunca pisa al Hub**: una plantilla `DRAFT` que va de camino conserva lo escrito, un
  cambio pendiente espera en `draft` (el veredicto de Meta nunca cae sobre un texto cambiado después) y
  una borrada aquí no vuelve (ni por nombre mientras su borrado está `pending`, ni por su `meta_id`).
- Solo se envían plantillas `supported` y `APPROVED` (409 `whatsapp_inbox.template_not_sendable` /
  `whatsapp_inbox.template_not_approved`); solo se editan las `supported` no desactivadas ni borradas en
  Meta (409 `whatsapp_inbox.template_read_only`), ni en revisión (`whatsapp_inbox.template_in_review`)
  ni de camino (`whatsapp_inbox.template_submitting`); la categoría, solo de una `DRAFT` o `REJECTED`
  (`whatsapp_inbox.template_category_fixed`). El formulario aplica las reglas de Meta en el servidor
  (422 bajo su campo): nombre `[a-z0-9_]`, variables `{{1}}…{{n}}` sin huecos ni con nombre, un ejemplo
  por variable, sin variables en cabecera ni pie, 60 caracteres en cabecera y pie, 1024 en el cuerpo,
  hasta 10 botones con las respuestas rápidas juntas, 2 enlaces https sin variables y 1 llamada E.164.
- **La clave es obligatoria y una por mensaje** (`client_message_id`): la pantalla la guarda hasta que el
  Hub acepta el mensaje (aunque se retoque el texto) y el asistente genera una por intención. La misma
  clave dos veces, también a la vez, es un solo mensaje y una sola entrega (restricción única; el
  segundo recibe la fila del primero).
- La ventana de 24 h se cuenta desde el último mensaje **del cliente** (`last_inbound_at`), en el
  servidor; fuera de ella, `message.send` con texto da 409 `whatsapp_inbox.window_closed`. Sin
  `SAAS_INTERNAL_URL`, sin número conectado o con el mes gastado no se guarda nada (409
  `whatsapp_inbox.saas_unconfigured`, `whatsapp_inbox.channel_not_connected`,
  `whatsapp_inbox.cap_reached`). Recibir no mira el tope.
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
- Números: el que llega de erplora.com tiene que ser internacional (`+?[1-9]` y 7–15 cifras) o es un
  422, y sus cifras sueltas son internacionales; el que escribe una persona (`to` de `message.send`) es
  del país del negocio salvo que lleve su prefijo (`600222333` es de España, nunca +60; gh:whatsapp_inbox#279).
  El número del negocio, E.164 o vacío.
- `message.received` dice a qué mensaje **del Hub** contesta (`reply_to_message_id`: solo uno con
  `origin=hub` de esa conversación) y la opción (`reply_id`), los dos siempre presentes. Ningún evento
  lleva el número, el nombre ni el texto: el outbox se guarda días después de un borrado.
- Zona horaria de la fase 1: `Europe/Madrid` (el mes del tope y las horas de la bandeja).

### Retención (RGPD)

Las conversaciones se guardan mientras el negocio usa la app. Se borran: a mano (F10), al borrar la
ficha en Clientes (F11) y con la base de datos del negocio cuando se da de baja. Borrar vacía en el Hub,
al momento, el número, el nombre, los textos, los adjuntos, las variables de plantilla, la opción tocada,
el objeto de Meta y las notas; y pide a erplora.com que olvide el número y los mensajes (los adjuntos
viven allí). Quedan el identificador de cada mensaje (para no volver a crearlo si erplora.com lo
entregara otra vez), las fechas y, solo hasta que erplora.com confirma, el número a olvidar
(`erase_phone`). Los avisos del outbox solo llevan identificadores. No hay purga automática por
antigüedad en la fase 1: si se decide un plazo, será un ajuste con su tarea.

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

**Cuatro puertas que monta `base`** (erplora.com → Hub; cada una ejecuta una operación de sistema). Están
montadas desde hub#127 (`base/internal.py`), probadas en `base/tests/test_internal_whatsapp.py` y, por HTTP
firmado con la bandeja abierta, en `tests/e2e/whatsapp-internal.spec.ts`; erplora.com las llama desde saas#63,
probado de punta a punta con su número de pruebas en `tests/e2e/whatsapp-inbox-erplora.spec.ts`:

1. `POST /internal/whatsapp/inbound` → `whatsapp_inbox.message.receive`. Un mensaje del cliente o el eco
   de lo que el dueño escribió en el móvil, en vivo o del historial:

   ```json
   {"hub": "a", "wa_message_id": "wamid.HBgL…", "from": "34600111222", "contact_name": "Ana",
    "direction": "inbound", "source": "live", "type": "image", "text": "",
    "media": {"url": "https://erplora.com/whatsapp/media/7f3c…", "mime_type": "image/jpeg",
              "filename": "", "caption": "Mi pelo"},
    "reply_to": "", "reply": null, "sent_at": "2026-10-15T10:00:00Z", "payload": {"…": "objeto de Meta"}}
   ```

   `from`: el número internacional del cliente, con o sin `+`. `direction`: `inbound` (cliente) u
   `outbound` (eco del móvil; `from` sigue siendo el cliente). `source`: `live` o `history`.
   `media.url`: del origen de erplora.com y por https; el navegador la abre con la sesión del negocio.
   Una reacción llega con `type: "reaction"`, el emoji en `text` y el mensaje que responde en
   `reply_to`. Una opción tocada (F38) llega con `type: "button"` o `"interactive"`, `reply_to` = el
   `wa_message_id` del mensaje que la ofrecía y `reply: {"id": "<payload o id de la opción>", "title":
   "<su texto>"}`; sin `reply`, el Hub la lee de `payload` (`button.payload`/`button.text`,
   `interactive.button_reply` o `interactive.list_reply`, y `context.id`). Respuesta 200
   `{"id", "conversation_id", "created"}`; repetir el mismo `wa_message_id` es 200 con `created: false`
   (o completa un `media_placeholder` del historial). 422 con el sobre de errores si el cuerpo no vale
   (no reintentar); 404 `app_inactive` si la app no está activa en ese negocio, 5xx o sin respuesta:
   erplora.com guarda el mensaje y reintenta con espera creciente.
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
   consumo o una plantilla (también cuando Meta cambia un veredicto: erplora.com escucha su aviso):

   ```json
   {"hub": "a", "version": 42, "status": "connected", "phone_number": "+34910000000",
    "display_name": "Peluquería Ana", "monthly_limit": 150, "monthly_usage": 12, "usage_month": "2026-10",
    "templates": [{"name": "recordatorio", "language": "es", "category": "UTILITY", "status": "APPROVED",
                   "header_format": "TEXT", "header": "Tu cita", "body": "Hola {{1}}, te esperamos el {{2}}.",
                   "body_examples": ["Ana", "viernes"], "footer": "",
                   "buttons": [{"type": "QUICK_REPLY", "text": "Sí"}],
                   "variables": 2, "rejected_reason": "", "meta_id": "1234567890"}]}
   ```

   → 200 `{"applied": true|false, "version": 42}`. `templates: null` deja las plantillas como están;
   una lista las sustituye (las que faltan quedan `DELETED`), sin pisar lo que el Hub tiene de camino ni
   traer de vuelta lo borrado aquí. `header_format`: vacío, `TEXT`, `IMAGE`, `VIDEO`, `DOCUMENT` o
   `LOCATION`. Una `version` igual o menor que la guardada no se aplica. El historial que trae la
   conexión no gasta cupo: `monthly_usage` cuenta solo lo que envía el negocio.
4. La clave `whatsapp` de la **foto de estado** (`PUT /internal/hubs/{id}/state`): el mismo cuerpo que la
   puerta 3 (sin `hub`), con la `version` de la foto; `base` se la pasa a `whatsapp_inbox.channel.sync`.

**Las puertas que sirve el SaaS** (el Hub → erplora.com; `apps/whatsapp_inbox/gateway.py`, `httpx`, 5 s
para conectar y 15 s para leer; siempre después del COMMIT, nunca dentro de una transacción). Existen en
erplora.com desde saas#63 (2026-10-21), con su webhook de Meta (`saas/whatsapp/internal.py`; su WORKBOOK,
«Contrato con el Hub», añade las 10–12):

5. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/send`, con `Idempotency-Key: <client_message_id>`:

   ```json
   {"hub": "a", "to": "+34600111222", "type": "text", "text": "Sí, mañana a las 10"}
   {"hub": "a", "to": "+34600111222", "type": "template",
    "template": {"name": "recordatorio", "language": "es", "variables": ["Ana", "viernes"]}}
   ```

   Respuestas: 200 `{"wa_message_id": "wamid…"}` (aceptado por Meta); 409
   `{"error": {"code": "whatsapp.cap_reached" | "whatsapp.not_connected" | "whatsapp.reconnect_needed" |
   "whatsapp.window_closed" | "whatsapp.template_not_approved" | "whatsapp.recipient_blocked" |
   "whatsapp.meta_rejected", "message": "…"}}` = no ha salido (`reconnect_needed`: el permiso caducó o se
   retiró, el 190 de Meta, y erplora.com marca el número «Hay que reconectar» con foto nueva; `meta_rejected`:
   otro rechazo de Meta, con su motivo);
   un 4xx que no es 409 (también 429) = no ha salido; 5xx o sin respuesta = no se sabe. erplora.com
   **nunca envía dos veces la misma clave** (devuelve el `wa_message_id` que ya tenía) y **reserva el
   cupo del mes de forma atómica al aceptar**: dos envíos simultáneos no pueden pasar ambos el tope.
6. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/erase`:

   ```json
   {"hub": "a", "phone": "+34600111222", "wa_message_ids": ["wamid.HBgL…", "wamid.HBgM…"]}
   ```

   erplora.com borra lo que guarda de ese número para ese negocio (mensajes aparcados, adjuntos, el
   cliente en sus colas) y contesta 200 `{"erased": true}`. Cualquier otra respuesta deja el borrado
   `pending` y el Hub lo vuelve a pedir.
7. El **envío de estados** de la puerta 2 es obligación del SaaS: cada estado de Meta de un mensaje del
   Hub, con su `wa_message_id` y su `client_message_id`, hasta 200.
8. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/templates`, con `Idempotency-Key: <submit_key>` (F29,
   F30): registra en Meta una plantilla nueva o, con `meta_id`, el cambio de una que Meta ya tiene:

   ```json
   {"hub": "a", "name": "recordatorio", "language": "es", "category": "UTILITY", "header": "Tu cita",
    "body": "Hola {{1}}, te esperamos el {{2}}.", "body_examples": ["Ana", "viernes"],
    "footer": "Peluquería Ana", "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}], "meta_id": ""}
   ```

   Respuestas: 200 `{"meta_id": "…", "status": "PENDING" | "APPROVED" | "REJECTED" | …}` (Meta la
   recibió); 409 `{"error": {"code": "whatsapp.template_invalid" | "whatsapp.meta_unreachable" |
   "whatsapp.meta_rate_limited" | "whatsapp.not_connected" | "whatsapp.reconnect_needed", "message": "<motivo
   de Meta>"}}` = no aceptada (`reconnect_needed`: el permiso caducó o se retiró, el 190 de Meta, y erplora.com
   marca el número «Hay que reconectar» con foto nueva, como en la puerta 5; el Hub deja la plantilla `failed`
   con `whatsapp_inbox.reconnect_needed` y su propio texto (`RECONNECT_NEEDED`), nunca el de Meta: la fila dice
   «No aceptada: El permiso de WhatsApp para tu número caducó: vuelve a conectarlo.»); el resto como en la
   puerta 5. erplora.com **nunca registra dos veces la misma clave**.
9. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/templates/delete` (F31):

   ```json
   {"hub": "a", "name": "recordatorio", "language": "es", "meta_id": "1234567890"}
   ```

   Borra en Meta esa plantilla en ese idioma (no las demás del mismo nombre). 200 `{"deleted": true}` o
   404 `{"error": {"code": "whatsapp.template_not_found", …}}` (Meta ya no la tiene) = borrada; cualquier
   otro 404 (una puerta que no existe, una dirección mal puesta: gh:whatsapp_inbox#296), 409 con su
   motivo (`whatsapp.meta_unreachable`, `whatsapp.meta_rate_limited`, `whatsapp.not_connected`,
   `whatsapp.reconnect_needed` o `whatsapp.meta_rejected`), otro 4xx, 5xx o sin respuesta = sigue `pending` y
   el Hub lo vuelve a pedir. Los cuatro primeros se dicen con palabras del Hub, como en la puerta 8:
   con `reconnect_needed` (el mismo 190, y erplora.com marca el número) la fila dice «Borrándose en Meta» con
   el texto `RECONNECT_NEEDED`, y el borrado solo sale bien cuando el número se vuelve a conectar.

Las tres de **conectar el número desde Ajustes** (F01, F02; `whatsapp_inbox.channel.prepare`, `.connect` y
`.disconnect`, en la petición de la persona y sin transacción abierta). En las tres, el sobre de errores de
erplora.com con cualquier estado es un rechazo: no se hizo nada y se dice su motivo (`hub_unknown` → 409
`whatsapp_inbox.hub_unknown`, «una demo no puede conectar»; `whatsapp.meta_rejected` → 409
`whatsapp_inbox.meta_rejected` con las palabras de Meta; `whatsapp.number_not_in_account` y
`whatsapp.number_not_chosen` → 409 con el suyo; `whatsapp.meta_rate_limited` → 409; `whatsapp.meta_unreachable`
y `whatsapp.meta_no_token` → 503 `whatsapp_inbox.meta_unreachable`; `whatsapp.not_configured` → 409
`whatsapp_inbox.whatsapp_unavailable`; otro código → 503 `whatsapp_inbox.saas_refused`, con log de error). Un
4xx sin sobre o sin conexión → 503 `whatsapp_inbox.saas_unreachable` (no salió nada); un 5xx sin sobre, sin
respuesta o un 200 que no es el de la puerta → 503 `whatsapp_inbox.connect_unknown` /
`whatsapp_inbox.disconnect_unknown` (no se sabe: la foto lo dirá). Sin `SAAS_INTERNAL_URL`, 409
`whatsapp_inbox.saas_unconfigured`.

10. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/config` `{"hub": "a"}` → 200 `{"configured": true, "app_id":
    "1234567890", "config_id": "9876543210", "graph_version": "v25.0", "redirect_uri":
    "https://erplora.com/whatsapp/return"}` (solo identificadores públicos). `configured: false` → «WhatsApp
    todavía no está disponible en ERPlora.» y no se ofrece conectar. Ids que no son cifras o una versión que
    no es `vNN.N` → 503 `whatsapp_inbox.saas_unreachable`. `redirect_uri` es la página de erplora.com a la que
    Meta devuelve el código (`GET /whatsapp/return`, saas#71), y la misma con la que la puerta 11 lo canjea. El
    Hub solo la acepta del origen exacto de `SAAS_URL` (esquema, host y puerto) y sin fragmento: https, y http
    solo en desarrollo (`DEBUG`) con un `SAAS_URL` http, la misma regla que erplora.com
    (`whatsapp.meta.redirect_uri`). Sin ella, o si las páginas del Hub cortan las ventanas que abren
    (`SECURE_CROSS_ORIGIN_OPENER_POLICY` que no es `same-origin-allow-popups` ni `unsafe-none`; `base` pone
    `same-origin-allow-popups` desde hub#154), `prepare` dice `available: false` con `window_unavailable` o
    `popups_blocked` y la pantalla, «Todavía no se puede conectar el número desde aquí.».
11. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/connect` con lo que dio la ventana, tal cual:

    ```json
    {"hub": "a", "code": "AQB…", "event": "FINISH", "waba_id": "102290129340398",
     "phone_number_id": "106540352242922", "business_id": "2729063490586005"}
    ```

    → 200 `{"connected": true, "phone_number": "+34910000000", "display_name": "Peluquería Ana",
    "history_requested": false}`: el Hub lo guarda en la fila del negocio al momento (con un número E.164 y un
    nombre de hasta 200; si no, `connect_unknown`) y avisa `whatsapp_inbox.channel.connected`
    (`{"history_requested"}`). `event`: `FINISH` o `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` (número de la app
    del móvil: erplora.com pide su historial); una ventana cancelada no llega a la puerta. El código dura 30 s.
12. `POST {SAAS_INTERNAL_URL}/internal/whatsapp/disconnect` `{"hub": "a"}` → 200 `{"disconnected": true |
    false}` (`false`: no había número). En los dos casos la fila del negocio queda `not_connected` sin número
    (con `whatsapp_inbox.channel.disconnected` si cambió); el consumo del mes y las conversaciones se quedan.

**La ventana de Meta sin el SDK de Facebook** (la CSP del Hub no carga nada de otro origen; decidido con el
mercado: Meta «manual flow» y Embedded Signup, HubSpot, Chatwoot, respond.io, Chakra, Typewise y Bird). En el
clic, `window.open` de `https://www.facebook.com/<graph_version>/dialog/oauth?client_id=<app_id>&config_id=<config_id>&response_type=code&override_default_response_type=true&redirect_uri=<redirect_uri>&state=<slug>.<32 hex>&display=popup&extras={"setup":{}}`.
Mientras corre, Meta manda a esta página por `postMessage`, desde `https://*.facebook.com`, la sesión
(`WA_EMBEDDED_SIGNUP`: `FINISH*` con `waba_id`, `phone_number_id`, `business_id`; `CANCEL` o `ERROR` con su
motivo); al terminar lleva el navegador a `redirect_uri` con `?code=…&state=…` (o `error`). **Propuesta a
erplora.com** (FIX de su carril): `GET /whatsapp/return`, pública, con COOP `unsafe-none`, que hace
`window.opener.postMessage({"type": "erplora.whatsapp.signup", "state", "code" | "error", "error_description"},
"https://<slug>.erplora.com")` con el `slug` del `state` y se cierra; y el canje del código en la puerta 11 con
ese mismo `redirect_uri` (Meta lo exige: error 100/36008). El Hub solo acepta la sesión de facebook.com y la
vuelta del origen de `redirect_uri` con el `state` de ese intento; sin sesión en 3 s tras el código, «Meta no
ha dicho qué cuenta de WhatsApp Business se eligió». Riesgo no medido: que Meta mande la sesión a una ventana
abierta sin su SDK; si no la manda, la puerta 11 tendría que sacar la cuenta del permiso
(`debug_token`, `granular_scopes`).

### Contrato con `base`

- Monta las puertas 1–3 en `/internal/whatsapp/` (no publicadas en el ALB; hecho desde hub#127,
  `base/internal.py`): comprueba la firma y la marca de tiempo, resuelve el negocio por `hub` (fase 1:
  `Scope("host", hub)`; fase 2: `use_hub`), comprueba que la app está activa (si no, 404 `app_inactive`) y
  ejecuta la operación con `system_context(scope)`, devolviendo su salida o el sobre de errores con su
  estado HTTP (422 para un cuerpo que no vale).
- Al recibir la foto de estado con la clave `whatsapp` (puerta 4), se la pasa a
  `whatsapp_inbox.channel.sync` con la versión de la foto (hecho desde hub#127).
- El relay del outbox entrega `customer.customer.created/updated/merged/deleted/erased` a
  `apps.whatsapp_inbox.events.react` (ya en la fase 1, `base/relay.py`); en la fase 2, el worker ejecuta
  la tarea `resume_deliveries` de `apps.py` en cada hub (`hub_due`), y el trabajo diferido de esta app
  entra con `use_hub(hub)`.
- La campana de la barra superior lee `whatsapp_inbox.conversation.count_awaiting_reply` (la declaración `bell`
  de `apps.py`, con el permiso `whatsapp_inbox.view`), que comparte con `summary` la única definición de
  «esperando respuesta» (`AWAITING_REPLY` de `queries.py`); se refresca con `AWAITING_REPLY_EVENTS` de `events.py`.
- Los avisos del dispositivo (`notices` de `apps.py`, hub#2303) leen `whatsapp_inbox.conversation.notices`: una
  fila por conversación esperando respuesta con `at` = el último mensaje del cliente (`last_inbound_at`), así que
  el dispositivo, que cuenta cada par (`id`, `at`) una vez, avisa de nuevo cuando el cliente vuelve a escribir.
  Con ellos, quien puede leer la bandeja figura en `sources` de `base.notice.list` y la app instalada le pide
  permiso para avisar aunque el negocio solo use WhatsApp (hub#2306).
- Las fotos y las notas de voz del hilo (F06) se cargan de erplora.com: la CSP del Hub permite su origen en
  `img-src` y `media-src` (`config/settings.py`, hub#147), y erplora.com las sirve a quien tiene su sesión
  (`<slug>.erplora.com` y `erplora.com` son un mismo sitio, así que la cookie viaja).
- Para que la ventana de Meta devuelva su código (F01, F02), las páginas del Hub no pueden cortar las
  ventanas que abren: `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"` en `config/settings.py`
  (hecho en hub#154). La CSP no cambia: la ventana es otra pestaña, sin
  `frame-src`, `connect-src` ni `form-action` nuevos, y el `postMessage` no pasa por la CSP.

### Respuestas automáticas: lo que falta

F14–F26 son recetas de fábrica de esta app sobre el registro de Automatizaciones (`apps/flow/recipes.py`,
FLOW-F33 a F36), y las tarjetas de **Ajustes → ¿Para qué lo usas?** las encienden, pausan y restauran por
sus operaciones (`flow.recipe.list`, `flow.recipe.enable`, `flow.recipe.disable`, `flow.recipe.restore`):
esta app no lleva recetas propias en su base de datos. `recipes.py` declara ya «Cita confirmada → WhatsApp»
(F23, `appointment_confirmed`: lee la ficha, busca la conversación con `conversation.by_phone`, se para sin
error si no hay teléfono o conversación, lee la cita y avisa con `message.notify`, el envío acotado de
FLOW-F31, que una automatización sí puede tener) y su par de mesa «Reserva confirmada → WhatsApp» (F26,
`reservation_confirmed`: escucha `reservation.reservation.status_changed` solo con `input.status` = `confirmed`
en el «Solo cuando…» del disparador, lee la reserva con `reservation.reservation.get`, que da `guest_phone`,
`date_label`, `time_label` y `party_size`, busca la conversación de `guest_phone`, se para igual sin teléfono o
sin conversación y avisa con `message.notify` y la plantilla `reservation_confirmed` de tres datos). Se usa el
teléfono de la reserva y no el de la ficha: es el número con el que se reservó (RESERVATION-F17 guarda ahí el de
la conversación, ya en internacional) y no pide Clientes. La reserva que nace confirmada también avisa:
`reservation.reservation.create` (y la conversión desde la lista de espera) graban `status_changed` con
`previous_status` vacío. Las demás esperan a una pieza que no está en `main` (2026-10-24):

1. **El asistente en el Hub**: ni la app `assistant` ni un paso de Automatizaciones que lo ejecute con
   herramientas (las operaciones con `ai=`). Las automatizaciones solo tienen pasos `command`, `query`,
   `condition`, `delay`, `http` y `ask`. Sin él nadie lee el texto libre de la clienta (F14–F22, F24, F25):
   la receta vieja era un paso `ai` con `policy: auto`, el acuse fijo y la disculpa de F20.

Cómo encaja cuando lleguen: `apps/whatsapp_inbox/recipes.py` añade «WhatsApp → cita reservada» junto a su
acompañante «Cita confirmada → WhatsApp», que ya está, y «WhatsApp → mesa reservada» junto a «Reserva confirmada →
WhatsApp», que también está; la exclusión entre tarjetas (una sola respuesta automática en el número) y el orden al apagar
(acompañantes primero) son de la pantalla; el interruptor de F16 escribe `auto_confirm_online` con
`appointment.settings.update` o `auto_confirm` con `reservation.settings.update`; F19 necesita guardar la
última lista ofrecida por conversación (24 h) y casar con ella lo escrito; F20 necesita marcar la
conversación «Necesita atención» (hoy la bandeja solo tiene **Sin leer**).

### Contradicciones escritas, sin resolver

- `PLAN-SAAS.md` (fila de `assistant`, `speech`, `whatsapp_inbox`, `notify` ≈l.45; ≈l.758; ≈l.875) y
  `PLAN-HUB.md` (≈l.71 y ≈l.461) dicen que WhatsApp **sale del SaaS** y que el Hub llama a Meta
  directamente. Esta app sigue el encargo del 2026-10-15: la cuenta de WhatsApp Business, el webhook de
  Meta y el registro de plantillas siguen en el SaaS, y el Hub habla con él por `/internal`. Falta la
  ronda nueva que lo decida en los planes.
- `PLAN-SAAS.md` (bloque 12: «Ninguna [pantalla] en el panel: la bandeja y sus ajustes son del Hub») no
  dice dónde se crean las plantillas, y el WORKBOOK anterior las mandaba a erplora.com. Decidido en la
  migración (mercado: Odoo, WATI, Respond.io, Twilio, Gupshup, AiSensy, Interakt y Zoko las crean en su
  propio panel; el producto actual las creaba en el Hub): **se crean, editan y borran en el Hub**
  (Ajustes) y erplora.com solo las registra en Meta (puertas 8 y 9). Falta escribirlo como ronda.
- F24: el producto actual no creaba ficha a quien pedía mesa por WhatsApp («su ficha si ya existe (no se
  crea)»), pero Reservas, ya en el Hub, le crea una de origen WhatsApp si su teléfono no tiene
  (RESERVATION-F17, probado en sus tests). F24 sigue a Reservas, que es quien escribe la reserva; en las
  citas también se crea (F21, CUSTOMER-F26).
- Fase 1 sin tenencia: las conversaciones de `a` y `b` comparten tablas (solo los avisos vivos van por
  hub), como en todas las apps de la fase 1. El número y las plantillas ya no: `Channel` y `Template` son
  de cada negocio (ver «Modelo»), porque la foto de `b` pisaba el número de `a` y su lista de Meta dejaba
  «Borradas en WhatsApp Manager» las plantillas de `a`; y el mensaje que sale del Hub y el número que se
  pide olvidar guardan su negocio, porque el worker los retomaba con el suyo y «Reintentar» o volver a
  borrar desde otro negocio los entregaban con el de quien lo pedía.

### Cambios frente al producto actual

| Producto actual | Aquí | Motivo |
|---|---|---|
| El Hub **sondea** a erplora.com (`/api/v1/hub/device/whatsapp/inbox`, `statuses`) | erplora.com **empuja** al Hub por `/internal` | Contrato SaaS ↔ Hub (el SaaS empuja tras el commit; PLAN-SAAS §2) |
| La bandeja no contesta («Desde esta pantalla no se contesta») | Se contesta desde el Hub (F32, F33) | Mercado (ver «Referencia adoptada») |
| Estados `active`/`closed`, solo el borrado cierra | Abierta / pendiente / cerrada, a mano; un mensaje nuevo reabre | Mercado (Zendesk, Fresha, Shopify) |
| Asignar tecleando el identificador, solo el administrador | Selector del equipo + «Asignármela»; el responsable asigna | Mercado (Shopify, Chakra); el producto actual lo marcaba «parcial» |
| Sin notas | Notas internas (F36) | Mercado (Fresha, Intercom, Front) |
| «Necesita atención» lo ponían las recetas | Filtro **Sin leer** + la campana **Clientes de WhatsApp esperando respuesta** (`awaiting_reply`) | Sin recetas no hay quien la ponga |
| La app instalada avisaba cuando subía el contador de la campana (hub#2303) | Un aviso del dispositivo por cada mensaje de un cliente que queda sin contestar | Mercado (WhatsApp Business, Shopify Inbox, Square, Fresha avisan de cada mensaje); un aviso por subida del contador callaría al cliente que vuelve a escribir tras cerrarse sin respuesta |
| Fotos y audio dentro del hilo, descargados por una puerta del Hub | Fotos y notas de voz dentro del hilo, servidas por erplora.com; vídeos y documentos con **Abrir el adjunto** | El Hub no guarda ni pasa archivos: erplora.com los sirve con la sesión de la persona y la CSP del Hub permite su origen (ver «Contrato con `base`») |
| Plantillas: crear, editar y borrar desde el Hub, subiendo la muestra de la cabecera | Igual (F29–F31), con la entrega a Meta por erplora.com; sin cabecera con archivo | El Hub no guarda archivos; la cabecera con foto, vídeo o documento se hace en WhatsApp Manager |
| Repaso cada 15 min de conversaciones sin ficha | Se une al recibir y al guardar la ficha | No hay conversaciones anteriores a la app nueva que repasar |
| `templates.list` y ajustes solo para el administrador | Elegir plantilla para enviar: quien contesta; Ajustes: propietario y administrador | Quien contesta necesita las plantillas |

## Lo que NO hace, a propósito

- **No guarda credenciales de Meta**: la cuenta de WhatsApp Business, el webhook y el token viven en
  erplora.com, que es quien habla con Meta.
- **No sube la muestra de una cabecera con foto, vídeo o documento**: esas plantillas se hacen en
  WhatsApp Manager y aquí se ven, pero no se envían.
- **No contesta sola ni reserva todavía** (F14–F22, F24, F25): las respuestas automáticas que reservan cita o
  mesa necesitan el asistente, que aún no está en el Hub («Respuestas automáticas: lo que falta»). Los avisos de
  la cita y de la mesa confirmadas (F23, F26) sí salen.
- **No hace campañas** ni envíos masivos.
- No sincroniza grupos ni listas de difusión (límite de la coexistencia de Meta).
