<script setup lang="ts">
// «New tag» and «Edit · {name}» (CUSTOMER-F28), the product's panel of the Tags table as the shared
// FormModal: Name and Color; editing adds «Active». Saved: «Tag created» / «Tag updated». A name taken
// by another active tag is said under «Name»; anything else on top of the form.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { colorOptions } from '../lib/colors';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { TagRow } from '../operations';

const open = defineModel<boolean>('open', { default: false });
const props = defineProps<{ tag: TagRow | null }>();

const { t } = useCustomerI18n();
const create = useCommand('customer.tag.create');
const update = useCommand('customer.tag.update');
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => create.error.value ?? update.error.value);
const errors = computed(() => refusalFields(error.value));
const failure = computed(() => {
  const message = refusalOutsideFields(error.value, ['name', 'color', 'is_active']);
  return message ? { message } : null;
});

const name = ref('');
const color = ref('primary');
const active = ref(true);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    create.error.value = null;
    update.error.value = null;
    name.value = props.tag?.name ?? '';
    color.value = props.tag?.color || 'primary';
    active.value = props.tag?.is_active ?? true;
  },
  { immediate: true },
);

const title = computed(() => (props.tag ? t('customer.tags.editTitle', { name: props.tag.name }) : t('customer.tags.new')));
const invalid = (key: string) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

async function save(): Promise<void> {
  const fields = { name: name.value.trim(), color: color.value };
  try {
    if (props.tag) await update.run({ id: props.tag.id, ...fields, is_active: active.value });
    else await create.run(fields);
  } catch {
    return; // the form paints the refusal.
  }
  open.value = false;
  void toastSuccess(t(props.tag ? 'customer.tags.updated' : 'customer.tags.created'));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="customer-tag-form"
    :title="title"
    :pending="pending"
    :error="failure"
    :submit-disabled="!name.trim()"
    @submit="save"
  >
    <div class="customer-config-form">
      <ion-input
        v-model="name"
        data-testid="customer-tag-form-name"
        :label="$t('customer.tags.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="60"
        :error-text="errors.name"
        :class="invalid('name')"
      />
      <ion-select
        v-model="color"
        data-testid="customer-tag-form-color"
        :label="$t('customer.tags.color')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :error-text="errors.color"
        :class="invalid('color')"
      >
        <ion-select-option
          v-for="option in colorOptions(tag?.color ?? '')"
          :key="option"
          :value="option"
        >
          {{ $te(`customer.colors.${option}`) ? $t(`customer.colors.${option}`) : option }}
        </ion-select-option>
      </ion-select>
      <ion-checkbox
        v-if="tag"
        data-testid="customer-tag-form-active"
        label-placement="end"
        justify="start"
        :checked="active"
        @ion-change="active = $event.detail.checked"
      >
        {{ $t('customer.tags.active') }}
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
