<template>
  <ion-app>
    <ion-split-pane content-id="main" when="lg" :class="{ rail: railCollapsed }">
      <!-- Menú lateral (drawer en móvil, fijo en desktop ≥lg). Solo con sesión. -->
      <ion-menu
        v-if="isAuthed"
        :menu-id="SHELL_MENU_ID"
        content-id="main"
        type="overlay"
        class="dash-menu"
      >
        <!-- Tarjeta de usuario ARRIBA (decisión 2026-07-16: el avatar de la topbar se retiró por
             duplicado; el usuario vive aquí). La tarjeta ENTERA es el trigger de un menú
             desplegable (ion-popover) con Perfil / Cerrar sesión — patrón "user menu" del
             dashboard de Cloud/Untitled UI, en vez de iconos sueltos. -->
        <ion-header class="ion-no-border">
          <ion-toolbar class="brand-toolbar">
            <button
              id="sidebar-user-menu"
              class="sidebar-user"
              type="button"
              aria-haspopup="menu"
              @keydown.enter.prevent="openUserMenuFromKeyboard"
              @keydown.space.prevent="openUserMenuFromKeyboard"
            >
              <div class="sidebar-user-avatar">
                <img v-if="user?.avatarUrl" :src="user.avatarUrl" alt="" />
                <span v-else>{{ initials }}</span>
              </div>
              <div class="sidebar-user-meta nav-label">
                <div class="sidebar-user-name">{{ user?.name }}</div>
                <div class="sidebar-user-email">{{ user?.email }}</div>
              </div>
              <HubIcon class="sidebar-user-chevron nav-label" name="chevron-expand-outline" />
            </button>
            <ion-popover
              trigger="sidebar-user-menu"
              trigger-action="click"
              :dismiss-on-select="true"
              side="bottom"
              alignment="start"
              class="sidebar-user-popover"
            >
              <ion-content>
                <ion-list lines="none">
                  <ion-item button :detail="false" @click="goProfile">
                    <HubIcon slot="start" name="person-outline" />
                    <ion-label>{{ t('sidebar.profile') }}</ion-label>
                  </ion-item>
                  <ion-item button :detail="false" @click="onLogout">
                    <HubIcon slot="start" name="log-out-outline" />
                    <ion-label>{{ t('sidebar.signOut') }}</ion-label>
                  </ion-item>
                </ion-list>
              </ion-content>
            </ion-popover>
            <!-- El rail-toggle se movió a la topbar compartida (AppTopbar), a la derecha del back,
                 para dar paridad con el shell de Cloud. El estado sigue en lib/shell (railCollapsed). -->
          </ion-toolbar>
        </ion-header>

        <ion-content class="sidebar-content">
          <ion-list v-for="section in nav" :key="section.titleKey" lines="none" class="nav-list">
            <ion-list-header class="nav-section-label">{{ t(section.titleKey) }}</ion-list-header>
            <ion-menu-toggle v-for="it in section.items" :key="it.path" :auto-hide="false">
              <ion-item
                button
                class="nav-item"
                :class="{ selected: isActive(it.path) }"
                :router-link="it.path"
                router-direction="root"
                :detail="false"
                :aria-current="isActive(it.path) ? 'page' : undefined"
              >
                <HubIcon slot="start" class="nav-icon" :name="it.icon" />
                <ion-label class="nav-label">{{ t(it.labelKey) }}</ion-label>
              </ion-item>
            </ion-menu-toggle>
          </ion-list>

          <!-- Los módulos instalados NO van en el sidebar: se acceden desde el botón «apps»
               de la topbar (rejilla, estilo Google) y desde el Home del Hub (pestaña Aplicaciones).
               El estado `moduleNav` sigue vivo (lo usa la rejilla de la topbar). -->
        </ion-content>

        <!-- Footer: brand (logo + wordmark, click → home) + versión de la app. El usuario se
             movió a la cabecera del menú; el botón «Instalar app» lo sustituye el modal PWA
             (PwaInstallModal). -->
        <ion-footer class="ion-no-border sidebar-foot">
          <!-- The app on this counter is older than the one we publish (hub#400). In the FOOTER on
               purpose: it is the one part of the sidebar that never scrolls away, and the issue
               asks for visible, not buried in settings. It paints itself only when there is
               something to do AND this session is the one it belongs to; the rest of the time it is
               not there at all. -->
          <ion-menu-toggle :auto-hide="false">
            <SidebarAppUpdate />
          </ion-menu-toggle>
          <div class="sidebar-foot-brand">
            <ion-menu-toggle :auto-hide="false">
              <a class="erp-lockup sm brand-link" role="button" tabindex="0" @click="goHome">
                <span class="erp-logo sm">
                  <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
                  <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
                  <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
                </span>
                <span class="erp-wordmark nav-label">erplora</span>
              </a>
            </ion-menu-toggle>
            <span class="sidebar-foot-text ml-auto nav-label">v{{ appVersion }}</span>
          </div>
        </ion-footer>
      </ion-menu>

      <ion-router-outlet id="main" />
    </ion-split-pane>

    <!-- Drawer del asistente (lo abre el sparkles de la topbar). Hermano del split-pane:
         va por encima del shell. Solo con sesión. Los errores del frontend se reportan
         AUTOMÁTICAMENTE al runtime (lib/error-report), sin modal ni acción del usuario. -->
    <template v-if="isAuthed">
      <AssistantDrawer />
      <!-- Modal «vista nativa» (PWA): se ofrece al entrar mientras la app no esté instalada;
           lib/pwa decide (standalone/Tauri/descartado-para-siempre → no se abre). -->
      <PwaInstallModal />
      <!-- El diálogo de aprobación por PIN (hub#363). Se monta UNA vez, aquí, y lo abre el
           TRANSPORTE ante un `requires_elevation` — nunca un módulo ni una pantalla: así el
           encargado aprueba igual venga la acción de la app que venga, y ninguna se lo deja sin
           poner. Solo con sesión: quien no ha entrado no tiene acción que elevar. -->
      <ElevationDialog />
    </template>
  </ion-app>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar,
  IonContent, IonList, IonListHeader, IonItem, IonLabel, IonFooter,
  IonPopover, IonRouterOutlet,
} from '@ionic/vue';
import HubIcon from './components/HubIcon.vue';
import AssistantDrawer from './components/AssistantDrawer.vue';
import PwaInstallModal from './components/PwaInstallModal.vue';
import ElevationDialog from './components/ElevationDialog.vue';
import SidebarAppUpdate from './components/SidebarAppUpdate.vue';
import { user, isAuthed, logout } from './lib/session';
import { refreshModuleNav } from './lib/nav';
import { resolveEntitlement, needsActivation } from './lib/entitlement';
import { railCollapsed } from './lib/shell';
import { SHELL_MENU_ID, runAfterShellMenuCloses } from './lib/shell-menu';
import { PROFILE_ROUTE } from './lib/routes';
import { maybeShowInstallModal } from './lib/pwa';
import { apiDocsEnabled } from './lib/api-docs';
import { getHubSettings } from './lib/hub-settings';
import { installIdleLogout } from './lib/idle-logout';
import { bootHubLanguage } from './i18n';
import { getUserProfile } from './lib/user-profile';
import { getClient } from './lib/runtime';
import { refreshSetupStatus } from './lib/setup-status';
import { bootAppUpdateWatch } from './lib/app-update';
import { bootDeadLetterWatch } from './lib/dead-letter';

interface NavItem { path: string; labelKey: string; icon: string }
interface NavSection { titleKey: string; items: NavItem[] }

// Etiquetas de la nav del shell por CLAVE i18n (EN/ES, ver src/i18n). Antes hardcoded en español.
// `computed`: la entrada «Documentación de la API» (ADR-0057 §4) aparece SOLO con el toggle de
// Ajustes activo (apiDocsEnabled). El resto es fijo.
const nav = computed<NavSection[]>(() => [
  {
    titleKey: 'nav.general',
    items: [
      { path: '/dashboard', labelKey: 'nav.home', icon: 'home-outline' },
      { path: '/employees', labelKey: 'nav.employees', icon: 'people-outline' },
      { path: '/files', labelKey: 'nav.files', icon: 'folder-outline' },
    ]
  },
  {
    titleKey: 'nav.account',
    items: [
      { path: '/billing', labelKey: 'nav.billing', icon: 'card-outline' },
      { path: '/apps', labelKey: 'nav.apps', icon: 'storefront-outline' },
      { path: '/system', labelKey: 'nav.system', icon: 'hardware-chip-outline' },
      ...(apiDocsEnabled.value
        ? [{ path: '/api-docs', labelKey: 'nav.apiDocs', icon: 'code-slash-outline' }]
        : []),
      // Export/Import del hub (ADR-0113) ya NO cuelga aquí: vive en la pestaña Datos de
      // Ajustes (/settings?tab=data, navegación secundaria — decisión del humano 2026-07-12).
      { path: '/settings', labelKey: 'nav.settings', icon: 'settings-outline' },
    ]
  },
]);

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// Versión de la app (horneada por Vite, ver vite.config.ts `define`).
const appVersion = __APP_VERSION__;

const isActive = (path: string): boolean =>
  route.path === path || route.path.startsWith(`${path}/`);

// Iniciales del nombre (o del email como fallback) para el avatar de la tarjeta de usuario.
const initials = computed<string>(() => {
  const name = user.value?.name?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
  }
  return (user.value?.email?.[0] ?? '?').toUpperCase();
});

// Resuelve el entitlement (§2.10) ANTES de pintar la nav de módulos: solo se montan los que el
// hub puede usar. AppsPage refresca la nav al recibir el evento WS `module.installed`.
async function gateAndRefresh(): Promise<void> {
  await resolveEntitlement();
  await refreshModuleNav();
  // Settings del hub (moneda/idioma/doc-API): GET exige sesión, así que se carga aquí (post-login),
  // no en el boot anónimo. Best-effort: si falla, sigue lo sembrado por /api/hub/context y la doc de
  // la API queda OFF. Refresca también la moneda/idioma efectivos por si cambiaron.
  try {
    const s = await getHubSettings();
    bootHubLanguage(s.language);
  } catch {
    /* el hub puede no exponer settings aún; degrada a lo ya sembrado */
  }
  // Después de intentar resolver los defaults del Hub, carga la fila del usuario y aplica sus
  // overrides. Si no tiene ninguno, user-profile hereda exactamente los valores disponibles.
  await getUserProfile().catch(() => null);
  // `hub.setup.status`: UNA lectura para todo el hub (hub#374). Antes la única la hacía el panel, así
  // que quien entraba directo al TPV llevaba una franja alimentada por nada. Best-effort: si falla,
  // no hay franja — una lectura rota no es una respuesta.
  void refreshSetupStatus(getClient());
  // Is the app on this counter the one we publish? (hub#400). After the session, because the entry
  // it feeds lives in the sidebar and the sidebar needs a session; idempotent, so the `watch` below
  // re-entering does not start a second clock. In a browser it never starts at all.
  bootAppUpdateWatch();
  // Campana de dead-letters (hub#660): sondea el count y alimenta el badge del topbar para que un
  // admin vea, sin ir a buscarlo, que hay eventos caídos. Solo arranca para admin (el propio
  // watcher se filtra por rol), igual que el de actualizaciones solo arranca en Tauri.
  bootDeadLetterWatch();
}
onMounted(() => {
  if (isAuthed.value) void gateAndRefresh();
});
watch(isAuthed, (authed) => {
  if (authed) void gateAndRefresh();
});
// Cierre por INACTIVIDAD (hub#628): con «Mostrar pinpad» ON y el range en N minutos
// (`pin_policy = always`), una caja `shared` que nadie toca N minutos cierra la sesión y vuelve
// al pinpad. El detector se arma/desarma solo (lib/idle-logout) según política + modo + sesión;
// el ticket abierto no se pierde: las líneas ya persisten en BD en cada toque (ADR-0144).
installIdleLogout(() => {
  logout();
  void router.replace('/login');
});
// Modal PWA «vista nativa»: se ofrece al ENTRAR (autenticado y ya FUERA de /login — el login
// cloud crea sesión antes de terminar, p. ej. en el paso «crea tu PIN», y el modal no debe
// taparlo). lib/pwa garantiza como mucho una oferta por sesión.
watch(
  () => isAuthed.value && !route.path.startsWith('/login'),
  (entered) => {
    if (entered) maybeShowInstallModal();
  },
  { immediate: true },
);
// La franja bloqueante NO se puede descartar (hub#374): la única forma de que desaparezca es que el
// hub deje de estar bloqueado, así que el documento se relee al navegar. Es también lo que detecta
// un gate que APARECE a mitad de sesión —instalar el módulo que pide certificado añade un ⛔ que en
// el login no existía—. El coste es una query LOCAL del runtime (no hay viaje al SaaS: el catálogo
// lo anota el host, §4bis) y solo se paga al cambiar de pantalla.
watch(
  () => route.path,
  () => {
    if (isAuthed.value) void refreshSetupStatus(getClient());
  },
);
// Si el entitlement resulta `needs_activation` (Tauri offline sin token cacheado, hub sin
// derecho…), saca al usuario del negocio → pantalla de activación.
watch(needsActivation, (needs) => {
  if (needs && route.name !== 'activation') void router.replace('/activation');
});

function goHome(): void {
  void router.push('/dashboard');
}

// Ionic posiciona el popover mediante el click de su trigger. Los botones nativos deberían generar
// ese click con Enter/Espacio, pero el webview no lo hace de forma consistente: lo normalizamos.
function openUserMenuFromKeyboard(event: KeyboardEvent): void {
  if (event.currentTarget instanceof HTMLButtonElement) event.currentTarget.click();
}

// Las acciones esperan a que el drawer móvil termine de cerrarse antes de navegar. Lanzar el
// cierre sin await deja la ruta nueva debajo del menú abierto y hace que Perfil parezca inerte.
async function goProfile(): Promise<void> {
  await runAfterShellMenuCloses(() => router.push(PROFILE_ROUTE));
}

async function onLogout(): Promise<void> {
  await runAfterShellMenuCloses(async () => {
    logout();
    await router.replace('/login');
  });
}
</script>

<!--
  CSS GLOBAL (no scoped) del "push" del panel del asistente. La clase `assistant-open` la togglea
  AssistantDrawer.vue en <html> según `assistantOpen`. Desde tablet (≥768px) reservamos a la
  derecha un ancho adaptable (360–420px): el panel fijo cae en ese hueco y EMPUJA el Hub, de modo
  que dashboard/asistente siguen siendo interactivos simultáneamente. Solo en móvil (<768px) el
  panel overlaya con scrim.
  El ion-split-pane es `position:absolute; inset:0` (right:0), así que padear el <ion-app> NO lo
  encoge (un hijo inset:0 llena el padding-box). Movemos directamente su borde derecho.
-->
<style>
/* 33vw escala el asistente en tablet; los límites conservan un chat usable sin comerse el Hub. */
:root {
  --assistant-panel-width: 420px;
}
@media (min-width: 768px) {
  :root {
    --assistant-panel-width: clamp(360px, 33vw, 420px);
  }

  html.assistant-open ion-split-pane {
    inset-inline-end: var(--assistant-panel-width);
    transition: inset-inline-end 0.2s ease;
  }
}
@media (min-width: 768px) and (prefers-reduced-motion: reduce) {
  html.assistant-open ion-split-pane {
    transition: none;
  }
}
</style>
