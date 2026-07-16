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
    <!-- Pantalla de ajustes declarativa (settings-as-widgets): cuando la pestaña activa es la de
         `settings` y el módulo declara el bloque `settings` SIN `component`, el shell pinta el FORM
         GENÉRICO (a partir del JSON Schema) en vez del WC de ajustes del módulo. ADR settings declarativos. -->
    <ModuleSettingsForm
      v-else-if="status === 'ready' && isGenericSettingsTab && settings"
      :module-id="params().moduleId"
      :settings="settings"
    />
    <!-- Módulo de pago BLOQUEADO por la revalidación híbrida (ADR-0114 §6): el dispatcher del
         runtime rechaza sus queries/commands (402) — la UI lo cuenta y manda a gestionar la
         suscripción al SaaS. Los datos locales NUNCA se tocan. La pestaña "Plan" sigue accesible. -->
    <ion-card v-if="status === 'ready' && isBlocked && !isPlanTab" color="warning" class="blocked-card">
      <ion-card-content>
        <strong>{{ t('moduleView.blockedTitle') }}</strong>
        <p class="blocked-hint">{{ t('moduleView.blockedHint') }}</p>
        <ion-button size="small" @click="onManageSubscription">
          <HubIcon name="open-outline" slot="start" />
          {{ t('moduleView.manageSubscription') }}
        </ion-button>
      </ion-card-content>
    </ion-card>

    <!-- El WebComponent (Lit) de la pestaña activa se monta aquí en runtime (createElement + append). -->
    <div
      ref="outlet"
      class="outlet"
      v-show="status === 'ready' && !isPlanTab && !isGenericSettingsTab && !isBlocked"
    />

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
  IonToolbar, IonCard, IonCardContent, IonButton,
  IonFooter, IonSegment, IonSegmentButton,  IonLabel, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ModulePlanPanel from '../components/ModulePlanPanel.vue';
import ModuleSettingsForm from '../components/ModuleSettingsForm.vue';
import { loadMenu, loadComponent, loadManifest, type MenuEntry } from '../lib/module-loader';
import { clientInjectionKey, getClient } from '../lib/runtime';
import { isModuleBlocked, resolveEntitlement } from '../lib/entitlement';
import { openExternal } from '../lib/open-external';
import { config } from '../lib/config';
import type { ModuleBilling, ModuleSettingsDef } from '@erplora/module-types';

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
/**
 * Bloque `settings` del manifest (settings declarativos). Si está y NO trae `component`, la pestaña
 * `settings` del módulo se pinta con el FORM GENÉRICO (ModuleSettingsForm) en vez del WC declarado.
 */
const settings = ref<ModuleSettingsDef | null>(null);
/** ¿Está activa la pestaña sintética "Plan"? */
const isPlanTab = computed(() => activeNavId.value === PLAN_TAB_ID);
/** ¿Módulo de pago bloqueado por la revalidación híbrida? (bloque `revalidation`, ADR-0114 §6). */
const isBlocked = computed(() => isModuleBlocked(params().moduleId));

/** CTA del banner de bloqueo: gestionar la suscripción en el marketplace del SaaS
 *  (deep-link con hub) + recheck del entitlement al recuperar el foco. */
async function onManageSubscription(): Promise<void> {
  const url =
    `${config.cloudApiUrl}/dashboard/marketplace/modules/${encodeURIComponent(params().moduleId)}` +
    `/?hub=${encodeURIComponent(config.hubId)}&utm_source=hub`;
  const recheck = (): void => {
    window.removeEventListener('focus', recheck);
    void resolveEntitlement();
  };
  window.addEventListener('focus', recheck);
  try {
    await openExternal(url);
  } catch {
    window.removeEventListener('focus', recheck);
  }
}
/**
 * ¿La pestaña activa es la de ajustes Y el módulo declara `settings` sin `component`? Entonces el
 * shell pinta el form genérico. Con `settings.component`, en cambio, se monta ese WC (vía outlet).
 */
const isGenericSettingsTab = computed(
  () => activeNavId.value === 'settings' && !!settings.value && !settings.value.component,
);

/** Pestañas del ion-segment = las del módulo + las SINTÉTICAS del shell (Ajustes, Plan). */
const segmentTabs = computed<SegmentTab[]>(() => {
  const list: SegmentTab[] = tabs.value.map((e) => ({
    id: e.nav.id,
    label: e.nav.label,
    icon: e.nav.icon,
    iconSvg: e.iconSvg,
  }));
  // Pestaña de ajustes SINTÉTICA: la coloca el shell a partir del bloque `settings` (igual que los
  // widgets, que no viven en `navigation[]`). Su label/icono salen del propio bloque. Se omite si el
  // módulo ya declara una entrada `navigation` con id `settings` (compatibilidad durante la migración).
  if (settings.value && !tabs.value.some((e) => e.nav.id === 'settings')) {
    // La pestaña SIEMPRE se llama "Ajustes" con icono de engranaje (no el nombre del módulo): es la
    // pestaña de settings, no una pantalla más. `settings.title` se usa como cabecera DENTRO del form.
    list.push({ id: 'settings', label: t('moduleSettings.tab'), icon: 'settings-outline' });
  }
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
    settings.value = manifest?.settings ?? null;

    // Pestaña "Plan": panel del shell, no un WC del módulo → no se monta nada en el outlet.
    if (navId === PLAN_TAB_ID && billing.value) {
      moduleName.value = manifest?.name ?? tabs.value[0]?.moduleName ?? moduleId;
      activeNavId.value = PLAN_TAB_ID;
      if (outlet.value) outlet.value.innerHTML = ''; // el WC previo no debe quedar montado
      status.value = 'ready';
      return;
    }

    // Pestaña de AJUSTES del bloque `settings` (la coloca el shell; NO vive en `navigation[]`, igual
    // que los widgets). Sin `component` → ModuleSettingsForm pinta el form genérico (limpiar outlet).
    // Con `component` (escape-hatch) → montamos ESE WC del módulo, cargando su bundle vía cualquier
    // entry de su nav. Se maneja ANTES del lookup de `entry` porque no hay entrada de nav para settings.
    if (navId === 'settings' && settings.value) {
      moduleName.value = manifest?.name ?? tabs.value[0]?.moduleName ?? moduleId;
      activeNavId.value = 'settings';
      if (settings.value.component) {
        if (tabs.value[0]) await loadComponent(tabs.value[0]); // registra el custom element del bundle
        if (outlet.value) {
          outlet.value.innerHTML = '';
          const el = document.createElement(settings.value.component) as HTMLElement & { client?: unknown };
          el.client = client;
          outlet.value.appendChild(el);
        }
      } else if (outlet.value) {
        outlet.value.innerHTML = '';
      }
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

.blocked-card {
  margin: 12px 0;
}

.blocked-hint {
  margin: 6px 0 12px;
  font-size: 13px;
}
</style>
