<script setup lang="ts">
// «New drawer» / «Rename drawer» (CASH_REGISTER-F02): the drawer's «Name», required. «Save» creates it (or
// renames it) and says so; a name another drawer already has — whatever its case — is said at the field until the
// person types another one.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';

const props = defineProps<{ register: { id: string; name: string } | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const create = useCommand('cash_register.register.create');
const update = useCommand('cash_register.register.update');

const name = shallowRef('');
const missing = shallowRef(false);

watch(
  open,
  (now) => {
    if (!now) return;
    name.value = props.register?.name ?? '';
    missing.value = false;
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);
watch(name, () => {
  missing.value = false;
});

const pending = computed(() => create.pending.value || update.pending.value);
const error = computed<FormModalError | null>(() => refusal(create.error.value ?? update.error.value, t('cash_register.registers.modal.failed')));
const nameError = (fieldErrors: Readonly<Record<string, string>>): string | undefined =>
  missing.value ? t('cash_register.registers.modal.required') : fieldErrors.name;

async function confirm(): Promise<void> {
  const text = name.value.trim();
  missing.value = !text;
  if (!text) return;
  try {
    if (props.register) await update.run({ register_id: props.register.id, name: text });
    else await create.run({ name: text });
  } catch {
    return; // The window shows the refusal.
  }
  void toastSuccess(t(props.register ? 'cash_register.registers.modal.renamed' : 'cash_register.registers.modal.created'));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('cash-register-register', name, open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    size="sm"
    testid="cash-register-register"
    :title="register ? $t('cash_register.registers.modal.rename') : $t('cash_register.registers.modal.create')"
    :submit-label="$t('cash_register.registers.modal.save')"
    :cancel-label="$t('cash_register.registers.modal.cancel')"
    :pending="pending"
    :error="error"
    @submit="confirm"
  >
    <template #default="{ fieldErrors }">
      <ion-input
        data-testid="cash-register-register-name"
        name="name"
        :label="$t('cash_register.registers.modal.name')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="100"
        :value="name"
        :error-text="nameError(fieldErrors)"
        :class="{ 'ion-invalid': !!nameError(fieldErrors), 'ion-touched': !!nameError(fieldErrors) }"
        @ion-input="name = String($event.detail.value ?? '')"
      />
    </template>
  </FormModal>
</template>
