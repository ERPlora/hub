# Workbook — Pagos (app)
Prefijo: PAYMENT
Alcance MVP: fuera del MVP (en la tienda; no viene en ninguna plantilla)
Estado de la app: completa (2026-10-23); sus avisos arrancan las automatizaciones (PAYMENT-F07)

> Manual de usuario y especificación de la app `payment`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Pagos del producto actual
> (`modules-workspace/modules/payments`, `origin/main` `820c799`, v1.0.30), de sus `docs/` y de sus
> tests. Los números de flujo se conservan (`PAYMENTS-Fnn` → `PAYMENT-Fnn`); PAYMENT-F08 es nuevo.
> Lo que cambia frente al producto actual lo dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Pagos registra el **dinero que sale** del negocio: lo que se paga a un proveedor, una transferencia,
un reembolso que no es de una venta. Cada pago lleva su referencia propia (`PAY-AAAAMMDD-NNNN`) y
pasa por una escalera de estados — **Borrador**, **Aprobado**, **Enviado**, **Completado** — o se
**Cancela** —, y guarda quién lo apuntó, quién lo aprobó y cuándo pasó cada paso.

Es lo contrario del cobro del TPV. Un **método de pago** de esta app es **desde dónde paga el
negocio** (su cuenta del banco, su tarjeta de empresa, el efectivo del cajón), no cómo paga el
cliente: las formas de cobro del TPV (Efectivo, Tarjeta…) son de **Ventas** y no tienen nada que ver
con estas. **Pagos no mueve dinero**: no habla con ningún banco, no genera ficheros SEPA ni ejecuta
transferencias; «Enviado» y «Completado» los marca una persona cuando el banco ya lo ha hecho.

Quién la usa:

- El **empleado**: solo mira la lista de pagos y la de métodos.
- El **responsable**, el **administrador** y el **propietario**: además registran pagos, los marcan
  como enviados y completados, los aprueban y los cancelan, y gestionan los métodos de pago.

## Referencia adoptada

- **Las formas de cobro del TPV son ajustes de la caja; pagar a proveedores es otra pieza** (cuentas a
  pagar): Odoo separa los métodos de pago del TPV (Point of Sale → Configuración) del registro de pagos
  a proveedor con su diario de banco o caja; Square, Lightspeed y WooCommerce configuran sus formas de
  cobro en los ajustes del cobro, y pagar facturas de proveedor es un producto aparte (Toast con
  xtraCHEF Bill Pay, Shopify con Shopify Bill Pay, Holded con su cuenta Wallet). Por eso Pagos no
  toca los métodos de cobro de Ventas y Ventas no depende de Pagos.
- **Aprobación por estados, con la separación por permisos** (Odoo, Business Central con su diario de
  pagos y sus flujos de aprobación; xtraCHEF solo deja pagar facturas aprobadas). Se copia la escalera y
  la separación de permisos (registrar ≠ aprobar); no hay conciliación bancaria ni remesas. **Quien
  tiene los dos permisos puede aprobar lo que registró**, como en QuickBooks (una factura que crea su
  propio aprobador queda aprobada:
  https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-workflows/set-use-bill-approval-and-payment-release-workflows/L1IOLL9hv_US_en_US);
  Odoo no trae aprobación de pagos de serie (la dan módulos aparte, por grupos). Bloquearlo dejaría sin
  poder pagar al negocio de una sola persona. Lo que sí queda siempre es el rastro: quién registró,
  quién aprobó y cuándo pasó cada paso.
- **Un método o una forma de pago no se borra: se desactiva** (Lightspeed: las formas integradas no se
  borran, se desactivan; Square: se pasan a «desactivadas» y se recuperan). Los pagos que lo usaron lo
  conservan.

Investigación y enlaces en «Para quien lo mantiene · Decisión: Pagos no es Ventas».

## Antes de empezar

1. Pagos no viene encendida con ningún tipo de negocio: se enciende desde la tienda de apps. No
   enciende ninguna otra app ni la necesita: se puede encender y apagar sola.
2. Al encenderla **no hay ningún método de pago**. Entra en **Pagos → Métodos** y crea al menos uno
   (PAYMENT-F01), por ejemplo «Cuenta BBVA» (Transferencia) o «Caja» (Efectivo).
3. La moneda de los pagos es la del negocio (euros mientras el Hub no guarde otra).

## Pantallas

Pagos se abre desde el menú **Pagos** y tiene dos pestañas: **Pagos** y **Métodos**. Lo que una
persona no puede hacer no aparece, y la app lo rechaza aunque lo intente por la API o por el
asistente.

### Pagos

Título «Pagos salientes». Una tabla con las columnas **Referencia**, **Fecha**, **Beneficiario**,
**Importe** y **Estado** (y **Método**, que se puede mostrar con el selector de columnas). Buscador
«Buscar referencia o beneficiario…» (busca también en la referencia de la factura del proveedor),
filtros por columna — referencia y beneficiario por un trozo del texto, la fecha «desde / hasta», el importe
«desde / hasta» en euros, el estado por lista —, orden por columna, vista de lista o de tarjetas y 50
filas por página. Va ordenada por la **fecha del pago**, la más reciente arriba (no por la de alta).

Cada fila ofrece la acción que le toca, con el nombre de lo que hace: **Aprobar** (Borrador),
**Marcar como enviado** (Aprobado) o **Marcar como completado** (Enviado), y **Cancelar pago**
mientras no esté completado ni cancelado. Un pago completado o cancelado no ofrece ninguna. Un pago
cancelado enseña su motivo debajo del estado; uno aprobado (y después enviado o completado), quién lo
aprobó («Aprobado por …»). Mientras una acción de fila trabaja, su botón gira y un segundo toque no
hace nada.

El botón **Nuevo pago** abre el formulario «Nuevo pago»: **Método**, **Fecha** (viene la de hoy),
**Importe**, **Beneficiario**, **Concepto** y, si se quieren, **IBAN del beneficiario** y **Factura
del proveedor** (su número).

### Métodos

Una tabla con **Nombre**, **Tipo** (Efectivo, Transferencia, Tarjeta, SEPA, Cheque u Otro),
**Cuenta** (la referencia de la cuenta bancaria, tapada salvo los últimos cuatro caracteres: un IBAN
sale como `ES** **** **** **** **** 1332`; entera al editar el método) y **Estado** (Activo o
Desactivado). Buscador
«Buscar método…», filtros de tipo y estado, 50 filas por página, ordenada por nombre. **Nuevo
método** abre el formulario; una fila (o su **Editar**) abre «Editando método — {nombre}»; cada fila
ofrece **Desactivar** o **Activar**.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin pagos.» o «Sin métodos de pago.»; con búsqueda o filtro, «Sin resultados». |
| Error | El aviso de la tabla con «Reintentar». Un rechazo del formulario sale dentro del formulario, cada motivo debajo de su campo, sin perder lo tecleado; el de una acción de fila, encima de la tabla. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

Importes y fechas salen con el formato del idioma de quien mira; el importe, en la moneda del pago.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| PAYMENT-F01 | Crear un método de pago | hecho |
| PAYMENT-F02 | Registrar un pago | hecho |
| PAYMENT-F03 | Aprobar un pago | hecho |
| PAYMENT-F04 | Marcar un pago como enviado y como completado | hecho |
| PAYMENT-F05 | Cancelar un pago | hecho |
| PAYMENT-F06 | Buscar y revisar los pagos | hecho |
| PAYMENT-F07 | Avisar de un pago completado | hecho |
| PAYMENT-F08 | Editar, desactivar y reactivar un método de pago | hecho |

### PAYMENT-F01 Crear un método de pago
<!-- origen: fi:modules/payments#command-payments-methods-create old:payments/WORKFLOW.md#payments-f01 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Métodos
Pasos:
1. En **Pagos → Métodos** pulsa **Nuevo método**.
2. Escribe el **Nombre**, elige el **Tipo** (viene **Transferencia**) y, si quiere, la **Cuenta** (la
   referencia de la cuenta del banco, por ejemplo los últimos dígitos del IBAN).
3. Pulsa **Crear método**: el formulario se cierra y el método sale en la tabla como **Activo**.
4. Desde ese momento se puede elegir en el **Método** de «Nuevo pago».
Entra: nombre, tipo y cuenta, de la persona.
Sale: un método activo (`payment.method.created`).
Si falla: dentro del formulario, debajo de su campo: un nombre vacío; un nombre que ya tiene otro
método, sin distinguir mayúsculas («Ya hay un método de pago con ese nombre. Elige otro nombre.»); un
tipo fuera de la lista. Lo tecleado se conserva. Sin ningún método activo, «Nuevo pago» avisa
«Todavía no hay métodos de pago activos. Crea uno en Métodos antes de registrar un pago.».
Implicados: FLOW-F11, FLOW-F21

### PAYMENT-F02 Registrar un pago
<!-- origen: fi:modules/payments#command-wasm-payments-payments-create-create_payment old:payments/WORKFLOW.md#payments-f02 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pagos
Pasos:
1. En **Pagos** pulsa **Nuevo pago**.
2. Elige el **Método** (solo salen los activos), deja la **Fecha** de hoy o pon otra, escribe el
   **Importe** como lo escribiría a mano (12,50; 1.250,00; 12,50 €), el **Beneficiario** y, si quiere,
   el **Concepto**, el **IBAN del beneficiario** y la **Factura del proveedor**.
3. Pulsa **Registrar pago**.
4. El formulario se cierra y el pago sale en la lista como **Borrador**, con su referencia. La lista
   va por la fecha del pago: uno con una fecha antigua no sale arriba.
5. Si se corta la conexión y vuelves a pulsar **Registrar pago** en el mismo formulario, el pago se
   registra una sola vez.
Entra: los datos del formulario; la moneda del negocio. Por el asistente o la API, el método se dice
por su id o por su nombre, el importe va en céntimos y, si se quiere, una clave del intento: repetir
la misma llamada con la misma clave responde el pago ya registrado en vez de registrar otro.
Sale: un pago en borrador con referencia `PAY-AAAAMMDD-NNNN` — la fecha es la del día del negocio en
que se registra, no la del pago; el número cuenta por día y nunca se repite — y el aviso
`payment.payment.created` (lleva la referencia, el beneficiario, el importe y la moneda).
Si falla: nada se guarda y no se gasta número. Dentro del formulario, debajo de su campo: un importe
vacío, 0 o negativo («El importe de un pago tiene que ser mayor que 0.»), uno que no es una cifra
(«Esto no es un importe. Escribe una cifra, por ejemplo 12,50.») o que se lee de dos maneras («1.250»
puede ser 1.250 € o 1,25 €: hay que escribir los decimales); un beneficiario vacío; un IBAN que no es
válido («Ese IBAN no es válido: revisa el país, los dígitos de control y la longitud.»); un método
que no existe («Ese método de pago no existe en este negocio.») o desactivado («Ese método de pago
está desactivado: elige uno activo.»). Por el asistente, un nombre de método que encaja con varios
dice cuáles («“Caja” encaja con varios métodos de pago: …»). Una clave de intento que ya registró
otro pago se rechaza («Esa clave de intento ya registró otro pago. Crea una clave nueva para cada
pago.») y no se guarda nada.
Implicados: FLOW-F11, FLOW-F21

### PAYMENT-F03 Aprobar un pago
<!-- origen: fi:modules/payments#command-payments-payments-approve old:payments/WORKFLOW.md#payments-f03 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pagos
Pasos:
1. En la fila de un pago en **Borrador**, pulsa **Aprobar**.
2. La fila pasa a **Aprobado**.
Entra: el pago (por el asistente, por su referencia).
Sale: el estado, quién lo aprobó y cuándo (la fila lo enseña: «Aprobado por …»); el aviso
`payment.payment.approved`.
Si falla: quien solo registra pagos (sin permiso de aprobar) no ve la acción y la app lo rechaza.
Aprobar un pago que ya no está en borrador no cambia nada, no avisa a nadie y dice por qué («Solo se
puede aprobar un pago en borrador; este está Aprobado.»), encima de la tabla.
Implicados: FLOW-F21

### PAYMENT-F04 Marcar un pago como enviado y como completado
<!-- origen: fi:modules/payments#command-payments-payments-mark_completed fi:modules/payments#command-payments-payments-mark_sent old:payments/WORKFLOW.md#payments-f04 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pagos
Pasos:
1. En la fila de un pago **Aprobado**, pulsa **Marcar como enviado**: pasa a **Enviado**.
2. Cuando el banco o el proveedor ya lo ha recibido, pulsa **Marcar como completado**: pasa a
   **Completado**.
Entra: el pago.
Sale: el estado; los avisos `payment.payment.sent` y `payment.payment.completed`. No se mueve dinero
ni se habla con ningún banco.
Si falla: cada paso exige el anterior; saltarse uno no cambia nada, no avisa y dice por qué («Solo se
puede marcar como enviado un pago aprobado; este está Borrador.», «Solo se puede marcar como
completado un pago enviado; …»). Un pago completado o cancelado no ofrece más acciones.
Implicados: FLOW-F21

### PAYMENT-F05 Cancelar un pago
<!-- origen: fi:modules/payments#command-payments-payments-cancel old:payments/WORKFLOW.md#payments-f05 -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Pagos
Pasos:
1. En la fila de un pago que no está completado ni cancelado, pulsa **Cancelar pago**.
2. Escribe el **Motivo de cancelación** en el formulario que sale y pulsa **Cancelar pago**.
3. La fila pasa a **Cancelado** y enseña el motivo debajo del estado.
Entra: el pago y el motivo (obligatorio).
Sale: el estado cancelado y el motivo guardados en el pago (no se borra nada); el aviso
`payment.payment.cancelled`.
Si falla: sin motivo (o con solo espacios) no se puede pulsar; por el asistente, un motivo vacío se
rechaza («Di por qué se cancela este pago: el motivo se queda en el pago.»). Un pago completado o
cancelado no se puede cancelar («El pago ya no admite cancelación.»), dentro del formulario y con el
motivo escrito: no cambia nada y no avisa. Una aprobación no se deshace: se cancela el pago y se registra otro.
Implicados: FLOW-F21

### PAYMENT-F06 Buscar y revisar los pagos
<!-- origen: fi:modules/payments#navigation-list-erp-payments-list fi:modules/payments#query-payments-payments-get fi:modules/payments#query-payments-payments-list old:payments/WORKFLOW.md#payments-f06 -->
Estado: hecho
Actor: empleado, responsable, administrador, propietario, asistente
Pantalla: Pagos
Pasos:
1. Abre **Pagos**.
2. Escribe en el buscador un trozo de la referencia (los últimos dígitos, la fecha), del beneficiario
   o de la factura del proveedor, o usa los filtros de columna: la **Fecha** desde un día, hasta otro o
   entre los dos; el **Importe** desde / hasta en euros; el **Estado** de la lista.
3. Ordena por la columna que necesite.
Entra: lo que teclea la persona.
Sale: nada; solo lectura. La lista se pone al día sola cuando otra persona registra o cambia un pago.
Por el asistente, «el pago PAY-20261014-0003» se lee entero, con su método, concepto, IBAN y factura.
Si falla: si la lista no carga, la tabla lo dice («No se han podido cargar los pagos.») con
«Reintentar», nunca «Sin pagos.». Un importe del filtro que no es una cifra no filtra (nunca «desde 0»).
Implicados: FLOW-F11

### PAYMENT-F07 Avisar de un pago completado
<!-- origen: fi:modules/payments#event-emitidos-payment-created-approved-sent-completed-cancelled old:payments/WORKFLOW.md#payments-f07 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna (la automatización se crea en **Automatizaciones**)
Pasos:
1. En **Automatizaciones**, crea una automatización que arranque con «se completa un pago» (por
   ejemplo, para que te deje la tarea de archivar el justificante) y enciéndela.
2. Marca un pago como **Completado** (PAYMENT-F04).
3. En unos segundos la automatización corre, una sola vez, con los datos de ese pago.
Entra: el pago completado.
Sale: el aviso `payment.payment.completed`, con el id, la referencia, el estado, el importe y la
moneda. Cada automatización que lo espera corre una vez por pago, aunque el aviso le llegue dos veces.
Los demás pasos de un pago (registrar, aprobar, enviar, cancelar) y los cambios de un método también
se pueden elegir como disparador.
Si falla: solo sale cuando el pago cambia de verdad: un «completar» rechazado no avisa y no arranca
nada. Sin ninguna automatización que lo espere, no pasa nada. El aviso de un negocio nunca arranca
nada en otro. Esta app no escucha a ninguna otra.
Implicados: FLOW-F21

### PAYMENT-F08 Editar, desactivar y reactivar un método de pago
<!-- origen: old:payments/WORKFLOW.md#payments-f01 fi:modules/payments#query-payments-methods-list -->
Estado: hecho
Actor: responsable, administrador, propietario, asistente
Pantalla: Métodos
Pasos:
1. En **Pagos → Métodos** pulsa una fila (o su **Editar**): se abre «Editando método — {nombre}».
2. Cambia el nombre, el tipo o la cuenta y pulsa **Guardar**.
3. Para dejar de usarlo, pulsa **Desactivar** en su fila: pasa a **Desactivado** y deja de salir en
   «Nuevo pago». **Activar** lo devuelve.
Entra: el método (por el asistente, por su nombre) y lo que cambia.
Sale: el método cambiado (`payment.method.updated`, `.deactivated`, `.activated`). Los pagos que ya
lo usaron lo conservan y enseñan su nombre nuevo.
Si falla: un nombre que ya tiene otro método se rechaza debajo de Nombre. Desactivar uno desactivado
o activar uno activo no cambia nada y dice por qué. Un método no se borra nunca.
Implicados: FLOW-F11, FLOW-F21

## Pagos: lo que entra y lo que sale

### Lo que ofrece: consultas (leen, no cambian nada)

| Operación | Qué da | Permiso |
|---|---|---|
| `payment.payment.list` | Los pagos, paginados (≤ 100), con búsqueda, filtros (referencia, beneficiario, concepto por trozo; método por id o nombre, estado, moneda, IBAN y factura exactos; fecha e importe por rango) y orden | `payment.view_payment` |
| `payment.payment.get` | Un pago entero, por su id o su referencia, con su IBAN completo | `payment.view_payment` |
| `payment.method.list` | Los métodos, paginados, con búsqueda (nombre o cuenta), tipo, estado y orden | `payment.view_payment` |
| `payment.method.get` | Un método, por su id o su nombre, con su cuenta completa | `payment.view_payment` |

### Lo que ofrece: acciones (cambian datos)

| Operación | Qué hace | Permiso |
|---|---|---|
| `payment.method.create` | Crea un método activo | `payment.add_payment` |
| `payment.method.update` | Cambia nombre, tipo o cuenta (solo lo que se envía) | `payment.add_payment` |
| `payment.method.deactivate` / `.activate` | Lo saca de «Nuevo pago» / lo devuelve | `payment.add_payment` |
| `payment.payment.create` | Registra un pago en borrador con su referencia | `payment.add_payment` |
| `payment.payment.approve` | Borrador → Aprobado | `payment.approve_payment` |
| `payment.payment.mark_sent` | Aprobado → Enviado | `payment.add_payment` |
| `payment.payment.mark_completed` | Enviado → Completado | `payment.add_payment` |
| `payment.payment.cancel` | Cualquiera no terminado → Cancelado, con motivo | `payment.approve_payment` |

### Lo que avisa

`payment.payment.created`, `.approved`, `.sent`, `.completed`, `.cancelled` y
`payment.method.created`, `.updated`, `.deactivated`, `.activated`; cada uno en la misma transacción
que su cambio y solo si el cambio ocurrió.

### A qué reacciona y lo que necesita de otras apps

A nada y de nadie: `requires = []`. Ninguna otra app lee Pagos salvo **Automatizaciones**, que
escucha todos sus avisos y los ofrece como disparadores (PAYMENT-F07, FLOW-F21). Sus pasos también
pueden consultar pagos y métodos y usar las acciones de Pagos que no piden confirmación (FLOW-F11):
registrar un pago y crear, cambiar, desactivar o activar un método. Aprobar, marcar como enviado o
completado y cancelar piden una persona: una automatización no los hace.

### Quién puede qué

| Papel | Ver | Registrar, enviar, completar y gestionar métodos | Aprobar y cancelar |
|---|---|---|---|
| Propietario | sí | sí | sí |
| Administrador | sí | sí | sí |
| Responsable | sí | sí | sí |
| Empleado | sí | no | no |

Quien tiene los dos permisos puede aprobar lo que registró (como hoy y como QuickBooks; ver
«Referencia adoptada»); el pago guarda quién lo registró, quién lo aprobó (`approved_by`,
`approved_at`), cuándo se envió y se completó (`sent_at`, `completed_at`) y quién lo canceló y cuándo
(`cancelled_by`, `cancelled_at`).

## Para quien lo mantiene

### Decisión: Pagos no es Ventas (2026-10-14)

El encargo suponía que `payment` podía ser la pantalla de gestión de las formas de cobro del TPV
(`sale.PaymentMethod`). **No lo es**: el módulo viejo registra pagos **salientes** a proveedores y
su «método» es la cuenta desde la que paga el negocio (su propio `WORKFLOW.md` lo dice y su catálogo
no tiene relación con `sales_payment_method`). Comparado con lo que `apps/sale` ya tiene:

| Lo que hay | `apps/sale` | `apps/payment` |
|---|---|---|
| Formas de cobro del TPV (Efectivo, Tarjeta…; `sale.payment_method.*`) | sí | no |
| Cobros de una venta por forma de cobro, devoluciones | sí (`SalePayment`, `RefundPayment`) | no |
| Cuentas desde las que paga el negocio (banco, caja, tarjeta de empresa) | no | sí (`payment.PaymentMethod`) |
| Pagos a proveedores con referencia diaria y aprobación por estados | no | sí (`payment.Payment`) |
| Datáfonos, pasarelas, conciliación bancaria, SEPA | no | no (fuera de los dos) |

No hay solapamiento, así que **no se duplica nada y no se pide nada a Ventas**: Pagos modela lo suyo
y `requires = []` (una dependencia con Ventas sería falsa: obligaría a encender el TPV para pagar a
un proveedor). `tests/test_integration_sale.py` prueba con Ventas real que los dos catálogos no se
mezclan.

Mercado (8 referencias):

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Odoo (TPV) | Las formas de cobro son configuración del TPV, cada una con su diario | https://www.cybrosys.com/odoo/odoo-books/v17/pos/payments/ |
| Odoo (Contabilidad) | Pagar a proveedor: «Registrar pago» eligiendo el diario (banco o caja) desde el que sale | https://hibou.io/docs/accounting-3/register-vendor-payments-1465 |
| Business Central | Pagos a proveedor en el diario de pagos, con flujos de aprobación | https://learn.continia.com/module/payment-approval-workflows/create-and-set-up-approval-workflows-1 |
| Square | Formas de cobro en Ajustes → Cobro; se reordenan y se desactivan, no se borran | https://squareup.com/help/us/en/article/6389-manage-payment-types-with-the-square-app |
| Lightspeed | Formas de cobro en Ajustes; las integradas no se borran, se desactivan | https://o-series-support.lightspeedhq.com/hc/articles/31329343706907 |
| Toast | Pagar a proveedores es xtraCHEF Bill Pay, aparte del TPV; solo paga facturas aprobadas | https://intercom.help/toast-central/en/articles/14725514-xtrachef-pay-vendor-bills-with-toast-bill-pay |
| Shopify | Pagar facturas de proveedor es Shopify Bill Pay, aparte de los ajustes de cobro | https://help.shopify.com/ar/manual/finance/shopify-bill-pay |
| Holded | Pagar a proveedores desde la cuenta de empresa, vinculado a su factura | https://www.holded.com/es/cuenta-empresa-wallet |

**Gana:** cobro del TPV y pagos a proveedor como piezas separadas; métodos que se desactivan, nunca se
borran. **Por qué no lo otro:** fundir los dos catálogos confunde «cómo me pagan» con «desde dónde
pago» (el asistente del producto actual ya corría ese riesgo) y ata Pagos a Ventas sin motivo.

### Cómo está hecho

- Anatomía completa (copia de `apps/service`): `apps.py`, `models.py`, `migrations/`, `schemas.py`,
  `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/`
  y un `tests/test_<fichero>.py` por fichero, más `test_integration_sale.py` (con Ventas real),
  `test_concurrency.py` (hilos) y `test_relay.py` (el aviso por el relay real del worker hasta una
  automatización real de Automatizaciones, PAYMENT-F07).
- Modelos: `PaymentMethod` (nombre único sin distinguir mayúsculas, tipo, cuenta, activo),
  `Payment` (referencia única, método, fecha del pago, importe en la unidad menor de su moneda > 0,
  moneda ISO 4217, beneficiario, IBAN, concepto, estado, factura del proveedor, motivo de cancelación,
  quién lo creó y quién lo cambió por última vez) y `PaymentCounter` (último número por día). UUIDv7,
  sin `hub_id`.
- **Referencia** `PAY-AAAAMMDD-NNNN`: el día es el del negocio (`timezone.localdate()`) al
  registrarlo; el contador sube con `UPDATE … RETURNING` en la transacción del alta (nunca una
  secuencia), así que dos altas a la vez no repiten número y un alta rechazada no gasta ninguno. Por
  encima de 9999 al día, el número sale entero (`PAY-20261014-10000`).
- **Un intento, un pago**: `payment.payment.create` acepta `idempotency_key` (UUID, opcional; columna
  única). El mismo intento otra vez responde el pago que registró, tal como está, sin gastar número ni
  avisar; dos a la vez: el segundo espera al primero (el bloqueo del método) y su alta choca con la
  columna única dentro de un savepoint, que devuelve el número, y responde el del primero. Con otros
  datos, 409 `payment.idempotency_key_reused`. «Nuevo pago» crea una clave al abrirse y la manda en cada
  envío (la idea de `sale.sale.complete`; payments#8).
- **Transiciones**: cada una bloquea la fila del pago (`select_for_update`) y comprueba el estado de
  origen; si no casa, 409 `payment.invalid_transition` (cancelar: `payment.not_cancellable`), sin
  cambio y sin aviso.
- **Importe**: la API y el asistente lo dan en céntimos (entero > 0, ≤ 9.999.999.999.999); la
  pantalla lo lee como se escribe a mano y nunca adivina un «1.250». La moneda, si no se da, es la del
  negocio (`EUR` mientras el Hub no guarde otra); si se da, un código ISO 4217 que exista (pycountry).
- **IBAN**: opcional; si se da, se valida y se guarda compacto y en mayúsculas (`python-stdnum`).
- **Cuentas tapadas**: una lista y su flujo vivo nunca llevan un IBAN ni una cuenta enteros
  (`queries.mask_account`: el país y los últimos cuatro de un IBAN, en grupos de cuatro; de otro texto,
  sus últimos cuatro); las respuestas de las acciones, tampoco. Enteros, solo `payment.payment.get` y
  `payment.method.get` (el formulario de editar método lee este antes de rellenarse).
- **Rastro de la escalera**: cada paso escribe el suyo en la misma transacción — `approved_by` y
  `approved_at`, `sent_at`, `completed_at`, `cancelled_by` y `cancelled_at` —; `updated_by` es solo
  quien lo tocó por última vez.
- **Doble toque**: las acciones de fila (avanzar un pago, desactivar o activar un método) quedan
  ocupadas mientras su orden corre (`loading` de la fila); un segundo toque no manda otra.
- Referencias humanas para el asistente y la voz: un método por su nombre (exacto, si no el único
  que lo contiene; varios → 409 `payment.method_ambiguous` con sus nombres); un pago por su referencia.
- Asistente: toda operación declara `ai` con `description` y `risk` (`high` en aprobar, enviar,
  completar y cancelar) y todo campo de entrada su `description`. `expose_api=True` en todas.
- El admin de Django del Hub tiene **CRUD completo** sobre los tres modelos (ronda 12, PLAN §17); una
  escritura del admin no pasa por las reglas ni deja aviso.

### Cómo son las páginas

- `frontend/pages/PaymentsPage.vue` y `MethodsPage.vue`, con la barra de pestañas de `frontend/tabs.ts`.
  La Fecha de Pagos filtra por rango (`daterange`: `payment_date_from` y `payment_date_to`, cada extremo
  por su lado).
  Listas con `DataTable` de servidor (`useServerTable` + `useLiveList`, copias de las de `service`),
  formularios en `FormModal` (`PaymentFormModal`, `MethodFormModal`, `CancelPaymentModal`), importes
  con `MoneyInput` y `lib/money.ts`.
- Los importes agrupan los millares también con cuatro cifras («1.234,56 €»; `useGrouping: 'always'` en
  `lib/format.ts`, porque el CLDR del español espera a cinco: hub#1090, que salió de payments#20), como
  Carrito y Tarifas.
- Lo que falta de `@erplora/ui` está en `UI-REQUESTS.md`: los iconos y las piezas que viven copiadas en
  la app (tabla de servidor viva, `useT`, dinero y avisos de página).

### Tablas de paridad con el producto actual

Operaciones:

| Producto actual | Ahora | Nota |
|---|---|---|
| `payments.payments.list` | `payment.payment.list` | mismos filtros; fecha por rango con `payment_date_from/to` |
| `payments.payments.get` | `payment.payment.get` | también por referencia |
| `payments.methods.list` | `payment.method.list` | filtro `is_active` declarado (ya no hay `f_is_active`) |
| `payments.hub_currency` | función interna `business_currency()` | no es una operación: nadie la pedía de fuera |
| `payments.payments.create` (WASM) | `payment.payment.create` | método por id o por nombre; rechaza método inexistente o inactivo |
| `payments._bump_counter`, `payments._insert_payment` | dentro de `payment.payment.create` | eran intenciones internas del WASM |
| `payments.payments.approve` | `payment.payment.approve` | 409 en vez de no-op mudo |
| `payments.payments.mark_sent` | `payment.payment.mark_sent` | 409 en vez de no-op mudo |
| `payments.payments.mark_completed` | `payment.payment.mark_completed` | 409 en vez de no-op mudo |
| `payments.payments.cancel` | `payment.payment.cancel` | motivo en su campo, no pegado al concepto |
| `payments.methods.create` | `payment.method.create` | ahora con pantalla |
| — | `payment.method.get`, `.update`, `.deactivate`, `.activate` | nuevas (PAYMENT-F08) |

Tests:

| Producto actual | Ahora |
|---|---|
| `every_string_has_its_translation.contract` | `tests/test_i18n.py` y `frontend/locale/locale.test.ts` |
| `filter_boxes_match_the_manifest.contract` | `tests/test_queries.py` (cada filtro de la página existe en `PaymentListIn`) y `PaymentsPage.test.ts` |
| `payment_currency.hub` / `.postgres` | `tests/test_services.py` (moneda del negocio, explícita, inválida) |
| `text_filters_narrow_by_fragment.pg` | `tests/test_queries.py` (referencia y beneficiario por trozo, sin cruzar de negocio) |
| `handler` (Rust): importe en céntimos, ≤ 0 rechazado, HALF_UP | `tests/test_schemas.py` y `frontend/lib/money.test.ts` |
| `erp-payments-list.test.ts`, `list-paging.test.ts`, `form-error-in-panel.test.ts`, `list-load-error.test.ts`, `amount-filter.test.ts` | `frontend/pages/PaymentsPage.test.ts`, `components/PaymentFormModal.test.ts`, `components/CancelPaymentModal.test.ts` |
| `lib/enums.test.ts`, `money-display-guard.test.ts` | `frontend/lib/format.test.ts` |

## Lo que queda fuera

Nada de sus flujos: los ocho están hechos (hub#182; app completa el 2026-10-23). Lo que no hace a
propósito, abajo. Lo que aún espera de `@erplora/ui` (iconos y piezas compartidas) está en
`UI-REQUESTS.md`, con sustituto en uso y ningún flujo roto.

## Lo que NO hace, a propósito

- No mueve dinero ni habla con bancos; no genera SEPA ni concilia extractos.
- No registra cobros de clientes ni devoluciones de ventas: eso es Ventas. La caja no ve estos pagos:
  pagar a un proveedor en efectivo hay que anotarlo también como salida en Caja.
- No enlaza la «factura del proveedor» con ninguna factura: es texto.
- No hay pagos parciales de un pago ni edición del importe: se cancela y se registra otro.
- No hay datáfono ni pasarela: eso es del TPV.

## Cambios frente al producto actual

- **Repetir el alta no duplica el pago**: el mismo intento enviado otra vez (un reintento tras un corte,
  un doble toque) responde el pago ya registrado; antes registraba otro, con su número (payments#8).
- **Los rechazos ya no son mudos**: aprobar, enviar, completar o cancelar en el estado equivocado, o
  registrar con un método que no existe o desactivado, contesta con su motivo, no cambia nada, no
  gasta número y no avisa. Antes contestaba bien, gastaba número y emitía el aviso (incluido el de
  pago completado que dispara automatizaciones).
- **Pantalla Métodos** con alta, edición, desactivación y reactivación (antes solo se creaban por el
  asistente o la API, y nunca se podían desactivar).
- **Acciones con el nombre de lo que hacen** (Aprobar, Marcar como enviado, Marcar como completado,
  Cancelar pago) en vez de «Avanzar», y solo las que el pago y la persona pueden usar.
- **Cancelar pide el motivo en un formulario** (antes, una ventana del navegador) y lo guarda aparte;
  el concepto ya no se toca.
- **IBAN y factura del proveedor** se pueden poner en «Nuevo pago»; el IBAN se valida.
- **La fecha del pago es un día** (`AAAA-MM-DD`); la API ya no acepta una hora. La **fecha de la
  referencia** es el día del negocio, no el del reloj UTC del servidor.
- **Fecha por defecto**: «Nuevo pago» viene con la de hoy.
- **Fuera de las plantillas** (decisión del 2026-10-14): el catálogo actual la tenía retirada del MVP
  (saas#1542), así que ni la peluquería ni el restaurante la traen al darse de alta (`verticals = []`);
  sigue en la tienda (`listed`), desde donde la enciende quien la quiera.
