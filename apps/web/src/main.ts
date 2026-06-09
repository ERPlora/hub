import { createApp } from 'vue';
import { IonicVue } from '@ionic/vue';
import { addIcons } from 'ionicons';
import {
  pencil, trash, add, close, chevronBack, chevronForward,
  listOutline, gridOutline, funnelOutline, downloadOutline, cloudUploadOutline,
} from 'ionicons/icons';

import App from './App.vue';
import { router } from './router';
import { getClient, clientInjectionKey, bootHubContext } from './lib/runtime';
import { setOnSessionExpired } from './lib/cloud';
import { logout } from './lib/session';

// Los componentes de OutfitKit (ok-data-table, etc.) usan ion-icon POR NOMBRE ('pencil', 'trash',
// 'chevron-back'…). En @ionic/vue los iconos por nombre hay que registrarlos con addIcons (no se
// auto-cargan como en el loader CDN). Registramos el set que usan los ok-*.
addIcons({
  pencil, trash, add, close,
  'chevron-back': chevronBack, 'chevron-forward': chevronForward,
  'list-outline': listOutline, 'grid-outline': gridOutline, 'funnel-outline': funnelOutline,
  'download-outline': downloadOutline, 'cloud-upload-outline': cloudUploadOutline,
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
// Los ok-* asumen que el host registró los ion-* que usan por dentro (searchbar/select/overlays).
import { registerOutfitkitIonicDeps } from './lib/ionic-wc';

registerOutfitkitIonicDeps();

// Tema de marca (--ion-*) + logo de marca (rejilla CSS) + pulido visual + globales (Tailwind).
import './theme/variables.css';
import './theme/erplora-logo.css';
import './theme/polish.css';
import './theme/global.css';

const app = createApp(App).use(IonicVue).use(router);

// Cliente del runtime local (Axum) inyectado en todo el árbol (provide/inject). Las vistas y
// ModuleView lo consumen para hablar con el runtime (query/command/eventos WS). lib/runtime.ts.
app.provide(clientInjectionKey, getClient());

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
