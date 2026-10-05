# WORKFLOW — Hub · pantallas · Asistente

Prefijo: HUB_SHELL

> Área «Asistente» de las pantallas del hub: el panel lateral con el que una persona pregunta y le
> pide cosas al asistente. Lo que el servidor hace detrás (armar la conversación, ofrecer las
> herramientas, medir el consumo, guardar la denuncia) está en `hub-wf-mensajeria-asistente`
> (`workflow/asistente.md`, HUB-F273 a HUB-F279) y aquí solo se enlaza. Escrito contra
> `origin/develop` del hub (05/10/2026). Código: `apps/web/src/components/AssistantDrawer.vue`,
> `apps/web/src/lib/assistant*.ts`, `lib/shell.ts`, `lib/user-switch.ts`, `lib/session.ts`.
> Un dato que conviene tener presente: el asistente **no** lee la documentación (`docs/`) de los
> módulos; solo las descripciones de las consultas y órdenes que cada módulo expone para elegir
> herramientas (HUB-F276). Por eso este panel no cita documentación como fuente de nada.

## Flujos

### HUB_SHELL-F185 Abrir y cerrar el panel del asistente
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Con la sesión abierta, pulsa el icono de destellos «Asistente» de la barra superior. En una pantalla estrecha el mismo botón está dentro de «Más opciones», con el mismo nombre. Volver a pulsarlo lo cierra.
2. El panel entra por la derecha. En móvil (menos de 768 px) cubre la pantalla y deja detrás un velo oscuro. En tableta y escritorio ocupa entre 360 y 420 px de ancho y empuja el contenido hacia la izquierda: se puede seguir trabajando en la pantalla con el panel abierto.
3. Se cierra con la × de la cabecera («Cerrar»), pulsando el velo (solo móvil), volviendo a pulsar el icono de la barra, o al pulsar «Ir a …» en una respuesta (HUB_SHELL-F189).
4. Si se deja abierto, sigue abierto al cambiar de pantalla y al recargar la página: el navegador recuerda solo «abierto» o «cerrado».
Entra: la sesión; el recordatorio local de abierto/cerrado (`erplora.assistant.open`).
Sale: al abrirlo, el panel pide el plan del asistente (HUB_SHELL-F197) y la lista de puesta en marcha (HUB_SHELL-F196); cerrarlo no pide nada.
Si falla: no hay fallo propio. El botón no existe en las pantallas sin sesión (entrada, activación). La capacidad nunca se apaga: el botón se muestra siempre que haya sesión, también a un hub sin plan de asistente o con el servicio caído (nada llama a la función que lo ocultaría). Cerrar el panel no detiene una respuesta que ya viene de camino: sigue escribiéndose en segundo plano y, si pide confirmación, la tarjeta sale igualmente encima de la pantalla que haya (HUB_SHELL-F186, HUB_SHELL-F190).
Implicados: ninguno
QA: qa-hub-assistant §1 (el banco, punto 1)

### HUB_SHELL-F186 Preguntar al asistente y leer cómo escribe
Estado: parcial — «Detener» antes de que llegue el primer texto deja una burbuja vacía con los tres puntos animados para siempre (y así queda guardada); en un teclado de móvil sin tecla Mayús no se puede escribir un salto de línea, y el panel no se cierra con Esc (no hay manejador de esa tecla)
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Con la conversación vacía, el panel enseña los destellos, la frase «Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.» y los atajos «¿Qué falta por configurar?» y, por cada paso pendiente que le toque a esta persona (hasta cuatro), «¿Cómo configuro …?» (HUB_SHELL-F196).
2. Escribe en «Escribe un mensaje…» y pulsa Enter o el botón «Enviar». Mayús+Enter salta de línea. El botón no se activa con el cuadro vacío y sin adjuntos.
3. Su mensaje sale a la derecha tal cual lo escribió. Debajo aparece la burbuja del asistente con tres puntos animados hasta que llega el primer texto.
4. Mientras el asistente responde, el cuadro, «Adjuntar archivo» y «Dictar por voz» quedan desactivados y «Enviar» se convierte en «Detener». El texto va apareciendo y la lista se desplaza sola hasta abajo.
5. Al terminar, el cuadro vuelve a estar activo. Si el asistente acaba sin decir nada, la burbuja dice «(sin respuesta)».
6. «Detener» corta lo que falte; lo ya escrito se queda.
Entra: lo que la persona escribe; toda la conversación de la sesión viaja en cada pregunta (HUB_SHELL-F195).
Sale: pide la respuesta al servidor (HUB-F273), que la reenvía y la mide; el panel no guarda nada fuera del navegador.
Si falla: sin conexión, servicio caído o sin mensajes: HUB_SHELL-F199 y HUB_SHELL-F197. Pulsar «Detener» no deshace una orden que ya estaba ejecutándose.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F273 (conversar con el asistente: el servidor que contesta lo que este panel pregunta)
QA: qa-hub-assistant §1 (el banco), qa-hub-assistant §R0

### HUB_SHELL-F187 Adjuntar un archivo o dictar por voz
Estado: parcial — la burbuja de una imagen enviada la rotula «image» (inglés, sin traducir); los adjuntos (hasta 8 MB cada uno, en base64) se vuelven a enviar en cada pregunta siguiente y llenan el almacenamiento donde se guarda la conversación; el micrófono se enseña aunque el aparato no pueda grabar, y solo avisa al pulsarlo
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Para adjuntar, pulsa «Adjuntar archivo» y elige uno o varios: imágenes, PDF, .doc, .docx, .txt, .csv o .md. Cada uno aparece en una bandeja sobre el cuadro con su nombre (una imagen, «imagen») y una × («Quitar adjunto»).
2. Se envían con el siguiente mensaje, con o sin texto. En la burbuja de la persona quedan como fichas con el nombre.
3. Para dictar, pulsa «Dictar por voz». El navegador pide permiso del micrófono. Mientras graba, el botón se pone rojo y se llama «Detener la grabación».
4. Al parar, un indicador gira mientras se transcribe y el texto cae en el cuadro (detrás de lo que ya hubiera). **No se envía solo**: la persona lo revisa y pulsa «Enviar».
Entra: el archivo elegido o el audio grabado (máximo 2 MB).
Sale: el archivo viaja con la pregunta y lo lee el servicio del asistente (HUB-F273); el audio va a la transcripción del SaaS, nunca a un modelo desde el hub.
Si falla: un archivo de más de 8 MB: «El archivo es demasiado grande.» durante 4 segundos y no se adjunta. Micrófono denegado: «El acceso al micrófono está denegado. Permítelo en tu navegador para dictar.»; aparato sin grabación: «Este navegador no puede grabar audio.»; audio de más de 2 MB o transcripción rota: «No se ha podido transcribir el audio.» (el mismo texto para las dos causas).
Implicados: pendiente
Pendiente de enlazar: saas — asistente: lectura de documentos adjuntos y transcripción de voz (`apps/speech`)
QA: qa-hub-assistant §R5

### HUB_SHELL-F188 Leer la respuesta: texto, listas, tablas y enlaces
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. La respuesta del asistente se pinta con formato: negrita, cursiva, código en línea, encabezados, listas con viñetas o numeradas y tablas.
2. Una tabla se desplaza hacia los lados dentro de su propio recuadro: a 390 px el panel no se mueve.
3. Un enlace escrito como `[texto](/ruta)` se lee por su texto, sin corchetes ni dirección. Solo se puede pulsar si lleva a una pantalla de este hub (HUB_SHELL-F189); cualquier otra dirección, externa o inventada, se ve como texto y no lleva a ninguna parte.
4. Lo que el panel no entiende (bloques de código con vallas, imágenes, citas) se queda como texto corriente.
5. El mensaje de la persona sale siempre tal cual lo escribió.
Entra: el texto que escribe el modelo.
Sale: nada; es solo presentación. El panel nunca interpreta HTML de la respuesta.
Si falla: una respuesta mal formateada se lee como texto; nunca se descarta ni rompe el panel.
Implicados: ninguno
QA: qa-hub-assistant §R0

### HUB_SHELL-F189 Ir a una pantalla desde una respuesta
Estado: parcial — el panel solo ofrece botón o enlace para siete familias de pantalla; Archivos, Perfil y la documentación de la API se pueden nombrar en una respuesta y comprobar, pero nunca salen como botón
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Si la respuesta nombra una pantalla de este hub, aparece bajo la burbuja un botón «Ir a {nombre}» (hasta cuatro por mensaje, sin repetir) y la propia mención se vuelve enlace.
2. Las pantallas a las que puede llevar son: una app (`/m/<app>`), una pestaña de una app (`/m/<app>/<pestaña>`), Inicio, Empleados, Ajustes (con o sin ancla, p. ej. `/settings#data`), Apps, Sistema y Mi plan.
3. El botón usa el nombre que la persona ya ve en el menú: «Inicio», «Empleados», «Ajustes», «Apps», «Sistema», «Mi plan», y para una app «Nombre de la app › Pestaña» (la pestaña de ajustes de una app se llama «Ajustes»). Nunca el identificador interno.
4. Al pulsarlo se abre esa pantalla y el panel se cierra para que se vea.
Entra: las rutas que el modelo escribió en el texto; el mapa real de pantallas del hub y de las apps instaladas.
Sale: la navegación dentro del hub; no se pide nada al servidor.
Si falla: una pantalla que este hub no sirve (una app que no está instalada, una ruta inventada) no se convierte en botón ni en enlace, y la respuesta lleva el aviso de HUB_SHELL-F192. Si la pantalla existe pero la persona no tiene permiso para verla, el panel no lo comprueba: la pantalla de destino es quien decide (sin confirmar qué ve).
Implicados: ninguno
QA: qa-hub-assistant §R1 (el «Ir a…» lleva al registro), qa-hub-assistant §R3

### HUB_SHELL-F190 Confirmar una acción antes de que se ejecute
Estado: parcial — la tarjeta enseña los nombres técnicos de los datos («price_cents: 15,00 €»), no dice de qué app viene la acción, y una acción del núcleo (instalar una app, aplicar una plantilla) o de una app instalada hace un momento sale como «Una acción que esta app no sabe nombrar»; además las líneas de la tarjeta se pasan al aviso como saltos de línea que el aviso de Ionic probablemente junta en un solo párrafo (sin ver en pantalla)
Actor: administrador, responsable, empleado, cajero
Pantalla: Tarjeta de confirmación del asistente
Pasos:
1. La persona le pide algo que cambia datos («crea el servicio Corte caballero a 15 € de 30 min», «instala la app de citas»).
2. Antes de ejecutar, aparece un aviso encima de todo: «El asistente quiere ejecutar una acción». Debajo, la acción con el nombre que le da la propia app (p. ej. «Anular una venta») o, si la app no sabe nombrarla, «Una acción que esta app no sabe nombrar». Nunca el nombre interno de la orden.
3. El cuerpo lista cada dato que el asistente va a mandar, uno por línea y siempre en el mismo orden (alfabético por nombre del dato). Los importes que el servidor marca como dinero salen en euros («15,00 €», no «1500»); un sí/no sale «Sí»/«No», un dato vacío «—» y un dato compuesto como texto compacto.
4. «Ejecutar» lanza la orden con la sesión de quien preguntó (HUB_SHELL-F193). «Cancelar», cerrar tocando fuera o recargar la página no ejecutan nada: el asistente recibe «no confirmado» y se lo dice a la persona.
5. Las consultas que solo leen no piden tarjeta («¿qué huecos libres hay?»). Cualquier otra orden la pide, también una que el módulo publique como orden aunque solo conteste, salvo que el servidor la marque expresamente como lectura (HUB-F274); ante cualquier duda, hay tarjeta.
6. Mientras la tarjeta está abierta, el resto del panel no se puede usar. Cada orden de la misma respuesta pide la suya.
Entra: la orden, sus datos y las marcas que manda el servidor (riesgo, qué datos son dinero, si solo lee); los nombres de acción que cada app trae en su traducción.
Sale: si se acepta, la orden se ejecuta por la misma puerta y con el mismo permiso que el botón de la pantalla, revisado otra vez en el servidor (HUB-F274). El panel no pregunta ni guarda nada más.
Si falla: sin función de confirmar, el panel cancela toda orden (nunca se muta en silencio). Una orden que el servidor rechaza vuelve al asistente como error y es él quien lo cuenta (HUB_SHELL-F192). Las acciones de una app instalada durante esta misma sesión (por ejemplo, por el propio asistente) no tienen nombre hasta recargar: la lista de nombres se carga una vez, al montar el shell.
Implicados: FLOWS-F26
Pendiente de enlazar: hub — HUB-F274 (qué herramientas se ofrecen, y las marcas de riesgo y de solo lectura que decide esta tarjeta)
Pendiente de enlazar: hub — HUB, módulos y órdenes (la misma puerta de órdenes que usa el botón de la pantalla)
QA: qa-hub-assistant §R1, qa-hub-assistant §R3 (punto 4)

### HUB_SHELL-F191 Acciones peligrosas: escribir para confirmar, o no desde el chat
Estado: parcial — si lo que se escribe no coincide, la acción se cancela sin decir por qué; la frase dice «no se puede deshacer desde la pantalla», que confunde porque se está en el chat; y solo funciona para las órdenes cuya app declara el riesgo (una app que no lo declara se trata como orden corriente)
Actor: administrador, responsable, empleado, cajero
Pantalla: Tarjeta de confirmación del asistente
Pasos:
1. Una orden que su app declara destructiva no se confirma con un clic: el aviso pide escribir una palabra. Dice «Esto no se puede deshacer desde la pantalla. Escribe BORRAR para confirmar.» y el cuadro lleva «BORRAR» como pista.
2. Una orden que borra muchos registros a la vez enseña primero cuántos: «Vas a borrar 12 registros.» (o «1 registro»), y pide escribir **ese número**, no una palabra: obliga a leer la frase donde está la cifra.
3. El número lo saca el panel de la lista más larga que trae la propia orden. Si la orden no nombra los registros (un «todas», un filtro) o la lista está vacía, no se ejecuta desde el chat: el aviso dice «No puedo saber cuántos registros borraría esto, así que no lo hago desde aquí. Abre la pantalla, donde puedes verlos.» y solo ofrece «Cancelar».
4. Solo se ejecuta si lo escrito coincide exactamente (sin contar espacios) y se pulsa «Ejecutar». En cualquier otro caso, nada.
Entra: el riesgo que declara la app (`corriente`, `destructiva`, `masiva`) y los datos de la orden.
Sale: si se acepta, lo mismo que HUB_SHELL-F190. El panel no sabe qué es una cita o una factura: solo aplica la política.
Si falla: un aviso con la palabra equivocada no ejecuta nada y el asistente lo cuenta como cancelado. Las acciones destructivas del propio hub (desinstalar, reiniciar, borrar datos) no se ofrecen nunca, así que no llegan a esta tarjeta (HUB-F274); las órdenes de borrar de una app sí llegan.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F274 (declarar el riesgo y qué órdenes se ofrecen; un riesgo desconocido llega como destructivo)
QA: qa-hub-assistant §R3 (puntos 3 y 4)

### HUB_SHELL-F192 Comprobar lo que dice el asistente contra lo que de verdad hizo
Estado: parcial — el panel no enseña ningún recibo de lo ejecutado ni distingue «el servidor respondió bien» de «cambió algo»: una orden que contesta sin error cuenta como hecha aunque no haya tocado ninguna fila, y una sola orden correcta del turno basta para que ninguna otra afirmación del mismo turno se marque; tampoco se enseña de dónde sale una cifra
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Al acabar cada respuesta, el panel la compara con lo que se ejecutó en ese turno. No se fía de lo que la respuesta dice de sí misma.
2. Si la respuesta afirma un cambio («he creado…», «se ha actualizado…», «queda guardado», «has been created…») y en el turno no se ejecutó ninguna orden que cambie datos, o la persona la canceló, o falló, aparece **fuera de la burbuja** el aviso «El asistente ha dicho que hizo un cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.»
3. Si la respuesta escribe un identificador (un código largo) que ninguna consulta de ese turno devolvió y que la persona tampoco escribió: «Esta respuesta muestra un identificador que el asistente no ha leído de verdad. No te fíes de él.»
4. Si nombra una pantalla que este hub no sirve: «Esta respuesta señala una pantalla que no existe aquí.» y no se ofrece botón (HUB_SHELL-F189).
5. Los avisos van con un icono de alerta, no los escribe el modelo y se quedan con ese mensaje, también tras recargar. Una respuesta limpia no lleva nada.
6. Tras una orden aceptada, lo único que la persona ve es lo que el asistente cuente con sus palabras y, para comprobarlo, el «Ir a …» a la pantalla del registro.
Entra: las órdenes del turno con su desenlace (hecha, error o cancelada) y sus resultados; el mapa real de pantallas.
Sale: el aviso sobre el mensaje; nada se manda al servidor. Aplicar una plantilla devuelve además al asistente lo que sigue sin hacer (qué pasos de la puesta en marcha siguen bloqueando), para que no diga que ya se puede facturar.
Si falla: «hecha» significa que la puerta de órdenes no devolvió error y la persona aprobó la tarjeta. Una orden de una app que no comprueba cuántas filas tocó responde bien sin haber hecho nada (doble apertura de caja, doble cierre) y el asistente puede contar que sí; igualmente, un lote que pone a cero lo que no se le nombró devuelve éxito. Ese filtro no lo hace este panel: lo tiene que hacer la orden del servidor (HUB, módulos y órdenes).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F273 (los recibos del turno: el panel los construye de lo que ejecuta; el servidor no los guarda)
Pendiente de enlazar: hub — HUB, módulos y órdenes (que una orden diga cuántas filas cambió; hoy una orden sin esa comprobación contesta bien sin hacer nada)
QA: qa-hub-assistant §R0, qa-hub-assistant §R2, qa-hub-assistant §R4

### HUB_SHELL-F193 Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable
Estado: parcial — el panel no muestra nada propio cuando falta un permiso: lo cuenta el modelo con el error que reciba, sin texto fijo; y que la ventana del PIN se abra también cuando la orden viene del asistente la hace el transporte común y ningún test del asistente la ejercita
Actor: empleado, cajero, responsable, administrador
Pantalla: Asistente
Pasos:
1. El asistente trabaja con la sesión de quien está delante: ve y hace lo que esa persona vería y haría con los botones, nada más. Una persona sin permiso para una orden no la tiene entre las herramientas del asistente: es como si no existiera, y así lo dice.
2. Si una orden pide un permiso que la persona no tiene pero sí el perfil responsable, al pulsar «Ejecutar» aparece la ventana «Hace falta una aprobación» con «Se aprueba: {acción}». Un responsable elige su nombre y teclea su PIN o pasa su placa. Si lo aprueba, la orden sigue y queda anotado quién la aprobó.
3. Si cancela o el PIN no vale, la orden no se ejecuta, el asistente recibe el error y se lo explica a la persona. Si hay ya una ventana de aprobación abierta, una segunda petición se rechaza sin cola.
4. Instalar una app y aplicar una plantilla solo se ofrecen a quien administra (HUB-F274); el panel no vuelve a comprobarlo, lo revisa el servidor cada vez.
5. Lo que el asistente trae de vuelta (listas, cifras) es lo que esa sesión puede leer: el panel no filtra nada por su cuenta.
Entra: la sesión local de quien pregunta, que es la que firma cada orden.
Sale: la orden ejecutada con el empleado como autor y, si hubo PIN, el responsable como aprobador (HUB-F152).
Si falla: sin permiso y sin aprobación posible, el asistente recibe el rechazo del servidor (HUB-F151) y lo explica con sus palabras; en la ventana del PIN, los textos son los de esa ventana («Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.»). Una acción del núcleo no tiene nombre en esa ventana: sale «una acción que esta app no sabe nombrar».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F274 (qué herramientas se ofrecen a cada perfil)
Pendiente de enlazar: hub — HUB-F05 (pedir la aprobación de un responsable cuando falta el permiso)
Pendiente de enlazar: hub — HUB-F151 (rechazar una orden para la que no se tiene permiso)
Pendiente de enlazar: hub — HUB-F152 (aprobar una acción con el PIN de un responsable)
QA: qa-hub-assistant §R3 (puntos 5 y 9)

### HUB_SHELL-F194 Pedirle varias cosas seguidas
Estado: parcial — no hay vista previa del plan entero ni «cancelar todo»; al pasar de 6 rondas de herramientas el turno se corta sin aviso si ya había texto, o con «No se pudo contactar con el asistente.» (que es falso) si no lo había; no hay deshacer de lo ya ejecutado
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. La persona pide una cadena («crea la categoría Bebidas, el producto Caña a 2,50 y 20 unidades de stock»).
2. El asistente la resuelve por rondas: lee lo que necesita (sin tarjeta), pide una orden, el panel la ejecuta y se la devuelve, y sigue. El texto de todas las rondas va a la misma burbuja.
3. Cada orden que cambia datos pide su propia tarjeta (HUB_SHELL-F190), una detrás de otra. Aprobar la primera no aprueba las siguientes.
4. Si la persona cancela una, el asistente lo sabe y decide cómo seguir (puede insistir con otra). Lo que ya se ejecutó se queda ejecutado.
5. El turno admite como máximo 6 rondas de herramientas; es un tope contra bucles, no una cuota.
Entra: la petición; cada resultado de orden, que vuelve al asistente.
Sale: tantas órdenes como tarjetas aprobadas, cada una en su app (HUB-F273, HUB-F274).
Si falla: si falla una orden a mitad, el asistente la recibe como error y debe contarlo; las anteriores no se deshacen. Con la red cortada a mitad se aplica HUB_SHELL-F199; pasada la sexta ronda, lo dicho arriba.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F273 (el bucle de herramientas; el SaaS manda como mucho una herramienta por respuesta)
QA: qa-hub-assistant §R4

### HUB_SHELL-F195 La conversación: qué se guarda, dónde y cuándo se borra
Estado: parcial — no hay «nueva conversación»: el hilo crece sin límite, se reenvía entero en cada pregunta y, si el servicio lo rechaza por demasiado grande, la persona solo sale cerrando sesión o cambiando de usuario; si el navegador no deja guardar (un adjunto grande), el hilo sigue en memoria pero no sobrevive a una recarga
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. El hilo vive solo en el navegador de esa pestaña (`sessionStorage`, clave `erplora.assistant.history`): ni el hub ni erplora.com guardan la conversación. Se guarda al enviar y al terminar cada respuesta.
2. Recargar la página lo recupera. Cerrar la pestaña o la ventana lo pierde. Cerrar el panel no lo borra.
3. Se vacía del todo, y con él cualquier respuesta que estuviera llegando (que se corta y libera el cuadro), cuando: la persona cierra sesión; la sesión caduca o se pierde por inactividad o por abrirse en otro dispositivo; o **cambia de usuario con PIN** en la misma caja, en cuanto el PIN nuevo es aceptado. La persona que llega abre el panel y lo encuentra vacío.
4. Si el PIN del cambio de usuario se rechaza, no se borra nada: quien estaba sigue dentro con su hilo.
5. Lo que se guarda: lo que escribió la persona (con sus adjuntos), lo que respondió el asistente y los avisos de comprobación. No se guardan las órdenes ejecutadas ni lo que enseñó la tarjeta.
6. Para empezar de cero sin salir, hoy no hay botón.
Entra: los mensajes del panel; los cierres de sesión y los relevos de usuario.
Sale: la clave del navegador; en cada pregunta, el hilo entero va al servidor (HUB-F273) y se olvida al acabar el turno.
Si falla: un almacenamiento lleno o bloqueado (modo privado) se ignora en silencio. Un hilo guardado ilegible arranca vacío.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F273 (el hub no guarda la conversación)
Pendiente de enlazar: hub — HUB-F136 y HUB-F138 (cerrar sesión y cambiar de usuario, que disparan el borrado; HUB-F138 dice hoy que el historial sigue en pantalla, y no es lo que hace el código)
QA: qa-hub-assistant §Pendiente (fase C) (cambio de usuario por PIN), qa-hub-restaurant §7.02

### HUB_SHELL-F196 El asistente en la puesta en marcha
Estado: hecho
Actor: administrador, responsable
Pantalla: Asistente
Pasos:
1. En Inicio, la tarjeta «Termina de configurar tu negocio» lleva el botón «Pedírselo al asistente». Abre el panel con el texto «Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.».
2. Abierto desde la barra superior también se ofrecen los atajos: «¿Qué falta por configurar?» y, por cada paso pendiente que le toque a esta persona (hasta cuatro), «¿Cómo configuro {el paso, con el mismo nombre que en la tarjeta}?». Los pasos que no puede hacer esa sesión (los que solo desbloquea un administrador) y los «Todavía no disponible» nunca se ofrecen como atajo.
3. Pulsar un atajo escribe la pregunta y la envía en el acto. La conversación se abre ya sobre ese paso.
4. Antes de cada pregunta del panel de configuración, el panel vuelve a leer el estado de la lista y se lo da al asistente como contexto que la persona no ve: lo pendiente, lo que bloquea facturar, lo que ya está hecho y lo que le toca a otro. Así, un negocio que se configura a mitad de la charla deja de ser descrito como sin configurar.
5. Si pide aplicar una plantilla de sector o instalar una app, pasa por la tarjeta (HUB_SHELL-F190). Al terminar de aplicar una plantilla, el shell pregunta en pantalla los permisos de las apps que ha traído, no el modelo.
Entra: el estado de la lista de puesta en marcha, filtrado por país y por permiso (HUB-F35); lo que la persona escribe.
Sale: el contexto de configuración, solo para el modelo; la conversación normal.
Si falla: si no se puede leer el estado, el contexto dice que no se pudo y el asistente no afirma que el negocio esté configurado; los atajos se reducen a «¿Qué falta por configurar?». La tarjeta de Inicio conserva «Configurar» en cada paso, así que un asistente caído no deja a nadie sin salida.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F35 (calcular la lista de puesta en marcha que el asistente lee)
QA: qa-hub-assistant §R0 (pregunta 4), qa-hub-assistant §R4 (montar el hub por chat)

### HUB_SHELL-F197 Ver el plan del asistente, el límite de uso y ampliarlo
Estado: parcial — el aviso de cuota, una vez agotada, se queda pegado al último mensaje del hilo para siempre (también tras renovarse o tras ampliar el plan, y le saldría a la persona que llega tras un cambio de usuario); el plan se escribe con su identificador interno («Plan basic»); el texto para quien no puede pagar manda a «el responsable del negocio», pero solo pagan el propietario y el administrador
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Al abrir el panel se lee el plan del asistente de este negocio (una vez por apertura). Si no se puede leer, no se enseña nada: nunca un número inventado.
2. Desde el 80 % de los mensajes del mes, el pie dice «Plan {plan} — te quedan {n} de {total} mensajes este mes.», con «Se renuevan el {fecha}.» y, cuando el nivel viene del plan del negocio, «Incluido en tu plan {nombre}.». Por debajo del 80 % no se enseña nada.
3. El contador se mueve al terminar cada respuesta, sin recargar.
4. Al agotarse, la respuesta es «Has usado todos tus mensajes del asistente Plan {plan} — {usados} de {total} mensajes este mes. Se renuevan el {fecha}.» (no «No se pudo contactar»), y debajo lo que toca a esa persona.
5. Un administrador o propietario, cuando el nivel lo da el plan del negocio, ve «Incluido en tu plan {nombre}.» y el botón «Subir de plan», que abre la página del plan de su cuenta en el navegador (la misma puerta que el menú «Mi plan»).
6. Si el nivel viene de una compra propia del asistente, ve «Ver planes»: con un solo plan contratable va directo al pago; con varios, una hoja «Elige un plan» con «{nombre} — {precio} €/mes» y «Ir al pago». El pago se abre fuera de la caja, y al volver se relee el plan.
7. En la copia de la app instalada desde Google Play no hay botón de pago: «El plan del asistente se amplía desde tu cuenta de ERPlora, en erplora.com.»
8. Quien no administra ve «Pídele al responsable del negocio que amplíe el plan del asistente.» y ningún botón.
Entra: nivel, mensajes usados, límite y fecha de renovación que da el SaaS; planes contratables.
Sale: la dirección de pago o de la página de plan se abre en el navegador (HUB-F277); el panel no cobra nada ni lleva contador propio.
Si falla: sin planes contratables, «Ahora mismo no hay planes a los que ampliar.»; sin dirección de pago, «No se pudo contactar con el asistente.» (texto que no corresponde); si el navegador no abre: «No se pudo abrir la página de pago en el navegador. Inténtalo de nuevo y, si sigue fallando, actualiza la app de ERPlora.» o, para el plan, «No se pudo abrir la página de tu plan en el navegador. Inténtalo de nuevo.»
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F277 (ver el plan del asistente y lo que queda del mes)
Pendiente de enlazar: saas — asistente: nivel y consumo, y planes contratables
QA: qa-hub-assistant §R4 (el 429), qa-hub-assistant §0 (la cuota del banco)

### HUB_SHELL-F198 Informar de una respuesta mala
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Bajo cada respuesta ya terminada aparece «Denunciar un problema». No aparece en la burbuja que aún se está escribiendo.
2. Se abre «Denunciar esta respuesta»: «Si esta respuesta del asistente te parece inapropiada o dañina, envíanosla y la revisaremos.», con un cuadro «Comentario (opcional)».
3. «Denunciar» la envía junto con la pregunta que la provocó; «Cancelar» no manda nada.
4. Aviso «Gracias, hemos recibido tu denuncia.»
Entra: el texto de la respuesta, la pregunta anterior y el comentario.
Sale: la denuncia al hub, que la deja en su registro de errores para revisión (HUB-F278). Cualquier perfil puede denunciar. El panel no pide motivo, aunque el servidor lo admita, ni ofrece 👍 o 👎.
Si falla: «No se pudo enviar la denuncia. Inténtalo de nuevo.» y el botón sigue ahí. El botón sale también bajo los mensajes que escribe el propio panel («No se pudo contactar…», «(sin respuesta)»), que no son de ningún modelo.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F278 (denunciar una respuesta del asistente: el registro que guarda lo que este botón manda)
QA: qa-hub-assistant §Pendiente (fase C) («Report an issue»)

### HUB_SHELL-F199 El asistente sin conexión, con el servicio caído o sin plan
Estado: parcial — el panel no desactiva ni avisa de que no hay red antes de enviar; no hay «Reintentar»; si el corte llega con parte del texto ya escrito se queda la respuesta a medias sin ningún aviso; una sesión caducada durante la charla se lee como «no se pudo contactar» en vez de llevar a la entrada; los fallos permanentes (el servicio sin credencial, sin plan, el hilo demasiado grande) dicen «vuelve a intentarlo en unos minutos»
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Sin Internet en el aparato, el aviso general de conexión de la barra del shell aparece, pero el panel sigue abierto y se puede escribir. Al enviar, la burbuja del asistente dice «No se pudo contactar con el asistente.»
2. Con Internet pero sin llegar a erplora.com (el hub lo avisa así), el mensaje es el mismo.
3. Si erplora.com contesta que no atiende (proveedor sin credencial, sin modelo, negocio sin nivel, petición demasiado grande), el mensaje es otro: «El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos minutos.» El panel distingue las dos cosas por quién emite el fallo, no por su texto.
4. Quedarse sin mensajes del mes no es una avería: HUB_SHELL-F197.
5. En todos los casos el cuadro vuelve a estar activo y la pregunta queda en el hilo; para repetirla hay que escribirla o enviar otra.
Entra: el desenlace de la petición del panel al hub.
Sale: solo texto en el hilo (también queda guardado, y viaja al asistente en la siguiente pregunta como si lo hubiera dicho él).
Si falla: un hub que no responde lo cuenta el aviso general de la barra (área de acceso y navegación), no este panel. El botón de HUB_SHELL-F198 aparece también bajo estos mensajes aunque no sean del modelo.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F273 (los fallos del servicio llegan con un código: `cloud_unreachable`, cupo agotado, proveedor sin credencial)
Pendiente de enlazar: hub — HUB-F277 (nivel y consumo)
QA: qa-hub-assistant §R4 (negativos de cadena), qa-hub-assistant §R6

## Cobertura contra la referencia

Referencia: los asistentes dentro del producto que operan un ERP/TPV por lenguaje natural (Business
Central Copilot, Odoo AI, SAP Joule, Shopify Sidekick, Square AI, Toast IQ), tal como las contrasta
`qa-hub-assistant` («El mercado decide»): entender, pedir lo que falta, previsualizar, confirmar,
ejecutar, confirmar con el dato real, ofrecer el «ir a…», y si no puede decir dónde se hace a mano.

| Elemento | Estado | Flujo |
|---|---|---|
| Panel persistente que no tapa el trabajo (tableta y escritorio) | hecho | HUB_SHELL-F185 |
| Conversación con memoria dentro de la sesión | hecho | HUB_SHELL-F195 |
| Empezar una conversación nueva sin cerrar sesión | no hecho | HUB_SHELL-F195 |
| Historial entre sesiones y dispositivos (Sidekick lo guarda) | no hecho (decisión: la conversación vive solo en el navegador, ADR-0149) | HUB_SHELL-F195 |
| Respuesta con tablas, listas y enlaces a pantallas | hecho | HUB_SHELL-F188, HUB_SHELL-F189 |
| Previsualizar lo que va a hacer antes de ejecutar | parcial: lista de datos, sin el valor anterior ni el efecto | HUB_SHELL-F190 |
| Previsualizar un plan entero de varios pasos | no hecho | HUB_SHELL-F194 |
| Confirmación antes de cada cambio | hecho | HUB_SHELL-F190 |
| Fricción según el daño (clic, escribir, no desde el chat) | hecho | HUB_SHELL-F191 |
| Confirmar el resultado con el dato real (número, importe) | parcial: depende de lo que cuente el modelo; el panel no pinta un recibo | HUB_SHELL-F192 |
| Marca de «hecho» que distinga ejecutado de «respondió bien» | no hecho | HUB_SHELL-F192 |
| «Ir a…» a la pantalla del registro | hecho | HUB_SHELL-F189 |
| Deshacer lo hecho por el asistente | no hecho | HUB_SHELL-F194 |
| Mismo permiso que el botón; el asistente no puede más | hecho | HUB_SHELL-F193 |
| Aprobación de un responsable (PIN) cuando falta el permiso | parcial: la ventana es la común, sin prueba del camino del asistente | HUB_SHELL-F193 |
| Aviso cuando la respuesta afirma algo que no pasó | hecho | HUB_SHELL-F192 |
| Citar de dónde sale cada cifra (registro, enlace) | no hecho | HUB_SHELL-F192 |
| Adjuntar fotos y documentos; dictado que no se envía solo | parcial | HUB_SHELL-F187 |
| Puesta en marcha guiada y leyendo el estado real | hecho | HUB_SHELL-F196 |
| Cuota visible antes de agotarse y salida al plan | parcial | HUB_SHELL-F197 |
| Denunciar una respuesta | hecho | HUB_SHELL-F198 |
| Valorar con 👍/👎 | no hecho | HUB_SHELL-F198 |
| Estado sin conexión / servicio caído / sin plan, con salida | parcial | HUB_SHELL-F199 |

### Lo que garantiza el panel para las acciones que hoy solo se hacen con el asistente

Los documentos de los módulos marcan con `Pantalla: asistente` lo que hoy no tiene botón (altas en
lote de servicios, mesas o bloqueos de agenda; cambiar notas de una cita; borrar una comanda o una
reserva; ajustar las reglas de reserva; los bonos…). Para todas, sin excepción por módulo, esto es lo
que el panel garantiza y lo que no:

| Garantía | Estado | Flujo |
|---|---|---|
| Se pide confirmación siempre que la orden cambie datos o dude de si los cambia | hecho | HUB_SHELL-F190 |
| La tarjeta enseña los datos que se van a mandar, con el dinero en euros | hecho | HUB_SHELL-F190 |
| La tarjeta enseña qué cambia de lo que ya hay (valor anterior → nuevo) | no hecho | HUB_SHELL-F190 |
| La tarjeta del alta en lote cuenta cuántas filas son | no hecho (solo cuenta para los borrados masivos) | HUB_SHELL-F191 |
| Borrar con riesgo declarado pide escribir; masivo pide escribir el número | hecho | HUB_SHELL-F191 |
| Una app que no declara el riesgo de su borrado se confirma con un clic | parcial | HUB_SHELL-F191 |
| El panel distingue «hecho» de «el servidor respondió bien» | no hecho | HUB_SHELL-F192 |
| Un rechazo del servidor llega a la persona con palabras del modelo, sin texto fijo | parcial | HUB_SHELL-F192, HUB_SHELL-F193 |
| Quien no tiene permiso no ve la herramienta | hecho (lo decide el servidor) | HUB_SHELL-F193 |

## Datos: de quién es cada dato

El panel no es dueño de ningún dato de negocio. Lo que guarda es solo del navegador de esa persona:

| Dato | Dónde | De quién | Cuándo se borra |
|---|---|---|---|
| La conversación (texto, adjuntos en base64, avisos de comprobación, identificador de cada respuesta) | `sessionStorage`, clave `erplora.assistant.history`, por pestaña | de la persona que la escribió | cerrar sesión, caducar la sesión, cambiar de usuario con PIN aceptado, cerrar la pestaña |
| Si el panel está abierto | `localStorage`, clave `erplora.assistant.open` | del aparato | nunca; no distingue personas |
| Qué quiere ver el panel al abrirse (la puesta en marcha) | memoria de la pantalla | de la sesión | al enviar la primera pregunta |
| Plan y consumo del mes | memoria de la pantalla; la verdad es del SaaS | del negocio | al recargar |

Dato personal: el contenido de la conversación puede traer nombres de clientes, importes y
documentos adjuntos (un albarán, un CSV de clientes). Sale del aparato en cada pregunta hacia el hub y
de ahí al proveedor del modelo a través del SaaS; la denuncia manda al registro del hub el texto de una
respuesta y de la pregunta (HUB-F278). El panel no guarda nada de eso en el servidor.

## Reglas que no se rompen

- **Ninguna orden que cambie datos se ejecuta sin que la persona la apruebe**: si el panel no tiene
  forma de preguntar, cancela; solo una marca de «solo lee» literalmente verdadera salta la tarjeta.
- **El asistente no tiene más permiso que quien pregunta**: ejecuta con la sesión local y por la misma
  puerta que el botón; el servidor lo vuelve a revisar en cada orden.
- **Un borrado masivo que no dice cuántos registros afecta no se hace desde el chat.**
- **Una dirección que escribe el modelo no saca a la persona del hub**: solo se sigue una pantalla de
  este hub que exista; el HTML de la respuesta no se interpreta.
- **La conversación de una persona no pasa a la siguiente en la misma caja** (cerrar sesión o cambiar
  de usuario la vacía y corta lo que esté llegando).
- **Lo dictado no se envía solo.**
- **El pago de un plan lo ofrece solo quien administra, y no en la copia de Google Play.**

## Lo que NO hace, a propósito

- No guarda la conversación fuera del navegador (ADR-0149): no hay historial entre dispositivos.
- No ejecuta acciones destructivas del propio hub (desinstalar, reiniciar, borrar datos).
- No lee la documentación de las apps; contesta con las descripciones de sus consultas y órdenes.
- No cita fuentes ni valora respuestas con 👍/👎; no deshace lo que ejecutó.
- No hace «lo mismo en lote» con una sola confirmación: cada orden pide la suya.

## Dudas abiertas

- ¿«Nueva conversación» (botón que vacía el hilo sin cerrar sesión)? Odoo, Sidekick y Joule lo traen
  y es la única salida cuando el hilo pasa del tamaño que acepta el servicio. Se resuelve con
  `market-decision`.
- ¿Un recibo por orden ejecutada en la propia burbuja («Servicio creado · Corte caballero · 15,00 €»
  con «Ir a…»), distinto del texto del modelo? Es lo que cierra la familia «contesta que sí sin
  haber hecho nada»; hoy solo lo cubre el servidor si la orden comprueba filas.
- ¿Debe una app poder dar nombre y texto propio a la tarjeta de sus órdenes más allá de la etiqueta?
- ¿Se oculta el botón del asistente en un negocio sin nivel o con el servicio sin credencial?

## Fuentes contrastadas

- `hand-book/hub/10-asistente-y-notificaciones.md` dice que el asistente se muestra solo cuando la
  capacidad está disponible: el código lo muestra siempre con sesión (`setAssistantAvailable` no la
  llama nadie). Dice también que el dictado aparece «cuando el dispositivo lo admite»: el botón se
  enseña siempre y avisa al pulsarlo.
- `hub-wf-acceso/workflow/acceso.md` (HUB-F138) escribe que el historial del asistente de quien se fue
  sigue en la pantalla tras cambiar de usuario (hub#1544); el código lo vacía en cuanto el PIN nuevo
  se acepta (`lib/user-switch.ts`, `clearAssistantHistory()`, con test `user-switch.test.ts`) y también
  en `logout()` (`lib/session.ts`). El guion de QA lo lista como pendiente («el historial no pasa al
  siguiente usuario») y el código lo cumple.
- `qa-hub-assistant` pide que la tarjeta diga «de qué app viene»: el panel calcula el nombre de la app
  pero no lo enseña (`described.app` no se usa). También espera «`MAX_TOOL_ITERS` agotado con mensaje
  humano»: el panel o calla o dice «No se pudo contactar», y «cierra el drawer a mitad ... nada se
  ejecuta»: cerrar el panel no corta el turno.
- El comentario de `AssistantDrawer.vue` dice «lo destructivo ni llega aquí: no se ofrece como tool»; es
  cierto para el hub, no para las órdenes de borrar de una app, que sí llegan (`assistant-danger.ts` es
  la política). `architecture/saas/assistant.md` describe una herramienta `search_docs` sobre la
  documentación de las apps que no existe en el hub.
- Dos textos visibles no salen de las claves de traducción: los «Sí»/«No» de la tarjeta de
  confirmación (`lib/assistant-confirm.ts`) y la ficha «image» de una imagen en la burbuja de la
  persona (`messageAttachments`). El resto del panel tiene su cadena `en` y su `es` (comprobado: las
  claves de `assistant` son las mismas en los dos idiomas).
