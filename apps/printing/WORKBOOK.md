# Workbook — Impresión (app)
Prefijo: PRINTING
Alcance MVP: núcleo
Estado de la app: servidor y páginas hechos; el papel sale cuando `base` sirva `/ws/print` (fase 2,
bloque 6) y cuando cada app productora llame a `printing.job.create` (lo dice cada flujo)

> Manual de usuario y especificación de la app `printing`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Impresión del producto actual
> (`modules-workspace/modules/printing`, `origin/main` `89fa116`, v0.1.30) y de la cola de impresión
> del Hub viejo (`hub` `origin/develop` `9dd38215`). Los números de flujo se conservan porque otras
> apps los citan (INVENTORY-F25 → PRINTING-F04 y F12).

## Para qué sirve y para quién

Impresión es donde el negocio **da de alta sus impresoras, dice qué sale por cada una y ve si el
papel está saliendo**. Cada impresora tiene un nombre («Caja», «Cocina»), su conexión (red, USB,
Bluetooth o la impresora del sistema), su ancho de papel (58 u 80 mm) y su **función**: tiques,
cocina, barra o etiquetas. Las demás apps (Ventas al cobrar, Caja al cerrar el turno, Inventario para
las etiquetas) **piden** sus impresiones a Impresión, que las pone en la **cola de impresión** del
negocio; el dispositivo con la app de ERPlora instalada junto a la impresora las saca en papel y
confirma. Si algo no sale, la cola lo dice y deja reintentarlo o cancelarlo.

Quién la usa:

- El **propietario** y el **administrador**: todo; además reintentan y cancelan trabajos atascados.
- El **responsable**: da de alta y cambia impresoras y ajustes, y pide impresiones.
- El **empleado**: ve impresoras, ajustes y cola, y pide impresiones (una prueba, un tique).

Sirve igual a la peluquería y al restaurante: los dos imprimen el tique y las etiquetas; la comanda de
cocina y barra es solo del restaurante.

Impresión **no compone** lo que se imprime (el tique es de Ventas, la factura de Facturación, el
informe del turno de Caja, la etiqueta de Inventario) y **no habla con la impresora**: lo hace la app
del dispositivo. Un navegador no llega a las impresoras.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó.

- [Square — impresoras de recibos, pedidos y etiquetas](https://squareup.com/help/us/en/article/5530-set-up-a-printer):
  cada impresora se da de alta en el punto de venta con su nombre, su conexión y lo que imprime
  (recibos, tiques de cocina, etiquetas); una prueba de impresión por impresora.
- [Toast — impresión y estaciones de cocina](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html):
  cada documento sale por la impresora de su estación; la comanda no se desvía a la de tiques.
- [Toast — modo sin conexión](https://doc.toasttab.com/doc/platformguide/platformOfflineMode.html) y
  [Square — modo sin conexión](https://squareup.com/help/es/es/article/7777-process-card-payments-with-offline-mode):
  un trabajo que no puede salir **espera** y se avisa; recuperarlo no lo duplica.
- Epson TM y Star (manuales de las térmicas de 58 y 80 mm): el ancho del papel es de cada
  impresora, no del negocio.
- Lightspeed y Odoo TPV: la cola de impresión con reintento y el «abrir cajón al cobrar» por la
  impresora de tiques.
- [AEAT — SIF y VERI*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html):
  el tique lleva el QR de cotejo y la reimpresión es copia («DUPLICADO»); la cuenta de la mesa no
  lleva número, QR ni pago, y avisa de que no es factura. Lo pone quien compone el documento.

## Antes de empezar

- **Encender Impresión** en el negocio. No necesita ninguna otra app.
- **La app de ERPlora instalada** en el dispositivo que está junto a la impresora (en su red, con su
  cable USB o emparejado por Bluetooth). Ese dispositivo saca el papel de la cola; desde un navegador
  no se llega a las impresoras.
- Una **impresora térmica** (ESC/POS) para tiques, comandas y etiquetas, encendida; para A4 (una
  factura completa), la impresora del sistema del ordenador.

Configuración inicial, paso a paso:

1. Abre **Impresión → Impresoras** y pulsa «Añadir impresora». Escribe su nombre, elige la conexión,
   escribe su dirección (la IP de su hoja de configuración, la MAC de Bluetooth o el nombre de la cola
   USB), el ancho de papel y su función (PRINTING-F03, PRINTING-F04).
2. Pulsa «Probar» en su fila y comprueba que sale la hoja de prueba (PRINTING-F05).
3. En **Impresión → Ajustes** decide si el tique sale solo al cobrar, si se abre el cajón con él,
   cuántas copias y, si tienes varias impresoras con la misma función, cuál es la de cada una
   (PRINTING-F06).
4. La cabecera y el pie del tique se escriben en los ajustes de Ventas, no aquí.
5. Cobra una venta de prueba y comprueba en **Impresión → Cola** que el trabajo sale y queda «Impreso»
   (PRINTING-F07, PRINTING-F01).

## Pantallas

Tres pestañas abajo, las mismas que el menú: **Impresoras**, **Cola** y **Ajustes**.

### Impresoras
Menú **Impresión → Impresoras**. Título «Impresión» y la frase «Da de alta las impresoras del negocio,
di qué sale por cada una y comprueba que el papel sale.». Dos zonas, en este orden:

- **Estado de la impresión**: una tarjeta por cada función que tenga alguna impresora o trabajos
  esperando (un negocio nuevo no ve ninguna), con su nombre («Recibo», «Cocina», «Barra»,
  «Etiqueta»), su estado («Listo», «En cola, sin impresora», «Con errores»), «En cola: N · el más
  antiguo lleva 3 min» o «Nada en cola», los fallidos («Fallidos: N») y por qué impresora sale ahora:
  «Imprime en: Caja.» (la elegida en los ajustes o, si no, la primera activa con esa función). Una
  función con trabajos esperando más de un minuto y sin ninguna impresora activa saca el aviso naranja
  «3 trabajos de impresión de Cocina llevan 3 min esperando. Ninguna impresora activa tiene esta
  función: añade una abajo o dale esta función a una de ellas.» («1 trabajo … lleva …» si es uno). Con
  todo vacío: «Todo al día: no hay nada en cola.». Error de lectura: «No se pudo leer la cola de
  impresión.» con «Reintentar».
- **Impresoras**: la tabla (o tarjetas en el móvil) con Nombre, Función, Conexión, Dirección, Papel,
  Estado y Activa. El estado es «Lista», «Esperando» (tiene trabajos que no salen desde hace más de un
  minuto), «Con errores» (el último intento falló: debajo, «Último error: …») o «Inactiva». Por fila:
  «Editar», «Probar» y «Desactivar»/«Activar». Arriba, «Buscar impresoras» (PRINTING-F02) y «Añadir
  impresora». Vacía: «Todavía no hay
  impresoras. Añade la de tu caja con su dirección.». Una nota recuerda que el papel lo saca la app de
  ERPlora del dispositivo que está junto a la impresora; en un navegador añade «un navegador no llega a
  las impresoras», y dentro de la app no habla de navegadores.

La ventana **Nueva impresora / Editar impresora** tiene «Nombre», «Conexión» («Red», «USB», «Bluetooth»,
«Impresora del sistema (A4)»), «Dirección IP o nombre» y «Puerto» (red; 9100 de fábrica), «MAC de
Bluetooth» (Bluetooth), «Nombre de la cola USB» (USB), «Ancho de papel» (80 mm o 58 mm; no en la del
sistema; debajo, «Se guarda con la impresora: la app de ERPlora imprime por ahora 32 caracteres por línea,
sea cual sea el papel.»), «Función» y «Activa», con «Guardar» y «Cancelar».

La ventana **Buscar impresoras** lista lo que encuentra la app del dispositivo (nombre, conexión y
dirección), cada una con «Añadir» o «Ya añadida», con «Buscar otra vez», «Añadir por su dirección» y
«Cerrar»; mientras busca, «Buscando impresoras…».

Quien no puede cambiar impresoras no ve «Buscar impresoras», «Añadir impresora», «Editar» ni
«Desactivar»; quien no puede imprimir no ve «Probar».

### Cola
Menú **Impresión → Cola**. Título «Cola de impresión». La tabla de trabajos, del más reciente al más
antiguo, 50 por página: Documento («Tique T-000123», o «Tique · 14/10/26 23:05» si no trae número),
Función, Impresora, Estado («Pendiente», «Enviado», «Impreso», «Fallido», «Cancelado»), Intentos, Pedido el
y Detalle («Último error: …», «Cancelado por Ana · motivo», «Reenviado por Ana»). Filtros por estado,
función e impresora, y buscador por número de documento. Quien puede gestionar la cola ve en cada fila
«Reintentar» (un trabajo fallido, o enviado y sin respuesta pasado su plazo) y «Cancelar» (en cola,
fallido o sin respuesta); «Cancelar» abre una ventana con «Motivo (opcional)», «Sí, cancelar» y
«Volver». Vacía: «No hay trabajos de impresión.». Error al cargar: el mensaje con «Reintentar».

### Ajustes
Menú **Impresión → Ajustes**. Una tarjeta «Ajustes del ticket» con «Imprimir ticket al cobrar», «Abrir cajón al
cobrar» y «Copias del ticket» (1, 2 o 3); otra «Impresora de cada función» con un desplegable por
función («Recibo», «Cocina», «Barra», «Etiqueta»): «La primera activa con esa función» o una de sus
impresoras activas. La nota «El encabezado y el pie del tique forman parte de los ajustes de Ventas,
que es de donde sale el tique.» con el enlace «Abrir los ajustes del tique» (si Ventas está encendida). «Guardar ajustes» guarda lo que
cambió y dice «Ajustes guardados.». Quien no puede cambiarlos los ve bloqueados con «No tienes permiso
para cambiar estos ajustes.». Cargando: «Cargando ajustes…». Error: «No se pudieron cargar los
ajustes.» con «Reintentar»; al guardar, «No se pudieron guardar los ajustes.» con el motivo.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (en Ajustes, «Cargando ajustes…») mientras llega el primer resultado. |
| Vacío | Impresoras: «Todavía no hay impresoras. Añade la de tu caja con su dirección.»; Cola: «No hay trabajos de impresión.»; el estado de la impresión, «Todo al día: no hay nada en cola.». |
| Error | El aviso de su pantalla con «Reintentar»; un rechazo de una acción sale en su ventana, junto a su campo, o en un aviso. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva | «Impresión no está activa en este negocio.» |
| Sin permiso | No aparece lo que no puede hacer; los ajustes salen bloqueados con «No tienes permiso para cambiar estos ajustes.». |

## Flujos

| ID | Flujo | Vertical | Estado |
|---|---|---|---|
| PRINTING-F01 | Ver cómo va la impresión | común | hecho |
| PRINTING-F02 | Encontrar una impresora de la red sin escribir su dirección | común | parcial: la app solo busca para el negocio al que está vinculada |
| PRINTING-F03 | Añadir una impresora por su dirección | común | hecho |
| PRINTING-F04 | Asignar qué sale por cada impresora | común | hecho |
| PRINTING-F05 | Hacer una prueba de impresión | común | parcial: el papel sale con `/ws/print` |
| PRINTING-F06 | Elegir cómo imprime el negocio | común | hecho |
| PRINTING-F07 | Imprimir el tique al cobrar | común | parcial: falta que Ventas lo pida |
| PRINTING-F08 | Reimprimir un tique o una factura | común | parcial: falta que Ventas y Facturación lo pidan |
| PRINTING-F09 | Imprimir la cuenta de la mesa | restaurante | parcial: falta que Ventas lo pida |
| PRINTING-F10 | Imprimir la comanda en cocina y barra | restaurante | hecho |
| PRINTING-F11 | Reimprimir una comanda | restaurante | hecho |
| PRINTING-F12 | Imprimir la etiqueta de un código de barras | común | parcial: falta que Inventario lo pida |
| PRINTING-F13 | Abrir el cajón al cobrar | común | parcial: falta que Ventas lo pida |
| PRINTING-F14 | Sacar del atasco un trabajo de impresión | común | hecho |
| PRINTING-F15 | Llevar el texto antiguo del tique a Ventas | común | retirado |
| PRINTING-F16 | Mandar imprimir desde el asistente | común | hecho |
| PRINTING-F17 | Imprimir el cierre de caja | común | parcial: falta que Caja lo pida |
| PRINTING-F18 | Sacar el papel: el dispositivo recoge y confirma los trabajos | común | parcial: la recogida está hecha; el canal `/ws/print` es de `base` |
| PRINTING-F19 | Ver el estado de una impresora | común | hecho |
| PRINTING-F20 | Cuánto tiempo guarda el hub los trabajos de impresión | común | hecho |

### PRINTING-F01 Ver cómo va la impresión
<!-- origen: wf:restaurante-dia#rec_restaurante-f16 old-hub:HUB_SHELL-F60 old-hub:HUB_SHELL-F63 old-hub:HUB_SHELL-F75 old-hub:HUB-F201 old-hub:HUB-F202 old-hub:HUB-F203 old:printing/workflow/impresoras.md#printing-f01 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Impresoras, Cola
Pasos:
1. Abre **Impresión → Impresoras**: las tarjetas de función dicen si cada una tiene impresora y cuál
   la imprime, cuánto espera y desde cuándo.
2. Abre **Impresión → Cola** para ver cada trabajo con su estado, sus intentos y su último error.
3. Si una función sale «En cola, sin impresora» o hay un aviso naranja, el papel no está saliendo:
   sigue por PRINTING-F04 (dar la función a una impresora) o PRINTING-F14 (sacar el trabajo del
   atasco).
Entra: la cola y las impresoras del negocio.
Sale: nada guardado. Lo que depende del reloj (cuánto lleva esperando, el aviso naranja, «Esperando»
y un enviado que no contestó a tiempo) se recalcula solo cada 30 s, sin esperar a otro cambio; «Todo al
día» exige que no haya nada en cola, enviado sin confirmar ni fallido. Las pantallas se refrescan solas al encolarse, enviarse, imprimirse, fallar,
reintentarse o cancelarse un trabajo.
Si falla: «No se pudo leer la cola de impresión.» con «Reintentar»; no se pinta «Todo al día» cuando
la lectura falla.
Implicados: PRINTING-F14, PRINTING-F18, CASH_REGISTER-F08

### PRINTING-F02 Encontrar una impresora de la red sin escribir su dirección
<!-- origen: old-hub:HUB_APP-F07 old-hub:HUB_APP-F08 old-hub:HUB_APP-F09 old-hub:HUB_APP-F15 old-hub:HUB_APP-F16 old-hub:HUB_SHELL-F138 old-hub:HUB_SHELL-F140 old-hub:HUB_APP-F13 old-hub:HUB_PERIPHERALS-F01 old-hub:HUB_PERIPHERALS-F03 old:printing/workflow/impresoras.md#printing-f02 qa:modules/printing/discover-printers qa:verticals/restaurant/10-hardware-offline-and-recovery -->
Estado: parcial — la búsqueda está en Impresoras y la hace la app de ERPlora del dispositivo, pero la app
solo busca para el negocio al que está vinculada, y ese vínculo llega cuando la entrada de las apps en
erplora.com lo dé; mientras tanto la ventana lo dice y la impresora se añade por su dirección (PRINTING-F03)
Vertical: común
Actor: administrador, responsable
Pantalla: Impresoras
Pasos:
1. En **Impresión → Impresoras**, pulsa «Buscar impresoras».
2. La app del dispositivo busca en la red (en el móvil, también las Bluetooth emparejadas; en el
   ordenador, sus colas USB) y lista lo que encuentra: nombre, conexión y dirección. Las que el negocio
   ya tiene dicen «Ya añadida»; las impresoras de oficina (A4) no se ofrecen.
3. Pulsa «Añadir» en la que quieras: se abre «Nueva impresora» con su nombre, conexión, dirección y
   papel ya puestos; elige su «Función» y pulsa «Guardar» (PRINTING-F03).
4. Si no aparece, «Buscar otra vez» o «Añadir por su dirección».
Entra: lo que encuentra la app del dispositivo.
Sale: la impresora dada de alta en el negocio, como en PRINTING-F03.
Si falla: desde un navegador, «Desde el navegador no se puede buscar impresoras: añádela por su
dirección.»; sin permiso para la red local, «La app no tiene permiso para buscar en la red local: dáselo
en los ajustes del dispositivo y vuelve a buscar.» (nunca una lista vacía); con la app sin vincular, «Esta
app no está vinculada a este negocio: ábrelo desde la app para buscar sus impresoras.»; si la búsqueda
falla, «No se pudo buscar impresoras.»; sin resultados, «No se ha encontrado ninguna impresora. Comprueba
que está encendida y en la misma red, o añádela por su dirección.».
Implicados: PRINTING-F03

### PRINTING-F03 Añadir una impresora por su dirección
<!-- origen: old-hub:HUB_APP-F14 old-hub:HUB_SHELL-F165 old-hub:HUB_PERIPHERALS-F02 old:printing/workflow/impresoras.md#printing-f03 qa:modules/printing/register-printer-by-ip qa:modules/printing/usb-printer-raw-queue -->
Estado: hecho
Vertical: común
Actor: administrador, responsable
Pantalla: Impresoras
Pasos:
1. Pulsa «Añadir impresora».
2. Escribe el «Nombre» («Caja», «Cocina»), elige la «Conexión» y escribe su dirección: la IP (o el
   nombre en la red) y el puerto para una de red (la IP sale en la hoja de configuración que imprime
   la impresora al encenderla con el botón de avance pulsado); la MAC para una Bluetooth emparejada; el
   nombre de la cola del sistema para una USB. La «Impresora del sistema (A4)» no lleva dirección: es
   la del ordenador.
3. Elige el «Ancho de papel» y la «Función», y pulsa «Guardar».
4. Sale «Impresora añadida.» y aparece en la tabla.
Entra: el nombre, la conexión, la dirección, el papel y la función.
Sale: la impresora del negocio (avisa: `printing.printer.created`).
Si falla: el campo marcado con el motivo: «Ya hay una impresora con ese nombre.», «Escribe una IP o un
nombre de red válidos (por ejemplo 192.168.1.100).», «El puerto va de 1 a 65535.», «Escribe la MAC
como AA:BB:CC:DD:EE:FF.», «Escribe el nombre de la cola de impresión tal como lo da el sistema (sin
espacios, barras ni #).», «La impresora del sistema imprime páginas A4: dale la función Recibo.». Sin
nombre, «Ponle un nombre a la impresora.».
Implicados: PRINTING-F04, PRINTING-F05

### PRINTING-F04 Asignar qué sale por cada impresora
<!-- origen: old-hub:HUB_APP-F17 old-hub:HUB_SHELL-F75 wf:restaurante-dia#rec_restaurante-f02 qa:verticals/restaurant/10-hardware-offline-and-recovery qa:modules/printing/register-printer-by-ip old-hub:HUB-F193 old-hub:HUB-F194 old-hub:HUB-F195 old-hub:HUB_PERIPHERALS-F04 old:printing/workflow/impresoras.md#printing-f04 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable
Pantalla: Impresoras, Ajustes
Pasos:
1. Al dar de alta o editar una impresora, elige su «Función»: «Recibo» (tique, factura, cuenta de la
   mesa, informe de caja, albarán), «Cocina» (comandas), «Barra» (comandas de barra) o «Etiqueta»
   (etiquetas de código de barras).
2. Si hay varias impresoras con la misma función, en **Ajustes → Impresora de cada función** elige la
   que la saca; si no eliges, sale por la primera activa con esa función (por nombre).
3. «Desactivar» deja una impresora fuera sin borrarla: no recibe trabajos nuevos y sus trabajos en
   cola esperan (reintentarlos los manda a la impresora que toque entonces).
Entra: la función de cada impresora y, si hay varias, la elegida.
Sale: cada documento sale por la impresora de su función. Una impresora no se borra: la cola la nombra.
Si falla: si ninguna impresora activa tiene la función, el trabajo **espera** en la cola sin
impresora («En cola, sin impresora») y sale en cuanto una la tenga. En ajustes, una impresora de otra
función o inactiva se rechaza: «Esa impresora no tiene esta función.», «Esa impresora está inactiva.».
Implicados: PRINTING-F01, PRINTING-F06, INVENTORY-F25

### PRINTING-F05 Hacer una prueba de impresión
<!-- origen: old-hub:HUB_APP-F20 old-hub:HUB_PERIPHERALS-F14 old:printing/workflow/impresoras.md#printing-f05 -->
Estado: parcial — la prueba se encola y la recoge el dispositivo (PRINTING-F18); el papel sale cuando
`base` sirva `/ws/print` (bloque 6)
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Impresoras
Pasos:
1. Pulsa «Probar» en la fila de la impresora.
2. Sale «Prueba enviada a la cola de Caja.» y en la cola aparece «Hoja de prueba».
3. El dispositivo junto a la impresora la saca: el nombre del negocio (el que tiene Facturación; sin
   Facturación o sin permiso para leerlo, «ERPlora»), «Impresora OK», la fecha y la dirección de la
   impresora. Una impresora del sistema saca la hoja en A4 con lo mismo.
Entra: la impresora.
Sale: un trabajo «Hoja de prueba» para esa impresora (avisa: `printing.job.queued`).
Si falla: una impresora inactiva no se prueba: «Esa impresora está inactiva: actívala para probarla.».
Si el papel no sale, el trabajo queda «Fallido» con el error del dispositivo (PRINTING-F14).
Implicados: PRINTING-F18

### PRINTING-F06 Elegir cómo imprime el negocio
<!-- origen: old-hub:HUB_SHELL-F165 fi:modules/printing#command-printing-settings-update fi:modules/printing#query-printing-settings-get old-hub:HUB_PERIPHERALS-F16 old:printing/workflow/impresoras.md#printing-f06 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable
Pantalla: Ajustes
Pasos:
1. Abre **Impresión → Ajustes**.
2. Enciende o apaga «Imprimir ticket al cobrar» y «Abrir cajón al cobrar», elige las «Copias del
   tique» y, si quieres, la impresora de cada función.
3. Pulsa «Guardar ajustes». Se guarda lo que cambiaste; lo demás queda como estaba.
Entra: las decisiones del negocio.
Sale: los ajustes de impresión, una sola fila (avisa: `printing.settings.updated`). Sin guardar
nunca valen los de fábrica: tique al cobrar encendido, cajón apagado, una copia, sin impresora elegida.
Si falla: «No se pudieron guardar los ajustes.» con el motivo. Si la lectura falla, la pantalla no
enseña valores y ofrece «Reintentar». Sin permiso, bloqueados y sin «Guardar ajustes».
Implicados: PRINTING-F07, PRINTING-F13

### PRINTING-F07 Imprimir el tique al cobrar
<!-- origen: old-hub:HUB_PERIPHERALS-F09 wf:restaurante-dia#rec_restaurante-f12 fi:hub/app-web#print-on-sale-auto-impresion-del-ticket-al-cerrar-venta old-hub:HUB_APP-F19 old-hub:HUB_SHELL-F70 qa:verticals/beauty/06-fiscal-and-printing qa:verticals/restaurant/11-races-and-concurrency old-hub:HUB-F190 old-hub:HUB-F192 old:printing/workflow/documentos.md#printing-f07 qa:modules/printing/print-receipt qa:verticals/restaurant/07-payment-and-fiscal -->
Estado: parcial — Impresión lo hace en cuanto se le pide (`printing.job.create` con `automatic`);
falta que Ventas lo pida al cobrar (pedido al worker de `sale`) y el papel, con `/ws/print`
Vertical: común
Actor: empleado
Pantalla: Vender (de Ventas)
Pasos:
1. El empleado cobra en **Ventas → Vender**.
2. En la misma transacción del cobro, Ventas pide a Impresión el tique (`automatic: true`).
3. Si «Imprimir ticket al cobrar» está encendido, el tique entra en la cola de la función Recibo
   con las copias de los ajustes y, si «Abrir cajón al cobrar» está encendido, con la orden de abrir
   el cajón; el dispositivo lo saca.
Entra: el tique compuesto por Ventas (`receipt`).
Sale: un trabajo en la cola, o nada si el negocio no imprime al cobrar.
Si falla: una venta **nunca se cae** por la impresión: si Impresión no está encendida o la petición
falla, Ventas cobra igual y lo dice. Un trabajo que no sale queda en la cola (PRINTING-F14).
Implicados: SALE-F08, PRINTING-F13, PRINTING-F18

### PRINTING-F08 Reimprimir un tique o una factura
<!-- origen: old-hub:HUB_PERIPHERALS-F09 old-hub:HUB_APP-F22 old-hub:HUB_SHELL-F77 qa:modules/printing/print-receipt qa:verticals/restaurant/07-payment-and-fiscal old:printing/workflow/documentos.md#printing-f08 -->
Estado: parcial — Impresión acepta el tique (`receipt` con `duplicate`) y la factura (`invoice`, o la
página A4 de Facturación para la impresora del sistema); falta que Ventas y Facturación lo pidan
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Ventas, Facturas (de esas apps)
Pasos:
1. En la ficha de la venta o de la factura, pulsa «Imprimir».
2. La app pide a Impresión el documento marcado como copia («DUPLICADO»).
Entra: el documento con `duplicate: true`.
Sale: un trabajo en la cola de Recibo; una factura A4 va a la impresora del sistema.
Si falla: como F07.
Implicados: SALE-F31

### PRINTING-F09 Imprimir la cuenta de la mesa
<!-- origen: old-hub:HUB_PERIPHERALS-F11 qa:verticals/restaurant/07-payment-and-fiscal old:printing/workflow/documentos.md#printing-f09 qa:modules/sales/guest-check wf:restaurante-dia#rec_restaurante-f09 -->
Estado: parcial — Impresión acepta la cuenta (`prebill`) y rechaza una sin líneas; falta que Ventas la
pida
Vertical: restaurante
Actor: empleado
Pantalla: Vender (de Ventas)
Pasos:
1. Con la cuenta abierta, pulsa «Imprimir cuenta».
2. Ventas pide la cuenta (sin número, sin QR, sin pago y con el aviso de que no es factura).
Entra: la cuenta (`prebill`) con sus líneas.
Sale: un trabajo en la cola de Recibo. Cada pulsación saca una cuenta.
Si falla: «Una cuenta lleva líneas que cobrar: esta no tiene ninguna.» (422).
Implicados: SALE-F15

### PRINTING-F10 Imprimir la comanda en cocina y barra
<!-- origen: old-hub:HUB_PERIPHERALS-F10 wf:restaurante-dia#rec_restaurante-f07 old-hub:HUB_SHELL-F72 qa:verticals/restaurant/06-service-orders-and-kitchen old:printing/workflow/cocina-y-cola.md#printing-f10 -->
Estado: hecho
Vertical: restaurante
Actor: empleado
Pantalla: Vender (de Ventas)
Pasos:
1. En **Ventas → Vender**, con la cuenta abierta, el camarero pulsa «Enviar comanda» (o «Enviar
   URGENTE»).
2. Cocina abre la comanda y pide a Impresión una hoja por impresora: los platos de cada estación, por su
   función («Cocina» o «Barra») o por la impresora concreta de la estación (KITCHEN-F08).
3. Cada hoja entra en la cola de la impresora de su función con la mesa, el número, la ronda, el
   camarero y sus platos; el dispositivo la saca (PRINTING-F18).
Entra: la comanda de Cocina (mesa, camarero, ronda y platos).
Sale: un trabajo por impresora en la cola de Impresión.
Si falla: la comanda no se desvía a la impresora de tiques: sin impresora con su función, espera en la
cola («En cola, sin impresora») y sale en cuanto una la tenga. El papel nunca bloquea al camarero.
Implicados: KITCHEN-F08, KITCHEN-F18, PRINTING-F04, PRINTING-F18

### PRINTING-F11 Reimprimir una comanda
<!-- origen: old:printing/workflow/cocina-y-cola.md#printing-f11 -->
Estado: hecho
Vertical: restaurante
Actor: empleado, responsable
Pantalla: Comandas (de Cocina)
Pasos:
1. En **Cocina → Comandas**, en la fila de la comanda, «⋮ → Reimprimir».
2. Cocina pide a Impresión otra hoja por cada impresora de sus platos, marcada como copia (KITCHEN-F09).
Entra: la comanda.
Sale: un trabajo nuevo con otra clave cada vez, en la cola de la impresora de su función.
Si falla: como PRINTING-F10; si Impresión la rechaza, Cocina dice su motivo.
Implicados: KITCHEN-F09, PRINTING-F10

### PRINTING-F12 Imprimir la etiqueta de un código de barras
<!-- origen: old-hub:HUB_PERIPHERALS-F12 old:printing/workflow/documentos.md#printing-f12 -->
Estado: parcial — Impresión acepta la etiqueta (`barcode_label`, función Etiqueta: nombre, código y
precio; el código lo dibuja la impresora); falta que Inventario la pida (INVENTORY-F25)
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Ficha del producto (de Inventario)
Pasos:
1. En la ficha del producto, «Imprimir código de barras».
2. Inventario pide la etiqueta a Impresión.
Entra: `product_name`, `barcode` (el SKU) y `price`.
Sale: un trabajo en la cola de Etiqueta. Cada pulsación saca una etiqueta.
Si falla: sin impresora con la función Etiqueta, la etiqueta **espera** en la cola y la tarjeta de
Etiqueta lo dice («En cola, sin impresora»).
Implicados: INVENTORY-F25, PRINTING-F04

### PRINTING-F13 Abrir el cajón al cobrar
<!-- origen: old-hub:HUB_APP-F21 old-hub:HUB_SHELL-F71 wf:restaurante-dia#rec_restaurante-f17 qa:verticals/beauty/06-fiscal-and-printing qa:verticals/restaurant/10-hardware-offline-and-recovery qa:verticals/restaurant/07-payment-and-fiscal old-hub:HUB-F207 old-hub:HUB_PERIPHERALS-F15 old:printing/workflow/documentos.md#printing-f13 qa:modules/printing/open-cash-drawer -->
Estado: parcial — el trabajo del tique lleva la orden de abrir el cajón (o, con el tique apagado, un
trabajo solo de cajón); falta que Ventas lo pida (F07)
Vertical: común
Actor: empleado
Pantalla: Vender (de Ventas)
Pasos:
1. Con «Abrir cajón al cobrar» encendido en **Impresión → Ajustes**, cobra en **Ventas → Vender**, con
   cualquier forma de pago.
2. El cobro (F07) pide el tique con la orden de abrir el cajón conectado a la impresora de tiques; con
   el tique apagado, un trabajo solo de cajón.
Entra: el ajuste.
Sale: la orden de abrir el cajón, en el mismo trabajo que el tique.
Si falla: si el tique no sale, el cajón tampoco; el trabajo queda en la cola (PRINTING-F14).
Implicados: PRINTING-F06, PRINTING-F07

### PRINTING-F14 Sacar del atasco un trabajo de impresión
<!-- origen: qa:verticals/restaurant/10-hardware-offline-and-recovery old-hub:HUB-F204 old-hub:HUB-F205 old:printing/workflow/cocina-y-cola.md#printing-f14 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador
Pantalla: Cola
Pasos:
1. En **Impresión → Cola**, busca el trabajo «Fallido» (o «Enviado» que no contestó).
2. «Reintentar» lo devuelve a la cola con los intentos a cero, hacia la impresora que toque ahora:
   «Devuelto a la cola: el próximo dispositivo que se conecte lo imprimirá.».
3. «Cancelar» pide un motivo (opcional) y lo retira: «Trabajo cancelado. No se imprimirá.». Queda en
   la cola con quién, cuándo y por qué.
Entra: el trabajo y, al cancelar, el motivo.
Sale: el trabajo en cola otra vez o cancelado (avisa: `printing.job.retried`, `printing.job.cancelled`).
Nadie lo borra: la cola lo olvida 30 días después de acabar (PRINTING-F20).
Si falla: «Solo se reintenta un trabajo fallido o que no contestó; este está …», «Un trabajo que está
imprimiendo o ya impreso no se cancela; este está …». Sin permiso no se ven los botones.
Implicados: PRINTING-F01

### PRINTING-F15 Llevar el texto antiguo del tique a Ventas
<!-- origen: old-hub:HUB_SHELL-F76 old:printing/workflow/impresoras.md#printing-f15 -->
Estado: retirado — la plataforma nueva no tiene cabecera ni pie de tique en Impresión que llevar: el
texto del tique vive en los ajustes de Ventas desde el principio
Vertical: común
Actor: administrador
Pantalla: Ajustes
Pasos:
1. Abre **Impresión → Ajustes**.
2. La nota del encabezado y el pie lleva, con «Abrir los ajustes del tique», a los ajustes de Ventas,
   donde se escribe el texto del tique.
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: SALE-F02

### PRINTING-F16 Mandar imprimir desde el asistente
<!-- origen: old-hub:HUB-F191 old:printing/workflow/cocina-y-cola.md#printing-f16 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Asistente
Pasos:
1. Pide al asistente «Imprime una prueba en la de cocina», «reintenta los trabajos fallidos de
   etiquetas» o «¿cómo está la impresora de la caja?».
2. El asistente hace lo mismo que las pantallas, nombrando la impresora por su nombre y el trabajo por
   su número, y contesta con lo que ha hecho.
Entra: la petición.
Sale: lo mismo que la pantalla.
Si falla: lo mismo que la pantalla, con las palabras del servidor.
Implicados: PRINTING-F05, PRINTING-F14, PRINTING-F19

### PRINTING-F17 Imprimir el cierre de caja
<!-- origen: old-hub:HUB_PERIPHERALS-F13 old:printing/workflow/documentos.md#printing-f17 -->
Estado: parcial — Impresión acepta el informe (`cash_session_report`); falta que Caja lo pida al
imprimir el informe X o Z (hoy sale por el diálogo del navegador)
Vertical: común
Actor: empleado
Pantalla: Detalle de la sesión (de Caja)
Pasos:
1. En el detalle de la sesión, «Imprimir».
2. Caja pide el informe a la función Recibo.
Entra: el informe (sesión, cajero, fondo, cierre y movimientos).
Sale: un trabajo en la cola de Recibo.
Si falla: como F07.
Implicados: CASH_REGISTER-F16

### PRINTING-F18 Sacar el papel: el dispositivo recoge y confirma los trabajos
<!-- origen: fi:hub/tauri-packages#camino-de-hardware-handlers-invoke-de-perifericos-erplora-peripherals old-hub:HUB_APP-F19 old-hub:HUB_APP-F18 old-hub:HUB_SHELL-F73 old-hub:HUB_SHELL-F74 qa:verticals/restaurant/10-hardware-offline-and-recovery fi:modules/printing#integracion-bridge-hardware-client-side-no-es-command-query-del-manifest old-hub:HUB-F196 old-hub:HUB-F197 old-hub:HUB-F198 old-hub:HUB-F199 old-hub:HUB-F200 old-hub:HUB_PERIPHERALS-F06 old-hub:HUB_PERIPHERALS-F07 old-hub:HUB_PERIPHERALS-F08 -->
Estado: parcial — recoger, confirmar y avisar del fallo están hechos en Impresión; falta el canal por el
que el dispositivo los pide (de la plataforma: hoy el servidor no lo sirve), quien recoge en la app del
dispositivo y el vínculo de esa app con el negocio. Contrato en «Contrato con la plataforma».
Vertical: común
Actor: sistema (la app del dispositivo)
Pantalla: ninguna
Pasos:
1. El dispositivo junto a la impresora pide el siguiente trabajo de las impresoras a las que llega.
2. Impresión le da el más antiguo en cola (de esa impresora, o sin impresora y de su función), lo
   marca «Enviado» con un plazo de 90 s y suma un intento.
3. El dispositivo lo imprime —la primera copia como original y las demás de un tique o una factura
   como «DUPLICADO»— y confirma diciendo quién es y qué entrega contesta: «Impreso». Si no pudo, avisa
   con el error: vuelve a la cola hasta 5 intentos y después queda «Fallido».
4. Si el dispositivo se cae sin contestar, pasado el plazo el trabajo vuelve a la cola y se avisa a los
   dispositivos (`printing.job.queued`).
Entra: las impresoras que alcanza el dispositivo y, al confirmar, el resultado.
Sale: el trabajo con su estado (avisa: `printing.job.claimed`, `printing.job.printed`,
`printing.job.failed`).
Si falla: confirmar dos veces es una confirmación. Una confirmación tardía del mismo dispositivo
(una impresora lenta con copias pasa de los 90 s y el trabajo ya había vuelto a la cola) se acepta: el
papel salió y no se imprime otra vez. Una confirmación o un fallo de otro dispositivo, o de una entrega
que no es la suya, se rechaza (409 `printing.job_not_yours`) y no cambia nada.
Implicados: PRINTING-F05, PRINTING-F07, PRINTING-F14

### PRINTING-F19 Ver el estado de una impresora
<!-- origen: old-hub:HUB_SHELL-F162 old-hub:HUB_SHELL-F37 old-hub:HUB_SHELL-F137 old-hub:HUB_PERIPHERALS-F05 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Impresoras
Pasos:
1. La columna «Estado» de cada impresora dice «Lista», «Esperando», «Con errores» o «Inactiva», con
   su último error.
2. El asistente lo contesta por el nombre de la impresora.
Entra: la impresora.
Sale: su estado, cuántos trabajos esperan y desde cuándo, cuándo imprimió por última vez y su último
error.
Si falla: «No hay ninguna impresora con ese nombre.».
Implicados: PRINTING-F01

### PRINTING-F20 Cuánto tiempo guarda el hub los trabajos de impresión
<!-- origen: old-hub:HUB-F206 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: Cola
Pasos:
1. Un trabajo se queda en la cola mientras espera, mientras el dispositivo lo imprime y después de
   acabar («Impreso», «Cancelado» o «Fallido»), con su número, su función, su impresora y sus sellos; al
   imprimirse o cancelarse ya suelta el documento.
2. Cada hora, la cola olvida los trabajos que acabaron hace más de 30 días; uno en cola o enviado no se
   toca nunca.
3. Desde ese momento ya no sale en **Impresión → Cola** ni cuenta en el estado de la impresión.
Entra: nada: lo hace la plataforma sola.
Sale: los trabajos terminados hace más de 30 días, borrados (avisa: `printing.job.pruned`, con
cuántos). Pedir otra vez el mismo documento después vuelve a ponerlo en cola.
Si falla: si una hora no puede limpiar, lo hace la siguiente; un trabajo nunca se borra antes de su
plazo.
Implicados: PRINTING-F01, PRINTING-F14

## Servicios: lo que entra y lo que sale

Las demás apps y el asistente usan Impresión por estas operaciones, por su nombre; nunca sus tablas.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los ajustes de impresión (los de fábrica si nunca se guardaron) | ver | F06 | `printing.settings.get` |
| Las impresoras, con búsqueda por nombre, filtros (función, conexión, activa) y páginas, cada una con su estado | ver | F03, F04, F19 | `printing.printer.list` |
| Una impresora por id o por nombre | ver | F04 | `printing.printer.get` |
| El estado de una impresora (por id o nombre) | ver | F19 | `printing.printer.status` |
| La cola, del más reciente al más antiguo, con búsqueda por documento, filtros (estado, función, impresora) y páginas | ver | F01, F14 | `printing.job.list` |
| El resumen de la cola por función, con la impresora por la que sale cada una | ver | F01 | `printing.job.summary` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Guarda los ajustes (solo lo que se manda) | ajustes | F06 | `printing.settings.update` |
| Da de alta una impresora | ajustes | F03 | `printing.printer.create` |
| Cambia una impresora, o la desactiva y activa | ajustes | F04 | `printing.printer.update` |
| Encola la hoja de prueba de una impresora | imprimir | F05 | `printing.printer.test` |
| Encola un documento (idempotente por su clave) | imprimir | F07–F13, F16, F17 | `printing.job.create` |
| Da al dispositivo el siguiente trabajo de sus impresoras | imprimir | F18 | `printing.job.claim` |
| Confirma un trabajo impreso | imprimir | F18 | `printing.job.complete` |
| Avisa de que un trabajo no salió | imprimir | F18 | `printing.job.fail` |
| Devuelve a la cola un trabajo fallido o sin respuesta | cola | F14 | `printing.job.retry` |
| Cancela un trabajo | cola | F14 | `printing.job.cancel` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Ajustes guardados | Guardar los ajustes | Qué campos cambiaron | `printing.settings.updated` |
| Impresora nueva | Dar de alta una impresora | Cuál | `printing.printer.created` |
| Impresora cambiada | Editarla, desactivarla o activarla | Cuál y qué campos | `printing.printer.updated` |
| Trabajo en cola | Encolar (también reintentar) | El trabajo, su función y su impresora | `printing.job.queued` |
| Trabajo enviado | Un dispositivo lo recoge | El trabajo y su impresora | `printing.job.claimed` |
| Trabajo impreso | El dispositivo confirma | El trabajo | `printing.job.printed` |
| Trabajo fallido | El dispositivo avisa del error | El trabajo y si ya no se reintenta | `printing.job.failed` |
| Trabajo devuelto a la cola | Reintentar | El trabajo | `printing.job.retried` |
| Trabajo cancelado | Cancelar | El trabajo | `printing.job.cancelled` |
| Trabajos olvidados | La limpieza de cada hora borra lo terminado hace más de 30 días | Cuántos | `printing.job.pruned` |

Los avisos no llevan el documento (puede tener el nombre o el NIF de un cliente): solo ids.

### A qué reacciona

A nada. Las apps que imprimen llaman a `printing.job.create` por su nombre, dentro de su propia
transacción (la de la venta, la del cierre), y no esperan a un aviso.

### Lo que necesita de otras apps

Nada (`requires = []`). No lee modelos de nadie: quien imprime manda el documento ya compuesto.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Ventas | Tique al cobrar, reimpresión, cuenta de la mesa (cuando lo adopte) | `printing.job.create` |
| Facturación | Factura en térmica o A4 (cuando lo adopte) | `printing.job.create` |
| Caja | Informe X y Z (cuando lo adopte) | `printing.job.create` |
| Inventario | Etiqueta de código de barras (cuando lo adopte) | `printing.job.create` |
| Cocina | La comanda de cada estación y su reimpresión | `printing.job.create` |
| `base` (`/ws/print`) | Entregar y confirmar trabajos | `printing.job.claim`, `printing.job.complete`, `printing.job.fail` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver impresoras, ajustes y cola | sí | sí | sí | sí | `printing.view_settings` |
| Impresoras y ajustes | sí | sí | sí | no | `printing.manage_settings` |
| Imprimir (pedir, probar, recoger y confirmar) | sí | sí | sí | sí | `printing.print` |
| Reintentar y cancelar trabajos | sí | sí | no | no | `printing.manage_jobs` |

## Para quien lo mantiene

### Contrato con la plataforma

**Lo que pide cada app (`printing.job.create`).** La entrada es la del cuadro; los importes van en
unidades de la moneda (12.50), con `decimals` si no son 2, y las fechas, ya escritas:

| Campo | Qué es |
|---|---|
| `job_key` | Clave de idempotencia de quien pide (≤ 128): dos peticiones con la misma clave son **un** trabajo; la segunda contesta `duplicate: true` con el que ya estaba. Sin clave, Impresión pone una. |
| `document_type` | Uno de los ocho que la impresora sabe pintar: `receipt`, `kitchen_order`, `invoice`, `delivery_note`, `barcode_label`, `cash_session_report`, `prebill`, `generic`. Otro es 422. |
| `document` | El documento **estructurado** (objeto JSON, ≤ 512 KB): nunca HTML para una térmica. Los campos son los que lee `crates/peripherals/src/escpos.rs` de la app (abajo). |
| `format` | `receipt` (térmica, de fábrica) o `a4` (impresora del sistema). |
| `html` | La página A4 completa (≤ 2 MB, sin scripts) cuando `format` es `a4`; obligatoria entonces y prohibida si no. |
| `usage` | La función: `receipt`, `kitchen`, `bar` o `label`. Sin ella sale del documento: `kitchen_order` → cocina, `barcode_label` → etiquetas, el resto → tiques. |
| `printer` | Una impresora concreta por id o por nombre («Cocina»); sin ella, la de la función (ajustes), o la primera activa con esa función, o ninguna (espera). |
| `copies` | De 1 a 5; sin ella, las copias del tique de los ajustes para `receipt` y 1 para lo demás. |
| `automatic` | `true` = la impresión sola al cobrar: respeta «Imprimir ticket al cobrar» (apagado → nada en cola, `skipped: "print_on_sale_off"`) y añade «Abrir cajón al cobrar» (`open_drawer`; con el tique apagado y el cajón encendido, encola un trabajo solo de cajón). |
| `source_app`, `source_ref` | Quién lo pide y qué documento es («sale», «T-000123»): lo que se ve en la cola. |

Si el documento no trae `locale`, Impresión pone el idioma de quien lo pide; si no trae `decimals`
(salvo en `generic`, que imprime todas sus claves), los de la moneda (`currency`, ISO 4217; sin ella,
EUR). Un valor que no es JSON (un `Decimal`, una fecha) es 422, nunca un error del servidor.

Campos del documento que lee la impresora (los demás se ignoran):

- `receipt` e `invoice`: `business_name`, `business_address`, `vat_number`, `phone`, `receipt_id`,
  `duplicate`, `rectifying`, `cashier`, `customer_name`, `customer_tax_id`, `customer_address`,
  `items` (`name`, `quantity`, `total`, `notes`, `components`, `modifiers`), `subtotal`,
  `tax_amount`, `tax_label`, `tax_breakdown` (`rate`, `base`, `tax`), `discount`, `total`,
  `payment_method`, `paid`, `change`, `qr_data`, `qr_heading`, `qr_legend`, `receipt_header`,
  `receipt_footer`, `claim_*`, `promo_*`, `decimals`, `locale`. Una `invoice` exige `vat_number`,
  `receipt_id`, `customer_name`, `customer_tax_id` y `tax_breakdown` no vacío (422 si falta).
- `prebill`: lo mismo sin número, QR ni pago, con `notice`; exige `items` no vacío.
- `kitchen_order`: `order_number`, `round_number`, `table`, `waiter`, `label`, `priority`, `items`
  (`name`, `quantity`, `notes`, `combo_name`, `combo_ref`).
- `barcode_label`: `product_name`, `barcode`, `price`.
- `cash_session_report`: `receipt_id` (la sesión), `cashier`, `opening_balance`, `closing_balance`,
  `transactions` (`label`, `amount`).
- `delivery_note`: `receipt_id`, `customer_name`, `delivery_address`, `items` (`name`, `quantity`).
- `generic`: `title` y cualquier par clave–valor.

**Lo que hace `base` con `/ws/print` (fase 2, bloque 6).** El protocolo es el del Hub viejo
(`print_ws.rs`): `hello` con la sesión en el primer mensaje y el `deviceId`, `ready`, `claim`, `job`,
`done`/`failed`, `ack`, `beat`, `wake`, `idle`, `error`. Lo de Impresión es el estado de la cola; el
canal llama a sus operaciones con el contexto de la sesión del dispositivo:

1. `claim` → `printing.job.claim` con `printers` (los ids de las impresoras del negocio que ese
   dispositivo alcanza; el dispositivo los conoce por `printing.printer.list`) y `device` (su nombre o
   `deviceId`). Contesta `{"job": null}` (→ `idle`) o el trabajo:
   `{"id", "kind", "printer_id", "target", "paper_width", "document_type", "document", "copy_document", "format", "html", "copies", "open_drawer", "attempts", "leased_until"}`.
2. El dispositivo lo imprime con los comandos nativos de la app, **que no cambian**:
   - `kind = "document"` y `format = "receipt"`: `erplora_print(printerId = target, documentType, data = document, jobId = id)` una vez y, si `copies` > 1, `erplora_print(…, data = copy_document, …)` las `copies − 1` restantes. En un `receipt` o una `invoice`, `copy_document` es el documento con `"duplicate": true`: la app imprime «DUPLICADO» (`escpos.rs`) y nunca sale un segundo original (RD 1619/2012, art. 14.4). Una página A4 se imprime una vez;
   - `kind = "document"` y `format = "a4"`: `print_document(html)`;
   - `kind = "test_page"`: `erplora_test_print(printerId = target, data = document)` (en la impresora del sistema, `print_document(html)`);
   - `kind = "drawer"`, o `open_drawer: true` después de imprimir: `erplora_open_drawer(printerId = target)`.
   `target` es el `printer_id` que entiende la app: `network:<ip>:<puerto>`, `bluetooth:<MAC>`,
   `usb:<cola>` o `system`.
3. `done` → `printing.job.complete` con `device` y `attempt` (`{"confirmed": true}` → `ack`); se acepta
   también si el trabajo ya volvió a la cola, siempre que sea del mismo dispositivo. `failed` →
   `printing.job.fail` con el error, `device` y `attempt`; solo vale para la entrega en curso. Otro
   dispositivo u otra entrega → 409 `printing.job_not_yours`.
4. `wake`: tras el COMMIT de un trabajo nuevo llega el aviso `printing.job.queued` por la BD de control
   (el mismo NOTIFY que `/api/live`); el canal despierta a los dispositivos de esa impresora o función.
   Es un empujón: el documento solo viaja en la respuesta a `claim`.
5. Quién puede ser dispositivo de impresión (el registro de dispositivos y su latido) es de `base`; el
   permiso de las tres operaciones es `printing.print`.

**Lo que se pide a cada app** (no se toca desde aquí):

- **Ventas** (`sale`): al cobrar, llamar a `printing.job.create` con el tique (`receipt`,
  `automatic: true`, `job_key` = `sale-<id>-receipt`, `source_app: "sale"`, `source_ref` = número) en
  la transacción del cobro, sin caerse si Impresión está apagada; en «Imprimir» de la ficha, lo mismo
  con `duplicate: true` y otra clave; en «Imprimir cuenta», `prebill`. Los importes en unidades
  (céntimos / 100).
- **Facturación** (`invoice`): «Imprimir» → `invoice` (térmica) o su página A4
  (`templates/invoice/invoice.html`) con `format: "a4"`.
- **Caja** (`cash_register`): «Imprimir» del detalle → `cash_session_report`.
- **Inventario** (`inventory`, INVENTORY-F25): «Imprimir código de barras» → `barcode_label` con
  `product_name`, `barcode` = SKU y `price`.
- **Cocina** (`kitchen`): ya lo hace — `kitchen_order` por estación, `usage` `kitchen` o `bar` o la impresora
  de la estación, en un savepoint de su transacción (KITCHEN-F08, F09).

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `documents.py` (el
  vocabulario y las comprobaciones del documento), `queries.py`, `services.py`, `events.py`,
  `live.py`, `api.py`, `admin.py`, `templates/printing/`, `locale/`, `frontend/` y un
  `tests/test_<fichero>.py` por fichero, más `tests/test_integration_sale.py` (una venta real de Ventas
  encolada por nombre) y `tests/test_integration_kitchen.py` (la comanda y la reimpresión reales de
  Cocina, por estación).
- **`requires = []`**: Impresión no lee modelos de nadie. Quien imprime compone el documento.
- **Modelos**: `Settings` (una fila; sin ella valen los de fábrica), `Printer` (nunca se borra: la
  cola la nombra; nombre único sin distinguir mayúsculas) y `PrintJob` (la cola: clave única
  `job_key`, tipo, documento, HTML, formato, función, impresora, copias, cajón, estado, intentos,
  plazo, dispositivo, último error y los sellos de quién reintentó o canceló). Nadie borra un trabajo a
  mano: la tarea programada `prune` (`printing.job.prune`, cada hora, como sistema y sin ruta) borra los
  terminados (`done`, `cancelled`, `failed`) 30 días después de acabar, 500 como mucho por pasada.
- **Estados**: `pending` → (`claim`) `sent` → (`complete`) `done`; `sent` → (`fail`) `pending` hasta 5
  intentos, después `failed`; `sent` con el plazo vencido (90 s) vuelve a `pending` (o `failed` si
  agotó los intentos) en el siguiente `claim`; `failed` o `sent` vencido → (`retry`) `pending` con los
  intentos a cero (también un `pending`, que va a la impresora de su función de ahora); `pending`,
  `failed` o `sent` vencido → (`cancel`) `cancelled`. Un `done` tardío del mismo dispositivo se acepta
  desde `pending`. `attempts` cuenta
  entregas, no fallos: un dispositivo que se cae también gasta un intento.
- **Concurrencia**: `claim` bloquea el trabajo con `SELECT … FOR UPDATE SKIP LOCKED`: dos
  dispositivos a la vez nunca reciben el mismo. `complete`, `fail`, `retry` y `cancel` bloquean la
  fila (`select_for_update`). La clave `job_key` es única en la BD: dos peticiones a la vez encolan una.
- **Impresora de un trabajo**: la pedida; si no, la de su función en los ajustes (activa y
  compatible); si no, la primera activa con esa función por nombre; si no, ninguna: espera, y la
  recoge el primer dispositivo con una impresora compatible de esa función. Compatible: la del sistema
  imprime `a4` y las térmicas `receipt`. Reintentar vuelve a elegir si la suya ya no está activa.
- **Hoja de prueba**: `kind = "test_page"` con `{"locale", "business_name"?}` para la térmica (el nombre,
  de `invoice.issuer.get` por su nombre, si Facturación está y lo deja leer); para la del sistema,
  `templates/printing/test_page.html`.
- **Impresora que se va**: al desactivar una impresora o cambiar su función o su conexión, sus trabajos
  en cola que ya no puede imprimir pasan a la impresora de su función de ahora (o esperan sin impresora)
  y se avisa `printing.job.queued`.
- **RGPD (decidido)**: al pasar a `done` o `cancelled`, el trabajo vacía `document` y `html`; conserva su
  número (`reference`), su función, su impresora y los sellos. Reimprimir es un trabajo nuevo pedido desde
  la app de origen (Ventas, Facturación…). Un `failed` guarda el documento para reintentarlo hasta
  que se cancela o se olvida: 30 días después de acabar (PRINTING-F20; mercado: PrintNode borra el
  documento al entregarlo o a las 2 semanas, BarTender Cloud guarda el historial 30 días, Universal Print
  enseña lo liberado 30 días, CUPS no guarda el fichero y acota el historial; la plataforma guarda 90 días
  el historial de Automatizaciones, que es lo que se consulta, y la cola no se consulta pasado un mes).
- **Sin ESC/POS en el servidor**: los bytes los hace la app (`crates/peripherals/src/escpos.rs`), que
  solo acepta documentos estructurados (`erplora_print(printer_id, document_type, data, job_id)`);
  PLAN-HUB §5 y la decisión de Ioan del 08/08/2026 (hub#501: el documento viaja estructurado y no hay
  traductor a ESC/POS en el servidor). Por eso no hay `python-escpos` ni `python-barcode`: el código de
  barras lo dibuja la impresora (`GS k`).
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17), solo en `hubs.erplora.com`; ids y
  fechas de solo lectura. Lo que guarda no pasa por las operaciones ni deja aviso.
- **Asistente**: cada operación declara `ai` y cada campo de `schemas.py` su `description`; la
  impresora se nombra por su nombre y el trabajo por su número de documento.

### Cambios frente al producto actual

| Producto actual | Plataforma nueva | Motivo |
|---|---|---|
| Las impresoras viven en el registro de la app de cada dispositivo; el Hub no las conoce | Las impresoras se dan de alta en el negocio (nombre, conexión, dirección, papel, función, activa) | Square y Toast: la impresora es del punto de venta; así la ven todos los dispositivos, la cola sabe a qué impresora va cada trabajo y el asistente las nombra |
| «Impresoras en la red»: búsqueda automática desde la app | «Buscar impresoras» (F02) pide la lista a la app y abre «Nueva impresora» rellena; alta por dirección (F03) siempre | La app solo busca para el hub vinculado: hasta que el SaaS sirva `/shell/` y `?shell=1` (PLAN-SAAS bloque 3) contesta `not_the_linked_hub` y la ventana lo dice |
| Una pantalla con tres zonas | Tres pestañas: Impresoras (con el estado), Cola y Ajustes | Patrón de la plataforma (Caja, Impuestos) |
| Ancho de papel global, guardado y sin efecto | Ancho de papel por impresora, que viaja con el trabajo (`paper_width`) | Duda abierta 2 resuelta como Epson/Star/Square. La app de hoy imprime siempre 32 caracteres por línea (`escpos.rs`, `LINE_WIDTH`): el ancho se guarda y viaja, pero no cambia el papel hasta que la app lo use (`UI-REQUESTS.md`, «App nativa») |
| Función por dispositivo («host» de un rol) | Función por impresora, y la impresora de cada función en ajustes | La impresora es la que imprime; el dispositivo solo la alcanza |
| Estados `pending`/`printing`/`done`/`dead`/`discarded` | `pending`/`sent`/`done`/`failed`/`cancelled` | Los del encargo; misma máquina (5 entregas, 90 s) |
| «Descartar» | «Cancelar», con motivo y sello | Mismo gesto; nombre del mercado |
| «Reintentar» solo un trabajo muerto | También uno enviado sin respuesta pasado su plazo | Un dispositivo caído dejaba el trabajo «Imprimiendo» hasta el siguiente `claim` |
| Imprimir al cobrar y la comanda los hacía el navegador al oír el aviso (`print-on-sale.ts`) | La venta encola en su transacción (`automatic`) | Ronda 9 (PLAN §14): sin reacciones del cliente |
| `printing.jobs.create` + `printing.print.due` + `host.print` | `printing.job.create` encola directamente | La cola es de la app; sin listener intermedio |
| Copias: no había | «Copias del ticket» (1–3) y `copies` por trabajo | Encargo; Square y Lightspeed lo ofrecen |
| Cajón sin trabajo propio | `open_drawer` en el tique, o un trabajo de cajón si el tique está apagado | Con el tique apagado el cajón no se abría |
| Prueba solo desde la app del dispositivo | La prueba es un trabajo de la cola | Funciona desde cualquier dispositivo y lo ve la cola |
| Permiso `printing.open_drawer` (sin uso) | Retirado | Ninguna operación lo pedía |
| Reintentar/descartar: administrador + permiso de impresora concedido al módulo | `printing.manage_jobs` (propietario y administrador) | No hay capacidades de módulo en la plataforma |
| Cabecera y pie heredados y su traslado (F15) | Retirado | No hay texto heredado que llevar |
| Tabla de enrutado retirada (`printing_routing`) | No existe | Sin consumidor desde printing#25 |
| La cola guardaba el documento sin límite de tamaño | ≤ 512 KB por documento, ≤ 2 MB de HTML | Que una sesión no meta ficheros en la BD |
| La cola refrescaba cada 30 s | En vivo (`useLive`) | Plataforma nueva |

### Paridad con la pantalla actual

| Pantalla actual (`erp-printing-settings`) | Plataforma nueva | Nota |
|---|---|---|
| Título «Impresoras» y frase de entrada | **Impresoras**: la frase de entrada, arriba | El título de la página es el de la app, como en el resto |
| «Cola de impresión»: tarjetas por función, aviso naranja, «Todo al día», error de lectura | **Impresoras**: «Cola de impresión» (`QueueSummary`), en vivo | Sin «Refrescar»: la plataforma refresca sola; sin «Imprime desde N dispositivos» (los dispositivos son de `base`, fase 2) |
| Trabajos atascados con «Reintentar» y «Descartar» | **Cola**: tabla completa con filtros, «Reintentar» y «Cancelar» con motivo | Se ven todos los trabajos, no solo los atascados; «Retirados recientemente» = filtro «Cancelado» |
| «Ajustes del ticket»: nota de Ventas y enlace, ancho de papel, tique y cajón al cobrar, «Guardar ajustes» | **Ajustes**: la misma tarjeta con copias y la impresora de cada función | El ancho de papel pasa a cada impresora; el traslado del texto antiguo se retira (F15) |
| «Impresoras en la red»: búsqueda, rol y «Probar» | **Impresoras**: tabla con función, conexión, dirección, papel, estado y «Probar»; «Buscar impresoras» en su ventana | La búsqueda llama a `erplora_discover_printers` de la app (F02) |
| «Añadir impresora por IP» | «Añadir impresora» (red, USB, Bluetooth o del sistema) | Se guarda en el negocio, no en el dispositivo |

### Paridad con los tests del módulo actual

| Test actual | Dónde queda |
|---|---|
| `jobs_create.contract.test.py` (clave idempotente, vocabulario cerrado, rol opcional, formato opcional, aislamiento por hub) | `tests/test_services.py` (clave, vocabulario, función, A4), `tests/test_schemas.py`, `tests/test_documents.py`, `tests/test_concurrency.py` |
| `settings_defaults.postgres.test.py` (ajustes de fábrica sin fila, la lectura no escribe) | `tests/test_queries.py::test_a_business_that_never_saved_has_the_factory_settings` |
| `settings_revive.pg.test.py` (guardar resucita la fila borrada) | No aplica: sin borrado lógico; `_locked_settings` crea la fila única la primera vez (`tests/test_services.py`) |
| `legacy_receipt_text.postgres.test.py` | Retirado con F15: no hay texto heredado |
| `routing_retired.contract.test.py` | No aplica: la tabla de enrutado no existe |
| `manifest.contract.test.py` | `tests/test_apps.py` (metadatos, permisos, menú) y `tests/test_api.py` (rutas, `ai` y `expose_api`) |
| Cola del Hub (`print_queue.rs`: 5 entregas, 90 s, hecho/fallido, reintentar/descartar sellados) | `tests/test_services.py` (bloques PRINTING-F18 y F14), `tests/test_concurrency.py` |

### Lo que NO hace, a propósito

- No compone documentos: cada app manda el suyo.
- No genera ESC/POS ni imágenes de códigos de barras: la app del dispositivo.
- No habla con las impresoras ni busca impresoras: la app del dispositivo.
- Nadie borra trabajos ni impresoras: se cancelan y se desactivan; la cola olvida sola lo terminado a los
  30 días (PRINTING-F20).
- No abre el cajón a mano («sin venta»).
- No enruta por categoría de producto: las estaciones de cocina serán de Cocina.

### Dudas abiertas

1. ¿El cajón al cobrar solo con efectivo (Square, Toast)? Hoy, con cualquier forma de pago; lo decidirá
   Ventas al pedirlo (`automatic` solo en cobros en efectivo).
2. ¿Abrir el cajón a mano («sin venta») con permiso y registro, desde Caja o desde Impresión?
3. ~~¿Cuánto tiempo se guardan los trabajos impresos, con su documento (RGPD)?~~ Decidido: el documento
   se vacía al imprimirse o cancelarse, y el trabajo terminado se borra a los 30 días (PRINTING-F20).
