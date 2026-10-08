# WORKFLOW — Hub (servidor) · Automatizaciones

Prefijo: HUB

> Área «Automatizaciones» del servidor del hub: el motor de ADR-0283 (`crates/runtime/src/flows/`,
> `flows_api.rs`, `secret_box.rs`; `crates/server`: `flows_api`, `flow_io`, `flows_header_media`,
> `agent_runner`) y las lecturas del catálogo de avisos que usa el editor (`outbox_admin`,
> `event_shape`). Contrastado contra `origin/develop` del hub el 05/10/2026. Lo técnico vive en
> `architecture/hub/flows.md`.
>
> **Reparto.** El motor no tiene pantalla propia: la pantalla «Automatizaciones» es el módulo
> `flows` (FLOWS-F01…F29) y las recetas de WhatsApp se encienden desde la Bandeja de WhatsApp. Aquí
> se cuenta qué hace el hub cuando esas pantallas le piden algo, y qué hace solo, por su cuenta.
> Todas las puertas del motor exigen la **sesión de un dueño o administrador** del hub (anónimo:
> rechazo por falta de sesión; cajero o empleado: rechazo por perfil) y, si la petición se declara
> hecha por un módulo (cabecera `X-Erplora-Module`), que ese módulo tenga **«Administrar
> automatizaciones»** (`manage_flows`) concedido. Esa cabecera es una **declaración, no una
> autenticación**: un módulo que no se declara pasa solo con la sesión del administrador. Las
> excepciones (las recetas de fábrica) se dicen en su flujo.

## Referencia adoptada

La ya contrastada en `.claude/agents/qa-hub-flows.md` (recorridos R0–R10,
scorecard contra Zapier, Make, Power Automate, Shopify Flow, Odoo y Business Central) y en el
`WORKFLOW.md` de `flows`. Se adopta: disparador elegido de una lista (aviso, horario en la hora del
negocio, fecha, a mano), columna lineal sin bifurcaciones (ADR-0461), permisos explícitos por
automatización (ADR-0283 D2), pregunta a una persona con plazo y qué pasa con el silencio (Power
Automate, Odoo «Allowed Group»), secretos de solo escritura, y recetas de fábrica que se encienden
en un toque desde su módulo (ADR-0470; Square y Vagaro: un interruptor).

## Antes de empezar

- Para automatizar: instalar Automatizaciones, concederle «Administrar automatizaciones» y entrar
  como dueño o administrador (HUB-F111, FLOWS-F01).
- Para usar secretos en «Llamar a otro sistema», el hub necesita su llave de cifrado
  (`HUB_SECRETS_KEY`, del despliegue) (HUB-F99).
- Lo que vale también para los avisos (permisos para imprimir o avisar, mensajes) está en
  [avisos.md](avisos.md).

## Flujos

### HUB-F80 Crear una automatización
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. Desde Automatizaciones (desde cero, una tarjeta de la galería, una copia o un borrador del asistente) se manda al hub el nombre, si nace encendida y el documento entero: cuándo arranca y sus pasos.
2. El hub lee el documento entero antes de guardar nada: la versión del documento, cada disparador, cada paso y cada dato que nombra.
3. Si algo no encaja, no guarda nada y dice qué (un horario imposible, una consulta que no existe, una espera de más de 90 días, una pregunta de más de 30 días).
4. Si encaja, la guarda y arma sus disparadores. La automatización nace **sin ningún permiso**.
Entra: `{name, enabled, definition}`; la sesión del administrador.
Sale: la automatización guardada (`_flow`) con quién la creó, y sus disparadores armados (`_flow_triggers`). Si no se dice nada, nace **encendida**: la pausa de la galería, la copia y el borrador la pide la pantalla.
Si falla: sin nombre o sin documento, se rechaza. Una versión de documento distinta de la 1 (también más nueva) se rechaza (`flow.unknown_schema_version`). Una clave que el hub no conoce, pasos vacíos o repetidos, un operador desconocido o un secreto usado fuera de un paso «Llamar a otro sistema» se rechazan (`flow.invalid_definition`, `flow.unknown_operator`, `flow.secret_not_available`). Un horario o una fecha imposibles, `flow.invalid_cron` / `flow.invalid_at`. Una consulta que el hub no tiene, «no encontrada». Una acción **interna** de un módulo se rechaza; una acción que **no existe** se acepta (puede ser de un módulo aún no instalado) y fallará al ejecutarse o al conceder su permiso. Todos los mensajes del hub van en inglés.
Implicados: FLOWS-F04, FLOWS-F08, FLOWS-F12, FLOWS-F27, FLOWS-F05, FLOWS-F13
QA: qa-hub-flows R1, BD-10

### HUB-F81 Ver las automatizaciones del negocio
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Automatizaciones
Pasos:
1. Al abrir Automatizaciones, la pantalla pide al hub todas las automatizaciones del negocio.
2. El hub las devuelve de una vez, con su documento, si están encendidas y de qué receta de fábrica salen si es el caso.
3. Al abrir una, la pide sola.
Entra: la sesión del administrador.
Sale: la lista, sin las borradas; nada guardado.
Si falla: una automatización borrada o de otro hub da «no encontrada».
Implicados: FLOWS-F02
QA: qa-hub-flows R10

### HUB-F82 Arrancar una automatización cuando pasa algo en el negocio
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo deja un aviso («se cobra una venta») y el hub lo reparte (HUB-F51).
2. En la misma entrega, el hub busca las automatizaciones **encendidas** que arrancan con ese aviso.
3. Si la automatización lleva un filtro («solo si el total pasa de 100 €»), lo comprueba con los datos del aviso; si no casa, no arranca nada.
4. Por cada una que casa, apunta una ejecución nueva con los datos del aviso (todos, o solo los que la automatización elige). La ejecuta el motor en el siguiente segundo, fuera de la entrega.
Entra: el aviso entregado y los disparadores de tipo aviso (`event`, con `filter` e `input`).
Sale: una ejecución pendiente (`_flow_runs`) que recuerda qué aviso la arrancó. Un mismo aviso entregado dos veces no crea dos ejecuciones.
Si falla: los avisos que llegan con la automatización en pausa se pierden para ella (no se recuperan al encenderla). Un filtro que el hub no sabe leer no casa nunca (se apunta en el registro del servidor). Una ruta que el aviso no trae no casa. Si la automatización ya arrancó 30 veces en el último minuto, o el aviso viene de una cadena de 16 niveles, no arranca (HUB-F110). Si apuntar la ejecución falla, el aviso entero se reintenta (HUB-F52).
Implicados: FLOWS-F13
QA: qa-hub-flows R1, qa-hub-flows R2, BD-10

### HUB-F83 Arrancar una automatización según un horario, en la hora del negocio
Estado: parcial — al volver a encender una automatización pausada, el disparo que le tocó mientras estaba en pausa sale al momento (el hub conserva su hora); y si se cambia el horario, el reloj viejo no se migra (es otro disparador)
Actor: sistema
Pantalla: ninguna
Pasos:
1. La automatización dice cada cuánto («todos los días a las 9:00», «los lunes a las 8:00», «el día 1 de cada mes»).
2. El hub lo lee en la hora del negocio: la zona de los ajustes del negocio o, si no hay, la que se deduce del país y la región (Canarias tiene la suya); y guarda la próxima hora.
3. Cada segundo mira qué horarios han llegado y arranca una ejecución por cada uno.
4. Si el hub estuvo apagado y se perdió varios disparos, al volver hace **uno solo** y sigue con la siguiente hora que toque.
5. En el cambio de hora: una hora que no existe (primavera) dispara en el salto; una hora que se repite (otoño) dispara una sola vez.
Entra: el horario (`cron` de 5 campos con rangos, listas, pasos, nombres de mes y de día, y `@daily` y similares) y la zona del negocio.
Sale: una ejecución pendiente por disparo; la próxima hora guardada en UTC. Si cambia la zona del negocio, el horario se recalcula.
En este mismo documento se apoya en: HUB-F227 (Fijar la zona horaria del negocio), HUB-F229 (Mover los horarios de las automatizaciones con la zona).
Si falla: un horario imposible no se guarda (HUB-F80). Por encima de 30 ejecuciones por minuto, el disparo se salta. Los datos de entrada que un horario declara se resuelven sin aviso detrás (vacíos), y un filtro en un disparador por horario se acepta y se ignora.
Implicados: FLOWS-F13
QA: qa-hub-flows R2

### HUB-F84 Arrancar una automatización una vez, en una fecha y hora
Estado: parcial — el hub compara la fecha como texto con la hora UTC: una fecha con desplazamiento distinto de UTC (`+02:00`), que puede llegar por la API, por un borrador del asistente o por una receta, dispara dos horas tarde, o antes si es negativo (leído, sin ejecutar). El editor de Automatizaciones siempre manda UTC (`Z`) y con él no ocurre
Actor: sistema
Pantalla: ninguna
Pasos:
1. La automatización dice un instante concreto, con su zona.
2. Cuando llega, el hub arranca una ejecución.
3. Después ese disparador se apaga para siempre.
Entra: el instante (`at`, RFC-3339 con desplazamiento obligatorio).
Sale: una ejecución pendiente; el disparador apagado y sin próxima hora.
Si falla: un instante ilegible no se guarda (`flow.invalid_at`). Un instante ya pasado dispara en cuanto se guarda la automatización encendida, y uno que venció con el hub apagado dispara al volver.
Implicados: FLOWS-F13
QA: qa-hub-flows R2

### HUB-F85 Lanzar una automatización a mano
Estado: parcial — solo por la API: Automatizaciones no tiene botón «Ejecutar» (FLOWS-F22); y las ejecuciones a mano no tienen límite, pero sí cuentan: 30 lanzadas a mano en un minuto frenan durante ese minuto los disparos por aviso y por horario de esa automatización
Actor: administrador
Pantalla: asistente
Pasos:
1. Se pide al hub que ejecute ya una automatización encendida, con datos de entrada si se quiere.
2. El hub apunta la ejecución y contesta en el acto con su referencia; la ejecuta el motor en el siguiente segundo.
3. Su resultado aparece en el historial (HUB-F102).
Entra: la automatización, los datos de entrada (`input` o el cuerpo entero) y la sesión del administrador (`POST /api/hub/flows/{id}/run`).
Sale: una ejecución real, con todos sus efectos: el hub no tiene modo de prueba.
Si falla: una automatización en pausa se niega (`flow.disabled`); una borrada o de otro hub, «no encontrada».
Implicados: FLOWS-F22
QA: qa-hub-flows R2 (discrepa)

### HUB-F86 Guardar los cambios de una automatización
Estado: parcial — no hay control de versiones: dos personas que guardan a la vez se pisan sin aviso; y una ejecución a medias sigue con el documento nuevo por número de paso, así que añadir o quitar pasos la mueve a otro paso (leído, sin ejecutar)
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. Desde el editor, la lista o el arreglo de una automatización de WhatsApp se manda al hub el documento entero otra vez, con el nombre y el interruptor.
2. El hub lo vuelve a leer entero, igual que al crear (HUB-F80).
3. Si encaja, lo guarda y rearma los disparadores: un horario que no ha cambiado conserva su próxima hora; uno cambiado empieza de cero.
Entra: `{name, enabled, definition}` completo.
Sale: la automatización con quién la cambió y cuándo; los disparadores rearmados. Los permisos no cambian.
Si falla: lo mismo que HUB-F80, y no se guarda nada. Una automatización borrada no se puede guardar.
Implicados: FLOWS-F03, FLOWS-F11, FLOWS-F21
QA: qa-hub-flows R10

### HUB-F87 Pausar una automatización y volver a encenderla
Estado: parcial — pausar no frena todo (hub#2650): una propuesta que esperaba se puede aprobar y su acción se ejecuta, los mensajes que ya estaban en cola salen, una llamada a otro sistema en vuelo se hace, y un turno del asistente en curso puede ejecutar su acción o dejar una propuesta nueva aunque ya esté en pausa; y al volver a encenderla, el horario o la fecha que vencieron en la pausa disparan al momento
Actor: administrador
Pantalla: FLOWS: Automatizaciones
Pasos:
1. Se guarda la automatización con el interruptor apagado (HUB-F86).
2. Desde ese momento no arranca con ningún aviso ni horario.
3. Una ejecución que estaba lista para seguir se cancela en su siguiente paso (en un segundo); si la pausa llega mientras el motor la está avanzando en ese mismo segundo, puede dar hasta 8 pasos más. Una que estaba esperando un plazo se cancela al despertar, salvo que se haya vuelto a encender antes; mientras tanto, los avisos que cancelan o reprograman su espera siguen actuando.
4. Al volver a encenderla, arranca de nuevo con lo que pase desde entonces.
Entra: la automatización con `enabled: false` o `true`.
Sale: la automatización pausada o encendida; las ejecuciones canceladas con el motivo «la automatización se apagó mientras corría». Los permisos y el historial se quedan.
Si falla: lo mismo que HUB-F86.
Implicados: FLOWS-F03, FLOWS-F21
QA: qa-hub-flows R10

### HUB-F88 Borrar una automatización
Estado: parcial — las preguntas y propuestas que esperaban respuesta no se cancelan: siguen en la bandeja hasta que alguien contesta o caducan
Actor: administrador
Pantalla: FLOWS: Automatizaciones
Pasos:
1. Se pide al hub que borre la automatización.
2. Deja de arrancar al momento; lo que esperaba un plazo se cancela al momento; sus permisos se retiran; los mensajes que tenía en cola ya no saldrán.
3. Su historial se conserva.
Entra: la automatización y la sesión del administrador.
Sale: la automatización marcada como borrada (quién y cuándo, nunca se borra la fila), sus disparadores y esperas desarmados, sus permisos retirados, sus ejecuciones dormidas o pendientes canceladas (`flow.flow_deleted`), y sus mensajes en cola se cierran en «Eventos caídos» sin destinatario cuando el repartidor vuelve a tomarlos (al momento si estaban pendientes, en su próximo reintento si estaban apartados) (HUB-F53). Aprobar una propuesta pendiente de una automatización borrada se niega (sin permiso) y la propuesta sigue en la bandeja hasta que se rechaza o caduca. Si era una receta de fábrica, volver a encenderla desde su módulo crea otra.
Si falla: una automatización que ya no existe da «no encontrada».
Implicados: FLOWS-F09
QA: qa-hub-flows R10

### HUB-F89 Paso «Hacer algo»: ejecutar la acción de un módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al llegar al paso, el hub comprueba en ese momento que la automatización tiene permiso para esa acción (y, si el permiso tiene límites, que los datos los cumplen).
2. Ejecuta la acción del módulo como lo haría una persona, con las mismas comprobaciones del módulo y las fiscales, pero en nombre de la automatización.
3. Lo que la acción hace, la marca del paso y el avance de la ejecución se guardan juntos.
Entra: el nombre de la acción y sus datos, ya rellenados con lo que trae el aviso y lo que dieron los pasos anteriores.
Sale: los efectos de la acción, sus avisos (marcados con la ejecución que los emitió) y la salida del paso, que leen los pasos siguientes.
Si falla: sin permiso, `flow.grant_denied` y la ejecución se para; una acción interna se rechaza igual que para alguien de fuera; el error del módulo se guarda tal cual en el paso. Si el hub se reinicia justo después de guardar la acción y antes de apuntar su salida, la ejecución se para (`flow.step_output_lost`) en vez de seguir con un dato vacío.
Implicados: FLOWS-F14
QA: qa-hub-flows R1, qa-hub-flows R3

### HUB-F90 Paso «Consultar algo»: leer datos de un módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub comprueba el permiso de esa consulta en ese momento.
2. Hace la consulta con los datos indicados y guarda lo pedido: la primera fila campo a campo, solo cuántas hay, o una lista de opciones para ofrecer en un mensaje.
3. Si no encuentra nada, la ejecución sigue (para pararla se pone después un «Solo sigue si»).
Entra: la consulta, sus datos, qué guardar y el máximo de filas (1 a 200; 10 para opciones).
Sale: la salida del paso con lo encontrado y el total real.
Si falla: sin permiso, `flow.grant_denied`; un máximo fuera de rango no se guarda (`flow.limit_out_of_range`); una opción mal formada, `flow.query_bad_option`.
Implicados: FLOWS-F14
QA: qa-hub-flows R1

### HUB-F91 Paso «Solo sigue si»
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub compara los datos (del aviso o de pasos anteriores) con las condiciones del paso: igual, distinto, uno de, presente, contiene, mayor o menor que, dentro de los últimos…
2. Si se cumplen todas, sigue. Si no, la ejecución **termina bien** ahí: es la automatización funcionando, no un fallo.
Entra: las condiciones del paso.
Sale: el paso «parado» y la ejecución terminada sin error.
Si falla: un operador que el hub no conoce no se guarda.
Implicados: FLOWS-F14
QA: qa-hub-flows R1, BD-10

### HUB-F92 Paso «Esperar»
Estado: parcial — si el hub muere justo después de apuntar la espera y antes de guardarla, al volver (a los 5 minutos, cuando caduca su reserva) la ejecución sigue en el paso siguiente sin esperar (leído, sin ejecutar)
Actor: sistema
Pantalla: ninguna
Pasos:
1. La ejecución se duerme el tiempo indicado, o hasta una fecha que trae el aviso (con un adelanto o retraso), como mucho 90 días.
2. Mientras duerme, puede despertarla otro aviso: uno que la **cancela** (la cita se anuló) o uno que la **reprograma** (la cita se movió), si se refiere a lo mismo (por ejemplo, la misma cita), como mucho 20 reprogramaciones.
3. Al vencer, sigue con el paso siguiente. Si la fecha ya había pasado, según se haya dicho: termina, sigue al momento o falla.
Entra: segundos o la ruta de una fecha, el adelanto, el máximo, qué hacer si ya pasó, y hasta 5 avisos que cancelan o reprograman, con hasta 3 datos para casarlos.
Sale: la ejecución dormida con su hora de despertar y sus esperas armadas (`_flow_run_waits`).
Si falla: una espera fija de más de 90 días, o demasiados avisos o reprogramaciones, no se guardan (`flow.delay_horizon`, `flow.max_reschedules`). Una espera hasta una fecha que cae a más de 90 días para la ejecución en ese paso con `flow.delay_horizon`, también al reprogramarse. Si se pausa la automatización, la ejecución se cancela al despertar.
Implicados: FLOWS-F14
QA: qa-hub-flows R3

### HUB-F93 Paso «Enviar un mensaje» a un cliente
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub saca el destinatario de una consulta del negocio (nunca de una dirección escrita a mano) y comprueba que sale **exactamente uno**.
2. Comprueba que la automatización tiene sus dos permisos: el canal (correo o WhatsApp) y de qué consulta y campo sale el destinatario.
3. Deja el mensaje en la cola de salida, junto con el paso: que salga de verdad lo hace la cola (HUB-F61), que vuelve a leer los permisos al enviarlo.
4. El historial dice «Mensaje en cola para mandarse» y oculta el teléfono o el correo.
Entra: el canal, la consulta y el campo del destinatario, la plantilla de WhatsApp o el asunto del correo, el texto con datos insertados y, si hace falta, la cabecera y los botones.
Sale: un aviso de mensaje pendiente (`flow.reminder.due`) con el destinatario (solo ahí) y el paso hecho en el historial. El historial oculta la dirección, no el resto: guarda el texto del mensaje con los datos insertados y los datos de la consulta del destinatario.
Si falla: ninguno o más de un destinatario, o uno con mala forma, para la ejecución (`recipient_not_found`, `recipient_ambiguous`, `recipient_invalid`); un texto que sale de un paso que no lo publicó, `flow.text_not_found`; una lista de opciones que no está, `flow.options_not_found`; una lista de opciones vacía termina la ejecución **bien, sin mandar nada**. El SMS no se guarda. Sin permiso, `flow.grant_denied`. Retirar el permiso con el mensaje en cola lo cierra para siempre (HUB-F53).
Implicados: FLOWS-F15
QA: qa-hub-flows R7

### HUB-F94 Paso «Llamar a otro sistema»
Estado: parcial — un servicio que pide la clave de no repetición en el cuerpo o con otro nombre de cabecera (Square, PayPal) aún no la recibe, y puede crear dos veces lo mismo si el hub se reinicia durante la llamada (hub#2675)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub comprueba que la dirección encaja con un permiso de la automatización (un patrón de dirección).
2. Pone los secretos en su sitio (HUB-F99) y llama, fuera del bucle principal: una llamada lenta no frena la caja ni las demás automatizaciones.
3. Antes de conectar, comprueba que la dirección no apunta dentro del negocio ni de la nube (redes privadas, el propio equipo, direcciones de metadatos, IPv6 internas o disfrazadas): lo resuelve una vez y conecta solo a lo comprobado.
4. Guarda la respuesta (código, y el cuerpo como datos o como texto) para los pasos siguientes.
Entra: método (GET, POST, PUT, PATCH, DELETE), dirección, cabeceras, cuerpo y tiempo de espera (1 a 30 s, 10 de fábrica).
Sale: la salida del paso con el código y el cuerpo, cortado a 1 MiB con la marca de cortado; los secretos sustituidos por asteriscos en lo guardado.
Si falla: sin permiso, ninguna llamada sale. Una dirección con usuario y contraseña, interna o que resuelve a una interna se bloquea (`flow.http_blocked`); una dirección rellenada que no es una URL, `flow.http_url_invalid`; no se siguen redirecciones; una respuesta que no es 2xx (`flow.http_status`), un fallo de conexión o de TLS (`flow.http_failed`) o que tarda más del plazo (`flow.http_timeout`) para la ejecución salvo «seguir si falla». La llamada sale **al menos una vez**: si el hub se reinicia durante la llamada, se repite a los 5 minutos, y por eso cada intento lleva la misma cabecera `Idempotency-Key` (una por ejecución y paso, distinta en cada ejecución, y guardada en el historial), con la que el otro sistema reconoce la repetición y no crea el pedido o el cobro dos veces (hub#2659); si el autor escribe su propia `Idempotency-Key`, manda la suya. Un servicio que pide la clave en otro sitio (en el cuerpo, o con otro nombre de cabecera) aún no tiene cómo recibirla (hub#2675). El tapado de secretos en la respuesta es por coincidencia exacta: si el otro sistema lo devuelve codificado (base64, URL), no se tapa.
Implicados: FLOWS-F16
QA: qa-hub-flows R5, qa-hub-flows R9

### HUB-F95 Paso «Pedírselo al asistente»
Estado: parcial — el encargo solo puede insertar datos de pasos terminados bien (uno saltado o que falló con «seguir» sale vacío) y no la hora (el asistente sí la recibe en sus instrucciones, en UTC) (leído, sin ejecutar); no hay tope de gasto propio, solo el número de vueltas
Actor: sistema, asistente
Pantalla: ninguna
Pasos:
1. El hub manda al asistente el encargo del paso, con los datos insertados, y le ofrece solo las consultas y acciones que la automatización tiene concedidas y el paso declara.
2. El asistente consulta y propone. Con «Que me lo pregunte» (de fábrica), lo que quiera cambiar queda en la bandeja esperando a un administrador (HUB-F100) y la ejecución espera, salvo una orden que solo responde (de solo lectura), que se ejecuta sin pasar por la bandeja; con «Que lo haga por su cuenta», lo ejecuta.
3. Como mucho las vueltas indicadas (de 1 a 10; 6 de fábrica). Ante un fallo pasajero del proveedor hace 3 intentos en total (con pausas de 1 y 3 segundos), nunca repitiendo una acción; es un mecanismo propio, no la escalera de los avisos.
4. Guarda lo que contestó y las herramientas que usó.
Entra: el encargo, las herramientas permitidas, la política, las vueltas y, si se pide, los datos que tiene que devolver.
Sale: la salida del paso (`text`, las llamadas a herramientas y los datos pedidos) y, con «Que me lo pregunte», una propuesta en la bandeja que caduca a las 72 horas.
En este mismo documento se apoya en: HUB-F273 (Conversar con el asistente), HUB-F277 (Ver el plan del asistente y lo que queda del mes), HUB-F279 (Pedirle un paso al asistente dentro de una automatización).
Si falla: un secreto en el encargo o más de 10 vueltas no se guardan. Sin enlace con ERPlora, `flow.agent_no_cloud_credential`. Se para con `agent_max_iters`, `agent_timeout` (60 s el paso, 45 s cada turno), `agent_upstream`, `agent_no_output` o `agent_bad_output`, salvo «seguir si falla».
Implicados: FLOWS-F17, WHATSAPP_INBOX-F20
QA: qa-hub-flows R6, L-12

### HUB-F96 Paso «Preguntar antes a alguien»
Estado: parcial — el rol al que se pregunta no restringe nada en la práctica: solo un administrador puede ver la bandeja, y un administrador siempre puede contestar
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al llegar al paso, el hub deja la pregunta (con su texto y detalles ya rellenados) en la bandeja y la ejecución se para ahí.
2. Espera la respuesta hasta el plazo (de 1 segundo a 30 días; 72 horas de fábrica).
3. Con un sí, sigue. Con un no: para la ejecución o sigue, según se dijo. Sin respuesta en plazo: o se cancela la ejecución (de fábrica, también con «contarlo como un no») o sigue con la respuesta «caducada», según el plazo diga; no se aplica lo que se dijo para un no.
4. La respuesta (sí, no o caducada, quién y la nota) queda como dato para un «Solo sigue si» posterior.
Entra: título, detalles, rol, plazo, qué hacer con un no y con el silencio.
Sale: una pregunta pendiente (`_flow_approvals`, tipo decisión), la ejecución esperando y un aviso efímero por el canal en vivo (`flow.approval.created`, con el título y el resumen ya rellenados, que pueden llevar datos del cliente y que recibe toda pantalla del hub, HUB-F60). Este paso no pide permiso.
Si falla: un plazo fuera de rango o una pregunta vacía no se guardan.
Implicados: FLOWS-F18
QA: qa-hub-flows R6, BD-10

### HUB-F97 «Solo si» y «seguir si falla» en cada paso
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cualquier paso (menos «Solo sigue si») puede llevar una condición «solo si»: si no se cumple, el paso no se hace, queda como saltado y la ejecución sigue.
2. Cualquier paso puede decir «si falla, sigue»: el fallo queda escrito en el paso, la ejecución continúa y los pasos siguientes pueden mirar si falló.
3. Sin decir nada, un paso que falla para la ejecución.
Entra: `run_if` (condiciones como las de HUB-F91) y `on_error` (`stop` o `continue`) de cada paso.
Sale: el paso saltado no aparece en el historial (los pasos siguientes lo ven como `steps.<id>.skipped`); el fallido queda con su error; la ejecución sigue. No hay reintento de un paso.
Si falla: un valor de `on_error` que no es ninguno de los dos no se guarda.
Implicados: FLOWS-F14, WHATSAPP_INBOX-F20
QA: qa-hub-flows R8

### HUB-F98 Conceder, limitar y retirar los permisos de una automatización
Estado: parcial — guardar la lista no es todo-o-nada al escribir: dos permisos iguales en la lista chocan después de haber retirado y concedido una parte; y un límite ilegible sobrevive a volver a conceder el mismo permiso sin límite (leído, sin ejecutar)
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. La pantalla manda la **lista entera** de permisos que debe tener la automatización: acciones, consultas, canales de mensaje, de dónde sale el destinatario y direcciones externas.
2. El hub comprueba toda la lista antes de tocar nada: que cada acción y consulta existe, que no es interna, que cada patrón de dirección, canal y destinatario está bien escrito, y que cada límite tiene sentido.
3. Retira lo que ya no está y concede lo nuevo. Un permiso puede llevar límites: ciertos datos tienen que ser un valor fijo o lo que averiguó la propia automatización.
4. Desde ese momento, cada paso comprueba su permiso al ejecutarse, también los que ya estaban en marcha. Quién concedió no importa: no se comprueba qué puede hacer quien concede, y la automatización sigue actuando aunque su creador deje de ser administrador o se desactive (ADR-0283 D2).
Entra: la lista de permisos (`command`, `query`, `notify`, `http`, `recipient_query`, con su límite si lo tiene) y la sesión del administrador.
Sale: los permisos vivos de la automatización, con quién los concedió o retiró y cuándo. La lectura marca un permiso cuyo límite no se puede leer (`payload_unreadable`); ese permiso no autoriza nada.
Si falla: una acción o consulta que no existe, «no encontrada»; una interna, rechazo; un patrón, canal o destinatario mal escrito, o un límite con un secreto, rechazo con su código. En todos esos casos no cambia nada. Con un límite incumplido, el paso se para con `flow.grant_payload_denied`.
Implicados: FLOWS-F19, FLOWS-F15, FLOWS-F16
QA: qa-hub-flows R3, BD-10

### HUB-F99 Guardar secretos que no se pueden volver a leer
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. Se guarda un secreto con su nombre (en mayúsculas, hasta 64 caracteres) y su valor.
2. El hub lo cifra y solo vuelve a enseñar el nombre: no hay pantalla ni puerta que devuelva el valor. Pero quien puede crear automatizaciones puede enviarlo con un paso «Llamar a otro sistema» a una dirección que él mismo conceda.
3. Un paso «Llamar a otro sistema» lo usa en la dirección, las cabeceras o el cuerpo; en el historial sale como asteriscos, y si el otro sistema lo devuelve en su respuesta o en su error, también se tapa.
4. Borrar un secreto lo vacía; los pasos que lo usaban fallarán.
Entra: nombre y valor; la sesión del administrador.
Sale: el secreto cifrado (`_flow_secrets`), compartido por todas las automatizaciones del negocio, con quién lo cambió.
Si falla: sin la llave de cifrado del hub, «no se pueden guardar secretos» (`flow.secrets_key_missing`). Un valor vacío se rechaza con un código que habla del nombre (`flow.invalid_secret_name`). Un paso que usa un secreto borrado falla con `flow.secret_not_found`. Usar un secreto fuera de «Llamar a otro sistema» no se guarda.
Implicados: FLOWS-F16
QA: qa-hub-flows R5

### HUB-F100 Decidir una pregunta o una propuesta que espera
Estado: parcial — aprobar ejecuta aunque la automatización esté en pausa (hub#2650)
Actor: administrador
Pantalla: FLOWS: Automatizaciones
Pasos:
1. La bandeja lista lo que espera respuesta (hasta 100), con lo que se preguntó ya rellenado.
2. Un administrador aprueba o rechaza, con una nota si quiere.
3. Si es una propuesta del asistente y se aprueba, el hub vuelve a comprobar en ese momento el permiso y los datos, y ejecuta **exactamente** lo propuesto, sin volver a preguntar al asistente. La acción y el «aprobada» se guardan juntos: o quedan las dos cosas o ninguna.
4. Si es una pregunta, no ejecuta nada: la ejecución sigue con la respuesta como dato.
5. Un no hace lo que el paso dijo (parar o seguir).
Entra: la pregunta o propuesta, la decisión, la nota y la sesión (de ahí sale quién decidió, nunca del cuerpo).
Sale: la decisión guardada con quién, cuándo y la nota; la ejecución sigue, se cancela o, si la acción aprobada falla, queda fallida con el error. Al llegar y al caducar una propuesta sale un aviso efímero por el canal en vivo (`flow.approval.created` / `flow.approval.expired`) que refresca la bandeja.
Si falla: ya decidida, «alguien ya contestó» (`flow.approval_already_decided`); caducada, `flow.approval_expired`; de otro rol y sin ser administrador, `flow.approval_not_yours`. Si al aprobar falta el permiso, la propuesta sigue pendiente. Si dos personas deciden a la vez (o una aprueba justo cuando el repaso de HUB-F101 la cierra), gana una sola: la acción se ejecuta como mucho una vez, y la otra recibe «alguien ya contestó» o «caducada» sin que se haya hecho nada por ella.
Implicados: FLOWS-F24
QA: qa-hub-flows R6

### HUB-F101 Cerrar lo que nadie contestó a tiempo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada hora el hub repasa las preguntas y propuestas cuyo plazo ha vencido.
2. Las cierra como caducadas y hace lo que dice cada una: contar como un no, parar o seguir. Una propuesta del asistente caduca a las 72 horas y no se ejecuta.
Entra: las preguntas y propuestas pendientes con su plazo.
Sale: la pregunta caducada (quién la cerró: el propio hub) y su ejecución terminada o reanudada; una vez terminada, entra en la poda de 90 días.
Si falla: si el repaso falla, se apunta en el registro del servidor y se intenta a la hora siguiente. Hasta que pasa el repaso, la pregunta vencida sigue en la bandeja pero ya no se puede contestar. Si una aprobación estaba ejecutando su acción cuando el repaso cierra la propuesta, esa acción se deshace entera y no queda nada hecho.
Implicados: FLOWS-F18, FLOWS-F24
QA: qa-hub-flows R6

### HUB-F102 Guardar el historial de ejecuciones
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. Cada ejecución queda guardada con su estado (pendiente, en marcha, esperando, esperando respuesta, terminada, fallida, cancelada), cuándo empezó y terminó, y su último error.
2. Cada paso hecho guarda lo que entró, lo que salió y su error, con los secretos y la dirección del destinatario de los mensajes ocultos; un paso saltado por su «solo si» no deja fila.
3. La pantalla pide las ejecuciones de una automatización de 50 en 50 (hasta 200) de la más nueva a la más antigua, y el detalle de una con sus pasos y los avisos que emitió.
4. A los 90 días de terminar, la ejecución y sus pasos, preguntas y esperas se borran; las que siguen vivas no se borran nunca.
Entra: la automatización o la ejecución, y la sesión del administrador.
Sale: nada guardado al leer.
En este mismo documento se apoya en: HUB-F249 (Vaciar el historial del hub que nombra a la persona), HUB-F253 (Purgar el historial por retención).
Si falla: una ejecución de otro hub o ya podada da «no encontrada». Lo que devuelven las consultas y el asistente se guarda legible, también datos de clientes, hasta la poda o el borrado de ese cliente.
Implicados: FLOWS-F23
QA: qa-hub-flows R1, qa-hub-flows R8, BD-10

### HUB-F103 Reanudar una ejecución desde el paso que falló
Estado: no hecho — no existe ninguna forma de reintentar ni reanudar una ejecución fallida (hub#952): hay que arreglar la causa y esperar al siguiente disparo o lanzarla de nuevo entera
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. En una ejecución que se paró por un error, tras arreglar la causa, se pide reanudarla.
2. El hub la retoma en el paso que falló, sin repetir los pasos que ya hicieron efecto.
Entra: la ejecución fallida.
Sale: la ejecución en marcha desde el paso fallido.
Si falla: sin construir.
Implicados: FLOWS-F23
QA: qa-hub-flows R8

### HUB-F104 Servir las recetas de fábrica de los módulos
Estado: hecho
Actor: sistema
Pantalla: FLOWS: Automatizaciones
Pasos:
1. Un módulo trae sus automatizaciones de fábrica en su carpeta de recetas (hoy, la Bandeja de WhatsApp trae tres: cita por WhatsApp, aviso de cita confirmada y mesa por WhatsApp).
2. Al instalarlo o arrancar el hub, el hub las lee y aparta las que no puede ofrecer, con su motivo: le falta un idioma, el documento no se lee, no trae permisos, o falta, está en pausa o es vieja una aplicación que la receta necesita.
3. Cuando una pantalla las pide, devuelve las de los módulos activos: su texto en todos los idiomas, los permisos que pedirán (con sus límites), lo que necesitan y, si ya se encendió, cuál es, si está encendida y si hay una versión más nueva; y la lista de las apartadas con su motivo.
Entra: las carpetas de recetas de los módulos instalados y la sesión de un administrador. No pide «Administrar automatizaciones»: un módulo sin ese permiso recibe solo las suyas.
Sale: las recetas ofrecidas y las descartadas (`discarded[]`, con el módulo que falta y la versión pedida).
Si falla: un módulo en pausa no ofrece las suyas. Los permisos que se enseñan son una petición, no una concesión.
Implicados: FLOWS-F05, WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F18
QA: qa-hub-flows R7

### HUB-F105 Encender una receta de fábrica con exactamente sus permisos
Estado: parcial — conceder los permisos no es todo-o-nada: un fallo de base de datos a mitad deja permisos a medias, y la siguiente activación la enciende así; y dos activaciones a la vez pueden crear dos automatizaciones (leído, sin ejecutar)
Actor: administrador
Pantalla: WHATSAPP_INBOX: Ajustes
Pasos:
1. Desde la pantalla del módulo que la trae (por ejemplo, «Reservar citas» en la Bandeja de WhatsApp), el administrador la activa.
2. La primera vez, el hub la crea en el idioma del hub, en pausa; le concede **exactamente** los permisos que declara la receta, con sus límites; y solo entonces la enciende.
3. Si ya existía, solo la enciende, conservando lo que el dueño cambió o retiró; solo si no le queda ningún permiso vuelve a darle los de la receta.
4. Pulsar dos veces es una sola automatización.
Entra: el módulo y la receta, y la sesión del administrador. Un módulo solo puede encender las suyas.
Sale: la automatización encendida, marcada con la receta de la que sale y su huella (para saber después si hay versión nueva); nueva o reutilizada.
Si falla: si falla antes de conceder, queda en pausa y sin permisos, y la siguiente activación la reutiliza y le da los de la receta. Si falla a mitad de conceder, queda en pausa con parte de los permisos, y la siguiente activación la **enciende con esos**: el hub no garantiza deshacer lo que llegó a encender. Una receta apartada se niega con su motivo; una que no existe, «no encontrada»; otro módulo, `flow.template_not_yours`.
Implicados: WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15, REC_WA_CITA-F01, REC_WA_MESA-F01
QA: WR-01, WA-01

### HUB-F106 Apagar una receta de fábrica sin borrarla
Estado: hecho
Actor: administrador
Pantalla: WHATSAPP_INBOX: Ajustes
Pasos:
1. Desde la pantalla del módulo, el administrador la apaga.
2. El hub la pone en pausa con su propio documento: no la borra, no le quita permisos y no toca su historial.
3. Se ve en Automatizaciones como «En pausa»; pausarla desde allí es lo mismo.
Entra: el módulo y la receta, y la sesión del administrador.
Sale: la automatización en pausa, con sus efectos de HUB-F87.
Si falla: una receta que nunca se encendió (o se borró) da «no encontrada»; otro módulo, `flow.template_not_yours`.
Implicados: WHATSAPP_INBOX-F17, REC_WA_CITA-F01, REC_WA_MESA-F01
QA: ninguno

### HUB-F107 Restaurar una receta a la versión actual de su módulo
Estado: parcial — mientras se restaura una receta encendida, queda en pausa un instante, y una ejecución que el motor tome justo entonces se cancela (leído, sin ejecutar)
Actor: administrador
Pantalla: WHATSAPP_INBOX: Ajustes
Pasos:
1. El hub avisa de que el módulo trae una versión distinta de la que se encendió (o el dueño quiere deshacer sus retoques).
2. El administrador la restaura desde la pantalla del módulo o desde Automatizaciones.
3. El hub sustituye el nombre, el documento y los permisos por los de la receta actual, guarda la huella nueva, y la deja encendida o en pausa como estaba.
Entra: el módulo y la receta, y la sesión del administrador; puede pedirlo el propio módulo o el que tiene «Administrar automatizaciones».
Sale: la misma automatización (mismo historial), con la receta de hoy.
Si falla: una receta que nunca se encendió, «no encontrada»; otro módulo sin «Administrar automatizaciones», `flow.template_not_yours`; una receta apartada, su motivo.
Implicados: FLOWS-F06, WHATSAPP_INBOX-F18, REC_WA_CITA-F01, REC_WA_MESA-F01
QA: ninguno

### HUB-F108 Ofrecer el catálogo de avisos del negocio
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. Al elegir «Pasa algo», el editor pide al hub qué avisos existen en este negocio.
2. El hub junta los que declaran los módulos instalados y los que ha visto pasar de verdad (lo que queda en su historial: los entregados de los últimos 90 días y los pendientes o caídos de cualquier antigüedad), con quién los declara y cuándo se vio el último.
Entra: la sesión del administrador (y «Administrar automatizaciones» si lo pide un módulo).
Sale: la lista de nombres, sin contenido.
Si falla: el mismo rechazo de sesión de todo el motor.
Implicados: FLOWS-F04, FLOWS-F13
QA: qa-hub-flows R0

### HUB-F109 Enseñar ejemplos reales de un aviso con los datos de personas ocultos
Estado: parcial — el texto que escribe un cliente en un WhatsApp entrante sale como ejemplo (hasta 64 caracteres): su clave `text` no está entre las de texto libre y el aviso no cuenta como «de una persona»; y un teléfono de 9 dígitos sin prefijo bajo una clave neutra no se detecta (leído, sin ejecutar)
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. El editor pide qué datos trae un aviso («Total de la venta — 42,50 €»).
2. El hub mira los últimos avisos de ese nombre en este negocio (5, hasta 20) y devuelve cada dato con su tipo, en cuántos aparece y un ejemplo.
3. El ejemplo se oculta, pero el dato se lista, cuando puede ser de una persona: por el nombre del dato (correo, teléfono, dirección, NIF, IBAN, tarjeta…), por estar dentro de un cliente o un empleado, porque el aviso es de una persona y el dato es su nombre o su ciudad, porque es texto libre (notas, comentarios, `message`, `body`; **no** `text`: el texto de un WhatsApp entrante se enseña) o porque el valor parece un correo, un IBAN, una tarjeta o un teléfono con prefijo.
4. Las listas se dan como un dato con su longitud, sin entrar.
Entra: el nombre del aviso y cuántas muestras.
Sale: la forma del aviso (hasta 200 datos, 6 niveles, ejemplos de 64 caracteres), nunca los avisos enteros.
Si falla: un aviso que nadie declara y nunca se vio, «no encontrado»; uno declarado sin ejemplos vivos se contesta con 0 muestras.
Implicados: FLOWS-F14, FLOWS-F20, FLOWS-F13
QA: qa-hub-flows R0, qa-hub-flows R1

### HUB-F110 Frenar una automatización que se dispara en bucle
Estado: parcial — lo que se descarta por el límite solo queda en el registro del servidor: ni el historial ni la campana dicen que una automatización se frenó; y las ejecuciones a mano no tienen límite, aunque cuentan para el de los disparos por aviso y por horario
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una automatización cuya acción provoca el mismo aviso que la arranca entraría en bucle.
2. El hub corta por dos lados: un aviso que viene de 16 reacciones en cadena ya no arranca nada, y una automatización no arranca más de 30 veces por minuto por avisos u horarios.
3. Lo que pasa del límite se descarta; el resto del hub sigue vendiendo.
Entra: la profundidad del aviso y las ejecuciones del último minuto.
Sale: nada nuevo; el aviso se da por entregado para esa automatización.
Si falla: no aplica.
Implicados: ninguno
QA: qa-hub-flows R8, qa-hub-flows R9

### HUB-F111 Decir qué versión de automatizaciones entiende el hub
Estado: hecho
Actor: sistema
Pantalla: FLOWS: Automatizaciones
Pasos:
1. Al abrir Automatizaciones, la pantalla pregunta al hub qué versión del documento entiende y qué versión del hub es.
2. Con eso decide si puede trabajar o enseña el aviso de versión (FLOWS-F01).
Entra: la sesión del administrador (y «Administrar automatizaciones» si lo pide un módulo).
Sale: la versión del documento (hoy 1), la del hub y el esquema completo, el mismo que el hub usa para juzgar.
Si falla: sin sesión de administrador o sin el permiso del módulo, el rechazo correspondiente, que la pantalla traduce en sus avisos de entrada.
Implicados: FLOWS-F01, FLOWS-F27, HUB_SHELL-F167
QA: qa-hub-flows R0, qa-hub-flows R3

### HUB-F112 Subir la foto, el vídeo o el PDF de la cabecera de un WhatsApp
Estado: hecho
Actor: administrador
Pantalla: FLOWS: Editor de automatización
Pasos:
1. En un paso «Enviar un mensaje» con una plantilla que lleva cabecera, se sube el archivo.
2. El hub mira el archivo por dentro (no por su nombre): tiene que ser JPEG o PNG, MP4 o PDF, del tipo que pide la cabecera (sin tipo, se toma «imagen») y como mucho 5, 16 o 100 MiB.
3. Lo guarda en el almacén de ERPlora del hub (no en su disco) con un nombre propio (su huella) y devuelve la referencia que guarda el paso.
4. En cada envío, el hub pide a ERPlora un enlace firmado a ese archivo para que WhatsApp lo descargue.
Entra: el tipo de cabecera y el archivo; la sesión del administrador.
Sale: el archivo en el almacén de ERPlora del hub y su referencia, tipo y tamaño. El mismo archivo subido dos veces lleva el mismo nombre (que sea un solo archivo depende de ERPlora, sin confirmar).
Si falla: un archivo de otro tipo, demasiado grande o un formulario mal hecho se rechazan; si el almacén falla, error. Si la firma del enlace falla al enviar, se reintenta 8 veces y acaba en «Eventos caídos»; si el archivo se borró, hoy ERPlora firma igual (saas#2393) y el fallo llega después, desde WhatsApp.
Implicados: FLOWS-F15
QA: qa-hub-flows R7

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Disparador por aviso, horario (hora del negocio), fecha, a mano | parcial: fecha con desplazamiento mal comparada; a mano solo API | HUB-F82…F85 |
| Validar el documento entero al guardar | hecho (acción inexistente se acepta) | HUB-F80, HUB-F86 |
| Acción, consulta, condición, espera, mensaje, llamada, asistente, pregunta | hecho / parcial por paso | HUB-F89…F96 |
| «Solo si» y «seguir si falla» por paso | hecho; sin reintento por paso | HUB-F97 |
| Permisos por automatización con límites | parcial (escritura no todo-o-nada) | HUB-F98 |
| Secretos de solo escritura y protección de llamadas salientes | hecho | HUB-F94, HUB-F99 |
| Aprobación con plazo y qué pasa con el no y el silencio | parcial: el rol no restringe; aprobar ejecuta con la automatización en pausa (hub#2650) | HUB-F96, HUB-F100, HUB-F101 |
| Historial paginado con retención | hecho (90 días) | HUB-F102 |
| Reanudar desde el paso que falló (Make, Power Automate) | no hecho (hub#952) | HUB-F103 |
| Recetas de fábrica: servir, encender, apagar, restaurar | parcial: encender no es todo-o-nada; restaurar con hueco de pausa | HUB-F104…F107 |
| Catálogo de avisos y ejemplos reales sin datos de personas | parcial: el texto de un WhatsApp entrante sale como ejemplo | HUB-F108, HUB-F109 |
| Protección contra bucles sin parar la caja | parcial: lo descartado no se ve | HUB-F110 |
| Modo prueba en el servidor | no existe a propósito: lo hace la pantalla (FLOWS-F20) | — |

## Datos: de quién es cada dato

Tablas de sistema del motor, todas con `hub_id`. El inventario de datos personales de avisos y
automatizaciones, y lo que alcanza el borrado de un cliente, están en [avisos.md](avisos.md).

| Tabla | Qué guarda | Cuánto vive |
|---|---|---|
| `_flow` | automatización: nombre, documento (con los destinatarios, textos y direcciones que escribe el dueño), encendida, receta y huella; `created_by`, `updated_by`, `deleted_by` | para siempre (borrado lógico) |
| `_flow_grants` | permisos con su límite; `granted_by`, `revoked_by` | para siempre (borrado lógico) |
| `_flow_triggers` | disparadores, filtro, mapeo, horario, próxima/última vez | para siempre (borrado lógico) |
| `_flow_runs` | ejecución: `input` (los datos del aviso), `vars` (memoria), último error, `created_by` | terminadas: 90 días; vivas: sin límite |
| `_flow_run_steps` | por paso: entrada, salida, error | con su ejecución |
| `_flow_approvals` | pregunta o propuesta: texto, resumen, **payload verbatim**, motivo, rol, decisión, `decided_by`, nota | con su ejecución (90 días desde que termina; el recibo de 4 años es `_elevation_audit`, que no guarda el contenido) |
| `_flow_run_waits` | esperas armadas con el dato de correlación (`correlate_value`, p. ej. el id de una cita) | con su ejecución |
| `_flow_secrets` | secretos cifrados (AES-256-GCM), credenciales de terceros; `created_by`, `updated_by`, `deleted_by` | para siempre; al borrar se vacía el valor |
| `media/whatsapp/headers/` | archivos de cabecera subidos (HUB-F112) | sin poda |

## Reglas que no se rompen

- **Una automatización actúa con sus propios permisos**, releídos en cada paso; nace sin ninguno; una
  receta de fábrica nace con exactamente los de su receta y nunca queda encendida a medias.
- **Ninguna pantalla ni puerta devuelve un secreto**, y no aparece en el historial. No es secreto
  frente a quien crea automatizaciones: puede enviarlo con un paso «Llamar a otro sistema» a una
  dirección que conceda.
- **Una llamada saliente no llega a la red interna** (comprobación en la propia resolución de nombres).

## Lo que NO hace, a propósito

- No reintenta pasos de automatización ni tiene modo de prueba en el servidor (la prueba es de la
  pantalla).
- No bifurca: una automatización es una columna (ADR-0461).

## Dudas abiertas

1. ¿Debe pausar una automatización cancelar también sus preguntas pendientes y sus mensajes en cola?
2. ¿Debe volver a encenderse una automatización sin disparar lo que venció durante la pausa?
3. ¿Quién debe poder contestar una pregunta dirigida a un rol (hoy solo administradores)?
4. ¿Debe haber límite de ejecuciones a mano por minuto?

## Fuentes contrastadas

- `architecture/hub/flows.md` §8: «un run termina con la definición con la que nació (snapshot)»; el
  código relee el documento en cada paso por número de paso (HUB-F86).
- `architecture/hub/flows.md` §7.2 / `boot.rs`: el TTL de 72 h es de las propuestas del asistente; una
  pregunta tiene su propio plazo (1 s…30 d, 72 h de fábrica) (HUB-F96).
- `WORKFLOW.md` de `flows` (FLOWS-F12, FLOWS-F14): «el hub rechaza al guardar una acción que no existe»;
  el hub acepta una acción desconocida (solo rechaza las internas); sí rechaza una consulta desconocida
  (HUB-F80).
- `WORKFLOW.md` de `flows` (FLOWS-F09, «Reglas»): «lo que esperaba una respuesta se cancela cuando
  alguien contesta o caduca» — cierto para rechazar o caducar; aprobar una propuesta de una
  automatización pausada ejecuta la acción antes de cancelar la ejecución, y aprobar una de una
  automatización borrada se niega (sin permiso) y la deja pendiente (HUB-F87, HUB-F88, HUB-F100).
- `WORKFLOW.md` de `flows` (FLOWS-F03, «Reglas»): «pausar hace que lo que estaba en marcha se cancele
  en su siguiente paso»; una espera dormida solo se cancela al despertar, y los mensajes en cola salen
  igual (HUB-F87).
- `WORKFLOW.md` de `whatsapp_inbox` (WHATSAPP_INBOX-F14): «quedan… con exactamente los permisos que
  declaran»; cierto la primera vez; al volver a activar se conservan los del dueño (HUB-F105).
- Los rechazos del motor que la pantalla pinta tal cual están en inglés (HUB-F80).
- Guion `qa-hub-flows` R2: prueba «Ejecutar» por la UI; solo existe por la API (HUB-F85).
