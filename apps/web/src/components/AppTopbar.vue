<!--
  AppTopbar — topbar compartida del shell del Hub (paridad con cloud/templates/page_base.html).
  Sustituye el `<ion-header><ion-toolbar>` que cada vista duplicaba. Primitivos Ionic.

  Orden/iconos iguales al shell de Cloud:
    start:  menu-button (drawer móvil; Ionic lo oculta en ≥lg) · back contextual
    title:  título de la vista (prop `title`)
    end:    [slot actions de la vista] · apps (rejilla) · asistente (sparkles)
            · notificaciones (campana+badge)
    bajo el toolbar: barra de progreso mientras hay peticiones en vuelo.

  El toggle de tema y el avatar se retiraron (2026-07-16, no cabían en móvil): tema → Ajustes;
  usuario/perfil → cabecera del sidebar (App.vue).

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

        <!-- Management (hub#364, PLAN step 8, ADR-0251): the door to the SaaS panel — plans,
             invoices and businesses are NOT screens of this app, so this LINKS (it does not write).
             Only whoever administers the hub sees it (`hub.administer`, ADR-0248): a filter, not a
             wall, because it refuses a cashier nothing — it simply is not their task. `open-outline`
             is the mark the shell already uses for "this leads to the SaaS" (Billing, Profile,
             ModuleView). The accessible name says the destination out loud: it is all an icon-only
             action has, and this one crosses the product boundary. Opens in THIS tab — the reasons
             live in management-link.ts. Note: the labels of the login→till path ("Mi plan", "Añadir
             funciones") belong to hub#365; this only names its own button. -->
        <ion-button
          v-if="canOpenManagement"
          data-testid="topbar-manage"
          fill="clear"
          :aria-label="t('topbar.manage')"
          :title="t('topbar.manage')"
          @click="openManagement"
        >
          <HubIcon slot="icon-only" name="open-outline" />
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

        <!-- El toggle de tema y el avatar se RETIRARON de la topbar (2026-07-16): en móvil no
             cabían los iconos. El tema se cambia en Ajustes (selector system/light/dark) y el
             usuario/perfil vive en la cabecera del sidebar (App.vue). -->
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
import { assistantAvailable, toggleAssistant, notificationCount, isLoading, railCollapsed } from '../lib/shell';
import { canOpenManagement, openManagement } from '../lib/management-link';
import { moduleNav } from '../lib/nav';
import { resolveIcon } from '../lib/icons';

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

// Rejilla de apps para ok-app-launcher: un tile por módulo instalado + Apps (la tienda) al final.
// El icono se PRE-RESUELVE a SVG horneado (resolveIcon, offline/CSP); el launcher lo detecta como
// SVG ya resuelto y lo pinta vía la prop `icon` de ion-icon (no por nombre). `id` = ruta del shell.
const launcherApps = computed<LauncherApp[]>(() => {
  const apps: LauncherApp[] = moduleNav.value.map((m) => ({
    id: m.path,
    label: m.label,
    icon: resolveIcon(m.icon),
  }));
  // Apps (la tienda): siempre presente, para instalar más módulos (color de marca).
  apps.push({
    id: '/apps',
    label: t('nav.apps'),
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

function goBack(): void {
  // Si hay historial dentro de la app, volvemos; si no (deep-link), al href de fallback.
  if (window.history.state?.back) router.back();
  else if (props.backHref) void router.push(props.backHref);
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
