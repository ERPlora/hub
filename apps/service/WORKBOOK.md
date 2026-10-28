# Workbook — Servicios (app)
Prefijo: SERVICE
Alcance MVP: peluquería
Estado de la app: completa (2026-10-21)
Lo que no entra todavía: ver «Lo que queda fuera».

> Manual de usuario y especificación de la app `service`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Servicios del producto actual
> (`modules-workspace/modules/services`, `origin/main` `75ee10a`, v1.5.77) y de sus `workflow/*.md`,
> más los servicios por profesional que el producto actual guardaba en Personal (`modules/staff`,
> STAFF-F10, F11 y F12). Los números de flujo se conservan (`SERVICES-Fnn` → `SERVICE-Fnn`); los de
> Personal pasan a SERVICE-F31, F32 y F33. Lo que cambia frente al producto actual lo dice «Cambios
> frente al producto actual», al final.

## Para qué sirve y para quién

Servicios es el **catálogo de lo que vende una peluquería o un centro de estética cuando lo que se
vende no es un artículo**: cada servicio con su nombre, su tarifa, su precio, su duración, su
categoría y su categoría fiscal (el IVA con el que se cobra), y **qué profesionales lo hacen**, con su
duración y su precio propios si los tienen. De este catálogo leen la agenda de Citas (qué se reserva,
cuánto dura y con quién), el TPV de Ventas (qué se cobra), la página de Reservas online (qué se puede
reservar desde fuera y si se enseñan su precio y su duración) y Tarifas (los precios especiales de un
servicio).

También guarda los **bonos**: un bono es un paquete de sesiones de servicios concretos que una
clienta compra una vez y gasta en varias visitas. Un bono paga una línea de servicio entera, no un
importe (no es una tarjeta regalo), y la titular es una sola clienta.

Quién la usa:

- El **empleado** (recepción, caja): ve el catálogo, las categorías y los bonos, da de alta servicios,
  ve los bonos vendidos y sus movimientos, concede un bono a una clienta y gasta sesiones.
- El **responsable**: además edita servicios y categorías, crea y edita bonos, asigna profesionales a
  un servicio, anula o ajusta un bono vendido y ve los bonos que se quedaron sin cliente.
- El **propietario** y el **administrador**: además archivan servicios, eliminan categorías y bonos y
  cambian los ajustes.

Solo lo usa la peluquería: la plantilla de restaurante no lo trae y ningún flujo de restaurante
depende de él.

## Referencia adoptada

- **Catálogo de salón** (Fresha, Vagaro, Mangomint, DaySmart, Square Appointments): un servicio =
  nombre, precio, duración y categoría; archivar en vez de borrar; un servicio de precio no cerrado
  («Desde», «Variable») se cobra preguntando el importe.
- **Quién hace cada servicio se asigna en el servicio** (Fresha «Team members», Square Appointments,
  Vagaro, Mangomint, Odoo Appointments), con la duración y el precio propios de cada profesional.
- **Bonos** (Mindbody, Vagaro, Boulevard, Fresha): el bono se paga al venderlo y gastarlo no emite
  documento fiscal; cubre líneas de servicio, no importes; la caducidad cuenta desde la compra; lo
  vendido conserva las condiciones con que se vendió; regalar o corregir es un movimiento aparte con
  motivo; anular solo un bono que no se ha usado.
- Decisiones del producto actual que mandan aquí: ADR-0386 (un bono cubre líneas; una tarjeta regalo,
  importes), ADR-0390 (la titularidad nace al venderlo, el reloj arranca en la compra y no se
  transfiere) y ADR-0085 (el IVA se enlaza por la categoría fiscal de Impuestos).

## Antes de empezar

1. Servicios enciende con él **Impuestos**, **Personal** y **Clientes**, y no se pueden apagar
   mientras Servicios esté encendida: la categoría fiscal de cada servicio es de Impuestos, los
   profesionales son de Personal y la titular de un bono es una ficha de Clientes.
2. En **Impuestos → Categorías** tiene que haber al menos una categoría fiscal activa: sin ella el
   formulario de servicio avisa «Todavía no hay categorías fiscales. Configúralas en Impuestos antes
   de añadir servicios.».
3. Crea las categorías que quieras para agrupar el catálogo (SERVICE-F07) y da de alta los servicios
   (SERVICE-F01). Para muchos a la vez, el asistente los da de alta de golpe (SERVICE-F06).
4. Abre cada servicio y asígnale los profesionales que lo hacen (SERVICE-F31). Mientras un servicio
   no tenga a nadie asignado, la agenda deja que lo haga todo el equipo reservable (SERVICE-F33).
5. Crea los bonos en **Bonos y paquetes** (SERVICE-F12) poniendo siempre **Usos**: vacío significa
   sesiones ilimitadas.
6. En **Ajustes** elige la duración, el margen y la categoría fiscal que toma un servicio nuevo cuando
   no se dicen (SERVICE-F11).

Los importes (el precio de un servicio y el de cada profesional, el precio cerrado y el descuento en importe
de un bono, lo pagado por un bono) van en **la moneda del negocio**, la de su país, la que dice **Ajustes →
Negocio** (euros en España, złoty en Polonia, yenes en Japón), con sus decimales (el yen no tiene), escritos
con coma o punto: «1500» es un precio de 1500 yenes en Japón y de 1500,00 € en España, y Ventas lo cobra igual.
Mientras el negocio no contesta, un importe sale como una cifra sin símbolo, nunca en euros. Los ejemplos de
este documento son de un negocio de España, en euros.

## Pantallas

Servicios se abre desde el menú **Servicios** y tiene tres pestañas: **Servicios**, **Categorías** y
**Bonos y paquetes**, más **Ajustes** para quien puede cambiarlos. Lo que una persona no puede hacer
no aparece, y la app lo rechaza aunque lo intente por la API o por el asistente.

### Servicios
Tabla con buscador «Buscar servicio…», columnas **Nombre, Categoría, Tarifa** (Precio fijo, Por hora,
Desde, Variable, Gratis), **Precio** (en la moneda del negocio), **Duración (min)** y **Estado**: **Activo**, **Sin configurar** (con
el motivo debajo, «Sin categoría fiscal: no se puede cobrar») o **Archivado**. Se ordena por
cualquier columna y, con el botón **Filtros**, se filtra por Nombre, Categoría, Tarifa, Precio
(desde–hasta, en la moneda del negocio), Duración y Estado (el filtro de Estado en **Archivado** cambia a la vista de
archivados); vista de lista o de tarjetas; 50 por página.

**Nuevo servicio** abre el formulario: **Nombre, Tarifa, Precio (<moneda>)** (en la moneda del negocio y
con sus decimales: «Precio (EUR)» y «22,50» en España, «Precio (JPY)» y «1500» en Japón; solo «Precio»
mientras el negocio no contesta; al salir del campo se reescribe con la notación del idioma, y no antes de
que conteste), **Duración (min)**, **Categoría** («Sin categoría» o
una de la lista) y **Categoría fiscal** (sin opción vacía; viene elegida la de los Ajustes) y el
botón **Crear servicio**. Tocar una fila (o su **Editar**) abre «Editando servicio — <nombre>» con el
botón **Guardar cambios** y, debajo, **Profesionales que lo hacen** (SERVICE-F31, F32). Por fila:
**Editar** y **Archivar**; en la vista de archivados, **Restaurar**. **Archivar** pide confirmar:
«Archivar servicio» — «<nombre> — dejará de ofrecerse y de poder reservarse. Se conservan su
histórico y las citas ya reservadas.» y, si Citas tiene citas próximas con él, «{count} cita(s)
próxima(s) siguen usando este servicio. Conservan su reserva, precio y duración; solo dejan de
admitirse reservas nuevas.».

### Categorías
Tabla con buscador «Buscar categoría…» y columnas **Nombre, Categoría padre, Orden** y **Servicios**
(cuántos servicios en oferta tiene). **Nueva categoría** abre el formulario: **Nombre, Categoría
padre** («Sin padre (raíz)» u otra) y **Orden**, con **Crear categoría** / **Guardar cambios**. Por
fila: **Editar** y **Eliminar**; **Eliminar** pide confirmar: «Eliminar categoría» — «<nombre> — la
categoría desaparece; los servicios que contiene se conservan, sin categoría.» y, si tiene servicios,
«{count} servicio(s) se quedarán sin categoría.».

### Bonos y paquetes
Arriba, **Bonos sin cliente** (solo responsable, propietario y administrador). Tabla con buscador
«Buscar paquete…», columnas **Nombre, Descuento, Precio cerrado, Líneas** y **Estado** (Activo,
Archivado o Eliminado). En **Filtros**, el filtro de Estado en **Eliminado** cambia a la vista de los bonos
eliminados del catálogo que alguien compró: por fila solo **Movimientos** y **Bonos vendidos**.
**Nuevo paquete** abre el formulario: **Nombre, Tipo de descuento** (Porcentaje o Importe fijo),
**Descuento (%)** o **Descuento (<moneda>)**, **Precio cerrado (<moneda>)** (en la moneda del negocio:
«Precio cerrado (PLN)» en Polonia; sin el código, «Descuento (importe)» y «Precio cerrado», mientras el
negocio no contesta; «Déjalo vacío para que valga la suma de sus líneas menos el descuento.»), **Vigencia (días)** («Días canjeables desde la compra; vacío = no
caduca.»), **Usos** («Usos que concede el bono; vacío = ilimitados.») y **Servicios incluidos**: una
fila por servicio con **Servicio** y, debajo, **Sesiones** y «Quitar línea»; **Añadir servicio**; botón **Crear
paquete**. Al editar, en lugar de las líneas sale «Los servicios incluidos no se cambian una vez
creado: elimina este paquete y crea uno nuevo.». Por fila: **Editar, Movimientos, Bonos vendidos** y
**Eliminar** (con «Eliminar paquete»: «<nombre> — el paquete y sus {count} línea(s) salen del catálogo
y ya no se pueden vender; los bonos ya vendidos se siguen pudiendo gastar y los encuentras filtrando
Estado por Eliminado.»).

Hojas que se abren encima, todas con **Cerrar**, «Cargando…» mientras llegan, su vacío, su error y
**Cargar más** con «Se muestran {shown} de {total}» cuando hay más:

- **Movimientos del bono**: cada sesión y cada ajuste de ese bono, de todas las clientas, el más
  reciente primero, con su etiqueta (**Reservada**, **Entregada**, **Liberada**, **Caducada**,
  **Devuelta**, **Cortesía**, **Corrección**), el servicio, la fecha, «Cliente: <nombre>», quién y el
  motivo. Vacía: «Este bono aún no se ha usado.».
- **Bonos vendidos**: una fila por compra, con **Activo** o **Anulado**, la clienta, la fecha, el
  importe, «{used} usadas · quedan {remaining}» (o «· sin límite»), «Caduca el …» o «No caduca» y lo
  regalado o corregido después; en una anulada, «Anulado por {who} el {when}» y el motivo. Botones
  **Ajustar** y **Anular** cuando proceden. Vacía: «Nadie ha comprado este bono todavía.».
- **Bonos sin cliente**: los bonos vivos cuya ficha se eliminó o se anonimizó, con «Quedan {remaining}
  sesión(es)», «Sin límite de sesiones» o «Agotado», el bono, el importe, «Cliente borrado el {when}»,
  «Caducado» si lo está y «Referencia del cliente: <identificador>». Vacía: «Ningún bono se ha quedado
  sin cliente.».

### Ajustes de Servicios
Solo para quien puede cambiarlos. Campos: «Duración por defecto (min)», «Tiempo de margen por
defecto (min)», «Categoría fiscal por defecto», «Mostrar precios», «Mostrar duración» y «Permitir
reserva online»; botón **Guardar**. Mientras el negocio no ha guardado nunca, salen los de fábrica
(60 min, 0 min, ninguna categoría, sí, sí, sí). Guardado: «Ajustes guardados.».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin servicios.», «No hay categorías.» o «No hay paquetes.»; con búsqueda o filtro, «Sin resultados». |
| Error | El aviso de la tabla con «Reintentar». Un rechazo de un formulario sale dentro del formulario, cada motivo debajo de su campo, sin perder lo tecleado; el de una acción de fila, en su confirmación o encima de la tabla. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

Importes, duraciones y fechas salen con el formato del idioma de quien mira.

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| SERVICE-F01 | Dar de alta un servicio | hecho |
| SERVICE-F02 | Editar un servicio | hecho |
| SERVICE-F03 | Poner un servicio a precio abierto | hecho |
| SERVICE-F04 | Archivar un servicio | hecho |
| SERVICE-F05 | Ver y restaurar los servicios archivados | hecho |
| SERVICE-F06 | Dar de alta muchos servicios de golpe | hecho (asistente y API; no hay importador en pantalla) |
| SERVICE-F07 | Crear y editar categorías | hecho |
| SERVICE-F08 | Eliminar una categoría | hecho |
| SERVICE-F09 | Vender un servicio en el TPV | hecho (lo hace Ventas, SALE-F38) |
| SERVICE-F10 | Dar el catálogo a Citas, Ventas, Reservas online y Tarifas | hecho |
| SERVICE-F11 | Cambiar los ajustes de Servicios | hecho |
| SERVICE-F12 | Crear un bono | hecho |
| SERVICE-F13 | Editar o eliminar un bono | hecho |
| SERVICE-F14 | Vender un bono a una clienta | hecho la concesión (asistente y API); la venta en el TPV, no (ver «Lo que queda fuera») |
| SERVICE-F15 | Consultar los bonos de una clienta | hecho (asistente y API) |
| SERVICE-F16 | Ver quién ha comprado un bono | hecho |
| SERVICE-F17 | Anular un bono vendido por error | hecho |
| SERVICE-F18 | Regalar sesiones, alargar la caducidad o corregir el saldo | hecho |
| SERVICE-F19 | Ver los movimientos de un bono | hecho |
| SERVICE-F20 | Un bono caduca | hecho |
| SERVICE-F21 | Gastar una sesión fuera del cobro | hecho (asistente y API) |
| SERVICE-F22 | Pagar una línea con un bono | hecho (con Ventas, SALE-F27) |
| SERVICE-F23 | Soltar la sesión si la línea o la cuenta desaparecen | hecho |
| SERVICE-F24 | Dar por gastadas las sesiones al cobrar | hecho (conceder los bonos vendidos en el tique, no: ver «Lo que queda fuera») |
| SERVICE-F25 | La sesión retenida que nadie cobra vuelve sola | hecho (al leer y con la tarea de cada hora) |
| SERVICE-F26 | Devolver la sesión al devolver la venta | hecho (con Ventas, SALE-F32) |
| SERVICE-F27 | Devolver la sesión al anular la venta | hecho (anular los bonos vendidos en ella, no: ver «Lo que queda fuera») |
| SERVICE-F28 | Unir dos fichas: los bonos pasan a la que queda | hecho |
| SERVICE-F29 | Eliminar o anonimizar una ficha: sus bonos quedan sin cliente | hecho |
| SERVICE-F30 | Rescatar los bonos sin cliente | hecho (la lista; un bono no se pasa a otra ficha) |
| SERVICE-F31 | Asignar un profesional a un servicio | hecho |
| SERVICE-F32 | Cambiar o quitar un profesional de un servicio | hecho |
| SERVICE-F33 | Saber quién puede hacer un servicio | hecho |

### SERVICE-F01 Dar de alta un servicio
<!-- origen: qa:verticals/beauty/01-services-professionals-and-schedules wf:peluqueria-dia#rec_peluqueria-f04 fi:modules/services#command-services-services-create-sql-transaccional fi:modules/services#navigation fi:modules/services#permission-role_permissions fi:modules/services#query-services-services-list fi:modules/services#validation-declarativa-bloque-validates old:services/workflow/catalogo.md#services-f01 qa:modules/services/create-service-with-duration-and-price -->
Estado: hecho
Actor: empleado, responsable, asistente
Pantalla: Servicios
Pasos:
1. En **Servicios** pulsa **Nuevo servicio**.
2. Escribe el Nombre, elige la Tarifa (viene **Precio fijo**), el Precio y la Duración (min). Elige
   una Categoría o deja «Sin categoría».
3. Elige la Categoría fiscal (son las de Impuestos, por su nombre y su tipo; viene la de los Ajustes
   si hay una). Sin ella **Crear servicio** no se puede pulsar.
4. Pulsa **Crear servicio**: el formulario se cierra y el servicio sale en la tabla como **Activo**.
Entra: las categorías de Servicios y las categorías fiscales activas de Impuestos.
Sale: el servicio en oferta y reservable (`service.service.created`); desde ese momento lo ven la
agenda y el TPV y, si se reserva online, la página de Reservas online. Lo que no se dice toma los Ajustes: duración, margen antes y después,
reserva online y categoría fiscal; sin Ajustes, 60 min, sin margen y con reserva online.
Si falla: dentro del formulario, cada motivo debajo de su campo: un importe que no se entiende
(«Esto no es un importe. Escribe una cifra, por ejemplo 12,50.», también con el símbolo de otra moneda:
«22,50 €» en un negocio de Polonia), uno que se lee de dos maneras o uno negativo; una categoría eliminada («Esa categoría no está disponible: no existe en este negocio o se
ha eliminado.»); una categoría fiscal que no existe o está desactivada («Esa categoría fiscal no
existe en Impuestos o está desactivada.»); sin ninguna categoría fiscal, el aviso de Impuestos. Lo
tecleado se conserva.
Implicados: TAX-F01

### SERVICE-F02 Editar un servicio
<!-- origen: fi:modules/services#command-services-services-update-sql-transaccional fi:modules/services#query-services-services-get old:services/workflow/catalogo.md#services-f02 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Servicios
Pasos:
1. Toca la fila del servicio o su **Editar**: se abre «Editando servicio — <nombre>» con sus datos.
2. Cambia Nombre, Tarifa, Precio, Duración, Categoría o Categoría fiscal (esta no se puede vaciar).
3. Pulsa **Guardar cambios**: el formulario se cierra y la tabla se pone al día sola.
Entra: el servicio completo.
Sale: el servicio cambiado (`service.service.updated`); se cambia solo lo que se tocó. Las citas ya
reservadas conservan el nombre, el precio y la duración que tenían; los bonos ya vendidos no cambian.
Si falla: los motivos de SERVICE-F01; un servicio que ya no existe, «Ese servicio no existe en este
negocio.». Un servicio cuya categoría se eliminó sale «Sin categoría» y se guarda sin problema.
Implicados: SERVICE-F31

### SERVICE-F03 Poner un servicio a precio abierto
<!-- origen: old:services/workflow/catalogo.md#services-f03 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Servicios
Pasos:
1. En el formulario elige la Tarifa **Desde**, **Por hora**, **Variable** o **Gratis** (o pídeselo al
   asistente: «Mechas desde 65 €»).
2. La columna Tarifa lo enseña.
Entra: el servicio.
Sale: el servicio con su tarifa (`service.service.updated`). Para Ventas, un servicio que no es de
precio fijo pide el importe al cobrarlo, con su precio como sugerencia; «Gratis» no fuerza el precio a
0. Los precios mínimo y máximo (asistente y API) se guardan; el mínimo no puede pasar del máximo.
Si falla: una tarifa fuera de las cinco o un mínimo por encima del máximo se rechazan con su motivo.
Implicados: SALE-F09

### SERVICE-F04 Archivar un servicio
<!-- origen: fi:modules/services#command-services-services-delete-sql-transaccional old:services/workflow/catalogo.md#services-f04 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Servicios
Pasos:
1. En la fila del servicio pulsa **Archivar**.
2. Lee «Archivar servicio»: «<nombre> — dejará de ofrecerse y de poder reservarse. Se conservan su
   histórico y las citas ya reservadas.» y, si Citas está activa y tiene citas próximas con ese
   servicio, «{count} cita(s) próxima(s) siguen usando este servicio. Conservan su reserva, precio y
   duración; solo dejan de admitirse reservas nuevas.».
3. Pulsa **Archivar** (o **Cancelar**). La fila desaparece de la lista.
Entra: el servicio y, si Citas está activa y quien archiva ve citas, cuántas citas pendientes o
confirmadas lo usan desde ahora.
Sale: el servicio fuera de oferta, no borrado (`service.service.archived`): deja de salir en la
agenda, en el TPV, en la página de Reservas online y en el selector de líneas de un bono. Las citas ya reservadas, los
bonos que lo incluyen y los profesionales asignados no cambian.
Si falla: en la confirmación, el motivo (por ejemplo, «Ese servicio no existe en este negocio.»).
Archivar uno ya archivado no cambia nada. El aviso de citas es un consejo: nunca impide
archivar, y si Citas no contesta la confirmación sale sin esa línea.
Implicados: APPOINTMENT-F01, APPOINTMENT-F26

### SERVICE-F05 Ver y restaurar los servicios archivados
<!-- origen: old:services/workflow/catalogo.md#services-f05 -->
Estado: hecho
Actor: responsable
Pantalla: Servicios
Pasos:
1. En **Filtros**, elige **Archivado** en Estado y pulsa **Aplicar**: la tabla enseña solo los archivados.
2. En la fila pulsa **Restaurar** (no pide confirmación).
3. El servicio vuelve a la lista como antes, con su nombre, precio, duración y categoría.
Entra: los servicios archivados.
Sale: el servicio otra vez en oferta y reservable (`service.service.restored`).
Si falla: encima de la tabla, «No se pudo restaurar el servicio» o «Ese servicio no existe en este
negocio.». Restaurar uno que ya está en oferta no cambia nada. En la vista de archivados la fila no
ofrece Editar ni Archivar y tocarla no abre nada.
Implicados: SERVICE-F04

### SERVICE-F06 Dar de alta muchos servicios de golpe
<!-- origen: fi:modules/services#command-services-services-bulk_create-handler-wasm-bulk_create_services old:services/workflow/catalogo.md#services-f06 -->
Estado: hecho (asistente y API; no hay importador en pantalla)
Actor: responsable, asistente
Pantalla: ninguna
Pasos:
1. Pide al asistente que cree una lista de servicios (hasta 500), cada uno con nombre, precio,
   duración y, si quieres, categoría fiscal y categoría.
2. El asistente responde cuántos se crearon.
Entra: la lista de servicios.
Sale: los servicios, todos o ninguno, cada uno con su aviso (`service.service.created`). Lo que una
línea no dice toma los Ajustes, como el alta suelta.
Si falla: una línea mal formada, con una categoría o una categoría fiscal que no existen, rechaza el
lote entero antes de crear nada, con el motivo de cada línea en su campo (por ejemplo, el precio
de la cuarta línea).
Implicados: SERVICE-F01, SERVICE-F11

### SERVICE-F07 Crear y editar categorías
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f04 fi:modules/services#command-services-categories-create-sql-transaccional fi:modules/services#command-services-categories-update-sql-transaccional fi:modules/services#query-services-categories-list old:services/workflow/catalogo.md#services-f07 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Categorías
Pasos:
1. En **Categorías** pulsa **Nueva categoría**.
2. Escribe el Nombre y, si quieres, elige la Categoría padre y un Orden.
3. Pulsa **Crear categoría**. Para cambiarla, toca la fila o su **Editar** («Editando categoría —
   <nombre>»), cambia lo que haga falta y pulsa **Guardar cambios**.
Entra: las categorías vivas del negocio.
Sale: la categoría (`service.category.created`, `service.category.updated`), que aparece en el campo
Categoría del formulario de servicio y en el filtro de la columna Categoría. Las listas y el TPV las
ordenan por Orden y nombre.
Si falla: un nombre que ya tiene otra categoría viva (sin distinguir mayúsculas ni espacios de más)
sale debajo del campo: «Ya hay una categoría con ese nombre. Elige otro nombre.». Una categoría no
puede ser su propio padre ni colgar de una de sus hijas: «Una categoría no puede colgar de sí misma
ni de una de sus subcategorías.». Un padre eliminado: «Esa categoría padre no está disponible: no
existe en este negocio o se ha eliminado.».
Implicados: SERVICE-F01, SERVICE-F08

### SERVICE-F08 Eliminar una categoría
<!-- origen: fi:modules/services#command-services-categories-delete-sql-transaccional old:services/workflow/catalogo.md#services-f08 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Categorías
Pasos:
1. En la fila de la categoría pulsa **Eliminar**.
2. Lee «Eliminar categoría» y, si tiene servicios, cuántos se quedarán sin categoría.
3. Pulsa **Eliminar** (o **Cancelar**). La fila desaparece.
Entra: la categoría y cuántos servicios en oferta tiene.
Sale: la categoría eliminada, no borrada (`service.category.deleted`); su nombre queda libre. Sus
servicios se quedan **sin categoría** y sus subcategorías pasan a colgar de su padre (o a ser raíz).
Si falla: en la confirmación, el motivo (por ejemplo, «Esa categoría no existe en este negocio.»).
Implicados: SERVICE-F07, SERVICE-F02

### SERVICE-F09 Vender un servicio en el TPV
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f09 old:services/workflow/catalogo.md#services-f09 -->
Estado: hecho (lo hace Ventas, SALE-F38)
Actor: empleado
Pantalla: Ventas: Vender
Pasos:
1. En la tira de categorías del TPV, **Servicios** enseña cada servicio en oferta con su precio y su
   duración (también salen en el buscador).
2. Un servicio **Sin configurar** sale con la marca «Falta el IVA» y no se vende.
3. Un servicio que no es de precio fijo pide el importe, con su precio como sugerencia.
Entra: los servicios en oferta, su tarifa y su categoría fiscal.
Sale: la línea de venta con el servicio; Servicios no anota nada por vender un servicio suelto.
Si falla: lo dice Ventas (SALE-F38).
Implicados: SALE-F01, SALE-F38

### SERVICE-F10 Dar el catálogo a Citas, Ventas, Reservas online y Tarifas
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f06 wf:whatsapp-cita#rec_wa_cita-f04 fi:modules/services#event-emitidos old:services/workflow/catalogo.md#services-f10 -->
Estado: hecho
Actor: sistema, asistente
Pantalla: ninguna
Pasos:
1. Quien reserva (la agenda de Citas y la página de Reservas online), cobra (el TPV de Ventas) o pone
   precios (Tarifas) no abre Servicios: lee su lista de servicios en oferta o un servicio concreto.
2. La lista trae solo los servicios en oferta, con nombre, tarifa, precio, mínimo y máximo, duración,
   margen, si es reservable, su categoría y su categoría fiscal (y si le falta); también los que aún
   no tienen categoría fiscal, marcados.
Entra: el catálogo.
Sale: nada; Servicios no guarda quién lo lee.
Si falla: cada lector decide.
Implicados: APPOINTMENT-F01, SALE-F01, ONLINE_BOOKING-F01, ONLINE_BOOKING-F07, PRICING-F07,
WHATSAPP_INBOX-F21

### SERVICE-F11 Cambiar los ajustes de Servicios
<!-- origen: fi:modules/services#command-services-settings-update-sql-transaccional fi:modules/services#query-services-settings-get old:services/workflow/catalogo.md#services-f11 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes de Servicios
Pasos:
1. Abre **Servicios → Ajustes**.
2. Cambia los campos y pulsa **Guardar**.
3. Sale «Ajustes guardados.».
Entra: los ajustes guardados (o los de fábrica).
Sale: los ajustes (`service.settings.updated`). La duración, el margen (antes y después), la reserva
online y la categoría fiscal por defecto los toma todo servicio nuevo que no los diga (formulario,
asistente, API y alta de golpe); el formulario trae elegida la categoría fiscal por defecto.
«Mostrar precios» y «Mostrar duración» los usa la página de Reservas online: sin ellos no enseña el
precio o la duración de cada servicio.
Si falla: «No se pudieron guardar los ajustes.» y el motivo debajo del campo (una duración de 0, una
categoría fiscal que no existe).
Implicados: SERVICE-F01, SERVICE-F06, ONLINE_BOOKING-F01

### SERVICE-F12 Crear un bono
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f04 wf:peluqueria-dia#rec_peluqueria-f13 fi:modules/services#command-services-packages-create-handler-wasm-create_package fi:modules/services#query-services-package_items-list fi:modules/services#query-services-packages-list old:services/workflow/bonos.md#services-f12 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Bonos y paquetes
Pasos:
1. Pulsa **Nuevo paquete**.
2. Escribe el Nombre («Bono 5 cortes»). Elige el Tipo de descuento y su valor, y si quieres un Precio
   cerrado.
3. Pon la Vigencia (días), que cuenta desde la compra (vacía = no caduca), y los **Usos**: las
   sesiones que da el bono en total (vacío = ilimitadas).
4. En «Servicios incluidos» elige cada Servicio (los que están en oferta) y sus Sesiones; **Añadir
   servicio** añade otra fila y «Quitar línea» la quita.
5. Pulsa **Crear paquete**: sale en la tabla como **Activo** con su número de líneas.
Entra: los servicios en oferta.
Sale: el bono en el catálogo (`service.package.created`). Al gastarlo, cualquier servicio de sus
líneas consume uno de sus «Usos».
Si falla: sin ningún servicio, «Añade al menos un servicio: un paquete sin líneas no se puede
canjear.»; un servicio repetido, archivado o que no existe; un importe ilegible o negativo, debajo de
su campo; un nombre que ya tiene otro bono vivo, «Ya hay un paquete con ese nombre. Elige otro
nombre.».
Implicados: SERVICE-F14, SERVICE-F22

### SERVICE-F13 Editar o eliminar un bono
<!-- origen: fi:modules/services#command-services-packages-delete-sql-transaccional fi:modules/services#command-services-packages-update-sql-transaccional fi:modules/services#query-services-packages-get old:services/workflow/bonos.md#services-f13 -->
Estado: hecho
Actor: responsable (editar), propietario y administrador (eliminar)
Pantalla: Bonos y paquetes
Pasos:
1. Toca la fila o su **Editar** («Editando paquete — <nombre>»): cambia Nombre, Descuento, Precio
   cerrado, Vigencia o Usos; las líneas no se cambian. Pulsa **Guardar cambios**.
2. Para quitarlo del catálogo pulsa **Eliminar** y confirma.
3. Para ver lo vendido de un bono eliminado, en **Filtros** elige **Eliminado** en Estado.
Entra: el bono del catálogo.
Sale: al editar, el bono cambiado (`service.package.updated`); «Usos» y «Vigencia» valen para las
ventas futuras, los bonos vendidos conservan lo que se vendió; el nombre nuevo se ve también en ellos.
Al eliminar (`service.package.deleted`), el bono sale del catálogo y ya no se puede conceder; los ya
vendidos se siguen gastando, ajustando y anulando igual. Un bono eliminado que nadie compró no sale
en ninguna vista.
Si falla: al guardar, dentro del formulario, el motivo («Ese paquete no existe en este negocio.» si se
eliminó entretanto) o los de SERVICE-F12 debajo de su campo; al eliminar, el motivo en la confirmación.
Implicados: SERVICE-F12, SERVICE-F16

### SERVICE-F14 Vender un bono a una clienta
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:peluqueria-dia#rec_peluqueria-f13 old:services/workflow/bonos.md#services-f14 -->
Estado: hecho la concesión (asistente y API); la venta en el TPV, no (ver «Lo que queda fuera»)
Actor: empleado, responsable, asistente
Pantalla: asistente
Pasos:
1. Pide al asistente que conceda el bono a la clienta (por su nombre o su teléfono), con el importe
   cobrado y la venta si los hay.
2. El bono sale en **Bonos vendidos** de ese bono (SERVICE-F16).
Entra: el bono del catálogo, vivo y activo, y la clienta (Clientes).
Sale: un bono vendido con la titular, la fecha, el importe y los «Usos» y la «Vigencia» del catálogo
congelados; la caducidad cuenta desde ese momento (`service.grant.granted`). No sale ningún documento
fiscal: lo emite la venta del bono.
Si falla: «Elige el cliente al que pertenece el bono…» si no se dice; «Ese paquete no existe en este
negocio.» si el bono se eliminó o está desactivado; una fecha de compra futura, «Un bono no se puede
comprar en el futuro.» (alargar un bono es **Ajustar**, SERVICE-F18), y una sin zona horaria, que la
diga; un nombre de clienta que vale para varias, la lista para elegir.
Implicados: CUSTOMER-F01

### SERVICE-F15 Consultar los bonos de una clienta
<!-- origen: fi:modules/services#query-services-packages-balance old:services/workflow/bonos.md#services-f15 -->
Estado: hecho (asistente y API)
Actor: empleado, responsable, asistente
Pantalla: asistente
Pasos:
1. Pregunta al asistente por los bonos de la clienta, por su nombre o su teléfono.
2. Responde una fila por compra, con el bono, la fecha, lo pagado, las sesiones usadas y las que
   quedan, cuándo caduca y si ya caducó o se anuló; también los de una ficha unida a la suya.
Entra: la clienta (Clientes) y sus bonos vendidos.
Sale: nada; solo lectura.
Si falla: si el nombre vale para varias clientas, el asistente dice cuáles y pide que elija; si no
la encuentra, lo dice.
Implicados: SERVICE-F14, SERVICE-F28, CUSTOMER-F01

### SERVICE-F16 Ver quién ha comprado un bono
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f13 old:services/workflow/bonos.md#services-f16 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Bonos y paquetes
Pasos:
1. En la fila del bono pulsa **Bonos vendidos** (de uno eliminado, con Estado en **Eliminado**).
2. Sale una fila por compra, la más reciente primero (ver «Pantallas»).
3. **Cargar más** trae la siguiente página; **Cerrar** vuelve a la tabla.
Entra: las compras de ese bono y el nombre de cada clienta (Clientes); de una ficha eliminada, su
identificador.
Sale: nada; solo lectura. **Ajustar** y **Anular** salen donde proceden y para quien puede.
Si falla: vacía, «Nadie ha comprado este bono todavía.»; si no se puede leer, «No se han podido
cargar los bonos vendidos» con el motivo.
Implicados: SERVICE-F17, SERVICE-F18

### SERVICE-F17 Anular un bono vendido por error
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f13 old:services/workflow/bonos.md#services-f17 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Bonos y paquetes
Pasos:
1. En **Bonos vendidos**, en la compra equivocada pulsa **Anular** (solo sale si no se ha gastado
   ninguna sesión).
2. Lee «¿Anular este bono?»: «El bono del cliente {customer} ({amount}) deja de poder usarse y queda
   en la lista como anulado. El dinero no se devuelve aquí: si se cobró, devuelve la venta desde
   Ventas con una devolución.».
3. Escribe el Motivo (obligatorio) y pulsa **Anular**.
Entra: la compra y el motivo.
Sale: el bono deja de poder gastarse y queda como rastro, con quién, cuándo y el motivo
(`service.grant.voided`). No mueve dinero ni emite documento.
Si falla: «Ese bono ya se ha usado: no se puede anular.», «Ese bono ya estaba anulado.» o «Indica
por qué se anula este bono: el motivo queda en su registro.». Si otra caja gasta una sesión a la vez,
la anulación espera y recibe el motivo real.
Implicados: SERVICE-F16, SALE-F32

### SERVICE-F18 Regalar sesiones, alargar la caducidad o corregir el saldo
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 old:services/workflow/bonos.md#services-f18 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Bonos y paquetes
Pasos:
1. En **Bonos vendidos** pulsa **Ajustar** en una compra viva con límite de sesiones o caducidad.
2. Elige **Añadir sesiones** o **Quitar sesiones** y cuántas (hasta 100; quitar, hasta las que le
   quedan), y/o «Días que se alarga» (hasta 366).
3. Escribe el Motivo y revisa «Tras el ajuste: quedan {remaining} sesión(es) · caduca el {when}».
4. Pulsa **Ajustar**.
Entra: la compra, las cantidades y el motivo.
Sale: un movimiento aparte con quién, cuándo, cuánto y por qué (`service.grant.adjusted`), que sale en
**Movimientos** como **Cortesía** o **Corrección**; la compra no se reescribe. Revive un bono caducado
o agotado.
Si falla: «Indica por qué se ajusta este bono…», «Añade o quita al menos una sesión, o añade al menos
un día.», «No puedes quitar más sesiones de las que le quedan al cliente.», «Ese bono no tiene límite
de sesiones…», «Ese bono no caduca…» o «Ese bono ya estaba anulado.».
Implicados: SERVICE-F16, SERVICE-F20

### SERVICE-F19 Ver los movimientos de un bono
<!-- origen: old:services/workflow/bonos.md#services-f19 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Bonos y paquetes
Pasos:
1. En la fila del bono pulsa **Movimientos**.
2. Sale cada sesión entregada y cada ajuste, el más reciente primero (ver «Pantallas»); **Cargar
   más** trae los siguientes, cada movimiento una sola vez aunque varios lleven la misma hora.
Entra: las sesiones y los ajustes de ese bono.
Sale: nada; solo lectura.
Si falla: vacía, «Este bono aún no se ha usado.»; si no se puede leer, «No se han podido cargar los
movimientos» con el motivo.
Implicados: SERVICE-F18, SERVICE-F21, SERVICE-F22

### SERVICE-F20 Un bono caduca
<!-- origen: old:services/workflow/bonos.md#services-f20 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un bono con «Vigencia (días)» caduca ese número de días después de su compra, más los días
   regalados con **Ajustar**.
2. Desde ese momento gastarlo se rechaza con «Este bono ha caducado.»; sus sesiones sin usar se quedan
   y **Ajustar** lo revive.
Entra: la fecha de compra, la vigencia vendida y los días regalados.
Sale: nada se escribe al caducar.
Si falla: nada falla al caducar; gastarlo después se rechaza con «Este bono ha caducado.».
Implicados: SERVICE-F18, SERVICE-F21

### SERVICE-F21 Gastar una sesión fuera del cobro
<!-- origen: fi:modules/services#command-services-packages-redeem-sql-transaccional fi:modules/services#query-services-packages-redeem_check old:services/workflow/bonos.md#services-f21 -->
Estado: hecho (asistente y API)
Actor: empleado, responsable, asistente
Pantalla: asistente
Pasos:
1. Si quieres, pregunta antes al asistente si se podría gastar una sesión de ese bono y por qué no.
2. Pide al asistente que gaste una sesión de un bono comprado por la clienta, y si quieres que diga
   qué servicio se hizo y la enlace a la cita o a la venta.
Entra: la compra del bono; el servicio, la cita y la venta, como referencia.
Sale: una sesión **Entregada** al momento (`service.grant.redeemed`), que cuenta contra los «Usos».
No emite documento fiscal.
Si falla: «Este bono está anulado: ya no se puede usar.», «Este bono ya no tiene sesiones
disponibles.», «Este bono ha caducado.», «Este bono no cubre ese servicio. Un bono de cortes paga
cortes, no el champú.» o «Esa venta de bono no existe en este negocio.». Dos cajas que gastan la
última sesión a la vez van en fila y la segunda recibe el motivo real.
Implicados: SERVICE-F19, SERVICE-F20

### SERVICE-F22 Pagar una línea con un bono
<!-- origen: qa:verticals/beauty/05-sale-upsell-and-payment wf:peluqueria-dia#rec_peluqueria-f10 wf:peluqueria-dia#rec_peluqueria-f11 old:services/workflow/cobro-y-devolucion.md#services-f22 -->
Estado: hecho (con Ventas, SALE-F27)
Actor: empleado, responsable
Pantalla: Ventas: Cobro
Pasos:
1. Con la clienta asignada a la cuenta, abre el cobro. En «Líneas pagadas de otra forma», cada línea
   de un servicio enseña «Pagar esta línea con un bono» con los bonos de esa clienta que cubren ese
   servicio, tienen sesiones y no han caducado (también los de un bono eliminado del catálogo y los de
   una ficha unida a la suya). Una línea de varias unidades se separa antes («Separar en {n} líneas»).
2. Viene elegido el bono que se gasta primero, con el porqué: primero uno con sesiones contadas antes
   que uno ilimitado, después el que antes caduca, el ya empezado, al que le quedan menos sesiones y
   el comprado antes. Con dos o más dice «{count} bonos válidos». Toca otra tarjeta para gastar otro.
3. Revisa «Quedan {before} sesiones · {after} después de esta» y pulsa **Gastar una sesión**.
4. Sale «{name}: sesión gastada. Quedan {after}.» y la línea pasa a 0,00 € con «Ya pagado · {name}»; el
   importe del cobro baja. **Deshacer** la devuelve mientras la venta no esté cobrada.
5. Cobra lo demás con su medio (SERVICE-F24). Cerrar el cobro, aparcar la cuenta o recargar la
   pantalla no cambia nada: la marca vive en la línea de la cuenta, así que al volver la línea sigue
   pagada con el bono y el hueco enseña la sesión gastada con **Deshacer**.
Entra: la clienta, la cuenta, la línea y su servicio (Ventas); los bonos de la clienta (Servicios).
Sale: una sesión **Reservada** para esa línea durante un día (`service.session.reserved`), que cuenta
como usada y ya no se puede gastar en otra línea; la línea de la cuenta, pagada con el bono. No emite
documento fiscal: el bono se declaró al venderlo.
Si falla: si no se pueden leer los bonos, «No se han podido cargar los bonos del cliente. Inténtalo
otra vez antes de cobrar el precio completo.» con **Reintentar**, nunca «no tiene bonos». Sin bonos:
«Este cliente no tiene ningún bono que cubra este servicio.». Al gastar: «Este bono ya no tiene
sesiones disponibles.», «Este bono ha caducado.», «Este bono está anulado: ya no se puede usar.» o
«Este bono no cubre ese servicio…». Si otra caja gasta a la vez la última sesión, la segunda espera y
recibe el motivo real. **Deshacer** tras cobrar: «Esa sesión del bono ya no se puede soltar: la venta
está cobrada. Devolverla es una devolución.». Sin Servicios activa, o sin permiso para gastar
sesiones, el hueco no aparece.
Implicados: SALE-F27, CUSTOMER-F17

### SERVICE-F23 Soltar la sesión si la línea o la cuenta desaparecen
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f10 old:services/workflow/cobro-y-devolucion.md#services-f23 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Ventas: Vender, Cobro
Pasos:
1. Quien cobra pulsa **Deshacer** en el hueco, quita de la cuenta la línea pagada con el bono, la
   anula si ya se envió a cocina o elimina la cuenta entera.
2. Ventas suelta la sesión reservada de esa línea en la misma operación.
3. En **Movimientos** la sesión sale como **Liberada**.
Entra: la sesión reservada de la línea (la guarda la línea de la cuenta).
Sale: la sesión de vuelta en el bono al momento (`service.session.released`). Soltar una sesión ya
liberada o caducada no cambia nada. Dividir o juntar cuentas no la toca: la sesión va con su línea.
Si falla: una sesión ya cobrada no se suelta (ver arriba). Si Servicios no está activa en ese momento,
la línea se quita igual y la sesión vuelve sola al cabo de un día (SERVICE-F25).
Implicados: SALE-F18, SALE-F20, SALE-F27

### SERVICE-F24 Dar por gastadas las sesiones al cobrar
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f10 old:services/workflow/cobro-y-devolucion.md#services-f24 -->
Estado: hecho (conceder los bonos vendidos en el tique, no: ver «Lo que queda fuera»)
Actor: empleado, responsable
Pantalla: Ventas: Cobro
Pasos:
1. Se cobra una cuenta (entera o unas líneas) con líneas pagadas con bono.
2. En la misma operación del cobro, Ventas da por **Entregada** la sesión de cada línea pagada con
   bono que entra en ese cobro, enlazada a la venta. Las líneas que no entran en este cobro conservan
   su sesión reservada para cuando se cobren (SALE-F22).
3. Desde ese momento la sesión ya no se suelta: solo vuelve con una devolución (SERVICE-F26) o
   anulando la venta (SERVICE-F27).
Entra: las sesiones reservadas de las líneas cobradas, la venta y su clienta (Ventas).
Sale: las sesiones gastadas para siempre y enlazadas a la venta (`service.session.settled`). Repetir
el cobro con la misma clave no gasta dos veces.
Si falla: nada se cobra y la cuenta sigue igual si una sesión ya no está reservada («La sesión
reservada de «{name}» ya no está reservada (pasó su día o se soltó). Quita el bono de la línea y vuelve
a aplicarlo.»), si la venta no es de la titular del bono («El bono «{name}» es de otro cliente: cobra la
venta a nombre de su titular o quita el bono de la línea.»). Si Servicios no está activa en el
negocio, tampoco se cobra.
Implicados: SALE-F01, SALE-F22, SALE-F27

### SERVICE-F25 La sesión retenida que nadie cobra vuelve sola
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f10 old:services/workflow/cobro-y-devolucion.md#services-f25 -->
Estado: hecho (al leer y con la tarea de cada hora)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una sesión reservada en un cobro tiene un día de plazo para cobrarse (por ejemplo, una cuenta
   aparcada y olvidada).
2. Pasado el plazo deja de contar en el saldo del bono al momento; la tarea de cada hora la marca como
   **Caducada** en **Movimientos**.
3. Si se vuelve a esa cuenta, la línea sigue marcada, pero cobrarla se rechaza (SERVICE-F24): se
   deshace el bono y se vuelve a aplicar.
Entra: las sesiones reservadas sin cobrar y su plazo.
Sale: la sesión de vuelta en el bono (`service.session.expired`, uno por sesión, cuando la tarea las
marca).
Si falla: si la tarea no corre, la sesión vuelve igual en cuanto pasa el plazo: el saldo no la cuenta.
Implicados: SALE-F17

### SERVICE-F26 Devolver la sesión al devolver la venta
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 old:services/workflow/cobro-y-devolucion.md#services-f26 qa:verticals/beauty/08-edge-cases -->
Estado: hecho (con Ventas, SALE-F32)
Actor: responsable
Pantalla: Ventas: Devolver
Pasos:
1. En **Ventas**, pulsa **Devolver** en la venta (también en una pagada entera con bono, a 0,00 €).
2. En «Qué se devuelve», cada línea pagada con bono dice «Ya pagado · {name}». Márcala: «La sesión
   vuelve a {name}.».
3. Pulsa el botón de devolver: se puede devolver solo la sesión, sin dinero.
Entra: las sesiones gastadas en esa venta (las guarda cada línea de la venta).
Sale: la sesión de vuelta en el bono, con quién, cuándo y el documento de devolución
(`service.session.returned`); en **Movimientos**, **Devuelta**. No mueve dinero ni emite documento;
si el bono ya caducó, la sesión consta pero no se puede gastar hasta alargarlo (SERVICE-F18). La
misma devolución repetida devuelve una sola sesión.
Si falla: «Esa sesión ya se devolvió en otra devolución.». Si Servicios no está activa en el negocio,
la devolución se rechaza entera.
Implicados: SALE-F31, SALE-F32

### SERVICE-F27 Devolver la sesión al anular la venta
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:peluqueria-dia#rec_peluqueria-f13 old:services/workflow/cobro-y-devolucion.md#services-f27 -->
Estado: hecho (anular los bonos vendidos en ella, no: ver «Lo que queda fuera»)
Actor: responsable
Pantalla: Ventas: Anular venta
Pasos:
1. Un responsable anula en Ventas una venta cobrada (SALE-F30).
2. En la misma operación, cada sesión gastada en esa venta vuelve a su bono, aunque haya caducado.
3. En **Movimientos** cada una sale como **Devuelta**, con quien anuló, la hora y el motivo.
Entra: la venta anulada, quién y el motivo; las sesiones gastadas en esa venta.
Sale: las sesiones de vuelta en su bono (`service.session.returned`). No mueve dinero ni emite
documento fiscal.
Si falla: repetir la anulación no devuelve dos veces. Si Servicios no está activa en el negocio, la
venta no se anula y se avisa en la ventana.
Implicados: SALE-F30

### SERVICE-F28 Unir dos fichas: los bonos pasan a la que queda
<!-- origen: old:services/workflow/fichas-de-clienta.md#services-f28 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Clientes alguien une dos fichas de la misma persona.
2. Al momento, los bonos de la ficha absorbida ya salen entre los de la que queda (SERVICE-F15) y el
   cobro los acepta: ninguno queda invisible ni sin poder gastarse, y ninguno sale dos veces.
3. En unos segundos, Servicios pasa a la ficha que queda todos los bonos de la absorbida (vivos y
   anulados), con sus sesiones y sus ajustes.
Entra: la ficha que queda y la absorbida (avisa Clientes: `customer.customer.merged`).
Sale: los bonos apuntando a la ficha que queda (`service.grant.reassigned`); si dos compras son del
mismo bono, quedan dos, cada una con su saldo y su caducidad.
Si falla: repetir el aviso no cambia nada.
Implicados: CUSTOMER-F13, SERVICE-F15, SERVICE-F22

### SERVICE-F29 Eliminar o anonimizar una ficha: sus bonos quedan sin cliente
<!-- origen: old-hub:HUB-F250 old:services/workflow/fichas-de-clienta.md#services-f29 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. En Clientes un administrador elimina una ficha o borra sus datos personales.
2. Sus bonos vivos pasan a **Bonos sin cliente** (SERVICE-F30) con la fecha en que se eliminó.
3. Si se borraron sus datos personales (RGPD), Servicios vacía los textos libres de sus bonos: la nota
   de la compra, el motivo de una anulación, el motivo de cada ajuste y la nota y el motivo de
   devolución de cada sesión.
Entra: la ficha eliminada o anonimizada (Clientes; al anonimizar avisa `customer.customer.erased`).
Sale: el bono conserva la referencia de la ficha, que es lo que lo casa con la venta que lo pagó;
sesiones, importes y movimientos no cambian. Al anonimizar, los textos libres vacíos
(`service.grant.erased`). Los anulados no salen en la lista.
Si falla: repetir el aviso no cambia nada.
Implicados: CUSTOMER-F07, CUSTOMER-F16

### SERVICE-F30 Rescatar los bonos sin cliente
<!-- origen: old:services/workflow/fichas-de-clienta.md#services-f30 -->
Estado: hecho (la lista; un bono no se pasa a otra ficha)
Actor: responsable
Pantalla: Bonos y paquetes
Pasos:
1. Pulsa **Bonos sin cliente**.
2. Sale cada bono cuya ficha se eliminó o se anonimizó, el más reciente primero (ver «Pantallas»). No
   hay nombre, correo ni teléfono.
3. Para devolver el dinero, busca la venta en **Ventas** y haz una devolución; para anular el bono si
   no se usó, ábrelo desde **Bonos vendidos** de ese bono, donde sale con su referencia.
Entra: los bonos vivos de fichas eliminadas o anonimizadas.
Sale: nada; solo lectura.
Si falla: vacía, «Ningún bono se ha quedado sin cliente.»; si no se puede leer, «No se han podido
cargar los bonos sin cliente.».
Implicados: SERVICE-F29, SERVICE-F17

### SERVICE-F31 Asignar un profesional a un servicio
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f03 old:staff/workflow/disponibilidad.md#staff-f10 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Servicios (Editando servicio)
Pasos:
1. Abre el servicio: en «Profesionales que lo hacen» sale la lista o «Nadie asignado todavía: lo
   puede hacer todo el equipo reservable.».
2. En «Añadir profesional…» elige a alguien de Personal (salen los que aún no lo tienen) y, si
   quieres, sus «Minutos (opcional)» y su precio propio, «Precio (<moneda>, opcional)» (en la moneda del
   negocio: «Precio (EUR, opcional)» en España; «Precio (opcional)» mientras el negocio no contesta).
3. Pulsa **Asignar**.
Entra: el servicio y la ficha del profesional (Personal).
Sale: la asignación, activa y no principal (`service.assignment.assigned`). Citas la lee para filtrar
los profesionales de un servicio y tomar su duración y su precio propios, y Ventas cobra ese precio
propio (SALE-F38). Asignar otra vez a la misma persona (asistente o API) cambia sus minutos y su precio;
su servicio principal solo cambia si se dice.
Si falla: dentro de la sección, «Ese miembro del personal no existe en este negocio.», un nombre que
vale para varios (la lista para elegir) o el importe ilegible o negativo. Mientras llega la lista sale
«Cargando…»; si no se puede leer, «No se han podido cargar los profesionales.» con el motivo y
«Reintentar», nunca «Nadie asignado todavía».
Implicados: STAFF-F01, SALE-F38

### SERVICE-F32 Cambiar o quitar un profesional de un servicio
<!-- origen: old:staff/workflow/disponibilidad.md#staff-f11 -->
Estado: hecho
Actor: responsable, asistente
Pantalla: Servicios (Editando servicio)
Pasos:
1. En «Profesionales que lo hacen», cambia los «Minutos (opcional)» o el «Precio (<moneda>, opcional)» de
   una persona y pulsa **Guardar**.
2. Pulsa «Hacerlo su servicio principal»: sale «Servicio principal» (uno por persona, el anterior deja
   de serlo).
3. Apaga «Lo hace» para que deje de hacerlo sin quitarla, o pulsa «Quitar».
4. Si en Personal se da de baja a una persona, deja de salir al momento en «Profesionales que lo hacen»
   y en quién puede hacerlo (SERVICE-F33), y en unos segundos Servicios la quita sola de todos los
   servicios que hacía.
Entra: la asignación.
Sale: el cambio (`service.assignment.updated`, `service.assignment.removed`). Dar de baja a una
persona en Personal la quita de todos los servicios que hacía.
Si falla: «Esa asignación no existe en este negocio.».
Implicados: SERVICE-F31, SERVICE-F33, STAFF-F06

### SERVICE-F33 Saber quién puede hacer un servicio
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f06 wf:whatsapp-cita#rec_wa_cita-f04 old:staff/workflow/disponibilidad.md#staff-f12 -->
Estado: hecho
Actor: sistema, asistente
Pantalla: ninguna
Pasos:
1. Quien reserva pregunta qué profesionales pueden hacer un servicio.
2. Servicios contesta con las personas **Activas** y **Reservables** con una asignación activa para
   ese servicio, con su duración y su precio propios, las de servicio principal primero y luego por
   nombre.
Entra: el servicio.
Sale: la lista, de solo lectura. Vacía quiere decir «nadie declarado» o «quien lo tiene no está
activo y reservable»: la regla «entonces lo hace todo el equipo reservable» es de Citas.
Si falla: un servicio que no existe, «Ese servicio no existe en este negocio.».
Implicados: SERVICE-F31, APPOINTMENT-F01

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y los mismos permisos. Un servicio, una categoría o un bono se
nombran por su id o por su nombre; un profesional, por su nombre; una clienta, por su nombre o su
teléfono. Si un nombre vale para varios, se dice cuáles y se pide que elija (409
`service.service_ambiguous`, `service.category_ambiguous`, `service.package_ambiguous`,
`staff.ambiguous_member`, `customer.customer_ambiguous`).

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los servicios, con búsqueda, filtros y orden, en páginas (hasta 100) | ver servicios | F01–F05 | `service.service.list` |
| Un servicio completo | ver servicios | F02, F10 | `service.service.get` |
| El catálogo para vender y reservar: los servicios en oferta | ver servicios | F09, F10 | `service.service.list_for_sale` |
| Cuántos servicios hay en oferta y cuántos se pueden cobrar | ver servicios | F01 | `service.catalog.status` |
| Las categorías, con los servicios en oferta de cada una | ver categorías | F07, F08 | `service.category.list` |
| Una categoría | ver categorías | F07 | `service.category.get` |
| Los ajustes | ver servicios | F11 | `service.settings.get` |
| Los profesionales de un servicio, o los servicios de un profesional | ver servicios | F31, F32 | `service.assignment.list` |
| Quién puede hacer un servicio | ver servicios | F33 | `service.assignment.eligible` |
| Los bonos del catálogo (y los eliminados que alguien compró) | ver bonos | F12, F13 | `service.package.list` |
| Un bono con sus líneas | ver bonos | F13 | `service.package.get` |
| Los bonos vendidos, de un bono o de una clienta, con su saldo | ver saldos de bonos | F15, F16 | `service.grant.list` |
| Los bonos sin cliente | ver bonos sin cliente | F30 | `service.grant.list_orphans` |
| Si un bono vendido se puede anular y por qué no | anular bonos | F17 | `service.grant.void_check` |
| Qué se puede ajustar de un bono vendido | ajustar bonos | F18 | `service.grant.adjust_check` |
| Si se puede gastar una sesión y por qué no | gastar sesiones | F21 | `service.grant.redeem_check` |
| Los bonos de una clienta que pueden pagar un servicio, el que se gasta primero y por qué | gastar sesiones | F22 | `service.grant.tender_options` |
| Los movimientos de un bono | ver saldos de bonos | F19 | `service.movement.list` |

Todas, menos las comprobaciones, se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Da de alta un servicio | dar de alta servicios | F01, F03 | `service.service.create` |
| Da de alta hasta 500 servicios de golpe | editar servicios | F06 | `service.service.bulk_create` |
| Cambia un servicio (solo lo enviado) | editar servicios | F02, F03 | `service.service.update` |
| Archiva un servicio | archivar servicios | F04 | `service.service.archive` |
| Restaura un servicio archivado | editar servicios | F05 | `service.service.restore` |
| Crea una categoría | crear categorías | F07 | `service.category.create` |
| Cambia una categoría (solo lo enviado) | editar categorías | F07 | `service.category.update` |
| Elimina una categoría | eliminar categorías | F08 | `service.category.delete` |
| Guarda los ajustes (solo lo enviado) | ajustes | F11 | `service.settings.update` |
| Asigna un profesional a un servicio (o cambia su asignación) | editar servicios | F31 | `service.assignment.assign` |
| Cambia una asignación | editar servicios | F32 | `service.assignment.update` |
| Quita una asignación | editar servicios | F32 | `service.assignment.remove` |
| Crea un bono con sus líneas | crear bonos | F12 | `service.package.create` |
| Cambia un bono (solo lo enviado; las líneas no) | editar bonos | F13 | `service.package.update` |
| Elimina un bono del catálogo | eliminar bonos | F13 | `service.package.delete` |
| Concede un bono a una clienta | conceder bonos | F14 | `service.grant.create` |
| Anula un bono vendido sin usar | anular bonos | F17 | `service.grant.void` |
| Regala o quita sesiones, o alarga la caducidad | ajustar bonos | F18 | `service.grant.adjust` |
| Gasta una sesión | gastar sesiones | F21 | `service.grant.redeem` |
| Reserva una sesión de un bono para una línea de la cuenta (la llama Ventas) | gastar sesiones | F22 | `service.session.hold` |
| Suelta una sesión reservada (la llama Ventas) | gastar sesiones | F23 | `service.session.release` |
| Da por gastadas las sesiones reservadas de una venta cobrada (la llama Ventas) | gastar sesiones | F24 | `service.session.settle` |
| Marca como caducadas las reservas vencidas (tarea de cada hora) | sistema | F25 | `service.session.expire` |
| Devuelve al bono sesiones gastadas en una venta anulada o devuelta (la llama Ventas) | devolver sesiones | F26, F27 | `service.session.return` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Servicio nuevo | Alta (uno por servicio en el alta de golpe) | Cuál (`id`) y su nombre | `service.service.created` |
| Servicio cambiado | Edición con algún cambio | Cuál (`id`) | `service.service.updated` |
| Servicio archivado | Archivar | Cuál (`id`) | `service.service.archived` |
| Servicio restaurado | Restaurar | Cuál (`id`) | `service.service.restored` |
| Categoría nueva / cambiada / eliminada | Crear, editar, eliminar | Cuál (`id`) | `service.category.created`, `.updated`, `.deleted` |
| Ajustes cambiados | Guardar con algún cambio | Nada | `service.settings.updated` |
| Profesional asignado / cambiado / quitado | Asignar, cambiar, quitar (también al dar de baja a alguien) | La asignación, el servicio y el profesional | `service.assignment.assigned`, `.updated`, `.removed` |
| Bono nuevo / cambiado / eliminado | Crear, editar, eliminar | Cuál (`id`) | `service.package.created`, `.updated`, `.deleted` |
| Bono concedido | Conceder | La compra, el bono y la clienta | `service.grant.granted` |
| Bono anulado | Anular | La compra, el bono y la clienta, sin el motivo | `service.grant.voided` |
| Bono ajustado | Ajustar | La compra y las cantidades, sin el motivo | `service.grant.adjusted` |
| Sesión gastada | Gastar | La compra, la sesión y el servicio | `service.grant.redeemed` |
| Sesión reservada / soltada / caducada | Reservar en el cobro, soltarla, la tarea de cada hora | La sesión y la compra | `service.session.reserved`, `.released`, `.expired` |
| Sesión entregada al cobrar | Cobrar la venta | La sesión, la compra y la venta | `service.session.settled` |
| Sesión devuelta | Anular o devolver la venta | La sesión, la compra y el documento, sin el motivo | `service.session.returned` |
| Bonos reasignados | Unir dos fichas | La ficha que queda y la absorbida | `service.grant.reassigned` |
| Textos de los bonos vaciados | Anonimizar una ficha con bonos con texto | La ficha | `service.grant.erased` |

### A qué reacciona y lo que necesita de otras apps

| Aviso de otra app | Qué hace Servicios | Flujos |
|---|---|---|
| `staff.member.terminated` (Personal) | Quita a esa persona de todos los servicios | F32 |
| `customer.customer.merged` (Clientes) | Pasa los bonos de la ficha absorbida a la que queda | F28 |
| `customer.customer.erased` (Clientes) | Vacía los textos libres de los bonos de esa ficha (RGPD) | F29 |

De Impuestos lee las categorías fiscales; de Personal, las fichas (nombre, si está activa y es
reservable); de Clientes, el nombre de la titular y si su ficha se eliminó.

### Contrato con Ventas

Ventas no depende de Servicios (Servicios no está en sus `requires`): usa sus operaciones por nombre,
con la sesión de quien vende, como hace con Inventario.

- **Vender un servicio (F09)**: `service.service.list_for_sale` (búsqueda, `category_id`, páginas de
  hasta 100) da por servicio `id`, `name`, `pricing_type`, `price`, `min_price`, `max_price`,
  `duration_minutes`, `category_id`, `category_name`, `tax_category_id`, `tax_category_key` y
  `needs_tax_setup` (sin categoría fiscal viva: no se vende). `service.service.get` da uno, también
  archivado. Al cobrar, la categoría fiscal de la línea es la de `tax_category_key`. Con la profesional de
  la línea, un servicio de precio fijo se cobra a su precio propio si su asignación activa lo tiene
  (`service.assignment.list` con `service_id` y `member_id`).
- **El bono en el cobro y en la devolución (F22–F27)**: Ventas llama por su nombre, con la sesión de
  quien cobra (su permiso y la app activa los comprueba cada operación), y **en la misma transacción**
  que su propia escritura, sin esperar a ningún aviso:
  - al pagar una línea con un bono, `service.session.hold` (`grant_id`, `service_id`,
    `order_line_id`) y guarda en la línea la sesión que le devuelve;
  - al deshacerlo, quitar la línea, anularla o eliminar la cuenta, `service.session.release` (`id`);
  - al cobrar, `service.session.settle` (`ids` de las líneas cobradas, `sale_id`, `customer_id` de la
    venta);
  - al anular la venta, `service.session.return` con todas sus sesiones (`reference` = la venta) y,
    al devolverla, con las de las líneas que vuelven (`reference` = la devolución).
  Para pintar el hueco, el cobro lee `service.grant.tender_options` (`customer_id`, `service_id`).
  Servicios guarda la venta y la línea de la cuenta como identificadores opacos (`sale_id`,
  `order_line_id`): Ventas no es requisito de Servicios ni Servicios de Ventas.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver servicios, ajustes y profesionales asignados | sí | sí | sí | sí | `service.view_service` |
| Dar de alta servicios | sí | sí | sí | sí | `service.add_service` |
| Editar y restaurar servicios, alta de golpe y asignar profesionales | sí | sí | sí | no | `service.change_service` |
| Archivar servicios | sí | sí | no | no | `service.delete_service` |
| Ver categorías | sí | sí | sí | sí | `service.view_category` |
| Crear categorías | sí | sí | sí | no | `service.add_category` |
| Editar categorías | sí | sí | sí | no | `service.change_category` |
| Eliminar categorías | sí | sí | no | no | `service.delete_category` |
| Ver bonos | sí | sí | sí | sí | `service.view_package` |
| Crear bonos | sí | sí | sí | no | `service.add_package` |
| Editar bonos | sí | sí | sí | no | `service.change_package` |
| Eliminar bonos | sí | sí | no | no | `service.delete_package` |
| Conceder bonos | sí | sí | sí | sí | `service.grant_package` |
| Gastar sesiones | sí | sí | sí | sí | `service.redeem_package` |
| Ver bonos vendidos, saldos y movimientos | sí | sí | sí | sí | `service.view_package_balance` |
| Ver bonos sin cliente | sí | sí | sí | no | `service.view_orphan_grant` |
| Anular bonos vendidos | sí | sí | sí | no | `service.void_grant` |
| Ajustar bonos vendidos | sí | sí | sí | no | `service.adjust_grant` |
| Devolver sesiones al anular o devolver una venta | sí | sí | sí | no | `service.return_session` |
| Ajustes | sí | sí | no | no | `service.manage_settings` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero del producto actual es un empleado: lo que tenía (ver, gastar y conceder) lo tiene el empleado.

## Para quien lo mantiene

- Anatomía completa de una app (copia de `apps/tax`): `apps.py`, `models.py`, `migrations/`,
  `schemas.py`, `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`,
  `frontend/` y un `tests/test_<fichero>.py` por fichero, más `tests/test_integration_tax.py`,
  `test_integration_staff.py`, `test_integration_customer.py` (con las apps reales, sin dobles),
  `test_relay.py` (los avisos de Clientes y Personal por el relay real del worker, con dos hubs) y
  `test_concurrency.py` (hilos).
- **`requires = ["tax", "staff", "customer"]`**: `Service.tax_category` y
  `ServiceSettings.default_tax_category` son claves ajenas a `tax.TaxCategory`;
  `Assignment.member`, a `staff.Member`; `Grant.customer`, a `customer.Customer`. Los nombres se
  resuelven con `apps.staff.queries.resolve_member` y `apps.customer.queries.find_customer`. La venta
  y la cita de una sesión o de una compra son identificadores opacos (`sale_id`, `appointment_id`),
  sin clave ajena: Ventas y Citas no son requisito (como `sale` guarda `staff_id`).
- Modelos: `ServiceSettings` (una fila, restricción `service_settings_singleton`), `Category`,
  `Service`, `Assignment`, `Package`, `PackageItem`, `Grant`, `GrantAdjustment` y `Redemption`.
  UUIDv7, sin `hub_id`. Dinero en unidades menores enteras de la moneda del negocio (céntimos en euros; el
  yen no tiene), nunca negativo, la misma unidad que cobra Ventas (service-business-currency: la pantalla la
  lee y la escribe con `useBusinessMoney` de `base`); el descuento en porcentaje, en
  puntos básicos (1050 = 10,50 %).
- **Archivar y eliminar son lógicos**: un servicio archivado (`is_active = False`, `archived_at`),
  una categoría o un bono eliminados (`is_deleted`) siguen en la base de datos. Una categoría
  eliminada suelta sus servicios y sube sus subcategorías a su padre en la misma transacción.
- **Nombres únicos** entre los vivos, sin distinguir mayúsculas: categorías
  (`service_category_live_name_unique`) y bonos (`service_package_live_name_unique`); el servicio lo
  comprueba antes para dar el 409 y traduce la violación (dos guardados a la vez) al mismo 409.
- **Saldo de un bono vendido**: usos = los congelados + la suma de los ajustes; usadas = las sesiones
  entregadas más las reservadas cuyo plazo no ha vencido; quedan = usos − usadas (sin límite si los
  usos congelados son nulos); caduca = compra + vigencia congelada + días regalados. Se calcula al
  leer, no se guarda.
- **Estados de una sesión** (`Redemption.status`): `held` (reservada para una línea de la cuenta,
  `order_line_id`, hasta `hold_until`, un día) → `consumed` (entregada: la venta, `sale_id` y
  `settled_at`) | `released` (soltada) | `expired` (vencida, la marca la tarea); `consumed` →
  `returned` (devuelta, con `return_reference` = la devolución o la venta anulada y su motivo). Una
  sesión gastada fuera del cobro (F21) nace `consumed`. Una línea tiene como mucho una sesión viva
  (`held` o `consumed`): restricción `service_redemption_one_per_line`. `ended_at` y `ended_by` dicen
  cuándo y quién la soltó, la marcó vencida o la devolvió.
- **Concurrencia**: gastar, reservar, entregar, devolver, anular y ajustar bloquean primero la fila de
  la compra (`select_for_update`, en orden de id cuando son varias): dos cajas sobre el mismo bono van
  en fila y la segunda decide sobre lo que dejó la primera. Una escritura que nombra una fila (crear, dar
  de alta de golpe o editar un servicio con su categoría fiscal o su categoría, los ajustes, la categoría
  padre, asignar un profesional, las líneas de un bono, vender un bono y unir fichas) la retiene hasta su
  COMMIT: la categoría fiscal con la lectura retenida de Impuestos (`FOR KEY SHARE`), las filas propias con
  `FOR NO KEY UPDATE` en orden de id y la ficha con el bloqueo de Clientes. Su «Eliminar», archivarla o el
  borrado del admin esperan a la escritura, y una ya en curso se rechaza como una borrada antes (el mismo
  422 o 404). El orden evita las esperas en círculo: el borrado del admin de una categoría entra como su
  «Eliminar», bloqueando antes todas las categorías vivas, y luego vacía lo que la nombraba (sus servicios y
  subcategorías), ya con lo que dejó la escritura; editar un servicio retiene lo que nombra antes que su
  propia fila; asignar bloquea la asignación que ya existía antes de retener el servicio, el orden en que el
  borrado del admin de un servicio borra sus asignaciones y después el servicio. Hay tests con hilos de cada
  carrera.
- **Tareas programadas**: `scheduled_tasks` del `AppConfig` declara `service.session.expire` cada
  hora (`0 * * * *`, UTC, `collapse`); hecho — la corre el worker (`base/scheduler.py`, 2026-10-15; en la
  fase 1, sobre un solo hub). Además, el saldo ya no cuenta una reserva vencida y reservar de nuevo la misma
  línea marca antes la vencida.
- **Bonos sin cliente** se calculan desde la ficha de Clientes (eliminada o anonimizada, y no unida a
  otra): no hace falta sellar nada al eliminarla. Unir dos fichas mueve los bonos con la reacción a
  `customer.customer.merged`; hasta que el relay la entrega (el siguiente tick del worker, o el
  reintento si falla), `service.grant.list`, `service.grant.tender_options` y el cobro leen también
  los de las fichas unidas a ella (Clientes deja la cadena en un nivel). Un bono tiene un solo dueño,
  así que antes y después del movimiento sale una sola vez. Anonimizar vacía sus textos libres con la
  reacción a `customer.customer.erased` (manda el WORKBOOK de Clientes). Igual con las bajas: quien
  está de baja en Personal ya no sale en las listas desde el momento de la baja, y la reacción a
  `staff.member.terminated` borra después sus asignaciones.
- **Árbol de categorías**: mover o eliminar una categoría bloquea antes todas las categorías vivas en
  orden de id (dos movimientos a la vez van en fila y el segundo ve el árbol que dejó el primero); el
  recorrido hacia arriba guarda las visitadas, así que un bucle que dejara una escritura cruda se
  rechaza (409 `service.category_cycle`) en vez de dar vueltas. El admin rechaza también un padre que
  cerraría un bucle.
- **Fecha de compra de un bono**: nunca en el futuro (5 minutos de margen de reloj) y con zona horaria;
  alargar un bono es **Ajustar**, con sus límites.
- **Reacciones**: el relay del outbox (`base/relay.py`, en cada tick del worker) entrega cada aviso de
  `REACTIONS` a `events.react(scope, name, payload)`, que ejecuta la operación de esta app que
  reacciona, como el sistema, en el hub del aviso y en su propia transacción; las tres son
  idempotentes (un aviso entregado otra vez no escribe nada ni anota otro evento). Sus operaciones
  piden `service.system`, que no tiene ningún papel.
- Asistente: toda operación declara `ai` (descripción; en las acciones, `risk`: `high` en archivar,
  eliminar categorías y bonos, anular, ajustar, alta de golpe y ajustes) y todo campo de entrada su
  `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre todos los modelos (ronda 12, PLAN §17);
  una escritura cruda del admin no pasa por las reglas ni deja aviso, salvo la del árbol de categorías.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo. Todas las apps están encendidas en todos los
  negocios (`base.relay.active_apps`): los rechazos por «Servicios no activa» de F24, F26 y F27 solo los
  ven los tests hasta que un negocio pueda apagarla (fase 2).
- Quién lee el catálogo, contado por sus llamadas (`rg '"service\.' apps`): Citas
  (`service.service.list_for_sale`, `service.assignment.eligible` y los modelos, que requiere), Ventas
  (las de «Contrato con Ventas», sin requerirla), Reservas online (`service.service.list` y `.update` en sus
  Ajustes, y los modelos con «Mostrar precios» y «Mostrar duración», que requiere) y Tarifas
  (`service.service.list` y `.get`, sin requerirla). Menús no admite servicios (solo artículos de
  Inventario) y la respuesta automática de WhatsApp lo leerá por el asistente (WHATSAPP_INBOX-F21).

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/service/services`, `/service/categories`, `/service/packages` y
  `/service/settings`; la barra de pestañas (`frontend/tabs.ts`) añade «Ajustes» solo a quien puede
  guardarlos.
- Listas en vivo con `useLiveList` (ventanas de 100 filas) y `useServerTable`; filtros por columna del
  `DataTable`; escrituras con `useCommand`; los selectores de listas largas (categoría, categoría
  fiscal, servicio, profesional) son `Combo` que buscan en el servidor.
- Las hojas de un bono (Movimientos, Bonos vendidos, Bonos sin cliente) siguen su consulta en vivo y
  crecen de 20 en 20 con **Cargar más**.

## Lo que queda fuera

- **Vender un bono en el TPV (F14) y, con ello, concederlo al cobrar (F24) y anularlo al anular o
  devolver su venta (F27)**: el TPV del producto actual tampoco lo ofrecía (solo el asistente o la API,
  con la línea marcada como servicio y el IVA que mandaba el cobro); aquí toda línea necesita una
  categoría fiscal y un bono del catálogo no la tiene. Mientras, el bono se cobra a precio libre (con
  la sección de su IVA) y se concede con la concesión (asistente o API, F14) diciendo la venta.
- **Importar servicios desde un fichero**: como en el producto actual, el alta de golpe es del
  asistente y la API.
- **El paso «Tu catálogo de servicios» de «Termina de configurar tu negocio»**: el Hub aún no tiene
  esa lista; la consulta `service.catalog.status` ya está.

## Lo que NO hace, a propósito

- No reserva (Citas), no cobra ni imprime (Ventas) y no calcula el IVA (Impuestos).
- No tiene variantes ni extras: la opción con precio es un suplemento (Suplementos).
- No pasa un bono de una clienta a otra ni lo comparte (ADR-0390).
- No es una tarjeta regalo: un bono paga una línea de servicio entera.
- No avisa a la clienta de que su bono va a caducar.
- Las «Sesiones» de cada línea de un bono no limitan nada: el tope es «Usos», para el bono entero
  (como en el producto actual).

## Cambios frente al producto actual

1. **Los servicios por profesional viven aquí** (antes en Personal, STAFF-F10–F12), y se asignan en
   el servicio, como en Fresha, Square o Vagaro. Se pueden cambiar los minutos y el precio de una
   asignación desde la pantalla (antes había que quitarla y volver a asignarla), y dar de baja a una
   persona la quita de sus servicios.
2. **Servicios requiere Clientes**: la titular de un bono es una ficha de Clientes.
3. **La Tarifa se elige en el formulario** (antes solo con el asistente o la API).
4. **Eliminar una categoría suelta de verdad sus servicios** y sube sus subcategorías (antes los
   servicios seguían apuntando a ella y editarlos se rechazaba); una categoría no puede colgar de una
   de sus hijas (antes solo de sí misma).
5. **«Categoría fiscal por defecto»** es una categoría de Impuestos que el formulario trae elegida y
   que toma el alta sin categoría fiscal (antes «Tipo de IVA por defecto» era un texto que nadie
   leía). Salen de los ajustes «Precios con IVA incluido» (es de Ventas) y «Moneda» (la del negocio es
   la de su país, que da la plataforma), que nadie leía.
6. **Un nombre de bono se puede reutilizar** cuando el anterior se eliminó (antes se rechazaba sin
   decir por qué), y un nombre repetido se dice («Ya hay un paquete con ese nombre.»).
7. **Gastar una sesión fuera del cobro comprueba el servicio** si se dice cuál (antes no).
8. **El alta de golpe usa los Ajustes** y avisa de cada servicio creado (antes ninguna de las dos).
9. **Bonos sin cliente**: un bono ilimitado sale «Sin límite de sesiones» (antes «Quedan 0»).
10. **El empleado concede bonos** (lo hacía el cajero, que ahora es un empleado).
11. **Anonimizar una ficha vacía los textos libres de sus bonos** (antes se quedaban, «hueco de la
    familia RGPD»), como dice el WORKBOOK de Clientes.
12. **Una compra no se puede fechar en el futuro** (antes se aceptaba cualquier fecha: un bono fechado
    en 2099 no caducaba nunca).
13. **La sesión del cobro se reserva, se entrega y se devuelve en la misma operación de Ventas**
    (antes Servicios esperaba los avisos `sale.completed`, `order.line_removed`, `order.voided`…): ya
    no hay una línea cobrada a 0 sin sesión detrás (sales#539), ni una sesión que se queda en la
    cuenta de origen al dividirla o juntarla (sales#540), ni un cobro que gasta la sesión y cobra el
    precio a la vez tras recargar (la marca vive en la línea, no en la pantalla).
14. **La sesión se devuelve también sin dinero** (antes solo junto con una devolución de dinero,
    sales#512 y sales#531): en un tique pagado entero con bono, **Devolver** devuelve la sesión.
15. **Cobrar la venta a otra clienta que la del bono se rechaza** (antes la línea se cobraba a su
    precio y la sesión volvía al bono sin avisar): lo que enseña el cobro es lo que se cobra.
16. **Devolver una sesión** pide su propio permiso, que tienen responsable, propietario y
    administrador (antes la devolvía quien hacía la devolución).
