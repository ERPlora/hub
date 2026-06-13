<template>
  <ion-app>
    <ion-split-pane content-id="main" when="lg" :class="{ rail: railCollapsed }">
      <!-- Menú lateral (drawer en móvil, fijo en desktop ≥lg). Solo con sesión. -->
      <ion-menu v-if="isAuthed" content-id="main" type="overlay" class="dash-menu">
        <!-- Brand: rejilla CSS (erplora-logo) + wordmark, igual que el dashboard de Cloud. -->
        <ion-header class="ion-no-border">
          <ion-toolbar class="brand-toolbar">
            <ion-menu-toggle :auto-hide="false" slot="start">
              <a class="erp-lockup sm brand-link" role="button" tabindex="0" @click="goHome">
                <span class="erp-logo sm">
                  <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
                  <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
                  <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
                </span>
                <span class="erp-wordmark nav-label">erplora</span>
              </a>
            </ion-menu-toggle>
            <ion-buttons slot="end">
              <!-- DECISIÓN HUMANO PENDIENTE (issue #38 pto 7): el rail-toggle vive aquí (cabecera
                   del sidebar), NO en la topbar como en Cloud. Se mantiene la ubicación del Hub
                   hasta que el humano decida; el estado es compartido (lib/shell). -->
              <ion-button
                class="rail-toggle"
                fill="clear"
                :aria-label="railCollapsed ? t('topbar.expandMenu') : t('topbar.collapseMenu')"
                @click="railCollapsed = !railCollapsed"
              >
                <HubIcon slot="icon-only" :name="railCollapsed ? 'chevron-forward-outline' : 'chevron-back-outline'" />
              </ion-button>
            </ion-buttons>
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

          <!-- Módulos instalados (dinámico): se rellena del runtime y se refresca al instalar. -->
          <ion-list v-if="moduleNav.length" lines="none" class="nav-list">
            <ion-list-header class="nav-section-label">{{ t('nav.modules') }}</ion-list-header>
            <ion-menu-toggle v-for="m in moduleNav" :key="m.path" :auto-hide="false">
              <ion-item
                button
                class="nav-item"
                :class="{ selected: isActive(m.path) }"
                :router-link="m.path"
                router-direction="root"
                :detail="false"
                :aria-current="isActive(m.path) ? 'page' : undefined"
              >
                <HubIcon slot="start" class="nav-icon" :name="m.icon" />
                <ion-label class="nav-label">{{ m.label }}</ion-label>
              </ion-item>
            </ion-menu-toggle>
          </ion-list>
        </ion-content>

        <!-- Tarjeta de usuario: avatar + nombre/email + enlace a perfil; fila de acciones
             (reportar problema + logout) + versión de app. Paridad con el footer del sidebar
             de Cloud (cloud/.../partials/sidebar.html). -->
        <ion-footer class="ion-no-border sidebar-foot">
          <div class="sidebar-user">
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
              <HubIcon slot="icon-only" name="person-outline" />
            </ion-button>
          </div>
          <div class="sidebar-foot-actions nav-label">
            <ion-button
              fill="clear"
              size="small"
              :aria-label="t('sidebar.reportProblem')"
              @click="bugReportOpen = true"
            >
              <HubIcon slot="icon-only" name="bug-outline" />
            </ion-button>
            <ion-button
              fill="clear"
              size="small"
              :aria-label="t('sidebar.signOut')"
              @click="onLogout"
            >
              <HubIcon slot="icon-only" name="log-out-outline" />
            </ion-button>
            <span class="sidebar-foot-text ml-auto">v{{ appVersion }}</span>
          </div>
        </ion-footer>
      </ion-menu>

      <ion-router-outlet id="main" />
    </ion-split-pane>

    <!-- Drawer del asistente (lo abre el sparkles de la topbar) + modal de reporte de problemas.
         Hermanos del split-pane: drawer/modal van por encima del shell. Solo con sesión. -->
    <template v-if="isAuthed">
      <AssistantDrawer />
      <BugReportModal v-model:open="bugReportOpen" />
    </template>
  </ion-app>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar, IonButtons,
  IonContent, IonList, IonListHeader, IonItem, IonLabel,  IonFooter,
  IonButton, IonRouterOutlet
} from '@ionic/vue';
import HubIcon from './components/HubIcon.vue';
import AssistantDrawer from './components/AssistantDrawer.vue';
import BugReportModal from './components/BugReportModal.vue';
import { user, isAuthed, logout } from './lib/session';
import { moduleNav, refreshModuleNav } from './lib/nav';
import { resolveEntitlement, needsActivation } from './lib/entitlement';
import { railCollapsed } from './lib/shell';
import { PROFILE_ROUTE } from './lib/routes';

interface NavItem { path: string; labelKey: string; icon: string }
interface NavSection { titleKey: string; items: NavItem[] }

// Etiquetas de la nav del shell por CLAVE i18n (EN/ES, ver src/i18n). Antes hardcoded en español.
const nav: NavSection[] = [
  {
    titleKey: 'nav.general',
    items: [
      { path: '/dashboard', labelKey: 'nav.home', icon: 'home-outline' },
      { path: '/employees', labelKey: 'nav.employees', icon: 'people-outline' },
    ]
  },
  {
    titleKey: 'nav.account',
    items: [
      { path: '/billing', labelKey: 'nav.billing', icon: 'card-outline' },
      { path: '/marketplace', labelKey: 'nav.marketplace', icon: 'storefront-outline' },
      { path: '/system', labelKey: 'nav.system', icon: 'hardware-chip-outline' },
      { path: '/settings', labelKey: 'nav.settings', icon: 'settings-outline' },
    ]
  },
];

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// Versión de la app (horneada por Vite, ver vite.config.ts `define`).
const appVersion = __APP_VERSION__;

// Estado del modal de reporte de problemas (footer del sidebar).
const bugReportOpen = ref<boolean>(false);

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
// hub puede usar. MarketplacePage refresca la nav al recibir el evento WS `module.installed`.
async function gateAndRefresh(): Promise<void> {
  await resolveEntitlement();
  await refreshModuleNav();
}
onMounted(() => {
  if (isAuthed.value) void gateAndRefresh();
});
watch(isAuthed, (authed) => {
  if (authed) void gateAndRefresh();
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
