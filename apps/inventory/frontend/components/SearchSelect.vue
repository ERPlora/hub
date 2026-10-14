<script setup lang="ts">
// A picker over a list the server pages (tax categories, product categories). While the whole list
// fits in one query (`complete`) it is the plain outlined select of the old screens. A longer list
// cannot be held whole (the API serves at most 100 rows): the field opens a dialog with a search box
// that asks the server (`update:search`) and the matching options; a tap picks one (and closes) or,
// with `multiple`, toggles it. The names of the options picked are remembered while the search
// changes. From the keyboard the field is a combobox: Enter or Space open it, Enter in the search box
// picks the first match; neither key ever reaches the form around it (FormModal submits on Enter).
// A stand-in until @erplora/ui ships a shared `SearchSelect` (UI-REQUESTS.md).
import { HubIcon } from '@erplora/ui/shell';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonModal,
  IonSearchbar,
  IonSelect,
  IonSelectOption,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref, watch } from 'vue';

export interface SearchOption {
  value: string;
  label: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: string | string[];
    /** What the server returned for the current search. */
    options: readonly SearchOption[];
    /** `options` hold the whole list: the plain select is enough. */
    complete: boolean;
    /** Options always offered first («— (default)»). */
    fixedOptions?: readonly SearchOption[];
    multiple?: boolean;
    label: string;
    placeholder?: string;
    testid: string;
    errorText?: string;
    disabled?: boolean;
  }>(),
  { fixedOptions: () => [], multiple: false, placeholder: undefined, errorText: undefined, disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [value: string | string[]]; 'update:search': [text: string] }>();

const picking = ref(false);
/** Every label seen, so a picked option keeps its name when it is not among the current options. */
const known = ref(new Map<string, string>());
watch(
  () => [...props.fixedOptions, ...props.options],
  (options) => {
    const next = new Map(known.value);
    for (const option of options) next.set(option.value, option.label);
    known.value = next;
  },
  { immediate: true },
);

const picked = computed<string[]>(() =>
  Array.isArray(props.modelValue) ? props.modelValue : props.modelValue === '' && !props.fixedOptions.some((o) => o.value === '') ? [] : [props.modelValue],
);
const summary = computed(() => picked.value.map((value) => known.value.get(value) ?? value).join(', '));
const invalid = computed(() => ({ 'ion-invalid': !!props.errorText, 'ion-touched': !!props.errorText }));

function fromSelect(value: unknown): void {
  if (props.multiple) emit('update:modelValue', Array.isArray(value) ? value.map(String) : []);
  else emit('update:modelValue', typeof value === 'string' ? value : '');
}

function choose(value: string): void {
  if (!props.multiple) {
    emit('update:modelValue', value);
    picking.value = false;
    return;
  }
  const now = picked.value;
  emit('update:modelValue', now.includes(value) ? now.filter((v) => v !== value) : [...now, value]);
}

function openPicker(): void {
  if (!props.disabled) picking.value = true;
}

/** Enter in the search box: the first option shown. */
function chooseFirst(): void {
  const first = [...props.fixedOptions, ...props.options][0];
  if (first) choose(first.value);
}

function search(event: CustomEvent<{ value?: string | null }>): void {
  emit('update:search', (event.detail.value ?? '').trim());
}

function close(): void {
  picking.value = false;
  emit('update:search', '');
}
</script>

<template>
  <ion-select
    v-if="complete"
    :data-testid="testid"
    :model-value="modelValue"
    :multiple="multiple"
    :label="label"
    :placeholder="placeholder"
    label-placement="floating"
    fill="outline"
    mode="md"
    :disabled="disabled"
    :error-text="errorText"
    :class="invalid"
    @update:model-value="fromSelect"
  >
    <ion-select-option
      v-for="option in [...fixedOptions, ...options]"
      :key="option.value"
      :value="option.value"
    >
      {{ option.label }}
    </ion-select-option>
  </ion-select>
  <template v-else>
    <ion-input
      :data-testid="testid"
      :model-value="summary"
      :readonly="true"
      :label="label"
      :placeholder="placeholder"
      label-placement="floating"
      fill="outline"
      mode="md"
      :disabled="disabled"
      :error-text="errorText"
      :class="[invalid, 'search-select__field']"
      role="combobox"
      aria-haspopup="dialog"
      @click="openPicker"
      @keydown.enter.prevent.stop="openPicker"
      @keydown.space.prevent.stop="openPicker"
    />
    <ion-modal
      :is-open="picking"
      :aria-label="label"
      :data-testid="`${testid}-picker`"
      @did-dismiss="close"
    >
      <ion-header class="ion-no-border">
        <ion-toolbar>
          <ion-title>{{ label }}</ion-title>
          <ion-buttons slot="end">
            <ion-button
              :aria-label="$t('inventory.common.close')"
              :data-testid="`${testid}-close`"
              @click="close"
            >
              <HubIcon
                slot="icon-only"
                name="ion:close-outline"
              />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
        <ion-toolbar>
          <ion-searchbar
            :data-testid="`${testid}-search`"
            :debounce="250"
            @ion-input="search"
            @keydown.enter.stop.prevent="chooseFirst"
          />
        </ion-toolbar>
      </ion-header>
      <ion-content>
        <ion-list>
          <ion-item
            v-for="option in [...fixedOptions, ...options]"
            :key="option.value"
            button
            :detail="false"
            :data-testid="`${testid}-option`"
            :data-value="option.value"
            @click="choose(option.value)"
          >
            <ion-label>{{ option.label }}</ion-label>
            <HubIcon
              v-if="picked.includes(option.value)"
              slot="end"
              name="ion:checkmark-outline"
            />
          </ion-item>
        </ion-list>
      </ion-content>
    </ion-modal>
  </template>
</template>

<style scoped>
.search-select__field {
  cursor: pointer;
}
</style>
