<script setup lang="ts">
// The options of a step (WORKBOOK FLOW-F25; the old engine's `run_if` and `on_error`), folded under
// «More options»: «Only if…» on every step but «Only continue if…» — when it does not hold the step is
// skipped and the automation goes on — and «If it fails, carry on with the next steps» on an action or
// a read or a call (FLOW-F27). Off, the step keeps no option at all (the document stays as it was).
import { IonCheckbox } from '@ionic/vue';
import { computed, ref } from 'vue';

import type { DataChoice } from '../lib/document';
import type { CatalogOut, Condition, Step } from '../operations';
import ConditionRows from './ConditionRows.vue';

type Optionable = Exclude<Step, { kind: 'condition' }>;

const props = defineProps<{
  step: Optionable;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The data this step can insert (for its «Only if…»). */
  choices: readonly DataChoice[];
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();

const id = computed(() => props.step.id);
const canFail = computed(() => props.step.kind === 'command' || props.step.kind === 'query' || props.step.kind === 'http');
const onError = computed(() => (props.step.kind === 'delay' || props.step.kind === 'ask' ? false : props.step.on_error === 'continue'));
const open = ref(!!props.step.run_if || onError.value);

function without<T extends object>(value: T, key: string): T {
  const next = { ...value } as Record<string, unknown>;
  delete next[key];
  return next as T;
}

function setRunIf(on: boolean): void {
  emit('update:step', on ? { ...props.step, run_if: props.step.run_if ?? {} } : without(props.step, 'run_if'));
}

function setCondition(runIf: Condition): void {
  emit('update:step', { ...props.step, run_if: runIf });
}

function setOnError(on: boolean): void {
  if (props.step.kind === 'delay' || props.step.kind === 'ask') return;
  emit('update:step', on ? { ...props.step, on_error: 'continue' } : without(props.step, 'on_error'));
}
</script>

<template>
  <div class="flow-options">
    <button
      type="button"
      class="flow-options__toggle"
      :aria-expanded="open ? 'true' : 'false'"
      :data-testid="`flow-step-options-toggle-${id}`"
      @click="open = !open"
    >
      {{ $t('flow.steps.options.toggle') }}
    </button>
    <div
      v-if="open"
      class="flow-options__panel"
      :data-testid="`flow-step-options-${id}`"
    >
      <IonCheckbox
        :checked="!!step.run_if"
        label-placement="end"
        justify="start"
        :data-testid="`flow-step-runif-${id}`"
        @ion-change="setRunIf($event.detail.checked)"
      >
        {{ $t('flow.steps.options.runIf') }}
      </IonCheckbox>
      <template v-if="step.run_if">
        <span
          class="flow-card__hint"
          :data-testid="`flow-step-runif-hint-${id}`"
        >{{ $t('flow.steps.options.runIfHint') }}</span>
        <ConditionRows
          :testid="`flow-step-runif-cond-${id}`"
          :model-value="step.run_if"
          :choices="choices"
          :pick="pick"
          :steps="steps"
          :catalog="catalog"
          @update:model-value="setCondition"
        />
      </template>
      <template v-if="canFail">
        <IonCheckbox
          :checked="onError"
          label-placement="end"
          justify="start"
          :data-testid="`flow-step-onerror-${id}`"
          @ion-change="setOnError($event.detail.checked)"
        >
          {{ $t('flow.steps.options.onError') }}
        </IonCheckbox>
        <span
          v-if="onError"
          class="flow-card__hint"
          :data-testid="`flow-step-onerror-hint-${id}`"
        >{{ $t('flow.steps.options.onErrorHint') }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.flow-options {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.flow-options__toggle {
  align-self: flex-start;
  min-height: 2.6rem;
  padding: 0 0.25rem;
  border: 0;
  background: transparent;
  color: var(--ion-color-primary);
  font: inherit;
  cursor: pointer;
}
.flow-options__panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-left: 0.25rem;
}
.flow-options__panel ion-checkbox {
  --size: 1.2rem;
  white-space: normal;
}
</style>
