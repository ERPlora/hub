<template>
  <AppPage :title="t('nav.home')">
      <!-- ── Resumen ── -->
      <template v-if="tab === 'resumen'">
        <!-- Alerta de módulos instalados SIN configurar (ADR-0063, lib/setup-status). Solo admin;
             cada módulo declara su chequeo `setup` en module.json. CTA → ajustes del módulo. -->
        <ion-list v-if="pendingSetups.length" inset class="setup-banner">
          <ion-list-header>
            <ion-label color="danger">{{ t('dashboard.setupTitle', { n: pendingSetups.length }) }}</ion-label>
          </ion-list-header>
          <ion-item v-for="s in pendingSetups" :key="s.moduleId" lines="full">
            <HubIcon slot="start" :name="s.icon" />
            <ion-label class="ion-text-wrap">
              <h3>{{ s.title }}</h3>
              <p v-if="s.description">{{ s.description }}</p>
            </ion-label>
            <ion-button slot="end" size="small" @click="goConfigure(s.route)">{{ t('dashboard.configure') }}</ion-button>
          </ion-item>
        </ion-list>

        <!-- Widget CORE de export/import (ADR-0113 §4). DECISIÓN: tarjeta fija ENCIMA del board,
             NO un WidgetDef dentro de ok-widget-board — el board solo se pinta cuando hay módulos
             con widgets (hasWidgets) y su picker/persistencia (storage-key) permitiría ocultarlo;
             justo el hub vacío/recién restaurable, que es quien MÁS lo necesita, no lo vería.
             Una tarjeta fija está SIEMPRE visible, con o sin módulos. -->
        <ion-card data-testid="dashboard-blueprint-widget" class="blueprint-card">
          <ion-card-content>
            <div class="blueprint-row">
              <span class="blueprint-icon"><HubIcon name="swap-vertical-outline" /></span>
              <div>
                <h2 class="blueprint-title">{{ t('dashboard.blueprintTitle') }}</h2>
                <p class="blueprint-body">{{ t('dashboard.blueprintBody') }}</p>
              </div>
            </div>
            <div class="blueprint-actions">
              <ion-button
                size="small"
                data-testid="dashboard-blueprint-import"
                router-link="/import"
                router-direction="forward"
              >
                <HubIcon slot="start" name="cloud-upload-outline" />
                {{ t('dashboard.blueprintImport') }}
              </ion-button>
              <ion-button
                size="small"
                fill="outline"
                data-testid="dashboard-blueprint-export"
                router-link="/export"
                router-direction="forward"
              >
                <HubIcon slot="start" name="download-outline" />
                {{ t('dashboard.blueprintExport') }}
              </ion-button>
            </div>
          </ion-card-content>
        </ion-card>

        <!-- Superficie principal: tablero de widgets que los MÓDULOS instalados declaran en su
             module.json (campo `widgets`, ADR-0054). El shell recolecta, filtra por permiso y
             renderiza cada uno con su ok-* (kind) o el WC del módulo (component). Datos REALES de
             las queries declaradas; degrada a estado vacío/muted (nunca datos inventados). -->
        <ion-list v-if="loadingWidgets" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>{{ t('dashboard.loadingWidgets') }}</ion-label>
          </ion-item>
        </ion-list>
        <ion-list v-else-if="hasWidgets === false" inset>
          <ion-item lines="none">
            <ion-label class="ion-text-center" style="opacity: .6">{{ t('dashboard.noWidgets') }}</ion-label>
          </ion-item>
        </ion-list>
        <!-- ref imperativo: <ok-widget-board> recibe widgets/presets/labels por PROPIEDAD (no
             atributo) — gotcha OutfitKit/Lit con datos tipados. -->
        <ok-widget-board
          v-show="!loadingWidgets && hasWidgets"
          ref="board"
          editable
          storage-key="dashboard-hub"
        />

        <ion-list inset class="ion-padding">
          <ion-list-header>{{ t('dashboard.thisTerminal') }}</ion-list-header>
          <ion-item>
            <ion-label>{{ t('dashboard.plan') }}</ion-label>
            <ion-note slot="end">{{ plan }}</ion-note>
          </ion-item>
          <ion-item>
            <ion-label>{{ t('dashboard.status') }}</ion-label>
            <ion-badge slot="end" :color="estadoActivo ? 'success' : 'medium'">
              {{ estadoActivo === null ? '—' : estadoActivo ? t('dashboard.active') : t('dashboard.inactive') }}
            </ion-badge>
          </ion-item>
          <ion-item>
            <ion-label>{{ t('dashboard.nextInvoice') }}</ion-label>
            <ion-note slot="end">{{ nextInvoice }}</ion-note>
          </ion-item>
          <ion-item lines="none">
            <ion-label>{{ t('dashboard.bridge') }}</ion-label>
            <ion-badge slot="end" :color="bridgeOnline ? 'success' : 'medium'">
              {{ bridgeOnline === null ? '—' : bridgeOnline ? t('dashboard.connected') : t('dashboard.disconnected') }}
            </ion-badge>
          </ion-item>
        </ion-list>
        <ion-button expand="block" fill="outline" router-link="/system" router-direction="forward">
          <HubIcon name="hardware-chip-outline" slot="start" /> {{ t('dashboard.openSystem') }}
        </ion-button>
      </template>

      <!-- ── Aplicaciones ── -->
      <template v-else-if="tab === 'apps'">
        <ion-list v-if="loading" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>{{ t('dashboard.loadingModules') }}</ion-label>
          </ion-item>
        </ion-list>
        <!-- Apps al estilo "Google apps"/ok-app-launcher: icono en caja + label (no cards). -->
        <div v-else class="app-grid">
          <button
            v-for="entry in modules"
            :key="entry.moduleId"
            type="button"
            class="app"
            @click="router.push(`/m/${entry.moduleId}`)"
          >
            <span class="box"><HubIcon :name="entry.iconSvg ?? entry.nav.icon" /></span>
            <span class="label">{{ entry.moduleName }}</span>
          </button>
          <!-- Añadir módulo: misma rejilla, caja "fantasma" para distinguirlo de las apps reales. -->
          <button type="button" class="app" @click="router.push('/marketplace')">
            <span class="box box-add"><HubIcon name="add-outline" /></span>
            <span class="label">{{ t('dashboard.addModule') }}</span>
          </button>
        </div>
      </template>

      <!-- ── Actividad ── (data-table: filtros de columna + búsqueda + orden + paginación) -->
      <template v-else-if="tab === 'actividad'">
        <ion-list v-if="loadingFeed" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>{{ t('dashboard.loading') }}</ion-label>
          </ion-item>
        </ion-list>
        <!-- El estado vacío lo aporta la propia ok-data-table (sin filas). -->
        <div v-else class="fill">
          <ok-data-table
            ref="activityTable"
            fill
            :columns="activityColumns"
            :rows="activity"
            :views="['table', 'cards']"
            :searchKeys="['sale', 'customer', 'method']"
            search-placeholder="Buscar actividad…"
            page-size="15"
            column-picker
          ></ok-data-table>
        </div>
      </template>
    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          :value="tab"
          @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value"
        >
          <ion-segment-button value="resumen">
            <HubIcon name="speedometer-outline" />
            <ion-label>{{ t('dashboard.tabSummary') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="apps">
            <HubIcon name="grid-outline" />
            <ion-label>{{ t('dashboard.tabApps') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="actividad">
            <HubIcon name="pulse-outline" />
            <ion-label>{{ t('dashboard.tabActivity') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonFooter,
  IonSegment, IonSegmentButton, IonLabel,
  IonBadge, IonButton, IonSpinner,
  IonList, IonListHeader, IonItem, IonNote, IonToolbar,
  IonCard, IonCardContent,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';
import { loadMenu, type MenuEntry } from '../lib/module-loader';
import { getClient, getHubSector } from '../lib/runtime';
import { cloudSubscriptions, cloudInvoices, getAccessToken } from '../lib/cloud';
import { collectDashboardWidgets } from '../lib/dashboard-widgets';
import { pendingSetups, refreshSetupStatus } from '../lib/setup-status';
import { formatAmount } from '../lib/money';
import type { WidgetDef, WidgetPreset, OkWidgetBoardLabels } from '@erplora/outfitkit';

const { t } = useI18n();

type Tab = 'resumen' | 'apps' | 'actividad';
type Tone = 'success' | 'warning' | 'primary' | 'medium';

// ok-data-table (OutfitKit) registrado en main.ts. Tipos locales: OutfitKit no emite .d.ts.
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

const tab = ref<Tab>('resumen');
const modules = ref<MenuEntry[]>([]);
const loading = ref<boolean>(true);
const router = useRouter();
const client = getClient();

// ── Tablero de widgets de módulos (ADR-0054) ────────────────────────────────────────────────
// El <ok-widget-board> recibe el catálogo (recolectado de los manifests instalados) y los presets
// por sector por PROPIEDAD JS (datos tipados). El render(cell) de cada WidgetDef ejecuta la query
// del widget y pinta su ok-* (o monta el WC del módulo). Cero mocks: degrada a vacío/muted.
type WidgetBoardEl = HTMLElement & {
  widgets: WidgetDef[];
  presets: WidgetPreset[];
  labels: Partial<OkWidgetBoardLabels>;
};
const board = ref<WidgetBoardEl | null>(null);
const loadingWidgets = ref<boolean>(true);
const hasWidgets = ref<boolean | null>(null);

async function loadWidgets(): Promise<void> {
  try {
    const { widgets, presets } = await collectDashboardWidgets({
      client,
      sector: getHubSector(),
      // Sin set de permisos en cliente hoy (el runtime es la autoridad y revalida cada query):
      // no filtramos por permiso aquí (null = permisivo). Cuando el shell exponga los permisos de
      // la sesión, basta con devolver true/false en este resolutor.
      hasPermission: () => null,
      labels: { empty: t('dashboard.widgetEmpty'), error: t('dashboard.widgetError') },
    });
    hasWidgets.value = widgets.length > 0;
    const el = board.value;
    if (el) {
      el.widgets = widgets;
      el.presets = presets;
      el.labels = {
        customize: t('dashboard.customizePanel'),
        close: t('dashboard.closePanel'),
        presets: t('dashboard.presetsTitle'),
        active: t('dashboard.activeWidgets'),
        available: t('dashboard.availableWidgets'),
        empty: t('dashboard.emptyPanel'),
      };
    }
  } catch {
    hasWidgets.value = false;
  } finally {
    loadingWidgets.value = false;
  }
}

// Formateador de dinero con la MONEDA DEL HUB (money.ts; no más 'EUR' hardcodeado). Datos en
// unidades mayores. Sin decimales para los KPI, con 2 para el feed.
const eur = (n: number, dec = 0): string => formatAmount(n, { maximumFractionDigits: dec });
const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });

// ── "Este terminal" (Plan/Estado/Próxima factura del Cloud + estado del Bridge local) ────────
const plan = ref<string>('—');
const estadoActivo = ref<boolean | null>(null);
const nextInvoice = ref<string>('—');
const bridgeOnline = ref<boolean | null>(null);

async function loadTerminal(): Promise<void> {
  // Plan / Estado / Próxima factura son conceptos del Cloud (billing). Solo se piden si hay
  // sesión cloud (JWT de usuario). En sesión local por PIN NO se llama al Cloud: su 401
  // dispararía el logout global (onSessionExpired) y rebotaría a /login. Sin JWT → '—'.
  if (getAccessToken()) {
    try {
      const subs = await cloudSubscriptions();
      plan.value = subs[0]?.planName ?? '—';
      estadoActivo.value = subs.some((s) => s.status === 'paid' || s.status === 'open');
    } catch { /* degrada */ }
    try {
      const invoices = await cloudInvoices();
      const open = invoices
        .filter((i) => i.status === 'open')
        .sort((a, b) => +new Date(a.dueDate) - +new Date(b.dueDate))[0];
      nextInvoice.value = open ? fmtDate(open.dueDate) : '—';
    } catch { /* degrada */ }
  }
  // Estado del Bridge (hardware local) — detect con timeout corto.
  try {
    const b = await client.peripherals.detect(800);
    bridgeOnline.value = b.online;
  } catch { bridgeOnline.value = false; }
}

// ── Actividad reciente = últimas ventas (datos reales; sin histórico de eventos aún) ─────────
// Vista de data-table: columnas con filtros (método/estado), búsqueda, orden y paginación.
const fmtDateTime = (iso: string): string =>
  iso
    ? new Date(iso).toLocaleString('es-ES', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : '—';

// Pill de estado (tinte suave con tokens Ionic; cruzan el shadow de la tabla).
function badgeCell(text: string, tone: Tone): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

interface ActivityRow {
  date: string; sale: string; customer: string; method: string; amount: number; status: string; tone: Tone;
}
const activity = ref<ActivityRow[]>([]);
const loadingFeed = ref<boolean>(true);
const activityTable = ref<HTMLElement | null>(null);

const activityColumns: DataTableColumn[] = [
  { key: 'date', header: 'Fecha', format: (r) => fmtDateTime(String(r.date ?? '')) },
  { key: 'sale', header: 'Venta' },
  { key: 'customer', header: 'Cliente' },
  { key: 'method', header: 'Método', filterable: true, filterType: 'select' },
  { key: 'amount', header: 'Importe', align: 'right', format: (r) => eur(Number(r.amount) || 0, 2) },
  {
    key: 'status', header: 'Estado', align: 'center', filterable: true, filterType: 'select',
    render: (r) => badgeCell(String(r.status), (r.tone as Tone) ?? 'medium'),
  },
];

// Las labels (filtros/empty/pager) se fijan por PROPIEDAD; el placeholder de búsqueda por atributo.
// La tabla solo está en el DOM cuando la pestaña Actividad está activa y ya cargó → watch del ref.
watch(activityTable, (el) => {
  if (el) (el as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
});

async function loadActivity(): Promise<void> {
  try {
    const page = await client.queryPage<Record<string, unknown>>('sales.list', {
      limit: 100,
      sort: 'created_at',
      dir: 'desc',
    });
    activity.value = page.rows.map((r) => ({
      date: String(r.created_at ?? ''),
      sale: String(r.sale_number ?? `#${r.id}`),
      customer: String(r.customer_name ?? '—'),
      method: String(r.payment_method_name ?? '—'),
      amount: Number(r.total) || 0,
      status: r.status === 'completed' ? 'Completada' : 'Pendiente',
      tone: r.status === 'completed' ? 'success' : 'medium',
    }));
  } catch {
    activity.value = [];
  } finally {
    loadingFeed.value = false;
  }
}

// Navega a los ajustes del módulo pendiente de configurar (ADR-0063).
function goConfigure(route: string): void {
  void router.push(route);
}

onMounted(async () => {
  // Tablero de widgets (módulos), terminal y actividad en paralelo (cada uno degrada por su
  // cuenta). El board está en el DOM por v-show, así que el ref ya existe en onMounted.
  await nextTick();
  void loadWidgets();
  void loadTerminal();
  void loadActivity();
  void refreshSetupStatus(client); // módulos sin configurar (ADR-0063): banner + campana
  try {
    // Una tarjeta por MÓDULO (loadMenu devuelve una entrada por cada navigation[] del manifest).
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
/* La pestaña Actividad usa ok-data-table en modo `fill`: fija el alto al área de ion-content
   (cabecera/filtros/pager fijos, scroll solo en el cuerpo) — mismo patrón que Marketplace. */
.fill {
  height: 100%;
}

/* Widget CORE de export/import: icono en tile suave (wash del color de marca, patrón
   ok-icon-tile) + título/cuerpo + fila de acciones. Espaciado por gap (sin padding custom). */
.blueprint-row {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}
.blueprint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(var(--ion-color-primary-rgb), 0.12);
  color: var(--ion-color-primary);
  font-size: 1.5rem;
}
.blueprint-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}
.blueprint-body {
  color: var(--ion-color-medium);
  margin: 0.15rem 0 0;
}
.blueprint-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

/* Apps tab: rejilla estilo "Google apps"/ok-app-launcher (icono en caja + label), no cards.
   auto-fill → más columnas en pantallas anchas. Mismo look que el launcher de la topbar. */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 0.5rem;
}
.app {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.45rem;
  padding: 0.75rem 0.3rem;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
  border-radius: 12px;
  text-align: center;
  transition: background-color 150ms ease, transform 120ms ease;
}
@media (hover: hover) {
  .app:hover {
    background: var(--ion-color-step-50, #f3f4f6);
    transform: translateY(-1px);
  }
}
.app:active {
  transform: scale(0.97);
}
/* Caja del icono: tile redondeado con color de marca; el icono (HubIcon=ion-icon) hereda
   color (contraste) y tamaño (font-size). */
.app .box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast);
  font-size: 1.7rem;
}
/* "Añadir módulo": caja fantasma (borde discontinuo, sin relleno) para distinguirla de las apps. */
.app .box-add {
  background: transparent;
  color: var(--ion-color-medium);
  border: 1.5px dashed var(--ion-border-color, #d8dbe1);
}
.app .label {
  font-size: 0.78rem;
  line-height: 1.2;
  color: var(--ion-color-medium);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
