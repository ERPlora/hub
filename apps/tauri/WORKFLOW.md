# WORKFLOW — La aplicación instalada (ERPlora para Windows, macOS y Android)

Prefijo: HUB_APP
Alcance MVP: transversal

> Contrato de comportamiento de `apps/tauri` y, por referencia, de `crates/tauri-plugin-erplora-android`
> (el Kotlin de Android: permisos, Bluetooth, NFC, aviso permanente, guardar y imprimir). Contrastado
> contra `origin/develop` del hub el 05/10/2026. Todo lo que aquí se afirma está **leído en el código,
> sin ejecutar**: no se ha instalado la aplicación ni tocado ningún emulador. Lo técnico vive en
> `architecture/hub/apps/tauri.md`; el protocolo de la impresora, en `crates/peripherals/WORKFLOW.md`
> (`HUB_PERIPHERALS`); lo que el servidor hace con la cola, en `WORKFLOW.md` de la raíz (`HUB`, área
> Impresión); lo que se ve en las pantallas del hub, en `apps/web/WORKFLOW.md` (`HUB_SHELL`).

## Para qué sirve y para quién

La aplicación instalada es una **ventana con permiso para tocar el hardware**. No lleva el negocio
dentro: abre `erplora.com` la primera vez y, una vez elegido el negocio, abre el hub de ese negocio
a pantalla completa en cada arranque (el hub lo sirve su servidor, no el instalador). Existe por lo
que un navegador no puede hacer: sacar papel por una impresora térmica, abrir el cajón, leer una
tarjeta NFC, avisar con el sistema operativo, arrancar con el ordenador y abrir ficheros o enlaces
fuera de la ventana. La usan el **administrador** y el **responsable** (la instalan, enlazan el negocio
y montan las impresoras) y, sin saberlo, el **cajero**, la **camarera** y el **empleado** cada vez que
cobran, disparan una comanda o pasan la placa.

Gobierna `apps/tauri/` y, **por referencia**, `crates/tauri-plugin-erplora-android/` (sus comandos y su
Kotlin son la mitad Android de los flujos de aquí). No gobierna `crates/peripherals` (qué bytes salen
por la impresora: `HUB_PERIPHERALS`), ni el servidor del hub, ni lo que las pantallas del hub pintan.
Hay un solo binario por sistema bajo una sola identidad, `com.erplora.app`.

## Referencia adoptada

No se rehace: la de impresión y hardware está contrastada en `.claude/qa/qa-hub.md` §8 y la de la app
de Android en `.claude/agents/qa-hub-android.md`. Se adopta solo esto (los nombres de productos son los
que citan los comentarios del código; **no se han vuelto a contrastar con el mercado en esta ronda**):

- **Montar el puesto como Square, Toast, Lightspeed o Shopify POS**: la impresora se encuentra sola o
  se añade por su IP, se prueba con una hoja y se le da una función (Recibo, Cocina, Barra, Etiqueta).
- **Explicar antes de pedir un permiso** (guía de Android y práctica de los TPV): una frase nuestra
  primero y el diálogo del sistema después, una sola vez; la respuesta «ahora no» no se vuelve a pedir
  sola.
- **Seguir a la escucha con la pantalla apagada** como las aplicaciones de pedidos para comercios
  (Uber Eats Orders, Glovo Partners, Deliveroo Restaurant Hub): servicio en primer plano con su aviso
  permanente. **No hay push** (decisión vigente, ERPlora/hub#2307, cerrada).
- **Atrás cierra lo de encima antes de salir** (Square, Loyverse) y **un aviso abre lo que sonó**
  (Square, Shopify Inbox, Zendesk).
- **Cobrar fuera de la aplicación**: las compras se hacen en el navegador del sistema (ADR-0114 §4),
  porque Google Play no permite pagar bienes digitales dentro; la copia de Play además se niega a
  seguir páginas del SaaS que cobran.
- **Actualizar por la tienda**: Play y Microsoft Store actualizan sus instalaciones; el resto recibe un
  aviso con la descarga.

## Antes de empezar

- Una **cuenta de ERPlora** y un negocio (el gratuito se crea al registrarse) y **conexión a internet**:
  la aplicación no funciona sin red; con la red caída solo enseña una pantalla de espera (HUB_APP-F11).
- **Sistemas**: Windows 10 1809 o posterior, 64 bits, con WebView2 (Windows 10/11 al día lo traen);
  Android 7 (API 24) o posterior, compilada para Android 16 (API 36); macOS en Apple Silicon.
  También se construyen para Linux (`.deb`, AppImage) pero no es un sistema anunciado (Dudas abiertas).
  iOS está en el código pero no se construye ni se publica.
- Para imprimir: una **impresora térmica ESC/POS** encendida, en la misma red (puerto 9100), por USB
  en un ordenador macOS o Linux, o emparejada por Bluetooth en Android. La configuración paso a paso
  de las impresoras es la de Impresión (`PRINTING`, «Configuración inicial»); aquí cambia lo que pasa
  por debajo.
- Para NFC: una tableta o móvil Android con lector y el NFC encendido; en un ordenador, un lector USB
  que escribe como teclado (no es de esta aplicación).
- En **Android 17**, el permiso de red local; en **macOS 15**, el de red local; en Android 13 o
  posterior, el de notificaciones; en Android 12 o posterior, el de Bluetooth (HUB_APP-F07, F09).

## Pantallas

La aplicación tiene muy pocas pantallas **propias**; casi todo lo que se ve lo pinta el hub o el SaaS
dentro de su ventana. Cada flujo dice cuál es.

### Ventana de ERPlora
La ventana principal (`main`): 1280×800, mínimo 960×600, titulada «ERPlora», sin barra de direcciones
ni botón de recargar. Carga `erplora.com/shell/` si no recuerda ningún negocio o el hub recordado si
lo hay. Si la dirección inicial es ilegible carga la pantalla «Sin conexión a internet». Una sola por
instalación en ordenador (una segunda apertura entrega sus argumentos a la ya abierta).

### Sin conexión a internet
Página incluida en la propia aplicación, con la marca. Título «Sin conexión a internet»; texto «ERPlora
no puede conectar con tu negocio ahora mismo. Es un problema de conexión, no es un fallo de la
aplicación: no se ha perdido nada de lo que guardaste.»; consejo «Comprueba el wifi o los datos móviles.
ERPlora vuelve a conectarse solo en cuanto haya red.»; botón «Reintentar»; línea de estado «Comprobando
la conexión…» o «Sigue sin conexión. Comprueba el wifi o los datos móviles.». Va en español, o en
inglés si el dispositivo no está en español. Vacía/cargando/error: es ella misma el estado de error de red.

### Aviso «Esta página no está disponible en la aplicación.»
Un diálogo del sistema (`alert`) que sale encima de la página en la que se queda la ventana cuando la
copia de Google Play se niega a seguir una página del SaaS. Mismo idioma que la página anterior.

### Ventana de impresión
Solo en ordenador: una ventana de 820×1060 titulada «ERPlora» que enseña el documento A4 y abre el
diálogo de impresión del sistema (lista de impresoras y «Guardar como PDF»). En Android es la pantalla
de impresión del propio Android.

### Pedir permiso
Los diálogos del sistema operativo (red local, notificaciones, Bluetooth), precedidos por la frase del
hub («Vamos a buscar tu impresora», «Deja que te avisemos»). Los textos son de `HUB_SHELL`.

### Aviso del sistema
La notificación del sistema (Windows, macOS, Linux, Android) con título y cuerpo. Y, en Android, la
notificación permanente «ERPlora está a la escucha» («Te avisará cuando algo necesite tu atención, aunque
la pantalla esté apagada.»; canal «Avisos con la pantalla apagada»), silenciosa y que no se puede quitar
mientras dura.

### Pantallas de otros que esta aplicación usa
`saas: Abre tu hub` (la lista de negocios de `/shell/`) · `printing: Impresoras` (buscar, añadir, probar,
función) · `HUB_SHELL: Sistema` (tarjeta de impresión, avisos, aviso de actualización) · `HUB_SHELL:
Ajustes` (Hub › «Arrancar al iniciar sesión») · `HUB_SHELL: Barra superior` («Cambiar de negocio»).

## Qué puede hacer cada página (los tres juegos de permisos)

La aplicación no «cambia de modo»: **Tauri decide por el origen de la página que enseña la ventana**
qué órdenes nativas acepta. Hay tres juegos (`capabilities/*.json`), todos para la ventana `main`.
Cualquier otra ventana (la de impresión) no tiene ninguno.

| Juego | Se aplica a | Puede | No puede |
|---|---|---|---|
| `default` | `https://*.erplora.com/*` (cualquier negocio, cualquier «aura»), `127.0.0.1:8787` y `:5173` (desarrollo) **y la página incluida en la aplicación** | Todo el hardware (buscar, añadir, probar, imprimir, cajón, funciones, nombres, quitar), `device_context`, `forget_hub`, abrir enlace externo, guardar descarga, imprimir A4, avisos del sistema, reclamar el toque de un aviso, NFC, arranque automático, `core:default` (incluye la versión de la aplicación) y los permisos de Android | Las órdenes crudas del plugin de abrir ficheros; navegar la ventana |
| `onboarding` | `https://erplora.com/*` (el apex, el SaaS) y `127.0.0.1:8001` (desarrollo) | Solo `device_context` (identidad para iniciar sesión) y `forget_hub` | Todo el hardware, abrir enlaces, guardar, imprimir, avisos, NFC, permisos de Android, versión |
| `degraded` | Solo la página incluida en la aplicación (sin `remote`) | Añade solo `shell_retry` (comprobar la red y mover la ventana) | Nada más propio; hereda de `default` lo que ya tiene esa página |

Consecuencias: el apex **no puede abrir el cajón** aunque lo inyecten; una página de otro dominio
(dominio propio del negocio, un enlace externo cargado en la ventana) **no puede ni pedir su identidad**,
así que parece funcionar y no imprime. El SaaS usa para el alta el `app_access_url` (dirección de la
plataforma, no el dominio propio) precisamente por esto (hub#448, cerrada).

## Flujos

### HUB_APP-F01 Instalar la aplicación
Estado: parcial — la publicación en Google Play y en Microsoft Store no está confirmada hoy (GOOGLE-PLAY.md, 19/08/2026: nunca enviada a revisión; la ficha da 404 hasta que Producción esté en vivo); el `.dmg` de macOS se construye pero el hub no ofrece descarga para macOS ni está notarizado
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
Sale: la aplicación `com.erplora.app` con su versión (la de `tauri.conf.json`, hoy 1.0.1) y su canal
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
Entra: la cuenta del SaaS; la dirección del negocio, que solo se recuerda si es de la plataforma
(`<etiqueta>[.<etiqueta>…].erplora.com`, nunca el apex) o un bucle local de desarrollo.
Sale: el origen en el fichero `hub.url` de la carpeta de datos de la aplicación, y el identificador de
instalación `device.id` la primera vez (HUB_APP-F06). Una sola escritura por cambio. No se guarda
ninguna contraseña ni sesión aquí: la sesión vive en la ventana (almacenamiento del origen del hub).
Si falla: un destino que no es de la plataforma (el marcador viene de un enlace ajeno) **no se
recuerda** y se avisa solo en el registro técnico; un `hub.url` editado a mano o de una versión sin el
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
Entra: un enlace con exactamente una pieza tras `hub/`: la dirección de un negocio de la plataforma
(mayúsculas o minúsculas) o un bucle local con puerto numérico.
Sale: la ventana en `https://<dirección>/?shell=1`; nada más. La dirección se reconstruye solo desde
el nombre: ni consulta ni fragmento ni parámetros se leen.
Si falla: un enlace que no cuadra (otro dominio, el apex, con usuario, con puerto, con más trozos) no
hace nada, en silencio y a propósito: el que decide qué mostrar es el navegador que lo lanzó. Un
negocio inexistente sí se acepta (se valida la forma, no la existencia). Un enlace `erplora://notice`
no es una navegación: es el clic en un aviso (HUB_APP-F25).
Implicados: pendiente
Pendiente de enlazar: saas — lanzadera «Abrir terminal» y su enlace visible de reserva
Pendiente de enlazar: hub — HUB_SHELL, Sistema (código QR del menú: abre el negocio por https en otro dispositivo, no la aplicación)
QA: ninguno

### HUB_APP-F04 Cambiar de negocio
Estado: parcial — el aviso dice «Este dispositivo cerrará la sesión de este negocio», pero ni la aplicación ni la pantalla cierran la sesión ni borran los datos de la ventana: la sesión del hub anterior sigue en el almacenamiento de su origen hasta que caduque (leído, sin ejecutar)
Actor: administrador, responsable
Pantalla: HUB_SHELL: Barra superior
Pasos:
1. Dentro de la aplicación (no en un navegador), pulsa el icono «Cambiar de negocio».
2. Lee «¿Cambiar de negocio?» y confirma con «Cambiar» (o «Cancelar», o toca fuera: es un no).
3. La aplicación olvida el negocio recordado y lleva la ventana a la lista de negocios del SaaS
   (`/shell/?choose=1`), que fuerza la lista aunque solo haya uno.
4. Elige otro: se recuerda como en HUB_APP-F02.
Entra: la confirmación de la persona.
Sale: el fichero `hub.url` borrado. **Se conserva `device.id`** (ancla de la sesión única por
dispositivo): reasignar una caja a otro local no obliga a desinstalar (en Android, desinstalar lo
destruiría).
Si falla: sin ventana no falla, simplemente no navega. Con un solo negocio, sin `?choose=1` el SaaS lo
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
   (`forget_hub` sin lista forzada), cierra la sesión y lleva al acceso.
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
   cliente (`hub-desktop` en ordenador, `hub-mobile` en Android), el sistema (windows, macos, linux,
   android) y el canal (`play`, `msstore`, `direct`).
Entra: nada; lee su carpeta de datos.
Sale: `X-Device-Id`, tipo y plataforma, que el hub usa para la sesión única por dispositivo y para el modo
compartido/personal. Sobrevive a cerrar sesión y a cambiar de negocio; se pierde al desinstalar (en
Android) o al borrar la carpeta de datos.
Si falla: si no puede crear su carpeta de datos, devuelve error y el inicio de sesión sigue sin
identidad (el hub trata un cliente sin identidad como compartido). Un origen sin juego `default` ni
`onboarding` ni siquiera puede preguntar (ver «Qué puede hacer cada página»).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F137 (perder la sesión por abrirla en otro dispositivo) y HUB-F139 (dispositivo compartido o personal)
QA: qa-hub-android Fase 0

### HUB_APP-F07 Android pide los permisos en su momento
Estado: parcial — la frase previa solo existe para la red local y los avisos; el permiso de Bluetooth sale en el mismo diálogo de «dispositivos cercanos» que la red local, sin frase propia
Actor: administrador, responsable, empleado
Pantalla: Pedir permiso
Pasos:
1. Solo en Android. La persona hace algo que necesita un permiso: buscar impresoras, imprimir, añadir
   una impresora por IP (red local y Bluetooth), o dar de alta el puesto de impresión / abrir la primera
   comanda o cita (notificaciones).
2. El hub enseña **antes** una frase suya: «Vamos a buscar tu impresora» / «Deja que te avisemos», con
   «Ahora no» y el botón de permitir.
3. Si acepta, Android enseña su diálogo, **uno solo** aunque la operación necesite varios permisos
   (red local y Bluetooth viajan juntos); si dice «ahora no», no se vuelve a pedir sola.
4. La aplicación solo pide lo que la operación va a usar (el cajón y el tique piden red local o
   Bluetooth según el identificador de la impresora; los avisos, notificaciones).
Entra: la operación y la lista de permisos que Android conoce en esta versión: notificaciones desde la 13
(API 33), Bluetooth desde la 12 (API 31), red local desde la 17 (API 37). En versiones anteriores no se
pide lo que no existe (en algunos fabricantes colgaría el diálogo).
Sale: el estado real de cada permiso; un «no» **se contesta, no se rechaza**: sin impresora el TPV tiene
que seguir vendiendo. El NFC y el servicio en primer plano son permisos de instalación: no hay diálogo.
Si falla: sin el permiso de red local el barrido y el envío a la red son tiempos de espera, no errores
(Android los bloquea por debajo de la API): sin protección parecería «no hay impresoras» (HUB_APP-F13).
Después de dos «no» Android deja de mostrar el diálogo para siempre: la salida es HUB_APP-F08.
Implicados: PRINTING-F02
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (la frase previa y el permiso de notificaciones)
QA: qa-hub-android Fase 2, qa-hub-android Fase 3

### HUB_APP-F08 Volver a activar un permiso negado
Estado: hecho
Actor: administrador, responsable
Pantalla: HUB_SHELL: Sistema
Pasos:
1. Con la red local o los avisos negados, la pantalla lo dice («La búsqueda de impresoras está
   bloqueada» / «Los avisos están desactivados») y ofrece «Permitir la búsqueda» / «Activar los avisos».
2. Si Android aún deja preguntar, vuelve a salir el diálogo.
3. Si ya no, la pantalla ofrece «Abrir los ajustes»: la aplicación abre **su** página en los ajustes del
   sistema; la persona activa el permiso y vuelve.
Entra: el estado de los permisos (`check_permissions`, sin molestar).
Sale: la aplicación abierta en los ajustes; nada guardado.
Si falla: un dispositivo sin esa página (modo quiosco) o una aplicación más antigua que la orden rechaza,
y la pantalla dice dónde ir en vez de quedarse muda («Tu dispositivo no ha vuelto a preguntar. Abre sus
ajustes, busca ERPlora y concédele el acceso a la red local.»). En ordenador no hay estado: la ausencia
del permiso se lee como «no aplica», nunca como «negado».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Sistema (tarjeta de impresión y fila de avisos desactivados)
QA: qa-hub-android Fase 2

### HUB_APP-F09 Red local en ordenador (macOS y Windows)
Estado: parcial — en macOS 15 la aplicación no puede saber si el permiso se negó: la búsqueda vuelve vacía y la pantalla dice «No se ha encontrado ninguna impresora» en vez de «dale permiso a la app»
Actor: administrador, responsable
Pantalla: printing: Impresoras
Pasos:
1. **macOS 15 o posterior**: la primera vez que la aplicación habla con una impresora de la red local,
   el sistema pregunta con el motivo que declara la aplicación («ERPlora needs access to your local
   network to find and print to the receipt and kitchen printers in your business.»). La aplicación declara
   los dos servicios que busca (`_pdl-datastream._tcp`, `_ipp._tcp`).
2. Sin respuesta afirmativa, las conexiones expiran en silencio.
3. **Windows**: el paquete de la Store declara acceso a internet y a la red privada; el instalador
   normal no pide nada.
Entra: la respuesta de la persona al sistema.
Sale: nada guardado por la aplicación; el sistema recuerda la respuesta.
Si falla: negado en macOS, la búsqueda no encuentra nada y no hay señal que lo distinga de «no hay
impresoras». Se arregla en Ajustes del sistema › Privacidad › Red local.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_PERIPHERALS-F01 (búsqueda de impresoras)
QA: ninguno

### HUB_APP-F10 Cada página tiene su juego de permisos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada vez que la ventana enseña una página, Tauri comprueba el origen contra los tres juegos de «Qué
   puede hacer cada página».
2. Una orden nativa desde un origen que no la tiene concedida se rechaza antes de ejecutarse.
3. El negocio recordado y la lista de destinos de un enlace salen de la **misma regla** que los juegos:
   así nunca se recuerda un origen que luego no podría imprimir, ni se autoriza uno que no se recuerda.
Entra: el origen de la página.
Sale: órdenes aceptadas o rechazadas; nada guardado.
Si falla: un origen fuera de la plataforma no puede pedir `device_context`; el apex no puede tocar el
hardware; y la orden de reintentar de la pantalla de espera solo existe para la página incluida (un
origen remoto no puede mover la ventana). Una orden nueva sin permiso generado rompe la compilación.
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
3. Con **dos** fallos seguidos (unos 5 s) la ventana pasa a «Sin conexión a internet»; uno solo no, porque
   un cambio de wifi o un portal cautivo se ven igual.
4. Mientras la pantalla de espera está puesta, la aplicación vuelve a comprobar cada 2, 4, 8 y 16 s y
   después cada 30 s; en cuanto contesta, **devuelve sola la ventana** a donde estaba.
5. «Reintentar» comprueba ya: si hay red, la ventana vuelve; si no, «Sigue sin conexión…».
Entra: el último origen al que fue la ventana.
Sale: la ventana en la pantalla de espera o de vuelta; sin datos guardados.
Si falla: si no puede construir la comprobación se queda en la pantalla de espera con el error en el
registro técnico. Con red pero con el servidor del negocio caído y el borde contestando, no hay pantalla
de espera (es lo que el borde sirva). No es la franja «sin conexión» de dentro del hub (eso lo pinta el
hub, `HUB_SHELL`).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (franja sin conexión y pantalla «no se puede conectar» del arranque del hub)
QA: qa-hub-android Fase 4

### HUB_APP-F12 En la copia de Google Play, solo páginas del SaaS que no cobran
Estado: hecho
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
Sale: nada guardado; en el registro técnico, el origen y la ruta, nunca la consulta (puede llevar un
código de un solo uso).
Si falla: el aviso va en español o inglés según el dispositivo. El aviso **no nombra otro sitio al que
ir** (hacerlo sería lo que Play prohíbe). Los negocios, la pantalla de impresión y el resto de copias
(Store, instalador) siguen todo como antes.
Implicados: pendiente
Pendiente de enlazar: saas — páginas del SaaS dentro de la aplicación (marca «en la aplicación», sin puertas web)
QA: qa-hub-android Fase 4

### HUB_APP-F13 Buscar impresoras
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. Abre **Impresión › Impresoras**: la búsqueda arranca sola; «Re-escanear» la repite.
2. En Android, antes se pide el permiso de red local y el de Bluetooth juntos (HUB_APP-F07).
3. La aplicación junta **una sola lista** de cuatro orígenes: la red (mDNS y barrido del 9100), las
   Bluetooth ya emparejadas (solo Android), las colas USB del sistema (solo ordenador) y las que la
   persona escribió a mano (HUB_APP-F14), sin repetir ninguna.
4. Cada una queda en el registro de esta aplicación para poder darle función.
Entra: la red del dispositivo; en Android, la lista de emparejados de Android.
Sale: la lista de impresoras (red `network:<ip>:<puerto>`, Bluetooth `bluetooth:<mac>`, USB `usb:<cola>`).
Las Bluetooth salen siempre sin clasificar: se ofrecen las emparejadas cuyo nombre o clase parecen
impresora. Un fallo de Bluetooth o de CUPS **no estropea** la mitad de red: se anota y la red sigue.
Si falla: sin permiso de red local la búsqueda **no se hace** y devuelve «bloqueada» en vez de una lista
vacía: «ERPlora no ha podido buscar en esta red: el sistema no le ha dado permiso…». Con permiso y sin
nada: «No se ha encontrado ninguna impresora en esta red…» (lo dicho en HUB_APP-F09 para macOS). En el
emulador de Android el barrido recorre la red del emulador y no encuentra nada: no es un defecto (QA).
Desde un navegador: «Desde el navegador, este dispositivo no puede llegar a las impresoras…».
Implicados: PRINTING-F02
Pendiente de enlazar: hub — HUB_PERIPHERALS-F01 (cómo se busca) y HUB-F196 (alta del dispositivo y búsqueda)
QA: qa-hub §8, qa-hub-android Fase 3

### HUB_APP-F14 Añadir una impresora por su IP
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. Pulsa «Añadir impresora por IP» (solo se ofrece en la aplicación instalada).
2. Escribe la dirección IPv4 de la hoja de configuración de la impresora y el puerto (9100).
3. Pulsa «Añadir y probar»: la aplicación se conecta (3 s de plazo) y **solo si contesta** la guarda.
4. Sale en la lista y la hoja de prueba sale por ella (HUB_APP-F20).
Entra: `host` y `puerto`; en Android antes se asegura el permiso de red local.
Sale: la impresora marcada «escrita a mano»: las siguientes búsquedas la siguen listando aunque el barrido
no la vea (otra subred, wifi aislada, mDNS bloqueado).
Si falla: la orden contesta un **código estable** además del texto para que la pantalla distinga lo que
escribió mal (`invalid_printer_address`: «La dirección no es válida…») de una impresora que no contestó
(`printer_unreachable`: «Ninguna impresora ha respondido en {dirección}…»); una aplicación más antigua
que la orden da «No se pudo añadir la impresora. Actualiza la app…». Contestar en el 9100 no prueba que
sea térmica: una láser de oficina también contesta.
Implicados: PRINTING-F03
Pendiente de enlazar: hub — HUB_PERIPHERALS-F02 (cómo se comprueba la dirección)
QA: qa-hub-android Fase 3

### HUB_APP-F15 Impresora Bluetooth (solo Android)
Estado: parcial — no hay forma de emparejar desde ERPlora (se empareja en los ajustes de Android); el nombre y la función de una Bluetooth no se vigilan y, apagada, solo se sabe al imprimir
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. Empareja la impresora en los **ajustes de Bluetooth de Android** (la aplicación no escanea ni empareja,
   para no pedir el permiso de escaneo ni tocar el PIN).
2. En **Impresión › Impresoras** aparece en la lista (HUB_APP-F13) con el nombre del emparejamiento o
   «Bluetooth (MAC)». Dale función y pruébala.
3. Imprimir abre la conexión **en cada trabajo** y la cierra al acabar (no la mantiene).
Entra: el emparejamiento de Android y el permiso de Bluetooth.
Sale: los bytes por el canal serie (SPP). A diferencia de la red, **el resultado vuelve de verdad**: la
orden no contesta hasta que los bytes se han escrito o el intento ha fallado.
Si falla: Bluetooth apagado o sin permiso, o impresora fuera de alcance/apagada: la orden rechaza con el
motivo («impresora inalcanzable: …» o `bluetooth_permission_denied`) y la persona lo ve en la hoja de
prueba y el hub marca el trabajo como fallido para reintentar. El conectar puede tardar segundos; la
orden no deja la pantalla colgada porque corre fuera del hilo principal.
Implicados: PRINTING-F02, PRINTING-F05
Pendiente de enlazar: hub — HUB_PERIPHERALS-F06 (envío de un documento) y HUB_PERIPHERALS-F14 (hoja de prueba)
QA: qa-hub-android Pendiente (Bluetooth SPP, fase C)

### HUB_APP-F16 Impresora USB (solo ordenador)
Estado: parcial — una USB se ve, se nombra y se prueba, pero no recibe tiques, comandas, trabajos de la cola ni el cajón al cobrar; en Windows no existe (ERPlora/hub#1269)
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. En macOS o Linux con la impresora puesta y su controlador instalado, **Impresión › Impresoras**
   la muestra con el nombre de la cola del sistema.
2. Dale nombre o función; «Probar» manda la hoja por la cola RAW del sistema.
3. Un tique, una comanda o un trabajo de la cola **no llegan a ella**: la puerta de impresión y el
   alta del puesto solo reconocen impresoras con dirección de red o Bluetooth con MAC
   (`apps/web/src/lib/print.ts:199-202`); una USB entra en el registro con dirección vacía
   (`crates/peripherals/src/registry.rs:259-273`).
4. En Android no hay cola del sistema: un identificador `usb:` falla con «impresora inalcanzable… usa una
   de red o una Bluetooth emparejada».
Entra: el identificador `usb:<cola>`.
Sale: solo la hoja de prueba y la orden directa; con las colas CUPS la aplicación comprueba el estado
antes de enviar y cancela a los 15 s lo que no sale (`HUB_PERIPHERALS-F07`).
Si falla: en Windows no se listan colas (no hay `lp`): una impresora USB de Windows se usa por red.
Implicados: PRINTING-F02
Pendiente de enlazar: hub — HUB_PERIPHERALS-F03, F07 y F08
QA: qa-hub §8

### HUB_APP-F17 Dar nombre y función a una impresora, y quitarla
Estado: parcial — un nombre puesto a mano lo pisa la siguiente búsqueda; quitar la función o borrar la impresora aquí no da de baja al dispositivo en el hub; no hay ninguna pantalla que llame a renombrar ni a quitar
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. En la tarjeta de la impresora elige una función en el desplegable «Rol» (Recibo, Cocina, Barra,
   Etiqueta): la aplicación la guarda en el registro del dispositivo (`devices.json`, en su carpeta de
   datos) y devuelve el registro entero.
2. La orden de **renombrar** cambia el nombre y la de **quitar** borra la entrada; ambas devuelven el
   registro actualizado.
3. En el siguiente arranque, si el dispositivo tiene una única impresora y ninguna función en todo el
   registro, la aplicación le pone «Recibo» sola (lo hace la pantalla al arrancar, no la aplicación).
Entra: la clave de la impresora (MAC o identificador) y el valor; la función `receipt`, `kitchen`, `bar` o
`label`.
Sale: el registro de **este dispositivo**; el hub lo sabe solo cuando el puesto se da de alta (HUB_APP-F18).
Si falla: una impresora que el registro no tiene («escanea otra vez»). **Un nombre puesto a mano lo
sobrescribe la siguiente búsqueda** del mismo equipo (`crates/peripherals/src/registry.rs:300-310`,
`existing.name = name`). Quitar la entrada del registro no retira al dispositivo del hub ni la función
queda sin dar de baja: el dispositivo se vuelve a dar de alta solo mientras tenga otra función, y una
función ya anunciada no se retira (`HUB-F197`). No existe la acción «dejar sin función». La orden de
renombrar y la de quitar existen y están concedidas, pero ninguna pantalla del hub ni del módulo las llama
(sin confirmar en ejecución).
Implicados: PRINTING-F04
Pendiente de enlazar: hub — HUB_PERIPHERALS-F04 (registro) y HUB-F196/F197 (alta y retirada del puesto en el hub)
QA: qa-hub §8

### HUB_APP-F18 Ser el puesto que imprime
Estado: parcial — el puesto solo imprime mientras la ventana está viva (no hay icono de bandeja ni nada que la mantenga al cerrarla) y, en Android, mientras el sistema no la congele (HUB_APP-F26 solo lo evita si hay algo que avisar y los avisos no están negados); una función quitada en el hub no la retira este puesto
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al abrir el hub dentro de la aplicación, la página pregunta a la aplicación si hay hardware
   (`erplora_bridge_status`: contesta con la versión de la aplicación, la de `tauri.conf.json`).
2. Si lo hay, la página lee el registro de impresoras de la aplicación y, si hay una sola impresora
   alcanzable y ninguna función, le pone «Recibo».
3. La página da de alta este equipo en el hub como puesto de las funciones de sus impresoras alcanzables
   y abre el canal en vivo de la cola; cada trabajo que el hub le entrega se lo pasa a la aplicación
   (HUB_APP-F19).
4. Si la ventana se cierra, el canal se cae con ella; el hub da el puesto por muerto a los 90 s.
Entra: el registro de la aplicación y la sesión del hub.
Sale: la aplicación aporta la lista, la versión y la orden de imprimir; la cola, las funciones y la
reconexión son del hub y de la página.
Si falla: un navegador sin aplicación no es puesto. Una USB no cuenta como alcanzable (HUB_APP-F16). Lo
que la aplicación no hace es avisar al hub de que una impresora se apagó (el vigilante solo escribe en
su registro técnico, `crates/peripherals`).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F196 (alta del dispositivo y búsqueda), HUB-F197 (mantener vivo) y HUB-F198 (canal en vivo y reconexión)
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (arranque del puesto)
QA: qa-hub §8

### HUB_APP-F19 Imprimir un tique, una factura o una comanda
Estado: parcial — con una impresora de red, la aplicación contesta «correcto» al ponerlo en una cola en memoria y nadie se entera de si salió (ERPlora/hub#2494)
Actor: sistema, cajero, empleado
Pantalla: ninguna
Pasos:
1. Una venta cobrada, una comanda disparada o un trabajo de la cola llegan a la aplicación con la
   impresora de su función, el tipo de documento y el documento estructurado.
2. La aplicación comprueba el identificador, que el tipo es uno de los ocho conocidos y que el documento
   se puede componer; si no, **rechaza ya** y el error vuelve a quien pidió el papel.
3. **Red**: pone los bytes en una cola interna en memoria y contesta «correcto» (`erplora_print`,
   `apps/tauri/src-tauri/src/lib.rs:1671-1683`). Un único trabajador la vacía: 3 intentos, 3 s para
   conectar, 10 s para escribir, 2 s entre intentos.
4. **Bluetooth**: manda los bytes por el canal serie y contesta cuando se han escrito; el fallo vuelve.
5. **USB**: la orden existe pero la puerta no se la da (HUB_APP-F16).
Entra: el identificador de la impresora, el tipo de documento y el documento (nunca HTML).
Sale: lo que **se le devuelve a la pantalla** por caso:

   | Caso | Qué recibe quien pidió el papel |
   |---|---|
   | Identificador mal formado, tipo desconocido, documento que no compone | Error al instante |
   | Red, impresora apagada, IP equivocada, sin permiso de red local en Android 17 | **«Correcto»**. Tras los 3 intentos (unos 13 s) solo un `eprintln!` (`lib.rs:1256-1266`); en Android ni eso llega a `logcat` (`Cargo.toml`: el `eprintln!` de Rust no llega) |
   | Red, impresora encendida pero sin papel o con la tapa abierta | **«Correcto» y nada más**: no se consulta el estado de la impresora; escribir en el socket funciona |
   | Bluetooth fuera de alcance, apagado o sin permiso | Error con el motivo |
   | USB (hoja de prueba o cajón) | Error con el motivo si la cola no está lista o no saca el trabajo en 15 s |

   Quien lo pidió trata el «correcto» como entregado: la puerta de impresión devuelve `via: bridge`
   (`apps/web/src/lib/print.ts:381-404`), el puesto manda `done` al hub y la fila queda hecha
   (`print-drain.ts:212-213`). Cuando el tique sale por la puerta directa ni siquiera hay fila en la cola.
   La cola interna vive en memoria: lo que espera se pierde al cerrar la aplicación; no se deduplica el
   `jobId`; el trabajador único detiene ~13 s a las **demás** impresoras del mismo equipo por cada
   trabajo a una impresora apagada. No hay estado de fallo, reintento posterior ni aviso a la persona.
Si falla: lo anterior. La salida de verdad es mirar el papel; QA lo dice (qa-hub §8: «mira si sale papel,
no el valor de retorno»). Ver también `HUB_PERIPHERALS-F06` y `HUB-F199`.
Implicados: PRINTING-F07, PRINTING-F10, SALES-F01, KITCHEN-F08
Pendiente de enlazar: hub — HUB_PERIPHERALS-F06 (enviar un documento a la impresora de red) y HUB-F199 (confirmar que salió el papel)
QA: qa-hub §8, qa-hub-restaurant §16, qa-hub-android Fase 3

### HUB_APP-F20 Hacer una hoja de prueba
Estado: parcial — con una impresora de red «Probar» no avisa si no contesta: la hoja entra en la misma cola en memoria y la orden contesta «correcto» (`lib.rs:1700-1706`); ERPlora/hub#2494
Actor: administrador, responsable, empleado
Pantalla: printing: Impresoras
Pasos:
1. Pulsa «Probar» en la tarjeta de la impresora (o se envía sola al añadir por IP).
2. La aplicación compone la hoja (idioma y nombre del negocio, si llegan; si no, «ERPlora» en español) y
   la manda: por la cola interna si es de red, directa si es USB o Bluetooth.
Entra: el identificador de la impresora y, opcionalmente, el nombre del negocio y el idioma.
Sale: la hoja; nada guardado; no pasa por la cola del hub. Una aplicación más antigua que el módulo
recibe «sin datos» y la hoja sale igual.
Si falla: de red: no hay error aunque la impresora no conteste (HUB_APP-F19). De USB o Bluetooth: el
error vuelve y sale en rojo. Por eso **añadir por IP sí comprueba la conexión y «Probar» no**.
Implicados: PRINTING-F05
Pendiente de enlazar: hub — HUB_PERIPHERALS-F14 (hoja de prueba)
QA: qa-hub §8, qa-hub-android Fase 3

### HUB_APP-F21 Abrir el cajón
Estado: parcial — el cajón se abre por la impresora, pero no sin venta, una USB nunca lo recibe y el error se descarta antes de llegar a la persona; con una IP que no contesta la orden no tiene plazo propio
Actor: sistema, cajero
Pantalla: ninguna
Pasos:
1. Con «Abrir cajón al cobrar» activo, el dispositivo que cobró le manda a la aplicación el pulso para la
   impresora de Recibo.
2. **Red**: abre una conexión directa (sin cola, sin reintentos) y manda cinco bytes; **Bluetooth**: por
   el canal serie, esperando el resultado; **USB**: la orden existe pero la puerta no se la da al cobrar.
3. El pulso va por el pin 2 (por defecto); cualquier otro valor se trata como pin 5.
Entra: la impresora y el pin.
Sale: el pulso; nada guardado ni avisado al hub.
Si falla: la orden **sí devuelve el error** (a diferencia de imprimir): conexión rechazada, impresora
inalcanzable. Pero la pantalla lo descarta (`apps/web/src/lib/print-on-sale.ts:195`, `.catch(() =>
undefined)`). La conexión de red no lleva plazo propio (`crates/peripherals/src/drawer.rs`, `open_drawer`):
una IP que no responde cuelga la orden lo que dure el plazo del sistema, y el error es el de E/S, no
«impresora inalcanzable». Un pulso por el pin equivocado no da error: el cajón no se abre.
Implicados: PRINTING-F13, SALES-F01
Pendiente de enlazar: hub — HUB_PERIPHERALS-F15 (abrir el cajón) y HUB-F207 (lo que sabe el servidor)
QA: qa-hub §8, qa-hub-restaurant §16

### HUB_APP-F22 Imprimir un documento A4 con el diálogo del sistema
Estado: hecho
Actor: cajero, administrador, responsable
Pantalla: Ventana de impresión
Pasos:
1. Desde una factura u otro documento A4, la persona pulsa imprimir.
2. **Ordenador**: se abre una ventana que enseña el documento y, al cargar, el diálogo de impresión del
   sistema con su lista de impresoras y «Guardar como PDF»; la ventana se queda detrás como vista previa
   hasta que se cierra.
3. **Android**: se abre la pantalla de impresión de Android con el documento a A4.
Entra: el HTML del documento (no vacío, con tope de tamaño).
Sale: nada guardado. Se contesta cuando el diálogo se ha pedido; lo que la persona haga en él (imprimir,
guardar, cancelar) es del sistema.
Si falla: documento vacío o demasiado grande: `print_document_refused`; sistema sin diálogo (iOS):
`native_print_unsupported`; ventana que no se abre: `native_print_failed`. En todos la puerta de
impresión **no da el papel por impreso**: devuelve el motivo. El documento corre sin scripts (política
que no permite ninguno), sin permisos de ninguna orden y sin poder navegar a otro sitio.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (puerta de impresión y documento A4)
QA: qa-hub-android Fase 3

### HUB_APP-F23 Leer una tarjeta NFC para entrar
Estado: parcial — la lectura con tarjeta y tableta reales no está validada (pm#145); en ordenador no existe y el lector USB sigue siendo la vía
Actor: responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En Android, en una pantalla que espera una tarjeta (acceso con placa, aprobación, ficha de personal),
   la persona acerca la tarjeta a la tableta.
2. La página abre una ventana de lectura de 15 s (acotada entre 1 y 60 s) y la repite mientras alguien
   la espera; la tableta pita al leer.
3. La aplicación contesta el número de la tarjeta (el UID en mayúsculas hexadecimal, sin separadores),
   que entra por **la misma puerta** que el lector USB: ninguna pantalla sabe de dónde vino.
Entra: la tarjeta (se leen NFC-A, B, F y V; no se busca mensaje).
Sale: la placa; nada guardado aquí (el hub guarda solo un índice cifrado).
Si falla: tres rechazos distintos: sin lector (`nfc_unavailable`: la página deja de preguntar toda la
sesión), lector apagado (`nfc_disabled`: «El NFC está apagado en este aparato. Enciéndelo para leer las
tarjetas acercándolas.», una vez por pantalla) y tarjeta que da un número nuevo en cada lectura
(`nfc_random_uid`: «Esta tarjeta da un número distinto cada vez que se lee, así que no puede usarse como
placa. Prueba con otra.»). Un UID de ceros o de menos de 4 bytes también se rechaza. Pasada la ventana sin
tarjeta no es un error. En ordenador la orden contesta siempre `nfc_unavailable`. El NFC no es requisito
de instalación: la ficha de Play sigue abierta a tabletas sin chip.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F134 (entrar pasando la placa)
Pendiente de enlazar: hub — HUB_SHELL, Acceso y Personas (captura de la placa y ficha de personal)
QA: ninguno

### HUB_APP-F24 Avisar con el sistema aunque nadie mire la pantalla
Estado: hecho
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Llega una comanda a la cocina, una cita que no salió de este TPV o sube un contador de la campana.
   La página (no la aplicación) decide avisar y manda título, cuerpo, un número de aviso y la pantalla a
   la que lleva.
2. En Android, la página pide antes el permiso de notificaciones (HUB_APP-F07); sin él **no manda el
   aviso** (para no abrir el diálogo de Android a pelo en pleno servicio).
3. La aplicación muestra el aviso del sistema: Windows, con un enlace propio para poder abrirlo desde el
   Centro de actividades; macOS y Linux, esperando el clic; Android, por el plugin de notificaciones.
Entra: título, cuerpo, número (si cabe en 32 bits) y ruta (solo pantallas del propio hub).
Sale: la notificación. **Nunca falla hacia arriba**: permiso negado o plataforma que no puede mostrarla se
anota y la comanda o la cita siguen. Un número fuera de rango no impide el aviso, solo le quita su destino.
Si falla: un navegador sin aplicación no tiene aviso del sistema. Sin permiso negado no hay otra señal que
el que el aviso no sale (la fila «Los avisos están desactivados» de Sistema lo cuenta).
Implicados: KITCHEN-F05
Pendiente de enlazar: hub — HUB-F60 (avisar a las pantallas en vivo)
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (qué eventos disparan un aviso)
QA: qa-hub-restaurant §7.08

### HUB_APP-F25 Tocar un aviso
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Aviso del sistema
Pasos:
1. La persona toca (o hace clic en) el aviso.
2. La aplicación se trae la ventana delante y la página abre **la pantalla de la que avisaba** (la
   conversación, la agenda, la cocina).
3. **Android con la aplicación abierta**: el plugin entrega el toque a la página. **Android con la
   aplicación cerrada o matada por el sistema**: el aviso guarda su destino, la aplicación arranca, y la
   página lo reclama al arrancar. **Ordenador**: el clic se guarda y la página lo reclama (la aplicación le
   avisa de que hay uno esperando). **Windows**: cada clic, también desde el Centro de actividades y con la
   aplicación cerrada, lanza la aplicación con un enlace propio (`erplora://notice?...`) que la ya abierta
   recibe.
Entra: el número del aviso y la ruta con que salió.
Sale: la pantalla abierta; el toque se entrega **una vez**. Si la página es nueva y no recuerda el número,
usa la ruta que el aviso trae, tras comprobar de nuevo que es una pantalla del hub.
Si falla: un aviso sin número solo trae la ventana al frente. Una ruta que no es de una pantalla del hub
(otra dirección, `//…`) se descarta. Un aviso que pasó sin clic (macOS, Linux) no abre nada.
Implicados: KITCHEN-F05
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (campana y destino del aviso)
QA: ninguno

### HUB_APP-F26 Seguir a la escucha con la pantalla apagada (Android)
Estado: parcial — solo se mantiene a la escucha si la persona ha iniciado sesión, el hub tiene algo que avisar y los avisos no están negados; un puesto que solo imprime (sin cocina, citas ni contador de campana) o con las notificaciones negadas se congela con la pantalla apagada, y con el sistema matando el proceso no vuelve solo
Actor: sistema
Pantalla: Aviso del sistema
Pasos:
1. Decisión vigente (ERPlora/hub#2307): **no hay push**; los avisos con la pantalla apagada van por tener la
   aplicación escuchando durante el turno.
2. Con sesión iniciada, algo que avisar (cocina, citas o un módulo con contador en la campana) y los avisos
   no negados, la página pide mantener la aplicación a la escucha con las palabras de la notificación en
   el idioma del hub.
3. Android arranca un servicio en primer plano y muestra la notificación permanente «ERPlora está a la
   escucha». Mientras dura, la aplicación mantiene viva la página: la desbloquea cuando la pantalla se
   apaga o la aplicación pasa al fondo (sin ello Chromium la congela al minuto) y los avisos de la
   comanda y la cita siguen llegando.
4. Al cerrar la sesión, al negar los avisos o al cerrar la aplicación desde recientes, se para.
Entra: la petición de la página (activar con textos o desactivar).
Sale: el servicio y su notificación silenciosa, sin sonido ni insignia. No se reinicia solo
(`START_NOT_STICKY`): lo reabre la página al abrir la aplicación.
Si falla: Android 12 o posterior no deja arrancar un servicio en primer plano desde el segundo plano: la
orden rechaza y los avisos siguen funcionando con la aplicación en pantalla. Sin los permisos de servicio
(Android 14) lanza error. En ordenador no se necesita: la aplicación no se duerme mientras esté abierta.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Avisos e impresión (cuándo pedir escuchar) y HUB-F60 (los avisos nacen en la página)
QA: qa-hub-android Pendiente (pantalla apagada y segundo plano)

### HUB_APP-F27 Arrancar con el ordenador
Estado: hecho
Actor: administrador, responsable
Pantalla: HUB_SHELL: Ajustes
Pasos:
1. En un ordenador (no en Android), en **Ajustes › Hub** aparece «Arrancar al iniciar sesión»; está
   **apagado** de fábrica.
2. Al activarlo, la aplicación lo registra en el sistema (macOS, agente de arranque; Windows, clave de
   registro; Linux, carpeta de autoarranque) y vuelve a leer qué dice el sistema.
3. La pantalla enseña lo que el sistema respondió, no lo que se pidió.
Entra: activar o desactivar.
Sale: la entrada del sistema; la aplicación no guarda estado propio.
Si falla: un fallo al registrar se propaga y la pantalla dice «No se pudo cambiar el ajuste de arranque al
iniciar sesión». En Android la orden rechaza a propósito y el control no se pinta. Arrancar con el
ordenador es para que siempre haya un puesto que saque la cola; abrir el equipo no garantiza que haya
sesión iniciada en el hub.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes (control «Arrancar al iniciar sesión»)
QA: ninguno

### HUB_APP-F28 Botón Atrás de Android
Estado: hecho
Actor: empleado, cajero
Pantalla: Ventana de ERPlora
Pasos:
1. La página toma el botón Atrás del sistema.
2. Cierra primero lo de encima: un diálogo, una hoja, el menú lateral o lo que el módulo abierto declare;
   uno que no se puede cerrar retiene la pulsación.
3. Sin nada abierto y con historial, retrocede; sin historial, manda la aplicación al fondo (no la cierra
   ni la mata).
Entra: la pulsación.
Sale: la aplicación en segundo plano.
Si falla: una aplicación más antigua que la orden devuelve el botón a Tauri, que sale por sí misma.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (navegación y botón Atrás)
QA: ninguno

### HUB_APP-F29 Abrir un enlace fuera de la aplicación
Estado: hecho
Actor: administrador, responsable
Pantalla: ninguna
Pasos:
1. Un botón que cobra o lleva a la cuenta (comprar un módulo, planes, portal de facturación, la descarga
   de la actualización) pide abrir una dirección.
2. La aplicación comprueba la dirección y la entrega al **navegador del sistema** (no a una pestaña
   propia): la caja se queda como estaba mientras se paga.
3. La persona vuelve a la aplicación, que sigue donde estaba.
Entra: una dirección https de erplora.com o de un negocio, la de pago `checkout.stripe.com` (solo ese host),
o http a un bucle local de desarrollo.
Sale: el navegador abierto; nada guardado.
Si falla: una dirección que no es de las anteriores, con usuario o contraseña, o de otro esquema
(`file:`, `javascript:`) se rechaza (`external_url_refused`); sin navegador instalado, o que dice que no
(`external_url_unavailable`). La página convierte ambos en un aviso: un botón que no hace nada es el
defecto que esto evita. Desde un navegador normal es una pestaña nueva.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Aplicaciones, plan y archivos (salidas al SaaS)
QA: qa-hub-android Fase 4

### HUB_APP-F30 Guardar una descarga
Estado: parcial — iOS la rechaza y Android 9 o anterior no tiene dónde guardar (la frase de la pantalla habla de «un móvil o una tablet» en general)
Actor: administrador, responsable
Pantalla: ninguna
Pasos:
1. Desde Archivos, una copia de seguridad o una factura en PDF, la persona pulsa descargar.
2. La página tiene los bytes y se los da a la aplicación con un nombre.
3. **Ordenador**: se guarda en la carpeta Descargas del usuario; si ya existe, el nombre pasa a
   `nombre (2).ext` (hasta 999; nunca pisa un fichero). **Android 10 o posterior**: se publica en la
   colección pública de Descargas; se enseña «Download/<nombre>».
4. La pantalla enseña «Guardado en {ruta}»: dentro de la aplicación no hay barra de descargas ni aviso.
Entra: nombre y contenido (en base64).
Sale: el fichero; la ruta que se enseña.
Si falla: un nombre con separadores, `:` (flujos alternativos de Windows), caracteres de control, solo
puntos o de más de 255 bytes se rechaza (`download_refused`) en vez de recortarse. Sin carpeta de
descargas alcanzable: «Esta app no puede guardar archivos en un móvil o una tablet. Abre tu negocio en un
navegador para descargarlo.»; cualquier otro fallo, «No se ha podido descargar el archivo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Aplicaciones, plan y archivos (descargar un archivo) y Ajustes (exportar)
QA: ninguno

### HUB_APP-F31 Saber que hay una versión nueva y actualizar
Estado: parcial — la aplicación nunca se actualiza sola: abre la descarga en el navegador; macOS no tiene destino; la copia de la Store y la de Play no avisan (las actualiza la tienda)
Actor: administrador, responsable
Pantalla: HUB_SHELL: Sistema
Pasos:
1. Al arrancar y cada 6 horas, la página pregunta a la aplicación qué versión es (orden estándar de
   Tauri, que existe aun en aplicaciones viejas) y al hub cuál es la última publicada.
2. Solo si la publicada es **estrictamente mayor** (comparando número a número) y quien está conectado
   administra el negocio, el menú lateral enseña «Actualizar ERPlora ({versión})», una vez por versión.
3. Al pulsarlo, confirma: en ordenador, «Se abre tu navegador para descargar la versión… No se instala
   nada solo»; en Android, «Se abre la ficha de ERPlora en Google Play…».
4. La descarga o la ficha se abre en el navegador del sistema (HUB_APP-F29). Nada recarga ni cierra la
   ventana: el momento de instalar lo elige la persona.
Entra: la versión instalada, la publicada (`latest.json`, que escribe cada publicación), el sistema y el
canal.
Sale: el navegador abierto en `erplora.com/app/download/<sistema>/` (el Cloud decide el instalador o la
tienda).
Si falla: sin red, versión ilegible o sin respuesta: silencio, ni alarma ni «estás al día». Para las
copias de Play y de Microsoft Store no hay destino y no se ofrece (Google prohíbe descargar un APK fuera de
Play). macOS no tiene descarga. Una versión con sufijo (`1.2.3-beta`) se ignora. «No hemos podido abrir
tu navegador…» si no se pudo abrir.
Implicados: pendiente
Pendiente de enlazar: saas — publicación de versión y redirección a la tienda
Pendiente de enlazar: hub — HUB_SHELL, Sistema y menú lateral (aviso de actualización)
QA: qa-hub-android Fase 4

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Instalar desde la tienda (Play, Microsoft Store) | parcial: publicación sin confirmar | F01 |
| Instalador directo de Windows y `.dmg` de macOS | parcial: sin firmar / sin notarizar | F01 |
| Elegir negocio y recordarlo | hecho | F02 |
| Enlace profundo para abrir un negocio | hecho | F03 |
| Cambiar de negocio | parcial: no cierra la sesión | F04 |
| Olvidar un negocio borrado | hecho | F05 |
| Escanear un QR dentro de la aplicación para enlazar | no existe (la aplicación no tiene cámara; el QR del menú abre el negocio por https en el móvil) | F03 |
| Permisos de Android con explicación previa | parcial | F07, F08 |
| Permiso de red local en macOS | parcial | F09 |
| Juegos de permisos por origen | hecho | F10 |
| Pantalla sin conexión y vuelta sola | hecho | F11 |
| Buscar impresoras (red, Bluetooth, USB) | hecho | F13 |
| Añadir por IP | hecho | F14 |
| Impresora Bluetooth | parcial: no se empareja desde ERPlora | F15 |
| Impresora USB | parcial / no hecho en Windows | F16 |
| Nombre, función y quitar impresora | parcial | F17 |
| Puesto de impresión | parcial | F18 |
| Imprimir tique y comanda con aviso si falla | parcial: red sin aviso | F19 |
| Hoja de prueba | parcial: red sin aviso | F20 |
| Abrir el cajón | parcial | F21 |
| Imprimir A4 con el diálogo del sistema | hecho | F22 |
| Tarjeta NFC | parcial: sin validar con hardware | F23 |
| Aviso del sistema y abrir su pantalla al tocarlo | hecho | F24, F25 |
| Avisos con la pantalla apagada (sin push) | parcial | F26 |
| Arranque automático | hecho | F27 |
| Atrás de Android | hecho | F28 |
| Enlace externo, guardar descarga | hecho / parcial | F29, F30 |
| Actualización | parcial: sin actualización en el sitio | F31 |
| Báscula | no existe (hub#1217) | — |
| Push (FCM) con la aplicación cerrada | no existe, por decisión (hub#2307) | F26 |
| iOS | sin construir | — |

## Datos: de quién es cada dato

- **De la aplicación, en su carpeta de datos del usuario** (no en el hub): `device.id` (identificador de
  instalación), `hub.url` (origen del negocio recordado) y `devices.json` (registro de impresoras:
  clave, MAC si se conoce, dirección, puerto, nombre, función, tipo, vistas por primera y última vez,
  en línea). Ninguno se sube al hub por sí solo.
- **De Android**: el último toque de aviso recordado (`com.erplora.notice_taps`) y los permisos del sistema.
- **Del navegador integrado**, por origen: la sesión del hub y la memoria de «ya te pregunté» de los
  permisos (`erplora.notifications.primerAnswered`, `erplora.localNetwork.primerAnswered`) y la última
  versión anunciada.
- **Del hub**: la cola de impresión, los puestos, las funciones, las sesiones (HUB, área Impresión y
  Acceso). **Del SaaS**: la cuenta, los negocios y las versiones publicadas.
- **Datos personales** (inventario RGPD): no persiste ninguno. Pasan por memoria y por el registro
  técnico: títulos y cuerpos de avisos (pueden nombrar a un cliente: nombre en una cita), documentos de
  impresión (nombre, NIF y dirección del cliente de una factura; mesa y camarero de una comanda) y el
  UID de una tarjeta NFC. Lo que se guarda en disco es la MAC y la IP de impresoras de la empresa, sus
  nombres, un identificador de instalación y la dirección del negocio. Desinstalar o borrar la carpeta
  los elimina.

## Reglas que no se rompen

- **Hardware solo desde el origen del negocio.** Lo hace cumplir `capabilities/default.json`; el apex del
  SaaS solo recibe identidad y olvidar (`tests/remote_acl.rs`).
- **Solo se recuerda, se abre por enlace o se envía al navegador lo que la regla permite**: negocios de la
  plataforma y bucle local (y el apex y `checkout.stripe.com` solo para el navegador del sistema).
- **El enlace profundo se resuelve, no se abre**: la dirección se reconstruye desde el nombre.
- **Una orden que no pudo hacerse se devuelve, no se traga** (abrir enlace, guardar, imprimir A4, NFC,
  Bluetooth, USB). *Excepción vigente y defecto*: la impresora de red encola y contesta «correcto»
  (HUB_APP-F19, ERPlora/hub#2494).
- **La copia de Google Play no sigue páginas del SaaS que cobran ni nombra otro sitio donde pagar.**
- **Un permiso que Android no conoce no se pide, y uno que falta no se lee como denegado.**
- **Una descarga nunca pisa otro fichero y el nombre lo decide el escritorio, no la página.**
- **La actualización no interrumpe**: no recarga, no cierra y no instala sola.

## Lo que NO hace, a propósito

- No lleva el negocio ni la base de datos dentro: no hay servidor local, ni modo sin conexión, ni
  autorización de módulos (la decide el servidor).
- No hay push (FCM): los avisos con la pantalla apagada van por mantener la aplicación escuchando.
- No empareja Bluetooth ni escanea dispositivos (solo lee los emparejados); no pide el permiso de escaneo.
- No actualiza la aplicación por sí misma.
- No tiene icono de bandeja ni mantiene la aplicación viva al cerrar la ventana.
- No lee básculas ni escáneres de códigos (el escáner es un teclado para el sistema).
- No escanea códigos QR ni usa la cámara.
- No maneja impresoras de etiquetas (ZPL/TSPL/EPL) ni imprime imágenes (`HUB_PERIPHERALS`).
- No sigue las páginas de otros dominios con permisos: un negocio con dominio propio no recibe hardware.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

1. **Báscula**: no existe en la aplicación (ni orden, ni permiso, ni evento `erplora:scale-weight`);
   ERPlora/hub#1217 sigue abierta (P1, hardware). ¿Entra en el MVP o después del primer cliente?
2. **¿Se sigue anunciando Linux?** Se construyen `.deb` y AppImage («canal de QA») pero ningún documento
   de producto los ofrece. ¿Se retira de la matriz o se declara?
3. **macOS**: el `.dmg` sale sin notarizar y `downloadPlatform` no tiene destino para él. ¿Se publica una
   descarga o se declara fuera del MVP?
4. **Aviso al administrador cuando una impresora de red no saca el papel** (ERPlora/hub#2494): ¿consultar
   el estado de la impresora (ESC/POS en tiempo real) o confirmar el envío al socket? ¿qué se enseña a la
   cajera?
5. **Puesto de impresión que solo imprime** en Android: ¿debe mantenerse a la escucha aunque no haya cocina,
   citas ni contador de campana? Hoy no.
6. **El QR del menú abre el negocio por https**, no `erplora://`: en un móvil con la aplicación instalada se
   abre en el navegador. ¿Es lo que se quiere?
7. La ventana emergente de **Meta** («Tu número» de WhatsApp) usa una ventana nueva del navegador integrado,
   que en la aplicación no abre ninguna (`window.open` no hace nada): sin confirmar cómo se completa ahí.

## Fuentes contrastadas

- `GOOGLE-PLAY.md` dice «Sin declaración de FGS… la app no corre en segundo plano»: **ya no es cierto**; el
  manifiesto declara el servicio en primer plano `specialUse` desde hub#2307 y lo arranca la página.
- `apps/tauri/README.md` y los comentarios de `app-update.ts` dicen que macOS «se construye solo en local»;
  `tauri-release.yml` ya construye el `.dmg` en CI (sin notarizar).
- El texto de «¿Cambiar de negocio?» («cerrará la sesión») no se corresponde con el código (HUB_APP-F04).
- El guion de QA de Android (`qa-hub-android.md`) no tiene identificadores de escenario, solo fases; las
  referencias `qa-hub-android §15` de `HUB_PERIPHERALS` y de `PRINTING` no existen: el guion tiene la
  impresión en la Fase 3 (paso 15).
- `architecture/hub/apps/tauri.md` §«Las cuatro preguntas del ciclo de vida» dice que no hay control para
  cambiar de negocio (hub#447): sí lo hay (HUB_APP-F04), cerrada.
- `README.md` de la app llama «Bridge» a la app: el Bridge no existe (ADR-0196); lo que queda con ese nombre
  es `erplora_bridge_status` (devuelve la versión) y `bridge-transport.ts` (el transporte de hardware).
- El guion dice que `qa-hub-android` prueba el deep link en «Pendiente (fase C)»: no hay escenario aún.
