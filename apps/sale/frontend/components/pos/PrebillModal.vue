<script setup lang="ts">
// «Bill», the pre-bill (SALE-F21): the check as the paper taken to the table. The business (the first
// line of the receipt header, «My business» without one), «Bill», the check's title, now, the customer;
// each line with its quantity × price, its amount, its note and «(comp)»; the ticket discount, the VAT
// breakdown and the total — all of it as `sale.checkout.preview` works it out —, and «Bill — this is
// not an invoice…». No number, no QR, no payment: it consumes nothing. The printer prints this very
// paper (`printPaper`); a failure says so. It values the check while it is mounted: the page mounts
// it only while the bill is open.
import { formatDateTime } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonModal, IonSpinner, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, useTemplateRef } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { taxRow } from '../../lib/breakdown';
import { formatMoney, formatQuantity } from '../../lib/format';
import { printPaper } from '../../lib/print';
import type { OrderLineOut, OrderOut } from '../../operations';

const props = defineProps<{ order: OrderOut; customerName: string | null; header: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const paper = useTemplateRef<HTMLElement>('paper');

const { data: valued, error, refresh } = useLive('sale.checkout.preview', () => ({ order_id: props.order.id }));

const business = computed(() => props.header.split('\n')[0]?.trim() || t('sale.pos.docDefaultBusiness'));
const now = computed(() => formatDateTime(new Date(), locale.value));

const amount = (line: OrderLineOut) =>
  `${formatQuantity(line.quantity, line.unit, locale.value)} × ${formatMoney(line.unit_price, locale.value)}`;

/** The kinds of tax the bill names in the reader's language; a component with its own name keeps it. */
const TAX_KINDS = new Set(['vat', 'surcharge', 'igic', 'ipsi']);
const taxName = (label: string) => (TAX_KINDS.has(label) ? t(`sale.pos.taxes.${label}`) : label);
/** One row per fiscal key, read as the ticket reads it (an exempt key names its cause). */
const taxes = computed(() =>
  (valued.value?.breakdown ?? []).map((row) => ({
    ...row,
    ...taxRow(row, {
      locale: locale.value,
      taxName,
      qualification: (kind: string) => t(`sale.document.qualification.${kind}`),
    }),
  })),
);

/** A comp says so after its name («Wine (comp)»). */
const lineName = (line: OrderLineOut) => (line.is_gift ? `${line.name} ${t('sale.pos.giftSuffix')}` : line.name);

function print(): void {
  if (!paper.value) return;
  try {
    printPaper(paper.value);
  } catch {
    void toastError(t('sale.pos.prebillPrintFailed'));
  }
}
</script>

<template>
  <ion-modal
    class="pos-prebill"
    :is-open="open"
    :aria-label="$t('sale.pos.prebillTitle')"
    data-testid="pos-prebill"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title data-testid="pos-prebill-title">
          {{ $t('sale.pos.prebillTitle') }}
        </ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="pos-prebill-print"
            :aria-label="$t('sale.pos.print')"
            :disabled="!valued"
            @click="print"
          >
            <HubIcon
              slot="icon-only"
              name="ion:receipt-outline"
            />
          </ion-button>
          <ion-button
            data-testid="pos-prebill-close"
            :aria-label="$t('sale.pos.close')"
            @click="open = false"
          >
            <HubIcon
              slot="icon-only"
              name="ion:close-outline"
            />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding pos-prebill__body">
      <div
        v-if="error && !valued"
        class="pos-prebill__state"
        role="alert"
        data-testid="pos-prebill-error"
      >
        <p>{{ $t('sale.pos.prebillLoadFailed') }}</p>
        <ion-button
          size="small"
          fill="outline"
          @click="refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </div>
      <div
        v-else-if="!valued"
        class="pos-prebill__state"
        data-testid="pos-prebill-loading"
      >
        <ion-spinner />
        <p>{{ $t('sale.pos.prebillLoading') }}</p>
      </div>
      <article
        v-else
        ref="paper"
        class="pos-bill"
        data-testid="pos-prebill-paper"
      >
        <header class="pos-bill__head">
          <strong class="pos-bill__business">{{ business }}</strong>
          <span class="pos-bill__kind">{{ $t('sale.pos.prebillTitle') }}</span>
          <span
            v-if="order.label"
            class="pos-bill__label"
          >{{ order.label }}</span>
          <span class="pos-bill__date">{{ now }}</span>
          <span
            v-if="customerName"
            class="pos-bill__customer"
          >{{ $t('sale.pos.docCustomer') }}: {{ customerName }}</span>
        </header>
        <ul class="pos-bill__lines">
          <li
            v-for="line in order.lines"
            :key="line.id"
            class="pos-bill__line"
          >
            <span class="pos-bill__name">{{ lineName(line) }}</span>
            <span class="pos-bill__qty">{{ amount(line) }}</span>
            <span class="pos-bill__amount">{{ formatMoney(line.line_total, locale) }}</span>
            <span
              v-if="line.notes"
              class="pos-bill__note"
            >{{ line.notes }}</span>
          </li>
        </ul>
        <dl class="pos-bill__sums">
          <div
            v-if="valued.ticket_discount_amount > 0"
            class="pos-bill__row pos-bill__discount"
          >
            <dt>{{ $t('sale.pos.docDiscount') }}</dt>
            <dd>−{{ formatMoney(valued.ticket_discount_amount, locale) }}</dd>
          </div>
          <div class="pos-bill__row">
            <dt>{{ $t('sale.pos.docSubtotal') }}</dt>
            <dd>{{ formatMoney(valued.subtotal, locale) }}</dd>
          </div>
          <div
            v-for="row in taxes"
            :key="row.key"
            class="pos-bill__row pos-bill__tax"
          >
            <dt>{{ row.label }}</dt>
            <dd>
              <span>{{ formatMoney(row.base, locale) }}</span>
              <span>{{ formatMoney(row.tax, locale) }}</span>
            </dd>
          </div>
          <div class="pos-bill__row pos-bill__total">
            <dt>{{ $t('sale.pos.total') }}</dt>
            <dd>{{ formatMoney(valued.total, locale) }}</dd>
          </div>
        </dl>
        <p class="pos-bill__notice">
          {{ $t('sale.pos.prebillNotice') }}
        </p>
      </article>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.pos-prebill__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  padding: 2rem 1rem;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-bill {
  max-width: 22rem;
  margin: 0 auto;
  padding: 1rem;
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  font-size: 0.85rem;
  color: #111;
  background: #fff;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 6px;
}
.pos-bill__head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  margin-bottom: 0.8rem;
  text-align: center;
}
.pos-bill__business {
  font-size: 1rem;
}
.pos-bill__kind {
  font-weight: 700;
  text-transform: uppercase;
}
.pos-bill__lines {
  margin: 0;
  padding: 0.5rem 0;
  list-style: none;
  border-block: 1px dashed #999;
}
.pos-bill__line {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0 0.5rem;
  padding: 0.2rem 0;
}
.pos-bill__qty {
  grid-column: 1;
  color: #555;
}
.pos-bill__amount {
  grid-row: 1;
  grid-column: 2;
  font-weight: 700;
}
.pos-bill__note {
  grid-column: 1 / -1;
  font-style: italic;
  color: #555;
}
.pos-bill__sums {
  margin: 0.5rem 0;
}
.pos-bill__row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
.pos-bill__row dt,
.pos-bill__row dd {
  margin: 0;
}
.pos-bill__tax dd {
  display: flex;
  gap: 0.8rem;
}
.pos-bill__total {
  margin-top: 0.3rem;
  font-size: 1.1rem;
  font-weight: 800;
}
.pos-bill__notice {
  margin: 0.8rem 0 0;
  font-size: 0.78rem;
  text-align: center;
}
</style>

<style>
ion-modal.pos-prebill {
  --width: min(94vw, 30rem);
  --height: min(90vh, 44rem);
  --border-radius: 16px;
}
@media (max-width: 820px) {
  ion-modal.pos-prebill {
    --width: 100%;
    --height: 100%;
    --border-radius: 0;
  }
}
</style>
