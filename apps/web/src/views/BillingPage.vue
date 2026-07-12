<template>
  <AppPage :title="t('nav.billing')">
    <!-- Facturas -->
    <div v-show="tab === 'invoices'" class="fill">
      <div v-if="loadingInvoices" class="flex justify-center py-10">
        <ion-spinner name="dots" />
      </div>
      <!-- `fill` fija el alto al área de ion-content (cabecera/pager fijos, scroll solo en el
           cuerpo) — mismo patrón que AppsPage/EmployeesPage. -->
      <ok-data-table
        v-show="!loadingInvoices"
        ref="invoicesTable"
        fill
        :columns="invoiceColumns"
        :rows="invoices"
        :views="['table', 'cards']"
        :searchKeys="['number']"
        :actions="invoiceActions"
        page-size="10"
        column-picker
      ></ok-data-table>
    </div>

    <!-- Suscripciones -->
    <div v-show="tab === 'subscriptions'" class="fill">
      <div v-if="loadingSubs" class="flex justify-center py-10">
        <ion-spinner name="dots" />
      </div>
      <ok-data-table
        v-show="!loadingSubs"
        ref="subsTable"
        fill
        :columns="subColumns"
        :rows="subscriptions"
        :views="['table', 'cards']"
        :searchKeys="['planName']"
        page-size="10"
        column-picker
      ></ok-data-table>
    </div>

    <!-- Pagos -->
    <div v-show="tab === 'payments'" class="flex items-center justify-center py-16 text-center opacity-60">
      <p>{{ t('billing.paymentsPortalNotice') }}</p>
    </div>

    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="invoices">
            <HubIcon name="receipt-outline" />
            <ion-label>{{ t('billing.invoices') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="subscriptions">
            <HubIcon name="refresh-outline" />
            <ion-label>{{ t('billing.subscriptions') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="payments">
            <HubIcon name="card-outline" />
            <ion-label>{{ t('billing.payments') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';

const { t } = useI18n();
import {
  cloudInvoices, cloudSubscriptions, getAccessToken,
  type CloudInvoice, type CloudSubscription
} from '../lib/cloud';
import { config } from '../lib/config';
import { formatAmount } from '../lib/money';

type BillingTab = 'invoices' | 'subscriptions' | 'payments';

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

const tab = ref<BillingTab>('invoices');
const invoices = ref<CloudInvoice[]>([]);
const subscriptions = ref<CloudSubscription[]>([]);
const loadingInvoices = ref(true);
const loadingSubs = ref(true);

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'invoices' || detail.value === 'subscriptions' || detail.value === 'payments') {
    tab.value = detail.value;
  }
}

// --- Formatters ---
function fmtDate(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

// Formateo con la moneda DE LA FACTURA (las facturas del Cloud traen su propia divisa); sin divisa
// explícita cae a la moneda del hub (money.ts). Locale = el activo del shell.
function fmtMoney(n: number, currency?: string): string {
  return formatAmount(n, currency ? { currency } : undefined);
}

// Estado → clave i18n / color Ionic
const STATUS_LABEL_KEY: Record<CloudInvoice['status'], string> = {
  draft: 'billing.statusDraft',
  open: 'billing.statusOpen',
  paid: 'billing.statusPaid',
  void: 'billing.statusVoid',
  uncollectible: 'billing.statusUncollectible'
};

const STATUS_COLOR: Record<CloudInvoice['status'], string> = {
  draft: 'medium',
  open: 'warning',
  paid: 'success',
  void: 'medium',
  uncollectible: 'danger'
};

function statusLabel(s: CloudInvoice['status']): string {
  const key = STATUS_LABEL_KEY[s];
  return key ? t(key) : s;
}

// Pill de estado: las clases .ion-color-* NO penetran el shadow del data-table, así que el color
// va por vars inline (heredan al shadow). Mismo recurso que AppsPage.badgeCell.
function statusCell(s: CloudInvoice['status']): Node {
  const tone = STATUS_COLOR[s] ?? 'medium';
  const span = document.createElement('span');
  span.textContent = statusLabel(s);
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

// Importe en negrita (las facturas se escanean por importe).
function moneyCell(text: string): Node {
  const span = document.createElement('span');
  span.style.fontWeight = '600';
  span.textContent = text;
  return span;
}

// --- Columnas + acciones (computed → recalculan cabeceras/celdas al cambiar de idioma) ---
const invoiceColumns = computed<DataTableColumn[]>(() => [
  { key: 'number', header: t('billing.colInvoice') },
  { key: 'issueDate', header: t('billing.colDate'), format: (r) => fmtDate(String(r.issueDate ?? '')) },
  { key: 'dueDate', header: t('billing.colDueDate'), format: (r) => fmtDate(String(r.dueDate ?? '')) },
  { key: 'total', header: t('billing.colAmount'), align: 'right', render: (r) => moneyCell(fmtMoney(Number(r.total), r.currency ? String(r.currency) : undefined)) },
  { key: 'status', header: t('billing.colStatus'), filterable: true, filterType: 'select', render: (r) => statusCell(r.status as CloudInvoice['status']) },
]);
const invoiceActions = computed<DataTableAction[]>(() => [
  { id: 'download', label: t('billing.download'), icon: 'download-outline' },
]);

const subColumns = computed<DataTableColumn[]>(() => [
  { key: 'planName', header: t('billing.colSubscription') },
  { key: 'planPrice', header: t('billing.colPrice'), align: 'right', format: (r) => `${fmtMoney(Number(r.planPrice), 'EUR')}/${String(r.billingCycle || t('billing.month'))}` },
  { key: 'currentPeriodEnd', header: t('billing.colRenews'), format: (r) => fmtDate(String(r.currentPeriodEnd ?? '')) },
  { key: 'status', header: t('billing.colStatus'), filterable: true, filterType: 'select', render: (r) => statusCell(r.status as CloudInvoice['status']) },
]);

// --- Wiring de la acción de fila (rowAction es camelCase → addEventListener) ---
const invoicesTable = ref<HTMLElement | null>(null);
const subsTable = ref<HTMLElement | null>(null);

function handleInvoiceAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'download') void downloadInvoice(Number((row as unknown as CloudInvoice).id));
}

// --- Fetch + labels ES al montar (refs vivos por v-show, aunque la tabla esté oculta) ---
onMounted(() => {
  cloudInvoices()
    .then((data) => { invoices.value = data; })
    .catch(() => { invoices.value = []; })
    .finally(() => { loadingInvoices.value = false; });

  cloudSubscriptions()
    .then((data) => { subscriptions.value = data; })
    .catch(() => { subscriptions.value = []; })
    .finally(() => { loadingSubs.value = false; });

  // Vista por defecto responsive: tarjetas en móvil (≤768px), tabla en escritorio — recupera el
  // fallback a tarjetas del listado original. `views` habilita el toggle; `viewMode` es @state
  // interno del WC (default 'table') sin prop pública, así que lo fijamos por referencia.
  const initialView = window.matchMedia('(max-width: 768px)').matches ? 'cards' : 'table';

  if (invoicesTable.value) {
    const el = invoicesTable.value as HTMLElement & { labels: Record<string, string>; viewMode: string };
    el.labels = { ...DT_LABELS_ES, empty: t('billing.noInvoices') };
    el.viewMode = initialView;
    invoicesTable.value.addEventListener('rowAction', handleInvoiceAction);
  }
  if (subsTable.value) {
    const el = subsTable.value as HTMLElement & { labels: Record<string, string>; viewMode: string };
    el.labels = { ...DT_LABELS_ES, empty: t('billing.noSubscriptions') };
    el.viewMode = initialView;
  }
});

onBeforeUnmount(() => {
  invoicesTable.value?.removeEventListener('rowAction', handleInvoiceAction);
});

// --- Descarga PDF de factura (endpoint real del Cloud) ---
async function downloadInvoice(id: number): Promise<void> {
  const token = getAccessToken();
  try {
    const res = await fetch(`${config.cloudApiUrl}/api/v1/billing/invoices/${id}/download/`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-Client-Type': 'hub'
      }
    });
    if (!res.ok) throw new Error(String(res.status));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `factura-${id}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('No se pudo descargar la factura', e);
  }
}
</script>

<style scoped>
/* Fija el alto al área de ion-content (no min-height): las tablas en modo `fill` resuelven su
   :host{height:100%} contra este contenedor → cabecera + pager fijos y scroll solo en el cuerpo. */
.fill {
  height: 100%;
}
</style>
