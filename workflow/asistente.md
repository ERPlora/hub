# WORKFLOW — Hub (servidor) · Asistente

Prefijo: HUB

> Área «WhatsApp y asistente», segunda mitad. El asistente es una capacidad del núcleo, no un
> módulo (ADR-0033). El hub **nunca habla con un modelo de IA**: arma la conversación (qué
> herramientas se ofrecen, con qué instrucciones) y la reenvía al proxy del SaaS, que es quien
> llama al proveedor y mide el gasto. El bucle que ejecuta las herramientas corre en el navegador
> con la sesión de quien pregunta, salvo en una automatización, donde lo corre el servidor
> (HUB-F280). Escrito contra `origin/develop` del hub (05/10/2026). Código:
> `crates/server/src/{assistant,assistant_api,assistant_report,router,embed,agent_runner}.rs`,
> `crates/server/src/ingest.rs` (`collect_chunks`) y el crate `vector`.

## Flujos

### HUB-F273 Conversar con el asistente
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Asistente
Pasos:
1. La persona abre el asistente desde la barra superior y escribe (o adjunta, o dicta) lo que necesita.
2. El panel manda al hub la conversación de la sesión. El hub comprueba la sesión, prepara las herramientas que esa persona puede usar (HUB-F274) y escribe las instrucciones del turno: que es el asistente de ERPlora, la versión instalada, la fecha y hora del momento, los módulos activos con sus pantallas, qué registros no se editan sino que se corrigen (HUB-F276), que el dinero va en céntimos, que se lee antes de cambiar, que primero se responde desde el hub y que contesta en el idioma de quien escribe.
3. El hub reenvía todo al proxy del SaaS con la credencial del propio hub y le pasa al panel la respuesta según llega: el texto, cada herramienta que el modelo quiere usar (con lo que el catálogo sabe de ella) y el consumo del mes al cerrar el turno.
4. El panel ejecuta las herramientas con la sesión de la persona, pidiendo confirmación antes de cambiar nada (HUB_SHELL), y sigue la conversación.
Entra: los mensajes de la sesión (`messages`, con sus adjuntos); la sesión local, que da los permisos y el usuario que viaja como dato de gasto, nunca como permiso.
Sale: un flujo de eventos `token`, `function_call` (anotado con `kind`, `read_only`, `risk` y `money_fields`), `usage` y `done`. **El hub no guarda la conversación**: vive en el navegador durante la sesión (ADR-0149) y el SaaS no la conserva.
Si falla: sin sesión, `401`; una llave de API no entra por esta puerta; hub sin enrolar, `401` «hub sin credencial»; si el proxy no contesta o el flujo se corta a mitad, el panel recibe un evento de error con el código `cloud_unreachable` (nunca la dirección del servidor); si el SaaS rechaza el turno (cupo agotado, `quota_exceeded`; proveedor sin credencial) el evento de error viaja tal cual y el hub deja la causa en su registro, salvo el cupo agotado, que es el plan funcionando (hub#1738).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, panel del asistente (bucle de herramientas, tarjeta de confirmación, historial de sesión, recibos del turno)
Pendiente de enlazar: saas — asistente: `POST /api/v1/hub/device/assistant/chat/stream/` con `{input, messages, tools, instructions, user}` que inserta `instructions` como mensaje de sistema, ofrece las `tools` al modelo y devuelve SSE con `function_call` (argumentos completos, uno por llamada), `usage` al cerrar y `error` con `code` y `retriable`, terminado en `[DONE]`; mide un turno solo si se completa
QA: qa-hub-assistant §R0, qa-hub-assistant §R6

### HUB-F274 Ofrecer al asistente las consultas y órdenes de los módulos y del núcleo
Estado: hecho
Actor: asistente
Pantalla: HUB_SHELL: Asistente
Pasos:
1. En cada turno el hub repasa los módulos **activos** y toma cada consulta y cada orden que el módulo describe para el asistente.
2. Se queda solo con las que la persona tiene permiso de ejecutar; las órdenes internas de un módulo no se ofrecen nunca, aunque las describa.
3. Añade las del núcleo: qué falta por configurar, buscar en el marketplace y ver las plantillas de sector (cualquier sesión), y aplicar una plantilla de sector o instalar un módulo (solo quien administra). Nada destructivo del hub (desinstalar, reiniciar, borrar datos) se ofrece jamás.
4. Marca cada una: si solo contesta o puede cambiar algo, cuánto daño declara el módulo (corriente, destructiva, masiva) y qué campos son dinero.
5. El modelo elige; quien ejecuta es el panel, por la misma puerta y con el mismo permiso que el botón de la pantalla, revisado otra vez en el servidor.
Entra: el registro de módulos activos (el bloque `ai` de cada consulta u orden, su permiso y su esquema); los permisos de la sesión.
Sale: la lista de herramientas del turno, ordenada siempre igual. Así llega al asistente, por ejemplo, la orden de Automatizaciones que deja un borrador (FLOWS-F26): se ofrece solo a quien puede gestionar automatizaciones y la ejecuta el panel con su sesión.
Si falla: una operación sin descripción para el asistente no existe para él (la persona la hace en su pantalla); un `risk` que el núcleo no conoce se trata como destructivo; una orden que el módulo publica como orden pero solo contesta (comprobar un hueco libre) se marca como lectura solo si pide un permiso que el módulo también exige a sus consultas (hub#1594); ante la duda, cuenta como escritura y lleva tarjeta.
Implicados: FLOWS-F26
Pendiente de enlazar: hub — HUB_SHELL, panel del asistente (confirmación según el riesgo: un clic, escribir, o negarse a ejecutar desde el chat)
Pendiente de enlazar: hub — HUB, módulos y órdenes (la misma puerta de consultas y órdenes que usa la pantalla, con su permiso)
QA: qa-hub-assistant §R1, qa-hub-assistant §R3

### HUB-F275 Recortar las herramientas a los módulos que importan para la pregunta
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Con ocho o más módulos activos, el hub pide al SaaS la huella de la última pregunta de la persona.
2. La compara con el índice del hub (HUB-F276) y se queda con los módulos más cercanos (de los 24 trozos más parecidos).
3. Ofrece solo las herramientas de esos módulos, más las del núcleo, que se ofrecen siempre.
Entra: la última pregunta de la persona; el índice del hub.
Sale: un catálogo más corto, que abarata cada turno. No es una puerta de seguridad: el permiso sigue siendo el de HUB-F274.
Si falla: con menos de ocho módulos, sin índice, con el índice vacío, sin pregunta o si la huella no se puede pedir, se ofrecen **todas** las herramientas; el asistente nunca se queda sin contestar por esto. Un fallo deja una línea en el registro.
Implicados: ninguno
QA: qa-hub-assistant §R6

### HUB-F276 Anclar al asistente a lo que este hub tiene instalado
Estado: parcial — el asistente se ancla a la versión del hub, a los módulos activos y a la descripción que cada módulo instalado da de sí mismo, pero no lee la documentación (`docs/`) de los módulos: no hay índice de documentación, solo de descripciones para elegir herramientas (ADR-0282 lo dejó fuera)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al instalar o actualizar un módulo desde el hub, el hub toma la descripción que el módulo da para el asistente y la de cada consulta u orden, pide su huella al SaaS y la guarda en su índice con la versión del módulo.
2. Al desinstalarlo, borra sus entradas del índice.
3. Al arrancar, añade al índice los módulos activos que todavía no están (los instalados antes de que existiera el índice, o cuyo indexado falló), sin repetir los que ya están.
4. En cada turno, las instrucciones nombran la versión del hub (la misma que enseñan el menú lateral y el estado del sistema), los módulos activos con sus pantallas y, de cada registro que un módulo declara que no se edita, por qué y con qué orden se corrige.
Entra: los módulos instalados y activos; su descripción para el asistente; los registros inmutables que declaran (`records` con `mutable: false`, `reason`, `correct_with`).
Sale: el índice del hub (una fila por trozo, con módulo, versión e idioma inglés) y las instrucciones de cada turno. Las respuestas «¿qué versión tengo?», «¿qué módulos tengo?» o «¿cómo corrijo una factura?» salen de aquí, no de la memoria del modelo (hub#1044, ADR-0331).
Si falla: si la base de datos del hub no tiene la extensión de vectores, no hay índice y el asistente ofrece todas las herramientas (HUB-F275); el hub arranca igual. Un indexado que falla no deshace la instalación. Una actualización que entra al arrancar o desde otra instancia del hub no vuelve a indexar, y el arranque no reindexa un módulo que ya estaba: su entrada se queda con el texto de la versión anterior hasta la siguiente actualización desde el hub (hueco leído, sin ejecutar).
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes (instalar, actualizar y desinstalar un módulo, que disparan el indexado)
Pendiente de enlazar: saas — asistente: `POST /api/v1/hub/device/assistant/embeddings/` con `{texts}` → `{embeddings, model}`, un vector por texto y en el mismo orden, medido por hub
QA: qa-hub-assistant §R0

### HUB-F277 Ver el plan del asistente y lo que queda del mes
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Asistente
Pasos:
1. Al abrir el asistente, el panel pregunta al hub qué plan tiene el asistente de este negocio.
2. El hub exige una sesión, pregunta al SaaS con su credencial y devuelve la respuesta sin tocarla: nivel, mensajes usados del mes y lo que se puede contratar.
3. Tras cada turno, el consumo nuevo llega en el propio flujo de la conversación (HUB-F273), así que el contador no va un mensaje por detrás.
4. Para ampliar, quien administra pide al hub abrir el pago; el hub pide al SaaS la dirección del pago y la devuelve.
Entra: la sesión; para ampliar, una sesión de administrador.
Sale: el plan y el consumo para el panel; la dirección del pago en Stripe. El hub no lleva ningún contador del asistente: el nivel lo da el plan del hub (ADR-0474) y lo cuenta el SaaS.
Si falla: sin sesión, `401` (antes de hub#1254 cualquiera que alcanzara el hub podía preguntar o abrir pagos); ampliar sin ser administrador, `403`; un `402`/`429` del SaaS llega tal cual para que el panel diga que el cupo se agotó; SaaS caído, `424` con `cloud_unreachable`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, panel del asistente (plan, consumo y «ver planes»)
Pendiente de enlazar: saas — asistente: `GET /api/v1/hub/device/assistant/config/` (nivel, uso del mes, planes) y `POST …/assistant/subscription/checkout/` → `{checkout_url}`, con el nivel resuelto desde el plan del hub
QA: qa-hub-assistant §R4

### HUB-F278 Denunciar una respuesta del asistente
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Asistente
Pasos:
1. Bajo una respuesta terminada, la persona pulsa denunciarla y, si quiere, dice el motivo y un comentario.
2. El hub exige una sesión (cualquier perfil: quien se siente ofendido es quien está delante) y que vengan el identificador de la respuesta y su texto.
3. Lo deja en el registro único de errores del hub como algo a revisar, con quién lo denunció, y el registro lo manda al SaaS.
Entra: el identificador de la respuesta, su texto, y opcionalmente la pregunta que la provocó, el motivo y el comentario.
Sale: una entrada `assistant_content_report` en el registro de errores, que llega al SaaS para revisión. Los textos se recortan (respuesta y pregunta a 4.000 caracteres, comentario a 1.000, motivo a 100) para no guardar más de lo necesario; cada denuncia es distinta aunque el texto se repita.
Si falla: sin sesión, `401`; sin identificador o sin texto, rechazo con el campo que falta. El hub contesta `{ok: true}` en cuanto lo apunta; que llegue al SaaS es asunto del registro de errores, que lo reintenta.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, botón de denuncia bajo cada respuesta
Pendiente de enlazar: saas — registro de errores del hub (`POST /api/v1/hub/device/error-report/`) donde se revisan las denuncias de contenido
QA: qa-hub-assistant §R5

### HUB-F279 [retirado] Guardar el historial del asistente en el hub
Implicados: ninguno

### HUB-F280 Pedirle un paso al asistente dentro de una automatización
Estado: hecho
Actor: sistema, asistente
Pantalla: flows: Editor de automatización
Pasos:
1. Una automatización llega a un paso «Pedírselo al asistente». El servidor lo atiende fuera del ciclo que reparte los avisos, sin bloquear la caja mientras espera al modelo.
2. Le ofrece al modelo solo las herramientas que cumplen tres cosas a la vez: las puede usar la automatización con sus permisos, el paso las nombra y la automatización las tiene concedidas. Las del núcleo (instalar un módulo, configurar) no se ofrecen nunca aquí.
3. A las instrucciones de siempre añade que nadie está mirando: que no pregunte, que decida con las herramientas y, según el paso, que lo que cambie tiene efecto inmediato o que se queda esperando a una persona.
4. Las consultas, y las órdenes que solo contestan, se ejecutan en el acto. Una orden que cambia algo, con «Que me lo pregunte» (lo de fábrica), se comprueba contra su esquema y se deja en la bandeja de aprobaciones; el turno termina ahí. Con «Que lo haga por su cuenta», se ejecuta con los permisos de la automatización.
5. Si el paso pidió datos concretos (un texto, un número, una lista de opciones para tocar), el modelo tiene que entregarlos al final con una herramienta propia del paso, y el servidor comprueba su forma.
Entra: lo que el paso pide (`prompt`, herramientas, `policy`, vueltas como mucho, `output`); los permisos concedidos a la automatización.
Sale: la respuesta del paso (`text`, las herramientas usadas con su resultado y los datos pedidos) para los pasos siguientes; o la propuesta en la bandeja, con la tarea como motivo. Cada vuelta es una llamada al proxy del SaaS que gasta del cupo del asistente.
Si falla: el paso falla con el motivo escrito en el historial de la ejecución: sin credencial de máquina (`flow.agent_no_cloud_credential`), más de 60 s en total (`flow.agent_timeout`), más vueltas de las permitidas (`flow.agent_max_iters`), sin los datos pedidos o con otra forma (`flow.agent_no_output`, `flow.agent_bad_output`), o el proxy rechaza (`flow.agent_upstream`). Una llamada que falla por un momento (red, 5xx, 429) se repite dos veces con 1 s y 3 s de espera sin volver a ejecutar nada del negocio; el cupo agotado o una petición rechazada no se repiten. Una herramienta que el modelo no tenía, o que el permiso o el esquema rechazan, vuelve al modelo como error para que lo diga, sin tumbar el paso.
Implicados: FLOWS-F17
Pendiente de enlazar: hub — HUB, automatizaciones (ejecución del paso, bandeja de aprobaciones, caducidad y decisión de una propuesta)
Pendiente de enlazar: saas — asistente: el mismo `…/assistant/chat/stream/` de HUB-F273 llamado con la credencial de máquina, sin usuario, y `retriable: false` en los errores que no pasan esperando
QA: qa-hub-flows R6
