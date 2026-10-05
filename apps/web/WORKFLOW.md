# WORKFLOW — Hub · pantallas
Prefijo: HUB_SHELL
Alcance MVP: transversal

> Contrato de comportamiento de las pantallas del hub (`apps/web`, Vue + Ionic + OutfitKit),
> pm#620, pm#621. Se lee antes de tocar el código de `apps/web/src` y se actualiza en la misma PR
> que cambie un comportamiento. Lo que hace el servidor detrás de cada pantalla está en
> `hub/WORKFLOW.md` (prefijo `HUB`); lo técnico, en `architecture/hub/apps/web.md` y vecinos.
> Índice partido: el detalle de los flujos vive en `workflow/<área>.md`.

## Para qué sirve y para quién

Las pantallas del hub son lo que una persona del negocio tiene delante todo el día: entra con su
cuenta o con su PIN, ve **Inicio**, abre sus apps (Ventas, Caja, Agenda…) desde el lanzador, y el
administrador gestiona desde el menú a las personas, las apps, el plan, el sistema y los ajustes.
El shell es el marco común a todas las apps instaladas: la entrada y la sesión, el menú y la barra
superior, la campana, el asistente, el diálogo que pide el PIN de un responsable, la impresión del
tique al cobrar, las franjas que avisan de que no se puede facturar o no hay conexión, y la vista
donde se monta cada app. Lo usan el **administrador** (todo), el **responsable** (aprueba con su
PIN, ve cifras), el **empleado** y el **cajero** (el perfil que añade Ventas), en la caja compartida,
en la tableta de cocina, en el portátil del despacho y en el móvil.

## Cómo está partido este documento

Un worker lee este índice **y** el fichero del área que va a tocar. Las vistas y piezas de
`apps/web/src` que gobierna cada fichero:

| Área | Fichero | IDs | Vistas y piezas principales |
|---|---|---|---|
| Acceso, navegación y perfil | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) | F01–F24 | LoginPage, ActivationPage, AuthenticatedChrome, AppTopbar, shell-menu, nav, UserSwitchOverlay, DeviceModeCard, OfflineStrip, BootUnreachable, idle-logout, session-end-reason, NotFoundPage, ProfilePage, pwa, SidebarInstallQr, SidebarAppUpdate, theme, viewport |
| Inicio y puesta en marcha | [workflow/inicio.md](workflow/inicio.md) | F25–F39 | DashboardPage, SetupChecklistCard, SetupBlockingStrip, BlueprintHeroCard, MyAppsCard, dashboard-widgets, dashboard-activity, setup-status |
| La vista de un módulo | `workflow/vista-de-modulo.md` | F40–F59 | ModuleView, module-loader, ModuleSettingsForm, module-settings, ModulePlanPanel, module-quota, module-usage, protects, lock-refusal, ElevationDialog, elevation, module-failure-message, runtime-error-sentence, invalid-field, slot-fillers, outfitkit-skew |
| Avisos e impresión | `workflow/avisos-e-impresion.md` | F60–F79 | bell-counters, bell-notice, notice-listening, notice-tap, notification-permission, appointment-notice, print-on-sale, print-comanda, print-host, print-host-registration, print-drain, print-enqueue, print-alert, print-coverage, native-print, receipt-template, sale-document, printer-discovery, toast |
| Personas y permisos | `workflow/personas-y-permisos.md` | F80–F104 | EmployeesPage, EmployeeFormPage, RolesPanel, ApprovalsPanel, ApiKeysPanel, ApiDocsPage, PinPolicyCard, DevicesCard, hub-users, approvals, api-keys, badge-scanner, nfc-badge |
| Aplicaciones, plan y archivos | `workflow/aplicaciones-plan-y-archivos.md` | F105–F134 | AppsPage, apps-catalog, apps-grid, installed-app-actions, module-updates, module-update-notice, BillingPage, PlanLimitsPanel, entitlement, upgrade-plan-link, management-link, saas-door, FilesPage, FilePreviewModal, GrantFilePicker |
| Sistema | `workflow/sistema.md` | F135–F154 | SystemPage y sus pestañas (system-tabs, system-health, system-metrics, system-usage, dead-letter, update-history, app-update), error-report |
| Ajustes del negocio y datos | `workflow/ajustes-y-datos.md` | F155–F184 | SettingsPage y sus pestañas (settings-tabs, hub-settings, timezone), WhatsAppConnect, DataPanel, ExportPanel, ImportPanel, ImportPermissionsConsent, import-retry, ResetPanel |
| Asistente | `workflow/asistente.md` | F185–F199 | AssistantDrawer y assistant*.ts (confirmación, peligro, anclaje, historial, plan, informe, rutas, puesta en marcha) |

Una pieza que dos áreas comparten se describe donde se ve y la otra la cita. **Ajustes › General**
lleva tres tarjetas de tres flujos: «Este dispositivo» (`DeviceModeCard`) es de Acceso
(HUB_SHELL-F11); «Pinpad» (`PinPolicyCard`) y «Dispositivos» (`DevicesCard`) son de «Personas y
permisos» (HUB_SHELL-F99…F104); la pestaña en sí, de «Ajustes del negocio y datos». «Actualizar
ERPlora» del menú es de Acceso (HUB_SHELL-F20) y la pestaña Sistema › Actualizaciones, de Sistema; la
salud del Inicio (HUB_SHELL-F37) usa las mismas frases que Sistema.

Ficheros de `src/lib/` que la tabla no nombra, y quién los cubre:

| Fichero | Área |
|---|---|
| `session.ts`, `courier.ts`, `user-switch.ts`, `pin-policy.ts`, `pinpad-dial.ts`, `pin-length.ts`, `device-mode.ts`, `device.ts`, `cloud.ts` (acceso), `boot.ts`, `boot-screen.ts`, `offline.ts`, `immersive.ts`, `change-hub.ts`, `install-qr.ts`, `deep-link.ts`, `user-profile.ts`, `branding.ts`, `routes.ts`, `hash-tab.ts`, `tabbar-peek.ts`, `list-load-state.ts`, `router/` | Acceso, navegación y perfil |
| `dashboard-heading.ts`, `dashboard-blueprint-widget.ts`, `blueprint-hero.ts`, `app-usage.ts` | Inicio y puesta en marcha |
| `autostart.ts` | `HUB_APP` el comportamiento; el interruptor de Ajustes, «Ajustes del negocio y datos» |
| `bridge-transport.ts`, `client-instance.ts` | «Avisos e impresión» (y `HUB_APP` el transporte de la app) |
| `device-permission.ts`, `local-network-permission.ts` | `HUB_APP`; su entrada desde Sistema, «Sistema» |
| `platform-failure.ts` | «Personas y permisos» |
| `teleported-styles.ts` | «La vista de un módulo» |
| `media.ts` | «Aplicaciones, plan y archivos» |
| `money.ts` | regla común (ver «Lo que comparten todas las pantallas») |

`visual-baseline-gate.ts` (herramienta de tests visuales) y `src/parked/` (código sin enrutar) no
tienen comportamiento visible y no los gobierna ningún flujo.

## Referencia adoptada

Se adopta esto, contrastado en `.claude/agents/qa-hub-restaurant.md` §2, en las decisiones de
`architecture/hub/auth.md` y en los comentarios de las vistas que citan su referencia:

- **Entrar con PIN en un dispositivo compartido, con rejilla de caras, y relevo de turno sin cerrar
  la venta**: Square (Team passcodes) y Toast (employee passcodes, «switch user» como capa encima de
  la app). PIN de longitud fija por negocio, 4 o 6, que entra al último dígito: Clover (hub#974).
- **Placa (RFID/NFC) como la misma identidad que el PIN, nunca sustituta**: Toast, Aloha/NCR,
  Square, Lightspeed (ADR-0347).
- **Arranque que no encuentra el servidor: un aviso y un solo gesto, reintentar**: Square, Toast,
  Lightspeed (hub#2143).
- **Una franja persistente mientras no hay conexión, que se va sola**: Square, Toast, Shopify POS
  ([Square — modo sin conexión](https://squareup.com/help/es/es/article/7777-process-card-payments-with-offline-mode)).
- **Dirección inexistente: una página que lo dice y una salida**: Shopify admin, Square Dashboard,
  Stripe, Odoo, Business Central (hub#1723).
- **Pantalla de venta sin el marco de la aplicación**: Odoo POS, Square, Lightspeed (pantalla
  completa).
- **Inicio con una guía de puesta en marcha que se cierra sola al terminar, y un empuje inicial con
  plantilla de sector**: las guías de arranque de Shopify, Odoo y Square (hub#368, hub#372).
- **Tablero de paneles que aportan las apps, con presets por sector**: ADR-0054.
- **Instalar como aplicación desde el navegador, sin que el producto lo pida**: hub#685, hub#1715.

> **Integrador:** aquí se añaden las referencias de las áreas «La vista de un módulo», «Avisos e
> impresión», «Personas y permisos», «Aplicaciones, plan y archivos», «Sistema», «Ajustes del
> negocio y datos» y «Asistente».

## Antes de empezar

- El hub tiene que estar **dado de alta** en erplora.com (llega así al crearlo desde el panel); uno
  sin alta solo enseña el acceso y no deja entrar (HUB_SHELL-F12).
- Cada dispositivo necesita **una primera entrada con una cuenta de erplora.com** miembro del negocio,
  por el formulario o desde la app instalada (en un navegador, entrar por el pase del panel no
  cuenta): es lo que lo hace de confianza y enciende el PIN en él (HUB_SHELL-F01, HUB_SHELL-F02,
  HUB_SHELL-F04). Tras dar un PIN nuevo, recarga ERPlora en las cajas para que salga en la rejilla.
- En una caja compartida: márcala como compartida (HUB_SHELL-F11), decide en **Ajustes → General →
  Pinpad** si se pregunta quién vende y cada cuánto, y que cada persona tenga su PIN (HUB_SHELL-F03,
  HUB_SHELL-F22 o Empleados).
- Para facturar: razón social y NIF en Ajustes › Negocio, y la vía hasta la AEAT; la franja roja dice
  qué falta (HUB_SHELL-F28).

Configuración inicial, paso a paso:

1. Entra con tu cuenta en la caja, marca «Confiar en este dispositivo» y elige tu PIN (HUB_SHELL-F01, HUB_SHELL-F03).
2. En **Inicio**, usa una plantilla de tu sector o añade apps (HUB_SHELL-F26, HUB_SHELL-F32).
3. Sigue «Termina de configurar tu negocio» empezando por lo que es «Necesario para facturar» (HUB_SHELL-F27 a HUB_SHELL-F31).
4. Da de alta al equipo en **Empleados** y comprueba la salud de la impresora en **Inicio** (HUB_SHELL-F37).
5. Escanea el QR del menú desde el móvil si vas a usarlo (HUB_SHELL-F19).

## Lo que comparten todas las pantallas

Vale para todas las áreas; quien escribe una pantalla nueva lo cumple sin volver a decidirlo.

- **Un solo marco.** Toda pantalla con sesión va dentro del mismo esqueleto: barra superior,
  franjas (bloqueo de facturación y conexión) entre la barra y el contenido, el contenido y, si la
  pantalla tiene secciones, pestañas abajo. Solo Acceso, la pantalla de arranque sin hub y la de
  activación van sin marco. Las pestañas de una pantalla viven en la dirección (`/settings#data`),
  así un enlace abre la pestaña.
- **Sin sesión no hay marco.** El menú, la barra, el asistente, el diálogo de aprobación y el relevo
  de turno solo existen con una sesión abierta.
- **Cuatro estados, cada uno con su frase.** Cargando (indicador o baldosas grises con su frase para
  el lector de pantalla), vacío (una frase que dice qué aparecerá y cómo llenarlo), error (lo que
  pasó y, donde se puede, «Reintentar») y sin conexión (la franja de HUB_SHELL-F14). Una lista que
  no se pudo leer no se pinta vacía (hub#770, hub#894); un rechazo por permiso esconde la acción o
  dice quién puede hacerla, nunca el nombre técnico del permiso.
- **Tres tamaños.** Móvil (menos de 768 px): menú en cajón, acciones de la barra plegadas en «Más
  opciones», rejillas a dos filas por debajo de 540 px. Tableta (768–991 px): menú en cajón, barra
  completa. Escritorio (992 px o más): menú fijo que se pliega a iconos. Con poca altura (500 px o
  menos, un móvil apaisado) la franja de bloqueo se pliega a una línea. QA mide 1440, 834 y 390.
- **Idiomas.** El texto de la pantalla sale de `src/i18n/locales/`: el inglés es la fuente y cada
  cadena nueva lleva su español; un test de paridad lo exige. El idioma es el de la persona (Mi
  perfil), si no el del negocio, si no español. Los nombres y títulos de las apps los traduce el hub.
  Nunca se pinta un código interno (`hub.users.pin_in_use`) ni una traza.
- **Dinero.** Se pinta con la moneda del hub y los separadores del idioma (`lib/money.ts`). El hub y
  las apps guardan el dinero en céntimos: se pinta con `formatMoney`, que divide según los decimales
  de la moneda; `formatAmount` es solo para cifras que ya llegan en euros. Confundirlas multiplica el
  importe por cien (HUB_SHELL-F36).
- **Campos.** El shell fija el modo `ios` de Ionic, en el que `fill="outline"` no pinta nada en
  `ion-input`, `ion-select` e `ion-textarea`. La regla es una: los campos del shell declaran
  `fill="outline"` junto a `mode="md"` (lo vigila `theme/ionic-fill-needs-md.test.ts`) y un gancho
  que se carga antes que Ionic (`lib/ionic-fill.ts`) pone `mode="md"` a todo campo con `fill` que no
  declare modo, módulos incluidos (hub#760, hub#1060). En `ion-button`, `fill="outline"` sí pinta.
- **Iconos.** Por el componente del shell y el registro de iconos de Iconify horneado en la
  compilación (`ion:` por defecto): sin SVG sueltos y sin bajar nada de la red.
- **El PIN de un responsable.** Cuando una orden necesita la aprobación de un responsable, el diálogo
  «Hace falta una aprobación» se abre encima de la pantalla que sea, lo abre el transporte y no la
  app, y la orden se repite sola al aprobarla (área «La vista de un módulo»).
- **Confirmaciones y avisos.** Lo irreversible se confirma con un diálogo que dice la consecuencia; lo
  que acaba de pasar se dice con un aviso breve. El botón Atrás de Android cierra antes la hoja o el
  diálogo que haya encima.

> **Integrador:** si otra área aporta una regla común, va aquí.

## Pantallas

### Acceso
Al abrir el hub sin sesión. Sin menú ni barra: arriba a la derecha el botón de tema (sol o luna);
en el centro el logo del negocio (o el de ERPlora si no carga) con «Entra en tu negocio», «Introduce
tu PIN», «Crea tu PIN de acceso» o «Verifica que eres tú» según el paso; encima, cuando toca, el
aviso de sesión desalojada (HUB_SHELL-F06) o el del pase del panel (HUB_SHELL-F02). Una tarjeta con
las pestañas «PIN» y «Email» si el dispositivo ofrece PIN. **Email**: «Email», «Contraseña», «Confiar
en este dispositivo» con su ⓘ (o la nota del dispositivo personal), «Entrar», «o», «Continuar con
Google» y, sin pestañas, «Usar PIN en su lugar». **PIN**: «…o pasa tu placa…», «Elige tu usuario»
con una tarjeta por persona, después la cara elegida y el teclado de círculos con «Cambiar usuario».
**Crear PIN** y **código de verificación**: un paso cada uno dentro de la misma tarjeta. Pie: «ERPlora
· dispositivo de confianza» o «ERPlora · conexión segura». Cargando: el círculo en el botón; error: la
frase en rojo bajo el control.

### Cambiar de usuario
Ventana encima de la pantalla en curso, desde la tarjeta de usuario del menú en una caja compartida:
«Cambiar de usuario», «La venta sigue abierta…», «¿Quién se pone?» con las caras (o «Su nombre» y
«Continuar» si el hub aún no las ha dado), después el teclado con «Otra persona», y «Cancelar». Error:
la frase en rojo bajo el teclado; la ventana no se cierra.

### Menú lateral
Fijo a la izquierda en escritorio, en cajón en tableta y móvil. Arriba, la **tarjeta de usuario**
(foto o iniciales, nombre y correo) que despliega «Perfil», «Cambiar de usuario» (solo en caja
compartida) y «Cerrar sesión». Secciones «General» (Inicio, Empleados, Archivos) y «Cuenta» (Mi plan,
Apps, Sistema, API si está publicada, Ajustes). Pie, siempre a la vista: «Actualizar ERPlora ({version})» en
la app instalada, cuando hay versión nueva y solo a quien administra; el QR «Ábrelo en el móvil», «Actualizar plan» (salvo en la copia de Google Play), el logo
que lleva a Inicio y la versión. Sin estados propios: las entradas son fijas.

### Barra superior
Encima de cada pantalla con marco: botón del menú (tableta y móvil), «Atrás» en las de detalle,
plegar el menú (escritorio), el título de la pantalla, las acciones de la pantalla, el lanzador
«Mis apps» (hoja con una baldosa por app y «Apps»; vacía: «Aquí aparecerán tus apps…»), y desde
768 px «erplora.com» (quien administra y entró con su cuenta), «Cambiar de negocio» (app
instalada), «Asistente» (si está disponible) y la campana con su número;
en el móvil esas cuatro van en «Más opciones». Una línea fina de progreso debajo mientras hay
peticiones en curso. El contenido de la campana es del área «Avisos e impresión».

### Franja de conexión
Bajo la barra superior de cualquier pantalla con marco, solo mientras falta la red («Sin conexión a
Internet») o el hub no contesta («ERPlora no responde»). Sin botón; no se cierra.

### No podemos conectar con tu negocio
Lo que se ve al abrir ERPlora si el hub no contesta su contexto: un icono, el título («No podemos
conectar con tu negocio» o «Tu negocio no está disponible ahora mismo»), su explicación y
«Reintentar» / «Reintentar ahora». Sin menú ni barra. Mientras reintenta, el indicador de carga.

### Esta página no existe
Dentro del marco, con menú: «Esta página no existe», su explicación y «Ir a Inicio».

### Activación requerida
Pantalla sin marco con el logo, «Activación requerida», su explicación, «Reintentar» y «Cerrar
sesión». Hoy no se alcanza nunca: el shell no llega a marcar un negocio como pendiente de activación
(ver «Fuentes contrastadas»).

### Mi perfil
Desde «Perfil» en la tarjeta de usuario; «Atrás» lleva a Inicio. Cabecera con la foto («Cambiar
foto», «Quitar»), «Mi perfil», el nombre como encabezado, «Tu identidad y tus preferencias personales
en este negocio.» y dos distintivos (rol y tipo de cuenta). Tarjetas «Datos de la cuenta» (Nombre,
Apellidos, Correo electrónico, «Rol en este negocio», «Guardar mis datos»), «Preferencias» (Idioma,
Apariencia, «Usar la apariencia del negocio»), «PIN» (actual, nuevo, repetido y «Cambiar PIN» o
«Establecer PIN») y «Gestión de la cuenta» («Gestionar cuenta en erplora.com», «Borrar mi cuenta»).
Error al cargar: el aviso «No se pudo cargar el perfil» y el formulario vacío.

### Este dispositivo
Tarjeta de **Ajustes → General**, bajo su propio encabezado y antes de «Preguntar quién vende»
(Pinpad) y «Dispositivos»: el título, la explicación y dos opciones, «Compartido» y «Personal», cada
una con su consecuencia debajo. Sin ser administrador, desactivadas y con la nota de quién puede.
Error: un aviso rojo bajo las opciones.

### Inicio
Menú → «Inicio», y la primera pantalla tras entrar. Pestaña **Resumen**: el nombre del negocio (o el
saludo) y la fecha; la tarjeta de plantillas si el negocio está vacío y quien mira lo administra;
«Mis apps» (baldosas, «Ver todas las apps» en el móvil, «Añadir apps»); «Termina de configurar tu
negocio»; los paneles; y al pie la salud (impresora, WhatsApp) con «Ver sistema». Pestaña
**Actividad**: la tabla de las últimas ventas con búsqueda, filtros, vista tabla o tarjetas y 15 por
página. Cargando: baldosas grises, «Cargando widgets…», «Cargando…»; vacío y error por zona (ver
sus flujos). Aquí no sale la franja roja: la lista ya está a la vista.

### Termina de configurar tu negocio
Tarjeta de Inicio: título (o «Tu negocio está listo»), «{done} de {total} hechos», barra de progreso,
las filas (icono, título, descripción, nota, etiqueta y «Configurar» o «Dar permiso»), «Ver todo» /
«Ver menos» y «Pedírselo al asistente». Sin respuesta del hub, no sale.

### Franja «Todavía no puedes facturar»
Bajo la barra superior de cualquier pantalla con marco salvo el Resumen de Inicio: «Todavía no puedes
facturar», «No se podrá emitir ningún ticket ni factura hasta que configures esto:» y una línea por
cosa que falta con «Configurar» o quién puede. Plegada a una línea con «Ver qué falta» en pantallas
bajas. No se cierra.

### Paneles de Inicio
El tablero de la pestaña Resumen: tarjetas de las apps (cifra, lista, cronología, gráfico o trozo de
la app) y, mientras el negocio está vacío, «Configura tu negocio». El ⋮ abre «Personalizar panel»
(«Empezar desde un preset», «Activos · arrastra para reordenar», «Disponibles», «Cerrar»). Por tarjeta:
indicador mientras carga, «Sin datos», «No disponible». Vacío: «Panel vacío. Pulsa ⋮ para añadir
widgets.».

> **Integrador:** aquí se insertan, en este orden, las pantallas de «La vista de un módulo» (debe
> llamarse **Vista de un módulo**, la cita HUB_SHELL-F18), «Avisos e impresión», «Personas y
> permisos», «Aplicaciones, plan y archivos», «Sistema», «Ajustes del negocio y datos» (debe incluir
> **Ajustes**, que citan los flujos del servidor) y «Asistente».

## Flujos

El detalle de cada flujo (pasos, datos, fallos, implicados y QA) vive en `workflow/`, con la misma
gramática y el mismo prefijo. Huecos (`parcial`, `no hecho`): el porqué está en su línea `Estado:`.

| ID | Flujo | Estado | Fichero |
|---|---|---|---|
| HUB_SHELL-F01 | Entrar con la cuenta de erplora.com | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F02 | Entrar desde el panel de erplora.com sin volver a teclear la contraseña | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F03 | Elegir el PIN la primera vez que se entra en una caja | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F04 | Entrar con PIN | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F05 | Entrar pasando la placa | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F06 | Perder la sesión porque se abrió en otro dispositivo | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F07 | La sesión termina mientras se trabaja | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F08 | Cerrar la sesión de una caja que nadie toca | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F09 | Cambiar de usuario sin perder la venta | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F10 | Cerrar sesión | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F11 | Decidir si este dispositivo es compartido o personal | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F12 | Abrir un hub que todavía no está dado de alta | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F13 | Abrir ERPlora cuando el hub no contesta | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F14 | Saber que no hay conexión con el hub | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F15 | Moverse por el menú lateral y la barra superior | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F16 | Ir a erplora.com ya identificado | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F17 | Abrir una dirección que el hub no tiene | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F18 | Poner la pantalla de una app a pantalla completa | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F19 | Abrir el hub en el móvil y dejarlo como aplicación | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F20 | Actualizar la aplicación instalada cuando hay versión nueva | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F21 | Cambiar mis datos, foto, idioma y apariencia | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F22 | Cambiar mi PIN desde Mi perfil | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F23 | Gestionar o borrar mi cuenta de erplora.com | hecho | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
| HUB_SHELL-F25 | Ver el negocio de un vistazo al entrar | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F26 | Empezar con una plantilla de un negocio como el tuyo | parcial | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F27 | Seguir la lista «Termina de configurar tu negocio» | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F28 | Ver qué falta para poder facturar | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F29 | Dar a una app el permiso que le falta desde la lista | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F30 | Pedirle al asistente que repase la configuración | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F31 | Ver los pasos que aportan las apps | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F32 | Abrir una app desde «Mis apps» | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F33 | Ver los paneles de las apps en Inicio | parcial | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F34 | Personalizar el tablero de paneles | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F35 | Mantener los paneles al día sin recargar | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F36 | Consultar la actividad reciente | parcial | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F37 | Ver si la impresora y WhatsApp funcionan | parcial | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F38 | Ir a configurar desde el panel «Configura tu negocio» | hecho | [workflow/inicio.md](workflow/inicio.md) |
| HUB_SHELL-F39 | Ver Inicio al día después de importar una plantilla | hecho | [workflow/inicio.md](workflow/inicio.md) |

HUB_SHELL-F24 queda libre en el rango de Acceso.

> **Integrador:** aquí se añaden las filas de HUB_SHELL-F40 a HUB_SHELL-F199, área por área.

## Cobertura contra la referencia

**Acceso y sesión**

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Entrar con cuenta, segundo factor y Google | hecho | F01 |
| «Confiar en este dispositivo» decide si el dispositivo es de confianza | no hecho: el hub confía en todo acceso con cuenta; la casilla solo decide el PIN y si el navegador recuerda a la persona | F01 |
| Decir por qué no se entra (baja, ya no miembro) | parcial: misma frase que credenciales erróneas | F01 |
| Entrar desde el panel de gestión sin volver a identificarse | parcial: en el navegador no hace el dispositivo de confianza | F02 |
| Pedir el PIN propio en el primer acceso a una caja | parcial: solo con «Confiar» y no al entrar por el panel | F02, F03 |
| Rejilla de caras y PIN de longitud fija | parcial: la rejilla es la del arranque hasta recargar | F04 |
| Bloqueo por intentos con el tiempo de espera | hecho (lo aplica el servidor, HUB-F135) | F04 |
| Placa en el acceso | parcial: sin validar con hardware real | F05 |
| Placa en el relevo de turno | no hecho | F09 |
| Relevo de turno encima de la venta | parcial: el lanzador y la lista siguen siendo los de quien se fue hasta navegar | F09 |
| Cierre por inactividad configurable | parcial: solo la pantalla; sin aviso previo ni motivo | F08 |
| Avisar de la sesión desalojada por el plan | hecho | F06 |
| Dispositivo compartido o personal | hecho (rechazo en inglés) | F11 |
| Cerrar todas mis sesiones | no hecho (tampoco en el servidor) | — |
| Modo quiosco (una sola app, sin salir) | no existe; lo más cercano es pantalla completa | F18 |

**Navegación y marco**

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Arranque sin servidor: aviso y reintentar | hecho | F13 |
| Cambiar de negocio cerrando la sesión | parcial: no la cierra | F16 |
| Trabajar sin conexión con el hub | no existe (hub en la nube): solo se avisa | F14 |
| Franja persistente sin conexión | hecho | F14 |
| Menú filtrado por el rol | parcial: el menú enseña todo; recortan las pantallas | F15 |
| Lanzador de apps | hecho | F15, F32 |
| Página «no existe» con salida | hecho | F17 |
| Pantalla completa para el TPV y la cocina | hecho | F18 |
| Instalar como aplicación y abrir en el móvil | hecho (sin pedirlo nunca) | F19 |
| Avisar de una versión nueva de la app instalada | hecho | F20 |
| Avisar de una versión nueva del hub en el navegador | no hecho, a propósito: se aplica al recargar | F19 |
| Perfil: datos, foto, idioma, tema | hecho | F21 |
| Cambiar el propio PIN | hecho | F22 |
| Borrar la cuenta desde la app | hecho (en erplora.com) | F23 |

**Inicio y puesta en marcha**

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Guía de puesta en marcha con progreso | hecho | F27 |
| Pasos que nadie marca a mano: se comprueban | hecho | F27, F31 |
| Bloqueo legal visible en todas las pantallas | hecho | F28 |
| Delegar un paso que no es tuyo | hecho («Esto lo tiene que configurar un administrador.») | F27 |
| Plantilla de sector de un clic | parcial: fallo del catálogo mudo; «Ahora no» no se recuerda | F26 |
| Datos de ejemplo opcionales | no hecho: vienen siempre con la plantilla | F26 |
| Paneles por app con presets por sector | parcial: sin filtro por permiso en la pantalla | F33, F34 |
| Tablero guardado por persona | no hecho: se guarda por navegador | F34 |
| Paneles en vivo | hecho para lo que la app declara | F35 |
| Actividad reciente | parcial: importe ×100, solo ventas y estados mal nombrados | F36 |
| Estado de la impresora y de WhatsApp | parcial: detalle solo al pasar el ratón | F37 |

> **Integrador:** aquí van las tablas de las demás áreas.

## Datos: de quién es cada dato

Las pantallas no tienen base de datos ni migraciones: todo dato del negocio es del hub o de cada app y
se pide por su puerta (contexto público, sesión, consultas y órdenes). Lo único que el shell guarda es
lo que deja en **el navegador del dispositivo**. Inventario de lo de las áreas de Acceso e Inicio
(leído en `src/lib/*.ts` y `src/views/LoginPage.vue`):

| Dónde (navegador) | Qué guarda | Dato personal | Cuándo se borra |
|---|---|---|---|
| `erplora.session` | identificador, nombre, correo, foto, rol y permisos de quien tiene la sesión | sí | al cerrar sesión o perderla |
| `erplora.hub_session`, `erplora.hub_session_credential` | la sesión del hub y cómo se abrió (cuenta, PIN, placa) | credencial | al cerrar sesión |
| tokens de erplora.com (`erplora.access`, `erplora.refresh`) | la credencial de la cuenta | credencial | al cerrar sesión y en el relevo de turno; **no** si el acceso con cuenta falla después de que erplora.com acepte la contraseña, ni al entrar con PIN, ni con «Cambiar de negocio» [SEG] |
| `erplora.trusted_users`, `erplora.trusted` | id, nombre, **correo** e iniciales de quien entró con su cuenta en este navegador sin desmarcar «Confiar» (marcada por defecto, también donde no se ve); la rejilla de PIN enseña el correo | sí | nunca al cerrar sesión, al quitar el dispositivo ni al pasarlo a personal [SEG]; se recorta contra la lista del hub al abrir Acceso (conservando el correo de quien siga con PIN) y se vacía si nadie tiene PIN |
| `erplora.device_id` | el identificador de este dispositivo | no | nunca (es lo que el hub reconoce como de confianza) |
| `erplora.apps.usage` | cuántas veces se abre cada app | no | nunca |
| tablero de paneles (`okwb:dashboard-hub`) | qué paneles y en qué orden | no | nunca; compartido por quien use el navegador |
| `erplora.locale` | el idioma activo | no | se rehace en cada arranque |
| `erplora.theme`, `erplora.palette` | claves antiguas del tema | no | se borran al arrancar |
| `erplora.assistant.history` (sesión del navegador) | la conversación con el asistente | sí | al cerrar sesión, en el relevo y al cerrar la pestaña |

El PIN no se guarda nunca: viaja en el cuerpo de la petición y el ticket del código de verificación
vive solo en memoria. En memoria (no en el navegador) quedan además, tras cerrar sesión, la última
lista de puesta en marcha y, tras el relevo, el menú de apps de quien se fue.

El perfil, el PIN, el modo del dispositivo y los dispositivos son del hub (`HUB`, HUB-F132, HUB-F139,
HUB-F143); la lista de puesta en marcha y los paneles, del hub y de cada app (HUB-F34, HUB-F35).

> **Integrador:** aquí va lo que guardan en el navegador las demás áreas (impresión, avisos,
> asistente…).

## Reglas que no se rompen

Solo lo que el código hace cumplir:

- Sin sesión no se pinta el marco y toda dirección que la pide lleva a Acceso; con un hub sin alta,
  una sesión guardada se cierra y no hay pinpad (router, `authGate`).
- El shell no se monta hasta que el hub contesta su contexto (`bootUntilReachable`).
- El pinpad y la placa solo se ofrecen con dispositivo compartido, de confianza **según el hub** y
  un negocio que pregunta; sin respuesta del hub, no hay pinpad. La placa solo se atiende en el paso
  PIN.
- Un rechazo del hub solo cierra la sesión si una comprobación aparte confirma que está muerta (no
  por falta de rol ni por un corte de red), y la cierra una vez aunque haya muchas peticiones en vuelo.
- El relevo de turno no navega y no suelta la sesión anterior hasta tener la nueva; un PIN erróneo no
  cambia nada.
- El hub solo da el pase hacia erplora.com a una sesión abierta con la cuenta; a cualquier otra, la
  pantalla le abre el enlace normal, que pide la contraseña. El botón «erplora.com» solo se ofrece con
  el permiso de administrar; en la copia de Google Play no hay salida al plan ni a la gestión.
- Las franjas de bloqueo y de conexión no se pueden cerrar; la de bloqueo solo sale con un paso
  «Necesario para facturar» pendiente.
- Un panel que falla dice «No disponible»: nunca un valor viejo ni inventado.
- Cada cadena nueva existe en inglés y en español (test de paridad de `src/i18n/`); ninguna pantalla
  pinta un código interno del hub (`screens-never-paint-a-runtime-code.test.ts`), salvo cinco que, a
  propósito, pintan la frase que dio el hub cuando no tienen una propia (lista en el test); «Este
  dispositivo» es una de ellas.

Lo que hoy **no** se cumple y no es una regla, sino un hueco de seguridad [SEG] (detalle en sus
flujos): los tokens de erplora.com de un acceso fallido se quedan y los usa la sesión siguiente
(HUB_SHELL-F01); tras el relevo el lanzador y la lista son los de quien se fue (HUB_SHELL-F09); una
lectura rota del dial desarma el cierre por inactividad (HUB_SHELL-F08); los correos de la rejilla
sobreviven al cierre de sesión, a quitar el dispositivo y a pasarlo a personal (HUB_SHELL-F04);
«Cambiar de negocio» no cierra la sesión (HUB_SHELL-F16).

> **Integrador:** aquí van las reglas de las demás áreas.

## Lo que NO hace, a propósito

- No pide instalar ERPlora como aplicación ni interrumpe para ofrecerlo: el QR espera en el menú
  (hub#685, hub#1715).
- La franja sin conexión no tiene «Reintentar»: recargar perdería lo tecleado y no arreglaría la red;
  el reintento vive en la pantalla que falló.
- No adivina direcciones (`/tpv` → Vender): el shell no conoce los ids de las apps.
- La pantalla nunca decide si un PIN es correcto: lo decide el hub.
- Las apps no viven en el menú lateral: se abren desde el lanzador y desde Inicio.
- No avisa de una versión nueva del hub en el navegador: se aplica sola al recargar.
- No ofrece «Actualizar plan» ni «erplora.com» en la copia de Google Play (hub#756).

> **Integrador:** aquí va lo de las demás áreas.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- **Menú por rol.** Square y Toast esconden lo que el rol no puede usar; aquí el empleado ve Empleados,
  Mi plan, Apps, Sistema y Ajustes y las pantallas le recortan dentro (HUB_SHELL-F15).
- **Cierre por inactividad.** ¿Aviso con cuenta atrás antes de cerrar y una frase después? Hoy vuelve
  al pinpad sin decir nada (HUB_SHELL-F08).
- **Tablero por persona o por dispositivo.** Hoy se guarda en el navegador y lo comparten todos los de
  una caja (HUB_SHELL-F34).
- **Placa en el relevo de turno** (HUB_SHELL-F09).
- **PIN tras entrar desde el panel.** ¿Pedirlo también ahí, como tras el acceso con «Confiar»?
  (HUB_SHELL-F02, HUB_SHELL-F03).
- **Correos en la rejilla de caras.** La rejilla de una caja compartida enseña el correo de quien entró
  allí con su cuenta, guardado en el navegador y que no se borra al cerrar sesión; el hub, en cambio,
  nunca da el correo en su lista pública.
- **La casilla «Confiar en este dispositivo».** Hacerla real (que el hub no confíe sin ella) o
  quitarla; hoy su ⓘ promete lo que no pasa.
- **Pantalla «Activación requerida».** Retirarla o volver a cablearla: hoy no se alcanza.

> **Integrador:** aquí van las dudas de las demás áreas.

## Fuentes contrastadas

- `hub` HUB-F138 (servidor) dice que el historial del asistente de quien se fue sigue en pantalla
  (hub#1544); el relevo del shell lo borra (`src/lib/user-switch.ts`, `switchUser`) y lo cubre un test
  de hub#1544. HUB-F138 dice además «o pasa su placa»: el relevo no acepta placa.
- `hub` HUB-F133 dice que la lista de personas nunca lleva el correo; la rejilla del shell enseña el
  correo guardado en el navegador (`LoginPage.vue`, tarjeta de persona).
- `hub` HUB-F132 dice que la pantalla pide el PIN tras entrar por primera vez con la cuenta en un
  dispositivo compartido; solo lo hace si se marcó «Confiar» y nunca al entrar por el pase del panel.
- `hub` HUB-F136 dice que el cierre por inactividad lo hace solo la pantalla: confirmado
  (`src/lib/idle-logout.ts`), y además sin aviso.
- `hub` y el manual (`hand-book/hub/01-acceso-y-navegacion.md`, «Pantalla de activación cuando el Hub
  no puede confirmar un acceso válido»): la pantalla «Activación requerida» no se alcanza nunca;
  `src/lib/entitlement.ts` solo pone `unknown` o `unlocked`, nunca `needs_activation`.
- Manual 01: «En móvil, las acciones secundarias se agrupan en **Más**»: el botón no tiene texto, es
  ⋮ con el nombre accesible «Más opciones».
- Manual 02: «el tablero incluye una entrada de datos del núcleo»: solo mientras el negocio no tiene
  apps (hub#2199).
- `cash_register` CASH_REGISTER-F12 dice que el empleado no ve «Caja (sesión actual)»: la pantalla no
  filtra paneles por permiso (`DashboardPage.vue`, `hasPermission: () => null`); lo ve en el catálogo
  y, si está puesto, sale «No disponible».
- `src/i18n/locales/es.ts`: `dashboard.noWidgets` («Ninguna app instalada ofrece widgets todavía.»)
  no lo usa ninguna pantalla.
- `system.health.printerUnknownDetail` promete «Volveremos a comprobarlo solos»; Inicio solo lo relee
  al volver a la pantalla.
- `CLAUDE.md` de la raíz («nunca `fill="outline"` en `ion-input`…») está desfasado: la regla del código
  es `fill="outline"` con `mode="md"` más el gancho de `src/lib/ionic-fill.ts`.
- `es.ts` `login.popoverBody` («Si no la marcas, siempre tendrás que iniciar sesión con email») es
  falso: el hub vuelve de confianza el dispositivo en todo acceso con cuenta (HUB_SHELL-F01).
- `es.ts` `shell.changeHubBody` («Este dispositivo cerrará la sesión de este negocio…»): no la cierra
  (HUB_SHELL-F16).
- `es.ts` `notFound.body` dice que las apps «se abren desde el menú»: no están en el menú lateral,
  se abren desde el lanzador de la barra o desde Inicio.
- `src/lib/dashboard-activity.test.ts` alimenta `total: '12.5'` (euros) cuando `sales.list` da
  céntimos: no detecta el importe ×100 de HUB_SHELL-F36.
- QA `qa-hub-restaurant` §7.00 pide «recargar y volver a entrar: no reaparece onboarding»: la tarjeta
  de plantillas reaparece al recargar mientras el negocio siga sin apps («Ahora no» no se recuerda).

> **Integrador:** aquí van las discrepancias de las demás áreas.
