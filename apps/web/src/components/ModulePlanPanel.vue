<!--
  ModulePlanPanel — panel del SHELL (no un Web Component de módulo) que se renderiza en la pestaña
  sintética "Plan" de la navegación de un módulo (ver ModuleView). Es la cara de cliente del plano
  "compra = usuario": pinta los tiers del manifest (`billing.tiers`), el estado de suscripción
  actual (cloudModuleSubscription) y los CTAs comprar/mejorar/cancelar, que pegan DIRECTO al Cloud
  con el JWT del usuario + X-Hub-Id (NO el proxy del runtime ni el token de máquina).

  El Cloud NO expone el slug del tier actual (ni module-subscription ni check_ownership lo traen),
  así que en v1 NO se resalta un tier concreto: se muestra solo el `status` global y los CTAs se
  habilitan según ese estado.
-->
<template>
  <div class="plan-panel">
    <!-- Estado de la suscripción actual -->
    <ion-card class="status-card">
      <ion-card-header>
        <div class="status-head">
          <ion-card-title>{{ t('modulePlan.statusTitle') }}</ion-card-title>
          <ion-badge :color="statusColor">{{ statusLabel }}</ion-badge>
        </div>
      </ion-card-header>
      <ion-card-content>
        <div v-if="loadingStatus" class="flex items-center gap-2 opacity-70">
          <ion-spinner name="crescent" /> {{ t('modulePlan.loadingStatus') }}
        </div>
        <template v-else>
          <p v-if="sub && sub.status === 'trialing' && sub.trialEnd" class="status-line">
            {{ t('modulePlan.trialEnds', { date: fmtDate(sub.trialEnd) }) }}
          </p>
          <p v-else-if="sub && sub.periodEnd && (sub.status === 'active' || sub.status === 'canceled')" class="status-line">
            {{ sub.status === 'canceled'
              ? t('modulePlan.cancelsOn', { date: fmtDate(sub.periodEnd) })
              : t('modulePlan.renewsOn', { date: fmtDate(sub.periodEnd) }) }}
          </p>
          <p v-else class="status-line opacity-70">{{ statusHint }}</p>

          <!-- Cancelar: solo si hay una suscripción activa o en prueba (no cancelada ya). -->
          <ion-button
            v-if="canCancel"
            class="cancel-btn"
            fill="outline"
            color="danger"
            size="small"
            :disabled="busy"
            @click="onCancel"
          >
            <HubIcon name="close-outline" slot="start" />
            {{ t('modulePlan.cancel') }}
          </ion-button>
        </template>
      </ion-card-content>
    </ion-card>

    <!-- Tiers del manifest -->
    <div v-if="tiers.length" class="tiers-grid">
      <ion-card v-for="tier in tiers" :key="tier.slug" class="tier-card">
        <ion-card-header>
          <ion-card-title>{{ tier.name }}</ion-card-title>
          <ion-card-subtitle>{{ priceLabel(tier) }}</ion-card-subtitle>
        </ion-card-header>
        <ion-card-content>
          <ul class="tier-meta">
            <li v-if="tier.trial_days">
              <HubIcon name="time-outline" />
              {{ t('modulePlan.trialDays', { n: tier.trial_days }) }}
            </li>
            <li v-if="quotaLabel(tier)">
              <HubIcon name="cube-outline" />
              {{ t('modulePlan.quota', { quota: quotaLabel(tier) }) }}
            </li>
            <li v-if="tier.metered && tier.overage_price != null">
              <HubIcon name="cash-outline" />
              {{ t('modulePlan.overage', { price: fmtMoney(tier.overage_price) }) }}
            </li>
          </ul>
          <ion-button
            expand="block"
            :fill="isOwned ? 'outline' : 'solid'"
            :disabled="busy"
            @click="onPurchase(tier)"
          >
            <HubIcon :name="isOwned ? 'trending-up-outline' : 'cart-outline'" slot="start" />
            {{ isOwned ? t('modulePlan.upgrade') : t('modulePlan.buy') }}
          </ion-button>
        </ion-card-content>
      </ion-card>
    </div>
    <p v-else class="opacity-70 py-6 text-center">{{ t('modulePlan.noTiers') }}</p>

    <ion-toast
      :is-open="toastOpen"
      :message="toastMsg"
      :color="toastColor"
      :duration="3000"
      @did-dismiss="toastOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonCard, IonCardHeader, IonCardTitle, IonCardSubtitle, IonCardContent,
  IonBadge, IonButton, IonSpinner, IonToast,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import {
  cloudModuleSubscription, cloudPurchaseModule, cloudCancelModuleSubscription,
  type CloudModuleSubscription, type ModuleSubscriptionStatus,
} from '../lib/cloud';
import type { ModuleBilling, BillingTierDef } from '@erplora/module-types';
import { formatAmount } from '../lib/money';

const props = defineProps<{
  /** Slug del módulo (el Hub usa el module_id como slug; el Cloud resuelve por pk|slug|module_id). */
  moduleId: string;
  /** Bloque `billing` del manifest del módulo. */
  billing: ModuleBilling;
}>();

const { t } = useI18n();

const sub = ref<CloudModuleSubscription | null>(null);
const loadingStatus = ref(true);
const busy = ref(false);
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');

const tiers = computed<BillingTierDef[]>(() => props.billing.tiers ?? []);

// "Posee el módulo" según el estado de la suscripción: activa, en prueba o cancelada-pero-vigente.
const isOwned = computed(() => {
  const s = sub.value?.status;
  return s === 'active' || s === 'trialing' || s === 'canceled' || s === 'past_due';
});
// Cancelar solo tiene sentido sobre una suscripción viva no cancelada aún.
const canCancel = computed(() => {
  const s = sub.value?.status;
  return s === 'active' || s === 'trialing' || s === 'past_due';
});

// Estado → color del badge / etiqueta i18n.
const STATUS_COLOR: Record<ModuleSubscriptionStatus, 'success' | 'warning' | 'danger' | 'medium'> = {
  active: 'success',
  trialing: 'success',
  past_due: 'warning',
  canceled: 'warning',
  expired: 'danger',
  none: 'medium',
};
const statusColor = computed(() => (sub.value ? STATUS_COLOR[sub.value.status] : 'medium'));
const statusLabel = computed(() => {
  const s = sub.value?.status ?? 'none';
  return t(`modulePlan.status.${s}`);
});
const statusHint = computed(() => {
  const s = sub.value?.status ?? 'none';
  return t(`modulePlan.hint.${s}`);
});

function fmtDate(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}
function fmtMoney(units: number): string {
  return formatAmount(units);
}

// La cuota es un dict (p.ej. `{conversations_per_month: 30}`) — la formateamos legible. Las claves
// las define el autor del módulo (snake_case), así que solo las "humanizamos" (sin localizar): cada
// entrada → "30 conversations per month"; varias se unen con " · ". Vacío si no hay cuota.
function quotaLabel(tier: BillingTierDef): string {
  const q = tier.quota;
  if (!q || typeof q !== 'object') return '';
  return Object.entries(q)
    .map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`)
    .join(' · ');
}

function priceLabel(tier: BillingTierDef): string {
  if (!tier.price) return t('modulePlan.free');
  const amount = fmtMoney(tier.price);
  if (tier.interval === 'one_time') return amount;
  const per = tier.interval === 'year' ? t('modulePlan.perYear') : t('modulePlan.perMonth');
  return `${amount}${per}`;
}

function notify(msg: string, color: 'primary' | 'success' | 'danger'): void {
  toastMsg.value = msg;
  toastColor.value = color;
  toastOpen.value = true;
}

async function loadStatus(): Promise<void> {
  loadingStatus.value = true;
  try {
    sub.value = await cloudModuleSubscription(props.moduleId);
  } catch {
    sub.value = null;
  } finally {
    loadingStatus.value = false;
  }
}

async function onPurchase(tier: BillingTierDef): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  // Volver a ESTA pestaña tras el checkout; el panel refresca al ver `?checkout=success`.
  const base = `${window.location.origin}/m/${props.moduleId}/__plan__`;
  try {
    const res = await cloudPurchaseModule(props.moduleId, {
      tierSlug: tier.slug,
      successUrl: `${base}?checkout=success`,
      cancelUrl: `${base}?checkout=cancel`,
    });
    if (res.isFree) {
      notify(res.message || t('modulePlan.acquired'), 'success');
      await loadStatus();
    } else if (res.checkoutUrl) {
      // Checkout alojado de Stripe: redirige a la pasarela; al volver caemos en `?checkout=success`.
      window.location.assign(res.checkoutUrl);
    } else {
      notify(t('modulePlan.purchaseError'), 'danger');
    }
  } catch {
    notify(t('modulePlan.purchaseError'), 'danger');
  } finally {
    busy.value = false;
  }
}

async function onCancel(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    const res = await cloudCancelModuleSubscription(props.moduleId);
    notify(res.success ? (res.message || t('modulePlan.canceled')) : t('modulePlan.cancelError'),
      res.success ? 'primary' : 'danger');
    await loadStatus();
  } catch {
    notify(t('modulePlan.cancelError'), 'danger');
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  void loadStatus();
  // Al volver del checkout de Stripe: refresca el estado y avisa.
  const checkout = new URLSearchParams(window.location.search).get('checkout');
  if (checkout === 'success') {
    notify(t('modulePlan.checkoutSuccess'), 'success');
    void loadStatus();
  } else if (checkout === 'cancel') {
    notify(t('modulePlan.checkoutCanceled'), 'primary');
  }
});
</script>

<style scoped>
.plan-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 960px;
  margin: 0 auto;
}
.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.status-line {
  margin: 0;
}
.cancel-btn {
  margin-top: 0.75rem;
}
.tiers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}
.tier-card {
  margin: 0;
}
.tier-meta {
  list-style: none;
  margin: 0 0 1rem;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.tier-meta li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}
</style>
