<template>
  <AppPage :title="t('nav.billing')">
      <!-- Facturas -->
      <template v-if="tab === 'invoices'">
        <h2 class="text-lg font-semibold mb-3">{{ t('billing.invoices') }}</h2>

        <div v-if="loadingInvoices" class="flex justify-center py-10">
          <ion-spinner name="dots" />
        </div>

        <template v-else-if="invoices.length > 0">
          <!-- Tabla (pantallas medianas+) -->
          <div class="hidden sm:block overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-[color:var(--ion-border-color)]">
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colInvoice') }}</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colDate') }}</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colDueDate') }}</th>
                  <th class="text-right py-2 px-3 font-medium opacity-60">{{ t('billing.colAmount') }}</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colStatus') }}</th>
                  <th class="py-2 px-3"></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="inv in invoices"
                  :key="inv.id"
                  class="border-b border-[color:var(--ion-border-color)] last:border-0"
                >
                  <td class="py-2 px-3">{{ inv.number }}</td>
                  <td class="py-2 px-3">{{ fmtDate(inv.issueDate) }}</td>
                  <td class="py-2 px-3">{{ fmtDate(inv.dueDate) }}</td>
                  <td class="py-2 px-3 text-right font-medium">{{ fmtMoney(inv.total, inv.currency) }}</td>
                  <td class="py-2 px-3">
                    <ion-badge :color="statusColor(inv.status)">{{ statusLabel(inv.status) }}</ion-badge>
                  </td>
                  <td class="py-2 px-3 text-right">
                    <ion-button fill="clear" size="small" :aria-label="t('billing.downloadInvoiceAria', { number: inv.number })" @click="downloadInvoice(inv.id)">
                      <HubIcon slot="icon-only" name="download-outline" />
                    </ion-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Tarjetas (móvil) -->
          <div class="flex flex-col gap-3 sm:hidden">
            <ion-card v-for="inv in invoices" :key="inv.id">
              <ion-card-header>
                <ion-card-title class="flex items-center gap-2 text-base">
                  <HubIcon name="document-text-outline" class="text-[color:var(--ion-color-medium)]" />
                  {{ inv.number }}
                </ion-card-title>
              </ion-card-header>
              <ion-card-content>
                <div class="flex items-center justify-between mb-2">
                  <span class="font-semibold">{{ fmtMoney(inv.total, inv.currency) }}</span>
                  <ion-badge :color="statusColor(inv.status)">{{ statusLabel(inv.status) }}</ion-badge>
                </div>
                <p class="text-xs opacity-60">
                  {{ t('billing.issuedOn', { date: fmtDate(inv.issueDate) }) }} · {{ t('billing.duesOn', { date: fmtDate(inv.dueDate) }) }}
                </p>
                <ion-button fill="clear" size="small" class="mt-2 -ml-2" @click="downloadInvoice(inv.id)">
                  <HubIcon slot="start" name="download-outline" />
                  {{ t('billing.download') }}
                </ion-button>
              </ion-card-content>
            </ion-card>
          </div>
        </template>

        <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
          <HubIcon name="receipt-outline" style="font-size: 2.5rem;" />
          <p>{{ t('billing.noInvoices') }}</p>
        </div>
      </template>

      <!-- Suscripciones -->
      <template v-else-if="tab === 'subscriptions'">
        <h2 class="text-lg font-semibold mb-3">{{ t('billing.subscriptions') }}</h2>

        <div v-if="loadingSubs" class="flex justify-center py-10">
          <ion-spinner name="dots" />
        </div>

        <template v-else-if="subscriptions.length > 0">
          <!-- Tabla (pantallas medianas+) -->
          <div class="hidden sm:block overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-[color:var(--ion-border-color)]">
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colSubscription') }}</th>
                  <th class="text-right py-2 px-3 font-medium opacity-60">{{ t('billing.colPrice') }}</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colRenews') }}</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">{{ t('billing.colStatus') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="sub in subscriptions"
                  :key="sub.id"
                  class="border-b border-[color:var(--ion-border-color)] last:border-0"
                >
                  <td class="py-2 px-3">{{ sub.planName }}</td>
                  <td class="py-2 px-3 text-right font-medium">
                    {{ fmtMoney(sub.planPrice, 'EUR') }}/{{ sub.billingCycle || t('billing.month') }}
                  </td>
                  <td class="py-2 px-3">{{ fmtDate(sub.currentPeriodEnd ?? '') }}</td>
                  <td class="py-2 px-3">
                    <ion-badge :color="statusColor(sub.status)">{{ statusLabel(sub.status) }}</ion-badge>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Tarjetas (móvil) -->
          <div class="flex flex-col gap-3 sm:hidden">
            <ion-card v-for="sub in subscriptions" :key="sub.id">
              <ion-card-header>
                <ion-card-title class="flex items-center gap-2 text-base">
                  <HubIcon name="card-outline" class="text-[color:var(--ion-color-medium)]" />
                  {{ sub.planName }}
                </ion-card-title>
              </ion-card-header>
              <ion-card-content>
                <p class="font-semibold mb-1">
                  {{ fmtMoney(sub.planPrice, 'EUR') }}/{{ sub.billingCycle || t('billing.month') }}
                </p>
                <ion-badge :color="statusColor(sub.status)">{{ statusLabel(sub.status) }}</ion-badge>
                <p v-if="sub.currentPeriodEnd" class="text-xs opacity-60 mt-2">
                  {{ sub.cancelAtPeriodEnd ? t('billing.ends') : t('billing.renews') }} {{ fmtDate(sub.currentPeriodEnd) }}
                </p>
              </ion-card-content>
            </ion-card>
          </div>
        </template>

        <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
          <HubIcon name="refresh-outline" style="font-size: 2.5rem;" />
          <p>{{ t('billing.noSubscriptions') }}</p>
        </div>
      </template>

      <!-- Pagos -->
      <template v-else>
        <div class="flex items-center justify-center py-16 text-center opacity-60">
          <p>{{ t('billing.paymentsPortalNotice') }}</p>
        </div>
      </template>
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
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel,  IonBadge,
  IonButton, IonCard, IonCardHeader, IonCardTitle, IonCardContent, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';

const { t } = useI18n();
import {
  cloudInvoices, cloudSubscriptions, getAccessToken,
  type CloudInvoice, type CloudSubscription
} from '../lib/cloud';
import { config } from '../lib/config';

type BillingTab = 'invoices' | 'subscriptions' | 'payments';

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

function fmtMoney(n: number, currency: string): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: currency || 'EUR' }).format(n);
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

function statusColor(s: CloudInvoice['status']): string {
  return STATUS_COLOR[s] ?? 'medium';
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
