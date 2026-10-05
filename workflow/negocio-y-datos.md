# WORKFLOW — Hub · Negocio y datos

Prefijo: HUB

## Flujos

### HUB-F220 Leer los ajustes del negocio
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Ajustes › Hub
Pasos:
1. La persona abre **Ajustes**; la pantalla pide al hub los ajustes del negocio.
2. Ve país, región, zona horaria, moneda, idioma, apariencia, identidad del negocio y las opciones del PIN. Quien no administra los ve sin poder guardarlos (lo pinta el shell).
3. Antes de iniciar sesión, el teclado del PIN y el formato de dinero salen de otra lectura sin sesión (moneda, decimales, idioma, zona resuelta y dígitos del PIN).
Entra: una sesión de usuario válida, de cualquier perfil (`GET /api/settings`); la lectura sin sesión es `GET /api/hub/context`.
Sale: un objeto con las 20 claves conocidas: lo guardado más el valor por defecto de lo que no tiene fila. Una fila que ya no valida se lee como su valor por defecto; una clave desconocida se ignora. La zona horaria viaja cruda (`null` mientras se deduzca del país); la resuelta va en la lectura sin sesión.
Si falla: sin sesión, 401 con su código. Si la lectura de arranque falla, el shell arranca con los valores por defecto (EUR, español, UTC).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Hub (la pantalla que pinta estos valores)
QA: BD-02

### HUB-F221 Cambiar los ajustes del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Hub
Pasos:
1. El administrador cambia uno o varios valores y pulsa guardar.
2. El hub valida el lote entero antes de escribir nada: una clave desconocida o un valor inválido rechaza todo con 422.
3. Si todo valida, escribe clave a clave y devuelve el objeto completo actualizado.
Entra: un mapa parcial de claves, con la sesión de un propietario o administrador. No sirve una llave de API ni el token de máquina.
Sale: una fila por clave con quién la cambió (`hub_user:<id>`) y cuándo. No sale ningún aviso a los módulos: no existe un evento de ajustes cambiados; cada módulo recibe el valor nuevo en la siguiente orden que se le dé (HUB-F228). Claves: `currency`, `currency_decimals`, `language`, `country_code`, `region_code`, `timezone`, `theme_palette`, `api_docs_enabled`, `notify_allowed_recipients`, las de identidad (HUB-F222) y `pin_policy`, `pin_length`, `pin_inactivity_minutes` (de Acceso). No guarda historial de valores anteriores.
Si falla: el rechazo por validación no escribe nada. Las escrituras de un lote no van en una única transacción: si la base falla a mitad, las claves anteriores quedan guardadas y se ve el error.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso (las claves del PIN que comparten esta puerta)
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Hub (formulario de ajustes)
QA: BD-02

### HUB-F222 Guardar la identidad del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Negocio
Pasos:
1. El administrador escribe identificador fiscal, razón social y el domicilio en vía, número, código postal y municipio.
2. Guarda.
3. El hub valida el identificador y compone la línea de domicilio.
Entra: `business_tax_id`, `business_legal_name`, `business_street`, `business_street_number`, `business_postal_code`, `business_city`.
Sale: el identificador se acepta como DNI, NIE o CIF con su control oficial, o como identificador extranjero con prefijo de país (no `ES`); los puntos y guiones se quitan. Cada fallo tiene su código (`invalid_tax_id_type`, `tax_id_too_long`, `invalid_tax_id_format`, `invalid_tax_id_control`). Los textos admiten hasta 500 caracteres. `business_address` se compone como «vía número, CP municipio» solo cuando el lote trae alguna parte; las partes que faltan salen de lo guardado, y un guardado de otra cosa no la borra. Vacío es válido: que la identidad esté completa lo decide la puerta fiscal. Esas tres claves llegan a todo módulo en cada orden como `:business_tax_id`, `:business_legal_name` y `:business_address`.
Si falla: 422 con el código del identificador o del campo; no se guarda nada. En una demo el administrador la escribe igual que en un hub real.
Implicados: VERIFACTU-F01
QA: BD-02

### HUB-F223 Congelar el NIF y el país, y casar la región con el país
Estado: hecho
Actor: administrador, sistema
Pantalla: HUB_SHELL: Ajustes › Negocio
Pasos:
1. Un hub que ya emitió su primer registro fiscal intenta cambiar el identificador fiscal, o uno que ya salió a producción intenta cambiar el país.
2. El hub compara el valor normalizado con el guardado y con el ancla del perfil fiscal.
3. Si cambia, lo rechaza.
Entra: `business_tax_id` o `country_code` en un guardado de ajustes.
Sale: nada guardado. El NIF se congela con el primer registro enviado; el país, al pasar el perfil a activo o cerrado. Repetir el mismo valor no es un cambio. La región (`ES-CN`…) debe empezar por el país del lote o, si no viene, el guardado; vaciarla siempre vale. Si el perfil no se puede leer, no se congela nada.
Si falla: `business_tax_id_frozen` o `hub_country_frozen`, con el valor al que está anclado y desde cuándo; o 422 `settings.region_code`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, perfil fiscal (el perfil guarda su propia copia del país y el sello del primer registro)
QA: BD-02

### HUB-F224 Publicar la identidad del negocio en el SaaS
Estado: hecho
Actor: administrador, sistema
Pantalla: HUB_SHELL: Ajustes › Negocio
Pasos:
1. El administrador guarda un cambio en NIF, razón social, domicilio, país o en la casilla «usar estos datos también para mi factura de ERPlora».
2. El hub guarda y, si hay NIF, lo manda al SaaS con la credencial de máquina (espera 5 segundos como máximo).
3. La respuesta de guardado dice si no llegó.
Entra: la identidad guardada y `business_identity_for_erplora_billing`.
Sale: el SaaS refleja el NIF para la autorización de representación; solo con la casilla marcada toca el perfil que paga el hub. La casilla viaja siempre, también apagada, y no viaja en una plantilla. Un guardado de otra clave no publica nada. También existe `POST /api/business/fiscal-identity`, que reenvía lo guardado.
Si falla: el guardado queda escrito y la respuesta lleva `fiscal_identity_publish_error` (`cloud_rejected` o `cloud_unreachable`). Sin NIF o sin credencial de máquina no se avisa.
Implicados: pendiente
Pendiente de enlazar: saas — alta de la identidad fiscal y perfil de facturación del hub
QA: BD-02

### HUB-F225 Sembrar el país y la identidad de una demo al arrancar
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar, el hub lee `HUB_COUNTRY`.
2. Si es un país ISO y no hay país guardado, lo guarda.
3. Si es una demo, rellena NIF, razón social y domicilio vacíos con los de ERPlora Demo.
Entra: `HUB_COUNTRY` del despliegue y la marca de demo.
Sale: `country_code` con autor `system:provisioning`; en la demo, las tres claves con autor `system:demo`. Nunca pisa un valor ya guardado ni una corrección del administrador.
Si falla: se escribe una línea en el log y el arranque sigue.
Implicados: pendiente
Pendiente de enlazar: saas — alta del hub (el país elegido que viaja como `HUB_COUNTRY`)
QA: BD-02

### HUB-F226 Moneda, decimales e idioma del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Hub
Pasos:
1. El administrador elige moneda e idioma y guarda.
2. Solo si la moneda no está en el registro ISO-4217, declara sus decimales.
Entra: `currency` (3 letras, se pasa a mayúsculas), `currency_decimals` (0 a 4 o vacío), `language` (`es` o `en`).
Sale: el dinero viaja en unidades mínimas; los decimales salen de `currency_decimals` o, si no, del registro (EUR 2, JPY 0, KWD 3, desconocida 2). El idioma decide el del papel de la impresora y el de quien llama cuando no tiene el suyo (HUB-F228). La moneda no se entrega a los módulos en las órdenes y no se bloquea tras vender.
Si falla: 422 con la clave; una fila ilegible se lee como el valor por defecto.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, impresión (el idioma del papel se sella en cada documento)
QA: ninguno

### HUB-F227 Fijar la zona horaria del negocio
Estado: hecho
Actor: administrador, sistema
Pantalla: HUB_SHELL: Ajustes › Hub
Pasos:
1. El administrador comprueba la zona horaria en Ajustes; por defecto no escribe nada.
2. Si su país tiene varios husos, elige una zona por nombre (Europe/Madrid).
3. El hub guarda el nombre.
Entra: `timezone` (nombre IANA, o vacío para deducirla), `country_code`, `region_code`.
Sale: la zona resuelta es la declarada si vale; si no, la deducida del país y la región. Se deduce solo donde es única: España Europe/Madrid (`ES-CN` Atlantic/Canary), Portugal Lisbon (`PT-20` Azores, `PT-30` Madeira) y 30 países europeos; un país con varios husos o fuera de la tabla da UTC hasta que se declare. Una abreviatura (`CEST`) o un desfase (`+02:00`) se rechaza. Una fila corrupta degrada a la deducción. Se ofrece resuelta en la lectura sin sesión.
Si falla: 422 `settings.timezone`. Si la tabla no se lee, se deduce del país por defecto (`ES`).
Implicados: SCHEDULES-F09
QA: BD-06

### HUB-F228 Entregar el reloj del negocio a los módulos en cada orden
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo recibe una orden o una consulta.
2. Antes de ejecutarla, el hub resuelve la zona del negocio y el idioma de quien llama.
3. El módulo las usa en su SQL o en su manejador.
Entra: la zona (HUB-F227), el idioma personal o el del hub (`es` si no hay), y la identidad (HUB-F222).
Sale: `:timezone` y `:caller_lang` en el SQL de órdenes y consultas, y `timezone` en el contexto de los manejadores, ya como nombre IANA. `UTC` si no se pudo resolver, nunca vacío. El instante `:now` sigue siendo UTC. Un manejador recibe además `country_code` y `region_code`; el SQL, no. Las tareas programadas que declara un módulo siguen en UTC aunque el negocio esté en otra zona.
Si falla: si la lectura falla, UTC y `es`; el módulo no se entera.
Implicados: SCHEDULES-F10, SCHEDULES-F09
QA: BD-06

### HUB-F229 Mover los horarios de las automatizaciones con la zona
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una automatización se guarda con un disparador de reloj, o el negocio cambia su zona o su país.
2. El hub calcula la próxima ejecución en la zona del negocio.
3. En el siguiente barrido reprograma todo disparador de reloj calculado con otra zona.
Entra: la expresión del disparador y la zona resuelta.
Sale: la hora del disparador es hora de pared del negocio. Una hora que se repite al cambiar el reloj se toma la primera vez; una que no existe pasa al final del hueco. Un disparador de instante fijo lleva su propio desfase. La zona no se guarda en el documento: corregir el país corrige todas a la vez.
Si falla: una expresión que no se puede resolver no se programa y se avisa.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, automatizaciones (disparadores de reloj)
QA: ninguno

### HUB-F230 Exportar los datos del negocio
Estado: parcial — el volcado traga en silencio los errores de lectura de usuarios, perfiles y automatizaciones (un fallo da un zip sin esa parte y sin avisar), descarta lo marcado como borrado (`is_deleted`) y toda fila con `created_by = 'system'`, y el nombre y país del manifiesto se leen de claves que no existen (`business_name`, `country`): salen vacío y `ES`
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Exportar
Pasos:
1. El administrador escribe un nombre (letras, números, guiones; hasta 64) y el idioma, y elige copia de seguridad o plantilla.
2. Marca personas, ajustes, datos fiscales, archivos y, por app, si entra la app y sus datos (y qué tablas).
3. Pulsa exportar; el navegador descarga `<nombre>_<idioma>.blueprint.zip`.
Entra: nombre, idioma y selección, con sesión de administrador.
Sale: un zip con `manifest.json` (versión de formato 1, finalidad, módulos con versión, secciones, roles activos, permisos de módulos, automatizaciones, sha256 de cada fichero) y `data/*.sql`. Solo filas del hub, ordenadas para que un padre vaya antes que su hijo. Una copia lleva personas (con perfil, preferencias, PIN y el vínculo con la cuenta del SaaS a vacío), todos los ajustes, permisos concedidos, automatizaciones con sus permisos y el certificado propio. Una plantilla no lleva personas, datos fiscales, permisos ni automatizaciones; de los ajustes solo `country_code`, `region_code`, `currency`, `currency_decimals`, `language` y `theme_palette` (la zona horaria no viaja); y deja fuera la numeración de facturas. Las casillas acotan, nunca amplían. Una demo y el hub de desarrollo exportan siempre plantilla. No salen nunca los secretos de automatizaciones, el historial ni las tablas `_hub_*`. Los importes y cantidades salen tal como se guardan (unidades mínimas y cantidades a escala 10⁶).
Si falla: nombre inválido, 422; sin sesión de administrador, 401. Una parte que no se puede leer falta del zip sin aviso.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Exportar
QA: ninguno

### HUB-F231 Meter los archivos y el certificado en el zip
Estado: parcial — con finalidad plantilla y «datos fiscales» marcado, esta capa añade igualmente el certificado propio al zip; los ficheros de más de 25 MiB se omiten sin decirlo y todo se carga en memoria antes de empaquetar
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Exportar
Pasos:
1. El administrador marca datos fiscales y/o archivos.
2. El hub añade el certificado y recorre la carpeta de archivos.
Entra: la selección del export.
Sale: con datos fiscales, `data/fiscal/certificate.p12` solo si el negocio tiene certificado propio (nunca el delegado de ERPlora) y sin su contraseña. Con archivos, cada fichero de la carpeta de archivos bajo `media/`, menos las carpetas de primer nivel que empiezan por `_` (registros y sistema). El sha256 de cada uno entra en el manifiesto.
Si falla: un fichero que no se descarga, o pasa de 25 MiB, falta del zip y solo queda en el log.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Exportar
QA: ninguno

### HUB-F232 Ver qué tablas y cuántas filas lleva cada app
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Exportar
Pasos:
1. Al abrir Exportar, la pantalla pide el recuento por tabla de cada app instalada.
2. El administrador desmarca las tablas que no quiere publicar.
Entra: sesión de administrador.
Sale: por app, sus tablas con el número de filas que de verdad volcaría el export (mismas reglas de hub, borrados y filas sembradas), de más a menos, y la finalidad impuesta si la hay.
Si falla: 401 sin sesión de administrador.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Exportar
QA: ninguno

### HUB-F233 Inspeccionar un fichero antes de importarlo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. El administrador elige un `.blueprint.zip` de su equipo.
2. El hub lo abre en memoria, comprueba las rutas y lee el manifiesto.
3. La pantalla muestra nombre, idioma, país, apps y secciones, y deja marcar qué aplicar.
Entra: el zip (hasta 256 MiB).
Sale: un identificador de subida y el manifiesto; el zip queda en una carpeta temporal del hub hasta que se importa.
Si falla: 422 si el zip está mal formado, una ruta intenta salir de su carpeta, falta `manifest.json` o la versión de formato no es la 1.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Importar
QA: ninguno

### HUB-F234 Traer una plantilla del catálogo
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. La pantalla muestra el catálogo de plantillas de erplora.com («Desde erplora.com»).
2. La persona elige una; el hub la descarga.
3. Sigue el mismo camino que un fichero local (HUB-F233 y HUB-F235).
Entra: el identificador de la plantilla (y el idioma si hay dos).
Sale: el zip, entregado solo si su sha256 coincide con el que anunció el SaaS; la credencial de máquina no sale del hub. Lista y descarga piden sesión de usuario de cualquier perfil; aplicarla pide administrador.
Si falla: sin credencial, 424; hash distinto, error y ningún byte; un identificador en dos idiomas, el SaaS contesta 400.
Implicados: pendiente
Pendiente de enlazar: saas — catálogo de plantillas y descarga firmada
QA: BD-01

### HUB-F235 Importar un fichero o una plantilla
Estado: parcial — el aviso «sin SQL arbitrario» cubre la forma, no el valor: una sección no se aplica en una transacción, así que una sentencia que falla deja las anteriores escritas (quedan en el lote y se pueden deshacer, salvo ajustes y tablas sin `id`); y las apps del manifiesto se instalan aunque no estén marcadas
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. El administrador marca qué aplicar y pulsa importar.
2. El hub comprueba la integridad y instala las apps que falten.
3. Aplica las secciones y devuelve el informe (HUB-F239).
Entra: el identificador de subida y la selección (personas, ajustes, fiscal, archivos, apps con datos).
Sale: en este orden: (1) sha256 de cada fichero en ambos sentidos y versión de formato; si falla, 422 sin efectos. (2) Instalación de las apps del manifiesto no instaladas; una copia reinstala la versión del manifiesto, una plantilla la más nueva compatible; una app de pago sin comprar sale `blocked`. (3) Un lote de importación con el nombre de la plantilla. (4) Las secciones en el orden del manifiesto (personas, ajustes, apps), solo `INSERT` de literales en sus propias tablas, nunca tablas `_*`, cada fila con un identificador nuevo derivado del hub destino. (5) Roles, permisos y automatizaciones (HUB-F237). (6) Archivos al gestor, por lotes de 40 y 25 MiB con reintentos. (7) El certificado nunca se aplica: queda `pending` y se sube a mano, porque su contraseña no viaja; en una plantilla, `ignored`. Una sección que sustituye a una fila de marcador sembrada por la app (por ejemplo el horario genérico) la retira si la sección aterrizó. El arranque de un hub nuevo ya no importa ninguna plantilla.
Si falla: una sección fallida se anota y el resto sigue; una app que no se instala deja `failed` su sección («módulo no instalado»).
Implicados: INVENTORY-F12, SCHEDULES-F12
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Importar
Pendiente de enlazar: blueprints — catálogo de arranque que sustituye la semana de Horarios
QA: BD-01, qa-hub §4

### HUB-F236 Qué deja entrar el hub según de quién es el fichero
Estado: parcial — «es mi propia copia» se decide solo con el `hub_id` que el propio fichero declara, y ese identificador lo ve cualquiera sin sesión en `GET /api/hub/context`: un zip fabricado con él pasa por copia propia y se lleva personas, permisos, automatizaciones y datos ligados a la instalación
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub compara el origen del manifiesto con su propio identificador; un origen vacío nunca coincide.
2. Aplica a cada sección la regla de abajo.
Entra: el manifiesto y la selección.
Sale: nunca entran los datos de sistema (`_*`). Una plantilla descarta personas y datos fiscales aunque estén marcados. En un fichero que no es la copia propia se descartan: las personas, de los ajustes todo lo que no sea configuración (queda `PartiallyApplied` con `settings_not_portable` y el número de filas), la numeración de facturas y su libro (`numbering_not_portable`), los datos de apps ligados a la instalación como la cadena fiscal (`installation_bound_data`), y los permisos de módulo y de automatizaciones. Una fila de una tabla que la app instalada ya no tiene se salta (`table_gone_in_installed_version`) sin perder el resto. Se aplica la regla por el manifiesto, no por la casilla.
Si falla: la sección descartada sale `Ignored` con su código y el número de filas.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, perfil fiscal (la cadena VeriFactu no cruza hubs)
QA: BD-01

### HUB-F237 Permisos, roles y automatizaciones que trae el fichero
Estado: hecho
Actor: sistema, administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. Tras las secciones de datos, el hub activa los roles del manifiesto.
2. Si es la copia propia, devuelve los permisos concedidos a cada app.
3. Guarda las automatizaciones por la misma puerta que la pantalla de automatizaciones.
4. Al terminar, la pantalla pregunta por los permisos que una plantilla no puede conceder.
Entra: `active_roles`, `capability_grants` y `flows` del manifiesto.
Sale: un rol que ninguna app declara, o uno base o de administración, se rechaza (`roles_not_activatable`). Los permisos de una plantilla se descartan siempre (`capability_grants_not_portable`); en la copia propia se vuelven a conceder los que la app instalada declara (`capabilities_not_grantable` para el resto). Cada automatización entra apagada, con una copia de sus permisos solo si es la copia propia, y se enciende al final si todos volvieron; si no, queda en pausa (`flows_paused_without_grants`). Un documento que la pantalla rechazaría se cuenta y no entra (`flows_not_restorable`). El mismo nombre y documento ya vivos no se duplican; nunca se borra lo creado después. Los secretos no viajan. Estas tres piezas se aplican aunque ninguna casilla las nombre.
Si falla: un fallo de base de datos sale `Failed`, no como descarte.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, automatizaciones (guardar una automatización y sus permisos)
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Permisos (los permisos que la plantilla no concede)
QA: BD-01

### HUB-F238 Volver a importar lo mismo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. El administrador importa un fichero o plantilla que ya aplicó, o uno que choca con datos que ya tiene.
2. El hub salta las filas que ya existen.
3. El informe cuenta las secciones como aplicadas.
Entra: el mismo zip, o uno con las mismas claves naturales.
Sale: identificadores derivados del hub y de la fila origen: reimportar en el mismo hub no duplica. Además, una fila se salta si ya hay una equivalente por cualquier índice único de su tabla (el SKU de un producto, el código de una serie) y por las claves que declara el sembrado de la app, salvo en la copia propia. Nunca se actualiza una fila existente ni se renumera: un SKU repetido conserva el precio y el stock que ya tiene. Los ajustes ya guardados no se pisan (se escribe solo lo que no tiene fila). Los importes y cantidades entran sin convertir.
Si falla: sin confirmar qué pasa con un índice parcial que el hub no sabe leer: esa clave se ignora y la fila puede chocar.
Implicados: INVENTORY-F12
QA: BD-01

### HUB-F239 El informe de la importación
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. Al terminar, la pantalla pinta una línea por sección: aplicada, omitida, descartada, parcial o fallida.
2. Si se sale de la pantalla, al volver a Ajustes › Datos recupera el último informe.
Entra: el resultado de la importación.
Sale: una fila por sección con su estado, el motivo estable y las filas descartadas; más apps instaladas (`installed`, `already_installed`, `failed`, `blocked`, versión pedida si se sustituyó), archivos copiados y fallidos, estado del certificado y el origen (plantilla y versión, o fichero local). Se guarda por lote y se borra al deshacerlo.
Si falla: si no se puede guardar, la importación vale y solo se pierde esta vista.
Implicados: INVENTORY-F12
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Importar (informe y tarjeta de inicio)
QA: BD-01

### HUB-F240 Reintentar lo que falló en una importación
Estado: parcial — solo las importaciones de plantilla del catálogo; una de fichero local se rechaza
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Importar
Pasos:
1. Tras un informe parcial, el administrador pulsa reintentar.
2. El hub vuelve a bajar la misma plantilla y aplica solo lo fallido.
3. Sale un informe nuevo.
Entra: el lote del informe.
Sale: reaplica solo secciones `Failed`, apps `failed` o `blocked` y archivos que fallaron. Se niega si el catálogo ya sirve otra versión. Si no queda nada, responde que no hay nada que reintentar.
Si falla: `import_origin_not_retryable`, `import_retry_version_unavailable`, `import_retry_batch_not_found`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Importar (botón de reintento)
QA: ninguno

### HUB-F241 Deshacer una importación
Estado: parcial — solo quita filas con `id`; los ajustes y las tablas de vínculo no se revierten
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Restablecer
Pasos:
1. El administrador elige una importación de la lista y la deshace.
2. El hub borra las filas que trajo.
Entra: el lote.
Sale: se borran exactamente las filas registradas, en una transacción, sin tocar lo creado después; vuelven los marcadores sembrados que el lote retiró, si nadie escribió ahí. La lista avisa de las tablas editadas después. Deshacer dos veces, o un lote ajeno, no hace nada.
Si falla: si el borrado revierte, el lote sigue.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Restablecer
QA: ninguno

### HUB-F242 Restablecer el hub
Estado: parcial — las secciones «archivos» y «datos fiscales» se aceptan pero no borran nada (solo bloquean si ya se emitió); el borrado de personas deja su perfil y preferencias; el servidor no pide ninguna confirmación (el nombre del negocio lo pide la pantalla)
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos › Restablecer
Pasos:
1. El administrador abre Restablecer y ve cada sección con su número de filas y sus bloqueos.
2. Marca solo lo necesario y confirma en pantalla.
3. Lee el informe.
Entra: la selección (ajustes, personas, roles, cola de impresión, apps); todo apagado por defecto.
Sale: borrado duro, acotado al hub, en una sola transacción, en orden inverso de claves foráneas; las filas que sembró la app sobreviven. Las personas se borran menos quien ejecuta (sale de su sesión). La cola de impresión se vacía; las impresoras emparejadas no. Si el hub ya emitió registros fiscales (sello del primer registro o facturas remitidas), Verifactu, Facturas y Ventas y los datos fiscales quedan bloqueados (RD 1007/2023) y el servidor lo rechaza con 409 aunque el cliente lo fuerce. No toca historial de avisos ni automatizaciones.
Si falla: 409 con el motivo y «No se ha borrado nada»; si la transacción falla, no se borra nada.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Datos › Restablecer
QA: ninguno

### HUB-F243 Convertir el dinero de un hub antiguo a céntimos
Estado: parcial — solo se lanza como subcomando del binario (`--backfill-money`), sin puerta de API
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar, un hub con todo el dinero ya en enteros se marca `money_unit = cents`.
2. Un hub antiguo en euros espera la orden de conversión.
3. La orden convierte cada columna de dinero.
Entra: el tipo declarado de cada columna de dinero de `MONEY_COLUMNS`.
Sale: si todas son enteras, solo se marca; si todas son decimales, se multiplica por 100 y se marca en una transacción; si hay mezcla, se niega, no marca ni convierte y lo comunica. Repetirla no hace nada. No toca las cantidades (escala 10⁶).
Si falla: `money_unit_ambiguous` en un hub a medias.
Implicados: pendiente
Pendiente de enlazar: infra — operación de conversión de dinero en un hub desplegado
QA: ninguno

### HUB-F244 Comprobar la unidad del dinero sin escribir
Estado: parcial — solo como subcomando del binario (`--check-money-unit`)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Operaciones lanza la comprobación contra la base del hub.
2. Lee el marcador y el tipo de cada columna.
Entra: la base del hub.
Sale: céntimos, euros, sin dinero o mezcla, sin crear ni escribir nada.
Si falla: una mezcla se comunica por el registro de errores y por stderr.
Implicados: ninguno
QA: ninguno

### HUB-F245 Ver y descargar archivos
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Archivos
Pasos:
1. La persona abre **Archivos** y navega por carpetas.
2. Abre un archivo en el visor o lo descarga.
Entra: la carpeta o la ruta; sesión de usuario de cualquier perfil. Una llave de API no entra.
Sale: el listado (carpetas, ficheros, cuota y qué acciones permite cada carpeta) y los bytes, que el hub pide al almacenamiento de erplora.com y entrega (tope de 25 MiB, 8 descargas a la vez). Para que una imagen del TPV se cargue sin cabecera, el hub da una cookie de solo lectura (`erplora_media`, `HttpOnly`, `Secure`, `SameSite=Strict`, solo para la puerta de lectura). Todo usuario con sesión puede leer cualquier carpeta, incluidos `_logs` (registro de peticiones) y los XML de Verifactu: no hay permiso de lectura por fichero.
Si falla: hub sin credencial de máquina o nube caída, 424 con código; sin sesión, 401.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Archivos
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F06, adjuntos recibidos (aquí solo dónde se guardan)
QA: ninguno

### HUB-F246 Subir, organizar y borrar archivos
Estado: parcial — no existe copiar; los archivos no se pueden borrar ni subir en carpetas de apps que no lo declaran
Actor: administrador
Pantalla: HUB_SHELL: Archivos
Pasos:
1. El administrador sube ficheros, crea una carpeta, renombra, mueve o borra.
2. El hub comprueba qué permite la carpeta.
Entra: ruta y acción, con sesión de propietario o administrador.
Sale: la carpeta decide: `_logs` y `_system` y la raíz `modules` son solo lectura; bajo `modules/<carpeta>/` manda lo que la app declara en `static_files.user_actions` (sin declarar, solo lectura); cualquier otra carpeta, gestión completa. Renombrar solo cambia el nombre (no admite rutas). Mover exige poder borrar el origen y subir al destino, y no deja meter una carpeta en sí misma. Crear carpeta cuenta como subir. Todo se hace en el almacenamiento de erplora.com, que valida las rutas.
Si falla: 403 `media.read_only_folder`, 400 `media.invalid_name`, `media.same_path`, `media.move_into_itself`; 424 con la nube.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Archivos
QA: ninguno

### HUB-F247 Guardar ficheros desde una app
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una app declara `static_files.folder` en su manifiesto.
2. Al instalarla, el hub crea `media/modules/<carpeta>/`.
3. La app pide escribir un fichero con una ruta relativa.
Entra: carpeta (minúsculas, dígitos, `_`, `-`, hasta 64) y ruta relativa sin `..`, sin `/` inicial, sin `\`.
Sale: el fichero queda en `modules/<carpeta>/<ruta>` y el hub devuelve esa ruta; en producción por el almacenamiento de erplora.com, en desarrollo en disco, con la misma ruta lógica. Una app solo escribe en su carpeta; la persona la ve en Archivos según HUB-F246.
Si falla: carpeta o ruta inválida, error de almacenamiento antes de tocar la red; sin credencial de máquina, la instalación de una app con `static_files` falla.
Implicados: pendiente
Pendiente de enlazar: verifactu — la copia de cada XML en el almacenamiento de ficheros del módulo
QA: ninguno

### HUB-F248 Borrar los datos de una persona: el aviso único
Estado: parcial — el aviso lo emite Clientes y solo lo escuchan WhatsApp, Servicios y el hub; Citas, Reservas y Reservas online no; el motivo escrito por el administrador queda en el propio aviso durante 90 días
Actor: administrador, sistema
Pantalla: HUB_SHELL: Clientes › ficha del cliente
Pasos:
1. El administrador pulsa **Borrar datos personales** en la ficha (flujo de Clientes).
2. Clientes sustituye los datos de la ficha y publica `customer.anonymized`.
3. El hub entrega ese aviso a quien lo escucha y vacía su propio historial (HUB-F249).
Entra: el aviso `<sujeto>.anonymized` con su `<sujeto>_id` (de Clientes: `customer_id` y `reason`, hasta 500 caracteres).
Sale: el contrato es solo un nombre: el hub reconoce cualquier evento que acabe en `.anonymized` con el identificador del sujeto como cadena y no nombra a ningún módulo. Cada módulo que guarda algo de la persona se suscribe a ese aviso y borra lo suyo (HUB-F250); lo que no lo hace, se queda. Es idempotente: repetirlo no cambia nada. Cualquier app puede emitir un `.anonymized` y vaciar el historial de un identificador ajeno (no hay regla de permiso, hub#2485).
Si falla: si el vaciado del hub falla, el aviso se difiere y se reintenta con espera creciente, y no se marca entregado hasta que termina.
Implicados: CUSTOMERS-F16
QA: L-10, WA-06 (discrepa)

### HUB-F249 Vaciar el historial del hub que nombra a la persona
Estado: parcial — no repasa lo que estaba en curso al borrar y acaba después (hub#2484), ni las copias que llevan el dato sin el identificador (hub#2477, hub#2474), ni el propio aviso de borrado
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub entrega un aviso `<sujeto>.anonymized`.
2. En una sola sentencia vacía (`{}`) lo terminal que nombra ese identificador.
3. Registra cuántas filas vació.
Entra: el identificador y el hub.
Sale: se vacían, sin borrar la fila: los avisos entregados o descartados cuyo contenido tiene el identificador como valor; las ejecuciones terminadas (hechas, fallidas, canceladas) que lo tocan en entrada, variables, paso o propuesta, o que nacieron de un aviso así; todos los pasos y propuestas de esas ejecuciones; y los avisos que esas ejecuciones encolaron (un recordatorio lleva el teléfono sin el identificador). No se tocan los avisos pendientes o atascados ni las ejecuciones vivas: conservan los datos hasta procesarse o hasta la retención de 90 días (HUB-F253). Se conserva la fila porque es el rastro de la trazabilidad. Solo este hub; reentrega sin efecto. Coste: un barrido del historial terminal por borrado.
Si falla: error de base de datos; el aviso queda sin entregar y el reintento lo completa; nada queda medio vaciado.
Implicados: CUSTOMERS-F16, WHATSAPP_INBOX-F11
QA: L-10

### HUB-F250 Lo que le toca a cada app al recibir el aviso de borrado
Estado: parcial — Citas (nombre, teléfono, correo y notas en citas, series e historial), Reservas (RESERVATIONS-F22) y Reservas online no escuchan el aviso
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una app que guarda datos de la persona escucha el aviso.
2. Vacía sus tablas por el identificador de la ficha.
Entra: `customer.anonymized` y su identificador.
Sale: el hub garantiza entrega con reintentos, el vaciado de su historial (HUB-F249) y que ningún módulo puede tocar las tablas del núcleo. No garantiza que cada app escuche, ni vacía las tablas de una app. Hoy: WhatsApp vacía y cierra sus conversaciones unidas a la ficha; Servicios marca sus bonos; Ventas y Facturas conservan su copia fiscal a propósito, y Verifactu conserva NIF y nombre del cliente en sus registros y XML porque la norma obliga a conservarlos.
Si falla: el aviso de esa app se reintenta como cualquier otro.
Implicados: CUSTOMERS-F16, RESERVATIONS-F22, WHATSAPP_INBOX-F11
QA: L-10, WA-06 (discrepa)

### HUB-F251 Borrar los datos de un número sin ficha
Estado: no hecho — la bandeja de WhatsApp borra sus conversaciones pero no emite ningún aviso `.anonymized` con un identificador que el hub pueda buscar: los mensajes y su número siguen 90 días en el historial del hub (hub#2474, hub#2477)
Actor: administrador
Pantalla: HUB_SHELL: WhatsApp › Bandeja de entrada
Pasos:
1. El administrador pulsa **Borrar datos de este número** en una conversación.
2. La app borra lo suyo.
3. Debería avisar al hub para vaciar las copias de los mensajes.
Entra: el identificador de la conversación o una huella del número.
Sale: hoy, nada en el hub. `hub.whatsapp.message_received` y `whatsapp_inbox.message.received` guardan número, nombre y texto sin identificador de ficha.
Si falla: sin confirmar (no existe).
Implicados: WHATSAPP_INBOX-F10
QA: L-11, WA-06 (discrepa)

### HUB-F252 Borrar los datos de una persona del equipo
Estado: no hecho — el hub solo desactiva a una persona (cierra sus sesiones); nombre, correo, PIN cifrado, perfil y preferencias se quedan, y no hay vaciado en el historial
Actor: administrador
Pantalla: ninguna
Pasos:
1. El administrador da de baja a una persona del equipo.
2. El hub la marca inactiva y cierra sus sesiones.
Entra: la persona.
Sale: nada se borra ni se seudonimiza. La atribución («quién autorizó qué») conserva el identificador cuatro años y el lector resuelve el nombre.
Si falla: no aplica.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso (dar de baja a una persona)
QA: ninguno

### HUB-F253 Purgar el historial por retención
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada hora el hub cierra primero las propuestas caducadas de las automatizaciones.
2. Después borra el historial terminal con más de 90 días.
3. Registra cuántas filas borró.
Entra: el reloj y el historial de avisos y ejecuciones.
Sale: se borran, a 90 días desde su fin: avisos entregados o descartados (con sus marcadores de entrega), ejecuciones hechas, fallidas o canceladas con sus pasos, propuestas y esperas. Los recibos de autorización de un responsable duran cuatro años (1461 días) y contienen la huella del contenido, no el contenido. No se purgan nunca los avisos pendientes o atascados, ni las ejecuciones vivas. Es dura (`DELETE`), en lotes de 500 y hasta 20 pasadas por vuelta. Los 90 días son fijos. El historial de actualizaciones solo enseña 90 días y los dispositivos sin uso se limpian a mano a los 30 días (Acceso). Nada purga la cola de impresión, que guarda el HTML de cada documento hasta restablecer el hub.
Si falla: se registra el aviso y la vuelta siguiente continúa.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, avisos entre módulos (avisos atascados y su reintento)
QA: ninguno

### HUB-F254 Registrar la actividad del negocio para el SaaS
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien entra, sale, cobra, devuelve o abre o cierra caja.
2. El hub anota un hecho con quién lo hizo.
3. En el latido diario lo manda al SaaS y borra lo entregado.
Entra: la orden pública (`complete_sale`, `refund`, apertura y cierre de caja) o el inicio y cierre de sesión.
Sale: una fila `(id, tipo, usuario del hub, instante)`: nunca nombre, ni nada del cliente final. No se anota sin persona detrás (tareas, avisos). Se lee sin borrar, hasta 500 por latido, y solo se borra tras la confirmación del SaaS; el SaaS descarta duplicados por id. Sin conexión conserva 5.000 y descarta lo más antiguo. Anotar nunca falla la venta.
Si falla: un fallo al anotar se escribe en el log y la operación sigue.
Implicados: pendiente
Pendiente de enlazar: saas — recepción de la actividad del hub
QA: ninguno
