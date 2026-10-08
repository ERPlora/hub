# WORKFLOW — Hub · pantallas · Ajustes del negocio y datos

Prefijo: HUB_SHELL

> Detalle del área «Ajustes del negocio y datos»: la pantalla Ajustes y sus pestañas (General,
> Negocio, Impresión, Permisos, Datos y copias), la ventana «Permisos de tus apps» y el bloque «Tu
> número» de la Bandeja de WhatsApp. En Ajustes › General, las tarjetas «Este dispositivo» (área de
> acceso, HUB_SHELL-F11), «Pinpad» y «Dispositivos» (área de personas, HUB_SHELL-F99…F104) no son de
> este fichero; en Ajustes › Impresión, la tarjeta «Estado de impresión» la cuenta el
> fichero de avisos e impresión (HUB_SHELL-F75; aquí F166 quedó retirado). Código: `views/SettingsPage.vue`,
> `components/WhatsAppConnect.vue`, `DataPanel.vue`, `ExportPanel.vue`, `ImportPanel.vue`,
> `ImportPermissionsConsent.vue`, `ResetPanel.vue` y `lib/settings-tabs.ts`, `hub-settings.ts`,
> `timezone.ts`, `import-retry.ts`, `import-permissions.ts`, `app-names.ts`, `whatsapp-connect.ts`,
> `autostart.ts` (el interruptor; el arranque en sí es de `HUB_APP`).

## Referencia adoptada

- **Ajustes**: Odoo (Ajustes › Empresa: razón social, NIF, dirección, moneda, idioma, zona), Square
  (Cuenta y configuración › Información del negocio), Shopify (Configuración › General) y Business
  Central (Información de la empresa).
- **Datos**: la exportación e importación de «plantillas de configuración» de Odoo (módulos de datos)
  y Shopify (exportar/importar CSV), más el «restablecer» tipo GitHub (teclear el nombre).
- **«Tu número»**: Embedded Signup de Meta con coexistencia (especificación oficial de Meta).

## Antes de empezar

- Para tocar Ajustes, Permisos o Datos hace falta ser dueño o administrador; el resto de perfiles lee
  Ajustes en solo lectura.
- Para el bloque «Tu número»: la app de la Bandeja de WhatsApp instalada y WhatsApp configurado en la
  plataforma.
- Para exportar o importar: la lista de apps instaladas ya cargada; para importar una plantilla,
  conexión con erplora.com.

## Flujos

### HUB_SHELL-F155 Abrir Ajustes y moverse por sus pestañas
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ajustes
Pasos:
1. Pulsa **Ajustes** en el menú lateral (sección «Cuenta»), o llega desde un enlace de otra pantalla (la lista de puesta en marcha de Inicio, la campana o el botón de configurar de una app).
2. Abajo hay cinco pestañas: **General**, **Negocio**, **Impresión**, **Permisos** y **Datos y copias**. Se abre **General**. La pestaña elegida queda en la dirección (`#hub`, `#business`, `#tickets`, `#permissions`, `#data`), así que Atrás y un enlace guardado vuelven a ella. En el móvil las cinco no caben: la barra se desliza de lado, y la pestaña que se toca (o la que abre un enlace) se trae a la vista entera y fuera del difuminado que avisa de que hay más pestañas por ese lado; si es la última, la barra llega hasta su final, donde ya no hay difuminado (hub#2617, como la barra de una app, HUB_SHELL-F42).
3. Las direcciones antiguas siguen llevando a su sitio: `#tax` abre **Negocio** (lo llevan versiones de VeriFactu ya publicadas; la actual lleva a su propia Configuración), `#store` y cualquier pestaña desconocida abren **General**, y las antiguas páginas `/export` e `/import` abren **Datos y copias**. `?data=export` abre **Datos y copias** ya en Exportar.
4. Quien no es dueño ni administrador ve todo en solo lectura: los desplegables se sustituyen por el valor, los campos no se pueden editar, los interruptores no se pueden pulsar y muestran su valor, y el botón «Guardar cambios» no existe.
5. **General** también trae tres tarjetas que son de otras áreas: «Este dispositivo» (HUB_SHELL-F11), «Pinpad» y «Dispositivos» (HUB_SHELL-F99 a F104).
6. Cada cambio de **General** se guarda al instante («Ajustes guardados»); **Negocio** se guarda con su botón.
7. Mientras llegan los ajustes, **General** y **Negocio** enseñan lo que ya se leyó antes en la sesión o, si no hay nada, el indicador de carga («Cargando los ajustes del negocio…»).
Entra: los ajustes del negocio que da el hub (HUB-F220); se leen al arrancar y otra vez al abrir la pantalla.
Sale: nada guardado.
Si falla: si la lectura al abrir falla, **General** y **Negocio** dicen «No se pudieron cargar los ajustes del negocio» («Tus ajustes guardados siguen igual. Comprueba la conexión y vuelve a intentarlo.») con «Reintentar», en lugar de lo que sale de esa lectura: en General, País, Zona horaria, Moneda, Idioma del negocio, Paleta, «Mostrar documentación de la API» y la tarjeta «Pinpad»; en Negocio, el formulario entero con «Guardar cambios». No se pinta ningún valor por defecto ni lo leído antes en la sesión, y no hay nada que guardar encima. «Este dispositivo», «Dispositivos», la fila de hardware y las pestañas Impresión, Permisos y Datos y copias no dependen de esa lectura y siguen. «Reintentar» vuelve a leer (el botón se apaga mientras tanto) y, si contesta, sale todo con lo guardado (hub#2541). Lo que depende de los nombres y direcciones de las pestañas está listado en el índice (los módulos enlazan a `#hub` y, en versiones publicadas, a `#tax`).
Implicados: HUB-F220, VERIFACTU-F01, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F156 Cambiar el país del negocio
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General** abre el desplegable **País** («País para la configuración regional»). Solo ofrece «España» y «Portugal».
2. Elige uno. Se guarda al instante y sale «Ajustes guardados».
3. Si la zona horaria está en «Automática», el hub la vuelve a deducir del país nuevo y el reloj del negocio cambia.
4. La lista de puesta en marcha de Inicio se vuelve a leer antes del aviso, porque el país decide qué pasos aplican.
Entra: el país elegido.
Sale: el país en los ajustes (HUB-F221); lo leen los impuestos y los módulos de cumplimiento de cada país.
En este mismo documento se apoya en: HUB_SHELL-F27 (Seguir la lista «Termina de configurar tu negocio»).
Si falla: el desplegable vuelve al valor anterior y sale el motivo si el hub lo dio: «El país ya no se puede cambiar: este negocio ya declara con sus normas fiscales. Escríbenos si el negocio se ha mudado de verdad.»; con otro motivo, «No se pudieron guardar los ajustes». Un perfil que no administra ve solo el código del país.
Implicados: HUB-F221, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F157 Elegir la zona horaria del negocio
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General** abre **Zona horaria** («Zona horaria para fechas y horarios»).
2. La primera opción es «Automática · {zona}, {hora}»: dice a qué zona resuelve el hub ahora. Debajo van las zonas del país (España: Europe/Madrid y Atlantic/Canary; Portugal: Europe/Lisbon, Atlantic/Azores y Atlantic/Madeira), cada una con su hora ahora («Europe/Madrid · 23:30»). Esa hora avanza sola cada 30 segundos mientras la pantalla está abierta: es la prueba que se compara con el reloj de la pared. Una zona ya declarada que no sea de esas se mantiene en la lista.
3. Elige una: se guarda al instante («Ajustes guardados»). Elegir «Automática» devuelve el hub a deducirla del país.
4. El hub vuelve a decir cuál es la zona en vigor y la entrega a las apps, para que las horas de citas, cierres y automatizaciones sean las de la pared.
Entra: la zona elegida (o «automática»).
Sale: la zona declarada en los ajustes (vacía = deducida del país) y la zona en vigor republicada (HUB-F221, SCHEDULES-F09). El manual dice que la zona se edita sin más: lo que el hub hace es deducirla del país salvo que se declare, y por eso un negocio en Canarias con país España tiene que declararla.
Si falla: el desplegable vuelve a lo que había, sale el motivo o «No se pudieron guardar los ajustes», y no se republica nada. Quien no administra ve la zona en vigor con su hora.
Implicados: FLOWS-F13, HUB-F221, SCHEDULES-F09, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F158 Cambiar la moneda del negocio
Estado: parcial — los nombres de las monedas («US Dollar», «Pound Sterling», «Swedish Krona»…) están escritos en inglés en el código, fuera de i18n: quien usa el producto en español los lee en inglés
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General**, **Moneda** («Moneda de tu negocio para precios y totales») ofrece diez: EUR, USD, GBP, CHF, SEK, NOK, DKK, PLN, MXN y BRL, escritas «EUR · Euro».
2. Elige una: se guarda al instante («Ajustes guardados») y todos los importes de la pantalla y de las apps se vuelven a escribir con ella, sin recargar.
Entra: el código de moneda.
Sale: la moneda en los ajustes (HUB-F221); la leen todos los importes. La pantalla ofrece diez; el hub acepta cualquier código de moneda reconocido.
Si falla: la moneda vuelve a la anterior (también en las apps) y sale el motivo o «No se pudieron guardar los ajustes».
Implicados: HUB-F221, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F159 Elegir el idioma del negocio
Estado: parcial — el idioma de la pantalla cambia antes de saber si el guardado ha salido: si el hub lo rechaza, el desplegable vuelve atrás pero el idioma sigue cambiado hasta recargar (leído, sin ejecutar)
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General**, **Idioma del negocio** («Idioma por defecto para quien no haya elegido el suyo») lista los idiomas que trae el producto por su nombre.
2. Elige uno: se guarda al instante («Ajustes guardados»).
3. Quien no haya elegido un idioma propio en su perfil ve ya la pantalla en el nuevo; quien lo eligió sigue en el suyo.
Entra: el idioma elegido.
Sale: el idioma por defecto en los ajustes (HUB-F221); es el de quien no ha elegido el suyo.
En este mismo documento se apoya en: HUB_SHELL-F21 (Cambiar mis datos, foto, idioma y apariencia).
Si falla: el desplegable vuelve al valor anterior y sale el motivo o «No se pudieron guardar los ajustes».
Implicados: HUB-F221, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F160 Elegir la paleta de colores del negocio
Estado: parcial — quien no administra lee el identificador interno de la paleta («erplora»), no un nombre
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General**, **Paleta por defecto** («La paleta que ven los usuarios que no han elegido una propia») muestra el selector de paletas (sin el modo claro/oscuro, que es de cada persona).
2. Elige una: se guarda al instante y el shell la aplica a quien no tenga una propia.
Entra: la paleta elegida.
Sale: la paleta por defecto en los ajustes (HUB-F221).
Si falla: la paleta vuelve a la anterior y sale el motivo. Quien no administra solo lee el nombre interno de la paleta, sin selector.
Implicados: HUB-F221
QA: ninguno

### HUB_SHELL-F161 Mostrar u ocultar la documentación de la API
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **General**, el interruptor **Mostrar documentación de la API** («Añade una página interna con la documentación de la API (Swagger) para integraciones»).
2. Al encenderlo se guarda al instante y aparece la entrada «API» en el menú lateral; al apagarlo desaparece, sin recargar.
Entra: el interruptor.
Sale: el ajuste de documentación de la API (HUB-F221); la seguridad real es la sesión que exige el hub para ver el documento.
En este mismo documento se apoya en: HUB_SHELL-F98 (Consultar la documentación de la API).
Si falla: sale el motivo; que el interruptor vuelva visualmente a su valor está sin confirmar (la vuelta atrás no cambia el valor enlazado). A quien no administra le sale desactivado.
Implicados: HUB-F221
QA: ninguno

### HUB_SHELL-F162 Ir del hardware de Ajustes al diagnóstico de Sistema
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ajustes › General
Pasos:
1. En **General**, bajo «Hardware», la fila **Acceso a recursos locales y de red** («Impresoras, escáneres y otros dispositivos de este equipo o de su red») dice «Disponible aquí» dentro de la app instalada y «Solo desde la app instalada» en un navegador.
2. Pulsarla abre **Sistema › Recursos**, donde está el estado de la impresora y el diagnóstico.
Entra: si la pantalla corre dentro de la app instalada.
Sale: nada guardado. «Disponible aquí» solo quiere decir que este equipo puede hablar con el hardware, no que haya una impresora.
Si falla: no falla; es navegación.
Implicados: HUB_APP-F10, HUB_APP-F18
QA: ninguno

### HUB_SHELL-F163 Arrancar ERPlora al iniciar sesión en el ordenador
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ajustes › General
Pasos:
1. Solo en la app de escritorio, **General** muestra el interruptor **Arrancar al iniciar sesión** («Abre ERPlora al iniciar sesión en este ordenador, para que los tiques siempre tengan dónde imprimirse»). En un navegador o en Android no existe.
2. Viene apagado. Al encenderlo, el sistema operativo lo recuerda y el interruptor muestra lo que el sistema contesta, no lo que se pidió.
Entra: el interruptor.
Sale: el arranque automático del sistema operativo, de este equipo, no del negocio.
Si falla: «No se pudo cambiar el ajuste de arranque al iniciar sesión»; que el interruptor vuelva visualmente a lo que el sistema dice está sin confirmar.
Implicados: HUB_APP-F27
QA: ninguno

### HUB_SHELL-F164 Guardar los datos del negocio y su identidad fiscal
Estado: parcial — la pantalla no comprueba el NIF ni nada antes de guardar (lo hace el hub y la pantalla traduce el motivo), y no hay nombre comercial, teléfono ni correo del negocio: solo razón social y domicilio fiscal
Actor: administrador
Pantalla: Ajustes › Negocio
Pasos:
1. Abre **Negocio**. La tarjeta **Datos del negocio** dice «Identidad del obligado tributario (la usan las facturas y las apps fiscales).».
2. Rellena **Identificador fiscal (NIF/CIF/VAT)** y **Razón social / nombre**.
3. Rellena el domicilio fiscal en partes: **Vía pública**, **Número**, **Código postal** y **Municipio**. La línea que imprimen las facturas y los tiques la compone el hub; no se escribe a mano. Un negocio con la dirección antigua en una sola línea la ve debajo («Dirección actual: {dirección}. Rellena los campos de arriba para sustituirla.») hasta que rellene las partes.
4. Decide la casilla **Usar estos datos también para mi factura de ERPlora** (viene sin marcar): marcada, ERPlora pone también esa razón social, NIF y dirección en las facturas que te emite a ti; sin marcar, ERPlora sigue sabiendo quién es el negocio (lo necesita para presentar ante Hacienda) pero no toca el perfil que le paga, que puede ser el de tu gestoría.
5. Pulsa **Guardar cambios**. Sale «Ajustes guardados». La franja de bloqueo de Inicio y la lista de puesta en marcha se releen antes de que se lea el mensaje, porque el NIF y la razón social son lo que desbloquea poder facturar.
Entra: los seis campos y la casilla.
Sale: los datos del negocio en los ajustes (HUB-F221); el hub los publica en erplora.com (nombra al obligado en el otorgamiento de representación). Los leen Facturas y los módulos fiscales como emisor. El hub normaliza el NIF.
En este mismo documento se apoya en: HUB_SHELL-F27 (Seguir la lista «Termina de configurar tu negocio»), HUB_SHELL-F28 (Ver qué falta para poder facturar).
Si falla: lo escrito se queda en los campos para corregir solo el que falla (no se vacían). El motivo sale como frase: «El NIF ya no se puede cambiar: este negocio ya ha emitido con él.», «El NIF debe ser un texto.», «El NIF es demasiado largo: el límite de la AEAT es de 20 caracteres.», «Eso no tiene forma de NIF: DNI (12345678Z), NIE (X1234567L), CIF (B12345674) o identificador extranjero con prefijo de país (FR123456789).», «La letra o dígito de control del NIF no es el que corresponde: revísalo y vuelve a escribirlo.»; en una demo, «Una demo se queda siempre en el entorno de pruebas de la AEAT. Crea tu propio negocio en erplora.com para remitir de verdad.». Si se guardó pero no se pudo compartir con erplora.com, sale además «No se han podido compartir los datos con ERPlora.». Un perfil que no administra ve los campos sin poder editarlos.
Implicados: HUB-F221, INVOICE-F01, INVOICE-F03, VERIFACTU-F01, REC_ALTA-F09
QA: ninguno

### HUB_SHELL-F165 Ir a dar de alta la impresora y configurar el tique
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ajustes › Impresión
Pasos:
1. Abre **Impresión**. La primera fila es **Impresoras y tique** («Da de alta tu impresora y configura el tique impreso y digital»).
2. Pulsarla abre la pantalla de la app de impresión, donde se dan de alta las impresoras y se arregla el tique.
3. Si la app de impresión no está instalada, la fila dice «Instala la app Impresión para dar de alta tu impresora y configurar el tique» y lleva a **Apps** para instalarla. En cuanto se instala, la fila deja de mandar a la tienda sin recargar.
Entra: las apps instaladas.
Sale: nada guardado; la plantilla del tique y las impresoras son de la app de impresión, no del shell.
Si falla: no falla; es navegación.
Implicados: PRINTING-F01, PRINTING-F02, PRINTING-F06, REC_ALTA-F17
QA: ninguno

### HUB_SHELL-F166 [retirado] Ver quién está sacando cada tipo de tique
Implicados: ninguno
Sustituido por HUB_SHELL-F75 (`workflow/avisos-e-impresion.md`): era el mismo gesto, la tarjeta «Estado de impresión» de Ajustes › Impresión (`lib/print-coverage.ts`).

### HUB_SHELL-F167 Conceder un permiso a una app
Estado: parcial — no hay confirmación al conceder ni al retirar, ni siquiera con el certificado; tras conceder no se relee ni la campana de eventos caídos ni la lista de puesta en marcha, aunque el hub haya reenviado en ese gesto los avisos que cayeron por falta de permiso; y si la carga falla, a la vez sale un aviso de error y «Ninguna app instalada pide permisos»
Actor: administrador
Pantalla: Ajustes › Permisos
Pasos:
1. Abre **Permisos**. Arriba: «Permisos de las apps — Concede o revoca los permisos que cada app pide (acceso a internet, certificado, impresora, notificaciones, administrar automatizaciones). Por seguridad, todo está denegado hasta que lo concedas.». Quien no administra lee además «Solo un administrador puede cambiar los permisos.».
2. Mientras carga, tres puntos. Después, una tarjeta por cada app instalada que pide alguno, con un interruptor por permiso: su nombre, lo que permite, y —mientras está apagado— la consecuencia: «Sin esto, tus facturas no se firman y no llegan a Hacienda.», «Sin esto, los tiques y las comandas se quedan en la cola de impresión y no sale ninguno.», «Sin esto, no llega ningún recordatorio ni confirmación a tus clientes por email, SMS o WhatsApp.», «Sin esto, la app no puede salir a internet…», «Sin esto, la app no puede crear ni editar tus automatizaciones, así que las que necesita no se ejecutan.».
3. Enciende el interruptor del permiso. Sale «{permiso} concedido a {app}.» y la consecuencia desaparece.
4. El permiso de administrar automatizaciones se concede aquí a la app que las necesita; lo que el motor de automatizaciones exige después a la sesión es cosa del hub.
Entra: el permiso elegido de una app instalada.
Sale: el permiso concedido a esa app (HUB-F32); en el mismo gesto el hub devuelve a la cola todos los avisos del hub que habían caído por un permiso sin conceder, de cualquier app (HUB-F58); la campana y la pestaña Eventos caídos no se releen.
Si falla: el interruptor vuelve a su sitio y sale «No se pudo cambiar el permiso.». Si no se pudieron leer los permisos de una app, esa app falta en la lista sin decirlo; si no se pudo leer la lista de apps, sale «No se pudieron cargar los permisos.» y debajo «Ninguna app instalada pide permisos.». La lista se carga la primera vez que se entra en la pestaña y no se vuelve a leer hasta recargar la pantalla.
Implicados: FLOWS-F01, HUB-F32, HUB-F58, HUB-F111, PRINTING-F16, VERIFACTU-F01, REC_ALTA-F10
QA: ninguno

### HUB_SHELL-F168 Retirar un permiso a una app
Estado: hecho
Actor: administrador
Pantalla: Ajustes › Permisos
Pasos:
1. En **Permisos**, apaga el interruptor del permiso de la app.
2. Sale «{permiso} revocado a {app}.» y debajo del permiso aparece la consecuencia de F167 («Sin esto…»), con un aviso de atención, para que quien lo apaga sepa qué deja de funcionar.
Entra: el permiso elegido.
Sale: el permiso retirado a esa app (HUB-F32); no mueve ningún aviso.
Si falla: el interruptor vuelve a «concedido» y sale «No se pudo cambiar el permiso.». A quien no administra el interruptor le sale desactivado.
Implicados: HUB-F32
QA: ninguno

### HUB_SHELL-F169 Dar los permisos de las apps que ha instalado una plantilla
Estado: hecho
Actor: administrador
Pantalla: Permisos de tus apps
Pasos:
1. Al terminar de cargar una plantilla (desde Ajustes › Datos y copias, desde la tarjeta de un negocio vacío de Inicio o con el asistente) sale una ventana **Permisos de tus apps**, solo si alguna de las apps instaladas pide algo que aún no está concedido: «La plantilla ha instalado estas apps y necesitan tu permiso para funcionar: una plantilla no puede dártelo por ti. Puedes cambiarlo cuando quieras en Ajustes → Permisos.».
2. Cada app lista sus permisos, lo que permiten y qué deja de funcionar sin ellos.
3. La ventana sale también tras cargar la copia de otro negocio o tras «Reintentar lo que falta», aunque su texto hable de «la plantilla».
4. **Dar permisos** los concede todos de una vez («Dando permisos…»); la lista de puesta en marcha se relee. **Ahora no** (o tocar fuera) cierra sin conceder nada.
Entra: el informe de la importación, para saber qué apps se instalaron.
Sale: los permisos concedidos a esas apps (HUB-F32) si se acepta. Una plantilla nunca concede nada por sí sola (HUB-F237).
Si falla: «No se han podido dar los permisos de {apps}. Vuelve a intentarlo o actívalos en Ajustes → Permisos.»; quedan en la ventana solo las apps que fallaron.
Implicados: HUB-F32, HUB-F237, REC_ALTA-F08
QA: ninguno

### HUB_SHELL-F170 Conectar el número de WhatsApp del negocio
Estado: parcial — hoy Meta solo deja conectar números del portfolio de ERPlora (verificación del negocio y revisión de la app pendientes, pm#277); la etiqueta «App de WhatsApp Business» no sale nunca, porque erplora.com no manda `is_on_biz_app` ni al conectar ni en la lista de números
Actor: administrador
Pantalla: Tu número
Pasos:
1. Abre **Bandeja de WhatsApp → Ajustes**; el bloque **Tu número** dice: «Conecta el número de WhatsApp de tu negocio. Iniciarás sesión con Facebook y escanearás un código QR con la app de WhatsApp Business de tu móvil.» y muestra **Conectar WhatsApp**. A quien no es dueño ni administrador el hub le niega el estado (403): ese perfil no ve la presentación, ni el número, ni botones; solo la frase roja «Solo un dueño o un administrador puede conectar el número de WhatsApp.», sin Reintentar.
2. Pulsa **Conectar WhatsApp**: «Abriendo la conexión con WhatsApp…». El navegador carga el programa de Facebook (en español o inglés) y abre su ventana.
3. En la ventana inicia sesión, elige conectar la app de WhatsApp Business, escribe el número y escanea el QR con la app del móvil.
4. Al cerrarse, «Conectando tu número…»: el hub entrega a erplora.com lo que devolvió Facebook (un código de un solo uso y los identificadores).
5. El bloque pasa a **Conectado** con el número y **Desconectar** (la etiqueta «App de WhatsApp Business» saldría si erplora.com dijera que el número es de esa app, pero no lo dice ni al conectar, que solo devuelve el identificador y el número visible, ni en la lista, HUB-F261); debajo, «Los mensajes de tus clientes llegan a la Bandeja y las automatizaciones los contestan.».
Entra: el código y los identificadores que da Facebook al terminar; el hub los reenvía con su credencial de máquina (el navegador no la ve).
Sale: el número queda conectado en erplora.com (HUB-F260); empiezan a llegar mensajes (HUB-F263).
Si falla: la frase del motivo y, si procede, **Reintentar**: «La conexión se canceló antes de terminar.» y «No se pudo abrir la ventana de Facebook. Permite las ventanas emergentes en este sitio e inténtalo de nuevo.» (las decide la propia pantalla), «No se añadió ningún número de teléfono. Vuelve a abrir la conexión y añade o elige un número.» (el 404 de erplora.com), la de quien no puede conectar, o la genérica «Algo ha fallado al conectar. Inténtalo de nuevo en un minuto.». Las frases propias de los motivos de erplora.com y de Meta (`whatsappConnect.errors.not_configured`, `internal_error`, `no_business_account`, `no_access_token`, `meta_unreachable`, `meta_api_error`) no se ven nunca a través del hub: un fallo 5xx llega como `cloud_rejected` (`crates/server/src/cloud_proxy.rs`, `cloud_envelope_passthrough`) y una negativa en prosa no es un código (`lib/whatsapp-connect.ts`, `refusalCode`), así que las dos caen en la genérica. Si la plataforma no tiene WhatsApp configurado, al administrador el bloque no le pinta nada (ni botón, ni mensaje): no se ofrece conectar; quien no administra ve igualmente la frase de negativa. Si el elemento no existe en un hub antiguo, la Bandeja lo dice.
Implicados: HUB-F260, WHATSAPP_INBOX-F01, SAAS_WHATSAPP_INBOX-F01, SAAS_WHATSAPP_INBOX-F02
QA: WA-01, WA-07

### HUB_SHELL-F171 Ver si el número está bien conectado y reconectarlo
Estado: hecho
Actor: administrador
Pantalla: Tu número
Pasos:
1. En **Tu número**, cada número conectado sale con una etiqueta: **Conectado** en verde, o **Hay que reconectar** en rojo si WhatsApp retiró el permiso de escribir en nombre del negocio.
2. Con **Hay que reconectar** el bloque dice: «WhatsApp ha retirado el permiso para escribir en nombre de tu negocio. Los mensajes de tus clientes no están llegando y nada de lo que contestes sale. Vuelve a conectar tu número para recuperar el canal.» y el botón **Volver a conectar WhatsApp**. La frase de «tus mensajes llegan a la Bandeja» no sale mientras el permiso está caído.
3. Pulsarlo abre la misma ventana de Facebook que en F170; no hace falta desconectar antes. Al volver, el bloque se vuelve a leer y se pone verde solo.
Entra: la lista de números con su marca de «hay que reconectar», que viene de erplora.com (HUB-F261).
Sale: el permiso renovado en erplora.com.
En este mismo documento se apoya en: HUB_SHELL-F37 (Ver si la impresora y WhatsApp funcionan).
Si falla: igual que F170; a quien no es dueño ni administrador el hub le niega el estado: solo ve, en rojo, «Solo un dueño o un administrador puede conectar el número de WhatsApp.», sin número, sin «Hay que reconectar» y sin **Reintentar**. Si el hub antiguo de erplora.com no manda la marca, el bloque lee «Conectado»: la falta de dato no levanta la alarma.
Implicados: HUB-F261, HUB-F262, WHATSAPP_INBOX-F02
QA: WA-09

### HUB_SHELL-F172 Desconectar el número de WhatsApp
Estado: hecho
Actor: administrador
Pantalla: Tu número
Pasos:
1. En **Tu número**, pulsa **Desconectar** (rojo, junto al número; solo un administrador lo ve).
2. El navegador pregunta, en su ventana de confirmación: «¿Desconectar este número? Los mensajes dejarán de llegar aquí.». Si cancela, no pasa nada.
3. El bloque se vuelve a leer y vuelve a ofrecer **Conectar WhatsApp**. Las conversaciones guardadas no se tocan.
Entra: el número elegido.
Sale: erplora.com deja de recoger los mensajes de ese número (HUB-F262).
Si falla: la frase del motivo (y **Reintentar** si procede). Si el número ya no estaba conectado, no es un error: «Ese número ya no está conectado.» y la lista se actualiza.
Implicados: HUB-F262, WHATSAPP_INBOX-F02
QA: WA-01, WA-09

### HUB_SHELL-F173 Exportar una copia de seguridad o una plantilla
Estado: parcial — «Ajustes» se exporta entero o no se exporta; el nombre viene relleno con «hub»; la copia de seguridad solo restaura de verdad en el MISMO hub (en otro hub entran la configuración y los datos de las apps, pero no las personas, ni el NIF, la razón social y el domicilio, ni la numeración, ni los permisos, aunque la pantalla diga «mudar» e «Incluye a tu gente», y el certificado nunca se aplica); con «Plantilla», «Imágenes y media» (marcada por defecto) copia también la carpeta de VeriFactu con los XML enviados a Hacienda, con datos de clientes (ERPlora/hub#2496); y el código conserva un `TODO(ADR-0113)` en producción
Actor: administrador
Pantalla: Ajustes › Datos y copias › Exportar
Pasos:
1. Abre **Datos y copias** y elige **Exportar** en el selector de arriba (Importar, Exportar y Restablecer). Dice: «Empaqueta cómo está configurado este negocio — y si quieres sus datos — como una plantilla que puedes cargar en otro negocio.». Un perfil que no administra lee «Solo un administrador puede exportar el negocio.» y no puede pulsar **Exportar**.
2. Escribe el **Nombre** y elige el **Idioma** del archivo; debajo se ve el nombre final: «{nombre}_{idioma}.blueprint.zip».
3. Responde «¿Para qué es este archivo?»: **Copia de seguridad de este negocio** («Copia privada para restaurar o mudar este negocio. Incluye a tu gente y sus accesos.», la que viene marcada; el texto promete más de lo que hace en otro hub, ver el `Estado`) o **Plantilla para compartir** («Para publicar o dar a otro negocio. Nunca incluye personas, PIN ni certificados fiscales.»). En una instalación de demostración o de pruebas solo se puede exportar plantilla y la elección sale apagada con «Esta es una instalación de demostración o de pruebas, así que solo puede exportar plantillas: las personas, los PIN y los datos fiscales nunca viajan en su archivo.». La elección se conserva si se pasa a Importar o Restablecer y se vuelve.
4. Marca las **Secciones**: **Usuarios** («Empleados, roles y permisos»), **Ajustes** («Ajustes del negocio: moneda, idioma, datos fiscales»; en una plantilla, «…país, moneda, idioma y tema. Nunca el NIF ni la razón social.»), **Fiscal** («Configuración VeriFactu y el certificado de empresa», viene sin marcar y avisa: «Incluye el certificado: el .p12 viaja tal cual y conserva su contraseña. Comparte el fichero solo con gente de confianza.») e **Imágenes y media**. Con «Plantilla» desaparecen Usuarios y Fiscal.
5. Elige las apps (F174) y pulsa **Exportar**. Mientras trabaja: «Exportando…».
6. En un navegador, el archivo baja por el gestor de descargas y sale «{archivo} descargado.»; en la app instalada lo guarda la propia app y el aviso dice «Guardado en {ruta}».
Entra: el nombre, el idioma, la finalidad, las secciones y las apps; la lista de apps instaladas y, si el hub lo impone, la finalidad fijada.
Sale: un `.blueprint.zip` (HUB-F230, HUB-F231). Con «Plantilla» la pantalla oculta Usuarios y Fiscal y manda las dos a `false`; el hub excluye personas y NIF, pero el certificado lo decide la casilla tal como llega al hub (si no se pudo leer la finalidad impuesta, en una demo se puede elegir «Copia» con Fiscal marcado y el certificado viaja), y «Imágenes y media» copia también `media/modules/verifactu/**` (ERPlora/hub#2496). El texto de la demo «los datos fiscales nunca viajan en su archivo» es falso mientras siga abierta esa issue.
Si falla: «La exportación falló: {motivo}» con la frase del hub; si tarda demasiado, «El servidor está tardando demasiado en generar la copia. Inténtalo de nuevo en un momento.»; si no se puede guardar, «No se ha podido descargar el archivo.», o en móvil y tableta «Esta app no puede guardar archivos en un móvil o una tablet. Abre tu negocio en un navegador para descargarlo.».
Implicados: HUB-F230, HUB-F231, HUB-F232, HUB_APP-F30, REC_ALTA-F23
QA: qa-hub §4

### HUB_SHELL-F174 Elegir qué apps, datos y tablas viajan en la exportación
Estado: parcial — las casillas de tablas enseñan el nombre interno de cada tabla («inventory_product · 12»), no un nombre que el dueño reconozca; y si el hub no da la lista de tablas se exporta todo sin decirlo
Actor: administrador
Pantalla: Ajustes › Datos y copias › Exportar
Pasos:
1. En **Exportar**, bajo «Apps» («Elige qué apps instaladas registra la plantilla y si sus datos viajan con ella»), una tabla con una fila por app instalada: **App**, **Versión**, y dos casillas, **App** (registrarla para que se instale) y **Datos** (llevar también sus datos). Vienen todas con la app marcada y sin datos.
2. Desmarcar la app desmarca y desactiva sus datos. **Seleccionar todo** marca app y datos de todas; **Deseleccionar todo** desmarca app y datos de todas (no vuelve a lo de fábrica: deja la plantilla sin ninguna app registrada).
3. Al marcar **Datos** de una app aparece debajo una tarjeta con el nombre de la app y una casilla por tabla con su número de filas. Desmarcar una tabla la deja fuera: es una herramienta para no publicar, por ejemplo, las citas pasadas de la peluquería de origen.
4. Pulsar **Exportar** (F173) manda la selección. Sin ninguna tabla desmarcada se manda «todas» (no la lista), para que una tabla nueva de una app no se quede fuera sin que nadie lo decida.
Entra: las apps instaladas y el recuento de filas por tabla (HUB-F232).
Sale: nada guardado; la selección viaja al exportar.
Si falla: si no se pueden leer las apps instaladas, la tabla sale vacía; si no se puede leer el recuento de tablas, no salen las tarjetas de tablas y se exporta todo.
Implicados: HUB-F230, HUB-F232, REC_ALTA-F23
QA: ninguno

### HUB_SHELL-F175 Elegir una plantilla del catálogo para importar
Estado: hecho
Actor: administrador
Pantalla: Ajustes › Datos y copias › Importar
Pasos:
1. Abre **Datos y copias**; **Importar** es lo que se abre. Dice: «Carga una plantilla: instala las apps que falten, aplica sus datos y copia las imágenes.» y «Elige qué cargar — Elige una plantilla publicada para tu negocio, o sube un .blueprint.zip que hayas exportado o guardado como copia.».
2. Mientras carga el catálogo: «Cargando plantillas…». Después, tarjetas (o tabla, a elección) con **Plantilla**, descripción, **Idioma**, **País** (el nombre, «España», no «ES»), **Versión**, **Descargas** y **Tamaño**, con búsqueda «Buscar plantillas».
3. Pulsa **Usar plantilla** en la que sirva: el hub la baja, comprueba que está íntegra y la lee; sigue F177.
Entra: el catálogo de plantillas de erplora.com y la plantilla elegida (HUB-F234).
Sale: nada guardado hasta F177.
En este mismo documento se apoya en: HUB_SHELL-F26 (Empezar con una plantilla de un negocio como el tuyo).
Si falla: un perfil sin permiso de administrar no pide el catálogo y lee «Solo un administrador puede ver e importar plantillas.» (y arriba «Solo un administrador puede importar.»); sin plantillas, «Todavía no hay plantillas publicadas para tu negocio.»; si el catálogo no se pudo leer, «No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.» con **Reintentar**; si la plantilla no baja o no se lee, «No se pudo leer el fichero: {motivo}».
Implicados: HUB-F234, INVENTORY-F12, REC_ALTA-F08
QA: qa-hub §4

### HUB_SHELL-F176 Subir un fichero para importar
Estado: hecho
Actor: administrador
Pantalla: Ajustes › Datos y copias › Importar
Pasos:
1. En **Importar**, pulsa **Subir desde archivo** y elige un `.blueprint.zip` (una plantilla de otro negocio o una copia de seguridad).
2. Mientras el hub lo lee, el botón gira. Después, sigue F177.
3. Se puede elegir el mismo fichero otra vez tras un error.
Entra: el fichero.
Sale: nada guardado hasta F177; el hub lo inspecciona (HUB-F233).
Si falla: «No se pudo leer el fichero: {motivo}», y se queda en la elección.
Implicados: HUB-F233
QA: qa-hub §4

### HUB_SHELL-F177 Revisar y cargar lo que trae el fichero
Estado: parcial — las apps del fichero se instalan aunque se desmarquen, los roles, los permisos y las automatizaciones entran sin casilla, y la casilla de Fiscal viene marcada y promete «el certificado», que el hub nunca aplica
Actor: administrador
Pantalla: Ajustes › Datos y copias › Importar
Pasos:
1. Tras elegir una plantilla o un fichero, ve su resumen: **Nombre**, **Idioma**, **País** (el idioma y el país salen como códigos, `es`, `ES`, mientras el catálogo los da por nombre), **Apps** (cuántas) y **Creado**.
2. En «Secciones detectadas» solo salen las que el fichero trae, todas marcadas: **Usuarios**, **Ajustes**, **Fiscal** («Configuración VeriFactu y el certificado de empresa (.p12)») e **Imágenes y media**.
3. En «Apps», una casilla por app del fichero, con su identificador interno y «v{versión}» (más «incluye datos» si los trae).
4. Pulsa **Importar** («Importando… instalando apps y aplicando datos.») o **Elegir otro fichero** para volver.
5. Al terminar sale el informe (F178). Si el hub rechaza la importación, vuelve a esta pantalla con «La importación falló: {motivo}» y el fichero cargado.
6. Cuando termina, el lanzador «Mis apps» de la barra superior se actualiza con las apps nuevas (las apps no están en el menú lateral).
Entra: las casillas y el identificador de subida; el origen (plantilla y versión) si vino del catálogo.
Sale: la importación completa (HUB-F235): apps instaladas, secciones aplicadas, roles, permisos de apps y automatizaciones (HUB-F237) y un informe guardado por lote (HUB-F239).
Si falla: solo un perfil con permiso de administrar puede pulsar **Importar**; el hub vuelve a comprobarlo.
Implicados: HUB-F235, HUB-F236, HUB-F237, INVENTORY-F12, REC_ALTA-F08
QA: qa-hub §4

### HUB_SHELL-F178 Leer el informe de la importación
Estado: parcial — la fila Fiscal dice «Saltado» aunque se marcara y el certificado pendiente (que el hub nunca aplica y manda a subir a mano) no se avisa nunca; las filas de datos de app enseñan el identificador interno («App {id}»); y «Numeración descartada… configúralas en Ajustes» manda a un sitio donde no hay series
Actor: administrador
Pantalla: Ajustes › Datos y copias › Importar
Pasos:
1. Al terminar, «Informe de la importación»: una fila por sección (Usuarios, Ajustes, Fiscal, Imágenes y media, Roles, Permisos de las apps, Automatizaciones, «App {id}»…) con su estado a la derecha y, debajo, el motivo: **Aplicado**, **Saltado**, **Descartado**, **Aplicado en parte** o **Falló**.
2. Los descartes se explican en una frase con su número: por ejemplo, «Los usuarios, roles y PIN son del negocio que los creó. Cuentas descartadas: {n}. Nadie ha obtenido acceso al tuyo.», «Se han aplicado el país, la moneda y el idioma. Ajustes descartados: {n} — el NIF, la razón social y demás datos son del negocio que creó el fichero; los tuyos se quedan como están.», «Permisos de apps descartados: {n}. El acceso a tu impresora, a tu certificado de firma y a internet se concede solo en este terminal…», «Automatizaciones restauradas, pero apagadas…». Las imágenes que no se copiaron salen como «{n} sin copiar».
3. Debajo, el bloque «Apps»: cada app con su nombre, **Aplicado** si se instaló, **Saltado** si ya estaba, **Falló** con su motivo, o **Requiere contratación** con qué contratar y su precio («No se ha instalado: necesita apps que aún no tienes contratadas: Facturación (9,00 €). Contrátalas y vuelve a cargarla — no se ha tocado nada más.»). Si entró otra versión de la pedida: «La plantilla traía la {x}; ha entrado la más reciente compatible, la {y}.».
4. **Ir al inicio** lleva a Inicio; los permisos de las apps instaladas se piden en la ventana de F169.
Entra: el informe que devuelve el hub (HUB-F239).
Sale: nada guardado en la pantalla; el informe queda guardado en el hub.
Si falla: un estado que la pantalla no conoce se pinta como «Falló» con el texto tal cual, nunca como un éxito inventado.
Implicados: HUB-F239, INVENTORY-F12
QA: qa-hub §4

### HUB_SHELL-F179 Volver al informe de una importación que no entró entera y reintentar
Estado: parcial — el informe viejo tapa el catálogo cada vez que se abre Importar mientras tenga una fila «Descartado» o «Aplicado en parte» (lo normal al cargar la copia de seguridad de otro negocio o plantillas antiguas; una plantilla actual da Aplicado o Saltado), y justo tras una importación con fallos no sale el botón de reintentar hasta volver a entrar (leído, sin ejecutar)
Actor: administrador
Pantalla: Ajustes › Datos y copias › Importar
Pasos:
1. Al abrir **Importar**, un administrador ve primero, en lugar del catálogo, el informe de su última importación si algo falló, quedó pendiente de contratar, se descartó o se aplicó en parte, con el aviso «Este es el informe de tu última importación de {nombre} ({fecha}). No todo entró.».
2. Si algo falló o está pendiente de contratar, ve **Reintentar lo que falta**. El hub vuelve a bajar la misma versión de la plantilla y reaplica solo lo que no entró; lo ya aplicado no se toca ni se duplica. Sale el informe nuevo.
3. Si la importación vino de un archivo subido a mano, el botón sale desactivado con el porqué: «Esta importación vino de un archivo subido a mano, así que no se puede reintentar automáticamente. Vuelve a subir el archivo y selecciona solo lo que falló.».
4. **Ver las plantillas** cierra el informe y vuelve al catálogo; **Ir al inicio** sale.
Entra: el último informe guardado (HUB-F239) y, al reintentar, el identificador de su lote.
Sale: el informe nuevo y, si procede, apps y datos que antes no entraron (HUB-F240).
En este mismo documento se apoya en: HUB_SHELL-F26 (Empezar con una plantilla de un negocio como el tuyo), HUB_SHELL-F39 (Ver Inicio al día después de importar una plantilla).
Si falla: «La versión de la plantilla que usó esta importación ya no está en el catálogo, así que el reintento no se ejecutó — reintentar con otra versión podría cargar datos distintos.», «El informe de esta importación ya no está registrado (puede que se deshiciera), así que no hay nada que reintentar.»; con otro fallo, la frase del hub. Sin nada que reintentar no hay botón.
Implicados: HUB-F239, HUB-F240
QA: ninguno

### HUB_SHELL-F180 Deshacer una importación
Estado: parcial — la pantalla no enseña el fallo si el hub rechaza deshacer, y el hub no revierte ajustes ni tablas sin identificador (HUB-F241)
Actor: administrador
Pantalla: Ajustes › Datos y copias › Restablecer
Pasos:
1. En **Restablecer**, si hay importaciones deshacibles, aparece arriba «Deshacer una importación — Quita solo lo que trajo ese blueprint. Lo que hayas creado después se conserva.» con una fila por importación: nombre, «{n} filas» y **Deshacer**.
2. Pulsa **Deshacer**: «Deshacer «{nombre}»» — «Se borrarán las {n} filas que trajo este blueprint. Lo que creaste después se conserva.», y si cambiaste algo después: «Cambiaste {apps} después de importar. Al deshacer solo se quedan tus cambios ahí: lo que este blueprint sustituyó no vuelve.».
3. Confirma con **Deshacer** (o **Cancelar**). No pide escribir el nombre: se puede volver a importar.
4. Sale el recuento por app («{app} — {n} filas borradas») y, si hay, «En {apps} solo se han quedado tus cambios: lo que el blueprint había sustituido no ha vuelto. Revisa esa pantalla.».
Entra: el lote elegido.
Sale: se borran exactamente las filas que trajo el lote (HUB-F241).
Si falla: no hay mensaje; la promesa rechazada no se recoge y la lista no cambia (el informe automático de F149 lo apunta).
Implicados: HUB-F241
QA: ninguno

### HUB_SHELL-F181 Restablecer el negocio por secciones
Estado: parcial — escribir mal el nombre (o no tener razón social guardada: entonces no se puede restablecer nunca) cierra la ventana sin decir nada; si el hub rechaza, no se ve el motivo; quien no administra ve una lista vacía y ningún mensaje; tras restablecer los ajustes el shell no los relee; y la pantalla no dice qué NO se borra
Actor: administrador
Pantalla: Ajustes › Datos y copias › Restablecer
Pasos:
1. En **Restablecer**: «Borra definitivamente los datos que marques. No se puede deshacer: si dudas, expórtate antes una copia.». El botón **Exportar una copia antes** lleva a Exportar.
2. Aparece una casilla por cada sección que tenga filas, con su número («{n} filas»): **Ajustes del negocio**, **Empleados**, **Roles activos**, **Cola de impresión** y una por cada app (por su nombre). Las que el hub bloquea (si el negocio ya emitió registros fiscales) salen sin poder marcarse y con el motivo al lado. Con «O borrar por secciones» si hay importaciones que deshacer.
3. Marca lo que quiere. **Restablecer el negocio** (rojo) se activa con al menos una.
4. Sale «Esto no se puede deshacer — Se borrarán definitivamente {n} filas:» con el desglose, y un campo de texto con la razón social del negocio como pista. Hay que escribir exactamente esa razón social (la de Ajustes › Negocio) y pulsar **Borrar definitivamente** (o **Cancelar**).
5. Sale el informe: una línea por sección con «{nombre} — {n} filas borradas», y la lista se recalcula.
Entra: el plan del hub (filas y bloqueos por sección, HUB-F242) y la selección.
Sale: borrado definitivo de lo marcado; el hub no pide ninguna confirmación (solo la pide esta pantalla) y revalida que sea administrador y el límite fiscal.
Lo que NO borra (HUB-F242): archivos, certificado, perfil fiscal, automatizaciones, permisos de las apps, llaves de API, dispositivos, historial de avisos, ni las sesiones y perfiles de las personas borradas; tampoco borra a quien lo ejecuta; y con el negocio ya emitiendo, Ventas, Facturas y VeriFactu quedan bloqueados, así que «empezar de cero» no es posible.
Si falla: si el nombre escrito no coincide, o el negocio no tiene razón social guardada, la ventana se cierra sin mensaje y no se borra nada; si el hub rechaza (por ejemplo, el límite fiscal), no se muestra su motivo y no se avisa; si no se pudo leer el plan (por ejemplo, un perfil que no administra: el hub contesta 401 o 403), la lista sale vacía, el botón rojo desactivado y no se da ningún mensaje, ni se piden las importaciones deshacibles. El manual dice «escribe el nombre del negocio»: lo que hay que escribir es la razón social.
Implicados: HUB-F242
Pendiente de enlazar: verifactu — el límite fiscal que bloquea el borrado tras emitir
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| País, zona, moneda, idioma, paleta del negocio | hecho (moneda, idioma y paleta: parcial) | HUB_SHELL-F156 a F161 |
| Nombre comercial, teléfono y correo del negocio | no hecho | HUB_SHELL-F164 |
| Identidad fiscal y domicilio en partes | parcial | HUB_SHELL-F164 |
| Certificado, vía de envío, producción y vuelta a pruebas | de VeriFactu (módulo), no del shell | VERIFACTU-F02/F03/F04/F08/F09 |
| Permisos de las apps: conceder y retirar | parcial / hecho | HUB_SHELL-F167, HUB_SHELL-F168 |
| Permisos tras importar una plantilla | hecho | HUB_SHELL-F169 |
| «Tu número» de WhatsApp: conectar, estado, reconectar, desconectar | parcial / hecho | HUB_SHELL-F170, F171, F172 |
| Exportar copia o plantilla | parcial | HUB_SHELL-F173, HUB_SHELL-F174 |
| Importar plantilla o fichero, con informe por sección | parcial | HUB_SHELL-F175 a F179 |
| Deshacer una importación | parcial | HUB_SHELL-F180 |
| Restablecer con confirmación | parcial | HUB_SHELL-F181 |
| Tarjetas Este dispositivo / Pinpad / Dispositivos | de otras áreas | HUB_SHELL-F11, HUB_SHELL-F99 a F104 |

## Datos: de quién es cada dato

- Los ajustes del negocio, los permisos concedidos a cada app, el informe de importación y los
  números de WhatsApp son del servidor; esta área no guarda nada propio. Lo único que la pantalla
  recuerda es la pestaña, en la dirección; las selecciones de exportar no se guardan.
- Datos personales que pasan por estas pantallas: la razón social y el NIF (de una persona física en
  un autónomo), el domicilio fiscal, el número de teléfono de WhatsApp y el nombre de las personas
  dentro de una copia de seguridad (exportación con «Usuarios»).

## Reglas que no se rompen

- Una plantilla nunca concede permisos por sí misma: se piden con la ventana de HUB_SHELL-F169.
- Restablecer exige teclear la razón social guardada en Ajustes › Negocio; la autoridad sobre el
  borrado y el límite fiscal es el hub.

Lo que se busca y hoy **no** se cumple (huecos, no reglas):

- «Exportar como plantilla no lleva personas, PIN, NIF ni certificados». Hoy: Usuarios y Fiscal los
  oculta la pantalla; el certificado lo decide la casilla tal como llega al hub; «Imágenes y media»
  (marcada por defecto) copia los XML enviados de VeriFactu (ERPlora/hub#2496) (HUB_SHELL-F173).
- «La copia de seguridad sirve para mudar el negocio». Solo restaura de verdad en el mismo hub
  (HUB_SHELL-F173).

## Lo que NO hace, a propósito

- No se sube el certificado, ni se elige la vía de envío, ni se pasa a producción desde Ajustes: es
  del módulo VeriFactu.
- Restablecer no borra archivos, certificado, perfil fiscal, automatizaciones, permisos de las apps,
  llaves de API, dispositivos, historial de avisos ni a quien lo ejecuta.

## Dudas abiertas

- ¿El informe de una importación vieja debe seguir tapando el catálogo cuando solo hay filas
  «Descartado»?

## Fuentes contrastadas

- Manual `08-ajustes-del-negocio.md` y los flujos del servidor: «Ajustes › Hub»; la pestaña se llama
  **General**. El manual lista la zona horaria como editable; el hub la deduce del país salvo que se
  declare, y la pantalla ofrece «Automática» más las zonas del país.
- Manual `09-datos-importacion-exportacion.md`: «Ajustes > Datos» y «escribe el nombre del negocio»;
  la pestaña es **Datos y copias** y hay que escribir la **razón social** de Ajustes › Negocio, exacta.
- Servidor (HUB-F242): «las secciones archivos y datos fiscales se aceptan pero no borran nada»; la
  pantalla nunca las ofrece (el plan no las trae); existen las claves `settings.reset_media` y
  `settings.reset_fiscal`, sin uso.
- La nota del informe de importación del hub (`export_import.rs:812-817`) manda a subir el
  certificado «en Ajustes → Negocio»; allí no hay certificado.
- Servidor (HUB-F235): «las apps del manifiesto se instalan aunque no estén marcadas»; la pantalla
  ofrece una casilla por app.
- Los comentarios de `settings-tabs.ts` dicen que «Negocio» contiene «los datos de la empresa y su
  certificado»; solo los datos.
