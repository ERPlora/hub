import { createApp } from 'vue';
import { IonicVue } from '@ionic/vue';
import { addIcons } from 'ionicons';
import {
  pencil, trash, add, close, chevronBack, chevronForward,
  listOutline, gridOutline, funnelOutline, downloadOutline, cloudUploadOutline,
  appsOutline, closeOutline, arrowBackOutline, backspaceOutline,
  // ok-kpi (DashboardPage / /system): iconos de tendencia + neutro.
  trendingUp, trendingDown, remove,
  // ok-kpi icon prop (DashboardPage): estas pasan directamente a <ion-icon name="…"> dentro del WC.
  trendingUpOutline, receiptOutline, peopleOutline, warningOutline,
  // ok-data-table / ok-empty-state: icono por defecto del estado vacío.
  fileTrayOutline,
  // ok-data-table: indicador de orden en cabeceras de columna.
  swapVerticalOutline,
  // ok-file-manager (/files): navegación por carpetas, tipo de archivo terminal.
  chevronForwardOutline, folderOpenOutline, terminalOutline,
} from 'ionicons/icons';

import App from './App.vue';
import { router } from './router';
import { i18n } from './i18n';
import { getClient, clientInjectionKey, bootHubContext } from './lib/runtime';
import { setOnSessionExpired } from './lib/cloud';
import { logout } from './lib/session';
import { setOnHubGone } from './lib/entitlement';
import { invokeTauri } from './lib/device';
import { bootPrintOnSale } from './lib/print-on-sale';
import { bootTheme } from './lib/theme';
import { bootPwa } from './lib/pwa';
import { installErrorReporting } from './lib/error-report';

// Los componentes de OutfitKit (ok-data-table, etc.) usan ion-icon POR NOMBRE ('pencil', 'trash',
// 'chevron-back'…). En @ionic/vue los iconos por nombre hay que registrarlos con addIcons (no se
// auto-cargan como en el loader CDN). Registramos el set que usan los ok-*.
addIcons({
  pencil, trash, add, close,
  'chevron-back': chevronBack, 'chevron-forward': chevronForward,
  'list-outline': listOutline, 'grid-outline': gridOutline, 'funnel-outline': funnelOutline,
  'download-outline': downloadOutline, 'cloud-upload-outline': cloudUploadOutline,
  // Trigger (rejilla) y cerrar de ok-app-launcher (OutfitKit), por NOMBRE.
  'apps-outline': appsOutline, 'close-outline': closeOutline,
  // Teclado PIN del login (ok-pinpad): borrado + tecla «cambiar usuario».
  'arrow-back-outline': arrowBackOutline, 'backspace-outline': backspaceOutline,
  // ok-kpi (DashboardPage + /system): flecha tendencia arriba/abajo y neutro.
  'trending-up': trendingUp, 'trending-down': trendingDown, 'remove': remove,
  // ok-kpi `icon` prop (DashboardPage): KPI icon names passed directly to ion-icon inside the WC.
  'trending-up-outline': trendingUpOutline, 'receipt-outline': receiptOutline,
  'people-outline': peopleOutline, 'warning-outline': warningOutline,
  // ok-data-table / ok-empty-state: default empty-state icon used by all module tables.
  'file-tray-outline': fileTrayOutline,
  // ok-data-table: sort indicator shown on every sortable column header.
  'swap-vertical-outline': swapVerticalOutline,
  // ok-file-manager (/files): folder navigation and terminal file-type icon.
  'chevron-forward-outline': chevronForwardOutline,
  'folder-open-outline': folderOpenOutline,
  'terminal-outline': terminalOutline,
});

// CSS base de Ionic (core + utilidades). Dark mode por clase (.ion-palette-dark).
import '@ionic/vue/css/core.css';
import '@ionic/vue/css/normalize.css';
import '@ionic/vue/css/structure.css';
import '@ionic/vue/css/typography.css';
import '@ionic/vue/css/padding.css';
import '@ionic/vue/css/flex-utils.css';
import '@ionic/vue/css/palettes/dark.class.css';

// OutfitKit: registra los Web Components (Lit) que usa el shell. OutfitKit aporta lo que Ionic
// no tiene o compuestos complejos (p. ej. ok-data-table). Import por efecto secundario.
import '@erplora/outfitkit/ok-data-table';
// Launcher de apps (rejilla «Google apps» + hoja inferior) usado en la topbar del shell.
import '@erplora/outfitkit/ok-app-launcher';
// Dashboard / métricas de la pantalla /system (gauge, KPIs, stat, sparkline, pill de estado, vacío).
import '@erplora/outfitkit/ok-gauge';
import '@erplora/outfitkit/ok-kpi';
import '@erplora/outfitkit/ok-stat';
import '@erplora/outfitkit/ok-sparkline';
import '@erplora/outfitkit/ok-status-pill';
import '@erplora/outfitkit/ok-empty-state';
// Gestor de archivos (Drive-like) de la carpeta media del Hub — pantalla /files.
import '@erplora/outfitkit/ok-file-manager';
// Login (LoginPage): teclado PIN (con pantalla de círculos + tecla «cambiar usuario») y avatares.
import '@erplora/outfitkit/ok-pinpad';
import '@erplora/outfitkit/ok-avatar';
// Los ok-* asumen que el host registró los ion-* que usan por dentro (searchbar/select/overlays).
import { registerOutfitkitIonicDeps } from './lib/ionic-wc';

registerOutfitkitIonicDeps();

// Tema de marca (--ion-*) + logo de marca (rejilla CSS) + pulido visual + globales (Tailwind).
import './theme/variables.css';
import './theme/erplora-logo.css';
import './theme/polish.css';
import './theme/global.css';

// Aplica el modo de tema guardado (claro/oscuro/system) antes del primer render.
bootTheme();

// Registra el service worker y engancha el botón «Instalar app» (PWA, ver lib/pwa.ts).
bootPwa();

const app = createApp(App).use(IonicVue).use(router).use(i18n);

// Captura AUTOMÁTICA de errores del frontend (sin modal ni acción del usuario): errores globales,
// promesas rechazadas y errorHandler de Vue → POST best-effort al runtime local (lib/error-report).
installErrorReporting(app);

// Cliente del runtime local (Axum) inyectado en todo el árbol (provide/inject). Las vistas y
// ModuleView lo consumen para hablar con el runtime (query/command/eventos WS). lib/runtime.ts.
app.provide(clientInjectionKey, getClient());

// Los Web Components de módulo (Lit) leen el cliente de `globalThis.erplora` (datos por
// .query/.command, hardware por .peripherals). El shell es el ÚNICO dueño de la conexión al
// Bridge — los módulos nunca lo abren ellos mismos (ARQUITECTURA.md §2.7).
(globalThis as typeof globalThis & { erplora: ReturnType<typeof getClient> }).erplora = getClient();

// Auto-impresión del ticket al cerrar venta (escucha `sale.completed` en el shell, no en sales).
bootPrintOnSale(getClient());

// Si un refresh falla (sesión expirada de verdad), cloud.ts ya limpió los tokens; aquí
// limpiamos el estado reactivo del usuario y mandamos a /login vía el router del shell.
setOnSessionExpired(() => {
  logout();
  void router.replace('/login');
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
void bootHubContext().finally(() => {
  router.isReady().then(() => app.mount('#app'));
});
