import { createApp } from 'vue';
import { IonicVue } from '@ionic/vue';
import { addIcons } from 'ionicons';
import {
  pencil, trash, add, close, chevronBack, chevronForward,
  listOutline, gridOutline, funnelOutline, downloadOutline, cloudUploadOutline,
  appsOutline, closeOutline, ellipsisVertical, power,
  // Iconos que pintan POR NOMBRE los widgets del dashboard (ok-kpi/ok-timeline/ok-inline-feedback
  // usan ion-icon por dentro). Tendencia de ok-kpi: trending-up/down/remove.
  trendingUp, trendingDown, remove,
  trendingUpOutline, receiptOutline, peopleOutline, alertCircleOutline,
  walletOutline, barChartOutline,
  bagHandleOutline, checkmarkOutline, warningOutline, personOutline, fingerPrintOutline,
} from 'ionicons/icons';

import App from './App.vue';
import { router } from './router';
import { i18n } from './i18n';
import { getClient, clientInjectionKey, bootHubContext } from './lib/runtime';
import { setOnSessionExpired } from './lib/cloud';
import { logout } from './lib/session';
import { bootPrintOnSale } from './lib/print-on-sale';
import { bootTheme } from './lib/theme';
import { bootPwa } from './lib/pwa';

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
  // ⋮ del ok-widget-board (botón "Personalizar panel") + menú overflow de ok-data-table.
  'ellipsis-vertical': ellipsisVertical,
  // Acción «Activar / Desactivar» del marketplace (menú de fila de ok-data-table).
  power,
  // Flechas de tendencia de ok-kpi.
  'trending-up': trendingUp, 'trending-down': trendingDown, remove,
  // Iconos de label de los KPIs y de las celdas del dashboard (ok-kpi/ok-timeline/feedback).
  'trending-up-outline': trendingUpOutline, 'receipt-outline': receiptOutline,
  'people-outline': peopleOutline, 'alert-circle-outline': alertCircleOutline,
  'wallet-outline': walletOutline, 'bar-chart-outline': barChartOutline,
  'bag-handle-outline': bagHandleOutline, 'checkmark-outline': checkmarkOutline,
  'warning-outline': warningOutline, 'person-outline': personOutline,
  'finger-print-outline': fingerPrintOutline,
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
// Dashboard del Hub: panel de widgets configurable (ok-widget-board) + widgets que monta dentro
// (ok-chart, ok-bar-list, ok-timeline) y cabecera de página (ok-page-header). ok-kpi/ok-sparkline
// /ok-status-pill ya están arriba; ok-inline-feedback se usa para avisos en el panel.
import '@erplora/outfitkit/ok-widget-board';
import '@erplora/outfitkit/ok-chart';
import '@erplora/outfitkit/ok-bar-list';
import '@erplora/outfitkit/ok-timeline';
import '@erplora/outfitkit/ok-page-header';
import '@erplora/outfitkit/ok-inline-feedback';
// Tarjeta de catálogo del marketplace (misma que el marketplace público del Cloud).
import '@erplora/outfitkit/ok-product-card';
// Gestor de archivos (Drive-like) de la carpeta media del Hub — pantalla /files.
import '@erplora/outfitkit/ok-file-manager';
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

// Resuelve el hub_id desde el runtime (`GET /api/hub/context`) ANTES de montar, para que
// X-Hub-Id esté disponible en la primera llamada. No bloquea si el runtime no responde
// (deja el fallback VITE_HUB_ID). Decisión del humano (2): hub_id inyectado, sin picker.
void bootHubContext().finally(() => {
  router.isReady().then(() => app.mount('#app'));
});
