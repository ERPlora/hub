<script setup lang="ts">
// A record (VERIFACTU-F17, F18, F24, F25, F30, F35; the old detail of `erp-verifactu-records`, now its own page with Back
// to the list): «Record <number>» with its status and environment; «Not at the AEAT yet» with why and when, or «The
// AEAT rejected it» with its code, its message and what to do; the invoice's figures, the fingerprint chain, the QR
// (and «Verify at the AEAT»), the AEAT's answer with the delivery's fingerprint, the XML and its latest events.
// «Send now», «Ask the AEAT» (in the queue: it leaves only if the AEAT already has it), «Correct» and «Cancel record»
// where they apply and for whoever may; a refusal is said right above them.
// It follows `verifactu.record.get` live: an answer of the AEAT shows by itself.
import { formatDateTime, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toast, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import CancelRecordModal from '../components/CancelRecordModal.vue';
import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney } from '../lib/format';
import { environmentTone, statusTone } from '../lib/record';
import { refusal } from '../lib/refusal';

const props = defineProps<{ id: string }>();

const session = useSession();
const canTransmit = computed(() => session.can('verifactu.transmit_record'));
const canCorrect = computed(() => session.can('verifactu.correct_record'));
const t = useT();
const locale = useLocale();
const { confirm } = useConfirm();

const { data: record, status, error } = useLive('verifactu.record.get', () => ({ record_id: props.id }));
const transmit = useCommand('verifactu.record.transmit');
const reconcile = useCommand('verifactu.record.reconcile');
const correct = useCommand('verifactu.record.correct');
const cancelling = shallowRef(false);
const refused = shallowRef<string | null>(null);

const notFound = computed(() => status.value === 'error' && (error.value?.code === 'not_found' || error.value?.code === 'verifactu.not_found'));
const loadError = computed(() =>
  status.value === 'error' && !notFound.value && error.value?.code !== 'app_inactive' && error.value?.code !== 'permission_denied'
    ? error.value?.message ?? ''
    : null,
);
const pending = computed(() => transmit.pending.value || reconcile.pending.value || correct.pending.value);
// A business outside Spain never sends it (VeriFactu is only for Spain): no «it goes out by itself».
const neverSent = computed(() => !!record.value?.waiting.some((reason) => reason.code === 'outside_spain'));

const when = (value: string | null | undefined) => (value ? formatDateTime(value, locale.value) : '—');

const invoiceFields = computed(() => {
  const r = record.value;
  if (!r) return [];
  const rows = [
    { key: 'invoice', label: t('verifactu.detail.invoice'), value: r.invoice_number },
    { key: 'issue-date', label: t('verifactu.detail.issueDate'), value: formatDate(r.issue_date, locale.value) },
  ];
  if (r.operation_date) rows.push({ key: 'operation-date', label: t('verifactu.detail.operationDate'), value: formatDate(r.operation_date, locale.value) });
  rows.push(
    { key: 'type', label: t('verifactu.detail.invoiceType'), value: r.invoice_type ? r.invoice_type : t(`verifactu.recordType.${r.record_type}`) },
    { key: 'issuer', label: t('verifactu.detail.issuer'), value: r.issuer_name },
    { key: 'issuer-nif', label: t('verifactu.detail.issuerNif'), value: r.issuer_nif },
  );
  if (r.recipient_tax_id) {
    rows.push(
      { key: 'customer', label: t('verifactu.detail.customer'), value: r.recipient_name },
      { key: 'customer-nif', label: t('verifactu.detail.customerNif'), value: r.recipient_tax_id },
    );
  }
  for (const ref of r.rectified) rows.push({ key: 'rectifies', label: t('verifactu.detail.rectifies'), value: ref.number });
  for (const ref of r.substituted) rows.push({ key: 'replaces', label: t('verifactu.detail.replaces'), value: ref.number });
  if (r.description) rows.push({ key: 'description', label: t('verifactu.detail.description'), value: r.description });
  if (r.total_amount !== null) {
    rows.push(
      { key: 'base', label: t('verifactu.detail.base'), value: formatMoney(r.base_amount, locale.value) },
      { key: 'tax', label: t('verifactu.detail.tax'), value: formatMoney(r.tax_amount, locale.value) },
      { key: 'total', label: t('verifactu.detail.total'), value: formatMoney(r.total_amount, locale.value) },
    );
  }
  return rows;
});

async function sendNow(): Promise<void> {
  const r = record.value;
  if (!r || pending.value) return;
  refused.value = null;
  let answer;
  try {
    answer = await transmit.run({ record_id: r.id });
  } catch {
    refused.value = refusal(transmit.error.value, t('verifactu.detail.transmitFailed'))?.message ?? t('verifactu.detail.transmitFailed');
    return;
  }
  // A reason means it did not reach the AEAT (or the AEAT refused the sending): a warning, never a success.
  if (answer.reason) {
    void toast(answer.message, 'warning', 4500);
    return;
  }
  void toastSuccess(
    t('verifactu.detail.transmitted', { accepted: answer.accepted + answer.accepted_with_errors, rejected: answer.rejected, waiting: answer.waiting }),
  );
}

async function askTheAeat(): Promise<void> {
  const r = record.value;
  if (!r || pending.value) return;
  refused.value = null;
  let answer;
  try {
    answer = await reconcile.run({ record_id: r.id });
  } catch {
    refused.value = refusal(reconcile.error.value, t('verifactu.detail.actionFailed'))?.message ?? t('verifactu.detail.actionFailed');
    return;
  }
  // Not held is no failure, but nothing changed: it stays in the queue (a warning, never a success).
  if (!answer.held) {
    void toast(t('verifactu.detail.askNotHeld', { number: r.invoice_number }), 'warning', 4500);
    return;
  }
  void toastSuccess(t('verifactu.detail.askHeld', { number: r.invoice_number }));
}

async function correctIt(): Promise<void> {
  const r = record.value;
  if (!r || pending.value) return;
  refused.value = null;
  const yes = await confirm({
    title: t('verifactu.detail.correctTitle', { number: r.invoice_number }),
    message: t('verifactu.detail.correctMessage'),
    confirmLabel: t('verifactu.detail.correct'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'primary',
  });
  if (!yes) return;
  try {
    await correct.run({ record_id: r.id });
  } catch {
    refused.value = refusal(correct.error.value, t('verifactu.detail.actionFailed'))?.message ?? t('verifactu.detail.actionFailed');
    return;
  }
  void toastSuccess(t('verifactu.detail.correctDone', { number: r.invoice_number }));
}
</script>

<template>
  <AppPage
    :title="$t('verifactu.title')"
    back-href="/verifactu/records"
    content-layout="detail"
  >
    <PageNotices
      testid="verifactu-record"
      :status="status"
      :error="notFound ? null : error"
    />
    <div
      v-if="!record && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="verifactu-record-loading" />
    </div>
    <template v-if="notFound || loadError !== null">
      <InlineFeedback
        tone="warning"
        :data-testid="notFound ? 'verifactu-record-not-found' : 'verifactu-record-load-error'"
        :heading="notFound ? $t('verifactu.detail.notFound') : $t('verifactu.detail.actionFailed')"
      >
        {{ notFound ? '' : loadError }}
      </InlineFeedback>
      <ion-button
        fill="clear"
        router-link="/verifactu/records"
        data-testid="verifactu-record-back"
      >
        ← {{ $t('verifactu.back') }}
      </ion-button>
    </template>
    <template v-if="record && !notFound">
      <header class="verifactu-record__head">
        <h2
          class="verifactu-record__title"
          data-testid="verifactu-record-title"
        >
          {{ $t('verifactu.detail.title', { number: record.invoice_number }) }}
        </h2>
        <StatusPill
          data-testid="verifactu-record-status"
          :tone="statusTone(record.status)"
          :label="$t(`verifactu.status.${record.status}`)"
        />
        <StatusPill
          :tone="environmentTone(record.environment)"
          :label="$t(`verifactu.env.${record.environment}`)"
        />
      </header>

      <InlineFeedback
        v-if="record.waiting.length"
        tone="warning"
        data-testid="verifactu-record-waiting"
        :heading="$t('verifactu.detail.waitingTitle')"
      >
        <ul class="verifactu-record__reasons">
          <li
            v-for="reason in record.waiting"
            :key="reason.code"
          >
            {{ reason.message }}
          </li>
        </ul>
        <p v-if="!neverSent">
          {{ $t('verifactu.detail.waitingWhen') }}
        </p>
        <p v-if="record.next_attempt_at">
          {{ $t('verifactu.detail.nextAttempt') }}: {{ when(record.next_attempt_at) }}
        </p>
      </InlineFeedback>
      <InlineFeedback
        v-if="record.status === 'rejected'"
        tone="danger"
        data-testid="verifactu-record-rejected"
        :heading="$t('verifactu.detail.rejectedTitle')"
      >
        <p>{{ record.aeat_code }} · {{ record.aeat_message }}</p>
        <p>{{ $t('verifactu.detail.rejectedHelp') }}</p>
      </InlineFeedback>

      <section class="verifactu-record__section">
        <h3>{{ $t('verifactu.detail.invoice') }}</h3>
        <dl class="verifactu-record__fields">
          <template
            v-for="field in invoiceFields"
            :key="field.key"
          >
            <dt>{{ field.label }}</dt>
            <dd :data-testid="`verifactu-record-${field.key}`">
              {{ field.value }}
            </dd>
          </template>
        </dl>
      </section>

      <section class="verifactu-record__section">
        <h3>{{ $t('verifactu.detail.chain') }}</h3>
        <dl class="verifactu-record__fields">
          <dt>{{ $t('verifactu.detail.sequence') }}</dt>
          <dd>{{ record.sequence }}</dd>
          <dt>{{ $t('verifactu.detail.generatedAt') }}</dt>
          <dd>{{ record.generated_at }}</dd>
          <dt>{{ $t('verifactu.detail.fingerprint') }}</dt>
          <dd
            class="verifactu-record__hash"
            data-testid="verifactu-record-fingerprint"
          >
            {{ record.fingerprint }}
          </dd>
          <dt>{{ $t('verifactu.detail.previousFingerprint') }}</dt>
          <dd
            :class="{ 'verifactu-record__hash': record.previous_fingerprint }"
            data-testid="verifactu-record-previous"
          >
            {{ record.previous_fingerprint ? `${record.previous_fingerprint} (${record.previous_number})` : $t('verifactu.detail.firstOfChain') }}
          </dd>
          <template v-if="record.correction">
            <dt>{{ $t('verifactu.detail.correction') }}</dt>
            <dd>{{ $t('verifactu.yes') }}</dd>
          </template>
        </dl>
      </section>

      <section class="verifactu-record__section verifactu-record__qr">
        <h3>{{ $t('verifactu.detail.qr') }}</h3>
        <img
          :src="record.qr_svg"
          :alt="$t('verifactu.detail.qr')"
          width="160"
          height="160"
          data-testid="verifactu-record-qr"
        >
        <a
          :href="record.qr_url"
          target="_blank"
          rel="noopener"
          data-testid="verifactu-record-verify"
        >{{ $t('verifactu.detail.verify') }} ↗</a>
      </section>

      <section class="verifactu-record__section">
        <h3>{{ $t('verifactu.detail.aeat') }}</h3>
        <dl class="verifactu-record__fields">
          <dt>{{ $t('verifactu.detail.transmittedAt') }}</dt>
          <dd>{{ when(record.transmitted_at) }}</dd>
          <dt>{{ $t('verifactu.detail.csv') }}</dt>
          <dd>{{ record.csv || '—' }}</dd>
          <dt>{{ $t('verifactu.detail.code') }}</dt>
          <dd>{{ record.aeat_code || '—' }}</dd>
          <dt>{{ $t('verifactu.detail.message') }}</dt>
          <dd>{{ record.aeat_message || '—' }}</dd>
          <dt>{{ $t('verifactu.detail.attempts') }}</dt>
          <dd>{{ record.attempts }}</dd>
          <dt>{{ $t('verifactu.detail.transmissionId') }}</dt>
          <dd>{{ record.transmission_id ?? '—' }}</dd>
          <dt>{{ $t('verifactu.detail.digest') }}</dt>
          <dd
            class="verifactu-record__hash"
            data-testid="verifactu-record-digest"
          >
            {{ record.envelope_digest || $t('verifactu.detail.notStamped') }}
          </dd>
          <template v-if="record.incident">
            <dt>{{ $t('verifactu.detail.incident') }}</dt>
            <dd>{{ $t('verifactu.yes') }}</dd>
          </template>
        </dl>
      </section>

      <section class="verifactu-record__section">
        <h3>{{ $t('verifactu.detail.xml') }}</h3>
        <pre
          v-if="record.envelope"
          class="verifactu-record__xml"
          data-testid="verifactu-record-xml"
        >{{ record.envelope }}</pre>
        <p
          v-else
          data-testid="verifactu-record-xml-pending"
        >
          {{ $t('verifactu.detail.xmlPending') }}
        </p>
      </section>

      <section
        v-if="record.events.length"
        class="verifactu-record__section"
      >
        <h3>{{ $t('verifactu.detail.events') }}</h3>
        <ul class="verifactu-record__events">
          <li
            v-for="event in record.events"
            :key="event.id"
          >
            <span class="verifactu-record__when">{{ when(event.created_at) }}</span> {{ event.message }}
          </li>
        </ul>
      </section>

      <InlineFeedback
        v-if="refused"
        tone="danger"
        data-testid="verifactu-record-error"
      >
        {{ refused }}
      </InlineFeedback>
      <div class="verifactu-record__actions">
        <ion-button
          v-if="canTransmit && record.can_transmit"
          data-testid="verifactu-record-transmit"
          :disabled="pending"
          @click="sendNow"
        >
          {{ $t('verifactu.detail.transmit') }}
        </ion-button>
        <ion-button
          v-if="canTransmit && record.can_transmit"
          fill="outline"
          data-testid="verifactu-record-ask"
          :disabled="pending"
          @click="askTheAeat"
        >
          {{ $t('verifactu.detail.ask') }}
        </ion-button>
        <ion-button
          v-if="canCorrect && record.can_correct"
          fill="outline"
          data-testid="verifactu-record-correct"
          :disabled="pending"
          @click="correctIt"
        >
          {{ $t('verifactu.detail.correct') }}
        </ion-button>
        <ion-button
          v-if="canCorrect && record.can_cancel"
          fill="outline"
          color="danger"
          data-testid="verifactu-record-cancel"
          :disabled="pending"
          @click="cancelling = true"
        >
          {{ $t('verifactu.detail.cancelRecord') }}
        </ion-button>
      </div>
      <CancelRecordModal
        v-if="canCorrect"
        v-model:open="cancelling"
        :record="record"
      />
    </template>
  </AppPage>
</template>

<style scoped>
.verifactu-record__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.verifactu-record__title {
  margin: 0;
  font-size: 1.15rem;
}
.verifactu-record__section {
  margin-top: 1rem;
}
.verifactu-record__section h3 {
  margin: 0 0 0.4rem;
  font-size: 0.95rem;
}
.verifactu-record__fields {
  display: grid;
  grid-template-columns: minmax(8rem, max-content) 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}
.verifactu-record__fields dt {
  color: var(--ion-color-medium, #8a8577);
}
.verifactu-record__fields dd {
  margin: 0;
}
.verifactu-record__hash {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  word-break: break-all;
}
.verifactu-record__qr {
  display: grid;
  justify-items: start;
  gap: 0.5rem;
}
.verifactu-record__xml {
  max-height: 20rem;
  overflow: auto;
  padding: 0.75rem;
  border-radius: 8px;
  background: var(--ion-color-light, #f4f2ec);
  font-size: 0.75rem;
  white-space: pre-wrap;
  word-break: break-all;
}
.verifactu-record__reasons {
  margin: 0 0 0.4rem;
  padding-inline-start: 1.1rem;
}
.verifactu-record__events {
  margin: 0;
  padding-inline-start: 1.1rem;
  font-size: 0.9rem;
}
.verifactu-record__when {
  color: var(--ion-color-medium, #8a8577);
}
.verifactu-record__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1rem;
}
@media (max-width: 575px) {
  .verifactu-record__fields {
    grid-template-columns: 1fr;
  }
}
</style>
