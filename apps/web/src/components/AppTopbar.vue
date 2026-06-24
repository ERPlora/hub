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
        <!-- Rail-toggle (colapsar/expandir el menú lateral). Paridad con Cloud: vive en la topbar
             de TODA la app, a la derecha del back. Icono `panel-left` (= lucide:panel-left de Cloud).
             Solo escritorio (.rail-toggle se oculta en móvil, donde manda el drawer). -->
        <ion-button
          class="rail-toggle"
          fill="clear"
          :aria-label="railCollapsed ? t('topbar.expandMenu') : t('topbar.collapseMenu')"
          @click="railCollapsed = !railCollapsed"
        >
          <HubIcon slot="icon-only" name="panel-left" />
        </ion-button>
      </ion-buttons>

      <ion-title>{{ title }}</ion-title>

      <ion-buttons slot="end">
        <!-- Acciones propias de la vista (a la izquierda de los controles globales). -->
        <slot name="actions" />

        <!-- Apps (rejilla estilo Google): acceso rápido a los módulos instalados desde cualquier
             pantalla. ok-app-launcher (OutfitKit) abre una hoja inferior con la rejilla de módulos
             + enlace a la tienda. Los módulos NO viven en el sidebar; se entra por aquí o por el
             Home (pestaña Aplicaciones). Iconos pre-resueltos a SVG horneado (offline/CSP). -->
        <ok-app-launcher
          :apps="launcherApps"
          :labels="launcherLabels"
          @ok-app-select="onAppSelect"
        ></ok-app-launcher>

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

        <!-- Notificaciones: campana + badge. Central de notificaciones de EVENTOS (placeholder):
             el contador es un STUB a 0 (lib/shell, sin backend de notificaciones todavía) y el
             popover muestra un estado vacío. NO está acoplada a la configuración pendiente de los
             módulos — eso vive SOLO en el dashboard (ADR-0063, banner). -->
        <ion-button
          id="topbar-notif-btn"
          fill="clear"
          class="topbar-notif"
          :aria-label="t('topbar.notifications')"
          :title="t('topbar.notifications')"
        >
          <HubIcon slot="icon-only" name="notifications-outline" />
          <ion-badge v-if="notificationCount > 0" color="danger" class="notif-badge">
            {{ notificationCount }}
          </ion-badge>
        </ion-button>
        <ion-popover trigger="topbar-notif-btn" trigger-action="click">
          <ion-content>
            <ion-list lines="full">
              <ion-item lines="none">
                <ion-label class="ion-text-wrap" style="opacity:.6">{{ t('topbar.noNotifications') }}</ion-label>
              </ion-item>
            </ion-list>
          </ion-content>
        </ion-popover>

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
  </ion-header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonHeader, IonToolbar, IonButtons, IonButton, IonMenuButton, IonTitle, IonBadge,
  IonPopover, IonContent, IonList, IonItem, IonLabel,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { user } from '../lib/session';
import { isDark, toggleTheme } from '../lib/theme';
import { assistantAvailable, toggleAssistant, notificationCount, isLoading, railCollapsed } from '../lib/shell';
import { moduleNav } from '../lib/nav';
import { resolveIcon } from '../lib/icons';
import { PROFILE_ROUTE } from '../lib/routes';

// Una entrada de la rejilla de ok-app-launcher (OutfitKit). Espejo de su `OkLauncherApp`.
interface LauncherApp {
  id: string;
  label: string;
  icon: string;
  color?: string;
}

const props = defineProps<{
  /** Título de la vista. */
  title: string;
  /** Href de fallback del botón Back. Si se pasa, la vista es de detalle y muestra el Back. */
  backHref?: string;
}>();

const { t } = useI18n();
const router = useRouter();

const backHref = computed<string | undefined>(() => props.backHref);

// Rejilla de apps para ok-app-launcher: un tile por módulo instalado + la Tienda al final.
// El icono se PRE-RESUELVE a SVG horneado (resolveIcon, offline/CSP); el launcher lo detecta como
// SVG ya resuelto y lo pinta vía la prop `icon` de ion-icon (no por nombre). `id` = ruta del shell.
const launcherApps = computed<LauncherApp[]>(() => {
  const apps: LauncherApp[] = moduleNav.value.map((m) => ({
    id: m.path,
    label: m.label,
    icon: resolveIcon(m.icon),
  }));
  // Tienda: siempre presente, para instalar más módulos (color de marca).
  apps.push({
    id: '/marketplace',
    label: t('nav.marketplace'),
    icon: resolveIcon('storefront-outline'),
    color: 'var(--ion-color-primary, #0091ce)',
  });
  return apps;
});

// Textos traducibles de la hoja del launcher (título/aria + vacío + cerrar).
const launcherLabels = computed(() => ({
  apps: t('topbar.apps'),
  empty: t('topbar.appsEmpty'),
  close: t('topbar.appsClose'),
}));

// Selección de una app: navega por el router del shell (SPA), no recarga la página.
function onAppSelect(e: Event): void {
  const id = (e as CustomEvent<{ id: string }>).detail?.id;
  if (id) void router.push(id);
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
/* ok-app-launcher (OutfitKit): alinea el trigger con los ion-button de la topbar y mapea sus
   tokens al theme del Hub (la hoja interna ya hereda --ion-* vía la cadena --ok-* → --ion-*). */
ok-app-launcher {
  display: inline-flex;
  align-items: center;
}
</style>
