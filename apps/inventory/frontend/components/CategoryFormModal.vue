<script setup lang="ts">
// The category form (WORKBOOK «Categorías», INVENTORY-F06), the old table's side panel as a dialog
// (FormModal; UI-REQUESTS.md asks for DataTable's side panel): «New category» or «Editing category —
// <name>», with Name, «Slug (optional)» (empty: the server makes it from the name) and «Tax rate»
// («— (default)» or a tax category of Taxes). An edit sends only what changed, so what the screen
// does not show (description, icon, colour, order) stays as it is. A refusal stays in the dialog.
import { FormModal } from '@erplora/ui/components';
import { type OutputOf, useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { errorFields } from '../lib/errors';
import TaxCategorySelect from './TaxCategorySelect.vue';

type Category = OutputOf<'inventory.category.list'>['rows'][number];

interface Fields {
  name: string;
  slug: string;
  tax: string;
}

const props = defineProps<{ category: Category | null }>();
const open = defineModel<boolean>('open', { default: false });

const { t } = useT();
const create = useCommand('inventory.category.create');
const update = useCommand('inventory.category.update');

const editing = computed(() => props.category !== null);
const original = computed<Fields>(() => ({
  name: props.category?.name ?? '',
  slug: props.category?.slug ?? '',
  tax: props.category?.tax_category_key ?? '',
}));
const form = ref<Fields>({ ...original.value });

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    form.value = { ...original.value };
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const command = computed(() => (editing.value ? update : create));
const error = computed(() => command.value.error.value);
const pending = computed(() => command.value.pending.value);
const fields = computed(() => errorFields(error.value));
const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

const title = computed(() =>
  editing.value ? t('inventory.categories.form.editTitle', { name: props.category?.name ?? '' }) : t('inventory.categories.form.newTitle'),
);

function set(key: keyof Fields, value: unknown): void {
  form.value = { ...form.value, [key]: value === null || value === undefined ? '' : String(value) };
}

async function save(): Promise<void> {
  const name = form.value.name.trim();
  if (!name) return;
  const slug = form.value.slug.trim();
  try {
    if (props.category) {
      const changed = {
        ...(name !== original.value.name ? { name } : {}),
        // An emptied slug is not sent: the category keeps its own (never an empty one).
        ...(slug && slug !== original.value.slug ? { slug } : {}),
        ...(form.value.tax !== original.value.tax ? { tax_category_key: form.value.tax } : {}),
      };
      await update.run({ id: props.category.id, ...changed });
    } else {
      // Without a slug the server makes it from the name.
      await create.run({ name, ...(slug ? { slug } : {}), tax_category_key: form.value.tax || null });
    }
  } catch {
    return; // the dialog paints the error and stays open.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="title"
    testid="inventory-category-form"
    :submit-label="editing ? $t('inventory.common.saveChanges') : $t('inventory.common.save')"
    :cancel-label="editing ? $t('inventory.categories.form.cancelEdit') : $t('inventory.common.cancel')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <div class="category-form">
      <ion-input
        data-testid="inventory-category-name"
        :model-value="form.name"
        :label="$t('inventory.categories.form.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="100"
        :error-text="fields.name"
        :class="invalid('name')"
        @update:model-value="set('name', $event)"
      />
      <ion-input
        data-testid="inventory-category-slug"
        :model-value="form.slug"
        :label="$t('inventory.categories.form.slug')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="120"
        :error-text="fields.slug"
        :class="invalid('slug')"
        @update:model-value="set('slug', $event)"
      />
      <TaxCategorySelect
        testid="inventory-category-tax"
        allow-default
        :label="$t('inventory.categories.form.tax')"
        :model-value="form.tax"
        :error-text="fields.tax_category_key"
        @update:model-value="set('tax', $event)"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.category-form {
  display: grid;
  gap: 16px;
}
</style>
