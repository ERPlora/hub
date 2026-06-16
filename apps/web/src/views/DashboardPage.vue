<!--
  DashboardPage — «Inicio» del Hub, con tres pestañas (footer):
    · Widgets    → panel configurable con `ok-widget-board` (el usuario activa lo que necesita).
    · Apps       → listado de las apps/módulos instalados (fuente de verdad = runtime, loadMenu).
    · Actividad  → registro de la actividad de usuarios (ok-data-table; demo hasta que el core
                   exponga el audit/event-log — el log del SISTEMA vive en /system › Registros).
-->
<template>
  <AppPage :title="t('nav.home')">
    <!-- ── Widgets ── -->
    <template v-if="tab === 'widgets'">
      <ok-widget-board
        editable
        storage-key="dashboard-hub"
        :widgets="WIDGETS"
        :presets="PRESETS"
        :labels="boardLabels"
      >
        <span slot="title" class="board-title">{{ t('dashboard.myPanel') }}</span>
      </ok-widget-board>
    </template>

    <!-- ── Apps (módulos instalados) ── -->
    <template v-else-if="tab === 'apps'">
      <ion-list v-if="loading" inset>
        <ion-item lines="none">
          <ion-spinner slot="start" name="crescent" />
          <ion-label>{{ t('dashboard.loadingModules') }}</ion-label>
        </ion-item>
      </ion-list>
      <ion-grid v-else class="ion-no-padding">
        <ion-row>
          <ion-col v-for="entry in modules" :key="entry.moduleId" size="6" size-md="3" size-lg="2">
            <ion-card button class="app-card ion-no-margin" @click="router.push(`/m/${entry.moduleId}`)">
              <ion-card-content class="app-card__body">
                <HubIcon :name="entry.iconSvg ?? entry.nav.icon" class="app-card__icon" />
                <span class="app-card__label">{{ entry.moduleName }}</span>
              </ion-card-content>
            </ion-card>
          </ion-col>
          <ion-col size="6" size-md="3" size-lg="2">
            <ion-card button class="app-card app-card--add ion-no-margin" router-link="/marketplace" router-direction="forward">
              <ion-card-content class="app-card__body">
                <HubIcon name="add-outline" class="app-card__icon" />
                <span class="app-card__label">{{ t('dashboard.addModule') }}</span>
              </ion-card-content>
            </ion-card>
          </ion-col>
        </ion-row>
      </ion-grid>
    </template>

    <!-- ── Actividad (registro de usuarios) ── -->
    <template v-else>
      <ok-data-table
        :columns="activityColumns"
        :rows="activityRows"
        :searchKeys="['user', 'action', 'detail']"
        search-placeholder="Buscar en la actividad…"
        page-size="15"
        empty-message="Sin actividad registrada"
        column-picker
      ></ok-data-table>
    </template>

    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <ion-segment :value="tab" @ion-change="onTabChange">
            <ion-segment-button value="widgets">
              <HubIcon name="grid-outline" />
              <ion-label>{{ t('dashboard.tabWidgets') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="apps">
              <HubIcon name="apps-outline" />
              <ion-label>{{ t('dashboard.apps') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="activity">
              <HubIcon name="pulse-outline" />
              <ion-label>{{ t('dashboard.activity') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
        </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonGrid, IonRow, IonCol, IonCard, IonCardContent,
  IonSpinner, IonList, IonItem, IonLabel,
  IonFooter, IonToolbar, IonSegment, IonSegmentButton,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { loadMenu, type MenuEntry } from '../lib/module-loader';

const { t } = useI18n();
const router = useRouter();

type Tab = 'widgets' | 'apps' | 'activity';
const tab = ref<Tab>('widgets');
function onTabChange(ev: Event): void {
  const v = (ev as CustomEvent<{ value: Tab }>).detail.value;
  if (v === 'widgets' || v === 'apps' || v === 'activity') tab.value = v;
}

// ── Tipos del catálogo de ok-widget-board / ok-data-table (OutfitKit no emite .d.ts aquí) ───────
type WidgetSize = 'sm' | 'md' | 'lg';
interface WidgetDef { id: string; title: string; icon?: string; category?: string; size?: WidgetSize; render: (cell: HTMLElement) => void }
interface WidgetPreset { id: string; label: string; widgets: string[] }
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string; header: string; align?: 'left' | 'right' | 'center';
  filterable?: boolean; filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  format?: (row: Row) => string; render?: (row: Row) => Node | string;
}

// Textos del selector del panel (⋮). El componente cae a inglés si no se pasan.
const boardLabels = {
  customize: t('dashboard.board.customize'),
  close: t('dashboard.board.close'),
  presets: t('dashboard.board.presets'),
  active: t('dashboard.board.active'),
  available: t('dashboard.board.available'),
  empty: t('dashboard.board.empty'),
};

// ── Helpers para construir el cuerpo (DOM) de cada widget con SUS datos (imperativo, CSP-safe) ──
type ElOpts = { attrs?: Record<string, unknown>; props?: Record<string, unknown>; style?: string; text?: string };
function el(tag: string, opts: ElOpts = {}): HTMLElement {
  const n = document.createElement(tag) as HTMLElement & Record<string, unknown>;
  for (const [k, v] of Object.entries(opts.attrs ?? {})) v === true ? n.setAttribute(k, '') : v != null && n.setAttribute(k, String(v));
  for (const [k, v] of Object.entries(opts.props ?? {})) (n as Record<string, unknown>)[k] = v;
  if (opts.style) n.style.cssText = opts.style;
  if (opts.text != null) n.textContent = opts.text;
  return n;
}
function card(cell: HTMLElement, title: string, sub?: string): HTMLElement {
  const c = el('ion-card', { style: 'margin:0;height:100%' });
  const hd = el('ion-card-header');
  hd.appendChild(el('ion-card-title', { text: title, style: 'font-size:1rem' }));
  if (sub) hd.appendChild(el('ion-card-subtitle', { text: sub }));
  c.appendChild(hd);
  const body = el('ion-card-content');
  c.appendChild(body);
  cell.appendChild(c);
  return body;
}

// ── Catálogo de widgets (datos demo representativos; se cablearán a queries del runtime) ────────
const WIDGETS: WidgetDef[] = [
  {
    id: 'ventas-hoy', title: 'Ventas hoy', icon: 'trending-up-outline', category: 'Ventas', size: 'sm',
    render: (cell) => {
      const k = el('ok-kpi', { attrs: { label: 'Ventas hoy', value: '€4 812', delta: '+12,4% vs ayer', trend: 'up', icon: 'trending-up-outline' } });
      k.appendChild(el('ok-sparkline', { attrs: { type: 'line', filled: true, height: '32' }, props: { values: [6, 9, 8, 12, 11, 15, 14, 18, 21] }, style: 'display:block;margin-top:6px' }));
      cell.appendChild(k);
    },
  },
  {
    id: 'pedidos', title: 'Pedidos', icon: 'receipt-outline', category: 'Ventas', size: 'sm',
    render: (cell) => cell.appendChild(el('ok-kpi', { attrs: { label: 'Pedidos', value: '183', delta: '+9 en la última hora', trend: 'up', icon: 'receipt-outline' } })),
  },
  {
    id: 'personal', title: 'Personal activo', icon: 'people-outline', category: 'RRHH', size: 'sm',
    render: (cell) => {
      const k = el('ok-kpi', { attrs: { label: 'Personal activo', value: '6', icon: 'people-outline' } });
      k.appendChild(el('ok-status-pill', { attrs: { tone: 'success', dot: true, label: '2 en caja ahora' }, style: 'margin-top:6px' }));
      cell.appendChild(k);
    },
  },
  {
    id: 'stock-bajo', title: 'Stock bajo', icon: 'alert-circle-outline', category: 'Inventario', size: 'sm',
    render: (cell) => cell.appendChild(el('ok-kpi', { attrs: { label: 'Stock bajo', value: '7', delta: 'bajo umbral', trend: 'down', icon: 'alert-circle-outline' } })),
  },
  {
    id: 'ventas-semana', title: 'Ventas — última semana', icon: 'bar-chart-outline', category: 'Ventas', size: 'lg',
    render: (cell) => {
      const body = card(cell, 'Ventas — última semana', '€14.218 totales · objetivo €15.000');
      body.appendChild(el('ok-chart', {
        attrs: { type: 'bar', height: '180', gridlines: true },
        props: { labels: ['L', 'M', 'X', 'J', 'V', 'S', 'D'], axis: ['€3K', '€2K', '€1K', '€0'], series: [{ name: 'Ventas', data: [1500, 1900, 2100, 2450, 2900, 2750, 2250] }] },
      }));
    },
  },
  {
    id: 'top-productos', title: 'Top productos', icon: 'bar-chart-outline', category: 'Inventario', size: 'md',
    render: (cell) => {
      const body = card(cell, 'Top productos', 'Esta semana · por importe');
      body.appendChild(el('ok-bar-list', {
        attrs: { 'value-format': 'currency', currency: 'EUR', locale: 'es-ES' },
        props: { items: [
          { label: 'Café con leche', value: 1820, color: 'brand' },
          { label: 'Tostada', value: 1240, color: 'leaf' },
          { label: 'Menú del día', value: 980, color: 'info' },
          { label: 'Cerveza', value: 760, color: 'warn' },
          { label: 'Agua', value: 410, color: 'neutral' },
        ] },
      }));
    },
  },
  {
    id: 'actividad', title: 'Actividad reciente', icon: 'receipt-outline', category: 'General', size: 'md',
    render: (cell) => {
      const body = card(cell, 'Actividad reciente', 'Últimos movimientos');
      body.appendChild(el('ok-timeline', { props: { items: [
        { id: 'e1', icon: 'bag-handle-outline', color: 'primary', title: 'Pedido #1042 cerrado', description: '38,90 € · tarjeta · caja 1', time: 'hace 2 min' },
        { id: 'e2', icon: 'warning-outline', color: 'warning', title: 'Alerta de stock · Cola 33cl', description: 'bajo umbral (quedan 4)', time: 'hace 14 min' },
        { id: 'e3', icon: 'person-outline', color: 'medium', title: 'Lucía García fichó entrada', description: 'caja 2', time: 'hace 22 min' },
        { id: 'e4', icon: 'checkmark-outline', color: 'success', title: 'Factura INV-2026-00018 pagada', description: '29,99 €', time: 'hace 31 min' },
      ] } }));
    },
  },
  {
    id: 'stock-alert', title: 'Aviso de stock', icon: 'warning-outline', category: 'Inventario', size: 'md',
    render: (cell) => {
      cell.appendChild(el('ok-inline-feedback', {
        attrs: { tone: 'warning', heading: '7 productos bajo umbral', icon: 'warning-outline' },
        text: 'Revisa el inventario para reponer antes de quedarte sin stock.',
      }));
    },
  },
];

const PRESETS: WidgetPreset[] = [
  { id: 'general', label: 'General', widgets: ['ventas-hoy', 'pedidos', 'personal', 'stock-bajo', 'ventas-semana', 'actividad'] },
  { id: 'hosteleria', label: 'Hostelería', widgets: ['ventas-hoy', 'pedidos', 'ventas-semana', 'actividad'] },
  { id: 'retail', label: 'Retail', widgets: ['ventas-hoy', 'stock-bajo', 'top-productos', 'ventas-semana', 'stock-alert'] },
];

// ── Actividad de usuarios (ok-data-table). Demo hasta que el core exponga el audit/event-log. ───
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'warning' | 'danger'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}
const activityColumns: DataTableColumn[] = [
  { key: 'time', header: 'Hora' },
  { key: 'user', header: 'Usuario', filterable: true, filterType: 'select' },
  { key: 'action', header: 'Acción', render: (r) => badgeCell(String(r.action), String(r.tone) as 'success') },
  { key: 'detail', header: 'Detalle' },
];
const activityRows: Row[] = [
  { time: '14:31', user: 'Demo Admin', action: 'Venta', tone: 'success', detail: 'Pedido #1042 · 38,90 €' },
  { time: '14:18', user: 'María López', action: 'Inventario', tone: 'warning', detail: 'Ajuste stock · Cola 33cl (-4)' },
  { time: '14:05', user: 'Juan Pérez', action: 'Fichaje', tone: 'primary', detail: 'Entrada · caja 2' },
  { time: '13:52', user: 'Demo Admin', action: 'Factura', tone: 'success', detail: 'INV-2026-00018 pagada · 29,99 €' },
  { time: '13:40', user: 'Ana Ruiz', action: 'Login', tone: 'medium', detail: 'Inicio de sesión (PIN)' },
];

// ── Aplicaciones (módulos instalados, fuente de verdad = runtime vía loadMenu) ──────────────────
const modules = ref<MenuEntry[]>([]);
const loading = ref<boolean>(true);
onMounted(async () => {
  try {
    const entries = await loadMenu();
    const byModule = new Map<string, MenuEntry>();
    for (const e of entries) if (!byModule.has(e.moduleId)) byModule.set(e.moduleId, e);
    modules.value = [...byModule.values()];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.board-title {
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--ion-color-medium);
}
.app-card { height: 100%; }
.app-card__body { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; text-align: center; }
.app-card__icon { font-size: 1.6rem; color: var(--ion-color-primary); }
.app-card--add { border: 1px dashed var(--ion-border-color, rgba(127, 127, 127, 0.3)); opacity: 0.8; }
.app-card--add .app-card__icon { color: var(--ion-color-medium); }
.app-card__label { font-size: 0.8rem; font-weight: 500; line-height: 1.2; }
</style>
