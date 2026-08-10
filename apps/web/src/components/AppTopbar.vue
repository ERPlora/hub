<!--
  AppTopbar — topbar compartida del shell del Hub (paridad con cloud/templates/page_base.html).
  Sustituye el `<ion-header><ion-toolbar>` que cada vista duplicaba. Primitivos Ionic.

  Orden/iconos iguales al shell de Cloud:
    start:  menu-button (drawer móvil; Ionic lo oculta en ≥lg) · back contextual
    title:  título de la vista (prop `title`)
    end:    [slot actions de la vista] · apps (rejilla) · gestión (nube) · asistente (sparkles)
            · notificaciones (campana+badge)
    bajo el toolbar: barra de progreso mientras hay peticiones en vuelo.

  En MÓVIL (<768px, `isCompactViewport`) las tres acciones globales se pliegan en un solo menú
  (`ellipsis-vertical`): en modo `ios` Ionic centra el `ion-title`, así que los iconos no lo empujan
  — lo tapan. El launcher de apps se queda fuera del menú porque es la puerta a los módulos.

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

        <!-- Con sitio (≥768px): las acciones globales, una a una. -->
        <template v-if="!isCompactViewport">
          <!-- Management (hub#364, PLAN step 8, ADR-0251): the door to the SaaS panel — plans,
               invoices and businesses are NOT screens of this app, so this LINKS (it does not
               write). Only whoever administers the hub sees it (`hub.administer`, ADR-0248): a
               filter, not a wall, because it refuses a cashier nothing — it simply is not their
               task. The mark is a CLOUD, not the shell's generic `open-outline`: Billing, Profile
               and ModuleView use that one next to a sentence that explains it, while this sits
               icon-only among three other icons and has to name the DESTINATION (the online
               account), not merely announce that something opens. The accessible name says
               `erplora.com` out loud, which is all an icon-only action crossing a product boundary
               has. It leaves through the door OUT — new tab in a browser, system browser in the
               installed app — and the reasons live in management-link.ts. Note: the labels of the
               login→till path ("Mi plan", "Añadir funciones") belong to hub#365. -->
          <ion-button
            v-if="canOpenManagement"
            data-testid="topbar-manage"
            fill="clear"
            :aria-label="t('topbar.manage')"
            :title="t('topbar.manage')"
            @click="openManagement"
          >
            <HubIcon slot="icon-only" name="cloud-outline" />
          </ion-button>

          <!-- Asistente (sparkles): visible cuando la capacidad está disponible. Abre el drawer. -->
          <ion-button
            v-if="assistantAvailable"
            data-testid="topbar-assistant"
            fill="clear"
            :aria-label="t('topbar.assistant')"
            :title="t('topbar.assistant')"
            @click="toggleAssistant"
          >
            <HubIcon slot="icon-only" name="sparkles-outline" />
          </ion-button>

          <!-- Campana de notificaciones (hub#660): el contador lo alimenta el watcher de lib/dead-letter
               desde el endpoint de count. Con eventos caídos, el popover avisa y lleva directo a
               Sistema → Eventos, donde se reenvían (uno/todos) o se descartan; sin nada, el estado
               vacío de siempre. -->
          <ion-button
            data-testid="topbar-notifications"
            fill="clear"
            class="topbar-notif"
            :aria-label="t('topbar.notifications')"
            :title="t('topbar.notifications')"
            @click="openNotifications"
          >
            <HubIcon slot="icon-only" name="notifications-outline" />
            <ion-badge v-if="notificationCount > 0" color="danger" class="notif-badge">
              {{ notificationCount }}
            </ion-badge>
          </ion-button>
        </template>

        <!-- Sin sitio (<768px): UN botón. Ionic centra el `ion-title` en modo `ios`, así que estos
             iconos no empujaban el título — se le ponían encima y lo tapaban (reportado a 390px el
             2026-08-09). Se pliegan en un menú, que es lo que hace cualquier barra de móvil.
             `v-if`/`v-else` y no `display:none`: escondidas por CSS las cuatro acciones seguirían en
             el orden de tabulación y anunciadas, duplicadas. El launcher de apps NO se pliega: es la
             puerta a los módulos instalados (el TPV), no una acción secundaria, y ya abre su hoja. -->
        <template v-else>
          <ion-button
            data-testid="topbar-more"
            fill="clear"
            class="topbar-notif"
            :aria-label="t('topbar.more')"
            :title="t('topbar.more')"
            @click="openMore"
          >
            <HubIcon slot="icon-only" name="ellipsis-vertical" />
            <!-- El badge viaja con el menú: plegar la campana no puede esconder que hay algo. -->
            <ion-badge v-if="notificationCount > 0" color="danger" class="notif-badge">
              {{ notificationCount }}
            </ion-badge>
          </ion-button>
          <!-- `keep-contents-mounted`: las filas son tres y así el menú abre pintado, sin el salto
               de la primera vez (y son observables sin presentar el overlay). -->
          <ion-popover
            :is-open="moreOpen"
            :event="moreEvent"
            keep-contents-mounted
            @did-dismiss="moreOpen = false"
          >
            <ion-content>
              <ion-list lines="full">
                <ion-item
                  v-if="canOpenManagement"
                  button
                  :detail="false"
                  data-testid="topbar-more-manage"
                  @click="pick(openManagement)"
                >
                  <HubIcon slot="start" name="cloud-outline" />
                  <ion-label class="ion-text-wrap">{{ t('topbar.manage') }}</ion-label>
                </ion-item>
                <ion-item
                  v-if="assistantAvailable"
                  button
                  :detail="false"
                  data-testid="topbar-more-assistant"
                  @click="pick(toggleAssistant)"
                >
                  <HubIcon slot="start" name="sparkles-outline" />
                  <ion-label>{{ t('topbar.assistant') }}</ion-label>
                </ion-item>
                <ion-item
                  button
                  :detail="false"
                  data-testid="topbar-more-notifications"
                  @click="pick(openNotifications)"
                >
                  <HubIcon slot="start" name="notifications-outline" />
                  <ion-label>{{ t('topbar.notifications') }}</ion-label>
                  <ion-badge v-if="notificationCount > 0" slot="end" color="danger">
                    {{ notificationCount }}
                  </ion-badge>
                </ion-item>
              </ion-list>
            </ion-content>
          </ion-popover>
        </template>

        <!-- La central de notificaciones es UNA, la abran la campana o la fila del menú: por eso va
             gobernada por `is-open` y no por `trigger`, que solo sabe atarse a un botón. -->
        <ion-popover :is-open="notifOpen" :event="notifEvent" @did-dismiss="notifOpen = false">
          <ion-content>
            <ion-list lines="full">
              <ion-item v-if="notificationCount > 0" lines="none" button detail @click="goToDeadLetters">
                <HubIcon slot="start" name="alert-circle-outline" color="danger" />
                <ion-label class="ion-text-wrap">
                  <h3>{{ t('topbar.deadLettersTitle') }}</h3>
                  <p>{{ t('topbar.deadLettersBody', { count: notificationCount }) }}</p>
                </ion-label>
              </ion-item>
              <ion-item v-else lines="none">
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
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonHeader, IonToolbar, IonButtons, IonButton, IonMenuButton, IonTitle, IonBadge,
  IonPopover, IonContent, IonList, IonItem, IonLabel,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { assistantAvailable, toggleAssistant, notificationCount, isLoading, railCollapsed } from '../lib/shell';
import { canOpenManagement, openManagement } from '../lib/management-link';
import { isCompactViewport } from '../lib/viewport';
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

// ── Los dos overlays de la barra ────────────────────────────────────────────
// Ambos van gobernados por `is-open` (y no por `trigger`) porque los abre más de un sitio: la
// central de notificaciones, la campana o la fila del menú. `event` es lo que ancla el popover al
// botón que lo abrió; abierto desde el menú no hay ancla viva —esa fila desaparece con el propio
// menú— y Ionic lo centra, que en un móvil es exactamente donde debe salir.
const moreOpen = ref(false);
const moreEvent = ref<Event | undefined>(undefined);
const notifOpen = ref(false);
const notifEvent = ref<Event | undefined>(undefined);

function openMore(event: Event): void {
  moreEvent.value = event;
  moreOpen.value = true;
}

function openNotifications(event?: Event): void {
  notifEvent.value = event;
  notifOpen.value = true;
}

/** Elegir en el menú lo CIERRA: una acción ejecutada y el menú aún abierto encima es un menú roto. */
function pick(action: (event?: Event) => void): void {
  moreOpen.value = false;
  action();
}

function goBack(): void {
  // Si hay historial dentro de la app, volvemos; si no (deep-link), al href de fallback.
  if (window.history.state?.back) router.back();
  else if (props.backHref) void router.push(props.backHref);
}

// La campana avisa de dead-letters: llevar directo a la pestaña donde se gestionan (hub#660).
function goToDeadLetters(): void {
  void router.push({ path: '/system', hash: '#events' });
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
