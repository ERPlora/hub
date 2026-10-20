<script setup lang="ts">
// The form of «Ask someone first» (WORKBOOK FLOW-F28; the old module's flows-f18): the question and its
// details, with data inserted (filled in when it is asked); who answers it — whoever runs the business by
// default, or the managers or the employees, and whoever runs the business always can —; how long to
// wait, from an hour to thirty days; and what a no and silence do. With «Carry on», the next steps can
// read the answer: it says how. Asking needs no permission.
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { asCallText } from '../lib/document';
import type { AskStep, CatalogOut, QuestionRole, Step } from '../operations';
import ValueBox from './ValueBox.vue';

const ROLES: readonly QuestionRole[] = ['', 'manager', 'employee'];
/** The server's limits (apps/flow/schemas.py `AskStep`). */
const MAX_HOURS = 720;

const props = defineProps<{
  step: AskStep;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** Opens the editor's picker for this step; the chosen path, or `null`. */
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();

const id = computed(() => props.step.id);
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.${field}`];
const carriesOn = computed(() => props.step.on_no === 'continue' || props.step.on_timeout === 'continue');

function change(patch: Partial<AskStep>): void {
  emit('update:step', { ...props.step, ...patch });
}

function setHours(text: string | null | undefined): void {
  const hours = Math.round(Number(text));
  if (!Number.isFinite(hours) || hours < 1) return;
  change({ hours: Math.min(MAX_HOURS, hours) });
}
</script>

<template>
  <div
    class="flow-ask"
    :data-testid="`flow-ask-${id}`"
  >
    <ValueBox
      :testid="`flow-ask-title-${id}`"
      :model-value="step.title"
      :label="$t('flow.ask.title')"
      :required="true"
      :error-text="error('title')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="change({ title: asCallText($event) })"
    />
    <ValueBox
      :testid="`flow-ask-details-${id}`"
      :model-value="step.details"
      :label="$t('flow.ask.details')"
      :error-text="error('details')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="change({ details: asCallText($event) })"
    />
    <IonSelect
      :data-testid="`flow-ask-role-${id}`"
      :value="step.role"
      :label="$t('flow.ask.role')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      @ion-change="change({ role: $event.detail.value as QuestionRole })"
    >
      <IonSelectOption
        v-for="role in ROLES"
        :key="role || 'admin'"
        :value="role"
      >
        {{ $t(`flow.ask.roleOptions.${role || 'admin'}`) }}
      </IonSelectOption>
    </IonSelect>
    <span
      class="flow-card__hint"
      :data-testid="`flow-ask-who-${id}`"
    >{{ $t(step.role ? 'flow.ask.whoRole' : 'flow.ask.whoAdmin', { who: $t(`flow.ask.whoNames.${step.role || 'admin'}`) }) }}</span>
    <IonInput
      :data-testid="`flow-ask-hours-${id}`"
      type="number"
      :min="1"
      :max="MAX_HOURS"
      :value="step.hours"
      :label="$t('flow.ask.hours')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :error-text="error('hours')"
      :class="{ 'ion-invalid ion-touched': !!error('hours') }"
      @ion-input="setHours($event.detail.value)"
    />
    <div class="flow-ask__pair">
      <IonSelect
        :data-testid="`flow-ask-onno-${id}`"
        :value="step.on_no"
        :label="$t('flow.ask.onNo')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="change({ on_no: $event.detail.value as AskStep['on_no'] })"
      >
        <IonSelectOption value="stop">
          {{ $t('flow.ask.stop') }}
        </IonSelectOption>
        <IonSelectOption value="continue">
          {{ $t('flow.ask.continue') }}
        </IonSelectOption>
      </IonSelect>
      <IonSelect
        :data-testid="`flow-ask-ontimeout-${id}`"
        :value="step.on_timeout"
        :label="$t('flow.ask.onTimeout')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="change({ on_timeout: $event.detail.value as AskStep['on_timeout'] })"
      >
        <IonSelectOption value="no">
          {{ $t('flow.ask.asNo') }}
        </IonSelectOption>
        <IonSelectOption value="stop">
          {{ $t('flow.ask.stop') }}
        </IonSelectOption>
        <IonSelectOption value="continue">
          {{ $t('flow.ask.continue') }}
        </IonSelectOption>
      </IonSelect>
    </div>
    <span
      v-if="carriesOn"
      class="flow-card__hint"
      :data-testid="`flow-ask-continuehint-${id}`"
    >{{ $t('flow.ask.continueHint') }}</span>
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-ask {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-ask__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0.5rem;
}
@media (max-width: 480px) {
  .flow-ask__pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
