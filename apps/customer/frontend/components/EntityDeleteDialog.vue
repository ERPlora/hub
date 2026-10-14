<script setup lang="ts">
// «Delete» of a group, a tag or a custom field (CUSTOMER-F27–F29), in the shared ConfirmDialog (the
// product asked in an alert dialog): the question carries the consequence; confirmed, it deletes and
// says «Group {name} deleted»; the live table loses the row. A refusal stays in the dialog.
// `v-model:target` holds what is asked about.
import { ConfirmDialog } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';

interface Target {
  id: string;
  name: string;
}

const target = defineModel<Target | null>('target', { default: null });
const props = defineProps<{ kind: 'groups' | 'tags' | 'fields' }>();

const OPERATIONS = { groups: 'customer.group.delete', tags: 'customer.tag.delete', fields: 'customer.field.delete' } as const;

const { t } = useCustomerI18n();
const { run: remove, pending, error } = useCommand(OPERATIONS[props.kind]);

const shown = ref<Target | null>(target.value);
watch(target, (now) => {
  if (now) {
    shown.value = now;
    error.value = null;
  }
});

const open = computed({
  get: () => target.value !== null,
  set: (value: boolean) => {
    if (!value) target.value = null;
  },
});

async function confirm(): Promise<void> {
  const what = target.value;
  if (!what) return;
  try {
    await remove({ id: what.id });
  } catch {
    return; // the dialog shows the refusal.
  }
  target.value = null;
  void toastSuccess(t(`customer.${props.kind}.deleted`, { name: what.name }));
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    :testid="`customer-${kind}-delete`"
    tone="danger"
    :title="$t(`customer.${kind}.deleteTitle`)"
    :message="$t(`customer.${kind}.deleteMessage`, { name: shown?.name ?? '' })"
    :confirm-label="$t('customer.common.delete')"
    confirm-icon="ion:trash-outline"
    :pending="pending"
    :error="error"
    @confirm="confirm"
  />
</template>
