# Workbook — Ventas / TPV (app)
Prefijo: SALE
Alcance MVP: núcleo
Estado de la app: hecha (servidor y páginas); lo que depende de apps que aún no existen lo dice cada flujo

> Manual de usuario y especificación de la app `sale`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Ventas / TPV del producto actual
> (`modules-workspace/modules/sales`, `origin/main` `c6cf4af`, v2.16.169) y de sus ficheros
> `workflow/*.md`. La app hace lo mismo y se ve igual; los números de flujo se conservan
> (`SALES-Fnn` → `SALE-Fnn`) porque otras apps los citan. Lo que todavía depende de una app que no
> existe en esta plataforma (Cocina, Suplementos, Menús, VeriFactu, Impresión) lo dice su flujo
> en la línea `Estado:`.

## Para qué sirve y para quién

Ventas / TPV es la **caja registradora** del negocio: se monta la cuenta tocando artículos, se cobra
en efectivo, con tarjeta o repartido entre varios medios, y queda una **venta que ya no se puede
cambiar**, con su número del día, su IVA línea a línea y su tique o su factura. Sirve a los dos
negocios:

- En el **restaurante**, la cuenta vive abierta mientras la mesa come: se le añaden rondas, se manda a
  cocina, se imprime la cuenta para la mesa, se cobra entera o por partes, se divide o se junta.
- En la **peluquería**, cada servicio del tique lleva a la profesional que lo hizo y la cuenta se
  cobra al terminar, con la clienta puesta.

Quién la usa:

- El **empleado** (camarero, recepcionista, cajero): monta la cuenta, pone notas, invita una línea,
  aplica descuentos hasta el máximo del negocio, aparca y recupera cuentas, cobra y consulta las
  ventas.
- El **responsable**: además vende a precio libre, aplica descuentos por encima del máximo, anula una
  cuenta abierta o una línea ya enviada a cocina, anula y devuelve ventas, ve las cifras y prepara las
  notas rápidas, las secciones, los medios de pago y los ajustes del TPV.
- El **propietario** y el **administrador**: todo.

Ventas no guarda mesas ni clientes en la cuenta (son de Mesas y de Clientes), no numera facturas ni
habla con la AEAT (se las pide a Facturación en el mismo cobro; la AEAT es de VeriFactu), no mueve el
stock (lo hace Inventario al oír la venta) y no cuadra la caja (Caja lee las ventas; Ventas solo le
pregunta si la caja está abierta antes de cobrar en efectivo).

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó.

- **Cobrar por artículos y repartir el pago entre medios**, como
  [Square](https://squareup.com/help/gb/en/article/8421-new-order-and-pay-capabilities-with-square-for-restaurants)
  y [Lightspeed](https://resto-support.lightspeedhq.com/hc/en-us/articles/226405708-Splitting-a-bill).
  No se reparte por asiento.
- **Anular antes de que se mueva el dinero, devolver después**, con motivo y permiso, sin mezclar los
  dos caminos: [Toast — anulaciones](https://doc.toasttab.com/doc/platformguide/adminVoidingOrders.html)
  y [devoluciones frente a anulaciones](https://doc.toasttab.com/doc/platformguide/adminRefundsAndVoids.html),
  Lightspeed, Dynamics 365 Business Central, Square y Shopify trazan la misma línea.
- **La comanda nace al enviar, no al cobrar**, por rondas
  ([Toast — flujo de cocina](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html)).
- **Una cuenta abierta se cobra al precio con que se pidió** (Square Orders, Oracle Simphony, Odoo,
  Business Central): cambiar el precio del catálogo no reprecia una cuenta que ya está abierta.
- **Notas rápidas** preconfiguradas que se aplican de un toque (Lightspeed Restaurant K-Series).
- **Cada servicio lleva a quien lo hizo** y la cita se cobra sin volver a teclearla (Fresha, Vagaro).
- **Tique o factura** según la AEAT: tique (factura simplificada) hasta su límite, factura completa
  con nombre, NIF y domicilio por encima o a petición, copia marcada como duplicado
  ([AEAT — facturas simplificadas](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/manual-iva-2025/capitulo-10-obligac-formales-suj-registro/obligaciones-materia-facturacion/facturas-simplificadas.html),
  art. 4 del Real Decreto 1619/2012: 3.000 € con IVA en hostelería, comercio al por menor y
  peluquería).
- **Nada en efectivo desde 1.000 €** en un negocio de España, también repartido entre medios (Ley
  7/2012, art. 7).

## Antes de empezar

- **Impuestos** y **Clientes** se activan con Ventas y no se pueden apagar mientras Ventas esté
  encendida: sin las reglas de IVA no se cierra ninguna venta, y la venta guarda la ficha de su
  cliente.
- **Inventario** es opcional. Con él, el TPV vende su catálogo y la venta baja el stock; sin él, el
  TPV vende a precio libre por sección y lo dice en la rejilla.
- **Servicios** es opcional (peluquería). Con él, el TPV vende sus servicios (SALE-F38), al precio
  propio de la profesional si lo tiene, y una línea de servicio se puede pagar con un bono de la
  clienta (SALE-F27).
- **Facturación** es opcional. Con ella, cada cobro sale con su tique (factura simplificada) o su
  factura numerados en su serie en el mismo cobro, y cada anulación o devolución con su rectificativa;
  sin ella, la venta es un tique sin documento fiscal. Configura antes el **emisor** en Facturación: sin
  él se cobra igual y el documento queda pendiente, a la vista, hasta «Emitir ahora» (SALE-F29).
- **Caja** es opcional. Con «Activar caja» encendido, no se cobra en efectivo sin una sesión de caja
  abierta (SALE-F08); con tarjeta y otros medios, sí.
- Los artículos tienen que tener categoría de IVA: si no, salen marcados «Falta el IVA» y no se
  venden.
- **Canarias, Ceuta y Melilla**: si en **Impuestos → Ajustes** el negocio es de Canarias, Ventas dice
  «IGIC» donde dice «IVA» («Falta el IGIC», «Sección (IGIC)», «IGIC que cobra», «Precios con IGIC
  incluido»…); en Ceuta o Melilla, «IPSI». Cambiar el territorio lo renombra al momento, en todas las
  pantallas abiertas. La cifra del impuesto de **Ventas** es la excepción: dice el impuesto con que se
  declararon las ventas del periodo, no el territorio de hoy (SALE-F28).
- De fábrica hay dos medios de pago: **Efectivo** y **Tarjeta**. Bizum, transferencia u otro se
  añaden con el asistente diciendo su tipo (SALE-F37).
- Venta por peso: tecleando la cantidad (SALE-F10); no hay lector de báscula.

Configuración inicial, paso a paso:

1. **Ajustes** del TPV: medios permitidos, descuentos y descuento máximo, cliente obligatorio,
   documento por defecto, cabecera y pie del tique (SALE-F34).
2. **Secciones**, si se cobra a precio libre (frutería, varios) (SALE-F35).
3. **Notas rápidas**, si la cocina recibe instrucciones repetidas (SALE-F36).
4. Haz una venta de prueba con cada medio y comprueba el tique (SALE-F01, SALE-F02, SALE-F29).

## Pantallas

Ventas / TPV se abre desde el menú **Ventas / TPV** y tiene cinco entradas: **Vender**, **Ventas**,
**Notas rápidas**, **Secciones** y **Ajustes**. «Secciones» es lo que el producto actual llamaba
«Departamentos»: la palabra corta cabe en la barra de pestañas de un móvil con las cinco a la vista.

### Vender
Se abre a pantalla completa de la aplicación; el menú ⋮ de la tira de categorías tiene «Pantalla
completa» / «Salir de pantalla completa» (la del navegador, cuando el dispositivo la permite). Dos
zonas:

- **Catálogo**: la tira de categorías de Inventario con su número de artículos («Todos» primero y,
  con Servicios, «Servicios» detrás), la lupa que abre el buscador («Buscar producto…», por nombre o
  SKU, en el servidor; con Servicios busca también sus servicios) y la rejilla: artículos con sus
  iniciales, su unidad y su precio, y al final la baldosa «Precio libre». En «Servicios», cada servicio
  con sus iniciales, su duración y su precio («Desde», «Por hora», «Variable» o «Gratis» si no es de
  precio fijo). La rejilla pide de 100 en 100, por categoría, y «Cargar más» trae los siguientes.
- **Cuenta** (en el móvil, un cajón que abre el botón flotante con el total): arriba, el botón de
  pausa «Aparcar esta cuenta», el de cliente («Asignar cliente» o su nombre), «Cuentas abiertas» con
  su número, y «Cerrar» en el móvil; el título editable («Cuenta nueva») y los chips de cliente,
  «Atiende …» y «Falta el cliente». Cada línea: nombre, precio por unidad, marca de descuento o
  «Invitación», nota y profesional debajo; botones de descuento, nota, invitación y el selector de
  cantidad (una línea enviada a cocina solo enseña su cantidad, «Comanda N» y el botón ⊗ «Anular
  este artículo»; una pagada con bono, «Ya pagado · <bono>», 0,00 € y solo el botón de quitarla). Pie: la fila «Descuento del ticket» si lo hay, «Total» (el que calcula el
  servidor), el botón de descuento, la impresora («Imprimir cuenta») y «Cobrar · <importe>».

Hojas que se abren encima: precio libre, importe de un servicio sin precio fijo, nota, descuento,
«Anular «<artículo>»», «Aparcar cuenta»,
«Quién atiende esta cuenta», «Tienes una cuenta a medias» y el buscador de clientes. Vacía: «Toca un
producto para añadirlo.» y, sin artículos, «Sin productos.» (o el motivo: Inventario no está activo).
Avisos arriba de la rejilla: artículos sin IVA («N artículos no se pueden vender…» con «Revisar el
catálogo», solo a quien puede arreglarlo). Error de carga: «Error cargando el TPV» con «Reintentar».

### Cobro
Hoja que abre «Cobrar». Arriba, el importe grande (el que calcula el servidor), «Cobrando N líneas de
<total>» si hay líneas marcadas y «Restante» al repartir. A un lado, el resumen («Tique» / «Factura»,
cliente), con «Factura» los datos del cliente y, con Servicios, «Líneas pagadas de otra forma»: cada
línea de servicio del cobro con su hueco del bono (SALE-F27). Al otro, «Cobros tomados», los medios de pago
(el efectivo, no disponible desde 1.000 €, con su motivo), «Entregado», «Cambio» y el teclado en
efectivo, o «Importe exacto» y «Cobra <importe> en el datáfono y confirma.» con otro medio;
«Repartir el cobro» y «Añadir este cobro». Pie: el motivo si no se puede cobrar y «Cobrar <importe>»
(«Cobrando…» mientras va); con la caja cerrada y efectivo, el rechazo y «Abrir sesión de caja».

### Cuentas abiertas
Desplegable del icono de tique de la cuenta: «Aparcar esta cuenta» con su explicación, «Cuentas
abiertas» y «Toca una cuenta para retomarla.», y una fila por cuenta abierta del negocio (título o
importe, hora e importe) con su papelera. Vacía: «No hay cuentas abiertas». Un fallo se pinta encima
de las filas.

### Cuenta (precuenta)
Ventana «Cuenta» que abre la impresora del pie: el papel que se lleva a la mesa, con el aviso «Cuenta
— no es una factura. El tiquet fiscal se entrega al cobrar.», y los botones de imprimir y cerrar.

### Ventas
Título «Ventas», periodo («Hoy», «7 días», «30 días», «Todo»), seis cifras («Tickets», «Ingresos»,
«Ticket medio», «IVA», «Descuentos», «Anuladas») y la tabla (Fecha, Número, Cliente, Pago, Estado,
Total) con el buscador «Buscar número o cliente…», filtros, vista tabla o tarjetas, 50 por página.
Por fila: «Documento», «Reimprimir» y, según permiso, «Anular» y «Devolver». Vacía: «Aún no hay
ventas.»; cargando: «Cargando…»; error: el aviso con «Reintentar».

### Documento de venta
Ventana del tique de una venta: el papel tal como se imprime (título «Tique» o «Factura», cabecera,
el número que le dio Facturación —«Factura FACT-2026-000012», «Tiquet TICKET-2026-000031»— o, sin
él, el de la venta, fecha, líneas, una fila de IVA por clave fiscal, total, forma de pago, entregado y
cambio, pie), la ✕ y la impresora. Toda impresión desde **Ventas** sale con «DUPLICADO». Error:
«Error cargando el documento».

### Devolver
Ventana «Devolver la venta <número>»: explicación, una tarjeta por forma de pago («Cobrado», «Ya
devuelto», «Devolvible», «Importe a devolver» y, si hace falta, «Devolver por»), «Devolver todo»,
«Qué se devuelve» (las líneas de la venta con una casilla cada una y, en una línea de varias
unidades, «Unidades que vuelven»; la pagada con bono dice «Ya pagado · <bono>» y, marcada, «La sesión
vuelve a <bono>.»), «Motivo» y «Devolver <importe>». Cargando: «Cargando lo que se
puede devolver…»; nada que devolver: «No queda nada por devolver en esta venta.».

### Anular venta
Ventana «Anular la venta <número>»: la explicación, el «Motivo (obligatorio)» y «Anular» /
«Cancelar». Un rechazo se lee dentro de la ventana, que sigue abierta.

### Notas rápidas
Explicación, tabla (Nota, Posición) con buscador, **+** para añadir y, por fila, «Editar» y
«Eliminar». Vacía: «Todavía no hay notas rápidas…»; cargando: «Cargando notas rápidas…». Quien no
tiene el permiso de ajustes la ve sin **+** ni acciones.

### Secciones
Explicación, tabla (Nombre, IVA que cobra, Posición), **+** y, por fila, «Editar» y «Eliminar». Vacía:
«Todavía no hay secciones…»; cargando: «Cargando secciones…». Quien no tiene el permiso de
ajustes la ve sin **+** ni acciones.

### Ajustes
Cabecera «TPV»: un interruptor o campo por ajuste (SALE-F34) y «Guardar». Cargando: «Cargando
ajustes…»; error: «No se pudieron cargar los ajustes.» con «Reintentar»; sin permiso: «No tienes
permiso para cambiar estos ajustes. Pídeselo a un administrador si lo necesitas.».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (o el texto de su pantalla) mientras llega el primer resultado. |
| Vacío | El texto de su pantalla, con **+** si puede crear. |
| Error | El aviso con «Reintentar»; un rechazo de una acción sale dentro de su hoja o ventana, junto a su campo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva (`app_inactive`) | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Vertical | Estado |
|---|---|---|---|
| SALE-F01 | Vender y cobrar en efectivo | común | hecho |
| SALE-F02 | Cobrar con tarjeta u otro medio sin cambio | común | hecho |
| SALE-F03 | Repartir el cobro entre varios medios de pago | común | hecho |
| SALE-F04 | Elegir tique o factura y los datos del cliente | común | hecho |
| SALE-F05 | Cobrar cuando el negocio exige cliente | común | hecho |
| SALE-F06 | Recuperar un cobro que se quedó sin respuesta | común | hecho |
| SALE-F07 | El TPV avisa de lo que hoy no se puede vender | común | parcial |
| SALE-F08 | Cobrar sin la caja abierta | común | hecho |
| SALE-F09 | Vender a precio libre por sección | común | hecho |
| SALE-F10 | Vender por peso, tecleando la cantidad | común | hecho |
| SALE-F11 | Elegir los suplementos de un artículo | común | hecho |
| SALE-F12 | Componer un menú | restaurante | no hecho: Menús |
| SALE-F13 | Poner una nota en una línea | común | hecho |
| SALE-F14 | Aplicar un descuento a una línea o a la cuenta | común | parcial |
| SALE-F15 | Invitar una línea | común | hecho |
| SALE-F16 | Atribuir la cuenta o una línea a quien atiende | común | hecho |
| SALE-F17 | Aparcar una cuenta y recuperarla | común | hecho |
| SALE-F18 | Eliminar una cuenta abierta | común | hecho |
| SALE-F19 | Abrir la cuenta de una mesa y dejarla en la mesa | restaurante | hecho |
| SALE-F20 | Enviar la comanda a cocina y anular una línea enviada | restaurante | parcial |
| SALE-F21 | Imprimir la cuenta para la mesa (precuenta) | restaurante | hecho |
| SALE-F22 | Cobrar solo una parte de la cuenta | restaurante | hecho |
| SALE-F23 | Dividir la cuenta de una mesa | restaurante | hecho |
| SALE-F24 | Juntar las cuentas de dos mesas | restaurante | hecho |
| SALE-F25 | Pasar la cuenta a otra mesa | restaurante | hecho |
| SALE-F26 | Cobrar una cita desde la agenda | peluquería | hecho |
| SALE-F27 | Pagar una línea con un bono | peluquería | hecho |
| SALE-F28 | Consultar el historial y las cifras de ventas | común | hecho |
| SALE-F29 | Ver y reimprimir el documento de una venta | común | hecho |
| SALE-F30 | Anular una venta cobrada | común | hecho |
| SALE-F31 | Devolver una venta (toda, una parte o por otro medio) | común | hecho |
| SALE-F32 | Devolver la sesión de un bono | peluquería | hecho |
| SALE-F33 | Unir las ventas de dos fichas de cliente | común | hecho |
| SALE-F34 | Ajustar el TPV | común | hecho |
| SALE-F35 | Dar de alta y ordenar las secciones del precio libre | común | hecho |
| SALE-F36 | Preparar las notas rápidas | común | hecho |
| SALE-F37 | Añadir un medio de pago (Bizum, transferencia…) | común | parcial |
| SALE-F38 | Vender un servicio de Servicios | peluquería | hecho |

### SALE-F01 Vender y cobrar en efectivo
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender, Cobro
Pasos:
1. En **Vender**, elige una categoría en la tira de arriba («Todos» enseña todo) o pulsa la lupa y
   busca por nombre o SKU.
2. Toca el artículo: entra como línea de la cuenta. Tocarlo otra vez (mismo profesional, sin nota ni
   descuento) sube la cantidad; el selector de la línea la sube o la baja, y a 0 la línea se quita.
3. Pulsa «Cobrar · <total>» al pie de la cuenta (en el móvil, abre antes la cuenta con el botón
   flotante, que enseña el total).
4. En la hoja **Cobro**, con efectivo elegido, marca en el teclado el importe entregado; el cambio
   sale debajo en grande.
5. Pulsa «Cobrar <total>».
6. La hoja se cierra, la cuenta queda vacía y se abre el **Documento de venta** con el tique.
Entra: los artículos y precios de Inventario; los tipos de IVA de Impuestos; los ajustes del TPV.
Sale: la venta cobrada e inmutable, con número `AAAAMMDD-NNNN` del día del negocio, sus líneas, su
pago y su desglose de IVA (una fila por clave fiscal, cerrada una sola vez: lo mismo que declara la
factura), y la cuenta cerrada. Con Facturación, su tique (F2) numerado en la serie del año en el mismo
cobro (INVOICE-F01): o los dos o ninguno. Ventas avisa de la venta cobrada: Inventario baja el stock
(INVENTORY-F21) y Clientes suma la compra a la ficha (CUSTOMER-F20). Cada línea guarda la categoría,
el tipo, el país, la región y la regla de Impuestos con que se cobró.
Si falla: sin importe entregado el botón no cobra y se lee «Marca en el teclado el importe
entregado»; corto, «Lo entregado no cubre el total». Un artículo sin IVA sale marcado «Falta el IVA»
y al tocarlo dice «No se puede vender: sin categoría fiscal. Falta configurar el IVA.». Un rechazo al
cobrar se pinta en la hoja con su frase (p. ej. «Un producto del tique ya no está en el catálogo.
Quita la línea y vuelve a añadirla.») y la cuenta sigue intacta. Si mientras se cobra otro
dispositivo cambia la cuenta (añade, cambia, quita, anula o cobra una línea, pone o quita un
descuento, la divide, la junta o la cierra), gana el primero: el cobro no cobra nada, la hoja dice
«La cuenta ha cambiado mientras se cobraba. No se ha cobrado nada; la cuenta se ha vuelto a cargar,
revísala y vuelve a cobrar.» y el siguiente «Cobrar» cobra lo que hay; si gana el cobro, el cambio
que llegaba se rechaza con «La cuenta ha cambiado mientras se cobraba. No se ha cambiado nada: revisa
las líneas y vuelve a intentarlo.». Nunca entra en la venta una línea anulada o quitada ni se cobra
otra cantidad u otro descuento del que guarda la cuenta.
Implicados: INVENTORY-F21, CUSTOMER-F20, TAX-F18

### SALE-F02 Cobrar con tarjeta u otro medio sin cambio
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. Con la cuenta lista, pulsa «Cobrar · <total>».
2. En la hoja **Cobro**, toca **Tarjeta** (o el medio que sea; salen los medios activos que permiten
   los ajustes).
3. Se lee «Importe exacto» y «Cobra <importe> en el datáfono y confirma.»: cobra en el datáfono
   aparte.
4. Pulsa «Cobrar <importe> con tarjeta». El resultado es el de SALE-F01.
Entra: los medios de pago del negocio.
Sale: la venta con un pago por el importe exacto y sin cambio; el aviso de venta cobrada lleva el
tipo de cada medio, para que Caja no lo sume al efectivo.
Si falla: el TPV no habla con el datáfono: si la tarjeta se rechaza, cierra la hoja sin confirmar.
Un medio que el negocio no permite o que ya no está activo se rechaza: «Esa forma de pago no está
disponible en este negocio.».
Implicados: ninguno

### SALE-F03 Repartir el cobro entre varios medios de pago
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. En la hoja **Cobro**, pulsa «Repartir el cobro». Arriba aparece «Restante».
2. Elige un medio, marca el «Importe de este cobro» (en efectivo, lo entregado) y pulsa «Añadir este
   cobro». Sin importe marcado, el cobro cubre todo lo que falta.
3. Los cobros tomados salen en «Cobros tomados»; la ✕ quita uno.
4. Cuando el restante llega a 0, pulsa «Cobrar <total>».
Entra: los medios de pago y lo que entrega el cliente.
Sale: una venta con una fila por medio; el cambio sale siempre del efectivo y nunca se reparte.
Si falla: mientras falte dinero, el botón dice «Faltan <importe>»; si los cobros no suman el total al
céntimo, el servidor lo rechaza: «Los cobros no suman el total de la venta.». En un negocio de España,
una venta de 1.000 € o más no admite **ningún** cobro en efectivo, tampoco repartido: el botón de
efectivo sale desactivado con su motivo y el servidor rechaza «Por ley, una venta de 1.000 € o más no
se puede cobrar en efectivo, ni en parte. Cóbrala con tarjeta, Bizum o transferencia.». Partir la
cuenta en varios cobros (SALE-F22) no lo salta: cuenta la cuenta entera (lo ya cobrado de ella y todo lo
que le queda), porque la ley suma los pagos en que se fracciona una operación (Ley 7/2012, art. 7.Uno.1,
párrafo 2): en una cuenta de 1.000 € o más ningún cobro parcial puede llevar efectivo.
Implicados: ninguno

### SALE-F04 Elegir tique o factura y los datos del cliente
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. En la hoja **Cobro**, toca «Tique» o «Factura». Arranca en «Documento por defecto», o en «Factura»
   si «Emitir factura si el cliente tiene NIF» está encendido y el cliente asignado tiene NIF.
2. Con «Factura», debajo se piden «Nombre o razón social», «País», «NIF» y «Domicilio», ya rellenos si
   hay cliente asignado. Fuera de España se pide además el «Tipo de documento» (NIF-IVA de la UE,
   Identificación fiscal de su país, Pasaporte, Otro documento).
3. Si el importe pasa del límite de la factura simplificada (3.000 € en España), no hay botón «Tique»:
   sale «Esta venta no puede ser un tique» y los mismos datos.
4. Con los tres datos puestos se lee «Esta venta sale como factura completa» y se cobra como siempre.
Entra: el cliente asignado (Clientes).
Sale: la venta con su tipo de documento fijado al cobrar, que no se puede cambiar después y, con
Facturación, su factura completa (F1) numerada en la serie «FACT» en el mismo cobro (INVOICE-F02); el
nombre, NIF, dirección, país y tipo de documento del cliente viajan con ella y con el aviso de venta
cobrada, y la venta guarda su copia (lo que declara un documento emitido después, SALE-F29). El nombre
fiscal de una ficha con empresa es el de la **empresa** («Estudio Ana SL», la razón social que va con su
CIF), no el de la persona; el TPV sigue enseñando a la persona.
Si falla: sin los tres datos el botón dice «Faltan los datos del cliente»; una factura sin esos datos
la rechaza el servidor por cualquier vía: «Una factura necesita el nombre, el NIF y la dirección del
cliente. Rellénalos o cóbrala como tique.». El NIF se lee como lo lee Clientes: un NIF, NIE o CIF
español que no cuadra sale bajo su casilla («Ese NIF no es válido.») y el botón dice «Revisa el NIF»;
fuera de España, sin tipo de documento, «Indica qué tipo de documento es un NIF extranjero…» (el
servidor lo rechaza igual, 422 en su campo; un NIF-IVA europeo lo comprueba el servidor). Un tique por
encima del límite también lo rechaza el servidor por cualquier vía: «Por encima de 3.000 € esta venta
no puede ser un tique: cóbrala como factura con los datos del cliente.». El país es un código ISO 3166-1
(la misma lista que Facturación: «UK» o «EL» no valen, «GB» sí): otro se rechaza con «Escribe el código
ISO del país, p. ej. ES, FR o GB.» (422 en `customer_country`), también el que traiga una ficha vieja.
Si Facturación rechaza los datos del destinatario de una factura (422), el cobro no se graba y se
corrigen: nunca queda una factura «pendiente» que no se podría emitir.
Implicados: CUSTOMER-F17, INVOICE-F02

### SALE-F05 Cobrar cuando el negocio exige cliente
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Con «Exigir cliente en cada venta» encendido y sin cliente, la cuenta enseña el chip «Falta el
   cliente» y «Cobrar» se ve bloqueado.
2. Al tocar «Cobrar» o el chip, sale «Este negocio exige un cliente en cada venta. Elige uno para seguir
   con el cobro.» y se abre el buscador de Clientes.
3. Elige o da de alta el cliente; el chip pasa a su nombre y «Cobrar» abre la hoja.
Entra: el cliente que elige el buscador de Clientes.
Sale: nada propio hasta cobrar; la venta lleva el cliente.
Si falla: el servidor rechaza cualquier cobro sin cliente: «Este negocio exige un cliente en cada
venta.».
Implicados: CUSTOMER-F17, CUSTOMER-F18

### SALE-F06 Recuperar un cobro que se quedó sin respuesta
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. Pulsa «Cobrar…» y el hub no contesta (se reinicia, se cae la red).
2. El TPV pregunta él solo (hasta dos veces) si ese intento de cobro llegó a grabarse.
3. Si se grabó, se cierra como un cobro normal. Si no, sale «El servidor no responde (puede estar
   reiniciándose). Inténtalo de nuevo en unos segundos y, si persiste, avisa al encargado.» y volver
   a pulsar no duplica la venta.
4. Si no se pudo saber, sale «No hemos podido confirmar si el cobro se completó. Compruébalo en Ventas
   antes de volver a cobrar.» con el botón «Comprobar en Ventas».
Entra: nada de otras apps.
Sale: como mucho una venta por intento de cobro: la clave del intento nace al abrir la hoja y se
reutiliza en cada reintento; el mismo intento devuelve la misma venta, también si dos dispositivos lo
mandan a la vez (el segundo espera y recibe la venta del primero, nunca «no se ha cobrado»). Una clave
ya usada para otra cuenta, otras líneas u otra venta de mostrador se rechaza: «Esa clave de intento ya
se usó para otro cobro. Vuelve a abrir el cobro para cobrar este.». Si el documento fiscal de esa venta
había quedado pendiente, el reintento se lo vuelve a pedir a Facturación (sin cobrar otra vez); si sigue
sin poder, sigue pendiente, a la vista (SALE-F29).
Si falla: ver los pasos 3 y 4; nunca dice «no se ha cobrado» sin saberlo.
Implicados: ninguno

### SALE-F07 El TPV avisa de lo que hoy no se puede vender
Estado: parcial — el aviso de que el negocio ya factura con VeriFactu y sus tiques no llegarían a Hacienda llega con VeriFactu
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Al abrir **Vender**, si hay artículos sin categoría fiscal, sale arriba de la rejilla «N artículos
   no se pueden vender: les falta el IVA.» y, a quien puede arreglarlo, «Revisar el catálogo», que
   lleva a Inventario.
2. Esos artículos salen en la rejilla marcados «Falta el IVA» y no entran en la cuenta.
3. Si Inventario no está activo, la rejilla lo explica y se vende a precio libre.
Entra: el catálogo de venta de Inventario.
Sale: nada.
Si falla: si el catálogo no carga, «No se ha podido cargar el catálogo.» con «Reintentar»; el precio
libre sigue disponible.
Implicados: INVENTORY-F04
Pendiente: el aviso de que el negocio ya factura con VeriFactu y sus tiques no llegarían a Hacienda
llega con VeriFactu.

### SALE-F08 Cobrar sin la caja abierta
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. Con «Activar caja» encendido en Caja y sin sesión de caja abierta, cobra en efectivo (también un
   cobro repartido con una parte en efectivo).
2. La hoja **Cobro** no cobra nada y dice «La caja está cerrada: abre una sesión de caja para cobrar en
   efectivo.»; a quien puede abrirla le ofrece «Abrir sesión de caja», que lleva a **Caja**. La
   pantalla **Vender** no cambia: la cuenta sigue ahí.
3. Abierta la sesión, vuelve a **Vender** y cobra. Con tarjeta, Bizum o transferencia se cobra siempre,
   con la caja abierta o cerrada.
Entra: si la caja está activada y si hay sesión abierta, que Ventas pregunta a Caja
(`cash_register.session.current`) con la sesión de quien cobra, solo cuando hay efectivo.
Sale: nada propio; el cobro rechazado no gasta número.
Si falla: si Caja no está en el negocio, está apagada o no contesta (un rechazo, un fallo), se cobra:
el bloqueo cede antes que parar las ventas, y Caja enseña ese cobro entre los de fuera de turno
(CASH_REGISTER-F17).
Implicados: CASH_REGISTER-F04, CASH_REGISTER-F17

### SALE-F09 Vender a precio libre por sección
Estado: hecho
Vertical: común
Actor: responsable (empleado con el permiso de precio libre)
Pantalla: Vender
Pasos:
1. Toca la baldosa «Precio libre», al final de la rejilla.
2. Marca el importe en el teclado y elige la sección en «Sección (IVA)»; cada botón enseña su
   tipo de IVA.
3. Pulsa «Añadir <importe>»: entra una línea con el nombre de la sección y ese importe. Nunca se
   suma a otra línea.
Entra: las secciones del negocio (SALE-F35) o, si no hay, las categorías de IVA de Impuestos.
Sale: una línea sin artículo de catálogo, con su importe y su categoría de IVA, que se cobra como
cualquier otra.
Si falla: «Añadir» no se puede pulsar sin importe y sección; sin secciones ni categorías, «No hay
categorías de IVA que elegir. Configura antes tus tipos de IVA, en Impuestos.». Sin el permiso de precio libre la baldosa dice «Lo tiene que hacer
un responsable» y el servidor rechaza la línea por cualquier vía (también al cobrar directamente).
Implicados: TAX-F18

### SALE-F10 Vender por peso, tecleando la cantidad
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Toca un artículo cuya unidad es de masa, volumen o tiempo (kg, g, l, h…): entra como línea con su
   unidad.
2. Escribe la cantidad en el selector de la línea (p. ej. 0,532).
3. El importe se recalcula en el servidor y la línea muestra la unidad («0,532 kg»).
Entra: la unidad del artículo, su escalón y la cantidad a la que se refiere su precio, de Inventario.
Sale: la línea con su cantidad y su unidad congeladas.
Si falla: una cantidad que no encaja con el escalón de la unidad se rechaza con «La cantidad no encaja
con el escalón del producto» y la línea queda como estaba. No hay lector de báscula.
Implicados: INVENTORY-F26

### SALE-F11 Elegir los suplementos de un artículo
<!-- origen: wf:restaurante-dia#rec_restaurante-f06 old:sales/workflow/la-cuenta.md#sales-f11 -->
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Con Suplementos activa, toca un artículo que tiene grupos de suplementos (suyos o de su categoría): se
   abre una hoja con su nombre. Sin grupos, el artículo entra directo, como siempre.
2. Cada grupo dice su regla: «Elige N» si es obligatorio, «Hasta N» si tiene techo, «Opcional» si no; cada
   opción lleva su suplemento con su signo («+1,00 €», «−2,00 €»; nada si es gratis) y las de fábrica ya
   salen marcadas.
3. Toca las opciones: en un grupo de una sola, tocar otra la cambia y tocar la misma la quita; en uno con
   techo, al llegar a él el siguiente toque dice «Extras está completo: quita una para elegir otra»; una
   opción que se puede repetir lleva su contador («× 2») y su «−».
4. Pulsa «Añadir · <precio>»: la línea entra con sus suplementos debajo del nombre y su precio ya sumado.
   Mientras un grupo obligatorio no esté completo, el botón dice «Elige una opción para continuar» y
   tocarlo señala ese grupo.
5. Cobra como siempre (SALE-F01): la línea cobra lo que valía al pedirla aunque el suplemento cambie o se
   borre después. Un suplemento con otro tipo de IVA (el refresco del menú infantil, al 21 % junto a la
   hamburguesa al 10 %) sale en el tique como línea propia debajo del plato («+ Refresco»), por cada plato.
Entra: los grupos y opciones de Suplementos, que comprueba y valora lo elegido al añadir la línea.
Sale: la línea con sus suplementos congelados (avisa: cuenta cambiada); la comanda de cocina los lleva bajo el
plato («+QUESO, -CEBOLLA», avisa: comanda enviada); al cobrar, el tique los nombra bajo el plato y cada
suplemento de otro IVA es una línea propia con su base y su cuota; el stock lo baja solo el plato.
Si falla: los motivos de Suplementos dentro de la hoja («Elige al menos 1 en «Punto».», «Esta opción no se
ofrece con este producto.»…), también por el asistente o la API, que no pasan por la hoja: un grupo
obligatorio sin elegir se rechaza igual. Si no se pueden leer los grupos, «No se han podido leer los
suplementos de este producto. Inténtalo de nuevo.» y no entra nada. Sin Suplementos activa, un artículo con
suplementos pedido por la API se rechaza («Suplementos no está activa en este negocio…») y uno sin ellos
entra como siempre.
Implicados: MODIFIER-F06, MODIFIER-F07, MODIFIER-F08

### SALE-F12 Componer un menú
Estado: no hecho — los menús son de la app Menús, que todavía no existe en esta plataforma
Vertical: restaurante
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. En «Todos», los menús salen primero con la etiqueta «Menú». Toca uno y elige los platos de cada
   grupo.
2. Pulsa «Añadir · <total>»; al cobrar el menú se reparte en tantas líneas como tipos de IVA tenga.
Entra: los menús de Menús.
Sale: una línea de menú; el aviso de venta lleva sus componentes para que Inventario baje cada plato.
Si falla: lo dirá Menús.
Implicados: COMBOS-F09, INVENTORY-F22

### SALE-F13 Poner una nota en una línea
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. En la línea, toca el botón «Nota».
2. Toca las notas rápidas que salen arriba (se suman separadas por coma; tocarlas otra vez las quita)
   o escribe en el cuadro (hasta 255 caracteres).
3. Pulsa «Guardar»: la nota sale debajo de la línea. «Quitar», o dejar el cuadro vacío, la borra.
Entra: las notas rápidas del negocio (SALE-F36).
Sale: la nota en la línea; viaja a la comanda de cocina, a la cuenta impresa y queda congelada en la
venta.
Si falla: si las notas rápidas no cargan, «No se han podido cargar las notas rápidas: escribe la nota
a mano.». Si no se guarda, «No se ha podido guardar ese cambio de la línea. La línea vuelve a estar
como estaba.». Una línea ya enviada a cocina no tiene botón de nota.
Implicados: ninguno

### SALE-F14 Aplicar un descuento a una línea o a la cuenta
Estado: parcial — sin el PIN del encargado en el dispositivo del empleado (elevación de la plataforma): el descuento por encima del máximo lo aplica un responsable desde su sesión
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Para una línea, toca su etiqueta de precio («Descuento en la línea»); para toda la cuenta, el botón
   de etiqueta del pie («Descuento del ticket»).
2. Marca el porcentaje; en la cuenta puedes cambiar a importe fijo con el botón de la moneda.
3. Pulsa «Aplicar −N %» (o «Aplicar −<importe>»). «Quitar» lo borra. La línea enseña «−N %» y el pie
   la fila «Descuento del ticket».
4. Si el descuento pasa del máximo que el negocio deja dar sin autorización, solo lo puede aplicar un
   responsable; la cuenta guarda quién lo autorizó y no lo vuelve a comprobar al cobrar.
Entra: «Permitir descuentos» y el descuento máximo de los ajustes.
Sale: el descuento en la cuenta o en la línea; al cobrar se reparte entre las líneas, la base y el IVA
declarados ya lo llevan descontado, y la venta guarda el importe descontado.
Si falla: con «Permitir descuentos» apagado no hay botones y el servidor rechaza «Este negocio no
permite descuentos.». Por encima del máximo sin ser responsable: «Ese descuento supera lo que este
negocio permite sin que lo autorice el encargado.» y la cuenta sigue como estaba. Un importe mayor
que la cuenta no se puede aplicar. Si otro dispositivo está cobrando esa cuenta, gana el primero
(SALE-F01).
Implicados: ninguno
Pendiente: el PIN del encargado sobre el dispositivo del empleado llega con la elevación por PIN de la
plataforma; mientras, el empleado le pasa el dispositivo o el responsable lo aplica desde el suyo.

### SALE-F15 Invitar una línea
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. En la línea, toca el regalo («Invitar / quitar invitación»).
2. La línea queda a 0 con la marca «Invitación»; tocarlo otra vez la vuelve a cobrar.
Entra: nada de otras apps.
Sale: la línea invitada: no suma dinero ni IVA, pero el aviso de venta la lleva para que Inventario
baje el stock; la venta guarda el coste de lo invitado.
Si falla: «No se ha podido guardar ese cambio de la línea. La línea vuelve a estar como estaba.». Una
línea ya enviada a cocina no se puede invitar.
Implicados: INVENTORY-F21

### SALE-F16 Atribuir la cuenta o una línea a quien atiende
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. En la cabecera de la cuenta, el chip «Atiende yo» dice a quién se atribuye. Tócalo.
2. En «Quién atiende esta cuenta», elige a la persona del equipo de Personal o «Yo (quien tenga la
   sesión)».
3. Las líneas que se añadan a partir de ahí quedan selladas con esa persona. Para corregir una línea
   ya puesta, toca el nombre que sale debajo de ella («De quién es esta línea») y elige otra persona o
   «El profesional de la cuenta».
4. Al cobrar, el chip vuelve a «yo».
Entra: el equipo de Personal (fichas activas).
Sale: la venta y cada línea atribuidas a esa persona (para el cierre por profesional).
Si falla: «No se ha podido cargar el equipo. La venta se sigue atribuyendo a quien tenga la sesión.»;
«No se ha podido mover la línea a otro profesional. Se queda con el que tenía.». Una línea enviada a
cocina no se reasigna.
Implicados: STAFF-F21

### SALE-F17 Aparcar una cuenta y recuperarla
Estado: hecho
Vertical: común
Actor: empleado, responsable
Pantalla: Cuentas abiertas
Pasos:
1. Con una cuenta a medias, pulsa el botón de pausa («Aparcar esta cuenta») o, en **Cuentas
   abiertas**, «Aparcar esta cuenta».
2. En «Aparcar cuenta» el título viene con la hora; cámbialo si quieres («p. ej. Ana — terraza») y
   confirma: sale «Aparcada como «…»» y la pantalla queda vacía, también de cliente.
3. Para retomarla, abre **Cuentas abiertas** (icono de tique con el número de cuentas) y toca su fila;
   su cliente vuelve con ella.
4. Si delante hay otra cuenta, pregunta «Tienes una cuenta a medias»: «Aparcarla y abrir»,
   «Eliminarla y abrir» o «Cancelar».
5. Al recargar la pantalla, cada dispositivo vuelve a la cuenta que tenía abierta.
Entra: al retomar la cuenta, su cliente, de Clientes (CUSTOMER-F19).
Sale: la cuenta sigue abierta con su título; aparcar nunca la anula.
Si falla: «No se ha podido aparcar la cuenta. Sigue en pantalla.». Con «Permitir tiques aparcados»
apagado no hay botón de aparcar en ningún sitio.
Implicados: CUSTOMER-F19

### SALE-F18 Eliminar una cuenta abierta
Estado: hecho
Vertical: común
Actor: responsable; una cuenta vacía, también el empleado
Pantalla: Cuentas abiertas
Pasos:
1. En **Cuentas abiertas**, toca la papelera de la cuenta: cambia a «Toca otra vez para eliminar —
   anula la cuenta». Si no se toca en 3 segundos, se desarma.
2. Toca otra vez: la cuenta desaparece de la lista. También se elimina con «Eliminarla y abrir» al
   cambiar de cuenta.
Entra: la cuenta elegida.
Sale: la cuenta queda anulada, no borrada (avisa: cuenta anulada); lo ya cobrado de ella sigue en sus
ventas.
Si falla: «No se ha podido eliminar esa cuenta abierta. Sigue en la lista.». Una cuenta ya cobrada no
se puede anular: «Esa cuenta ya no está abierta.»; anularla dos veces no hace nada la segunda. Sin
permiso de anular no hay papelera, salvo en una **cuenta vacía** (sin líneas vivas ni cobros): esa la
elimina quien monta cuentas, porque un grupo que se va sin pedir no obliga a llamar a un responsable
(como Mesas al cerrar una mesa vacía, TABLE-F21). Con algo pedido o cobrado, el servidor exige el
permiso de anular (403).
Implicados: TABLE-F20, TABLE-F21

### SALE-F19 Abrir la cuenta de una mesa y dejarla en la mesa
Estado: hecho — sin preguntar los comensales en el TPV (ver «Lo que queda fuera»)
Vertical: restaurante
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Con Mesas activa y permiso de sentar, la barra de la cuenta tiene, antes del cliente, el botón de
   mesa (rejilla, «Asignar mesa»). Tócalo: se abre «Elegir mesa», con un buscador («Buscar mesa…», en el
   servidor) y las mesas en servicio como baldosas del color de su estado (Disponible verde, Ocupada
   roja, Reservada ámbar, Bloqueada gris), con el número, la zona, las plazas («4 pax»), el estado y,
   si la tiene, la reserva de hoy («Marta · 21:00»). Sin mesas: «Aún no hay mesas. Créalas en Mesas →
   Plano de sala.».
2. Toca una mesa Disponible o Reservada: la cuenta en pantalla se sienta allí (TABLE-F12) y toma su
   nombre como título («Mesa 4»); sin cuenta aún, Mesas abre una con ese título y el TPV la pone en
   pantalla (TABLE-F10). Una cuenta a la que se quitó la mesa se vuelve a sentar (TABLE-F24). Las
   Ocupadas y Bloqueadas no se pueden tocar (su título dice por qué).
3. La cabecera de la cuenta enseña su mesa («Mesa 4») y el botón se pinta en color.
4. «Quitar de la mesa», en la misma ventana, suelta la mesa sin cobrar: la mesa queda libre y la cuenta
   sigue abierta en **Cuentas abiertas** (TABLE-F13).
Entra: las mesas, su estado y la mesa de la cuenta, de Mesas (`table.table.list`,
`table.floor.status`, `table.session.by_order`), seguidos en vivo.
Sale: nada propio; Mesas sienta (`table.session.open` con la cuenta, `.restore`) o suelta
(`table.session.park`) con la sesión de quien atiende, y retitula la cuenta (`sale.order.set_label`).
Si falla: el rechazo de Mesas dentro de la ventana, con sus palabras («Otro dispositivo acaba de ocupar
esa mesa…», «Esa cuenta ya está en la mesa N.»…). Sin Mesas activa, o sin permiso de ver sus mesas y
sentar, no hay botón ni se pregunta nada a Mesas.
Implicados: TABLE-F10, TABLE-F12, TABLE-F13, TABLE-F24

### SALE-F20 Enviar la comanda a cocina y anular una línea enviada
Estado: parcial — servidor hecho (envío por rondas y anulación de una línea enviada, también en la pantalla); la pestaña «Comanda actual» con el botón de envío la pone Cocina, que todavía no existe
Vertical: restaurante
Actor: empleado (enviar), responsable (anular)
Pantalla: Vender
Pasos:
1. Enviar a cocina marca las líneas pendientes de la cuenta con una ronda nueva («Comanda N») y la
   hora de envío; un doble envío no manda nada dos veces.
2. Una línea enviada queda bloqueada: ni cantidad, ni nota, ni descuento, ni invitación.
3. Para quitar un plato ya enviado, pulsa ⊗ «Anular este artículo» en su línea: se abre «Anular
   «<artículo>»» con «Ya se envió a cocina. Sale de la cuenta y se guarda el motivo. Tiene que
   autorizarlo un responsable.», los motivos de un toque («Error al pedir», «El cliente lo cambia»,
   «Agotado», «Pedido dos veces») y «O escribe el motivo…». «Anular artículo» no se puede pulsar sin
   motivo.
4. La línea sale de la cuenta, el total baja y la línea guarda el motivo, quién lo autorizó y cuándo.
Entra: las líneas pendientes de la cuenta.
Sale: las líneas con su ronda (avisa: comanda enviada, con las líneas, sus notas y quién atiende); al
anular una línea enviada, avisa de la línea anulada con su motivo.
Si falla: sin nada pendiente, «No hay nada nuevo que enviar a cocina.». Pedir que se quite una línea
ya enviada la rechaza: «Esa línea ya no se puede quitar: ya se envió a cocina (anúlala con un
motivo), ya está cobrada o ya no está en una cuenta abierta.». Anular una línea sin enviar, cobrada,
ya anulada o sin motivo se rechaza con «Esa línea no se puede anular…».
Implicados: KITCHEN-F29
Pendiente: la pestaña «Comanda actual» con el botón de envío la pone Cocina; hasta que exista, el envío
se hace por el asistente o la API.

### SALE-F21 Imprimir la cuenta para la mesa (precuenta)
Estado: hecho — imprime con el diálogo de impresión del dispositivo hasta que exista Impresión
Vertical: restaurante
Actor: empleado, responsable
Pantalla: Cuenta (precuenta)
Pasos:
1. Con la cuenta en pantalla, pulsa la impresora del pie («Imprimir cuenta»).
2. Se abre «Cuenta» con las líneas, notas, descuentos, el desglose de IVA, el total y el título, y el
   aviso «Cuenta — no es una factura. El tiquet fiscal se entrega al cobrar.».
3. Pulsa la impresora de arriba: sale por la impresora del dispositivo.
Entra: la cuenta abierta y su total calculado por el servidor.
Sale: un papel sin número fiscal; no consume numeración ni crea venta.
Si falla: «No se pudo imprimir la cuenta».
Implicados: ninguno
Pendiente: la impresora de tiques en red llega con Impresión; hasta entonces se imprime con el
diálogo de impresión del dispositivo.

### SALE-F22 Cobrar solo una parte de la cuenta
Estado: hecho
Vertical: restaurante
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Con dos o más líneas, toca las líneas que paga esta persona (la línea, no sus botones): se marcan
   con un círculo.
2. Pulsa «Cobrar»: la hoja dice «Cobrando N líneas de <total>» y cobra solo esas.
3. Tras cobrar se abre el **Documento de venta** de ese cobro y, detrás, la cuenta sigue abierta con
   lo que falta; lo cobrado ya no vuelve a salir. Cobrar la última línea pendiente cierra la cuenta.
   Si es parcial o total lo dice lo que se cobró (las líneas fijadas al abrir la hoja), no lo que esté
   marcado al terminar.
Entra: las líneas marcadas.
Sale: una venta con esas líneas (avisa: venta cobrada); las líneas quedan atadas a su venta. El
descuento en % de la cuenta se aplica a cada cobro; el de importe fijo, solo al que la cierra.
Si falla: los mismos rechazos que un cobro normal, también el de la cuenta que cambió mientras se
cobraba (SALE-F01): la hoja cobra las líneas y la versión que enseñaba al abrirse, nunca las de
después. Si con la hoja abierta otro dispositivo cierra la cuenta, la pantalla la suelta al cerrar la
hoja y avisa; no queda una cuenta fantasma.
Implicados: ninguno

### SALE-F23 Dividir la cuenta de una mesa
Estado: hecho — el botón «Dividir cuenta» es del control de mesa de Mesas (TABLE-F17)
Vertical: restaurante
Actor: empleado, responsable
Pantalla: ninguna propia (el control de mesa es de Mesas; también por el asistente o la API)
Pasos:
1. Se eligen las líneas que pasan a una cuenta nueva y se divide.
2. Las líneas pasan enteras a la cuenta nueva con su importe, su IVA y su ronda de cocina. Sin líneas,
   la cuenta nueva nace vacía.
Entra: la cuenta y las líneas que se mueven.
Sale: dos cuentas abiertas que suman lo mismo que la original al céntimo (avisa: cuenta abierta).
Si falla: si otro dispositivo está cobrando esa cuenta, la división espera y, si la cobró, se rechaza
(«La cuenta ha cambiado…») sin mover nada.
Implicados: TABLE-F17

### SALE-F24 Juntar las cuentas de dos mesas
Estado: hecho — el botón «Fusionar» es del control de mesa de Mesas (TABLE-F16)
Vertical: restaurante
Actor: empleado, responsable
Pantalla: ninguna propia (el control de mesa es de Mesas; también por el asistente o la API)
Pasos:
1. Se elige la cuenta que se absorbe y la que queda.
2. Las líneas sin cobrar de una pasan a la otra y la vacía queda anulada.
Entra: las dos cuentas.
Sale: una sola cuenta; las líneas se mueven sin volver a crearlas, así que lo ya enviado a cocina no
se envía otra vez. Repetirlo no cambia nada (avisa: cuentas juntadas, con la absorbida y la que
queda).
Si falla: si una de las dos ya no está abierta, se rechaza sin mover nada.
Implicados: TABLE-F16, KITCHEN-F28

### SALE-F25 Pasar la cuenta a otra mesa
Estado: hecho en Mesas (TABLE-F15): la cuenta no cambia
Vertical: restaurante
Actor: empleado, responsable
Pantalla: ninguna
Pasos:
1. En el control de mesa (de Mesas), pulsa «Transferir».
2. Elige la mesa libre.
Entra: la mesa de destino, de Mesas.
Sale: nada en Ventas.
Si falla: lo dirá Mesas.
Implicados: TABLE-F15

### SALE-F26 Cobrar una cita desde la agenda
Estado: hecho — el botón «Cobrar» de la agenda es de Citas (APPOINTMENT-F17)
Vertical: peluquería
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. En la agenda de Citas, «Cobrar» abre la cuenta de la cita (con una línea por servicio, a su precio
   reservado y con la profesional) y lleva al TPV con esa cuenta en pantalla (`/sale/pos?order=<id>`).
2. Se cobra como en SALE-F01; si se aparca y se recupera, la cuenta sigue atada a la cita.
3. Pulsar «Cobrar» otra vez (o en otro dispositivo a la vez) vuelve a la misma cuenta abierta: una cita
   tiene una sola cuenta abierta, nunca dos.
Entra: la cita, de Citas.
Sale: la venta con la cita y la profesional (avisa: venta cobrada y venta nacida de una cita, con la
cita, quién atendió y el total).
Si falla: enlazar una cita a una cuenta que ya no está abierta se rechaza; enlazarla a otra cuenta
cuando ya tiene una abierta, «Esa cita ya tiene una cuenta abierta: cobra esa (Cuentas abiertas).». Si
la dirección nombra una cuenta que ya no está abierta (se cobró, se anuló) o que no existe, el TPV lo
dice («Esa cuenta ya no está abierta…») y sigue como estaba.
Implicados: APPOINTMENTS-F17

### SALE-F27 Pagar una línea con un bono
Estado: hecho
Vertical: peluquería
Actor: empleado, responsable
Pantalla: Cobro
Pasos:
1. Con Servicios activa y la clienta asignada a la cuenta, pulsa «Cobrar»: aparece «Líneas pagadas de
   otra forma» con cada línea de un servicio del cobro y, en su hueco, «Pagar esta línea con un bono»:
   los bonos de la clienta que cubren ese servicio, el que se gasta primero y por qué (SERVICE-F22).
2. Si la línea es de más de una unidad («Corte × 2»), pulsa «Separar en N líneas»: un bono paga una
   línea entera de una unidad, y cada una tiene su hueco.
3. Elige el bono (viene elegido el que se gasta primero) y pulsa «Gastar una sesión»: la línea pasa a
   0,00 € con «Ya pagado · <bono>», el importe del cobro baja y el hueco dice «<bono>: sesión gastada.
   Quedan N.» con «Deshacer». Lo que no paga el bono se cobra con su medio; si el bono paga todo, se
   cobra 0,00 € sin medio de pago.
4. Cobra: la línea sale en el tique a 0,00 € con «Ya pagado · <bono>» y la sesión queda gastada.
5. Cerrar la hoja, aparcar la cuenta, recargar o cobrarla en otro dispositivo no cambia nada: la
   línea de la cuenta guarda el bono que la paga.
Entra: los bonos de la clienta y su saldo, de Servicios.
Sale: la línea de la cuenta pagada con una sesión reservada de Servicios (avisa: cuenta cambiada);
al cobrar, la venta con la línea a 0,00 € y la sesión gastada en la misma operación (SERVICE-F24).
Quitar la línea, anularla o eliminar la cuenta suelta la sesión (SERVICE-F23); dividir o juntar
cuentas la lleva con su línea. Una línea pagada con bono no cambia de cantidad, invitación ni
descuento: se deshace el bono antes.
Si falla: los motivos de Servicios se leen en el hueco («Este bono ya no tiene sesiones
disponibles.», «Este bono ha caducado.»…). Una línea que no es de un servicio, una invitación o una de
varias unidades no se puede pagar con bono («Un bono paga una línea de una unidad: separa la línea
antes.»); un descuento de importe fijo de la cuenta mayor que lo que quedaría por pagar se rechaza
(«Ese descuento es mayor que el importe del que se descuenta.»). Al cobrar, nada se cobra si la sesión ya
no está reservada (pasó un día, SERVICE-F25) o si la venta no es de la titular del bono: se lee el
motivo en la hoja y se deshace el bono. El descuento máximo sin responsable se mide sobre lo que queda
por pagar: una línea pagada con bono no cuenta. Sin permiso para gastar sesiones, el hueco no
aparece. Queda fuera hasta la fase 2 (activación por hub): sin Servicios activa el hueco tampoco aparece y, si
se apaga con líneas pagadas con bono, cobrarlas se rechaza («Servicios no está activa en este
negocio…»); hoy la plataforma no apaga apps por hub y ese camino solo se prueba en los tests.
Implicados: SERVICE-F22, SERVICE-F23, SERVICE-F24, SERVICE-F25

### SALE-F28 Consultar el historial y las cifras de ventas
<!-- origen: fi:modules/sales#query-sales-by_staff wf:peluqueria-dia#rec_peluqueria-f15 fi:modules/sales#query-sales-last_7_days fi:modules/sales#query-sales-list fi:modules/sales#query-sales-stats fi:modules/sales#query-sales-today old:sales/workflow/historial-y-correcciones.md#sales-f28 -->
Estado: hecho
Vertical: común
Actor: empleado (historial), responsable (cifras)
Pantalla: Ventas
Pasos:
1. Abre **Ventas / TPV → Ventas**. Arriba, el periodo («Hoy» por defecto, «7 días», «30 días»,
   «Todo»), contado en el día del negocio.
2. Las cifras del periodo: «Tickets», «Ingresos», «Ticket medio», «IVA», «Descuentos» y «Anuladas».
   «Ingresos» ya resta lo devuelto. La cifra del impuesto lleva el nombre del impuesto con que se
   declararon las ventas del periodo: «IVA», «IGIC» si todas se cobraron con IGIC (Canarias) o «IPSI»
   (Ceuta y Melilla). Si en el periodo hay ventas de dos impuestos (porque el negocio cambió de
   territorio a mitad, por ejemplo), se llama «Impuestos». Sin ventas en el periodo, lleva el impuesto del
   territorio de **Impuestos → Ajustes**, y cambia al momento si se cambia el territorio.
3. La tabla: Fecha, Número, Cliente, Pago, Estado (Completada, Anulada, Devuelta; con «Por devolver
   <importe>» si se devolvió una parte) y Total. Busca con «Buscar número o cliente…», filtra por
   estado, pago, fecha o total, u ordena.
4. Toca una fila para ver su documento (SALE-F29). La tabla se recarga sola cuando se cobra, anula o
   devuelve una venta.
Entra: nada de otras apps.
Sale: nada guardado. Lo vendido por cada profesional en el periodo (lo piden Personal y el asistente para
la comisión) ya resta lo devuelto: lo que vuelve, a quien lo vendió; el dinero que vuelve sin nada que
valga (solo dinero, una invitación o la sesión de un bono), a todos los de esa venta según lo que a cada
uno le queda por devolver tras las devoluciones anteriores, así que nadie baja de 0. Cada devolución
cuenta en el día de su venta y se reparte al céntimo: con lo que nadie atendió, suma los «Ingresos» del
periodo.
Si falla: «Error cargando métricas» (las cifras salen como «—»). Vacía: «Aún no hay ventas.». Quien
no tiene permiso de informes ve la tabla, sin las cifras. Un total que no es un importe dice «Escribe
un importe, como 12,50» bajo su campo, y una fecha final anterior a la inicial, «La fecha final no
puede ser anterior a la inicial.»; ninguno de los dos filtra y manda el periodo.
Implicados: STAFF-F21

### SALE-F29 Ver y reimprimir el documento de una venta
Estado: hecho — sin el QR de VeriFactu, que llega con su app
Vertical: común
Actor: empleado, responsable
Pantalla: Documento de venta
Pasos:
1. En **Ventas**, toca la fila o la acción «Documento»; también se abre solo tras cobrar, la cuenta
   entera o una parte (SALE-F22).
2. Se ve el tique («Tique», o «Factura» si se cobró como factura) con su cabecera, el número que le
   dio Facturación en el cobro («Factura FACT-2026-000012», «Tiquet TICKET-2026-000031»; sin
   Facturación, o mientras su documento está pendiente, el número de la venta), fecha, líneas, una fila
   de IVA por clave fiscal (un exento dice su causa: «Exento (E1)»), total, forma de pago, entregado y
   cambio, y el pie. Si su documento fiscal no se pudo emitir al cobrar, el papel lo dice bajo el
   número («Documento fiscal pendiente») y, encima del papel (fuera de lo que se imprime), el aviso
   «Documento fiscal pendiente — Facturación no pudo emitirlo al cobrar (falta el emisor, o un permiso).
   Cuando esté resuelto, emítelo ahora.» con «Emitir ahora».
3. Pulsa la impresora del pie para imprimirlo, o «Reimprimir» en la fila. Toda impresión desde
   **Ventas** sale con «DUPLICADO»; solo el primer papel justo tras cobrar es el original.
4. **Documento pendiente**: en la lista, una venta con algún documento fiscal pendiente (el suyo, la
   rectificativa de su anulación o la de una devolución) lleva la pastilla «Documento pendiente» bajo
   su estado y la acción «Emitir ahora» (quien cobra). «Emitir ahora» pide a Facturación, por nombre y
   con la sesión de quien lo pulsa, todo lo que espera, en orden (su tique o factura y luego las
   rectificativas) y sale «Documentos fiscales emitidos.». La fase 1 no tiene relay que lo emita solo.
Entra: la venta, con el número de su documento fiscal (que Facturación le dio en el mismo cobro).
Sale: el papel; reimprimir no crea venta ni documento fiscal. «Emitir ahora» emite los documentos que
esperaban (avisa: venta con su documento, uno por documento).
Si falla: «Cargando documento…» y «Error cargando el documento». «No se pudo imprimir». «Emitir ahora»
rechazado dice el motivo de Facturación («Configura el emisor…») y no cambia nada; sin palabras del
servidor, «No se han podido emitir los documentos. Inténtalo de nuevo.».
Implicados: INVOICE-F01, INVOICE-F02, INVOICE-F06
Pendiente: el QR de VeriFactu llega con su app; el A4 de una factura con los datos del destinatario lo
imprime Facturación (INVOICE-F18).

### SALE-F30 Anular una venta cobrada
Estado: hecho
Vertical: común
Actor: responsable
Pantalla: Ventas, Anular venta
Pasos:
1. En **Ventas**, en una venta Completada sin devoluciones, pulsa «Anular».
2. Se abre «Anular la venta <número>». Escribe el «Motivo (obligatorio)» y pulsa «Anular», o
   «Cancelar».
3. Sale «Venta anulada», la ventana se cierra, la fila pasa a Anulada y la cifra «Anuladas» sube.
Entra: la venta elegida.
Sale: la venta marcada como anulada con hora, quién y motivo; no se borra (avisa: venta anulada).
Con Facturación, la rectificativa del tique entero (R5, serie «RECT») en la misma anulación
(INVOICE-F07); si el tique había quedado pendiente, se emite antes, en la misma anulación. Si Facturación
sigue sin poder, la anulación sigue adelante y los dos documentos quedan pendientes, a la vista
(SALE-F29, «Emitir ahora»). Inventario repone el stock (INVENTORY-F23) y Clientes resta la compra (CUSTOMER-F21).
Si falla: sin motivo, «Hace falta un motivo para anular una venta»; si se cobró como factura
completa, «Esta venta lleva factura completa: emite una factura rectificativa en vez de anularla»;
con devoluciones, «Esta venta ya tiene devoluciones: devuelve el importe que queda en vez de
anularla»; anulada desde otro dispositivo a la vez, «Esta venta ya está anulada». Un rechazo se lee
dentro de la ventana, que sigue abierta. Sin permiso no aparece «Anular».
Implicados: INVENTORY-F23, CUSTOMER-F21, INVOICE-F07

### SALE-F31 Devolver una venta (toda, una parte o por otro medio)
Estado: hecho
Vertical: común
Actor: responsable
Pantalla: Devolver
Pasos:
1. En **Ventas**, en una venta Completada (también con factura), pulsa «Devolver».
2. «Devolver la venta <número>» enseña una tarjeta por cada forma en que se pagó: «Cobrado», «Ya
   devuelto» y «Devolvible», con una propuesta de devolución total ya repartida («Devolver todo» la
   repone).
3. Si el cliente devuelve artículos, márcalos en «Qué se devuelve»: el importe se propone solo (la
   parte de cada línea marcada, sin pasar de lo que queda). Con dos o más unidades por devolver, sale
   «Unidades que vuelven» para elegir cuántas. Una línea de la que ya volvió una parte dice «<n> de
   <m> ya devueltas»; la que ya volvió entera sale como «Ya devuelta». Sin marcar nada solo se
   devuelve dinero.
4. Cambia el «Importe a devolver» de cada forma si solo vuelve una parte. Si el medio original ya no
   está disponible, elige otro en «Devolver por».
5. Escribe el «Motivo» y pulsa «Devolver <importe>».
6. Sale «Devolución registrada.»; si ya no queda nada por devolver, la venta pasa a Devuelta; si
   queda, la fila dice «Por devolver <importe>».
Entra: lo cobrado y lo ya devuelto por cada forma de pago; las líneas de la venta y las que ya
volvieron.
Sale: el documento de devolución con una fila por forma de pago, las líneas que vuelven con sus
unidades, su motivo y quién la hizo (avisa: venta devuelta, con las líneas devueltas y si queda
devuelta del todo) y, con Facturación, su rectificativa en la misma devolución (R5 de un tique, R1 de
una factura; por diferencias, o lo que queda si cierra la venta: INVOICE-F09, F10).
Si falla: «<medio>: <importe> es más que los <importe> que quedan por devolver.», «<medio>: elige por
dónde vuelve este dinero.», «Una devolución necesita un motivo.», «No queda dinero por devolver en
esta venta.». Si otra devolución se lleva a la vez lo último de una línea marcada: «Una de las líneas
marcadas ya se devolvió en otra devolución. Vuelve a abrir la devolución para ver lo que queda.». Si
el hub no contesta, repetir con la misma clave no devuelve dos veces.
Implicados: INVENTORY-F24, CUSTOMER-F22, INVOICE-F09, INVOICE-F10
Clientes resta lo devuelto del gasto de la ficha al oír «venta devuelta» (CUSTOMER-F22) e Inventario
repone las unidades que vuelven (INVENTORY-F24), una vez por devolución.

### SALE-F32 Devolver la sesión de un bono
Estado: hecho
Vertical: peluquería
Actor: responsable
Pantalla: Devolver, Anular venta
Pasos:
1. En **Ventas**, pulsa «Devolver» en una venta con líneas pagadas con bono (sale también en una
   pagada entera con bono, a 0,00 €, mientras le quede una sesión por devolver).
2. En «Qué se devuelve», la línea pagada con bono dice «Ya pagado · <bono>». Márcala: «La sesión
   vuelve a <bono>.».
3. Escribe el «Motivo» y pulsa el botón: con dinero, «Devolver <importe>»; solo la sesión, «Devolver
   la sesión».
4. Anular la venta (SALE-F30) devuelve también todas sus sesiones.
Entra: las líneas de la venta pagadas con bono y lo que ya volvió de cada una.
Sale: la devolución (avisa: venta devuelta) y la sesión de vuelta en su bono en la misma operación
(SERVICE-F26, SERVICE-F27). La venta pasa a Devuelta cuando vuelven todo el dinero y todas sus
sesiones.
Si falla: «Una devolución tiene que devolver dinero o la sesión de un bono.»; una sesión ya devuelta,
«Una de las líneas marcadas ya se devolvió…». Queda fuera hasta la fase 2 (activación por hub): si Servicios
no está activa, la devolución o la anulación de una venta con sesiones se rechaza («Servicios no está
activa en este negocio…»); hoy la plataforma no apaga apps por hub y ese camino solo se prueba en los
tests.
Implicados: SERVICE-F26, SERVICE-F27

### SALE-F33 Unir las ventas de dos fichas de cliente
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Clientes, alguien une dos fichas de la misma persona (CUSTOMER-F13).
2. Las ventas de la ficha absorbida pasan a la que queda, en cualquier estado.
Entra: la ficha absorbida y la que queda (avisa Clientes: fichas unidas).
Sale: el vínculo de las ventas con la ficha; el nombre impreso, el número y los importes no cambian.
Si falla: no hay pantalla; repetirlo no cambia nada.
Implicados: CUSTOMER-F13

### SALE-F34 Ajustar el TPV
Estado: hecho
Vertical: común
Actor: responsable, administrador
Pantalla: Ajustes
Pasos:
1. Abre **Ventas / TPV → Ajustes**; arriba se lee «TPV».
2. Cambia lo que necesites: «Permitir efectivo», «Permitir tarjeta», «Permitir transferencia»,
   «Mostrar productos en el TPV», «Mostrar servicios en el TPV», «Exigir cliente en cada venta»,
   «Permitir descuentos», «Descuento máximo que puede aplicar solo quien cobra, por descuento (%)»,
   «Permitir tiques aparcados», «Precios con IVA incluido», «Emitir factura si el cliente tiene NIF»,
   «Documento por defecto» («Tique» o «Factura»), «Cabecera del recibo», «Pie del recibo», «Imagen de
   pie (URL)», «URL del QR promocional» y «Texto del QR promocional».
3. Pulsa **Guardar**: sale «Ajustes guardados.».
Entra: nada de otras apps.
Sale: los ajustes del negocio (una fila). El servidor aplica al cobrar «Permitir efectivo / tarjeta /
transferencia», «Exigir cliente», «Permitir descuentos», el descuento máximo y los precios con IVA
incluido; el TPV lee el resto al abrirse.
Si falla: «No se pudieron guardar los ajustes.». Sin permiso, los campos se bloquean, no hay
«Guardar» y sale «No tienes permiso para cambiar estos ajustes. Pídeselo a un administrador si lo
necesitas.». Si se apagan todos los medios de pago que existen, el TPV y el servidor vuelven a
aceptar todos los medios activos.
Implicados: ninguno

### SALE-F35 Dar de alta y ordenar las secciones del precio libre
Estado: hecho
Vertical: común
Actor: responsable
Pantalla: Secciones
Pasos:
1. Abre **Ventas / TPV → Secciones**.
2. Pulsa **+**, escribe el Nombre («p. ej. Frutas y verduras»), elige «IVA que cobra» y la Posición.
3. Pulsa «Añadir». Para cambiarlo, toca «Editar», corrige y pulsa «Guardar»; para quitarlo,
   «Eliminar» y confirma.
4. En **Vender**, la baldosa «Precio libre» ofrece estas secciones en ese orden, con su IVA al
   lado. Con la lista vacía ofrece las categorías de IVA tal cual.
Entra: las categorías de IVA de Impuestos.
Sale: la sección (nombre, categoría de IVA, posición). Lo ya vendido conserva el nombre y el IVA
con que se cobró.
Si falla: una categoría de IVA que no existe se rechaza junto a su campo. Una sección que otro ya
borró: «Esa sección ya no está en este negocio. Recarga la lista y vuelve a intentarlo.».
Implicados: TAX-F01

### SALE-F36 Preparar las notas rápidas
Estado: hecho
Vertical: común
Actor: responsable
Pantalla: Notas rápidas
Pasos:
1. Abre **Ventas / TPV → Notas rápidas**.
2. Pulsa **+**, escribe la Nota (hasta 80 caracteres, p. ej. «sin sal») y la Posición.
3. Pulsa «Añadir». Para cambiarla, «Editar»; para quitarla, «Eliminar» y confirma.
4. En **Vender**, la hoja de la nota de una línea pinta estas notas como botones, en ese orden
   (SALE-F13).
Entra: nada de otras apps.
Sale: la nota rápida. Borrarla deja de ofrecerla; las notas ya escritas conservan su texto.
Si falla: «No se ha podido guardar la nota rápida.»; una nota que ya no existe: «Esa nota rápida ya
no está en este negocio. Recarga la lista y vuelve a intentarlo.».
Implicados: ninguno

### SALE-F37 Añadir un medio de pago (Bizum, transferencia…)
Estado: hecho — sin pantalla, como el producto actual (asistente o API)
Vertical: común
Actor: responsable, asistente
Pantalla: ninguna (asistente o API)
Pasos:
1. Pide al asistente que añada el medio y di de qué tipo es («añade Bizum como forma de pago, de tipo
   otro»): sin tipo se crea como efectivo.
2. El medio aparece en la hoja de cobro la próxima vez que se abre **Vender**.
Entra: el nombre del medio y su tipo (efectivo, tarjeta, transferencia u otro).
Sale: el medio de pago, activo. De fábrica el negocio tiene solo Efectivo y Tarjeta; «Permitir
transferencia» no ofrece nada mientras no exista un medio de tipo transferencia.
Si falla: un nombre repetido se rechaza: «Ya hay una forma de pago con ese nombre.».
Implicados: ninguno

### SALE-F38 Vender un servicio de Servicios
Estado: hecho
Vertical: peluquería
Actor: empleado, responsable
Pantalla: Vender
Pasos:
1. Con Servicios activa y «Mostrar servicios en el TPV» encendido, toca «Servicios» en la tira de
   categorías (o búscalo con la lupa).
2. Toca el servicio: entra como línea con su precio. Si no es de precio fijo («Desde», «Por hora»,
   «Variable», «Gratis»), se abre «Importe de <servicio>» con su precio como sugerencia: marca el
   importe y pulsa «Añadir <importe>».
3. Cobra como en SALE-F01; la línea lleva a la profesional como cualquier otra (SALE-F16).
4. **Precio de la profesional**: un servicio de precio fijo hecho por una profesional que tiene su
   propio precio en Servicios (Fresha, Phorest y Timely cobran el suyo) entra a ese precio; sin precio
   propio, al del servicio. El precio se fija al añadir la línea: cambiar después de profesional
   (SALE-F16) no lo cambia.
5. **Precio reservado**: la cuenta de una cita (SALE-F26) cobra cada servicio al precio con que se
   reservó, aunque hoy el catálogo diga otro (`booked_price`). Ventas lo comprueba con Citas: la cita
   existe y la ve quien cobra, no está cancelada, no se presentó ni está cobrada, es de la clienta de la
   venta y reservó ese servicio a ese precio (uno menor, solo quien puede vender a precio libre). Sin
   Citas en el negocio, un precio reservado es un precio libre: solo para quien tiene ese permiso. El
   precio reservado manda sobre el de la profesional.
Entra: los servicios en oferta, su tarifa, su mínimo y su máximo y su categoría fiscal, de Servicios;
el precio propio de la profesional (sus asignaciones, `service.assignment.list`); la cita y lo que
reservó, de Citas (`appointment.appointment.get`).
Sale: una línea de servicio con el servicio, su precio congelado y la categoría fiscal del servicio;
no mueve stock.
Si falla: un servicio sin categoría fiscal sale «Falta el IVA» y no entra («No se puede vender: sin
categoría fiscal. Falta configurar el IVA.»); uno archivado, «Ese servicio ya no se ofrece…»; un
importe fuera del mínimo y el máximo del servicio, «Ese importe está fuera de lo que admite el
servicio (<mínimo> – <máximo>).». Un precio reservado que no casa con la cita: «Ese no es el precio
que reservó la cita para este servicio: está cancelada, es de otra clienta, no reservó este servicio o
lo reservó más barato.» (409 en su campo). Sin Servicios activa, «Servicios» no sale en la tira.
Implicados: SERVICE-F09, SERVICE-F03, SERVICE-F05, APPOINTMENT-F17

## Qué comparten los verticales

| Pieza compartida | Flujos que la usan |
|---|---|
| El cobro: mismo precio del servidor, mismo IVA, mismos rechazos y el mismo aviso de venta cobrada que escuchan Inventario y Clientes | F01–F06, F22, F26 |
| La cuenta abierta y sus líneas: el precio se congela al añadir la línea; aparcar, recuperar y cita son la misma cuenta | F09–F18, F22–F24, F26 |
| La hoja **Cobro**: medios, teclado, tique o factura, datos del cliente | F01–F05, F22 |
| La marca de líneas: sirve para cobrar una parte y para dividir la cuenta | F22, F23 |
| El chip «Atiende» y el sello de la línea | F16, F20, F26 |
| La anulación de una venta: un solo aviso, y cada app que reacciona decide su efecto | F30 |
| Los ajustes del TPV: los mismos para los dos negocios | F34 y todos los de cobro |

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia
persona) y la API, con las mismas reglas y los mismos permisos. Pensado para la voz: un producto se
nombra por su id, su SKU o su nombre; un cliente por su id, su nombre, su teléfono o su email; una
venta por su id o su número; una sección o una nota rápida por su id o su nombre; un medio de
pago por su id, su nombre o su tipo («efectivo», «tarjeta»). Si un nombre casa con varios, se rechaza
diciendo cuáles (409 `*_ambiguous`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las ventas, con búsqueda por número o cliente, filtros (estado, pago, cliente, profesional, días, total), orden y páginas (hasta 100); cada una dice si tiene algún documento fiscal pendiente | ver ventas | F28, F29 | `sale.sale.list` |
| Una venta entera: cabecera, líneas, cobros, desglose de IVA y lo devuelto | ver ventas | F29 | `sale.sale.get` |
| La venta grabada con una clave de intento de cobro | ver ventas | F06 | `sale.sale.by_idempotency_key` |
| Las cifras de un periodo de días del negocio, con el impuesto con que se declararon sus ventas (vacío si mezclan impuestos) | informes | F28 | `sale.sale.stats` |
| Lo vendido hoy y los tiques de hoy | informes | F28 | `sale.sale.today` |
| Lo vendido cada uno de los últimos 7 días | informes | F28 | `sale.sale.last_7_days` |
| Lo vendido por cada profesional en un periodo: bruto, base, impuesto, lo devuelto de sus líneas y lo que queda (sobre lo que va la comisión) | informes | F16, F28 | `sale.sale.by_staff` |
| Lo que cobraría una cuenta, o unas líneas, sin cobrar nada (total, base, IVA, descuentos, desglose y líneas) | ver ventas | F01, F21, F22 | `sale.checkout.preview` |
| Las cuentas abiertas (o de otro estado), con búsqueda por título y páginas | ver ventas | F17 | `sale.order.list` |
| Una cuenta con sus líneas sin cobrar | ver ventas | F17, F19 | `sale.order.get` |
| Los medios de pago activos, con los que permite hoy el negocio | ver medios de pago | F02, F03 | `sale.payment_method.list` |
| Los ajustes del TPV (para editarlos) | ajustes | F34 | `sale.settings.get` |
| Los ajustes que el TPV necesita para vender | ver ventas | F01–F05 | `sale.pos_settings.get` |
| Las secciones, en su orden, con su IVA de hoy | ver ventas | F09, F35 | `sale.department.list` |
| Las notas rápidas, en su orden | ver ventas | F13, F36 | `sale.quick_note.list` |
| El día del negocio de hoy | ver ventas | F28 | `sale.business_day.get` |
| Por cada cobro de una venta, lo devuelto y lo que queda, y por cada línea lo que ya volvió | ver ventas | F31 | `sale.refund.options` |
| Las devoluciones de una venta, con el estado y el número de su rectificativa | ver ventas | F31 | `sale.refund.list` |
| La devolución grabada con una clave | ver ventas | F31 | `sale.refund.by_idempotency_key` |

Las ventas, las cifras, las cuentas, la previsión del cobro, los medios de pago, los ajustes, las
secciones, las notas rápidas y lo devolvible se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Cobra una cuenta (entera o unas líneas) o unas líneas sueltas, con uno o varios medios; gasta las sesiones de sus líneas pagadas con bono; pide a Facturación su tique o su factura en el mismo cobro; en efectivo, solo con la caja abierta | cobrar | F01–F06, F08, F22, F26, F27 | `sale.sale.complete` |
| El mismo cobro, con un descuento por encima del máximo | descuento sin tope | F14 | `sale.sale.complete_over_limit` |
| Anula una venta cobrada con motivo (y devuelve sus sesiones de bono); con su rectificativa en la misma anulación (y antes su tique, si estaba pendiente) | anular | F30, F32 | `sale.sale.void` |
| Emite ahora los documentos fiscales de una venta que esperan («Emitir ahora»): su tique o factura y las rectificativas de su anulación y de sus devoluciones | cobrar (y el permiso de Facturación de cada documento) | F29 | `sale.sale.issue_documents` |
| Devuelve dinero de una venta por cobro, y las líneas que vuelven (las pagadas con bono devuelven su sesión); con su rectificativa en la misma devolución | devolver | F31, F32 | `sale.sale.refund` |
| Abre una cuenta, con o sin líneas (artículos, servicios —a su precio reservado o al de la profesional— o precio libre); la de una cita que ya tiene una abierta devuelve esa (`already`) | montar la cuenta | F01, F17, F26, F38 | `sale.order.open` |
| Añade un artículo del catálogo a una cuenta | montar la cuenta | F01, F10 | `sale.order.add_line` |
| Añade un servicio de Servicios a una cuenta | montar la cuenta | F38 | `sale.order.add_service_line` |
| Paga una línea de servicio con un bono de la clienta (reserva la sesión) | montar la cuenta y gastar sesiones | F27 | `sale.order.apply_voucher` |
| Deshace el bono de una línea (suelta la sesión) | montar la cuenta y gastar sesiones | F27 | `sale.order.remove_voucher` |
| Añade una línea a precio libre | precio libre | F09 | `sale.order.add_open_line` |
| Cambia la cantidad, la invitación o la nota de una línea | montar la cuenta | F01, F10, F13, F15 | `sale.order.update_line` |
| Cambia de quién es una línea | montar la cuenta | F16 | `sale.order.set_line_staff` |
| Separa una línea de N unidades en N líneas | montar la cuenta | F27 | `sale.order.split_line` |
| Quita una línea sin enviar | montar la cuenta | F01 | `sale.order.remove_line` |
| Anula una línea ya enviada a cocina, con motivo | anular | F20 | `sale.order.void_line` |
| Envía a cocina las líneas pendientes | montar la cuenta | F20 | `sale.order.fire` |
| Divide una cuenta | montar la cuenta | F23 | `sale.order.split` |
| Junta dos cuentas | montar la cuenta | F24 | `sale.order.merge` |
| Anula una cuenta abierta (una vacía, sin líneas vivas ni cobros, con solo montar la cuenta) | anular; vacía: montar la cuenta | F18 | `sale.order.void` |
| Pone el descuento de la cuenta (y su versión por encima del máximo) | montar la cuenta / descuento sin tope | F14 | `sale.order.set_discount`, `sale.order.set_discount_over_limit` |
| Pone el descuento de una línea (y su versión por encima del máximo) | montar la cuenta / descuento sin tope | F14 | `sale.order.set_line_discount`, `sale.order.set_line_discount_over_limit` |
| Pone el título de una cuenta (aparcar) | montar la cuenta | F17 | `sale.order.set_label` |
| Enlaza una cuenta a su cita | montar la cuenta | F26 | `sale.order.set_appointment` |
| Crea un medio de pago | crear medios de pago | F37 | `sale.payment_method.create` |
| Guarda los ajustes del TPV | ajustes | F34 | `sale.settings.update` |
| Crea, cambia y elimina secciones | ajustes | F35 | `sale.department.create`, `.update`, `.delete` |
| Crea, cambia y elimina notas rápidas | ajustes | F36 | `sale.quick_note.create`, `.update`, `.delete` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Venta cobrada | Cobrar | La venta, su número, cuenta, documento, importes en céntimos, moneda, momento, cliente y su copia fiscal, quién atendió, cita, cobros y líneas (producto o servicio, cantidad, si es servicio, si la pagó un bono, importes) | `sale.sale.completed` |
| Venta nacida de una cita | Cobrar una cuenta con cita | La venta, la cita, quién atendió y el total | `sale.sale.created_from_appointment` |
| Venta anulada | Anular | La venta, su número, motivo, quién y cuándo, total, cliente, cuenta y documento | `sale.sale.voided` |
| Venta devuelta | Devolver | La venta, la devolución, el importe, el motivo, si queda devuelta del todo, los cobros y las líneas devueltas | `sale.sale.refunded` |
| Ventas re-apuntadas | Unir fichas | La ficha que queda y la absorbida | `sale.sale.reassigned` |
| Venta con su documento | Un documento que no se pudo emitir en el cobro, la anulación o la devolución se emite después (reintento del cobro, «Emitir ahora» o la reacción de Facturación) | La venta, el documento, su número, la devolución (`refund_id`) o si es el de la anulación (`void`); uno por documento | `sale.sale.invoiced` |
| Cuenta abierta | Abrir o dividir | La cuenta | `sale.order.opened` |
| Cuenta cambiada | Cualquier cambio de líneas, descuentos o título | La cuenta | `sale.order.changed` |
| Comanda enviada | Enviar a cocina | La cuenta, su título, el canal, la ronda, quién atiende y las líneas con sus notas | `sale.order.fired` |
| Cuenta cerrada | Cobrar lo último de una cuenta | La cuenta | `sale.order.completed` |
| Cuenta anulada | Anular una cuenta abierta | La cuenta | `sale.order.voided` |
| Cuentas juntadas | Juntar | La absorbida y la que queda | `sale.order.merged` |
| Línea quitada | Quitar o anular una línea | La cuenta y la línea | `sale.order.line_removed` |
| Línea anulada | Anular una línea enviada | La cuenta, la línea y el motivo | `sale.order.line_voided` |
| Medio de pago, ajustes, sección, nota rápida | Crearlos o cambiarlos | Cuál | `sale.payment_method.created`, `sale.settings.updated`, `sale.department.*`, `sale.quick_note.*` |

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Fichas unidas (`customer.customer.merged`) | Clientes | Pasa las ventas de la ficha absorbida a la que queda (F33) | `sale.customer.reassign` |
| Documento emitido (`invoice.invoice.issued`) | Facturación | Enlaza por su origen (`source = {type, sale_id, refund_id, void}`) un documento que quedó pendiente: la rectificativa de una devolución vuelve a esa devolución, la de una anulación a la venta, el tique o la factura del cobro a la venta; lo demás (factura manual, F3 que sustituye, rectificativa de una factura) es de Facturación (F29) | `sale.sale.record_invoice` |

### Lo que necesita de otras apps

- **Impuestos** (requisito): la regla y el cálculo del IVA de cada línea al cobrar.
- **Clientes** (requisito): la ficha del cliente de la venta y su búsqueda por nombre o teléfono; el
  enlace de la cuenta con su cliente lo guarda Clientes (`customer.order.link`).
- **Inventario** (opcional): el catálogo de venta, el precio, la unidad y la categoría fiscal de cada
  artículo, leídos con sus propias consultas al añadir la línea.
- **Personal** (opcional): el equipo para el chip «Atiende».
- **Servicios** (opcional): sus servicios en oferta (`service.service.list_for_sale`, y
  `service.service.get` al añadir la línea), los bonos de la clienta para un servicio
  (`service.grant.tender_options`) y las sesiones de bono: las reserva, las suelta, las gasta y las
  devuelve llamando a sus operaciones por nombre (`service.session.hold`, `.release`, `.settle`,
  `.return`), con la sesión de quien vende y en la misma transacción; el precio propio de una
  profesional (`service.assignment.list`).
- **Facturación** (opcional): el tique (F2) o la factura (F1) de cada cobro, la rectificativa de cada
  anulación (R5) y de cada devolución (R1/R5), emitidos por sus operaciones por nombre
  (`invoice.invoice.create_from_sale`, `.rectify_from_void`, `.rectify_from_refund`) con la sesión de
  quien cobra y en la misma transacción.
- **Caja** (opcional): si se puede cobrar en efectivo ahora (`cash_register.session.current`), solo
  cuando el cobro lleva efectivo.
- **Mesas** (opcional): «Elegir mesa» del TPV (F19) habla con Mesas solo por el nombre de sus
  operaciones, desde la pantalla y con la sesión de quien atiende: `table.table.list` y
  `table.floor.status` (las mesas), `table.session.by_order` (la mesa de la cuenta), `table.session.open`
  con la cuenta en pantalla, `.restore` y `.park`. Sin Mesas activa no hay botón.
- **Citas** (opcional): la cita de una cuenta y lo que reservó, para cobrar su precio reservado
  (`appointment.appointment.get`).

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Inventario | Baja el stock al cobrarse una venta, lo repone al anularse y repone lo que vuelve en una devolución | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Clientes | Suma la compra a la ficha, la resta al anularse y resta lo devuelto | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Servicios | No reacciona a avisos: Ventas llama a sus operaciones de sesiones al montar, cobrar, anular y devolver | `service.session.*` |
| Facturación | Ventas le pide el documento en el mismo cobro, anulación o devolución; sus reacciones a los avisos lo emiten si entonces no pudo (INVOICE-F06) y lee la venta, sus líneas y sus devoluciones (la requiere) | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Caja | No reacciona a avisos: lee las ventas, anulaciones y devoluciones de cada turno (la requiere); Ventas le pregunta si la caja está abierta | `Sale`, `Refund`, `sale.order.list` |
| Citas | Marca cobrada la cita de una venta y lo deshace al anularla; abre la cuenta de una cita (`sale.order.open`) y la lleva al TPV por su dirección | `sale.sale.created_from_appointment`, `sale.sale.voided` |
| Mesas | Abre, retitula, divide y junta las cuentas de sus mesas y anula la vacía de una mesa que se cierra, por las operaciones de Ventas con la sesión de quien está en la sala; lee el estado de cada cuenta | `sale.order.open`, `.set_label`, `.split`, `.merge`, `.void` |
| VeriFactu, Cocina | Reaccionarán a los avisos cuando existan | los avisos de arriba |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver ventas, cuentas, ajustes del TPV, secciones y notas rápidas | sí | sí | sí | sí | `sale.view_sale` |
| Montar la cuenta (abrir, añadir, cambiar, quitar, dividir, juntar, enviar a cocina, descuento hasta el máximo) | sí | sí | sí | sí | `sale.add_sale` |
| Cobrar | sí | sí | sí | sí | `sale.take_payment` |
| Vender a precio libre | sí | sí | sí | no | `sale.sell_open_price` |
| Descuentos por encima del máximo | sí | sí | sí | no | `sale.discount_over_limit` |
| Anular ventas, cuentas abiertas con algo pedido o cobrado y líneas enviadas (una cuenta vacía la anula quien monta la cuenta) | sí | sí | sí | no | `sale.void_sale` |
| Devolver | sí | sí | sí | no | `sale.refund_sale` |
| Ver los medios de pago | sí | sí | sí | sí | `sale.view_paymentmethod` |
| Crear medios de pago | sí | sí | sí | no | `sale.add_paymentmethod` |
| Ver las cifras | sí | sí | sí | no | `sale.view_reports` |
| Ajustes, secciones y notas rápidas | sí | sí | sí | no | `sale.manage_settings` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado.

Lo que toca la sesión de un bono pide además el permiso de Servicios, porque es Servicios quien la
mueve con la sesión de quien vende: pagar una línea con bono, deshacerlo, quitar, anular o cobrar una
línea pagada con bono, «Gastar sesiones» (`service.redeem_package`, lo tienen los cuatro papeles); anular
o devolver una venta con sesiones, «Devolver sesiones de bono» (`service.return_session`: propietario,
administrador y responsable, los mismos que anulan y devuelven).

## Para quien lo mantiene

- Anatomía completa: `apps.py`, `models.py`, `migrations/` (`0002` siembra Efectivo y Tarjeta, con
  reverso), `schemas.py`, `pricing.py` (la valoración, sin ORM), `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un `tests/test_<fichero>.py`
  por fichero, más `tests/test_integration_*.py` con Impuestos, Clientes, Inventario, Servicios,
  Facturación, Caja y Citas reales.
- **`requires = ["tax", "customer"]`**. `Sale.customer` y `Department.tax_category` son claves
  ajenas. **Inventario no es requisito** (PLAN §20.5): la línea guarda una copia del producto (id como
  UUID sin clave ajena, nombre, SKU, unidad, precio, coste y categoría fiscal) y el producto se lee con
  las operaciones de Inventario (`inventory.product.get`, `inventory.unit.list`) al añadir la línea,
  con la sesión de quien vende. Inventario apagado → `sale.catalog_unavailable`; el precio libre sigue.
  El equipo de Personal y la cita son UUID opacos (`staff_id`, `appointment_id`).
- **Servicios no es requisito** (como Inventario): la línea de un servicio guarda una copia (id como
  UUID sin clave ajena, `service_id`, nombre, precio y categoría fiscal), leída con
  `service.service.get` al añadirla. Una línea pagada con bono guarda la sesión que la paga
  (`voucher_session_id`, `voucher_grant_id`, el nombre del bono y lo que le quedaba, y el plazo de la
  reserva), copiados a la línea de la venta. Servicios apagado o ausente (`UnknownOperation`,
  `app_inactive`) → `sale.services_unavailable`; quitar una línea o eliminar la cuenta sigue
  adelante y la sesión vuelve sola al cabo de un día.
- **Una línea pagada con bono vale 0** en la valoración (`pricing.LineIn.covered`): ni descuento ni
  invitación; su categoría fiscal cierra con base 0. Solo una línea de servicio, de una unidad y que no
  sea invitación (`sale.voucher_needs_one_unit`, `sale.line_not_coverable`); cambiar su cantidad, su
  invitación o su descuento se rechaza (`sale.line_covered_by_voucher`).
- **Devolver sin dinero**: una línea pagada con bono vuelve entera (`sale.refund_voucher_line_whole`: su
  sesión no se parte); una devolución puede no tener cobros si devuelve una línea pagada con bono
  (`Refund.total` ≥ 0, `sale.refund_nothing` si no devuelve nada); la venta pasa a Devuelta cuando ha
  vuelto todo el dinero y todas sus sesiones (`sessions_to_return` en la venta y en la lista).
- **Modelos**: `Order` (cuenta abierta: `open` → `completed` | `voided`, `version` que sube con cada
  cambio, descuento de la cuenta y quién lo autorizó) y `OrderLine` (fila de trabajo: precio
  congelado, unidad, ronda de cocina, venta que la cobró, anulación); `Sale` (cabecera fiscal:
  número, día del negocio, importes, documento, cliente, clave de intento), `SaleLine` (copia fiscal:
  categoría, tipo, país, región y regla de Impuestos), `SalePayment`, `SaleCounter` (uno por día del
  negocio); `Refund`, `RefundPayment`, `RefundLine`; `PaymentMethod`, `Settings` (una fila),
  `Department`, `QuickNote` (borrado lógico).
- **Un solo camino de cobro**: todo cobro sale de una cuenta. Una venta de mostrador (líneas sueltas
  por el asistente o la API) abre por dentro una cuenta con esas líneas, con las mismas reglas de
  precio, y la cobra en la misma transacción.
- **El precio lo decide el servidor**: el de un artículo sale de Inventario y se congela en la fila al
  añadirla; la cantidad tiene que encajar en el escalón de su unidad (`sale.quantity_off_grid`, nunca
  se redondea). El precio es por `price_quantity` de `pricing_unit`: importe = precio × (cantidad en la
  unidad del precio) ÷ `price_quantity`, una sola vez a mitad hacia arriba. Una línea libre lleva el
  importe que se teclea y la categoría de su sección (`Department`; o una categoría de Impuestos) y exige
  `sale.sell_open_price` por cualquier vía.
- **La valoración** (`pricing.py`, la misma para la previsión y el cobro) es la del producto actual:
  descuento efectivo de línea y de cuenta, `exacto = precio × (1 − ef) × cantidad`, importe a mitad
  hacia arriba; invitación a 0 (y su coste a `gift_total`); el importe fijo de la cuenta se reparte por
  peso (bruto con IVA incluido, base sin él) con resto mayor y empate a la línea anterior; y el cierre
  **una vez por clave fiscal**: cada categoría se resuelve a su regla con
  `apps.tax.queries.calculate_tax` (la vigente el día del negocio, en su país y su territorio fiscal de
  Impuestos → Ajustes, TAX-F11) y las líneas se
  agrupan por la clave de esa regla (impuesto, régimen, calificación, causa de exención y tipos de sus
  componentes: la `FiscalKey` de `apps/invoice/fiscal.py`); cada clave se cierra una sola vez sobre el
  dinero de todas sus líneas, sean de la categoría que sean, y se reparte entre ellas por peso **como
  lo hace Facturación** (`fiscal.close_charged`): con IVA incluido, la base de la clave por peso y la
  cuota de cada línea es su importe menos su base (con recargo, la cuota principal por peso y el último
  componente se lleva lo que queda); sin IVA incluido, la cuota de cada componente por peso sobre la
  base. Así cada línea de la venta declara la misma base y cuota que su línea de la factura
  (`SaleLine.net_amount == InvoiceLine.base_amount`). Cada línea guarda la regla de su propia categoría. Así cuadra cada fila (base +
  cuota = total) y cada entrada del desglose (`tax_breakdown`, una por clave y componente, con
  `tax_type`, `regime`, `qualification` y `exempt_reason`), y el tique y su factura declaran la misma
  base y cuota al céntimo (1,50 € de comida y 1,50 € de bebida al 10 %, IVA incluido: 2,73 + 0,27, no
  1,36 + 1,36). Sin regla: `sale.no_tax_rule`.
- **Concurrencia**: toda escritura sobre una cuenta bloquea antes su fila (`select_for_update`) y
  sube `version` (también pagar o deshacer un bono, que además bloquea la compra del bono en
  Servicios: dos cajas sobre la última sesión van en fila y la segunda recibe su motivo); el cobro bloquea la cuenta, comprueba que sigue abierta, que las líneas que cobra
  siguen vivas y sin cobrar y, si la pantalla manda `order_version`, que es la misma
  (`sale.order_changed`). Anular y devolver una venta bloquean su fila: gana el primero.
- **Borrar en el admin del Hub**: «Eliminar» de una cuenta abierta (su página y «Eliminar seleccionados»)
  bloquea antes las cuentas (`lock_orders`, por id), así que espera a la escritura en curso y se lleva lo
  que dejó (la línea añadida o partida, las líneas que trajo una unión) o responde «No se puede eliminar»
  si un cobro ya la cobró; las líneas que una división o una unión se llevó a otra cuenta siguen allí, y la
  escritura que llega después no la encuentra (`sale.order_not_found`). Unir dos cuentas las bloquea con
  el mismo `lock_orders`: nunca se esperan en círculo con «Eliminar seleccionados». «Eliminar» una sección o un
  método de pago bloquea antes sus filas (`lock_rows`, por id), y la escritura que los nombra (la línea de precio
  libre que se añade, abre una cuenta o va en un cobro de mostrador; el pago de un cobro; la devolución por otro
  método) los retiene con `FOR KEY SHARE` (`held`, también por id) antes de escribir lo que los apunta: el borrado
  espera y responde «No se puede eliminar», o la escritura que llega después recibe lo mismo que con una sección
  (422 en su campo) o un método (409) que no existen (`tests/test_concurrency.py`).
- **Numeración**: `SaleCounter` por día del negocio (zona horaria del Hub) con `UPDATE … RETURNING`
  (asignar `F("last") + 1` y guardar: Django devuelve el valor con `RETURNING`), en la transacción del
  cobro: un rechazo no gasta número y nunca hay huecos. `AAAAMMDD-NNNN`, cuatro cifras como mínimo
  (la 10.000 es `AAAAMMDD-10000`). Sin secuencias de Postgres.
- **Idempotencia**: la clave del intento es única; repetirla devuelve la venta grabada (`already`)
  sin avisos, siempre que sea el mismo cobro (misma cuenta y mismas líneas, o venta de mostrador); si no,
  409 `sale.idempotency_key_reused`. Dos intentos a la vez con la misma clave: sobre una cuenta, el
  segundo espera al bloqueo de la cuenta y, tras él, vuelve a buscar la clave y devuelve la venta del
  primero; en una venta de mostrador, la cuenta interna se crea lo primero con la clave
  (`Order.attempt_key`, única), así que el segundo espera ahí y devuelve la misma venta, sin gastar
  número. Igual en las devoluciones (tras bloquear la venta).
- **La cadena fiscal en la misma transacción** (CLAUDE.md «Fiscal»): `sale.sale.complete` pide a
  Facturación por nombre (`call_app`) su tique o su factura tras numerar la venta, con el aviso de venta
  cobrada como entrada (el destinatario solo en una factura); `sale.sale.void` pide
  `invoice.invoice.rectify_from_void` y `sale.sale.refund`, `invoice.invoice.rectify_from_refund`. Se
  emite SIEMPRE: F2 para un tique, F1 para una factura (INVOICE-F01, F02). La respuesta y la fila dicen
  `invoice_status`: `issued` (con `invoice_id`, `invoice_number`, `invoice_type`), `none` (una devolución
  sin dinero: nada que rectificar), `unavailable` (Facturación no está en el negocio: tique sin
  documento) o `pending` (Facturación rechazó ahora —sin emisor, sin permiso de quien cobra, importes
  que no cuadran—: su savepoint se deshace, incluido el número que la serie ya hubiera subido
  (`invoice.number_taken`), la venta sigue y queda en el log). Un error de programación (`LiveMisuse`)
  o cualquier excepción inesperada dentro de Facturación nunca se traga: deshace la escritura entera. En
  una **factura**, un `InvalidPayload` de Facturación (los datos del destinatario, que son la entrada
  de quien cobra) sale como 422 y no se cobra: nunca queda pendiente una factura que no se podría
  emitir. Un negocio que presenta en real y no puede hacer llegar sus registros a la AEAT (VeriFactu en
  producción sin ruta: `verifactu.live_option_unpaid`, `verifactu.representation_not_approved`,
  `verifactu.own_certificate_missing`, que Facturación deja pasar tal cual) rechaza la escritura misma con
  ese 409 y sus palabras: no se cobra, ni se devuelve, ni se anula (reglas de trabajo §15; el
  `enforce_fiscal_road` del Hub antiguo, HUB-1935). La venta guarda el número de su documento y el de la rectificativa de su anulación; la
  devolución, el de la suya; y una venta cobrada como factura, la **copia del destinatario** comprobada
  (`customer_tax_id`, `customer_address`, `customer_country`, `customer_id_type`, migración `0008`, con
  `db_default` por expand/contract), lo que declara un documento emitido después.
- **Salida de `pending` en la fase 1** (sin relay): (a) repetir el cobro con la misma clave vuelve a pedir
  el documento que espera (`_replay`, idempotente: Facturación emite uno por venta); (b) «Emitir ahora»
  (`sale.sale.issue_documents`, permiso de cobrar y, de cada documento, el de Facturación de quien lo
  pulsa) emite en orden todo lo que espera —el tique o factura, la R de la anulación, las R de las
  devoluciones— y un rechazo llega tal cual (nada se guarda); (c) anular o devolver una venta cuyo tique
  espera lo pide primero (la rectificativa lo necesita) y, si sigue sin poder, siguen las dos pendientes.
  La lista y la venta dicen `documents_pending`; cada devolución, su `invoice_status`. Cuando exista el
  relay, la reacción de Facturación (INVOICE-F06) los emite sola y `sale.sale.record_invoice` los
  enlaza por su `source` (`refund_id` → la devolución, `void` → la anulación, `type = sale` → el cobro).
- **El nombre del destinatario** es el fiscal: el que se escribe en la hoja o, de la ficha, su empresa
  si la tiene (`company_name`), si no la persona, como lo lee Facturación. El país, ISO 3166-1 alpha-2
  con `apps.customer.tax_ids.normalize_country` (la lista de Facturación; sin alias «UK»/«EL»), en la
  entrada (`CompleteIn`) y en el de la ficha de una factura: 422 `customer_country`.
- **El NIF del destinatario de una factura** se lee con `apps.customer.tax_ids` (python-stdnum), el de
  Clientes y Facturación: NIF/NIE/CIF y NIF-IVA europeo comprobados (y compactos); fuera de España,
  tipo de documento 02–07 obligatorio. 422 `invalid_field` en `customer_tax_id` o `customer_id_type`.
  Un tique no comprueba un NIF que no declara.
- **Caja abierta para el efectivo** (CASH_REGISTER-F04): con algún cobro en efectivo, antes de numerar,
  `cash_register.session.current` por nombre con la sesión de quien cobra; `required` y sin sesión →
  409 `sale.cash_register_closed`. Caja ausente, apagada o fallando (`OperationError`, error de base de
  datos) → se cobra y queda en el log. Los tests de Ventas venden como un negocio sin Caja (fixture
  `without_cash_register`); el bloqueo se prueba en `test_integration_cash_register.py`.
- **Precio de un servicio**: `booked_price` (comprobado contra la cita por nombre,
  `appointment.appointment.get`, 409 `sale.booked_price_mismatch`; sin cita o sin Citas, precio libre:
  403 sin `sale.sell_open_price`) manda sobre el precio propio de la profesional (asignación activa con
  `custom_price`, `service.assignment.list`), que manda sobre el del servicio; solo en servicios de
  precio fijo, porque los demás se teclean. La duración propia no entra en la venta.
- **Una cuenta abierta por cita**: restricción única parcial `sale_order_one_open_per_appointment`
  (`appointment_id` con `status = open` y `source = pos`); `sale.order.open` devuelve la abierta
  (`already`), también con dos a la vez (la segunda espera al índice y la lee); `set_appointment` sobre
  una cita con otra cuenta abierta → 409 `sale.appointment_check_open`.
- **Índices que lee Caja**: `sale_sale_voided_idx` (parcial, `voided_at` no nulo) y
  `sale_refund_created_idx` (migración `0005`, reversible).
- **Límites legales en España** (país del negocio, el de Impuestos: hoy `ES` para todos): nada en efectivo
  desde 1.000 € (100.000 céntimos), también repartido y también en una cuenta cobrada por partes (la
  operación es la cuenta entera: lo ya cobrado más lo que le queda, `operation_total` de la previsión); tique hasta 3.000 € con IVA (300.000), por
  encima solo factura.
- **El impuesto del territorio no es de Ventas** (TAX-F11; ronda 2026-10-17 de PLAN-HUB): lo publica solo
  `tax.settings.get` (`tax_kind`). Las pantallas lo nombran con `useTaxName()` de Impuestos
  (`apps/tax/frontend/composables/useTaxName.ts`) y el 409 `sale.tax_category_missing` con
  `TAX_KIND_NAMES` de `apps/tax/schemas.py`; Ventas no tiene operación propia que lo repita (la fachada
  `sale.sale.tax_kind` se borró, y `test_api.py` vigila que no vuelva). En los tests de la SPA, `mount-sale`
  carga el catálogo de Impuestos y `taxSettings(familia)` da la respuesta de `tax.settings.get`.
- **La cifra del impuesto de un periodo** (SALE-F28): `sale.sale.stats` devuelve `tax_kind`, de
  `declared_tax_kind()` en `queries.py`: los `tax_type` distintos de `Sale.tax_breakdown` de las ventas
  contadas (completadas y devueltas; las anuladas no), con `jsonb_array_elements` y `DISTINCT … LIMIT 2`.
  Una sola familia de territorio (`vat`, `igic`, `ipsi`) → esa; dos o más (cambio de territorio en el
  periodo, el recargo de equivalencia junto al IVA) o un impuesto que no es de territorio → `null`, y la
  cifra dice «Impuestos» (`sale.sales.kpis.taxes`); sin ventas → el del territorio (`business_tax_kind()`).
  Por eso la consulta viva sigue también a `tax.settings.updated`. `SalesKpis.vue` usa `useTaxName()` de
  Impuestos mientras las cifras no llegan, fallan o el periodo no tiene ventas.
- **Medios de pago**: los de fábrica (`cash`, `card`) guardan su nombre en inglés y se traducen al
  leerlos mientras no se renombren. Los ajustes «Permitir efectivo / tarjeta / transferencia» los
  aplica el servidor (si dejan sin ninguno, valen todos los activos).
- **Avisos**: cada escritura anota su aviso en el outbox, en su transacción. El de venta cobrada lleva
  lo que esperan las reacciones de Inventario (`inventory.stock.apply_sale`: `sale_id`, `items[]` con
  `product_id`, `quantity`, `is_service`, `components`) y de Clientes (`customer.purchase.record`:
  `customer_id`, `sale_id`, `total`, `currency`, `purchased_at`); el de anulada, lo de
  `inventory.stock.restore_sale` y `customer.purchase.void` (`sale_id`, `reason`). Hay tests que dan
  el aviso real a esas reacciones reales.
- **Administrador de Django**, solo en `hubs.erplora.com` (PLAN §17–§18). CRUD completo en lo abierto
  (formas de pago, ajustes, departamentos, notas rápidas, cuentas abiertas y sus líneas). Lo cobrado es
  documento fiscal (PLAN-HUB §3.2, ronda 2026-10-20): ventas, sus líneas y cobros, el contador del día,
  devoluciones y sus líneas y cobros se ven enteros, sin «Añadir» ni «Eliminar»; solo cambian las notas de
  la venta y de la devolución. Una venta se corrige con su anulación o sus devoluciones, como en caja
  (`tests/test_admin.py`). Lo que guarda no pasa por las operaciones ni deja aviso.
- **Asistente**: cada operación declara `ai` (descripción; en las escrituras, `risk`: `high` en cobrar,
  anular, devolver y descuentos) y cada campo de `schemas.py` su `description`.

### Decisiones de plataforma

- **Ids sin clave ajena hacia apps fuera de `requires`** (precedente PLAN §20.5, `product_id`): la venta
  guarda `invoice_id` de Facturación y la línea `service_id`, `voucher_session_id`, `staff_id` y la
  cuenta `appointment_id`, como UUID opacos; Ventas sigue sin requerir Facturación, Caja, Citas ni
  Servicios (Facturación y Caja requieren Ventas: sería un ciclo). **Llamadas por nombre** a
  Facturación (`invoice.invoice.create_from_sale`, `.rectify_from_void`, `.rectify_from_refund`), Caja
  (`cash_register.session.current`), Servicios (`service.service.*`, `service.session.*`,
  `service.assignment.list`) y Citas (`appointment.appointment.get`, validación del precio reservado),
  con la sesión de quien vende, su permiso y su app activa, por la única puerta `call_app`. Mesas (que
  requiere Ventas) solo desde la pantalla «Elegir mesa», también por el nombre de sus operaciones
  (`useLive`/`useCommand`), sin importar nada de `apps/table`. Todo señalado para una ronda nueva de
  PLAN-HUB (este WORKBOOK no edita los planes).

### Cambios frente al producto actual

1. **El permiso de precio libre se exige por cualquier vía**, también al abrir la cuenta o al cobrar
   líneas sueltas (antes solo lo pedía la puerta de la pantalla).
2. **El límite del tique (3.000 €) lo aplica el servidor**, no solo la pantalla.
3. **«Permitir efectivo / tarjeta / transferencia» los aplica el servidor** al cobrar.
4. **Una línea sin categoría fiscal se rechaza siempre**: ya no se acepta un tipo de IVA declarado por
   el cliente (era la salida de bonos y servicios sin categoría, que llegan con Servicios).
5. **«Ingresos» resta lo devuelto** y una venta devuelta entera ya no desaparece de las cifras: cuenta
   como tique con su ingreso neto (antes una devolución parcial no restaba y la total borraba la
   venta).
6. **Cobrar una cuenta comprueba su versión**: la pantalla manda la que leyó; cualquier cambio entre la
   previsión y el cobro lo rechaza (antes se comparaba línea a línea; el resultado para la persona es
   el mismo).
7. **Anular una cuenta ya cobrada se rechaza** (antes contestaba bien y avisaba igual); anularla dos
   veces no avisa la segunda.
8. **Los ajustes se guardan por campos** (lo que no se manda no cambia; antes lo que faltaba volvía al
   de fábrica).
9. **Un nombre repetido de medio de pago se rechaza** (antes nacían dos «Bizum»).
10. **Cada línea cobrada queda atada a su venta**, también en el cobro que cierra la cuenta.
11. **Referencias humanas**: producto por SKU o nombre, cliente por nombre o teléfono, venta por número,
    medio de pago por nombre o tipo, sección y nota por nombre (409 `*_ambiguous` si casan
    varios).
12. **El cajero** es un empleado: monta la cuenta y cobra.
13. **Las cifras del panel de inicio** (los widgets «Ventas hoy», «Tickets hoy», «Ventas últimos 7
    días», «Actividad reciente») no tienen dónde pintarse: el inicio del Hub es la rejilla de apps. Sus
    consultas existen (`sale.sale.today`, `sale.sale.last_7_days`, `sale.sale.list`).
14. **«Descuentos» de la venta cuenta todos los descuentos**, también los de línea (antes solo el de la
    cuenta); las invitaciones van aparte, a coste.
15. **El IVA se cierra una vez por clave fiscal** con el cálculo de Impuestos (antes, por perfil de
    tipos): dos categorías de la misma clave son un solo redondeo, el mismo que hace la factura; dos
    claves del mismo tipo (un 0 % sujeto y un exento) son dos filas.
16. **«Precios con IVA incluido»** (antes «… por defecto»): el servidor aplica el ajuste a toda venta;
    no hay elección por venta, así que «por defecto» ya no describía nada (contradicción entre la UI
    vieja y este manual, resuelta a favor del manual).
17. **El tique dice «Descuento de <importe>, ya aplicado…»** con todos los descuentos de la venta (de
    línea y de cuenta), porque la venta guarda uno solo (ver 14).
18. **El límite del efectivo cuenta la cuenta entera** en los cobros por partes (antes cada cobro iba
    por separado y se saltaba el límite partiendo la cuenta, sales#502).
19. **Una clave de intento repetida para otro cobro se rechaza** (antes devolvía la otra venta como si
    fuera la misma).
20. **Con «Repartir el cobro», el botón dice «Cobrar <importe> con <forma de pago>»** (antes decía «con
    tarjeta» también con Bizum o transferencia).
21. **El servidor comprueba el bono de una línea pagada con bono** (antes la daba por pagada si el cobro
    lo decía, sin preguntar a Servicios, sales#539): la marca la pone `sale.order.apply_voucher` tras
    reservar la sesión, vive en la línea de la cuenta (no en la pantalla) y el cobro gasta la sesión en
    la misma operación. Dividir o juntar cuentas lleva la sesión con su línea (sales#540).
22. **Se devuelve solo la sesión de un bono, sin dinero** (antes había que devolver algo de dinero a la
    vez, sales#512, y en un tique a 0,00 € no se podía, sales#531).
23. **Una línea pagada con bono no se cambia** (cantidad, invitación, descuento) sin deshacer antes el
    bono (antes la pantalla lo permitía y la sesión se quedaba cubriendo otra cosa).
24. **Cobrar a otra clienta que la del bono se rechaza** (antes la línea se cobraba a su precio y la
    sesión volvía al bono sin avisar).
25. **El documento fiscal nace en el mismo cobro** (antes, Facturación lo emitía al oír la venta): el
    tique, la factura y las rectificativas se numeran en la transacción de la venta, la anulación o la
    devolución, y el papel imprime su número.
26. **La caja cerrada no cobra en efectivo** y lo dice el propio cobro (antes, Caja tapaba la pantalla
    Vender): con tarjeta se sigue cobrando.
27. **Una venta con devoluciones, aunque sean sin dinero** (solo la sesión de un bono), ya no ofrece
    «Anular» (antes la fila lo ofrecía y el servidor lo rechazaba).
28. **Una cita tiene una sola cuenta abierta**: cobrarla dos veces vuelve a la misma.
29. **El servicio se cobra al precio de la profesional** o al reservado en la cita (antes, siempre al
    del catálogo).
30. **Una cuenta vacía la elimina quien monta cuentas** (antes pedía siempre el permiso de anular): un
    grupo que se va sin pedir no obliga a llamar a un responsable.
31. **La factura a una ficha con empresa sale a nombre de la empresa** (antes, con el nombre de la
    persona y el CIF de la empresa: un NombreRazon que no casaba con el NIF).
32. **El país del destinatario es un código ISO de verdad** (antes valían dos letras cualesquiera, y
    Facturación rechazaba después «UK»).
33. **Un documento fiscal pendiente se ve y se emite** («Documento pendiente», «Emitir ahora»; antes no
    había forma de saberlo ni de emitirlo hasta que llegara el relay).
34. **Cada línea declara la misma base que su línea de la factura** (antes la cuota se repartía por
    peso y la base salía de restar; Facturación reparte la base: el total cuadraba, la línea no).
35. **«Elegir mesa» busca en el servidor** en vez de las pestañas de zona del producto actual (cada
    baldosa dice su zona) y una mesa ocupada no se toca (antes abría su cuenta).
36. **Lo vendido por cada profesional resta lo devuelto** (ver 5), a quien vendió lo que vuelve (antes
    una devolución parcial no restaba y la total borraba la venta, así que la suma de las profesionales
    no cuadraba con los «Ingresos» del día).

### Lo que NO hace, a propósito

- No guarda mesas ni clientes en la cuenta: el enlace cuenta–cliente es de Clientes y el de
  cuenta–mesa, de Mesas (`table.session.by_order`).
- No numera facturas ni habla con la AEAT: se las pide a Facturación en el mismo cobro; la AEAT es de
  VeriFactu.
- No mueve stock ni cuadra la caja: Inventario al oír la venta; Caja lee las ventas de cada turno.
- No habla con el datáfono ni con la báscula.
- No tiene propinas, ni comensal por línea, ni cursos con retención.
- No reabre una venta cobrada ni cambia su tipo de documento.
- No reprecia una cuenta abierta: si el catálogo cambia, la cuenta conserva el precio con que se
  pidió.
- No edita, desactiva ni borra medios de pago (como el producto actual).

### Lo que queda fuera

- **Vender un bono en el TPV** (SERVICE-F14) y, con ello, concederlo al cobrar y anularlo al anular o
  devolver su venta (el aviso «se vendió en esta venta y se anulará con ella»): el TPV del producto
  actual no lo ofrecía (solo el asistente o la API, con el IVA que mandaba el cobro) y aquí toda línea
  necesita una categoría fiscal que un bono del catálogo no tiene. Mientras, se cobra a precio libre y
  se concede en Servicios.
- **El hueco de la devolución con el saldo del bono** («Quedan N sesiones · M tras esta devolución» y
  el aviso de bono caducado del producto actual): la línea dice qué bono recibe la sesión; el saldo se
  ve en **Bonos vendidos** de Servicios.
- **«Elegir mesa» en el TPV, lo que no entra** (F19): preguntar los comensales al sentar (se sientan
  con los de la reserva o las plazas de la mesa y se corrigen en Mesas, TABLE-F14); trasladar, fusionar
  y dividir desde el TPV (están en el plano de Mesas, TABLE-F15–F17; tocar otra mesa con la cuenta ya
  sentada devuelve «Esa cuenta ya está en la mesa N.»); abrir la cuenta de una mesa ocupada tocándola
  (se abre desde el plano, TABLE-F11, o desde **Cuentas abiertas**); y el icono relleno `grid` del botón
  con mesa (no está registrado en `packages/ui`: se pinta `grid-outline` en color).

### Dudas abiertas

1. Anular un tique ya remitido a la AEAT: lo decidió Facturación (INVOICE-F07): la anulación emite la
   rectificativa R5 del tique entero, en la misma operación; el registro de VeriFactu es de su app.
2. El PIN del encargado sobre el dispositivo del empleado (elevación) es de la plataforma; mientras,
   las acciones de responsable piden a un responsable (F09, F14, F18, F20, F30, F31).
3. El nombre legal y el NIF del emisor en el documento: el producto actual los leía del hub
   (`sales.business.get`); aquí la identidad fiscal del negocio vive en el SaaS y el Hub aún no la
   tiene, así que el tique pinta la «Cabecera del recibo» de los ajustes. El documento fiscal (con NIF del
   emisor, número de factura y QR) lo emitirá Facturación (F29).
