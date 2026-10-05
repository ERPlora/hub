# WORKFLOW — Hub (servidor) · Avisos entre módulos

Prefijo: HUB

> **Para qué sirve (avisos y automatizaciones).** El hub reparte entre módulos lo que pasa en el
> negocio: cuando una orden se guarda, deja un **aviso** en una cola que se guarda a la vez que la
> orden, y un repartidor de fondo lo entrega a cada módulo que lo escucha, con reintentos y con una
> cola de **avisos caídos** («Eventos caídos») que decide un administrador. Encima de ese reparto
> corre el **motor de automatizaciones** (ADR-0283, [automatizaciones.md](automatizaciones.md)):
> reglas que el dueño monta en la pantalla Automatizaciones (módulo `flows`) o que traen de fábrica
> los módulos (las recetas de WhatsApp), con permisos propios por automatización. También ejecuta
> las tareas programadas de los módulos, empuja los avisos a las pantallas en vivo y le dice a
> ERPlora que alguien usa el hub. Lo que vale para las dos partes (datos personales, borrado de un
> cliente, puertas) está al final de este fichero.
>
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

## Antes de empezar

- Nada que preparar para el reparto de avisos ni las tareas programadas: corren solos desde el
  arranque del hub.
- Para que un módulo pueda imprimir o mandar mensajes por la cola, el dueño le concede ese permiso
  en Ajustes › Permisos (sin él, sus avisos caen al momento en «Eventos caídos» y se reenvían solos al
  concederlo: HUB-F53, HUB-F58).
- Para mandar mensajes: el hub enlazado con ERPlora (credencial de máquina) y, para WhatsApp, el
  número conectado y cupo (HUB-F61).

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
Sale: una fila en la cola de salida (`_event_outbox`, estado pendiente) con el aviso, su contenido, el módulo que lo emite, la persona que lo causó, la automatización que lo emitió si la hay (`run_id`), el aviso que lo provocó si es una reacción en cadena (`parent_event_id`) y la pantalla que mandó la orden (`client_instance`). Si el manifiesto declara una clave de no repetición para ese aviso (`emit[].dedup_key`, por ejemplo el identificador del mensaje de WhatsApp), un segundo aviso con la misma clave en el mismo hub no se apunta. Si el módulo devuelve desde su código el mismo aviso que declara, se apunta una sola vez, la copia del código (hub#1786), y en ese caso no se aplica la clave de no repetición. También empuja el aviso a las pantallas en vivo (HUB-F60).
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
Si falla: si la base de datos falla al apuntar el reintento, el aviso se queda como estaba y se vuelve a tomar a los 5 minutos, cuando caduca su reserva. Nadie avisa al módulo que emitió el aviso ni a la persona que lo causó: el único rastro es el recuento de la campana para el administrador (HUB-F59) y la lista de «Eventos caídos». El contador que guarda el aviso caído dice 7, no 8 (el intento que lo mata no se suma).
Implicados: CASH_REGISTER-F14, FLOWS-F25, INVENTORY-F21, INVOICE-F06, KITCHEN-F05, PRINTING-F16, REC_FISCAL-F09
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
Si falla: sin sesión, el hub contesta que no hay sesión; con la sesión de un perfil que no administra (cajero, empleado), la rechaza. Si la petición se declara hecha por un módulo (cabecera `X-Erplora-Module`), ese módulo necesita además «Administrar automatizaciones» concedido; es una declaración, no una autenticación: un módulo que no se declara pasa solo con la sesión del administrador (la misma regla vale para HUB-F55…F59 y F63). Una API key o el token de máquina no sirven. Los avisos caídos de otro hub no se ven.
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
3. Al conceder cualquier permiso de primitiva a cualquier módulo, el hub devuelve a la cola todos los avisos caídos por un permiso sin conceder, de todo el hub; no hace falta ir a «Eventos caídos».
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
Estado: parcial — no filtra por perfil: cualquier sesión del hub, también la de un cajero, recibe todos los avisos con los datos de los clientes; el tope de 16 conexiones es para el hub entero (todas las pantallas comparten llave); en `/ws` un segundo mensaje de autenticación cambia la llave y su alcance; el canal SSE acepta una API key de larga duración en la dirección; y revocar una llave o cerrar sesión no corta un canal ya abierto (leído, sin ejecutar)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al abrirse, la aplicación del hub pide al hub un pase de un solo uso (vale 60 segundos) con la sesión de quien la usa, sea del perfil que sea.
2. Con ese pase abre el canal en vivo (por SSE, en la dirección; o por WebSocket, en el primer mensaje). Desde entonces recibe al momento cada aviso que se guarda en el hub: una venta cobrada, una comanda nueva, una cita, una pregunta de una automatización, un módulo instalado.
3. Cada pantalla reacciona por su cuenta: la cocina pinta la comanda, el TPV que cobró imprime el tique, la campana o el aviso del sistema avisan.
4. Si la conexión se corta, la aplicación pide otro pase y se vuelve a conectar.
Entra: la sesión de una persona del hub (para el pase), o una API key del hub que pueda leer (para una integración).
Sale: cada aviso con su contenido, el módulo que lo emitió y la pantalla que mandó la orden (`client_instance`), por WebSocket (`/ws`) o por SSE (`/api/events`). La aplicación entra con la llave de solo lectura del propio hub y recibe **todo, sea cual sea el perfil de quien la abre** (también un cajero recibe los avisos con datos de clientes, los mensajes de WhatsApp y las preguntas de las automatizaciones). Una llave de integración `read_only` o `full` lo recibe todo; una `custom`, solo lo de los módulos que puede leer, y nada del hub. Los avisos propios del hub (módulo instalado, impresión) llevan otra forma de mensaje (`{"type": …}`).
Si falla: el canal en vivo no guarda nada: un aviso que llega mientras la pantalla está desconectada, o que se pierde porque la pantalla va lenta (más de 256 avisos de retraso), no se le vuelve a mandar; los módulos sí lo reciben por la cola (HUB-F51). Sin credencial, o con una de otro hub, se rechaza; una llave que solo puede escribir también. Más de 16 conexiones a la vez **en todo el hub** (todas las pantallas y dispositivos comparten la llave de la aplicación) se rechazan: la pantalla 17.ª se queda sin avisos en vivo. En `/ws` los rechazos llegan como mensaje `stream.error`, no como código HTTP, y una credencial inválida en la cabecera del saludo se ignora y acaba en «sin autenticar» a los 15 segundos.
Implicados: KITCHEN-F05
Pendiente de enlazar: hub — HUB_SHELL, la aplicación: imprimir al oír la venta o la comanda solo en el dispositivo que la mandó, y lanzar el aviso del sistema
Pendiente de enlazar: hub — HUB_APP, aviso del sistema de la app instalada al llegar una comanda o una cita
Pendiente de enlazar: hub — HUB, acceso, personas y plan: la llave de solo lectura de la aplicación y el pase del canal en vivo
QA: qa-hub-restaurant §7.08

### HUB-F61 Mandar el email o el WhatsApp que pide un módulo o una automatización
Estado: parcial — un mensaje puede salir dos veces: el envío y la marca de «enviado» son dos escrituras separadas y a ERPlora no se le pasa clave de no repetición (leído, sin ejecutar)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo (o un paso «Enviar un mensaje» de una automatización, HUB-F93) deja un aviso de mensaje pendiente: por qué canal, a quién, con qué plantilla y qué texto.
2. El hub comprueba, antes de que salga nada, que quien lo pide puede: un módulo necesita el permiso de mensajes concedido, haber declarado ese canal y que el destinatario sea del propio hub (la lista de destinatarios permitidos de los ajustes, o el correo de un usuario activo); una automatización necesita sus dos permisos vivos, canal y de dónde sale el destinatario, que se vuelven a leer en ese momento.
3. Lo manda por ERPlora: el correo sale con el remitente verificado de ERPlora y la respuesta va al negocio; el WhatsApp sale con el número del negocio, descontando su cuota.
4. Después, en una escritura aparte, lo apunta como enviado, con el identificador que le dio WhatsApp, para no repetir lo que ya consta como enviado y para saber qué automatización preguntó si el cliente contesta tocando un botón.
Entra: el aviso de mensaje (`*.reminder.due`): canal, destinatario, plantilla y variables.
Sale: el mensaje entregado al proveedor y la marca de envío con el identificador del proveedor, la automatización y su paso. Un archivo de cabecera subido al hub se firma en cada intento para que WhatsApp lo pueda descargar.
Si falla: un fallo de red o del proveedor, o cualquier rechazo de ERPlora que no sea de cuota (número sin WhatsApp, plantilla rechazada), sigue la escalera de HUB-F52; solo la cuota agotada (402/429) y el permiso del módulo sin conceder van directos a «Eventos caídos» (HUB-F53); el permiso retirado de una automatización lo cierra para siempre sin destinatario. Un destinatario mal escrito (un correo sin dominio, un teléfono que no es internacional `+34…`), dos destinatarios en uno, uno que no es del hub, un canal no declarado o el SMS (sin transporte) se rechazan en cada intento y, tras los 8 (unos 4 min), acaban en «Eventos caídos». Sin enlace con ERPlora (token de máquina) no sale nada y se reintenta. Si la respuesta de ERPlora se pierde después de enviar, o falla apuntar la marca, el reintento lo vuelve a mandar: el cliente puede recibir el mismo WhatsApp o correo dos veces. Que el mensaje llegue al cliente no se comprueba: la marca dice «entregado al proveedor».
Implicados: pendiente
Pendiente de enlazar: saas — proxy de notificaciones del dispositivo: enviar el correo y el WhatsApp del hub y cobrar la cuota
Pendiente de enlazar: hub — HUB, WhatsApp y asistente: cuota de WhatsApp del negocio
QA: qa-hub-flows R7

### HUB-F62 Ejecutar las tareas programadas de los módulos
Estado: parcial — una tarea cuya orden falla se repite cada 5 minutos para siempre sin dejar rastro fuera del registro del servidor (ni campana, ni «Eventos caídos», ni contador de intentos), y ese fallo corta el resto de tareas vencidas de ese segundo; y no hay ninguna pantalla que diga qué tareas hay ni cuándo corrieron por última vez
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo declara en su manifiesto tareas que el hub debe hacer solo cada cierto tiempo. Hoy: cerrar las cajas olvidadas (cada 5 min), soltar las reservas sin confirmar y las mesas retenidas (cada 15 min), caducar las sesiones de bono retenidas (cada hora), enviar a la AEAT lo que quedó pendiente (cada 5 min) y repasar las conversaciones de WhatsApp sin ficha (cada 15 min).
2. Al instalar o actualizar el módulo, el hub apunta sus tareas; al actualizar conserva cuándo toca la siguiente, también si el módulo cambió el horario (el nuevo se aplica a partir de esa vez); las que el módulo ya no declara se borran.
3. Cada segundo el hub mira qué tareas tocan y ejecuta la orden de cada una como el propio hub, sin persona detrás.
4. Si el hub estuvo apagado y se perdió varias pasadas, al volver la hace **una sola vez** y sigue con la siguiente hora que toque (o ninguna, si la tarea lo pide así).
Entra: las tareas del manifiesto (`scheduled_tasks`: orden del propio módulo, horario `cron` de 5 campos, datos y qué hacer con lo perdido).
Sale: los efectos de la orden y la hora de la siguiente vez, guardados juntos: si la orden falla, la tarea no avanza. Los horarios se leen en hora UTC, no en la del negocio (las automatizaciones sí usan la hora del negocio, HUB-F83).
Si falla: una orden que falla deja la tarea apartada 5 minutos y se vuelve a intentar, sin límite; además corta el repaso de ese segundo, y las demás tareas vencidas esperan al siguiente. Un horario que el hub no sabe leer no se programa (se avisa en el registro del servidor). Una tarea de un módulo desactivado no corre y solo se reprograma. Con dos copias del hub a la vez durante una actualización, cada tarea la ejecuta una sola.
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
Sale: el aviso sin su contenido, pero sus ejecuciones de automatización con sus datos de entrada (normalmente el contenido completo del aviso, con datos de clientes), y los avisos hijos sin contenido, hasta 200 de cada.
Si falla: un aviso de otro hub o que ya se podó (90 días después de entregarse) da «no encontrado». El mismo rechazo de sesión que HUB-F54.
Implicados: ninguno
QA: qa-hub-flows R8

### HUB-F64 Contar que alguien usa el hub
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada petición que trae una sesión o una API key del hub y no es rechazada por falta de permiso (401/403) cuenta como entrada: el hub anota la hora (sin escribir nada en ese momento) y no comprueba aparte que la credencial sea válida.
2. Cada minuto guarda esa hora en la base de datos, y al apagarse de forma ordenada, también.
3. En su latido diario a ERPlora le dice cuándo entró alguien por última vez, solo si ha habido entradas nuevas.
4. ERPlora usa esa hora para no apagar ni borrar un hub gratuito que se está usando.
Entra: las peticiones con cabecera de sesión (`X-Hub-Session`) o de API key (`Bearer erpl_live_…`) que no terminaron en 401/403, también las de rutas que no autentican (`/healthz`, `/api/hub/context`) y las que terminan en 404 o 500.
Sale: la hora de la última entrada (`_hub_activity`), que nunca retrocede, y la hora que ERPlora ya confirmó.
Si falla: una petición rechazada con 401/403 no cuenta, ni las anónimas (sin cabecera), ni el pase del canal en vivo, ni el primer mensaje de `/ws`, ni la llave de máquina (`erpk_`). Si el hub muere de golpe, se puede perder como mucho el último minuto. Si el latido falla, se vuelve a mandar en el siguiente.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso, personas y plan: el latido diario a ERPlora que lleva la última entrada
Pendiente de enlazar: saas — ciclo de vida del hub gratuito: apagar a los 60 días sin entradas y borrar a los 120
QA: ninguno

## Cobertura contra la referencia

Referencia adoptada:

- **Transactional Outbox** (`architecture/hub/event-outbox.md`, decisión del 2026-06-09): el aviso se
  guarda en la misma transacción que la orden; entrega al menos una vez, sin repetir por módulo.
- [Business Central — Job Queue Entries](https://learn.microsoft.com/en-us/dynamics365/business-central/admin-job-queues-schedule-tasks):
  número máximo de intentos con espera entre ellos, estado «Error» que espera a una persona,
  reiniciar, y aviso cuando una tarea falla. Se adopta la escalera de reintentos y la cola de errores
  operable; no se adopta el aviso dirigido a quien lanzó la tarea (hueco, HUB-F52).
- [Odoo OCA `queue_job`](https://github.com/OCA/queue/tree/16.0/queue_job): reintentos con patrón de
  espera, estado fallido, «Requeue» y «Set to done». Se adopta reenviar y cerrar (aquí con motivo).

| Elemento | Estado | Flujo |
|---|---|---|
| Guardar el aviso con la orden, sin perderlo en un reinicio | hecho | HUB-F50 |
| Entrega al menos una vez, sin repetir por receptor | hecho para los módulos; un correo o WhatsApp puede salir dos veces | HUB-F51, HUB-F61 |
| Reintentos con espera creciente y número máximo | hecho (8, ~4 min, fijo; no configurable) | HUB-F52 |
| Negativas que no merece la pena reintentar, al momento | hecho | HUB-F53 |
| Cola de errores visible con el motivo | parcial: 100 más recientes, sin paginar | HUB-F54 |
| Reenviar uno / todos | hecho | HUB-F55, HUB-F56 |
| Cerrar sin entregar, con quién y por qué | hecho (motivo opcional; la pantalla de Sistema no lo pide: HUB_SHELL) | HUB-F57 |
| Ver lo cerrado | parcial: lectura en el servidor, sin pantalla (flows#47) | HUB-F54 |
| Avisar a quien lanzó lo que falló | no hecho: solo el recuento genérico de la campana para el administrador | HUB-F59 |
| Tareas programadas con estado, último error y reinicio visibles | parcial: corren y se recuperan, pero sin pantalla ni rastro de error | HUB-F62 |

## Datos: de quién es cada dato

Todo lo de avisos y automatizaciones es del hub (tablas de sistema): ningún módulo las escribe salvo
por las puertas del hub. Las de las automatizaciones están en
[automatizaciones.md](automatizaciones.md).

| Tabla | Qué guarda | Cuánto vive |
|---|---|---|
| `_event_outbox` | cada aviso: nombre, **contenido completo**, módulo emisor, `user_id` de quien lo causó, permisos del emisor (forense), estado, intentos, último error, ejecución y aviso padre, pantalla de origen; al cerrarse, quién (`hub_user:<id>`), cuándo y el motivo libre | entregados y cerrados: 90 días desde que terminan; **pendientes y caídos: sin límite** |
| `_event_delivery` | marca «entregado a este receptor», id del mensaje del proveedor, automatización y paso que preguntaron | con su aviso |
| `_scheduled_tasks` | tareas de los módulos, horario, próxima y última vez (sin `hub_id`: un hub por despliegue) | mientras el módulo las declare |
| `_hub_activity` | hora de la última entrada y la última confirmada por ERPlora | sin límite (una fila) |

No hay que confundir `_hub_activity` (la señal de última entrada, HUB-F64) con `_hub_activity_log`
(el registro de actividad que viaja en el latido, de [negocio-y-datos.md](negocio-y-datos.md),
HUB-F254).

**Inventario de datos personales de avisos y automatizaciones** (de las migraciones de sistema
`crates/runtime/src/system_migrations.rs` de las tablas `_flow*` y `_hub_activity`, y del
`ENSURE_TABLES` de `outbox.rs`):

- Contenido de los avisos (`_event_outbox.payload`): nombre, teléfono, correo, NIF y notas de clientes
  en avisos como `customer.created`, `sale.completed`, los mensajes de WhatsApp entrantes
  (`hub.whatsapp.message_received`) y los mensajes que salen (`*.reminder.due`, con el destinatario
  `to`). En un aviso caído se enseña entero en pantalla (HUB-F54).
- Quién hizo qué: `user_id` en cada aviso; `created_by`/`updated_by`/`deleted_by`/`granted_by`/
  `revoked_by`/`discarded_by`/`decided_by` en las tablas del motor.
- Texto libre: `discard_reason`, `comment` de una aprobación, `summary`/`title` de una pregunta
  (rellenados con datos del aviso), lo que el asistente escribe en la salida de su paso.
- Ejecuciones: `input`, `vars`, entrada y salida de pasos (lo que devuelven las consultas, legible;
  el texto de los mensajes con los datos insertados), `payload` de las propuestas. La dirección del
  destinatario de un mensaje se oculta en el historial (solo vive en la cola); los secretos se
  ocultan. La traza de un aviso (HUB-F63) devuelve el `input` de sus ejecuciones.
- Canal en vivo (HUB-F60): no guarda nada, pero entrega los avisos completos, con datos de clientes,
  a cualquier sesión del hub, también la de un cajero.
- Ejemplos del editor (HUB-F109): el texto de un WhatsApp entrante sale como ejemplo.
- `_flow_run_waits.correlate_value` (id de una cita o una reserva).
- **Borrado de un cliente** (lo hace negocio y datos, HUB-F249, `erasure.rs`): al llegar
  `customer.anonymized`, vacía los avisos **terminados** que contienen su id, las ejecuciones
  terminadas que lo tocaron con sus pasos y propuestas, y los avisos que esas ejecuciones encolaron.
  **No** alcanza: avisos pendientes o caídos, ejecuciones vivas (hub#2484), `last_error`, el `error` de
  cada paso, el `title`, `summary`, `reason` y `comment` de las preguntas, las esperas
  (`_flow_run_waits`), y copias con el teléfono pero sin el id (mensajes de WhatsApp entrantes,
  hub#2477; número sin ficha, hub#2474). Cualquier módulo puede emitir un `*.anonymized` sin
  declararlo (hub#2485).

## Reglas que no se rompen

- **Un aviso existe si y solo si su orden se guardó** (misma transacción).
- **Un módulo que escucha nunca recibe dos veces el mismo aviso** (marca por receptor en la misma
  transacción que sus efectos); los módulos no tienen que ser idempotentes. Un mensaje al exterior
  (correo, WhatsApp) y una llamada de un paso «Llamar a otro sistema» salen **al menos una vez**: se
  pueden repetir (HUB-F61, HUB-F94).
- **Un receptor reacciona con la autoridad de su módulo**, nunca con la del cajero; el `hub_id` sale
  siempre de la fila; la atribución (`created_by`) es la persona que causó el aviso. Las comprobaciones
  fiscales, de permisos de host y de esquema siguen aplicándose a los receptores.
- **Un aviso caído no se borra ni se poda** mientras nadie decida; cerrar nunca borra la fila.
- **Las puertas de la cola de caídos y del motor de automatizaciones exigen sesión de dueño o
  administrador**, nunca una llave de API ni la credencial de máquina; si la petición se declara
  hecha por un módulo, ese módulo necesita además «Administrar automatizaciones» (la cabecera es una
  declaración, no una autenticación: regla común del índice).
- **Nada sale del hub sin permiso vivo**: un mensaje de módulo exige permiso, canal declarado y
  destinatario del propio hub; uno de automatización, sus dos permisos releídos al enviar.

## Lo que NO hace, a propósito

- No entrega avisos en orden estricto: con reintentos, uno más nuevo puede llegar antes.
- No guarda lo que pasa por el canal en vivo: una pantalla desconectada no recibe lo que se perdió.
- No da a un módulo reactivado los avisos que se entregaron mientras estaba apagado.
- No manda SMS (no hay transporte).
- Las tareas programadas de los módulos van en UTC (hub#731): las escribe el programador, no el dueño.

## Dudas abiertas

1. ¿Debe la cola de caídos avisar al módulo o a la persona que causó el aviso (como Business Central
   avisa a quien lanzó la tarea), en vez de solo el recuento genérico del administrador?
2. ¿Debe una tarea programada que falla tener intentos máximos, un estado de error visible y un sitio
   en «Eventos caídos»?
3. ¿Debe el canal en vivo filtrar por perfil (un cajero no necesita los datos de clientes ni las
   preguntas de las automatizaciones), y el tope de conexiones ser por dispositivo y no por hub?

## Fuentes contrastadas

- `architecture/hub/state-durability.md` §4: dice que `ActivityState` vive solo en memoria; desde
  hub#670 se guarda en `_hub_activity` cada minuto (HUB-F64).
- `crates/server/src/event_stream.rs:675-678`: el comentario dice que `handle_frame` rechaza un segundo
  `auth`; lo acepta y cambia la llave del socket (HUB-F60).
- `architecture/hub/event-outbox.md` «Estado / verificado»: el «kick» inmediato tras cada orden no
  existe; el repartidor solo repasa cada segundo (HUB-F51).
- `WORKFLOW.md` de `flows` (FLOWS-F25): «tras sus reintentos»; los rechazados por permiso, cuota o
  permiso de automatización retirado llegan tras el primer intento (HUB-F53).
- Textos del shell (`apps/web/src/i18n/locales/es.ts`): «Hay {count} evento que el relay no pudo
  entregar» y «Evento reenviado al relay.» usan la jerga «relay» en la pantalla española (HUB_SHELL).
- El `409` de reenviar un aviso sale en inglés y la pantalla lo pinta tal cual (HUB-F55).
