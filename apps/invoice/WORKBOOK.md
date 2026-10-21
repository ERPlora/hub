# Workbook — Facturación (app)
Prefijo: INVOICE
Alcance MVP: núcleo
Estado de la app: hecha (servidor y páginas); lo que depende de piezas que aún no existen lo dice cada flujo

> Manual de usuario y especificación de la app `invoice`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Facturación del producto actual
> (`modules-workspace/modules/invoice`, `origin/main` `a68c8ae`, v1.2.74) y de sus ficheros
> `workflow/*.md`. La app hace lo mismo y se ve igual; los números de flujo se conservan
> (`INVOICE-Fnn`) porque otras apps los citan. Las dudas abiertas del producto actual se han decidido
> con el mercado (sección «Decisiones») y lo que todavía depende de una pieza que no existe en esta
> plataforma lo dice su flujo en la línea `Estado:`.

## Para qué sirve y para quién

Facturación convierte cada venta cobrada en un **documento fiscal numerado** y lo guarda para siempre:
el **tique** (factura simplificada, F2) de cada cobro, la **factura completa** (F1) cuando el cliente da
su NIF, la **factura completa que sustituye a un tique** (F3) que ya se llevó el cliente, y la
**rectificativa** (R1–R5) cuando se devuelve dinero, se anula una venta o un documento estaba mal. Es
el eslabón entre Ventas y VeriFactu en la cadena fiscal española (venta → factura → registro VeriFactu
→ AEAT): aquí nace el número de serie que luego viaja a Hacienda. Sirve igual al restaurante y a la
peluquería: no hay nada propio de un vertical.

Quién la usa:

- El **empleado** consulta las facturas, las imprime, emite una factura a mano, pasa un tique a
  factura completa y marca pagada una factura.
- El **responsable**, además, rectifica y lleva las series de numeración.
- El **propietario** y el **administrador**, además, configuran el **emisor** (la identidad fiscal del
  negocio que sale en cada factura).
- El **sistema**, sin nadie delante, factura cada cobro y rectifica cada devolución y cada anulación.

No cobra ni devuelve dinero (eso es Ventas), no envía nada a la AEAT ni calcula la huella (eso es
VeriFactu) y no guarda la forma de pago.

## Referencia adoptada

Aquí manda la especificación oficial sobre el mercado:

- [RD 1619/2012 (Reglamento de facturación)](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696):
  factura completa (art. 6: número y serie, fecha de expedición y de operación si es distinta, nombre,
  NIF y domicilio de emisor y destinatario, descripción, base, tipo y cuota por tipo), simplificada
  (art. 7), sustitución del tique por factura completa, y rectificativa con su serie propia, la
  referencia a la factura que corrige y la corrección hecha (art. 15). Series correlativas, una aparte
  para las rectificativas, como recuerda la
  [AEAT](https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/presentacion-declaraciones-ayuda-tecnica/aplicacion-gratuita-verifactu-aeat/emision-facturas.html).
- [SIF / VERI*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html)
  (RD 1007/2023, Orden HAC/1177/2024): tipos F1, F2, F3 y R1–R5, rectificativa por diferencias
  (`TipoRectificativa` «I») con importes negativos, inmutabilidad del documento emitido.
- Numeración, contrastada con Odoo, Business Central, NetSuite, Sage 50, Holded, Lightspeed, Toast,
  Shopify, WooCommerce y Square: el número se asigna en la misma operación que guarda el documento,
  una serie por código y año que vuelve a 1 cada 1 de enero, plantilla de formato que se congela con el
  primer número, vista previa del siguiente número sin gastarlo, y la prueba de que no hay huecos.
- El tipo de rectificativa como en el `l10n_es_edi_verifactu` de Odoo: R5 para un tique, R1 («error
  fundado en derecho y art. 80 Uno, Dos y Seis LIVA», la devolución) por defecto en una factura
  completa, y R2–R4 a elegir al rectificar a mano.
- El número fiscal se gasta al **cobrar**, nunca al abrir la cuenta: la cuenta abierta y la precuenta
  no llevan número de serie.

## Antes de empezar

- Al activar Facturación se activan con ella **Ventas**, **Impuestos** y **Clientes** (las requiere).
  **VeriFactu** no se activa sola, pero en España hace falta para que cada factura llegue a la AEAT.
- **El emisor** (razón social, NIF y domicilio del negocio) es obligatorio: **sin él no se emite
  ningún documento** (Facturación → Emisor, INVOICE-F21); hasta entonces, **Facturas** y **Series** lo
  avisan arriba («Todavía no puedes facturar», con «Configurar»). Hoy la identidad fiscal del negocio vive en
  la cuenta de ERPlora (el SaaS); cuando el SaaS la mande en la foto del hub, el emisor se rellenará
  solo (INVOICE-F22) y la pantalla dirá que viene de la cuenta.
- **«Hoy» es la hora de Madrid** en la fase 1 (el Hub todavía no guarda la zona horaria del negocio):
  decide la fecha de cada documento y, con ella, el año de su serie. Un cobro a las 00:30 del 1 de enero
  numera en la serie del año nuevo.
- Las series se crean solas la primera vez que se usan en el año: «TICKET» (tiques, F2), «FACT»
  (facturas completas y sustitutivas, F1 y F3) y «RECT» (rectificativas, R1–R5), con el código como
  prefijo (`TICKET-2026-000001`). La de un año nuevo hereda el nombre, el prefijo y el formato de la del
  año anterior con el mismo código. La venta numera **siempre** en esas tres; una serie con otro código
  sirve para las facturas hechas a mano (INVOICE-F12).

Configuración inicial, paso a paso:

1. En **Facturación → Emisor**, escribe la razón social, el NIF y el domicilio del negocio y guarda.
2. Si quieres otro prefijo, otro formato o continuar la numeración de otro sistema, crea **antes de la
   primera venta del año** las series `TICKET` (Ticket F2), `FACT` (Factura F1) y `RECT` (Rectificativa
   R1) del año en curso con su «Siguiente número» (INVOICE-F12). Comprueba el «Siguiente número» al
   editarlas (INVOICE-F13).
3. Haz una venta de prueba y comprueba en **Facturación → Facturas** que aparece su tique con el número
   esperado (INVOICE-F01, INVOICE-F16).

## Pantallas

### Facturas
Menú **Facturación → Facturas**. Tabla paginada de 50 en 50 (vista de tabla o de tarjetas; en el móvil,
tarjetas con el número como título) con «Número», «Cliente», «Total», «Estado», «Fecha» y «Tipo»; cada
columna se ordena. Buscador «Buscar facturas…» (número, nombre o NIF del cliente) y filtros de «Estado»,
«Tipo», «Serie», «Origen», «Fecha» (entre dos días) y «Total» (entre dos importes). Sin ordenar, lo
último emitido sale arriba. Mientras el emisor no está configurado, arriba sale «Todavía no puedes
facturar» («No se podrá emitir ningún tique ni factura hasta que configures esto:», «Los datos de tu
negocio» y «Configurar», que abre **Emisor**). Por fila: «Ver» (también al pulsar la fila), «Marcar pagada» (solo en las
que están «Emitida» y no son rectificativas) y «Rectificar» (solo en las que no son rectificativas, no
están canceladas ni sustituidas). El botón **+** abre «Nueva factura manual» (INVOICE-F03); sin permiso
de emitir no aparece, ni tampoco «Marcar pagada». La lista se pone al día sola cuando se emite, se
rectifica o se paga una factura en cualquier dispositivo.
Vacía: «Aún no hay facturas.». Cargando: «Cargando…». Error: el mensaje con «Reintentar». Un rechazo de
una acción de fila sale como aviso encima de la tabla.

### Ficha de factura
Se abre desde una fila de **Facturas** (`/invoice/invoices/<id>`). Arriba, «Factura {número}» con la
etiqueta de estado y los botones «Imprimir / PDF» y «← Volver». Si es una factura completa o una
rectificativa de una factura completa sin NIF del cliente, el aviso «Esta factura no tiene el NIF del
cliente: la impresora de tiques no puede sacarla como factura completa.». Debajo, «Tipo», «Serie»,
«Fecha de emisión», «Fecha de operación» (si es otra), «Cliente», «NIF cliente», «Dirección», «Emisor»,
«Origen» («Venta del TPV», «Alta manual», «Sustituye a una factura simplificada», «Rectificación»,
«Devolución de la venta», «Anulación de la venta»), «Venta» (su número), «Rectifica a» (el número de la
original, que la abre), «Sustituye a» / «Sustituida por» (enlaces), «Rectificativas» (las que la
corrigen), «Pagada el» y «Notas». Las líneas: «#», «Descripción», «Cant.», «Precio», el tipo con el
nombre del impuesto que declara la factura («IVA %», «IGIC %» o «IPSI %»; «Imp. %» si mezcla impuestos),
«Base», «Impuesto», «Total» (en el móvil, cada línea en bloque); sin líneas, «Sin líneas de detalle.». El
desglose por tipo («IVA 21 %», «Recargo de equivalencia 5,2 %», «Exento (E1)», «No sujeto»,
«Inversión del sujeto pasivo») con su base y su cuota, y los totales «Base», «Impuestos» y «Total». Los
botones «Marcar pagada», «Rectificar» y «Factura completa» (solo en un tique que no se ha sustituido)
con la misma regla que en la fila. Un rechazo sale justo encima de esos botones. Con **VeriFactu** activa y
permiso para ver sus registros, debajo, la tarjeta «Justificante VeriFactu»: el estado del registro en la AEAT
(«Pendiente», «Enviado, sin respuesta», «Aceptado», «Aceptado con errores» o «Rechazado»; «Pruebas (AEAT de
pruebas)» si es del entorno de pruebas), el «CSV» cuando la AEAT ya contestó, el QR y «Validar en la Agencia
Tributaria ↗». Sin VeriFactu, sin registro todavía o sin permiso, no sale la tarjeta.
Error al abrir: «Factura no encontrada» o el mensaje del fallo, con «← Volver».

### Rectificar
Ventana que abre «Rectificar», desde la fila o desde la ficha. Título «Rectificar {número}», la nota
«Se emitirá una rectificativa (serie RECT) con los importes negados y la factura original quedará
cancelada. Esta operación no se puede deshacer.», el «Tipo de rectificativa» (R1 a R4; en un tique,
siempre R5, sin elegir), el campo «Motivo» (obligatorio), «Emitir rectificativa» («Rectificando…»
mientras va) y «Cancelar». Tres finales dentro de la misma ventana: el rechazo traducido, el documento
que no se puede rectificar («Una rectificativa no se puede rectificar.», «La factura ya está
cancelada.») y el resultado «Rectificativa {número} emitida. {original} queda cancelada.», cada uno con
«Cerrar».

### Factura completa (sustituir un tique)
Ventana que abre «Factura completa» en la ficha de un tique. Título «Factura completa del tique
{número}», el buscador de clientes de Clientes (rellena los datos) y «Nombre o razón social», «País»,
«Tipo de documento» (solo fuera de España), «NIF» y «Domicilio», todos obligatorios salvo el tipo.
«Emitir factura completa» y «Cancelar». Al emitir, la ventana se cierra y la ficha abre la F3 nueva.

### Nueva factura manual
Ventana con la «Serie» (las activas del año que emiten F1 o F2; de entrada, la predeterminada o FACT),
el buscador de clientes de Clientes, «Cliente», «NIF cliente», «Dirección», «País», «Notas» y las
líneas: «Descripción», «Cant.» (1 de entrada; admite decimales), «Precio» (sin impuesto, en euros) y el
tipo, con el nombre del impuesto del territorio fiscal del negocio: «IVA %» (21 de entrada), «IGIC %» en
Canarias o «IPSI %» en Ceuta y Melilla, que empiezan en el tipo general de su regla de Impuestos y vacíos
si el territorio aún no tiene regla de su impuesto. «+ Línea» añade otra y la cruz la quita. «Emitir
factura» («Emitiendo…» mientras va) está en gris hasta que cada línea tiene descripción, cantidad, precio
y tipo. Un rechazo sale encima de los botones, por campo cuando es de un campo.

### Series
Menú **Facturación → Series** (solo con permiso de llevar las series). La entrada «Cada serie define
el prefijo, el formato y el contador de la numeración por año y tipo de factura…» y una tabla con
«Código», «Nombre», «Tipo», «Año», «Prefijo», «Formato» (vacío se lee `PREFIX-YYYY-NNNNNN`), «Nº
actual», «Activa» y «Predet.»; buscador «Buscar código, nombre…». Por debajo de 1280 px abre en
tarjetas. **+** abre «Nueva serie de numeración»; «Editar» (o pulsar la fila) abre «Editar serie
{código}» (INVOICE-F12, INVOICE-F13). Sin emisor, el mismo aviso «Todavía no puedes facturar» que en
**Facturas**.
Vacía: «Aún no hay series. Crea la primera para numerar tus facturas.». Cargando: «Cargando series…».
Error: «No se pudieron cargar las series» con «Reintentar».

### Emisor
Menú **Facturación → Emisor**. «Razón social», «NIF», «Domicilio», «Código postal», «Ciudad»,
«Provincia» y «País», y «Guardar». Arriba, si aún no está completo, «Sin el emisor no se puede emitir
ninguna factura.»; si lo mandó la cuenta de ERPlora, «Datos recibidos de tu cuenta de ERPlora el
{fecha}.». Solo lo cambian el propietario y el administrador; el resto lo ve sin poder editar.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» (o «Cargando series…») mientras llega el primer resultado. |
| Vacío | «Aún no hay facturas.» / «Aún no hay series…» (o «Sin resultados» con búsqueda o filtro), con **+** si puede crear. |
| Error | El aviso de la tabla con «Reintentar»; un rechazo de una ventana sale dentro de ella, junto a su campo si es de un campo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva (`app_inactive`) | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| INVOICE-F01 | El tique (factura simplificada) que nace al cobrar | hecho — Ventas lo pide dentro del mismo cobro |
| INVOICE-F02 | La factura completa al cobrar a un cliente con NIF | hecho — Ventas lo pide dentro del mismo cobro |
| INVOICE-F03 | Emitir una factura a mano | hecho |
| INVOICE-F04 | El cliente pide la factura completa de su tique | servidor hecho; falta la página pública de la plataforma (`/p`) |
| INVOICE-F05 | Pasar un tique a factura completa desde el mostrador | hecho |
| INVOICE-F06 | Una venta cobrada que no se ha podido facturar | hecho |
| INVOICE-F07 | Anular una venta cobrada que ya tiene su tique | hecho — Ventas la pide dentro de la misma anulación |
| INVOICE-F08 | Rectificar una factura a mano | hecho |
| INVOICE-F09 | La rectificativa al devolver una venta entera | hecho — Ventas la pide dentro de la misma devolución |
| INVOICE-F10 | La rectificativa por diferencias al devolver parte de una venta | hecho — Ventas la pide dentro de la misma devolución |
| INVOICE-F11 | Numerar cada documento en su serie y su año | hecho |
| INVOICE-F12 | Crear una serie de numeración | hecho |
| INVOICE-F13 | Cambiar una serie | hecho |
| INVOICE-F14 | Saber si la numeración del año está preparada | servidor hecho; la tarea de Inicio es de la plataforma |
| INVOICE-F15 | Comprobar que la numeración no tiene huecos | hecho |
| INVOICE-F16 | Buscar una factura | hecho |
| INVOICE-F17 | Ver una factura | hecho |
| INVOICE-F18 | Imprimir o guardar en PDF una factura | hecho |
| INVOICE-F19 | Marcar una factura como pagada | hecho |
| INVOICE-F20 | Dar a otras apps la factura de una venta | hecho |
| INVOICE-F21 | Configurar el emisor | hecho |
| INVOICE-F22 | Recibir el emisor de la cuenta de ERPlora | servidor hecho; la foto del SaaS todavía no lleva el emisor |
| INVOICE-F23 | Emitir las facturas de ERPlora (hub de plataforma) | hecho (servidor; sin pantalla); en la fase 1 no se da de alta donde factura un negocio real |

### INVOICE-F01 El tique (factura simplificada) que nace al cobrar
<!-- origen: old:invoice/workflow/emision.md#invoice-f01 -->
Estado: hecho — Ventas lo pide dentro del mismo cobro
Actor: sistema
Pantalla: ninguna
Pasos:
1. El cajero cobra una venta en Ventas como tique, que es lo habitual en barra y en el salón.
2. Al cobrar, Ventas pide a Facturación su factura simplificada (F2), dentro del mismo cobro: sale en la
   serie «TICKET» del año, fechada el día del negocio, con la fecha de operación del cobro, las líneas de
   la venta y el cliente si la venta tenía uno. La factura nace **«Pagada»** (el dinero ya está en la
   caja), con la hora del cobro, y el tique de Ventas ya lleva su número.
3. La factura aparece en **Facturación → Facturas** como «Ticket», «Pagada», con «Origen» «Venta del
   TPV».
4. Se comprueba abriéndola: las líneas y el «Total» son los del tique de Ventas, al céntimo.
Entra: la venta cobrada de Ventas (`sale.sale.completed`), leída de la propia venta: sus líneas con
base y cuota ya calculadas, si los precios llevaban el IVA dentro, la regla fiscal congelada de cada
línea y el tipo de documento; el emisor configurado.
Sale: la F2 con su número, la descripción de la operación («Venta {número de la venta}», en español, la
lengua de la AEAT), sus líneas (cada una con su precio unitario sin IVA y antes de descuentos, y el
descuento aparte, sin IVA) y el desglose por clave fiscal (impuesto, régimen, calificación,
tipo y recargo), cerrado **una vez por clave**: lo cobrado no cambia ni un céntimo, pero con el IVA
incluido la base y la cuota de cada tipo se recalculan sobre el total cobrado de ese tipo (base por
división, cuota por diferencia) y se reparten a las líneas, que siguen sumando lo cobrado. Avisa
`invoice.invoice.issued`: VeriFactu crea su registro y Ventas podrá poner el número en su tique.
Si falla: pedir otra vez el documento de la misma venta no crea otro ni gasta número (una factura por
venta, también con dos peticiones a la vez): responde el que emitió el cobro. Si VeriFactu rechaza
su registro (no se podría declarar), no se emite el tique: el cobro queda con el documento «pendiente»,
el motivo a la vista y «Emitir ahora» en Ventas. Sin emisor
configurado, o si los importes no cuadran (una cuota que no corresponde a su tipo, una cuota en una
línea que no es sujeta), Facturación no escribe nada ni gasta número; Ventas cobra igualmente con el
documento «pendiente», a la vista, hasta «Emitir ahora» (INVOICE-F06). Una venta que
ya no existe no se factura. El techo de la simplificada (3.000 €) lo vigila Ventas al cobrar.
Implicados: SALE-F01, SALE-F04, TAX-F18, TAX-F19

### INVOICE-F02 La factura completa al cobrar a un cliente con NIF
<!-- origen: old:invoice/workflow/emision.md#invoice-f02 -->
Estado: hecho — Ventas lo pide dentro del mismo cobro
Actor: sistema
Pantalla: ninguna
Pasos:
1. El cajero cobra en Ventas eligiendo «Factura», con el nombre, el NIF y la dirección del cliente
   (Ventas no deja cobrar como factura sin los tres).
2. Al cobrar, Ventas pide la factura completa (F1), dentro del mismo cobro: sale en la serie «FACT» del
   año, con el nombre, el NIF, la dirección, el país y el tipo de documento del cliente copiados del
   cobro (o, si el cobro no los trae, de la ficha del cliente), y cada línea con su precio sin IVA y su
   descuento aparte (RD 1619/2012, art. 6.1.f).
3. Aparece en **Facturas** como «Factura», «Pagada», «Venta del TPV», y la ficha enseña «NIF cliente» y
   «Dirección».
Entra: la venta cobrada como factura (`sale.sale.completed` con tipo de documento factura) y los datos
fiscales del cliente que viajan en el aviso.
Sale: la F1 (avisa `invoice.invoice.issued`). Es una copia: editar después la ficha del cliente no la
cambia. Un cliente de fuera de España se declara por su país y su tipo de documento.
Si falla: como en INVOICE-F01. Sin nombre, NIF y dirección del cliente, «Una factura completa necesita
el nombre, el NIF y la dirección del cliente.» y no se emite nada. El destinatario se lee igual que en
cualquier otro documento: un NIF español que no valida, o un NIF extranjero
sin su tipo de documento, se rechaza bajo su campo (422) y no se emite nada. En un **tique** (F2) el
destinatario es opcional: si el NIF de la ficha o del cobro no valida, el tique sale igualmente con el
nombre y sin NIF (queda en el registro de la aplicación), para que nunca quede «pendiente» por eso.
Implicados: SALE-F04, CUSTOMER-F17

### INVOICE-F03 Emitir una factura a mano
<!-- origen: fi:modules/invoice#command-invoice-create-handler-wasm-create_invoice old:invoice/workflow/emision.md#invoice-f03 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Facturas, Nueva factura manual
Pasos:
1. En **Facturas**, pulsa **+**: se abre «Nueva factura manual».
2. Elige la «Serie» (las activas del año que emiten facturas, F1, o tiques, F2, y siempre «FACT» y «TICKET»
   aunque el año aún no las haya abierto; empieza en la predeterminada o en «FACT») y, si quieres, busca al
   cliente en Clientes: rellena nombre, NIF, dirección y país. Escribe o corrige «Cliente», «NIF
   cliente», «Dirección» y «Notas».
3. Rellena cada línea: «Descripción», «Cant.» (1 de entrada; hasta tres decimales), «Precio» sin impuesto
   y en euros, y el tipo, que lleva el nombre del impuesto del territorio fiscal del negocio: «IVA %» (21
   de entrada), «IGIC %» en Canarias o «IPSI %» en Ceuta y Melilla. Empieza en el tipo general de su regla
   de Impuestos (en Canarias, el de la regla de Canarias); si el territorio aún no tiene regla de su
   impuesto, está vacío: escríbelo tú. «+ Línea» añade otra, con el mismo tipo de entrada, y la cruz la
   quita.
4. Pulsa «Emitir factura»; está en gris hasta que cada línea tiene descripción, cantidad, precio y tipo. La
   ventana se cierra y la factura aparece en la lista con su número, «Emitida» y «Origen» «Alta manual».
Entra: lo que escribe la persona; el emisor configurado. Por la API o el asistente una línea puede
llevar además la categoría fiscal de Impuestos: entonces su tipo y su calificación son los de la regla
vigente hoy, no el tipo escrito. El tipo escrito es del impuesto del territorio fiscal del negocio
(Impuestos → Ajustes, TAX-F11): en Canarias se declara como IGIC y en Ceuta y Melilla como IPSI.
Sale: la factura (F1 en una serie de facturas, F2 en una de tiques) con el impuesto calculado encima del
precio, cerrado una vez por tipo y repartido entre las líneas por resto mayor (los conceptos suman el
total impreso), y como descripción de la operación sus conceptos («Curso de corte, Kit de tinte», hasta
500 caracteres); avisa `invoice.invoice.issued`.
Si falla: dentro de la ventana, encima de los botones: «Una factura completa necesita el nombre, el NIF
y la dirección del cliente.», «Ese NIF no es válido.» (bajo el campo), «Línea {n}: el precio no es un
importe…», una línea con precio que sale a 0,00, una serie inactiva, que no emite facturas o de otro
año («Esa serie numera otro año…»), un tique por encima del límite de Ventas («Por encima de 3.000,00 €
no se puede emitir un tique…», RD 1619/2012 art. 4), o la falta de emisor. No se emite nada ni se gasta
número, y lo escrito se conserva. Si no se puede leer el territorio fiscal, el tipo se llama «Imp. %», sale
vacío y avisa «No se pudo leer el territorio fiscal del negocio: escribe el tipo de cada línea.»; la
factura se emite igual, con el impuesto del territorio.
Implicados: TAX-F18, CUSTOMER-F17, TAX-F11

### INVOICE-F04 El cliente pide la factura completa de su tique
Estado: servidor hecho; falta la página pública de la plataforma (`/p`)
Actor: cliente
Pantalla: página pública de la plataforma (`/p`)
Pasos:
1. El tique que imprime Ventas lleva un código para pedir la factura.
2. El cliente lo abre en su móvil, sin iniciar sesión, y escribe sus datos fiscales.
3. Facturación emite la factura completa sustitutiva (F3), como en INVOICE-F05.
Entra: el tique (F2) y los datos que escribe el cliente.
Sale: la F3 (avisa `invoice.invoice.issued`).
Si falla: como en INVOICE-F05.
Pendiente: la página pública y el código del tique son de la plataforma (`/p`) y de Ventas; Facturación
ya ofrece la operación que la página llamará (`invoice.invoice.substitute`).
Implicados: SALE-F29

### INVOICE-F05 Pasar un tique a factura completa desde el mostrador
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ficha de factura, Factura completa
Pasos:
1. El cliente vuelve con su tique y pide la factura a su nombre.
2. En **Facturas**, busca el tique (por su número) y ábrelo.
3. Pulsa «Factura completa», busca al cliente o escribe sus datos (nombre, país, NIF y domicilio) y
   pulsa «Emitir factura completa».
4. Se abre la F3 nueva: «Factura», «Origen» «Sustituye a una factura simplificada» y «Sustituye a» con
   el número del tique; el tique dice «Sustituida por» con el de la F3.
Entra: el tique (F2) que se sustituye y los datos fiscales del cliente.
Sale: la F3 en la serie «FACT» del año, con las líneas y los importes del tique copiados al céntimo
(misma operación) y la misma fecha de operación; el tique no se toca. Si el tique estaba pagado, la F3
nace pagada. Avisa `invoice.invoice.issued`. Desde entonces, rectificar o devolver esa venta rectifica
la F3, no el tique.
Si falla: sin nombre, NIF o domicilio, rechazo; un NIF español que no es válido, «Ese NIF no es
válido.»; un documento que no es un tique, «Solo un tique (factura simplificada) se puede sustituir por
una factura completa.». Si el tique ya tiene su F3, responde con ella sin emitir otra ni gastar número.
Implicados: INVOICE-F04

### INVOICE-F06 Una venta cobrada que no se ha podido facturar
<!-- origen: old:invoice/workflow/emision.md#invoice-f06 wf:cadena-fiscal#rec_fiscal-f09 old-hub:HUB-F52 old-hub:HUB-F55 -->
Estado: hecho
Actor: sistema, empleado, responsable, administrador, asistente
Pantalla: ninguna
Pasos:
1. Una venta queda cobrada y Facturación no puede emitir su documento al cobrar: falta el emisor, quien
   cobra no puede emitir facturas o los importes no cuadran. Ventas cobra igualmente y deja su
   documento «pendiente»: en **Ventas** la venta lleva «Documento pendiente» y su documento avisa
   «Documento fiscal pendiente» encima del papel.
2. El hub lo vuelve a intentar solo, cada vez más espaciado (unos minutos en total, hasta 8 veces); un
   intento que falla no escribe nada ni gasta número. Si mientras tanto se arregla la causa (por ejemplo,
   se configura el emisor, INVOICE-F21), el siguiente intento emite el documento y la venta deja de estar
   pendiente.
3. Pasados los intentos, o sin esperar a ellos, quien arregla la causa pulsa «Emitir ahora» en esa venta:
   sale su documento y la venta deja de estar pendiente. Por la API o el asistente se pide igual, por el
   número de la venta, a Ventas o a Facturación: en los dos casos la venta lleva su documento en cuanto se
   emite.
4. Si todavía no se puede, «Emitir ahora» dice por qué y no cambia nada.
Entra: la venta que espera su documento.
Sale: lo de INVOICE-F01 o INVOICE-F02, fechado el día en que por fin se emite (la fecha de operación
sigue siendo la del cobro); la venta lleva su número desde ese mismo momento (avisa
`invoice.invoice.issued`).
Si falla: anular o devolver una venta cuyo documento espera lo pide antes, en la misma operación; si
sigue sin poder, la anulación o la devolución sigue adelante y los dos documentos quedan «pendientes»: el
hub los reintenta y «Emitir ahora» los emite en orden (INVOICE-F07, INVOICE-F09). Pedir a Facturación la
rectificativa de esa anulación o de esa devolución la deja también en Ventas al momento. Pedir otra vez un
documento que ya salió no emite otro ni gasta número.
Implicados: SALE-F01, SALE-F29

### INVOICE-F07 Anular una venta cobrada que ya tiene su tique
<!-- origen: old:invoice/workflow/emision.md#invoice-f07 -->
Estado: hecho — Ventas la pide dentro de la misma anulación
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien anula en Ventas una venta cobrada como tique, con su motivo (Ventas no deja anular una venta
   cobrada como factura ni una con devoluciones).
2. Al anular, Ventas pide la rectificativa del tique entero, dentro de la anulación: R5 (rectificativa de simplificada) en la
   serie «RECT» del año, en negativo, con el motivo de la anulación. Si el tique ya se había sustituido
   por una F3, rectifica la F3 (R1).
3. El tique pasa a «Cancelada»; la rectificativa sale con «Origen» «Anulación de la venta».
Entra: la anulación de la venta (`sale.sale.voided`), resuelta desde la propia venta.
Sale: la rectificativa y la original cancelada (avisa `invoice.invoice.issued` y
`invoice.invoice.rectified`); VeriFactu la registra. El aviso repetido no emite otra.
Si falla: si el tique de la venta aún espera, Ventas lo pide antes, en la misma anulación; si sigue sin
poder, la anulación sigue adelante y los dos quedan «pendientes», a la vista, hasta «Emitir ahora»
(INVOICE-F06).
Implicados: SALE-F30

### INVOICE-F08 Rectificar una factura a mano
Estado: hecho
Actor: responsable, administrador, asistente
Pantalla: Rectificar
Pasos:
1. En **Facturas** (fila) o en la ficha, pulsa «Rectificar» en una factura que no sea rectificativa ni
   esté cancelada o sustituida.
2. Elige el «Tipo de rectificativa» (R1 de entrada: error fundado en derecho y art. 80 Uno, Dos y Seis
   LIVA; R2 concurso; R3 deudas incobrables; R4 resto; un tique siempre R5), escribe el «Motivo» y pulsa
   «Emitir rectificativa» (un segundo clic no emite otra).
3. La ventana dice «Rectificativa {número} emitida. {original} queda cancelada.». Al cerrarla, la
   original sale «Cancelada» y la lista tiene una «Rectificativa» nueva fechada hoy, con los importes y
   las líneas de la original en negativo y la nota «Rectifica la factura {número}. Motivo: {motivo}».
Entra: la factura elegida, el tipo y el motivo. La fecha la pone el servidor: el día del negocio.
Sale: la rectificativa numerada en la serie «RECT» del año, con el emisor y el cliente de la original,
su desglose en negativo y sus líneas en negativo (la cantidad lleva el signo; el precio no); la
original pasa a «Cancelada» (avisa `invoice.invoice.issued` y `invoice.invoice.rectified`). No mueve
dinero ni caja. Si la original ya tenía rectificativas por diferencias (devoluciones parciales), esta
rectifica exactamente lo que queda, con una línea por clave fiscal a su propio tipo.
Si falla: dentro de la ventana, traducido. Una fecha que no es la de hoy (API o asistente): «Una
factura rectificativa lleva la fecha del día en que se emite…» y no se emite nada. Sobre una
rectificativa o una cancelada, la ventana solo dice por qué. Sobre un tique sustituido, «Este tique ya
se sustituyó por una factura completa: rectifica la factura completa.». Dos rectificaciones a la vez
de la misma factura: la segunda espera a la primera y se rechaza sin gastar número. Sin permiso no
aparece la acción.
Implicados: SALE-F31

### INVOICE-F09 La rectificativa al devolver una venta entera
<!-- origen: old:invoice/workflow/rectificacion.md#invoice-f09 -->
Estado: hecho — Ventas la pide dentro de la misma devolución
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien devuelve en Ventas una venta cobrada entera, de una vez.
2. Al devolver, Ventas pide la rectificativa, dentro de la devolución: la factura de esa venta entera en
   negativo, en la serie
   «RECT» del año, fechada el día del negocio, con las líneas de la original en negativo y el motivo de
   la devolución. R5 si la original es un tique; R1 si es una factura completa.
3. La original pasa a «Cancelada»; la rectificativa aparece en **Facturas** con «Origen» «Devolución de
   la venta» y «Rectifica a» la original.
Entra: la devolución de Ventas (`sale.sale.refunded`), leída del propio documento de devolución: la
venta, el importe y si cierra la venta. La factura original se busca por la venta (su F3 si el tique se
sustituyó), nunca por lo que diga el aviso.
Sale: la rectificativa y la original cancelada (avisa `invoice.invoice.issued` y
`invoice.invoice.rectified`).
Si falla: la misma devolución dos veces es un solo documento, un solo número. Si el documento de la
venta aún espera, Ventas lo pide antes, en la misma devolución; si sigue sin poder, la devolución sigue
adelante y los dos quedan «pendientes», a la vista, hasta «Emitir ahora» (INVOICE-F06).
Implicados: SALE-F31

### INVOICE-F10 La rectificativa por diferencias al devolver parte de una venta
<!-- origen: old:invoice/workflow/rectificacion.md#invoice-f10 -->
Estado: hecho — Ventas la pide dentro de la misma devolución
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien devuelve en Ventas una parte de una venta cobrada.
2. Al devolver, Ventas pide una rectificativa por diferencias por el importe devuelto: en negativo, en
   la serie «RECT» del año. Si volvieron artículos, el importe se reparte **solo entre sus claves
   fiscales** (devolver el champú al 21 % no toca el menú al 10 %); si solo volvió dinero, entre todas las
   claves en proporción. Lleva **una línea por clave**, a su propio tipo, con lo que volvió de esa clave
   («2 × Champú, 1 × Cera») o, sin artículos, el motivo. La original sigue «Pagada» o «Emitida».
3. Cada devolución siguiente emite la suya sobre lo que queda; la que cierra la venta se lleva
   exactamente lo que queda, y entonces la original pasa a «Cancelada».
4. Con la venta devuelta entera, la original y sus rectificativas suman cero al céntimo, tipo a tipo.
Entra: la devolución de Ventas (`sale.sale.refunded`), como en INVOICE-F09.
Sale: una rectificativa por documento de devolución; la original se cancela solo cuando queda a cero.
Si falla: la misma devolución dos veces es un solo documento, y nunca se rectifica más de lo que queda
de la original.
Implicados: SALE-F31

### INVOICE-F11 Numerar cada documento en su serie y su año
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada vez que se emite un documento (tique, factura, sustitutiva o rectificativa), Facturación toma
   la serie de su código y del año del día del negocio; si no existe, la crea en ese momento con el
   contador a 0, heredando nombre, prefijo y formato de la del año anterior con ese código (o, la
   primera vez, con el código como prefijo).
2. Sube el contador de esa serie en uno y escribe el número con el formato de la serie (sin formato,
   `TICKET-2026-000001`) en la misma operación que guarda el documento.
3. El 1 de enero, a la hora del negocio, el siguiente documento abre la serie del año nuevo y vuelve a 1
   (o al «Siguiente número» que se le haya fijado).
Entra: el código de serie que toca (TICKET para los tiques, FACT para las facturas completas y las
sustitutivas, RECT para las rectificativas; en el alta manual, la serie elegida) y el día del negocio.
Sale: el número del documento. El número entra en la huella encadenada de VeriFactu.
Si falla: si la emisión se rechaza o falla, no se guarda nada y el contador no sube: no queda hueco.
Dos cobros a la vez en la misma serie esperan uno al otro y reciben números seguidos; dos documentos de
la misma serie no pueden llevar el mismo número («Ese número ya existe en la serie…»: pasa si una serie
de otro año usa un formato sin el año).
Implicados: ninguno

### INVOICE-F12 Crear una serie de numeración
Estado: hecho
Actor: responsable, administrador
Pantalla: Series
Pasos:
1. En **Facturación → Series**, pulsa **+**: se abre «Nueva serie de numeración».
2. Escribe «Código» (mayúsculas, dígitos, guion o guion bajo), «Nombre», «Tipo de factura» (de F1 a R5),
   «Año» (de entrada, el del negocio), «Prefijo» (vacío = el código), si quieres «Formato del número»
   (marcadores `{prefix}`, `{code}`, `{year}`, `{seq}` y `{seq:01d}`…`{seq:09d}`; vacío es
   `PREFIX-YYYY-NNNNNN`) y «Siguiente número» (1 de entrada; otro para continuar la numeración de otro
   sistema). Elige «Activa» y «Serie predeterminada».
3. Pulsa «Crear serie». La ventana se cierra y la serie aparece con «Nº actual» uno menos que el
   siguiente número.
Entra: lo que escribe la persona.
Sale: la serie; si se marcó predeterminada, la que lo era ese año deja de serlo. Para que la usen las
ventas y las devoluciones, el código tiene que ser TICKET, FACT o RECT; con otro código, sirve para el
alta manual (si su tipo es F1 o F2).
Si falla: un código vacío o con otra forma, un formato sin el año o sin marcador de secuencia, con un
salto de línea, o un prefijo o formato con tildes o símbolos como º o ª, salen bajo su campo (el número
es el `NumSerieFactura` de VeriFactu: solo ASCII imprimible); unos números que con la secuencia más
ancha pasarían de 60 caracteres, «Los números de esta serie no cabrían en 60 caracteres…» bajo el
prefijo o el formato; un código que ya existe ese año, «Ya hay una serie con ese código ese año.».
Implicados: ninguno

### INVOICE-F13 Cambiar una serie
Estado: hecho
Actor: responsable, administrador
Pantalla: Series
Pasos:
1. En **Series**, pulsa «Editar» en la fila (o la fila entera): se abre «Editar serie {código}».
2. Cambia «Nombre», «Activa», «Serie predeterminada» y, mientras la serie no haya emitido nada,
   «Prefijo», «Formato del número» y «Siguiente número». «Código», «Tipo de factura» y «Año» están
   bloqueados.
3. Mira «Siguiente número»: es exactamente el número que llevará el próximo documento, calculado por el
   servidor sin gastarlo.
4. Pulsa «Guardar»; la ventana se cierra y la tabla se pone al día.
Entra: la serie elegida y los cambios.
Sale: la serie cambiada; los números ya emitidos no cambian. Una serie inactiva deja de ofrecerse (y se
rechaza) en el alta manual; las ventas siguen numerando en TICKET, FACT y RECT.
Si falla: con la serie ya usada, prefijo, formato y siguiente número están bloqueados y lo dice «Esta
serie ya ha emitido facturas, así que su prefijo, su formato y su siguiente número ya no se pueden
cambiar: el número forma parte de la cadena de VeriFactu. Crea una serie nueva si necesitas otros.».
Implicados: ninguno

### INVOICE-F14 Saber si la numeración del año está preparada
Estado: servidor hecho; la tarea de Inicio es de la plataforma
Actor: responsable, administrador, asistente
Pantalla: ninguna (la tarea de Inicio llegará con la plataforma)
Pasos:
1. Se pregunta (asistente, API o la futura tarea de Inicio) si la numeración del año está preparada.
2. La respuesta dice el año del negocio y cuántas series ordinarias (F1, F2, F3), de rectificativas
   (R1–R5) y predeterminadas tiene ese año, y si está preparada (al menos una ordinaria y una de
   rectificativas).
Entra: las series del año del negocio.
Sale: nada; solo se lee.
Si falla: nada que fallar; un negocio recién creado responde que no está preparada.
Pendiente: la tarea «Tu numeración de facturas» de Inicio es de la plataforma.
Implicados: ninguno

### INVOICE-F15 Comprobar que la numeración no tiene huecos
Estado: hecho
Actor: empleado, responsable, administrador, asistente
Pantalla: ninguna (asistente o API)
Pasos:
1. Pide al asistente si la numeración tiene huecos, o el libro de números de una serie.
2. Sin huecos, la respuesta es que no falta ninguno; con huecos, dice la serie, el año, el último número
   que sí está y cuántos faltan seguidos.
3. El libro dice qué número se dio a qué documento y cuándo.
Entra: los documentos emitidos.
Sale: nada; solo se lee.
Si falla: el libro es la propia factura (el número se asigna en la misma transacción que la guarda, así
que un número sin documento no puede existir). El hueco que se ve es el de un «Siguiente número» que se
saltó números, o uno que nunca se usó; antes del primer número de una serie no cuenta como hueco.
Implicados: ninguno

### INVOICE-F16 Buscar una factura
<!-- origen: fi:modules/invoice#navigation-web-components fi:modules/invoice#query-invoice-list old:invoice/workflow/consulta.md#invoice-f16 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Facturas
Pasos:
1. Abre **Facturación → Facturas**.
2. Escribe en «Buscar facturas…» un número, un nombre de cliente o un NIF; o filtra (estado, tipo,
   serie, origen, fecha, total); o pulsa una columna para ordenar.
3. La tabla enseña las que casan, de 50 en 50; lo último emitido, arriba.
4. Pulsa «Ver», o la fila, para abrirla (INVOICE-F17).
Entra: las facturas del hub.
Sale: nada; solo se lee.
Si falla: sin resultados, «Sin resultados»; con un error, el mensaje y «Reintentar». Un total que no
es un importe dice «Escribe un importe, como 12,50» bajo su campo, y una fecha final anterior a la
inicial, «La fecha final no puede ser anterior a la inicial.»; ninguno de los dos filtra.
Implicados: ninguno

### INVOICE-F17 Ver una factura
<!-- origen: fi:modules/invoice#query-invoice-get fi:modules/invoice#query-invoice-lines old:invoice/workflow/consulta.md#invoice-f17 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ficha de factura
Pasos:
1. En **Facturas**, abre la factura.
2. Lee la cabecera, las líneas (con su «Precio» sin IVA y antes de descuentos y, si alguna lo tiene, la
   columna «Dto.» con el descuento sin IVA), el desglose y los totales.
3. Con **VeriFactu**, lee debajo el «Justificante VeriFactu»: el estado del registro en la AEAT, su «CSV»
   cuando la AEAT ya contestó y el QR, que se puede escanear o abrir con «Validar en la Agencia Tributaria ↗».
4. «Rectifica a», «Sustituye a», «Sustituida por» y las rectificativas abren el documento enlazado.
5. «← Volver» regresa a la lista.
Entra: la factura y sus líneas y, con VeriFactu, su registro.
Sale: nada; solo se lee. La ficha se pone al día sola si mientras tanto se paga, se rectifica o la AEAT
contesta.
Si falla: «Factura no encontrada» o el motivo del fallo. Sin VeriFactu, sin registro todavía o sin permiso
para verlo, la ficha sale sin la tarjeta del justificante.
Implicados: VERIFACTU-F19

### INVOICE-F18 Imprimir o guardar en PDF una factura
<!-- origen: old:invoice/workflow/consulta.md#invoice-f18 qa:verticals/beauty/06-fiscal-and-printing -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ficha de factura
Pasos:
1. En la ficha, pulsa «Imprimir / PDF».
2. Con **Impresión** y una impresora del sistema activa con la función Recibo, la factura en A4 va a esa
   impresora, con el QR de VeriFactu si tiene su registro, y se lee «Enviado a <impresora>.»
   (PRINTING-F08).
3. Si no (sin Impresión encendida, sin impresora del sistema, o si no se pudo leer su registro de VeriFactu
   para esa impresora), se abre el diálogo de impresión del
   navegador con la factura en A4 (con VeriFactu, arriba el QR del registro con «QR tributario:» y
   «VERI*FACTU»; emisor, «Facturar a», líneas, desglose por tipo, totales y la nota de lo que rectifica),
   desde donde se puede guardar como PDF. Mientras llega el registro, «Imprimir / PDF» espera: el papel
   nunca sale sin su QR.
4. Siempre en el idioma de quien imprime. Un documento de una venta sale como «Copia» (el original fue
   el papel del cobro); uno emitido desde Facturación, como original.
Entra: la factura y sus líneas.
Sale: el papel; la factura no cambia. Cada pulsación, un papel.
Si falla: «No se pudo imprimir la factura», también si no se puede leer el registro de VeriFactu de una
factura que lo tiene (no se imprime sin su QR).
Implicados: PRINTING-F08, VERIFACTU-F19

### INVOICE-F19 Marcar una factura como pagada
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Facturas, Ficha de factura
Pasos:
1. En **Facturas** (fila) o en la ficha, pulsa «Marcar pagada» en una factura «Emitida».
2. Confirma en «¿Marcar {número} como pagada?» («El cobro se registra con la fecha y la hora de
   ahora.») con «Marcar pagada», o vuelve con «Cancelar».
3. La factura pasa a «Pagada» y la ficha enseña «Pagada el» con la fecha y la hora.
Entra: la factura elegida.
Sale: el estado «Pagada» y la fecha de pago (avisa `invoice.invoice.paid`). Ningún importe cambia y la
caja no se toca.
Si falla: si mientras tanto alguien la pagó o la rectificó, «Esta factura no se puede marcar como
pagada: solo se puede con una factura emitida que aún no esté pagada. No se ha cambiado nada.». Las
facturas que nacen de una venta ya nacen pagadas y una rectificativa no se paga: no ofrecen la acción.
Implicados: ninguno

### INVOICE-F20 Dar a otras apps la factura de una venta
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Otra app pregunta qué factura nació de una venta.
2. Facturación contesta con el documento vigente de la venta (su F3 si el tique se sustituyó): número,
   tipo, serie, fecha, emisor, cliente, total y estado.
Entra: la venta (su id o su número).
Sale: los datos de la factura; solo se lee.
Si falla: si la factura aún no existe, contesta que no hay.
Implicados: SALE-F29

### INVOICE-F21 Configurar el emisor
<!-- origen: old-hub:HUB_SHELL-F164 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Facturas, Series, Emisor
Pasos:
1. Abre **Facturación → Emisor**, o pulsa «Configurar» en el aviso «Todavía no puedes facturar» que sale
   arriba en **Facturas** y **Series** mientras no hay emisor.
2. Escribe «Razón social», «NIF», «Domicilio», «Código postal», «Ciudad», «Provincia» y elige el «País»
   (España de entrada).
3. Pulsa «Guardar»: sale «Emisor guardado.» y el aviso de **Facturas** y **Series** desaparece, también en
   los demás dispositivos.
Entra: lo que escribe la persona.
Sale: el emisor, que se copia en cada documento que se emita desde ahora (los ya emitidos no cambian);
avisa `invoice.issuer.updated`.
Si falla: sin razón social, NIF o domicilio, bajo su campo; un NIF español que no es válido, «Ese NIF no
es válido.».
Implicados: ninguno

### INVOICE-F22 Recibir el emisor de la cuenta de ERPlora
Estado: servidor hecho; la foto del SaaS todavía no lleva el emisor
Actor: sistema
Pantalla: Emisor
Pasos:
1. Cuando la cuenta de ERPlora (el SaaS) manda la foto del hub con la identidad fiscal del negocio, la
   plataforma se la entrega a Facturación con la versión de la foto.
2. Facturación guarda el emisor y la pantalla dice «Datos recibidos de tu cuenta de ERPlora el
   {fecha}.».
Entra: el bloque `issuer` de la foto (`legal_name`, `tax_id`, `address`, `postal_code`, `city`,
`province`, `country`) y su `version`.
Sale: el emisor (avisa `invoice.issuer.updated`). Una foto más vieja que la guardada se ignora.
Si falla: un emisor incompleto o con un NIF no válido se rechaza y queda el anterior.
Pendiente: la foto del SaaS todavía no lleva la identidad fiscal; el contrato está escrito abajo.
Implicados: ninguno

### INVOICE-F23 Emitir las facturas de ERPlora (hub de plataforma)
Estado: hecho (servidor; sin pantalla: nadie entra en el hub de plataforma)
Actor: sistema (la cuenta de ERPlora, el SaaS, por `/internal/platform/invoices`)
Pantalla: ninguna
Pasos:
1. Un cliente paga su suscripción en Stripe; el SaaS numera su factura (`ERP-2026-00123`, abonos en
   `ERPR`) y la manda al hub de plataforma de ERPlora con `POST /internal/platform/invoices`, firmada.
2. Facturación la emite tal cual llega, con el número y la fecha del SaaS (ninguna serie del Hub cuenta
   para ella), con ERPlora como emisor y el pagador de ese día como destinatario, y VeriFactu sella su
   registro en la misma transacción. Contesta `201 {"status": "issued", "qr", "error": null}`.
3. El SaaS pregunta después cómo va (`GET …/{id}`): `issued` mientras el registro va a la AEAT,
   `accepted`, `accepted_with_errors` o `rejected` cuando contesta (con su código y su mensaje).
4. El PDF (`GET …/{id}/pdf`) es el mismo A4 de INVOICE-F18 en el idioma del pagador, con el QR de
   VeriFactu («QR tributario:», «VERI*FACTU») solo cuando la AEAT ya lo aceptó, como el SaaS antiguo.
Entra: el cuerpo de `platform_payload()` del SaaS (`id`, `kind`, `series`, `number`, `issued_on`,
`rectification`, `currency`, `language`, céntimos, `tax_treatment`, `tax_country`, `tax_rate`,
`recipient`, `lines`, `rectifies`).
Sale: la factura con `platform_ref` = el `id` del SaaS (avisa `invoice.invoice.issued`; un abono, además,
`invoice.invoice.rectified`) y su registro de VeriFactu.
Si falla: la misma factura otra vez (o dos entregas a la vez) contesta lo que ya hay, sin escribir nada
(`200`); un abono de una factura que no llegó, 404 `invoice.platform_original_unknown`; más de 400 € sin
NIF, 409 `invoice.platform_recipient_required`; un cuerpo fuera de contrato, 422 con su código; un
rechazo de VeriFactu deshace la factura entera.
Implicados: VeriFactu (`verifactu.record.create`, `verifactu.record.by_invoice`, `verifactu.record.get`)

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia
persona) y la API, con las mismas reglas y los mismos permisos. Pensado para la voz: una factura se
nombra por su número (`FACT-2026-000012`), una venta por su número del día (`20261014-0003`), un
cliente por su nombre, su teléfono o su correo (como en Clientes) y una serie por su código.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las facturas, con búsqueda, filtros, orden y páginas (hasta 100) | ver | F16 | `invoice.invoice.list` |
| Una factura con sus líneas, desglose y enlaces, por su id o su número | ver | F17 | `invoice.invoice.get` |
| La factura vigente de una venta | ver | F20 | `invoice.invoice.by_source` |
| El documento imprimible (HTML A4) de una factura | ver | F18 | `invoice.invoice.document` |
| El tipo con que empieza una línea tecleada: el general del territorio, de su propia regla en Impuestos (vacío sin ella) | emitir | F03 | `invoice.invoice.line_defaults` |
| Las series, con búsqueda, filtros y páginas | ver | F12, F13 | `invoice.series.list` |
| El siguiente número de una serie, sin gastarlo | ver | F13 | `invoice.series.peek_next` |
| Si la numeración del año está preparada | ver | F14 | `invoice.numbering.status` |
| Los huecos de la numeración | ver | F15 | `invoice.numbering.gaps` |
| El libro de números entregados | ver | F15 | `invoice.numbering.allocations` |
| El emisor | ver | F21, F22 | `invoice.issuer.get` |
| Cómo va una factura de ERPlora (por el `id` del SaaS) | solo el sistema | F23 | `invoice.invoice.platform_status` |
| El A4 de una factura de ERPlora, en su idioma | solo el sistema | F23 | `invoice.invoice.platform_document` |
| Si el hub de plataforma puede emitir ahora | solo el sistema | F23 | `invoice.invoice.platform_health` |

Todas se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Emite una factura a mano | emitir | F03 | `invoice.invoice.create` |
| Emite la factura de una venta cobrada (también la reacción a su cobro) | emitir | F01, F02, F06 | `invoice.invoice.create_from_sale` |
| Sustituye un tique por una factura completa | emitir | F04, F05 | `invoice.invoice.substitute` |
| Marca pagada una factura emitida | emitir | F19 | `invoice.invoice.mark_paid` |
| Rectifica una factura | rectificar | F08 | `invoice.invoice.rectify` |
| Emite la rectificativa de una devolución (también la reacción a ella) | rectificar | F09, F10 | `invoice.invoice.rectify_from_refund` |
| Emite la rectificativa de una venta anulada (también la reacción a ella) | rectificar | F07 | `invoice.invoice.rectify_from_void` |
| Crea una serie | llevar las series | F12 | `invoice.series.create` |
| Cambia una serie | llevar las series | F13 | `invoice.series.update` |
| Guarda el emisor | configurar el emisor | F21 | `invoice.issuer.update` |
| Manda la página A4 de una factura a la cola de Impresión (o dice que no se encoló: la imprime el dispositivo) | ver | F18 | `invoice.invoice.print` |
| Guarda el emisor que manda la cuenta de ERPlora | solo el sistema | F22 | `invoice.issuer.sync` |
| Emite una factura de ERPlora con su registro de VeriFactu | solo el sistema | F23 | `invoice.invoice.issue_platform` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Documento emitido | Toda F1, F2, F3 y R1–R5 nueva | `invoice_id`, `number`, `series`, `invoice_type`, `total`, `source_type`, `sale_id`, `source` (`{type, sale_id, refund_id, void}`: de qué cobro, devolución o anulación de Ventas sale), `rectifies_id`, `substitutes_id` | `invoice.invoice.issued` |
| Factura rectificada | Una rectificativa corrige una factura | `invoice_id` (la original), `number`, `status`, `rectification_id`, `rectification_number`, `remaining` | `invoice.invoice.rectified` |
| Factura pagada | Marcar pagada | `invoice_id`, `number`, `paid_at` | `invoice.invoice.paid` |
| Serie nueva | Crear una serie | `id`, `code`, `year` | `invoice.series.created` |
| Serie cambiada | Cambiar una serie | `id`, `code`, `year`, `fields` | `invoice.series.updated` |
| Emisor cambiado | Guardar o recibir el emisor | `source` | `invoice.issuer.updated` |

Contrato del origen con Ventas: `source.type` es el `source_type` del documento (`sale`, `manual`,
`substitution`, `rectification`, `refund`, `void`); `source.sale_id` la venta de la que sale (también en
su F3 y en sus rectificativas), `source.refund_id` la devolución de una rectificativa por devolución y
`source.void` es `true` en la de una anulación. Con él `sale.sale.record_invoice` enlaza con su cobro, su
devolución o su anulación un documento que quedó «pendiente» y se emitió después: Facturación se lo pide
por nombre en la misma operación que lo emite (también con «Emitir ahora», la API, el asistente o un
reintento del hub), así que la venta y su documento cuadran al terminar; la reacción de Ventas a este aviso,
cuando le llega después, ya no cambia nada.

Qué refresca cada aviso: la lista, la ficha, la factura de una venta y el documento, con «emitido»,
«rectificada» y «pagada»; las series, el siguiente número, el estado de la numeración, los huecos y el
libro, con «emitido» y los de series; el emisor, con «emisor cambiado».

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Venta cobrada (`sale.sale.completed`) | Ventas | Emite su F2 o su F1 (F01, F02) | `invoice.invoice.create_from_sale` |
| Venta devuelta (`sale.sale.refunded`) | Ventas | Emite la rectificativa de la devolución (F09, F10) | `invoice.invoice.rectify_from_refund` |
| Venta anulada (`sale.sale.voided`) | Ventas | Emite la rectificativa del tique entero (F07) | `invoice.invoice.rectify_from_void` |

Cada reacción corre como el sistema, en su propia transacción, y es idempotente: una por venta, una
por devolución y una por anulación. El documento lo pide antes Ventas dentro de su cobro, su anulación o
su devolución; el reparto de avisos del hub le entrega después estos avisos y, si aquel quedó «pendiente»,
lo reintenta a los 2, 4, 8… segundos hasta 8 veces; pasado eso, sale con «Emitir ahora» (INVOICE-F06).

### Lo que necesita de otras apps

- **Ventas** (requisito): la venta, sus líneas, sus devoluciones y su anulación, leídas de sus filas; y
  `sale.sale.record_invoice`, por nombre y con el permiso de la plataforma, para dar a la venta, a su
  anulación o a su devolución el documento que esperaba (INVOICE-F06).
- **Impuestos** (requisito): la regla congelada en cada línea de la venta (impuesto, régimen,
  calificación, tipo y recargo) y, en el alta manual por categoría, la regla vigente hoy
  (`resolve_tax`, en el territorio fiscal del negocio); el impuesto de un territorio (`tax_kind_of`,
  `business_tax_kind`) para lo que no tiene regla: la línea con tipo tecleado (el territorio del negocio) y la
  de una venta cuya regla ya no existe (el territorio que la línea congeló al cobrarse); el redondeo a mitad
  hacia arriba (`round_half_up`). El nombre del impuesto del tipo de una línea tecleada («IVA %», «IGIC %»,
  «IPSI %») lo lee la pantalla de `tax.settings.get` (`tax_kind`, con `useTaxKind()` de Impuestos), la única
  fuente: `invoice.invoice.line_defaults` solo da el tipo general y no repite el impuesto (ronda 2026-10-17
  de PLAN-HUB). Lo ya emitido se rotula por lo que declaró (el impuesto de su desglose; «Imp. %» si mezcla),
  nunca por el territorio de hoy: la misma regla que la cifra de impuestos de Ventas (SALE-F28), que dice el
  impuesto de las ventas del periodo, «Impuestos» si mezclan, y el del territorio solo sin ventas.
- **Clientes** (requisito): la ficha del cliente (nombre o empresa, NIF, domicilio y país) que rellena
  los datos fiscales en el alta manual, en la sustitución y en la F1 de una venta que no los trae.
- **Impresión** (por nombre, sin requisito): `printing.job.create` con la página A4 de una factura para la
  impresora del sistema (F18), en un punto de guardado propio; sin Impresión encendida, sin impresora del
  sistema o si la rechaza, no se encola nada y la imprime el dispositivo.
- **VeriFactu** (por nombre, sin requisito): `verifactu.record.by_invoice`, el QR que lleva esa página A4.

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| VeriFactu | Registrar cada documento emitido y encadenar su huella | `invoice.invoice.issued` + la factura (requiere `invoice`) |
| VeriFactu | Su «Crear factura de prueba» | `invoice.invoice.create` |
| Ventas | Emitir el documento de su cobro, su anulación y su devolución, dentro de ellos | `invoice.invoice.create_from_sale`, `invoice.invoice.rectify_from_void`, `invoice.invoice.rectify_from_refund` |
| Ventas e Impresión | El emisor de sus papeles | `invoice.issuer.get` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver facturas, series, numeración y emisor; imprimir | sí | sí | sí | sí | `invoice.view_invoice` |
| Emitir a mano, facturar una venta, sustituir un tique, marcar pagada | sí | sí | sí | sí | `invoice.add_invoice` |
| Rectificar (a mano, por devolución y por anulación) | sí | sí | sí | no | `invoice.rectify_invoice` |
| Crear y cambiar series | sí | sí | sí | no | `invoice.manage_series` |
| Configurar el emisor | sí | sí | no | no | `invoice.manage_issuer` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).
Recibir el emisor del SaaS (`invoice.sync_issuer`) no es de ningún papel: solo del sistema.

## Para quien lo mantiene

- **Hub de plataforma** (INVOICE-F23; PLAN-SAAS §4; plan del bloque fiscal, tarea 4): el hub propio de
  ERPlora, el slug `PLATFORM_HUB_SLUG` (`erplora`, reservado en `live.slugs`: ningún negocio lo puede
  coger y el alta normal del SaaS no lo crea). Las cuatro puertas viven en `base/internal.py`
  (`/internal/platform/invoices`, `/health`, `/{id}`, `/{id}/pdf`) y llaman como sistema a
  `invoice.invoice.issue_platform`, `platform_status`, `platform_document` y `platform_health` (permiso
  `invoice.issue_platform`, sin rol ni ruta ninja). `platform.py` traduce el cuerpo del SaaS (puro):
  - **Tipo**: F1 con NIF del pagador; sin NIF, F2 hasta 400 € (RD 1619/2012 art. 4) y 409 por encima
    (`fiscal/invoice_type.py` del SaaS antiguo). Un abono es rectificativa por diferencias (`I`) con el
    tipo del SaaS (R1–R4), o R5 si rectifica una F2.
  - **Desglose** (ADR-0183 del SaaS antiguo, `fiscal/desglose.py`, validado contra la AEAT): `domestic` →
    sujeta S1 a su tipo; `oss` (régimen 17), `reverse_charge` y `not_subject` → no sujeta por
    localización (N2), y `exempt` → E1; todas sin tipo ni cuota (error 1237 de la AEAT), con el importe
    entero de la línea como base. Por eso en una venta OSS la cabecera de Facturación es base = total y
    cuota 0 (el IVA de otro Estado no lo recauda la AEAT); la nota del documento dice «IVA 19 % (DE)». No
    lleva el aviso «VAT included — customer VAT number could not be verified» del PDF antiguo (queda fuera).
  - **Notas**: el aviso que imprimía la factura antigua (inversión del sujeto pasivo, OSS, no sujeta), en
    el idioma del pagador.
  - **Número**: el del SaaS tal cual; `sequence` = sus últimas cifras; la serie `ERP`/`ERPR` del año nace
    con el formato del SaaS (`{prefix}-{year}-{seq:05d}`) y su contador no se usa. Dos entregas a la vez
    se ponen en cola en el bloqueo de esa serie y la segunda contesta lo de la primera (test con hilos);
    `platform_ref` es único en la base de datos.
  - **Entorno**: el registro va al entorno de la AEAT del despliegue (`ERPLORA_ENVIRONMENT=prod` →
    producción; `pre` → pruebas; `verifactu.queries.effective_environment`), y su interruptor está fijo
    (409 `verifactu.platform_fixed`).
  - **PDF**: `pdf.py` (WeasyPrint ≥ 66) imprime el A4 fuera de la transacción; solo lee `data:` (nada de
    red). La imagen lleva Pango, HarfBuzz y DejaVu, y la caché de Fontconfig en `/tmp`.
- **Alta del hub de plataforma**: `manage.py create_platform_hub` (ensayo; con `--execute` escribe),
  idempotente como el `ensure_platform_hub` del SaaS antiguo. En la fase 1 no hay registro de hubs ni
  BD por hub: le pone el emisor de ERPlora desde `PLATFORM_ISSUER_LEGAL_NAME`, `PLATFORM_ISSUER_TAX_ID`,
  `PLATFORM_ISSUER_ADDRESS`, `PLATFORM_ISSUER_POSTAL_CODE`, `PLATFORM_ISSUER_CITY`,
  `PLATFORM_ISSUER_PROVINCE` y `PLATFORM_ISSUER_COUNTRY` (por defecto, los datos de ERPLORA CLOUD SL del
  `seed_company_036` antiguo) y fija VeriFactu al entorno del despliegue
  (`verifactu.config.follow_deployment`). Nunca escribe encima de otro emisor (otra cadena). En AWS se
  lanza una vez por entorno como tarea ECS puntual con la definición del servicio `hub` y el comando
  `python manage.py create_platform_hub --execute` (primero sin `--execute` para ver lo que hará). En
  la fase 2 añade la fila del registro (`is_platform`) y su BD, como cualquier alta. ⚠️ **En la fase 1 hay
  una sola BD**: el emisor que pone sería el de todos los hosts, así que no se lanza en un despliegue donde
  factura un negocio real hasta que haya una BD por hub (PLAN-HUB §4, ronda 2026-10-15c).

- Anatomía completa: `apps.py`, `models.py` (`InvoiceSeries`, `Issuer`, `Invoice`, `InvoiceLine`),
  `migrations/`, `schemas.py`, `fiscal.py` (aritmética pura: cierre por clave fiscal, prorrateo,
  formato del número), `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`,
  `templates/invoice/invoice.html`, `locale/`, `frontend/` y un `tests/test_<fichero>.py` por fichero,
  más integración con Ventas y Clientes y concurrencia con hilos.
- **Numeración**: `InvoiceSeries.current_number` se sube con `UPDATE … RETURNING` (Django 6 refresca el
  campo asignado con `F()`) dentro de la transacción del documento: la fila queda bloqueada hasta el
  COMMIT, así que dos emisiones de la misma serie se ponen en cola y un rechazo deshace el número. Nunca
  secuencias de Postgres. Únicas en la base de datos: `(code, year)` de la serie, `(series, sequence)` y
  `(series_code, number)` del documento. Prefijo, formato y siguiente número se bloquean con el **primer
  documento** de la serie (`queries.series_started`), no con el contador: una serie que empieza en el 7
  para continuar otro sistema sigue editable hasta que numera (lo cazó el e2e de INVOICE-F12).
- **Una por**: una factura por venta (`sale` con origen `sale`), una rectificativa por devolución
  (`refund`), una por anulación (`sale` con origen `void`) y una F3 por tique (`substitutes`), todas
  como restricciones únicas. Además cada operación bloquea antes la fila que decide (la venta, o la
  factura original) para que la segunda entrega espere y conteste «ya estaba» sin gastar número.
- **Inmutable**: ninguna operación cambia importes, partes, número ni fechas de un documento emitido;
  solo `status` y `paid_at` (pagar, cancelar al rectificar entera). Se corrige con una rectificativa
  por diferencias (importes negativos, `rectification_kind = "I"`); nunca se borra.
- **Dinero**: céntimos enteros con signo (las R en negativo); `Decimal` y mitad hacia arriba
  (`apps.tax.queries.round_half_up`); cantidades con tres decimales, como Ventas.
- **El desglose** (`tax_breakdown`) es una lista, una entrada por clave fiscal, en orden estable:
  `{"tax", "regime", "qualification", "exempt_reason", "rate", "surcharge_rate", "base", "quota",
  "surcharge_quota"}` (sin recargo, `"surcharge_rate": "0.00"` y `"surcharge_quota": 0`); los tipos como
  texto con dos decimales. Lo que cobra una venta
  no se mueve: con el IVA incluido, la base de cada clave sale de dividir lo cobrado y la cuota por
  diferencia, y se reparte a las líneas por resto mayor; sin él, base y cuota son las de las líneas. En
  el alta manual la cuota se calcula una vez por clave sobre la suma de bases. La auditoría (cuota contra
  `base × tipo` con tolerancia de un céntimo por categoría de la clave; solo una clave sujeta lleva
  cuota; base + cuota = total; F nunca negativa) rechaza antes de numerar.
- **La rectificativa por diferencias** reparte el importe sobre lo que **queda** de cada clave (la
  original menos sus rectificativas vivas) por resto mayor, base por proporción y cuota por diferencia;
  si se lleva todo lo que queda de una clave, copia sus cifras tal cual. Entera, niega cabecera,
  desglose y líneas de la original.
- **Fechas**: `issue_date` es el día del negocio al emitir (Madrid en la fase 1); `operation_date`, el
  del cobro (`Sale.business_day`), el de la devolución o el de la anulación; la F3 conserva el del tique.
- **El emisor** (`Issuer`, una fila) se copia en cada documento. Contrato con el SaaS (pendiente de la
  foto): el bloque `issuer` de `PUT /internal/hubs/{id}/state` → la plataforma llama a
  `invoice.issuer.sync` como sistema con `{legal_name, tax_id, address, postal_code, city, province,
  country, version}`; una `version` menor o igual que la guardada se ignora.
- **Contrato con VeriFactu** (`apps/verifactu`, `requires=["invoice"]`; su WORKBOOK, «Contrato con
  Facturación»): `_issue`, tras escribir el documento y su aviso y **dentro de la misma transacción**, llama
  por nombre a `verifactu.record.create` con `{"invoice_id": …}` y la misma sesión, en su savepoint. La
  respuesta de la operación que emitió dice `verifactu_status`: `sealed` (registro sellado en el mismo
  commit), `unavailable` (VeriFactu no está en este negocio: operación desconocida o `app_inactive`; el
  documento sale sin registro) o `pending` (solo un error transitorio de la base de datos: el savepoint no
  deja nada, la factura sigue y la reacción de VeriFactu a `invoice.invoice.issued` lo sella después).
  **Un rechazo de VeriFactu** (409 `verifactu.impossible_record`, `invalid_record`, `recipient_required`, o
  403) es determinista —fallaría igual al reintentar— y el registro de alta se genera al expedir (RD
  1007/2023): **deshace la emisión entera** y la serie devuelve su número; el 409 llega tal cual a quien
  emitía. En un cobro, Ventas lo convierte en su documento «pendiente» con «Emitir ahora» y el motivo a la
  vista (el cobro no se pierde). Un `LiveMisuse` tampoco se traga. Leer la factura después no trae
  `verifactu_status` (el estado vivo es `verifactu.record.by_invoice`). VeriFactu lee la `Invoice` por su id. Lo que necesita está en la fila:
  `number` (NumSerieFactura), `series_code`, `issue_date` (FechaExpedicionFactura),
  `operation_date` (FechaOperacion, si es otra), `issuer_tax_id` / `issuer_name` (IDEmisorFactura,
  NombreRazonEmisor), `customer_tax_id` / `customer_name` / `customer_country` / `customer_id_type`
  (Destinatarios: NIF, o IDOtro con país y tipo 02–07), `invoice_type` (TipoFactura F1, F2, F3, R1–R5),
  `rectification_kind` («I»), `rectifies` → su `number` e `issue_date` (FacturasRectificadas),
  `substitutes` → su `number` e `issue_date` (FacturasSustituidas), `tax_breakdown` (Desglose:
  Impuesto, ClaveRegimen, CalificacionOperacion / OperacionExenta, TipoImpositivo, BaseImponible,
  CuotaRepercutida, TipoRecargoEquivalencia, CuotaRecargoEquivalencia), `tax_amount` (CuotaTotal),
  `total_amount` (ImporteTotal) y `description` (DescripcionOperacion, en **todos** los documentos:
  «Venta {número}» en los de una venta y su F3, los conceptos en una manual y el motivo en una R). El
  número cabe siempre en `NumSerieFactura` (≤ 60 caracteres ASCII imprimibles: se comprueba al crear o
  cambiar la serie con su secuencia más ancha, y el formato exige el año). El QR, la huella y la
  remisión son suyos; Facturación no los guarda ni los simula.
- **Límites del registro de VeriFactu** (`SuministroInformacion.xsd`): el nombre del cliente y el del
  emisor, como mucho 120 caracteres (`NombreRazon`, `TextMax120Type`); su NIF o documento, 20 (`IDOtro/ID`,
  `TextMax20Type`; un NIF español tiene 9); el número, 60 (`NumSerieFactura`); la descripción, 500. Las
  columnas, los esquemas y los campos de las pantallas los aplican (migración `0003`, reversible); un
  nombre de ficha más largo (la ficha admite 200) se rechaza bajo «customer_name» en una factura y en un
  tique sale sin nombre. La dirección no viaja en el registro: no tiene tope de la AEAT.
- **Precio unitario y descuento** (RD 1619/2012 art. 6.1.f): `InvoiceLine.unit_price` es el precio por
  unidad **sin IVA y antes de descuentos**, en céntimos con dos decimales (0,8264 €), y
  `discount_amount` el descuento sin IVA, con el signo de la línea; `quantity × unit_price −
  discount_amount` es la base, que es la cifra que cuenta. En las de una venta se calculan desde lo que
  la línea valía a su precio (`apps.sale.pricing`), sin IVA en la misma proporción en que se cobró; sin
  descuento, el precio es la base entre la cantidad. Una rectificativa por diferencias lleva una línea
  por clave con su base como precio.
- **Devoluciones con artículos**: el importe se reparte solo entre las claves de las líneas que vuelven
  (`sale_line` → su clave congelada, pesada por lo que se cobró de esa parte), sin pasar de lo que queda
  de cada clave; lo que sobre va a las demás. Sin artículos, a prorrata de lo que queda.
- **Destinatario**: una sola lectura para Ventas y Facturación en `apps/customer/tax_ids.py` (NIF, NIE,
  CIF y NIF-IVA de la UE con `python-stdnum`; un NIF extranjero exige su tipo 02–07, el `IDType` de
  `IDOtro`). `create_from_sale` la aplica igual que el alta manual (422 por campo).
- **Administrador de Django**: series y emisor con CRUD completo; una serie no cambia su código, año ni
  tipo una vez creada, ni su prefijo, formato y contador desde que numeró un documento; el NIF del
  emisor se valida como en la operación. Las facturas y sus líneas se ven enteras, con sus campos
  fiscales de solo lectura, sin alta ni borrado desde el admin (la ley obliga a conservarlas y el número
  solo lo da la operación); solo cambian las notas, y marcar pagada se hace con
  `invoice.invoice.mark_paid` (pantalla, API o asistente). Ids y fechas, siempre de solo lectura.
  **Ronda a escribir en PLAN §17**: CLAUDE.md dice «CRUD completo… fiscales incluidas»; aquí la ley
  manda solo lectura en lo emitido (decisión mantenida tras la revisión fiscal del 2026-10-14).
- **Reacciones**: Ventas llama a las mismas operaciones dentro de su cobro, devolución o anulación (un
  rechazo deshace solo su parte y la venta queda «pendiente»); `events.react(scope, name, payload)` las
  ejecuta como sistema cuando el relay del outbox (`base/relay.py`, en el worker desde hub#105) entrega el
  aviso: si el documento ya existe, responde el mismo sin gastar número; si se rechaza (sin emisor), el
  relay reintenta a 2, 4, 8… s y al octavo intento lo deja (`dead`), y queda «Emitir ahora»
  (`sale.sale.issue_documents`). Los tests entregan el aviso real del outbox (`deliver`) y
  `tests/test_relay.py` lo hace por el tick real del worker.
- **La venta sabe su documento en la misma transacción** (INVOICE-F06): `create_from_sale`,
  `rectify_from_void` y `rectify_from_refund` llaman a `sale.sale.record_invoice` (`_tell_sales`, contexto
  de quien pide más el permiso `sale.record_invoice` de la plataforma, como `apps/reservation`) cuando la
  fila de Ventas ya está escrita sin él: su estado fiscal (`invoice_status`, `void_invoice_status` o el de
  la devolución) no está vacío. Dentro del propio cobro, anulación o devolución ese estado aún está vacío y
  lo escribe Ventas con la respuesta. También en la rama «ya estaba» (repara una venta que una versión
  anterior dejó «pendiente» con su factura emitida). `record_invoice` solo escribe lo que no está
  «emitido» y avisa `sale.sale.invoiced` una vez por documento; «Emitir ahora» ya no lo escribe dos veces.
- **Validación del NIF**: `python-stdnum` (NIF, NIE y CIF de España; NIF-IVA de la UE con el tipo 02).
- **Asistente**: cada operación declara `ai` (en las escrituras, `risk`: `high` al emitir, sustituir,
  rectificar y en el emisor) y cada campo su `description`.

### Decisiones (dudas abiertas del producto actual, resueltas con el mercado)

1. **La factura de una venta nace «Pagada»** (Square, Lightspeed, Toast, Odoo TPV): el dinero ya se
   cobró. «Marcar pagada» queda para las emitidas a mano.
2. **Tras sustituir un tique por su F3, se rectifica la F3** (devolución, anulación y a mano): es el
   documento vigente de la operación. El tique sustituido no ofrece «Rectificar».
3. **Anular una venta cobrada emite una rectificativa automática** (R5 del tique), como una devolución;
   el registro de anulación de VeriFactu es para un registro emitido por error y es de VeriFactu.
4. **Tipo de rectificativa**: R5 para un tique; R1 por defecto y R2–R4 a elegir a mano en una factura
   completa (Odoo `l10n_es_edi_verifactu`). Siempre por diferencias («I»): la sustitución «S» de
   VeriFactu no se emite; corregir datos de una factura es rectificarla entera y emitir otra.
5. **Serie por TPV o elegible para la venta**: no; la venta numera en TICKET y FACT.
6. **Continuar la numeración de otro sistema**: sí, con «Siguiente número» mientras la serie no se ha
   usado.
7. **La serie del año nuevo hereda** nombre, prefijo y formato de la del año anterior con su código.
8. **«Activa» gobierna el alta manual** (una inactiva no se ofrece y se rechaza); «Predeterminada» es
   la serie que el alta manual propone.
9. **El empleado emite a mano y marca pagada** (como el producto actual).
10. **«Devolución» pasa a llamarse «Rectificar»**: en Facturación no se devuelve dinero; eso es Ventas.
11. **Prefijo vacío al crear = el código**, y el prefijo se congela con el primer número, como el formato
    (cambiarlo cambiaba la forma de los números siguientes).
12. **Dos rectificaciones a la vez** de la misma factura: la segunda espera al bloqueo de la original y
    se rechaza sin gastar número (test con dos sesiones reales).
13. **Una devolución o anulación que llega antes que la factura** se rechaza para que se reintente (antes
    se perdía); Ventas pide antes el documento que espera, en la misma operación.
14. **La factura completa (F1 y F3) exige nombre, NIF y domicilio** del cliente (art. 6 RD 1619/2012);
    el producto actual solo pedía el NIF.
15. **El documento de una venta se emite al cobrar**, dentro de la transacción del cobro (Ventas llama a
    `invoice.invoice.create_from_sale`; igual la devolución y la anulación), y cuando no se pudo (sin
    emisor, importes que no cuadran) la venta queda «pendiente»: la reacción del outbox la reintenta sola
    unos minutos y después queda «Emitir ahora».
21. **La venta y su documento cuadran al terminar la operación que lo emite** (Odoo, Square, Shopify: el
    estado de facturación de un pedido cambia con la factura, no después): pedido a Facturación por la API
    o el asistente, el documento ya está en la venta al contestar; el aviso que llega después no cambia
    nada.
16. **Precio unitario sin IVA y descuento aparte** en cada línea (art. 6.1.f RD 1619/2012); antes la
    factura de una venta imprimía el precio con IVA y antes del descuento.
17. **Una rectificativa por diferencias no inventa un «tipo efectivo»**: una línea por clave fiscal, a su
    tipo; si la devolución trae artículos, solo sus claves.
18. **El formato de una serie exige el año** (si no, la serie del año siguiente, que nace de esta,
    repetiría sus números) y el número es ASCII imprimible de 60 caracteres como mucho.
19. **Un tique manual respeta el límite de Ventas** (3.000 € en España, RD 1619/2012 art. 4) y una
    factura manual solo se numera en una serie de este año.
20. **Un rechazo de VeriFactu deshace la emisión** (revisión fiscal de VeriFactu, 2026-10-15): una
    factura sin su registro de alta no se emite ni se imprime; solo un error transitorio de la base de
    datos la deja «pendiente» de la reacción, y sin VeriFactu en el negocio sale sin registro.

### Cambios frente al producto actual

1. La factura de una venta se construye leyendo la propia venta (líneas, importes, regla congelada),
   no el aviso: un aviso no puede inflar ni cambiar lo que se declara, y la calificación es la regla con
   la que se cobró, no la vigente el día de emitir (desaparece el rechazo por cambio de tipo entre el
   cobro y la emisión).
2. Sin emisor configurado no se emite nada (antes se emitía sin emisor y VeriFactu no podía
   registrarla).
3. El libro de números es la propia factura (no hay tabla aparte): un número sin documento no puede
   existir.
4. La lista sale por defecto con lo último emitido arriba.
5. «Factura completa» tiene botón en la ficha del tique (antes solo asistente o API).
6. El alta manual pide la serie de entre las que emiten facturas (F1, F2) y la rechaza si está
   inactiva; ya no emite una «Rectificativa» en positivo con la serie RECT.
7. Los nombres de las series que se crean solas y la línea de la rectificativa por diferencias ya no
   salen en inglés en un papel en español: las series de fábrica llevan su nombre traducido y la línea
   dice lo que volvió.

### Lo que NO hace, a propósito

- No envía nada a la AEAT ni calcula la huella ni el QR: eso es VeriFactu.
- No cobra ni devuelve dinero: «Marcar pagada» no toca la caja y «Rectificar» no devuelve dinero.
- No guarda la forma de pago: vive en la venta.
- No envía facturas por correo ni por WhatsApp, ni genera un PDF propio (el PDF es el del diálogo de
  impresión del navegador).
- No hace presupuestos, proformas, borradores ni albaranes.
- No lleva vencimientos, cobros parciales ni recordatorios de impago.
- No exporta el libro registro de facturas expedidas para la gestoría.
- No vigila el techo de la factura simplificada: lo pide Ventas al cobrar.
- No borra ni anonimiza los datos de un cliente en sus facturas (la ley obliga a conservarlas).
