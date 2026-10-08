# WORKFLOW — Hub · pantallas · Avisos e impresión

Prefijo: HUB_SHELL

> Detalle del índice `apps/web/WORKFLOW.md`. La campana, los avisos del sistema del dispositivo y la
> impresión que hace el shell solo (el tique al cobrar, la comanda al disparar y su vale al cancelarla, el
> dispositivo que saca la cola). Código: `components/AppTopbar.vue` (campana), `lib/bell-counters.ts`,
> `lib/dead-letter.ts`, `lib/print-alert.ts`, `lib/module-update-notice.ts`, `lib/bell-notice.ts`,
> `lib/appointment-notice.ts`, `lib/notice-tap.ts`, `lib/notification-permission.ts`,
> `lib/notice-listening.ts`, `lib/print.ts`, `lib/print-on-sale.ts`, `lib/print-on-sale-notice.ts`,
> `lib/print-comanda.ts`, `lib/print-comanda-notice.ts`, `lib/print-void.ts`, `lib/sale-document.ts`,
> `lib/print-enqueue.ts`, `lib/print-host.ts`, `lib/print-host-registration.ts`,
> `lib/print-drain.ts`, `lib/print-coverage.ts`, `lib/receipt-template.ts`, `lib/native-print.ts`,
> `lib/printer-discovery.ts`, `lib/toast.ts`; el cableado en `main.ts` y `App.vue`.
>
> **Los dos caminos del papel.** Cuando este dispositivo tiene una impresora con la función pedida
> (de red o Bluetooth), el papel sale **directo** por ella y el hub no guarda ninguna fila. Cuando no
> la tiene, el trabajo va a la **cola del hub** y lo saca el dispositivo dado de alta para esa
> función. Desde hub#2494 la app instalada contesta lo que pasó con el papel (espera a la
> impresora de red; con ella apagada, «impresora inalcanzable» a los ~13 s): por el directo la caja
> lo avisa con un aviso fijo y «Reintentar» (tique, comanda y vale); por la cola el dispositivo
> contesta «falló» y el trabajo vuelve a la cola sin que nadie lo vea (HUB_SHELL-F74). Una impresora
> de red encendida pero sin papel sigue contestando «hecho» (HUB_PERIPHERALS-F06).

## Referencia adoptada

- **Impresión al cobrar y comanda al disparar** (Toast, Square for Restaurants, Lightspeed): el
  tique sale en el terminal que cobró; la comanda nace al enviar, no al cobrar; la cabecera lleva
  quién la disparó. Contrastado en `qa-hub-restaurant.md` §2 y `sales/WORKFLOW.md`.
- **Avisos que abren lo que avisó** (Square, Shopify Inbox, Zendesk, según hub#2305) y **campana
  derivada sin «marcar como leído»** (ADR-0067: se limpia cuando se arregla la causa).

## Antes de empezar

- Para imprimir sin diálogos: la app instalada en el dispositivo conectado a la impresora, con la
  impresora dada de alta y con su función («Recibo», «Cocina», «Barra») en Impresión. Ese
  dispositivo se da de alta solo al arrancar con sesión (HUB_SHELL-F73).
- Para recibir avisos con la pantalla apagada: la app instalada en Android con los avisos
  permitidos (HUB_SHELL-F68, F69). En un navegador no hay avisos del sistema; solo la campana.
- «Abrir cajón al cobrar» e «Imprimir ticket al cobrar» se encienden en los ajustes de Impresión.

## Flujos

### HUB_SHELL-F60 Ver en la campana lo que espera atención
Estado: parcial — la fila de impresión parada nombra la función por su clave interna («Nadie está imprimiendo «kitchen»»), la de eventos caídos habla del «relay», y las filas se refrescan cada 30 o 60 s, no al momento
Actor: empleado, responsable, administrador
Pantalla: Campana de notificaciones
Pasos:
1. Arriba a la derecha está la campana con un número rojo: la suma de todo lo que espera. En el móvil, la campana está dentro del menú «más» de la barra, con el mismo número.
2. Al tocarla se abre la lista «Notificaciones», con una fila por cosa pendiente, y cada fila lleva a donde se arregla:
3. «Eventos caídos» (solo administrador) → Sistema, pestaña de eventos (HUB_SHELL-F62).
4. «Nadie está imprimiendo «{función}»», una por función (para todos) → Ajustes › Impresión (HUB_SHELL-F63).
5. «Actualizaciones de apps» (solo administrador) → «Mis apps»; si no se pudo comprobar, «No se ha podido comprobar si hay actualizaciones» con «Comprobar de nuevo».
6. Lo que ponen las apps (citas por confirmar, clientes de WhatsApp esperando), cada una con su número → la pestaña de esa app (HUB_SHELL-F61).
7. Sin nada pendiente: «Todo al día. Sin notificaciones.».
8. El número baja solo cuando se resuelve la causa: no hay «marcar como leído».
Entra: cuatro fuentes que el shell consulta por su cuenta: el número de eventos caídos (cada 60 s, HUB-F59), las funciones de impresión sin atender (cada 30 s, HUB-F201), los contadores que declaran las apps (cada 30 s) y las actualizaciones de apps (cada varias horas, HUB-F24).
Sale: nada guardado.
Si falla: una consulta que no llega deja el número que había (un hub caído no se lee como «todo al día»); en eventos caídos, una respuesta de rechazo pone 0. Con la pestaña del navegador escondida solo siguen los contadores de las apps. Al cambiar de persona con el PIN se recalculan al momento los contadores de las apps y las actualizaciones; «Eventos caídos» e impresión esperan a su siguiente vuelta (un empleado que releva a un administrador puede ver «Eventos caídos» hasta 60 s). Las filas «Eventos caídos» y «Nadie está imprimiendo» navegan sin cerrar la lista (sin confirmar en pantalla si se queda abierta encima).
Implicados: HUB-F24, HUB-F59, HUB-F201
QA: ninguno

### HUB_SHELL-F61 Atender desde la campana lo que pone una app
Estado: hecho
Vertical: comun
Actor: empleado, responsable, administrador
Pantalla: Campana de notificaciones
Pasos:
1. Una app declara un contador para la campana: hoy Citas («Citas por confirmar») y WhatsApp («Clientes de WhatsApp esperando respuesta»), con el nombre que trae su traducción.
2. Cuando hay algo, la campana enseña la fila con su icono y su número.
3. La persona la toca y se abre la pestaña de la app que declaró el contador (la agenda, la bandeja).
4. Cuando lo atiende, el número baja en la siguiente vuelta (como mucho 30 s).
Entra: el bloque `bell` del `module.json` de cada app activa (una consulta de la propia app que devuelve `count`, su permiso y su pestaña); la consulta se hace con la sesión de quien mira.
Sale: nada.
Si falla: un contador cuyo permiso no tiene la persona no aparece. Un contador que pida una consulta de otra app se ignora. Si la consulta falla, queda el último número conocido.
Implicados: APPOINTMENTS-F03, APPOINTMENTS-F18, REC_WA_CITA-F09, REC_WA_MESA-F09, WHATSAPP_INBOX-F09
QA: ninguno

### HUB_SHELL-F62 Ver en la campana los avisos entre apps que no se entregaron
Estado: parcial — la fila no dice qué falló ni de qué documento (una venta sin factura se ve igual que cualquier otro aviso) y solo la ve un administrador
Actor: administrador
Pantalla: Campana de notificaciones
Pasos:
1. Un aviso entre apps (p. ej. «venta cobrada» hacia Facturación) agotó sus reintentos y quedó caído.
2. En la siguiente vuelta (como mucho 60 s, con la pestaña a la vista), la campana de un administrador sube y enseña «Eventos caídos» — «Hay {count} evento que el relay no pudo entregar. Revísalo y reenvíalo.».
3. Al tocarla se abre Sistema en la pestaña de eventos caídos, donde se reenvía o se descarta.
4. Cuando no queda ninguno, la fila desaparece.
Entra: el número de caídos (HUB-F59), pedido solo con la sesión de un administrador.
Sale: nada.
Si falla: un empleado o un responsable no ve la fila. Un fallo al preguntar deja el número anterior.
Implicados: HUB-F59, INVOICE-F06, REC_FISCAL-F09
QA: BD-09

### HUB_SHELL-F63 Ver en la campana que nadie está imprimiendo una función
Estado: parcial — la función sale con su clave interna («kitchen», «receipt») en lugar de «Comandas de cocina» o «Tiques de venta»
Actor: empleado, responsable, administrador
Pantalla: Campana de notificaciones
Pasos:
1. Hay trabajos de una función esperando en la cola del hub y ningún dispositivo vivo para sacarlos desde hace al menos 1 minuto.
2. En la siguiente vuelta (como mucho 30 s), la campana de todos los que están conectados sube y enseña «Nadie está imprimiendo «{función}»» — «Hay {count} documento esperando desde hace {minutes} min. Comprueba que la caja que imprime ahí está encendida.».
3. Al tocarla se abre Ajustes › Impresión, con el estado por función (HUB_SHELL-F75).
4. Cuando un dispositivo de esa función se conecta y vacía lo pendiente, la fila desaparece.
Entra: las funciones sin atender, ya decididas por el hub (`GET /api/print/undrained`, HUB-F201): cuántos esperan y desde cuándo.
Sale: nada.
Si falla: solo ve lo que pasó por la cola del hub. Un tique impreso directo que no salió (impresora apagada) no llega nunca aquí: lo avisa la caja que lo pidió, con «Reintentar» (HUB_SHELL-F70). Un dispositivo cuenta como vivo, y la fila no sale, aunque no saque nada: si dejó de tener esa función en la app pero sigue dado de alta; si su canal de impresión se paró para siempre por un rechazo (sesión caducada al reconectar, retirada, saludo tardío) mientras su alta sigue latiendo; o si un trabajo le falló y nadie lo vuelve a pedir (HUB_SHELL-F74). Los trabajos se apilan hasta reiniciar la app de ese dispositivo.
Implicados: HUB-F201, HUB-F202
QA: qa-hub §8, qa-hub-restaurant §16

### HUB_SHELL-F64 Recibir un aviso del sistema cuando sube un contador de la campana
Estado: hecho
Vertical: comun
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Entre dos vueltas de la campana sube el contador de una app (un cliente de WhatsApp pasa a una persona).
2. En la app instalada, el dispositivo enseña un aviso del sistema «{contador} ({número})» — «Míralo en la campana para atenderlo.».
3. Tocarlo abre la pestaña de esa app (HUB_SHELL-F67).
Entra: la subida de un contador respecto a la vuelta anterior de la misma sesión.
Sale: la notificación del dispositivo.
Si falla: lo que ya esperaba al entrar no avisa (es lo pendiente, no algo nuevo). Las citas no avisan por aquí: tienen su aviso propio (HUB_SHELL-F66). En el navegador no hay aviso del sistema. Con los avisos denegados no se intenta.
Implicados: HUB_APP-F24, HUB_APP-F25, REC_WA_CITA-F09, REC_WA_MESA-F09, WHATSAPP_INBOX-F09
QA: ninguno

### HUB_SHELL-F65 Recibir el aviso del sistema «Nueva comanda»
Estado: hecho
Vertical: restaurante
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Una camarera dispara una ronda (o entra un pedido por la API o un flujo).
2. Cada dispositivo con el hub abierto en la app instalada enseña «Nueva comanda · {mesa}» (o «Nueva comanda» sin etiqueta) con el número del pedido y «{n} líneas».
3. Sale también en el dispositivo que la disparó y aunque la comanda sea solo de pantalla.
4. Tocarlo abre Cocina.
Entra: el aviso en vivo de comanda creada (`kitchen.order.created`, HUB-F60) y la cabecera y las líneas de la comanda, leídas a Cocina.
Sale: la notificación del dispositivo, antes de imprimir nada.
Si falla: un fallo del aviso no frena la impresión. Si la pantalla estaba desconectada del canal en vivo cuando nació la comanda, no hay aviso (el canal no guarda nada). En el navegador no hay aviso del sistema.
Implicados: HUB-F60, HUB_APP-F24, KITCHEN-F05
QA: qa-hub-restaurant §08

### HUB_SHELL-F66 Recibir el aviso del sistema de una cita nueva o cancelada
Estado: hecho
Vertical: peluqueria
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Una clienta pide o cancela una cita por WhatsApp, por la web o un flujo, sin pasar por una caja.
2. Los dispositivos con la app instalada enseñan «Nueva cita · {clienta}» o «Cita cancelada · {clienta}», con el servicio, «{fecha} a las {hora}» y la profesional.
3. Tocarlo abre Citas.
Entra: los avisos en vivo de cita creada o cancelada y la ficha de la cita, leída a Citas.
Sale: la notificación del dispositivo.
Si falla: una cita dada desde una caja no avisa (quien la dio ya lo sabe). Si la ficha no se puede leer, se usa lo que traía el aviso.
Implicados: APPOINTMENTS-F06, APPOINTMENTS-F18, HUB-F60, HUB_APP-F24
QA: B-02

### HUB_SHELL-F67 Tocar un aviso del sistema y abrir su pantalla
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Aviso del sistema
Pasos:
1. La persona toca un aviso del sistema del hub (comanda, cita, contador de la campana).
2. La app pasa al frente y abre la pantalla de la que habla el aviso, aunque estuviera en otra.
3. Si la app estaba cerrada (Android) o el aviso se pulsó en el ordenador, al abrirse va también a esa pantalla.
Entra: el número del aviso, y la pantalla que se le dio al mandarlo.
Sale: nada.
Si falla: solo se sigue una dirección que es una pantalla del hub; cualquier otra cosa deja la app donde estaba. La app recuerda los 50 últimos avisos. Un mismo toque no abre dos veces.
Implicados: HUB_APP-F25, KITCHEN-F05
QA: ninguno

### HUB_SHELL-F68 Permitir los avisos del sistema en el dispositivo
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Aviso del sistema
Pasos:
1. La primera vez que alguien entra en un dispositivo con la app instalada, el dispositivo se da de alta como el que imprime o llega el primer aviso (comanda, cita, contador) a un dispositivo al que nunca se le preguntó, y solo si el hub tiene algo que avisar (Cocina, Citas o una app con contador en la campana), sale la hoja «Deja que te avisemos» — «Cuando algo necesite tu atención podemos avisarte, aunque nadie esté mirando esta pantalla. Tu dispositivo te lo preguntará a continuación.».
2. «Activar los avisos» abre la pregunta de Android; «Ahora no» la cierra.
3. Se pregunta una sola vez por instalación.
4. Si se denegó, Sistema enseña «Los avisos están desactivados» con «Activar los avisos»; si Android ya no vuelve a preguntar, dice cómo hacerlo en los ajustes del dispositivo.
Entra: qué apps están activas y cuáles ponen contador en la campana; el estado del permiso en Android.
Sale: el permiso del dispositivo; la marca de «ya preguntado» guardada en el dispositivo.
Si falla: con el permiso denegado no se manda ningún aviso (mandarlo haría saltar la pregunta pelada de Android en mitad del servicio). En el ordenador, en el navegador y en Android anterior a 13 no hay nada que pedir: no sale ni la hoja ni la fila.
Implicados: HUB_APP-F07, HUB_APP-F08
QA: qa-hub-android §Fase 2

### HUB_SHELL-F69 Seguir recibiendo avisos con la pantalla apagada
Estado: hecho
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Con una sesión abierta en Android, el hub con algo que avisar y los avisos permitidos, la app se queda a la escucha y lo dice con una notificación fija «ERPlora está a la escucha» — «Te avisará cuando algo necesite tu atención, aunque la pantalla esté apagada.».
2. Con la pantalla apagada o la app al fondo siguen llegando los avisos (comanda, cita, campana).
3. Al cerrar la sesión deja de escuchar.
Entra: la sesión, el permiso y las apps activas.
Sale: el servicio de escucha de Android encendido o apagado.
Si falla: si no se puede encender, se anota y los avisos solo llegan con la app delante. Fuera de Android no hace nada.
Implicados: HUB_APP-F26
QA: ninguno

### HUB_SHELL-F70 Imprimir el tique al cobrar, solo en el dispositivo que cobró
Estado: parcial — por la cola, con la impresora de red de quien la saca apagada, el tique vuelve «fallido» sin aviso (HUB_SHELL-F74), y una impresora de red sin papel pero encendida se da por impresa (HUB_PERIPHERALS-F06); si la pantalla estaba desconectada del canal en vivo al cobrar, o se recargó antes de oír la venta, no se imprime ni se avisa; la hora del papel es la de imprimir; y el papel no lleva quién atendió
Vertical: comun
Actor: sistema
Pantalla: sales: Cobro
Pasos:
1. La cajera cobra con «Imprimir tiquet» encendido (o con el ajuste de Impresión, si la venta no dice nada).
2. Solo la pantalla que mandó el cobro reacciona; las demás cajas abiertas no imprimen ni avisan.
3. Ventas compone el papel y espera hasta unos 10 s al número fiscal y al QR de VeriFactu; si en 15 s no hay papel, sale «El tique no se pudo preparar…».
4. Camino directo: si este dispositivo tiene una impresora con función «Recibo» (de red o Bluetooth), el tique sale por ella. El hub no guarda nada.
5. Camino por la cola: si no la tiene (un navegador, un móvil sin impresora), el tique se encola en el hub y lo saca el dispositivo dado de alta para «Recibo» (HUB_SHELL-F74).
6. Si la impresora «Recibo» de este dispositivo no lo coge (apagada, fuera de la red), a los ~13 s sale un aviso rojo que **se queda** hasta que la cajera actúa: «El tique NO se imprimió: la impresora no contesta. Comprueba que está encendida y con papel y pulsa «Reintentar».», con los botones «Reintentar» (vuelve a sacar ese mismo tique; si vuelve a fallar, vuelve a avisar con su «Reintentar») y «OK». No se manda a la cola: quien la saca es este mismo dispositivo, con la misma impresora apagada (hub#2494).
7. Si salió antes de que el QR estuviera listo: «El tique salió antes de que estuviera listo su QR de VeriFactu. Vuelve a imprimirlo desde la pantalla del tique para darle al cliente el completo.».
Entra: el aviso en vivo «venta cobrada» con la pantalla que la mandó (`sale.completed`, HUB-F60); los ajustes de Impresión; el papel que compone Ventas (`erp-sales-document`).
Sale: el papel, o un trabajo en la cola del hub con clave `sale-<id>` (HUB-F190).
Si falla: la venta nunca se cae. En la caja sale: «El tique está en espera: aún no hay ninguna impresora dada de alta. Da una de alta y saldrá solo.» (en cola sin nadie); «El tique NO se imprimió. Vuelve a imprimirlo desde la pantalla del tique.» (no hay impresora ni cola); «El tique no se pudo preparar y NO se imprimió. Imprímelo desde la pantalla del tique.». Por el directo con la impresora de red apagada, el aviso fijo con «Reintentar» del paso 6; el hub no tiene fila. Por la cola, el dispositivo que la saca contesta «falló» y el trabajo vuelve a la cola sin aviso en la caja (HUB_SHELL-F74). Una venta hecha por la API o un flujo no la imprime ninguna caja. Sin Impresión instalada, o si la persona no puede leer sus ajustes (un rol personalizado sin `printing.view_settings`), no se imprime ni se avisa. Con más de 16 pantallas de la misma persona conectadas al canal en vivo, la 17.ª no oye la venta; una pantalla cuya persona no puede leer Ventas tampoco la oye (HUB-F60). Si el tique fue por la cola y el dispositivo que la saca tiene el canal parado o le falló, se queda esperando sin aviso en la caja ni fila en la campana (HUB_SHELL-F74).
Implicados: HUB-F60, HUB-F190, HUB-F199, HUB_PERIPHERALS-F06, PRINTING-F07, REC_FISCAL-F07, SALES-F01
QA: R-09, L-04, qa-hub §8 (discrepa)

### HUB_SHELL-F71 Abrir el cajón al cobrar
Estado: parcial — se abre con cualquier forma de pago (no solo efectivo), siempre por el pin 2, nunca con una impresora USB ni desde el navegador; si no se abre, el error se descarta y nadie lo sabe; no hay «Abrir cajón» manual ni «Sin venta»
Vertical: comun
Actor: sistema
Pantalla: sales: Cobro
Pasos:
1. Con «Abrir cajón al cobrar» encendido en Impresión, la cajera cobra.
2. La pantalla que cobró manda el pulso a la impresora con función «Recibo» de este mismo dispositivo, a la vez que el tique y sin esperarlo.
3. El cajón se abre.
Entra: el ajuste de Impresión; la impresora «Recibo» de red o Bluetooth del dispositivo.
Sale: el pulso; nada guardado ni en cola: el cajón está aquí o no está.
Si falla: sin impresora «Recibo» alcanzable, en el navegador, con una USB o con la impresora sin contestar, el cajón no se abre y no sale ningún aviso (`print-on-sale.ts:194-195`, leído en el código, sin ejecutar).
Implicados: HUB-F207, HUB_PERIPHERALS-F15, PRINTING-F13, SALES-F01
QA: R-09, qa-hub §8

### HUB_SHELL-F72 Imprimir la comanda al disparar la ronda, solo en el TPV que la envió
Estado: parcial — por la cola, con la impresora de quien la saca apagada, la comanda vuelve «fallida» sin aviso (HUB_SHELL-F74); si no se pueden leer las líneas de la comanda, no se imprime nada y tampoco se avisa; y la hora del papel es la de imprimir
Vertical: restaurante
Actor: sistema
Pantalla: sales: Vender
Pasos:
1. La camarera dispara una ronda desde el TPV.
2. La pantalla que la disparó lee las líneas en Cocina y las agrupa por la función de impresora de su estación («Cocina», «Barra»); lo que va solo a pantalla no se imprime; una línea sin estación sale por «Cocina».
3. Sale una hoja por función, con la mesa, la ronda, el número, quién la disparó (su nombre, nunca un identificador), las cantidades, los suplementos, la marca de menú y «URGENTE» si la ronda es urgente.
4. Directo si este dispositivo tiene la impresora de esa función; si no, por la cola del hub. Una comanda que no disparó ninguna caja (API, automatización, pedido online) la encola cada pantalla abierta y conectada al canal en vivo cuando nace, con la misma clave, así que queda un solo trabajo.
5. Las demás cajas no imprimen; solo dan el aviso «Nueva comanda» (HUB_SHELL-F65).
Entra: el aviso de comanda creada con la pantalla que la mandó; las líneas y la cabecera (de Cocina); el nombre de quien la disparó, leído a la lista de personas del hub y, si no está, al equipo de Personal.
Sale: una hoja por función, clave `kitchen-<pedido>-<función>`.
Si falla: nunca bloquea a la camarera. Una comanda sin caja que la disparó, con todas las pantallas cerradas o desconectadas (un pedido online de madrugada), no la encola nadie: ni papel ni aviso; y si la cola no tiene quien la saque, cada pantalla abierta saca el aviso de espera. Avisos: «No se imprimió la comanda de {estación} de {mesa}. Revisa la impresora y avisa en {estación}: la comanda está en la pantalla de cocina.» — si fue la impresora de esa estación de este dispositivo la que no contestó, el aviso se queda hasta que la camarera actúa y lleva «Reintentar», que vuelve a sacar solo la hoja de esa estación (la otra ya tiene la suya; hub#2494); «La comanda de {estación} de {mesa} está en espera: aún no hay ninguna impresora dada de alta para esa estación. Da una de alta y saldrá sola.». Nunca se desvía a la impresora de tiques. Sin nombre que poner (la persona ya no está, no se pudo leer), la línea de camarero no sale.
Implicados: HUB-F60, HUB-F190, HUB_PERIPHERALS-F06, HUB_PERIPHERALS-F10, KITCHEN-F08, PRINTING-F10, STAFF-F09
QA: qa-hub-restaurant §08, BD-08

### HUB_SHELL-F73 Dar de alta este dispositivo como el que imprime
Estado: parcial — una impresora USB nunca da de alta al dispositivo; quitarle la función a una impresora (o borrarla) no lo da de baja en el hub, que sigue contándolo como vivo para esa función; y el alta sigue latiendo aunque el canal de impresión se haya parado para siempre (sesión caducada al reconectar, retirada por el hub, saludo tardío): el dispositivo cuenta como vivo sin sacar nada hasta reiniciar la app
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar la app instalada con una sesión abierta, el shell mira las impresoras de este dispositivo.
2. Si hay una sola impresora de red y ninguna tiene función, le pone «Recibo» (una Bluetooth no; solo al arrancar).
3. Por cada función de una impresora de red o Bluetooth, le dice al hub «yo imprimo esta función» y, desde entonces, da señales de vida cada 30 s y vuelve a mirar si hay funciones nuevas.
4. La primera vez que el hub lo acepta, empieza a sacar la cola (HUB_SHELL-F74) y, si el hub tiene algo que avisar, pide el permiso de avisos (HUB_SHELL-F68).
5. La tarjeta «Estado de impresión» de Ajustes › Impresión dice «Imprimiendo en {dispositivo}» la próxima vez que se abre la pestaña (no se refresca sola).
Entra: las impresoras y funciones del dispositivo (HUB_PERIPHERALS-F04); el identificador del dispositivo y la sesión.
Sale: el alta en el hub por función (HUB-F196) y su latido (HUB-F197).
Si falla: en un navegador (sin identificador de dispositivo o sin hardware) no se da de alta nada. Un rechazo del hub solo se anota en la consola. Sin sesión, espera a que alguien entre.
Implicados: HUB-F196, HUB-F197, HUB_APP-F18, HUB_PERIPHERALS-F04, PRINTING-F04
QA: qa-hub §8, qa-hub-android §Fase 2

### HUB_SHELL-F74 Sacar los trabajos de la cola y confirmar que salieron
Estado: parcial — desde hub#2494 el dispositivo confirma «salió» cuando el papel llegó a la impresora y «falló» cuando no, pero un trabajo que falla vuelve a la cola sin despertar a nadie ni avisar en la caja o en la cocina
Actor: sistema
Pantalla: ninguna
Pasos:
1. Dado de alta, el dispositivo abre el canal de impresión del hub y se presenta con su sesión e identificador.
2. Pide el trabajo de cada una de sus funciones; el hub le entrega el más antiguo.
3. Lo manda a su impresora con esa función y espera: contesta «salió» cuando la impresora se queda el papel y «falló» con el motivo cuando no (una de red apagada, a los ~13 s).
4. Cuando no queda nada, espera a que el hub le avise de que hay trabajo.
5. Si se cae la conexión, se reconecta esperando cada vez más, y vuelve a confirmar lo que imprimió y no llegó a confirmar, para no sacar dos papeles.
Entra: los trabajos de la cola, con el documento ya compuesto (HUB-F198, HUB-F199).
Sale: «salió» o «falló» con el motivo por cada trabajo.
Si falla: si el dispositivo no puede imprimirlo (ya no tiene impresora con esa función, «no printer on this device holds the … role»; una Bluetooth o una de red que no contesta), contesta «falló» y deja de pedir esa función. El trabajo vuelve a la cola, pero el hub no despierta a nadie: nadie lo vuelve a pedir hasta que llega otro de esa función o el dispositivo se reconecta; a los 5 intentos muere. Mientras, el dispositivo late y cuenta como vivo, y la campana calla. Si el hub le dice que no imprime nada aquí, que la sesión no vale o que saludó tarde, el canal se para para siempre (no reintenta en bucle) y solo lo anota en la consola, pero el alta sigue latiendo por su lado (HUB_SHELL-F73).
Implicados: HUB-F198, HUB-F199, HUB-F200, HUB_APP-F18, HUB_PERIPHERALS-F06, PRINTING-F14
QA: qa-hub-restaurant §16

### HUB_SHELL-F75 Ver quién imprime cada función
Estado: parcial — la tarjeta calcula su propio estado con lo que esperan y los vivos, en vez de usar el «sin atender» que ya decide el hub; un dispositivo que ya no tiene esa función, o cuyo canal se paró (HUB_SHELL-F73, F74), sale como «Imprimiendo en …» mientras los trabajos se apilan; solo se lee al abrir la pestaña; y una función sin trabajos ni dispositivos no aparece
Actor: empleado, responsable, administrador
Pantalla: Ajustes › Impresión
Pasos:
1. La persona abre Ajustes, pestaña «Impresión» (o llega desde la fila de la campana). La tarjeta se vuelve a pedir cada vez que se entra en la pestaña.
2. Si hay algo que contar (el hub devuelve alguna función: un negocio que nunca ha impreso no ve nada), ve «Estado de impresión» — «Qué dispositivos están sacando cada tipo de tique ahora mismo.», con una fila por función («Tiques de venta», «Comandas de cocina», «Comandas de barra», «Etiquetas»):
3. «Imprimiendo en {dispositivos}» en verde si hay alguno vivo (cada uno por su nombre; el que no tiene, por los cuatro últimos caracteres de su identificador, «…e7f8», nunca el identificador entero, hub#2551); «Nadie está imprimiendo esto — {n} tiques en espera» en rojo si hay trabajo y nadie; «El dispositivo que imprimía esto no responde» en ámbar si no hay nadie y nada espera.
4. Debajo de las dos últimas: «Abre la app de ERPlora en el equipo conectado a esta impresora.».
5. Este flujo recoge también el antiguo HUB_SHELL-F166 «Ver quién está sacando cada tipo de tique» (área de ajustes), retirado por describir la misma tarjeta; la pestaña Impresión es de Ajustes, la tarjeta de esta área.
Entra: los dispositivos dados de alta y la cobertura por función (`GET /api/print/hosts`, HUB-F202).
Sale: nada.
Si falla: «No se ha podido comprobar quién está imprimiendo ahora mismo.» (nunca una pantalla verde vacía ni filas inventadas). Un negocio que nunca imprimió no ve la tarjeta. Una función que no está en el catálogo sale con su clave. Un tique impreso directo nunca aparece aquí.
Implicados: HUB-F201, HUB-F202, PRINTING-F01
QA: qa-hub §8

### HUB_SHELL-F76 Saber qué sale en el papel del tique y dónde se cambia
Estado: parcial — la fecha y la hora del papel son las del reloj del dispositivo al imprimir (una reimpresión o un tique que esperó en la cola lleva otra hora), y el papel no lleva el nombre de quien atendió aunque la impresora sabe pintarlo
Vertical: comun
Actor: administrador, responsable
Pantalla: Ajustes › Impresión
Pasos:
1. En Ajustes › Impresión, la fila «Impresoras y tique» — «Da de alta tu impresora y configura el tique impreso y digital» lleva a la pantalla de Impresión; sin esa app, dice «Instala la app Impresión para dar de alta tu impresora y configurar el tique» y lleva a Apps.
2. El tique lo compone Ventas, igual que el botón de imprimir de la pantalla del tique: nombre, dirección y NIF del negocio, número, cliente, líneas con su importe y notas, subtotal, IVA, total, forma de pago, entregado y cambio, el QR de VeriFactu con su leyenda, el bloque «pide tu factura», el QR promocional y el pie.
3. La impresora añade la fecha y la hora, que son las de su reloj en el momento de imprimir.
4. La cabecera y el pie se cambian en los ajustes de Ventas.
Entra: el papel de Ventas (`printableDocument`); los decimales de la moneda del hub.
Sale: nada.
Si falla: el primer papel de una venta sale como original y los siguientes del mismo dispositivo como «DUPLICADO».
Implicados: HUB_PERIPHERALS-F09, PRINTING-F07, SALES-F29, SALES-F34
QA: L-04

### HUB_SHELL-F77 Imprimir un documento desde una pantalla
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. En una app, la persona pide imprimir algo (la cuenta de la mesa, una factura, una etiqueta, el cierre de caja).
2. Si el documento es de rollo y este dispositivo tiene una impresora con esa función, sale directo.
3. Si no la tiene, se encola en el hub y lo saca el dispositivo de esa función.
4. Una factura o un albarán en A4 dentro de la app instalada abre el diálogo de impresión del sistema (con «Guardar como PDF»); en un navegador, su diálogo de imprimir con solo el documento.
5. La app dice lo que pasó con lo que le contesta la puerta.
Entra: la petición de la app (función, tipo de documento, documento, papel), por la puerta única del shell (`erplora.print`): ninguna app abre el hardware ni el diálogo del navegador por su cuenta.
Sale: el papel, un trabajo en la cola (HUB-F190) o el diálogo de impresión.
Si falla: dentro de la app instalada no hay respaldo de navegador: si no hay impresora ni cola, la respuesta es «no salió» y la app avisa. Un documento sin contenido estructurado no se encola (saldría en blanco). Con la impresora de red de este dispositivo apagada, la respuesta es «no salió» con `printerFailed` y la app que lo pidió decide cómo avisarlo (el aviso con «Reintentar» del shell es el del tique, la comanda y el vale).
Implicados: HUB-F190, HUB_APP-F22, HUB_PERIPHERALS-F06, INVENTORY-F25, KITCHEN-F14, KITCHEN-F17, KITCHEN-F20, PRINTING-F09
QA: qa-hub §8

### HUB_SHELL-F78 Imprimir el vale de anulación al cancelar una ronda o anular un plato ya enviados
Estado: parcial — por la cola, con la impresora de quien la saca apagada, el vale vuelve «fallido» sin aviso, como la comanda (HUB_SHELL-F74); y si la cancelación o la anulación no la hizo ninguna caja y todas las pantallas están cerradas, no lo encola nadie
Vertical: restaurante
Actor: sistema
Pantalla: kitchen: Comandas
Pasos:
1. Un responsable cancela una ronda en **Cocina → Comandas** (KITCHEN-F22), o se elimina la cuenta que la envió y Cocina cancela sus rondas en marcha (KITCHEN-F28).
2. La pantalla que canceló lee en Cocina las líneas de esa ronda (siguen ahí, canceladas) y las agrupa como la comanda: una hoja por función de impresora («Cocina», «Barra»); lo que fue solo a pantalla no imprime nada, una ronda que no salió en papel no saca vale, y un plato que el TPV ya había anulado no vuelve a salir (ya tuvo su vale).
3. Sale una hoja por función, en la misma impresora que sacó la comanda: «ANULADA · Mesa 4» (o «ANULADA» sin etiqueta) donde va la mesa, en doble altura, el número y la ronda, y cada plato con la cantidad en negativo («-2x Croquetas»), con sus suplementos y su nota. Nunca lleva «URGENTE».
4. Directo si este dispositivo tiene la impresora de esa función; si no, por la cola del hub. Las demás pantallas no imprimen. Una cancelación que no hizo ninguna caja (el asistente, la API, un flujo) la encola cada pantalla abierta y conectada, con la misma clave, así que queda un solo vale.
5. Si en el TPV se anula **un plato** ya enviado (KITCHEN-F29) y Cocina lo tacha, la pantalla que lo anuló saca su vale con solo ese plato: «PLATO ANULADO · Mesa 4» (o «PLATO ANULADO» sin etiqueta) y el plato en negativo («-1x Croquetas»), en la impresora de su función, por el mismo camino del paso 4. Un menú anulado entero saca un vale por función con sus platos, no uno por plato; un plato del menú que ya se había servido no entra. Si era el último plato vivo de la ronda, la ronda se cancela y no sale otro vale de ronda encima.
Entra: el aviso en vivo de comanda cancelada (`kitchen.order.cancelled`) o de plato anulado (`kitchen.item.voided`, con la línea de cocina), con la pantalla que lo pidió (HUB-F60); las líneas y la cabecera de la comanda, de Cocina.
Sale: una hoja por función, clave `kitchen-void-<pedido>-<función>` para la ronda y `kitchen-void-<pedido>-<línea de venta>-<función>` para un plato (distintas de la de la comanda, para que la cola no las tome por repetidas); un mismo plato no se imprime dos veces aunque el aviso llegue repetido.
Si falla: nunca bloquea la cancelación ni la anulación. Avisos en la pantalla que canceló: «No se imprimió el vale de anulación de {estación} de {mesa}. Avisa en {estación} de viva voz: esa comanda ya no se prepara.»; «El vale de anulación de {estación} de {mesa} está en espera: aún no hay ninguna impresora dada de alta para esa estación. Avisa en {estación} de viva voz: esa comanda ya no se prepara.». Para un plato, la misma frase con el plato: «No se imprimió el vale de anulación de {plato} para {estación} de {mesa}. Avisa en {estación} de viva voz: ese plato ya no se prepara.» y su versión «está en espera». Si fue la impresora de esa estación de este dispositivo la que no contestó, el aviso se queda hasta que se actúa y lleva «Reintentar», que vuelve a sacar solo ese vale (hub#2494). Sin aviso del sistema del dispositivo. Nunca se desvía a la impresora de tiques. Si no se pueden leer las líneas, no sale nada y no se avisa (como la comanda, HUB_SHELL-F72).
Implicados: HUB-F60, HUB-F190, HUB_PERIPHERALS-F06, HUB_PERIPHERALS-F10, KITCHEN-F22, KITCHEN-F28, KITCHEN-F29
Pendiente de enlazar: printing — PRINTING-F10, la impresora con la función «Cocina» o «Barra» que saca la comanda saca también su vale de anulación
QA: qa-hub-restaurant §7.13

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Campana derivada con destino por fila | parcial (claves internas «kitchen», «relay») | HUB_SHELL-F60…F63 |
| Avisos del sistema que abren su pantalla | hecho (solo app instalada) | HUB_SHELL-F64…F67 |
| Avisos en el navegador (Web Push) | no hecho (por diseño: decisión «sin push FCM por ahora») | — |
| Permiso de avisos en contexto, una vez | hecho | HUB_SHELL-F68 |
| Avisos con la pantalla apagada (Android) | hecho | HUB_SHELL-F69 |
| Tique en el terminal que cobró | parcial (impresora apagada: aviso con «Reintentar» por el directo, mudo por la cola) | HUB_SHELL-F70 |
| Cajón solo con efectivo, «Sin venta» con permiso y registro | no hecho (se abre con cualquier pago, sin manual) | HUB_SHELL-F71 |
| Comanda al disparar, con quién la disparó | parcial (impresora apagada mudo por la cola; lectura fallida mudo) | HUB_SHELL-F72 |
| Alta y baja del dispositivo que imprime | parcial (USB fuera; quitar función no da de baja; canal parado sigue «vivo») | HUB_SHELL-F73 |
| Confirmación de papel real | parcial (red: se confirma cuando la impresora se queda los bytes; sin papel no se detecta) | HUB_SHELL-F74 |
| Reintento de un trabajo que falló | parcial (vuelve a la cola sin despertar a nadie) | HUB_SHELL-F74 |
| Comanda de un pedido sin caja con todas las pantallas cerradas | no hecho (no sale ni avisa) | HUB_SHELL-F72 |
| Reintentar desde el aviso un papel que no salió (Square, Toast, Lightspeed) | hecho (tique, comanda y vale por el directo) | HUB_SHELL-F70, F72, F78 |
| Vale de anulación en la impresora de la comanda al cancelar la ronda o anular un plato | parcial (impresora apagada mudo por la cola) | HUB_SHELL-F78 |
| Cobertura por función visible | parcial (recalcula el estado; puede mentir) | HUB_SHELL-F75 |
| Hora de la venta y nombre de quien atiende en el tique | no hecho | HUB_SHELL-F76 |
| A4 con diálogo del sistema / navegador | hecho | HUB_SHELL-F77 |

## Datos: de quién es cada dato

Ninguno de estos flujos tiene tabla propia: todo lo que pintan se lee del hub o de la app instalada.

| Dato | Dueño | Cómo lo lee el shell |
|---|---|---|
| Cola de impresión, dispositivos que imprimen, cobertura | hub (HUB-F190…F202) | `POST /api/print/jobs`, `/api/print/hosts`, `/api/print/undrained`, `/ws/print` |
| Impresoras y su función | la app instalada del dispositivo (HUB_PERIPHERALS-F04) | `peripherals.getDevices` |

Datos que el shell guarda en el dispositivo: la marca «ya se preguntó por los avisos»
(`erplora.notifications.primerAnswered`), el identificador de la pestaña (`CLIENT_INSTANCE`, solo en
memoria) y, en memoria, los 50 últimos avisos con su pantalla.

**Datos personales que pasan por estos flujos** (ninguno se guarda en el shell): el nombre de la
clienta, el servicio y la profesional en el aviso de cita (lo enseña Android en la bandeja de
notificaciones, también con la pantalla bloqueada); la etiqueta de la comanda (puede ser «Recogida
Ana») y el nombre de quien la disparó en el aviso y en el papel; el nombre y el NIF del cliente en el
papel del tique y en la fila de la cola del hub cuando va por ella.

## Reglas que no se rompen

- **Solo la pantalla que cobró imprime el tique y abre el cajón** (`meta.clientInstance ===
  CLIENT_INSTANCE`, `print-on-sale.ts:91`); solo la que disparó la ronda imprime la comanda; una
  comanda sin caja que la disparó la encolan, con la misma clave, las pantallas abiertas y
  conectadas cuando nace, y queda un solo trabajo (`print-comanda.ts:170-182,243`). Con todas
  cerradas no la encola nadie (hueco, no regla).
- **Una venta o una comanda nunca se caen por la impresión**: la impresión es posterior y sus
  fallos solo avisan.
- **Un papel que la impresora de este dispositivo no cogió no se manda a la cola**: la sacaría este
  mismo dispositivo con la misma impresora; se avisa con «Reintentar» y el aviso no se va solo
  (`print.ts`, `print-on-sale-notice.ts`, hub#2494).
- **La comanda y su vale de anulación nunca se desvían a la impresora de tiques** (`print-comanda.ts:263`, `print-void.ts`).
- **Dentro de la app instalada no hay «impreso por el navegador»**: sin impresora ni cola la
  respuesta es «no salió» (`print.ts:354-362`).
- **Un documento sin contenido estructurado no se encola** (saldría en blanco, `print.ts:320`).
- **Un aviso del sistema solo lleva a pantallas del hub** (`isNoticeTarget`).
- **Con los avisos denegados no se manda ninguno** (`shouldSendNotice`).
- **Un fallo de una fuente de la campana no la pone a cero** (se queda el último número).

## Lo que NO hace, a propósito

- No imprime por el diálogo del navegador lo que nadie pidió (tique y comanda automáticos).
- No avisa en el navegador con notificaciones del sistema (sin push; decisión de 2026-09-30, hub#2307).
- No tiene «marcar como leído» en la campana: se limpia sola al arreglar la causa (ADR-0067).

## Dudas abiertas

- ¿El cajón al cobrar debe abrirse solo con efectivo y haber un «Abrir cajón / Sin venta» con
  permiso y registro? (Square/Toast lo hacen; hoy no.) → `market-decision`.
- ¿«Nueva comanda» debe sonar también en el TPV que la disparó? Hoy sí (test
  `print-comanda.test.ts` «on the device that prints it and on the one that does not»).
- ¿El tique debe llevar la hora de la venta y el nombre de quien atendió? (la impresora ya sabe pintar
  `cashier`; Ventas no lo manda).

## Fuentes contrastadas

- `architecture/hub/print-queue.md` dice que el estado «atascado» llega resuelto y que ninguna
  pantalla lo recalcula; la tarjeta «Estado de impresión» de Ajustes lo recalcula (`classifyRole` en
  `print-coverage.ts`) y su «El dispositivo que imprimía esto no responde» no es el «sin atender» del hub.
- `qa-hub.md` §8 pide «impresora caída → el trabajo espera en cola y se avisa»: por el directo se avisa
  con «Reintentar» pero no espera en la cola (a propósito: la sacaría la misma impresora); por la cola
  vuelve sin aviso (HUB_SHELL-F74) — `qa-hub §8 (discrepa)` en HUB_SHELL-F70.
- `hand-book/hub/10-asistente-y-notificaciones.md` dice que al pulsar un aviso de la campana se va
  «a Sistema o a la app correspondiente»; la impresión parada lleva a Ajustes › Impresión. Tampoco
  cuenta los contadores de las apps ni las actualizaciones.
- `main.ts` (comentario de `bootPrintHost`) dice que «sigue faltando la pantalla de cobertura»: ya
  existe (Ajustes › Impresión, hub#800).
