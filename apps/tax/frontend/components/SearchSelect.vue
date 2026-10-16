<script lang="ts">
/** One choice of a SearchSelect. */
export interface SearchOption {
  value: string;
  label: string;
}
</script>

<script setup lang="ts">
// SearchSelect — a choice among MANY options (the 249 countries, the business's categories): a read-only
// outlined field that opens a modal with a searchbar and the list, the pattern Ionic recommends for long
// lists (an `ion-select` has no search). Without `v-model:query` the options are filtered here as one
// types (by their name, which carries the code); with it, the text goes to the page, which asks the
// server and passes the answer as `options`. The chosen option keeps its name when a later answer no
// longer lists it. Enter never leaves it (a form around would submit: `ion-input` is scoped, its keydown
// bubbles): on the field it opens the list; in the searchbar it chooses the first match. Asked for as a
// shared component in apps/tax/UI-REQUESTS.md.
import { HubIcon } from '@erplora/ui/shell';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonItem,
  IonList,
  IonModal,
  IonSearchbar,
  IonSpinner,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    options: readonly SearchOption[];
    label: string;
    placeholder?: string;
    errorText?: string;
    disabled?: boolean;
    /** The server is answering a search. */
    loading?: boolean;
    /** Hooks: `<testid>` (the field), `-modal`, `-search`, `-option` (`data-value`), `-empty`. */
    testid: string;
  }>(),
  { placeholder: undefined, errorText: undefined, disabled: false, loading: false },
);

const value = defineModel<string>({ required: true });
/** `v-model:query`: bound, the search is the server's; unbound (`undefined`), it is done here. */
const query = defineModel<string | undefined>('query', { default: undefined });

const open = ref(false);
const typed = ref('');
/** The name of the chosen option, for when the options no longer list it. */
const chosenLabel = ref<string>();

const serverSearch = computed(() => query.value !== undefined);

const listed = computed<SearchOption[]>(() => {
  const text = typed.value.trim().toLowerCase();
  if (serverSearch.value || !text) return [...props.options];
  return props.options.filter((option) => option.label.toLowerCase().includes(text));
});

const shown = computed(() => {
  if (!value.value) return '';
  return props.options.find((option) => option.value === value.value)?.label ?? chosenLabel.value ?? value.value;
});

watch(value, (now) => {
  if (!now) chosenLabel.value = undefined;
});

function show(): void {
  if (props.disabled) return;
  typed.value = '';
  open.value = true;
}

function onSearch(event: CustomEvent<{ value?: string | null }>): void {
  typed.value = event.detail.value ?? '';
  if (serverSearch.value) query.value = typed.value.trim();
}

/** Enter in the searchbar: the first match, if there is one (never a submit of a form around). */
function chooseFirst(): void {
  const first = listed.value[0];
  if (first && !props.loading) choose(first);
}

function choose(option: SearchOption): void {
  chosenLabel.value = option.value ? option.label : undefined;
  value.value = option.value;
  open.value = false;
}

const invalid = computed(() => ({ 'ion-invalid': !!props.errorText, 'ion-touched': !!props.errorText }));
</script>

<template>
  <ion-input
    class="search-select"
    :data-testid="testid"
    :value="shown"
    :label="label"
    :placeholder="placeholder"
    label-placement="floating"
    fill="outline"
    mode="md"
    :readonly="true"
    :disabled="disabled"
    :error-text="errorText"
    :class="invalid"
    @click="show"
    @keydown.enter.prevent.stop="show"
  >
    <HubIcon
      slot="end"
      name="ion:chevron-down-outline"
      aria-hidden="true"
    />
  </ion-input>
  <ion-modal
    :is-open="open"
    :data-testid="`${testid}-modal`"
    :aria-label="label"
    @did-dismiss="open = false"
  >
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-title>{{ label }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            :aria-label="$t('tax.searchSelect.close')"
            :data-testid="`${testid}-close`"
            @click="open = false"
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
          :value="typed"
          :placeholder="$t('tax.searchSelect.search')"
          :debounce="250"
          @ion-input="onSearch"
          @keydown.enter.stop.prevent="chooseFirst"
        />
      </ion-toolbar>
    </ion-header>
    <ion-content>
      <div
        v-if="loading"
        class="ion-text-center ion-padding"
      >
        <ion-spinner :data-testid="`${testid}-loading`" />
      </div>
      <ion-list v-else-if="listed.length">
        <ion-item
          v-for="option in listed"
          :key="option.value"
          button
          :detail="false"
          :data-testid="`${testid}-option`"
          :data-value="option.value"
          :class="{ 'search-select__option--chosen': option.value === value }"
          @click="choose(option)"
        >
          <span class="search-select__label">{{ option.label }}</span>
          <HubIcon
            v-if="option.value === value"
            slot="end"
            name="ion:checkmark-outline"
          />
        </ion-item>
      </ion-list>
      <p
        v-else
        class="ion-padding ion-text-center search-select__empty"
        :data-testid="`${testid}-empty`"
      >
        {{ $t('tax.noResults') }}
      </p>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.search-select {
  cursor: pointer;
}
.search-select__empty {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.search-select__label {
  flex: 1 1 auto;
  padding: 10px 0;
}
.search-select__option--chosen {
  font-weight: 600;
}
</style>
