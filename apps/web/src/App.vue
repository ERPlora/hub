<template>
  <ion-app>
    <ion-split-pane content-id="main" when="lg" :class="{ rail: railCollapsed }">
      <!-- Menú lateral (drawer en móvil, fijo en desktop ≥lg). Solo con sesión. -->
      <ion-menu v-if="isAuthed" content-id="main" type="overlay" class="dash-menu">
        <!-- Tarjeta de usuario ARRIBA (decisión 2026-07-16: el avatar de la topbar se retiró por
             duplicado; el usuario vive aquí): avatar/iniciales + nombre/email + editar perfil +
             logout. El brand (logo + versión) baja al footer. -->
        <ion-header class="ion-no-border">
          <ion-toolbar class="brand-toolbar">
            <div class="sidebar-user">
              <!-- TODO(#39): migrar a ok-avatar cuando exista (ERPlora/outfitkit). Hasta entonces,
                   avatar de iniciales a mano; el CSS vive en polish.css (.sidebar-user-avatar). -->
              <div class="sidebar-user-avatar">{{ initials }}</div>
              <div class="sidebar-user-meta nav-label">
                <div class="sidebar-user-name">{{ user?.name }}</div>
                <div class="sidebar-user-email">{{ user?.email }}</div>
              </div>
              <ion-button
                class="nav-label"
                fill="clear"
                size="small"
                :aria-label="t('sidebar.profile')"
                @click="goProfile"
              >
                <HubIcon slot="icon-only" name="create-outline" />
              </ion-button>
              <ion-button
                class="nav-label"
                fill="clear"
                size="small"
                :aria-label="t('sidebar.signOut')"
                @click="onLogout"
              >
                <HubIcon slot="icon-only" name="log-out-outline" />
              </ion-button>
            </div>
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
    </template>
  </ion-app>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar,
  IonContent, IonList, IonListHeader, IonItem, IonLabel,  IonFooter,
  IonButton, IonRouterOutlet
} from '@ionic/vue';
import HubIcon from './components/HubIcon.vue';
import AssistantDrawer from './components/AssistantDrawer.vue';
import PwaInstallModal from './components/PwaInstallModal.vue';
import { user, isAuthed, logout } from './lib/session';
import { refreshModuleNav } from './lib/nav';
import { resolveEntitlement, needsActivation } from './lib/entitlement';
import { railCollapsed } from './lib/shell';
import { PROFILE_ROUTE } from './lib/routes';
import { maybeShowInstallModal } from './lib/pwa';
import { apiDocsEnabled } from './lib/api-docs';
import { getHubSettings } from './lib/hub-settings';
import { bootHubLanguage } from './i18n';

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
}
onMounted(() => {
  if (isAuthed.value) {
    void gateAndRefresh();
    maybeShowInstallModal();
  }
});
watch(isAuthed, (authed) => {
  if (authed) {
    void gateAndRefresh();
    maybeShowInstallModal();
  }
});
// Si el entitlement resulta `needs_activation` (Tauri offline sin token cacheado, hub sin
// derecho…), saca al usuario del negocio → pantalla de activación.
watch(needsActivation, (needs) => {
  if (needs && route.name !== 'activation') void router.replace('/activation');
});

function goHome(): void {
  void router.push('/dashboard');
}

function goProfile(): void {
  void router.push(PROFILE_ROUTE);
}

async function onLogout(): Promise<void> {
  logout();
  await router.replace('/login');
}
</script>

<!--
  CSS GLOBAL (no scoped) del "push" del panel del asistente. La clase `assistant-open` la togglea
  AssistantDrawer.vue en <html> según `assistantOpen` (lib/shell). En desktop (≥992px, el mismo
  breakpoint que el ion-split-pane when="lg") reservamos 420px a la derecha del shell: el panel
  (position:fixed; right:0; width:420px) cae en ese hueco y EMPUJA el contenido (sin scrim). En
  móvil (<992px) no reservamos nada → el panel overlaya con scrim (ver AssistantDrawer.vue).
  El ion-split-pane es `position:absolute; inset:0` (right:0), así que padear el <ion-app> NO lo
  encoge (un hijo inset:0 llena el padding-box). Movemos su borde derecho a 420px directamente.
-->
<style>
@media (min-width: 992px) {
  /* Encoge el shell entero (menú fijo + contenido flex) moviendo el borde derecho del split-pane a
     420px → el contenido (flex:1) absorbe la reducción y el panel fijo cae en el hueco. Verificado en
     QA con Playwright (main_right pasa de 1280→860 en viewport 1280). */
  html.assistant-open ion-split-pane {
    inset-inline-end: 420px;
    transition: inset-inline-end 0.2s ease;
  }
}
@media (min-width: 992px) and (prefers-reduced-motion: reduce) {
  html.assistant-open ion-split-pane {
    transition: none;
  }
}
</style>
