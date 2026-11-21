<script setup lang="ts">
// «Change business?» beside the pane (BackgroundChrome), asked from the bar inside the installed app (ERPlora/app
// HUB_APP-F04). It waits while the session of this hub closes and the app forgets the hub; what failed is said in it.
import { ConfirmDialog, type FormModalError } from '@erplora/ui/components';
import { nativeBridge } from '@erplora/ui/shell';
import { shallowRef } from 'vue';

import { changeBusiness, changeBusinessOpen } from '../lib/change-business';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const bridge = nativeBridge();
const pending = shallowRef(false);
const error = shallowRef<FormModalError | null>(null);

async function confirm(): Promise<void> {
  if (!bridge || pending.value) return;
  pending.value = true;
  error.value = null;
  const outcome = await changeBusiness(bridge);
  pending.value = false;
  if (outcome !== 'left') error.value = { message: t(`base.changeBusiness.${outcome}`) };
}

function cancel(): void {
  changeBusinessOpen.value = false;
  error.value = null;
}
</script>

<template>
  <ConfirmDialog
    v-if="bridge"
    v-model:open="changeBusinessOpen"
    testid="change-business-dialog"
    tone="primary"
    confirm-icon="ion:swap-horizontal-outline"
    :title="t('base.changeBusiness.title')"
    :message="t('base.changeBusiness.message')"
    :confirm-label="t('base.changeBusiness.confirm')"
    :pending="pending"
    :error="error"
    @confirm="confirm"
    @cancel="cancel"
  />
</template>
