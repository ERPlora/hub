<script setup lang="ts">
// TAX-F02 (create a category of the business's own): Key, Name and Description in a dialog (the old table's
// create panel), «Add». The server validates; the dialog closes only when it saved the category, and
// the live list paints the new row by itself. A refusal stays in the dialog, under its field.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

const open = defineModel<boolean>('open', { default: false });

const blank = () => ({ key: '', name: '', description: '' });
const form = ref(blank());
const { run, error, pending } = useCommand('tax.category.create');

const complete = computed(() => form.value.key.trim() !== '' && form.value.name.trim() !== '');
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function set(field: keyof ReturnType<typeof blank>, value: unknown): void {
  form.value = { ...form.value, [field]: value == null ? '' : String(value) };
}

async function save(): Promise<void> {
  try {
    await run({ key: form.value.key.trim(), name: form.value.name.trim(), description: form.value.description.trim() });
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  form.value = blank();
  error.value = null;
  open.value = false;
}

function cancel(): void {
  form.value = blank();
  error.value = null;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="tax-category-form"
    :title="$t('tax.categories.form.title')"
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
          data-testid="tax-category-form-key"
          :value="form.key"
          :label="$t('tax.categories.columns.key')"
          :placeholder="$t('tax.categories.form.keyPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="80"
          autocapitalize="off"
          :error-text="fieldErrors.key"
          :class="invalid(fieldErrors.key)"
          @ion-input="set('key', $event.detail.value)"
        />
        <ion-input
          data-testid="tax-category-form-name"
          :value="form.name"
          :label="$t('tax.categories.columns.name')"
          :placeholder="$t('tax.categories.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="set('name', $event.detail.value)"
        />
        <ion-input
          data-testid="tax-category-form-description"
          :value="form.description"
          :label="$t('tax.categories.columns.description')"
          :placeholder="$t('tax.categories.form.descriptionPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="1000"
          :error-text="fieldErrors.description"
          :class="invalid(fieldErrors.description)"
          @ion-input="set('description', $event.detail.value)"
        />
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
