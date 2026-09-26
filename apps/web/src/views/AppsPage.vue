<template>
  <AppPage :title="t('nav.apps')">
    <!-- `.fill` fija el alto al área de ion-content para que cabecera/pager de la tabla queden
         fijos y el scroll viva solo en el cuerpo (mismo patrón que EmployeesPage/ModuleView). -->
    <!-- 100% de ancho; el padding lo aporta el `ion-content` de AppPage (un solo ion-padding,
         como todas las vistas). La vista por defecto es GRID (tarjetas) — se fija en onMounted. -->
    <!-- Aquí vivía un `v-if="loading"` con un spinner a pantalla completa que escondía las DOS
         pestañas mientras el CATÁLOGO viajaba al Cloud (hub#1129). Escondía de más y escondía de
         menos: de más, porque «Mis apps» sale del runtime local y ya estaba listo; y de menos,
         porque `loadCatalog()` lo volvía a levantar en cada refresco —al recuperar el foco de la
         ventana, al cambiar de idioma, tras cada instalación—, así que un alt-tab dejaba la
         pantalla en blanco varios segundos. Cada tabla dice ahora su propio estado
         (`installedEmptyMessage` / `catalogEmptyMessage`) y ninguna desaparece para decirlo. -->
    <div class="fill">
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
      <!-- El fallo se DICE, y se dice al lado de la lista, no en su lugar (hub#770). «Añadir apps»
           ya pintaba su error; «Mis apps» se lo tragaba y se quedaba en un vacío que parecía un
           hecho sobre el hub. -->
      <ok-inline-feedback v-if="installedDisplay === 'error' && tab === 'mine'" tone="danger" class="mb-3">
        <span>{{ t('apps.installedLoadError') }}</span>
        <ion-button size="small" fill="clear" @click="loadInstalled">
          {{ t('apps.retryCatalog') }}
        </ion-button>
      </ok-inline-feedback>

      <!-- Un distintivo por sí solo no explica nada (hub#1134): esta es la línea que dice qué
           significa «retirado» — sigue funcionando, sigue actualizándose, ya no se ofrece. Mismo
           patrón que el aviso de plugin cerrado de WordPress: chip en la fila, explicación arriba. -->
      <ok-inline-feedback
        v-if="tab === 'mine' && retiredInstalled.length > 0"
        data-testid="apps-retired-notice"
        tone="warning"
        class="mb-3"
      >
        {{ t('apps.retiredNotice', { apps: retiredAppNames }) }}
      </ok-inline-feedback>

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
        :empty-message="installedEmptyMessage"
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
        :empty-message="catalogEmptyMessage"
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

    <!-- Page notices, anchored above the tab bar (hub#2244). -->
    <ion-toast
      :is-open="toastOpen"
      :message="toastMsg"
      :color="toastColor"
      :duration="toastDuration"
      :buttons="toastButtons"
      position="bottom"
      :position-anchor="TOAST_ANCHOR"
      @did-dismiss="onToastDismissed"
    />
    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer :id="TOAST_ANCHOR" class="ion-no-border">
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
  IonToast,
  IonModal, IonHeader, IonTitle, IonButtons, IonButton, IonContent,
  IonList, IonItem, alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { dataTableLabels } from '../lib/data-table-labels';

const { t, te, locale } = useI18n();
const tableLabels = computed(() => dataTableLabels(locale.value));
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  getModuleCapabilities, putModuleCapabilities, InstallBlockedError, ModuleActionError,
  updateModule, listModuleUpdates, listModuleVersions, modulePublicationStatus,
  type InstalledModule, type ModuleCapability
} from '../lib/runtime';
import { moduleNav, refreshModuleNav } from '../lib/nav';
import { fetchSystemInfo } from '../lib/system';
import { reloadForModuleUpdate } from '../lib/module-loader';
import { canOpenModule, dependentsOf, hidesUpdateAction, moduleRoutePath, toggleIntent } from '../lib/installed-app-actions';
import {
  alsoInstalledNames, catalogActionFor, catalogPrice, catalogRowState, catalogVisibleAction, hubTooOldFor, isModuleInstalled,
  modulesWithUnknownPublication, publicationOf,
  type CatalogBusyAction, type CatalogPrice, type CatalogRowState, type PublicationStatus,
} from '../lib/apps-catalog';
import { listDisplay, type ListLoadState } from '../lib/list-load-state';
import { capabilitiesToConsent } from '../lib/module-capabilities';
import { moduleFailureMessage } from '../lib/module-failure-message';
import {
  defaultVersion, pendingUpdate, shouldPickVersion, updateLabel, updateNeedsNewerHub,
  type ModuleUpdateInfo,
} from '../lib/module-updates';
import { isModuleEntitled, entitlementStatus, resolveEntitlement } from '../lib/entitlement';
import { isAdmin } from '../lib/session';

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
  /** Ids de los permisos que declara el manifest, según el catálogo Cloud (pm#132). */
  capabilities: string[];
  /** Minimum ERPlora version the announced `version` needs, or `null` (saas#2239, hub#2054). */
  minErploraVersion: string | null;
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
  /** ADDITIVE (OutfitKit ≥0.1.84): the action is not painted for that row (list, card or «⋮»). */
  hidden?: (row: Row) => boolean;
}

// --- Estado ---
const modules = ref<Mod[]>([]);
const installedModules = ref<InstalledModule[]>([]);
// Qué sabe la pantalla de esa lista (hub#770). Arranca en `loading`: el primer pintado ocurre antes
// de que ninguna petición haya vuelto, y nacer en `ready` es decir «no tienes apps» en cada carga.
const installedState = ref<ListLoadState>('loading');
// Qué versión ofrece hoy el marketplace por módulo instalado (hub#516). Se pide BAJO DEMANDA al
// abrir la pantalla, no en bucle: el resolutor vive en el runtime (el mismo del arranque), así que
// esto es solo lo que hay que enseñar. Vacío = no se ofrece nada (incluido «no se pudo preguntar»).
const moduleUpdates = ref<ModuleUpdateInfo[]>([]);
/**
 * Qué sabe la pantalla de la última petición del CATÁLOGO — gemelo de `installedState` (hub#770).
 *
 * Nace en `loading` por el mismo motivo: el primer pintado ocurre antes de que ninguna respuesta
 * haya vuelto, y nacer en `ready` es decir «no hay apps» en cada carga.
 *
 * Y sustituye al `loading` a pantalla completa que había (hub#1129): aquel no era un estado de la
 * LISTA sino de la PÁGINA, así que cada refresco del catálogo —al recuperar el foco de la ventana
 * (`recheckEntitlement`), al cambiar de idioma, tras cada instalación— desmontaba las dos tablas.
 * Medido en el hub de producción `qa-pm149` el 2026-08-25: UN solo evento `focus` dejaba la
 * pantalla sin tablas ~3 s. Eso es hub#1129 («no pinta nunca») y la mitad de hub#1122 («Mis apps»
 * sin apps mientras el runtime tiene una).
 */
const catalogState = ref<ListLoadState>('loading');
const catalogError = computed(() => catalogState.value === 'error');
let catalogLoadId = 0;
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');
// Duración del toast (ms). 0 = persistente (lo usamos para "Instalando…" mientras corre la
// instalación en background; el resultado lo cierra y muestra el suyo). Por defecto 2.5s.
const toastDuration = ref<number>(2500);
// Toast actions. Empty = informative toast. Used to go to Settings → Permissions when a module
// comes in without its permissions (pm#132), and to retry/close a failed install (hub#2244).
type ToastButton = { text: string; role?: 'cancel'; handler?: () => void };
const toastButtons = ref<ToastButton[]>([]);
// hub#2244 — every notice of this page sits ABOVE the Apps tab bar (the footer below), not at the
// window edge under it: on a desktop the error rose over the tabs, bottom edge 10 px from the frame.
const TOAST_ANCHOR = 'apps-footer';
// hub#2244 — `didDismiss` of a notice the page REPLACED arrives after its successor is already open
// (Ionic finishes the leave animation first). Counted here so that late event does not close the
// new notice: it closed the install error ~0.3 s after it rose.
let replacedToasts = 0;

function onToastDismissed(): void {
  if (replacedToasts > 0) {
    replacedToasts -= 1;
    return;
  }
  toastOpen.value = false;
}

/** Shows a notice, replacing the one on screen (closed first, so the new one is re-presented). */
function showToast(msg: string, color: 'primary' | 'success' | 'danger', duration: number, buttons: ToastButton[]): void {
  // A declarative ion-toast does NOT update its message/duration while open, so chaining notices
  // («Installing…» → «installed») is dismiss + re-present on the next tick.
  if (toastOpen.value) replacedToasts += 1;
  toastOpen.value = false;
  void nextTick(() => {
    toastMsg.value = msg;
    toastColor.value = color;
    toastDuration.value = duration;
    toastButtons.value = buttons;
    toastOpen.value = true;
  });
}

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

// Módulos con una actualización en curso (hub#516). Se reemplaza el Set en cada cambio (no se muta)
// para que los computed que lo leen reaccionen, igual que el mapa de progreso de instalación.
const updatingIds = ref<Set<string>>(new Set());

function setUpdating(id: string, busy: boolean): void {
  const next = new Set(updatingIds.value);
  if (busy) next.add(id);
  else next.delete(id);
  updatingIds.value = next;
}

// --- Celdas ricas: pill de tinte suave con tokens Ionic (cruzan el shadow de la tabla) ---
/**
 * Nombre del módulo + el distintivo de su estado de publicación (hub#1134).
 *
 * El distintivo va PEGADO AL NOMBRE, que es donde lo pone el mercado (el «deprecated» de Shopify,
 * el de Odoo): es un hecho sobre la app, no sobre si está encendida — que es lo que dice la columna
 * de estado, y una app retirada puede estar perfectamente activa.
 *
 * Sólo `retired` se pinta. `unlisted` se sigue instalando por referencia directa (ADR-0380), así
 * que en un hub que ya lo tiene no hay nada de lo que avisar.
 */
function nameCell(name: string, publication: PublicationStatus | null): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
  const label = document.createElement('span');
  label.textContent = name;
  wrap.append(label);
  if (publication === 'retired') wrap.append(badgeCell(t('apps.publicationRetired'), 'warning'));
  return wrap;
}

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
  if (row.state === 'updatable') return badgeCell(String(row.stateLabel ?? ''), 'primary');
  if (row.state === 'installed') return badgeCell(t('apps.stateInstalled'), 'success');
  if (row.state === 'unavailable') return badgeCell(t('apps.stateUnavailable'), 'warning');
  if (row.state === 'needs_newer_hub') return badgeCell(String(row.stateLabel ?? ''), 'warning');
  return badgeCell(t('apps.stateAvailable'), 'medium');
}

// El runtime es la FUENTE DE VERDAD local de qué está instalado (`listInstalledModules`). El flag
// `installed` del catálogo Cloud (proxy al SaaS) puede no reflejar aún la instalación de ESTE hub
// (`mark_installed` es best-effort), así que lo cruzamos con la lista local para no mostrar
// "Disponible" (ni el botón Instalar activo) en un módulo ya instalado. (Bug demo 2026-07-12.)
const installedIds = computed<Set<string>>(() => new Set(installedModules.value.map((m) => m.id)));

// The version this hub runs (`/api/system`, e.g. `v1.4.0`), to compare with each app's floor before
// anyone presses «Install» (hub#2054). `null` until it answers — or when it cannot — and then no card
// is blocked: the runtime still refuses a too-new app at install time (hub#1620).
const hubVersion = ref<string | null>(null);
async function loadHubVersion(): Promise<void> {
  const info = await fetchSystemInfo();
  if (!info) console.warn('[apps] could not read the hub version: the catalog cannot warn about app floors');
  hubVersion.value = info?.hubVersion ?? null;
}

// Los ids que el CATÁLOGO trae hoy. Estar ahí ya es la respuesta: la lista del marketplace sólo
// sirve `publication_status='listed'` (lo filtra el SaaS en su acción `list`), así que un módulo
// que vuelve en el catálogo está `listed` por construcción y preguntar por él otra vez es coste
// puro.
const catalogIds = computed<Set<string>>(() => new Set(modules.value.map((m) => m.id)));

/**
 * Qué OFRECE hoy el marketplace de cada módulo instalado (ADR-0380, hub#1134).
 *
 * Sólo guarda lo que hubo que preguntar —lo que el catálogo NO listó—, y `null` cuando no se pudo
 * preguntar: «no lo sé» no es «retirado» ni «al día», y ninguno de los dos se pinta por el otro.
 */
const publicationStatuses = ref<Map<string, PublicationStatus | null>>(new Map());

/**
 * Pregunta por los pocos módulos instalados que el catálogo no listó (hub#1134).
 *
 * 🔴 El modo de fallo que cierra es el *closed plugin* de WordPress.org que cita ADR-0380: el
 * módulo se retira, el hub se queda con él —a propósito: `retired` cierra la OFERTA, nunca el
 * suministro— y la pantalla lo pinta como si estuviera al día, porque no hay actualización que
 * ofrecer. Nadie se entera nunca. `online_booking`, `cart_checkout`, `payments` e `invoice_series`
 * son ese caso en producción hoy.
 *
 * **Cuesta CERO llamadas en un hub sano**: el catálogo responde por todo lo que lista, y sólo lo
 * que falta de él llega hasta aquí. Es lo que permite que esto cuelgue del mismo refresco que ya
 * dispara `focus` sin convertirlo en 25 peticiones al Cloud.
 *
 * Con el catálogo caído no se pregunta NADA: sin catálogo no hay nada listado, y «no listado»
 * pasaría a significar «pregunta por todas tus apps» para concluir lo que ya se sabía.
 */
async function loadPublicationStatuses(): Promise<void> {
  if (catalogState.value !== 'ready') return;
  const pending = modulesWithUnknownPublication(
    installedModules.value.map((m) => m.id),
    catalogIds.value,
    publicationStatuses.value,
  );
  if (pending.length === 0) return;
  const answers = await Promise.all(
    pending.map(async (id) => {
      const status = await modulePublicationStatus(id).catch((error: unknown) => {
        // Un fallo se VE (regla de entrega): la fila se queda sin distintivo, y el motivo queda en
        // la consola en vez de desaparecer.
        console.warn(`[apps] no se pudo leer el estado de publicación de ${id}`, error);
        return null;
      });
      return [id, status] as const;
    }),
  );
  const next = new Map(publicationStatuses.value);
  for (const [id, status] of answers) next.set(id, status);
  publicationStatuses.value = next;
}

// Se resuelve cuando las DOS mitades están: el catálogo dice qué se sigue ofreciendo y el runtime
// dice qué tiene este hub. Reemplazar el mapa (no mutarlo) es lo que hace reaccionar a las filas.
watch(
  [catalogState, installedModules, modules],
  () => {
    void loadPublicationStatuses();
  },
  { immediate: true },
);

/** Los módulos instalados que el marketplace ya no ofrece — los que llevan aviso y distintivo. */
const retiredInstalled = computed<InstalledModule[]>(() =>
  installedModules.value.filter(
    (m) => publicationOf(m.id, catalogIds.value, publicationStatuses.value) === 'retired',
  ),
);
const retiredAppNames = computed(() => retiredInstalled.value.map((m) => m.name).join(', '));

const filteredModules = computed<Row[]>(() => {
  const base = tab.value === 'paid' ? modules.value.filter((m) => m.paid) : modules.value;
  // Inyecta el estado de instalación en cada fila: cambia la identidad del array cuando `installing`
  // cambia → la tabla (Lit) re-renderiza celdas y predicados de acción con el estado fresco.
  return base.map((m) => {
    const prog = installing.value.get(m.id) ?? null;
    const isInstalled = isModuleInstalled(m.installed, m.id, installedIds.value);
    // Instalado PERO con versión nueva: estado propio (hub#516). Antes todo lo instalado caía en
    // «Instalado» con el botón muerto, así que el arreglo publicado no tenía por dónde entrar.
    const update = isInstalled ? pendingUpdate(m.id, moduleUpdates.value) : null;
    // Un SOLO sitio decide instalar-o-actualizar (hub#795). Antes se decidía aquí para pintar el
    // badge y OTRA VEZ dentro del click, leyendo el flag del Cloud a secas: los dos discrepaban
    // justo cuando importa (`mark_installed` va por detrás), y la fila entraba por instalar algo
    // que tocaba actualizar.
    const state = catalogRowState({
      cloudInstalled: m.installed,
      id: m.id,
      localInstalledIds: installedIds.value,
      hasUpdate: update !== null,
      available: m.available,
      busy: prog !== null || updatingIds.value.has(m.id),
      needsNewerHub: hubTooOldFor(m.minErploraVersion, hubVersion.value),
      updateNeedsNewerHub: updateNeedsNewerHub(update, hubVersion.value),
    });
    return {
      ...m,
      state,
      // Which operation is running, so its button keeps the spinner and the other one stays out.
      busyAction: updatingIds.value.has(m.id) ? 'update' : prog !== null ? 'install' : null,
      stateLabel:
        state === 'installing'
          ? t('apps.stateInstalling')
          : state === 'updatable'
            ? t('apps.stateUpdatable', { version: update?.latest ?? '' })
            : state === 'installed'
              ? t('apps.stateInstalled')
              : state === 'unavailable'
                ? t('apps.stateUnavailable')
                : state === 'needs_newer_hub'
                  ? update
                    ? t('apps.stateUpdateNeedsNewerHub', { version: update.latest, floor: update.latest_min_erplora_version ?? '' })
                    : t('apps.stateNeedsNewerHub', { version: m.minErploraVersion ?? '' })
                  : t('apps.stateAvailable'),
      progress: prog,
    };
  });
});

/**
 * Qué mira la pestaña «Mis apps»: sus apps, la espera, el fallo o un vacío de verdad (hub#770).
 *
 * Las tres frases son excluyentes y ninguna se dice por la otra. La tabla solo sabe pintar UN texto
 * cuando no hay filas (`empty-message`), así que es ese texto el que cambia — «Aún no tienes apps»
 * queda para la única situación en la que es cierto: una respuesta que volvió y venía vacía.
 */
const installedDisplay = computed(() => listDisplay(installedState.value, installedModules.value.length));
const installedEmptyMessage = computed(() =>
  installedDisplay.value === 'loading'
    ? t('apps.loadingInstalled')
    : installedDisplay.value === 'error'
      ? t('apps.installedLoadError')
      : t('apps.emptyInstalled'),
);

/**
 * Lo mismo para «Añadir apps» (hub#1129): esperar, fallar y no haber nada son TRES frases.
 *
 * La pestaña del catálogo solo sabía decir «no hay apps que coincidan con tu búsqueda», y la decía
 * también mientras cargaba y —al lado del aviso de error— cuando el Cloud no había contestado. Es
 * la misma mentira que hub#770 arregló en «Mis apps», en la superficie de al lado.
 */
const catalogDisplay = computed(() => listDisplay(catalogState.value, filteredModules.value.length));
const catalogEmptyMessage = computed(() =>
  catalogDisplay.value === 'loading'
    ? t('apps.loadingCatalog')
    : catalogDisplay.value === 'error'
      ? t('apps.catalogLoadError')
      : t('apps.emptyCatalog'),
);

// Instalados desde el runtime, como filas de la tabla. Se les cuelga la actualización pendiente
// (hub#516) para que la celda de versión y el predicado de la acción la vean sin recalcularla.
const installedRows = computed<Row[]>(() =>
  installedModules.value.map((m) => {
    const update = pendingUpdate(m.id, moduleUpdates.value);
    return {
      ...m,
      update,
      // hub#2082: the pending version needs a newer ERPlora — no «Update», the row says why instead.
      updateNeedsNewerHub: updateNeedsNewerHub(update, hubVersion.value),
      updating: updatingIds.value.has(m.id),
      // ADR-0380 (hub#1134): si el marketplace lo sigue ofreciendo. `null` = no se pudo preguntar.
      publicationStatus: publicationOf(m.id, catalogIds.value, publicationStatuses.value),
    };
  }) as unknown as Row[],
);

// --- Columnas + acciones ---
// `computed` para que cabeceras/labels/celdas se recalculen al cambiar de idioma en caliente.
const mineColumns = computed<DataTableColumn[]>(() => [
  {
    key: 'name',
    header: t('apps.colModule'),
    // `searchKeys: ['name']` sigue leyendo el valor CRUDO de la fila, así que el distintivo no
    // entra en la búsqueda: se pinta, no se indexa.
    render: (r) =>
      nameCell(String(r.name ?? ''), (r.publicationStatus as PublicationStatus | null) ?? null),
  },
  {
    key: 'version',
    header: t('apps.colVersion'),
    // DE → A cuando hay actualización (`1.1.1 → 1.1.2`), y solo lo que corre cuando no la hay
    // (ADR-0269 §3.5). «Inventario 1.1.2» no dice nada; «1.1.1 → 1.1.2» sí.
    format: (r) => {
      const update = (r.update as ModuleUpdateInfo | null) ?? null;
      // hub#2082: an update this hub is too old for is not «1.0.0 → 2.0.0»: it names what it needs.
      if (update && r.updateNeedsNewerHub === true) {
        return `${String(r.version ?? '')} · ${t('apps.stateUpdateNeedsNewerHub', {
          version: update.latest, floor: update.latest_min_erplora_version ?? '',
        })}`;
      }
      return updateLabel(String(r.version ?? ''), update);
    },
  },
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
const mineActions = computed<DataTableAction[]>(() => {
  if (!isAdmin.value) return [];
  // Read here, in the computed BODY, not inside the `disabled` closure: that is what makes this
  // computed depend on the nav, so a module that was just switched on produces a NEW actions array
  // and okdt re-renders its buttons. Read lazily inside the closure, the list would be right and
  // the screen would still show the old one until something else happened to change a row.
  const nav = moduleNav.value;
  return [
      {
        // FIRST, and on purpose (hub#773): what a person opens this card for is the app itself.
        // Until now the row ended in a switch and a bin — two ways to take the app away and none
        // to get into it — so the only route in was the launcher grid in the topbar.
        //
        // Icon-only like every other action (regla de Ioan 2026-07-16 sobre ADR-0133): the `label`
        // is what okdt puts in `aria-label` and `title`, never visible text.
        id: 'open',
        label: t('apps.actionOpen'),
        icon: 'open-outline',
        color: 'primary',
        // A module that paints nothing, or one that is switched off, has no screen to open — and a
        // button that lands on an empty page is worse than no button. `canOpenModule` decides, and
        // the button is left out rather than greyed out (hub#2015).
        hidden: (row) => !canOpenModule(row as unknown as InstalledModule, nav),
      },
      {
        // El botón «Actualizar» de ADR-0269 §3.5: **por módulo**, para ADELANTAR. Que el sistema
        // acabe haciéndolo solo al arrancar no quita que se pueda pedir ahora.
        id: 'update',
        label: t('apps.actionUpdate'),
        icon: 'arrow-up-circle-outline',
        // No new version, no button (hub#2015). While one runs it stays, with the spinner instead
        // of the icon, and a second press cannot start it again.
        hidden: (row) => hidesUpdateAction(row),
        disabled: (row) => row.updating === true,
        loading: (row) => row.updating === true,
      },
      {
        // hub#2082: in place of «Update» when the new version needs a newer ERPlora. The hub updates
        // itself (ADR-0269), so this leads to where its version and what changed are shown.
        id: 'see_hub_updates',
        label: t('apps.actionSeeHubUpdates'),
        icon: 'information-circle-outline',
        hidden: (row) => row.updateNeedsNewerHub !== true || row.updating === true,
      },
      { id: 'toggle', label: t('apps.actionToggle'), icon: 'power-outline' },
      { id: 'uninstall', label: t('apps.actionUninstall'), icon: 'trash', color: 'danger' },
  ];
});

const catalogColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apps.colModule') },
  { key: 'version', header: t('apps.colVersion'), format: (r) => String(r.version ?? '—') },
  { key: 'cat', header: t('apps.colCategory'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.cat ?? ''), 'medium') },
  { key: 'desc', header: t('apps.colDescription') },
  { key: 'price', header: t('apps.colPrice'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.price ?? ''), r.paid ? 'medium' : 'success') },
  // Estado visual (Instalado / Instalando… + fase / Disponible). `stateLabel` (traducido) es el
  // valor crudo de la fila → el filtro select y el buscador ven la misma etiqueta que el usuario.
  { key: 'stateLabel', header: t('apps.colStatus'), align: 'center', filterable: true, filterType: 'select', render: (r) => stateCell(r) },
]);
// DOS acciones, no una con dos significados (hub#795). Antes había un solo botón «Instalar» que
// servía también para actualizar: la columna de estado decía «Update to 1.2.22» y el nombre
// accesible del botón de al lado seguía siendo «Install». Con actions solo-icono el `label` ES lo
// único que se lee (aria-label + tooltip), así que a un teclado y a un lector de pantalla se les
// estaba diciendo el verbo equivocado de la operación que iban a lanzar.
//
// Each one is painted only where its operation applies — the other is left out, not greyed out
// (hub#2019, same as «My apps» in hub#2015). `catalogVisibleAction` decides, and while a row is busy it
// keeps the running one, disabled and with its spinner. Never both on the same row.
const catalogActions = computed<DataTableAction[]>(() => isAdmin.value && !config.demo
  ? [
      {
        id: 'install',
        label: t('apps.actionInstall'),
        icon: 'download-outline',
        hidden: (row) => catalogVisibleAction(row.state as CatalogRowState, row.busyAction as CatalogBusyAction) !== 'install',
        disabled: (row) => row.state === 'installing',
        loading: (row) => row.state === 'installing',
      },
      {
        id: 'update',
        label: t('apps.actionUpdate'),
        icon: 'arrow-up-circle-outline',
        hidden: (row) => catalogVisibleAction(row.state as CatalogRowState, row.busyAction as CatalogBusyAction) !== 'update',
        disabled: (row) => row.state === 'installing',
        loading: (row) => row.state === 'installing',
      },
      {
        // hub#2054: in place of «Install» on an app this hub is too old for. The hub updates itself
        // (ADR-0269), so this leads to where its version and what changed are shown.
        id: 'see_hub_updates',
        label: t('apps.actionSeeHubUpdates'),
        icon: 'information-circle-outline',
        hidden: (row) => catalogVisibleAction(row.state as CatalogRowState, row.busyAction as CatalogBusyAction) !== 'see_hub_updates',
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

function notify(msg: string, color: 'primary' | 'success' | 'danger', duration = 2500): void {
  showToast(msg, color, duration, []);
}

/** «Close» for a sticky notice: a notice that never expires needs a way out. */
function closeButton(): ToastButton {
  return { text: t('apps.noticeClose'), role: 'cancel' };
}

/**
 * El módulo entró pero sus permisos NO se concedieron (pm#132).
 *
 * Es la red de seguridad: sin ella el siguiente paso del usuario es abrir el módulo y leer «no
 * tengo permiso» sin saber que la solución está a dos pantallas. Sticky (0) para que se pueda
 * LEER, y con el botón que lleva allí — describir la ruta con palabras ya lo hacía el cartel del
 * módulo y no bastaba.
 */
function notifyGrantFailed(name: string): void {
  showToast(t('apps.installedButNoPermissions', { name }), 'danger', 0, [
    { text: t('apps.goToPermissions'), handler: () => { void router.push('/settings#permissions'); } },
  ]);
}

// Cliente del runtime (provide en main.ts; fallback al singleton) para escuchar `module.installed`
// y el progreso por fases `module.install.progress`.
const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;
let unsubProgress: (() => void) | null = null;
// hub#1317: activate/deactivate/uninstall (unlike install) emitted nothing of their own —
// another tab/device of the same hub stayed on this list exactly as it was until it reloaded.
let unsubActivated: (() => void) | null = null;
let unsubDeactivated: (() => void) | null = null;
let unsubUninstalled: (() => void) | null = null;

// --- Consentimiento de permisos al instalar (modal best-effort) ---
// Si el módulo a instalar DECLARA capabilities, las mostramos antes de instalar y al confirmar las
// concedemos todas (PUT a true). La gestión autoritativa posterior está en Ajustes → Permisos; el
// catálogo Cloud no expone capabilities pre-instalación, así que las leemos del runtime tras
// instalar (mismo contrato `GET /api/modules/{id}/capabilities` que declara el manifest del zip).
const consentOpen = ref(false);
const consentCaps = ref<ModuleCapability[]>([]);
const consentMod = ref<Mod | null>(null);
// La versión ya elegida (hub#675): se decide ANTES del consentimiento y viaja hasta la instalación,
// para que los permisos que se enseñan sean los de la versión que acaba entrando.
const consentVersion = ref('latest');

function closeConsent(): void {
  consentOpen.value = false;
  consentMod.value = null;
  consentCaps.value = [];
  consentVersion.value = 'latest';
}

/**
 * El módulo necesita suscripción y este hub no la tiene: se DICE, no se lleva a comprar.
 *
 * Aquí había un `openPurchase()` que abría la ficha del módulo en el marketplace del SaaS —donde
 * está el checkout— con su recheck-on-focus. Retirado en hub#479: es el caso de manual de steering,
 * un control de la app que empuja al pago de fuera, y es causa de rechazo en Play y en Microsoft
 * Store. El recheck no se pierde: `resolveEntitlement()` sigue corriendo al recuperar el foco desde
 * `onMounted`, así que quien contrate en erplora.com vuelve y el módulo ya se instala.
 */
function sayItNeedsASubscription(mod: Mod): void {
  notify(t('apps.needsSubscription', { name: mod.name }), 'primary');
}

/**
 * Qué versión instalar o actualizar (hub#675). Devuelve `null` si el usuario canceló.
 *
 * **Solo pregunta si hay algo que elegir.** Con una sola opción —el caso común: un módulo con una
 * versión nueva— sigue siendo un clic; el desplegable aparece cuando hay varias de verdad.
 *
 * La lista la decide el runtime, no esta pantalla: llega ya sin versiones en cuarentena, sin
 * ninguna anterior a la instalada y vacía si soporte tiene el módulo clavado. Aquí no se filtra
 * nada, porque un filtro propio sería una segunda política — y la que manda es la del runtime.
 *
 * Si el Cloud no contestó, la lista viene vacía y se pide `latest`: el runtime resuelve por su
 * cuenta, igual que antes de que existiera el desplegable. Sin lista se instala; no se bloquea.
 */
async function chooseVersion(moduleId: string, name: string): Promise<string | null> {
  const { versions } = await listModuleVersions(moduleId).catch(() => ({ versions: [] as string[] }));
  if (!shouldPickVersion(versions)) return defaultVersion(versions);

  // Radios en un alert: es el desplegable de Ionic para elegir de una lista (lo mismo que abre un
  // `ion-select` en modo alert), y ya es el patrón de esta pantalla para confirmar (desinstalar,
  // cascadas). La última va la PRIMERA y marcada: elegir otra es deliberado, no un descuido.
  const alert = await alertController.create({
    header: t('apps.versionPickTitle'),
    subHeader: name,
    message: t('apps.versionPickBody'),
    inputs: versions.map((version, index) => ({
      type: 'radio' as const,
      label: index === 0 ? t('apps.versionLatest', { version }) : version,
      value: version,
      checked: index === 0,
    })),
    buttons: [
      { text: t('apps.cascadeCancel'), role: 'cancel' },
      { text: t('apps.versionPickConfirm'), role: 'confirm' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  if (result.role !== 'confirm') return null;
  // `data.values` es la opción marcada. Si el overlay no la trae (dismiss raro), no se inventa:
  // se cae a la última, que es justo lo que estaba seleccionado.
  return (result.data as { values?: string } | undefined)?.values ?? defaultVersion(versions);
}

/**
 * Actualiza un módulo instalado (hub#516) a la versión elegida, o a la que el runtime resuelva.
 *
 * El runtime pone las reglas: nunca una versión en cuarentena, nunca hacia atrás, y el pin de
 * soporte gana. Si el intento falla, el módulo se queda con la versión que ya tenía **funcionando**
 * —eso lo garantiza el runtime, no esta pantalla—, así que aquí solo hay que decirlo.
 */
async function updateInstalledModule(id: string, name: string): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  if (updatingIds.value.has(id)) return;
  // Antes de tocar nada: si hay varias versiones, que elija. Cancelar aquí no deja rastro.
  const version = await chooseVersion(id, name);
  if (version === null) return;
  setUpdating(id, true);
  notify(t('apps.updating', { name }), 'primary', 0);
  try {
    const result = await updateModule(id, version);
    if (!result.updated) {
      notify(t('apps.updateUpToDate', { name }), 'primary');
      return;
    }
    // hub#935 — el módulo ya está actualizado en el hub, pero ESTA página no puede mostrarlo: el
    // custom element del bundle anterior ya está registrado y un tag solo se define una vez por
    // documento. Sin recargar, la lista y el manifest dirían la versión nueva y la pantalla del
    // módulo seguiría ejecutando la vieja — el fallo mudo que motivó la issue. Se avisa (toast
    // sticky) y se recarga; refrescar el menú aquí no serviría de nada.
    notify(t('apps.updateSuccessReloading', { name, from: result.from, to: result.to }), 'success', 0);
    reloadForModuleUpdate();
  } catch (e) {
    if (e instanceof InstallBlockedError) {
      // ADR-0060: a la versión nueva le faltan módulos de pago sin contratar. No se ha tocado nada
      // y NO se ha cobrado nada; el módulo sigue en la versión anterior. Sticky para poder leerlo.
      notify(
        t('apps.updateBlocked', { name, missing: e.blockedOn.join(', ') }),
        'danger',
        0,
      );
    } else {
      // What the RUNTIME said, and only if it said anything (hub#673). What matters about the
      // message is still that the module was NOT left half-done — the runtime guarantees that,
      // not the sentence.
      notify(moduleFailureMessage(e, t('apps.updateError', { name }), { t, te }), 'danger');
    }
  } finally {
    setUpdating(id, false);
    await loadModuleUpdates();
  }
}

/** Punto de entrada de instalación: decide si pedir consentimiento o instalar directo. */
async function installModule(mod: Mod): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  // Ya está aquí: la RUTA de actualizar es la suya propia (hub#795) y esta se limita a decirlo. La
  // verdad la pone el runtime cruzado con el catálogo (`isModuleInstalled`), nunca el flag del Cloud
  // a secas: `mark_installed` es best-effort y va por detrás justo después de instalar, que es
  // cuando este camino se recorre.
  if (isModuleInstalled(mod.installed, mod.id, installedIds.value)) {
    if (pendingUpdate(mod.id, moduleUpdates.value)) {
      await updateInstalledModule(mod.id, mod.name);
    } else {
      notify(t('apps.alreadyInstalled', { name: mod.name }), 'primary');
    }
    return;
  }
  // Ya en curso (doble clic o instalación arrancada por otro cliente): no relanzar el request.
  if (installing.value.has(mod.id)) return;
  // Gate de suscripción (ADR-0114): un módulo de pago SIN entitlement de ESTE hub no se intenta
  // instalar (el download/ del SaaS lo denegaría con un error genérico) — se avisa y ya; contratar
  // es cosa de erplora.com (hub#479). El freemium (premium con capa gratis) SÍ viene en el token de
  // entitlement, así que sigue instalándose sin contratar nada (ADR-0032) — que es el caso de los
  // 24 módulos de hoy. Solo gateamos con el entitlement RESUELTO (permisivo mientras 'unknown',
  // igual que el resto del shell).
  if (mod.paid && entitlementStatus.value === 'unlocked' && !isModuleEntitled(mod.id)) {
    sayItNeedsASubscription(mod);
    return;
  }
  // Qué versión, ANTES del consentimiento: los permisos que se conceden son los de la versión que
  // se va a instalar, así que preguntar por ellos y luego cambiar de versión sería enseñar unos y
  // conceder otros.
  const version = await chooseVersion(mod.id, mod.name);
  if (version === null) return;
  // Los permisos que declara el módulo, ANTES de instalar (pm#132). Dos fuentes, por orden:
  //   1. el RUNTIME, que es la autoridad — pero solo conoce un módulo que YA estuvo instalado;
  //   2. el CATÁLOGO Cloud, que expone los ids del manifest (`capabilities`) y es lo único que hay
  //      en una PRIMERA instalación, que es justo cuando esto hace falta.
  // Antes solo existía (1): en un alta nueva la lista salía vacía, no había modal, y el módulo
  // entraba con todo DENEGADO — el dueño aterrizaba en un «no tengo permiso» de algo que acababa
  // de instalar él. `null` = ni siquiera se pudo preguntar (módulo desconocido → error).
  let fromRuntime: ModuleCapability[] | null = null;
  try {
    fromRuntime = (await getModuleCapabilities(mod.id)).capabilities;
  } catch {
    fromRuntime = null;
  }
  const declared = capabilitiesToConsent(fromRuntime, mod.capabilities);
  if (declared.length) {
    consentMod.value = mod;
    consentVersion.value = version;
    consentCaps.value = declared;
    consentOpen.value = true;
    return;
  }
  await doInstall(mod, version);
}

/** Confirma el modal: instala y, al terminar, concede todas las capabilities declaradas. */
async function confirmConsentInstall(): Promise<void> {
  const mod = consentMod.value;
  const caps = consentCaps.value;
  const version = consentVersion.value;
  if (!mod) return;
  consentOpen.value = false;
  await doInstall(mod, version, caps);
  closeConsent();
}

/** Instalación real: pide al runtime instalar y (opcional) concede las capabilities pasadas. */
async function doInstall(mod: Mod, version: string, grantCaps: ModuleCapability[] = []): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  // La card pasa a "Instalando…" al instante (fase genérica hasta que llegue el primer evento WS
  // `module.install.progress` con la fase real). El toast persistente se mantiene como refuerzo.
  setProgress(mod.id, mod.id, '');
  notify(t('apps.installing', { name: mod.name }), 'primary', 0);
  try {
    // Pide la instalación al runtime: descarga el zip firmado (marketplace Cloud), verifica
    // SHA256 y aplica migraciones. La confirmación llega por el evento WS `module.installed`.
    // `version` viene de `chooseVersion`: la elegida, o `latest` cuando no había nada que elegir
    // (el runtime la resuelve). Ya NO se usa la del catálogo Cloud: el catálogo dice qué versión
    // publica el marketplace, no cuál puede instalar ESTE hub.
    const result = await requestInstall(mod.id, version);
    // Concede los permisos consentidos (PUT solo admin → el runtime revalida). Best-effort: si
    // falla no rompe la instalación — pero YA NO SE CALLA. Un fallo aquí deja el módulo instalado
    // y sin permisos, que es exactamente el aterrizaje en «no tengo permiso» de pm#132; el toast
    // dice dónde se arregla y lleva un botón que va allí de un clic, en vez de describir la ruta.
    let grantFailed = false;
    if (grantCaps.length) {
      const grants = Object.fromEntries(grantCaps.map((c) => [c.id, true]));
      grantFailed = await putModuleCapabilities(mod.id, grants).then(() => false, () => true);
    }
    // Optimista: badge "Instalado" ya, sin esperar al refresco del catálogo (loadCatalog llega
    // detrás vía `module.installed` y confirma el estado real del Cloud).
    const row = modules.value.find((m) => m.id === mod.id);
    if (row) row.installed = true;
    if (grantFailed) {
      notifyGrantFailed(mod.name);
    } else if (result.also_installed.length) {
      // hub#1130: the install-plan closure (ADR-0060) dragged dependencies in — the owner asked
      // for ONE app and got several. Naming them in the SAME confirmation (never a second modal,
      // market: Odoo/Shopify) is the reverse of hub#1101's `409 has_dependents`, which already
      // names what an uninstall would break.
      const names = alsoInstalledNames(result.also_installed, modules.value).join(', ');
      notify(t('apps.installSuccessWithDependencies', { name: mod.name, names }), 'success', 0);
    } else {
      notify(t('apps.installSuccess', { name: mod.name }), 'success');
    }
  } catch (e) {
    // ADR-0060: «bloqueado» NO es una avería — al plan le faltan módulos de pago sin contratar y
    // no se ha instalado nada. Decirlo y nombrarlos es la diferencia entre que el usuario sepa qué
    // contratar y que vea un «no se pudo» opaco. La compra es suya: aquí nunca se cobra.
    if (e instanceof InstallBlockedError) {
      // Sticky (0): the user has to be able to READ what is missing, not watch it go by. No
      // «Retry»: nothing changes until they subscribe (hub#2244).
      showToast(
        t('apps.installBlocked', { name: mod.name, missing: e.blockedOn.join(', ') }),
        'danger',
        0,
        [closeButton()],
      );
    } else {
      // This is where the second discard of hub#673 lived. `e` carried the runtime's sentence —no
      // machine token, bad signature, missing version, unresolved dependency, SHA-256 mismatch,
      // migration blown up— and this `else` threw it away to print the same line every time. With
      // six causes indistinguishable, the fleet-wide install breakage of 08-09 (saas#1352) was
      // invisible from the till.
      // hub#2244: sticky, with «Retry» — the same app, version and granted permissions (the consent
      // was already given) — because the failure can be transient and 2.5 s was not enough to read it.
      showToast(moduleFailureMessage(e, t('apps.installError', { name: mod.name }), { t, te }), 'danger', 0, [
        {
          text: t('apps.installRetry'),
          handler: () => {
            if (!installing.value.has(mod.id)) void doInstall(mod, version, grantCaps);
          },
        },
        closeButton(),
      ]);
    }
  } finally {
    clearProgress(mod.id);
  }
}

/**
 * Carga los módulos instalados desde el RUNTIME (fuente de verdad local, no el catálogo Cloud).
 *
 * El `catch` ponía `[]`, y eso convertía «no he podido preguntar» en «este hub no tiene apps»
 * (hub#770) — una afirmación sobre el hub que nadie había comprobado. Con una sesión desplazada por
 * un segundo dispositivo (plan Free), «Mis apps» decía «Aún no tienes apps» mientras el TPV de la
 * pestaña de al lado seguía vendiendo. Ahora la lista SOBREVIVE al fallo y lo que cambia es lo que
 * la pantalla sabe de ella.
 */
async function loadInstalled(): Promise<void> {
  try {
    installedModules.value = await listInstalledModules();
    installedState.value = 'ready';
  } catch {
    installedState.value = 'error';
  }
}

/**
 * Pregunta al runtime qué versión ofrece hoy el marketplace por módulo instalado (hub#516).
 *
 * Bajo demanda, al abrir la pantalla y tras instalar/actualizar. Un fallo deja la lista vacía: sin
 * respuesta **no se ofrece nada** — «no lo sé» no se pinta como «hay novedad».
 */
async function loadModuleUpdates(): Promise<void> {
  try {
    moduleUpdates.value = await listModuleUpdates();
  } catch {
    moduleUpdates.value = [];
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

/**
 * Preguntar ANTES de mover el interruptor, diciendo hacia dónde va (hub#773).
 *
 * Antes solo se preguntaba cuando la cascada de ADR-0128 arrastraba a otros módulos; en el caso
 * normal —el 90 %— el icono de encendido apagaba el TPV sin una palabra, y el propio icono no dice
 * nada: es el mismo dibujo para encender que para apagar. Ahora la pregunta es siempre, y su título
 * NOMBRA la app y el estado al que va («Desactivar Ventas»), que es la información que faltaba.
 *
 * La cascada no desaparece: cuando hay arrastrados, se listan dentro de la misma pregunta. Un solo
 * diálogo, no dos.
 */
async function confirmToggle(m: InstalledModule, affected: InstalledModule[]): Promise<boolean> {
  const off = toggleIntent(m.status) === 'deactivate';
  const lines = [t(off ? 'apps.toggleOffBody' : 'apps.toggleOnBody', { name: m.name })];
  if (affected.length) {
    lines.push(t(off ? 'apps.cascadeOffMsg' : 'apps.cascadeOnMsg', { name: m.name }));
    lines.push(affected.map((a) => `· ${a.name}`).join('\n'));
  }
  const alert = await alertController.create({
    header: t(off ? 'apps.toggleOffTitle' : 'apps.toggleOnTitle', { name: m.name }),
    message: lines.join('\n'),
    cssClass: 'cascade-alert',
    buttons: [
      { text: t('apps.cascadeCancel'), role: 'cancel' },
      { text: t(off ? 'apps.toggleOffConfirm' : 'apps.toggleOnConfirm'), role: 'confirm' },
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
    if (toggleIntent(m.status) === 'deactivate') {
      if (!(await confirmToggle(m, activeDependentsOf(m.id)))) return;
      await deactivateModule(m.id);
      notify(t('apps.deactivated', { name: m.name }), 'primary');
    } else {
      if (!(await confirmToggle(m, inactiveDepsOf(m.id)))) return;
      await activateModule(m.id);
      notify(t('apps.activated', { name: m.name }), 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch (e) {
    notify(moduleFailureMessage(e, t('apps.toggleError', { name: m.name }), { t, te }), 'danger');
  }
}

/** Desinstala un módulo y refresca la lista + la nav del shell. */
async function removeModule(m: InstalledModule): Promise<void> {
  if (!isAdmin.value) { notify(t('apps.adminOnly'), 'danger'); return; }
  // Qué se lleva por delante, ANTES de llevárselo (hub#773). El diálogo decía qué se CONSERVA
  // («los datos y archivos se guardan») y callaba lo único irreversible del momento: las otras apps
  // que dependen de esta se quedan sin ella. Se nombran, transitivamente y aunque estén apagadas —
  // desinstalar no es desactivar: el paquete se va, así que una dependiente apagada ya no se podrá
  // volver a encender.
  const breaks = dependentsOf(m.id, installedModules.value);
  const body = breaks.length
    ? `${t('apps.uninstallBreaks', { name: m.name })}\n${breaks.map((a) => `· ${a.name}`).join('\n')}\n\n${t('apps.uninstallBody')}`
    : t('apps.uninstallBody');
  const alert = await alertController.create({
    header: t('apps.uninstallTitle', { name: m.name }),
    message: body,
    cssClass: 'cascade-alert',
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
    // hub#1101: el runtime rechaza por su cuenta si algo depende de esta app, y hace bien — esa
    // guarda existe para el que NUNCA vio esta lista (un script, el asistente, un flujo, un
    // `curl`). Aquí sí se vio y sí se confirmó, así que la pantalla contesta esa pregunta. Sin
    // dependientes no se manda nada: si la lista se hubiera quedado vieja, el rechazo tiene que
    // llegar en lugar de colarse.
    await uninstallModule(m.id, { force: breaks.length > 0 });
    notify(t('apps.uninstalled', { name: m.name }), 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch (e) {
    // Ese caso — la lista con la que se pintó el diálogo era vieja — llega con su código estable y
    // sus dependientes. La frase del runtime va en inglés (es código), así que se traduce y se
    // nombran las apps QUE MANDÓ ÉL, que son las de verdad.
    if (e instanceof ModuleActionError && e.code === 'has_dependents') {
      const names = (e.dependents ?? []).join(', ');
      notify(t('apps.uninstallBlocked', { name: m.name, apps: names }), 'danger');
      await loadInstalled();
      return;
    }
    notify(moduleFailureMessage(e, t('apps.uninstallError', { name: m.name }), { t, te }), 'danger');
  }
}

/** Words for a card's price line; the unit never goes out without its amount (hub#2072). */
function priceText(p: CatalogPrice): string {
  switch (p.kind) {
    case 'label':
      return p.label;
    case 'free':
      return t('apps.priceFree');
    case 'included_in_plan':
      return t('apps.priceIncludedInPlan');
    case 'monthly':
      return t('apps.priceMonthly', { price: p.amount });
    case 'yearly':
      return t('apps.priceYearly', { price: p.amount });
    case 'one_time':
      return t('apps.priceOneTime', { price: p.amount });
    case 'on_request':
      return t('apps.priceOnRequest');
  }
}

function toViewModule(m: CloudMarketplaceModule): Mod {
  const price = priceText(catalogPrice(m));
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
    capabilities: m.capabilities,
    minErploraVersion: m.minErploraVersion,
  };
}

/**
 * Recarga exclusivamente el catálogo real de SaaS. No existe fallback con módulos locales.
 *
 * NO toca la pantalla mientras trabaja (hub#1129): lo que hay pintado se queda, y lo que cambia es
 * `catalogState`. Y un fallo NO vacía el catálogo (misma regla que `loadInstalled`, hub#770): las
 * filas que ya estaban sobreviven y el fallo se DICE en el aviso de arriba, al lado de la lista y
 * no en su lugar. Un `focus` con la red mala borraba las 25 apps de la pantalla.
 */
async function loadCatalog(): Promise<void> {
  const loadId = ++catalogLoadId;
  // Solo se anuncia la espera cuando no hay nada mejor que enseñar; con un catálogo ya en pantalla,
  // volver a decir «cargando» sería pisar datos buenos con un mensaje.
  if (catalogState.value !== 'ready') catalogState.value = 'loading';
  try {
    const cloudMods = await cloudMarketplaceModules();
    if (loadId !== catalogLoadId) return;
    modules.value = cloudMods.map(toViewModule);
    catalogState.value = 'ready';
  } catch {
    if (loadId !== catalogLoadId) return;
    catalogState.value = 'error';
  }
}

// --- Wiring de eventos de las tablas (rowAction es camelCase → addEventListener) ---
const mineTable = ref<HTMLElement | null>(null);
const catalogTable = ref<HTMLElement | null>(null);

function handleMineAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  const m = row as unknown as InstalledModule;
  // Open the app (hub#773). `canOpenModule` already left the button out when there is no screen,
  // but it is asked again here: the event can come from a keyboard over a state that just changed,
  // and navigating to `/m/<id>` of a switched-off module leaves the person on an empty screen.
  if (actionId === 'open') {
    if (canOpenModule(m, moduleNav.value)) void router.push(moduleRoutePath(m.id));
    return;
  }
  if (actionId === 'toggle') void toggleModule(m);
  else if (actionId === 'uninstall') void removeModule(m);
  else if (actionId === 'update') void updateInstalledModule(m.id, m.name);
  else if (actionId === 'see_hub_updates') void router.push('/system#updates');
}
function handleCatalogAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  const mod = row as unknown as Mod;
  // Por el ESTADO de la fila, que ya cruzó el Cloud con el runtime — no por el flag del Cloud
  // (hub#795). Se vuelve a comprobar aquí y no solo en `disabled`: el evento puede llegar de un
  // teclado sobre una fila que acaba de cambiar de estado.
  const offered = catalogActionFor(row.state as CatalogRowState);
  if (actionId === 'update' && offered === 'update') void updateInstalledModule(mod.id, mod.name);
  else if (actionId === 'install' && offered === 'install') void installModule(mod);
  else if (actionId === 'see_hub_updates' && offered === 'see_hub_updates') void router.push('/system#updates');
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

// Cablear cada vez que APAREZCA un elemento de tabla nuevo. Un elemento nuevo no conserva los
// listeners del anterior: con el guard `once` original, tras el primer refresco toggle/uninstall/
// install quedaban MUERTOS hasta recargar la página (bug del demo, 2026-07-12). Esto colgaba de
// `loading`→false porque el `v-if` destruía y recreaba las tablas en CADA carga; retirado ese
// `v-if` (hub#1129) se vigila el ELEMENTO en sí — que es lo que de verdad importaba, y lo que
// sigue valiendo el día que vuelva a haber un `v-if` de por medio.
// `wireTable` es idempotente → re-cablear es seguro.
watch(
  [mineTable, catalogTable],
  () => {
    wireTable(mineTable.value, handleMineAction);
    wireTable(catalogTable.value, handleCatalogAction);
  },
  { immediate: true, flush: 'post' },
);
watch(locale, () => {
  wireTable(mineTable.value, handleMineAction);
  wireTable(catalogTable.value, handleCatalogAction);
  // La preferencia personal se hidrata después del shell. Recargamos con `Accept-Language`
  // efectivo para no mezclar cabeceras traducidas con metadatos del catálogo en otro idioma.
  void loadCatalog();
  // And the INSTALLED ones (hub#781). Their names are localized by the runtime and travel baked
  // into the answer (`/api/modules?locale=`, ADR-0055): without asking again, «My apps» kept the
  // ones from the first request — the chrome in English and the apps as `Clientes`, `Impuestos`,
  // `Inventario`, the language the shell booted with before the profile arrived.
  void loadInstalled();
});

// --- Fetch + suscripción al evento de instalación al montar ---
/**
 * Re-resuelve el entitlement (y recarga el catálogo) al recuperar el foco.
 *
 * Colgaba de `openPurchase()` y se desenganchaba tras el primer foco. Al retirar ese botón
 * (hub#479) pasa a ser permanente mientras la vista vive: quien contrate en erplora.com —en el
 * navegador, en el móvil o en otro equipo— vuelve aquí y el módulo ya se puede instalar, sin F5.
 */
const recheckEntitlement = (): void => void resolveEntitlement().then(() => loadCatalog());

onMounted(() => {
  window.addEventListener('focus', recheckEntitlement);
  void loadCatalog();
  void loadInstalled();
  void loadHubVersion();
  // Qué módulos publican pantalla, para el botón «Abrir» (hub#773). El shell ya la carga al entrar,
  // pero esta pantalla no puede depender de eso: entrar por `/apps` directamente (deep-link, F5)
  // dejaría todos los «Abrir» en gris hasta que algo más la refrescase.
  void refreshModuleNav();
  // Bajo demanda, al abrir la pantalla (hub#516): una llamada por módulo instalado, y solo cuando
  // alguien está mirando. La vía desatendida la cubre el arranque, que resuelve la última versión.
  void loadModuleUpdates();
  // Cuando el runtime termina de instalar un módulo, refrescamos catálogo, instalados y nav.
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    // Cubre también instalaciones iniciadas por OTRO cliente/pestaña (aquí no corre doInstall).
    if (id) clearProgress(id);
    notify(found ? t('apps.moduleInstalledNamed', { name: found.name }) : t('apps.moduleInstalled'), 'success');
    void loadCatalog();
    void loadInstalled();
    void loadModuleUpdates();
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
  // hub#1317 (review of hub#1311): activate/deactivate/uninstall emitted NOTHING over `/ws` —
  // the same hole hub#631 closed only for `module.installed`. No toast here on purpose: the tab
  // that DID the action already tells itself (`toggleModule`/`removeModule`, further up this
  // file); this subscription is for the ones that did NOT.
  unsubActivated = client.on('module.activated', () => {
    void loadCatalog();
    void loadInstalled();
    void loadModuleUpdates();
    void refreshModuleNav();
  });
  unsubDeactivated = client.on('module.deactivated', () => {
    void loadCatalog();
    void loadInstalled();
    void loadModuleUpdates();
    void refreshModuleNav();
  });
  unsubUninstalled = client.on('module.uninstalled', () => {
    void loadCatalog();
    void loadInstalled();
    void loadModuleUpdates();
    void refreshModuleNav();
  });
});

onBeforeUnmount(() => {
  window.removeEventListener('focus', recheckEntitlement);
  unsubInstalled?.();
  unsubProgress?.();
  unsubActivated?.();
  unsubDeactivated?.();
  unsubUninstalled?.();
  mineTable.value?.removeEventListener('rowAction', handleMineAction);
  catalogTable.value?.removeEventListener('rowAction', handleCatalogAction);
});
</script>

<style scoped>
/* Fija el alto al área de ion-content (no min-height): las tablas en modo `fill` resuelven su
   alto contra este contenedor → cabecera + pager fijos y scroll solo en el cuerpo.
   Columna flex porque encima de la tabla puede haber avisos (`ok-inline-feedback`): con la tabla
   a `height:100%` a secas, el aviso SUMA su alto y empuja el pager fuera de la pantalla — que es
   justo lo que pasa en el estado de error, donde el aviso siempre está. */
.fill {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: var(--ok-work-surface-min);
}
/* Gana a la regla de documento `ok-data-table[fill] { height: 100% }` (theme/polish.css) por
   especificidad: aquí el alto lo reparte el flex, no un 100% del contenedor entero. */
.fill > ok-data-table[fill] {
  flex: 1 1 auto;
  height: auto;
  min-height: 0;
}
</style>
