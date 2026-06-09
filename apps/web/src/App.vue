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
              <ion-button
                class="rail-toggle"
                fill="clear"
                :aria-label="railCollapsed ? 'Expandir menú' : 'Colapsar menú'"
                @click="railCollapsed = !railCollapsed"
              >
                <ion-icon slot="icon-only" :icon="railCollapsed ? chevronForwardOutline : chevronBackOutline" />
              </ion-button>
            </ion-buttons>
          </ion-toolbar>
        </ion-header>

        <ion-content class="sidebar-content">
          <ion-list v-for="section in nav" :key="section.title" lines="none" class="nav-list">
            <ion-list-header class="nav-section-label">{{ section.title }}</ion-list-header>
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
                <ion-icon slot="start" class="nav-icon" :icon="it.icon" />
                <ion-label class="nav-label">{{ it.label }}</ion-label>
              </ion-item>
            </ion-menu-toggle>
          </ion-list>
        </ion-content>

        <!-- Tarjeta de usuario: avatar de iniciales + nombre/email + logout. -->
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
              aria-label="Cerrar sesión"
              @click="onLogout"
            >
              <ion-icon slot="icon-only" :icon="logOutOutline" />
            </ion-button>
          </div>
        </ion-footer>
      </ion-menu>

      <ion-router-outlet id="main" />
    </ion-split-pane>
  </ion-app>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar, IonButtons,
  IonContent, IonList, IonListHeader, IonItem, IonLabel, IonIcon, IonFooter,
  IonButton, IonRouterOutlet,
} from '@ionic/vue';
import {
  homeOutline, peopleOutline, cardOutline, storefrontOutline,
  hardwareChipOutline, settingsOutline, logOutOutline,
  chevronBackOutline, chevronForwardOutline,
} from 'ionicons/icons';
import { user, isAuthed, logout } from './lib/session';

interface NavItem { path: string; label: string; icon: string }
interface NavSection { title: string; items: NavItem[] }

const nav: NavSection[] = [
  {
    title: 'General',
    items: [
      { path: '/dashboard', label: 'Inicio', icon: homeOutline },
      { path: '/employees', label: 'Empleados', icon: peopleOutline },
    ],
  },
  {
    title: 'Cuenta',
    items: [
      { path: '/billing', label: 'Facturación', icon: cardOutline },
      { path: '/marketplace', label: 'Marketplace', icon: storefrontOutline },
      { path: '/system', label: 'Sistema', icon: hardwareChipOutline },
      { path: '/settings', label: 'Ajustes', icon: settingsOutline },
    ],
  },
];

const route = useRoute();
const router = useRouter();

// Rail colapsable (solo escritorio): añade .rail al split-pane → CSS estrecha y oculta labels.
const railCollapsed = ref<boolean>(false);

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

function goHome(): void {
  void router.push('/dashboard');
}

async function onLogout(): Promise<void> {
  logout();
  await router.replace('/login');
}
</script>
