<script setup lang="ts">
// The form of «Ask the assistant» (WORKBOOK FLOW-F37; old hub HUB-F95): what it is asked, with data inserted (filled
// in when it runs); the reads and actions it may use — only those the assistant can use, each one a permission of the
// automation (FLOW-F12) —; the data a tool always gets, fixed by the automation, that the assistant never sees nor
// changes («On behalf of the customer» = their card); whether a change waits for a yes in «Waiting for your answer»
// («Ask me first», the default) or it makes it on its own; and its most turns, one to ten. What it only looks up
// never waits.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, nextTick, ref } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { asCallText } from '../lib/document';
import { actionLabel, fieldLabel } from '../lib/phrasing';
import type { AssistantStep, CatalogOut, Step } from '../operations';
import ValueBox from './ValueBox.vue';

/** The server's limits (apps/flow/schemas.py `AssistantStep`). */
const MAX_ROUNDS = 10;
const MODES: readonly AssistantStep['mode'][] = ['ask', 'auto'];

const props = defineProps<{
  step: AssistantStep;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** Opens the editor's picker for this step; the chosen path, or `null`. */
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();
const phrasing = usePhrasing();

const id = computed(() => props.step.id);
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.${field}`];
const label = (name: string): string => actionLabel(name, props.catalog, phrasing.value);

/** What only «Ask me first» may use (cancelling a booking): never offered to a step that does it on its own. */
const askFirst = (name: string): boolean => !!props.catalog?.actions.find((action) => action.name === name)?.ask_first;

/** What it may still be given: the assistant's reads and actions of the active apps, by app and name. */
const addable = computed<ComboOption[]>(() =>
  (props.catalog?.actions ?? [])
    .filter((action) => action.assistant && !props.step.tools.includes(action.name))
    .filter((action) => props.step.mode === 'ask' || !action.ask_first)
    .map((action) => ({ id: action.name, label: label(action.name), hint: action.app_name, app: action.app_name }))
    .sort((a, b) => a.app.localeCompare(b.app, phrasing.value.locale) || a.label.localeCompare(b.label, phrasing.value.locale))
    .map(({ id: name, label: text, hint }) => ({ id: name, label: text, hint })),
);

/** The chosen ones that wait for the yes of someone who may do them, said under the mode while it asks first. */
const waitsForWho = computed<string>(() =>
  props.step.mode === 'ask' ? props.step.tools.filter(askFirst).map((name) => `«${label(name)}»`).join(', ') : '',
);

function change(patch: Partial<AssistantStep>): void {
  emit('update:step', { ...props.step, ...patch });
}

type Pinned = Record<string, Record<string, unknown>>;

/** The fixed data without what is left empty of a tool: none at all is no `pinned` (a step saved as before). */
function tidy(pinned: Pinned): Pinned | undefined {
  const kept = Object.fromEntries(Object.entries(pinned).filter(([, data]) => Object.keys(data).length));
  return Object.keys(kept).length ? kept : undefined;
}

/** Each fixed datum, tool by tool in the order it may use them. */
const pins = computed(() =>
  Object.entries(props.step.pinned ?? {}).flatMap(([tool, data]) =>
    Object.entries(data).map(([field, value]) => ({ tool, field, value, label: `${label(tool)} › ${fieldLabel(field, phrasing.value)}` })),
  ),
);

/** What may still be fixed: each datum of each tool it may use, that is not fixed yet. */
const pinnable = computed<ComboOption[]>(() =>
  props.step.tools.flatMap((tool) =>
    (props.catalog?.actions.find((action) => action.name === tool)?.fields ?? [])
      .filter((field) => !(field.name in (props.step.pinned?.[tool] ?? {})))
      .map((field) => ({ id: `${tool}|${field.name}`, label: fieldLabel(field.name, phrasing.value), hint: label(tool) })),
  ),
);

function setPin(tool: string, field: string, value: unknown): void {
  const pinned = props.step.pinned ?? {};
  change({ pinned: { ...pinned, [tool]: { ...(pinned[tool] ?? {}), [field]: value } } });
}

/** ``pinned`` without ``tool``'s datum ``field`` or, with no ``field``, without all of ``tool``'s. */
function without(tool: string, field?: string): Pinned | undefined {
  const pinned: Pinned = { ...props.step.pinned };
  if (field === undefined) delete pinned[tool];
  else pinned[tool] = Object.fromEntries(Object.entries(pinned[tool] ?? {}).filter(([name]) => name !== field));
  return tidy(pinned);
}

function unpin(tool: string, field: string): void {
  change({ pinned: without(tool, field) });
}

function removeTool(name: string): void {
  change({ tools: props.step.tools.filter((tool) => tool !== name), pinned: without(name) });
}

/** The datum just chosen to fix, then nothing again (as the search of what it may use). */
const chosenPin = ref<ComboOption | null>(null);

async function addPin(option: ComboOption | null): Promise<void> {
  chosenPin.value = option;
  if (option) {
    const [tool = '', field = ''] = String(option.id).split('|');
    setPin(tool, field, '');
  }
  await nextTick();
  chosenPin.value = null;
}

/** What the search holds: the option just chosen, then nothing again, so its field empties (the Combo empties it when
 *  its value goes back to none) and what was added never looks like a value of the field. */
const chosen = ref<ComboOption | null>(null);

async function addTool(option: ComboOption | null): Promise<void> {
  chosen.value = option;
  if (option && !props.step.tools.includes(String(option.id))) change({ tools: [...props.step.tools, String(option.id)] });
  await nextTick();
  chosen.value = null;
}

function setRounds(text: string | null | undefined): void {
  const rounds = Math.round(Number(text));
  if (!Number.isFinite(rounds) || rounds < 1) return;
  change({ max_rounds: Math.min(MAX_ROUNDS, rounds) });
}
</script>

<template>
  <div
    class="flow-assistant"
    :data-testid="`flow-assistant-${id}`"
  >
    <ValueBox
      :testid="`flow-assistant-prompt-${id}`"
      :model-value="step.prompt"
      :label="$t('flow.assistant.prompt')"
      :required="true"
      :error-text="error('prompt')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="change({ prompt: asCallText($event) })"
    />
    <div class="flow-assistant__tools">
      <span class="flow-assistant__label">{{ $t('flow.assistant.tools') }}</span>
      <ul
        v-if="step.tools.length"
        class="flow-assistant__chips"
      >
        <li
          v-for="name in step.tools"
          :key="name"
          class="flow-assistant__chip"
        >
          <span :data-testid="`flow-assistant-tool-${id}-${name}`">{{ label(name) }}</span>
          <button
            type="button"
            class="flow-icon-btn"
            :aria-label="$t('flow.assistant.removeTool', { action: label(name) })"
            :data-testid="`flow-assistant-tool-remove-${id}-${name}`"
            @click="removeTool(name)"
          >
            <HubIcon name="ion:close-outline" />
          </button>
        </li>
      </ul>
      <span
        v-else
        class="flow-card__hint"
        :data-testid="`flow-assistant-notools-${id}`"
      >{{ $t('flow.assistant.noTools') }}</span>
      <Combo
        :testid="`flow-assistant-addtool-${id}`"
        :model-value="chosen"
        :options="addable"
        :label="$t('flow.assistant.addTool')"
        :placeholder="$t('flow.assistant.chooseTool')"
        @update:model-value="addTool"
      />
      <span
        v-if="error('tools')"
        class="flow-assistant__bad"
        :data-testid="`flow-assistant-tools-error-${id}`"
      >{{ error('tools') }}</span>
      <span class="flow-card__hint">{{ $t('flow.assistant.toolsHint') }}</span>
    </div>
    <div
      v-if="step.tools.length"
      class="flow-assistant__tools"
      :data-testid="`flow-assistant-pinned-${id}`"
    >
      <span class="flow-assistant__label">{{ $t('flow.assistant.pinned') }}</span>
      <div
        v-for="pin in pins"
        :key="`${pin.tool}|${pin.field}`"
        class="flow-assistant__pin"
      >
        <ValueBox
          :testid="`flow-assistant-pin-${id}-${pin.tool}-${pin.field}`"
          :model-value="pin.value"
          :label="pin.label"
          :required="true"
          :steps="steps"
          :catalog="catalog"
          :pick="pick"
          @update:model-value="setPin(pin.tool, pin.field, $event)"
        />
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.assistant.removePin', { datum: pin.label })"
          :data-testid="`flow-assistant-unpin-${id}-${pin.tool}-${pin.field}`"
          @click="unpin(pin.tool, pin.field)"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <span
        v-if="!pins.length"
        class="flow-card__hint"
        :data-testid="`flow-assistant-nopins-${id}`"
      >{{ $t('flow.assistant.noPins') }}</span>
      <Combo
        v-if="pinnable.length"
        :testid="`flow-assistant-addpin-${id}`"
        :model-value="chosenPin"
        :options="pinnable"
        :label="$t('flow.assistant.addPin')"
        :placeholder="$t('flow.assistant.choosePin')"
        @update:model-value="addPin"
      />
      <span
        v-if="error('pinned')"
        class="flow-assistant__bad"
        :data-testid="`flow-assistant-pinned-error-${id}`"
      >{{ error('pinned') }}</span>
      <span
        class="flow-card__hint"
        :data-testid="`flow-assistant-pinnedhint-${id}`"
      >{{ $t('flow.assistant.pinnedHint') }}</span>
    </div>
    <div class="flow-assistant__pair">
      <IonSelect
        :data-testid="`flow-assistant-mode-${id}`"
        :value="step.mode"
        :label="$t('flow.assistant.mode')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="change({ mode: $event.detail.value as AssistantStep['mode'] })"
      >
        <IonSelectOption
          v-for="mode in MODES"
          :key="mode"
          :value="mode"
        >
          {{ $t(`flow.assistant.modes.${mode}`) }}
        </IonSelectOption>
      </IonSelect>
      <IonInput
        :data-testid="`flow-assistant-rounds-${id}`"
        type="number"
        :min="1"
        :max="MAX_ROUNDS"
        :value="step.max_rounds"
        :label="$t('flow.assistant.rounds')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="error('max_rounds')"
        :class="{ 'ion-invalid ion-touched': !!error('max_rounds') }"
        @ion-input="setRounds($event.detail.value)"
      />
    </div>
    <span
      class="flow-card__hint"
      :data-testid="`flow-assistant-modehint-${id}`"
    >{{ $t(`flow.assistant.modeHints.${step.mode}`) }}</span>
    <span
      v-if="waitsForWho"
      class="flow-card__hint"
      :data-testid="`flow-assistant-askfirst-${id}`"
    >{{ $t('flow.assistant.askFirst', { actions: waitsForWho }) }}</span>
    <span class="flow-card__hint">{{ $t('flow.assistant.answerHint') }}</span>
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-assistant {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-assistant__tools {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}
.flow-assistant__label {
  font-size: 0.875rem;
  font-weight: 600;
}
.flow-assistant__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.flow-assistant__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.125rem;
  max-width: 100%;
  padding: 0.125rem 0.125rem 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--ion-color-light, #f4f5f8);
  overflow-wrap: anywhere;
}
.flow-assistant__pin {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.25rem;
}
.flow-assistant__bad {
  color: var(--ion-color-danger);
  font-size: 0.8125rem;
}
.flow-assistant__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0.5rem;
}
@media (max-width: 480px) {
  .flow-assistant__pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
