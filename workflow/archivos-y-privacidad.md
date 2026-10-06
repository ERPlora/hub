# WORKFLOW — Hub (servidor) · Negocio y datos: archivos, privacidad y retención

Prefijo: HUB

> Área «Negocio y datos» del servidor del hub, segunda mitad (`crates/runtime`: `module_storage`,
> `erasure`, `retention`, `activity_log`; `crates/server`: `media`, `module_storage`): los archivos
> del negocio y de las apps, el borrado de los datos de una persona, la poda del historial, el
> registro de actividad que viaja en el latido y la semilla SQL del arranque. Los ajustes, las
> copias, la importación y restablecer están en [negocio-y-datos.md](negocio-y-datos.md), donde
> está también lo que vale para toda el área.

## Referencia adoptada

Para el borrado de una persona, el patrón de las plataformas de referencia: un
único aviso de borrado al que responde toda app (Shopify `customers/redact`, Odoo). RGPD arts. 5.1.c,
5.1.e y 17; retención de 4 años por LGT art. 66 para los recibos de autorización.

## Flujos

### HUB-F245 Ver y descargar archivos
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: HUB_SHELL: Archivos
Pasos:
1. La persona abre **Archivos** y navega por carpetas.
2. Abre un archivo en el visor o lo descarga.
Entra: la carpeta o la ruta; sesión de usuario de cualquier perfil. Una llave de API no entra.
Sale: el listado (carpetas, ficheros, cuota y qué acciones permite cada carpeta) y los bytes, que el hub pide al almacenamiento de erplora.com y entrega (tope de 25 MiB, 8 descargas a la vez). Para que una imagen del TPV se cargue sin cabecera, el hub da una cookie de solo lectura (`erplora_media`, `HttpOnly`, `Secure`, `SameSite=Strict`, solo para la puerta de lectura), que pasa por la misma regla. Leer sigue la regla de las carpetas (hub#2495): las del propio hub (las que empiezan por `_`: `_logs`, el registro de peticiones; `_system`, la actividad) y todo el árbol de las apps (`modules`, donde VeriFactu guarda los XML enviados a Hacienda con el NIF y el nombre de los clientes) solo las lee el propietario o un administrador (permiso `hub.administer`); cualquier otra carpeta del negocio (fotos de producto, cabeceras de WhatsApp, lo que sube una persona) la lee cualquier sesión. A quien no administra, el árbol del listado ni siquiera le nombra esas carpetas. Ninguna app declara hoy quién más puede leer sus archivos. El alcance es el negocio propio.
Si falla: hub sin credencial de máquina o nube caída, 424 con código; sin sesión, 401; quien no administra pide una carpeta o un archivo del hub o de una app (también escrito con `..`, `.` o `\`), 403 `forbidden`, antes de pedir nada a erplora.com.
Implicados: HUB_SHELL-F130, HUB_SHELL-F132, WHATSAPP_INBOX-F06, SAAS_DASHBOARD-F67, SAAS_DASHBOARD-F68
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
Implicados: HUB_SHELL-F131, HUB_SHELL-F133, HUB_SHELL-F134, SAAS_DASHBOARD-F67
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
Implicados: VERIFACTU-F15
QA: ninguno

### HUB-F248 Borrar los datos de una persona: el aviso único
Estado: parcial — el aviso lo emite Clientes y solo lo escuchan WhatsApp, Servicios y el hub; Citas, Reservas y Reservas online no; el motivo escrito por el administrador queda en el propio aviso durante 90 días
Actor: administrador, sistema
Pantalla: CUSTOMERS: Ficha de cliente
Pasos:
1. El administrador pulsa **Borrar datos personales** en la ficha (flujo de Clientes).
2. Clientes sustituye los datos de la ficha y publica `customer.anonymized`.
3. El hub entrega ese aviso a quien lo escucha y vacía su propio historial (HUB-F249).
Entra: el aviso `<sujeto>.anonymized` con su `<sujeto>_id` (de Clientes: `customer_id` y `reason`, hasta 500 caracteres).
Sale: el contrato es solo un nombre: el hub reconoce cualquier evento que acabe en `.anonymized` con el identificador del sujeto como cadena y no nombra a ningún módulo. Cada módulo que guarda algo de la persona se suscribe a ese aviso y borra lo suyo (HUB-F250); lo que no lo hace, se queda. Es idempotente: repetirlo no cambia nada. Solo vacía el historial la app **dueña** del dato (hub#2485): el identificador tiene que tener la forma de los que genera el hub y ser una fila de una tabla de la app que emite el aviso, en este negocio. Una app que nombra a una persona que no es suya, el núcleo o una app no instalada no vacían nada.
Si falla: si el identificador no es uno que genera el hub (`erasure.invalid_subject_id`) o no es de la app que emite (`erasure.subject_not_owned`), el aviso no se entrega a nadie ni vacía nada, se reintenta y acaba en «Eventos caídos» con ese código, donde lo ve una persona. Si el vaciado del hub falla, el aviso se difiere y se reintenta con espera creciente hasta 8 veces; después queda atascado (dead-letter) hasta que alguien lo reintente. El identificador se busca como cadena entre comillas en cualquier punto del contenido, claves incluidas.
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
Sale: se vacían, sin borrar la fila: los avisos entregados o descartados cuyo contenido tiene el identificador como valor; las ejecuciones terminadas (hechas, fallidas, canceladas) que lo tocan en entrada, variables, paso o propuesta, o que nacieron de un aviso así; todos los pasos y propuestas de esas ejecuciones; y los avisos que esas ejecuciones encolaron (un recordatorio lleva el teléfono sin el identificador). No se tocan los avisos pendientes o atascados ni las ejecuciones vivas: conservan los datos hasta procesarse o hasta la retención de 90 días (HUB-F253). Se conserva la fila porque es el rastro de la trazabilidad. Solo este hub; reentrega sin efecto. Coste: un barrido de todo `_event_outbox` del hub y de las ejecuciones terminales por cada borrado. No toca la cola de impresión ni los localizadores públicos (`_public_claim`).
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
Sale: el hub garantiza entrega con reintentos, el vaciado de su historial (HUB-F249) y que ningún módulo puede tocar las tablas del núcleo. No garantiza que cada app escuche, ni vacía las tablas de una app. Hoy: WhatsApp vacía y cierra sus conversaciones unidas a la ficha; Servicios marca sus bonos; Nadie toca los XML de Verifactu del almacenamiento de archivos ni los localizadores públicos. Ventas y Facturas conservan su copia fiscal a propósito, y Verifactu conserva NIF y nombre del cliente en sus registros y XML porque la norma obliga a conservarlos.
Si falla: el aviso de esa app se reintenta como cualquier otro.
Implicados: CUSTOMERS-F16, RESERVATIONS-F22, WHATSAPP_INBOX-F11
QA: L-10, WA-06 (discrepa)

### HUB-F251 Borrar los datos de un número sin ficha
Estado: no hecho — la bandeja de WhatsApp borra sus conversaciones pero no emite ningún aviso `.anonymized` con un identificador que el hub pueda buscar: los mensajes y su número siguen 90 días en el historial del hub (hub#2474, hub#2477)
Actor: administrador
Pantalla: WHATSAPP_INBOX: Bandeja de entrada
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
Estado: no hecho — el hub solo desactiva a una persona (cierra sus sesiones); nombre, correo, la huella de su PIN, perfil y preferencias se quedan, y no hay vaciado en el historial
Actor: administrador
Pantalla: ninguna
Pasos:
1. El administrador da de baja a una persona del equipo.
2. El hub la marca inactiva y cierra sus sesiones.
Entra: la persona.
Sale: nada se borra ni se seudonimiza. La atribución («quién autorizó qué») conserva el identificador cuatro años y el lector resuelve el nombre.
En este mismo documento se apoya en: HUB-F149 (Dar de baja y reincorporar a una persona).
Si falla: no aplica.
Implicados: ninguno
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
En este mismo documento se apoya en: HUB-F54 (Ver la cola de avisos caídos), HUB-F55 (Reenviar un aviso caído), HUB-F56 (Reenviar todos los avisos caídos), HUB-F57 (Cerrar un aviso caído con motivo).
Si falla: se registra el aviso y la vuelta siguiente continúa.
Implicados: ninguno
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
Implicados: SAAS_DASHBOARD-F18, SAAS_DASHBOARD-F57
QA: ninguno

### HUB-F255 Aplicar la semilla SQL del despliegue al arrancar
Estado: parcial — el SQL se ejecuta sin la validación del import (cualquier sentencia, no solo `INSERT` de literales en las tablas de una sección)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El despliegue pasa `HUB_SEED_SQL` (SQL inline) o `HUB_SEED_SQL_PATH` (fichero); si están los dos, gana el inline.
2. Al arrancar, tras las tablas de sistema, el hub ejecuta el SQL.
Entra: el SQL del despliegue, con el identificador del hub.
Sale: la configuración inicial escrita; la idempotencia la pone el propio SQL. Es configuración del despliegue, no una plantilla.
Si falla: un seed roto aborta el arranque con un error claro.
Implicados: SAAS_PUBLIC-F90
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Copiar un archivo | no hecho (ver «Lo que NO hace») | — |
| Aviso único de borrado de una persona | parcial | HUB-F248 a HUB-F250 |
| Borrado de una persona del equipo | no hecho | HUB-F252 |

## Datos: de quién es cada dato

- `_hub_activity_log`: una fila por actividad con `actor` (el identificador de la persona, o
  `apikey:<id>` si la orden llegó con una llave), tipo e instante; sin nombre. Viaja a erplora.com en
  el latido (HUB-F164) y se borra cuando erplora.com lo confirma (HUB-F254).
- El almacenamiento de archivos (en erplora.com): los XML de Verifactu con NIF y nombre de clientes,
  los adjuntos, las fotos de perfil y `_logs` (registro de peticiones); `_logs`, `_system` y los XML
  de Verifactu solo los lee el propietario o un administrador, el resto cualquier sesión (HUB-F245).
- Lo que el hub vacía al borrar a una persona: `_event_outbox`, `_flow_runs`, `_flow_run_steps` y
  `_flow_approvals` terminales (HUB-F249). Lo que **no** alcanza —la cola de impresión con el HTML de
  cada documento, sin purga; los localizadores públicos (`_public_claim`), sin purga de caducados;
  las fichas del personal (`hub_user` con la huella del PIN y de la placa, `hub_user_profile`,
  `hub_user_pref`, `hub_session`, `hub_trusted_device`)— está en el inventario de cada área:
  [avisos.md](avisos.md), [impresion.md](impresion.md), [modulos.md](modulos.md),
  [acceso.md](acceso.md), [whatsapp.md](whatsapp.md).
- Otros sitios con datos de personas que el borrado no mira y que conviene tener presentes:
  `_hub_certificate` (el certificado del negocio, con nombre y DNI si el titular es persona física) y
  `_hub_fiscal_profile.taxpayer_id` ([fiscal.md](fiscal.md)); los documentos de automatización con
  destinatarios, textos y URLs (`_flow`), sus secretos (`_flow_secrets`, credenciales de terceros) y
  sus esperas (`_flow_run_waits`) ([automatizaciones.md](automatizaciones.md)); `hub_api_key`
  ([personas-y-permisos.md](personas-y-permisos.md)).

## Reglas que no se rompen

- Leer archivos: las carpetas del propio hub (`_*`) y el árbol de las apps (`modules`) solo las lee
  el propietario o un administrador, y el árbol que recibe otra sesión no las nombra; las demás
  carpetas del negocio, cualquier sesión (HUB-F245).
- El borrado de una persona vacía (no borra la fila) y solo lo terminal; lo pendiente y lo atascado
  no se toca (HUB-F249).

## Lo que NO hace, a propósito

- No copia archivos ni da permiso de lectura por fichero; una app no puede abrir a su personal la
  lectura de su carpeta (solo el propietario o un administrador la lee).
- No purga la cola de impresión.
- Los 90 días de retención no son configurables (HUB-F253).

## Dudas abiertas

- Si el borrado de una persona del equipo debe seudonimizar su ficha está en las dudas comunes del
  índice (HUB-F252).

## Fuentes contrastadas

- WA-06 espera borrado lógico únicamente; la ficha ya vacía las conversaciones y el hub su historial
  (HUB-F248, HUB-F250).
