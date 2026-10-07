# WORKFLOW — Hub (servidor) · Arranque, plan, nube y sistema

Prefijo: HUB

> Detalle del área «Acceso, personas y plan» (oleada 3): qué hace el hub al arrancar y qué anuncia a
> erplora.com, cómo comprueba su plan y qué pasa sin conexión, el latido de uso, cómo habla con
> erplora.com sin enseñar nunca su credencial al navegador, y lo que cuenta de su propia salud. Las
> pestañas de **Sistema** y la pantalla **Mi plan** son de `HUB_SHELL`. Técnico:
> `architecture/hub/auth.md` §2.3 y §2.10, `system-info.md`, `versioning.md`, `tenancy.md`.

## Referencia adoptada

**Plan firmado verificable sin conexión con gracia**, el patrón de licencia
offline (ADR-0154, `architecture/hub/auth.md` §2.10).

## Flujos

### HUB-F159 Arrancar el hub y avisar a erplora.com de que ya atiende
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El despliegue arranca el hub con su identificador de negocio, su base de datos y su credencial de máquina.
2. El hub pide a erplora.com la clave con la que comprobará los accesos con cuenta (hasta 5 s), aplica sus migraciones, apunta su versión, siembra al dueño de la cuenta y carga las apps instaladas (si una versión nueva no arranca, vuelve a la anterior).
3. Lanza sus tareas de fondo **antes** de abrir la puerta: avisos y automatizaciones cada segundo, la recogida de WhatsApp, la poda horaria, y la comprobación del plan con el latido (HUB-F162, HUB-F164), que sale al instante y luego cada 24 h; así que al arrancar sale un latido antes de que el hub escuche.
4. Abre la puerta y, en cuanto puede servir (HUB-F161), manda a erplora.com un único aviso de «ya atiendo» con casi el mismo resumen que el latido (sin la última actividad de las personas). Si erplora.com todavía tiene el hub como «desplegando», antes de contestar a ese aviso (o al latido) sondea varias veces seguidas su `/readyz` y solo con todas buenas lo da por activo: el hub espera con la petición abierta mientras tanto.
Entra: el identificador del negocio (`HUB_ID`), la base de datos (`HUB_DATABASE_URL`, obligatoria), la credencial de máquina (`HUB_CLOUD_API_TOKEN`), el correo del dueño (`HUB_OWNER_EMAIL`), la dirección de erplora.com (`HUB_CLOUD_API_URL`; sin ella, producción).
Sale: el hub sirviendo; la fila de versión en el historial (HUB-F167); el dueño marcado en su ficha; el aviso de arranque (`POST /api/v1/hub/device/heartbeat/`) con la credencial de máquina (`X-Api-Key` si es una llave `erpk_…`, `X-Hub-Token` si es la antigua; siempre con `X-Hub-Id`).
En este mismo documento se apoya en: HUB-F25 (Reponer las aplicaciones al arrancar y actualizarlas solas).
Si falla: sin base de datos o sin poder migrar, el hub no arranca. Si erplora.com no da la clave, arranca igual: el acceso con cuenta queda no disponible y el PIN funciona. Si el aviso de arranque falla o el hub tarda más de 5 minutos en estar listo, no se reintenta: erplora.com se entera por su propio sondeo. Una app que no se puede cargar queda apuntada como arranque incompleto (HUB-F161).
Implicados: REC_ALTA-F06, SAAS-F02, SAAS_AUTH-F26, SAAS_DASHBOARD-F27, SAAS_DASHBOARD-F28, SAAS_DASHBOARD-F29, SAAS_DASHBOARD-F55, SAAS_PUBLIC-F82, SAAS_PUBLIC-F90
QA: qa-hub-restaurant §7.00

### HUB-F160 No abrir nada hasta que el hub esté registrado
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un hub al que le falta su identificador real o su credencial de máquina arranca, pero no abre el negocio.
2. Cualquier petición (acceso con PIN, apps, ajustes, datos) recibe «este dispositivo debe registrarse».
3. Solo contestan la salud, el contexto público que lee la pantalla de acceso, los informes de política de contenido del navegador (`/csp-report/`) y la página pública del tique.
Entra: las dos mitades de la identidad de máquina; el hub de desarrollo está exento.
Sale: `428 machine_registration_required` para todo lo demás; el contexto público dice `registration_required`, nunca el secreto.
Si falla: la pantalla no tiene frase propia para este rechazo (sin confirmar qué pinta).
Implicados: HUB_SHELL-F12, REC_ALTA-F06, SAAS_DASHBOARD-F28
QA: ninguno

### HUB-F161 Decir si el hub está listo para servir
Estado: parcial — la respuesta, sin sesión, lleva la versión y los errores internos tal como salen (ERPlora/hub#2549), y queda retenida mientras se instala o actualiza una aplicación (ERPlora/hub#2508)
Actor: sistema
Pantalla: ninguna
Pasos:
1. El orquestador del servidor pregunta cada 30 s si el hub está listo. erplora.com también lo pregunta, varias veces seguidas, cuando recibe un aviso o un latido de un hub que todavía tiene como «desplegando» (HUB-F159), y mantiene abierta la petición del hub mientras lo hace.
2. El hub comprueba su base de datos, que la tabla de migraciones se pueda leer (no que haya alguna) y que todas las apps activas estén cargadas.
3. Si todo está bien contesta «listo»; si algo falla o no lo sabe, «no me mandes tráfico». Que el despliegue de una versión que no llega a «listo» se deshaga es cosa de la infraestructura (sin confirmar en este repo).
Entra: nada; sin sesión.
Sale: `/readyz` con el estado general, la versión y cada comprobación (la base de datos, las migraciones contadas, las apps que faltan o fallaron con su motivo): 200 solo si todo está bien, 503 en otro caso. `/healthz` solo dice que el proceso vive. Ninguna de las dos pregunta a erplora.com ni pasa por el freno de carga. Como `/readyz` no pide sesión, cualquiera lee la versión del hub y, si la base de datos falla, el texto crudo del error (ver huecos).
Si falla: un 503 deja el hub sin tráfico hasta que se recupere; el motivo queda en el cuerpo.
Implicados: HUB_SHELL-F13, HUB_SHELL-F14, REC_ALTA-F06, SAAS_DASHBOARD-F04, SAAS_DASHBOARD-F29, SAAS_DASHBOARD-F32
QA: ninguno

### HUB-F162 Comprobar el plan y qué apps puede usar el negocio
Estado: parcial — el plan vive solo en memoria (tras reiniciar sin conexión no se aplica ningún tope ni bloqueo, sin límite de tiempo); el corte de una app solo vale en las órdenes y consultas de la pantalla, no en la API pública, las tareas programadas, las automatizaciones ni los avisos; el tope de base de datos no se aplica; no existe «hub pausado»
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar y después cada 24 horas, el hub pide a erplora.com su permiso firmado: el plan, las apps permitidas con su nivel, el número de dispositivos, de personas y el tamaño de base de datos, y hasta cuándo vale sin conexión. erplora.com solo lista las apps publicadas y activas que tienen versión en el carril del hub: borrar o apagar una app en erplora.com la quita del permiso.
2. Comprueba la firma con la clave de erplora.com y se lo queda.
3. Una app que ya no está en el permiso (de pago o gratuita) deja de responder al momento en las órdenes y consultas de la pantalla, sin desinstalarse ni perder datos; su API pública, sus tareas programadas, sus automatizaciones y sus avisos siguen corriendo. Si erplora.com no contesta, las apps gratuitas siguen siempre; una de pago (o de un nivel desconocido, que cuenta como de pago) se corta solo tras tres fallos seguidos **y** pasada su gracia. Con una comprobación al arrancar y otra cada 24 h, el tercer fallo llega a las 72 h; la gracia la pone erplora.com en el permiso (5 días desde la emisión las de pago, `paid_grace_until`, y 7 la general, `grace_until`; el permiso vale 24 h): **a los 3 días sin conexión no se corta nada**, las de pago caen hacia el día 5 (o el 7) y las gratuitas nunca. Si el hub se reinicia durante el corte, vuelve a «todo abierto» y además el acceso con cuenta deja de estar disponible.
4. Los topes de personas y dispositivos se aplican al dar de alta (HUB-F147) y al entrar (HUB-F137).
Entra: el permiso firmado (`GET /api/v1/hub/device/entitlement/`) con la credencial de máquina; la clave pública (`/api/v1/auth/public-key/`).
Sale: el plan verificado en memoria; las órdenes y consultas de una app bloqueada contestan `module_entitlement_blocked` (402) y la vista del módulo dice «Suscripción necesaria». Con una sesión de PIN (sin credencial de erplora.com) la pantalla no conoce el plan y no pinta el bloqueo: la app aparece normal y sus peticiones fallan con el 402. La pantalla recibe el plan por una puerta propia con 60 s de memoria, que ante un «demasiadas peticiones» de erplora.com sigue sirviendo el último bueno. En el mismo turno se recoge el cupo de mensajes de WhatsApp del mes.
Si falla: sin ninguna comprobación buena todavía, no se bloquea nada (la autoridad es erplora.com). Una firma que no cuadra cuenta como fallo y se mantiene lo último bueno. Ante un fallo de red, la puerta de la pantalla contesta 424 y no sirve el último bueno (solo lo hace ante un «demasiadas peticiones»). Cada llamada a erplora.com tiene tope —10 s para conectar y 60 s en total— y cada paso del turno (el permiso, el latido, el cupo de WhatsApp, la entrega de la actividad) tiene además el suyo de 5 minutos: una comprobación que erplora.com deja sin contestar cuenta como fallo, el turno sigue sin ella y el siguiente sale a su hora.
Implicados: HUB_SHELL-F41, HUB_SHELL-F46, HUB_SHELL-F49, HUB_SHELL-F128, WHATSAPP_INBOX-F13, REC_ALTA-F15, REC_ALTA-F21, REC_ALTA-F22, SAAS-F11, SAAS_DASHBOARD-F53, SAAS_DASHBOARD-F100, SAAS_DASHBOARD-F111, SAAS_DASHBOARD-F113, SAAS_DASHBOARD-F116, SAAS_DASHBOARD-F188, SAAS_DASHBOARD-F189, SAAS_PUBLIC-F20, SAAS_PUBLIC-F23, SAAS_PUBLIC-F35, SAAS_PUBLIC-F36
QA: ninguno

### HUB-F163 Aplicar un cambio de plan al momento
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El dueño cambia de plan en erplora.com.
2. erplora.com manda al hub el permiso nuevo ya firmado. Es el único caso en que lo empuja: comprar o cancelar una app, o una suspensión, no empujan nada y llegan con la comprobación de cada 24 h (HUB-F162).
3. El hub comprueba la firma, que es para este negocio y que no es más viejo que el que tiene (el mismo momento de emisión se acepta), y lo aplica sin esperar a la comprobación diaria ni a un reinicio.
Entra: el permiso firmado; no hace falta sesión ni llave: la firma es la prueba. Pasa por la barrera de registro (HUB-F160) y por un freno de 5 rechazos por dirección (sin cabecera de proxy, todos comparten la misma clave).
Sale: el plan nuevo en memoria; las apps y topes cambian desde la siguiente petición.
Si falla: sin permiso, `entitlement_token_missing`; firma inválida, `entitlement_token_invalid`; de otro negocio, `entitlement_wrong_hub`; más viejo que el vigente, `entitlement_stale`; sin clave para comprobar, `entitlement_key_unavailable`; demasiados rechazos seguidos, `entitlement_push_throttled` (429); estado interno ilegible, `entitlement_state_unavailable` (500). En todos los casos queda el anterior y la comprobación diaria lo corrige.
Implicados: REC_ALTA-F05, SAAS_DASHBOARD-F40, SAAS_DASHBOARD-F54, SAAS_DASHBOARD-F95, SAAS_DASHBOARD-F96
QA: ninguno

### HUB-F164 Mandar el latido diario de uso a erplora.com
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. En el mismo turno diario de HUB-F162 (y al arrancar), el hub reúne un resumen de su día.
2. Lo manda a erplora.com con su credencial de máquina.
3. Si erplora.com confirma, borra de su cola la actividad que ya entregó; si no, la vuelve a mandar en el siguiente latido.
Entra: las ventas cobradas hoy y la última, los dispositivos con sesión, las personas activas, la última actividad, la versión del hub, lo que cada motor nativo debe aún a una autoridad (cuánto y desde cuándo), la vía de envío fiscal, la CPU y la memoria.
Sale: el latido (`POST /api/v1/hub/device/heartbeat/`); la actividad del negocio (tipo, momento y el identificador interno de quien la hizo, nunca su nombre ni datos de clientes), como mucho 500 por latido y entregada al menos una vez mientras quepa en la cola: tras un corte largo la cola se recorta a 5000 y se pierde lo más viejo. El recuento de personas activas es el mismo que usa el tope de plazas.
Si falla: un latido fallido —también el que erplora.com deja sin contestar, que se da por fallido a los 60 s— queda en el registro y se repite en el siguiente turno con la misma marca de actividad, que solo se da por entregada cuando erplora.com confirma el latido; si la tabla de ventas no se puede leer, el dato se omite en vez de mandar un cero.
Implicados: REC_ALTA-F21, SAAS_DASHBOARD-F34, SAAS_DASHBOARD-F36, SAAS_DASHBOARD-F55, SAAS_DASHBOARD-F57
QA: ninguno

### HUB-F165 Ver el uso de recursos frente a los límites del plan
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Sistema › Plan y límites
Pasos:
1. El administrador abre **Sistema → Plan y límites** (o **Recursos**).
2. Ve el plan actual y, para memoria, CPU, base de datos, dispositivos y personas, lo usado frente al límite («{used} de {limit}», «Ilimitado», «n/d»).
3. En **Recursos** elige «3 h», «24 h» o «3 días» para ver la evolución.
4. Cerca o por encima del límite sale el aviso y la salida a ampliar el plan.
Entra: la sesión de administrador para el uso en vivo; cualquier sesión para la evolución, que el hub pide a erplora.com con su credencial.
Sale: nada guardado. El uso en vivo sale del contenedor y de la base de datos, con los límites del último plan verificado (sin plan, límites a 0 = ilimitado); la evolución la guarda erplora.com y el hub la pasa tal cual con 30 s de memoria.
Si falla: la memoria, la CPU y la base de datos que no se pudieron medir salen como no medidas («No hemos podido leerlo», «n/d»); en cambio sesiones, dispositivos y personas salen a **0** si su consulta falla. Si erplora.com no da la evolución, el hub contesta 424 con «no sé» para cada medida; un intervalo que no sea 3 h, 24 h o 3 días, `invalid_range` (400). Sin ser administrador, el uso en vivo responde 401.
Implicados: HUB_SHELL-F128, HUB_SHELL-F136, SAAS_DASHBOARD-F26, SAAS_DASHBOARD-F65, SAAS_DASHBOARD-F66
QA: ninguno

### HUB-F166 Ver el estado del sistema, sus registros y documentos
Estado: parcial — en el servidor de producción la CPU y la memoria solo dan el porcentaje (sin cifras ni historial) y los documentos salen sin enlace para abrirlos
Actor: administrador
Pantalla: HUB_SHELL: Sistema
Pasos:
1. El dueño o un administrador abre **Sistema**.
2. Ve el uso de CPU y memoria, la base de datos y sus conexiones, los últimos 50 avisos entre apps como **Registros** (error, aviso o información). La pantalla ya no enseña los documentos guardados en la nube, aunque el servidor los sigue pidiendo.
Entra: la sesión de dueño o administrador (no una llave), la misma puerta que la cola de avisos caídos (HUB-F54): el último error de un aviso puede llevar el NIF y el nombre de un cliente (el rechazo de la AEAT). Sin sesión, 401; cualquier otro rol, 403 `forbidden` sin datos. Los documentos y el espacio usado los pide el hub a erplora.com con su credencial.
Sale: nada guardado.
En este mismo documento se apoya en: HUB-F50 (Dejar un aviso en la cola al guardar una orden), HUB-F51 (Entregar un aviso a los módulos que lo escuchan), HUB-F52 (Reintentar un aviso que un módulo no pudo procesar).
Si falla: «No se pudo consultar el sistema» con «Reintentar»; si erplora.com no da los documentos, la lista sale vacía.
Implicados: HUB_SHELL-F114, HUB_SHELL-F118, HUB_SHELL-F135, HUB_SHELL-F136, HUB_SHELL-F144, SAAS_DASHBOARD-F69
QA: ninguno

### HUB-F167 Saber qué versión corre y qué se le ha actualizado
Estado: parcial — el historial no guarda quién pulsó «Actualizar», y la versión no tiene puerta propia (va en la salud, en Sistema y en el latido)
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Sistema › Actualizaciones
Pasos:
1. Cada arranque, el hub compara su versión con la última apuntada: si cambió, apunta el salto (o la vuelta atrás); si es la misma, nada.
2. Cada actualización de una app (sola al arrancar o con el botón «Actualizar» de un administrador) apunta de qué versión a cuál, o que volvió a la anterior porque la nueva no arrancó, o, si fallaron la nueva y la vuelta atrás, que la app quedó sin funcionar.
3. En **Sistema → Actualizaciones** se ve «Vas por la {version}» y «Qué te hemos actualizado», agrupado por días.
Entra: la versión del hub, fijada al compilar; las actualizaciones de apps.
Sale: el historial (`_update_history`), sin datos personales. La pantalla lee como mucho 20 entradas de los últimos 90 días, con el nombre de cada app en su idioma; el motivo técnico de un fallo viaja pero no se pinta.
En este mismo documento se apoya en: HUB-F23 (Actualizar una aplicación), HUB-F25 (Reponer las aplicaciones al arrancar y actualizarlas solas).
Si falla: sin cambios, «No te hemos cambiado nada»; una vuelta atrás, «Volvió a la {version}: la nueva no arrancó»; una app perdida, «Esta app no está funcionando: estamos en ello». Si no se puede apuntar la versión al arrancar, queda en el registro y el hub arranca igual.
Implicados: HUB_SHELL-F20, HUB_SHELL-F142, SAAS_DASHBOARD-F31
QA: qa-hub-restaurant §7.00

### HUB-F168 Hablar con erplora.com en nombre del negocio
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una pantalla del hub necesita algo que solo sabe erplora.com: el catálogo de apps, una plantilla de negocio, la versión publicada de la app instalada, el plan del asistente, la conexión de WhatsApp, las series de uso o dar de alta a un miembro.
2. Lo pide al hub, nunca a erplora.com directamente.
3. El hub comprueba la sesión, añade su credencial de máquina y reenvía la petición a su propia dirección de erplora.com.
4. Devuelve la respuesta, o un motivo que la pantalla sabe traducir.
Entra: la sesión de la persona (también para la versión publicada de la app, aunque esa llamada a erplora.com sale sin credencial); la credencial de máquina, que solo vive en el servidor.
Sale: la respuesta de erplora.com. La credencial del hub y la de la persona solo viajan a erplora.com y a los anfitriones de confianza declarados en el despliegue; a cualquier otro destino se llama sin ellas. Las facturas, suscripciones y el estado de suscripción de una app los pide la pantalla a erplora.com con la credencial de la persona, sin pasar por aquí.
En este mismo documento se apoya en: HUB-F19 (Instalar una aplicación del catálogo), HUB-F24 (Consultar qué actualizaciones y versiones hay), HUB-F260 (Conectar el número de WhatsApp del negocio), HUB-F261 (Saber qué número está conectado y si hay que reconectarlo), HUB-F277 (Ver el plan del asistente y lo que queda del mes).
Si falla: erplora.com no contesta, «Tu hub no ha podido llegar a erplora.com. Revisa la conexión e inténtalo de nuevo.» (`cloud_unreachable`, 424); contesta con error, «ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.» (`cloud_rejected`); hub sin conectar, «Este hub todavía no está conectado con ERPlora.». El cuerpo de un error 5xx de erplora.com no llega al navegador, pero los 4xx se pasan tal cual, con su texto en inglés. Cada llamada tiene tope: 10 s para conectar y 60 s en total (también el catálogo), y pasado el tope la pantalla recibe el mismo «no ha podido llegar»; el chat del asistente y las subidas y bajadas de archivos tienen 15 minutos. Instalar, actualizar, listar versiones y pedir una instalación cortan además a los 30 s sin recibir nada.
Implicados: SAAS-F02, SAAS_ASSISTANT-F01, SAAS_ASSISTANT-F19, SAAS_AUTH-F27, SAAS_DASHBOARD-F50, SAAS_PUBLIC-F12
QA: ninguno

### HUB-F169 Dejar que un motor del hub llame a erplora.com con la identidad del negocio
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un motor propio del hub (el fiscal) necesita preguntar algo a erplora.com.
2. Dice el verbo (solo leer o enviar), la ruta y el contenido; el hub pone el destino y la credencial.
3. El hub rechaza cualquier ruta que intente salir de su propia dirección de erplora.com.
Entra: la petición del motor; la credencial de máquina.
Sale: la respuesta tal cual al motor. El contenido de la respuesta nunca se copia a un error ni al registro.
En este mismo documento se apoya en: HUB-F305 (Enviar la autorización de representación y seguir su estado), HUB-F306 (Pedir, recoger y renovar la conexión segura con la celda fiscal).
Si falla: una ruta que no es suya, `cloud_call.path_not_mine`; un fallo de red se devuelve al motor, que decide si reintenta.
Implicados: SAAS-F02
QA: ninguno

### HUB-F170 Rechazar trabajo cuando el hub está saturado
Estado: parcial — el aviso de saturación sale en español escrito en el servidor y la pantalla no tiene frase propia para él
Actor: sistema
Pantalla: ninguna
Pasos:
1. El hub atiende como mucho un número de peticiones a la vez (512 si el despliegue no dice otra cosa).
2. Si llega una más, la rechaza al momento en vez de ponerla en cola, para que lo que ya está en marcha termine.
3. La salud y «listo para servir» quedan fuera del límite.
Entra: cualquier petición; el tope `HUB_MAX_INFLIGHT_REQUESTS`.
Sale: `503 service_overloaded` con `Retry-After: 1`. No hay contador propio: queda en el registro de peticiones.
Si falla: un fallo interno de esta capa sale como 500 con su mensaje, nunca vacío.
Implicados: ninguno
QA: ninguno

### HUB-F171 Atender cada petición solo con los datos de su negocio
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada hub tiene su propia base de datos y su identificador, fijados por el despliegue.
2. Toda petición con sesión se resuelve contra ese identificador, nunca contra uno que mande quien llama.
3. Las personas, sesiones, dispositivos, llaves, ajustes y datos de las apps llevan el identificador del negocio en cada fila, y cada consulta lo filtra (la tabla interna `_hub_meta` no lo lleva: vive en la base de datos propia del negocio).
Entra: el identificador del despliegue (`HUB_ID`); la cabecera `X-Hub-Id` no decide nada salvo en el modo de desarrollo, aunque la que manda el navegador viaja tal cual a erplora.com en el pase de HUB-F142.
Sale: nada nuevo; la garantía de que un token, un PIN o un dispositivo de un negocio no abre otro aunque compartieran base de datos.
Si falla: sin `HUB_ID`, el hub toma el identificador de desarrollo y no se da por registrado (HUB-F160); con `HUB_ID` vacío y credencial, sí se da por registrado (ver huecos), y solo las filas de confianza de dispositivo se niegan a escribirse.
Implicados: SAAS_DASHBOARD-F50
QA: qa-hub-restaurant §6

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Plan firmado, gracia sin conexión, bloqueo de apps | parcial (memoria; tras reinicio sin topes; el corte no alcanza la API pública, tareas, automatizaciones ni avisos; con sesión de PIN la pantalla no pinta el bloqueo) | HUB-F162 |
| Cambio de plan aplicado al momento | hecho | HUB-F163 |
| Hub pausado | no hecho en el servidor | HUB-F162 |
| Tope de tamaño de base de datos | no hecho (solo se muestra) | HUB-F165 |
| Listo para servir / salud | hecho | HUB-F161 |
| Uso de recursos frente a límites | hecho | HUB-F165 |
| Versión e historial de actualizaciones | parcial (sin autor) | HUB-F167 |
| Freno de carga | parcial (sin texto traducido) | HUB-F170 |

## Datos: de quién es cada dato

Las tablas de toda el área están en [acceso.md](acceso.md). De erplora.com, leídos por su puerta
(HUB-F168): la credencial firmada de la persona (JWT con `hubs[]`), el plan firmado, la membresía e
invitación (`/api/v1/hub/device/members/`), las series de uso, los documentos, el catálogo y las
facturas (estas, desde la pantalla con la credencial de la persona). `_update_history` y `_hub_meta`
no guardan datos personales (el historial no tiene autor).

## Lo que NO hace, a propósito

- No persiste el plan verificado en base de datos: vive en memoria (HUB-F162).

## Dudas abiertas

- **Freno de carga**: ¿texto traducido para `service_overloaded`?
- El hub pausado y el plan tras un reinicio sin conexión están en las dudas comunes del índice.

## Fuentes contrastadas

- `architecture/hub/auth.md` §2.3 (tabla) dice que la máquina usa `X-Hub-Token`; el código manda
  `X-Api-Key` cuando la credencial es una llave `erpk_…` (`crates/cloud-client/src/lib.rs`).
- `architecture/hub/auth.md` §2.3 dice que el runtime aún manda `X-Webhook-Secret` para el M2M de
  fondo; no hay ningún uso de `Auth::Webhook` en el servidor ni en el runtime.
- `architecture/hub/auth.md` lista `bootstrap` y `enroll` entre los endpoints usados; el hub no los
  llama.
- `architecture/hub/auth.md` §2.10 dice «sin token válido ni cacheado no monta los módulos»; el código
  deja pasar todo mientras no haya una comprobación buena (`crates/server/src/entitlement.rs`)
  (HUB-F162).
- `architecture/hub/system-info.md` dice que no hay rama de ECS y que documentos y registros están
  pendientes; los dos existen. En Hetzner la CPU y la memoria solo traen el porcentaje y
  `documents[].url` es siempre nulo (HUB-F166).
- `architecture/hub/versioning.md` cita `GET /system`; la ruta es `/api/system`. El comentario de
  `crates/runtime/src/core_version.rs` dice que `/api/hub/context` publica la versión: no lo hace
  (HUB-F167).
- `crates/server/src/entitlement.rs` (comentario) dice que el límite de peticiones del SaaS es por IP;
  el documento dice que ahora es por hub.
- `crates/server/src/whatsapp_quota.rs` (comentario) dice que no hay vía SaaS→hub;
  `POST /api/entitlement/refresh` (HUB-F163) lo es.
- Manual `hand-book/hub/01`: «Pantalla de activación cuando el Hub no puede confirmar un acceso
  válido»; la pantalla no se alcanza (nadie pone ese estado en `apps/web/src/lib/entitlement.ts`)
  (HUB-F162).
- Manual `hand-book/hub/05` y `07` hablan de «Sistema > Plan»; la pestaña es «Plan y límites»
  (HUB-F165).
