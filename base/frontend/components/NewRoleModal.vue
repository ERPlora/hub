<script setup lang="ts">
// «New role»: a role of the business is made from another, basic or its own, and allows the same until it is adjusted.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { ref, watch } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import { roleName } from '../lib/people';
import { useUnsavedFormOnOpen } from '../lib/unsaved-changes';
import type { HubRoleRow } from '../operations/people';

const open = defineModel<boolean>('open', { default: false });
const props = defineProps<{
  roles: HubRoleRow[];
  /** The key of the role it starts from. */
  from: string;
}>();
const emit = defineEmits<{ created: [key: string] }>();

const { t } = useBaseI18n();
const { run, pending, error } = useCommand('base.role.create');

const name = ref('');
const basedOn = ref('');

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    error.value = null;
    name.value = '';
    basedOn.value = props.from;
  },
  { immediate: true },
);

async function create(): Promise<void> {
  let role: HubRoleRow;
  try {
    role = await run({ name: name.value.trim(), based_on: basedOn.value });
  } catch {
    return; // The window paints the refusal.
  }
  open.value = false;
  toastSuccess(t('base.roles.add.created', { name: role.label }));
  emit('created', role.key);
}

const canDismiss = useUnsavedFormOnOpen('role-new', () => ({ name: name.value, basedOn: basedOn.value }), open);
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="role-new"
    :can-dismiss="canDismiss"
    :title="t('base.roles.add.title')"
    :submit-label="t('base.roles.add.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!name.trim()"
    @submit="create"
  >
    <template #default="{ fieldErrors }">
      <ion-input
        v-model="name"
        data-testid="role-new-name"
        mode="md"
        fill="outline"
        label-placement="floating"
        :class="['ion-margin-bottom', { 'ion-invalid ion-touched': fieldErrors.name }]"
        :label="t('base.roles.add.name')"
        :maxlength="80"
        :error-text="fieldErrors.name"
      />
      <ion-select
        v-model="basedOn"
        data-testid="role-new-based-on"
        mode="md"
        fill="outline"
        interface="popover"
        label-placement="floating"
        :label="t('base.roles.add.basedOn')"
        :helper-text="t('base.roles.add.help')"
      >
        <ion-select-option
          v-for="role in roles"
          :key="role.key"
          :value="role.key"
        >
          {{ roleName(role, t) }}
        </ion-select-option>
      </ion-select>
    </template>
  </FormModal>
</template>
