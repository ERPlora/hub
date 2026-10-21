# Workbook — Cocina (app)
Prefijo: KITCHEN
Alcance MVP: restaurante
Estado de la app: hecha (servidor y páginas). Las dos piezas que Cocina pone en el TPV (el botón
«Enviar comanda» con su urgencia y la hoja «Comandas de la cuenta») están en la pantalla «Vender» de
Ventas, con las operaciones de aquí (KITCHEN-F18–F20).

> Manual de usuario y especificación de la app `kitchen`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo Cocina del producto actual
> (`modules-workspace/modules/kitchen`, `origin/main` `fa95827`) y de sus `workflow/*.md`. Los números
> de flujo se conservan (`KITCHEN-Fnn`) porque otras apps los citan. Lo que cambia frente al producto
> actual lo dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Cocina recibe cada ronda que el camarero envía desde el TPV, antes de cobrar, y la convierte en una
**comanda**: la enseña en una pantalla de cocina legible a un metro (la **Pantalla**), reparte sus
platos entre **estaciones** (plancha, barra, postres…), deja que cada estación los marque **listos** y
que el pase los **entregue**, y guarda un **historial** de lo que se hizo.

Quién la usa:

- El **empleado** de cocina o de sala (cocinero, camarero): marca platos listos, los recupera, entrega,
  marca urgente una ronda y envía rondas desde el TPV. Solo cambia estados.
- El **responsable**: además cancela y borra comandas, gestiona las estaciones y el enrutado de
  productos y categorías, y guarda los ajustes de la pantalla.
- El **administrador** y el **propietario**: todo.

Cocina no sabe qué es una mesa ni un cliente: recibe una **etiqueta** («Mesa 4»; sin etiqueta, la
tarjeta dice el tipo: «En sala», «Para llevar», «A domicilio») que pinta e imprime tal cual. No cobra,
no descuenta stock y no lleva recetas.

## Referencia adoptada

ERPlora no inventa flujos: adopta los que el mercado ya probó (contrastados en el producto actual el
10/08, 15/08, 24/08 y 02/09/2026, y revisados al portar).

- **Estaciones de preparación, vista de pase (todas las estaciones), marcar listo por plato y por
  comanda, «urgente» después de enviar**:
  [Toast — flujo KDS](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html).
  Los cursos con retener y lanzar no se adoptan (fuera del MVP).
- **Un plato anulado en el TPV se ve en cocina, tachado**:
  [Toast — anulaciones](https://doc.toasttab.com/doc/platformguide/adminVoidingOrders.html).
- **Completar un plato suelto o la comanda entera, y la vista de completadas**:
  [Square KDS](https://squareup.com/help/us/en/article/8171-complete-orders-with-square-kds).
- **Cada toque hace avanzar el plato; semáforo de dos tiempos que cuenta desde que se envió**:
  [Lightspeed K-Series KDS 2.0](https://k-series-support.lightspeedhq.com/hc/en-us/articles/22708154090267-Using-the-Kitchen-Display-System-2-0).
- **La comanda pasa sola a la siguiente etapa cuando se tacha el último plato**:
  [Odoo — pantalla de preparación](https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/preparation.html).
- **Una estación deja de ver una comanda en cuanto termina su parte; el pase («Todas») la sigue
  viendo entera** (Toast prep stations, Square KDS por estación, Fresh KDS): decisión de mercado de la
  duda 1 del producto actual.
- **Cada tableta recuerda su estación** (Toast, Square y Fresh configuran cada pantalla a una
  estación): decisión de mercado de la duda 4.
- **Imprimir el pase al marcar listo, apagado de fábrica; un solo interruptor de sonido con volumen
  y tono de una lista cerrada** (Toast, Fresh KDS, MobiPOS).
- **Lo que va solo a impresora no espera a que nadie lo marque**, y **cobrar no para la cocina**
  (Toast, Lightspeed K, Odoo, LS Central, Simphony): al cobrar sale lo que nadie va a marcar.

## Antes de empezar

- Al encender Cocina se encienden con ella **Ventas** e **Inventario**. **Mesas** y **Clientes** no
  hacen falta: sin Mesas, la comanda lleva la etiqueta de la cuenta o su tipo.
- Para que salga papel hace falta **Impresión** con una impresora de la función «Cocina» (o «Barra»)
  dada de alta (PRINTING-F04). Sin Impresión, Cocina funciona solo con la pantalla.
- Configuración inicial, paso a paso:
  1. En **Cocina → Estaciones**, crea las estaciones reales (Plancha, Barra, Postres) con su destino
     (pantalla, papel o ambos) y su impresora (KITCHEN-F01).
  2. En el panel «Enrutado», manda cada categoría a su estación y los productos sueltos que deban ir a
     otra (KITCHEN-F04). Lo que no tenga estación sale en la pantalla bajo «Sin estación» y por la
     impresora de cocina.
  3. En **Cocina → Ajustes**, ajusta los avisos ámbar y rojo, el sonido y, si se quiere, el pase en
     papel. Si en la cocina nadie va a marcar nada en la pantalla, apaga «La cocina trabaja con la
     pantalla» (KITCHEN-F26).
  4. En la tableta de la cocina abre **Cocina → Pantalla**, elige su estación, pulsa «Pantalla
     completa» y toca la pantalla una vez para que el navegador deje sonar el aviso (KITCHEN-F16).
  5. Envía una ronda de prueba desde el TPV y comprueba que cada plato sale en su estación.

## Pantallas

### Pantalla
Menú **Cocina → Pantalla**. El tablero de cocina. Una sola barra arriba, fija al desplazar: las tres
vistas en pestañas con su contador («Comandas» y «Listas»; «Resumen» sin contador), el botón «Pantalla completa»
y, si en las comandas en marcha hay platos de más de una estación, los botones de estación («Todas»,
cada estación por su nombre y con su color, y «Sin estación»). La estación elegida se recuerda en ese
dispositivo. Debajo, una rejilla de tarjetas de columnas iguales (una sola en el móvil). Cada tarjeta:
la etiqueta («Mesa 4»; sin etiqueta, el tipo), «Camarero: <nombre>», las marcas «Urgente», «VIP»,
«Ronda N» (desde la segunda) y «Lista», el reloj y el número corto «#0012»; los platos con la cantidad
grande, el nombre, sus suplementos en negrita, la nota en cursiva y, en «Todas», la estación; los platos
de un menú, junto a una raya bajo la cabecera del menú, que dice cuántos platos lleva («2 platos») y al
tocarla marca listos sus platos; un icono de papel si la estación es solo de papel. Un plato anulado en el TPV sale tachado, con «Anulado» y el motivo en rojo, y no
responde al toque. Al pie, según el permiso y el estado: «Listo», «Marcar urgente» / «Quitar
urgente», «Recuperar» y «Servida», enteros y del tamaño de un dedo en una tableta. El borde superior de la tarjeta va en verde, ámbar o rojo según el
tiempo desde que se envió. Vacía: «No hay comandas en marcha.» (Comandas), «No hay nada esperando a
recoger.» (Listas), «No queda nada por cocinar.» (Resumen). Cargando: «Cargando la pantalla…». Error:
«No se pudo cargar la pantalla de cocina» con «Reintentar». Un fallo al pedir papel deja «No se ha
podido imprimir el pase. Revisa la impresora de la estación.» o «No se ha podido imprimir el aviso de
urgencia. Avisa a cocina de viva voz y revisa su impresora.» hasta que una impresión posterior salga
bien. Se actualiza sola con cada cambio, sin recargar.

### Comandas
Menú **Cocina → Comandas**. Tabla de todas las comandas, la más nueva primero, 50 por página (otro
tamaño se elige al pie):
Comanda (número completo `AAAAMMDD-NNNN`), Destino (la etiqueta), Tipo, Prioridad, Estado, Platos y
Total; buscador «Buscar comanda o destino…» (por número y etiqueta), filtros por Tipo, Prioridad y
Estado (cada uno, una lista con sus palabras: «En sala», «Urgente», «Por preparar»…), y vista tabla o
tarjetas. Acciones por fila, solo icono: «Lanzar», «Lista», «Servida»,
«Recuperar» y «Cancelar» (en el menú «⋮», con confirmación y motivo opcional); solo salen las que el
perfil puede hacer y se esconden las que el estado no admite. Tocar una fila abre su detalle: los
platos con su menú, sus suplementos, su estación y su estado. «Nueva comanda» abre el panel (a pantalla completa en el móvil)
con Tipo, Destino, Notas y sus platos (producto del catálogo, cantidad y nota; «Añadir plato»), y
«Crear comanda». Vacía: «Sin comandas.». Cargando: el esqueleto de la tabla. Error de carga: el de la
tabla con reintento; un rechazo de una acción sale en su diálogo o encima de la tabla, y uno del alta,
dentro del panel.

### Estaciones
Menú **Cocina → Estaciones**. Tabla: Estación (con su color), Destino («Pantalla y papel», «Solo
pantalla», «Solo papel»), Impresora (la función —«Cocina», «Barra»— y, si se eligió, la impresora
concreta), En curso (platos por hacer de esa estación) y Activa («Sí»/«No»); buscador «Buscar
estación…». «Añadir estación» abre el panel con Nombre («p. ej. Plancha»), Color, Destino, Función de
impresora, Impresora «(opcional)» y Activa. Por fila: «Editar» (también tocando la fila), «Enrutar» (el
panel del enrutado con esa estación elegida) y «Eliminar», que pregunta «¿Eliminar «<nombre>»?». Debajo, el panel **Enrutado**: la lista de lo que va a cada
estación (Producto o Categoría, su nombre, la estación) con «Quitar» por fila, y «Enrutar» abre el
panel para elegir la estación y un producto o una categoría del catálogo («Guardar enrutado»). Vacía:
«Sin estaciones.» y «Nada enrutado todavía: todo sale en «Sin estación».». Cargando: el esqueleto.
Error: el de la tabla con reintento; cada rechazo dentro de su formulario o de su diálogo. Las
acciones solo salen a quien puede gestionar estaciones (responsable, administrador, propietario).

### Historial
Menú **Cocina → Historial**, título «Historial de cocina». Tabla de lo que pasó en cocina, lo último
primero, 50 por página (otro tamaño se elige al pie): Acción, Comanda (el número), Plato, Quién (el
nombre de la persona o, si no tiene, su correo; «Sistema» si lo hizo Cocina sola), Notas y Cuándo
(fecha y hora del negocio). Buscador «Buscar comanda o notas…» (un trozo del número o palabras de las
notas); filtro de acción con las mismas palabras de la columna («Recibida», «Creada», «Lanzada»,
«Lista», «Plato listo», «Plato recuperado», «Plato anulado», «Servida», «Recuperada», «Cancelada»,
«Urgente», «Urgencia quitada», «Reimpresa», «Borrada»). Vacía: «Sin actividad reciente en cocina.». Cargando: el esqueleto. Error:
el de la tabla con reintento.

### Ajustes
Pestaña **Cocina → Ajustes** (solo para quien puede guardarlos: responsable, administrador,
propietario). «Mostrar cronómetro», «Aviso ámbar (minutos)», «Aviso rojo (minutos)», «Semáforo de
color», «Sonar al entrar una comanda», «Volumen del sonido (0-100)», «Tono del sonido» («Campanilla»,
«Timbre», «Zumbador»), «Imprimir el pase al marcar listo», «La cocina trabaja con la pantalla» y
«Tipo de comanda por defecto» («En sala», «Para llevar», «A domicilio»), con «Guardar» (solo se puede
pulsar cuando algo cambió; al guardar, «Ajustes guardados.») y «Probar sonido». Cargando: «Cargando ajustes…». Error:
«No se pudieron cargar los ajustes.» con reintento; un rechazo al guardar, bajo el formulario con el
campo marcado.

## Estados de cada pantalla

| Pantalla | Cargando | Vacía | Error |
|---|---|---|---|
| Pantalla | «Cargando la pantalla…» | «No hay comandas en marcha.» · «No hay nada esperando a recoger.» · «No queda nada por cocinar.» | «No se pudo cargar la pantalla de cocina» + Reintentar |
| Comandas | esqueleto de la tabla | «Sin comandas.» (con búsqueda: «Sin resultados») | el de la tabla + Reintentar |
| Estaciones | esqueleto de la tabla | «Sin estaciones.» | el de la tabla + Reintentar |
| Historial | esqueleto de la tabla | «Sin actividad reciente en cocina.» | el de la tabla + Reintentar |
| Ajustes | «Cargando ajustes…» | — | «No se pudieron cargar los ajustes.» + Reintentar |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| KITCHEN-F01 | Crear una estación | hecho |
| KITCHEN-F02 | Editar, renombrar o desactivar una estación | hecho |
| KITCHEN-F03 | Eliminar una estación | hecho |
| KITCHEN-F04 | Mandar productos y categorías a una estación (y quitarlos) | hecho |
| KITCHEN-F05 | Recibir la ronda que envía el TPV | hecho |
| KITCHEN-F06 | Un menú del día en la comanda | hecho |
| KITCHEN-F07 | Notas de cada plato | hecho |
| KITCHEN-F08 | La comanda sale en papel en cada estación | hecho |
| KITCHEN-F09 | Reimprimir una comanda | hecho |
| KITCHEN-F10 | Ver el tablero de cocina | hecho |
| KITCHEN-F11 | Marcar platos listos | hecho |
| KITCHEN-F12 | Recuperar lo marcado por error | hecho |
| KITCHEN-F13 | Entregar lo que está listo | hecho |
| KITCHEN-F14 | Marcar urgente una ronda desde la pantalla de cocina | hecho |
| KITCHEN-F15 | Ver cuánto queda por cocinar | hecho |
| KITCHEN-F16 | Sonar al entrar una comanda | hecho |
| KITCHEN-F17 | Imprimir el pase al marcar lista | hecho |
| KITCHEN-F18 | Enviar la ronda desde el TPV, normal o urgente | hecho |
| KITCHEN-F19 | Seguir las comandas de la cuenta desde el TPV | hecho |
| KITCHEN-F20 | Marcar urgente una ronda desde el TPV | hecho |
| KITCHEN-F21 | Mover una comanda desde la lista de Comandas | hecho |
| KITCHEN-F22 | Cancelar una comanda | hecho |
| KITCHEN-F23 | Crear una comanda a mano | hecho |
| KITCHEN-F24 | Borrar una comanda | hecho |
| KITCHEN-F25 | Consultar el historial de cocina | hecho |
| KITCHEN-F26 | Ajustar la pantalla de cocina | hecho |
| KITCHEN-F27 | Cerrar las rondas al cobrar la cuenta entera | hecho |
| KITCHEN-F28 | Retirar las rondas de una cuenta eliminada o unida a otra | hecho |
| KITCHEN-F29 | Anular un plato ya enviado con aviso a cocina | hecho |
| KITCHEN-F30 | Pasar las comandas de un cliente unido a otro | descartado — la comanda no guarda cliente |
| KITCHEN-F31 | Dar a Caja las comandas que siguen en marcha | hecho |

### KITCHEN-F01 Crear una estación
<!-- origen: fi:modules/kitchen#command-kitchen-stations-create-update-sql fi:modules/kitchen#query-kitchen-stations-list old:kitchen/workflow/estaciones.md#kitchen-f01 wf:restaurante-dia#rec_restaurante-f02 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Estaciones
Pasos:
1. Pulsa «Añadir estación»: se abre el panel.
2. Escribe el nombre («p. ej. Plancha») y elige el color, el destino («Pantalla y papel», «Solo
   pantalla», «Solo papel»), la función de impresora («Cocina» o «Barra») y, si quieres, una impresora
   concreta por su nombre.
3. Pulsa «Crear estación»: el panel se cierra y la estación sale en la tabla, «Activa: Sí», «En
   curso: 0».
Entra: lo que escribe quien la crea.
Sale: la estación (avisa: estación creada).
Si falla: el rechazo sale dentro del panel. Un nombre que ya tiene otra estación viva se rechaza
(«Ya hay una estación con ese nombre.»); el de una eliminada vuelve a estar libre. Quien no puede
gestionar estaciones no ve el botón.
Implicados: KITCHEN-F02, KITCHEN-F03, KITCHEN-F04, KITCHEN-F08, PRINTING-F04

### KITCHEN-F02 Editar, renombrar o desactivar una estación
<!-- origen: fi:modules/kitchen#command-kitchen-stations-create-update-sql old:kitchen/workflow/estaciones.md#kitchen-f02 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Estaciones
Pasos:
1. Toca la fila (o «Editar»): se abre «Editar estación».
2. Cambia el nombre, el color, el destino, la impresora o «Activa».
3. Pulsa «Guardar»: la tabla se actualiza.
Entra: la estación y lo que cambia.
Sale: la estación cambiada (avisa: estación cambiada). Desactivarla hace que los platos que se envíen
después busquen la estación de su categoría y, si no hay, salgan «Sin estación». Lo ya enviado no cambia
de estación ni de destino; el nombre y el color que pinta la pantalla sí son los vivos.
Si falla: dentro del formulario. Un nombre repetido se rechaza; guardar una estación que otro
dispositivo acaba de eliminar dice que ya no existe.
Implicados: KITCHEN-F01, KITCHEN-F04, KITCHEN-F10, PRINTING-F04

### KITCHEN-F03 Eliminar una estación
<!-- origen: fi:modules/kitchen#command-kitchen-stations-delete-handler-wasm-delete_station old:kitchen/workflow/estaciones.md#kitchen-f03 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Estaciones
Pasos:
1. En la fila, «Eliminar»: sale «¿Eliminar «<nombre>»?» con «La estación sale de la lista y deja de
   recibir comandas. Las comandas ya enviadas la conservan en su historial.».
2. Pulsa «Eliminar estación».
Entra: la estación.
Sale: la estación retirada (no se borra) y su nombre libre (avisa: estación eliminada).
Si falla: con productos o categorías enrutados a ella, o con platos suyos por hacer, se rechaza con
«Esta estación no se puede eliminar: tiene productos o categorías enrutados, o platos por hacer.
Pásalos antes a otra estación.», dentro del diálogo.
Implicados: KITCHEN-F01, KITCHEN-F04, KITCHEN-F10

### KITCHEN-F04 Mandar productos y categorías a una estación (y quitarlos)
<!-- origen: wf:restaurante-dia#rec_restaurante-f17 wf:restaurante-dia#rec_restaurante-f02 fi:modules/kitchen#command-kitchen-stations-set_routing-handler-wasm-set_routing old:kitchen/workflow/estaciones.md#kitchen-f04 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Estaciones
Pasos:
1. En el panel «Enrutado», pulsa «Enrutar»: elige la estación y un producto o una categoría (por su
   nombre, del catálogo de Inventario).
2. Pulsa «Guardar enrutado»: sale en la lista del enrutado, sustituyendo el que tuviera.
3. «Quitar» en una fila del enrutado lo borra: lo que se envíe después irá por su categoría o «Sin
   estación».
Entra: la estación y los productos y categorías de Inventario.
Sale: el enrutado (avisa: enrutado cambiado). Solo afecta a lo que se envíe después. Al enviar, cada
plato va a la estación de su producto; si no tiene, a la de su categoría (la que la línea trae de
Ventas); si no, «Sin estación», que se ve en la pantalla y sale por la impresora de cocina. Una bebida
enrutada a una estación de barra sale por la impresora de la barra; si su cuenta no tiene título ni
canal, la comanda es «En sala», nunca «Para llevar».
Si falla: enrutar a una estación inactiva se rechaza («Esa estación está desactivada: actívala o elige
otra.»); un producto, una categoría o una estación que no existe, también. Si alguien lo borra en ese mismo
momento, el enrutado se rechaza igual o se guarda antes del borrado: nunca da error.
Implicados: KITCHEN-F01, KITCHEN-F05, KITCHEN-F08, INVENTORY-F04, INVENTORY-F06, INVENTORY-F07, INVENTORY-F27

### KITCHEN-F05 Recibir la ronda que envía el TPV
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 wf:restaurante-dia#rec_restaurante-f17 fi:modules/kitchen#command-kitchen-orders-create_from_sale-handler-wasm-create_order_from_sale fi:modules/kitchen#event-listen-sale-completed-kitchen-orders-create_from_sale old:kitchen/workflow/llegada-de-la-comanda.md#kitchen-f05 qa:modules/kitchen/kds-screen-and-courses qa:verticals/restaurant/06-service-orders-and-kitchen -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El camarero envía la ronda (KITCHEN-F18) o Ventas la envía sola (por el asistente o la API); la
   que envía Ventas sola llega a Cocina un momento después, sin que nadie haga nada.
2. Cocina abre una comanda con el número del día (`AAAAMMDD-NNNN`, el día del negocio, hora de
   Madrid), la ronda de la cuenta, la etiqueta de la cuenta («Mesa 4»), el tipo, la prioridad y el
   camarero.
3. Cada línea que no es un servicio es un plato, en el orden de la cuenta, mandado a su estación
   (KITCHEN-F04); un menú, un plato por cada plato elegido (KITCHEN-F06). Las líneas de servicio no se
   cocinan.
4. La comanda aparece en la pantalla «Por preparar», suena (KITCHEN-F16) y sale en papel
   (KITCHEN-F08).
Entra: de Ventas, las líneas enviadas de la cuenta (su ronda, su hora de envío, su producto, su
cantidad, su nota, sus suplementos, su categoría y, si es un menú, sus platos) y, cuando el envío lo hace Cocina, la prioridad, el canal y quién
envía.
Sale: la comanda «Por preparar» con sus platos y «Recibida» en el Historial, a la hora del envío
(avisa: comanda recibida).
Si falla: una ronda de solo servicios no abre comanda. Lo que se envió antes de que existiera Cocina en
el negocio no aparece. Una misma ronda nunca abre dos comandas, aunque llegue dos veces. Ningún fallo de
aquí bloquea al camarero.
Implicados: SALE-F20, KITCHEN-F04, KITCHEN-F06, KITCHEN-F07, KITCHEN-F08, KITCHEN-F16, KITCHEN-F18

### KITCHEN-F06 Un menú del día en la comanda
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 old:kitchen/workflow/llegada-de-la-comanda.md#kitchen-f06 -->
Estado: hecho
Actor: empleado
Pantalla: Pantalla
Pasos:
1. En el TPV, añade un menú eligiendo un plato de cada tanda (SALE-F12) y pulsa «Enviar comanda»
   (KITCHEN-F18).
2. En la tarjeta sale la cabecera del menú (su nombre de cocina o, si no tiene, su nombre) con cuántos
   platos lleva («2 platos»; «1 plato» si es uno) y, debajo, junto a una raya, cada plato elegido con la
   cantidad multiplicada por los menús pedidos.
3. Cada plato va a la estación de su propio producto o, si no tiene, a la de su categoría (KITCHEN-F04),
   nunca a la del menú: cada estación ve solo sus platos, con la misma cabecera encima.
4. Toca un plato para marcarlo listo, o toca la cabecera del menú para marcar listos de una vez sus
   platos que quedan en pantalla; el resto de la comanda no cambia.
5. En el papel de cada estación sale la cabecera del menú y, sangrados debajo, sus platos (KITCHEN-F08).
Entra: de Ventas, el menú tal como se pidió: sus platos elegidos (cada uno con su producto y su
categoría), su nombre de cocina, cuántos menús y la nota del menú, que sale en cada uno de sus platos.
Sale: un plato por cada plato del menú, cada uno en su estación, que se marca listo y se entrega por
separado; el importe del menú cuenta una sola vez en el total de la comanda (avisa: comanda recibida).
Si falla: un plato del menú que es un servicio no se cocina ni sale; un menú cuyos platos son todos
servicios no abre comanda. El TPV no deja añadir un menú sin elegir nada ni al que le falta una tanda
obligatoria, así que nunca llega vacío ni a medias. Anular el menú en el TPV tacha todos sus platos (KITCHEN-F29). Lo ya enviado no cambia aunque
el menú cambie después.
Implicados: SALE-F12, SALE-F20, COMBO-F11, KITCHEN-F04, KITCHEN-F08, KITCHEN-F29

### KITCHEN-F07 Notas de cada plato
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 old:kitchen/workflow/llegada-de-la-comanda.md#kitchen-f07 -->
Estado: hecho
Actor: empleado
Pantalla: Pantalla
Pasos:
1. En el TPV, elige los suplementos del plato («+QUESO», «sin cebolla», el punto) (SALE-F11) y, si hace
   falta, escribe una nota en la línea (SALE-F13); después envía la ronda.
2. En la tarjeta, debajo del nombre del plato salen sus suplementos en negrita, separados por comas y en
   el orden en que se eligieron, y debajo la nota en cursiva.
3. En el papel salen igual: cada suplemento en su renglón, sangrado bajo el plato, y después la nota
   (KITCHEN-F08).
Entra: de Ventas, los suplementos elegidos con su nombre de cocina (si no tiene, su nombre), la nota de
la línea y, si la línea va invitada, el motivo.
Sale: los suplementos y la nota congelados en el plato: cambiar el catálogo después no cambia esta
comanda.
Si falla: una alergia solo existe como texto de la nota: no se resalta ni se distingue de otra nota. Un
suplemento que se cobra en una línea aparte (otro IVA) sale igual bajo su plato.
Implicados: SALE-F11, SALE-F13, SALE-F20, MODIFIER-F08, KITCHEN-F08

### KITCHEN-F08 La comanda sale en papel en cada estación
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 old:kitchen/workflow/llegada-de-la-comanda.md#kitchen-f08 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al recibir la ronda, Cocina pide a Impresión una hoja por impresora: los platos de cada estación
   que no es «Solo pantalla», por su función («Cocina», «Barra») o por la impresora concreta de la
   estación; un plato sin estación, por «Cocina». Vale igual para la ronda que envía el camarero
   (KITCHEN-F18) y para la que Ventas envía sola, que se imprime cuando llega a Cocina.
2. La hoja lleva la etiqueta, el número, la ronda, el camarero y cada plato con su cantidad, sus
   suplementos (uno por renglón) y su nota, y los platos de un menú sangrados bajo su cabecera
   (KITCHEN-F06, F07); si la ronda va urgente, `!! URGENTE !!`.
Entra: los platos con el destino y la impresora congelados al recibir.
Sale: un trabajo por impresora en la cola de Impresión, una sola vez aunque se pida dos veces: la ronda
que envió Cocina no vuelve a imprimirse cuando le llega el aviso de Ventas.
Si falla: nunca bloquea al camarero. Sin Impresión no sale papel y no se avisa (la cocina trabaja con
la pantalla). Si Impresión rechaza el trabajo, la comanda sigue en la pantalla y se puede reimprimir
(KITCHEN-F09); en el TPV, el camarero ve «Comanda N enviada a cocina, pero no se imprimió. Revisa la
impresora de cocina en Impresión.» (KITCHEN-F18).
Implicados: KITCHEN-F05, KITCHEN-F06, KITCHEN-F07, KITCHEN-F09, KITCHEN-F18, SALE-F20, PRINTING-F04, PRINTING-F10, PRINTING-F18

### KITCHEN-F09 Reimprimir una comanda
<!-- origen: old:kitchen/workflow/llegada-de-la-comanda.md#kitchen-f09 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Comandas
Pasos:
1. En la fila, «⋮ → Reimprimir».
2. Sale otra hoja por cada impresora de sus platos, marcada como copia. Una comanda que nunca salió en
   papel sale como su primera hoja, sin «copia».
Entra: la comanda.
Sale: trabajos nuevos en la cola de Impresión (cada reimpresión es un trabajo distinto).
Si falla: «No se pudo imprimir la comanda.» con el motivo de Impresión; sin Impresión, «Impresión no
está activa en este negocio.».
Implicados: KITCHEN-F08, KITCHEN-F21, PRINTING-F11

### KITCHEN-F10 Ver el tablero de cocina
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 qa:modules/kitchen/kds-screen-and-courses qa:verticals/restaurant/06-service-orders-and-kitchen fi:modules/kitchen#query-kitchen-orders-items old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f10 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla
Pasos:
1. Abre **Cocina → Pantalla**. En una tableta, «Pantalla completa» deja solo el tablero en la
   pantalla, sin el menú del Hub; otro toque («Salir de pantalla completa») lo devuelve.
2. Arriba, las pestañas «Comandas», «Listas» y «Resumen». En «Comandas» están las que se cocinan: primero las urgentes, después las VIP y después el resto,
   la más antigua primero dentro de cada grupo.
3. Si hay platos de más de una estación, elige la tuya: «Todas» enseña todos los platos (el pase);
   una estación enseña solo sus platos y solo las comandas que aún tienen algo suyo por hacer; «Sin
   estación», los platos sin enrutar. La elección se recuerda en ese dispositivo.
4. El borde de cada tarjeta pasa de verde a ámbar al llegar a «Aviso ámbar» y a rojo al llegar a «Aviso
   rojo», contando desde que se envió; el reloj sigue en rojo. Sin «Semáforo de color» el borde queda
   gris; sin «Mostrar cronómetro» no hay reloj.
Entra: las comandas Por preparar, En preparación y Listas con sus platos; los ajustes; los nombres y
colores vivos de las estaciones.
Sale: nada; solo enseña. Los botones de cada tarjeta se ven enteros y se pulsan bien con el dedo en una
tableta.
Si falla: «No se pudo cargar la pantalla de cocina» con «Reintentar», un botón de tamaño normal. Sin
permiso de cambiar comandas, la pantalla es de solo mirar: sin botones y los platos no responden.
Implicados: KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F14, KITCHEN-F15, KITCHEN-F16, KITCHEN-F26

### KITCHEN-F11 Marcar platos listos
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 qa:verticals/restaurant/06-service-orders-and-kitchen fi:modules/kitchen#command-kitchen-orders-set_status-handler-wasm-update_order_status old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f11 qa:modules/kitchen/mark-ready-and-pass -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla (también el asistente: «marca lista la mesa 4»)
Pasos:
1. Toca un plato cuando esté hecho: se tacha con ✓.
2. O toca la cabecera de la tarjeta, o «Listo»: se marcan los platos de esa tarjeta que se ven en tu
   pantalla y siguen por hacer (en una estación, solo los suyos).
3. El primer plato marcado pasa la comanda a «En preparación». Cuando no queda ningún plato por hacer,
   de ninguna estación, la comanda pasa a «Lista»: sale de «Comandas» y aparece en «Listas».
Entra: los platos de la tarjeta.
Sale: cada plato listo (avisa: plato listo; Historial «Plato listo»), la comanda empezada («Lanzada»)
o lista («Lista»); con el pase encendido, sale en papel (KITCHEN-F17).
Si falla: dos cocineros que marcan el mismo plato a la vez lo marcan una vez. Un plato de una comanda
Servida o Cancelada se rechaza con «Esa comanda ya no está en el estado que requiere esta acción.
Actualiza e inténtalo de nuevo.».
Implicados: KITCHEN-F10, KITCHEN-F12, KITCHEN-F17, KITCHEN-F25

### KITCHEN-F12 Recuperar lo marcado por error
<!-- origen: fi:modules/kitchen#command-kitchen-orders-set_status-handler-wasm-update_order_status qa:modules/kitchen/mark-ready-and-pass old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f12 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla
Pasos:
1. Toca un plato tachado: vuelve a estar por hacer.
2. O «Recuperar» en la tarjeta (en una tableta, el botón se ve entero): vuelven los platos tachados
   que se ven en tu pantalla.
3. Una comanda de «Listas» se recupera con «Recuperar»: vuelve a «En preparación» y a «Comandas».
Entra: los platos tachados.
Sale: cada plato por hacer (avisa: plato recuperado; Historial «Plato recuperado») y, si la comanda
estaba Lista, «Recuperada». Recuperar lo que ya está por hacer no cambia nada.
Si falla: una comanda Servida o Cancelada no se recupera.
Implicados: KITCHEN-F10, KITCHEN-F11, KITCHEN-F16, KITCHEN-F21, KITCHEN-F25

### KITCHEN-F13 Entregar lo que está listo
<!-- origen: qa:verticals/restaurant/06-service-orders-and-kitchen fi:modules/kitchen#command-kitchen-orders-set_status-handler-wasm-update_order_status qa:modules/kitchen/mark-ready-and-pass old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f13 wf:restaurante-dia#rec_restaurante-f08 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla, Comandas
Pasos:
1. En «Listas», las comandas terminadas esperan a que alguien las recoja, la más antigua primero.
2. Cuando sale el plato, pulsa «Servida»: la tarjeta desaparece.
Entra: la comanda Lista.
Sale: la comanda Servida (avisa: comanda servida; Historial «Servida»). Al cobrar la cuenta entera,
las Listas pasan solas a Servidas (KITCHEN-F27).
Si falla: solo una comanda Lista se entrega.
Implicados: KITCHEN-F11, KITCHEN-F21, KITCHEN-F27

### KITCHEN-F14 Marcar urgente una ronda desde la pantalla de cocina
<!-- origen: old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f14 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla
Pasos:
1. En una tarjeta que se cocina, «Marcar urgente»: lleva «Urgente» y salta al principio del tablero
   en todas las pantallas, que suenan una vez.
2. Las estaciones que imprimen y aún tienen platos de esa ronda por hacer reciben un aviso corto en
   papel: la cabecera de la comanda con `!! URGENTE !!` y sin platos.
3. «Quitar urgente» lo deshace y no imprime nada. Una ronda VIP no ofrece el botón, y por el asistente
   o la API se rechaza («Esa comanda es VIP: marcarla urgente no cambia su prioridad.»).
Entra: la comanda que se cocina.
Sale: la ronda urgente (avisa: comanda cambiada; Historial «Urgente»); cada paso a urgente da un aviso
en papel nuevo.
Si falla: solo una comanda Por preparar o En preparación se marca urgente («Esa comanda ya no se
cocina.»). Si el aviso no se imprime, la pantalla lo dice.
Implicados: KITCHEN-F10, KITCHEN-F16, KITCHEN-F20, PRINTING-F10

### KITCHEN-F15 Ver cuánto queda por cocinar
<!-- origen: fi:modules/kitchen#query-kitchen-stations-pending_counts old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f15 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Pantalla (también el asistente: «qué hay pendiente en plancha»)
Pasos:
1. Pulsa «Resumen»: cada plato y la cantidad que falta por hacer sumando todas las comandas que se
   cocinan, de más a menos; en «Todas», con su estación.
2. Con una estación elegida, solo lo suyo.
Entra: los platos por hacer de las comandas Por preparar y En preparación.
Sale: nada.
Si falla: sin nada por hacer, «No queda nada por cocinar.».
Implicados: KITCHEN-F10, KITCHEN-F29

### KITCHEN-F16 Sonar al entrar una comanda
<!-- origen: old-hub:HUB_APP-F24 old-hub:HUB_APP-F26 old-hub:HUB_SHELL-F65 old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f16 -->
Estado: hecho
Actor: sistema
Pantalla: Pantalla
Pasos:
1. Con «Sonar al entrar una comanda», la pantalla suena cuando llega una comanda que no tenía o cuando
   una que tenía pasa a urgente; si llegan varias a la vez, una vez.
2. Suena con el tono y el volumen de Ajustes; al abrir la pantalla no suena por lo que ya estaba.
   Recuperar una comanda de «Listas» no vuelve a sonar: solo suenan las rondas nuevas y las urgencias.
Entra: las comandas de cada actualización y los ajustes.
Sale: el sonido; nada se guarda.
Si falla: si el navegador no deja sonar hasta el primer toque, ese aviso se pierde. Con volumen 0 no
suena.
Implicados: KITCHEN-F05, KITCHEN-F10, KITCHEN-F12, KITCHEN-F14, KITCHEN-F26

### KITCHEN-F17 Imprimir el pase al marcar lista
<!-- origen: qa:modules/kitchen/mark-ready-and-pass old:kitchen/workflow/pantalla-de-cocina.md#kitchen-f17 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. En **Cocina → Ajustes**, enciende «Imprimir el pase al marcar listo» (apagado de fábrica) y pulsa
   «Guardar».
2. Cada vez que una comanda pasa a Lista (KITCHEN-F11), sale el pase en la impresora de la estación de
   sus platos: una hoja por impresora con sus platos (no los de estaciones solo de pantalla), la
   etiqueta, el número, la ronda y el camarero.
Entra: la comanda que pasa a Lista.
Sale: trabajos en la cola de Impresión; una comanda recuperada y vuelta a marcar lista saca otro pase.
Si falla: la pantalla enseña «No se ha podido imprimir el pase. Revisa la impresora de la estación.».
Implicados: KITCHEN-F11, KITCHEN-F26, PRINTING-F10

### KITCHEN-F18 Enviar la ronda desde el TPV, normal o urgente
<!-- origen: wf:restaurante-dia#rec_restaurante-f07 qa:modules/kitchen/kds-screen-and-courses qa:verticals/restaurant/06-service-orders-and-kitchen old:kitchen/workflow/tpv.md#kitchen-f18 qa:modules/sales/take-order-by-courses qa:verticals/restaurant/11-races-and-concurrency -->
Estado: hecho
Actor: empleado
Pantalla: Ventas: Vender
Pasos:
1. En **Ventas → Vender**, con la cuenta abierta, abre la pestaña «Comanda actual»: lo que falta por
   enviar. Al añadir el primer producto, que abre la cuenta, el TPV se queda en esa pestaña.
2. Si la ronda corre prisa, toca la llama: el botón pasa a «Enviar URGENTE (N)». Cada toque la arma o
   la desarma.
3. Pulsa «Enviar comanda (N)» (o «Enviar URGENTE (N)»): sale «Comanda N enviada a cocina.» y la llama
   se desarma.
4. Ventas marca las líneas pendientes con una ronda nueva (SALE-F20) y Cocina abre la comanda
   (KITCHEN-F05), urgente si se armó la llama, y la imprime en cada estación (KITCHEN-F08).
Entra: la cuenta abierta con sus líneas sin enviar, su etiqueta, el canal, la prioridad y quién envía.
Sale: la comanda en la pantalla de cocina y en papel, con el nombre de quien envió la ronda (avisa:
comanda recibida).
Si falla: sin nada nuevo, «No hay nada nuevo que enviar a cocina.»: no es un error y no se envía nada.
Si la ronda se envía pero su hoja no se imprime, el TPV dice «Comanda N enviada a cocina, pero no se
imprimió. Revisa la impresora de cocina en Impresión.», nunca el motivo técnico; la comanda ya está en
la pantalla de cocina y se puede reimprimir (KITCHEN-F09). Si Cocina no responde, «No se ha podido
enviar la comanda a cocina. Inténtalo de nuevo.». Sin Cocina activa, el TPV no tiene pestaña ni botón.
Implicados: SALE-F20, KITCHEN-F05, KITCHEN-F08, KITCHEN-F09, KITCHEN-F19, PRINTING-F10

### KITCHEN-F19 Seguir las comandas de la cuenta desde el TPV
<!-- origen: wf:restaurante-dia#rec_restaurante-f08 old:kitchen/workflow/tpv.md#kitchen-f19 -->
Estado: hecho
Actor: empleado
Pantalla: Ventas: Vender (hoja «Comandas de la cuenta»)
Pasos:
1. En **Ventas → Vender**, con Cocina activa y permiso de ver comandas, la pestaña «Cuenta» enseña
   «Comandas · N» junto a la cabecera de lo enviado; púlsalo.
2. Se abre la hoja «Comandas de la cuenta»: una tarjeta por ronda, la más reciente primero, con
   «Comanda N», la hora de envío (la del negocio), su estado con las mismas palabras que la cocina
   («Por preparar», «En preparación», «Lista», «Servida», «Cancelada»), «Urgente» si lo es y sus platos
   (uno anulado, tachado con «Anulado»).
3. La hoja se actualiza sola mientras está abierta: lo que la cocina marca se ve sin recargar.
Entra: las comandas de esa cuenta, también las que llegaron de una cuenta unida a ella.
Sale: nada; solo enseña.
Si falla: si no se pueden cargar, «No se pudieron cargar las comandas de la cuenta.» con «Reintentar».
Sin permiso de ver comandas, o sin Cocina activa, el TPV no enseña «Comandas · N».
Implicados: SALE-F20, SALE-F24, KITCHEN-F05, KITCHEN-F20, KITCHEN-F28, KITCHEN-F29

### KITCHEN-F20 Marcar urgente una ronda desde el TPV
<!-- origen: wf:restaurante-dia#rec_restaurante-f08 old:kitchen/workflow/tpv.md#kitchen-f20 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Ventas: Vender (hoja «Comandas de la cuenta»)
Pasos:
1. Abre «Comandas de la cuenta» (KITCHEN-F19).
2. En la tarjeta de una ronda que se cocina (Por preparar o En preparación), pulsa «Marcar urgente»: la
   tarjeta lleva «Urgente» y, en la cocina, la ronda salta al principio del tablero y suena, como desde
   la pantalla de cocina (KITCHEN-F14).
3. Las estaciones que imprimen y aún tienen platos de esa ronda por hacer reciben el aviso corto en
   papel.
4. «Quitar urgente» lo deshace y no imprime nada.
Entra: la ronda que se cocina y quien la marca, con el permiso de cambiar comandas (el de KITCHEN-F14).
Sale: la ronda urgente o de vuelta a normal (avisa: comanda cambiada; Historial «Urgente» o «Urgencia
quitada»).
Si falla: si no se puede cambiar, «No se pudo actualizar la comanda». Si el aviso en papel no se
imprime, la hoja lo dice: «No se ha podido imprimir el aviso de urgencia. Avisa a cocina de viva voz y
revisa su impresora.». Una ronda Lista, Servida, Cancelada o VIP no lleva el botón, ni quien no puede
cambiar comandas lo ve. Sin Cocina activa, el TPV no enseña nada de esto.
Implicados: SALE-F20, KITCHEN-F14, KITCHEN-F19

### KITCHEN-F21 Mover una comanda desde la lista de Comandas
<!-- origen: fi:modules/kitchen#command-kitchen-orders-set_status-handler-wasm-update_order_status fi:modules/kitchen#command-kitchen-orders-update-sql fi:modules/kitchen#query-kitchen-orders-get fi:modules/kitchen#query-kitchen-orders-list old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f21 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Comandas
Pasos:
1. Busca la comanda o filtra por Tipo, Prioridad o Estado (cada filtro, una lista con sus palabras). Al
   pie, elige cuántas ver por página: con 25 se ven 25.
2. Usa la acción de su fila: «Lanzar» (Por preparar → En preparación), «Lista» (→ Lista, con todos sus
   platos), «Recuperar» (Lista → En preparación; sus platos listos vuelven a por hacer) o «Servida»
   (Lista → Servida).
Entra: la comanda.
Sale: el estado nuevo y su entrada en el Historial; la pantalla de cocina y el TPV se actualizan solos.
Si falla: si la comanda cambió en otra pantalla, «Esa comanda ya no está en el estado que requiere
esta acción. Actualiza e inténtalo de nuevo.».
Implicados: KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F19, KITCHEN-F22, KITCHEN-F23, KITCHEN-F25

### KITCHEN-F22 Cancelar una comanda
<!-- origen: old-hub:HUB_SHELL-F78 old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f22 qa:modules/kitchen/void-visible-in-kitchen -->
Estado: hecho
Actor: responsable
Pantalla: Comandas (también el asistente)
Pasos:
1. En la fila, «⋮ → Cancelar»: sale «¿Cancelar la comanda <número>?» con «Sale de la pantalla de
   cocina. La cuenta del TPV no cambia: los platos siguen en ella.» y un motivo opcional.
2. Pulsa «Cancelar comanda»: la comanda y sus platos pasan a «Cancelada» (un plato anulado sigue
   «Anulado»).
Entra: la comanda Por preparar, En preparación o Lista.
Sale: la comanda cancelada (avisa: comanda cancelada; Historial «Cancelada» con el motivo). Si la
ronda salió en papel, Cocina pide a Impresión un vale de anulación con lo que quedaba por hacer
(«ANULADA · Mesa 4», los platos en negativo), para que la cocina deje de prepararlo; también cuando la
ronda se cancela porque su cuenta se elimina en el TPV (KITCHEN-F28).
Si falla: una comanda Servida o Cancelada no se cancela. Una que nunca salió en papel no imprime vale.
Implicados: KITCHEN-F21, KITCHEN-F25, KITCHEN-F28, KITCHEN-F29, PRINTING-F10

### KITCHEN-F23 Crear una comanda a mano
<!-- origen: fi:modules/kitchen#command-kitchen-orders-create-handler-wasm-create_order old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f23 -->
Estado: hecho
Actor: empleado, responsable
Pantalla: Comandas
Pasos:
1. «Nueva comanda»: elige el Tipo (empieza en el de Ajustes), escribe el Destino y unas Notas si
   quieres, y añade sus platos (producto del catálogo, cantidad y nota).
2. «Crear comanda»: el panel se cierra y la comanda sale arriba de la lista (aunque estuvieras en
   otra página, la lista vuelve a la primera) y en la pantalla.
Entra: el tipo, el destino, las notas y los platos.
Sale: una comanda Por preparar, ronda 1, sin cuenta, con el nombre de quien la crea (avisa: comanda
creada; Historial «Creada»); sus platos van a su estación como los de una ronda.
Si falla: dentro del panel. Una comanda sin platos se rechaza («Añade al menos un plato.»). Como no
cuelga de ninguna cuenta, cobrar no la cierra.
Implicados: KITCHEN-F04, KITCHEN-F10, KITCHEN-F21, KITCHEN-F24, KITCHEN-F27, INVENTORY-F27

### KITCHEN-F24 Borrar una comanda
<!-- origen: fi:modules/kitchen#command-kitchen-orders-delete-handler-wasm-delete_order old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f24 -->
Estado: hecho
Actor: responsable
Pantalla: asistente o API
Pasos:
1. Pide al asistente que borre la comanda.
2. Solo se borra una comanda hecha a mano que esté Por preparar o Cancelada: se retira (no se borra de
   verdad) y desaparece de las listas.
Entra: la comanda.
Sale: la comanda retirada (avisa: comanda borrada; Historial «Borrada»).
Si falla: una comanda de una cuenta del TPV, o en marcha, se rechaza con «Esa comanda no se puede
borrar: viene de una cuenta o ya se está cocinando. Cancélala.». Borrar otra vez una ya borrada contesta
lo mismo y no cambia nada.
Implicados: KITCHEN-F22, KITCHEN-F23, KITCHEN-F25

### KITCHEN-F25 Consultar el historial de cocina
<!-- origen: fi:modules/kitchen#command-kitchen-logs-create-sql fi:modules/kitchen#event-listen-kitchen-order-fired-ready-served-recalled-cancelled-kitchen-logs-create fi:modules/kitchen#query-kitchen-logs-list old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f25 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Historial
Pasos:
1. Abre **Cocina → Historial**: qué pasó, en qué comanda y con qué plato, quién (su nombre o, si no
   tiene, su correo), sus notas y cuándo, lo último primero.
2. En «Buscar comanda o notas…», escribe un trozo del número de la comanda o unas palabras de las
   notas; filtra por acción («Recibida», «Cancelada»…).
3. Al pie, pasa de página o elige cuántas entradas ver (25, 50…).
Entra: las entradas que Cocina apunta sola: recibida, creada, lanzada, plato listo, recuperado o
anulado (con el motivo), lista, recuperada, servida, cancelada (con el motivo), urgente, urgencia
quitada, reimpresa y borrada.
Sale: nada; solo enseña.
Si falla: si no se puede cargar, «No se pudo cargar el historial» con «Reintentar». Quien no tiene
permiso de ver el historial lee «No tienes permiso para ver esto.».
Implicados: KITCHEN-F05, KITCHEN-F11, KITCHEN-F12, KITCHEN-F14, KITCHEN-F21, KITCHEN-F22, KITCHEN-F24, KITCHEN-F29

### KITCHEN-F26 Ajustar la pantalla de cocina
<!-- origen: fi:modules/kitchen#command-kitchen-settings-update-sql fi:modules/kitchen#query-kitchen-settings-get old:kitchen/workflow/comandas-historial-y-ajustes.md#kitchen-f26 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Ajustes
Pasos:
1. Cambia lo que haga falta: «Mostrar cronómetro», «Aviso ámbar (minutos)» (15), «Aviso rojo
   (minutos)» (30), «Semáforo de color», «Sonar al entrar una comanda», «Volumen del sonido (0-100)»
   (70), «Tono del sonido» («Campanilla»), «Imprimir el pase al marcar listo» (apagado), «La cocina
   trabaja con la pantalla» (encendido) y «Tipo de comanda por defecto» («En sala»). El tono y el tipo
   se eligen por sus palabras («Campanilla», «Timbre», «Zumbador»; «En sala», «Para llevar», «A
   domicilio»).
2. «Guardar» solo se puede pulsar cuando algo cambió: sale «Ajustes guardados.» y las pantallas
   abiertas los toman al momento.
Entra: los valores.
Sale: los ajustes (avisa: ajustes cambiados). «La cocina trabaja con la pantalla» vale desde el
siguiente cobro: lo cobrado antes se sirve a mano.
Si falla: minutos fuera de 1–120 o volumen fuera de 0–100 se rechazan; el ámbar igual o mayor que el
rojo, también («El aviso ámbar tiene que llegar antes que el rojo.»). El rechazo sale bajo el
formulario, con el campo marcado, y lo escrito se queda.
Implicados: KITCHEN-F10, KITCHEN-F16, KITCHEN-F17, KITCHEN-F23, KITCHEN-F27

### KITCHEN-F27 Cerrar las rondas al cobrar la cuenta entera
<!-- origen: wf:restaurante-dia#rec_restaurante-f11 wf:restaurante-dia#rec_restaurante-f17 old:kitchen/workflow/cierre-y-otros-modulos.md#kitchen-f27 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El cajero cobra la cuenta entera; un cobro parcial no cuenta.
2. Un momento después del cobro, sin que nadie haga nada, las rondas de esa cuenta que ya estaban
   Listas pasan a Servidas y salen de la pantalla. Las Por
   preparar y En preparación **no se tocan**: cobrar no para la cocina; cuando terminen, van a «Listas»
   y el pase las entrega.
3. Salvo lo que nadie va a marcar: con «La cocina trabaja con la pantalla» apagado (desde que se
   apagó), todas las rondas en marcha de la cuenta; y, con él encendido, la ronda cuyos platos fueron
   todos a estaciones «Solo papel». Esas pasan a Servidas con sus platos.
Entra: de Ventas, la cuenta cerrada.
Sale: cada ronda cerrada Servida, con su entrada en el Historial. Las comandas a mano no se tocan.
Si falla: un cobro de una parte de la cuenta (SALE-F22) no cierra ninguna ronda: siguen en la cocina
hasta que se cobra la cuenta entera. Con «La cocina trabaja con la pantalla» apagado, lo cobrado se
sirve al cobrar aunque nadie lo haya marcado; lo cobrado antes de apagarlo se sirve a mano
(KITCHEN-F26). Un aviso de cobro repetido no cambia nada: ninguna ronda se sirve dos veces.
Implicados: SALE-F01, SALE-F22, KITCHEN-F13, KITCHEN-F25, KITCHEN-F26

### KITCHEN-F28 Retirar las rondas de una cuenta eliminada o unida a otra
<!-- origen: qa:verticals/restaurant/08-incidents-voids-and-refunds old:kitchen/workflow/cierre-y-otros-modulos.md#kitchen-f28 wf:restaurante-dia#rec_restaurante-f10 wf:restaurante-dia#rec_restaurante-f14 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un responsable elimina en Ventas una cuenta abierta que ya envió rondas: un momento después, sin
   recargar, Cocina cancela las que siguen en marcha, con sus platos; salen de la pantalla y quedan en
   el Historial como canceladas. Si la ronda salió en papel, sale el vale «ANULADA · Mesa 4» con lo que
   quedaba por hacer (KITCHEN-F22).
2. Se juntan dos cuentas: las rondas enviadas desde la absorbida pasan a la que queda, como sus
   platos, en el mismo estado y con su etiqueta; al cobrar la que queda se cierran como las suyas.
Entra: de Ventas, la cuenta anulada o las líneas que cambiaron de cuenta.
Sale: rondas canceladas (avisa: comanda cancelada) o de otra cuenta.
Si falla: una ronda ya Servida o Cancelada no se toca. Una cuenta sin rondas en marcha no cambia nada
en la cocina, y un aviso repetido tampoco: ninguna ronda se cancela dos veces.
Implicados: SALE-F18, SALE-F24, KITCHEN-F19, KITCHEN-F22, KITCHEN-F25, KITCHEN-F27

### KITCHEN-F29 Anular un plato ya enviado con aviso a cocina
<!-- origen: old-hub:HUB_SHELL-F78 qa:verticals/restaurant/08-incidents-voids-and-refunds qa:verticals/restaurant/06-service-orders-and-kitchen qa:modules/kitchen/void-visible-in-kitchen wf:restaurante-dia#rec_restaurante-f14 old:kitchen/workflow/cierre-y-otros-modulos.md#kitchen-f29 qa:modules/sales/modify-order-after-sending -->
Estado: hecho
Actor: responsable (en el TPV)
Pantalla: Ventas: Vender
Pasos:
1. En el TPV se anula una línea ya enviada, con su motivo (SALE-F20).
2. Un momento después, en la pantalla de cocina y sin recargar, ese plato sale tachado con «Anulado» y el motivo; no se
   puede tocar, «Listo» ya no lo incluye y deja de contar en el «Resumen» y en «En curso».
3. La ronda sigue con lo que queda: si no queda nada vivo, pasa a Cancelada; si lo que queda ya está
   listo, pasa a Lista.
Entra: de Ventas, la línea anulada y su motivo.
Sale: el plato Anulado (avisa: plato anulado; Historial «Plato anulado» con el motivo). Si la ronda
salió en papel, sale el vale «PLATO ANULADO · Mesa 4» con ese plato.
Si falla: una ronda Servida o Cancelada no se toca.
Implicados: SALE-F20, COMBO-F11, KITCHEN-F06, KITCHEN-F10, KITCHEN-F15, KITCHEN-F19, KITCHEN-F25

### KITCHEN-F30 Pasar las comandas de un cliente unido a otro
<!-- origen: old:kitchen/workflow/cierre-y-otros-modulos.md#kitchen-f30 -->
Estado: descartado — la comanda no guarda cliente: unir dos fichas de cliente no toca Cocina
Actor: nadie en Cocina (la unión la hace Clientes)
Pantalla: ninguna
Pasos:
1. En Clientes se unen dos fichas de la misma persona (CUSTOMER-F13) y Ventas pasa sus ventas a la que
   queda (SALE-F33).
2. En Cocina no pasa nada: la comanda guarda la etiqueta de la cuenta como texto y ningún cliente, así
   que no hay nada que pasar.
Entra: nada; el TPV no manda el cliente a Cocina.
Sale: nada; las comandas no cambian.
Si falla: no aplica: Cocina no hace nada que pueda fallar.
Implicados: CUSTOMER-F13, SALE-F33

### KITCHEN-F31 Dar a Caja las comandas que siguen en marcha
<!-- origen: wf:restaurante-dia#rec_restaurante-f16 old:kitchen/workflow/cierre-y-otros-modulos.md#kitchen-f31 qa:verticals/restaurant/09-register-closing-and-reports -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al pulsar «Cerrar sesión» en Caja, Caja pregunta a Cocina qué comandas siguen en marcha.
2. Cocina devuelve las Por preparar, En preparación y Listas con su etiqueta, su número y sus platos;
   Caja las enseña en «Revisión del turno» como «Comandas sin servir: N» (CASH_REGISTER-F08).
Entra: la consulta, con el permiso de ver comandas de quien cierra.
Sale: la lista; en Cocina no cambia nada.
Si falla: si quien cierra no tiene permiso de ver comandas, Caja no las lista y avisa de que la revisión
puede estar incompleta («No se ha podido comprobar lo que queda pendiente, así que esta revisión puede
estar incompleta.»). Con Cocina apagada no hay comandas pendientes. Nunca impide cerrar la caja.
Implicados: CASH_REGISTER-F08, CASH_REGISTER-F09, KITCHEN-F10, KITCHEN-F13

## Para quien lo mantiene

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| El tablero: las comandas en marcha y las listas, por estación, con sus platos, las estaciones que salen en ellas y los contadores | ver comandas | F10, F13, F31 | `kitchen.ticket.board` |
| Lo que queda por cocinar, sumado por plato y estación | ver comandas | F15 | `kitchen.ticket.all_day` |
| Las comandas, con búsqueda, filtros y páginas | ver comandas | F21 | `kitchen.ticket.list` |
| Una comanda por id, número o etiqueta («la mesa 4») | ver comandas | F21 | `kitchen.ticket.get` |
| Las comandas de una cuenta de Ventas | ver comandas | F19 | `kitchen.ticket.by_order` |
| Las estaciones, con lo que tienen en curso | ver comandas | F01–F03 | `kitchen.station.list` |
| El enrutado de productos y categorías | ver comandas | F04 | `kitchen.routing.list` |
| Los ajustes (los de fábrica si nunca se guardaron) | ver comandas | F26 | `kitchen.settings.get` |
| El historial | ver el historial | F25 | `kitchen.log.list` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Envía a cocina lo pendiente de una cuenta (por Ventas) y abre la comanda, normal o urgente | enviar | F18 | `kitchen.ticket.send` |
| Abre la comanda de una ronda ya enviada (la reacción al envío y lo que Ventas llama por nombre) | enviar | F05 | `kitchen.ticket.receive` |
| Crea una comanda a mano | enviar | F23 | `kitchen.ticket.create` |
| Lanza, marca lista, recupera una comanda | cambiar comandas | F21 | `kitchen.ticket.start`, `.ready`, `.recall` |
| Marca servida una comanda | entregar | F13 | `kitchen.ticket.serve` |
| Marca o quita la urgencia | cambiar comandas | F14, F20 | `kitchen.ticket.set_rush` |
| Reimprime una comanda | cambiar comandas | F09 | `kitchen.ticket.reprint` |
| Cancela una comanda (riesgo alto) | cancelar | F22 | `kitchen.ticket.cancel` |
| Borra una comanda a mano (riesgo alto) | borrar | F24 | `kitchen.ticket.delete` |
| Marca listos o recupera platos | cambiar comandas | F11, F12 | `kitchen.item.bump`, `kitchen.item.recall` |
| Crea, cambia y elimina estaciones (eliminar, riesgo alto) | gestionar estaciones | F01–F03 | `kitchen.station.create`, `.update`, `.delete` |
| Enruta y quita el enrutado | gestionar estaciones | F04 | `kitchen.routing.set`, `kitchen.routing.clear` |
| Guarda los ajustes | ajustes | F26 | `kitchen.settings.update` |
| Pone al día las comandas de una cuenta con lo que hizo Ventas (reacción del sistema) | sistema | F27–F29 | `kitchen.ticket.sync` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Comanda recibida | Llega una ronda | La comanda, su número, la cuenta y la ronda | `kitchen.ticket.received` |
| Comanda creada | Alta a mano | La comanda y su número | `kitchen.ticket.created` |
| Comanda lanzada, lista, recuperada, servida, cancelada, borrada | Sus acciones y los cierres de F27–F29 | La comanda y su número (la cancelada, su motivo) | `kitchen.ticket.started`, `.ready`, `.recalled`, `.served`, `.cancelled`, `.deleted` |
| Comanda cambiada | Urgencia | La comanda y su prioridad | `kitchen.ticket.updated` |
| Plato listo, recuperado, anulado | Sus acciones y F29 | La comanda y los platos (el anulado, su motivo) | `kitchen.item.bumped`, `.recalled`, `.voided` |
| Estación creada, cambiada, eliminada | F01–F03 | La estación | `kitchen.station.created`, `.updated`, `.deleted` |
| Enrutado cambiado | F04 | La estación y el producto o la categoría | `kitchen.routing.changed` |
| Ajustes cambiados | F26 | Los campos que cambiaron | `kitchen.settings.updated` |

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Comanda enviada (`sale.order.fired`) | Ventas | Abre la comanda de esa ronda con su prioridad, su canal y su camarero, e imprime | `kitchen.ticket.receive` |
| Cuenta cerrada (`sale.order.completed`), anulada (`sale.order.voided`), línea anulada (`sale.order.line_voided`) | Ventas | Pone al día las comandas de la cuenta (F27–F29) | `kitchen.ticket.sync` |

Las reacciones las entrega el relay del outbox, en el worker (hub#105), que corre en producción: una
ronda que Ventas envía sola, un cobro, una cuenta eliminada o unida y una línea anulada llegan solos a
Cocina un momento después del COMMIT de Ventas (y la ronda se imprime, una sola vez). Además, **lo que
hizo Ventas se lee en cada lectura y se asienta en cada escritura**, para el rato entre el COMMIT y la
reacción. Una ronda enviada que
Cocina aún no tiene se pinta igual (comanda «por recibir», con el número que tendrá) y la primera
escritura de Cocina la guarda; una cuenta cobrada, anulada o una línea anulada cambian el estado que se
lee, y la primera escritura lo guarda con su Historial. `live.py` re-ejecuta las consultas con los
avisos de Ventas (`sale.order.*`).

### Lo que necesita de otras apps

- **Ventas** (requisito): sus cuentas y sus líneas enviadas (`Order`, `OrderLine`: ronda, hora de
  envío, producto, nombre, cantidad, nota, categoría, anulación y su motivo, estado y hora de cierre de
  la cuenta, y lo que la línea congeló al pedirse: los suplementos con su nombre de cocina, `modifiers`,
  y el menú con su `kitchen_name` y sus platos, `combo.components`), leídas con sus modelos; el envío,
  por su operación `sale.order.fire`. Un plato de un menú guarda la línea del menú y su número dentro de
  él (`menu_dish`); su id sale del de la línea (`queries.dish_id`), así que la comanda por recibir y la
  guardada comparten los ids de sus platos.
- **Inventario** (requisito): los productos y las categorías del enrutado (claves ajenas) y sus
  listas para elegirlos (`inventory.product.list`, `inventory.category.list`).
- **Impresión** (opcional): `printing.job.create` por nombre, con el documento `kitchen_order`
  («Contrato con la plataforma» de Impresión). Sin Impresión (`UnknownOperation`, `app_inactive`) no
  sale papel y no es un error; otro rechazo se dice en la pantalla y no deshace la acción.

### Lo que pide a otras apps

- **A Ventas** (ya hecho, en su pantalla «Vender»): la pestaña «Comanda actual» con «Enviar comanda»
  y la llama de urgencia (SALE-F20, KITCHEN-F18): con Cocina activa, el botón llama a
  `kitchen.ticket.send` (`priority: "rush"` si se armó la llama), y sin ella, a `sale.order.fire`; y la
  hoja «Comandas de la cuenta» (KITCHEN-F19, F20): `useLive('kitchen.ticket.by_order', {order_id})` y
  `kitchen.ticket.set_rush`, con los textos y estados de la pantalla de cocina.
- **A Ventas** (sigue pedido):
  1. Un aviso propio del cambio de título de una cuenta (p. ej. `sale.order.relabeled`): la pantalla ya
     no se relanza con `sale.order.changed` (cada línea añadida en cualquier TPV la relanzaba), así que
     el título nuevo de una ronda por recibir sale en el siguiente aviso de cocina.
  2. Índices parciales para la lectura de las rondas por recibir: `sale_orderline(fired_at) WHERE
     fired_at IS NOT NULL` y `sale_order(closed_at)`.
- **A Impresión**: nada nuevo; usa `kitchen_order` tal como está. Cada plato lleva además sus
  suplementos (`modifiers`, una lista) y, si es de un menú, `combo_ref` (la línea del menú) y
  `combo_name` (su cabecera), que la impresora de la app ya pinta (KITCHEN-F06, F07).
- **A Caja** (ya hecho): avisar al cerrar de las comandas sin servir con `kitchen.ticket.board`
  (CASH_REGISTER-F08, KITCHEN-F31).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver comandas, estaciones, enrutado y ajustes | sí | sí | sí | sí | `kitchen.view_ticket` |
| Enviar rondas y crear comandas a mano | sí | sí | sí | sí | `kitchen.add_ticket` |
| Cambiar comandas (lanzar, listo, recuperar, urgencia, reimprimir) | sí | sí | sí | sí | `kitchen.change_ticket` |
| Entregar (servida) | sí | sí | sí | sí | `kitchen.complete_ticket` |
| Cancelar comandas | sí | sí | sí | no | `kitchen.cancel_ticket` |
| Borrar comandas a mano | sí | sí | sí | no | `kitchen.delete_ticket` |
| Gestionar estaciones y enrutado | sí | sí | sí | no | `kitchen.manage_station` |
| Guardar los ajustes | sí | sí | sí | no | `kitchen.change_settings` |
| Ver el historial | sí | sí | sí | sí | `kitchen.view_log` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); el
cajero y el cocinero del producto actual son empleados. `kitchen.ticket.sync` pide `kitchen.system`,
que no tiene ningún papel: solo el sistema (`*`).

### Notas técnicas

- Anatomía completa: `apps.py`, `models.py`, `migrations/` (`0002` crea la fila de ajustes con la
  hora desde la que Cocina recibe, con reverso), `schemas.py`, `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un `tests/test_<fichero>.py`
  por fichero, más `test_integration_sale.py`, `test_integration_inventory.py` y `test_concurrency.py`
  con las apps reales.
- **`requires = ["sale", "inventory"]`**. El enrutado apunta a `inventory.Product` y
  `inventory.Category` con clave ajena. Las cuentas y las líneas de Ventas, por UUID opaco
  (`Ticket.order_id`, `TicketItem.sale_line_id`): sin clave ajena, como Mesas.
- **Modelos**: `Station`, `ProductRoute`, `CategoryRoute`, `KitchenSettings` (una fila), `DayCounter`
  (uno por día del negocio), `Ticket` (la comanda: número, día, cuenta y ronda, etiqueta, tipo,
  prioridad, estado, camarero, horas de recibida, empezada, lista, servida y cancelada, urgencias,
  total informativo, borrado lógico), `TicketItem` (el plato: línea de Ventas, nombre, cantidad, nota,
  estación, destino, función e impresora congelados, estado, motivo de anulación) y `LogEntry`.
- **La comanda de una ronda se identifica por su primera línea**: el id de la comanda es el de la
  primera línea de Ventas de la ronda y el de cada plato el de su línea (UUIDv7 de Ventas), así una
  comanda «por recibir» y la guardada tienen el mismo id y la pantalla no salta. Las comandas a mano
  y sus platos, UUIDv7 nuevos. Una ronda = las líneas de una cuenta con la misma ronda y la misma hora
  de envío.
- **Estados**. Comanda: `pending` → `preparing` → `ready` → `served`; `ready` → `preparing`
  (recuperar); `pending|preparing|ready` → `cancelled`. Plato: `pending`, `preparing`, `ready`,
  `served`, `cancelled`, `voided`. Lo que se sale del camino es 409 `kitchen.invalid_transition`, sin
  escribir nada ni avisar.
- **Asentar** (`settle`, al empezar toda escritura): bloquea la fila de ajustes (todas las escrituras
  de Cocina de un negocio van en fila: dos cocineros a la vez no se pisan), guarda las rondas por
  recibir y aplica lo que hizo Ventas. El «Eliminar» de una estación en el admin del Hub entra en la misma
  fila (`StationAdmin.delete_model`/`delete_queryset` bloquean antes la fila de ajustes), como el de Cocina:
  espera a la escritura en curso, así ninguna ruta, plato ni línea del Historial nombra una estación borrada
  a la vez, y la escritura que llega detrás ya no la ve (su plato va por su categoría o a «Sin estación»).
  **Enrutar** bloquea primero la ruta que sustituye y después retiene su producto o su categoría hasta el
  COMMIT (`held` de Inventario, `FOR KEY SHARE`), en el mismo orden en que borra el admin (primero lo que
  apunta a la fila, la fila al final): el «Eliminar» de Inventario o el del admin espera a la ruta, uno ya en
  curso se lee terminado, como uno borrado antes (404 `kitchen.product_not_found`,
  `kitchen.category_not_found`, `kitchen.station_not_found`), y nunca hay un 500, un interbloqueo ni una ruta
  creada a algo ya borrado. Quitar una ruta solo la bloquea (no nombra nada). Probado con hilos en
  `test_concurrency.py`. Las mismas reglas las aplica la lectura sin escribir
  (`queries.effective`): F29 (plato anulado), F28 (cuenta anulada) y F27 (cerrada: la Lista desde
  antes del cierre pasa a Servida; la de papel o con la cocina en papel desde antes del cierre, a
  Servida con sus platos).
- **Número del día** por `DayCounter` con `select_for_update` en la transacción; una comanda por
  recibir enseña el que tendrá (el siguiente del contador por orden de envío).
- **Desde cuándo recibe**: `KitchenSettings.receiving_since` (la hora a la que se crearon sus tablas):
  lo enviado antes no aparece. Sin fila de ajustes (una base de datos vaciada), recibe todo.
- **Rondas por recibir, solo de cuentas vivas**: una ronda que Cocina no ha guardado se lee de Ventas
  mientras su cuenta sigue abierta o se cerró hace menos de un día (`UNSAVED_WINDOW`); así una cocina
  que no escribe nunca (en papel) no relee un pasado creciente. La reacción al envío guarda cada ronda
  un momento después de enviarse, así que la ventana solo cubre el rato hasta que llega.
- **Papel**: `printing.job.create` en la misma transacción, en un savepoint; un rechazo no deshace la
  acción (vuelve en `print_error`). `Ticket.printed_at` dice cuándo se encoló su primera hoja: solo una
  comanda que salió en papel recibe vales de anulación (F22, F29) y copias (F09). El pase sale también
  cuando la comanda queda Lista por una anulación del TPV (F17). Claves: `kitchen-<comanda>-<función>-<impresora>` (comanda),
  `…-pass-<hora de lista>` (pase), `…-rush-<n>` (urgencia), `…-void` (vale), `…-copy-<n>` (copia).
- **Coste de lo vivo**: las rondas por recibir se leen en dos consultas (cuentas abiertas, por su
  estado; cerradas hace menos de un día, por su cierre). La pantalla, la lista y el Historial no se
  relanzan con `sale.order.opened`/`changed` (líneas añadidas en cualquier TPV); solo las comandas de una
  cuenta (`by_order`), que una división mueve. «Resumen» se sigue solo mientras está abierto.
- **Estación eliminada**: no se encuentra ni por id ni por nombre (`kitchen.station_not_found`) y ya no
  sale entre los botones; la pantalla que la recordaba vuelve a «Todas» en vez de quedarse vacía para
  siempre (eliminarla exige que no tenga platos por hacer ni enrutado, F03).
- **Zona horaria**: fase 1, la del negocio es `settings.TIME_ZONE` (Europe/Madrid): día del número y
  horas del Historial.
- Toda lista pagina (`limit` ≤ 100) con desempate por `id`; el tablero tiene un tope de 200 comandas en
  marcha (`truncated`).

### Cambios frente al producto actual

| Producto actual | Ahora | Por qué |
|---|---|---|
| El reloj vuelve a cero cuando cocina toca la comanda | Cuenta desde el envío | BD-08 y el mercado: el semáforo mide la espera real |
| «Lista» desde Comandas no tachaba los platos | Los tacha | Dejaba platos colgados que impedían borrar la estación |
| Una estación ve su tarjeta tachada hasta que terminan las demás | Sale de esa estación al terminar su parte; el pase la sigue viendo | Duda 1, mercado (Toast, Square, Fresh) |
| La estación elegida no se recuerda | Se recuerda en el dispositivo | Duda 4, mercado |
| Color e Impresora de la estación no hacían nada; destino y función solo por API | Color en la pantalla; destino, función e impresora en el formulario | Duda 5: lo que se ve, hace algo |
| Enrutado invisible, sin quitar, y a una estación inactiva decía «guardado» | Lista con «Quitar» y rechazo claro | Parcial de F04 |
| Nueva comanda a mano sin platos | Con platos | Duda 6: una tarjeta vacía no sirve |
| Cancelar sin confirmación ni motivo | Confirmación y motivo opcional | Parcial de F22 |
| Borrar contestaba bien sin borrar | Rechazo claro | Parcial de F24 |
| No había reimpresión | «Reimprimir» | F09 |
| Historial sin quién, sin plato; urgencias y borrados sin apuntar | Con quién, plato, urgencia y borrado | Parcial de F25 |
| El número del día iba en UTC | Día del negocio (Madrid) | Entre medianoche y la 1–2 salía el día anterior |
| La hoja del TPV enseñaba la hora en UTC | La hora del envío, en la del negocio | F19 |
| Pase y aviso de urgencia los imprimía la pantalla | Los pide el servidor en la transacción | Sin reacciones del cliente (PLAN §14) |
| Unión de clientes (F30) | Descartado | La comanda no guarda cliente |
| Apuntar en el historial a mano (`kitchen.logs.create`) | Retirado | Un historial que se escribe a mano deja de ser historial; ningún KDS lo ofrece |
| Ajustes retirados en kitchen#48 (aceptar y retirar solas…) | No vuelven | No movían nada |

### Contradicciones (sin resolver; se señalan)

- **Fase 1 sin tenencia**: todas las cuentas comparten tablas, así que la pantalla de cocina de un hub
  lee también las rondas de otro (`b.localhost` ve las de `a.localhost`). Lo resuelve la BD por hub de la
  fase 2.
- **Quién sale en la comanda**: la comanda nombra a quien **envía** la ronda (nunca vacío); el producto
  actual ponía a la persona de «Atiende» del TPV (SALE-F16), y Ventas manda también quién atiende con la
  ronda (kitchen#82, hub#2033, staff#59). Se señala, no se elige.
- **Ronda de una cuenta fusionada**: Ventas conserva su `round_no`, así que la cuenta que queda puede
  tener dos «Comanda 1»; el producto actual las renumeraba detrás de las suyas.

### Lo que queda fuera

- Iconos deseados (`UI-REQUESTS.md`).
- Vaciar de golpe las comandas cobradas antes de pasar la cocina a papel (kitchen#158): hoy se sirven a
  mano (KITCHEN-F26, F27). Comportamiento nuevo, después del MVP.
- Alérgenos de punta a punta (pm#115): hoy una alergia es solo texto de la nota (KITCHEN-F07).
  Comportamiento nuevo, después del MVP.
