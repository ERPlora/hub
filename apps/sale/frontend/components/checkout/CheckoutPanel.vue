<script setup lang="ts">
// What the charge sheet holds (WORKBOOK «Pantallas · Cobro», the old `.pay-sheet`): the head, the
// amount to charge, big (the server's: `sale.checkout.preview`, never the screen's arithmetic), «Paying
// N lines of <total>» for part of a check and «Remaining» while splitting; what the sale is (CheckoutSide)
// and how it is paid (CheckoutTender); the foot with «Charge». Mounted once per opening of the sheet:
// the attempt key is born here (useCheckout) and nothing is read while the sheet is closed.
// What decides is the server's: the total, the cash limit and the ticket limit (preview), the methods
// that may charge (`allowed`), the default document (`sale.pos_settings.get`); the client only adds up
// what the person types, and the server re-checks it all when charging.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, toast } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import { useCheckout } from '../../composables/checkout/useCheckout';
import { useTender } from '../../composables/checkout/useTender';
import { useLocale, useT } from '../../composables/useT';
import { type ChargeBlock, chargeBlock } from '../../lib/checkout/blocks';
import { chargeableMethods } from '../../lib/checkout/methods';
import { recipientComplete, recipientFrom, recipientPayload } from '../../lib/checkout/recipient';
import { formatMoney } from '../../lib/format';
import type { DocumentType, PaymentMethodOut, PreviewIn, SaleOut } from '../../operations';
import CheckoutFoot from './CheckoutFoot.vue';
import CheckoutSide from './CheckoutSide.vue';
import CheckoutTender from './CheckoutTender.vue';

const props = defineProps<{
  orderId: string;
  /** The lines marked to pay on their own; empty = the whole check. */
  lineIds: readonly string[];
  orderVersion: number;
  customer: CustomerSnapshot | null;
  staffId: string | null;
}>();

const emit = defineEmits<{ charged: [sale: SaleOut]; close: []; busy: [busy: boolean] }>();

/** Methods are a handful; one page holds them all. */
const METHODS_PAGE = 100;
const SALES_PATH = '/sale/sales';

const t = useT();
const locale = useLocale();
const router = useRouter();
const money = (cents: number | null | undefined): string => formatMoney(cents, locale.value);

// ── What the server says ──────────────────────────────────────────────────────────────────────
const partial = computed(() => props.lineIds.length > 0);
const previewParams = computed<PreviewIn>(() =>
  partial.value ? { order_id: props.orderId, line_ids: [...props.lineIds] } : { order_id: props.orderId },
);
const preview = useLive('sale.checkout.preview', previewParams);
/** The whole check, for «Paying N lines of <total>» (the same subscription as above when nothing is marked). */
const whole = useLive('sale.checkout.preview', () => ({ order_id: props.orderId }));
const methodPage = useLive('sale.payment_method.list', { limit: METHODS_PAGE });
const settings = useLive('sale.pos_settings.get', {});

const reads = [preview, whole, methodPage, settings];
const readError = computed(() => reads.map((read) => read.error.value).find(Boolean) ?? null);
const reconnecting = computed(() => reads.some((read) => read.status.value === 'reconnecting'));

/** The amount to charge; `undefined` until the server has worked it out. */
const total = computed(() => (preview.status.value === 'loading' ? undefined : preview.data.value?.total));
const cashLimit = computed(() => preview.data.value?.cash_limit ?? null);
const ticketLimit = computed(() => preview.data.value?.ticket_limit ?? null);
const methodsLoaded = computed(() => methodPage.status.value !== 'loading' || methodPage.data.value !== undefined);
const methods = computed<PaymentMethodOut[]>(() => chargeableMethods(methodPage.data.value?.rows ?? []));

const partialText = computed(() => {
  const wholeTotal = whole.data.value?.total;
  if (!partial.value || wholeTotal === undefined || whole.status.value === 'loading') return '';
  const n = props.lineIds.length;
  return n === 1 ? t('sale.checkout.payingPartOne', { total: money(wholeTotal) }) : t('sale.checkout.payingPart', { n, total: money(wholeTotal) });
});

// ── What the person chooses and types ─────────────────────────────────────────────────────────
const tender = useTender({ total, methods, cashLimit });

const recipient = ref(recipientFrom(props.customer));
const complete = computed(() => recipientComplete(recipient.value));
const chosenDocument = shallowRef<DocumentType | null>(null);
const overLimit = computed(() => ticketLimit.value !== null && total.value !== undefined && total.value > ticketLimit.value);
const defaultDocument = computed<DocumentType>(() => {
  const current = settings.data.value;
  if (current?.default_document_type === 'invoice') return 'invoice';
  return current?.auto_invoice_with_tax_id && props.customer?.customer_tax_id.trim() ? 'invoice' : 'ticket';
});
/** Above the ticket limit the law decides: an invoice. */
const documentType = computed<DocumentType>({
  get: () => (overLimit.value ? 'invoice' : (chosenDocument.value ?? defaultDocument.value)),
  set: (next) => (chosenDocument.value = next),
});
/** The side group unfolded on a phone; what has to be answered opens it. */
const sideOpen = shallowRef(false);
const needsRecipient = computed(() => documentType.value === 'invoice' && !complete.value);
watch(needsRecipient, (needed) => needed && (sideOpen.value = true), { immediate: true });

const block = computed<ChargeBlock | null>(() =>
  total.value === undefined
    ? null
    : chargeBlock({
        requireCustomer: !!settings.data.value?.require_customer,
        hasCustomer: !!props.customer,
        documentType: documentType.value,
        recipientComplete: complete.value,
        total: total.value,
        cashLimit: cashLimit.value,
        method: tender.method.value,
        typed: tender.typed.value,
        splitting: tender.splitting.value,
        legs: tender.legs.value,
      }),
);
const ready = computed(
  () => total.value !== undefined && !readError.value && methodsLoaded.value && (methods.value.length > 0 || total.value === 0),
);

// ── Charging ──────────────────────────────────────────────────────────────────────────────────
const checkout = useCheckout({ onCharged: (sale) => emit('charged', sale) });
watch(checkout.busy, (busy) => emit('busy', busy));

function pick(method: PaymentMethodOut): void {
  if (!tender.pick(method)) void toast(t('sale.checkout.cashLimitReason', { amount: money(cashLimit.value) }), 'warning');
}

function onBlocked(reason: ChargeBlock, message: string): void {
  void toast(message, 'warning');
  if (reason.kind === 'recipient') sideOpen.value = true;
}

function confirm(): void {
  void checkout.charge({
    order_id: props.orderId,
    ...(partial.value ? { line_ids: [...props.lineIds] } : {}),
    order_version: props.orderVersion,
    payments: tender.payments(),
    document_type: documentType.value,
    ...(props.customer ? { customer_id: props.customer.customer_id } : {}),
    ...recipientPayload(recipient.value),
    staff_id: props.staffId,
  });
}

function checkSales(): void {
  void router.push(SALES_PATH);
  emit('close');
}
</script>

<template>
  <div
    class="sale-checkout"
    data-testid="sale-checkout"
  >
    <div class="sheet-h">
      <h2
        class="sheet-h__title"
        data-testid="sale-checkout-title"
      >
        {{ $t('sale.checkout.title') }}
      </h2>
      <ion-button
        fill="clear"
        color="medium"
        class="sheet-h__close"
        data-testid="sale-checkout-close"
        :aria-label="$t('sale.checkout.close')"
        :disabled="checkout.busy.value"
        @click="emit('close')"
      >
        <HubIcon
          slot="icon-only"
          name="ion:close"
        />
      </ion-button>
    </div>
    <div class="sheet-top">
      <InlineFeedback
        v-if="readError"
        tone="danger"
        data-testid="sale-checkout-read-error"
      >
        {{ readError.message }}
        <template #actions>
          <ion-button
            fill="clear"
            size="small"
            data-testid="sale-checkout-retry"
            @click="preview.refresh()"
          >
            {{ $t('sale.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <p
        v-else-if="reconnecting"
        class="pay-note"
        role="status"
      >
        {{ $t('sale.live.reconnecting') }}
      </p>
      <div
        class="pay-total"
        data-testid="sale-checkout-total"
        aria-live="polite"
      >
        <template v-if="total !== undefined">
          {{ money(total) }}
        </template>
        <span
          v-else
          class="pay-total__loading"
        >
          <ion-spinner
            name="crescent"
            aria-hidden="true"
          />
          {{ $t('sale.checkout.loadingTotal') }}
        </span>
      </div>
      <div
        v-if="partialText"
        class="pay-part"
        data-testid="sale-checkout-partial"
      >
        {{ partialText }}
      </div>
      <div
        v-if="tender.splitting.value"
        class="pay-remaining"
        data-testid="sale-checkout-remaining"
        aria-live="polite"
        :data-covered="tender.remaining.value === 0 ? 'true' : undefined"
      >
        <span>{{ $t('sale.checkout.remaining') }}</span>
        <span class="pay-remaining__value">{{ money(tender.remaining.value) }}</span>
      </div>
    </div>
    <div class="pay">
      <CheckoutSide
        v-model:document="documentType"
        v-model:recipient="recipient"
        v-model:open="sideOpen"
        class="pay-side"
        :over-limit="overLimit"
        :ticket-limit="ticketLimit"
      />
      <div class="pay-tender">
        <p
          v-if="!methodsLoaded"
          class="pay-note"
          data-testid="sale-checkout-methods-loading"
        >
          <ion-spinner
            name="crescent"
            aria-hidden="true"
          />
          {{ $t('sale.checkout.loadingMethods') }}
        </p>
        <p
          v-else-if="!methods.length"
          class="pay-note"
          data-testid="sale-checkout-no-methods"
        >
          {{ $t('sale.checkout.noMethods') }}
        </p>
        <CheckoutTender
          v-else-if="total !== undefined"
          :methods="methods"
          :method="tender.method.value"
          :cash-off="tender.cashOff.value"
          :splitting="tender.splitting.value"
          :legs="tender.legs.value"
          :typed="tender.typed.value"
          :change="tender.change.value"
          :total="total"
          :remaining="tender.remaining.value"
          @pick="pick"
          @key="tender.press"
          @split="tender.startSplit"
          @add="tender.addLeg"
          @edit="tender.editLeg"
          @remove="tender.removeLeg"
        />
      </div>
    </div>
    <CheckoutFoot
      class="sheet-foot"
      :total="total"
      :method="tender.method.value"
      :split="tender.splitting.value || tender.legs.value.length > 0"
      :block="block"
      :busy="checkout.busy.value"
      :ready="ready"
      :failure="checkout.failure.value"
      @confirm="confirm"
      @blocked="onBlocked"
      @check-sales="checkSales"
    />
  </div>
</template>

<style scoped>
/* One column on a phone: head, figure, then what scrolls (the side group folded above the tender), and
   the foot stuck to the bottom so «Charge» never needs a scroll. */
.sale-checkout {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--ion-background-color, #fff);
  color: var(--ion-text-color, #1c1b18);
}

.sheet-h,
.sheet-top {
  flex: none;
  padding: 0 1rem;
}

.sheet-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.4rem;
  padding-top: 0.6rem;
}

.sheet-h__title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
}

.sheet-h__close {
  margin: 0;
  font-size: 1.1rem;
}

.pay-total {
  margin: 0.2rem 0 1rem;
  font-size: 2.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  text-align: center;
}

.pay-total__loading {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium, #8b897f);
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0;
}

.pay-part {
  margin: -0.6rem 0 0.9rem;
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.9rem;
  text-align: center;
}

/* The remaining, out of the scroll: the figure looked at on every leg; accent while something is left,
   success once covered. */
.pay-remaining {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin: -0.6rem 0 0.9rem;
  padding: 0.5rem 0.7rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 0.7rem;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.9rem;
  font-weight: 600;
}

.pay-remaining__value {
  color: var(--ion-color-primary, #0091ce);
  font-size: 1.35rem;
  font-weight: 800;
}

.pay-remaining[data-covered] {
  border-color: var(--ion-color-success, #2dd36f);
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 10%, transparent);
}

.pay-remaining[data-covered] .pay-remaining__value {
  color: var(--ion-color-success, #2dd36f);
}

.pay-note {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.6rem;
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.9rem;
}

.pay {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.8rem;
  min-height: 8rem;
  padding: 0 1rem 0.75rem;
}

.sheet-foot {
  position: sticky;
  bottom: 0;
  z-index: 1;
  flex: none;
  padding: 0.75rem 1rem calc(1rem + var(--ion-safe-area-bottom, 0px));
  border-top: 1px solid var(--ion-border-color, #e6e3db);
  background: var(--ion-background-color, #fff);
}

/* From 821 px, two columns as on Square or Shopify POS: the figure and what the sale is on the left, the
   method, the amount and the keypad on the right, from the figure down to the foot. Each column scrolls
   on its own; `.pay` steps aside so its two groups are the grid's items. */
@media (min-width: 821px) {
  .sale-checkout {
    display: grid;
    grid-template-areas:
      'head head'
      'top tender'
      'side tender'
      'foot foot';
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    overflow: hidden;
  }

  .sheet-h {
    grid-area: head;
  }

  .sheet-top {
    grid-area: top;
  }

  .pay {
    display: contents;
  }

  .pay-side {
    grid-area: side;
    min-height: 0;
    overflow: auto;
    padding: 0 1rem 0.75rem;
  }

  .pay-tender {
    grid-area: tender;
    min-height: 0;
    overflow: auto;
    padding: 0 1rem 0.75rem;
    border-left: 1px solid var(--ion-border-color, #e6e3db);
  }

  .sheet-foot {
    grid-area: foot;
    position: static;
  }
}
</style>
