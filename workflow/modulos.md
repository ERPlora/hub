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

## Flujos

### HUB-F01 Leer datos de un módulo
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla de un módulo, el asistente, una automatización o una integración pide una consulta por su nombre (`modulo.entidad.accion`) con sus datos de búsqueda.
2. El hub comprueba la sesión (o la llave de API), que la app dueña de la consulta esté instalada, activa e incluida en el plan del hub, y que quien pregunta tenga el permiso que la consulta declara. Una consulta nunca pide el PIN de un responsable: sin permiso se rechaza y ya está.
3. Comprueba los datos contra el esquema de la consulta, rechaza cualquier dato que la consulta no conozca y cualquier dato que su SQL necesite y no haya llegado.
4. Añade por su cuenta el negocio (hub), quién pregunta, la hora, la identidad fiscal del negocio, su zona horaria, el idioma de quien pregunta y si el negocio es una demo; nadie puede mandar esos valores desde fuera.
5. Devuelve las filas. Si la consulta es de lista, devuelve la página con el total (HUB-F02).
Entra: el nombre de la consulta y sus datos (`POST /api/query`, o `POST /api/v1/{módulo}/q/{consulta}` con llave si el módulo la marca `expose_api`); la sesión de quien pregunta; los ajustes del negocio (`hub_settings`).
Sale: nada guardado. Una consulta de un módulo no instalado o apagado contesta `module_not_installed` / `module_inactive` (404), que el SDK de los módulos convierte en «no hay» cuando la pide como opcional; la de un módulo fuera del plan, `module_entitlement_blocked` (402).
Si falla: sin sesión, 401. Sin permiso, `permission_denied` (403). Un dato que no cumple el esquema, `invalid_payload` (422) con los campos señalados. Un dato que la consulta no conoce, `unknown_filter` (422) con la lista de los aceptados; uno que falta, `missing_required_param` (422): antes contestaban «no hay nada» y se confundían con una ficha inexistente (hub#1173, hub#1913, hub#2383). Una consulta inexistente en una app activa es `not_found` (contrato roto). El error se anota en el registro de errores con las claves del payload, nunca sus valores.
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
Si falla: un extremo de rango que la columna no sabe leer, `invalid_filter_bound` (422); un dato de contexto obligatorio que falta, `missing_required_param` (422). Si el hub no puede averiguar el tipo de las columnas, ordena sin desempate y compara los rangos tal como llegaron, y lo deja escrito en el registro.
Implicados: ninguno
QA: qa-hub §11

### HUB-F03 Ejecutar una orden de un módulo
Estado: hecho
Actor: empleado, responsable, administrador, asistente, sistema
Pantalla: ninguna
Pasos:
1. Una pantalla, el asistente, una automatización, otra aplicación (por un aviso o una tarea programada) o una integración pide una orden por su nombre con su contenido.
2. El hub comprueba la sesión y que la app esté instalada, activa e incluida en el plan del hub, y prepara los datos que pone él: negocio, quién pide, hora, un identificador nuevo, la identidad fiscal, el país, la zona horaria, el idioma y si los permisos de host de la app están concedidos.
3. Pasa la orden por sus puertas, siempre en este orden: orden interna llamada desde fuera (HUB-F08) · bloqueo que pone otra app (HUB-F13) · permiso, o aprobación del responsable (HUB-F05) · completar una edición parcial (HUB-F07) · esquema y valores por defecto (HUB-F04) · reglas del dueño · candados fiscales.
4. Ejecuta el SQL de la orden, o el manejador del módulo (HUB-F10, HUB-F12), y apunta los avisos que la orden emite en la misma transacción: o queda todo, o no queda nada.
5. Si la orden declara la comprobación de filas afectadas y no se cumple, deshace todo (HUB-F06).
6. Tras guardar, avisa en vivo a las pantallas conectadas y contesta `ok` con los identificadores que ha creado.
Entra: el nombre de la orden y su contenido (`POST /api/command` desde el hub; `POST /api/v1/{módulo}/c/{orden}` con llave si el módulo la marca `expose_api`); la aprobación del responsable, si la hay, en la cabecera `X-Elevation-Token`, nunca dentro del contenido.
Sale: lo que la orden escribe en las tablas del módulo; una fila por aviso emitido en la cola de avisos, en la misma transacción (los entrega después la cola a las apps que escuchan); el aviso en vivo, solo si se guardó; la marca de quién aprobó (`approved_by`) junto a quién pidió. Si la orden abre una cadena fiscal con el hub ya en producción, el hub deja sellado el primer registro y desde entonces no se puede volver a pruebas. Las órdenes públicas que cuentan como actividad del negocio se anotan en el registro de actividad.
Si falla: cada puerta contesta con su código estable (HUB-F14) y nada queda escrito. Una cascada de avisos de más de 16 niveles se corta (`event_loop`). Un fallo de base de datos sale como «the request could not be completed — the hub recorded the details» y el detalle queda en el registro del servidor.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, avisos: la cola que entrega los avisos de una orden a las apps que escuchan, sus reintentos y los avisos caídos
Pendiente de enlazar: hub — HUB, automatizaciones: el paso de una automatización que ejecuta una orden con su propio permiso concedido
Pendiente de enlazar: hub — HUB, acceso: las reglas que escribe el dueño (políticas) y que se comprueban después del esquema
Pendiente de enlazar: hub — HUB, perfil fiscal: los candados fiscales (identidad, certificado, vía hasta la AEAT, periodo cerrado, demo en pruebas)
Pendiente de enlazar: hub — HUB, negocio y datos: el registro de actividad del negocio
QA: qa-hub §11, BD-09

### HUB-F04 Comprobar el contenido de una orden contra su esquema y rellenar lo que falta
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de tocar la base de datos o el manejador del módulo, el hub compara el contenido de la orden con el esquema que el módulo declara para ella (compilado una sola vez, al instalar).
2. Si algo no cumple (falta un campo obligatorio, un tipo no es el esperado, sobra un campo que el esquema prohíbe), rechaza la orden entera: la comprobación propia del manejador no llega a ejecutarse.
3. Si cumple, rellena con el valor por defecto del esquema cada campo que no ha llegado. Un campo que llega, aunque sea vacío (`null`), no se toca.
4. Ajusta cada número a la forma que el esquema declara (entero o decimal), venga como venga.
5. Ese contenido completado es el que reciben el SQL, el manejador y las reglas del dueño.
Entra: el contenido de la orden y el esquema del módulo (`schemas/*.json`).
Sale: el contenido completado. Por eso un `COALESCE` posterior del módulo nunca ve vacío un campo con valor por defecto: el ajuste que venía detrás no se aplica nunca.
Si falla: `invalid_payload` (422) con la lista de campos rechazados en `fields`, que la pestaña de Ajustes del hub usa para marcar cada campo. Una orden sin esquema acepta cualquier contenido. Las consultas se comprueban igual, pero sin rellenar valores por defecto.
Implicados: ninguno
QA: ninguno

### HUB-F05 Pedir la aprobación de un responsable cuando falta el permiso
Estado: hecho
Actor: empleado, responsable
Pantalla: HUB_SHELL: diálogo del PIN del responsable
Pasos:
1. Un empleado pide una orden cuyo permiso no tiene; si ese permiso lo tiene el perfil responsable en la app dueña (y la app está activa), el hub no la rechaza sin más: contesta `requires_elevation` con el permiso que falta.
2. La pantalla pide el PIN de un responsable, que el hub comprueba, y devuelve un pase de un solo uso para esa acción.
3. La pantalla repite la orden con el pase.
4. El hub gasta el pase en la misma puerta del permiso, solo si coincide con el mismo hub, el mismo empleado, la misma orden, el mismo contenido y el mismo permiso; anota quién aprobó antes de ejecutar y la orden sigue con el empleado como autor y el responsable como aprobador.
Entra: el pase en la cabecera `X-Elevation-Token`; la tabla de permisos por perfil de cada app instalada.
Sale: la orden ejecutada con `approved_by` y el recibo de la aprobación. El pase vale para esa acción y no para la siguiente.
Si falla: un pase de otra acción, de otro empleado, de otro hub, caducado o ya usado vale lo mismo que ninguno: otra vez `requires_elevation`. Las consultas, la llave de API y las automatizaciones nunca piden PIN: un permiso que falta es un rechazo. Dentro del manejador, una operación que pida más permiso que la orden se rechaza sin ofrecer PIN. El pase se gasta al pasar la puerta: si la orden falla después (esquema, regla del dueño, candado fiscal), hay que volver a pedir el PIN (leído en el código, sin ejecutar).
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
4. La misma regla vale para cada operación que propone un manejador: cada una con su propio mínimo.
Entra: la declaración de la orden en `module.json`.
Sale: nada si no se cumple; la orden normal si se cumple.
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
3. Vale igual si el choque viene del SQL de la orden, de una operación del manejador o del motor propio del módulo.
Entra: la declaración `on_unique` de la orden.
Sale: nada guardado; el código del módulo.
Si falla: un índice que la orden no nombra, o una tabla de otro módulo o del hub, deja el error de base de datos genérico (redactado, HUB-F14): un módulo no puede rebautizar el rechazo de un índice ajeno. El instalador exige que el código sea del espacio del módulo y esté en su catálogo de errores.
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
4. El hub valida cada operación (que sea SQL, de su mismo módulo y que no pida más permiso que la orden), cada aviso (declarado, de su espacio de nombres; un recordatorio exige el permiso de avisar concedido y una impresión el de imprimir declarado) y aplica los candados fiscales a lo que resultó.
5. Guarda todas las operaciones y avisos en una sola transacción, cada operación con su comprobación de filas (HUB-F06), y contesta con los identificadores que de verdad se usaron y, si la hay, la respuesta del manejador.
Entra: el código del manejador del paquete instalado; topes ajustables por despliegue (`HUB_WASM_MEMORY_MAX_MB`, `HUB_WASM_FUEL`, `HUB_WASM_TIMEOUT_MS`).
Sale: lo mismo que HUB-F03. Un aviso que la orden declara y el manejador también emite sale una sola vez, con el contenido del manejador.
Si falla: un rechazo de negocio sale con el código del módulo (409), si es de su espacio y está en su catálogo; si no, es un fallo del módulo. Pasarse de instrucciones da `wasm_budget_exceeded` y del tiempo `wasm_timeout`: nada cambia y la pantalla dice «Esta acción es demasiado grande para hacerla de una vez. No se ha cambiado nada: prueba con menos elementos o un rango más corto.» o «Esta acción ha tardado demasiado en terminar. No se ha cambiado nada: prueba con menos elementos o un rango más corto.». Una respuesta de más de 64 KiB, una operación de otro módulo o un aviso no declarado tumban la orden entera sin escribir nada.
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
1. Algunas órdenes de un módulo de primera parte (hoy solo VeriFactu) las resuelve un motor compilado dentro del hub, que sí puede usar la red y el certificado.
2. Antes de ejecutarlo, el hub exige que todos los permisos de host que el módulo pide (red, certificado…) estén concedidos en Ajustes › Permisos; si falta uno, no corre.
3. El motor lee solo con consultas de lectura que hace el hub por él y propone operaciones y avisos como un manejador.
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
Pantalla: HUB_SHELL: vista de un módulo
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
1. Cualquier rechazo de una consulta o una orden sale con la misma forma: `{ok: false, error: {code, message}}` y el estado HTTP de su familia.
2. El código es estable y es lo que traducen las pantallas; los datos que la pantalla necesita viajan aparte (el permiso que falta, las apps que dependen, los campos rechazados, lo que falta para facturar, la consulta y el dato que no llegó, la app afectada).
3. El texto solo llega a quien llama si lo escribió el hub o el módulo a propósito y no lleva palabras del motor de base de datos ni direcciones internas; si no, sale una frase fija y el detalle queda en el registro del servidor.
4. Un fallo de instalación o de actualización nunca sale como error 5xx, para que el proxy de delante no se coma el código.
Entra: el error de cualquier puerta.
Sale: la respuesta al que llama y, para los fallos del sistema, una entrada en el registro de errores atribuida al módulo cuando se sabe cuál es.
Si falla: un cuerpo que no es JSON contesta `invalid_body` con su estado (400 o 422), no la frase en inglés del servidor web.
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
3. No anuncia lo que rechazaría: ni las órdenes internas ni las de apps apagadas.
Entra: `GET /api/hub/operations[?module=]`.
Sale: el catálogo; no guarda nada.
Si falla: sin sesión, 401; con sesión que no es de administrador, 403. Si quien llama se identifica como un módulo, ese módulo necesita además el permiso de host «administrar automatizaciones» concedido.
Implicados: ninguno
QA: qa-hub §11

### HUB-F16 Emitir el localizador para que el cliente pida su factura
Estado: hecho
Actor: empleado, sistema
Pantalla: ninguna
Pasos:
1. Al imprimir un tique, la app que lo imprime pide al hub un localizador para él: qué orden ejecutará el canje, con qué contenido sellado (líneas e importes del tique), qué campos podrá rellenar el cliente y, si quiere, las opciones de algunos campos (país, tipo de documento) y la fecha límite.
2. El hub comprueba que quien lo pide podría ejecutar esa orden él mismo; si no, no lo emite.
3. Calcula un localizador de 16 caracteres a partir del tique con una clave propia del negocio, y guarda el localizador cifrado, la orden, el contenido sellado, los campos y la fecha límite (45 días si nadie fija otra).
4. Devuelve el localizador y su dirección (`/p/<localizador>`), que la app imprime como segundo código QR.
Entra: `POST /api/hub/public-claims` con sesión; la clave del negocio (`_public_claim_key`), creada la primera vez.
Sale: la fila del localizador (`_public_claim`). Reimprimir el mismo tique devuelve el mismo localizador, sin mover la fecha límite ni reabrir uno ya canjeado.
Si falla: orden desconocida, `unknown_command` (400); sin su permiso, `permission_denied` (403); opciones mal formadas o de más de 400 entradas, `invalid_choices` (400); sin tipo, tique u orden, `public_claim.incomplete` / `public_claim.no_command` (409).
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F29 (el tique impreso lleva el QR «Pide tu factura» con el localizador)
QA: L-02

### HUB-F17 Canjear un localizador en la página pública
Estado: parcial — un dato rechazado (un NIF mal escrito) puede enseñarse con la frase del módulo o del esquema en inglés aunque la página esté en español; los tres campos fijos (NIF, nombre, domicilio) se piden siempre, los declare o no el localizador
Actor: cliente
Pantalla: Página pública para pedir la factura
Pasos:
1. El cliente escanea el segundo QR del tique o escribe la dirección y el «Código del tique»; no inicia sesión.
2. Ve «Pide tu factura», «Convierte el tique que te han dado en una factura completa con tus datos fiscales.» y el formulario: «NIF/CIF», «Nombre o razón social», «Domicilio» y, si el tique los ofrece, desplegables como el país o el tipo de documento.
3. Pulsa «Emitir mi factura».
4. El hub marca el localizador como usado antes de ejecutar nada, junta lo sellado con solo los campos que el cliente puede rellenar (lo sellado gana siempre) y ejecuta la orden con el permiso que esa orden pide, como si fuera el que imprimió el tique.
5. Ve «Tu factura está emitida», la referencia de la factura y «Guarda esta referencia. Si necesitas una copia, enséñala en el mostrador.».
Entra: el localizador; los datos fiscales del cliente; el idioma de la página (el del negocio, o `?lang=es|en`).
Sale: lo que produce la orden del localizador (hoy, la factura completa que sustituye al tique) y la referencia guardada en el localizador. Volver a abrirlo enseña la misma referencia.
Si falla: un código desconocido o de otro negocio: «Este código no corresponde a ningún tique de este negocio. Comprueba que lo has escrito tal como está impreso.» (404). Pasada la fecha: «El plazo para pedir factura de este tique terminó el {fecha}. Pregunta en el mostrador.» (410). Si la orden se rechaza, el localizador se libera y se vuelve al formulario con lo escrito y el motivo (o «No se han podido aceptar los datos. Revisa el NIF y vuelve a intentarlo.»). Si la orden ya no existe en el hub: «Este negocio no puede emitir facturas ahora mismo. Pregunta en el mostrador.». Demasiados fallos desde la misma dirección: «Demasiados intentos. Vuelve a probar en {segundos} segundos.» (429). Dos envíos a la vez: el segundo ve la factura del primero, nunca dos facturas.
Implicados: pendiente
Pendiente de enlazar: invoice — INVOICE-F04 (el cliente pide la factura completa de su tique)
Pendiente de enlazar: architecture — REC_FISCAL-F10 (pasar un tique a factura completa sustitutiva)
QA: L-02, BD-09

### HUB-F18 Redondear el dinero igual en todos los módulos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Los manejadores de los módulos que calculan dinero (Venta, Impuestos, Facturación, Cocina, Servicios, Precios, Carrito, Inventario, Caja) enlazan la misma aritmética del hub (`guest-sdk`).
2. Todo importe es un entero de la unidad mínima de la moneda del negocio (céntimos en euros); las tasas y las cantidades llevan decimales y se calculan en decimal exacto, nunca en coma flotante.
3. El dinero pierde precisión en un solo sitio: el redondeo a la unidad mínima, con la mitad exacta alejándose de cero (la regla de la ley del euro).
4. Una línea se calcula `precio × cantidad − descuento` con un solo redondeo al final; con IVA incluido, la base sale de dividir y la cuota es lo que resta, así que lo cobrado no se mueve un céntimo; el desglose por tipo redondea la cuota una vez por tipo.
Entra: importes, tasas y cantidades de cada manejador; la moneda y sus decimales de los ajustes del negocio.
Sale: los importes que cada módulo guarda y declara.
Si falla: un decimal que llegue donde se espera un importe se redondea, nunca se trunca. Cambiar el redondeo en el hub no llega a un módulo hasta que ese módulo se vuelve a compilar y publicar (lo enlaza al compilarse); el motor de VeriFactu formatea sus importes por su cuenta (HUB_VERIFACTU).
Implicados: pendiente
Pendiente de enlazar: taxes — TAXES-F18 (calcular el impuesto de un importe con el redondeo común)
Pendiente de enlazar: sales — SALES-F01 (el tique se cierra por tipo con el mismo redondeo)
Pendiente de enlazar: invoice — INVOICE-F01 (la cuota de cada tipo cuadra al céntimo)
QA: L-08
