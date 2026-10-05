# WORKFLOW — Hub (servidor) · Avisos entre módulos

Prefijo: HUB

> Área «Avisos entre módulos» del servidor del hub (`crates/runtime`: `events`, `events_api`,
> `outbox`, `host_notify`, `scheduler`; `crates/server`: `event_stream`, `outbox_admin`,
> `notify_transport`, `activity`, y el bucle de fondo de `boot.rs`). Contrastado contra
> `origin/develop` del hub el 05/10/2026. Lo técnico vive en `architecture/hub/event-outbox.md`;
> aquí se escribe qué pasa y qué se garantiza.
>
> **Vocabulario.** Un **aviso** es lo que un módulo deja dicho cuando hace algo («se ha cobrado
> una venta»), para que otros módulos reaccionen («baja el stock», «emite la factura»). En el
> código y en las pantallas técnicas se llama *evento*. La **cola de salida** es la tabla donde el
> aviso espera hasta que todos los que lo escuchan lo han recibido; los **avisos caídos** son los
> que no se pudieron entregar y esperan a que una persona decida (pantalla «Eventos caídos»).

## Flujos

### HUB-F50 Dejar un aviso en la cola al guardar una orden
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien hace algo en un módulo (cobra una venta, anula un tique, envía una ronda a cocina) o lo hace una automatización o una tarea programada.
2. En el mismo momento en que se guarda lo que ha hecho, el hub apunta en la cola de salida cada aviso que esa orden declara.
3. Si lo guardado se deshace (la orden falla a mitad), el aviso tampoco existe: nunca hay un aviso de algo que no pasó, ni algo que pasó sin su aviso.
4. La orden contesta en cuanto se guarda; los módulos que escuchan el aviso reaccionan después, en segundo plano (HUB-F51), nunca dentro de la misma orden.
Entra: la orden de un módulo con los avisos que declara en su manifiesto (`emit`), y quién la pidió (persona, automatización o el propio hub).
Sale: una fila en la cola de salida (`_event_outbox`, estado pendiente) con el aviso, su contenido, el módulo que lo emite, la persona que lo causó, la automatización que lo emitió si la hay (`run_id`), el aviso que lo provocó si es una reacción en cadena (`parent_event_id`) y la pantalla que mandó la orden (`client_instance`). Si el manifiesto declara una clave de no repetición para ese aviso (`emit[].dedup_key`, por ejemplo el identificador del mensaje de WhatsApp), un segundo aviso con la misma clave en el mismo hub no se apunta. Si el módulo devuelve desde su código el mismo aviso que declara, se apunta una sola vez, la copia del código (hub#1786). También empuja el aviso a las pantallas en vivo (HUB-F60).
Si falla: si la orden falla, no queda ni el cambio ni el aviso, y quien la pidió ve el error de la orden. Una orden que no exige filas cambiadas (`min_affected_rows`) contesta bien y emite su aviso aunque no haya cambiado nada. Si el código de un módulo (no su manifiesto) devuelve un aviso que el módulo no declara en `events.emits` ni en el `emit` de sus órdenes, o del espacio de nombres de otro módulo instalado, o un aviso de mensaje o de impresión sin tener ese permiso declarado, la orden se rechaza entera y no se apunta nada (lo primero solo en un módulo que declara `events.emits`, como todos los publicados). Una clave de no repetición que el contenido no trae se ignora con un aviso en el registro del servidor y el aviso sale sin deduplicar.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes: ejecutar una orden de un módulo y su comprobación de qué avisos puede emitir
QA: BD-09, qa-hub-flows R1, qa-hub-flows R7

### HUB-F51 Entregar un aviso a los módulos que lo escuchan
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada segundo el hub repasa la cola de salida y toma, de la más antigua a la más nueva, hasta 50 avisos que ya tocan.
2. Para cada aviso busca los módulos **activos** que lo escuchan en ese momento y le pasa el aviso a cada uno. Cada módulo reacciona con su propia autoridad, no con la de la persona que causó el aviso: una venta que cobra un empleado baja el stock y manda la factura igual que si la cobrara el dueño.
3. Lo que hace cada módulo queda guardado junto con la marca de «ya entregado a este módulo». Si el hub se reinicia a mitad, al volver no repite a quien ya lo recibió.
4. Además, en la misma pasada: si es un mensaje para fuera, lo manda (HUB-F61); si es un trabajo de impresión, lo deja en la cola de impresión; si es el borrado de los datos de un cliente, vacía el historial que lo nombra; despierta o cancela las esperas de las automatizaciones que dependen de ese aviso; y arranca las automatizaciones que se disparan con él (HUB-F82).
5. Si todo fue bien, el aviso queda como entregado. Si algo falló, solo se repite lo que falló (HUB-F52).
Entra: los avisos pendientes de la cola y la lista de módulos activos con lo que escucha cada uno (`events.listen`).
Sale: los efectos de cada módulo que escucha, en el hub del aviso y atribuidos a la persona que lo causó (el `created_by` de un movimiento de stock dice quién cobró); la marca de entrega por módulo (`_event_delivery`); los avisos que esos módulos emiten a su vez, con un nivel más de cadena; y el aviso marcado como entregado. Las reacciones en cadena también llegan a las pantallas en vivo.
Si falla: un módulo que falla no impide que los demás reciban el aviso en la misma pasada. Una cadena de reacciones de más de 16 niveles se corta y el aviso va directamente a «Eventos caídos». Un módulo desactivado no recibe el aviso y, si se vuelve a activar, no recibe los que se entregaron mientras estaba apagado. Si dos copias del hub corren a la vez durante una actualización, cada aviso lo toma solo una; si la copia que lo tomó muere a mitad, otra lo retoma a los 5 minutos. El orden de entrega es el de llegada mientras nada falla: un aviso que se reintenta puede llegar después de otros más nuevos.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, negocio y datos: vaciar del historial del hub lo que nombra a un cliente borrado (`customer.anonymized`)
Pendiente de enlazar: hub — HUB, impresión: dejar en la cola de impresión el trabajo que trae un aviso `*.print.due`
QA: BD-09, qa-hub-flows R3, qa-hub-flows R9, qa-hub-restaurant §7.03

### HUB-F52 Reintentar un aviso que un módulo no pudo procesar
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo que escucha un aviso lo rechaza o falla (Caja sin turno abierto para apuntar una anulación, Facturación que no cuadra un importe, Cocina que recibe una ronda sin nada que cocinar).
2. El hub no lo da por perdido: lo vuelve a intentar más tarde, cada vez más espaciado (a los 2, 4, 8, 16, 32, 64 y 128 segundos), y solo con el módulo que falló.
3. Si al octavo intento sigue fallando (unos 4 minutos después del primero), el aviso pasa a «Eventos caídos» con el último error, y ahí espera a que una persona decida (HUB-F54).
4. Lo que hizo la orden que lo emitió sigue hecho: la venta sigue cobrada, la anulación sigue anulada.
Entra: el aviso pendiente y el error del módulo que falló.
Sale: el aviso con su contador de intentos, la hora del siguiente intento y el último error; al agotarse, el aviso en estado caído (`dead`), con su contenido completo intacto. Los módulos que sí lo recibieron no vuelven a recibirlo.
Si falla: si la base de datos falla al apuntar el reintento, el aviso se queda como estaba y se vuelve a tomar en el siguiente repaso. Nadie avisa al módulo que emitió el aviso ni a la persona que lo causó: el único rastro es el recuento de la campana para el administrador (HUB-F59) y la lista de «Eventos caídos». El contador que guarda el aviso caído dice 7, no 8 (el intento que lo mata no se suma).
Implicados: CASH_REGISTER-F14, INVENTORY-F21, INVOICE-F06, KITCHEN-F05, REC_FISCAL-F09
QA: BD-09, qa-hub-flows R8, qa-hub-restaurant §11

### HUB-F53 Mandar a «Eventos caídos» al momento lo que reintentar no arregla
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Hay tres negativas que el octavo intento sabría igual que el primero, y el hub no espera los 4 minutos para reconocerlas:
   - el módulo que escucha (o el que pide imprimir o mandar un mensaje) necesita un permiso que el dueño no le ha concedido en Ajustes → Permisos;
   - la cuota de WhatsApp del negocio está agotada;
   - el dueño retiró el permiso de una automatización mientras su mensaje esperaba en la cola.
2. En los tres casos el aviso pasa a «Eventos caídos» en el primer intento, con el motivo marcado.
3. Los dos primeros se pueden reenviar (al conceder el permiso o recuperar la cuota). El tercero no: al aviso se le borra el destinatario y no se ofrece reenviarlo.
Entra: el aviso y la negativa del permiso, de la cuota o de la automatización.
Sale: el aviso caído con su motivo (`failure_kind`: `module.capability_denied`, vacío para la cuota, o `flow.release_revoked`). En el tercer caso, el teléfono o el correo del destinatario desaparece del contenido guardado y queda la marca de destinatario oculto.
Si falla: solo se mata al momento si esa negativa es el único fallo de la pasada; si otro módulo también falló, el aviso sigue la escalera normal de HUB-F52. Un fallo de la base de datos al comprobar el permiso no cuenta como negativa: sigue la escalera.
Implicados: PRINTING-F16
Pendiente de enlazar: hub — HUB, módulos y órdenes: conceder y comprobar el permiso de una primitiva del hub (impresora, mensajes, certificado) de un módulo
QA: qa-hub-flows R8

### HUB-F54 Ver la cola de avisos caídos
Estado: parcial — la lista enseña solo los 100 más recientes, sin paginar (con más, los antiguos no se ven, aunque «Reenviar todos» los mueve igual); y no hay forma de ver lo cerrado en la pantalla de Sistema (la lectura existe en el servidor, flows#47)
Actor: administrador
Pantalla: HUB_SHELL: Sistema › Eventos caídos
Pasos:
1. Un administrador abre **Sistema → Eventos caídos** (o la bandeja «Necesita tu atención» de Automatizaciones, FLOWS-F25).
2. Ve cada aviso que no se pudo entregar, del más nuevo al más antiguo: qué aviso era, qué módulo lo emitió, quién lo causó, su contenido completo, el último error, cuántos intentos y cuándo nació, y si se puede reenviar.
3. Desde ahí lo reenvía (HUB-F55, HUB-F56) o lo cierra (HUB-F57).
Entra: la sesión de un dueño o administrador de este hub.
Sale: nada guardado. La lista de cerrados (`GET /api/hub/events/discarded`) da quién cerró cada uno, cuándo y por qué, sin el contenido.
Si falla: sin sesión, el hub contesta que no hay sesión; con la sesión de un perfil que no administra (cajero, empleado), la rechaza. Si la petición la hace un módulo, ese módulo necesita además el permiso «Administrar automatizaciones» concedido. Una API key o el token de máquina no sirven. Los avisos caídos de otro hub no se ven.
Implicados: FLOWS-F25
Pendiente de enlazar: hub — HUB_SHELL, Sistema › Eventos caídos (la pantalla que lista, reenvía y descarta)
QA: BD-10, qa-hub-flows R8

### HUB-F55 Reenviar un aviso caído
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Sistema › Eventos caídos
Pasos:
1. Quien arregló la causa (concedió el permiso, abrió la caja, corrigió la regla de impuestos) pulsa reenviar en el aviso caído.
2. El aviso vuelve a la cola con los 8 intentos de nuevo y lo entrega el siguiente repaso, en un segundo.
3. Solo lo recibe el módulo que había fallado: los que ya lo recibieron no lo vuelven a procesar.
4. Si la causa sigue, el aviso vuelve a caer y reaparece en la lista.
Entra: el aviso caído elegido y la sesión de un administrador.
Sale: el aviso pendiente de nuevo, con el error y el motivo borrados; el contenido no se edita.
Si falla: un aviso que ya no está caído (se entregó, se cerró, no existe o es de otro hub) da «no encontrado». Uno marcado como no reenviable (permiso de una automatización retirado) se niega con su motivo (`409`, mensaje del hub en inglés): hay que volver a conceder el permiso y relanzar la automatización.
Implicados: FLOWS-F25, INVOICE-F06, REC_FISCAL-F09, CASH_REGISTER-F14
Pendiente de enlazar: hub — HUB_SHELL, Sistema › Eventos caídos (reintentar desde la pantalla)
QA: BD-10, qa-hub-flows R8

### HUB-F56 Reenviar todos los avisos caídos
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Sistema › Eventos caídos
Pasos:
1. Tras una caída pasajera que tumbó varios avisos a la vez, el administrador arregla la causa y pulsa **Reenviar todos**.
2. Todos los avisos caídos del hub que se pueden reenviar vuelven a la cola de una vez, también los que no caben en la lista.
3. Se ve cuántos se han reenviado.
Entra: la sesión de un administrador.
Sale: los avisos caídos reenviables, pendientes otra vez con los intentos a cero. Los que no se pueden reenviar se quedan donde estaban. Repetirlo sin avisos caídos no mueve nada.
Si falla: el mismo rechazo de sesión que HUB-F54.
Implicados: FLOWS-F25
Pendiente de enlazar: hub — HUB_SHELL, Sistema › Eventos caídos (botón «Reenviar todos»)
QA: qa-hub-flows R8

### HUB-F57 Cerrar un aviso caído con motivo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Sistema › Eventos caídos
Pasos:
1. El administrador decide que un aviso caído no debe entregarse nunca (está duplicado, ya se resolvió a mano, ya no aplica).
2. Lo cierra, con un motivo si quiere.
3. El aviso deja de estar en la cola de caídos y no se vuelve a intentar nunca.
Entra: el aviso caído, el motivo (opcional; se guarda sin espacios sobrantes y cortado a 500 caracteres) y la sesión del administrador.
Sale: el aviso cerrado (`discarded`), con la hora, quién lo cerró (sale de la sesión, nunca de lo que se envía) y el motivo. No se borra: se conserva 90 días desde el cierre y después la poda del historial lo quita. Cerrar el cobro de una venta deja esa venta sin factura para siempre.
Si falla: un aviso que ya no está caído da «no encontrado» y no cambia nada.
Implicados: FLOWS-F25, INVOICE-F06, REC_FISCAL-F09
Pendiente de enlazar: hub — HUB_SHELL, Sistema › Eventos caídos (descartar desde la pantalla)
Pendiente de enlazar: hub — HUB, negocio y datos: la poda de 90 días del historial terminal
QA: BD-10, qa-hub-flows R8

### HUB-F58 Reenviar solo lo que un permiso había rechazado, al concederlo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Permisos
Pasos:
1. Un aviso cayó porque a un módulo le faltaba un permiso de primitiva (impresora, mensajes, certificado) que nadie había concedido (HUB-F53).
2. El dueño concede ese permiso en Ajustes → Permisos.
3. En ese mismo gesto el hub devuelve a la cola todos los avisos caídos por un permiso sin conceder, de todo el hub; no hace falta ir a «Eventos caídos».
4. Los que siguen sin su permiso vuelven a caer en la siguiente pasada, con su motivo.
Entra: el permiso concedido.
Sale: los avisos caídos con el motivo `module.capability_denied`, pendientes otra vez. Retirar un permiso no mueve nada.
Si falla: si el reenvío no puede hacerse (base de datos caída), el permiso queda concedido igual, el fallo va al registro del servidor y los avisos se quedan caídos para reenviarlos a mano (HUB-F55).
Implicados: PRINTING-F16
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Permisos (conceder el permiso de una app)
QA: ninguno

### HUB-F59 Contar los avisos caídos para la campana
Estado: hecho
Actor: sistema, administrador
Pantalla: HUB_SHELL: campana de Notificaciones
Pasos:
1. Con la sesión de un administrador, la campana pregunta al hub cuántos avisos caídos hay ahora.
2. El hub contesta solo con el número: los caídos que esperan decisión, sin contar los pendientes, los entregados ni los cerrados.
3. Cuando el número baja a cero (porque se reenviaron o se cerraron), la fila de la campana desaparece sola.
Entra: la sesión de un administrador.
Sale: el número de avisos caídos del hub; ningún contenido.
Si falla: el mismo rechazo de sesión que HUB-F54: un cajero o un empleado no recibe el número. El número no dice qué aviso es ni de qué documento (por ejemplo, que es una venta sin factura).
Implicados: INVOICE-F06, REC_FISCAL-F09
Pendiente de enlazar: hub — HUB_SHELL, campana de Notificaciones (fuente «Eventos caídos», que sondea este número cada 60 s)
QA: BD-09

### HUB-F60 Avisar a las pantallas en vivo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al abrirse, la aplicación del hub pide al hub un pase de un solo uso (vale 60 segundos) con la sesión de quien la usa.
2. Con ese pase abre el canal en vivo. Desde entonces recibe al momento cada aviso que se guarda en el hub: una venta cobrada, una comanda nueva, una cita, un módulo instalado.
3. Cada pantalla reacciona por su cuenta: la cocina pinta la comanda, el TPV que cobró imprime el tique, la campana o el aviso del sistema avisan.
4. Si la conexión se corta, la aplicación pide otro pase y se vuelve a conectar.
Entra: la sesión de una persona del hub (para el pase), o una API key del hub que pueda leer (para una integración).
Sale: cada aviso con su contenido, el módulo que lo emitió y la pantalla que mandó la orden (`client_instance`), por WebSocket (`/ws`) o por SSE (`/api/events`). La aplicación entra con la llave de solo lectura del propio hub y lo recibe todo; una llave de integración con permisos por módulo solo recibe los avisos de los módulos que puede leer, y ninguno del propio hub.
Si falla: el canal en vivo no guarda nada: un aviso que llega mientras la pantalla está desconectada, o que se pierde porque la pantalla va lenta (más de 256 avisos de retraso), no se le vuelve a mandar; los módulos sí lo reciben por la cola (HUB-F51). Sin credencial, o con una de otro hub, se rechaza; una llave que solo puede escribir también; más de 16 conexiones con la misma llave se rechazan.
Implicados: KITCHEN-F05
Pendiente de enlazar: hub — HUB_SHELL, la aplicación: imprimir al oír la venta o la comanda solo en el dispositivo que la mandó, y lanzar el aviso del sistema
Pendiente de enlazar: hub — HUB_APP, aviso del sistema de la app instalada al llegar una comanda o una cita
QA: qa-hub-restaurant §7.08

### HUB-F61 Mandar el email o el WhatsApp que pide un módulo o una automatización
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo (o un paso «Enviar un mensaje» de una automatización, HUB-F93) deja un aviso de mensaje pendiente: por qué canal, a quién, con qué plantilla y qué texto.
2. El hub comprueba, antes de que salga nada, que quien lo pide puede: un módulo necesita el permiso de mensajes concedido, haber declarado ese canal y que el destinatario sea del propio hub (la lista de destinatarios permitidos de los ajustes, o el correo de un usuario activo); una automatización necesita sus dos permisos vivos, canal y de dónde sale el destinatario, que se vuelven a leer en ese momento.
3. Lo manda por ERPlora: el correo sale con el remitente verificado de ERPlora y la respuesta va al negocio; el WhatsApp sale con el número del negocio, descontando su cuota.
4. Lo apunta como enviado, con el identificador que le dio WhatsApp, para no repetirlo y para saber qué automatización preguntó si el cliente contesta tocando un botón.
Entra: el aviso de mensaje (`*.reminder.due`): canal, destinatario, plantilla y variables.
Sale: el mensaje entregado al proveedor y la marca de envío con el identificador del proveedor, la automatización y su paso. Un archivo de cabecera subido al hub se firma en cada intento para que WhatsApp lo pueda descargar.
Si falla: un fallo de red o del proveedor sigue la escalera de HUB-F52; cuota agotada o permiso del módulo sin conceder van directos a «Eventos caídos» (HUB-F53); el permiso retirado de una automatización lo cierra para siempre sin destinatario. Un destinatario mal escrito (un correo sin dominio, un teléfono que no es internacional `+34…`), dos destinatarios en uno o uno que no es del hub se rechazan y acaban en «Eventos caídos». El SMS no tiene transporte y se rechaza. Sin enlace con ERPlora (token de máquina) no sale nada y se reintenta. Que el mensaje llegue al cliente no se comprueba: la marca dice «entregado al proveedor».
Implicados: pendiente
Pendiente de enlazar: saas — proxy de notificaciones del dispositivo: enviar el correo y el WhatsApp del hub y cobrar la cuota
Pendiente de enlazar: hub — HUB, WhatsApp y asistente: cuota de WhatsApp del negocio
QA: qa-hub-flows R7

### HUB-F62 Ejecutar las tareas programadas de los módulos
Estado: parcial — una tarea cuya orden falla se repite cada 5 minutos para siempre sin dejar rastro fuera del registro del servidor (ni campana, ni «Eventos caídos», ni contador de intentos); y no hay ninguna pantalla que diga qué tareas hay ni cuándo corrieron por última vez
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo declara en su manifiesto tareas que el hub debe hacer solo cada cierto tiempo. Hoy: cerrar las cajas olvidadas (cada 5 min), soltar las reservas sin confirmar y las mesas retenidas (cada 15 min), caducar las sesiones de bono retenidas (cada hora), enviar a la AEAT lo que quedó pendiente (cada 5 min) y repasar las conversaciones de WhatsApp sin ficha (cada 15 min).
2. Al instalar o actualizar el módulo, el hub apunta sus tareas; al actualizar conserva cuándo toca la siguiente; las que el módulo ya no declara se borran.
3. Cada segundo el hub mira qué tareas tocan y ejecuta la orden de cada una como el propio hub, sin persona detrás.
4. Si el hub estuvo apagado y se perdió varias pasadas, al volver la hace **una sola vez** y sigue con la siguiente hora que toque (o ninguna, si la tarea lo pide así).
Entra: las tareas del manifiesto (`scheduled_tasks`: orden del propio módulo, horario `cron` de 5 campos, datos y qué hacer con lo perdido).
Sale: los efectos de la orden y la hora de la siguiente vez, guardados juntos: si la orden falla, la tarea no avanza. Los horarios se leen en hora UTC, no en la del negocio (las automatizaciones sí usan la hora del negocio, HUB-F83).
Si falla: una orden que falla deja la tarea apartada 5 minutos y se vuelve a intentar, sin límite. Un horario que el hub no sabe leer no se programa (se avisa en el registro del servidor). Una tarea de un módulo desactivado no corre y solo se reprograma. Con dos copias del hub a la vez durante una actualización, cada tarea la ejecuta una sola.
Implicados: VERIFACTU-F20, REC_FISCAL-F06
Pendiente de enlazar: hub — HUB, módulos y órdenes: el instalador que apunta las tareas programadas al instalar, actualizar y desinstalar
QA: ninguno

### HUB-F63 Seguir la cadena de lo que provocó un aviso
Estado: parcial — solo por la API: ninguna pantalla lo enseña, y el historial de una automatización no enlaza con el aviso que la arrancó
Actor: administrador
Pantalla: asistente
Pasos:
1. Con el identificador de un aviso (por ejemplo, el de una venta), se pide al hub qué provocó.
2. El hub devuelve el aviso, las automatizaciones que arrancó y los avisos que nacieron al entregarlo, un nivel cada vez.
3. Para seguir bajando, se pide lo mismo con cada aviso hijo.
Entra: el identificador del aviso y la sesión de un administrador (`GET /api/hub/events/{id}/trace`).
Sale: el aviso (sin su contenido), sus ejecuciones de automatización y los avisos hijos, hasta 200 de cada.
Si falla: un aviso de otro hub o que ya se podó (90 días después de entregarse) da «no encontrado». El mismo rechazo de sesión que HUB-F54.
Implicados: ninguno
QA: qa-hub-flows R8

### HUB-F64 Contar que alguien usa el hub
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada vez que una persona o una integración del hub hace algo con una credencial válida, el hub anota la hora (sin escribir nada en ese momento).
2. Cada minuto guarda esa hora en la base de datos, y al apagarse de forma ordenada, también.
3. En su latido diario a ERPlora le dice cuándo entró alguien por última vez, solo si ha habido entradas nuevas.
4. ERPlora usa esa hora para no apagar ni borrar un hub gratuito que se está usando.
Entra: las peticiones con sesión o con API key que no fueron rechazadas.
Sale: la hora de la última entrada (`_hub_activity`), que nunca retrocede, y la hora que ERPlora ya confirmó.
Si falla: un intento con credencial caducada o rechazada no cuenta, ni las visitas anónimas (la pantalla de entrada, un comprobador de salud). Si el hub muere de golpe, se puede perder como mucho el último minuto. Si el latido falla, se vuelve a mandar en el siguiente.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso, personas y plan: el latido diario a ERPlora que lleva la última entrada
Pendiente de enlazar: saas — ciclo de vida del hub gratuito: apagar a los 60 días sin entradas y borrar a los 120
QA: ninguno
