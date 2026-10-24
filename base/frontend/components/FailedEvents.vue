<script setup lang="ts">
// System › Failed events (BASE-G91…G94; the old hub's SystemPage `#events`, HUB_SHELL-F145…F148), for who runs the
// business (the page shows anyone else who may see it): the live `base.failed_event.list`, the 100 most recent events
// between apps the relay gave up on — which event, from which app to which, its attempts, when and its last error —,
// re-run when the relay gives one up and when one is resent or discarded, so the bell and this list never disagree.
// «Resend» puts one back in the queue (not when the app it was for is off: the row says why); «Resend all» asks
// first; «Discard» closes one for good in the product's dialog, with what is lost and an optional reason. Each action
// has its label (the old icons had none) and a refusal is told from its code. A failed read is never «All in order»
// (it may be fiscal): it says so, with «Retry» in sight (hub#2540).
import { ConfirmDialog, EmptyState, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonTextarea } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import { failureKey } from '../lib/system';
import type { FailedEvent } from '../operations';

/** The most the list shows: the old hub's; «Resend all» reaches the ones beyond it too. */
const SHOWN = 100;

const { t, locale } = useBaseI18n();
const { confirm } = useConfirm();

const { data, status, refresh } = useLive('base.failed_event.list', { limit: SHOWN });
const retry = useCommand('base.failed_event.retry');
const retryAll = useCommand('base.failed_event.retry_all');
const discard = useCommand('base.failed_event.discard');

const items = computed<FailedEvent[]>(() => data.value?.items ?? []);
const total = computed(() => data.value?.total ?? 0);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const loading = computed(() => data.value === undefined && !failed.value);
/** The row being resent: only its button waits. */
const resending = ref<string | null>(null);
const discarding = ref<FailedEvent | null>(null);
const discardOpen = ref(false);
const reason = ref('');

const when = (iso: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));

function why(error: unknown): string {
  return t(failureKey((error as ApiError | undefined)?.code));
}

async function resend(item: FailedEvent): Promise<void> {
  resending.value = item.id;
  try {
    await retry.run({ id: item.id });
    void toastSuccess(t('base.system.failed.retried'));
  } catch (error) {
    void toastError(t('base.system.failed.retryFailed', { reason: why(error) }));
  } finally {
    resending.value = null;
  }
}

async function resendAll(): Promise<void> {
  const yes = await confirm({
    title: t('base.system.failed.retryAllConfirm.title'),
    message: t('base.system.failed.retryAllConfirm.message'),
    confirmLabel: t('base.system.failed.retryAll'),
    cancelLabel: t('base.system.failed.discardConfirm.cancel'),
    tone: 'primary',
  });
  if (!yes) return;
  try {
    const { count } = await retryAll.run({});
    void toastSuccess(
      count ? t('base.system.failed.retriedAll', { count }) : t('base.system.failed.nothingToRetry'),
    );
  } catch (error) {
    void toastError(t('base.system.failed.retryFailed', { reason: why(error) }));
  }
}

function askDiscard(item: FailedEvent): void {
  discarding.value = item;
  reason.value = '';
  discard.error.value = null;
  discardOpen.value = true;
}

async function confirmDiscard(): Promise<void> {
  const item = discarding.value;
  if (!item) return;
  try {
    await discard.run({ id: item.id, reason: reason.value.trim() });
    discardOpen.value = false;
    void toastSuccess(t('base.system.failed.discarded'));
  } catch (error) {
    discardOpen.value = false;
    void toastError(t('base.system.failed.discardFailed', { reason: why(error) }));
  }
}
</script>

<template>
  <section class="failed-events">
    <header class="failed-events-head">
      <h2>{{ t('base.system.failed.heading') }}</h2>
      <ion-button
        v-if="items.length"
        size="small"
        fill="outline"
        data-testid="failed-events-retry-all"
        :disabled="retryAll.pending.value"
        @click="resendAll()"
      >
        {{ t('base.system.failed.retryAll') }}
      </ion-button>
    </header>
    <p
      v-if="loading"
      class="failed-events-muted"
      data-testid="failed-events-loading"
      role="status"
    >
      {{ t('base.system.failed.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="failed-events-error"
      :heading="t('base.system.error.heading')"
    >
      {{ t('base.system.failed.errorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="failed-events-reload"
          @click="refresh()"
        >
          {{ t('base.system.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <EmptyState
      v-else-if="!items.length"
      icon="ion:checkmark-circle-outline"
      data-testid="failed-events-empty"
      :heading="t('base.system.failed.empty.heading')"
      :message="t('base.system.failed.empty.body')"
    />
    <template v-else>
      <p class="failed-events-muted">
        {{ t('base.system.failed.hint') }}
      </p>
      <ul class="failed-events-list">
        <li
          v-for="item in items"
          :key="item.id"
          class="failed-event"
          data-testid="failed-event-row"
        >
          <div class="failed-event-head">
            <code class="failed-event-name">{{ item.name }}</code>
            <StatusPill
              tone="warning"
              size="sm"
              :dot="false"
              :label="t('base.system.failed.attempts', { n: item.attempts })"
            />
          </div>
          <p class="failed-event-route">
            {{ t('base.system.failed.route', { source: item.source_app_name, target: item.target_app_name }) }}
            · {{ when(item.occurred_at) }}
          </p>
          <pre class="failed-event-error">{{ item.last_error }}</pre>
          <p
            v-if="!item.retryable"
            class="failed-event-stuck"
            data-testid="failed-event-not-retryable"
          >
            {{ t('base.system.failed.notRetryable', { app: item.target_app_name }) }}
          </p>
          <div class="failed-event-actions">
            <ion-button
              v-if="item.retryable"
              size="small"
              fill="solid"
              data-testid="failed-event-retry"
              :disabled="resending === item.id"
              @click="resend(item)"
            >
              {{ t('base.system.failed.retry') }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              color="danger"
              data-testid="failed-event-discard"
              @click="askDiscard(item)"
            >
              {{ t('base.system.failed.discard') }}
            </ion-button>
          </div>
        </li>
      </ul>
      <p
        v-if="total > items.length"
        class="failed-events-muted"
        data-testid="failed-events-more"
      >
        {{ t('base.system.failed.more', { shown: items.length, total }) }}
      </p>
    </template>
    <ConfirmDialog
      v-model:open="discardOpen"
      testid="failed-event-discard-dialog"
      tone="danger"
      :title="t('base.system.failed.discardConfirm.title')"
      :confirm-label="t('base.system.failed.discardConfirm.confirm')"
      :cancel-label="t('base.system.failed.discardConfirm.cancel')"
      :pending="discard.pending.value"
      @confirm="confirmDiscard()"
      @cancel="discardOpen = false"
    >
      <p class="ep-confirm-dialog__text">
        {{
          discarding
            ? t('base.system.failed.discardConfirm.message', { event: discarding.name, app: discarding.target_app_name })
            : ''
        }}
      </p>
      <p class="failed-event-stuck">
        {{ t('base.system.failed.discardConfirm.consequence') }}
      </p>
      <ion-textarea
        data-testid="failed-event-discard-reason"
        :value="reason"
        :label="t('base.system.failed.discardConfirm.reason')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :auto-grow="true"
        :maxlength="500"
        @ion-input="reason = $event.detail.value ?? ''"
      />
    </ConfirmDialog>
  </section>
</template>

<style scoped>
.failed-events {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.failed-events-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.failed-events-head h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.failed-events-muted {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.failed-events-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.failed-event {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.failed-event-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.failed-event-name {
  font-size: 0.9375rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.failed-event-route,
.failed-event-stuck {
  margin: 0;
  font-size: 0.875rem;
}

.failed-event-route {
  color: var(--ion-color-medium-shade, #555);
}

.failed-event-stuck {
  color: var(--ion-color-warning-shade, #8a6d00);
}

.failed-event-error {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--ion-color-light, #f4f5f8);
  font-size: 0.8125rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.failed-event-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
</style>
