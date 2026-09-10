// 🔴 PRIMER import del shell, y el orden importa (hub#1060). Hace que `fill="outline"` pinte caja
// en TODA la app — shell, OutfitKit y los Web Components de los 25 módulos, dentro de su Shadow
// DOM incluidos— enganchando `customElements.define` ANTES de que nadie registre los ion-*.
// `@ionic/vue` los registra al importarse, y la spec congela los callbacks del custom element
// dentro de `define`: si este import baja de aquí, el arreglo deja de existir en silencio.
// Guard: `src/theme/ionic-fill-needs-md.test.ts`. Detalle: `src/lib/ionic-fill.ts`.
import './lib/ionic-fill.boot';

import { createApp } from 'vue';
import { IonicVue } from '@ionic/vue';
import { addIcons } from 'ionicons';
import { iconRegistry } from './lib/icons';

import App from './App.vue';
import { router } from './router';
import { i18n } from './i18n';
import {
  getClient,
  clientInjectionKey,
  bootHubContext,
  ensureMediaCookie,
  RUNTIME_URL,
  runtimeHeaders,
  setOnRuntimeSessionExpired,
} from './lib/runtime';
import { setOnSessionExpired, setOnHubGone } from './lib/cloud';
import { logout } from './lib/session';
import { invokeTauri } from './lib/device';
import { bootPrintOnSale } from './lib/print-on-sale';
import { bootPrintHost } from './lib/print-host';
import { bootPrintComanda } from './lib/print-comanda';
import {
  ensureNotificationPermission,
  primerLabelsFrom,
  shouldSendNotice,
} from './lib/notification-permission';
import { createPrintService } from './lib/print';
import { loadSlotComponents } from './lib/module-loader';
import { bootTheme } from './lib/theme';
import { bootPwa } from './lib/pwa';
import { bootModuleNavLocale } from './lib/nav';
import { bootActionFeedback, toast, toastError } from './lib/toast';
import { installErrorReporting } from './lib/error-report';
import { bootCourier, takeShellCourierCode } from './lib/courier';

// Pick up the bearer-like one-time code before registering workers, reporting errors or making any
// boot request.  It remains only in memory until the Hub context is ready for the exchange.
//
// The URL was already scrubbed by `./router` on the import above — it has to be, because that
// module builds the history that snapshots the location (hub#755).  This call is idempotent and
// just hands over what was taken there.
const shellCourierCode = takeShellCourierCode();

// Los ok-* de OutfitKit y los Web Components de los módulos pintan sus iconos POR NOMBRE
// (`<ion-icon name="trash-outline">`): son WC ajenos, no pueden llamar a `resolveIcon()`. ion-icon
// resuelve el nombre contra el mapa global `window.Ionicons.map` y, si no está, intenta bajar el
// SVG por red → en offline/CSP el icono sale VACÍO y sin error. Aquí volcamos el registro entero
// (SVG Iconify horneados en build) en ese mapa, con la API pública de ionicons.
// La fuente de verdad es lib/icons.ts, la misma de la que come <HubIcon> → un icono nuevo se añade
// en UN sitio y funciona en los dos caminos. Guard: src/lib/icons.test.ts.
addIcons(iconRegistry());

// CSS base de Ionic (core + utilidades). Dark mode por clase (.ion-palette-dark).
import '@ionic/vue/css/core.css';
import '@ionic/vue/css/normalize.css';
import '@ionic/vue/css/structure.css';
import '@ionic/vue/css/typography.css';
import '@ionic/vue/css/padding.css';
import '@ionic/vue/css/flex-utils.css';
import '@ionic/vue/css/palettes/dark.class.css';

// Impresión: reglas GLOBALES del Hub (deja en el papel solo el documento, quita la app). Van aquí
// —no dentro de cada modal— porque imprimir es del shell y debe valer para cualquier documento.
import './print.css';

// OutfitKit: registra los Web Components (Lit) que usa el shell. OutfitKit aporta lo que Ionic
// no tiene o compuestos complejos (p. ej. ok-data-table). Import por efecto secundario.
import '@erplora/outfitkit/ok-data-table';
// Launcher de apps (rejilla «Google apps» + hoja inferior) usado en la topbar del shell.
import '@erplora/outfitkit/ok-app-launcher';
// Dashboard / métricas de la pantalla /system (gauge, KPIs, stat, sparkline, pill de estado, vacío).
import '@erplora/outfitkit/ok-gauge';
// Paneles de uso con serie (CPU/RAM/conexiones) de /system: serie del SaaS proxied por el
// runtime (saas#1511). Requiere el bump de @erplora/outfitkit que publica ok-resource-usage.
import '@erplora/outfitkit/ok-resource-usage';
import '@erplora/outfitkit/ok-kpi';
import '@erplora/outfitkit/ok-stat';
import '@erplora/outfitkit/ok-sparkline';
import '@erplora/outfitkit/ok-status-pill';
import '@erplora/outfitkit/ok-empty-state';
// Sidebar → «Open on your phone» (hub#1715). Pure-JS QR generator: no dependency and no `eval`, so
// it renders under the hub's strict CSP where a canvas library would not.
import '@erplora/outfitkit/ok-qr';
// Tarjeta de plan de los tiers de un módulo (pestaña «Plan», hub#1605): la pieza compartida en
// vez de una tarjeta a mano por panel.
import '@erplora/outfitkit/ok-pricing-card';
// Usuarios → API keys: aviso "el secreto no se volverá a mostrar" en el modal del token.
import '@erplora/outfitkit/ok-inline-feedback';
// Ajustes → selector de tema compartido Cloud↔Hub (paleta + modo, ADR-0138).
import '@erplora/outfitkit/ok-theme-picker';
// Dashboard de inicio (DashboardPage): tablero de widgets de módulos (ADR-0054) + los kinds del
// render genérico que aún no estaban registrados (bar-list, timeline, chart). ok-kpi/ok-stat/
// ok-sparkline/ok-empty-state ya se importan arriba.
import '@erplora/outfitkit/ok-widget-board';
import '@erplora/outfitkit/ok-bar-list';
import '@erplora/outfitkit/ok-timeline';
import '@erplora/outfitkit/ok-chart';
// Gestor de archivos (Drive-like) de la carpeta media del Hub — pantalla /files.
import '@erplora/outfitkit/ok-file-manager';
// Visor de ficheros de /files (ADR-0171): texto/logs/código y JSON. La hoja de cálculo reutiliza
// el ok-data-table de arriba; PDF/imagen/Word no necesitan Web Component.
import '@erplora/outfitkit/ok-code';
import '@erplora/outfitkit/ok-json-viewer';
// Login (LoginPage): teclado PIN (con pantalla de círculos + tecla «cambiar usuario») y avatares.
import '@erplora/outfitkit/ok-pinpad';
import '@erplora/outfitkit/ok-avatar';
// Los ok-* asumen que el host registró los ion-* que usan por dentro (searchbar/select/overlays).
import { registerOutfitkitIonicDeps } from './lib/ionic-wc';

registerOutfitkitIonicDeps();

// Tema de marca (--ion-*) + logo de marca (rejilla CSS) + pulido visual + globales (Tailwind).
import './theme/variables.css';
// Paletas de tema opcionales (data-ok-palette, ADR-0138) — DESPUÉS de variables.css para
// ganar la cascada; el atributo lo pone lib/theme.ts (override local u hub_settings global).
import '@erplora/outfitkit/palettes.css';
import './theme/erplora-logo.css';
// Tabbar de footer (ion-segment como barra de navegación): ancho, scroll y degradado de borde.
// Comportamiento compartido con el SaaS — lo cablea AppPage con bindTabbar (outfitkit#29).
import '@erplora/outfitkit/tabbar.css';
import './theme/polish.css';
import './theme/global.css';

// Aplica el modo de tema guardado (claro/oscuro/system) antes del primer render.
bootTheme();

// Module names are localized BY THE RUNTIME and travel baked into the navigation (ADR-0055), so it
// has to be ASKED FOR AGAIN when the language changes: the personal preference arrives after the
// first render, and without this the list stayed in the language it booted with (hub#781).
// See lib/nav.ts.
bootModuleNavLocale();

// Registra el service worker y engancha el botón «Instalar app» (PWA, ver lib/pwa.ts).
bootPwa();

// Pide la cookie con la que el NAVEGADOR pide las fotos (hub#791). `setHubSession` ya la pide en
// cada login, pero el caso más frecuente no es un login: es la caja que YA tiene sesión y se
// recarga —el F5 al abrir, el webview reiniciado, la PWA que vuelve—. Ahí no empieza ninguna
// sesión, así que sin esta llamada el TPV amanecería con las 50 baldosas en blanco hasta el
// siguiente login. Sin sesión no llama a ninguna puerta, así que en la pantalla de login no cuesta
// nada.
void ensureMediaCookie();

// Feedback global de acciones: toast en export/import CSV de cualquier ok-data-table (y base para
// que el shell muestre éxito/fallo de otras acciones). Ver lib/toast.ts.
bootActionFeedback();

// mode: 'ios' FIJO. Sin esto Ionic autodetecta plataforma (md en desktop/Android, ios en
// Safari/iPad), así que el mismo Hub se veía distinto según el dispositivo. Debe coincidir con
// el SaaS (templates/base.html y public_base.html: window.Ionic.config.mode) — paridad SaaS↔Hub.
//
// swipeBackEnabled: false NO es opcional, es lo que hace usable el TPV. @ionic/vue lo activa SOLO
// al poner mode 'ios' (`config.get("swipeBackEnabled", outlet.mode === "ios")`), y verificado con
// gesto táctil real: con una comanda abierta, arrastrar desde el borde izquierdo navega
// /m/sales/pos → /dashboard y DESMONTA el POS a media comanda (las líneas sobreviven en
// sales_active_cart, pero al operario lo expulsa). Solo pasa por debajo de 992px — a partir de ahí
// el ion-menu fijo del split-pane (App.vue, when="lg") tapa el borde y el gesto no puede empezar —
// o sea que afecta justo al tablet en vertical (768/834), el formato de sala. ADR-0143.
const app = createApp(App).use(IonicVue, { mode: 'ios', swipeBackEnabled: false }).use(router).use(i18n);

// Captura AUTOMÁTICA de errores del frontend (sin modal ni acción del usuario): errores globales,
// promesas rechazadas y errorHandler de Vue → POST best-effort al runtime local (lib/error-report).
installErrorReporting(app);

// Cliente del runtime local (Axum) inyectado en todo el árbol (provide/inject). Las vistas y
// ModuleView lo consumen para hablar con el runtime (query/command/eventos WS). lib/runtime.ts.
app.provide(clientInjectionKey, getClient());

// Los Web Components de módulo (Lit) leen el cliente de `globalThis.erplora` (datos por
// .query/.command, hardware por .peripherals). El shell es el ÚNICO dueño de la conexión al
// Bridge — los módulos nunca lo abren ellos mismos (ARQUITECTURA.md §2.7).
// `loadSlot` (ADR-0043): el shell resuelve los componentes que otros módulos aportan a un slot
// cross-módulo (p.ej. el POS monta el picker de mesa/cliente que aportan `tables`/`customers`).
// El WC ya lo llama (`globalThis.erplora.loadSlot(slot)`); aquí se lo cableamos al cliente.
const erploraClient = getClient();
(erploraClient as unknown as { loadSlot?: (slot: string) => Promise<{ component: string }[]> }).loadSlot =
  loadSlotComponents;
// `print` (global): LA puerta de impresión para TODOS los módulos. Bridge si lo hay —por ROL de
// impresora: receipt/kitchen/bar/…—, COLA del hub si no hay Bridge (PWA, hub#344), y diálogo del
// navegador como último respaldo. Ningún módulo abre el Bridge ni llama a window.print() por su
// cuenta: se pisan entre sí y el hardware es del shell.
(erploraClient as unknown as { print?: ReturnType<typeof createPrintService> }).print =
  createPrintService(erploraClient as unknown as Parameters<typeof createPrintService>[0], {
    // Vía COLA (hub#344): sin Bridge, el tique térmico se encola en el hub y un print host del rol
    // lo drene. Reusa el mismo baseURL + auth del resto de llamadas al runtime.
    enqueue: async (job) => {
      const res = await fetch(`${RUNTIME_URL}/api/print/jobs`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...runtimeHeaders() },
        body: JSON.stringify({
          jobId: job.jobId,
          role: job.role,
          documentType: job.documentType,
          document: job.document,
          format: job.format ?? 'receipt',
        }),
      });
      // 200 con ok:true → encolado (nuevo o duplicado, ambos éxito). Cualquier otra cosa → false
      // (la puerta cae al navegador: una venta no se cae por impresión).
      if (!res.ok) return false;
      const body = await res.json().catch(() => ({}));
      return body?.ok === true;
    },
  });
(globalThis as typeof globalThis & { erplora: ReturnType<typeof getClient> }).erplora = erploraClient;

/**
 * Asks to be allowed to warn, at most once per install (hub#1732).
 *
 * `force` is what the System screen passes when the user asks for the notices back after saying
 * no; the boot never forces. The strings come through `i18n` — the sheet is the only text the
 * user reads before Android's own dialog, and a hardcoded one would ship English to a Spanish
 * shop (ADR-0055/0199).
 */
function askToWarn(force = false) {
  return ensureNotificationPermission({
    labels: primerLabelsFrom((key) => i18n.global.t(key)),
    force,
  });
}

// Auto-impresión del ticket al cerrar venta (escucha `sale.completed` en el shell, no en sales).
// Sale por la MISMA puerta que todo lo demás (hub#862): resolvía él mismo rol→impresora y llamaba al
// hardware directo, así que con la impresora sin rol —o sin hardware en este equipo— el tique
// desaparecía sin cola, sin navegador y sin aviso.
bootPrintOnSale(getClient(), {
  print: (req) => (erploraClient as unknown as { print: ReturnType<typeof createPrintService> }).print(req),
  onFailure: (f) => {
    void toastError(`El tique de la venta ${f.saleId} NO se imprimió: ${f.error}`);
  },
});

// HOST DE IMPRESIÓN (ADR-0196 §6, hub#343 + hub#501 + hub#749): este equipo se DA DE ALTA como host
// de los roles que puede imprimir de verdad y drena la cola del hub. Se arranca SIEMPRE y en todos
// los dispositivos a propósito: el alta solo ocurre donde hay hardware alcanzable con impresoras
// enroladas, así que el móvil con la PWA no se da de alta de nada y no cuesta más que la pregunta.
// Hasta hub#749 NADIE llamaba a `POST /api/print/hosts` —ni el shell, ni la app, ni un módulo—, así
// que la cola entera era inalcanzable desde el producto: lo encolado se quedaba encolado para
// siempre. Lo que sigue faltando es la pantalla de COBERTURA («nadie está imprimiendo lo de
// cocina»), que se daba por hecha en hub#344 y no se hizo.
//
// The alta is also WHERE THE SHELL ASKS TO BE ALLOWED TO WARN ANYBODY (hub#1732). Until now
// nothing did: `POST_NOTIFICATIONS` was declared in both manifests and the plugin could ask for
// it, but the only caller was the kitchen-order notice below — so a clean install used for a full
// morning was never asked, and Android reports a permission nobody was shown as denied for the
// life of the install. This moment is the right one twice over: the device has just become the one
// that gets TOLD an order came in, and somebody is standing at it setting it up. Asked at the
// first order instead, the dialog appears on a tablet propped on a shelf with nobody in front of
// it. `ensureNotificationPermission` asks at most once and never throws.
void bootPrintHost(erploraClient as unknown as Parameters<typeof bootPrintHost>[0], {
  onRegistered: () => void askToWarn(),
});

// Comanda a cocina al DISPARAR el pedido (ADR-0144), no al cobrar. Aquí y no en `kitchen` porque
// tiene que imprimir siempre, no solo con el KDS montado: la cocina caliente suele ser solo papel.
// Si la impresora falla NO se bloquea al camarero —la comanda ya está en la BD y el KDS es la
// fuente de verdad—: se avisa, y desde el KDS se reimprime.
bootPrintComanda(getClient(), {
  print: (req) => (erploraClient as unknown as { print: ReturnType<typeof createPrintService> }).print(req),
  onFailure: (f) => {
    void toastError(`No se imprimió la comanda de ${f.label || 'sala'} (${f.role}): ${f.error}`);
  },
  // Aviso del SISTEMA, no un toast: el toast solo se ve si alguien está mirando ESTA pantalla, y
  // en cocina la tablet suele estar apoyada, en otra vista o bloqueada. Va por el bridge (el shell
  // en Tauri, el binario/WS en navegador), así que sale igual en escritorio y en Android.
  //
  // The permission first (hub#1732), and this is the FALLBACK trigger: a KDS screen with no
  // printer never registers as a print host, so the alta above never reaches it. Idempotent —
  // after the first answer this is one storage read.
  //
  // And a refusal STOPS here instead of falling through to `peripherals.notify()`: that call asks
  // for the permission itself, with no sentence of ours in front of it (hub#758's scope), so
  // letting it through would pop Android's bare dialog in the middle of a service. Android drops
  // the notice either way; what the user gets instead is the row on System › your printer, which
  // says the notices are off and offers to ask again.
  notify: async (title, body) => {
    if (!shouldSendNotice(await askToWarn())) return;
    await getClient().peripherals.notify(title, body);
  },
});

// Si un refresh falla (sesión expirada de verdad), cloud.ts ya limpió los tokens; aquí
// limpiamos el estado reactivo del usuario y mandamos a /login vía el router del shell.
setOnSessionExpired(() => {
  logout();
  void router.replace('/login');
});

// The LOCAL plane (hub#846), twin of the Cloud hook above: a RUNTIME 401 whose session was
// CONFIRMED dead (expired, or displaced by another device on the single-device plan) already
// closed the local session inside lib/runtime.ts — the invalidation is ONE and lives there. Here
// the shell EXPLAINS it (i18n toast, not a failure with a «Retry» that could never help) and
// leads to the login. `reason` travels in the query so LoginPage can adopt it later (the key
// `login.sessionTakenOver` already sits waiting for that wire). The login screen keeps deciding
// on its own what to offer — pinpad in the demo or on a trusted device (ADR-0329: the runtime's
// `demo_would_adopt` rule stays untouched and keeps answering that question).
setOnRuntimeSessionExpired(() => {
  void toast(i18n.global.t('auth.sessionEnded'), 'warning', 6000);
  void router.replace({ name: 'login', query: { reason: 'session-expired' } });
});

// El Cloud reportó que el hub fue borrado/revocado (410 hub_not_found, vía el gate de
// entitlement): olvidamos la identidad de máquina local (`forget_hub` borra token + hub_id +
// entitlement cacheado) y cerramos sesión. El `device.id` se conserva, así que el próximo login
// re-registra el hub por dispositivo (§2.9b). Distinto de un token caducado (que solo refresca).
setOnHubGone(() => {
  void invokeTauri('forget_hub').catch(() => null);
  logout();
  void router.replace('/login');
});

// Resuelve el hub_id desde el runtime (`GET /api/hub/context`) ANTES de montar, para que
// X-Hub-Id esté disponible en la primera llamada. No bloquea si el runtime no responde
// (deja el fallback VITE_HUB_ID). Decisión del humano (2): hub_id inyectado, sin picker.
void bootHubContext().finally(async () => {
  // ADR-0159: if the SaaS sent a one-time shell courier, consume it before router mount so the
  // first protected route sees an authenticated local session.  The fragment is scrubbed before
  // this network call; failure falls through to the ordinary login page without logging the code.
  try {
    await bootCourier(shellCourierCode);
  } catch {
    // Login remains available and the one-time credential has already been removed from the URL.
  }
  router.isReady().then(() => app.mount('#app'));
});
