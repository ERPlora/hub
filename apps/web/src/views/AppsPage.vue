<template>
  <AppPage :title="t('nav.apps')">
    <div v-if="loading" class="flex justify-center py-10">
      <ion-spinner name="crescent" />
    </div>

    <!-- `.fill` fija el alto al área de ion-content para que cabecera/pager de la tabla queden
         fijos y el scroll viva solo en el cuerpo (mismo patrón que EmployeesPage/ModuleView). -->
    <!-- 100% de ancho; el padding lo aporta el `ion-content` de AppPage (un solo ion-padding,
         como todas las vistas). La vista por defecto es GRID (tarjetas) — se fija en onMounted. -->
    <div v-else class="fill">
      <ok-inline-feedback v-if="!isAdmin" tone="info" class="mb-3">
        {{ t('apps.adminOnly') }}
      </ok-inline-feedback>
      <ok-inline-feedback v-if="config.demo && tab !== 'mine'" tone="info" class="mb-3">
        {{ t('apps.demoCatalogReadOnly') }}
      </ok-inline-feedback>
      <ok-inline-feedback v-if="catalogError && tab !== 'mine'" tone="danger" class="mb-3">
        <span>{{ t('apps.catalogLoadError') }}</span>
        <ion-button size="small" fill="clear" @click="loadCatalog">
          {{ t('apps.retryCatalog') }}
        </ion-button>
      </ok-inline-feedback>

      <div v-if="tab !== 'mine'" class="catalog-country" data-testid="marketplace-country-filter">
        <ion-label>{{ t('apps.countryFilter') }}</ion-label>
        <ion-select
          v-model="catalogCountry"
          interface="popover"
          :aria-label="t('apps.countryFilter')"
          @ion-change="onCatalogCountryChange($event.detail.value as string)"
        >
          <ion-select-option v-for="country in MARKETPLACE_COUNTRIES" :key="country" :value="country">
            {{ country }}
          </ion-select-option>
        </ion-select>
      </div>

      <!-- Mis módulos: instalados SEGÚN EL RUNTIME (fuente de verdad local) + ciclo de vida. -->
      <ok-data-table
        v-show="tab === 'mine'"
        ref="mineTable"
        fill
        :columns="mineColumns"
        :rows="installedRows"
        :views="['cards', 'table']"
        default-view="cards"
        :searchKeys="['name']"
        :actions="mineActions"
        :labels="tableLabels"
        :search-placeholder="t('apps.searchInstalled')"
        :empty-message="t('apps.emptyInstalled')"
        page-size="10"
        column-picker
      ></ok-data-table>

      <!-- Catálogo / Pago: módulos del Cloud. -->
      <ok-data-table
        v-show="tab !== 'mine'"
        ref="catalogTable"
        fill
        :columns="catalogColumns"
        :rows="filteredModules"
        :views="['cards', 'table']"
        default-view="cards"
        :searchKeys="['name', 'desc', 'cat']"
        :actions="catalogActions"
        :labels="tableLabels"
        :search-placeholder="t('apps.searchCatalog')"
        :empty-message="t('apps.emptyCatalog')"
        page-size="10"
        column-picker
      ></ok-data-table>
    </div>

    <!-- Modal de consentimiento de permisos al instalar (best-effort). Solo aparece si el módulo a
         instalar DECLARA capabilities; instalar concede todas (PUT a true). La gestión autoritativa
         posterior vive en Ajustes → Permisos. Si no declara ninguna, se instala directo (sin modal). -->
    <ion-modal :is-open="consentOpen" @did-dismiss="closeConsent">
      <ion-header>
        <ion-toolbar>
          <ion-title>{{ t('apps.consentTitle') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button @click="closeConsent">
              <HubIcon name="close-outline" />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <p class="mb-3">{{ t('apps.consentIntro') }}</p>
        <ion-list lines="full">
          <ion-item v-for="cap in consentCaps" :key="cap.id">
            <HubIcon slot="start" name="shield-checkmark-outline" />
            <ion-label class="ion-text-wrap">
              <h2>{{ cap.label }}</h2>
              <p>{{ cap.description }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
        <ion-button class="mt-3" expand="block" @click="confirmConsentInstall">
          <HubIcon slot="start" name="download-outline" />
          {{ t('apps.consentInstallGrant') }}
        </ion-button>
        <ion-button class="mt-2" expand="block" fill="outline" @click="closeConsent">
          {{ t('apps.consentCancel') }}
        </ion-button>
      </ion-content>
    </ion-modal>

    <!-- ADR-0060: el Cloud resuelve el árbol completo ANTES de instalar. Dependencias gratis =
         consentimiento informativo; cualquier nodo bloqueado = compra explícita, nunca autocobro. -->
    <ion-modal :is-open="planOpen" data-testid="install-plan-modal" @did-dismiss="closePlan">
      <ion-header>
        <ion-toolbar>
          <ion-title>{{ plan?.blocked ? t('apps.planBlockedTitle') : t('apps.planTitle') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button :aria-label="t('apps.consentCancel')" @click="closePlan">
              <HubIcon name="close-outline" />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <p>{{ plan?.blocked ? t('apps.planBlockedIntro') : t('apps.planIntro') }}</p>
        <ion-list lines="full" data-testid="install-plan-items">
          <ion-item v-for="node in plan?.plan ?? []" :key="node.module_id">
            <HubIcon slot="start" :name="node.requires_purchase ? 'card-outline' : 'cube-outline'" />
            <ion-label class="ion-text-wrap">
              <h2>{{ moduleName(node.module_id) }}</h2>
              <p>{{ node.reason === 'dependency' ? t('apps.planDependency') : t('apps.planRequested') }} · v{{ node.version }}</p>
            </ion-label>
            <ion-button
              v-if="node.requires_purchase"
              slot="end"
              size="small"
              data-testid="install-plan-purchase"
              @click="openPlanPurchase(node)"
            >
              {{ t('apps.planPurchase') }}
            </ion-button>
          </ion-item>
        </ion-list>
        <ion-button
          v-if="plan && !plan.blocked"
          class="mt-3"
          expand="block"
          data-testid="install-plan-confirm"
          @click="confirmPlanInstall"
        >
          <HubIcon slot="start" name="download-outline" />
          {{ t('apps.planConfirm') }}
        </ion-button>
        <ion-button class="mt-2" expand="block" fill="outline" @click="closePlan">
          {{ t('apps.consentCancel') }}
        </ion-button>
      </ion-content>
    </ion-modal>

    <!-- Toast simple (Ionic IonToast no requiere importaciones extra en el template) -->
    <ion-toast
      :is-open="toastOpen"
      :message="toastMsg"
      :color="toastColor"
      :duration="toastDuration"
      @did-dismiss="toastOpen = false"
    />
    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar" :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="mine">
            <HubIcon name="cube-outline" />
            <ion-label>{{ t('apps.tabMine') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="all">
            <HubIcon name="storefront-outline" />
            <ion-label>{{ t('apps.tabCatalog') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="paid">
            <HubIcon name="wallet-outline" />
            <ion-label>{{ t('apps.tabPaid') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel,
  IonSpinner, IonToast,
  IonSelect, IonSelectOption,
  IonModal, IonHeader, IonTitle, IonButtons, IonButton, IonContent,
  IonList, IonItem, alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { dataTableLabels } from '../lib/data-table-labels';

const { t, locale } = useI18n();
const tableLabels = computed(() => dataTableLabels(locale.value));
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall, previewInstallPlan,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  getModuleCapabilities, putModuleCapabilities,
  type InstalledModule, type ModuleCapability, type InstallPlan, type InstallPlanNode
} from '../lib/runtime';
import { refreshModuleNav } from '../lib/nav';
import { isModuleInstalled } from '../lib/apps-catalog';
import { resolveEntitlement } from '../lib/entitlement';
import { openExternal } from '../lib/open-external';
import { isAdmin } from '../lib/session';
import { hubSettings } from '../lib/hub-settings';

// --- Tipos ---
interface Mod {
  id: string;
  name: string;
  desc: string;
  price: string;
  paid: boolean;
  installed: boolean;
  available: boolean;
  cat: string;
  /** Versión a instalar; si el Cloud no la expone usamos 'latest' en el request-install. */
  version?: string;
  countries: string[];
  coverage: string;
}

type AppsTab = 'mine' | 'all' | 'paid';
const TABS: readonly AppsTab[] = ['mine', 'all', 'paid'];

const route = useRoute();
const router = useRouter();
// Deep-link por HASH (/apps#paid) — la ruta base no cambia, así Ionic no la trata como página
// secundaria (mismo patrón que Settings/System/etc.). Sincroniza tab ↔ hash.
const tab = ref<AppsTab>(TABS.find((v) => v === route.hash.slice(1)) ?? 'mine');
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'mine')) void router.replace({ hash: `#${value}` });
});
watch(() => route.hash, (h) => {
  const next = TABS.find((v) => v === h.slice(1)) ?? 'mine';
  if (next !== tab.value) tab.value = next;
});

// ok-data-table (OutfitKit) está registrado en main.ts. Tipos locales: OutfitKit no emite .d.ts.
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  filterable?: boolean;
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}
interface DataTableAction {
  id: string;
  label: string;
  icon?: string;
  color?: string;
  /** ADITIVO (OutfitKit ≥0.1.14): deshabilita el botón para esa fila (instalado → no re-instalable). */
  disabled?: (row: Row) => boolean;
  /** ADITIVO (OutfitKit ≥0.1.14): spinner en lugar del icono mientras la fila está en curso. */
  loading?: (row: Row) => boolean;
}

// --- Estado ---
const modules = ref<Mod[]>([]);
const MARKETPLACE_COUNTRIES = ['ES', 'FR', 'PT', 'DE', 'IT'] as const;
const catalogCountry = ref<string>(hubSettings.value?.country_code ?? 'ES');
const catalogRegion = computed<string | null>(() =>
  catalogCountry.value === (hubSettings.value?.country_code ?? 'ES')
    ? (hubSettings.value?.region_code ?? null)
    : null,
);
const installedModules = ref<InstalledModule[]>([]);
const loading = ref(true);
const catalogError = ref(false);
let catalogLoadId = 0;
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');
// Duración del toast (ms). 0 = persistente (lo usamos para "Instalando…" mientras corre la
// instalación en background; el resultado lo cierra y muestra el suyo). Por defecto 2.5s.
const toastDuration = ref<number>(2500);

// --- Progreso de instalación por módulo (feedback visual en la card) ---
// Clave = módulo pedido (root); valor = módulo en curso (puede ser una dep anidada) + fase.
// Se alimenta del evento WS `module.install.progress` del runtime (resolving → downloading →
// verifying → installing) y se limpia al terminar (`module.installed` o error HTTP). El Map se
// REEMPLAZA en cada cambio (no se muta) para que los computed que lo leen reaccionen.
interface InstallProgress {
  /** Módulo en curso ≠ root cuando el runtime está instalando una dependencia anidada. */
  dep: string | null;
  phase: string;
}
const installing = ref<Map<string, InstallProgress>>(new Map());

function setProgress(rootId: string, moduleId: string, phase: string): void {
  const next = new Map(installing.value);
  next.set(rootId, { dep: moduleId !== rootId ? moduleId : null, phase });
  installing.value = next;
}

function clearProgress(rootId: string): void {
  if (!installing.value.has(rootId)) return;
  const next = new Map(installing.value);
  next.delete(rootId);
  installing.value = next;
}

// --- Celdas ricas: pill de tinte suave con tokens Ionic (cruzan el shadow de la tabla) ---
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'danger' | 'warning'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

// Etiqueta humana de una fase del pipeline de instalación (contrato WS del runtime).
function phaseLabel(phase: string): string {
  switch (phase) {
    case 'resolving': return t('apps.phaseResolving');
    case 'downloading': return t('apps.phaseDownloading');
    case 'verifying': return t('apps.phaseVerifying');
    case 'installing': return t('apps.phaseInstalling');
    default: return t('apps.stateInstalling');
  }
}

// Celda de estado del catálogo: spinner + fase mientras instala; badge Instalado/Disponible si no.
function stateCell(row: Row): Node {
  if (row.state === 'installing') {
    const prog = row.progress as InstallProgress | null;
    const wrap = document.createElement('span');
    wrap.style.cssText =
      'display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ion-color-primary)';
    const spinner = document.createElement('ion-spinner');
    spinner.setAttribute('name', 'dots');
    spinner.style.cssText = 'width:18px;height:18px';
    const label = document.createElement('span');
    const phase = phaseLabel(prog?.phase ?? '');
    label.textContent = prog?.dep ? t('apps.phaseDependency', { name: prog.dep, phase }) : phase;
    wrap.append(spinner, label);
    return wrap;
  }
  if (row.state === 'installed') return badgeCell(t('apps.stateInstalled'), 'success');
  if (row.state === 'unavailable') return badgeCell(t('apps.stateUnavailable'), 'warning');
  return badgeCell(t('apps.stateAvailable'), 'medium');
}

// El runtime es la FUENTE DE VERDAD local de qué está instalado (`listInstalledModules`). El flag
// `installed` del catálogo Cloud (proxy al SaaS) puede no reflejar aún la instalación de ESTE hub
// (`mark_installed` es best-effort), así que lo cruzamos con la lista local para no mostrar
// "Disponible" (ni el botón Instalar activo) en un módulo ya instalado. (Bug demo 2026-07-12.)
const installedIds = computed<Set<string>>(() => new Set(installedModules.value.map((m) => m.id)));

const filteredModules = computed<Row[]>(() => {
  const base = tab.value === 'paid' ? modules.value.filter((m) => m.paid) : modules.value;
  // Inyecta el estado de instalación en cada fila: cambia la identidad del array cuando `installing`
  // cambia → la tabla (Lit) re-renderiza celdas y predicados de acción con el estado fresco.
  return base.map((m) => {
    const prog = installing.value.get(m.id) ?? null;
    const isInstalled = isModuleInstalled(m.installed, m.id, installedIds.value);
    const state = prog
      ? 'installing'
      : isInstalled
        ? 'installed'
        : m.available
          ? 'available'
          : 'unavailable';
    return {
      ...m,
      state,
      stateLabel:
        state === 'installing'
          ? t('apps.stateInstalling')
          : state === 'installed'
            ? t('apps.stateInstalled')
            : state === 'unavailable'
              ? t('apps.stateUnavailable')
              : t('apps.stateAvailable'),
      progress: prog,
    };
  });
});

// Instalados desde el runtime, como filas de la tabla.
const installedRows = computed<Row[]>(() => installedModules.value as unknown as Row[]);

// --- Columnas + acciones ---
// `computed` para que cabeceras/labels/celdas se recalculen al cambiar de idioma en caliente.
const mineColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apps.colModule') },
  { key: 'version', header: t('apps.colVersion'), format: (r) => `v${String(r.version ?? '')}` },
  {
    key: 'status', header: t('apps.colStatus'), filterable: true, filterType: 'select',
    // Tres estados (ADR-0128): apagado A MANO ≠ ARRASTRADO por la cascada de una dependencia.
    // El arrastrado va en warning: volverá solo cuando su dependencia vuelva.
    render: (r) => badgeCell(
      r.status === 'active' ? t('apps.statusActive')
        : r.status === 'inactive_auto' ? t('apps.statusInactiveAuto')
        : t('apps.statusInactive'),
      r.status === 'active' ? 'success' : r.status === 'inactive_auto' ? 'warning' : 'medium',
    ),
  },
]);
const mineActions = computed<DataTableAction[]>(() => isAdmin.value
  ? [
      { id: 'toggle', label: t('apps.actionToggle'), icon: 'power-outline' },
      { id: 'uninstall', label: t('apps.actionUninstall'), icon: 'trash', color: 'danger' },
    ]
  : []);

const catalogColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apps.colModule') },
  { key: 'version', header: t('apps.colVersion'), format: (r) => String(r.version ?? '—') },
  { key: 'cat', header: t('apps.colCategory'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.cat ?? ''), 'medium') },
  { key: 'coverage', header: t('apps.colCountries'), render: (r) => badgeCell(String(r.coverage ?? ''), 'primary') },
  { key: 'desc', header: t('apps.colDescription') },
  { key: 'price', header: t('apps.colPrice'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.price ?? ''), r.paid ? 'medium' : 'success') },
  // Estado visual (Instalado / Instalando… + fase / Disponible). `stateLabel` (traducido) es el
  // valor crudo de la fila → el filtro select y el buscador ven la misma etiqueta que el usuario.
  { key: 'stateLabel', header: t('apps.colStatus'), align: 'center', filterable: true, filterType: 'select', render: (r) => stateCell(r) },
]);
const catalogActions = computed<DataTableAction[]>(() => isAdmin.value && !config.demo
  ? [
      {
        id: 'install',
        label: t('apps.actionInstall'),
        icon: 'download-outline',
        // Instalado o en curso → botón muerto; en curso → spinner en su lugar (pista de actividad).
        disabled: (row) => row.state !== 'available',
        loading: (row) => row.state === 'installing',
      },
    ]
  : []);

// --- Handlers ---
function onTabChange(ev: Event): void {
  // El watch(tab) sincroniza el hash; aquí solo validamos y asignamos.
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  const next = TABS.find((v) => v === detail.value);
  if (next) tab.value = next;
}

function onCatalogCountryChange(value: string): void {
  const normalized = value.trim().toUpperCase();
  if (!normalized) return;
  // `v-model` actualiza el ref antes de `ionChange`; comparar contra el ref aquí impediría
  // recargar el catálogo precisamente cuando el usuario cambia de país.
  catalogCountry.value = normalized;
  void loadCatalog();
}

function notify(msg: string, color: 'primary' | 'success' | 'danger', duration = 2500): void {
  // Cerrar + reabrir en el siguiente tick: un ion-toast declarativo NO actualiza su mensaje/
  // duración mientras sigue abierto, así que para encadenar toasts (p. ej. "Instalando…" →
  // "instalado") hay que dismiss + re-present.
  toastOpen.value = false;
  void nextTick(() => {
    toastMsg.value = msg;
    toastColor.value = color;
    toastDuration.value = duration;
    toastOpen.value = true;
  });
}

// Cliente del runtime (provide en main.ts; fallback al singleton) para escuchar `module.installed`
// y el progreso por fases `module.install.progress`.
const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;
let unsubProgress: (() => void) | null = null;

// --- Consentimiento de permisos al instalar (modal best-effort) ---
// Si el módulo a instalar DECLARA capabilities, las mostramos antes de instalar y al confirmar las
// concedemos todas (PUT a true). La gestión autoritativa posterior está en Ajustes → Permisos; el
// catálogo Cloud no expone capabilities pre-instalación, así que las leemos del runtime tras
// instalar (mismo contrato `GET /api/modules/{id}/capabilities` que declara el manifest del zip).
const consentOpen = ref(false);
const consentCaps = ref<ModuleCapability[]>([]);
const consentMod = ref<Mod | null>(null);
const planOpen = ref(false);
const plan = ref<InstallPlan | null>(null);
const planMod = ref<Mod | null>(null);

function closeConsent(): void {
  consentOpen.value = false;
  consentMod.value = null;
  consentCaps.value = [];
}

function closePlan(): void {
  planOpen.value = false;
  plan.value = null;
  planMod.value = null;
}

function moduleName(id: string): string {
  return modules.value.find((m) => m.id === id)?.name ?? id;
}

/** Deep-link a la ficha de compra del módulo en el marketplace del SaaS (el Hub NO vende,
 *  ADR-0114): abre el navegador externo y, al volver el foco, re-resuelve el entitlement
 *  y refresca el catálogo para reflejar la compra. */
async function openPurchase(mod: Mod): Promise<void> {
  const url =
    `${config.cloudApiUrl}/dashboard/marketplace/modules/${encodeURIComponent(mod.id)}` +
    `/?hub=${encodeURIComponent(config.hubId)}&utm_source=hub`;
  const recheck = (): void => {
    window.removeEventListener('focus', recheck);
    void resolveEntitlement().then(() => loadCatalog());
  };
  window.addEventListener('focus', recheck);
  try {
    await openExternal(url);
    notify(t('apps.purchaseInBrowser', { name: mod.name }), 'primary');
  } catch {
    window.removeEventListener('focus', recheck);
    notify(t('apps.purchaseOpenError'), 'danger');
  }
}

async function openPlanPurchase(node: InstallPlanNode): Promise<void> {
  const mod = planMod.value;
  if (!mod) return;
  const raw = node.purchase?.purchase_url;
  if (!raw) {
    await openPurchase(mod);
    return;
  }
  const url = new URL(raw, config.cloudApiUrl);
  url.searchParams.set('hub', config.hubId);
  url.searchParams.set('utm_source', 'hub');
  const recheck = (): void => {
    window.removeEventListener('focus', recheck);
    closePlan();
    void resolveEntitlement().then(() => loadCatalog());
  };
  window.addEventListener('focus', recheck);
  try {
    await openExternal(url.toString());
    notify(t('apps.purchaseInBrowser', { name: moduleName(node.module_id) }), 'primary');
  } catch {
    window.removeEventListener('focus', recheck);
    notify(t('apps.purchaseOpenError'), 'danger');
  }
}

/** Tras consentir el plan, conserva el consentimiento de capabilities ya existente. */
async function prepareCapabilitiesOrInstall(mod: Mod): Promise<void> {
  let declared: ModuleCapability[] = [];
  try {
    const caps = await getModuleCapabilities(mod.id);
    declared = caps.capabilities.filter((c) => c.requested);
  } catch {
    declared = [];
  }
  if (declared.length) {
    consentMod.value = mod;
    consentCaps.value = declared;
    consentOpen.value = true;
    return;
  }
  await doInstall(mod);
}

async function confirmPlanInstall(): Promise<void> {
  const mod = planMod.value;
  if (!mod || plan.value?.blocked) return;
  closePlan();
  await prepareCapabilitiesOrInstall(mod);
}

/** Punto de entrada de instalación: decide si pedir consentimiento o instalar directo. */
async function installModule(mod: Mod): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  if (mod.installed) { notify(t('apps.alreadyInstalled', { name: mod.name }), 'primary'); return; }
  // Ya en curso (doble clic o instalación arrancada por otro cliente): no relanzar el request.
  if (installing.value.has(mod.id)) return;
  // El plan Cloud es la autoridad para dependencias Y compra. Se resuelve antes de descargar: si
  // está bloqueado mostramos su CTA; si trae deps pedimos consentimiento informativo.
  setProgress(mod.id, mod.id, 'resolving');
  try {
    const resolved = await previewInstallPlan(mod.id, mod.version ?? 'latest');
    const dependencies = resolved.plan.filter((n) => n.reason === 'dependency');
    if (resolved.blocked || dependencies.length > 0) {
      plan.value = resolved;
      planMod.value = mod;
      planOpen.value = true;
      clearProgress(mod.id);
      return;
    }
  } catch {
    clearProgress(mod.id);
    notify(t('apps.planError', { name: mod.name }), 'danger');
    return;
  }
  clearProgress(mod.id);
  await prepareCapabilitiesOrInstall(mod);
}

/** Confirma el modal: instala y, al terminar, concede todas las capabilities declaradas. */
async function confirmConsentInstall(): Promise<void> {
  const mod = consentMod.value;
  const caps = consentCaps.value;
  if (!mod) return;
  consentOpen.value = false;
  await doInstall(mod, caps);
  closeConsent();
}

/** Instalación real: pide al runtime instalar y (opcional) concede las capabilities pasadas. */
async function doInstall(mod: Mod, grantCaps: ModuleCapability[] = []): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  // La card pasa a "Instalando…" al instante (fase genérica hasta que llegue el primer evento WS
  // `module.install.progress` con la fase real). El toast persistente se mantiene como refuerzo.
  setProgress(mod.id, mod.id, '');
  notify(t('apps.installing', { name: mod.name }), 'primary', 0);
  try {
    // Pide la instalación al runtime: descarga el zip firmado (marketplace Cloud), verifica
    // SHA256 y aplica migraciones. La confirmación llega por el evento WS `module.installed`.
    // Default de versión: 'latest' (el runtime resuelve la última publicada). flag → humano.
    await requestInstall(mod.id, mod.version ?? 'latest');
    // Concede los permisos consentidos (PUT solo admin → el runtime revalida). Best-effort: si falla
    // no rompe la instalación; el usuario puede ajustarlos en Ajustes → Permisos.
    if (grantCaps.length) {
      const grants = Object.fromEntries(grantCaps.map((c) => [c.id, true]));
      await putModuleCapabilities(mod.id, grants).catch(() => null);
    }
    // Optimista: badge "Instalado" ya, sin esperar al refresco del catálogo (loadCatalog llega
    // detrás vía `module.installed` y confirma el estado real del Cloud).
    const row = modules.value.find((m) => m.id === mod.id);
    if (row) row.installed = true;
    notify(t('apps.installSuccess', { name: mod.name }), 'success');
  } catch {
    notify(t('apps.installError', { name: mod.name }), 'danger');
  } finally {
    clearProgress(mod.id);
  }
}

/** Carga los módulos instalados desde el RUNTIME (fuente de verdad local, no el catálogo Cloud). */
async function loadInstalled(): Promise<void> {
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = [];
  }
}

/** Dependientes transitivos ACTIVOS de `id` (los que la cascada apagará al desactivarlo). */
function activeDependentsOf(id: string): InstalledModule[] {
  const out: InstalledModule[] = [];
  const fallen = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const m of installedModules.value) {
      if (fallen.has(m.id) || m.status !== 'active') continue;
      if ((m.depends_on ?? []).some((d) => fallen.has(d))) {
        fallen.add(m.id);
        out.push(m);
        grew = true;
      }
    }
  }
  return out;
}

/** Dependencias transitivas NO activas de `id` (las que la cascada encenderá al activarlo). */
function inactiveDepsOf(id: string): InstalledModule[] {
  const byId = new Map(installedModules.value.map((m) => [m.id, m]));
  const seen = new Set<string>();
  const out: InstalledModule[] = [];
  const walk = (mid: string) => {
    for (const d of byId.get(mid)?.depends_on ?? []) {
      if (seen.has(d)) continue;
      seen.add(d);
      const dep = byId.get(d);
      if (dep && dep.status !== 'active') out.push(dep);
      walk(d);
    }
  };
  walk(id);
  return out;
}

/** Confirmación cuando el toggle va a arrastrar a OTROS módulos (ADR-0128): la cascada nunca
 *  sorprende — se lista lo afectado antes de tocar nada. Sin afectados, ni se pregunta. */
async function confirmCascade(titleKey: string, msgKey: string, m: InstalledModule, affected: InstalledModule[]): Promise<boolean> {
  if (!affected.length) return true;
  const alert = await alertController.create({
    header: t(titleKey, { name: m.name }),
    message: `${t(msgKey, { name: m.name })}\n${affected.map((a) => `· ${a.name}`).join('\n')}`,
    cssClass: 'cascade-alert',
    buttons: [
      { text: t('apps.cascadeCancel'), role: 'cancel' },
      { text: t('apps.cascadeConfirm'), role: 'confirm' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  return role === 'confirm';
}

/** Activa o desactiva un módulo (hot-plug) y refresca la lista + la nav del shell. */
async function toggleModule(m: InstalledModule): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  try {
    if (m.status === 'active') {
      if (!(await confirmCascade('apps.cascadeOffTitle', 'apps.cascadeOffMsg', m, activeDependentsOf(m.id)))) return;
      await deactivateModule(m.id);
      notify(t('apps.deactivated', { name: m.name }), 'primary');
    } else {
      if (!(await confirmCascade('apps.cascadeOnTitle', 'apps.cascadeOnMsg', m, inactiveDepsOf(m.id)))) return;
      await activateModule(m.id);
      notify(t('apps.activated', { name: m.name }), 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch {
    notify(t('apps.toggleError', { name: m.name }), 'danger');
  }
}

/** Desinstala un módulo y refresca la lista + la nav del shell. */
async function removeModule(m: InstalledModule): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  const alert = await alertController.create({
    header: t('apps.uninstallTitle', { name: m.name }),
    message: t('apps.uninstallBody'),
    buttons: [
      { text: t('apps.cascadeCancel'), role: 'cancel' },
      {
        text: t('apps.uninstallConfirm'),
        role: 'confirm',
        cssClass: 'alert-button-danger',
      },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  if (result.role !== 'confirm') return;
  try {
    await uninstallModule(m.id);
    notify(t('apps.uninstalled', { name: m.name }), 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch {
    notify(t('apps.uninstallError', { name: m.name }), 'danger');
  }
}

function toViewModule(m: CloudMarketplaceModule): Mod {
  const amount = m.priceAmount ?? '';
  const price = m.isFree
    ? t('apps.priceFree')
    : m.priceLabel
      || (m.priceInterval === 'month'
        ? t('apps.priceMonthly', { price: amount })
        : m.priceInterval === 'year'
          ? t('apps.priceYearly', { price: amount })
          : amount
            ? t('apps.priceOneTime', { price: amount })
            : t('apps.priceOnRequest'));
  return {
    id: m.id,
    name: m.name,
    desc: m.description,
    price,
    paid: !m.isFree,
    installed: m.installed,
    available: m.available,
    cat: m.category,
    version: m.version,
    countries: m.countries,
    coverage: m.countries.length ? m.countries.join(', ') : t('apps.countryUniversal'),
  };
}

/** Recarga exclusivamente el catálogo real de SaaS. No existe fallback con módulos locales. */
async function loadCatalog(): Promise<void> {
  const loadId = ++catalogLoadId;
  loading.value = true;
  catalogError.value = false;
  try {
    const cloudMods = await cloudMarketplaceModules(catalogCountry.value, catalogRegion.value);
    if (loadId !== catalogLoadId) return;
    modules.value = cloudMods.map(toViewModule);
  } catch {
    if (loadId !== catalogLoadId) return;
    modules.value = [];
    catalogError.value = true;
  } finally {
    if (loadId === catalogLoadId) loading.value = false;
  }
}

// --- Wiring de eventos de las tablas (rowAction es camelCase → addEventListener) ---
const mineTable = ref<HTMLElement | null>(null);
const catalogTable = ref<HTMLElement | null>(null);

function handleMineAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  const m = row as unknown as InstalledModule;
  if (actionId === 'toggle') void toggleModule(m);
  else if (actionId === 'uninstall') void removeModule(m);
}
function handleCatalogAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'install') void installModule(row as unknown as Mod);
}

// Cablea una tabla (labels del locale activo + listener de rowAction). La vista inicial = tarjetas la fija el
// propio WC vía el atributo `default-view="cards"` (robusto, no depende del ref).
function wireTable(el: HTMLElement | null, handler: (e: Event) => void): void {
  if (!el) return;
  (el as HTMLElement & { labels: Record<string, string> }).labels = dataTableLabels(locale.value);
  // Idempotente: quitar antes de añadir evita listeners duplicados si el mismo elemento persiste
  // entre re-cableados (`handler` es una referencia estable, así que removeEventListener casa).
  el.removeEventListener('rowAction', handler);
  el.addEventListener('rowAction', handler);
}

// Cablear en CADA `loading`→false. Las tablas viven detrás de `v-else` (loading): cada vez que
// `loadCatalog` re-togglea `loading` (al instalar, al cambiar de contexto…) el v-if(loading)/v-else
// DESTRUYE y RECREA las tablas, y los elementos NUEVOS no conservan sus listeners. Con el guard
// `once` anterior, tras el primer refresco toggle/uninstall/install quedaban MUERTOS hasta recargar
// la página (bug reportado en el demo, 2026-07-12). `wireTable` es idempotente → re-cablear es seguro.
watch(
  loading,
  (isLoading) => {
    if (isLoading) return;
    void nextTick(() => {
      wireTable(mineTable.value, handleMineAction);
      wireTable(catalogTable.value, handleCatalogAction);
    });
  },
  { immediate: true },
);
watch(locale, () => {
  wireTable(mineTable.value, handleMineAction);
  wireTable(catalogTable.value, handleCatalogAction);
  // La preferencia personal se hidrata después del shell. Recargamos con `Accept-Language`
  // efectivo para no mezclar cabeceras traducidas con metadatos del catálogo en otro idioma.
  void loadCatalog();
});
watch(hubSettings, (settings) => {
  if (!settings || catalogCountry.value === settings.country_code) return;
  catalogCountry.value = settings.country_code;
  void loadCatalog();
});

// --- Fetch + suscripción al evento de instalación al montar ---
onMounted(() => {
  void loadCatalog();
  void loadInstalled();
  // Cuando el runtime termina de instalar un módulo, refrescamos catálogo, instalados y nav.
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    // Cubre también instalaciones iniciadas por OTRO cliente/pestaña (aquí no corre doInstall).
    if (id) clearProgress(id);
    notify(found ? t('apps.moduleInstalledNamed', { name: found.name }) : t('apps.moduleInstalled'), 'success');
    void loadCatalog();
    void loadInstalled();
    void refreshModuleNav();
  });
  // Progreso por fases del pipeline (resolving → downloading → verifying → installing). El frame
  // llega entero (sin `payload`): `root_id` = módulo pedido (clave de la card), `module_id` = el
  // que está procesando de verdad (puede ser una dependencia anidada).
  unsubProgress = client.on('module.install.progress', (payload) => {
    const p = payload as { module_id?: string; root_id?: string; phase?: string } | null;
    const root = p?.root_id ?? p?.module_id;
    if (!root) return;
    setProgress(root, p?.module_id ?? root, p?.phase ?? '');
  });
});

onBeforeUnmount(() => {
  unsubInstalled?.();
  unsubProgress?.();
  mineTable.value?.removeEventListener('rowAction', handleMineAction);
  catalogTable.value?.removeEventListener('rowAction', handleCatalogAction);
});
</script>

<style scoped>
/* Fija el alto al área de ion-content (no min-height): las tablas en modo `fill` resuelven su
   :host{height:100%} contra este contenedor → cabecera + pager fijos y scroll solo en el cuerpo. */
.fill {
  height: 100%;
}

.catalog-country {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.catalog-country ion-select {
  min-width: 7rem;
}
</style>
