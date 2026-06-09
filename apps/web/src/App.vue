<template>
  <ion-app>
    <ion-split-pane
      content-id="main"
      when="lg"
      style="--side-width: 232px; --side-min-width: 220px; --side-max-width: 248px"
    >
      <!-- Menú lateral (drawer en móvil, fijo en desktop ≥lg). Solo con sesión. Más estrecho. -->
      <ion-menu v-if="isAuthed" content-id="main" type="overlay" style="--width: 240px">
        <ion-header class="ion-no-border">
          <ion-toolbar>
            <ion-title>ERPlora · Hub</ion-title>
          </ion-toolbar>
        </ion-header>
        <!-- ion-padding para que los ítems no queden pegados al borde -->
        <ion-content class="ion-padding">
          <ion-list v-for="section in nav" :key="section.title">
            <ion-list-header>{{ section.title }}</ion-list-header>
            <ion-menu-toggle v-for="it in section.items" :key="it.path" :auto-hide="false">
              <ion-item
                button
                :router-link="it.path"
                router-direction="root"
                :detail="false"
                lines="none"
                :color="isActive(it.path) ? 'light' : undefined"
              >
                <ion-icon slot="start" :icon="it.icon" />
                <ion-label>{{ it.label }}</ion-label>
              </ion-item>
            </ion-menu-toggle>
          </ion-list>
        </ion-content>
        <ion-footer class="ion-no-border">
          <ion-toolbar>
            <ion-item lines="none">
              <ion-label>
                <h3 class="font-semibold">{{ user?.name }}</h3>
                <p class="text-xs opacity-60">{{ user?.email }}</p>
              </ion-label>
              <ion-button slot="end" fill="clear" aria-label="Cerrar sesión" @click="onLogout">
                <ion-icon slot="icon-only" :icon="logOutOutline" />
              </ion-button>
            </ion-item>
          </ion-toolbar>
        </ion-footer>
      </ion-menu>

      <ion-router-outlet id="main" />
    </ion-split-pane>
  </ion-app>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar, IonTitle,
  IonContent, IonList, IonListHeader, IonItem, IonLabel, IonIcon, IonFooter,
  IonButton, IonRouterOutlet,
} from '@ionic/vue';
import {
  homeOutline, peopleOutline, cardOutline, storefrontOutline,
  hardwareChipOutline, settingsOutline, logOutOutline,
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

const isActive = (path: string): boolean => route.path === path;

async function onLogout(): Promise<void> {
  logout();
  await router.replace('/login');
}
</script>
