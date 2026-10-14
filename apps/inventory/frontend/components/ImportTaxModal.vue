<script setup lang="ts">
// «CSV tax categories» (WORKBOOK INVENTORY-F09, step 2), the old modal: one block per fiscal text of
// the file that Taxes did not recognise («Rows with no tax category» for the rows that bring none),
// each with «Pick» (a category of Taxes), «Create» (Key and Name) or «Skip», and «Confirm & import».
// What is decided for a text is learned in Taxes by the importer; «Cancel» imports nothing.
import { FormModal } from '@erplora/ui/components';
import { IonInput, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed } from 'vue';

import type { TaxChoice, UnresolvedText } from '../composables/useProductImport';
import TaxCategorySelect from './TaxCategorySelect.vue';

const props = withDefaults(
  defineProps<{
    unresolved: readonly UnresolvedText[];
    /** The import is under way: it cannot be confirmed twice. */
    pending?: boolean;
  }>(),
  { pending: false },
);
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ setChoice: [text: string, patch: Partial<TaxChoice>]; confirm: []; cancel: [] }>();

/** «Pick» without a category or «Create» without a key: nothing to apply yet. */
const incomplete = computed(() =>
  props.unresolved.some(({ choice }) => (choice.mode === 'pick' && !choice.key) || (choice.mode === 'create' && !choice.newKey.trim())),
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

function setMode(item: UnresolvedText, event: CustomEvent<{ value?: unknown }>): void {
  const mode = event.detail.value;
  if ((mode === 'pick' || mode === 'create' || mode === 'skip') && mode !== item.choice.mode) emit('setChoice', item.text, { mode });
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="$t('inventory.import.taxTitle')"
    testid="inventory-import-tax"
    :submit-label="$t('inventory.import.taxConfirm')"
    :submit-disabled="incomplete"
    :pending="pending"
    @submit="emit('confirm')"
    @cancel="emit('cancel')"
  >
    <p class="import-tax__hint">
      {{ $t('inventory.import.taxHint') }}
    </p>
    <section
      v-for="(item, index) in unresolved"
      :key="item.text"
      class="import-tax__block"
    >
      <strong data-testid="inventory-import-tax-text">{{ item.text === '' ? $t('inventory.import.taxMissing') : $t('inventory.import.taxText', { text: item.text }) }}</strong>
      <ion-segment
        data-testid="inventory-import-tax-mode"
        :value="item.choice.mode"
        @ion-change="setMode(item, $event)"
      >
        <ion-segment-button value="pick">
          <ion-label>{{ $t('inventory.import.pick') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button value="create">
          <ion-label>{{ $t('inventory.import.create') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button value="skip">
          <ion-label>{{ $t('inventory.import.skip') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <div
        v-if="item.choice.mode === 'pick'"
        data-testid="inventory-import-tax-pick"
      >
        <TaxCategorySelect
          :testid="`inventory-import-tax-category-${index}`"
          :model-value="item.choice.key"
          @update:model-value="emit('setChoice', item.text, { key: $event })"
        />
      </div>
      <div
        v-else-if="item.choice.mode === 'create'"
        class="import-tax__create"
      >
        <ion-input
          data-testid="inventory-import-tax-new-key"
          :model-value="item.choice.newKey"
          :label="$t('inventory.import.newKey')"
          label-placement="floating"
          fill="outline"
          mode="md"
          placeholder="restaurant.food"
          @update:model-value="emit('setChoice', item.text, { newKey: text($event) })"
        />
        <ion-input
          data-testid="inventory-import-tax-new-name"
          :model-value="item.choice.newName"
          :label="$t('inventory.import.newName')"
          label-placement="floating"
          fill="outline"
          mode="md"
          @update:model-value="emit('setChoice', item.text, { newName: text($event) })"
        />
      </div>
    </section>
  </FormModal>
</template>

<style scoped>
.import-tax__hint {
  margin: 0 0 12px;
}

.import-tax__block {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--ion-border-color, #e6e2d8);
  border-radius: 10px;
}

.import-tax__create {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

@media (max-width: 575px) {
  .import-tax__create {
    grid-template-columns: 1fr;
  }
}
</style>
