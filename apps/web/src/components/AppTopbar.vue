<!--
  AppTopbar — topbar compartida del shell del Hub (paridad con cloud/templates/page_base.html).
  Sustituye el `<ion-header><ion-toolbar>` que cada vista duplicaba. Primitivos Ionic.

  Orden/iconos iguales al shell de Cloud:
    start:  menu-button (drawer móvil; Ionic lo oculta en ≥lg) · back contextual
    title:  título de la vista (prop `title`)
    end:    [slot actions de la vista] · asistente (sparkles) · notificaciones (campana+badge)
            · toggle de tema · avatar (iniciales) → perfil
    bajo el toolbar: barra de progreso mientras hay peticiones en vuelo.

  La vista pasa `title` y, si es una vista de detalle, `back-href` (muestra el botón Back).
  Acciones propias de la vista (p. ej. "Nuevo empleado") van en el slot `#actions`.
-->
<template>
  <ion-header class="ion-no-border app-topbar">
    <ion-toolbar>
      <ion-buttons slot="start">
        <!-- Drawer móvil. Ionic lo oculta en ≥lg (menú fijo). -->
        <ion-menu-button :aria-label="t('topbar.menu')" />
        <!-- Back contextual: solo en vistas de detalle (cuando hay `backHref`). -->
        <ion-button
          v-if="backHref"
          fill="clear"
          :aria-label="t('topbar.back')"
          @click="goBack"
        >
          <HubIcon slot="icon-only" name="arrow-back-outline" />
        </ion-button>
      </ion-buttons>

      <ion-title>{{ title }}</ion-title>

      <ion-buttons slot="end">
        <!-- Acciones propias de la vista (a la izquierda de los controles globales). -->
        <slot name="actions" />

        <!-- Apps (rejilla estilo Google): acceso rápido a los módulos instalados desde cualquier
             pantalla. Abre un popover con la rejilla de módulos + enlace a la tienda. Los módulos
             NO viven en el sidebar; se entra por aquí o por el Home (pestaña Aplicaciones). -->
        <ion-button
          fill="clear"
          :aria-label="t('topbar.apps')"
          :title="t('topbar.apps')"
          @click="openApps"
        >
          <HubIcon slot="icon-only" name="apps-outline" />
        </ion-button>

        <!-- Asistente (sparkles): visible cuando la capacidad está disponible. Abre el drawer. -->
        <ion-button
          v-if="assistantAvailable"
          fill="clear"
          :aria-label="t('topbar.assistant')"
          :title="t('topbar.assistant')"
          @click="toggleAssistant"
        >
          <HubIcon slot="icon-only" name="sparkles-outline" />
        </ion-button>

        <!-- Notificaciones: campana + badge. Contador = STUB (lib/shell, sin backend aún). -->
        <ion-button
          fill="clear"
          class="topbar-notif"
          :aria-label="t('topbar.notifications')"
          :title="t('topbar.notifications')"
        >
          <HubIcon slot="icon-only" name="notifications-outline" />
          <ion-badge v-if="notificationCount > 0" color="primary" class="notif-badge">
            {{ notificationCount }}
          </ion-badge>
        </ion-button>

        <!-- Tema: alterna claro/oscuro (movido aquí desde SettingsPage). -->
        <ion-button
          fill="clear"
          :aria-label="t('topbar.toggleTheme')"
          :title="t('topbar.toggleTheme')"
          @click="toggleTheme"
        >
          <HubIcon slot="icon-only" :name="isDark ? 'sunny-outline' : 'moon-outline'" />
        </ion-button>

        <!-- Avatar (iniciales) → perfil. -->
        <!-- TODO(#39): migrar a ok-avatar cuando exista (ERPlora/outfitkit). -->
        <a
          class="topbar-avatar"
          :aria-label="t('topbar.profile')"
          :title="t('topbar.profile')"
          role="button"
          tabindex="0"
          @click="goProfile"
          @keydown.enter="goProfile"
        >{{ initials }}</a>
      </ion-buttons>
    </ion-toolbar>

    <!-- Barra de progreso mientras hay peticiones en vuelo (paridad .dash-progress de Cloud). -->
    <div v-show="isLoading" class="topbar-progress"><div /></div>

    <!-- Rejilla de apps (módulos instalados). Anclada al botón «apps» de la topbar. -->
    <ion-popover
      :is-open="appsOpen"
      :event="appsEvent"
      :show-backdrop="true"
      @did-dismiss="appsOpen = false"
    >
      <ion-content class="apps-popover">
        <div class="apps-grid">
          <a
            v-for="m in moduleNav"
            :key="m.path"
            class="apps-tile"
            role="button"
            tabindex="0"
            @click="goModule(m.path)"
            @keydown.enter="goModule(m.path)"
          >
            <HubIcon class="apps-tile-icon" :name="m.icon" />
            <span class="apps-tile-label">{{ m.label }}</span>
          </a>
          <!-- Tienda: siempre presente, para instalar más módulos. -->
          <a
            class="apps-tile apps-tile-store"
            role="button"
            tabindex="0"
            @click="goModule('/marketplace')"
            @keydown.enter="goModule('/marketplace')"
          >
            <HubIcon class="apps-tile-icon" name="storefront-outline" />
            <span class="apps-tile-label">{{ t('nav.marketplace') }}</span>
          </a>
        </div>
        <p v-if="!moduleNav.length" class="apps-empty">{{ t('topbar.appsEmpty') }}</p>
      </ion-content>
    </ion-popover>
  </ion-header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonHeader, IonToolbar, IonButtons, IonButton, IonMenuButton, IonTitle, IonBadge,
  IonPopover, IonContent,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { user } from '../lib/session';
import { isDark, toggleTheme } from '../lib/theme';
import { assistantAvailable, toggleAssistant, notificationCount, isLoading } from '../lib/shell';
import { moduleNav } from '../lib/nav';
import { PROFILE_ROUTE } from '../lib/routes';

const props = defineProps<{
  /** Título de la vista. */
  title: string;
  /** Href de fallback del botón Back. Si se pasa, la vista es de detalle y muestra el Back. */
  backHref?: string;
}>();

const { t } = useI18n();
const router = useRouter();

const backHref = computed<string | undefined>(() => props.backHref);

// Popover de apps (rejilla de módulos instalados), anclado al botón de la topbar.
const appsOpen = ref<boolean>(false);
const appsEvent = ref<Event | undefined>(undefined);
function openApps(e: Event): void {
  appsEvent.value = e;
  appsOpen.value = true;
}
function goModule(path: string): void {
  appsOpen.value = false;
  void router.push(path);
}

// Iniciales para el avatar (mismo cálculo que el footer del sidebar).
const initials = computed<string>(() => {
  const name = user.value?.name?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
  }
  return (user.value?.email?.[0] ?? '?').toUpperCase();
});

function goBack(): void {
  // Si hay historial dentro de la app, volvemos; si no (deep-link), al href de fallback.
  if (window.history.state?.back) router.back();
  else if (props.backHref) void router.push(props.backHref);
}

function goProfile(): void {
  void router.push(PROFILE_ROUTE);
}
</script>

<style scoped>
/* Rejilla de apps estilo «Google apps»: tiles cuadrados con icono + etiqueta. */
.apps-popover {
  --width: 320px;
}
.apps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 12px;
}
.apps-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 14px 6px;
  border-radius: 12px;
  cursor: pointer;
  text-align: center;
  color: inherit;
  transition: background 0.15s ease;
}
.apps-tile:hover,
.apps-tile:focus-visible {
  background: var(--ion-color-step-100, rgba(0, 0, 0, 0.06));
  outline: none;
}
.apps-tile-icon {
  font-size: 1.7rem;
}
.apps-tile-label {
  font-size: 0.72rem;
  line-height: 1.1;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.apps-tile-store .apps-tile-icon {
  color: var(--ion-color-primary, #0091ce);
}
.apps-empty {
  padding: 8px 16px 16px;
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
  text-align: center;
}
</style>
