# WORKFLOW — Hub (servidor) · Negocio y datos: ajustes, copias e importación

Prefijo: HUB

> Área «Negocio y datos» del servidor del hub, primera mitad (`crates/runtime`: `settings`,
> `settings_api`, `export`, `import`, `import_sql`, `reset`, `money_backfill`; `crates/server`:
> `settings`, `export_import`, `reset`): los ajustes del negocio (identidad, moneda, idioma, zona
> horaria y el reloj que reciben los módulos), exportar e importar copias y plantillas, restablecer
> el hub y la unidad del dinero. Los archivos, el borrado de los datos de una persona, la retención,
> el registro de actividad y la semilla del arranque están en
> [archivos-y-privacidad.md](archivos-y-privacidad.md). Lo que vale para toda el área está al final
> de este fichero. Las pantallas (Ajustes › General, Negocio y Datos y copias) son de `HUB_SHELL`.

## Referencia adoptada

Para esta área (la del borrado de una persona está en
[archivos-y-privacidad.md](archivos-y-privacidad.md)):

- Ajustes del negocio, zona horaria por nombre IANA y moneda con decimales por ISO-4217: Odoo
  (compañía), Square y Shopify (ajustes de tienda), Business Central (compañía y moneda). Contraste de
  mercado reutilizado de ADR-0273/ADR-0195 y de hub#731.
- Exportar/importar como copia de seguridad frente a plantilla, con mecánica de `migrate`: Odoo
  (módulos con datos de demo), Shopify (importación de CSV y temas), Toast y Square (menú de
  plantilla). Ver `architecture/hub/export-import.md`.

## Antes de empezar

- El país y la zona horaria deben estar bien antes de crear automatizaciones con hora y antes de
  salir a producción fiscal (el país se congela, HUB-F223).
- Cambiar ajustes, exportar, importar y restablecer piden sesión de dueño o administrador (regla
  común del índice); leer los ajustes, cualquier sesión.

## Flujos

### HUB-F220 Leer los ajustes del negocio
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. La persona abre **Ajustes**; la pantalla pide al hub los ajustes del negocio.
2. Ve país, región, zona horaria, moneda, idioma, apariencia, identidad del negocio y las opciones del PIN. Quien no administra los ve sin poder guardarlos (lo pinta el shell).
3. Antes de iniciar sesión, el teclado del PIN y el formato de dinero salen de otra lectura sin sesión (moneda, decimales, idioma, zona resuelta y dígitos del PIN).
Entra: una sesión de usuario válida, de cualquier perfil (`GET /api/settings`); la lectura sin sesión es `GET /api/hub/context`.
Sale: un objeto con las 20 claves conocidas: lo guardado más el valor por defecto de lo que no tiene fila. Una fila que ya no valida se lee como su valor por defecto; una clave desconocida se ignora. La zona horaria viaja cruda (`null` mientras se deduzca del país); la resuelta va en la lectura sin sesión. Esa lectura sin sesión publica además el identificador del hub (la llave de HUB-F236) y el nombre y rol de cada persona con PIN, para la rejilla de acceso.
Si falla: sin sesión, 401 con su código. Si la lectura de arranque falla, el shell arranca con los valores por defecto (EUR, español, UTC).
Implicados: HUB_SHELL-F155
QA: BD-02

### HUB-F221 Cambiar los ajustes del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. El administrador cambia uno o varios valores y pulsa guardar.
2. El hub valida el lote entero antes de escribir nada: una clave desconocida o un valor inválido rechaza todo con 422.
3. Si todo valida, escribe clave a clave y devuelve el objeto completo actualizado.
Entra: un mapa parcial de claves, con la sesión de un propietario o administrador. No sirve una llave de API ni el token de máquina.
Sale: una fila por clave con quién la cambió (`hub_user:<id>`) y cuándo. No sale ningún aviso a los módulos: no existe un evento de ajustes cambiados; cada módulo recibe el valor nuevo en la siguiente orden que se le dé (HUB-F228). Claves: `currency`, `currency_decimals`, `language`, `country_code`, `region_code`, `timezone`, `theme_palette`, `api_docs_enabled`, `notify_allowed_recipients`, las de identidad (HUB-F222) y `pin_policy`, `pin_length`, `pin_inactivity_minutes` (de Acceso). No guarda historial de valores anteriores.
En este mismo documento se apoya en: HUB-F140 (Decidir si el negocio pide PIN y cuántos dígitos tiene).
Si falla: el rechazo por validación no escribe nada. Las escrituras de un lote no van en una única transacción: si la base falla a mitad, las claves anteriores quedan guardadas y se ve el error.
Implicados: HUB_SHELL-F156, HUB_SHELL-F157, HUB_SHELL-F158, HUB_SHELL-F159, HUB_SHELL-F160, HUB_SHELL-F161, HUB_SHELL-F164
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
Implicados: VERIFACTU-F01, REC_ALTA-F09
QA: BD-02

### HUB-F223 Congelar el NIF y el país, y casar la región con el país
Estado: parcial — cambiar solo el país no revalida la región guardada (queda p. ej. `ES-CN` con país `PT`, y la zona deducida pasa a Atlantic/Canary); la región tampoco se congela al salir a producción
Actor: administrador, sistema
Pantalla: HUB_SHELL: Ajustes › Negocio
Pasos:
1. Un hub que ya emitió su primer registro fiscal intenta cambiar el identificador fiscal (en Ajustes › Negocio), o uno que ya salió a producción intenta cambiar el país (en Ajustes › General, donde están también país y región).
2. El hub compara el valor normalizado con el guardado y con el ancla del perfil fiscal.
3. Si cambia, lo rechaza.
Entra: `business_tax_id` o `country_code` en un guardado de ajustes.
Sale: nada guardado. El NIF se congela con el primer registro enviado; el país, al pasar el perfil a activo o cerrado. Repetir el mismo valor no es un cambio. Si el lote trae región, debe empezar por el país del lote o, si no viene, por el guardado; vaciarla siempre vale. Cambiar solo el país no revisa la región guardada. Si el perfil no se puede leer, no se congela nada.
En este mismo documento se apoya en: HUB-F300 (Resolver el perfil fiscal del hub al arrancar), HUB-F307 (Pasar a producción).
Si falla: `business_tax_id_frozen` o `hub_country_frozen`, con el valor al que está anclado y desde cuándo; o 422 `settings.region_code`.
Implicados: REC_ALTA-F09
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
Sale: el SaaS refleja el NIF para la autorización de representación; solo con la casilla marcada toca el perfil que paga el hub. La casilla viaja siempre, también apagada, y no viaja en una plantilla. Publican los cambios de NIF, razón social, `business_address`, país o la casilla; un guardado de otra clave no publica nada, tampoco uno que solo traiga partes del domicilio (sin NIF): recompone la línea pero no la publica. También existe `POST /api/business/fiscal-identity`, que reenvía lo guardado.
Si falla: el guardado queda escrito y la respuesta lleva `fiscal_identity_publish_error` (`cloud_rejected` o `cloud_unreachable`). Sin NIF o sin credencial de máquina no se avisa.
Implicados: REC_ALTA-F09, SAAS_DASHBOARD-F90
QA: BD-02

### HUB-F225 Sembrar el país y la identidad de una demo al arrancar
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar, el hub lee `HUB_COUNTRY`.
2. Si es un país ISO y no hay país guardado, lo guarda.
3. Si es una demo, rellena NIF, razón social y domicilio vacíos con los de ERPlora Demo. A una demo erplora.com le manda `HUB_COUNTRY` vacío, así que la demo no recibe país y el paso 2 no guarda ninguno.
Entra: `HUB_COUNTRY` del despliegue y la marca de demo.
Sale: `country_code` con autor `system:provisioning`; en la demo, las tres claves con autor `system:demo`. Nunca pisa un valor ya guardado ni una corrección del administrador.
Si falla: se escribe una línea en el log y el arranque sigue.
Implicados: REC_ALTA-F09, SAAS_DASHBOARD-F01, SAAS_DASHBOARD-F02, SAAS_DASHBOARD-F28, SAAS_PUBLIC-F90
QA: BD-02

### HUB-F226 Moneda, decimales e idioma del negocio
Estado: parcial — una vez declarados, `currency_decimals` no se puede vaciar por esta puerta (el vacío da 422) para volver a resolverlos del registro
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. El administrador elige moneda e idioma y guarda.
2. Solo si la moneda no está en el registro ISO-4217, declara sus decimales (no hay vuelta atrás a «los del registro»).
Entra: `currency` (3 letras, se pasa a mayúsculas), `currency_decimals` (entero de 0 a 4), `language` (`es` o `en`).
Sale: el dinero viaja en unidades mínimas; los decimales salen de `currency_decimals` o, si no, del registro (EUR 2, JPY 0, KWD 3, desconocida 2). El idioma decide el del papel de la impresora y el de quien llama cuando no tiene el suyo (HUB-F228). La moneda no se entrega a los módulos en las órdenes y no se bloquea tras vender.
En este mismo documento se apoya en: HUB-F190 (Pedir imprimir un documento desde una pantalla o un dispositivo).
Si falla: 422 con la clave; una fila ilegible se lee como el valor por defecto.
Implicados: ninguno
QA: ninguno

### HUB-F227 Fijar la zona horaria del negocio
Estado: hecho
Actor: administrador, sistema
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. El administrador comprueba la zona horaria en Ajustes; por defecto no escribe nada.
2. Si su país tiene varios husos, elige una zona por nombre (Europe/Madrid).
3. El hub guarda el nombre.
Entra: `timezone` (nombre IANA, o vacío para deducirla), `country_code`, `region_code`.
Sale: la zona resuelta es la declarada si vale; si no, la deducida del país y la región. Se deduce solo donde es única: España Europe/Madrid (`ES-CN` Atlantic/Canary), Portugal Lisbon (`PT-20` Azores, `PT-30` Madeira) y otros 29 países europeos; un país con varios husos o fuera de la tabla da UTC hasta que se declare. Se rechaza todo lo que no sea un nombre de la base IANA (`CEST`, `+02:00`); algunos nombres heredados como `CET` sí son IANA y se aceptan. Una fila corrupta degrada a la deducción. Se ofrece resuelta en la lectura sin sesión.
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
En este mismo documento se apoya en: HUB-F83 (Arrancar una automatización según un horario, en la hora del negocio), HUB-F84 (Arrancar una automatización una vez, en una fecha y hora).
Si falla: una expresión que no se puede resolver no se programa y se avisa.
Implicados: ninguno
QA: ninguno

### HUB-F230 Exportar los datos del negocio
Estado: parcial — un fallo al leer usuarios, perfiles, ajustes, roles, permisos de módulo, automatizaciones o las filas de una tabla de app da un zip sin esa parte y sin aviso; el nombre y el país del manifiesto se leen de claves que no existen (`business_name`, `country`): salen vacío y `ES`; y con finalidad plantilla el certificado propio y la carpeta de archivos de cada app (los XML de Verifactu) entran igualmente (HUB-F231)
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Exportar
Pasos:
1. El administrador escribe un nombre (letras, números, guiones; hasta 64) y el idioma, y elige copia de seguridad o plantilla.
2. Marca personas, ajustes, datos fiscales, archivos y, por app, si entra la app y sus datos (y qué tablas).
3. Pulsa exportar; el navegador descarga `<nombre>_<idioma>.blueprint.zip`.
Entra: nombre, idioma y selección, con sesión de administrador.
Sale: un zip con `manifest.json` (versión de formato 1, finalidad, módulos con versión, secciones, roles activos, permisos de módulos, automatizaciones, sha256 de cada fichero) y `data/*.sql`. Solo filas del hub, ordenadas para que un padre vaya antes que su hijo. Una copia lleva personas (con perfil, preferencias, PIN y el vínculo con la cuenta del SaaS a vacío), todos los ajustes, permisos concedidos, automatizaciones con sus permisos y el certificado propio. Se dejan fuera, a propósito, las filas borradas y las que la app siembra al instalarse (salvo las tablas cuya semilla es dato del negocio, como `taxes_rule`). Una plantilla no lleva personas, permisos ni automatizaciones, ni las tablas y la sección fiscales (`verifactu_config`, certificado en el motor) ni la numeración; de los ajustes solo `country_code`, `region_code`, `currency`, `currency_decimals`, `language` y `theme_palette` (la zona horaria no viaja); y deja fuera la numeración de facturas. Las casillas acotan, nunca amplían. Una demo y el hub de desarrollo exportan siempre plantilla. No salen nunca los secretos de automatizaciones, el historial ni las tablas `_hub_*`. Los importes y cantidades salen tal como se guardan (unidades mínimas y cantidades a escala 10⁶).
Si falla: nombre inválido (letras, números, `-`, `_` y `.`), 422; sin sesión de administrador, 401. Una parte que no se puede leer falta del zip sin aviso.
Implicados: HUB_SHELL-F173, HUB_SHELL-F174, REC_ALTA-F23, SAAS_PUBLIC-F40
QA: ninguno

### HUB-F231 Meter los archivos y el certificado en el zip
Estado: parcial — con finalidad plantilla, «datos fiscales» añade igualmente el certificado propio (esta capa mira la casilla en bruto, no el valor efectivo del motor), y «archivos» copia también las carpetas de las apps (`modules/verifactu/`, con los XML que llevan NIF y nombre de clientes), sin mirar la finalidad; los ficheros de más de 25 MiB se omiten sin decirlo y todo se carga en memoria antes de empaquetar
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Exportar
Pasos:
1. El administrador marca datos fiscales y/o archivos.
2. El hub añade el certificado y recorre la carpeta de archivos.
Entra: la selección del export.
Sale: con datos fiscales, `data/fiscal/certificate.p12` solo si el negocio tiene certificado propio (nunca el delegado de ERPlora) y sin su contraseña. Con archivos, cada fichero del almacenamiento bajo `media/`, incluidas las carpetas de las apps, menos las de primer nivel que empiezan por `_` (registros y sistema). No se filtra por finalidad. El sha256 de cada uno entra en el manifiesto.
Si falla: un fichero que no se descarga, o pasa de 25 MiB, falta del zip y solo queda en el log.
Implicados: HUB_SHELL-F173, REC_ALTA-F23, SAAS_PUBLIC-F41
QA: ninguno

### HUB-F232 Ver qué tablas y cuántas filas lleva cada app
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Exportar
Pasos:
1. Al abrir Exportar, la pantalla pide el recuento por tabla de cada app instalada.
2. El administrador desmarca las tablas que no quiere publicar.
Entra: sesión de administrador.
Sale: por app, sus tablas con el número de filas que de verdad volcaría el export (mismas reglas de hub, borrados y filas sembradas), de más a menos, y la finalidad impuesta si la hay.
Si falla: 401 sin sesión de administrador.
Implicados: HUB_SHELL-F173, HUB_SHELL-F174
QA: ninguno

### HUB-F233 Inspeccionar un fichero antes de importarlo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. El administrador elige un `.blueprint.zip` de su equipo.
2. El hub lo abre en memoria, comprueba las rutas y lee el manifiesto.
3. La pantalla muestra nombre, idioma, país, apps y secciones, y deja marcar qué aplicar.
Entra: el zip (hasta 256 MiB).
Sale: un identificador de subida y el manifiesto; el zip queda en una carpeta temporal del hub hasta que se importa; uno inspeccionado y nunca importado se queda hasta que el contenedor se reinicia.
Si falla: 422 si el zip está mal formado, una ruta intenta salir de su carpeta, falta `manifest.json` o la versión de formato no es la 1.
Implicados: HUB_SHELL-F176
QA: ninguno

### HUB-F234 Traer una plantilla del catálogo
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. La pantalla muestra el catálogo de plantillas de erplora.com («Desde erplora.com»).
2. La persona elige una; el hub la descarga.
3. Sigue el mismo camino que un fichero local (HUB-F233 y HUB-F235).
Entra: el identificador de la plantilla (y el idioma si hay dos).
Sale: el zip, entregado solo si su sha256 coincide con el que anunció el SaaS; la credencial de máquina no sale del hub. Lista y descarga piden sesión de usuario de cualquier perfil; aplicarla pide administrador.
Si falla: sin credencial, 424; hash distinto, error y ningún byte; un identificador en dos idiomas, el SaaS contesta 400.
Implicados: HUB_SHELL-F26, HUB_SHELL-F175, INVENTORY-F12, REC_ALTA-F08, SAAS_DASHBOARD-F193, SAAS_PUBLIC-F45, SAAS_PUBLIC-F46
QA: BD-01

### HUB-F235 Importar un fichero o una plantilla
Estado: parcial — una sección no se aplica en una transacción, así que una sentencia que falla deja las anteriores escritas (quedan en el lote y se pueden deshacer, salvo ajustes y tablas sin `id`); las apps del manifiesto se instalan aunque no estén marcadas; los archivos del zip se escriben en cualquier carpeta, también en las de solo lectura de las apps y en `_logs`, sin la política de HUB-F246; y en una tabla de objeto único se retira lo que hubiera antes aunque lo escribiera el negocio
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. El administrador marca qué aplicar y pulsa importar.
2. El hub comprueba la integridad y instala las apps que falten.
3. Aplica las secciones y devuelve el informe (HUB-F239).
Entra: el identificador de subida y la selección (personas, ajustes, fiscal, archivos, apps con datos).
Sale: en este orden: (1) sha256 de cada fichero en ambos sentidos y versión de formato; si falla, 422 sin efectos. (2) Instalación de las apps del manifiesto no instaladas; una copia reinstala la versión del manifiesto, una plantilla la más nueva compatible; una app de pago sin comprar sale `blocked`. Mientras se descargan, el hub sigue atendiendo (la caja cobra) y la importación espera su turno en la cola de cambios de apps (HUB-F19). (3) Un lote de importación con el nombre de la plantilla. (4) Las secciones en el orden del manifiesto (personas, ajustes, apps): solo `INSERT` de literales en sus propias tablas, nunca tablas `_*`, cada fila con un identificador nuevo derivado del hub destino; la única excepción es el `UPDATE` de la retirada de marcadores de abajo. (5) Roles, permisos y automatizaciones (HUB-F237). (6) Archivos al gestor, por lotes de 40 y 25 MiB con reintentos, en la carpeta que nombre cada ruta: solo se comprueba que no se salga de `media/`, sin política de carpetas ni filtro por finalidad. (7) El certificado nunca se aplica: queda `pending` y se sube a mano, porque su contraseña no viaja; en una plantilla, `ignored`. En una tabla que la app declara como objeto único (su semilla se guarda por el hub entero, p. ej. la semana de Horarios), lo que hubiera antes —sembrado, escrito por el negocio o traído por otra plantilla— se marca como borrado (apuntado en el lote) en cuanto entra al menos una fila del fichero, también en la copia propia; el informe de la sección no lo dice. El arranque de un hub nuevo ya no importa ninguna plantilla.
Si falla: una sección fallida se anota y el resto sigue; una app que no se instala deja `failed` su sección («módulo no instalado»).
Implicados: INVENTORY-F12, SCHEDULES-F12, HUB_SHELL-F26, HUB_SHELL-F177, REC_ALTA-F08, SAAS_PUBLIC-F16
Pendiente de enlazar: blueprints — catálogo de arranque que sustituye la semana de Horarios
QA: BD-01, qa-hub §4

### HUB-F236 Qué deja entrar el hub según de quién es el fichero
Estado: parcial — «es mi propia copia» se decide solo con el `hub_id` que el propio fichero declara, y ese identificador lo ve cualquiera sin sesión en `GET /api/hub/context`: un zip fabricado con él pasa por copia propia y trae personas con `pin_hash`, ajustes sin validar, permisos de módulo y automatizaciones encendidas con sus permisos. Hace falta que un administrador del propio hub suba el fichero; no es una puerta anónima
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub compara el origen del manifiesto con su propio identificador; un origen vacío nunca coincide.
2. Aplica a cada sección la regla de abajo.
Entra: el manifiesto y la selección.
Sale: nunca entran los datos de sistema (`_*`). Una plantilla descarta personas y datos fiscales aunque estén marcados. En un fichero que no es la copia propia se descartan: las personas, de los ajustes todo lo que no sea configuración (queda `PartiallyApplied` con `settings_not_portable` y el número de filas), la numeración de facturas y su libro (`numbering_not_portable`), los datos de apps ligados a la instalación como la cadena fiscal (`installation_bound_data`), y los permisos de módulo y de automatizaciones. Una fila de una tabla que la app instalada ya no tiene se salta (`table_gone_in_installed_version`) sin perder el resto. Se aplica la regla por el manifiesto, no por la casilla. El sha256 se comprueba contra el propio manifiesto (prueba que el zip no se corrompió, no de dónde viene), se exige sesión de administrador y el servidor no pide otra confirmación. En la copia propia los ajustes se escriben sin pasar por la validación ni las congelaciones de HUB-F221 y HUB-F223 (solo las claves sin fila).
En este mismo documento se apoya en: HUB-F300 (Resolver el perfil fiscal del hub al arrancar), HUB-F314 (Bloquear la cadena fiscal sin módulo que cumpla o con una instalación ajena).
Si falla: la sección descartada sale `Ignored` con su código y el número de filas.
Implicados: HUB_SHELL-F177, SAAS_PUBLIC-F41
QA: BD-01

### HUB-F237 Permisos, roles y automatizaciones que trae el fichero
Estado: hecho
Actor: sistema, administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. Tras las secciones de datos, el hub activa los roles del manifiesto.
2. Si es la copia propia, devuelve los permisos concedidos a cada app.
3. Guarda las automatizaciones por la misma puerta que la pantalla de automatizaciones.
4. Al terminar, la pantalla pregunta por los permisos que una plantilla no puede conceder.
Entra: `active_roles`, `capability_grants` y `flows` del manifiesto.
Sale: un rol que ninguna app declara, o uno base o de administración, se rechaza (`roles_not_activatable`). Los permisos de una plantilla se descartan siempre (`capability_grants_not_portable`); en la copia propia se vuelven a conceder los que la app instalada declara (`capabilities_not_grantable` para el resto). Cada automatización entra apagada, con una copia de sus permisos solo si es la copia propia, y se enciende al final si todos volvieron; si no, queda en pausa: `flow_grants_not_portable` si el fichero no es la copia propia, `flows_paused_without_grants` si lo es y algún permiso no volvió. Un documento que la pantalla rechazaría se cuenta y no entra (`flows_not_restorable`). El mismo nombre y documento ya vivos no se duplican; nunca se borra lo creado después. Los secretos no viajan. Estas tres piezas se aplican aunque ninguna casilla las nombre.
En este mismo documento se apoya en: HUB-F80 (Crear una automatización), HUB-F98 (Conceder, limitar y retirar los permisos de una automatización).
Si falla: un fallo de base de datos sale `Failed`, no como descarte.
Implicados: HUB_SHELL-F169, HUB_SHELL-F177, REC_ALTA-F08
QA: BD-01

### HUB-F238 Volver a importar lo mismo
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
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
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. Al terminar, la pantalla pinta una línea por sección: aplicada, omitida, descartada, parcial o fallida.
2. Si se sale de la pantalla, al volver a Ajustes › Datos y copias recupera el último informe.
Entra: el resultado de la importación.
Sale: una fila por sección con su estado, el motivo estable y las filas descartadas; más apps instaladas (`installed`, `already_installed`, `failed`, `blocked`, versión pedida si se sustituyó), archivos copiados y fallidos, estado del certificado y el origen (plantilla y versión, o fichero local). Se guarda por lote y se borra al deshacerlo.
Si falla: si no se puede guardar, la importación vale y solo se pierde esta vista.
Implicados: INVENTORY-F12, HUB_SHELL-F26, HUB_SHELL-F39, HUB_SHELL-F178, HUB_SHELL-F179, REC_ALTA-F08
QA: BD-01

### HUB-F240 Reintentar lo que falló en una importación
Estado: parcial — solo las importaciones de plantilla del catálogo; una de fichero local se rechaza
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Importar
Pasos:
1. Tras un informe parcial, el administrador pulsa reintentar.
2. El hub vuelve a bajar la misma plantilla y aplica solo lo fallido.
3. Sale un informe nuevo.
Entra: el lote del informe.
Sale: reaplica solo secciones `Failed`, apps `failed` o `blocked` y archivos que fallaron. Se niega si el catálogo ya sirve otra versión. Si no queda nada, responde que no hay nada que reintentar.
Si falla: `import_origin_not_retryable`, `import_retry_version_unavailable`, `import_retry_batch_not_found`.
Implicados: HUB_SHELL-F179, REC_ALTA-F08
QA: ninguno

### HUB-F241 Deshacer una importación
Estado: parcial — solo quita filas con `id`; los ajustes y las tablas de vínculo no se revierten
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Restablecer
Pasos:
1. El administrador elige una importación de la lista y la deshace.
2. El hub borra las filas que trajo.
Entra: el lote.
Sale: se borran exactamente las filas registradas, en una transacción, sin tocar lo creado después; vuelven los marcadores sembrados que el lote retiró, si nadie escribió ahí. La lista avisa solo de las tablas de objeto único (p. ej. el horario) en las que el negocio escribió después; una fila importada que se editó después se borra igual al deshacer. Deshacer dos veces, o un lote ajeno, no hace nada.
Si falla: si el borrado revierte, el lote sigue.
Implicados: HUB_SHELL-F180
QA: ninguno

### HUB-F242 Restablecer el hub
Estado: parcial — las secciones «archivos» y «datos fiscales» se aceptan pero no borran nada (solo bloquean si ya se emitió); el borrado de personas deja su perfil y preferencias; el servidor no pide ninguna confirmación (la razón social la pide la pantalla)
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Datos y copias › Restablecer
Pasos:
1. El administrador abre Restablecer y ve cada sección con su número de filas y sus bloqueos.
2. Marca solo lo necesario y confirma en pantalla escribiendo la razón social del negocio (lo pide la pantalla, no el servidor).
3. Lee el informe.
Entra: la selección (ajustes, personas, roles, cola de impresión, apps); todo apagado por defecto.
Sale: borrado duro, acotado al hub, en una sola transacción, en orden inverso de claves foráneas; las filas que sembró la app sobreviven. Las personas se borran menos quien ejecuta (se identifica por su sesión, nunca por el cuerpo de la petición). La cola de impresión se vacía; las impresoras emparejadas no. Si el hub ya emitió registros fiscales (sello del primer registro o facturas remitidas), Verifactu, Facturas y Ventas y los datos fiscales quedan bloqueados (RD 1007/2023) y el servidor lo rechaza con 409 aunque el cliente lo fuerce. El plan no muestra las secciones de archivos ni de datos fiscales. No toca historial de avisos, automatizaciones, permisos de módulo, certificado, perfil fiscal, llaves de API ni dispositivos de confianza; las sesiones, perfiles y preferencias de las personas borradas se quedan. La petición no lleva ningún token de confirmación.
Si falla: 409 con el motivo y «No se ha borrado nada»; si la transacción falla, tampoco se borra nada, pero sale también 409, indistinguible del bloqueo legal.
Implicados: HUB_SHELL-F181
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

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Ajustes de negocio con validación y auditoría de autor | hecho (sin historial de valores) | HUB-F221 |
| Zona horaria del negocio declarada o deducida | hecho | HUB-F227 |
| Moneda con decimales | hecho | HUB-F226 |
| Copia de seguridad y plantilla | parcial (errores tragados, certificado en plantilla) | HUB-F230, HUB-F231 |
| Importar con informe por sección, reintento y deshacer | parcial | HUB-F235, HUB-F239 a HUB-F241 |
| Restablecer por secciones con bloqueo fiscal | parcial | HUB-F242 |

## Datos: de quién es cada dato

De esta área (las tablas de la segunda mitad, en
[archivos-y-privacidad.md](archivos-y-privacidad.md)):

- `hub_settings`: 20 claves. Contiene el correo y el teléfono de `notify_allowed_recipients` y la
  identidad del negocio, que puede ser una persona física si es autónomo. Las claves del PIN y
  `api_docs_enabled` son del área de acceso, pero se guardan por esta puerta (HUB-F221).
- `_hub_import_batch`, `_hub_import_row`, `_hub_import_retired_row` y `_hub_import_report`: los lotes
  de importación, sus filas, lo que retiraron y su informe (HUB-F235 a HUB-F241).
- `_hub_meta`: la marca de la unidad del dinero (`money_unit`, HUB-F243), entre otras claves de
  otras áreas.
- `GET /api/hub/context` expone sin sesión el nombre y el rol de cada persona con PIN, para la rejilla
  de acceso, y el identificador del hub (HUB-F220).
- Los datos personales de los clientes viven en cada módulo, no en el hub.

## Reglas que no se rompen

- Un lote de ajustes se valida entero antes de escribir (`settings::set_many`).
- El NIF se congela con el primer registro fiscal y el país al activar el perfil fiscal (HUB-F223).
- Objetivo, hoy sin cumplir del todo (HUB-F231): una plantilla no lleva personas, datos fiscales,
  permisos ni automatizaciones. Hoy el servidor mete el certificado propio si «datos fiscales» está
  marcado y «archivos» copia las carpetas de las apps (los XML de Verifactu). Las identidades solo
  deben entrar en la copia propia, que hoy se decide por el `hub_id` que declara el propio fichero
  (HUB-F236, dudas).
- Las secciones de datos del import solo hacen `INSERT` de literales en las tablas de su sección y
  nunca tocan tablas `_*`. Excepciones: retira (borrado lógico) el contenido previo de las tablas de
  objeto único, y sube los archivos del zip a la carpeta que nombren, sin la política de carpetas.
- Restablecer está acotado por `hub_id`, es una transacción y no borra lo fiscal si ya se emitió.

## Lo que NO hace, a propósito

- No avisa a los módulos de que un ajuste cambió.
- No importa una plantilla al arrancar un hub nuevo (retirado). Sí ejecuta, si el despliegue lo pasa,
  el SQL de `HUB_SEED_SQL` sin la validación del import (HUB-F255).
- No guarda la contraseña del certificado en un fichero de exportación ni lo aplica automáticamente.

## Dudas abiertas

- Cómo decidir que un fichero es la copia propia sin fiarse de su manifiesto (firma del hub o prueba
  de posesión) (HUB-F236).
- Si la región debe congelarse también tras salir a producción (HUB-F223).
- Si el servidor debe pedir una confirmación para restablecer (hoy solo la pantalla) (HUB-F242).
- Si el fichero de exportación debe llevar una marca de unidad de dinero (HUB-F230, HUB-F243).

## Fuentes contrastadas

- `architecture/hub/settings.md` dice que `timezone` está pendiente de código en una nota y como
  implementada en otra; el código la tiene (`settings.rs`) (HUB-F227).
- `architecture/hub/export-import.md` está como «contrato propuesto, fases pendientes»; todo está
  implementado.
- El comentario de `server/export_import.rs` habla de un import «de arranque»; no tiene llamador
  (`boot.rs` lo retiró).
- El manual (09) dice que Restablecer pide escribir el nombre del negocio; lo que pide la pantalla es
  la razón social, y el servidor no pide nada (HUB-F242).
- El manual (08) lista la zona horaria como editable; el hub solo la deduce salvo que se declare
  (HUB-F227).
- INVENTORY-F09/F11: la multiplicación ×100 y ×10⁶ al reimportar no sale del hub: exportar, importar y
  `money_backfill` mueven los números tal cual; sale del CSV de la lista de productos (HUB-F238).
