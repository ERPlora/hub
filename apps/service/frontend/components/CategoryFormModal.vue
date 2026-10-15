<script setup lang="ts">
// SERVICE-F07 «Crear y editar categorías»: «New category» asks for the old panel's Name, Parent category
// (searched on the server; empty = «No parent (root)») and Order; a row opens «Editing category —
// {name}». New sends `service.category.create`; Edit only what changed with `service.category.update`
// (no parent = `parent_id: null`, a root). The category itself is never offered as its parent; the
// server refuses its descendants. Refusals stay in the dialog, under their field.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { searchServiceCategories } from '../lib/pickers';
import type { CategoryOut, CategoryPatchIn } from '../operations';

const props = defineProps<{
  /** The category being edited; `null` = «New category». */
  category: CategoryOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  parent: ComboOption | null;
  order: string;
}

const t = useT();
const client = useLiveClient();
const creation = useCommand('service.category.create');
const update = useCommand('service.category.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.category ? update.error.value : creation.error.value));
const title = computed(() =>
  props.category ? t('service.categories.form.titleEdit', { name: props.category.name }) : t('service.categories.form.titleNew'),
);
const form = ref<Form>({ name: '', parent: null, order: '0' });

const searchAll = searchServiceCategories(client);
/** The parent search, without the category itself. */
const searchParents = async (query: string): Promise<ComboOption[]> =>
  (await searchAll(query)).filter((option) => option.id !== props.category?.id);

function fromCategory(category: CategoryOut | null): Form {
  if (!category) return { name: '', parent: null, order: '0' };
  const parent = category.parent_id ? { id: category.parent_id, label: category.parent_name ?? '' } : null;
  return { name: category.name, parent, order: String(category.sort_order) };
}

watch(
  () => [open.value, props.category?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromCategory(props.category);
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function patch(category: CategoryOut): CategoryPatchIn {
  const f = form.value;
  const out: CategoryPatchIn = { id: category.id };
  if (f.name.trim() !== category.name) out.name = f.name.trim();
  if ((f.parent?.id ?? null) !== category.parent_id) out.parent_id = f.parent?.id ?? null;
  if (f.order.trim() !== String(category.sort_order)) out.sort_order = whole(f.order);
  return out;
}

async function save(): Promise<void> {
  const f = form.value;
  try {
    if (props.category) await update.run(patch(props.category));
    else await creation.run({ name: f.name.trim(), parent_id: f.parent?.id ?? null, sort_order: whole(f.order || '0') });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-category-form"
    :title="title"
    :submit-label="category ? $t('service.categories.form.save') : $t('service.categories.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="service-category-form">
        <ion-input
          data-testid="service-category-form-name"
          :value="form.name"
          :label="$t('service.categories.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <Combo
          testid="service-category-form-parent"
          :model-value="form.parent"
          :search="searchParents"
          :label="$t('service.categories.form.parent')"
          :placeholder="$t('service.categories.form.noParent')"
          :error-text="fieldErrors.parent_id"
          @update:model-value="form = { ...form, parent: $event }"
        />
        <ion-input
          data-testid="service-category-form-sort_order"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form.order"
          :label="$t('service.categories.form.order')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="form = { ...form, order: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.service-category-form {
  display: grid;
  gap: 14px;
}
</style>
