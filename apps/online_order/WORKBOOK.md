# Workbook — Pedidos online (app)
Prefijo: ONLINE_ORDER
Alcance MVP: restaurante (en la tienda; no viene en ninguna plantilla)
Estado de la app: en construcción — hoy, el código de cada mesa y su regeneración por la API y el asistente

> Manual de usuario y especificación de la app `online_order`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor y
> páginas).

## Para qué sirve y para quién

Pedidos online deja que el cliente sentado a la mesa pida él mismo desde su móvil: escanea el QR de su mesa, ve la
carta y pide, y el pedido llega a la cuenta de la mesa y a cocina. El pago no cambia: se cobra en el TPV como
siempre.

### En detalle

- **Cada mesa tiene su propio QR**, con un código que nadie puede adivinar. El QR se imprime una vez y se deja en la
  mesa; no caduca ni cambia solo.
- **Regenerar el QR** de una mesa le da un código nuevo: el QR impreso deja de valer en ese momento y hay que imprimir
  el nuevo. Sirve cuando alguien se ha llevado una foto del QR y pide desde fuera, o cuando el papel se ha perdido.
- **El cliente pide sin cuenta ni app instalada**: abre la página de su mesa con la cámara del móvil, ve la carta
  (fotos, descripción, alérgenos, suplementos y menús) y manda su pedido.
- **Solo se pide con el negocio abierto**, según el horario de Horarios.
- **Si la mesa ya tiene la cuenta abierta**, el pedido entra en ella y va a cocina. Si no, el primer pedido espera a
  que un empleado lo acepte o lo rechace desde el centro de avisos, salvo que el negocio apague «Aceptar el primer
  pedido de cada mesa».
- La cuenta se cobra en el TPV como cualquier otra.

### Quién la usa y qué hace cada uno

- El **propietario**, el **administrador** y el **responsable** ven el código de cada mesa y lo regeneran.
- El **empleado** no ve los códigos de las mesas.
- El **asistente** (por voz o por texto, con la sesión de quien habla) hace lo mismo: «¿qué mesas tienen ya su código
  QR para pedir?», «regenera el código QR de la mesa 4 de la terraza». Antes de regenerar pide confirmar con su
  tarjeta, que nombra la mesa por su número y su zona, como la nombra el plano de sala.

## Referencia adoptada

**Odoo, Square, Toast, Lightspeed, Qamarero, Last.app, SumUp y GloriaFood** (tabla y enlaces en «Decisiones de
mercado»): un QR fijo por mesa con un identificador imposible de adivinar, pedir solo con el negocio abierto y que un
empleado acepte el primer pedido de una mesa sin cuenta abierta (el «open table» de Qamarero, la aceptación manual de
Lightspeed y Toast). Nadie rota el QR impreso por tiempo ni usa la ubicación del móvil, que pide permiso y falla en
interiores; volver a generar el QR de una mesa es la salida cuando uno ya no se quiere que valga.

## Antes de empezar

1. Pedidos online enciende con ella **Mesas** (y, por Mesas, **Ventas** y **Clientes**), y no se puede apagar Mesas
   mientras esté encendida.
2. En **Mesas**, da de alta las zonas y las mesas del local: cada mesa tiene su QR.
3. Cada mesa recibe su código la primera vez que se genera su QR; desde entonces el mismo código vale hasta que se
   regenera.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| ONLINE_ORDER-F01 | Generar o regenerar el QR de una mesa | parcial — por la API y el asistente; falta el botón en la hoja de QR |
| ONLINE_ORDER-F02 | Ver e imprimir la hoja de QR de las mesas | parcial — la lista de mesas con su código, por la API y el asistente; falta la hoja |
| ONLINE_ORDER-F03 | El cliente abre la carta desde el QR de su mesa | no hecho |
| ONLINE_ORDER-F04 | El cliente pide desde su mesa | no hecho |
| ONLINE_ORDER-F05 | Aceptar o rechazar el primer pedido de una mesa | no hecho |
| ONLINE_ORDER-F06 | El cliente ve si su pedido se ha aceptado | no hecho |
| ONLINE_ORDER-F07 | Configurar los pedidos desde la mesa | no hecho |
| ONLINE_ORDER-F08 | La cuenta dice que el pedido es online | no hecho |

### ONLINE_ORDER-F01 Generar o regenerar el QR de una mesa
Estado: parcial — se hace por la API y con el asistente; falta el botón «Regenerar QR» de la hoja de QR
Actor: propietario, administrador o responsable; el asistente, con la sesión de quien habla
Pantalla: ninguna todavía (llegará en la hoja de QR de las mesas)
Pasos:
1. Elige la mesa, por su número y, si el número se repite, por su zona («la 4 de la terraza»).
2. Pide regenerar su QR: el asistente enseña su tarjeta con la mesa y avisa de que el QR impreso dejará de valer.
3. Al confirmar, la mesa recibe un código nuevo: el anterior deja de abrir la página de la mesa en ese momento. Una
   mesa que aún no tenía código recibe el primero.
Entra: la mesa, de Mesas.
Sale: el código nuevo de la mesa, la dirección de su página y cuándo se generó; el aviso de que se ha regenerado.
Si falla: no cambia nada. La mesa no existe o está borrada («Esa mesa no existe en este negocio.»); el número se repite en
varias zonas y no se dice cuál (Mesas pide la zona); quien lo pide no puede cambiar los QR de las mesas («No tienes
permiso»).
Implicados: TABLE-F02, TABLE-F04

### ONLINE_ORDER-F02 Ver e imprimir la hoja de QR de las mesas
Estado: parcial — la lista de las mesas con su código y su dirección se lee por la API y con el asistente; falta la hoja que se imprime desde el navegador
Actor: propietario, administrador o responsable
Pantalla: ninguna todavía (llegará como la hoja de QR de las mesas)
Pasos:
1. Abre la lista de las mesas: cada una con su número, su zona y, si ya tiene código, la dirección de su página y
   cuándo se generó. Las mesas salen en el orden del plano de sala (la 2 antes que la 10).
2. Imprime la hoja: un QR por mesa con su número y su zona, para recortar y dejar en cada mesa.
Entra: las mesas y sus zonas, de Mesas.
Sale: nada; solo se lee.
Si falla: sin mesas dadas de alta, la lista sale vacía; quien no puede ver los QR de las mesas no la ve («No tienes
permiso»).
Implicados: TABLE-F02, WEBSITE-F09

### ONLINE_ORDER-F03 El cliente abre la carta desde el QR de su mesa
Estado: no hecho — falta la página pública de la mesa
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. Escanea el QR de su mesa con la cámara del móvil y se abre la página de la mesa, con el nombre del negocio y el
   número de la mesa.
2. Ve la carta completa: los productos a la venta que se muestran en la carta, con su foto, su descripción, sus
   alérgenos y su precio, los suplementos de cada uno y los menús. Lo agotado no sale.
Entra: la carta (Inventario, Suplementos, Menús) y el horario del negocio (Horarios).
Sale: nada; solo se lee.
Si falla: un QR que ya no vale (regenerado) enseña «Este QR ya no está activo; pide ayuda al personal.»; con el
negocio cerrado, la carta se ve pero dice que ahora no se aceptan pedidos.
Implicados: ONLINE_ORDER-F01, INVENTORY-F36, SCHEDULE-F02

### ONLINE_ORDER-F04 El cliente pide desde su mesa
Estado: no hecho — falta el pedido
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. Añade productos, con sus suplementos, menús, cantidad y una nota.
2. Pulsa **Pedir**.
3. Si la mesa tiene la cuenta abierta, el pedido entra en ella y se manda a cocina con todo lo que la cuenta tenía
   sin mandar, también lo que el camarero había apuntado en el TPV. Si no la tiene, el pedido queda pendiente hasta
   que un empleado lo acepte (ONLINE_ORDER-F05).
Entra: la carta, la cuenta de la mesa (Mesas y Ventas) y el horario del negocio.
Sale: las líneas en la cuenta de la mesa y la comanda en cocina, o el pedido pendiente con su aviso.
Si falla: no se escribe nada. El negocio cerrado; un producto que se ha agotado mientras pedía; demasiados pedidos
seguidos desde el mismo móvil o en el negocio («Inténtalo dentro de unos minutos o pide ayuda al personal.»); un QR
que ya no vale.
Implicados: ONLINE_ORDER-F05, SALE-F20, KITCHEN-F05

### ONLINE_ORDER-F05 Aceptar o rechazar el primer pedido de una mesa
Estado: no hecho — falta el pedido pendiente y su aviso
Actor: empleado, responsable, administrador o propietario
Pantalla: Centro de avisos → Pedidos por aceptar
Pasos:
1. El centro de avisos enseña «Pedidos por aceptar» con cada pedido pendiente: la mesa, lo que pide y cuándo.
2. Pulsa **Aceptar**: se abre la cuenta de la mesa, entran las líneas y se mandan a cocina; o pulsa **Rechazar** y
   el cliente lo ve en su página.
3. Cobrada o anulada la cuenta, el siguiente pedido de esa mesa vuelve a esperar.
Entra: el pedido pendiente.
Sale: la cuenta de la mesa con sus líneas y la comanda, o el pedido rechazado.
Si falla: otro empleado ya lo ha decidido («Este pedido ya está decidido.»).
Implicados: ONLINE_ORDER-F04, TABLE-F10, TABLE-F18

### ONLINE_ORDER-F06 El cliente ve si su pedido se ha aceptado
Estado: no hecho — falta el pedido
Actor: cliente (sin sesión)
Pantalla: Página de la mesa
Pasos:
1. Tras pedir, la página de la mesa enseña su pedido como pendiente, aceptado o rechazado.
2. Se actualiza sola cuando un empleado lo decide.
Entra: el pedido.
Sale: nada; solo se lee.
Si falla: un QR que ya no vale deja de enseñar el pedido.
Implicados: ONLINE_ORDER-F05

### ONLINE_ORDER-F07 Configurar los pedidos desde la mesa
Estado: no hecho — faltan los ajustes
Actor: propietario o administrador
Pantalla: Ajustes
Pasos:
1. Enciende o apaga «Aceptar el primer pedido de cada mesa» (encendido de fábrica). Apagado, todo pedido entra solo
   y abre la cuenta de la mesa si no la hay.
2. Pulsa **Guardar**.
Entra: los ajustes de la app y el horario del negocio (Horarios), que dicen si hoy se aceptan pedidos.
Sale: los ajustes guardados.
Si falla: sin horario del negocio, los ajustes avisan de que no se aceptarán pedidos hasta configurarlo.
Implicados: SCHEDULE-F02

### ONLINE_ORDER-F08 La cuenta dice que el pedido es online
Estado: no hecho — faltan el origen y el canal en la cuenta de Ventas
Actor: camarero o cocina
Pantalla: ninguna propia (se ve en la cuenta de Ventas y en la comanda de Cocina)
Pasos:
1. Una cuenta abierta por un pedido desde la mesa lleva el origen «Pedido online».
2. Su comanda sale en cocina como un pedido para comer en el local.
Entra: el pedido del cliente.
Sale: la cuenta de Ventas con su origen y su canal.
Si falla: no aplica; lo pone el propio pedido.
Implicados: SALE-F19, KITCHEN-F05

## Servicios: lo que entra y lo que sale

Todo se puede pedir por la API y el asistente (por voz o por texto, con la sesión de quien habla), con las mismas
reglas y permisos; las pantallas llegarán con la hoja de QR. Una mesa se nombra por su id o como la dice una persona:
su número y, si se repite, su zona.

### Lo que ofrece: consultas

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las mesas en el orden del plano de sala, cada una con su zona y, si ya lo tiene, su código, la dirección de su página y cuándo se generó, en páginas (hasta 100) | ver los QR de las mesas (+ ver mesas) | F02 | `online_order.qr_code.list` |

### Lo que ofrece: acciones

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Da a una mesa un código nuevo; el anterior deja de valer al momento | regenerar los QR de las mesas (+ ver mesas) | F01 | `online_order.qr_code.regenerate` |

Regenerar es de **riesgo alto** para el asistente: el QR impreso deja de valer y no se puede volver atrás, así que su
tarjeta pide la confirmación antes de hacerlo.

### Lo que avisa

| Aviso | Cuándo | Qué lleva |
|---|---|---|
| `online_order.qr_code.regenerated` | Se genera o se regenera el código de una mesa | La mesa (`table_id`); nunca el código |

### A qué reacciona

A ningún aviso de otra app.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver los QR de las mesas | sí | sí | sí | no | `online_order.view_qr_code` |
| Regenerar los QR de las mesas | sí | sí | sí | no | `online_order.change_qr_code` |

Las mesas las lee Mesas con el permiso de quien pregunta: hace falta el de esta app **y** el de ver mesas.

## Para quien lo mantiene

- **`requires = ["table"]`**: lo único que llama hoy son las lecturas de Mesas, `table.table.list` y
  `table.table.get`, por su nombre (`base.operations.call`), con el permiso de quien pregunta. Las apps que necesitarán
  el pedido (Ventas, Inventario, Clientes y Horarios) entran en `requires` en el mismo cambio que empiece a llamarlas.
- Modelo (UUIDv7, sin `hub_id`): `TableCode`, una fila por mesa con código: el id de la mesa de Mesas (`table_id`,
  único, sin clave ajena, como `order_id` de Mesas hacia Ventas), el código (`secrets.token_urlsafe(16)`, guardado tal
  cual porque la hoja se vuelve a imprimir, único) y cuándo se generó. Regenerar escribe con un solo `INSERT … ON
  CONFLICT (table_id) DO UPDATE`: dos regeneraciones a la vez de una mesa sin código no chocan, gana la última.
- La dirección de la página de una mesa es `/p/<negocio>/order/<código>` sobre la dirección pública del negocio
  (`base.qr.public_url`, la misma que usa Página web para su QR). La página la servirá la puerta pública de `base`
  cuando la app declare `public_pages = {"order": "online_order.public"}`, con ONLINE_ORDER-F03.
- Las mesas borradas en Mesas no salen en la lista; su fila de `TableCode` se queda y no abre nada, porque la página
  de la mesa comprobará que la mesa sigue existiendo.
- El aviso `online_order.qr_code.regenerated` no lleva el código: los avisos llegan a Automatizaciones y al
  registro, y el código abre la página de la mesa.

## Lo que queda fuera

- **Encargar para recoger** y **a domicilio** (con la dirección, las zonas de reparto, el pedido mínimo y los gastos
  de envío) son las dos entregas siguientes de esta app, después del pedido desde la mesa.
- **Pagar desde el móvil**: el pago sigue en el TPV.
- La verificación del teléfono por SMS, la rotación automática del QR y su caducidad por tiempo.
- La carta solo para mirar, con un QR para todo el local, es la de la Página web del negocio.

## Decisiones de mercado (2026-11-25)

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Odoo | QR fijo por mesa; solo con la sesión de caja abierta; entra solo a cocina; se paga en caja | https://www.odoo.com/documentation/17.0/applications/sales/point_of_sale/self_order.html |
| Square | QR fijo por mesa; la barrera es el cobro o una retención de tarjeta | https://squareup.com/help/us/en/article/8690-set-up-open-tabs-for-your-online-selling-profile |
| Toast | QR fijo por mesa; cuentas abiertas; domicilio con aprobación manual opcional | https://support.toasttab.com/en/article/Setting-Up-Toast-Mobile-Order-and-Pay |
| Lightspeed | QR por mesa; aceptación automática o manual en el TPV | https://resto-support.lightspeedhq.com/hc/articles/4411463548443 |
| Qamarero | Mesa abierta por defecto; opción de aceptar el primer pedido de cada mesa | https://intercom.help/qamarero-9e4c4f5026e3/es/articles/9711683-open-table-acepta-cada-primer-pedido-desde-el-qr |
| Last.app | QR por mesa; solo dentro del horario; QR aparte para llevar | https://desk.last.app/portal/en/kb/articles/lastqr-configuration |
| SumUp | Se paga al pedir; sin cuenta abierta | https://www.sumup.com/es-es/pedir-y-pagar/ |
| GloriaFood | Aceptar o rechazar cada pedido | https://gloriafood.com/order-taking-app-for-restaurants |

La ubicación del móvil se descarta: su precisión depende del dispositivo y del entorno y exige permiso
(https://developer.mozilla.org/en-US/docs/Web/API/GeolocationCoordinates/accuracy).
