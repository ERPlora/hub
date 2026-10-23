<script setup lang="ts">
// «Categories» of the product form (WORKBOOK INVENTORY-F01, INVENTORY-F08), as Shopify's «Collections»
// and Odoo's tags: a `Combo` of @erplora/ui that searches the business's categories on the server (at
// most 100 per query) to add one more, and the chosen ones under it as chips, each removed with its
// button; a category is never added twice nor offered once chosen. Only there when the business has
// categories: the first page, followed live, decides it and names the chosen ones (with more than one
// query holds, a category is named once a search has offered it).
import { Combo, type ComboOption, InlineFeedback } from '@erplora/ui/components';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonChip, IonLabel } from '@ionic/vue';
import { computed, nextTick, ref } from 'vue';

import { useT } from '../composables/useT';

const props = withDefaults(
  defineProps<{
    /** The ids of the chosen categories, in the order they were added. */
    modelValue: readonly string[];
    /** `data-testid` of the field; its chips take it as prefix. */
    testid: string;
    /** The server's message for this field. */
    errorText?: string;
    disabled?: boolean;
  }>(),
  { errorText: undefined, disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [ids: string[]] }>();

const { t } = useT();
const client = useLiveClient();
// At most 100 per query (the API's cap).
const PAGE = { limit: 100, sort: 'name' } as const;
const { data, status, error } = useLive('inventory.category.list', () => PAGE);

const any = computed(() => (data.value?.total ?? 0) > 0);
/** The names of the categories a search offered (beyond the first page), by id. */
const found = ref(new Map<string, string>());
const nameOf = (id: string): string => data.value?.rows.find((row) => row.id === id)?.name ?? found.value.get(id) ?? id;
const chosen = computed(() => props.modelValue.map((id) => ({ id, label: nameOf(id) })));

/** The Combo's pick, shown for one render and then emptied: the field is ready for the next category
 *  (the Combo paints its v-model when it changes). Remounting it instead would orphan its open list. */
const adding = ref<ComboOption | null>(null);

async function search(query: string): Promise<ComboOption[]> {
  const text = query.trim();
  const answer = await client.api.call('inventory.category.list', { ...PAGE, ...(text ? { search: text } : {}) });
  const next = new Map(found.value);
  for (const row of answer.rows) next.set(row.id, row.name);
  found.value = next;
  return answer.rows.filter((row) => !props.modelValue.includes(row.id)).map((row) => ({ id: row.id, label: row.name }));
}

async function add(option: ComboOption | null): Promise<void> {
  if (!option) return;
  if (!props.modelValue.includes(option.id)) emit('update:modelValue', [...props.modelValue, option.id]);
  adding.value = option;
  await nextTick();
  adding.value = null;
}

function remove(id: string): void {
  emit(
    'update:modelValue',
    props.modelValue.filter((chosenId) => chosenId !== id),
  );
}
</script>

<template>
  <div
    v-if="any"
    class="product-categories"
  >
    <Combo
      :testid="testid"
      :model-value="adding"
      :search="search"
      :label="t('inventory.form.categories')"
      :placeholder="t('inventory.form.categoriesSearch')"
      :disabled="disabled"
      :error-text="errorText"
      @update:model-value="add"
    />
    <div
      v-if="chosen.length"
      class="product-categories__chips"
    >
      <ion-chip
        v-for="category in chosen"
        :key="category.id"
        :data-testid="`${testid}-chip-${category.id}`"
      >
        <ion-label><span>{{ category.label }}</span></ion-label>
        <ion-button
          fill="clear"
          size="small"
          :disabled="disabled"
          :aria-label="t('inventory.form.removeCategory', { name: category.label })"
          :data-testid="`${testid}-remove-${category.id}`"
          @click="remove(category.id)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:close-outline"
          />
        </ion-button>
      </ion-chip>
    </div>
  </div>
  <InlineFeedback
    v-else-if="status === 'error'"
    tone="danger"
    :data-testid="`${testid}-error`"
    :heading="t('inventory.form.categoriesLoadError')"
  >
    {{ error?.message }}
  </InlineFeedback>
</template>

<style scoped>
.product-categories {
  display: grid;
  gap: 6px;
}

.product-categories__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.product-categories__chips ion-chip {
  margin: 0;
}
</style>
