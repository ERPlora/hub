<script setup lang="ts">
// «New custom field» and «Edit · {name}» (CUSTOMER-F29), the product's panel of the Fields table as
// the shared FormModal: Name, Type, the Options of a select (comma-separated), Order and Required;
// editing adds «Active» (an inactive field leaves the cards and is not required; its values stay).
// The server's refusals go under their field: a name taken, a select without options, a type that
// cannot change once cards have values.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomFieldType, FieldRow } from '../operations';

const open = defineModel<boolean>('open', { default: false });
const props = defineProps<{ field: FieldRow | null }>();

const TYPES: CustomFieldType[] = ['text', 'number', 'date', 'boolean', 'select', 'textarea'];

const { t } = useCustomerI18n();
const create = useCommand('customer.field.create');
const update = useCommand('customer.field.update');
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => create.error.value ?? update.error.value);
const errors = computed(() => refusalFields(error.value));
const failure = computed(() => {
  const message = refusalOutsideFields(error.value, ['name', 'field_type', 'options', 'sort_order', 'is_required', 'is_active']);
  return message ? { message } : null;
});

const name = ref('');
const fieldType = ref<CustomFieldType>('text');
const options = ref('');
const order = ref<string | number>('0');
const required = ref(false);
const active = ref(true);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    create.error.value = null;
    update.error.value = null;
    name.value = props.field?.name ?? '';
    fieldType.value = props.field?.field_type ?? 'text';
    options.value = (props.field?.options ?? []).join(', ');
    order.value = String(props.field?.sort_order ?? 0);
    required.value = props.field?.is_required ?? false;
    active.value = props.field?.is_active ?? true;
  },
  { immediate: true },
);

const title = computed(() => (props.field ? t('customer.fields.editTitle', { name: props.field.name }) : t('customer.fields.new')));
const invalid = (key: string) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

async function save(): Promise<void> {
  const fields = {
    name: name.value.trim(),
    field_type: fieldType.value,
    options:
      fieldType.value === 'select'
        ? options.value
            .split(',')
            .map((o) => o.trim())
            .filter(Boolean)
        : [],
    is_required: required.value,
    sort_order: Number(order.value) || 0,
  };
  try {
    if (props.field) await update.run({ id: props.field.id, ...fields, is_active: active.value });
    else await create.run(fields);
  } catch {
    return; // the form paints the refusal.
  }
  open.value = false;
  void toastSuccess(t(props.field ? 'customer.fields.updated' : 'customer.fields.created'));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="customer-field-form"
    :title="title"
    :pending="pending"
    :error="failure"
    :submit-disabled="!name.trim()"
    @submit="save"
  >
    <div class="customer-config-form">
      <ion-input
        v-model="name"
        data-testid="customer-field-form-name"
        :label="$t('customer.fields.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="100"
        :error-text="errors.name"
        :class="invalid('name')"
      />
      <ion-select
        v-model="fieldType"
        data-testid="customer-field-form-type"
        :label="$t('customer.fields.type')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :error-text="errors.field_type"
        :class="invalid('field_type')"
      >
        <ion-select-option
          v-for="type in TYPES"
          :key="type"
          :value="type"
        >
          {{ $t(`customer.fieldType.${type}`) }}
        </ion-select-option>
      </ion-select>
      <ion-input
        v-if="fieldType === 'select'"
        v-model="options"
        data-testid="customer-field-form-options"
        :label="$t('customer.fields.options')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="errors.options"
        :class="invalid('options')"
      />
      <ion-input
        v-model="order"
        data-testid="customer-field-form-order"
        type="number"
        inputmode="numeric"
        min="0"
        :label="$t('customer.fields.order')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="errors.sort_order"
        :class="invalid('sort_order')"
      />
      <ion-checkbox
        data-testid="customer-field-form-required"
        label-placement="end"
        justify="start"
        :checked="required"
        @ion-change="required = $event.detail.checked"
      >
        {{ $t('customer.fields.required') }}
      </ion-checkbox>
      <ion-checkbox
        v-if="field"
        data-testid="customer-field-form-active"
        label-placement="end"
        justify="start"
        :checked="active"
        @ion-change="active = $event.detail.checked"
      >
        {{ $t('customer.fields.active') }}
      </ion-checkbox>
    </div>
  </FormModal>
</template>

<style scoped>
.customer-config-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
