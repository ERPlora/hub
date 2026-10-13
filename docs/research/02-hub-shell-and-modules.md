# Hallazgos: Hub actual (/home/user/erplora/hub) — shell, PIN, módulos

Documento de referencia del sistema anterior, recibido el 2026-10-12. Las rutas y afirmaciones describen la investigación original; no certifican el estado de estos repositorios.

> **Informe recibido el 2026-10-12; donde contradiga PLAN §16 (ronda 11, 2026-10-13) manda el plan.**
> Choques concretos: (1) «Anatomía de app en la ronda 9»: no hay `manifest.py`, `handbook.md`, `README.md`
> ni `CHANGELOG.md` por app; la especificación es `WORKBOOK.md` y los metadatos van en el `AppConfig`
> (`LiveAppConfig`), como en `README.md` «Anatomía de una app». (2) «claves útiles para manifest.py»: esas
> claves pasan al `AppConfig`, no a un `manifest.py`. (3) `/m/:moduleId` → «`/apps/:slug/:tab?` →
> AppView»: no hay vista genérica; cada app declara sus rutas en `frontend/plugin.ts` (p. ej.
> `/demo/items`). (4) «`/_enter?t=` canje del ticket»: el Hub canjea el código de un solo uso con
> `/internal/auth/redeem` (PLAN-SAAS §2.1); en la fase 1 la sesión es `django.contrib.auth` +
> `core.Membership`. (5) Los iconos pasan a `HubIcon` con juegos de Iconify (PLAN §16.4).

## Rutas de la shell (apps/web/src/router/index.ts) y destino en hub-next
| hoy | vista | hub-next |
|---|---|---|
| `/login` | LoginPage (pin · email · twoFactor · setup) | solo `PinPage` en dispositivos de confianza; email → SaaS |
| `/auth/google/callback` | LoginPage canjea `?code=` | `/_enter?t=` canje del ticket |
| `/dashboard` | DashboardPage: BlueprintHeroCard, MyAppsCard, SetupChecklistCard (hub.setup.status), ok-widget-board | `HomePage` |
| `/employees`, `/new`, `/:id` | EmployeesPage (staff · roles · apikeys · approvals), EmployeeFormPage | `PeoplePage` lectura + PIN por persona; approvals se queda; usuarios/roles/invitaciones → SaaS |
| `/files` | FilesPage (ok-file-manager) | se queda |
| `/profile` | ProfilePage (avatar, idioma, tema, PIN propio, link SaaS) | hoja "Me" |
| `/billing` | BillingPage (invoices · subscriptions · payments) | enlace al SaaS |
| `/apps` (+`/marketplace`) | AppsPage (mine · all · paid; install/uninstall/toggle/update) | `AppsPage` activar/apagar; comprar → SaaS |
| `/system` | SystemPage (resources · plan · updates · logs · events) | logs + eventos caídos + dispositivo |
| `/settings` | SettingsPage (hub · business · tickets · permissions · data) | igual, sin paleta global ni api-docs toggle |
| `/api-docs` | Swagger | post-lanzamiento |
| `/m/:moduleId/:navId?` | ModuleView (WC Lit; tabbar de navigation[]; tab Plan sintética; tab settings declarativa; estados loading/offline/empty/not-installed/unknown/blocked) | **`/apps/:slug/:tab?` → AppView** (páginas Vue de cada app) |
| `/activation` | ActivationPage | `BlockedPage` (HubState.status ≠ active) |
| `/export` `/import` `/first-run` | redirects | fuera |
| `/:pathMatch(.*)*` | NotFoundPage (mantiene la URL) | se queda |
Tab activa en el hash (`/settings#permissions`).

## Chrome
- `AuthenticatedChrome.vue` (gate: authed + meta.auth). Sidebar (App.vue, ion-menu en split pane): tarjeta de usuario arriba (Profile, Switch user, Sign out); nav General: Home, Employees, Files; Account: Billing, Apps, System, API docs (toggle), Settings; sin módulos en el menú; footer: logo+versión, SidebarAppUpdate, SidebarInstallQr (QR para abrir en móvil), botón Upgrade plan → SaaS.
- Topbar (AppTopbar.vue): menú (móvil), back en detalle, rail toggle, título, acciones por vista, lanzador de apps (rejilla), Manage → SaaS, Change hub (cierra sesión y olvida URL), asistente (si capacidad), campana (dead-letter + módulos); overflow en estrecho.
- AppPage.vue: topbar → SetupBlockingStrip (blocking_pending) → OfflineStrip (navegador offline / hub no responde) → contenido.
- Overlays: AssistantDrawer (chat LLM; enlaces solo a rutas existentes; voz; confirm cards; CTA plan), UserSwitchOverlay (caras + pinpad; PIN fallido no toca la sesión anterior; 5 intentos por nombre), ElevationDialog (responsable aprueba con PIN).

## PIN y acceso (LoginPage.vue, lib/session.ts, workflow/acceso.md)
- Hoy: primer acceso con cuenta email (JWT SaaS → `/api/auth/cloud`, HUB-F130, 2FA opcional); Google/handoff mismo camino (F131); "Trust this device" guarda `hub_trusted_device`; PIN solo en dispositivos de confianza (F133); setup pide PIN si no hay (F132), argon2id.
- Reglas: longitud 4 o 6 por negocio, el pad envía al último dígito; triviales rechazados (1111, 1234); único entre activos; `pin_policy` always | per_shift | never; relock por inactividad 1–30 min (5 por defecto) (F140, PinPolicyCard).
- Bloqueo (F135): 5 fallos por nombre/placa → 5 min; 20 fallos o 20 sesiones falsas por IP en 15 min.
- Modo de dispositivo (F139, DeviceModeCard): shared (pinpad + caras, sesión ≤12 h), personal (sin pinpad, ≤30 d); con always ≤1 h; desconocido = shared.
- Cambio de persona (F138, UserSwitchOverlay): nueva sesión sustituye; se limpian credenciales SaaS y chat; placas no aceptadas aquí (placa RFID/NFC solo en login, F134).
- Sesión opaca `X-Hub-Session` con credencial de origen (cloud | pin | badge); solo `cloud` abre "Manage" del SaaS (F142). Dispositivos (F141, DevicesCard): nombrar/quitar; quitar mata sesiones y confianza; plan single device expulsa otras sesiones (F137).

## Manual del hub (docs-next/user-manual/hub/01–12)
01 acceso y navegación (next: email → redirect al SaaS; PIN y menús se quedan) · 02 inicio y puesta en marcha · 03 personas y permisos (hoy todo en el hub; en next todo al SaaS salvo PIN y approvals) · 04 archivos · 05 plan y facturas (solo muestra; contratar en erplora.com; next: enlaces) · 06 aplicaciones (next: sin instalar/actualizar, solo activar) · 07 sistema (next: fuera recursos y updates; quedan eventos y logs) · 08 ajustes del negocio (hub, business, tickets, permissions, data) · 09 datos import/export · 10 asistente y avisos · 11 app instalada y hardware · 12 estados y problemas.

## Inventario de módulos (24; mismas ids en showcase y manual)
| id | nombre | propósito | sección | requires | tabs | tier | notas |
|---|---|---|---|---|---|---|---|
| sales | Ventas y TPV | cuentas, cobrar, aparcar, historial | Venta, cobro y fiscalidad | inventory, taxes | pos, sales, quick_notes, departments | free | settings; ledger de todos los canales (`sales.complete_sale`, evento `sale.completed`, `sales_settings.pos_layout`) |
| cash_register | Caja | turnos, movimientos, arqueos | Venta | — (opcional sales) | cash_register | free | settings admin |
| cart_checkout | Carrito y checkout | carritos y pedidos al pagar | Venta | — | carts, orders | free | §15.2: carrito interno del POS / tickets aparcados |
| payments | Pagos | salidas de dinero con aprobación | Venta | — | list | free | |
| invoice | Facturación | ventas → documentos fiscales F1/F2/R1 | Venta | sales, taxes | invoice, settings | free | |
| taxes | Impuestos | categorías y reglas por país/región/fecha; alias | Venta | — | categories, rules, aliases | free | |
| verifactu | VeriFactu | registros encadenados a la AEAT | Venta | invoice | records, contingency, events, recovery, config, settings | free forzado | fiscal_regime ES |
| inventory | Inventario | productos, precios, costes, stock | Catálogo | taxes | dashboard, products, movements, categories | free | settings; una ubicación |
| services | Servicios | catálogo de servicios, bonos | Catálogo | taxes | services, categories, packages | free | settings |
| pricing | Precios | tarifas y reglas de descuento | Catálogo | — | lists | free | |
| combos | Menús y combos | artículos compuestos | Catálogo | — (opc. inventory, services) | menus | free | |
| modifiers | Modificadores | opciones de producto | Catálogo | — | groups | free | |
| customers | Clientes | fichas, grupos, etiquetas, campos, consentimiento | Clientes | — (opc. sales) | customers, groups, tags, fields | free | |
| appointments | Citas | agenda cliente/servicio/profesional | Clientes | customers, services, staff | appointments | free | settings |
| online_booking | Reservas online | solicitudes públicas | Clientes | customers | bookings, settings | free | |
| schedules | Horarios | apertura, festivos, excepciones | Clientes | — | hours | free | |
| staff | Personal | fichas, roles, servicios, horarios, ausencias | Clientes | — (opc. services) | staff, roles, time_off, schedules | free | settings |
| tables | Mesas | plano, zonas, mesas, sesiones | Restaurante | — (opc. sales, reservations) | floor_plan, zones, tables, sessions | free | settings |
| reservations | Reservas | reservas de mesa, franjas, lista de espera | Restaurante | tables, customers | list, waitlist, availability | free | |
| kitchen | Cocina | comandas, estaciones, seguimiento | Restaurante | sales, inventory | display, active, stations, history | free | settings |
| flows | Automatizaciones | disparadores, pasos, aprobaciones | Organización | — | automations | free | owner/admin; permiso manage_flows |
| tasks | Tareas | tareas, proyectos | Organización | — | all, projects | free | |
| whatsapp_inbox | WhatsApp | bandeja, plantillas, canal | Organización | customers (opc. flows) | inbox, settings (+plan) | premium | billing con capa gratis y uso medido |
| printing | Impresión | papel, impresoras, cola | Organización | — | printing | free | |
Fuera del inventario: attendance (solo repo, settings panel), warehouse (futuro, depende de inventory).

DAG: taxes (raíz) ← inventory ← sales ← invoice ← verifactu; sales ← kitchen (+inventory); taxes ← services ← appointments (+customers, staff); customers (raíz) ← online_booking, whatsapp_inbox, reservations (+tables); tables, staff raíces; independientes: cart_checkout, cash_register, payments, pricing, combos, modifiers, schedules, tasks, printing, flows.

## module.json actual (hub/schemas/module.schema.json) — claves útiles para manifest.py
id, name, description (en), icon (ion:), version, agent{description, keywords}, ai_context, depends_on [str | {id,min_version}], permissions, roles, role_permissions, navigation[{id,label,icon,component,permission}], queries, commands, events, widgets, bell, setup, settings, network{secrets}, notify, capabilities (network, certificate, printer, notify, manage_flows), fiscal_regime{country, regime}, scheduled_tasks, marketplace{functional_unit, sectors[], business_types[]}, billing{tier, type, interval, price, trial_days, tiers[], usage}, compatibility.min_erplora_version, setup.countries, seed, errors, protects.

## Anatomía de app en la ronda 9 (docs-next)
`apps/<id>/{apps.py, manifest.py (nuevo), models.py, schemas.py, services.py, queries.py, api.py, live.py, events.py, admin.py, handbook.md (nuevo), README.md, CHANGELOG.md, frontend/{plugin.ts, pages/, components/}, tests/}`. Sin views.py ni urls.py. `@operation(name, kind="query"|"command", permission, input, output, ai=None, expose_api=False)`; queries READ ONLY en queries.py; commands en services.py; solo services/queries tocan el ORM; toda ruta ninja ligada a una @operation. Sobre de error `{error:{code,message,fields?}}`; 422 con fields; 401 unauthorized. limit ≤100; resultado ≤256 KB; 50 suscripciones por stream; batching 150 ms. Eventos `<app>.<entidad>.<hecho>`. Tests `test_<módulo>.py`.

## Tablas al activar (docs-next/superpowers/specs/2026-10-11-tablas-al-activar-design.md)
Estados por hub: no creada (sin filas en django_migrations) · creada · activa (derecho del SaaS ∧ encendida ∧ creada). Máquina: off → creating (202) → on; failed con reintentos 1 m, 5 m, 15 m, 1 h; on → off conserva datos. Se crea al encender por primera vez, no al tener derecho. Worker como `hub_migrator` sobre alias `hub_<hex>__ddl`: `MigrationExecutor(...).migrate([(app_label, leaf)])`; `migrate --database=hub_…` a pelo se rechaza; control guarda `Hub.schema_apps`; `pg_try_advisory_lock` por hub. Plantillas: `hub_template` = core; `hub_template_<vertical>` = core + apps de la vertical cerradas bajo requires; vertical desconocida → 422. `requires` en AppConfig: encender A enciende sus requires; sin derecho → 402 app_entitlement_blocked; apagar B con A dependiente encendida → 409 core.app_required; FKs solo hacia dependencias declaradas; lint de ciclos. Modelo de app inactiva → 404 app_inactive.
