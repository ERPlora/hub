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
  </ion-header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { IonHeader, IonToolbar, IonButtons, IonButton, IonMenuButton, IonTitle, IonBadge } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { user } from '../lib/session';
import { isDark, toggleTheme } from '../lib/theme';
import { assistantAvailable, toggleAssistant, notificationCount, isLoading } from '../lib/shell';
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
