<template>
  <AppPage :title="moduleName">
    <div v-if="status === 'loading'" class="flex items-center gap-2 py-8 opacity-70">
      <ion-spinner name="crescent" /> {{ t('moduleView.loading') }}
    </div>
    <p v-else-if="status === 'error'" class="text-[color:var(--ion-color-danger)]">
      {{ t('moduleView.loadError') }}
    </p>
    <!-- Pestaña sintética "Plan" (auto-inyectada para módulos con `billing`): panel del SHELL,
         no un WC del módulo. Se muestra en vez del outlet del WC cuando está activa. -->
    <ModulePlanPanel
      v-if="status === 'ready' && isPlanTab && billing"
      :module-id="params().moduleId"
      :billing="billing"
    />
    <!-- El WebComponent (Lit) de la pestaña activa se monta aquí en runtime (createElement + append). -->
    <div ref="outlet" class="outlet" v-show="status === 'ready' && !isPlanTab" />

    <!-- Tabbar secundario del módulo: las pestañas salen de `navigation[]` del manifest
         (module.json) — el módulo solo aporta el contenido (su WC), el shell pinta la nav.
         Si el módulo tiene `billing`, el shell AÑADE una pestaña sintética "Plan" (id `__plan__`).
         Mismo patrón que DashboardPage (ion-footer > ion-toolbar > ion-segment). -->
    <template #footer>
      <ion-footer v-if="segmentTabs.length > 1" class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          :value="activeNavId"
          @ion-change="onTabChange($event as CustomEvent<{ value: string }>)"
        >
          <ion-segment-button v-for="tb in segmentTabs" :key="tb.id" :value="tb.id">
            <HubIcon :name="tb.iconSvg ?? tb.icon" />
            <ion-label>{{ tb.label }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton,  IonLabel, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ModulePlanPanel from '../components/ModulePlanPanel.vue';
import { loadMenu, loadComponent, loadManifest, type MenuEntry } from '../lib/module-loader';
import { clientInjectionKey, getClient } from '../lib/runtime';
import type { ModuleBilling } from '@erplora/module-types';

/** Id de la pestaña sintética "Plan" auto-inyectada para módulos con `billing`. */
const PLAN_TAB_ID = '__plan__';

/** Una pestaña del ion-segment: las del módulo + la sintética "Plan". */
interface SegmentTab {
  id: string;
  label: string;
  icon?: string;
  iconSvg?: string;
}

const { t } = useI18n();
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
/** Bloque `billing` del manifest del módulo activo (si lo trae) → habilita la pestaña "Plan". */
const billing = ref<ModuleBilling | null>(null);
/** ¿Está activa la pestaña sintética "Plan"? */
const isPlanTab = computed(() => activeNavId.value === PLAN_TAB_ID);

/** Pestañas del ion-segment = las del módulo + (si hay `billing`) la sintética "Plan". */
const segmentTabs = computed<SegmentTab[]>(() => {
  const list: SegmentTab[] = tabs.value.map((e) => ({
    id: e.nav.id,
    label: e.nav.label,
    icon: e.nav.icon,
    iconSvg: e.iconSvg,
  }));
  if (billing.value) {
    list.push({ id: PLAN_TAB_ID, label: t('modulePlan.tab'), icon: 'pricetag' });
  }
  return list;
});

function params(): { moduleId: string; navId: string } {
  return {
    moduleId: String(route.params.moduleId ?? ''),
    navId: String(route.params.navId ?? '')
  };
}

async function mount(): Promise<void> {
  const { moduleId, navId } = params();
  status.value = 'loading';
  try {
    const menu = await loadMenu();
    tabs.value = menu.filter((m) => m.moduleId === moduleId);
    // El bloque `billing` del manifest decide si auto-inyectamos la pestaña "Plan" (sin tocar el
    // module.json de cada módulo). El manifest se sirve completo desde `/modules/<id>/module.json`.
    const manifest = await loadManifest(moduleId);
    billing.value = manifest?.billing ?? null;

    // Pestaña "Plan": panel del shell, no un WC del módulo → no se monta nada en el outlet.
    if (navId === PLAN_TAB_ID && billing.value) {
      moduleName.value = manifest?.name ?? tabs.value[0]?.moduleName ?? moduleId;
      activeNavId.value = PLAN_TAB_ID;
      if (outlet.value) outlet.value.innerHTML = ''; // el WC previo no debe quedar montado
      status.value = 'ready';
      return;
    }

    const entry: MenuEntry | undefined =
      tabs.value.find((tb) => tb.nav.id === navId) ?? tabs.value[0];
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

<style scoped>
/* El WC del módulo se monta en `.outlet` y usa `:host{height:100%}`. Sin una altura
   DEFINIDA aquí, ese 100% resolvía a `auto` (alto del contenido) y el modo `fill` de
   `ok-data-table` (cabecera sticky + pager fijo + scroll SOLO en el cuerpo) no tenía
   contra qué constreñir → scrolleaba la página entera.
   `height:100%` (no `min-height`) fija el outlet al alto del área de `ion-content`:
   - tablas en modo `fill` → su `:host{height:100%}` resuelve a ese alto y el scroll
     queda DENTRO del WC (cabecera/pager fijos);
   - pantallas no-tabla más altas (settings, formularios largos) → su contenido desborda
     el outlet y sigue scrolleando vía `ion-content` (que es el scroller por defecto). */
.outlet {
  height: 100%;
}
</style>
