<script setup lang="ts">
// «New group» and «Edit · {name}» (CUSTOMER-F27), the product's panel of the Groups table as the
// shared FormModal: Name (required), Description, Color and Order; editing adds «Active» (a group
// not active is no longer offered on the cards, which keep it). Saved: «Group created» / «Group
// updated» and it closes; the live table paints the change. A name taken by another active group is
// said under «Name»; anything else on top of the form.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { colorOptions } from '../lib/colors';
import { withApproval } from '../../../../base/frontend/lib/approval';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { GroupRow } from '../operations';

const open = defineModel<boolean>('open', { default: false });
const props = defineProps<{ group: GroupRow | null }>();

const { t } = useCustomerI18n();
const create = useCommand('customer.group.create');
const update = useCommand('customer.group.update');
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => create.error.value ?? update.error.value);
const FIELDS = ['name', 'description', 'color', 'sort_order', 'is_active'];
const errors = computed(() => refusalFields(error.value));
const failure = computed(() => {
  const message = refusalOutsideFields(error.value, FIELDS);
  return message ? { message } : null;
});

const name = ref('');
const description = ref('');
const color = ref('primary');
const order = ref<string | number>('0');
const active = ref(true);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    create.error.value = null;
    update.error.value = null;
    name.value = props.group?.name ?? '';
    description.value = props.group?.description ?? '';
    color.value = props.group?.color || 'primary';
    order.value = String(props.group?.sort_order ?? 0);
    active.value = props.group?.is_active ?? true;
  },
  { immediate: true },
);

const title = computed(() => (props.group ? t('customer.groups.editTitle', { name: props.group.name }) : t('customer.groups.new')));
const invalid = (key: string) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

async function save(): Promise<void> {
  const fields = {
    name: name.value.trim(),
    description: description.value.trim(),
    color: color.value,
    sort_order: Number(order.value) || 0,
  };
  try {
    // A manager's PIN lets an employee create or change it (BASE-F84, `apps.py` `approvals`).
    if (props.group) await withApproval(() => update.run({ id: props.group.id, ...fields, is_active: active.value }));
    else await withApproval(() => create.run(fields));
  } catch {
    return; // the form paints the refusal.
  }
  open.value = false;
  void toastSuccess(t(props.group ? 'customer.groups.updated' : 'customer.groups.created'));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="customer-group-form"
    :title="title"
    :pending="pending"
    :error="failure"
    :submit-disabled="!name.trim()"
    @submit="save"
  >
    <div class="customer-config-form">
      <ion-input
        v-model="name"
        data-testid="customer-group-form-name"
        :label="$t('customer.groups.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="100"
        :error-text="errors.name"
        :class="invalid('name')"
      />
      <ion-input
        v-model="description"
        data-testid="customer-group-form-description"
        :label="$t('customer.groups.description')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="1000"
        :error-text="errors.description"
        :class="invalid('description')"
      />
      <ion-select
        v-model="color"
        data-testid="customer-group-form-color"
        :label="$t('customer.groups.color')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :error-text="errors.color"
        :class="invalid('color')"
      >
        <ion-select-option
          v-for="option in colorOptions(group?.color ?? '')"
          :key="option"
          :value="option"
        >
          {{ $te(`customer.colors.${option}`) ? $t(`customer.colors.${option}`) : option }}
        </ion-select-option>
      </ion-select>
      <ion-input
        v-model="order"
        data-testid="customer-group-form-order"
        type="number"
        inputmode="numeric"
        min="0"
        :label="$t('customer.groups.order')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="errors.sort_order"
        :class="invalid('sort_order')"
      />
      <ion-checkbox
        v-if="group"
        data-testid="customer-group-form-active"
        label-placement="end"
        justify="start"
        :checked="active"
        @ion-change="active = $event.detail.checked"
      >
        {{ $t('customer.groups.active') }}
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
