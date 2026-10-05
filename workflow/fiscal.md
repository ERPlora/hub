# WORKFLOW — Hub (servidor) · Perfil fiscal

Prefijo: HUB

> La mitad del servidor que no es el motor: el perfil fiscal del negocio y su estado, el
> certificado, la vía de envío, la autorización de representación, la identidad de máquina ante la
> celda fiscal, el paso a producción y la regla «en producción, sin vía no se cobra». Escrito contra
> `origin/develop` (`c7d73b22`, 05/10/2026). Código: `crates/runtime/src/{fiscal,fiscal_profile,
> certificate,gateway_identity,producer_facts}.rs`, `crates/server/src/{gateway_enrolment,
> representation_grant}.rs`, las puertas fiscales de `crates/server/src/settings.rs` y las ramas
> fiscales del despachador (`crates/runtime/src/commands.rs`). El motor (huella, XML, envío) está en
> `crates/plugins/verifactu/WORKFLOW.md` (HUB_VERIFACTU). Las pantallas son del módulo VeriFactu
> (`VeriFactu: Configuración`, `VeriFactu: Ajustes`): el hub es país-agnóstico y no pinta ninguna.

## Flujos

### HUB-F300 Resolver el perfil fiscal del hub al arrancar
Estado: parcial — el estado «listo» (identidad, vía y un módulo que cumple el régimen) solo se recalcula al arrancar el hub: un negocio que sube su certificado o firma su conexión segura sigue «sin configurar» hasta el siguiente arranque, y uno que borra su certificado sigue «listo» (leído, sin ejecutar)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada vez que el hub arranca, con los módulos ya cargados, el núcleo lee el país del negocio y busca su régimen: España → VeriFactu; un país sin régimen no debe nada.
2. Un hub nuevo nace «sin configurar» (o «no exigible» fuera de España), con su número de instalación fijado al identificador del hub.
3. Mientras no está en producción, el perfil sigue al país, y pasa a «listo» si tiene NIF y razón social, una vía de envío (certificado propio activo o conexión segura firmada) y un módulo activo que cumple su régimen; si no, vuelve a «sin configurar».
4. Anota si el hub es de demostración (entonces no podrá pasar a producción), si sus filas las escribió otra instalación (lo marca para revisión) y qué avisos abren una cadena fiscal, aprendidos del módulo que cumple el régimen mientras está sano.
Entra: el país y la identidad del negocio (Ajustes › Negocio), el certificado y la conexión segura, los módulos montados y la marca de demostración del despliegue (`HUB_DEMO`).
Sale: el perfil fiscal del hub en la tabla de sistema `_hub_fiscal_profile` (país, régimen, estado, entorno, NIF congelado, fechas). El modo «bloqueado» no se guarda: se deduce en cada lectura (HUB-F314).
Si falla: un fallo al resolverlo no impide arrancar; se apunta en el registro del servidor y la siguiente lectura lo vuelve a calcular. Un hub que ya emitió nunca vuelve a «no exigible»; si su país pide otro régimen, se marca para revisión y no se adivina.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F01 (activar VeriFactu y la lista de puesta en marcha que lee si el hub tiene vía)
Pendiente de enlazar: hub — HUB, módulos y órdenes (lista de puesta en marcha `setup.status`, que usa la misma pregunta «¿tiene vía?»)
QA: BD-02, qa-hub §7

### HUB-F301 Saber dónde y por qué vía declara el hub
Estado: hecho
Actor: sistema, empleado, responsable, administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. Cualquier pantalla con sesión local pregunta al núcleo por la vía de envío: la vía (certificado propio o ERPlora), el estado de la autorización y su fecha, qué impide declarar ahora mismo (o nada), dónde se arregla y cuándo caduca el certificado propio.
2. El entorno (pruebas o producción), si puede pasar a producción y si ya declaró de verdad se leen por separado.
3. El estado del certificado dice si hay uno subido, quién y cuándo lo subió, si está en uso y cuál firma; nunca los bytes ni la contraseña.
Entra: el perfil fiscal, el certificado y la conexión segura, del núcleo; el módulo que cumple el régimen declara la ruta de su puesta en marcha.
Sale: nada; es consulta (`hub.fiscal.transmission`, `GET /api/fiscal/go-live`, `GET /api/business/certificate`). El estado de la autorización sale de la copia guardada, sin preguntar a la nube.
Si falla: un hub sin perfil todavía contesta vacío, nunca un estado inventado. Un módulo que pregunta por el certificado o por el entorno necesita el permiso «Certificado del negocio (firma fiscal)».
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F07 (el TPV avisa de que hoy no puede cobrar)
Pendiente de enlazar: verifactu — VERIFACTU-F04 (el interruptor enseña la vía actual) y VERIFACTU-F08 (entorno)
QA: qa-hub §7

### HUB-F302 Guardar o sustituir el certificado del negocio
Estado: parcial — no comprueba la contraseña ni que el fichero sea un certificado: uno inservible se guarda, el hub queda en «vía propia» y sus registros esperan en la cola sin salir; la caducidad se lee si se puede, pero no se enseña al subir
Actor: administrador
Pantalla: VeriFactu: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Mi certificado», el administrador elige el `.p12` o `.pfx`, escribe su contraseña y pulsa «Subir certificado».
2. El núcleo lo guarda cifrado con la clave maestra del despliegue, con quién y cuándo lo subió, qué es (sello de entidad o certificado de persona, leído del propio fichero) y cuándo caduca.
3. Subirlo es elegirlo: el certificado queda en uso aunque el anterior estuviera apagado. Si ya había uno, lo sustituye en la misma escritura; la cadena no cambia y los registros siguientes salen firmados con el nuevo.
4. El núcleo avisa en el momento al SaaS de la vía nueva.
Entra: el fichero en base64 y la contraseña, del administrador.
Sale: el certificado en la tabla de sistema `_hub_certificate`; el estado nuevo a la pantalla; un latido al SaaS con la vía (`announce_route_change`). Un hub de demostración también puede subir el suyo (lo separa de la AEAT real el entorno clavado a pruebas, HUB-F315).
Si falla: sin fichero, «falta pkcs12_b64» con el código `invalid_field`; sin la clave maestra del despliegue no se guarda nada en claro y se niega; quien no es administrador recibe la negativa de sesión; un módulo sin el permiso del certificado, la negativa del permiso. Si el aviso al SaaS falla, se queda para el latido diario.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F02 (subir el certificado propio) y VERIFACTU-F34 (renovarlo sin romper la cadena)
Pendiente de enlazar: saas — guardar la vía de envío que el hub anuncia en su latido
QA: qa-hub §7, qa-hub-restaurant §7.11

### HUB-F303 Borrar el certificado del negocio
Estado: parcial — se borra al primer intento también en producción, sin comprobar que la vía de ERPlora esté lista: un hub en producción sin autorización aprobada o sin conexión segura se queda sin vía y deja de cobrar (el interruptor de HUB-F304 sí lo impide)
Actor: administrador
Pantalla: VeriFactu: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Mi certificado», el administrador pulsa «Quitarlo».
2. El núcleo borra el certificado; desde ese momento la vía es la de ERPlora.
3. Avisa al SaaS de la vía nueva.
Entra: la orden del administrador.
Sale: el certificado borrado; los registros siguientes salen por la celda de ERPlora; el latido al SaaS.
Si falla: quien no es administrador o un módulo sin el permiso del certificado reciben la negativa. Un hub de demostración también puede borrarlo.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F03 (quitar el certificado propio)
Pendiente de enlazar: architecture — REC_FISCAL-F01 (antes de cobrar: el negocio puede facturar)
QA: qa-hub §7

### HUB-F304 Elegir la vía de envío: mi certificado o ERPlora
Estado: hecho
Actor: administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, el administrador enciende o apaga «Usar mi propio certificado». El certificado sigue guardado en los dos casos.
2. Encender exige un certificado subido.
3. Apagar en producción exige que ERPlora pueda declarar de verdad en su nombre: autorización aprobada y, después, conexión segura firmada. En pruebas se permite sin nada: los registros esperan hasta que haya vía.
4. Si se permite, el núcleo lo guarda y avisa al SaaS de la vía nueva.
Entra: encendido o apagado, del administrador; el perfil, la autorización y la conexión segura, del núcleo.
Sale: la vía cambiada (los registros siguientes salen por ella) y el latido al SaaS.
Si falla: encender sin certificado: `fiscal.own_certificate_not_uploaded`; apagar en producción sin autorización: `fiscal.no_representation_grant`; sin conexión segura: `fiscal.gateway_not_enrolled`; en todos, no cambia nada. Apagar sin certificado subido no hace nada. Las frases las pone la pantalla de VeriFactu.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F04 (elegir quién remite)
QA: qa-hub §7

### HUB-F305 Enviar la autorización de representación y seguir su estado
Estado: hecho
Actor: administrador, sistema
Pantalla: VeriFactu: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Lo remite ERPlora», el administrador pide el modelo oficial relleno con los datos del negocio y de quien firma; el hub lo trae del SaaS como PDF.
2. Sube el modelo firmado (PDF), la copia del DNI o NIE, la muestra de firma si es NIE y, si el negocio es una sociedad (NIF que empieza por letra de entidad), el justificante de representación; cada documento, menos de 10 MB.
3. El hub comprueba lo que falta antes de cruzar la red y reenvía los documentos al SaaS con la credencial de máquina; el estado pasa a «pendiente» hasta que una persona de ERPlora lo revisa.
4. Cada vez que se abre la pantalla, el hub pregunta al SaaS el estado (pendiente, vigente, rechazado, revocado o ninguno), el motivo de un rechazo y el historial de envíos, y guarda una copia del estado y su fecha en el perfil fiscal.
5. Además, cada hora, un hub en producción por la vía de ERPlora vuelve a preguntar solo: si ERPlora revoca o rechaza la autorización, el hub deja de cobrar sin que nadie abra la pantalla; si la vuelve a aprobar, vuelve a cobrar.
Entra: los datos del negocio y de quien firma y los documentos, del administrador; el estado, del SaaS.
Sale: la autorización en el SaaS para revisión; en el hub, solo el estado y su fecha (`_hub_fiscal_profile`); los documentos no se guardan en el hub ni salen en el registro del servidor.
Si falla: lo que falta sale con su código (`obligado_nif_required`, `signer_required`, `document_type_invalid`, `signed_document_required`, `signed_document_not_pdf`, `dni_copy_required`, `signature_sample_required`, `representation_proof_required`, `document_too_large`). Sin credencial de máquina, `hub_not_enrolled`; sin respuesta o con negativa del SaaS, `cloud_unreachable` o `cloud_rejected`, y la copia guardada no cambia.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F05 (firmar y subir la autorización) y VERIFACTU-F06 (volver a enviarla)
Pendiente de enlazar: saas — servir el modelo oficial, recibir los documentos, revisar y aprobar, devolver o revocar la autorización (Anexo I) y contestar su estado e historial
QA: qa-hub §7

### HUB-F306 Pedir, recoger y renovar la conexión segura con la celda fiscal
Estado: parcial — el hub no renueva solo ni avisa antes de que caduque (el aviso de «caduca pronto» es de la pantalla) y da por válida una conexión caducada; el servicio que recoge la firma no arranca si el hub arrancó sin credencial de máquina; borrar la identidad en producción no se impide y deja al hub sin vía
Actor: administrador, sistema
Pantalla: VeriFactu: Configuración
Pasos:
1. En **VeriFactu → Configuración**, bloque «Conexión segura con ERPlora», el administrador pulsa «Solicitar la conexión».
2. El hub crea su clave privada (nace en el hub, cifrada, y no sale nunca) y una solicitud de firma a nombre de este hub, y la presenta en el expediente del hub en el SaaS con su credencial de máquina.
3. Una persona de ERPlora la firma. Mientras tanto, el hub pregunta solo cada 2 minutos; «Comprobar el estado» pregunta en el momento. Cuando está firmada, instala el certificado: comprueba que es de su clave, de su nombre y que no ha caducado.
4. Para renovar se repite la solicitud con la misma clave; si la renovación llega sin la autoridad de confianza, reutiliza la guardada.
Entra: la orden del administrador; el certificado firmado, del SaaS.
Sale: la identidad de máquina en la tabla de sistema `_hub_gateway_identity`; con ella, el hub tiene vía por la celda (carril mutuo) y lo nota el estado «listo» del perfil en el siguiente arranque (HUB-F300).
Si falla: la respuesta dice el estado (`filed`, `awaiting_review`, `installed`, `rejected` con el motivo, `out_of_budget` si se pasó del presupuesto de 30 comprobaciones por hora) o un código de rechazo (`enrolment.no_machine_credential`, `enrolment.cloud_unreachable`, `enrolment.cloud_refused`, `enrolment.install_refused`…). Una solicitud rechazada no se vuelve a presentar sola. Sin la clave maestra del despliegue no se crea ninguna clave.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F07 (solicitar o renovar la conexión segura)
Pendiente de enlazar: saas — recibir la solicitud de firma del hub en su expediente, firmarla o devolverla con motivo, y entregar el certificado con la autoridad de confianza
Pendiente de enlazar: verifactu-gateway — aceptar la conexión del hub con su identidad de máquina (carril mutuo)
QA: qa-hub §7

### HUB-F307 Pasar a producción
Estado: parcial — la comprobación de «listo» usa el estado calculado en el último arranque (HUB-F300): tras configurar sin reiniciar se niega con `fiscal.not_ready`, y con un estado viejo puede dejar pasar a un hub que ya no tiene vía (que luego no podrá cobrar, HUB-F313)
Actor: administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, el administrador pulsa «Pasar a producción» y confirma.
2. El núcleo comprueba, en este orden: que el hub no haya cesado; que no sea de demostración; que, si declara por la vía de ERPlora, la autorización esté aprobada; que el perfil esté «listo»; y que el certificado propio que firma no haya caducado.
3. Si todo está, el hub pasa a producción: congela el NIF del negocio como el de la cadena y anota el momento. Pulsarlo estando ya en producción no hace nada.
4. Los registros nuevos nacen en la cadena de producción; los que nacieron en pruebas siguen yendo a pruebas.
Entra: el perfil fiscal, la vía, la autorización y la caducidad del certificado, del núcleo.
Sale: el perfil en producción (`POST /api/fiscal/go-live`). Desde ese momento el motor envía a la AEAT real y el NIF de Ajustes › Negocio no se puede cambiar una vez emitido.
Si falla: `fiscal.hub_closed`, `fiscal.go_live_forbidden` (demostración), `fiscal.no_representation_grant`, `fiscal.not_ready` o `fiscal.own_certificate_expired`, y el hub sigue en pruebas. Solo el administrador; un módulo sin el permiso del certificado no puede pedirlo.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F08 (pasar a producción)
Pendiente de enlazar: architecture — REC_FISCAL-F14 (de pruebas a producción sin perder ningún tique)
QA: L-04, BD-02, qa-hub §7

### HUB-F308 Volver a pruebas mientras no se haya declarado nada en producción
Estado: parcial — la vuelta se cierra con el sello «primer registro en producción», que solo pone una orden declarativa que declara el aviso que abre la cadena; la emisión de facturas de Facturación es un manejador que devuelve ese aviso y no lo pone, así que tras vender en producción se puede seguir volviendo a pruebas hasta la primera rectificativa, y las ventas siguientes irían a la AEAT de pruebas (leído, sin ejecutar)
Actor: administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, con el hub en producción y sin nada declarado de verdad, el administrador pulsa «Volver a pruebas» y confirma.
2. El núcleo vuelve el perfil a pruebas y a «listo», y borra el momento del paso a producción.
3. Lo que **debe** cerrar la vuelta es la primera transacción que abre una cadena fiscal en producción, aunque su registro no haya salido aún. Hoy el sello solo lo pone una orden declarativa (la rectificativa de Facturación); la factura de cada venta no lo pone (ver Estado).
Entra: el sello «primer registro en producción» del perfil.
Sale: el perfil en pruebas (`DELETE /api/fiscal/go-live`); los registros que nacieron en producción siguen yendo a producción.
Si falla: con el sello puesto, `fiscal.already_emitted` («…create another hub») y no cambia nada. Estando ya en pruebas no hace nada.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F09 (volver a pruebas)
Pendiente de enlazar: architecture — REC_FISCAL-F14 (se puede volver hasta la primera venta en producción)
QA: L-04

### HUB-F309 Cerrar el perfil fiscal de un negocio que cesa
Estado: no hecho — el núcleo sabe cerrar el perfil, pero ninguna puerta, pantalla ni orden lo llama
Actor: administrador
Pantalla: ninguna
Pasos:
1. Lo que existe en el núcleo: cerrar el perfil desde cualquier estado, con el nombre de quien lo decide; es irreversible y cerrarlo dos veces no mueve la fecha.
2. Cerrado, el hub sigue consultando y exportando, pero niega toda escritura salvo las del propio hub y las del módulo que cumple el régimen (para vaciar lo pendiente), y «Pasar a producción» lo niega con `fiscal.hub_closed`.
3. No envía nada a ninguna parte: el cese ante Hacienda es la baja censal del negocio.
Entra: quién lo decide.
Sale: el perfil cerrado, con fecha y autor.
Si falla: sin autor, `fiscal.close_needs_actor`.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F33 (cesar la actividad)
QA: ninguno

### HUB-F310 Servir la declaración responsable y los datos del productor
Estado: parcial — los datos del productor viven solo en memoria y llegan con el latido al SaaS del arranque, el diario y el de cada cambio de vía: si el del arranque falla, pueden faltar hasta un día y mientras tanto no sale ningún registro
Actor: sistema, empleado, responsable, administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. Al arrancar, cada día y tras cada cambio de vía, el hub manda su latido al SaaS y recibe los datos del productor del software (razón social y NIF de ERPlora, nombre y código del sistema, tipos de uso e indicador de varios obligados) y la referencia de la declaración responsable que cubre esta versión.
2. Cualquier sesión puede pedir la declaración: los datos del productor, la versión que está corriendo, el número de instalación (el identificador del hub), el enlace a la declaración y su versión.
3. El motor usa esos mismos datos en cada registro.
Entra: el bloque del productor y la referencia de la declaración, del SaaS.
Sale: la declaración (`GET /api/system/declaration`) con los mismos datos que viajan en cada XML.
Si falla: mientras no han llegado, el bloque sale vacío y no se inventa nada; sin referencia, el enlace apunta al archivo general de declaraciones. Los registros se sellan y esperan en la cola hasta que lleguen (HUB_VERIFACTU-F05).
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F12 (consultar la declaración responsable)
Pendiente de enlazar: saas — publicar los datos del productor y la declaración vigente de cada versión en la respuesta del latido
QA: L-04, qa-hub-restaurant §7.00

### HUB-F311 Drenar la cola de contingencia por reloj
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. El módulo VeriFactu declara una tarea cada 5 minutos que procesa su cola.
2. El reloj del hub la lanza como el propio sistema (sin persona detrás) y el motor hace una pasada (HUB_VERIFACTU-F10).
3. Si el hub estuvo apagado, al arrancar hace una sola pasada y sigue con el horario.
4. Si la pasada falla entera, no avanza su próximo turno: se reintenta en el siguiente tic.
Entra: la tarea declarada por el módulo y el reloj del hub.
Sale: la pasada del motor (avisa: `verifactu.contingency.processed`).
Si falla: sin el permiso «Certificado del negocio (firma fiscal)» no corre. Sin vía no envía nada.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F20 (contingencia automática)
Pendiente de enlazar: architecture — REC_FISCAL-F06 (tarea programada que drena la cola)
Pendiente de enlazar: hub — HUB, avisos entre módulos (el reloj de tareas programadas)
QA: L-04, BD-09, qa-hub §7

### HUB-F312 Drenar la cola a petición, con los permisos de quien la pide
Estado: hecho
Actor: responsable, administrador
Pantalla: VeriFactu: Contingencia
Pasos:
1. En **VeriFactu → Contingencia**, alguien pulsa «Procesar cola».
2. El hub comprueba su permiso de gestión de VeriFactu (a un empleado se le pide el PIN de un responsable) y el permiso del certificado del módulo.
3. El motor hace la misma pasada que la del reloj (HUB_VERIFACTU-F10).
Entra: la orden de quien la pide.
Sale: la pasada (avisa: `verifactu.contingency.processed`).
Si falla: sin permiso, la negativa del hub; sin vía no se envía nada.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F21 (procesar la cola a mano)
Pendiente de enlazar: hub — HUB, acceso (permisos y aprobación con PIN)
QA: qa-hub §7

### HUB-F313 En producción, sin vía no se cobra
Estado: parcial — «vía» se mira sin red: una conexión segura caducada o un certificado propio que no carga (contraseña mala) cuentan como vía, y entonces se cobra y los registros esperan sin salir; el permiso «Certificado del negocio (firma fiscal)» no se mira, así que sin él se cobra y no nace registro
Actor: sistema, cajero
Pantalla: Ventas: Vender
Pasos:
1. Antes de cobrar, el TPV pregunta al núcleo qué impide declarar (HUB-F301) y, si algo lo impide, avisa y manda a donde se arregla.
2. Al confirmar cualquier transacción que abriría una cadena fiscal (la venta, la devolución, la factura), venga de donde venga (pantalla, asistente, API o automatización), el núcleo comprueba si el hub, en producción, tiene por dónde hacer llegar el registro: con certificado propio, que no haya caducado; por la vía de ERPlora, la autorización aprobada y después la conexión segura.
3. Si no la tiene, niega la transacción entera, con el código de lo que falta, antes de escribir nada.
4. En pruebas nunca se niega por esto. Una AEAT o una celda caídas tampoco: el registro espera en la cola.
5. La factura de una venta cobrada cuando la vía existía se sigue emitiendo aunque la vía se rompa antes de que llegue el aviso: su registro espera.
Entra: el perfil fiscal, la vía, la autorización y la caducidad del certificado, del núcleo; los avisos que abren una cadena, aprendidos del módulo del régimen.
Sale: la transacción negada, o nada.
Si falla: la negativa lleva `fiscal.no_representation_grant`, `fiscal.gateway_not_enrolled` o `fiscal.own_certificate_expired`; la frase la pone el TPV. Si el perfil no se puede leer, no se niega por esto.
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F07 (el TPV avisa de que hoy no puede cobrar)
Pendiente de enlazar: architecture — REC_FISCAL-F01 (la regla «en producción, sin vía no se cobra» y la ruta donde se arregla)
Pendiente de enlazar: verifactu — VERIFACTU-F20 (sin vía no se cobra en producción) y VERIFACTU-F34 (certificado caducado)
QA: L-04, qa-hub §7, qa-hub-restaurant §7.11

### HUB-F314 Bloquear la cadena fiscal sin módulo que cumpla o con una instalación ajena
Estado: parcial — adoptar la instalación ajena existe en el núcleo pero ninguna puerta lo llama: un hub bloqueado por instalación ajena no tiene salida
Actor: sistema
Pantalla: ninguna
Pasos:
1. En producción, si no queda ningún módulo activo que cumpla el régimen del hub, o si las filas del perfil las escribió otra instalación (otro identificador de hub), el hub está «bloqueado».
2. Bloqueado, el núcleo niega solo lo que abriría una cadena fiscal (la venta, la factura); el resto de la caja sigue funcionando y las consultas nunca se bloquean.
3. Reinstalar o reactivar el módulo del régimen lo desbloquea en la siguiente lectura: el bloqueo no se guarda.
Entra: el perfil fiscal y los módulos montados.
Sale: la transacción negada, o nada.
Si falla: la negativa lleva `fiscal.provider_missing` o `fiscal.installation_mismatch`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes (desactivar o desinstalar el módulo del régimen)
QA: qa-hub §7

### HUB-F315 Clavar a pruebas un hub de demostración
Estado: hecho
Actor: sistema
Pantalla: VeriFactu: Ajustes
Pasos:
1. Un hub desplegado como demostración (marca `HUB_DEMO`, que solo pone el SaaS al crearlo) nunca puede pasar a producción.
2. Ninguna orden puede escribir otro entorno fiscal que el de pruebas.
3. Sí puede tener identidad fiscal y certificado propio, y envía de verdad, siempre al entorno de pruebas de la AEAT.
Entra: la marca de demostración del despliegue, leída una vez al arrancar.
Sale: el perfil con «no puede pasar a producción»; la pantalla lo explica.
Si falla: un intento de pasar a producción: `fiscal.go_live_forbidden`; uno de escribir otro entorno: la negativa de demostración (`demo_fiscal_environment_locked`).
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F08 (en un hub de demostración no aparece «Pasar a producción»)
QA: BD-02, qa-hub §7

### HUB-F316 No dejar en producción a un hub sin ningún módulo que cumpla su régimen
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: Aplicaciones
Pasos:
1. Alguien desactiva o desinstala un módulo, o uno que arrastra a otros (apagar Facturación apaga VeriFactu).
2. Con el hub en producción, el núcleo calcula todo lo que se iría y, si no quedaría ningún módulo activo que cumpla el régimen, lo niega aunque la cola esté vacía.
3. Con dos módulos del mismo régimen, quitar uno se permite.
Entra: el conjunto de módulos que se irían y el perfil fiscal.
Sale: nada si se niega.
Si falla: `fiscal.no_provider_left`. La otra guarda, la de registros sin enviar, la pregunta el hub al propio módulo (área de módulos).
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
Pendiente de enlazar: hub — HUB, módulos y órdenes (desactivar y desinstalar, preguntando antes al módulo si puede irse)
QA: L-14, qa-hub §7

### HUB-F317 No emitir un documento fiscal sin la identidad del negocio
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Toda transacción que estampa la identidad fiscal del negocio en un documento (la factura) exige razón social y NIF en Ajustes › Negocio.
2. En producción exige además que el hub tenga vía (certificado propio o conexión segura), mientras haya instalado algún módulo que use el certificado; en pruebas no.
3. Si falta algo, la niega antes de escribir nada y dice qué falta y dónde se rellena.
Entra: la identidad del negocio y la vía, del núcleo.
Sale: la transacción negada, o nada.
Si falla: `fiscal_precondition_failed` con la lista de lo que falta; la frase («Para emitir facturas, completa primero … en Ajustes › Negocio…») la compone el kit de los módulos. Una venta sin identidad se cierra igual: lo que se niega es su factura, que acaba en «Eventos caídos».
Implicados: pendiente
Pendiente de enlazar: architecture — REC_FISCAL-F09 (una venta cobrada que no se pudo facturar)
Pendiente de enlazar: hub — HUB, negocio y datos (identidad fiscal en Ajustes › Negocio)
QA: BD-02, qa-hub §7
