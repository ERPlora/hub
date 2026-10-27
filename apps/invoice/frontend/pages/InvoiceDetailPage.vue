<script setup lang="ts">
// The open invoice (INVOICE-F17, F18, F19, F05, F08; the old detail of `erp-invoice-list`, now its own page
// with Back to the list): «Invoice <number>» with its status, «Print / PDF» and «Back»; the warning of a full
// invoice without the customer's tax ID; Type, Series, Issue date (and Operation date when it differs),
// Customer, Customer tax ID, Address, Issuer, Source, Sale, Rectifies / Replaces / Replaced by / Rectifying
// invoices (each opens), Paid on and Notes (a rectifying invoice's note says what it rectifies and why, in
// the reader's language); the lines, the breakdown and the totals; «Mark as paid», «Rectify» and «Full
// invoice» where they apply and for whoever may, a refusal said right above them. «Print / PDF» asks the
// printing queue first (`invoice.invoice.print`, PRINTING-F08): queued for the system printer, a toast names
// it; not queued (Printing off, no system printer) or the queue out of reach, the browser prints the A4
// paper (a document of a sale is a copy: its original was the till's paper). With VeriFactu on and its records
// readable, it follows the invoice's record too (`verifactu.record.by_invoice`, VERIFACTU-F19, by name: Invoicing
// does not require VeriFactu): the «VeriFactu receipt» card under the invoice and the record's QR on the screen's
// paper, which waits for it and is never printed without it (a record it cannot read prints nothing). It follows
// `invoice.invoice.get` live: a payment or a rectification made elsewhere shows by itself.
import { formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import FiscalRecordFollower, { type FiscalRecordState } from '../../../sale/frontend/components/document/FiscalRecordFollower.vue';
import { printPaper } from '../../../sale/frontend/lib/print';
import InvoiceLinesTable from '../components/InvoiceLinesTable.vue';
import InvoicePaper from '../components/InvoicePaper.vue';
import InvoiceTotals from '../components/InvoiceTotals.vue';
import PageNotices from '../components/PageNotices.vue';
import RectifyModal from '../components/RectifyModal.vue';
import SubstituteModal from '../components/SubstituteModal.vue';
import VerifactuReceipt from '../components/VerifactuReceipt.vue';
import { useMarkPaid } from '../composables/useMarkPaid';
import { useLocale, useT } from '../composables/useT';
import { formatDate, moneyOf } from '../lib/format';
import { documentNote, missingTaxId, statusTone } from '../lib/invoice';
import type { InvoiceLinkOut, InvoiceOut } from '../operations';

const props = defineProps<{ id: string }>();

const router = useRouter();
const session = useSession();
const canAdd = computed(() => session.can('invoice.add_invoice'));
const canRectify = computed(() => session.can('invoice.rectify_invoice'));
const t = useT();
const locale = useLocale();

const { data: invoice, status, error } = useLive('invoice.invoice.get', () => ({ invoice_id: props.id }));

const loadError = computed(() => {
  if (status.value !== 'error' || !error.value) return null;
  if (error.value.code === 'app_inactive' || error.value.code === 'permission_denied') return null;
  const notFound = error.value.code === 'invoice.not_found' || error.value.code === 'not_found';
  return { heading: notFound ? t('invoice.detail.notFound') : t('invoice.detail.loadError'), message: notFound ? '' : error.value.message };
});


const fields = computed(() => {
  const doc = invoice.value;
  if (!doc) return [];
  const issuer = doc.issuer_tax_id ? `${doc.issuer_name} (${doc.issuer_tax_id})` : doc.issuer_name;
  const rows: { key: string; label: string; value: string }[] = [
    { key: 'type', label: t('invoice.detail.fields.type'), value: t(`invoice.typeNames.${doc.invoice_type}`) },
    { key: 'series', label: t('invoice.detail.fields.series'), value: doc.series_code },
    { key: 'issue-date', label: t('invoice.detail.fields.issueDate'), value: formatDate(doc.issue_date, locale.value) },
  ];
  if (doc.operation_date && doc.operation_date !== doc.issue_date) {
    rows.push({ key: 'operation-date', label: t('invoice.detail.fields.operationDate'), value: formatDate(doc.operation_date, locale.value) });
  }
  rows.push(
    { key: 'customer', label: t('invoice.detail.fields.customer'), value: doc.customer_name || '—' },
    { key: 'customer-tax-id', label: t('invoice.detail.fields.customerTaxId'), value: doc.customer_tax_id || '—' },
    { key: 'address', label: t('invoice.detail.fields.address'), value: doc.customer_address || '—' },
    { key: 'issuer', label: t('invoice.detail.fields.issuer'), value: issuer || '—' },
    { key: 'source', label: t('invoice.detail.fields.source'), value: t(`invoice.sources.${doc.source_type}`) },
  );
  if (doc.sale_number) rows.push({ key: 'sale', label: t('invoice.detail.fields.sale'), value: doc.sale_number });
  return rows;
});

const links = computed(() => {
  const doc = invoice.value;
  if (!doc) return [];
  const out: { key: string; label: string; items: InvoiceLinkOut[] }[] = [];
  if (doc.rectifies) out.push({ key: 'rectifies', label: t('invoice.detail.fields.rectifies'), items: [doc.rectifies] });
  if (doc.substitutes) out.push({ key: 'substitutes', label: t('invoice.detail.fields.substitutes'), items: [doc.substitutes] });
  if (doc.substituted_by) out.push({ key: 'substituted-by', label: t('invoice.detail.fields.substitutedBy'), items: [doc.substituted_by] });
  if (doc.rectifications.length) out.push({ key: 'rectifications', label: t('invoice.detail.fields.rectifications'), items: doc.rectifications });
  return out;
});

const note = computed(() => (invoice.value ? documentNote(invoice.value, t) : ''));

/** VeriFactu on in this business and the right to read its records. */
const verifactuOn = computed(
  () => !!session.me.value?.apps.some((app) => app.label === 'verifactu' && app.state === 'on') && session.can('verifactu.view_record'),
);
/** The invoice whose record is followed, from the start (one stream with the invoice); none without VeriFactu. */
const recordOf = computed(() => (verifactuOn.value ? props.id : null));
const fiscal = shallowRef<FiscalRecordState>({ record: undefined, error: null });
watch(recordOf, () => {
  fiscal.value = { record: undefined, error: null };
});
/** Its record (its receipt and the paper's QR); none without VeriFactu or before VeriFactu has one. */
const record = computed(() => (recordOf.value ? (fiscal.value.record ?? null) : null));
/** The screen's paper waits for the record it must carry. */
const waitingRecord = computed(() => !!recordOf.value && fiscal.value.record === undefined && !fiscal.value.error);
/** A document of a sale, a refund or a void: its original was the till's paper. */
const duplicate = computed(() => ['sale', 'refund', 'void'].includes(invoice.value?.source_type ?? ''));

function go(link: InvoiceLinkOut): void {
  void router.push(`/invoice/invoices/${link.id}`);
}

// ── Actions ──────────────────────────────────────────────────────────────────────────────────────
const paid = useMarkPaid();
const rectifyOpen = shallowRef(false);
const substituteOpen = shallowRef(false);
const paper = shallowRef<{ $el: HTMLElement } | null>(null);

const queue = useCommand('invoice.invoice.print');
/** A print on its way: a second press waits for it. */
const sending = shallowRef(false);

async function print(): Promise<void> {
  const element = paper.value?.$el;
  if (!element || sending.value) return;
  sending.value = true;
  try {
    const sent = await queue.run({ invoice_id: props.id, duplicate: duplicate.value });
    if (sent.queued) {
      void toastSuccess(t('invoice.detail.queued', { printer: sent.printer ?? '' }));
      return;
    }
  } catch {
    // The queue could not be asked: the screen's paper still prints (below).
  } finally {
    sending.value = false;
  }
  // The screen's paper never goes out without the QR of a record it could not read.
  if (recordOf.value && fiscal.value.error) {
    void toastError(t('invoice.detail.printFailed'));
    return;
  }
  try {
    printPaper(element);
  } catch {
    void toastError(t('invoice.detail.printFailed'));
  }
}

function onSubstituted(full: InvoiceOut): void {
  void router.push(`/invoice/invoices/${full.id}`);
}
</script>

<template>
  <AppPage
    :title="$t('invoice.title')"
    back-href="/invoice/invoices"
    content-layout="detail"
  >
    <PageNotices
      testid="invoice-detail"
      :status="status"
      :error="error"
    />
    <FiscalRecordFollower
      v-if="recordOf"
      :key="recordOf"
      :invoice-id="recordOf"
      @change="fiscal = $event"
    />
    <InlineFeedback
      v-if="loadError"
      tone="warning"
      data-testid="invoice-detail-load-error"
      :heading="loadError.heading"
    >
      {{ loadError.message }}
    </InlineFeedback>
    <div
      v-if="!invoice && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="invoice-detail-loading" />
    </div>

    <template v-if="invoice">
      <header class="invoice-detail__header">
        <div class="invoice-detail__title">
          <h2 data-testid="invoice-detail-title">
            {{ $t('invoice.detail.title', { number: invoice.number }) }}
          </h2>
          <StatusPill
            data-testid="invoice-detail-status"
            :tone="statusTone(invoice.status)"
            :label="$t(`invoice.status.${invoice.status}`)"
          />
        </div>
        <div class="invoice-detail__header-actions">
          <ion-button
            :disabled="sending || waitingRecord"
            data-testid="invoice-detail-print"
            @click="print"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            {{ $t('invoice.detail.print') }}
          </ion-button>
          <ion-button
            fill="outline"
            color="medium"
            data-testid="invoice-detail-back"
            @click="router.push('/invoice/invoices')"
          >
            ← {{ $t('invoice.back') }}
          </ion-button>
        </div>
      </header>

      <InlineFeedback
        v-if="missingTaxId(invoice)"
        tone="warning"
        data-testid="invoice-missing-tax-id"
      >
        {{ $t('invoice.detail.missingTaxId') }}
      </InlineFeedback>

      <section class="invoice-detail__card">
        <dl class="invoice-detail__grid">
          <div
            v-for="field in fields"
            :key="field.key"
          >
            <dt>{{ field.label }}</dt>
            <dd :data-testid="`invoice-detail-${field.key}`">
              {{ field.value }}
            </dd>
          </div>
          <div
            v-for="link in links"
            :key="link.key"
          >
            <dt>{{ link.label }}</dt>
            <dd :data-testid="`invoice-detail-${link.key}`">
              <a
                v-for="item in link.items"
                :key="item.id"
                class="invoice-detail__link"
                href="#"
                :data-testid="`invoice-detail-${link.key}-link`"
                @click.prevent="go(item)"
              >{{ item.number }}</a>
            </dd>
          </div>
          <div v-if="invoice.paid_at">
            <dt>{{ $t('invoice.detail.fields.paidAt') }}</dt>
            <dd data-testid="invoice-detail-paid-at">
              {{ formatDateTime(invoice.paid_at, locale) }}
            </dd>
          </div>
          <div v-if="note">
            <dt>{{ $t('invoice.detail.fields.notes') }}</dt>
            <dd data-testid="invoice-detail-notes">
              {{ note }}
            </dd>
          </div>
        </dl>
        <InvoiceLinesTable
          :lines="invoice.lines"
          :taxes="invoice.tax_breakdown.map((entry) => entry.tax)"
          :money="moneyOf(invoice)"
        />
        <InvoiceTotals :invoice="invoice" />
        <InlineFeedback
          v-if="paid.refused.value"
          tone="danger"
          data-testid="invoice-detail-error"
        >
          {{ paid.refused.value }}
        </InlineFeedback>
        <div class="invoice-detail__actions">
          <ion-button
            v-if="canAdd && invoice.can_mark_paid"
            color="success"
            data-testid="invoice-detail-mark-paid"
            :disabled="paid.pending.value === invoice.id"
            @click="paid.mark(invoice)"
          >
            {{ $t('invoice.detail.actions.markPaid') }}
          </ion-button>
          <ion-button
            v-if="canRectify && invoice.can_rectify"
            fill="outline"
            color="danger"
            data-testid="invoice-detail-rectify"
            @click="rectifyOpen = true"
          >
            {{ $t('invoice.detail.actions.rectify') }}
          </ion-button>
          <ion-button
            v-if="canAdd && invoice.can_substitute"
            fill="outline"
            data-testid="invoice-detail-substitute"
            @click="substituteOpen = true"
          >
            {{ $t('invoice.detail.actions.substitute') }}
          </ion-button>
        </div>
      </section>

      <VerifactuReceipt
        v-if="record"
        :record="record"
      />

      <div
        class="invoice-detail__paper"
        hidden
      >
        <InvoicePaper
          ref="paper"
          :invoice="invoice"
          :duplicate="duplicate"
          :record="record"
        />
      </div>
    </template>

    <RectifyModal
      v-if="canRectify"
      v-model:open="rectifyOpen"
      :invoice="invoice ?? null"
    />
    <SubstituteModal
      v-if="canAdd"
      v-model:open="substituteOpen"
      :ticket="invoice ?? null"
      @substituted="onSubstituted"
    />
  </AppPage>
</template>

<style scoped>
/* The header wraps: on a phone the buttons drop below instead of breaking the number or the status. */
.invoice-detail__header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.75rem;
}
.invoice-detail__title {
  display: flex;
  flex-wrap: wrap;
  flex: 1 1 auto;
  min-width: 0;
  gap: 0.5rem;
  align-items: center;
}
.invoice-detail__title h2 {
  margin: 0;
  font-size: 1.15rem;
}
.invoice-detail__header-actions {
  display: flex;
  flex: none;
  gap: 0.5rem;
  margin-inline-start: auto;
}
.invoice-detail__header-actions ion-button,
.invoice-detail__actions ion-button {
  min-height: 44px;
  white-space: nowrap;
}
.invoice-detail__card {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: var(--ep-radius-sm, 10px);
  padding: 1rem;
  margin: 0.75rem 0 1rem;
  background: var(--ion-card-background, #fffdf7);
}
.invoice-detail__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.35rem 0.75rem;
  margin: 0.5rem 0;
}
.invoice-detail__grid dt {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--ion-color-medium, #8a8577);
  margin: 0;
}
.invoice-detail__grid dd {
  margin: 0 0 0.4rem;
  font-weight: 500;
  word-break: break-word;
}
.invoice-detail__link {
  display: inline-block;
  margin-inline-end: 0.5rem;
  color: var(--ion-color-primary, #3880ff);
  font-weight: 600;
  text-decoration: none;
}
.invoice-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.6rem;
}
</style>
