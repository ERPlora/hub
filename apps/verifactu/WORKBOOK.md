# Workbook — VeriFactu (app)
Prefijo: VERIFACTU
Alcance MVP: núcleo
Estado de la app: completa (2026-10-27)

> Manual de usuario y especificación de la app `verifactu`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `Estado: hecho` cuando sus tests están en verde
> (servidor y páginas). Los números de flujo (`VERIFACTU-Fnn`) no cambian ni se reutilizan, porque otras
> apps y el QA los citan.

## Para qué sirve y para quién

VeriFactu convierte cada factura y cada tique que emite Facturación en su registro para la Agencia Tributaria (AEAT):
encadenado al anterior por su huella, con el QR que el cliente puede cotejar, y enviado a la AEAT en orden. Lo que no
puede salir en el momento espera en la cola y sale solo después. Solo vale para negocios de España, y empieza en el
entorno de pruebas de la AEAT hasta que pasas a producción.

### En detalle

VeriFactu es el final de la cadena fiscal: cada factura o tique que emite Facturación se convierte aquí en
un **registro de facturación** encadenado (cada registro lleva la huella del anterior), con su **QR** de
cotejo, que se envía a la Agencia Tributaria (AEAT). Si no puede salir en ese momento, se queda en la cola
y sale solo después, en orden. Sirve igual a la peluquería y al restaurante: todo es común.

Solo vale para negocios de **España** (Canarias, Ceuta y Melilla incluidas): VeriFactu obliga a quien tributa
aquí. Un negocio dado de alta en erplora.com en otro país no registra ni envía nada a la AEAT aunque tenga la app
encendida: sus facturas y tiques salen sin registro ni QR de VeriFactu, como con la app apagada.

Quién la usa:

- El **empleado** no abre sus pantallas (por su dirección, «Sin acceso» (BASE-F118)); sus ventas llegan igual a la AEAT.
- El **responsable**, además, envía un registro concreto, procesa y reintenta la cola, consulta lo que
  tiene la AEAT y prueba la conexión.
- El **propietario** y el **administrador**, además, suben o quitan el certificado del negocio, pasan a
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
  anular, y las dos vías (certificado propio o el proveedor en tu nombre).

## Antes de empezar

- Al encender VeriFactu se enciende con ella **Facturación** (la requiere): sin facturas no hay nada que
  registrar. Encender VeriFactu en el Hub **es** activarla: desde ese momento registra cada factura que se
  emite. No hay otro interruptor.
- **El emisor** es el de Facturación (Facturación → Emisor): VeriFactu toma de cada factura su NIF y su razón
  social, no los pide otra vez.
- **El entorno** empieza en **pruebas** (la AEAT de pruebas): nada de lo que se emite cuenta ante Hacienda
  hasta pasar a producción (VERIFACTU-F08).
- **La vía de envío** no se elige: la decide tu certificado (VERIFACTU-F04). Con tu propio certificado cargado y
  vigente, remites tú con él; sin él, en pruebas remite ERPlora en tu nombre con su sello. Para pasar a producción
  hace falta tu certificado o, donde ERPlora presenta por cuenta de los negocios, tu autorización firmada (el Anexo
  I) aprobada por ERPlora; con las dos, gana el certificado, y la vía de ese momento queda fijada. La autorización
  (el otorgamiento de representación) se firma y se sube aquí, en «Lo remite ERPlora», y la revisa ERPlora; el
  certificado se sube aquí, en «Mi certificado».
- **En el Inicio**, mientras no tengas cómo llevar tus registros a la AEAT de producción (ni tu certificado vigente ni
  la autorización aprobada), «Termina de configurar tu negocio» lo recuerda con «Configura VeriFactu»; su
  «Configurar» lleva a VeriFactu → Configuración, y el paso queda «Hecho» en cuanto subes tu certificado o ERPlora
  aprueba la autorización. En pruebas lleva la pastilla «Importante» (no frena la venta: en pruebas se vende igual)
  y solo lo ve quien configura VeriFactu. En producción (VERIFACTU-F08), si la vía fijada se pierde (con la de ERPlora,
  se revoca la autorización; con la del certificado, caduca o se quita), lleva «Necesario para facturar» y sale
  el aviso «Todavía no puedes facturar» en la campana, con «Configurar VeriFactu», porque cada venta nueva se rechaza; lo ve
  todo el equipo, y a quien no configura VeriFactu le dice «Esto lo tiene que configurar un administrador.». Solo
  se lo pide a un negocio de España; uno sin país (una demo) cuenta como España, y uno de otro país no lo ve nunca,
  ni en pruebas ni en producción (hub#682).
- **Es obligatoria en España.** Mientras está desactivada en un negocio de España (o sin país, como una demo),
  «Termina de configurar tu negocio» pide a quien lo administra «Activa VeriFactu» («Importante»), con «Configurar»
  que lleva a **Apps**; en cuanto la activa, ese paso se va y llega «Configura VeriFactu». Nunca se activa sola:
  ata al negocio con la AEAT hasta el fin del año natural, así que la activa el dueño (BASE-F01, hub#997).
- **Los datos del productor del software** (ERPlora) van fijos en cada registro (los declara su declaración
  responsable), también «Da servicio a varios obligados», siempre «S».
- **Las horas y los días son los del negocio**, en su zona horaria (la de «Ajustes»), no los de Madrid: la hora a la
  que se genera cada registro (con su huso), la hora hasta la que la AEAT pidió esperar, el mes en curso que se
  pregunta a la AEAT y el día en que caduca tu certificado. Un negocio en Canarias ve sus registros generados a su
  hora y, la Nochevieja a las 23:30, pregunta a la AEAT por diciembre, aunque en Madrid ya sea enero.

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
Cada factura y cada tique que emites tiene aquí su registro de VeriFactu, lo último arriba, con su estado ante la
AEAT (Pendiente, Enviado, Aceptado, Aceptado con errores o Rechazado) y su entorno, pruebas o producción. Búscalos por
factura, emisor o NIF y fíltralos por estado, tipo, fecha o total. Toca uno para abrir su ficha: la factura, la cadena
de huellas, el QR, la respuesta de la AEAT y, si aún no ha llegado, por qué espera; desde ahí, según su estado y tu
permiso, lo envías ya, lo subsanas o lo anulas.

#### Detalle
Menú **VeriFactu → Registros**. Título «Registros VeriFactu». Tabla de 50 en 50 (tabla o tarjetas; en el
móvil, tarjetas con el número de factura como título) con «Seq», «Factura», «Fecha», «Tipo» (Alta /
Anulación), «F.» (F1…R5), «Emisor», «Total», «Entorno» (Pruebas / Producción) y «Estado» (Pendiente,
Enviado, Aceptado, Aceptado con errores, Rechazado, en una pastilla de color; junto a un alta rechazada o aceptada
con errores, «Pendiente de subsanar» o «Subsanado», que abre el registro que la subsana: VERIFACTU-F24). Buscador
«Buscar factura, emisor o NIF…» (número de secuencia, número de factura, nombre o NIF del emisor). Filtros de estado,
tipo, tipo de factura, subsanación («Pendientes de subsanar» o «Subsanados»), entorno, fecha y total (en euros),
tras el embudo de la tabla con su contador; un total que no
es un importe, o una fecha «hasta» anterior a la «desde», se dice bajo su campo y no filtra. Lo último sellado
sale arriba. Por fila: «Ver» (también
al pulsar la fila) y «Cotejar en la AEAT» (abre la página de cotejo del QR). La lista se pone al día sola
cuando nace, sale o cambia un registro en cualquier dispositivo.
Vacía: «Todavía no hay registros. Cada factura que emitas se sella y aparece aquí.»; con búsqueda o filtro,
«Sin resultados». Cargando: «Cargando…». Error: el mensaje con «Reintentar».

#### Ficha de registro
Se abre desde una fila de **Registros** (`/verifactu/records/<id>`). Arriba, «Registro {número}» con su estado,
su entorno y «← Volver». Si no está en la AEAT (Pendiente o Enviado), el aviso «Aún no está en la AEAT» con
el porqué y el cuándo (VERIFACTU-F17). Si fue rechazado, el aviso «La AEAT lo ha rechazado» con qué hacer
(VERIFACTU-F24); ya subsanado (también un «Aceptado con errores»), en lugar de qué hacer, «Ya está subsanado con un
registro nuevo» con el enlace «Ver el registro que lo subsana». Bloques:
- **Factura**: «Factura», «Fecha de expedición», «Fecha de operación» (si es otra), «Tipo de factura»,
  «Emisor», «NIF del emisor», «Cliente» y «NIF del cliente» (si los hay), «Rectifica a» / «Sustituye a»,
  «Base», «Cuota» y «Total».
- **Cadena de huellas**: «Seq», «Generado el», «Huella», «Huella anterior» (o «Primer registro de la cadena»).
- **QR**: la imagen del QR y «Cotejar en la AEAT».
- **Respuesta de la AEAT**: «Enviado el», «CSV», «Código de respuesta», «Mensaje de respuesta», «Intentos»,
  «Próximo intento» y la «Huella de la entrega» («ID de transmisión», «Digest del sobre (SHA-256)»; «Aún sin
  estampar» mientras no ha salido).
- **XML**: el sobre que se envía (o «El XML se construye al enviar el registro a la AEAT.»).
Botones según el estado y el permiso: «Enviar ahora» (VERIFACTU-F25) y «Preguntar a la AEAT» (VERIFACTU-F35) mientras
está en la cola, «Subsanar» (VERIFACTU-F24) y «Anular registro» (VERIFACTU-F30). Un rechazo sale justo encima de los botones.
Error al abrir: «Registro no encontrado» o el mensaje del fallo, con «← Volver».

### Contingencia
La cola de los registros que aún no están en la AEAT, en el orden en que van a salir, con sus intentos, el próximo
intento y el último error. El sistema los envía solo, en orden, y lo que vuelve a fallar espera un poco más antes del
siguiente intento. «Procesar cola» hace la pasada en ese momento y «Reintentar» pone un registro a salir en la
siguiente. Vacía, todo está en la AEAT.

#### Detalle
Menú **VeriFactu → Contingencia**. Título «Cola de contingencia» y botón «Procesar cola» («Procesando…»
mientras trabaja). Tabla de los registros que aún no están en la AEAT: «Factura», «Entorno», «Intentos»,
«Estado», «Próximo intento» y «Último error», en el orden en que salen (cada columna se ordena); buscador «Buscar
factura o error…». Por fila: «Reintentar» (lo
pone a salir en la siguiente pasada) y «Ver». Debajo de la tabla, el resultado de la última pasada a mano.
Vacía: «Cola vacía: todo está en la AEAT.». Cargando: «Cargando…». Error: el mensaje encima de la tabla.

### Eventos
Lo que ha pasado con tus registros y con la conexión a la AEAT, lo más reciente primero: cada registro creado, cada
envío aceptado, aplazado o fallido, cada pasada de la cola, las comprobaciones de la cadena, las consultas a la AEAT y
los cambios de configuración. Búscalos por tipo o por mensaje y fíltralos por tipo, severidad o fecha.

#### Detalle
Menú **VeriFactu → Eventos**. Título «Eventos de auditoría». Tabla, lo más reciente primero: «Cuándo»,
«Severidad» (Depuración, Información, Aviso, Error, Crítico), «Tipo» (Registro creado, Envío aplazado, Envío
aceptado, Aceptado con errores, Envío fallido, Cola procesada, Registro reprogramado, Cadena verificada, Cadena
rota, Consulta a la AEAT, Cadena recuperada, Prueba de conexión, Configuración cambiada) y «Mensaje», compuesto en el idioma de
quien mira. Buscador «Buscar tipo o mensaje…» que encuentra por las palabras que se ven, en español o en
inglés; filtros de tipo, severidad y fecha, tras el embudo de la tabla con su contador (una fecha «hasta»
anterior a la «desde» se dice bajo su campo y no filtra). Se pone al día sola.
Vacía: «Sin eventos.». Cargando: «Cargando…». Error: el mensaje con «Reintentar».

### Recuperación
Aquí compruebas que la cadena de huellas de tus registros está íntegra y consultas los registros que la AEAT tiene de
tu negocio este mes. Si hace falta, recuperas la cadena: desde la AEAT, después de restaurar una copia de la base de
datos, o desde la última huella de la aplicación que usabas antes, al migrar. Las dos recuperaciones piden
confirmación.

#### Detalle
Menú **VeriFactu → Recuperación**. Título «Recuperación de cadena». Campo «NIF del emisor» (rellenado con el
del emisor de Facturación) y el entorno actual. Bloque «Integridad de la cadena» con el último veredicto
(«Cadena de huellas íntegra ✓», «Cadena de huellas ROTA ✗» con la secuencia, o «Sin validar todavía») y la
nota «Recalcula las huellas SHA-256 y verifica el encadenado. No vuelve a auditar los importes: la base, la cuota y
el total se toman como los declaró la factura.». Botones
«Validar cadena», «Consultar AEAT» y «Recuperar cadena desde la AEAT». Tabla «Últimos registros en la AEAT»:
«Factura», «Fecha», «Huella», «Estado», «CSV» y «Consultado el»; vacía: «Sin datos de la AEAT. Pulsa
«Consultar AEAT».». Bloque «Continuar cadena manualmente (migración)» con «Última huella (64 hex)», «Nº de
factura» y «Fecha» y «Continuar desde esta huella». Las dos recuperaciones piden confirmación («Confirmar
recuperación» / «Cancelar»). Al terminar: «Operación completada.».

### Configuración
Aquí preparas cómo llegan tus registros a la AEAT. En «Mi certificado» subes el certificado electrónico de tu negocio
(un fichero .p12 o .pfx) con su contraseña, ves su titular y cuándo caduca, y lo renuevas o lo quitas. Si ERPlora
presenta por cuenta de los negocios, la pestaña «Lo remite ERPlora» te deja descargar el modelo de autorización y,
una vez firmado, enviarlo a revisión, y dice en qué estado está. Solo quien configura VeriFactu sube o envía algo.

#### Detalle
Menú **VeriFactu → Configuración**. Título «Configuración de VeriFactu». Con la vía de ERPlora disponible, dos
pestañas, las dos vías:
- **«Lo remite ERPlora»** (abre por defecto): «Otorgamiento de
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
  30 días o menos y «El certificado ha caducado. Sube uno vigente para poder enviar a la AEAT.») y, en pruebas,
  «AEAT de pruebas»: «Sin probar todavía», «Aceptado» o «Rechazado», con el aviso de cómo se prueba o de por qué lo
  ha rechazado (VERIFACTU-F02). Quien configura
  VeriFactu ve «Elegir el fichero .p12 / .pfx», «Contraseña del certificado», «Subir el certificado» y, con uno
  cargado, «Quitar» (pregunta antes, en una tarjeta que dice qué pasará: en pruebas, «Puedes seguir probando sin él:
  tus registros de pruebas siguen saliendo.»; en producción con tu certificado, «Los registros esperarán hasta
  que subas otro certificado.»; en producción con ERPlora, «Tus registros siguen saliendo con el sello de
  ERPlora.»). Nota: «El certificado y su contraseña se guardan cifrados en este Hub y solo viajan a la pasarela de
  ERPlora al enviar a la AEAT; no se vuelven a mostrar.».
Cuando la vía de ERPlora no está disponible, no hay pestañas ni se muestra nada del otorgamiento. El certificado
es la única tarjeta: su estado dice «Sin certificado», «Válido», «Caduca pronto» o «Caducado», además de sus datos
y los avisos de caducidad. En pruebas y sin certificado, «Puedes probar VeriFactu sin certificado. Solo lo necesitas
para pasar a producción.»; en producción, «Sube un certificado válido para enviar tus registros a la AEAT.». «Subir
el certificado» es la única acción principal; elegir el fichero y quitarlo son secundarias. Al quitarlo, el aviso es el
mismo que con las pestañas. La nota de cifrado no menciona la vía de ERPlora.
En un negocio de fuera de España, arriba sale «VeriFactu solo es para negocios de España.» como único motivo: «Lo
remite ERPlora», si está disponible, no enseña el otorgamiento ni el trámite, y el certificado solo enseña su estado,
sin subirlo ni quitarlo.

### Ajustes
Aquí ves por qué vía salen tus registros (con tu certificado o por ERPlora) y en qué entorno de la AEAT estás, pruebas
o producción. Pasas a producción cuando ya no falta nada (si falta algo, la pantalla dice qué), o vuelves a pruebas
mientras no se haya sellado ningún registro en producción. También pruebas la conexión con la AEAT sin enviar nada,
creas una factura de prueba mientras estás en pruebas y lees la declaración responsable del sistema.

#### Detalle
Menú **VeriFactu → Ajustes**. Título «Ajustes de VeriFactu». Tres bloques:
- **«Envío»**: con la vía de ERPlora disponible, una frase con su icono dice por qué vía salen los registros y qué
  falta (VERIFACTU-F04), con «Abrir Configuración»: con tu certificado, «Envías tú directamente a Hacienda con el
  certificado de tu negocio, subido en Configuración → Mi certificado.»; por ERPlora con la autorización aprobada,
  «ERPlora remite tus registros de facturación a Hacienda en tu nombre, con su propio sello: tu autorización firmada
  está aprobada.»; por ERPlora en pruebas sin ella, «ERPlora remite tus registros de pruebas con su sello. Para pasar
  a producción, sube el certificado de tu negocio o consigue que ERPlora apruebe tu autorización firmada.»; por
  ERPlora en producción sin ella, «ERPlora remite en tu nombre con su sello, pero tu autorización firmada no está
  aprobada: tus registros esperan hasta que lo esté.». Debajo, «Entorno AEAT» con la pastilla «Pruebas (AEAT de pruebas)» o «Producción» y, según el caso, «Pasar a
  producción» (con «Todavía no puede pasar a producción:» y lo que falta, si falta algo) o «Volver a pruebas» con su
  explicación y su confirmación; en producción, «Las ventas y facturas nuevas se rechazan hasta que se resuelva:» y
  el motivo, si no hay ruta a la AEAT, y «Los registros están esperando:» y por qué, si esperan.
- **«Prueba en vivo»**: «Probar la conexión» y «Crear factura de prueba»; debajo, el resultado de la última
  prueba («Probado el», «Se remite», «Entorno», «Pasarela de ERPlora», «Emisor», «Vía lista» y «Este negocio puede
  enviar.» o «Todavía no puede enviar:» con los motivos), o «Aún no has ejecutado ninguna prueba.».
- **«Declaración responsable»**: «Leer la declaración firmada», «Versión de la declaración» y los «Datos
  identificativos de este sistema» (Productor, NIF del productor, Nombre del sistema, Código del sistema,
  Versión instalada, Número de instalación, Solo VERI\*FACTU, Puede dar servicio a varios obligados, Da
  servicio a varios obligados: siempre «S»).
Cuando la vía de ERPlora no está disponible, «Envío» muestra el estado del certificado y «Sube tu certificado» o
«Gestionar el certificado», sin la frase de la vía ni ninguna referencia a la autorización. Si falta para producción, un
aviso informativo junto a «Pasar a producción» dice «Puedes seguir probando. Para pasar a producción, sube el
certificado de tu negocio.», sin enlace propio: la acción es la que va junto al estado del certificado, una sola en la
tarjeta; los demás bloqueos siguen en su lista y el botón queda
deshabilitado mientras haya alguno. Los avisos y diagnósticos no recuperan la autorización ni el nombre de la vía
antigua, y «Probar la conexión» es secundario en pruebas.
En un negocio de fuera de España, arriba sale «VeriFactu solo es para negocios de España.» como único motivo, y «Pasar
a producción», «Probar la conexión» y «Crear factura de prueba» van deshabilitados.
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
| VERIFACTU-F01 | Activar VeriFactu | hecho — encender la app en el Hub es activarla, en ese negocio; fuera de España, Apps no la ofrece y el hub la niega (`can_enable`, hub#694), y una ya encendida no registra ni envía nada |
| VERIFACTU-F02 | Subir el certificado propio del negocio | hecho — en el Hub; cifrado en la BD del hub con `FISCAL_CERTIFICATE_KEY` |
| VERIFACTU-F03 | Quitar el certificado propio | hecho — en el Hub |
| VERIFACTU-F04 | Saber quién remite: mi certificado o ERPlora | hecho — la vía no se elige: la decide el certificado y queda fijada al pasar a producción |
| VERIFACTU-F05 | Firmar y subir el otorgamiento de representación para que remita ERPlora | hecho — se sube en el Hub, lo revisa el staff en el SaaS (`fiscal/`) y el estado vuelve en la foto; con la vía de ERPlora cerrada en el servidor no se ofrece |
| VERIFACTU-F06 | Volver a enviar el otorgamiento | hecho — en el Hub, como VERIFACTU-F05 |
| VERIFACTU-F08 | Pasar a producción | hecho — producción = despliegue `prod` ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (certificado propio vigente y aceptado por la AEAT de pruebas \| vía ERPlora abierta en el servidor con otorgamiento aprobado) ∧ cuenta activa, en todos los planes (también en Gratis); el servidor lo tiene cerrado hasta que ERPlora lo abra (bajo supervisión de Ioan) |
| VERIFACTU-F09 | Volver a pruebas | hecho |
| VERIFACTU-F10 | Probar la conexión con la AEAT | hecho — con la sonda de la pasarela del SaaS (`/internal/verifactu/probe`) |
| VERIFACTU-F11 | Crear una factura de prueba | hecho |
| VERIFACTU-F12 | Consultar la declaración responsable | hecho |
| VERIFACTU-F13 | Registrar una factura emitida | hecho — Facturación lo pide por nombre dentro de su emisión; el relay del outbox del worker queda de respaldo |
| VERIFACTU-F14 | Registrar una factura rectificativa | hecho — igual que F13 |
| VERIFACTU-F15 | Enviar el registro a la AEAT y recoger su respuesta | hecho — lo envía el worker por la pasarela del SaaS; sin `VERIFACTU_GATEWAY_URL` los registros esperan en la cola |
| VERIFACTU-F16 | Consultar los registros y su estado | hecho |
| VERIFACTU-F17 | Ver el detalle de un registro y por qué espera | hecho |
| VERIFACTU-F18 | Cotejar el QR en la sede de la AEAT | parcial — falta cotejar un registro en la app instalada, que abre la sede de la AEAT desde la versión 1.1.34 |
| VERIFACTU-F19 | Dar el QR y el estado fiscal al tique y a la factura | hecho (Ventas e Impresión lo piden por nombre) |
| VERIFACTU-F20 | Enviar después lo que no pudo salir (contingencia automática) | hecho — la corre el worker cada minuto, en cada negocio |
| VERIFACTU-F21 | Procesar la cola a mano | hecho |
| VERIFACTU-F22 | Reintentar una entrada de la cola | hecho |
| VERIFACTU-F24 | Actuar ante un registro rechazado por la AEAT | hecho |
| VERIFACTU-F25 | Reenviar un registro concreto | hecho — por la pasarela del SaaS |
| VERIFACTU-F26 | Verificar la cadena de huellas | hecho |
| VERIFACTU-F27 | Consultar lo que tiene la AEAT | hecho — por la pasarela del SaaS (`/internal/verifactu/query`) |
| VERIFACTU-F28 | Recuperar la cadena desde la AEAT tras restaurar una copia | hecho — por la pasarela del SaaS (`/internal/verifactu/query`) |
| VERIFACTU-F29 | Continuar la cadena de otra aplicación (migración) | hecho |
| VERIFACTU-F30 | Anular un registro enviado por error | hecho |
| VERIFACTU-F31 | Vigilar los envíos desde las pantallas | hecho — también desde los cuatro paneles del Inicio |
| VERIFACTU-F32 | Impedir apagar la app una vez encendida | hecho — `can_disable` de VeriFactu y 409 `base.app_vetoed` de `base.app.disable` (hub#267); en España no se apaga nunca |
| VERIFACTU-F34 | Renovar el certificado propio | hecho — en el Hub (subir el renovado sustituye al anterior) |
| VERIFACTU-F35 | Preguntar a la AEAT si ya tiene un registro de la cola | hecho — en la ficha del registro, en el admin del Hub y por la API |

### VERIFACTU-F01 Activar VeriFactu
Estado: hecho — encender la app en el Hub es activarla, en ese negocio; fuera de España, Apps no la ofrece y el hub la niega (`can_enable`, hub#694), una ya encendida no registra ni envía nada y el Inicio no le pide «Configura VeriFactu» (hub#682); ninguna plantilla la enciende, tampoco en España: la activa el dueño (hub#998)
Actor: administrador
Pantalla: Hub: Apps
Pasos:
1. En las apps del Hub, enciende **VeriFactu** (se enciende Facturación con ella).
2. Desde ese momento cada factura que emite Facturación se registra (VERIFACTU-F13) en el entorno de
   pruebas.
3. Solo en un negocio de España. En uno de otro país (el de su cuenta de erplora.com), Apps no la ofrece: sale
   «No disponible» con «VeriFactu solo es para negocios de España.» y sin «Activar», y el hub contesta lo mismo si se
   pide por el asistente o por la API. Un fichero de datos que la trae (el que exportó otro negocio) no promete
   encenderla, carga todo lo demás y queda completo, sin «Reintentar», diciendo por qué VeriFactu se queda fuera.
4. Si ya estaba encendida en un negocio de otro país, no hace nada y se puede desactivar: las facturas salen sin registro ni QR, **VeriFactu → Ajustes** y **VeriFactu → Configuración** dicen
   arriba «VeriFactu solo es para negocios de España.» sin ofrecer nada que lleve a la AEAT, y lo que pida registrar o enviar algo contesta lo mismo.
   «Termina de configurar tu negocio», en el Inicio, no le pide «Configura VeriFactu» ni el aviso «Todavía no puedes
   facturar» de la campana sale por ella; un negocio sin país (una demo) cuenta como España y sí lo ve (hub#682).
5. Ninguna plantilla la enciende, tampoco en España: ni «Empieza con un negocio como el tuyo» del Inicio ni «Usar
   plantilla» de **Ajustes → Datos y copias** la nombran en «Revisa lo que trae» ni la activan. Cargan todo lo demás del
   sector, Facturación incluida, y VeriFactu sigue «Desactivada» en Apps, con «Activar», y «Termina de configurar tu
   negocio» pide «Activa VeriFactu» hasta que el dueño la enciende él: le ata a la AEAT hasta el fin del año natural y
   ya no se apaga (VERIFACTU-F32).
Entra: nada más que la orden.
Sale: la app activa; sin interruptor propio.
Si falla: lo dice la página de apps del Hub.
Implicados: INVOICE-F01, BASE-F18, BASE-F31, BASE-F38

### VERIFACTU-F02 Subir el certificado propio del negocio
Estado: hecho — en el Hub; cifrado en la BD del hub con `FISCAL_CERTIFICATE_KEY`
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. En **Configuración**, pestaña «Mi certificado», pulsa «Elegir el fichero .p12 / .pfx» y elige el certificado
   del negocio (como mucho 1 MB).
2. Escribe su contraseña en «Contraseña del certificado» y pulsa «Subir el certificado».
3. El Hub lo abre con la contraseña, lee titular, NIF, tipo y caducidad y lo guarda cifrado, junto con la
   contraseña, en la base de datos del Hub. No mira qué entidad lo ha emitido: si vale, lo dice la AEAT de pruebas
   (paso 4). Sale, por ejemplo, «Certificado subido: Bar Sol SL (B12345678).» y la pestaña pasa a «Cargado». Subir
   otro sustituye al anterior.
4. Mientras el negocio está en pruebas, desde ese momento sus registros salen con él, también los que
   la pasarela había rechazado, y con ellos lo prueba la AEAT de pruebas. En la pestaña, la fila «AEAT de pruebas»
   dice «Sin probar todavía» y debajo «Se prueba con el próximo registro que salga en pruebas: cuando la AEAT de
   pruebas lo acepte, podrás pasar a producción.». Cuando la AEAT de pruebas contesta a un envío hecho con él con su
   veredicto sobre los registros (aunque rechace alguno por su contenido), pasa a «Aceptado» y ya puede pasar a
   producción con él. Si lo rechaza por el certificado, pasa a «Rechazado» y debajo sale por qué: la sede de la AEAT
   contesta con su página de error («Se ha producido un error al verificar el certificado presentado»: no lo ha
   emitido una entidad que reconozca, no vale para este servicio o ha caducado), o responde el
   fallo 4112 («El titular del certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o Sucesor»). Una
   AEAT caída o que no responde, un fallo del contenido del envío o un fallo pasajero como el 103 «NIF no
   identificado» (la AEAT de pruebas se lo ha dado a certificados buenos y al rato los identificaba) no lo cambian; si
   después la AEAT de pruebas lo acepta, pasa a «Aceptado». Subir otro lo deja
   otra vez «Sin probar todavía». En producción la fila no sale: la producción nunca prueba un certificado.
5. En un negocio de fuera de España no se ofrece: arriba dice «VeriFactu solo es para negocios de España.» y la pestaña solo enseña el estado del
   certificado, sin subirlo ni quitarlo.
Entra: el `.p12`/`.pfx` en base64 y su contraseña (`verifactu.certificate.upload`).
Sale: el certificado guardado (`OwnCertificate`), un evento «Certificado propio de … subido» y el aviso
`verifactu.config.changed`; cuando la AEAT de pruebas lo acepta o lo rechaza, el evento «La AEAT de pruebas ha aceptado el certificado propio de …: el negocio ya puede pasar a producción
con él.» o «La AEAT de pruebas ha rechazado el certificado propio de … (motivo): sube otro.» y el mismo aviso. El fichero y la contraseña no se vuelven a mostrar: ni en la API, ni en el admin,
ni en la foto, ni en los registros del servidor.
Si falla: el certificado no se guarda y la pantalla dice por qué:
- si este servidor todavía no puede guardar certificados, «Este servidor aún no puede guardar certificados: ERPlora
  tiene que configurar su clave de almacenamiento.»;
- sin emisor, pide configurarlo antes en Facturación, pestaña Emisor;
- con una contraseña mala o un fichero que no es un .p12, «El fichero no es un certificado .p12/.pfx que abra esta
  contraseña.»; autofirmado, «Este certificado no lo ha emitido ninguna entidad (es autofirmado), así que la AEAT
  no lo aceptará. Usa el certificado electrónico de tu negocio emitido por una entidad reconocida, por ejemplo la
  FNMT.»; sin uso de autenticación de cliente, «El certificado no permite la autenticación de cliente,
  así que no puede conectar con la AEAT.»; caducado, por ejemplo «El certificado caducó el 2025-12-31: sube uno
  vigente.»;
- con un titular distinto del emisor de Facturación, por ejemplo «El certificado es de B87654321, no del emisor de
  este negocio, B12345678.»: por la vía propia se presentaría en nombre de otro.
Implicados: VERIFACTU-F04, VERIFACTU-F08, VERIFACTU-F34

### VERIFACTU-F03 Quitar el certificado propio
Estado: hecho — en el Hub
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. En «Mi certificado», con uno cargado, pulsa «Quitar»; una tarjeta pregunta «¿Quitar el certificado?» y dice qué
   pasará (la pantalla Configuración).
2. Al confirmar, el certificado se borra de la base de datos del Hub, sale «Certificado quitado.» y la pestaña
   pasa a «Sin cargar».
3. En pruebas, los registros que aún no han salido pasan a salir con el sello de ERPlora, también los que la
   pasarela había rechazado. En producción con la vía del certificado fijada, dejan de poder salir hasta subir otro:
   esperan en la cola con el motivo «tu certificado propio no está cargado o ha caducado» y las ventas nuevas se
   rechazan; nunca vuelven al sello. En producción con la vía de ERPlora fijada, no cambia
   nada.
Entra: nada (`verifactu.certificate.remove`).
Sale: el certificado borrado, un evento «Certificado propio de … quitado» y el aviso `verifactu.config.changed`.
Si falla: sin permiso para configurar VeriFactu no sale «Quitar», y pedirlo por otra puerta se rechaza.
Implicados: VERIFACTU-F04, VERIFACTU-F08

### VERIFACTU-F04 Saber quién remite: mi certificado o ERPlora
Estado: hecho — la vía no se elige: la decide el certificado y queda fijada al pasar a producción
Actor: administrador
Pantalla: Ajustes
Pasos:
1. La vía la decide el certificado. Con un certificado propio cargado y vigente, los registros salen
   con él; sin él, en pruebas los remite ERPlora con su sello, también en un
   negocio de demostración. Mientras el negocio está en pruebas, subir, quitar o dejar caducar el certificado cambia
   la vía de lo que aún no ha salido.
2. En **Ajustes**, «Envío» lo dice en una frase con su icono, con lo que falta.
3. Al pasar a producción, la vía de ese momento queda fijada: con un certificado válido, el
   certificado, aunque también esté aprobada la autorización; sin él, la de ERPlora. Desde entonces, subir, quitar o
   dejar caducar el certificado no la cambia. Con la del certificado fijada y sin certificado válido, los registros
   esperan y las ventas nuevas se rechazan; nunca vuelven al sello. Con la de ERPlora fijada, sigue enviando y
   anulando con el sello mientras su autorización siga aprobada.
4. ERPlora puede dejar de presentar por cuenta de los negocios en un servidor (de partida presenta): entonces solo se
   pasa a producción con el certificado propio. Las pruebas sin certificado, también las de las
   demos, siguen saliendo con el sello, y quien ya está en producción por ella sigue enviando y anulando por ella. El
   negocio de la propia ERPlora no se ve afectado: remite siempre con el sello.
5. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.».
Entra: el certificado subido (VERIFACTU-F02, F03), el entorno y, de la cuenta, el estado de la autorización.
Sale: la vía con la que sale cada registro, en `verifactu.config.get` (`route`); al pasar a producción, guardada.
Si falla: no hay nada que elegir ni que rechazar. Lo que falta para enviar lo dice «Los registros están esperando:»,
y lo que falta para pasar a producción, la lista «Todavía no puede pasar a producción:», en la misma pantalla.
Implicados: VERIFACTU-F02, VERIFACTU-F03, VERIFACTU-F05, VERIFACTU-F08

### VERIFACTU-F05 Firmar y subir el otorgamiento de representación para que remita ERPlora
Estado: hecho — se sube en el Hub, lo revisa el staff en el SaaS y el estado vuelve en la foto
Actor: administrador (permiso «configurar»)
Pantalla: Configuración
Pasos:
1. En **Configuración**, pestaña «Lo remite ERPlora», el estado dice «Sin firmar».
2. «Descargar el modelo» baja el modelo oficial (el Anexo I del Convenio 17, que da ERPlora) con los datos del negocio ya
   puestos: la razón social, el NIF y la dirección del emisor de Facturación (el municipio y la vía pública, con el
   número tal como figura en la dirección); sin emisor, baja en blanco. Se completa lo que falte y se firma fuera de
   la pantalla: a mano (y se escanea a PDF, con el sello si es una sociedad) o con AutoFirma. Debajo del botón sale
   «Modelo descargado. Fírmalo y súbelo aquí abajo.»; dentro de la app de ERPlora el modelo se guarda en Descargas y
   sale también la carpeta donde ha quedado.
3. Una sociedad escribe su representante legal (nombre y NIF/NIE); un autónomo firma él mismo.
4. Se elige el documento de identidad (DNI o NIE) y se adjuntan los PDF: el modelo firmado, la copia del
   documento, con NIE una muestra de la firma y, con sociedad, el justificante de representación.
5. «Enviar a revisión»: el Hub comprueba los documentos y los reenvía tal cual a ERPlora; queda «En revisión».
6. Una persona de ERPlora lo revisa; tu cuenta de ERPlora manda al Hub el estado nuevo: «Aprobado», «Devuelto»
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
Si falla: antes de enviar nada, la pantalla dice lo que falta: el modelo («Adjunta el modelo firmado.»), que sea un
PDF («El modelo firmado tiene que ser un PDF — escanéalo o fírmalo con AutoFirma.»), la copia del documento, con NIE
la muestra de firma, con sociedad el representante o el justificante, o un fichero de más de 5 MB («Cada fichero
puede ocupar 5 MB como máximo.»). Si ERPlora lo rechaza al recibirlo, sale su motivo. Sin emisor en Facturación, pide
configurarlo antes; si ERPlora todavía no ha vinculado el negocio, «ERPlora todavía no ha vinculado este negocio.»; si
ERPlora no contesta, «ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.». Si ERPlora deja de
presentar por cuenta de los negocios, la pestaña «Lo remite ERPlora» ya no sale, y pedirlo por otra puerta contesta
«De momento ERPlora no presenta por cuenta de los negocios: presenta con tu propio certificado.».
Al descargar el modelo, un dato del emisor que el modelo no puede escribir (una letra fuera de las suyas o un texto
demasiado largo) baja en blanco para escribirlo a mano, con el resto ya puesto: nunca deja sin modelo. Dentro de la app,
si no lo puede guardar, lo dice con su motivo y no sale «Modelo descargado».
Implicados: VERIFACTU-F08, BASE-F112 (dentro de la app)

### VERIFACTU-F06 Volver a enviar el otorgamiento
Estado: hecho — en el Hub, como VERIFACTU-F05
Actor: administrador (permiso «configurar»)
Pantalla: Configuración
Pasos:
1. Devuelto o revocado, el trámite ya está abierto: se corrige lo que dice el motivo y se envía de nuevo.
2. En revisión o aprobado, «Volver a enviar» lo abre y avisa: el envío nuevo sustituye al que está en revisión;
   con uno aprobado, se sigue remitiendo con él mientras se revisa el nuevo. «Cancelar» lo cierra.
Entra: como VERIFACTU-F05.
Sale: como VERIFACTU-F05; el envío lleva el número siguiente.
Si falla: lo mismo que al enviarlo la primera vez.
Implicados: VERIFACTU-F05

### VERIFACTU-F08 Pasar a producción
Estado: hecho — producción = despliegue `prod` ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (certificado propio vigente y
aceptado por la AEAT de pruebas | vía ERPlora abierta en el servidor con otorgamiento aprobado) ∧ cuenta activa (`status` de la foto), en todos los planes
(también en Gratis, sin opción de pago); el servidor lo tiene cerrado hasta que ERPlora lo abra (bajo supervisión de Ioan). En `pre` nunca se abre: todo va a pruebas. Un
hub demo nunca pasa a producción (`verifactu.go_live_forbidden`).
Actor: administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes**, «Entorno AEAT» enseña «Pruebas (AEAT de pruebas)» y «Tus facturas van al entorno de
   pruebas de la AEAT. Cuando esté todo listo, pasa a producción.». Si falta algo, debajo sale «Todavía no puede
   pasar a producción:» con la lista (negocio de demostración, otorgamiento sin aprobar, vía de ERPlora cerrada en el
   servidor, certificado propio que falta o ha caducado, certificado propio que la AEAT de pruebas aún no ha aceptado
   o ha rechazado, cuenta con un pago pendiente o suspendida) y «Pasar a
   producción» queda desactivado. Ningún plan falta en ella: VeriFactu en vivo es de todos los planes.
2. Pulsa «Pasar a producción» y confirma en «¿Enviar tus facturas a la AEAT de verdad?» («A partir de ahora
   cada registro se remite a la AEAT real. En cuanto se selle el primero ya no podrás volver a pruebas.»).
3. Sale «Tu negocio está en producción: los registros ya se remiten a la AEAT real.» y la pastilla pasa a
   «Producción».
Entra: el emisor de Facturación; el certificado propio, su caducidad y si la AEAT de pruebas lo ha aceptado
(VERIFACTU-F02); de la foto de la cuenta
(`verifactu.config.sync`), el otorgamiento y el estado del negocio (la foto de un SaaS anterior aún trae `live_paid`:
se acepta y no se lee).
Sale: el entorno en producción y la vía de ese momento fijada (VERIFACTU-F04: con certificado válido, el certificado;
sin él, la de ERPlora), avisando `verifactu.config.changed`: los registros nuevos nacen en la cadena de producción, con
el QR de la sede real; los que nacieron en pruebas siguen yendo a pruebas.
Si falla: mientras falte algo, «Pasar a producción» se queda desactivado, el entorno sigue en pruebas y la lista
«Todavía no puede pasar a producción:» dice qué falta:
- que ERPlora todavía no haya abierto la presentación real a la AEAT en este servidor, o que falte su pasarela de
  envío;
- que sea un negocio de demostración, que siempre presenta en el entorno de pruebas de la AEAT;
- con tu certificado, que este servidor no lo pueda abrir (hay que volver a subirlo en «Mi certificado»), que la AEAT
  de pruebas aún no lo haya aceptado (se prueba con el próximo registro que salga en pruebas: haz una venta o una
  factura y pasa a producción cuando lo acepte) o que lo haya rechazado (hay que subir otro);
- sin certificado válido, que ERPlora no haya aprobado todavía tu autorización firmada o, si ERPlora no presenta por
  cuenta de los negocios, que falte tu propio certificado;
- que tu cuenta de ERPlora tenga un pago pendiente o esté suspendida: hay que regularizar el pago en tu cuenta.

Sin emisor en Facturación, pide configurarlo antes. Ya en producción, no hace nada. En un negocio de fuera de España,
Ajustes dice arriba «VeriFactu solo es para negocios de España.» como único motivo y «Pasar a producción» va
deshabilitado.
Si en producción se pierde la vía fijada (con la de ERPlora, se revoca tu autorización; con la del certificado, caduca
o se quita), no se cambia de vía ni se vuelve a pruebas: no se sella nada nuevo. La venta o la factura se rechazan con
«No se ha emitido nada: este negocio presenta en real a la AEAT y ahora no puede hacerle llegar sus registros:» y el
motivo, y Ajustes lo dice bajo «Las ventas y facturas nuevas se rechazan hasta que se resuelva:». Lo ya sellado
espera, porque no se podría presentar.
Si ERPlora deja de presentar por cuenta de los negocios, quien ya está en producción por esa vía sigue sellando,
enviando y anulando con el sello de ERPlora, porque la AEAT solo acepta una anulación presentada con el mismo sello;
subir después un certificado tampoco la cambia. Quien ya está en producción con su certificado y sube otro sigue
enviando con él sin que se pruebe: la producción nunca prueba un certificado.
Implicados: VERIFACTU-F04, VERIFACTU-F05, VERIFACTU-F09

### VERIFACTU-F09 Volver a pruebas
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
Estado: hecho — con la sonda de la pasarela del SaaS (`/internal/verifactu/probe`)
Actor: responsable, administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes**, «Prueba en vivo», pulsa «Probar la conexión» (los botones esperan mientras prueba).
2. El Hub comprueba, sin presentar nada a la AEAT, todo lo que hace falta para enviar: el emisor, los datos del
   productor, la vía y su estado y, si la pasarela está configurada, le pregunta si puede presentar ahora.
3. Debajo sale el resultado, línea a línea, y «Este negocio puede enviar.» o «Todavía no puede enviar:» con los
   motivos.
4. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.» y «Probar la conexión» va deshabilitado.
Entra: la configuración del Hub; la respuesta de la sonda de la pasarela.
Sale: el resultado como evento «Prueba de conexión» (avisa `verifactu.diagnostic.run`), sin crear ningún
registro ni tocar la cadena.
Si falla: lo que falta, dicho en el resultado. Nunca presenta un registro de muestra: un registro remitido no
se puede deshacer.
Implicados: VERIFACTU-F15

### VERIFACTU-F11 Crear una factura de prueba
Estado: hecho
Actor: administrador
Pantalla: Ajustes
Pasos:
1. Con el negocio en pruebas, en **Ajustes**, «Prueba en vivo», pulsa «Crear factura de prueba». En producción el
   botón no aparece.
2. VeriFactu pide a Facturación un tique (F2) de una línea «Prueba VeriFactu» de 1,00 € más el 21 % de IVA en
   la serie TICKET, como una factura hecha a mano.
3. Sale, por ejemplo, «Factura de prueba TICKET-2026-000001 creada: su registro está en Registros.».
4. En un negocio de fuera de España, arriba dice «VeriFactu solo es para negocios de España.» y «Crear factura de prueba» va deshabilitado.
Entra: nada que escribir.
Sale: una factura real de Facturación en pruebas y su registro, que sale como cualquier otro.
Si falla: el rechazo de Facturación (sin emisor, sin permiso de emitir).
Implicados: INVOICE-F03

### VERIFACTU-F12 Consultar la declaración responsable
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ajustes
Pasos:
1. En **Ajustes**, tarjeta «Declaración responsable», «Leer la declaración firmada» abre la
   publicada en erplora.com (en la app instalada, en el navegador del dispositivo); al lado, «Versión de la declaración».
2. «Datos identificativos de este sistema» enseña los datos del productor, la versión instalada y el número de
   instalación (el identificador de este negocio en ERPlora).
Entra: la declaración (fija en la versión del Hub).
Sale: nada; es consulta.
Si falla: el mensaje del fallo; en la app instalada, si no puede abrirla, «No se ha podido abrir esa página. Inténtalo de nuevo.».
Implicados: ninguno

### VERIFACTU-F13 Registrar una factura emitida
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
Implicados: INVOICE-F01, INVOICE-F02, INVOICE-F03, INVOICE-F05

### VERIFACTU-F14 Registrar una factura rectificativa
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
El registro de un negocio se presenta siempre como ese negocio, nunca como el hub de ERPlora (hub#454): el worker
pasa por cada negocio en su BD y con su ámbito, y cada pasada presenta lo que guarda su BD como su negocio, sea cual
sea el NIF del registro. La BD del hub de ERPlora solo guarda los registros de ERPlora (hub#602, hub#1130).
Implicados: VERIFACTU-F20, FLOW-F04 (la tarjeta de la galería de Automatizaciones que crea una tarea urgente cuando
la AEAT rechaza un registro)

### VERIFACTU-F16 Consultar los registros y su estado
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Registros
Pasos:
1. Abre **Registros**.
2. Busca por número de factura, secuencia, nombre o NIF del emisor, o filtra por estado, tipo, tipo de
   factura, entorno, fecha y total.
3. Cada fila enseña su estado con color: verde «Aceptado», ámbar «Pendiente» / «Enviado» / «Aceptado con
   errores», rojo «Rechazado»; y su entorno, para no confundir pruebas con producción.
Entra: los registros.
Sale: nada; es consulta.
Si falla: el mensaje con «Reintentar». El total se lee como en cualquier campo de importe del Hub y como en las
demás listas («1.000,50», «1,000.50», «2 500» y «12,50 €» filtran); uno que no se puede leer lo dice
bajo su campo con las palabras del campo de importe («Esto no es un importe. Escribe una cifra, por ejemplo
12,50.», «Este importe no puede ser negativo.» o, con «1.000» en euros, «Este importe se puede leer de dos
maneras…»), y una fecha final anterior a la inicial, «La fecha final no puede ser anterior a la inicial.»; ninguno
de los dos filtra.
Implicados: INVOICE-F16

### VERIFACTU-F17 Ver el detalle de un registro y por qué espera
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Ficha de registro
Pasos:
1. En **Registros**, pulsa una fila.
2. Se abre su ficha, por ejemplo «Registro TICKET-2026-000001», con la factura, la cadena, el QR, la respuesta de
   la AEAT y el XML.
3. Si no está en la AEAT, «Aún no está en la AEAT» dice por qué («la pasarela de envío de ERPlora no está
   configurada en este servidor», «tu certificado propio no está cargado o ha caducado», que la AEAT pidió esperar
   hasta cierta hora, que no se ha podido contactar con la pasarela o con la AEAT) y un solo cuándo: si
   todo lo que espera se resuelve solo (la AEAT pidió esperar, sin contacto, sin respuesta, un fallo de la AEAT),
   «Sale solo en la próxima pasada, en orden y declarado como envío tardío si ya falló antes. No tienes que hacer
   nada.»; si espera a que se resuelva algo (un rechazo de la pasarela, que no se reenvía solo; la autorización; la
   vía; el servidor), «Sale solo, en orden y declarado como envío tardío, en cuanto se resuelva.». Debajo, el
   «Próximo intento».
4. En un negocio de fuera de España dice solo «este negocio no está en España: VeriFactu solo es para negocios de
   España, así que no se envía nada a la AEAT», sin próximo intento ni botones para enviar, subsanar o anular:
   nunca sale.
Entra: el registro.
Sale: nada; es consulta.
Si falla: «Registro no encontrado» o el mensaje del fallo.
Implicados: VERIFACTU-F15

### VERIFACTU-F18 Cotejar el QR en la sede de la AEAT
Estado: parcial — falta cotejar un registro en la app instalada: desde la versión 1.1.34 la app abre la sede de la AEAT en
el navegador del dispositivo, pero aún no se ha probado en un dispositivo
Actor: empleado, responsable, administrador, cliente
Pantalla: Registros
Pasos:
1. En **Registros**, «Cotejar en la AEAT» en la fila (o en la ficha) abre en otra pestaña (en la app instalada, en el
   navegador del dispositivo) la página de cotejo de la AEAT con el NIF del emisor, el número, la fecha y el importe.
2. Un registro nacido en pruebas lleva a la sede de pruebas; uno de producción, a la sede real.
3. El cliente hace lo mismo escaneando el QR de su tique o su factura.
Entra: el enlace del QR fijado al sellar.
Sale: nada en el Hub.
Si falla: un registro que aún no ha salido se ve en la AEAT como no encontrado; uno rechazado, nunca. En la app
instalada, si no puede abrir la página, «No se ha podido abrir esa página. Inténtalo de nuevo.».
Implicados: VERIFACTU-F19

### VERIFACTU-F19 Dar el QR y el estado fiscal al tique y a la factura
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
Estado: hecho — la corre el worker cada minuto, en cada negocio
Actor: sistema
Pantalla: Contingencia
Pasos:
1. Mientras se vende nada se para por esto: si la pasarela, la AEAT o la red están caídas, el cobro sigue y el
   registro espera.
2. Cada minuto el sistema hace la pasada de envío en todas las cadenas a las que les toca, cada una en su
   entorno, en orden y respetando la espera que pidió la AEAT; si se perdieron pasadas (servidor parado), al volver
   se hace una sola.
3. Lo que vuelve a fallar espera más (5, 10, 20, 40 y 60 minutos), sin límite de intentos.
4. Queda el evento de la pasada en **Eventos**, por ejemplo «Cola procesada: 3 enviados, 3 aceptados, 0 rechazados, 0
   en espera.».
Entra: los registros pendientes.
Sale: los envíos y sus respuestas (avisa `verifactu.contingency.processed`).
Si falla: lo que no sale sigue en la cola con su motivo; en un negocio de fuera de España no sale nunca. La pasada
presenta cada registro como el negocio al que pertenece, nunca como el de ERPlora.
Implicados: VERIFACTU-F15

### VERIFACTU-F21 Procesar la cola a mano
Estado: hecho
Actor: responsable, administrador
Pantalla: Contingencia
Pasos:
1. En **Contingencia**, pulsa «Procesar cola» («Procesando…»).
2. Se hace en ese momento la misma pasada que la automática.
3. Debajo de la tabla sale el resultado; la tabla se pone al día sola.
Entra: la cola.
Sale: como VERIFACTU-F20.
Si falla: sin pasarela, el aviso «la pasarela de envío de ERPlora no está configurada en este servidor»; los
registros siguen en la cola y salen en cuanto lo esté.
Implicados: VERIFACTU-F20

### VERIFACTU-F22 Reintentar una entrada de la cola
Estado: hecho
Actor: responsable, administrador
Pantalla: Contingencia
Pasos:
1. En **Contingencia**, pulsa «Reintentar» en la fila.
2. El registro (y los anteriores de su cadena, que salen antes que él) pasan a salir en la siguiente pasada;
   los intentos se conservan.
Entra: el registro elegido.
Sale: el registro reprogramado (avisa `verifactu.contingency.retried`).
Si falla: un registro aceptado o rechazado no está en la cola: «Este registro no está en la cola: ya está en la AEAT, o la AEAT lo
rechazó.».
Implicados: VERIFACTU-F21

### VERIFACTU-F24 Actuar ante un registro rechazado por la AEAT
Estado: hecho
Actor: administrador
Pantalla: Registros, Ficha de registro
Pasos:
1. El registro sale en rojo «Rechazado» en **Registros**, y a su lado «Pendiente de subsanar»; en **Eventos** queda
   «Envío fallido» con el motivo. El filtro «Subsanación», en «Pendientes de subsanar», deja solo los que faltan.
2. En su ficha, «La AEAT lo ha rechazado» con el código y el mensaje literales de la AEAT y qué hacer: si el
   error está en los datos de la factura (un NIF de cliente que la AEAT no reconoce, un importe), se corrige
   **en Facturación** con una rectificativa; si no (un error de la cadena tras restaurar una copia, un fallo
   nuestro), «Subsanar».
3. «Subsanar» (con confirmación) sella un registro **nuevo** de la misma factura, leída otra vez, marcado como
   subsanación, que entra en la cola. El rechazado se queda tal cual. El registro nuevo le dice a la AEAT si ya tenía
   esa factura o si se rechazó desde el primer envío.
4. Un «Aceptado con errores» también se puede subsanar.
5. Ya subsanado, en **Registros** el de antes dice «Subsanado», que abre el registro que lo subsana, y su ficha,
   «Ya está subsanado con un registro nuevo» con «Ver el registro que lo subsana». Si la AEAT rechaza también la
   subsanación, esa sale «Pendiente de subsanar» y se subsana a su vez; la de antes sigue «Subsanado».
Entra: el registro rechazado o aceptado con errores.
Sale: el registro de subsanación (avisa `verifactu.record.created`).
Si falla: solo se subsana un registro de alta rechazado o aceptado con errores, y solo el último de su
factura: «Este registro no se puede subsanar: solo se subsana el último registro de un alta que la AEAT rechazó o
aceptó con errores.».
Implicados: INVOICE-F08

### VERIFACTU-F25 Reenviar un registro concreto
Estado: hecho — por la pasarela del SaaS
Actor: responsable, administrador, asistente
Pantalla: Ficha de registro
Pasos:
1. En la ficha de un registro pendiente o enviado sin respuesta, pulsa «Enviar ahora».
2. Sale ya su cadena hasta él (los anteriores pendientes van delante, en orden), si la espera de la AEAT ya
   pasó.
3. El registro queda con la respuesta de la AEAT: «Aceptado», «Aceptado con errores» o «Rechazado».
Entra: el registro elegido (por su id o por el número de su factura).
Sale: el envío y su respuesta (avisa `verifactu.record.transmitted`).
Si falla: sin pasarela, «No se puede enviar ahora: la pasarela de envío de ERPlora no está configurada en este
servidor. Sigue en la cola y sale en cuanto se pueda.»; ya aceptado o rechazado, «Este registro no está en la cola:
ya está en la AEAT, o la AEAT lo rechazó.»; con la espera
de la AEAT en curso, por ejemplo «La AEAT pidió esperar: sale solo a las 12:05.». Nunca dice «aceptado» sin respuesta.
Implicados: VERIFACTU-F15

### VERIFACTU-F26 Verificar la cadena de huellas
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Recuperación
Pasos:
1. En **Recuperación**, con el «NIF del emisor», pulsa «Validar cadena» («Trabajando…»).
2. El sistema recalcula la huella de cada registro de la cadena del entorno actual y comprueba que cada uno
   lleva la del anterior.
3. Sale «Operación completada.» y el veredicto: por ejemplo, «Cadena de huellas íntegra: 120 registros con su
   encadenado SHA-256 verificado (B12345678). No se re-auditan los importes.» o «Cadena de huellas ROTA en la
   secuencia 57 (B12345678).».
Entra: los registros de la cadena.
Sale: el veredicto como evento (avisa `verifactu.chain.validated`). Solo lee: no repara nada ni re-audita los
importes.
Si falla: sin registros de ese NIF, «No hay registros de ese emisor en este entorno.».
Implicados: VERIFACTU-F28

### VERIFACTU-F27 Consultar lo que tiene la AEAT
Estado: hecho — por la pasarela del SaaS (`/internal/verifactu/query`)
Actor: responsable, administrador
Pantalla: Recuperación
Pasos:
1. En **Recuperación**, pulsa «Consultar AEAT» («Trabajando…»).
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
Estado: hecho — por la pasarela del SaaS (`/internal/verifactu/query`)
Actor: administrador
Pantalla: Recuperación
Pasos:
1. Tras restaurar una copia de la base de datos (la AEAT tiene registros que la copia no), deja de emitir y
   abre **Recuperación**.
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
Estado: hecho
Actor: administrador
Pantalla: Recuperación
Pasos:
1. En **Recuperación**, bloque «Continuar cadena manualmente (migración)», escribe la «Última
   huella (64 hex)» de la aplicación anterior, el «Nº de factura» y la «Fecha» de ese último registro.
2. Pulsa «Continuar desde esta huella» y confirma («La huella indicada será el antecedente del próximo
   registro fiscal. Usa esta opción únicamente durante una migración y con los datos del último registro de la
   aplicación anterior.»).
3. Sale «Operación completada.»; la próxima factura se encadena sobre esa huella.
Entra: la huella, el número y la fecha del último registro de la aplicación anterior.
Sale: un ancla nueva (avisa `verifactu.chain.recovered`).
Si falla: una huella que no tiene 64 caracteres hexadecimales, «La huella debe tener 64 caracteres
hexadecimales»; sin número o fecha, que son parte del encadenado, el campo lo pide; con registros pendientes en
la cadena, «Antes tienen que salir los registros pendientes de esta cadena.».
Implicados: ninguno

### VERIFACTU-F30 Anular un registro enviado por error
Estado: hecho
Actor: administrador, asistente
Pantalla: Ficha de registro
Pasos:
1. Solo para una factura que **nunca debió emitirse** (un duplicado, una prueba hecha en producción). Una
   devolución o una corrección no se anula: es una rectificativa en Facturación.
2. En la ficha del registro de alta, pulsa «Anular registro», escribe el motivo y confirma («Se declarará a la
   AEAT que esta factura se emitió por error. Una devolución o una corrección nunca es esto: es una rectificativa
   en Facturación. La factura sigue en Facturación.»).
3. Se sella un registro de **anulación** encadenado, que sale como cualquier otro, y aparece en Registros con
   tipo «Anulación».
Entra: el registro de alta (o el número de su factura).
Sale: el registro de anulación (avisa `verifactu.record.created`).
Si falla: un alta rechazada no se anula (no está en la AEAT); una ya anulada, tampoco: «Este registro no se
puede anular: solo se anula un alta que está (o estará) en la AEAT y no tiene anulación.». Si la AEAT rechazó la
anulación, se puede volver a anular: la nueva le dice a la AEAT que la anterior se rechazó.
Implicados: INVOICE-F07

### VERIFACTU-F31 Vigilar los envíos desde las pantallas
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

### VERIFACTU-F32 Impedir apagar la app una vez encendida
Estado: hecho — la plataforma pregunta al apagar (`base.app.disable`, hub#256) y VeriFactu responde con su
`can_disable` (hub#267); en España, una vez encendida, no se apaga nunca, y Apps no ofrece «Desactivar» (hub#618)
Actor: sistema
Pantalla: Hub: Apps
Pasos:
1. Al apagar VeriFactu en un negocio de España, la plataforma le pregunta y VeriFactu lo niega siempre: una vez
   encendida, las facturas del negocio tienen que seguir llegando a la AEAT (la ley obliga a seguir con VERI*FACTU
   al menos hasta que acabe el año natural, y ERPlora no tiene otra forma de registrarlas). En **Apps** su fila no
   ofrece «Desactivar» y dice ese motivo (BASE-F25).
2. Da igual lo que haya en la cola: con registros por enviar o con todo ya contestado por la AEAT, la respuesta es
   la misma. VeriFactu sigue encendida y sus registros se quedan como estaban. Tampoco se pueden apagar las apps que
   necesita: Facturación y, por ella, Impuestos, Ventas / TPV y Clientes; sus filas tampoco lo ofrecen y dicen por
   qué (hub#619).
3. Un negocio sin país (una demo) es de España: tampoco se apaga.
4. Mientras su estado dice «Activándose…» o «No se ha podido activar» todavía no ha estado encendida ni ha sellado
   nada: se puede desactivar.
5. En un negocio de fuera de España no lo niega nunca: sus registros no se van a enviar, así que apagarla no para
   nada; se guardan tal cual.
Entra: la petición de apagar.
Sale: nada en España con la app encendida; si no, la app apagada.
Si falla: «VeriFactu no se puede desactivar una vez activada: la ley obliga a que tus facturas sigan llegando a la
AEAT.».
Implicados: BASE-F21, BASE-F23, BASE-F25

### VERIFACTU-F34 Renovar el certificado propio
Estado: hecho — en el Hub (subir el renovado sustituye al anterior)
Actor: propietario y administrador (configurar)
Pantalla: Configuración
Pasos:
1. «Mi certificado» enseña su fecha en «Caduca el» y, a 30 días o menos, por ejemplo «Caduca en 12 días: sube aquí
   el renovado.».
2. El certificado nuevo se sube como el primero, con «Elegir el fichero .p12 / .pfx», su contraseña y «Subir el
   certificado», y sustituye al anterior; la cadena no cambia.
Entra: el certificado renovado.
Sale: el nuevo, en lugar del anterior.
Si falla: caducado, en pruebas los registros salen con el sello de ERPlora hasta subir el renovado, y en producción
con la vía del certificado fijada esperan con el motivo; si el servidor cambió
su clave de almacenamiento y no puede abrir el guardado, esperan con «tu certificado propio no se puede abrir
en este servidor: vuelve a subirlo».
Implicados: VERIFACTU-F02

### VERIFACTU-F35 Preguntar a la AEAT si ya tiene un registro de la cola
Estado: hecho — en la ficha del registro, en el admin de Django del Hub (soporte) y por la API
Actor: responsable, administrador (enviar); el staff de ERPlora desde el admin
Pantalla: Ficha de registro («Preguntar a la AEAT»); para el staff, el admin de Django (Registros → «Consultar a la
AEAT (sale de la cola si ya lo tiene)»)
Pasos:
1. Un registro se quedó «Enviado» sin respuesta (o «Pendiente») y puede que la AEAT ya lo tenga: en su ficha, pulsa
   «Preguntar a la AEAT».
2. Se consulta a la AEAT, por la pasarela de ERPlora, el emisor del registro en el mes de su fecha de expedición;
   la tabla «Últimos registros en la AEAT» de Recuperación queda al día con esa consulta.
3. Si la AEAT devuelve **ese mismo registro** (mismo emisor, número y huella), sale de la cola como «Aceptado» o
   «Aceptado con errores», según lo que diga la AEAT, sin perder sus intentos; queda un evento con quién lo hizo.
4. Si no lo tiene (o tiene otro registro de la misma factura, p. ej. el original de una subsanación), no cambia
   nada: sigue en la cola y se envía en la siguiente pasada.
Entra: el registro (id o número de su factura).
Sale: si la AEAT lo tenía y el registro (avisa `verifactu.record.reconciled`; la consulta, `verifactu.aeat.queried`).
En la ficha sale «La AEAT ya tiene {número}: sale de la cola.» o, en aviso, «La AEAT no tiene {número}: sigue en la
cola y sale en la siguiente pasada.».
Si falla: un registro aceptado o rechazado no está en la cola (la ficha no ofrece el botón; por la API, «Este
registro no está en la cola: ya está en la AEAT, o la AEAT lo rechazó.»); sin pasarela o si la AEAT no contesta, el motivo, encima de los botones, y el
registro sigue en la cola.
Implicados: VERIFACTU-F22, VERIFACTU-F27

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de la propia persona)
y la API, con las mismas reglas y permisos, salvo subir el certificado propio y enviar el otorgamiento firmado:
llevan ficheros y la contraseña del certificado, que no se dicen ni se escriben en una conversación, así que el
asistente no los ofrece y se hacen en **VeriFactu → Configuración** («Mi certificado» y «Lo remite ERPlora») o por
la API. Pensado para la voz: un registro se nombra por el **número de su
factura** (`TICKET-2026-000012`) o por su secuencia; un emisor, por su NIF.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| La configuración: entorno, vía con la que salen los registros (y si la de ERPlora está disponible), certificado propio (titular, NIF, tipo, caducidad; nunca su material), estado de la autorización, datos del productor, declaración | ver | F02, F04, F08, F09, F12 | `verifactu.config.get` |
| Los registros, con búsqueda, filtros, orden y páginas (hasta 100) | ver | F16 | `verifactu.record.list` |
| Un registro, por su id o por el número de su factura, con su QR, su XML y por qué espera | ver | F17, F18 | `verifactu.record.get` |
| El registro vigente de una factura (QR, CSV, estado) | ver | F19 | `verifactu.record.by_invoice` |
| La cola: los registros que aún no están en la AEAT | ver | F20–F22 | `verifactu.contingency.list` |
| Los eventos de auditoría, con búsqueda por palabras y filtros | ver | F31 | `verifactu.event.list` |
| Cuántos registros no están en la AEAT | ver | F31 | `verifactu.stats.compliance_summary` |
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
| Plataforma (`base.app.disable`) | No apagar VeriFactu una vez encendida (en España) | `can_disable` de `VerifactuConfig` |
| Plataforma (`base.app.enable`) | No encender VeriFactu fuera de España | `can_enable` de `VerifactuConfig` |

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver registros, cola, eventos, cadena y configuración; verificar la cadena | sí | sí | sí | sí | `verifactu.view_record` |
| Registrar una factura emitida (lo pide Facturación con la sesión de quien emite) | sí | sí | sí | sí | `verifactu.add_record` |
| Enviar, procesar y reintentar la cola, consultar a la AEAT, probar la conexión | sí | sí | sí | no | `verifactu.transmit_record` |
| Subsanar y anular registros | sí | sí | no | no | `verifactu.correct_record` |
| Subir y quitar el certificado propio, pasar a producción y volver, recuperar la cadena, factura de prueba | sí | sí | no | no | `verifactu.configure` |

Los papeles llegan del SaaS con prefijo (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`). Guardar lo
que manda la cuenta (`verifactu.sync_config`) no es de ningún papel: solo del sistema.

## Para quien lo mantiene

### Anatomía

`apps.py`, `models.py` (`Config`, `OwnCertificate`, `Chain`, `SendControl`, `Record`, `Event`, `AeatRecord`),
`migrations/`,
`schemas/`, `services/`, `queries/`, `api.py`, `live.py`, `events.py`, `admin.py`, `locale/`,
`frontend/` y, puros y sin ORM: `chain.py` (formatos, huella, QR), `envelope.py` (el XML: `RegistroAlta`,
`RegistroAnulacion`, el sobre y la consulta), `xsd.py` (validación con los esquemas de `xsd/`), `aeat.py`
(lectura de las respuestas de la AEAT y de la consulta), `gateway.py` (cliente de la pasarela del SaaS),
`certificates.py` (abre e inspecciona el certificado propio y lo cifra y descifra; la fila la leen y escriben
`queries/` y `services/`) y
`producer.py` (los datos del productor que declara la declaración responsable). Un `tests/test_<fichero>.py`
por fichero, más `test_xsd.py` contra los esquemas reales, `test_integration_invoice.py` (Facturación real,
sin dobles), `test_concurrency.py` (sesiones reales en hilos; también una emisión cuyo cerrojo de cadena no
llega a tiempo y queda «pendiente») y `test_notifications.py` (escribir en el hub B no avisa al A).

### El Inicio (los «hooks» de `LiveAppConfig`)

`setup` y `widgets` en `apps.py` (sin `bell`). **Paso** `verifactu.sending_route`
(«Set up VeriFactu» / «Configura VeriFactu», `required=True` → «Importante» en pruebas, gh:hub#1726; ⛔ «Necesario
para facturar» donde `environment` de su fila es `production`, por `LEGAL_IN_PRODUCTION` de `base/home.py`: el nivel
es de `base`), sobre `verifactu.config.get` con `route_ready_for_production` (`not _route_sending_problem(config,
production, scope)` sobre la vía que tendría en producción, `queries.route.sending_route`: certificado propio vigente que
este servidor abre o, sin él, la vía ERPlora abierta en el servidor (`erplora_route.closed`) con el otorgamiento
aprobado; ya en producción, la vía fijada, sin mirar el interruptor; la exención del hub de ERPlora incluida; lo que le
falte al servidor no cuenta, no es tarea del negocio),
descripción según la vía de ERPlora para el negocio que lee el Inicio (`erplora_route.step_description`, perezosa: la
misma `erplora_route.available` que da `erplora_route_available` a Configuración; con ella cerrada, solo el certificado),
permiso `verifactu.configure`, ruta `/verifactu/config`, `refresh_on` `verifactu.config.changed`, `countries`
`(SPAIN,)` (`apps.py`; hub#682: un negocio de otro país no lo ve, ni su muro en producción; uno sin país cuenta como
España por `base.business.country_or_market`, que también lee `queries.country.outside_spain`: una sola regla). **Paneles** (permiso
`verifactu.view_record`, `refresh_on` = lo que `live.py` re-ejecuta): `pending` (kpi de
`verifactu.stats.compliance_summary.pending_count`, de serie), `contingency` (stat de `contingency_summary`,
`queued_count` y `severity`), `by_status` (bar-list de `records_by_status`) y `events` (componente
`RecentEventsPanel.vue`, que sigue `verifactu.stats.events_recent` con `limit` 8 y nombra el tipo con el catálogo de la
app: gh:verifactu#139). Tests: `test_apps.py` (declaración, textos `en` + `es`, iconos, eventos),
`test_integration_home.py` (por `base.setup.status` y `base.widget.list` reales, con dos hubs),
`test_queries.py` (`route_ready_for_production`), `RecentEventsPanel.test.ts` y la e2e
`tests/e2e/fix-verifactu-setup-hooks.spec.ts`.

### El asistente: lo que dice la persona para cada herramienta (hub#1089)

Las 30 herramientas dicen sus `asks`, las frases en `en` y `es` con que una persona las pide (`live.E020`: VeriFactu
está en `LIVE_ASSISTANT_ASKS_REQUIRED` y `base/tests/test_assistant_asks.py` exige que cada frase traiga su herramienta
entre las diez primeras, por rol). Sin ellos, «los cinco acontecimientos fiscales más recientes», «valida la cadena»,
«adelanta el registro de la cola» o «sella el registro de la factura de prueba» no traían su herramienta entre las que
ve el modelo (VERIFACTU-F13, F22, F26, F31): contestaba que no tenía herramienta, mandaba a la pantalla de
Recuperación o creaba otra factura de prueba. Hablan de «Hacienda», «AEAT», «huella», «cadena», «cola» y
«contingencia», y nombran un registro por su número («el registro 12») o por su factura. Nunca dicen «presenta» (la
raíz de la presencia de Control horario), «pregunta» (las preguntas de Automatizaciones), «este mes», «factura» en la
de prueba (empuja las sondas de numeración de Facturación), ni en inglés «record» (la raíz de «recordatorio», de
WhatsApp) o «waiting» (la de «waiter»). Hasta ERPlora/live#71 el asistente leía además «sella» como una venta,
«producción» como un producto y «comprueba» como una compra; ya las lee como lo que son.
`tests/test_assistant_asks.py` mide con las frases reales de la QA de la capa 2
(`tests/e2e/qa/probes/*-es-verifactu-*.json`), nunca con los propios asks, y con una frase propia por herramienta que
solo la trae con sus asks; el empleado no recibe las escrituras que no puede hacer, y ningún test sale de la máquina
(ni la AEAT de pruebas ni la de producción). Hasta ERPlora/live#76, la sonda de pasar a producción («activa el envío
real… comprobando antes que la cuenta y la autorización estén listas») se ofrecía la 34.ª de 40: «la cuenta» (la de
ERPlora) se leía como la cuenta de una mesa y pasaban delante las escrituras de Ventas que la toman. Lo que se nombra de
pasada, en la parte de la frase que abre con un gerundio («comprobando…»), ya no cuenta como lo que «activa» enciende, y
la sonda trae la herramienta la 8.ª.

La tarjeta de confirmación de una escritura (BASE-F97) dice qué registro toca por el número de su factura, como la
lista de registros y la ficha: reintentar, reenviar, preguntar a la AEAT, subsanar o anular el registro de una factura
sale «Registro: TICKET-2026-000012», nunca su id. Sellar una factura por su id la dice por su número, como Facturación
(«Factura: TICKET-2026-000012»). Lo lee `verifactu.record.get` (o `invoice.invoice.get`) como la persona que pregunta,
en una transacción de solo lectura: quien no puede ver los registros o las facturas, un id que no existe o el de otro
negocio, y una automatización sin nadie detrás, no ven esa línea. La marca de cada dato está en `card_names.py`
(`base.E009` la comprueba al arrancar). Test: `test_card_names.py`.

### La cadena, la huella y el QR

- **Huella** (`chain.py`): SHA-256 en hexadecimal **mayúsculas** de
  `IDEmisorFactura={nif}&NumSerieFactura={número}&FechaExpedicionFactura={DD-MM-AAAA}&TipoFactura={tipo}&CuotaTotal={cuota}&ImporteTotal={total}&Huella={anterior}&FechaHoraHusoGenRegistro={ISO con huso}`
  para el alta, y
  `IDEmisorFacturaAnulada=…&NumSerieFacturaAnulada=…&FechaExpedicionFacturaAnulada=…&Huella=…&FechaHoraHusoGenRegistro=…`
  para la anulación. Importes en euros con dos decimales y punto (los céntimos se dividen en el límite), fecha
  `DD-MM-AAAA`, marca de tiempo con segundos enteros y huso (`2026-09-22T19:58:55+02:00`), a la hora del negocio en
  su zona horaria (`base.business.business_zone`; Canarias, `+00:00` o `+01:00`), la misma que fecha la factura: al
  este de Madrid, un registro emitido pasada su medianoche se genera el día en que se expide, no la víspera. Un
  registro sellado nunca cambia la suya, así que la huella de los ya sellados cuadra igual. Vectores: los tres
  casos oficiales de la AEAT (un alta, la siguiente y una anulación encadenadas) y
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
  congela **al sellar** (el `SistemaInformatico` no espera a nada de la cuenta); uno guardado sin XML lo construye
  su primer envío. Si aun así un sobre no pasa al enviarse, la
  cadena espera con `xml_invalid` y el evento crítico se anota **una vez**, no en cada pasada. La consulta
  (`ConsultaFactuSistemaFacturacion`) se valida contra `xsd/ConsultaLR.xsd` antes de salir.
  Procedencia de los esquemas: `SuministroLR.xsd` y `SuministroInformacion.xsd` del motor actual (los últimos
  de la AEAT, con E7/E8 y la clave 21), `ConsultaLR.xsd` de la sede de la AEAT (2026-10-15) y
  `xmldsig-core-schema.xsd` de la W3C; SHA-256 en `tests/test_xsd.py`.
- **SistemaInformatico** (`producer.py`): `NombreRazon` ERPLORA CLOUD SL, `NIF` B27593136,
  `NombreSistemaInformatico` ERPlora Hub, `IdSistemaInformatico` EC, `TipoUsoPosibleSoloVerifactu` S y
  `TipoUsoPosibleMultiOT` S, los de la declaración responsable v1 firmada (`saas/public/declaracion/v1` de `ERPlora/saas`);
  `Version` = `APP_VERSION` (el commit de la imagen; `dev` en local), `NumeroInstalacion` = el identificador
  del negocio (la clave de su ámbito, el `slug` del hub) e `IndicadorMultiplesOT` **S siempre** (`MULTIPLE_OT`):
  ERPlora es una plataforma para muchos negocios, un sistema multi-obligado por definición, así que no depende de
  la cuenta.

### Contrato con Facturación (lo que `invoice` tiene que hacer)

1. **Dentro de la transacción de cada emisión** (`_issue` de `apps/invoice/services/__init__.py`, hecho), tras escribir el
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
     `verifactu.production_closed`): igual, nada se emite (working-rules §15). Venta (`sale`) no lo deja
     pendiente: rechaza el cobro, la devolución o la anulación con ese 409; reconoce los códigos de la ruta por su
     nombre, como nombra las operaciones de Facturación, aunque VeriFactu no está en sus `requires`. La reacción del
     sistema a un documento ya emitido no se rechaza: su registro se sella y espera.
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
    temporal privado del SaaS que se borra en cuanto TLS los ha leído. `hub` nombra al negocio
    (`queries.route.presenter`, el mismo para el envío, la consulta y la prueba de conexión): siempre el slug de su host
    (`ctx.scope.key`), sea cual sea el NIF del registro. El hub de ERPlora (`PLATFORM_HUB_SLUG`) solo guarda y
    presenta los registros de ERPlora (emisor `PLATFORM_ISSUER_TAX_ID`). En `hub` la pasarela acepta un UUID o
    un slug válido de `live.slugs` (saas#25). Solo pide el otorgamiento aprobado en producción
    (`fiscal_gateway/internal.py`, `_identity`; saas#210): por la vía por defecto, un negocio nuevo llega a la AEAT
    de pruebas desde su primer tique, y el Anexo I es lo que abre el paso a producción (VERIFACTU-F08). En pruebas
    rechaza igual a un negocio que declara el NIF de ERPlora (409 `nif_mismatch`).
  - Lo que no es `200`: `404 {"error": {"code": "hub_unknown"}}` (el `hub` del cuerpo no es ningún hub del SaaS;
    saas#29; cualquier otro 404 es una puerta que aún no está y se reintenta); `409 {"error": {"code",
    "message"}}` con `nif_mismatch` (el sobre nombra a otro contribuyente; se decide antes de tocar la AEAT),
    `representation_not_approved`, `no_seal`, `no_certificate`, `certificate_invalid` o
    `environment_not_allowed`; `413 payload_too_large` (más de 10 MiB); `422 invalid_payload` (con `fields`):
    el Hub los toma como **rechazo** (`refused`, con su código y mensaje a la vista en el registro y en la prueba
    de conexión; `hub_unknown` y `representation_not_approved` con texto propio en/es en vez del mensaje del SaaS): sigue
    `pending` y no se reintenta solo, porque se rechazaría igual (lo sellado detrás espera con el mismo motivo, y la
    cola no le pone «próximo intento»); vuelve a la cola al subir o quitar el
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
- **La foto** (`PUT /internal/hubs/{id}/state`, contrato con el SaaS): `{"hub_id",
  "slug", "version", "status": "active"|"past_due"|"suspended", …, "verifactu": {"representation": {"status":
  "none"|"submitted"|"approved"|"returned"|"revoked", "updated_at": ISO|null, "reason"}}}`. `live_paid` no es
  del contrato: si llega, se acepta y no se lee, y su columna (`Config.live_paid`) no se lee ni se escribe (su
  contracción, en «Qué queda fuera»).
  La recibe `base/internal.py`: firma HMAC v1 o v2 (la v2, si viene, decide sola),
  ±300 s, `INTERNAL_SHARED_SECRET` y, en una rotación, `INTERNAL_SHARED_SECRET_PREVIOUS`; sin firma, `401
  internal.unsigned`. Nombra su hub por `slug` (`422 internal.slug_invalid`); un `hub_id` distinto del de la ruta,
  `422 internal.hub_mismatch`; fuera de contrato, `422 internal.payload_invalid`. Aplica el bloque `verifactu` y el
  `status` con `verifactu.config.sync` (solo el sistema) en ese hub y contesta `200 {"applied", "version"}`; sin
  ninguno de los dos, `200 {"applied": false}`. Una `version` menor o igual que la guardada se ignora. «Validado»
  = `representation.status == "approved"`, en todos los planes. `own_certificate` y `multiple_taxpayers` no viajan (`null` = sin cambio): el
  certificado propio se sube en el Hub. La ruta de la foto le dice al Hub su id en
  ERPlora (`Config.hub_id`, sin variable de entorno `HUB_ID`): adonde se envía el otorgamiento. Cada cambio de
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
  esperan con `own_certificate_unreadable` sin llamar a la pasarela. Al subirlo se rechaza el autofirmado (emisor
  igual al sujeto); el emisor no se compara con ninguna lista de autoridades: si la AEAT lo admite lo dice la AEAT de
  pruebas (`aeat.certificate_verdict`, `aeat_proof`). Las columnas `issuer_recognised` y `checked_list` de la tabla ya
  no se usan: la migración `0008` las quitó solo del estado, porque el código anterior aún las lee durante el
  despliegue, y las filas nuevas las dejan vacías.
- **Producción**: además de lo de VERIFACTU-F08, el despliegue tiene que ser `prod` (`ERPLORA_ENVIRONMENT`; en
  `pre` nunca) y el servidor tener `VERIFACTU_PRODUCTION_ENABLED` a verdadero. Cerrado de nuevo, ningún registro de
  producción sale (esperan con `production_closed`, sin llamar a la pasarela) y no se emite nada nuevo en producción
  (`queries.route.route_problem`: primero lo que le falta a la vía, después lo del servidor, pasarela y apertura). Los workers solo trabajan contra la AEAT de pruebas; abrir la remisión real y los certificados
  queda bajo la supervisión de Ioan (working-rules §15).
- **Hub de plataforma de ERPlora** (PLAN-SAAS §4; Facturación, INVOICE-F23): el hub `PLATFORM_HUB_SLUG` emite las
  facturas de ERPlora a sus clientes. Sus registros van al entorno de la AEAT del despliegue, diga lo que diga su
  configuración (`queries.route.effective_environment`: `prod` con la remisión real abierta → producción; si no, pruebas;
  ya en producción, sigue en producción con el servidor cerrado y sus registros esperan, para que sus facturas reales
  no pasen nunca a la cadena de pruebas; lo usan `record.create` y la factura de prueba); su interruptor está fijo (`go_live` y `back_to_testing` → 409 `verifactu.platform_fixed`) y
  `manage.py create_platform_hub` alinea su configuración con `verifactu.config.follow_deployment` (409
  `verifactu.platform_only` en cualquier otro negocio). El sello de ERPlora presenta sus propios registros sin
  otorgamiento (`queries.route.route_problem`: el hub de plataforma **y** el emisor de Facturación `PLATFORM_ISSUER_TAX_ID`):
  ERPlora no se representa a sí misma. Un negocio cualquiera que teclee ese NIF como emisor sigue necesitando su
  otorgamiento aprobado (saas#2524): sin él, en producción no se emite nada nuevo; la pasarela del SaaS lo rechaza
  igual (`fiscal_gateway`, 409).
- **Hub de demostración** (PLAN-SAAS §3.5; `base.Hub.is_demo`, que lee `base.operations.is_demo_hub`): nunca pasa a
  producción (`go_live` → 409 `verifactu.go_live_forbidden`) y todo lo que sella va a la AEAT de pruebas
  (`queries.route.effective_environment`), diga lo que diga su configuración.

### La cola y el envío

- La cola **son los registros** (`pending`, `sent`, `accepted`, `accepted_with_errors`, `rejected`): sin tabla
  aparte. Espera por la ruta solo cuando no puede presentar (`queries.route.route_problem`: certificado propio que falta
  o caducó, otorgamiento sin aprobar en producción, o el servidor sin pasarela o cerrado). `SendControl` (una fila por `(NIF, entorno)`) guarda `next_send_at` (`TiempoEsperaEnvio` de la última
  respuesta) y es el cerrojo del envío: la pasada la toma con `select_for_update(skip_locked=True)`, así que dos
  pasadas nunca mandan la misma cadena y el sellado (que bloquea `Chain`) no espera a la red.
- **La llamada a la pasarela espera dentro de la transacción** de la operación, porque sus cerrojos son los que impiden
  que dos pasadas manden la misma cadena. Esa espera puede pasar de los 30 s en los que el clúster corta una transacción
  ociosa (`idle_in_transaction_session_timeout`; la pasarela puede tardar 45 s en leer), así que cada llamada (`submit`,
  `query` y `probe`) amplía antes el corte para su transacción, y solo para ella (`SET LOCAL`,
  `base.operations.allow_idle_wait`, `gateway.LONGEST_WAIT_SECONDS`): una respuesta lenta de la AEAT se guarda y no gasta
  un intento ni se reenvía con incidencia (hub#623).
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
  corre el worker (`base/scheduler.py`, desde `base/worker.py`, cada tick de 5 s) como el sistema, en cada negocio
  que sirve, en su BD y con su ámbito (`base.hub_visits`: `use_hub` y `Scope("host", slug)`): su reloj es una
  fila de `base.TaskSchedule` en esa BD, que el worker escribe la primera vez que lo sirve desde que arrancó; cada
  pasada la toma con
  `select_for_update(skip_locked=True)` y mueve `next_run` en la misma transacción que el envío, así que dos
  workers a la vez (un despliegue) nunca la corren dos veces, y los minutos perdidos con el worker parado se
  juntan en una sola pasada. Si la pasada falla, se registra en el log, se deshace lo suyo y vuelve al minuto
  siguiente. La pasada de un negocio ve solo sus registros y los presenta con su slug. También se sirve a un negocio
  que se fue y conserva su BD (`base.services.provisioning.hubs_to_serve`), porque lo que le queda por enviar tiene que llegar a
  la AEAT. La pasada del hub de ERPlora (`PLATFORM_HUB_SLUG`) solo ve los registros de ERPlora y los presenta como
  `erplora` (`queries.route.presenter`, hub#1130).
- La consulta a la AEAT (VERIFACTU-F27 y F28) sigue todas sus páginas.
- Los importes agrupan los millares desde cuatro cifras (hub#1090): «1.234,56 €» en español en la lista y la ficha
  de un registro y en la lista del admin. El XML y la huella de la AEAT llevan el importe sin millares, como pide su
  esquema.

### Administrador de Django

Solo para el staff de la plataforma (`hubs.erplora.com/admin`, con el hub elegido en `/admin/hub/<slug>/`), **al
servicio del soporte**. El criterio: «un registro no enviado no es un registro registrado; no se
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
    rechazados, N siguen esperando.» (cada recuento con el suyo: con uno, «1 aceptado», «1 rechazado», «1 sigue
    esperando»; hub#1304).
  - **«Reprogramar: enviar en la próxima pasada»** → `verifactu.contingency.retry` (VERIFACTU-F22): el registro y
    los anteriores de su cadena salen en la pasada siguiente (la tarea de cada minuto), sin perder sus intentos.
    «Reprogramado: N registros salen en la próxima pasada.» (con uno, «1 registro sale»; cada aviso con un número
    lo dice en singular o en plural, nunca con «(s)», hub#1275).
  - **«Consultar a la AEAT (sale de la cola si ya lo tiene)»** → `verifactu.record.reconcile` (VERIFACTU-F35): si
    la AEAT tiene ese mismo registro (misma huella), sale de la cola como registrado; si no, sigue en la cola.
    «Consulta a la AEAT: N ya registrados (fuera de la cola), N no están en la AEAT (siguen en la cola).» (con
    uno, «1 ya registrado», «1 no está en la AEAT (sigue en la cola)»).
  - **«Subsanar el rechazo con un registro nuevo»** → `verifactu.record.correct` (VERIFACTU-F24), solo sobre un
    registro rechazado: el rechazado se queda tal cual y entra uno nuevo en la cola. «Subsanado: N registros
    nuevos en la cola.» (con uno, «1 registro nuevo»).
  - **Retirar de la cola** es solo lo que la AEAT ya tiene, y se hace consultándola (la acción de arriba). Nada
    sale de la cola sin que la AEAT lo tenga (VERIFACTU-F35); un rechazo definitivo se resuelve con la subsanación
    (VERIFACTU-F24), que deja el rechazado como estaba.
- **Control de envío por `(NIF, entorno)`**: en solo lectura; su acción **«Reprogramar su cola: enviar en la
  próxima pasada»** llama a `verifactu.contingency.retry` sobre el registro más reciente que espera en esa cadena.
  `next_send_at` es el `TiempoEsperaEnvio` de la AEAT y **nunca se acorta** (las preguntas frecuentes de la AEAT, en «Referencia adoptada»):
  reprogramar hace que salga en cuanto la AEAT lo permita. El `wait_reason` de un registro tampoco se borra al
  reprogramar: es lo que lo declara fuera de plazo (`Incidencia` S); lo reescribe la pasada siguiente. La excepción
  es un rechazo de la pasarela (`refused`, con su código y su mensaje en el detalle), que no sale nunca por tiempo:
  reprogramarlo lo devuelve a la cola sin motivo, y sus intentos lo siguen declarando fuera de plazo.
- **Configuración**: se ve entera y no se teclea nada. La vía no se elige (VERIFACTU-F04: la fija `go_live`), el
  entorno va por «Pasar a producción» / «Volver a pruebas», lo que manda la foto del SaaS (`representation_*`,
  `hub_status`, `hub_id`, `synced_version`) llega de la cuenta y el certificado se sube en el módulo. La columna
  `live_paid`, sin uso, no se enseña.
- **Registros**: las columnas secuencia, factura, fecha, tipo, emisor, total, estado, entorno y CSV de la AEAT; filtros por estado, motivo de
  espera (solo los que tiene algún registro, en el idioma del lector), tipo de registro, tipo de factura y entorno;
  jerarquía por fecha de expedición; búsqueda por número, NIF, nombre del emisor, huella y CSV. La ficha agrupa
  todos los campos en Factura (con enlace a la factura en su admin), Cadena de huellas, Respuesta de la AEAT
  (estado, **por qué aún no está en la AEAT** en frase, intentos, `wait_reason`, detalle, respuesta y código de la
  AEAT), XML y Metadatos.

### Contradicciones señaladas

- **Declaración responsable**: la v1 firmada no nombra una pasarela en Python dentro del SaaS (la v2, sin
  firmar, nombra el `verifactu-gateway` en Rust); el cambio de composición necesita una versión nueva firmada. Es un
  trámite legal, fuera del código (PLAN-HUB §8, «Bloque fiscal: lo que queda fuera»).
- **«Fijo tras el primer envío» frente a «tras el primer sellado»** (PLAN-HUB §4): PLAN §30 deja el interruptor en
  vivo fijo cuando se **envía** la primera factura a la AEAT; `verifactu.config.back_to_testing` se niega (409
  `verifactu.production_has_records`) en cuanto hay un registro **sellado** en producción (VERIFACTU-F09, Decisión
  9), más estricto que la regla.

### Decisiones

1. **Hay botón de enviar ya** en la ficha: Odoo, Holded y Sage lo ofrecen.
2. **Ante un rechazo, la ficha dice qué hacer** y ofrece «Subsanar»: datos de la factura → rectificativa en
   Facturación; lo demás → subsanación.
3. **El registro de anulación tiene pantalla**: «Anular registro» en la ficha, con motivo y confirmación, solo el
   administrador.
4. **Se avisa de la caducidad del certificado propio** a 30 días.
5. **Pruebas y producción se separan** en la lista con la columna y el filtro «Entorno».
6. **No hay «Activar VeriFactu»**: encender la app es activarla; una app encendida registra siempre.
7. **No hay cese en el Hub**: el cese ante Hacienda es la baja censal del negocio (modelo 036/037), fuera de
   ERPlora, y el software no envía nada.
8. **La prueba de conexión nunca presenta un registro**, tampoco con certificado propio.
9. **Volver a pruebas se cierra con el primer registro de producción**, sea una venta o una rectificativa.
10. **La anulación de una venta es una rectificativa R5**, registrada como alta (Facturación, decisión 3): un
    registro de anulación además la contaría dos veces ante la AEAT.
11. **Sin reenganche automático** ante un rechazo de cadena: se recupera la cadena (F28) y se subsana (F24); mover
    la cadena sin una persona es peor que el rechazo.
12. **Una factura completa sin NIF de cliente se niega**, no se degrada a F2 (Facturación ya lo exige; degradarla
    declararía un tipo distinto del impreso).
13. **Un SOAP Fault no rechaza registros**: es un rechazo del envío; los registros
    esperan con `aeat_fault` y el intento gastado. Ninguna norma pide marcarlos rechazados: la Orden
    HAC/1177/2024 pide remitir los registros, y uno que la AEAT no evaluó no existe para ella. Lo único en contra
    es práctico: un Fault permanente se repite en cada intento (con la espera de 5 a 60 minutos) hasta que una
    persona arregla su causa; por eso queda como evento crítico.
14. **Un rechazo de VeriFactu deshace la emisión** (contrato con Facturación): reintentarlo fallaría igual;
    solo un error pasajero de la base de datos deja el documento «pendiente» para la reacción.
15. **VeriFactu solo vale en España**: el RD
    1007/2023 y la Orden HAC/1177/2024 obligan a quien tributa en España (Canarias, Ceuta y Melilla son regiones de
    ES). Un negocio con otro país en su cuenta (`base.Hub.country`, que lee `base.business.get`) se comporta como con
    la app apagada (`queries.country.outside_spain`, `refuse_outside_spain` → `AppInactive`): sus facturas salen
    «unavailable» (nunca un 409 que las deshaga), la reacción no sella, la cola no envía (`blockers` →
    `outside_spain`), la factura no pinta recibo (`by_invoice` vacío) y el veto de apagar no lo atrapa
    (`disable_refusal` → `None`). Sin país (una demo), es España. El hub propio de ERPlora lee su país como los demás,
    de `base.business.get`, que para él contesta el de su emisor (`PLATFORM_ISSUER_COUNTRY`, hub#329): VeriFactu no
    guarda otra fuente del mismo dato. Lo sellado antes en
    un negocio de fuera no se borra (los registros fiscales nunca se borran): se queda sin enviar, con su motivo. **Apps**
    no la ofrece encendible fuera de España: `can_enable(self, ctx) -> str | None` en `LiveAppConfig`, como
    `can_disable`, que respetan `base.app.enable`, `base.app.retry` y `base.app.list` (hub#694). Un fichero que la
    trae pasa por `base.app.enable`: VeriFactu se queda fuera, con su motivo, y lo demás carga (ninguna plantilla del
    catálogo la trae, decisión 17). Una ya encendida se queda como está y no hace nada.
16. **Una vez encendida, VeriFactu no se apaga en España**: `disable_refusal`
    contesta siempre `NEVER_OFF`, salvo fuera de España (decisión 15) o si nunca llegó a `on` (`creating` o `failed`: no ha
    sellado nada, y el negocio no se queda atado a una activación que falló); sin país (una demo), es España. La
    AEAT obliga a seguir con VERI*FACTU al menos hasta el fin del año natural (FAQ de su sede). El mercado se parte: la
    mayoría no lo apaga a mitad de año (Square: la baja se aplica a final de año; Sage 50: baja con fecha 31-12,
    «irreversible» tras la primera factura certificada; B2Brouter, el conector de Business Central: desde 2027 no se
    desactiva en un ejercicio con envíos) y otros lo dejan con aviso (Zoho Books: desaconsejado salvo migración).
    «Nunca» es más estricto que el año natural: ERPlora no tiene modo «NO VERI*FACTU», así que una baja diferida a
    fin de año dejaría al negocio sin registro de sus facturas: la regla es «nunca», sin baja programada. Solo
    `base.app.disable` apaga una app: bajar de plan no apaga nada (BASE-F24), la foto del SaaS no apaga apps, una
    demo caducada se borra entera y la baja de un negocio conserva su base de datos.
17. **Ninguna plantilla la enciende, tampoco en España** (hub#998): una app que ata al
    negocio con la AEAT hasta fin de año y no se apaga (decisión 16) la activa el dueño, de forma explícita, como en
    Square, Odoo, Holded o Sage 50. La app no lista ningún sector en `verticals` (`apps.py`), así que
    `base.catalog.template_apps` no la mete en las plantillas de restaurante ni de peluquería: ni «Revisa lo que trae»
    la anuncia ni la carga la activa. En erplora.com, `verticals` es también lo que la tienda pública usa para
    «Pensada para» y para las apps de cada sector (`public/industries.py` del SaaS), así que VeriFactu no sale en las
    páginas de restaurante ni de peluquería, como Pagos, que tampoco viene en ninguna plantilla.
18. **La vía de ERPlora se cierra con un interruptor del servidor, sin borrar nada**: de momento ERPlora no quiere
    asumir la presentación por cuenta de los negocios. `VERIFACTU_ERPLORA_ROUTE_ENABLED` (verdadero por
    defecto) y `erplora_route.py` frenan solo las entradas: pedir o subir el otorgamiento, pasar a producción por ella
    y el paso del Inicio (`erplora_route.closed`, que solo mira a quien aún no está en producción). El envío no lo
    mira: las pruebas, demos incluidas, siguen con el sello, y quien ya está en producción por ella sigue sellando,
    enviando y anulando, porque la AEAT solo acepta una anulación con el mismo sello. El hub de ERPlora queda fuera.
    `verifactu.config.get` lo expone en `erplora_route_available` para que la pantalla oculte la vía. Volver a abrirla
    es solo cambiar el ajuste.
19. **La vía se calcula, no se elige** (`erplora_route.route_for`, que lee `queries.route.sending_route`): en pruebas, con
    un certificado propio cargado y vigente, el certificado; sin él, el sello de ERPlora. `go_live` guarda en
    `Config.route` la de ese momento y, desde entonces, esa manda en producción para enviar, consultar, anular y probar
    la conexión, aunque el certificado se suba, se quite o caduque: lo presentado con un sello se anula con el mismo,
    y una vía propia sin certificado espera, no vuelve al sello. El hub de ERPlora remite siempre con el sello. No hay
    interruptor que elegir: lo que decide es tener o no el certificado.

### Qué queda fuera

Lo demás del bloque fiscal está en PLAN-HUB §8, «Bloque fiscal: lo que queda fuera».

- **Rotar `FISCAL_CERTIFICATE_KEY`**: un solo `Fernet`, sin `MultiFernet`; con la clave cambiada, el certificado
  guardado no se abre y los registros por la vía propia esperan con `own_certificate_unreadable` hasta que se vuelva
  a subir.
- **Avisar por correo de la caducidad del certificado propio**: hoy el aviso es solo en pantalla, a 30 días.
- **Subsanar y anular en producción sin ruta**: no se rechazan (no son cobros) y esperan en la cola.
- **Arrastrar y soltar los ficheros** (certificado y otorgamiento): falta el componente de subida en
  `@erplora/ui`; hoy, un botón y el nombre del fichero.
- **OSS**: la factura de plataforma no lleva el aviso «VAT included — customer VAT number could not be verified»
  cuando el NIF-IVA del cliente no se pudo verificar.
- **Contracción de `hub_unregistered` como espera** (hub#1130): ninguna pasada pone ya ese motivo, así que «Aún no
  está en la AEAT» no lo dice. El texto de su motivo en `WAIT_REASONS` («ERPlora todavía no ha vinculado este
  negocio con su cuenta en este servidor») se queda para leer el `Record.wait_reason` que guardaron pasadas
  anteriores: lo enseñan la cola (`last_error`) y el filtro del admin hasta que una pasada posterior lo
  envía o le pone otro motivo. Se retira cuando ninguna BD de negocio guarde un registro con `wait_reason =
  "hub_unregistered"`. El código `verifactu.hub_unregistered` del otorgamiento (sin `Config.hub_id` o con el 404 del
  SaaS, VERIFACTU-F08) sigue vivo.
- **Contracción de `live_paid`**: la columna `Config.live_paid` (migración `0003_live_paid`) sigue sin lectura ni
  escritura y `ConfigSyncIn` acepta e ignora el campo hasta que ningún SaaS desplegado lo mande (expand/contract,
  hub#205 y saas#108).

### Lo que NO hace, a propósito

- No emite, anula ni modifica facturas: eso es Facturación.
- No calcula impuestos: los importes llegan decididos.
- No guarda el sello de ERPlora (Secrets Manager, solo en el SaaS) ni enseña nunca el material del certificado
  propio: el `.p12` y su contraseña se guardan cifrados y solo salen hacia la pasarela.
- No borra ni edita un registro sellado.
- No presenta nada a la AEAT por su cuenta: lo hace la pasarela del SaaS.
- No lleva el registro de eventos de la modalidad NO VERI\*FACTU.
- No tramita el cese de actividad.

### Lo que la ventana de ayuda no enseña

La ayuda del Hub publica el primer apartado hasta su primer `###`, el resumen de cada pestaña (lo que va antes de su
primer `####`) y, de cada flujo hecho en una pestaña o en una de sus ventanas, su título, sus pasos y «Si falla», sin
nombres de código, incidencias ni ids de flujo (`tests/test_help_workbooks.py`). Por eso la ficha de un registro es una
ventana (`####`) de **Registros**: así VERIFACTU-F17, F24, F25, F30 y F35 se publican en esa pestaña. Lo que esas
partes dejaron de decir, y quien mantiene VeriFactu necesita:

- Los códigos de los rechazos que los flujos dicen por su frase:
  - al subir el certificado (VERIFACTU-F02), todos 409: `verifactu.certificate_storage_unavailable`,
    `verifactu.issuer_missing`, `verifactu.certificate_invalid` (contraseña o fichero, autofirmado, sin autenticación
    de cliente o caducado) y `verifactu.certificate_holder_mismatch`; quitarlo sin permiso de configurar es 403 (F03);
  - el otorgamiento (F05 y F06): la comprobación previa con los códigos del SaaS (422), el rechazo del SaaS con su
    código `fiscal.*` y sus campos tal cual, 409 `verifactu.issuer_missing`, 409 `verifactu.hub_unregistered` (sin
    `Config.hub_id` o un negocio que el SaaS no conoce), 503 `verifactu.saas_unreachable` y, con la vía de ERPlora
    cerrada en el servidor, 409 `verifactu.erplora_route_unavailable` en «Descargar el modelo» y en «Enviar a
    revisión», salvo en el negocio de la propia ERPlora. Guardar el modelo dentro de la app es BASE-F112;
  - pasar a producción (F08) se comprueba en este orden y la primera causa da el 409 con su código: el servidor
    cerrado (`verifactu.production_closed`; en la lista de Ajustes, `production_closed`) → un negocio de
    demostración (`verifactu.go_live_forbidden`; quién es demo lo dice la plataforma, `base.operations.is_demo_hub`)
    → el emisor (`verifactu.issuer_missing`) → la vía (con certificado válido, `verifactu.own_certificate_unreadable`,
    `verifactu.own_certificate_untested` o `verifactu.own_certificate_rejected`; sin él,
    `verifactu.representation_not_approved` o, con la vía de ERPlora cerrada, `verifactu.own_certificate_required`)
    → la cuenta (`verifactu.hub_not_active`); sin pasarela, `verifactu.gateway_unavailable`. Fuera de España, 404
    `app_inactive`. En producción sin la vía fijada, la venta o la factura se rechazan con 409 y el código de la ruta
    (`verifactu.representation_not_approved`, `verifactu.own_certificate_missing`), y Ajustes lo dice en
    `issue_blocker`.
- La vía de ERPlora la abre o la cierra `VERIFACTU_ERPLORA_ROUTE_ENABLED` (abierta por defecto; F04, F05 y F08).
- El certificado propio se guarda cifrado con Fernet y la clave `FISCAL_CERTIFICATE_KEY` (F02); la sede de la AEAT de
  pruebas contesta a un certificado que no reconoce redirigiendo a su página de error 401.
- El paso «Configura VeriFactu» del Inicio solo se da por hecho con el certificado propio cuando la AEAT de pruebas lo
  ha aceptado y, con la vía de ERPlora cerrada, solo habla de él: «Sube el certificado del negocio para enviar tus
  facturas a la AEAT.» (con la vía abierta, «Firma la autorización para que ERPlora envíe tus facturas a la AEAT, o
  sube el certificado del negocio.»).
- La pasada automática (F20) es la tarea programada `process_queue`, que corre la de VERIFACTU-F15; su evento es
  «Cola procesada: {enviados} enviados, {aceptados} aceptados, {rechazados} rechazados, {en espera} en espera.». Cada
  registro se presenta como su negocio, nunca como el hub de ERPlora (hub#454).
- El total del filtro de Registros se lee como cualquier importe del Hub (hub#1247, F16).
- La subsanación (F24) lleva `RechazoPrevio` según la Descripción del servicio web VERI\*FACTU v1.0.3: `X` si la AEAT
  no tiene ningún registro de esa factura (se rechazó el alta inicial; §9.1.3, «alta por rechazo»); `S` si la AEAT sí
  la tiene y lo rechazado fue una subsanación posterior. Un «Aceptado con errores» se subsana con `Subsanacion = S` y
  `RechazoPrevio = N` (§9.1.2). Volver a anular tras una anulación rechazada lleva `RechazoPrevio = S` (§9.2.2, F30).
- Los mensajes con hueco (`{titular}`, `{NIF}`, `{fecha}`, `{número}`, `{hora}`, `{total}`, `{seq}`, `{n}`,
  `{ruta}`) la ayuda los enseña con un ejemplo o sin el hueco. La factura de prueba (F11) se pide a Facturación por la
  misma puerta que el alta manual (INVOICE-F03).
