<template>
  <AppPage :title="moduleName">
    <div v-if="status === 'loading'" class="state-loading">
      <ion-spinner name="crescent" /> {{ t('moduleView.loading') }}
    </div>
    <ok-inline-feedback
      v-else-if="status === 'error'"
      tone="danger"
      icon="alert-circle-outline"
      :heading="t('moduleView.loadError')"
    >
      {{ t('moduleView.loadErrorHint') }}
      <ion-button slot="actions" size="small" fill="outline" @click="mount">
        {{ t('moduleView.retry') }}
      </ion-button>
    </ok-inline-feedback>
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
         runtime rechaza sus queries/commands (402) — la UI lo cuenta y dice dónde se arregla. Los
         datos locales NUNCA se tocan. La pestaña "Plan" sigue accesible.
         El botón que llevaba al marketplace del SaaS se retiró (hub#479): aterrizaba en el
         checkout, y eso es steering. El aviso nombra erplora.com en vez de abrirlo — nadie se
         queda sin saber qué hacer, que era el riesgo de quitarlo a secas. -->
    <ion-card v-if="status === 'ready' && isBlocked && !isPlanTab" color="warning" class="blocked-card">
      <ion-card-content>
        <strong>{{ t('moduleView.blockedTitle') }}</strong>
        <p class="blocked-hint">{{ t('moduleView.blockedHint') }}</p>
      </ion-card-content>
    </ion-card>

    <!--
      hub#775 — el guard `protects` bloquea la pantalla (la mitad cosmética; la autoritativa es el
      dispatcher). La caja está activada y cerrada: el POS no se monta. Si el módulo que declara el
      guard trae un Web Component (`component`, p. ej. `erp-cashregister-open`), se monta ESE; si no,
      fallback genérico del shell con título + pista. Al recibir `resume_on` (`cash_register.session_opened`)
      se re-monta sin recarga manual.
    -->
    <div
      v-if="status === 'ready' && protectsGuard && !isPlanTab && !isGenericSettingsTab"
      ref="protectsOutlet"
      class="outlet protects-outlet"
    >
      <ion-card v-if="!protectsGuard.def.component" color="warning" class="blocked-card">
        <ion-card-content>
          <strong>{{ t('moduleView.protectedTitle') }}</strong>
          <p class="blocked-hint">{{ t('moduleView.protectedHint') }}</p>
          <ion-button slot="actions" size="small" fill="outline" @click="mount">
            {{ t('moduleView.retry') }}
          </ion-button>
        </ion-card-content>
      </ion-card>
    </div>

    <!-- El WebComponent (Lit) de la pestaña activa se monta aquí en runtime (createElement + append). -->
    <div
      ref="outlet"
      class="outlet"
      v-show="status === 'ready' && !isPlanTab && !isGenericSettingsTab && !isBlocked && !protectsGuard"
    />

    <!-- Tabbar secundario del módulo: las pestañas salen de `navigation[]` del manifest
         (module.json) — el módulo solo aporta el contenido (su WC), el shell pinta la nav.
         Si el módulo tiene `billing`, el shell AÑADE una pestaña sintética "Plan" (id `__plan__`).
         Mismo patrón que DashboardPage (ion-footer > ion-toolbar > ion-segment). -->
    <template #footer>
      <ion-footer v-if="segmentTabs.length > 1" class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          class="ok-tabbar module-tabbar"
          ref="tabbar"
          scrollable
          :value="activeNavId"
          @ion-change="onTabChange($event as CustomEvent<{ value: string }>)"
        >
          <ion-segment-button
            v-for="tb in segmentTabs"
            :key="tb.id"
            :value="tb.id"
            :aria-label="tb.label"
          >
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
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
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
import { scrollActiveTabIntoView } from '@erplora/outfitkit/tabbar';
import { clientInjectionKey, getClient } from '../lib/runtime';
import { resolveProtectsGuard, type ActiveProtectsGuard } from '../lib/protects';
import { isModuleBlocked, resolveEntitlement } from '../lib/entitlement';
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
/** Outlet del guard `protects` (hub#775): aquí se monta el WC `component` del módulo que declara el guard. */
const protectsOutlet = ref<HTMLDivElement | null>(null);
/** El `ion-segment` del tabbar de footer (ver `revealActiveTab`). */
const tabbar = ref<{ $el?: HTMLElement } | null>(null);
const status = ref<'loading' | 'ready' | 'error'>('loading');
const moduleName = ref<string>('');
/** Entradas de `navigation[]` del módulo activo (pestañas del tabbar). */
const tabs = ref<MenuEntry[]>([]);
const activeNavId = ref<string>('');
/**
 * Guard `protects` activo para esta ruta (hub#775), o `null` si la ruta no está protegida ahora
 * mismo. Lo resuelve `mount()` antes de montar el WC del módulo; al recibir `resume_on` se anula
 * y se re-monta sin recarga manual.
 */
const protectsGuard = ref<ActiveProtectsGuard | null>(null);
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

/**
 * Re-comprueba el entitlement al recuperar el foco: quien acaba de contratar en erplora.com vuelve
 * a esta pantalla y el bloqueo se levanta solo, sin recargar.
 *
 * Antes esto colgaba de `onManageSubscription()` —el botón que abría el marketplace del SaaS— y se
 * desenganchaba tras el primer foco, porque solo cubría «el usuario acaba de salir a comprar». Al
 * retirar ese botón (hub#479) el recheck no se va con él: se queda PERMANENTE mientras la vista
 * vive, que además cubre el caso que antes no cubría —contratar desde el móvil o desde otro equipo
 * mientras el TPV sigue abierto aquí—. Sin él, quitar el botón habría dejado el módulo bloqueado
 * hasta un F5 a mano.
 */
const recheckEntitlement = (): void => void resolveEntitlement();
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

let mountGeneration = 0;
/**
 * Limpieza de la suscripción a `resume_on` del guard `protects` activo (hub#775). Se anulaba
 * implícitamente al remontar; ahora se guarda para poder quitarla al desmontar la vista.
 */
let protectsUnsub: (() => void) | null = null;
function clearProtectsSubscription(): void {
  if (protectsUnsub) {
    protectsUnsub();
    protectsUnsub = null;
  }
}

async function mount(): Promise<void> {
  const generation = ++mountGeneration;
  const { moduleId, navId } = params();
  status.value = 'loading';
  // Cada montaje empieza SIN guard: o se vuelve a evaluar abajo, o no aplica (p. ej. pestaña Plan).
  protectsGuard.value = null;
  clearProtectsSubscription();
  try {
    const menu = await loadMenu();
    if (generation !== mountGeneration) return;
    tabs.value = menu.filter((m) => m.moduleId === moduleId);
    // El bloque `billing` del manifest decide si auto-inyectamos la pestaña "Plan" (sin tocar el
    // module.json de cada módulo). El manifest se sirve completo desde `/modules/<id>/module.json`.
    const manifest = await loadManifest(moduleId);
    if (generation !== mountGeneration) return;
    billing.value = manifest?.billing ?? null;
    settings.value = manifest?.settings ?? null;

    // Pestaña "Plan": panel del shell, no un WC del módulo → no se monta nada en el outlet.
    if (navId === PLAN_TAB_ID && billing.value) {
      moduleName.value = manifest?.name ?? tabs.value[0]?.moduleName ?? moduleId;
      activeNavId.value = PLAN_TAB_ID;
      if (outlet.value) outlet.value.replaceChildren(); // el WC previo no debe quedar montado
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
        if (generation !== mountGeneration) return;
        if (outlet.value) {
          outlet.value.replaceChildren();
          const el = document.createElement(settings.value.component) as HTMLElement & { client?: unknown };
          el.client = client.forModule(moduleId);
          outlet.value.appendChild(el);
        }
      } else if (outlet.value) {
        outlet.value.replaceChildren();
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

    // hub#775 — el guard `protects` sobre ESTA ruta. Si está armado y la precondición no se cumple
    // (la caja está cerrada), el POS no se monta: se renderiza el `component` del módulo que declara
    // el guard (p. ej. `erp-cashregister-open`) o, si no trae WC, el fallback genérico del shell.
    // La mitad autoritativa la sigue haciendo el dispatcher; esto es UX.
    const guard = await resolveProtectsGuard(client, route.path);
    if (generation !== mountGeneration) return;
    if (guard) {
      protectsGuard.value = guard;
      if (outlet.value) outlet.value.replaceChildren(); // el WC previo no debe quedar montado
      if (guard.def.component) {
        // Registra el custom element del módulo que DECLARA el guard (cash_register), no el protegido.
        // Su bundle se resuelve por cualquiera de sus propias entradas de navegación.
        try {
          const declaringMenu = await loadMenu();
          const declaringEntry = declaringMenu.find((m) => m.moduleId === guard.declaringModule);
          if (declaringEntry) await loadComponent(declaringEntry);
        } catch {
          // sin bundle → el fallback genérico del template se queda
        }
        if (generation !== mountGeneration) return;
        if (protectsOutlet.value) {
          protectsOutlet.value.replaceChildren();
          const el = document.createElement(guard.def.component) as HTMLElement & { client?: unknown };
          // El componente del guard lo aporta OTRO módulo (el que declara el `protects`), así que
          // el scope es el suyo y no el de la página que se está bloqueando (hub#714).
          el.client = client.forModule(guard.declaringModule);
          protectsOutlet.value.appendChild(el);
        }
      }
      // Escucha `resume_on` para re-montar sin recarga manual en cuanto se abra la caja.
      if (typeof client.on === 'function') {
        protectsUnsub = client.on(guard.def.resume_on, () => {
          void mount().then(revealActiveTab);
        });
      }
      status.value = 'ready';
      return;
    }

    const tag = await loadComponent(entry);
    if (generation !== mountGeneration) return;
    if (outlet.value) {
      outlet.value.replaceChildren();
      const el = document.createElement(tag) as HTMLElement & { client?: unknown };
      // Inyecta el cliente del runtime ANTES de append: el WC (Lit) lo recibe en su
      // primer render y lo usa para query/command/eventos. WC → SDK → Rust (ARQUITECTURA.md §7.5).
      //
      // Va con el SCOPE del módulo (hub#714): el id sale de AQUÍ, del cargador —el único que sabe
      // de verdad qué módulo está montando—, no de lo que el módulo diga de sí mismo. Es lo que
      // habilita `client.flows` (kernel de automatización, ADR-0283 §9) y lo que el runtime lee
      // para exigir la capability `manage_flows`.
      el.client = client.forModule(moduleId);
      outlet.value.appendChild(el);
    }
    status.value = 'ready';
    // Un navId retirado o mal escrito no puede dejar la URL afirmando una pestaña mientras se
    // muestra otra. Canonizamos al primer tab real (también cubre bookmarks de versiones viejas).
    if (navId !== entry.nav.id) {
      void router.replace(`/m/${moduleId}/${entry.nav.id}`);
    }
  } catch {
    if (generation !== mountGeneration) return;
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

/**
 * Trae a la vista la pestaña activa del tabbar. Hace falta porque la pestaña activa la fija la RUTA
 * (deep-link, back/forward), no un toque: con 5 pestañas —`tables`, `verifactu`— la barra ya
 * desborda en un móvil de 390px y la activa puede quedar fuera de pantalla al montar. Ionic no lo
 * cubre. Se espera a `nextTick` (Vue pinta el segment) + un frame (Ionic aplica
 * `.segment-button-checked` en su propio ciclo, no en el de Vue).
 */
async function revealActiveTab(): Promise<void> {
  await nextTick();
  requestAnimationFrame(() => {
    scrollActiveTabIntoView((tabbar.value?.$el as HTMLElement | undefined) ?? null);
  });
}

onMounted(() => {
  window.addEventListener('focus', recheckEntitlement);
  void mount().then(revealActiveTab);
});
watch(
  () => [route.params.moduleId, route.params.navId],
  () => {
    if (route.name === 'module' && params().moduleId) void mount().then(revealActiveTab);
  },
);

onBeforeUnmount(() => {
  window.removeEventListener('focus', recheckEntitlement);
  mountGeneration += 1;
  clearProtectsSubscription();
  outlet.value?.replaceChildren();
  protectsOutlet.value?.replaceChildren();
});
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

/* Las rutas de módulo usan nombres de producto, no abreviaturas automáticas. Un mínimo más ancho
   fuerza scroll horizontal antes de que Ionic aplaste o trunque «Etiquetas», «Configuración», etc. */
.module-tabbar {
  --ok-tabbar-min: 116px;
}

.module-tabbar ion-segment-button {
  min-width: var(--ok-tabbar-min);
}

.module-tabbar ion-label {
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
  line-height: 1.1;
}

/* Estados de carga/error al montar el WC del módulo. Antes usaban utilidades Tailwind
   (flex/opacity) y un valor arbitrario text-[color:...]; ahora scoped con tokens Ionic,
   misma línea que el dashboard. */
.state-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  opacity: 0.7;
}
.blocked-card {
  margin: 12px 0;
}

.blocked-hint {
  margin: 6px 0 12px;
  font-size: 13px;
}
</style>
