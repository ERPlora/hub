<!--
  ModulePlanPanel — panel del SHELL (no un Web Component de módulo) que se renderiza en la pestaña
  sintética "Plan" de la navegación de un módulo (ver ModuleView). Pinta los tiers del manifest
  (`billing.tiers`) y el estado de suscripción actual (cloudModuleSubscription, JWT del usuario +
  X-Hub-Id).

  El Hub NO vende, y desde hub#479 tampoco LLEVA a vender: los CTAs comprar/mejorar/cancelar abrían
  un deep-link a la página del módulo en el SaaS —donde vive el checkout— y eso es exactamente el
  steering que rechazan Google Play y Microsoft Store. Ya no existen. El panel MUESTRA: el estado de
  la suscripción y qué tiers declara el manifest. Contratar o cambiar de tier se hace en erplora.com,
  que es el único sitio donde ERPlora vende.

  El botón "comprobar" se queda, y ahora es el que importa: quien contrate desde el navegador vuelve
  aquí y refresca el estado (además del recheck-on-focus, que sigue).

  El Cloud NO expone el slug del tier actual (ni module-subscription ni check_ownership lo traen),
  así que en v1 NO se resalta un tier concreto: se muestra solo el `status` global.

  ## Por qué aquí no hay una tarjeta propia (hub#1605)

  El panel pintaba sus tiers con `ion-card` + `ion-card-header` y una rejilla propia. Dos costes,
  medidos sobre el hub real:

  - `ion-card-header` y `ion-badge` son Shadow DOM y su padding vive en `:host`. El `padding: 0`
    del preflight de Tailwind es una regla del DOCUMENTO, y esa gana siempre a `:host`, así que
    títulos y badge quedaban pegados al borde mientras el cuerpo iba sangrado. Las pantallas que se
    ven bien (Perfil) lo pagan escribiendo su propio padding a mano.
  - Este panel se inyecta para cada módulo que declara `billing`, así que un defecto aquí no es una
    pantalla: es una por cada módulo de pago.

  OutfitKit ya trae las dos piezas —`ok-pricing-card` y `ok-status-pill`— y ambas llevan su padding
  dentro de su propio shadow root, donde el preflight no llega. Reutilizar antes que crear.
-->
<template>
  <div class="plan-panel">
    <!-- Estado de la suscripción. `ok-inline-feedback` es la pieza que el shell ya usa para un
         bloque con título, cuerpo y acciones (BillingPage, SetupBlockingStrip). -->
    <ok-inline-feedback :tone="statusTone" :icon="statusIcon" :heading="t('modulePlan.statusTitle')">
      <div v-if="loadingStatus" class="flex items-center gap-2 opacity-70">
        <ion-spinner name="crescent" /> {{ t('modulePlan.loadingStatus') }}
      </div>
      <template v-else>
        <ok-status-pill :tone="statusTone" :label="statusLabel" size="sm" />
        <p v-if="sub && sub.status === 'trialing' && sub.trialEnd" class="status-line">
          {{ t('modulePlan.trialEnds', { date: fmtDate(sub.trialEnd) }) }}
        </p>
        <p
          v-else-if="sub && sub.periodEnd && (sub.status === 'active' || sub.status === 'canceled')"
          class="status-line"
        >
          {{ sub.status === 'canceled'
            ? t('modulePlan.cancelsOn', { date: fmtDate(sub.periodEnd) })
            : t('modulePlan.renewsOn', { date: fmtDate(sub.periodEnd) }) }}
        </p>
        <p v-else class="status-line opacity-70">{{ statusHint }}</p>

        <!-- Dónde se gestiona. Frase, no enlace: la página del módulo en el SaaS tiene checkout y
             llevar ahí desde dentro de la app es steering (hub#479). El enlace a la página de
             CUENTA —que sí valdría— espera a que exista en el SaaS: ERPlora/saas#1901 y hub#1608. -->
        <p class="status-line opacity-70">{{ t('modulePlan.managedInAccount') }}</p>
      </template>
      <!-- Re-consulta manual: "ya lo he contratado" (además del recheck-on-focus). -->
      <ion-button
        slot="actions"
        size="small"
        fill="outline"
        :disabled="loadingStatus"
        @click="onCheckPurchase"
      >
        <HubIcon name="refresh-outline" slot="start" />
        {{ t('modulePlan.checkPurchase') }}
      </ion-button>
    </ok-inline-feedback>

    <!-- Tiers del manifest: rejilla de Ionic, tarjeta de OutfitKit. Aquí vivía el botón
         «Comprar»/«Mejorar» que abría el checkout del SaaS; los tiers se siguen VIENDO —qué incluye
         cada uno y qué cuesta es información, no un camino al pago—, pero desde el hub no se
         contrata. -->
    <ion-grid v-if="tiers.length" class="ion-no-padding">
      <ion-row>
        <ion-col v-for="tier in tiers" :key="tier.slug" size="12" size-md="6" size-lg="3">
          <ok-pricing-card
            :name="tier.name"
            :price="priceLabel(tier)"
            :period="periodLabel(tier)"
            :features.prop="tierFeatures(tier)"
          />
        </ion-col>
      </ion-row>
    </ion-grid>
    <ok-empty-state v-else icon="pricetag-outline" :heading="t('modulePlan.noTiers')" />

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
import { IonButton, IonCol, IonGrid, IonRow, IonSpinner, IonToast } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import {
  cloudModuleSubscription,
  type CloudModuleSubscription, type ModuleSubscriptionStatus,
} from '../lib/cloud';
import type { ModuleBilling, BillingTierDef } from '@erplora/module-types';
import { formatAmount } from '../lib/money';
import { formatDate } from '../lib/format-datetime';

const props = defineProps<{
  /** Slug del módulo (el Hub usa el module_id como slug; el Cloud resuelve por pk|slug|module_id). */
  moduleId: string;
  /** Bloque `billing` del manifest del módulo. */
  billing: ModuleBilling;
}>();

const { t, locale } = useI18n();

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
// `canCancel` gateaba el botón «Cancelar», retirado con el resto de controles que aterrizaban en el
// checkout (hub#479). Cancelar sigue siendo posible: en erplora.com.

/** Tono compartido por el bloque y la píldora: el vocabulario de OutfitKit, no los colores de Ionic. */
type Tone = 'success' | 'warning' | 'danger' | 'neutral';
const STATUS_TONE: Record<ModuleSubscriptionStatus, Tone> = {
  active: 'success',
  trialing: 'success',
  past_due: 'warning',
  canceled: 'warning',
  expired: 'danger',
  // No tener plan no es un fallo, así que no toma un tono de alarma.
  none: 'neutral',
};
const STATUS_ICON: Record<Tone, string> = {
  success: 'checkmark-circle-outline',
  warning: 'alert-circle-outline',
  danger: 'close-circle-outline',
  neutral: 'pricetag-outline',
};
const statusTone = computed<Tone>(() => (sub.value ? STATUS_TONE[sub.value.status] : 'neutral'));
const statusIcon = computed(() => STATUS_ICON[statusTone.value]);
const statusLabel = computed(() => {
  const s = sub.value?.status ?? 'none';
  return t(`modulePlan.status.${s}`);
});
const statusHint = computed(() => {
  const s = sub.value?.status ?? 'none';
  return t(`modulePlan.hint.${s}`);
});

function fmtDate(iso: string): string {
  // #273 — locale de la app (vue-i18n), no del navegador (mezclaba idiomas).
  // hub#1212 — y el huso del NEGOCIO, no el del navegador.
  return formatDate(iso, { locale: locale.value, day: '2-digit', month: 'short', year: 'numeric' }) ?? '—';
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

/** El importe. El periodo viaja aparte para que la tarjeta pueda componerlo a su manera. */
function priceLabel(tier: BillingTierDef): string {
  if (!tier.price) return t('modulePlan.free');
  return fmtMoney(tier.price);
}

/** «/mes», «/año» — vacío para un pago único y para el gratuito, que no repiten. */
function periodLabel(tier: BillingTierDef): string {
  if (!tier.price || tier.interval === 'one_time') return '';
  return tier.interval === 'year' ? t('modulePlan.perYear') : t('modulePlan.perMonth');
}

/** Lo que incluye el tier, en la lista que pinta `ok-pricing-card`. */
function tierFeatures(tier: BillingTierDef): string[] {
  const out: string[] = [];
  if (tier.trial_days) out.push(t('modulePlan.trialDays', { n: tier.trial_days }));
  const quota = quotaLabel(tier);
  if (quota) out.push(t('modulePlan.quota', { quota }));
  if (tier.metered && tier.overage_price != null) {
    out.push(t('modulePlan.overage', { price: fmtMoney(tier.overage_price) }));
  }
  return out;
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

// Aquí vivía `deepLink` —la página del módulo en el SaaS, con el checkout de Stripe— y los dos
// controles que la abrían, `onPurchase()` y `onCancel()`. Los tres se fueron con hub#479: una
// dirección construida aquí para llevar al pago es steering la construya quien la construya, y esa
// es la causa de rechazo que había que quitar de en medio antes de subir la app a las tiendas.

/** Botón "ya lo he contratado — comprobar": re-consulta y avisa si el plan ya está activo. */
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
/* Fluido como el resto de superficies del shell: el único límite horizontal es el gutter de la
   página (hub#1605). Lo demás lo ponen los componentes. */
.plan-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.status-line {
  margin: 0;
}
</style>
