# Workbook — Carrito y pago (app)
Prefijo: CART_CHECKOUT
Alcance MVP: fuera del MVP (en la tienda; no viene en ninguna plantilla)
Estado de la app: hecha (servidor, pantallas y pruebas de punta a punta en tres tamaños)

> Manual de usuario y especificación de la app `cart_checkout`. Se escribe **antes** que el código: no
> se programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Carrito y pago del producto actual
> (`modules-workspace/modules/cart_checkout`, `origin/main` `571c2cc`, v1.0.26), de sus `docs/`, de su
> manejador y de sus tests. Los números de flujo se conservan. Lo que cambia frente al producto actual
> lo dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Carrito y pago es una **libreta interna de carritos y pedidos**. Guarda **carritos** — de una persona
(su email y su nombre) o de una visita anónima, que se distingue por un **código de sesión** — con sus
líneas (producto, cantidad y precio), y los convierte en **pedidos** con número, direcciones, método de
envío y de pago y un estado: **Iniciado**, **Pagado** o **Fallido**, y **Completado**.

Lo más importante: **no es el TPV y nada de lo que hace es fiscal**. Un pedido pagado y completado aquí
**no** genera venta, ni factura, ni registro VeriFactu, ni movimiento de caja, ni movimiento de stock, y
nada de lo cobrado aquí llega a la AEAT. «Pagado» es un estado que **una persona marca** después de
cobrar por otra vía: la app no cobra, no habla con ninguna pasarela y no pide importe ni justificante.
Para cobrar en el mostrador está **Ventas**.

No tiene tienda ni página pública: solo la usa personal con sesión en el Hub.

Quién la usa:

- El **empleado**: solo mira los carritos y los pedidos.
- El **responsable**, el **administrador** y el **propietario**: además crean, abandonan y borran
  carritos, y marcan los pedidos como pagados, completados o fallidos.
- El **asistente**: hace lo mismo que la persona que le habla y, además, lo que la pantalla no ofrece:
  añadir y cambiar líneas, vaciar un carrito, iniciar un pedido y caducar los carritos vencidos.

## Referencia adoptada

El modelo de carrito y pedido de una tienda en línea (Shopify Checkout, WooCommerce, Odoo eCommerce):
carrito con código de sesión, pedido con número correlativo y estados iniciado → pagado o fallido →
completado. Se adopta **solo el modelo de estados**: la tienda pública, la pasarela de pago, los
impuestos, el envío y el stock de esas referencias **no existen aquí**. Sin investigación nueva: es el
mismo alcance que el producto actual.

## Antes de empezar

1. Carrito y pago no viene encendida con ningún tipo de negocio: se enciende desde la tienda de apps.
   No enciende ninguna otra app ni la necesita: se puede encender y apagar sola.
2. No tiene ajustes. La moneda de un carrito nuevo es la del negocio (euros mientras el Hub no guarde
   otra), salvo que quien lo crea por el asistente o la API diga otra.
3. Un carrito puede llevar fecha de caducidad; sin ella no caduca nunca.

## Pantallas

Carrito y pago se abre desde el menú y tiene dos pestañas, abajo: **Carritos** y **Pedidos**. La barra
de arriba dice «Carrito y pago» y la pestaña en la que estás. Lo que una persona no puede hacer no
aparece, y la app lo rechaza aunque lo intente por la API o por el asistente.

### Carritos

Una tabla con las columnas **Sesión**, **Email**, **Estado** (Activo, Abandonado, Convertido,
Expirado), **Ítems** y **Total**. Buscador «Buscar sesión o email…» (busca en el código de sesión, el
email y el nombre), filtros por columna — sesión y email por un trozo del texto, el estado por lista,
los ítems y el total «desde / hasta» —, orden por columna, vista de lista o de tarjetas y 50 filas por
página. Va ordenada por fecha de alta, el más reciente arriba. El total sale en la moneda del carrito;
el filtro de Total se escribe en la moneda del negocio (en euros: «12» son 12,00 €) y compara el importe
tal cual, sin convertir monedas. Se puede pegar con sus puntos de miles («1.250,50») o con el símbolo
(«12,50 €»); un importe que no se entiende («1.250», que puede ser 1.250 € o 1,25 €) se avisa debajo de
su caja, «Escribe un importe, como 12,50», y no filtra.

El botón **Nuevo carrito** abre el formulario «Nuevo carrito»: **Sesión** (obligatoria; «Guardar» no se
activa sin ella), **Email** y **Nombre**. Cada fila ofrece **Abandonar** (solo un carrito activo) y
**Borrar** (pide confirmación). **No hay pantalla de las líneas** de un carrito ni para añadirlas: eso
lo hace el asistente o la API.

### Pedidos

Una tabla con **Pedido** (su número, siempre entero), **Email**, **Estado** (Iniciado, Pagado, Fallido, Completado),
**Pago** (el método de pago, texto) y **Total**, en la moneda del pedido. Buscador «Buscar pedido o
email…», filtros por columna, orden por columna, vista de lista o de tarjetas y 50 filas por página, el
más reciente arriba. Un pedido fallido enseña su motivo entero debajo del estado.

Cada fila ofrece la acción que le toca: **Marcar pagado** (Iniciado), **Completar** (Pagado) y
**Fallar** (Iniciado o Pagado), que abre un formulario que pide el **motivo**. Mientras una acción de
fila trabaja, su botón gira y un segundo toque no hace nada. No hay botón para crear un pedido: nacen
del flujo CART_CHECKOUT-F08.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin carritos.» o «Sin pedidos.»; con búsqueda o filtro, «Sin resultados». |
| Error | El aviso de la tabla con «Reintentar». Un rechazo de un formulario sale dentro del formulario, cada motivo debajo de su campo, sin perder lo tecleado; el de una acción de fila, encima de la tabla. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

Importes con el formato del idioma de quien mira y en la moneda de cada fila; cantidades sin ceros de
adorno («2», «0,5»).

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| CART_CHECKOUT-F01 | Crear un carrito | hecho |
| CART_CHECKOUT-F02 | Añadir una línea a un carrito | hecho |
| CART_CHECKOUT-F03 | Cambiar la cantidad de una línea o quitarla | hecho |
| CART_CHECKOUT-F04 | Vaciar un carrito | hecho |
| CART_CHECKOUT-F05 | Abandonar un carrito | hecho |
| CART_CHECKOUT-F06 | Borrar un carrito | hecho |
| CART_CHECKOUT-F07 | Caducar los carritos vencidos | hecho |
| CART_CHECKOUT-F08 | Iniciar el pedido desde un carrito | hecho |
| CART_CHECKOUT-F09 | Marcar un pedido como pagado | hecho |
| CART_CHECKOUT-F10 | Registrar que el pago falló | hecho |
| CART_CHECKOUT-F11 | Completar un pedido | hecho |
| CART_CHECKOUT-F12 | Consultar carritos, líneas y pedidos | hecho |
| CART_CHECKOUT-F13 | Avisar a otras apps de lo que ocurre | hecho |
| CART_CHECKOUT-F14 | Borrar los datos personales de un cliente | hecho |

### CART_CHECKOUT-F01 Crear un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-carts-create old:cart_checkout/WORKFLOW.md#cart_checkout-f01 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Carritos
Pasos:
1. En **Carritos** pulsa **Nuevo carrito**.
2. Escribe la **Sesión** (el código que distingue la visita, obligatorio) y, si quieres, **Email** y
   **Nombre**.
3. Pulsa **Guardar**: el formulario se cierra y el carrito sale en la lista como **Activo**, sin líneas
   y con total cero.
Entra: código de sesión (hasta 128 caracteres), email y nombre, de la persona; el asistente o la API
pueden dar además la moneda (código ISO 4217) y la fecha de caducidad.
Sale: un carrito activo en la moneda dicha o, si no se dice, la del negocio
(`cart_checkout.cart.created`).
Si falla: dentro del formulario, debajo de su campo: una sesión vacía; una sesión que ya usa otro
carrito no borrado («Ya hay un carrito con esa sesión.»); un email que no es un email; una moneda que no
existe; una caducidad que ya pasó. Lo tecleado se conserva. Sin permiso, se rechaza.
Implicados: ninguno

### CART_CHECKOUT-F02 Añadir una línea a un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-items-add-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f02 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente añadir un producto a un carrito, diciendo el carrito (su sesión, o el email o el
   nombre del cliente), la referencia y el nombre del producto, la cantidad y el precio por unidad.
2. Confirma la tarjeta del asistente.
3. La línea queda guardada y los totales del carrito (ítems e importe) se recalculan.
Entra: el carrito; referencia y nombre del producto (texto libre: no se comprueban contra el
catálogo), SKU y atributos de variante (talla, color…) opcionales, cantidad mayor que cero y como mucho
1 000 000 (hasta tres decimales: «0,5») y precio por unidad en céntimos, que **dice quien llama**.
Sale: la línea con su total (cantidad × precio, redondeado al céntimo, la mitad hacia arriba), los
totales del carrito y su última actividad (`cart_checkout.item.added`).
Si falla: carrito que no existe («Ese carrito no existe en este negocio.»); varios carritos para lo
dicho (los nombra y pide cuál); carrito que no está activo, también uno vencido («Este carrito ya no
admite cambios: está Abandonado.»); referencia o nombre vacíos, cantidad cero, negativa o de más de
1 000 000, precio negativo: cada uno en su campo; un total de la línea, o del carrito con ella, por encima
de lo que cabe en un carrito (99 999 999 999,99 €), debajo de la cantidad. No se guarda nada.
Implicados: ninguno

### CART_CHECKOUT-F03 Cambiar la cantidad de una línea o quitarla
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-items-remove fi:modules/cart_checkout#command-cart_checkout-items-update-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f03 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente cambiar la cantidad de una línea, o quitarla.
2. Confirma la tarjeta.
3. Con cantidad mayor que cero la línea cambia y su total se recalcula con el precio guardado en la
   línea; con cantidad cero la línea se quita. También existe la orden «quitar línea», que solo quita.
4. Los totales del carrito se recalculan en la misma operación.
Entra: la línea (su id) y la cantidad; el precio lo lee el Hub de la línea, nunca de quien llama.
Sale: la línea cambiada o quitada, los totales del carrito y su última actividad
(`cart_checkout.item.updated`, con `removed: true` cuando la cantidad es cero;
`cart_checkout.item.removed` sale de «quitar línea»).
Si falla: línea que no existe; carrito que ya no está activo; cantidad negativa o de más de 1 000 000; un
total por encima de lo que cabe en un carrito, debajo de la cantidad. No cambia nada.
Implicados: ninguno

### CART_CHECKOUT-F04 Vaciar un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-carts-clear-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f04 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente vaciar un carrito.
2. Confirma la tarjeta.
3. Se quitan todas sus líneas y los totales vuelven a cero; el carrito sigue **Activo**.
Entra: el carrito.
Sale: el carrito sin líneas, totales a cero (`cart_checkout.cart.cleared`). Vaciar uno que ya estaba
vacío no cambia nada ni avisa.
Si falla: carrito que no existe o que no está activo. No cambia nada.
Implicados: ninguno

### CART_CHECKOUT-F05 Abandonar un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-carts-mark_abandoned old:cart_checkout/WORKFLOW.md#cart_checkout-f05 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Carritos
Pasos:
1. En **Carritos**, en la fila de un carrito activo, pulsa **Abandonar**.
2. El carrito pasa a **Abandonado** y conserva sus líneas. El asistente puede dar un motivo, que queda
   en el carrito.
Entra: el carrito y un motivo opcional (hasta 500 caracteres).
Sale: estado Abandonado (`cart_checkout.cart.abandoned`).
Si falla: solo se abandona un carrito activo; en otro estado se rechaza diciendo en cuál está, encima de
la tabla, y no cambia nada.
Implicados: ninguno

### CART_CHECKOUT-F06 Borrar un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-carts-delete old:cart_checkout/WORKFLOW.md#cart_checkout-f06 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Carritos
Pasos:
1. En **Carritos**, en la fila, pulsa **Borrar**.
2. Confirma «¿Borrar el carrito …?» con **Borrar**; **Cancelar** lo deja como estaba.
3. El carrito desaparece de la lista. El asistente pide confirmación reforzada (acción peligrosa).
Entra: el carrito.
Sale: el carrito borrado en cualquier estado, también Convertido (`cart_checkout.cart.deleted`). Sus
pedidos siguen existiendo y su sesión queda libre para otro carrito.
Si falla: un carrito que no existe (o ya borrado) se rechaza; no cambia nada.
Implicados: ninguno

### CART_CHECKOUT-F07 Caducar los carritos vencidos
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-carts-cleanup_expired-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f07 -->
Estado: hecho
Actor: sistema (tarea programada), administrador, asistente
Pantalla: Carritos (el estado)
Pasos:
1. Un carrito activo cuya fecha de caducidad ya pasó **se lee como Expirado** en la lista, en su
   detalle y en el filtro por estado, y ya no admite cambios ni pedidos.
2. Cada quince minutos, la tarea de la app lo deja guardado como Expirado. También se puede pedir al
   asistente o a la API «caducar los carritos vencidos».
Entra: nada; la hora la pone el Hub.
Sale: los carritos vencidos pasan a Expirado y la orden dice cuántos
(`cart_checkout.cart.expired`, con el número; sin ninguno no avisa).
Si falla: sin carritos vencidos contesta «0» y no avisa. Un carrito sin caducidad no caduca nunca. Con la
lista ya abierta, un carrito que vence en ese momento sigue pintado «Activo» hasta que la lista se vuelve a
leer: con el siguiente cambio, al volver a abrirla o con la relectura de seguridad del Hub (cada 5
minutos). Cuando la orden la da alguien del negocio, por el asistente o la API, la lista abierta se pone
al día en ese momento.
Implicados: ninguno

### CART_CHECKOUT-F08 Iniciar el pedido desde un carrito
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-checkout-initiate-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f08 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente iniciar el pedido de un carrito y, si quieres, el email del cliente, las
   direcciones de envío y de facturación, el método de envío, el método de pago y unas notas.
2. Confirma la tarjeta.
3. Aparece en **Pedidos** un pedido **Iniciado** con número `OS-AAAAMMDD-NNNN` (correlativo por día
   del negocio, sin huecos) y el total del carrito copiado en ese momento, en su moneda.
Entra: el carrito; el email del cliente (sin él, el del carrito); direcciones (si falta la de
facturación se copia la de envío); métodos de envío y de pago (texto) y notas.
Sale: un pedido Iniciado con el total del carrito en ese instante (`cart_checkout.checkout.initiated`).
El carrito sigue activo, así que se pueden cambiar sus líneas e iniciar otro pedido, con el número
siguiente; el total del pedido ya no cambia.
Si falla: carrito que no existe, que no está activo (también vencido) o sin líneas; email que falta o
que no es un email. No se crea pedido, **no se gasta número** y no avisa.
Implicados: ninguno

### CART_CHECKOUT-F09 Marcar un pedido como pagado
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-orders-mark_paid old:cart_checkout/WORKFLOW.md#cart_checkout-f09 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pedidos
Pasos:
1. Cobra al cliente fuera de esta app.
2. En **Pedidos**, en la fila de un pedido Iniciado, pulsa **Marcar pagado**.
3. El pedido pasa a **Pagado** con la hora del pago.
Entra: el pedido (por su número o su id).
Sale: estado Pagado y hora del pago (`cart_checkout.order.paid`). No se cobra ni se pide importe, medio
ni justificante, y no se crea venta, factura, registro fiscal, movimiento de caja ni de stock. El
asistente pide confirmación reforzada.
Si falla: solo se marca un pedido Iniciado; en otro estado se rechaza diciendo en cuál está. El
empleado no puede.
Implicados: ninguno

### CART_CHECKOUT-F10 Registrar que el pago falló
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-orders-fail old:cart_checkout/WORKFLOW.md#cart_checkout-f10 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pedidos
Pasos:
1. En **Pedidos**, en la fila de un pedido Iniciado o Pagado, pulsa **Fallar**.
2. Escribe el **motivo** (obligatorio; «Fallar pedido» no se activa sin él) y pulsa **Fallar pedido**;
   **Mantener** lo deja como estaba.
3. El pedido pasa a **Fallido** y enseña su motivo entero debajo del estado.
Entra: el pedido y el motivo (hasta 500 caracteres).
Sale: estado Fallido, el motivo y la hora (`cart_checkout.order.failed`). Un pedido ya Pagado también
puede fallar, como hoy: **no deja rastro de devolución** (no hay devoluciones en esta app). El carrito
sigue como estaba. El asistente pide confirmación reforzada.
Si falla: un pedido Completado o ya Fallido se rechaza; un motivo vacío, debajo de su campo, sin perder
lo escrito.
Implicados: ninguno

### CART_CHECKOUT-F11 Completar un pedido
<!-- origen: fi:modules/cart_checkout#command-cart_checkout-orders-complete-handler-wasm old:cart_checkout/WORKFLOW.md#cart_checkout-f11 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pedidos
Pasos:
1. En **Pedidos**, en la fila de un pedido Pagado, pulsa **Completar**.
2. El pedido pasa a **Completado** y su carrito, a **Convertido**, en la misma operación.
Entra: el pedido.
Sale: pedido Completado con su hora y carrito Convertido (`cart_checkout.order.completed`). Nada
fiscal ni de stock. Si el carrito ya estaba borrado, el pedido se completa igual.
Si falla: solo se completa un pedido Pagado; en otro estado se rechaza diciendo en cuál está.
Implicados: ninguno

### CART_CHECKOUT-F12 Consultar carritos, líneas y pedidos
<!-- origen: fi:modules/cart_checkout#navigation fi:modules/cart_checkout#query-cart_checkout-carts-get fi:modules/cart_checkout#query-cart_checkout-carts-list fi:modules/cart_checkout#query-cart_checkout-items-list fi:modules/cart_checkout#query-cart_checkout-orders-get fi:modules/cart_checkout#query-cart_checkout-orders-list old:cart_checkout/WORKFLOW.md#cart_checkout-f12 -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario, asistente
Pantalla: Carritos, Pedidos
Pasos:
1. Abre **Carritos** o **Pedidos**.
2. Busca por sesión, email o nombre (carritos) o por número de pedido o email (pedidos), filtra por
   columna (el Total, como se escribe o se pega: «12», «12,50», «1.250,50») y ordena.
3. Las líneas de un carrito y el detalle de un pedido (direcciones, métodos, fechas, notas) se leen con
   el asistente o la API: un carrito por su sesión o por el email o el nombre de su cliente, un pedido
   por su número.
Entra: permiso «ver carritos» (el empleado lo tiene).
Sale: listas de 50 filas (hasta 100 por petición). Cantidades con sus decimales, importes en céntimos
con la moneda de la fila.
Si falla: error de carga con «Reintentar»; sin permiso, «No tienes permiso»; un importe de Total que no
se entiende, «Escribe un importe, como 12,50» debajo de su caja, sin filtrar.
Implicados: ninguno

### CART_CHECKOUT-F13 Avisar a otras apps de lo que ocurre
<!-- origen: fi:modules/cart_checkout#events-emitidos-catalogo old:cart_checkout/WORKFLOW.md#cart_checkout-f13 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada cambio de los flujos anteriores deja un aviso en el outbox del Hub en su misma transacción.
2. Las dos pantallas se actualizan solas con lo que cambió.
Entra: el cambio que lo provoca.
Sale: trece avisos: los doce del producto actual (`cart.created`, `cart.abandoned`, `cart.deleted`,
`cart.cleared`, `cart.expired`, `item.added`, `item.updated`, `item.removed`, `checkout.initiated`,
`order.paid`, `order.failed`, `order.completed`) y `customer.erased`, con el prefijo `cart_checkout.`.
Ninguna app del Hub los escucha.
Si falla: un cambio rechazado no deja ni el cambio ni el aviso.
Implicados: ninguno (ninguna app del Hub escucha estos avisos)

### CART_CHECKOUT-F14 Borrar los datos personales de un cliente
<!-- origen: nuevo (el borrado de datos personales de Shopify y WooCommerce, «erase personal data»: el derecho de supresión del RGPD) -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente; el personal de la plataforma desde el admin
Pantalla: asistente; admin del Hub (acción «Borrar los datos personales de sus clientes»)
Pasos:
1. Un cliente pide que se borren sus datos (derecho de supresión, RGPD).
2. Pide al asistente borrar los datos del cliente con su email exacto, o el personal de la plataforma
   marca sus carritos o pedidos en el admin y lanza la acción.
3. Confirma la tarjeta (acción peligrosa: no se deshace).
Entra: el email exacto del cliente (sin distinguir mayúsculas).
Sale: todos los carritos con ese email, también los borrados, se quedan sin email, nombre, notas ni
motivo de abandono; todos los pedidos con ese email o de esos carritos, sin email, direcciones, notas ni
motivo de fallo. Número, importes, estados y fechas se quedan. Dice cuántos carritos y pedidos cambió
(`cart_checkout.customer.erased`, con los dos números y nunca el email; si no había nada, no avisa).
Si falla: un email vacío o que no es un email, en su campo. Sin permiso «gestionar carritos», se rechaza.
En el admin, sin hub elegido no hace nada y lo dice.
Implicados: ninguno

## Carrito y pago: lo que entra y lo que sale

### Lo que ofrece: consultas (leen, no cambian nada)

| Operación | Qué da |
|---|---|
| `cart_checkout.cart.list` | Carritos, con búsqueda, filtros, orden y páginas de hasta 100. |
| `cart_checkout.cart.get` | Un carrito con sus líneas, por id, sesión o cliente (email o nombre). |
| `cart_checkout.item.list` | Las líneas de un carrito, con búsqueda, filtros y páginas. |
| `cart_checkout.item.get` | Una línea por su id. |
| `cart_checkout.order.list` | Pedidos, con búsqueda, filtros, orden y páginas de hasta 100. |
| `cart_checkout.order.get` | Un pedido con todo (direcciones, métodos, fechas, notas), por id o número. |

### Lo que ofrece: acciones (cambian datos)

| Operación | Qué hace | Permiso |
|---|---|---|
| `cart_checkout.cart.create` | Crea un carrito | gestionar carritos |
| `cart_checkout.cart.mark_abandoned` | Abandona un carrito activo | gestionar carritos |
| `cart_checkout.cart.delete` | Borra un carrito (peligrosa) | gestionar carritos |
| `cart_checkout.cart.clear` | Vacía un carrito activo | gestionar carritos |
| `cart_checkout.cart.cleanup_expired` | Caduca los carritos vencidos (también la tarea) | gestionar carritos |
| `cart_checkout.item.add` | Añade una línea | gestionar carritos |
| `cart_checkout.item.update` | Cambia la cantidad (0 la quita) | gestionar carritos |
| `cart_checkout.item.remove` | Quita una línea | gestionar carritos |
| `cart_checkout.checkout.initiate` | Inicia un pedido desde un carrito | cobrar |
| `cart_checkout.order.mark_paid` | Marca un pedido pagado (peligrosa) | cobrar |
| `cart_checkout.order.fail` | Marca un pedido fallido con su motivo (peligrosa) | cobrar |
| `cart_checkout.order.complete` | Completa un pedido pagado y convierte su carrito | cobrar |
| `cart_checkout.customer.erase` | Borra los datos personales de un cliente por su email (peligrosa) | gestionar carritos |

### Lo que avisa

Los trece avisos de CART_CHECKOUT-F13. Solo salen cuando el cambio ocurrió.

### A qué reacciona y lo que necesita de otras apps

Nada. No lee ni escribe en otras apps: producto, referencia, SKU y precio son texto y números libres,
sin vínculo con Inventario, y el cliente es un email y un nombre sin vínculo con Clientes.

### Quién puede qué

| Permiso | Qué deja hacer | Quién lo tiene |
|---|---|---|
| `cart_checkout.view_cart` | Ver carritos, líneas y pedidos | todos, también el empleado |
| `cart_checkout.manage_cart` | Crear, abandonar, borrar, vaciar y caducar carritos; añadir, cambiar y quitar líneas; borrar los datos personales de un cliente | responsable, administrador, propietario |
| `cart_checkout.checkout` | Iniciar pedidos y marcarlos pagados, fallidos o completados | responsable, administrador, propietario |

## Para quien lo mantiene

### Decisión: una libreta interna, fuera de las plantillas (2026-10-15)

- El catálogo actual la tiene fuera del MVP y su `WORKFLOW.md` la describe como libreta interna sin
  tienda. Se porta **igual, sin ampliar**: `verticals = []` (ninguna plantilla la trae al darse de alta)
  y `listed = True` (en la tienda, desde donde la enciende quien la quiera), como `payment`.
- `requires = []`: el producto actual guarda producto, SKU y precio como **texto libre** (`product_ref`,
  `product_name`, `sku`, sin `product_id`) y al cliente como **email y nombre** (sin `customer_id`). Se
  mantiene: no hay FK hacia `inventory` ni hacia `customer`, y por eso tampoco reacciona a
  `customer.customer.merged/erased`. Enlazar el carrito con una ficha o las líneas con el catálogo es
  ampliar el alcance: queda fuera.
- La descripción del asistente dice expresamente que **no es el TPV** y que no cobra: el producto
  actual se describía como «mark payments» y podía elegirse ante «registra el cobro» en vez de Ventas.

### Cómo está hecho

- Modelos (`models.py`, PK UUIDv7): `Cart`, `CartItem`, `Order` (la «sesión de checkout» del producto
  actual) y `OrderCounter` (último número por día). Importes en céntimos (`BigIntegerField`);
  cantidades `Decimal` con tres decimales, como `sale` e `inventory` (el producto actual usaba enteros
  con escala 10⁶).
- **Borrar un carrito es lógico** (`deleted_at`): sus pedidos siguen apuntándole. La sesión es única
  solo entre carritos no borrados (restricción parcial de la base). Las líneas quitadas se borran de
  verdad.
- **Caducidad**: el estado efectivo se calcula al leer (activo + `expires_at` pasado = `expired`), en
  las listas, el detalle, el filtro y las guardas de las acciones. `cart_checkout.cart.cleanup_expired`
  lo guarda; la tarea `expire_overdue_carts` (cada 15 min, en UTC, `catch_up: collapse`) la declara
  `apps.py` y la corre el worker del Hub (`base.scheduler`; `tests/test_scheduled_expiry.py`). En la fase
  1 corre sobre su ámbito fijo (`WORKER_SCOPE_SLUG`): su aviso no llega a las listas abiertas en otro
  negocio, que se ponen al día con la relectura de 5 minutos.
- **Numeración sin huecos**: `OS-AAAAMMDD-NNNN` con el día del negocio (Europe/Madrid), del contador del
  día subido con `UPDATE … RETURNING` dentro de la transacción del pedido; nunca una secuencia. Todas las
  comprobaciones van antes, así que un rechazo no gasta número. Probado con hilos y sesiones reales.
- Cada acción sobre un carrito, una línea o un pedido **bloquea su fila** (`select_for_update`): dos
  personas a la vez van una detrás de otra y la segunda oye por qué.
- Totales: `line_total = cantidad × precio` redondeado al céntimo con `ROUND_HALF_UP`; los del carrito
  se recalculan con una suma en la base en la misma transacción.
- Rechazos con su código: 404 `cart_checkout.cart_not_found`, `item_not_found`, `order_not_found`;
  409 `cart_checkout.session_taken`, `cart_not_active`, `cart_empty`, `cart_ambiguous`,
  `invalid_transition`; 422 por campo.
- Referencias humanas para el asistente y la voz: un carrito por su sesión, o por el email exacto o un
  trozo del nombre de su cliente. Si encajan varios carritos de **un mismo cliente** (mismo email sin
  mayúsculas, o mismo nombre completo sin mayúsculas ni espacios de más) y solo uno está activo, es ese;
  si son de clientes distintos («ana» es un trozo de «Mariana») o hay varios activos, 409
  `cart_checkout.cart_ambiguous` con sus sesiones, aunque solo uno esté activo. Un pedido, por su número.
- Topes: una línea lleva como mucho 1 000 000 unidades (422 en el esquema) y ni su total ni el del
  carrito pasan de `MAX_AMOUNT` (99 999 999 999,99 €; 422 bajo `quantity` antes de escribir): un producto
  mayor desbordaba el `bigint` de la base (un 500).
- Asistente: toda operación declara `ai` con `description` y `risk` (`high` en marcar pagado, fallar,
  borrar y borrar los datos de un cliente) y todo campo de entrada su `description`. `expose_api=True` en
  todas.
- Datos personales (CART_CHECKOUT-F14): `cart_checkout.customer.erase` vacía email, nombre, notas y
  motivo de abandono de los carritos con ese email (también los borrados) y email, direcciones, notas y
  motivo de fallo de sus pedidos, en una transacción con las filas bloqueadas; su aviso lleva los números,
  nunca el email. El email de un pedido admite quedar vacío (migración 0002).
- El admin de Django del Hub tiene **CRUD completo** sobre los cuatro modelos (ronda 12, PLAN §17); una
  escritura del admin no pasa por las reglas ni deja aviso. Su acción «Borrar los datos personales de sus
  clientes» (carritos y pedidos) sí es la operación, sobre el hub elegido en el admin.

### Cómo son las páginas

- `frontend/pages/CartsPage.vue` y `OrdersPage.vue`, con la barra de pestañas de `frontend/tabs.ts`.
  Listas con `DataTable` de servidor (`useServerTable` + `useLiveList`, copias de las de `payment`),
  formularios en `FormModal` (`CartFormModal`, `FailOrderModal`), confirmación de borrar con
  `useConfirm`, importes y cantidades con `lib/format.ts`.
- La barra de arriba lleva el nombre de la app (`cart_checkout.title`), como el hub viejo; la pestaña la
  añade el shell.
- Los importes agrupan los millares también con cuatro cifras (`useGrouping: 'always'`: el CLDR del
  español deja «1234,56 €»; hub#1090). El filtro de Total es `{ type: 'range', amount: true }`: `toMinor`
  lee lo que se pega («1.250,50», «12,50 €»; lo ambiguo, «1.250», no se adivina) y `unreadableTotals` da
  los `filterErrors` (pm#521).
- La columna del número de pedido tiene ancho mínimo (`minmax(10.5rem, 1fr)`) y el motivo de un pedido
  fallido parte en líneas dentro de su celda: cortados, dos pedidos del día se leían iguales.
- Lo que falta de `@erplora/ui` está en `UI-REQUESTS.md` (iconos y piezas copiadas).
- e2e: `tests/e2e/cart-checkout-flows.spec.ts` (las pantallas, en 390, 834 y 1440), `-api.spec.ts` (los
  flujos sin pantalla, por la API real) y `-employee.spec.ts` (el empleado solo mira), con
  `cart-checkout-helpers.ts`.

### Tablas de paridad con el producto actual

Operaciones:

| Producto actual | Ahora | Nota |
|---|---|---|
| `cart_checkout.carts.list` | `cart_checkout.cart.list` | busca también por sesión; filtros declarados |
| `cart_checkout.carts.get` | `cart_checkout.cart.get` | por id, sesión o cliente; trae sus líneas |
| `cart_checkout.items.list` | `cart_checkout.item.list` | el carrito por id o sesión |
| `cart_checkout.items.get` | `cart_checkout.item.get` | ahora también del asistente |
| `cart_checkout.orders.list` | `cart_checkout.order.list` | con la moneda del pedido |
| `cart_checkout.orders.get` | `cart_checkout.order.get` | también por número |
| `cart_checkout.carts.create` | `cart_checkout.cart.create` | 409 con campo si la sesión está usada |
| `cart_checkout.carts.mark_abandoned` | `cart_checkout.cart.mark_abandoned` | 409 en vez de no-op mudo; motivo en su campo |
| `cart_checkout.carts.delete` | `cart_checkout.cart.delete` | 404 si no existe; confirmación |
| `cart_checkout.carts.clear` (WASM) | `cart_checkout.cart.clear` | 409 si no está activo |
| `cart_checkout.carts.cleanup_expired` (WASM) | `cart_checkout.cart.cleanup_expired` | dice cuántos; tarea declarada |
| `cart_checkout.items.add` (WASM) | `cart_checkout.item.add` | 404/409 en vez de no-op mudo |
| `cart_checkout.items.update` (WASM) | `cart_checkout.item.update` | precio de la línea, nunca de quien llama |
| `cart_checkout.items.remove` | `cart_checkout.item.remove` | 404/409 |
| `cart_checkout.checkout.initiate` (WASM) | `cart_checkout.checkout.initiate` | sin huecos; email del carrito por defecto |
| `cart_checkout.orders.mark_paid` | `cart_checkout.order.mark_paid` | 409 en vez de no-op mudo |
| `cart_checkout.orders.fail` | `cart_checkout.order.fail` | 409 si completado o ya fallido; motivo en su campo |
| `cart_checkout.orders.complete` (WASM) | `cart_checkout.order.complete` | 409 si no está pagado |
| `_insert_item`, `_recalc_totals_by_token`, `_recalc_totals_by_item` | dentro de `item.add/update/remove` y `cart.clear` | intenciones internas del WASM |
| `_update_item_qty`, `_soft_delete_item`, `_soft_delete_cart_items` | dentro de `item.update/remove` y `cart.clear` | |
| `_expire_carts` | dentro de `cart.cleanup_expired` | |
| `_bump_counter`, `_insert_checkout` | dentro de `checkout.initiate` | |
| `_complete_checkout`, `_convert_cart` | dentro de `order.complete` | |
| — | `cart_checkout.customer.erase` | nueva: borrar los datos personales de un cliente (F14) |

Avisos: los doce del producto actual con el mismo hecho; solo cambia `carts.expired` →
`cart.expired` (entidad en singular). Nuevo: `cart_checkout.customer.erased` (CART_CHECKOUT-F14).

Tests:

| Producto actual | Ahora |
|---|---|
| `cart_currency.hub` / `.postgres` | `tests/test_services.py` (moneda del negocio, explícita, nula, inválida) |
| `handler` (Rust): cantidad × precio, HALF_UP, precio de la fila al cambiar cantidad | `tests/test_services.py` |
| `erp-cart-checkout-carts.test.ts` (alta dentro de la tabla, estado con lista, moneda del carrito) | `frontend/pages/CartsPage.test.ts`, `components/CartFormModal.test.ts` |
| `erp-cart-checkout-orders.test.ts` (total en céntimos con formato) | `frontend/pages/OrdersPage.test.ts` |
| `range-filters.test.ts`, `total-amount-filter.test.ts` | `frontend/pages/CartsPage.test.ts`, `OrdersPage.test.ts` (rangos en la unidad que se ve) |
| `form-error-in-panel.test.ts` | `components/CartFormModal.test.ts` (rechazo dentro del formulario) |
| `list-load-error.test.ts` | `frontend/pages/*.test.ts` (error de carga con Reintentar) |
| `lib/quantity.test.ts`, `money-display-guard.test.ts` | `frontend/lib/format.test.ts` |

## Lo que queda fuera

- **El aviso al instante de un carrito que vence solo** (CART_CHECKOUT-F07): la tarea de cada 15
  minutos corre en la fase 1 sobre el ámbito del worker, así que una lista abierta en el negocio no se
  entera hasta el siguiente cambio, hasta que se vuelve a abrir o hasta la relectura de 5 minutos. Con la
  tenencia de la fase 2 la tarea corre en cada hub y avisa a los suyos.
- **La entrega de avisos entre apps** (CART_CHECKOUT-F13): salen al outbox en la misma transacción y
  ninguna app los escucha, así que no hay nada que entregar.
- **Iconos propios** (`ion:bag-check-outline` del producto actual): pedidos en `UI-REQUESTS.md`.

## Lo que NO hace, a propósito

- No tiene tienda ni página pública: nadie sin sesión crea carritos ni pedidos.
- No cobra: «Pagado» es una marca manual; no hay pasarela, medio de pago ni importe cobrado.
- No genera venta, factura, registro VeriFactu, movimiento de caja ni de stock. Nada de lo cobrado aquí
  llega a la AEAT.
- No valida el precio ni el producto contra Inventario, ni calcula impuestos, envío o descuentos.
- No se enlaza con Clientes ni con Pagos.
- No avisa de carritos abandonados.
- No borra solo los datos personales al borrar un carrito (el borrado es lógico): para eso está
  CART_CHECKOUT-F14, que los vacía en carritos (también borrados) y pedidos cuando el cliente lo pide.
  El código de sesión, el número, los importes y las líneas (producto y precio) se quedan.

## Cambios frente al producto actual

- **Los rechazos ya no son mudos**: abandonar, vaciar, añadir o cambiar líneas en un carrito que no
  está activo, iniciar un pedido de un carrito inexistente, inactivo o vacío, marcar pagado o completar
  en el estado equivocado, o fallar uno completado, contesta con su motivo y no cambia nada ni avisa.
  Antes contestaba bien y emitía el aviso igualmente.
- **La numeración de pedidos no tiene huecos**: un pedido rechazado no gasta número (antes subía el
  contador igual). El día del número es el del negocio, no el del reloj UTC del servidor.
- **Un carrito vencido se lee como Expirado** aunque nadie haya lanzado la caducidad, y la caducidad
  está declarada como tarea programada (antes no la ejecutaba nadie).
- **Borrar pide confirmación** y **Fallar pide el motivo** en un formulario (antes, «Cancelled by
  operator» fijo, en inglés); el motivo de fallo y el de abandono van en su campo, no pegados a las
  notas. Fallar un pedido ya fallido se rechaza (antes repetía la nota).
- **Cada fila ofrece solo la acción que le toca** (Abandonar solo en un carrito activo; Marcar pagado,
  Completar y Fallar según el estado del pedido), y solo a quien puede.
- **El buscador de Carritos encuentra por sesión** (antes solo por email y nombre, aunque lo decía).
- **El pedido guarda su moneda** (la del carrito) y su total se pinta en ella (antes, en la del
  negocio).
- **Borrar un carrito deja libre su sesión** para otro carrito (antes la sesión de un carrito borrado
  no se podía volver a usar).
- **Cantidades con tres decimales** (`0,5`), como el resto del Hub; antes, enteros con escala 10⁶.
- **Email validado** en el carrito y en el pedido; iniciar el pedido sin email usa el del carrito.
- **Las líneas quitadas se borran** (antes quedaban con borrado lógico, sin forma de leerlas).
- **Fuera de las plantillas** (como `payment`): `verticals = []`, en la tienda.
- **Borrar los datos personales de un cliente** (CART_CHECKOUT-F14, nuevo): el producto actual no tenía
  forma de hacerlo; se adopta lo de Shopify y WooCommerce («erase personal data») y lo que ya hacen
  `service`, `reservation`, `appointment` y `table` con sus textos libres.
- **Topes de cantidad y de importe**: una línea de más de 1 000 000 unidades o un total por encima de
  99 999 999 999,99 € se rechazan en su campo (antes, error genérico).
