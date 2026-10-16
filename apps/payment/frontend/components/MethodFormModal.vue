<script setup lang="ts">
// PAYMENT-F01 «Crear un método de pago» and F08 «Editar…»: «New method» asks for Name, Type (Bank
// transfer unless chosen) and Account, with «Create method» (`payment.method.create`); a row opens
// «Editing method — {name}» with «Save», which sends only what changed (`payment.method.update`). The
// list masks the account, so editing reads the whole method first (`payment.method.get`): the form
// shows, compares and never sends back the masked text. Refusals stay in the dialog, under their
// field, with what was typed.
import { FormModal } from '@erplora/ui/components';
import { ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { MethodOut, MethodPatchIn, MethodType } from '../operations';

const TYPES: readonly MethodType[] = ['cash', 'transfer', 'card', 'sepa', 'check', 'other'];

const props = defineProps<{
  /** The method being edited; `null` = «New method». */
  method: MethodOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  type: MethodType;
  account: string;
}

const t = useT();
const client = useLiveClient();
const creation = useCommand('payment.method.create');
const update = useCommand('payment.method.update');
/** The method being edited as the server keeps it (whole account); `null` while it is read. */
const whole = ref<MethodOut | null>(null);
const loading = ref(false);
const loadError = ref<ApiError | null>(null);
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.method ? (loadError.value ?? update.error.value) : creation.error.value));
const title = computed(() =>
  props.method ? t('payment.methods.form.titleEdit', { name: props.method.name }) : t('payment.methods.form.titleNew'),
);
const form = ref<Form>({ name: '', type: 'transfer', account: '' });

function fromMethod(method: MethodOut | null): Form {
  return method ? { name: method.name, type: method.method_type, account: method.bank_account_ref } : { name: '', type: 'transfer', account: '' };
}

/** Reads the whole method being edited (the list masks its account) and fills the form with it. */
async function loadWhole(id: string): Promise<void> {
  loading.value = true;
  try {
    const method = await client.api.call('payment.method.get', { id });
    if (props.method?.id !== id) return; // Another row opened meanwhile.
    if (typeof method?.name !== 'string') {
      // A reply that is not a method is a failed read: the form keeps the row and cannot be saved.
      loadError.value = new ApiError(200, 'unexpected_response', t('payment.methods.form.loadError'));
      return;
    }
    whole.value = method;
    form.value = fromMethod(method);
  } catch (failure) {
    loadError.value = failure as ApiError;
  } finally {
    loading.value = false;
  }
}

watch(
  () => [open.value, props.method?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromMethod(props.method && { ...props.method, bank_account_ref: '' });
    whole.value = null;
    loadError.value = null;
    creation.error.value = null;
    update.error.value = null;
    if (props.method) void loadWhole(props.method.id);
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function patch(method: MethodOut): MethodPatchIn {
  const f = form.value;
  const out: MethodPatchIn = { id: method.id };
  if (f.name.trim() !== method.name) out.name = f.name.trim();
  if (f.type !== method.method_type) out.method_type = f.type;
  if (f.account.trim() !== method.bank_account_ref) out.bank_account_ref = f.account.trim();
  return out;
}

async function save(): Promise<void> {
  const f = form.value;
  try {
    if (props.method) {
      if (!whole.value) return; // Still reading it, or it could not be read (said on top).
      await update.run(patch(whole.value));
    }
    else await creation.run({ name: f.name.trim(), method_type: f.type, bank_account_ref: f.account.trim() });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="payment-method-form"
    :title="title"
    :submit-label="method ? $t('payment.methods.form.save') : $t('payment.methods.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim() || (!!method && !whole)"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="payment-method-form">
        <ion-input
          data-testid="payment-method-form-name"
          :value="form.name"
          :label="$t('payment.methods.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-select
          data-testid="payment-method-form-type"
          :value="form.type"
          :label="$t('payment.methods.form.type')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.method_type"
          @ion-change="form = { ...form, type: $event.detail.value as MethodType }"
        >
          <ion-select-option
            v-for="type in TYPES"
            :key="type"
            :value="type"
          >
            {{ t(`payment.types.${type}`) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          data-testid="payment-method-form-account"
          :value="form.account"
          :disabled="loading"
          :label="$t('payment.methods.form.account')"
          :helper-text="$t('payment.methods.form.accountHelper')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.bank_account_ref"
          :class="invalid(fieldErrors.bank_account_ref)"
          @ion-input="form = { ...form, account: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.payment-method-form {
  display: grid;
  gap: 14px;
}
</style>
