<script setup lang="ts">
// Cash register → the detail of a session (CASH_REGISTER-F11, F16; the old `erp-cashregister-session-
// detail`): «Session detail · S-…» with Back to the sessions, the summary (who opened and closed it, the
// drawer, the figures by payment method, expected, counted, difference and the notes), the session's
// «Movements» and «Counts», and «Print»: the X report of an open session or the Z of a closed one, through
// the browser's dialog. Read-only; everything re-runs by itself (a sale, a movement, a count, the close).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, nextTick, shallowRef, useTemplateRef } from 'vue';

import ClosingReport from '../components/ClosingReport.vue';
import SessionCounts from '../components/SessionCounts.vue';
import SessionLines from '../components/SessionLines.vue';
import SessionSummary from '../components/SessionSummary.vue';
import { useT } from '../composables/useT';
import * as paper from '../lib/print';
import { cashRegisterTabs } from '../tabs';

/** The session of the address (the route hands it once: `props: true`). */
const props = defineProps<{ id: string }>();

const t = useT();
const detail = useLive('cash_register.session.get', () => ({ session_id: props.id }));
const { data: session, status, error, refresh } = detail;

const notFound = computed(() => !session.value && error.value?.code === 'cash_register.session_not_found');
const failed = computed(() => !session.value && status.value === 'error' && !notFound.value);
const report = useTemplateRef<InstanceType<typeof ClosingReport>>('report');
/** When the paper is printed: set at each «Print», never when the page opened. */
const printedAt = shallowRef<Date | null>(null);

async function printReport(): Promise<void> {
  printedAt.value = new Date();
  await nextTick();
  const element = report.value?.$el as HTMLElement | undefined;
  if (!element) return;
  try {
    paper.printPaper(element);
  } catch {
    void toastError(t('cash_register.detail.printFailed'));
  }
}
</script>

<template>
  <AppPage
    :title="$t('cash_register.title')"
    back-href="/cash_register/sessions"
    :tabs="cashRegisterTabs($t)"
    :tabs-label="$t('cash_register.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="cash-register-detail-reconnecting"
    >
      {{ $t('cash_register.live.reconnecting') }}
    </InlineFeedback>
    <p
      v-if="!session && status === 'loading'"
      class="cash-detail__state"
      data-testid="cash-register-detail-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('cash_register.detail.loading') }}
    </p>
    <InlineFeedback
      v-else-if="notFound"
      tone="warning"
      data-testid="cash-register-detail-not-found"
    >
      {{ $t('cash_register.detail.notFound') }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      icon="cloud-offline-outline"
      data-testid="cash-register-detail-error"
      :heading="error?.code === 'app_inactive' ? $t('cash_register.live.appInactive') : $t('cash_register.detail.loadError')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="cash-register-detail-retry"
          @click="refresh()"
        >
          {{ $t('cash_register.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <div
      v-if="session"
      class="cash-detail"
    >
      <header class="cash-detail__header">
        <h2 data-testid="cash-register-detail-title">
          {{ $t('cash_register.detail.title', { number: session.number }) }}
        </h2>
        <ion-button
          fill="outline"
          data-testid="cash-register-detail-print"
          @click="printReport"
        >
          <HubIcon
            slot="start"
            name="ion:receipt-outline"
          />
          {{ $t('cash_register.detail.print') }}
        </ion-button>
      </header>
      <SessionSummary :session="session" />
      <h3>{{ $t('cash_register.detail.movements') }}</h3>
      <SessionLines
        :query="{ session_id: session.id }"
        testid="cash-register-session-movements"
        :empty-message="$t('cash_register.detail.noMovements')"
      />
      <h3>{{ $t('cash_register.detail.counts') }}</h3>
      <SessionCounts :session-id="session.id" />
      <div
        class="cash-detail__paper"
        aria-hidden="true"
      >
        <ClosingReport
          ref="report"
          :session="session"
          :printed-at="printedAt"
        />
      </div>
    </div>
  </AppPage>
</template>

<style scoped>
.cash-detail {
  display: grid;
  gap: 0.85rem;
}
.cash-detail__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.cash-detail__header h2 {
  flex: 1;
  margin: 0;
  font-size: 1.15rem;
}
.cash-detail__header ion-button {
  min-height: 44px;
  margin: 0;
}
.cash-detail__header ion-button ion-icon {
  margin-inline-end: 0.35rem;
}
.cash-detail h3 {
  margin: 0.75rem 0 0;
  font-size: 1rem;
}
.cash-detail__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
/* The paper only shows on paper: printPaper copies it into its own print root. */
.cash-detail__paper {
  display: none;
}
</style>
