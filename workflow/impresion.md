# WORKFLOW — Hub · Impresión (la mitad del servidor)

Prefijo: HUB

> Área «Impresión» del servidor del hub (`crates/runtime`: `printing`, `print_queue`, `print_drain`,
> `print_hosts`, `print_routes`, `print_stations`, `host_print`; `crates/server`: `print`,
> `print_ws`): la cola de trabajos de impresión, las funciones (Recibo, Cocina, Barra, Etiqueta) y a
> qué función va cada documento, los dispositivos que imprimen cada función y cómo se reintenta o se
> descarta un trabajo. La pantalla «Impresoras» es del módulo Impresión (`printing`); la mitad de
> dispositivo (descubrir, ESC/POS, USB, cajón) está en `crates/peripherals/WORKFLOW.md`
> (HUB_PERIPHERALS-F01 a F16).

## Referencia adoptada

Estaciones como filas, mapa tipo de documento → estación y cola con clave por
trabajo (Toast, Square, Lightspeed K, Odoo, Oracle Simphony, Epson ePOS, Star CloudPRNT; contrastado
en hub#457/#987, `qa-hub-restaurant` §2). Se adopta: la impresora es un destino y la función dice
para qué sirve; el trabajo espera si no hay nadie (tarde, no perdido); el mapa falla abierto a
Recibo.

## Antes de empezar

- Una aplicación instalada abierta en el puesto que tiene la impresora, dada de alta como quien
  imprime una función (HUB-F196); sin ella los trabajos esperan (HUB-F201).
- Las cuatro funciones de fábrica (Recibo, Cocina, Barra, Etiqueta) nacen con el hub (solo se
  siembran si no tiene ninguna); solo Recibo no se puede borrar.
- La caja que cobra, si tiene la impresora de la función, imprime directo y el hub no ve ese papel.

## Flujos

### HUB-F190 Pedir imprimir un documento desde una pantalla o un dispositivo
Estado: parcial — el aviso en vivo lleva la palabra de función tal como la escribió quien pidió, no la función resuelta: si no la manda (asistente, flujo, API) o la escribe con otras mayúsculas o espacios, ningún dispositivo conectado se despierta y el trabajo espera a una reconexión o a otro aviso de esa función. Y este camino solo cuenta cuando el trabajo pasa por la cola: la caja que cobra, si tiene la impresora de la función, imprime directo y el hub no se entera
Actor: empleado, responsable, administrador, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla (el cobro, la ronda del restaurante, la ficha de un producto) pide imprimir un
   documento por la puerta de impresión del shell. **Si ese dispositivo tiene una impresora con la
   función del documento, el shell la manda directamente a la impresora y el hub no recibe nada**
   (camino directo, sin fila en la cola: ver «Lo que el hub no ve»). Solo si no la tiene (o no
   llega al hardware: un navegador) el shell sigue con el paso 2. La petición lleva: un identificador de trabajo, el tipo de documento, el
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
Lo que el hub no ve: la impresión directa de la caja que cobró o disparó la comanda
(`apps/web/src/lib/print.ts:381-404`). No deja ninguna fila en la cola, ni cuenta en la cobertura,
ni sale en Impresión ni en el cierre de caja; si el papel se pierde (HUB-F199) nadie del hub lo sabe.
Si falla: sin sesión, 401. Identificador vacío, tipo de documento que no es de los ocho, documento que
no es un objeto, vacío o de más de 512 KiB, papel desconocido, o una función que este hub no tiene:
422 con el motivo (y, en la función, las que sí hay). Nada se guarda. Las pantallas de los módulos sí entran por aquí (puerta `erplora.print`); solo las órdenes de módulo que emiten `…print.due` entran por HUB-F191.
Implicados: HUB_SHELL-F70, HUB_SHELL-F72, HUB_SHELL-F77, INVENTORY-F25, KITCHEN-F08, KITCHEN-F14, KITCHEN-F17, KITCHEN-F20, PRINTING-F07, PRINTING-F09, PRINTING-F10, PRINTING-F12, REC_FISCAL-F07
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
En este mismo documento se apoya en: HUB-F52 (Reintentar un aviso que un módulo no pudo procesar), HUB-F53 (Mandar a «Eventos caídos» al momento lo que reintentar no arregla), HUB-F54 (Ver la cola de avisos caídos), HUB-F55 (Reenviar un aviso caído), HUB-F56 (Reenviar todos los avisos caídos), HUB-F58 (Reenviar solo lo que un permiso había rechazado, al concederlo).
Si falla: si el aviso lo devuelve el código del módulo, la orden falla entera cuando el módulo no
declara la capacidad; si es un `emit` declarado en el manifiesto, la orden responde bien y el aviso
acaba en Eventos caídos, marcado por permiso. Si el módulo la declara pero el usuario no la ha
concedido, el aviso queda en Sistema › Eventos caídos de inmediato, sin
reintentos, y se encola solo al conceder el permiso. Si la cola rechaza el trabajo (tipo desconocido,
función que no existe, documento mal formado), el aviso se reintenta con espera creciente hasta 8
veces y acaba en Eventos caídos; la orden ya había contestado «bien». Sin módulo atribuido, no se
imprime.
Implicados: FLOWS-F25, PRINTING-F16
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
Implicados: INVENTORY-F25, KITCHEN-F14, KITCHEN-F17, KITCHEN-F20, PRINTING-F10, PRINTING-F12
QA: qa-hub-restaurant §16

### HUB-F193 Decidir por qué impresora sale cada documento
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un documento llega sin función (hoy: solo el asistente, un flujo o la API; todas las pantallas nombran la función): el hub mira su mapa de tipo de documento a función y lo manda a la
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
Implicados: KITCHEN-F14, KITCHEN-F17, KITCHEN-F20, PRINTING-F04, PRINTING-F10
QA: qa-hub §8, qa-hub-restaurant §08

### HUB-F194 Cambiar a qué función va cada documento
Estado: parcial — solo por la API del hub (y un administrador); ninguna pantalla muestra ni cambia el mapa, y hoy todas las pantallas nombran la función (tique, cuenta, comanda, pase, aviso de urgencia, etiqueta, factura), así que cambiar el mapa solo mueve lo que piden el asistente, un flujo o la API sin función; la puerta directa del shell tampoco lo consulta
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
Si falla: clave repetida o inválida, nombre largo, o sin clave y sin nombre, 422 (con clave explícita y nombre vacío se acepta; al renombrar, el nombre vacío es 422). Borrar una función con trabajo esperando
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
Sale: una fila por dispositivo y función, con quién y cuándo la dio de alta; repetir el alta
renueva la señal de vida y vuelve a poner el nombre actual del dispositivo; no cambia quién ni cuándo lo dio de alta. Varios dispositivos pueden imprimir la
misma función y uno puede imprimir varias. La alta sobrevive a un reinicio del hub; lo que no
sobrevive es estar «vivo» (HUB-F197). El alta para la función **Recibo** es lo que marca hecho el paso «Configura tu impresora» de la
lista de arranque.
Si falla: sin `X-Device-Id`, 422; función que no existe, 422 con las que hay; nombre de más de 120
caracteres, 422; sin sesión, 401. Una impresora **USB** no se da de alta (la puerta del shell solo
acepta red y Bluetooth), por eso no recibe trabajos (HUB_PERIPHERALS-F07). Un dispositivo que se dio de
alta y se apaga sigue en la lista, «no vivo».
Implicados: HUB_PERIPHERALS-F04, HUB_APP-F13, HUB_APP-F17, HUB_APP-F18, HUB_SHELL-F73, PRINTING-F04
QA: qa-hub §8, qa-hub-android §15

### HUB-F197 Mantener vivo o retirar un dispositivo de impresión
Estado: parcial — retirar solo se hace por la API (ninguna pantalla lo llama); un dispositivo retirado con la aplicación abierta se vuelve a dar de alta solo y cuenta como vivo sin imprimir; una función quitada o una impresora borrada en la aplicación nunca se retira del hub, que sigue dando la función por cubierta
Actor: sistema, administrador
Pantalla: ninguna
Pasos:
1. Un dispositivo conectado da señales cada 30 s (por el canal en vivo o por la puerta HTTP). Se le da por
   vivo hasta 90 s después de su última señal: tres señales perdidas, no una.
2. Si el hub le contesta que no tiene nada que refrescar, el dispositivo debe darse de alta otra vez.
3. Un dispositivo puede retirarse de una función o de todas. Retirar el de **otro** (la caja cambiada o
   robada) lo hace un administrador.
Entra: `POST /api/print/hosts/heartbeat` (sesión de usuario y `X-Device-Id`), o la señal por el canal en
vivo; `DELETE /api/print/hosts?role=&deviceId=`. El `deviceId` de otro dispositivo solo lo lee un
administrador en `GET /api/print/hosts` (HUB-F202).
Sale: la marca de última señal. Estar vivo no se guarda: se calcula al leer, porque un dispositivo apagado no
puede escribir. Retirar borra la fila (a diferencia de apagarse, que la deja «no viva»).
Si falla: sin `X-Device-Id`, 422; retirar a otro sin ser administrador, 403. «Refrescadas: 0» es una
respuesta correcta, no un error: significa «no imprimes nada aquí, regístrate». Un dispositivo cuyo canal en vivo murió por un
código fatal (`unauthenticated`, `print.host_not_registered`, `print.not_ready`) sigue dando señales por HTTP y cuenta
como vivo: «sin atender» no salta y la cobertura dice que la función se imprime (HUB-F201, HUB-F202).
Implicados: HUB_APP-F17, HUB_APP-F18, HUB_SHELL-F73
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
`print.frame_too_large` (más de 8 KiB). Sin `hello` en 15 s, se cuelga. Todas cierran el canal salvo
`print.role_not_hosted`; la sesión sola no basta (un móvil con sesión no puede vaciar la cola) ni el registro solo (el
identificador no es una credencial).
Implicados: HUB_APP-F18, HUB_SHELL-F74
QA: qa-hub §8

### HUB-F199 Sacar un trabajo de la cola y confirmar que salió el papel
Estado: parcial — el papel de una impresora de red apagada se pierde sin aviso: `erplora_print` (`apps/tauri/src-tauri/src/lib.rs:1671-1683`) pone los bytes en una cola en memoria y contesta `Ok`; sus 3 intentos solo dejan rastro con `eprintln!` (`lib.rs:1256-1266`); el dispositivo manda `done` (`apps/web/src/lib/print-drain.ts:212-213`) y el hub marca el trabajo «hecho». No hay reintento, ni estado «fallido», ni aviso (HUB_PERIPHERALS-F06)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dispositivo pide el siguiente trabajo de su función. El hub le entrega el más antiguo que esté
   pendiente y lo reserva 90 s; dos dispositivos de la misma función se llevan trabajos distintos.
2. El dispositivo lo imprime y confirma «salió»: el trabajo pasa a «hecho».
3. Si no pudo imprimir, dice «falló» con el motivo: el trabajo vuelve a «pendiente» para otro intento, pero sin aviso en vivo: solo se vuelve a repartir con el siguiente trabajo de esa función o cuando un dispositivo se reconecta.
4. Si el dispositivo se cae sin contestar, a los 90 s el trabajo se devuelve a «pendiente» (sin proceso en
   segundo plano: se hace en el siguiente reparto).
Entra: los mensajes del canal en vivo (HUB-F198), de un dispositivo dado de alta para esa función.
Sale: el estado del trabajo (pendiente → imprimiendo → hecho), con los intentos y el último error. Cada
entrega gasta un intento. Un dispositivo que imprimió y murió antes de confirmar hace que el trabajo
salga **otra vez**: el hub prefiere un papel de más a un cliente sin tique.
Si falla: confirmar o fallar un trabajo de otra función, o desde un dispositivo no dado de alta, se
rechaza; confirmar un trabajo que ya está muerto o retirado contesta «no confirmado» sin cambiar nada;
un trabajo que el hub ya no tiene también. Confirmar con el reserva vencido se acepta: el papel salió.
Implicados: HUB_PERIPHERALS-F06, HUB_PERIPHERALS-F07, HUB_APP-F19, HUB_SHELL-F70, HUB_SHELL-F74, PRINTING-F07, PRINTING-F10
QA: qa-hub-restaurant §16

### HUB-F200 Un trabajo que no sale acaba «muerto»
Estado: hecho
Actor: sistema
Pantalla: PRINTING: Impresoras
Pasos:
1. Un trabajo lleva cinco entregas como mucho. Cada vez que un dispositivo lo reclama gasta una.
2. Si falla cinco veces, o si el dispositivo se cae cinco veces sin contestar, el trabajo pasa a «muerto» y
   se queda con su último error («print host lease expired» si fue por desconexión).
3. Un trabajo muerto no se entrega más ni se borra: espera a que una persona lo reintente o lo descarte
   (HUB-F204, HUB-F205).
Entra: los fallos y desconexiones de los dispositivos.
Sale: un trabajo en estado «muerto», visible en la cola. Su identificador sigue gastado (HUB-F192).
Si falla: un trabajo solo muere por fallos **antes** del envío (la aplicación no pudo componer, el dispositivo no tiene impresora con esa
función —también si se la quitaron sin retirarlo del hub, HUB-F197—, o una Bluetooth no contestó) o por
desconexiones; una USB nunca recibe trabajos de la cola; una impresora de red apagada no lo mata,
porque el dispositivo ya lo dio por hecho (HUB-F199). Un dispositivo que falla deja de pedir esa función
hasta que le llegue un aviso o se reconecte, para no gastar las cinco entregas en milisegundos; y el trabajo devuelto no despierta a nadie (HUB-F199).
Implicados: HUB_SHELL-F74, PRINTING-F14
QA: qa-hub-restaurant §16

### HUB-F201 Trabajo en cola y nadie conectado para sacarlo
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: Ajustes › Impresión
Pasos:
1. Se cobra o se dispara una ronda y no hay ningún dispositivo vivo para esa función.
2. El trabajo se guarda y **espera**: tarde, no perdido. El hub no se niega a cobrar porque no haya
   impresora.
3. La respuesta de la petición dice `liveHosts: 0`, y el TPV avisa («El tique está en espera: aún no hay
   ninguna impresora dada de alta…»).
4. Si pasa 1 minuto con trabajo esperando y nadie vivo, la función se marca «sin atender» y la campana de
   cada pantalla lo cuenta, igual que la tarjeta «Estado de impresión» de Ajustes › Impresión.
Entra: el trabajo y el registro de dispositivos.
Sale: `liveHosts: 0`, un aviso en el registro del hub por cada tique nuevo (no por los duplicados) y, al
minuto, la función en la lista de «sin atender». «Vivo» es la misma definición en las tres puertas
(HUB-F202): un dispositivo que se apagó hace menos de 90 s aún cuenta como vivo y el aviso no sale.
Si falla: con un dispositivo caído menos de 90 s no se avisa; la espera la ve quien mire la cola, no
quien cobra. Al conectarse un dispositivo de esa función, vacía lo que esperaba, en orden. Un dispositivo
con el canal en vivo muerto que sigue dando señales por HTTP cuenta como vivo, y la alarma no salta (HUB-F197).
Implicados: CASH_REGISTER-F08, HUB_SHELL-F60, HUB_SHELL-F63, HUB_SHELL-F75, PRINTING-F01, PRINTING-F07, PRINTING-F10
QA: qa-hub §8, qa-hub-restaurant §16

### HUB-F202 Saber qué funciones tienen quién las imprima
Estado: parcial — un dispositivo cuyo canal de impresión se paró sigue contando como vivo, y una función que se le quitó a una impresora en la aplicación sigue saliendo cubierta: la vista puede decir que hay quien imprima cuando no lo hay (ERPlora/hub#2494)
Actor: empleado, responsable, administrador, sistema
Pantalla: PRINTING: Impresoras
Pasos:
1. Quien está en el puesto abre la pantalla de Impresión, o una pantalla del hub la consulta sola.
2. Por cada función que tenga algún dispositivo dado de alta o trabajos esperando, el hub dice cuántos
   trabajos esperan, cuántos dispositivos están vivos, cuáles (por su nombre), cuánto lleva esperando el
   más antiguo y si está «sin atender».
3. «Sin atender» = trabajo esperando, ningún dispositivo vivo y al menos 60 s de espera. Un dispositivo con el canal
   en vivo muerto que sigue dando señales por HTTP cuenta como vivo (HUB-F197).
Entra: la consulta `hub.print.coverage` (módulos), `GET /api/print/hosts` (shell) o
`GET /api/print/undrained` (solo las atascadas, para la campana). Vale cualquier sesión local, **no**
hace falta ser administrador y no vale una clave de API.
Sale: la misma vista para las tres puertas, con el veredicto ya resuelto: nadie recalcula el umbral. Cada
dispositivo se nombra por su nombre o, si se dio de alta sin él, por los cuatro últimos caracteres de su
identificador («…e7f8»), nunca por el identificador entero: es la prueba de un dispositivo de confianza
(HUB-F139). `GET /api/print/hosts` lista además los dispositivos dados de alta con ese mismo `name`; su
`deviceId` solo va al propio dispositivo (el de la cabecera `X-Device-Id`) o a un administrador, que lo
necesita para retirar uno ajeno (HUB-F197) (hub#2551). Una
función sin dispositivo y sin trabajo no aparece (hasta que algo espere); un hub sin impresoras da una lista
vacía.
Si falla: una lectura que falla no se pinta como «todo al día» (la pantalla lo cuida).
Implicados: CASH_REGISTER-F08, HUB_SHELL-F37, HUB_SHELL-F63, HUB_SHELL-F75, HUB_SHELL-F137, PRINTING-F01
QA: qa-hub §8

### HUB-F203 Leer la cola de trabajos
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: PRINTING: Impresoras
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
Pantalla: PRINTING: Impresoras
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
Pantalla: PRINTING: Impresoras
Pasos:
1. En un trabajo «Pendiente» o «Muerto», pulsa «Descartar».
2. Escribe un motivo (opcional) y confirma.
3. El trabajo queda «Retirado» y ya no bloquea su función.
Entra: `POST /api/print/jobs/{jobId}/discard` con `{ reason? }` (500 caracteres como mucho) y los mismos
permisos que HUB-F204.
Sale: el trabajo retirado, **sin borrar**: quién, cuándo, por qué módulo y por qué. Ningún dispositivo lo
recibe más. Es la única forma de poder borrar una función con trabajo esperando.
Si falla: un trabajo que se está imprimiendo, ya hecho o ya retirado, 409 (`print.job_not_discardable`) con su estado; que no
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
Sale: la fila queda con el documento (nombre, NIF y dirección de un cliente en una factura; mesa, camarero y la
etiqueta de la comanda con el nombre de un cliente, «Recogida Ana»), el motivo escrito a mano de un
descarte, quién relanzó o retiró (`retried_by`, `discarded_by`), qué dispositivo lo reclamó
(`claimed_by`) y quién cambió el mapa (`_print_route.updated_by`) o dio de alta el dispositivo
(`_print_host.registered_by`). Los avisos `…print.due` del
registro de avisos se borran a los 90 días; la fila de la cola no.
En este mismo documento se apoya en: HUB-F242 (Restablecer el hub), HUB-F248 (Borrar los datos de una persona: el aviso único), HUB-F249 (Vaciar el historial del hub que nombra a la persona), HUB-F253 (Purgar el historial por retención).
Si falla: el borrado de un cliente (hub#2467) vacía la copia del aviso `…print.due` ya entregado si lleva su id, pero no la fila de la cola: un cliente que pide el borrado de sus datos sigue en ella y no hay forma de
quitarlo, salvo reiniciar todo el negocio. Tampoco hay límite de tamaño ni de edad.
Implicados: ninguno
QA: ninguno

### HUB-F207 Abrir el cajón por la impresora (lo que sabe el servidor)
Estado: parcial — el hub no participa: no hay forma de abrir el cajón desde el servidor, ni cola, ni registro de quién lo abrió, ni una apertura manual; y si el dispositivo que cobró no llega a la impresora o ésta contesta con error, el cajón no se abre y nadie lo sabe
Actor: empleado, sistema
Pantalla: ninguna
Pasos:
1. Con «Abrir cajón al cobrar» activado en Impresión, el dispositivo que cobró (el único que reacciona a su
   venta) lee la impresora de la función Recibo y le manda el pulso (HUB_PERIPHERALS-F15).
2. Si ese dispositivo no llega a esa impresora, no se abre.
Entra: el ajuste «Abrir cajón al cobrar» (de Impresión) y la venta cobrada.
Sale: nada en el hub. El pulso no es un documento, no entra en la cola, no queda guardado ni se difunde.
Se abre con cualquier forma de pago (no solo efectivo) y siempre por el pin 2.
Si falla: con una impresora de Recibo USB no se abre nunca (la resolución del shell descarta las USB); el error de la impresora se descarta sin aviso; si el dispositivo está en un navegador, no se
abre. No existe «Abrir cajón / sin venta» con permiso y registro.
Implicados: HUB_PERIPHERALS-F15, HUB_APP-F21, HUB_SHELL-F71, PRINTING-F13, SALES-F01
QA: qa-hub §8

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Cola en el servidor con clave por trabajo | hecho para lo que pasa por la cola; el camino directo de la caja no deja fila | HUB-F190, HUB-F191, HUB-F192 |
| Estaciones como filas y mapa documento → estación | hecho; sin pantalla | HUB-F193, HUB-F194, HUB-F195 |
| Hosts múltiples por función, latido, retirar | parcial: retirar solo por API, el dispositivo retirado se vuelve a dar de alta y una función quitada no se da de baja | HUB-F196, HUB-F197 |
| Canal en vivo con aviso «hay trabajo» | parcial: el aviso no llega con función omitida o escrita distinto, ni por la puerta de módulos, ni al reintentar un trabajo muerto ni cuando vuelve a la cola por un fallo | HUB-F190, HUB-F191, HUB-F198, HUB-F204 |
| Trabajo en espera sin impresora y alarma | hecho | HUB-F201, HUB-F202 |
| Reintentar y descartar con sello | hecho | HUB-F204, HUB-F205 |
| «Hecho» solo cuando sale el papel | parcial: `erplora_print` contesta Ok al encolar en memoria (`apps/tauri/src-tauri/src/lib.rs:1671-1683`) | HUB-F199 |
| Retención y borrado RGPD de la cola | no hecho | HUB-F206 |
| Cajón desde el servidor / sin venta | no hecho | HUB-F207 |

## Datos: de quién es cada dato

Del hub, por `hub_id`: la cola de trabajos (`_print_queue`, con el documento entero), las funciones
(`_print_station`), el mapa (`_print_route`) y los dispositivos que imprimen (`_print_host`: quién y
cuándo los dio de alta, nombre del dispositivo).

Datos personales: el documento dentro de la cola (cliente, NIF, mesa, camarero, etiqueta de comanda
con nombre de cliente), el motivo libre de un descarte, `claimed_by` (dispositivo),
`retried_by`/`discarded_by` (persona), `_print_route.updated_by` y `_print_host.registered_by`. El
borrado de un cliente (hub#2467) vacía la copia del aviso `…print.due` ya entregado si lleva su id,
pero no la fila de la cola. No se purga (HUB-F206); restablecer el hub vacía la cola y conserva los
dispositivos (HUB-F242).

## Reglas que no se rompen

- Aislamiento por hub en toda lectura y escritura; la clave `(hub, jobId)` es única.
- Vocabulario cerrado de ocho documentos.
- Solo un dispositivo dado de alta de una función saca sus trabajos (dos negativas distintas).
- El documento sale de la cola solo por el canal con sesión y registro; por la puerta de módulos
  viaja también dentro del aviso `…print.due`, visible para el administrador en Eventos caídos.
- Reintentar y descartar exigen administrador y, si lo pide un módulo, el permiso de impresora de ese
  módulo; descartar nunca borra.

## Lo que NO hace, a propósito

- No se niega a cobrar sin impresora.
- No compone el papel.
- No abre el cajón.
- No enruta por categoría de producto.

## Dudas abiertas

1. ¿«Hecho» debe significar papel salido (el dispositivo debe devolver el fallo de red)?
2. ¿Cuánto se conserva la cola y cómo se borra a un cliente (RGPD)?
3. ¿Pantalla para el mapa y las estaciones?
4. Idioma del papel por la puerta directa, sin confirmar (la cola sella el `locale` del hub; la
   directa no).
5. ¿Debe despertar al dispositivo un trabajo de módulo o un reintento?
6. Báscula: hub#1217 (ver HUB_PERIPHERALS).

## Fuentes contrastadas

- `architecture/hub/print-queue.md` dice «Tarde, no perdido» y da el aviso en vivo por función: el
  aviso lleva la palabra del productor (HUB-F190).
- El guion de QA §10 espera un trabajo pendiente con la impresora apagada: no ocurre (HUB-F199).
