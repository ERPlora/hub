<script setup lang="ts">
// «Review what it brings» (BASE-G105; the old hub's ImportPanel review): what a template or a file is — name, type,
// language and country by name, how many apps, when a file was made —, one box per app with what it brings, ticked
// when the app is on here or the load turns it on (`turns_on`: an app the blueprint lists that is off, round
// 2026-10-27, says so); an app left off or that this hub does not have, and personal data in a template, say they stay
// out. What this hub never loads (people, fiscal data…) is listed. «Import» emits the apps ticked, in the file's order;
// the page imports them and passes back `pending` and the reason it failed.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonCheckbox } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useBaseI18n } from '../../lib/i18n';
import type { BlueprintSummary } from '../../operations';
import '../../data.css';

const props = withDefaults(defineProps<{ summary: BlueprintSummary; pending?: boolean; error?: string }>(), {
  pending: false,
  error: '',
});
const emit = defineEmits<{ import: [apps: string[]]; back: [] }>();

const { t, locale } = useBaseI18n();

/** The statuses of an app that loads: on here, or turned on by the load first. */
const LOADS = new Set(['on', 'turns_on']);
const loads = (status: string): boolean => LOADS.has(status);
const onHere = computed(() => props.summary.apps.filter((app) => loads(app.status)).map((app) => app.id));
const ticked = ref(new Set<string>());
watch(onHere, (ids) => (ticked.value = new Set(ids)), { immediate: true });

const chosen = computed(() => onHere.value.filter((id) => ticked.value.has(id)));
const nothingLoads = computed(() => onHere.value.length === 0);

function tick(app: string, checked: boolean): void {
  const next = new Set(ticked.value);
  if (checked) next.add(app);
  else next.delete(app);
  ticked.value = next;
}

function displayName(code: string, type: 'language' | 'region'): string {
  if (!code) return '—';
  try {
    return new Intl.DisplayNames([locale.value], { type }).of(type === 'region' ? code.toUpperCase() : code) ?? code;
  } catch {
    return code;
  }
}

const created = computed(() => {
  if (!props.summary.created_at) return '';
  const date = new Date(props.summary.created_at);
  return Number.isNaN(date.getTime())
    ? props.summary.created_at
    : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
});

function appNote(status: string): string {
  if (status === 'turns_on') return t('base.data.review.appTurnsOn');
  if (status === 'inactive') return t('base.data.review.appOff');
  if (status === 'unknown') return t('base.data.review.appUnknown');
  return '';
}
</script>

<template>
  <section
    class="data-card"
    data-testid="review"
  >
    <h3 class="data-title">
      {{ t('base.data.review.title') }}
    </h3>
    <dl
      class="data-facts"
      data-testid="review-facts"
    >
      <div>
        <dt>{{ t('base.data.review.name') }}</dt>
        <dd>{{ summary.name }}</dd>
      </div>
      <div>
        <dt>{{ t('base.data.review.kind') }}</dt>
        <dd>{{ summary.purpose === 'backup' ? t('base.data.review.backup') : t('base.data.review.template') }}</dd>
      </div>
      <div>
        <dt>{{ t('base.data.import.language') }}</dt>
        <dd>{{ displayName(summary.language, 'language') }}</dd>
      </div>
      <div>
        <dt>{{ t('base.data.import.country') }}</dt>
        <dd>{{ displayName(summary.country, 'region') }}</dd>
      </div>
      <div>
        <dt>{{ t('base.data.review.apps') }}</dt>
        <dd>{{ summary.apps.length }}</dd>
      </div>
      <div v-if="created">
        <dt>{{ t('base.data.review.created') }}</dt>
        <dd>{{ created }}</dd>
      </div>
    </dl>

    <p class="data-hint">
      {{ t('base.data.review.appsHint') }}
    </p>
    <ul class="data-rows">
      <li
        v-for="app in summary.apps"
        :key="app.id"
        class="data-row"
        data-testid="review-app"
        :data-id="app.id"
      >
        <ion-checkbox
          :checked="loads(app.status) && ticked.has(app.id)"
          :disabled="!loads(app.status) || pending"
          label-placement="end"
          justify="start"
          @ion-change="tick(app.id, $event.detail.checked)"
        >
          <span class="data-row-name">{{ app.label }}</span>
        </ion-checkbox>
        <div class="data-row-main">
          <p
            v-if="appNote(app.status)"
            class="data-row-detail"
          >
            {{ appNote(app.status) }}
          </p>
          <p
            v-for="dataset in app.datasets"
            :key="dataset.key"
            class="data-row-detail"
          >
            {{ dataset.label }} · {{ dataset.rows }}
            <template v-if="!dataset.travels">
              — {{ t('base.data.review.personal') }}
            </template>
          </p>
        </div>
      </li>
    </ul>

    <div
      v-if="summary.dropped.length"
      class="data-hint"
      data-testid="review-dropped"
    >
      <strong>{{ t('base.data.review.dropped') }}:</strong>
      {{ summary.dropped.join(' · ') }}
    </div>

    <InlineFeedback
      v-if="nothingLoads"
      tone="warning"
    >
      {{ t('base.data.review.nothingLoads') }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="!chosen.length"
      tone="info"
    >
      {{ t('base.data.review.noApps') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="review-error"
    >
      {{ t('base.data.review.importError', { reason: error }) }}
    </InlineFeedback>

    <div class="data-actions">
      <ion-button
        data-testid="review-import"
        :disabled="pending || !chosen.length"
        @click="emit('import', chosen)"
      >
        {{ pending ? t('base.data.review.importing') : t('base.data.review.import') }}
      </ion-button>
      <ion-button
        fill="outline"
        data-testid="review-back"
        :disabled="pending"
        @click="emit('back')"
      >
        {{ t('base.data.review.back') }}
      </ion-button>
    </div>
  </section>
</template>
