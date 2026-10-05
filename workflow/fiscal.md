# WORKFLOW — Hub (servidor) · Perfil fiscal

Prefijo: HUB

> **Para qué sirve.** El núcleo del hub decide **que** el negocio debe declarar y **por dónde** puede
> hacerlo, aunque el módulo que cumple el régimen se desinstale: guarda el perfil fiscal (país,
> régimen, estado, entorno de pruebas o producción, NIF congelado), custodia el certificado del
> negocio (cifrado, la clave nunca llega a un módulo), lleva la vía de envío (certificado propio o
> ERPlora en nombre del negocio), copia el estado de la autorización de representación, crea y guarda
> la identidad de máquina para la celda fiscal, decide el paso a producción y la vuelta a pruebas,
> sirve la declaración responsable y niega cobrar en producción cuando no hay vía. Lo usan el
> **administrador** (puesta en marcha), el **cajero** (el TPV lo consulta antes de cobrar) y el
> **sistema**.
>
> La mitad del servidor que no es el motor: el perfil fiscal del negocio y su estado, el
> certificado, la vía de envío, la autorización de representación, la identidad de máquina ante la
> celda fiscal, el paso a producción y la regla «en producción, sin vía no se cobra». Escrito contra
> `origin/develop` (`c7d73b22`, 05/10/2026). Código: `crates/runtime/src/{fiscal,fiscal_profile,
> certificate,gateway_identity,producer_facts}.rs`, `crates/server/src/{gateway_enrolment,
> representation_grant}.rs`, las puertas fiscales de `crates/server/src/settings.rs` y las ramas
> fiscales del despachador (`crates/runtime/src/commands.rs`). El motor (huella, XML, envío) está en
> `crates/plugins/verifactu/WORKFLOW.md` (HUB_VERIFACTU). Las pantallas son del módulo VeriFactu
> (`VeriFactu: Configuración`, `VeriFactu: Ajustes`): el hub es país-agnóstico y no pinta ninguna.

## Referencia adoptada

La norma, no un competidor: RD 1007/2023 y Orden HAC/1177/2024 (declaración
responsable en el propio sistema, art. 13.2; `SistemaInformatico`; colaboración social para presentar
en nombre del obligado); las preguntas frecuentes de la AEAT (todo registro generado tiene que
llegar). Del mercado (Odoo `l10n_es_edi_verifactu`, Holded) solo el reparto: el certificado es del
negocio y, si no sube uno, el proveedor remite en su nombre. Decisiones propias: ADR-0081 (certificado
en el núcleo), ADR-0273 (la obligación es del núcleo), ADR-0320 y ADR-0478 (vía delegada por la
celda), ADR-0360 (en pruebas no hay nada que autorizar), ADR-0425 (el entorno va en cada registro),
ADR-0203 (sin identidad no se emite). Guion que la contrasta: bloque legal L-01…L-18 de
`qa-method-shared.md` y `qa-hub.md` §7.

## Antes de empezar

En un hub de España, en este orden: NIF y razón social en Ajustes › Negocio; el módulo VeriFactu
instalado con el permiso «Certificado del negocio (firma fiscal)»; una vía de envío (certificado
propio, HUB-F302; o la de ERPlora: autorización aprobada, HUB-F305, y conexión segura, HUB-F306);
probar en pruebas y pasar a producción (HUB-F307). En pruebas la vía de ERPlora funciona sin
autorización ni conexión segura si ERPlora publica su autoridad de confianza. Un hub de otro país no
debe nada (HUB-F300). Ojo: el estado «listo» que pide el paso a producción se recalcula al arrancar
el hub (HUB-F300).

## Flujos

### HUB-F300 Resolver el perfil fiscal del hub al arrancar
Estado: parcial — el estado «listo» (identidad, vía y un módulo que cumple el régimen) solo se recalcula al arrancar el hub: un negocio que sube su certificado o firma su conexión segura sigue «sin configurar» hasta el siguiente arranque, y uno que borra su certificado sigue «listo» (leído, sin ejecutar); y el paso 0 pasa a producción sin ninguna comprobación
Actor: sistema
Pantalla: ninguna
Pasos:
0. Antes de nada, una sola vez por hub (transición de ERPlora/hub#2079): si la configuración del módulo VeriFactu dice producción y el perfil dice pruebas, el perfil pasa a producción tal cual —sin mirar si está listo, la autorización ni la caducidad del certificado—, salvo en una demostración o un hub cerrado. Es para los hubs que pasaron a producción con el antiguo selector del módulo.
1. Cada vez que el hub arranca, con los módulos ya cargados, el núcleo lee el país del negocio y busca su régimen: España → VeriFactu; un país sin régimen no debe nada.
2. Un hub nuevo nace «sin configurar» (o «no exigible» fuera de España), con su número de instalación fijado al identificador del hub.
3. Mientras no está en producción, el perfil sigue al país, y pasa a «listo» si tiene NIF y razón social, una vía de envío (certificado propio activo o conexión segura firmada) y un módulo activo que cumple su régimen; si no, vuelve a «sin configurar».
4. Anota si el hub es de demostración (entonces no podrá pasar a producción), si sus filas las escribió otra instalación (lo marca para revisión) y qué avisos abren una cadena fiscal, aprendidos del módulo que cumple el régimen mientras está sano.
Entra: el país y la identidad del negocio (Ajustes › Negocio), el certificado y la conexión segura, los módulos montados y la marca de demostración del despliegue (`HUB_DEMO`).
Sale: el perfil fiscal del hub en la tabla de sistema `_hub_fiscal_profile` (país, régimen, estado, entorno, NIF congelado, fechas). El modo «bloqueado» no se guarda: se deduce en cada lectura (HUB-F314).
En este mismo documento se apoya en: HUB-F35 (Calcular la lista de puesta en marcha).
Si falla: un fallo al resolverlo no impide arrancar; se apunta en el registro del servidor y la siguiente lectura lo vuelve a calcular. Un hub que ya emitió nunca vuelve a «no exigible»; si su país pide otro régimen, se marca para revisión y no se adivina.
Implicados: VERIFACTU-F01, REC_ALTA-F09, REC_ALTA-F10, REC_ALTA-F14
QA: BD-02, qa-hub §7

### HUB-F301 Saber dónde y por qué vía declara el hub
Estado: hecho
Actor: sistema, empleado, responsable, administrador
Pantalla: VERIFACTU: Ajustes
Pasos:
1. Cualquier pantalla con sesión local pregunta al núcleo por la vía de envío: la vía (certificado propio o ERPlora), el estado de la autorización y su fecha, qué impide declarar ahora mismo (o nada), dónde se arregla y cuándo caduca el certificado propio.
2. El entorno (pruebas o producción), si puede pasar a producción y si ya declaró de verdad se leen por separado. «Ya declaró de verdad» hoy dice «no» aunque ya se haya vendido en producción, hasta la primera rectificativa (HUB-F308).
3. El estado del certificado dice si hay uno subido, quién y cuándo lo subió, si está en uso y cuál firma; nunca los bytes ni la contraseña.
Entra: el perfil fiscal, el certificado y la conexión segura, del núcleo; el módulo que cumple el régimen declara la ruta de su puesta en marcha.
Sale: nada; es consulta (`hub.fiscal.transmission`, `GET /api/fiscal/go-live`, `GET /api/business/certificate`). El estado de la autorización sale de la copia guardada, sin preguntar a la nube.
Si falla: un hub sin perfil todavía contesta vacío, nunca un estado inventado. Un módulo que pregunta por el certificado o por el entorno necesita el permiso «Certificado del negocio (firma fiscal)».
Implicados: REC_FISCAL-F01, SALES-F07, VERIFACTU-F04, VERIFACTU-F08
QA: qa-hub §7

### HUB-F302 Guardar o sustituir el certificado del negocio
Estado: parcial — no comprueba la contraseña ni que el fichero sea un certificado: uno inservible se guarda, el hub queda en «vía propia» y sus registros esperan en la cola sin salir; la caducidad se lee si se puede, pero no se enseña al subir
Actor: administrador
Pantalla: VERIFACTU: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Mi certificado», el administrador elige el `.p12` o `.pfx`, escribe su contraseña y pulsa «Subir certificado».
2. El núcleo lo guarda cifrado con la clave maestra del despliegue, con quién y cuándo lo subió, qué es (sello de entidad o certificado de persona, leído del propio fichero) y cuándo caduca.
3. Subirlo es elegirlo: el certificado queda en uso aunque el anterior estuviera apagado. Si ya había uno, lo sustituye en la misma escritura; la cadena no cambia y los registros siguientes salen firmados con el nuevo.
4. El núcleo avisa en el momento al SaaS de la vía nueva.
Entra: el fichero en base64 y la contraseña, del administrador.
Sale: el certificado en la tabla de sistema `_hub_certificate`; el estado nuevo a la pantalla; un latido al SaaS con la vía (`announce_route_change`). Un hub de demostración también puede subir el suyo (lo separa de la AEAT real el entorno clavado a pruebas, HUB-F315).
Si falla: sin fichero, «falta pkcs12_b64» con el código `invalid_field`; sin la clave maestra del despliegue no se guarda nada en claro y se niega; quien no es administrador recibe la negativa de sesión; un módulo sin el permiso del certificado, la negativa del permiso. Si el aviso al SaaS falla, se queda para el latido diario.
Implicados: HUB_VERIFACTU-F06, VERIFACTU-F02, VERIFACTU-F34, REC_ALTA-F12, SAAS_DASHBOARD-F42, SAAS_DASHBOARD-F55, SAAS_DASHBOARD-F149, SAAS_PUBLIC-F91
QA: qa-hub §7, qa-hub-restaurant §7.11

### HUB-F303 Borrar el certificado del negocio
Estado: parcial — se borra al primer intento también en producción, sin comprobar que la vía de ERPlora esté lista: un hub en producción sin autorización aprobada o sin conexión segura se queda sin vía y deja de cobrar (el interruptor de HUB-F304 sí lo impide)
Actor: administrador
Pantalla: VERIFACTU: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Mi certificado», el administrador pulsa «Quitarlo».
2. El núcleo borra el certificado; desde ese momento la vía es la de ERPlora.
3. Avisa al SaaS de la vía nueva.
Entra: la orden del administrador.
Sale: el certificado borrado; los registros siguientes salen por la celda de ERPlora; el latido al SaaS. Lo que ya estaba en la cola sigue en su cadena y en el siguiente intento sale por la celda, con el Sello como presentador, si la vía de ERPlora está lista; si es de producción y el hub no tiene conexión segura, el carril de pruebas lo niega y espera sin límite.
Si falla: quien no es administrador o un módulo sin el permiso del certificado reciben la negativa. Un hub de demostración también puede borrarlo.
Implicados: REC_FISCAL-F01, VERIFACTU-F03, SAAS_DASHBOARD-F149
QA: qa-hub §7

### HUB-F304 Elegir la vía de envío: mi certificado o ERPlora
Estado: hecho
Actor: administrador
Pantalla: VERIFACTU: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, el administrador enciende o apaga «Usar mi propio certificado». El certificado sigue guardado en los dos casos.
2. Encender exige un certificado subido.
3. Apagar en producción exige que ERPlora pueda declarar de verdad en su nombre: autorización aprobada y, después, conexión segura firmada. En pruebas se permite sin nada: los registros esperan hasta que haya vía.
4. Si se permite, el núcleo lo guarda y avisa al SaaS de la vía nueva.
Entra: encendido o apagado, del administrador; el perfil, la autorización y la conexión segura, del núcleo.
Sale: la vía cambiada (los registros siguientes salen por ella) y el latido al SaaS.
Si falla: encender sin certificado: `fiscal.own_certificate_not_uploaded`; apagar en producción sin autorización: `fiscal.no_representation_grant`; sin conexión segura: `fiscal.gateway_not_enrolled`; en todos, no cambia nada. Apagar sin certificado subido no hace nada. Las frases las pone la pantalla de VeriFactu.
Implicados: HUB_VERIFACTU-F06, VERIFACTU-F04, REC_ALTA-F12, SAAS_DASHBOARD-F149
QA: qa-hub §7

### HUB-F305 Enviar la autorización de representación y seguir su estado
Estado: parcial — [SEG] el estado que sigue el hub es el del otorgamiento del NIF que el hub declara, no uno ligado a este hub: erplora.com no comprueba que ese NIF sea de este negocio, así que declarar el NIF de otro negocio con otorgamiento vigente da «vigente» (y su historial)
Actor: administrador, sistema
Pantalla: VERIFACTU: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Lo remite ERPlora», el administrador pide el modelo oficial relleno con los datos del negocio y de quien firma; el hub lo trae del SaaS como PDF.
2. Sube el modelo firmado (PDF), la copia del DNI o NIE, la muestra de firma si es NIE y, si el negocio es una sociedad (NIF que empieza por letra de entidad), el justificante de representación; cada documento, menos de 10 MB.
3. El hub comprueba lo que falta antes de cruzar la red y reenvía los documentos al SaaS con la credencial de máquina; el estado pasa a «pendiente» hasta que una persona de ERPlora lo revisa.
4. Cada vez que se abre la pantalla, el hub pregunta al SaaS el estado (pendiente, vigente, rechazado, revocado o ninguno), el motivo de un rechazo y el historial de envíos, y guarda una copia del estado y su fecha en el perfil fiscal. Lo que contesta el SaaS es el otorgamiento del NIF que este hub le ha declarado (el de Ajustes › Negocio publicado), sea de quien sea: el otorgamiento no está atado al hub y el SaaS no comprueba que el NIF sea de este negocio.
5. Además, cada hora, un hub en producción por la vía de ERPlora vuelve a preguntar solo: si ERPlora revoca o rechaza la autorización, el hub deja de cobrar sin que nadie abra la pantalla; si la vuelve a aprobar, vuelve a cobrar.
Entra: los datos del negocio y de quien firma y los documentos, del administrador; el estado, del SaaS.
Sale: la autorización en el SaaS para revisión; en el hub, solo el estado y su fecha (`_hub_fiscal_profile`); los documentos no se guardan en el hub ni salen en el registro del servidor.
Si falla: lo que falta sale con su código (`obligado_nif_required`, `signer_required`, `document_type_invalid`, `signed_document_required`, `signed_document_not_pdf`, `dni_copy_required`, `signature_sample_required`, `representation_proof_required`, `document_too_large`). Sin credencial de máquina, `hub_not_enrolled`; sin respuesta o con negativa del SaaS, `cloud_unreachable` o `cloud_rejected`, y la copia guardada no cambia.
Implicados: HUB_VERIFACTU-F07, VERIFACTU-F05, VERIFACTU-F06, REC_ALTA-F11, SAAS_DASHBOARD-F154, SAAS_DASHBOARD-F155, SAAS_DASHBOARD-F156, SAAS_DASHBOARD-F157, SAAS_DASHBOARD-F158
QA: qa-hub §7

### HUB-F306 Pedir, recoger y renovar la conexión segura con la celda fiscal
Estado: parcial — el hub no renueva solo ni avisa antes de que caduque (el aviso de «caduca pronto» es de la pantalla) y da por válida una conexión caducada; «Renovar» no presenta una solicitud nueva mientras el expediente diga «aprobada»; el servicio que recoge la firma no arranca si el hub arrancó sin credencial de máquina; borrar la identidad en producción no se impide y deja al hub sin vía; las puertas de la identidad no piden el permiso del certificado a un módulo, a diferencia de las del certificado
Actor: administrador, sistema
Pantalla: VERIFACTU: Configuración
Pasos:
1. En **VeriFactu → Configuración**, bloque «Conexión segura con ERPlora», el administrador pulsa «Solicitar la conexión».
2. El hub crea su clave privada (nace en el hub, cifrada, y no sale nunca) y una solicitud de firma a nombre de este hub, y la presenta en el expediente del hub en el SaaS con su credencial de máquina.
3. Una persona de ERPlora la firma. Mientras tanto, el hub pregunta solo cada 2 minutos; «Comprobar el estado» pregunta en el momento. Cuando está firmada, instala el certificado: comprueba que es de su clave, de su nombre y que no ha caducado.
4. Para renovar, el administrador vuelve a pulsar: el hub no presenta una solicitud nueva mientras el expediente diga «aprobada»; instala lo que ERPlora haya emitido en esa fila (con la misma clave) y, si llega sin autoridad de confianza, reutiliza la guardada. El servicio de fondo no lo recoge (solo trabaja mientras no hay certificado).
5. El operador de ERPlora tiene además puertas manuales de administrador: pedir la solicitud de firma, instalar un certificado firmado sin pasar por el expediente y olvidar la identidad entera (clave incluida). El estado (con su fecha de caducidad) lo lee cualquier sesión y es lo que la pantalla usa para «caduca pronto».
Entra: la orden del administrador; el certificado firmado, del SaaS.
Sale: la identidad de máquina en la tabla de sistema `_hub_gateway_identity`; con ella, el hub tiene vía por la celda (carril mutuo) y lo nota el estado «listo» del perfil en el siguiente arranque (HUB-F300).
Si falla: la respuesta dice el estado (`filed`, `awaiting_review` —también para una identidad revocada o sustituida—, `installed`, `rejected` con el motivo) o un código de rechazo (`enrolment.no_machine_credential`, `enrolment.cloud_unreachable`, `enrolment.cloud_refused`, `enrolment.install_refused`…). La puerta crea su presupuesto en cada petición, así que nunca contesta `out_of_budget`: el presupuesto de 30 pasadas por hora solo lo agota el servicio de fondo. Una solicitud rechazada no se vuelve a presentar sola. Sin la clave maestra del despliegue no se crea ninguna clave.
Implicados: HUB_VERIFACTU-F07, VERIFACTU-F07, VFGW-F01, VFGW-F03, VFGW-F05, REC_ALTA-F13, SAAS_DASHBOARD-F150, SAAS_DASHBOARD-F151, SAAS_DASHBOARD-F153
QA: qa-hub §7

### HUB-F307 Pasar a producción
Estado: parcial — [SEG] la autorización aprobada que exige es la del NIF que el hub declara a erplora.com, no una atada a este hub (HUB-F305); la comprobación de «listo» usa el estado calculado en el último arranque (HUB-F300): tras configurar sin reiniciar se niega con `fiscal.not_ready`, y con un estado viejo puede dejar pasar a un hub que ya no tiene vía (que luego no podrá cobrar, HUB-F313)
Actor: administrador
Pantalla: VERIFACTU: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, el administrador pulsa «Pasar a producción» y confirma.
2. El núcleo comprueba, en este orden: que el hub no haya cesado; que no sea de demostración; que, si declara por la vía de ERPlora, la autorización esté aprobada (la copia del estado de HUB-F305: la del NIF que el hub declara, sin que erplora.com compruebe que es suyo); que el perfil esté «listo»; y que el certificado propio que firma no haya caducado.
3. Si todo está, el hub pasa a producción: congela el NIF del negocio como el de la cadena y anota el momento. Pulsarlo estando ya en producción no hace nada.
4. Los registros nuevos nacen en la cadena de producción; los que nacieron en pruebas siguen yendo a pruebas.
Entra: el perfil fiscal, la vía, la autorización y la caducidad del certificado, del núcleo.
Sale: el perfil en producción (`POST /api/fiscal/go-live`). Desde ese momento el motor envía a la AEAT real y el NIF de Ajustes › Negocio no se puede cambiar una vez emitido.
Si falla: `fiscal.hub_closed`, `fiscal.go_live_forbidden` (demostración), `fiscal.no_representation_grant`, `fiscal.not_ready` o `fiscal.own_certificate_expired`, y el hub sigue en pruebas. Esta no es la única forma de llegar a producción: el arranque adopta una sola vez, sin comprobaciones, el entorno que diga la configuración del módulo (HUB-F300, paso 0). Y no mira la conexión segura: con un «listo» viejo pasa un hub que ya no tiene vía. Solo el administrador; un módulo sin el permiso del certificado no puede pedirlo.
Implicados: REC_FISCAL-F14, VERIFACTU-F08, REC_ALTA-F14
QA: L-04, BD-02, qa-hub §7

### HUB-F308 Volver a pruebas mientras no se haya declarado nada en producción
Estado: parcial — la vuelta se cierra con el sello «primer registro en producción», que solo pone una orden declarativa que declara el aviso que abre la cadena; la emisión de facturas de Facturación es un manejador que devuelve ese aviso y no lo pone, así que tras vender en producción se puede seguir volviendo a pruebas hasta la primera rectificativa, y las ventas siguientes irían a la AEAT de pruebas (leído, sin ejecutar; confirmado por la verificación de la oleada); el test que dice probarlo (`crates/runtime/tests/fiscal_mode.rs:131-169`) no recorre el camino real: llama directamente a la función que pone el sello
Actor: administrador
Pantalla: VERIFACTU: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, con el hub en producción y sin nada declarado de verdad, el administrador pulsa «Volver a pruebas» y confirma.
2. El núcleo vuelve el perfil a pruebas y a «listo», y borra el momento del paso a producción.
3. Lo que **debe** cerrar la vuelta es la primera transacción que abre una cadena fiscal en producción, aunque su registro no haya salido aún. Hoy el sello solo lo pone una orden declarativa (la rectificativa de Facturación); la factura de cada venta no lo pone (ver Estado).
Entra: el sello «primer registro en producción» del perfil.
Sale: el perfil en pruebas (`DELETE /api/fiscal/go-live`); los registros que nacieron en producción siguen yendo a producción.
Si falla: con el sello puesto, `fiscal.already_emitted` («…create another hub») y no cambia nada. Estando ya en pruebas no hace nada.
Implicados: REC_FISCAL-F14, VERIFACTU-F09, REC_ALTA-F14
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
Implicados: VERIFACTU-F33, REC_ALTA-F24
QA: ninguno

### HUB-F310 Servir la declaración responsable y los datos del productor
Estado: parcial — los datos del productor viven solo en memoria y llegan con el latido al SaaS del arranque, el diario y el de cada cambio de vía: si el del arranque falla, pueden faltar hasta un día y mientras tanto no sale ningún registro
Actor: sistema, empleado, responsable, administrador
Pantalla: VERIFACTU: Ajustes
Pasos:
1. Al arrancar, cada día y tras cada cambio de vía, el hub manda su latido al SaaS y recibe los datos del productor del software (razón social y NIF de ERPlora, nombre y código del sistema, tipos de uso e indicador de varios obligados) y la referencia de la declaración responsable que cubre esta versión.
2. Cualquier sesión puede pedir la declaración: los datos del productor, la versión que está corriendo, el número de instalación (el identificador del hub), el enlace a la declaración y su versión.
3. El motor usa esos mismos datos en cada registro.
Entra: el bloque del productor y la referencia de la declaración, del SaaS.
Sale: la declaración (`GET /api/system/declaration`) con los mismos datos que viajan en cada XML.
Si falla: mientras no han llegado, el bloque sale vacío y no se inventa nada; sin referencia, el enlace apunta al archivo general de declaraciones. Los registros se sellan y esperan en la cola hasta que lleguen (HUB_VERIFACTU-F05).
Implicados: VERIFACTU-F12, SAAS_DASHBOARD-F55, SAAS_DASHBOARD-F161
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
En este mismo documento se apoya en: HUB-F62 (Ejecutar las tareas programadas de los módulos).
Si falla: sin el permiso «Certificado del negocio (firma fiscal)» no corre. Sin vía no envía nada.
Implicados: REC_FISCAL-F06, VERIFACTU-F20
QA: L-04, BD-09, qa-hub §7

### HUB-F312 Drenar la cola a petición, con los permisos de quien la pide
Estado: hecho
Actor: responsable, administrador
Pantalla: VERIFACTU: Contingencia
Pasos:
1. En **VeriFactu → Contingencia**, alguien pulsa «Procesar cola».
2. El hub comprueba su permiso de gestión de VeriFactu (a un empleado se le pide el PIN de un responsable) y el permiso del certificado del módulo.
3. El motor hace la misma pasada que la del reloj (HUB_VERIFACTU-F10).
Entra: la orden de quien la pide.
Sale: la pasada (avisa: `verifactu.contingency.processed`).
En este mismo documento se apoya en: HUB-F05 (Pedir la aprobación de un responsable cuando falta el permiso), HUB-F151 (Rechazar una orden para la que no se tiene permiso), HUB-F152 (Aprobar una acción con el PIN de un responsable).
Si falla: sin permiso, la negativa del hub; sin vía no se envía nada.
Implicados: REC_FISCAL-F06, VERIFACTU-F21
QA: qa-hub §7

### HUB-F313 En producción, sin vía no se cobra
Estado: parcial — «vía» se mira sin red: una conexión segura caducada o un certificado propio que no carga (contraseña mala) cuentan como vía, y entonces se cobra y los registros esperan sin salir; el permiso «Certificado del negocio (firma fiscal)» no se mira, así que sin él se cobra y no nace registro
Actor: sistema, cajero
Pantalla: SALES: Vender
Pasos:
1. Antes de cobrar, el TPV pregunta al núcleo qué impide declarar (HUB-F301) y, si algo lo impide, avisa y manda a donde se arregla.
2. Al confirmar cualquier transacción que abriría una cadena fiscal (la venta, la devolución, la factura), venga de donde venga (pantalla, asistente, API o automatización), el núcleo comprueba si el hub, en producción, tiene por dónde hacer llegar el registro: con certificado propio, que no haya caducado; por la vía de ERPlora, la autorización aprobada y después la conexión segura.
3. Si no la tiene, niega la transacción entera, con el código de lo que falta, antes de escribir nada.
4. En pruebas nunca se niega por esto. Una AEAT o una celda caídas tampoco: el registro espera en la cola.
5. La factura de una venta cobrada cuando la vía existía se sigue emitiendo aunque la vía se rompa antes de que llegue el aviso: su registro espera.
Entra: el perfil fiscal, la vía, la autorización y la caducidad del certificado, del núcleo; los avisos que abren una cadena, aprendidos del módulo del régimen.
Sale: la transacción negada, o nada.
Si falla: la negativa lleva `fiscal.no_representation_grant`, `fiscal.gateway_not_enrolled` o `fiscal.own_certificate_expired`; la frase la pone el TPV. Si el perfil no se puede leer, no se niega por esto.
Implicados: HUB_SHELL-F28, REC_FISCAL-F01, SALES-F07, VERIFACTU-F20, VERIFACTU-F34, REC_ALTA-F10, REC_ALTA-F19
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
En este mismo documento se apoya en: HUB-F27 (Activar una aplicación), HUB-F28 (Desactivar una aplicación preguntando antes si puede irse), HUB-F29 (Desinstalar una aplicación).
Si falla: la negativa lleva `fiscal.provider_missing` o `fiscal.installation_mismatch`.
Implicados: ninguno
QA: qa-hub §7

### HUB-F315 Clavar a pruebas un hub de demostración
Estado: hecho
Actor: sistema
Pantalla: VERIFACTU: Ajustes
Pasos:
1. Un hub desplegado como demostración (marca `HUB_DEMO`, que solo pone el SaaS al crearlo) nunca puede pasar a producción. erplora.com la pone a las demos, al hub canario de cada versión y, en PRE (`HUB_FISCAL_FORCE_TESTING`), a todos los hubs. Junto con la falta de conexión segura, es la única barrera entre la demo, que lleva el NIF de ERPlora, y producción: con ese NIF, la celda presenta sin otorgamiento (VFGW-F08).
2. Ninguna orden puede escribir otro entorno fiscal que el de pruebas.
3. Al arrancar, el núcleo le siembra, si no tiene una, una identidad fiscal de demostración (NIF y razón social) para que sus ventas se puedan facturar. Puede tener certificado propio, y envía de verdad, siempre al entorno de pruebas de la AEAT. Esa identidad sembrada no se publica a erplora.com (solo publica guardar Ajustes › Negocio): por la vía de ERPlora no se envía nada hasta que el visitante guarda su identidad, porque erplora.com rechaza el permiso de la celda (`400 obligado_nif_invalid`) y los registros esperan en la cola.
Entra: la marca de demostración del despliegue, leída una vez al arrancar.
Sale: el perfil con «no puede pasar a producción»; la pantalla lo explica.
Si falla: un intento de pasar a producción: `fiscal.go_live_forbidden`; uno de escribir otro entorno: la negativa de demostración (`demo_fiscal_environment_locked`).
Implicados: VERIFACTU-F08, REC_ALTA-F02, SAAS_PUBLIC-F91
QA: BD-02, qa-hub §7

### HUB-F316 No dejar en producción a un hub sin ningún módulo que cumpla su régimen
Estado: parcial — al desinstalar solo se mira el módulo que se desinstala, no lo que arrastra: desinstalar Facturación forzando la guarda de dependientes deja a VeriFactu sin facturas que registrar, la venta deja de contar como apertura de cadena y el TPV cobra sin factura ni registro (leído, sin ejecutar)
Actor: sistema
Pantalla: HUB_SHELL: Apps
Pasos:
1. Alguien desactiva o desinstala un módulo, o uno que arrastra a otros (apagar Facturación apaga VeriFactu).
2. Con el hub en producción, al **desactivar** el núcleo calcula todo lo que se iría (el módulo y lo que arrastra) y, si no quedaría ningún módulo activo que cumpla el régimen, lo niega aunque la cola esté vacía. Al **desinstalar** solo mira el módulo que se desinstala; la desinstalación forzada (para un administrador, que salta la guarda de dependientes) no salta esta guarda, pero como Facturación no cumple ningún régimen, quitarla pasa.
3. Con dos módulos del mismo régimen, quitar uno se permite.
Entra: el conjunto de módulos que se irían y el perfil fiscal.
Sale: nada si se niega.
En este mismo documento se apoya en: HUB-F28 (Desactivar una aplicación preguntando antes si puede irse), HUB-F29 (Desinstalar una aplicación).
Si falla: `fiscal.no_provider_left`. La otra guarda, la de registros sin enviar, la pregunta el hub al propio módulo (área de módulos).
Implicados: VERIFACTU-F32
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
En este mismo documento se apoya en: HUB-F222 (Guardar la identidad del negocio).
Si falla: `fiscal_precondition_failed` con la lista de lo que falta; la frase («Para emitir facturas, completa primero … en Ajustes › Negocio…») la compone el kit de los módulos. Una venta sin identidad se cierra igual: lo que se niega es su factura, que acaba en «Eventos caídos».
Implicados: HUB_SHELL-F28, REC_FISCAL-F09, REC_ALTA-F09
QA: BD-02, qa-hub §7

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| La obligación fiscal no depende de que el módulo esté instalado | parcial: desinstalar forzando Facturación en producción deja cobrar sin factura ni registro | HUB-F300, HUB-F314, HUB-F316 |
| Certificado del negocio custodiado en el núcleo, cifrado | hecho | HUB-F302 |
| Comprobar el certificado al subirlo (contraseña, caducidad visible) | parcial: no comprueba la contraseña; no enseña la caducidad | HUB-F302 |
| Elegir la vía (propia o ERPlora) sin perder el certificado | hecho | HUB-F304 |
| Quitar el certificado sin dejar al negocio sin vía | parcial: en producción no se impide | HUB-F303 |
| Autorización de representación (Anexo I) con revisión humana | parcial: revisión en el SaaS, pero el otorgamiento va por el NIF que declara el hub, no atado a él | HUB-F305 |
| Conexión segura con la celda | parcial: sin renovación ni aviso de caducidad en el hub | HUB-F306 |
| Paso a producción con comprobaciones | parcial: estado «listo» del último arranque; adopción única sin comprobaciones al arrancar (hub#2079) | HUB-F300, HUB-F307 |
| Paso a producción irreversible tras la primera emisión | parcial: el sello no lo pone la factura de una venta | HUB-F308 |
| Cese de actividad | no hecho (sin puerta) | HUB-F309 |
| Declaración responsable visible en el sistema | hecho | HUB-F310 |
| En producción, sin vía no se cobra | parcial: vía comprobada sin red; el permiso del certificado no se mira | HUB-F313 |
| Demo clavada a pruebas | hecho | HUB-F315 |
| Sin identidad del negocio no se emite | hecho | HUB-F317 |

## Datos: de quién es cada dato

- **Del núcleo (tablas de sistema):** `_hub_fiscal_profile` (país, régimen, estado, entorno, NIF
  congelado `taxpayer_id`, número de instalación, avisos que abren cadena, marcas de demostración y
  revisión, fechas de paso a producción, primer registro, cierre y adopción **y quién** cerró o
  adoptó (`closed_by`, `adopted_by`: identificador de usuario del hub), estado y fecha de la
  autorización); `_hub_fiscal_regime_registry` (país → régimen y techo de la simplificada, sin datos
  personales); `_hub_certificate` (el `.p12` y su contraseña cifrados, tipo, caducidad, si está en
  uso, `uploaded_by`); `_hub_gateway_identity` (clave privada cifrada, certificado de máquina,
  autoridad, nombre común).
- **De Ajustes › Negocio** ([negocio-y-datos.md](negocio-y-datos.md)): NIF, razón social, domicilio y
  país; el perfil copia el NIF al pasar a producción (la puerta de ajustes lo cierra desde el primer
  registro, HUB-F223).
- **Del SaaS:** el estado de la autorización (se guarda una copia), los datos del productor y la
  referencia de la declaración (solo en memoria), el permiso de envío de la celda (memoria del motor).
- **Datos personales (inventario RGPD, desde `system_migrations.rs` y el código):** el certificado del
  negocio contiene el nombre y el NIF de su titular (una persona si es autónomo o representante) y se
  guarda cifrado; `uploaded_by`, `closed_by`, `adopted_by` identifican a personas del hub; el
  `taxpayer_id` es el NIF del negocio (persona si es autónomo). Los documentos de la autorización
  (modelo firmado, copia del DNI/NIE, muestra de firma, justificante) y los NIF y nombres de obligado y
  firmante **pasan** por el hub hacia el SaaS y no se guardan ni salen en el registro del servidor.
  Nada de esto lo toca el borrado RGPD de un cliente.

## Reglas que no se rompen

- **La obligación es del núcleo**: en producción no se desactiva (con lo que arrastra) ni se
  desinstala el último módulo que cumple el régimen (HUB-F316) y, sin él, no se abre ninguna cadena
  (HUB-F314). Hueco: al desinstalar no se mira lo que arrastra (HUB-F316).
- **En producción, sin vía no se cobra** (`hub.fiscal.transmission` y el despachador leen la misma
  regla): toda transacción que abriría una cadena fiscal se niega antes de escribir si el hub, en
  producción, no tiene vía; en pruebas nunca; una AEAT o una celda caídas nunca (HUB-F313).
- **Sin identidad del negocio no se emite** (ADR-0203) (HUB-F317).
- **El paso a producción tiene una sola puerta**, la del núcleo, con sus comprobaciones; congela el
  NIF de la cadena (HUB-F307) — salvo la transición única de ERPlora/hub#2079: un hub que ya había
  pasado a producción desde el antiguo selector del módulo se anota como en producción al arrancar,
  una sola vez y sin comprobaciones (HUB-F300, paso 0).
- **La demo nunca pasa a producción ni escribe otro entorno** (HUB-F315).
- **El certificado y la clave de máquina nunca se guardan en claro**: sin la clave maestra del
  despliegue no se guardan; la clave privada nunca sale del hub ni llega a un módulo.
- **Las puertas del certificado y del entorno exigen sesión de administrador** (leer: cualquier
  sesión) **y, si quien llama es un módulo, el permiso «Certificado del negocio (firma fiscal)»**.
- **Un hub cerrado no vuelve a emitir** (HUB-F309; hoy sin puerta que lo cierre).
- **Hueco, no regla: «la vuelta a pruebas se cierra con la primera venta en producción»** — el sello
  no lo pone la factura de cada venta (HUB-F308).
- **Hueco, no regla: «todo tique con QR llega a la AEAT»** — ver el documento del motor
  (`crates/plugins/verifactu/WORKFLOW.md`).

## Lo que NO hace, a propósito

- No pinta pantallas fiscales: el hub es país-agnóstico y las pantallas son del módulo del régimen.
- No tramita el cese ante Hacienda (es la baja censal); cerrar el perfil no envía nada.
- No guarda los documentos de la autorización: los custodia el SaaS.
- No decide la autorización: la revisa una persona de ERPlora en el SaaS.
- No deja que la pantalla «olvide» la conexión segura más que por la puerta de administrador
  (rotación del operador).

## Dudas abiertas

1. ¿Debe recalcularse el estado «listo» al cambiar la identidad, el certificado o la conexión
   segura, en vez de solo al arrancar (HUB-F300, HUB-F307)?
2. ¿Debe borrar el certificado en producción tener la misma guarda que apagar el interruptor
   (HUB-F303)? ¿Y borrar la identidad de máquina (HUB-F306)?
3. ¿Debe el sello «primer registro en producción» ponerlo también una transacción de manejador que
   devuelve el aviso que abre la cadena (HUB-F308)? Afecta también al límite fiscal del reinicio del
   hub, que lee el mismo sello, aunque ahí lo cubre además el conteo de registros remitidos.
4. ¿Debe la regla de HUB-F313 mirar el permiso «Certificado del negocio (firma fiscal)» y la caducidad
   de la conexión segura?
5. ¿Entra en el MVP una puerta para cerrar el perfil de un negocio que cesa (HUB-F309) y otra para
   adoptar una instalación ajena (HUB-F314)?
6. ¿Debe la guarda del último proveedor mirar, al desinstalar, lo que arrastra la desinstalación,
   como ya hace al desactivar (HUB-F316)?

## Fuentes contrastadas

- `architecture/hub/fiscal-engines.md` y el comentario de `certificate.rs` dicen que el certificado
  se sube en Ajustes → Negocio; se sube en VeriFactu → Configuración.
- `verifactu/WORKFLOW.md`, VERIFACTU-F02 dice que un hub de demostración «no puede tener certificado
  propio»; desde hub#1848 sí puede (HUB-F302, HUB-F315).
- `verifactu/WORKFLOW.md`, VERIFACTU-F09 y REC_FISCAL-F14 dan por hecho que la vuelta a pruebas se
  cierra con la primera venta en producción; el sello solo lo pone una orden declarativa (HUB-F308,
  leído, sin ejecutar).
- `verifactu/WORKFLOW.md`, VERIFACTU-F12 y `producer_facts.rs` dicen que los datos del productor
  llegan «al minuto»; llegan con el latido del arranque, el diario o el de un cambio de vía
  (HUB-F310).
- Comentario de `gateway_enrolment.rs` («presupuesto compartido por el servicio y la puerta»): la
  puerta crea un presupuesto nuevo en cada petición (HUB-F306).
- Comentario de `fiscal_profile.rs` («Nothing here rejects anything… hub#556 is the gate»): las
  negativas ya existen en `commands.rs`.
- Test `crates/runtime/tests/fiscal_mode.rs:131-169`
  (`a_sale_that_starts_the_fiscal_chain_in_production_seals_the_go_live`): su nombre promete el
  camino de una venta, pero llama directamente a `stamp_first_record` (HUB-F308).
- `qa-hub.md` §7 dice que el estado del registro va «pending→transmitted/accepted»: el motor nunca
  escribe «transmitted» (ver el documento del motor).
- Mensaje de `go_live` (`fiscal.no_representation_grant`): «Sign it in Settings → Business»; se firma
  en VeriFactu → Configuración.
