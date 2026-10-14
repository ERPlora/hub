<script setup lang="ts">
// TAX-F14 (teach a category alias by hand): the Alias (an outside text the inventory importer will
// meet), the Category searched on the server among all the business's and the Origin («Learned» to
// begin with), in a dialog (the old table's create panel). The server keeps the alias lowercase with
// single spaces and refuses a repeated one under Alias; the dialog closes when it is saved.
import { FormModal } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { categoryOptionLabel } from '../lib/rules';
import type { AliasSource } from '../operations';
import SearchSelect from './SearchSelect.vue';

const open = defineModel<boolean>('open', { default: false });

const SOURCES: readonly AliasSource[] = ['learned', 'shipped'];

const blank = () => ({ alias: '', category: '', source: 'learned' as AliasSource });
const form = ref(blank());
const { run, error, pending } = useCommand('tax.alias.create');

/** The category picker searches the server: all the business's categories, not a first page. */
const categoryQuery = ref('');
const categories = useLive('tax.category.list', () => ({
  search: categoryQuery.value || undefined,
  sort: 'display_name' as const,
  dir: 'asc' as const,
  limit: 50,
}));
const categoryOptions = computed(() =>
  (categories.data.value?.rows ?? []).map((category) => ({ value: category.key, label: categoryOptionLabel(category) })),
);

const complete = computed(() => form.value.alias.trim() !== '' && form.value.category !== '');
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function set<K extends keyof ReturnType<typeof blank>>(field: K, value: unknown): void {
  form.value = { ...form.value, [field]: value == null ? '' : String(value) };
}

async function save(): Promise<void> {
  try {
    await run({ alias: form.value.alias.trim(), tax_category_key: form.value.category, source: form.value.source });
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  form.value = blank();
  categoryQuery.value = '';
  error.value = null;
  open.value = false;
}

function cancel(): void {
  form.value = blank();
  categoryQuery.value = '';
  error.value = null;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="tax-alias-form"
    :title="$t('tax.aliases.form.title')"
    :submit-label="$t('tax.add')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
    @cancel="cancel"
  >
    <template #default="{ fieldErrors }">
      <div class="tax-form">
        <ion-input
          data-testid="tax-alias-form-alias"
          :value="form.alias"
          :label="$t('tax.aliases.columns.alias')"
          :placeholder="$t('tax.aliases.form.aliasPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.alias"
          :class="invalid(fieldErrors.alias)"
          @ion-input="set('alias', $event.detail.value)"
        />
        <SearchSelect
          v-model:query="categoryQuery"
          testid="tax-alias-form-category"
          :model-value="form.category"
          :options="categoryOptions"
          :loading="categories.status.value === 'loading' && !categoryOptions.length"
          :label="$t('tax.aliases.columns.category')"
          :placeholder="$t('tax.aliases.form.categoryPlaceholder')"
          :error-text="fieldErrors.tax_category_key"
          @update:model-value="set('category', $event)"
        />
        <ion-select
          data-testid="tax-alias-form-source"
          :value="form.source"
          :label="$t('tax.aliases.columns.source')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.source"
          :class="invalid(fieldErrors.source)"
          @ion-change="set('source', $event.detail.value)"
        >
          <ion-select-option
            v-for="source in SOURCES"
            :key="source"
            :value="source"
          >
            {{ $t(`tax.aliases.source.${source}`) }}
          </ion-select-option>
        </ion-select>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.tax-form {
  display: grid;
  gap: 14px;
}
</style>
