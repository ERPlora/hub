<script setup lang="ts">
// One step of the column (WORKBOOK FLOW-F11; the old editor's step nodes). «Do something» and «Look
// something up» are cards that open to choose the action or read — from this business's, in words,
// searchable — and fill what it asks for: the required fields always, the rest with «Add
// information», each value composed of text and picked data. «Only continue if…» is a dashed chip
// that narrows the line; «Wait» is a label on it. Each step has its handle (`ion-reorder`, the
// finger's gesture) and its ×. «Call another system» is a card named by its host that opens to its form
// (`HttpStepPanel`, FLOW-F27); «Ask someone first», one named by its question (`AskStepPanel`, FLOW-F28).
// Every step but a condition carries «More options» (`StepOptions`, FLOW-F25), and says them under its
// title when closed.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonInput, IonReorder, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { type DataChoice, delayParts, type DelayUnit, NOTIFY_OPERATION, secondsOf } from '../lib/document';
import { actionLabel, describeClause, describeStep, fieldLabel } from '../lib/phrasing';
import type { CatalogOut, Condition, FieldOut, Step } from '../operations';
import AskStepPanel from './AskStepPanel.vue';
import AssistantStepPanel from './AssistantStepPanel.vue';
import ConditionRows from './ConditionRows.vue';
import HttpStepPanel from './HttpStepPanel.vue';
import MessageStepPanel from './MessageStepPanel.vue';
import StepOptions from './StepOptions.vue';
import ValueBox from './ValueBox.vue';

const props = defineProps<{
  step: Step;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  open: boolean;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** The data this step can insert (for its conditions). */
  choices: readonly DataChoice[];
  /** Opens the editor's picker for this step; the chosen path, or `null`. */
  pick: () => Promise<string | null>;
  /** The picker of a call's values, which also offers the secrets and the call's key (FLOW-F27). */
  pickCall?: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step]; remove: []; toggle: [] }>();
const phrasing = usePhrasing();

const UNITS: readonly DelayUnit[] = ['minutes', 'hours', 'days'];
const id = computed(() => props.step.id);
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.${field}`];

// ── Waits ──
const delay = computed(() => (props.step.kind === 'delay' ? delayParts(props.step.seconds) : { amount: 1, unit: 'hours' as DelayUnit }));

function setDelay(amount: number, unit: DelayUnit): void {
  if (props.step.kind !== 'delay') return;
  emit('update:step', { ...props.step, seconds: secondsOf(Math.max(1, amount || 1), unit) });
}

// ── Conditions ──
function setCondition(when: Condition): void {
  if (props.step.kind === 'condition') emit('update:step', { ...props.step, when });
}

// ── Actions and reads ──
const actions = computed<ComboOption[]>(() => {
  const step = props.step;
  if (step.kind !== 'command' && step.kind !== 'query') return [];
  return (props.catalog?.actions ?? [])
    .filter((action) => action.kind === step.kind && !action.ask_first)
    .map((action) => ({ id: action.name, label: actionLabel(action.name, props.catalog, phrasing.value), hint: `${action.app_name} · ${action.name}`, app: action.app_name }))
    .sort((a, b) => a.app.localeCompare(b.app, phrasing.value.locale) || a.label.localeCompare(b.label, phrasing.value.locale))
    .map(({ id: name, label, hint }) => ({ id: name, label, hint }));
});

const action = computed(() => {
  const step = props.step;
  if (step.kind !== 'command' && step.kind !== 'query') return undefined;
  return props.catalog?.actions.find((candidate) => candidate.name === step.operation);
});

const chosenAction = computed<ComboOption | null>(() => {
  const step = props.step;
  if ((step.kind !== 'command' && step.kind !== 'query') || !step.operation) return null;
  return actions.value.find((option) => option.id === step.operation) ?? { id: step.operation, label: actionLabel(step.operation, props.catalog, phrasing.value) };
});

const params = computed<Record<string, unknown>>(() => (props.step.kind === 'command' || props.step.kind === 'query' ? props.step.params : {}));

/** The fields painted: the required ones, then the ones with a value, then values it does not know. */
const shownFields = computed<FieldOut[]>(() => {
  const fields = action.value?.fields ?? [];
  const shown = fields.filter((field) => field.required || field.name in params.value);
  for (const name of Object.keys(params.value)) {
    if (!fields.some((field) => field.name === name)) shown.push({ name, type: 'string', required: false, description: '', choices: [] });
  }
  return shown;
});

const addable = computed(() => (action.value?.fields ?? []).filter((field) => !field.required && !(field.name in params.value)));

function setAction(option: ComboOption | null): void {
  const step = props.step;
  if (step.kind !== 'command' && step.kind !== 'query') return;
  const chosen = props.catalog?.actions.find((candidate) => candidate.name === option?.id);
  const next: Record<string, unknown> = {};
  for (const field of chosen?.fields ?? []) {
    if (field.name in step.params) next[field.name] = step.params[field.name];
    else if (field.required) next[field.name] = '';
  }
  emit('update:step', { ...step, operation: option?.id ?? '', params: next });
}

function setParam(name: string, value: unknown): void {
  const step = props.step;
  if (step.kind === 'command' || step.kind === 'query') emit('update:step', { ...step, params: { ...step.params, [name]: value } });
}

function removeParam(name: string): void {
  const step = props.step;
  if (step.kind !== 'command' && step.kind !== 'query') return;
  const next = { ...step.params };
  delete next[name];
  emit('update:step', { ...step, params: next });
}

function setResult(result: 'first' | 'count'): void {
  if (props.step.kind === 'query') emit('update:step', { ...props.step, result });
}

/** What helps to fill a field: its choices, or (in English, the language they are written in) its words. */
function helper(field: FieldOut): string | undefined {
  if (field.choices.length) return field.choices.join(', ');
  return phrasing.value.locale === 'en' && field.description ? field.description : undefined;
}

const title = computed(() => describeStep(props.step, props.steps, props.catalog, phrasing.value));
/** «Send a message» (FLOW-F31): the narrow send has its own form, not the list of actions. */
const message = computed(() => props.step.kind === 'command' && props.step.operation === NOTIFY_OPERATION);

/** «Only if: … · If it fails, it carries on», for a closed step that has options. */
const summary = computed(() => {
  const step = props.step;
  if (step.kind === 'condition') return '';
  const parts: string[] = [];
  const t = phrasing.value.t;
  if (step.run_if && Object.keys(step.run_if).length) {
    const clauses = Object.entries(step.run_if).flatMap(([path, comparisons]) =>
      Object.entries(comparisons ?? {}).map(([op, value]) => describeClause({ path, op: op as never, value }, props.steps, props.catalog, phrasing.value)),
    );
    parts.push(t('flow.steps.options.summaryRunIf', { clauses: clauses.join('; ') }));
  }
  if ((step.kind === 'command' || step.kind === 'query' || step.kind === 'http' || step.kind === 'assistant') && step.on_error === 'continue') parts.push(t('flow.steps.options.summaryOnError'));
  return parts.join(' · ');
});
</script>

<template>
  <div
    class="flow-node"
    :data-node="id"
    :data-testid="`flow-step-${id}`"
  >
    <!-- A wait: a label on the line. -->
    <template v-if="step.kind === 'delay'">
      <div class="flow-segment">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          {{ title }}
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <span
        v-if="summary && !open"
        class="flow-card__hint flow-step__summary"
        :data-testid="`flow-step-summary-${id}`"
      >{{ summary }}</span>
      <div
        v-if="open"
        class="flow-detached-panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <div class="flow-step__pair">
          <IonInput
            :data-testid="`flow-step-amount-${id}`"
            type="number"
            :min="1"
            :value="delay.amount"
            :label="$t('flow.steps.amount')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="error('seconds')"
            :class="{ 'ion-invalid ion-touched': !!error('seconds') }"
            @ion-input="setDelay(Number($event.detail.value), delay.unit)"
          />
          <IonSelect
            :data-testid="`flow-step-unit-${id}`"
            :value="delay.unit"
            :label="$t('flow.steps.unit')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="setDelay(delay.amount, $event.detail.value as DelayUnit)"
          >
            <IonSelectOption
              v-for="unit in UNITS"
              :key="unit"
              :value="unit"
            >
              {{ $t(`flow.steps.units.${unit}.many`) }}
            </IonSelectOption>
          </IonSelect>
        </div>
        <StepOptions
          :step="step"
          :steps="steps"
          :catalog="catalog"
          :choices="choices"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
      </div>
    </template>

    <!-- A condition: a dashed chip that narrows the line. -->
    <template v-else-if="step.kind === 'condition'">
      <div class="flow-chip">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          <span><strong>{{ $t('flow.steps.guard') }}</strong> {{ title }}</span>
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <div
        v-if="open"
        class="flow-detached-panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <span class="flow-card__hint">{{ $t('flow.steps.guardHint') }}</span>
        <ConditionRows
          :testid="`flow-step-cond-${id}`"
          :model-value="step.when"
          :choices="choices"
          :pick="pick"
          :steps="steps"
          :catalog="catalog"
          @update:model-value="setCondition"
        />
        <span
          v-if="error('when')"
          class="flow-card__error"
        >{{ error('when') }}</span>
      </div>
    </template>

    <!-- A call to another system: a card named by its host. -->
    <div
      v-else-if="step.kind === 'http'"
      class="flow-card"
    >
      <div class="flow-card__row">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          <span class="flow-card__title"><HubIcon name="ion:globe-outline" /> {{ title }}</span>
          <span
            v-if="summary && !open"
            class="flow-card__hint flow-step__summary"
            :data-testid="`flow-step-summary-${id}`"
          >{{ summary }}</span>
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <div
        v-if="open"
        class="flow-card__panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <HttpStepPanel
          :step="step"
          :index="index"
          :steps="steps"
          :catalog="catalog"
          :errors="errors"
          :pick="pickCall ?? pick"
          @update:step="emit('update:step', $event)"
        />
        <StepOptions
          :step="step"
          :steps="steps"
          :catalog="catalog"
          :choices="choices"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
      </div>
    </div>

    <!-- A question to someone (FLOW-F28): a card named by what it asks. -->
    <div
      v-else-if="step.kind === 'ask'"
      class="flow-card"
    >
      <div class="flow-card__row">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          <span class="flow-card__title"><HubIcon name="ion:help-circle-outline" /> {{ title }}</span>
          <span
            v-if="summary && !open"
            class="flow-card__hint flow-step__summary"
            :data-testid="`flow-step-summary-${id}`"
          >{{ summary }}</span>
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <div
        v-if="open"
        class="flow-card__panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <AskStepPanel
          :step="step"
          :index="index"
          :steps="steps"
          :catalog="catalog"
          :errors="errors"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
        <StepOptions
          :step="step"
          :steps="steps"
          :catalog="catalog"
          :choices="choices"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
      </div>
    </div>

    <!-- A task for the assistant (FLOW-F37): a card named by what it is asked. -->
    <div
      v-else-if="step.kind === 'assistant'"
      class="flow-card"
    >
      <div class="flow-card__row">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          <span class="flow-card__title"><HubIcon name="ion:sparkles-outline" /> {{ title }}</span>
          <span
            v-if="summary && !open"
            class="flow-card__hint flow-step__summary"
            :data-testid="`flow-step-summary-${id}`"
          >{{ summary }}</span>
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <div
        v-if="open"
        class="flow-card__panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <AssistantStepPanel
          :step="step"
          :index="index"
          :steps="steps"
          :catalog="catalog"
          :errors="errors"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
        <StepOptions
          :step="step"
          :steps="steps"
          :catalog="catalog"
          :choices="choices"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
      </div>
    </div>

    <!-- An action or a read: a card. -->
    <div
      v-else
      class="flow-card"
      :class="{ 'flow-card--gap': !!error('operation') }"
    >
      <div class="flow-card__row">
        <IonReorder
          class="flow-handle"
          :aria-label="$t('flow.steps.reorder')"
        >
          ⠿
        </IonReorder>
        <button
          type="button"
          class="flow-card__open"
          :aria-expanded="open ? 'true' : 'false'"
          :data-testid="`flow-step-open-${id}`"
          @click="emit('toggle')"
        >
          <span class="flow-card__title">{{ title }}</span>
          <span
            v-if="summary && !open"
            class="flow-card__hint flow-step__summary"
            :data-testid="`flow-step-summary-${id}`"
          >{{ summary }}</span>
        </button>
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.steps.remove')"
          :data-testid="`flow-step-remove-${id}`"
          @click="emit('remove')"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <div
        v-if="open"
        class="flow-card__panel"
        :data-testid="`flow-step-panel-${id}`"
      >
        <MessageStepPanel
          v-if="message"
          :step="step"
          :index="index"
          :steps="steps"
          :catalog="catalog"
          :errors="errors"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
        <Combo
          v-else
          :testid="`flow-step-action-${id}`"
          :model-value="chosenAction"
          :options="actions"
          :label="step.kind === 'query' ? $t('flow.steps.whatQuery') : $t('flow.steps.what')"
          :placeholder="step.kind === 'query' ? $t('flow.steps.chooseQuery') : $t('flow.steps.choose')"
          :error-text="error('operation')"
          :clearable="false"
          @update:model-value="setAction"
        />
        <template v-if="step.kind === 'query'">
          <IonSelect
            :data-testid="`flow-step-result-${id}`"
            :value="step.result"
            :label="$t('flow.steps.keep')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="setResult($event.detail.value)"
          >
            <IonSelectOption value="first">
              {{ $t('flow.steps.keepFirst') }}
            </IonSelectOption>
            <IonSelectOption value="count">
              {{ $t('flow.steps.keepCount') }}
            </IonSelectOption>
          </IonSelect>
          <span
            class="flow-card__hint"
            :data-testid="`flow-step-queryhint-${id}`"
          >{{ $t('flow.steps.queryHint') }}</span>
        </template>
        <div
          v-if="step.operation && !message"
          class="flow-card__field"
        >
          <span class="flow-card__label">{{ $t('flow.steps.info') }}</span>
          <div
            v-for="field in shownFields"
            :key="field.name"
            class="flow-step__param"
          >
            <ValueBox
              :testid="`flow-step-param-${id}-${field.name}`"
              :model-value="params[field.name]"
              :label="fieldLabel(field.name, phrasing)"
              :required="field.required"
              :helper="helper(field)"
              :error-text="error(`params.${field.name}`)"
              :steps="steps"
              :catalog="catalog"
              :pick="pick"
              @update:model-value="setParam(field.name, $event)"
            />
            <button
              v-if="!field.required"
              type="button"
              class="flow-icon-btn"
              :aria-label="$t('flow.steps.removeInfo')"
              :data-testid="`flow-step-unparam-${id}-${field.name}`"
              @click="removeParam(field.name)"
            >
              <HubIcon name="ion:close-outline" />
            </button>
          </div>
          <IonSelect
            v-if="addable.length"
            :data-testid="`flow-step-addinfo-${id}`"
            :value="null"
            :label="$t('flow.steps.addInfo')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="$event.detail.value && setParam(String($event.detail.value), '')"
          >
            <IonSelectOption
              v-for="field in addable"
              :key="field.name"
              :value="field.name"
            >
              {{ fieldLabel(field.name, phrasing) }}
            </IonSelectOption>
          </IonSelect>
        </div>
        <StepOptions
          :step="step"
          :steps="steps"
          :catalog="catalog"
          :choices="choices"
          :pick="pick"
          @update:step="emit('update:step', $event)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-step__pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}
.flow-step__param {
  display: flex;
  align-items: flex-start;
  gap: 0.3rem;
}
.flow-step__param > .flow-value {
  flex: 1 1 auto;
}
</style>
