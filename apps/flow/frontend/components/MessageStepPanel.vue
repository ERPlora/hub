<script setup lang="ts">
// The form of «Send a message» (WORKBOOK FLOW-F31; the old module's flows-f15): a «Do something» step of the
// WhatsApp inbox's narrow send (`whatsapp_inbox.message.notify`). To whom is a datum — the customer's exact
// international number, never one typed by hand —; the message goes as it is within the customer's 24 hours;
// after them WhatsApp only lets an approved template through, chosen from the business's (read live from the
// inbox) with a value for each of its blanks. A template it no longer finds stays chosen and says so.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { asCallText } from '../lib/document';
import type { CatalogOut, Step } from '../operations';
import ValueBox from './ValueBox.vue';

interface TemplateParam {
  name: string;
  language?: string;
  variables: string[];
}

const props = defineProps<{
  step: Step;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** Opens the editor's picker for this step; the chosen path, or `null`. */
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();

const templates = useLive('whatsapp_inbox.template.list', { sendable: true, limit: 100 });

const id = computed(() => props.step.id);
const params = computed<Record<string, unknown>>(() => (props.step.kind === 'command' ? props.step.params : {}));
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.params.${field}`];

const chosen = computed<TemplateParam | null>(() => {
  const value = params.value.template as TemplateParam | undefined;
  return value && typeof value === 'object' && value.name ? { ...value, variables: [...(value.variables ?? [])] } : null;
});
const rows = computed(() => templates.data.value?.rows ?? []);
const optionOf = (name: string, language = ''): string => `${name}|${language}`;
const known = computed(() => rows.value.find((row) => row.name === chosen.value?.name && (!chosen.value?.language || row.language === chosen.value.language)) ?? null);
/** Chosen, but not among the approved ones read (renamed, deleted…): kept, and said. */
const missing = computed(() => !!chosen.value && !!templates.data.value && !known.value);

function setParams(next: Record<string, unknown>): void {
  if (props.step.kind === 'command') emit('update:step', { ...props.step, params: next });
}

function setPhone(value: unknown): void {
  setParams({ ...params.value, phone: value });
}

function setText(value: unknown): void {
  setParams({ ...params.value, text: asCallText(value) });
}

function chooseTemplate(value: string | null | undefined): void {
  const next = { ...params.value };
  if (!value) {
    delete next.template;
    setParams(next);
    return;
  }
  const [name, language = ''] = value.split('|');
  const row = rows.value.find((candidate) => candidate.name === name && candidate.language === language);
  const count = row?.variables ?? chosen.value?.variables.length ?? 0;
  next.template = { name, language, variables: Array.from({ length: count }, (_, i) => chosen.value?.variables[i] ?? '') };
  setParams(next);
}

function setVariable(position: number, value: unknown): void {
  if (!chosen.value) return;
  const variables = [...chosen.value.variables];
  variables[position] = asCallText(value);
  setParams({ ...params.value, template: { ...chosen.value, variables } });
}
</script>

<template>
  <div
    class="flow-message"
    :data-testid="`flow-message-${id}`"
  >
    <ValueBox
      :testid="`flow-message-phone-${id}`"
      :model-value="params.phone"
      :label="$t('flow.message.phone')"
      :required="true"
      :error-text="error('phone')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="setPhone"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-phonehint-${id}`"
    >{{ $t('flow.message.phoneHint') }}</span>
    <ValueBox
      :testid="`flow-message-text-${id}`"
      :model-value="params.text"
      :label="$t('flow.message.text')"
      :error-text="error('text')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="setText"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-texthint-${id}`"
    >{{ $t('flow.message.textHint') }}</span>
    <InlineFeedback
      v-if="templates.error.value && !templates.data.value"
      tone="danger"
      :data-testid="`flow-message-templateerror-${id}`"
    >
      {{ $t('flow.message.templatesError') }}
      <IonButton
        size="small"
        fill="clear"
        :data-testid="`flow-message-templateretry-${id}`"
        @click="templates.refresh()"
      >
        {{ $t('flow.live.retry') }}
      </IonButton>
    </InlineFeedback>
    <span
      v-else-if="!templates.data.value"
      class="flow-card__hint"
      :data-testid="`flow-message-templateloading-${id}`"
    >{{ $t('flow.message.templatesLoading') }}</span>
    <IonSelect
      v-else
      :data-testid="`flow-message-template-${id}`"
      :value="chosen ? optionOf(chosen.name, known?.language ?? chosen.language) : ''"
      :label="$t('flow.message.template')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      :error-text="error('template')"
      :class="{ 'ion-invalid ion-touched': !!error('template') }"
      @ion-change="chooseTemplate($event.detail.value)"
    >
      <IonSelectOption value="">
        {{ $t('flow.message.noTemplate') }}
      </IonSelectOption>
      <IonSelectOption
        v-for="row in rows"
        :key="row.id"
        :value="optionOf(row.name, row.language)"
      >
        {{ row.name }} ({{ row.language }})
      </IonSelectOption>
      <IonSelectOption
        v-if="missing && chosen"
        :value="optionOf(chosen.name, chosen.language)"
      >
        {{ chosen.name }}
      </IonSelectOption>
    </IonSelect>
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-templatehint-${id}`"
    >{{ $t('flow.message.templateHint') }}</span>
    <span
      v-if="templates.data.value && !rows.length && !chosen"
      class="flow-card__hint"
      :data-testid="`flow-message-notemplates-${id}`"
    >{{ $t('flow.message.noTemplates') }}</span>
    <InlineFeedback
      v-if="missing && chosen"
      tone="warning"
      :data-testid="`flow-message-missing-${id}`"
    >
      {{ $t('flow.message.missing', { name: chosen.name }) }}
    </InlineFeedback>
    <template v-if="chosen">
      <p
        v-if="known"
        class="flow-message__preview"
        :data-testid="`flow-message-preview-${id}`"
      >
        {{ known.body }}
      </p>
      <ValueBox
        v-for="(value, position) in chosen.variables"
        :key="position"
        :testid="`flow-message-var-${id}-${position}`"
        :model-value="value"
        :label="$t('flow.message.variable', { n: position + 1 })"
        :required="true"
        :steps="steps"
        :catalog="catalog"
        :pick="pick"
        @update:model-value="setVariable(position, $event)"
      />
    </template>
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-message {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.flow-message__preview {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--ep-surface-muted, #f4f3ee);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
