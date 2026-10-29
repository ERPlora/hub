<script setup lang="ts">
// «History» (WORKBOOK FLOW-F16; `flow.run.list`, live): what the automation did, the newest first,
// twenty at a time with «See more» (in live windows of at most 100 rows, `useLiveList`). The runs that
// stopped by an error go on top under «Needs somebody», with how many there are in all. Each run says
// how it ended and when, opens to its steps in words, says why it failed and what to do (the technical
// text folded, for support), and copies its reference. A run stopped by an error at a step that can
// still be resumed offers «Resume from the step that failed» (FLOW-F24; `flow.run.retry`), after a
// confirmation: it does things for real.
import { InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import { describeLog, runStatusPill } from '../lib/phrasing';
import type { CatalogOut, RunOut, RunPageOut, Step } from '../operations';

const props = defineProps<{ flowId: string; steps: readonly Step[]; catalog: CatalogOut | null }>();
const phrasing = usePhrasing();
const { confirm } = useConfirm();
const retrying = useCommand('flow.run.retry');
/** What went wrong resuming a run, by its id. */
const retryProblem = ref<Record<string, string>>({});

const PAGE = 20;
const MAX_WINDOW = 100;
const shown = ref(PAGE);
const windows = computed(() => {
  const out = [];
  for (let offset = 0; offset < shown.value; offset += MAX_WINDOW) out.push({ limit: Math.min(MAX_WINDOW, shown.value - offset), offset });
  return out;
});

const { data, status, error, refresh } = useLiveList('flow.run.list', () => ({ flow_id: props.flowId }), () => windows.value);
const page = computed(() => data.value as RunPageOut | undefined);
const runs = computed(() => page.value?.rows ?? []);
const broken = computed(() => runs.value.filter((run) => run.status === 'failed'));
const rest = computed(() => runs.value.filter((run) => run.status !== 'failed'));
const open = ref<Set<string>>(new Set());

function toggle(id: string): void {
  const next = new Set(open.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  open.value = next;
}

async function copy(id: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(id);
    void toastSuccess(phrasing.value.t('flow.history.copied'));
  } catch {
    // No clipboard (an old webview, a denied permission): the reference is still on screen to read.
  }
}

function when(run: RunOut): string {
  return new Intl.DateTimeFormat(phrasing.value.locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(run.started_at));
}

function advice(code: string): string {
  const key = `flow.history.advice.${code.replaceAll('.', '__')}`;
  return phrasing.value.te(key) ? phrasing.value.t(key) : '';
}

function technical(run: RunOut): string {
  const last = run.log.at(-1)?.error;
  return [run.error_code, last?.technical, last?.fields ? JSON.stringify(last.fields) : ''].filter(Boolean).join(' · ');
}

async function retry(run: RunOut): Promise<void> {
  const t = phrasing.value.t;
  const yes = await confirm({
    title: t('flow.history.retryTitle'),
    message: t('flow.history.retryMessage'),
    tone: 'warning',
    confirmLabel: t('flow.history.retryYes'),
    cancelLabel: t('flow.history.retryNo'),
  });
  if (!yes) return;
  retryProblem.value = { ...retryProblem.value, [run.id]: '' };
  try {
    const resumed = await retrying.run({ id: run.id });
    if (resumed.status === 'failed') retryProblem.value = { ...retryProblem.value, [run.id]: t('flow.history.retriedFailed', { message: resumed.error_message }) };
    else void toastSuccess(t(resumed.status === 'waiting' ? 'flow.history.retriedWaiting' : 'flow.history.retried'));
  } catch (failure) {
    retryProblem.value = { ...retryProblem.value, [run.id]: wording(failure, t('flow.errors.action')) };
  }
}

const attentionText = computed(() => {
  const n = page.value?.failed ?? 0;
  return phrasing.value.t(n === 1 ? 'flow.history.attentionOne' : 'flow.history.attentionMany', { n });
});
</script>

<template>
  <div class="flow-history">
    <div
      v-if="status === 'loading' && !page"
      class="flow-history__loading"
    >
      <IonSpinner name="dots" /> {{ $t('flow.loading') }}
    </div>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="flow-history-error"
    >
      {{ wording(error, $t('flow.errors.read')) }}
      <IonButton
        size="small"
        fill="clear"
        @click="refresh()"
      >
        {{ $t('flow.live.retry') }}
      </IonButton>
    </InlineFeedback>
    <p
      v-if="page && !runs.length"
      class="flow-history__muted"
      data-testid="flow-history-empty"
    >
      {{ $t('flow.history.empty') }}
    </p>
    <section
      v-if="broken.length"
      class="flow-history__attention"
      data-testid="flow-history-attention"
    >
      <h3>{{ $t('flow.history.attention') }}</h3>
      <span class="flow-history__muted">{{ attentionText }}</span>
    </section>
    <div
      v-for="run in [...broken, ...rest]"
      :key="run.id"
      class="flow-history__run"
      :data-testid="`flow-run-${run.id}`"
    >
      <div class="flow-history__head">
        <StatusPill v-bind="runStatusPill(run.status, phrasing, run.log)" />
        <span class="flow-history__when">{{ when(run) }}<template v-if="run.trigger_kind === 'manual'"> · {{ $t('flow.history.byHand') }}</template></span>
        <button
          type="button"
          class="flow-history__icon"
          :aria-label="$t('flow.history.copy')"
          :title="$t('flow.history.copy')"
          :data-testid="`flow-run-copy-${run.id}`"
          @click="copy(run.id)"
        >
          <HubIcon name="ion:copy-outline" />
        </button>
        <button
          type="button"
          class="flow-history__icon"
          :aria-label="$t('flow.history.showSteps')"
          :aria-expanded="open.has(run.id) ? 'true' : 'false'"
          :data-testid="`flow-run-toggle-${run.id}`"
          @click="toggle(run.id)"
        >
          <HubIcon :name="open.has(run.id) ? 'ion:chevron-up-outline' : 'ion:chevron-down-outline'" />
        </button>
      </div>
      <div
        v-if="run.error_message"
        class="flow-history__trouble"
        :data-testid="`flow-run-trouble-${run.id}`"
      >
        <span class="flow-history__why">{{ run.error_message }}</span>
        <span
          v-if="advice(run.error_code)"
          class="flow-history__do"
        >{{ advice(run.error_code) }}</span>
        <details v-if="technical(run)">
          <summary>{{ $t('flow.history.technical') }}</summary>
          <code>{{ technical(run) }}</code>
        </details>
        <IonButton
          v-if="run.resumable"
          class="flow-history__retry"
          size="small"
          fill="outline"
          mode="md"
          :disabled="retrying.pending.value"
          :data-testid="`flow-run-retry-${run.id}`"
          @click="retry(run)"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('flow.history.retry') }}
        </IonButton>
        <span
          v-if="retryProblem[run.id]"
          class="flow-history__why"
          role="alert"
          :data-testid="`flow-run-retry-problem-${run.id}`"
        >{{ retryProblem[run.id] }}</span>
      </div>
      <ul
        v-if="open.has(run.id)"
        class="flow-history__steps"
        :data-testid="`flow-run-steps-${run.id}`"
      >
        <li
          v-for="(entry, index) in run.log"
          :key="index"
        >
          {{ describeLog(entry, steps, catalog, phrasing) }}
        </li>
      </ul>
    </div>
    <IonButton
      v-if="page && runs.length < page.total"
      size="small"
      fill="outline"
      mode="md"
      data-testid="flow-history-more"
      @click="shown += PAGE"
    >
      {{ $t('flow.history.more') }}
    </IonButton>
  </div>
</template>

<style scoped>
.flow-history {
  max-width: 44rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-history > ion-button {
  align-self: flex-start;
}
.flow-history__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.flow-history__muted {
  margin: 0;
  font-size: 0.88rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-history__attention h3 {
  margin: 0.5rem 0 0.15rem;
  font-size: 0.95rem;
  color: var(--ion-color-danger);
}
.flow-history__run {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 10px;
}
.flow-history__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.flow-history__when {
  flex: 1 1 auto;
  font-size: 0.88rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-history__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.6rem;
  min-height: 2.6rem;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.flow-history__trouble {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.88rem;
}
.flow-history__why {
  color: var(--ion-color-danger);
}
.flow-history__retry {
  align-self: flex-start;
  white-space: normal;
}
.flow-history__trouble code {
  font-size: 0.78rem;
  overflow-wrap: anywhere;
}
.flow-history__steps {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.88rem;
}
</style>
