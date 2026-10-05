# WORKFLOW — Hub (servidor) · WhatsApp

Prefijo: HUB

> Área «WhatsApp y asistente», primera mitad. El hub **no habla con Meta**: todo pasa por la
> pasarela de WhatsApp del SaaS, firmado con la credencial de máquina del hub, que nunca sale al
> navegador (ADR-0012, ADR-0452, ADR-0470). Lo que la persona ve está en `whatsapp_inbox`
> (`WORKFLOW.md` del módulo) y en el shell (`HUB_SHELL`); aquí, qué hace el servidor cuando le
> llega cada orden y qué garantiza. Escrito contra `origin/develop` del hub (05/10/2026).
> Código: `crates/server/src/{whatsapp_connect,inbound_poll,whatsapp_media,whatsapp_templates,
> whatsapp_header_samples,whatsapp_quota}.rs`, la salida por `notify_transport.rs` y las puertas
> de `crates/cloud-client`.

## Flujos

### HUB-F260 Conectar el número de WhatsApp del negocio
Estado: parcial — la puerta del hub está entera, pero hoy Meta solo deja terminar la conexión con números del portfolio de ERPlora (verificación del negocio pendiente, pm#277), y el canje del código ocurre en la plataforma, fuera de este código
Actor: administrador
Pantalla: whatsapp_inbox: Ajustes
Pasos:
1. El administrador abre **Bandeja de WhatsApp → Ajustes**. Para pintar el bloque «Tu número», la pantalla pregunta al hub qué necesita la ventana de Meta; el hub se lo pregunta a la plataforma y devuelve su respuesta sin tocarla. Si la plataforma dice que WhatsApp no está configurado, la pantalla no enseña el bloque «Tu número» en absoluto (ni conectar, ni los números ya conectados, ni desconectar).
2. Pulsa **Conectar WhatsApp**, inicia sesión en Facebook, elige el número y escanea el QR con la app de WhatsApp Business del móvil.
3. Al cerrarse la ventana, la pantalla entrega al hub lo que devolvió Meta; el hub lo reenvía tal cual a la plataforma, firmando con la credencial del propio hub (un cajero con PIN no tiene otra que prestar).
4. La plataforma canjea el código, guarda el permiso de Meta y contesta; el hub devuelve esa misma respuesta y el bloque pasa a «Conectado».
Entra: el código de un solo uso y los identificadores que Meta entrega a la ventana (`code`, `event`, `waba_id`, `phone_number_id`, `business_id`); la sesión de quien pulsa.
Sale: el número queda ligado a este hub **en la plataforma**; el hub no guarda ni el número ni el permiso de Meta. Desde ese momento la recogida (HUB-F263) trae los mensajes nuevos y el historial que Meta entrega al conectar (HUB-F264).
Si falla: sin sesión, `401`; con la sesión de un perfil que no administra, `403` y el bloque dice «Solo un dueño o un administrador puede conectar el número de WhatsApp.»; un cuerpo que no es un objeto se rechaza antes de salir (`whatsapp.invalid_body`); si la plataforma no contesta, el hub responde `424` con `cloud_unreachable` (nunca un «conectado» falso); un rechazo 4xx de la plataforma (`missing_code`, `no_phone_number`, `hub_not_found`) vuelve con su status y su código y el bloque lo traduce («No se añadió ningún número de teléfono…», «La ventana de Facebook se cerró antes de terminar…»); un fallo de Meta o de la plataforma (5xx: Meta no contesta, Meta rechaza, no hay cuenta de WhatsApp Business, WhatsApp sin configurar) llega como `424 cloud_rejected` sin su código, y el bloque solo dice una frase genérica: las frases traducidas de esos códigos no se ven nunca (hueco). Se reintenta pulsando otra vez.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F01 (Conectar el número de WhatsApp del negocio)
Pendiente de enlazar: hub — HUB_SHELL, bloque «Tu número» dentro de Ajustes de la bandeja (abre la ventana de Meta y entrega su resultado al servidor)
Pendiente de enlazar: saas — pasarela de WhatsApp: `GET /api/v1/hub/device/whatsapp/config/` → `{configured, app_id, config_id, graph_version}` con la credencial de máquina, y `POST …/whatsapp/connect/` que canjea el código, suscribe la cuenta de WhatsApp Business, registra o sincroniza el número y guarda el token; rechazos como `{error: <código>}` y `404` solo para «Meta no devolvió ningún número». Lo que el hub necesita y no hay: que los fallos de Meta (hoy 5xx con código) lleguen con un status que el hub reenvíe con su código, o que el hub los conserve
QA: WA-01, WA-07

### HUB-F261 Saber qué número está conectado y si hay que reconectarlo
Estado: parcial — la etiqueta «App de WhatsApp Business» no aparece nunca: la plataforma no manda `is_on_biz_app` en la lista de números
Actor: administrador
Pantalla: whatsapp_inbox: Ajustes
Pasos:
1. Al abrir el bloque «Tu número», la pantalla pide al hub los números de este negocio.
2. El hub los pide a la plataforma y devuelve la lista tal cual: número visible, si está activo (la pantalla no enseña los inactivos) y si Meta retiró el permiso.
3. Con un número activo el bloque enseña «Conectado» (la etiqueta «App de WhatsApp Business» solo saldría si la lista dijera que lo es, y hoy no lo dice); si Meta retiró el permiso, «Hay que reconectar» con su explicación y **Volver a conectar WhatsApp** (HUB-F262).
Entra: la sesión del administrador.
Sale: nada; solo lee. El hub no cachea la lista: cada apertura pregunta a la plataforma.
Si falla: los mismos rechazos de sesión que HUB-F260; plataforma caída, `424` con `cloud_unreachable` y el bloque ofrece «Reintentar».
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F01 (Conectar el número de WhatsApp del negocio)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F02 (Desconectar o volver a conectar el número)
Pendiente de enlazar: hub — HUB_SHELL, bloque «Tu número» (estado «Conectado» / «Hay que reconectar»)
Pendiente de enlazar: saas — pasarela de WhatsApp: `GET …/whatsapp/numbers/` con `[{phone_number_id, display_phone, is_active, needs_reconnect, …}]` de ESTE hub (`needs_reconnect` lo marca la renovación del token de Meta cuando falla). Falta en la plataforma: `is_on_biz_app` en esta lista (hoy solo lo devuelve el canje del código)
QA: WA-01, WA-09

### HUB-F262 Desconectar o volver a conectar el número
Estado: hecho
Actor: administrador
Pantalla: whatsapp_inbox: Ajustes
Pasos:
1. En «Tu número», el administrador pulsa **Desconectar** y confirma «¿Desconectar este número? Los mensajes dejarán de llegar aquí.».
2. El hub comprueba que el identificador del número son solo cifras (como mucho 32) y pide a la plataforma que deje de enviar ese número a este hub.
3. Para volver a conectar (o reconectar tras «Hay que reconectar»), se repite HUB-F260 entero.
Entra: el identificador de Meta del número elegido; la sesión del administrador.
Sale: la plataforma deja de guardar mensajes de ese número para este hub. En el hub no se borra nada: las conversaciones de la bandeja siguen y lo ya recogido sigue en el historial interno.
Si falla: un identificador que no son cifras se rechaza en el hub con `whatsapp.invalid_phone_number_id` antes de llamar a nadie (una `/` no puede desviar la llamada a otra ruta de la plataforma, hub#1134); el resto, como HUB-F260.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F02 (Desconectar o volver a conectar el número)
Pendiente de enlazar: hub — HUB_SHELL, bloque «Tu número» (desconectar con confirmación y reconectar)
Pendiente de enlazar: saas — pasarela de WhatsApp: `POST …/whatsapp/disconnect/<phone_number_id>/` que suelta el número de este hub, y la renovación del token de Meta que marca `needs_reconnect` si Meta la rechaza
QA: WA-01, WA-09

### HUB-F263 Recoger los mensajes de WhatsApp que esperan en la plataforma
Estado: hecho
Actor: cliente, sistema
Pantalla: ninguna
Pasos:
1. La clienta escribe al número del negocio. Meta se lo entrega a la plataforma, que lo aparca para este hub (la plataforma no puede llamar a un hub: el hub va a buscarlo).
2. Cada 5 segundos el hub pregunta por lo que tiene pendiente, siempre que la Bandeja de WhatsApp esté instalada y activa, el hub esté enrolado y el plan conocido no la bloquee (si el hub aún no conoce su plan, recoge); si no, no sale ni una petición. El intervalo se puede cambiar por entorno (`HUB_WHATSAPP_POLL_SECS`) y todas las llamadas del hub a la plataforma comparten un freno de tasa por hub (5.000 por hora), del que esta recogida gasta 720.
3. La plataforma entrega hasta 100 mensajes por vuelta, del más antiguo al más reciente. Por cada uno el hub escribe un aviso del núcleo con el número, el texto, si lo escribió la clienta o el negocio, si es en vivo o del historial, lo que tocó (si tocó una opción) y el mensaje de Meta tal cual.
4. Solo **después** de escribirlos confirma a la plataforma cuáles ya tiene; lo confirmado no se le vuelve a servir.
5. El reparto de avisos del hub entrega el mensaje a la Bandeja de WhatsApp, que lo guarda y lo enseña (WHATSAPP_INBOX-F03), y arranca las automatizaciones que escuchan ese aviso (las recetas de cita y de mesa).
Entra: los mensajes pendientes de este hub en la plataforma (`wa_message_id`, `from`, `contact`, `direction`, `source`, `reply_id`, `reply_title`, `reply_to`, `payload`, `received_at`).
Sale: un aviso `hub.whatsapp.message_received` por mensaje, con identificador `wa-<id de Meta>`; el módulo lo convierte en su propio aviso público y en la conversación. El hub no lee ni filtra el contenido: lo que se pinta o se contesta lo decide quien escucha.
Si falla:
- **Mismo mensaje dos veces** (una confirmación perdida, un reintento de Meta): el identificador ya existe y no se escribe otro aviso; se vuelve a confirmar para que la plataforma deje de servirlo. Un mensaje, una conversación, un arranque (WA-08).
- **Un mensaje no se pudo escribir**: no se confirma, así que vuelve en la vuelta siguiente; el resto de la página sigue su curso.
- **La confirmación falla**: no se pierde nada, los avisos ya están escritos; la siguiente vuelta los recibe otra vez y los descarta como duplicados.
- **La plataforma rechaza la credencial del hub** (401/403): el hub deja de preguntar con esperas que se duplican desde 10 s hasta 5 minutos, con un solo aviso en el registro al empezar y otro al recuperarse, sin reiniciar (hub#733). Cualquier otro fallo (red, 5xx) se reintenta en la vuelta siguiente.
- **Hub apagado, en pausa, módulo pausado o plan vencido**: los mensajes esperan en la plataforma, sin caducidad, y llegan al volver, 100 cada 5 s. El hub no mira su antigüedad: un mensaje en vivo de hace dos días se entrega como en vivo y arranca las recetas igual (hueco, ver «Dudas abiertas»).
- **Orden**: se escriben en el orden en que la plataforma los sirve y el reparto los entrega por orden de escritura; un mensaje que tuvo que volver queda detrás de los que entraron después, y Meta tampoco garantiza el orden. Cada aviso lleva la hora de la plataforma.
- Con el cupo del mes agotado el hub los recoge igual; es el módulo el que deja de guardar los entrantes en vivo (WHATSAPP_INBOX-F13). Las recetas se disparan igual, porque escuchan el aviso del núcleo y no el del módulo: la conversación no se guarda, la receta corre (gasta un turno del asistente y puede reservar) y solo su respuesta cae a «Eventos caídos» por cupo (HUB-F266).
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F03 (Recibir un mensaje en la bandeja)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F13 (Ver el consumo del mes y llegar al tope)
Pendiente de enlazar: architecture — REC_WA_CITA-F02 (La clienta escribe y el mensaje llega al hub)
Pendiente de enlazar: architecture — REC_WA_MESA-F02 (El comensal escribe y el mensaje llega al hub)
Pendiente de enlazar: hub — HUB, avisos entre módulos (reparto del aviso a sus oyentes, reintentos y eventos caídos)
Pendiente de enlazar: saas — pasarela de WhatsApp: recibe el webhook de Meta, aparca por hub (`wa_message_id` único) y sirve `GET /api/v1/hub/device/whatsapp/inbox/?direction=all&source=all` (pendiente = no confirmado, del más antiguo al más reciente, máx. 100) y `POST …/inbox/ack/` con `{wa_message_ids}` (máx. 500, responde cuántas filas cambió)
QA: WA-02, WA-08, BD-07

### HUB-F264 Distinguir lo que contesta el dueño desde el móvil y el historial al conectar
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dueño contesta a una clienta desde la app WhatsApp Business del móvil. Meta devuelve a la plataforma una copia de lo que él escribió, y la recogida (HUB-F263) la trae como mensaje **del negocio**, colgado del número de la clienta y no del número de la tienda.
2. Al conectar el número, Meta entrega hasta 180 días de historial; la recogida lo trae marcado como **historial**, con la hora en que se dijo.
3. Una foto, nota de voz o documento reciente del historial llega primero vacío y después completo: el hub escribe la copia completa como un aviso nuevo, marcado como historial, y una repetición idéntica no escribe nada (hub#2102).
4. La bandeja enseña la respuesta del dueño en el hilo correcto sin sumar «Sin leer», y el historial con su hora (WHATSAPP_INBOX-F08, WHATSAPP_INBOX-F03).
Entra: los campos `direction` (`inbound`/`outbound`), `contact` (el número del otro lado) y `source` (`live`/`history`) que sirve la plataforma; si una plataforma antigua no los manda, valen `inbound`, el remitente y `live`.
Sale: los mismos avisos de HUB-F263 con esas tres marcas; la copia completa de un mensaje del historial con identificador `wa-<id>~<huella del mensaje>`. El hub **no** filtra nada: dejar fuera de las respuestas automáticas el eco del dueño y el historial lo hacen las recetas en su disparador (WHATSAPP_INBOX-F21, F24), y una automatización montada a mano sin ese filtro contestaría encima (FLOWS-F11).
Si falla: un valor de `direction` o `source` fuera de contrato no se reinterpreta: viaja tal cual al aviso y se nombra una vez en el registro, igual que un campo nuevo que este hub no conoce (que no viaja); un mensaje en vivo ya recogido nunca se vuelve a emitir aunque la plataforma lo sirva con otro contenido.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F03 (Recibir un mensaje en la bandeja)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F08 (Contestar desde la app de WhatsApp Business del móvil)
Pendiente de enlazar: flows — FLOWS-F11 (Reparar una automatización de WhatsApp montada con un fallo ya corregido)
Pendiente de enlazar: architecture — REC_WA_CITA-F09 (Cuando la respuesta automática no puede contestar)
Pendiente de enlazar: architecture — REC_WA_MESA-F09 (Cuando la respuesta automática no puede contestar)
Pendiente de enlazar: saas — pasarela de WhatsApp: guarda el eco del dueño (`direction=outbound`, `contact` = la clienta) y el historial de coexistencia (`source=history`), y completa en su sitio la fila de un adjunto del historial volviendo a servirla con el mismo `wamid`
QA: W-05, WA-02

### HUB-F265 Saber a qué pregunta contesta lo que toca la clienta
Estado: hecho
Actor: cliente, sistema
Pantalla: ninguna
Pasos:
1. Una automatización manda a la clienta un WhatsApp con opciones para tocar (botones o una lista) por HUB-F266; al salir, el hub apunta el identificador que Meta dio a ese mensaje junto con la automatización y el paso que lo mandó.
2. La clienta toca una opción. La recogida trae su respuesta con lo que tocó (identificador y texto de la opción) y el identificador del mensaje al que responde.
3. Antes de escribir el aviso, el hub busca ese identificador en lo que él mismo mandó y añade qué automatización y qué paso hicieron la pregunta.
4. La automatización que espera esa respuesta la reconoce aunque haya dos preguntas abiertas con el mismo «Sí».
Entra: `reply_id`, `reply_title` y `reply_to` de la plataforma o, si no los trae, leídos del mensaje de Meta.
Sale: el aviso lleva además `reply_to_step` y `reply_to_flow`; vacíos (nunca ausentes) cuando el mensaje no contesta a nada que este hub mandara.
Si falla: si la búsqueda no se puede hacer, el mensaje no se escribe ni se confirma y vuelve en la vuelta siguiente (no se entrega un toque sin saber a qué pregunta contesta); un identificador de otro hub o desconocido deja los dos campos vacíos.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F19 (Elegir el hueco escribiendo en vez de tocando)
Pendiente de enlazar: flows — FLOWS-F14 (Añadir, ordenar y rellenar los pasos)
Pendiente de enlazar: hub — HUB, automatizaciones (el paso «esperar respuesta» que compara el toque con la pregunta)
Pendiente de enlazar: saas — pasarela de WhatsApp: saca `reply_id`/`reply_title` del botón o fila tocados y `reply_to` del `context.id` de Meta, y devuelve el `message_id` (`wamid`) de cada envío
QA: W-02, W-07

### HUB-F266 Mandar un WhatsApp desde el hub
Estado: parcial — el hub no sabe si la clienta escribió en las últimas 24 h: si Meta rechaza en el acto, la plataforma contesta `502 meta_send_failed` y el hub lo reintenta 8 veces (≈4 min) antes de «Eventos caídos»; si Meta lo falla después, nada lo registra; y cualquier 429, también el freno de tasa, se toma por cupo agotado
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una automatización (una receta de la bandeja o una montada en Automatizaciones) llega a un paso de mensaje por WhatsApp; el hub lo deja en la cola de avisos, no lo manda en el acto.
2. Al repartirlo, el hub comprueba quién lo manda: una automatización necesita sus dos permisos concedidos (el canal y de qué consulta sale el teléfono) y el teléfono se lee de esa consulta; un módulo necesita la capacidad de notificaciones concedida, el canal WhatsApp declarado y un destinatario de la lista del negocio. En los dos casos el teléfono tiene que ir con `+` y entre 8 y 15 cifras.
3. Lo manda a la plataforma: una plantilla aprobada (con su cabecera, que si es un archivo subido al hub se firma en ese momento), o texto libre, o texto con opciones para tocar.
4. La plataforma cobra el mensaje del cupo y lo entrega a Meta; el hub apunta el identificador de Meta junto con la automatización y el paso que lo mandaron (HUB-F265).
Entra: la intención de envío (`channel`, `to`, `template`, `vars`, opciones `interactive`), y opcionalmente cuál de los números del negocio la manda.
Sale: el mensaje en el móvil de la clienta; en el historial del hub, la entrega con el identificador de Meta. La ventana de 24 h no la vigila el hub. Una automatización puede preguntar la hora actual en un paso «solo si» (`now.iso`, hub#1694), pero necesita además la hora del último mensaje de la clienta (sin confirmar qué consulta la da). Si Meta acepta el envío y lo falla después, la plataforma descarta ese estado y el hub lo da por enviado.
Si falla:
- **Cupo del mes agotado** (la plataforma contesta 429 `quota_exceeded`): no se reintenta; el aviso cae al momento a «Eventos caídos» con el motivo y se reintenta a mano cuando haya cupo (hub#971). El hub trata así **cualquier** 429 o 402 sin mirar el cuerpo, y la plataforma también contesta 429 cuando el hub agota su freno de tasa por hora (compartido con la recogida, el asistente y el resto): un envío frenado por tasa cae igual, sin reintentos (hueco).
- **Módulo sin la capacidad de notificaciones concedida**: no se manda; cae al momento con su motivo y vuelve a la cola sola cuando el dueño la concede (hub#1192). Lo que pasa cuando a una automatización le retiran un permiso es del motor de automatizaciones.
- **Plataforma caída, rechazo (Meta rechaza: `502 meta_send_failed`; plantilla no aprobada: `409 template_not_approved`), o el archivo de cabecera no se pudo firmar**: se reintenta con esperas de 2, 4, 8… 128 s y, tras 8 intentos (unos 4 minutos), cae a «Eventos caídos»: una caída de la plataforma de más de 4 minutos deja todos los envíos de ese rato para reintentar a mano.
- **Hub sin enrolar**: falla y se reintenta, nunca se da por enviado.
- **Una forma imposible** (dos cabeceras, opciones que no son un objeto, una variable fuera de plantilla, un teléfono sin `+`) no llega a la plataforma, pero se trata como cualquier fallo: los 8 intentos y después «Eventos caídos», con el motivo. Las automatizaciones la rechazan antes, al guardar el paso.
Implicados: pendiente
Pendiente de enlazar: flows — FLOWS-F15 (Mandar un mensaje a un cliente desde una automatización)
Pendiente de enlazar: flows — FLOWS-F25 (Reenviar o cerrar lo que no llegó a pasar)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F13 (Ver el consumo del mes y llegar al tope)
Pendiente de enlazar: hub — HUB, avisos entre módulos (cola, reintentos, «Eventos caídos» y su reintento a mano)
Pendiente de enlazar: hub — HUB, automatizaciones (paso de mensaje: permisos de canal y de destinatario, cabecera subida al hub)
Pendiente de enlazar: saas — pasarela de WhatsApp: `POST /api/v1/hub/device/notify/whatsapp/` con `{to, body | template{name, language, components}, interactive?, phone_number_id?}` → `{message_id}`; cobra del cupo antes de gastar y contesta `429 quota_exceeded` al agotarlo; cualquier fallo de Meta es hoy `502 meta_send_failed` y los estados `failed` que Meta manda luego por webhook se descartan. Lo que el hub necesita y no hay: un código distinguible para «ventana de 24 h cerrada», que el freno de tasa no use el mismo 429 que el cupo agotado (o un cuerpo que los distinga), y avisar al hub de un envío que Meta falla después
QA: WA-04, WA-07, qa-hub-flows R7

### HUB-F267 Ver una foto, una nota de voz o un documento de la clienta
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: whatsapp_inbox: Bandeja de entrada
Pasos:
1. En un hilo de la bandeja, la persona abre una foto o pulsa **Reproducir** o **Descargar**.
2. La bandeja pide el adjunto al hub por el identificador que Meta le dio (solo cifras, hasta 32).
3. El hub comprueba que hay una persona con sesión y que su perfil puede leer la bandeja; si la petición viene de un módulo, que ese módulo tenga concedidas las notificaciones y declarado WhatsApp.
4. El hub pide el archivo a la plataforma y lo pasa a la pantalla según llega, sin guardarlo, con el tipo que dio Meta.
Entra: el identificador del adjunto; la sesión de quien mira.
Sale: el archivo, marcado para que el navegador no lo guarde en caché compartida, no lo ejecute y lo descargue si se abre la dirección directamente. Nada queda en el hub.
Si falla: sin sesión, `401`; sin permiso de leer la bandeja, rechazo de permiso; un identificador que no son cifras, `invalid_media_id` antes de llamar a nadie; la plataforma rechaza con su código y la bandeja distingue «ya no está disponible» (`media_not_found`), «inténtalo otra vez» (`media_unavailable`) y «vuelve a conectar WhatsApp» (`meta_permission_denied`); plataforma caída, `cloud_unreachable`. Una llave de API no es una persona y no pasa.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F06 (Ver una foto, una nota de voz o un documento)
Pendiente de enlazar: saas — pasarela de WhatsApp: `GET …/whatsapp/media/<media_id>/` que canjea el id de Meta por los bytes con el token del negocio y los sirve con el `Content-Type` de Meta; rechazos `{error, detail}` decididos antes del primer byte
QA: WA-10

### HUB-F268 Ver las plantillas del negocio con lo que dice Meta de cada una
Estado: hecho
Actor: administrador
Pantalla: whatsapp_inbox: Plantillas de Meta
Pasos:
1. Al abrir **Ajustes** de la bandeja, el módulo pide al hub las plantillas.
2. El hub exige una sesión de administrador y, como la pide un módulo, que ese módulo tenga concedidas las notificaciones y declarado WhatsApp.
3. Pide la lista a la plataforma, que en ese momento pregunta a Meta, y la devuelve dentro del sobre del hub con nombre, idioma, categoría, estado y motivo de rechazo de cada una, y la marca de «no pude preguntar a Meta» si la hay.
Entra: la sesión del administrador y el módulo que pregunta.
Sale: nada en el hub. El módulo guarda los veredictos y trae las que el negocio creó en WhatsApp Manager (WHATSAPP_INBOX-F27, F28). Se pregunta al abrir, nunca con un temporizador: la plataforma consulta a Meta en cada llamada y no tiene freno propio.
Si falla: sin sesión, `401`; cajero, `403`; módulo sin la capacidad concedida o sin WhatsApp declarado, `capability_denied`; Meta inalcanzable, la plataforma contesta con lo último que sabía y la marca `stale`; plataforma caída, `cloud_unreachable` en el sobre; un 5xx de la plataforma, aunque traiga código, llega como `424 cloud_rejected`.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F27 (Ver las plantillas y lo que dice Meta de cada una)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F28 (Traer las plantillas creadas en WhatsApp Manager)
Pendiente de enlazar: saas — pasarela de WhatsApp: `GET …/whatsapp/templates/` → `{templates: [{name, language, category, status, rejected_reason, meta_id, …contenido}], stale}`, refrescando contra Meta en cada llamada
QA: WA-04

### HUB-F269 Mandar una plantilla a revisión de Meta, nueva o editada
Estado: parcial — cuando Meta rechaza la plantilla (`meta_template_failed`) o no contesta (`meta_unreachable`), el módulo recibe `cloud_rejected` sin el motivo de Meta
Actor: administrador
Pantalla: whatsapp_inbox: Plantillas de Meta
Pasos:
1. El administrador pulsa **Añadir** o **Guardar** en el panel de la plantilla.
2. El módulo entrega al hub la plantilla tal como se escribió (nombre, idioma, categoría, cabecera, cuerpo, pie, ejemplos, botones).
3. El hub comprueba la misma puerta que HUB-F268 y que el cuerpo es un objeto, y la reenvía a la plataforma sin validar nada más: las reglas de Meta las conoce la plataforma.
4. La plataforma la registra (o la edita) en Meta; las dos vuelven a «En revisión», y el hub devuelve su respuesta dentro del sobre.
Entra: la plantilla escrita por el negocio; si lleva cabecera de archivo, el identificador de la muestra ya subida (HUB-F270).
Sale: la plantilla registrada en Meta (`201` nueva, `200` editada); el módulo guarda el veredicto (WHATSAPP_INBOX-F29, F30).
Si falla: los rechazos 4xx de la plataforma (`invalid_name`, `missing_example`, `meta_rate_limited`…) llegan con su status y su código intactos para que el módulo los diga en español, y uno sin código llega como `cloud_rejected`; el rechazo de Meta (`502 meta_template_failed`, con el motivo de Meta en el detalle) y «Meta no contesta» (`503 meta_unreachable`) llegan como `424 cloud_rejected` y su motivo se pierde (la puerta de muestras y la de adjuntos sí conservan el código de un 5xx; esta no); sin sesión, sin permiso o sin capacidad, como HUB-F268.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F29 (Crear una plantilla y mandarla a revisión)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F30 (Editar una plantilla)
Pendiente de enlazar: saas — pasarela de WhatsApp: `POST …/whatsapp/templates/` que valida contra las reglas de Meta, registra o edita y responde `201`/`200` con el estado `PENDING`; rechazos `{error: <código>}`. Hoy `502 meta_template_failed` y `503 meta_unreachable` se pierden en el hub; o el hub los conserva, o la plataforma los da con un status 4xx
QA: WA-04

### HUB-F270 Subir a Meta la muestra de la cabecera de una plantilla
Estado: hecho
Actor: administrador
Pantalla: whatsapp_inbox: Plantillas de Meta
Pasos:
1. En una plantilla con cabecera de imagen, vídeo o PDF, el administrador elige **Elegir archivo de ejemplo**.
2. El módulo manda el archivo al hub en un formulario; el hub comprueba la puerta de HUB-F268, que el formulario declara su tamaño y que no pasa de lo que Meta acepta para un PDF (100 MB más un margen para el formulario).
3. El hub lo reenvía a la plataforma según llega, sin leerlo ni guardarlo; la plataforma mira qué es de verdad, lo sube a Meta y devuelve el identificador de la muestra.
4. El módulo guarda ese identificador y lo manda al registrar la plantilla (HUB-F269).
Entra: el archivo (`multipart/form-data`, campo `file`) con su tamaño declarado.
Sale: `{header_handle, format, mime_type, size}` dentro del sobre. Nada se guarda en el hub ni en el módulo: la muestra vive en Meta.
Si falla: sin formulario o sin su separador, `whatsapp.invalid_header_sample_upload`; sin tamaño declarado, `411`; más grande de lo que Meta acepta, `413` con `header_sample_too_large` (el mismo código que da la plataforma); tipo o tamaño por tipo no aceptados (JPEG/PNG hasta 5 MB, MP4 hasta 16 MB, PDF hasta 100 MB), lo rechaza la plataforma con su código.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F29 (Crear una plantilla y mandarla a revisión)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F30 (Editar una plantilla)
Pendiente de enlazar: saas — pasarela de WhatsApp: `POST …/whatsapp/template-header-samples/` (campo `file`) que comprueba el tipo por los bytes y el tamaño por tipo y sube la muestra a Meta; `201` con `header_handle`, rechazos `missing_file`, `unsupported_header_sample`, `header_sample_too_large`, `no_whatsapp_number`, `meta_*`
QA: WA-04

### HUB-F271 Borrar una plantilla en Meta
Estado: parcial — la puerta existe y funciona, pero ningún módulo la usa: borrar en la bandeja no la borra en Meta (WHATSAPP_INBOX-F31)
Actor: administrador
Pantalla: asistente
Pasos:
1. Quien llama (hoy solo la API, con sesión de administrador) pide al hub borrar una plantilla por su nombre.
2. El hub comprueba la puerta de HUB-F268 y que el nombre son solo minúsculas, cifras y guiones bajos (hasta 512).
3. La plataforma la borra en Meta y en su registro, **en todos sus idiomas**, como hace Meta.
Entra: el nombre de la plantilla; la sesión del administrador.
Sale: la plantilla deja de existir en Meta; respuesta vacía si todo fue bien.
Si falla: un nombre con otros caracteres se rechaza en el hub (`whatsapp.invalid_template_name`) antes de llamar a nadie; el resto, como HUB-F268 (un 5xx de la plataforma pierde su código). Borrar no se puede deshacer: una plantilla aprobada tarda días en volver a aprobarse.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F31 (Borrar una plantilla)
Pendiente de enlazar: saas — pasarela de WhatsApp: `DELETE …/whatsapp/templates/<name>/` que borra en Meta todos los idiomas de esa plantilla y responde vacío
QA: ninguno

### HUB-F272 Reflejar en el hub el cupo y el consumo de WhatsApp del mes
Estado: parcial — el consumo que enseña la pestaña Plan solo se refresca al arrancar el hub y una vez cada 24 h, así que puede ir hasta un día por detrás de lo que cobra la plataforma; un cambio de plan tampoco llega al medidor hasta esa vuelta; y al instalar la Bandeja con el hub ya encendido, el tope no llega hasta la siguiente vuelta diaria (el medidor queda en 0, que en el módulo es «sin tope»)
Actor: sistema
Pantalla: HUB_SHELL: Plan del módulo
Pasos:
1. Al arrancar y después una vez al día, si la Bandeja de WhatsApp está instalada y activa, el hub pregunta a la plataforma el plan del canal y lo gastado este mes.
2. Si la plataforma da un tope mayor que cero, el hub lo escribe en el medidor del módulo por una orden interna que nadie más puede llamar; si además da lo gastado y el módulo instalado sabe recibirlo, lo escribe al lado.
3. La pestaña **Plan** del módulo enseña esos dos números; al llegar al tope, «Has consumido todo lo que incluye tu plan este mes.» (WHATSAPP_INBOX-F13).
Entra: `tier.max_billable_messages` (o su alias `max_conversations`) y `usage.billable_messages` de la plataforma.
Sale: el tope y el consumo del mes en el medidor del módulo. El hub no cuenta nada por su cuenta: el único contador es el de la plataforma, que es también la que corta los envíos (HUB-F266).
Si falla: sin respuesta de la plataforma, un plan sin tope o un tope de cero, **no se escribe** (en el medidor, cero significa «sin tope», y un silencio no es un plan); el fallo queda en el registro del hub y llega al SaaS. Un consumo de cero sí se escribe (es el día 1). Si el módulo instalado es anterior al campo de consumo, se escribe solo el tope.
Implicados: pendiente
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F13 (Ver el consumo del mes y llegar al tope)
Pendiente de enlazar: architecture — REC_WA_CITA-F02 (La clienta escribe y el mensaje llega al hub)
Pendiente de enlazar: architecture — REC_WA_MESA-F02 (El comensal escribe y el mensaje llega al hub)
Pendiente de enlazar: hub — HUB_SHELL, pestaña Plan del módulo
Pendiente de enlazar: saas — facturación de WhatsApp: `GET /api/v1/hub/device/whatsapp/plan/` → `{tier: {max_billable_messages, max_conversations, …} | null, usage: {billable_messages, month}, available_tiers}`, el mismo contador que hace cumplir al enviar
QA: WA-03
