<!--
  ModulePlanPanel — panel del SHELL (no un Web Component de módulo) que se renderiza en la pestaña
  sintética "Plan" de la navegación de un módulo (ver ModuleView). Pinta los tiers del manifest
  (`billing.tiers`) y el estado de suscripción actual (cloudModuleSubscription, JWT del usuario +
  X-Hub-Id).

  El Hub NO vende (decisión Fase 4): los CTAs comprar/mejorar/cancelar abren un DEEP-LINK a la
  página del módulo en el SaaS (navegador externo vía openExternal), donde vive el checkout y la
  gestión de la suscripción. Al recuperar foco/visibilidad —o con el botón "comprobar"— el panel
  re-consulta la suscripción para reflejar la compra hecha en el navegador.

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

          <!-- La compra/gestión ocurre en el navegador (SaaS); aquí solo se refleja el estado. -->
          <p class="status-line opacity-70">{{ t('modulePlan.opensInBrowser') }}</p>
          <div class="status-actions">
            <!-- Re-consulta manual: "he completado la compra" (además del recheck-on-focus). -->
            <ion-button size="small" fill="outline" :disabled="loadingStatus" @click="onCheckPurchase">
              <HubIcon name="refresh-outline" slot="start" />
              {{ t('modulePlan.checkPurchase') }}
            </ion-button>
            <!-- Cancelar: la gestión vive en el SaaS → mismo deep-link que la compra. -->
            <ion-button
              v-if="canCancel"
              fill="outline"
              color="danger"
              size="small"
              @click="onCancel"
            >
              <HubIcon name="close-outline" slot="start" />
              {{ t('modulePlan.cancel') }}
            </ion-button>
          </div>
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
            @click="onPurchase"
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
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonCard, IonCardHeader, IonCardTitle, IonCardSubtitle, IonCardContent,
  IonBadge, IonButton, IonSpinner, IonToast,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import {
  cloudModuleSubscription,
  type CloudModuleSubscription, type ModuleSubscriptionStatus,
} from '../lib/cloud';
import type { ModuleBilling, BillingTierDef } from '@erplora/module-types';
import { formatAmount } from '../lib/money';
import { openExternal } from '../lib/open-external';
import { config } from '../lib/config';

const props = defineProps<{
  /** Slug del módulo (el Hub usa el module_id como slug; el Cloud resuelve por pk|slug|module_id). */
  moduleId: string;
  /** Bloque `billing` del manifest del módulo. */
  billing: ModuleBilling;
}>();

const { t } = useI18n();

const sub = ref<CloudModuleSubscription | null>(null);
const loadingStatus = ref(true);
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

// Deep-link a la página del módulo en el SaaS. El Hub NO vende: la compra, el upgrade y la
// cancelación viven ahí (checkout de Stripe incluido). `hub` identifica este hub en el SaaS
// (config.hubId lo resuelve el boot desde `GET /api/hub/context`, ver lib/runtime.ts).
const deepLink = computed(() =>
  `${config.cloudApiUrl}/dashboard/marketplace/modules/${encodeURIComponent(props.moduleId)}/?hub=${encodeURIComponent(config.hubId)}&utm_source=hub`);

async function onPurchase(): Promise<void> {
  // Abre el navegador externo; al volver el foco a esta vista, el recheck refleja la compra.
  try {
    await openExternal(deepLink.value);
  } catch {
    notify(t('modulePlan.purchaseError'), 'danger');
  }
}

async function onCancel(): Promise<void> {
  // La gestión de la suscripción vive en el SaaS: mismo deep-link que la compra.
  try {
    await openExternal(deepLink.value);
  } catch {
    notify(t('modulePlan.cancelError'), 'danger');
  }
}

/** Botón "He completado la compra — comprobar": re-consulta y avisa si el plan ya está activo. */
async function onCheckPurchase(): Promise<void> {
  await loadStatus();
  if (isOwned.value) notify(t('modulePlan.purchaseDetected'), 'success');
}

// Recheck-on-focus: la compra ocurre en OTRA pestaña/navegador. Al recuperar el foco o la
// visibilidad, re-consultamos la suscripción para reflejar el nuevo estado sin recargar.
function onFocusRecheck(): void {
  if (document.visibilityState === 'visible') void loadStatus();
}

onMounted(() => {
  void loadStatus();
  window.addEventListener('focus', onFocusRecheck);
  document.addEventListener('visibilitychange', onFocusRecheck);
});

onUnmounted(() => {
  window.removeEventListener('focus', onFocusRecheck);
  document.removeEventListener('visibilitychange', onFocusRecheck);
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
.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
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
