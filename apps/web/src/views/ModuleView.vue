<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start"><ion-menu-button /></ion-buttons>
        <ion-title>{{ moduleName }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <div v-if="status === 'loading'" class="flex items-center gap-2 py-8 opacity-70">
        <ion-spinner name="crescent" /> Cargando módulo…
      </div>
      <p v-else-if="status === 'error'" class="text-[color:var(--ion-color-danger)]">
        No se pudo cargar el módulo.
      </p>
      <!-- El WebComponent (Lit) de la pestaña activa se monta aquí en runtime (createElement + append). -->
      <div ref="outlet" v-show="status === 'ready'" />
    </ion-content>

    <!-- Tabbar secundario del módulo: las pestañas salen de `navigation[]` del manifest
         (module.json) — el módulo solo aporta el contenido (su WC), el shell pinta la nav.
         Mismo patrón que DashboardPage (ion-footer > ion-toolbar > ion-segment). -->
    <ion-footer v-if="tabs.length > 1" class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          :value="activeNavId"
          @ion-change="onTabChange($event as CustomEvent<{ value: string }>)"
        >
          <ion-segment-button v-for="t in tabs" :key="t.nav.id" :value="t.nav.id">
            <ion-icon :icon="manifestIcon(t.nav.icon)" />
            <ion-label>{{ t.nav.label }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { inject, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent,
  IonFooter, IonSegment, IonSegmentButton, IonIcon, IonLabel, IonSpinner,
} from '@ionic/vue';
import { loadMenu, loadComponent, type MenuEntry } from '../lib/module-loader';
import { clientInjectionKey, getClient } from '../lib/runtime';
import { manifestIcon } from '../lib/icons';

const route = useRoute();
const router = useRouter();
// Cliente del runtime inyectado en el boot (provide en main.ts); fallback al singleton.
const client = inject(clientInjectionKey) ?? getClient();
const outlet = ref<HTMLDivElement | null>(null);
const status = ref<'loading' | 'ready' | 'error'>('loading');
const moduleName = ref<string>('');
/** Entradas de `navigation[]` del módulo activo (pestañas del tabbar). */
const tabs = ref<MenuEntry[]>([]);
const activeNavId = ref<string>('');

function params(): { moduleId: string; navId: string } {
  return {
    moduleId: String(route.params.moduleId ?? ''),
    navId: String(route.params.navId ?? ''),
  };
}

async function mount(): Promise<void> {
  const { moduleId, navId } = params();
  status.value = 'loading';
  try {
    const menu = await loadMenu();
    tabs.value = menu.filter((m) => m.moduleId === moduleId);
    const entry: MenuEntry | undefined =
      tabs.value.find((t) => t.nav.id === navId) ?? tabs.value[0];
    if (!entry) {
      status.value = 'error';
      return;
    }
    moduleName.value = entry.moduleName;
    activeNavId.value = entry.nav.id;
    const tag = await loadComponent(entry);
    if (outlet.value) {
      outlet.value.innerHTML = '';
      const el = document.createElement(tag) as HTMLElement & { client?: unknown };
      // Inyecta el cliente del runtime ANTES de append: el WC (Lit) lo recibe en su
      // primer render y lo usa para query/command/eventos. WC → SDK → Rust (ARQUITECTURA.md §7.5).
      el.client = client;
      outlet.value.appendChild(el);
    }
    status.value = 'ready';
  } catch {
    status.value = 'error';
  }
}

// El segment solo navega; el montaje lo dirige el watcher de la ruta (única fuente de
// verdad — cubre también deep-links y back/forward). replace: cambiar de pestaña no
// apila historial; "atrás" sale del módulo.
function onTabChange(ev: CustomEvent<{ value: string }>): void {
  const navId = ev.detail.value;
  if (navId && navId !== params().navId) {
    void router.replace(`/m/${params().moduleId}/${navId}`);
  }
}

onMounted(() => void mount());
watch(
  () => [route.params.moduleId, route.params.navId],
  () => {
    if (route.name === 'module' && params().moduleId) void mount();
  },
);
</script>
