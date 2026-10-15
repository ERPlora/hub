<script setup lang="ts">
// «Sale lines in no shift» (CASH_REGISTER-F17): the sale lines that fell in no
// session (charged, voided or refunded with no session open), in the same table as a session's lines. It
// only reads them while the window is open. Nothing to do but read them: «Close».
import { FormModal } from '@erplora/ui/components';

import SessionLines from './SessionLines.vue';

const open = defineModel<boolean>('open', { required: true });
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cash-register-unassigned"
    :title="$t('cash_register.unassignedList.title')"
    :submit-label="$t('cash_register.unassignedList.close')"
    @submit="open = false"
  >
    <SessionLines
      v-if="open"
      :query="{ unassigned: true }"
      testid="cash-register-unassigned-lines"
      :empty-message="$t('cash_register.unassignedList.empty')"
    />
  </FormModal>
</template>
