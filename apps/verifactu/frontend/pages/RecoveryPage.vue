<script setup lang="ts">
// VeriFactu → Recovery (VERIFACTU-F26–F29; the old `erp-verifactu-recovery`): «Chain recovery» with the «Issuer tax
// ID» (filled with Invoicing's issuer) and the current environment; «Chain integrity» with the last verdict and the
// note of what it checks; «Validate chain», «Query AEAT» (whoever may send) and «Recover chain from AEAT» (asks
// first; owner and admin); «Latest records at the AEAT» (the last photo); and «Continue chain manually (migration)»
// (the last fingerprint, 64 hex, with its invoice number and date; asks first; owner and admin). Without a tax ID the
// buttons are off. Every action ends in «Operation completed.» or its refusal, in the server's words.
import { formatDateTime, InlineFeedback, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/format';
import { short } from '../lib/record';
import { refusal } from '../lib/refusal';
import { verifactuTabs } from '../tabs';

const HASH = /^[0-9a-fA-F]{64}$/;

const session = useSession();
const canSend = computed(() => session.can('verifactu.transmit_record'));
const canConfigure = computed(() => session.can('verifactu.configure'));
const t = useT();
const locale = useLocale();
const { confirm } = useConfirm();

const nif = shallowRef('');
const { data: config, status, error } = useLive('verifactu.config.get', () => ({}));
watch(
  config,
  (now) => {
    if (now && !nif.value) nif.value = now.issuer_nif;
  },
  { immediate: true },
);
const issuer = computed(() => nif.value.trim());
const { data: chainStatus } = useLive('verifactu.chain.status', () => (issuer.value ? { issuer_nif: issuer.value } : {}));
const { data: aeat } = useLive('verifactu.aeat_record.list', () => ({ limit: 50 }));

const head = computed(() => chainStatus.value?.chains.find((chain) => chain.environment === chainStatus.value?.environment) ?? null);
const integrity = computed(() => {
  const chain = head.value;
  if (!chain || chain.valid === null) return { tone: 'info' as const, text: t('verifactu.recovery.unknown') };
  return chain.valid
    ? { tone: 'success' as const, text: t('verifactu.recovery.valid') }
    : { tone: 'danger' as const, text: t('verifactu.recovery.broken', { seq: chain.first_invalid_sequence ?? '' }) };
});

const validate = useCommand('verifactu.chain.validate');
const query = useCommand('verifactu.aeat.query');
const recover = useCommand('verifactu.chain.recover_from_aeat');
const manual = useCommand('verifactu.chain.recover_manual');
const working = computed(() => validate.pending.value || query.pending.value || recover.pending.value || manual.pending.value);
const result = shallowRef<{ tone: 'success' | 'danger'; text: string } | null>(null);

const hash = shallowRef('');
const number = shallowRef('');
const day = shallowRef('');

async function act(run: () => Promise<unknown>, command: { error: { value: unknown } }): Promise<void> {
  result.value = null;
  try {
    await run();
  } catch {
    result.value = { tone: 'danger', text: refusal(command.error.value, t('verifactu.recovery.failed'))?.message ?? t('verifactu.recovery.failed') };
    return;
  }
  result.value = { tone: 'success', text: t('verifactu.recovery.done') };
}

async function recoverFromAeat(): Promise<void> {
  const yes = await confirm({
    title: t('verifactu.recovery.confirmAeatTitle'),
    message: t('verifactu.recovery.confirmAeatMessage'),
    confirmLabel: t('verifactu.recovery.confirm'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'danger',
  });
  if (yes) await act(() => recover.run({ issuer_nif: issuer.value }), recover);
}

async function continueManually(): Promise<void> {
  result.value = null;
  if (!HASH.test(hash.value.trim())) {
    result.value = { tone: 'danger', text: t('verifactu.recovery.hashInvalid') };
    return;
  }
  const yes = await confirm({
    title: t('verifactu.recovery.confirmManualTitle'),
    message: t('verifactu.recovery.confirmManualMessage'),
    confirmLabel: t('verifactu.recovery.confirm'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'danger',
  });
  if (!yes) return;
  await act(
    () => manual.run({ issuer_nif: issuer.value, fingerprint: hash.value.trim(), invoice_number: number.value.trim(), issue_date: day.value }),
    manual,
  );
}
</script>

<template>
  <AppPage
    :title="$t('verifactu.recovery.title')"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
    content-layout="detail"
  >
    <PageNotices
      testid="verifactu-recovery"
      :status="status"
      :error="error"
    />
    <div class="verifactu-recovery__issuer">
      <ion-input
        data-testid="verifactu-recovery-nif"
        :label="$t('verifactu.recovery.nif')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="32"
        :value="nif"
        @ion-input="nif = String($event.detail.value ?? '')"
      />
      <p v-if="config">
        {{ $t('verifactu.recovery.environment') }}: {{ $t(`verifactu.env.${config.environment}`) }}
      </p>
    </div>

    <section class="verifactu-recovery__section">
      <h3>{{ $t('verifactu.recovery.integrity') }}</h3>
      <InlineFeedback
        :tone="integrity.tone"
        data-testid="verifactu-recovery-integrity"
      >
        {{ integrity.text }}
        <template v-if="head?.validated_at">
          {{ $t('verifactu.recovery.checked', { total: head.total, date: formatDateTime(head.validated_at, locale) }) }}
        </template>
      </InlineFeedback>
      <p class="verifactu-recovery__note">
        {{ $t('verifactu.recovery.scope') }}
      </p>
      <div class="verifactu-recovery__buttons">
        <ion-button
          data-testid="verifactu-recovery-validate"
          :disabled="!issuer || working"
          @click="act(() => validate.run({ issuer_nif: issuer }), validate)"
        >
          {{ validate.pending.value ? $t('verifactu.recovery.working') : $t('verifactu.recovery.validate') }}
        </ion-button>
        <ion-button
          v-if="canSend"
          fill="outline"
          data-testid="verifactu-recovery-query"
          :disabled="!issuer || working"
          @click="act(() => query.run({ issuer_nif: issuer }), query)"
        >
          {{ query.pending.value ? $t('verifactu.recovery.working') : $t('verifactu.recovery.query') }}
        </ion-button>
        <ion-button
          v-if="canConfigure"
          fill="outline"
          color="danger"
          data-testid="verifactu-recovery-recover"
          :disabled="!issuer || working"
          @click="recoverFromAeat"
        >
          {{ recover.pending.value ? $t('verifactu.recovery.working') : $t('verifactu.recovery.recover') }}
        </ion-button>
      </div>
      <InlineFeedback
        v-if="result"
        :tone="result.tone"
        data-testid="verifactu-recovery-result"
      >
        {{ result.text }}
      </InlineFeedback>
    </section>

    <section class="verifactu-recovery__section">
      <h3>{{ $t('verifactu.recovery.aeatTitle') }}</h3>
      <div
        class="verifactu-recovery__table"
        data-testid="verifactu-recovery-aeat"
      >
        <p v-if="!aeat?.rows.length">
          {{ $t('verifactu.recovery.aeatEmpty') }}
        </p>
        <table v-else>
          <thead>
            <tr>
              <th>{{ $t('verifactu.recovery.aeatColumns.invoice') }}</th>
              <th>{{ $t('verifactu.recovery.aeatColumns.date') }}</th>
              <th>{{ $t('verifactu.recovery.aeatColumns.fingerprint') }}</th>
              <th>{{ $t('verifactu.recovery.aeatColumns.state') }}</th>
              <th>{{ $t('verifactu.recovery.aeatColumns.csv') }}</th>
              <th>{{ $t('verifactu.recovery.aeatColumns.queried') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in aeat.rows"
              :key="row.id"
            >
              <td>{{ row.invoice_number }}</td>
              <td>{{ formatDate(row.issue_date, locale) }}</td>
              <td class="verifactu-recovery__hash">
                {{ short(row.fingerprint) }}
              </td>
              <td>{{ row.state || '—' }}</td>
              <td>{{ row.csv || '—' }}</td>
              <td>{{ formatDateTime(row.queried_at, locale) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section
      v-if="canConfigure"
      class="verifactu-recovery__section"
    >
      <h3>{{ $t('verifactu.recovery.manualTitle') }}</h3>
      <p class="verifactu-recovery__note">
        {{ $t('verifactu.recovery.manualHint') }}
      </p>
      <div class="verifactu-recovery__manual">
        <ion-input
          data-testid="verifactu-recovery-hash"
          :label="$t('verifactu.recovery.manualHash')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="64"
          :value="hash"
          @ion-input="hash = String($event.detail.value ?? '')"
        />
        <ion-input
          data-testid="verifactu-recovery-invoice"
          :label="$t('verifactu.recovery.manualInvoice')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="60"
          :value="number"
          @ion-input="number = String($event.detail.value ?? '')"
        />
        <ion-input
          data-testid="verifactu-recovery-date"
          :label="$t('verifactu.recovery.manualDate')"
          label-placement="floating"
          fill="outline"
          mode="md"
          type="date"
          :value="day"
          @ion-change="day = String($event.detail.value ?? '')"
        />
      </div>
      <ion-button
        fill="outline"
        color="danger"
        data-testid="verifactu-recovery-manual"
        :disabled="!issuer || !number.trim() || !day || working"
        @click="continueManually"
      >
        {{ manual.pending.value ? $t('verifactu.recovery.working') : $t('verifactu.recovery.manualSubmit') }}
      </ion-button>
    </section>
  </AppPage>
</template>

<style scoped>
.verifactu-recovery__issuer {
  display: grid;
  gap: 0.5rem;
  max-width: 28rem;
}
.verifactu-recovery__section {
  margin-top: 1.25rem;
}
.verifactu-recovery__section h3 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}
.verifactu-recovery__note {
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.85rem;
}
.verifactu-recovery__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.verifactu-recovery__table {
  overflow-x: auto;
}
.verifactu-recovery__table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.verifactu-recovery__table th,
.verifactu-recovery__table td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--ion-color-light-shade, #e4e1d8);
  text-align: start;
}
.verifactu-recovery__hash {
  font-family: ui-monospace, monospace;
}
.verifactu-recovery__manual {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 0.5rem;
}
@media (max-width: 767px) {
  .verifactu-recovery__manual {
    grid-template-columns: 1fr;
  }
}
</style>
