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

## Referencia adoptada

Los asistentes dentro de producto que operan un ERP/TPV por lenguaje natural (Business Central
Copilot, Odoo AI, SAP Joule, Shopify Sidekick, Square AI, Toast IQ), ya contrastados en
`.claude/agents/qa-hub-assistant.md` («El mercado decide»): panel persistente, previsualizar y
confirmar antes de cambiar nada, fricción según el daño (clic / escribir / no desde el chat), «ir a…»
tras la acción, «no lo sé / hazlo aquí» honesto, cuota visible, denunciar la respuesta. No se rehízo
la búsqueda de mercado.

## Antes de empezar

- Sesión abierta (el panel no existe en Acceso ni en Activación requerida).
- Para que el asistente responda: hub con credencial de máquina enrolada y nivel de asistente (el que
  da el plan del negocio, ADR-0474). Para la puesta en marcha guiada, nada más.
- Para que la tarjeta dé nombre a una acción, la app tiene que traer su traducción de órdenes (hoy
  solo Ventas).

## Flujos

### HUB_SHELL-F185 Abrir y cerrar el panel del asistente
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Con la sesión abierta, pulsa el icono de destellos «Asistente» de la barra superior. En una pantalla estrecha el mismo botón está dentro de «Más opciones», con el mismo nombre. Volver a pulsarlo lo cierra.
2. El panel entra por la derecha. En móvil (menos de 768 px) lleva velo oscuro detrás y mide hasta 420 px: en un teléfono de 420 px o menos cubre la pantalla; entre 421 y 767 px es un panel de 420 px con velo. En tableta y escritorio ocupa entre 360 y 420 px de ancho, sin velo, y empuja el contenido hacia la izquierda: se puede seguir trabajando en la pantalla con el panel abierto.
3. Se cierra con la × de la cabecera («Cerrar»), pulsando el velo (solo móvil), volviendo a pulsar el icono de la barra, o al pulsar «Ir a …» en una respuesta (HUB_SHELL-F189).
4. Si se deja abierto, sigue abierto al cambiar de pantalla y al recargar la página: el navegador recuerda solo «abierto» o «cerrado».
Entra: la sesión; el recordatorio local de abierto/cerrado (`erplora.assistant.open`).
Sale: al abrirlo, el panel pide el plan del asistente (HUB_SHELL-F197) y la lista de puesta en marcha (HUB_SHELL-F196); cerrarlo no pide nada.
Si falla: no hay fallo propio. El botón no existe en las pantallas sin sesión (entrada, activación). La capacidad nunca se apaga: el botón se muestra siempre que haya sesión, también a un hub sin plan de asistente o con el servicio caído (nada llama a la función que lo ocultaría). Cerrar el panel no detiene una respuesta que ya viene de camino: sigue escribiéndose en segundo plano y, si pide confirmación, la tarjeta sale igualmente encima de la pantalla que haya (HUB_SHELL-F186, HUB_SHELL-F190).
Implicados: ninguno
QA: qa-hub-assistant §1 (el banco, punto 1)

### HUB_SHELL-F186 Preguntar al asistente y leer cómo escribe
Estado: parcial — «Detener» antes de que llegue el primer texto deja una burbuja vacía con los tres puntos animados para siempre (y así queda guardada); recargar la página a mitad de una respuesta pierde lo ya escrito y deja la misma burbuja de puntos para siempre (el hilo solo se guarda al enviar y al terminar, detener o fallar); en un teclado de móvil sin tecla Mayús no se puede escribir un salto de línea, y el panel no se cierra con Esc (no hay manejador de esa tecla)
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
Implicados: HUB-F273
QA: qa-hub-assistant §1 (el banco), qa-hub-assistant §R0

### HUB_SHELL-F187 Adjuntar un archivo o dictar por voz
Estado: parcial — el dictado va del navegador directo a erplora.com con el pase personal de quien entró con contraseña: con una sesión de PIN, o tras cualquier cambio de usuario (que borra ese pase), siempre acaba en «No se ha podido transcribir el audio.»; el panel acepta adjuntos de 8 MB pero el hub rechaza un cuerpo de más de 2 MB, así que un adjunto de más de ~1,5 MB hace que ese turno y todos los siguientes digan «No se pudo contactar con el asistente.» (leído, sin ejecutar); la burbuja de una imagen enviada la rotula «image» (inglés, sin traducir); los adjuntos se vuelven a enviar en cada pregunta y llenan el almacenamiento de la conversación; el micrófono se enseña aunque el aparato no pueda grabar, y solo avisa al pulsarlo
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Para adjuntar, pulsa «Adjuntar archivo» y elige uno o varios: imágenes, PDF, .doc, .docx, .txt, .csv o .md. Cada uno aparece en una bandeja sobre el cuadro con su nombre (una imagen, «imagen») y una × («Quitar adjunto»).
2. Se envían con el siguiente mensaje, con o sin texto. En la burbuja de la persona quedan como fichas con el nombre.
3. Para dictar, pulsa «Dictar por voz». El navegador pide permiso del micrófono. Mientras graba, el botón se pone rojo y se llama «Detener la grabación».
4. Al parar, un indicador gira mientras se transcribe y el texto cae en el cuadro (detrás de lo que ya hubiera). **No se envía solo**: la persona lo revisa y pulsa «Enviar».
Entra: el archivo elegido (el panel deja 8 MB, pero toda la conversación tiene que caber en 2 MB al enviarse) o el audio grabado (máximo 2 MB).
Sale: el archivo viaja con la pregunta y lo lee el servicio del asistente (HUB-F273); el audio sale del navegador directo a la transcripción de erplora.com, sin pasar por el hub, con el pase de erplora.com de quien está en la caja (nunca a un modelo desde el hub).
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
Estado: parcial — la acción solo tiene nombre si su app trae la etiqueta en su traducción, y hoy solo la trae Ventas (17 de sus 31 órdenes del asistente): en las otras 26 apps y en las herramientas del núcleo la tarjeta dice «Una acción que esta app no sabe nombrar»; los datos salen con su nombre técnico («price», «service_id») y sin decir de qué app vienen; las líneas se juntan en un solo párrafo porque el aviso no lleva la clase que respeta los saltos de línea (`theme/polish.css`, `cascade-alert`); los importes en euros solo en los campos de primer nivel que el esquema marca
Actor: administrador, responsable, empleado, cajero
Pantalla: Tarjeta de confirmación del asistente
Pasos:
1. La persona le pide algo que cambia datos («crea el servicio Corte caballero a 15 € de 30 min», «instala la app de citas»).
2. Antes de ejecutar, aparece un aviso encima de todo: «El asistente quiere ejecutar una acción». Debajo, la acción con el nombre que le da la propia app (por ejemplo «Anular una venta cobrada», en Ventas) o, en casi todas las demás, «Una acción que esta app no sabe nombrar». Nunca el nombre interno de la orden.
3. El cuerpo lista cada dato que el asistente va a mandar, siempre en el mismo orden (alfabético por nombre del dato), pero en un solo párrafo. Un importe sale en la moneda del negocio («15,00 €», no «1500») solo si es un campo de primer nivel que el esquema de la orden marca como céntimos; dentro de una lista (altas en lote) se ven los céntimos en crudo. Un sí/no sale «Sí»/«No», un dato vacío «—» y un dato compuesto como texto compacto.
4. «Ejecutar» lanza la orden con la sesión de quien preguntó. «Cancelar» y cerrar tocando fuera no ejecutan nada: el asistente recibe «no confirmado» y se lo dice a la persona. Recargar la página con la tarjeta abierta mata el turno: nada se ejecuta y el asistente no recibe nada.
5. Las consultas que solo leen no piden tarjeta. Una orden pide tarjeta si el servidor la marca como orden y no como lectura; ante la duda sobre esa marca, hay tarjeta. Una llamada sin tipo (que no estuviera en las notas del turno) iría por la puerta de consultas sin tarjeta, sin poder escribir.
6. Mientras la tarjeta está abierta, el resto del panel no se puede usar. Cada orden de la misma respuesta pide la suya.
Entra: la orden, sus datos y las marcas que manda el servidor (riesgo, qué datos son dinero, si solo lee); los nombres de acción que cada app trae en su traducción (`commands.<orden>.label`).
Sale: si se acepta, la orden se ejecuta por la misma puerta y con el mismo permiso que el botón de la pantalla, revisado otra vez en el servidor (HUB-F274). El panel no pregunta ni guarda nada más. La orden de Automatizaciones que deja un borrador (FLOWS-F26) pasa por esta tarjeta y, al no traer Automatizaciones etiquetas, sale sin nombre.
Si falla: sin función de confirmar, el panel cancela toda orden (nunca se muta en silencio). Una orden que el servidor rechaza vuelve al asistente como error y es él quien lo cuenta (HUB_SHELL-F192). El nombre de las acciones de una app instalada durante esta sesión no se carga hasta recargar (la lista se carga una vez, al montar el shell).
Implicados: FLOWS-F26, HUB-F03, HUB-F273, HUB-F274
QA: qa-hub-assistant §R1, qa-hub-assistant §R3 (punto 4)

### HUB_SHELL-F191 Acciones peligrosas: escribir para confirmar, o no desde el chat
Estado: parcial — la política existe, pero solo Citas declara el riesgo de sus borrados (4 órdenes): anular una venta, borrar productos, clientes, reservas, comandas, mesas o servicios se confirma con un clic; si lo escrito no coincide, la acción se cancela sin decir por qué; la frase dice «no se puede deshacer desde la pantalla», que confunde estando en el chat
Actor: administrador, responsable, empleado, cajero
Pantalla: Tarjeta de confirmación del asistente
Pasos:
1. Una orden que su app declara destructiva no se confirma con un clic: el aviso pide escribir una palabra. Dice «Esto no se puede deshacer desde la pantalla. Escribe BORRAR para confirmar.» y el cuadro lleva «BORRAR» como pista.
2. Una orden que su app declara de borrado masivo enseña primero cuántos: «Vas a borrar 12 registros.» (o «1 registro»), y pide escribir **ese número**, no una palabra.
3. El número lo saca el panel de la lista más larga que trae la propia orden. Si la orden no nombra los registros (un «todas», un filtro) o la lista está vacía, no se ejecuta desde el chat: el aviso dice «No puedo saber cuántos registros borraría esto, así que no lo hago desde aquí. Abre la pantalla, donde puedes verlos.» y solo ofrece «Cancelar».
4. Solo se ejecuta si lo escrito coincide exactamente (distingue mayúsculas: «borrar» no vale; solo se quitan los espacios de los extremos) y se pulsa «Ejecutar». En cualquier otro caso, nada.
Entra: el riesgo que declara la app (`normal`, `destructive`, `bulk_destructive`; un valor desconocido llega como `destructive`) y los datos de la orden.
Sale: si se acepta, lo mismo que HUB_SHELL-F190. El panel no sabe qué es una cita o una factura: solo aplica la política.
Si falla: un aviso con la palabra equivocada no ejecuta nada y el asistente lo cuenta como cancelado. Las acciones destructivas del propio hub no se ofrecen nunca (HUB-F274). Las órdenes de borrar o anular de una app que no declara riesgo (Ventas, Inventario, Clientes, Reservas, Cocina, Mesas, Personal, Servicios…) llegan con una tarjeta de un clic.
Implicados: HUB-F274
QA: qa-hub-assistant §R3 (puntos 3 y 4)

### HUB_SHELL-F192 Comprobar lo que dice el asistente contra lo que de verdad hizo
Estado: parcial — el panel no enseña ningún recibo de lo ejecutado ni distingue «el servidor respondió bien» de «cambió algo»: una orden que contesta sin error cuenta como hecha aunque no haya tocado ninguna fila; instalar una app y aplicar una plantilla devuelven un error escrito sin fallar y también cuentan como hechas; una orden cuya respuesta se pierde cuenta como fallida y el aviso puede decir «No se ha modificado nada» aunque quizá sí se ejecutó; si el turno termina en error no se comprueba nada; una sola orden correcta del turno basta para que ninguna otra afirmación del mismo turno se marque; no se enseña de dónde sale una cifra
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Al acabar cada respuesta, el panel la compara con lo que se ejecutó en ese turno. No se fía de lo que la respuesta dice de sí misma.
2. Si la respuesta afirma un cambio («he creado…», «se ha actualizado…», «queda guardado», «has been created…») y en el turno no se ejecutó ninguna orden que cambie datos, o la persona la canceló, o falló, aparece **fuera de la burbuja** el aviso «El asistente ha dicho que hizo un cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.»
3. Si la respuesta escribe un identificador (un código largo) que ninguna consulta de ese turno devolvió y que la última pregunta de la persona tampoco contenía: «Esta respuesta muestra un identificador que el asistente no ha leído de verdad. No te fíes de él.» Un identificador leído en un turno anterior de la misma conversación se marca como no leído, y una última pregunta con adjuntos no cuenta como texto.
4. Si nombra una pantalla que este hub no sirve: «Esta respuesta señala una pantalla que no existe aquí.» y no se ofrece botón (HUB_SHELL-F189).
5. Los avisos van con un icono de alerta, no los escribe el modelo y se quedan con ese mensaje, también tras recargar. Una respuesta limpia no lleva nada.
6. Tras una orden aceptada, lo único que la persona ve es lo que el asistente cuente con sus palabras y, para comprobarlo, el «Ir a …» a la pantalla del registro. Si una orden pierde su respuesta (se cae la red), sale el aviso del sistema «No sabemos si la operación se completó. Comprueba el resultado antes de reintentar.»
7. Al aplicar una plantilla por el chat, el shell además pregunta en pantalla por los permisos de las apps que ha traído (HUB_SHELL-F196).
Entra: las órdenes del turno con su desenlace (hecha, error o cancelada) y sus resultados; el mapa real de pantallas.
Sale: el aviso sobre el mensaje; nada se manda al servidor. Aplicar una plantilla devuelve además al asistente lo que sigue sin hacer, para que no diga que ya se puede facturar.
Si falla: «hecha» significa que la puerta de órdenes no lanzó error y la persona aprobó la tarjeta. Una orden de una app que no comprueba cuántas filas tocó responde bien sin haber hecho nada (doble apertura de caja, doble cierre) y el asistente puede contar que sí; un lote que pone a cero lo que no se le nombró devuelve éxito. Las herramientas del núcleo para instalar una app y aplicar una plantilla devuelven un error escrito (falta el dato, la app no está en el catálogo) sin lanzarlo: cuentan como hechas. Si el turno termina en error (más de 6 rondas, red cortada, servicio que rechaza a mitad), no se hace ninguna comprobación y un «he creado…» de una ronda anterior queda sin marcar. Ese filtro de filas no lo hace este panel: lo tiene que hacer la orden del servidor (HUB, módulos y órdenes).
Implicados: HUB-F06, HUB-F273
QA: qa-hub-assistant §R0, qa-hub-assistant §R2, qa-hub-assistant §R4

### HUB_SHELL-F193 Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable
Estado: parcial — una persona sin el permiso de una orden no la tiene entre las herramientas del asistente, aunque un responsable pudiera aprobarla con su PIN: la ventana de aprobación no se abre nunca desde el chat, mientras que el mismo botón de la pantalla sí la abre (diferencia con el botón); el panel tampoco muestra nada propio cuando falta un permiso: lo cuenta el modelo con sus palabras
Actor: empleado, cajero, responsable, administrador
Pantalla: Asistente
Pasos:
1. El asistente trabaja con la sesión de quien está delante: ve y hace lo que esa persona vería y haría con los botones, nada más. Una orden cuyo permiso la sesión no tiene no está entre las herramientas del asistente: es como si no existiera, y así lo dice.
2. Por eso un cajero que le pide anular una venta no recibe la herramienta: el asistente contesta que no puede, sin ventana de PIN. En la pantalla, el botón de anular sí abriría «Hace falta una aprobación» para que un responsable teclee su PIN o pase su placa. Esa vía no existe desde el chat.
3. Instalar una app y aplicar una plantilla solo se ofrecen a quien administra (HUB-F274); el servidor lo vuelve a revisar en cada orden.
4. Lo que el asistente trae de vuelta (listas, cifras) es lo que esa sesión puede leer: el panel no filtra nada por su cuenta.
Entra: la sesión local de quien pregunta, que es la que firma cada orden.
Sale: la orden ejecutada con esa persona como autora; nunca con un aprobador, porque el asistente no pide aprobación.
Si falla: sin permiso, el asistente no tiene la herramienta y lo explica con sus palabras (sin texto fijo del panel). Si un permiso se perdiera entre ofrecer la orden y ejecutarla, el servidor la rechaza (HUB-F151) y el asistente recibe el error. La conexión del transporte con la ventana del PIN existe pero ningún camino del asistente llega a ella.
Implicados: HUB-F05, HUB-F151, HUB-F274
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
Implicados: HUB-F273
QA: qa-hub-assistant §R4

### HUB_SHELL-F195 La conversación: qué se guarda, dónde y cuándo se borra
Estado: parcial — no hay «nueva conversación»: el hilo se reenvía entero en cada pregunta (el servicio solo lee los 100 mensajes más recientes, sin decirlo) y, si el cuerpo pasa de 2 MB, el hub lo rechaza y la persona solo sale cerrando sesión o cambiando de usuario; si el navegador no deja guardar (un adjunto grande), el hilo sigue en memoria pero no sobrevive a una recarga; recargar a mitad de una respuesta la pierde; al cambiar de usuario se borra el hilo pero no el texto ni los adjuntos sin enviar, ni el aviso de cuota agotada, ni el modo configuración
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. El hilo vive solo en el navegador de esa pestaña (`sessionStorage`, clave `erplora.assistant.history`): ni el hub ni erplora.com guardan la conversación. Se guarda al enviar y al terminar, detener o fallar una respuesta, nunca mientras se escribe.
2. Recargar la página lo recupera (sin lo que estuviera llegando). Cerrar la pestaña o la ventana lo pierde. Cerrar el panel no lo borra.
3. Se vacía el hilo, y con él se corta cualquier respuesta que estuviera llegando (se libera el cuadro), cuando: la persona cierra sesión; la sesión caduca o se pierde por inactividad o por abrirse en otro dispositivo; o **cambia de usuario con PIN** en la misma caja, en cuanto el PIN nuevo es aceptado.
4. Si el PIN del cambio de usuario se rechaza, no se borra nada: quien estaba sigue dentro con su hilo.
5. Lo que se guarda: lo que escribió la persona (con sus adjuntos), lo que respondió el asistente y los avisos de comprobación. No se guardan las órdenes ejecutadas ni lo que enseñó la tarjeta.
6. Al cambiar de usuario **no** se limpian: el texto escrito y no enviado, los adjuntos sin enviar, el aviso de cuota agotada de quien se fue (sale bajo la primera respuesta de quien llega), el modo configuración (su panel vacío dice «Revisa la configuración de tu negocio…» y sus preguntas llevan ese contexto; no se apaga ni al cerrar sesión, hasta recargar) y el panel abierto. Cerrar sesión sí desmonta el panel y limpia texto, adjuntos y cuota.
7. Para empezar de cero sin salir, hoy no hay botón.
Entra: los mensajes del panel; los cierres de sesión y los relevos de usuario.
Sale: la clave del navegador; en cada pregunta, el hilo entero va al servidor (HUB-F273) y se olvida al acabar el turno.
Si falla: un almacenamiento lleno o bloqueado (modo privado) se ignora en silencio. Un hilo guardado ilegible arranca vacío.
Implicados: HUB-F136, HUB-F138, HUB-F273
QA: qa-hub-assistant §Pendiente (fase C) (cambio de usuario por PIN), qa-hub-restaurant §7.02

### HUB_SHELL-F196 El asistente en la puesta en marcha
Estado: parcial — si la relectura de la lista falla, el asistente recibe la última lista leída como si fuera de ahora (solo dice «no se pudo» si nunca hubo una lectura buena); el modo configuración no se apaga hasta recargar la página, y pasa a la persona siguiente (HUB_SHELL-F195)
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
Si falla: si nunca se pudo leer el estado, el contexto dice que no se pudo y el asistente no afirma que el negocio esté configurado; si ya hubo una lectura buena y la nueva falla, se usa la anterior sin avisar. Los atajos se reducen a «¿Qué falta por configurar?». La tarjeta de Inicio conserva «Configurar» en cada paso, así que un asistente caído no deja a nadie sin salida.
Implicados: HUB-F35
QA: qa-hub-assistant §R0 (pregunta 4), qa-hub-assistant §R4 (montar el hub por chat)

### HUB_SHELL-F197 Ver el plan del asistente, el límite de uso y ampliarlo
Estado: parcial — el aviso de cuota, una vez agotada, se queda pegado al último mensaje del hilo hasta recargar la página o cerrar sesión (también tras renovarse, tras ampliar el plan y tras un cambio de usuario); el plan se escribe con su identificador interno («Plan basic»); el texto para quien no puede pagar manda a «el responsable del negocio», pero solo pagan el propietario y el administrador
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Al abrir el panel se lee el plan del asistente de este negocio (una vez por apertura). Si no se puede leer, no se enseña nada: nunca un número inventado.
2. Desde el 80 % de los mensajes del mes, el pie dice «Plan {plan} — te quedan {n} de {total} mensajes este mes.», con «Se renuevan el {fecha}.» y, cuando el nivel viene del plan del negocio, «Incluido en tu plan {nombre}.». Por debajo del 80 % no se enseña nada.
3. El contador se mueve al terminar cada respuesta, sin recargar.
4. Al agotarse, la respuesta es «Has usado todos tus mensajes del asistente Plan {plan} — {usados} de {total} mensajes este mes. Se renuevan el {fecha}.» (no «No se pudo contactar»), y debajo lo que toca a esa persona.
5. Un administrador o propietario, cuando el SaaS dice que el nivel lo da el plan del negocio, ve «Incluido en tu plan {nombre}.» y el botón «Subir de plan», que abre la página del plan de su cuenta en el navegador (la misma puerta que el menú «Mi plan»).
6. Si el SaaS no dice que el nivel lo da el plan (hub gratuito, compra propia o sin dato), ve «Ver planes»: con un solo plan contratable va directo al pago; con varios, una hoja «Elige un plan» con «{nombre} — {precio} €/mes» y «Ir al pago». El pago se abre fuera de la caja, y al volver se relee el plan.
7. En la copia de la app instalada desde Google Play un administrador no ve ningún botón de pago, ni «Subir de plan» ni «Ver planes»: «El plan del asistente se amplía desde tu cuenta de ERPlora, en erplora.com.»
8. Quien no administra ve «Pídele al responsable del negocio que amplíe el plan del asistente.» y ningún botón.
Entra: nivel, mensajes usados, límite y fecha de renovación que da el SaaS; planes contratables.
Sale: la dirección de pago o de la página de plan se abre en el navegador (HUB-F277); al volver a la caja se relee el plan cada vez que la ventana recupera el foco. Si el corte fuera por sesiones, la frase sigue diciendo «mensajes este mes» con un número de sesiones; el panel no cobra nada ni lleva contador propio.
Si falla: sin planes contratables, «Ahora mismo no hay planes a los que ampliar.»; sin dirección de pago, «No se pudo contactar con el asistente.» (texto que no corresponde); si el navegador no abre: «No se pudo abrir la página de pago en el navegador. Inténtalo de nuevo y, si sigue fallando, actualiza la app de ERPlora.» o, para el plan, «No se pudo abrir la página de tu plan en el navegador. Inténtalo de nuevo.»
Implicados: HUB-F277
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
Implicados: HUB-F278
QA: qa-hub-assistant §Pendiente (fase C) («Report an issue»)

### HUB_SHELL-F199 El asistente sin conexión, con el servicio caído o sin plan
Estado: parcial — el panel no desactiva ni avisa de que no hay red antes de enviar; no hay «Reintentar»; si el corte llega con parte del texto ya escrito se queda la respuesta a medias sin ningún aviso; una sesión caducada durante la charla se lee como «no se pudo contactar» en vez de llevar a la entrada; los fallos permanentes que sí llegan con texto (sin credencial, sin nivel) dicen «vuelve a intentarlo en unos minutos»; las órdenes que pierden su respuesta dejan el aviso «No sabemos si la operación se completó…»
Actor: administrador, responsable, empleado, cajero
Pantalla: Asistente
Pasos:
1. Sin Internet en el aparato, el aviso general de conexión de la barra del shell aparece, pero el panel sigue abierto y se puede escribir. Al enviar, la burbuja del asistente dice «No se pudo contactar con el asistente.»
2. Con Internet pero sin llegar a erplora.com (el hub lo avisa así), el mensaje es el mismo.
3. Solo si erplora.com rechaza **dentro** de una respuesta que ya está en marcha (proveedor sin credencial, sin modelo, negocio sin nivel, hilo de más de 1 MB de texto) el mensaje es otro: «El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos minutos.» Cualquier rechazo HTTP de erplora.com (sesión del hub no reconocida, petición inválida, freno por tasa) el hub lo cuenta como «no se pudo contactar», y un cuerpo de más de 2 MB lo rechaza el propio hub con un 413 que el panel lee igual (leído, sin ejecutar).
4. Quedarse sin mensajes del mes no es una avería: HUB_SHELL-F197.
5. En todos los casos el cuadro vuelve a estar activo y la pregunta queda en el hilo; para repetirla hay que escribirla o enviar otra.
Entra: el desenlace de la petición del panel al hub.
Sale: solo texto en el hilo (también queda guardado, y viaja al asistente en la siguiente pregunta como si lo hubiera dicho él).
Si falla: un hub que no responde lo cuenta el aviso general de la barra (área de acceso y navegación), no este panel. El botón de HUB_SHELL-F198 aparece también bajo estos mensajes aunque no sean del modelo.
Implicados: HUB-F273, HUB-F277
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
| Previsualizar lo que va a hacer antes de ejecutar | parcial: datos con nombre técnico, en un párrafo, sin nombre de acción en 26 de 27 apps, sin el valor anterior ni el efecto | HUB_SHELL-F190 |
| Previsualizar un plan entero de varios pasos | no hecho | HUB_SHELL-F194 |
| Confirmación antes de cada cambio | hecho | HUB_SHELL-F190 |
| Fricción según el daño (clic, escribir, no desde el chat) | parcial: la política está, pero solo Citas declara el riesgo de sus borrados; en el resto, borrar o anular se confirma con un clic | HUB_SHELL-F191 |
| Confirmar el resultado con el dato real (número, importe) | parcial: depende de lo que cuente el modelo; el panel no pinta un recibo | HUB_SHELL-F192 |
| Marca de «hecho» que distinga ejecutado de «respondió bien» | no hecho | HUB_SHELL-F192 |
| «Ir a…» a la pantalla del registro | hecho | HUB_SHELL-F189 |
| Deshacer lo hecho por el asistente | no hecho | HUB_SHELL-F194 |
| Mismo permiso que el botón; el asistente no puede más | hecho | HUB_SHELL-F193 |
| Aprobación de un responsable (PIN) cuando falta el permiso | no hecho: la orden ni se ofrece al asistente; el botón de la pantalla sí abre el PIN | HUB_SHELL-F193 |
| Aviso cuando la respuesta afirma algo que no pasó | parcial: tres agujeros (herramientas del núcleo con error escrito, respuesta perdida, turno terminado en error) | HUB_SHELL-F192 |
| Citar de dónde sale cada cifra (registro, enlace) | no hecho | HUB_SHELL-F192 |
| Adjuntar fotos y documentos; dictado que no se envía solo | parcial | HUB_SHELL-F187 |
| Puesta en marcha guiada y leyendo el estado real | parcial: una relectura fallida reutiliza la lista anterior | HUB_SHELL-F196 |
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
| La tarjeta enseña los datos que se van a mandar, con el dinero en la moneda del negocio | parcial: solo importes de primer nivel que el esquema marca; dentro de un lote, céntimos en crudo; nombres técnicos; en un párrafo | HUB_SHELL-F190 |
| La tarjeta enseña qué cambia de lo que ya hay (valor anterior → nuevo) | no hecho | HUB_SHELL-F190 |
| La tarjeta del alta en lote cuenta cuántas filas son | no hecho (solo cuenta para los borrados masivos declarados); un alta en lote crea todas sus filas con una sola tarjeta | HUB_SHELL-F191 |
| Borrar con riesgo declarado pide escribir; masivo pide escribir el número | hecho (solo para lo que la app declara) | HUB_SHELL-F191 |
| Una app que no declara el riesgo de su borrado se confirma con un clic | hueco: es el caso de 26 de 27 apps | HUB_SHELL-F191 |
| El panel distingue «hecho» de «el servidor respondió bien» | no hecho | HUB_SHELL-F192 |
| Un rechazo del servidor llega a la persona con palabras del modelo, sin texto fijo | parcial | HUB_SHELL-F192, HUB_SHELL-F193 |
| Quien no tiene permiso no ve la herramienta (tampoco si un responsable podría aprobarla con su PIN) | hecho (lo decide el servidor) | HUB_SHELL-F193 |
| Una orden de la que solo un responsable puede responder con su PIN se puede pedir al asistente | no hecho | HUB_SHELL-F193 |

## Datos: de quién es cada dato

El panel no es dueño de ningún dato de negocio. Lo que guarda es solo del navegador de esa persona:

| Dato | Dónde | De quién | Cuándo se borra |
|---|---|---|---|
| La conversación (texto, adjuntos en base64, avisos de comprobación, identificador de cada respuesta) | `sessionStorage`, clave `erplora.assistant.history`, por pestaña | de la persona que la escribió | cerrar sesión, caducar la sesión, cambiar de usuario con PIN aceptado, cerrar la pestaña |
| Si el panel está abierto | `localStorage`, clave `erplora.assistant.open` | del aparato | nunca; no distingue personas |
| Qué quiere ver el panel (el modo de configuración) | memoria del módulo del shell | del aparato | al recargar la página; solo el paso concreto se olvida al enviar la primera pregunta |
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
- **Un borrado que su app declara masivo y que no dice cuántos registros afecta no se hace desde el chat.**
- **Una dirección que escribe el modelo no saca a la persona del hub**: solo se sigue una pantalla de
  este hub que exista; el HTML de la respuesta no se interpreta.
- Cambiar de usuario con PIN o cerrar sesión vacía el hilo y corta lo que esté llegando. Hueco: con
  el cambio de usuario se quedan el texto y los adjuntos sin enviar, el aviso de cuota de quien se fue
  y el modo configuración (HUB_SHELL-F195).
- **Lo dictado no se envía solo.**
- **El pago de un plan lo ofrece solo quien administra, y no en la copia de Google Play.**

## Lo que NO hace, a propósito

- No guarda la conversación fuera del navegador (ADR-0149): no hay historial entre dispositivos.
- No ejecuta acciones destructivas del propio hub (desinstalar, reiniciar, borrar datos).
- No lee la documentación de las apps; contesta con las descripciones de sus consultas y órdenes.
- No cita fuentes ni valora respuestas con 👍/👎; no deshace lo que ejecutó.
- Una tarjeta no aprueba dos órdenes; pero una orden de alta en lote crea todas sus filas con una sola tarjeta, sin decir cuántas.

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
- El guion de QA da por pendiente el borrado del historial al cambiar de usuario; el código ya lo hace (hub#1544, cerrada; HUB-F138 de acceso ya dice lo mismo). `qa-hub-assistant` pide que la tarjeta diga «de qué app viene»: el panel calcula el nombre de la app
  pero no lo enseña (`described.app` no se usa). También espera «`MAX_TOOL_ITERS` agotado con mensaje
  humano»: el panel o calla o dice «No se pudo contactar», y «cierra el drawer a mitad ... nada se
  ejecuta»: cerrar el panel no corta el turno. Y espera que un perfil sin permiso pueda llegar al PIN
  de un responsable por el chat: no, la orden ni se le ofrece al asistente (HUB_SHELL-F193).
- El comentario de `AssistantDrawer.vue` dice «lo destructivo ni llega aquí: no se ofrece como tool»; es
  cierto para el hub, no para las órdenes de borrar de una app, que sí llegan (`assistant-danger.ts` es
  la política). `architecture/saas/assistant.md` describe una herramienta `search_docs` sobre la
  documentación de las apps que no existe en el hub.
- Dos textos visibles no salen de las claves de traducción: los «Sí»/«No» de la tarjeta de
  confirmación (`lib/assistant-confirm.ts`) y la ficha «image» de una imagen en la burbuja de la
  persona (`messageAttachments`). El resto del panel tiene su cadena `en` y su `es` (comprobado: las
  claves de `assistant` son las mismas en los dos idiomas).
