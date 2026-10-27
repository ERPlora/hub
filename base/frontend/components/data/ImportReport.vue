<script setup lang="ts">
// «Import report» (BASE-G106; the old hub's ImportPanel report) and the last import that did not go in whole
// (BASE-G107, `unfinished`): how it went, app by app and part by part, in words and tone — a status this screen does
// not know is «Failed» with its own text, never a success —, what went wrong (an app of the blueprint the load could
// not turn on says why: the plan's limit, no right to it), what was left out on purpose, and
// «Retry what is missing» when the server says it can; when it cannot because the file came by hand or the template's
// version is gone, the button stays off with why. «See the templates» and «Go to Home» leave the report.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import { RETRY_BLOCKED_KEY, statusPill } from '../../lib/data';
import { useBaseI18n } from '../../lib/i18n';
import type { ImportRow } from '../../operations';
import '../../data.css';

const props = withDefaults(
  defineProps<{ load: ImportRow; unfinished?: boolean; retrying?: boolean; retryError?: string }>(),
  { unfinished: false, retrying: false, retryError: '' },
);
const emit = defineEmits<{ retry: []; templates: [] }>();

const { t, locale } = useBaseI18n();
const router = useRouter();

const HEADLINE = {
  complete: { tone: 'success', key: 'base.data.report.complete' },
  partial: { tone: 'warning', key: 'base.data.report.partial' },
  failed: { tone: 'danger', key: 'base.data.report.failed' },
} as const;
const headline = computed(() => HEADLINE[props.load.report.status] ?? HEADLINE.failed);

const when = computed(() => {
  const date = new Date(props.load.created_at);
  return Number.isNaN(date.getTime())
    ? props.load.created_at
    : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
});

/** A retry that cannot run for a reason the person can act on: the button stays, off, with why. */
const blockedReason = computed(() => {
  const blocked = props.load.retry_blocked;
  return blocked === 'file' || blocked === 'version_gone' ? t(RETRY_BLOCKED_KEY[blocked]) : '';
});

function pill(status: string): { tone: ReturnType<typeof statusPill>['tone']; label: string; raw: string } {
  const look = statusPill(status);
  return { tone: look.tone, label: t(look.key), raw: look.raw ?? '' };
}
</script>

<template>
  <section
    class="data-card"
    data-testid="report"
  >
    <h3 class="data-title">
      {{ t('base.data.report.title') }}
    </h3>

    <InlineFeedback
      v-if="unfinished"
      tone="warning"
      class="report-notice"
      data-testid="report-unfinished"
    >
      {{ t('base.data.report.unfinished', { name: load.name, date: when }) }}
    </InlineFeedback>
    <InlineFeedback
      v-else
      :tone="headline.tone"
      class="report-notice"
      data-testid="report-status"
    >
      {{ t(headline.key) }}
    </InlineFeedback>

    <ul class="data-rows">
      <li
        v-for="app in load.report.apps"
        :key="app.id"
        class="data-row"
        data-testid="report-app"
        :data-id="app.id"
      >
        <div class="data-row-main">
          <span class="data-row-name">{{ app.label }}</span>
          <p
            v-if="app.reason"
            class="data-row-detail"
            data-testid="report-app-reason"
          >
            {{ app.reason }}
          </p>
          <p
            v-if="pill(app.status).raw"
            class="data-row-detail"
          >
            {{ pill(app.status).raw }}
          </p>
          <div
            v-for="dataset in app.datasets"
            :key="dataset.key"
            class="report-dataset"
          >
            <p class="data-row-detail">
              {{ dataset.label }} ·
              {{ t('base.data.report.counts', { created: dataset.created, already: dataset.already, failed: dataset.failed }) }}
            </p>
            <ul
              v-if="dataset.problems.length"
              class="data-problems"
            >
              <li
                v-for="problem in dataset.problems"
                :key="problem"
              >
                {{ problem }}
              </li>
            </ul>
          </div>
        </div>
        <StatusPill
          :tone="pill(app.status).tone"
          :label="pill(app.status).label"
          data-testid="report-app-status"
        />
      </li>
    </ul>

    <p
      v-if="load.report.dropped.length"
      class="data-hint"
      data-testid="report-dropped"
    >
      <strong>{{ t('base.data.report.dropped') }}:</strong>
      {{ load.report.dropped.join(' · ') }}
    </p>

    <InlineFeedback
      v-if="retryError"
      tone="danger"
      class="report-notice"
      data-testid="report-retry-error"
    >
      {{ t('base.data.report.retryError', { reason: retryError }) }}
    </InlineFeedback>
    <p
      v-if="blockedReason"
      class="data-hint"
      data-testid="report-retry-blocked"
    >
      {{ blockedReason }}
    </p>

    <div class="data-actions">
      <ion-button
        v-if="load.retry || blockedReason"
        data-testid="report-retry"
        :disabled="!load.retry || retrying"
        @click="emit('retry')"
      >
        {{ retrying ? t('base.data.report.retrying') : t('base.data.report.retry') }}
      </ion-button>
      <ion-button
        fill="outline"
        data-testid="report-templates"
        :disabled="retrying"
        @click="emit('templates')"
      >
        {{ t('base.data.report.templates') }}
      </ion-button>
      <ion-button
        fill="clear"
        data-testid="report-home"
        @click="router.push('/')"
      >
        {{ t('base.data.report.home') }}
      </ion-button>
    </div>
  </section>
</template>

<style scoped>
.report-notice {
  margin-top: 12px;
}

.report-dataset {
  margin-top: 2px;
}
</style>
