# Workbook — Demo (app)
Prefijo: DEMO
Alcance MVP: fase 1 (referencia técnica, no se vende)
Estado de la app: hecha (servidor y páginas)

> Manual de usuario y especificación de la app `demo`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Demo es la app que se **copia** para escribir cualquier otra (plan de la fase 1,
> §4.5): enseña el patrón completo con el mínimo de negocio posible.

## Para qué sirve y para quién

Demo guarda **elementos** con un nombre, un estado («Abierto» o «Hecho») y una nota, y cada elemento
lleva una lista de **líneas** (texto y cantidad). No resuelve ningún problema del negocio: sirve para
comprobar, en la tableta, que la plataforma funciona de punta a punta.

- Lo que se crea, cambia o borra en una tableta aparece en las demás **en menos de un segundo**, sin
  recargar.
- «Añadir línea» se ve **al instante**, antes de que conteste el servidor; si el servidor la rechaza,
  la línea desaparece sola y sale el motivo.
- Una persona sin permiso no ve lo que no puede hacer, y la app lo rechaza aunque lo intente por la API.

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** ven, crean, cambian y borran
  elementos y añaden líneas, y ven las cifras.
- El **empleado** solo ve la lista y la ficha.

## Referencia adoptada

Es el patrón de lista y ficha de cualquier backoffice del mercado (Odoo, Shopify, Square Dashboard):
lista paginada con buscador y filtro de estado, ficha con sus líneas, formulario con el error junto a
cada campo y borrado con confirmación. La línea que aparece al instante y se deshace si el servidor
la rechaza es la «actualización optimista» de Linear, Trello o Google Docs. La repetición segura de
una petición con un identificador que pone el cliente es la clave de idempotencia de Stripe. Una ficha
que se borra en otro sitio, o que la persona deja de poder ver, deja de enseñarse y dice por qué, como
el «registro que ya no existe» de Odoo.

## Antes de empezar

- Hace falta entrar con una cuenta que tenga papel en ese negocio. Demo no tiene entrada propia: sin
  sesión, lleva a la entrada de ERPlora, que vuelve al negocio ya con su papel.
- En la fase 1 el negocio es la **primera parte de la dirección** (el negocio `a` y el negocio `b`). En
  la fase 2 cada negocio tendrá sus propios datos.
- ⚠️ En la fase 1 los dos negocios **comparten los elementos**. Lo que sí se separa ya es el **aviso
  en vivo**: guardar en `a` solo refresca las pantallas abiertas en `a`. Las de `b` ven el cambio al
  recargar o con el siguiente aviso de `b`.

## Pantallas

Demo se abre desde **«Mis apps»**, arriba a la derecha, y tiene dos pantallas y dos formularios.

### Elementos (lista)
Tabla con Nombre, Estado («Abierto» / «Hecho»), Líneas (cuántas tiene) y Actualizado. Buscador
«Buscar…» por nombre (sin distinguir mayúsculas); el embudo abre «Filtros», con el de estado («Todos»,
«Abierto», «Hecho»); 50 por página (se puede cambiar), del cambiado más recientemente al más antiguo,
como tabla o como tarjetas; en el móvil, «Cargar más». Botón **«Nuevo elemento»** solo para quien
puede gestionar. Tocar una fila abre la ficha. Encima, las cifras «Abiertos», «Hechos» y «Líneas»,
solo para quien puede gestionar.

![La lista de elementos en el móvil, con las cifras, el buscador, el embudo de filtros y «Nuevo elemento»](docs/img/items-list.png)

### Ficha del elemento
Nombre, estado, nota y la lista de líneas (texto y cantidad, en el orden en que se añadieron).
Acciones para quien puede gestionar: «Editar», «Marcar como hecho» (o «Reabrir»), «Eliminar»,
«Guardar nota» y «Añadir línea». Si otra persona cambia la nota mientras se escribe, la nota escrita
**no se pisa** y sale «Actualizado en otro sitio», con «Recargar» para tomar la de la otra persona. Si
el elemento se borra en otro sitio, o la persona deja de poder verlo, la ficha deja de enseñarlo y
dice por qué.

### Nuevo elemento y Editar elemento (formularios)
Campos Nombre (obligatorio, hasta 120 caracteres), Estado y Nota. «Guardar». Un dato que no vale
sale debajo de su campo y no se guarda nada. Quien no puede gestionar ve «No tienes permiso» en lugar
del formulario.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» en la lista y una rueda en la ficha mientras llega el primer resultado. |
| Vacío | «Todavía no hay elementos» (o «Sin resultados» si hay búsqueda o filtro), con «Nuevo elemento» si puede crear; una ficha sin líneas, «Todavía no hay líneas». |
| Error | «No se pudieron cargar los elementos» con «Reintentar»; en la ficha, «No se pudo cargar el elemento» con el motivo. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…» hasta que vuelve la conexión. |
| App inactiva | «Esta app no está activa en este negocio». No se reintenta solo: vuelve cuando la app se activa. |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| DEMO-F01 | Crear un elemento | hecho |
| DEMO-F02 | Editar un elemento | hecho |
| DEMO-F03 | Borrar un elemento | hecho |
| DEMO-F04 | Añadir una línea al instante (optimista e idempotente) | hecho |
| DEMO-F05 | Ver el cambio en otra tableta en menos de un segundo | hecho |
| DEMO-F06 | Intentarlo sin permiso | hecho |

### DEMO-F01 Crear un elemento
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Elementos
Pasos:
1. En **Elementos**, pulsa «Nuevo elemento»: se abre el formulario «Nuevo elemento».
2. Escribe el Nombre; Estado («Abierto» de entrada) y Nota son opcionales.
3. Pulsa «Guardar». Vuelves a la lista y el elemento sale el primero, «sin líneas».
Entra: nada de otras apps.
Sale: el elemento, en un solo paso; Demo avisa de que hay un elemento nuevo
(`demo.item.created`) y se refrescan la lista y las cifras.
Si falla: un Nombre vacío (o solo espacios) o de más de 120 caracteres sale debajo del campo y no se
guarda nada.
Implicados: ninguno

### DEMO-F02 Editar un elemento
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Ficha del elemento
Pasos:
1. En la ficha, pulsa «Editar»: se abre «Editar elemento» con los datos guardados.
2. Cambia lo que haga falta y pulsa «Guardar». Solo se cambia lo que has tocado; lo demás queda como
   estaba.
3. Vuelves a la ficha con los datos nuevos, y el elemento sube al principio de la lista.
4. Sin abrir el formulario, en la misma ficha: «Marcar como hecho» (o «Reabrir») cambia el estado, y
   «Guardar nota» guarda la nota escrita.
Entra: el elemento tal como está guardado.
Sale: el elemento cambiado; Demo avisa del cambio (`demo.item.updated`). Guardar sin cambiar nada
no avisa a nadie.
Si falla: los mismos rechazos por campo que al crear. Si el elemento ya no existe (otra persona lo
borró): «Este elemento ya no existe».
Implicados: ninguno

### DEMO-F03 Borrar un elemento
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Ficha del elemento
Pasos:
1. En la ficha, pulsa «Eliminar»: sale «¿Eliminar este elemento y sus líneas?».
2. Pulsa «Eliminar» para confirmar («Cancelar» no borra nada). Vuelves a la lista y el elemento ya no
   está, ni sus líneas.
Entra: el elemento elegido.
Sale: el elemento y sus líneas, borrados; Demo avisa (`demo.item.deleted`). Las otras tabletas que
tengan abierta su ficha ven «Este elemento ya no existe», sin el elemento ni sus botones.
Si falla: «Este elemento ya no existe» si otra persona lo borró antes.
Implicados: ninguno

### DEMO-F04 Añadir una línea al instante (optimista e idempotente)
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: administrador, responsable
Pantalla: Ficha del elemento
Pasos:
1. En la ficha de un elemento abierto, escribe el texto y la cantidad y pulsa «Añadir línea».
2. La línea aparece **en el acto**, al final, antes de que conteste el servidor.
3. Cuando contesta, la línea provisional se cambia por la guardada sin que se note.
Entra: el elemento, su estado y sus líneas.
Sale: la línea, al final (posición siguiente a la última), y el elemento como recién cambiado; Demo
avisa (`demo.item.line_added`). Repetir es seguro: cada línea lleva un identificador que pone la
tableta, y si la misma línea llega dos veces (un reintento por mala cobertura), la segunda devuelve la
ficha tal cual, **sin duplicar la línea ni volver a avisar**; con el mismo identificador gana la
primera línea guardada, y un reintento de una línea que ya entró se acepta aunque el elemento se haya
cerrado después.
Si falla: si el elemento está «Hecho», la línea provisional **se deshace** y sale «Este elemento está
cerrado: ábrelo para añadir líneas». Sin texto, «Añadir línea» no se puede pulsar, y el texto no pasa
de 200 caracteres; una cantidad que no sea mayor que cero (hasta 3 decimales) sale debajo de su campo.
Si el elemento ya no existe: «Este elemento ya no existe».
Implicados: ninguno

### DEMO-F05 Ver el cambio en otra tableta en menos de un segundo
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: cualquiera con permiso de ver
Pantalla: Elementos y Ficha del elemento
Pasos:
1. Abre la lista (o la misma ficha) en dos tabletas del mismo negocio.
2. En una, crea, cambia, borra o añade una línea.
3. La otra lo enseña en menos de un segundo, sin recargar.
Entra: los avisos de Demo de ese negocio.
Sale: la lista, la ficha y las cifras al día. Cada pantalla recibe el resultado completo, nunca el
aviso suelto.
Si falla: sin conexión, lo pintado se queda con «Reconectando…»; al volver llegan los resultados
completos. Lo hecho en `a` no avisa a las pantallas de `b` (ni al revés).
Implicados: ninguno

### DEMO-F06 Intentarlo sin permiso
<!-- origen: nuevo (app de referencia de la fase 1, PLAN §16; sin módulo viejo) -->
Estado: hecho
Actor: empleado
Pantalla: Elementos y Ficha del elemento
Pasos:
1. Un empleado abre **Demo**: ve la lista y la ficha, sin «Nuevo elemento», «Editar», «Marcar como
   hecho», «Eliminar», «Guardar nota», «Añadir línea» ni cifras; la nota solo se lee.
2. Si abre a mano el formulario de crear o de editar, ve «No tienes permiso»; si lo intenta por la API
   o el asistente, se rechaza.
Entra: su papel en ese negocio.
Sale: nada cambia.
Si falla: «No tienes permiso». Sin sesión, lleva a la entrada. Si le quitan el permiso con la
pantalla abierta, en el siguiente refresco la ficha deja de enseñar el elemento y dice «No tienes
permiso».
Implicados: ninguno

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (fase 2) y la API, con las mismas reglas y los
mismos permisos.

### Lo que ofrece: consultas (leen, no cambian nada; todas se pueden seguir en vivo)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Los elementos, con búsqueda por nombre, filtro de estado y páginas (hasta 100 por página) | ver | F01–F05 | `demo.item.list` |
| La ficha de un elemento con sus líneas | ver | F02–F05 | `demo.item.detail` |
| Las cifras: total, abiertos, hechos y líneas | gestionar | F05 | `demo.item.stats` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea un elemento | gestionar | F01 | `demo.item.create` |
| Cambia un elemento (solo lo enviado) | gestionar | F02 | `demo.item.update` |
| Borra un elemento y sus líneas | gestionar | F03 | `demo.item.delete` |
| Añade una línea; repetir con el mismo identificador no la duplica | gestionar | F04 | `demo.item.add_line` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Elemento nuevo | Crear | Cuál (`id`) | `demo.item.created` |
| Elemento cambiado | Editar con algún cambio | Cuál (`id`) | `demo.item.updated` |
| Elemento borrado | Borrar | Cuál (`id`) | `demo.item.deleted` |
| Línea añadida | Añadir una línea nueva (no en una repetición) | El elemento (`id`) y la línea (`line_id`) | `demo.item.line_added` |

Qué refresca cada aviso: la lista y las cifras, con los cuatro; la ficha, con «cambiado», «borrado» y
«línea añadida».

### A qué reacciona y lo que necesita de otras apps
Nada: Demo no depende de ninguna app.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver elementos | sí | sí | sí | sí | `demo.view` |
| Gestionar elementos y ver las cifras | sí | sí | sí | no | `demo.manage` |

El propietario y el administrador tienen siempre todos los permisos de todas las apps; el responsable y
el empleado, los que declara cada app. Los papeles de la plataforma (el equipo de ERPlora) no tienen
papel en ningún negocio.

## Para quien lo mantiene

- Anatomía completa de una app: `apps.py`, `models.py`, `schemas.py`, `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/` y un `tests/test_<fichero>.py` por fichero.
- Las rutas no llevan parámetros en la ruta: el `id` viaja en la entrada (consulta en GET, cuerpo en
  POST), porque cada ruta toma **un** parámetro igual a la entrada de su operación.
- La línea es idempotente por `(elemento, client_line_id)` (restricción `demo_line_client_id_unique`);
  `add_line` bloquea la fila del elemento, así que dos líneas a la vez no comparten posición.
- Errores: 422 `invalid_payload` con `fields` por campo (mensaje en el idioma de la petición); 404
  `not_found` («Este elemento ya no existe»); 409 `demo.item_done` (línea en un elemento hecho); 403
  `permission_denied`; 401 `unauthorized`; 404 `app_inactive`. En la ficha, cualquier error de la
  consulta viva deja de pintar el elemento y sus acciones (`ItemDetailPage.vue`, `shown`), y
  `permission_denied` se titula «No tienes permiso».
- El administrador de Django enseña los elementos con sus líneas **solo para leer**: toda escritura
  pasa por una operación, que es la que deja el aviso. Vive solo en `http://hubs.localhost:8000/admin/`
  (en `a.localhost:8000/admin/`, 404) y entra el staff desde la página «Hubs» del admin del SaaS
  (`platform@example.com` / `platform`); ningún papel de negocio entra en él.
- Entrada en desarrollo: sin sesión, el Hub manda al login del SaaS
  (`http://localhost:8001/hub-login/?hub=a`), que vuelve con un código de un solo uso y el papel en
  ese negocio. Cuentas del SaaS: `owner@example.com` / `owner` (propietario de `a` y `b`) y
  `employee@example.com` / `employee` (empleado de `a`).
- Los papeles de negocio llegan del SaaS tal cual y se guardan con prefijo: `hub_owner`, `hub_admin`,
  `hub_manager` y `hub_employee` (las claves de `role_permissions`); en pantalla solo se ve su nombre
  traducido. Un papel sin el prefijo se rechaza al entrar. Ningún papel de negocio da `is_staff`: los
  papeles de plataforma (superusuario y grupo `support`) solo llegan al Hub por la audiencia
  `hub-admin` (el admin del Hub en `hubs`), sobre una copia local propia del staff, `saas-staff:<id>`,
  separada de la copia de cliente `saas:<id>` y sin papel en ningún hub.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b` (una sola
  base de datos, sin tenencia); la fase 2 cambia solo `base/operations.py` (ámbito = hub, una BD por
  hub).
- Pruebas por flujo: `tests/e2e/demo-flows.spec.ts` recorre DEMO-F01 a F06 en 390, 834 y 1440 (capturas
  `APP-DEMO-<flujo>-<ancho>`); las medidas finas siguen en `two-tabs-live`, `optimistic-add-line`,
  `two-orgs-isolated`, `reconnect`, `delete-item`, `create-edit-pages`, `list-filters-stats`,
  `datatable` y `employee-permissions`.

## Lo que NO hace, a propósito

- No tiene precios, impuestos ni nada fiscal: no es una app de negocio.
- No borra ni reordena líneas: con añadir basta para enseñar el patrón optimista.
- No separa los datos de `a` y `b` en la fase 1 (llega con la tenencia de la fase 2).
