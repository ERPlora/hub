# Workbook — Clientes (app)
Prefijo: CUSTOMER
Alcance MVP: núcleo
Estado de la app: hecha (servidor y páginas); fuera, con su motivo: la aprobación con PIN (fase 2)

> Manual de usuario y especificación de la app `customer`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en
> verde (servidor y páginas). Parte del `WORKFLOW.md` del módulo Clientes del producto actual
> (`modules-workspace/modules/customers`, `origin/main` `32b0831`, v2.3.70). La app hace lo mismo,
> corrige los fallos que ese documento tenía anotados (lista en «Cambios frente al producto actual»,
> en la parte de quien lo mantiene) y deja en «Dudas abiertas» lo que todavía no está decidido.
> Los números de flujo son los del producto actual (`CUSTOMERS-Fnn` → `CUSTOMER-Fnn`).

## Para qué sirve y para quién

Clientes es el **fichero de personas y empresas** del negocio y el dueño de su dato personal: la
ficha con el contacto y los datos fiscales, sus grupos, etiquetas y campos propios, sus notas y su
actividad, su consentimiento para recibir publicidad por cada canal y lo que ha comprado.

- En la **peluquería** es la clienta de la agenda: Citas cuelga sus visitas de la ficha y la
  reconoce cuando escribe por WhatsApp.
- En el **restaurante** es el comensal que reserva o pide factura: el TPV le pone su ficha a la
  cuenta y la factura sale con sus datos fiscales.

Es la app de la que más dependen las demás: el TPV le pide el cliente de la venta y su copia fiscal,
Citas y Reservas lo buscan por nombre o teléfono, WhatsApp lo reconoce por su número y todas se
enteran cuando se unen dos fichas o se borran los datos de una persona. Clientes no necesita ninguna
otra app.

Quién la usa:

- El **propietario** y el **administrador**: todo, también eliminar fichas y borrar datos personales.
- El **responsable**: edita fichas, une duplicados, crea y cambia grupos, etiquetas y campos (y
  elimina campos), exporta y anota en la actividad lo que traen otras apps.
- El **empleado** (también en la caja): consulta, da de alta, edita la ficha, importa, añade notas,
  asigna grupos y etiquetas, registra el consentimiento y pone el cliente a la venta.
- El **cliente** no usa estas pantallas: sus datos entran por el mostrador, el TPV o su WhatsApp.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó.

- **Teléfonos en formato internacional E.164** (UIT-T), con las reglas de **libphonenumber** de
  Google: el número sin prefijo se lee en el país del negocio, como hacen los TPV de referencia.
- **Alta de ficha** como Odoo, Shopify, Square, Toast, Lightspeed, Fresha y Holded: solo el nombre es
  obligatorio; teléfono, email y NIF a la vista y el resto a un toque.
- **Unir fichas duplicadas** como Square, Shopify, Odoo, Fresha, Lightspeed y Mindbody: una ficha se
  queda, completa sus huecos con la otra y cada app re-apunta lo suyo.
- **Cliente en el TPV** como Square, Toast, Lightspeed, Shopify POS y Fresha: buscar por nombre o
  teléfono y «+ nuevo cliente» en dos toques, sin salir de la venta.
- **Consentimiento por canal**, con la frase guardada palabra por palabra y retirarlo tan fácil como
  darlo: RGPD arts. 7 y 17 y Directrices 05/2020 del CEPD, como Shopify, Klaviyo, Mailchimp y HubSpot.
- **Borrado de datos personales** como el aviso `customers/redact` de Shopify y el buscador de
  privacidad de Odoo: se borra a la persona y se conserva lo que la ley obliga a guardar (las ventas).
- **Notas y actividad en una sola línea de tiempo**, como el «chatter» de Odoo y la línea de tiempo
  de Shopify.
- **Alergias y prueba de sensibilidad** en su propio bloque de la ficha, a la vista de quien atiende,
  como Fresha, Phorest, Timely, Vagaro, Zenoti, Mindbody, Shortcuts y Kitomba; y, por ser datos de
  salud, solo con el permiso expreso de la persona (RGPD art. 9.2.a), que se retira tan fácil como se
  da y al retirarlo se borran (arts. 7.3 y 17).
- **Permisos por acción** como los de personal de Shopify: ver, gestionar, exportar, unir, eliminar
  y borrar datos personales son permisos distintos.

## Antes de empezar

1. Encender **Clientes** en la página de apps del negocio. No necesita ninguna otra app. Con
   **Venta** aparece el buscador en el TPV y las compras se apuntan solas; con **Citas**, el
   historial de visitas en la ficha; con la **Bandeja de WhatsApp**, el reconocimiento por teléfono.
2. El país que se supone para un teléfono escrito sin prefijo es **España** mientras el negocio no
   tenga su país en los ajustes (CUSTOMER-F11).
3. Si hace falta segmentar, crear los grupos, las etiquetas (CUSTOMER-F27, F28) y los campos propios
   del negocio (CUSTOMER-F29). Marcar como obligatorios solo los imprescindibles: se exigen cada vez
   que se guarda la ficha completa (no al darla de alta).
4. Traer los clientes que ya se tienen con **Importar CSV** (CUSTOMER-F08) o darlos de alta
   (CUSTOMER-F01).
5. Comprobar en el TPV que la ficha sale en el buscador y que la venta se cobra con ella
   (CUSTOMER-F17).

⚠️ En la fase 1 el negocio es la primera parte de la dirección (`a.localhost:8000` es el negocio `a`)
y los negocios **comparten las fichas** (una sola base de datos). Lo que ya se separa es el aviso en
vivo. En la fase 2 cada negocio tendrá su base de datos.

## Pantallas

Clientes se abre desde el menú **Clientes** y tiene cuatro pestañas: **Clientes**, **Grupos**,
**Etiquetas** y **Campos**. No tiene pestaña de ajustes.

### Clientes
Arriba, cuatro cifras: «Clientes», «Activos», «VIP» e «Ingresos» (lo gastado por las fichas vivas).
Debajo, la tabla: «Nombre», «Email», «Teléfono», «Etapa» y «Gastado»; buscador «Buscar nombre,
teléfono o email…» (busca también NIF y empresa); filtros por etapa, origen, activo y gastado
(«Desde / Hasta», en euros); orden por cualquier columna; 50 por página. En la barra, **Añadir** e
**Importar CSV** a quien puede gestionar fichas, y **Exportar CSV** a quien puede exportar. Tocar
una fila abre la ficha.

### Ficha de cliente
El nombre y los botones que permite el perfil: **Editar**, **Eliminar**, **Fusionar con…** y
**Borrar datos personales**. Bloques: los datos (Email, Teléfono, NIF/CIF, Empresa, Dirección,
Etapa, Origen, Canal preferido, Compras, Gastado, Última compra, Activo, notas internas, cumpleaños,
aniversario y campos personalizados); «Grupos» y «Etiquetas» con casillas; «Consentimiento de
marketing» con una línea por canal y «Todo lo que se decidió»; «Añadir nota»; «Actividad»;
«Compras» (cada venta con su importe y su estado); y al final los bloques de otras apps (hoy, el
«Historial de visitas» de Citas).

### Grupos
Tabla «Nombre», «Descripción», «Clientes» (cuántas fichas vivas tiene), «Orden» y «Activo»; buscador
«Buscar grupo…» y filtro de activos; **Añadir** y **Editar** a quien puede configurar, **Eliminar** al
propietario y al administrador.

### Etiquetas
Tabla «Nombre», «Color», «Clientes» y «Activa»; buscador «Buscar etiqueta…»; mismas acciones que
Grupos.

### Campos
Tabla «Nombre», «Tipo», «Obligatorio» (Sí/No), «Orden» y «Activo»; buscador «Buscar campo…»; filtros
por tipo, obligatorio y activo; **Añadir**, **Editar** y **Eliminar** a quien puede configurar.

### Buscador de cliente del TPV
Vive dentro de la pantalla de venta de **Venta**: un botón «Asignar cliente» (o el nombre del cliente
ya elegido) abre un buscador por nombre, teléfono o email, con «+ Nuevo cliente «…»» (nombre y
teléfono) y **Quitar cliente**. Lo pinta Clientes; el hueco lo reserva Venta.

### Buscador de cliente del TPV · API
El componente `CustomerSearch` de Clientes (Venta lo importa por su ruta, de los componentes de Clientes).

```vue
<CustomerSearch v-model="venta.cliente" v-model:open="eligiendo" />
```

- `v-model` (`CustomerSnapshot | null`): el cliente asignado, como COPIA de su ficha fiscal en el momento:
  `customer_id`, `customer_name`, `customer_tax_id`, `customer_address` («calle, CP ciudad, país», en el
  idioma de la página) y `customer_country` (código ISO de dos letras, o vacío). `null` = sin cliente.
- `v-model:open` (opcional): abre y cierra el buscador; Venta lo pone a `true` cuando exige cliente y no hay.
- El botón dice «Asignar cliente» o el nombre del cliente. El buscador (un `ion-modal`) busca por nombre,
  teléfono o email entre las 20 primeras fichas, en vivo, y distingue «buscando», «sin resultados»,
  «caído» (con «Reintentar») y «sin permiso». Al elegir lee la ficha entera (`customer.customer.detail`);
  si no se puede leer, no asigna y lo dice. «+ Nuevo cliente «…»» (quien gestiona fichas) crea con nombre
  y teléfono; si fichas vivas ya tienen ese teléfono, las enseña y pregunta «usar o crear una nueva»
  (nunca asigna sin elegir; F12, F18). «Quitar cliente» devuelve `null`.
- No enlaza el pedido: eso es de Venta, con `customer.order.link` y `customer.order.customer` (F19).
- Mientras Venta no existe, se ve y se prueba en `/customer/preview/customer-search` (solo en el servidor
  de desarrollo; nunca en el build de producción).

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin clientes.» (o «Sin resultados» si hay búsqueda o filtro); «Sin grupos.», «Sin etiquetas.», «Sin campos personalizados.», «Sin actividad registrada.» |
| Error | El motivo con «Reintentar»; lo tecleado se conserva. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |
| Ficha que ya no está | «Este cliente ya no está disponible.» (eliminada, unida a otra o con los datos borrados). |

## Flujos

| ID | Flujo | Estado | Vertical |
|---|---|---|---|
| CUSTOMER-F01 | Dar de alta una ficha | hecho | común |
| CUSTOMER-F02 | Buscar y filtrar fichas | hecho | común |
| CUSTOMER-F03 | Abrir la ficha de un cliente | hecho | común |
| CUSTOMER-F04 | Editar la ficha y sus campos personalizados | hecho | común |
| CUSTOMER-F05 | Añadir una nota a la ficha | hecho | común |
| CUSTOMER-F06 | Poner grupos y etiquetas a una ficha | hecho | común |
| CUSTOMER-F07 | Eliminar una ficha | hecho | común |
| CUSTOMER-F08 | Importar fichas desde un CSV | hecho | común |
| CUSTOMER-F09 | Exportar las fichas a CSV | hecho | común |
| CUSTOMER-F10 | Reconocer a una persona por su número de teléfono | hecho | común |
| CUSTOMER-F11 | Guardar el teléfono en formato internacional (E.164) | hecho | común |
| CUSTOMER-F12 | Evitar fichas duplicadas de la misma persona | hecho | común |
| CUSTOMER-F13 | Unir dos fichas de la misma persona | hecho | común |
| CUSTOMER-F14 | Registrar el consentimiento de un canal | hecho | común |
| CUSTOMER-F15 | Retirar el consentimiento de un canal | hecho | común |
| CUSTOMER-F16 | Borrar los datos personales de un cliente (RGPD) | hecho | común |
| CUSTOMER-F17 | Asignar un cliente a la venta en el TPV | hecho | común |
| CUSTOMER-F18 | Crear un cliente desde el buscador del TPV | hecho | común |
| CUSTOMER-F19 | Enlazar el cliente al pedido abierto | hecho | común |
| CUSTOMER-F20 | Sumar la compra a la ficha al cobrar | hecho | común |
| CUSTOMER-F21 | Restar una venta anulada | hecho | común |
| CUSTOMER-F22 | Restar una devolución | hecho | común |
| CUSTOMER-F23 | Ver el historial de compras de un cliente | hecho | común |
| CUSTOMER-F24 | Ver en la ficha lo que otras apps saben del cliente | hecho | común |
| CUSTOMER-F25 | Crear la clienta sin salir de la agenda | hecho | peluquería |
| CUSTOMER-F26 | Crear la ficha de quien pide cita por WhatsApp | parcial | peluquería |
| CUSTOMER-F27 | Crear, cambiar y eliminar grupos de clientes | hecho | común |
| CUSTOMER-F28 | Crear, cambiar y eliminar etiquetas de clientes | hecho | común |
| CUSTOMER-F29 | Definir los campos personalizados de la ficha | hecho | común |
| CUSTOMER-F30 | Dar la ficha de un cliente a otras apps | hecho | común |
| CUSTOMER-F31 | Ver las cifras de los clientes | hecho | común |
| CUSTOMER-F32 | Apuntar alergias o la prueba de sensibilidad con su permiso | hecho | peluquería |

«Hecho»: servidor y páginas con sus tests (de las páginas y de extremo a extremo en Chrome). «Parcial»:
lo que falta y por qué va en su «Estado».

### CUSTOMER-F01 Dar de alta una ficha
<!-- origen: fi:modules/customers#command-customers-create old:customers/workflow/fichas.md#customers-f01 qa:modules/customers/create-customer -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable, empleado
Pantalla: Clientes
Pasos:
1. En **Clientes** pulsa **Añadir**: se abre el diálogo «Nuevo cliente» (el panel lateral del producto,
   pedido a `@erplora/ui` en `UI-REQUESTS.md`).
2. A la vista: «Nombre», «Teléfono», «Email», «NIF/CIF» y «Empresa». Detrás de «Más datos»:
   «Dirección», «Ciudad», «Código postal», «País», «Foto» (su dirección), «Cumpleaños»,
   «Aniversario», «Origen» («En el local» de entrada), «Etapa» («Contacto» de entrada), «Canal
   preferido» («Ninguno» de entrada) y «Notas internas».
3. Solo el nombre es obligatorio: hasta que no lo hay, **Guardar** no se puede pulsar.
4. Pulsa **Guardar**: el panel se cierra y la ficha aparece en la lista; las cifras se recalculan.
Entra: lo que se teclea. El país se guarda con su código de dos letras (`ES`, `FR`). El teléfono se
guarda en formato internacional (`+34` y las cifras seguidas, CUSTOMER-F11); el email y el NIF, sin los
espacios de los extremos.
Sale: la ficha nueva, activa y sin consentimiento de ningún tipo (CUSTOMER-F14), y el aviso de ficha
creada (`customer.customer.created`), que escucha WhatsApp para unir a la ficha las conversaciones
que ya tenía ese número.
Si falla: el motivo sale debajo de su campo y lo tecleado se conserva. Un email mal formado: «Escribe
un email válido.». Un teléfono que no es un número de su país: «No es un teléfono válido de su país:
revisa las cifras o escríbelo con su prefijo internacional (+44…).». Un país que no existe: «Elige
un país de la lista.». No se guarda nada. Los campos personalizados no se piden en el alta.
Implicados: WHATSAPP_INBOX-F04

### CUSTOMER-F02 Buscar y filtrar fichas
<!-- origen: fi:modules/customers#navigation-web-components fi:modules/customers#query-customers-list fi:modules/customers#query-customers-stats old:customers/workflow/fichas.md#customers-f02 -->
Estado: hecho
Vertical: común
Actor: todos
Pantalla: Clientes
Pasos:
1. Escribe en el buscador. Busca a la vez en nombre, email, teléfono, NIF y empresa, sin distinguir
   mayúsculas ni acentos («garcia» encuentra «García»). Un término hecho solo de cifras y signos de
   teléfono (con espacios, guiones o paréntesis, con `+` o `00` delante) se busca por sus cifras, sin
   el `00` ni el cero nacional, así que la ficha se encuentra se escriba como se escriba.
2. Con los filtros: etapa, origen, activo y gastado por rango («Desde / Hasta», en euros).
3. Ordena por nombre, email, teléfono, etapa, gastado, última compra o fecha de alta. De entrada, por
   nombre de la A a la Z, 50 por página (como mucho 100).
4. Toca una fila para abrir su ficha (CUSTOMER-F03).
Entra: el texto, los filtros y el orden.
Sale: nada; solo lectura. Las fichas eliminadas, unidas a otra o con los datos borrados no salen;
las marcadas como no activas, sí.
Si falla: la tabla enseña el error con «Reintentar». Sin resultados: «Sin clientes.».
Implicados: ninguno

### CUSTOMER-F03 Abrir la ficha de un cliente
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f08 fi:modules/customers#query-customers-get old:customers/workflow/fichas.md#customers-f03 qa:modules/customers/profile-and-history qa:verticals/beauty/04-check-in-and-service -->
Estado: hecho
Vertical: común
Actor: todos
Pantalla: Ficha de cliente
Pasos:
1. Desde **Clientes**, toca la fila.
2. La ficha enseña todos sus datos (también notas internas, cumpleaños, aniversario y campos
   personalizados, que en el producto actual solo se veían al editar), sus grupos y etiquetas, su
   consentimiento por canal, la actividad (más reciente primero, 50 por página), sus compras y los
   bloques de otras apps.
3. **← Volver** regresa a la lista.
Entra: la ficha y, aparte, su actividad, sus compras y su historial de consentimientos.
Sale: nada; solo lectura. Si otra persona la cambia mientras está abierta, se ve el cambio sin
recargar.
Si falla: «Este cliente ya no está disponible.» si se eliminó, se unió a otra o se borraron sus datos.
Implicados: CUSTOMER-F24

### CUSTOMER-F04 Editar la ficha y sus campos personalizados
<!-- origen: fi:modules/customers#command-customers-update old:customers/workflow/fichas.md#customers-f04 qa:modules/customers/tax-details-for-invoice -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas (propietario, administrador, responsable, empleado)
Pantalla: Ficha de cliente
Pasos:
1. En la ficha pulsa **Editar**: los datos pasan a ser el formulario del alta, más los «Campos
   personalizados» del negocio (cada uno con su forma: texto, número, fecha, sí/no, lista o texto
   largo; los obligatorios llevan `*`) y la casilla «Activo».
2. Cambia lo que haga falta. Vaciar un campo también es un cambio.
3. Pulsa **Guardar**. Sale «Cliente actualizado».
Entra: los datos cambiados y el valor de cada campo personalizado. El teléfono se guarda en formato
internacional, como en el alta.
Sale: la ficha y sus campos guardados en una sola escritura, y el aviso de ficha actualizada
(`customer.customer.updated`), que escucha WhatsApp para unir conversaciones de un teléfono recién
corregido. Guardar sin cambiar nada no avisa a nadie. El consentimiento queda anotado con la
dirección para la que se dio: cambiar el teléfono o el email no lo traslada (CUSTOMER-F14).
Si falla: un campo obligatorio vacío («Este campo es obligatorio.»), un valor que no encaja con su
tipo («Introduce un número.», «Introduce una fecha válida.», «Elige una de las opciones.»), un campo que
ya no existe o un teléfono que no es de su país rechazan TODO el guardado y el motivo sale junto a su
campo. La casilla «Activo» desmarcada solo cambia la cifra «Activos»: la ficha sigue saliendo en
búsquedas, en el TPV y en WhatsApp.
Implicados: WHATSAPP_INBOX-F04

### CUSTOMER-F05 Añadir una nota a la ficha
<!-- origen: fi:modules/customers#command-customers-notes-add fi:modules/customers#query-customers-activities old:customers/workflow/fichas.md#customers-f05 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Ficha de cliente
Pasos:
1. En «Añadir nota», escribe la nota.
2. Pulsa **Añadir**. Sale «Nota añadida» y la nota aparece arriba de la «Actividad», con quién la
   escribió y cuándo.
Entra: el texto (hasta 5.000 caracteres) y, si lo pone quien la escribe por otra vía (una
automatización), un título propio y el nombre del autor.
Sale: la nota, que ES su entrada de la actividad (una sola fila: no puede haber nota sin actividad),
y el aviso de nota añadida (`customer.note.added`). Las notas no se editan ni se borran. Una
automatización puede escribir notas por el mismo servicio.
Si falla: una nota vacía sale debajo del campo; «Este cliente ya no está disponible.» si la ficha ya
no existe.
Implicados: ninguno

### CUSTOMER-F06 Poner grupos y etiquetas a una ficha
<!-- origen: fi:modules/customers#command-customers-set_groups-handler-wasm-set_groups fi:modules/customers#command-customers-set_tags-handler-wasm-set_tags fi:modules/customers#query-customers-group_ids fi:modules/customers#query-customers-tag_ids old:customers/workflow/fichas.md#customers-f06 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Ficha de cliente
Pasos:
1. En «Grupos», marca o desmarca las casillas.
2. Pulsa **Guardar grupos**. Sale «Grupos asignados».
3. Igual con «Etiquetas» y **Guardar etiquetas** («Etiquetas asignadas»).
Entra: la selección completa de grupos o de etiquetas.
Sale: la selección SUSTITUYE a la anterior (no se añade), y el aviso de grupos o etiquetas cambiados
(`customer.customer.groups_changed`, `customer.customer.tags_changed`) si algo cambió. El recuento
«Clientes» de Grupos y Etiquetas se actualiza solo. Si otra persona cambia la ficha mientras marcas,
lo que has marcado o desmarcado y aún no has guardado se queda como lo dejaste; lo que esa persona
añade, borra o quita y tú no has tocado aparece o desaparece también en tu selección. Guardar nunca
vuelve a poner lo que otra persona quitó o borró.
Si falla: un grupo o una etiqueta que otra persona acaba de eliminar: «Ese grupo ya no existe.» /
«Esa etiqueta ya no existe.», y no se guarda nada; lo que se borró sale de tu selección (lo demás que
marcaste se queda, aunque la búsqueda lo esconda) y el siguiente **Guardar grupos** o **Guardar
etiquetas** funciona. Sin grupos o etiquetas: «No hay grupos.» / «No hay etiquetas.».
Implicados: ninguno

### CUSTOMER-F07 Eliminar una ficha
<!-- origen: fi:modules/customers#command-customers-delete old:customers/workflow/fichas.md#customers-f07 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador
Pantalla: Ficha de cliente
Pasos:
1. En la ficha pulsa **Eliminar**.
2. Un diálogo pregunta «Eliminar cliente» — «¿Eliminar {nombre}? Deja de salir en la lista, en el
   TPV y en la búsqueda por teléfono. Sus ventas se conservan.» con **Cancelar** y **Eliminar**.
3. Al confirmar sale «Cliente {nombre} eliminado» y la ficha desaparece de la lista, del TPV y de la
   búsqueda por teléfono.
Entra: la ficha.
Sale: la ficha marcada como eliminada CONSERVANDO sus datos, su actividad, sus consentimientos, sus
compras y sus pedidos enlazados, y el aviso de ficha eliminada (`customer.customer.deleted`). Una
ficha con compras se elimina igual: las ventas y facturas guardan su propia copia fiscal. Una venta
que llegue después para esa ficha ya no suma (CUSTOMER-F20). No es el borrado de datos personales:
eso es CUSTOMER-F16.
Si falla: una ficha que no existe: «Este cliente ya no está disponible.», sin avisar a nadie. Sobre
una ficha ya eliminada, unida a otra o con los datos borrados NO falla: responde bien y vuelve a
avisar.
Implicados: SERVICE-F29

### CUSTOMER-F08 Importar fichas desde un CSV
<!-- origen: fi:modules/customers#command-customers-bulk_create-handler-wasm-bulk_create old:customers/workflow/fichas.md#customers-f08 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Clientes
Pasos:
1. Pulsa **Importar CSV** y elige el fichero.
2. Cabeceras que entiende: `name`/«Nombre», `email`/«Email»/«correo», `phone`/«Teléfono»/«tel»,
   `tax_id`/«NIF»/«CIF», `company_name`/«Empresa», `address`/«Dirección», `city`/«Ciudad»,
   `postal_code`/«CP»/«Código postal», `country`/«País», `lifecycle_stage`/«Etapa» y
   `notes`/«Notas» (las mismas columnas que da la exportación, CUSTOMER-F09), y además `source`,
   `preferred_channel`, `birthday`, `anniversary` y `avatar`.
3. Mientras trabaja sale «Importando…». Al acabar, un resumen «Importación: {total} filas —
   {creadas} creadas, {omitidas} omitidas.» con cada fila omitida y su motivo, que empieza por la
   columna de la que habla («Nombre: Este campo es obligatorio.»; igual con un email o un teléfono
   que no son válidos), y las que tienen algo que revisar («país no reconocido: importado sin país,
   revísalo en la ficha»).
Entra: el fichero, que la pantalla envía en bloques de 50 filas.
Sale: las fichas creadas, con origen «Importación», el teléfono en formato internacional y sin
consentimiento (aunque el fichero traiga una columna de consentimiento), y un aviso de ficha creada
por cada una, así WhatsApp une sus conversaciones como en el alta a mano. Una fila sin etapa entra
como «Activo» (es un cliente que ya se tenía), igual que en el producto actual; la etapa antigua
`customer` también se lee como «Activo». Una fila sin origen entra como «Importación».
Si falla: una fila mala se omite con su motivo y las demás se crean. Una fila con el mismo nombre,
teléfono y email que una ficha que ya está (porque ya se importó o porque el fichero la repite) se
omite con «Ya hay una ficha con este nombre, teléfono y email: no se vuelve a crear.»; así, volver a
importar el mismo fichero tras un corte a mitad solo crea lo que faltaba. Basta que cambie uno de los
tres para que se cree (una madre y su hija comparten teléfono, CUSTOMER-F12).
Implicados: WHATSAPP_INBOX-F04

### CUSTOMER-F09 Exportar las fichas a CSV
<!-- origen: old:customers/workflow/fichas.md#customers-f09 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable
Pantalla: Clientes
Pasos:
1. Con la búsqueda y los filtros que se quieran, pulsa **Exportar CSV**.
2. El navegador descarga `customers.csv` con TODAS las fichas que cumplen la búsqueda, no solo la
   página que se ve.
Entra: la búsqueda y los filtros de la tabla.
Sale: un fichero con las columnas `name`, `email`, `phone`, `tax_id`, `company_name`, `address`,
`city`, `postal_code`, `country`, `lifecycle_stage`, `notes`, `source`, `is_active`,
`total_purchases`, `total_spent` (en euros, con dos decimales), `last_purchase_at`, `created_at`,
`groups` y `tags`. Un valor que empieza por `=`, `+`, `-` o `@` (un teléfono, por ejemplo) sale con
un apóstrofo delante para que la hoja de cálculo no lo lea como una fórmula; la importación lo quita.
Si falla: sin permiso de exportar, el servidor lo rechaza aunque se llame por la API. Sin fichas,
sale un fichero solo con las cabeceras.
Implicados: ninguno

### CUSTOMER-F10 Reconocer a una persona por su número de teléfono
<!-- origen: wf:whatsapp-cita#rec_wa_cita-f03 old:customers/workflow/identidad-y-privacidad.md#customers-f10 wf:whatsapp-mesa#rec_wa_mesa-f03 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. Otra app (WhatsApp, Reservas al apuntar una reserva a mano) o el alta rápida del TPV
   (CUSTOMER-F12) pregunta qué fichas llevan un número.
2. El número se lee con las mismas reglas con que se guarda (CUSTOMER-F11): con el prefijo que lleve
   (`+` o el `00` del país del negocio) o, si no lleva, en el país del negocio.
3. Unas cifras sin `+` se leen además como número internacional, que es como las da WhatsApp: en un
   negocio de España, unas cifras que empiezan por `44` son también un número del Reino Unido.
4. Casan las fichas vivas cuyo teléfono es uno de esos números. En un negocio de España, el mismo
   móvil escrito con espacios, con guiones o con `+34`, `0034` o `34` delante es la misma persona.
5. Las mismas cifras detrás del prefijo de otro país son otra persona: ese móvil con el prefijo de
   Francia (`+33`) no es la ficha del móvil español de un salón español.
Entra: el número tal como llegue.
Sale: las fichas que casan (nombre, email y teléfono), por nombre. Si son dos o más, decide quien
pregunta.
Si falla: un número vacío, con letras o que no es posible en su país no casa con nadie (nunca
devuelve la lista entera). Las fichas eliminadas, unidas o con los datos borrados no salen.
Implicados: RESERVATION-F06, WHATSAPP_INBOX-F04

### CUSTOMER-F11 Guardar el teléfono en formato internacional (E.164)
<!-- origen: wf:whatsapp-cita#rec_wa_cita-f07 old-hub:HUB-F36 old:customers/workflow/identidad-y-privacidad.md#customers-f11 -->
Estado: hecho
Vertical: común
Actor: quien da de alta o edita
Pantalla: Ficha de cliente
Pasos:
1. Al dar de alta, editar, importar o crear en el TPV o por WhatsApp, se escribe el teléfono como se
   tenga (con espacios o guiones, con `0034` o `+34` delante, o con el prefijo de otro país y el cero
   nacional entre paréntesis).
2. Al guardar se leen las reglas de libphonenumber: con el prefijo que lleve o, si no lleva, en el
   país del negocio (España mientras no haya otro); fuera espacios, guiones, puntos, barras,
   paréntesis y el cero nacional (también entre paréntesis tras el prefijo). Italia y los demás
   países que conservan el `0` tras el prefijo lo conservan. El número tiene que ser un número
   válido de su país (su numeración, no solo su longitud). Se guarda con su prefijo y las cifras
   seguidas (`+34` y las nueve cifras, para un número español).
3. Vaciar el teléfono está permitido: solo el nombre es obligatorio.
Entra: el teléfono tecleado.
Sale: el teléfono en E.164 en la ficha. Quien lo copia (Citas en la cita) lo copia ya normalizado.
Si falla: un número que no es válido en su país (`600111` en España, un rango que no se usa), con
letras (una extensión) o con dos números en el mismo campo se rechaza con «No es un teléfono válido de su país: revisa las
cifras o escríbelo con su prefijo internacional (+44…).» y no se guarda nada.
Implicados: APPOINTMENT-F01, WHATSAPP_INBOX-F04

### CUSTOMER-F12 Evitar fichas duplicadas de la misma persona
<!-- origen: old:customers/workflow/identidad-y-privacidad.md#customers-f12 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Clientes y Buscador de cliente del TPV
Pasos:
1. Antes de crear, se busca por nombre, teléfono, email o NIF (CUSTOMER-F02).
2. En el alta rápida del TPV, si el teléfono es el de una o más fichas vivas (CUSTOMER-F10), se
   enseñan y se pregunta: usar una de ellas o crear otra (puede ser otra persona con el mismo
   teléfono). Nunca se asigna sin elegir (CUSTOMER-F18).
3. Por WhatsApp, la respuesta de citas solo crea ficha si la búsqueda por número no encuentra a nadie.
4. Si ya hay dos fichas de la misma persona, se juntan con CUSTOMER-F13.
Entra: lo que se teclea.
Sale: nada propio. A propósito, ninguna regla impide dos fichas con el mismo teléfono, email o NIF:
una madre y su hija comparten teléfono, y una empresa da el mismo email a varias personas.
Si falla: la ficha duplicada se crea; se junta después.
Implicados: WHATSAPP_INBOX-F37

### CUSTOMER-F13 Unir dos fichas de la misma persona
<!-- origen: old:customers/workflow/identidad-y-privacidad.md#customers-f13 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable
Pantalla: Ficha de cliente
Pasos:
1. Abre la ficha que se va a QUEDAR y pulsa **Fusionar con…**.
2. Busca la duplicada (nombre, email, teléfono, NIF o empresa) y tócala.
3. Lee el aviso: «{absorbida} se fusionará en {superviviente}: sus citas, ventas, reservas,
   conversaciones, bonos, notas y consentimientos pasan a {superviviente}, los datos que falten se
   completan con los suyos y {absorbida} desaparece de la lista. No se puede deshacer.».
4. Pulsa **Fusionar**. Sale «{nombre} se ha fusionado en esta ficha.».
Entra: las dos fichas, vivas y distintas.
Sale: la que se queda conserva sus datos y solo rellena sus campos VACÍOS con los de la otra (también
el canal preferido si era «Ninguno»); las notas internas se juntan una detrás de otra; compras y
gastado se suman y la última compra es la más reciente. Pasan a ella la actividad (notas incluidas),
los campos personalizados que no tenía, los grupos y las etiquetas (unidos), las compras, los
pedidos enlazados y todos los consentimientos, que conservan la dirección para la que se dieron.
Nombre, etapa, origen y «Activo» son los suyos. En su actividad queda «Ficha duplicada fusionada en
esta». La otra queda retirada, con las cifras a cero, y conserva sus datos y los valores de campo que
chocaban hasta que se borren los datos de la que se queda: CUSTOMER-F16 borra las dos a la vez (es la
misma persona). Las fichas que antes se habían unido en la absorbida pasan a apuntar a la que se
queda, así nunca hay cadenas. El aviso de fichas unidas (`customer.customer.merged`)
hace que Citas, Ventas, Reservas, WhatsApp y Servicios re-apunten lo suyo; Reservas online lo sigue a
través de Citas. Cocina no guarda cliente: no tiene nada que re-apuntar.
Si falla: «Este cliente ya no está disponible.» si una de las dos ya no está; elegir la misma ficha:
«Elige otra ficha: no se puede fusionar una ficha consigo misma.». No cambia nada.
Implicados: APPOINTMENT-F23, RESERVATION-F21, SALE-F33, SERVICE-F28, WHATSAPP_INBOX-F12, ONLINE_BOOKING-F09

### CUSTOMER-F14 Registrar el consentimiento de un canal
<!-- origen: old:customers/workflow/identidad-y-privacidad.md#customers-f14 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Ficha de cliente
Pasos:
1. En «Consentimiento de marketing» hay una línea para Email, WhatsApp y SMS (y otra por cada canal
   con algo apuntado: Teléfono, Correo postal), con su estado: «Nunca se le ha preguntado», «Dado» o
   «Retirado», y la fecha y la dirección si las hay.
2. Pulsa **Registrar consentimiento**. Sale la frase «Quiero recibir ofertas y novedades de este
   negocio por este canal. Puedo darme de baja cuando quiera.» con la indicación «Léelo en voz alta y
   pulsa solo si dice que sí. Esta frase exacta es la que queda guardada como prueba, junto a tu
   nombre y la hora.».
3. Si el cliente dice que sí, pulsa **Ha dicho que sí**. Sale «Consentimiento registrado.».
Entra: el canal, la frase exacta y su versión, el origen («en el mostrador» de entrada) y, si lo hay,
un justificante. La dirección la pone el servidor con la de la ficha en ese momento (el email, el
teléfono para WhatsApp, SMS y llamadas, o la dirección postal) y quién lo apunta sale de la sesión.
Sale: un hecho nuevo que nunca se edita ni se borra, una entrada «Consentimiento dado» en la
actividad y el aviso de consentimiento dado (`customer.consent.granted`).
Si falla: una frase vacía o una fecha en el futuro se rechazan junto a su campo; «Este cliente ya no
está disponible.» si la ficha ya no está. Quien no gestiona fichas ve el estado sin botones. Editar,
crear o importar una ficha NUNCA pone consentimiento.
Implicados: ninguno

### CUSTOMER-F15 Retirar el consentimiento de un canal
<!-- origen: old:customers/workflow/identidad-y-privacidad.md#customers-f15 -->
Estado: hecho
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Ficha de cliente
Pasos:
1. En un canal «Dado», pulsa **Retirar**: un solo toque, sin diálogo y sin pedir motivo.
2. Sale «Consentimiento retirado. Está en vigor desde ya.» y la línea pasa a «Retirado».
Entra: el canal y, si se quiere, un motivo.
Sale: un hecho nuevo (el «Dado» anterior se conserva: prueba el tiempo en que sí se podía escribir),
«Consentimiento retirado» en la actividad y el aviso `customer.consent.withdrawn`. Volver a darlo
después es otro hecho.
Si falla: como CUSTOMER-F14.
Implicados: ninguno

### CUSTOMER-F16 Borrar los datos personales de un cliente (RGPD)
<!-- origen: old-hub:HUB-F250 old-hub:HUB-F248 old-hub:HUB-F249 old:customers/workflow/identidad-y-privacidad.md#customers-f16 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador
Pantalla: Ficha de cliente
Pasos:
1. En la ficha pulsa **Borrar datos personales**.
2. Sale «Borrar datos personales (RGPD)» con el texto «Borra los datos personales de {nombre}, sus
   notas, su actividad, sus datos de salud y sus campos personalizados, y no se puede deshacer. Las ventas y facturas
   conservan su referencia. Queda una entrada de auditoría con quién, cuándo y por qué.» y el campo
   «Motivo (queda en la auditoría)».
3. Pulsa **Borrar datos personales**. La ficha se cierra y sale «Datos personales borrados.».
Entra: la ficha y el motivo (opcional, hasta 500 caracteres). Vale también para una ficha ya
eliminada o unida a otra. Las fichas duplicadas que se unieron en ella (CUSTOMER-F13) son la misma
persona: sus datos se borran en el mismo paso, cada una con su auditoría y su aviso.
Sale: la ficha se queda con su identificador, el nombre fijo `Deleted customer` y sin contacto, NIF,
dirección, fechas, notas internas ni canal, y desaparece de todas las listas. Se borran su actividad
(notas incluidas), sus datos de salud (CUSTOMER-F32), sus valores de campos personalizados y su pertenencia a grupos y etiquetas; sus
consentimientos se quedan sin dirección, justificante ni motivo. Se conservan el origen, la etapa,
las compras, el gastado, la última compra y la fecha de alta, las compras y los pedidos enlazados
(prueba comercial y fiscal) y una única entrada de auditoría (quién, cuándo, el motivo y qué se borró
y qué se guardó). El aviso de datos borrados (`customer.customer.erased`) lo escuchan WhatsApp,
Servicios, Citas, Reservas, Reservas online y Mesas para vaciar sus copias. Ventas y Facturación
conservan su copia fiscal (es un documento fiscal).
Si falla: «Este cliente ya no está disponible.» si no existe. Repetirlo no cambia los datos ni
duplica la auditoría, pero vuelve a avisar.
Implicados: RESERVATION-F22, SERVICE-F29, WHATSAPP_INBOX-F11, APPOINTMENT-F24, ONLINE_BOOKING-F12, TABLE-F31

### CUSTOMER-F17 Asignar un cliente a la venta en el TPV
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f09 fi:modules/customers#slot-sales-pos-customer_context-erp-customers-pos-search old:customers/workflow/con-otros-modulos.md#customers-f17 wf:peluqueria-dia#rec_peluqueria-f10 -->
Estado: hecho — el buscador es `CustomerSearch` (ver «Buscador de cliente del TPV · API»); lo monta Venta en su pantalla
Vertical: común
Actor: todos
Pantalla: Buscador de cliente del TPV
Pasos:
1. En la pantalla de venta toca «Asignar cliente». Si el negocio exige cliente, al cobrar sin él el
   buscador se abre solo.
2. El buscador enseña las 20 primeras fichas por nombre; al escribir busca como CUSTOMER-F02.
3. Toca la ficha: el botón pasa a enseñar su nombre y la venta recibe una COPIA de sus datos
   fiscales (nombre, NIF, dirección y país).
4. **Quitar cliente** deja la venta sin cliente. Al cobrar, aparcar, dejar en la mesa o eliminar la
   cuenta, Venta suelta el cliente y quita su enlace al pedido (CUSTOMER-F19).
5. Al recargar, recuperar una cuenta aparcada o retomar una mesa, la cuenta vuelve con su cliente:
   Venta pregunta a Clientes qué cliente tiene ese pedido.
Entra: la búsqueda y, al elegir, la ficha completa (CUSTOMER-F30).
Sale: a Venta, el cliente y la copia fiscal. Cambiar la ficha después no cambia una factura emitida.
Si falla: el motivo con «Reintentar»; sin resultados, «Sin resultados.»; si la ficha completa no se
puede leer, el cliente no se asigna. Si al recuperar la cuenta su cliente ya no está disponible, la
cuenta sigue sin cliente y sale «No se pudo recuperar el cliente de esta cuenta. Vuelve a asignarlo
antes de cobrar.».
Implicados: SALE-F04, SALE-F05, SALE-F17, INVOICE-F02

### CUSTOMER-F18 Crear un cliente desde el buscador del TPV
<!-- origen: old:customers/workflow/con-otros-modulos.md#customers-f18 -->
Estado: hecho — el buscador es `CustomerSearch` (ver «Buscador de cliente del TPV · API»); lo monta Venta en su pantalla
Vertical: común
Actor: todos los que gestionan fichas
Pantalla: Buscador de cliente del TPV
Pasos:
1. Escribe algo que no encuentra y pulsa **+ Nuevo cliente «{lo escrito}»**. Si parece un teléfono,
   va a «Teléfono»; si no, a «Nombre».
2. Completa «Nombre» y «Teléfono» y pulsa **Crear y asignar**.
3. Si ese teléfono ya es el de una ficha viva, sale «Ya existe {nombre} con este teléfono. ¿Usar esa
   ficha o crear una nueva?» (con varias, «Estas fichas ya tienen este teléfono…» y la lista) con
   **Usar {nombre}** y **Crear una nueva**; nada se asigna hasta elegir (como Square y Lightspeed).
4. La ficha elegida o la nueva queda asignada a la venta como en CUSTOMER-F17.
Entra: nombre y teléfono.
Sale: la ficha con origen «En el local», el teléfono en E.164, el aviso de ficha creada y la venta
con cliente.
Si falla: sin nombre no se puede pulsar; un teléfono que no es de su país sale dentro del formulario;
si no se puede consultar quién tiene ese teléfono, la ficha se crea (la venta no se bloquea; si era la
misma persona se juntan con CUSTOMER-F13).
Implicados: SALE-F05, WHATSAPP_INBOX-F04

### CUSTOMER-F19 Enlazar el cliente al pedido abierto
<!-- origen: old:customers/workflow/con-otros-modulos.md#customers-f19 -->
Estado: hecho
Vertical: común
Actor: sistema (lo pide Venta)
Pantalla: ninguna
Pasos:
1. Con un cliente asignado, Venta abre o guarda el pedido (la cuenta de la mesa, el carrito) y le
   pide a Clientes que lo enlace.
2. Clientes anota qué cliente tiene ese pedido. Reasignar otro cliente al mismo pedido sustituye el
   anterior (un pedido, como mucho un cliente); el mismo cliente otra vez no reescribe nada.
3. Al soltar el cliente (quitarlo, dejar la cuenta en la mesa, eliminar la cuenta), Venta pide el
   enlace sin cliente y el enlace se quita.
Entra: el pedido y el cliente (o ninguno), con el permiso de quien está en la caja.
Sale: el enlace cliente ↔ pedido y su aviso (`customer.order.linked` o `customer.order.unlinked`).
Venta lo lee para devolver el cliente a la cuenta (CUSTOMER-F17).
Si falla: la venta sigue; Venta enseña «La venta sigue, pero el cliente no se pudo asociar al
pedido.». Un cliente que ya no está disponible no se enlaza.
Implicados: SALE-F17

### CUSTOMER-F20 Sumar la compra a la ficha al cobrar
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f09 wf:restaurante-dia#rec_restaurante-f11 fi:modules/customers#command-customers-record_purchase fi:modules/customers#event-listen-sale-completed-customers-record_purchase old:customers/workflow/con-otros-modulos.md#customers-f20 -->
Estado: hecho — la reacción está declarada (`events.REACTIONS`, `events.react`); la entrega entre apps la hace el relay del outbox (fase 2)
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. Se cobra una venta con cliente.
2. En su ficha suben «Compras» en una y «Gastado» en el total de la venta, «Última compra» pasa a ese
   momento y la «Actividad» gana «Compra registrada».
3. La etapa avanza sola: «Contacto» o «Prospecto» → «1ª compra»; «1ª compra», «En riesgo» o
   «Inactivo» → «Activo». «Perdido» y «VIP» no se tocan.
Entra: la venta cobrada, con su cliente y su total en céntimos (aviso `sale.sale.completed` de Venta).
Sale: una línea en el historial de compras por venta, las cifras y la etapa de la ficha, la entrada
de actividad y el aviso `customer.purchase.recorded`.
Si falla: una venta sin cliente no hace nada; la misma venta entregada dos veces cuenta una sola vez;
una ficha eliminada, unida o con los datos borrados no suma.
Implicados: SALE-F01

### CUSTOMER-F21 Restar una venta anulada
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:restaurante-dia#rec_restaurante-f15 old:customers/workflow/con-otros-modulos.md#customers-f21 -->
Estado: hecho — la reacción está declarada (`events.REACTIONS`, `events.react`); la entrega entre apps la hace el relay del outbox (fase 2)
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. Se anula una venta que tenía cliente.
2. En su ficha bajan «Compras» y «Gastado», «Última compra» vuelve a la compra anterior que siga en
   pie y la «Actividad» gana «Compra anulada» con el motivo.
3. La etapa retrocede: sin compras, «1ª compra» o «Activo» → «Contacto»; con una, «Activo» →
   «1ª compra». «VIP» y las demás no se tocan.
Entra: la venta anulada (aviso `sale.sale.voided` de Venta).
Sale: la línea del historial marcada como anulada (no se borra), las cifras, la etapa y el aviso
`customer.purchase.voided`.
Si falla: anular dos veces la misma venta resta una sola vez; una venta que no estaba apuntada no
hace nada.
Implicados: SALE-F30

### CUSTOMER-F22 Restar una devolución
<!-- origen: wf:peluqueria-dia#rec_peluqueria-f14 wf:restaurante-dia#rec_restaurante-f15 old:customers/workflow/con-otros-modulos.md#customers-f22 -->
Estado: hecho — la reacción está declarada (`events.REACTIONS`, `events.react`); la entrega entre apps la hace el relay del outbox (fase 2)
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. Se devuelve todo o parte de una venta que tenía cliente.
2. En su ficha, «Gastado» baja en lo devuelto; «Compras», «Última compra» y la etapa no cambian; la
   «Actividad» gana «Devolución de compra» con el importe y el motivo.
Entra: la devolución de la venta (aviso `sale.sale.refunded` de Venta: venta, devolución, importe
devuelto, motivo y momento).
Sale: una línea de devolución en el historial de compras, con su importe en negativo y el estado
«Devolución», y el aviso `customer.purchase.refunded`. El «Gastado» de la ficha es lo cobrado menos
lo devuelto, también para la auditoría de cifras (`customer.purchase.divergences`).
Si falla: la misma devolución entregada dos veces cuenta una sola vez; la devolución de una venta que
no está apuntada (sin cliente) o que se anuló no hace nada; en una ficha con los datos borrados resta
pero no deja actividad.
Implicados: SALE-F31

### CUSTOMER-F23 Ver el historial de compras de un cliente
<!-- origen: old:customers/workflow/con-otros-modulos.md#customers-f23 -->
Estado: hecho
Vertical: común
Actor: todos
Pantalla: Ficha de cliente
Pasos:
1. Abre la ficha (CUSTOMER-F03).
2. En «Compras» sale cada venta con su fecha, su importe y su estado («Cobrada» o «Anulada»), y cada
   devolución en su propia línea («Devolución», importe en negativo), la más reciente primero, 50 por
   página; se puede filtrar por estado.
Entra: el historial de compras de la ficha.
Sale: nada; solo lectura.
Si falla: «Sin compras.» si no hay ninguna.
Implicados: ninguno

### CUSTOMER-F24 Ver en la ficha lo que otras apps saben del cliente
<!-- origen: fi:modules/customers#command-customers-activity-add old:customers/workflow/con-otros-modulos.md#customers-f24 -->
Estado: hecho
Vertical: común
Actor: todos
Pantalla: Ficha de cliente
Pasos:
1. Abre la ficha. Al final aparece el bloque de cada app encendida que lo ofrece (hoy, Citas con el
   «Historial de visitas»); si la app está apagada, su bloque no sale.
2. Lee el bloque: en «Historial de visitas» salen sus diez últimas citas, la más reciente primero, con
   los servicios, el profesional, el estado y las notas de la visita. Una cita nueva aparece sin
   recargar la ficha.
Entra: qué cliente está abierto (Clientes se lo dice al bloque; no le pasa más datos).
Sale: nada; solo lectura.
Si falla: cada bloque enseña su propio error en su sitio («No se pudo mostrar este bloque.») y el resto
de la ficha sigue.
Implicados: APPOINTMENT-F20

### CUSTOMER-F25 Crear la clienta sin salir de la agenda
<!-- origen: qa:verticals/beauty/03-appointments-and-whatsapp wf:peluqueria-dia#rec_peluqueria-f06 old:customers/workflow/con-otros-modulos.md#customers-f25 -->
Estado: hecho
Vertical: peluquería
Actor: todos los que gestionan fichas
Pantalla: Citas: Agenda
Pasos:
1. En la agenda, pulsa «Añadir cita» y, en «Nueva cita», elige los servicios, el profesional, el día y
   la hora en el orden que quieras.
2. En «Cliente», pulsa «Asignar cliente» y escribe el nombre o el teléfono de la clienta. Si no tiene
   ficha, sale «Sin resultados.» y, debajo, «+ Nuevo cliente «…»» con lo que has escrito.
3. Púlsalo. Lo escrito pasa a «Nombre» (o a «Teléfono», si es un número); completa el otro (solo el
   nombre es obligatorio) y pulsa «Crear y asignar».
4. Si ese teléfono ya está en otra ficha, se enseña y eliges: «Usar» esa ficha o «Crear una nueva»
   (una madre y su hija pueden compartir teléfono).
5. La clienta queda elegida en «Cliente» y el resto de la cita sigue como estaba; pulsa «Añadir cita».
Entra: el nombre y, si lo das, el teléfono.
Sale: la ficha nueva, con origen «En el local», y la cita con ella.
Si falla: el motivo sale dentro de «Elegir cliente», junto a lo que has escrito (un teléfono que no es
de su país, debajo de «Teléfono»), y no se pierde nada: ni el nombre y el teléfono tecleados ni los
servicios, el profesional, el día y la hora de la cita. Corrige y vuelve a pulsar «Crear y asignar».
Quien no gestiona fichas no ve «+ Nuevo cliente».
Implicados: APPOINTMENT-F01, CUSTOMER-F18

### CUSTOMER-F26 Crear la ficha de quien pide cita por WhatsApp
<!-- origen: wf:whatsapp-cita#rec_wa_cita-f03 old:customers/workflow/con-otros-modulos.md#customers-f26 -->
Estado: parcial — el alta con origen «WhatsApp» está (también a mano desde la Bandeja,
WHATSAPP_INBOX-F37); falta la respuesta automática de citas de la Bandeja de WhatsApp, que aún no está
migrada
Vertical: peluquería
Actor: asistente
Pantalla: ninguna
Pasos:
1. Una clienta escribe al WhatsApp del salón con la respuesta automática de citas encendida.
2. La respuesta busca su ficha por el número (CUSTOMER-F10). Si la encuentra, la usa.
3. Si no, crea una ficha con el nombre que la clienta haya dado (o su teléfono como nombre), su
   teléfono en E.164 y origen «WhatsApp».
4. En el restaurante la respuesta de mesas NO crea ficha: solo liga la reserva a la que ya exista.
Entra: el número y el mensaje.
Sale: la ficha nueva y el aviso de ficha creada.
Si falla: un número que no es válido no crea ficha; si casa con dos o más fichas, no crea ninguna.
Implicados: WHATSAPP_INBOX-F37, APPOINTMENT-F18

### CUSTOMER-F27 Crear, cambiar y eliminar grupos de clientes
<!-- origen: fi:modules/customers#command-customers-groups-create-update-delete fi:modules/customers#query-customers-groups-list old:customers/workflow/segmentacion.md#customers-f27 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable (eliminar: propietario y administrador)
Pantalla: Grupos
Pasos:
1. En **Grupos** pulsa **Añadir** («Nuevo grupo»): «Nombre» (obligatorio), «Descripción», «Color» y
   «Orden». **Guardar** → «Grupo creado».
2. Para cambiarlo, toca la fila («Editar · {nombre}»), que añade la casilla «Activo». **Guardar** →
   «Grupo actualizado». Un grupo desactivado deja de ofrecerse en las fichas (las que lo tienen lo
   conservan) y sigue en la lista con el filtro de inactivos, desde donde se vuelve a activar.
3. Para quitarlo, **Eliminar**: «¿Eliminar {nombre}? Las fichas que lo tienen lo pierden.» → «Grupo
   {nombre} eliminado».
Entra: los datos del grupo.
Sale: el grupo, que se asigna desde cada ficha (CUSTOMER-F06), y su aviso
(`customer.group.created`, `.updated`, `.deleted`). Eliminar un grupo lo quita de todas sus fichas
de verdad. Un grupo no lleva descuento ni precio.
Si falla: un nombre ya usado por otro grupo activo (sin distinguir mayúsculas ni espacios de los
extremos): «Ya hay un grupo con ese nombre. Elige otro nombre.» debajo de «Nombre»; un grupo
inactivo libera su nombre, y reactivarlo con un nombre que ya tiene otro se rechaza igual.
Implicados: ninguno

### CUSTOMER-F28 Crear, cambiar y eliminar etiquetas de clientes
<!-- origen: fi:modules/customers#command-customers-tags-create-update-delete fi:modules/customers#query-customers-tags-list old:customers/workflow/segmentacion.md#customers-f28 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable (eliminar: propietario y administrador)
Pantalla: Etiquetas
Pasos:
1. En **Etiquetas** pulsa **Añadir** («Nueva etiqueta»): «Nombre» y «Color». **Guardar** →
   «Etiqueta creada».
2. Al editar («Editar · {nombre}») aparece «Activa», como en los grupos. **Guardar** → «Etiqueta
   actualizada».
3. **Eliminar**: «¿Eliminar {nombre}? Las fichas que la tienen la pierden.» → «Etiqueta {nombre}
   eliminada».
Entra: nombre y color.
Sale: la etiqueta, que se asigna desde cada ficha (CUSTOMER-F06), y su aviso
(`customer.tag.created`, `.updated`, `.deleted`). Eliminarla la quita de todas sus fichas.
Si falla: «Ya hay una etiqueta con ese nombre. Elige otro nombre.» debajo de «Nombre».
Implicados: ninguno

### CUSTOMER-F29 Definir los campos personalizados de la ficha
<!-- origen: fi:modules/customers#command-customers-fields-create-update-delete fi:modules/customers#query-customers-fields-list old:customers/workflow/segmentacion.md#customers-f29 -->
Estado: hecho
Vertical: común
Actor: propietario, administrador, responsable
Pantalla: Campos
Pasos:
1. En **Campos** pulsa **Añadir** («Nuevo campo personalizado»): «Nombre», «Tipo» («Texto»,
   «Número», «Fecha», «Sí/No», «Selección» o «Texto largo»), las «Opciones» si es de selección,
   «Orden» y, si hace falta, «Obligatorio».
2. **Guardar** → «Campo creado». El campo aparece en la ficha de TODOS los clientes (CUSTOMER-F03,
   F04), con su forma.
3. Al editar («Editar · {nombre}») aparece «Activo»: un campo inactivo no sale en las fichas ni se
   exige, y sus valores se quedan. Se cambia todo menos el tipo, si ya hay fichas con un valor.
   **Eliminar** → «¿Eliminar {nombre}? Se borran también los valores guardados en las fichas.» →
   «Campo {nombre} eliminado».
Entra: la definición del campo.
Sale: el campo y su aviso (`customer.field.created`, `.updated`, `.deleted`). «Obligatorio» solo se
exige al guardar la ficha completa (CUSTOMER-F04), nunca al darla de alta (Clientes, TPV,
importación ni WhatsApp).
Si falla: «Ya hay un campo con ese nombre. Elige otro nombre.» debajo de «Nombre»; un campo de
selección sin opciones: «Añade al menos una opción.»; cambiar el tipo de un campo con valores: «Este
campo ya tiene valores en algunas fichas: su tipo no se puede cambiar.».
Implicados: ninguno

### CUSTOMER-F30 Dar la ficha de un cliente a otras apps
<!-- origen: old:customers/workflow/con-otros-modulos.md#customers-f30 -->
Estado: hecho
Vertical: común
Actor: sistema
Pantalla: ninguna
Pasos:
1. Otra app pide la ficha de un cliente por su identificador: Citas al reservar, Servicios al pintar
   la titular de un bono, Venta al asignar el cliente (CUSTOMER-F17); y la propia ficha.
2. Clientes contesta con la ficha: nombre, email, teléfono, NIF, empresa, dirección, ciudad, código
   postal, país, notas, cumpleaños, aniversario, canal preferido, etapa, origen, si está activa, los
   acumulados de compra, sus grupos, sus etiquetas, sus campos personalizados y su consentimiento
   por canal.
Entra: el identificador de la ficha y el permiso de ver clientes.
Sale: nada guardado; solo lectura.
Si falla: una ficha que no existe, eliminada, unida a otra o con los datos borrados no se devuelve:
«Este cliente ya no está disponible.». Una ficha desactivada sí se devuelve.
Implicados: APPOINTMENT-F01, SERVICE-F16, SALE-F05

### CUSTOMER-F31 Ver las cifras de los clientes
<!-- origen: fi:modules/customers#widget-customers-total-kpi-customers-active-stat-customers-revenue-kpi -->
Estado: hecho
Vertical: común
Actor: todos
Pantalla: Clientes
Pasos:
1. Abre **Clientes**: arriba, encima de la tabla, salen cuatro cifras: «Clientes», «Activos», «VIP» e
   «Ingresos».
2. «Clientes» cuenta las fichas que siguen en la lista; «Activos», las que tienen marcada la casilla
   «Activo»; «VIP», las de la etapa «VIP», e «Ingresos» suma lo que han gastado todas ellas, en euros.
3. Las cifras cambian solas, sin recargar, cuando alguien da de alta, edita, elimina, une o borra los
   datos de una ficha, o cuando se cobra, se anula o se devuelve una venta con cliente.
Entra: nada: cuentan todas las fichas que siguen en la lista, no solo las que deja ver la búsqueda o
los filtros de la tabla.
Sale: nada; solo lectura.
Si falla: «No se pudieron cargar las cifras» en su sitio, y la tabla sigue funcionando. Mientras
llegan, cada cifra enseña «…». En el móvil van de dos en dos, para que la tabla se siga viendo debajo.
Implicados: ninguno

### CUSTOMER-F32 Apuntar alergias o la prueba de sensibilidad con su permiso
<!-- origen: qa:modules/customers/profile-with-health-data-l10 -->
Estado: hecho
Vertical: peluquería
Actor: todos los que gestionan fichas (verlo: todos)
Pantalla: Ficha de cliente
Pasos:
1. En la ficha, el bloque «Salud y alergias» dice «Para apuntar alergias o pruebas de sensibilidad
   hace falta su permiso expreso.» y enseña **Pedir permiso**.
2. Púlsalo: sale la frase «Doy mi permiso para que este negocio guarde mis alergias y mis pruebas de
   sensibilidad para atenderme con seguridad. Puedo retirarlo cuando quiera y entonces se borrarán.»
   con la indicación «Léelo en voz alta y pulsa solo si dice que sí. Esta frase exacta es la que queda
   guardada como prueba, junto a tu nombre y la hora.».
3. Si dice que sí, pulsa **Ha dicho que sí**: sale «Permiso registrado.» y el bloque enseña sus datos
   de salud (al principio, «Sin alergias apuntadas.» y «Sin prueba de sensibilidad.»).
4. Pulsa **Editar**: «Alergias y sensibilidades», «Fecha de la prueba de sensibilidad» y «Resultado»
   («Sin resultado», «Negativa» o «Positiva»). **Guardar** → «Datos de salud guardados.».
5. Con alergias apuntadas, el bloque las enseña destacadas, como aviso, para que quien atienda las vea
   antes del servicio.
6. **Retirar permiso** pregunta «¿Retirar el permiso? Se borran sus alergias y su prueba de
   sensibilidad.» y, al confirmar, sale «Permiso retirado y datos de salud borrados.».
Entra: la frase exacta y su versión (quién lo apunta sale de la sesión); las alergias (hasta 2.000
caracteres), la fecha de la prueba y su resultado.
Sale: el permiso, como un hecho más del libro de consentimientos (finalidad «datos de salud», con su
entrada en la «Actividad» y su aviso `customer.health.consent_granted` o
`customer.health.consent_withdrawn`), y los datos de salud, con «Datos de salud actualizados» en la
actividad (sin su contenido) y el aviso `customer.health.updated`. Los avisos solo llevan
identificadores. Retirar el permiso BORRA los datos de salud en el mismo paso.
Si falla: sin el permiso en vigor no se guarda nada: «Registra antes su permiso para guardar datos de
salud.». Una prueba con fecha futura: «Esta fecha está en el futuro.»; un resultado sin fecha: «Pon la
fecha de la prueba.». «Este cliente ya no está disponible.» si la ficha ya no está. Quien no gestiona
fichas ve el bloque sin botones.
Implicados: CUSTOMER-F13, CUSTOMER-F16

## Qué comparten los verticales

Tocar una pieza de esta tabla afecta a la peluquería **y** al restaurante.

| Pieza compartida | Flujos que la usan |
|---|---|
| Un solo formulario de ficha para el alta y la edición | F01, F04, F11 |
| La lectura del teléfono (las mismas reglas al guardar y al buscar por número) | F01, F04, F08, F10, F11, F18, F26 |
| La búsqueda de texto de la lista (tabla, fusión, TPV y selector de Citas) | F02, F13, F17, F18, F25 |
| El aviso de ficha creada o actualizada, que escucha WhatsApp | F01, F04, F08, F18, F26 |
| La fusión y su aviso | F13 |
| El borrado de datos y su aviso, y la eliminación | F07, F16 |
| El buscador del TPV, la copia fiscal y el historial de compras | F17, F18, F19, F20, F21, F23 |
| El consentimiento por canal | F14, F15 |
| Grupos, etiquetas y campos personalizados | F06, F27, F28, F29 |

Lo que **no** se comparte: crear la ficha de quien escribe por WhatsApp (solo la peluquería, F26), el
historial de visitas en la ficha (solo Citas, F24) y el alta desde la agenda (F25).

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien lo
usa) y la API, con las mismas reglas y los mismos permisos. Las listas van por páginas de hasta 100 y
todas tienen buscador. Para hablar con naturalidad, un cliente se puede nombrar por su id o por su
nombre exacto, su teléfono o su email («añade una nota a Ana García»), y un grupo, una etiqueta o un
campo, por su nombre; si dos fichas encajan, se pide el id, el teléfono o el email.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | En vivo | Servicio |
|---|---|---|---|---|
| Las fichas, con búsqueda, filtros, orden y páginas | ver | F02, F17 | sí | `customer.customer.list` |
| La ficha completa, con grupos, etiquetas, campos y consentimiento por canal | ver | F03, F30 | sí | `customer.customer.detail` |
| Las cifras: clientes, activos, VIP e ingresos | ver | F02, F31 | sí | `customer.customer.stats` |
| Las fichas que llevan un número de teléfono | ver | F10, F12, F18 | no | `customer.customer.by_phone` |
| El CSV de todas las fichas que cumplen la búsqueda | exportar | F09 | no | `customer.customer.export` |
| Los grupos, con cuántas fichas tiene cada uno | ver | F06, F27 | sí | `customer.group.list` |
| Las etiquetas, con cuántas fichas tiene cada una | ver | F06, F28 | sí | `customer.tag.list` |
| Los campos personalizados | ver | F04, F29 | sí | `customer.field.list` |
| La actividad de una ficha, más reciente primero | ver | F03, F05 | sí | `customer.activity.list` |
| Las compras de una ficha | ver | F23 | sí | `customer.purchase.list` |
| Las fichas cuyas cifras no cuadran con sus compras (auditoría) | ver | F20, F21 | sí | `customer.purchase.divergences` |
| El consentimiento en vigor de una ficha, por finalidad y canal (también para las API keys) | ver | F14, F15 | sí | `customer.consent.state` |
| Todo lo que se decidió sobre el consentimiento de una ficha | ver | F14, F15 | sí | `customer.consent.history` |
| Qué cliente tiene un pedido | ver | F17, F19 | sí | `customer.order.customer` |
| Los pedidos de una ficha (también para las API keys) | ver | F19 | sí | `customer.order.list` |
| Los datos de salud de una ficha y su permiso (solo en pantalla) | ver | F32 | sí | `customer.health.detail` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Da de alta una ficha | gestionar | F01, F18, F25, F26 | `customer.customer.create` |
| Cambia la ficha (solo lo enviado) y sus campos personalizados | gestionar | F04 | `customer.customer.update` |
| Crea hasta 50 fichas de un CSV, fila a fila | gestionar | F08 | `customer.customer.import` |
| Sustituye los grupos de una ficha | gestionar | F06 | `customer.customer.set_groups` |
| Sustituye las etiquetas de una ficha | gestionar | F06 | `customer.customer.set_tags` |
| Elimina una ficha (conserva sus datos) | eliminar | F07 | `customer.customer.delete` |
| Une una ficha duplicada en otra | unir | F13 | `customer.customer.merge` |
| Borra los datos personales de una ficha | borrar datos | F16 | `customer.customer.erase` |
| Añade una nota | gestionar | F05 | `customer.note.add` |
| Anota en la actividad una entrada de otra app (una visita, una reserva) | anotar actividad | F24 | `customer.activity.add` |
| Registra un consentimiento dado | gestionar | F14 | `customer.consent.grant` |
| Registra un consentimiento retirado | gestionar | F15 | `customer.consent.withdraw` |
| Enlaza (o desenlaza) el cliente de un pedido | gestionar | F19 | `customer.order.link` |
| Registra el permiso para guardar datos de salud | gestionar | F32 | `customer.health.grant` |
| Retira ese permiso y borra los datos de salud | gestionar | F32 | `customer.health.withdraw` |
| Guarda las alergias y la prueba de sensibilidad (con el permiso en vigor) | gestionar | F32 | `customer.health.update` |
| Crea y cambia grupos; los elimina | configurar; eliminar | F27 | `customer.group.create`, `.update`; `.delete` |
| Crea y cambia etiquetas; las elimina | configurar; eliminar | F28 | `customer.tag.create`, `.update`; `.delete` |
| Crea, cambia y elimina campos personalizados | configurar | F29 | `customer.field.create`, `.update`, `.delete` |
| Apunta la compra de una venta cobrada (solo el sistema) | sistema | F20 | `customer.purchase.record` |
| Resta la compra de una venta anulada (solo el sistema) | sistema | F21 | `customer.purchase.void` |
| Apunta una devolución y la resta del gastado (solo el sistema) | sistema | F22 | `customer.purchase.refund` |

### Lo que avisa (para las apps que quieran reaccionar)

Los avisos llevan solo identificadores, nunca datos personales: quien necesite la ficha la pide
(CUSTOMER-F30).

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Ficha creada | Alta, alta rápida, WhatsApp e importación (uno por fila) | `id` | `customer.customer.created` |
| Ficha actualizada | Editar con algún cambio | `id` | `customer.customer.updated` |
| Grupos cambiados | Guardar grupos con algún cambio | `id` | `customer.customer.groups_changed` |
| Etiquetas cambiadas | Guardar etiquetas con algún cambio | `id` | `customer.customer.tags_changed` |
| Ficha eliminada | Eliminar (también la repetición) | `id` | `customer.customer.deleted` |
| Fichas unidas | Fusionar | `id` (la que se queda) y `absorbed_id` | `customer.customer.merged` |
| Datos personales borrados | Borrar datos (también la repetición) | `id` | `customer.customer.erased` |
| Nota añadida | Añadir nota | `id` (la nota) y `customer_id` | `customer.note.added` |
| Actividad anotada por otra app | Anotar actividad | `id` (la entrada) y `customer_id` | `customer.activity.recorded` |
| Consentimiento dado / retirado | Registrar / retirar | `id`, `customer_id` y `channel` | `customer.consent.granted`, `customer.consent.withdrawn` |
| Pedido enlazado / desenlazado | Enlazar con otro cliente / soltarlo | `order_id` y `customer_id` | `customer.order.linked`, `customer.order.unlinked` |
| Compra apuntada / anulada | Venta cobrada / anulada | `customer_id` y `sale_id` | `customer.purchase.recorded`, `customer.purchase.voided` |
| Devolución apuntada | Venta devuelta (toda o parte) | `customer_id`, `sale_id` y `refund_id` | `customer.purchase.refunded` |
| Grupo, etiqueta o campo creado, cambiado o eliminado | Configurar | `id` | `customer.group.*`, `customer.tag.*`, `customer.field.*` |
| Permiso de datos de salud dado / retirado | Registrar / retirar | `id` (el hecho) y `customer_id` | `customer.health.consent_granted`, `customer.health.consent_withdrawn` |
| Datos de salud guardados | Guardar con algún cambio | `id` y `customer_id` | `customer.health.updated` |

### A qué reacciona (avisos de otras apps)

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Venta cobrada (`sale.sale.completed`) | Venta | Apunta la compra (CUSTOMER-F20) | `customer.purchase.record` |
| Venta anulada (`sale.sale.voided`) | Venta | Resta la compra (CUSTOMER-F21) | `customer.purchase.void` |
| Venta devuelta (`sale.sale.refunded`) | Venta | Apunta la devolución y la resta del gastado (CUSTOMER-F22) | `customer.purchase.refund` |

Las tres reacciones son de Clientes (como las de Inventario) y están probadas con los avisos reales de
Venta; las ejecuta el sistema, cada una en su transacción, cuando
el relay del outbox reparta los avisos entre apps (fase 2). Clientes no depende de Venta: es el
único enlace.

### Lo que necesita de otras apps

Nada para funcionar. Con **Venta** se usan el buscador del TPV, el enlace al pedido y las compras;
con **Citas**, el bloque de visitas y el alta desde la agenda; con la **Bandeja de WhatsApp**, el
reconocimiento por número y el alta automática. Ninguna de esas apps es requisito de Clientes: son
ellas las que usan los servicios de Clientes.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver fichas, grupos, etiquetas, campos, actividad, compras y consentimientos | sí | sí | sí | sí | `customer.view` |
| Dar de alta, editar, importar, añadir notas, asignar grupos y etiquetas, registrar el consentimiento y enlazar pedidos | sí | sí | sí | sí | `customer.manage` |
| Crear y cambiar grupos, etiquetas y campos personalizados; eliminar campos | sí | sí | sí | no | `customer.configure` |
| Unir fichas duplicadas | sí | sí | sí | no | `customer.merge` |
| Exportar a CSV | sí | sí | sí | no | `customer.export` |
| Anotar en la actividad lo que traen otras apps | sí | sí | sí | no | `customer.record_activity` |
| Eliminar fichas, grupos y etiquetas | sí | sí | no | no | `customer.delete` |
| Borrar datos personales | sí | sí | no | no | `customer.erase` |

Apuntar y anular compras no es de ningún papel: lo hace el sistema al cobrarse o anularse una venta
(`customer.record_purchase`, que ninguna app declara y por eso solo tiene el sistema).

El servidor aplica estos permisos aunque la pantalla enseñe el botón, también por la API y el
asistente. Lo que en el producto actual tenía el perfil «Cajero» lo tiene aquí el empleado.

## Para quien lo mantiene

- Anatomía completa de una app, copiada de `apps/demo`: `apps.py`, `models.py`, `schemas.py`,
  `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/` y un
  `tests/test_<fichero>.py` por fichero. Además, `phones.py` (la lectura E.164) y `search.py` (el
  texto de búsqueda), sin ORM.
- `phones.py` lee el teléfono con `phonenumbers` (el port de Python de libphonenumber) y exige un
  número válido de su país; sus tests son el contrato del SDK del producto actual
  (`crates/guest-sdk/tests/phone_test.rs`), corregido donde ese SDK, que solo copiaba longitudes, se
  apartaba de libphonenumber. Los países se validan con `pycountry` (ISO 3166). El país del negocio
  es `ES` mientras la plataforma no tenga ajustes por negocio (`queries.business_country`).
- Datos de salud (F32): `HealthRecord`, una fila por ficha, y su permiso en el libro `Consent` con
  `purpose = "health"` y sin canal. Sus cuatro operaciones (`customer.health.*`) no declaran `ai` ni
  `expose_api`: los datos de salud no llegan al asistente ni a las API keys (RGPD art. 9,
  minimización). No salen en la lista, la búsqueda, la exportación ni `customer.customer.detail`.
- Toda operación (salvo las de salud) declara `ai` (descripción para el asistente y, en las escrituras, `risk`) y todo
  campo de `schemas.py` su descripción: son la herramienta del asistente. Las referencias humanas
  (nombre, teléfono, email) las resuelve `queries.find_customer`, solo entre fichas vivas.
- Búsqueda: cada ficha guarda `search_text` (nombre, email, teléfono, NIF y empresa en minúsculas y
  sin acentos), recalculado en `Customer.save()`; así no hace falta la extensión `unaccent`.
- Estados de una ficha: viva (`deleted_at` vacío), eliminada (`deleted_at`), unida (`merged_into`) y
  con los datos borrados (`erased_at`). Las lecturas solo ven las vivas.
- La nota y su actividad son UNA fila de `Activity` (`kind = note_added`), como el «chatter» de Odoo.
  La actividad guarda claves (`kind`), nunca frases: la pantalla las traduce.
- Compras: una fila de `Purchase` por venta (`sale_id` único entre las filas cobradas) y otra por
  devolución (`refund_id` único, importe en negativo, estado `refunded`); la suma se mueve solo al
  crear la fila o al anularla, así un aviso repetido no cuenta dos veces.
- Consentimiento: `Consent` es un libro de hechos, solo se añaden filas; el estado de un canal es su
  último hecho.
- Los nombres de grupos, etiquetas y campos son únicos sin distinguir mayúsculas
  (`Lower("name")`); el esquema les quita los espacios de los extremos.
- `customer.purchase.record`, `customer.purchase.void` y `customer.purchase.refund` no tienen ruta
  de API: son del sistema y los ejecuta `events.react` con los avisos de Venta (declarados en
  `events.py`, `REACTIONS`).
- Bloques de la ficha (CUSTOMER-F24): una app que quiera estar en la ficha publica
  `apps/<id>/frontend/customer-card/<Bloque>.vue`, un componente con una sola prop, `customerId` (el id
  de la ficha); lee lo suyo con sus propias consultas. Clientes no depende de ninguna: los encuentra
  (`components/CustomerCardBlocks.vue`), pinta solo los de las apps encendidas en el negocio, cada uno
  en su trozo y en su marco (si falla, «No se pudo mostrar este bloque.» en su sitio y la ficha sigue).
- El administrador de Django (solo en `hubs.erplora.com`, para el staff) tiene CRUD completo sobre
  todas las tablas (ronda 12, PLAN §17); lo que cambia ahí no deja aviso en el outbox.
- Toda escritura sobre una ficha bloquea antes su fila (también nota, actividad, consentimiento y
  enlace de pedido), así no se cuela en una ficha que se está eliminando o uniendo. El orden de los
  bloqueos es siempre la ficha y después lo que cuelga de ella (compras, enlaces), el mismo que el de
  la fusión: anular una venta bloquea primero la ficha y luego su compra.

## Cambios frente al producto actual

- **Permisos**: ocho claves (`view`, `manage`, `configure`, `merge`, `export`, `delete`, `erase`,
  `record_activity`) en lugar de veintiuna, juntando las que todos los papeles tenían a la vez; cada
  papel puede lo mismo que antes. El perfil «Cajero» desaparece y sus permisos pasan al empleado, que
  ahora edita fichas y registra consentimientos.
- **Exportar** se comprueba en el servidor y exporta todas las fichas que cumplen la búsqueda, con
  más columnas (antes: solo la página visible y el permiso solo escondía el botón).
- **Email** comprobado al guardar en el alta, la edición y la importación (antes se guardaba mal
  formado).
- **Importar** avisa de cada ficha creada (antes no, y WhatsApp no unía sus conversaciones); una fila
  sin etapa sigue entrando como «Activo», como en el producto actual. Volver a importar el mismo
  fichero ya no duplica: la fila con el mismo nombre, teléfono y email que una ficha viva se omite
  (services#152, customers#15).
- **Borrar datos personales** alcanza también a las fichas duplicadas unidas en la borrada (antes la
  absorbida se quedaba con sus datos y la única pista hacia ella, la actividad «fusionada», se
  borraba).
- **Grupos y etiquetas**: eliminarlos los quita de verdad de las fichas (antes la pertenencia se
  quedaba y bloqueaba guardar los grupos de esas fichas). Desactivarlos ya no los pierde: siguen en la
  lista con el filtro de inactivos y se reactivan. Eliminar un campo borra sus valores.
- **Campos**: no se puede cambiar el tipo de un campo con valores (antes se cambiaba y las fichas no
  se podían guardar hasta corregirlo). Fechas comprobadas en el calendario real.
- **Ficha**: notas internas, cumpleaños, aniversario y campos personalizados se ven sin pulsar
  Editar; las compras salen con su importe y su estado (antes solo por el asistente).
- **Notas**: una sola fila con su actividad (antes dos tablas).
- **Avisos** sin datos personales: solo identificadores (antes llevaban la ficha entera y había que
  vaciarlos al borrar datos).
- **Borrado de datos**: borra la actividad, las notas y los valores de campo en lugar de vaciarlos y
  esconderlos.
- **Consentimiento**: la dirección la pone el servidor con la de la ficha; sin la casilla antigua ni
  el estado «Marcado antes de que hubiera registro», que solo existía para migrar datos viejos; sin
  marca derivada en la ficha (el estado por canal sale del libro).
- **Teléfono**: con la librería libphonenumber entera, el número tiene que ser válido en su país (el
  SDK del producto solo miraba la longitud y dejaba pasar `+44012345678`). Sin la tarea programada que
  reescribía teléfonos antiguos ni su copia: aquí todo teléfono entra ya en E.164.
- **Referencias humanas**: toda operación sobre una ficha acepta su nombre exacto, teléfono o email
  además del id, y las de grupos, etiquetas y campos, su nombre (para el asistente por voz).
- **Enlace al pedido**: quitar el cliente de un pedido es el mismo servicio con cliente vacío; una
  ficha que ya no está disponible no se devuelve como cliente del pedido.
- **Pantallas** (las mismas vistas, pestañas y textos; `UI-REQUESTS.md` lleva lo que falta en
  `@erplora/ui`): el alta y la edición de grupos, etiquetas y campos van en un diálogo, no en el panel
  lateral de la tabla; el color de un grupo o etiqueta se elige de los colores del tema (antes, texto
  libre); el país se busca por su nombre; los teléfonos se pintan agrupados (`+34 600 111 222`); la ficha
  enseña además las compras y los pedidos enlazados; en el móvil «Cargar más» pide trozos de 100 como
  mucho (lo que acepta una consulta).
- **Cifras**: los tres «widgets de escritorio» (clientes, activos e ingresos) que anunciaba la
  documentación del producto nunca se declararon en el módulo; aquí no hay escritorio de widgets y esas
  cifras, más «VIP», son las de arriba de la lista (F31).
- Fuera, a propósito: el descuento por grupo (ya retirado en el producto), la tarea de reescribir
  teléfonos antiguos y su copia, el estado «Marcado antes de que hubiera registro» y el canal «any»
  del consentimiento (solo existían para datos heredados) y el permiso `customers.manage_settings`
  (no había ajustes).

## Datos: de quién es cada dato

| Dato personal | Dónde vive | Cómo se borra |
|---|---|---|
| Nombre, email, teléfono, NIF, empresa, dirección, ciudad, código postal, país, notas internas, cumpleaños, aniversario y canal preferido | la ficha (`Customer`) | F16: vaciados; nombre `Deleted customer`. F07 no borra nada |
| Origen, etapa, compras, gastado, última compra y fecha de alta | la ficha | se conservan (no identifican por sí solos) |
| Valores de campos propios | `CustomFieldValue` | F16: borrados |
| Alergias y prueba de sensibilidad (datos de salud, RGPD art. 9) | `HealthRecord` | F32: borrados al retirar el permiso; F16: borrados |
| Notas y actividad (textos, frase del consentimiento, motivos, importes) | `Activity` | F16: borradas; queda solo la auditoría del borrado |
| Pertenencia a grupos y etiquetas | grupos y etiquetas de la ficha | F16: quitada |
| Consentimientos (canal, dirección, frase, versión, origen, justificante, motivo, quién y cuándo) | `Consent` | F16: dirección, justificante y motivo vaciados; el hecho se queda |
| Ventas y devoluciones de la persona (venta, devolución, importe, moneda, estado) | `Purchase` | se conservan (prueba comercial y fiscal) |
| Pedidos de la persona | `OrderLink` | se conservan |
| Nombre y datos fiscales en la venta y la factura | Venta / Facturación | se conservan: documento fiscal |

## Reglas que no se rompen

- **Para crear basta el nombre.** Nada más se exige al dar de alta.
- **El teléfono se guarda en E.164 o no se guarda**: toda escritura lo normaliza, y uno que no es un
  número válido de su país rechaza el guardado.
- **El consentimiento no se pone editando, creando ni importando.** Solo con su acción, que exige la
  frase; cada decisión es un hecho nuevo que nada edita ni borra; quién lo apuntó sale de la sesión.
- **Una venta cuenta una sola vez, y una anulación y cada devolución restan una sola vez**; una venta
  sin cliente no toca ninguna ficha.
- **Un pedido tiene como mucho un cliente.**
- **Unir fichas es todo o nada**: dos fichas vivas y distintas, o no cambia nada; no se deshace.
- **Borrar datos personales no se deshace**, alcanza a las fichas unidas en la borrada; repetirlo no
  cambia nada (pero vuelve a avisar), y conserva las compras y los pedidos.
- **Eliminar o borrar datos de una ficha que no existe falla y no avisa a nadie**; sobre una ficha ya
  eliminada, unida o borrada, las dos órdenes funcionan y vuelven a avisar.
- **La edición de la ficha se guarda entera o nada.**
- **Un nombre por negocio** entre los grupos, entre las etiquetas y entre los campos, sin distinguir
  mayúsculas ni espacios.
- **Un dato de salud solo se guarda con el permiso expreso en vigor**, y retirarlo lo borra.
- **El dinero va en céntimos**; la pantalla escribe los filtros en euros.
- **Buscar por teléfono nunca devuelve a todos.**
- **Clientes no depende de ninguna app**: se enciende sola.

## Lo que NO hace, a propósito

- No envía nada (ni campañas, ni recordatorios, ni mensajes): guarda el consentimiento para que lo
  consulte quien envíe.
- No aplica descuentos por grupo: un grupo dice quién es el cliente, no lo que paga.
- No lleva puntos de fidelidad ni saldo; los bonos son de Servicios.
- No guarda ni cambia facturas: la venta lleva una copia fiscal congelada.
- No entrega a la persona una copia de sus datos (acceso, portabilidad).
- No relaciona personas con su empresa ni guarda varias direcciones por ficha.
- No tiene segmentos dinámicos por reglas ni etapas que cambien solas por tiempo sin comprar.
- No impide fichas con el mismo teléfono, email o NIF (CUSTOMER-F12).

## Dudas abiertas

1. **Aviso de posible duplicado al crear (F12).** ¿Un aviso que no bloquea con las fichas del mismo
   teléfono o email? Hoy lo hace solo el alta rápida del TPV.
2. **Etapas por tiempo.** «En riesgo», «Inactivo» y «Perdido» solo se ponen a mano: ¿tarea programada?
3. **País del negocio.** Llega cuando la plataforma tenga ajustes por negocio; hasta entonces, España.
4. **Aprobación con PIN.** El producto actual dejaba hacer con el PIN de un responsable lo que es del
   responsable; llega con la elevación de la plataforma (fase 2).
