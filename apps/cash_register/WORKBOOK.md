# Workbook — Caja (app)
Prefijo: CASH_REGISTER
Alcance MVP: núcleo
Estado de la app: completa (2026-10-21)

> Manual de usuario y especificación de la app `cash_register`. Se escribe **antes** que el código: no
> se programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en
> verde (servidor y páginas). Parte del `WORKFLOW.md` del módulo Caja del producto actual
> (`modules-workspace/modules/cash_register`, `origin/main` `9c7a237`, v1.3.75). La app hace lo mismo
> y se ve igual; los números de flujo se conservan porque otras apps los citan.

## Para qué sirve y para quién

Caja controla el **efectivo del cajón por turnos**. Se abre una sesión con el fondo que hay en el
cajón; durante el turno, los cobros, las anulaciones y las devoluciones de Ventas aparecen solos, y
las entradas y salidas de efectivo (cambio traído de la caja fuerte, un pago a un proveedor, una
retirada al banco) se apuntan a mano; se cuenta el cajón por billetes y monedas, y al cerrar se
compara lo que debería haber (**esperado**) con lo que se ha contado: la **diferencia** queda guardada
para siempre. Sirve igual a la peluquería y al restaurante.

Quién la usa:

- El **empleado** que hace de cajero: abre, apunta, cuenta y cierra.
- El **responsable**: lo mismo y, además, ve el efectivo esperado aunque el arqueo sea ciego.
- El **propietario** y el **administrador**: todo, y además configuran la caja y dan de alta los
  cajones.

Caja no cobra (es de Ventas), no abre el cajón físico (lo hará Impresión) y no factura.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó.

- [Toast — revisión de turno](https://doc.toasttab.com/doc/platformguide/platformCompletingShiftReview.html):
  al cerrar se enseña lo que queda abierto y se avisa sin impedir el cierre; el cajón se cierra al
  corte del día de negocio (04:00 de fábrica) si nadie lo cerró; el cierre ciego, con un permiso que
  deja ver el esperado al supervisor.
- [Lightspeed — lista de comprobación del turno](https://resto-support.lightspeedhq.com/hc/en-us/article_attachments/360044738513):
  apertura con fondo, entradas y salidas, recuento ciego y cierre por turno.
- Square (gestión del cajón): «esperado en el cajón» visible durante el turno, entradas y salidas con
  motivo, informe del cajón por sesión con el desglose por forma de pago; informe parcial (X) y de
  cierre (Z).
- Odoo, Shopify POS, Loyverse y Lightspeed Retail: con el control de caja encendido, no se cobra en
  efectivo sin una sesión abierta; la pantalla de apertura se pone delante del TPV.
- Del mercado en general: el cajón es solo efectivo (la tarjeta no cuenta para el esperado), un turno
  cerrado no se reabre, y lo que se corrige después se corrige con otro movimiento en el turno abierto,
  nunca reescribiendo el cerrado.

## Antes de empezar

- **Ventas** se enciende con Caja y no se puede apagar mientras Caja esté encendida: los cobros, las
  anulaciones y las devoluciones del turno son los de Ventas.
- **Ajustes**: los de fábrica valen desde el primer día (recuento obligatorio al cerrar, sin saldo
  negativo, sin arqueo ciego, sin cierre automático). Se cambian en **Caja → Ajustes**.
- **Cajones**: opcionales. Si el negocio tiene varios (barra y terraza), se dan de alta en **Caja →
  Ajustes → Cajones**; al abrir la sesión se elige uno. Con uno solo se elige solo.
- **Moneda**: la del negocio, la de su país, con sus decimales: el euro en España, el esloti en Polonia. Todos los
  importes de Caja van en ella, y el arqueo enseña sus billetes y monedas.
- **Zona horaria**: la del negocio. En esta fase, la hora de Madrid (`Europe/Madrid`) para todos: de
  ella salen el día de negocio, el número de sesión y la hora del cierre automático.

Configuración inicial, paso a paso:

1. Como administrador, abre **Caja → Ajustes**, decide fondo obligatorio, recuento obligatorio, saldo
   negativo, arqueo ciego y cierre automático, y pulsa «Guardar» (CASH_REGISTER-F01).
2. Si tienes varios cajones, dalos de alta en la misma pantalla (CASH_REGISTER-F02).
3. En **Caja**, pulsa «Abrir sesión» y abre con el fondo real (CASH_REGISTER-F03).
4. Cobra una venta pequeña en efectivo en **Ventas → Vender** y comprueba en **Caja** que el esperado
   sube.

## Pantallas

### Caja
Menú **Caja**. Arriba, el título «Caja» y el botón «Abrir sesión» (apagado mientras haya una sesión
abierta: «Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra.»). Debajo, las cifras de la
caja: «Sesión actual» y «Descuadres recientes» (CASH_REGISTER-F12; las mismas cifras salen también en
los paneles del **Inicio**). Después, la tabla de
sesiones, de la más reciente a la más antigua, 50 por página: Sesión, Abierta el, Estado («Abierta»,
«Cerrada»), Apertura, Esperado, Contado, Diferencia. Buscador «Buscar sesión…» (por número), filtros
(estado, número y los cuatro importes) y vista de tabla o tarjetas. Por fila: «Detalle» siempre y,
en la sesión abierta, «Movimiento», «Arqueo» y «Cerrar»; tocar la fila abre el detalle. Cada acción
abre su ventana:

- **Abrir sesión de caja**: «Cajón» (opcional; solo si hay cajones), «Fondo de apertura», «Notas»,
  «Abrir sesión» y «Cancelar».
- **Movimiento de caja · S-…**: «Tipo» («Entrada» o «Salida»), «Importe», «Concepto», «Registrar» y
  «Cancelar».
- **Arqueo de caja · S-…**: «Tipo de arqueo» («Cierre» de fábrica, o «Apertura»), «Notas», una casilla
  por billete y por moneda bajo «Billetes» y «Monedas» y «Total contado» en vivo; sin tabla para la
  moneda, un solo campo «Total contado». «Registrar arqueo» y «Cancelar».
- **Cerrar sesión · S-…**: la revisión del turno, «Esperado en el cajón» y «Diferencia» en vivo (si
  quien cierra puede verlos), «Efectivo contado», «Notas de cierre», «Cerrar sesión» y «Cancelar».

El éxito sale como aviso verde («Sesión abierta», «Movimiento de entrada registrado (…)», «Arqueo
registrado · total contado …», «Sesión S-… cerrada · esperado … · contado … · diferencia …»); un
rechazo, dentro de la ventana, con las palabras del servidor y el campo marcado. Vacía: «Sin sesiones
de caja.». Cargando: «Cargando…». Error al cargar: el mensaje en la tabla con «Reintentar».

Encima de la tabla pueden salir dos avisos:

- «Cobros fuera de turno»: cuántas líneas de venta (cobros, anulaciones, devoluciones) y cuánto
  efectivo no entraron en ningún turno, con «Ver» para su lista (CASH_REGISTER-F17).
- «La sesión S-… debía cerrarse sola a las 04:00»: el cierre automático está encendido y la sesión
  sigue abierta de un día anterior; «Abrir sesión» se enciende y, al abrir, la vieja se cierra sola
  (CASH_REGISTER-F10). Esa sesión ya no admite movimientos, arqueos ni cierre: en su fila solo queda
  «Detalle».

### Detalle de la sesión
Desde **Caja**, «Detalle» o tocar una fila: se abre como página, con su flecha de volver. Título
«Detalle de la sesión · S-…». Un resumen
en dos columnas: Estado, Cajón, Abierta (cuándo y quién), Cerrada (cuándo y quién, o «Cerrada sola»),
Movimientos (cuántos), Fondo de apertura, Ventas (todas las formas de pago) y, debajo, Ventas en
efectivo, Ventas con tarjeta y Ventas con otras formas de pago (esta solo si hubo), Devoluciones,
Entradas, Salidas, Invitaciones, Esperado, Contado y Diferencia, y las notas de apertura y de cierre.
En una sesión abierta Contado y Diferencia salen «—». Debajo, dos tablas, de lo más reciente a lo más
antiguo, 50 por página y en tarjetas en el móvil: **Movimientos** (Cuándo, Tipo, Importe con su signo,
Método, Concepto) y **Arqueos** (Cuándo, Tipo de arqueo, Total contado, Notas). Vacías: «Sin
movimientos en esta sesión.» y «Sin arqueos en esta sesión.». El botón «Imprimir» saca el informe en
papel: «Informe parcial (X)» si la sesión está abierta, «Cierre de caja (Z)» si está cerrada
(CASH_REGISTER-F16).

### Ajustes de Caja
Menú **Caja → Ajustes**. Una tarjeta «Caja» con «Activar caja», «Exigir fondo de apertura», «Exigir
recuento al cierre», «Permitir saldo negativo», «Arqueo ciego», «Cierre automático diario» y «Hora del
cierre automático» (de 00:00 a 23:00, en horas en punto), y «Guardar». Debajo, la tarjeta «Cajones»:
la lista de cajones (nombre, activo) con «Añadir cajón», «Cambiar nombre» y «Desactivar»/«Activar».
Quien no puede cambiar los ajustes los ve bloqueados con «No tienes permiso para cambiar estos
ajustes.». Cargando: «Cargando ajustes…». Error: «No se pudieron cargar los ajustes.» con
«Reintentar»; al guardar, «No se pudieron guardar los ajustes.». Guardado: «Ajustes guardados.».
«Guardar» se enciende al cambiar algo y, mientras los ajustes no se han guardado nunca, también sin
cambios: así el negocio se queda con los de fábrica.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (o el texto de su pantalla: «Cargando ajustes…», «Cargando las cifras de la caja…») mientras llega el primer resultado. |
| Vacío | «Sin sesiones de caja.», «Sin movimientos en esta sesión.», «Sin arqueos en esta sesión.», «Todavía no hay sesiones cerradas.». |
| Error | El aviso con «Reintentar»; un rechazo de una acción sale dentro de su ventana, junto a su campo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva | «Caja no está activa en este negocio.» en lugar de la lista. |
| Sin permiso | No aparece lo que no puede hacer («Abrir sesión», «Movimiento», «Arqueo», «Cerrar», «Guardar»); si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Vertical | Estado |
|---|---|---|---|
| CASH_REGISTER-F01 | Configurar cómo funciona la caja | común | hecho |
| CASH_REGISTER-F02 | Dar de alta, renombrar y desactivar un cajón | común | hecho |
| CASH_REGISTER-F03 | Abrir el turno de caja con el fondo inicial | común | hecho |
| CASH_REGISTER-F04 | Vender solo con la caja abierta | común | hecho |
| CASH_REGISTER-F05 | Registrar una entrada o una salida de efectivo | común | hecho |
| CASH_REGISTER-F06 | Contar el cajón por billetes y monedas | común | hecho |
| CASH_REGISTER-F07 | Contar a ciegas: quién ve el efectivo esperado | común | hecho |
| CASH_REGISTER-F08 | Revisar lo que queda pendiente antes de cerrar | común | hecho |
| CASH_REGISTER-F09 | Cerrar el turno: esperado, contado y diferencia | común | hecho |
| CASH_REGISTER-F10 | Cerrar sola la caja olvidada al final del día | común | hecho |
| CASH_REGISTER-F11 | Consultar una sesión y revisar un descuadre | común | hecho |
| CASH_REGISTER-F12 | Ver la caja en los paneles del inicio | común | hecho |
| CASH_REGISTER-F13 | Anotar en la caja cada cobro de una venta | común | hecho |
| CASH_REGISTER-F14 | Compensar en la caja una venta anulada | común | hecho |
| CASH_REGISTER-F15 | Anotar en la caja una devolución | común | hecho |
| CASH_REGISTER-F16 | Imprimir el informe de la sesión (X o Z) | común | hecho |
| CASH_REGISTER-F17 | Ver los cobros fuera de turno | común | hecho |

### CASH_REGISTER-F01 Configurar cómo funciona la caja
<!-- origen: fi:modules/cash_register#command-cash_register-settings-update fi:modules/cash_register#events-emitidos-catalogo fi:modules/cash_register#navigation-settings fi:modules/cash_register#permission-role_permissions fi:modules/cash_register#query-cash_register-settings-get old:cash_register/WORKFLOW.md#cash_register-f01 -->
Estado: hecho
Vertical: común
Actor: administrador
Pantalla: Inicio: Termina de configurar tu negocio; Ajustes de Caja
Pasos:
1. Mientras los ajustes de caja no se han guardado nunca, en el **Inicio** la lista «Termina de
   configurar tu negocio» trae el paso «Tu caja» («Decide cómo se abre y se cierra la caja: el fondo
   inicial, el arqueo de cierre y la pantalla del TPV que queda bloqueada hasta abrirla.»), marcado
   «Recomendado». Su «Configurar» lleva a **Caja → Ajustes**, que también se abre desde el menú.
2. Enciende o apaga «Activar caja», «Exigir fondo de apertura», «Exigir recuento al cierre», «Permitir
   saldo negativo», «Arqueo ciego» y «Cierre automático diario» con su hora.
3. Pulsa «Guardar». Se guarda lo que cambiaste; lo demás queda como estaba. La primera vez se puede
   guardar sin cambiar nada: el negocio se queda con los de fábrica.
4. Sale «Ajustes guardados.» y, desde ese momento, el servidor aplica el fondo obligatorio (F03), el
   recuento obligatorio (F09), el saldo negativo (F05), el arqueo ciego (F07) y el cierre automático
   (F10), venga la orden de la pantalla, del asistente o de la API. En el Inicio, «Tu caja» sale hecho
   sin recargar.
Entra: las decisiones del administrador.
Sale: los ajustes de caja del negocio, una sola fila (avisa: `cash_register.settings.updated`, también
el primer guardado sin cambios). Sin guardar nunca, valen los de fábrica y «Tu caja» sigue pendiente;
abrir una sesión no lo cuenta como hecho.
Si falla: «No se pudieron guardar los ajustes.» con el motivo, y los ajustes quedan como estaban. Si
la lectura falla, la pantalla no enseña valores (nunca los de fábrica como si fueran los del negocio)
y ofrece «Reintentar». Sin el permiso de ajustes, los campos salen bloqueados, no hay «Guardar» y el
Inicio no le enseña el paso «Tu caja».
Implicados: CASH_REGISTER-F03, F05, F07, F09, F10

### CASH_REGISTER-F02 Dar de alta, renombrar y desactivar un cajón
<!-- origen: fi:modules/cash_register#command-cash_register-registers-create fi:modules/cash_register#query-cash_register-registers-list old:cash_register/WORKFLOW.md#cash_register-f02 -->
Estado: hecho
Vertical: común
Actor: administrador, asistente
Pantalla: Ajustes de Caja
Pasos:
1. En **Caja → Ajustes → Cajones**, pulsa «Añadir cajón», escribe su nombre («Barra») y pulsa
   «Guardar»; o pídeselo al asistente («crea un cajón llamado Barra»).
2. Para cambiarle el nombre, pulsa «Cambiar nombre»; para dejar de usarlo, «Desactivar».
3. El cajón activo aparece en «Cajón» al abrir la caja.
Entra: el nombre del cajón.
Sale: el cajón (avisa: `cash_register.register.created` o `cash_register.register.updated`). Un cajón
nunca se borra: las sesiones lo nombran.
Si falla: sin nombre, «Escribe el nombre del cajón.»; con un nombre que ya tiene otro cajón (sin
distinguir mayúsculas), «Ya hay un cajón con ese nombre.».
Implicados: CASH_REGISTER-F03

### CASH_REGISTER-F03 Abrir el turno de caja con el fondo inicial
<!-- origen: fi:modules/cash_register#events-emitidos-catalogo fi:modules/cash_register#command-cash_register-session-open fi:modules/cash_register#query-cash_register-current_session old:cash_register/WORKFLOW.md#cash_register-f03 qa:modules/cash_register/open-register qa:modules/cash_register/shift-change wf:peluqueria-dia#rec_peluqueria-f01 wf:restaurante-dia#rec_restaurante-f01 -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador, asistente
Pantalla: Caja
Pasos:
1. En **Caja**, pulsa «Abrir sesión».
2. Elige el «Cajón» si hay varios (con uno solo se elige solo), escribe el «Fondo de apertura» tal
   como se lee («150,50»; vacío es 0) y, si quieres, «Notas».
3. Pulsa «Abrir sesión».
4. Sale «Sesión abierta»; la sesión aparece arriba de la tabla como «Abierta», con su número
   `S-AAMMDD-NNNN` (correlativo del día de negocio, lo pone el sistema) y «Abrir sesión» se apaga.
Entra: cajón, fondo y notas; los ajustes del negocio.
Sale: la sesión abierta, a nombre de quien la abre (avisa: `cash_register.session.opened`). El fondo
cuenta para el esperado desde ese momento.
Si falla: «Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra.» (una por negocio, sea cual
sea el cajón; si dos dispositivos abren a la vez, solo uno abre y el otro recibe este aviso); con el
fondo obligatorio y el fondo vacío o a cero, «Este negocio exige fondo de apertura: indica el efectivo
con el que empieza la caja.» bajo el campo; un cajón desactivado o que no existe, «Ese cajón no está
disponible.»; un importe ilegible («Esto no es un importe. Escribe una cifra, por ejemplo 12,50.»),
negativo o ambiguo («1.250») se para antes de enviar.
Implicados: CASH_REGISTER-F04, F09

### CASH_REGISTER-F04 Vender solo con la caja abierta
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f01 wf:restaurante-dia#rec_restaurante-f01 old:cash_register/WORKFLOW.md#cash_register-f04 -->
Estado: hecho — lo aplica Ventas al cobrar (SALE-F08): pregunta a Caja si la caja está abierta (ver
«Contrato con Ventas»). Lo que se cobra en efectivo sin turno porque Caja estaba apagada o no
respondió sale en «Cobros fuera de turno» (F17), sin perder nada.
Vertical: común
Actor: empleado, sistema
Pantalla: Vender (de Ventas)
Pasos:
1. Con «Activar caja» encendido y sin sesión abierta, el cajero intenta cobrar en efectivo.
2. Ventas lo rechaza con «La caja está cerrada: abre una sesión de caja para cobrar en efectivo.» (409
   `sale.cash_register_closed`); con tarjeta, transferencia u otro cobra. Una sesión abierta pasada su
   corte (F10) sigue dejando cobrar: lo cobrado sale en F17.
Entra: «Activar caja» y si hay sesión abierta (`cash_register.session.current`).
Sale: nada propio.
Si falla: si Caja no responde, Ventas cobra (el bloqueo cede antes que parar las ventas) y el cobro
aparece en F17.
Implicados: SALE-F08

### CASH_REGISTER-F05 Registrar una entrada o una salida de efectivo
<!-- origen: fi:modules/cash_register#command-cash_register-movement-add fi:modules/cash_register#query-cash_register-movements-list old:cash_register/WORKFLOW.md#cash_register-f05 qa:modules/cash_register/cash-count-and-movements -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador, asistente
Pantalla: Caja
Pasos:
1. En la fila de la sesión abierta, pulsa «Movimiento».
2. Elige «Entrada» (cambio traído de la caja fuerte) o «Salida» (pago a un proveedor, retirada al
   banco), escribe el «Importe» en positivo y el «Concepto».
3. Pulsa «Registrar».
4. Sale «Movimiento de entrada registrado (…)» o «Movimiento de salida registrado (…)»; en el detalle
   aparece el movimiento (la salida en negativo) y el esperado sube o baja.
Entra: tipo, importe y concepto. Desde la pantalla el medio es siempre efectivo; el asistente o la API
pueden apuntar también tarjeta, transferencia u otro, que salen en la lista y en «Entradas» o
«Salidas» pero no cuentan para el esperado.
Sale: el movimiento, a nombre de quien lo apunta (avisa: `cash_register.movement.added`). El signo lo
pone el sistema según el tipo.
Si falla: «Esta salida dejaría la caja en negativo y el saldo negativo no está permitido.» si los
ajustes no lo permiten; un importe cero, ilegible o negativo se para antes de enviar; la sesión
cerrada en otro dispositivo: «Esa caja está cerrada: una caja cerrada no acepta movimientos nuevos.».
Un movimiento equivocado no se edita ni se borra: se apunta el contrario con un concepto que diga por
qué.
Implicados: ninguno

### CASH_REGISTER-F06 Contar el cajón por billetes y monedas
<!-- origen: qa:modules/cash_register/cash-count-and-movements fi:modules/cash_register#command-cash_register-count-add-handler-wasm fi:modules/cash_register#query-cash_register-counts-list old:cash_register/WORKFLOW.md#cash_register-f06 -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador
Pantalla: Caja
Pasos:
1. En la fila de la sesión abierta, pulsa «Arqueo».
2. Deja «Cierre» (al final del turno) o elige «Apertura» (para comprobar el fondo); escribe cuántos
   hay de cada billete y moneda; «Total contado» se va sumando. Sin tabla para la moneda, escribe el
   total.
3. Pulsa «Registrar arqueo».
4. Sale «Arqueo registrado · total contado …» y el arqueo aparece en el detalle. Si era de «Cierre»,
   se abre directamente «Cerrar sesión» con «Efectivo contado» ya puesto (F09); el arqueo no cierra
   nada por sí solo.
Entra: las cantidades por billete y moneda, o el total.
Sale: el arqueo con su desglose (avisa: `cash_register.count.added`). El total lo suma el sistema con
los decimales de la moneda; un total escrito a mano (o enviado por la API) se guarda tal cual y
prevalece sobre el desglose.
Si falla: una sesión cerrada, «Esa caja está cerrada: una caja cerrada no acepta movimientos
nuevos.»; un billete o moneda que no es de la moneda del negocio, bajo el desglose; sin desglose ni
total, «Cuenta el cajón: indica los billetes y monedas o el total.».
Implicados: CASH_REGISTER-F09

### CASH_REGISTER-F07 Contar a ciegas: quién ve el efectivo esperado
<!-- origen: old:cash_register/WORKFLOW.md#cash_register-f07 -->
Estado: hecho
Vertical: común
Actor: administrador, responsable, empleado
Pantalla: Caja, Detalle de la sesión
Pasos:
1. El administrador enciende «Arqueo ciego» y guarda (F01).
2. Durante el turno, en la sesión abierta, el empleado ve vacía la columna Esperado; en el detalle ve
   el fondo y «—» en Esperado, Ventas, Devoluciones, Entradas, Salidas e Invitaciones, y en la lista de
   movimientos solo las entradas y salidas apuntadas a mano: ni las ventas, ni las anulaciones, ni las
   devoluciones, así que no hay con qué sumar el esperado (Square y Lightspeed ocultan igual el esperado
   en el cierre ciego). El responsable, el propietario y el administrador lo ven todo: la tabla, el
   detalle, la lista y la ventana de cierre. El asistente tampoco se lo dice a quien no puede verlo: el
   resumen del cierre (F09) le llega sin esperado ni diferencia, y el asistente no los conoce.
3. El cajero cuenta (F06) y cierra (F09) sin ver el esperado.
4. Al cerrar aparecen esperado, contado y diferencia para todos.
Entra: el ajuste «Arqueo ciego» y el permiso de ver el esperado (responsable, propietario y
administrador).
Sale: nada nuevo; cambia lo que ve cada uno. La regla del saldo negativo sigue funcionando con el
esperado real.
Si falla: nada propio.
Implicados: CASH_REGISTER-F09

### CASH_REGISTER-F08 Revisar lo que queda pendiente antes de cerrar
<!-- origen: old:cash_register/WORKFLOW.md#cash_register-f08 wf:peluqueria-dia#rec_peluqueria-f16 wf:restaurante-dia#rec_restaurante-f16 -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador
Pantalla: Caja
Pasos:
1. Al abrir «Cerrar sesión» sale «Comprobando lo que queda pendiente…».
2. Si queda algo, sale «Revisión del turno» con cada cosa pendiente: «Cuentas abiertas: N» y sus
   títulos (Ventas), «Comandas sin servir: N» y sus mesas o números (Cocina: por preparar, en
   preparación o listas para servir) e «Impresiones sin salir: N» y sus funciones («Recibos», «Cocina»,
   «Barra», «Etiquetas»; Impresión: lo que espera en la cola y lo que falló). Sin nada pendiente no sale
   nada.
3. El primer «Cerrar sesión» no cierra: avisa «El turno se cerrará igualmente. Pulsa otra vez para
   confirmar.» y el botón pasa a «Cerrar de todos modos».
4. El segundo clic cierra (F09).
Entra: las cuentas abiertas de Ventas, las comandas en marcha de Cocina y la cola de Impresión. Si Cocina
o Impresión no están encendidas en el negocio, no tienen nada pendiente.
Sale: nada; avisa, nunca impide.
Si falla: si una lectura no se puede hacer, «No se ha podido comprobar lo que queda pendiente, así que
esta revisión puede estar incompleta.»; si las otras encontraron algo, sale dentro del aviso y se pide
igual la confirmación; si no, se cierra con un solo clic.
Implicados: SALE-F17, SALE-F18, KITCHEN-F31, PRINTING-F01

### CASH_REGISTER-F09 Cerrar el turno: esperado, contado y diferencia
<!-- origen: fi:modules/cash_register#query-cash_register-current_session qa:modules/cash_register/shift-change wf:peluqueria-dia#rec_peluqueria-f16 wf:restaurante-dia#rec_restaurante-f16 fi:modules/cash_register#command-cash_register-session-close old:cash_register/WORKFLOW.md#cash_register-f09 qa:modules/cash_register/close-register-z-report -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador, asistente
Pantalla: Caja
Pasos:
1. En la fila de la sesión abierta, pulsa «Cerrar» (o llega desde un arqueo de «Cierre», F06); o
   pídeselo al asistente («cierra la caja con 250 € contados») y sigue en el paso 5.
2. Escribe o revisa el «Efectivo contado» (viene del último arqueo de cierre de esa sesión; nunca de
   uno de apertura); si puedes ver el esperado, «Esperado en el cajón» y «Diferencia» se ven mientras
   escribes. Añade «Notas de cierre» si quieres.
3. Pulsa «Cerrar sesión» (dos veces si la revisión del turno avisó, F08).
4. Sale «Sesión S-… cerrada · esperado … · contado … · diferencia …»; la fila pasa a «Cerrada» con los
   tres importes fijos para siempre y «Abrir sesión» vuelve a encenderse.
5. Con el asistente, antes de cerrar nada te enseña el resumen del cierre: el número de la sesión, el
   efectivo contado y, si puedes ver el esperado, el esperado y la diferencia (con el arqueo ciego, a
   quien no lo ve no se lo dice: el asistente tampoco lo conoce, F07), y lo que la revisión del turno
   encuentre pendiente (F08).
6. Después sale «¿Ejecutar esta acción?» con «Cerrar en Caja. Revisa cada dato antes de seguir.», la
   sesión y el efectivo contado: escribe «CONFIRMAR» y pulsa «Ejecutar». Se cierra esa misma sesión, a tu
   nombre y con los tres importes, igual que desde la pantalla.
7. Si pulsas «Cancelar», no se cierra nada: la sesión sigue abierta y el asistente lo dice («No se hizo,
   cancelado: Cerrar en Caja»).
Entra: el efectivo contado y las notas, escritos en la ventana o dichos al asistente.
Sale: la sesión cerrada con esperado (fondo + ventas y entradas en efectivo − salidas, devoluciones y
anulaciones en efectivo; lo cobrado o apuntado con tarjeta, transferencia u otro no cuenta), contado y
diferencia (contado − esperado: positiva sobra, negativa falta), a nombre de quien cierra (avisa:
`cash_register.session.closed`). Las líneas de Ventas del turno quedan copiadas en la sesión: lo que
pase después (una anulación de ayer) va al turno abierto, nunca a este.
Si falla: «Escribe el efectivo contado para cerrar la sesión.» con el campo vacío (la pantalla siempre
lo pide; el ajuste de recuento obligatorio lo hace cumplir también al asistente y a la API); si otro
dispositivo la cerró antes, «Esa caja está cerrada: una caja cerrada no acepta movimientos nuevos.»
(dos cierres a la vez: uno cierra, el otro recibe este aviso). Al asistente, si el recuento es
obligatorio y no dices cuánto has contado, te lo pide con ese mismo aviso y no sale la confirmación; si
la sesión del resumen se cierra en otro dispositivo antes de que confirmes, no se cierra ninguna otra:
sale el aviso de caja cerrada. No se reabre una sesión cerrada por error: se abre otra con el efectivo
real como fondo.
Implicados: CASH_REGISTER-F06, F07, F08

### CASH_REGISTER-F10 Cerrar sola la caja olvidada al final del día
<!-- origen: old:cash_register/WORKFLOW.md#cash_register-f10 -->
Estado: hecho — el cierre se aplica al abrir la siguiente sesión, y el pase cada 5 minutos lo hace el Hub
por su cuenta
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. El administrador enciende «Cierre automático diario» y elige la hora (04:00 de fábrica).
2. Cada 5 minutos el Hub mira si ya pasó el último corte en la hora del negocio y cierra la sesión que
   siga abierta desde antes de ese corte; la abierta después del corte no se toca. Un Hub parado
   durante el corte la cierra en cuanto vuelve, y quien abre la caja por la mañana también: la vieja
   se cierra sola antes de abrir la nueva.
3. En Caja la sesión aparece «Cerrada», con «Cerrada sola» en el detalle, su esperado al corte y
   Contado y Diferencia vacíos.
Entra: el ajuste, la hora y la zona horaria del negocio.
Sale: la sesión cerrada a la hora del corte, sin recuento y sin persona (avisa:
`cash_register.session.closed` una vez por sesión). Mientras sigue abierta pasado el corte, sus cifras
se paran en el corte y lo cobrado después ya sale como «Cobros fuera de turno» (F17), también en la
ventana de abrir la siguiente, para contarlo en su fondo; nunca entra en la vieja ni en la nueva.
Si falla: con el ajuste apagado no cierra nada. Una sesión pasada su corte no admite movimientos,
arqueos ni cierre: «La sesión S-… debía cerrarse sola a las 04:00: abre una sesión nueva (esta se
cierra entonces).» (409 `cash_register.session_auto_close_due`).
Implicados: CASH_REGISTER-F17

### CASH_REGISTER-F11 Consultar una sesión y revisar un descuadre
<!-- origen: fi:modules/cash_register#query-cash_register-movements-list fi:modules/cash_register#query-cash_register-session-summary fi:modules/cash_register#query-cash_register-sessions-list old:cash_register/WORKFLOW.md#cash_register-f11 -->
Estado: hecho
Vertical: común
Actor: responsable, administrador, empleado
Pantalla: Detalle de la sesión
Pasos:
1. En Caja, pulsa «Detalle» o toca la fila de cualquier sesión, abierta o cerrada.
2. Lee el resumen: quién abrió y cerró, el cajón, el fondo, las ventas por forma de pago, devoluciones,
   entradas, salidas, invitaciones aparte (son coste, no efectivo), esperado, contado, diferencia y las
   notas.
3. Repasa Movimientos: cada venta se nombra por su documento («Tique …», «Factura …»), una devolución
   «Devolución de …» y una anulación «Anulación de …»; un movimiento a mano enseña su concepto. Y repasa
   Arqueos.
4. Pulsa «Volver».
Entra: la sesión elegida; el número y el documento de cada venta, de Ventas.
Sale: nada; es de solo lectura.
Si falla: «No se pudo cargar el detalle de la sesión» o el error de cada tabla con «Reintentar».
Implicados: SALE-F28

### CASH_REGISTER-F12 Ver la caja en los paneles del inicio
<!-- origen: fi:modules/cash_register#widget-cash_register-current_session-kpi fi:modules/cash_register#widget-cash_register-recent_sessions-bar-list old:cash_register/WORKFLOW.md#cash_register-f12 -->
Estado: hecho
Vertical: común
Actor: responsable, administrador, empleado
Pantalla: Inicio; Caja
Pasos:
1. En el **Inicio**, el panel «Caja (sesión actual)» sale de serie con el efectivo esperado en el cajón
   de la sesión abierta, en la moneda del negocio, y se mueve solo con cada cobro, cada movimiento, la
   apertura y el cierre; sin sesión abierta dice «Sin datos». Solo lo tiene quien puede ver el esperado
   con el arqueo ciego (el propietario, el administrador y el responsable); el empleado, que cuenta
   a ciegas, no.
2. «Descuadres recientes» se añade con ⋮ («Personalizar panel»), donde va agrupado bajo «Caja»: una
   línea por cada una de las ocho últimas sesiones cerradas, de la que se cerró más tarde a la más
   antigua, con su número y su diferencia con signo y céntimos. Lo tiene quien ve las sesiones.
3. Además, en **Caja**, encima de la tabla salen dos tarjetas. «Sesión actual» enseña el «Esperado en el
   cajón» de la sesión abierta y su número, y se mueve solo con cada cobro y cada movimiento; sin sesión
   abierta, «No hay ninguna sesión abierta.».
4. «Descuadres recientes» enseña la diferencia de las ocho últimas sesiones cerradas, de la que se cerró
   más tarde a la más antigua, con su signo y sus céntimos y una barra tan larga como la diferencia:
   roja si faltó, verde si sobró. Una sesión cerrada sola, sin recuento, sale «—».
Entra: la sesión abierta, las sesiones cerradas y la moneda del negocio.
Sale: nada.
Si falla: «No se pudieron cargar las cifras de la caja.» con «Reintentar»; en el Inicio, un panel que no
se puede leer dice «No disponible». Con el arqueo ciego, quien no puede ver el esperado lo ve «—» en
**Caja** y no tiene el panel del esperado en el Inicio (F07). Sin sesiones cerradas, «Todavía no hay
sesiones cerradas.» (en el Inicio, «Sin datos»).
Implicados: CASH_REGISTER-F07, F09

### CASH_REGISTER-F13 Anotar en la caja cada cobro de una venta
<!-- origen: fi:modules/cash_register#command-cash_register-record_sale-handler-wasm fi:modules/cash_register#event-listen-sale-completed-cash_register-record_sale old:cash_register/WORKFLOW.md#cash_register-f13 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: Caja, Detalle de la sesión
Pasos:
1. El cajero cobra en **Ventas → Vender**.
2. Sin que nadie teclee nada, la sesión abierta recibe una línea «Venta» por cada forma de pago del
   cobro: con pago mixto, una en efectivo y otra con tarjeta.
3. Cada línea lleva lo que esa forma de pago cubrió, no lo entregado: el cambio ya salió del cajón.
4. Solo las de efectivo suben el esperado; las de tarjeta, transferencia u otro salen en la lista y en
   «Ventas con tarjeta» o «Ventas con otras formas de pago». El coste de las invitaciones va aparte, una
   vez por venta, a «Invitaciones».
Entra: los cobros de Ventas (venta, sus formas de pago con su tipo e importe, y el coste de las
invitaciones).
Sale: la línea en la sesión abierta, al momento (la pantalla se refresca sola con el aviso
`sale.sale.completed`). Una venta de total cero sin invitaciones no deja nada; una toda invitación
deja una línea de importe cero con su coste.
Si falla: sin sesión abierta, el cobro no se pierde: sale en F17.
Implicados: SALE-F01, SALE-F02, SALE-F03, SALE-F15

### CASH_REGISTER-F14 Compensar en la caja una venta anulada
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 fi:modules/cash_register#command-cash_register-_reverse_sale-interno fi:modules/cash_register#event-listen-sale-voided-cash_register-_reverse_sale old:cash_register/WORKFLOW.md#cash_register-f14 wf:restaurante-dia#rec_restaurante-f15 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: Caja, Detalle de la sesión
Pasos:
1. Alguien anula en Ventas una venta ya cobrada.
2. La sesión abierta en ese momento recibe una «Anulación de …» por cada forma de pago de la venta; la
   de efectivo baja el esperado. La línea de la venta no se toca.
3. Va siempre al turno abierto al anular, aunque la venta sea de un turno ya cerrado: el cerrado no se
   mueve. Anulada en el mismo turno, la venta y su anulación se compensan y no cuentan.
Entra: la venta anulada y cuándo se anuló (`sale.sale.voided`).
Sale: la línea de anulación. Cada anulación se anota una sola vez.
Si falla: sin sesión abierta, la anulación sale en F17. Anular no corrige nada fiscal: el tique sigue
emitido (SALE-F30).
Implicados: SALE-F30

### CASH_REGISTER-F15 Anotar en la caja una devolución
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:restaurante-dia#rec_restaurante-f15 old:cash_register/WORKFLOW.md#cash_register-f15 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: Caja, Detalle de la sesión
Pasos:
1. Alguien hace en Ventas una devolución, total o parcial, de una venta de hoy o de otro día.
2. La sesión abierta recibe una «Devolución de …» por cada forma de pago por la que vuelve el dinero.
3. Manda por dónde vuelve el dinero, no cómo se cobró: una venta con tarjeta devuelta en efectivo baja
   el esperado; una en efectivo devuelta a la tarjeta no lo toca.
Entra: la devolución con sus formas de pago e importes (`sale.sale.refunded`).
Sale: la línea de devolución. Cada forma de pago de cada devolución se anota una sola vez.
Si falla: sin sesión abierta, la devolución sale en F17.
Implicados: SALE-F31

### CASH_REGISTER-F16 Imprimir el informe de la sesión (X o Z)
<!-- origen: qa:modules/cash_register/close-register-z-report old-hub:HUB_PERIPHERALS-F13 -->
Estado: hecho
Vertical: común
Actor: responsable, administrador, empleado
Pantalla: Detalle de la sesión
Pasos:
1. En el detalle de una sesión, pulsa «Imprimir».
2. Con **Impresión** encendida y una impresora de recibos activa, el informe va a su cola y sale «Informe
   enviado a la impresora …» (o «… a la impresora de recibos» si no hay una elegida); el dispositivo con
   esa impresora lo saca en papel. Con la sesión abierta es el «Informe parcial (X)»; cerrada, el «Cierre de
   caja (Z)».
3. El papel lleva el número de sesión con su X o su Z, quién la abrió (X) o la cerró (Z; «Cerrada sola» si
   se cerró sola), el fondo, el esperado y, línea a línea, las ventas por forma de pago, devoluciones,
   entradas, salidas, invitaciones, el esperado y, en el Z, el contado y el descuadre.
4. Sin Impresión encendida o sin ninguna impresora de recibos activa, sale el diálogo de impresión del
   navegador con el mismo informe (en la cola esperaría para siempre).
Entra: el resumen de la sesión, el mismo que enseña la pantalla.
Sale: un trabajo en la cola de recibos de Impresión (o el papel del navegador). Cada «Imprimir» es un papel
nuevo.
Si falla: «No se pudo imprimir.» con el motivo de Impresión (por ejemplo, sin permiso de imprimir). Con el
arqueo ciego, quien no puede ver el esperado no ve «Imprimir» en una sesión abierta (el informe lleva el
esperado); en una cerrada sí.
Implicados: CASH_REGISTER-F11, PRINTING-F17

### CASH_REGISTER-F17 Ver los cobros fuera de turno
<!-- origen: nuevo (Caja de ERPlora: lo cobrado sin turno no se pierde) -->
Estado: hecho
Vertical: común
Actor: empleado, responsable, administrador
Pantalla: Caja
Pasos:
1. En Caja sale «Cobros fuera de turno: N líneas de venta no entraron en ninguna sesión · … en
   efectivo» cuando alguna línea de Ventas no cayó en ningún turno:
   - con la caja cerrada: lo cobrado, anulado o devuelto desde el último turno sin sesión abierta;
   - con una sesión olvidada pasado su corte (F10): lo de después del corte;
   - con una sesión abierta: las rezagadas del turno anterior, confirmadas mientras se cerraba (su Z
     ya no las recoge).
2. Pulsa «Ver» para ver la lista (cuándo, tipo, importe, método y documento).
3. Al abrir la sesión, cuenta ese efectivo en el fondo: ya está en el cajón (la ventana de abrir lo
   recuerda).
Entra: los cobros, anulaciones y devoluciones de Ventas que no cayeron en ninguna sesión.
Sale: nada; avisa. Con «Activar caja» apagado no hay turnos que cumplir y no avisa.
Si falla: nada propio.
Implicados: CASH_REGISTER-F04, F10, F13

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia
persona) y la API, con las mismas reglas y los mismos permisos. Pensado para la voz: una sesión se
nombra por su número («S-261014-0001») y, si no se dice cuál, se entiende la abierta («cierra la
caja», «apunta una salida de 20 €»); un cajón, por su nombre.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los ajustes de caja (los de fábrica si nunca se guardaron, sin fecha de guardado) | ver sesiones | F01 | `cash_register.settings.get` |
| Los cajones, con búsqueda por nombre, filtro de activos y páginas (hasta 100) | ver sesiones | F02, F03 | `cash_register.register.list` |
| Las sesiones, de la más reciente a la más antigua (o por cuándo se cerraron), con búsqueda por número, filtros (estado, número, cajón, fechas e importes) y páginas | ver sesiones | F03, F09, F12 | `cash_register.session.list` |
| La sesión abierta con su esperado (si quien pregunta puede verlo), si la caja está activada y los cobros fuera de turno (cuántos y su efectivo) | ver sesiones | F04, F10, F12, F17 | `cash_register.session.current` |
| Una sesión (por id o número) con su resumen: ventas por forma de pago, devoluciones, entradas, salidas, invitaciones, esperado, contado y diferencia | ver sesiones | F11, F16 | `cash_register.session.get` |
| Los movimientos de una sesión (o los cobros fuera de turno), con búsqueda, filtros y páginas; con el arqueo ciego, a quien no puede ver el esperado, solo los apuntados a mano de la sesión abierta | ver movimientos | F07, F11, F17 | `cash_register.movement.list` |
| Los arqueos de una sesión, con páginas | ver arqueos | F06, F09, F11 | `cash_register.count.list` |
| El resumen del cierre de una sesión (la abierta si no se dice) con el efectivo contado: su número, el contado y, si quien pregunta puede verlo, el esperado y la diferencia, y lo que la revisión del turno encuentra abierto; no cierra nada | cerrar | F08, F09 | `cash_register.session.closing_summary` |
| La moneda del negocio, sus decimales y sus billetes y monedas | ver sesiones | F06, F12 | `cash_register.currency.get` |

Todas se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Guarda los ajustes (solo lo que se manda) | ajustes | F01 | `cash_register.settings.update` |
| Da de alta un cajón | ajustes | F02 | `cash_register.register.create` |
| Cambia el nombre de un cajón o lo desactiva y reactiva | ajustes | F02 | `cash_register.register.update` |
| Abre una sesión con su fondo | abrir | F03, F10 | `cash_register.session.open` |
| Cierra una sesión con el efectivo contado | cerrar | F09 | `cash_register.session.close` |
| Cierra las sesiones olvidadas al corte del día | cerrar | F10 | `cash_register.session.auto_close` |
| Apunta una entrada o una salida | apuntar | F05 | `cash_register.movement.add` |
| Registra un arqueo | contar | F06 | `cash_register.count.add` |
| Imprime el informe X o Z de una sesión en la impresora de recibos | ver sesiones | F16 | `cash_register.session.print` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Ajustes guardados | Guardar los ajustes (también el primer guardado sin cambios) | Qué campos cambiaron (ninguno en ese primer guardado) | `cash_register.settings.updated` |
| Cajón nuevo | Dar de alta un cajón | Cuál | `cash_register.register.created` |
| Cajón cambiado | Renombrarlo, desactivarlo o activarlo | Cuál | `cash_register.register.updated` |
| Sesión abierta | Abrir | La sesión, su número, el fondo y quién | `cash_register.session.opened` |
| Sesión cerrada | Cerrar (a mano o sola) | La sesión, su número, esperado, contado, diferencia y si se cerró sola | `cash_register.session.closed` |
| Movimiento apuntado | Apuntar una entrada o una salida | La sesión, el tipo, el importe y el medio | `cash_register.movement.added` |
| Arqueo registrado | Registrar un arqueo | La sesión, el tipo y el total | `cash_register.count.added` |

### A qué reacciona

A nada: no necesita avisos de nadie. Las líneas de Ventas las lee de Ventas, que es su requisito, en el
momento en que se miran; las pantallas se refrescan con `sale.sale.completed`, `sale.sale.voided` y
`sale.sale.refunded`.

### Lo que necesita de otras apps

- **Ventas** (requisito): los cobros, las anulaciones (la venta anulada y cuándo) y las devoluciones,
  leídos de Ventas; las cuentas abiertas para la revisión del turno.
- **Cocina** (sin requisito; solo si está encendida): las comandas en marcha para la revisión del turno
  (KITCHEN-F31), en la ventana de cierre y en el resumen del cierre del asistente.
- **Impresión** (sin requisito; solo si está encendida): lo que espera o falló en la cola, para la revisión
  del turno (PRINTING-F01), y la cola de recibos para el informe X o Z (PRINTING-F17).
- **Plataforma**: la moneda del negocio y sus decimales (`base.business.get`, la de su país), para los importes,
  el arqueo por billetes y monedas y el informe X o Z.
- **Índices de Ventas para estas lecturas** (hecho, `sale/0005_cash_register_indexes`): parciales en
  `sale_sale(voided_at)` y `sale_refund(created_at)`, para que las lecturas por ventana de tiempo de
  anulaciones y devoluciones no recorran la tabla entera.

### Contrato con Ventas (CASH_REGISTER-F04)

Caja no puede tocar Ventas, y Ventas no requiere Caja (sería un ciclo). El bloqueo de cobrar en
efectivo con la caja cerrada lo hace Ventas así (hecho; probado contra esta app con ventas reales):

1. Antes de cobrar con un medio de tipo efectivo, Ventas llama a la operación
   `cash_register.session.current` por su nombre (`live.operations.get`; CLAUDE.md «Apps»: operaciones
   de otra app por nombre, con su permiso y su app activa), con la sesión de quien cobra.
2. Si la respuesta trae `required: true` y `session: null`, rechaza el cobro con 409
   `sale.cash_register_closed` («La caja está cerrada: abre una sesión de caja para cobrar en
   efectivo.»). Solo el efectivo: tarjeta, transferencia y otros cobran siempre.
3. Si Caja está apagada en el Hub o la llamada falla, Ventas cobra igual (el bloqueo cede antes que
   parar las ventas).
4. La pantalla Vender no se sustituye: el rechazo se lee en el cobro, con un botón que lleva a **Caja**
   a abrir la sesión.

Lo que dice Ventas de esto está en su WORKBOOK (SALE-F08). Lo que se cobra en efectivo sin turno porque
Caja estaba apagada o no respondió se ve en CASH_REGISTER-F17.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Ventas | Saber si puede cobrar en efectivo (F04) | `cash_register.session.current` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver sesiones, ajustes, cajones y moneda | sí | sí | sí | sí | `cash_register.view_session` |
| Abrir sesión | sí | sí | sí | sí | `cash_register.add_session` |
| Cerrar sesión | sí | sí | sí | sí | `cash_register.close_session` |
| Ver movimientos | sí | sí | sí | sí | `cash_register.view_movement` |
| Apuntar entradas y salidas | sí | sí | sí | sí | `cash_register.add_movement` |
| Ver arqueos | sí | sí | sí | sí | `cash_register.view_count` |
| Registrar arqueos | sí | sí | sí | sí | `cash_register.add_count` |
| Ver el esperado con el arqueo ciego | sí | sí | sí | no | `cash_register.view_expected_totals` |
| Ajustes y cajones | sí | sí | no | no | `cash_register.manage_settings` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado.

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/`, `schemas.py`, `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un `tests/test_<fichero>.py`
  por fichero, más `tests/test_integration_sale.py` (ventas reales de Ventas) y
  `tests/test_concurrency.py` (sesiones reales en hilos).
- **`requires = ["sale"]`**. Quién abre, cierra o apunta se guarda como el actor del contexto (texto,
  como Ventas), no como clave ajena a Personal: Caja no requiere Personal.
- **Modelos**: `Settings` (una fila; sin ella valen los de fábrica), `Register` (cajón; nunca se
  borra), `Session` (número `S-AAMMDD-NNNN`, día de negocio, fondo, esperado, contado y diferencia
  congelados al cerrar, cerrada sola), `SessionCounter` (uno por día de negocio), `Movement` (líneas:
  entradas y salidas a mano y, al cerrar, la copia de las líneas de Ventas del turno) y `Count`
  (arqueo con su desglose). Importes en céntimos, enteros y nunca negativos: el signo sale del tipo.
- **Las líneas de Ventas se leen, no se escuchan**. Las de la sesión abierta salen de los modelos de
  Ventas en el momento de mirar: cobros (`SalePayment` de las ventas cobradas desde la apertura),
  anulaciones (`SalePayment` de las ventas anuladas desde la apertura) y devoluciones
  (`RefundPayment` de las devoluciones desde la apertura). Al cerrar, esas líneas se copian en
  `Movement` (con su clave de origen, única por tipo: un pago de venta se copia una vez como venta y
  una como anulación; un pago de devolución, una vez) y la sesión cerrada solo lee sus copias: un
  turno cerrado nunca cambia. Así no depende del relay del outbox (que el worker reparte desde el
  2026-10-21, `base/relay.py`: Caja no declara `REACTIONS`) y no pierde nada si un aviso no llega.
  Si una línea ya está copiada se mira por su origen (`sale_payment_id`,
  `refund_payment_id`, `sale_id`: los índices únicos parciales de `Movement`). Lo que no cayó en ninguna
  sesión (`queries.unassigned_window`: con la caja cerrada, lo de después del corte de una sesión
  olvidada, o las rezagadas confirmadas mientras se cerraba la anterior) sale en `session.current`,
  contado con agregados SQL (sin listar), y en `movement.list` con `unassigned`. Una sesión abierta
  pasada su corte lee y congela solo hasta el corte, y no admite escrituras (409
  `cash_register.session_auto_close_due`).
- **Esperado** = fondo + efectivo de ventas y entradas − efectivo de salidas, devoluciones y
  anulaciones. Solo el tipo `cash` del medio de pago cuenta, nunca su nombre traducido. Al cerrar se
  congela en `expected_balance` con `closing_balance` y `difference`; las lecturas de una sesión
  cerrada enseñan esas cifras y no recalculan.
- **Arqueo ciego**: con el ajuste encendido, a quien no tiene `cash_register.view_expected_totals` una
  sesión abierta no le enseña su esperado en ninguna lectura (lista, sesión abierta, detalle), ni
  ningún total que lo sume (ventas, devoluciones, entradas, salidas, invitaciones: vacíos), y su lista
  de movimientos solo trae los apuntados a mano. La regla del saldo negativo usa el esperado real.
- **Numeración**: `SessionCounter` por día de negocio (zona horaria del Hub) con `UPDATE … RETURNING`
  en la transacción de la apertura: una apertura rechazada no gasta número. Nunca secuencias.
- **Concurrencia**: una sola sesión abierta por negocio, con un índice único parcial
  (`status = 'open'`): dos aperturas a la vez abren una y la otra recibe 409
  `cash_register.session_already_open`. Cerrar, apuntar y contar bloquean la fila de la sesión
  (`select_for_update`): dos cierres a la vez cierran uno y el otro recibe 409
  `cash_register.session_not_open`; un movimiento no entra en una sesión que se está cerrando.
- **Cierre automático**: `cash_register.session.auto_close` cierra, si el ajuste está encendido, cada
  sesión abierta antes del último corte (hora del ajuste en la zona del negocio), con `closed_at` = el
  corte, sin recuento, `auto_closed` y sin persona; copia solo las líneas de antes del corte. Lo
  declara `apps.py` como tarea programada (`*/5 * * * *`, `collapse`), que corre el worker
  (`base/scheduler.py`, 2026-10-15), y
  `session.open` lo aplica antes de abrir.
- **Monedas**: la del negocio es la de su país, que da `base.business.get` desde el registro de este hub (APP-BASE-6),
  y en el hub propio de ERPlora (sin registro en la fase 1, `create_platform_hub`, con todas las apps activas), la del
  país de su emisor (`PLATFORM_ISSUER_COUNTRY`). En el servidor, `business_currency` de Ventas (`apps.sale.queries`,
  la misma con la que nace cada venta; leída como la plataforma: una API key solo tiene el permiso de su operación);
  en pantalla, `useBusinessMoney()` de `base`. Los decimales, de `babel` (los del servidor, nunca los de Intl: Intl le
  da 0 al forinto y Babel 2). Cada venta guarda su moneda al nacer (`Sale.currency`, hub#286). Caja copia el `amount`
  de cada cobro, anulación y devolución sin leer `Sale.currency`, y lo suma y lo pinta en la del negocio, que es la de
  cada venta: el país, y con él la moneda, no cambia desde que el negocio puede vender (`hubs.country_locked` del
  SaaS). Solo una venta de antes de hub#286 en un negocio sin euro guarda `EUR` y
  sale con el símbolo del negocio. Los billetes y monedas de 18 monedas viven en `queries.DENOMINATIONS` (las mismas
  del producto actual).
  El total de un arqueo lo suma el servidor; un billete o moneda de otra moneda es 422.
- **Zona horaria (fase 1)**: `Europe/Madrid` (`TIME_ZONE` del Hub) para todos los negocios: día de
  negocio, número de sesión y corte del cierre automático. Cuando el Hub guarde la zona de cada negocio,
  saldrá de ahí.
- **Inicio** (ronda PLAN-HUB 2026-10-21; FIX-CASH_REGISTER-SETUP-HOOKS): `setup` y `widgets` de `apps.py`, los
  del `module.json` viejo (sin `bell`). El paso `cash_register.drawer` lee `updated_at` de
  `cash_register.settings.get` (orden 90, no `required`, permiso `cash_register.manage_settings`, refresco por
  `cash_register.settings.updated`): el viejo pedía `id`, la fila que solo existía al guardar; aquí los de
  fábrica valen sin fila, así que lo que dice «el negocio ya decidió» es haberlos guardado una vez (Square,
  Shopify POS, Toast, Lightspeed, Odoo, Loyverse: la caja se configura encendiéndola y guardando; Business
  Central da por hecha una guía al ejecutarla). Por eso el primer guardado avisa aunque no cambie nada y la
  tarjeta deja «Guardar» encendido mientras `updated_at` está vacío. Los dos paneles leen
  `cash_register.session.list` con `events.SESSION_EVENTS`, las mismas que la re-ejecutan en `live.py`: el
  esperado (`kpi`, `status=open`, `limit` 1, `expected_balance`; `session.current` lo anida y un `kpi` lee
  campos de la primera fila) con `cash_register.view_expected_totals`, y los descuadres (`bar-list`, los
  mismos parámetros que la tarjeta de **Caja**, `number` y `difference`) con `cash_register.view_session` (el
  «ver informes» del viejo ya no existe, cambio 14). Ningún panel fija moneda, escala ni idioma
  (gh:cash_register#121, gh:hub#2387, gh:outfitkit#243) ni categoría (gh:cash_register#123); el `kpi` no repite
  su nombre en `options.label` (gh:hub#1105), así que «Efectivo esperado en caja» del viejo no se pinta.
- **Administrador de Django con CRUD completo** (ronda 12, PLAN §17), solo en `hubs.erplora.com`; ids
  y fechas de solo lectura. Lo que guarda no pasa por las operaciones ni deja aviso.
- **Asistente**: cada operación declara `ai` (descripción; en las escrituras, `risk`: `high` en abrir,
  cerrar, cerrar sola, apuntar y contar) y cada campo de `schemas.py` su `description`. La tarjeta de
  confirmación nombra cada dato por el `title` de su esquema (`gettext_noop`, con su `es` en el catálogo:
  «Cajón» para `register_name`, «Efectivo contado», «Notas de cierre») o, si no lo tiene, por el
  `verbose_name` de su campo en el modelo; un dato sin ninguno sale con el nombre técnico y lo para
  `tests/test_integration_assistant.py` (`test_i18n.py` exige el `es` de cada `title`).
- **El cierre por el asistente** (F09; PLAN §30, la primera de las cinco acciones de IA pulidas): la
  descripción de `session.close` le pide leer antes `session.closing_summary` con el mismo contado,
  decir su resumen y cerrar nombrando la sesión por el número que dio (así nunca cierra otra que se
  abriera entre medias). Esa consulta valida como el cierre (sesión abierta y sin pasar su corte;
  recuento obligatorio: 409 `cash_register.closing_balance_required`), aplica el arqueo ciego (esperado y
  diferencia vacíos) y lee la revisión del turno de Ventas (`sale.order.list`), Cocina
  (`kitchen.ticket.board`) e Impresión (`printing.job.summary`) por su nombre, con el permiso de quien
  pregunta: una app que no está encendida no tiene nada pendiente y una lectura rechazada deja la revisión
  incompleta. Su nombre no lleva el verbo de una acción (`close_…`): la plataforma nombra la acción de cada
  recibo por su verbo y una lectura no puede decir «Hecho: Cerrar». La confirmación es la tarjeta de riesgo
  alto de la plataforma (escribir la palabra, que el servidor vuelve a comprobar).

### Cambios frente al producto actual

1. **Las líneas de Ventas se leen de Ventas** en vez de escribirse al oír sus avisos: no hace falta el
   relay ni reintentos, y una anulación o devolución sin caja abierta ya no se pierde ni se rechaza
   (sale en F17).
2. **Una venta cobrada sin turno no se pierde en silencio**: Caja la enseña (F17). El bloqueo del cobro
   en efectivo con la caja cerrada (F04) lo aplica Ventas, preguntando a Caja.
3. **Los ajustes de fábrica valen desde el principio**; antes no se aplicaba ninguna regla hasta el
   primer guardado. «URL del POS protegido» desaparece: la ruta del TPV es fija y el bloqueo es de
   Ventas.
4. **Dos aperturas o dos cierres a la vez**: solo uno hace algo y el otro recibe su aviso (antes el
   segundo contestaba bien sin hacer nada).
5. **El arqueo exige una sesión abierta** (antes solo lo impedía la pantalla).
6. **El esperado se ve donde se puede, y el ciego es ciego**: el responsable lo ve también en la tabla
   y en la ventana de cierre con el arqueo ciego (antes solo en el detalle); el empleado ya no ve las
   líneas de venta ni los totales con los que sumarlo (antes sí).
7. **El detalle enseña quién abrió y cerró, el cajón y las notas**, y se imprime (informe X y Z).
8. **Cajones en pantalla**, con nombre obligatorio y sin repetir (antes solo el asistente, sin
   comprobar nada).
9. **Movimientos a mano: solo entrada o salida**. Las líneas de venta, devolución y anulación son
   siempre las de Ventas.
10. **Una anulación de otro turno sale por cada forma de pago**, también la de tarjeta (sin tocar el
    esperado), con el tipo «Anulación».
11. **La revisión del turno mira también las cuentas abiertas de Ventas** (Toast), además de las comandas
    sin servir de Cocina y la cola de Impresión; las impresiones que fallaron cuentan como pendientes.
12. **El número de sesión toma el día de negocio** (hora del negocio), no el de UTC.
13. **El estado «Suspendida» desaparece**: nada llevaba a él.
14. **Permiso «ver informes» desaparece**: ninguna operación lo pedía (era el del panel «Descuadres
    recientes», que lee las sesiones: en el Inicio lo tiene quien ve las sesiones).
15. **El cierre automático cierra a la hora del corte**, con las líneas de antes del corte; las de
    después van a F17 o a la sesión siguiente.
16. **Abrir, apuntar, contar y cerrar son ventanas (diálogos)** sobre la tabla, como en el resto de
    apps de la plataforma (antes, paneles encima de la tabla); el detalle es una página con su flecha de
    volver. «Movimiento», «Arqueo» y «Cerrar» solo salen en la fila de la sesión abierta (antes salían en
    todas y una cerrada respondía «La sesión S-… no está abierta»).
17. **Quién abrió o cerró** se guarda como lo lee una persona (su nombre o su correo), no como el
    identificador interno del usuario.
18. **Las cifras de la caja están en Caja y en el Inicio**: la sesión actual y los descuadres recientes salen
    encima de la tabla de sesiones y, como en el producto actual, en los paneles del Inicio.
19. **Cerrar la caja pidiéndoselo al asistente enseña antes el resumen** (sesión, contado y, a quien puede
    verlos, esperado y diferencia, y lo pendiente) y pide escribir la palabra; antes el asistente cerraba
    la sesión abierta con el contado, sin resumen previo.
20. **«Tu caja» se da por hecho al guardar los ajustes una vez**, también sin cambiar nada: los de fábrica
    valen desde el principio (cambio 3), así que el paso pide la decisión del negocio, no una fila.

### Lo que NO hace, a propósito

- No cobra ni factura: Ventas, Facturación y VeriFactu.
- No abre el cajón físico: Impresión. El informe X o Z lo imprime Impresión, en su cola de recibos (sin
  Impresión o sin impresora de recibos, el diálogo del navegador).
- No lleva varios cajones abiertos a la vez: una sesión por negocio, aunque haya varios cajones dados de
  alta (el índice único parcial de `Session`). Una sesión por cajón, para dos cajas cobrando a la vez, queda
  fuera de esta versión: el negocio del norte (una peluquería o un restaurante con una sola caja) no la
  necesita, y cambiarla toca a Ventas (F04 pregunta por «la» sesión abierta).
- No reabre turnos ni edita o borra movimientos o arqueos: se corrige con otro movimiento.
- No gestiona propinas, banco ni caja fuerte más allá de una salida de efectivo.
- No pide aprobación ni nota obligatoria cuando la diferencia pasa de un umbral. Toast y Lightspeed lo
  ofrecen como opción, no de fábrica; si llega, será una política del dueño (ADR-0476: el número y la
  consecuencia los pone él) sobre el cierre de F09.
- No abre el cajón sin venta («no-sale»). El cajón físico lo abre Impresión (PRINTING-F13, al cobrar);
  abrirlo sin venta, con su permiso y su rastro en la sesión, queda fuera de esta versión.

Las tres salidas de esta lista que el mercado sí ofrece (una sesión por cajón, el umbral del descuadre y
el «no-sale») se decidieron al cerrar la app (2026-10-21) y van a «Fuera por ahora» (`## 6` de
`MIGRATION.md`).
