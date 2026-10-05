# WORKFLOW — Motor fiscal VeriFactu del hub

Prefijo: HUB_VERIFACTU
Alcance MVP: nucleo

> Contrato de comportamiento del motor fiscal (pm#620, pm#621). Gobierna `crates/plugins/verifactu`.
> Escrito contra `origin/develop` del hub (`c7d73b22`, 05/10/2026) y `origin/main` del módulo
> `verifactu` (v1.5.63). El detalle técnico vive en `architecture/hub/fiscal-engines.md`,
> `architecture/hub/engine-reason-codes.md` y `architecture/saas/verifactu-gateway.md`; aquí se
> escribe qué hace el motor y qué garantiza. Las pantallas son del módulo `verifactu`; el perfil
> fiscal del negocio (certificado, vía, paso a producción) es del núcleo del hub
> (`workflow/fiscal.md` de la raíz, HUB-F300…).

## Para qué sirve y para quién

Es la pieza que convierte cada factura o tique que emite Facturación en un **registro de
facturación** válido ante la Agencia Tributaria y lo hace llegar: le da su número en la cadena,
calcula su huella encadenada con la del anterior, compone su QR y su XML, comprueba el XML contra
las reglas de la AEAT, lo presenta (con el certificado del propio negocio, directo a la AEAT, o a
través de la celda fiscal de ERPlora, que presenta en su nombre), lee la respuesta y, si no pudo
salir, lo deja en la cola de contingencia y lo vuelve a enviar después, declarado como envío tardío.
También comprueba y repara la cadena (recalcular huellas, consultar lo que tiene la AEAT, anclar la
cadena) y responde a la prueba de diagnóstico de la pantalla de VeriFactu.

No tiene pantalla propia: lo usan, sin saberlo, el **cajero** y el **empleado** que cobran (cada
cobro acaba aquí), el **responsable** que vigila la cola y el **administrador** que pone el sistema
en marcha y rescata la cadena, siempre desde las pantallas del módulo VeriFactu; el **asistente**
alcanza las puertas que no tienen botón; y casi todo lo hace el **sistema** solo. Es común a
restaurante y peluquería.

## Referencia adoptada

Aquí la referencia es la norma, no un competidor. Se adopta esto, no más:

- [Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840) y
  [Orden HAC/1177/2024](https://www.boe.es/buscar/doc.php?id=BOE-A-2024-22138): registro de alta y
  de anulación, huella SHA-256 encadenada con los campos y el formato de la orden (los vectores
  oficiales de alta y anulación están en las pruebas del motor), QR de cotejo, `SistemaInformatico`
  en cada registro, remisión VERI\*FACTU inmediata y remisión posterior marcada como incidencia.
- Los esquemas oficiales de la AEAT (`SuministroLR.xsd`, `SuministroInformacion.xsd`), copiados en
  `schemas/aeat/`: el validador del motor saca de ellos los elementos obligatorios y su orden, y
  añade las reglas de negocio de la AEAT que el esquema no expresa (destinatario obligatorio en
  F1/F3/R1–R4, desglose, techo de la simplificada).
- Las [preguntas frecuentes VeriFactu de la AEAT](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes.html):
  todo registro generado tiene que llegar; una incidencia se remite después con `Incidencia = S`;
  un `AceptadoConErrores` está registrado y no se reenvía (ADR-0189).
- Decisiones propias que mandan sobre el diseño: el motor es nativo y de primera parte (ADR-0009);
  la custodia del certificado es del núcleo (ADR-0081); la vía delegada por la celda fiscal
  (ADR-0320, ADR-0478); el entorno viaja dentro de cada registro (ADR-0425); en pruebas no hay nada
  que autorizar (ADR-0360); VERI\*FACTU únicamente, sin registro de eventos (ADR-0271).
- El guion que ya contrasta esta norma: bloque legal L-01…L-18 de `.claude/qa/qa-method-shared.md`
  (sobre todo L-04 y L-14) y `.claude/qa/qa-hub.md` §7.

## Antes de empezar

El motor no se configura: trabaja con lo que le da el resto del hub.

1. El módulo **VeriFactu** instalado y activo (es quien declara las órdenes del motor y la tarea
   de cada 5 minutos) con el permiso **«Certificado del negocio (firma fiscal)»** concedido en
   Ajustes → Permisos. Sin él no corre ninguna operación del motor.
2. La **identidad fiscal** del negocio (NIF y razón social) en Ajustes → Negocio.
3. Una **vía de envío**: el certificado propio del negocio, o la vía de ERPlora (en pruebas, sin
   nada más si ERPlora ha publicado su autoridad de confianza; en producción, con la autorización
   aprobada y la conexión segura). Ver HUB-F302…HUB-F306 de `workflow/fiscal.md`.
4. Los **datos del productor** del software, que llegan solos del SaaS (HUB-F310).
5. El **entorno** (pruebas o producción) lo decide el perfil fiscal del núcleo (HUB-F307, HUB-F308).

## Pantallas

El motor no tiene pantallas. Lo que hace se ve en las del módulo VeriFactu (`verifactu/WORKFLOW.md`,
«Pantallas»), que en este fichero se nombran como `VeriFactu: <pantalla>`:

- **VeriFactu: Registros** — cada registro con su estado, su huella, su QR y la respuesta de la AEAT.
- **VeriFactu: Contingencia** — la cola de envíos pendientes y «Procesar cola».
- **VeriFactu: Eventos** — el rastro de cada sellado, envío, rechazo, pasada de la cola y prueba.
- **VeriFactu: Recuperación** — «Validar cadena», «Consultar AEAT», «Recuperar cadena desde la
  AEAT» y «Continuar cadena manualmente (migración)».
- **VeriFactu: Ajustes** — la tarjeta «Prueba en vivo».

## Qué comparten los flujos del motor

Piezas que usan varios flujos de este documento, y lo que hay que revisar si cambian:

| Pieza compartida | Flujos que la usan | Qué más la lee (revisar si cambia) |
|---|---|---|
| La clasificación de la respuesta de la AEAT (aceptado, aceptado con errores, rechazado, error) | HUB_VERIFACTU-F05, F07, F08, F09, F10, F11 | La prueba en vivo **no** la usa: tiene su propia regla (`diagnostics.rs:189-200`, F17). Leen los estados que produce: la guarda de desactivar y desinstalar VeriFactu y el contador «Pendientes VeriFactu» (`pending_obligations`, `engine.rs`; VERIFACTU-F32, HUB-F316); quién espera a quién y qué recoge la pasada (`earlier_record_due`, `DUE_NEVER_QUEUED` / `DUE_FROM_QUEUE`; F05, F10); qué es eslabón (`is_chainable_status`) y el validador de cadena (F01, F12); el límite fiscal del reinicio del hub, que cuenta `transmitted`/`accepted` (`reset.rs`); los avisos públicos `verifactu.record.rejected` / `accepted_with_errors` (FLOWS-F04); y la celda, que entrega la respuesta cruda |
| La vía de envío (certificado propio o celda) | F05, F06, F07, F10, F11, F13, F14, F16, F17 | El perfil fiscal del núcleo (HUB-F302…F306, HUB-F313) |
| El entorno de cada registro | F01, F05, F07, F10, F12, F14, F15 | El paso a producción y la vuelta a pruebas (HUB-F307, HUB-F308) |
| El ancla y el enlace de la cadena (huella y registro anterior del XML) | F01, F03, F04, F09, F12, F14, F15 | — |
| La cola de contingencia y su espera | F05, F08, F10, F11 | La tarea de cada 5 minutos (HUB-F311) |
| El XML guardado y su marca de envío tardío | F04, F05, F07, F10, F11 | La celda (idempotencia por identificador de envío) |

## Flujos

### HUB_VERIFACTU-F01 Sellar el registro de alta de una factura emitida
Estado: parcial — una segunda entrega de la misma factura (o una rectificativa que choca con un registro ya existente, verifactu#110) no se trata como repetida: el motor vuelve a sellar y a intentar el envío, y solo la guarda de unicidad de la base de datos deshace la operación, que acaba en «Eventos caídos»; y como el envío inmediato ocurre antes de guardar, la AEAT puede recibir un registro que el hub no conserva (leído, sin ejecutar)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Facturación emite una factura, un tique, una sustitutiva o una rectificativa y lo avisa.
2. El motor lee esa factura una sola vez (número oficial, fecha, emisor, cliente, importes, desglose por tipo, la simplificada que sustituye o la factura que rectifica). Si no existe, no hace nada.
3. Decide el tipo: el de la factura; una F1 o F3 sin NIF de cliente se declara F2 y una R1–R4 sin NIF, R5, y queda el evento «Tipo de factura cambiado». Si esa F2 rebajada pasa de 3.010 € (3.000 € más 10 € de margen de la AEAT), se niega sin gastar número.
4. Comprueba la aritmética: la cuota de cada tipo tiene que cuadrar con su base, el desglose con la cabecera y base más cuota con el total; una factura ordinaria no puede sumar en negativo (una de 0,00 € sí se sella). Si algo no cuadra, o falta el NIF del emisor, no escribe nada. El motor no calcula ningún importe ni usa el redondeo común: declara tal cual los céntimos de Facturación y, con su propia tolerancia, como mucho se niega a sellar.
5. Sella: siguiente número de su cadena (por hub, NIF del emisor y entorno), huella encadenada con la del último registro no rechazado de esa cadena (o primer registro si no hay ninguno), enlace del QR a la sede de pruebas o a la real según el entorno en que nace, y el entorno guardado en el propio registro. Ojo: el XML que se envía declara como registro anterior el de número inmediatamente inferior, esté como esté; si ese fue rechazado, la AEAT recibe un enlace que no tiene y contesta 2007 (aceptado con avisos) (HUB_VERIFACTU-F04).
6. Queda el evento «Registro creado» y, en el mismo momento, intenta enviarlo (HUB_VERIFACTU-F05). El registro aparece en **VeriFactu → Registros**.
Entra: el aviso de factura emitida o rectificada de Facturación (`invoice.created`, `invoice.rectified`) y la fila de la factura (lectura acotada de ADR-0058); el entorno del perfil fiscal del núcleo; los datos del productor.
Sale: el registro de alta en la tabla de registros del módulo (avisa: `verifactu.record.created`), el evento de auditoría y el resultado del envío. Todo en una sola operación: si algo falla, no queda ni registro ni número gastado.
Si falla: lo que no cuadra o no tiene emisor se niega y el aviso de Facturación se reintenta hasta quedar en «Eventos caídos» (Sistema). Sin el permiso «Certificado del negocio (firma fiscal)» no corre: el aviso acaba en esa misma cola como permiso denegado y se reprocesa al concederlo. Una factura con registro ya existente choca con la guarda de unicidad y también acaba ahí (verifactu#110).
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F13 (registrar una factura emitida) y VERIFACTU-F14 (rectificativa)
Pendiente de enlazar: architecture — REC_FISCAL-F04 (registrar y encadenar el documento)
Pendiente de enlazar: hub — HUB, avisos entre módulos (entrega del aviso, reintentos y «Eventos caídos»)
QA: L-04, L-03, BD-09, R-09, B-06, qa-hub §7

### HUB_VERIFACTU-F02 Sellar un registro a mano, por la puerta manual
Estado: parcial — solo con el asistente o la API; esta puerta no rebaja el tipo: una F1 sin NIF de cliente se sella (gasta número) y después queda «Rechazado» sin salir del hub; el número de líneas lo declara quien llama y no se comprueba
Actor: responsable, administrador, asistente
Pantalla: asistente
Pasos:
1. Se pide al asistente (o por la API) crear un registro con emisor, número, fecha, tipo, importes y, si hace falta, destinatario.
2. El motor hace las mismas comprobaciones aritméticas que HUB_VERIFACTU-F01 y sella igual: número, huella, QR y entorno.
3. Intenta el envío en el momento (HUB_VERIFACTU-F05).
Entra: los datos del registro, escritos por quien llama.
Sale: el registro sellado (avisa: `verifactu.record.created`) y su envío.
Si falla: sin NIF del emisor, con importes que no cuadran o sin el permiso del certificado, se niega sin escribir nada. Sin permiso de gestión de VeriFactu, el hub pide el PIN de un responsable.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F13 (la puerta manual que usa el asistente)
QA: qa-hub §7

### HUB_VERIFACTU-F03 Sellar un registro de anulación y su huella
Estado: parcial — solo con el asistente o la API (ninguna pantalla lo ofrece) y el motor no comprueba que exista el alta que se anula
Actor: responsable, administrador, asistente
Pantalla: asistente
Pasos:
1. Solo para un registro enviado por error. Se pide al asistente un registro de anulación con el emisor, el número, la fecha y el tipo de la factura anulada.
2. El motor lo sella en la misma cadena que las altas: siguiente número y una huella propia de anulación (emisor, número y fecha de la factura anulada, huella anterior y momento de generación; sin tipo ni importes).
3. Lo envía como cualquier otro registro (HUB_VERIFACTU-F05) y aparece en **VeriFactu → Registros** con tipo «Anulación».
Entra: los datos de la factura anulada, que da quien llama.
Sale: el registro de anulación sellado y enviado (avisa: `verifactu.record.created`). La factura sigue existiendo en Facturación.
Si falla: como HUB_VERIFACTU-F02. Ningún aviso de otro módulo crea anulaciones: anular una venta o una factura no llega aquí.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F30 (anular un registro enviado por error)
Pendiente de enlazar: architecture — REC_FISCAL-F13 (anular una venta cobrada, que hoy no produce nada fiscal)
QA: L-04 (discrepa), qa-hub §7 (discrepa)

### HUB_VERIFACTU-F04 Comprobar el XML contra las reglas de la AEAT antes de enviarlo
Estado: parcial — tras cualquier rechazo (local o de la AEAT) el registro siguiente sale con un registro anterior que nombra al rechazado, mientras su huella se calculó sobre el de antes, y la AEAT lo acepta con el aviso 2007; un registro de la cola que no pasa el esquema conserva su entrada y se vuelve a comprobar, sin éxito, en cada pasada
Actor: sistema
Pantalla: VeriFactu: Registros
Pasos:
1. Justo antes de cada envío (inmediato, desde la cola o a mano) el motor compone el XML del registro, o reutiliza el que ya guardó si es un reenvío, y le pone hoy quién lo presenta.
2. Lo comprueba: elementos obligatorios y su orden según los esquemas oficiales, valores admitidos, destinatario en F1/F3/R1–R4, reglas del desglose y techo de la simplificada (una F2 de más de 3.010 €).
3. Si pasa, guarda el XML exacto que va a viajar en el almacenamiento de ficheros del módulo; si no se puede guardar, no se envía.
4. Si no pasa, el registro queda «Rechazado» con el código «XSD» sin salir del hub, con el motivo traducible en **Eventos** (qué elemento y en qué línea del desglose).
Entra: el registro sellado; los datos del productor y la vía del momento.
Sale: el XML guardado (`xml/<registro>.xml`) o el rechazo local (avisa: `verifactu.record.rejected`, motivo `xsd_invalid`).
Si falla: el rechazo local ya tiene gastado su número y deja de ser eslabón para la huella del siguiente, pero no para su registro anterior declarado en el XML (ver Estado). Si el registro venía de la cola, su entrada no se cierra: cada pasada lo vuelve a comprobar y suma un «con error». Una F1/F3/R rechazada solo por faltarle el cliente se recompone con el cliente de la factura en la siguiente pasada de la cola (HUB_VERIFACTU-F10); cualquier otro rechazo local queda así para siempre y cuenta como no enviado.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F15 (un XML que no pasa el esquema queda «Rechazado») y VERIFACTU-F24
Pendiente de enlazar: architecture — REC_FISCAL-F03 (tique por encima del techo que entra por el asistente o la API)
QA: L-04, L-01, qa-hub §7

### HUB_VERIFACTU-F05 Enviar el registro en el momento, o dejarlo esperando con su motivo
Estado: hecho
Actor: sistema
Pantalla: VeriFactu: Registros
Pasos:
1. Recién sellado, el motor mira si el hub tiene vía: certificado propio que firma, o acceso a la celda fiscal de ERPlora.
2. Sin vía, el registro queda «Pendiente» con el evento «Envío aplazado» y el motivo «este hub aún no tiene vía de envío…»; sin entrada en la cola: lo recoge la siguiente pasada en cuanto haya vía (HUB_VERIFACTU-F10).
3. Con vía, si un registro anterior de la misma cadena tiene que salir ahora mismo, este espera su turno con el motivo «antes tiene que salir un registro anterior de la misma cadena…». Uno anterior que está esperando su reintento no lo frena: el nuevo puede llegar antes a la AEAT, y entonces la AEAT lo acepta con el aviso 2007, porque su registro anterior aún no ha llegado.
4. Si puede salir, lo presenta al **entorno del propio registro** (no al que tenga el hub en ese momento) por la vía que corresponda: certificado propio (HUB_VERIFACTU-F06) o celda de ERPlora (HUB_VERIFACTU-F07), y clasifica la respuesta (HUB_VERIFACTU-F08).
5. Si la vía debía estar y se rompe por el camino (la nube no da el permiso de envío, el freno tras un fallo reciente), el registro entra en la cola con su motivo.
Entra: el registro sellado; la vía del momento (certificado del núcleo o acceso a la celda).
Sale: el registro presentado y su respuesta, o «Pendiente» con su evento, o una entrada en la cola.
Si falla: un registro que no sabe su entorno no se envía a ninguno: queda en la cola con el motivo «entorno desconocido» (avisa: `verifactu.record.rejected`, motivo `record_environment_unknown`). Sin los datos del productor el sobre no se puede construir: entra en la cola con el motivo `record_not_declarable` y sale cuando lleguen.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F15 (enviar el registro y recoger su respuesta) y VERIFACTU-F17 (por qué espera)
Pendiente de enlazar: architecture — REC_FISCAL-F05 (enviar el registro a la AEAT en el momento)
QA: L-04, BD-09, R-09, B-06, qa-hub §7

### HUB_VERIFACTU-F06 Presentar con el certificado propio, directo a la AEAT
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Con el certificado del negocio activo, el núcleo presta su identidad para la conexión segura (la clave nunca llega al motor).
2. La puerta de la AEAT la elige el tipo de certificado y el entorno del registro: sello de entidad por `www10` / `prewww10`; certificado de persona o representante por `www1` / `prewww1`; un entorno que no sea exactamente «producción» va siempre a preproducción.
3. Si el titular del certificado no es el obligado (una gestoría), el XML declara al representante; si es el mismo, no.
4. Envía el XML con 30 segundos de espera y pasa la respuesta a HUB_VERIFACTU-F08.
Entra: el XML comprobado; el certificado del núcleo (identidad, tipo y titular).
Sale: la respuesta de la AEAT, o un fallo de conexión o de certificado.
Si falla: un certificado caducado o revocado se ve como rechazo de la conexión, no antes; un fallo de red o un 5xx van a la cola (HUB_VERIFACTU-F08).
Implicados: pendiente
Pendiente de enlazar: hub — HUB, perfil fiscal: HUB-F302 (guardar o sustituir el certificado del negocio) y HUB-F304 (elegir la vía)
QA: qa-hub §7, qa-hub-restaurant §7.11

### HUB_VERIFACTU-F07 Presentar por la vía de ERPlora, a través de la celda fiscal
Estado: parcial — si ERPlora no publica la autoridad de confianza de su celda, o el hub no tiene enlace con su nube, un hub sin certificado propio no tiene vía tampoco en pruebas y sus registros esperan sin límite; con la conexión segura caducada el hub la sigue presentando, la celda la rechaza y sus registros esperan sin límite, también en pruebas (no cae al carril de pruebas), mientras en producción se sigue cobrando (HUB-F313); el reintento de un envío sin respuesta a tiempo no lleva los mismos bytes y, si el primero sí llegó, la AEAT contesta 3000 «duplicado» y el registro queda «Rechazado» aunque la AEAT lo tenga
Actor: sistema
Pantalla: ninguna
Pasos:
1. Sin certificado propio activo, el motor pide a la nube de ERPlora, con la credencial de máquina del hub, un permiso de envío de corta duración (unos 5 minutos, se reutiliza mientras vale). La nube dice a qué celda ir, con qué autoridad de confianza y quién presenta (el Sello de ERPlora).
2. Elige carril: con la conexión segura del hub firmada, el carril mutuo (comprueba que el permiso sea para este hub); sin ella, el carril de pruebas, que solo se abre si la nube publica la autoridad de confianza y que **nunca** lleva un registro de producción.
3. Envía a la celda el XML, su huella SHA-256, el NIF del obligado, el identificador del envío y el **entorno del registro**; la celda lo presenta en nombre del negocio y devuelve la respuesta de la AEAT.
4. Comprueba que la celda devuelve la huella de lo que se le mandó; si no, lo trata como fallo. Si el permiso caducó, pide otro y reintenta una vez. Un «sin respuesta a tiempo» (504) entra en la cola; el reintento sale con el mismo identificador pero con la marca de envío tardío, así que no son los mismos bytes; si el primero sí llegó, la AEAT contesta 3000 «duplicado» y el registro queda «Rechazado» aunque la AEAT lo tenga. Una página de mantenimiento que la celda entrega como respuesta correcta tampoco es un veredicto: va a la cola y se reintenta sin tope.
5. Pasa la respuesta a HUB_VERIFACTU-F08.
Entra: el XML comprobado; la conexión segura del hub, si la hay; el permiso de envío de la nube.
Sale: la respuesta de la AEAT tal como la devuelve la celda.
Si falla: si la nube niega el permiso, o la celda no responde, el registro va a la cola con su motivo; en producción sin autorización aprobada la celda lo rechaza (y el núcleo ya habría negado la venta: HUB-F313). Si la nube contesta que este hub debe ir por su propio certificado, no hay vía por la celda.
Implicados: pendiente
Pendiente de enlazar: verifactu-gateway — presentar el registro en nombre del negocio por `POST /v1/verifactu/transmissions` (carril mutuo y carril de pruebas), devolver la respuesta de la AEAT con la huella de lo recibido, y no aceptar nunca un registro de producción por el carril de pruebas
Pendiente de enlazar: saas — acuñar el permiso de envío de la celda para cada hub (`/api/v1/hub/device/fiscal/gateway-token/`), también sin autorización para el carril de pruebas
Pendiente de enlazar: hub — HUB, perfil fiscal: HUB-F305 (autorización de representación) y HUB-F306 (conexión segura con la celda)
QA: qa-hub §7, qa-hub-restaurant §7.11

### HUB_VERIFACTU-F08 Clasificar la respuesta de la AEAT
Estado: parcial — una respuesta que trae estado de envío pero no un estado de registro reconocible («Error») no entra en la cola si no la tenía ya, y nadie la vuelve a enviar sola; un 3000 «duplicado» se toma por rechazo aunque el bloque de registro duplicado diga que la AEAT lo tiene aceptado, y ese registro deja de ser eslabón
Actor: sistema
Pantalla: VeriFactu: Registros
Pasos:
1. **Correcto**: «Aceptado» con su CSV; evento «Envío aceptado»; si tenía entrada en la cola, se cierra.
2. **Aceptado con errores** (por ejemplo, el 2007 tras restaurar una copia): también «Aceptado», con el código de la AEAT; no se reenvía nunca; evento «Aceptado con avisos». Un aceptado limpio de un registro que salió a un entorno distinto del actual del hub (uno de pruebas que sale tras pasar a producción) queda como aviso con la nota del entorno.
3. **Incorrecto** (y los Fault que la AEAT repetiría igual: 4102, 4104, 4116): «Rechazado» con el código y el mensaje de la AEAT; no se reintenta solo; si venía de la cola, la entrada pasa a «failed». Si el rechazo es por la cadena, antes intenta HUB_VERIFACTU-F09. Un 3000 (duplicado) también queda «Rechazado», aunque la respuesta diga que la AEAT lo tiene aceptado (hueco).
4. **Sin respuesta** (red, certificado rechazado en la conexión, tiempo agotado, error del servidor, un Fault que no es veredicto o un cuerpo irreconocible): «Error», entra o sigue en la cola con espera creciente (HUB_VERIFACTU-F10) y el motivo en **Eventos**.
5. **Otro estado** (envío no correcto sin estado de registro conocido): «Error», sin cola si no la tenía ya; si venía de la cola, su entrada se reintenta en cada pasada sin que crezca la espera.
Entra: la respuesta de la AEAT, directa o a través de la celda.
Sale: el estado, el código, el mensaje y el CSV en el registro; el evento de auditoría; avisos públicos `verifactu.record.rejected` (rechazo, fallo de envío) y `verifactu.record.accepted_with_errors`, que llevan el id del registro, el número de factura, el estado, el motivo, el código, el mensaje de la AEAT (que puede traer el NIF y el nombre del obligado, como en un Fault 4116) y el entorno; nunca importes, huella ni XML. Un aceptado limpio no avisa a nadie más que con el `verifactu.record.transmitted` del envío manual.
Si falla: el «Error» del paso 5 se queda así hasta que alguien lo reenvíe a mano (HUB_VERIFACTU-F11).
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F15 (estados del registro) y VERIFACTU-F24 (actuar ante un rechazado)
Pendiente de enlazar: architecture — REC_FISCAL-F05 (respuesta no reconocida)
Pendiente de enlazar: flows — FLOWS-F04 (automatizaciones que escuchan los avisos de rechazo)
QA: L-04, qa-hub §7

### HUB_VERIFACTU-F09 Reengancharse a la cadena de la AEAT tras un rechazo de encadenamiento
Estado: hecho
Actor: sistema
Pantalla: VeriFactu: Eventos
Pasos:
1. Un registro vuelve **rechazado** con un motivo de encadenamiento (código 2007 o una descripción que habla del registro anterior o del primer registro).
2. El motor consulta a la AEAT por la misma vía y en el entorno del registro, toma como ancla el último registro que tiene la AEAT de ese emisor en el mes en curso y deja la recuperación anotada.
3. Vuelve a encadenar el registro sobre esa ancla (número y huella nuevos), recompone el XML y lo reenvía **una sola vez**.
4. Si vuelve a ser rechazado, queda «Rechazado» (y su entrada de la cola, «failed»).
Entra: el rechazo de la AEAT y su consulta del mes en curso.
Sale: un ancla de recuperación en la cadena (evento «Cadena recuperada»), el registro reencadenado y su respuesta.
Si falla: sin registros de la AEAT con huella, no hay ancla y queda el rechazo original; si la consulta no sale por la red, se reintenta desde la cola. Un 2007 que llega como «aceptado con errores» no dispara nada: ya está en la AEAT.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F15 (rechazo por la cadena: se reengancha y se reenvía una vez)
QA: qa-hub §7

### HUB_VERIFACTU-F10 Drenar la cola de contingencia: una pasada
Estado: parcial — si la nube de ERPlora niega el permiso de envío de la celda, la pasada entera falla antes de enviar nada; un hub sin vía (también en pruebas) no envía nada y sus registros esperan sin límite; no hay tope de intentos y el ajuste de máximo de reintentos no se lee
Actor: sistema, responsable
Pantalla: VeriFactu: Contingencia
Pasos:
1. Cada 5 minutos (HUB-F311) o al pulsar «Procesar cola», el motor reúne lo que toca: entradas de la cola cuyo próximo intento ha llegado, registros «Pendiente» que nunca salieron y registros rechazados en el propio hub solo por faltarles el cliente (los recompone con el cliente de la factura).
2. Si el hub no tiene vía, no hace nada.
3. Los ordena por entorno, emisor y número de la cadena y envía hasta 85 por pasada, cada uno a su entorno, reutilizando el XML guardado y declarados a la AEAT como envío tardío por incidencia.
4. Si uno falla, los demás siguen. El que vuelve a fallar espera más: el intervalo de reintento (5 minutos de fábrica) y después el doble cada vez, con un tope de 60 minutos. El aceptado sale de la cola; el rechazado pasa a «failed».
5. Queda el evento «Cola de contingencia procesada: {successful} enviados, {failed} con error».
Entra: la cola y los registros pendientes; la vía del momento.
Sale: los registros enviados y sus respuestas (como HUB_VERIFACTU-F08) (avisa: `verifactu.contingency.processed`).
Si falla: el «Error» sin cola de HUB_VERIFACTU-F08 no se recoge. Lo que quede por encima de 85 sale en la pasada siguiente.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F20 (contingencia automática) y VERIFACTU-F21 (procesar la cola a mano)
Pendiente de enlazar: architecture — REC_FISCAL-F06 (si no pudo salir: contingencia y envío posterior)
Pendiente de enlazar: verifactu-gateway — presentar los envíos tardíos marcados como incidencia y servir el carril de pruebas
QA: L-04, BD-09, qa-hub §7, qa-hub-restaurant §7.11

### HUB_VERIFACTU-F11 Enviar a mano un registro concreto
Estado: parcial — solo con el asistente o la API (no hay botón en Registros); sin vía, el motivo manda a subir el certificado «en Ajustes → Negocio», que no es donde se sube
Actor: responsable, administrador, asistente
Pantalla: asistente
Pasos:
1. Se pide al asistente que envíe a la AEAT el registro de una factura concreta.
2. El motor lo envía en el momento por la vía del hub, con el XML guardado y declarado como envío tardío por incidencia, y clasifica la respuesta (HUB_VERIFACTU-F08).
3. El resultado se ve en **VeriFactu → Registros**.
Entra: el registro elegido.
Sale: el envío y su respuesta (avisa: `verifactu.record.transmitted`).
Si falla: un registro ya aceptado no se reenvía («el registro ya fue aceptado por la AEAT»); sin vía se niega; un fallo de red lo deja en la cola.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F25 (reenviar un registro concreto)
Pendiente de enlazar: architecture — REC_FISCAL-F05 (reenvío a mano de lo que no salió)
QA: qa-hub §7

### HUB_VERIFACTU-F12 Recalcular y comprobar las huellas de la cadena
Estado: parcial — si la configuración del módulo nunca se guardó y el hub no tiene certificado propio, recorre la cadena de pruebas aunque el hub esté en producción; solo dice el primer punto roto; y marca «ROTA» una cadena que el propio motor produce: si un registro se rechaza cuando el siguiente ya se había sellado sobre él, el validador salta el rechazado y el siguiente ya no casa (leído, sin ejecutar)
Actor: empleado, responsable, administrador
Pantalla: VeriFactu: Recuperación
Pasos:
1. En **VeriFactu → Recuperación**, con el NIF del emisor, se pulsa «Validar cadena».
2. El motor recorre en orden los registros de ese emisor en el entorno del hub, salta los rechazados, se fía de las anclas de recuperación, recalcula la huella de cada alta y de cada anulación y comprueba que cada una lleva la del anterior.
3. Sale «Cadena de huellas íntegra: {total} registro(s)…» o «Cadena de huellas ROTA en la secuencia {seq}…». No vuelve a auditar los importes ni repara nada.
Entra: el NIF del emisor (o el de la configuración) y los registros de la cadena.
Sale: el veredicto como evento «Cadena verificada» o «Cadena rota» (avisa: `verifactu.chain.validated`).
Si falla: sin NIF se niega («falta issuer_nif del obligado…»). Sin el permiso del certificado, se niega aunque solo lea.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F26 (verificar la cadena de huellas)
QA: L-14, qa-hub §7

### HUB_VERIFACTU-F13 Consultar los registros que tiene la AEAT
Estado: hecho
Actor: responsable, administrador
Pantalla: VeriFactu: Recuperación
Pasos:
1. En **VeriFactu → Recuperación** se pulsa «Consultar AEAT».
2. El motor pregunta a la AEAT, por la misma vía que usa para enviar y en el entorno actual del hub, por los registros de ese emisor **del mes en curso**.
3. La tabla «Últimos registros en la AEAT» se llena con hasta 10.
Entra: el NIF del emisor; la respuesta de la AEAT.
Sale: la foto de lo que tiene la AEAT, que sustituye a la anterior de ese emisor (sea del entorno que sea), y el evento «Consulta a la AEAT» (avisa: `verifactu.aeat.queried`). No toca la cadena.
Si falla: un Fault de la AEAT es un error, no «cero registros»; sin vía o sin red, error visible.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F27 (consultar lo que tiene la AEAT)
QA: qa-hub §7

### HUB_VERIFACTU-F14 Anclar la cadena en el último registro de la AEAT
Estado: hecho
Actor: administrador
Pantalla: VeriFactu: Recuperación
Pasos:
1. Tras restaurar una copia, el administrador pulsa «Recuperar cadena desde la AEAT» y confirma.
2. El motor consulta a la AEAT (como HUB_VERIFACTU-F13) y toma el registro más reciente por fecha de generación de ese emisor en el mes en curso.
3. Escribe un ancla en la cadena del entorno actual del hub con la huella de ese registro: el siguiente registro se encadena sobre ella.
Entra: el NIF del emisor; el último registro del mes en curso que tiene la AEAT.
Sale: el ancla de recuperación (avisa: `verifactu.chain.recovered`), la foto de la AEAT actualizada y el evento «Cadena recuperada desde la AEAT…».
Si falla: si la AEAT no tiene registros del mes en curso, «la AEAT no devolvió registros para este emisor/periodo; nada que recuperar»; si los tiene sin huella, tampoco ancla. Solo el administrador. Si el último registro del mes es la muestra de una prueba en vivo con certificado propio (HUB_VERIFACTU-F17, hub#2490), la cadena se ancla sobre ella.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F28 (recuperar la cadena desde la AEAT)
QA: qa-hub §7

### HUB_VERIFACTU-F15 Anclar la cadena en una huella aportada a mano
Estado: parcial — si la configuración del módulo nunca se guardó y el hub no tiene certificado propio, el ancla va a la cadena de pruebas aunque el hub esté en producción
Actor: administrador
Pantalla: VeriFactu: Recuperación
Pasos:
1. Al migrar desde otra aplicación, el administrador pega la última huella (64 caracteres hexadecimales) y, si quiere, el número y la fecha de la última factura, y confirma.
2. El motor comprueba la huella y escribe un ancla en la cadena del entorno del hub; sin número usa «RECOVERY-» y el principio de la huella, y sin fecha, la de hoy.
3. La próxima factura se encadena sobre esa huella.
Entra: la huella, el número y la fecha que escribe el administrador.
Sale: el ancla (avisa: `verifactu.chain.recovered`) y el evento «Cadena continuada manualmente…».
Si falla: una huella mal formada se niega («record_hash debe ser 64 caracteres hexadecimales (SHA-256)»). Solo el administrador.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F29 (continuar la cadena de otra aplicación)
QA: qa-hub §7

### HUB_VERIFACTU-F16 Probar la vía de ERPlora sin presentar nada (prueba de conexión)
Estado: hecho
Actor: responsable, administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, tarjeta «Prueba en vivo», con el hub sin certificado propio, se elige el tipo de prueba (F2 o F1 con cliente de prueba) y se pulsa «Enviar prueba».
2. El motor pregunta primero a la celda si puede presentar ahora mismo (disponible, por qué no, si tiene el envío activo, NIF del titular del Sello).
3. Comprueba el NIF del emisor y construye y comprueba un registro de muestra igual que uno de verdad (HUB_VERIFACTU-F04), con el Sello como presentador, **sin presentarlo**: un registro remitido no se puede deshacer y en producción consumiría la autorización.
4. Sale «ERPlora puede remitir por ti» o el motivo (falta el NIF, el registro de muestra no es válido y por qué, la celda no está disponible y por qué, sin vía).
Entra: el tipo de prueba; la vía y el entorno del hub; la configuración guardada del módulo.
Sale: un solo evento «Prueba de conexión» con el resultado (vía, entorno, huella y QR de la muestra, respuesta de la celda) (avisa: `verifactu.diagnostic.run`). Ningún registro, ningún cambio en la cadena.
Si falla: sin configuración guardada del módulo se niega («VeriFactu sin configurar»); sin el permiso del certificado, se niega.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F10 (probar la conexión con la AEAT)
Pendiente de enlazar: verifactu-gateway — responder si la celda puede remitir ahora (`GET /readyz`: estado, motivo, envío activo y NIF del titular del Sello)
QA: qa-hub §7

### HUB_VERIFACTU-F17 Prueba en vivo con el certificado propio
Estado: parcial — hub#2490 (P0, abierta): con el hub en producción la muestra (un alta «PRUEBA-AAAA-MM-DD» de 121,00 € —base 100,00 € e IVA 21 %—, marcada como primer registro) se presenta de verdad en la AEAT real a nombre del negocio, porque esta rama no mira el entorno; lo que debe hacer es presentar la muestra solo en el entorno de pruebas y, en producción, comprobar el certificado y construir y validar la muestra sin presentarla, como ya hace la vía de ERPlora; y la muestra debe llevar un importe de 1 o 2 € con base, cuota y huella coherentes (indicación de Ioan en la issue); tampoco se mira la caducidad del certificado antes de enviar
Actor: responsable, administrador
Pantalla: VeriFactu: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, tarjeta «Prueba en vivo», con certificado propio, se elige el tipo de prueba y se pulsa «Enviar prueba».
2. El motor carga el certificado con su contraseña («Certificado cargado correctamente.» o el motivo de por qué no carga).
3. Sin NIF del emisor, se para ahí: «Configura el NIF del obligado tributario (emisor) antes de enviar la prueba.».
4. Construye y comprueba el registro de muestra; si no es válido, dice qué falla.
5. **Hoy**: lo presenta a la AEAT del entorno del hub, también en producción, y enseña «Aceptado por la AEAT» con su CSV o el error. **Debe**: presentarlo solo con el hub en pruebas; en producción, quedarse en el paso 4 y decirlo.
Entra: el tipo de prueba; el certificado del núcleo; el entorno del perfil fiscal.
Sale: un evento «Prueba de conexión» con el resultado (avisa: `verifactu.diagnostic.run`) y ningún registro local. Hoy, además, un alta en la AEAT que el hub no tiene: en producción queda en la AEAT real y una recuperación posterior (HUB_VERIFACTU-F14) puede anclar la cadena sobre ella.
Si falla: un certificado caducado o revocado se ve como rechazo de la conexión («…revisa que no esté caducado ni revocado»); sin red, «inténtalo en unos minutos». Sin configuración guardada no se niega: con certificado propio el motor arma una configuración con lo que dice el núcleo y se para en el NIF del emisor («Configura el NIF…»); «VeriFactu sin configurar» solo lo ve un hub sin certificado propio (HUB_VERIFACTU-F16). La prueba decide «aceptado» con su propia regla (registro correcto o aceptado con errores, o envío correcto), no con la clasificación de HUB_VERIFACTU-F08.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F10 (prueba en vivo con certificado propio) y VERIFACTU-F11 (factura de prueba, cuyo importe hub#2490 pide revisar con el mismo criterio)
Pendiente de enlazar: architecture — REC_FISCAL-F14 (de pruebas a producción sin perder ningún tique)
QA: qa-hub §7

## Cobertura contra la referencia

Requisitos de la norma que toca el motor:

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Registro de alta por cada factura expedida | parcial: una segunda entrega de la misma factura choca y acaba en «Eventos caídos» (verifactu#110) | HUB_VERIFACTU-F01 |
| Huella SHA-256 encadenada con los campos de la orden | parcial: la huella es correcta (vectores oficiales en las pruebas), pero el registro anterior declarado en el XML no salta los rechazados | HUB_VERIFACTU-F01, F03, F04 |
| Registro de anulación y su huella | parcial: sin pantalla | HUB_VERIFACTU-F03 |
| QR con la URL de cotejo del entorno | hecho | HUB_VERIFACTU-F01 |
| XML conforme a los esquemas oficiales | parcial: validador propio contrastado con los XSD (no un motor XSD completo); el rechazado desde la cola se revalida en cada pasada | HUB_VERIFACTU-F04 |
| `SistemaInformatico` en cada registro | hecho (sin datos del productor, no sale) | HUB_VERIFACTU-F05 |
| Remisión inmediata | hecho | HUB_VERIFACTU-F05, F06, F07 |
| Clasificación de la respuesta (correcto, aceptado con errores, incorrecto, sin respuesta) | parcial: un estado no reconocido queda «Error» sin cola; un 3000 «duplicado» se toma por rechazo aunque la AEAT lo tenga aceptado | HUB_VERIFACTU-F08 |
| Remisión posterior con `Incidencia = S` | hecho | HUB_VERIFACTU-F10, F11 |
| Todo registro generado llega a la AEAT | parcial: ver «Reglas que no se rompen», hueco | HUB_VERIFACTU-F07, F08, F10 |
| Cadena separada por entorno | hecho | HUB_VERIFACTU-F01, F05 |
| Consulta de lo remitido | hecho (solo el mes en curso) | HUB_VERIFACTU-F13 |
| Continuidad de la cadena tras restaurar o migrar | hecho desde la AEAT; parcial a mano | HUB_VERIFACTU-F09, F14, F15 |
| Colaboración social (presentar en nombre del obligado) | hecho por la celda; pendiente del lado de la celda | HUB_VERIFACTU-F07 |
| Prueba de la vía sin efectos | parcial: con certificado propio en producción presenta de verdad (hub#2490) | HUB_VERIFACTU-F16, F17 |

## Datos: de quién es cada dato

- **El motor no tiene tablas propias.** Escribe en las del módulo VeriFactu a través de las órdenes
  internas que el módulo declara: los registros de facturación (con huella, XML y respuesta), la
  cola de contingencia, el registro de eventos, la foto de lo que tiene la AEAT y la copia de cada XML
  enviado en el almacenamiento de ficheros del módulo (`xml/<registro>.xml`). Lee la configuración
  del módulo.
- **Del núcleo del hub**, por las ventanas que el núcleo le presta y nunca por tabla: el entorno del
  perfil fiscal, qué certificado firma (tipo y titular) y su identidad para la conexión (la clave
  nunca llega al motor), la identidad de máquina para la celda, la llamada a la nube con la
  credencial del hub y los datos del productor que sirve el SaaS.
- **De Facturación**: una sola lectura acotada de la factura y sus líneas por su id (ADR-0058).
- **De fuera**: la respuesta de la AEAT y el permiso de envío de la nube de ERPlora.
- **Datos personales** que el motor escribe (inventario RGPD; las columnas las define el módulo):
  NIF y nombre del emisor (si es autónomo, una persona); NIF, nombre, país y tipo de documento del
  cliente de una factura completa; los NIF de la factura sustituida o rectificada; la descripción;
  el enlace del QR (lleva el NIF del emisor); el XML completo, en la fila y en el fichero copiado;
  el CSV; en los eventos, números de factura y, en recuperación y pruebas, el NIF del emisor; en la
  foto de la AEAT, NIF del emisor, números de factura y CSV. Se conservan a propósito: la norma
  obliga a conservar los registros.

## Reglas que no se rompen

Solo las que el código hace cumplir:

- **VeriFactu no se simula.** No existe ningún modo simulado: todo envío es una conexión real a la
  AEAT o a la celda; la prueba por la vía de ERPlora comprueba sin presentar. Un hub de
  demostración envía de verdad, siempre al entorno de pruebas.
- **El entorno va dentro de cada registro** (ADR-0425): se fija al sellar con el del perfil fiscal
  del núcleo y el registro sale a ese entorno aunque el hub haya cambiado después; uno que no sabe su
  entorno no se envía a ninguno. Solo la palabra exacta «producción» lleva a la AEAT real.
- **La demo, clavada a pruebas**: el motor toma el entorno del núcleo, que en una demo nunca pasa a
  producción y no deja escribir otro entorno (HUB-F315).
- **El carril de pruebas de la celda nunca lleva producción**: sin conexión segura firmada, un
  registro de producción no sale por la celda (vía delegada, ADR-0320 / ADR-0478).
- **Dos cadenas por hub y emisor**: pruebas y producción no se encadenan entre sí; un registro
  rechazado no es eslabón.
- **No se sella lo imposible**: cuota que no cuadra con su tipo, desglose que no suma, factura
  ordinaria en negativo, emisor sin NIF, F2 rebajada por encima de 3.010 € → no se escribe nada ni
  se gasta número.
- **Lo que sale tarde se declara**: todo envío desde la cola o a mano lleva `Incidencia = S`, en el
  orden de su cadena.
- **Sin XML guardado no hay envío**: si el almacenamiento no confirma la copia, no se envía.
- **Un aceptado no se reenvía**: ni a mano ni por el reenganche (un `AceptadoConErrores` está
  registrado, ADR-0189).
- **Sin vía, el registro espera; no se pierde**: queda «Pendiente» o en la cola con su motivo.
- **Sin el permiso «Certificado del negocio (firma fiscal)» no corre nada del motor** (el núcleo lo
  exige antes de cada operación nativa; por defecto, denegado).
- **Permisos** (los declara el módulo): ver y validar la cadena, ver VeriFactu; sellar a mano,
  ingerir y procesar la cola, gestionar VeriFactu; enviar a mano, consultar la AEAT y la prueba,
  transmitir; recuperar la cadena, configurar VeriFactu (administrador).
- **Hueco, no regla: todo tique con QR tiene que llegar a la AEAT.** El código no lo garantiza, al
  menos, en estos casos:
  - un hub sin certificado propio al que ERPlora no da paso (sin autoridad de confianza publicada,
    sin enlace o con el permiso negado) espera sin límite, también en pruebas (F07, F10);
  - una conexión segura caducada o un certificado propio con contraseña mala cuentan como «hay vía»:
    se cobra y los registros esperan sin fin (F07, HUB-F313);
  - cualquier rechazo local por esquema queda «Rechazado» para siempre: la F2 declarada por encima
    del techo, la F1 sin cliente de la puerta manual…; solo se recompone la F1/F3/R sin cliente con
    factura enlazada (F02, F04);
  - todo rechazo de la AEAT que no sea de encadenamiento no se reenvía nunca solo (F08);
  - un estado de respuesta no reconocido queda «Error» sin cola (F08);
  - registros sin entorno o imposibles de declarar (falta un dato) esperan en la cola sin fin (F05);
  - volver a pruebas tras vender en producción: las ventas siguientes nacen en la cadena de pruebas,
    con el QR de la sede de pruebas, y nunca llegan a la AEAT real (HUB-F308);
  - una segunda entrega de la misma factura choca y acaba en «Eventos caídos» (F01).
  
  Y al revés, llega a la AEAT lo que el hub no tiene o no reconoce: lo enviado antes de guardar y
  luego deshecho, en la venta y en la pasada de la cola (F01, F10); el 3000 «duplicado» que marca
  «Rechazado» un registro que la AEAT ya tiene, que además deja de ser eslabón y descuadra la cadena
  siguiente (F07, F08); y la prueba en vivo con certificado propio, que presenta en la AEAT real lo
  que no debería (F17, hub#2490).

## Lo que NO hace, a propósito

- No decide el entorno, ni la vía, ni si el hub puede pasar a producción: eso es del núcleo
  (`workflow/fiscal.md`).
- No guarda ni ve el certificado ni su contraseña: el núcleo le presta la identidad.
- No calcula impuestos, totales ni redondeos, ni emite facturas: declara tal cual los céntimos de
  Facturación (no usa el redondeo común `money::round`) y su comprobación aritmética, con tolerancia
  propia, como mucho se niega a sellar; nunca produce una cifra distinta.
- No crea registros de anulación por su cuenta: solo cuando alguien los pide.
- No lleva el registro de eventos de los sistemas NO VERI\*FACTU (ADR-0271).
- No borra ni edita un registro sellado.
- No reenvía solo un registro rechazado por la AEAT, salvo el rechazo por la cadena.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

1. ¿Debe la prueba en vivo con certificado propio presentar la muestra solo en el entorno de pruebas
   y, en producción, quedarse en comprobar y validar sin presentar, o basta con avisar antes
   (hub#2490)? Se decide con la norma (un registro remitido no se deshace) y el mercado.
2. ¿Debe un estado de respuesta no reconocido entrar en la cola como un fallo de red (F08)?
3. ¿Debe la ingesta tratar como «ya hecho» una segunda entrega de la misma factura en vez de chocar
   (verifactu#110), y debe el envío inmediato esperar a que el registro esté guardado?
4. ¿Qué hace un hub sin certificado propio al que ERPlora no da paso en pruebas: aviso al dueño,
   tope de espera…? (F07, F10).
5. ¿Debe la validación de la cadena y el ancla manual usar el entorno del núcleo también sin
   configuración guardada, como ya hacen el sellado y la recuperación desde la AEAT (F12, F15)?
6. ¿Debe un 3000 «duplicado» leerse como aceptado cuando la respuesta dice que la AEAT ya lo tiene, y
   debe el reintento tras un 504 llevar exactamente los mismos bytes (F07, F08)?
7. ¿Debe el registro anterior declarado en el XML ser el mismo que el de la huella, saltando los
   rechazados (F04)?

## Fuentes contrastadas

Una línea por discrepancia; manda el código.

- **Comentario de `events.rs`** («rechazado en local en vez de gastar un número de la cadena») frente
  a `records.rs`: un rechazo del esquema llega al enviar, con el número ya gastado (F04).
- **Comentario de `config.rs`** («un hub que nadie configuró solo puede llegar a la AEAT de
  pruebas»): el sellado toma el entorno del núcleo también sin configuración guardada (prueba
  `a_hub_without_a_saved_config_transmits_in_the_core_environment`).
- **`verifactu/WORKFLOW.md`, F15**: «una respuesta que no es ninguna de las anteriores: Error, sin
  entrada en la cola». Matiz: un Fault o un cuerpo irreconocible sí entra en la cola; solo un estado
  de envío no correcto sin estado de registro conocido se queda sin ella (F08).
- **Motivo de «sin vía»** en el envío manual y en la resolución de la vía: manda a subir el `.p12`
  «en Ajustes → Negocio»; se sube en VeriFactu → Configuración (F11).
- **Encargo de esta oleada**: pide «prueba de conexión» y «prueba en vivo» como dos cosas; en el
  motor son una sola operación (`run_diagnostics`) que se comporta distinto según la vía (F16, F17).
- **«Validación contra el XSD»**: el validador es propio (sin motor XSD, por Android), contrastado
  con los XSD oficiales por pruebas; no valida todo lo que un motor XSD validaría (F04).
- **`qa-hub.md` §7** espera un registro de anulación al anular: el motor solo lo crea si alguien lo
  pide (F03).
- **Comentario de `diagnostics.rs`** («Prueba de extremo a extremo SIN tocar la cadena»): no toca la
  cadena local, pero con certificado propio presenta un alta en la AEAT del entorno del hub (F17).
