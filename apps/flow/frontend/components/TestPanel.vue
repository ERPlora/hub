<script setup lang="ts">
// «Try it» (WORKBOOK FLOW-F13; `flow.flow.test`): what the automation WOULD do with the last thing that
// really happened in this business, step by step, and executing nothing. It takes the editor's
// document as it is, saved or not, and the saved automation's permissions. It says what would come out
// empty, what the action would refuse (the server validates the data against the action), where a
// condition would stop it (that is the automation working), what depends on a step that has not run,
// and what it is not allowed yet. A datum an «Ask the assistant» step fixes is said as the card of the change says it
// (FLOW-F29, base's `fieldText`): a record by its name, an amount in the currency the server gives it, never an id.
import { InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onMounted, ref, shallowRef } from 'vue';

import { type AssistantField, fieldText } from '../../../../base/frontend/lib/assistant-card';
import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import { cleanTrigger, type FlowDocument } from '../lib/document';
import { actionLabel, describeClause, describeDuration, describeStep, eventLabel, fieldLabel } from '../lib/phrasing';
import type { CatalogOut, PinnedOut, TestOut, TestStepOut } from '../operations';

const props = defineProps<{ document: FlowDocument; flowId: string | null; catalog: CatalogOut | null }>();
const client = useLiveClient();
const phrasing = usePhrasing();

const result = shallowRef<TestOut | null>(null);
const error = shallowRef<ApiError | null>(null);
const loading = ref(false);

async function run(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const document = JSON.stringify({ trigger: cleanTrigger(props.document.trigger), steps: props.document.steps });
    result.value = await client.api.call('flow.flow.test', { document, ...(props.flowId ? { id: props.flowId } : {}) });
  } catch (failure) {
    error.value = failure as ApiError;
    result.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(run);

const sampleLine = computed(() => {
  const answer = result.value;
  if (!answer) return '';
  if (answer.sample.found) {
    const date = answer.sample.at ? new Intl.DateTimeFormat(phrasing.value.locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(answer.sample.at)) : '';
    return phrasing.value.t('flow.test.with', { event: eventLabel(answer.sample.event, props.catalog, phrasing.value), date });
  }
  return props.document.trigger.kind === 'event' ? phrasing.value.t('flow.test.noSample') : phrasing.value.t('flow.test.noEvent');
});

function stepOf(id: string) {
  return props.document.steps.find((step) => step.id === id);
}

/** What a step would send; a call's host is already in its verdict. */
function shownParams(step: TestStepOut): Record<string, unknown> {
  // What it would ask is its verdict; the names of what it may use are not words for a person.
  if (step.outcome === 'would_ask_assistant') return {};
  if (step.outcome === 'would_ask') return Object.fromEntries(Object.entries(step.params).filter(([field]) => field === 'title' || field === 'details'));
  if (step.kind !== 'http') return step.params;
  // A call in words: its host is in the verdict, each header is «Name: value», nothing empty.
  const out: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(step.params)) {
    const text = field === 'headers' && value && typeof value === 'object' ? Object.entries(value).map(([name, said]) => `${name}: ${String(said)}`).join(' · ') : value;
    if (field !== 'host' && text !== '' && text !== null && text !== undefined) out[field] = text;
  }
  return out;
}

function outcome(step: TestStepOut): string {
  const own = stepOf(step.id);
  const action = own?.kind === 'http' ? describeStep(own, props.document.steps, props.catalog, phrasing.value) : step.operation ? actionLabel(step.operation, props.catalog, phrasing.value) : '';
  if (step.outcome === 'would_call') return phrasing.value.t('flow.test.outcomes.would_call', { host: String(step.params.host ?? '') });
  if (step.outcome === 'would_ask_assistant') return phrasing.value.t('flow.test.outcomes.would_ask_assistant', { prompt: String(step.params.prompt ?? '') });
  if (step.outcome === 'would_ask') {
    const who = phrasing.value.t(`flow.ask.roles.${String(step.params.role || 'admin')}`);
    return phrasing.value.t('flow.test.outcomes.would_ask', { who, hours: Number(step.params.hours ?? 72) });
  }
  if (step.outcome === 'waits') return phrasing.value.t('flow.test.outcomes.waits', { duration: describeDuration(step.seconds ?? 0, phrasing.value) });
  return phrasing.value.t(`flow.test.outcomes.${step.outcome}`, { action });
}

function shown(value: unknown): string {
  return typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value);
}

const names = (fields: readonly string[]): string => fields.map((field) => fieldLabel(field, phrasing.value)).join(', ');

/** «Cancel a reservation › On behalf of the customer»: a datum an «Ask the assistant» step fixes. */
const pinnedLabel = (row: PinnedOut): string => `${actionLabel(row.tool, props.catalog, phrasing.value)} › ${fieldLabel(row.field, phrasing.value)}`;
const pinnedIn = (step: TestStepOut, state: PinnedOut['state']): PinnedOut[] => (step.pinned ?? []).filter((row) => row.state === state);
/** The fixed data that would be filled in, each in the card's words; one the card leaves out has no row. */
const pinnedSaid = (step: TestStepOut) => pinnedIn(step, 'filled').filter((row): row is PinnedOut & { said: AssistantField } => row.said !== null);
const saidText = (said: AssistantField): string => fieldText(said, { locale: phrasing.value.locale, t: phrasing.value.t });

/** Each tool that would not be used, with its fixed data that would be empty in this trial. */
function unusedTools(step: TestStepOut): { tool: string; text: string }[] {
  const empty = pinnedIn(step, 'empty');
  return [...new Set(empty.map((row) => row.tool))].map((tool) => ({
    tool,
    text: phrasing.value.t('flow.test.pinnedEmpty', {
      action: actionLabel(tool, props.catalog, phrasing.value),
      fields: empty.filter((row) => row.tool === tool).map((row) => `«${fieldLabel(row.field, phrasing.value)}»`).join(', '),
    }),
  }));
}
</script>

<template>
  <div class="flow-test">
    <InlineFeedback
      tone="warning"
      data-testid="flow-test-banner"
    >
      {{ $t('flow.test.banner') }}
    </InlineFeedback>
    <div
      v-if="loading && !result"
      class="flow-test__loading"
      data-testid="flow-test-loading"
    >
      <IonSpinner name="dots" /> {{ $t('flow.test.loading') }}
    </div>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="flow-test-error"
    >
      {{ wording(error, $t('flow.errors.read')) }}
    </InlineFeedback>
    <template v-if="result">
      <p
        class="flow-test__sample"
        data-testid="flow-test-sample"
      >
        {{ sampleLine }}
      </p>
      <InlineFeedback
        v-if="!result.starts"
        tone="warning"
        data-testid="flow-test-notstart"
      >
        {{ $t('flow.test.notStart') }}
        {{ result.trigger_failed.map((clause) => describeClause(clause, document.steps, catalog, phrasing)).join('; ') }}
      </InlineFeedback>
      <div
        v-for="step in result.steps"
        :key="step.id"
        class="flow-test__step"
        :data-outcome="step.outcome"
        :data-testid="`flow-test-step-${step.id}`"
      >
        <strong>{{ stepOf(step.id) ? describeStep(stepOf(step.id)!, document.steps, catalog, phrasing) : step.id }}</strong>
        <span class="flow-test__verdict">{{ outcome(step) }}</span>
        <div
          v-for="(value, field) in shownParams(step)"
          :key="field"
          class="flow-test__value"
        >
          <span class="flow-test__key">{{ fieldLabel(String(field), phrasing) }}</span>
          <span>{{ shown(value) }}</span>
        </div>
        <div
          v-for="row in pinnedSaid(step)"
          :key="`${row.tool}|${row.field}`"
          class="flow-test__value"
          :data-testid="`flow-test-pinned-${step.id}-${row.tool}-${row.field}`"
        >
          <span class="flow-test__key">{{ pinnedLabel(row) }}</span>
          <span>{{ saidText(row.said) }}</span>
        </div>
        <span
          v-for="unused in unusedTools(step)"
          :key="unused.tool"
          class="flow-test__bad"
          :data-testid="`flow-test-pinnedempty-${step.id}-${unused.tool}`"
        >{{ unused.text }}</span>
        <span
          v-if="pinnedIn(step, 'unknown').length"
          class="flow-test__note"
          :data-testid="`flow-test-pinnedunknown-${step.id}`"
        >{{ $t('flow.test.unknown', { fields: pinnedIn(step, 'unknown').map(pinnedLabel).join(', ') }) }}</span>
        <span
          v-if="step.empty.length"
          class="flow-test__bad"
        >{{ $t('flow.test.empty', { fields: names(step.empty) }) }}</span>
        <span
          v-if="step.unknown.length"
          class="flow-test__note"
        >{{ $t('flow.test.unknown', { fields: names(step.unknown) }) }}</span>
        <span
          v-for="(message, field) in step.errors"
          :key="field"
          class="flow-test__bad"
        >{{ fieldLabel(String(field), phrasing) }}: {{ message }}</span>
        <ul
          v-if="step.failed.length"
          class="flow-test__clauses"
        >
          <li
            v-for="(clause, index) in step.failed"
            :key="index"
          >
            {{ describeClause(clause, document.steps, catalog, phrasing) }}
          </li>
        </ul>
      </div>
    </template>
    <IonButton
      size="small"
      fill="outline"
      mode="md"
      data-testid="flow-test-again"
      :disabled="loading"
      @click="run"
    >
      {{ $t('flow.test.again') }}
    </IonButton>
  </div>
</template>

<style scoped>
.flow-test {
  max-width: 44rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-test > ion-button {
  align-self: flex-start;
}
.flow-test__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-test__sample {
  margin: 0;
  font-size: 0.9rem;
}
.flow-test__step {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-left: 3px solid var(--ep-border, #d7d5cc);
  border-radius: 10px;
  background: var(--ep-surface, #fff);
}
.flow-test__step[data-outcome='would_run'],
.flow-test__step[data-outcome='would_call'],
.flow-test__step[data-outcome='would_ask'],
.flow-test__step[data-outcome='would_ask_assistant'],
.flow-test__step[data-outcome='waits'] {
  border-left-color: var(--ion-color-success);
}
.flow-test__step[data-outcome='stops_here'],
.flow-test__step[data-outcome='cannot_tell'] {
  border-left-color: var(--ion-color-warning);
}
.flow-test__step[data-outcome='refused'],
.flow-test__step[data-outcome='high_risk'],
.flow-test__step[data-outcome='not_allowed'],
.flow-test__step[data-outcome='unavailable'] {
  border-left-color: var(--ion-color-danger);
}
.flow-test__step[data-outcome='not_reached'] {
  opacity: 0.6;
}
.flow-test__verdict {
  font-size: 0.88rem;
}
.flow-test__value {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  font-size: 0.88rem;
}
.flow-test__key {
  min-width: 6rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-test__bad {
  font-size: 0.85rem;
  color: var(--ion-color-danger);
}
.flow-test__note {
  font-size: 0.85rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-test__clauses {
  margin: 0;
  padding-left: 1rem;
  font-size: 0.85rem;
}
</style>
