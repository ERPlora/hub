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
