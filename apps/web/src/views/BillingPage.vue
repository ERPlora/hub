<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-menu-button />
        </ion-buttons>
        <ion-title>Billing</ion-title>
      </ion-toolbar>
    </ion-header>

    <ion-content class="ion-padding">
      <!-- Facturas -->
      <template v-if="tab === 'invoices'">
        <h2 class="text-lg font-semibold mb-3">Facturas</h2>

        <div v-if="loadingInvoices" class="flex justify-center py-10">
          <ion-spinner name="dots" />
        </div>

        <template v-else-if="invoices.length > 0">
          <!-- Tabla (pantallas medianas+) -->
          <div class="hidden sm:block overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-[color:var(--ion-border-color)]">
                  <th class="text-left py-2 px-3 font-medium opacity-60">Factura</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">Fecha</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">Vencimiento</th>
                  <th class="text-right py-2 px-3 font-medium opacity-60">Importe</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">Estado</th>
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
                    <ion-button fill="clear" size="small" :aria-label="`Descargar ${inv.number}`" @click="downloadInvoice(inv.id)">
                      <ion-icon slot="icon-only" :icon="downloadOutline" />
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
                  <ion-icon :icon="documentTextOutline" class="text-[color:var(--ion-color-medium)]" />
                  {{ inv.number }}
                </ion-card-title>
              </ion-card-header>
              <ion-card-content>
                <div class="flex items-center justify-between mb-2">
                  <span class="font-semibold">{{ fmtMoney(inv.total, inv.currency) }}</span>
                  <ion-badge :color="statusColor(inv.status)">{{ statusLabel(inv.status) }}</ion-badge>
                </div>
                <p class="text-xs opacity-60">
                  Emitida {{ fmtDate(inv.issueDate) }} · Vence {{ fmtDate(inv.dueDate) }}
                </p>
                <ion-button fill="clear" size="small" class="mt-2 -ml-2" @click="downloadInvoice(inv.id)">
                  <ion-icon slot="start" :icon="downloadOutline" />
                  Descargar
                </ion-button>
              </ion-card-content>
            </ion-card>
          </div>
        </template>

        <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
          <ion-icon :icon="receiptOutline" style="font-size: 2.5rem;" />
          <p>No hay facturas</p>
        </div>
      </template>

      <!-- Suscripciones -->
      <template v-else-if="tab === 'subscriptions'">
        <h2 class="text-lg font-semibold mb-3">Suscripciones</h2>

        <div v-if="loadingSubs" class="flex justify-center py-10">
          <ion-spinner name="dots" />
        </div>

        <template v-else-if="subscriptions.length > 0">
          <!-- Tabla (pantallas medianas+) -->
          <div class="hidden sm:block overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-[color:var(--ion-border-color)]">
                  <th class="text-left py-2 px-3 font-medium opacity-60">Suscripción</th>
                  <th class="text-right py-2 px-3 font-medium opacity-60">Precio</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">Renueva</th>
                  <th class="text-left py-2 px-3 font-medium opacity-60">Estado</th>
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
                    {{ fmtMoney(sub.planPrice, 'EUR') }}/{{ sub.billingCycle || 'mes' }}
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
                  <ion-icon :icon="cardOutline" class="text-[color:var(--ion-color-medium)]" />
                  {{ sub.planName }}
                </ion-card-title>
              </ion-card-header>
              <ion-card-content>
                <p class="font-semibold mb-1">
                  {{ fmtMoney(sub.planPrice, 'EUR') }}/{{ sub.billingCycle || 'mes' }}
                </p>
                <ion-badge :color="statusColor(sub.status)">{{ statusLabel(sub.status) }}</ion-badge>
                <p v-if="sub.currentPeriodEnd" class="text-xs opacity-60 mt-2">
                  {{ sub.cancelAtPeriodEnd ? 'Finaliza' : 'Renueva' }} {{ fmtDate(sub.currentPeriodEnd) }}
                </p>
              </ion-card-content>
            </ion-card>
          </div>
        </template>

        <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
          <ion-icon :icon="refreshOutline" style="font-size: 2.5rem;" />
          <p>No hay suscripciones activas</p>
        </div>
      </template>

      <!-- Pagos -->
      <template v-else>
        <div class="flex items-center justify-center py-16 text-center opacity-60">
          <p>La gestión del método de pago se realiza desde el portal de facturación.</p>
        </div>
      </template>
    </ion-content>

    <!-- Tabs en footer -->
    <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="invoices">
            <ion-icon :icon="receiptOutline" />
            <ion-label>Facturas</ion-label>
          </ion-segment-button>
          <ion-segment-button value="subscriptions">
            <ion-icon :icon="refreshOutline" />
            <ion-label>Suscripciones</ion-label>
          </ion-segment-button>
          <ion-segment-button value="payments">
            <ion-icon :icon="cardOutline" />
            <ion-label>Pagos</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonIcon, IonBadge,
  IonButton, IonCard, IonCardHeader, IonCardTitle, IonCardContent, IonSpinner,
} from '@ionic/vue';
import {
  receiptOutline, refreshOutline, cardOutline, downloadOutline, documentTextOutline,
} from 'ionicons/icons';
import {
  cloudInvoices, cloudSubscriptions, getAccessToken,
  type CloudInvoice, type CloudSubscription,
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

// Estado → etiqueta / color Ionic
const STATUS_LABEL: Record<CloudInvoice['status'], string> = {
  draft: 'Borrador',
  open: 'Abierta',
  paid: 'Pagada',
  void: 'Anulada',
  uncollectible: 'Incobrable',
};

const STATUS_COLOR: Record<CloudInvoice['status'], string> = {
  draft: 'medium',
  open: 'warning',
  paid: 'success',
  void: 'medium',
  uncollectible: 'danger',
};

function statusLabel(s: CloudInvoice['status']): string {
  return STATUS_LABEL[s] ?? s;
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
        'X-Client-Type': 'hub',
      },
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
