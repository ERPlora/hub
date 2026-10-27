# Workbook — VeriFactu (app)
Prefijo: VERIFACTU
Alcance MVP: núcleo
Estado de la app: servidor, páginas, envío por el worker y pasarela del SaaS
(`fiscal_gateway/`, saas#22) hechos (bloque fiscal, 2026-10-15); sin validar todavía en `pre` contra la AEAT de
pruebas. Lo que depende de piezas que aún no existen lo dice cada flujo en su línea `Estado:`

> Manual de usuario y especificación de la app `verifactu`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Parte del `WORKFLOW.md` del módulo VeriFactu del producto actual
> (`modules-workspace/modules/verifactu`, `origin/main` `dce2106`, v1.5.63), de sus ficheros `workflow/*.md`
> y del motor fiscal del Hub actual (`hub/crates/plugins/verifactu`, `origin/develop` `9dd3821`). Los
> números de flujo se conservan (`VERIFACTU-Fnn`) porque otras apps y el QA los citan. Las dudas abiertas
> del producto actual están decididas en «Decisiones».

## Para qué sirve y para quién

VeriFactu es el final de la cadena fiscal: cada factura o tique que emite Facturación se convierte aquí en
un **registro de facturación** encadenado (cada registro lleva la huella del anterior), con su **QR** de
cotejo, que se envía a la Agencia Tributaria (AEAT). Si no puede salir en ese momento, se queda en la cola
y sale solo después, en orden. Sirve igual a la peluquería y al restaurante: todo es común.

Solo vale para negocios de **España** (Canarias, Ceuta y Melilla incluidas): VeriFactu obliga a quien tributa
aquí. Un negocio dado de alta en erplora.com en otro país no registra ni envía nada a la AEAT aunque tenga la app
encendida: sus facturas y tiques salen sin registro ni QR de VeriFactu, como con la app apagada.

Quién la usa:

- El **empleado** consulta los registros, la cola, los eventos y el estado de la cadena.
- El **responsable**, además, envía un registro concreto, procesa y reintenta la cola, consulta lo que
  tiene la AEAT y prueba la conexión.
- El **propietario** y el **administrador**, además, eligen quién remite (su certificado o ERPlora), pasan a
  producción o vuelven a pruebas, subsanan o anulan un registro, recuperan la cadena y crean la factura de
  prueba.
- El **sistema**, sin nadie delante, registra cada factura en la misma operación que la emite y envía la
  cola.

No emite ni rectifica facturas (eso es Facturación) ni calcula impuestos (llegan decididos en la factura). El
certificado propio del negocio, si lo usa, se sube aquí y se guarda cifrado en la base de datos del hub.

## Referencia adoptada

Aquí la referencia no es un competidor: es la norma de la AEAT.

- [Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840) (Reglamento de los sistemas
  informáticos de facturación) y la [Orden HAC/1177/2024](https://www.boe.es/buscar/doc.php?id=BOE-A-2024-22138):
  registro de alta y de anulación, encadenamiento por huella SHA-256, QR cotejable, identificación del
  sistema informático, remisión voluntaria con incidencia y declaración responsable.
- «Detalle de las especificaciones técnicas para generación de la huella o hash de los registros de
  facturación» v0.1.2 (27/08/2024): el orden exacto de los campos de la huella y sus tres casos oficiales,
  que la app reproduce en sus tests.
- Los esquemas oficiales `SuministroLR.xsd` y `SuministroInformacion.xsd` de la AEAT: todo registro se valida
  contra ellos **antes** de sellarse o enviarse.
- La modalidad **VERI\*FACTU** únicamente: cada registro se remite a la AEAT; por eso no hay registro de
  eventos de la modalidad NO VERI\*FACTU, y «Eventos» es trazabilidad propia.
- [Preguntas frecuentes VeriFactu de la AEAT](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes.html):
  un registro generado tiene que llegar a la AEAT; lo que sale tarde por una incidencia se declara con
  `Incidencia = S`; el sistema respeta el `TiempoEsperaEnvio` que devuelve la AEAT entre envíos y agrupa hasta
  1.000 registros de un mismo obligado por envío.
- Del mercado (Odoo `l10n_es_edi_verifactu`, Holded, Sage, Square) se copia el reparto de pantallas: una lista
  de envíos con su estado y su QR, la ficha con la respuesta de la AEAT, un botón de enviar ahora y uno de
  anular, y la elección de la vía (certificado propio o el proveedor en tu nombre).

## Antes de empezar

- Al encender VeriFactu se enciende con ella **Facturación** (la requiere): sin facturas no hay nada que
  registrar. Encender VeriFactu en el Hub **es** activarla: desde ese momento registra cada factura que se
  emite. No hay otro interruptor.
- **El emisor** es el de Facturación (Facturación → Emisor): VeriFactu toma de cada factura su NIF y su razón
  social, no los pide otra vez.
- **El entorno** empieza en **pruebas** (la AEAT de pruebas): nada de lo que se emite cuenta ante Hacienda
  hasta pasar a producción (VERIFACTU-F08).
- **La vía de envío**: o ERPlora remite en tu nombre con su sello (para producción necesita tu autorización
  firmada, el Anexo I, aprobada por ERPlora), o remites tú con tu propio certificado. La autorización (el
  otorgamiento de representación) se firma y se sube aquí, en «Lo remite ERPlora», y la revisa ERPlora; el
  certificado se sube aquí, en «Mi certificado». Aquí se elige cuál usar.
- **En el Inicio**, mientras la vía elegida no pueda llevar tus registros a la AEAT de producción (ERPlora sin la
  autorización aprobada, o tu certificado sin subir o caducado), «Termina de configurar tu negocio» lo recuerda con
  «Configura VeriFactu»; su «Configurar» lleva a VeriFactu → Configuración, y el paso queda «Hecho» en cuanto ERPlora
  aprueba la autorización o subes y eliges tu certificado. En pruebas lleva la pastilla «Importante» (no frena la
  venta: en pruebas se vende igual) y solo lo ve quien configura VeriFactu. En producción (VERIFACTU-F08), si la vía
  se pierde (se revoca la autorización, o el certificado caduca o se quita), lleva «Necesario para facturar» y sale
  la franja «Todavía no puedes facturar» encima de las demás pantallas, porque cada venta nueva se rechaza; lo ve
  todo el equipo, y a quien no configura VeriFactu le dice «Esto lo tiene que configurar un administrador.».
- **Los datos del productor del software** (ERPlora) van fijos en cada registro (los declara su declaración
  responsable), también «Da servicio a varios obligados», siempre «S» (contradicción 7, cerrada).

Configuración inicial, paso a paso:

1. En **Facturación → Emisor**, completa la razón social, el NIF y el domicilio.
2. Enciende **VeriFactu** en las apps del Hub.
3. Emite una factura de prueba (**VeriFactu → Ajustes → Crear factura de prueba**, VERIFACTU-F11) y comprueba
   en **VeriFactu → Registros** que aparece su registro con su QR.
4. Cuando la vía esté lista, **Ajustes → Pasar a producción** (VERIFACTU-F08).

## Pantallas

Seis pestañas en el pie de cada página de VeriFactu (las del menú, en este orden): Registros, Contingencia,
Eventos, Recuperación, Configuración y Ajustes. Todas se ven con el permiso de consulta; los botones que
la persona no puede usar no aparecen.

### Registros
Menú **VeriFactu → Registros**. Título «Registros VeriFactu». Tabla de 50 en 50 (tabla o tarjetas; en el
móvil, tarjetas con el número de factura como título) con «Seq», «Factura», «Fecha», «Tipo» (Alta /
Anulación), «F.» (F1…R5), «Emisor», «Total», «Entorno» (Pruebas / Producción) y «Estado» (Pendiente,
Enviado, Aceptado, Aceptado con errores, Rechazado, en una pastilla de color). Buscador «Buscar factura,
emisor o NIF…» (número de secuencia, número de factura, nombre o NIF del emisor). Filtros de estado, tipo,
tipo de factura, entorno, fecha y total (en euros), tras el embudo de la tabla con su contador; un total que no
es un importe, o una fecha «hasta» anterior a la «desde», se dice bajo su campo y no filtra. Lo último sellado
sale arriba. Por fila: «Ver» (también
al pulsar la fila) y «Cotejar en la AEAT» (abre la página de cotejo del QR). La lista se pone al día sola
cuando nace, sale o cambia un registro en cualquier dispositivo.
Vacía: «Todavía no hay registros. Cada factura que emitas se sella y aparece aquí.»; con búsqueda o filtro,
«Sin resultados». Cargando: «Cargando…». Error: el mensaje con «Reintentar».

### Ficha de registro
Se abre desde una fila de **Registros** (`/verifactu/records/<id>`). Arriba, «Registro {número}» con su estado,
su entorno y «← Volver». Si no está en la AEAT (Pendiente o Enviado), el aviso «Aún no está en la AEAT» con
el porqué y el cuándo (VERIFACTU-F17). Si fue rechazado, el aviso «La AEAT lo ha rechazado» con qué hacer
(VERIFACTU-F24). Bloques:
- **Factura**: «Factura», «Fecha de expedición», «Fecha de operación» (si es otra), «Tipo de factura»,
  «Emisor», «NIF del emisor», «Cliente» y «NIF del cliente» (si los hay), «Rectifica a» / «Sustituye a»,
  «Base», «Cuota» y «Total».
- **Cadena de huellas**: «Seq», «Generado el», «Huella», «Huella anterior» (o «Primer registro de la cadena»).
- **QR**: la imagen del QR y «Cotejar en la AEAT».
- **Respuesta de la AEAT**: «Enviado el», «CSV», «Código de respuesta», «Mensaje de respuesta», «Intentos»,
  «Próximo intento» y la «Huella de la entrega» («ID de transmisión», «Digest del sobre (SHA-256)»; «Aún sin
  estampar» mientras no ha salido).
- **XML**: el sobre que se envía (o «El XML se construye cuando lleguen los datos del productor.»).
Botones según el estado y el permiso: «Enviar ahora» (VERIFACTU-F25) y «Preguntar a la AEAT» (VERIFACTU-F35) mientras
está en la cola, «Subsanar» (VERIFACTU-F24) y «Anular registro» (VERIFACTU-F30). Un rechazo sale justo encima de los botones.
Error al abrir: «Registro no encontrado» o el mensaje del fallo, con «← Volver».

### Contingencia
Menú **VeriFactu → Contingencia**. Título «Cola de contingencia» y botón «Procesar cola» («Procesando…»
mientras trabaja). Tabla de los registros que aún no están en la AEAT: «Factura», «Entorno», «Intentos»,
«Estado», «Próximo intento» y «Último error», en el orden en que salen (cada columna se ordena); buscador «Buscar
factura o error…». Por fila: «Reintentar» (lo
pone a salir en la siguiente pasada) y «Ver». Debajo de la tabla, el resultado de la última pasada a mano.
Vacía: «Cola vacía: todo está en la AEAT.». Cargando: «Cargando…». Error: el mensaje encima de la tabla.

### Eventos
Menú **VeriFactu → Eventos**. Título «Eventos de auditoría». Tabla, lo más reciente primero: «Cuándo»,
«Severidad» (Depuración, Información, Aviso, Error, Crítico), «Tipo» (Registro creado, Envío aplazado, Envío
aceptado, Aceptado con errores, Envío fallido, Cola procesada, Registro reprogramado, Cadena verificada, Cadena
rota, Consulta a la AEAT, Cadena recuperada, Prueba de conexión, Configuración cambiada) y «Mensaje», compuesto en el idioma de
quien mira. Buscador «Buscar tipo o mensaje…» que encuentra por las palabras que se ven, en español o en
inglés; filtros de tipo, severidad y fecha, tras el embudo de la tabla con su contador (una fecha «hasta»
anterior a la «desde» se dice bajo su campo y no filtra). Se pone al día sola.
Vacía: «Sin eventos.». Cargando: «Cargando…». Error: el mensaje con «Reintentar».

### Recuperación
Menú **VeriFactu → Recuperación**. Título «Recuperación de cadena». Campo «NIF del emisor» (rellenado con el
del emisor de Facturación) y el entorno actual. Bloque «Integridad de la cadena» con el último veredicto
(«Cadena de huellas íntegra ✓», «Cadena de huellas ROTA ✗» con la secuencia, o «Sin validar todavía») y la
nota «Recalcula las huellas SHA-256 y verifica el encadenado. No vuelve a auditar los importes.». Botones
«Validar cadena», «Consultar AEAT» y «Recuperar cadena desde la AEAT». Tabla «Últimos registros en la AEAT»:
«Factura», «Fecha», «Huella», «Estado», «CSV» y «Consultado el»; vacía: «Sin datos de la AEAT. Pulsa
«Consultar AEAT».». Bloque «Continuar cadena manualmente (migración)» con «Última huella (64 hex)», «Nº de
factura» y «Fecha» y «Continuar desde esta huella». Las dos recuperaciones piden confirmación («Confirmar
recuperación» / «Cancelar»). Al terminar: «Operación completada.».

### Configuración
Menú **VeriFactu → Configuración**. Título «Configuración de VeriFactu». Dos pestañas, las dos vías:
- **«Lo remite ERPlora»** (abre por defecto), como el `erp-verifactu-grant` del módulo antiguo: «Otorgamiento de
  representación» con su estado («Sin firmar», «En revisión desde el {fecha}», «Aprobado el {fecha}», «Devuelto el
  {fecha}» con «Nota de la revisión», «Revocado el {fecha}»); «Lo que has enviado» («Envío n.º {n}, enviado el
  {fecha}» y los documentos: «Modelo firmado», «Copia del documento de identidad», «Muestra de firma»,
  «Justificante de representación»); «Sus pasos» (con dos o más: cada estado que contó la cuenta, con su fecha y
  su motivo). En revisión o aprobado, «Volver a enviar» abre el trámite con su aviso («el envío nuevo sustituye al
  que está en revisión» / «sigues remitiendo con el actual») y «Cancelar». Sin firmar, devuelto o revocado, el
  trámite está abierto: el texto de entrada, «Obligado tributario: {razón social} ({NIF}), el emisor de
  Facturación.» (se lee, no se pide), «1 · Consigue el modelo oficial» con «Descargar el modelo» (el modelo en
  blanco del SaaS) y cómo firmarlo (a mano o con AutoFirma); con una sociedad, «Representante legal» con «Nombre y
  apellidos de quien firma» y «NIF/NIE de quien firma» (un autónomo firma él mismo y no se le pide); la
  información básica del art. 13 RGPD **antes** de pedir ningún documento; «2 · Sube el modelo firmado» con
  «Documento de identidad» (DNI / NIE) y los adjuntos, cada uno un PDF de 5 MB como máximo: «Adjuntar el modelo
  firmado (PDF)», «Adjuntar copia del documento de identidad (PDF)», con NIE «Adjuntar muestra de firma (PDF)» y
  con sociedad «Adjuntar el justificante de representación (PDF)»; «Enviar a revisión». Sin emisor en
  Facturación o mientras la cuenta no haya vinculado el negocio, lo dice y no envía. Solo quien configura
  VeriFactu ve el trámite. Si la cuenta aún no ha enviado nada, «Tu cuenta de ERPlora todavía no ha enviado este
  dato.».
- **«Mi certificado»**: «Certificado del negocio (.p12 / .pfx)» con «Cargado» / «Sin cargar», «Titular», «NIF
  del titular», «Tipo», «Subido el» y «Caduca el» (con el aviso «Caduca en {n} días: sube aquí el renovado.» a
  30 días o menos y «El certificado ha caducado. Sube uno vigente para poder enviar a la AEAT.»). Quien configura
  VeriFactu ve «Elegir el fichero .p12 / .pfx», «Contraseña del certificado», «Subir el certificado» y, con uno
  cargado, «Quitar» (pregunta antes, en una tarjeta). Nota: «El certificado y su contraseña se guardan cifrados
  en este Hub y solo viajan a la pasarela de ERPlora al enviar a la AEAT; no se vuelven a mostrar.».
En un negocio de fuera de España, arriba sale «VeriFactu solo es para negocios de España.» como único motivo: «Lo
remite ERPlora» no enseña el otorgamiento ni el trámite, y «Mi certificado» solo enseña el estado del certificado, sin
subirlo ni quitarlo.

### Ajustes
Menú **VeriFactu → Ajustes**. Título «Ajustes de VeriFactu». Tres bloques:
- **«Envío»**: «Usar mi propio certificado» (interruptor, con su explicación según la vía) y «Entorno AEAT» con
  la pastilla «Pruebas (AEAT Test)» o «Producción» y, según el caso, «Pasar a producción» (con «Todavía no puede
  pasar a producción:» y lo que falta, si falta algo) o «Volver a pruebas» con su explicación y su confirmación; en
  producción, «Las ventas y facturas nuevas se rechazan hasta que se resuelva:» y el motivo, si no hay ruta a la
  AEAT, y «Los registros están esperando:» y por qué, si esperan.
- **«Prueba en vivo»**: «Probar la conexión» y «Crear factura de prueba»; debajo, el resultado de la última
  prueba («Se remite», «Entorno», «Pasarela de ERPlora», «Emisor», «Puede enviar»), o
  «Aún no has ejecutado ninguna prueba.».
- **«Declaración responsable»**: «Leer la declaración firmada», «Versión de la declaración» y los «Datos
  identificativos de este sistema» (Productor, NIF del productor, Nombre del sistema, Código del sistema,
  Versión instalada, Número de instalación, Solo VERI\*FACTU, Puede dar servicio a varios obligados, Da
  servicio a varios obligados: siempre «S»).
En un negocio de fuera de España, arriba sale «VeriFactu solo es para negocios de España.» como único motivo, y «Usar mi propio certificado»,
«Pasar a producción», «Probar la conexión» y «Crear factura de prueba» van deshabilitados.
Avisos de la pantalla: el resultado de cada acción en una franja arriba (verde si fue bien, roja si no).

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | El texto propio de cada tabla (o «Sin resultados» con búsqueda o filtro). |
| Error | El aviso de la tabla con «Reintentar»; un rechazo de una acción sale encima de sus botones. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva (`app_inactive`) | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| VERIFACTU-F01 | Activar VeriFactu | hecho — encender la app en el Hub es activarla (la activación por hub llega con la fase 2); fuera de España, encendida, no registra ni envía nada (FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN), y que Apps no la ofrezca allí espera un gancho de encendido de la plataforma |
| VERIFACTU-F02 | Subir el certificado propio del negocio | hecho — en el Hub; cifrado en la BD del hub con `FISCAL_CERTIFICATE_KEY` |
| VERIFACTU-F03 | Quitar el certificado propio | hecho — en el Hub |
| VERIFACTU-F04 | Elegir quién remite: mi certificado o ERPlora | hecho |
| VERIFACTU-F05 | Firmar y subir el otorgamiento de representación para que remita ERPlora | hecho — se sube en el Hub, lo revisa el staff en el SaaS (`fiscal/`) y el estado vuelve en la foto (ronda §25) |
| VERIFACTU-F06 | Volver a enviar el otorgamiento | hecho — en el Hub, como VERIFACTU-F05 |
| VERIFACTU-F07 | Solicitar o renovar la conexión segura con ERPlora | descartado — sin identidad por hub (ronda 5); el Hub firma cada llamada con HMAC |
| VERIFACTU-F08 | Pasar a producción | hecho — producción = despliegue `prod` ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (vía propia con certificado válido \| vía ERPlora con otorgamiento aprobado) ∧ cuenta activa, en todos los planes (ronda 2026-10-22b: VeriFactu en Gratis); el servidor lo tiene cerrado hasta que ERPlora lo abra (bajo supervisión de Ioan) |
| VERIFACTU-F09 | Volver a pruebas | hecho |
| VERIFACTU-F10 | Probar la conexión con la AEAT | hecho — con la sonda de la pasarela del SaaS (`/internal/verifactu/probe`) |
| VERIFACTU-F11 | Crear una factura de prueba | hecho |
| VERIFACTU-F12 | Consultar la declaración responsable | hecho |
| VERIFACTU-F13 | Registrar una factura emitida | hecho — Facturación lo pide por nombre dentro de su emisión; el relay del outbox del worker queda de respaldo |
| VERIFACTU-F14 | Registrar una factura rectificativa | hecho — igual que F13 |
| VERIFACTU-F15 | Enviar el registro a la AEAT y recoger su respuesta | hecho — lo envía el worker por la pasarela del SaaS; sin `VERIFACTU_GATEWAY_URL` los registros esperan en la cola |
| VERIFACTU-F16 | Consultar los registros y su estado | hecho |
| VERIFACTU-F17 | Ver el detalle de un registro y por qué espera | hecho |
| VERIFACTU-F18 | Cotejar el QR en la sede de la AEAT | hecho |
| VERIFACTU-F19 | Dar el QR y el estado fiscal al tique y a la factura | hecho (Ventas e Impresión lo piden por nombre) |
| VERIFACTU-F20 | Enviar después lo que no pudo salir (contingencia automática) | hecho — la corre el worker cada minuto (en la fase 1, sobre un solo hub) |
| VERIFACTU-F21 | Procesar la cola a mano | hecho |
| VERIFACTU-F22 | Reintentar una entrada de la cola | hecho |
| VERIFACTU-F23 | Descartar una entrada de la cola | descartado — un registro generado no se descarta nunca |
| VERIFACTU-F24 | Actuar ante un registro rechazado por la AEAT | hecho |
| VERIFACTU-F25 | Reenviar un registro concreto | hecho — por la pasarela del SaaS |
| VERIFACTU-F26 | Verificar la cadena de huellas | hecho |
| VERIFACTU-F27 | Consultar lo que tiene la AEAT | hecho — por la pasarela del SaaS (`/internal/verifactu/query`) |
| VERIFACTU-F28 | Recuperar la cadena desde la AEAT tras restaurar una copia | hecho — por la pasarela del SaaS (`/internal/verifactu/query`) |
| VERIFACTU-F29 | Continuar la cadena de otra aplicación (migración) | hecho |
| VERIFACTU-F30 | Anular un registro enviado por error | hecho |
| VERIFACTU-F31 | Vigilar los envíos desde las pantallas | hecho — también desde los cuatro paneles del Inicio |
| VERIFACTU-F32 | Impedir apagar la app con registros sin enviar | hecho — `can_disable` de VeriFactu y 409 `base.app_vetoed` de `base.app.disable` (hub#267) |
| VERIFACTU-F33 | Cesar la actividad | descartado — la baja censal es del negocio, fuera de ERPlora; un negocio dado de baja no abre (410) |
| VERIFACTU-F34 | Renovar el certificado propio | hecho — en el Hub (subir el renovado sustituye al anterior) |
| VERIFACTU-F35 | Preguntar a la AEAT si ya tiene un registro de la cola | hecho — en la ficha del registro, en el admin del Hub y por la API |

### VERIFACTU-F01 Activar VeriFactu
<!-- origen: old-hub:HUB-F300 old:verifactu/workflow/configuracion.md#verifactu-f01 -->
Estado: hecho — encender la app en el Hub es activarla (la activación por hub llega con la fase 2); fuera de España, encendida, no registra ni envía nada (FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN), y que Apps no la ofrezca allí espera un gancho de encendido de la plataforma
Actor: administrador
Pantalla: Hub: Apps
Pasos:
1. En las apps del Hub, enciende **VeriFactu** (se enciende Facturación con ella).
2. Desde ese momento cada factura que emite Facturación se registra (VERIFACTU-F13) en el entorno de
   pruebas.
3. Solo en un negocio de España. En uno de otro país (el de su cuenta de erplora.com), VeriFactu encendida no
   hace nada: las facturas salen sin registro ni QR, **VeriFactu → Ajustes** y **VeriFactu → Configuración** dicen
   arriba «VeriFactu solo es para negocios de España.» sin ofrecer nada que lleve a la AEAT, y lo que pida registrar o enviar algo contesta lo mismo.
Entra: nada más que la orden.
Sale: la app activa; sin interruptor propio.
Si falla: lo dice la página de apps del Hub.
Implicados: INVOICE-F01

### VERIFACTU-F02 Subir el certificado propio del negocio
<!-- origen: fi:hub/runtime#certificado-fiscal-del-negocio-core-adr-0079-0081 fi:hub/server-cloud#settings-capabilities-certificado-fiscal-settings-rs old-hub:HUB-F302 old:verifactu/workflow/configuracion.md#verifactu-f02 qa:modules/verifactu/configure-identity-and-certificate -->
Estado: hecho — en el Hub; cifrado en la BD del hub con `FISCAL_CERTIFICATE_KEY`
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Mi certificado», pulsa «Elegir el fichero .p12 / .pfx» y elige el
   certificado del negocio (como mucho 1 MB).
2. Escribe su contraseña en «Contraseña del certificado» y pulsa «Subir el certificado».
3. El Hub lo abre con la contraseña, lee titular, NIF, tipo y caducidad y lo guarda cifrado (Fernet) junto con
   la contraseña en la base de datos del hub. Sale «Certificado subido: {titular} ({NIF}).» y la pestaña pasa a
   «Cargado». Subir otro sustituye al anterior.
4. En un negocio de fuera de España no se ofrece: arriba dice «VeriFactu solo es para negocios de España.» y la pestaña solo enseña el estado del
   certificado, sin subirlo ni quitarlo.
Entra: el `.p12`/`.pfx` en base64 y su contraseña (`verifactu.certificate.upload`).
Sale: el certificado guardado (`OwnCertificate`), un evento «Certificado propio de … subido» y el aviso
`verifactu.config.changed`. El fichero y la contraseña no se vuelven a mostrar: ni en la API, ni en el admin,
ni en la foto, ni en los registros del servidor.
Si falla: el certificado no se guarda (409):
- sin clave de almacenamiento en el servidor, «Este servidor aún no puede guardar certificados: ERPlora tiene
  que configurar su clave de almacenamiento.» (`verifactu.certificate_storage_unavailable`);
- sin emisor, «Configura antes el emisor en Facturación → Emisor.» (`verifactu.issuer_missing`);
- contraseña mala o fichero que no es un `.p12`, «El fichero no es un certificado .p12/.pfx que abra esta
  contraseña.»; sin uso de autenticación de cliente, «El certificado no permite la autenticación de cliente,
  así que no puede conectar con la AEAT.»; caducado, «El certificado caducó el {fecha}: sube uno vigente.»
  (todos `verifactu.certificate_invalid`);
- titular distinto del emisor de Facturación, «El certificado es de {NIF}, no del emisor de este negocio,
  {NIF}.» (`verifactu.certificate_holder_mismatch`): por la vía propia se presentaría en nombre de otro.
Implicados: VERIFACTU-F04, VERIFACTU-F34

### VERIFACTU-F03 Quitar el certificado propio
<!-- origen: fi:hub/runtime#certificado-fiscal-del-negocio-core-adr-0079-0081 old-hub:HUB-F303 old:verifactu/workflow/configuracion.md#verifactu-f03 -->
Estado: hecho — en el Hub
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. En «Mi certificado», con uno cargado, pulsa «Quitar»; una tarjeta pregunta «¿Quitar el certificado?».
2. Al confirmar, el certificado se borra de la base de datos del hub, sale «Certificado quitado.» y la pestaña
   pasa a «Sin cargar».
3. Si la vía era «mi certificado», los registros dejan de poder salir hasta subir otro o elegir ERPlora
   (VERIFACTU-F04): esperan en la cola con el motivo «tu certificado propio no está cargado o ha caducado».
Entra: nada (`verifactu.certificate.remove`).
Sale: el certificado borrado, un evento «Certificado propio de … quitado» y el aviso `verifactu.config.changed`.
Si falla: sin permiso de configurar, 403.
Implicados: VERIFACTU-F04

### VERIFACTU-F04 Elegir quién remite: mi certificado o ERPlora
<!-- origen: old-saas:SAAS_DASHBOARD-F149 fi:hub/domain#read_config-load_pkcs12-config-del-hub-y-carga-del-certificado qa:modules/verifactu/configure-identity-and-certificate fi:modules/verifactu#command-sql-declarativo-verifactu-config-save fi:modules/verifactu#query-verifactu-config-get old-hub:HUB-F301 old-hub:HUB-F304 old:verifactu/workflow/configuracion.md#verifactu-f04 -->
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, el interruptor «Usar mi propio certificado» enseña la vía actual con su
   explicación: «ERPlora remite tus registros a Hacienda en tu nombre, con su propio sello. No necesitas
   certificado.» o «Envías tú directamente a Hacienda con el certificado de tu negocio, subido en Configuración
   → Mi certificado.».
2. Cámbialo.
3. Sale «Listo: a partir de ahora envías con tu propio certificado.» o «Listo: a partir de ahora remite
   ERPlora en tu nombre.».
4. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.» y el interruptor va deshabilitado.
Entra: la vía elegida; el certificado subido (VERIFACTU-F02) y el estado de la autorización, de la cuenta.
Sale: la vía guardada; los registros siguientes salen por ella (avisa `verifactu.config.changed`).
Si falla: sin certificado vigente, «No hay ningún certificado válido cargado: súbelo en VeriFactu →
Configuración → Mi certificado.»; en producción y por la vía de ERPlora sin autorización aprobada, «Para que ERPlora remita en
producción falta que apruebe tu autorización firmada.». El interruptor vuelve a la vía real.
Implicados: VERIFACTU-F02, VERIFACTU-F05

### VERIFACTU-F05 Firmar y subir el otorgamiento de representación para que remita ERPlora
<!-- origen: old-saas:SAAS_DASHBOARD-F154 old-saas:SAAS_DASHBOARD-F155 old-saas:SAAS_DASHBOARD-F156 old-saas:SAAS_DASHBOARD-F157 old-saas:SAAS_DASHBOARD-F158 old-hub:HUB-F305 old:verifactu/workflow/configuracion.md#verifactu-f05 -->
Estado: hecho — se sube en el Hub (como el módulo antiguo), lo revisa el staff en el SaaS y el estado vuelve en la
foto (ronda §25, PLAN-SAAS §4)
Actor: administrador (permiso «configurar»)
Pantalla: Configuración
Pasos:
1. En **VeriFactu → Configuración**, pestaña «Lo remite ERPlora», el estado dice «Sin firmar».
2. «Descargar el modelo» baja el modelo oficial (Anexo I del Convenio 17, el del SaaS) con los datos del negocio ya
   puestos: la razón social, el NIF y la dirección del emisor de Facturación (el municipio y la vía pública, con el
   número tal como figura en la dirección); sin emisor, baja en blanco. Se completa lo que falte y se firma fuera de
   la pantalla: a mano (y se escanea a PDF, con el sello si es una sociedad) o con AutoFirma.
3. Una sociedad escribe su representante legal (nombre y NIF/NIE); un autónomo firma él mismo.
4. Se elige el documento de identidad (DNI o NIE) y se adjuntan los PDF: el modelo firmado, la copia del
   documento, con NIE una muestra de la firma y, con sociedad, el justificante de representación.
5. «Enviar a revisión»: el Hub comprueba los documentos y los reenvía tal cual al SaaS; queda «En revisión».
6. Una persona de ERPlora lo revisa en el SaaS; la cuenta manda al Hub el estado nuevo: «Aprobado», «Devuelto»
   (con el motivo) o «Revocado».
7. En un negocio de fuera de España no se ofrece: arriba dice «VeriFactu solo es para negocios de España.» y la
   pestaña no enseña el otorgamiento ni el trámite.
Entra: el emisor de Facturación (obligado tributario), el representante, el tipo de documento y los PDF en base64
(`verifactu.representation.submit`); el modelo, de `verifactu.representation.model`, que le pasa al SaaS los datos
del emisor.
Sale: `POST /internal/hubs/{id}/representation` al SaaS; «En revisión» (uno aprobado sigue vigente y remitiendo
hasta que se apruebe el nuevo), su huella en «Lo que has enviado» y en el registro de auditoría (número, fecha,
tipo de documento y qué documentos; nunca su contenido) y el aviso `verifactu.config.changed`. El Hub no guarda
ningún documento. Aprobado, abre la vía de ERPlora en producción (VERIFACTU-F08).
Si falla: antes de llamar, con los códigos del SaaS (422): falta el modelo («Adjunta el modelo firmado.»), no es un
PDF («El modelo firmado tiene que ser un PDF — escanéalo o fírmalo con AutoFirma.»), falta la copia del documento,
con NIE la muestra de firma, con sociedad el representante o el justificante, un fichero de más de 5 MB («Cada
fichero puede ocupar 5 MB como máximo.»); el rechazo del SaaS, con su código `fiscal.*` y sus campos tal cual; sin
emisor, 409 `verifactu.issuer_missing`; sin la foto de la cuenta (el Hub aún no sabe su id en ERPlora) o un negocio
que el SaaS no conoce, 409 `verifactu.hub_unregistered` («ERPlora todavía no ha vinculado este negocio.»); sin el
SaaS, 503 `verifactu.saas_unreachable` («ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.»).
Al descargar el modelo, un dato del emisor que el modelo no puede escribir (una letra fuera de las suyas o un texto
demasiado largo) baja en blanco para escribirlo a mano, con el resto ya puesto: nunca deja sin modelo.
Implicados: VERIFACTU-F08

### VERIFACTU-F06 Volver a enviar el otorgamiento
<!-- origen: old-saas:SAAS_DASHBOARD-F157 old:verifactu/workflow/configuracion.md#verifactu-f06 -->
Estado: hecho — en el Hub, como VERIFACTU-F05
Actor: administrador (permiso «configurar»)
Pantalla: Configuración
Pasos:
1. Devuelto o revocado, el trámite ya está abierto: se corrige lo que dice el motivo y se envía de nuevo.
2. En revisión o aprobado, «Volver a enviar» lo abre y avisa: el envío nuevo sustituye al que está en revisión;
   con uno aprobado, se sigue remitiendo con él mientras se revisa el nuevo. «Cancelar» lo cierra.
Entra: como VERIFACTU-F05.
Sale: como VERIFACTU-F05; el envío lleva el número siguiente.
Si falla: como VERIFACTU-F05.
Implicados: VERIFACTU-F05

### VERIFACTU-F07 Solicitar o renovar la conexión segura con ERPlora
<!-- origen: old-saas:SAAS_DASHBOARD-F150 old-saas:SAAS_DASHBOARD-F151 old-saas:SAAS_DASHBOARD-F152 old-saas:SAAS_DASHBOARD-F153 old-hub:HUB-F306 old:verifactu/workflow/configuracion.md#verifactu-f07 -->
Estado: descartado — sin identidad por hub (ronda 5): el Hub firma cada llamada a la pasarela de ERPlora con HMAC, así
que no hay conexión segura que pedir ni renovar
Actor: ninguno
Pantalla: ninguna
Pasos:
1. No hay nada que pedir ni que renovar.
2. El Hub y la cuenta de ERPlora se hablan por su canal interno firmado.
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: ninguno

### VERIFACTU-F08 Pasar a producción
<!-- origen: old-hub:HUB-F307 old:verifactu/workflow/configuracion.md#verifactu-f08 wf:cadena-fiscal#rec_fiscal-f14 -->
Estado: hecho — producción = despliegue `prod` ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (vía propia con certificado
válido | vía ERPlora con otorgamiento aprobado) ∧ cuenta activa (`status` de la foto), en todos los planes (ronda
2026-10-22b: VeriFactu en Gratis, sin opción de pago); el servidor lo tiene cerrado hasta que ERPlora lo abra (bajo supervisión de Ioan). En `pre` nunca se abre: todo va a pruebas. Un
hub demo nunca pasa a producción (`verifactu.go_live_forbidden`).
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, «Entorno AEAT» enseña «Pruebas (AEAT de pruebas)» y «Tus facturas van al entorno de
   pruebas de la AEAT. Cuando esté todo listo, pasa a producción.». Si falta algo, debajo sale «Todavía no puede
   pasar a producción:» con la lista (negocio de demostración, otorgamiento sin aprobar, certificado propio que falta
   o ha caducado, cuenta con un pago pendiente o suspendida) y «Pasar a producción» queda desactivado. Ningún plan
   falta en ella: VeriFactu en vivo es de todos los planes.
2. Pulsa «Pasar a producción» y confirma en «¿Enviar tus facturas a la AEAT de verdad?» («A partir de ahora
   cada registro se remite a la AEAT real. En cuanto se selle el primero ya no podrás volver a pruebas.»).
3. Sale «Tu negocio está en producción: los registros ya se remiten a la AEAT real.» y la pastilla pasa a
   «Producción».
Entra: el emisor de Facturación; la vía y su estado; de la foto de la cuenta (`verifactu.config.sync`), el
otorgamiento y el estado del negocio (la foto de un SaaS anterior aún trae `live_paid`: se acepta y no se lee).
Sale: el entorno en producción (avisa `verifactu.config.changed`): los registros nuevos nacen en la cadena
de producción, con el QR de la sede real; los que nacieron en pruebas siguen yendo a pruebas.
Si falla: mientras ERPlora no lo abra en el servidor, «El paso a producción todavía no está abierto en este
servidor: ERPlora lo abre cuando la remisión real esté lista.» (en Ajustes, en la lista de lo que falta: «ERPlora
todavía no ha abierto la presentación real a la AEAT en este servidor», `production_closed`); sin la pasarela del
SaaS en el servidor, «La pasarela de envío de ERPlora no está configurada en este servidor: nada podría llegar a la
AEAT.» (`verifactu.gateway_unavailable`); con un certificado propio que este servidor no abre (la clave
`FISCAL_CERTIFICATE_KEY` falta o se rotó), «Tu certificado propio no se puede abrir en este servidor: vuelve a
subirlo en VeriFactu → Configuración → Mi certificado.» (`verifactu.own_certificate_unreadable`); en un hub demo, «Un negocio de demostración no
puede pasar a producción: siempre presenta en el entorno de pruebas de la AEAT.» (`verifactu.go_live_forbidden`;
quién es demo lo dice la plataforma, `base.operations.is_demo_hub`); sin emisor, «Configura antes el emisor en
Facturación → Emisor.»; por la vía de ERPlora sin autorización aprobada, «Para que ERPlora remita en producción
falta que apruebe tu autorización firmada.» (`verifactu.representation_not_approved`); con la cuenta con un pago
pendiente o suspendida, «Tu cuenta de ERPlora tiene un pago pendiente o está suspendida: regulariza el pago en tu
cuenta de ERPlora para pasar a producción.» (`verifactu.hub_not_active`); con certificado propio que falta o ha
caducado, «No hay ningún certificado válido cargado: súbelo en VeriFactu → Configuración → Mi certificado.»
(`verifactu.no_own_certificate`). Todos son 409 y el entorno sigue en pruebas. Ya en producción, no hace nada.
En un negocio de fuera de España se niega como con la app apagada, «VeriFactu solo es para negocios de España.» (404
`app_inactive`), y Ajustes lo dice arriba, «VeriFactu solo es para negocios de España.», como único motivo (sin la lista de lo que falta), con
«Pasar a producción» deshabilitado.
Si en producción se pierde la ruta (la foto deja de traer el otorgamiento aprobado, o caduca el certificado propio),
no se vuelve a pruebas (ya hay registros de producción): **no se sella nada nuevo** —la venta o la factura se
rechazan con 409 y el código de la ruta (`verifactu.representation_not_approved`,
`verifactu.own_certificate_missing`) y «No se ha emitido nada: este negocio presenta en real a la AEAT y ahora no
puede hacerle llegar sus registros:», el motivo y «Resuélvelo en VeriFactu → Ajustes y vuelve a intentarlo.»— y
Ajustes lo dice bajo «Las ventas y facturas nuevas se rechazan hasta que se
resuelva:» (`issue_blocker`). Lo ya sellado sin otorgamiento aprobado o sin certificado válido espera, porque la
pasarela no podría presentarlo. Cambiar a la vía de ERPlora en producción sin el otorgamiento aprobado se rechaza
igual.
Del Hub antiguo (`fiscal_profile::go_live`): el orden (cerrado → demo → vía → listo), el certificado propio sin
otorgamiento, el 409 con el código de la causa y VeriFactu sin pago aparte. Nuevo por el modelo de Ioan del
2026-10-15: el estado de la cuenta, que antes solo frenaba el token de la pasarela en el SaaS. La opción de pago que
ese modelo añadía la retiró la ronda 2026-10-22b (VeriFactu en Gratis).
Implicados: VERIFACTU-F05, VERIFACTU-F09

### VERIFACTU-F09 Volver a pruebas
<!-- origen: wf:cadena-fiscal#rec_fiscal-f14 old-hub:HUB-F308 old:verifactu/workflow/configuracion.md#verifactu-f09 -->
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En producción y sin ningún registro sellado en producción, sale «Todavía no se ha sellado ningún registro en
   producción, así que aún puedes volver a pruebas.» y «Volver a pruebas».
2. Confirma en «¿Volver al entorno de pruebas?».
3. Sale «Tu negocio ha vuelto al entorno de pruebas.».
Entra: si hay registros de producción.
Sale: el entorno en pruebas (avisa `verifactu.config.changed`).
Si falla: con un registro de producción ya sellado (una venta basta), «No se puede volver a pruebas: este
negocio ya tiene registros en producción.» y el botón no aparece.
Implicados: VERIFACTU-F08

### VERIFACTU-F10 Probar la conexión con la AEAT
<!-- origen: fi:hub/domain#run_diagnostics-prueba-en-vivo-cert-huella-qr-envio-aeat wf:cadena-fiscal#rec_fiscal-f14 fi:modules/verifactu#command-handler-nativo-verifactu-diagnostics-run-run_diagnostics fi:modules/verifactu#query-verifactu-diagnostics-last old-hub:HUB_VERIFACTU-F16 old-hub:HUB_VERIFACTU-F17 old:verifactu/workflow/configuracion.md#verifactu-f10 -->
Estado: hecho — con la sonda de la pasarela del SaaS (`/internal/verifactu/probe`)
Actor: responsable, administrador
Pantalla: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, «Prueba en vivo», pulsa «Probar la conexión» («Probando…»).
2. El Hub comprueba, sin presentar nada a la AEAT, todo lo que hace falta para enviar: el emisor, los datos del
   productor, la vía y su estado y, si la pasarela está configurada, le pregunta si puede presentar ahora.
3. Debajo sale el resultado, línea a línea, y «Puede enviar» o «No puede enviar: {motivo}».
4. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.» y «Probar la conexión» va deshabilitado.
Entra: la configuración del Hub; la respuesta de la sonda de la pasarela.
Sale: el resultado como evento «Prueba de conexión» (avisa `verifactu.diagnostic.run`), sin crear ningún
registro ni tocar la cadena.
Si falla: lo que falta, dicho en el resultado. Nunca presenta un registro de muestra: un registro remitido no
se puede deshacer.
Implicados: VERIFACTU-F15

### VERIFACTU-F11 Crear una factura de prueba
<!-- origen: wf:cadena-fiscal#rec_fiscal-f14 old:verifactu/workflow/configuracion.md#verifactu-f11 -->
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. Con el negocio en pruebas, en **VeriFactu → Ajustes**, «Prueba en vivo», pulsa «Crear factura de prueba»
   («Creando…»). En producción el botón no aparece.
2. VeriFactu pide a Facturación un tique (F2) de una línea «Prueba VeriFactu» de 1,00 € más el 21 % de IVA en
   la serie TICKET, por la misma puerta que el alta manual (INVOICE-F03).
3. Sale «Factura de prueba {número} creada: su registro está en Registros.».
4. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.» y «Crear factura de prueba» va deshabilitado.
Entra: nada que escribir.
Sale: una factura real de Facturación en pruebas y su registro, que sale como cualquier otro.
Si falla: el rechazo de Facturación (sin emisor, sin permiso de emitir).
Implicados: INVOICE-F03

### VERIFACTU-F12 Consultar la declaración responsable
<!-- origen: old-saas:SAAS_DASHBOARD-F161 old-hub:HUB-F310 old:verifactu/workflow/configuracion.md#verifactu-f12 qa:modules/verifactu/responsible-declaration-and-status -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ajustes
Pasos:
1. En **VeriFactu → Ajustes**, tarjeta «Declaración responsable», «Leer la declaración firmada» abre la
   publicada en erplora.com; al lado, «Versión de la declaración».
2. «Datos identificativos de este sistema» enseña los datos del productor, la versión instalada y el número de
   instalación (el identificador de este negocio en ERPlora).
Entra: la declaración (fija en la versión del Hub).
Sale: nada; es consulta.
Si falla: el mensaje del fallo.
Implicados: ninguno

### VERIFACTU-F13 Registrar una factura emitida
<!-- origen: wf:restaurante-dia#rec_restaurante-f12 fi:hub/domain#build_record_output-recordinput-nucleo-de-encadenado fi:hub/domain#create_record-command-issue-verifactu-2 fi:hub/domain#derive_tax_rate-tipo-iva-del-registro-a-partir-del-desglose-real fi:hub/domain#ingest_invoice-listener-de-invoice-created-invoice-rectified fi:hub/domain#modulo-chain-formatos-aeat-huella-sha-256-url-qr wf:peluqueria-dia#rec_peluqueria-f11 wf:cadena-fiscal#rec_fiscal-f04 fi:modules/verifactu#command-handler-nativo-verifactu-records-create-create_record fi:modules/verifactu#command-handler-nativo-verifactu-records-ingest_invoice-ingest_invoice fi:modules/verifactu#event-events-listen-invoice-created-invoice-rectified old-hub:HUB-F317 old-hub:HUB_VERIFACTU-F01 old-hub:HUB_VERIFACTU-F04 old:verifactu/workflow/registro-y-envio.md#verifactu-f13 qa:modules/verifactu/record-and-qr-for-each-receipt -->
Estado: hecho — Facturación lo pide por nombre dentro de su emisión; el relay del outbox del worker queda de respaldo
Actor: quien emite (su propia sesión); en la reacción al aviso, el sistema
Pantalla: ninguna
Pasos:
1. Facturación emite una factura o un tique (al cobrar, a mano o la factura de prueba).
2. En la **misma transacción** que la emite, con la sesión de quien emite, Facturación pide a VeriFactu su
   registro (el registro lleva a ese usuario en «creado por»). Solo si la base de datos falla un momento (un
   cerrojo, una conexión) el documento queda «pendiente» y la reacción al aviso `invoice.invoice.issued` lo
   sella después, como el sistema. Si el negocio no está en España, VeriFactu no registra nada: la factura se
   emite igual, sin registro ni QR, como con la app apagada, y nunca se deshace por eso.
3. VeriFactu lee la factura (número, fechas, emisor, cliente, importes, desglose por clave fiscal y la factura
   que rectifica o sustituye) y la comprueba: el desglose suma la base y la cuota, la cuota de cada clave
   cuadra con su tipo, no pasa de 12 claves (las que admite la AEAT; nunca se recorta), una factura ordinaria
   no suma en negativo, una completa identifica al cliente.
4. Sella el registro de **alta**: bloquea la fila de su cadena (NIF del emisor y entorno), le da el siguiente
   número, calcula su huella con la del registro anterior y fija su QR en la sede del entorno (pruebas o real).
   Valida **siempre** su XML contra el esquema oficial; con los datos del productor ya recibidos lo guarda, y
   sin ellos lo valida con un `SistemaInformatico` provisional que no se guarda (su XML se construye antes del
   primer envío).
5. El registro aparece en **Registros** como «Pendiente» y sale en la siguiente pasada (VERIFACTU-F15).
Entra: la factura emitida, de Facturación (por su id).
Sale: el registro sellado (avisa `verifactu.record.created`).
Si falla: si no cuadra o el XML no pasa el esquema, no se escribe nada ni se gasta número, y **la emisión
entera se deshace** (Facturación devuelve el número a su serie): reintentarlo fallaría igual. Una factura que
ya tiene registro contesta el mismo: nunca dos registros ni dos números, tampoco con dos entregas a la vez.
Una factura que no existe no hace nada.
Implicados: INVOICE-F01, INVOICE-F02, INVOICE-F03, INVOICE-F04, INVOICE-F05

### VERIFACTU-F14 Registrar una factura rectificativa
<!-- origen: fi:hub/domain#ingest_invoice-listener-de-invoice-created-invoice-rectified wf:cadena-fiscal#rec_fiscal-f12 fi:modules/verifactu#command-handler-nativo-verifactu-records-ingest_invoice-ingest_invoice fi:modules/verifactu#event-events-listen-invoice-created-invoice-rectified old-hub:HUB_VERIFACTU-F01 old:verifactu/workflow/registro-y-envio.md#verifactu-f14 -->
Estado: hecho — igual que F13
Actor: sistema
Pantalla: ninguna
Pasos:
1. Facturación emite una rectificativa (R1–R5, por diferencias, importes negativos): una devolución, la
   anulación de una venta (R5 del tique) o una corrección a mano.
2. VeriFactu la registra como un **alta** más, con su tipo R, `TipoRectificativa = I` y la factura que
   rectifica (NIF, número y fecha). La anulación de una venta es una rectificativa: **no** es un registro de
   anulación (eso es VERIFACTU-F30).
Entra: la rectificativa emitida, de Facturación.
Sale: el registro de alta de la rectificativa (avisa `verifactu.record.created`).
Si falla: como VERIFACTU-F13.
Implicados: INVOICE-F07, INVOICE-F08, INVOICE-F09, INVOICE-F10

### VERIFACTU-F15 Enviar el registro a la AEAT y recoger su respuesta
<!-- origen: fi:hub/domain#modulo-aeat-xml-soap-identidad-pkcs-12-post-tls-mutua-parseo fi:hub/domain#transmit_record-transmit_one-apply_transmission-command-issue-verifactu-3 old-hub:HUB_VERIFACTU-F04 qa:modules/verifactu/record-and-qr-for-each-receipt fi:modules/verifactu#command-handler-nativo-verifactu-records-transmit-transmit_record old-hub:HUB_VERIFACTU-F05 old-hub:HUB_VERIFACTU-F06 old-hub:HUB_VERIFACTU-F07 old-hub:HUB_VERIFACTU-F08 old:verifactu/workflow/registro-y-envio.md#verifactu-f15 wf:cadena-fiscal#rec_fiscal-f05 -->
Estado: hecho — lo envía el worker por la pasarela del SaaS; sin `VERIFACTU_GATEWAY_URL` los registros esperan en la cola
Actor: sistema
Pantalla: ninguna
Pasos:
1. La pasada de envío (cada minuto, VERIFACTU-F20, o «Procesar cola») toma cada cadena cuya espera de la AEAT
   (`TiempoEsperaEnvio`) ya pasó y cuyo primer registro pendiente ya toca, y junta sus registros pendientes en
   orden de cadena, hasta 1.000 en un envío.
2. Construye el sobre (el obligado, quien presenta si es ERPlora y, si alguno ya intentó salir antes,
   `Incidencia = S`), lo valida contra el esquema y lo manda a la pasarela de ERPlora, que lo presenta a la
   AEAT del entorno de los registros con el sello de ERPlora o con tu certificado y devuelve su respuesta.
3. Con la respuesta, cada registro queda «Aceptado» (con su CSV), «Aceptado con errores» (está en la AEAT; se
   guarda el código), o «Rechazado» (con el código y el mensaje de la AEAT; VERIFACTU-F24). Un «duplicado»
   (3000) de un registro que la AEAT ya tenía aceptado cuenta como aceptado. La espera que pide la AEAT se
   guarda en la cadena y el siguiente envío no sale antes.
4. Si no hay respuesta (la pasarela o la AEAT caídas): el registro sigue «Pendiente» con «Intentos» +1 y el
   próximo intento a 5, 10, 20, 40 y 60 minutos, sin límite. Si la petición salió pero no volvió nada, queda
   «Enviado» y se vuelve a mandar con incidencia (la AEAT dirá «duplicado» si ya lo tenía).
Entra: los registros pendientes; la vía; la respuesta de la pasarela.
Sale: el estado y la respuesta en cada registro (avisa `verifactu.record.transmitted` y, según el caso,
`verifactu.record.rejected` o `verifactu.record.accepted_with_errors`, sin importes).
Si falla: sin pasarela configurada, sin datos del productor o sin vía lista, no se manda nada y cada registro
dice por qué espera (VERIFACTU-F17). Nunca se da por aceptado un registro sin la respuesta de la AEAT. Un negocio
de fuera de España no envía nada nunca: lo que quedó sellado antes se guarda tal cual, sin salir, y dice por qué.
Implicados: VERIFACTU-F20, FLOW-F04 (la tarjeta de la galería de Automatizaciones que crea una tarea urgente cuando
la AEAT rechaza un registro)

### VERIFACTU-F16 Consultar los registros y su estado
<!-- origen: qa:modules/verifactu/responsible-declaration-and-status fi:modules/verifactu#query-verifactu-records-list old:verifactu/workflow/registro-y-envio.md#verifactu-f16 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Registros
Pasos:
1. Abre **VeriFactu → Registros**.
2. Busca por número de factura, secuencia, nombre o NIF del emisor, o filtra por estado, tipo, tipo de
   factura, entorno, fecha y total.
3. Cada fila enseña su estado con color: verde «Aceptado», ámbar «Pendiente» / «Enviado» / «Aceptado con
   errores», rojo «Rechazado»; y su entorno, para no confundir pruebas con producción.
Entra: los registros.
Sale: nada; es consulta.
Si falla: el mensaje con «Reintentar».
Implicados: INVOICE-F16

### VERIFACTU-F17 Ver el detalle de un registro y por qué espera
<!-- origen: old-hub:HUB_VERIFACTU-F05 fi:modules/verifactu#query-verifactu-records-get old:verifactu/workflow/registro-y-envio.md#verifactu-f17 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ficha de registro
Pasos:
1. En **Registros**, pulsa una fila.
2. Se abre «Registro {número}» con la factura, la cadena, el QR, la respuesta de la AEAT y el XML.
3. Si no está en la AEAT, «Aún no está en la AEAT» dice por qué («La pasarela de envío de ERPlora no está
   configurada en este servidor», «Sin vía de envío
   lista», «La AEAT pidió esperar hasta las {hora}», «No se pudo contactar: {motivo}») y cuándo: «Sale solo en
   la próxima pasada, en orden y declarado como envío tardío si ya falló antes. No tienes que hacer nada.»
   con el «Próximo intento».
4. En un negocio de fuera de España dice solo «este negocio no está en España: VeriFactu solo es para negocios de
   España, así que no se envía nada a la AEAT», sin próximo intento ni botones para enviar, subsanar o anular:
   nunca sale.
Entra: el registro.
Sale: nada; es consulta.
Si falla: «Registro no encontrado» o el mensaje del fallo.
Implicados: VERIFACTU-F15

### VERIFACTU-F18 Cotejar el QR en la sede de la AEAT
<!-- origen: fi:hub/domain#modulo-chain-formatos-aeat-huella-sha-256-url-qr old:verifactu/workflow/registro-y-envio.md#verifactu-f18 wf:cadena-fiscal#rec_fiscal-f08 -->
Estado: hecho
Actor: empleado, responsable, administrador, cliente
Pantalla: Registros
Pasos:
1. En **Registros**, «Cotejar en la AEAT» en la fila (o en la ficha) abre en otra pestaña la página de cotejo
   de la AEAT con el NIF del emisor, el número, la fecha y el importe.
2. Un registro nacido en pruebas lleva a la sede de pruebas; uno de producción, a la sede real.
3. El cliente hace lo mismo escaneando el QR de su tique o su factura.
Entra: el enlace del QR fijado al sellar.
Sale: nada en el Hub.
Si falla: un registro que aún no ha salido se ve en la AEAT como no encontrado; uno rechazado, nunca.
Implicados: VERIFACTU-F19

### VERIFACTU-F19 Dar el QR y el estado fiscal al tique y a la factura
<!-- origen: wf:restaurante-dia#rec_restaurante-f12 wf:peluqueria-dia#rec_peluqueria-f11 qa:verticals/beauty/06-fiscal-and-printing wf:cadena-fiscal#rec_fiscal-f07 qa:modules/verifactu/record-and-qr-for-each-receipt fi:modules/verifactu#query-verifactu-records-by_invoice old:verifactu/workflow/registro-y-envio.md#verifactu-f19 -->
Estado: hecho (Ventas e Impresión lo piden por nombre)
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cuando Ventas, Facturación o Impresión pintan un documento, piden a VeriFactu el registro de su factura.
2. VeriFactu devuelve el más reciente: su enlace y su imagen de QR, su CSV, su estado, su tipo y su huella.
Entra: el id de la factura.
Sale: el registro (`verifactu.record.by_invoice`); sin registro, nada (el documento sale sin QR).
Si falla: sin VeriFactu activa, sin permiso de consulta o en un negocio de fuera de España, el documento sale sin
QR ni recibo de VeriFactu.
Implicados: INVOICE-F17, INVOICE-F18

### VERIFACTU-F20 Enviar después lo que no pudo salir (contingencia automática)
<!-- origen: fi:hub/domain#process_contingency_queue-scheduled-task-trigger-manual-issue-verifactu-7 fi:modules/verifactu#command-handler-nativo-verifactu-contingency-process-process_contingency_queue fi:modules/verifactu#query-verifactu-contingency-list old-hub:HUB-F311 old-hub:HUB_VERIFACTU-F10 old:verifactu/workflow/contingencia.md#verifactu-f20 wf:cadena-fiscal#rec_fiscal-f06 -->
Estado: hecho — la corre el worker cada minuto (en la fase 1, sobre un solo hub)
Actor: sistema
Pantalla: Contingencia
Pasos:
1. Mientras se vende nada se para por esto: si la pasarela, la AEAT o la red están caídas, el cobro sigue y el
   registro espera.
2. Cada minuto (tarea programada `process_queue`) el sistema hace la pasada de VERIFACTU-F15 en todas las
   cadenas a las que les toca, cada una en su entorno; si se perdieron pasadas (servidor parado), al volver
   se hace una sola.
3. Lo que vuelve a fallar espera más (5, 10, 20, 40 y 60 minutos), sin límite de intentos.
4. Queda el evento «Cola procesada: {enviados} enviados, {aceptados} aceptados, {rechazados} rechazados, {en
   espera} en espera».
Entra: los registros pendientes.
Sale: los envíos y sus respuestas (avisa `verifactu.contingency.processed`).
Si falla: lo que no sale sigue en la cola con su motivo; en un negocio de fuera de España no sale nunca.
Implicados: VERIFACTU-F15

### VERIFACTU-F21 Procesar la cola a mano
<!-- origen: fi:hub/domain#process_contingency_queue-scheduled-task-trigger-manual-issue-verifactu-7 fi:modules/verifactu#command-handler-nativo-verifactu-contingency-process-process_contingency_queue old-hub:HUB-F312 old:verifactu/workflow/contingencia.md#verifactu-f21 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Contingencia
Pasos:
1. En **VeriFactu → Contingencia**, pulsa «Procesar cola» («Procesando…»).
2. Se hace en ese momento la misma pasada que la automática.
3. Debajo de la tabla sale el resultado; la tabla se pone al día sola.
Entra: la cola.
Sale: como VERIFACTU-F20.
Si falla: sin pasarela, «La pasarela de envío de ERPlora no está configurada en este servidor: los registros
siguen en la cola y saldrán en cuanto lo esté.».
Implicados: VERIFACTU-F20

### VERIFACTU-F22 Reintentar una entrada de la cola
<!-- origen: fi:modules/verifactu#command-sql-declarativo-verifactu-contingency-retry-verifactu-contingency-cancel old:verifactu/workflow/contingencia.md#verifactu-f22 -->
Estado: hecho
Actor: responsable, administrador
Pantalla: Contingencia
Pasos:
1. En **VeriFactu → Contingencia**, pulsa «Reintentar» en la fila.
2. El registro (y los anteriores de su cadena, que salen antes que él) pasan a salir en la siguiente pasada;
   los intentos se conservan.
Entra: el registro elegido.
Sale: el registro reprogramado (avisa `verifactu.contingency.retried`).
Si falla: un registro aceptado o rechazado no está en la cola: «Este registro no está en la cola.».
Implicados: VERIFACTU-F21

### VERIFACTU-F23 Descartar una entrada de la cola
<!-- origen: fi:modules/verifactu#command-sql-declarativo-verifactu-contingency-retry-verifactu-contingency-cancel old:verifactu/workflow/contingencia.md#verifactu-f23 -->
Estado: descartado — un registro generado no se descarta nunca: sale de la cola al enviarse (VERIFACTU-F25), porque la
AEAT ya lo tiene (VERIFACTU-F35) o subsanado con uno nuevo (VERIFACTU-F24)
Actor: ninguno
Pantalla: ninguna
Pasos:
1. Un registro que está en la cola tiene que llegar a la AEAT (FAQ §5); uno aceptado ya no está en la cola.
2. Lo único que sale de la cola sin un envío nuevo es lo que la AEAT **ya tiene**, preguntándoselo
   (VERIFACTU-F35); un rechazo se subsana con un registro nuevo (VERIFACTU-F24).
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: VERIFACTU-F24, VERIFACTU-F35

### VERIFACTU-F24 Actuar ante un registro rechazado por la AEAT
<!-- origen: wf:cadena-fiscal#rec_fiscal-f12 old-hub:HUB_VERIFACTU-F08 old:verifactu/workflow/contingencia.md#verifactu-f24 -->
Estado: hecho
Actor: administrador
Pantalla: Ficha de registro
Pasos:
1. El registro sale en rojo «Rechazado» en **Registros**; en **Eventos** queda «Envío fallido» con el motivo.
2. En su ficha, «La AEAT lo ha rechazado» con el código y el mensaje literales de la AEAT y qué hacer: si el
   error está en los datos de la factura (un NIF de cliente que la AEAT no reconoce, un importe), se corrige
   **en Facturación** con una rectificativa; si no (un error de la cadena tras restaurar una copia, un fallo
   nuestro), «Subsanar».
3. «Subsanar» (con confirmación) sella un registro **nuevo** de la misma factura, leída otra vez, marcado como
   subsanación, que entra en la cola. El rechazado se queda tal cual. `RechazoPrevio` según la Descripción del
   servicio web VERI*FACTU v1.0.3: `X` si la AEAT no tiene ningún registro de esa factura (se rechazó el alta
   inicial; §9.1.3, «alta por rechazo»); `S` si la AEAT sí la tiene y lo rechazado fue una subsanación
   posterior.
4. Un «Aceptado con errores» también se puede subsanar (`Subsanacion = S`, `RechazoPrevio = N`; §9.1.2).
Entra: el registro rechazado o aceptado con errores.
Sale: el registro de subsanación (avisa `verifactu.record.created`).
Si falla: solo se subsana un registro de alta rechazado o aceptado con errores, y solo el último de su
factura: «Este registro no se puede subsanar.».
Implicados: INVOICE-F08

### VERIFACTU-F25 Reenviar un registro concreto
<!-- origen: fi:hub/domain#transmit_record-transmit_one-apply_transmission-command-issue-verifactu-3 fi:modules/verifactu#command-handler-nativo-verifactu-records-transmit-transmit_record old-hub:HUB_VERIFACTU-F11 old:verifactu/workflow/contingencia.md#verifactu-f25 -->
Estado: hecho — por la pasarela del SaaS
Actor: responsable, administrador, asistente
Pantalla: Ficha de registro
Pasos:
1. En la ficha de un registro pendiente o enviado sin respuesta, pulsa «Enviar ahora».
2. Sale ya su cadena hasta él (los anteriores pendientes van delante, en orden), si la espera de la AEAT ya
   pasó.
3. El registro queda con la respuesta de la AEAT, como en VERIFACTU-F15.
Entra: el registro elegido (por su id o por el número de su factura).
Sale: el envío y su respuesta (avisa `verifactu.record.transmitted`).
Si falla: sin pasarela, «La pasarela de envío de ERPlora no está configurada en este servidor: el registro
sigue pendiente y saldrá en cuanto lo esté.»; ya aceptado, «Este registro ya está en la AEAT.»; con la espera
de la AEAT en curso, «La AEAT pidió esperar: sale solo a las {hora}.». Nunca dice «aceptado» sin respuesta.
Implicados: VERIFACTU-F15

### VERIFACTU-F26 Verificar la cadena de huellas
<!-- origen: fi:hub/domain#validate_chain-command-issue-verifactu-4 fi:modules/verifactu#command-handler-nativo-verifactu-chain-validate-validate_chain fi:modules/verifactu#query-verifactu-chain-status old-hub:HUB_VERIFACTU-F12 old:verifactu/workflow/cadena.md#verifactu-f26 -->
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Recuperación
Pasos:
1. En **VeriFactu → Recuperación**, con el «NIF del emisor», pulsa «Validar cadena» («Validando…»).
2. El sistema recalcula la huella de cada registro de la cadena del entorno actual y comprueba que cada uno
   lleva la del anterior.
3. Sale «Operación completada.» y el veredicto: «Cadena de huellas íntegra: {total} registro(s) con su
   encadenado SHA-256 verificado ({nif}).» o «Cadena de huellas ROTA en la secuencia {seq} ({nif}).».
Entra: los registros de la cadena.
Sale: el veredicto como evento (avisa `verifactu.chain.validated`). Solo lee: no repara nada ni re-audita los
importes.
Si falla: sin registros de ese NIF, «No hay registros de ese emisor en este entorno.».
Implicados: VERIFACTU-F28

### VERIFACTU-F27 Consultar lo que tiene la AEAT
<!-- origen: fi:hub/domain#helpers-de-consulta-recuperacion-run_consult-aeat_snapshot_ops-resolve_nif-next_sequence-environment_of-year_month-iso_date-short fi:hub/domain#query_aeat_records-snapshot-de-la-aeat-issue-verifactu-3 fi:modules/verifactu#command-handler-nativo-verifactu-aeat-query_recent-query_aeat_records fi:modules/verifactu#query-verifactu-aeat-records-list old-hub:HUB_VERIFACTU-F13 old:verifactu/workflow/cadena.md#verifactu-f27 -->
Estado: hecho — por la pasarela del SaaS (`/internal/verifactu/query`)
Actor: responsable, administrador
Pantalla: Recuperación
Pasos:
1. En **VeriFactu → Recuperación**, pulsa «Consultar AEAT» («Consultando…»).
2. El sistema pregunta a la AEAT, por la pasarela, por los registros de ese emisor del mes en curso.
3. La tabla «Últimos registros en la AEAT» se llena y sale «Operación completada.».
4. En la tabla, busca por factura, huella o CSV («Buscar factura, huella o CSV…»), ordena por cualquier columna y
   filtra por «Estado» (Correcto, Aceptado con errores, Anulado) o por «Fecha» desde el embudo; sin coincidencias,
   «Sin resultados»; sin consulta todavía, «Sin datos de la AEAT. Pulsa «Consultar AEAT».».
Entra: el NIF del emisor; la respuesta de la AEAT.
Sale: la foto de lo que tiene la AEAT, que sustituye a la anterior (avisa `verifactu.aeat.queried`). No toca
la cadena.
Si falla: sin pasarela, el mensaje de la pasarela no configurada; un rechazo de la AEAT, su mensaje.
Implicados: VERIFACTU-F28

### VERIFACTU-F28 Recuperar la cadena desde la AEAT tras restaurar una copia
<!-- origen: fi:hub/domain#recover_from_aeat-recover_manual-recuperacion-de-cadena-wasm-todo-9 fi:modules/verifactu#command-handler-nativo-verifactu-recovery-from_aeat-recover_from_aeat old-hub:HUB_VERIFACTU-F09 old-hub:HUB_VERIFACTU-F14 old:verifactu/workflow/cadena.md#verifactu-f28 -->
Estado: hecho — por la pasarela del SaaS (`/internal/verifactu/query`)
Actor: administrador
Pantalla: Recuperación
Pasos:
1. Tras restaurar una copia de la base de datos (la AEAT tiene registros que la copia no), deja de emitir y
   abre **VeriFactu → Recuperación**.
2. Pulsa «Recuperar cadena desde la AEAT» y confirma («Se reconstruirá la continuidad local desde el último
   registro disponible en la AEAT. Verifica el NIF del emisor antes de continuar.»).
3. El sistema consulta a la AEAT y ancla la cadena del entorno actual en el último registro (por su fecha de
   generación) que la AEAT tiene de ese emisor en el mes en curso. Sale «Operación completada.».
Entra: el NIF del emisor; la respuesta de la AEAT.
Sale: un ancla nueva (avisa `verifactu.chain.recovered`): el siguiente registro se encadena sobre ella.
Si falla: si la AEAT no tiene registros de ese emisor este mes, «La AEAT no tiene registros de ese emisor
este mes: no hay nada que recuperar.» y no se ancla nada; con registros pendientes en la cadena, «Antes tienen
que salir los registros pendientes de esta cadena.».
Implicados: VERIFACTU-F26

### VERIFACTU-F29 Continuar la cadena de otra aplicación (migración)
<!-- origen: fi:hub/domain#recover_from_aeat-recover_manual-recuperacion-de-cadena-wasm-todo-9 fi:modules/verifactu#command-handler-nativo-verifactu-recovery-manual-recover_manual old-hub:HUB_VERIFACTU-F15 old:verifactu/workflow/cadena.md#verifactu-f29 -->
Estado: hecho
Actor: administrador
Pantalla: Recuperación
Pasos:
1. En **VeriFactu → Recuperación**, bloque «Continuar cadena manualmente (migración)», escribe la «Última
   huella (64 hex)» de la aplicación anterior, el «Nº de factura» y la «Fecha» de ese último registro.
2. Pulsa «Continuar desde esta huella» y confirma («La huella indicada será el antecedente del próximo
   registro fiscal. Usa esta opción únicamente durante una migración.»).
3. Sale «Operación completada.»; la próxima factura se encadena sobre esa huella.
Entra: la huella, el número y la fecha del último registro de la aplicación anterior.
Sale: un ancla nueva (avisa `verifactu.chain.recovered`).
Si falla: una huella que no tiene 64 caracteres hexadecimales, «La huella debe tener 64 caracteres
hexadecimales»; sin número o fecha, que son parte del encadenado, el campo lo pide; con registros pendientes,
como VERIFACTU-F28.
Implicados: ninguno

### VERIFACTU-F30 Anular un registro enviado por error
<!-- origen: fi:hub/domain#create_record-command-issue-verifactu-2 fi:modules/verifactu#command-handler-nativo-verifactu-records-create-create_record old-hub:HUB_VERIFACTU-F03 old:verifactu/workflow/cadena.md#verifactu-f30 qa:modules/verifactu/fiscal-cancellation -->
Estado: hecho
Actor: administrador, asistente
Pantalla: Ficha de registro
Pasos:
1. Solo para una factura que **nunca debió emitirse** (un duplicado, una prueba hecha en producción). Una
   devolución o una corrección no se anula: es una rectificativa en Facturación (VERIFACTU-F14).
2. En la ficha del registro de alta, pulsa «Anular registro», escribe el motivo y confirma («Se declarará a la
   AEAT que esta factura se emitió por error. La factura sigue en Facturación.»).
3. Se sella un registro de **anulación** encadenado, que sale como cualquier otro, y aparece en Registros con
   tipo «Anulación».
Entra: el registro de alta (o el número de su factura).
Sale: el registro de anulación (avisa `verifactu.record.created`).
Si falla: un alta rechazada no se anula (no está en la AEAT); una ya anulada, tampoco: «Este registro no se
puede anular.». Si la AEAT rechazó la anulación, se puede volver a anular: la nueva lleva `RechazoPrevio = S`
(§9.2.2, «anulación por rechazo»).
Implicados: INVOICE-F07

### VERIFACTU-F31 Vigilar los envíos desde las pantallas
<!-- origen: fi:modules/verifactu#query-verifactu-events-list fi:modules/verifactu#query-verifactu-stats-contingency_summary fi:modules/verifactu#query-verifactu-stats-events_recent fi:modules/verifactu#query-verifactu-stats-records_by_status fi:modules/verifactu#widget-verifactu-pending-kpi-verifactu-contingency-stat-verifactu-by_status-bar-list-verifactu-events-timeline old:verifactu/workflow/control.md#verifactu-f31 -->
Estado: hecho — también desde los cuatro paneles del Inicio
Actor: empleado, responsable, administrador
Pantalla: Registros, Contingencia, Eventos, Inicio
Pasos:
1. **Registros** y **Contingencia** dicen qué falta por llegar; **Eventos**, qué pasó. Las tres se ponen al día
   solas.
2. En el **Inicio**, el panel «Pendientes VeriFactu» (encendido de serie) cuenta lo que aún no está en la AEAT
   (pendiente, enviado sin respuesta o rechazado); desde «Personalizar panel» se añaden «Cola de contingencia» (lo
   que espera en la cola, con «En cola de contingencia» bajo la cifra, en naranja si espera y en rojo si ya ha
   fallado algún intento), «Registros por estado» y «Eventos AEAT recientes» (los ocho últimos, con su hora, su tipo
   y su frase). Todos se ponen al día solos y los ve quien puede consultar los registros.
3. Los resúmenes (pendientes, por estado, cola y últimos eventos) se pueden pedir al asistente o por la API.
Entra: los registros y los eventos.
Sale: nada; es consulta.
Si falla: el mensaje con «Reintentar».
Implicados: ninguno

### VERIFACTU-F32 Impedir apagar la app con registros sin enviar
<!-- origen: fi:modules/verifactu#query-verifactu-stats-compliance_summary old-hub:HUB-F314 old-hub:HUB-F316 old:verifactu/workflow/control.md#verifactu-f32 -->
Estado: hecho — la plataforma pregunta al apagar (`base.app.disable`, hub#256) y VeriFactu responde con su
`can_disable` (hub#267, FIX-BASE-APP-TURN-OFF-VETO)
Actor: sistema
Pantalla: Hub: Apps
Pasos:
1. Al apagar VeriFactu, la plataforma le pregunta cuántos registros no están todavía en la AEAT: los pendientes
   (también los que esperan su reintento) y los enviados sin respuesta. Facturación no se puede apagar mientras
   VeriFactu esté encendida, porque VeriFactu la necesita.
2. Si queda alguno, lo niega y VeriFactu sigue encendida. Lo que la AEAT ya contestó (aceptado, aceptado con errores
   o rechazado) no cuenta: un rechazo se subsana con un registro nuevo, que cuenta mientras no salga.
3. En un negocio de fuera de España no lo niega nunca: sus registros no se van a enviar, así que apagarla no para
   nada; se guardan tal cual.
Entra: la petición de apagar.
Sale: nada si se niega; la app apagada si no queda nada por enviar.
Si falla: «VeriFactu aún tiene {n} registros por enviar a la AEAT. Espera a que se envíen o arréglalos antes de
desactivarla.» (con uno: «VeriFactu aún tiene 1 registro por enviar a la AEAT. Espera a que se envíe o arréglalo
antes de desactivarla.»).
Implicados: ninguno

### VERIFACTU-F33 Cesar la actividad
<!-- origen: old-hub:HUB-F309 old:verifactu/workflow/control.md#verifactu-f33 -->
Estado: descartado — el cese ante Hacienda es la baja censal del negocio (modelo 036/037), fuera de ERPlora; y un
negocio dado de baja en ERPlora ya no abre (410), así que no emite ni pasa a producción
Actor: administrador
Pantalla: ninguna
Pasos:
1. El cese ante Hacienda es la baja censal (modelo 036/037), fuera de ERPlora.
2. El software no envía nada.
Entra: nada.
Sale: nada.
Si falla: no aplica.
Implicados: ninguno

### VERIFACTU-F34 Renovar el certificado propio
<!-- origen: fi:hub/domain#inspect_certificate-extrae-y-persiste-caducidad-del-cert fi:hub/runtime#certificado-fiscal-del-negocio-core-adr-0079-0081 wf:cadena-fiscal#rec_fiscal-f01 fi:modules/verifactu#command-handler-nativo-verifactu-certificate-inspect-inspect_certificate old:verifactu/workflow/control.md#verifactu-f34 -->
Estado: hecho — en el Hub (subir el renovado sustituye al anterior)
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. «Mi certificado» enseña «Caduca el {fecha}» y, a 30 días o menos, «Caduca en {n} días: sube aquí el
   renovado.».
2. El certificado nuevo se sube como en VERIFACTU-F02 y sustituye al anterior; la cadena no cambia.
Entra: el certificado renovado.
Sale: el nuevo, en lugar del anterior.
Si falla: caducado y con la vía «mi certificado», los registros esperan con el motivo; si el servidor cambió
su clave de almacenamiento y no puede abrir el guardado, esperan con «tu certificado propio no se puede abrir
en este servidor: vuelve a subirlo».
Implicados: VERIFACTU-F02

### VERIFACTU-F35 Preguntar a la AEAT si ya tiene un registro de la cola
<!-- origen: nuevo (la cola no tenía salida para «enviado, sin respuesta» sin preguntar a la AEAT: Odoo `l10n_es_edi_verifactu` y la propia AEAT, con su consulta) -->
Estado: hecho — en la ficha del registro, en el admin de Django del Hub (soporte) y por la API
Actor: responsable, administrador (enviar); el staff de ERPlora desde el admin
Pantalla: Ficha de registro («Preguntar a la AEAT»); para el staff, el admin de Django (Registros → «Consultar a la
AEAT (sale de la cola si ya lo tiene)»)
Pasos:
1. Un registro se quedó «enviado, sin respuesta» (o pendiente) y puede que la AEAT ya lo tenga: en su ficha, pulsa
   «Preguntar a la AEAT».
2. Se consulta a la AEAT, por la pasarela de ERPlora, el emisor del registro en el mes de su fecha de expedición
   (como VERIFACTU-F27, que renueva la última foto).
3. Si la AEAT devuelve **ese mismo registro** (mismo emisor, número y huella), sale de la cola como «Aceptado» o
   «Aceptado con errores», según lo que diga la AEAT, sin perder sus intentos; queda un evento con quién lo hizo.
4. Si no lo tiene (o tiene otro registro de la misma factura, p. ej. el original de una subsanación), no cambia
   nada: sigue en la cola y se envía en la siguiente pasada.
Entra: el registro (id o número de su factura).
Sale: si la AEAT lo tenía y el registro (avisa `verifactu.record.reconciled`; la consulta, `verifactu.aeat.queried`).
En la ficha sale «La AEAT ya tiene {número}: sale de la cola.» o, en aviso, «La AEAT no tiene {número}: sigue en la
cola y sale en la siguiente pasada.».
Si falla: un registro aceptado o rechazado no está en la cola (la ficha no ofrece el botón; por la API, «Este
registro no está en la cola.»); sin pasarela o si la AEAT no contesta, el motivo, encima de los botones, y el
registro sigue en la cola.
Implicados: VERIFACTU-F22, VERIFACTU-F23, VERIFACTU-F27

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia persona)
y la API, con las mismas reglas y permisos. Pensado para la voz: un registro se nombra por el **número de su
factura** (`TICKET-2026-000012`) o por su secuencia; un emisor, por su NIF.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| La configuración: entorno, vía, certificado propio (titular, NIF, tipo, caducidad; nunca su material), estado de la autorización, datos del productor, declaración | ver | F02, F04, F08, F09, F12 | `verifactu.config.get` |
| Los registros, con búsqueda, filtros, orden y páginas (hasta 100) | ver | F16 | `verifactu.record.list` |
| Un registro, por su id o por el número de su factura, con su QR, su XML y por qué espera | ver | F17, F18 | `verifactu.record.get` |
| El registro vigente de una factura (QR, CSV, estado) | ver | F19 | `verifactu.record.by_invoice` |
| La cola: los registros que aún no están en la AEAT | ver | F20–F22 | `verifactu.contingency.list` |
| Los eventos de auditoría, con búsqueda por palabras y filtros | ver | F31 | `verifactu.event.list` |
| Cuántos registros no están en la AEAT (y si se puede apagar) | ver | F31, F32 | `verifactu.stats.compliance_summary`; al apagar, `can_disable` |
| Los registros por estado | ver | F31 | `verifactu.stats.records_by_status` |
| El resumen de la cola | ver | F31 | `verifactu.stats.contingency_summary` |
| Los últimos eventos | ver | F31 | `verifactu.stats.events_recent` |
| La última foto de lo que tiene la AEAT | ver | F27 | `verifactu.aeat_record.list` |
| El estado de cada cadena y su último veredicto | ver | F26 | `verifactu.chain.status` |
| El resultado de la última prueba de conexión | ver | F10 | `verifactu.diagnostic.last` |

Todas se pueden seguir en vivo.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Sella el registro de alta de una factura emitida (también la reacción a su aviso) | registrar | F13, F14 | `verifactu.record.create` |
| Subsana un registro rechazado o aceptado con errores | corregir | F24 | `verifactu.record.correct` |
| Sella el registro de anulación de una factura emitida por error | corregir | F30 | `verifactu.record.cancel` |
| Envía ya un registro (y los anteriores de su cadena) | enviar | F25 | `verifactu.record.transmit` |
| Hace la pasada de envío de la cola (también la tarea de cada minuto) | enviar | F20, F21 | `verifactu.contingency.process` |
| Pone un registro a salir en la siguiente pasada | enviar | F22 | `verifactu.contingency.retry` |
| Pregunta a la AEAT si ya tiene un registro de la cola; si lo tiene, sale de la cola como registrado | enviar | F35 | `verifactu.record.reconcile` |
| Verifica la cadena de huellas | ver | F26 | `verifactu.chain.validate` |
| Consulta a la AEAT los registros del mes | enviar | F27 | `verifactu.aeat.query` |
| Recupera la cadena desde la AEAT | configurar | F28 | `verifactu.chain.recover_from_aeat` |
| Continúa la cadena desde una huella externa | configurar | F29 | `verifactu.chain.recover_manual` |
| Prueba la conexión sin presentar nada | enviar | F10 | `verifactu.diagnostic.run` |
| Crea la factura de prueba (en pruebas) | configurar | F11 | `verifactu.test_invoice.create` |
| Elige la vía de envío | configurar | F04 | `verifactu.config.update` |
| Pasa a producción | configurar | F08 | `verifactu.config.go_live` |
| Vuelve a pruebas | configurar | F09 | `verifactu.config.back_to_testing` |
| Sube (o sustituye) el certificado propio | configurar | F02, F34 | `verifactu.certificate.upload` |
| Quita el certificado propio | configurar | F03 | `verifactu.certificate.remove` |
| Guarda lo que manda la cuenta de ERPlora (estado del otorgamiento, estado de la cuenta) | solo el sistema | F05, F08 | `verifactu.config.sync` |
| Fija el hub de plataforma de ERPlora al entorno de su despliegue | solo el sistema | — | `verifactu.config.follow_deployment` |
| Envía el otorgamiento de representación firmado a revisión | configurar | F05, F06 | `verifactu.representation.submit` |
| Da el modelo oficial en blanco (PDF) | configurar | F05 | `verifactu.representation.model` |

En un negocio de fuera de España, lo que sella un registro o habla con la AEAT o con la pasarela (registrar,
subsanar, anular, enviar ya, conciliar, consultar la AEAT, recuperar desde ella, probar la conexión, la factura de
prueba, pasar a producción y enviar el otorgamiento) contesta como con la app apagada: 404 `app_inactive`,
«VeriFactu solo es para negocios de España.». La pasada de la cola no envía nada y deja a cada registro su motivo
(`outside_spain`); el registro de una factura (`verifactu.record.by_invoice`) no se da.

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Registro creado | Todo registro sellado (alta, subsanación, anulación) | `record_id`, `invoice_id`, `invoice_number`, `record_type`, `sequence`, `environment` | `verifactu.record.created` |
| Registro enviado | Un envío con respuesta o sin ella | `record_ids`, `transmission_id`, `environment` | `verifactu.record.transmitted` |
| Registro rechazado | La AEAT lo rechaza | `record_id`, `invoice_number`, `code`, `message`, `environment` (sin importes) | `verifactu.record.rejected` |
| Aceptado con errores | La AEAT lo registra con un error | lo mismo | `verifactu.record.accepted_with_errors` |
| Cola procesada | Una pasada (a mano o programada) | `sent`, `accepted`, `rejected`, `waiting` | `verifactu.contingency.processed` |
| Registro reprogramado | «Reintentar» | `record_id` | `verifactu.contingency.retried` |
| Registro conciliado | La AEAT ya tenía un registro de la cola (VERIFACTU-F35) | `record_id`, `invoice_number`, `status`, `environment` | `verifactu.record.reconciled` |
| Cadena verificada | «Validar cadena» | `issuer_nif`, `environment`, `valid`, `total`, `first_invalid_sequence` | `verifactu.chain.validated` |
| Cadena recuperada | Recuperar desde la AEAT o a mano | `issuer_nif`, `environment`, `sequence`, `source` | `verifactu.chain.recovered` |
| Consulta a la AEAT | «Consultar AEAT» | `issuer_nif`, `count` | `verifactu.aeat.queried` |
| Prueba de conexión | «Probar la conexión» | `can_send` | `verifactu.diagnostic.run` |
| Configuración cambiada | Vía, entorno o lo que manda la cuenta | `fields` | `verifactu.config.changed` |

### A qué reacciona

| Aviso | De | Qué hace | Servicio |
|---|---|---|---|
| Documento emitido (`invoice.invoice.issued`) | Facturación | Sella su registro de alta (F13, F14) | `verifactu.record.create` |

Corre como el sistema, en su propia transacción, y es idempotente: un registro de alta por factura y entorno.
Es el **respaldo**: Facturación lo pide dentro de su emisión (contrato abajo) y el aviso de un documento ya
sellado no añade nada (`already`). En un negocio de fuera de España no reacciona (se da por entregado).

### Lo que necesita de otras apps

- **Facturación** (requisito): la factura emitida (`Invoice`), leída de su fila por su id; para la factura de
  prueba, su operación `invoice.invoice.create`.
  Un registro guarda su factura con `PROTECT` (la ley conserva las dos); lo que eso exige a las pruebas de
  Facturación, en «Contrato con Facturación».

### Quién la usa

| App | Para qué | Servicio |
|---|---|---|
| Facturación | Sellar el registro de cada documento dentro de su emisión | `verifactu.record.create` |
| Ventas, Facturación, Impresión | Poner el QR y el estado fiscal en el tique y la factura | `verifactu.record.by_invoice` |
| Plataforma (`base.app.disable`) | No apagar VeriFactu con registros sin enviar (en España) | `can_disable` de `VerifactuConfig` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver registros, cola, eventos, cadena y configuración; verificar la cadena | sí | sí | sí | sí | `verifactu.view_record` |
| Registrar una factura emitida (lo pide Facturación con la sesión de quien emite) | sí | sí | sí | sí | `verifactu.add_record` |
| Enviar, procesar y reintentar la cola, consultar a la AEAT, probar la conexión | sí | sí | sí | no | `verifactu.transmit_record` |
| Subsanar y anular registros | sí | sí | no | no | `verifactu.correct_record` |
| Subir y quitar el certificado propio, elegir la vía, pasar a producción y volver, recuperar la cadena, factura de prueba | sí | sí | no | no | `verifactu.configure` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`). Guardar lo
que manda la cuenta (`verifactu.sync_config`) no es de ningún papel: solo del sistema.

## Para quien lo mantiene

### Anatomía

`apps.py`, `models.py` (`Config`, `OwnCertificate`, `Chain`, `SendControl`, `Record`, `Event`, `AeatRecord`),
`migrations/`,
`schemas.py`, `services.py`, `queries.py`, `api.py`, `live.py`, `events.py`, `admin.py`, `locale/`,
`frontend/` y, puros y sin ORM: `chain.py` (formatos, huella, QR), `envelope.py` (el XML: `RegistroAlta`,
`RegistroAnulacion`, el sobre y la consulta), `xsd.py` (validación con los esquemas de `xsd/`), `aeat.py`
(lectura de las respuestas de la AEAT y de la consulta), `gateway.py` (cliente de la pasarela del SaaS),
`certificates.py` (abre e inspecciona el certificado propio y lo cifra y descifra; la fila la leen y escriben
`queries.py` y `services.py`) y
`producer.py` (los datos del productor que declara la declaración responsable). Un `tests/test_<fichero>.py`
por fichero, más `test_xsd.py` contra los esquemas reales, `test_integration_invoice.py` (Facturación real,
sin dobles), `test_concurrency.py` (sesiones reales en hilos; también una emisión cuyo cerrojo de cadena no
llega a tiempo y queda «pendiente») y `test_notifications.py` (escribir en el hub B no avisa al A).

### El Inicio (los «hooks» de `LiveAppConfig`, ronda PLAN-HUB 2026-10-21)

Los del `module.json` viejo (`setup` y `widgets`; no tenía `bell`), en `apps.py`. **Paso** `verifactu.sending_route`
(«Set up VeriFactu» / «Configura VeriFactu», `required=True` → «Importante» en pruebas, gh:hub#1726; ⛔ «Necesario
para facturar» donde `environment` de su fila es `production`, por `LEGAL_IN_PRODUCTION` de `base/home.py`: el nivel
es de `base`), sobre `verifactu.config.get` con `route_ready_for_production` (`not _route_sending_problem(config,
production, scope)`: vía propia con certificado vigente que este servidor abre, o vía ERPlora con el otorgamiento
aprobado; la exención del hub de ERPlora incluida; lo que le falte al servidor no cuenta, no es tarea del negocio),
permiso `verifactu.configure`, ruta `/verifactu/config`, `refresh_on` `verifactu.config.changed`. **Paneles** (permiso
`verifactu.view_record`, `refresh_on` = lo que `live.py` re-ejecuta): `pending` (kpi de
`verifactu.stats.compliance_summary.pending_count`, de serie), `contingency` (stat de `contingency_summary`,
`queued_count` y `severity`), `by_status` (bar-list de `records_by_status`) y `events` (componente
`RecentEventsPanel.vue`, que sigue `verifactu.stats.events_recent` con `limit` 8 y nombra el tipo con el catálogo de la
app: gh:verifactu#139). Tests: `test_apps.py` (declaración, textos `en` + `es`, iconos, eventos),
`test_integration_home.py` (por `base.setup.status` y `base.widget.list` reales, con dos hubs),
`test_queries.py` (`route_ready_for_production`), `RecentEventsPanel.test.ts` y la e2e
`tests/e2e/fix-verifactu-setup-hooks.spec.ts`.

### La cadena, la huella y el QR

- **Huella** (`chain.py`): SHA-256 en hexadecimal **mayúsculas** de
  `IDEmisorFactura={nif}&NumSerieFactura={número}&FechaExpedicionFactura={DD-MM-AAAA}&TipoFactura={tipo}&CuotaTotal={cuota}&ImporteTotal={total}&Huella={anterior}&FechaHoraHusoGenRegistro={ISO con huso}`
  para el alta, y
  `IDEmisorFacturaAnulada=…&NumSerieFacturaAnulada=…&FechaExpedicionFacturaAnulada=…&Huella=…&FechaHoraHusoGenRegistro=…`
  para la anulación. Importes en euros con dos decimales y punto (los céntimos se dividen en el límite), fecha
  `DD-MM-AAAA`, marca de tiempo con segundos enteros y huso (`2026-09-22T19:58:55+02:00`, hora de Madrid en la
  fase 1). Vectores: los tres casos oficiales de la AEAT (un alta, la siguiente y una anulación encadenadas) y
  las huellas de los 19 envíos reales aceptados por la preproducción (`tests/fixtures/*_sent_*.xml`).
- **Cadena** por `(NIF del emisor, entorno)`: la fila `Chain` guarda la secuencia, la huella, el número, la
  fecha y el NIF del último registro. Sellar bloquea esa fila (`select_for_update`) en la transacción del
  registro: dos facturas a la vez se ponen en cola, sin huecos ni dos registros con el mismo anterior, y un
  rechazo deshace el número. El primer registro lleva `PrimerRegistro = S`. Un ancla (recuperación desde la
  AEAT o a mano) solo cambia esa fila.
- **QR** (`chain.qr_url`): `https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=…&numserie=…&fecha=…&importe=…`
  en pruebas y `https://www2.agenciatributaria.gob.es/…` en producción, con los valores codificados RFC 3986;
  se fija al sellar con el entorno del registro. La imagen (SVG, corrección M) la pinta `qrcode` en el
  servidor y viaja como `data:` (la CSP admite `img-src data:`).

### El XML y la validación

- `envelope.py` porta **byte a byte** `aeat::build_soap` del motor actual, verificado contra la preproducción
  de la AEAT: los 19 sobres reales aceptados (`*_sent_*`) se reconstruyen idénticos en `test_envelope.py`.
  Añade lo que el motor no emitía: `FechaOperacion` (si difiere de la de expedición), `Subsanacion` y
  `RechazoPrevio` (`X` / `S` en el alta; `S` en una anulación tras otra anulación rechazada, §9.2.2). El desglose sale de `Invoice.tax_breakdown` (una entrada por clave fiscal): `tax` →
  `Impuesto` (`vat` 01, `ipsi` 02, `igic` 03, `other` 05), `regime` → `ClaveRegimen` (vacío = 01),
  `qualification` → `CalificacionOperacion` (`subject` S1, `subject_reverse` S2 con tipo y cuota 0 explícitos,
  `not_subject` N1, `not_subject_location` N2) u `OperacionExenta` (`exempt` con su `exempt_reason`, E6 sin
  causa); el recargo de equivalencia va dentro de su línea de IVA y solo si su tipo o su cuota no son cero;
  orden estable. Más de 12 claves (el máximo del esquema) es `UndeclarableRecord` / 409
  `verifactu.impossible_record` antes de sellar: nunca se recorta (declararía menos de lo cobrado).
- **Qué se guarda**: `Record.xml` es el **registro** (`<sum1:RegistroAlta>` o `<sum1:RegistroAnulacion>`),
  congelado; el sobre de un envío se monta con los registros de la cadena bajo **una** cabecera (obligado,
  `Representante` = ERPlora cuando presenta ERPlora y el obligado es otro, y `RemisionVoluntaria/Incidencia = S`
  si alguno ya intentó salir). La cabecera no entra en la huella. Cada registro enviado guarda el
  `transmission_id` y el SHA-256 del sobre que viajó.
- **XSD real** (`xsd.py`): `xmlschema` sobre `xsd/SuministroLR.xsd` (importa `SuministroInformacion.xsd`, que
  importa la firma `xmldsig-core-schema.xsd`), los tres en local y en modo `sandbox` (nunca red). Se valida el
  sobre de un solo registro **al sellar, siempre** (si no pasa, no hay registro ni número: uno inválido pararía
  su cadena para siempre) y cada sobre **antes de enviarlo**. El XML del registro se construye, se valida y se
  congela **al sellar** (el `SistemaInformatico` no espera a nada de la cuenta); uno guardado sin XML (sellado
  antes de T2b) lo construye su primer envío. Si aun así un sobre no pasa al enviarse, la
  cadena espera con `xml_invalid` y el evento crítico se anota **una vez**, no en cada pasada. La consulta
  (`ConsultaFactuSistemaFacturacion`) se valida contra `xsd/ConsultaLR.xsd` antes de salir.
  Procedencia de los esquemas: `SuministroLR.xsd` y `SuministroInformacion.xsd` del motor actual (los últimos
  de la AEAT, con E7/E8 y la clave 21), `ConsultaLR.xsd` de la sede de la AEAT (2026-10-15) y
  `xmldsig-core-schema.xsd` de la W3C; SHA-256 en `tests/test_xsd.py`.
- **SistemaInformatico** (`producer.py`): `NombreRazon` ERPLORA CLOUD SL, `NIF` B27593136,
  `NombreSistemaInformatico` ERPlora Hub, `IdSistemaInformatico` EC, `TipoUsoPosibleSoloVerifactu` S y
  `TipoUsoPosibleMultiOT` S, los de la declaración responsable v1 firmada (`saas-next/public/declaracion/v1`);
  `Version` = `APP_VERSION` (el commit de la imagen; `dev` en local), `NumeroInstalacion` = el identificador
  del negocio (el ámbito; en la fase 2, el id del hub) e `IndicadorMultiplesOT` **S siempre** (`MULTIPLE_OT`):
  ERPlora es una plataforma para muchos negocios, un sistema multi-obligado por definición, así que no depende de
  la cuenta (decisión del 2026-10-15, T2b; fuera `multiple_taxpayers` y `producer_facts_missing`).

### Contrato con Facturación (lo que `invoice` tiene que hacer)

1. **Dentro de la transacción de cada emisión** (`_issue` de `apps/invoice/services.py`, hecho), tras escribir el
   documento y su aviso, Facturación llama por nombre a `verifactu.record.create` con
   `{"invoice_id": "<uuid del documento>"}` y **la misma sesión** (el sellado síncrono lo firma quien emite; el
   de la reacción, el sistema), en un savepoint, y contesta `verifactu_status`:
   - `sealed`: el registro se escribió en el mismo COMMIT que el documento;
   - `unavailable`: `UnknownOperation` o 404 `app_inactive` (VeriFactu no está en este negocio) → sin registro;
   - `pending`: solo un error pasajero de la base de datos (`DatabaseError`: un cerrojo de la cadena que no
     llega, una conexión caída) → el documento queda emitido y la reacción al aviso lo sella después;
   - un rechazo de VeriFactu (409 `verifactu.impossible_record`, `verifactu.invalid_record`,
     `verifactu.recipient_required`, 403 sin permiso) es determinista (fallaría igual): **deshace la emisión
     entera** y la serie no gasta número; un error de programación tampoco se traga;
   - en **producción sin ruta a la AEAT**, 409 con el código de la ruta (`verifactu.representation_not_approved`,
     `verifactu.own_certificate_missing`,
     `verifactu.own_certificate_unreadable`) o del servidor (`verifactu.gateway_unavailable`,
     `verifactu.production_closed`; revisión del bloque fiscal, 2026-10-15): igual, nada se emite
     (working-rules §15; el `enforce_fiscal_road` del Hub antiguo, HUB-1935). Venta (`sale`) no lo deja pendiente:
     rechaza el cobro, la devolución o la anulación con ese 409. La reacción del sistema a un documento ya emitido
     no se rechaza: su registro se sella y espera, como el antiguo dejaba al relay entregar una cadena ya abierta.
   La respuesta (`RecordCreateOut`) trae `record.qr_url`, `record.qr_svg`, `record.status` y `already`.
2. **Lo que se lee de la fila** (`Invoice`, sin copiarlo a otro sitio): `number`, `issue_date`,
   `operation_date`, `issuer_tax_id`, `issuer_name`, `customer_tax_id`, `customer_name`, `customer_country`,
   `customer_id_type`, `invoice_type`, `rectification_kind`, `rectifies` (su `number`, `issue_date` e
   `issuer_tax_id`), `substitutes` (lo mismo), `tax_breakdown`, `base_amount`, `tax_amount`, `total_amount` y
   `description`.
3. **El respaldo**: `events.react` sella el registro de un documento «pending» o emitido sin VeriFactu cuando
   el relay del outbox del worker entrega `invoice.invoice.issued` (`{"invoice_id": …}`; `base/relay.py`, desde
   hub#105); `tests/test_relay.py` lo prueba con un tick real del worker y `test_services.py` entrega el aviso real
   del outbox a la reacción.
4. Facturación **no** pide nada al anular una venta: su R5 se registra como un alta más (VERIFACTU-F14). El
   registro de anulación (VERIFACTU-F30) es solo para una factura emitida por error.
5. **Los e2e de Facturación**: como un registro guarda su factura con `PROTECT`, su limpieza tiene que borrar
   antes los registros de VeriFactu de sus facturas (`tests/e2e/verifactu-records.spec.ts`, `cleanVerifactu`).

### Contrato con el SaaS

- **La pasarela** (`gateway.py`; en el SaaS, `fiscal_gateway/`, su README «Contrato con el Hub»), en
  `VERIFACTU_GATEWAY_URL` (la URL interna del SaaS; vacía = sin pasarela: nada se envía y nada se da por
  aceptado). Llamadas `POST` con JSON, firmadas como el resto de `/internal` (`X-Erplora-Timestamp` y
  `X-Erplora-Signature` = HMAC-SHA256 hex de `f"{timestamp}.{cuerpo}"` con `INTERNAL_SHARED_SECRET`, la v1; la
  pasarela acepta v1 sola o v2, y el Hub aún no firma v2). Tiempos: **Hub → pasarela, 5 s para conectar y 45 s
  para leer**; **pasarela → AEAT, 5 s y 30 s**: el Hub espera más que la pasarela a la AEAT.
  - `/internal/verifactu/submit` con `{"hub", "nif", "environment": "testing"|"production", "route":
    "erplora"|"own", "envelope", "certificate"?: {"p12_base64", "password"}}` → `200 {"aeat_status": <HTTP de
    la AEAT>, "aeat_body": "<respuesta SOAP de la AEAT>"}`. `certificate` solo con `route = "own"`: el
    certificado propio (VERIFACTU-F02) viaja descifrado en cada llamada y la pasarela no lo guarda; para
    presentarlo, su clave PEM pasa unos milisegundos por disco, en dos ficheros `0600` de un directorio
    temporal privado del SaaS que se borra en cuanto TLS los ha leído. `hub` nombra al negocio: en la fase 1, el
    slug de su host (`ctx.scope.key`); en la fase 2, el UUID de su registro. La pasarela acepta los dos (saas#25:
    UUID o un slug válido de `live.slugs`).
  - Lo que no es `200`: `404 {"error": {"code": "hub_unknown"}}` (el `hub` del cuerpo no es ningún hub del SaaS;
    saas#29; cualquier otro 404 es una puerta que aún no está y se reintenta); `409 {"error": {"code",
    "message"}}` con `nif_mismatch` (el sobre nombra a otro contribuyente; se decide antes de tocar la AEAT),
    `representation_not_approved`, `no_seal`, `no_certificate`, `certificate_invalid` o
    `environment_not_allowed`; `413 payload_too_large` (más de 10 MiB); `422 invalid_payload` (con `fields`):
    el Hub los toma como **rechazo** (`refused`, con su código y mensaje a la vista en el registro y en la prueba
    de conexión; `hub_unknown` y `representation_not_approved` con texto propio en/es en vez del mensaje del SaaS): sigue
    `pending` y no se reintenta solo, porque se rechazaría igual (lo sellado detrás espera con el mismo motivo, y la
    cola no le pone «próximo intento»); vuelve a la cola al cambiar la vía, subir el
    certificado o llegar una foto nueva de la cuenta, o a mano («Reenviar a la AEAT» del admin, «Enviar ahora»,
    «Reintentar»). `502 {"error": {"code": "aeat_unreachable", "sent"}}`: con `sent = true` la
    petición pudo llegar a la AEAT y el registro queda `sent` (motivo `unknown`, se reenvía declarado como
    incidencia); con `sent = false` no salió nada y se reintenta (`unreachable`). `503 gateway_busy` y cualquier
    otro estado: `unreachable`, a reintentar. El SaaS no valida nada fiscal: comprueba que el NIF del sobre es
    `nif`, presenta los bytes con el sello (dos huecos) o con el certificado del cliente al entorno pedido y
    devuelve la respuesta tal cual.
  - `/internal/verifactu/query` con el mismo cuerpo (la consulta `ConsultaFactuSistemaFacturacion`) → la misma
    forma.
  - `/internal/verifactu/probe` con `{"hub", "nif", "environment", "route", "certificate"?}` → `200 {"ready":
    bool, "detail"}`, sin presentar nada.
- **La foto** (`PUT /internal/hubs/{id}/state`, contrato acordado con el SaaS el 2026-10-15): `{"hub_id",
  "slug", "version", "status": "active"|"past_due"|"suspended", …, "verifactu": {"representation": {"status":
  "none"|"submitted"|"approved"|"returned"|"revoked", "updated_at": ISO|null, "reason"}}}`. `live_paid` ya no es
  del contrato (ronda 2026-10-22b, PLAN §30: VeriFactu en Gratis): mientras un SaaS anterior lo siga mandando, se
  acepta y no se lee, y su columna (`Config.live_paid`) se queda sin lectura ni escritura hasta que un paso de
  contracción la borre.
  La recibe `base/internal.py` (fase 1, sin registro de hubs): firma HMAC v1 o v2 (la v2, si viene, decide sola),
  ±300 s, `INTERNAL_SHARED_SECRET` y, en una rotación, `INTERNAL_SHARED_SECRET_PREVIOUS`; sin firma, `401
  internal.unsigned`. Nombra su hub por `slug` (`422 internal.slug_invalid`); un `hub_id` distinto del de la ruta,
  `422 internal.hub_mismatch`; fuera de contrato, `422 internal.payload_invalid`. Aplica el bloque `verifactu` y el
  `status` con `verifactu.config.sync` (solo el sistema) en ese hub y contesta `200 {"applied", "version"}`; sin
  ninguno de los dos, `200 {"applied": false}`. Una `version` menor o igual que la guardada se ignora. «Validado»
  = `representation.status == "approved"`, en todos los planes. `own_certificate` y `multiple_taxpayers` ya no viajan (`null` = sin cambio): el
  certificado propio se sube en el Hub (decisión de Ioan del 2026-10-15). La ruta de la foto le dice al Hub su id en
  ERPlora (`Config.hub_id`, sin variable de entorno `HUB_ID`): adonde se envía el otorgamiento (en la fase 2, del
  registro de control). Cada cambio de
  estado del otorgamiento deja su paso en el registro de auditoría («Sus pasos» de Configuración).
- **Otorgamiento de representación** (VERIFACTU-F05, F06; `representation.py`): `POST
  /internal/hubs/{id}/representation` con `{"taxpayer_tax_id", "taxpayer_name", "signer_tax_id", "signer_name",
  "signer_document_type": "dni"|"nie", "documents": {"signed_model", "id_copy", "signature_sample",
  "representation_proof"}}` (base64; los opcionales, `null`) → `201 {"status": "submitted", "version",
  "submitted_at"}`; `GET /internal/representation/model` → el modelo en blanco, `application/pdf`. Firmadas v1 y v2
  (la v2 sobre la ruta que ve el SaaS). Tiempos: 5 s para conectar y 60 s para leer (cuatro PDF de 5 MB). Rechazos:
  400/413/422 con su código (`fiscal.*`) y `fields` → 422 tal cual; 404 → 409 `verifactu.hub_unregistered`; sin
  conexión, 401, 5xx o fuera de contrato → 503 `verifactu.saas_unreachable`. La ruta del Hub (`POST
  /api/verifactu/representation`) admite un cuerpo de hasta 32 MB (`base.request_body.accept_body_up_to`; el resto
  de vistas, los 2,5 MB de Django). El Hub comprueba antes, con las reglas y los códigos del SaaS, y no guarda los
  documentos.
- **Certificado propio** (VERIFACTU-F02): `OwnCertificate`, una fila como mucho en la BD del hub, con titular,
  NIF, tipo, caducidad y el `.p12` con su contraseña cifrados juntos con Fernet (`certificates.py`) bajo
  `FISCAL_CERTIFICATE_KEY` (variable de entorno; en AWS, Secrets Manager en `hub` y `worker`). Sin clave, la
  subida se rechaza a la vista; con la clave cambiada, el guardado no se abre y los registros por la vía propia
  esperan con `own_certificate_unreadable` sin llamar a la pasarela.
- **Producción**: además de lo de VERIFACTU-F08, el despliegue tiene que ser `prod` (`ERPLORA_ENVIRONMENT`; en
  `pre` nunca) y el servidor tener `VERIFACTU_PRODUCTION_ENABLED` a verdadero. Cerrado de nuevo, ningún registro de
  producción sale (esperan con `production_closed`, sin llamar a la pasarela) y no se emite nada nuevo en producción
  (`queries.route_problem`: primero lo que le falta a la vía, después lo del servidor, pasarela y apertura). Los workers solo trabajan contra la AEAT de pruebas; abrir la remisión real y los certificados
  queda bajo la supervisión de Ioan (working-rules §15).
- **Hub de plataforma de ERPlora** (PLAN-SAAS §4; Facturación, INVOICE-F23): el hub `PLATFORM_HUB_SLUG` emite las
  facturas de ERPlora a sus clientes. Sus registros van al entorno de la AEAT del despliegue, diga lo que diga su
  configuración (`queries.effective_environment`: `prod` con la remisión real abierta → producción; si no, pruebas;
  ya en producción, sigue en producción con el servidor cerrado y sus registros esperan, para que sus facturas reales
  no pasen nunca a la cadena de pruebas; lo usan `record.create` y la factura de prueba); su interruptor está fijo (`go_live` y `back_to_testing` → 409 `verifactu.platform_fixed`) y
  `manage.py create_platform_hub` alinea su configuración con `verifactu.config.follow_deployment` (409
  `verifactu.platform_only` en cualquier otro negocio). El sello de ERPlora presenta sus propios registros sin
  otorgamiento (`queries.route_problem`: el hub de plataforma **y** el emisor de Facturación `PLATFORM_ISSUER_TAX_ID`):
  ERPlora no se representa a sí misma. Un negocio cualquiera que teclee ese NIF como emisor sigue necesitando su
  otorgamiento aprobado (saas#2524): sin él, en producción no se emite nada nuevo; la pasarela del SaaS lo rechaza
  igual (`fiscal_gateway`, 409).
- **Hub de demostración** (PLAN-SAAS §3.5; `base.Hub.is_demo`, que lee `base.operations.is_demo_hub`): nunca pasa a
  producción (`go_live` → 409 `verifactu.go_live_forbidden`) y todo lo que sella va a la AEAT de pruebas
  (`queries.effective_environment`), aunque en la fase 1 comparta tablas con un negocio que ya está en producción.

### La cola y el envío

- La cola **son los registros** (`pending`, `sent`, `accepted`, `accepted_with_errors`, `rejected`): sin tabla
  aparte. Espera por la ruta solo cuando no puede presentar (`queries.route_problem`: certificado propio que falta
  o caducó, otorgamiento sin aprobar en producción, o el servidor sin pasarela o cerrado). `SendControl` (una fila por `(NIF, entorno)`) guarda `next_send_at` (`TiempoEsperaEnvio` de la última
  respuesta) y es el cerrojo del envío: la pasada la toma con `select_for_update(skip_locked=True)`, así que dos
  pasadas nunca mandan la misma cadena y el sellado (que bloquea `Chain`) no espera a la red.
- Un envío junta los `pending` y `sent` de una cadena en orden de secuencia (hasta 1.000) cuando su primer
  pendiente ya toca (`next_attempt_at`) y la espera de la AEAT pasó. Sin respuesta: `attempts` +1 y espera de
  `5·2^(n−1)` minutos, con tope de 60; petición salida y sin respuesta (tiempo de lectura agotado): `sent`.
  Veredictos por línea de respuesta (número y tipo de operación): `Correcto` → `accepted`;
  `AceptadoConErrores` → `accepted_with_errors`; `Incorrecto` → `rejected`, salvo un 3000 cuyo
  `RegistroDuplicado` dice `Correcta`/`AceptadaConErrores` (ya estaba: `accepted`/`accepted_with_errors`). Un
  **SOAP Fault rechaza el envío, no sus registros** (la AEAT no evaluó ninguno): se quedan `pending` con
  `aeat_fault`, el intento gastado y su espera; nunca `rejected` (forzaría subsanaciones de registros que la AEAT
  no vio, con un `RechazoPrevio` equivocado). Un Fault permanente (4102/4104/4116: reenviarlo igual no sirve)
  se anota como evento crítico; cualquier otro Fault o una respuesta ilegible, a reintentar.
- Lo que contesta una pasada (`TransmitOut`): `sent` y `chains` cuentan solo lo que llegó (o pudo llegar) a la
  AEAT —respuesta o petición salida sin respuesta—; si la pasarela lo rechaza o no hay conexión, `sent` es 0 y
  `reason` (`refused`, `unreachable`, `aeat_fault`, `unknown`, `xml_invalid`) con su `message`: la pantalla lo
  enseña como aviso, nunca como éxito.
- **Consulta paginada** (§6.4.3): la AEAT contesta como mucho 10.000 registros; con `IndicadorPaginacion = S`
  se vuelve a preguntar con `ClavePaginacion` = el último registro que nombró, hasta el final (tope de 50
  páginas; una respuesta que repite la misma clave para la consulta con 409 `verifactu.aeat_unreachable`).
- Un registro enviado **nunca** se modifica en sus datos fiscales ni en su XML: cambian el estado, la respuesta
  y los intentos. Se corrige con uno nuevo (subsanación o anulación); una corrección de la factura es una
  rectificativa de Facturación.
- La tarea programada `process_queue` (`verifactu.contingency.process`, cada minuto, en UTC, `collapse`) la
  corre el worker (`base/scheduler.py`, desde `base/worker.py`, cada tick de 5 s) como el sistema: su reloj es
  una fila de `base.TaskSchedule` que el worker escribe al arrancar; cada pasada la toma con
  `select_for_update(skip_locked=True)` y mueve `next_run` en la misma transacción que el envío, así que dos
  workers a la vez (un despliegue) nunca la corren dos veces, y los minutos perdidos con el worker parado se
  juntan en una sola pasada. Si la pasada falla, se registra en el log, se deshace lo suyo y vuelve al minuto
  siguiente. En la fase 1 corre sobre un solo hub, `WORKER_SCOPE_SLUG` (por defecto el de plataforma,
  `PLATFORM_HUB_SLUG`); la fase 2 recorre los hubs a los que les toca (`hub_due`), cada uno con `use_hub`.

### Administrador de Django

Solo para el staff de la plataforma (`hubs.erplora.com/admin`, con el hub elegido en `/admin/hub/<slug>/`), **al
servicio del soporte**. Criterio de Ioan (2026-10-15): «un registro no enviado no es un registro registrado; no se
trata de borrar una venta, se trata de poder arreglar si hay un problema de envío, poder reenviar y cosas que se
necesitan para el soporte». Por eso:

- **Lo registrado en la AEAT no se toca.** Un registro aceptado o aceptado con errores, las cabezas de cadena, los
  eventos, la foto de la AEAT y el certificado propio se ven enteros y en solo lectura, sin alta, cambio ni borrado
  (un `POST` al formulario de un registro contesta 403). Ninguna acción cambia un registro registrado: lo dice y
  sigue. Del certificado se ve titular, tipo y caducidad, nunca el material sellado.
- **Lo no registrado (pendiente, enviado sin respuesta, rechazado) se arregla con acciones que son operaciones**,
  con el hub elegido y el staff como actor (cada una deja su evento con quién la hizo y un resumen en/es al
  terminar). Sin hub elegido, ninguna hace nada y lo dice.
  - **«Reenviar a la AEAT»** → `verifactu.record.transmit`: envía ya cada cadena una vez (el registro más reciente
    elegido arrastra los anteriores), respetando la espera de la AEAT. «Reenvío terminado: N aceptados, N
    rechazados, N aún en espera.».
  - **«Reprogramar: enviar en la próxima pasada»** → `verifactu.contingency.retry` (VERIFACTU-F22): el registro y
    los anteriores de su cadena salen en la pasada siguiente (la tarea de cada minuto), sin perder sus intentos.
    «Reprogramado: N registro(s) salen en la próxima pasada.».
  - **«Consultar a la AEAT (sale de la cola si ya lo tiene)»** → `verifactu.record.reconcile` (VERIFACTU-F35): si
    la AEAT tiene ese mismo registro (misma huella), sale de la cola como registrado; si no, sigue en la cola.
    «Consulta a la AEAT: N ya registrados (fuera de la cola), N no están en la AEAT (siguen en la cola).».
  - **«Subsanar el rechazo con un registro nuevo»** → `verifactu.record.correct` (VERIFACTU-F24), solo sobre un
    registro rechazado: el rechazado se queda tal cual y entra uno nuevo en la cola. «Subsanado: N registro(s)
    nuevo(s) en la cola.».
  - **Retirar de la cola**, como en el antiguo («Cancelar» solo si ya aceptado), es solo lo que la AEAT ya tiene,
    y se hace consultándola (la acción de arriba). Nada sale de la cola sin que la AEAT lo tenga (VERIFACTU-F23); un
    rechazo definitivo se resuelve con la subsanación, que deja el rechazado como estaba.
- **Control de envío por `(NIF, entorno)`**: en solo lectura; su acción **«Reprogramar su cola: enviar en la
  próxima pasada»** llama a `verifactu.contingency.retry` sobre el registro más reciente que espera en esa cadena.
  `next_send_at` es el `TiempoEsperaEnvio` de la AEAT y **nunca se acorta** (las preguntas frecuentes de la AEAT, en «Referencia adoptada»):
  reprogramar hace que salga en cuanto la AEAT lo permita. El `wait_reason` de un registro tampoco se borra al
  reprogramar: es lo que lo declara fuera de plazo (`Incidencia` S); lo reescribe la pasada siguiente. La excepción
  es un rechazo de la pasarela (`refused`, con su código y su mensaje en el detalle), que no sale nunca por tiempo:
  reprogramarlo lo devuelve a la cola sin motivo, y sus intentos lo siguen declarando fuera de plazo.
- **Configuración**: se ve entera y solo se elige la **vía de envío**, por `verifactu.config.update` (el
  formulario la ejecuta al validarse, así que su rechazo —sin certificado propio válido, sin el otorgamiento
  aprobado en producción— es el error del formulario y no se guarda nada). Nunca se teclean el entorno (va por
  «Pasar a producción» / «Volver a pruebas»), lo que manda la foto del SaaS (`representation_*`,
  `hub_status`, `hub_id`, `synced_version`) ni el certificado. La columna retirada `live_paid` (ronda 2026-10-22b) no
  se enseña.
- **Registros**: las columnas de la pantalla de registros del módulo antiguo (`erp-verifactu-records`: secuencia,
  factura, fecha, tipo, emisor, total, estado) más el entorno y el CSV de la AEAT; filtros por estado, motivo de
  espera (solo los que tiene algún registro, en el idioma del lector), tipo de registro, tipo de factura y entorno;
  jerarquía por fecha de expedición; búsqueda por número, NIF, nombre del emisor, huella y CSV. La ficha agrupa
  todos los campos en Factura (con enlace a la factura en su admin), Cadena de huellas, Respuesta de la AEAT
  (estado, **por qué aún no está en la AEAT** en frase, intentos, `wait_reason`, detalle, respuesta y código de la
  AEAT), XML y Metadatos.

### Contradicciones señaladas

Las cerradas quedan tachadas con su motivo; las abiertas dicen dónde siguen.

1. **Registro de anulación al anular una venta**: el encargo de esta app pedía un registro de anulación al emitir
   la R5 de una venta anulada; Facturación (decisión 3) y la norma la declaran como un **alta R5**. Aquí se hace
   así; un registro de anulación además la restaría dos veces ante la AEAT. La anulación queda para lo emitido por
   error (VERIFACTU-F30).
2. ~~**Certificados y otorgamiento de representación**~~ — **cerrada (PLAN §28 y su nota en §16.5, ronda
   2026-10-15c)**: PLAN §16.5 ponía el certificado del cliente en la BD del SaaS cifrado con KMS; la decisión de
   Ioan del 2026-10-15 (bloque fiscal) lo pone en la **BD del hub**, cifrado con Fernet bajo
   `FISCAL_CERTIFICATE_KEY`, y así se hace aquí. El otorgamiento se sube en el Hub y lo revisa el SaaS
   (VERIFACTU-F05). working-rules §15 deja la transmisión real y los certificados bajo la supervisión de Ioan: los tests
   solo usan certificados generados por ellos y la AEAT de pruebas; el paso a producción exige
   `VERIFACTU_PRODUCTION_ENABLED` en el servidor.
3. ~~**Quién revisa el otorgamiento de representación**~~ (PLAN-HUB §8) — **cerrada (ronda §25 y PLAN-HUB §4,
   2026-10-15c)**: lo revisa el staff de ERPlora en el SaaS (`fiscal/`); el Hub sube los documentos y no los
   guarda, y el estado vuelve en la foto.
4. ~~**Nombre del módulo**~~ — **cerrada**: PLAN-SAAS §4 llama «módulo `fiscal` de `hub-next`» al que recibe el
   motor VeriFactu del SaaS; la app es `verifactu` (en el SaaS, `fiscal/` es la revisión del otorgamiento y
   `fiscal_gateway/` la pasarela).
5. **Declaración responsable**: la v1 firmada no nombra una pasarela en Python dentro del SaaS (la v2, sin
   firmar, nombra el `verifactu-gateway` en Rust); el cambio de composición necesita una versión nueva firmada.
   **Sigue abierta**: es un trámite legal, fuera del código (PLAN-HUB §8, «Bloque fiscal: lo que queda fuera»).
6. ~~**Admin del Hub**~~ — **cerrada por Ioan (2026-10-15)**: CLAUDE.md dice «CRUD completo… fiscales
   incluidas» y el brief de la tarea 6, «CRUD completo con aviso»; Ioan fijó el criterio: «un registro no enviado
   no es un registro registrado; no se trata de borrar una venta, se trata de poder arreglar si hay un problema de
   envío, poder reenviar y cosas que se necesitan para el soporte». Lo registrado en la AEAT, en solo lectura; lo
   no registrado, con acciones de soporte que son operaciones; la vía, por su operación (ver «Administrador de
   Django»). Falta reflejarlo en PLAN §17 (CLAUDE.md sigue diciendo «CRUD completo»).
7. ~~**«Da servicio a varios obligados» sin origen**~~ — **cerrada (T2b, 2026-10-15)**: `IndicadorMultiplesOT` es
   «S» siempre, porque ERPlora es un sistema multi-obligado por definición; no depende de la foto. Fuera
   `multiple_taxpayers` (migración 0004, reversible) y `producer_facts_missing`.
8. ~~**La opción en vivo y la vía propia**~~ — **cerrada (aceptada en el bloque fiscal, 2026-10-15)**: el encargo de la tarea 2 pedía `live_paid` en las dos vías; el modelo de
   Ioan («con certificado propio, como en el Hub antiguo») y el plan del bloque solo en la de ERPlora. → **Retirada
   (ronda 2026-10-22b, PLAN §30: VeriFactu en Gratis; FIX-HUB-VERIFACTU-RETIRE-LIVE-PAID)**: ninguna vía la pide y
   el 409 `verifactu.live_option_unpaid` desaparece de `go_live`, del cambio de vía y de `verifactu.record.create`.
9. ~~**Cobrar sin ruta de envío**~~ — **cerrada (T2b, 2026-10-15)**: en producción sin ruta, `verifactu.record.create`
   rechaza con el código de la ruta y no se sella, numera ni cobra (VERIFACTU-F08; «Contrato con Facturación»). La
   cola nunca esperó por la opción en vivo, retirada después (punto 8). Venta reconoce los códigos de la ruta por nombre (como ya nombra las
   operaciones de Facturación), aunque VeriFactu no está en sus `requires`.
10. ~~**Hubs demo en la fase 1**~~ — **cerrada (2026-10-21)**: la demo es una fila de `base.Hub` (ronda 2026-10-17)
   y `base.operations.is_demo_hub` la lee; como en la fase 1 comparte tablas, su entorno no sale de la configuración
   sino de que es demo: siempre pruebas (`queries.effective_environment`). En la fase 2 lee `control.Hub.is_demo` y
   no cambia nada más.

### Decisiones (dudas abiertas del producto actual)

1. **Hay botón de enviar ya** en la ficha (duda 1): Odoo, Holded y Sage lo ofrecen.
2. **Ante un rechazo, la ficha dice qué hacer** y ofrece «Subsanar» (duda 2): datos de la factura →
   rectificativa en Facturación; lo demás → subsanación.
3. **El registro de anulación tiene pantalla** (duda 3): «Anular registro» en la ficha, con motivo y
   confirmación, solo el administrador.
4. **Se avisa de la caducidad del certificado propio** a 30 días (duda 4).
5. **Pruebas y producción se separan** en la lista con la columna y el filtro «Entorno» (duda 5).
6. **«Activar VeriFactu» desaparece** (duda 7): encender la app es activarla; un módulo activo registra
   siempre.
7. **No hay cese en el Hub** (duda 8): es la baja censal.
8. **La prueba de conexión nunca presenta un registro** (duda 9), tampoco con certificado propio.
9. **Volver a pruebas se cierra con el primer registro de producción**, sea una venta o una rectificativa
   (antes solo la rectificativa: ERPlora/hub#2498).
10. **La anulación de una venta es una rectificativa R5**, registrada como alta (Facturación, decisión 3): un
    registro de anulación además la contaría dos veces ante la AEAT.
11. **Sin reenganche automático** ante un rechazo de cadena: se recupera la cadena (F28) y se subsana (F24); mover
    la cadena sin una persona es peor que el rechazo.
12. **Una factura completa sin NIF de cliente se niega**, no se degrada a F2 (Facturación ya lo exige; degradar
    declaraba un tipo distinto del impreso).
13. **Un SOAP Fault no rechaza registros** (revisión fiscal, 2026-10-15): es un rechazo del envío; los registros
    esperan con `aeat_fault` y el intento gastado. Ninguna norma pide marcarlos rechazados: la Orden
    HAC/1177/2024 pide remitir los registros, y uno que la AEAT no evaluó no existe para ella. Lo único en contra
    es práctico: un Fault permanente se repite en cada intento (con la espera de 5 a 60 minutos) hasta que una
    persona arregla su causa; por eso queda como evento crítico.
14. **Un rechazo de VeriFactu deshace la emisión** (contrato con Facturación): reintentarlo fallaría igual;
    solo un error pasajero de la base de datos deja el documento «pendiente» para la reacción.
15. **VeriFactu solo vale en España** (FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN, 2026-10-27): el RD
    1007/2023 y la Orden HAC/1177/2024 obligan a quien tributa en España (Canarias, Ceuta y Melilla son regiones de
    ES). Un negocio con otro país en su cuenta (`base.Hub.country`, que lee `base.business.get`) se comporta como con
    la app apagada (`queries.outside_spain`, `refuse_outside_spain` → `AppInactive`): sus facturas salen
    «unavailable» (nunca un 409 que las deshaga), la reacción no sella, la cola no envía (`blockers` →
    `outside_spain`), la factura no pinta recibo (`by_invoice` vacío) y el veto de apagar no lo atrapa
    (`disable_refusal` → `None`). Sin país (una demo) o en el hub propio de ERPlora (`PLATFORM_ISSUER_COUNTRY`), es
    España. Lo sellado antes en un negocio de fuera no se borra (los registros fiscales nunca se borran): se queda
    sin enviar, con su motivo. Que **Apps** no la ofrezca encendible fuera de España necesita un gancho de encendido
    de la plataforma (`can_enable(self, ctx) -> str | None` en `LiveAppConfig`, como `can_disable`, que respeten
    `base.app.enable` y `base.app.list`); hasta entonces se enciende y no hace nada.

### Cambios frente al producto actual

1. La cola son los propios registros (no hay tabla de contingencia ni prioridad); «Contingencia» enseña el
   número de factura y los estados traducidos.
2. Un «duplicado» (3000) de un registro que la AEAT ya tenía aceptado cuenta como aceptado (antes quedaba
   «Rechazado» y descuadraba la cadena).
3. Se respeta `TiempoEsperaEnvio` y se agrupan hasta 1.000 registros por envío (antes uno por envío, sin
   respetarlo: hub#1942).
4. Se genera la subsanación (antes nunca).
5. El XML se valida con el esquema real de la AEAT (antes, un validador propio «ligero»).
6. La lista y los eventos se ponen al día solos; el buscador busca por NIF.
7. El otorgamiento de representación se firma y se sube en el Hub (como el módulo antiguo), lo revisa el staff
   en el SaaS y su estado vuelve en la foto; el certificado propio se sube en el Hub y se guarda cifrado en la BD
   del hub (antes, en el core del Hub).
8. La subsanación lleva el `RechazoPrevio` de la Descripción del servicio web v1.0.3 (`X` / `S` / `N`; antes,
   siempre `S`), el desglose no se recorta nunca (antes, a 12 líneas en silencio), la consulta a la AEAT sigue
   todas sus páginas (antes, solo la primera) y una pasada sin conexión no se cuenta como enviada.
9. Los importes agrupan los millares desde cuatro cifras (hub#1090): «1.234,56 €» en español en la lista y la
   ficha de un registro y en la lista del admin (antes «1234,56 €»). El XML y la huella de la AEAT no cambian:
   llevan el importe sin millares, como pide su esquema.

### Paridad con el módulo actual

| Módulo actual | Aquí |
|---|---|
| `verifactu.config.get` · `config.save` | `verifactu.config.get` · `verifactu.config.update` (+ `go_live`, `back_to_testing`, `sync`, que eran del núcleo) |
| `records.list` · `records.get` · `records.by_invoice` | `verifactu.record.list` · `record.get` · `record.by_invoice` |
| `records.create` · `records.ingest_invoice` | `verifactu.record.create` (un solo camino, desde la factura) |
| `records.transmit` | `verifactu.record.transmit` |
| — | `verifactu.record.correct` (subsanación) · `verifactu.record.cancel` (anulación con pantalla) |
| `contingency.list` · `contingency.process` · `contingency.retry` | `verifactu.contingency.list` · `contingency.process` · `contingency.retry` |
| `contingency.cancel` | desaparece (F23) |
| `events.list` | `verifactu.event.list` |
| `stats.compliance_summary` · `records_by_status` · `contingency_summary` · `events_recent` | los mismos, en `verifactu.stats.*` |
| `aeat.records.list` · `aeat.query_recent` | `verifactu.aeat_record.list` · `verifactu.aeat.query` |
| `chain.status` · `chain.validate` | `verifactu.chain.status` · `verifactu.chain.validate` |
| `recovery.from_aeat` · `recovery.manual` | `verifactu.chain.recover_from_aeat` · `verifactu.chain.recover_manual` |
| `diagnostics.run` · `diagnostics.last` | `verifactu.diagnostic.run` · `verifactu.diagnostic.last` |
| La factura de prueba (pantalla → `invoice.create`) | `verifactu.test_invoice.create` |
| `_insert_record`, `_insert_event`, `_enqueue_contingency`, `_apply_transmission`, `_rechain_record`, `_insert_recovery`, `_insert_aeat_record`, `_clear_aeat_records`, `_resolve_contingency` | internos del SQL: aquí son código de `services.py` |

| Test del módulo actual | Aquí |
|---|---|
| `arithmetic_integrity` | `test_services.py` (registro imposible: no se sella ni gasta número) |
| `desglose.hub` | `test_envelope.py` (una línea por clave, exenta, recargo) e `test_integration_invoice.py` |
| `recipient_snapshot`, `rectification_block`, `record_create_payload`, `record_detail_fields` | `test_services.py`, `test_envelope.py`, `test_schemas.py`, `test_queries.py` |
| `transmission_fingerprint` | `test_services.py` (ID de transmisión y digest del sobre) |
| `events_list.*`, `events_list_message_words`, `list_filters` | `test_queries.py` |
| `setup_locales`, `navigation_tabs_are_translated`, `widget_texts_translate` | `test_i18n.py`, `test_apps.py` y `frontend/locale/locale.test.ts` |
| `migrations_ddl_is_frozen` | `test_migrations.py` |
| `core_floor_is_declared`, `installation_bound`, `demo_activation` | `test_apps.py` (requiere Facturación); la activación es de la plataforma |
| `aeat_compliance.rs`, `chain.rs`, `xsd.rs`, `aceptado_con_errores.rs`, `consult.rs`, fixtures | `test_chain.py`, `test_envelope.py`, `test_xsd.py`, `test_aeat.py` |

### Paridad de pantallas con el módulo actual

| Pantalla actual | Aquí | Diferencia y motivo |
|---|---|---|
| Registros (`erp-verifactu-records`) | `RecordsPage.vue` | + columna y filtro «Entorno» (duda 5); + «Cotejar en la AEAT» por fila (verifactu#104); el buscador busca también por NIF |
| Detalle de un registro (dentro de la lista) | `RecordDetailPage.vue`, página propia con «← Volver» | + QR en imagen, XML, «Enviar ahora», «Subsanar» y «Anular registro» (dudas 1–3) |
| Contingencia (`erp-verifactu-contingency`) | `ContingencyPage.vue` | Sin «Prioridad» (no se usaba) ni «Cancelar» (F23); «Factura» en vez del id interno; estados traducidos |
| Eventos (`erp-verifactu-events`) | `EventsPage.vue` | Se pone al día sola |
| Recuperación (`erp-verifactu-recovery`) | `RecoveryPage.vue` | El ancla manual exige número y fecha (son parte del encadenado) |
| Configuración (`erp-verifactu-config`, `erp-verifactu-grant`) | `ConfigPage.vue` (+ `RepresentationGrant.vue`) | La subida del `.p12` sigue aquí («Mi certificado»: elegir el fichero, contraseña, «Subir el certificado», «Quitar») y el Anexo I también («Lo remite ERPlora»: modelo, firmante y PDF, «Enviar a revisión»); un botón y el nombre del fichero en vez de la zona de arrastre (falta el componente en `@erplora/ui`); la «Conexión segura» desaparece (F07) |
| Ajustes (`erp-verifactu-settings`) | `SettingsPage.vue` | Sin «Activar VeriFactu» (duda 7) ni «Tipo de prueba» (la prueba ya no presenta ninguna muestra) |
| Tarjetas del panel de Inicio (`verifactu.pending`, `verifactu.contingency`, `verifactu.by_status` y `erp-verifactu-events-widget`) | `widgets` de `apps.py` (tres declarativos) + `frontend/components/RecentEventsPanel.vue` | Agrupados bajo «VeriFactu» en «Personalizar panel» (el viejo, «Cumplimiento»); sin el rótulo bajo la cifra de la cola («En cola de contingencia»): un panel declarativo de `base` aún no lleva texto traducido en `options.label` (FIX en el informe); iconos registrados (`stats-chart-outline` espera en `UI-REQUESTS.md`) |
| Paso «Configura VeriFactu» del Inicio (`module.json#setup`) | `setup` de `apps.py` sobre `verifactu.config.get` | Hecho con la vía lista para producción (`route_ready_for_production`), no con «activar VeriFactu» y el certificado: ya no hay interruptor y la vía de ERPlora no pide certificado (PLAN §30) |

### Qué queda fuera

Del bloque fiscal del 2026-10-15 (el resto, en PLAN-HUB §8, «Bloque fiscal: lo que queda fuera»):

- **Rotar `FISCAL_CERTIFICATE_KEY`**: un solo `Fernet`, sin `MultiFernet`; con la clave cambiada, el certificado
  guardado no se abre y los registros por la vía propia esperan con `own_certificate_unreadable` hasta que se vuelva
  a subir.
- **Avisar por correo de la caducidad del certificado propio**: hoy el aviso es solo en pantalla, a 30 días.
- **Subsanar y anular en producción sin ruta**: no se rechazan (no son cobros) y esperan en la cola.
- **Arrastrar y soltar los ficheros** (certificado y otorgamiento): falta el componente de subida en
  `@erplora/ui`; hoy, un botón y el nombre del fichero.
- **El bucle por hubs del worker** (fase 2): en la fase 1, las tareas programadas corren sobre un solo hub,
  `WORKER_SCOPE_SLUG`.
- **`create_platform_hub` solo cuando haya una BD por hub** (fase 2): en la fase 1 hay una sola BD y su emisor
  sería el de todos los hosts; el comando se niega si ya hay otro emisor.
- **Botón «Consultar a la AEAT» en la SPA** (VERIFACTU-F35): la operación, su ruta y su tipo en `operations.d.ts`
  existen; hoy se usa desde el admin del Hub.
- **OSS**: la factura de plataforma no lleva el aviso «VAT included — customer VAT number could not be verified»
  del PDF antiguo cuando el NIF-IVA del cliente no se pudo verificar.

### Lo que NO hace, a propósito

- No emite, anula ni modifica facturas: eso es Facturación.
- No calcula impuestos: los importes llegan decididos.
- No guarda el sello de ERPlora (Secrets Manager, solo en el SaaS) ni enseña nunca el material del certificado
  propio: el `.p12` y su contraseña se guardan cifrados y solo salen hacia la pasarela.
- No borra ni edita un registro sellado.
- No presenta nada a la AEAT por su cuenta: lo hace la pasarela del SaaS.
- No lleva el registro de eventos de la modalidad NO VERI\*FACTU.
- No tramita el cese de actividad.
