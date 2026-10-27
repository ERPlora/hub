<script setup lang="ts">
// «Print queue» (PRINTING-F01; the old screen's queue zone): one card per role that has an active printer
// or jobs (a new business sees none), with its state — «Ready», «Waiting, no printer», «No device» (jobs no
// device set up here can print: where the bell's «Nothing is printing “…”» leads, it says why), «With errors» —,
// «Waiting: N · the oldest has waited 3 min» or «Nothing waiting», the failed ones and the printer it prints
// on now (the chosen one, else the first active one: named, never counted — hub#1527). A role with jobs waiting for over a minute and no active printer raises the orange alert
// with its cause. Nothing waiting, sent unconfirmed or failed: «All clear». Live: every job that changes re-runs
// it; the ages and the alert move on by themselves every 30 s (`useNow`). A failed read says so, with «Retry», and never «All clear».
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, watch } from 'vue';

import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { waited } from '../lib/format';
import type { UsageSummary } from '../operations';

/** A job waiting longer than this on a role nobody prints is worth an alert (the old screen's minute). */
const ALERT_AFTER_MS = 60_000;

const t = useT();
const live = useLive('printing.job.summary', {});
const { data, status, refresh } = live;

const now = useNow();
// A new result is measured against the moment it arrived.
watch(data, () => (now.value = new Date()));

const cards = computed(() => (data.value?.usages ?? []).filter((u) => u.printers > 0 || u.pending > 0 || u.failed > 0));
const alerts = computed(() =>
  (data.value?.usages ?? []).filter(
    (u) => u.printers === 0 && u.pending > 0 && !!u.oldest_pending_at && now.value.getTime() - new Date(u.oldest_pending_at).getTime() >= ALERT_AFTER_MS,
  ),
);
// Nothing waiting, nothing a device has without confirming, nothing failed.
const allClear = computed(
  () => !!data.value && data.value.pending === 0 && data.value.sent === 0 && data.value.failed === 0 && status.value !== 'error',
);
const failed = computed(() => status.value === 'error');

function stateOf(u: UsageSummary): { tone: 'success' | 'warning' | 'danger'; label: string } {
  if (u.printers === 0) return { tone: 'warning', label: t('printing.summary.stalled') };
  if (u.unattended > 0) return { tone: 'warning', label: t('printing.summary.noDevice') };
  if (u.failed > 0) return { tone: 'danger', label: t('printing.summary.failing') };
  return { tone: 'success', label: t('printing.summary.ready') };
}

function waiting(u: UsageSummary): string {
  if (u.pending === 0) return t('printing.summary.nothing');
  const count = t('printing.summary.waiting', { n: u.pending });
  return u.oldest_pending_at ? `${count} · ${t('printing.summary.oldest', { age: waited(u.oldest_pending_at, now.value, t) })}` : count;
}

function alertText(u: UsageSummary): string {
  const named = { n: u.pending, usage: t(`printing.usage.${u.usage}`), age: waited(u.oldest_pending_at ?? '', now.value, t) };
  return u.pending === 1 ? t('printing.summary.alertOne', named) : t('printing.summary.alert', named);
}
</script>

<template>
  <section
    class="printing-summary"
    data-testid="printing-summary"
  >
    <h2
      class="printing-summary__heading"
      data-testid="printing-summary-heading"
    >
      {{ $t('printing.summary.heading') }}
    </h2>

    <p
      v-if="!data && status === 'loading'"
      class="printing-summary__state"
      data-testid="printing-summary-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
    </p>

    <InlineFeedback
      v-if="failed"
      tone="danger"
      icon="cloud-offline-outline"
      data-testid="printing-summary-error"
      :heading="$t('printing.summary.loadError')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="printing-summary-retry"
          @click="refresh()"
        >
          {{ $t('printing.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <InlineFeedback
      v-for="u in alerts"
      :key="`alert-${u.usage}`"
      tone="warning"
      icon="warning-outline"
      :data-testid="`printing-summary-alert-${u.usage}`"
      :heading="alertText(u)"
    >
      {{ $t('printing.summary.alertCause') }}
    </InlineFeedback>

    <div
      v-if="cards.length"
      class="printing-summary__cards"
    >
      <article
        v-for="u in cards"
        :key="u.usage"
        class="printing-summary__card"
        :data-testid="`printing-summary-card-${u.usage}`"
      >
        <header class="printing-summary__card-head">
          <strong>{{ $t(`printing.usage.${u.usage}`) }}</strong>
          <StatusPill
            size="sm"
            v-bind="stateOf(u)"
          />
        </header>
        <p>{{ waiting(u) }}</p>
        <p v-if="u.failed > 0">
          {{ $t('printing.summary.failed', { n: u.failed }) }}
        </p>
        <p
          v-if="u.printers > 0 && u.unattended > 0"
          :data-testid="`printing-summary-no-device-${u.usage}`"
        >
          {{ $t('printing.summary.noDeviceHint') }}
        </p>
        <p
          v-if="u.prints_on"
          class="printing-summary__muted"
          :data-testid="`printing-summary-prints-on-${u.usage}`"
        >
          {{ $t('printing.summary.printsOn', { name: u.prints_on }) }}
        </p>
      </article>
    </div>

    <p
      v-if="allClear"
      class="printing-summary__clear"
      data-testid="printing-summary-all-clear"
    >
      {{ $t('printing.summary.allClear') }}
    </p>
  </section>
</template>

<style scoped>
.printing-summary {
  display: grid;
  gap: 8px;
}
.printing-summary__heading {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
.printing-summary__state {
  display: flex;
  padding: 0.5rem 0.25rem;
  margin: 0;
}
.printing-summary__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 8px;
}
.printing-summary__card {
  display: grid;
  /* A card as tall as its row keeps its lines at the top instead of spreading them. */
  align-content: start;
  gap: 4px;
  padding: 0.75rem 1rem;
  border: 1px solid var(--ion-color-step-150, var(--ion-border-color, #e5e7eb));
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color));
}
.printing-summary__card p {
  margin: 0;
  font-size: 0.875rem;
}
.printing-summary__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.printing-summary__muted,
.printing-summary__clear {
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.printing-summary__clear {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 0.875rem;
}
</style>
