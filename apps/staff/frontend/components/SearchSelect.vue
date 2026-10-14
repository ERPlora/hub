<script lang="ts">
/** One choice of the picker. */
export interface SearchOption {
  value: string;
  label: string;
}
</script>

<script setup lang="ts">
// SearchSelect — a picker for a list that may be longer than what the server gives at once (100):
// the staff members, the roles, the accounts of the business. A boxed field, like the `ion-select` of
// the old forms, shows the current choice; it opens a dialog with a search box and the first matches,
// which `load(search)` asks the server for as the person types. Picking one closes it and emits the
// value and its label. An optional «none» choice (`noneLabel`, value `''`) comes first. Enter never
// leaves the picker: on the field it opens it, in the search box it takes the first match, and in
// neither does it reach the form around (FormModal submits on Enter). Until
// `@erplora/ui` has its own (apps/staff/UI-REQUESTS.md, «SearchSelect»), the staff forms use this one.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonItem, IonList, IonSearchbar, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef } from 'vue';

const props = withDefaults(
  defineProps<{
    /** Label of the field, and title of its dialog. */
    label: string;
    /** The chosen value; `''` = none. */
    value: string;
    /** The label of the chosen value (the field shows it). */
    display: string;
    /** The first choice, value `''` («No role»); none without it. */
    noneLabel?: string;
    /** The matches of `search` (the server's first ones). */
    load: (search: string) => Promise<SearchOption[]>;
    /** Message under the field. */
    errorText?: string;
    disabled?: boolean;
    /** Hooks: `<testid>` (the field), `-picker`, `-search`, `-option`, `-empty`, `-error`. */
    testid: string;
  }>(),
  { noneLabel: undefined, errorText: undefined, disabled: false },
);

const emit = defineEmits<{ 'update:value': [value: string, label: string] }>();

// Two roots (the field and its dialog): attributes from the parent (`data-field`…) go to the field.
defineOptions({ inheritAttrs: false });

const open = ref(false);
const search = ref('');
const found = shallowRef<SearchOption[]>([]);
const loading = ref(false);
const failure = ref('');

const shown = computed(() => props.display || (props.value === '' ? (props.noneLabel ?? '') : props.value));
const choices = computed<SearchOption[]>(() => [
  ...(props.noneLabel !== undefined && search.value.trim() === '' ? [{ value: '', label: props.noneLabel }] : []),
  ...found.value,
]);

/** Each search retires the answers of the previous ones. */
let asked = 0;

async function ask(text: string): Promise<void> {
  const ticket = ++asked;
  search.value = text;
  loading.value = true;
  failure.value = '';
  try {
    const options = await props.load(text.trim());
    if (ticket === asked) found.value = options;
  } catch (error) {
    if (ticket === asked) {
      found.value = [];
      failure.value = error instanceof Error ? error.message : String(error);
    }
  } finally {
    if (ticket === asked) loading.value = false;
  }
}

function show(): void {
  if (props.disabled) return;
  found.value = [];
  open.value = true;
  void ask('');
}

function pick(option: SearchOption): void {
  emit('update:value', option.value, option.label);
  open.value = false;
}

/** Enter in the search box: the first match, if there is one (never the «none» choice). It stays in
 *  the picker: a form around the field must not submit (the dialog's FormModal submits on Enter). */
function pickFirst(): void {
  const first = found.value[0];
  if (first) pick(first);
}
</script>

<template>
  <ion-input
    v-bind="$attrs"
    :data-testid="testid"
    class="staff-search-select"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    :label="label"
    :value="shown"
    :readonly="true"
    :disabled="disabled"
    label-placement="floating"
    fill="outline"
    mode="md"
    :error-text="errorText"
    role="button"
    aria-haspopup="dialog"
    @click="show"
    @keydown.enter.prevent.stop="show"
    @keydown.space.prevent.stop="show"
  >
    <HubIcon
      slot="end"
      name="ion:chevron-down-outline"
      aria-hidden="true"
    />
  </ion-input>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="label"
    :testid="`${testid}-picker`"
    @submit="open = false"
  >
    <ion-searchbar
      :data-testid="`${testid}-search`"
      :value="search"
      :placeholder="$t('staff.picker.search')"
      :debounce="300"
      @ion-input="ask(String($event.detail.value ?? ''))"
      @keydown.enter.stop.prevent="pickFirst"
    />
    <InlineFeedback
      v-if="failure"
      tone="danger"
      :data-testid="`${testid}-error`"
    >
      {{ failure }}
    </InlineFeedback>
    <p
      v-else-if="loading && !choices.length"
      class="staff-search-select__state"
    >
      <ion-spinner name="crescent" />
      {{ $t('staff.loading') }}
    </p>
    <p
      v-else-if="!choices.length"
      class="staff-search-select__state"
      :data-testid="`${testid}-empty`"
    >
      {{ $t('staff.noResults') }}
    </p>
    <ion-list
      v-else
      class="staff-search-select__list"
    >
      <ion-item
        v-for="option in choices"
        :key="option.value"
        button
        :detail="false"
        :data-testid="`${testid}-option`"
        :data-value="option.value"
        :aria-current="option.value === value ? 'true' : undefined"
        @click="pick(option)"
      >
        <span class="staff-search-select__label">{{ option.label }}</span>
        <HubIcon
          v-if="option.value === value"
          slot="end"
          name="ion:checkmark-outline"
        />
      </ion-item>
    </ion-list>
    <template #footer>
      <ion-button
        fill="clear"
        :data-testid="`${testid}-dismiss`"
        @click="open = false"
      >
        {{ $t('staff.picker.cancel') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-search-select {
  cursor: pointer;
}
.staff-search-select__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.staff-search-select__label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.staff-search-select__list {
  max-height: 50vh;
  overflow-y: auto;
}
</style>
