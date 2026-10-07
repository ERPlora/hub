# WORKFLOW — Hub · pantallas
Prefijo: HUB_SHELL
Alcance MVP: transversal

> Contrato de comportamiento de las pantallas del hub (`apps/web`, Vue + Ionic + OutfitKit),
> pm#620, pm#621. Se lee antes de tocar el código de `apps/web/src`, junto con el fichero del área que
> se va a tocar, y se actualiza en la misma PR que cambie un comportamiento. Lo que hace el servidor
> detrás de cada pantalla está en `hub/WORKFLOW.md` (prefijo `HUB`); lo técnico, en
> `architecture/hub/apps/web.md` y vecinos. La aplicación instalada es `apps/tauri/WORKFLOW.md`
> (`HUB_APP`). Índice partido: el detalle de cada área vive en `workflow/<área>.md`.

## Para qué sirve y para quién

Las pantallas del hub son lo que una persona del negocio tiene delante todo el día: entra con su cuenta o con su PIN, ve **Inicio**, abre sus apps (Ventas, Caja, Agenda…) desde el lanzador, y el administrador gestiona desde el menú a las personas, las apps, el plan, el sistema y los ajustes. El shell es el marco común a todas las apps instaladas: la entrada y la sesión, el menú y la barra superior, la campana, el asistente, el diálogo que pide el PIN de un responsable, la impresión del tique al cobrar, las franjas que avisan de que no se puede facturar o no hay conexión, y la vista donde se monta cada app. Lo usan el **administrador** (todo), el **responsable** (aprueba con su PIN, ve cifras; en pantalla el rol se llama «Encargado»), el **empleado** y el **cajero** (el perfil que añade Ventas), en la caja compartida, en la tableta de cocina, en el portátil y en el móvil.

## Cómo está partido este documento

Un worker lee este índice **y** el fichero del área que va a tocar: cada fichero de área lleva, además de sus flujos, su referencia, lo que hay que tener antes, su cobertura, sus datos, sus reglas, lo que no hace, sus dudas y sus fuentes. Aquí queda lo común y el diccionario de pantallas.

| Área | Fichero | IDs | Vistas y componentes (`views/`, `components/`) |
|---|---|---|---|
| Acceso, navegación y perfil | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) | F01–F23 | LoginPage, ActivationPage, AuthenticatedChrome, AppTopbar (salvo la campana), AppPage, NotFoundPage, NotFoundState, ProfilePage, UserSwitchOverlay, DeviceModeCard, OfflineStrip, BootUnreachable, SidebarInstallQr, SidebarAppUpdate |
| Inicio y puesta en marcha | [workflow/inicio.md](workflow/inicio.md) | F25–F39 | DashboardPage, SetupChecklistCard, SetupBlockingStrip, BlueprintHeroCard, MyAppsCard |
| La vista de un módulo | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) | F40–F56 | ModuleView, ModuleSettingsForm, ModulePlanPanel, ElevationDialog |
| Avisos e impresión | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) | F60–F77 | la campana de AppTopbar |
| Personas y permisos | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) | F80–F104 | EmployeesPage, EmployeeFormPage, RolesPanel, ApprovalsPanel, ApiKeysPanel, ApiDocsPage, PinPolicyCard, DevicesCard |
| Aplicaciones (1.ª mitad del área «Aplicaciones, plan y archivos») | [workflow/aplicaciones.md](workflow/aplicaciones.md) | F105–F125 | AppsPage |
| Plan y archivos (2.ª mitad) | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) | F126–F134 | BillingPage, PlanLimitsPanel, FilesPage, FilePreviewModal |
| Sistema | [workflow/sistema.md](workflow/sistema.md) | F135–F149 | SystemPage |
| Ajustes del negocio y datos | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) | F155–F181 | SettingsPage, WhatsAppConnect, DataPanel, ExportPanel, ImportPanel, ImportPermissionsConsent, ResetPanel |
| Asistente | [workflow/asistente.md](workflow/asistente.md) | F185–F199 | AssistantDrawer |

Libres: F24, F57–F59, F78–F79, F150–F154, F182–F184. Retirados por duplicados (cabecera `[retirado]` en su fichero): F55 (lo sustituye F18), F141 (F128) y F166 (F75).

Ficheros de `src/lib/` (y `src/router/`) por área:

| Área | Ficheros |
|---|---|
| Acceso, navegación y perfil | `session.ts`, `courier.ts`, `cloud.ts`, `runtime.ts`, `config.ts`, `user-switch.ts`, `pin-policy.ts`, `pin-length.ts`, `pinpad-dial.ts` (también lo usa la tarjeta Pinpad), `device-mode.ts`, `device.ts`, `boot.ts`, `boot-screen.ts`, `offline.ts`, `immersive.ts`, `change-hub.ts`, `install-qr.ts`, `deep-link.ts`, `user-profile.ts`, `branding.ts`, `routes.ts`, `hash-tab.ts`, `tabbar-peek.ts`, `list-load-state.ts`, `shell.ts`, `shell-menu.ts`, `nav.ts`, `idle-logout.ts`, `session-end-reason.ts`, `pwa.ts`, `theme.ts`, `viewport.ts`, y `router/` |
| Inicio y puesta en marcha | `dashboard-widgets.ts`, `dashboard-activity.ts`, `dashboard-heading.ts`, `dashboard-blueprint-widget.ts`, `blueprint-hero.ts`, `setup-status.ts`, `app-usage.ts` |
| La vista de un módulo | `module-loader.ts`, `module-url.ts`, `module-settings.ts`, `module-quota.ts`, `module-usage.ts`, `module-plan-link.ts`, `protects.ts`, `lock-refusal.ts`, `elevation.ts`, `elevation-label.ts`, `module-failure-message.ts` (también Aplicaciones), `runtime-error-sentence.ts`, `invalid-field.ts` (también Personas), `slot-fillers.ts`, `outfitkit-skew.ts`, `teleported-styles.ts` |
| Avisos e impresión | `bell-counters.ts`, `bell-notice.ts`, `notice-listening.ts`, `notice-tap.ts`, `notification-permission.ts`, `appointment-notice.ts`, `print.ts`, `print-on-sale.ts`, `print-on-sale-notice.ts`, `print-comanda.ts`, `print-comanda-notice.ts`, `print-host.ts`, `print-host-registration.ts`, `print-drain.ts`, `print-enqueue.ts`, `print-alert.ts`, `print-coverage.ts`, `native-print.ts`, `receipt-template.ts`, `sale-document.ts`, `printer-discovery.ts`, `toast.ts`, `bridge-transport.ts`, `client-instance.ts` (`HUB_APP` cuenta el transporte de la app) |
| Personas y permisos | `hub-users.ts`, `approvals.ts`, `api-keys.ts`, `api-docs.ts`, `devices.ts`, `badge-scanner.ts`, `nfc-badge.ts`, `platform-failure.ts` |
| Aplicaciones | `apps-catalog.ts`, `apps-grid.ts`, `apps-list-columns.ts`, `installed-app-actions.ts`, `module-updates.ts`, `module-update-notice.ts` (también la campana y Sistema), `module-capabilities.ts` |
| Plan y archivos | `entitlement.ts`, `upgrade-plan-link.ts`, `management-link.ts`, `saas-door.ts`, `open-external.ts`, `save-download.ts`, `media.ts`, `file-preview.ts`, `file-preview-loaders.ts` |
| Sistema | `system.ts`, `system-tabs.ts`, `system-health.ts`, `system-metrics.ts`, `system-usage.ts`, `dead-letter.ts` (también la campana), `update-history.ts`, `app-update.ts` (también «Actualizar ERPlora» del menú, HUB_SHELL-F20), `error-report.ts`, `device-permission.ts` y `local-network-permission.ts` (la entrada desde Sistema; el resto es de `HUB_APP`) |
| Ajustes del negocio y datos | `settings-tabs.ts`, `hub-settings.ts`, `timezone.ts`, `import-retry.ts`, `import-permissions.ts`, `app-names.ts`, `whatsapp-connect.ts`, `autostart.ts` (el interruptor; el arranque es de `HUB_APP`) |
| Asistente | `assistant.ts`, `assistant-confirm.ts`, `assistant-danger.ts`, `assistant-grounding.ts`, `assistant-history.ts`, `assistant-markdown.ts`, `assistant-plan.ts`, `assistant-report.ts`, `assistant-routes.ts`, `assistant-setup.ts` |
| Común (lo gobierna este índice, «Lo que comparten todas las pantallas») | `money.ts`, `format-datetime.ts`, `data-table-labels.ts`, `iconify.ts`, `icons.ts`, `ionic-fill.ts`, `ionic-fill.boot.ts`, `ionic-registry-hook.ts`, `ionic-select-interface.ts`, `ionic-select-interface.boot.ts`, `ionic-select-text.ts`, `ionic-select-text.boot.ts`, `ionic-wc.ts`, y el componente HubIcon |

Sin comportamiento visible y sin flujo: `visual-baseline-gate.ts` (herramienta de tests visuales), `src/parked/` (código sin enrutar) y el componente GrantFilePicker (adjunto de documentos del otorgamiento fiscal, hub#1293: hoy no lo monta ninguna pantalla; si vuelve, es de «Ajustes del negocio y datos»).

**Piezas que cuentan dos áreas** (al cambiar una, se revisa la otra): Ajustes › General (pestaña de Ajustes; tarjetas de Acceso y de Personas); Ajustes › Impresión (la pestaña es de Ajustes; la tarjeta «Estado de impresión», de Avisos, F75; la fila «Impresoras y tique», F165 y F76); Sistema › Plan y límites (la pestaña es de Sistema; el flujo, de Plan y archivos, F128); la vista de un módulo a pantalla completa (F18, de Acceso); «Tus apps» de Sistema › Actualizaciones y la campana (F143 y F119); la salud de la impresora en Inicio y en Sistema › Recursos (F37 y F137, mismas frases); eventos caídos en la campana y en Sistema (F62 y F145); «Actualizar ERPlora» del menú (F20) y Sistema › Actualizaciones.

## Referencia adoptada

ERPlora no inventa flujos de pantalla: adopta los de la plataforma de los productos de referencia (Square, Toast, Odoo, Shopify, Lightspeed, Business Central; Zapier, Make y Shopify Flow para la bandeja de eventos fallidos). Lo que adopta cada área, con su contraste, está en su fichero:

- Acceso, navegación y perfil (PIN y relevo de turno de Square y Toast, PIN fijo de Clover, placa, arranque sin servidor, franja sin conexión, página inexistente, pantalla completa): `workflow/acceso-y-navegacion.md`.
- Inicio (guías de arranque de Shopify, Odoo y Square; paneles por sector, ADR-0054): `workflow/inicio.md`.
- Vista de un módulo (estados de carga, aprobación del encargado, caja cerrada, el hub no vende): `workflow/vista-de-modulo.md`.
- Avisos e impresión (tique en el terminal que cobró, comanda al disparar, campana derivada): `workflow/avisos-e-impresion.md`.
- Personas y permisos (Square, Toast, Lightspeed, Odoo; Clover para el PIN; dispositivos de Google, Apple y Shopify): `workflow/personas-y-permisos.md`.
- Aplicaciones (Odoo, Shopify, WordPress.org): `workflow/aplicaciones.md`; plan y archivos (reglas de las tiendas, gestor tipo Drive): `workflow/plan-y-archivos.md`.
- Sistema (Square/Toast hardware, Odoo, Zapier/Make/Shopify Flow): `workflow/sistema.md`.
- Ajustes y datos (Odoo, Square, Shopify, Business Central; Embedded Signup de Meta): `workflow/ajustes-y-datos.md`.
- Asistente (Copilot, Odoo AI, Joule, Sidekick, Square AI, Toast IQ): `workflow/asistente.md`.

## Antes de empezar

Lo común a todas las pantallas:

- El hub tiene que estar **dado de alta** en erplora.com (llega así al crearlo desde el panel); uno sin alta solo enseña Acceso y no deja entrar (HUB_SHELL-F12).
- Cada dispositivo necesita **una primera entrada con una cuenta de erplora.com** miembro del negocio, por el formulario o desde la app instalada (en un navegador, entrar por el pase del panel no cuenta): es lo que lo hace de confianza y enciende el PIN en él (HUB_SHELL-F01, F02, F04).
- Lo que toca el plan o la cuenta (Mi plan, la pestaña Plan de una app, el bloqueo por suscripción, ir a erplora.com) pide una sesión **con cuenta**, no de PIN (ver «Lo que comparten todas las pantallas»).
- Para facturar: razón social y NIF en Ajustes › Negocio, y la vía hasta la AEAT (módulo VeriFactu); la franja roja dice qué falta (HUB_SHELL-F28).

Configuración inicial, paso a paso:

1. Entra con tu cuenta en la caja, marca «Confiar en este dispositivo» y elige tu PIN (HUB_SHELL-F01, F03).
2. En **Inicio**, usa una plantilla de tu sector o añade apps (HUB_SHELL-F26, F32, F109).
3. Sigue «Termina de configurar tu negocio» empezando por lo que es «Necesario para facturar» (HUB_SHELL-F27 a F31).
4. Da de alta al equipo en **Empleados** (HUB_SHELL-F81, F82) y comprueba la salud de la impresora en **Inicio** (HUB_SHELL-F37).
5. Escanea el QR del menú desde el móvil si vas a usarlo (HUB_SHELL-F19).

Lo que pide cada área: acceso (caja compartida y PIN) en `acceso-y-navegacion.md`; la pestaña Ajustes o Plan de una app en `vista-de-modulo.md`; impresión sin diálogos y avisos con la pantalla apagada en `avisos-e-impresion.md`; invitaciones, roles y llaves de API en `personas-y-permisos.md`; apps de pago en `aplicaciones.md`; facturas en `plan-y-archivos.md`; eventos caídos en `sistema.md`; «Tu número» e importar en `ajustes-y-datos.md`; el nivel del asistente en `asistente.md`.

## Lo que comparten todas las pantallas

Vale para todas las áreas; quien escribe una pantalla nueva lo cumple sin volver a decidirlo.

- **Un solo marco.** Toda pantalla con sesión va dentro del mismo esqueleto: barra superior, franjas (bloqueo de facturación y conexión) entre la barra y el contenido, el contenido y, si la pantalla tiene secciones, pestañas abajo. Solo Acceso, «No podemos conectar con tu negocio» y «Activación requerida» van sin marco. Las pestañas viven en la dirección (`/settings#data`).
- **Sin sesión no hay marco.** El menú, la barra, el asistente, el diálogo de aprobación y el relevo de turno solo existen con una sesión abierta.
- **Sesión de PIN frente a sesión con cuenta de erplora.com.** Una sesión abierta con PIN o placa no lleva el token de erplora.com (`getAccessToken()`): al abrirla se borra el que hubiera, y el relevo con PIN también lo borra (hub#2506). Sin él no hay: bloqueo por suscripción ni rebote de apps fuera del plan (la app se abre y falla en cada pantalla, HUB_SHELL-F41, F49), estado de la pestaña Plan de una app (F46), facturas ni suscripciones en Mi plan (F126, F127), pase a erplora.com (F16, F129) ni «Gestionar cuenta» en Mi perfil (F23). Quien escriba una de esas pantallas dice qué ve una sesión de PIN.
- **Cuatro estados, cada uno con su frase.** Cargando (indicador o baldosas grises con su frase para el lector de pantalla), vacío (qué aparecerá y cómo llenarlo), error (lo que pasó y, donde se puede, «Reintentar») y sin conexión (la franja de HUB_SHELL-F14). Un rechazo por permiso esconde la acción o dice quién puede hacerla, nunca el nombre técnico del permiso.
- **Una lectura que falla no se pinta como vacía, como cero ni como «todo en orden»** (hub#770, hub#894): dice que no se pudo y conserva lo que ya tenía (`*load-refused*`, `apps-refresh-keeps-the-screen`). **Hoy se incumple** en: Sistema › Eventos caídos para quien no administra («Todo en orden», F145); Sistema › Actualizaciones (historial ilegible = «No te hemos cambiado nada», F142); Sistema › Registros («Sin eventos» bajo el error, F144); el refresco de Plan y límites (números viejos en silencio, F128, F141); Ajustes sin respuesta (España, EUR y español, F155); Empleados › Personal y Roles («Aún no hay…» bajo el error, F80, F91); una app sin permiso («Aquí todavía no hay nada», F41); la pestaña Plan con erplora.com caído (F46); la comanda con lectura fallida (F72); la puesta en marcha del asistente (reutiliza la lista anterior, F196); el catálogo de plantillas de Inicio (mudo, F26).
- **Tres tamaños.** Móvil (menos de 768 px): menú en cajón, acciones de la barra plegadas en «Más opciones», rejillas a dos filas por debajo de 540 px. Tableta (768–991 px): menú en cajón, barra completa. Escritorio (992 px o más): menú fijo que se pliega a iconos. Con poca altura (500 px o menos) la franja de bloqueo se pliega a una línea. QA mide 1440, 834 y 390.
- **Idiomas.** El texto sale de `src/i18n/locales/`: el inglés es la fuente y cada cadena nueva lleva su español (test de paridad). El idioma es el de la persona (Mi perfil), si no el del negocio, si no español. Los nombres de las apps los traduce el hub. Nunca se pinta un código interno (`hub.users.pin_in_use`) ni una traza.
- **Dinero.** Con la moneda del hub y los separadores del idioma (`lib/money.ts`). El hub y las apps guardan céntimos: se pinta con `formatMoney`, que divide según los decimales de la moneda; `formatAmount` es solo para cifras que ya llegan en euros. Confundirlas multiplica por cien (HUB_SHELL-F36). Fechas y horas, por `lib/format-datetime.ts`.
- **Campos.** El shell fija el modo `ios` de Ionic, en el que `fill="outline"` no pinta nada en `ion-input`, `ion-select` e `ion-textarea`. Los campos del shell declaran `fill="outline"` junto a `mode="md"` (lo vigila `theme/ionic-fill-needs-md.test.ts`) y un gancho que se carga antes que Ionic (`lib/ionic-fill.ts`) pone `mode="md"` a todo campo con `fill` que no declare modo, módulos incluidos (hub#760, hub#1060). En `ion-button`, `fill="outline"` sí pinta.
- **Iconos.** Por el componente HubIcon y el registro de Iconify horneado en la compilación (`ion:` por defecto): sin SVG sueltos y sin bajar nada de la red.
- **El PIN de un responsable.** Cuando una orden necesita la aprobación de un responsable, el diálogo «Hace falta una aprobación» se abre encima de la pantalla que sea, lo abre el transporte y no la app, y la orden se repite sola al aprobarla (HUB_SHELL-F51).
- **Confirmaciones y avisos.** Lo irreversible se confirma con un diálogo que dice la consecuencia; lo que acaba de pasar se dice con un aviso breve. El botón Atrás de Android cierra antes la hoja o el diálogo que haya encima.
- **El hub no vende** (Google Play, Microsoft Store, anti-steering, hub#479, hub#756): informa del plan y dice dónde se gestiona; contratar, cambiar y pagar son de erplora.com. La copia de Google Play no lleva «Actualizar plan», «erplora.com» ni «Ver planes»; el pago del asistente solo se ofrece a quien administra. Guardarraíl: `no-purchase-steering.test.ts`.

**Los nombres y hashes de las pestañas de Ajustes y de Sistema son contrato** con los módulos y el servidor. Antes de renombrar o mover una, se revisa:

| Qué | Dónde |
|---|---|
| Hash `#hub`, `#business`, `#tickets`, `#permissions`, `#data` (Ajustes; `#tax` es alias de Negocio y no caduca: `verifactu` v1.5.35 publicada lo usa) | enlaces del shell y de Rust (los vigila `lib/settings-tab-links.hub2016.test.ts`); **no vigilados**: `schedules` (`/settings#hub`, `erp-schedules-hours.ts:1265`), versiones publicadas de `verifactu` (`/settings#tax`), las rutas que siembra el asistente |
| Hash `#resources`, `#plan`, `#updates`, `#events`, `#logs` (Sistema; `#backups` retirado) | la campana, Apps (`see_hub_updates`), Inicio |
| Rótulos «Ajustes → Permisos», «Ajustes › Negocio» | textos del shell (`importPermissions.intro`, `importPermissions.grantError`, `importPage.reasonCapabilityGrantsNotPortable`), la nota del hub en `export_import.rs:812-817`, el «Ir a Permisos» de Apps |
| Rótulo en flujos | HUB_SHELL-F155 a F181, F11, F99 a F104; servidor: `negocio-y-datos.md` (con «Ajustes › Hub»), HUB-F58, HUB-F111, HUB-F201; módulos en `origin/main`: `verifactu` (28 menciones), `flows` (4), `printing` (3), `inventory` (1), `schedules` (1); recorrido `cadena-fiscal.md` |

**Las claves de los roles de fábrica (`admin`, `manager`, `employee`) son contrato** con erplora.com, los módulos y las traducciones: no se renombran. Están en el shell (`ADMIN_ROLES`, `ACCOUNT_ROLES`, `employees.roles.*`), en el runtime (`BASE_ROLES`, `is_grantable_account_role`, `is_admin_role`), en el `HUB_ROLES` de erplora.com y en el `role_permissions` de cada módulo; afectan a HUB_SHELL-F81, F82, F84, F91, F92, a HUB-F145 a F150 y F152 y a los flujos de módulo que conceden por rol (SALES-F14).

**Qué revisar si cambia el formato de los errores del servidor** (el sobre `{ok:false, error:{code, message, …}}` del hub, HUB-F14):

- El SDK de los módulos (`packages/module-sdk/src/index.ts`, `unwrap`): lee `code`, `message`, `permission`, `fields`/`field`, `retry_after_secs`, `module`, `query`, `reason`, `missing` y el 401 sin código. De él dependen los 27 módulos: los diez con traducción propia por código (`services`, `staff`, `tables`, `sales`, `pricing`, `appointments`, `invoice`, `kitchen`, `reservations`, `schedules`) y todos los que pintan `e.message`. Flujos: HUB_SHELL-F44, F51 (códigos `hub.elevation.*` y `requires_elevation`), F52, F53.
- Apps (`lib/module-failure-message.ts`: `detail`, `params`, `code`); Personas y permisos (`lib/invalid-field.ts`, `lib/platform-failure.ts`: `field`, `reason`, `module`, `query`).
- El consumo del plan (`lib/module-usage.ts` en `ModulePlanPanel`: `permission_denied` / `requires_elevation` no se avisan, F47); el bloqueo por intentos (`lib/lock-refusal.ts`: `retryAfterSecs`, acceso y F51); el bloque de plan del hub (`revalidation` del entitlement, F49).
- La impresión: el alta del dispositivo (`print-host.ts` `postToRuntime`: `error.code`, F73) y la cola (`print-enqueue.ts`: `ok`, `liveHosts`, F70, F72, F77).

## Pantallas

Diccionario de nombres de pantalla de todo ERPlora: los flujos de este componente las citan en `Pantalla:` por el nombre exacto del encabezado, y los del servidor y de los módulos como `Pantalla: HUB_SHELL: <nombre>`. Lista canónica, una por línea: `/tmp/wf-hub/int/pantallas.txt` en la oleada de integración. Cuando una pantalla la cuentan dos áreas, la entrada dice qué parte es de cada una.

### Acceso
Al abrir el hub sin sesión; sin menú ni barra. Arriba a la derecha el tema (sol o luna); en el centro el logo del negocio con «Entra en tu negocio», «Introduce tu PIN», «Crea tu PIN de acceso» o «Verifica que eres tú»; encima, cuando toca, el aviso de sesión desalojada (F06) o el del pase del panel (F02). Pestañas «PIN» y «Email» si el dispositivo ofrece PIN. **Email**: «Email», «Contraseña», «Confiar en este dispositivo» con su ⓘ, «Entrar», «Continuar con Google» y, sin pestañas, «Usar PIN en su lugar». **PIN**: «…o pasa tu placa…», «Elige tu usuario» con una tarjeta por persona, la cara elegida y el teclado con «Cambiar usuario». Crear PIN y código de verificación: un paso cada uno. Cargando: el círculo en el botón; error: la frase en rojo bajo el control. Área: Acceso.

### Cambiar de usuario
Ventana encima de la pantalla en curso, desde la tarjeta de usuario del menú en una caja compartida: «La venta sigue abierta…», «¿Quién se pone?» con las caras (o «Su nombre» y «Continuar»), el teclado con «Otra persona», y «Cancelar». Error: la frase en rojo bajo el teclado; no se cierra. Área: Acceso.

### Menú lateral
Fijo en escritorio, en cajón en tableta y móvil. Arriba la **tarjeta de usuario** («Perfil», «Cambiar de usuario» solo en caja compartida, «Cerrar sesión»). Secciones «General» (Inicio, Empleados, Archivos) y «Cuenta» (Mi plan, Apps, Sistema, API si está publicada, Ajustes); las apps no están aquí. Pie: «Actualizar ERPlora ({version})» (app instalada, versión nueva, quien administra), el QR «Ábrelo en el móvil», «Actualizar plan» (salvo Google Play), el logo y la versión. Área: Acceso.

### Barra superior
Botón del menú (tableta y móvil), «Atrás» en las de detalle, plegar el menú (escritorio), el título, las acciones de la pantalla, el lanzador «Mis apps» (hoja con una baldosa por app y «Apps»; vacía: «Aquí aparecerán tus apps…») y desde 768 px «erplora.com», «Cambiar de negocio» (app instalada), «Asistente» y la campana; en el móvil esas cuatro van en «Más opciones». Línea fina de progreso mientras hay peticiones. Área: Acceso; la campana es de Avisos e impresión.

### Franja de conexión
Bajo la barra superior, solo mientras falta la red («Sin conexión a Internet») o el hub no contesta («ERPlora no responde»). Sin botón; no se cierra. Área: Acceso.

### No podemos conectar con tu negocio
Al abrir ERPlora si el hub no contesta su contexto: icono, título («No podemos conectar con tu negocio» o «Tu negocio no está disponible ahora mismo»), explicación y «Reintentar» / «Reintentar ahora». Sin marco. Mientras reintenta, el indicador de carga. Área: Acceso.

### Esta página no existe
Dentro del marco: «Esta página no existe», su explicación y «Ir a Inicio». La usa también la vista de un módulo para una pestaña que no existe. Área: Acceso.

### Activación requerida
Sin marco: logo, «Activación requerida», explicación, «Reintentar» y «Cerrar sesión». Hoy no se alcanza nunca (ver `acceso-y-navegacion.md`, «Fuentes contrastadas»). Área: Acceso.

### Mi perfil
Desde «Perfil» en la tarjeta de usuario. Foto («Cambiar foto», «Quitar»), nombre, rol y tipo de cuenta; tarjetas «Datos de la cuenta» («Guardar mis datos»), «Preferencias» (Idioma, Apariencia), «PIN» («Cambiar PIN» o «Establecer PIN») y «Gestión de la cuenta» («Gestionar cuenta en erplora.com», «Borrar mi cuenta»). Error al cargar: «No se pudo cargar el perfil» y el formulario vacío. Área: Acceso.

### Inicio
Menú › «Inicio», y la primera pantalla tras entrar. Pestaña **Resumen**: nombre del negocio y fecha; la tarjeta de plantillas si el negocio está vacío y quien mira lo administra; «Mis apps» (baldosas, «Añadir apps»); «Termina de configurar tu negocio»; los paneles; al pie la salud (impresora, WhatsApp) con «Ver sistema». Pestaña **Actividad**: las últimas ventas con búsqueda, filtros, tabla o tarjetas y 15 por página. Cargando: baldosas grises; vacío y error por zona. Aquí no sale la franja roja. Área: Inicio.

### Termina de configurar tu negocio
Tarjeta de Inicio: título (o «Tu negocio está listo»), «{done} de {total} hechos», barra, las filas (icono, título, descripción, etiqueta y «Configurar» o «Dar permiso»), «Ver todo» / «Ver menos» y «Pedírselo al asistente». Sin respuesta del hub, no sale. Área: Inicio.

### Franja «Todavía no puedes facturar»
Bajo la barra de cualquier pantalla con marco salvo el Resumen de Inicio: «No se podrá emitir ningún ticket ni factura hasta que configures esto:» y una línea por cosa que falta con «Configurar» o quién puede. Plegada a «Ver qué falta» en pantallas bajas. No se cierra. Área: Inicio.

### Paneles de Inicio
El tablero de Resumen: tarjetas de las apps (cifra, lista, cronología, gráfico) y, con el negocio vacío, «Configura tu negocio». El ⋮ abre «Personalizar panel» (presets, «Activos · arrastra para reordenar», «Disponibles»). Por tarjeta: indicador, «Sin datos», «No disponible». Vacío: «Panel vacío. Pulsa ⋮ para añadir widgets.». Área: Inicio.

### Vista de un módulo
Desde el lanzador «Mis apps», «Mis apps» de Inicio o «Abrir» en Apps; dirección `/m/<app>/<pestaña>`. Arriba el nombre traducido de la app; en medio su pantalla; abajo las pestañas, con «Ajustes» y «Plan» si la app los declara. Cargando: esqueleto. Sin red: «Sin conexión a Internet» con «Reintentar». Fallo: «No se pudo cargar el módulo.». Vacía: «Aquí todavía no hay nada». No instalada: «Esta app no está instalada» con «Ir al catálogo». Sin derecho del plan: «Esta app no está disponible para este hub.». Bloqueada: tarjeta «Suscripción necesaria», o la pantalla de la app que bloquea («Abre la caja primero»). A pantalla completa (F18) se esconden menú, barra y pestañas. Área: Vista de un módulo; la pantalla completa, Acceso.

### Vista de un módulo › Ajustes
Pestaña «Ajustes»: una tarjeta con un campo por ajuste (interruptor, lista, número o texto) con su nombre y explicación de la app, «Probar» donde se declare, y «Guardar» (solo administrador) o «Solo un administrador puede cambiar estos ajustes.». Cargando: «Cargando ajustes…». Error: «No se pudieron cargar los ajustes.». Rechazo: «No se pudieron guardar los ajustes.» y los campos marcados. Si la app trae su propia pantalla de ajustes, se monta esa. Área: Vista de un módulo.

### Vista de un módulo › Plan
Pestaña «Plan»: «Tu plan» («Comprobando tu suscripción…» → estado) con «Gestionar plan» o «Sube de plan para tener más» (no en Google Play) y «Ya lo he contratado — comprobar»; «Este mes» con el consumo si la app lo mide; una tarjeta por plan. Sin planes: «Este módulo no ofrece planes de pago.». Área: Vista de un módulo.

### Aprobación de un responsable
Diálogo «Hace falta una aprobación» sobre cualquier pantalla: «Se aprueba: {acción}», «¿Quién lo aprueba?» con las tarjetas (o un campo de nombre), el teclado de PIN con «Otra persona», la placa en cualquier paso, el motivo de un rechazo y «Cancelar». Área: Vista de un módulo.

### Campana de notificaciones
Campana de la barra superior (en el móvil, en «Más opciones») con el número rojo de lo pendiente. Lista «Notificaciones»: «Eventos caídos» (administrador), «Nadie está imprimiendo «{función}»», «Actualizaciones de apps» o «No se ha podido comprobar si hay actualizaciones» con «Comprobar de nuevo», y una fila por contador de app («Citas por confirmar»…). Vacía: «Todo al día. Sin notificaciones.». Área: Avisos e impresión (la fila de actualizaciones la cuenta también Aplicaciones, F119).

### Aviso del sistema
Notificación del dispositivo, solo en la app instalada: «Nueva comanda · {mesa}», «Nueva cita · {clienta}», «Cita cancelada · {clienta}», «{contador} ({número})»; al tocarla abre su pantalla. Hoja previa «Deja que te avisemos» («Activar los avisos» / «Ahora no»); en Android, la fija «ERPlora está a la escucha». Área: Avisos e impresión.

### Empleados
Menú › Empleados (todos los perfiles). Pestañas **Personal** (tabla con búsqueda, filtros, CSV y, para administradores, alta en panel lateral, «Editar» y «Dar de baja»), **Roles** (interruptor «Disponible»), **API keys** y **Aprobaciones** (estas dos, solo administradores). Hash `#roles`, `#apikeys`, `#approvals`. Cargando, vacío, error con «Reintentar»; sin permiso, pestañas ocultas. Área: Personas y permisos.

### Ficha de usuario
Empleados › Editar, o alta de usuario: nombre, email, rol, PIN local, placa, «Usuario local» (solo en el alta), «Usuario activo», «Retirar el PIN», «Retirar la placa», «Cancelar» y «Guardar»; pregunta antes de descartar cambios. Área: Personas y permisos.

### Documentación de la API
Menú › API, solo con el ajuste encendido (F161). Swagger dentro del hub con una introducción; cargando, error con «Reintentar». Área: Personas y permisos.

### Apps
Menú › Apps (todos los perfiles). Pestañas **Mis apps**, **Añadir apps** y **De pago** (`#all`, `#paid`); tarjetas o tabla; avisos arriba (retiradas, comprobación fallida, «Actualizar todas») y sobre la barra de pestañas; ventanas «Elige una versión» y «Permisos solicitados». Instalar, desactivar y desinstalar, solo administrador. Área: Aplicaciones.

### Mi plan
Menú › Mi plan. Pestañas **Facturas**, **Suscripciones** y **Pagos**; con sesión de PIN, piden entrar con la cuenta. Área: Plan y archivos.

### Archivos
Menú › Archivos (todos los perfiles). Árbol, ruta, cuadrícula o lista, buscador, espacio usado, visor en ventana y diálogos de nombre, borrar y carpeta nueva. Área: Plan y archivos.

### Sistema
Menú › Cuenta › Sistema. Cinco pestañas abajo (en móvil se desplazan): Recursos, Plan y límites, Actualizaciones, Eventos caídos, Registros. Cargando: círculo; error: «No se pudo consultar el sistema» con «Reintentar». Área: Sistema.

### Sistema › Recursos
Rango 3 h / 24 h / 3 días; tarjetas CPU, Memoria, Base de datos y Conexiones; «Tu impresora» (con app de impresión) con pasos de puesta en marcha y descarga de la app; «Los avisos están desactivados» y «La búsqueda de impresoras está bloqueada» (Android, app instalada). Área: Sistema.

### Sistema › Plan y límites
Plan actual con «Dentro del límite» / «Cerca del límite»; cinco tarjetas (Memoria, CPU, Base de datos, Dispositivos, Personas); «Te estás quedando sin margen» solo en Gratis; se refresca cada 5 s. La pestaña es de Sistema; su flujo, HUB_SHELL-F128, de Plan y archivos (`PlanLimitsPanel`).

### Sistema › Actualizaciones
«Qué te hemos actualizado», «Vas por la {versión}», «Tus apps» (solo administrador, F143) y el historial por días. Vacía: «No te hemos cambiado nada». Área: Sistema.

### Sistema › Eventos caídos
Solo administrador: «Reenviar todos» y una fila por evento («{n}× intentos», app, hora, último error) con reenviar y descartar. Vacía: «Todo en orden». Error: «No se pudo consultar el sistema» con «Reintentar». Quien no administra la ve vacía. Área: Sistema.

### Sistema › Registros
Tabla «Registro de eventos» (Hora, Nivel, Evento) con búsqueda y filtro por nivel. Vacía: «Sin eventos». Área: Sistema.

### Ajustes
Menú › Cuenta › Ajustes. Pestañas General, Negocio, Impresión, Permisos y Datos y copias (`#hub`, `#business`, `#tickets`, `#permissions`, `#data`; `#tax` abre Negocio). Quien no administra lo lee en solo lectura. Área: Ajustes del negocio y datos.

### Ajustes › General
País, Zona horaria, Moneda, Idioma del negocio, Paleta, «Mostrar documentación de la API», la fila de hardware que lleva a Sistema y, solo en la app de escritorio, «Arrancar al iniciar sesión» (área Ajustes, F156–F163); la tarjeta **Este dispositivo** («Compartido» / «Personal»; sin ser administrador, desactivadas con la nota de quién puede; error en rojo bajo las opciones; área Acceso, F11); y las tarjetas **Pinpad** (preguntar quién vende, parada por inactividad, dígitos del PIN) y **Dispositivos** (nombrar, quitar, quitar los sin usar) (área Personas, F99–F104). Todo se guarda al instante.

### Ajustes › Negocio
NIF/CIF/VAT, razón social, domicilio fiscal en cuatro partes, «Usar estos datos también para mi factura de ERPlora» y «Guardar cambios». No lleva certificado, vía de envío ni paso a producción: son del módulo VeriFactu. Área: Ajustes.

### Ajustes › Impresión
Fila «Impresoras y tique» (lleva a la app de impresión, o a Apps si falta; F165, F76) y, si el hub tiene algo que contar, la tarjeta «Estado de impresión» con una fila por función («Imprimiendo en {dispositivos}», «Nadie está imprimiendo esto — {n} tiques en espera», «El dispositivo que imprimía esto no responde»). Error: «No se ha podido comprobar quién está imprimiendo ahora mismo.». La pestaña es de Ajustes; la tarjeta, de Avisos e impresión (F75).

### Ajustes › Permisos
Una tarjeta por app con permisos, un interruptor por permiso y la consecuencia mientras está apagado. Vacía: «Ninguna app instalada pide permisos.». Área: Ajustes.

### Ajustes › Datos y copias
Selector Importar (por defecto) / Exportar / Restablecer. Área: Ajustes.

### Ajustes › Datos y copias › Exportar
Nombre, idioma, finalidad, secciones, tabla de apps, tarjetas de tablas y «Exportar». Área: Ajustes.

### Ajustes › Datos y copias › Importar
Catálogo de plantillas en tarjetas o tabla, «Subir desde archivo», resumen, secciones, apps, informe y «Reintentar lo que falta». Área: Ajustes.

### Ajustes › Datos y copias › Restablecer
«Exportar una copia antes», importaciones que se pueden deshacer, casillas por sección y el botón rojo «Restablecer el negocio» (hay que teclear la razón social). Área: Ajustes.

### Permisos de tus apps
Ventana al terminar de cargar una plantilla, solo si alguna app instalada pide algo sin conceder: las apps y sus permisos, «Dar permisos» / «Ahora no». Área: Ajustes.

### Tu número
Bloque del shell dentro de Bandeja de WhatsApp › Ajustes. Sin número: texto y «Conectar WhatsApp». Con número: el número, «Conectado» o «Hay que reconectar», «Desconectar». Sin WhatsApp configurado en la plataforma no pinta nada. Área: Ajustes.

### Asistente
Panel lateral desde «Asistente» de la barra superior (en el móvil, en «Más opciones») o «Pedírselo al asistente» de Inicio; solo con sesión. Móvil: cubre la pantalla; tableta y escritorio: 360–420 px y empuja el contenido. Pie: aviso de cuota, adjuntos, «Adjuntar archivo», «Dictar por voz», «Escribe un mensaje…», «Enviar»/«Detener». Vacío: «Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.» y atajos. Cargando: tres puntos. Error: la frase en la burbuja, sin «Reintentar». Área: Asistente.

### Tarjeta de confirmación del asistente
Aviso centrado cuando el asistente quiere cambiar algo: «El asistente quiere ejecutar una acción», la acción en palabras de la app (o «Una acción que esta app no sabe nombrar»), los datos en un párrafo y «Cancelar» / «Ejecutar»; con cuadro para escribir («BORRAR» o el número de registros) en lo destructivo y masivo. Área: Asistente.

## Flujos

El detalle de cada flujo (pasos, datos, fallos, implicados y QA) vive en `workflow/`, con la misma
gramática y el mismo prefijo. El porqué de cada `parcial` o `no hecho` está en su línea `Estado:`.

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
| HUB_SHELL-F23 | Gestionar o borrar mi cuenta de erplora.com | parcial | [workflow/acceso-y-navegacion.md](workflow/acceso-y-navegacion.md) |
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
| HUB_SHELL-F40 | Abrir una app y ver su primera pestaña | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F41 | Entender por qué una app no se abre | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F42 | Moverse entre las pestañas de una app | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F43 | Ver los ajustes de una app en su pestaña «Ajustes» | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F44 | Guardar los ajustes de una app | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F45 | Probar un ajuste antes de guardarlo | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F46 | Ver el plan de una app de pago en su pestaña «Plan» | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F47 | Ver lo consumido este mes de lo que incluye el plan | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F48 | Ir a gestionar el plan de una app en erplora.com | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F49 | Ver una app de pago bloqueada | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F50 | Ver una pantalla bloqueada hasta que otra app cumpla su condición | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F51 | Aprobar con el PIN de un responsable | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F52 | Leer en palabras de la persona por qué el hub rechazó algo | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F53 | Ver señalado el campo que el hub rechazó | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F54 | Ver dentro de una pantalla las piezas que aportan otras apps | hecho | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F55 | Vender a pantalla completa | retirado (→ HUB_SHELL-F18) | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F56 | Pintar una app con los componentes visuales del hub | parcial | [workflow/vista-de-modulo.md](workflow/vista-de-modulo.md) |
| HUB_SHELL-F60 | Ver en la campana lo que espera atención | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F61 | Atender desde la campana lo que pone una app | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F62 | Ver en la campana los avisos entre apps que no se entregaron | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F63 | Ver en la campana que nadie está imprimiendo una función | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F64 | Recibir un aviso del sistema cuando sube un contador de la campana | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F65 | Recibir el aviso del sistema «Nueva comanda» | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F66 | Recibir el aviso del sistema de una cita nueva o cancelada | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F67 | Tocar un aviso del sistema y abrir su pantalla | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F68 | Permitir los avisos del sistema en el dispositivo | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F69 | Seguir recibiendo avisos con la pantalla apagada | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F70 | Imprimir el tique al cobrar, solo en el dispositivo que cobró | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F71 | Abrir el cajón al cobrar | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F72 | Imprimir la comanda al disparar la ronda, solo en el TPV que la envió | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F73 | Dar de alta este dispositivo como el que imprime | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F74 | Sacar los trabajos de la cola y confirmar que salieron | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F75 | Ver quién imprime cada función | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F76 | Saber qué sale en el papel del tique y dónde se cambia | parcial | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F77 | Imprimir un documento desde una pantalla | hecho | [workflow/avisos-e-impresion.md](workflow/avisos-e-impresion.md) |
| HUB_SHELL-F80 | Ver la lista de personas del negocio | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F81 | Dar de alta a una persona que entra solo con PIN | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F82 | Invitar a una persona con su cuenta de erplora.com | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F83 | Llegar al tope de personas del plan | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F84 | Cambiar el nombre, el correo, el rol o el estado de una persona | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F85 | Poner o cambiar el PIN de otra persona | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F86 | Retirar el PIN a una persona | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F87 | Dar de alta o retirar la placa de una persona | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F88 | Dar de baja a una persona | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F89 | Reincorporar a una persona dada de baja | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F90 | Entender cómo entra cada persona | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F91 | Ver los roles y encender los que trae una app | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F92 | Asignar un rol a una persona | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F93 | Consultar quién aprobó qué | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F94 | Crear una llave de API y copiar su token | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F95 | Rotar una llave de API | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F96 | Revocar una llave de API | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F97 | Ver las llaves de API y qué puede cada una | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F98 | Consultar la documentación de la API | parcial | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F99 | Decidir si se pide PIN en la caja y cuándo se vuelve a pedir | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F100 | Elegir cuántos dígitos tiene el PIN del negocio | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F101 | Ver los dispositivos en los que se ha entrado | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F102 | Ponerle nombre a un dispositivo | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F103 | Quitar un dispositivo que se ha perdido | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F104 | Quitar de golpe los dispositivos que nadie usa | hecho | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB_SHELL-F105 | Ver las apps instaladas en el negocio | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F106 | Abrir una app desde Apps | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F107 | Buscar una app en el catálogo | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F108 | Saber cuánto cuesta una app antes de instalarla | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F109 | Instalar una app | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F110 | Saber qué más se ha instalado de paso | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F111 | Intentar instalar una app que necesita suscripción | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F112 | Ver por qué ha fallado una instalación y reintentarla | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F113 | Seguir una instalación mientras se navega | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F114 | Ver que una app necesita un hub más nuevo | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F115 | Saber que una app se instaló sin sus permisos | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F116 | Actualizar una app | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F117 | Actualizar todas las apps de una vez | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F118 | Ver que una actualización necesita un hub más nuevo | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F119 | Enterarse de que hay versiones nuevas | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F120 | Volver a comprobar las actualizaciones cuando falla la comprobación | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F121 | Ver qué apps ya no se ofrecen | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F122 | Desactivar una app | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F123 | Activar una app | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F124 | Desinstalar una app | hecho | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F125 | Ver que una app se niega a desactivarse o desinstalarse | parcial | [workflow/aplicaciones.md](workflow/aplicaciones.md) |
| HUB_SHELL-F126 | Ver las facturas del plan y descargarlas | parcial | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F127 | Ver las suscripciones y dónde se gestionan los pagos | no hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F128 | Ver cuánto de los límites del plan se está usando | parcial | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F129 | Ir a erplora.com a gestionar o mejorar el plan | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F130 | Ver los archivos del negocio | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F131 | Subir archivos y crear carpetas | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F132 | Previsualizar y descargar un archivo | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F133 | Mover y renombrar un archivo o una carpeta | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F134 | Borrar un archivo o una carpeta | hecho | [workflow/plan-y-archivos.md](workflow/plan-y-archivos.md) |
| HUB_SHELL-F135 | Abrir Sistema y moverse por sus pestañas | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F136 | Ver cuánto está usando el hub | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F137 | Ver si la impresora está lista | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F138 | Descargar la app de ERPlora desde Sistema | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F139 | Volver a activar los avisos de este dispositivo | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F140 | Volver a permitir la búsqueda de impresoras | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F141 | Ver el plan y sus límites | retirado (→ HUB_SHELL-F128) | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F142 | Saber qué versión corre y qué se le ha actualizado | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F143 | Saber si tus apps tienen una versión nueva | hecho | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F144 | Ver el registro de sucesos del sistema | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F145 | Ver los eventos caídos | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F146 | Reenviar un evento caído | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F147 | Reenviar todos los eventos caídos | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F148 | Descartar un evento caído | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F149 | Informar de un error de la pantalla sin que nadie lo pida | parcial | [workflow/sistema.md](workflow/sistema.md) |
| HUB_SHELL-F155 | Abrir Ajustes y moverse por sus pestañas | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F156 | Cambiar el país del negocio | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F157 | Elegir la zona horaria del negocio | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F158 | Cambiar la moneda del negocio | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F159 | Elegir el idioma del negocio | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F160 | Elegir la paleta de colores del negocio | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F161 | Mostrar u ocultar la documentación de la API | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F162 | Ir del hardware de Ajustes al diagnóstico de Sistema | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F163 | Arrancar ERPlora al iniciar sesión en el ordenador | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F164 | Guardar los datos del negocio y su identidad fiscal | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F165 | Ir a dar de alta la impresora y configurar el tique | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F166 | Ver quién está sacando cada tipo de tique | retirado (→ HUB_SHELL-F75) | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F167 | Conceder un permiso a una app | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F168 | Retirar un permiso a una app | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F169 | Dar los permisos de las apps que ha instalado una plantilla | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F170 | Conectar el número de WhatsApp del negocio | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F171 | Ver si el número está bien conectado y reconectarlo | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F172 | Desconectar el número de WhatsApp | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F173 | Exportar una copia de seguridad o una plantilla | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F174 | Elegir qué apps, datos y tablas viajan en la exportación | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F175 | Elegir una plantilla del catálogo para importar | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F176 | Subir un fichero para importar | hecho | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F177 | Revisar y cargar lo que trae el fichero | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F178 | Leer el informe de la importación | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F179 | Volver al informe de una importación que no entró entera y reintentar | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F180 | Deshacer una importación | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F181 | Restablecer el negocio por secciones | parcial | [workflow/ajustes-y-datos.md](workflow/ajustes-y-datos.md) |
| HUB_SHELL-F185 | Abrir y cerrar el panel del asistente | hecho | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F186 | Preguntar al asistente y leer cómo escribe | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F187 | Adjuntar un archivo o dictar por voz | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F188 | Leer la respuesta: texto, listas, tablas y enlaces | hecho | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F189 | Ir a una pantalla desde una respuesta | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F190 | Confirmar una acción antes de que se ejecute | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F191 | Acciones peligrosas: escribir para confirmar, o no desde el chat | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F192 | Comprobar lo que dice el asistente contra lo que de verdad hizo | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F193 | Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F194 | Pedirle varias cosas seguidas | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F195 | La conversación: qué se guarda, dónde y cuándo se borra | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F196 | El asistente en la puesta en marcha | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F197 | Ver el plan del asistente, el límite de uso y ampliarlo | parcial | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F198 | Informar de una respuesta mala | hecho | [workflow/asistente.md](workflow/asistente.md) |
| HUB_SHELL-F199 | El asistente sin conexión, con el servicio caído o sin plan | parcial | [workflow/asistente.md](workflow/asistente.md) |

## Cobertura contra la referencia

Cada fichero de área lleva su tabla «elemento de la referencia → estado → flujo» al final: `acceso-y-navegacion.md` (acceso y sesión; navegación y marco), `inicio.md`, `vista-de-modulo.md`, `avisos-e-impresion.md`, `personas-y-permisos.md`, `aplicaciones.md`, `plan-y-archivos.md`, `sistema.md`, `ajustes-y-datos.md` y `asistente.md` (este con una segunda tabla: lo que garantiza el panel para las acciones que hoy solo se hacen con el asistente, `Pantalla: asistente` de los módulos).

## Datos: de quién es cada dato

Las pantallas no tienen base de datos ni migraciones: todo dato del negocio es del hub, de cada app o de erplora.com, y se pide por su puerta (contexto público, sesión, consultas y órdenes). Lo único que el shell guarda es lo que deja en **el navegador del dispositivo**; el inventario, con sus datos personales y cuándo se borra, está en la sección «Datos» de cada área: sesión, tokens, personas de confianza e identificador del dispositivo en `acceso-y-navegacion.md`; uso de apps y tablero en `inicio.md`; avisos ya preguntados en `avisos-e-impresion.md`; la conversación del asistente en `asistente.md`. Las demás áreas (vista de un módulo, personas, aplicaciones, plan y archivos, sistema, ajustes) no guardan nada propio y dicen allí qué datos personales pasan por sus pantallas.

## Reglas que no se rompen

Comunes a todas las pantallas, y las hace cumplir el código:

- **La pantalla espeja; el servidor decide.** Ocultar o desactivar un botón no es la barrera: permisos, roles, llaves, dispositivos, apps, archivos, ajustes, datos, WhatsApp, eventos caídos, el bloqueo de caja y el de suscripción se revalidan en el hub en cada orden.
- Sin sesión no se pinta el marco y toda dirección que la pide lleva a Acceso (router, `authGate`).
- El shell no se monta hasta que el hub contesta su contexto (`bootUntilReachable`).
- Cada cadena nueva existe en inglés y en español (test de paridad de `src/i18n/`); ninguna pantalla pinta un código interno del hub (`screens-never-paint-a-runtime-code.test.ts`), salvo cinco que, a propósito, pintan la frase que dio el hub cuando no tienen una propia (lista en el test); la tarjeta «Este dispositivo» es una de ellas.
- La copia de Google Play no lleva salida al pago (`no-purchase-steering.test.ts`).

Las de cada área (impresión en el terminal que cobró, aprobación que se gasta una vez, persona que no se borra, PIN que no se lee, plantilla que no concede permisos, asistente que no puede más que quien pregunta…) están en la sección «Reglas» de su fichero, con los huecos de seguridad conocidos [SEG] en `acceso-y-navegacion.md`.

## Lo que NO hace, a propósito

- No vende: contratar, cambiar, cancelar y pagar son de erplora.com (hub#479, hub#756).
- No pinta códigos internos ni trazas.
- No guarda datos del negocio en el navegador (solo lo que listan las secciones «Datos» de cada área).

Lo de cada área está en su fichero: no pedir instalar la app, sin «Reintentar» en la franja, sin adivinar direcciones (acceso); sin «marcar como leído» ni push en el navegador (avisos); sin roles propios ni reenviar invitaciones (personas); sin bajar de versión (aplicaciones); sin copiar archivos (plan y archivos); sin «Actualizar el hub» (sistema); sin certificado en Ajustes (ajustes); sin historial fuera del navegador ni acciones destructivas del hub (asistente).

## Dudas abiertas

Se resuelven con `market-decision` o contra el código; no las decide el worker. Entre áreas:

- **Estado de la tarjeta «Estado de impresión».** Antes de fundirlos, HUB_SHELL-F166 (Ajustes) la daba por `hecho` y HUB_SHELL-F75 (Avisos e impresión) por `parcial`, porque la tarjeta recalcula el estado con `liveHosts` y `waiting` en vez del «sin atender» del hub. El código (`lib/print-coverage.ts:56-58`, `classifyRole`) da la razón a F75, que es el que queda; F166 está retirado.
- **Flujos que cuentan la misma pieza desde dos sitios** y no se han fundido porque cada uno cuenta su pantalla: F119/F143 (campana y Sistema), F37/F137 (Inicio y Sistema), F62/F145 (campana y Sistema), F76/F165 (qué sale en el tique y la fila que lleva a configurarlo). No se contradicen hoy; al cambiar uno se revisa el otro.

Las de cada área, en su fichero: menú por rol, cierre por inactividad, placa en el relevo, casilla «Confiar», «Activación requerida» (acceso); tablero por persona (inicio); quién guarda los ajustes de una app (vista de un módulo); cajón solo con efectivo, hora y nombre en el tique (avisos e impresión); roles propios, reenviar invitación, rotar llaves (personas); bajar de versión, permisos parciales (aplicaciones); copiar archivos, Archivos para el cajero, facturas por negocio (plan y archivos); motivo al descartar, eventos para quien no administra (sistema); informe de importación viejo (ajustes); «Nueva conversación» y recibo por orden (asistente).

## Fuentes contrastadas

- `CLAUDE.md` de la raíz («nunca `fill="outline"` en `ion-input`…») está desfasado: la regla del código es `fill="outline"` con `mode="md"` más el gancho de `src/lib/ionic-fill.ts`.
- Nombres de pantalla que usan otros documentos: «Ajustes › Hub» (servidor, manual 08, comentarios de `PinPolicyCard` y `DevicesCard`) es **Ajustes › General**; «Ajustes › Datos» (servidor, manual 09) es **Ajustes › Datos y copias**; «Aplicaciones» es **Apps**; «Plan del módulo» (servidor) y «Hub: Plan» (WHATSAPP_INBOX-F13) son **Vista de un módulo › Plan**; FLOWS-F01 («Ajustes → Permisos») es **Ajustes › Permisos**.
- Cada área lleva sus discrepancias con el manual, el servidor, los módulos y QA en la sección «Fuentes contrastadas» de su fichero.
