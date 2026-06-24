<template>
  <AppPage :title="t('nav.marketplace')">
    <div v-if="loading" class="flex justify-center py-10">
      <ion-spinner name="dots" />
    </div>

    <!-- `.fill` fija el alto al área de ion-content para que cabecera/pager de la tabla queden
         fijos y el scroll viva solo en el cuerpo (mismo patrón que EmployeesPage/ModuleView). -->
    <!-- 100% de ancho; el padding lo aporta el `ion-content` de AppPage (un solo ion-padding,
         como todas las vistas). La vista por defecto es GRID (tarjetas) — se fija en onMounted. -->
    <div v-else class="fill">
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
        :search-placeholder="t('marketplace.searchInstalled')"
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
        :search-placeholder="t('marketplace.searchCatalog')"
        page-size="10"
        column-picker
      ></ok-data-table>
    </div>

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
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="mine">
            <HubIcon name="cube-outline" />
            <ion-label>{{ t('marketplace.tabMine') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="all">
            <HubIcon name="storefront-outline" />
            <ion-label>{{ t('marketplace.tabCatalog') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="paid">
            <HubIcon name="wallet-outline" />
            <ion-label>{{ t('marketplace.tabPaid') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel,
  IonSpinner, IonToast
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';

const { t } = useI18n();
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  type InstalledModule
} from '../lib/runtime';
import { refreshModuleNav } from '../lib/nav';

// --- Tipos ---
interface Mod {
  id: string;
  name: string;
  desc: string;
  price: string;
  installed: boolean;
  cat: string;
  /** Versión a instalar; si el Cloud no la expone usamos 'latest' en el request-install. */
  version?: string;
}

type MarketplaceTab = 'mine' | 'all' | 'paid';

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
interface DataTableAction { id: string; label: string; icon?: string; color?: string }

// --- Datos demo (solo si config.demo y el Cloud no responde) ---
const MODULES_DEMO: Mod[] = [
  { id: 'inventory', name: 'Inventario', desc: 'Productos, stock y movimientos', price: 'Gratis', installed: true, cat: 'Operación' },
  { id: 'pos', name: 'TPV / POS', desc: 'Punto de venta y caja', price: 'Gratis', installed: true, cat: 'Ventas' },
  { id: 'customers', name: 'Clientes (CRM)', desc: 'Fichas, grupos y actividad', price: 'Gratis', installed: true, cat: 'Ventas' },
  { id: 'invoice', name: 'Facturación', desc: 'Facturas y rectificativas', price: '9 €/mes', installed: false, cat: 'Finanzas' },
  { id: 'couriers', name: 'Envíos', desc: 'Integración con transportistas', price: '12 €/mes', installed: false, cat: 'Logística' },
  { id: 'appointments', name: 'Reservas', desc: 'Agenda y citas online', price: '7 €/mes', installed: false, cat: 'Operación' },
  { id: 'messaging', name: 'Mensajería', desc: 'WhatsApp y email unificados', price: '15 €/mes', installed: false, cat: 'Comunicación' },
  { id: 'analytics', name: 'Analítica', desc: 'Cuadros de mando e informes', price: '9 €/mes', installed: false, cat: 'BI' },
];

// --- Estado ---
const tab = ref<MarketplaceTab>('mine');
const modules = ref<Mod[]>([]);
const installedModules = ref<InstalledModule[]>([]);
const loading = ref(true);
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');
// Duración del toast (ms). 0 = persistente (lo usamos para "Instalando…" mientras corre la
// instalación en background; el resultado lo cierra y muestra el suyo). Por defecto 2.5s.
const toastDuration = ref<number>(2500);

// --- Celdas ricas: pill de tinte suave con tokens Ionic (cruzan el shadow de la tabla) ---
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'danger'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

const filteredModules = computed<Row[]>(() => {
  if (tab.value === 'paid') return modules.value.filter((m) => m.price !== 'Gratis');
  return modules.value;
});

// Instalados desde el runtime, como filas de la tabla.
const installedRows = computed<Row[]>(() => installedModules.value as unknown as Row[]);

// --- Columnas + acciones ---
// `computed` para que cabeceras/labels/celdas se recalculen al cambiar de idioma en caliente.
const mineColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('marketplace.colModule') },
  { key: 'version', header: t('marketplace.colVersion'), format: (r) => `v${String(r.version ?? '')}` },
  {
    key: 'status', header: t('marketplace.colStatus'), filterable: true, filterType: 'select',
    render: (r) => badgeCell(r.status === 'active' ? t('marketplace.statusActive') : t('marketplace.statusInactive'), r.status === 'active' ? 'success' : 'medium'),
  },
]);
const mineActions = computed<DataTableAction[]>(() => [
  { id: 'toggle', label: t('marketplace.actionToggle'), icon: 'power-outline' },
  { id: 'uninstall', label: t('marketplace.actionUninstall'), icon: 'trash', color: 'danger' },
]);

const catalogColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('marketplace.colModule') },
  { key: 'cat', header: t('marketplace.colCategory'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.cat ?? ''), 'medium') },
  { key: 'desc', header: t('marketplace.colDescription') },
  { key: 'price', header: t('marketplace.colPrice'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.price ?? ''), r.price === 'Gratis' ? 'success' : 'medium') },
  { key: 'installed', header: t('marketplace.colInstalled'), align: 'center', filterable: true, filterType: 'select', format: (r) => (r.installed ? t('marketplace.yes') : t('marketplace.no')) },
]);
const catalogActions = computed<DataTableAction[]>(() => [
  { id: 'install', label: t('marketplace.actionInstall'), icon: 'download-outline' },
]);

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'mine' || detail.value === 'all' || detail.value === 'paid') {
    tab.value = detail.value;
  }
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

// Cliente del runtime (provide en main.ts; fallback al singleton) para escuchar `module.installed`.
const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;

async function installModule(mod: Mod): Promise<void> {
  if (mod.installed) { notify(t('marketplace.alreadyInstalled', { name: mod.name }), 'primary'); return; }
  // Persistente (duration 0) mientras corre la instalación en background (descarga+verifica+migra);
  // el resultado (éxito/fallo o el evento WS `module.installed`) lo cierra y muestra el suyo.
  // Además la barra de progreso de la topbar se enciende vía requestInstall (inFlight del shell).
  notify(t('marketplace.installing', { name: mod.name }), 'primary', 0);
  try {
    // Pide la instalación al runtime: descarga el zip firmado (marketplace Cloud), verifica
    // SHA256 y aplica migraciones. La confirmación llega por el evento WS `module.installed`.
    // Default de versión: 'latest' (el runtime resuelve la última publicada). flag → humano.
    await requestInstall(mod.id, mod.version ?? 'latest');
    notify(t('marketplace.installSuccess', { name: mod.name }), 'success');
  } catch {
    notify(t('marketplace.installError', { name: mod.name }), 'danger');
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

/** Activa o desactiva un módulo (hot-plug) y refresca la lista + la nav del shell. */
async function toggleModule(m: InstalledModule): Promise<void> {
  try {
    if (m.status === 'active') {
      await deactivateModule(m.id);
      notify(t('marketplace.deactivated', { name: m.name }), 'primary');
    } else {
      await activateModule(m.id);
      notify(t('marketplace.activated', { name: m.name }), 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch {
    notify(t('marketplace.toggleError', { name: m.name }), 'danger');
  }
}

/** Desinstala un módulo y refresca la lista + la nav del shell. */
async function removeModule(m: InstalledModule): Promise<void> {
  try {
    await uninstallModule(m.id);
    notify(t('marketplace.uninstalled', { name: m.name }), 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch {
    notify(t('marketplace.uninstallError', { name: m.name }), 'danger');
  }
}

function toViewModule(m: CloudMarketplaceModule): Mod {
  return {
    id: m.id,
    name: m.name,
    desc: m.description,
    price: m.priceLabel || t('marketplace.priceOnRequest'),
    installed: m.installed,
    cat: m.category,
  };
}

/** Recarga el catálogo (estados de instalado) desde el Cloud, con fallback demo. */
async function loadCatalog(): Promise<void> {
  loading.value = true;
  try {
    const cloudMods = await cloudMarketplaceModules();
    modules.value = cloudMods.map(toViewModule);
  } catch {
    modules.value = config.demo ? MODULES_DEMO : [];
  } finally {
    loading.value = false;
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

// Cablea una tabla (labels en ES + listener de rowAction). La vista inicial = tarjetas la fija el
// propio WC vía el atributo `default-view="cards"` (robusto, no depende del ref).
function wireTable(el: HTMLElement | null, handler: (e: Event) => void): void {
  if (!el) return;
  (el as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
  el.addEventListener('rowAction', handler);
}

// Las tablas viven detrás de `v-else` (loading): al ejecutarse onMounted, loading=true y los refs
// aún son null, así que cablear ahí no hacía nada (labels en inglés + acciones muertas). Cableamos
// cuando loading pasa a false y las tablas ya existen, una sola vez (loadCatalog re-togglea loading
// en cada refresco; el flag evita duplicar listeners).
let tablesWired = false;
watch(
  loading,
  (isLoading) => {
    if (isLoading || tablesWired) return;
    void nextTick(() => {
      if (!mineTable.value && !catalogTable.value) return;
      wireTable(mineTable.value, handleMineAction);
      wireTable(catalogTable.value, handleCatalogAction);
      tablesWired = true;
    });
  },
  { immediate: true },
);

// --- Fetch + suscripción al evento de instalación al montar ---
onMounted(() => {
  void loadCatalog();
  void loadInstalled();
  // Cuando el runtime termina de instalar un módulo, refrescamos catálogo, instalados y nav.
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    notify(found ? t('marketplace.moduleInstalledNamed', { name: found.name }) : t('marketplace.moduleInstalled'), 'success');
    void loadCatalog();
    void loadInstalled();
    void refreshModuleNav();
  });
});

onBeforeUnmount(() => {
  unsubInstalled?.();
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
</style>
