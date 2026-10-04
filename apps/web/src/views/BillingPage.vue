<template>
  <AppPage :title="t('nav.billing')">
    <!-- Facturas -->
    <div v-show="tab === 'invoices'" class="fill">
      <div v-if="invoiceState === 'loading'" class="flex justify-center py-10">
        <ion-spinner name="crescent" />
      </div>
      <ok-inline-feedback
        v-else-if="invoiceState === 'auth-required'"
        class="billing-feedback"
        tone="warning"
        icon="person-circle-outline"
        :heading="t('billing.cloudAuthTitle')"
      >
        {{ t('billing.cloudAuthBody') }}
      </ok-inline-feedback>
      <ok-inline-feedback
        v-else-if="invoiceState === 'error'"
        class="billing-feedback"
        tone="danger"
        icon="cloud-offline-outline"
        :heading="t('billing.loadErrorTitle')"
      >
        {{ t('billing.loadErrorBody') }}
        <ion-button slot="actions" size="small" fill="outline" @click="loadInvoices">
          <HubIcon name="refresh-outline" slot="start" />
          {{ t('billing.retry') }}
        </ion-button>
      </ok-inline-feedback>
      <!-- `fill` fija el alto al área de ion-content (cabecera/pager fijos, scroll solo en el
           cuerpo) — mismo patrón que AppsPage/EmployeesPage. -->
      <ok-data-table
        v-show="invoiceState === 'ready'"
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
    <div v-show="tab === 'subscriptions'" class="fill subs-fill">
      <!-- El Hub NO vende (ADR-0114) y desde hub#479 tampoco lleva a vender: el CTA «Gestionar
           plan» abría el marketplace del SaaS, que cambia el plan con proración sobre la tarjeta
           guardada. Queda la frase que dice DÓNDE se gestiona; la tabla de abajo sigue mostrando
           lo contratado, que es lo que esta página tiene que hacer. -->
      <ion-card v-if="subscriptionState === 'ready'" class="plan-cta m-0">
        <ion-card-content class="plan-cta-content">
          <p class="plan-cta-hint">{{ t('billing.managePlanHint') }}</p>
        </ion-card-content>
      </ion-card>
      <div v-if="subscriptionState === 'loading'" class="flex justify-center py-10">
        <ion-spinner name="crescent" />
      </div>
      <ok-inline-feedback
        v-else-if="subscriptionState === 'auth-required'"
        class="billing-feedback"
        tone="warning"
        icon="person-circle-outline"
        :heading="t('billing.cloudAuthTitle')"
      >
        {{ t('billing.cloudAuthBody') }}
      </ok-inline-feedback>
      <ok-inline-feedback
        v-else-if="subscriptionState === 'error'"
        class="billing-feedback"
        tone="danger"
        icon="cloud-offline-outline"
        :heading="t('billing.loadErrorTitle')"
      >
        {{ t('billing.loadErrorBody') }}
        <ion-button slot="actions" size="small" fill="outline" @click="refreshSubscriptions">
          <HubIcon name="refresh-outline" slot="start" />
          {{ t('billing.retry') }}
        </ion-button>
      </ok-inline-feedback>
      <ok-data-table
        v-show="subscriptionState === 'ready'"
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

    <!-- Pagos: aviso (no es un vacío de datos, sino un portal externo) → ok-empty-state. El botón
         que abría ese portal se retiró (hub#479): el portal de facturación del SaaS es una
         superficie de pago —lleva el alta de Stripe Connect—, así que el aviso dice dónde está y
         ya. Ojo al escribir aquí: el guard `no-purchase-steering.test.ts` es literal a propósito y
         salta también con una ruta escrita en un comentario. Es lo que se quiere: prefiere un falso
         positivo que reformulas en diez segundos a un enlace real que se cuela. -->
    <div v-show="tab === 'payments'" class="payments-notice">
      <ok-empty-state
        icon="card-outline"
        :message="t('billing.paymentsPortalNotice')"
      />
    </div>

    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar" :value="tab" @ion-change="onTabChange">
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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useHashTab } from '../lib/hash-tab';
import {
  IonToolbar, IonCard, IonCardContent, IonButton,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { toastError, toastSuccess } from '../lib/toast';
import { saveDownload, saveDownloadMessageKey } from '../lib/save-download';

const { t, locale } = useI18n();
import {
  cloudInvoices, cloudSubscriptions, getAccessToken, hasIndependentLocalSession,
  type CloudInvoice, type CloudSubscription
} from '../lib/cloud';
import { cloudApiUrlReady, config } from '../lib/config';
import { formatAmount } from '../lib/money';
import { formatDate } from '../lib/format-datetime';

type BillingTab = 'invoices' | 'subscriptions' | 'payments';
type BillingLoadState = 'loading' | 'ready' | 'auth-required' | 'error';
const TABS: readonly BillingTab[] = ['invoices', 'subscriptions', 'payments'];

// Deep link by HASH (/billing#payments), synced only while the address is /billing (hub#2444).
const tab = useHashTab<BillingTab>('/billing', (h) => TABS.find((v) => v === h.slice(1)) ?? 'invoices');

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

const invoices = ref<CloudInvoice[]>([]);
const subscriptions = ref<CloudSubscription[]>([]);
const invoiceState = ref<BillingLoadState>('loading');
const subscriptionState = ref<BillingLoadState>('loading');

// --- Plan del hub: solo LECTURA (hub#479) ---
// Aquí había dos direcciones del SaaS y los controles que las abrían: `plansDeepLink()` (el
// marketplace de planes, que cambia el plan con proración sobre la tarjeta guardada) y
// `billingPortalLink()` (el portal de facturación, con el alta de Stripe Connect). Las dos son
// superficies de pago, así que llevar a ellas desde dentro de la app es steering — la causa de
// rechazo que hay que no tener en Google Play ni en Microsoft Store.
//
// Esta página conserva lo suyo: enseña facturas y suscripciones, que es información del plan
// contratado. Contratar, cambiar o cancelar se hace en erplora.com.

function unavailableCloudState(): BillingLoadState {
  return getAccessToken() ? 'error' : 'auth-required';
}

async function loadInvoices(): Promise<void> {
  if (!getAccessToken() && hasIndependentLocalSession()) {
    invoices.value = [];
    invoiceState.value = 'auth-required';
    return;
  }
  invoiceState.value = 'loading';
  try {
    invoices.value = await cloudInvoices();
    invoiceState.value = 'ready';
  } catch {
    invoiceState.value = unavailableCloudState();
  }
}

async function refreshSubscriptions(): Promise<void> {
  if (!getAccessToken() && hasIndependentLocalSession()) {
    subscriptions.value = [];
    subscriptionState.value = 'auth-required';
    return;
  }
  subscriptionState.value = 'loading';
  try {
    subscriptions.value = await cloudSubscriptions();
    subscriptionState.value = 'ready';
  } catch {
    subscriptionState.value = unavailableCloudState();
  }
}

function onWindowFocus(): void {
  void refreshSubscriptions();
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'visible') void refreshSubscriptions();
}

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'invoices' || detail.value === 'subscriptions' || detail.value === 'payments') {
    tab.value = detail.value;
  }
}

// --- Formatters ---
function fmtDate(iso: string): string {
  return (
    formatDate(iso, {
      locale: locale.value,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }) ?? '—'
  );
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

function applyTableLabels(): void {
  if (invoicesTable.value) {
    (invoicesTable.value as HTMLElement & { labels: Record<string, string> }).labels = {
      ...dataTableLabels(locale.value),
      empty: t('billing.noInvoices'),
    };
  }
  if (subsTable.value) {
    (subsTable.value as HTMLElement & { labels: Record<string, string> }).labels = {
      ...dataTableLabels(locale.value),
      empty: t('billing.noSubscriptions'),
    };
  }
}

function handleInvoiceAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'download') void downloadInvoice(row as unknown as CloudInvoice);
}

// --- Fetch + labels ES al montar (refs vivos por v-show, aunque la tabla esté oculta) ---
onMounted(() => {
  void loadInvoices();
  void refreshSubscriptions();

  // Recheck-on-focus: tras gestionar el plan en el SaaS (navegador externo),
  // el estado se refresca al volver a esta ventana.
  window.addEventListener('focus', onWindowFocus);
  document.addEventListener('visibilitychange', onVisibilityChange);

  // Vista por defecto responsive: tarjetas en móvil (≤768px), tabla en escritorio — recupera el
  // fallback a tarjetas del listado original. `views` habilita el toggle; `viewMode` es @state
  // interno del WC (default 'table') sin prop pública, así que lo fijamos por referencia.
  const initialView = window.matchMedia('(max-width: 768px)').matches ? 'cards' : 'table';

  if (invoicesTable.value) {
    const el = invoicesTable.value as HTMLElement & { labels: Record<string, string>; viewMode: string };
    el.labels = { ...dataTableLabels(locale.value), empty: t('billing.noInvoices') };
    el.viewMode = initialView;
    invoicesTable.value.addEventListener('rowAction', handleInvoiceAction);
  }
  if (subsTable.value) {
    const el = subsTable.value as HTMLElement & { labels: Record<string, string>; viewMode: string };
    el.labels = { ...dataTableLabels(locale.value), empty: t('billing.noSubscriptions') };
    el.viewMode = initialView;
  }
});
watch(locale, applyTableLabels);

onBeforeUnmount(() => {
  invoicesTable.value?.removeEventListener('rowAction', handleInvoiceAction);
  window.removeEventListener('focus', onWindowFocus);
  document.removeEventListener('visibilitychange', onVisibilityChange);
});

// --- Descarga PDF de factura (endpoint real del Cloud) ---
async function downloadInvoice(invoice: CloudInvoice): Promise<void> {
  const token = getAccessToken();
  try {
    await cloudApiUrlReady();
    const res = await fetch(`${config.cloudApiUrl}/api/v1/billing/invoices/${invoice.id}/download/`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-Client-Type': 'hub'
      }
    });
    if (!res.ok) throw new Error(String(res.status));
    const safeNumber = String(invoice.number || invoice.id).replace(/[^a-zA-Z0-9._-]+/g, '-');
    const savedTo = await saveDownload(`factura-${safeNumber}.pdf`, await res.blob());
    if (savedTo) await toastSuccess(t('download.savedTo', { path: savedTo }));
  } catch (error) {
    // The generic `billing.downloadError` only fits the fetch half. Inside the installed app the
    // half that fails is the SAVE, and «this app cannot save files on a tablet» is the only
    // sentence the user can act on (hub#480).
    await toastError(t(saveDownloadMessageKey(error)));
  }
}
</script>

<style scoped>
/* Fija el alto al área de ion-content (no min-height): las tablas en modo `fill` resuelven su
   :host{height:100%} contra este contenedor → cabecera + pager fijos y scroll solo en el cuerpo. */
.fill {
  height: 100%;
  min-height: var(--ok-work-surface-min);
}

/* La pestaña de suscripciones apila CTA de plan + tabla; la tabla resuelve su
   height:100% contra el hueco restante. */
.subs-fill {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.subs-fill > ok-data-table {
  flex: 1;
  min-height: 0;
}

.plan-cta-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.plan-cta-hint {
  margin: 0;
  font-size: 13px;
  opacity: 0.75;
}

/* Pestaña Pagos: aviso de portal externo centrado. Antes era un placeholder Tailwind. */
.payments-notice {
  padding: 2rem 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.billing-feedback {
  margin: 1rem 0;
}
</style>
