# WORKFLOW — La aplicación instalada · Instalar y enlazar

Prefijo: HUB_APP

## Flujos

### HUB_APP-F01 Instalar la aplicación
Estado: parcial — Google Play: producción (1.1.28, solo España) enviada a revisión el 19/09/2026 según `TODO-ANDROID.md`, resultado sin confirmar; Microsoft Store sin confirmar; el `.dmg` de macOS se construye sin notarizar y el hub no ofrece descarga para macOS
Actor: administrador, responsable
Pantalla: HUB_SHELL: Sistema
Pasos:
1. **Android**: instala «ERPlora» desde Google Play (único canal para clientes; no hay APK suelto).
2. **Windows**: instálala desde Microsoft Store (canal principal, MSIX que la Store firma) o con el
   instalador `.exe`/`.msi` que ofrece erplora.com (sin firmar: Windows avisa con SmartScreen).
3. **macOS**: abre el `.dmg` y arrastra ERPlora a Aplicaciones. Va sin notarizar: la primera vez,
   botón derecho → Abrir.
4. Ábrela (HUB_APP-F02). Desde un navegador, **Sistema** ofrece la descarga que corresponde al
   dispositivo y la oculta dentro de la propia aplicación.
Entra: el instalador del canal; en el instalador de Windows y en el de la Store, el esquema
`erplora://` queda registrado al instalar.
Sale: la aplicación `com.erplora.app` con su versión (la de `tauri.conf.json`, que cada publicación sobrescribe con el tag; 1.0.1 es el valor del repo) y su canal
(`play`, `msstore` o `direct`), horneado al compilar en Android y deducido en ejecución en Windows
(una copia que corre desde `WindowsApps` es `msstore`). Ante la duda es `direct`, a propósito.
Si falla: Windows muestra su aviso de editor desconocido; macOS, el de desarrollador no verificado;
Android sin Play no hay camino de instalación del cliente. En Linux solo hay `.deb` y AppImage de
QA, sin canal anunciado.
Implicados: pendiente
Pendiente de enlazar: saas — descarga `/app/download/<plataforma>/` y su redirección a la tienda
Pendiente de enlazar: hub — HUB_SHELL, Sistema (descargar la aplicación desde el navegador)
QA: qa-hub-android Fase 0

### HUB_APP-F02 Primer arranque: entrar y abrir el negocio
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ventana de ERPlora
Pasos:
1. Abre la aplicación recién instalada: no recuerda ningún negocio, así que carga la página de entrada
   de erplora.com (`/shell/`).
2. Inicia sesión o crea la cuenta (el negocio gratuito se crea al registrarse).
3. Con un solo negocio listo, entra solo; con varios, elige uno en «Abre tu hub» (cada tarjeta enseña
   su rol y, si aún se despliega, «Preparando tu hub… esta página se refresca sola»).
4. El SaaS lleva la ventana al negocio con la marca `?shell=1`. La aplicación recuerda **el origen** de
   esa dirección y abre el negocio a pantalla completa, sin barra de direcciones.
5. Cierra y vuelve a abrir: entra directa en el negocio, sin pasar por el SaaS.
Entra: la cuenta del SaaS; la dirección del negocio. Solo se recuerda `<etiqueta>[.<etiqueta>…].erplora.com`
(**incluye `www` y `pre`, que son el SaaS, y cualquier subdominio**; el apex `erplora.com` no) o el bucle local
(`127.0.0.1`/`localhost`, `http` o `https`, **cualquier puerto**), también en la copia de producción.
Sale: el origen en el fichero `hub.url` de la carpeta de datos de la aplicación, y el identificador de
instalación `device.id` la primera vez (HUB_APP-F06). Una sola escritura por cambio. No se guarda
ninguna contraseña ni sesión aquí: la sesión vive en la ventana (almacenamiento del origen del hub).
Si falla: un destino que no es de la plataforma (el marcador viene de un enlace ajeno) **no se
recuerda** y no queda rastro (la aplicación no instala ningún destino para sus registros); un `hub.url` editado a mano o de una versión sin el
filtro se revalida al leerlo y, si no vale, se arranca en el SaaS. Sin red, HUB_APP-F11. Un negocio con
dominio propio no tiene hardware en la aplicación (ver «Qué puede hacer cada página»).
Implicados: pendiente
Pendiente de enlazar: saas — pantalla «Abre tu hub» (`/shell/`, `/shell/open/<id>/`, `?choose=1`) y alta del negocio gratuito
Pendiente de enlazar: hub — HUB_SHELL, Acceso (el hub se abre con una sesión que trae el SaaS)
QA: qa-hub-android Fase 0, qa-hub-android Fase 1

### HUB_APP-F03 Abrir un negocio desde un enlace
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Ventana de ERPlora
Pasos:
1. En el SaaS o en un correo, pulsa «Abrir» en la aplicación (un enlace `erplora://hub/<dirección>`).
2. El sistema pregunta qué abrir: si ERPlora está cerrada, **arranca directa en ese negocio** (gana al
   recordado y al de desarrollo, y no comprueba si el recordado sigue existiendo); si está abierta, la
   misma ventana salta a ese negocio. En ordenador nunca se abre una segunda ventana.
3. El negocio queda recordado como en HUB_APP-F02.
4. Si la aplicación no está instalada, no pasa nada en el sistema: la página que lanzó el enlace espera
   800 ms y lleva el navegador al negocio por https (o a la descarga si la aplicación es obligatoria).
Entra: un enlace con exactamente una pieza tras `hub/`: una dirección `*.erplora.com` (incluidos `www` y `pre`;
mayúsculas o minúsculas) o un bucle local con **cualquier** puerto numérico (`lib.rs:297-304`).
Sale: la ventana en `https://<dirección>/?shell=1`; nada más. La dirección se reconstruye solo desde
el nombre: ni consulta ni fragmento ni parámetros se leen.
Si falla: un enlace que no cuadra (otro dominio, el apex, con usuario, con puerto, con más trozos) no
hace nada, en silencio y a propósito: el que decide qué mostrar es el navegador que lo lanzó. Un
negocio inexistente sí se acepta (se valida la forma, no la existencia). **Cualquier página o correo puede mandar este enlace y cambiar el negocio recordado del mostrador sin
preguntar** (`lib.rs:2086-2098`, `1118-1127`). Un enlace `erplora://notice` no es una navegación: es el
clic en un aviso (HUB_APP-F25).
Implicados: pendiente
Pendiente de enlazar: saas — lanzadera «Abrir terminal» y su enlace visible de reserva
Pendiente de enlazar: hub — HUB_SHELL, Sistema (código QR del menú: abre el negocio por https en otro dispositivo, no la aplicación)
QA: ninguno

### HUB_APP-F04 Cambiar de negocio
Estado: parcial — el aviso dice «Este dispositivo cerrará la sesión de este negocio», pero no se cierra nada: quedan en la ventana la sesión del hub (12 h en dispositivo compartido, hasta 30 días en personal), el nombre y el correo de la persona y sus credenciales de erplora.com; el servidor no revoca la sesión; un enlace `erplora://hub/<el anterior>` vuelve a entrar sin pasar por erplora.com; y en Android sigue encendido el aviso «a la escucha» (leído, sin ejecutar)
Actor: administrador, responsable
Pantalla: HUB_SHELL: Barra superior
Pasos:
1. Dentro de la aplicación (no en un navegador), pulsa el icono «Cambiar de negocio».
2. Lee «¿Cambiar de negocio?» y confirma con «Cambiar» (o «Cancelar», o toca fuera: es un no).
3. La aplicación olvida el negocio recordado y lleva la ventana a la lista de negocios del SaaS
   (`/shell/?choose=1`), que fuerza la lista aunque solo haya uno.
4. Elige otro: se recuerda como en HUB_APP-F02.
Entra: la confirmación de la persona.
Sale: el fichero `hub.url` borrado y nada más (`forget_hub`, `lib.rs:765-780`; `requestChangeHub` no llama a
`logout()`, `change-hub.ts:44-55`, a diferencia del 410, `main.ts:458-462`). Siguen en el almacenamiento del origen del
negocio anterior el token de sesión del hub (`session.ts:29,163`), el usuario con nombre y correo
(`session.ts:24,135`) y los tokens de acceso y refresco de erplora.com (`cloud.ts:101-113`). **Se conserva `device.id`** (ancla de la sesión única por
dispositivo): reasignar una caja a otro local no obliga a desinstalar (en Android, desinstalar lo
destruiría).
Si falla: sin ventana no falla, simplemente no navega. Defecto de seguridad `[SEG]`: ver «Dudas abiertas» y los huecos. Con un solo negocio, sin `?choose=1` el SaaS lo
volvería a abrir al instante; por eso este camino lo lleva.
Implicados: pendiente
Pendiente de enlazar: saas — lista de negocios `?choose=1`
Pendiente de enlazar: hub — HUB_SHELL, Barra superior (control «Cambiar de negocio»)
QA: qa-hub-android Fase 1

### HUB_APP-F05 Olvidar un negocio que ya no existe
Estado: hecho
Actor: sistema
Pantalla: Ventana de ERPlora
Pasos:
1. Al arrancar con un negocio recordado, la ventana ya está abierta en él; en segundo plano la
   aplicación le hace una petición `HEAD` (6 s de plazo).
2. Si contesta 404 o 410 (el negocio se borró), la aplicación olvida `hub.url` y lleva la ventana al
   SaaS. Cualquier otra respuesta —viva, sin sesión, caída— o ningún contacto: lo conserva.
3. Además, si estando dentro el Cloud contesta 410 «negocio no encontrado», el hub pide olvidar
   (`forget_hub` sin lista forzada) y cierra la sesión; como `forget_hub` navega toda la ventana, la persona acaba
   en `/shell/` del SaaS, no en el acceso del hub.
Entra: el `hub.url` y la respuesta del negocio.
Sale: el fichero borrado y la ventana en el SaaS. La asimetría es a propósito: olvidar de más obliga a
rehacer el alta; olvidar de menos deja una pantalla fea que se arregla sola.
Si falla: sin red no olvida nada (HUB_APP-F11). Con un enlace de apertura (HUB_APP-F03) no corre el
chequeo, para no llevarse por delante lo que se acaba de pedir. Se ve el 404 un instante antes del
SaaS.
Implicados: pendiente
Pendiente de enlazar: saas — borrado de un negocio (purga) que provoca el 404/410
QA: qa-hub-android Fase 1

### HUB_APP-F06 Saber qué equipo es este
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al iniciar sesión, el hub pregunta a la aplicación quién es.
2. La aplicación contesta un identificador único de esta instalación (lo crea la primera vez y lo guarda
   fuera de la ventana, así que sobrevive a limpiar los datos del navegador integrado), el tipo de
   cliente (`hub-desktop` en ordenador, `hub-mobile` en Android; pero la página lo convierte en `hub-desktop`
   antes de mandarlo, `device.ts:231`, y el SaaS distingue la tablet solo por la plataforma), el sistema (windows, macos, linux,
   android) y el canal (`play`, `msstore`, `direct`).
Entra: nada; lee su carpeta de datos.
Sale: `X-Device-Id`, tipo y plataforma, que el hub usa para la sesión única por dispositivo y para el modo
compartido/personal. Sobrevive a cerrar sesión y a cambiar de negocio; se pierde al desinstalar (en
Android) o al borrar la carpeta de datos.
Si falla: si no puede crear su carpeta de datos, devuelve error y la página usa el identificador que el
navegador integrado se acuña y guarda en el origen (`browserDeviceId`), que se pierde al limpiar los datos de
la ventana. Un origen sin juego `default` ni
`onboarding` ni siquiera puede preguntar (ver «Qué puede hacer cada página»).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F137 (perder la sesión por abrirla en otro dispositivo) y HUB-F139 (dispositivo compartido o personal)
QA: qa-hub-android Fase 0

### HUB_APP-F10 Cada página tiene su juego de permisos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada vez que la ventana enseña una página, Tauri comprueba el origen contra los tres juegos de «Qué
   puede hacer cada página».
2. Una orden nativa desde un origen que no la tiene concedida se rechaza antes de ejecutarse.
3. El negocio recordado y la lista de destinos de un enlace salen de una regla parecida pero **no idéntica** a la de
   los juegos: se recuerda el bucle local con cualquier puerto y `https` sobre bucle local (`lib.rs:617-619`), que
   el juego `default` no autoriza (solo `:8787` y `:5173`): puede quedar recordado un origen que no imprime.
Entra: el origen de la página.
Sale: órdenes aceptadas o rechazadas; nada guardado.
Si falla: un origen fuera de la plataforma no puede pedir `device_context`; el apex no puede tocar el
hardware; y la orden de reintentar de la pantalla de espera solo existe para la página incluida (un
origen remoto no puede mover la ventana). Una orden declarada y sin permiso generado la caza el test `tests/shell_surface.rs:247-300`; una orden no
concedida se rechaza en ejecución.
Implicados: ninguno
QA: ninguno

### HUB_APP-F11 Cuando no hay conexión con el negocio
Estado: hecho
Actor: sistema, administrador, responsable, empleado
Pantalla: Sin conexión a internet
Pasos:
1. Un vigilante de la aplicación comprueba la red: a los 3 s del arranque, en cada navegación a una
   página remota y, mientras todo va bien, **nunca más** (duerme sin temporizador).
2. La comprobación es un `HEAD` a la raíz del origen de la página (6 s de plazo). Cuenta **cualquier
   respuesta** como red viva, aunque sea 404 o 502; solo un fallo de transporte (DNS, conexión, plazo)
   cuenta como caída.
3. Con **dos** fallos seguidos (entre 2 y 14 s: 2 s de espera más el plazo de cada sondeo) la ventana pasa a «Sin conexión a internet»; uno solo no, porque
   un cambio de wifi o un portal cautivo se ven igual.
4. Mientras la pantalla de espera está puesta, la aplicación vuelve a comprobar a los 4, 8 y 16 s y
   después cada 30 s (`connectivity.rs:93-100`); en cuanto contesta, **devuelve sola la ventana** a donde estaba.
5. «Reintentar» comprueba ya: si hay red, la ventana vuelve; si no, «Sigue sin conexión…».
Entra: el último origen al que fue la ventana.
Sale: la ventana en la pantalla de espera o de vuelta; sin datos guardados.
Si falla: si no puede construir la comprobación se queda en la pantalla de espera sin dejar rastro del motivo. Con red pero con el servidor del negocio caído y el borde contestando, no hay pantalla
de espera (es lo que el borde sirva). No es la franja «sin conexión» de dentro del hub (eso lo pinta el
hub, `HUB_SHELL`).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (franja sin conexión y pantalla «no se puede conectar» del arranque del hub)
QA: qa-hub-android Fase 4

### HUB_APP-F12 En la copia de Google Play, solo páginas del SaaS que no cobran
Estado: parcial — los cambios de página por dentro del panel del SaaS (htmx) y lo que se abre en el navegador del sistema no pasan por la lista (ERPlora/hub#1918, abierta)
Actor: sistema
Pantalla: Aviso «Esta página no está disponible en la aplicación.»
Pasos:
1. Solo la copia de Google Play. Antes de seguir cualquier página de erplora.com (el apex, `www` y
   `pre`), la aplicación comprueba una lista corta: entrar, registrarse, el alta de correo y contraseña,
   la entrada a un negocio, la cuenta y lo legal.
2. Una página que no está en la lista (precios, el panel con facturación, el mercado público) **no se
   carga**: la ventana se queda donde estaba y sale el aviso.
3. La portada del SaaS (`/`) lleva al inicio de la propia aplicación en vez de enseñarse.
Entra: la dirección a la que va la ventana.
Sale: nada guardado (la aplicación anota el origen y la ruta, nunca la consulta, pero no hay destino para ese
registro).
Si falla: el aviso va en español o inglés según el dispositivo. El aviso **no nombra otro sitio al que
ir** (hacerlo sería lo que Play prohíbe). Los negocios, la pantalla de impresión y el resto de copias
(Store, instalador) siguen todo como antes.
Implicados: pendiente
Pendiente de enlazar: saas — páginas del SaaS dentro de la aplicación (marca «en la aplicación», sin puertas web)
QA: qa-hub-android Fase 4
