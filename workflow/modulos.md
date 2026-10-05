# WORKFLOW — Hub (servidor) · Módulos: consultas y órdenes

Prefijo: HUB

> Lo que hace el servidor del hub cuando una pantalla, el asistente, una automatización, otra
> aplicación o una integración le piden **datos** (una consulta) o le piden **hacer algo** (una
> orden) de un módulo; la página pública donde un cliente sin sesión canjea un localizador; y el
> redondeo común del dinero. El ciclo de vida de las aplicaciones (instalar, actualizar, apagar,
> quitar), sus ajustes, sus paneles de Inicio y la lista de puesta en marcha están en
> [modulos-aplicaciones.md](modulos-aplicaciones.md). Lo técnico vive en
> `architecture/hub/runtime-dispatcher.md` y `architecture/hub/module-system.md`; aquí se escribe lo
> que se observa.

## Referencia adoptada

Para las consultas y las órdenes (la de instalar y quitar apps está en
[modulos-aplicaciones.md](modulos-aplicaciones.md)):

- Toast y Square: la aprobación del responsable con su código en el momento, para una sola acción
  (HUB-F05; referencia contrastada en el módulo de Venta, SALES-F14).
- Cuiner *QuieroFactura* y Ágora *Crear factura*: el tique lleva un código para pedir la factura
  completa desde casa (HUB-F16, HUB-F17); plazo:
  [RD 1619/2012, art. 11.2](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696).
- [JSON Schema](https://json-schema.org/): el contenido de cada orden y consulta se valida contra el
  esquema que declara su módulo, con sus valores por defecto (HUB-F04).
- [Ley 46/1998, art. 11](https://www.boe.es/buscar/act.php?id=BOE-A-1998-29550): la mitad exacta se
  redondea hacia arriba; es el redondeo común del dinero (HUB-F18).

## Flujos

### HUB-F01 Leer datos de un módulo
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla de un módulo, el asistente, una automatización o una integración pide una consulta por su nombre (`modulo.entidad.accion`) con sus datos de búsqueda.
2. El hub comprueba la sesión (o la llave de API). En `/api/query` comprueba además que la app esté incluida en el plan del hub (402); la llave de API, las automatizaciones y las lecturas internas no lo comprueban.
3. Por este orden: que la app dueña esté instalada y activa; que quien pregunta tenga el permiso que la consulta declara (una consulta nunca pide el PIN de un responsable: sin permiso se rechaza y ya está); el esquema de la consulta, sin rellenar valores por defecto; y, después de añadir los datos del hub, que no llegue ningún dato que la consulta no conozca ni falte ninguno que su SQL necesite. Una consulta no pasa por el bloqueo de otra app (HUB-F13) ni tiene versión interna.
4. Añade por su cuenta el negocio (hub), quién pregunta, la hora, la identidad fiscal del negocio, su zona horaria, el idioma de quien pregunta, si el negocio es una demo, si tiene certificado y si la app tiene concedidos sus permisos de host; nadie puede mandar esos valores desde fuera.
5. Devuelve las filas. Si la consulta es de lista, devuelve la página con el total (HUB-F02).
Entra: el nombre de la consulta y sus datos (`POST /api/query`, o `POST /api/v1/{módulo}/q/{consulta}` con llave si el módulo la marca `expose_api`); la sesión de quien pregunta; los ajustes del negocio (`hub_settings`).
Sale: nada guardado. Una consulta de un módulo no instalado o apagado contesta `module_not_installed` / `module_inactive` (404), que el SDK de los módulos convierte en «no hay» cuando la pide como opcional; la de un módulo fuera del plan, por `/api/query`, `module_entitlement_blocked` (402).
Si falla: sin sesión, 401, sin código estable (`{"ok": false, "error": "<texto>"}`). Sin permiso, `permission_denied` (403). Un dato que no cumple el esquema, `invalid_payload` (422). Un dato que la consulta no conoce, `unknown_filter` (422), con la lista de los aceptados solo dentro de la frase; uno que falta, `missing_required_param` (422): antes contestaban «no hay nada» y se confundían con una ficha inexistente (hub#1173, hub#1913, hub#2383). Las lecturas que hace el propio hub por una orden (lecturas previas, bloqueos, cambios parciales) toleran el dato que falta y lo dejan vacío. Una consulta inexistente en una app activa es `not_found` (contrato roto). El error, también un rechazo normal de permiso o de esquema, se anota en el registro de errores atribuido al módulo, con las claves del payload y nunca sus valores. Por la llave de API, una consulta no publicada da 404 y una publicada sin llave válida da 401, así que se puede averiguar qué está publicado.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso: la sesión, la llave de API y el permiso de cada perfil que el hub comprueba en cada puerta
Pendiente de enlazar: hub — HUB, acceso: el bloqueo de un módulo que el plan del hub ya no incluye (`module_entitlement_blocked`)
QA: qa-hub §11

### HUB-F02 Pedir una lista con búsqueda, filtros, orden y páginas
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Una tabla de una pantalla pide la lista de un módulo con, si quiere, el texto del buscador, los filtros por columna, la columna por la que ordenar, el sentido y la página.
2. El hub solo acepta los filtros que la lista declara; un filtro que no existe se rechaza en vez de devolver la lista entera.
3. Busca el texto sin distinguir mayúsculas en las columnas declaradas como buscables; aplica cada filtro (igual, contiene o entre dos valores); un rango de fechas que acaba en un día incluye todo ese día.
4. Ordena solo por una columna permitida (si no, por la de fábrica), deja las filas sin valor al final en los dos sentidos y desempata por la ficha, para que dos páginas no repitan ni salten filas.
5. Devuelve la página, el total de filas que cumplen y el tamaño y desplazamiento usados.
Entra: los datos de la lista (`limit`, `offset`, `search`, `sort`, `dir`, `f_<columna>`, `f_<columna>_from`/`_to`) y los datos de contexto que su SQL use.
Sale: `{rows, total, limit, offset}`. Sin tamaño pedido manda el que declara el módulo; con tamaño pedido se devuelve exactamente ese, sin tope oculto. Cuando el propio hub lee una lista entera (lecturas previas de una orden, guardas, avisos) recorre todas las páginas y se niega con un error claro por encima de 100.000 filas, en vez de cortar en silencio.
Si falla: una página pedida más allá del final devuelve `total: 0` en lugar del total real (defecto). Un extremo de rango que la columna no sabe leer, `invalid_filter_bound` (422); un dato de contexto obligatorio que falta, `missing_required_param` (422). Si el hub no puede averiguar el tipo de las columnas, ordena sin desempate y compara los rangos tal como llegaron, y lo deja escrito en el registro.
Implicados: ninguno
QA: qa-hub §11

### HUB-F03 Ejecutar una orden de un módulo
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla, el asistente, una automatización, otra aplicación (por un aviso o una tarea programada) o una integración pide una orden por su nombre con su contenido.
2. El hub comprueba la sesión y que la app esté instalada y activa. Solo en `/api/command` comprueba además que la app esté incluida en el plan del hub (402): la llave de API, la página pública, las automatizaciones, la cola de avisos y las tareas programadas no lo comprueban.
3. Prepara los datos que pone él y que nadie puede mandar: negocio (`:hub_id`), quién pide, hora, un identificador nuevo (`:new_id`), la identidad fiscal del negocio, la zona horaria, el idioma de quien pide, si el negocio tiene certificado o vía de envío (`:has_certificate`), si es una demo (`:is_demo_hub`), si la app tiene concedidos sus permisos de host (`:capabilities_granted`) y quién aprobó (`:approved_by`). El país y la región del negocio solo llegan al manejador WASM (`context.country_code`, `context.region_code`), no al SQL ni al motor nativo.
4. Pasa la orden por sus puertas, siempre en este orden (el de `architecture/hub/runtime-dispatcher.md` §2.0, sin olvidar que ese documento aún no recoge las reglas del dueño ni el cambio parcial): orden interna llamada desde fuera (HUB-F08) · bloqueo que pone otra app (HUB-F13) · permiso, o aprobación del responsable (HUB-F05) · completar una edición parcial (HUB-F07) · esquema y valores por defecto (HUB-F04) · reglas del dueño · candados fiscales.
5. Ejecuta el SQL de la orden, o el manejador del módulo (HUB-F10, HUB-F12), y apunta en la cola de avisos, en la misma transacción, una fila por cada aviso que la orden emite: o quedan los cambios y esas filas, o no queda nada. Lo que hacen después las apps que escuchan corre más tarde, cada una en su propia transacción.
6. Si la orden declara la comprobación de filas afectadas y no se cumple, deshace todo (HUB-F06).
7. Tras guardar, avisa en vivo a las pantallas conectadas y contesta `ok`. En el camino SQL la respuesta trae siempre un identificador nuevo (`new_ids`), aunque la orden no haya creado nada; con manejador, solo los identificadores que sus operaciones usaron.
Entra: el nombre de la orden y su contenido (`POST /api/command` desde el hub; `POST /api/v1/{módulo}/c/{orden}` con llave si el módulo la marca `expose_api`); la aprobación del responsable, si la hay, en la cabecera `X-Elevation-Token`, nunca dentro del contenido.
Sale: lo que la orden escribe en las tablas del módulo; una fila por aviso emitido en la cola de avisos, en la misma transacción (los entrega después la cola a las apps que escuchan, cada una en su propia transacción; si una falla, la orden sigue hecha y el aviso acaba en avisos caídos); el aviso en vivo, solo si se guardó; la marca de quién aprobó (`approved_by`) junto a quién pidió. Las órdenes públicas que cuentan como actividad del negocio se anotan en el registro de actividad. Repetir una orden la ejecuta otra vez: lo único que no se repite es un aviso declarado con clave de duplicado y la entrega a cada app que escucha. **Sello del primer registro en producción**: solo lo pone una orden SQL que declara en su `emit` el aviso que abre la cadena fiscal; una orden con manejador no sella nunca, y la factura normal (`invoice.created`) la devuelve un manejador, así que hoy una venta no sella (defecto, leído en el código sin ejecutar).
Si falla: cada puerta contesta con su código estable (HUB-F14) y nada queda escrito. Una cascada de avisos de más de 16 niveles se corta (`event_loop`). Un fallo de base de datos sale como «the request could not be completed — the hub recorded the details» y el detalle queda en el registro del servidor.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, avisos: la cola que entrega los avisos de una orden a las apps que escuchan, sus reintentos y los avisos caídos
Pendiente de enlazar: hub — HUB, automatizaciones: el paso de una automatización que ejecuta una orden con su propio permiso concedido
Pendiente de enlazar: hub — HUB, acceso: las reglas que escribe el dueño (políticas) y que se comprueban después del esquema
Pendiente de enlazar: hub — HUB, perfil fiscal: los candados fiscales (identidad, certificado, vía hasta la AEAT, periodo cerrado, demo en pruebas)
Pendiente de enlazar: hub — HUB, perfil fiscal (HUB-F308): volver a pruebas mientras no se haya sellado el primer registro en producción
Pendiente de enlazar: hub — HUB, negocio y datos: el registro de actividad del negocio
QA: qa-hub §11, BD-09

### HUB-F04 Comprobar el contenido de una orden contra su esquema y rellenar lo que falta
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de tocar la base de datos o el manejador del módulo, el hub compara el contenido de la orden con el esquema que el módulo declara para ella (compilado una sola vez, al instalar).
2. Si algo no cumple (falta un campo obligatorio, un tipo no es el esperado, sobra un campo que el esquema prohíbe), rechaza la orden entera: la comprobación propia del manejador no llega a ejecutarse.
3. Si cumple, rellena con su `default` cada campo **de primer nivel** que no ha llegado; los `default` de objetos anidados y de las líneas (listas) no se rellenan. Como el esquema se comprueba antes, un campo obligatorio no se salva con su `default`: si no llega, la orden se rechaza.
4. Un campo que llega, aunque sea `null`, no se toca: un `null` explícito llega como `null`.
5. Ajusta cada número de primer nivel a la forma que el esquema declara (entero o decimal), venga como venga.
6. Ese contenido completado es el que reciben el SQL, el manejador y las reglas del dueño. Las operaciones que propone después un manejador no pasan por el esquema de su sub-orden (HUB-F10).
Entra: el contenido de la orden y el esquema del módulo (`schemas/*.json`).
Sale: el contenido completado. Un `COALESCE` posterior del módulo nunca ve vacío un campo de primer nivel con `default` que no llegó (el ajuste que venía detrás no se aplica); sí actúa sobre un `null` explícito y sobre los campos anidados.
Si falla: `invalid_payload` (422), con como mucho cinco violaciones en la frase. `fields` nombra solo los campos presentes con un valor inválido (un campo anidado nombra su campo raíz); un campo obligatorio que falta o uno que sobra se dice en la frase pero no sale en `fields`, así que la pestaña de Ajustes no marca ese control. Una orden sin esquema acepta cualquier contenido. Las consultas se comprueban igual, pero sin rellenar valores por defecto.
Implicados: ninguno
QA: ninguno

### HUB-F05 Pedir la aprobación de un responsable cuando falta el permiso
Estado: hecho
Actor: empleado, responsable
Pantalla: HUB_SHELL: Aprobación de un responsable
Pasos:
1. Un empleado pide una orden cuyo permiso no tiene; si ese permiso lo tiene el perfil responsable en la app dueña (y la app está activa), el hub no la rechaza sin más: contesta `requires_elevation` con el permiso que falta.
2. La pantalla pide el PIN de un responsable, que el hub comprueba, y devuelve un pase de un solo uso para esa acción.
3. La pantalla repite la orden con el pase.
4. El hub gasta el pase en la misma puerta del permiso, solo si coincide con el mismo hub, el mismo empleado, la misma orden, el mismo contenido y el mismo permiso; anota quién aprobó antes de ejecutar y la orden sigue con el empleado como autor y el responsable como aprobador.
Entra: el pase en la cabecera `X-Elevation-Token`; la tabla de permisos por perfil de cada app instalada.
Sale: la orden ejecutada con `approved_by` y el recibo de la aprobación (`_elevation_audit`), escrito antes de ejecutar y fuera de la transacción de la orden. El pase vale para esa acción y no para la siguiente, durante 120 s como mucho. El pase vive en la memoria del proceso: si la repetición la atiende otra copia del hub (durante un despliegue conviven dos) o el hub se ha reiniciado, contesta otra vez `requires_elevation` y hay que volver a teclear el PIN.
Si falla: un pase de otra acción, de otro empleado, de otro hub, caducado o ya usado vale lo mismo que ninguno: otra vez `requires_elevation` (un pase de otra acción no se gasta). La huella del contenido se calcula sobre lo que llega, antes del cambio parcial y de los valores por defecto. El pase abre la puerta de la orden, no amplía el permiso del empleado: si una operación del manejador declara el permiso que se aprobó, sale `permission_denied` con el pase ya gastado y el recibo escrito. Las consultas, la llave de API y las automatizaciones nunca piden PIN: un permiso que falta es un rechazo. Dentro del manejador, una operación que pida más permiso que la orden se rechaza sin ofrecer PIN. El pase se gasta al pasar la puerta: si la orden falla después (esquema, regla del dueño, candado fiscal), hay que volver a pedir el PIN (leído en el código, sin ejecutar).
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso: comprobar el PIN del responsable y emitir el pase de un solo uso (`/api/elevation/approve`)
Pendiente de enlazar: hub — HUB_SHELL, diálogo que pide el PIN del responsable y repite la orden
Pendiente de enlazar: sales — SALES-F14 (descuento por encima del tope con el PIN del responsable)
QA: ninguno

### HUB-F06 Comprobar que la orden cambió algo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo puede declarar en una orden cuántas filas tiene que cambiar como mínimo (`expect_rows`, con su código de error, y opcionalmente cuál de sus sentencias es la que cuenta).
2. El hub ejecuta la orden dentro de su transacción y cuenta las filas cambiadas: las de la sentencia señalada o, si no señala ninguna, la suma de todas las de la orden (nunca las de la cola de avisos).
3. Si no llega al mínimo, deshace la transacción entera, sin cambios y sin avisos, y contesta con el código que el módulo declaró.
4. En una orden con manejador, cuenta el mínimo de la sub-orden de cada operación que propone, cada una con el suyo; el `expect_rows` de la propia orden con manejador se ignora (y el instalador lo acepta). Una sub-orden sin comprobación que no cambia nada contesta `ok`.
Entra: la declaración de la orden en `module.json`.
Sale: nada si no se cumple; la orden normal si se cumple. Una orden SQL sin comprobación sobre una fila que no existe contesta `ok` con un identificador nuevo que no nombra nada, y se enteran igual las apps que escuchan (por la cola de avisos, después), las pantallas conectadas (aviso en vivo) y, si cuenta como actividad, el registro de actividad.
Si falla: con `expect_rows`, el código del módulo (409), que su traducción convierte en frase. Con la forma antigua (`min_affected_rows`), `not_found` o `conflict` (409). **Una orden que no declara la comprobación contesta `ok` y emite sus avisos aunque no haya cambiado ninguna fila**: el hub no puede saber qué significa «nada» para cada orden, así que declararla es responsabilidad del módulo. El instalador rechaza un módulo que combine las dos formas o que use la antigua sobre varias sentencias.
Implicados: ninguno
QA: ninguno

### HUB-F07 Cambiar solo algunos campos de una ficha
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Si el módulo declara que su orden de editar una ficha admite cambios parciales (`records.<ficha>.patch`), quien llama puede mandar solo los campos que cambian y el identificador.
2. Antes de comprobar el esquema, el hub lee la ficha con la consulta que el módulo indica, se queda con los campos que la orden de editar acepta y pone encima lo que llegó.
3. Un campo enviado vacío (`null`) borra el valor; un campo no enviado se conserva.
4. El contenido completo sigue por la comprobación de esquema y el SQL de siempre.
Entra: el identificador y los campos que cambian.
Sale: la ficha actualizada sin perder lo que no se mandó.
Si falla: si la lectura falla o la ficha no existe, el contenido sigue tal cual llegó y el esquema dice lo que falta: no se inventa nada ni se escribe nada.
Implicados: ninguno
QA: ninguno

### HUB-F08 Rechazar desde fuera las órdenes internas de un módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo marca una orden como interna (su último tramo empieza por `_`, o declara `internal`): es la mitad que solo debe ejecutar el propio hub cuando la pide la orden pública.
2. Si la pide una pantalla, el asistente, una integración o una automatización, el hub la rechaza antes de mirar permisos o contenido.
3. Solo el propio hub (la cola de avisos y las tareas programadas) la ejecuta.
Entra: el nombre de la orden.
Sale: nada.
Si falla: `internal_command` (403): la orden existe, pero esa puerta no es la suya. El catálogo de órdenes del hub no las anuncia (HUB-F15).
Implicados: ninguno
QA: ninguno

### HUB-F09 Avisar de un duplicado con el código del módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo declara en una orden qué índice único de sus tablas protege y con qué código quiere que se cuente el choque (`on_unique`).
2. Si al guardar la base de datos rechaza la fila por ese índice, el hub contesta con ese código en vez del error genérico.
3. Vale igual si el choque viene del SQL de la orden, de una operación del manejador o del motor propio del módulo, siempre que el índice lo nombre la orden pedida: el `on_unique` de una sub-orden que solo alcanza un manejador no se aplica.
Entra: la declaración `on_unique` de la orden.
Sale: nada guardado; el código del módulo.
Si falla: un índice que la orden no nombra, o una tabla de otro módulo o del hub, deja el error de base de datos genérico (redactado, HUB-F14): un módulo no puede rebautizar el rechazo de un índice ajeno. El instalador exige que el código sea del espacio del módulo y, si el módulo declara catálogo de errores, que esté en él.
Implicados: ninguno
QA: ninguno

### HUB-F10 Ejecutar el manejador de un módulo y validar lo que propone
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Si la orden tiene manejador, el hub le entrega el contenido ya comprobado, sus datos de sistema, la hora única de la orden, 256 identificadores nuevos y las lecturas previas (HUB-F11).
2. El manejador corre aislado, sin acceso a la base de datos ni a la red, con topes de memoria (32 MB), de instrucciones y de tiempo (5 s); el hub lo compila una vez por versión instalada.
3. El manejador contesta con operaciones (órdenes SQL de su propio módulo), avisos, un rechazo de negocio o una respuesta.
4. El hub valida cada operación: que sea SQL, de su mismo módulo, que su sub-orden tenga SQL declarativo y que no pida más permiso del que tiene quien llama. **No** la compara con el esquema de su sub-orden ni le pone sus valores por defecto: solo ajusta sus números a la forma declarada. El `emit` de la sub-orden no se emite: solo los avisos de la orden pedida y los que devuelve el manejador.
5. Valida cada aviso que devuelve el manejador: un recordatorio exige el permiso de avisar declarado y concedido, y una impresión el de imprimir declarado; un aviso con el espacio de nombres de otra app instalada se rechaza; si el módulo declara su lista de avisos (`events.emits`), cualquiera fuera de ella se rechaza; si no la declara, un aviso no declarado de su espacio, o de nadie, pasa con una nota en el registro. Luego aplica los candados fiscales a lo que resultó.
6. Guarda todas las operaciones y avisos en una sola transacción, cada operación con la comprobación de filas de su sub-orden (HUB-F06; la de la orden pedida no cuenta), y contesta con los identificadores que de verdad se usaron y, si la hay, la respuesta del manejador.
Entra: el código del manejador del paquete instalado; topes ajustables por despliegue (`HUB_WASM_MEMORY_MAX_MB`, `HUB_WASM_FUEL`, `HUB_WASM_TIMEOUT_MS`).
Sale: lo mismo que HUB-F03. Un aviso que la orden declara y el manejador también emite sale una sola vez, con el contenido del manejador.
Si falla: un rechazo de negocio sale con el código del módulo (409), si es de su espacio y está en su catálogo; si no, es un fallo del módulo. Pasarse de instrucciones da `wasm_budget_exceeded` y del tiempo `wasm_timeout`: nada cambia y la pantalla dice «Esta acción es demasiado grande para hacerla de una vez. No se ha cambiado nada: prueba con menos elementos o un rango más corto.» o «Esta acción ha tardado demasiado en terminar. No se ha cambiado nada: prueba con menos elementos o un rango más corto.». Si se agota el margen del hub (el tiempo del manejador más 2 s), sale un fallo genérico redactado, no `wasm_timeout`. Una respuesta de más de 64 KiB, una operación de otro módulo o un aviso rechazado (paso 5) tumban la orden entera sin escribir nada. El código WASM se compila una vez por versión instalada y se precalienta al arrancar.
Implicados: ninguno
QA: ninguno

### HUB-F11 Darle al manejador los datos de otros módulos antes de ejecutar
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una orden declara qué consultas necesita leídas antes (`reads`), con datos sacados de su propio contenido: las reglas de IVA para cobrar, el precio de un artículo.
2. El hub las ejecuta como sistema (mismo negocio, sin volver a mirar el permiso de quien pide) y se las entrega al manejador.
3. Una lectura marcada obligatoria solo se sirve si su módulo está entre las dependencias declaradas; una opcional se sirve aunque no lo esté.
4. Si una lectura opcional falla, se omite y el manejador decide qué hacer sin ella; si falla una obligatoria, la orden no se ejecuta.
Entra: las consultas declaradas y el contenido de la orden.
Sale: las filas de cada lectura dentro del contexto del manejador.
Si falla: una lectura obligatoria que no se resuelve aborta con `read_unavailable` y el motivo (app no instalada, apagada o consulta fallida); la pantalla dice, según el motivo, «Falta la app «…» y esta acción la necesita. Pide a un administrador que la instale desde Apps.», «La app «…» está desactivada y esta acción la necesita. Pide a un administrador que vuelva a activarla desde Apps.» o «No se pudo leer un dato que esta acción necesita, así que no se ha hecho nada. Inténtalo de nuevo y avisa a un administrador si sigue pasando.». Una lectura obligatoria fuera de las dependencias declaradas se omite con un aviso en el registro.
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F01 (cobrar: el IVA se resuelve contra las reglas que el hub precarga de Impuestos)
Pendiente de enlazar: taxes — TAXES-F19 (las reglas de IVA que lee la venta)
QA: ninguno

### HUB-F12 Ejecutar el motor propio de un módulo de confianza
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Algunas órdenes de un módulo de primera parte (hoy solo VeriFactu) las resuelve un motor compilado dentro del hub, que sí puede usar la red, el certificado, llamar a la nube de ERPlora y escribir ficheros en la carpeta propia del módulo.
2. Antes de ejecutarlo, el hub exige que todos los permisos de host que el módulo pide (red, certificado…) estén concedidos en Ajustes › Permisos; si falta uno, no corre.
3. El motor lee la base de datos solo con `SELECT` que hace el hub por él (cualquier tabla), no recibe lecturas previas ni el país del negocio, y para escribir en la base propone operaciones y avisos como un manejador.
4. El hub valida y guarda lo propuesto igual que en HUB-F10.
Entra: el motor registrado al arrancar; los permisos concedidos.
Sale: lo mismo que HUB-F10.
Si falla: `capability_denied` (403) con la app y el permiso que falta, y ningún dato tocado; un motor no registrado en este hub es un fallo del hub (redactado).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_VERIFACTU: el motor fiscal que se ejecuta por esta puerta
QA: qa-hub §7

### HUB-F13 Bloquear las órdenes de un módulo mientras otro no cumpla su condición
Estado: parcial — el rechazo no tiene frase propia: la pantalla, el asistente y la API reciben `protects_guard` con una frase en inglés del hub; y si la lectura de la condición falla, el bloqueo cede
Actor: sistema
Pantalla: HUB_SHELL: Vista de un módulo
Pasos:
1. Una app declara que protege la ruta de otra (`protects`): Caja protege la de Venta mientras «Activar caja» está guardado y no hay sesión abierta.
2. Ante cualquier orden de la app protegida, venga de donde venga (pantalla, asistente, automatización, API), el hub lee como sistema los ajustes de la app que protege: si el bloqueo está armado y su ruta apunta a la app de la orden, comprueba la condición.
3. Si la condición no se cumple, rechaza la orden antes de mirar permisos o contenido.
4. La pantalla, por su lado, no monta la app protegida y pinta en su lugar la de la app que protege, hasta que llega su aviso de reanudar.
Entra: la consulta de ajustes, la columna que arma el bloqueo, la columna con la ruta protegida (`/m/<módulo>`) y la consulta de la condición, todas declaradas por la app que protege.
Sale: nada; la orden rechazada.
Si falla: `protects_guard` (409). Las órdenes que el hub se hace a sí mismo (la cola de avisos, las tareas programadas) no se bloquean. Si la app que protege está apagada, sus ajustes no existen o una lectura falla, el bloqueo no actúa y la orden pasa (antes vender que parar la caja por una lectura rota).
Implicados: pendiente
Pendiente de enlazar: cash_register — CASH_REGISTER-F04 (vender solo con la caja abierta)
Pendiente de enlazar: sales — SALES-F08 (cobrar sin la caja abierta)
Pendiente de enlazar: hub — HUB_SHELL, vista de un módulo: pintar la pantalla de la app que protege en lugar de la protegida y volver al llegar su aviso
QA: R-01, B-01, BD-04

### HUB-F14 Contestar un fallo con un código estable y sin detalles internos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Los rechazos de una consulta o una orden salen con la forma `{ok: false, error: {code, message}}` y el estado HTTP de su familia. Excepción: el 401 de `/api/query`, `/api/command`, la llave de API y la emisión de localizadores sale como `{ok: false, error: "<texto>"}`, sin código.
2. El código es estable y es lo que traducen las pantallas; los datos que la pantalla necesita viajan aparte (el permiso que falta, las apps que dependen, los campos rechazados, lo que falta para facturar, la consulta y el dato que no llegó, la app afectada).
3. El texto solo llega a quien llama si lo escribió el hub o el módulo a propósito y no lleva palabras del motor de base de datos ni direcciones internas; si no, sale una frase fija y el detalle queda en el registro del servidor.
4. Un fallo de instalación o de actualización nunca sale como error 5xx, para que el proxy de delante no se coma el código. Las órdenes sí pueden: una orden sin SQL ni manejador da `not_implemented` (501) y un hub sin conexiones libres, `pool_limit` (503).
Entra: el error de cualquier puerta.
Sale: la respuesta al que llama y, para los fallos del sistema, una entrada en el registro de errores atribuida al módulo cuando se sabe cuál es.
Si falla: un cuerpo que no se puede leer contesta `invalid_body` con el estado del lector (400 si no es JSON, 415 sin `Content-Type: application/json`, 422 si falta un campo), no la frase en inglés del servidor web. El rechazo de bloqueo (`protects_guard`) lleva en su frase el nombre de la consulta interna y un texto propio de la caja, y no lleva como campo qué app bloquea a cuál.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, traducción de los códigos del hub a frases en la pantalla (catálogo del SDK y `runtimeErrors`)
QA: ninguno

### HUB-F15 Consultar qué órdenes y consultas acepta el hub
Estado: hecho
Actor: administrador
Pantalla: ninguna
Pasos:
1. Un administrador (o una herramienta con su sesión) pide el catálogo de operaciones, entero o de un módulo.
2. El hub contesta, ordenado por nombre, cada consulta y orden que su despachador acepta hoy: nombre exacto, permiso que pide, forma del contenido y si está publicada para la API con llave.
3. No anuncia las órdenes internas ni las de apps apagadas; sí anuncia las de apps que el plan del hub ya no incluye (que `/api/command` rechazaría con 402) y las consultas propias del hub (`hub.*`).
Entra: `GET /api/hub/operations[?module=]`.
Sale: el catálogo; no guarda nada.
Si falla: sin sesión, 401; con sesión que no es de administrador, 403. Si quien llama se identifica como un módulo (la cabecera es voluntaria), ese módulo necesita además el permiso de host «administrar automatizaciones» concedido.
Implicados: ninguno
QA: qa-hub §11

### HUB-F16 Emitir el localizador para que el cliente pida su factura
Estado: parcial — solo se comprueba el permiso de la orden: se puede emitir un localizador para una orden interna, y la fecha límite que manda la app no se valida (se compara como texto)
Actor: empleado, sistema
Pantalla: ninguna
Pasos:
1. Al imprimir un tique, la app que lo imprime pide al hub un localizador para él: qué orden ejecutará el canje, con qué contenido sellado (líneas e importes del tique), qué campos podrá rellenar el cliente y, si quiere, las opciones de algunos campos (país, tipo de documento) y la fecha límite.
2. El hub comprueba que quien lo pide tiene el permiso que declara esa orden; no mira si es interna, ni el bloqueo de otra app, ni el plan, y no ofrece PIN.
3. Calcula un localizador de 16 caracteres a partir del tique con una clave propia del negocio, y guarda la huella del localizador (SHA-256; el localizador en sí no se guarda), la orden, el contenido sellado en claro, los campos y la fecha límite (45 días si nadie fija otra).
4. Devuelve el localizador y su dirección (`/p/<localizador>`), que la app imprime como segundo código QR.
Entra: `POST /api/hub/public-claims` con sesión; la clave del negocio (`_public_claim_key`), creada la primera vez.
Sale: la fila del localizador (`_public_claim`). Reimprimir el mismo tique devuelve el mismo localizador, sin mover la fecha límite ni reabrir uno ya canjeado; si la reimpresión llega con otro contenido sellado, se ignora en silencio.
Si falla: orden desconocida o de una app apagada (también una orden vacía), `unknown_command` (400); sin su permiso, `permission_denied` (403); opciones mal formadas o de más de 400 entradas, `invalid_choices` (400); sin tipo o sin tique, `public_claim.incomplete` (409). Sin sesión, 401 sin código.
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F29 (el tique impreso lleva el QR «Pide tu factura» con el localizador)
QA: L-02

### HUB-F17 Canjear un localizador en la página pública
Estado: parcial — nunca enseña la referencia de la factura (busca claves que la respuesta de una orden no trae); un segundo envío ve «emitida» sin referencia, aunque el primero acabe fallando; un fallo del propio hub le dice al cliente que revise el NIF y le cuenta como intento fallido; un dato rechazado puede salir con la frase del módulo o del esquema en inglés; los tres campos fijos se piden siempre, los declare o no el localizador
Actor: cliente
Pantalla: Página pública para pedir la factura
Pasos:
1. El cliente escanea el segundo QR del tique o escribe la dirección `/p/<código>` en el navegador (no hay campo para teclear el código: la página lo enseña como «Código del tique»); no inicia sesión.
2. Ve «Pide tu factura», «Convierte el tique que te han dado en una factura completa con tus datos fiscales.» y el formulario: «NIF/CIF», «Nombre o razón social», «Domicilio» y, si el tique los ofrece, desplegables como el país o el tipo de documento.
3. Pulsa «Emitir mi factura».
4. El hub marca el localizador como usado antes de ejecutar nada, junta lo sellado con solo los campos que el cliente puede rellenar (lo sellado gana siempre) y ejecuta la orden con un autor propio del localizador (`public-claim:<id>`) que solo tiene el permiso que la orden declara hoy; quién emitió el localizador no cuenta.
5. Ve «Tu factura está emitida» y «Guarda esta referencia. Si necesitas una copia, enséñala en el mostrador.». La línea con la referencia no sale: el hub busca `number`, `invoice_number`, `id` o `invoice_id` en la respuesta, y una orden contesta `{ok, new_ids}` o `{ok, operations, new_ids, result}`.
Entra: el localizador; los datos fiscales del cliente; el idioma de la página (el del negocio, o `?lang=es|en`).
Sale: lo que produce la orden del localizador (hoy, la factura completa que sustituye al tique) y el localizador marcado como usado; la referencia que se guarda queda vacía. Volver a abrirlo enseña «emitida» sin referencia.
Si falla: un código desconocido o de otro negocio: «Este código no corresponde a ningún tique de este negocio. Comprueba que lo has escrito tal como está impreso.» (404). Pasada la fecha: «El plazo para pedir factura de este tique terminó el {fecha}. Pregunta en el mostrador.» (410), con la fecha como `AAAA-MM-DD` en UTC. Si la orden se rechaza, el localizador se libera y se vuelve al formulario con lo escrito y el motivo: la frase del módulo o del esquema si el rechazo es de negocio o de datos; si es del propio hub (falta la identidad fiscal, una lectura obligatoria, el bloqueo de otra app, una orden interna), «No se han podido aceptar los datos. Revisa el NIF y vuelve a intentarlo.», y cuenta como intento fallido. Si la orden ya no existe en el hub: «Este negocio no puede emitir facturas ahora mismo. Pregunta en el mostrador.». Demasiados fallos desde la misma dirección: «Demasiados intentos. Vuelve a probar en {segundos} segundos.» (429). Dos envíos a la vez: nunca dos facturas; el segundo ve «Tu factura está emitida» en cuanto el primero ha marcado el localizador, aunque el primero falle después y lo libere. La página pública no comprueba el plan del hub.
Implicados: pendiente
Pendiente de enlazar: invoice — INVOICE-F04 (el cliente pide la factura completa de su tique)
Pendiente de enlazar: architecture — REC_FISCAL-F10 (pasar un tique a factura completa sustitutiva)
QA: L-02, BD-09

### HUB-F18 Redondear el dinero igual en todos los módulos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Los manejadores de los módulos que calculan dinero enlazan la misma aritmética del hub (`guest-sdk`); comprobado su uso en Venta, Impuestos y Facturación (también lo enlazan Cocina, Servicios, Precios, `cart_checkout`, Inventario y Caja, sin comprobar para qué).
2. Todo importe es un entero de la unidad mínima de la moneda (céntimos en euros). Las operaciones de dinero de `guest-sdk` multiplican en decimal exacto, pero las tasas viajan como número de coma flotante (`TaxComponent.rate_pct`) y Venta suma tasas en coma flotante antes de pasarlas a decimal.
3. El dinero pierde precisión en un solo sitio: el redondeo a la unidad mínima, con la mitad exacta alejándose de cero (la regla de la ley del euro).
4. Una línea se calcula `precio × cantidad × (1 − descuento %)` con un solo redondeo al final; con IVA incluido, la base sale de dividir y la cuota es lo que resta, así que lo cobrado no se mueve un céntimo; el desglose por tipo redondea la cuota una vez por tipo.
Entra: importes, tasas y cantidades de cada manejador. El hub no le inyecta la moneda ni sus decimales: cada módulo trabaja en unidades mínimas sin saber cuáles son.
Sale: los importes que cada módulo guarda y declara.
Si falla: un decimal que llegue donde se espera un importe se redondea, nunca se trunca. Cambiar el redondeo en el hub no llega a un módulo hasta que ese módulo se vuelve a compilar y publicar (lo enlaza al compilarse); el motor de VeriFactu formatea sus importes por su cuenta (HUB_VERIFACTU).
Implicados: pendiente
Pendiente de enlazar: taxes — TAXES-F18 (calcular el impuesto de un importe con el redondeo común)
Pendiente de enlazar: sales — SALES-F01 (el tique se cierra por tipo con el mismo redondeo)
Pendiente de enlazar: invoice — INVOICE-F01 (la cuota de cada tipo cuadra al céntimo)
QA: L-08

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Aprobación del responsable con PIN para una acción | hecho | HUB-F05 |
| Validar lo que llega antes de ejecutar | hecho | HUB-F04 |
| Errores traducibles sin filtrar detalles internos | hecho | HUB-F14 |
| Factura completa pedida por el cliente desde el tique | parcial: sin referencia de la factura, errores del hub contados como «revisa el NIF», frases en inglés, localizadores para órdenes internas | HUB-F16, HUB-F17 |
| Un solo redondeo del dinero en todo el producto | hecho en los módulos con manejador (las tasas viajan en coma flotante); el motor de VeriFactu va aparte | HUB-F18 |
| Una orden repetida no se ejecuta dos veces | no hecho en el hub: solo los avisos con clave de duplicado y la entrega a cada app que escucha; lo resuelve cada módulo | HUB-F03 |

## Datos: de quién es cada dato

Para todo el área de módulos (lo común a todo el servidor, como lo que el hub pone en cada orden,
está en el índice):

- **De cada app**: sus tablas (con el prefijo de la app), sus ajustes y sus datos de partida. El hub
  las crea y migra, pero no las lee salvo por las consultas de la propia app (lecturas previas,
  bloqueos, ajustes, pasos de puesta en marcha, paneles). Desinstalar no las borra.
- **De esta parte del área**: los localizadores de la página pública (`_public_claim`: la huella
  SHA-256 del localizador, nunca el localizador, y el contenido sellado en claro) y su clave
  (`_public_claim_key`, un secreto guardado en claro en una tabla sin puerta HTTP); y los recibos de
  las aprobaciones del responsable que produce HUB-F05 (`_elevation_audit`, tabla del área de acceso).
  Las tablas del ciclo de vida de las apps están en [modulos-aplicaciones.md](modulos-aplicaciones.md).
- **Datos personales**, recorridas las migraciones de sistema:
  - `_public_claim`: quién emitió el localizador (`created_by`), el contenido sellado que decide la
    app que lo emite (hoy, líneas del tique; si incluye datos del cliente, sin confirmar) y la
    referencia del resultado (hoy siempre vacía, HUB-F17). Los datos fiscales que escribe el cliente
    **no** se guardan en el localizador: van a la orden (y de ahí a la factura de Facturación). No lo
    purga la retención ni lo vacía el borrado de una persona (HUB-F249).
  - `_elevation_audit`: quién pidió (`created_by`), quién aprobó (`approved_by`), la orden, el
    permiso, la huella del contenido y, si se aprobó con tarjeta, su tipo y referencia
    (`credential_kind`, `credential_ref`).
  - `_public_claim_key`: sin datos personales, pero es un secreto.
  - Los avisos de una orden llevan quién la pidió y quién la aprobó, y la identidad fiscal del
    negocio (que para un autónomo es su nombre y su NIF).
  - El registro de errores guarda las **claves** del contenido de una orden fallida, nunca sus
    valores.

## Reglas que no se rompen

Las del embudo de una orden (cada fila de un negocio, una app solo escribe en sus tablas, primero se
comprueba, una orden es una transacción, el permiso en el servidor, el orden de las puertas, el plan,
las órdenes internas, el dinero, nada fiscal se simula, errores sin detalles internos) valen para todo
el servidor y están en el índice. Las propias de esta parte:

- **El cliente de la página pública solo rellena los campos que el localizador permite**; lo sellado
  en el mostrador gana siempre, y un localizador produce como mucho un documento.

## Lo que NO hace, a propósito

- No pide PIN para leer: un informe no se desbloquea con el código del responsable.
- No deja que un manejador WASM toque la base de datos, la red ni otra app: propone, y el hub valida.
  El motor nativo de confianza (hoy VeriFactu) sí lee cualquier tabla con `SELECT`, usa la red y el
  certificado, llama a la nube y escribe ficheros en su carpeta, con sus permisos de host concedidos
  (HUB-F12); para escribir en la base también propone.
- No ejecuta código en la página pública salvo un único fichero propio que pone nombre a los países.

## Dudas abiertas

1. Cuando una orden aprobada con PIN falla después de la puerta, ¿se debe devolver la aprobación?
   (HUB-F05)
2. ¿Qué frase ve la cajera cuando una orden de Venta se rechaza porque la caja está cerrada? Hoy el
   código `protects_guard` no tiene traducción (HUB-F13, CASH_REGISTER-F04).

## Fuentes contrastadas

- `crates/runtime/src/wasm.rs` dice que ejecutar un manejador WASM «aún no está soportado»: es un
  resto; los manejadores corren por `wasm_cache` y `erplora-wasm-host` (HUB-F10).
- TAXES-F18 dice que el motor de VeriFactu usa el mismo redondeo común; el motor no enlaza
  `guest-sdk` y formatea sus importes por su cuenta (`chain.rs`, `format_amount`) — a contrastar en
  `HUB_VERIFACTU`.
- `guest-sdk/src/money.rs` llama «HALF_UP» al modo de redondeo; lo que aplica es la mitad
  alejándose de cero, que coincide con «hacia arriba» en importes positivos y redondea −0,5 a −1 en
  devoluciones (HUB-F18).
- INVOICE-F04 y REC_FISCAL-F10 deben apuntar su «Pendiente de enlazar hub» a HUB-F17; INVOICE-F04,
  además, que la frase del descuadre (`invoice.tax_quota_mismatch`) sale en inglés y en céntimos.
- `architecture/hub/runtime-dispatcher.md` §2.0 no tiene la puerta de reglas del dueño ni el cambio
  parcial, y sus números de línea ya no casan (HUB-F03).
- `crates/runtime/src/public_claim.rs:34` dice migración v51; es la v52 (HUB-F16).
