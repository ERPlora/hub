<script setup lang="ts">
// The page a customer opens from the code on her ticket, without a session (`/p/<slug>/invoice/<code>`, whose HTML
// base's public door serves): the ticket, her tax details for its full invoice, and that invoice once issued. As in
// the invoice's own page, the screen shows it in parts that fit a phone and its A4 is only for «Print / PDF». Asking
// again answers the same invoice, so a reload or a second visit shows it instead of the form.
import { InlineFeedback, useRefusal } from '@erplora/ui/components';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef, useTemplateRef } from 'vue';
import { useRoute } from 'vue-router';

import { openPublicDoor } from '../../../../base/frontend/lib/public-door';
import { printRefusal, withReason } from '../../../../base/frontend/lib/print-paper';
import { printPaper } from '../../../sale/frontend/lib/print';
import InvoiceLinesTable from '../components/InvoiceLinesTable.vue';
import InvoicePaper from '../components/InvoicePaper.vue';
import InvoiceTotals from '../components/InvoiceTotals.vue';
import RecipientFields from '../components/RecipientFields.vue';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney, type Money, moneyOf } from '../lib/format';
import { type Recipient, recipientComplete, recipientFrom, recipientPayload } from '../lib/recipient';
import { refusal } from '../lib/refusal';
import type { PublicTicketOut } from '../operations/public';

/** A code that will never open a ticket here: trying again changes nothing. */
const FINAL_REFUSALS = new Set(['invoice.code_not_found', 'invoice.code_expired']);

const route = useRoute();
const code = String(route.params.code ?? '');
const door = openPublicDoor(useLiveClient().config, {
  slug: String(route.params.slug ?? ''),
  operations: ['invoice.public.ticket', 'invoice.public.substitute'],
});
const t = useT();
const locale = useLocale();

const loading = shallowRef(true);
const ticket = shallowRef<PublicTicketOut | null>(null);
const loadFailure = shallowRef<unknown>(null);
const recipient = shallowRef<Recipient>(recipientFrom(null));
const issuing = shallowRef(false);
const issueFailure = shallowRef<unknown>(null);
const issuedNow = shallowRef(false);
const printing = shallowRef(false);
const paper = useTemplateRef<{ $el: HTMLElement }>('paper');

const invoice = computed(() => ticket.value?.invoice ?? null);
const record = computed(() => ticket.value?.record ?? null);
/** What the screen says of the issued invoice: who issued it, when, and to whom. */
const invoiceFields = computed(() => {
  const current = invoice.value;
  if (!current) return [];
  return [
    { label: t('invoice.detail.fields.issuer'), value: current.issuer_name },
    { label: t('invoice.detail.fields.issueDate'), value: formatDate(current.issue_date, locale.value) },
    { label: t('invoice.detail.fields.customer'), value: current.customer_name },
    { label: t('invoice.detail.fields.customerTaxId'), value: current.customer_tax_id },
  ];
});
const canIssue = computed(() => recipientComplete(recipient.value) && !issuing.value);
/** The ticket's amount in the business's money; a dash if the ticket was charged in another one. */
const ticketMoney = computed<Money | undefined>(() => {
  const current = ticket.value?.ticket;
  const business = door.money.value;
  if (!current || business?.currency !== current.currency) return undefined;
  return { currency: current.currency, decimals: business.decimals };
});
const ticketDate = computed(() => formatDate(ticket.value?.ticket.issue_date, locale.value));
const ticketTotal = computed(() => formatMoney(ticket.value?.ticket.total_amount, locale.value, ticketMoney.value));
const loadMessage = computed(() => refusal(loadFailure.value, t('invoice.public.loadFailed'))?.message ?? '');
const canRetry = computed(() => !(loadFailure.value instanceof ApiError && FINAL_REFUSALS.has(loadFailure.value.code)));
const refused = computed(() => refusal(issueFailure.value, t('invoice.public.issueFailed')));
const { fieldErrors, showsError, changed } = useRefusal(refused);

async function load(): Promise<void> {
  loading.value = true;
  loadFailure.value = null;
  try {
    ticket.value = await door.api.call('invoice.public.ticket', { code });
  } catch (error) {
    loadFailure.value = error;
  } finally {
    loading.value = false;
  }
}

async function issue(): Promise<void> {
  if (!ticket.value || invoice.value || !canIssue.value) return;
  issuing.value = true;
  issueFailure.value = null;
  try {
    const answer = await door.api.call('invoice.public.substitute', { code, ...recipientPayload(recipient.value) });
    ticket.value = { ...ticket.value, invoice: answer.invoice, record: answer.record };
    issuedNow.value = answer.issued;
  } catch (error) {
    issueFailure.value = error;
  } finally {
    issuing.value = false;
  }
}

/** A field the customer changed: its refusal has done its job (Ionic's fields hand their `name` to the event). */
function edited(event: Event): void {
  const name = (event.target as { name?: unknown } | null)?.name;
  changed(typeof name === 'string' && name ? name : undefined);
}

async function print(): Promise<void> {
  const element = paper.value?.$el;
  if (!element || !invoice.value || printing.value) return;
  printing.value = true;
  try {
    await printPaper(element, { title: t('invoice.detail.title', { number: invoice.value.number }) });
  } catch (failure) {
    toastError(withReason(t('invoice.detail.printFailed'), printRefusal(failure, t)));
  } finally {
    printing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <AppPage
    :title="$t('invoice.public.title')"
    content-layout="detail"
  >
    <p
      v-if="loading"
      data-testid="invoice-public-loading"
      role="status"
    >
      <ion-spinner name="crescent" />
      {{ $t('invoice.public.loading') }}
    </p>
    <InlineFeedback
      v-else-if="loadFailure"
      :tone="canRetry ? 'warning' : 'danger'"
      role="alert"
      data-testid="invoice-public-error"
    >
      {{ loadMessage }}
      <template
        v-if="canRetry"
        #actions
      >
        <ion-button
          fill="clear"
          data-testid="invoice-public-retry"
          @click="load"
        >
          {{ $t('invoice.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <section v-else-if="ticket && invoice">
      <InlineFeedback
        :tone="issuedNow ? 'success' : 'info'"
        :data-testid="issuedNow ? 'invoice-public-ready' : 'invoice-public-already'"
        role="status"
      >
        {{ issuedNow ? $t('invoice.public.ready') : $t('invoice.public.already') }}
      </InlineFeedback>
      <h2 data-testid="invoice-public-number">
        {{ $t('invoice.detail.title', { number: invoice.number }) }}
      </h2>
      <ion-list
        inset
        data-testid="invoice-public-invoice"
      >
        <ion-item
          v-for="field in invoiceFields"
          :key="field.label"
        >
          <ion-label>{{ field.label }}</ion-label>
          <ion-note slot="end">
            {{ field.value }}
          </ion-note>
        </ion-item>
      </ion-list>
      <InvoiceLinesTable
        :lines="invoice.lines"
        :taxes="invoice.tax_breakdown.map((entry) => entry.tax)"
        :money="moneyOf(invoice)"
      />
      <InvoiceTotals :invoice="invoice" />
      <p class="ion-text-center ion-margin-top">
        <ion-button
          data-testid="invoice-public-print"
          :disabled="printing"
          @click="print"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ $t('invoice.detail.print') }}
        </ion-button>
      </p>
      <div hidden>
        <InvoicePaper
          ref="paper"
          :invoice="invoice"
          :record="record"
        />
      </div>
    </section>

    <template v-else-if="ticket">
      <section data-testid="invoice-public-ticket">
        <h2 data-testid="invoice-public-ticket-number">
          {{ $t('invoice.public.ticket', { number: ticket.ticket.number }) }}
        </h2>
        <ion-list inset>
          <ion-item data-testid="invoice-public-business">
            <ion-label>{{ $t('invoice.public.business') }}</ion-label>
            <ion-note slot="end">
              {{ ticket.ticket.issuer_name }}
            </ion-note>
          </ion-item>
          <ion-item>
            <ion-label>{{ $t('invoice.public.date') }}</ion-label>
            <ion-note
              slot="end"
              class="ion-text-nowrap"
            >
              {{ ticketDate }}
            </ion-note>
          </ion-item>
          <ion-item lines="none">
            <ion-label>{{ $t('invoice.public.total') }}</ion-label>
            <ion-note
              slot="end"
              class="ion-text-nowrap"
            >
              {{ ticketTotal }}
            </ion-note>
          </ion-item>
        </ion-list>
      </section>

      <form
        data-testid="invoice-public-form"
        novalidate
        @submit.prevent="issue"
        @input="edited"
        @ionChange="edited"
      >
        <p>{{ $t('invoice.public.intro') }}</p>
        <RecipientFields
          v-model="recipient"
          :allow-search="false"
          :field-errors="fieldErrors"
        />
        <InlineFeedback
          v-if="refused && showsError"
          tone="danger"
          role="alert"
          data-testid="invoice-public-form-error"
        >
          {{ refused.message }}
        </InlineFeedback>
        <ion-button
          class="ion-margin-top"
          expand="block"
          type="submit"
          data-testid="invoice-public-submit"
          :disabled="!canIssue"
        >
          <ion-spinner
            v-if="issuing"
            slot="start"
            name="crescent"
          />
          {{ issuing ? $t('invoice.public.issuing') : $t('invoice.public.submit') }}
        </ion-button>
      </form>
    </template>
  </AppPage>
</template>
