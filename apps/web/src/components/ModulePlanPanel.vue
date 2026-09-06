<!--
  ModulePlanPanel — panel del SHELL (no un Web Component de módulo) que se renderiza en la pestaña
  sintética "Plan" de la navegación de un módulo (ver ModuleView). Pinta los tiers del manifest
  (`billing.tiers`) y el estado de suscripción actual (cloudModuleSubscription, JWT del usuario +
  X-Hub-Id).

  El Hub NO vende: los CTAs «comprar»/«mejorar» que abrían la FICHA DEL MARKETPLACE se fueron con
  hub#479 y no vuelven — esa es la superficie promocional, y enlazarla desde dentro de la app es el
  steering que rechazan Google Play y Microsoft Store.

  Lo que sí hay desde hub#1608 es «Gestionar plan», que aterriza en la CUENTA del cliente
  (`/dashboard/hubs/<id>/modules/<slug>/plan/`, ERPlora/saas#1901). Es la misma línea que ya cruzó
  el menú lateral con el plan del hub: gestión de lo que el cliente tiene, etiqueta neutra, y
  oculto donde el revisor de Play lo leería como steering. Contratar y pagar sigue ocurriendo en
  erplora.com, en el navegador.

  El botón "comprobar" se queda: quien contrate desde el navegador vuelve aquí y refresca el estado
  (además del recheck-on-focus, que sigue), y es el único control donde el enlace no se ofrece.

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

        <!-- Dónde se gestiona. La frase se queda aunque ahora haya botón: en Google Play el botón
             no se ofrece (hub#756) y sin esta línea ahí no quedaría dicho dónde se hace. -->
        <p class="status-line opacity-70">{{ t('modulePlan.managedInAccount') }}</p>
      </template>
      <!-- Gestión del plan, en la CUENTA del cliente (hub#1608). No es la ficha del marketplace
           —esa es la superficie promocional que el guardia anti-steering prohíbe nombrar
           (hub#479)—, sino la página que abrió ERPlora/saas#1901, con el hub y el módulo en la
           ruta: por eso aquí no hay la ambigüedad del enlace del menú lateral, que no dice si el
           plan es el del hub o el del módulo. Se oculta donde el revisor de Play lo leería como
           steering, con el mismo gate que el menú (hub#756). -->
      <ion-button
        v-if="canOfferPlanManagement"
        slot="actions"
        size="small"
        data-testid="module-manage-plan"
        @click="onManagePlan"
      >
        <HubIcon name="open-outline" slot="start" />
        {{ t('modulePlan.managePlan') }}
      </ion-button>
      <!-- Re-consulta manual: "ya lo he contratado" (además del recheck-on-focus). Se queda
           SIEMPRE, también donde el enlace no se ofrece: quien contrató en el navegador necesita
           poder refrescar. -->
      <ion-button
        slot="actions"
        size="small"
        fill="outline"
        data-testid="module-check-purchase"
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
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
import { getDeviceContext } from '../lib/device';
import { openExternal } from '../lib/open-external';
import { saasDoor } from '../lib/saas-door';
import { planUpgradeIsOfferable } from '../lib/upgrade-plan-link';
import { loadModuleLocale } from '../lib/module-loader';
import { modulePlanPath, modulePlanUrl } from '../lib/module-plan-link';
import { moduleBase } from '../lib/module-url';
import { quotaLabel as tierQuotaLabel, type ModuleBillingLocale } from '../lib/module-quota';

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

/** Bloque `billing` de `locales/<lang>.json` del módulo. `undefined` = el módulo no traduce. */
const billingLocale = ref<ModuleBillingLocale | undefined>(undefined);

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

// La cuota es un dict (p.ej. `{conversations_per_month: 30}`). Las claves las define el autor del
// módulo (snake_case) y ANTES solo se "humanizaban", sin localizar: un hub en español leía «Incluye
// 30 conversations per month», media frase traducida y media no (hub#1604). Ahora el rótulo de cada
// métrica sale de `locales/<lang>.json` del propio módulo —igual que los campos de la pantalla de
// ajustes (hub#1094)— y el inglés canónico es el respaldo. Detalle en `lib/module-quota.ts`.
function quotaLabel(tier: BillingTierDef): string {
  return tierQuotaLabel(tier, billingLocale.value);
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

/**
 * Traducciones del módulo para el idioma en pantalla (hub#1604).
 *
 * Base SIN versionar, igual que en la pantalla de ajustes: el runtime marca los assets sin versionar
 * «revalida siempre», y actualizar un módulo recarga la página entera (`reloadForModuleUpdate`).
 * Un módulo que no traiga el fichero deja `undefined` y la cuota cae al inglés del manifest.
 */
async function refreshLocale(): Promise<void> {
  const file = await loadModuleLocale(moduleBase(props.moduleId), locale.value);
  billingLocale.value = file?.billing;
}

// ¿Se le ofrece el enlace a la copia que tiene delante el usuario? Mismo corte que el menú
// lateral (`planUpgradeIsOfferable`, hub#756): manda la DISTRIBUCIÓN, no el sistema operativo, y
// sin señal se ofrece. El razonamiento entero vive en `upgrade-plan-link.ts`.
const canOfferPlanManagement = ref(true);

/** Abre la gestión del plan de este módulo en la cuenta del cliente. */
async function onManagePlan(): Promise<void> {
  try {
    const path = modulePlanPath(props.moduleId);
    await openExternal(await saasDoor(path, modulePlanUrl(props.moduleId), 'module-plan'));
  } catch {
    notify(t('modulePlan.managePlanError'), 'danger');
  }
}

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

watch(locale, () => void refreshLocale());

onMounted(async () => {
  void loadStatus();
  void refreshLocale();
  const context = await getDeviceContext();
  canOfferPlanManagement.value = planUpgradeIsOfferable(context?.distribution);
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
