# WORKFLOW — Hub · Impresión (la mitad del servidor)

Prefijo: HUB

## Flujos

### HUB-F190 Pedir imprimir un documento desde una pantalla o un dispositivo
Estado: parcial — el aviso en vivo a los dispositivos que imprimen lleva la palabra de función que mandó quien pidió, no la función resuelta: si no manda función (lo normal desde que el hub decide por el tipo de documento), ningún dispositivo se despierta y el trabajo espera a que alguno se reconecte o a otro aviso de esa función
Actor: empleado, responsable, administrador, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla (el cobro, la ronda del restaurante, la ficha de un producto) o un módulo desde el
   navegador pide imprimir un documento: un identificador de trabajo, el tipo de documento, el
   documento ya compuesto y, si quiere, el papel (tique o A4) y la función.
2. El hub comprueba la petición y la guarda en la cola. Contesta «puesto en cola» (o «ya estaba», si el
   identificador se repitió: HUB-F192), a qué función ha ido a parar y cuántos dispositivos la están
   imprimiendo ahora mismo.
3. Los dispositivos que imprimen esa función reciben un aviso de que hay trabajo (HUB-F198) y lo sacan
   (HUB-F199).
Entra: `POST /api/print/jobs` con `{ jobId, role?, documentType, document, format? }` y una sesión de
usuario del hub (no hace falta ser administrador). El tipo de documento es uno de ocho: tique, comanda,
factura, albarán, etiqueta, cierre de caja, cuenta, genérico. El documento es un objeto (nunca HTML) de
hasta 512 KiB. El papel es `receipt` (por omisión) o `a4`.
Sale: una fila en la cola del hub con el documento, la función resuelta (HUB-F193), el idioma del papel
(el del hub, salvo que el documento traiga el suyo) y los decimales de la moneda del hub (salvo que los
traiga). Respuesta con `status`, `role` y `liveHosts`. Un aviso de «hay trabajo» en el canal de eventos
del hub con solo la función, nunca el documento. Si `liveHosts` es 0, una línea de aviso en el registro
del hub (`print.job_unattended`), una por tique nuevo (HUB-F201).
Si falla: sin sesión, 401. Identificador vacío, tipo de documento que no es de los ocho, documento que
no es un objeto, vacío o de más de 512 KiB, papel desconocido, o una función que este hub no tiene:
422 con el motivo (y, en la función, las que sí hay). Nada se guarda. Un módulo o un flujo no entra por
aquí sino por HUB-F191.
Implicados: PRINTING-F07, PRINTING-F09, PRINTING-F10, PRINTING-F12, INVENTORY-F25, KITCHEN-F14, KITCHEN-F17, KITCHEN-F20
Pendiente de enlazar: hub — HUB_SHELL, la puerta de impresión del shell (imprimir el tique al oír la venta y la comanda al nacer, solo en el dispositivo que cobró)
QA: qa-hub §8, qa-hub-restaurant §16

### HUB-F191 Pedir imprimir desde un módulo, un flujo o el asistente
Estado: parcial — la entrega es asíncrona y no despierta a los dispositivos: un trabajo que llega por aquí espera a que el dispositivo se reconecte o a otro aviso de esa función; y quien lo pidió no se entera de un rechazo de la cola
Actor: sistema, asistente
Pantalla: asistente
Pasos:
1. Un módulo con permiso de impresora (por ejemplo Impresión, al pedírselo el asistente o un flujo)
   ejecuta una orden que emite un aviso `…print.due` con el trabajo.
2. Cuando el aviso se entrega, el hub comprueba que viene de un módulo, que tiene el permiso de
   impresora concedido, y lo pone en la cola igual que una petición de pantalla (HUB-F190).
3. Un dispositivo con esa función lo saca.
Entra: el aviso con `jobId`, `role` (opcional), `documentType`, `document` y `format` (opcional); lo
emite la orden de un módulo que declara la capacidad `printer`.
Sale: la misma fila en la cola. Sin puerta de flujo propia: el hub no emite nunca un `…print.due`, solo
los módulos. No difunde el aviso en vivo (HUB-F198).
Si falla: la orden que emite el aviso falla entera si el módulo no declara la capacidad. Si el módulo la
declara pero el usuario no la ha concedido, el aviso queda en Sistema › Eventos caídos de inmediato, sin
reintentos, y se encola solo al conceder el permiso. Si la cola rechaza el trabajo (tipo desconocido,
función que no existe, documento mal formado), el aviso se reintenta con espera creciente hasta 8
veces y acaba en Eventos caídos; la orden ya había contestado «bien». Sin módulo atribuido, no se
imprime.
Implicados: PRINTING-F16, FLOWS-F13
Pendiente de enlazar: hub — HUB, avisos entre módulos (reintentar y listar los avisos caídos)
QA: ninguno

### HUB-F192 Repetir una petición sin repetir el papel
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Quien pide imprimir manda siempre el mismo identificador de trabajo para el mismo documento
   (por ejemplo, `sale-42`, `kitchen-<pedido>-cocina`, el SKU de una etiqueta).
2. Si la petición se repite (un doble toque, un reintento de red, una reconexión), el hub contesta «ya
   estaba» y no guarda nada.
Entra: el identificador de trabajo (lo elige quien pide).
Sale: una sola fila por identificador y por hub. Repetir no sobrescribe el documento ya guardado ni
reabre un trabajo ya impreso, muerto o descartado: el identificador queda gastado **para siempre**,
mientras la fila exista (HUB-F206). El mismo identificador en dos hubs son dos trabajos.
Si falla: un identificador vacío se rechaza. Si una pantalla reutiliza una clave estable por producto
(las etiquetas de Inventario usan el SKU), la segunda etiqueta del mismo producto, hoy o dentro de un
mes, no sale y no dice nada: «ya estaba» cuenta como éxito. La impresión directa del dispositivo no
comprueba la clave (HUB_PERIPHERALS-F06).
Implicados: INVENTORY-F25, KITCHEN-F17, PRINTING-F10, PRINTING-F12
QA: qa-hub-restaurant §16

### HUB-F193 Decidir por qué impresora sale cada documento
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un documento llega sin función: el hub mira su mapa de tipo de documento a función y lo manda a la
   de ese tipo.
2. De fábrica: tique, factura, albarán, cuenta, cierre de caja y genérico van a **Recibo**; la comanda
   va a **Cocina**; la etiqueta va a **Etiqueta**. **Barra** no tiene ningún tipo asignado: solo recibe
   lo que se manda a esa función expresamente (una estación de Cocina con función Barra).
3. Si quien pide nombra una función, se respeta (con mayúsculas y espacios tolerados) siempre que
   exista; si no existe, se rechaza diciendo cuáles hay.
4. Si el tipo no tiene ruta, o su ruta apunta a una función borrada, el documento sale por Recibo: el
   mapa falla **abierto**, a Recibo, la única función que no se puede borrar.
Entra: el tipo de documento y, opcionalmente, la función.
Sale: la fila de la cola con la función resuelta y su identificador interno (que es por lo que se
reparte el trabajo, no por una palabra). Cambiar el nombre visible de una función no mueve ningún trabajo.
Si falla: un hub sin ninguna función no puede imprimir («no hay a dónde salga el papel»). Una función
nombrada por error nunca abre una cola huérfana: es rechazo, no cola nueva. Una comanda de un hub que
borró «Cocina» sale por Recibo.
Implicados: PRINTING-F04, PRINTING-F10, KITCHEN-F14, KITCHEN-F17, KITCHEN-F20
QA: qa-hub §8, qa-hub-restaurant §08

### HUB-F194 Cambiar a qué función va cada documento
Estado: parcial — solo por la API del hub (y un administrador); ninguna pantalla muestra ni cambia el mapa, y la pantalla de Impresión solo lo cuenta
Actor: administrador
Pantalla: asistente
Pasos:
1. Un administrador lee el mapa: tipo de documento → función, y la función de reserva.
2. Apunta un tipo a otra función existente (por ejemplo, las facturas a una impresora A4 propia).
3. Desde ese momento los documentos de ese tipo sin función nombrada salen por ella.
Entra: `PUT /api/print/routes` con `{ documentType, stationKey }`; la lectura (`GET`) vale con cualquier
sesión.
Sale: la ruta del tipo, con quién y cuándo la cambió. El mapa de fábrica se rellena en cada arranque,
solo para los tipos que faltan y nunca encima de lo elegido; una ruta cuya función se borró se lista
vacía, rota, en vez de esconderse.
Si falla: tipo desconocido o función que no existe, 422 con los nombres válidos. Sin sesión de
administrador, 401 o 403.
Implicados: PRINTING-F04
QA: ninguno

### HUB-F195 Crear, renombrar y quitar una función de impresión
Estado: parcial — solo por la API del hub; la pantalla de Impresión asigna las cuatro de fábrica (Recibo, Cocina, Barra, Etiqueta), no las crea ni las renombra, y un hub con una función nueva («Terraza») no la ve en el desplegable «Rol» sin que se sepa por qué
Actor: administrador
Pantalla: asistente
Pasos:
1. Un administrador crea una función con un nombre («Barra de la terraza»); el hub deriva la clave.
2. Puede cambiarle el nombre visible; la clave no cambia nunca.
3. Puede quitarla cuando ya no tiene trabajo esperando.
Entra: `POST /api/print/stations` `{ label, key? }`, `PATCH …/{id}` `{ label }`, `DELETE …/{id}`; la
lectura (`GET`) vale con cualquier sesión. La clave: hasta 40 caracteres, letras, números, `_` y `-`;
el nombre, hasta 120.
Sale: de fábrica cada hub tiene cuatro (receipt, kitchen, bar, label). Borrar quita también los
dispositivos dados de alta en esa función.
Si falla: clave repetida o inválida, nombre vacío o largo, 422. Borrar una función con trabajo esperando
o imprimiéndose, o la de Recibo, 409. Los trabajos muertos o retirados no impiden borrarla: quedan
apuntando a una función que no existe (reintentar uno de ellos lo deja sin nadie que lo pueda sacar;
solo se puede descartar).
Implicados: PRINTING-F04
QA: ninguno

### HUB-F196 Dar de alta un dispositivo como el que imprime una función
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dispositivo con la aplicación instalada, al arrancar y cada vez que a una de sus impresoras se le
   pone función (HUB_PERIPHERALS-F04), le dice al hub «yo imprimo esta función».
2. El hub lo apunta con el nombre que el negocio dio al dispositivo (o, si no, el de su plataforma) y
   contesta cada cuánto debe dar señales (30 s).
3. Desde ese momento la tarjeta de esa función pasa a «Listo» con «Imprime desde: <dispositivo>».
Entra: `POST /api/print/hosts` con `{ role, label? }`, la cabecera `X-Device-Id` y una sesión de
usuario (no hace falta ser administrador: un dispositivo solo se da de alta a sí mismo).
Sale: una fila por dispositivo y función, con quién y cuándo la dio de alta; repetir el alta solo
cuenta como señal de vida (no cambia el alta ni pisa el nombre). Varios dispositivos pueden imprimir la
misma función y uno puede imprimir varias. La alta sobrevive a un reinicio del hub; lo que no
sobrevive es estar «vivo» (HUB-F197). Es lo que marca hecho el paso «Configura tu impresora» de la
lista de arranque.
Si falla: sin `X-Device-Id`, 422; función que no existe, 422 con las que hay; nombre de más de 120
caracteres, 422; sin sesión, 401. Una impresora **USB** no se da de alta (la puerta del shell solo
acepta red y Bluetooth), por eso no recibe trabajos (HUB_PERIPHERALS-F07). Un dispositivo que se dio de
alta y se apaga sigue en la lista, «no vivo».
Implicados: PRINTING-F04, HUB_PERIPHERALS-F04
Pendiente de enlazar: hub — HUB_APP, el alta del dispositivo y la búsqueda de impresoras en la aplicación instalada
Pendiente de enlazar: hub — HUB_SHELL, quién da de alta el dispositivo al arrancar
QA: qa-hub §8, qa-hub-android §15

### HUB-F197 Mantener vivo o retirar un dispositivo de impresión
Estado: hecho
Actor: sistema, administrador
Pantalla: ninguna
Pasos:
1. Un dispositivo conectado da señales cada 30 s (por el canal en vivo o por la puerta HTTP). Se le da por
   vivo hasta 90 s después de su última señal: tres señales perdidas, no una.
2. Si el hub le contesta que no tiene nada que refrescar, el dispositivo debe darse de alta otra vez.
3. Un dispositivo puede retirarse de una función o de todas. Retirar el de **otro** (la caja cambiada o
   robada) lo hace un administrador.
Entra: `POST /api/print/hosts/heartbeat` (sesión de usuario y `X-Device-Id`), o la señal por el canal en
vivo; `DELETE /api/print/hosts?role=&deviceId=`.
Sale: la marca de última señal. Estar vivo no se guarda: se calcula al leer, porque un dispositivo apagado no
puede escribir. Retirar borra la fila (a diferencia de apagarse, que la deja «no viva»).
Si falla: sin `X-Device-Id`, 422; retirar a otro sin ser administrador, 401. «Refrescadas: 0» es una
respuesta correcta, no un error: significa «no imprimes nada aquí, regístrate».
Implicados: ninguno
QA: ninguno

### HUB-F198 Conectar el dispositivo a la cola en vivo
Estado: parcial — el aviso «hay trabajo» solo llega para las funciones que el dispositivo tenía al conectarse: una función dada de alta después no despierta a esa conexión hasta que se reconecte; el dispositivo no vuelve a preguntar por sí solo
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dispositivo abre el canal de impresión del hub y se identifica en el primer mensaje con la sesión
   y su identificador (la sesión no viaja en la dirección, para que no quede en los registros).
2. El hub comprueba la sesión y que el dispositivo imprime alguna función, y le contesta qué funciones
   imprime y cada cuánto dar señales.
3. El dispositivo pide el trabajo de cada una de sus funciones, y después espera a que el hub le avise de que
   ha llegado uno nuevo.
Entra: `GET /ws/print` con los mensajes `hello`, `claim`, `done`, `failed` y `beat`.
Sale: mensajes `ready`, `job`, `idle`, `ack`, `beat` y `wake` (este último con solo la función, nunca el
documento: el documento solo viaja en la respuesta a un `claim`). Cada `claim` cuenta como señal de vida.
Si falla: cada negativa tiene su código: `print.not_ready` (cualquier mensaje antes de `hello`),
`unauthenticated`, `print.device_required`, `print.host_not_registered` (el dispositivo no imprime nada en
este hub, incluidos los de otro hub), `print.role_not_hosted` (pide una función que no imprime) y
`print.frame_too_large` (más de 8 KiB). Sin `hello` en 15 s, se cuelga. Las primeras cuatro cierran el
canal; la sesión sola no basta (un móvil con sesión no puede vaciar la cola) ni el registro solo (el
identificador no es una credencial).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_APP, el canal de impresión del dispositivo instalado (reconexión)
QA: qa-hub §8

### HUB-F199 Sacar un trabajo de la cola y confirmar que salió el papel
Estado: parcial — el hub da por «hecho» lo que el dispositivo confirma, y el dispositivo confirma al poner el trabajo en su cola interna, no cuando sale el papel: con la impresora de red apagada el trabajo se marca hecho y no sale (HUB_PERIPHERALS-F06)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dispositivo pide el siguiente trabajo de su función. El hub le entrega el más antiguo que esté
   pendiente y lo reserva 90 s; dos dispositivos de la misma función se llevan trabajos distintos.
2. El dispositivo lo imprime y confirma «salió»: el trabajo pasa a «hecho».
3. Si no pudo imprimir, dice «falló» con el motivo: el trabajo vuelve a «pendiente» para otro intento.
4. Si el dispositivo se cae sin contestar, a los 90 s el trabajo se devuelve a «pendiente» (sin proceso en
   segundo plano: se hace en el siguiente reparto).
Entra: los mensajes del canal en vivo (HUB-F198), de un dispositivo dado de alta para esa función.
Sale: el estado del trabajo (pendiente → imprimiendo → hecho), con los intentos y el último error. Cada
entrega gasta un intento. Un dispositivo que imprimió y murió antes de confirmar hace que el trabajo
salga **otra vez**: el hub prefiere un papel de más a un cliente sin tique.
Si falla: confirmar o fallar un trabajo de otra función, o desde un dispositivo no dado de alta, se
rechaza; confirmar un trabajo que ya está muerto o retirado contesta «no confirmado» sin cambiar nada;
un trabajo que el hub ya no tiene también. Confirmar con el reserva vencido se acepta: el papel salió.
Implicados: PRINTING-F07, PRINTING-F10, HUB_PERIPHERALS-F06, HUB_PERIPHERALS-F07
QA: qa-hub-restaurant §16

### HUB-F200 Un trabajo que no sale acaba «muerto»
Estado: hecho
Actor: sistema
Pantalla: printing: Impresoras
Pasos:
1. Un trabajo lleva cinco entregas como mucho. Cada vez que un dispositivo lo reclama gasta una.
2. Si falla cinco veces, o si el dispositivo se cae cinco veces sin contestar, el trabajo pasa a «muerto» y
   se queda con su último error («print host lease expired» si fue por desconexión).
3. Un trabajo muerto no se entrega más ni se borra: espera a que una persona lo reintente o lo descarte
   (HUB-F204, HUB-F205).
Entra: los fallos y desconexiones de los dispositivos.
Sale: un trabajo en estado «muerto», visible en la cola. Su identificador sigue gastado (HUB-F192).
Si falla: un trabajo solo muere por fallos **antes** del envío (la aplicación no pudo componer, no hay
impresora, un USB rechazó el trabajo) o por desconexiones; una impresora de red apagada no lo mata,
porque el dispositivo ya lo dio por hecho (HUB-F199). Un dispositivo que falla deja de pedir esa función
hasta que le llegue un aviso o se reconecte, para no gastar las cinco entregas en milisegundos.
Implicados: PRINTING-F14
QA: qa-hub-restaurant §16

### HUB-F201 Trabajo en cola y nadie conectado para sacarlo
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: campana y Ajustes › Impresoras y tique (tarjeta «Estado de impresión»)
Pasos:
1. Se cobra o se dispara una ronda y no hay ningún dispositivo vivo para esa función.
2. El trabajo se guarda y **espera**: tarde, no perdido. El hub no se niega a cobrar porque no haya
   impresora.
3. La respuesta de la petición dice `liveHosts: 0`, y el TPV avisa («El tique está en espera: aún no hay
   ninguna impresora dada de alta…»).
4. Si pasa 1 minuto con trabajo esperando y nadie vivo, la función se marca «sin atender» y la campana de
   cada pantalla lo cuenta.
Entra: el trabajo y el registro de dispositivos.
Sale: `liveHosts: 0`, un aviso en el registro del hub por cada tique nuevo (no por los duplicados) y, al
minuto, la función en la lista de «sin atender». «Vivo» es la misma definición en las tres puertas
(HUB-F202): un dispositivo que se apagó hace menos de 90 s aún cuenta como vivo y el aviso no sale.
Si falla: con un dispositivo caído menos de 90 s no se avisa; la espera la ve quien mire la cola, no
quien cobra. Al conectarse un dispositivo de esa función, vacía lo que esperaba, en orden.
Implicados: PRINTING-F01, PRINTING-F07, PRINTING-F10, CASH_REGISTER-F08
Pendiente de enlazar: hub — HUB_SHELL, la campana de impresión y la tarjeta «Estado de impresión» de Ajustes
QA: qa-hub §8, qa-hub-restaurant §16

### HUB-F202 Saber qué funciones tienen quién las imprima
Estado: hecho
Actor: empleado, responsable, administrador, sistema
Pantalla: printing: Impresoras
Pasos:
1. Quien está en el puesto abre la pantalla de Impresión, o una pantalla del hub la consulta sola.
2. Por cada función que tenga algún dispositivo dado de alta o trabajos esperando, el hub dice cuántos
   trabajos esperan, cuántos dispositivos están vivos, cuáles (por su nombre), cuánto lleva esperando el
   más antiguo y si está «sin atender».
3. «Sin atender» = trabajo esperando, ningún dispositivo vivo y al menos 60 s de espera.
Entra: la consulta `hub.print.coverage` (módulos), `GET /api/print/hosts` (shell) o
`GET /api/print/undrained` (solo las atascadas, para la campana). Vale cualquier sesión local, **no**
hace falta ser administrador y no vale una clave de API.
Sale: la misma vista para las tres puertas, con el veredicto ya resuelto: nadie recalcula el umbral. Una
función sin dispositivo y sin trabajo no aparece (hasta que algo espere); un hub sin impresoras da una lista
vacía.
Si falla: una lectura que falla no se pinta como «todo al día» (la pantalla lo cuida).
Implicados: PRINTING-F01, CASH_REGISTER-F08
Pendiente de enlazar: hub — HUB_SHELL, la campana y la tarjeta «Estado de impresión»
QA: qa-hub §8

### HUB-F203 Leer la cola de trabajos
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: printing: Impresoras
Pasos:
1. En Impresión → Impresoras, la cola lista lo que espera, lo que se imprime, lo muerto y lo retirado.
2. Cada trabajo dice qué documento es (con su número impreso, «Recibo T-000123»), la función, el estado, los
   intentos, cuándo se puso y el último error.
Entra: `hub.print.jobs` o `GET /api/print/jobs?role=&status=&limit=` (cualquier sesión local; 100 por
omisión, 500 como mucho).
Sale: una vista de estado, **sin el documento** (solo su número impreso, que va en el papel). Los
pendientes e imprimiéndose en orden de entrega; los hechos y retirados, del más reciente al más
antiguo. Quién retiró o relanzó un trabajo, cuándo, por qué y desde qué módulo, con el nombre de la
persona, **solo** se ve con permiso de administrador; para el mostrador esas claves no existen.
Si falla: sin filtro de estado la lista mezcla los hechos y trae los más antiguos primero, y con más de
100 filas no llega a los pendientes (la pantalla de Impresión pide cada estado por separado).
Implicados: PRINTING-F01, PRINTING-F14
QA: qa-hub §8

### HUB-F204 Reintentar un trabajo muerto
Estado: hecho
Actor: administrador
Pantalla: printing: Impresoras
Pasos:
1. Arregla la causa (impresora, papel, función sin dispositivo).
2. En el trabajo «Muerto» pulsa «Reintentar».
3. El trabajo vuelve a «pendiente» con los intentos a cero.
Entra: `POST /api/print/jobs/{jobId}/retry`, con sesión de administrador y, si pasa por un módulo, con
el permiso de impresora concedido a ese módulo.
Sale: el trabajo pendiente, con quién, cuándo y por qué módulo lo relanzó (solo guarda el último
reintento). No despierta a nadie: lo saca el próximo dispositivo que se conecte o reciba un aviso de esa función.
Si falla: un trabajo que no está muerto, 409 (`print.job_not_requeueable`) con su estado real; que no
existe en este hub, 404; sin administrador, 401/403; módulo sin el permiso, rechazo. Un trabajo de una
función ya borrada vuelve a pendiente y no lo recoge nadie.
Implicados: PRINTING-F14
QA: qa-hub-restaurant §16, qa-hub §8

### HUB-F205 Descartar un trabajo que no debe salir
Estado: hecho
Actor: administrador
Pantalla: printing: Impresoras
Pasos:
1. En un trabajo «Pendiente» o «Muerto», pulsa «Descartar».
2. Escribe un motivo (opcional) y confirma.
3. El trabajo queda «Retirado» y ya no bloquea su función.
Entra: `POST /api/print/jobs/{jobId}/discard` con `{ reason? }` (500 caracteres como mucho) y los mismos
permisos que HUB-F204.
Sale: el trabajo retirado, **sin borrar**: quién, cuándo, por qué módulo y por qué. Ningún dispositivo lo
recibe más. Es la única forma de poder borrar una función con trabajo esperando.
Si falla: un trabajo que un dispositivo está imprimiendo, 409 (`print.job_not_discardable`); que no
existe, 404; sin permisos, rechazo.
Implicados: PRINTING-F14
QA: qa-hub-restaurant §16, qa-hub §8

### HUB-F206 Cuánto tiempo guarda el hub los trabajos de impresión
Estado: parcial — los trabajos hechos, muertos y retirados no se purgan nunca y guardan el documento entero; el borrado de datos de un cliente no los alcanza; solo el «reset» del negocio vacía la cola
Actor: sistema, administrador
Pantalla: ninguna
Pasos:
1. Un trabajo se guarda con su documento desde que se pone en cola.
2. Al terminar (hecho, muerto, retirado) la fila se queda.
3. Una persona con permiso de administrador puede vaciar la cola con el reinicio de datos del negocio; la
   configuración de dispositivos (quién imprime qué) se conserva.
Entra: el reinicio del negocio (sección «Cola de impresión»).
Sale: la fila queda con el documento (nombre, NIF y dirección de un cliente en una factura; mesa y camarero
en una comanda), el motivo escrito a mano de un descarte y quién actuó. Los avisos `…print.due` del
registro de avisos se borran a los 90 días; la fila de la cola no.
Si falla: un cliente que pide el borrado de sus datos sigue en las filas de la cola y no hay forma de
quitarlo, salvo reiniciar todo el negocio. Tampoco hay límite de tamaño ni de edad.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, negocio y datos (retención, borrado de un cliente y reinicio del negocio)
QA: ninguno

### HUB-F207 Abrir el cajón por la impresora (lo que sabe el servidor)
Estado: parcial — el hub no participa: no hay forma de abrir el cajón desde el servidor, ni cola, ni registro de quién lo abrió, ni una apertura manual; y si el dispositivo que cobró no llega a la impresora o ésta contesta con error, el cajón no se abre y nadie lo sabe
Actor: cajero, sistema
Pantalla: ninguna
Pasos:
1. Con «Abrir cajón al cobrar» activado en Impresión, el dispositivo que cobró (el único que reacciona a su
   venta) lee la impresora de la función Recibo y le manda el pulso (HUB_PERIPHERALS-F15).
2. Si ese dispositivo no llega a esa impresora, no se abre.
Entra: el ajuste «Abrir cajón al cobrar» (de Impresión) y la venta cobrada.
Sale: nada en el hub. El pulso no es un documento, no entra en la cola, no queda guardado ni se difunde.
Se abre con cualquier forma de pago (no solo efectivo) y siempre por el pin 2.
Si falla: el error de la impresora se descarta sin aviso; si el dispositivo está en un navegador, no se
abre. No existe «Abrir cajón / sin venta» con permiso y registro.
Implicados: PRINTING-F13, SALES-F01, HUB_PERIPHERALS-F15
Pendiente de enlazar: hub — HUB_SHELL, abrir el cajón al cobrar en el dispositivo que cobró
QA: qa-hub §8
