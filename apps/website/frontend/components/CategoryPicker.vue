<script setup lang="ts">
// CategoryPicker — which categories of the catalog's source the website shows: none chosen = every category (the
// usual default of Shopify's and Square's online catalogs). The categories are read from `website.catalog.categories`
// (the website's own read of Inventory or Services, never their operations from here) each time the source changes;
// while they load the select waits, and a failed read says so.
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { IonNote, IonSelect, IonSelectOption } from '@ionic/vue';
import { ref, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import type { CatalogSource } from '../operations';

const props = withDefaults(
  defineProps<{
    source: CatalogSource;
    modelValue: string[];
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>();

const t = useT();
const client = useLiveClient();
const categories = shallowRef<{ id: string; name: string }[]>([]);
const loading = ref(false);
const failed = ref<ApiError | null>(null);
let asked = 0;

watch(
  () => props.source,
  async (source) => {
    const mine = ++asked;
    loading.value = true;
    failed.value = null;
    try {
      const answer = await client.api.call('website.catalog.categories', { source });
      if (mine === asked) categories.value = answer.categories;
    } catch (error) {
      if (mine === asked) {
        categories.value = [];
        failed.value = error as ApiError;
      }
    } finally {
      if (mine === asked) loading.value = false;
    }
  },
  { immediate: true },
);

function pick(value: unknown): void {
  emit('update:modelValue', Array.isArray(value) ? value.map(String) : []);
}
</script>

<template>
  <ion-select
    data-testid="website-catalog-categories"
    :label="t('website.fields.categories')"
    label-placement="stacked"
    interface="popover"
    multiple
    :placeholder="t('website.fields.allCategories')"
    :value="modelValue"
    :disabled="disabled || loading"
    @ion-change="pick($event.detail.value)"
  >
    <ion-select-option
      v-for="category in categories"
      :key="category.id"
      :value="category.id"
    >
      {{ category.name }}
    </ion-select-option>
  </ion-select>
  <ion-note
    v-if="failed"
    color="danger"
    role="alert"
    data-testid="website-catalog-categories-error"
  >
    {{ t('website.fields.categoriesError') }}
  </ion-note>
</template>
