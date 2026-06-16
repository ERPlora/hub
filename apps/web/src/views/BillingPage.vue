<template>
  <AppPage :title="t('nav.billing')">
    <div class="fill">
      <!-- Facturas -->
      <div v-if="tab === 'invoices' && loadingInvoices" class="grid place-items-center h-full">
        <ion-spinner name="dots" />
      </div>
      <ok-data-table
        v-show="tab === 'invoices' && !loadingInvoices"
        ref="invoicesTable"
        fill
        :columns="invoiceColumns"
        :rows="invoices"
        :searchKeys="['number']"
        :actions="invoiceActions"
        search-placeholder="Buscar factura…"
        page-size="10"
        empty-message="No hay facturas"
        column-picker
      ></ok-data-table>

      <!-- Suscripciones -->
      <div v-if="tab === 'subscriptions' && loadingSubs" class="grid place-items-center h-full">
        <ion-spinner name="dots" />
      </div>
      <ok-data-table
        v-show="tab === 'subscriptions' && !loadingSubs"
        ref="subsTable"
        fill
        :columns="subColumns"
        :rows="subscriptions"
        :searchKeys="['planName']"
        search-placeholder="Buscar suscripción…"
        page-size="10"
        empty-message="No hay suscripciones activas"
        column-picker
      ></ok-data-table>

    </div>
    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="invoices">
            <HubIcon name="receipt-outline" />
            <ion-label>Facturas</ion-label>
          </ion-segment-button>
          <ion-segment-button value="subscriptions">
            <HubIcon name="refresh-outline" />
            <ion-label>Suscripciones</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonSpinner,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';

const { t } = useI18n();
import {
  cloudInvoices, cloudSubscriptions, getAccessToken,
  type CloudInvoice, type CloudSubscription
} from '../lib/cloud';
import { config } from '../lib/config';

type BillingTab = 'invoices' | 'subscriptions';

const tab = ref<BillingTab>('invoices');
const invoices = ref<CloudInvoice[]>([]);
const subscriptions = ref<CloudSubscription[]>([]);
const loadingInvoices = ref(true);
const loadingSubs = ref(true);

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'invoices' || detail.value === 'subscriptions') {
    tab.value = detail.value;
  }
}

// --- Formatters ---
function fmtDate(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtMoney(n: number, currency: string): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: currency || 'EUR' }).format(n);
}

// Estado → etiqueta / color Ionic
const STATUS_LABEL: Record<CloudInvoice['status'], string> = {
  draft: 'Borrador',
  open: 'Abierta',
  paid: 'Pagada',
  void: 'Anulada',
  uncollectible: 'Incobrable'
};

const STATUS_COLOR: Record<CloudInvoice['status'], string> = {
  draft: 'medium',
  open: 'warning',
  paid: 'success',
  void: 'medium',
  uncollectible: 'danger'
};

function statusLabel(s: CloudInvoice['status']): string {
  return STATUS_LABEL[s] ?? s;
}

function statusColor(s: CloudInvoice['status']): string {
  return STATUS_COLOR[s] ?? 'medium';
}

// ── ok-data-table: tipos locales + celdas + columnas/acciones ───────────────────────────────────
type Row = Record<string, unknown>;
type Tone = 'success' | 'medium' | 'primary' | 'danger' | 'warning';
interface DataTableColumn { key: string; header: string; align?: 'left' | 'right' | 'center'; format?: (row: Row) => string; render?: (row: Row) => Node | string }
interface DataTableAction { id: string; label: string; icon?: string; color?: string }

function badgeCell(text: string, tone: Tone): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}
function statusCell(row: Row): Node {
  const s = row.status as CloudInvoice['status'];
  return badgeCell(statusLabel(s), statusColor(s) as Tone);
}

const invoiceColumns: DataTableColumn[] = [
  { key: 'number', header: 'Factura' },
  { key: 'issueDate', header: 'Fecha', format: (r) => fmtDate(String(r.issueDate ?? '')) },
  { key: 'dueDate', header: 'Vencimiento', format: (r) => fmtDate(String(r.dueDate ?? '')) },
  { key: 'total', header: 'Importe', align: 'right', format: (r) => fmtMoney(Number(r.total ?? 0), String(r.currency ?? 'EUR')) },
  { key: 'status', header: 'Estado', render: statusCell },
];
const invoiceActions: DataTableAction[] = [
  { id: 'download', label: 'Descargar', icon: 'download-outline' },
];

const subColumns: DataTableColumn[] = [
  { key: 'planName', header: 'Suscripción' },
  { key: 'planPrice', header: 'Precio', align: 'right', format: (r) => `${fmtMoney(Number(r.planPrice ?? 0), 'EUR')}/${String(r.billingCycle || 'mes')}` },
  { key: 'currentPeriodEnd', header: 'Renueva', format: (r) => fmtDate(String(r.currentPeriodEnd ?? '')) },
  { key: 'status', header: 'Estado', render: statusCell },
];

// `rowAction` (descargar) es camelCase → ref + addEventListener (igual que /employees).
const invoicesTable = ref<HTMLElement | null>(null);
const subsTable = ref<HTMLElement | null>(null);
function handleInvoiceAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: CloudInvoice }>).detail;
  if (actionId === 'download') void downloadInvoice(row.id);
}

// --- Fetch al montar ---
onMounted(() => {
  cloudInvoices()
    .then((data) => { invoices.value = data; })
    .catch(() => { invoices.value = []; })
    .finally(() => { loadingInvoices.value = false; });

  cloudSubscriptions()
    .then((data) => { subscriptions.value = data; })
    .catch(() => { subscriptions.value = []; })
    .finally(() => { loadingSubs.value = false; });

  void nextTick(() => invoicesTable.value?.addEventListener('rowAction', handleInvoiceAction));
});

// El ref de la tabla de facturas puede montarse tras cambiar de pestaña (v-show); re-enganchar.
watch(tab, async () => {
  await nextTick();
  invoicesTable.value?.removeEventListener('rowAction', handleInvoiceAction);
  invoicesTable.value?.addEventListener('rowAction', handleInvoiceAction);
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
