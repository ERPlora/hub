<!--
  MarketplacePage — tienda de módulos del Hub.

  TODO va dentro de `ok-data-table`: vista de TARJETAS por defecto (cada fila se pinta como
  `ok-product-card`, la misma tarjeta del marketplace público del Cloud), con selección múltiple,
  búsqueda, filtros por columna (categoría = multiselect, precio) y paginación. Dos pestañas:
    · Mis módulos → instalados en el RUNTIME (activos + inactivos), acciones activar/desactivar/
      desinstalar; filtro de estado por la columna Estado.
    · Catálogo    → todos los módulos del Cloud; acción Instalar; filtro por categoría y precio.
-->
<template>
  <AppPage :title="t('nav.marketplace')">
    <div class="fill">
      <div v-if="loading" class="grid place-items-center h-full">
        <ion-spinner name="dots" />
      </div>

      <ok-data-table
        v-show="!loading && tab === 'mine'"
        ref="mineTable"
        fill
        selectable
        :views="['cards', 'table']"
        :columns="installedColumns"
        :rows="installedRows"
        :renderCard="renderInstalledCard"
        :searchKeys="['name', 'id']"
        :actions="installedActions"
        search-placeholder="Buscar módulo…"
        page-size="12"
        empty-message="No tienes módulos instalados"
      ></ok-data-table>

      <ok-data-table
        v-show="!loading && tab === 'catalog'"
        ref="catalogTable"
        fill
        selectable
        :views="['cards', 'table']"
        :columns="catalogColumns"
        :rows="catalogRows"
        :renderCard="renderCatalogCard"
        :searchKeys="['name', 'desc', 'cat']"
        :actions="catalogActions"
        search-placeholder="Buscar módulo…"
        page-size="12"
        empty-message="Sin módulos"
      ></ok-data-table>
    </div>

    <ion-toast
      :is-open="toastOpen"
      :message="toastMsg"
      :color="toastColor"
      :duration="2500"
      @did-dismiss="toastOpen = false"
    />

    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <ion-segment :value="tab" @ion-change="onTabChange">
            <ion-segment-button value="mine">
              <HubIcon name="cube-outline" />
              <ion-label>Mis módulos</ion-label>
            </ion-segment-button>
            <ion-segment-button value="catalog">
              <HubIcon name="storefront-outline" />
              <ion-label>Catálogo</ion-label>
            </ion-segment-button>
          </ion-segment>
        </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar, IonFooter, IonSegment, IonSegmentButton, IonLabel, IonSpinner, IonToast,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { resolveIcon } from '../lib/icons';
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  type InstalledModule,
} from '../lib/runtime';
import { refreshModuleNav } from '../lib/nav';

const { t } = useI18n();

// ── Tipos locales de ok-data-table (OutfitKit no emite .d.ts consumibles aquí) ──────────────────
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string; header: string; align?: 'left' | 'right' | 'center';
  filterable?: boolean; filterType?: 'text' | 'select' | 'multiselect' | 'number' | 'date' | 'range' | 'daterange';
  format?: (row: Row) => string; render?: (row: Row) => Node | string;
}
interface DataTableAction { id: string; label: string; icon?: string; color?: string }

interface Mod { id: string; name: string; desc: string; price: string; installed: boolean; cat: string; version?: string }
type MarketplaceTab = 'mine' | 'catalog';

// --- Datos demo (fallback sin Cloud) ---
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

// --- Helpers ---
function iconForModule(id: string, category: string): string {
  const key = `${id} ${category}`.toLowerCase();
  if (key.includes('pos') || key.includes('tpv') || key.includes('venta')) return 'cart-outline';
  if (key.includes('client') || key.includes('crm')) return 'people-outline';
  if (key.includes('fact') || key.includes('invoice')) return 'document-text-outline';
  if (key.includes('env') || key.includes('courier') || key.includes('log')) return 'send-outline';
  if (key.includes('reserva') || key.includes('agenda') || key.includes('appointment') || key.includes('booking')) return 'calendar-outline';
  if (key.includes('message') || key.includes('whatsapp') || key.includes('comun')) return 'chatbubble-outline';
  if (key.includes('analytic') || key.includes('bi')) return 'bar-chart-outline';
  return 'cube-outline';
}
function toViewModule(m: CloudMarketplaceModule): Mod {
  return { id: m.id, name: m.name, desc: m.description, price: m.priceLabel || 'Consultar', installed: m.installed, cat: m.category };
}
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'warning' | 'danger'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

// ── renderCard: cada fila → ok-product-card (la tarjeta del marketplace del Cloud). El icono va por
//    el slot (SVG horneado offline; el attr `icon` de ok-product-card tira de api.iconify = red/CSP). ─
function productCardEl(opts: { id: string; name: string; cat: string; desc?: string; price?: string; badge?: string }): HTMLElement {
  const c = document.createElement('ok-product-card');
  if (opts.cat) c.setAttribute('category', opts.cat);
  c.setAttribute('name', opts.name);
  if (opts.badge) c.setAttribute('badge', opts.badge);
  if (opts.price) c.setAttribute('price', opts.price);
  // Transparente + sin borde y a sangre: la propia `rcard` de la tabla aporta el fondo/selección.
  c.style.cssText = '--border:transparent;--surface:transparent;margin:-0.6rem -0.85rem';
  const ic = document.createElement('ion-icon');
  ic.setAttribute('slot', 'icon');
  (ic as HTMLElement & { icon?: string }).icon = resolveIcon(iconForModule(opts.id, opts.cat));
  ic.style.fontSize = '1.2rem';
  c.appendChild(ic);
  if (opts.desc) c.appendChild(document.createTextNode(opts.desc));
  return c;
}
function renderCatalogCard(row: Row): Node {
  const m = row as unknown as Mod;
  const badge = m.installed ? 'Instalado' : m.price !== 'Gratis' ? 'Premium' : undefined;
  return productCardEl({ id: m.id, name: m.name, cat: m.cat, desc: m.desc, price: m.price, badge });
}
function renderInstalledCard(row: Row): Node {
  const m = row as unknown as InstalledModule;
  return productCardEl({
    id: m.id, name: m.name, cat: 'Instalado',
    price: `v${m.version}`, badge: m.status === 'active' ? 'Activo' : 'Inactivo',
  });
}

// --- Columnas / acciones (vista tabla + búsqueda/filtros/CSV) ---
const installedColumns: DataTableColumn[] = [
  { key: 'name', header: 'Módulo' },
  { key: 'version', header: 'Versión', format: (r) => `v${String(r.version ?? '—')}` },
  {
    key: 'status', header: 'Estado', filterable: true, filterType: 'select',
    render: (r) => badgeCell(r.status === 'active' ? 'Activo' : 'Inactivo', r.status === 'active' ? 'success' : 'medium'),
  },
];
const installedActions: DataTableAction[] = [
  { id: 'toggle', label: 'Activar / Desactivar', icon: 'power' },
  { id: 'uninstall', label: 'Desinstalar', icon: 'trash', color: 'danger' },
];
const installedRows = computed<Row[]>(() => installedModules.value as unknown as Row[]);

const catalogColumns: DataTableColumn[] = [
  { key: 'name', header: 'Módulo' },
  { key: 'cat', header: 'Categoría', filterable: true, filterType: 'multiselect', render: (r) => badgeCell(String(r.cat), 'primary') },
  { key: 'desc', header: 'Descripción', format: (r) => String(r.desc ?? '') },
  { key: 'price', header: 'Precio', filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.price), r.price === 'Gratis' ? 'success' : 'medium') },
  { key: 'installed', header: 'Instalado', align: 'center', render: (r) => (r.installed ? badgeCell('Sí', 'success') : document.createTextNode('—')) },
];
const catalogActions: DataTableAction[] = [
  { id: 'install', label: 'Instalar', icon: 'download-outline' },
];
const catalogRows = computed<Row[]>(() => modules.value as unknown as Row[]);

// --- Handlers ---
function onTabChange(ev: Event): void {
  const v = (ev as CustomEvent<{ value: string }>).detail.value;
  if (v === 'mine' || v === 'catalog') tab.value = v;
}
function notify(msg: string, color: 'primary' | 'success' | 'danger'): void {
  toastMsg.value = msg;
  toastColor.value = color;
  toastOpen.value = true;
}

const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;

async function installModule(mod: Mod): Promise<void> {
  if (mod.installed) { notify(`${mod.name} ya está instalado.`, 'primary'); return; }
  notify(`Instalando ${mod.name}…`, 'primary');
  try {
    await requestInstall(mod.id, mod.version ?? 'latest');
  } catch {
    notify(`No se pudo iniciar la instalación de ${mod.name}.`, 'danger');
  }
}
async function toggleModule(m: InstalledModule): Promise<void> {
  try {
    if (m.status === 'active') {
      await deactivateModule(m.id);
      notify(`${m.name} desactivado.`, 'primary');
    } else {
      await activateModule(m.id);
      notify(`${m.name} activado.`, 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch {
    notify(`No se pudo cambiar el estado de ${m.name}.`, 'danger');
  }
}
async function removeModule(m: InstalledModule): Promise<void> {
  try {
    await uninstallModule(m.id);
    notify(`${m.name} desinstalado.`, 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch {
    notify(`No se pudo desinstalar ${m.name}.`, 'danger');
  }
}

// `rowAction` (camelCase) → ref + addEventListener (igual que /employees).
const mineTable = ref<(HTMLElement & { viewMode?: string }) | null>(null);
const catalogTable = ref<(HTMLElement & { viewMode?: string }) | null>(null);
function handleMineAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: InstalledModule }>).detail;
  if (actionId === 'toggle') void toggleModule(row);
  else if (actionId === 'uninstall') void removeModule(row);
}
function handleCatalogAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Mod }>).detail;
  if (actionId === 'install') void installModule(row);
}
// Vista por defecto = TARJETAS. ok-data-table arranca en 'table'; fijamos su viewMode reactivo al
// montar (consumer-side, hasta que el componente exponga un prop `default-view`).
function defaultToCards(el: (HTMLElement & { viewMode?: string }) | null): void {
  if (el) el.viewMode = 'cards';
}

// --- Carga de datos ---
async function loadInstalled(): Promise<void> {
  try { installedModules.value = await listInstalledModules(); } catch { installedModules.value = []; }
}
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

onMounted(() => {
  void loadCatalog();
  void loadInstalled();
  void nextTick(() => {
    mineTable.value?.addEventListener('rowAction', handleMineAction);
    catalogTable.value?.addEventListener('rowAction', handleCatalogAction);
    defaultToCards(mineTable.value);
    defaultToCards(catalogTable.value);
  });
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    notify(found ? `${found.name} instalado.` : 'Módulo instalado.', 'success');
    void loadCatalog();
    void loadInstalled();
    void refreshModuleNav();
  });
});

// Las tablas se montan con v-show; al cambiar de pestaña re-enganchamos y fijamos la vista cards.
watch(tab, async () => {
  await nextTick();
  mineTable.value?.removeEventListener('rowAction', handleMineAction);
  catalogTable.value?.removeEventListener('rowAction', handleCatalogAction);
  mineTable.value?.addEventListener('rowAction', handleMineAction);
  catalogTable.value?.addEventListener('rowAction', handleCatalogAction);
  defaultToCards(mineTable.value);
  defaultToCards(catalogTable.value);
});

onBeforeUnmount(() => {
  unsubInstalled?.();
  mineTable.value?.removeEventListener('rowAction', handleMineAction);
  catalogTable.value?.removeEventListener('rowAction', handleCatalogAction);
});
</script>

<style scoped>
.fill { height: 100%; }
</style>
